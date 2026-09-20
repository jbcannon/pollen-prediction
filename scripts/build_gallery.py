"""Build the gallery of finished seasons: one final map per year, and a thumbnail of each.

  site/seasons/YYYY/{latest,series,surface}.json, contours.geojson   the season's data, same format as the live map
  site/seasons/index.json                                            one line per season + the shared color scale
  site/gallery/thumbs/YYYY.png                                       the small static picture in the carousel

The pages read these (the carousel on the front page, and gallery.html#YYYY, which draws the season on the
interactive map). Every season uses the same color scale, so years can be compared by eye; the scale only ever
widens, so old thumbnails stay valid.

    uv run python scripts/build_gallery.py                # all complete seasons (about 20 minutes the first time)
    uv run python scripts/build_gallery.py --only-missing # just the seasons not built yet (the yearly workflow)
    uv run python scripts/build_gallery.py --thumbs-only  # redraw the thumbnails from the data on disk

The thumbnails need matplotlib, which is in the "gallery" dependency group: uv sync --group gallery
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from pollen.archive import season_files, shared_scale, summarize, write_index
from pollen.geo import load_range
from pollen.history import last_complete_year, load_history
from pollen.season import heat_table

ROOT = Path(__file__).resolve().parents[1]
FIRST_YEAR = 2001
RAMP = ["#f4e04d", "#b6d957", "#5fc16f", "#23a5a0", "#2a78d6", "#4b4ba8", "#3a1c63"]  # same as site/assets/map.js


def existing_index(root: Path) -> dict:
    path = root / "index.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"scale": None, "seasons": []}


FILES = ("latest.json", "series.json", "surface.json", "contours.geojson")


def summary_from_disk(season_dir: Path) -> dict | None:
    """A built season's index line, read back from its files (None if any file is missing or unreadable)."""
    try:
        latest = json.loads((season_dir / "latest.json").read_text(encoding="utf-8"))
        surface = json.loads((season_dir / "surface.json").read_text(encoding="utf-8"))
        if not all((season_dir / name).exists() for name in FILES):
            return None
    except (OSError, ValueError):
        return None
    return {**summarize(latest), "range": surface["range"]}


def draw_thumb(season_dir: Path, out: Path, scale: dict[str, int], states: list[np.ndarray], outline: list[np.ndarray]) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    doc = json.loads((season_dir / "surface.json").read_text(encoding="utf-8"))
    g = doc["grid"]
    values = np.array([np.nan if v is None else v for v in doc["values"]], dtype=float).reshape(g["n_lat"], g["n_lon"])
    half = g["step"] / 2
    extent = (g["lon0"] - half, g["lon0"] + (g["n_lon"] - 1) * g["step"] + half,
              g["lat0"] - (g["n_lat"] - 1) * g["step"] - half, g["lat0"] + half)
    fig = plt.figure(figsize=(4.8, 3.38), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    for ring in states:
        ax.plot(ring[:, 0], ring[:, 1], color="#d3d3cc", lw=0.5, zorder=1)
    ax.imshow(np.ma.masked_invalid(values), extent=extent, origin="upper", zorder=2, interpolation="bilinear",
              cmap=LinearSegmentedColormap.from_list("ramp", RAMP), vmin=scale["lo"], vmax=scale["hi"])
    xs = np.linspace(extent[0] + half, extent[1] - half, g["n_lon"])
    ys = np.linspace(extent[3] - half, extent[2] + half, g["n_lat"])
    levels = np.arange(np.ceil(scale["lo"] / 5) * 5, scale["hi"] + 1, 5)
    ax.contour(xs, ys, np.ma.masked_invalid(values), levels=levels, colors="#0b0b0b", linewidths=0.4, alpha=0.4, zorder=3)
    for ring in outline:
        ax.plot(ring[:, 0], ring[:, 1], color="#1f5d1f", lw=0.7, zorder=4)
    ax.set_xlim(-95.2, -75.6)
    ax.set_ylim(25.6, 37.2)
    ax.set_aspect(1 / np.cos(np.radians(31.5)))
    ax.axis("off")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor="white", metadata={"Software": None}, pil_kwargs={"optimize": True})
    plt.close(fig)


def states_rings() -> list[np.ndarray]:
    gj = json.loads((ROOT / "data" / "basemap" / "us-states.geojson").read_text(encoding="utf-8"))
    rings = []
    for f in gj["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        rings += [np.array(p[0]) for p in polys]
    return rings


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--years", type=int, nargs="*", help="only these seasons (default: every complete one)")
    p.add_argument("--only-missing", action="store_true", help="skip seasons that are already built")
    p.add_argument("--thumbs-only", action="store_true", help="redraw thumbnails from the data on disk")
    p.add_argument("--no-thumbs", action="store_true")
    p.add_argument("--smoothing", type=float, default=None, help="fix the surface smoothing (default: choose it per season)")
    p.add_argument("--out", type=Path, default=ROOT / "site" / "seasons")
    p.add_argument("--thumbs", type=Path, default=ROOT / "site" / "gallery" / "thumbs")
    args = p.parse_args()
    sys.stdout.reconfigure(line_buffering=True)

    index = existing_index(args.out)
    summaries = {s["year"]: s for s in index["seasons"]}
    if not args.thumbs_only:
        history = load_history(ROOT / "data" / "history" / "daily.csv.gz")
        stations = pd.read_csv(ROOT / "data" / "history" / "stations.csv")
        newest = min(int(history["date"].dt.year.max()), last_complete_year(datetime.now(UTC).date()))
        years = args.years or list(range(FIRST_YEAR, newest + 1))
        table = heat_table(history)
        ranges = {s["year"]: s.get("range") for s in index["seasons"]}
        for year in years:
            if args.only_missing and (done := summary_from_disk(args.out / str(year))) is not None:
                summaries[year], ranges[year] = done, done["range"]   # already built (e.g. by a run that was interrupted)
                continue
            t0 = time.time()
            s = season_files(history, stations, year, args.out / str(year), ROOT / "data" / "surface" / "mask.npz",
                             table=table, surface_smoothing=args.smoothing)
            ranges[year] = s.pop("surface_range")
            s.pop("bytes")
            summaries[year] = {**s, "range": ranges[year]}
            print(f"{year}: {s['in_range']} stations in range, peak {s['first']} to {s['last']} (median {s['median']}), "
                  f"{time.time() - t0:.0f} s", flush=True)
        # the shared scale only widens, so thumbnails drawn earlier stay valid
        scale = shared_scale([{"surface_range": r} for r in ranges.values() if r])
        old = index.get("scale")
        if old:
            scale = {"lo": min(scale["lo"], old["lo"]), "hi": max(scale["hi"], old["hi"])}
        path = write_index(args.out, list(summaries.values()), scale)
        index = json.loads(path.read_text(encoding="utf-8"))
    scale = index["scale"]
    if not args.no_thumbs:
        states, outline = states_rings(), load_range(ROOT / "data" / "range" / "pinupalu.geojson")
        for s in index["seasons"]:
            draw_thumb(args.out / str(s["year"]), args.thumbs / f"{s['year']}.png", scale, states, outline)
        print(f"drew {len(index['seasons'])} thumbnails (color scale day {scale['lo']} to {scale['hi']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
