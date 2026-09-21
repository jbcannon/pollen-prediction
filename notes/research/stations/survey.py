"""Survey IEM airport (ASOS/AWOS) stations in the Southeast for use in the pollen map.

For every station in the AOI, pull daily max/min back to 2001 and score how many
complete Jan-May seasons it has as analog years (every season since 2001 that is
fully in the past, so the window grows by itself each June), and whether the most
recent one is complete. Writes survey.csv and survey-map.png next to this script.

Run from the repo root:  uv run --with matplotlib python notes/research/stations/survey.py
Downloads are cached in research/stations/cache/ (gitignored); delete to refresh.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, date, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

from pollen import geo
from pollen.geo import in_range, km_to_range
from pollen.heatsum import daily_heat, fill_short_gaps
from pollen.iem import fetch_daily, list_stations

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CACHE = HERE / "cache"
RANGE = ROOT / "data" / "range" / "pinupalu.geojson"
STATES_URL = "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json"

STATES = ["TX", "LA", "MS", "AL", "GA", "FL", "SC", "NC", "VA", "TN", "AR"]
# Longleaf-range bbox (lon -95.22..-75.80, lat 26.62..36.85) plus a ~0.75 degree margin.
BBOX = (-96.0, -75.0, 25.9, 37.6)
TODAY = datetime.now(UTC).date()
FIRST_YEAR = 2001
# Last season (Jan-May) that is fully in the past: the current year counts once May has ended.
LAST_YEAR = TODAY.year if TODAY >= date(TODAY.year, 6, 1) else TODAY.year - 1
MIN_SEASONS = 15  # complete Jan-May seasons needed to count as having usable history
MAX_KM_FROM_RANGE = 100  # drop stations farther than this from the longleaf range polygon


def load_range() -> list[np.ndarray]:
    return geo.load_range(RANGE)

def get_daily(station: str, network: str) -> pd.DataFrame | None:
    """Daily max/min 2001-01-01 to today, cached on disk. None if the request failed."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"{network}_{station}.csv"
    if path.exists():
        return pd.read_csv(path, index_col="date", parse_dates=["date"])
    for attempt in (1, 2):
        try:
            df = fetch_daily(station, network, date(FIRST_YEAR, 1, 1), TODAY)
            df.to_csv(path)
            time.sleep(0.25)
            return df
        except (requests.RequestException, ValueError) as exc:
            print(f"    {network}/{station} attempt {attempt} failed: {exc}")
            time.sleep(2)
    return None


def season_complete(df: pd.DataFrame, year: int) -> bool:
    """True if Jan 1 - May 31 has a heat value every day once gaps of <=3 days are filled."""
    days = pd.date_range(f"{year}-01-01", f"{year}-05-31")
    s = df.reindex(days)
    return bool(fill_short_gaps(daily_heat(s)).notna().all())


def score(df: pd.DataFrame | None) -> dict:
    if df is None or df.dropna(how="all").empty:
        return {"n_days": 0, "first_date": None, "last_date": None, "complete_seasons": 0,
                "complete_last": False}
    valid = df.dropna(how="all")
    seasons = [y for y in range(FIRST_YEAR, LAST_YEAR + 1) if season_complete(df, y)]
    return {
        "n_days": len(valid),
        "first_date": valid.index.min().date(),
        "last_date": valid.index.max().date(),
        "complete_seasons": len(seasons),
        "complete_last": season_complete(df, LAST_YEAR),
    }


def haversine_km(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def coverage(rings, stations: pd.DataFrame) -> dict:
    """Share of the longleaf range within 50/100 km of a station (0.25 degree grid)."""
    lons = np.arange(BBOX[0], BBOX[1], 0.25)
    lats = np.arange(BBOX[2], BBOX[3], 0.25)
    pts = [(x, y) for x in lons for y in lats if in_range(rings, x, y)]
    d = np.array([haversine_km(x, y, stations.lon.to_numpy(), stations.lat.to_numpy()).min() for x, y in pts])
    return {"grid_cells": len(pts), "within_50km": float((d <= 50).mean()),
            "within_100km": float((d <= 100).mean()), "max_km": float(d.max())}


SURFACE, INK, INK_2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
# One-hue ordinal ramp (blue steps 250 / 450 / 700): darker = longer history.
HISTORY_BINS = [
    ("15-19 seasons", 15, 19, "#86b6ef", 26),
    ("20-24 seasons", 20, 24, "#2a78d6", 34),
    ("25+ seasons", 25, 99, "#0d366b", 44),
]


def draw_map(good: pd.DataFrame, rings):
    """Map of the stations in use, colored (and sized) by how many seasons of history they have."""
    states_path = CACHE / "us-states.json"
    if not states_path.exists():
        states_path.write_bytes(requests.get(STATES_URL, timeout=60).content)
    states = json.loads(states_path.read_text())
    fig, ax = plt.subplots(figsize=(11, 8), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for f in states["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        for poly in polys:
            r = np.array(poly[0])
            ax.fill(r[:, 0], r[:, 1], color="#f0efec", ec=AXIS, lw=0.6, zorder=1)
    for r in rings:
        ax.fill(r[:, 0], r[:, 1], color="#62A744", alpha=0.22, ec="#3d7a26", lw=0.8, zorder=2)
    for label, lo, hi, color, size in HISTORY_BINS:
        sub = good[good.complete_seasons.between(lo, hi)]
        ax.scatter(sub.lon, sub.lat, s=size, c=color, edgecolors=SURFACE, linewidths=0.9,
                   label=f"{label} (n={len(sub)})", zorder=4)
    ax.set_xlim(BBOX[0] - 1, BBOX[1] + 1)
    ax.set_ylim(BBOX[2] - 1, BBOX[3] + 1)
    ax.set_aspect(1 / np.cos(np.radians(32)))
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    for spine in ax.spines.values():
        spine.set_color(AXIS)
    n_in = int(good.in_range.sum())
    fig.suptitle(f"{len(good)} weather stations used for the pollen map", x=0.02, ha="left",
                 fontsize=15, fontweight="bold", color=INK)
    ax.set_title(f"{n_in} inside the longleaf pine range (green), none farther than {MAX_KM_FROM_RANGE} km from it. "
                 f"Color = complete Jan-May seasons of history, 2001-{LAST_YEAR}.",
                 loc="left", fontsize=10, color=INK_2)
    leg = ax.legend(loc="lower left", frameon=True, facecolor=SURFACE, edgecolor=AXIS, fontsize=10,
                    title="History length", title_fontsize=10)
    for text in [*leg.get_texts(), leg.get_title()]:
        text.set_color(INK_2)
    fig.tight_layout()
    fig.savefig(HERE / "survey-map.png", dpi=120, facecolor=SURFACE)


def main():
    sys.stdout.reconfigure(line_buffering=True)  # show progress live even when piped
    if "--map-only" in sys.argv:  # redraw the map from the last survey.csv
        res = pd.read_csv(HERE / "survey.csv")
        draw_map(res[res.usable], load_range())
        print("wrote", HERE / "survey-map.png")
        return
    frames = []
    for st in STATES:
        try:
            frames.append(list_stations(f"{st}_ASOS"))
        except requests.RequestException as exc:
            print(f"could not list {st}_ASOS: {exc}")
    meta = pd.concat(frames, ignore_index=True)
    inside = meta.lon.between(BBOX[0], BBOX[1]) & meta.lat.between(BBOX[2], BBOX[3])
    meta = meta[inside].copy()
    print(f"{len(meta)} stations in the AOI bbox ({meta.online.sum()} online)")

    rings = load_range()
    meta["in_range"] = [in_range(rings, x, y) for x, y in zip(meta.lon, meta.lat)]
    meta["km_outside"] = [round(km_to_range(rings, x, y), 1) for x, y in zip(meta.lon, meta.lat)]

    rows = []
    todo = meta[meta.online]
    for i, (_, s) in enumerate(todo.iterrows(), 1):
        print(f"[{i}/{len(todo)}] {s.network}/{s.id} {s['name']}")
        rows.append({"id": s.id, **score(get_daily(s.id, s.network))})
    scores = pd.DataFrame(rows)
    res = meta.merge(scores, on="id", how="left")
    recent = pd.Timestamp(TODAY) - pd.Timedelta(days=14)
    res["live_ok"] = res.last_date.notna() & (pd.to_datetime(res.last_date) >= recent)
    data_ok = (res.complete_seasons >= MIN_SEASONS) & res.complete_last.fillna(False) & res.live_ok
    res["usable"] = data_ok & (res.km_outside <= MAX_KM_FROM_RANGE)
    res.to_csv(HERE / "survey.csv", index=False)

    good = res[res.usable]
    print("\n=== summary")
    print(f"online stations scored: {len(todo)}")
    print(f">= {MIN_SEASONS} complete seasons of {LAST_YEAR - FIRST_YEAR + 1}: {(res.complete_seasons >= MIN_SEASONS).sum()}")
    print(f"complete {LAST_YEAR} season: {res.complete_last.fillna(False).sum()}   reporting in last 14 days: {res.live_ok.sum()}")
    print(f"passing the data rules: {data_ok.sum()}   dropped for being > {MAX_KM_FROM_RANGE} km from the range: {(data_ok & ~res.usable).sum()}")
    print(f"USABLE (data rules + within {MAX_KM_FROM_RANGE} km of range): {len(good)}   of which inside the range: {good.in_range.sum()}")
    print("usable by state:", good.state.value_counts().to_dict())
    print("seasons distribution among online stations:", res[res.online].complete_seasons.describe().round(1).to_dict())
    cov = coverage(rings, good)
    print(f"range coverage by usable stations: {cov}")
    draw_map(good, rings)
    print("wrote", HERE / "survey.csv", "and survey-map.png")


if __name__ == "__main__":
    main()
