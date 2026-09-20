"""Turn station peak dates into a smooth map surface, contour lines and the JSON the site reads.

Each station has one date (when it crossed, or the median forecast). A thin-plate spline through
those dates, smoothed so that station-to-station noise does not become bumps, gives a value for
every map cell. How smooth is chosen by leave-one-out testing: hide each station in turn and see
how well the surface predicts it. The result is the "weather map" of peak dates.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import contourpy
import numpy as np
from scipy.interpolate import RBFInterpolator

from pollen.geo import KM_PER_DEG_LAT, KM_PER_DEG_LON_AT_EQUATOR

SCHEMA_VERSION = 1
CENTER_LAT = 31.75  # distances are measured on a flat map scaled at this latitude
GRID_STEP = 0.05  # degrees, about 5 km
BOUNDS = (-95.3, -75.7, 26.55, 36.95)  # lon_min, lon_max, lat_min, lat_max: the longleaf range plus a small margin
SMOOTHINGS = tuple(float(s) for s in np.logspace(1, 7, 13))
CONTOUR_STEP_DAYS = 1  # one contour line per day...
FIVE_DAY_LINES = 5  # ...every fifth one is a "five" line...
INDEX_DAY_LINES = 15  # ...and every fifteenth is an "index" line (heaviest, labelled)


@dataclass(frozen=True)
class Grid:
    """Cell centres (ascending) and which cells to show (True = show)."""

    lons: np.ndarray
    lats: np.ndarray
    mask: np.ndarray  # shape (n_lat, n_lon)


def make_grid_axes(step: float = GRID_STEP, bounds=BOUNDS) -> tuple[np.ndarray, np.ndarray]:
    lon_min, lon_max, lat_min, lat_max = bounds
    lons = np.round(np.arange(lon_min + step / 2, lon_max, step), 4)
    lats = np.round(np.arange(lat_min + step / 2, lat_max, step), 4)
    return lons, lats


def save_grid(grid: Grid, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, lons=grid.lons, lats=grid.lats, mask=grid.mask)


def load_grid(path: Path) -> Grid:
    with np.load(path) as z:
        return Grid(lons=z["lons"], lats=z["lats"], mask=z["mask"].astype(bool))


def to_km(lon, lat) -> np.ndarray:
    """(lon, lat) in degrees to flat-map (x, y) in km, shape (n, 2)."""
    lon, lat = np.asarray(lon, dtype=float), np.asarray(lat, dtype=float)
    kx = KM_PER_DEG_LON_AT_EQUATOR * np.cos(np.radians(CENTER_LAT))
    return np.column_stack([lon * kx, (lat - CENTER_LAT) * KM_PER_DEG_LAT])


def fit(xy: np.ndarray, values: np.ndarray, smoothing: float) -> RBFInterpolator:
    return RBFInterpolator(xy, values, kernel="thin_plate_spline", smoothing=smoothing)


def loo_errors(xy: np.ndarray, values: np.ndarray, smoothing: float) -> np.ndarray:
    """Leave-one-out prediction errors (predicted minus actual) for every station."""
    n = len(values)
    out = np.empty(n)
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        keep[i] = False
        out[i] = fit(xy[keep], values[keep], smoothing)(xy[i : i + 1])[0] - values[i]
        keep[i] = True
    return out


def choose_smoothing(
    xy: np.ndarray, values: np.ndarray, candidates=SMOOTHINGS
) -> tuple[float, dict[float, float]]:
    """Smoothing with the lowest leave-one-out RMSE, and the RMSE of every candidate."""
    rmse = {s: float(np.sqrt(np.mean(loo_errors(xy, values, s) ** 2))) for s in candidates}
    return min(rmse, key=rmse.get), rmse


def surface_values(model: RBFInterpolator, grid: Grid) -> np.ndarray:
    """Model value in every shown cell (NaN elsewhere), shape (n_lat, n_lon)."""
    lon_g, lat_g = np.meshgrid(grid.lons, grid.lats)
    out = np.full(lon_g.shape, np.nan)
    shown = grid.mask
    out[shown] = model(to_km(lon_g[shown], lat_g[shown]))
    return out


def contour_levels(
    lo_yday: float, hi_yday: float, year: int, step: int = CONTOUR_STEP_DAYS
) -> list[tuple[date, int]]:
    """Contour levels every ``step`` days between two days of the year, as (date, day-of-year).

    Levels sit on multiples of ``step`` in day-of-year, so spacing is exactly ``step`` days.
    """
    first = math.ceil(lo_yday / step) * step
    return [
        (date(year, 1, 1) + timedelta(days=yday - 1), yday)
        for yday in range(first, int(hi_yday) + 1, step)
    ]


def contour_tier(yday: int) -> str:
    """``index`` (every 15 days), ``five`` (every 5 days) or ``day`` (the rest)."""
    if yday % INDEX_DAY_LINES == 0:
        return "index"
    return "five" if yday % FIVE_DAY_LINES == 0 else "day"


def contour_features(values: np.ndarray, grid: Grid, levels: list[tuple[date, int]]) -> list[dict]:
    """GeoJSON features (one MultiLineString per level) for the given date levels."""
    gen = contourpy.contour_generator(
        grid.lons, grid.lats, np.ma.masked_invalid(values), line_type=contourpy.LineType.Separate
    )
    features = []
    for d, yday in levels:
        lines = [np.round(line, 3).tolist() for line in gen.lines(float(yday)) if len(line) > 1]
        if lines:
            features.append({
                "type": "Feature",
                "properties": {
                    "date": d.isoformat(),
                    "label": f"{d.day} {d:%b}",
                    "yday": yday,
                    "tier": contour_tier(yday),
                    "major": yday % INDEX_DAY_LINES == 0,
                },
                "geometry": {"type": "MultiLineString", "coordinates": lines},
            })
    return features


def build_surface(
    stations: list[dict[str, Any]],
    grid: Grid,
    *,
    season: int,
    as_of: date,
    generated_at: str,
    smoothing: float | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fit the surface to the stations' ``peak_date`` and return (surface doc, contours doc).

    ``stations`` are the records of latest.json. Stations without a ``peak_date`` are skipped.
    With ``smoothing=None`` the smoothness is chosen by leave-one-out testing.
    """
    use = [s for s in stations if s.get("peak_date")]
    if len(use) < 10:
        raise ValueError(f"need at least 10 stations with a peak date, got {len(use)}")
    xy = to_km([s["lon"] for s in use], [s["lat"] for s in use])
    values = np.array([date.fromisoformat(s["peak_date"]).timetuple().tm_yday for s in use], dtype=float)

    table = None
    if smoothing is None:
        smoothing, table = choose_smoothing(xy, values)
    errs = loo_errors(xy, values, smoothing)
    surface = surface_values(fit(xy, values, smoothing), grid)

    shown = surface[np.isfinite(surface)]
    levels = contour_levels(shown.min(), shown.max(), season)
    flat = np.round(surface[::-1], 1).ravel()  # row 0 = northernmost
    doc = {
        "schema": SCHEMA_VERSION,
        "season": season,
        "as_of": as_of.isoformat(),
        "generated_at": generated_at,
        "unit": f"day of year in {season} (1 = 1 Jan)",
        "grid": {
            "lon0": float(grid.lons[0]), "lat0": float(grid.lats[-1]), "step": GRID_STEP,
            "n_lon": len(grid.lons), "n_lat": len(grid.lats),
            "order": "cell centres; row 0 is the northernmost row; columns run west to east",
        },
        "fit": {
            "method": "thin-plate spline", "smoothing": smoothing, "n_stations": len(use),
            "loo_rmse_days": round(float(np.sqrt(np.mean(errs**2))), 2),
            "loo_mae_days": round(float(np.mean(np.abs(errs))), 2),
            "smoothing_chosen_by_loo": table is not None,
        },
        "range": {"min": round(float(shown.min()), 1), "max": round(float(shown.max()), 1)},
        "values": [None if not np.isfinite(v) else float(v) for v in flat],
    }
    contours = {"type": "FeatureCollection", "features": contour_features(surface, grid, levels)}
    return doc, contours


def write_surface(out_dir: Path, surface_doc: dict, contours_doc: dict) -> dict[str, int]:
    """Write surface.json and contours.geojson (compact, no NaN); returns sizes in bytes."""
    out_dir.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for name, obj in (("surface.json", surface_doc), ("contours.geojson", contours_doc)):
        text = json.dumps(obj, separators=(",", ":"), allow_nan=False)
        (out_dir / name).write_text(text, encoding="utf-8")
        sizes[name] = len(text.encode("utf-8"))
    return sizes
