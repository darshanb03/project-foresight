## About This Project

My name is Darshan B. I built this project as part of my internship
at Zidio Development in the Data Science & Analytics track.

The client is NorthBay Living, a fictional D2C (direct-to-consumer) 
home and lifestyle brand with 200 products. They had a common inventory
problem: stocking out of popular items (lost sales) while sitting on 
too much slow-moving stock (wasted money).

I built Project FORESIGHT: a machine learning system that predicts 
demand for each product 8 weeks ahead, identifies which products are 
about to run out of stock, which have too much stock, and how much money 
is at risk which is displayed in an interactive dashboard that non-technical 
staff can use without any data science knowledge.

# Project FORESIGHT — Demand & Inventory Intelligence

**Client:** NorthBay Living (D2C home & lifestyle, ~200 SKUs)
**Engagement:** Zidio Development · Data Science & Analytics · 4 weeks
**Deliverable:** an 8-week SKU-level demand forecast, a stockout/overstock early-warning system, a planning dashboard, and a scoring service.


## The problem

NorthBay plans inventory on spreadsheets and instinct. They lose money in two directions at once: best-sellers run out (unrecoverable lost sales) and slow movers pile up (cash locked in stock that later gets marked down). They asked for three things: how much will we sell, what is about to run out, and what are we sitting on in a form their ops team can use without a data scientist in the room.

## Headline results

| | Result |
|---|---|
| Forecast accuracy (WAPE, rolling-origin backtest) | **0.169** |
| Seasonal-naive baseline (same metric, same test rows) | 0.213 |
| **Improvement over baseline** | **20.4%** — the model wins in all 4 folds |
| Sales at risk from projected stockouts | ₹1.28 Cr across 13 SKUs |
| Capital locked in overstock | ₹1.38 Cr across 18 SKUs |
| Concentration | the top 10 SKUs carry 64% of the total value at stake |

Accuracy is measured with rolling-origin cross-validation, never a random split. Full fold-by-fold results: `reports/backtest_results.json`.

> **Honesty note.** The seasonal-naive baseline is computed on exactly the same test rows as the model, using only history that precedes each target week (there is an automated test that proves this). An earlier version of this model beat the baseline by only 1.5% and lost one fold; the fix was giving the model the same seasonal anchor the baseline uses (demand in the same week last year, relative to the *target* week rather than the origin week). That is recorded here rather than quietly overwritten.


## Quickstart

```bash
git clone <your-repo-url>
cd foresight

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# If you have the client extracts, put the four CSVs in data/raw/.
# If not, generate a stand-in dataset with the same schema:
python tools/generate_synthetic_data.py

# Reproduce the entire engagement end to end (~60s)
python run_all.py

# Launch the planning dashboard
streamlit run app/streamlit_app.py

# Launch the scoring service (separate terminal)
uvicorn service.main:app --reload --port 8000   # docs at localhost:8000/docs
```

Verify the leakage guards:

```bash
python tests/test_pipeline.py        # or: python -m pytest tests -q
```


## Architecture

```
data/raw/*.csv              four client extracts (sales, SKU master, calendar, inventory)
        │
        ▼
src/pipeline.py             ingest → validate → clean → weekly aggregation → features
        │                   writes data/processed/ + reports/data_quality_report.json
        ├──────────────► src/eda.py        figures + insight numbers for the reports
        ▼
src/forecast.py             seasonal-naive baseline · global GBM · rolling-origin backtest
        │                   writes forecast.csv + backtest_results.json
        ▼
src/risk.py                 stockout / overstock scoring → action + rupee value at stake
        │                   writes risk.csv
        ├──────────────► app/streamlit_app.py     planning dashboard (D5)
        └──────────────► service/main.py          scoring API (D6)
```

Every stage reads files and writes files, so any stage can be re-run or inspected on its own. `run_all.py` chains all four.

---

## How the forecast works

**Framing.** Weekly SKU-level demand, 8-week horizon, WAPE as the primary metric (chosen over MAPE because many SKUs have zero-demand weeks, where MAPE is undefined or explodes). Bias is tracked as a secondary check for systematic over/under-forecasting.

**Baseline first.** A seasonal-naive forecast — demand equals the same week one year earlier — is built before any model, and every later result is reported against it.

**Model.** One global gradient-boosted tree model (`HistGradientBoostingRegressor`, Poisson loss because demand is non-negative count data) trained across all SKUs. Pooling helps the many SKUs with thin history; lag and level features keep products distinguishable.

**Direct multi-horizon, not recursive.** Each training row is "standing at week *w* knowing only the past, predict week *w+h-1*", with the horizon *h* as a feature. Recursive forecasting feeds predictions back in as inputs, compounding its own error and making accidental leakage easy. Direct framing keeps every prediction traceable to observed history.

**Features.** Lags (1–52 weeks), rolling mean/std/max over 4–26 weeks, a 4-vs-13-week trend ratio, cyclical week-of-year encoding, promotion flags and weeks-since-promo, relative price, category, weeks since launch, and the seasonal anchor (demand in the same week last year, anchored on the target week).

**Leakage rule.** Features for week *w* are computed strictly from weeks before *w*; every rolling window is shifted by one. The only target-week information used is the calendar and the promotion flag, both of which NorthBay genuinely knows in advance because they set their own promo calendar. `tests/test_pipeline.py` asserts all of this.

**Intervals.** The 80% interval comes from the empirical distribution of residuals per horizon on a held-out final fold — a measurement of how wrong this model actually was at that lead time, not a theoretical formula.


## How risk scoring works

Deliberately rule-based, not a second model. The ops team has to trust and override these calls, so each score is one explainable sentence.

| | Definition |
|---|---|
| **Stockout risk** | Forecast demand over the lead time, plus a 25% safety buffer, compared with on-hand + on-order stock. Score = shortfall ÷ required, capped at 1. |
| **Overstock risk** | On-hand stock ÷ average weekly forecast demand = weeks of cover. Anything beyond 12 weeks of cover is excess. Score = excess weeks ÷ 12, capped at 1. |
| **Sales at risk (₹)** | Shortfall units × list price. |
| **Capital locked (₹)** | Excess units × unit cost. |

Each SKU lands in one quadrant of the decisioning grid, with an action and a plain-language justification:

| Quadrant | Meaning | Action |
|---|---|---|
| Reorder now | High stockout, low overstock | Raise a replenishment order |
| Markdown / clear | High overstock, low stockout | Promote or discount to free capital |
| Watch / volatile | High on both | Investigate manually — demand is erratic |
| Healthy | Low on both | Leave as is |

Thresholds (safety factor, weeks of cover, risk cutoff) are business settings, not learned values. They all live in `src/config.py` so the client can tune them without touching model code.


## Data quality — what we found and what we did

Generated fresh on every run into `reports/data_quality_report.json`. From the current run:

| Issue | Handling | Rationale |
|---|---|---|
| 500 exact duplicate sales rows | Dropped | Extract artefacts, not real transactions |
| 200 rows with negative units | Floored to zero | Mis-booked returns; demand cannot be negative. Floored rather than deleted, because deleting would leave gaps that lag features would silently misread |
| 584 missing unit prices | Filled forward/backward within SKU | Price is sticky over time |
| 1,169 missing revenue values | Recomputed as units × price | Internally consistent and auditable |
| 8 SKUs missing unit cost | Imputed from category median | Keeps products in scope; their margin figures are approximate |
| 52 missing stock snapshots | Carried last known value forward | Stock is a level, not a flow |
| Inconsistent category labels (case, whitespace) | Normalised to title case | Prevented spurious duplicate categories |
| Weeks with no sales row | Treated as zero demand, not missing | A gap would make lag features jump over time |


## Key insights from EDA

Numbers computed in `src/eda.py`; figures in `reports/figures/`.

1. **Revenue is concentrated.** The top 20% of SKUs drive 60% of revenue — and the top 10 SKUs alone account for 64% of all value at stake. Planning effort should follow that curve, not be spread evenly across 200 products.
2. **Seasonality is strong and worth forecasting.** Peak week of year runs 2.7× the trough. A flat reorder policy will systematically over-order in the trough and under-order into the peak.
3. **Promotions nearly double demand.** Promo weeks average 80% higher units than normal weeks — so any forecast that ignores the promo calendar will badly under-order ahead of a campaign.
4. **Demand is lumpy at SKU level.** 4.5% of SKU-weeks have zero demand and the median SKU has a coefficient of variation of 0.53, which is why WAPE was chosen over MAPE and why intervals matter more than point forecasts.


## Repository layout

```
foresight/
├── data/
│   ├── raw/                  client extracts (gitignored)
│   └── processed/            analysis-ready outputs
├── notebooks/
│   ├── 01_eda.ipynb          exploration and data-quality investigation
│   ├── 02_baseline.ipynb     metric definition and seasonal-naive baseline
│   └── 03_model.ipynb        features, model, backtest vs baseline
├── src/
│   ├── config.py             every tunable assumption in one place
│   ├── pipeline.py           D1 — ingest, clean, aggregate, features
│   ├── eda.py                D2 — figures and insight numbers
│   ├── forecast.py           D3 — baseline, model, backtest, forecast
│   └── risk.py               D4 — risk scoring and rupee impact
├── app/streamlit_app.py      D5 — planning dashboard
├── service/main.py           D6 — scoring API
├── reports/                  D2 memo, D7 executive readout, figures, JSON results
├── tests/test_pipeline.py    leakage and correctness guards
├── tools/                    synthetic data generator
└── run_all.py                one-command reproduction
```


## Deployment

**Dashboard — Streamlit Community Cloud.** Point a new app at this repo, branch `main`, main file `app/streamlit_app.py`. The small serving artefacts in `data/processed/` are committed deliberately so the deployed app has data without re-running the pipeline on a free-tier container.

**Scoring service — Render.** New Web Service from this repo, build `pip install -r requirements.txt`, start `uvicorn service.main:app --host 0.0.0.0 --port $PORT` (also in the `Procfile`). Interactive docs are served at `/docs`.


## Assumptions and limitations

**Assumptions**
- The provided extracts are representative of real sales and inventory behaviour.
- Lead times and reorder points in the inventory data are broadly accurate.
- NorthBay's promotion calendar is known in advance, so promo flags for future weeks are legitimate inputs.
- Weekly grain is the right planning cadence; daily would be noisier than the decisions require.

**Limitations — read before acting on any number**
- Accuracy degrades sharply for SKUs with under ~3 months of history; those forecasts lean on pooled category seasonality.
- Promotions are modelled from a binary flag, not discount depth, so an unusually deep promotion will be under-forecast.
- Stock positions are weekly snapshots, so a SKU that moved sharply since the last snapshot can be mis-scored.
- Risk thresholds are judgement calls, not optimised values. They should be tuned against NorthBay's actual service-level target.
- The model has not been tested against a demand regime it has never seen (a supply shock, a viral product). Intervals will be too narrow in those conditions.

**Not built, deliberately** (out of scope per the brief): live system integrations, price optimisation, inventory-optimisation solvers, streaming pipelines, and automated PO placement.


## Reproducibility

Random seeds are fixed (`src/config.py`). A grader should be able to clone the repo, install requirements, run `python run_all.py`, and land on the same headline numbers printed above. If you are using the synthetic generator, the seed there is fixed too, so the dataset itself is reproducible.
