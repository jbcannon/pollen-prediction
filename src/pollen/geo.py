"""Geometry helpers for the longleaf pine range polygon: point-in-polygon and distance to its edge."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

KM_PER_DEG_LAT = 110.95
KM_PER_DEG_LON_AT_EQUATOR = 111.32


def ring_contains(ring: np.ndarray, x: float, y: float) -> bool:
    """Ray casting point-in-polygon for one ring of (lon, lat)."""
    xs, ys = ring[:, 0], ring[:, 1]
    x2, y2 = np.roll(xs, -1), np.roll(ys, -1)
    crosses = (ys > y) != (y2 > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        x_at = xs + (y - ys) * (x2 - xs) / (y2 - ys)
    return bool(np.sum(crosses & (x < x_at)) % 2)


def load_range(path: Path) -> list[np.ndarray]:
    """Outer rings (lon, lat) of the range polygons in a GeoJSON file."""
    gj = json.loads(Path(path).read_text())
    return [np.array(f["geometry"]["coordinates"][0]) for f in gj["features"]]


def in_range(rings: list[np.ndarray], lon: float, lat: float) -> bool:
    return any(ring_contains(r, lon, lat) for r in rings)


def km_to_range(rings: list[np.ndarray], lon: float, lat: float) -> float:
    """Distance in km from a point to the range polygon edge (0 if inside).

    Uses a local flat approximation at the point's latitude, which is accurate to
    well under a percent at the ~100 km scale that matters here.
    """
    if in_range(rings, lon, lat):
        return 0.0
    kx, ky = KM_PER_DEG_LON_AT_EQUATOR * np.cos(np.radians(lat)), KM_PER_DEG_LAT
    best = np.inf
    for r in rings:
        x, y = (r[:, 0] - lon) * kx, (r[:, 1] - lat) * ky
        dx, dy = np.roll(x, -1) - x, np.roll(y, -1) - y
        seg = dx * dx + dy * dy
        with np.errstate(divide="ignore", invalid="ignore"):
            t = np.where(seg > 0, np.clip(-(x * dx + y * dy) / seg, 0, 1), 0.0)
        best = min(best, float(np.hypot(x + t * dx, y + t * dy).min()))
    return best
