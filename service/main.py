"""
D6 — Scoring service.

A small read API over the latest planning run. It answers, for any SKU:
"what will we sell, and what should we do about our stock?"

Design note: this serves the outputs of the most recent pipeline run rather than
retraining per request. NorthBay replans weekly, not per second, so serving a
dated artefact is the honest design — and every response carries the run date so
a caller can see how stale it is.

Run locally:
    uvicorn service.main:app --reload --port 8000

Interactive docs are then at http://localhost:8000/docs
"""


import sys

from datetime import datetime
from pathlib import Path

import pandas as pd

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import config as C  # noqa: E402

app = FastAPI(
    title="Project FORESIGHT — Scoring Service",
    description=(
        "Demand forecast and inventory risk for NorthBay Living SKUs. "
        "Serves the most recent planning run."
    ),
    version="1.0.0",
)

_CACHE: dict[str, pd.DataFrame] = {}


def _load() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load forecast and risk tables once, then reuse."""
    if "risk" not in _CACHE:
        if not (C.RISK_PATH.exists() and C.FORECAST_PATH.exists()):
            raise HTTPException(
                status_code=503,
                detail="No planning run available. Run `python run_all.py` first.",
            )
        _CACHE["risk"] = pd.read_csv(C.RISK_PATH)
        _CACHE["forecast"] = pd.read_csv(
            C.FORECAST_PATH, parse_dates=["origin_week", "target_week"]
        )
    return _CACHE["forecast"], _CACHE["risk"]


# ------------------------------------------------------------------- schemas
class WeekPoint(BaseModel):
    week_starting: str = Field(..., description="Monday of the forecast week, YYYY-MM-DD")
    horizon_week: int = Field(..., description="Weeks ahead of the planning origin, 1-8")
    forecast_units: float = Field(..., description="Expected units sold that week")
    interval_low: float = Field(..., description="Lower bound, 80% interval")
    interval_high: float = Field(..., description="Upper bound, 80% interval")
    baseline_units: float = Field(..., description="Seasonal-naive comparison")


class SkuScore(BaseModel):
    sku_id: str
    category: str | None = None
    status: str = Field(..., description="Reorder now | Markdown / clear | Watch / volatile | Healthy")
    recommended_action: str
    explanation: str
    stockout_risk: float = Field(..., ge=0, le=1)
    overstock_risk: float = Field(..., ge=0, le=1)
    on_hand_units: float
    available_units: float
    avg_weekly_demand: float
    weeks_of_cover: float
    suggested_order_units: float
    sales_at_risk_inr: float
    capital_locked_inr: float
    forecast: list[WeekPoint]
    planning_run_origin: str


class BatchRequest(BaseModel):
    sku_ids: list[str] = Field(..., min_length=1, max_length=200,
                               description="Up to 200 SKU identifiers")


class BatchResponse(BaseModel):
    found: list[SkuScore]
    not_found: list[str]


# --------------------------------------------------------------------- build
def _score_for(sku_id: str, forecast: pd.DataFrame, risk: pd.DataFrame) -> SkuScore | None:
    r = risk[risk["sku_id"] == sku_id]
    if r.empty:
        return None
    r = r.iloc[0]
    f = forecast[forecast["sku_id"] == sku_id].sort_values("h")

    points = [
        WeekPoint(
            week_starting=str(row["target_week"].date()),
            horizon_week=int(row["h"]),
            forecast_units=round(float(row["forecast_units"]), 2),
            interval_low=round(float(row["forecast_lo"]), 2),
            interval_high=round(float(row["forecast_hi"]), 2),
            baseline_units=round(float(row["baseline_units"]), 2),
        )
        for _, row in f.iterrows()
    ]

    origin = str(f["origin_week"].iloc[0].date()) if not f.empty else "unknown"

    return SkuScore(
        sku_id=sku_id,
        category=None if pd.isna(r.get("category")) else str(r.get("category")),
        status=str(r["quadrant"]),
        recommended_action=str(r["recommended_action"]),
        explanation=str(r["why"]),
        stockout_risk=round(float(r["stockout_risk"]), 4),
        overstock_risk=round(float(r["overstock_risk"]), 4),
        on_hand_units=float(r["on_hand_units"]),
        available_units=float(r["available_units"]),
        avg_weekly_demand=round(float(r["avg_weekly_demand"]), 2),
        weeks_of_cover=round(float(r["weeks_of_cover"]), 2),
        suggested_order_units=float(r["suggested_order_units"]),
        sales_at_risk_inr=float(r["sales_at_risk_inr"]),
        capital_locked_inr=float(r["capital_locked_inr"]),
        forecast=points,
        planning_run_origin=origin,
    )


# -------------------------------------------------------------------- routes
@app.get("/", tags=["meta"])
def root() -> dict:
    return {
        "service": "Project FORESIGHT scoring service",
        "docs": "/docs",
        "endpoints": ["/health", "/skus", "/score/{sku_id}", "/score/batch", "/summary"],
    }


@app.get("/health", tags=["meta"])
def health() -> dict:
    try:
        forecast, risk = _load()
    except HTTPException:
        return {"status": "degraded", "reason": "no planning run available"}
    return {
        "status": "ok",
        "skus_available": int(risk["sku_id"].nunique()),
        "horizon_weeks": int(forecast["h"].max()),
        "checked_at": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/skus", tags=["lookup"])
def list_skus(
    category: str | None = Query(None, description="Filter by category"),
    status: str | None = Query(None, description="Filter by risk status"),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    _, risk = _load()
    df = risk
    if category:
        df = df[df["category"].str.lower() == category.lower()]
    if status:
        df = df[df["quadrant"].str.lower() == status.lower()]
    return {
        "count": int(len(df)),
        "sku_ids": df["sku_id"].head(limit).tolist(),
    }


@app.get("/score/{sku_id}", response_model=SkuScore, tags=["scoring"])
def score_sku(sku_id: str) -> SkuScore:
    """Forecast and risk for one SKU.

    Returns 404 with the closest matching identifiers if the SKU is unknown,
    rather than failing opaquely.
    """
    forecast, risk = _load()
    sku_id = sku_id.strip().upper()

    result = _score_for(sku_id, forecast, risk)
    if result is None:
        near = risk[risk["sku_id"].str.contains(sku_id[:4], case=False, na=False)]
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"SKU '{sku_id}' not found in the latest planning run.",
                "did_you_mean": near["sku_id"].head(5).tolist(),
            },
        )
    return result


@app.post("/score/batch", response_model=BatchResponse, tags=["scoring"])
def score_batch(req: BatchRequest) -> BatchResponse:
    """Score many SKUs at once. Unknown identifiers are reported, not fatal."""
    forecast, risk = _load()
    found, missing = [], []
    for raw in req.sku_ids:
        sid = str(raw).strip().upper()
        res = _score_for(sid, forecast, risk)
        (found.append(res) if res else missing.append(sid))
    return BatchResponse(found=found, not_found=missing)


@app.get("/summary", tags=["reporting"])
def summary() -> dict:
    """Portfolio-level headline numbers — what the Finance lead asks for."""
    _, risk = _load()
    return {
        "skus_scored": int(len(risk)),
        "status_counts": {k: int(v) for k, v in risk["quadrant"].value_counts().items()},
        "total_sales_at_risk_inr": round(float(risk["sales_at_risk_inr"].sum()), 2),
        "total_capital_locked_inr": round(float(risk["capital_locked_inr"].sum()), 2),
        "top_10_by_value": risk.nlargest(10, "value_at_stake_inr")[
            ["sku_id", "quadrant", "value_at_stake_inr"]
        ].to_dict(orient="records"),
    }
