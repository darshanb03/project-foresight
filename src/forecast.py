"""
D3 — Demand forecast model.

Design decisions, and why:

1. DIRECT MULTI-HORIZON, NOT RECURSIVE.
   We build one global model that takes the features known at an origin week
   plus the horizon h (1..8), and predicts demand h weeks ahead. Recursive
   forecasting (predict week 1, feed it back as a lag, predict week 2) compounds
   its own errors and makes leakage easy to introduce by accident. Direct
   multi-horizon keeps every prediction traceable to real observed history.

2. ONE GLOBAL MODEL, NOT 200 PER-SKU MODELS.
   Many SKUs have thin history. A global model pools the seasonal signal across
   200 products and still separates them through lag/level features, which is
   standard practice for retail demand forecasting at this scale.

3. LEAKAGE GUARD.
   Features for an origin week w are computed strictly from weeks before w (see
   pipeline.build_features). The only target-week information used is the
   calendar and the promotion flag, both of which NorthBay genuinely knows in
   advance because they plan their own promo calendar.

4. THE BASELINE IS THE BAR.
   Seasonal-naive (demand = same week last year) is computed on exactly the same
   test rows. If the model does not beat it on rolling-origin backtest, that is
   reported as the finding, not hidden.

Run:
    python -m src.forecast
"""


import json

import numpy as np
import pandas as pd

from sklearn.ensemble import HistGradientBoostingRegressor

from . import config as C
from .pipeline import FEATURE_COLS


ORIGIN_FEATURES = FEATURE_COLS
TARGET_FEATURES = [
    "h", "target_woy_sin", "target_woy_cos", "target_promo_flag", "target_holiday_days",
    # Demand in the SAME WEEK LAST YEAR, anchored on the target week (not the
    # origin week). This is observed history, so it is not leakage, and it is
    # exactly the information the seasonal-naive baseline uses. Without it the
    # model is handicapped against its own benchmark.
    "target_lag_52", "target_lag_52_roll3", "target_seasonal_ratio",
]
ALL_FEATURES = ORIGIN_FEATURES + TARGET_FEATURES


# ------------------------------------------------------------------- metrics
def wape(actual: np.ndarray, pred: np.ndarray) -> float:
    """Weighted Absolute Percentage Error: total error / total demand.

    Chosen over MAPE because many SKUs have weeks of zero demand, where MAPE is
    undefined or explodes.
    """
    denom = np.abs(actual).sum()
    if denom == 0:
        return float("nan")
    return float(np.abs(actual - pred).sum() / denom)


def mape(actual: np.ndarray, pred: np.ndarray) -> float:
    mask = actual != 0
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.abs((actual[mask] - pred[mask]) / actual[mask])))


def bias(actual: np.ndarray, pred: np.ndarray) -> float:
    """Signed mean error. Positive = the model over-forecasts."""
    denom = np.abs(actual).sum()
    if denom == 0:
        return float("nan")
    return float((pred - actual).sum() / denom)


# ------------------------------------------------------- supervised framing
def build_supervised(features: pd.DataFrame, horizon: int = C.HORIZON_WEEKS) -> pd.DataFrame:
    """Turn the weekly feature table into (origin, horizon) -> target rows.

    A row says: standing at the end of week `origin_week` knowing only the past,
    predict demand in week `target_week`, which is `h` weeks later.
    """
    df = features.sort_values(["sku_id", "week_start"]).copy()
    frames = []

    for h in range(1, horizon + 1):
        block = df.copy()
        block["h"] = h
        block["origin_week"] = block["week_start"]
        # Target is h-1 weeks after this row's own week (h=1 -> this week).
        block["target_week"] = block["week_start"] + pd.Timedelta(weeks=h - 1)

        target = df[["sku_id", "week_start", "units_sold", "promo_flag", "holiday_days"]].rename(
            columns={
                "week_start": "target_week",
                "units_sold": "y",
                "promo_flag": "target_promo_flag",
                "holiday_days": "target_holiday_days",
            }
        )
        block = block.merge(target, on=["sku_id", "target_week"], how="left")

        woy = block["target_week"].dt.isocalendar().week.astype(int)
        block["target_woy_sin"] = np.sin(2 * np.pi * woy / 52)
        block["target_woy_cos"] = np.cos(2 * np.pi * woy / 52)

        # Seasonal anchor: demand in the same week one year before the target.
        # Also a 3-week smoothed version, because a single week last year is
        # noisy for low-volume SKUs.
        ly = df[["sku_id", "week_start", "units_sold"]].copy()
        ly["target_week"] = ly["week_start"] + pd.Timedelta(weeks=C.SEASONAL_PERIOD_WEEKS)
        ly = ly.sort_values(["sku_id", "week_start"])
        ly["ly_roll3"] = (
            ly.groupby("sku_id")["units_sold"]
            .transform(lambda s: s.rolling(3, min_periods=1, center=True).mean())
        )
        ly = ly[["sku_id", "target_week", "units_sold", "ly_roll3"]].rename(
            columns={"units_sold": "target_lag_52", "ly_roll3": "target_lag_52_roll3"}
        )
        block = block.merge(ly, on=["sku_id", "target_week"], how="left")

        # How does the level a year ago compare with the level now? Lets the
        # model scale last year's seasonal shape to this year's demand.
        block["target_seasonal_ratio"] = block["target_lag_52_roll3"] / block["roll_mean_13"].replace(0, np.nan)

        frames.append(block)

    out = pd.concat(frames, ignore_index=True)
    return out


def seasonal_naive(sup: pd.DataFrame, weekly: pd.DataFrame) -> pd.Series:
    """Baseline: demand in the target week equals demand 52 weeks earlier.

    Where that week does not exist (young SKUs, short history) we fall back to
    the mean of the 4 weeks before the origin — the honest naive fallback a
    planner would use.
    """
    hist = weekly[["sku_id", "week_start", "units_sold"]].rename(
        columns={"week_start": "target_week", "units_sold": "sn"}
    )
    hist["target_week"] = hist["target_week"] + pd.Timedelta(weeks=C.SEASONAL_PERIOD_WEEKS)
    merged = sup[["sku_id", "target_week", "roll_mean_4"]].merge(
        hist, on=["sku_id", "target_week"], how="left"
    )
    return merged["sn"].fillna(merged["roll_mean_4"]).fillna(0.0).to_numpy()


# ------------------------------------------------------------------- model
def make_model() -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="poisson",           # demand is non-negative count data
        max_iter=400,
        learning_rate=0.06,
        max_depth=6,
        min_samples_leaf=40,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.1,
        random_state=C.RANDOM_SEED,
    )


def _fit_predict(train: pd.DataFrame, test: pd.DataFrame) -> np.ndarray:
    model = make_model()
    X_train = train[ALL_FEATURES]
    y_train = train["y"].clip(lower=0)
    model.fit(X_train, y_train)
    return np.clip(model.predict(test[ALL_FEATURES]), 0, None)


# --------------------------------------------------------------- backtesting
def rolling_origin_backtest(
    sup: pd.DataFrame,
    weekly: pd.DataFrame,
    folds: int = C.BACKTEST_FOLDS,
    step: int = C.BACKTEST_STEP_WEEKS,
) -> dict:
    """Repeatedly train on the past, test on the next `horizon` weeks.

    Never a random split: that would let the model see the future of a series it
    is being tested on, which is the classic way forecasting results get faked.
    """
    sup = sup[sup["y"].notna()].copy()
    last_week = sup["target_week"].max()

    results = []
    for fold in range(folds):
        # Origin walks backwards from the end of history.
        cutoff = last_week - pd.Timedelta(weeks=C.HORIZON_WEEKS + fold * step)
        train = sup[sup["target_week"] < cutoff]
        test = sup[
            (sup["target_week"] >= cutoff)
            & (sup["target_week"] < cutoff + pd.Timedelta(weeks=C.HORIZON_WEEKS))
            & (sup["origin_week"] == cutoff)  # single origin per fold = clean horizon curve
        ]
        if len(test) == 0 or len(train) < 5000:
            continue

        # Drop training rows with no usable level feature at all.
        train = train[train["roll_mean_4"].notna()]

        pred = _fit_predict(train, test)
        base = seasonal_naive(test, weekly)
        actual = test["y"].to_numpy()

        results.append(
            {
                "fold": fold + 1,
                "train_until": str((cutoff - pd.Timedelta(weeks=1)).date()),
                "test_from": str(cutoff.date()),
                "test_to": str((cutoff + pd.Timedelta(weeks=C.HORIZON_WEEKS - 1)).date()),
                "n_test_rows": int(len(test)),
                "model_wape": wape(actual, pred),
                "baseline_wape": wape(actual, base),
                "model_mape": mape(actual, pred),
                "model_bias": bias(actual, pred),
                "baseline_bias": bias(actual, base),
            }
        )

    if not results:
        raise RuntimeError("Backtest produced no folds — check history length.")

    m = float(np.mean([r["model_wape"] for r in results]))
    b = float(np.mean([r["baseline_wape"] for r in results]))
    summary = {
        "folds": results,
        "mean_model_wape": m,
        "mean_baseline_wape": b,
        "improvement_vs_baseline_pct": float((b - m) / b * 100) if b else float("nan"),
        "model_beats_baseline": bool(m < b),
        "horizon_weeks": C.HORIZON_WEEKS,
        "metric": "WAPE (lower is better)",
    }
    return summary


# ----------------------------------------------------------- future forecast
def forecast_future(sup: pd.DataFrame, weekly: pd.DataFrame) -> tuple[pd.DataFrame, HistGradientBoostingRegressor]:
    """Train on all usable history, then forecast the next HORIZON_WEEKS.

    Prediction intervals come from the empirical distribution of residuals on a
    held-out final fold, per horizon — an honest estimate of how wrong this
    model actually was at that lead time, rather than a theoretical formula.
    """
    labelled = sup[sup["y"].notna() & sup["roll_mean_4"].notna()]
    last_week = weekly["week_start"].max()

    # Residual quantiles per horizon, measured on a genuine holdout.
    holdout_cutoff = last_week - pd.Timedelta(weeks=C.HORIZON_WEEKS)
    tr = labelled[labelled["target_week"] < holdout_cutoff]
    te = labelled[labelled["target_week"] >= holdout_cutoff]
    resid_q: dict[int, tuple[float, float]] = {}
    if len(te) > 0 and len(tr) > 5000:
        p = _fit_predict(tr, te)
        te = te.assign(resid=te["y"].to_numpy() - p)
        for h, grp in te.groupby("h"):
            resid_q[int(h)] = (float(grp["resid"].quantile(0.10)), float(grp["resid"].quantile(0.90)))

    # Final model on everything.
    model = make_model()
    model.fit(labelled[ALL_FEATURES], labelled["y"].clip(lower=0))

    # Future rows: origin = the last complete week, horizons 1..H.
    future = sup[(sup["origin_week"] == last_week)].copy()
    future = future[future["target_week"] > last_week - pd.Timedelta(weeks=1)]
    future["forecast_units"] = np.clip(model.predict(future[ALL_FEATURES]), 0, None)
    future["baseline_units"] = seasonal_naive(future, weekly)

    lo = future["h"].map(lambda h: resid_q.get(int(h), (0.0, 0.0))[0])
    hi = future["h"].map(lambda h: resid_q.get(int(h), (0.0, 0.0))[1])
    future["forecast_lo"] = np.clip(future["forecast_units"] + lo, 0, None)
    future["forecast_hi"] = np.clip(future["forecast_units"] + hi, 0, None)

    cols = [
        "sku_id", "category", "subcategory", "origin_week", "target_week", "h",
        "forecast_units", "forecast_lo", "forecast_hi", "baseline_units",
        "avg_price", "unit_cost", "list_price",
    ]
    return future[cols].sort_values(["sku_id", "h"]).reset_index(drop=True), model


# ------------------------------------------------------------------- runner
def run() -> dict:
    weekly = pd.read_csv(C.WEEKLY_PATH, parse_dates=["week_start"])
    features = pd.read_csv(C.FEATURES_PATH, parse_dates=["week_start", "launch_date"])

    sup = build_supervised(features)

    print("Running rolling-origin backtest...")
    bt = rolling_origin_backtest(sup, weekly)
    C.BACKTEST_PATH.write_text(json.dumps(bt, indent=2))

    print("Fitting final model and forecasting...")
    fc, _ = forecast_future(sup, weekly)
    fc.to_csv(C.FORECAST_PATH, index=False)

    return {"backtest": bt, "forecast": fc}


if __name__ == "__main__":
    out = run()
    bt = out["backtest"]
    print("\n--- Backtest (rolling origin) ---")
    for f in bt["folds"]:
        print(
            f"  fold {f['fold']}  test {f['test_from']} -> {f['test_to']}  "
            f"model WAPE {f['model_wape']:.3f}  baseline WAPE {f['baseline_wape']:.3f}"
        )
    print(f"\n  mean model WAPE    : {bt['mean_model_wape']:.4f}")
    print(f"  mean baseline WAPE : {bt['mean_baseline_wape']:.4f}")
    print(f"  improvement        : {bt['improvement_vs_baseline_pct']:.1f}%")
    print(f"  beats baseline     : {bt['model_beats_baseline']}")
    print(f"\nForecast rows: {len(out['forecast'])} -> {C.FORECAST_PATH}")
