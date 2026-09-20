"""Season forecast for every station: this year's accumulated heat plus analog-year scenarios.

``forecast_season`` is the one code path. A live run feeds it this season's readings from
IEM; a replay (``replay``) feeds it a past season from the history store, cut off at an
"as of" date and with that year left out of its own analogs. Everything after loading is
identical, so a replay exercises the real pipeline.
"""

from __future__ import annotations

import warnings
from datetime import date, timedelta
from typing import Any

import pandas as pd

from pollen.boyer import first_crossing_yday, required_heat_sum
from pollen.forecast import first_crossings, scenario_paths, summarize_crossings
from pollen.heatsum import fill_short_gaps, lindsey_newman

ANALOG_WINDOW = 10  # a live run uses this many of the most recent complete seasons as analog years
GAP_LIMIT = 3  # runs of up to this many missing days are interpolated
MAX_FILLED_DAYS = 10  # more unfilled missing days than this and a station is not forecast

COLUMNS = [
    "station", "status", "data_through", "days_behind", "filled_days", "cum_heat",
    "required_heat", "crossing_date", "earliest", "median", "latest",
    "n_scenarios", "n_not_crossed",
]
DATE_COLUMNS = ["data_through", "crossing_date", "earliest", "median", "latest"]


def heat_table(daily: pd.DataFrame, gap_limit: int = GAP_LIMIT) -> pd.DataFrame:
    """Daily heat sums as a wide table (rows = date, columns = station).

    ``daily`` is long with columns ``station, date, tmax, tmin`` (deg F). The daily mean is
    (max+min)/2, the rule for sources with no true mean. Runs of up to ``gap_limit``
    missing days are interpolated within each year; longer gaps stay NaN.
    """
    tmax = daily.pivot(index="date", columns="station", values="tmax")
    tmin = daily.pivot(index="date", columns="station", values="tmin")
    heat = pd.DataFrame(
        lindsey_newman(tmax, (tmax + tmin) / 2, tmin), index=tmax.index, columns=tmax.columns
    )
    return fill_short_gaps(heat, gap_limit)


def _band(paths: pd.DataFrame, rng, end: date, interval: float) -> dict[str, Any] | None:
    """Spread of the scenario curves: low/middle/high cumulative heat per day.

    Runs from the day after the last reading to a week past the range's late end
    (or ``end``), which is all a chart needs.
    """
    if paths.empty or paths.shape[1] == 0:
        return None
    stop = end if rng.latest is None else min(end, rng.latest + timedelta(days=7))
    shown = paths.loc[: pd.Timestamp(stop)]
    q = shown.quantile([0.5 - interval / 2, 0.5, 0.5 + interval / 2], axis=1).round().astype(int)
    return {
        "start": shown.index[0].date().isoformat(),
        "lo": q.iloc[0].tolist(),
        "mid": q.iloc[1].tolist(),
        "hi": q.iloc[2].tolist(),
    }


def _station_row(
    station: str,
    live: pd.Series,
    analog: pd.Series,
    climatology: pd.Series,
    as_of: date,
    interval: float,
    max_filled: int,
    end: date,
    detail: bool = False,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """One station's summary row and (if ``detail``) its chart series."""
    row: dict[str, Any] = dict.fromkeys(COLUMNS)
    row.update(station=station, status="no_data")
    valid = live.dropna()
    if valid.empty:
        return row, None

    through = valid.index[-1]
    s = live.loc[:through]
    missing = s.isna()
    row.update(
        data_through=through.date(),
        days_behind=(as_of - through.date()).days,
        filled_days=int(missing.sum()),
    )
    if row["filled_days"] > max_filled:
        row["status"] = "insufficient_data"
        return row, None
    if row["filled_days"]:
        # Days still missing after short-gap interpolation get that calendar day's median heat.
        keys = list(zip(s.index.month, s.index.day, strict=True))
        fill = pd.Series(climatology.reindex(keys).to_numpy(), index=s.index)
        s = s.where(~missing, fill)

    cum = s.cumsum()
    series = None
    if detail:
        series = {"cum": cum.ffill().fillna(0).round().astype(int).tolist(), "band": None}
    row.update(
        cum_heat=float(cum.iloc[-1]),
        required_heat=float(required_heat_sum(through.dayofyear)),
    )
    yday = first_crossing_yday(cum.to_numpy(), s.index.dayofyear)
    if yday is not None:
        row.update(status="crossed", crossing_date=date(as_of.year, 1, 1) + timedelta(days=yday - 1))
        return row, series

    with warnings.catch_warnings():  # analog years with gaps are skipped; n_scenarios reports it
        warnings.simplefilter("ignore")
        paths = scenario_paths(row["cum_heat"], through.date(), analog, end=end)
    if paths.shape[1] == 0:  # no analog year covers the rest of the season
        row.update(status="no_analogs", n_scenarios=0)
        return row, series
    rng = summarize_crossings(first_crossings(paths), interval=interval)
    row.update(
        status="forecast",
        earliest=rng.earliest,
        median=rng.median,
        latest=rng.latest,
        n_scenarios=rng.n_scenarios,
        n_not_crossed=rng.n_not_crossed,
    )
    if detail:
        series["band"] = _band(paths, rng, end, interval)
    return row, series


def forecast_season(
    live: pd.DataFrame,
    analog: pd.DataFrame,
    as_of: date,
    interval: float = 0.5,
    max_filled: int = MAX_FILLED_DAYS,
    end: date | None = None,
    detail: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    """One row per station: has it crossed the Boyer line, and if not, when will it.

    ``live`` is this season's daily heat (wide table, from Jan 1); ``analog`` is the daily
    heat of the analog years in the same wide layout. A station whose latest reading is
    older than ``as_of`` is forecast from its own last day (``days_behind`` says how far).

    ``status`` is ``crossed`` (``crossing_date`` set), ``forecast`` (``earliest``/``median``/
    ``latest`` set; None where scenarios cross after ``end``), ``insufficient_data`` (too
    many missing days), ``no_analogs`` (no analog year covers the rest of the season) or
    ``no_data``.

    With ``detail=True`` also returns ``{station: {"cum": [...], "band": {...} or None}}``:
    the season's accumulated heat per day and the spread of the scenario curves, for charts.
    """
    end = end or date(as_of.year, 5, 31)
    clim = analog.groupby([analog.index.month, analog.index.day]).median()
    live = live.loc[: pd.Timestamp(as_of)]
    rows, series = [], {}
    for station in live.columns:
        if station in analog.columns:
            analog_s, clim_s = analog[station], clim[station]
        else:
            analog_s, clim_s = pd.Series(dtype=float), pd.Series(dtype=float)
        row, detail_s = _station_row(
            station, live[station], analog_s, clim_s, as_of, interval, max_filled, end, detail
        )
        rows.append(row)
        if detail_s is not None:
            series[station] = detail_s
    out = pd.DataFrame(rows, columns=COLUMNS)
    for col in DATE_COLUMNS:
        out[col] = pd.to_datetime(out[col])
    return (out, series) if detail else out


def forecast_outlook(
    analog: pd.DataFrame,
    station_ids: list[str],
    season: int,
    interval: float = 0.5,
    detail: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    """Preseason outlook for ``season``: no readings yet, so every station starts from zero heat.

    Each analog year is replayed over the whole Jan-May window, so the forecast rests on the
    recent climate alone. It returns the same table as ``forecast_season`` (status ``forecast``,
    or ``no_analogs``; ``data_through`` is empty and ``cum_heat`` is 0) and, with ``detail=True``,
    the chart series (an empty ``cum`` and the scenario band from 1 January).
    """
    before, end = date(season - 1, 12, 31), date(season, 5, 31)
    rows, series = [], {}
    for station in station_ids:
        row: dict[str, Any] = dict.fromkeys(COLUMNS)
        row.update(station=station, status="no_analogs", n_scenarios=0)
        paths = pd.DataFrame()
        if station in analog.columns:
            with warnings.catch_warnings():  # analog years with gaps are skipped; n_scenarios reports it
                warnings.simplefilter("ignore")
                paths = scenario_paths(0.0, before, analog[station], end=end)
        if paths.shape[1]:
            rng = summarize_crossings(first_crossings(paths), interval=interval)
            row.update(
                status="forecast", filled_days=0, cum_heat=0.0, required_heat=float(required_heat_sum(1)),
                earliest=rng.earliest, median=rng.median, latest=rng.latest,
                n_scenarios=rng.n_scenarios, n_not_crossed=rng.n_not_crossed,
            )
            if detail:
                series[station] = {"cum": [], "band": _band(paths, rng, end, interval)}
        rows.append(row)
    out = pd.DataFrame(rows, columns=COLUMNS)
    for col in DATE_COLUMNS:
        out[col] = pd.to_datetime(out[col])
    return (out, series) if detail else out


def replay(
    history: pd.DataFrame,
    season_year: int,
    as_of: date,
    analogs: str = "others",
    table: pd.DataFrame | None = None,
    window: int | None = None,
    **kwargs,
) -> pd.DataFrame:
    """Forecast a past season as if it were ``as_of``, using only what was known by then.

    The season's readings are cut off at ``as_of`` *before* gaps are filled, so nothing
    from later leaks in. ``analogs`` picks the analog years: ``"others"`` (every other
    year, leave-one-out) or ``"prior"`` (only earlier years, as a live run would have).
    With ``"prior"``, ``window`` keeps only the most recent that many years.
    Pass ``table=heat_table(history)`` to reuse it across many replays.
    """
    if analogs not in ("others", "prior"):
        raise ValueError("analogs must be 'others' or 'prior'")
    if window is not None and analogs != "prior":
        raise ValueError("window only applies with analogs='prior'")
    known = history[(history["date"].dt.year == season_year) & (history["date"] <= pd.Timestamp(as_of))]
    if known.empty:
        raise ValueError(f"no history for season {season_year} on or before {as_of}")
    live = heat_table(known)
    full = table if table is not None else heat_table(history)
    years = full.index.year
    if analogs == "others":
        analog = full[years != season_year]
    else:
        oldest = season_year - window if window else years.min()
        analog = full[(years < season_year) & (years >= oldest)]
    return forecast_season(live, analog, as_of, **kwargs)
