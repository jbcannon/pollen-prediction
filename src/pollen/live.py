"""Live mode: this season's readings from IEM, forecast with the same code as a replay.

Only the data loading differs from ``season.replay``. The season's daily max/min come from IEM
(one request per network), and the analog years are the most recent ``ANALOG_WINDOW`` complete
seasons in the history store. If the data looks broken the run raises ``LiveDataError`` before
writing anything, so the previous outputs stay in place.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from pollen import iem
from pollen.output import build_latest, build_series, write_outputs
from pollen.season import ANALOG_WINDOW, forecast_outlook, forecast_season, heat_table
from pollen.surface import build_surface, load_grid, write_surface

MIN_COVERAGE = 0.9  # share of stations that must report something, or the run fails

FetchMany = Callable[[str, list[str], date, date], pd.DataFrame]


class LiveDataError(RuntimeError):
    """The live data is too incomplete to publish."""


def plan(today: date) -> tuple[str, int, date]:
    """What to publish: ``(mode, season, as_of)``.

    From 2 January to 31 May the season is live and the last day is yesterday. From June to
    1 January the season is over, so the map shows the *next* season's outlook: no readings yet
    (``as_of`` is the 31 December before it), forecast from the recent analog years alone.
    """
    if today.month >= 6 or (today.month == 1 and today.day == 1):
        season = today.year + 1 if today.month >= 6 else today.year
        return "outlook", season, date(season - 1, 12, 31)
    yesterday = today - timedelta(days=1)
    return "live", today.year, min(yesterday, date(today.year, 5, 31))


def fetch_season(
    stations: pd.DataFrame,
    season: int,
    as_of: date,
    fetch_many: FetchMany = iem.fetch_daily_many,
) -> tuple[pd.DataFrame, list[str]]:
    """This season's daily max/min for every station, plus the networks that failed.

    Returns a long table (``station, date, tmax, tmin``) from 1 January to ``as_of`` and the
    list of network ids whose request failed after retries.
    """
    frames, failed = [], []
    for network, group in stations.groupby("network"):
        try:
            frames.append(fetch_many(str(network), group["id"].tolist(), date(season, 1, 1), as_of))
        except (OSError, ValueError) as exc:  # requests errors are OSError subclasses
            failed.append(f"{network} ({type(exc).__name__})")
    if not frames:
        raise LiveDataError(f"no data came back; every network failed: {failed}")
    live = pd.concat(frames, ignore_index=True)
    live = live[live["station"].isin(stations["id"])]
    live["date"] = pd.to_datetime(live["date"])
    return live[live["date"] <= pd.Timestamp(as_of)], failed


def run_live(
    history: pd.DataFrame,
    stations: pd.DataFrame,
    today: date,
    out_dir: Path,
    mask_path: Path | None = None,
    fetch_many: FetchMany = iem.fetch_daily_many,
    analog_window: int = ANALOG_WINDOW,
    min_coverage: float = MIN_COVERAGE,
    generated_at: str | None = None,
    surface_smoothing: float | None = None,
) -> dict[str, Any]:
    """Fetch the season, forecast every station, and write the site's data files.

    Everything is computed before anything is written. Returns a summary (season, as-of day,
    coverage, status counts, file sizes, failed networks).
    """
    mode, season, as_of = plan(today)
    if mode == "live":
        live_long, failed = fetch_season(stations, season, as_of, fetch_many)
        reporting = live_long.dropna(subset=["tmax", "tmin"], how="all")["station"].nunique()
        coverage = reporting / len(stations)
        if coverage < min_coverage:
            raise LiveDataError(
                f"only {reporting} of {len(stations)} stations reported ({coverage:.0%}, need "
                f"{min_coverage:.0%}); failed networks: {failed or 'none'}"
            )
    else:  # the outlook needs no readings
        live_long, failed, reporting, coverage = None, [], len(stations), 1.0

    full = heat_table(history)
    years = full.index.year
    analog = full[(years < season) & (years >= season - analog_window)]
    if analog.empty:
        raise LiveDataError(f"the history store has no seasons in the {analog_window} years before {season}")
    if mode == "live":
        live = heat_table(live_long).reindex(columns=stations["id"].tolist())
        table, series = forecast_season(live, analog, as_of, detail=True)
    else:
        table, series = forecast_outlook(analog, stations["id"].tolist(), season, detail=True)
    generated = generated_at or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    first, last = int(analog.index.year.min()), int(analog.index.year.max())
    latest = build_latest(
        table, stations, season=season, as_of=as_of, mode=mode, generated_at=generated,
        interval=0.5, analog_years=f"{first}-{last}",
    )
    series_doc = build_series(series, season=season, as_of=as_of)
    surface_docs = None
    if mask_path is not None and Path(mask_path).exists():
        surface_docs = build_surface(
            latest["stations"], load_grid(Path(mask_path)), season=season, as_of=as_of,
            generated_at=generated, smoothing=surface_smoothing,
        )

    sizes = write_outputs(out_dir, latest, series_doc)
    if surface_docs is not None:
        sizes.update(write_surface(out_dir, *surface_docs))
    return {
        "mode": mode,
        "season": season,
        "as_of": as_of,
        "coverage": coverage,
        "reporting_stations": reporting,
        "status_counts": latest["summary"]["status_counts"],
        "analog_years": f"{first}-{last}",
        "failed_networks": failed,
        "sizes": sizes,
        "surface_fit": surface_docs[0]["fit"] if surface_docs else None,
    }
