from datetime import date

import numpy as np
import pandas as pd
import pytest

from pollen import history

STATIONS = pd.DataFrame({"id": ["AAA", "BBB"], "network": ["GA_ASOS", "GA_ASOS"]})


def fake_daily(tmax=70.0, tmin=55.0, drop=()):
    """A fetch_daily stand-in: every day of 2001-2002 reports tmax/tmin except ``drop``."""
    days = pd.date_range("2001-01-01", "2002-12-31")
    df = pd.DataFrame({"tmax": tmax, "tmin": tmin}, index=pd.DatetimeIndex(days, name="date"))
    return df.drop(index=pd.DatetimeIndex(list(drop)))


@pytest.fixture
def fetched(monkeypatch):
    calls = []

    def fake_fetch(station, network, start, end):
        calls.append(station)
        return fake_daily(drop=["2001-02-10"] if station == "AAA" else [])

    monkeypatch.setattr(history, "fetch_daily", fake_fetch)
    return calls


def test_last_complete_year_rolls_over_on_june_1():
    assert history.last_complete_year(date(2026, 5, 31)) == 2025
    assert history.last_complete_year(date(2026, 6, 1)) == 2026
    assert history.last_complete_year(date(2027, 1, 15)) == 2026


def test_build_history_has_every_season_day_and_marks_missing(fetched):
    h = history.build_history(STATIONS, 2001, 2002, pause=0)
    # Jan 1 - May 31: 151 days in 2001, 151 in 2002 (neither is a leap year)
    assert len(h) == 2 * 302
    a = h[h.station == "AAA"].set_index("date")
    assert np.isnan(a.loc["2001-02-10", "tmax"])
    assert a.loc["2001-02-11", "tmax"] == 70.0
    assert not h[h.station == "BBB"][["tmax", "tmin"]].isna().any().any()


def test_leap_year_season_has_one_more_day():
    assert len(history.season_days(2024)) == len(history.season_days(2023)) + 1


def test_cache_is_used_and_skips_the_network(fetched, tmp_path):
    history.build_history(STATIONS, 2001, 2002, cache_dir=tmp_path, pause=0)
    assert sorted(fetched) == ["AAA", "BBB"]
    history.build_history(STATIONS, 2001, 2002, cache_dir=tmp_path, pause=0)
    assert sorted(fetched) == ["AAA", "BBB"]  # second build fetched nothing


def test_stale_cache_that_stops_early_is_refetched(fetched, tmp_path):
    short = fake_daily().loc[:"2001-12-31"]
    short.to_csv(tmp_path / "GA_ASOS_AAA.csv")
    history.build_history(STATIONS.iloc[:1], 2001, 2002, cache_dir=tmp_path, pause=0)
    assert fetched == ["AAA"]


def test_duplicate_station_ids_are_rejected():
    dup = pd.DataFrame({"id": ["AAA", "AAA"], "network": ["GA_ASOS", "FL_ASOS"]})
    with pytest.raises(ValueError, match="unique"):
        history.build_history(dup, 2001, 2001, pause=0)


def test_save_and_load_roundtrip_is_byte_stable(fetched, tmp_path):
    h = history.build_history(STATIONS, 2001, 2002, pause=0)
    # gzip records the file name in its header, so compare the same name in two folders
    history.save_history(h, tmp_path / "one" / "daily.csv.gz")
    history.save_history(h, tmp_path / "two" / "daily.csv.gz")
    assert (tmp_path / "one" / "daily.csv.gz").read_bytes() == (tmp_path / "two" / "daily.csv.gz").read_bytes()
    back = history.load_history(tmp_path / "one" / "daily.csv.gz")
    pd.testing.assert_frame_equal(back, h, check_dtype=False)


def test_complete_seasons_fills_short_gaps_but_not_long_ones(fetched):
    h = history.build_history(STATIONS, 2001, 2002, pause=0)
    h.loc[(h.station == "BBB") & h.date.between("2002-03-01", "2002-03-05"), ["tmax", "tmin"]] = np.nan
    seasons = history.complete_seasons(h)
    assert seasons.loc["AAA", 2001]  # 1-day gap is filled
    assert seasons.loc["BBB", 2001]
    assert not seasons.loc["BBB", 2002]  # 5-day gap is too long
    assert seasons.loc["AAA", 2002]


def test_station_heat_is_indexed_by_date_and_filled(fetched):
    h = history.build_history(STATIONS, 2001, 2001, pause=0)
    heat = history.station_heat(h, "AAA")
    assert heat.index[0] == pd.Timestamp("2001-01-01")
    assert heat.notna().all()
    # tmax 70 / tmin 55: whole day above 50, mean 62.5 -> (62.5 - 50) * 24 = 300
    assert heat.iloc[0] == pytest.approx(300.0)


def _store(years, share=1.0):
    """A small two-station store: `share` of each year's days have a reading."""
    rows = []
    for year in years:
        days = history.season_days(year)
        for station in ("AAA", "BBB"):
            df = pd.DataFrame({"station": station, "date": days, "tmax": 70.0, "tmin": 50.0})
            df.loc[int(len(df) * share):, ["tmax", "tmin"]] = float("nan")
            rows.append(df)
    return pd.concat(rows, ignore_index=True)


def test_update_check_accepts_a_normal_new_season():
    old = _store([2024, 2025])
    history.check_update(old, _store([2024, 2025, 2026]), 2026)


def test_update_check_refuses_an_incomplete_new_season():
    old = _store([2024, 2025])
    with pytest.raises(SystemExit, match="2026 season is only"):
        history.check_update(old, pd.concat([_store([2024, 2025]), _store([2026], share=0.5)]), 2026)


def test_update_check_refuses_a_download_that_loses_old_readings():
    old = _store([2024, 2025])
    with pytest.raises(SystemExit, match="missing from the new download"):
        history.check_update(old, pd.concat([_store([2024], share=0.5), _store([2025, 2026])]), 2026)


def test_update_check_works_on_a_first_build():
    history.check_update(None, _store([2025, 2026]), 2026)
