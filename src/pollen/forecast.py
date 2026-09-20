"""Forecast the Boyer crossing date from heat accumulated so far.

The heat accumulated so far this year is fixed; only the rest of the season is
uncertain. Each analog year supplies one scenario for the daily heat still to
come. For each scenario, start from this year's accumulated total, add that
analog year's daily heat day by day, and record the first day the Boyer
requirement is reached. The spread of those dates across scenarios is the
forecast range. It narrows to a single date as the real crossing approaches.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from pollen.boyer import required_heat_sum


@dataclass(frozen=True)
class ForecastRange:
    """Quantiles of the scenario crossing dates (None = later than the window)."""

    earliest: date | None
    median: date | None
    latest: date | None
    n_scenarios: int
    n_not_crossed: int


def same_calendar_day(target: date, year: int) -> date:
    """``target`` moved to ``year``; Feb 29 falls back to Feb 28 in non-leap years."""
    try:
        return target.replace(year=year)
    except ValueError:
        return target.replace(year=year, day=28)


def scenario_paths(
    cumulative: float,
    as_of: date,
    history: pd.Series,
    end: date | None = None,
) -> pd.DataFrame:
    """Cumulative heat sum from the day after ``as_of`` under each analog year.

    ``cumulative`` is the heat sum accumulated through ``as_of`` (the last day
    with observations). ``history`` is daily heat sums for the analog years,
    indexed by date. Rows are the days after ``as_of`` through ``end`` (default
    May 31) in ``as_of``'s year; columns are analog years. Analog years missing
    any day in the window are skipped with a warning.
    """
    end = end or date(as_of.year, 5, 31)
    days = pd.date_range(as_of + timedelta(days=1), end)

    paths = {}
    for year, heat in history.groupby(history.index.year):
        analog_days = [same_calendar_day(d.date(), year) for d in days]
        daily = heat.reindex(pd.DatetimeIndex(analog_days)).to_numpy(dtype=float)
        if np.isnan(daily).any():
            warnings.warn(f"analog year {year} skipped: missing days in window")
            continue
        paths[year] = cumulative + np.cumsum(daily)
    return pd.DataFrame(paths, index=days)


def scenario_crossings(
    cumulative: float,
    as_of: date,
    history: pd.Series,
    end: date | None = None,
) -> pd.Series:
    """First date each scenario reaches the Boyer requirement.

    One value per analog year (see :func:`scenario_paths`), NaT where the
    requirement is not reached by ``end``. Call this only while the requirement
    has not yet been reached.
    """
    return first_crossings(scenario_paths(cumulative, as_of, history, end))


def first_crossings(paths: pd.DataFrame) -> pd.Series:
    """First date each scenario path (a column of :func:`scenario_paths`) reaches the requirement."""
    required = pd.Series(required_heat_sum(paths.index.dayofyear), index=paths.index)
    reached = paths.ge(required, axis=0)
    first = reached.idxmax().where(reached.any())
    return first.rename("crossing").astype("datetime64[ns]")


def summarize_crossings(
    crossings: pd.Series, interval: float = 0.5
) -> ForecastRange:
    """Central ``interval`` of the scenario crossing dates plus the median.

    A scenario that never crosses counts as later than any date, so it pushes
    the upper end out rather than being dropped; the affected quantile is None.
    """
    if len(crossings) == 0:
        return ForecastRange(earliest=None, median=None, latest=None, n_scenarios=0, n_not_crossed=0)
    ordinals = np.array(
        [d.toordinal() if pd.notna(d) else np.inf for d in crossings], dtype=float
    )

    def quantile(p: float) -> date | None:
        v = np.quantile(ordinals, p, method="inverted_cdf")
        return None if np.isinf(v) else date.fromordinal(int(v))

    return ForecastRange(
        earliest=quantile(0.5 - interval / 2),
        median=quantile(0.5),
        latest=quantile(0.5 + interval / 2),
        n_scenarios=len(ordinals),
        n_not_crossed=int(np.isinf(ordinals).sum()),
    )
