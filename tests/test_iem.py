from datetime import date

import numpy as np
import pandas as pd
import pytest

from pollen import iem
from pollen.heatsum import daily_heat

CSV = """station,day,max_temp_f,min_temp_f,precip_in
ABY,2026-01-02,66.0,38.0,0.0
ABY,2026-01-01,65.0,30.0,0.0
ABY,2026-01-03,None,None,0.1
"""


class FakeResponse:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_fetch_daily_parses_sorts_and_marks_missing(monkeypatch):
    seen = {}

    def fake_get(url, params, timeout):
        seen.update(url=url, params=params)
        return FakeResponse(CSV)

    monkeypatch.setattr(iem.requests, "get", fake_get)
    df = iem.fetch_daily("ABY", "GA_ASOS", date(2026, 1, 1), date(2026, 1, 3))

    assert list(df.index.strftime("%Y-%m-%d")) == ["2026-01-01", "2026-01-02", "2026-01-03"]
    assert df.loc["2026-01-01", ["tmax", "tmin"]].tolist() == [65.0, 30.0]
    assert df.loc["2026-01-03"].isna().all()
    assert seen["params"]["stations"] == "ABY" and seen["params"]["network"] == "GA_ASOS"
    assert (seen["params"]["year1"], seen["params"]["month2"]) == (2026, 1)


def test_list_stations_parses_metadata(monkeypatch):
    payload = {
        "features": [
            {
                "id": "ABY",
                "properties": {
                    "sname": "Albany",
                    "state": "GA",
                    "elevation": 60.0,
                    "archive_begin": "1948-01-01",
                    "archive_end": None,
                    "online": True,
                },
                "geometry": {"type": "Point", "coordinates": [-84.19, 31.53]},
            }
        ]
    }

    class Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return payload

    monkeypatch.setattr(iem.requests, "get", lambda url, timeout: Resp())
    df = iem.list_stations("GA_ASOS")
    row = df.iloc[0]
    assert (row.id, row["name"], row.state, row.network) == ("ABY", "Albany", "GA", "GA_ASOS")
    assert (row.lat, row.lon) == (31.53, -84.19)
    assert row.archive_begin == pd.Timestamp("1948-01-01") and pd.isna(row.archive_end)
    assert row.online


MANY_CSV = """station,day,max_temp_f,min_temp_f
SAV,2026-01-02,70.0,50.0
ABY,2026-01-02,66.0,38.0
ABY,2026-01-01,65.0,None
"""


def test_fetch_daily_many_returns_a_sorted_long_table_and_sends_all_stations(monkeypatch):
    seen = {}

    def fake_get(url, params, timeout):
        seen.update(params)
        return FakeResponse(MANY_CSV)

    monkeypatch.setattr(iem.requests, "get", fake_get)
    df = iem.fetch_daily_many("GA_ASOS", ["ABY", "SAV"], date(2026, 1, 1), date(2026, 1, 2))
    assert list(df.columns) == ["station", "date", "tmax", "tmin"]
    assert df["station"].tolist() == ["ABY", "ABY", "SAV"]
    assert df["date"].tolist() == [pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-02")]
    assert pd.isna(df["tmin"].iloc[0]) and df["tmax"].iloc[2] == 70.0
    assert seen["stations"] == ["ABY", "SAV"] and seen["network"] == "GA_ASOS"


def test_fetch_daily_many_retries_server_errors_then_succeeds(monkeypatch):
    calls = []

    class Flaky(FakeResponse):
        def raise_for_status(self):
            if len(calls) < 3:
                raise iem.requests.HTTPError("503")

    def fake_get(url, params, timeout):
        calls.append(1)
        return Flaky(MANY_CSV)

    monkeypatch.setattr(iem.requests, "get", fake_get)
    monkeypatch.setattr(iem.time, "sleep", lambda s: None)
    df = iem.fetch_daily_many("GA_ASOS", ["ABY"], date(2026, 1, 1), date(2026, 1, 2))
    assert len(calls) == 3 and len(df) == 3


def test_fetch_daily_many_gives_up_after_the_retries(monkeypatch):
    class Down(FakeResponse):
        def raise_for_status(self):
            raise iem.requests.HTTPError("503")

    monkeypatch.setattr(iem.requests, "get", lambda url, params, timeout: Down(""))
    monkeypatch.setattr(iem.time, "sleep", lambda s: None)
    with pytest.raises(iem.requests.HTTPError):
        iem.fetch_daily_many("GA_ASOS", ["ABY"], date(2026, 1, 1), date(2026, 1, 2), retries=2)


def test_fetch_daily_rejects_unexpected_response(monkeypatch):
    monkeypatch.setattr(iem.requests, "get", lambda *a, **k: FakeResponse("Error: bad network"))
    with pytest.raises(ValueError, match="unexpected IEM response"):
        iem.fetch_daily("XXX", "NOPE", date(2026, 1, 1), date(2026, 1, 2))


def test_daily_heat_uses_midrange_when_no_mean():
    idx = pd.date_range("2026-03-01", periods=2)
    d = pd.DataFrame({"tmax": [70.0, 70.0], "tmin": [55.0, 40.0]}, index=idx)
    # day 1 is all above 50: (62.5 - 50) * 24 = 300;  day 2 straddles: 12*400/30 = 160
    assert daily_heat(d).tolist() == pytest.approx([300.0, 160.0])


def test_daily_heat_prefers_true_mean_and_falls_back_per_day():
    idx = pd.date_range("2026-03-01", periods=2)
    d = pd.DataFrame(
        {"tmax": [70.0, 70.0], "tmin": [55.0, 55.0], "tmean": [60.0, np.nan]}, index=idx
    )
    assert daily_heat(d).tolist() == pytest.approx([240.0, 300.0])
