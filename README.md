# Longleaf pine pollen countdown (Southeast US)

[![Tests](https://github.com/jbcannon/pollen-prediction/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/jbcannon/pollen-prediction/actions/workflows/tests.yml)
[![Daily forecast](https://github.com/jbcannon/pollen-prediction/actions/workflows/daily.yml/badge.svg?branch=main)](https://github.com/jbcannon/pollen-prediction/actions/workflows/daily.yml)
[![Yearly history and gallery](https://github.com/jbcannon/pollen-prediction/actions/workflows/extend-history.yml/badge.svg)](https://github.com/jbcannon/pollen-prediction/actions/workflows/extend-history.yml)

**Live site: <https://jbcannon.github.io/pollen-prediction/>**

A daily forecast of when longleaf pine (*Pinus palustris*) pollen shedding will peak, mapped across the
Southeast. It uses Boyer's (1973) heat-sum model and daily temperatures from airport weather stations.
The page is a static site (`site/`) rebuilt every morning by a GitHub Action and served with GitHub Pages.

## How it works

1. **Heat sum.** Each day's high and low temperature give degree-hours above 50 °F (Lindsey & Newman 1956).
   They add up from January 1.
2. **Threshold.** Peak shedding is expected on the day the running total reaches `19009 - 89.26 * day_of_year`
   (Boyer 1973).
3. **Forecast.** For a station that has not crossed yet, each of the last 10 springs is replayed from tomorrow
   onward on top of this year's total. Each spring gives one crossing date; the middle half of those dates is
   the forecast range.
4. **Map.** The stations' dates are smoothed into a surface over the longleaf pine range, with contour lines.

## What's here

| Path | What |
|---|---|
| `site/` | The web pages (`index.html`, `gallery.html`), the finished seasons (`seasons/`, `gallery/thumbs/`), the map (`assets/map.js`), "find my location" and click-to-read (`assets/locate.js`), styles, images. `site/data/` is built daily and not committed. |
| `content/` | The article text (`boyer-article.md`, and `methodology.md`, the collapsed section) and its images. `scripts/build_site.py` turns them into the pages in `site/`. |
| `src/pollen/` | The model: heat sums, the Boyer threshold, the forecast, IEM data access, the map surface, and the daily run (`live.py`) |
| `scripts/` | `run_daily.py` (the daily job), `build_gallery.py` (finished seasons and thumbnails), `dev.py` (live preview; `preview.bat` on Windows), `build_site.py`, `build_history.py` (yearly), `check_site.py` (browser test) |
| `data/history/` | Daily temperatures for 2001 onward at the 272 stations, and the station list |
| `data/basemap/` | US state outlines, for the gallery thumbnails |
| `data/range/`, `data/surface/` | The longleaf pine range outline (Little) and the map mask built from it |
| `docs/data-format.md` | The JSON files the page reads |
| `notes/` | To-do list, article follow-ups, the accuracy (hindcast) research and the tools behind it, and the station survey |
| `tests/` | Unit tests plus a few real-data regression checks |
| `.github/workflows/` | `tests.yml` (every push), `daily.yml` (the daily forecast, and publishing to Pages), `extend-history.yml` (each 2 June: the finished season goes into the history and the gallery), `keepalive.yml` |

## Running it

Uses [uv](https://docs.astral.sh/uv/) and Python 3.12.

```sh
uv sync                                                                  # install dependencies
uv run python scripts/dev.py                                             # live preview at http://localhost:8000
uv run pytest                                                            # run the tests
uv run python scripts/run_daily.py --out site/data                       # fetch today's data and forecast
```

On Windows you can double-click `preview.bat` instead of typing the preview command.

`scripts/dev.py` serves `site/`, rebuilds the page whenever you save the article, template or assets, and
reloads the browser. (Opening `site/index.html` by double-click does not work: browsers block a `file://`
page from reading the data files, so the map has to be served.)

`--today 2026-03-16` on `run_daily.py` pretends it is another day, which is handy for testing outside the season. From June to
1 January there is no season to track, so it writes the next season's preseason outlook instead: every station starts at zero heat
and is forecast from the last ten springs alone.

## Data and credits

- Temperatures: daily station summaries from the [Iowa Environmental Mesonet](https://mesonet.agron.iastate.edu/)
  (Iowa State University), which archives NWS/FAA airport (ASOS/AWOS) observations.
- Range map: E. L. Little Jr., *Atlas of United States Trees*; public domain, mirrored at
  [wpetry/USTreeAtlas](https://github.com/wpetry/USTreeAtlas).
- Basemap: [OpenFreeMap](https://openfreemap.org/) with data from OpenStreetMap, drawn with
  [MapLibre GL JS](https://maplibre.org/).
- Model: Boyer, W. D. (1973). Air temperature, heat sums, and pollen shedding phenology of longleaf pine.
  *Ecology* 54(2): 420-426. Lindsey, A. A. & Newman, J. E. (1956), heat-sum method.

## License

The code is MIT licensed (see `LICENSE`). The article text and images are not covered by it: all rights reserved,
and the reproduced figures belong to their owners as credited.
