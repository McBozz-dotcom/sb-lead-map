/* SB Lead Map front end. Plain JS + Leaflet, no build step. */
(function () {
  "use strict";

  const STATUS_LABELS = { new: "New", contacted: "Contacted", interested: "Interested", not_interested: "Not interested" };
  const LS_KEY = "sbleadmap.status.v1";
  const THIS_YEAR = new Date().getFullYear();
  const CENTER = [34.425, -119.72];

  const state = {
    all: [],
    shown: [],
    statuses: {},
    saveMode: "browser",
    catsOn: new Set(Object.keys(CATS)),
    selected: null,
    markers: new Map(),
  };

  // ---------- helpers ----------
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? u : null);
  const money = (n) => (n >= 1e6 ? `$${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M` : `$${Math.round(n / 1e3)}K`);
  const years = (b) => (b.year_founded ? THIS_YEAR - b.year_founded : null);
  const statusOf = (b) => state.statuses[b.id]?.status || "new";
  const webRating = (b) => b.website_check?.rating || (b.website ? "unchecked" : "none");
  const stars = (n) => `<span class="stars" title="Wanted level ${n}/5">${"★".repeat(n)}<span class="off">${"★".repeat(5 - n)}</span></span>`;
  const catOf = (b) => CATS[b.category] || CATS.retail;

  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.classList.remove("hidden");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => t.classList.add("hidden"), 1800);
  }

  // ---------- map ----------
  const TILE_URL = "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
  const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

  const map = L.map("map", { zoomControl: false, preferCanvas: false }).setView(CENTER, 13);
  L.control.zoom({ position: "bottomright" }).addTo(map);
  L.tileLayer(TILE_URL, { attribution: TILE_ATTR, subdomains: "abcd", maxZoom: 20, className: "gta-tiles" }).addTo(map);
  const markerLayer = L.layerGroup().addTo(map);

  const radar = L.map("radar", {
    zoomControl: false, attributionControl: false, dragging: false, scrollWheelZoom: false,
    doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false,
  }).setView(CENTER, 11);
  L.tileLayer(TILE_URL, { subdomains: "abcd", className: "gta-tiles" }).addTo(radar);
  const radarLayer = L.layerGroup().addTo(radar);
  const syncRadar = () => radar.setView(map.getCenter(), Math.max(map.getZoom() - 3, 9), { animate: false });
  map.on("move zoom", syncRadar);

  function iconFor(b) {
    const c = catOf(b);
    const st = statusOf(b);
    const rating = webRating(b);
    const cls = ["blip"];
    if (state.selected === b.id) cls.push("sel");
    if (st === "not_interested") cls.push("dim");
    else if ((rating === "none" || rating === "weak") && st === "new") cls.push("hot");
    const badge = st !== "new" ? `<span class="st ${st}">${st === "interested" ? "$" : st === "contacted" ? "✓" : "×"}</span>` : "";
    return L.divIcon({
      className: cls.join(" "),
      html: `<div class="b" style="--c:${c.color}">${blipSvg(b.category, 16)}${badge}</div>`,
      iconSize: [30, 30],
      iconAnchor: [15, 15],
    });
  }

  function markerFor(b) {
    let m = state.markers.get(b.id);
    if (!m) {
      m = L.marker([b.lat, b.lon], { icon: iconFor(b), title: b.name, riseOnHover: true, keyboard: true });
      m.on("click", () => select(b.id, false));
      state.markers.set(b.id, m);
    }
    return m;
  }
  const refreshIcon = (b) => state.markers.get(b.id)?.setIcon(iconFor(b));

  // ---------- filters ----------
  function readFilters() {
    const rev = $("#f-rev").value;
    const [rlo, rhi] = rev === "any" ? [null, null] : rev.split("-").map((x) => (x === "" ? Infinity : Number(x)));
    return {
      q: $("#search").value.trim().toLowerCase(),
      web: $("#f-web").value,
      status: $("#f-status").value,
      score: Number($("#f-score").value),
      ymin: $("#f-ymin").value === "" ? null : Number($("#f-ymin").value),
      ymax: $("#f-ymax").value === "" ? null : Number($("#f-ymax").value),
      rlo, rhi,
      unknown: $("#f-unknown").checked,
    };
  }

  function matches(b, f) {
    if (!state.catsOn.has(b.category)) return false;
    if (f.q) {
      const hay = [b.name, b.address, b.subtype, b.category_label, b.city, b.owner_name, b.phone].join(" ").toLowerCase();
      if (!f.q.split(/\s+/).every((t) => hay.includes(t))) return false;
    }
    const r = webRating(b);
    if (f.web === "needs" ? !(r === "none" || r === "weak") : f.web !== "any" && r !== f.web) return false;
    const st = statusOf(b);
    if (f.status === "open" ? st === "not_interested" : f.status !== "any" && st !== f.status) return false;
    if ((b.lead_score || 0) < f.score) return false;
    if (f.ymin !== null || f.ymax !== null) {
      const y = years(b);
      if (y === null) { if (!f.unknown) return false; }
      else if ((f.ymin !== null && y < f.ymin) || (f.ymax !== null && y > f.ymax)) return false;
    }
    if (f.rlo !== null) {
      if (b.revenue_low == null) { if (!f.unknown) return false; }
      else if (b.revenue_high < f.rlo || b.revenue_low >= f.rhi) return false;
    }
    return true;
  }

  const SORTS = {
    score: (a, b) => (b.lead_score || 0) - (a.lead_score || 0) || a.name.localeCompare(b.name),
    name: (a, b) => a.name.localeCompare(b.name),
    type: (a, b) => a.category_label.localeCompare(b.category_label) || a.name.localeCompare(b.name),
    age: (a, b) => (a.year_founded || 9999) - (b.year_founded || 9999) || a.name.localeCompare(b.name),
  };

  function render() {
    const f = readFilters();
    state.shown = state.all.filter((b) => matches(b, f)).sort(SORTS[$("#sort").value]);
    const shownIds = new Set(state.shown.map((b) => b.id));

    markerLayer.clearLayers();
    radarLayer.clearLayers();
    for (const b of state.shown) {
      markerLayer.addLayer(markerFor(b));
      radarLayer.addLayer(L.circleMarker([b.lat, b.lon], { radius: 3, weight: 1, color: "#000", fillColor: catOf(b).color, fillOpacity: 1 }));
    }
    if (state.selected && !shownIds.has(state.selected)) closeDetail();

    $("#count").textContent = `${state.shown.length} / ${state.all.length} LEADS`;
    const list = $("#list");
    list.innerHTML = state.shown.slice(0, 400).map((b) => {
      const c = catOf(b);
      const r = webRating(b);
      const tag = r === "none" ? '<span class="tag none">NO SITE</span>' : r === "weak" ? '<span class="tag weak">WEAK SITE</span>' : "";
      const st = statusOf(b);
      return `<li data-id="${esc(b.id)}" class="${state.selected === b.id ? "sel" : ""}">
        <span class="dot" style="--c:${c.color}">${blipSvg(b.category, 13)}</span>
        <span><div class="nm">${esc(b.name)}</div><div class="meta">${tag}${esc(b.subtype || c.label)} · ${esc(b.city || "")}${st !== "new" ? " · " + STATUS_LABELS[st] : ""}</div></span>
        ${stars(b.lead_score || 0)}
      </li>`;
    }).join("") + (state.shown.length > 400 ? `<li class="more"><span></span><span class="meta">+${state.shown.length - 400} more — narrow your filters</span></li>` : "");
    renderStats();
  }

  function renderStats() {
    const hot = state.all.filter((b) => ["none", "weak"].includes(webRating(b)) && statusOf(b) !== "not_interested").length;
    const count = (s) => state.all.filter((b) => statusOf(b) === s).length;
    $("#stat-main").textContent = `${hot} HOT LEADS`;
    $("#stat-rows").innerHTML =
      `<span style="color:var(--neon)">CONTACTED ${count("contacted")}</span>` +
      `<span style="color:var(--money)">INTERESTED ${count("interested")}</span>`;
  }

  function buildChips() {
    const counts = {};
    state.all.forEach((b) => (counts[b.category] = (counts[b.category] || 0) + 1));
    $("#cat-filters").innerHTML = Object.entries(CATS)
      .filter(([k]) => counts[k])
      .map(([k, c]) => `<span class="chip" data-cat="${k}" title="Click to toggle, double-click to show only this"><span class="dot" style="--c:${c.color}">${blipSvg(k, 12)}</span>${esc(c.label)} <span class="n">${counts[k]}</span></span>`)
      .join("");
  }

  // ---------- detail panel ----------
  const BADGE = { sourced: "SOURCED", estimated: "EST.", manual: "MANUAL", unknown: "UNKNOWN" };

  function field(label, b, key, valueHtml, opts = {}) {
    const p = (b.provenance || {})[opts.prov || key];
    const has = valueHtml !== null && valueHtml !== undefined && valueHtml !== "";
    const status = has ? p?.status || "sourced" : "unknown";
    const src = has
      ? `${esc(p?.source || "")}${p?.retrieved ? ` · ${esc(p.retrieved)}` : ""}${p?.note ? `<br>${esc(p.note)}` : ""}`
      : esc(opts.unknownNote || "Not found in any source");
    return `<div class="field"><div class="k">${esc(label)}</div>
      <div class="v ${has ? "" : "unknown"}">${has ? valueHtml : "Unknown"}
        <span class="src"><span class="badge ${status}">${BADGE[status]}</span>${src}</span></div></div>`;
  }

  function websiteBlock(b) {
    const wc = b.website_check;
    const r = webRating(b);
    const title = { none: "NO WEBSITE — PRIME LEAD", weak: "WEAK WEBSITE — GOOD LEAD", ok: "WEBSITE LOOKS OK", unchecked: "WEBSITE NOT CHECKED" }[r];
    const issues = wc?.issues?.length ? `<ul>${wc.issues.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>` : "";
    const when = wc?.checked && b.website ? `<div class="save-where">Checked ${esc(wc.checked)} by automated homepage scan</div>` : "";
    return `<div class="web-verdict ${r}">${title}${issues}</div>${when}`;
  }

  function openDetail(b) {
    const c = catOf(b);
    const st = statusOf(b);
    const note = state.statuses[b.id]?.note || "";
    const web = safeUrl(b.website);
    const social = safeUrl(b.social_url);
    const y = years(b);
    let revenue = null;
    if (b.revenue_usd) revenue = money(b.revenue_usd);
    else if (b.revenue_low != null) revenue = `Est. ${money(b.revenue_low)} – ${money(b.revenue_high)} / yr`;
    const mapsQ = encodeURIComponent(`${b.name} ${b.address || b.city || ""}`);
    const googleQ = encodeURIComponent(`"${b.name}" ${b.city || "Santa Barbara"} owner`);

    const d = $("#detail");
    d.style.setProperty("--c", c.color);
    d.innerHTML = `
      <div class="d-head">
        <button class="icon-btn d-close" title="Close (Esc)" aria-label="Close">✕</button>
        <div class="d-type"><span class="dot">${blipSvg(b.category, 16)}</span>${esc(c.label)}${b.subtype ? " · " + esc(b.subtype) : ""}</div>
        <div class="d-name">${esc(b.name)}</div>
        ${stars(b.lead_score || 0)}<span class="wanted-label">WANTED LEVEL</span>
        <div class="reasons">${esc((b.lead_reasons || []).join(" · "))}</div>
      </div>

      <div class="d-sec">
        <h3>Lead status</h3>
        <div class="status-btns">${Object.entries(STATUS_LABELS).map(([k, v]) => `<button data-s="${k}" class="${st === k ? "on" : ""}">${v}</button>`).join("")}</div>
        <textarea id="note" placeholder="Notes: who you talked to, follow-up date…">${esc(note)}</textarea>
        <div class="save-where">${state.saveMode === "server" ? "Saved to data/lead_status.json" : "Saved in this browser only (run python serve.py to save to disk)"}</div>
      </div>

      <div class="d-sec">
        <h3>Website</h3>
        ${websiteBlock(b)}
      </div>

      <div class="d-sec">
        <h3>Intel</h3>
        ${field("Phone", b, "phone", b.phone ? `<a href="tel:${esc(b.phone.replace(/[^\d+]/g, ""))}">${esc(b.phone)}</a>` : null)}
        ${field("Owner", b, "owner_name", b.owner_name ? esc(b.owner_name) : null, { unknownNote: "Not public in our sources — add it in data/manual_enrichment.csv once you find it" })}
        ${b.registered_agent ? field("Reg. agent", b, "registered_agent", esc(b.registered_agent)) : ""}
        ${b.legal_entity ? field("Legal entity", b, "legal_entity", esc(b.legal_entity)) : ""}
        ${field("In business", b, "year_founded", b.year_founded ? `Since ${b.year_founded} (${y} yr${y === 1 ? "" : "s"})` : null)}
        ${field("Employees", b, "employees", b.employees ? esc(b.employees) : null)}
        ${field("Revenue", b, "revenue", revenue, { prov: b.revenue_usd ? "revenue_usd" : "revenue", unknownNote: "Private businesses don't publish revenue. An estimate appears once an employee count is known." })}
        ${field("Website", b, "website", web ? `<a href="${esc(web)}" target="_blank" rel="noopener noreferrer">${esc(web.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, ""))}</a>` : null)}
        ${social ? field("Social", b, "social_url", `<a href="${esc(social)}" target="_blank" rel="noopener noreferrer">${esc(social.replace(/^https?:\/\/(www\.)?/, ""))}</a>`) : ""}
        ${field("Address", b, "address", b.address ? esc(b.address) : null)}
        ${b.email ? field("Email", b, "email", `<a href="mailto:${esc(b.email)}">${esc(b.email)}</a>`) : ""}
        ${b.opening_hours ? field("Hours", b, "opening_hours", esc(b.opening_hours)) : ""}
        ${b.google_rating != null ? field("Google", b, "google_rating", `${b.google_rating}★ (${b.google_reviews || 0} reviews)`) : ""}
        ${b.research_notes ? `<div class="field"><div class="k">Research</div><div class="v">${esc(b.research_notes)}</div></div>` : ""}
      </div>

      <div class="d-sec actions">
        <a class="btn small" href="https://www.google.com/maps/search/?api=1&query=${mapsQ}" target="_blank" rel="noopener noreferrer">Google Maps</a>
        <a class="btn small" href="https://www.google.com/search?q=${googleQ}" target="_blank" rel="noopener noreferrer">Find owner</a>
        <a class="btn small" href="https://bizfileonline.sos.ca.gov/search/business" target="_blank" rel="noopener noreferrer">CA bizfile</a>
      </div>
      <div class="d-sec save-where">ID ${esc(b.id)}</div>`;

    d.classList.remove("hidden");
    document.body.classList.add("detail-open");
    d.querySelector(".d-close").onclick = closeDetail;
    d.querySelectorAll(".status-btns button").forEach((btn) => (btn.onclick = () => setStatus(b, btn.dataset.s, $("#note").value)));
    const noteEl = $("#note");
    noteEl.oninput = () => {
      clearTimeout(noteEl._t);
      noteEl._t = setTimeout(() => setStatus(b, statusOf(b), noteEl.value, true), 600);
    };
  }

  function closeDetail() {
    const prev = state.all.find((b) => b.id === state.selected);
    state.selected = null;
    $("#detail").classList.add("hidden");
    document.body.classList.remove("detail-open");
    if (prev) refreshIcon(prev);
    document.querySelectorAll("#list li.sel").forEach((li) => li.classList.remove("sel"));
  }

  function select(id, fly) {
    const b = state.all.find((x) => x.id === id);
    if (!b) return;
    const prev = state.all.find((x) => x.id === state.selected);
    state.selected = id;
    if (prev) refreshIcon(prev);
    refreshIcon(b);
    document.querySelectorAll("#list li").forEach((li) => li.classList.toggle("sel", li.dataset.id === id));
    document.querySelector(`#list li[data-id="${CSS.escape(id)}"]`)?.scrollIntoView({ block: "nearest" });
    if (fly) map.flyTo([b.lat, b.lon], Math.max(map.getZoom(), 16), { duration: 0.6 });
    openDetail(b);
  }

  // ---------- status persistence ----------
  async function loadStatuses() {
    try {
      const r = await fetch("/api/status", { cache: "no-store" });
      if (r.ok && (r.headers.get("content-type") || "").includes("json")) {
        state.statuses = await r.json();
        state.saveMode = "server";
        return;
      }
    } catch (_) { /* static hosting or file:// */ }
    try { state.statuses = JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch (_) { state.statuses = {}; }
  }

  async function setStatus(b, status, note, quiet) {
    if (status === "new" && !note) delete state.statuses[b.id];
    else state.statuses[b.id] = { status, note, updated: new Date().toISOString() };
    let ok = true;
    if (state.saveMode === "server") {
      try {
        const r = await fetch("/api/status", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: b.id, status, note }) });
        ok = r.ok;
      } catch (_) { ok = false; }
    } else {
      try { localStorage.setItem(LS_KEY, JSON.stringify(state.statuses)); } catch (_) { ok = false; }
    }
    if (!quiet) {
      toast(ok ? `${STATUS_LABELS[status].toUpperCase()}` : "SAVE FAILED");
      document.querySelectorAll(".status-btns button").forEach((btn) => btn.classList.toggle("on", btn.dataset.s === status));
      refreshIcon(b);
      render();
    } else if (!ok) toast("SAVE FAILED");
  }

  // ---------- CSV export ----------
  function exportCsv() {
    const cols = [
      ["Name", (b) => b.name], ["Type", (b) => b.category_label], ["Subtype", (b) => b.subtype], ["City", (b) => b.city],
      ["Address", (b) => b.address], ["Phone", (b) => b.phone], ["Website", (b) => b.website],
      ["Website rating", (b) => webRating(b)], ["Website issues", (b) => (b.website_check?.issues || []).join("; ")],
      ["Wanted level", (b) => b.lead_score], ["Owner", (b) => b.owner_name || "Unknown"],
      ["Year founded", (b) => b.year_founded || "Unknown"], ["Years in business", (b) => years(b) ?? "Unknown"],
      ["Employees", (b) => b.employees || "Unknown"],
      ["Revenue", (b) => (b.revenue_usd ? b.revenue_usd : b.revenue_low != null ? `Est. ${b.revenue_low}-${b.revenue_high}` : "Unknown")],
      ["Status", (b) => STATUS_LABELS[statusOf(b)]], ["Notes", (b) => state.statuses[b.id]?.note || ""],
      ["Latitude", (b) => b.lat], ["Longitude", (b) => b.lon], ["ID", (b) => b.id],
      ["Field sources", (b) => Object.entries(b.provenance || {}).map(([k, v]) => `${k}: ${v.source} [${v.status}]`).join("; ")],
    ];
    const cell = (v) => {
      let s = String(v ?? "");
      if (typeof v === "string" && /^[=+\-@]/.test(s)) s = "'" + s; // stop spreadsheet formula injection
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    const csv = [cols.map((c) => c[0]).join(",")].concat(state.shown.map((b) => cols.map((c) => cell(c[1](b))).join(","))).join("\r\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv" }));
    a.download = `sb-leads-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    toast(`EXPORTED ${state.shown.length} LEADS`);
  }

  // ---------- wiring ----------
  function bind() {
    ["#search", "#f-ymin", "#f-ymax"].forEach((s) => $(s).addEventListener("input", render));
    ["#f-web", "#f-status", "#f-score", "#f-rev", "#f-unknown", "#sort"].forEach((s) => $(s).addEventListener("change", render));
    $("#cat-filters").addEventListener("click", (e) => {
      const chip = e.target.closest(".chip");
      if (!chip) return;
      const k = chip.dataset.cat;
      state.catsOn.has(k) ? state.catsOn.delete(k) : state.catsOn.add(k);
      chip.classList.toggle("off", !state.catsOn.has(k));
      render();
    });
    $("#cat-filters").addEventListener("dblclick", (e) => {
      const chip = e.target.closest(".chip");
      if (!chip) return;
      state.catsOn = new Set([chip.dataset.cat]);
      document.querySelectorAll(".chip").forEach((c) => c.classList.toggle("off", c.dataset.cat !== chip.dataset.cat));
      render();
    });
    $("#list").addEventListener("click", (e) => {
      const li = e.target.closest("li[data-id]");
      if (li) select(li.dataset.id, true);
    });
    $("#export").addEventListener("click", exportCsv);
    $("#hud-toggle").addEventListener("click", () => {
      $("#hud").classList.toggle("collapsed");
      document.body.classList.toggle("hud-collapsed");
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeDetail();
      if (e.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) { e.preventDefault(); $("#search").focus(); }
    });
    const tick = () => ($("#clock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));
    tick();
    setInterval(tick, 15000);
  }

  async function init() {
    bind();
    syncRadar();
    let data;
    try {
      const r = await fetch("../data/businesses.json", { cache: "no-store" });
      if (!r.ok) throw new Error(r.status);
      data = await r.json();
    } catch (_) {
      $("#empty").classList.remove("hidden");
      return;
    }
    state.all = (data.businesses || []).filter((b) => b.lat != null && b.lon != null);
    await loadStatuses();
    buildChips();
    render();
    if (state.all.length) map.fitBounds(L.latLngBounds(state.all.map((b) => [b.lat, b.lon])).pad(0.05), window.innerWidth > 760 ? { paddingTopLeft: [380, 0] } : { paddingBottomRight: [0, window.innerHeight * 0.5] });
    document.title = `SB Lead Map · ${state.all.length} leads`;
  }

  init();
})();
