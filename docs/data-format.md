# Data files the page reads

`scripts/run_daily.py` writes four files to `site/data/`; `site/assets/map.js` reads them. `latest.json` loads
first (enough to draw the map) and the others follow. Dates are ISO strings (`"2026-03-05"`), missing values are
`null`, and heat is degree-hours above 50 F accumulated from Jan 1. The Boyer requirement on any day is
`boyer_b0 + boyer_b1 * day_of_year`, using the constants in `method`. The JSON files carry `"schema": 1`, which
goes up if a field changes meaning or is removed.

## latest.json

`season`, `as_of` (the day the run describes), `generated_at`, `mode` (`live`; `outlook`, June to 1 January, the next season's
forecast with no readings yet: `as_of` is the 31 December before it, `cum_heat` is 0, `data_through` is `null`; or `replay`), `method` (the model
constants), `summary` (station counts by status, earliest and latest peak date) and `stations`: one record each.

| Station field | Meaning |
|---|---|
| `id`, `name`, `state`, `lat`, `lon`, `elevation_m` | the IEM station |
| `in_range`, `km_outside` | inside the longleaf range, or km from its edge (all are within 100) |
| `n_seasons` | complete Jan-May seasons of history behind it |
| `status` | `crossed`, `forecast`, `insufficient_data` (too many missing days), `no_analogs` or `no_data` |
| `data_through`, `days_behind` | last day with a reading, and how far that is behind `as_of` |
| `cum_heat`, `required_heat` | heat so far on `data_through`, and the Boyer requirement that day |
| `crossing_date` | when it crossed (`crossed` only) |
| `forecast_earliest`, `forecast_median`, `forecast_latest` | the forecast range, the middle half of the scenarios (`forecast` only); `null` where they cross after 31 May |
| `n_scenarios`, `n_not_crossed` | analog years behind the forecast, and how many never cross by 31 May |
| `peak_date` | the date to map: `crossing_date` if crossed, else `forecast_median` |

## series.json

The hover and panel charts. `stations[id]` has `cum` (accumulated heat per day from `cum_start` to
`data_through`) and, for stations not yet crossed, `band`: `start` (the day after `data_through`) and `lo`, `mid`,
`hi` (25th percentile, median and 75th percentile of the scenarios, one value per day). Stations with no data have
no entry.

## surface.json

One peak date for every 0.05 degree cell inside the longleaf range, smoothed between stations (thin-plate spline;
`fit` reports the leave-one-out error). `grid` gives the corner (`lon0`, `lat0`), `step`, `n_lon` and `n_lat`.
`values` is `n_lat * n_lon` day-of-year numbers, row 0 the northernmost, columns running west to east, `null` outside
the range. Cell (row r, column c) is at longitude `lon0 + c * step`, latitude `lat0 - r * step`. `range` gives the
earliest and latest value, for the color scale.

## seasons/ (finished seasons, for the gallery)

`site/seasons/YYYY/` holds the same four files for a finished season (`latest.json` has `"mode": "archive"`; every station
has a crossing date or no data, and `series.json` covers only the stations inside the range). `site/seasons/index.json` lists
the seasons newest first (`year`, `stations`, `in_range`, and `first`/`median`/`last`, the earliest, middle and latest peak date
across the range) plus the `scale` (`lo`, `hi` day of year) that every season's colors share. `site/gallery/thumbs/YYYY.png` is
the static picture of each. `scripts/build_gallery.py` writes all of it.

## contours.geojson

One `MultiLineString` per day across the surface's date range, with properties `date`, `label`, `yday` and `tier`:
`index` (every 15 days, labelled), `five` (every 5) or `day` (the rest, faint). Coordinates are `[lon, lat]`, and
lines stop at the range edge.
