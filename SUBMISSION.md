# Submission checklist — Project FORESIGHT

Zidio requires 5 links. Map them as follows.

| # | Deliverable | Marks | What to submit |
|---|---|---|---|
| 1 | Source Code | 5 | Your public GitHub repo URL |
| 2 | Live Deployment | 5 | Your Streamlit Cloud app URL |
| 3 | Demo Video | 4 | YouTube (unlisted), 3–5 min |
| 4 | Feedback Video | 4 | YouTube (unlisted), 1–2 min |
| 5 | Project Report | 2 | Google Drive link to `FORESIGHT_Executive_Readout.pptx` (or its PDF) |

The brief's D2 memo (`reports/eda_memo.md`) and README both live in the repo, which covers submission criterion "Repository & notebooks".

---

## Step 1 — Push to GitHub

```bash
cd foresight
git init
git add .
git commit -m "Project FORESIGHT — demand forecasting and inventory risk"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/foresight.git
git push -u origin main
```

`.gitignore` already excludes the raw extracts (confidential, large) and the 7 MB
feature table. The small serving files in `data/processed/` ARE committed on
purpose — the deployed dashboard reads them.

Check before pushing:
```bash
git status --short          # no .csv from data/raw/, no .env
python tests/test_pipeline.py
```

## Step 2 — Deploy the dashboard

1. share.streamlit.io → sign in with GitHub → **New app**
2. Repo `YOUR_USERNAME/foresight`, branch `main`, main file `app/streamlit_app.py`
3. Deploy. First build takes a few minutes.
4. **Open the URL in an incognito window** — Zidio guideline 3 requires no login prompt.

## Step 3 — Deploy the scoring service (optional but worth 5 marks under "Dashboard & deployment")

Render.com → New Web Service → connect the repo:
- Build: `pip install -r requirements.txt`
- Start: `uvicorn service.main:app --host 0.0.0.0 --port $PORT`

Docs land at `<your-url>/docs`. Test `/score/SKU0128` before submitting.

## Step 4 — Record the demo video (3–5 min)

The rubric wants "a walkthrough of the analysis and the tools, end to end."
A structure that covers it:

1. **(30s) The problem.** NorthBay stocks out of best-sellers and sits on slow
   movers. Show the brief's quote.
2. **(45s) The data and what was wrong with it.** Open `reports/data_quality_report.json`
   — duplicates, negative units, inconsistent category labels.
3. **(60s) The model.** Open notebook 03. Emphasise: baseline first, rolling-origin
   backtest, no random split. Show the fold chart — 0.169 vs 0.213, wins all four folds.
4. **(30s) Honesty moment.** Mention the first version only beat baseline by 1.5%
   and lost a fold, and why (`target_lag_52`). This is the single most credible
   thing you can say on camera.
5. **(90s) The dashboard.** Filter to "Reorder now", show the action list, open the
   decisioning grid, drill into SKU0128, show the forecast chart with its interval.
6. **(30s) The service.** Hit `/score/SKU0128` in the browser.
7. **(15s) Close.** ₹2.1 Cr addressable; 31 decisions instead of 200.

Record with OBS Studio (free) or Loom. Upload to YouTube as **Unlisted**.

## Step 5 — Record the feedback video (1–2 min)

Not a demo. A reflection. Cover honestly:
- What you learned (rolling-origin backtesting; why WAPE over MAPE; that a
  baseline is the whole point of the exercise).
- A real challenge (the seasonal-anchor bug, and how the backtest surfaced it).
- A key takeaway (an honestly-validated 20% gain beats an impressive number you
  cannot defend).

## Step 6 — Upload the report

Upload `reports/FORESIGHT_Executive_Readout.pptx` (and/or the PDF) to Google Drive,
set sharing to **Anyone with the link**, and submit that link.

## Step 7 — Final checks

- [ ] Every link opens in an incognito window with no login prompt
- [ ] README headline numbers match what `run_all.py` prints
- [ ] `python tests/test_pipeline.py` passes on a clean clone
- [ ] No confidential extracts or secrets committed
- [ ] You can explain: WAPE vs MAPE, why rolling-origin CV, why direct multi-horizon,
      and how stockout risk is calculated

You submit once — Zidio guideline 4. Check everything before you press it.
