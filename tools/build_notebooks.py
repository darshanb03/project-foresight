"""Build the three engagement notebooks.

The notebooks are the exploration record. The production logic lives in src/ and
the notebooks import it, so there is exactly one implementation of every
calculation and the notebooks can never drift from what actually ran.

    python tools/build_notebooks.py
"""


import json

from pathlib import Path

NB_DIR = Path(__file__).resolve().parents[1] / "notebooks"
NB_DIR.mkdir(exist_ok=True)

BOOT = """import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd().parent))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from src import config as C

pd.set_option("display.width", 140)
pd.set_option("display.max_columns", 40)
"""


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


def notebook(cells: list[dict]) -> dict:
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


# ------------------------------------------------------------------- 01 EDA
nb01 = notebook([
    md("""# 01 — Exploratory Data Analysis & Data Quality

**Project FORESIGHT · NorthBay Living**

Purpose: understand what the client actually gave us before modelling anything.
Three questions drive this notebook:

1. Is the data trustworthy? (what is broken, and how did we handle it)
2. What shape does demand have? (trend, seasonality, promotions, concentration)
3. What does that imply for how we forecast?

Run `python run_all.py` from the repo root first, so the processed files exist.
"""),
    code(BOOT),
    md("## 1. Raw extracts — first look\n\nProfile the extracts before any cleaning, so we can see the defects."),
    code("""raw_sales = pd.read_csv(C.RAW_DIR / "sales_daily.csv")
raw_skus = pd.read_csv(C.RAW_DIR / "sku_master.csv")
raw_inv = pd.read_csv(C.RAW_DIR / "inventory_snapshots.csv")

print("sales_daily        ", raw_sales.shape)
print("sku_master         ", raw_skus.shape)
print("inventory_snapshots", raw_inv.shape)
raw_sales.head()"""),
    code("""# Where are the defects?
print("Missing values in sales_daily:")
print(raw_sales.isna().sum()[lambda s: s > 0])
print("\\nExact duplicate rows:", raw_sales.duplicated().sum())
print("Rows with negative units:", (raw_sales["units_sold"] < 0).sum())
print("\\nCategory labels before cleaning:")
print(raw_skus["category"].value_counts())"""),
    md("""The category column shows the same categories appearing multiple times with
different casing and stray whitespace. Left alone this would split each category
into several fake categories and corrupt every category-level feature."""),
    md("## 2. Run the cleaning pipeline and read its audit log"),
    code("""import json

from src import pipeline as P

out = P.run()
weekly, skus = out["weekly"], out["skus"]

print(json.dumps(out["log"]["sales_daily"], indent=2))"""),
    code("""print("Category labels after cleaning:")
print(skus["category"].value_counts())
print("\\nWeekly grain:", weekly.shape)
weekly.head()"""),
    md("""### Why zero-filling matters

A week with no sales row means zero demand, not missing demand. If the gap is
left in place, `lag_1` silently reaches back further than one week for exactly
the SKUs that are behaving unusually — the ones we most need to get right."""),
    md("## 3. Demand shape"),
    code("""total = weekly.groupby("week_start", as_index=False)["units_sold"].sum()

fig, ax = plt.subplots(figsize=(11, 3.5))
ax.plot(total["week_start"], total["units_sold"], lw=1.8, color="#6b5bd6")
ax.set_title("Total weekly demand, all SKUs")
ax.set_ylabel("Units / week")
plt.show()"""),
    code("""# Seasonality: average demand per SKU by week of year
w = weekly.copy()
w["woy"] = w["week_start"].dt.isocalendar().week.astype(int)
by_woy = w.groupby("woy")["units_sold"].mean()

fig, ax = plt.subplots(figsize=(11, 3.5))
ax.bar(by_woy.index, by_woy.values, color="#6b5bd6", alpha=0.85)
ax.set_title("Mean units per SKU by week of year")
ax.set_xlabel("Week of year")
plt.show()

print(f"Peak week {by_woy.idxmax()} runs {by_woy.max() / by_woy.min():.1f}x the trough (week {by_woy.idxmin()})")"""),
    code("""# Revenue concentration — where should planning effort go?
by_sku = weekly.groupby("sku_id")["revenue"].sum().sort_values(ascending=False)
cum = by_sku.cumsum() / by_sku.sum()
top20 = int(len(by_sku) * 0.2)

fig, ax = plt.subplots(figsize=(9, 3.5))
ax.plot(range(1, len(cum) + 1), cum.values * 100, lw=2, color="#6b5bd6")
ax.axvline(top20, ls="--", color="#d69b45")
ax.set_title("Cumulative revenue share by SKU rank")
ax.set_ylabel("Cumulative revenue %")
plt.show()

print(f"Top 20% of SKUs = {cum.iloc[top20 - 1] * 100:.0f}% of revenue")"""),
    code("""# Promotion effect
promo = weekly[weekly["promo_flag"] == 1]["units_sold"].mean()
base = weekly[weekly["promo_flag"] == 0]["units_sold"].mean()
print(f"Normal week: {base:.2f} units/SKU")
print(f"Promo week : {promo:.2f} units/SKU  ({(promo / base - 1) * 100:.0f}% lift)")"""),
    code("""# Intermittency — does WAPE or MAPE make sense here?
zero_share = (weekly["units_sold"] == 0).mean()
cv = weekly.groupby("sku_id")["units_sold"].agg(["mean", "std"])
cv["cv"] = cv["std"] / cv["mean"].replace(0, np.nan)

print(f"Share of SKU-weeks with zero demand: {zero_share * 100:.1f}%")
print(f"Median SKU coefficient of variation: {cv['cv'].median():.2f}")
print(f"SKUs with CV > 1 (highly volatile) : {(cv['cv'] > 1).mean() * 100:.0f}%")"""),
    md("""**This settles the metric choice.** With zero-demand weeks present, MAPE is
undefined or explodes on exactly those rows. WAPE — total absolute error divided
by total actual demand — stays well-defined and weights SKUs by how much they
actually sell, which matches how the business experiences error."""),
    md("""## 4. What this means for modelling

| Finding | Modelling consequence |
|---|---|
| Strong annual seasonality (peak ≈ 2.7× trough) | Must include a same-week-last-year anchor and cyclical calendar features |
| Promotions lift demand ~80% | Promo flag must be a feature; NorthBay knows its own calendar ahead of time |
| Revenue highly concentrated | Weight attention and error review by revenue, not by SKU count |
| Lumpy, low-volume SKUs | WAPE over MAPE; prediction intervals matter more than point estimates |
| Some SKUs have thin history | Favour one pooled global model over 200 per-SKU models |
"""),
])

# -------------------------------------------------------------- 02 baseline
nb02 = notebook([
    md("""# 02 — Metric & Seasonal-Naive Baseline

**The bar the model has to clear.**

Forecasting is uniquely easy to fool yourself with. The defence is to fix the
metric and build the naive baseline *before* touching a model, then report every
later result against it on identical test rows.
"""),
    code(BOOT),
    code("""from src.forecast import build_supervised, seasonal_naive, wape, mape, bias

weekly = pd.read_csv(C.WEEKLY_PATH, parse_dates=["week_start"])
features = pd.read_csv(C.FEATURES_PATH, parse_dates=["week_start", "launch_date"])
print(f"{weekly['sku_id'].nunique()} SKUs, {weekly['week_start'].nunique()} weeks")"""),
    md("""## 1. The metric

**WAPE** = Σ|actual − forecast| ÷ Σ|actual|.

Chosen over MAPE because notebook 01 showed ~4.5% of SKU-weeks have zero demand,
where MAPE is undefined. WAPE also weights by volume, so being wrong about a
best-seller costs more than being wrong about a slow mover — which is exactly how
NorthBay experiences the error.

**Bias** (signed error) is tracked alongside it. A model can have decent WAPE
while systematically under-ordering, which would quietly cause stockouts."""),
    code("""a = np.array([10.0, 20.0, 30.0])
print("perfect forecast     WAPE:", wape(a, a))
print("10% over everywhere  WAPE:", round(wape(a, a * 1.1), 4), " bias:", round(bias(a, a * 1.1), 4))
print("10% under everywhere WAPE:", round(wape(a, a * 0.9), 4), " bias:", round(bias(a, a * 0.9), 4))"""),
    md("""## 2. The horizon

8 weeks. Long enough to cover the longest replenishment lead time in the
inventory data, short enough that the forecast is still informative."""),
    code("""inv = pd.read_csv(C.INVENTORY_PATH)
print(inv["lead_time_days"].describe())
print(f"\\nLongest lead time: {inv['lead_time_days'].max():.0f} days "
      f"= {inv['lead_time_days'].max() / 7:.1f} weeks")
print(f"Chosen horizon: {C.HORIZON_WEEKS} weeks")"""),
    md("""## 3. The baseline

Seasonal-naive: demand in the target week equals demand in the same week one
year earlier. Where that week does not exist (young SKUs), fall back to the mean
of the last 4 observed weeks — the honest fallback a human planner would use."""),
    code("""from src.pipeline import encode_categories

sup = build_supervised(encode_categories(features))
labelled = sup[sup["y"].notna()].copy()

last_week = labelled["target_week"].max()
cutoff = last_week - pd.Timedelta(weeks=C.HORIZON_WEEKS)
test = labelled[(labelled["target_week"] >= cutoff) & (labelled["origin_week"] == cutoff)]

base = seasonal_naive(test, weekly)
actual = test["y"].to_numpy()

print(f"Test rows: {len(test)}")
print(f"Baseline WAPE : {wape(actual, base):.4f}")
print(f"Baseline bias : {bias(actual, base):+.4f}")"""),
    md("""## 4. Where the baseline fails

Knowing *which* SKUs the naive forecast handles badly tells us what the model
has to add. If the baseline were uniformly good, there would be little to gain."""),
    code("""t = test.assign(base=base, err=np.abs(actual - base))
per_sku = t.groupby("sku_id").agg(actual=("y", "sum"), err=("err", "sum"))
per_sku["wape"] = per_sku["err"] / per_sku["actual"].replace(0, np.nan)

print("Worst 10 SKUs for the baseline:")
print(per_sku.sort_values("wape", ascending=False).head(10).round(3))
print("\\nBaseline WAPE by demand size:")
per_sku["bucket"] = pd.qcut(per_sku["actual"], 4, labels=["lowest", "low", "high", "highest"])
print(per_sku.groupby("bucket", observed=True)["wape"].median().round(3))"""),
    md("""**Read-through:** the baseline is weakest on low-volume and volatile SKUs,
which is where pooling information across products should help most. That is the
argument for a single global model rather than 200 per-SKU models."""),
])

# ----------------------------------------------------------------- 03 model
nb03 = notebook([
    md("""# 03 — Features, Model & Honest Backtest

Goal: beat the seasonal-naive baseline from notebook 02, without fooling
ourselves. Everything here calls the production code in `src/`, so what is
measured in this notebook is exactly what runs in the deployed service.
"""),
    code(BOOT),
    code("""from src.pipeline import FEATURE_COLS, encode_categories
from src.forecast import (
    ALL_FEATURES, build_supervised, make_model, rolling_origin_backtest,
    seasonal_naive, wape, bias,
)

weekly = pd.read_csv(C.WEEKLY_PATH, parse_dates=["week_start"])
features = pd.read_csv(C.FEATURES_PATH, parse_dates=["week_start", "launch_date"])
sup = build_supervised(encode_categories(features))
print(f"Supervised rows: {len(sup):,}   features: {len(ALL_FEATURES)}")"""),
    md("""## 1. The leakage rule

A feature for week *w* may only use data from before *w*. Verify it directly
rather than trusting the code comment."""),
    code("""one = features[features["sku_id"] == features["sku_id"].iloc[0]].sort_values("week_start")
check = one[["week_start", "units_sold", "lag_1", "roll_mean_4"]].head(8)
check["manual_lag_1"] = one["units_sold"].shift(1).head(8)
check["manual_roll_4"] = one["units_sold"].shift(1).rolling(4, min_periods=2).mean().head(8)
check.set_index("week_start").round(2)"""),
    md("""`lag_1` matches the previous week's actual and `roll_mean_4` is shifted by one
— neither touches the target week. The automated version of this check lives in
`tests/test_pipeline.py` and runs on every change."""),
    md("""## 2. Why direct multi-horizon, not recursive

A recursive forecaster predicts week 1, feeds that prediction back in as a lag,
and predicts week 2 — so by week 8 it is mostly reading its own guesses, and
errors compound. Here every row carries the horizon *h* as a feature and is
trained against genuine observed demand *h* weeks after a real origin."""),
    code("""sup[["sku_id", "origin_week", "target_week", "h", "y", "lag_1", "target_lag_52"]].head(10)"""),
    md("""## 3. Rolling-origin backtest

Never a random split. A random split lets the model train on the future of the
same series it is tested on, which inflates accuracy in a way that disappears in
production."""),
    code("""bt = rolling_origin_backtest(sup, weekly)
folds = pd.DataFrame(bt["folds"])
folds[["fold", "train_until", "test_from", "test_to", "model_wape", "baseline_wape", "model_bias"]].round(4)"""),
    code("""fig, ax = plt.subplots(figsize=(8, 3.5))
x = np.arange(len(folds))
ax.bar(x - 0.2, folds["model_wape"], 0.4, label="Model", color="#6b5bd6")
ax.bar(x + 0.2, folds["baseline_wape"], 0.4, label="Seasonal-naive", color="#d69b45")
ax.set_xticks(x); ax.set_xticklabels(folds["fold"])
ax.set_xlabel("Fold"); ax.set_ylabel("WAPE"); ax.legend()
ax.set_title("Model vs baseline, per backtest fold (lower is better)")
plt.show()

print(f"Mean model WAPE    : {bt['mean_model_wape']:.4f}")
print(f"Mean baseline WAPE : {bt['mean_baseline_wape']:.4f}")
print(f"Improvement        : {bt['improvement_vs_baseline_pct']:.1f}%")
print(f"Beats baseline     : {bt['model_beats_baseline']}")"""),
    md("""### The mistake worth recording

The first version of this model beat the baseline by only 1.5% and *lost* one
fold. The cause was a real modelling error: the model received `lag_52` relative
to the **origin** week, while the baseline used demand from the same week last
year relative to the **target** week. The model was being asked to beat a
benchmark while denied the benchmark's own information.

Adding `target_lag_52` (and a smoothed 3-week version, plus its ratio to the
current level) took the improvement to ~20% with wins in every fold. This is
recorded rather than quietly overwritten, because knowing *why* a model improved
is the difference between a result and a lucky number."""),
    md("""## 4. Which features carry the forecast

Permutation importance on a holdout — slower than a built-in attribute, but it
measures what the model actually relies on for out-of-sample accuracy."""),
    code("""from sklearn.inspection import permutation_importance

labelled = sup[sup["y"].notna() & sup["roll_mean_4"].notna()]
cut = labelled["target_week"].max() - pd.Timedelta(weeks=C.HORIZON_WEEKS)
tr, te = labelled[labelled["target_week"] < cut], labelled[labelled["target_week"] >= cut]

m = make_model()
m.fit(tr[ALL_FEATURES], tr["y"].clip(lower=0))

sample = te.sample(min(3000, len(te)), random_state=42)
imp = permutation_importance(
    m, sample[ALL_FEATURES], sample["y"], n_repeats=3, random_state=42, scoring="neg_mean_absolute_error"
)
pd.DataFrame({"feature": ALL_FEATURES, "importance": imp.importances_mean}) \\
    .sort_values("importance", ascending=False).head(15).round(4)"""),
    md("""## 5. Accuracy by horizon

Forecasts get worse further out. The ops team needs to know by how much, because
a week-8 number should be trusted less than a week-1 number."""),
    code("""te_pred = te.assign(pred=np.clip(m.predict(te[ALL_FEATURES]), 0, None))
by_h = te_pred.groupby("h").apply(
    lambda g: pd.Series({
        "model_wape": wape(g["y"].to_numpy(), g["pred"].to_numpy()),
        "bias": bias(g["y"].to_numpy(), g["pred"].to_numpy()),
    }),
    include_groups=False,
)
print(by_h.round(4))

fig, ax = plt.subplots(figsize=(7, 3))
ax.plot(by_h.index, by_h["model_wape"], marker="o", color="#6b5bd6")
ax.set_xlabel("Weeks ahead"); ax.set_ylabel("WAPE")
ax.set_title("Forecast error grows with horizon")
plt.show()"""),
    md("""## 6. Handing off

`python run_all.py` reproduces all of the above and writes the artefacts the
dashboard and the scoring service read. Risk scoring is deliberately rule-based
and lives in `src/risk.py` — see the README for the definitions."""),
])


for name, nb in [("01_eda.ipynb", nb01), ("02_baseline.ipynb", nb02), ("03_model.ipynb", nb03)]:
    (NB_DIR / name).write_text(json.dumps(nb, indent=1))
    print(f"wrote notebooks/{name}")
