"""
Generate a synthetic NorthBay Living dataset matching the schema in Appendix A
of the Project FORESIGHT brief.

IMPORTANT
---------
The engagement brief states that client extracts are provided. This generator
exists only so the repository is runnable end-to-end before those extracts are
dropped into data/raw/. If you have been given the real extracts, put them in
data/raw/ with the same four filenames and do NOT run this script.

The generated data is deliberately imperfect (missing values, duplicate rows,
inconsistent category labels, a few negative/zero-price rows) because cleaning
them is part of the engagement.

Usage:
    python tools/generate_synthetic_data.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pathlib import Path

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
SEED = 42

START = "2024-01-01"
END = "2025-12-31"
N_SKUS = 200

CATEGORIES = {
    "Furnishings": ["Cushions", "Throws", "Rugs"],
    "Decor": ["Candles", "Vases", "Wall Art"],
    "Small Appliances": ["Kettles", "Blenders", "Lamps"],
    "Kitchen": ["Cookware", "Storage", "Tableware"],
}

# Named promo events -> (month, day span)
PROMO_EVENTS = {
    "New Year Sale": ("01-01", "01-07"),
    "Spring Refresh": ("03-15", "03-22"),
    "Mid Year Sale": ("06-20", "06-30"),
    "Independence Sale": ("08-12", "08-18"),
    "Festive Diwali": ("10-25", "11-05"),
    "Black Friday": ("11-24", "11-30"),
    "Year End Clearance": ("12-26", "12-31"),
}

HOLIDAYS = ["01-01", "01-26", "03-08", "08-15", "10-02", "11-01", "12-25"]


def build_calendar(rng: np.random.Generator) -> pd.DataFrame:
    dates = pd.date_range(START, END, freq="D")
    cal = pd.DataFrame({"date": dates})
    cal["week"] = cal["date"].dt.isocalendar().week.astype(int)
    cal["month"] = cal["date"].dt.month
    cal["season"] = cal["month"].map(
        lambda m: "Winter" if m in (12, 1, 2)
        else "Spring" if m in (3, 4, 5)
        else "Summer" if m in (6, 7, 8)
        else "Autumn"
    )
    md = cal["date"].dt.strftime("%m-%d")
    cal["is_holiday"] = md.isin(HOLIDAYS).astype(int)

    cal["promo_event"] = pd.Series([pd.NA] * len(cal), dtype="object")
    for name, (start_md, end_md) in PROMO_EVENTS.items():
        mask = (md >= start_md) & (md <= end_md)
        cal.loc[mask, "promo_event"] = name
    return cal


def build_sku_master(rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    cats = list(CATEGORIES.items())
    for i in range(N_SKUS):
        cat, subs = cats[i % len(cats)]
        sub = subs[rng.integers(0, len(subs))]
        unit_cost = float(np.round(rng.uniform(80, 2500), 2))
        margin = rng.uniform(1.4, 2.6)
        rows.append(
            {
                "sku_id": f"SKU{i + 1:04d}",
                "category": cat,
                "subcategory": sub,
                # ~12% of SKUs launch mid-history -> sparse history, a real risk
                "launch_date": (
                    pd.Timestamp(START)
                    + pd.Timedelta(days=int(rng.integers(0, 420)) if rng.random() < 0.12 else 0)
                ),
                "unit_cost": unit_cost,
                "list_price": float(np.round(unit_cost * margin, 2)),
            }
        )
    return pd.DataFrame(rows)


def build_sales(cal: pd.DataFrame, skus: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Demand = base level x trend x weekly seasonality x annual seasonality x promo lift + noise."""
    frames = []
    day_index = np.arange(len(cal))
    dow = cal["date"].dt.dayofweek.to_numpy()
    doy = cal["date"].dt.dayofyear.to_numpy()
    on_promo = cal["promo_event"].notna().to_numpy()
    holiday = cal["is_holiday"].to_numpy().astype(bool)

    for _, sku in skus.iterrows():
        # popularity is lognormal: a few best sellers, a long tail of slow movers
        base = float(np.exp(rng.normal(1.5, 0.9)))
        trend = 1.0 + rng.normal(0.0, 0.25) * (day_index / len(cal))
        weekly = 1.0 + 0.35 * np.sin((dow + rng.integers(0, 7)) / 7 * 2 * np.pi)
        annual_amp = rng.uniform(0.15, 0.55)
        annual = 1.0 + annual_amp * np.sin((doy / 365.0) * 2 * np.pi + rng.uniform(0, 2 * np.pi))

        promo_lift = np.where(on_promo, rng.uniform(1.6, 3.2), 1.0)
        holiday_lift = np.where(holiday, rng.uniform(1.1, 1.5), 1.0)

        mu = base * trend * weekly * annual * promo_lift * holiday_lift
        mu = np.clip(mu, 0.02, None)
        units = rng.poisson(mu)

        # SKUs launched later have no sales before launch
        launched = cal["date"].to_numpy() >= np.datetime64(sku["launch_date"])
        units = np.where(launched, units, 0)

        discount = np.where(on_promo, rng.uniform(0.70, 0.90), 1.0)
        unit_price = np.round(sku["list_price"] * discount, 2)

        frames.append(
            pd.DataFrame(
                {
                    "date": cal["date"].to_numpy(),
                    "sku_id": sku["sku_id"],
                    "units_sold": units,
                    "unit_price": unit_price,
                    "revenue": np.round(units * unit_price, 2),
                    "promo_flag": on_promo.astype(int),
                }
            )
        )

    sales = pd.concat(frames, ignore_index=True)
    return sales[sales["units_sold"].notna()].reset_index(drop=True)


def build_inventory(sales: pd.DataFrame, skus: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Weekly stock snapshots, loosely (and imperfectly) tracking recent demand."""
    last_date = sales["date"].max()
    snap_dates = pd.date_range(last_date - pd.Timedelta(days=180), last_date, freq="W-MON")

    recent = sales[sales["date"] > last_date - pd.Timedelta(days=90)]
    avg_daily = recent.groupby("sku_id")["units_sold"].mean()

    rows = []
    for sku_id in skus["sku_id"]:
        daily = float(avg_daily.get(sku_id, 0.5))
        lead_time = int(rng.choice([7, 10, 14, 21, 30]))
        reorder_point = int(np.ceil(daily * lead_time * rng.uniform(1.0, 1.5)))
        # cover_weeks decides whether this SKU ends up healthy / short / overstocked
        cover_weeks = rng.choice([1, 2, 4, 6, 10, 16], p=[0.12, 0.18, 0.25, 0.20, 0.15, 0.10])
        for d in snap_dates:
            on_hand = max(0, int(rng.normal(daily * 7 * cover_weeks, daily * 4)))
            on_order = int(max(0, rng.normal(daily * lead_time * 0.5, daily * 3))) if rng.random() < 0.45 else 0
            rows.append(
                {
                    "date": d,
                    "sku_id": sku_id,
                    "on_hand_units": on_hand,
                    "on_order_units": on_order,
                    "lead_time_days": lead_time,
                    "reorder_point": reorder_point,
                }
            )
    return pd.DataFrame(rows)


def dirty(df: pd.DataFrame, rng: np.random.Generator, name: str) -> pd.DataFrame:
    """Introduce the kind of defects a real client extract would contain."""
    df = df.copy()

    if name == "sales_daily":
        # missing revenue values
        idx = rng.choice(df.index, size=int(len(df) * 0.008), replace=False)
        df.loc[idx, "revenue"] = np.nan
        # missing prices
        idx = rng.choice(df.index, size=int(len(df) * 0.004), replace=False)
        df.loc[idx, "unit_price"] = np.nan
        # a handful of impossible negative quantities (returns booked wrongly)
        idx = rng.choice(df.index, size=200, replace=False)
        df.loc[idx, "units_sold"] = -df.loc[idx, "units_sold"].abs() - 1
        # duplicate rows
        dup = df.sample(n=500, random_state=1)
        df = pd.concat([df, dup], ignore_index=True)

    if name == "sku_master":
        # inconsistent category labels
        idx = rng.choice(df.index, size=25, replace=False)
        df.loc[idx, "category"] = df.loc[idx, "category"].str.upper()
        idx = rng.choice(df.index, size=15, replace=False)
        df.loc[idx, "category"] = " " + df.loc[idx, "category"].astype(str) + " "
        # missing unit_cost
        idx = rng.choice(df.index, size=8, replace=False)
        df.loc[idx, "unit_cost"] = np.nan

    if name == "inventory_snapshots":
        idx = rng.choice(df.index, size=int(len(df) * 0.01), replace=False)
        df.loc[idx, "on_hand_units"] = np.nan
        idx = rng.choice(df.index, size=int(len(df) * 0.005), replace=False)
        df.loc[idx, "lead_time_days"] = np.nan

    return df


def main() -> None:
    rng = np.random.default_rng(SEED)
    RAW.mkdir(parents=True, exist_ok=True)

    cal = build_calendar(rng)
    skus = build_sku_master(rng)
    sales = build_sales(cal, skus, rng)
    inv = build_inventory(sales, skus, rng)

    dirty(sales, rng, "sales_daily").to_csv(RAW / "sales_daily.csv", index=False)
    dirty(skus, rng, "sku_master").to_csv(RAW / "sku_master.csv", index=False)
    cal.to_csv(RAW / "calendar.csv", index=False)
    dirty(inv, rng, "inventory_snapshots").to_csv(RAW / "inventory_snapshots.csv", index=False)

    print(f"Wrote 4 extracts to {RAW}")
    print(f"  sales_daily.csv         {len(sales):>8,} rows (+500 duplicates)")
    print(f"  sku_master.csv          {len(skus):>8,} rows")
    print(f"  calendar.csv            {len(cal):>8,} rows")
    print(f"  inventory_snapshots.csv {len(inv):>8,} rows")


if __name__ == "__main__":
    main()
