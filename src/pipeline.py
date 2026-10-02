"""
D1 — Data pipeline.

Ingests the four client extracts, validates and cleans them, aggregates sales to
a weekly SKU grain, and engineers the features the forecast model uses.

Every cleaning decision is recorded in a data-quality report written to
reports/data_quality_report.json, so the client can audit what was changed and
why.

Run:
    python -m src.pipeline
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import config as C


# --------------------------------------------------------------------- ingest
def _read(name: str) -> pd.DataFrame:
    path = C.RAW_DIR / C.RAW_FILES[name]
    if not path.exists():
        raise FileNotFoundError(
            f"Missing extract: {path}\n"
            "Put the client extracts in data/raw/, or run "
            "`python tools/generate_synthetic_data.py` to create a stand-in."
        )
    return pd.read_csv(path)


def load_raw() -> dict[str, pd.DataFrame]:
    return {name: _read(name) for name in C.RAW_FILES}


# ---------------------------------------------------------------------- clean
def clean_sku_master(df: pd.DataFrame, log: dict) -> pd.DataFrame:
    n0 = len(df)
    df = df.drop_duplicates(subset=["sku_id"]).copy()

    # Category labels arrive with inconsistent case and stray whitespace.
    for col in ("category", "subcategory"):
        df[col] = df[col].astype(str).str.strip().str.title()

    df["launch_date"] = pd.to_datetime(df["launch_date"], errors="coerce")

    # A few SKUs are missing unit_cost. Rather than drop products the client
    # sells, impute from the category median — margin figures for those SKUs are
    # therefore approximate, which is flagged in the report.
    missing_cost = int(df["unit_cost"].isna().sum())
    df["unit_cost"] = df.groupby("category")["unit_cost"].transform(
        lambda s: s.fillna(s.median())
    )
    df["unit_cost"] = df["unit_cost"].fillna(df["unit_cost"].median())

    log["sku_master"] = {
        "rows_in": n0,
        "rows_out": len(df),
        "duplicate_sku_ids_dropped": n0 - len(df),
        "category_labels_normalised": True,
        "unit_cost_imputed_from_category_median": missing_cost,
    }
    return df


def clean_sales(df: pd.DataFrame, log: dict) -> pd.DataFrame:
    n0 = len(df)
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

    bad_dates = int(df["date"].isna().sum())
    df = df[df["date"].notna()]

    # Exact duplicate rows are extract artefacts, not real transactions.
    dupes = int(df.duplicated().sum())
    df = df.drop_duplicates()

    # Negative units are mis-booked returns. Demand cannot be negative, so we
    # floor at zero rather than delete the SKU-day (deleting would create gaps
    # the lag features would silently misread).
    negatives = int((df["units_sold"] < 0).sum())
    df["units_sold"] = df["units_sold"].clip(lower=0)

    # Missing price -> forward/backward fill within the SKU (price is sticky).
    missing_price = int(df["unit_price"].isna().sum())
    df = df.sort_values(["sku_id", "date"])
    df["unit_price"] = df.groupby("sku_id")["unit_price"].ffill().bfill()

    # Revenue is recomputed where missing, from units x price.
    missing_rev = int(df["revenue"].isna().sum())
    df["revenue"] = df["revenue"].fillna(df["units_sold"] * df["unit_price"])

    df["promo_flag"] = df["promo_flag"].fillna(0).astype(int)

    # Collapse any remaining same SKU-day rows (partial duplicates).
    collapsed_from = len(df)
    df = (
        df.groupby(["sku_id", "date"], as_index=False)
        .agg(
            units_sold=("units_sold", "sum"),
            revenue=("revenue", "sum"),
            unit_price=("unit_price", "mean"),
            promo_flag=("promo_flag", "max"),
        )
    )

    log["sales_daily"] = {
        "rows_in": n0,
        "rows_out": len(df),
        "unparseable_dates_dropped": bad_dates,
        "exact_duplicate_rows_dropped": dupes,
        "negative_units_floored_to_zero": negatives,
        "missing_unit_price_filled_within_sku": missing_price,
        "missing_revenue_recomputed": missing_rev,
        "sku_day_rows_collapsed": collapsed_from - len(df),
    }
    return df


def clean_calendar(df: pd.DataFrame, log: dict) -> pd.DataFrame:
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna()].drop_duplicates(subset=["date"])
    df["is_holiday"] = df["is_holiday"].fillna(0).astype(int)
    df["promo_event"] = df["promo_event"].fillna("None").astype(str)
    log["calendar"] = {"rows_out": len(df), "promo_event_nulls_labelled_None": True}
    return df


def clean_inventory(df: pd.DataFrame, log: dict) -> pd.DataFrame:
    n0 = len(df)
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df[df["date"].notna()].drop_duplicates(subset=["sku_id", "date"])

    missing_onhand = int(df["on_hand_units"].isna().sum())
    missing_lead = int(df["lead_time_days"].isna().sum())

    df = df.sort_values(["sku_id", "date"])
    # Stock is a level: carry the last known snapshot forward.
    df["on_hand_units"] = df.groupby("sku_id")["on_hand_units"].ffill().bfill()
    df["on_order_units"] = df["on_order_units"].fillna(0)
    # Lead time is a SKU attribute: fill within SKU, then use the global median.
    df["lead_time_days"] = df.groupby("sku_id")["lead_time_days"].ffill().bfill()
    df["lead_time_days"] = df["lead_time_days"].fillna(df["lead_time_days"].median())
    df["reorder_point"] = df["reorder_point"].fillna(0)

    for col in ("on_hand_units", "on_order_units", "lead_time_days", "reorder_point"):
        df[col] = df[col].astype(float).clip(lower=0)

    log["inventory_snapshots"] = {
        "rows_in": n0,
        "rows_out": len(df),
        "missing_on_hand_forward_filled": missing_onhand,
        "missing_lead_time_filled": missing_lead,
    }
    return df


# ------------------------------------------------------------------ aggregate
def to_weekly(sales: pd.DataFrame, calendar: pd.DataFrame) -> pd.DataFrame:
    """Aggregate daily sales to the Monday-anchored weekly grain the brief asks for."""
    df = sales.merge(calendar[["date", "is_holiday", "promo_event"]], on="date", how="left")
    df["week_start"] = df["date"] - pd.to_timedelta(df["date"].dt.dayofweek, unit="D")

    weekly = (
        df.groupby(["sku_id", "week_start"], as_index=False)
        .agg(
            units_sold=("units_sold", "sum"),
            revenue=("revenue", "sum"),
            avg_price=("unit_price", "mean"),
            promo_days=("promo_flag", "sum"),
            holiday_days=("is_holiday", "sum"),
        )
    )
    weekly["promo_flag"] = (weekly["promo_days"] > 0).astype(int)

    # Drop the final partial week so the last row is never an artificially low
    # number that the model would learn from.
    last_full = weekly["week_start"].max()
    if df["date"].max() < last_full + pd.Timedelta(days=6):
        weekly = weekly[weekly["week_start"] < last_full]

    return _fill_missing_weeks(weekly)


def _fill_missing_weeks(weekly: pd.DataFrame) -> pd.DataFrame:
    """A week with no sales row means zero demand, not missing demand.

    Leaving the gap would make lag features jump over time and quietly lie.
    """
    full_index = pd.MultiIndex.from_product(
        [weekly["sku_id"].unique(), pd.date_range(weekly["week_start"].min(),
                                                  weekly["week_start"].max(), freq="W-MON")],
        names=["sku_id", "week_start"],
    )
    out = (
        weekly.set_index(["sku_id", "week_start"])
        .reindex(full_index)
        .reset_index()
    )
    out["units_sold"] = out["units_sold"].fillna(0.0)
    out["revenue"] = out["revenue"].fillna(0.0)
    out["promo_days"] = out["promo_days"].fillna(0)
    out["holiday_days"] = out["holiday_days"].fillna(0)
    out["promo_flag"] = out["promo_flag"].fillna(0).astype(int)
    out["avg_price"] = out.groupby("sku_id")["avg_price"].ffill().bfill()
    return out.sort_values(["sku_id", "week_start"]).reset_index(drop=True)


# ------------------------------------------------------------------- features
def build_features(weekly: pd.DataFrame, skus: pd.DataFrame) -> pd.DataFrame:
    """Lags, rolling statistics, calendar and promo signals.

    LEAKAGE RULE: every feature for week *t* is computed only from data
    available strictly before *t*. All rolling windows are shifted by one week.
    """
    df = weekly.sort_values(["sku_id", "week_start"]).copy()
    g = df.groupby("sku_id")["units_sold"]

    for lag in (1, 2, 3, 4, 8, 13, 26, 52):
        df[f"lag_{lag}"] = g.shift(lag)

    shifted = g.shift(1)
    for window in (4, 8, 13, 26):
        df[f"roll_mean_{window}"] = shifted.rolling(window, min_periods=2).mean().reset_index(level=0, drop=True)
        df[f"roll_std_{window}"] = shifted.rolling(window, min_periods=2).std().reset_index(level=0, drop=True)
    df["roll_max_13"] = shifted.rolling(13, min_periods=2).max().reset_index(level=0, drop=True)

    # Trend: how does the recent month compare with the quarter before it?
    df["trend_4_13"] = df["roll_mean_4"] / df["roll_mean_13"].replace(0, np.nan)

    # Calendar features
    df["week_of_year"] = df["week_start"].dt.isocalendar().week.astype(int)
    df["month"] = df["week_start"].dt.month
    df["quarter"] = df["week_start"].dt.quarter
    # Cyclical encoding so week 52 and week 1 are adjacent to the model.
    df["woy_sin"] = np.sin(2 * np.pi * df["week_of_year"] / 52)
    df["woy_cos"] = np.cos(2 * np.pi * df["week_of_year"] / 52)

    # Promo signals (promo_flag for week t is known in advance from the promo
    # calendar, so using it contemporaneously is legitimate, not leakage).
    df["promo_last_week"] = df.groupby("sku_id")["promo_flag"].shift(1).fillna(0)
    df["weeks_since_promo"] = (
        df.groupby("sku_id")["promo_flag"]
        .transform(lambda s: s.groupby((s == 1).cumsum()).cumcount())
    )

    # Price signals
    df["price_vs_roll"] = df["avg_price"] / (
        df.groupby("sku_id")["avg_price"].shift(1).rolling(13, min_periods=2).mean()
        .reset_index(level=0, drop=True).replace(0, np.nan)
    )

    # SKU attributes
    df = df.merge(
        skus[["sku_id", "category", "subcategory", "unit_cost", "list_price", "launch_date"]],
        on="sku_id",
        how="left",
    )
    df["weeks_since_launch"] = (
        (df["week_start"] - df["launch_date"]).dt.days / 7
    ).clip(lower=0)

    df["weeks_of_history"] = df.groupby("sku_id").cumcount()

    return df


FEATURE_COLS = [
    "lag_1", "lag_2", "lag_3", "lag_4", "lag_8", "lag_13", "lag_26", "lag_52",
    "roll_mean_4", "roll_mean_8", "roll_mean_13", "roll_mean_26",
    "roll_std_4", "roll_std_8", "roll_std_13", "roll_std_26",
    "roll_max_13", "trend_4_13",
    "week_of_year", "month", "quarter", "woy_sin", "woy_cos",
    "promo_flag", "promo_last_week", "weeks_since_promo",
    "holiday_days", "price_vs_roll", "avg_price",
    "unit_cost", "list_price", "weeks_since_launch", "weeks_of_history",
    "category_code",
]


def encode_categories(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["category_code"] = df["category"].astype("category").cat.codes
    return df


# ----------------------------------------------------------------------- main
def run() -> dict[str, pd.DataFrame]:
    log: dict = {}
    raw = load_raw()

    skus = clean_sku_master(raw["sku_master"], log)
    sales = clean_sales(raw["sales_daily"], log)
    calendar = clean_calendar(raw["calendar"], log)
    inventory = clean_inventory(raw["inventory_snapshots"], log)

    weekly = to_weekly(sales, calendar)
    features = encode_categories(build_features(weekly, skus))

    # Latest stock position per SKU — what the risk layer scores against.
    latest = (
        inventory.sort_values("date")
        .groupby("sku_id", as_index=False)
        .last()
    )

    # Referential integrity check: sales for SKUs not in the master.
    orphans = sorted(set(weekly["sku_id"]) - set(skus["sku_id"]))
    log["integrity"] = {
        "sku_ids_in_sales_missing_from_master": len(orphans),
        "skus_without_inventory_snapshot": len(set(skus["sku_id"]) - set(latest["sku_id"])),
        "weekly_rows": len(weekly),
        "weeks_covered": int(weekly["week_start"].nunique()),
        "skus_covered": int(weekly["sku_id"].nunique()),
        "date_range": [str(weekly["week_start"].min().date()), str(weekly["week_start"].max().date())],
    }

    weekly.to_csv(C.WEEKLY_PATH, index=False)
    features.to_csv(C.FEATURES_PATH, index=False)
    latest.to_csv(C.INVENTORY_PATH, index=False)
    skus.to_csv(C.SKU_PATH, index=False)
    C.DQ_REPORT_PATH.write_text(json.dumps(log, indent=2, default=str))

    return {"weekly": weekly, "features": features, "inventory": latest, "skus": skus, "log": log}


if __name__ == "__main__":
    out = run()
    print(json.dumps(out["log"], indent=2, default=str))
    print(f"\nWrote:\n  {C.WEEKLY_PATH}\n  {C.FEATURES_PATH}\n  {C.INVENTORY_PATH}\n  {C.SKU_PATH}\n  {C.DQ_REPORT_PATH}")
