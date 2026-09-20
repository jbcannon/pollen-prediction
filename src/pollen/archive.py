"""Finished seasons for the gallery: each past year's final map, built from the history store.

A past season needs no forecast: every station has had its whole Jan-May window, so the table is the day
each one crossed the Boyer line. It goes through the same code as a live run (``forecast_season`` with the
season's own readings, the surface fit and the contours), and is written in the same four-file format, so
the page can draw it with the same map. The season's own year is left out of its climatology (the fill for
medium gaps), as in a replay.

Everything here is deterministic: the same history gives byte-identical files.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from pollen.output import build_latest, build_series, write_outputs
from pollen.season import forecast_season, heat_table
from pollen.surface import build_surface, load_grid, write_surface

SCHEMA_VERSION = 1


def season_files(
    history: pd.DataFrame,
    stations: pd.DataFrame,
    year: int,
    out_dir: Path,
    mask_path: Path,
    table: pd.DataFrame | None = None,
    surface_smoothing: float | None = None,
) -> dict[str, Any]:
    """Write one finished season's four data files to ``out_dir``; returns its summary.

    ``table`` is ``heat_table(history)``, to reuse across seasons. The charts (``series.json``) are kept for
    the stations inside the longleaf range only, the ones the map draws; the others still shape the surface.
    """
    full = table if table is not None else heat_table(history)
    known = history[history["date"].dt.year == year]
    if known.empty:
        raise ValueError(f"no history for season {year}")
    as_of = date(year, 5, 31)
    live = heat_table(known).reindex(columns=stations["id"].tolist())
    analog = full[full.index.year != year]
    generated = f"{year}-06-01T00:00:00Z"  # fixed, so the files do not change when they are rebuilt
    tbl, series = forecast_season(live, analog, as_of, detail=True)
    latest = build_latest(
        tbl, stations, season=year, as_of=as_of, mode="archive", generated_at=generated,
        interval=0.5, analog_years="none (finished season)",
    )
    in_range = {s["id"] for s in latest["stations"] if s["in_range"]}
    series_doc = build_series({k: v for k, v in series.items() if k in in_range}, season=year, as_of=as_of)
    surface_doc, contours_doc = build_surface(
        latest["stations"], load_grid(Path(mask_path)), season=year, as_of=as_of, generated_at=generated,
        smoothing=surface_smoothing,
    )
    sizes = write_outputs(out_dir, latest, series_doc)
    sizes.update(write_surface(out_dir, surface_doc, contours_doc))
    return {**summarize(latest), "surface_range": surface_doc["range"], "bytes": sum(sizes.values())}


def summarize(latest: dict[str, Any]) -> dict[str, Any]:
    """One season's line for the gallery index.

    ``stations`` is how many stations had a crossing date, ``in_range`` how many of those are inside the
    longleaf range, and ``first``/``median``/``last`` are the earliest, middle and latest crossing dates
    among the in-range stations: when the peak came across the range.
    """
    crossed = [s for s in latest["stations"] if s["crossing_date"]]
    dates = sorted(s["crossing_date"] for s in crossed if s["in_range"])
    out: dict[str, Any] = {"year": latest["season"], "stations": len(crossed), "in_range": len(dates),
                           "first": None, "median": None, "last": None}
    if dates:
        ordinals = sorted(date.fromisoformat(d).toordinal() for d in dates)
        out.update(first=dates[0], median=date.fromordinal(ordinals[len(ordinals) // 2]).isoformat(), last=dates[-1])
    return out


def write_index(root: Path, summaries: list[dict[str, Any]], scale: dict[str, int]) -> Path:
    """``seasons/index.json``: one line per season, newest first, plus the color scale shared by all of them."""
    seasons = sorted(({k: v for k, v in s.items() if k not in ("surface_range", "bytes")} for s in summaries),
                     key=lambda s: -s["year"])
    doc = {"schema": SCHEMA_VERSION, "scale": scale, "seasons": seasons}
    root.mkdir(parents=True, exist_ok=True)
    path = root / "index.json"
    path.write_text(json.dumps(doc, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    return path


def shared_scale(summaries: list[dict[str, Any]], step: int = 5) -> dict[str, int]:
    """Day-of-year range covering every season's surface, rounded outward to ``step`` days."""
    lo = min(s["surface_range"]["min"] for s in summaries)
    hi = max(s["surface_range"]["max"] for s in summaries)
    return {"lo": int(lo // step * step), "hi": int(-(-hi // step) * step)}
