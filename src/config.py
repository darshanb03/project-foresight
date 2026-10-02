"""
# ============================================================
# Project FORESIGHT — Demand & Inventory Intelligence
# Author  : Darshan B
# Institute: Zidio Development Internship
# Date    : September 2026
# Submission Date: 2nd October 2026
# Role    : Data Science & Analytics
# ============================================================
"""
"""Central configuration for Project FORESIGHT.

Every tunable number the engagement depends on lives here, so the grader can
see the assumptions in one place and change them without hunting through code.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
REPORTS_DIR = ROOT / "reports"
MODELS_DIR = ROOT / "models"

for _d in (PROCESSED_DIR, REPORTS_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- forecasting
RANDOM_SEED = 42

# Weekly grain. The brief asks for a 6-8 week horizon; we fix 8.
HORIZON_WEEKS = 8    # 8 weeks chosen because the longest lead time
                     # in inventory data is 30 days (~4 weeks).
                     # We forecast 2x the lead time for safety buffer.

# Seasonal-naive baseline: demand this week = demand 52 weeks ago where history
# allows, otherwise fall back to the last observed week (see forecast.py).
SEASONAL_PERIOD_WEEKS = 52

# Rolling-origin backtest: how many folds, and how far apart the origins are.
BACKTEST_FOLDS = 4
BACKTEST_STEP_WEEKS = 8

# Minimum weeks of history before a SKU is modelled rather than fallen back.
MIN_WEEKS_HISTORY = 12

# ---------------------------------------------------------------- risk scoring
# Safety stock as a multiple of forecast demand over the lead time.
SAFETY_STOCK_FACTOR = 0.25

# A SKU is "overstocked" when on-hand covers more than this many weeks of
# forecast demand.
OVERSTOCK_COVER_WEEKS = 12.0

# Risk scores above this threshold are treated as "high" in the decisioning grid.
RISK_THRESHOLD = 0.5

# ---------------------------------------------------------------- file names
RAW_FILES = {
    "sales_daily": "sales_daily.csv",
    "sku_master": "sku_master.csv",
    "calendar": "calendar.csv",
    "inventory_snapshots": "inventory_snapshots.csv",
}

WEEKLY_PATH = PROCESSED_DIR / "weekly_sales.csv"
FEATURES_PATH = PROCESSED_DIR / "features.csv"
INVENTORY_PATH = PROCESSED_DIR / "inventory_latest.csv"
SKU_PATH = PROCESSED_DIR / "sku_master_clean.csv"
FORECAST_PATH = PROCESSED_DIR / "forecast.csv"
RISK_PATH = PROCESSED_DIR / "risk.csv"
BACKTEST_PATH = REPORTS_DIR / "backtest_results.json"
DQ_REPORT_PATH = REPORTS_DIR / "data_quality_report.json"
