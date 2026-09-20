"""Checks on the committed history store (data/history/)."""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from pollen.boyer import first_crossing_yday
from pollen.forecast import scenario_crossings, summarize_crossings
from pollen.history import complete_seasons, load_history, station_heat

STORE = Path(__file__).resolve().parents[1] / "data" / "history"


@pytest.fixture(scope="module")
def history():
    return load_history(STORE / "daily.csv.gz")


@pytest.fixture(scope="module")
def stations():
    return pd.read_csv(STORE / "stations.csv")


def crossing(heat: pd.Series, year: int) -> date:
    season = heat[heat.index.year == year]
    yday = first_crossing_yday(season.cumsum().to_numpy(), season.index.dayofyear)
    return date(year, 1, 1) + timedelta(days=yday - 1)


def test_store_covers_every_station_and_season(history, stations):
    assert set(history.station) == set(stations["id"])
    assert stations["id"].is_unique
    assert history.date.dt.year.min() == 2001
    assert not history.duplicated(["station", "date"]).any()
    per_station = history.groupby("station").size()
    assert per_station.nunique() == 1  # every station has a row for every season day
    assert (stations.n_seasons >= 15).all()
    assert stations.km_outside.max() <= 100


def test_store_only_holds_the_jan_to_may_window(history):
    md = history.date.dt.month
    assert md.between(1, 5).all()
    assert not ((md == 5) & (history.date.dt.day > 31)).any()


def test_albany_crossing_dates_match_the_earlier_analysis(history):
    # ABY (Albany, GA) is the airport nearest Camilla; these dates came from the same
    # IEM data before the store existed (Camilla's own station: 1 Mar, 13 Mar, 19 Mar, 10 Mar).
    heat = station_heat(history, "ABY")
    assert crossing(heat, 2023) == date(2023, 3, 1)
    assert crossing(heat, 2024) == date(2024, 3, 15)
    assert crossing(heat, 2025) == date(2025, 3, 17)
    assert crossing(heat, 2026) == date(2026, 3, 9)


def test_forecast_from_the_store_is_sane(history):
    heat = station_heat(history, "ABY")
    as_of = date(2026, 3, 1)
    cum = float(heat.loc["2026-01-01":str(as_of)].sum())
    analogs = heat[heat.index.year < 2026]
    rng = summarize_crossings(scenario_crossings(cum, as_of, analogs), interval=0.5)
    assert rng.n_scenarios == 25 and rng.n_not_crossed == 0
    assert date(2026, 3, 8) <= rng.earliest <= rng.median <= rng.latest <= date(2026, 3, 22)


def test_stored_season_counts_match_the_data(history, stations):
    sample = stations.sample(12, random_state=0)
    subset = history[history.station.isin(sample["id"])]
    counted = complete_seasons(subset).sum(axis=1)
    for row in sample.itertuples():
        assert counted[row.id] == row.n_seasons
