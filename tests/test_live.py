import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from pollen.history import load_history
from pollen.live import LiveDataError, plan, run_live
from pollen.season import replay

STORE = Path(__file__).resolve().parents[1] / "data" / "history"
MASK = Path(__file__).resolve().parents[1] / "data" / "surface" / "mask.npz"
TODAY = date(2026, 3, 6)  # so the season is 2026 and the last day is 5 March


@pytest.fixture(scope="module")
def history():
    return load_history(STORE / "daily.csv.gz")


@pytest.fixture(scope="module")
def stations():
    return pd.read_csv(STORE / "stations.csv")


def store_as_iem(history):
    """A stand-in for IEM that answers from the history store."""
    def fetch(network, ids, start, end):
        rows = history[history["station"].isin(ids) & history["date"].between(pd.Timestamp(start), pd.Timestamp(end))]
        return rows[["station", "date", "tmax", "tmin"]].reset_index(drop=True)

    return fetch


def test_plan_follows_the_calendar():
    assert plan(date(2026, 3, 6)) == ("live", 2026, date(2026, 3, 5))
    assert plan(date(2026, 5, 31)) == ("live", 2026, date(2026, 5, 30))
    assert plan(date(2027, 1, 2)) == ("live", 2027, date(2027, 1, 1))  # the new season begins
    # once the season is over the map looks ahead to the next one, with no readings yet
    assert plan(date(2026, 6, 1)) == ("outlook", 2027, date(2026, 12, 31))
    assert plan(date(2026, 9, 20)) == ("outlook", 2027, date(2026, 12, 31))
    assert plan(date(2027, 1, 1)) == ("outlook", 2027, date(2026, 12, 31))


@pytest.fixture(scope="module")
def live_run(history, stations, tmp_path_factory):
    out = tmp_path_factory.mktemp("live")
    result = run_live(history, stations, TODAY, out, mask_path=MASK, fetch_many=store_as_iem(history),
                      generated_at="2026-03-06T10:00:00Z", surface_smoothing=31623.0)
    return out, result


def test_live_matches_a_replay_with_the_same_rules_station_by_station(history, live_run):
    out, _ = live_run
    latest = json.loads((out / "latest.json").read_text())
    expected = replay(history, 2026, date(2026, 3, 5), analogs="prior", window=10)
    by_id = {s["id"]: s for s in latest["stations"]}
    assert len(by_id) == len(expected) == 272
    for row in expected.to_dict("records"):
        got = by_id[row["station"]]
        assert got["status"] == row["status"]
        if row["status"] == "crossed":
            assert got["crossing_date"] == row["crossing_date"].date().isoformat()
        elif row["status"] == "forecast":
            assert got["forecast_median"] == row["median"].date().isoformat()
            assert got["forecast_earliest"] == row["earliest"].date().isoformat()
            assert got["n_scenarios"] == row["n_scenarios"]


def test_live_files_say_live_and_use_the_last_ten_seasons(live_run):
    out, result = live_run
    latest = json.loads((out / "latest.json").read_text())
    assert latest["mode"] == "live" and latest["season"] == 2026 and latest["as_of"] == "2026-03-05"
    assert latest["method"]["analog_years"] == "2016-2025" == result["analog_years"]
    assert result["coverage"] == 1.0 and result["failed_networks"] == []
    assert {"latest.json", "series.json", "surface.json", "contours.geojson"} <= {p.name for p in out.iterdir()}
    assert json.loads((out / "surface.json").read_text())["fit"]["n_stations"] > 200


def test_running_twice_gives_identical_files(history, stations, live_run, tmp_path):
    out, _ = live_run
    run_live(history, stations, TODAY, tmp_path, mask_path=None, fetch_many=store_as_iem(history),
             generated_at="2026-03-06T10:00:00Z")
    for name in ("latest.json", "series.json"):
        assert (tmp_path / name).read_bytes() == (out / name).read_bytes()


def test_one_failed_network_is_reported_and_its_stations_show_no_data(history, stations, tmp_path):
    tn = stations[stations["network"] == "TN_ASOS"]["id"].tolist()
    assert tn  # the store has a Tennessee station
    good = store_as_iem(history)

    def fetch(network, ids, start, end):
        if network == "TN_ASOS":
            raise ConnectionError("IEM timed out")
        return good(network, ids, start, end)

    result = run_live(history, stations, TODAY, tmp_path, fetch_many=fetch)
    assert result["failed_networks"] == ["TN_ASOS (ConnectionError)"]
    latest = json.loads((tmp_path / "latest.json").read_text())
    assert {s["status"] for s in latest["stations"] if s["id"] in tn} == {"no_data"}


def test_too_few_reporting_stations_publishes_nothing(history, stations, tmp_path):
    good = store_as_iem(history)
    out = tmp_path / "site"

    def only_georgia(network, ids, start, end):
        return good(network, ids, start, end) if network == "GA_ASOS" else pd.DataFrame(
            columns=["station", "date", "tmax", "tmin"])

    with pytest.raises(LiveDataError, match="stations reported"):
        run_live(history, stations, TODAY, out, fetch_many=only_georgia)
    assert not out.exists()  # nothing was written, so yesterday's files would survive


def test_every_network_down_publishes_nothing(history, stations, tmp_path):
    def down(network, ids, start, end):
        raise ConnectionError("no route")

    with pytest.raises(LiveDataError, match="every network failed"):
        run_live(history, stations, TODAY, tmp_path / "site", fetch_many=down)
    assert not (tmp_path / "site").exists()


def test_a_season_with_no_earlier_history_is_refused(history, stations, tmp_path):
    # (only ~75% of stations have data as far back as 2001, so relax the coverage rule to reach this check)
    with pytest.raises(LiveDataError, match="no seasons"):
        run_live(history, stations, date(2001, 3, 6), tmp_path / "site", fetch_many=store_as_iem(history),
                 min_coverage=0.0)
    assert not (tmp_path / "site").exists()


def test_the_outlook_needs_no_readings_and_forecasts_every_station_from_recent_springs(history, stations, tmp_path):
    def no_network(*args):
        raise AssertionError("an outlook must not download anything")

    result = run_live(history, stations, date(2026, 9, 20), tmp_path, fetch_many=no_network,
                      generated_at="2026-09-20T10:00:00Z")
    assert result["mode"] == "outlook" and result["season"] == 2027
    latest = json.loads((tmp_path / "latest.json").read_text())
    assert latest["mode"] == "outlook" and latest["season"] == 2027 and latest["as_of"] == "2026-12-31"
    assert latest["method"]["analog_years"] == "2017-2026"
    assert latest["summary"]["status_counts"] == {"forecast": len(stations)}
    for s in latest["stations"]:
        assert s["cum_heat"] == 0 and s["data_through"] is None and s["crossing_date"] is None
        assert "2027-01-01" < s["forecast_median"] < "2027-06-01" and 6 <= s["n_scenarios"] <= 10  # analog years with gaps are skipped
        assert s["forecast_earliest"] <= s["forecast_median"] <= s["forecast_latest"]
    series = json.loads((tmp_path / "series.json").read_text())
    aby = series["stations"]["ABY"]
    assert aby["cum"] == [] and aby["band"]["start"] == "2027-01-01"
