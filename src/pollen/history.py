"""Analog-year history store: daily Jan-May max/min temperature per station.

The store keeps the observations as reported (deg F). Missing days are explicit
NaN rows and nothing is interpolated, so the file is an honest record; gaps of a
few days are filled when the heat sums are computed (see ``station_heat``).
"""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import pandas as pd

from pollen.heatsum import daily_heat, fill_short_gaps
from pollen.iem import fetch_daily

SEASON_END = (5, 31)  # the season window is Jan 1 - May 31
GAP_LIMIT = 3  # longest run of missing days that is interpolated
MIN_NEW_SEASON_SHARE = 0.95  # recent seasons are 98.6% or better
MAX_LOST_SHARE = 0.01  # of the readings the stored history already had


def check_update(old: pd.DataFrame | None, new: pd.DataFrame, last_year: int) -> None:
    """Refuse to overwrite the store with a broken download."""
    share = new.loc[new["date"].dt.year == last_year, "tmax"].notna().mean()
    if share < MIN_NEW_SEASON_SHARE:
        raise SystemExit(f"the {last_year} season is only {share:.1%} complete; not writing anything")
    if old is not None:
        had = old.dropna(subset=["tmax"])[["station", "date"]]
        now = new.dropna(subset=["tmax"])[["station", "date"]]
        lost = len(had.merge(now, how="left", indicator=True).query("_merge == 'left_only'")) / len(had)
        if lost > MAX_LOST_SHARE:
            raise SystemExit(f"{lost:.1%} of the stored readings are missing from the new download; not writing anything")


def last_complete_year(today: date) -> int:
    """Latest year whose Jan-May season is fully in the past (this year counts from June 1)."""
    return today.year if today >= date(today.year, 6, 1) else today.year - 1


def season_days(year: int) -> pd.DatetimeIndex:
    return pd.date_range(f"{year}-01-01", f"{year}-05-31")


def _daily_for(
    network: str, station: str, first_year: int, last_year: int, cache_dir: Path | None, pause: float
) -> pd.DataFrame:
    """One station's daily tmax/tmin, from the on-disk cache if it covers the window, else IEM."""
    need_end = pd.Timestamp(year=last_year, month=SEASON_END[0], day=SEASON_END[1])
    path = cache_dir / f"{network}_{station}.csv" if cache_dir else None
    if path is not None and path.exists():
        cached = pd.read_csv(path, index_col="date", parse_dates=["date"])
        if len(cached) and cached.index.max() >= need_end:
            return cached[["tmax", "tmin"]]
    raw = fetch_daily(station, network, date(first_year, 1, 1), need_end.date())
    if path is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        raw.to_csv(path)
    time.sleep(pause)
    return raw


def build_history(
    stations: pd.DataFrame,
    first_year: int,
    last_year: int,
    cache_dir: Path | None = None,
    pause: float = 0.25,
) -> pd.DataFrame:
    """Daily tmax/tmin for every station and every Jan-May day, ``first_year`` to ``last_year``.

    ``stations`` needs columns ``id`` (IEM station id) and ``network``. Returns a
    long table with columns ``station, date, tmax, tmin``; days with no report are
    kept as NaN rows so completeness is visible.
    """
    if stations["id"].duplicated().any():
        raise ValueError("station ids must be unique across networks")
    index = season_days(first_year)
    if last_year > first_year:
        index = index.append([season_days(y) for y in range(first_year + 1, last_year + 1)])
    frames = []
    for row in stations.itertuples():
        daily = _daily_for(row.network, row.id, first_year, last_year, cache_dir, pause)
        d = daily.reindex(index)
        d.index.name = "date"
        d.insert(0, "station", row.id)
        frames.append(d.reset_index())
    out = pd.concat(frames, ignore_index=True)
    out[["tmax", "tmin"]] = out[["tmax", "tmin"]].round(1)
    # Sorted, so the stored file is identical however the station list happens to be ordered.
    return out.sort_values(["station", "date"], kind="stable").reset_index(drop=True)


def save_history(history: pd.DataFrame, path: Path) -> None:
    """Write gzip CSV. ``mtime=0`` keeps the bytes identical when the data is unchanged."""
    path.parent.mkdir(parents=True, exist_ok=True)
    history.to_csv(
        path, index=False, date_format="%Y-%m-%d", compression={"method": "gzip", "mtime": 0}
    )


def load_history(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=["date"])


def station_heat(history: pd.DataFrame, station: str, gap_limit: int = GAP_LIMIT) -> pd.Series:
    """Daily heat sums for one station, indexed by date, with short gaps interpolated."""
    g = history[history["station"] == station].set_index("date").sort_index()
    return fill_short_gaps(daily_heat(g[["tmax", "tmin"]]), limit=gap_limit)


def complete_seasons(history: pd.DataFrame, gap_limit: int = GAP_LIMIT) -> pd.DataFrame:
    """Bool table (rows = station, columns = year): a heat value on every Jan-May day
    once gaps of up to ``gap_limit`` days are filled."""
    rows = {}
    for station, g in history.groupby("station"):
        g = g.set_index("date").sort_index()
        heat = fill_short_gaps(daily_heat(g[["tmax", "tmin"]]), limit=gap_limit)
        rows[station] = heat.notna().groupby(heat.index.year).all()
    return pd.DataFrame(rows).T
