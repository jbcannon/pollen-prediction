"""Rebuild the analog-year history store with every complete Jan-May season since 2001.

Reads the frozen station list (data/history/stations.csv), gets daily max/min for each station from IEM,
and rewrites:

  data/history/daily.csv.gz   station, date, tmax, tmin (deg F), blank where unreported
  data/history/stations.csv   the same stations, with each one's count of complete seasons refreshed

The extend-history workflow (.github/workflows/extend-history.yml) runs it every 2 June, once the season has
finished, and commits the two files. By hand:

    uv run python scripts/build_history.py

Nothing is written if the result looks wrong: the newest season under 95% complete (an IEM outage), or the
old seasons losing readings they had before.

It fetches each station's full record one at a time (a few minutes). If a folder of earlier downloads
exists at notes/research/stations/cache (only on the maintainer's machine) it is used to skip the download.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from pollen.history import (
    build_history,
    check_update,
    complete_seasons,
    last_complete_year,
    load_history,
    save_history,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "history"
CACHE = ROOT / "notes" / "research" / "stations" / "cache"
FIRST_YEAR = 2001


def main():
    sys.stdout.reconfigure(line_buffering=True)
    stations = pd.read_csv(OUT / "stations.csv")
    last_year = last_complete_year(datetime.now(UTC).date())
    print(f"{len(stations)} stations, seasons {FIRST_YEAR}-{last_year}")

    old = load_history(OUT / "daily.csv.gz") if (OUT / "daily.csv.gz").exists() else None
    history = build_history(stations, FIRST_YEAR, last_year, cache_dir=CACHE if CACHE.exists() else None)
    check_update(old, history, last_year)
    seasons = complete_seasons(history)
    stations["n_seasons"] = stations["id"].map(seasons.sum(axis=1)).astype(int)

    save_history(history, OUT / "daily.csv.gz")
    stations.to_csv(OUT / "stations.csv", index=False)
    size_mb = (OUT / "daily.csv.gz").stat().st_size / 1e6
    print(f"wrote {OUT / 'stations.csv'} and daily.csv.gz ({len(history):,} rows, {size_mb:.1f} MB)")
    print("seasons per station:", stations.n_seasons.describe().round(1).to_dict())


if __name__ == "__main__":
    main()
