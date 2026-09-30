"""Milestone 3: the assumptions layer.

Turns model contributions into assumption cards the customer can confirm, reject or edit, keeps
per-customer overrides in memory, and rescores live (milliseconds per correction).
"""
import json
import math
import re
import threading

import duckdb
import lightgbm as lgb
import numpy as np

from . import evidence, forecast, i18n, journeys, orchestrator
from . import session as session_store
from .services import mock
from .services.registry import NOT_USED_SERVICES, SIGNAL_EFFECTS
from .common import (
    AGE_BAND_LABELS, AGE_EDGES, COHORT_FEATURES, DB_PATH, DECLARABLE_EVENTS, EMPLOYMENT, HH_EDGES, MODEL_FEATURES,
    MODELS_DIR, MOMENT_LABELS, MOMENTS, NEIGHBOUR_FEATURES, OBS_MONTHS, OUT_MONTHS, REGIONS, cohort_cell,
    neighbour_matrix, sigmoid,
)

# Evidence sources (keys into i18n "source.*").
TX, PROD, APP, PEERS, TOLD, SVC = "transactions", "products", "app", "peers", "told", "services"

# Feature catalogue: every model feature, in plain English.
# type: amount | ratio | months | years | count | bool | choice | cohort
# months features carry `when`: "ahead" (in N months) or "ago" (N months ago).
CATALOGUE = {
    "age": dict(label="You are {value} old", evidence="Date of birth on file", editable=False, type="years",
                min=18, max=110, source=PROD),
    "household_size": dict(label="Your household has {value} people", label_one="You live on your own",
                           evidence="From your customer profile",
                           editable=True, type="count", min=1, max=12, source=PROD),
    "n_children": dict(label="{value} children live with you", label_zero="No children live with you",
                       label_one="1 child lives with you",
                       evidence="From your customer profile", editable=True, type="count", min=0, max=10, source=PROD),
    "owns_home": dict(label="You own your home", label_false="You don't own a home",
                      evidence="Mortgage or home insurance with us", editable=True, type="bool", source=PROD),
    "renting": dict(label="You rent your home", label_false="You don't rent a home",
                    evidence="Monthly rent transfers and a rental guarantee account", editable=True, type="bool", source=TX),
    "employment_type": dict(label="You are {value}", evidence="Based on the kind of income you receive",
                            editable=True, type="choice", options=EMPLOYMENT, source=TX),
    "net_income_monthly": dict(label="Your net income is about {value} a month", evidence="{income_evidence}",
                               editable=True, type="amount", min=0, max=50_000, unit="€/month", source=TX,
                               examples=("income", None, False)),
    "income_volatility": dict(label="Your income varies by about {value} from month to month",
                              evidence="Monthly income ranged from {inc_min} to {inc_max} over the last 12 months",
                              editable=True, type="ratio", min=0, max=2, source=TX),
    "savings_balance": dict(label="You have about {value} in savings", evidence="Balance of your savings accounts on 30 Sep 2026",
                            editable=True, type="amount", min=0, max=5_000_000, unit="€", source=PROD),
    "savings_growth_3m": dict(label="Your savings changed by {value} since July",
                              evidence="Net transfers between your current and savings accounts",
                              editable=True, type="amount", signed=True, min=-1_000_000, max=1_000_000, unit="€", source=TX,
                              examples=("savings", 3, True)),
    "avg_current_balance": dict(label="Your current account holds {value} on average",
                                evidence="Average month-end balance, Oct 2025 – Sep 2026", editable=False,
                                type="amount", source=PROD),
    "min_balance_12m": dict(label="Your lowest balance this year was {value}", evidence="Lowest point, reached in {min_month}",
                            editable=False, type="amount", source=PROD),
    "days_negative_12m": dict(label="Your account was below zero on {value} days this year",
                              label_zero="Your account never went below zero this year",
                              evidence="Counted from your daily balances, Oct 2025 – Sep 2026", editable=False,
                              type="count", source=PROD),
    "fixed_cost_ratio": dict(label="Fixed costs take about {value} of your income",
                             evidence="Rent or mortgage, utilities, insurance and subscriptions: about {fixed_amount} a month",
                             editable=True, type="ratio", min=0, max=1.5, source=TX, examples=("housing", 3, False)),
    "investments_value": dict(label="You hold {value} in investments", label_zero="You don't hold any investments with us",
                              evidence="Value of your investment portfolio with us on 30 Sep 2026",
                              editable=True, type="amount", min=0, max=10_000_000, unit="€", source=PROD),
    "mortgage_rate_reset_months": dict(label="Your mortgage rate resets {value}", label_null="You have no variable-rate mortgage",
                                       evidence="Variable-rate mortgage: next rate review in {when_month}",
                                       editable=False, type="months", when="ahead", source=PROD),
    "lease_end_months": dict(label="Your rental lease ends {value}", label_null="You don't have a rental lease",
                             evidence="Rental guarantee account opened in {lease_start}; standard 3-year lease",
                             editable=True, type="months", when="ahead", min=0, max=120, nullable=True, source=PROD),
    "months_since_home_purchase": dict(label="You bought your home {value}", label_null="You haven't bought a home",
                                       evidence="Mortgage deed or home insurance started in {when_month}",
                                       editable=True, type="months", when="ago", min=0, max=900, nullable=True, source=PROD),
    "has_car": dict(label="You have a car", label_false="You don't have a car",
                    evidence="Car insurance policy and regular fuel payments", evidence_false="No car insurance or fuel payments found",
                    editable=True, type="bool", source=PROD),
    "car_age_years": dict(label="Your car is about {value} old", label_null="You don't have a car",
                          label_zero="Your car is less than a year old",
                          evidence="Vehicle on your car insurance: first registered in {car_year}",
                          editable=True, type="years", min=0, max=40, nullable=True, source=PROD),
    "months_since_car_purchase": dict(label="You bought your current car {value}", label_null="You don't have a car",
                                      evidence="Car insurance policy started in {when_month}",
                                      editable=True, type="months", when="ago", min=0, max=600, nullable=True, source=PROD),
    "car_repair_12m": dict(label="You spent {value} on car repairs this year", label_zero="You had no car repairs this year",
                           evidence="{n_payments} at garages", editable=True, type="amount", min=0, max=100_000,
                           unit="€", source=TX, examples=("car_repair", None, True)),
    "diy_building_spend_3m": dict(label="You spent {value} at DIY and building suppliers since July",
                                  label_zero="You spent nothing at DIY or building suppliers since July",
                                  evidence="{n_payments} at DIY and building suppliers since July; {diy_12m} over the last 12 months", editable=True,
                                  type="amount", min=0, max=500_000, unit="€", source=TX, examples=("diy_building", 3, True)),
    "diy_building_spend_12m": dict(label="You spent {value} at DIY and building suppliers this year",
                                   label_zero="You spent nothing at DIY or building suppliers this year",
                                   evidence="{n_payments} at DIY and building suppliers", editable=True,
                                   type="amount", min=0, max=1_000_000, unit="€", source=TX, examples=("diy_building", None, True)),
    "furniture_spend_3m": dict(label="You spent {value} on furniture since July",
                               label_zero="You bought no furniture since July",
                               evidence="{n_payments} at furniture stores since July", editable=True,
                               type="amount", min=0, max=200_000, unit="€", source=TX, examples=("furniture", 3, True)),
    "travel_spend_12m": dict(label="You spent {value} on travel this year", label_zero="You spent nothing on travel this year",
                             evidence="{n_payments} to airlines, tour operators and booking sites", editable=True,
                             type="amount", min=0, max=500_000, unit="€", source=TX, examples=("travel", None, True)),
    "invest_page_views_90d": dict(label="You opened the Invest pages {value} times since July",
                                  label_zero="You haven't opened the Invest pages since July",
                                  evidence="Visits to the Invest section of the mobile app", editable=False, type="count", source=APP),
    "term_deposit_maturity_months": dict(label="Your term deposit matures {value}", label_null="You have no term deposit",
                                         evidence="Term deposit with us, maturing in {when_month}", editable=False,
                                         type="months", when="ahead", source=PROD),
    # --- Service usage in KBC Mobile (simulated integrations) ---
    "parking_sessions_90d": dict(label="You started {value} parking sessions in {parking_city} via 4411 in the last 3 months",
                                 label_zero="You haven't used 4411 parking in the last 3 months",
                                 evidence="{parking_evidence}", editable=False, type="count", source=SVC),
    "parking_city_changed_90d": dict(label="You recently parked mostly in {parking_city}, not in {city}",
                                     label_false="You mostly park where you live ({city})",
                                     evidence="4411 parking sessions by city, last 3 months", editable=False, type="bool", source=SVC),
    "sncb_tickets_90d": dict(label="You bought {value} SNCB train tickets in KBC Mobile in the last 3 months",
                             label_zero="You bought no SNCB tickets in KBC Mobile in the last 3 months",
                             evidence="Tickets bought through SNCB in KBC Mobile", editable=False, type="count", source=SVC),
    "has_commuter_pass": dict(label="You have an SNCB commuter pass", label_false="You don't have an SNCB commuter pass",
                              evidence="Commuter pass bought through SNCB in KBC Mobile",
                              evidence_false="No commuter pass bought in KBC Mobile", editable=True, type="bool", source=SVC),
    "cambio_bookings_12m": dict(label="You booked a Cambio car {value} times this year", label_zero="You didn't book a Cambio car this year",
                                evidence="Cambio car-sharing bookings paid in KBC Mobile", editable=False, type="count", source=SVC),
    "fuel_spend_12m": dict(label="You spent {value} on fuel this year", label_zero="You spent nothing on fuel this year",
                           evidence="{n_payments} at fuel stations", editable=True, type="amount", min=0, max=50_000, unit="€",
                           source=TX, examples=("transport", None, True)),
    "driving_licence_prep": dict(label="You're preparing for your driving licence", label_false="You're not preparing for a driving licence",
                                 evidence="Theory exam and lesson bookings via Driving licence in KBC Mobile",
                                 evidence_false="No driving-licence bookings in KBC Mobile", editable=True, type="bool", source=SVC),
    "has_lease_car_movesmart": dict(label="You drive a company lease car (Movesmart)", label_false="You don't have a Movesmart lease car",
                                    evidence="Lease contract visible in Movesmart in KBC Mobile",
                                    evidence_false="No lease contract in Movesmart", editable=True, type="bool", source=SVC),
    "myhome_valuations_90d": dict(label="You checked your home's value {value} times in MyHome in the last 3 months",
                                  label_zero="You didn't use MyHome in the last 3 months",
                                  evidence="MyHome valuations in KBC Mobile", editable=False, type="count", source=SVC),
    "registered_email_to_landlord_90d": dict(label="You sent {value} registered e-mail(s) to your landlord in the last 3 months",
                                             label_zero="You sent no registered e-mails to your landlord recently",
                                             evidence="Registered e-mail in KBC Mobile: we only see that the recipient is your landlord, never the content",
                                             editable=False, type="count", source=SVC),
    "service_vouchers_monthly": dict(label="You order about {value} service vouchers a month", label_zero="You don't order service vouchers",
                                     evidence="Service voucher orders in KBC Mobile", editable=False, type="count", source=SVC),
    "billit_overdue_invoices": dict(label="{value} of your invoices in Billit are overdue", label_zero="None of your Billit invoices are overdue",
                                    label_null="You don't use Billit in KBC Mobile",
                                    evidence="Billit invoices past their due date: {billit_amount} in total", editable=False,
                                    type="count", source=SVC),
    "billit_overdue_amount": dict(label="Your overdue Billit invoices total {value}", label_zero="You have no overdue Billit invoices",
                                  label_null="You don't use Billit in KBC Mobile", evidence="Billit invoices past their due date",
                                  editable=False, type="amount", source=SVC),
    "financial_news_reads_30d": dict(label="You read {value} financial news articles in KBC Mobile this month",
                                     label_zero="You didn't read financial news in KBC Mobile this month",
                                     evidence="Articles opened in Financial news, last 30 days", editable=False, type="count", source=SVC),
    "airport_passes_12m": dict(label="You booked {value} Brussels Airport passes this year",
                               label_zero="You didn't book Brussels Airport passes this year",
                               evidence="Fast Lane and lounge passes via Brussels Airport in KBC Mobile", editable=False,
                               type="count", source=SVC),
    "cohort": dict(label="Customers like you ({cohort}) often go through these moments",
                   evidence="Share of similar customers who had each moment last year", editable=False, type="cohort",
                   source=PEERS),
}

EDITABLE = {k: v for k, v in CATALOGUE.items() if v["editable"]}
# Features whose contributions are shown on another feature's card (same evidence).
CARD_GROUP = {"diy_building_spend_12m": "diy_building_spend_3m", "parking_city_changed_90d": "parking_sessions_90d",
              "billit_overdue_amount": "billit_overdue_invoices", **{c: "cohort" for c in COHORT_FEATURES}}



def signals_not_used(lang: str = "en") -> list[str]:
    lang = i18n.norm(lang)
    what = i18n.ui.NOT_USED_WHAT.get(lang, {})
    return list(i18n.ui.SIGNALS_NOT_USED[lang]) + [
        i18n.ui.NOT_USED_SERVICE[lang].format(name=name, what=what.get(sid, w)) for sid, name, w in NOT_USED_SERVICES]

MONTH_NAMES = {
    1: ["january", "jan", "januari", "janvier", "janv"], 2: ["february", "feb", "februari", "février", "fevrier", "févr"],
    3: ["march", "mar", "maart", "mars"], 4: ["april", "apr", "avril", "avr"], 5: ["may", "mei", "mai"],
    6: ["june", "jun", "juni", "juin"], 7: ["july", "jul", "juli", "juillet", "juil"],
    8: ["august", "aug", "augustus", "août", "aout"], 9: ["september", "sep", "sept", "septembre"],
    10: ["october", "oct", "oktober", "okt", "octobre"], 11: ["november", "nov", "novembre"],
    12: ["december", "dec", "décembre", "decembre", "déc"],
}
NOT_PLANNED = {"none", "no", "never", "not planned", "not_planned", "cancel", "niet", "nooit", "pas", "jamais"}


class ValidationError(ValueError):
    pass


# ----------------------------------------------------------------------------------------------
# Formatting helpers
# ----------------------------------------------------------------------------------------------
def month_label(ym: str, lang: str = "en") -> str:
    return i18n.month_label(ym, lang)


def shift_month(months: float, ahead: bool, lang: str = "en") -> str:
    """Calendar month N months after (ahead) or before (ago) 1 Oct 2026."""
    idx = 2026 * 12 + 9 + (int(round(months)) if ahead else -int(round(months)))
    return month_label(f"{idx // 12}-{idx % 12 + 1:02d}", lang)


def is_null(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def eur(v: float, signed=False, lang: str = "en") -> str:
    return i18n.eur(v, lang, signed)


def fmt_value(feature: str, v, lang: str = "en") -> str:
    c = CATALOGUE[feature]
    t = c["type"]
    if is_null(v):
        return "—"
    if t == "amount":
        return eur(v, c.get("signed", False), lang)
    if t == "ratio":
        return i18n.pct(v, lang)
    if t == "months":
        n = int(round(v))
        if c.get("when") == "ahead":
            return i18n.t("months.now", lang) if n == 0 else i18n.t(
                "months.ahead", lang, n=i18n.plural(n, "month", lang), month=shift_month(n, True, lang))
        return i18n.t("months.this_month", lang) if n == 0 else i18n.t(
            "months.ago", lang, n=i18n.plural(n, "month", lang), month=shift_month(n, False, lang))
    if t == "years":
        n = int(round(v))
        return i18n.t("years.lt1", lang) if n == 0 and feature == "car_age_years" else i18n.plural(n, "year", lang)
    if t == "count":
        return i18n.number(round(v), lang)
    if t == "bool":
        return i18n.t("yes" if v else "no", lang)
    if t == "choice":
        return i18n.t(f"emp.{v}", lang) if v in EMPLOYMENT else str(v)
    return str(v)


def texts(feature: str, lang: str = "en") -> dict:
    """The catalogue entry with its labels and evidence in the customer's language."""
    c = CATALOGUE[feature]
    lang = i18n.norm(lang)
    return c if lang == "en" else {**c, **i18n.features.TEXT.get(lang, {}).get(feature, {})}


def sentence(feature: str, v, ctx: dict, lang: str = "en") -> str:
    c = texts(feature, lang)
    if feature == "cohort":
        return c["label"].format(cohort=ctx["cohort"])
    if is_null(v) and "label_null" in c:
        return c["label_null"]
    if c["type"] == "bool":
        return _safe_format(c["label"] if v else c["label_false"], ctx)
    if not is_null(v) and v == 0 and "label_zero" in c:
        return c["label_zero"]
    if not is_null(v) and v == 1 and "label_one" in c:
        return c["label_one"]
    return _safe_format(c["label"], {**ctx, "value": fmt_value(feature, v, lang)})


def cohort_text(age, household_size, region: str, lang: str = "en") -> str:
    lang = i18n.norm(lang)
    a, h = int(np.digitize(age, AGE_EDGES)), int(np.digitize(household_size, HH_EDGES))
    return i18n.t("cohort", lang, age=AGE_BAND_LABELS[a], household=i18n.ui.HOUSEHOLD_BANDS[lang][h],
                  region=i18n.ui.REGIONS[lang][region])


def housing_of(v: dict) -> str:
    return "owner" if v.get("owns_home") else "tenant" if v.get("renting") else "with_parents"


# ----------------------------------------------------------------------------------------------
# Validation of customer-supplied values
# ----------------------------------------------------------------------------------------------
def parse_month(month) -> str | None:
    """Map a month expression to YYYY-MM inside the outcome window (Oct 2026 - Sep 2027).
    Returns None for 'not planned'. Raises ValidationError if it can't be placed in the window."""
    if month is None:
        raise ValidationError("Please give a month, e.g. 'March' or '2027-03'.")
    s = str(month).strip().lower()
    if s in NOT_PLANNED:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})", s)
    if m:
        ym = f"{int(m.group(1))}-{int(m.group(2)):02d}"
        if ym not in OUT_MONTHS:
            raise ValidationError(f"{ym} is outside the next 12 months (Oct 2026 – Sep 2027).")
        return ym
    if s in ("next month", "volgende maand", "le mois prochain", "mois prochain"):
        return OUT_MONTHS[1]
    if s in ("this month", "deze maand", "ce mois", "ce mois-ci"):
        return OUT_MONTHS[0]
    for num, names in MONTH_NAMES.items():
        if s.split()[0].strip(".") in names or s == str(num):
            return next(ym for ym in OUT_MONTHS if int(ym[5:]) == num)
    raise ValidationError(f"I couldn't read '{month}' as a month. Use a month name or YYYY-MM.")


def validate(feature: str, value):
    """Return a clean value for an editable feature or raise ValidationError with a clear message."""
    if feature not in CATALOGUE or feature == "cohort":
        raise ValidationError(f"Unknown feature '{feature}'. Editable features: {', '.join(EDITABLE)}.")
    c = CATALOGUE[feature]
    if not c["editable"]:
        raise ValidationError(f"'{feature}' comes straight from our own records and can't be edited here.")
    t = c["type"]
    if value is None or (isinstance(value, str) and value.strip().lower() in ("", "null", "none")):
        if c.get("nullable"):
            return float("nan")
        raise ValidationError(f"'{feature}' needs a value.")
    if t == "bool":
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if s in ("true", "yes", "1", "ja", "oui", "y"):
            return True
        if s in ("false", "no", "0", "nee", "non", "n"):
            return False
        raise ValidationError(f"'{feature}' is yes/no; got '{value}'.")
    if t == "choice":
        s = str(value).strip().lower().replace("-", "_").replace(" ", "_")
        if s in c["options"]:
            return s
        raise ValidationError(f"'{feature}' must be one of: {', '.join(c['options'])}.")
    if isinstance(value, bool):
        raise ValidationError(f"'{feature}' needs a number, not yes/no.")
    if isinstance(value, str):
        s = value.strip().lower().replace("€", "").replace("eur", "").replace(" ", "")
        pct = s.endswith("%")
        s = s.rstrip("%")
        mult = 1000 if s.endswith("k") else 1
        s = s.rstrip("k")
        if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", s):  # 2.500,50 (Belgian notation)
            s = s.replace(".", "").replace(",", ".")
        s = s.replace(",", "")
        try:
            num = float(s) * mult
        except ValueError:
            raise ValidationError(f"'{feature}' needs a number; got '{value}'.") from None
        if pct:
            num /= 100
    else:
        num = float(value)
    if math.isnan(num) or math.isinf(num):
        raise ValidationError(f"'{feature}' needs a finite number.")
    if t == "ratio" and num > c["max"]:
        num /= 100  # "35" means 35%
    if t in ("months", "years", "count"):
        num = float(round(num))
    lo, hi = c.get("min", -math.inf), c.get("max", math.inf)
    if not lo <= num <= hi:
        shown = (lambda x: f"{x * 100:.0f}%") if t == "ratio" else (lambda x: f"{x:,.0f}")
        raise ValidationError(f"'{feature}' must be between {shown(lo)} and {shown(hi)}; got {shown(num)}.")
    return num


# ----------------------------------------------------------------------------------------------
# Engine
# ----------------------------------------------------------------------------------------------
class Engine:
    def __init__(self):
        self.lock = threading.RLock()
        self.con = duckdb.connect(str(DB_PATH), read_only=True)
        self.meta = json.loads((MODELS_DIR / "meta.json").read_text())
        assert self.meta["features"] == MODEL_FEATURES, "Models were trained on another feature set: re-run app.train"
        self.boosters = {m: lgb.Booster(model_file=str(MODELS_DIR / f"{m}.txt")) for m in MOMENTS}
        self.cohort_rates = np.array(self.meta["cohort_rates"])
        nb = np.load(MODELS_DIR / "neighbours.npz")
        self.nb_X, self.nb_mean, self.nb_std = nb["X"], nb["mean"], nb["std"]
        self.nb_y, self.nb_ids = nb["y"].astype(np.float32), nb["user_id"]
        self.n_customers = self.con.execute("SELECT count(*) FROM profiles").fetchone()[0]
        self.sessions: dict[int, dict] = {}
        self._base_cache: dict[int, dict] = {}

    # --- data access ------------------------------------------------------------------------
    def base(self, uid: int) -> dict:
        if uid in self._base_cache:
            return self._base_cache[uid]
        with self.lock:
            cur = self.con.cursor()
            prof = cur.execute("SELECT * FROM profiles WHERE user_id = ?", [uid]).fetchdf()
            if prof.empty:
                raise KeyError(uid)
            feats = cur.execute("SELECT * FROM features WHERE user_id = ?", [uid]).fetchdf()
            monthly = cur.execute("SELECT * FROM monthly WHERE user_id = ?", [uid]).fetchdf()
        profile = {k: _py(v) for k, v in prof.iloc[0].items()}
        features = {k: _py(v) for k, v in feats.iloc[0].items() if k != "user_id"}
        m = {k: [float(x) for x in v] for k, v in monthly.iloc[0].items() if k != "user_id"}
        base = {"profile": profile, "features": features, "monthly": m}
        if len(self._base_cache) > 2000:
            self._base_cache.clear()
        self._base_cache[uid] = base
        return base

    def session(self, uid: int) -> dict:
        return self.sessions.setdefault(uid, session_store.new())

    def run(self, uid: int, blob: dict | None, fn):
        """Run fn() against the customer's client-held session. Returns (fn(), the updated session blob).

        Sessions live in the browser: every request brings its session and gets the new one back, so the engine
        stays stateless (safe on serverless, and one visitor never sees another's corrections)."""
        with self.lock:
            self.sessions[uid] = session_store.load(blob, uid)
            try:
                return fn(), session_store.dump(self.sessions[uid], uid)
            finally:
                self.sessions.pop(uid, None)

    # --- feature vector -------------------------------------------------------------------------
    def values(self, uid: int) -> dict:
        """Current raw values of every editable/profile/behaviour feature, overrides applied."""
        b = self.base(uid)
        v = {**{k: b["profile"][k] for k in ("age", "household_size", "n_children", "owns_home", "renting",
                                               "employment_type", "region", "city")}, **b["features"]}
        s = self.session(uid)
        v.update(s["service_updates"])
        v.update(s["implied"])
        v.update(s["overrides"])
        return v

    def vector(self, v: dict) -> np.ndarray:
        region = REGIONS.index(v["region"])
        cell = int(cohort_cell(v["age"], v["household_size"], region))
        row = []
        for f in MODEL_FEATURES:
            if f in COHORT_FEATURES:
                row.append(self.cohort_rates[cell, MOMENTS.index(f[len("cohort_"):])])
            elif f == "employment_type":
                row.append(EMPLOYMENT.index(v[f]))
            else:
                x = v[f]
                row.append(np.nan if x is None else float(x))
        return np.array([row], dtype=np.float64)

    def score(self, v: dict) -> dict:
        X = self.vector(v)
        out = {}
        for m in MOMENTS:
            contrib = self.boosters[m].predict(X, pred_contrib=True)[0]
            out[m] = {"logit": float(contrib.sum()), "contrib": contrib[:-1]}
        return out

    def neighbour_rates(self, v: dict, k: int = 500, uid: int | None = None) -> dict:
        q = (neighbour_matrix({f: v[f] for f in NEIGHBOUR_FEATURES}) - self.nb_mean) / self.nb_std
        d = ((self.nb_X - q) ** 2).sum(1)
        idx = np.argpartition(d, k + 1)[: k + 1]
        idx = idx[self.nb_ids[idx] != uid][:k] if uid is not None else idx[:k]
        return {m: float(r) for m, r in zip(MOMENTS, self.nb_y[idx].mean(0))}

    # --- state ------------------------------------------------------------------------------------
    def predictions(self, uid: int, v: dict, scored: dict, lang: str = "en") -> list[dict]:
        s = self.session(uid)
        region = REGIONS.index(v["region"])
        cell = int(cohort_cell(v["age"], v["household_size"], region))
        nb = self.neighbour_rates(v, uid=uid)
        preds = []
        for j, m in enumerate(MOMENTS):
            p_model = float(sigmoid(scored[m]["logit"]))
            d = s["declared"].get(m)
            prob = p_model if d is None else (0.95 if d["month"] else min(0.05, p_model))
            preds.append({
                "moment": m, "label": MOMENT_LABELS[m], "label_local": i18n.ui.MOMENTS[i18n.norm(lang)][m],
                "probability": prob, "model_probability": p_model,
                "cohort_rate": float(self.cohort_rates[cell, j]), "neighbour_rate": nb[m],
                "declared": d is not None, "declared_month": d["month"] if d else None,
                "declared_label": _declared_label(d, lang) if d else None,
            })
        if "birth" in s["declared"]:
            d = s["declared"]["birth"]
            preds.append({"moment": "birth", "label": MOMENT_LABELS["birth"],
                          "label_local": i18n.ui.MOMENTS[i18n.norm(lang)]["birth"], "probability": 0.95 if d["month"] else 0.05,
                          "model_probability": None, "cohort_rate": None, "neighbour_rate": None, "declared": True,
                          "declared_month": d["month"], "declared_label": _declared_label(d, lang), "not_predicted": True})
        preds.sort(key=lambda p: -p["probability"])
        return preds

    def cards(self, uid: int, v: dict, scored: dict, n: int = 5, lang: str = "en", include=()) -> list[dict]:
        s = self.session(uid)
        groups: dict[str, list[int]] = {}
        for i, f in enumerate(MODEL_FEATURES):
            groups.setdefault(CARD_GROUP.get(f, f), []).append(i)
        effects = {}
        for g, idx in groups.items():
            pts = {}
            for m in MOMENTS:
                logit = scored[m]["logit"]
                pts[m] = float(100 * (sigmoid(logit) - sigmoid(logit - scored[m]["contrib"][idx].sum())))
            effects[g] = pts
        ranked = sorted(effects, key=lambda g: -sum(abs(x) for x in effects[g].values()))
        pinned = set(s["overrides"]) | set(s["confirmed"])
        chosen = set(ranked[:n]) | pinned | set(include)
        # Keep the order stable within a session so a corrected card doesn't jump away.
        order = [g for g in s["card_order"] if g in chosen] + [g for g in ranked if g in chosen and g not in s["card_order"]]
        s["card_order"] = order
        chosen = order
        b = self.base(uid)
        txns = evidence.transactions(uid, b["monthly"], b["profile"], b["features"])
        region = REGIONS.index(v["region"])
        lang = i18n.norm(lang)
        ctx = self._context(uid, v, txns, lang)
        ctx["cohort"] = cohort_text(v["age"], v["household_size"], v["region"], lang)
        moment_names = i18n.ui.MOMENTS[lang]
        out = []
        for g in chosen:
            c = texts(g, lang)
            value = None if g == "cohort" else v[g]
            ex = []
            if g == "billit_overdue_invoices":
                inv = mock.invoices_for(uid, v.get("billit_overdue_invoices"), v.get("billit_overdue_amount"))
                ex = [{"date": i["due"], "merchant": i18n.t("invoice.overdue", lang, client=i["client"], number=i["number"],
                                                           days=i["days_overdue"]),
                       "amount": i["amount"]} for i in inv[:3]]
            if "examples" in c:
                cat, months, largest = c["examples"]
                ex = evidence.examples(txns, cat, months, n=3, largest=largest)
                k = len([t for t in txns if t["category"] == cat and (months is None or t["date"] >= OBS_MONTHS[-months])])
                ctx["n_payments"] = i18n.plural(k, "payment", lang)
            if c["type"] == "months" and not is_null(value):
                ctx["when_month"] = shift_month(value, c.get("when") == "ahead", lang)
            ev = c.get("evidence_false") if c["type"] == "bool" and not value and "evidence_false" in c else c["evidence"]
            if g == "cohort":
                cell = int(cohort_cell(v["age"], v["household_size"], REGIONS.index(v["region"])))
                ev_text = ev + ": " + ", ".join(f"{moment_names[m].lower()} {i18n.pct(self.cohort_rates[cell, j], lang)}"
                                                for j, m in enumerate(MOMENTS))
            else:
                ev_text = _safe_format(ev, ctx) if not (is_null(value) and "label_null" in c) else i18n.t("nothing_on_file", lang)
            status = "overridden" if g in s["overrides"] else "confirmed" if g in s["confirmed"] else (
                "implied" if g in s["implied"] else "inferred")
            base_value = None if g == "cohort" else self.base_value(uid, g)
            source = TOLD if status in ("overridden", "implied") else c["source"]
            out.append({
                "feature": g, "sentence": sentence(g, value, ctx, lang),
                "evidence": {"text": ev_text, "transactions": ex},
                "value": _json_val(value), "value_display": "" if g == "cohort" else fmt_value(g, value, lang),
                "original_display": fmt_value(g, base_value, lang) if status in ("overridden", "implied") else None,
                "type": c["type"], "editable": c["editable"], "min": c.get("min"), "max": c.get("max"),
                "unit": c.get("unit"), "options": c.get("options"), "nullable": c.get("nullable", False),
                "source": i18n.t(f"source.{source}", lang), "source_key": source, "status": status,
                "effects": sorted(
                    [{"moment": m, "label": moment_names[m], "pts": round(p, 1)} for m, p in effects[g].items()
                     if abs(p) >= 0.5], key=lambda e: -abs(e["pts"])),
            })
        return out

    def card(self, uid: int, feature: str, lang: str = "en") -> dict | None:
        """One assumption card, even if it isn't among the customer's top cards."""
        with self.lock:
            v = self.values(uid)
            return next((c for c in self.cards(uid, v, self.score(v), lang=lang, include={feature})
                         if c["feature"] == feature), None)

    def contribution_pts(self, uids: list[int], moment: str, feature: str) -> np.ndarray:
        """Percentage points one feature adds to one moment, for several customers at once."""
        X = np.vstack([self.vector(self.values(u)) for u in uids])
        contrib = self.boosters[moment].predict(X, pred_contrib=True)
        logit = contrib.sum(1)
        c = contrib[:, MODEL_FEATURES.index(feature)]
        return 100 * (sigmoid(logit) - sigmoid(logit - c))

    def base_value(self, uid: int, feature: str):
        b = self.base(uid)
        return b["profile"].get(feature, b["features"].get(feature))

    def _context(self, uid: int, v: dict, txns: list, lang: str = "en") -> dict:
        b = self.base(uid)
        inc = b["monthly"]["income"]
        bal = b["monthly"]["balance"]
        emp = b["profile"]["employment_type"]
        city = i18n.journeys.city
        ctx = {
            "income_evidence": i18n.t(f"income_evidence.{emp}", lang, employer=b["profile"]["employer_name"]),
            "inc_min": eur(min(inc), lang=lang), "inc_max": eur(max(inc), lang=lang),
            "min_month": month_label(OBS_MONTHS[int(np.argmin(bal))], lang),
            "fixed_amount": eur(v["fixed_cost_ratio"] * v["net_income_monthly"], lang=lang),
            "n_payments": i18n.plural(0, "payment", lang),
            "diy_12m": eur(v["diy_building_spend_12m"], lang=lang), "city": city(v["city"], lang),
            "parking_city": city(v.get("parking_city_recent") or v["city"], lang),
            "billit_amount": eur(v.get("billit_overdue_amount") or 0, lang=lang),
        }
        key = "parking_evidence.changed" if v.get("parking_city_changed_90d") else "parking_evidence.home"
        ctx["parking_evidence"] = i18n.t(key, lang, parking_city=ctx["parking_city"], city=ctx["city"])
        for f, key in (("lease_end_months", "lease_start"),):
            if not is_null(v.get(f)):
                ctx[key] = shift_month(36 - v[f], False, lang)
        if not is_null(v.get("car_age_years")):
            ctx["car_year"] = str(2026 - int(v["car_age_years"]))
        return ctx

    def _svc_ctx(self, uid: int, v: dict | None = None, p_cash: float | None = None) -> dict:
        b = self.base(uid)
        v = v or self.values(uid)
        ctx = mock.context(uid, b["profile"], v, self.session(uid))
        if p_cash is None:
            p_cash = self._probs(uid).get("cash_squeeze", 0.0)
        ctx["suggested_buffer"] = forecast.project(b["monthly"], v, p_cash)["suggested_buffer"]
        return ctx

    def forecast(self, uid: int, lang: str = "en", buffer_monthly: float | None = None) -> dict:
        """Balance outlook for the coming months (with the customer's buffer plan, or a what-if amount)."""
        b = self.base(uid)
        s = self.session(uid)
        plan = s["plans"].get("buffer_monthly") if buffer_monthly is None else buffer_monthly
        return forecast.project(b["monthly"], self.values(uid), self._probs(uid).get("cash_squeeze", 0.0),
                                buffer_monthly=plan, lang=lang)

    def state(self, uid: int, lang: str = "en") -> dict:
        """Everything the app and the under-the-hood panel show for one customer. Customer-facing text is in
        `lang`; rules and orchestrator reasons stay in English (they're for the jury)."""
        lang = i18n.norm(lang)
        with self.lock:
            v = self.values(uid)
            scored = self.score(v)
            b = self.base(uid)
            s = self.session(uid)
            prof = {**b["profile"], **{k: v[k] for k in ("age", "household_size", "n_children", "owns_home",
                                                           "renting", "employment_type")}}
            prof["housing"] = housing_of(v)
            preds = self.predictions(uid, v, scored, lang)
            cards = self.cards(uid, v, scored, lang=lang)
            probs = {p["moment"]: p["probability"] for p in preds if p["moment"] in MOMENTS}
            svc_ctx = mock.context(uid, prof, v, s)
            outlook = forecast.project(b["monthly"], v, probs["cash_squeeze"], s["plans"].get("buffer_monthly"), lang)
            svc_ctx["suggested_buffer"] = outlook["suggested_buffer"]
            js = journeys.build(v, probs, s["declared"], prof, svc_ctx, lang)
            ctx = self._context(uid, v, [], lang)
            rejected = [f for f in list(s["overrides"]) + list(s["implied"]) if f in CATALOGUE]
            baseline = None
            if rejected:  # what Kate would have offered without the corrections, to explain suppressions
                bv = {**{k: b["profile"][k] for k in ("age", "household_size", "n_children", "owns_home", "renting",
                                                        "employment_type", "region", "city")}, **b["features"], **s["service_updates"]}
                bprobs = {m: float(sigmoid(x["logit"])) for m, x in self.score(bv).items()}
                baseline = journeys.build(bv, bprobs, s["declared"], b["profile"], svc_ctx, lang)
            kate = orchestrator.plan(js, s, {f: sentence(f, self.base_value(uid, f), ctx, lang) for f in rejected}, baseline)
            return {
                "user_id": uid, "lang": lang,
                "profile": {k: _json_val(x) for k, x in prof.items()},
                "plate": svc_ctx["plate"],
                "chart": {"months": [month_label(m, lang) for m in OBS_MONTHS], **b["monthly"]},
                "forecast": outlook,
                "predictions": preds,
                "cards": cards,
                "journeys": js,
                "kate": kate,
                "opener": orchestrator.pick_opener(kate),
                "actions": [mock.for_display(a) for a in sorted(s["actions"].values(), key=lambda a: -int(a["id"][1:]))],
                "plans": dict(s["plans"]),
                "overrides": [{"feature": f, "sentence": sentence(f, x, ctx, lang) if f != "cohort" else "",
                               "value_display": fmt_value(f, x, lang),
                               "original_display": fmt_value(f, self.base_value(uid, f), lang)}
                              for f, x in s["overrides"].items()],
                "confirmed": list(s["confirmed"]),
                "declared": [{"event": e, "label": i18n.ui.MOMENTS[lang][e], **d} for e, d in s["declared"].items()],
                "ignored": dict(s["ignored"]),
                "signals_not_used": signals_not_used(lang),
                "model": {"auc": self.meta["auc"], "n_customers": self.n_customers},
            }

    # --- service actions (simulated integrations) ----------------------------------------------
    def prepare_action(self, uid: int, service: str, action: str, params: dict | None = None, lang: str = "en") -> dict:
        """Kate (or a help item) prepares an action. Nothing is executed until the customer confirms."""
        with self.lock:
            s = self.session(uid)
            try:
                card = mock.prepare(str(service), str(action), params or {}, self._svc_ctx(uid), s["seq"] + 1,
                                    i18n.norm(lang))
            except mock.ActionError as e:
                raise ValidationError(str(e)) from None
            s["seq"] += 1
            s["actions"][card["id"]] = card
            return {"card": card, "diff": []}

    def confirm_action(self, uid: int, action_id: str) -> dict:
        """Executes a prepared action. Only ever called from the customer's tap in the UI."""
        with self.lock:
            s = self.session(uid)
            card = s["actions"].get(action_id)
            if card is None:
                raise ValidationError(f"No prepared action '{action_id}'.")
            if card["status"] != "prepared":
                raise ValidationError(f"Action {action_id} is already {card['status']}.")
            before = self._probs(uid)
            card["result"] = mock.execute(card, self._svc_ctx(uid))
            card["status"] = "done"
            if (card["service"], card["action"]) == ("4411", "stop_parking"):
                for other in s["actions"].values():
                    if other["result"].get("session_id") == card["params"]["session_id"] and other is not card:
                        other["result"]["stopped"] = True
            if card["service"] == "buffer":  # a plan, not a model signal: it only changes the outlook
                if card["action"] == "start":
                    s["plans"]["buffer_monthly"] = float(card["params"]["amount"])
                else:
                    s["plans"].pop("buffer_monthly", None)
            effect = SIGNAL_EFFECTS.get((card["service"], card["action"]))
            if effect and not (card["service"] == "registered_email" and card["params"].get("template") != "lease_termination"):
                f, op, val = effect
                cur = self.values(uid).get(f)
                s["service_updates"][f] = (0 if is_null(cur) else cur) + val if op == "inc" else val
            after = self._probs(uid)
            return {"card": mock.for_display(card), "diff": self._diff(before, after)}

    def cancel_action(self, uid: int, action_id: str) -> dict:
        with self.lock:
            card = self.session(uid)["actions"].get(action_id)
            if card is None or card["status"] != "prepared":
                raise ValidationError(f"No prepared action '{action_id}' to cancel.")
            card["status"] = "cancelled"
            return {"card": card, "diff": []}

    def ignore_topic(self, uid: int, moment: str) -> dict:
        """The customer waved away a Kate conversation: pause that topic for 60 days."""
        with self.lock:
            if moment not in MOMENTS:
                raise ValidationError(f"Unknown moment '{moment}'.")
            self.session(uid)["ignored"][moment] = orchestrator.pause_until()
            return {"diff": [], "change": {"moment": moment, "paused_until": orchestrator.pause_until()}}

    # --- mutations ----------------------------------------------------------------------------
    def _probs(self, uid: int) -> dict:
        v = self.values(uid)
        scored = self.score(v)
        return {p["moment"]: p["probability"] for p in self.predictions(uid, v, scored)}

    def _diff(self, before: dict, after: dict, lang: str = "en") -> list[dict]:
        names = i18n.ui.MOMENTS[i18n.norm(lang)]
        return [{"moment": m, "label": names.get(m, m), "before": before.get(m), "after": after.get(m)}
                for m in dict.fromkeys(list(before) + list(after))
                if before.get(m) is None or after.get(m) is None or abs(before[m] - after[m]) >= 0.0005]

    def override(self, uid: int, feature: str, value, lang: str = "en") -> dict:
        with self.lock:
            clean = validate(feature, value)
            before = self._probs(uid)
            s = self.session(uid)
            old = self.values(uid)
            s["overrides"][feature] = clean
            s["implied"].update(_implied(feature, clean, old, s["overrides"]))
            for f in s["overrides"]:
                s["implied"].pop(f, None)
            if feature in s["confirmed"]:
                s["confirmed"].remove(feature)
            after = self._probs(uid)
            ctx = self._context(uid, self.values(uid), [], lang)
            return {"diff": self._diff(before, after, lang),
                    "change": {"feature": feature, "from": fmt_value(feature, old[feature], lang),
                               "to": fmt_value(feature, clean, lang), "sentence": sentence(feature, clean, ctx, lang)}}

    def confirm(self, uid: int, feature: str) -> dict:
        with self.lock:
            if feature not in CATALOGUE:
                raise ValidationError(f"Unknown feature '{feature}'.")
            s = self.session(uid)
            if feature not in s["confirmed"]:
                s["confirmed"].append(feature)
            return {"diff": [], "change": {"feature": feature, "confirmed": True}}

    def declare(self, uid: int, event: str, month, lang: str = "en") -> dict:
        with self.lock:
            event = str(event).strip().lower()
            if event not in DECLARABLE_EVENTS or event == "cash_squeeze":
                raise ValidationError(f"Unknown event '{event}'. Use one of: move_house, buy_car, renovation, "
                                      "start_investing, birth.")
            ym = parse_month(month)
            before = self._probs(uid)
            self.session(uid)["declared"][event] = {"month": ym}
            after = self._probs(uid)
            return {"diff": self._diff(before, after, lang), "change": {"event": event, "month": ym}}

    def reset(self, uid: int) -> dict:
        with self.lock:
            before = self._probs(uid)
            self.sessions[uid] = session_store.new()
            return {"diff": self._diff(before, self._probs(uid))}


def _implied(feature: str, value, old: dict, overrides: dict) -> dict:
    """Keep related features coherent when the customer corrects one of them."""
    imp = {}
    if feature == "owns_home":
        if value:
            imp["renting"] = False
            imp["lease_end_months"] = float("nan")
        else:
            imp["months_since_home_purchase"] = float("nan")
            imp["mortgage_rate_reset_months"] = float("nan")
    elif feature == "renting":
        if value:
            imp["owns_home"] = False
            imp["months_since_home_purchase"] = float("nan")
        else:
            imp["lease_end_months"] = float("nan")
    elif feature == "lease_end_months" and not is_null(value):
        imp.update(renting=True, owns_home=False)
    elif feature == "months_since_home_purchase" and not is_null(value):
        imp.update(owns_home=True, renting=False, lease_end_months=float("nan"))
    elif feature == "has_car" and not value:
        imp.update(car_age_years=float("nan"), months_since_car_purchase=float("nan"))
    elif feature in ("car_age_years", "months_since_car_purchase") and not is_null(value):
        imp["has_car"] = True
        if feature == "months_since_car_purchase" and "car_age_years" not in overrides:
            age = old.get("car_age_years")
            if is_null(age) or age > value / 12 + 0.5:
                imp["car_age_years"] = float(round(value / 12))  # assume a new car unless told otherwise
    elif feature == "n_children":
        imp["household_size"] = max(old["household_size"] - old["n_children"] + value, value + 1)
    elif feature == "household_size" and old["n_children"] > value - 1:
        imp["n_children"] = max(value - 1, 0)
    elif feature == "diy_building_spend_3m":
        imp["diy_building_spend_12m"] = max(value, old["diy_building_spend_12m"] - (old["diy_building_spend_3m"] - value))
    elif feature == "diy_building_spend_12m" and value < old["diy_building_spend_3m"]:
        imp["diy_building_spend_3m"] = value
    return {k: x for k, x in imp.items() if k not in overrides}


def _declared_label(d: dict, lang: str = "en") -> str:
    return i18n.t("declared.month", lang, month=month_label(d["month"], lang)) if d["month"] else i18n.t(
        "declared.not_planned", lang)


def _safe_format(template: str, ctx: dict) -> str:
    try:
        return template.format(**ctx)
    except (KeyError, ValueError):
        return re.sub(r"\{[^}]*\}", "", template).strip()


def _py(x):
    if isinstance(x, (np.generic,)):
        x = x.item()
    if isinstance(x, float) and math.isnan(x):
        return None
    try:
        import pandas as pd
        if x is pd.NA or x is pd.NaT:
            return None
    except ImportError:
        pass
    return x


def _json_val(x):
    if isinstance(x, float) and math.isnan(x):
        return None
    if isinstance(x, np.generic):
        return x.item()
    return x
