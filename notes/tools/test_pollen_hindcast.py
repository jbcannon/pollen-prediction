import numpy as np
import pandas as pd
import pytest

from pollen_hindcast import add_errors, hindcast, summarize

YEARS = (2001, 2002, 2003, 2005)  # no leap years, so day-of-year arithmetic is simple


def history(hot_year=None):
    """One station at 80 heat/day every day, except ``hot_year`` at 180/day."""
    frames = []
    for y in YEARS:
        tmax, tmin = (65.0, 50.0) if y == hot_year else (60.0, 45.0)
        days = pd.date_range(f"{y}-01-01", f"{y}-05-31")
        frames.append(pd.DataFrame({"station": "S", "date": days, "tmax": tmax, "tmin": tmin}))
    return pd.concat(frames, ignore_index=True)


def test_identical_seasons_are_forecast_exactly():
    # Every season crosses on day 113 (23 Apr); every scenario agrees, so error is 0 and covered.
    h = hindcast(history(), YEARS, [(2, 15)])
    scored = add_errors(h)
    assert len(scored) == 4
    assert (scored["actual"] == pd.Timestamp("2001-04-23")).sum() == 1
    assert (scored["error_days"] == 0).all()
    assert scored["covered"].all()
    assert (scored["lead_days"] == (scored["actual"] - scored["as_of"]).dt.days).all()


def test_a_much_hotter_season_is_forecast_too_late():
    # 2003 accumulates 180/day, so it crosses on day 71 (12 Mar), but the analog years (80/day)
    # forecast day 86 (27 Mar): 15 days late.
    scored = add_errors(hindcast(history(hot_year=2003), YEARS, [(2, 15)]))
    hot = scored[scored["year"] == 2003].iloc[0]
    assert hot["actual"] == pd.Timestamp("2003-03-12")
    assert hot["median"] == pd.Timestamp("2003-03-27")
    assert hot["error_days"] == 15 and hot["lead_days"] == 25
    assert not hot["covered"] or hot["earliest"] <= hot["actual"]


def test_stations_already_crossed_are_not_scored():
    # By 15 Apr (day 105) the 80/day station has not crossed yet (needs day 113); by 30 Apr it has.
    early = add_errors(hindcast(history(), YEARS, [(4, 15)]))
    late = add_errors(hindcast(history(), YEARS, [(4, 30)]))
    assert len(early) == 4 and late.empty


def test_lead_bins_and_summary():
    scored = add_errors(hindcast(history(hot_year=2003), YEARS, [(2, 15), (3, 1), (4, 1)]))
    assert set(scored["lead_bin"].dropna().unique()) <= {"0-7", "8-14", "15-21", "22-28", "29-42", "43+"}
    table = summarize(scored, "lead_bin")
    assert table["n"].sum() == len(scored)
    assert {"bias_days", "mae_days", "within_3_days", "range_coverage", "range_width_days"} <= set(table.columns)
    by_year = summarize(scored, "year")
    assert by_year.loc[2003, "bias_days"] > 0  # the hot year is forecast late
    assert by_year.loc[2001, "n"] > 0


def test_null_range_end_counts_as_covering_the_truth():
    df = pd.DataFrame({
        "year": [2001], "as_of": [pd.Timestamp("2001-03-01")], "station": ["S"],
        "earliest": [pd.Timestamp("2001-03-10")], "median": [pd.Timestamp("2001-04-01")],
        "latest": [pd.NaT], "n_scenarios": [5], "actual": [pd.Timestamp("2001-05-20")],
    })
    scored = add_errors(df)
    assert bool(scored["covered"].iloc[0]) is True
    assert np.isnan(scored["width_days"].iloc[0])


def test_rows_without_a_true_crossing_are_dropped():
    df = pd.DataFrame({
        "year": [2001], "as_of": [pd.Timestamp("2001-03-01")], "station": ["S"],
        "earliest": [pd.Timestamp("2001-03-10")], "median": [pd.Timestamp("2001-03-12")],
        "latest": [pd.Timestamp("2001-03-14")], "n_scenarios": [5], "actual": [pd.NaT],
    })
    assert add_errors(df).empty


def test_progress_callback_reports_each_season():
    seen = []
    hindcast(history(), YEARS, [(2, 15)], progress=seen.append)
    assert seen == [f"season {y} done" for y in YEARS]


def test_a_season_missing_from_the_history_gives_a_clear_error():
    with pytest.raises(ValueError, match="no history for season 1999"):
        hindcast(history(), [1999], [(2, 15)])
