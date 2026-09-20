# Forecast accuracy (hindcast)

How good is the forecast peak date? Seasons 2011-2026 were replayed on 1 Feb, 15 Feb, 1 Mar, 15 Mar and 1 Apr for all
272 stations, the way a live run would see them: this year's readings up to that date, plus the **10 most recent
earlier seasons** as analog years (nothing from later leaks in). Each forecast is compared with the day the station
actually crossed the Boyer line. That gives 15,616 forecasts for stations that had not yet crossed.

Reproduce: `uv run --with matplotlib python notes/tools/hindcast.py --analogs prior --window 10 --first-year 2011` (about 3 minutes).
Raw results go to `hindcast.csv.gz` (not tracked). Figure: [accuracy.png](accuracy.png).

## By lead time (days between the forecast and the true crossing)

| Lead | Forecasts | Typical miss (median, days) | Mean error | Within 3 days | Within 5 days | Bias (days, + = late) | Middle-50% range holds the truth |
|---|---|---|---|---|---|---|---|
| 0-7 | 1,719 | 1 | 1.2 | 94% | 99% | +0.5 | 67% |
| 8-14 | 2,041 | 2 | 2.6 | 75% | 89% | +1.4 | 55% |
| 15-28 | 3,855 | 3 | 4.1 | 52% | 74% | +1.8 | 51% |
| 29-42 | 3,412 | 4 | 4.6 | 46% | 66% | +1.6 | 52% |
| 0-10 | 2,589 | 1 | 1.5 | 91% | 98% | +0.6 | 65% |

## What it says

- **Forecasts within 10 days of the peak are good**: half are within a day, 91% within 3 days, 98% within 5. That
  supports the article's "most reliable within 10 days" line.
- **The middle-50% range is honest.** Beyond a week out it holds the true date 50-55% of the time, close to the 50% it
  claims. (Within a week it is very narrow, 2 days, and the truth lands on the median more often.)
- **Places behave alike.** Typical error 3.1-4.1 days for forecasts 8-28 days ahead in every state (Texas closest to zero
  bias, Alabama the largest at +2 days).
- **Most of the error is the season, not the place.** A warm or cold spring shifts every station the same way. Four
  warm late winters (2012, 2017, 2018, 2023) ran 3-7 days late and drive most of the average lateness: without them
  the bias 8-28 days ahead is +0.7 days instead of +1.8.

## Choosing how many analog years

Earlier all-years versions ran late in recent springs (about +2 days for 2019-2026) because recent springs cross earlier
than the long-run average. Dropping older years fixes part of that. Scored the honest way (earlier years only), seasons
2016-2026, forecasts 8-28 days ahead:

| Analog years used | Bias (days) | Typical error (days) | Range holds the truth |
|---|---|---|---|
| all earlier years | +2.6 | 3.7 | 54% |
| last 20 | +2.5 | 3.6 | 55% |
| last 15 | +2.2 | 3.5 | 57% |
| **last 10 (used)** | **+1.5** | **3.4** | 57% |

The last 10 seasons win on every measure and are easy to explain, so that is the default (`ANALOG_WINDOW` in
`src/pollen/season.py`; change it if you prefer 15). Recency weighting was not tried; dropping old years was enough.
It does not remove the warming bias entirely.

## Caveats

- **Errors are correlated within a season**, so the real evidence is 16 seasons, not 15,616 forecasts.
- **Only 16 seasons** (2011-2026) can be scored this way, since a 10-year window needs 10 earlier seasons.
- **This checks the heat-sum forecast, not the pollen.** The "truth" is the day the same temperature data crosses
  the Boyer line. There are no pollen counts in this project, so how well Boyer's threshold matches actual pollen
  in each place is not tested here.
- An earlier version of this page used all years as analogs, leaving out only the forecast year. Its numbers were a
  little better (for example 3.9 days typical error 22-28 days ahead vs 4.6 here) because it also saw years *after*
  the one being forecast; a live run never can.
