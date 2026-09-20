"""Live preview: serve the site, rebuild the page when you save, and reload the browser by itself.

    uv run python scripts/dev.py

Then edit content/boyer-article.md, content/methodology.md, site/template.html, site/map-block.html or anything in site/assets/,
save, and the browser refreshes within a second. Stop with Ctrl+C.

Why a server at all: browsers will not let a page opened by double-clicking (file://) read the data
files beside it, so the map needs to be served over http. This does that, and adds the auto-reload.

If site/data is empty it first builds today's data (about a minute). From June to December that is the next
season's preseason outlook; to see the live look, delete site/data and run with --today 2026-03-16.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
sys.path.insert(0, str(ROOT / "scripts"))
import build_site

REBUILD = [ROOT / "content" / "boyer-article.md", ROOT / "content" / "methodology.md", SITE / "template.html", SITE / "map-block.html"]
RELOAD_DIRS = [SITE / "assets", SITE / "data", SITE / "img"]
VERSION = [str(time.time())]  # changes whenever something the browser should reload changes

RELOAD_SNIPPET = (
    "<script>(()=>{let v=null;setInterval(async()=>{try{const t=await(await fetch('/__version',{cache:'no-store'})).text();"
    "if(v===null)v=t;else if(t!==v)location.reload();}catch(e){}},500);})();</script>"
)


def snapshot() -> dict[Path, float]:
    """Modification time of every file we watch."""
    files = list(REBUILD) + [SITE / "index.html"]
    for d in RELOAD_DIRS:
        if d.exists():
            files += [p for p in d.rglob("*") if p.is_file()]
    return {p: p.stat().st_mtime for p in files if p.exists()}


def watch():
    prev = snapshot()
    while True:
        time.sleep(0.4)
        cur = snapshot()
        if cur == prev:
            continue
        if any(cur.get(f) != prev.get(f) for f in REBUILD):
            try:
                build_site.main()
                print("rebuilt site/index.html")
            except (SystemExit, Exception) as exc:  # noqa: BLE001 - a typo in the article should not stop the preview
                print(f"could not rebuild: {exc}")
            cur = snapshot()  # the rebuild changed index.html itself
        VERSION[0] = str(time.time())
        prev = cur


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")  # always show the newest files
        super().end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/__version":
            body = VERSION[0].encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        local = Path(self.translate_path(path))
        if local.is_dir():
            local = local / "index.html"
        if local.suffix == ".html" and local.exists():
            html = local.read_text(encoding="utf-8").replace("</body>", RELOAD_SNIPPET + "</body>")
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()


def ensure_data(today: date | None):
    if (SITE / "data" / "latest.json").exists():
        return
    day = today or datetime.now(UTC).date()
    print(f"site/data is empty: building sample data as if today were {day} (about a minute)...")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "run_daily.py"), "--out", str(SITE / "data"), "--today", day.isoformat()],
                   check=True, cwd=ROOT)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-open", action="store_true", help="do not open a browser tab")
    p.add_argument("--today", type=date.fromisoformat, default=None, help="date to use if sample data has to be built")
    args = p.parse_args()

    ensure_data(args.today)
    build_site.main()
    server = None
    for port in range(args.port, args.port + 11):
        try:
            server = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Handler, directory=str(SITE)))
            break
        except OSError:
            continue
    if server is None:
        raise SystemExit(f"no free port between {args.port} and {args.port + 10}")
    server.daemon_threads = True
    url = f"http://localhost:{server.server_address[1]}/"
    threading.Thread(target=watch, daemon=True).start()
    print(f"\nLive preview at {url}\nEdit content/boyer-article.md or anything in site/, save, and the page updates. Ctrl+C to stop.")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
