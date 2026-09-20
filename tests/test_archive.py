import json
from pathlib import Path

import pandas as pd
import pytest

from pollen import archive
from pollen.history import load_history

ROOT = Path(__file__).resolve().parents[1]
MASK = ROOT / "data" / "surface" / "mask.npz"


@pytest.fixture(scope="module")
def history():
    return load_history(ROOT / "data" / "history" / "daily.csv.gz")


@pytest.fixture(scope="module")
def stations():
    st = pd.read_csv(ROOT / "data" / "history" / "stations.csv")
    # a mix of stations inside and outside the range keeps the fit quick
    return pd.concat([st[st.in_range].head(45), st[~st.in_range].head(15)]).reset_index(drop=True)


@pytest.fixture(scope="module")
def season(history, stations, tmp_path_factory):
    out = tmp_path_factory.mktemp("s2012")
    summary = archive.season_files(history, stations, 2012, out, MASK, surface_smoothing=31623.0)
    return out, summary


def test_a_finished_season_is_written_in_the_live_format_with_mode_archive(season, stations):
    out, summary = season
    assert {p.name for p in out.iterdir()} == {"latest.json", "series.json", "surface.json", "contours.geojson"}
    latest = json.loads((out / "latest.json").read_text())
    assert latest["mode"] == "archive" and latest["season"] == 2012 and latest["as_of"] == "2012-05-31"
    assert latest["generated_at"] == "2012-06-01T00:00:00Z"  # fixed, so rebuilding changes nothing
    assert len(latest["stations"]) == len(stations)
    statuses = {s["status"] for s in latest["stations"]}
    assert statuses <= {"crossed", "insufficient_data", "no_data"}  # nothing is left to forecast
    assert all(s["crossing_date"] for s in latest["stations"] if s["status"] == "crossed")
    assert summary["first"] <= summary["median"] <= summary["last"] and summary["in_range"] > 30


def test_charts_are_kept_only_for_stations_inside_the_range(season):
    out, _ = season
    latest = json.loads((out / "latest.json").read_text())
    series = json.loads((out / "series.json").read_text())["stations"]
    inside = {s["id"] for s in latest["stations"] if s["in_range"] and s["status"] == "crossed"}
    assert set(series) == inside
    assert all(v["band"] is None and len(v["cum"]) > 30 for v in series.values())  # heat curve, no forecast band


def test_the_surface_covers_the_seasons_dates(season):
    out, summary = season
    surface = json.loads((out / "surface.json").read_text())
    assert surface["season"] == 2012
    assert 30 < surface["range"]["min"] < surface["range"]["max"] < 130
    assert summary["surface_range"] == surface["range"]


def test_rebuilding_a_season_gives_identical_files(history, stations, season, tmp_path):
    out, _ = season
    archive.season_files(history, stations, 2012, tmp_path, MASK, surface_smoothing=31623.0)
    for name in ("latest.json", "series.json", "surface.json", "contours.geojson"):
        assert (tmp_path / name).read_bytes() == (out / name).read_bytes()


def test_a_year_with_no_history_is_refused(history, stations, tmp_path):
    with pytest.raises(ValueError, match="no history for season 1990"):
        archive.season_files(history, stations, 1990, tmp_path, MASK)


def test_index_is_newest_first_and_the_shared_scale_rounds_outward(tmp_path):
    seasons = [
        {"year": 2001, "first": "2001-02-20", "median": "2001-03-23", "last": "2001-04-21", "range": {"min": 47.2, "max": 112.8}},
        {"year": 2003, "first": "2003-02-26", "median": "2003-03-26", "last": "2003-04-18", "range": {"min": 55.0, "max": 104.1}},
        {"year": 2002, "first": "2002-02-12", "median": "2002-03-20", "last": "2002-04-12", "range": {"min": 43.9, "max": 101.0}},
    ]
    scale = archive.shared_scale([{"surface_range": s["range"]} for s in seasons])
    assert scale == {"lo": 40, "hi": 115}
    doc = json.loads(archive.write_index(tmp_path, seasons, scale).read_text())
    assert [s["year"] for s in doc["seasons"]] == [2003, 2002, 2001] and doc["scale"] == scale
