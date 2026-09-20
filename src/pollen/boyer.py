"""Boyer's required heat sum for peak longleaf pine pollen shed.

Peak shed is expected on the day the accumulated heat sum reaches
``B0 + B1 * yday`` (yday = day of year, Jan 1 = 1). The requirement falls as
the season goes on, so warm-season heat only has to make up the difference.
"""

from __future__ import annotations

import numpy as np

B0 = 19009.0
B1 = -89.26


def required_heat_sum(yday):
    """Heat sum (degree-hours) needed to reach peak shed by ``yday``."""
    return B0 + B1 * np.asarray(yday, dtype=float)


def first_crossing_yday(cumulative, yday) -> int | None:
    """First day-of-year where ``cumulative`` reaches the requirement, else None.

    ``cumulative`` and ``yday`` are parallel sequences (one entry per day).
    """
    cumulative = np.asarray(cumulative, dtype=float)
    yday = np.asarray(yday)
    hit = cumulative >= required_heat_sum(yday)  # NaN compares False
    return int(yday[hit.argmax()]) if hit.any() else None
