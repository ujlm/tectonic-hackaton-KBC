"""The contract between the engine and Kate's generated UI.

context(): the compact "context pack" for one turn. Facts have ids and values that are already formatted in the
  customer's language. The model may only quote these; every number in its text must match one of them. The pack
  also lists the ids that component props may reference in this turn.
resolve(): turns the references in a generated spec ("forecast", "peers:buy_car", "assumption:net_income_monthly",
  "service:buffer.start", ...) into data from engine state. A reference that doesn't resolve returns None, and the
  component that carries it is dropped.
whatif(): live numbers for the what-if slider, without changing the session.

Guardian signals never pass through here: this module is personalisation only.
"""
from . import i18n
from .assumptions import EDITABLE, CATALOGUE, fmt_value, validate
from .common import MOMENTS
from .journeys import PRODUCT_FROM, STAGES
from .services.registry import SERVICES

MAX_ASSUMPTIONS = {"simple": 3, "detailed": 5}
PLANS = {"buffer_monthly": dict(min=10, max=300, step=10)}


def _item(it: dict) -> dict:
    a = it.get("action")
    return {"id": it["id"], "kind": it["kind"], "title": it["title"], "say": it["say"],
            "action": f"{a['service']}.{a['action']}" if a else None}


def topic(state: dict, moment: str | None) -> dict | None:
    """The conversation topic for a moment: its stage and the help items that are live (not suppressed)."""
    if not moment or moment not in MOMENTS:
        return None
    j = next(x for x in state["journeys"] if x["moment"] == moment)
    if not j["stage"]:
        return None
    held = {h["id"] for h in state["kate"]["held"] if h["reason"] == "suppressed"}
    items = [it for it in j["items"] if it["id"] not in held]
    if not items:
        return None
    conv = next((c for c in state["kate"]["passed"] if c["moment"] == moment), None)
    return {"moment": moment, "label": j["label_local"], "stage": j["stage"], "stage_label": j["stage_label"],
            "time_critical": bool(conv and conv["time_critical"]),
            "lead": _item(items[0]), "items": [_item(it) for it in items]}


def _pred(state: dict, moment: str) -> dict:
    return next(p for p in state["predictions"] if p["moment"] == moment)


def _topic_cards(state: dict, moment: str, n: int) -> list[dict]:
    cards = [c for c in state["cards"] if c["feature"] != "cohort"]
    scored = [(abs(next((e["pts"] for e in c["effects"] if e["moment"] == moment), 0.0)), c) for c in cards]
    return [c for pts, c in sorted(scored, key=lambda x: -x[0]) if pts >= 1.0][:n]


def context(engine, uid: int, lang: str, depth: str = "simple", purpose: str = "opener", moment: str | None = None,
            event: dict | None = None) -> dict:
    lang = i18n.norm(lang)
    depth = "detailed" if depth == "detailed" else "simple"
    state = engine.state(uid, lang)
    if purpose == "opener" and moment is None:
        moment = (state["opener"] or {}).get("moment")
    t = topic(state, moment)
    facts = [("customer.first_name", state["profile"]["first_name"])]
    allowed = {"assumptions": [], "services": [], "products": [], "plans": [], "forecast": False, "peers": []}
    if t:
        p = _pred(state, t["moment"])
        facts += [("topic.label", t["label"]), ("topic.stage", t["stage_label"]),
                  ("topic.title", t["lead"]["title"]), ("topic.say", t["lead"]["say"]),
                  ("topic.chance", i18n.natural_frequency(p["probability"], lang))]
        if p.get("neighbour_rate") is not None:
            facts.append(("peers.chance", i18n.natural_frequency(p["neighbour_rate"], lang)))
            allowed["peers"].append(t["moment"])
        if depth == "detailed":
            facts.append(("topic.chance_pct", i18n.pct(p["probability"], lang)))
            if p.get("neighbour_rate") is not None:
                facts.append(("peers.chance_pct", i18n.pct(p["neighbour_rate"], lang)))
        for it in t["items"][1:4]:
            facts.append((f"item.{it['id']}.say", it["say"]))
        for c in _topic_cards(state, t["moment"], MAX_ASSUMPTIONS[depth]):
            facts.append((f"assumption.{c['feature']}", c["sentence"]))
            allowed["assumptions"].append(c["feature"])
        allowed["services"] = [it["action"] for it in t["items"] if it["kind"] == "service" and it["action"]]
        stages = STAGES[t["moment"]]
        if stages.index(t["stage"]) >= stages.index(PRODUCT_FROM[t["moment"]]):
            allowed["products"] = [it["id"] for it in t["items"] if it["kind"] == "product"]
        if t["moment"] == "cash_squeeze":
            f = state["forecast"]
            facts += [("forecast.tightest_month", f["tightest_month"]),
                      ("forecast.tightest_amount", i18n.eur(f["tightest_amount"], lang)),
                      ("buffer.suggested", i18n.eur(f["suggested_buffer"], lang))]
            allowed["forecast"] = True
            allowed["plans"].append("buffer_monthly")
            if state["plans"].get("buffer_monthly"):
                facts.append(("buffer.active", i18n.eur(state["plans"]["buffer_monthly"], lang)))
    if event:
        facts += _event_facts(event, lang, depth)
    return {
        "user_id": uid, "lang": lang, "depth": depth, "purpose": purpose,
        "region": state["profile"]["region"], "topic": t,
        "facts": [{"id": i, "text": str(x)} for i, x in facts],
        "allowed": allowed,
    }


def _event_facts(event: dict, lang: str, depth: str) -> list[tuple[str, str]]:
    """Facts about what just happened (a correction, a confirmed action) so Kate can explain it in one sentence."""
    out = []
    names = i18n.ui.MOMENTS[lang]
    for d in event.get("diff") or []:
        if d.get("before") is None or d.get("after") is None or d["moment"] not in names:
            continue
        m = d["moment"]
        out += [(f"change.{m}.label", names[m]),
                (f"change.{m}.before", i18n.natural_frequency(d["before"], lang)),
                (f"change.{m}.after", i18n.natural_frequency(d["after"], lang))]
        if depth == "detailed":
            out += [(f"change.{m}.before_pct", i18n.pct(d["before"], lang)),
                    (f"change.{m}.after_pct", i18n.pct(d["after"], lang))]
    change = event.get("change") or {}
    if change.get("sentence"):
        out.append(("change.sentence", change["sentence"]))
    card = event.get("card")
    if card:
        out.append(("action.summary", card.get("summary", "")))
        if card.get("status") == "done" and card.get("result", {}).get("title"):
            out.append(("action.result", card["result"]["title"]))
    return out


# ------------------------------------------------------------------------------------------------
# Reference resolution
# ------------------------------------------------------------------------------------------------
def resolve(engine, uid: int, lang: str, refs: list[str], allowed: dict | None = None) -> dict:
    """ref -> data (or None). `allowed` (from the context pack) limits what may resolve in this turn."""
    lang = i18n.norm(lang)
    state = engine.state(uid, lang)
    out = {}
    for ref in dict.fromkeys(refs):
        try:
            out[ref] = _resolve_one(engine, uid, lang, state, str(ref), allowed)
        except (KeyError, ValueError, StopIteration):
            out[ref] = None
    return out


def _ok(allowed, key, value) -> bool:
    return allowed is None or value in allowed.get(key, [])


def _resolve_one(engine, uid, lang, state, ref, allowed):
    kind, _, arg = ref.partition(":")
    if kind == "forecast":
        if allowed is not None and not allowed.get("forecast"):
            return None
        return state["forecast"]
    if kind == "peers" and arg in MOMENTS and _ok(allowed, "peers", arg):
        p = _pred(state, arg)
        if p.get("neighbour_rate") is None:
            return None
        return {"moment": arg, "label": p["label_local"],
                "you": i18n.natural_frequency(p["probability"], lang), "peers": i18n.natural_frequency(p["neighbour_rate"], lang),
                "you_pct": i18n.pct(p["probability"], lang), "peers_pct": i18n.pct(p["neighbour_rate"], lang),
                "you_p": p["probability"], "peers_p": p["neighbour_rate"]}
    if kind == "assumption" and arg in CATALOGUE and arg != "cohort" and _ok(allowed, "assumptions", arg):
        card = next((c for c in state["cards"] if c["feature"] == arg), None)
        return card or engine.card(uid, arg, lang)
    if kind == "service":
        service, _, action = arg.partition(".")
        if service not in SERVICES or SERVICES[service].action(action) is None or not _ok(allowed, "services", arg):
            return None
        existing = next((a for a in state["actions"] if a["service"] == service and a["action"] == action
                         and a["status"] == "prepared"), None)
        return existing or engine.prepare_action(uid, service, action, {}, lang)["card"]
    if kind == "product" and _ok(allowed, "products", arg):
        for j in state["journeys"]:
            it = next((x for x in j["items"] if x["id"] == arg and x["kind"] == "product"), None)
            if it:
                stages = STAGES[j["moment"]]
                if stages.index(j["stage"]) < stages.index(PRODUCT_FROM[j["moment"]]):
                    return None  # never before the stage where products are allowed
                return {"id": it["id"], "moment": j["moment"], "title": it["title"], "say": it["say"],
                        "kind_label": it["kind_label"]}
        return None
    if kind == "plan" and arg in PLANS and _ok(allowed, "plans", arg):
        active = state["plans"].get(arg)
        return {"id": arg, **PLANS[arg], "value": active or state["forecast"]["suggested_buffer"], "active": bool(active),
                "unit": "€", "display": i18n.eur(active or state["forecast"]["suggested_buffer"], lang)}
    if kind == "feature" and arg in EDITABLE and _ok(allowed, "assumptions", arg):
        c = CATALOGUE[arg]
        if c["type"] not in ("amount", "ratio", "count", "months", "years"):
            return None
        value = engine.values(uid).get(arg)
        lo, hi = c.get("min", 0), c.get("max", 100)
        if c["type"] == "amount":  # a sensible window around today's value, not the full validation range
            base = abs(value or 0)
            lo, hi = max(lo, 0), min(hi, max(1000, round(base * 2.5, -2)))
        step = 0.01 if c["type"] == "ratio" else 1 if c["type"] != "amount" else max(10, round((hi - lo) / 100, -1))
        return {"feature": arg, "min": lo, "max": hi, "step": step, "value": value,
                "display": fmt_value(arg, value, lang), "type": c["type"]}
    if kind == "why" and arg in MOMENTS:
        p = _pred(state, arg)
        cards = _topic_cards(state, arg, 5)
        return {"moment": arg, "label": p["label_local"], "chance": i18n.natural_frequency(p["probability"], lang),
                "chance_pct": i18n.pct(p["probability"], lang),
                "reasons": [{"feature": c["feature"], "sentence": c["sentence"],
                             "pts": next((e["pts"] for e in c["effects"] if e["moment"] == arg), 0.0),
                             "source": c["source"], "editable": c["editable"]} for c in cards]}
    return None


# ------------------------------------------------------------------------------------------------
# What-if (slider): numbers only, the session is left untouched
# ------------------------------------------------------------------------------------------------
def whatif(engine, uid: int, lang: str, kind: str, ident: str, value) -> dict:
    lang = i18n.norm(lang)
    if kind == "plan" and ident in PLANS:
        amount = float(min(max(float(value), PLANS[ident]["min"]), PLANS[ident]["max"]))
        f = engine.forecast(uid, lang, buffer_monthly=amount)
        return {"kind": kind, "id": ident, "value": amount, "display": i18n.eur(amount, lang), "forecast": f}
    if kind == "feature" and ident in EDITABLE:
        clean = validate(ident, value)
        s = engine.session(uid)
        before = engine._probs(uid)
        saved = dict(s["overrides"])
        s["overrides"][ident] = clean
        try:
            after = engine._probs(uid)
        finally:
            s["overrides"].clear()
            s["overrides"].update(saved)
        diff = engine._diff(before, after, lang)
        return {"kind": kind, "id": ident, "value": clean, "display": fmt_value(ident, clean, lang),
                "diff": [{**d, "before_words": i18n.natural_frequency(d["before"], lang) if d["before"] is not None else None,
                          "after_words": i18n.natural_frequency(d["after"], lang) if d["after"] is not None else None}
                         for d in diff]}
    raise ValueError(f"Unknown what-if {kind}:{ident}")
