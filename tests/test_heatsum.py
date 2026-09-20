import numpy as np
import pandas as pd
import pytest

from pollen.heatsum import daily_from_hourly, fill_short_gaps, lindsey_newman


def test_max_below_base_gives_zero():
    assert lindsey_newman(49.9, 45, 40) == 0.0


def test_whole_day_above_base_uses_mean():
    assert lindsey_newman(70, 62, 55) == pytest.approx((62 - 50) * 24)


def test_min_exactly_at_base_counts_as_whole_day_above():
    assert lindsey_newman(70, 60, 50) == pytest.approx(240.0)


def test_straddling_base_uses_sine_approximation():
    # 12 * (70 - 50)^2 / (70 - 40) = 160
    assert lindsey_newman(70, 55, 40) == pytest.approx(160.0)


def test_max_exactly_at_base_is_zero_heat():
    assert lindsey_newman(50, 45, 40) == pytest.approx(0.0)


def test_vectorized_matches_scalar():
    tmax = np.array([49, 70, 70])
    tmean = np.array([45, 62, 55])
    tmin = np.array([40, 55, 40])
    out = lindsey_newman(tmax, tmean, tmin)
    assert out.tolist() == pytest.approx([0.0, 288.0, 160.0])


@pytest.mark.parametrize("args", [(np.nan, 60, 50), (70, np.nan, 55), (70, 60, np.nan)])
def test_any_missing_input_gives_nan(args):
    # (nan, 60, 50) is a whole-day-above-base case that never reads tmax: still NaN.
    assert np.isnan(lindsey_newman(*args))


def test_series_in_series_out_keeps_index():
    idx = pd.date_range("2026-01-01", periods=3)
    out = lindsey_newman(
        pd.Series([49, 70, 70], index=idx),
        pd.Series([45, 62, 55], index=idx),
        pd.Series([40, 55, 40], index=idx),
    )
    assert isinstance(out, pd.Series)
    assert out.index.equals(idx)
    assert out.tolist() == pytest.approx([0.0, 288.0, 160.0])


def test_mismatched_series_indexes_raise():
    a = pd.Series([70.0], index=pd.date_range("2026-01-01", periods=1))
    b = pd.Series([60.0], index=pd.date_range("2026-01-02", periods=1))
    with pytest.raises(ValueError, match="same index"):
        lindsey_newman(a, b, b)


def test_custom_base_temperature():
    assert lindsey_newman(70, 62, 55, base=40) == pytest.approx((62 - 40) * 24)


def test_daily_from_hourly():
    times = pd.to_datetime(
        ["2026-01-01 00:00", "2026-01-01 12:00", "2026-01-01 23:00", "2026-01-02 06:00"]
    )
    daily = daily_from_hourly(times, [40.0, 60.0, np.nan, 50.0])
    day1 = daily.loc["2026-01-01"]
    assert (day1.tmax, day1.tmean, day1.tmin, day1.n_obs) == (60.0, 50.0, 40.0, 2)
    assert daily.loc["2026-01-02"].n_obs == 1


def test_fill_short_gaps_fills_short_but_not_long_or_edge_gaps():
    idx = pd.date_range("2020-01-01", periods=10)
    s = pd.Series([np.nan, 1.0, np.nan, 3.0, np.nan, np.nan, np.nan, np.nan, 9.0, 10.0], index=idx)
    out = fill_short_gaps(s, limit=3)
    assert np.isnan(out.iloc[0])  # edge gap stays missing
    assert out.iloc[2] == pytest.approx(2.0)  # 1-day gap filled
    # a 4-day gap exceeds limit=3: it stays entirely missing, not partly filled
    assert out.iloc[4:8].isna().all()


def test_fill_short_gaps_works_on_a_table_of_stations():
    idx = pd.date_range("2020-01-01", periods=6)
    t = pd.DataFrame(
        {"a": [1.0, np.nan, 3.0, 4.0, 5.0, 6.0], "b": [1.0, np.nan, np.nan, np.nan, np.nan, 6.0]},
        index=idx,
    )
    out = fill_short_gaps(t, limit=3)
    assert out["a"].tolist() == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert out["b"].iloc[1:5].isna().all()  # 4-day gap left alone
