"""Mock backend for the simulated KBC Mobile service integrations.

prepare() validates parameters and builds a confirmation card (nothing is executed).
execute() runs a prepared card after the customer's tap and returns a realistic confirmation object.
Everything is deterministic per customer, nothing leaves the process, and all customer-facing text comes in the
card's language (en / nl / fr).
"""
import datetime as dt
import hashlib
import math
import re

import numpy as np

from .. import i18n
from ..i18n.services import ACTIONS, BUTTONS, RESULTS, TEMPLATES
from .registry import SERVICES, TODAY, Action, needs_confirmation

BIG_CITIES = {"Antwerpen", "Gent", "Brussels", "Ixelles", "Schaerbeek", "Etterbeek", "Uccle", "Anderlecht", "Liège", "Leuven"}
MOBIT_CITIES = {"Gent", "Brussels", "Ixelles", "Schaerbeek", "Etterbeek", "Uccle", "Anderlecht", "Liège", "Leuven", "Mechelen"}
CLIENTS = ["Studio Verhaegen", "Atelier Lambert", "Bakkerij De Smet", "Maison Dubois", "Garage Claes", "Brasserie Peeters",
           "Immo Wouters", "Cabinet Lejeune", "Drukkerij Maes", "Fleuriste Martin"]


class ActionError(ValueError):
    pass


def _h(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)


def _ref(prefix: str, *parts) -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    h = _h(prefix, *parts)
    return prefix + "-" + "".join(alphabet[(h >> (5 * i)) % 32] for i in range(6))


def plate_for(uid: int) -> str:
    h = _h("plate", uid)
    letters = "".join("ABCDEFGHJKLMNPRSTVWXYZ"[(h >> (5 * i)) % 22] for i in range(3))
    return f"{1 + h % 2}-{letters}-{h % 1000:03d}"


def _now() -> str:
    return f"{TODAY} {dt.datetime.now():%H:%M}"


def _month_after(months: float) -> str:
    idx = 2026 * 12 + 9 + int(round(months))
    return f"{idx // 12}-{idx % 12 + 1:02d}-01"


def _eur(v: float, lang: str = "en") -> str:
    return i18n.eur(v, lang, decimals=2 if abs(v) < 100 and v != int(v) else 0)


def _date(iso: str, lang: str) -> str:
    """2026-10-02 -> 2 Oct 2026 / 2 okt 2026 / 2 oct. 2026."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(iso)):
        return str(iso)
    y, m, d = iso.split("-")
    return f"{int(d)} {i18n.month_label(f'{y}-{m}', lang)}"


def _r(lang: str, key: str, **kw):
    s = RESULTS[lang].get(key, RESULTS["en"][key])
    return s.format(**kw) if kw and isinstance(s, str) else s


def invoices_for(uid: int, n, total) -> list[dict]:
    """Deterministic overdue Billit invoices matching the customer's overdue count and amount."""
    if n is None or (isinstance(n, float) and math.isnan(n)) or n < 1:
        return []
    n = int(n)
    rng = np.random.default_rng(_h("inv", uid) % (2**32))
    shares = rng.dirichlet(np.ones(n) * 2) * float(total or 0)
    out = []
    for i, amt in enumerate(sorted(shares, reverse=True)):
        days = int(rng.integers(12, 96))
        due = dt.date(2026, 10, 1) - dt.timedelta(days=days)
        out.append({"number": f"INV-2026-{int(rng.integers(100, 999))}", "client": CLIENTS[int(rng.integers(len(CLIENTS)))],
                    "amount": round(float(amt), 2), "due": due.isoformat(), "days_overdue": days})
    return out


def context(uid: int, profile: dict, values: dict, session: dict) -> dict:
    """Customer facts used to fill action defaults."""
    city = profile["city"]
    changed = bool(values.get("parking_city_changed_90d"))
    new_city = values.get("parking_city_recent") if changed else None
    invoices = invoices_for(uid, values.get("billit_overdue_invoices"), values.get("billit_overdue_amount"))
    running = [a for a in session.get("actions", {}).values()
               if a["status"] == "done" and a["result"].get("kind") == "parking_session" and not a["result"].get("stopped")]
    lease = values.get("lease_end_months")
    declared_move = (session.get("declared", {}).get("move_house") or {}).get("month")
    return {
        "uid": uid, "first_name": profile["first_name"], "city": city, "region": profile["region"],
        "new_city": new_city or city, "work_city": city, "plate": plate_for(uid),
        "bike_provider": "Velo Antwerpen" if city == "Antwerpen" else "Mobit" if city in MOBIT_CITIES else "Blue-bike",
        "km_per_year": 12000 if values.get("has_car") else 6000,
        # Move-out: the month the customer told us, else the lease end if it's near, else the standard 3-month notice.
        "lease_end_date": f"{declared_move}-01" if declared_move else (
            _month_after(lease) if lease is not None and not (isinstance(lease, float) and math.isnan(lease)) and lease <= 15
            else _month_after(3)),
        "last_parking": running[-1]["result"]["session_id"] if running else None,
        "invoices": invoices,
        "largest_overdue": invoices[0]["number"] if invoices else None,
        "largest_overdue_amount": invoices[0]["amount"] if invoices else None,
        "suggested_buffer": 50,
    }


# ------------------------------------------------------------------------------------------------
# Validation and pricing
# ------------------------------------------------------------------------------------------------
def _coerce(p, value):
    t = p.type
    if t == "int":
        try:
            v = int(round(float(value)))
        except (TypeError, ValueError):
            raise ActionError(f"'{p.label or p.name}' needs a whole number.") from None
    elif t == "number":
        try:
            v = round(float(str(value).replace("€", "").replace(",", ".").strip()), 2)
        except (TypeError, ValueError):
            raise ActionError(f"'{p.label or p.name}' needs an amount.") from None
    elif t == "enum":
        opts = {str(o).lower(): o for o in p.options}
        v = opts.get(str(value).strip().lower())
        if v is None:
            raise ActionError(f"'{p.label or p.name}' must be one of: {', '.join(map(str, p.options))}.")
        return v
    elif t == "date":
        v = str(value).strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) or not ("2026-10-01" <= v <= "2027-12-31"):
            raise ActionError(f"'{p.label or p.name}' must be a date between 2026-10-01 and 2027-12-31 (YYYY-MM-DD).")
        return v
    elif t == "plate":
        v = str(value).strip().upper().replace(" ", "-")
        if not re.fullmatch(r"\d-[A-Z]{3}-\d{3}", v):
            raise ActionError("Number plates look like 1-ABC-123.")
        return v
    else:
        v = str(value).strip()[:80]
        if p.required and not v:
            raise ActionError(f"'{p.label or p.name}' can't be empty.")
        return v
    if (p.min is not None and v < p.min) or (p.max is not None and v > p.max):
        raise ActionError(f"'{p.label or p.name}' must be between {p.min:g} and {p.max:g}.")
    return v


def resolve(action: Action, params: dict, ctx: dict) -> dict:
    params = params or {}
    unknown = set(params) - {p.name for p in action.params}
    if unknown:
        raise ActionError(f"Unknown parameter(s): {', '.join(sorted(unknown))}.")
    out = {}
    for p in action.params:
        value = params.get(p.name)
        if isinstance(value, str) and value.startswith("@"):  # context reference from a help item
            value = ctx.get(value[1:])
        if value is None or value == "":
            d = p.default
            value = ctx.get(d[1:]) if isinstance(d, str) and d.startswith("@") else d
        if value is None or value == "":
            if p.required:
                raise ActionError(f"Missing '{p.label or p.name}'.")
            out[p.name] = ""
            continue
        out[p.name] = _coerce(p, value)
    return out


def _train_fare(a: str, b: str) -> float:
    if a == b:
        return 2.60
    h = _h(*sorted([a.lower(), b.lower()]))
    return round(2.60 + (h % 30) * 0.45, 2)


def price(service: str, action: str, v: dict, ctx: dict, lang: str = "en") -> tuple[float | None, str]:
    e = lambda x: _eur(x, lang)  # noqa: E731
    if service == "4411" and action == "start_parking":
        rate = 2.40 if v["city"] in BIG_CITIES else 1.80
        total = round(rate * v["duration_min"] / 60, 2)
        return total, _r(lang, "price.per_hour", total=e(total), rate=e(rate))
    if service == "sncb":
        fare = _train_fare(v["origin"], v["destination"])
        if action == "buy_ticket":
            p = fare * (1.5 if v["travel_class"] == "1st" else 1)
        elif action == "buy_multi":
            p = fare * 10 * 0.85
        else:
            p = fare * 13 * {1: 1, 3: 2.8, 12: 10}[int(v["months"])]
        return round(p, 2), e(round(p, 2))
    fixed = {("delijn", "single"): 2.50, ("delijn", "day pass"): 7.50, ("stib", "single"): 2.60, ("stib", "24h"): 8.40}
    if service in ("delijn", "stib"):
        p = fixed[(service, v["ticket_type"])]
        return p, e(p)
    if service == "shared_bike":
        p = {"Mobit": 10.00, "Blue-bike": 3.65, "Velo Antwerpen": 5.00}[v["provider"]]
        return p, e(p)
    if service == "cambio" and action == "book_car":
        p = round(v["hours"] * 2.80 + v["hours"] * 12 * 0.29, 2)
        return p, _r(lang, "price.cambio", total=e(p), rate=e(2.80), km=e(0.29))
    if service == "driving_licence":
        p = 58.0 * v["hours"]
        return p, e(p)
    if service == "brussels_airport":
        p = 12.0 if action == "book_fast_lane" else 39.0
        return p, e(p)
    if service == "service_vouchers":
        p = 10.0 * v["count"]
        return p, e(p)
    if service == "registered_email":
        return 4.95, e(4.95)
    if service == "gosolid":
        return None, _r(lang, "price.gosolid")
    if service in ("q8", "qpark"):
        return None, _r(lang, "price.link")
    if service == "buffer":
        return None, _r(lang, "price.free")
    return None, ""


# ------------------------------------------------------------------------------------------------
# Cards and execution
# ------------------------------------------------------------------------------------------------
def prepare(service_id: str, action_id: str, params: dict, ctx: dict, seq: int, lang: str = "en") -> dict:
    lang = i18n.norm(lang)
    svc = SERVICES.get(service_id)
    if svc is None:
        raise ActionError(f"Unknown service '{service_id}'. Services: {', '.join(SERVICES)}.")
    a = svc.action(action_id)
    if a is None:
        raise ActionError(f"'{svc.name}' has no action '{action_id}'. Actions: {', '.join(x.id for x in svc.actions)}.")
    if service_id == "4411" and action_id == "stop_parking" and not (params or {}).get("session_id") and not ctx.get("last_parking"):
        raise ActionError("There is no running parking session to stop.")
    v = resolve(a, params, ctx)
    city = lambda c: i18n.journeys.city(c, lang)  # noqa: E731
    fmt = {**v, "duration": _r(lang, "duration", n=v.get("duration_min", 0)),
           "template_label": TEMPLATES[lang].get(v.get("template"), v.get("template")),
           "note_suffix": f" ('{v['note']}')" if v.get("note") else ""}
    for k in ("city", "origin", "destination"):
        if v.get(k):
            fmt[k] = city(v[k])
    for k in ("date", "move_out"):
        if v.get(k):
            fmt[k] = _date(v[k], lang)
    if v.get("travel_class"):
        fmt["travel_class"] = _r(lang, f"class.{v['travel_class']}")
    if isinstance(v.get("amount"), (int, float)):
        fmt["amount"] = _eur(v["amount"], lang)
    if v.get("recipient") == "Your landlord":
        fmt["recipient"] = {"en": "your landlord", "nl": "je verhuurder", "fr": "votre propriétaire"}[lang]
    if isinstance(v.get("km_per_year"), int):
        fmt["km_per_year"] = i18n.number(v["km_per_year"], lang)
    name, confirm, button = ACTIONS[lang].get(f"{service_id}.{action_id}", (a.name, a.confirm, a.button or None))
    amount, price_text = price(service_id, action_id, v, ctx, lang)
    label = (button or BUTTONS[lang]["send" if a.sends else "confirm"]).format(**fmt)
    if a.costs_money and amount:
        label = f"{button or BUTTONS[lang]['pay']} · {_eur(amount, lang)}"
    return {
        "id": f"A{seq}", "service": svc.id, "service_name": svc.name, "action": a.id, "action_name": name,
        "params": v, "summary": confirm.format(**fmt), "price": amount, "price_text": price_text,
        "costs_money": a.costs_money, "sends": a.sends, "needs_confirmation": needs_confirmation(a),
        "button": label, "color": svc.color, "text": svc.text, "status": "prepared", "simulated": True, "result": {},
        "lang": lang,
    }


def qr_svg(seed: str, n: int = 25, px: int = 4) -> str:
    """A QR-looking placeholder (not a real QR code)."""
    h = hashlib.sha256(seed.encode()).digest() * 12
    bits = [(h[i // 8] >> (i % 8)) & 1 for i in range(n * n)]
    rects = []
    for y in range(n):
        for x in range(n):
            finder = next(((fx, fy) for fx, fy in ((0, 0), (n - 7, 0), (0, n - 7)) if fx <= x < fx + 7 and fy <= y < fy + 7), None)
            if finder:
                dx, dy = x - finder[0], y - finder[1]
                on = dx in (0, 6) or dy in (0, 6) or (2 <= dx <= 4 and 2 <= dy <= 4)
            else:
                on = bits[y * n + x]
            if on:
                rects.append(f'<rect x="{x * px}" y="{y * px}" width="{px}" height="{px}"/>')
    size = n * px
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-4 -4 {size + 8} {size + 8}" width="{size + 8}" height="{size + 8}" '
            f'role="img" aria-label="QR code placeholder"><rect x="-4" y="-4" width="{size + 8}" height="{size + 8}" fill="#fff"/>'
            f'<g fill="#111">{"".join(rects)}</g></svg>')


def for_display(card: dict) -> dict:
    """The card as the app shows it: tickets get their QR placeholder (not stored in the session)."""
    if card.get("result", {}).get("kind") == "ticket":
        return {**card, "result": {**card["result"], "qr_svg": qr_svg(card["result"]["reference"])}}
    return card


def execute(card: dict, ctx: dict) -> dict:
    s, a, v = card["service"], card["action"], card["params"]
    lang = i18n.norm(card.get("lang"))
    e = lambda x: _eur(x, lang)  # noqa: E731
    city = lambda c: i18n.journeys.city(c, lang)  # noqa: E731
    ref = _ref({"4411": "P", "sncb": "SNCB", "delijn": "DL", "stib": "STIB", "cambio": "CMB", "registered_email": "RE",
                "gosolid": "GS", "brussels_airport": "BRU", "driving_licence": "DRV", "buffer": "BUF"}.get(s, s[:3].upper()),
               ctx["uid"], card["id"])
    base = {"reference": ref, "service_name": card["service_name"], "created_at": _now(), "simulated": True}
    today = _date(TODAY, lang)
    if s == "4411" and a == "start_parking":
        start = dt.datetime.now().replace(second=0, microsecond=0)
        end = start + dt.timedelta(minutes=v["duration_min"])
        zone = _r(lang, "zone.paid" if v["city"] in BIG_CITIES else "zone.blue")
        end_day = _date((dt.date.fromisoformat(TODAY) + (end.date() - start.date())).isoformat(), lang)
        return {**base, "kind": "parking_session", "session_id": ref, "city": city(v["city"]), "zone": zone,
                "plate": v["plate"], "starts": f"{today} {start:%H:%M}", "ends": f"{end_day} {end:%H:%M}",
                "estimate": card["price_text"], "title": _r(lang, "parking.title", city=city(v["city"]), end=f"{end:%H:%M}")}
    if s == "4411" and a == "stop_parking":
        return {**base, "kind": "parking_stopped", "session_id": v["session_id"], "stopped_at": _now(),
                "title": _r(lang, "parking.stopped", id=v["session_id"])}
    if s in ("sncb", "delijn", "stib"):
        if s == "sncb":
            o, d = city(v["origin"]), city(v["destination"])
            if a == "buy_ticket":
                what = _r(lang, "ticket.single", origin=o, destination=d, travel_class=_r(lang, f"class.{v['travel_class']}"))
                valid = _date(v["date"], lang)
            elif a == "buy_multi":
                what, valid = _r(lang, "ticket.multi", origin=o, destination=d), _r(lang, "valid.year", date=today)
            else:
                what = _r(lang, "ticket.pass", origin=o, destination=d, months=v["months"])
                valid = _r(lang, "valid.from", date=today)
        else:
            what = _r(lang, "ticket.local", service=card["service_name"], ticket_type=v["ticket_type"])
            valid = _r(lang, "valid.activation", date=today)
        return {**base, "kind": "ticket", "what": what, "valid": valid, "price": card["price_text"], "title": what}
    if s in ("qpark", "q8"):
        return {**base, "kind": "link", "plate": v["plate"], "status": _r(lang, "status.active"),
                "title": _r(lang, "link.title", plate=v["plate"], service=card["service_name"])}
    if s in ("cambio", "shared_bike", "driving_licence", "brussels_airport") and a != "estimate_vs_owning":
        what = {"book_car": lambda: _r(lang, "booking.cambio", city=city(v.get("city")), date=_date(v.get("date"), lang), hours=v.get("hours")),
                "rent_day_bike": lambda: _r(lang, "booking.bike", provider=v.get("provider"), city=city(v.get("city"))),
                "book_lesson": lambda: _r(lang, "booking.lesson", date=_date(v.get("date"), lang), hours=v.get("hours")),
                "book_fast_lane": lambda: _r(lang, "booking.fast_lane", date=_date(v.get("date"), lang)),
                "book_lounge": lambda: _r(lang, "booking.lounge", date=_date(v.get("date"), lang))}[a]()
        extra = {"unlock_code": f"{_h('bike', ref) % 10000:04d}"} if s == "shared_bike" else {}
        return {**base, "kind": "booking", "what": what, "price": card["price_text"], "title": what, **extra}
    if s == "cambio" and a == "estimate_vs_owning":
        km = v["km_per_year"]
        owning = 230 + 75 + 35 + 55 + km * 0.075 / 12 + 25  # depreciation, insurance, tax, maintenance, fuel, parking
        cambio = 9 + (km / 12) * 0.29 + (km / 12 / 22) * 2.80
        # monthly: owning = 420 + 0.075 * km/12 ; cambio = 9 + (0.29 + 2.80/22) * km/12  ->  equal at km:
        breakeven = int(round((420 - 9) * 12 / (0.29 + 2.80 / 22 - 0.075) / 1000) * 1000)
        cambio_wins = cambio < owning
        cheaper = _r(lang, "compare.cambio" if cambio_wins else "compare.owning")
        rec = _r(lang, "compare.cambio_wins" if cambio_wins else "compare.owning_wins", km=i18n.number(km, lang),
                 cambio=e(round(cambio)), owning=e(round(owning)), breakeven=i18n.number(breakeven, lang))
        return {**base, "kind": "comparison", "owning_monthly": round(owning), "cambio_monthly": round(cambio),
                "breakeven_km": breakeven, "cheaper": cheaper, "recommendation": rec,
                "title": _r(lang, "compare.title", cheaper=cheaper)}
    if s == "movesmart":
        return {**base, "kind": "lease_status", "car": _r(lang, "lease.car"), "contract_end": "2028-03-31",
                "km": _r(lang, "lease.km"), "title": _r(lang, "lease.title")}
    if s == "service_vouchers":
        return {**base, "kind": "order", "what": _r(lang, "vouchers.what", count=v["count"]), "price": card["price_text"],
                "title": _r(lang, "vouchers.title", count=v["count"])}
    if s == "split_expenses" and a == "create_group":
        return {**base, "kind": "group", "what": _r(lang, "group.what", name=v["name"], members=v["members"]),
                "title": _r(lang, "group.title", name=v["name"])}
    if a in ("request_repayment", "request_money"):
        to = v.get("contact") or _r(lang, "request.members", group=v.get("group"))
        return {**base, "kind": "payment_request", "what": _r(lang, "request.what", amount=e(v["amount"]), to=to),
                "status": _r(lang, "request.status"), "title": _r(lang, "request.title", to=to)}
    if s == "myhome" and a == "estimate_value":
        base_value = {"Flanders": 335_000, "Wallonia": 245_000, "Brussels": 430_000}[ctx["region"]]
        val = round(base_value * (0.7 + (_h("home", ctx["uid"]) % 700) / 1000) / 1000) * 1000
        return {**base, "kind": "estimate", "value": val, "low": round(val * 0.93, -3), "high": round(val * 1.07, -3),
                "title": _r(lang, "estimate.title", value=e(val))}
    if s == "myhome" and a == "renovation_checklist":
        premium = i18n.journeys.PREMIUM[lang][ctx["region"]]
        return {**base, "kind": "checklist", "items": _r(lang, "checklist.items"), "premium": premium,
                "title": _r(lang, "checklist.title", premium=premium)}
    if s == "registered_email":
        subject = TEMPLATES[lang][v["template"]]
        recipient = {"en": "Your landlord", "nl": "Je verhuurder", "fr": "Votre propriétaire"}[lang] \
            if v["recipient"] == "Your landlord" else v["recipient"]
        return {**base, "kind": "registered_email", "recipient": recipient, "subject": subject,
                "status": _r(lang, "email.status"), "sent_at": _now(), "legally_valid": True,
                "preview": _r(lang, "email.preview", move_out=_date(v["move_out"], lang), name=ctx["first_name"]),
                "title": _r(lang, "email.title", subject=subject)}
    if s == "billit" and a == "list_overdue":
        inv = ctx["invoices"]
        total = round(sum(i["amount"] for i in inv), 2)
        return {**base, "kind": "invoice_list", "invoices": inv, "total": total,
                "title": _r(lang, "invoices.title", n=len(inv), total=e(total))}
    if s == "billit" and a == "send_reminder":
        n = len(ctx["invoices"]) or 1
        return {**base, "kind": "reminder", "what": _r(lang, "reminder.what", n=n), "status": _r(lang, "reminder.status"),
                "title": _r(lang, "reminder.title", n=n)}
    if s == "gosolid":
        return {**base, "kind": "collection", "what": _r(lang, "collection.what", invoice=v["invoice"], amount=e(v["amount"])),
                "status": _r(lang, "collection.status"), "fee": _r(lang, "price.gosolid"),
                "title": _r(lang, "collection.title", invoice=v["invoice"])}
    if s == "expenses":
        return {**base, "kind": "submission", "what": _r(lang, "receipts.what", count=v["count"], period=v["period"]),
                "status": _r(lang, "receipts.status"), "title": _r(lang, "receipts.title", count=v["count"])}
    if s == "financial_news":
        titles = _r(lang, f"articles.{v['topic']}")
        return {**base, "kind": "articles", "articles": [{"title": t, "minutes": 3 + i} for i, t in enumerate(titles)],
                "title": _r(lang, "articles.title", topic=v["topic"])}
    if s == "buffer" and a == "start":
        return {**base, "kind": "buffer", "monthly": v["amount"], "what": _r(lang, "buffer.what", date=_date("2026-10-25", lang)),
                "title": _r(lang, "buffer.title", amount=e(v["amount"]))}
    if s == "buffer" and a == "stop":
        return {**base, "kind": "buffer_stopped", "title": _r(lang, "buffer.stopped")}
    return {**base, "kind": "done", "title": card["action_name"]}
