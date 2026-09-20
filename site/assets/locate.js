/* "Find my location" and click-to-read for the pollen map. It sits on top of map.js: it uses the state
   map.js exposes (window.pollenMap, window.pollenState) and reads the same surface.json grid.
   The location is used in the browser only; nothing is sent anywhere. */
(() => {
  "use strict";

  const btn = document.getElementById("locate");
  if (!btn) return;

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const reduceMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let marker = null, popup = null, toastTimer = 0;

  // ---------- reading the map at a point ----------
  // Same grid maths as the raster in map.js: bilinear between the four nearest cells that have a value.
  function surfaceDay(lat, lon) {
    const S = window.pollenState.surface;
    if (!S) return null;
    const g = S.grid, fr = (g.lat0 - lat) / g.step, fc = (lon - g.lon0) / g.step;
    const at = (r, c) => (r < 0 || c < 0 || r >= g.n_lat || c >= g.n_lon ? null : S.values[r * g.n_lon + c]);
    if (at(Math.round(fr), Math.round(fc)) === null) return null;   // outside the longleaf pine range
    const r0 = Math.floor(fr), c0 = Math.floor(fc), dr = fr - r0, dc = fc - c0;
    let sw = 0, sv = 0;
    for (const [r, c, w] of [[r0, c0, (1 - dr) * (1 - dc)], [r0, c0 + 1, (1 - dr) * dc], [r0 + 1, c0, dr * (1 - dc)], [r0 + 1, c0 + 1, dr * dc]]) {
      const v = at(r, c);
      if (v !== null && w > 0) { sw += w; sv += w * v; }
    }
    return sw > 0 ? sv / sw : at(Math.round(fr), Math.round(fc));
  }

  function miles(lat1, lon1, lat2, lon2) {
    const rad = Math.PI / 180, dLat = (lat2 - lat1) * rad, dLon = (lon2 - lon1) * rad;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
    return 3958.8 * 2 * Math.asin(Math.sqrt(a));
  }
  function closestStation(lat, lon) {
    let best = null;
    for (const s of window.pollenState.latest.stations) {
      if (!s.peak_date) continue;
      const d = miles(lat, lon, s.lat, s.lon);
      if (!best || d < best.d) best = { rec: s, d };
    }
    return best;
  }

  function popupHTML(head, lat, lon) {
    const st = window.pollenState, L = st.latest, { fmtDate, isoOfYday, headline } = st.helpers;
    const day = surfaceDay(lat, lon), near = closestStation(lat, lon);
    let date, note;
    if (day === null) {
      date = "Outside the longleaf pine range";
      note = "The map only shows dates inside the range.";
    } else {
      const iso = isoOfYday(st.year, Math.round(day));
      date = iso <= L.as_of ? `Peak pollen came around ${fmtDate(iso)}` : `Peak pollen expected around ${fmtDate(iso)}`;
      const mae = st.surface && st.surface.fit && st.surface.fit.loo_mae_days;
      note = `Read from the smoothed map between stations${mae ? ` (typically off by about ${Math.max(1, Math.round(mae))} days)` : ""}.`;
    }
    // a station hundreds of miles away says nothing about here (visitors from outside the region)
    const nearHTML = near && (day !== null || near.d <= 100) ? `<p class="me-near">Closest station: <strong>${esc(st.helpers.niceName(near.rec.name))}, ${esc(near.rec.state)}</strong> (${Math.max(1, Math.round(near.d))} mi away). ${esc(headline(near.rec))}.</p>` : "";
    return `<div class="me"><p class="me-head">${esc(head)}</p><p class="me-date">${esc(date)}</p>${nearHTML}<p class="me-note">${esc(note)}</p></div>`;
  }

  function showPopup(html, lat, lon, offset) {
    if (popup) popup.remove();
    popup = new maplibregl.Popup({ closeButton: true, closeOnClick: false, offset, maxWidth: "270px" })
      .setLngLat([lon, lat]).setHTML(html).addTo(window.pollenMap);
  }

  // ---------- a short message over the map ----------
  function toast(text) {
    let t = document.querySelector(".map-toast");
    if (!t) {
      t = document.createElement("div");
      t.className = "map-toast";
      t.setAttribute("role", "status");
      document.querySelector(".map-wrap").appendChild(t);
    }
    t.textContent = text;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 7000);
  }

  // ---------- the button ----------
  function setBusy(busy) {
    btn.disabled = busy;
    btn.querySelector("span").textContent = busy ? "Locating…" : "Find my location";
  }
  function found(pos) {
    setBusy(false);
    const { latitude: lat, longitude: lon } = pos.coords, map = window.pollenMap;
    const close = document.querySelector("#panel .close");
    if (close && document.querySelector("#panel.open")) close.click();     // the station panel would cover the spot
    if (marker) marker.remove();
    const dot = document.createElement("div");
    dot.className = "me-dot";
    dot.setAttribute("aria-label", "Your location");
    marker = new maplibregl.Marker({ element: dot }).setLngLat([lon, lat]).addTo(map);
    const inside = surfaceDay(lat, lon) !== null;
    map.flyTo({ center: [lon, lat], zoom: Math.max(map.getZoom(), inside ? 6.5 : 5), duration: reduceMotion() ? 0 : 900 });
    showPopup(popupHTML("Near you", lat, lon), lat, lon, 16);
  }
  function failed(err) {
    setBusy(false);
    toast(err && err.code === 1
      ? "Location is blocked in your browser. You can still click anywhere on the map to read the date there."
      : "Couldn't find your location. You can still click anywhere on the map to read the date there.");
  }
  btn.addEventListener("click", () => {
    if (!navigator.geolocation) { toast("This browser can't share your location. Click anywhere on the map to read the date there."); return; }
    setBusy(true);
    navigator.geolocation.getCurrentPosition(found, failed, { enableHighAccuracy: false, timeout: 12000, maximumAge: 600000 });
  });

  // ---------- click anywhere else inside the range to read the date there ----------
  function wire(map) {
    map.on("click", (e) => {
      if (map.queryRenderedFeatures(e.point, { layers: ["stations"] }).length) return;   // a station click opens its own panel
      const { lat, lng } = e.lngLat;
      if (surfaceDay(lat, lng) === null) return;
      showPopup(popupHTML("At this spot", lat, lng), lat, lng, 6);
    });
    btn.disabled = false;
  }
  // map.js builds the map after the data arrives, so wait until its layers exist
  let tries = 0;
  const wait = setInterval(() => {
    const map = window.pollenMap;
    if (map && window.pollenState && window.pollenState.helpers && map.getLayer && map.getLayer("stations")) {
      clearInterval(wait);
      wire(map);
    } else if (++tries > 200) clearInterval(wait);   // ~30 s: the map never came up; the button stays disabled
  }, 150);
})();
