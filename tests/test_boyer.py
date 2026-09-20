import numpy as np
import pytest

from pollen.boyer import first_crossing_yday, required_heat_sum


def test_required_heat_sum_matches_published_line():
    assert required_heat_sum(1) == pytest.approx(19009 - 89.26)
    assert required_heat_sum(np.array([70, 100])) == pytest.approx(
        [19009 - 89.26 * 70, 19009 - 89.26 * 100]
    )


def test_first_crossing_finds_first_day_at_or_above_requirement():
    yday = np.array([10, 11, 12, 13])
    need = required_heat_sum(yday)
    cum = need - np.array([500, 100, 0, -400])  # reaches it exactly on day 12
    assert first_crossing_yday(cum, yday) == 12


def test_first_crossing_none_when_never_reached():
    yday = np.array([10, 11])
    assert first_crossing_yday(required_heat_sum(yday) - 1, yday) is None


def test_first_crossing_ignores_nan_days():
    yday = np.array([10, 11, 12])
    cum = np.array([np.nan, required_heat_sum(11) + 5, required_heat_sum(12) + 5])
    assert first_crossing_yday(cum, yday) == 11
