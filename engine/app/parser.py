"""Kate's offline fallback: a small rule-based parser for NL / FR / EN free text.

Used when the LLM is switched off (CHAT_ENABLED=false, the /demo toggle) or unreachable. It understands corrections,
plans, confirmations and a few service requests, runs them on the engine, and answers in the customer's language.
It never executes a service action: it only prepares a confirmation card.
"""
import re

from . import i18n
from .assumptions import Engine, ValidationError
from .common import CITY_NAMES

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


def detect_lang(text: str, default: str = "en") -> str:
    words = set(re.findall(r"[\w'éèàçû]+", text.lower()))
    en, nl, fr = len(words & EN_WORDS), len(words & NL_WORDS), len(words & FR_WORDS)
    if not (en or nl or fr):
        return i18n.norm(default)
    return "nl" if nl > max(en, fr) else "fr" if fr > max(en, nl) else "en"


def _cities(text: str) -> list[str]:
    found = []
    for m in re.finditer(r"[\wÀ-ÿ'-]+", text.lower()):
        c = CITY_ALIASES.get(m.group(0))
        if c and c not in found:
            found.append(c)
    return found


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


def _month_name(ym: str, lang: str) -> str:
    return i18n.month_label(ym, lang, long=True)


def reply(engine: Engine, uid: int, message: str, lang: str = "en") -> dict:
    """Parse one message, run what it asks on the engine (inside the caller's session), and answer.

    Returns {reply, lang, actions: [{tool, input, ok, error?}], diff: [...], prepared: [card ids]}."""
    lang = detect_lang(message, lang)
    labels = i18n.ui.MOMENTS[lang]
    text = message.lower()
    negated = re.search(NEGATION, text) is not None
    replies, actions, diff, prepared = [], [], [], []

    def run(tool, fn, **args):
        try:
            out = fn()
        except ValidationError as e:
            actions.append({"tool": tool, "input": args, "ok": False, "error": str(e)})
            return None, str(e)
        actions.append({"tool": tool, "input": args, "ok": True})
        diff.extend(out.get("diff", []))
        return out, None

    def after_change(out):
        parts = [T["went"][lang].format(label=labels.get(d["moment"], d["moment"]), a=i18n.pct(d["before"], lang),
                                        b=i18n.pct(d["after"], lang))
                 for d in out.get("diff", []) if d["before"] is not None and d["after"] is not None
                 and round(d["before"] * 100) != round(d["after"] * 100)]
        return " ".join(parts) or T["no_change"][lang]

    def declare(event, month):
        return run("declare_life_event", lambda: engine.declare(uid, event, month, lang), event=event, month=month)

    def prepare(service, action, **params):
        out, err = run("prepare_service_action", lambda: engine.prepare_action(uid, service, action, params, lang),
                       service=service, action=action, params=params)
        if err:
            return err
        prepared.append(out["card"]["id"])
        return T["prepared"][lang].format(summary=out["card"]["summary"], button=out["card"]["button"])

    # 0. Service requests and "I don't need a car".
    cities = _cities(message)
    if re.search(NO_CAR, text):
        out, err = declare("buy_car", "none")
        replies.append(err or T["not_planned"][lang].format(label=labels["buy_car"]) + " " + after_change(out))
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
            out, err = declare(event, "none")
            replies.append(err or T["not_planned"][lang].format(label=labels[event]) + " " + after_change(out))
        elif month:
            out, err = declare(event, month.group(0))
            if err:
                replies.append(err)
            else:
                replies.append(T["declared"][lang].format(label=labels[event], month=_month_name(out["change"]["month"], lang))
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
                out, err = run("update_feature", lambda f=f, val=val: engine.override(uid, f, val, lang), feature=f, value=val)
                if err:
                    replies.append(err)
                    break
                parts.append(out["change"]["sentence"])
                last = out
            if last:
                replies.insert(0, T["updated"][lang].format(s="; ".join(parts)) + " " + after_change(last))

    # 3. Confirmations.
    if not replies and re.search(r"(that's right|thats right|correct|klopt|juist|c'est exact|exact|c'est vrai|\bright\b|\byes\b|\bja\b|\boui\b)", text):
        cards = engine.state(uid, lang)["cards"]
        target = next((c for c in cards if c["status"] == "inferred"), cards[0] if cards else None)
        if target:
            run("confirm_assumption", lambda: engine.confirm(uid, target["feature"]), feature=target["feature"])
            replies.append(T["confirmed"][lang].format(s=target["sentence"]))

    if not replies:
        replies.append(T["help"][lang])
    return {"reply": " ".join(replies), "lang": lang, "actions": actions, "diff": diff, "prepared": prepared,
            "mode": "offline"}
