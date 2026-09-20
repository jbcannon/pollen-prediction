"""Hindcast: replay past seasons on several dates and compare each forecast with what happened.

Errors are grouped by *lead time*, the days between the forecast and the true crossing, because
that is what a reader cares about ("how good is the forecast N days before the peak?").
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date

import pandas as pd

from pollen.season import heat_table, replay

LEAD_BINS = [-1, 7, 14, 21, 28, 42, 400]
LEAD_LABELS = ["0-7", "8-14", "15-21", "22-28", "29-42", "43+"]
FAR_FUTURE = pd.Timestamp("2200-01-01")  # stands in for "after 31 May" when a range end is null


def hindcast(
    history: pd.DataFrame,
    years: Iterable[int],
    month_days: Iterable[tuple[int, int]],
    analogs: str = "others",
    progress: Callable[[str], None] | None = None,
    window: int | None = None,
) -> pd.DataFrame:
    """Forecast every season in ``years`` as of each (month, day), with the true crossing attached.

    Only stations not yet crossed on the forecast date are included. The true crossing date
    comes from replaying the season to 31 May with the same gap handling as a live run;
    stations without one (too many gaps) get no ``actual`` and drop out of the scoring.
    """
    table = heat_table(history)
    month_days = list(month_days)
    rows = []
    for year in years:
        truth = replay(history, year, date(year, 5, 31), analogs=analogs, table=table, window=window)
        actual = truth[truth["status"] == "crossed"].set_index("station")["crossing_date"]
        for month, day in month_days:
            as_of = date(year, month, day)
            out = replay(history, year, as_of, analogs=analogs, table=table, window=window)
            fc = out[out["status"] == "forecast"]
            rows.append(
                pd.DataFrame(
                    {
                        "year": year,
                        "as_of": pd.Timestamp(as_of),
                        "station": fc["station"].to_numpy(),
                        "earliest": fc["earliest"].to_numpy(),
                        "median": fc["median"].to_numpy(),
                        "latest": fc["latest"].to_numpy(),
                        "n_scenarios": fc["n_scenarios"].to_numpy(),
                        "actual": fc["station"].map(actual).to_numpy(),
                    }
                )
            )
        if progress:
            progress(f"season {year} done")
    return pd.concat(rows, ignore_index=True)


def add_errors(df: pd.DataFrame) -> pd.DataFrame:
    """Add lead time, signed error (median minus actual, days), coverage and range width.

    Rows with no true crossing or no forecast median are dropped. A null range end means
    "after 31 May", so it never excludes the true date.
    """
    out = df.dropna(subset=["actual", "median"]).copy()
    out["lead_days"] = (out["actual"] - out["as_of"]).dt.days
    out = out[out["lead_days"] >= 1].copy()  # crossed-by-as_of rows are not forecasts
    out["error_days"] = (out["median"] - out["actual"]).dt.days
    out["abs_error_days"] = out["error_days"].abs()
    latest = out["latest"].fillna(FAR_FUTURE)
    out["covered"] = (out["earliest"] <= out["actual"]) & (out["actual"] <= latest)
    out["width_days"] = (latest - out["earliest"]).dt.days.where(out["latest"].notna())
    out["lead_bin"] = pd.cut(out["lead_days"], bins=LEAD_BINS, labels=LEAD_LABELS)
    return out


def summarize(df: pd.DataFrame, by: str | list[str]) -> pd.DataFrame:
    """Forecast quality per group: n, bias (signed days), MAE, share within 3 days, range coverage."""
    g = df.groupby(by, observed=True)
    return pd.DataFrame(
        {
            "n": g["error_days"].size(),
            "bias_days": g["error_days"].mean(),
            "mae_days": g["abs_error_days"].mean(),
            "within_3_days": g["abs_error_days"].apply(lambda s: (s <= 3).mean()),
            "range_coverage": g["covered"].mean(),
            "range_width_days": g["width_days"].median(),
        }
    )
