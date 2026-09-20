"""Build the site pages from the articles in content/ and the page template.

  content/boyer-article.md -> site/index.html    the article, with the interactive map at the top
  content/methodology.md   -> inside site/index.html, as a collapsed section (summary + "Read the full methodology")
  content/gallery.md       -> site/gallery.html  finished seasons, one at a time on the interactive map

Run this whenever an article or the template changes, and commit the result; the daily job only adds site/data/.

    uv run python scripts/build_site.py

Also copies the articles' images into site/img/ and a lighter copy of the longleaf pine range outline to
site/assets/range.geojson. To see the result while you edit, run scripts/dev.py: it serves the site (the
map needs a web server, not a double-click) and calls this for you on every save.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
# (source, output, has the map, description for search results and link previews, scripts before the map's, scripts after)
PAGES = [
    (ROOT / "content" / "boyer-article.md", SITE / "index.html", True,
     "A daily forecast of when longleaf pine pollen shedding will peak, mapped across the Southeast.",
     [], ["assets/carousel.js"]),
    (ROOT / "content" / "gallery.md", SITE / "gallery.html", True,
     "Every finished longleaf pine pollen season since 2001, one map per year, on the same color scale.",
     ["assets/gallery.js"], []),
]
RANGE_SRC = ROOT / "data" / "range" / "pinupalu.geojson"


def round_coords(node, digits: int = 3):
    """Round every coordinate in a GeoJSON geometry (about 100 m at 3 digits) to shrink the file."""
    if isinstance(node, list):
        return [round_coords(n, digits) for n in node] if node and isinstance(node[0], list) else [round(v, digits) for v in node]
    return node


def build_range() -> int:
    gj = json.loads(RANGE_SRC.read_text())
    for f in gj["features"]:
        f["geometry"]["coordinates"] = round_coords(f["geometry"]["coordinates"])
        f["properties"] = {}
    out = SITE / "assets" / "range.geojson"
    out.write_text(json.dumps(gj, separators=(",", ":")), encoding="utf-8")
    return out.stat().st_size


METHODOLOGY = ROOT / "content" / "methodology.md"


def methodology_html() -> str:
    """The methodology as it goes on the main page: a summary that is always shown, then a collapsed section with the rest."""
    text = METHODOLOGY.read_text(encoding="utf-8")
    summary_md, _, more_md = text.partition("<!-- MORE -->")
    summary = markdown.markdown(summary_md, extensions=["extra", "sane_lists"], output_format="html")
    more = markdown.markdown(more_md, extensions=["extra", "sane_lists", "toc"], output_format="html")
    more = re.sub(r"<(/?)h2\b", r"<\1h3", more)                       # the section headings sit one level down inside the article
    more = more.replace("<img ", '<img loading="lazy" ')
    return (summary + '<details class="method" id="methodology-full"><summary>'
            '<span class="when-closed">Read the full methodology</span><span class="when-open">Hide the methodology</span></summary>'
            f'<div class="method-body">{more}</div></details>')


FIGURE = re.compile(r'<p>(<img [^>]*>)</p>\s*<p><em>(Figure \d+\..*?)</em></p>', re.DOTALL)


def side_figures(body: str) -> str:
    """The article's photos and figures: the picture (a link to the full-size image) and its caption in one box that floats to the
    right of the text. Only the article's own figures get this; the methodology's charts stay full width. A figure that would end a
    section (nothing to wrap around) moves up ahead of the paragraph before it."""
    def wrap(m: re.Match) -> str:
        src = re.search(r'src="([^"]+)"', m.group(1)).group(1)
        return (f'<figure class="side"><a href="{src}" target="_blank" rel="noopener" title="Click to see it full size">{m.group(1)}</a>'
                f'<figcaption class="caption">{m.group(2)}</figcaption></figure>')

    body = FIGURE.sub(wrap, body)
    for m in reversed(list(re.finditer(r'<figure class="side">.*?</figure>\n?', body, re.DOTALL))):
        if body[m.end():].lstrip().startswith("<h2"):
            before = body.rfind("<p>", 0, m.start())
            if before != -1:
                body = body[:before] + m.group(0) + body[before:m.start()] + body[m.end():]
    return body


def article_html(source: Path, map_block: str | None) -> tuple[str, str]:
    """(title, body html): the article, with the map where the <!-- MAP --> marker is (map pages only), and no editor notes."""
    lines = source.read_text(encoding="utf-8").splitlines()
    title = lines[0].removeprefix("# ").strip()
    body_md = "\n".join(lines[1:])
    body_md = re.sub(r"<!--\s*MAP\s*-->", "@@MAP@@", body_md)
    body_md = re.sub(r"<!--\s*METHODOLOGY\s*-->", "@@METHODOLOGY@@", body_md)
    body = markdown.markdown(body_md, extensions=["extra", "sane_lists", "toc"], output_format="html")
    if map_block is not None:
        if "<p>@@MAP@@</p>" not in body:
            raise SystemExit(f"the <!-- MAP --> marker is missing from {source.name}")
        body = body.replace("<p>@@MAP@@</p>", map_block)
    body = side_figures(body)
    if "<p>@@METHODOLOGY@@</p>" in body:
        body = body.replace("<p>@@METHODOLOGY@@</p>", methodology_html())
    body = re.sub(r"<p><em>(Figure \d+\..*?)</em></p>", r'<p class="caption">\1</p>', body, flags=re.DOTALL)
    body = re.sub(r"<p>(Jeffery Cannon.*?Landscape Ecologist.*?)</p>", r'<p class="byline">\1</p>', body, count=1, flags=re.DOTALL)
    body = re.sub(r"<!--.*?-->", "", body, flags=re.DOTALL)  # editor notes never reach the public page
    return title, body


ANCHOR = re.compile(r'<a\s+([^>]*?href="https?://[^"]+"[^>]*)>')


def external_links(page: str) -> str:
    """Every link that leaves the site (the lab pages, DOIs, Flickr, ...) opens in a new tab."""
    def add(m: re.Match) -> str:
        attrs = m.group(1)
        if "target=" in attrs:
            return m.group(0)
        return f'<a {attrs} target="_blank" rel="noopener">'
    return ANCHOR.sub(add, page)


def script_tags(names: list[str]) -> str:
    return "".join(f'<script src="{name}"></script>\n' for name in names)


def build_page(source: Path, out: Path, has_map: bool, description: str, pre: list[str], post: list[str],
               template: str, map_block: str) -> int:
    title, body = article_html(source, map_block if has_map else None)
    page = (template.replace("{{TITLE}}", html.escape(title)).replace("{{ARTICLE}}", body)
                    .replace("{{DESCRIPTION}}", html.escape(description, quote=True))
                    .replace("{{YEAR}}", str(datetime.now(UTC).year))
                    .replace("{{PRE_MAP}}", script_tags(pre)).replace("{{POST_MAP}}", script_tags(post)))
    if has_map:  # keep the map's stylesheet and scripts
        page = page.replace("<!--MAP_ONLY-->", "").replace("<!--/MAP_ONLY-->", "")
    else:        # a page without the map does not load them
        page = re.sub(r"<!--MAP_ONLY-->.*?<!--/MAP_ONLY-->", "", page, flags=re.DOTALL)
    page = external_links(page)
    out.write_text(page, encoding="utf-8")
    (SITE / "img").mkdir(exist_ok=True)
    used = sorted(set(re.findall(r'src="img/([^"]+)"', body)))
    for name in used:
        shutil.copy2(ROOT / "content" / "img" / name, SITE / "img" / name)
    print(f"wrote site/{out.name} ({len(page) / 1000:,.0f} KB), {len(used)} images")
    return len(used)


def main():
    map_block = (SITE / "map-block.html").read_text(encoding="utf-8")
    template = (SITE / "template.html").read_text(encoding="utf-8")
    for source, out, has_map, description, pre, post in PAGES:
        build_page(source, out, has_map, description, pre, post, template, map_block)
    (SITE / ".nojekyll").write_text("", encoding="utf-8")
    print(f"range outline {build_range() / 1000:,.0f} KB")


if __name__ == "__main__":
    main()
