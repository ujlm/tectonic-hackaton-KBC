"""Consistency of generated profiles on a sample of 10,000 synthetic customers."""
import numpy as np
import pandas as pd
import pytest

from app.common import MODEL_FEATURES
from app.generate import generate

N = 10_000


@pytest.fixture(scope="module")
def bank():
    t = generate(N, seed=123)
    df = t["profiles"].merge(t["features"], on="user_id")
    income = t["monthly"]["income"]
    df["income_peak"] = income.max(1)
    df["income_mean"] = income.mean(1)
    return {"df": df, "habits": t["payment_habits"]}


def test_housing_is_one_of_three_and_matches_the_flags(bank):
    df = bank["df"]
    assert set(df.housing) <= {"owner", "tenant", "with_parents"}
    assert (df.owns_home == (df.housing == "owner")).all()
    assert (df.renting == (df.housing == "tenant")).all()
    assert not (df.owns_home & df.renting).any()


def test_living_with_parents_means_a_shared_household(bank):
    wp = bank["df"][bank["df"].housing == "with_parents"]
    assert len(wp) > 100
    assert (wp.household_size >= 2).all(), "someone living with their parents is never a household of 1"
    assert (wp.age <= 30).all()
    assert (wp.n_children == 0).all()
    assert set(wp.employment_type) <= {"student", "employee", "self_employed"}


def test_own_household_is_adults_plus_children(bank):
    df = bank["df"][bank["df"].housing != "with_parents"]
    adults = df.household_size - df.n_children
    assert adults.between(1, 2).all()
    assert (df[df.n_children > 0].age >= 22).all()


def test_employment_fits_age(bank):
    df = bank["df"]
    assert (df[df.employment_type == "student"].age <= 25).all()
    assert (df[df.employment_type == "retired"].age >= 60).all()
    assert (df[df.age >= 66].employment_type == "retired").all()
    working = df[df.employment_type.isin(["employee", "self_employed"])]
    assert working.age.between(22, 65).all()


def test_home_and_car_fields_agree(bank):
    df = bank["df"]
    assert (df[df.owns_home].age >= 22).all()
    assert df.months_since_home_purchase.notna().eq(df.owns_home).all()
    assert df.lease_end_months.notna().eq(df.renting).all()
    assert df[df.mortgage_rate_reset_months.notna()].owns_home.all()
    assert df.car_age_years.notna().eq(df.has_car).all()
    assert (df[df.has_lease_car_movesmart].employment_type == "employee").all()


def _band(df, emp, lo, hi):
    return df[(df.employment_type == emp) & df.age.between(lo, hi)].net_income_monthly


def test_income_is_plausible_per_life_stage(bank):
    df = bank["df"]
    assert _band(df, "student", 18, 25).median() < 800
    assert 1500 <= _band(df, "employee", 22, 24).median() <= 2600
    assert 1500 <= df[df.employment_type == "retired"].net_income_monthly.median() <= 3000
    young_se = _band(df, "self_employed", 22, 29)
    assert young_se.median() < 3000
    assert young_se.quantile(0.99) < 8000
    # Older self-employed earn more than starters.
    assert _band(df, "self_employed", 35, 60).median() > young_se.median() * 1.3


def test_no_income_jackpots(bank):
    df = bank["df"]
    ratio = df.income_peak / np.maximum(df.income_mean, 1)
    assert ratio.max() < 4, "a single month never brings more than ~4x the average income"
    young_se = df[(df.employment_type == "self_employed") & (df.age < 30)]
    assert young_se.income_peak.quantile(0.99) < 12_000
    assert young_se.income_peak.max() < 20_000


def test_payment_habits_cover_everyone_and_are_sane(bank):
    h, df = bank["habits"], bank["df"]
    assert len(h) == N and h.user_id.is_unique
    assert (h.active_from < h.active_to).all()
    assert h.n_devices.between(1, 3).all()
    assert h.abroad_share.between(0, 0.2).all()
    assert h.typical_amount.between(20, 900).all()
    merged = h.merge(df[["user_id", "employment_type"]], on="user_id")
    assert merged.has_suppliers.eq(merged.employment_type == "self_employed").all()


def test_payment_habits_are_never_model_features(bank):
    habit_cols = set(bank["habits"].columns) - {"user_id"}
    assert not habit_cols & set(MODEL_FEATURES)
