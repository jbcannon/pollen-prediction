"""Daily heat sums (degree-hours above a base temperature, degrees Fahrenheit)."""

from __future__ import annotations

import numpy as np
import pandas as pd

BASE_TEMP_F = 50.0


def lindsey_newman(tmax, tmean, tmin, base: float = BASE_TEMP_F):
    """Daily heat sum in degree-hours above ``base`` (Lindsey & Newman 1956).

    Takes the day's max, mean and min temperature in degrees F:

    - max below base: 0
    - min at or above base (whole day above base): ``(mean - base) * 24``
    - otherwise: sine-curve approximation ``12 * (max - base)**2 / (max - min)``

    Scalars or array-likes (broadcast together). Returns a float for scalar
    input, a Series (same index) if given Series, else an ndarray. Any missing
    (NaN) input gives NaN, even on branches that don't use that value, so a
    bad sensor reading never silently turns into a plausible number; callers
    decide how to treat days with no data. Series inputs must share an index.
    """
    inputs = (tmax, tmean, tmin)
    indexes = [x.index for x in inputs if isinstance(x, pd.Series)]
    if any(not ix.equals(indexes[0]) for ix in indexes[1:]):
        raise ValueError("tmax, tmean and tmin Series must share the same index")

    h, m, w = np.broadcast_arrays(*(np.asarray(x, dtype=float) for x in inputs))
    # The sine-curve branch only applies when max >= base > min, so max > min.
    # Guard the other branches so they never divide by zero.
    span = np.where(h > w, h - w, 1.0)
    heat = np.where(
        np.isnan(h) | np.isnan(m) | np.isnan(w),
        np.nan,
        np.where(
            h < base,
            0.0,
            np.where(w >= base, (m - base) * 24.0, 12.0 * (h - base) ** 2 / span),
        ),
    )
    if heat.ndim == 0:
        return float(heat)
    return pd.Series(heat, index=indexes[0]) if indexes else heat


def daily_heat(daily: pd.DataFrame, base: float = BASE_TEMP_F) -> pd.Series:
    """Heat sum per day from a frame with ``tmax`` and ``tmin`` (and ``tmean`` if known).

    Uses the true daily mean where ``tmean`` is present and (max+min)/2
    otherwise, so sources that only report max/min still work.
    """
    tmean = daily["tmean"] if "tmean" in daily else pd.Series(np.nan, index=daily.index)
    tmean = tmean.fillna((daily["tmax"] + daily["tmin"]) / 2)
    return lindsey_newman(daily["tmax"], tmean, daily["tmin"], base)


def _fill_short_runs(s: pd.Series, limit: int) -> pd.Series:
    """Interpolate NaN runs of at most ``limit`` days that have data on both sides."""
    missing = s.isna()
    run_id = (missing != missing.shift()).cumsum()
    run_len = missing.groupby(run_id).transform("sum")  # length of each NaN run, 0 elsewhere
    filled = s.interpolate(limit_area="inside")
    return filled.where(~missing | (run_len <= limit), s)


def fill_short_gaps(heat: pd.Series | pd.DataFrame, limit: int = 3):
    """Linearly interpolate runs of up to ``limit`` missing days, per calendar year.

    ``heat`` is a daily Series (or a DataFrame with one column per station) indexed by
    date. A gap is filled only if the *whole* run is at most ``limit`` days; longer gaps
    stay entirely NaN rather than being partly invented. Gaps at the start or end of a
    year are left as NaN.
    """
    def fill(block):
        if isinstance(block, pd.DataFrame):
            return block.apply(_fill_short_runs, limit=limit)
        return _fill_short_runs(block, limit)

    return pd.concat([fill(block) for _, block in heat.groupby(heat.index.year)])


def daily_from_hourly(times, temps) -> pd.DataFrame:
    """Collapse hourly observations to daily tmax, tmean, tmin and n_obs.

    ``times`` must already be in the local time whose calendar days you want
    (timezone-naive). NaN temperatures are ignored, and ``n_obs`` counts the
    valid observations behind each day so callers can flag thin days.
    """
    s = pd.Series(np.asarray(temps, dtype=float), index=pd.DatetimeIndex(times))
    daily = s.groupby(s.index.normalize()).agg(
        tmax="max", tmean="mean", tmin="min", n_obs="count"
    )
    daily.index.name = "date"
    return daily
