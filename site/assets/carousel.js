/* Front page: the finished seasons as a fan of small static maps, oldest at the left and newest at the right, both in full
   and the years between overlapped like a deck of cards. Point at a card and a larger map of that year shows above it (the
   newest year to begin with). Each card links to gallery.html#YYYY.
   Reads seasons/index.json and gallery/thumbs/YYYY.png (see scripts/build_gallery.py). */
(() => {
  "use strict";
  const host = document.querySelector("#past-seasons");
  if (!host) return;
  const fmt = (iso) => new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  const thumb = (y) => `gallery/thumbs/${y}.png`;

  fetch("seasons/index.json", { cache: "no-cache" }).then((r) => r.json()).then((idx) => {
    const seasons = idx.seasons.slice().reverse();   // oldest first, so the fan reads left to right through time
    const n = seasons.length;
    if (!n) return;
    const cards = seasons.map((s, i) => {
      const end = i === 0 || i === n - 1;
      return `<a class="past-card${end ? " end" : ""}" style="--i:${i}" data-i="${i}" href="gallery.html#${s.year}" aria-label="${s.year} season: peak from ${fmt(s.first)} to ${fmt(s.last)}">` +
        `<img src="${thumb(s.year)}" alt="Map of peak pollen dates across the longleaf pine range in ${s.year}" width="480" height="338" ${end ? "" : 'loading="lazy"'}>` +
        `<span class="yr">${s.year}</span></a>`;
    }).join("");
    host.innerHTML =
      `<div class="past-head"><h2>Explore previous years</h2><a href="gallery.html">See the full gallery &rarr;</a></div>` +
      `<div class="past-stage" aria-live="polite">` +
        `<a class="stage-link" href="gallery.html#${seasons[n - 1].year}"><img class="stage-img" src="${thumb(seasons[n - 1].year)}" alt="" width="480" height="338"></a>` +
        `<div class="stage-text"><b class="stage-year"></b><span class="stage-mid"></span><span class="stage-range"></span>` +
        `<span class="stage-actions"><a class="open" href="#">Explore this year &rarr;</a></span></div>` +
      `</div>` +
      `<div class="past-track" style="--mid:${Math.max(0, n - 2)}" role="region" aria-label="Past seasons, oldest at the left and newest at the right">${cards}</div>`;

    const stageImg = host.querySelector(".stage-img"), stageLink = host.querySelector(".stage-link");
    const openLink = host.querySelector(".open");
    const cardEls = [...host.querySelectorAll(".past-card")];
    let current = -1;
    const show = (i) => {
      if (i === current) return;
      current = i;
      const s = seasons[i];
      stageImg.src = thumb(s.year);
      stageImg.alt = `Map of peak pollen dates across the longleaf pine range in ${s.year}`;
      stageLink.href = openLink.href = `gallery.html#${s.year}`;
      host.querySelector(".stage-year").textContent = `${s.year} season`;
      host.querySelector(".stage-mid").innerHTML = `Half of the stations had peaked by <strong>${fmt(s.median)}</strong>`;
      host.querySelector(".stage-range").textContent = `First stations ${fmt(s.first)}, last ${fmt(s.last)} (${s.in_range} stations in the range)`;
      cardEls.forEach((c, k) => c.classList.toggle("on", k === i));
    };
    show(n - 1);                                       // the newest season to begin with
    cardEls.forEach((c, i) => {                        // pointing at (or tabbing to) a year shows it in the panel
      c.addEventListener("mouseenter", () => show(i));
      c.addEventListener("focus", () => show(i));
    });
  }).catch((err) => console.warn("past seasons not loaded", err));
})();
