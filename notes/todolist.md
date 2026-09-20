# Pollen prediction: what is left

The build is done: model, daily data run, interactive map, article, tests, and the GitHub Actions (`tests.yml`,
`daily.yml`). This list is only what is still open. (The long decision log and phase checklists were trimmed on
2026-09-20; git history has them, and the reasons behind the choices are below.)

## To go live

- [ ] **GitHub Pages deploy.** Add a deploy job to `daily.yml`: assemble `_site` (index.html, assets, img, data,
      .nojekyll), upload with `upload-pages-artifact`, publish with `deploy-pages` (needs `pages: write` and
      `id-token: write`). Also redeploy on pushes to `main` that touch `site/` or `content/`. Enable Pages with
      `gh api -X POST repos/jbcannon/pollen-prediction/pages -f build_type=workflow` (needs a public repo, or a paid plan).
- [ ] **Keep-alive.** GitHub disables scheduled workflows in a public repo after 60 days without repo activity, and July
      to December has none. Add a monthly job that runs `gh workflow enable daily.yml` (`actions: write`), or run the daily
      job weekly in the off-season.
- [ ] **Before going public:** review `notes/` (decide what stays public); rescan the full git history for the old
      Weather Underground key and SFTP login (the fingerprints are in the assistant's project memory, not here); consider
      squashing history to one clean commit with a local backup bundle (**ask first**); make the repo public; enable Pages.
- [ ] **Review the gallery** (carousel on the front page, `gallery.html#YYYY`): built and previewed with 2001-2008; check all 26
      seasons once `scripts/build_gallery.py` finishes, then commit `site/seasons/` and `site/gallery/`.
- [ ] Link from `lab.jonesctr.org/pollen-shedding-countdown-for-longleaf-pine/` to the new site (a link or button; the
      WordPress site is separate and cannot embed it). The old page itself stays as it is.

## Each year

- [ ] **2 June: check that `extend-history.yml` ran** (it adds the finished season to the history and the gallery, commits, and
      starts the daily run). It has not run in GitHub yet, so watch the first one (2 June 2027, or start it by hand from the
      Actions tab to test it).
- [ ] Re-run the station survey (`notes/research/stations/survey.py`) to pick up stations that newly reach 15 seasons or stopped
      reporting, and review the changes before they reach the map. The station list is frozen until then.
- [ ] Re-run the accuracy check (`notes/tools/hindcast.py`) only if the method or analog window changes. The numbers typed
      into the articles are locked in at the values from the 2011-2026 run.

## Why it works the way it does

- **Stations:** IEM airport (ASOS/AWOS) daily max/min, no key needed. Of 642 online stations in the region, 345 have 15+
  complete seasons, a complete 2026 season and recent data; 272 of those are within 100 km of the longleaf range (153
  inside it). 84% of the range is within 50 km of a station and all of it within 100 km. The Weather Underground API
  is tied to one key and rate-limited, and personal stations are uneven in quality. Stations keep different history
  lengths (15+ seasons); the history grows each June.
- **Heat sum:** hourly data is not needed. The model uses only each day's max and min; the mean, (max+min)/2, matters only
  on days when the minimum is 50 F or higher. Tested at Camilla (2026): it moved the Boyer crossing by one day. Albany
  ASOS (about 25 miles away) crossed within 2 days of Camilla's own station.
- **Forecast:** this year's accumulated heat is fixed; each of the last 10 springs is replayed from tomorrow on top of
  it, giving one crossing date per scenario. The range is the middle 50%. Using only the most recent 10 seasons cut the
  late bias from +2.6 to +1.5 days (all-years analogs ran late as springs warmed). Scenarios that never cross by 31 May
  give an open-ended range.
- **Map surface:** a thin-plate spline through the stations' peak dates, smoothing chosen by leave-one-out (hidden
  stations are predicted within about 1.9 days). Drawn only inside the Little longleaf polygon, using stations up to
  100 km outside it. Elevation was tested and left out: it changed the hidden-station error by less than 0.05 days,
  because the range is flat (median station elevation 41 m). Revisit if the map ever reaches the Piedmont or the
  Appalachians.
- **Site:** static page (MapLibre, no build step for the map) served by GitHub Pages, separate from the WordPress lab
  site; its header links back to lab.jonesctr.org/cannon/ with full URLs.
