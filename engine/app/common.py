"""Shared constants and helpers (paths, time frame, feature lists, cohort banding)."""
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "bank.duckdb"
MODELS_DIR = ROOT / "models"

# Time frame: today is 1 Oct 2026.
TODAY = "2026-10-01"
OBS_MONTHS = [f"{2025 + (m >= 12)}-{(m % 12) + 1:02d}" for m in range(9, 21)]  # 2025-10 .. 2026-09
OUT_MONTHS = [f"{2026 + (m >= 12)}-{(m % 12) + 1:02d}" for m in range(9, 21)]  # 2026-10 .. 2027-09

MOMENTS = ["move_house", "buy_car", "renovation", "start_investing", "cash_squeeze"]
MOMENT_LABELS = {
    "move_house": "Moving house",
    "buy_car": "Buying a car",
    "renovation": "Renovating",
    "start_investing": "Starting to invest",
    "cash_squeeze": "Cash squeeze",
    "birth": "A new baby",
}
# Events a customer can declare. "birth" is never predicted: only the customer can tell us.
DECLARABLE_EVENTS = MOMENTS + ["birth"]

STAGES = ["student", "young_single", "couple_no_kids", "family", "empty_nest", "retired"]
REGIONS = ["Flanders", "Wallonia", "Brussels"]
EMPLOYMENT = ["employee", "self_employed", "retired", "student"]
CITIES = {  # (name, weight) per region
    "Flanders": [("Antwerpen", 5), ("Gent", 4), ("Leuven", 2), ("Brugge", 2), ("Mechelen", 1.5), ("Hasselt", 1.5),
                 ("Kortrijk", 1.2), ("Aalst", 1.2), ("Sint-Niklaas", 1), ("Genk", 1)],
    "Wallonia": [("Liège", 4), ("Charleroi", 4), ("Namur", 2.5), ("Mons", 2), ("Wavre", 1), ("Louvain-la-Neuve", 1),
                 ("Tournai", 1.2), ("Verviers", 1)],
    "Brussels": [("Brussels", 4), ("Ixelles", 2), ("Schaerbeek", 2), ("Etterbeek", 1), ("Uccle", 1.5), ("Anderlecht", 2)],
}
CITY_NAMES = [c for r in REGIONS for c, _ in CITIES[r]]
CATEGORIES = ["groceries", "housing", "transport", "diy_building", "furniture", "travel"]

PROFILE_MODEL_FEATURES = ["age", "household_size", "n_children", "owns_home", "renting", "employment_type"]
BEHAVIOUR_FEATURES = [
    "net_income_monthly", "income_volatility", "savings_balance", "savings_growth_3m",
    "avg_current_balance", "min_balance_12m", "days_negative_12m", "fixed_cost_ratio",
    "investments_value", "mortgage_rate_reset_months", "lease_end_months",
    "months_since_home_purchase", "has_car", "car_age_years", "months_since_car_purchase",
    "car_repair_12m", "diy_building_spend_3m", "diy_building_spend_12m", "furniture_spend_3m",
    "travel_spend_12m", "invest_page_views_90d", "term_deposit_maturity_months",
]
# Usage of third-party services inside KBC Mobile (simulated integrations).
SERVICE_FEATURES = [
    "parking_sessions_90d", "parking_city_changed_90d", "sncb_tickets_90d", "has_commuter_pass",
    "cambio_bookings_12m", "fuel_spend_12m", "driving_licence_prep", "has_lease_car_movesmart",
    "myhome_valuations_90d", "registered_email_to_landlord_90d", "service_vouchers_monthly",
    "billit_overdue_invoices", "billit_overdue_amount", "financial_news_reads_30d", "airport_passes_12m",
]
BEHAVIOUR_FEATURES = BEHAVIOUR_FEATURES + SERVICE_FEATURES
COHORT_FEATURES = [f"cohort_{m}" for m in MOMENTS]
MODEL_FEATURES = PROFILE_MODEL_FEATURES + BEHAVIOUR_FEATURES + COHORT_FEATURES
CATEGORICAL_FEATURES = ["employment_type"]  # integer-coded, index into EMPLOYMENT

# Cohorts: age band x household-size band x region.
AGE_EDGES = [25, 35, 45, 55, 65, 75]
AGE_BAND_LABELS = ["18–24", "25–34", "35–44", "45–54", "55–64", "65–74", "75+"]
HH_EDGES = [2, 3, 5]
HH_BAND_LABELS = ["1 person", "2 people", "3–4 people", "5+ people"]
N_CELLS = len(AGE_BAND_LABELS) * len(HH_BAND_LABELS) * len(REGIONS)


def cohort_cell(age, household_size, region_code):
    a = np.digitize(np.asarray(age), AGE_EDGES)
    h = np.digitize(np.asarray(household_size), HH_EDGES)
    return a * (len(HH_BAND_LABELS) * len(REGIONS)) + h * len(REGIONS) + np.asarray(region_code)


def cohort_label(age, household_size, region_code):
    a = int(np.digitize(age, AGE_EDGES))
    h = int(np.digitize(household_size, HH_EDGES))
    return f"aged {AGE_BAND_LABELS[a]}, household of {HH_BAND_LABELS[h]}, {REGIONS[int(region_code)]}"


# "People like you": nearest neighbours on a small standardised feature set.
NEIGHBOUR_FEATURES = [
    "age", "household_size", "n_children", "owns_home", "renting", "net_income_monthly",
    "income_volatility", "savings_balance", "fixed_cost_ratio", "avg_current_balance",
    "investments_value", "car_age_years",
]
_LOG_FEATURES = {"net_income_monthly", "savings_balance", "investments_value"}


def neighbour_matrix(cols: dict) -> np.ndarray:
    """cols: mapping feature -> array (or scalar). Returns float32 matrix (rows x 12), unscaled."""
    out = []
    for f in NEIGHBOUR_FEATURES:
        v = np.asarray(cols[f], dtype=np.float64)
        v = np.nan_to_num(v, nan=0.0)
        if f in _LOG_FEATURES:
            v = np.log1p(np.clip(v, 0, None))
        elif f == "avg_current_balance":
            v = np.sign(v) * np.log1p(np.abs(v))
        out.append(np.atleast_1d(v))
    return np.stack(out, axis=1).astype(np.float32)


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))
