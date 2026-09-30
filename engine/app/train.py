"""Milestone 2: one interpretable LightGBM classifier per key moment.

    python -m app.train

- trains on a sample of at most 400k customers (80/20 split)
- adds cohort features (outcome rate per age band x household band x region) computed on the
  training split only
- prints AUC and a calibration table per moment, saves models to models/
- scores every customer into the `scores` table
- saves a standardised float32 neighbour pool for "people like you" rates
"""
import json
import time

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from .common import (
    CATEGORICAL_FEATURES, COHORT_FEATURES, DB_PATH, EMPLOYMENT, MODEL_FEATURES, MODELS_DIR, MOMENTS,
    N_CELLS, NEIGHBOUR_FEATURES, REGIONS, cohort_cell, neighbour_matrix,
)

MAX_SAMPLE = 400_000
COHORT_PRIOR_WEIGHT = 50
PARAMS = dict(
    objective="binary", learning_rate=0.05, num_leaves=31, min_data_in_leaf=200,
    feature_fraction=0.8, bagging_fraction=0.8, bagging_freq=1, lambda_l2=1.0,
    verbose=-1, seed=7,
)
ROUNDS = 300

SELECT = """
SELECT p.user_id, p.age, p.household_size, p.n_children, p.owns_home, p.renting,
       p.employment_type, p.region, f.* EXCLUDE (user_id), o.* EXCLUDE (user_id)
FROM profiles p JOIN features f USING (user_id) JOIN outcomes o USING (user_id)
"""


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Encode categoricals/bools so the frame can feed LightGBM (cohort columns added later)."""
    df = df.copy()
    df["employment_type"] = df["employment_type"].map({e: i for i, e in enumerate(EMPLOYMENT)}).astype(np.int32)
    df["region_code"] = df["region"].map({r: i for i, r in enumerate(REGIONS)}).astype(np.int32)
    for c in ("owns_home", "renting", "has_car", "parking_city_changed_90d", "has_commuter_pass",
              "driving_licence_prep", "has_lease_car_movesmart"):
        df[c] = df[c].astype(np.float32)
    return df


def cohort_rates(train: pd.DataFrame) -> np.ndarray:
    cell = cohort_cell(train["age"].to_numpy(), train["household_size"].to_numpy(), train["region_code"].to_numpy())
    counts = np.bincount(cell, minlength=N_CELLS).astype(np.float64)
    rates = np.zeros((N_CELLS, len(MOMENTS)))
    for j, m in enumerate(MOMENTS):
        y = train[m].to_numpy().astype(np.float64)
        prior = y.mean()
        rates[:, j] = (np.bincount(cell, weights=y, minlength=N_CELLS) + COHORT_PRIOR_WEIGHT * prior) / (counts + COHORT_PRIOR_WEIGHT)
    return rates


def add_cohort(df: pd.DataFrame, rates: np.ndarray) -> pd.DataFrame:
    cell = cohort_cell(df["age"].to_numpy(), df["household_size"].to_numpy(), df["region_code"].to_numpy())
    for j, c in enumerate(COHORT_FEATURES):
        df[c] = rates[cell, j].astype(np.float32)
    return df


def matrix(df: pd.DataFrame) -> pd.DataFrame:
    return df[MODEL_FEATURES].astype({c: np.float32 for c in MODEL_FEATURES if c not in CATEGORICAL_FEATURES})


def calibration_table(y: np.ndarray, p: np.ndarray, bins: int = 5) -> str:
    order = np.argsort(p)
    lines = ["      bin   predicted  observed"]
    for i, idx in enumerate(np.array_split(order, bins)):
        lines.append(f"      q{i + 1}    {p[idx].mean():8.1%}  {y[idx].mean():8.1%}")
    return "\n".join(lines)


def main():
    t0 = time.time()
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    n_total = con.execute("SELECT count(*) FROM profiles").fetchone()[0]

    rng = np.random.default_rng(0)
    ids = pd.DataFrame({"user_id": np.sort(rng.choice(np.arange(1, n_total + 1), size=min(n_total, MAX_SAMPLE), replace=False)).astype(np.int32)})
    sample = prepare(con.execute(SELECT + " JOIN ids USING (user_id) ORDER BY user_id").fetchdf())
    is_test = rng.random(len(sample)) < 0.2
    train, test = sample[~is_test].copy(), sample[is_test].copy()

    rates = cohort_rates(train)
    train, test = add_cohort(train, rates), add_cohort(test, rates)
    X_train, X_test = matrix(train), matrix(test)
    print(f"Loaded {len(sample):,} of {n_total:,} customers ({len(train):,} train / {len(test):,} test) in {time.time() - t0:.1f}s")

    boosters, aucs, base_rates = {}, {}, {}
    for m in MOMENTS:
        t = time.time()
        ds = lgb.Dataset(X_train, train[m].astype(int), categorical_feature=CATEGORICAL_FEATURES, free_raw_data=False)
        b = lgb.train(PARAMS, ds, num_boost_round=ROUNDS)
        p = b.predict(X_test)
        y = test[m].to_numpy().astype(int)
        aucs[m] = float(roc_auc_score(y, p))
        base_rates[m] = float(train[m].mean())
        b.save_model(str(MODELS_DIR / f"{m}.txt"))
        boosters[m] = b
        top = pd.Series(b.feature_importance("gain"), index=MODEL_FEATURES).nlargest(4)
        print(f"\n{m:16s} AUC {aucs[m]:.3f}   base rate {base_rates[m]:.1%}   ({time.time() - t:.1f}s)")
        print(f"      top features: {', '.join(top.index)}")
        print(calibration_table(y, p))

    # Neighbour pool: whole sample, standardised, float32.
    nb = neighbour_matrix({f: sample[f].to_numpy() for f in NEIGHBOUR_FEATURES})
    mean, std = nb.mean(0), nb.std(0) + 1e-6
    np.savez(
        MODELS_DIR / "neighbours.npz",
        X=((nb - mean) / std).astype(np.float32), mean=mean, std=std,
        user_id=sample["user_id"].to_numpy(), y=sample[MOMENTS].to_numpy().astype(np.uint8),
    )

    meta = {
        "features": MODEL_FEATURES, "categorical": CATEGORICAL_FEATURES, "moments": MOMENTS,
        "cohort_rates": rates.round(5).tolist(), "base_rates": base_rates, "auc": aucs,
        "n_customers": int(n_total), "n_train": int(len(train)), "trained_at": time.strftime("%Y-%m-%d %H:%M"),
    }
    (MODELS_DIR / "meta.json").write_text(json.dumps(meta, indent=1))

    # Score every customer, in chunks.
    t = time.time()
    con.execute("DROP TABLE IF EXISTS scores")
    chunk = 500_000
    for lo in range(1, n_total + 1, chunk):
        df = prepare(con.execute(SELECT + f" WHERE user_id BETWEEN {lo} AND {lo + chunk - 1}").fetchdf())
        X = matrix(add_cohort(df, rates))
        scores = pd.DataFrame({"user_id": df["user_id"].to_numpy()})
        for m in MOMENTS:
            scores[f"p_{m}"] = boosters[m].predict(X).astype(np.float32)
        if lo == 1:
            con.execute("CREATE TABLE scores AS SELECT * FROM scores")
        else:
            con.execute("INSERT INTO scores SELECT * FROM scores")
    con.close()
    print(f"\nScored {n_total:,} customers in {time.time() - t:.1f}s. Total time {time.time() - t0:.1f}s")
    print("AUC summary: " + ", ".join(f"{m} {a:.3f}" for m, a in aucs.items()))


if __name__ == "__main__":
    main()
