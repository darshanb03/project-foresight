"""
Reproduce the entire engagement end-to-end from the raw extracts.

    python run_all.py

This is the single command referred to in the README and in acceptance
criterion D1.3. A grader should be able to clone the repo, install
requirements, run this, and land on the same headline numbers.
"""

from __future__ import annotations

import json
import sys
import time

from src import config as C
from src import eda as E
from src import forecast as F
from src import pipeline as P
from src import risk as R


def main() -> int:
    t0 = time.time()

    if not (C.RAW_DIR / C.RAW_FILES["sales_daily"]).exists():
        print(
            "No extracts found in data/raw/.\n"
            "Either drop the four client CSVs there, or run:\n"
            "    python tools/generate_synthetic_data.py"
        )
        return 1

    print("[1/4] Pipeline: ingest, clean, aggregate, engineer features")
    out = P.run()
    print(f"      {out['log']['integrity']['weekly_rows']:,} weekly rows, "
          f"{out['log']['integrity']['skus_covered']} SKUs, "
          f"{out['log']['integrity']['weeks_covered']} weeks")

    print("[2/4] EDA: figures and insight numbers for the reports")
    eda_findings = E.run()
    print(f"      {len(eda_findings)} findings -> reports/eda_findings.json")

    print("[3/4] Forecast: baseline, rolling-origin backtest, 8-week forecast")
    f_out = F.run()
    bt = f_out["backtest"]
    print(f"      model WAPE {bt['mean_model_wape']:.4f} vs baseline {bt['mean_baseline_wape']:.4f} "
          f"({bt['improvement_vs_baseline_pct']:+.1f}%)")

    print("[4/4] Risk: stockout / overstock scoring and rupee impact")
    risk = R.run()
    summary = R.summarise(risk)
    print(f"      {summary['quadrant_counts']}")
    print(f"      value at stake Rs {summary['total_value_at_stake_inr']:,.0f}")

    headline = {
        "backtest": {
            "mean_model_wape": bt["mean_model_wape"],
            "mean_baseline_wape": bt["mean_baseline_wape"],
            "improvement_vs_baseline_pct": bt["improvement_vs_baseline_pct"],
            "model_beats_baseline": bt["model_beats_baseline"],
        },
        "risk": summary,
        "eda": eda_findings,
    }
    (C.REPORTS_DIR / "headline_results.json").write_text(json.dumps(headline, indent=2))

    print(f"\nDone in {time.time() - t0:.0f}s. Headline results -> reports/headline_results.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
