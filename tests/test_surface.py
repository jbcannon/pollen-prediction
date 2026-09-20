import json
from datetime import date

import numpy as np
import pytest

from pollen import surface
from pollen.surface import Grid

RNG = np.random.default_rng(0)


def stations_on_a_slope(n=60, noise=0.0, seed=0):
    """Stations whose peak day rises 0.05 day per km north (a pure north-south gradient)."""
    rng = np.random.default_rng(seed)
    lon = rng.uniform(-92, -78, n)
    lat = rng.uniform(28, 36, n)
    yday = 60 + (lat - 28) * surface.KM_PER_DEG_LAT * 0.05 + rng.normal(0, noise, n)
    recs = []
    for i in range(n):
        d = date(2026, 1, 1).toordinal() + round(yday[i]) - 1
        recs.append({"id": f"S{i}", "lon": float(lon[i]), "lat": float(lat[i]),
                     "peak_date": date.fromordinal(d).isoformat()})
    return recs


def small_grid():
    lons = np.round(np.arange(-92, -78, 0.5), 3)
    lats = np.round(np.arange(28, 36, 0.5), 3)
    mask = np.ones((len(lats), len(lons)), dtype=bool)
    mask[:2, :4] = False  # a corner that is not shown
    return Grid(lons=lons, lats=lats, mask=mask)


def test_projection_scales_degrees_to_km():
    xy = surface.to_km([-85.0, -85.0], [31.75, 32.75])
    assert xy[1, 1] - xy[0, 1] == pytest.approx(surface.KM_PER_DEG_LAT)
    east = surface.to_km([-84.0], [31.75])[0, 0] - surface.to_km([-85.0], [31.75])[0, 0]
    assert east == pytest.approx(111.32 * np.cos(np.radians(31.75)))


def test_a_linear_field_is_reproduced_exactly_at_any_smoothing():
    lon = RNG.uniform(-92, -78, 40)
    lat = RNG.uniform(28, 36, 40)
    xy = surface.to_km(lon, lat)
    values = 50 + 0.03 * xy[:, 1] + 0.01 * xy[:, 0]
    model = surface.fit(xy, values, smoothing=1e4)
    probe = surface.to_km([-85.0, -80.0], [30.0, 34.0])
    assert model(probe) == pytest.approx(50 + 0.03 * probe[:, 1] + 0.01 * probe[:, 0], abs=1e-6)


def test_loo_errors_vanish_for_a_perfect_plane_and_grow_with_noise():
    clean = stations_on_a_slope(noise=0.0)
    xy = surface.to_km([s["lon"] for s in clean], [s["lat"] for s in clean])
    yd = np.array([date.fromisoformat(s["peak_date"]).timetuple().tm_yday for s in clean], dtype=float)
    # rounding to whole days leaves +-0.5 day of noise, so the error is small but not zero
    assert np.sqrt(np.mean(surface.loo_errors(xy, yd, 1e3) ** 2)) < 0.8
    noisy = stations_on_a_slope(noise=3.0, seed=1)
    xy2 = surface.to_km([s["lon"] for s in noisy], [s["lat"] for s in noisy])
    yd2 = np.array([date.fromisoformat(s["peak_date"]).timetuple().tm_yday for s in noisy], dtype=float)
    assert np.sqrt(np.mean(surface.loo_errors(xy2, yd2, 1e3) ** 2)) > 1.5


def test_noisy_data_prefers_more_smoothing_than_clean_data():
    def best(noise, seed):
        recs = stations_on_a_slope(n=80, noise=noise, seed=seed)
        xy = surface.to_km([s["lon"] for s in recs], [s["lat"] for s in recs])
        yd = np.array([date.fromisoformat(s["peak_date"]).timetuple().tm_yday for s in recs], dtype=float)
        return surface.choose_smoothing(xy, yd, candidates=(1e1, 1e3, 1e5, 1e7))[0]

    assert best(4.0, 2) >= best(0.0, 3)


def test_contour_levels_are_one_day_apart_by_default_and_any_step_on_request():
    daily = surface.contour_levels(59.4, 63.2, 2026)
    assert [y for _, y in daily] == [60, 61, 62, 63]
    five = surface.contour_levels(59, 100, 2026, step=5)  # 28 Feb .. 10 Apr
    assert [y for _, y in five] == [60, 65, 70, 75, 80, 85, 90, 95, 100]
    assert five[0][0].isoformat() == "2026-03-01" and five[-1][0].isoformat() == "2026-04-10"


def test_contour_tiers():
    assert surface.contour_tier(60) == "index"  # multiple of 15
    assert surface.contour_tier(65) == "five"  # multiple of 5 only
    assert surface.contour_tier(61) == "day"


def test_leap_years_give_the_right_dates_for_the_same_day_of_year():
    (d, y), *_ = surface.contour_levels(60, 60, 2028)  # day 60 of a leap year is 29 Feb
    assert (d.isoformat(), y) == ("2028-02-29", 60)


def test_surface_matches_the_slope_and_leaves_masked_cells_empty():
    grid = small_grid()
    recs = stations_on_a_slope(n=80)
    doc, _ = surface.build_surface(recs, grid, season=2026, as_of=date(2026, 3, 5),
                                          generated_at="2026-09-20T00:00:00Z", smoothing=1e3)
    vals = np.array([np.nan if v is None else v for v in doc["values"]]).reshape(len(grid.lats), len(grid.lons))
    vals = vals[::-1]  # back to south-first order to compare with the grid
    assert np.isnan(vals[:2, :4]).all() and np.isfinite(vals[2:, :]).all()
    expected = 60 + (grid.lats - 28) * surface.KM_PER_DEG_LAT * 0.05
    middle = vals[3:-1, 6:-2]
    assert np.abs(middle - expected[3:-1, None]).max() < 1.0


def test_contours_are_ordered_lines_inside_the_bounds_and_avoid_masked_cells():
    grid = small_grid()
    _, contours = surface.build_surface(stations_on_a_slope(n=80), grid, season=2026,
                                        as_of=date(2026, 3, 5), generated_at="x", smoothing=1e3)
    feats = contours["features"]
    assert feats and all(f["geometry"]["type"] == "MultiLineString" for f in feats)
    assert [f["properties"]["yday"] for f in feats] == sorted(f["properties"]["yday"] for f in feats)
    ydays = [f["properties"]["yday"] for f in feats]
    assert len(feats) >= 20 and ydays == sorted(set(ydays))
    # tiers follow the day-of-year rule, and all three tiers are present
    assert all(f["properties"]["tier"] == surface.contour_tier(f["properties"]["yday"]) for f in feats)
    assert {f["properties"]["tier"] for f in feats} == {"index", "five", "day"}
    assert all(f["properties"]["major"] == (f["properties"]["tier"] == "index") for f in feats)
    assert feats[0]["properties"]["label"].split()[1] in {"Feb", "Mar", "Apr", "May"}
    for f in feats:
        for line in f["geometry"]["coordinates"]:
            for lon, lat in line:
                assert grid.lons.min() - 0.5 <= lon <= grid.lons.max() + 0.5
                assert grid.lats.min() - 0.5 <= lat <= grid.lats.max() + 0.5


def test_document_shape_and_json_roundtrip(tmp_path):
    grid = small_grid()
    doc, contours = surface.build_surface(stations_on_a_slope(n=80), grid, season=2026,
                                          as_of=date(2026, 3, 5), generated_at="x")
    assert doc["schema"] == 1 and len(doc["values"]) == len(grid.lons) * len(grid.lats)
    assert doc["fit"]["smoothing_chosen_by_loo"] is True and doc["fit"]["n_stations"] == 80
    assert doc["grid"]["n_lon"] == len(grid.lons) and doc["grid"]["lat0"] == float(grid.lats[-1])
    sizes = surface.write_surface(tmp_path / "out", doc, contours)
    assert set(sizes) == {"surface.json", "contours.geojson"}
    assert json.loads((tmp_path / "out" / "surface.json").read_text())["range"] == doc["range"]


def test_too_few_stations_is_rejected():
    with pytest.raises(ValueError, match="at least 10"):
        surface.build_surface(stations_on_a_slope(n=5), small_grid(), season=2026,
                              as_of=date(2026, 3, 5), generated_at="x")


def test_stations_without_a_peak_date_are_skipped():
    recs = stations_on_a_slope(n=30)
    recs[0]["peak_date"] = None
    doc, _ = surface.build_surface(recs, small_grid(), season=2026, as_of=date(2026, 3, 5),
                                   generated_at="x", smoothing=1e3)
    assert doc["fit"]["n_stations"] == 29


def test_grid_saves_and_loads(tmp_path):
    g = small_grid()
    surface.save_grid(g, tmp_path / "mask.npz")
    back = surface.load_grid(tmp_path / "mask.npz")
    assert np.array_equal(back.mask, g.mask) and np.array_equal(back.lons, g.lons)
