"""Checks on the committed map mask (data/surface/mask.npz): the cells inside the longleaf range."""

from pathlib import Path

import numpy as np
import pandas as pd

from pollen.geo import in_range, load_range
from pollen.surface import BOUNDS, GRID_STEP, load_grid, make_grid_axes

ROOT = Path(__file__).resolve().parents[1]


def shown(grid, lon, lat):
    return bool(grid.mask[np.abs(grid.lats - lat).argmin(), np.abs(grid.lons - lon).argmin()])


def test_mask_matches_the_grid_definition():
    grid = load_grid(ROOT / "data" / "surface" / "mask.npz")
    lons, lats = make_grid_axes(GRID_STEP, BOUNDS)
    assert np.array_equal(grid.lons, lons) and np.array_equal(grid.lats, lats)
    assert grid.mask.shape == (len(lats), len(lons))
    assert 10_000 < grid.mask.sum() < 40_000


def test_every_shown_cell_is_inside_the_range():
    grid = load_grid(ROOT / "data" / "surface" / "mask.npz")
    rings = load_range(ROOT / "data" / "range" / "pinupalu.geojson")
    rows, cols = np.nonzero(grid.mask)
    pick = np.random.default_rng(0).choice(len(rows), 150, replace=False)
    assert all(in_range(rings, grid.lons[cols[i]], grid.lats[rows[i]]) for i in pick)


def test_nothing_outside_the_range_is_shown():
    grid = load_grid(ROOT / "data" / "surface" / "mask.npz")
    assert not shown(grid, -88.0, 28.0)  # Gulf of Mexico
    assert not shown(grid, -70.0, 30.0)  # Atlantic
    assert not shown(grid, -90.0, 36.5)  # Missouri bootheel, far from the range
    assert not shown(grid, -86.5, 34.5)  # north Alabama, inside the bounds but outside the range
    assert shown(grid, -84.2, 31.2)  # Camilla, Georgia


def test_almost_every_station_in_the_range_is_on_a_shown_cell():
    grid = load_grid(ROOT / "data" / "surface" / "mask.npz")
    st = pd.read_csv(ROOT / "data" / "history" / "stations.csv")
    inside = st[st["in_range"]]
    ok = [shown(grid, r.lon, r.lat) for r in inside.itertuples()]
    assert np.mean(ok) > 0.95  # a few coastal or edge stations fall between cells
