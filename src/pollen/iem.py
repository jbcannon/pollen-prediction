"""Daily station summaries from the Iowa Environmental Mesonet (IEM). Keyless.

One source serves both the live season and the analog-year history, so both are
measured the same way. IEM's daily file has max and min temperature but no
true daily mean.
"""

from __future__ import annotations

import io
import time
from datetime import date

import pandas as pd
import requests

DAILY_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/daily.py"
NETWORK_URL = "https://mesonet.agron.iastate.edu/geojson/network/{network}.geojson"


def list_stations(network: str, timeout: float = 60.0) -> pd.DataFrame:
    """Stations in one IEM network (e.g. ``GA_ASOS``) with location and archive dates."""
    resp = requests.get(NETWORK_URL.format(network=network), timeout=timeout)
    resp.raise_for_status()
    rows = []
    for f in resp.json()["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        rows.append(
            {
                "id": f["id"],
                "name": p.get("sname"),
                "state": p.get("state"),
                "network": network,
                "lat": lat,
                "lon": lon,
                "elevation_m": p.get("elevation"),
                "archive_begin": pd.to_datetime(p.get("archive_begin")),
                "archive_end": pd.to_datetime(p.get("archive_end")),
                "online": bool(p.get("online")),
            }
        )
    return pd.DataFrame(rows)


def fetch_daily_many(
    network: str,
    stations: list[str],
    start: date,
    end: date,
    timeout: float = 60.0,
    retries: int = 3,
    pause: float = 2.0,
) -> pd.DataFrame:
    """Daily max/min (deg F) for several stations of one network in a single request.

    Returns a long table with columns ``station, date, tmax, tmin`` (NaN where a station
    reported nothing; days IEM has no row for are absent). Server errors are retried
    ``retries`` times, ``pause`` seconds apart, before the last error is raised.
    """
    params = {
        "network": network,
        "stations": list(stations),
        "year1": start.year,
        "month1": start.month,
        "day1": start.day,
        "year2": end.year,
        "month2": end.month,
        "day2": end.day,
        "format": "csv",
    }
    last_error: requests.RequestException | None = None
    for attempt in range(retries):
        try:
            resp = requests.get(DAILY_URL, params=params, timeout=timeout)
            resp.raise_for_status()
            break
        except requests.RequestException as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(pause)
    else:
        raise last_error or RuntimeError("retries must be at least 1")
    raw = pd.read_csv(io.StringIO(resp.text), na_values=["None", "M", ""])
    missing = {"station", "day", "max_temp_f", "min_temp_f"} - set(raw.columns)
    if missing:
        raise ValueError(f"unexpected IEM response for {network}: no {sorted(missing)}")
    out = pd.DataFrame(
        {
            "station": raw["station"].to_numpy(),
            "date": pd.to_datetime(raw["day"]).to_numpy(),
            "tmax": raw["max_temp_f"].to_numpy(),
            "tmin": raw["min_temp_f"].to_numpy(),
        }
    )
    return out.sort_values(["station", "date"]).reset_index(drop=True)


def fetch_daily(
    station: str,
    network: str,
    start: date,
    end: date,
    timeout: float = 60.0,
) -> pd.DataFrame:
    """Daily max/min temperature (deg F) for one station, ``start`` to ``end``.

    ``network`` is IEM's network id, e.g. ``GA_ASOS`` for Georgia airports.
    Returns a DataFrame indexed by date with columns ``tmax`` and ``tmin``
    (NaN where the station reported nothing). Days IEM has no row for are
    simply absent, so callers should reindex if they need every calendar day.
    """
    params = {
        "network": network,
        "stations": station,
        "year1": start.year,
        "month1": start.month,
        "day1": start.day,
        "year2": end.year,
        "month2": end.month,
        "day2": end.day,
        "format": "csv",
    }
    resp = requests.get(DAILY_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    raw = pd.read_csv(io.StringIO(resp.text), na_values=["None", "M", ""])
    missing = {"day", "max_temp_f", "min_temp_f"} - set(raw.columns)
    if missing:
        raise ValueError(f"unexpected IEM response for {network}/{station}: no {sorted(missing)}")
    out = pd.DataFrame(
        {"tmax": raw["max_temp_f"].to_numpy(), "tmin": raw["min_temp_f"].to_numpy()},
        index=pd.DatetimeIndex(pd.to_datetime(raw["day"]), name="date"),
    )
    return out.sort_index()
