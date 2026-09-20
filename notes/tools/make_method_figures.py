"""Draw the four figures for the methods page (content/methodology.md) into content/img/.

Example (from the repo root; matplotlib is not a project dependency):
  uv run --with matplotlib python notes/tools/make_method_figures.py

Reads data/history/stations.csv, data/range/pinupalu.geojson, notes/research/stations/survey.csv and
notes/research/accuracy/hindcast.csv.gz. The state outlines are downloaded once (needs internet).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from pollen.geo import load_range  # noqa: E402

OUT = ROOT / "content" / "img"
STATES_URL = "https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json"

INK, INK_2, MUTED, GRID = "#353635", "#52514e", "#8a8a84", "#e1e0d9"
GREEN, GREEN_DK, GREEN_LT, SLATE, RED = "#62A744", "#3d7a26", "#93c470", "#728E9D", "#d62728"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": "#c3c2b7", "axes.labelcolor": INK_2, "xtick.color": INK_2,
                     "ytick.color": INK_2, "text.color": INK, "axes.spines.top": False, "axes.spines.right": False})


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, dpi=160, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", OUT / name)


def state_rings() -> list[np.ndarray]:
    gj = requests.get(STATES_URL, timeout=60).json()
    rings = []
    for f in gj["features"]:
        g = f["geometry"]
        polys = [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]
        rings += [np.array(p[0]) for p in polys]
    return rings


def fig_locations(stations: pd.DataFrame):
    fig, ax = plt.subplots(figsize=(7.4, 5.0))
    for r in state_rings():
        ax.plot(r[:, 0], r[:, 1], color="#cfcfc8", lw=0.7, zorder=1)
    for r in load_range(ROOT / "data" / "range" / "pinupalu.geojson"):
        ax.fill(r[:, 0], r[:, 1], color=GREEN_LT, alpha=0.45, lw=0, zorder=2)
        ax.plot(r[:, 0], r[:, 1], color=GREEN_DK, lw=0.9, zorder=3)
    inside, outside = stations[stations.in_range], stations[~stations.in_range]
    ax.scatter(outside.lon, outside.lat, s=16, facecolor="white", edgecolor=SLATE, lw=0.9, zorder=4,
               label=f"outside the range, within 100 km ({len(outside)})")
    ax.scatter(inside.lon, inside.lat, s=16, color=GREEN_DK, edgecolor="white", lw=0.5, zorder=5,
               label=f"inside the range ({len(inside)})")
    ax.set_xlim(-98.5, -74.5)
    ax.set_ylim(25.0, 38.2)
    ax.set_aspect(1 / np.cos(np.radians(31.5)))
    ax.axis("off")
    ax.legend(loc="lower left", frameon=False, fontsize=9, handletextpad=0.3)
    save(fig, "methods-stations-map.png")


def fig_numbers(stations: pd.DataFrame, survey: pd.DataFrame):
    online = survey[survey.online]
    seasons = online[online.complete_seasons >= 15]
    recent = seasons[seasons.complete_last & seasons.live_ok]
    near = recent[recent.km_outside <= 100]
    steps = [("Airport stations reporting to IEM\nin the Southeast", len(online)),
             ("15 or more complete\nJan-May seasons", len(seasons)),
             ("Complete 2026 season and\nreadings in the last 2 weeks", len(recent)),
             ("Within 100 km of the\nlongleaf range (used)", len(near)),
             ("...of those, inside the range", int(near.in_range.sum()))]
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.6, 4.3), gridspec_kw={"width_ratios": [1.2, 1], "wspace": 0.75})
    y = np.arange(len(steps))[::-1]
    a.barh(y, [n for _, n in steps], color=[SLATE, SLATE, SLATE, GREEN_DK, GREEN], height=0.62)
    for yi, (label, n) in zip(y, steps):
        a.text(n + 8, yi, f"{n:,}", va="center", fontweight="bold", color=INK)
    a.set_yticks(y, [s for s, _ in steps], fontsize=9)
    a.set_xlim(0, max(n for _, n in steps) * 1.16)
    a.set_xticks([])
    a.spines["bottom"].set_visible(False)
    a.set_title("Choosing the stations", loc="left", fontsize=10.5, fontweight="bold")
    counts = stations.n_seasons.value_counts().sort_index()
    b.bar(counts.index, counts.values, color=GREEN_DK, width=0.75)
    b.set_xticks([15, 18, 21, 24, 26])
    b.set_xlabel("complete Jan-May seasons on record (2001-2026)")
    b.set_ylabel("stations")
    b.set_title("How much history each has", loc="left", fontsize=10.5, fontweight="bold")
    b.yaxis.grid(True, color=GRID)
    b.set_axisbelow(True)
    save(fig, "methods-station-numbers.png")


def date_axis(ax, year=2026):
    ticks = [pd.Timestamp(year=year, month=m, day=d).dayofyear for m, d in [(2, 15), (3, 1), (3, 15), (4, 1)]]
    labels = ["Feb 15", "Mar 1", "Mar 15", "Apr 1"]
    ax.set_yticks(ticks, labels)


def fig_replay(h: pd.DataFrame, station="ABY"):
    d = h[(h.station == station)].copy()
    d["as_of"] = pd.to_datetime(d.as_of)
    for col in ("earliest", "median", "latest", "actual"):
        d[col] = pd.to_datetime(d[col])
    counts = d.groupby("year").size()
    years = [y for y in (2013, 2016, 2019, 2025) if counts.get(y, 0) >= 3]
    fig, axes = plt.subplots(1, len(years), figsize=(7.6, 3.7), sharey=True, gridspec_kw={"wspace": 0.14})
    for ax, yr in zip(np.atleast_1d(axes), years):
        g = d[d.year == yr].sort_values("as_of")
        x = np.arange(len(g))
        doy = lambda s: s.dt.dayofyear.to_numpy()  # noqa: E731
        ax.vlines(x, doy(g.earliest), doy(g.latest), color=GREEN, lw=7, alpha=0.45, zorder=2)
        ax.scatter(x, doy(g["median"]), color=GREEN_DK, s=28, zorder=3)
        ax.axhline(g.actual.dt.dayofyear.iloc[0], color=RED, lw=1.5, ls="--", zorder=1)
        ax.set_xticks(x, [f"{a:%b} {a.day}" for a in g.as_of], fontsize=8.5, rotation=40, ha="right")
        ax.set_xlim(-0.6, len(g) - 0.4)
        ax.set_title(str(yr), fontsize=10.5, fontweight="bold", loc="left")
        ax.yaxis.grid(True, color=GRID)
        ax.set_axisbelow(True)
        ax.text(0.03, g.actual.dt.dayofyear.iloc[0] + 1.2, f"actual: {g.actual.iloc[0]:%b} {g.actual.iloc[0].day}", ha="left", va="bottom",
                color=RED, fontsize=8.5, transform=ax.get_yaxis_transform())
        ax.set_ylim(46, 100)
    date_axis(np.atleast_1d(axes)[0])
    np.atleast_1d(axes)[0].set_ylabel("predicted peak date")
    fig.supxlabel("day the forecast was made", color=INK_2, fontsize=9.5, y=-0.06)
    save(fig, "methods-replay-example.png")


def fig_error(h: pd.DataFrame):
    bins = {"0-7": "0-7", "8-14": "8-14", "15-21": "15-28", "22-28": "15-28", "29-42": "29-42"}
    d = h[h.lead_bin.isin(bins)].copy()
    d["group"] = d.lead_bin.map(bins)
    order = ["0-7", "8-14", "15-28", "29-42"]
    labels = ["within a week\nof the peak", "1-2 weeks\nbefore", "2-4 weeks\nbefore", "4-6 weeks\nbefore"]
    data = [d[d.group == g].error_days.to_numpy() for g in order]
    fig, ax = plt.subplots(figsize=(7.4, 3.9))
    parts = ax.boxplot(data, positions=range(len(order)), widths=0.5, whis=(5, 95), showfliers=False, patch_artist=True,
                       medianprops={"color": INK, "lw": 2}, whiskerprops={"color": SLATE}, capprops={"color": SLATE},
                       boxprops={"facecolor": GREEN_LT, "edgecolor": GREEN_DK})
    ax.axhline(0, color=RED, lw=1.3, ls="--")
    ax.set_xticks(range(len(order)), [f"{lab}\n(n = {len(x):,})" for lab, x in zip(labels, data)], fontsize=9)
    ax.set_ylabel("forecast minus actual peak date (days)\nlate (+) / early (-)")
    ax.yaxis.grid(True, color=GRID)
    ax.set_axisbelow(True)
    ax.set_ylim(-12, 13)
    del parts
    save(fig, "methods-forecast-error.png")


def main():
    stations = pd.read_csv(ROOT / "data" / "history" / "stations.csv")
    survey = pd.read_csv(ROOT / "notes" / "research" / "stations" / "survey.csv")
    hind = pd.read_csv(ROOT / "notes" / "research" / "accuracy" / "hindcast.csv.gz")
    fig_locations(stations)
    fig_numbers(stations, survey)
    fig_replay(hind)
    fig_error(hind)


if __name__ == "__main__":
    main()
