"""
D4 — Risk scoring & decisioning.

Deliberately rule-based, not a second machine-learning model. The ops team has
to trust and override these calls, so every number below can be explained in one
sentence to a non-technical planner:

  stockout risk   how much of the stock I need for the lead time am I short by?
  overstock risk  how many weeks of demand am I sitting on beyond what's sane?

Both are scaled to 0-1 so they can be plotted on the decisioning grid in
Section 08 of the brief.

Run:
    python -m src.risk
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def _weeks_of_lead_time(lead_days: pd.Series) -> pd.Series:
    return (lead_days / 7.0).clip(lower=1.0)


def score(forecast: pd.DataFrame, inventory: pd.DataFrame, skus: pd.DataFrame) -> pd.DataFrame:
    """Combine the forecast with the latest stock position into one row per SKU."""
    fc = forecast.copy()

    # Total and average demand over the full forecast horizon.
    horizon = (
        fc.groupby("sku_id")
        .agg(
            horizon_demand=("forecast_units", "sum"),
            horizon_demand_hi=("forecast_hi", "sum"),
            avg_weekly_demand=("forecast_units", "mean"),
            weeks=("h", "max"),
        )
        .reset_index()
    )

    inv = inventory[
        ["sku_id", "on_hand_units", "on_order_units", "lead_time_days", "reorder_point", "date"]
    ].rename(columns={"date": "stock_as_of"})

    df = horizon.merge(inv, on="sku_id", how="left").merge(
        skus[["sku_id", "category", "subcategory", "unit_cost", "list_price"]],
        on="sku_id",
        how="left",
    )

    # Any SKU with no stock snapshot is treated as zero stock and flagged, not
    # silently dropped — a missing snapshot is itself an operational problem.
    df["missing_stock_data"] = df["on_hand_units"].isna()
    df[["on_hand_units", "on_order_units"]] = df[["on_hand_units", "on_order_units"]].fillna(0.0)
    df["lead_time_days"] = df["lead_time_days"].fillna(df["lead_time_days"].median())

    # ---------------------------------------------------------- stockout risk
    lt_weeks = _weeks_of_lead_time(df["lead_time_days"])
    df["lead_time_weeks"] = lt_weeks
    # Demand we expect to face before a replenishment order could arrive.
    df["lead_time_demand"] = df["avg_weekly_demand"] * lt_weeks
    # Plus a safety buffer, because forecasts are wrong in both directions.
    df["required_units"] = df["lead_time_demand"] * (1 + C.SAFETY_STOCK_FACTOR)
    df["available_units"] = df["on_hand_units"] + df["on_order_units"]

    shortfall = (df["required_units"] - df["available_units"]).clip(lower=0)
    df["shortfall_units"] = shortfall
    df["stockout_risk"] = np.where(
        df["required_units"] > 0,
        (shortfall / df["required_units"]).clip(0, 1),
        0.0,
    )

    # --------------------------------------------------------- overstock risk
    # How many weeks of forecast demand does current on-hand stock cover?
    df["weeks_of_cover"] = np.where(
        df["avg_weekly_demand"] > 0,
        df["on_hand_units"] / df["avg_weekly_demand"],
        np.where(df["on_hand_units"] > 0, 999.0, 0.0),
    )
    excess_weeks = (df["weeks_of_cover"] - C.OVERSTOCK_COVER_WEEKS).clip(lower=0)
    df["overstock_risk"] = (excess_weeks / C.OVERSTOCK_COVER_WEEKS).clip(0, 1)
    df["excess_units"] = (
        df["on_hand_units"] - df["avg_weekly_demand"] * C.OVERSTOCK_COVER_WEEKS
    ).clip(lower=0)

    # ------------------------------------------------------------ rupee impact
    # Sales at risk: units we expect to be unable to sell, at their selling price.
    df["sales_at_risk_inr"] = (df["shortfall_units"] * df["list_price"]).round(2)
    # Capital locked: excess stock valued at what it cost to buy.
    df["capital_locked_inr"] = (df["excess_units"] * df["unit_cost"]).round(2)
    df["value_at_stake_inr"] = df["sales_at_risk_inr"] + df["capital_locked_inr"]

    # ------------------------------------------------------------- decisioning
    hi_out = df["stockout_risk"] >= C.RISK_THRESHOLD
    hi_over = df["overstock_risk"] >= C.RISK_THRESHOLD

    df["quadrant"] = np.select(
        [hi_out & ~hi_over, ~hi_out & hi_over, hi_out & hi_over],
        ["Reorder now", "Markdown / clear", "Watch / volatile"],
        default="Healthy",
    )
    df["recommended_action"] = df["quadrant"].map(
        {
            "Reorder now": "Raise a replenishment order before stock runs out.",
            "Markdown / clear": "Promote or discount to free up capital.",
            "Watch / volatile": "Investigate — demand is erratic; review manually.",
            "Healthy": "No action needed; leave as is.",
        }
    )

    # Suggested order quantity: cover the horizon plus safety, net of what is
    # already on hand or on order.
    df["suggested_order_units"] = np.ceil(
        (df["horizon_demand"] * (1 + C.SAFETY_STOCK_FACTOR) - df["available_units"]).clip(lower=0)
    )
    df.loc[df["quadrant"] != "Reorder now", "suggested_order_units"] = 0

    # A one-line, human-readable justification for every row. The brief demands
    # transparency, and a planner who cannot see the reasoning will not act.
    df["why"] = df.apply(_explain, axis=1)

    df["priority_rank"] = df["value_at_stake_inr"].rank(ascending=False, method="min").astype(int)

    cols = [
        "sku_id", "category", "subcategory", "quadrant", "recommended_action", "why",
        "stockout_risk", "overstock_risk",
        "on_hand_units", "on_order_units", "available_units",
        "avg_weekly_demand", "horizon_demand", "lead_time_days", "lead_time_weeks",
        "lead_time_demand", "required_units", "shortfall_units",
        "weeks_of_cover", "excess_units", "suggested_order_units",
        "unit_cost", "list_price",
        "sales_at_risk_inr", "capital_locked_inr", "value_at_stake_inr",
        "priority_rank", "missing_stock_data", "stock_as_of",
    ]
    return df[cols].sort_values("priority_rank").reset_index(drop=True)


def _explain(row: pd.Series) -> str:
    q = row["quadrant"]
    if q == "Reorder now":
        return (
            f"Expect ~{row['lead_time_demand']:.0f} units over the {row['lead_time_weeks']:.0f}-week "
            f"lead time but only {row['available_units']:.0f} are available — short by "
            f"{row['shortfall_units']:.0f} units (₹{row['sales_at_risk_inr']:,.0f} of sales at risk)."
        )
    if q == "Markdown / clear":
        return (
            f"{row['on_hand_units']:.0f} units on hand covers {row['weeks_of_cover']:.0f} weeks of "
            f"forecast demand — {row['excess_units']:.0f} units beyond a sensible "
            f"{C.OVERSTOCK_COVER_WEEKS:.0f}-week cover, locking ₹{row['capital_locked_inr']:,.0f}."
        )
    if q == "Watch / volatile":
        return (
            "Scores high on both stockout and overstock — demand is erratic relative to stock "
            "position; review manually before ordering."
        )
    return (
        f"Stock covers {row['weeks_of_cover']:.0f} weeks against forecast demand of "
        f"{row['avg_weekly_demand']:.1f} units/week. Within tolerance."
    )


def summarise(risk: pd.DataFrame) -> dict:
    """Headline numbers for the executive readout."""
    counts = risk["quadrant"].value_counts().to_dict()
    return {
        "skus_scored": int(len(risk)),
        "quadrant_counts": {k: int(v) for k, v in counts.items()},
        "total_sales_at_risk_inr": float(risk["sales_at_risk_inr"].sum()),
        "total_capital_locked_inr": float(risk["capital_locked_inr"].sum()),
        "total_value_at_stake_inr": float(risk["value_at_stake_inr"].sum()),
        "top_10_value_share_pct": float(
            risk.nlargest(10, "value_at_stake_inr")["value_at_stake_inr"].sum()
            / max(risk["value_at_stake_inr"].sum(), 1e-9) * 100
        ),
        "skus_missing_stock_data": int(risk["missing_stock_data"].sum()),
    }


def run() -> pd.DataFrame:
    forecast = pd.read_csv(C.FORECAST_PATH, parse_dates=["origin_week", "target_week"])
    inventory = pd.read_csv(C.INVENTORY_PATH, parse_dates=["date"])
    skus = pd.read_csv(C.SKU_PATH, parse_dates=["launch_date"])

    risk = score(forecast, inventory, skus)
    risk.to_csv(C.RISK_PATH, index=False)
    return risk


if __name__ == "__main__":
    r = run()
    s = summarise(r)
    print("--- Risk summary ---")
    for k, v in s["quadrant_counts"].items():
        print(f"  {k:<18} {v:>4} SKUs")
    print(f"\n  Sales at risk (stockouts) : Rs {s['total_sales_at_risk_inr']:,.0f}")
    print(f"  Capital locked (overstock): Rs {s['total_capital_locked_inr']:,.0f}")
    print(f"  Total value at stake      : Rs {s['total_value_at_stake_inr']:,.0f}")
    print(f"  Top 10 SKUs are {s['top_10_value_share_pct']:.0f}% of it")
    print(f"\nWrote {C.RISK_PATH}")
