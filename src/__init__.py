"""
D5 — NorthBay Living planning dashboard.

FIXED VERSION 

Run locally:
    streamlit run app/streamlit_app.py
"""

# ── PATH FIX (must happen before any src imports) ──────────────────────────
import os
import sys
from pathlib import Path

# Work out where the repo root is and add it to Python's search path.
# This makes "from src import ..." work both locally and on Streamlit Cloud.
_HERE = Path(__file__).resolve()           # .../project-foresight/app/streamlit_app.py
_ROOT = _HERE.parents[1]                   # .../project-foresight/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)                            # make relative file paths work too
# ───────────────────────────────────────────────────────────────────────────

import json

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src import config as C
from src import risk as risk_mod

st.set_page_config(
    page_title="FORESIGHT — NorthBay Planning",
    page_icon="📦",
    layout="wide",
)

PALETTE = {
    "Reorder now": "#d64545",
    "Markdown / clear": "#6b5bd6",
    "Watch / volatile": "#d69b45",
    "Healthy": "#3f9e6a",
}


# ------------------------------------------------------------------ data load
@st.cache_data(show_spinner=False)
def load_data():
    needed = [C.WEEKLY_PATH, C.FORECAST_PATH, C.RISK_PATH, C.SKU_PATH]
    if not all(p.exists() for p in needed):
        return None

    weekly = pd.read_csv(C.WEEKLY_PATH, parse_dates=["week_start"])
    forecast = pd.read_csv(C.FORECAST_PATH, parse_dates=["origin_week", "target_week"])
    risk = pd.read_csv(C.RISK_PATH)
    skus = pd.read_csv(C.SKU_PATH, parse_dates=["launch_date"])

    backtest = None
    if C.BACKTEST_PATH.exists():
        backtest = json.loads(C.BACKTEST_PATH.read_text())

    return weekly, forecast, risk, skus, backtest


def inr(x: float) -> str:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return "—"
    if abs(x) >= 1e7:
        return f"₹{x / 1e7:.2f} Cr"
    if abs(x) >= 1e5:
        return f"₹{x / 1e5:.2f} L"
    return f"₹{x:,.0f}"


# ---------------------------------------------------------------- main layout
st.title("📦 FORESIGHT — Demand & Inventory Planning")
st.caption("NorthBay Living · 8-week SKU-level demand forecast and stock risk")

with st.spinner("Loading latest planning run..."):
    data = load_data()

if data is None:
    st.warning("No planning run found yet.")
    st.markdown(
        """
        This dashboard reads the outputs of the FORESIGHT pipeline.

        **If you are running this locally:**
        ```bash
        python tools/generate_synthetic_data.py
        python run_all.py
        ```

        **If you are on Streamlit Cloud:**
        The processed data files need to be committed to GitHub.
        Run the pipeline locally first, then commit the files in
        `data/processed/` (except `features.csv`) and push to GitHub.
        """
    )
    st.stop()

weekly, forecast, risk, skus, backtest = data

# -------------------------------------------------------------------- filters
st.sidebar.header("Filters")
categories = sorted(risk["category"].dropna().unique().tolist())
sel_cats = st.sidebar.multiselect("Category", categories, default=categories)
quadrants = ["Reorder now", "Markdown / clear", "Watch / volatile", "Healthy"]
sel_quads = st.sidebar.multiselect("Status", quadrants, default=quadrants)
min_value = st.sidebar.slider(
    "Minimum value at stake (₹)", 0,
    int(max(risk["value_at_stake_inr"].max(), 1)), 0, step=1000,
)

view = risk[
    risk["category"].isin(sel_cats)
    & risk["quadrant"].isin(sel_quads)
    & (risk["value_at_stake_inr"] >= min_value)
].copy()

st.sidebar.markdown("---")
horizon_end = forecast["target_week"].max()
st.sidebar.caption(
    f"Forecast horizon: {C.HORIZON_WEEKS} weeks\n\n"
    f"Through {horizon_end.date()}\n\n"
    f"{risk['sku_id'].nunique()} SKUs scored"
)
if backtest:
    st.sidebar.caption(
        f"Backtest WAPE: {backtest['mean_model_wape']:.3f} "
        f"(baseline {backtest['mean_baseline_wape']:.3f})"
    )

if view.empty:
    st.info("No SKUs match these filters. Widen the category, status or value filter.")
    st.stop()

# ----------------------------------------------------------------- headline
c1, c2, c3, c4 = st.columns(4)
c1.metric("Sales at risk", inr(view["sales_at_risk_inr"].sum()),
          help="Revenue we expect to lose to stockouts over the lead time.")
c2.metric("Capital locked", inr(view["capital_locked_inr"].sum()),
          help="Cost value of stock beyond a sensible weeks-of-cover.")
c3.metric("Reorder now", int((view["quadrant"] == "Reorder now").sum()))
c4.metric("Markdown / clear", int((view["quadrant"] == "Markdown / clear").sum()))

tab_action, tab_grid, tab_sku, tab_model = st.tabs(
    ["🚨 Action list", "🎯 Decisioning grid", "🔍 SKU detail", "📊 Model & accuracy"]
)

# -------------------------------------------------------------- action list
with tab_action:
    st.subheader("What to do this week")
    st.caption("Sorted by rupee value at stake — work down from the top.")

    reorder = view[view["quadrant"] == "Reorder now"].sort_values(
        "sales_at_risk_inr", ascending=False
    )
    markdown = view[view["quadrant"] == "Markdown / clear"].sort_values(
        "capital_locked_inr", ascending=False
    )

    st.markdown(f"#### 🔴 Reorder now — {len(reorder)} SKUs")
    if reorder.empty:
        st.success("Nothing is projected to stock out under the current filters.")
    else:
        st.dataframe(
            reorder[[
                "sku_id", "category", "on_hand_units", "available_units",
                "avg_weekly_demand", "lead_time_days", "shortfall_units",
                "suggested_order_units", "sales_at_risk_inr", "why",
            ]].rename(columns={
                "sku_id": "SKU", "category": "Category",
                "on_hand_units": "On hand", "available_units": "Available",
                "avg_weekly_demand": "Fcst/wk", "lead_time_days": "Lead (d)",
                "shortfall_units": "Short by", "suggested_order_units": "Order qty",
                "sales_at_risk_inr": "Sales at risk ₹", "why": "Why",
            }),
            use_container_width=True, hide_index=True,
            column_config={
                "Fcst/wk": st.column_config.NumberColumn(format="%.1f"),
                "Sales at risk ₹": st.column_config.NumberColumn(format="%.0f"),
            },
        )

    st.markdown(f"#### 🟣 Markdown / clear — {len(markdown)} SKUs")
    if markdown.empty:
        st.success("No SKUs are carrying excess cover under the current filters.")
    else:
        st.dataframe(
            markdown[[
                "sku_id", "category", "on_hand_units", "avg_weekly_demand",
                "weeks_of_cover", "excess_units", "capital_locked_inr", "why",
            ]].rename(columns={
                "sku_id": "SKU", "category": "Category", "on_hand_units": "On hand",
                "avg_weekly_demand": "Fcst/wk", "weeks_of_cover": "Weeks cover",
                "excess_units": "Excess units", "capital_locked_inr": "Capital locked ₹",
                "why": "Why",
            }),
            use_container_width=True, hide_index=True,
            column_config={
                "Fcst/wk": st.column_config.NumberColumn(format="%.1f"),
                "Weeks cover": st.column_config.NumberColumn(format="%.1f"),
                "Capital locked ₹": st.column_config.NumberColumn(format="%.0f"),
            },
        )

    st.download_button(
        "Download this action list (CSV)",
        view.to_csv(index=False).encode("utf-8"),
        file_name="foresight_action_list.csv",
        mime="text/csv",
    )

# ---------------------------------------------------------- decisioning grid
with tab_grid:
    st.subheader("Every SKU on one grid")
    st.caption(
        "Bubble size is the rupee value at stake. Top-left needs reordering, "
        "bottom-right needs clearing."
    )

    fig = px.scatter(
        view,
        x="overstock_risk", y="stockout_risk",
        size="value_at_stake_inr", color="quadrant",
        color_discrete_map=PALETTE,
        hover_name="sku_id",
        hover_data={
            "category": True, "on_hand_units": ":.0f",
            "avg_weekly_demand": ":.1f", "weeks_of_cover": ":.1f",
            "value_at_stake_inr": ":,.0f",
            "overstock_risk": ":.2f", "stockout_risk": ":.2f",
        },
        size_max=45,
        labels={
            "overstock_risk": "Overstock risk →",
            "stockout_risk": "Stockout risk →",
            "quadrant": "Status",
        },
    )
    fig.add_hline(y=C.RISK_THRESHOLD, line_dash="dot", line_color="#999")
    fig.add_vline(x=C.RISK_THRESHOLD, line_dash="dot", line_color="#999")
    fig.update_layout(height=560, xaxis_range=[-0.05, 1.05], yaxis_range=[-0.05, 1.05])
    st.plotly_chart(fig, use_container_width=True)

    counts = view["quadrant"].value_counts().reindex(quadrants).fillna(0).astype(int)
    g1, g2, g3, g4 = st.columns(4)
    for col, q in zip((g1, g2, g3, g4), quadrants):
        col.metric(q, int(counts[q]))

# ------------------------------------------------------------------ sku view
with tab_sku:
    st.subheader("Single SKU deep dive")
    sku_list = sorted(view["sku_id"].unique().tolist())
    sel_sku = st.selectbox("SKU", sku_list)

    row = view[view["sku_id"] == sel_sku].iloc[0]
    hist = weekly[weekly["sku_id"] == sel_sku].sort_values("week_start").tail(52)
    fc = forecast[forecast["sku_id"] == sel_sku].sort_values("target_week")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Status", row["quadrant"])
    m2.metric("On hand", f"{row['on_hand_units']:.0f}")
    m3.metric("Forecast / week", f"{row['avg_weekly_demand']:.1f}")
    m4.metric("Weeks of cover", f"{row['weeks_of_cover']:.1f}")

    st.info(row["why"])
    if row["suggested_order_units"] > 0:
        st.warning(f"Suggested order quantity: **{row['suggested_order_units']:.0f} units**")

    chart = go.Figure()
    chart.add_trace(go.Scatter(
        x=hist["week_start"], y=hist["units_sold"],
        name="Actual demand", mode="lines", line=dict(color="#222", width=2),
    ))
    if not fc.empty:
        chart.add_trace(go.Scatter(
            x=list(fc["target_week"]) + list(fc["target_week"])[::-1],
            y=list(fc["forecast_hi"]) + list(fc["forecast_lo"])[::-1],
            fill="toself", fillcolor="rgba(107,91,214,0.18)",
            line=dict(color="rgba(0,0,0,0)"), name="80% interval", hoverinfo="skip",
        ))
        chart.add_trace(go.Scatter(
            x=fc["target_week"], y=fc["forecast_units"],
            name="Forecast", mode="lines+markers",
            line=dict(color="#6b5bd6", width=3),
        ))
        chart.add_trace(go.Scatter(
            x=fc["target_week"], y=fc["baseline_units"],
            name="Seasonal-naive baseline", mode="lines",
            line=dict(color="#d69b45", width=2, dash="dash"),
        ))
    chart.update_layout(
        height=420, hovermode="x unified", yaxis_title="Units / week",
        xaxis_title="", legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(chart, use_container_width=True)

# ---------------------------------------------------------------- model tab
with tab_model:
    st.subheader("How accurate is this forecast?")
    if not backtest:
        st.info("No backtest results found. Run `python run_all.py` to generate them.")
    else:
        b1, b2, b3 = st.columns(3)
        b1.metric("Model WAPE", f"{backtest['mean_model_wape']:.3f}")
        b2.metric("Baseline WAPE", f"{backtest['mean_baseline_wape']:.3f}")
        b3.metric(
            "Improvement",
            f"{backtest['improvement_vs_baseline_pct']:.1f}%",
            delta="beats baseline" if backtest["model_beats_baseline"] else "below baseline",
        )
        st.caption(
            "WAPE = total absolute error ÷ total actual demand. Lower is better. "
            "Measured with rolling-origin backtesting: the model is trained only on "
            "data before each test window, never on it."
        )
        folds = pd.DataFrame(backtest["folds"])
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=folds["fold"], y=folds["model_wape"],
            name="Model", marker_color="#6b5bd6",
        ))
        fig2.add_trace(go.Bar(
            x=folds["fold"], y=folds["baseline_wape"],
            name="Seasonal-naive", marker_color="#d69b45",
        ))
        fig2.update_layout(barmode="group", height=340,
                           xaxis_title="Backtest fold", yaxis_title="WAPE")
        st.plotly_chart(fig2, use_container_width=True)
        st.dataframe(
            folds[["fold", "train_until", "test_from", "test_to",
                   "n_test_rows", "model_wape", "baseline_wape", "model_bias"]],
            use_container_width=True, hide_index=True,
        )
        st.markdown(
            """
            **Known limitations:**
            - Accuracy is worse for SKUs with under ~3 months of history.
            - Promotions are modelled from a flag, not discount depth.
            - Stock positions are weekly snapshots — a SKU that moved sharply
              since the last snapshot may be mis-scored.
            - The risk thresholds are business settings. Change them in `src/config.py`.
            """
        )

st.markdown("---")
st.caption(
    "FORESIGHT · Zidio Development · "
    "forecasts are decision support, not a replacement for planner judgement."
)
