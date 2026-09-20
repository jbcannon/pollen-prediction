from datetime import date

import pandas as pd
import pytest

from pollen.forecast import (
    same_calendar_day,
    scenario_crossings,
    scenario_paths,
    summarize_crossings,
)


def constant_history(rates: dict[int, float]) -> pd.Series:
    """Analog years that each add the same heat every day (Jan 1 - May 31)."""
    parts = [
        pd.Series(rate, index=pd.date_range(f"{year}-01-01", f"{year}-05-31"))
        for year, rate in rates.items()
    ]
    return pd.concat(parts)


# Hand-worked case. As of 15 Mar 2026 (yday 74) with 10,000 accumulated, a scenario adding
# c per day reaches the requirement on day k >= (19009 - 89.26*74 - 10000) / (c + 89.26):
#   c=500 -> k=5 (20 Mar);  c=250 -> k=8 (23 Mar);  c=0 -> k=27 (11 Apr).
AS_OF = date(2026, 3, 15)
HISTORY = constant_history({2001: 500.0, 2002: 250.0, 2003: 0.0})


def test_each_scenario_gets_its_own_crossing_date():
    crossings = scenario_crossings(10_000, AS_OF, HISTORY)
    assert crossings.loc[2001] == pd.Timestamp("2026-03-20")
    assert crossings.loc[2002] == pd.Timestamp("2026-03-23")
    assert crossings.loc[2003] == pd.Timestamp("2026-04-11")


def test_scenario_that_does_not_cross_by_end_is_nat():
    crossings = scenario_crossings(10_000, AS_OF, HISTORY, end=date(2026, 3, 25))
    assert pd.isna(crossings.loc[2003])
    assert crossings.loc[2001] == pd.Timestamp("2026-03-20")


def test_paths_start_from_todays_total():
    paths = scenario_paths(10_000, AS_OF, HISTORY, end=date(2026, 3, 18))
    assert paths.index[0] == pd.Timestamp("2026-03-16")
    assert paths.loc["2026-03-16", 2001] == pytest.approx(10_500)
    assert paths.loc["2026-03-18", 2002] == pytest.approx(10_750)
    assert list(paths.columns) == [2001, 2002, 2003]


def test_range_is_quantiles_of_one_date_per_scenario():
    crossings = scenario_crossings(10_000, AS_OF, HISTORY, end=date(2026, 3, 25))
    rng = summarize_crossings(crossings, interval=0.5)
    assert rng.earliest == date(2026, 3, 20)
    assert rng.median == date(2026, 3, 23)
    assert rng.latest is None  # 1 of 3 scenarios never crosses in the window
    assert (rng.n_scenarios, rng.n_not_crossed) == (3, 1)


def test_range_does_not_depend_on_how_far_off_the_crossing_is():
    # Regression guard for the old bug, where every pre-crossing day was pooled:
    # a scenario crossing 27 days out must weigh the same as one crossing in 5.
    crossings = pd.Series(
        pd.to_datetime(["2026-03-20", "2026-03-20", "2026-04-11"]), index=[1, 2, 3]
    )
    rng = summarize_crossings(crossings, interval=0.5)
    assert rng.median == date(2026, 3, 20)


def test_analog_year_with_missing_day_is_skipped_with_warning():
    history = HISTORY.copy()
    history.loc["2002-03-20"] = float("nan")
    with pytest.warns(UserWarning, match="2002"):
        paths = scenario_paths(10_000, AS_OF, history, end=date(2026, 3, 25))
    assert 2002 not in paths.columns


def test_same_calendar_day_handles_leap_day():
    assert same_calendar_day(date(2028, 2, 29), 2027) == date(2027, 2, 28)
    assert same_calendar_day(date(2028, 2, 29), 2024) == date(2024, 2, 29)
    assert same_calendar_day(date(2026, 3, 15), 2001) == date(2001, 3, 15)
