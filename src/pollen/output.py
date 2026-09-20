"""The JSON files the website reads. See docs/data-format.md for the field-by-field description.

``latest.json`` has one small record per station and is enough to draw the map.
``series.json`` holds the chart data (daily accumulated heat and the forecast band) and
can load after first paint.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from pollen.boyer import B0, B1
from pollen.heatsum import BASE_TEMP_F

SCHEMA_VERSION = 1


def _missing(value: Any) -> bool:
    return value is None or bool(pd.isna(value))


def _iso(value: Any) -> str | None:
    return None if _missing(value) else pd.Timestamp(value).date().isoformat()


def _int(value: Any) -> int | None:
    return None if _missing(value) else round(float(value))


def _round(value: Any, digits: int) -> float | None:
    return None if _missing(value) else round(float(value), digits)


def build_latest(
    table: pd.DataFrame,
    stations: pd.DataFrame,
    *,
    season: int,
    as_of: date,
    mode: str,
    generated_at: str,
    interval: float,
    analog_years: str,
) -> dict[str, Any]:
    """Assemble ``latest.json`` from a forecast table and the station list.

    ``table`` is the output of ``forecast_season``; ``stations`` is data/history/stations.csv.
    ``mode`` is ``"live"`` or ``"replay"``. ``analog_years`` is a human-readable label such as
    ``"2001-2025"``.
    """
    merged = table.merge(stations, left_on="station", right_on="id", how="left")
    records = []
    for r in merged.to_dict("records"):
        crossed = r["status"] == "crossed"
        records.append(
            {
                "id": r["station"],
                "name": r["name"],
                "state": r["state"],
                "lat": _round(r["lat"], 4),
                "lon": _round(r["lon"], 4),
                "elevation_m": _int(r["elevation_m"]),
                "in_range": bool(r["in_range"]),
                "km_outside": _round(r["km_outside"], 1),
                "n_seasons": _int(r["n_seasons"]),
                "status": r["status"],
                "data_through": _iso(r["data_through"]),
                "days_behind": _int(r["days_behind"]),
                "filled_days": _int(r["filled_days"]),
                "cum_heat": _int(r["cum_heat"]),
                "required_heat": _int(r["required_heat"]),
                "crossing_date": _iso(r["crossing_date"]),
                "forecast_earliest": _iso(r["earliest"]),
                "forecast_median": _iso(r["median"]),
                "forecast_latest": _iso(r["latest"]),
                "n_scenarios": _int(r["n_scenarios"]),
                "n_not_crossed": _int(r["n_not_crossed"]),
                "peak_date": _iso(r["crossing_date"] if crossed else r["median"]),
            }
        )
    records.sort(key=lambda rec: rec["id"])
    peaks = [rec["peak_date"] for rec in records if rec["peak_date"]]
    return {
        "schema": SCHEMA_VERSION,
        "season": season,
        "as_of": as_of.isoformat(),
        "generated_at": generated_at,
        "mode": mode,
        "method": {
            "base_temp_f": BASE_TEMP_F,
            "boyer_b0": B0,
            "boyer_b1": B1,
            "forecast_interval": interval,
            "analog_years": analog_years,
            "daily_mean": "(max+min)/2",
            "source": "IEM airport stations (ASOS/AWOS)",
        },
        "summary": {
            "n_stations": len(records),
            "status_counts": {k: int(v) for k, v in table["status"].value_counts().items()},
            "peak_date_min": min(peaks) if peaks else None,
            "peak_date_max": max(peaks) if peaks else None,
        },
        "stations": records,
    }


def build_series(
    series: dict[str, dict[str, Any]], *, season: int, as_of: date
) -> dict[str, Any]:
    """Assemble ``series.json`` from the ``detail`` output of ``forecast_season``."""
    return {
        "schema": SCHEMA_VERSION,
        "season": season,
        "as_of": as_of.isoformat(),
        "cum_start": f"{season}-01-01",
        "stations": {k: series[k] for k in sorted(series)},
    }


def write_outputs(out_dir: Path, latest: dict, series: dict) -> dict[str, int]:
    """Write both files (compact JSON, no NaN) and return their sizes in bytes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for name, obj in (("latest.json", latest), ("series.json", series)):
        text = json.dumps(obj, separators=(",", ":"), allow_nan=False, ensure_ascii=False)
        (out_dir / name).write_text(text, encoding="utf-8")
        sizes[name] = len(text.encode("utf-8"))
    return sizes
