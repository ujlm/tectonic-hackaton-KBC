"""The customer's session, held by the client (browser) and sent with every request.

It holds corrections, confirmations, declared events, prepared/executed actions, paused topics and plans. The engine
treats it as untrusted input: `load` re-validates everything and drops what doesn't fit, `dump` makes it JSON-safe.
"""
import math
import re

VERSION = 1
MAX_ACTIONS = 60
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def new() -> dict:
    return {"overrides": {}, "implied": {}, "confirmed": [], "declared": {}, "card_order": [], "actions": {},
            "seq": 0, "ignored": {}, "service_updates": {}, "plans": {}, "guardian": {}}


def _num_or_none(x):
    if x is None or isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return None if isinstance(x, float) and (math.isnan(x) or math.isinf(x)) else x
    return x


def load(blob: dict | None, uid: int) -> dict:
    """A clean session from a client blob. A blob for another customer, or garbage, gives a fresh session."""
    from . import assumptions as a  # local import: assumptions imports this module
    from .common import DECLARABLE_EVENTS, MOMENTS, OUT_MONTHS, SERVICE_FEATURES

    s = new()
    if not isinstance(blob, dict) or blob.get("user_id") != uid or blob.get("v") != VERSION:
        return s
    for f, x in (blob.get("overrides") or {}).items():
        if f in a.EDITABLE:
            try:
                s["overrides"][f] = a.validate(f, x)
            except a.ValidationError:
                pass
    for f, x in (blob.get("implied") or {}).items():
        if f in a.CATALOGUE and f != "cohort" and f not in s["overrides"]:
            s["implied"][f] = float("nan") if x is None else x
    s["confirmed"] = [f for f in (blob.get("confirmed") or []) if f in a.CATALOGUE][:60]
    for e, d in (blob.get("declared") or {}).items():
        month = (d or {}).get("month") if isinstance(d, dict) else None
        if e in DECLARABLE_EVENTS and e != "cash_squeeze" and (month is None or month in OUT_MONTHS):
            s["declared"][e] = {"month": month}
    s["card_order"] = [g for g in (blob.get("card_order") or []) if isinstance(g, str) and g in a.CATALOGUE][:60]
    actions = blob.get("actions") or {}
    if isinstance(actions, dict):
        for aid, card in list(actions.items())[-MAX_ACTIONS:]:
            if (isinstance(card, dict) and re.fullmatch(r"A\d{1,4}", str(aid)) and card.get("id") == aid
                    and card.get("status") in ("prepared", "done", "cancelled")):
                s["actions"][aid] = card
    seq = blob.get("seq")
    s["seq"] = max([seq if isinstance(seq, int) else 0] + [int(k[1:]) for k in s["actions"]])
    for m, until in (blob.get("ignored") or {}).items():
        if m in MOMENTS and isinstance(until, str) and _DATE.fullmatch(until):
            s["ignored"][m] = until
    for f, x in (blob.get("service_updates") or {}).items():
        if f in SERVICE_FEATURES and isinstance(x, (int, float, bool)):
            s["service_updates"][f] = x
    plans = blob.get("plans") or {}
    b = plans.get("buffer_monthly") if isinstance(plans, dict) else None
    if isinstance(b, (int, float)) and 10 <= b <= 500:
        s["plans"]["buffer_monthly"] = float(b)
    g = blob.get("guardian")
    if isinstance(g, dict):
        s["guardian"] = g  # validated by the Guardian itself
    return s


def dump(s: dict, uid: int) -> dict:
    """JSON-safe copy (NaN -> null) tagged with the customer id and version."""
    return {
        "v": VERSION, "user_id": uid,
        "overrides": {f: _num_or_none(x) for f, x in s["overrides"].items()},
        "implied": {f: _num_or_none(x) for f, x in s["implied"].items()},
        "confirmed": list(s["confirmed"]), "declared": dict(s["declared"]), "card_order": list(s["card_order"]),
        "actions": s["actions"], "seq": s["seq"], "ignored": dict(s["ignored"]),
        "service_updates": {f: _num_or_none(x) for f, x in s["service_updates"].items()},
        "plans": dict(s["plans"]), "guardian": s.get("guardian", {}),
    }
