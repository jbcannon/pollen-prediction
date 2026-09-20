/* gallery.html: pick a finished season with #YYYY, draw it on the map (map.js reads window.POLLEN_SRC after
   window.POLLEN_READY resolves), and show the year picker and the year-by-year chart.
   Reads seasons/index.json (see scripts/build_gallery.py). */
(() => {
  "use strict";
  const $ = (sel) => document.querySelector(sel);
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May"];
  const fmt = (iso) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  const yday = (iso) => Math.round((Date.parse(iso + "T00:00:00Z") - Date.UTC(+iso.slice(0, 4), 0, 0)) / 864e5);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function buildNav(idx, year) {
    const el = $("#year-nav");
    if (!el) return;
    const years = idx.seasons.map((s) => s.year);
    const i = years.indexOf(year);
    const chip = (y) => `<a class="chip${y === year ? " on" : ""}" href="#${y}"${y === year ? ' aria-current="true"' : ""}>${y}</a>`;
    el.innerHTML =
      `<div class="yr-nav"><a class="step${i >= years.length - 1 ? " off" : ""}" href="#${years[Math.min(i + 1, years.length - 1)]}" aria-label="Earlier season">&larr; ${years[i + 1] || ""}</a>` +
      `<div class="chips" role="navigation" aria-label="Choose a season">${years.slice().reverse().map(chip).join("")}</div>` +
      `<a class="step${i <= 0 ? " off" : ""}" href="#${years[Math.max(i - 1, 0)]}" aria-label="Later season">${years[i - 1] || ""} &rarr;</a></div>`;
    const on = el.querySelector(".chip.on");
    if (on) el.querySelector(".chips").scrollLeft = on.offsetLeft - el.querySelector(".chips").clientWidth / 2;
  }

  function buildTrend(idx, year) {
    const el = $("#trend");
    if (!el) return;
    const rows = idx.seasons.filter((s) => s.first && s.last).slice().sort((a, b) => a.year - b.year);
    if (!rows.length) return;
    const w = 940, h = 300, m = { l: 62, r: 14, t: 16, b: 34 };
    const lo = Math.floor(Math.min(...rows.map((s) => yday(s.first))) / 10) * 10 - 5, hi = Math.ceil(Math.max(...rows.map((s) => yday(s.last))) / 10) * 10 + 5;
    const X = (yr) => m.l + ((yr - rows[0].year + 0.5) / rows.length) * (w - m.l - m.r);
    const Y = (d) => m.t + ((d - lo) / (hi - lo)) * (h - m.t - m.b);   // earlier dates at the top
    const parts = [];
    for (let mo = 1; mo < 5; mo++) {   // month gridlines
      const d = Math.round((Date.UTC(2001, mo, 1) - Date.UTC(2001, 0, 0)) / 864e5);
      if (d > lo && d < hi) parts.push(`<line x1="${m.l}" x2="${w - m.r}" y1="${Y(d)}" y2="${Y(d)}" stroke="#e1e0d9"/><text x="${m.l - 8}" y="${Y(d) + 4}" text-anchor="end" font-size="12" fill="#6b6b66">${MONTHS[mo]} 1</text>`);
    }
    const bw = Math.min(16, (w - m.l - m.r) / rows.length - 6);
    for (const s of rows) {
      const cur = s.year === year, x = X(s.year), y1 = Y(yday(s.first)), y2 = Y(yday(s.last)), ym = Y(yday(s.median));
      const tip = `${s.year}: peak from ${fmt(s.first)} to ${fmt(s.last)}, middle ${fmt(s.median)}`;
      parts.push(`<a href="#${s.year}" aria-label="${esc(tip)}"><title>${esc(tip)}</title>` +
        `<rect x="${x - bw / 2}" y="${y1}" width="${bw}" height="${Math.max(3, y2 - y1)}" rx="3" fill="${cur ? "#e8a317" : "#93c470"}" fill-opacity="${cur ? 0.95 : 0.7}"/>` +
        `<circle cx="${x}" cy="${ym}" r="${cur ? 4.5 : 3}" fill="${cur ? "#0b0b0b" : "#3d7a26"}"/>` +
        `<rect x="${x - (w - m.l - m.r) / rows.length / 2}" y="${m.t}" width="${(w - m.l - m.r) / rows.length}" height="${h - m.t - m.b}" fill="transparent"/></a>`);
      if (s.year % 5 === 0 || cur) parts.push(`<text x="${x}" y="${h - 12}" text-anchor="middle" font-size="12" fill="${cur ? "#0b0b0b" : "#6b6b66"}" font-weight="${cur ? 700 : 400}">${s.year}</text>`);
    }
    const byMedian = rows.slice().sort((a, b) => yday(a.median) - yday(b.median));
    const first = byMedian[0], last = byMedian[byMedian.length - 1];
    el.innerHTML = `<h2>Every season at a glance</h2>` +
      `<p class="trend-note">Each bar runs from the earliest to the latest peak across the longleaf range that year, and the dot is the middle station. Click a year to see its map. ` +
      `The earliest spring was <strong>${first.year}</strong> (middle peak ${fmt(first.median)}) and the latest was <strong>${last.year}</strong> (${fmt(last.median)}).</p>` +
      `<svg class="trend" viewBox="0 0 ${w} ${h}" role="img" aria-label="Peak dates across the longleaf range for each season since ${rows[0].year}">${parts.join("")}</svg>`;
  }

  window.POLLEN_READY = (async () => {
    const idx = await (await fetch("seasons/index.json", { cache: "no-cache" })).json();
    let year = parseInt(location.hash.slice(1), 10);
    if (!idx.seasons.some((s) => s.year === year)) {
      year = idx.seasons[0].year;
      history.replaceState(null, "", `#${year}`);
    }
    window.POLLEN_SRC = `seasons/${year}/`;
    buildNav(idx, year);
    buildTrend(idx, year);
    document.title = `${year} season - Past seasons - The Jones Center at Ichauway Research Labs`;
  })();
  window.addEventListener("hashchange", () => location.reload());   // a new year means new data: start the page over
})();
