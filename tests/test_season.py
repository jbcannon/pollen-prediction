from datetime import date

import numpy as np
import pandas as pd
import pytest

from pollen import season
from pollen.season import forecast_season, heat_table, replay

AS_OF = date(2026, 3, 5)  # day 64


def long_history(spec, years=(2001, 2002, 2003, 2026)):
    """Long history where each station has constant tmax/tmin every Jan-May day.

    spec: {station: (tmax, tmin)}. (70, 55) is 300 heat/day, (60, 45) is 80 heat/day.
    """
    frames = []
    for station, (tmax, tmin) in spec.items():
        for y in years:
            days = pd.date_range(f"{y}-01-01", f"{y}-05-31")
            frames.append(pd.DataFrame(
                {"station": station, "date": days, "tmax": float(tmax), "tmin": float(tmin)}))
    return pd.concat(frames, ignore_index=True)


def blank(history, station, start, end):
    m = (history.station == station) & history.date.between(start, end)
    history.loc[m, ["tmax", "tmin"]] = np.nan


def test_heat_table_is_wide_and_fills_only_short_gaps():
    h = long_history({"A": (70, 55)}, years=(2001,))
    blank(h, "A", "2001-02-01", "2001-02-03")  # 3 days: filled
    blank(h, "A", "2001-03-01", "2001-03-05")  # 5 days: stays missing
    t = heat_table(h)
    assert list(t.columns) == ["A"]
    assert t.loc["2001-02-01":"2001-02-03", "A"].notna().all()
    assert t.loc["2001-03-01":"2001-03-05", "A"].isna().all()
    assert t.loc["2001-01-01", "A"] == pytest.approx(300.0)


def test_station_that_already_crossed_reports_its_crossing_date():
    # 300/day: reaches 19009 - 89.26*k when k >= 48.83, so day 49 = 18 Feb
    h = long_history({"A": (70, 55)})
    out = replay(h, 2026, AS_OF)
    row = out.set_index("station").loc["A"]
    assert row.status == "crossed"
    assert row.crossing_date == pd.Timestamp("2026-02-18")
    assert pd.isna(row["median"])


def test_station_still_accumulating_gets_a_forecast_range():
    # 80/day: on day 64, cum = 5120. Adding 80/day it crosses on day 113 (23 Apr) in every scenario.
    h = long_history({"B": (60, 45)})
    out = replay(h, 2026, AS_OF)
    row = out.set_index("station").loc["B"]
    assert row.status == "forecast"
    assert row.cum_heat == pytest.approx(5120.0)
    assert row.earliest == row["median"] == row.latest == pd.Timestamp("2026-04-23")
    assert row.n_scenarios == 3  # analog years 2001-2003, the season year is left out
    assert row.n_not_crossed == 0


def test_season_year_is_left_out_of_its_own_analogs():
    h = long_history({"B": (60, 45)})
    # make 2026 itself wildly hot after the as-of date: must not affect anything
    late = (h.station == "B") & (h.date > "2026-03-05") & (h.date.dt.year == 2026)
    h.loc[late, ["tmax", "tmin"]] = [100.0, 80.0]
    row = replay(h, 2026, AS_OF).set_index("station").loc["B"]
    assert row["median"] == pd.Timestamp("2026-04-23")
    assert row.n_scenarios == 3


def test_prior_years_mode_uses_only_earlier_years():
    h = long_history({"B": (60, 45)}, years=(2001, 2002, 2026, 2027))
    others = replay(h, 2026, AS_OF, analogs="others").set_index("station").loc["B"]
    prior = replay(h, 2026, AS_OF, analogs="prior").set_index("station").loc["B"]
    assert others.n_scenarios == 3 and prior.n_scenarios == 2


def test_window_keeps_only_the_most_recent_prior_years():
    h = long_history({"B": (60, 45)}, years=(2001, 2002, 2024, 2025, 2026))
    everything = replay(h, 2026, AS_OF, analogs="prior").set_index("station").loc["B"]
    recent = replay(h, 2026, AS_OF, analogs="prior", window=2).set_index("station").loc["B"]
    assert everything.n_scenarios == 4 and recent.n_scenarios == 2


def test_no_analog_years_gives_a_clear_status_instead_of_a_crash():
    h = long_history({"B": (60, 45)}, years=(2001, 2002, 2026))
    row = replay(h, 2026, AS_OF, analogs="prior", window=1).set_index("station").loc["B"]
    assert row.status == "no_analogs"
    assert row.n_scenarios == 0 and pd.isna(row["median"])
    assert row.cum_heat == pytest.approx(5120.0)  # this season's own numbers are still reported


def test_window_needs_prior_analogs():
    with pytest.raises(ValueError, match="window"):
        replay(long_history({"B": (60, 45)}), 2026, AS_OF, analogs="others", window=5)


def test_replay_rejects_unknown_analog_mode():
    with pytest.raises(ValueError, match="analogs"):
        replay(long_history({"B": (60, 45)}), 2026, AS_OF, analogs="all")


def test_station_with_no_recent_data_is_forecast_from_its_last_day():
    h = long_history({"B": (60, 45)})
    blank(h, "B", "2026-03-04", "2026-03-31")  # stopped reporting after 3 Mar
    row = replay(h, 2026, AS_OF).set_index("station").loc["B"]
    assert row.data_through == pd.Timestamp("2026-03-03")
    assert row.days_behind == 2
    assert row.status == "forecast"
    assert row.cum_heat == pytest.approx(80 * 62)  # through 3 Mar = day 62


def test_station_with_nothing_is_no_data():
    h = long_history({"B": (60, 45), "C": (60, 45)})
    blank(h, "C", "2026-01-01", "2026-05-31")
    out = replay(h, 2026, AS_OF).set_index("station")
    assert out.loc["C", "status"] == "no_data"
    assert out.loc["B", "status"] == "forecast"


def test_moderate_gap_is_filled_from_climatology_and_flagged():
    h = long_history({"B": (60, 45)})
    blank(h, "B", "2026-02-01", "2026-02-05")  # 5 days: too long to interpolate, under the limit
    row = replay(h, 2026, AS_OF).set_index("station").loc["B"]
    assert row.status == "forecast"
    assert row.filled_days == 5
    assert row.cum_heat == pytest.approx(5120.0)  # climatology (80/day) makes it whole


def test_too_many_missing_days_is_insufficient_data():
    h = long_history({"B": (60, 45)})
    for a, b in [("2026-02-01", "2026-02-05"), ("2026-02-10", "2026-02-14"), ("2026-02-20", "2026-02-24")]:
        blank(h, "B", a, b)  # 15 missing days in 5-day runs
    row = replay(h, 2026, AS_OF).set_index("station").loc["B"]
    assert row.status == "insufficient_data"
    assert row.filled_days == 15
    assert pd.isna(row["median"])


def test_forecast_season_takes_live_and_analog_tables_directly():
    # The live path: no replay, just a live table and an analog table.
    h = long_history({"B": (60, 45)})
    table = heat_table(h)
    live = table[table.index.year == 2026]
    analog = table[table.index.year != 2026]
    out = forecast_season(live, analog, AS_OF)
    assert out.loc[0, "median"] == pd.Timestamp("2026-04-23")


def test_scenarios_that_never_cross_by_the_end_are_counted():
    h = long_history({"B": (60, 45)})
    out = replay(h, 2026, AS_OF, end=date(2026, 4, 1)).set_index("station")
    row = out.loc["B"]
    assert row.n_not_crossed == 3 and pd.isna(row.earliest) and pd.isna(row.latest)


def test_outlook_replays_every_analog_year_from_zero_heat():
    # constant 100 degree-hours a day: 19009 - 89.26 * d <= 100 * d first holds on day 101 (11 April 2027)
    days = pd.date_range("2024-01-01", "2026-12-31")
    analog = pd.DataFrame({"AAA": 100.0}, index=days)
    out, series = season.forecast_outlook(analog, ["AAA", "ZZZ"], 2027, detail=True)
    a = out.set_index("station").loc["AAA"]
    assert a["status"] == "forecast" and a["cum_heat"] == 0 and a["n_scenarios"] == 3 and a["n_not_crossed"] == 0
    assert a["earliest"] == a["median"] == a["latest"] == pd.Timestamp("2027-04-11")
    assert pd.isna(a["data_through"]) and pd.isna(a["crossing_date"])
    assert series["AAA"]["cum"] == [] and series["AAA"]["band"]["start"] == "2027-01-01"
    z = out.set_index("station").loc["ZZZ"]  # a station with no history has nothing to replay
    assert z["status"] == "no_analogs" and "ZZZ" not in series
