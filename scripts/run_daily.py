"""The daily job: fetch this season from IEM, forecast every station, write the site's data files.

From June to 1 January there is no season to track, so it writes the next season's outlook instead: every station
starts at zero heat and is forecast from the last ten springs alone (mode "outlook" in latest.json).

Example:  uv run python scripts/run_daily.py --out site/data
          uv run python scripts/run_daily.py --today 2026-03-06 --out figures/live_test   (a dry run for a past day)

Exit code 1 (and nothing written) if the data is too incomplete to publish.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from pollen.history import load_history
from pollen.live import MIN_COVERAGE, LiveDataError, run_live

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--today", type=date.fromisoformat, default=None, help="pretend today is this date (UTC date by default)")
    p.add_argument("--out", type=Path, default=ROOT / "site" / "data", help="folder for latest.json, series.json, ...")
    p.add_argument("--history", type=Path, default=ROOT / "data" / "history")
    p.add_argument("--mask", type=Path, default=ROOT / "data" / "surface" / "mask.npz")
    p.add_argument("--min-coverage", type=float, default=MIN_COVERAGE)
    args = p.parse_args()

    today = args.today or datetime.now(UTC).date()
    history = load_history(args.history / "daily.csv.gz")
    stations = pd.read_csv(args.history / "stations.csv")
    try:
        result = run_live(history, stations, today, args.out, mask_path=args.mask, min_coverage=args.min_coverage)
    except LiveDataError as exc:
        print(f"NOT PUBLISHED: {exc}", file=sys.stderr)
        return 1

    if result["mode"] == "outlook":
        print(f"{result['season']} outlook (no readings yet), run on {today}")
    else:
        print(f"season {result['season']}, through {result['as_of']} (run on {today})")
        print(f"stations reporting: {result['reporting_stations']} ({result['coverage']:.0%})")
    print(f"status: {result['status_counts']}")
    print(f"analog years: {result['analog_years']}")
    if result["failed_networks"]:
        print("failed networks (their stations show as no data):", result["failed_networks"])
    if result["surface_fit"]:
        fit = result["surface_fit"]
        print(f"surface: leave-one-out error {fit['loo_mae_days']} days (mean), {fit['n_stations']} stations")
    for name, size in result["sizes"].items():
        print(f"  {args.out / name}  {size / 1000:,.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
