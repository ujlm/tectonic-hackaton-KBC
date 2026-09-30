"""A cautious outlook of the current account for the next 6 months (Oct 2026 – Mar 2027).

Built only from what we observed (Oct 2025 – Sep 2026): the recent level, last year's seasonal pattern for the same
months, the usual dip within a month, how much income varies, and overdue invoices. It never looks at the
generator's hidden outcome window. It is a picture for the customer, not the model: the chance of a tight month
itself comes from the cash-squeeze model.

A buffer plan sets money aside on payday; whenever the account would go below zero, the buffer tops it up.
"""
import math

import numpy as np

from . import i18n
from .common import OUT_MONTHS

HORIZON = 6
BUFFER_MIN, BUFFER_MAX, BUFFER_STEP = 10, 300, 10


def _num(v, default=0.0) -> float:
    return default if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


def project(monthly: dict, values: dict, p_cash: float, buffer_monthly: float | None = None, lang: str = "en") -> dict:
    lang = i18n.norm(lang)
    bal = np.asarray(monthly["balance"], dtype=float)
    income = _num(values.get("net_income_monthly"))
    level = bal[-3:].mean()
    season = bal[:HORIZON] - bal.mean()          # Oct 2025 – Mar 2026 relative to the year's average
    trend = (bal[-3:].mean() - bal[:3].mean()) / 9
    end = level + 0.8 * season + 0.5 * trend * np.arange(1, HORIZON + 1)
    # The usual dip inside a month (bills before payday), seen in the lowest month last year.
    dip = float(np.clip(bal.min() - _num(values.get("min_balance_12m"), bal.min()), 0.1 * income, 0.6 * income))
    # A cautious view: a weaker month for variable incomes, and slower payments for overdue invoices.
    bad_month = income * min(_num(values.get("income_volatility")), 0.6) * 0.6
    late = np.zeros(HORIZON)
    if _num(values.get("billit_overdue_invoices")) >= 1:
        late[:4] = -min(_num(values.get("billit_overdue_amount")), 0.8 * income) * np.array([0.25, 0.5, 0.6, 0.5])
    low = end - dip - bad_month + late

    shortfall = np.maximum(0.0, -low)
    need = max((shortfall[k] / (k + 1) for k in range(HORIZON)), default=0.0)
    if need > 0:
        suggested = math.ceil(need / BUFFER_STEP) * BUFFER_STEP
    else:
        suggested = round(0.03 * income / BUFFER_STEP) * BUFFER_STEP
    # Never suggest more than about a tenth of income: a partial cover is better than an unaffordable plan.
    cap = max(20, math.floor(0.10 * income / BUFFER_STEP) * BUFFER_STEP)
    suggested = int(min(max(suggested, 20), cap, BUFFER_MAX))

    k_min = int(np.argmin(low))
    out = {
        "months": [i18n.month_label(m, lang) for m in OUT_MONTHS[:HORIZON]],
        "months_long": [i18n.month_label(m, lang, long=True) for m in OUT_MONTHS[:HORIZON]],
        "ym": OUT_MONTHS[:HORIZON],
        "low": [round(float(x)) for x in low],
        "tightest_index": k_min,
        "tightest_month": i18n.month_label(OUT_MONTHS[k_min], lang, long=True),
        "tightest_amount": round(float(low[k_min]), -1),
        "below_zero": bool(low[k_min] < 0),
        "probability": float(p_cash),
        "suggested_buffer": suggested,
        "buffer": None,
    }
    if buffer_monthly:
        saved = buffer_monthly * np.arange(1, HORIZON + 1)
        with_buffer = np.where(low < 0, np.minimum(0.0, low + saved), low)
        covered = bool((with_buffer >= 0).all())
        out["buffer"] = {
            "monthly": float(buffer_monthly), "low": [round(float(x)) for x in with_buffer], "covered": covered,
            "saved_by_tightest": round(float(saved[k_min])),
        }
    out["summary"] = summary(out, lang)
    return out


SUMMARY = {
    "en": {"below": "Your tightest month looks like {month}: your balance could dip to about {amount}.",
           "above": "Your tightest month looks like {month}, with about {amount} left at the lowest point.",
           "covered": "With {buffer} a month set aside, the buffer covers it.",
           "partly": "With {buffer} a month set aside, the buffer covers part of it."},
    "nl": {"below": "Je krapste maand wordt wellicht {month}: je saldo kan zakken tot ongeveer {amount}.",
           "above": "Je krapste maand wordt wellicht {month}, met op het laagste punt nog ongeveer {amount}.",
           "covered": "Met {buffer} per maand opzij vangt de buffer dat op.",
           "partly": "Met {buffer} per maand opzij vangt de buffer een deel op."},
    "fr": {"below": "Votre mois le plus serré semble être {month} : votre solde pourrait descendre à environ {amount}.",
           "above": "Votre mois le plus serré semble être {month}, avec environ {amount} au plus bas.",
           "covered": "Avec {buffer} par mois de côté, la réserve couvre ce creux.",
           "partly": "Avec {buffer} par mois de côté, la réserve en couvre une partie."},
}


def summary(f: dict, lang: str) -> str:
    t = SUMMARY[lang]
    s = t["below" if f["below_zero"] else "above"].format(month=f["tightest_month"],
                                                          amount=i18n.eur(f["tightest_amount"], lang))
    if f["buffer"] and f["below_zero"]:
        s += " " + t["covered" if f["buffer"]["covered"] else "partly"].format(buffer=i18n.eur(f["buffer"]["monthly"], lang))
    return s
