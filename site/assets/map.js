/* Interactive map of predicted peak pollen dates for longleaf pine.
   Reads latest.json, series.json, surface.json and contours.geojson from data/ (today's forecast), or from the folder in
   window.POLLEN_SRC (gallery.html sets it to seasons/YYYY/ for a finished season)
   (format: docs/data-format.md). No build step; MapLibre GL JS comes from the page. */
(() => {
  "use strict";

  const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
  // early -> late: yellow, green, teal, blue, indigo, purple (lightness falls steadily)
  const RAMP = ["#f4e04d", "#b6d957", "#5fc16f", "#23a5a0", "#2a78d6", "#4b4ba8", "#3a1c63"];
  const RED = "#d62728", BLUE = "#1f77b4", GREEN = "#2ca02c", INK = "#0b0b0b", GOLD = "#e8a317";
  const DAY_MS = 864e5;
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May"];

  let SRC = "data/";   // gallery.html points this at a finished season (window.POLLEN_SRC, set once window.POLLEN_READY resolves)
  const $ = (sel) => document.querySelector(sel);
  const state = { latest: null, series: null, surface: null, contours: null, year: 0, lo: 0, hi: 1,
                  byId: {}, selected: null, map: null, popup: null, hoverId: null };

  // ---------- dates and colours ----------
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = (iso) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  // "Sep 20, 2026, 3:40 PM EDT": the moment the forecast was built, in Eastern time (the abbreviation follows daylight saving)
  const fmtStamp = (iso) => new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZone: "America/New_York", timeZoneName: "short" });
  const fmtLong = (iso) => new Date(iso.slice(0, 10) + "T00:00:00Z").toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric", timeZone: "UTC" });
  const ydayOf = (iso) => Math.round((Date.parse(iso.slice(0, 10) + "T00:00:00Z") - Date.UTC(+iso.slice(0, 4), 0, 0)) / DAY_MS);
  const isoOfYday = (year, yday) => new Date(Date.UTC(year, 0, yday)).toISOString().slice(0, 10);
  const hexToRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const RAMP_RGB = RAMP.map(hexToRgb);
  function colorAt(t) {
    t = Math.min(1, Math.max(0, t));
    const x = t * (RAMP.length - 1), i = Math.min(RAMP.length - 2, Math.floor(x)), f = x - i;
    return RAMP_RGB[i].map((v, k) => Math.round(v + (RAMP_RGB[i + 1][k] - v) * f));
  }
  const tOf = (yday) => (yday - state.lo) / (state.hi - state.lo);

  // ---------- wording ----------
  // Airport names in the source data are mostly in capitals ("PUNTA GORDA", "WARNER ROBINS AFB"). Names already in mixed case are left alone.
  const KEEP_UPPER = new Set(["AFB", "NAS", "NAF", "AAF", "AFS", "ANG", "ANGB", "MCAS", "MCALF", "NALF", "NOLF", "NASA", "USAF", "AWOS", "ASOS", "II", "III", "IV"]);
  function niceName(name) {
    if (!name || /[a-z]/.test(name)) return name;
    return name.replace(/[A-Z0-9][A-Z0-9']*/g, (w) => {
      if (KEEP_UPPER.has(w) || w.length === 1) return w;
      if (/^MC[A-Z]{3,}/.test(w)) return "Mc" + w[2] + w.slice(3).toLowerCase();
      return w[0] + w.slice(1).toLowerCase().replace(/'([a-z])/g, (_, c) => "'" + c.toUpperCase());
    });
  }
  function rangeText(rec) {
    const a = rec.forecast_earliest ? fmtDate(rec.forecast_earliest) : "?";
    const b = rec.forecast_latest ? fmtDate(rec.forecast_latest) : "after 31 May";
    return a === b ? a : `${a}–${b}`;
  }
  function headline(rec) {
    if (rec.status === "crossed") return `${state.latest.mode === "archive" ? "Peaked" : "Passed its peak"} on ${fmtDate(rec.crossing_date)}`;
    if (rec.status === "forecast") return `Peak expected ${rangeText(rec)}`;
    return "No forecast yet (not enough recent data)";
  }

  // ---------- charts (plain SVG) ----------
  function chartSVG(rec, s, big) {
    const narrow = window.matchMedia("(max-width: 760px)").matches;
    const w = big ? 350 : 224, h = big ? (narrow ? 165 : 200) : 72;
    const m = big ? { l: 44, r: 10, t: 12, b: 24 } : { l: 3, r: 3, t: 3, b: 3 };
    const { boyer_b0: B0, boyer_b1: B1 } = state.latest.method;
    const band = s && s.band;
    const bandStart = band ? ydayOf(band.start) : 0;
    const bandEnd = band ? bandStart + band.mid.length - 1 : 0;
    const xMax = Math.max(120, bandEnd), yMax = 19500;
    const X = (d) => m.l + ((d - 1) / (xMax - 1)) * (w - m.l - m.r);
    const Y = (v) => m.t + (1 - v / yMax) * (h - m.t - m.b);
    const pt = (d, v) => `${X(d).toFixed(1)},${Y(v).toFixed(1)}`;
    const parts = [];
    if (big) {
      for (const v of [0, 5000, 10000, 15000]) {
        parts.push(`<line x1="${m.l}" x2="${w - m.r}" y1="${Y(v)}" y2="${Y(v)}" stroke="#e6e5de" stroke-width="1"/>`,
                   `<text x="${m.l - 6}" y="${Y(v) + 4}" text-anchor="end" font-size="10.5" fill="#6b6b66">${v.toLocaleString("en-US")}</text>`);
      }
      MONTHS.forEach((name, i) => {
        const d = ydayOf(`${state.year}-0${i + 1}-01`);
        if (d < xMax) parts.push(`<line x1="${X(d)}" x2="${X(d)}" y1="${m.t}" y2="${h - m.b}" stroke="#eeeee8"/>`,
                                 `<text x="${X(d) + 3}" y="${h - 8}" font-size="10.5" fill="#6b6b66">${name}</text>`);
      });
      parts.push(`<text x="${m.l}" y="9" font-size="10.5" fill="#6b6b66">degree-hours of heat</text>`);
    }
    // the Boyer threshold
    const boyer = [];
    for (let d = 1; d <= xMax; d += 3) boyer.push(pt(d, B0 + B1 * d));
    parts.push(`<polyline fill="none" stroke="${BLUE}" stroke-width="${big ? 2 : 1.5}" points="${boyer.join(" ")}"/>`);
    // the forecast band and its middle path
    if (band) {
      const top = band.hi.map((v, i) => pt(bandStart + i, v));
      const bottom = band.lo.map((v, i) => pt(bandStart + i, v)).reverse();
      parts.push(`<polygon fill="${GREEN}" fill-opacity="0.28" points="${top.concat(bottom).join(" ")}"/>`,
                 `<polyline fill="none" stroke="${GREEN}" stroke-width="1.3" stroke-dasharray="4 3" points="${band.mid.map((v, i) => pt(bandStart + i, v)).join(" ")}"/>`);
    }
    // heat accumulated so far (joined to the band's first day)
    if (s && s.cum.length) {
      const pts = s.cum.map((v, i) => pt(i + 1, v));
      if (band) pts.push(pt(bandStart, band.mid[0]));
      parts.push(`<polyline fill="none" stroke="${RED}" stroke-width="${big ? 2.4 : 1.8}" stroke-linejoin="round" points="${pts.join(" ")}"/>`);
    }
    // the date itself: a band across the predicted range (behind everything else), or a thin line once crossed
    if (rec.status === "crossed") {
      const d = ydayOf(rec.crossing_date);
      parts.push(`<line x1="${X(d)}" x2="${X(d)}" y1="${m.t}" y2="${h - m.b}" stroke="${INK}" stroke-width="1.2" stroke-dasharray="2 3" opacity="0.7"/>`);
    } else if (rec.status === "forecast" && (rec.forecast_earliest || rec.forecast_median)) {
      const d0 = ydayOf(rec.forecast_earliest || rec.forecast_median);
      const d1 = rec.forecast_latest ? ydayOf(rec.forecast_latest) : xMax;   // open-ended: runs to the edge of the chart
      const x0 = X(d0 - 0.5), x1 = Math.max(X(d1 + 0.5), x0 + 3);
      parts.unshift(`<rect x="${x0.toFixed(1)}" y="${m.t}" width="${(x1 - x0).toFixed(1)}" height="${h - m.t - m.b}" fill="${GOLD}" fill-opacity="0.3"/>`);
    }
    const label = `Chart of accumulated heat against the Boyer threshold for ${niceName(rec.name)}: ${headline(rec)}`;
    return `<svg class="chart" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${esc(label)}">${parts.join("")}</svg>`;
  }

  // ---------- hover popup and detail panel ----------
  function popupHTML(rec) {
    const s = state.series && state.series.stations[rec.id];
    const chart = s ? chartSVG(rec, s, false) : '<div class="pp-note">loading chart…</div>';
    return `<div class="pp"><strong>${esc(niceName(rec.name))}</strong>, ${esc(rec.state)}<div class="pp-line">${esc(headline(rec))}</div>${chart}<div class="pp-note">Click for details</div></div>`;
  }
  function panelHTML(rec) {
    const L = state.latest, s = state.series && state.series.stations[rec.id];
    const facts = [];
    if (L.mode !== "archive" && rec.data_through && rec.cum_heat != null) facts.push(`Heat so far: ${rec.cum_heat.toLocaleString("en-US")} of ${rec.required_heat.toLocaleString("en-US")} degree-hours needed on ${fmtDate(rec.data_through)}.`);
    if (rec.days_behind > 0) facts.push(`Latest reading is ${rec.days_behind} day${rec.days_behind > 1 ? "s" : ""} old.`);
    if (rec.n_seasons) facts.push(`Based on ${rec.n_seasons} springs of records at this airport (${rec.elevation_m != null ? rec.elevation_m + " m elevation" : "elevation unknown"}).`);
    let detail = "";
    if (rec.status === "crossed") {
      detail = `Accumulated heat reached the Boyer threshold on ${fmtLong(rec.crossing_date)}. ${state.latest.mode === "archive" ? "Pollen shedding peaked around then." : "Pollen shedding is expected to peak around then."}`;
    } else if (rec.status === "forecast") {
      detail = L.mode === "outlook"
        ? `Most likely ${fmtDate(rec.forecast_median)}. No weather from ${L.season} has been recorded yet, so this outlook rests only on the last ten springs (${L.method.analog_years}). The yellow band is the predicted range, and it narrows once the heat starts to add up in January. The green band is the middle half of ${rec.n_scenarios} scenarios, one per recent spring.`
        : `Most likely ${fmtDate(rec.forecast_median)}. The yellow band is the predicted range. The green band is the middle half of ${rec.n_scenarios} scenarios: each replays the weather from one of the recent springs (${L.method.analog_years}) on top of this year so far.`;
      if (rec.n_not_crossed) detail += ` In ${rec.n_not_crossed} of them the threshold is not reached by 31 May.`;
    } else {
      detail = "This station has too few recent readings to forecast right now.";
    }
    const chart = s ? chartSVG(rec, s, true) : "";
    const key = s ? `<div class="chart-key">${s.cum.length ? `<span><i style="background:${RED}"></i>heat so far</span>` : ""}<span><i style="background:${BLUE}"></i>Boyer threshold</span>${s.band ? '<span><i class="band"></i>range of scenarios</span>' : ""}${rec.status === "forecast" ? '<span><i class="pk"></i>predicted peak range</span>' : ""}</div>` : "";
    // The scrolling lives in an inner wrapper: a scrollable panel laid directly over the map made some
    // browsers drop the map behind it on small screens.
    return `<button class="close" aria-label="Close">&times;</button><div class="panel-body"><h3>${esc(niceName(rec.name))}, ${esc(rec.state)}</h3>` +
      `<p class="sub">${rec.in_range ? "Inside" : "Near"} the longleaf pine range · ${L.mode === "outlook" ? `${L.season} outlook` : L.mode === "archive" ? `${L.season} final results` : `as of ${fmtDate(L.as_of)}`}</p>` +
      `<p class="headline">${esc(headline(rec))}</p><p class="detail">${esc(detail).replace(/\n/g, "<br>")}</p>${chart}${key}<p class="facts">${facts.map(esc).join(" ")}</p></div>`;
  }
  function openPanel(id) {
    const rec = state.byId[id];
    if (!rec) return;
    state.selected = id;
    const panel = $("#panel");
    panel.innerHTML = panelHTML(rec);
    panel.classList.add("open");
    panel.querySelector(".close").addEventListener("click", closePanel);
    state.map.setFilter("stations-selected", ["==", ["get", "id"], id]);
    const narrow = window.matchMedia("(max-width: 760px)").matches;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    // Put the station in the part of the map the panel leaves visible: the top of the map on a phone
    // (where the panel is a bottom sheet), the left of the map on a wide screen.
    state.map.easeTo({ center: [rec.lon, rec.lat], duration: reduce ? 0 : 450,
                       zoom: narrow ? Math.max(state.map.getZoom(), 5) : state.map.getZoom(),
                       offset: narrow ? [0, -Math.round($(".map-wrap").clientHeight * 0.3)] : [-Math.round(Math.min(390, $(".map-wrap").clientWidth) / 2), 0] });
  }
  function closePanel() {
    state.selected = null;
    $("#panel").classList.remove("open");
    state.map.setFilter("stations-selected", ["==", ["get", "id"], ""]);
  }

  // ---------- the colour raster (clipped to the range by the data itself) ----------
  function buildRaster(surf) {
    const g = surf.grid, vals = surf.values, nLon = g.n_lon, nLat = g.n_lat, step = g.step;
    const west = g.lon0 - step / 2, east = g.lon0 + (nLon - 0.5) * step;
    const north = g.lat0 + step / 2, south = g.lat0 - (nLat - 0.5) * step;
    const merc = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
    const unmerc = (y) => ((2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180) / Math.PI;
    const W = nLon * 2, H = Math.round((W * (merc(north) - merc(south))) / (((east - west) * Math.PI) / 180));
    const cv = document.createElement("canvas");
    cv.width = W; cv.height = H;
    const ctx = cv.getContext("2d"), img = ctx.createImageData(W, H);
    const at = (r, c) => (r < 0 || c < 0 || r >= nLat || c >= nLon ? null : vals[r * nLon + c]);
    const yN = merc(north), yS = merc(south);
    for (let j = 0; j < H; j++) {
      const fr = (g.lat0 - unmerc(yN - ((j + 0.5) / H) * (yN - yS))) / step;
      for (let i = 0; i < W; i++) {
        const fc = (west + ((i + 0.5) / W) * (east - west) - g.lon0) / step;
        const nearest = at(Math.round(fr), Math.round(fc));
        if (nearest === null) continue;                    // outside the range: stays transparent
        const r0 = Math.floor(fr), c0 = Math.floor(fc), dr = fr - r0, dc = fc - c0;
        let sw = 0, sv = 0;
        for (const [rr, cc, wgt] of [[r0, c0, (1 - dr) * (1 - dc)], [r0, c0 + 1, (1 - dr) * dc], [r0 + 1, c0, dr * (1 - dc)], [r0 + 1, c0 + 1, dr * dc]]) {
          const v = at(rr, cc);
          if (v !== null && wgt > 0) { sw += wgt; sv += wgt * v; }
        }
        const [R, G, B] = colorAt(tOf(sw > 0 ? sv / sw : nearest)), k = (j * W + i) * 4;
        img.data[k] = R; img.data[k + 1] = G; img.data[k + 2] = B; img.data[k + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
    return { url: cv.toDataURL("image/png"), coordinates: [[west, north], [east, north], [east, south], [west, south]] };
  }

  // ---------- page pieces ----------
  function rangeStations() { return state.latest.stations.filter((s) => s.in_range); }
  function renderSummary() {
    const L = state.latest, inr = rangeStations();
    const crossed = inr.filter((s) => s.status === "crossed").length;
    const dated = inr.filter((s) => s.peak_date).map((s) => s.peak_date).sort();
    const fc = inr.filter((s) => s.status === "forecast" && s.forecast_median).map((s) => s.forecast_median).sort();
    const seasonOver = L.as_of.slice(5) === "05-31";
    let html;
    if (!dated.length) html = "No forecasts are available right now.";
    else if (L.mode === "archive") html = `In <strong>${L.season}</strong>, across the longleaf pine range, peak shedding came between <strong>${fmtDate(dated[0])}</strong> and <strong>${fmtDate(dated[dated.length - 1])}</strong>, from the ${dated.length} weather stations in the range that reported that spring.`;
    else if (L.mode === "outlook") html = `Across the longleaf pine range, the peak is expected to arrive between <strong>${fmtDate(dated[0])}</strong> and <strong>${fmtDate(dated[dated.length - 1])}</strong>.`;
    else if (seasonOver && crossed === inr.length) html = `The <strong>${L.season}</strong> season is complete. Across the longleaf pine range, peak shedding came between <strong>${fmtDate(dated[0])}</strong> and <strong>${fmtDate(dated[dated.length - 1])}</strong>.`;
    else if (fc.length) html = `As of <strong>${fmtDate(L.as_of)}</strong>, <strong>${crossed} of ${inr.length}</strong> weather stations in the longleaf pine range have passed their peak. The rest are forecast between <strong>${fmtDate(fc[0])}</strong> and <strong>${fmtDate(fc[fc.length - 1])}</strong>.`;
    else html = `As of <strong>${fmtDate(L.as_of)}</strong>, all ${inr.length} weather stations in the longleaf pine range have passed their peak.`;
    if (dated.length > 1) {   // how far the peak travels across the range, from the earliest to the latest station
      const first = inr.find((s) => s.peak_date === dated[0]), last = inr.find((s) => s.peak_date === dated[dated.length - 1]);
      const weeks = Math.round((Date.parse(dated[dated.length - 1]) - Date.parse(dated[0])) / (7 * DAY_MS));
      if (weeks >= 2) html += ` The peak pollen season sweeps across the range over about <strong>${weeks} weeks</strong>, from ${esc(niceName(first.name))}, ${esc(first.state)} to ${esc(niceName(last.name))}, ${esc(last.state)}.`;
    }
    $(".map-summary").innerHTML = html;
    $(".map-updated .when").textContent = fmtStamp(L.generated_at);
    // the label that says which season this is and what kind of forecast it is
    const kind = { live: ["Live, updated every morning", "live"], outlook: ["Preseason outlook", "outlook"], replay: ["Test data", "replay"], archive: ["Final results", "archive"] }[L.mode] || ["", ""];
    $(".map-title .yr").textContent = L.mode === "archive" ? `${L.season} season` : `${L.season} forecast`;
    const pill = $(".map-title .kind");
    pill.textContent = kind[0];
    pill.className = `kind ${kind[1]}`;
    const b = $(".map-banner");
    if (L.mode === "replay") {
      b.textContent = `Test data: this is a replay of the ${L.season} season as it looked on ${fmtLong(L.as_of)}, not today's forecast.`;
      b.style.display = "block";
    } else if (L.mode === "archive") {
      $(".map-updated").style.display = "none";
      const help = $(".map-help");
      if (help) help.textContent = "Colors show the day peak pollen shedding came at each station, inside the longleaf pine range. Hover over a dot for a chart; click it for details. Click anywhere else in the range to read the date there.";
      for (const id of ["#key-crossed", "#key-forecast"]) { const k = $(id); if (k) k.style.display = "none"; }
    } else if (L.mode === "outlook") {
      b.innerHTML = `<strong>Preseason outlook, not yet a live forecast.</strong><br>No ${L.season} weather has been recorded yet, so these dates come only from the last ten springs and are typically off by about a week. They sharpen once daily updates begin in January.`;
      b.style.display = "block";
      const done = $("#key-crossed");
      if (done) done.style.display = "none";   // nothing has passed its peak yet
    }
  }
  function renderLegend() {
    $("#legend-bar").style.background = `linear-gradient(to right, ${RAMP.join(",")})`;
    const ticks = [];
    for (let i = 0; i < 6; i++) ticks.push(`<span>${fmtDate(isoOfYday(state.year, Math.round(state.lo + ((state.hi - state.lo) * i) / 5)))}</span>`);
    $("#legend-ticks").innerHTML = ticks.join("");
  }
  const showMessage = (text) => { const m = $(".map-msg"); m.textContent = text; m.hidden = false; };

  // ---------- the map ----------
  function stationsGeoJSON() {
    return { type: "FeatureCollection", features: rangeStations().filter((s) => s.peak_date).map((s) => ({
      type: "Feature", geometry: { type: "Point", coordinates: [s.lon, s.lat] },
      properties: { id: s.id, status: s.status, yday: ydayOf(s.peak_date) } })) };
  }
  function initMap() {
    const map = new maplibregl.Map({
      container: "map", style: STYLE_URL, minZoom: 3.5, maxZoom: 11, attributionControl: false,
      bounds: [[-95.6, 26.2], [-75.3, 37.3]], fitBoundsOptions: { padding: 6 },
      cooperativeGestures: window.matchMedia("(pointer: coarse)").matches,   // don't trap page scrolling on phones
    });
    state.map = map;
    window.pollenMap = map;   // handy for testing in the browser console
    window.pollenState = state;
    state.helpers = { fmtDate, isoOfYday, headline, niceName };   // used by locate.js
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    const attribution = new maplibregl.AttributionControl({ compact: true,
      customAttribution: 'Temperatures: <a href="https://mesonet.agron.iastate.edu/" target="_blank" rel="noopener">Iowa Environmental Mesonet</a> · range map: E. L. Little Jr.' });
    map.addControl(attribution);
    // The credits stay one click away behind the (i) button instead of open over the map on first load.
    const collapseCredits = () => {
      const el = map.getContainer().querySelector(".maplibregl-ctrl-attrib");
      if (el) { el.classList.remove("maplibregl-compact-show"); el.removeAttribute("open"); }
    };
    collapseCredits(); map.once("load", collapseCredits); map.once("idle", collapseCredits);
    map.on("error", (e) => console.warn("map error", e && e.error && e.error.message));
    map.once("load", () => {
      const before = (map.getStyle().layers.find((l) => l.type === "symbol") || {}).id;   // keep place names above our layers
      const abs = (p) => new URL(p, location.href).href;
      if (state.surface) {
        const r = buildRaster(state.surface);
        map.addSource("surface", { type: "image", url: r.url, coordinates: r.coordinates });
        map.addLayer({ id: "surface", type: "raster", source: "surface", paint: { "raster-opacity": 0.9, "raster-resampling": "linear", "raster-fade-duration": 0 } }, before);
      }
      map.addSource("range", { type: "geojson", data: abs("assets/range.geojson") });
      map.addLayer({ id: "range-line", type: "line", source: "range", paint: { "line-color": "#1f5d1f", "line-width": 1.6 } }, before);
      if (state.contours) {
        map.addSource("contours", { type: "geojson", data: state.contours });
        const tier = (t) => ["==", ["get", "tier"], t];
        map.addLayer({ id: "c-day", type: "line", source: "contours", filter: tier("day"), minzoom: 5.4, paint: { "line-color": INK, "line-width": 0.5, "line-opacity": 0.28 } }, before);
        map.addLayer({ id: "c-five", type: "line", source: "contours", filter: tier("five"), paint: { "line-color": INK, "line-width": 0.8, "line-opacity": 0.55 } }, before);
        map.addLayer({ id: "c-index", type: "line", source: "contours", filter: tier("index"), paint: { "line-color": INK, "line-width": 1.7, "line-opacity": 0.85 } }, before);
        map.addLayer({ id: "c-labels", type: "symbol", source: "contours", filter: tier("index"),
          layout: { "symbol-placement": "line", "text-field": ["get", "label"], "text-font": ["Noto Sans Bold"], "text-size": 12, "symbol-spacing": 380, "text-max-angle": 35 },
          paint: { "text-color": INK, "text-halo-color": "#ffffff", "text-halo-width": 2 } });
      }
      const stops = [];
      RAMP.forEach((c, i) => stops.push(state.lo + ((state.hi - state.lo) * i) / (RAMP.length - 1), c));
      map.addSource("stations", { type: "geojson", data: stationsGeoJSON() });
      map.addLayer({ id: "stations", type: "circle", source: "stations", paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 3.5, 2.6, 5, 4.2, 7, 6, 10, 9],
        "circle-color": ["interpolate", ["linear"], ["get", "yday"], ...stops],
        "circle-stroke-width": 1.6, "circle-stroke-color": ["case", ["==", ["get", "status"], "crossed"], INK, "#ffffff"] } });
      map.addLayer({ id: "stations-selected", type: "circle", source: "stations", filter: ["==", ["get", "id"], ""], paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 4, 7, 7, 10, 10, 14], "circle-color": "rgba(0,0,0,0)", "circle-stroke-width": 3, "circle-stroke-color": INK } });

      state.popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, maxWidth: "260px" });
      map.on("mousemove", "stations", (e) => {
        const id = e.features[0].properties.id;
        map.getCanvas().style.cursor = "pointer";
        if (state.hoverId === id) return;
        state.hoverId = id;
        state.popup.setLngLat(e.features[0].geometry.coordinates).setHTML(popupHTML(state.byId[id])).addTo(map);
      });
      map.on("mouseleave", "stations", () => { state.hoverId = null; state.popup.remove(); map.getCanvas().style.cursor = ""; });
      map.on("click", "stations", (e) => openPanel(e.features[0].properties.id));
      document.addEventListener("keydown", (e) => { if (e.key === "Escape" && state.selected) closePanel(); });
    });
  }

  // ---------- start ----------
  const getJSON = async (url, required) => {
    try {
      const r = await fetch(url, { cache: "no-cache" });
      if (!r.ok) throw new Error(`${url}: ${r.status}`);
      return await r.json();
    } catch (err) { if (required) throw err; console.warn(err); return null; }
  };
  async function main() {
    if (window.POLLEN_READY) { await window.POLLEN_READY.catch(() => {}); SRC = window.POLLEN_SRC || SRC; }
    try {
      state.latest = await getJSON(SRC + "latest.json", true);
    } catch (err) {
      console.error(err);
      showMessage("The forecast map could not be loaded right now. Please try again later.");
      return;
    }
    [state.surface, state.contours] = await Promise.all([getJSON(SRC + "surface.json"), getJSON(SRC + "contours.geojson")]);
    const L = state.latest;
    state.year = L.season;
    state.byId = Object.fromEntries(L.stations.map((s) => [s.id, s]));
    const days = rangeStations().filter((s) => s.peak_date).map((s) => ydayOf(s.peak_date));
    const range = state.surface ? state.surface.range : { min: Math.min(...days), max: Math.max(...days) };
    state.lo = Math.floor(range.min); state.hi = Math.max(state.lo + 1, Math.ceil(range.max));
    if (L.mode === "archive") {   // every finished season uses the same colors, so years can be compared
      const idx = await getJSON("seasons/index.json");
      if (idx && idx.scale) { state.lo = idx.scale.lo; state.hi = idx.scale.hi; }
    }
    renderSummary(); renderLegend();
    initMap();
    getJSON(SRC + "series.json").then((s) => {          // the charts can arrive after the first draw
      state.series = s;
      if (state.selected) openPanel(state.selected);
    });
  }
  main();
})();
