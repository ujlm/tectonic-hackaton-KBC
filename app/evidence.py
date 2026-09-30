"""Turn one customer's monthly category totals into plausible individual transactions.

Deterministic (seeded by user_id) so the same customer always shows the same evidence.
Transactions are generated on demand and never stored for all users.
"""
from functools import lru_cache

import numpy as np

from .common import OBS_MONTHS

MERCHANTS = {
    "groceries": ["Colruyt", "Delhaize", "Carrefour Market", "Aldi", "Lidl", "Okay", "Spar", "Albert Heijn"],
    "fuel": ["TotalEnergies", "Q8", "DATS 24", "Esso", "Shell", "Lukoil"],
    "transit": ["NMBS/SNCB", "De Lijn", "STIB-MIVB", "TEC", "Blue-bike"],
    "garage": ["Midas", "Norauto", "Carglass", "Garage Peeters", "Garage Dupont", "Autocentrum Janssens", "Speedy"],
    "diy_building": ["Gamma", "Brico", "Hubo", "Mr. Bricolage", "Brico Plan-it", "Facq", "Van Marcke", "Tollens"],
    "furniture": ["IKEA", "Leen Bakker", "JYSK", "Casa", "Maisons du Monde", "Kwantum", "Vanden Borre"],
    "travel": ["Brussels Airlines", "TUI", "Ryanair", "Booking.com", "Airbnb", "Eurostar", "Sunweb"],
}
SPLITS = {"groceries": (4, 8), "diy_building": (1, 3), "furniture": (1, 2), "travel": (1, 2)}


def _date(month: str, day: int) -> str:
    return f"{month}-{min(day, 28):02d}"


@lru_cache(maxsize=512)
def _cached(user_id: int, key: tuple) -> tuple:
    monthly, employment_type, employer_name, has_car, car_repair_12m, savings_growth_3m = key
    monthly = dict(monthly)
    rng = np.random.default_rng(user_id * 7919 + 17)
    txns = []

    def add(month_idx, merchant, amount, category):
        txns.append({"date": _date(OBS_MONTHS[month_idx], int(rng.integers(1, 29))), "merchant": merchant,
                     "amount": round(float(amount), 2), "category": category})

    # Income credits.
    payer = {"employee": employer_name, "self_employed": "Client payments (own business)",
             "retired": "Pension payment", "student": "Student job / transfers"}[employment_type]
    for t, amt in enumerate(monthly["income"]):
        if amt > 0:
            txns.append({"date": _date(OBS_MONTHS[t], 25 + t % 3), "merchant": payer, "amount": round(float(amt), 2),
                         "category": "income"})

    # Housing: one rent / mortgage debit per month.
    for t, amt in enumerate(monthly["housing"]):
        if amt > 0:
            txns.append({"date": _date(OBS_MONTHS[t], 2), "merchant": "Rent or mortgage instalment",
                         "amount": -round(float(amt), 2), "category": "housing"})

    # Split categories into a few purchases at typical merchants.
    for cat, (lo, hi) in SPLITS.items():
        for t, amt in enumerate(monthly[cat]):
            if amt < 5:
                continue
            k = int(rng.integers(lo, hi + 1))
            parts = rng.dirichlet(np.ones(k)) * amt
            for p in parts:
                add(t, MERCHANTS[cat][int(rng.integers(len(MERCHANTS[cat])))], -p, cat)

    # Transport: garage visits for repairs (placed in the costliest months), the rest is fuel/transit.
    transport = np.array(monthly["transport"], dtype=float)
    remaining = float(car_repair_12m or 0)
    repairs = np.zeros(12)
    for t in np.argsort(-transport):
        if remaining < 1:
            break
        r = min(remaining, max(transport[t] - np.median(transport) * 0.8, 0))
        repairs[t], remaining = r, remaining - r
    for t in range(12):
        if repairs[t] >= 1:
            add(t, MERCHANTS["garage"][int(rng.integers(len(MERCHANTS["garage"])))], -repairs[t], "car_repair")
        rest = transport[t] - repairs[t]
        if rest >= 5:
            pool = MERCHANTS["fuel"] if has_car else MERCHANTS["transit"]
            for p in rng.dirichlet(np.ones(2)) * rest:
                add(t, pool[int(rng.integers(len(pool)))], -p, "transport")

    # Savings transfers in the last 3 months.
    g = float(savings_growth_3m or 0)
    if abs(g) >= 10:
        for t, share in zip(range(9, 12), rng.dirichlet(np.ones(3))):
            txns.append({"date": _date(OBS_MONTHS[t], 26 + t % 3),
                         "merchant": "Transfer to savings account" if g > 0 else "Transfer from savings account",
                         "amount": round(float(-g * share), 2), "category": "savings"})

    txns.sort(key=lambda x: x["date"])
    return tuple(txns)


def transactions(user_id: int, monthly: dict, profile: dict, features: dict) -> list[dict]:
    """All synthetic transactions of the 12-month observation window for one customer."""
    key = (
        tuple((k, tuple(round(float(x), 2) for x in v)) for k, v in monthly.items()),
        profile["employment_type"], profile["employer_name"], bool(features["has_car"]),
        features.get("car_repair_12m"), features.get("savings_growth_3m"),
    )
    return [dict(t) for t in _cached(int(user_id), key)]


def examples(txns: list[dict], categories, last_months: int | None = None, n: int = 3, largest=True) -> list[dict]:
    """Pick n example transactions of the given categories (largest, or most recent)."""
    cats = {categories} if isinstance(categories, str) else set(categories)
    since = OBS_MONTHS[-last_months] if last_months else OBS_MONTHS[0]
    pool = [t for t in txns if t["category"] in cats and t["date"] >= since]
    key = (lambda t: abs(t["amount"])) if largest else (lambda t: t["date"])
    return sorted(pool, key=key, reverse=True)[:n]
