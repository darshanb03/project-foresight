"""
Tests that protect the two things most likely to silently invalidate this work:
leakage in the features, and a backtest that accidentally trains on the future.

Run:
    python -m pytest tests -q
or, with no pytest installed:
    python tests/test_pipeline.py
"""


import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd

from src import config as C
from src.forecast import build_supervised, seasonal_naive, wape
from src.pipeline import build_features, encode_categories


def _toy_weekly(n_weeks: int = 120, n_skus: int = 3) -> pd.DataFrame:
    weeks = pd.date_range("2023-01-02", periods=n_weeks, freq="W-MON")
    rows = []
    for s in range(n_skus):
        for i, w in enumerate(weeks):
            rows.append(
                {
                    "sku_id": f"SKU{s:03d}",
                    "week_start": w,
                    "units_sold": float(10 + i % 7),
                    "revenue": 100.0,
                    "avg_price": 10.0,
                    "promo_days": 0,
                    "holiday_days": 0,
                    "promo_flag": 0,
                }
            )
    return pd.DataFrame(rows)


def _toy_skus(n_skus: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "sku_id": [f"SKU{s:03d}" for s in range(n_skus)],
            "category": ["Decor"] * n_skus,
            "subcategory": ["Vases"] * n_skus,
            "unit_cost": [100.0] * n_skus,
            "list_price": [200.0] * n_skus,
            "launch_date": [pd.Timestamp("2023-01-02")] * n_skus,
        }
    )


def test_lag_features_use_only_the_past():
    """lag_1 at week w must equal actual demand at week w-1, never week w."""
    weekly = _toy_weekly()
    feats = build_features(weekly, _toy_skus())
    one = feats[feats["sku_id"] == "SKU000"].sort_values("week_start").reset_index(drop=True)

    expected = one["units_sold"].shift(1)
    assert np.allclose(one["lag_1"].dropna(), expected.dropna()), "lag_1 is not a true one-week lag"
    # And it must never equal the current week where the series actually moves.
    moving = one["units_sold"] != one["units_sold"].shift(1)
    assert not (one.loc[moving, "lag_1"] == one.loc[moving, "units_sold"]).all()
    print("PASS  lag features use only the past")


def test_rolling_features_are_shifted():
    """A rolling mean at week w must not include week w's own value."""
    weekly = _toy_weekly()
    feats = build_features(weekly, _toy_skus())
    one = feats[feats["sku_id"] == "SKU000"].sort_values("week_start").reset_index(drop=True)

    manual = one["units_sold"].shift(1).rolling(4, min_periods=2).mean()
    assert np.allclose(one["roll_mean_4"].dropna(), manual.dropna()), "roll_mean_4 includes the target week"
    print("PASS  rolling features are shifted by one week")


def test_supervised_target_is_h_weeks_ahead():
    """Row with horizon h must carry the actual demand h-1 weeks after its own week."""
    weekly = _toy_weekly()
    feats = encode_categories(build_features(weekly, _toy_skus()))
    sup = build_supervised(feats, horizon=4)

    truth = weekly.set_index(["sku_id", "week_start"])["units_sold"]
    sample = sup[sup["y"].notna()].sample(200, random_state=0)
    for _, r in sample.iterrows():
        assert r["target_week"] == r["origin_week"] + pd.Timedelta(weeks=int(r["h"]) - 1)
        assert r["y"] == truth.loc[(r["sku_id"], r["target_week"])]
    print("PASS  supervised targets sit h-1 weeks after the origin")


def test_seasonal_anchor_is_one_year_old():
    """target_lag_52 must be demand 52 weeks before the target week."""
    weekly = _toy_weekly(n_weeks=160)
    feats = encode_categories(build_features(weekly, _toy_skus()))
    sup = build_supervised(feats, horizon=2)

    truth = weekly.set_index(["sku_id", "week_start"])["units_sold"]
    sample = sup[sup["target_lag_52"].notna()].sample(200, random_state=0)
    for _, r in sample.iterrows():
        key = (r["sku_id"], r["target_week"] - pd.Timedelta(weeks=C.SEASONAL_PERIOD_WEEKS))
        assert r["target_lag_52"] == truth.loc[key]
    print("PASS  seasonal anchor is exactly 52 weeks old")


def test_wape_is_sane():
    a = np.array([10.0, 20.0, 30.0])
    assert wape(a, a) == 0.0
    assert abs(wape(a, a * 1.1) - 0.1) < 1e-9
    print("PASS  WAPE behaves as defined")


def test_baseline_never_sees_the_future():
    """seasonal_naive must only ever read weeks that precede the target."""
    weekly = _toy_weekly(n_weeks=160)
    feats = encode_categories(build_features(weekly, _toy_skus()))
    sup = build_supervised(feats, horizon=2)
    # Pin to ONE target week, so "the future" is unambiguous for every row.
    t0 = sup.loc[sup["y"].notna(), "target_week"].max()
    sub = sup[(sup["y"].notna()) & (sup["target_week"] == t0)].copy()
    assert len(sub) > 0

    base = seasonal_naive(sub, weekly)
    # Corrupt every week from the target week onwards. A baseline that only
    # reads pre-target history must be completely unaffected.
    cutoff = t0
    corrupted = weekly.copy()
    corrupted.loc[corrupted["week_start"] >= cutoff, "units_sold"] = 99999.0
    base2 = seasonal_naive(sub, corrupted)

    assert np.allclose(base, base2), "baseline changed when future data changed — it is leaking"
    print("PASS  baseline reads only pre-target history")


if __name__ == "__main__":
    test_lag_features_use_only_the_past()
    test_rolling_features_are_shifted()
    test_supervised_target_is_h_weeks_ahead()
    test_seasonal_anchor_is_one_year_old()
    test_wape_is_sane()
    test_baseline_never_sees_the_future()
    print("\nAll checks passed.")
