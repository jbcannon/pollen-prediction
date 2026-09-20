import json
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pollen.history import load_history
from pollen.output import SCHEMA_VERSION, build_latest, build_series, write_outputs
from pollen.season import replay

STORE = Path(__file__).resolve().parents[1] / "data" / "history"
KW = {"season": 2026, "as_of": date(2026, 3, 5), "mode": "replay",
      "generated_at": "2026-09-20T00:00:00Z", "interval": 0.5, "analog_years": "2001-2025"}


def small_inputs():
    table = pd.DataFrame({
        "station": ["B", "A", "C"],
        "status": ["forecast", "crossed", "no_data"],
        "data_through": pd.to_datetime(["2026-03-05", "2026-03-05", None]),
        "days_behind": [0, 0, None],
        "filled_days": [0, 2, None],
        "cum_heat": [5120.4, 20000.0, np.nan],
        "required_heat": [13296.4, 13296.4, np.nan],
        "crossing_date": pd.to_datetime([None, "2026-02-18", None]),
        "earliest": pd.to_datetime(["2026-04-20", None, None]),
        "median": pd.to_datetime(["2026-04-23", None, None]),
        "latest": pd.to_datetime(["2026-04-26", None, None]),
        "n_scenarios": [3, None, None],
        "n_not_crossed": [0, None, None],
    })
    stations = pd.DataFrame({
        "id": ["A", "B", "C"], "network": ["GA_ASOS"] * 3, "name": ["Alpha", "Bravo", "Charlie"],
        "state": ["GA", "GA", "FL"], "lat": [31.12345678, 32.0, 30.0], "lon": [-84.1, -84.2, -85.0],
        "elevation_m": [60.4, 61.0, 5.0], "in_range": [True, True, False],
        "km_outside": [0.0, 0.0, 12.34], "n_seasons": [26, 20, 17],
    })
    return table, stations


def test_latest_records_are_sorted_typed_and_null_safe():
    table, stations = small_inputs()
    latest = build_latest(table, stations, **KW)
    assert latest["schema"] == SCHEMA_VERSION
    assert [s["id"] for s in latest["stations"]] == ["A", "B", "C"]
    a, b, c = latest["stations"]
    assert a["status"] == "crossed" and a["crossing_date"] == "2026-02-18"
    assert a["peak_date"] == "2026-02-18" and a["forecast_median"] is None
    assert b["peak_date"] == "2026-04-23" and b["crossing_date"] is None
    assert b["forecast_earliest"] == "2026-04-20" and b["n_scenarios"] == 3
    assert c["status"] == "no_data" and c["peak_date"] is None and c["cum_heat"] is None
    assert b["cum_heat"] == 5120 and isinstance(b["cum_heat"], int)
    assert a["lat"] == 31.1235 and c["km_outside"] == 12.3
    assert a["in_range"] is True and c["in_range"] is False


def test_latest_summary_and_method():
    table, stations = small_inputs()
    latest = build_latest(table, stations, **KW)
    assert latest["summary"]["n_stations"] == 3
    assert latest["summary"]["status_counts"] == {"forecast": 1, "crossed": 1, "no_data": 1}
    assert latest["summary"]["peak_date_min"] == "2026-02-18"
    assert latest["summary"]["peak_date_max"] == "2026-04-23"
    assert latest["method"]["boyer_b0"] == 19009 and latest["method"]["boyer_b1"] == -89.26
    assert latest["as_of"] == "2026-03-05" and latest["mode"] == "replay"


def test_write_outputs_is_valid_json_without_nan(tmp_path):
    table, stations = small_inputs()
    latest = build_latest(table, stations, **KW)
    series = build_series({"B": {"cum": [1, 2], "band": None}}, season=2026, as_of=date(2026, 3, 5))
    sizes = write_outputs(tmp_path / "out", latest, series)
    assert set(sizes) == {"latest.json", "series.json"}
    back = json.loads((tmp_path / "out" / "latest.json").read_text(encoding="utf-8"))
    assert back["stations"][0]["id"] == "A"
    assert json.loads((tmp_path / "out" / "series.json").read_text())["cum_start"] == "2026-01-01"


def test_nan_that_slips_through_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="Out of range float"):
        write_outputs(tmp_path, {"x": float("nan")}, {})


def test_real_replay_produces_consistent_files(tmp_path):
    history = load_history(STORE / "daily.csv.gz")
    stations = pd.read_csv(STORE / "stations.csv")
    as_of = date(2026, 3, 5)
    table, series = replay(history, 2026, as_of, detail=True)
    latest = build_latest(table, stations, **{**KW, "as_of": as_of})
    doc = build_series(series, season=2026, as_of=as_of)
    sizes = write_outputs(tmp_path, latest, doc)

    assert latest["summary"]["status_counts"] == {"forecast": 188, "crossed": 84}
    assert sizes["latest.json"] < 200_000 and sizes["series.json"] < 1_500_000
    assert set(doc["stations"]) == {s["id"] for s in latest["stations"]}

    for rec in latest["stations"]:
        entry = doc["stations"][rec["id"]]
        through = date.fromisoformat(rec["data_through"])
        assert len(entry["cum"]) == through.timetuple().tm_yday  # Jan 1 .. data_through
        assert entry["cum"][-1] == rec["cum_heat"]
        if rec["status"] == "crossed":
            assert entry["band"] is None
            continue
        band = entry["band"]
        assert band["start"] == (pd.Timestamp(through) + pd.Timedelta(days=1)).date().isoformat()
        assert len(band["lo"]) == len(band["mid"]) == len(band["hi"]) > 0
        assert all(lo <= mid <= hi for lo, mid, hi in zip(band["lo"], band["mid"], band["hi"], strict=True))
        assert band["lo"][0] >= rec["cum_heat"]  # the future never subtracts heat
