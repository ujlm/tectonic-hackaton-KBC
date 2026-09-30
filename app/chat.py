"""Chat: Claude with tool use, plus an offline rule-based fallback when no API key is set.

The API key is read from the environment by the Anthropic SDK and never printed or logged.
"""
import json
import logging
import os
import re

from .assumptions import CATALOGUE, EDITABLE, Engine, ValidationError, parse_month
from .common import CITY_NAMES, MOMENT_LABELS, MOMENTS
from .services.registry import SERVICES, catalogue

log = logging.getLogger("chat")

DEFAULT_MODEL = "claude-sonnet-5-5"
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5", "claude-opus-5", "claude-fable-5-1"}
MAX_TOOL_ROUNDS = 6
_use_fallbacks = True

SYSTEM_PROMPT = """You are Kate, the assistant in the KBC Mobile banking app (this is a hackathon demo: all customer \
data is synthetic and every service integration is simulated). You help one customer review and correct the \
assumptions behind the bank's predictions, and you turn those predictions into concrete, helpful next steps.
The models estimate five moments for the next 12 months (Oct 2026 - Sep 2027): moving house, buying a car, renovating, \
starting to invest, and a cash squeeze (the current account going below zero). Today is 1 October 2026.

How to work:
- Reply in the language of the customer's latest message (Dutch, French or English).
- Keep replies short: two or three sentences, no headings, no lists unless asked.
- When the customer corrects a fact, call update_feature. When they say an assumption is right, call \
confirm_assumption. When they tell you about a planned event and when it happens, call declare_life_event; if they \
say an event will not happen (e.g. "I don't need a car"), call it with month "none".
- After every change, say what changed in numbers, using the before/after probabilities from the tool result, for \
example "Car purchase went from 34% to 4%."
- If a value or a month is ambiguous ("a few thousand", "soon", "next year"), ask one short clarifying question \
instead of guessing.
- Only the editable features listed below can be changed. If the customer disputes something that comes from the \
bank's own records (balances, days below zero, app visits, product dates, service usage counts), explain briefly that \
it can't be edited here.
- Never infer, ask about or discuss health, pregnancy, religion, ethnic origin or nationality, or trade-union \
membership, and never store such information. The one exception: a customer may declare a birth with \
declare_life_event(event="birth", month=...). Acknowledge it neutrally and do not ask follow-up questions about it. \
Helena (medical data), charity donations, the digital safe and eBox contents are never used.

Services and journeys:
- KBC Mobile offers third-party services (ids and actions below). Use get_journey to see where the customer is in a \
moment's journey and which help fits; prefer free information and service actions over KBC products, and only suggest \
a product when the journey is at the deciding stage or later. It's fine to recommend NOT buying something.
- Propose actions naturally ("Want me to prepare the registered e-mail to your landlord?"). When the customer wants \
one, call prepare_service_action. It only prepares a confirmation card: the customer must tap the button on the card to \
execute it. You never execute anything yourself and never say an action is done; say it's ready for them to confirm.
- If a required parameter is missing (e.g. the destination of a train ticket), ask for it first.

Service ids and actions: {services}

Editable features (name: meaning; type; allowed range):
{features}
"""


def _service_lines() -> str:
    return "; ".join(f"{sv.id} ({sv.name}): " + ", ".join(a.id for a in sv.actions) for sv in SERVICES.values())


def _feature_lines() -> str:
    lines = []
    for f, c in EDITABLE.items():
        meaning = c["label"].replace("{value}", "X")
        t = c["type"]
        if t == "choice":
            rng = "one of " + ", ".join(c["options"])
        elif t == "bool":
            rng = "true/false"
        elif t == "ratio":
            rng = f"fraction {c['min']}-{c['max']} (0.35 = 35%)"
        else:
            rng = f"{c['min']:,}-{c['max']:,}" + (f" {c['unit']}" if c.get("unit") else "")
        extra = " (null = not applicable)" if c.get("nullable") else ""
        when = {"ahead": " (counted from now)", "ago": " (counted back from now)"}.get(c.get("when"), "")
        lines.append(f"- {f}: {meaning}; {t}{when}; {rng}{extra}")
    return "\n".join(lines)


TOOLS = [
    {
        "name": "get_state",
        "description": "Get the customer's current predictions (with 'people like you' rates), assumption cards "
                       "and all editable feature values. Use it when you need values not in the snapshot.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "update_feature",
        "description": "Correct one assumption with a value the customer gave. Only editable features are accepted; "
                       "the value is validated for type and range. Returns the change and before/after probabilities "
                       "for every moment that moved.",
        "input_schema": {
            "type": "object",
            "properties": {
                "feature": {"type": "string", "enum": list(EDITABLE), "description": "Editable feature name."},
                "value": {"description": "New value: euros as a number, ratios as fractions (0.35 = 35%), months, "
                                         "years and counts as whole numbers, booleans as true/false, "
                                         "employment_type as a string, or null for 'not applicable'."},
            },
            "required": ["feature", "value"],
        },
    },
    {
        "name": "confirm_assumption",
        "description": "Mark an assumption as confirmed by the customer (it stays unchanged).",
        "input_schema": {
            "type": "object",
            "properties": {"feature": {"type": "string", "description": "Feature name of the assumption card, or 'cohort'."}},
            "required": ["feature"],
        },
    },
    {
        "name": "list_services",
        "description": "List the third-party services in KBC Mobile with their actions, parameters (and defaults), and "
                       "whether an action costs money or sends something. All integrations are simulated.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "prepare_service_action",
        "description": "Prepare a service action as a confirmation card in the app. Does NOT execute: the customer "
                       "must tap the card's button. Missing optional parameters use sensible defaults from the "
                       "customer's context (their city, number plate, overdue invoices...).",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "enum": list(SERVICES), "description": "Service id."},
                "action": {"type": "string", "description": "Action id of that service."},
                "params": {"type": "object", "description": "Action parameters, e.g. {\"destination\": \"Gent\"}."},
            },
            "required": ["service", "action"],
        },
    },
    {
        "name": "get_journey",
        "description": "Journey stage of one moment (exploring/deciding/doing/after; cash squeeze: forecast/short), the "
                       "rule that set it, the help items that fit now (free info, service actions, KBC products, "
                       "advisor) and what Kate plans to say proactively this quarter.",
        "input_schema": {
            "type": "object",
            "properties": {"moment": {"type": "string", "enum": MOMENTS}},
            "required": ["moment"],
        },
    },
    {
        "name": "declare_life_event",
        "description": "Record a future event the customer told us about. The moment is then shown as told by the "
                       "customer (95%, or 5% if not planned) next to the model's own estimate. A birth can only be "
                       "declared, never predicted.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event": {"type": "string", "enum": ["move_house", "buy_car", "renovation", "start_investing", "birth"]},
                "month": {"type": "string", "description": "YYYY-MM between 2026-10 and 2027-09, or 'none' if the "
                                                           "customer says it will not happen."},
            },
            "required": ["event", "month"],
        },
    },
]


def pct(p) -> str:
    return "—" if p is None else f"{p * 100:.0f}%"


def snapshot(state: dict) -> str:
    p = state["profile"]
    lines = [f"[Bank context, not written by the customer] Customer: {p['first_name']}, {p['age']}, {p['region']}, "
             f"household of {p['household_size']}, {p['employment_type']}.",
             "Predictions: " + "; ".join(
                 f"{x['label']} {pct(x['probability'])}" + (f" ({x['declared_label']}, model {pct(x['model_probability'])})"
                                                           if x["declared"] else f" (people like you {pct(x['neighbour_rate'])})")
                 for x in state["predictions"]),
             "Assumption cards:"]
    for c in state["cards"]:
        eff = ", ".join(f"{e['pts']:+.0f} pts {e['label'].lower()}" for e in c["effects"][:3])
        lines.append(f"- {c['feature']}: \"{c['sentence']}\" ({'editable' if c['editable'] else 'not editable'}, "
                     f"{c['status']}; effect: {eff or 'small'})")
    stages = [f"{j['label']}: {j['stage']}" for j in state.get("journeys", []) if j["stage"]]
    if stages:
        lines.append("Journey stages: " + "; ".join(stages))
    pending = [f"{a['id']} {a['service_name']} · {a['action_name']}" for a in state.get("actions", []) if a["status"] == "prepared"]
    if pending:
        lines.append("Waiting for the customer's tap: " + "; ".join(pending))
    return "\n".join(lines)


def _tool_result(engine: Engine, uid: int, name: str, args: dict) -> tuple[dict, bool]:
    try:
        if name == "get_state":
            st = engine.state(uid)
            vals = engine.values(uid)
            return {"snapshot": snapshot(st), "editable_values": {f: _plain(vals.get(f)) for f in EDITABLE}}, False
        if name == "list_services":
            return {"services": catalogue(), "note": "All integrations are simulated."}, False
        if name == "get_journey":
            st = engine.state(uid)
            j = next((x for x in st["journeys"] if x["moment"] == args.get("moment")), None)
            if j is None:
                return {"error": f"Unknown moment '{args.get('moment')}'. Use one of: {', '.join(MOMENTS)}."}, True
            plan = [p for p in st["kate"]["passed"] if p["moment"] == j["moment"]]
            held = [{"item": h["title"], "reason": h["reason"], "detail": h["detail"]} for h in st["kate"]["held"]
                    if h["moment"] == j["moment"]]
            return {"moment": j["label"], "probability": pct(j["probability"]), "stage": j["stage"], "rule": j["rule"],
                    "help_now": [{"kind": i["kind"], "title": i["title"], "kate_says": i["say"], "action": i["action"]} for i in j["items"]],
                    "next_stage": j["next_stage"], "proactive_this_quarter": [{"month": p["month"], "channel": p["channel"]} for p in plan],
                    "held_back": held}, False
        if name == "prepare_service_action":
            r = engine.prepare_action(uid, args.get("service"), args.get("action"), args.get("params") or {})
            c = r["card"]
            return {"ok": True, "prepared": {"id": c["id"], "summary": c["summary"], "price": c["price_text"], "button": c["button"]},
                    "note": "Shown to the customer as a confirmation card. Nothing is executed until they tap the button."}, False
        if name == "update_feature":
            r = engine.override(uid, args.get("feature"), args.get("value"))
        elif name == "confirm_assumption":
            r = engine.confirm(uid, args.get("feature"))
        elif name == "declare_life_event":
            r = engine.declare(uid, args.get("event"), args.get("month"))
        else:
            return {"error": f"Unknown tool {name}"}, True
        return {"ok": True, "change": r["change"],
                "probabilities": [{"moment": d["label"], "before": pct(d["before"]), "after": pct(d["after"])}
                                  for d in r["diff"]]}, False
    except ValidationError as e:
        return {"error": str(e)}, True


def _plain(x):
    return None if isinstance(x, float) and x != x else x


def _history(history) -> list[dict]:
    msgs = []
    for h in history or []:
        role, content = h.get("role"), h.get("content")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            if msgs and msgs[-1]["role"] == role:
                msgs[-1]["content"] += "\n\n" + content
            else:
                msgs.append({"role": role, "content": content})
    msgs = msgs[-20:]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    if msgs and msgs[-1]["role"] == "user":  # the new message follows; keep strict alternation
        msgs.append({"role": "assistant", "content": "(no reply)"})
    return msgs


def _echo(content) -> list:
    """Blocks to send back as the assistant turn. After a server-side fallback, drop the declined model's
    non-text blocks that precede the last fallback marker."""
    blocks = list(content)
    last = max((i for i, b in enumerate(blocks) if b.type == "fallback"), default=None)
    if last is None:
        return blocks
    return [b for i, b in enumerate(blocks) if i > last or (i < last and b.type == "text")]


def _create(client, **kw):
    global _use_fallbacks
    import anthropic
    if _use_fallbacks and kw["model"] in FALLBACK_MODELS:
        try:
            return client.beta.messages.create(**kw, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
        except anthropic.BadRequestError as e:
            log.warning("Fallbacks rejected (%s); continuing without them", e.status_code)
            _use_fallbacks = False
    try:
        return client.messages.create(**kw)
    except anthropic.BadRequestError:
        kw.pop("output_config", None)  # e.g. a model without effort support
        return client.messages.create(**kw)


def claude_chat(engine: Engine, uid: int, message: str, history) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    model = os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
    messages = _history(history) + [{"role": "user", "content": [
        {"type": "text", "text": snapshot(engine.state(uid))},
        {"type": "text", "text": message},
    ]}]
    kw = dict(
        model=model, max_tokens=4096,
        system=[{"type": "text", "text": SYSTEM_PROMPT.format(features=_feature_lines(), services=_service_lines()),
                 "cache_control": {"type": "ephemeral"}}],
        tools=TOOLS, output_config={"effort": "low"},
    )
    actions, reply = [], ""
    for _ in range(MAX_TOOL_ROUNDS):
        resp = _create(client, messages=messages, **kw)
        if resp.stop_reason == "refusal":
            reply = "Sorry, I can't help with that here."
            break
        blocks = _echo(resp.content)
        messages.append({"role": "assistant", "content": blocks})
        tool_uses = [b for b in blocks if b.type == "tool_use"]
        text = " ".join(b.text for b in blocks if b.type == "text").strip()
        if resp.stop_reason != "tool_use" or not tool_uses:
            reply = text
            break
        results = []
        for tu in tool_uses:
            args = tu.input if isinstance(tu.input, dict) else {}
            out, is_error = _tool_result(engine, uid, tu.name, args)
            actions.append({"tool": tu.name, "input": args, "ok": not is_error, **({"error": out["error"]} if is_error else {})})
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": json.dumps(out, default=str),
                            **({"is_error": True} if is_error else {})})
        messages.append({"role": "user", "content": results})
    return {"reply": reply or "Done.", "actions": actions, "mode": "claude", "model": model}


# ------------------------------------------------------------------------------------------------
# Offline rule-based fallback
# ------------------------------------------------------------------------------------------------
LABELS = {
    "nl": {"move_house": "Verhuizen", "buy_car": "Een auto kopen", "renovation": "Verbouwen",
           "start_investing": "Beginnen met beleggen", "cash_squeeze": "Krap bij kas", "birth": "Een baby"},
    "fr": {"move_house": "Déménager", "buy_car": "Acheter une voiture", "renovation": "Rénover",
           "start_investing": "Commencer à investir", "cash_squeeze": "Découvert", "birth": "Un bébé"},
    "en": {m: l for m, l in MOMENT_LABELS.items()},
}
T = {
    "went": {"en": "{label} went from {a} to {b}.", "nl": "{label} ging van {a} naar {b}.", "fr": "{label} passe de {a} à {b}."},
    "updated": {"en": "Updated: “{s}”.", "nl": "Aangepast: “{s}”.", "fr": "Mis à jour : « {s} »."},
    "declared": {"en": "Noted: {label} in {month}.", "nl": "Genoteerd: {label} in {month}.", "fr": "C'est noté : {label} en {month}."},
    "not_planned": {"en": "Noted: {label} is not planned.", "nl": "Genoteerd: {label} is niet gepland.",
                    "fr": "C'est noté : {label} n'est pas prévu."},
    "confirmed": {"en": "Thanks, I've marked \"{s}\" as confirmed.", "nl": "Bedankt, \"{s}\" staat nu als bevestigd.",
                  "fr": "Merci, « {s} » est confirmé."},
    "which_month": {"en": "In which month do you expect that?", "nl": "In welke maand verwacht je dat?",
                    "fr": "Pour quel mois le prévoyez-vous ?"},
    "help": {"en": "I'm in offline mode and understand simple corrections, e.g. \"my income is €3,200\", \"my car is 2 years "
                   "old\", \"we're moving in March\" or \"that's right\".",
             "nl": "Ik werk offline en begrijp eenvoudige correcties, bv. \"mijn inkomen is €3.200\", \"mijn auto is 2 jaar "
                   "oud\", \"we verhuizen in maart\" of \"klopt\".",
             "fr": "Je suis hors ligne et je comprends des corrections simples, p. ex. « mon salaire est de 3 200 € », "
                   "« ma voiture a 2 ans », « nous déménageons en mars » ou « c'est exact »."},
    "prepared": {"en": "I've prepared this for you: {summary} Nothing happens until you tap “{button}”.",
                 "nl": "Ik heb dit voor je klaargezet: {summary} Er gebeurt niets tot je op “{button}” tikt.",
                 "fr": "J'ai préparé ceci : {summary} Rien ne se passe tant que vous n'appuyez pas sur « {button} »."},
    "where_to": {"en": "Where would you like to go by train?", "nl": "Naar waar wil je met de trein?",
                 "fr": "Vous allez où en train ?"},
    "landlord_offer": {"en": "Since you rent, I've also prepared the registered e-mail to your landlord.",
                       "nl": "Omdat je huurt, heb ik ook de aangetekende e-mail aan je verhuurder klaargezet.",
                       "fr": "Comme vous êtes locataire, j'ai aussi préparé l'e-mail recommandé pour votre propriétaire."},
    "cambio_offer": {"en": "Curious what car sharing would cost you instead?", "nl": "Benieuwd wat autodelen je zou kosten?",
                     "fr": "Curieux de savoir ce que coûterait l'autopartage ?"},
    "no_change": {"en": "No probabilities changed noticeably.", "nl": "Geen enkele kans veranderde merkbaar.",
                  "fr": "Aucune probabilité n'a sensiblement changé."},
}

NL_WORDS = {"ik", "wij", "mijn", "niet", "geen", "een", "het", "klopt", "maand", "maanden", "jaar", "ben", "heb",
            "hebben", "gaan", "verhuizen", "onze", "ons", "loon", "inkomen", "juist", "dat", "nog", "zijn", "wordt",
            "verbouwen", "kopen", "gekocht", "nieuwe", "oud", "spaargeld", "kinderen", "huren", "maart", "mei", "naar",
            "morgen", "graag", "wil", "trein", "treinticket", "parkeren", "voor", "uur", "minuten", "nodig", "auto"}
FR_WORDS = {"je", "nous", "mon", "ma", "mes", "pas", "une", "le", "la", "les", "voiture", "mois", "salaire", "ans",
            "est", "c'est", "j'ai", "nos", "notre", "déménager", "déménageons", "exact", "vrai", "au", "du", "des",
            "acheté", "nouvelle", "épargne", "enfants", "louons", "mars", "mai", "bébé", "à", "pour", "garer", "billet",
            "demain", "veux", "heures", "besoin", "abonnement", "voudrais", "plus", "déménageons", "n'ai", "je"}
EN_WORDS = {"i", "my", "our", "is", "the", "a", "an", "that's", "right", "car", "salary", "income", "moving",
            "bought", "years", "months", "not", "old", "new", "was", "were", "for", "have", "don't", "it", "we're",
            "please", "want", "park", "ticket", "to", "hours", "need", "train", "stop"}

EVENT_PATTERNS = {
    "birth": r"\b(baby|birth|born|geboorte|bevalling|naissance|bébé|bebe)\b",
    "move_house": r"(verhuiz|\bmov(e|ing)\b|déménag|demenag)",
    "buy_car": r"((buy|buying|get|kopen|acheter|nouvelle|nieuwe|new)\b.{0,15}\b(car|auto|voiture))",
    "renovation": r"(renovat|verbouw|rénov|renov)",
    "start_investing": r"(invest|belegg|placement|placer)",
}
NEGATION = r"\b(not|no|never|don't|dont|won't|wont|niet|geen|nooit|pas|jamais|aucun)\b"
MONTH_RE = (r"\b(\d{4}-\d{1,2}|next month|volgende maand|mois prochain|"
            r"jan(uary|uari|vier)?|feb(ruary|ruari)?|févr(ier)?|fevrier|mar(ch)?|maart|mars|apr(il)?|avril|may|mei|mai|"
            r"jun(e|i)?|juin|jul(y|i)?|juillet|aug(ust|ustus)?|août|aout|sep(t|tember|tembre)?|oct(ober|obre)?|okt(ober)?|"
            r"nov(ember|embre)?|dec(ember)?|décembre|decembre)\b")
AMOUNT_RE = r"(?:€\s*)?(\d{1,3}(?:[.,\s]\d{3})+|\d+(?:[.,]\d+)?)\s*(k\b)?\s*(?:€|eur|euro)?"


CITY_ALIASES = {c.lower(): c for c in CITY_NAMES} | {
    "brussel": "Brussels", "bruxelles": "Brussels", "gand": "Gent", "ghent": "Gent", "anvers": "Antwerpen",
    "antwerp": "Antwerpen", "louvain": "Leuven", "bruges": "Brugge", "malines": "Mechelen", "luik": "Liège",
    "liege": "Liège", "namen": "Namur", "bergen": "Mons", "courtrai": "Kortrijk", "doornik": "Tournai", "ostend": "Oostende",
    "oostende": "Oostende", "ostende": "Oostende", "alost": "Aalst", "hasselt": "Hasselt",
}
NO_CAR = (r"((don'?t|do not|no longer)\s+need\s+(a\s+)?car|geen\s+auto\s+(meer\s+)?nodig|auto\s+niet\s+(meer\s+)?nodig|"
          r"(pas|plus)\s+besoin\s+d[e']?\s*(une\s+)?voiture)")
PARKING = r"\b(park|parking|parkeren|parkeer|stationner|stationnement|garer)\b"
TRAIN = r"\b(train|trein|treinticket|treinkaartje|sncb|nmbs)\b"
PASS_WORDS = r"(commuter|season|pass\b|abonnement|trajectticket)"
STOP_WORDS = r"\b(stop|stoppen|stopzetten|arrêter|arreter|arrête|beëindig\w*)\b"


def _cities(text: str) -> list[str]:
    found = []
    for m in re.finditer(r"[\wÀ-ÿ'-]+", text.lower()):
        c = CITY_ALIASES.get(m.group(0))
        if c and c not in found:
            found.append(c)
    return found


def detect_lang(text: str) -> str:
    words = set(re.findall(r"[\w'éèàçû]+", text.lower()))
    en, nl, fr = len(words & EN_WORDS), len(words & NL_WORDS), len(words & FR_WORDS)
    return "nl" if nl > max(en, fr) else "fr" if fr > max(en, nl) else "en"


def _amount(text: str):
    for m in re.finditer(AMOUNT_RE, text):
        raw = m.group(1).replace(" ", "")
        if re.fullmatch(r"\d{4}", raw) and raw.startswith("20") and not m.group(2):
            continue  # looks like a year
        val = raw + ("k" if m.group(2) else "")
        if re.fullmatch(r"\d{1,3}(,\d{3})+", raw):
            val = raw.replace(",", "") + ("k" if m.group(2) else "")
        return val
    return None


def _number_before(text: str, unit_re: str):
    m = re.search(r"(\d+)\s*" + unit_re, text)
    return int(m.group(1)) if m else None


def offline_chat(engine: Engine, uid: int, message: str) -> dict:
    lang = detect_lang(message)
    text = message.lower()
    negated = re.search(NEGATION, text) is not None
    replies, actions = [], []

    def run(tool, **args):
        out, is_error = _tool_result(engine, uid, tool, args)
        actions.append({"tool": tool, "input": args, "ok": not is_error, **({"error": out["error"]} if is_error else {})})
        return out, is_error

    def after_change(out):
        diffs = [T["went"][lang].format(label=LABELS[lang].get(_key(d["moment"]), d["moment"]), a=d["before"], b=d["after"])
                 for d in out.get("probabilities", []) if d["before"] != d["after"]]
        return " ".join(diffs) or T["no_change"][lang]

    def prepare(service, action, **params):
        out, err = run("prepare_service_action", service=service, action=action, params=params)
        if err:
            return out["error"]
        return T["prepared"][lang].format(summary=out["prepared"]["summary"], button=out["prepared"]["button"])

    # 0. Service requests and "I don't need a car".
    cities = _cities(message)
    if re.search(NO_CAR, text):
        out, err = run("declare_life_event", event="buy_car", month="none")
        replies.append(out["error"] if err else T["not_planned"][lang].format(label=LABELS[lang]["buy_car"]) + " " + after_change(out))
        replies.append(T["cambio_offer"][lang] + " " + prepare("cambio", "estimate_vs_owning"))
    elif re.search(PARKING, text) and not re.search(r"\b(parked|geparkeerd|garé)\b", text):
        if re.search(STOP_WORDS, text):
            replies.append(prepare("4411", "stop_parking"))
        else:
            hours = _number_before(text, r"(h\b|hours?|uur|heures?)")
            mins = _number_before(text, r"(min\b|mins|minutes|minuten)")
            params = {"duration_min": hours * 60 if hours else mins or 60}
            if cities:
                params["city"] = cities[0]
            replies.append(prepare("4411", "start_parking", **params))
    elif re.search(TRAIN, text):
        dest = re.search(r"\b(?:to|naar|pour|à|a|vers|richting)\s+([\wÀ-ÿ'-]+)", text)
        destination = (CITY_ALIASES.get(dest.group(1)) if dest else None) or (cities[-1] if cities else None)
        origin = next((c for c in cities if c != destination), None)
        if not destination:
            replies.append(T["where_to"][lang])
        else:
            params = {"destination": destination, **({"origin": origin} if origin else {})}
            if re.search(r"\b(tomorrow|morgen|demain)\b", text):
                params["date"] = "2026-10-02"
            action = "buy_commuter_pass" if re.search(PASS_WORDS, text) else "buy_ticket"
            if action == "buy_commuter_pass":
                params.pop("date", None)
            replies.append(prepare("sncb", action, **params))

    # 1. Declared events (birth first: it can only ever be declared).
    for event, pat in ({} if replies else EVENT_PATTERNS).items():
        if not re.search(pat, text):
            continue
        if event == "buy_car" and re.search(r"\b(bought|gekocht|acheté|achete)\b", text):
            continue  # a past purchase is a fact about the car, handled below
        month = re.search(MONTH_RE, text)
        if negated and event != "birth":
            out, err = run("declare_life_event", event=event, month="none")
            replies.append(out["error"] if err else T["not_planned"][lang].format(label=LABELS[lang][event]) + " " + after_change(out))
        elif month:
            out, err = run("declare_life_event", event=event, month=month.group(0))
            if err:
                replies.append(out["error"])
            else:
                ym = out["change"]["month"]
                replies.append(T["declared"][lang].format(label=LABELS[lang][event], month=_month_name(ym, lang))
                               + " " + after_change(out))
                if event == "move_house" and engine.values(uid).get("renting"):
                    replies.append(T["landlord_offer"][lang] + " " + prepare("registered_email", "send_template"))
        else:
            replies.append(T["which_month"][lang])
        break

    # 2. Corrections of facts.
    if not replies:
        upd = None
        amount = _amount(text)
        if re.search(r"\b(bought|gekocht|acheté|achete)\b", text) and re.search(r"\b(car|auto|voiture)\b", text):
            months = _number_before(text, r"(months?|maanden|mois)") or 1
            upd = [("months_since_car_purchase", months)]
            if re.search(r"\b(new|nieuwe|neuve|nouvelle)\b", text):
                upd.append(("car_age_years", 0))
        elif re.search(r"\b(no|don't have a|geen|pas de|n'ai pas de)\s*(car|auto|voiture)\b", text):
            upd = [("has_car", False)]
        elif re.search(r"\b(car|auto|voiture)\b", text) and _number_before(text, r"(years?|jaar|ans)") is not None:
            upd = [("car_age_years", _number_before(text, r"(years?|jaar|ans)"))]
        elif re.search(r"(lease|huurcontract|contrat de bail|\bbail\b)", text):
            m = _number_before(text, r"(months?|maanden|mois)")
            y = _number_before(text, r"(years?|jaar|ans)")
            upd = [("lease_end_months", m if m is not None else (y * 12 if y is not None else 36))]
        elif re.search(r"(diy|gamma|brico|hubo|doe-het-zelf|bouwmateri|bricolage)", text):
            upd = [("diy_building_spend_3m", 0 if (negated or re.search(r"(parents|ouders|one-off|eenmalig|someone else|iemand anders)", text)) or amount is None else amount)]
        elif re.search(r"(stable|stabiel|vast contract|permanent|\bcdi\b|vaste job|regular)", text):
            upd = [("income_volatility", 0.05)]
        elif amount and re.search(r"(income|salary|earn|\bnet\b|loon|salaris|verdien|inkomen|salaire|revenu|gagne)", text):
            upd = [("net_income_monthly", amount)]
        elif amount and re.search(r"(saving|spaar|épargne|epargne)", text):
            upd = [("savings_balance", amount)]
        elif amount and re.search(r"(invest|belegg|placement)", text):
            upd = [("investments_value", amount)]
        elif _number_before(text, r"(kids|children|child|kinderen|kind|enfants?)") is not None:
            upd = [("n_children", _number_before(text, r"(kids|children|child|kinderen|kind|enfants?)"))]
        elif re.search(r"\b(no|geen|pas d'|pas de)\s*(kids|children|kinderen|enfants)", text):
            upd = [("n_children", 0)]
        elif _number_before(text, r"(people|persons|personen|personnes)") is not None:
            upd = [("household_size", _number_before(text, r"(people|persons|personen|personnes)"))]
        elif re.search(r"\b(we|i|ik|wij|je|nous)\s+(rent|huren|huur|loue|louons)\b", text):
            upd = [("renting", True)]
        elif re.search(r"\b(own|eigenaar|propriétaire|proprietaire)\b", text):
            upd = [("owns_home", not negated)]
        if upd:
            parts, last = [], None
            for f, val in upd:
                out, err = run("update_feature", feature=f, value=val)
                if err:
                    replies.append(out["error"])
                    break
                parts.append(out["change"]["sentence"])
                last = out
            if last:
                replies.insert(0, T["updated"][lang].format(s="; ".join(parts)) + " " + after_change(last))

    # 3. Confirmations.
    if not replies and re.search(r"(that's right|thats right|correct|klopt|juist|c'est exact|exact|c'est vrai|\bright\b|\byes\b|\bja\b|\boui\b)", text):
        cards = engine.state(uid)["cards"]
        target = next((c for c in cards if c["status"] == "inferred"), cards[0] if cards else None)
        if target:
            run("confirm_assumption", feature=target["feature"])
            replies.append(T["confirmed"][lang].format(s=target["sentence"]))

    if not replies:
        replies.append(T["help"][lang])
    return {"reply": " ".join(replies), "actions": actions, "mode": "offline"}


def _key(label: str) -> str:
    return next((m for m, lab in MOMENT_LABELS.items() if lab == label), label)


def _month_name(ym: str, lang: str) -> str:
    names = {"en": ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"],
             "nl": ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"],
             "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]}
    return f"{names[lang][int(ym[5:]) - 1]} {ym[:4]}"


def chat(engine: Engine, uid: int, message: str, history) -> dict:
    """Route to Claude when an API key is available, otherwise (or on API failure) to the offline parser."""
    before = engine._probs(uid)
    before_ids = set(engine.session(uid)["actions"])
    result = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            result = claude_chat(engine, uid, message, history)
        except Exception as e:  # network, auth, rate limit: keep the demo alive
            log.warning("Claude chat failed (%s); using the offline parser", type(e).__name__)
            result = offline_chat(engine, uid, message)
            result["notice"] = "Claude is unreachable, so the offline parser answered."
    else:
        result = offline_chat(engine, uid, message)
    state = engine.state(uid)
    prepared = [a for a in state["actions"] if a["id"] not in before_ids and a["status"] == "prepared"]
    return {**result, "state": state, "prepared": prepared, "diff": engine._diff(before, engine._probs(uid))}


__all__ = ["chat", "parse_month", "CATALOGUE"]
