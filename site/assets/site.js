/* The menu button in the header (shown on phones). One script for every page; the header itself is site/template.html. */
(() => {
  "use strict";
  const header = document.querySelector(".site-header"), button = header && header.querySelector(".nav-toggle");
  if (!button) return;
  const set = (open) => {
    header.classList.toggle("open", open);
    button.setAttribute("aria-expanded", String(open));
    button.setAttribute("aria-label", open ? "Close menu" : "Open menu");
  };
  button.addEventListener("click", () => set(!header.classList.contains("open")));
  header.querySelectorAll("nav a").forEach((a) => a.addEventListener("click", () => set(false)));
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") set(false); });
  document.addEventListener("click", (e) => { if (!header.contains(e.target)) set(false); });
})();
