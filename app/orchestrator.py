"""Attention budget: every candidate help item for a customer goes through this orchestrator.

Rules
- budget: 1 proactive Kate conversation per month; time-critical items (predicted dip, deadlines) may exceed it
- channel follows urgency: in-app Kate card by default, push notification only for deadlines
- suppression: items built on an assumption the customer rejected disappear; ignored topics pause 60 days
- bundling: all items for the same moment become one Kate conversation
"""
import datetime as dt

from .common import MOMENT_LABELS
from .journeys import STAGE_WEIGHT, build

QUARTER_MONTHS = ["Oct 2026", "Nov 2026", "Dec 2026"]
BUDGET_PER_MONTH = 1
PAUSE_DAYS = 60
TODAY = dt.date(2026, 10, 1)


def pause_until() -> str:
    return (TODAY + dt.timedelta(days=PAUSE_DAYS)).isoformat()


def plan(journeys: list[dict], session: dict, sentences: dict, baseline: list[dict] | None = None) -> dict:
    """journeys: output of journeys.build(); session: the customer's in-memory session;
    sentences: feature -> the original assumption sentence (to explain suppressions);
    baseline: journeys without the customer's corrections (items that vanished because of a correction)."""
    rejected = set(session.get("overrides", {})) | set(session.get("implied", {}))
    ignored = session.get("ignored", {})
    held, conversations = [], []

    current = {it["id"] for j in journeys for it in j["items"]}
    for j in baseline or []:
        for it in j["items"]:
            hit = [f for f in it["depends"] if f in rejected]
            if it["id"] not in current and hit:
                held.append({**it, "reason": "suppressed",
                             "detail": f"built on an assumption you corrected: “{sentences.get(hit[0], hit[0])}”"})

    for j in journeys:
        m = j["moment"]
        for it in j["next_items"]:  # show what is deliberately not offered yet
            if it["kind"] == "product":
                held.append({**it, "reason": "not the right stage yet",
                             "detail": f"{j['label']} is at '{j['stage'] or 'no stage'}'; KBC products only come at '{it['stage']}'"})
        if not j["items"]:
            continue
        live = []
        for it in j["items"]:
            hit = [f for f in it["depends"] if f in rejected]
            if hit:
                held.append({**it, "reason": "suppressed",
                             "detail": f"built on an assumption you corrected: “{sentences.get(hit[0], hit[0])}”"})
            elif m in ignored and ignored[m] >= TODAY.isoformat():
                held.append({**it, "reason": "suppressed", "detail": f"you ignored this topic; paused until {ignored[m]}"})
            else:
                live.append(it)
        if not live:
            continue
        lead, rest = live[0], live[1:]
        for it in rest:
            held.append({**it, "reason": "bundled", "detail": f"part of the '{j['label']}' conversation"})
        deadline = next((it["deadline"] for it in live if it["deadline"]), None)
        critical = deadline or next((it["critical"] for it in live if it["critical"]), None)
        conversations.append({
            "moment": m, "label": j["label"], "stage": j["stage"], "lead": lead, "items": live,
            "priority": j["probability"] * STAGE_WEIGHT.get(j["stage"], 1) + (1 if critical else 0),
            "time_critical": critical, "channel": "push" if deadline else "in-app Kate card",
        })

    conversations.sort(key=lambda c: -c["priority"])
    free = list(QUARTER_MONTHS) * BUDGET_PER_MONTH
    passed = []
    for c in conversations:
        if c["time_critical"]:
            exceeds = not free
            month = free.pop(0) if free else QUARTER_MONTHS[0]
            passed.append({**c, "month": month, "exceeds": exceeds,
                           "why": f"time-critical: {c['time_critical']}" + (" (exceeds the monthly budget)" if exceeds else "")})
    for c in conversations:
        if c["time_critical"]:
            continue
        if free:
            passed.append({**c, "month": free.pop(0), "exceeds": False, "why": "highest priority within the monthly budget"})
        else:
            held.append({**c["lead"], "reason": "budget",
                         "detail": f"only {BUDGET_PER_MONTH} proactive message per month; '{c['label']}' ranks lower"})
    over = sum(p["exceeds"] for p in passed)
    order = {"not the right stage yet": 3, "suppressed": 0, "budget": 1, "bundled": 2}
    held.sort(key=lambda h: (order.get(h["reason"], 9), h["moment"]))
    return {"quarter": "Oct – Dec 2026", "budget": len(QUARTER_MONTHS) * BUDGET_PER_MONTH, "over_budget": over,
            "passed": [_slim(p) for p in sorted(passed, key=lambda p: QUARTER_MONTHS.index(p["month"]))],
            "held": held, "candidates": sum(len(j["items"]) for j in journeys)}


def _slim(c: dict) -> dict:
    return {k: c[k] for k in ("moment", "label", "stage", "lead", "items", "time_critical", "channel", "month", "why", "exceeds")}


def scale_view(rows: list[dict]) -> dict:
    """Proactive messages per customer per year, with and without the orchestrator.
    Simplification: each customer's stages stay as they are today for the whole year.
    Without: every eligible help item is pushed once per quarter (campaign-style).
    With: per quarter, at most 3 conversations (1 per month), bundled per moment, plus time-critical ones."""
    without, with_, pushes, reached = [], [], [], 0
    for r in rows:
        probs, values, profile = r["probs"], r["values"], r["profile"]
        js = build(values, probs, {}, profile, {"plate": "", "new_city": profile["city"], "work_city": profile["city"]})
        n_items = sum(len(j["items"]) for j in js)
        convs = [j for j in js if j["items"]]
        crit = [j for j in convs if any(it["deadline"] or it["critical"] for it in j["items"])]
        dl = [j for j in convs if any(it["deadline"] for it in j["items"])]
        normal = len(convs) - len(crit)
        per_q = len(crit) + min(normal, max(0, 3 - len(crit)))
        without.append(n_items * 4)
        with_.append(per_q * 4)
        pushes.append(len(dl) * 4)
        reached += per_q > 0
    n = max(len(rows), 1)
    mean = lambda xs: sum(xs) / n  # noqa: E731
    p90 = lambda xs: sorted(xs)[int(0.9 * (len(xs) - 1))] if xs else 0  # noqa: E731
    return {"customers": len(rows), "without_mean": round(mean(without), 1), "with_mean": round(mean(with_), 1),
            "without_p90": p90(without), "with_p90": p90(with_), "push_mean": round(mean(pushes), 2),
            "reached_share": round(reached / n, 3), "max_with": max(with_) if with_ else 0,
            "reduction": round(1 - mean(with_) / mean(without), 3) if mean(without) else 0,
            "note": "Assumes each customer's journey stages stay as they are today for the whole year."}
