"""Regional accuracy check: replay every season on several dates and score the forecasts.

Example (from the repo root; matplotlib is not a project dependency):
  uv run --with matplotlib python notes/tools/hindcast.py --analogs prior --window 10 --first-year 2011
Writes notes/research/accuracy/hindcast.csv.gz (all forecasts with their true outcome; gitignored)
and notes/research/accuracy/accuracy.png, and prints the summary tables.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from pollen_hindcast import LEAD_LABELS, add_errors, hindcast, summarize
from pollen.history import load_history

ROOT = Path(__file__).resolve().parents[2]
STORE = ROOT / "data" / "history"
OUT = ROOT / "notes" / "research" / "accuracy"
SURFACE, INK, INK_2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
BLUE, ORANGE = "#2a78d6", "#eb6834"
DEFAULT_DATES = "02-01,02-15,03-01,03-15,04-01"


def parse_dates(text: str) -> list[tuple[int, int]]:
    return [tuple(int(p) for p in d.split("-")) for d in text.split(",")]


def style(ax, title, ylabel):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=11, color=INK, fontweight="bold")
    ax.set_ylabel(ylabel, color=INK_2)
    ax.set_xlabel("days between the forecast and the true crossing", color=INK_2)
    ax.tick_params(colors=MUTED, labelsize=9)
    ax.grid(axis="y", color="#e1e0d9", lw=0.6)
    for spine in ax.spines.values():
        spine.set_color(AXIS)


def draw(scored: pd.DataFrame, by_lead: pd.DataFrame, analogs: str):
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.8), facecolor=SURFACE)
    x = range(len(by_lead))
    labels = list(by_lead.index)

    ax = axes[0]
    style(ax, "Error of the median forecast date", "days")
    ax.plot(x, by_lead["mae_days"], color=BLUE, marker="o", lw=2, label="typical error (mean absolute)")
    ax.plot(x, by_lead["bias_days"], color=ORANGE, marker="o", lw=2, label="bias (+ = forecast too late)")
    ax.axhline(0, color=AXIS, lw=1)
    ax.set_xticks(list(x), labels)
    ax.legend(fontsize=9, frameon=False, labelcolor=INK_2)

    ax = axes[1]
    style(ax, "Does the middle-50% range hold the truth?", "share of forecasts")
    ax.plot(x, by_lead["range_coverage"], color=BLUE, marker="o", lw=2)
    ax.axhline(0.5, color=ORANGE, lw=1.5, ls="--")
    ax.text(0, 0.45, "50% = what an honest range would show", ha="left", color=INK_2, fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_xticks(list(x), labels)

    ax = axes[2]
    mid = scored[scored["lead_bin"].isin(["15-21", "22-28"])]
    yearly = summarize(mid, "year")
    style(ax, "Bias by year (forecasts 15-28 days ahead)", "days (+ = forecast too late)")
    ax.set_xlabel("season", color=INK_2)
    colors = [ORANGE if v > 0 else BLUE for v in yearly["bias_days"]]
    ax.bar([str(y) for y in yearly.index], yearly["bias_days"], color=colors)
    ax.axhline(0, color=AXIS, lw=1)
    ax.tick_params(axis="x", rotation=90)

    fig.suptitle(f"Forecast accuracy, all seasons and stations (analogs: {analogs})", x=0.01, ha="left",
                 fontsize=14, fontweight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "accuracy.png", dpi=120, facecolor=SURFACE)


def main():
    sys.stdout.reconfigure(line_buffering=True)
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--analogs", choices=["others", "prior"], default="others")
    p.add_argument("--dates", default=DEFAULT_DATES, help="forecast dates as MM-DD,MM-DD,...")
    p.add_argument("--first-year", type=int, default=None)
    p.add_argument("--window", type=int, default=None,
                   help="with --analogs prior: use only the most recent N earlier years")
    p.add_argument("--redraw", action="store_true", help="redraw the figure from the saved results")
    args = p.parse_args()
    label = args.analogs if args.window is None else f"{args.analogs}, last {args.window} years"

    if args.redraw:
        scored = pd.read_csv(OUT / "hindcast.csv.gz", parse_dates=["as_of", "earliest", "median", "latest", "actual"])
        by_lead = summarize(scored, "lead_bin").reindex(LEAD_LABELS).dropna(subset=["n"])
        draw(scored, by_lead, label)
        print("wrote", OUT / "accuracy.png")
        return

    history = load_history(STORE / "daily.csv.gz")
    stations = pd.read_csv(STORE / "stations.csv")[["id", "state", "in_range"]]
    years_all = sorted(history["date"].dt.year.unique())
    years = [y for y in years_all if args.first_year is None or y >= args.first_year]
    print(f"{len(years)} seasons x {len(parse_dates(args.dates))} dates, analogs: {label}")

    start = time.time()
    raw = hindcast(history, years, parse_dates(args.dates), analogs=args.analogs, window=args.window,
                   progress=lambda m: print(f"  {m} ({time.time() - start:.0f}s)"))
    scored = add_errors(raw).merge(stations, left_on="station", right_on="id").drop(columns="id")
    OUT.mkdir(parents=True, exist_ok=True)
    scored.to_csv(OUT / "hindcast.csv.gz", index=False, date_format="%Y-%m-%d")

    pd.set_option("display.width", 200)
    by_lead = summarize(scored, "lead_bin").reindex(LEAD_LABELS).dropna(subset=["n"])
    print(f"\n{len(scored):,} scored forecasts")
    print("\n=== by lead time (days before the true crossing)")
    print(by_lead.round(2).to_string())
    mid = scored[scored["lead_bin"].isin(["8-14", "15-21", "22-28"])]
    print("\n=== by state, forecasts 8-28 days ahead")
    print(summarize(mid, "state").round(2).to_string())
    print("\n=== by season, forecasts 8-28 days ahead")
    print(summarize(mid, "year").round(2).to_string())
    draw(scored, by_lead, label)
    print("\nwrote", OUT / "accuracy.png")


if __name__ == "__main__":
    main()
