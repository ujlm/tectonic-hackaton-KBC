"""Milestone 1: synthetic bank generator.

    python -m app.generate --n 200000 --seed 42

Everything is vectorised numpy. Hidden state (life stage, latent intents) drives the observed
signals and the outcomes but is never written to the database.
Observation window Oct 2025 - Sep 2026 (features); outcome window Oct 2026 - Sep 2027 (labels).
"""
import argparse
import time

import duckdb
import numpy as np
import pandas as pd

from .common import CATEGORIES, CITIES, CITY_NAMES, DATA_DIR, DB_PATH, EMPLOYMENT, REGIONS, STAGES

STAGE_P = [0.06, 0.15, 0.15, 0.30, 0.16, 0.18]

NAMES_NL = ["Lotte", "Emma", "Louise", "Marie", "Elise", "Noor", "Julie", "Lien", "Sofie", "An",
            "Hanne", "Fien", "Anke", "Griet", "Kato", "Jens", "Pieter", "Wout", "Arne", "Bram",
            "Thomas", "Stijn", "Koen", "Dries", "Ruben", "Lars", "Seppe", "Joris", "Tom", "Wim"]
NAMES_FR = ["Camille", "Manon", "Chloé", "Léa", "Clara", "Céline", "Sophie", "Aurélie", "Nathalie",
            "Élise", "Julie", "Margaux", "Pauline", "Isabelle", "Anne", "Hugo", "Louis", "Arthur",
            "Nicolas", "Julien", "Maxime", "Antoine", "Thibault", "Mathieu", "Olivier", "Laurent",
            "Benoît", "Quentin", "Romain", "Sébastien"]
EMPLOYER_A = ["Noordzee", "Kempen", "Schelde", "Ardenne", "Meuse", "Brabant", "Zenne", "Leie", "Dijle",
              "Hesbaye", "Condroz", "Famenne", "Polder", "Haspengouw", "Westhoek", "Senne", "Durme",
              "Gaume", "Nete", "Ourthe"]
EMPLOYER_B = ["Logistics", "Bouw", "Tech", "Foods", "Care", "Engineering", "Retail", "Consult",
              "Metaal", "Energie", "Mobility", "Print", "Textiel", "Services", "Solutions", "Labs"]
EMPLOYER_C = ["NV", "BV", "SA", "SRL"]


def f32(x):
    return np.asarray(x, dtype=np.float32)


def generate(n: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    U = lambda *shape: rng.random(shape if shape else n, dtype=np.float32)  # noqa: E731
    N = lambda *shape: rng.standard_normal(shape if shape else n, dtype=np.float32)  # noqa: E731

    uid = np.arange(1, n + 1, dtype=np.int32)
    stage = rng.choice(6, size=n, p=STAGE_P).astype(np.int8)
    student, young, couple, family, empty_nest, retired = (stage == i for i in range(6))

    # --- Demographics -------------------------------------------------------------------------
    age_lo = np.array([18, 22, 25, 27, 48, 62])[stage]
    age_hi = np.array([25, 35, 45, 56, 67, 64])[stage]
    age = rng.integers(age_lo, age_hi + 1)
    age = np.where(retired, 62 + np.minimum(rng.gamma(2.0, 5.5, n), 32).astype(int), age).astype(np.int16)

    n_children = np.where(family, rng.choice([1, 2, 3, 4], size=n, p=[0.35, 0.45, 0.15, 0.05]), 0).astype(np.int16)
    adults = np.select(
        [student | young, couple, family, empty_nest, retired],
        [1, 2, np.where(U() < 0.85, 2, 1), np.where(U() < 0.85, 2, 1), np.where(U() < 0.55, 2, 1)],
    ).astype(np.int16)
    household_size = (adults + n_children).astype(np.int16)
    region = rng.choice(3, size=n, p=[0.58, 0.32, 0.10]).astype(np.int8)
    city = np.empty(n, dtype=np.int16)
    for r, name in enumerate(REGIONS):
        idx = np.array([CITY_NAMES.index(c) for c, _ in CITIES[name]])
        w = np.array([w for _, w in CITIES[name]], dtype=float)
        city[region == r] = rng.choice(idx, size=int((region == r).sum()), p=w / w.sum())

    emp = np.where(U() < 0.14, 1, 0)
    emp = np.where(empty_nest & (U() < 0.12), 2, emp)
    emp = np.where(retired, 2, np.where(student, 3, emp)).astype(np.int8)
    tenure = np.floor(U() * (age - 17)).astype(np.int16)

    # --- Home -----------------------------------------------------------------------------------
    own_p = np.array([0.02, 0.25, 0.55, 0.72, 0.82, 0.78], dtype=np.float32)[stage]
    rent_p = np.array([0.55, 0.85, 0.95, 0.95, 0.95, 0.95], dtype=np.float32)[stage]
    owns = U() < own_p
    renting = ~owns & (U() < rent_p)
    recent_p = np.array([0.3, 0.3, 0.25, 0.12, 0.04, 0.02], dtype=np.float32)[stage]
    recent_buyer = owns & (U() < recent_p)
    msince_home = np.where(
        recent_buyer, rng.integers(1, 25, n), rng.integers(25, np.maximum(26, (age - 21) * 12))
    ).astype(np.float32)
    msince_home[~owns] = np.nan
    has_mortgage = owns & (msince_home < 25 * 12) & (U() < 0.9)
    mortgage_reset = np.where(has_mortgage & (U() < 0.25), rng.integers(1, 61, n), np.nan).astype(np.float32)

    # --- Income -----------------------------------------------------------------------------
    two = adults == 2
    inc_base = np.select(
        [emp == 0, emp == 1, emp == 2, emp == 3],
        [
            (1900 + 45 * np.clip(age - 22, 0, 30)) * np.exp(0.28 * N()) * np.where(two, 1.75, 1.0),
            2600 * np.exp(0.45 * N()) * np.where(two, 1.6, 1.0),
            1500 * np.exp(0.25 * N()) * np.where(two, 1.6, 1.0),
            500 * np.exp(0.5 * N()),
        ],
    )
    inc_base = f32(np.round(inc_base / 10) * 10)
    inc_sigma = np.select(
        [emp == 0, emp == 1, emp == 2, emp == 3],
        [np.where(U() < 0.10, 0.12 + 0.23 * U(), 0.03), 0.15 + 0.55 * U(), 0.01, 0.2 + 0.4 * U()],
    ).astype(np.float32)
    s = inc_sigma[:, None]
    inc = inc_base[:, None] * np.exp(s * N(n, 24) - s * s / 2)
    dry = ((emp == 1)[:, None] & (U(n, 24) < 0.05)) | ((emp == 3)[:, None] & (U(n, 24) < 0.10))
    inc = f32(np.where(dry, inc * 0.1, inc))
    # Hidden: self-employed whose clients pay late. Income dips now and more in the coming months.
    late_payers = (emp == 1) & (U() < 0.25)
    inc[:, 10:12] *= np.where(late_payers, 0.75, 1.0)[:, None]
    inc[:, 12:16] *= np.where(late_payers, 0.55, 1.0)[:, None]
    inc_obs = inc[:, :12]
    net_income = inc_obs.mean(axis=1)
    income_vol = inc_obs.std(axis=1) / np.maximum(net_income, 1)

    # --- Wealth & products --------------------------------------------------------------------
    savings = inc_base * np.exp(np.log(2.5 + 0.12 * np.clip(age - 20, 0, None)) + 0.9 * N())
    savings = f32(savings * np.where(retired, 1.5, 1.0) * np.where(student, 0.5, 1.0))
    has_inv = U() < (0.12 + 0.006 * np.clip(age - 20, 0, 50))
    investments = f32(np.where(has_inv, savings * 0.8 * np.exp(0.8 * N()), 0.0))
    has_td = U() < np.where(retired, 0.35, np.where(age > 50, 0.15, 0.05))
    td_maturity = np.where(has_td, rng.integers(1, 37, n), np.nan).astype(np.float32)

    # --- Car ----------------------------------------------------------------------------------
    has_car = U() < np.array([0.25, 0.6, 0.85, 0.92, 0.88, 0.7], dtype=np.float32)[stage]
    car_age = np.where(has_car, np.minimum(np.floor(rng.gamma(2.2, 3.3, n)), 25), np.nan).astype(np.float32)
    lease_car = has_car & (emp == 0) & (U() < 0.12)  # company lease car managed in Movesmart
    car_age = np.where(lease_car, rng.integers(0, 4, n), car_age).astype(np.float32)
    msince_car = np.where(has_car, 1 + np.floor(U() * np.minimum(np.nan_to_num(car_age) * 12 + 6, 144)), np.nan)
    msince_car = f32(msince_car)

    # --- Latent intents (hidden) --------------------------------------------------------------
    move_base = np.array([0.22, 0.17, 0.12, 0.06, 0.05, 0.03], dtype=np.float32)[stage]
    p_move = move_base * np.where(renting, 1.7, np.where(owns, 0.55, 1.2)) * np.where(recent_buyer, 0.15, 1.0)
    car_nocar = np.array([0.03, 0.08, 0.08, 0.07, 0.03, 0.01], dtype=np.float32)[stage]
    ca = np.nan_to_num(car_age)
    p_car = np.where(has_car, 0.025 + 0.13 / (1 + np.exp(-(ca - 10) / 2.5)), car_nocar)
    p_car = p_car * np.where(has_car & (np.nan_to_num(msince_car, nan=99) < 18), 0.3, 1.0) * np.where(lease_car, 0.15, 1.0)
    p_reno = np.where(owns, np.where(recent_buyer, 0.33, 0.05), np.where(renting, 0.012, 0.005))
    p_inv = (0.03 * np.where(savings > 15000, 2.5, 1.0) * np.where((age >= 25) & (age <= 45), 1.8, 1.0)
             * np.where(investments > 0, 0.6, 1.0) * np.where(np.nan_to_num(td_maturity, nan=99) <= 3, 4.0, 1.0))
    i_move, i_car, i_reno, i_inv = (U() < np.clip(p, 0, 0.6) for p in (p_move, p_car, p_reno, p_inv))

    # --- Leading indicators (noisy, mostly in the last 3 months) --------------------------------
    lease_end = np.where(renting, rng.integers(1, 37, n), np.nan).astype(np.float32)
    lease_end = np.where(renting & i_move & (U() < 0.45), rng.integers(1, 7, n), lease_end).astype(np.float32)

    page_views = (rng.poisson(0.6, n) + (i_inv & (U() < 0.45)) * rng.poisson(7, n)
                  + (~i_inv & (U() < 0.08)) * rng.poisson(4, n) + has_inv * rng.poisson(1.5, n)).astype(np.int16)
    sav_growth = inc_base * (0.25 + 0.4 * N())
    sav_growth += (i_inv & (U() < 0.6)) * (1500 + 4500 * U())
    sav_growth -= (i_reno & (U() < 0.25)) * (1000 + 3000 * U())
    sav_growth = f32(np.round(sav_growth, -1))

    rows = np.arange(n)
    last3 = lambda: rng.integers(9, 12, n)  # noqa: E731  (month index within the last 3 months)

    # Spending categories, 12 observed months each.
    groceries = (260 * adults + 140 * n_children + 180 * student)[:, None] * np.exp(0.12 * N(n, 12))
    rent = (620 + 180 * (household_size - 1)) * np.array([1.0, 0.85, 1.25])[region] * np.exp(0.18 * N())
    rent = np.where(student, 430 * np.array([1.0, 0.85, 1.25])[region] * np.exp(0.15 * N()), rent)
    mortgage_pay = 950 * np.array([1.0, 0.85, 1.25])[region] * np.exp(0.3 * N())
    housing_m = np.where(renting, rent, np.where(has_mortgage, mortgage_pay, np.where(owns, 120, 0)))
    housing = np.repeat(f32(np.round(housing_m))[:, None], 12, axis=1)
    other_fixed = (180 + 70 * household_size) * np.exp(0.3 * N()) + 90 * has_car
    fixed_ratio = f32(np.clip((housing_m + other_fixed) / np.maximum(net_income, 1), 0.05, 1.5))

    transport = np.where(has_car, 110, 45)[:, None] * np.exp(0.25 * N(n, 12))
    repair_base = has_car * (U() < 0.6) * np.exp(np.log(150 + 35 * ca) + 0.6 * N())
    big_repair = has_car * (((i_car & (U() < 0.55)) | (~i_car & (U() < 0.07))) * (600 + 1900 * U()))
    transport[rows, rng.integers(0, 12, n)] += repair_base
    transport[rows, rng.integers(6, 12, n)] += big_repair
    car_repair = f32(np.round(repair_base + big_repair))

    diy_habit = np.where(owns, U() < 0.45, U() < 0.2) * np.where(owns, 1.0, 0.5)
    season = np.array([1, 1, 0.8, 0.8, 0.9, 1.4, 1.6, 1.5, 1.2, 1.1, 1, 1], dtype=np.float32)
    diy = diy_habit[:, None] * (U(n, 12) < 0.3) * np.exp(np.log(60) + 0.8 * N(n, 12)) * season
    reno_signal = i_reno & (U() < 0.5)
    diy[:, 9:] += (reno_signal[:, None] & (U(n, 3) < 0.8)) * (250 + 2250 * U(n, 3))
    diy[:, 6:9] += ((i_reno & (U() < 0.4))[:, None] & (U(n, 3) < 0.6)) * (100 + 700 * U(n, 3))
    diy[rows, last3()] += (~i_reno & owns & (U() < 0.13)) * (300 + 1700 * U())
    diy[rows, rng.integers(0, 9, n)] += (~i_reno & (U() < 0.08)) * (300 + 1500 * U())

    furniture = (U(n, 12) < 0.06) * (40 + 460 * U(n, 12))
    furniture[rows, last3()] += (i_move & (U() < 0.4)) * (400 + 2100 * U())
    furniture[rows, last3()] += (i_reno & (U() < 0.25)) * (300 + 1200 * U())
    furniture[rows, last3()] += (U() < 0.05) * (300 + 1700 * U())
    furniture[rows, rng.integers(0, 12, n)] += (np.nan_to_num(msince_home, nan=99) < 14) * (U() < 0.6) * (500 + 2500 * U())

    travel_budget = inc_base * U() * np.where(student, 0.5, 1.0) * np.where(fixed_ratio > 0.7, 0.4, 1.0)
    travel_w = np.zeros((n, 12), dtype=np.float32)
    travel_w[:, 9] = 0.35
    travel_w[:, 10] = 0.25
    travel_w[:, 2] = 0.1
    travel_w[:, 4] = 0.1
    travel_w += 0.2 * rng.dirichlet(np.ones(12), n).astype(np.float32)
    travel = travel_budget[:, None] * travel_w * (U(n, 12) < 0.85)

    # --- Service usage in KBC Mobile (simulated integrations) --------------------------------------
    young = age <= 26
    uses_4411 = has_car & (U() < 0.45)
    home_sessions = uses_4411 * rng.poisson(np.where(region == 2, 9, 5) * (0.3 + U()))
    away = has_car & ((i_move & (U() < 0.35)) | (~i_move & (U() < 0.07)))  # house hunting / other trips
    away_sessions = away * (2 + rng.poisson(4, n))
    parking = (home_sessions + away_sessions).astype(np.int16)
    parking_changed = away & (away_sessions > home_sessions)
    other = rng.integers(0, len(CITY_NAMES), n)
    for r, name in enumerate(REGIONS):  # 70% of moves stay within the region
        same_region = np.array([CITY_NAMES.index(c) for c, _ in CITIES[name]])
        m = (region == r) & (U() < 0.7)
        other[m] = rng.choice(same_region, size=int(m.sum()))
    other = np.where(other == city, (other + 1) % len(CITY_NAMES), other)
    parking_city = np.where(parking_changed, other, np.where(parking > 0, city, -1))

    train_user = U() < np.where(has_car, 0.12, 0.45)
    commuter_pass = ((emp == 0) | (emp == 3)) & np.where(has_car, U() < 0.05, U() < 0.35)
    sncb_tickets = (train_user * rng.poisson(np.where(student, 8, 4)) * np.where(commuter_pass, 0.2, 1.0)).astype(np.int16)
    cambio = ((~has_car & (U() < np.where(region == 2, 0.25, 0.10))) * rng.poisson(6, n)
              + (i_car & ~has_car & (U() < 0.35)) * rng.poisson(5, n)).astype(np.int16)
    fuel = f32(np.round(np.where(has_car, (transport.sum(1) - repair_base - big_repair) * np.where(lease_car, 0.3, 1.0), 0), 2))
    dl_prep = ~has_car & ((young & (U() < np.where(i_car, 0.55, 0.10))) | (~young & (U() < np.where(i_car, 0.12, 0.01))))
    myhome = (owns * (U() < 0.06) * rng.poisson(1.5, n) + (i_move & owns & (U() < 0.35)) * (1 + rng.poisson(2, n))
              + (i_reno & (U() < 0.25)) * (1 + rng.poisson(1.5, n)) + (i_move & renting & (U() < 0.15)) * (1 + rng.poisson(1, n)))
    reg_mail = (renting & ((i_move & (U() < 0.25)) | (U() < 0.025))) * (1 + (U() < 0.2))
    vouchers = ((U() < np.where(n_children > 0, 0.3, np.where(retired, 0.18, 0.08))) & ((inc_base > 2500) | retired)) * rng.integers(5, 21, n)
    uses_billit = (emp == 1) & (U() < 0.6)
    overdue_n = np.where(late_payers, 1 + rng.poisson(2.5, n), rng.poisson(0.35, n))
    overdue_amt = np.round(overdue_n * (800 + 3200 * U()), -1)
    overdue_n = np.where(uses_billit, overdue_n, np.nan).astype(np.float32)
    overdue_amt = np.where(uses_billit, overdue_amt, np.nan).astype(np.float32)
    news = ((U() < np.where(retired | (age > 45), 0.35, 0.2)) * rng.poisson(3, n) + (i_inv & (U() < 0.4)) * rng.poisson(6, n)).astype(np.int16)
    airport = ((U() < np.clip(travel_budget / 8000, 0, 0.5)) * (1 + rng.poisson(1, n))).astype(np.int16)

    cats = {k: f32(np.round(v, 2)) for k, v in zip(
        CATEGORIES, [groceries, housing, transport, diy, furniture, travel])}

    # --- Current-account balance: mean-reverting walk over 24 months ------------------------------
    var_ratio = (groceries.mean(1) + transport.mean(1) + travel.sum(1) / 12) / np.maximum(inc_base, 1)
    strain = fixed_ratio + var_ratio - 0.95 + 0.08 * N()
    drift = -inc_base * np.clip(strain, 0, None) * 0.6
    buffer = inc_base * np.exp(np.log(1.2) + 0.7 * N()) * np.where(fixed_ratio > 0.8, 0.5, 1.0)
    # Life goes on: buffer and budget strain drift a bit in the outcome window.
    buffer_out = buffer * np.exp(0.8 * N())
    drift_out = -inc_base * np.clip(strain + 0.25 * N(), 0, None) * 0.6

    lumpy = np.zeros((n, 24), dtype=np.float32)
    lumpy[:, :12] = diy + furniture + travel + (transport - transport.mean(1, keepdims=True))
    lumpy[:, :12] -= lumpy[:, :12].mean(1, keepdims=True)

    # Outcomes of the key moments (intent realised ~70% of the time + rare spontaneous events).
    move_house = (i_move & (U() < 0.7)) | (U() < 0.012)
    buy_car = (i_car & (U() < 0.7)) | (U() < 0.010)
    renovation = (i_reno & (U() < 0.7)) | (U() < 0.008)
    start_investing = (i_inv & (U() < 0.7)) | (U() < 0.010)

    # Outcome-window costs: realised moments, random shocks, mortgage rate resets.
    lumpy[rows, 12 + rng.integers(0, 12, n)] += move_house * 2000 * (0.5 + 1.5 * U())
    lumpy[rows, 12 + rng.integers(0, 12, n)] += buy_car * 1500 * (0.5 + 1.5 * U())
    reno_m = 12 + rng.integers(0, 11, n)
    reno_cost = renovation * 3000 * (0.5 + 2.0 * U())
    lumpy[rows, reno_m] += reno_cost / 2
    lumpy[rows, reno_m + 1] += reno_cost / 2
    for _ in range(2):  # unexpected bills
        lumpy[rows, 12 + rng.integers(0, 12, n)] += (U() < 0.2) * (500 + 4500 * U())
    reset_m = np.nan_to_num(mortgage_reset, nan=99)
    after_reset = (np.arange(24)[None, :] >= 11 + reset_m[:, None])
    lumpy += after_reset * (0.12 * housing_m)[:, None]

    bal = np.empty((n, 24), dtype=np.float32)
    prev = buffer + 0.3 * inc_base * N()
    noise = 0.08 * inc_base[:, None] * N(n, 24)
    for t in range(24):
        b, d = (buffer, drift) if t < 12 else (buffer_out, drift_out)
        prev = b + 0.55 * (prev - b) + 0.8 * (inc[:, t] - inc_base) - 0.5 * lumpy[:, t] + d + noise[:, t]
        bal[:, t] = prev
    dip = 0.3 * inc_base[:, None] * (0.5 + 0.7 * U(n, 24))
    intramonth_min = bal - dip

    obs_min = intramonth_min[:, :12]
    min_balance = f32(np.round(obs_min.min(1), 2))
    days_neg = np.where(obs_min < 0, np.clip(np.round(-obs_min / np.maximum(inc_base, 1)[:, None] * 30 + 1 + 4 * U(n, 12)), 1, 30), 0)
    days_neg = days_neg.sum(1).astype(np.int16)
    avg_balance = f32(np.round(bal[:, :12].mean(1), 2))

    rescued = (savings > 2 * inc_base) & (U() < 0.6)
    cash_squeeze = (intramonth_min[:, 12:].min(1) < -30) & ~rescued

    # --- Assemble tables ------------------------------------------------------------------------
    names_nl, names_fr = np.array(NAMES_NL), np.array(NAMES_FR)
    first_name = np.where(
        (region == 0) | ((region == 2) & (U() < 0.4)),
        names_nl[rng.integers(0, len(names_nl), n)], names_fr[rng.integers(0, len(names_fr), n)])
    employer = np.char.add(np.char.add(np.array(EMPLOYER_A)[rng.integers(0, len(EMPLOYER_A), n)], " "),
                           np.array(EMPLOYER_B)[rng.integers(0, len(EMPLOYER_B), n)])
    employer = np.char.add(np.char.add(employer, " "), np.array(EMPLOYER_C)[np.where(region == 0, rng.integers(0, 2, n), rng.integers(2, 4, n))])
    employer = np.select([emp == 1, emp == 2, emp == 3], ["Own business", "Pension fund", "Student jobs"], employer)

    profiles = pd.DataFrame({
        "user_id": uid, "first_name": first_name, "age": age, "region": np.array(REGIONS)[region],
        "city": np.array(CITY_NAMES)[city],
        "household_size": household_size, "n_children": n_children,
        "employment_type": np.array(EMPLOYMENT)[emp], "employer_name": employer,
        "tenure_years": tenure, "owns_home": owns, "renting": renting,
    })
    features = pd.DataFrame({
        "user_id": uid,
        "net_income_monthly": f32(np.round(net_income, 2)),
        "income_volatility": f32(np.round(income_vol, 3)),
        "savings_balance": f32(np.round(savings, 2)),
        "savings_growth_3m": sav_growth,
        "avg_current_balance": avg_balance,
        "min_balance_12m": min_balance,
        "days_negative_12m": days_neg,
        "fixed_cost_ratio": f32(np.round(fixed_ratio, 3)),
        "investments_value": f32(np.round(investments, 2)),
        "mortgage_rate_reset_months": mortgage_reset,
        "lease_end_months": lease_end,
        "months_since_home_purchase": msince_home,
        "has_car": has_car,
        "car_age_years": car_age,
        "months_since_car_purchase": msince_car,
        "car_repair_12m": car_repair,
        "diy_building_spend_3m": f32(np.round(diy[:, 9:].sum(1), 2)),
        "diy_building_spend_12m": f32(np.round(diy.sum(1), 2)),
        "furniture_spend_3m": f32(np.round(furniture[:, 9:].sum(1), 2)),
        "travel_spend_12m": f32(np.round(travel.sum(1), 2)),
        "invest_page_views_90d": page_views,
        "term_deposit_maturity_months": td_maturity,
        "parking_sessions_90d": parking,
        "parking_city_changed_90d": parking_changed,
        "sncb_tickets_90d": sncb_tickets,
        "has_commuter_pass": commuter_pass,
        "cambio_bookings_12m": cambio,
        "fuel_spend_12m": fuel,
        "driving_licence_prep": dl_prep,
        "has_lease_car_movesmart": lease_car,
        "myhome_valuations_90d": myhome.astype(np.int16),
        "registered_email_to_landlord_90d": reg_mail.astype(np.int16),
        "service_vouchers_monthly": vouchers.astype(np.int16),
        "billit_overdue_invoices": overdue_n,
        "billit_overdue_amount": overdue_amt,
        "financial_news_reads_30d": news,
        "airport_passes_12m": airport,
        "parking_city_recent": np.where(parking_city >= 0, np.array(CITY_NAMES)[np.maximum(parking_city, 0)], None),
    })
    monthly = {"user_id": uid, "balance": f32(np.round(bal[:, :12], 2)), "income": f32(np.round(inc_obs, 2)), **cats}
    outcomes = pd.DataFrame({
        "user_id": uid, "move_house": move_house, "buy_car": buy_car, "renovation": renovation,
        "start_investing": start_investing, "cash_squeeze": cash_squeeze,
    })
    return {"profiles": profiles, "features": features, "monthly": monthly, "outcomes": outcomes}


def write(tables: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for suffix in ("", ".wal"):
        p = DB_PATH.with_name(DB_PATH.name + suffix)
        if p.exists():
            p.unlink()
    con = duckdb.connect(str(DB_PATH))
    for name in ("profiles", "features", "outcomes"):
        df = tables[name]  # noqa: F841  (scanned by DuckDB by name)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM df")

    # Monthly: wide float32 frame -> LIST columns of 12 values.
    m = tables["monthly"]
    series = ["balance", "income"] + CATEGORIES
    wide = pd.DataFrame({"user_id": m["user_id"], **{f"{s}_{t}": m[s][:, t] for s in series for t in range(12)}})
    lists = ", ".join(
        "[" + ", ".join(f"round({s}_{t}, 2)" for t in range(12)) + f"]::FLOAT[] AS {s}" for s in series)
    con.execute(f"CREATE TABLE monthly AS SELECT user_id, {lists} FROM wide")
    con.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=200_000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    t0 = time.time()
    tables = generate(args.n, args.seed)
    t1 = time.time()
    write(tables)
    t2 = time.time()
    o = tables["outcomes"]
    rates = ", ".join(f"{c} {o[c].mean():.1%}" for c in o.columns if c != "user_id")
    print(f"Generated {args.n:,} customers in {t1 - t0:.1f}s, wrote {DB_PATH.relative_to(DB_PATH.parent.parent)} in {t2 - t1:.1f}s")
    print(f"Outcome rates: {rates}")


if __name__ == "__main__":
    main()
