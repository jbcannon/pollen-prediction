"""Load the built site in a real headless browser, use the map like a visitor, and save screenshots.

    uv run --with playwright python scripts/check_site.py
    (first time only: uv run --with playwright python -m playwright install chromium)

Needs site/index.html (scripts/build_site.py) and some data in site/data/ (scripts/run_daily.py).
Writes screenshots to figures/site/ and exits 1 if the page logs errors or the map does not come up.
"""

from __future__ import annotations

import functools
import http.server
import io
import sys
import threading
from pathlib import Path

from PIL import Image
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
OUT = ROOT / "figures" / "site"


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve() -> tuple[http.server.ThreadingHTTPServer, str]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(SITE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/"


def station_pixel(page) -> dict:
    """Screen position of one in-range station dot, found through the map itself."""
    return page.evaluate("""() => {
      const m = window.pollenMap;
      const f = m.queryRenderedFeatures({layers: ['stations']}).filter(x => x.properties.status === 'forecast')[0]
             || m.queryRenderedFeatures({layers: ['stations']})[0];
      const p = m.project(f.geometry.coordinates), r = m.getCanvas().getBoundingClientRect();
      return {x: r.left + p.x, y: r.top + p.y, id: f.properties.id};
    }""")


def blank_map_share(page) -> float:
    """Share of sampled points on the map, outside the detail panel, that show the bare container colour."""
    box = page.evaluate("""() => { const w = document.querySelector('.map-wrap').getBoundingClientRect(),
        p = document.querySelector('#panel').getBoundingClientRect();
        return {w: [w.left, w.top, w.width, w.height], p: [p.left, p.top, p.width, p.height]}; }""")
    im = Image.open(io.BytesIO(page.screenshot())).convert("RGB")
    (wx, wy, ww, wh), (px, py, pw, ph) = box["w"], box["p"]
    points = [(wx + ww * fx, wy + wh * fy) for fx in (0.15, 0.3, 0.45, 0.6, 0.75, 0.9) for fy in (0.1, 0.25, 0.4, 0.6, 0.8, 0.92)]
    points = [(x, y) for x, y in points if not (px <= x <= px + pw and py <= y <= py + ph)]  # only what the panel leaves showing
    points = [(x, y) for x, y in points if 0 <= x < im.width and 0 <= y < im.height]
    return sum(im.getpixel((int(x), int(y))) == (234, 241, 246) for x, y in points) / max(1, len(points))


def run(browser, url: str, name: str, **ctx_args) -> list[str]:
    problems: list[str] = []
    ctx = browser.new_context(**ctx_args)
    page = ctx.new_page()
    page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
    page.on("console", lambda m: problems.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_function("window.pollenMap && window.pollenMap.isStyleLoaded()", timeout=60000)
    try:
        page.wait_for_function("window.pollenMap.loaded()", timeout=30000)
    except PlaywrightTimeout:
        problems.append("map tiles were still loading after 30 s")
    page.wait_for_timeout(1500)

    info = page.evaluate("""() => {
      const m = window.pollenMap;
      return {layers: ['surface','range-line','c-day','c-five','c-index','c-labels','stations'].filter(id => m.getLayer(id)),
              stations: m.queryRenderedFeatures({layers: ['stations']}).length,
              summary: document.querySelector('.map-summary').innerText,
              zoom: m.getZoom().toFixed(2)};
    }""")
    print(f"[{name}] layers: {info['layers']}\n[{name}] dots on screen: {info['stations']}, zoom {info['zoom']}\n[{name}] summary: {info['summary']}")
    if "surface" not in info["layers"] or info["stations"] == 0:
        problems.append("map is missing its raster or its stations")

    page.locator("#map-block").scroll_into_view_if_needed()
    page.locator("#map-block").screenshot(path=OUT / f"{name}-map.png")
    # the fixed header covers the top of the page, so bring the map to the middle of the screen before pointing at a dot
    page.evaluate("document.querySelector('.map-wrap').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(500)
    s = station_pixel(page)
    if ctx_args.get("has_touch"):
        page.touchscreen.tap(s["x"], s["y"])
    else:
        page.mouse.move(s["x"], s["y"])
        page.wait_for_selector(".maplibregl-popup", timeout=5000)
        page.wait_for_timeout(600)
        page.locator("#map-block").screenshot(path=OUT / f"{name}-hover.png")
        page.mouse.click(s["x"], s["y"])
    page.wait_for_selector("#panel.open", timeout=5000)
    page.wait_for_timeout(1500)
    print(f"[{name}] opened the panel for station {s['id']}: {page.locator('#panel .headline').inner_text()}")
    # Regression guard: with the panel open, the map behind/above it must still be drawn (it once went blank).
    if (share := blank_map_share(page)) > 0.5:
        problems.append(f"the map goes blank while the detail panel is open ({share:.0%} of it)")
    page.locator("#map-block").screenshot(path=OUT / f"{name}-panel.png")
    page.keyboard.press("Escape")
    if not ctx_args.get("has_touch"):
        page.screenshot(path=OUT / f"{name}-fullpage.png", full_page=True)
    ctx.close()
    return problems


def check_methodology(browser, url: str) -> list[str]:
    """The collapsed methodology section on the front page: closed at first, opens, its images draw, and a link into it opens it."""
    problems: list[str] = []
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url, wait_until="networkidle")
    box = page.locator("details.method")
    if box.count() != 1 or box.evaluate("e => e.open"):
        problems.append("the methodology section is missing, or is open before anyone asked for it")
    page.locator("details.method > summary").click()
    page.evaluate("document.querySelectorAll('details.method img').forEach(i => i.loading = 'eager')")
    page.wait_for_timeout(1500)
    broken = page.evaluate("[...document.querySelectorAll('details.method img')].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.src)")
    n = page.evaluate("document.querySelectorAll('details.method img').length")
    print(f"[methodology] {n} images, {len(broken)} broken, {len(errors)} script errors")
    if broken or n < 4:
        problems.append(f"methodology images did not load: {broken} ({n} found)")
    if errors:
        problems.append(f"methodology script errors: {errors}")
    page.locator("details.method > summary").click()   # close it again, then follow a link into it
    page.goto(url + "#from-temperatures-to-heat", wait_until="networkidle")
    if not page.locator("details.method").evaluate("e => e.open"):
        problems.append("a link into the methodology did not open it")
    page.close()
    return problems


def check_gallery(browser, url: str) -> list[str]:
    """The carousel on the front page, and a finished season on the gallery page."""
    problems: list[str] = []
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(url, wait_until="networkidle")
    page.wait_for_selector(".past-card", timeout=15000)
    cards = page.locator(".past-card")
    n = cards.count()
    page.evaluate("document.querySelectorAll('.past-card img').forEach(i => i.loading = 'eager')")
    page.wait_for_timeout(1500)
    broken = page.evaluate("[...document.querySelectorAll('.past-card img')].filter(i => !i.complete || i.naturalWidth === 0).map(i => i.src)")
    href = cards.first.get_attribute("href")
    print(f"[carousel] {n} seasons, {len(broken)} thumbnails broken, first links to {href}")
    if n < 20 or broken or not (href or "").startswith("gallery.html#"):
        problems.append(f"carousel problem: {n} cards, broken thumbnails {broken}, first link {href}")

    year = href.split("#")[1] if href else "2015"
    page.goto(url + f"gallery.html#{year}", wait_until="networkidle")
    page.wait_for_function("window.pollenMap && window.pollenMap.getLayer('stations')", timeout=20000)
    page.wait_for_timeout(1500)
    title = page.locator(".map-title .yr").inner_text()
    dots = page.evaluate("window.pollenMap.queryRenderedFeatures({layers: ['stations']}).length")
    chips = page.locator(".yr-nav .chip").count()
    bars = page.locator("svg.trend rect").count()
    print(f"[gallery] {title!r}, {dots} dots, {chips} year chips, {bars} chart marks")
    if title != f"{year} season" or dots == 0 or chips < 20 or bars < 20:
        problems.append(f"gallery page problem: title {title!r}, dots {dots}, chips {chips}, chart marks {bars}")
    if errors:
        problems.append(f"gallery script errors: {errors}")
    page.screenshot(path=OUT / "gallery-desktop.png")
    page.close()
    return problems


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if not (SITE / "index.html").exists() or not (SITE / "data" / "latest.json").exists():
        print("build the page and the data first (see the docstring)")
        return 1
    server, url = serve()
    problems: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        problems += run(browser, url, "desktop", viewport={"width": 1280, "height": 900})
        problems += run(browser, url, "mobile", viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                        device_scale_factor=2)
        problems += check_methodology(browser, url)
        problems += check_gallery(browser, url)
        browser.close()
    server.shutdown()
    print(f"\nscreenshots in {OUT}")
    for line in problems:
        print("PROBLEM:", line)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
