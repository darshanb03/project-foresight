"""
D2 — Exploratory data analysis.

Produces the figures used in the EDA memo and the executive readout, and prints
the numbers those documents quote, so no figure in the reports is hand-typed.

Run:
    python -m src.eda
"""

import json

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import config as C  # noqa: E402

FIG_DIR = C.REPORTS_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 130,
    "font.size": 9,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.25,
})

PURPLE = "#6b5bd6"
AMBER = "#d69b45"
GREEN = "#3f9e6a"
RED = "#d64545"


def run() -> dict:
    weekly = pd.read_csv(C.WEEKLY_PATH, parse_dates=["week_start"])
    skus = pd.read_csv(C.SKU_PATH, parse_dates=["launch_date"])
    df = weekly.merge(skus[["sku_id", "category", "unit_cost", "list_price"]], on="sku_id", how="left")

    findings: dict = {}

    # ------------------------------------------------- 1. total demand trend
    total = df.groupby("week_start", as_index=False)["units_sold"].sum()
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(total["week_start"], total["units_sold"], color=PURPLE, lw=1.8)
    ax.set_title("Total weekly demand across all SKUs")
    ax.set_ylabel("Units / week")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "01_total_demand.png")
    plt.close(fig)

    first_half = total.head(len(total) // 2)["units_sold"].mean()
    second_half = total.tail(len(total) // 2)["units_sold"].mean()
    findings["demand_trend_pct"] = float((second_half - first_half) / first_half * 100)

    # ---------------------------------------------- 2. concentration (Pareto)
    by_sku = (
        df.groupby("sku_id", as_index=False)["revenue"].sum().sort_values("revenue", ascending=False)
    )
    by_sku["cum_share"] = by_sku["revenue"].cumsum() / by_sku["revenue"].sum()
    top20_idx = max(int(len(by_sku) * 0.2), 1)
    findings["top_20pct_skus_revenue_share"] = float(by_sku["cum_share"].iloc[top20_idx - 1] * 100)

    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(range(1, len(by_sku) + 1), by_sku["cum_share"] * 100, color=PURPLE, lw=2)
    ax.axvline(top20_idx, color=AMBER, ls="--", lw=1.2)
    ax.axhline(findings["top_20pct_skus_revenue_share"], color=AMBER, ls="--", lw=1.2)
    ax.set_title("Revenue concentration — cumulative share by SKU rank")
    ax.set_xlabel("SKUs ranked by revenue")
    ax.set_ylabel("Cumulative revenue %")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "02_revenue_concentration.png")
    plt.close(fig)

    # ------------------------------------------------------- 3. dead stock
    recent = df[df["week_start"] > df["week_start"].max() - pd.Timedelta(weeks=13)]
    recent_units = recent.groupby("sku_id")["units_sold"].sum()
    dead = recent_units[recent_units <= 1]
    findings["dead_sku_count"] = int(len(dead))
    findings["dead_sku_pct"] = float(len(dead) / len(recent_units) * 100)

    # -------------------------------------------------- 4. weekly seasonality
    seasonal = df.copy()
    seasonal["woy"] = seasonal["week_start"].dt.isocalendar().week.astype(int)
    by_woy = seasonal.groupby("woy", as_index=False)["units_sold"].mean()
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.bar(by_woy["woy"], by_woy["units_sold"], color=PURPLE, alpha=0.85)
    ax.set_title("Average demand per SKU by week of year (seasonality)")
    ax.set_xlabel("Week of year")
    ax.set_ylabel("Mean units / SKU")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "03_seasonality.png")
    plt.close(fig)

    peak = by_woy.loc[by_woy["units_sold"].idxmax()]
    trough = by_woy.loc[by_woy["units_sold"].idxmin()]
    findings["peak_week"] = int(peak["woy"])
    findings["trough_week"] = int(trough["woy"])
    findings["peak_vs_trough_ratio"] = float(peak["units_sold"] / max(trough["units_sold"], 1e-9))

    # ---------------------------------------------------------- 5. promo lift
    promo_mean = df[df["promo_flag"] == 1]["units_sold"].mean()
    base_mean = df[df["promo_flag"] == 0]["units_sold"].mean()
    findings["promo_lift_pct"] = float((promo_mean - base_mean) / base_mean * 100)

    fig, ax = plt.subplots(figsize=(4.5, 3))
    ax.bar(["Normal week", "Promo week"], [base_mean, promo_mean], color=[GREEN, AMBER])
    ax.set_title("Mean weekly units per SKU")
    ax.set_ylabel("Units")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "04_promo_lift.png")
    plt.close(fig)

    # ------------------------------------------------------- 6. intermittency
    zero_share = (df["units_sold"] == 0).mean()
    findings["zero_demand_week_share_pct"] = float(zero_share * 100)

    sku_cv = (
        df.groupby("sku_id")["units_sold"]
        .agg(["mean", "std"])
        .assign(cv=lambda x: x["std"] / x["mean"].replace(0, np.nan))
    )
    findings["median_sku_cv"] = float(sku_cv["cv"].median())
    findings["volatile_sku_pct"] = float((sku_cv["cv"] > 1).mean() * 100)

    # ----------------------------------------------------- 7. category split
    by_cat = df.groupby("category", as_index=False).agg(
        revenue=("revenue", "sum"), units=("units_sold", "sum")
    ).sort_values("revenue", ascending=False)
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.barh(by_cat["category"], by_cat["revenue"] / 1e5, color=PURPLE)
    ax.set_title("Revenue by category")
    ax.set_xlabel("Revenue (₹ lakh)")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "05_category_revenue.png")
    plt.close(fig)
    findings["top_category"] = str(by_cat.iloc[0]["category"])
    findings["top_category_revenue_share_pct"] = float(
        by_cat.iloc[0]["revenue"] / by_cat["revenue"].sum() * 100
    )

    # ------------------------------------------------- 8. history sufficiency
    weeks_live = df[df["units_sold"] > 0].groupby("sku_id")["week_start"].nunique()
    findings["skus_under_12_weeks_of_sales"] = int((weeks_live < 12).sum())

    (C.REPORTS_DIR / "eda_findings.json").write_text(json.dumps(findings, indent=2))
    return findings


if __name__ == "__main__":
    f = run()
    print("--- EDA findings ---")
    for k, v in f.items():
        print(f"  {k:<38} {v if isinstance(v, (int, str)) else f'{v:.2f}'}")
    print(f"\nFigures -> {FIG_DIR}")
