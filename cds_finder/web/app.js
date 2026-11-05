"use strict";

(() => {
  // ------------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------------
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
  const fmt = (n) => Number(n).toLocaleString("en-US");
  const plural = (n, word, many = word + "s") => `${fmt(n)} ${n === 1 ? word : many}`;
  const NAME = /^[A-Z0-9_/]{1,30}$/;
  const isName = (t) => NAME.test(t);
  const splitTables = (text) => [...new Set(String(text || "").toUpperCase().split(/[\s,;+]+/).filter(Boolean))];
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
  const when = (iso) => {
    const d = new Date(iso);
    return isNaN(d) ? iso : d.toLocaleString("en-GB", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  };
  const ICON = {
    yes: '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2 6.5l2.5 2.5L10 3.5"/></svg>',
    no: '<svg viewBox="0 0 12 12" aria-hidden="true"><path d="M3 3l6 6M9 3l-6 6"/></svg>',
    search: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5L14 14"/></svg>',
    product: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l9 4.5-9 4.5-9-4.5z"/><path d="M3 12l9 4.5 9-4.5"/><path d="M3 16.5l9 4.5 9-4.5"/></svg>',
    checkCircle: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7.5"/><path d="M6.8 10.2l2.2 2.2 4.3-4.6"/></svg>',
    cross: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M5.5 5.5l9 9M14.5 5.5l-9 9"/></svg>',
    chevron: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5L10.5 8 6 12.5"/></svg>',
    prev: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10 3.5L5.5 8l4.5 4.5"/></svg>',
    close: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8"/></svg>',
    doc: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="2" width="10" height="12" rx="1.5"/><path d="M5.5 5.5h5M5.5 8h5M5.5 10.5h3"/></svg>',
    trophy: '<svg viewBox="0 0 32 32" aria-hidden="true"><path d="M10 5h12v6a6 6 0 0 1-12 0z"/><path d="M10 7H5.5v2a4.5 4.5 0 0 0 4.5 4.5M22 7h4.5v2a4.5 4.5 0 0 1-4.5 4.5"/><path d="M16 17v5M11 27h10M12.5 27l1-5h5l1 5"/></svg>',
    grid: '<svg viewBox="0 0 32 32" aria-hidden="true"><rect x="5" y="5" width="22" height="22" rx="2"/><path d="M5 12.3h22M5 19.7h22M12.3 5v22M19.7 5v22"/></svg>',
    info: '<svg viewBox="0 0 24 24" aria-hidden="true"><ellipse cx="12" cy="6" rx="7" ry="2.8"/><path d="M5 6v12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8V6"/><path d="M5 12c0 1.5 3.1 2.8 7 2.8s7-1.3 7-2.8"/></svg>',
    kvView: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2.5l7 3.5-7 3.5L3 6z"/><path d="M3 10l7 3.5 7-3.5M3 13.8l7 3.5 7-3.5"/></svg>',
    kvTable: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="3.5" width="14" height="13" rx="1.5"/><path d="M3 8h14M3 12.3h14M8 3.5v13"/></svg>',
    kvExtract: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 14l4.5-4.5 3 3L17 6"/><path d="M12.5 6H17v4.5"/></svg>',
    kvDelta: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 16L10 4l6 12z"/></svg>',
    kvRelease: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="7.5"/><path d="M10 6v4.5l3 1.8"/></svg>',
    kvLevel: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 5h14M5.5 10h9M8 15h4"/></svg>',
    kvFields: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M4 5h12M4 10h12M4 15h7"/></svg>',
    kvKey: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="7" cy="12.5" r="3.5"/><path d="M9.5 10l6.5-6.5M13.5 6l2 2"/></svg>',
    kvSize: '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 17V9M8 17V5M13 17v-6M18 17V3"/></svg>',
    kvRoot: '<svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="4.5" r="2"/><circle cx="5" cy="15.5" r="2"/><circle cx="15" cy="15.5" r="2"/><path d="M10 6.5v4M10 10.5l-5 3M10 10.5l5 3"/></svg>',
    arrow: '<svg viewBox="0 0 22 12" aria-hidden="true"><path d="M1 6h18M15 1.5L20 6l-5 4.5"/></svg>',
    compare: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="3" y="3.5" width="14" height="13" rx="1.5"/><path d="M3 8h14M8 8v8.5"/></svg>',
    calc: '<svg viewBox="0 0 20 20" aria-hidden="true"><rect x="4" y="3" width="12" height="14" rx="1.5"/><path d="M7 7h6M7 11h1M10 11h1M7 14h1M10 14h1"/></svg>',
    download: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.5v8M4.5 7L8 10.5 11.5 7M3 13.5h10"/></svg>',
  };
  const store = {
    get: (k) => { try { return localStorage.getItem(k) || ""; } catch { return ""; } },
    set: (k, v) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } },
  };

  class ApiError extends Error {
    constructor(message, status, current) { super(message); this.status = status; this.current = current; }
  }

  async function api(path, { method = "GET", body, raw = false } = {}) {
    let res;
    try {
      res = await fetch(path, {
        method,
        headers: body ? { "Content-Type": "application/json" } : {},
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch {
      throw new ApiError("Cannot reach the server. Check your connection and try again.", 0);
    }
    if (res.ok) return raw ? res : res.json();
    let data = {};
    try { data = await res.json(); } catch { /* not JSON */ }
    throw new ApiError(data.detail || `The server could not complete the request (status ${res.status}).`, res.status, data.current);
  }

  async function download(path, options) {
    const res = await api(path, { ...options, raw: true });
    const name = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "")?.[1] || "export.csv";
    const url = URL.createObjectURL(await res.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  let toastTimer;
  function toast(text) {
    const el = $("#toast");
    el.textContent = text;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 3200);
  }

  function showMessage(el, { title, text, retry, kind = "error" }) {
    el.className = `message ${kind}`;
    el.innerHTML = `<h2>${esc(title)}</h2><p>${esc(text)}</p>${retry ? '<button type="button" class="btn">Try again</button>' : ""}`;
    el.hidden = false;
    if (retry) $("button", el).addEventListener("click", () => { el.hidden = true; retry(); });
  }

  function confirmDialog(title, text, okLabel) {
    const dlg = $("#confirmDialog");
    $("#confirmTitle").textContent = title;
    $("#confirmText").textContent = text;
    $("#confirmOk").textContent = okLabel;
    dlg.returnValue = "";
    dlg.showModal();
    return new Promise((resolve) => dlg.addEventListener("close", () => resolve(dlg.returnValue === "ok"), { once: true }));
  }

  function pager(el, paging, go) {
    if (!paging || paging.pages <= 1) { el.innerHTML = ""; return; }
    const { page, pages } = paging;
    const shown = [...new Set([1, page - 1, page, page + 1, pages])].filter((n) => n >= 1 && n <= pages).sort((a, b) => a - b);
    let last = 0;
    const numbers = shown.map((n) => {
      const gap = n - last > 1 ? '<span class="gap" aria-hidden="true">…</span>' : "";
      last = n;
      return `${gap}<button type="button" data-go="${n}" ${n === page ? 'aria-current="page"' : ""} aria-label="Page ${n}">${fmt(n)}</button>`;
    }).join("");
    el.innerHTML = `
      <button type="button" data-go="${page - 1}" ${page <= 1 ? "disabled" : ""} aria-label="Previous page">${ICON.prev}</button>
      ${numbers}
      <button type="button" data-go="${page + 1}" ${page >= pages ? "disabled" : ""} aria-label="Next page">${ICON.chevron}</button>`;
    el.onclick = (e) => { const b = e.target.closest("[data-go]"); if (b && !b.disabled && b.getAttribute("aria-current") !== "page") go(Number(b.dataset.go)); };
  }

  const prioBadge = (level, label) =>
    `<span class="prio p${level}" title="Priority ${level}: ${esc(label)}">${ICON.doc}P${level}<span class="sr">: ${esc(label)}</span></span>`;

  const productChip = (p, view) => `
    <button type="button" class="dp-chip" data-product="${esc(p.name)}" data-view="${esc(view)}" data-match="${esc(p.cdsViews.join(","))}" aria-haspopup="dialog"
      title="${esc(p.name)}">${ICON.product}<span>${esc(p.title)}</span><span class="sr">: data product details</span></button>`;

  const flag = (on, label) => `<span class="flag ${on ? "yes" : "no"}">${on ? ICON.checkCircle : ICON.cross}${on ? "Yes" : "No"}<span class="sr"> ${esc(label)}</span></span>`;
  const status = (on, yes, no) => `<span class="status ${on ? "yes" : "no"}">${on ? ICON.checkCircle : ICON.cross}${on ? yes : no}</span>`;
  const kvRow = (icon, label, value) => `<div>${icon}<dt>${label}</dt><dd>${value}</dd></div>`;
  const TIER_ICON = { 1: ICON.trophy, 2: ICON.product, 3: ICON.grid };

  // Tabs: click or arrow keys switch panels inside one container
  function tabs(container) {
    const list = $$('[role="tab"]', container);
    const show = (tab) => {
      list.forEach((t) => {
        const on = t === tab;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        $(`#${t.getAttribute("aria-controls")}`, container).hidden = !on;
      });
    };
    list.forEach((t, i) => {
      t.addEventListener("click", () => show(t));
      t.addEventListener("keydown", (e) => {
        const step = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
        if (!step) return;
        e.preventDefault();
        const next = list[(i + step + list.length) % list.length];
        show(next);
        next.focus();
      });
    });
  }
  const tabBar = (id, names) => `<div class="tabs" role="tablist" aria-label="Sections">${names.map((n, i) => `
    <button type="button" role="tab" id="${id}-tab-${i}" aria-controls="${id}-panel-${i}" aria-selected="${i === 0}" tabindex="${i === 0 ? 0 : -1}">${n}</button>`).join("")}</div>`;
  const tabPanel = (id, i, html) => `<section role="tabpanel" id="${id}-panel-${i}" aria-labelledby="${id}-tab-${i}" tabindex="0" ${i ? "hidden" : ""}>${html}</section>`;

  // ------------------------------------------------------------------------
  // Reference data
  // ------------------------------------------------------------------------
  let meta = null;

  async function loadMeta() {
    const pill = $("#dataButton");
    try {
      meta = await api("/api/meta");
    } catch (err) {
      pill.className = "status-pill missing";
      $("#dataStatus").textContent = "Server unavailable";
      showMessage($("#findMessage"), { title: "The finder is not available", text: err.message, retry: loadMeta });
      return;
    }
    const catalogue = meta.dataProducts > 0;
    pill.className = `status-pill ${meta.ready ? "ready" : "missing"}`;
    $("#dataLabel").textContent = catalogue ? "Data Product Catalogue" : "View metadata";
    $("#dataStatus").textContent = !meta.ready ? "Missing" : catalogue ? "Loaded" : `${fmt(meta.views)} views`;
    pill.title = meta.ready ? `${plural(meta.views, "view")} loaded${catalogue ? `, ${plural(meta.dataProducts, "data product")}` : ""}` : "View metadata files are missing";
    if (meta.brandLogo && $("#brandLogo").hidden) {
      const logo = $("#brandLogo");
      logo.addEventListener("load", () => { logo.hidden = false; $("#brandDivider").hidden = false; }, { once: true });
      logo.src = "/brand-logo";
    }
    $("#setupNotice").hidden = meta.ready;
    $("#searchButton").disabled = !meta.ready;
    $("#compareFieldsStart").disabled = !meta.ready;
    $("#tableSuggestions").innerHTML = meta.suggestions.map((t) => `<option value="${esc(t)}">`).join("");
    $("#tierList").innerHTML = meta.priorities.map((p) => `
      <li class="tier p${p.level}">
        <div class="tier-top"><span class="tier-icon">${TIER_ICON[p.level]}</span><span class="tier-badge">P${p.level}</span></div>
        <h3>${esc(p.label)}</h3><p>${esc(p.description)}</p></li>`).join("");
    $("#helpTiers").innerHTML = meta.priorities.map((p) =>
      `<li>${prioBadge(p.level, p.label)}<div><b>${esc(p.label)}</b><span>${esc(p.description)}</span></div></li>`).join("");
    $("#fileList").innerHTML = meta.files.map((f) => `<li><b>${esc(f.name)}</b><span>${esc(f.holds)}</span></li>`).join("");
    $("#noticeBlock").hidden = !meta.notices.length;
    $("#noticeList").innerHTML = meta.notices.map((n) => `<li class="${n.level}"><b>${esc(n.title)}</b>${esc(n.text)}</li>`).join("");
    $("#dataLoaded").textContent = meta.ready
      ? `Metadata for ${plural(meta.views, "view")}, loaded ${meta.loadedAt}.`
      : "The view metadata files are not loaded. The table mapping is available.";
    $$("#tableRows .trow").forEach(updateSource);
  }

  // ------------------------------------------------------------------------
  // Find views: input rows
  // ------------------------------------------------------------------------
  const MAX_TABLES = 10;
  const rowsEl = $("#tableRows");

  function addRow(ecc = "", s4 = "") {
    const row = $("#tableRowTemplate").content.firstElementChild.cloneNode(true);
    const id = `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
    for (const role of ["ecc", "s4"]) {
      $(`[data-role="${role}"]`, row).id = `${id}-${role}`;
      $(`[data-for="${role}"]`, row).htmlFor = `${id}-${role}`;
    }
    $('[data-role="ecc"]', row).value = ecc;
    $('[data-role="s4"]', row).value = s4;
    rowsEl.append(row);
    updateSource(row);
    syncRows();
    return row;
  }

  function syncRows() {
    const rows = $$(".trow", rowsEl);
    rows.forEach((r) => { $('[data-role="remove"]', r).hidden = rows.length === 1; });
    $("#addRow").disabled = rows.length >= MAX_TABLES;
  }

  function updateSource(row) {
    const ecc = $('[data-role="ecc"]', row).value.trim().toUpperCase();
    const s4Input = $('[data-role="s4"]', row);
    const mapped = meta?.mappings?.[ecc];
    const src = $('[data-role="source"]', row);
    s4Input.placeholder = mapped ? mapped.join("; ") : "Same as the ECC table";
    if (s4Input.value.trim()) src.innerHTML = '<span class="tag entered">Entered by you</span>';
    else if (mapped) src.innerHTML = '<span class="tag mapping">From table mapping</span>';
    else src.innerHTML = ecc ? '<span class="tag same">Same table name</span>' : "";
  }

  function readRows() {
    const tables = [];
    let problem = null;
    for (const row of $$(".trow", rowsEl)) {
      const eccEl = $('[data-role="ecc"]', row);
      const s4El = $('[data-role="s4"]', row);
      const ecc = eccEl.value.trim().toUpperCase();
      const s4 = splitTables(s4El.value);
      eccEl.removeAttribute("aria-invalid");
      s4El.removeAttribute("aria-invalid");
      if (!ecc && !s4.length) continue;
      if (!isName(ecc)) {
        eccEl.setAttribute("aria-invalid", "true");
        problem ??= { el: eccEl, text: ecc ? `${ecc} is not a valid table name. Use letters, digits, _ and /.` : "Enter the ECC table for this row." };
      }
      const bad = s4.find((t) => !isName(t));
      if (bad || s4.length > 10) {
        s4El.setAttribute("aria-invalid", "true");
        problem ??= { el: s4El, text: bad ? `${bad} is not a valid table name.` : "Enter at most 10 S/4HANA tables." };
      }
      tables.push({ ecc, s4 });
    }
    if (!problem && !tables.length) problem = { el: $('[data-role="ecc"]', rowsEl), text: "Enter at least one ECC table." };
    return { tables, problem };
  }

  rowsEl.addEventListener("input", (e) => {
    const row = e.target.closest(".trow");
    if (row) { e.target.removeAttribute("aria-invalid"); updateSource(row); }
  });
  rowsEl.addEventListener("click", (e) => {
    const clear = e.target.closest('[data-role="clear"]');
    if (clear) {
      const input = clear.previousElementSibling;
      input.value = "";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.focus();
      return;
    }
    const btn = e.target.closest('[data-role="remove"]');
    if (!btn) return;
    const row = btn.closest(".trow");
    const next = row.nextElementSibling || row.previousElementSibling;
    row.remove();
    syncRows();
    $('[data-role="ecc"]', next)?.focus();
  });
  $("#addRow").addEventListener("click", () => $('[data-role="ecc"]', addRow()).focus());

  // ------------------------------------------------------------------------
  // Find views: search and results
  // ------------------------------------------------------------------------
  const search = { tables: [], priority: null, q: "", sort: "recommended", includeCustom: true, withDataProduct: false, page: 1 };
  let result = null;
  let selected = null;
  let searchSeq = 0;
  let detailSeq = 0;
  const detailCache = new Map();

  const requestBody = (extra = {}) => ({
    tables: search.tables, priority: search.priority, includeCustom: search.includeCustom,
    withDataProduct: search.withDataProduct && meta?.dataProducts > 0,
    q: search.q, sort: search.sort, page: search.page, pageSize: 20, ...extra,
  });
  const tablesKey = (tables) => tables.map((t) => t.ecc + (t.s4.length ? ":" + t.s4.join(";") : "")).join(",");

  $("#searchForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const { tables, problem } = readRows();
    if (problem) {
      showMessage($("#findMessage"), { title: "Check your input", text: problem.text, kind: "error" });
      problem.el.focus();
      return;
    }
    $("#findMessage").hidden = true;
    Object.assign(search, { tables, priority: null, q: "", page: 1 });
    $("#viewFilter").value = "";
    detailCache.clear();
    selected = null;
    history.pushState(null, "", "#/find?" + tables.map((t) => "t=" + encodeURIComponent(t.ecc + (t.s4.length ? ":" + t.s4.join(";") : ""))).join("&"));
    runSearch();
  });

  const wide = () => matchMedia("(min-width: 1360px)").matches;
  const catalogueOn = () => meta?.dataProducts > 0;

  function renderSkeleton() {
    const cols = catalogueOn() ? 7 : 6;
    $("#viewList").innerHTML = Array.from({ length: 6 }, () =>
      `<tr class="sk-row" aria-hidden="true">${'<td><span class="skeleton"></span></td>'.repeat(cols)}</tr>`).join("");
    if (!$("#viewDetail").hidden) $("#viewDetail").innerHTML = SKELETON_PANEL;
    $("#resultCount").textContent = "Searching";
  }
  const SKELETON_PANEL = '<div class="sk-detail" aria-hidden="true"><span class="skeleton"></span><span class="skeleton"></span><span class="skeleton"></span><span class="skeleton"></span></div>';

  function setPanel(open) {
    $("#viewDetail").hidden = !open;
    $("#findLayout").classList.toggle("with-panel", open);
  }

  async function runSearch({ keepSelection = false } = {}) {
    const seq = ++searchSeq;
    const button = $("#searchButton");
    $("#results").hidden = false;
    button.setAttribute("aria-busy", "true");
    renderSkeleton();
    try {
      const res = await api("/api/search", { method: "POST", body: requestBody() });
      if (seq !== searchSeq) return;
      result = res;
      search.page = res.paging.page;
      renderResults(keepSelection);
    } catch (err) {
      if (seq !== searchSeq) return;
      $("#results").hidden = true;
      showMessage($("#findMessage"), { title: "The search did not complete", text: err.message, retry: () => runSearch() });
    } finally {
      if (seq === searchSeq) button.removeAttribute("aria-busy");
    }
  }

  function renderResults(keepSelection) {
    const res = result;
    $("#inputSummary").innerHTML = res.inputs.map((i) => {
      const source = { mapping: "from table mapping", entered: "entered by you", same: "same table name" }[i.source];
      const s4 = i.s4.map((t) => `<span class="code ${i.unknownTables.includes(t) ? "unknown" : ""}">${esc(t)}</span>`).join(", ");
      const views = i.views ? plural(i.views, "view") : "no views";
      return `<span class="input-chip"><span class="code">${esc(i.ecc)}</span><span aria-hidden="true">→</span>${s4}<span>${esc(source)} · ${views}</span></span>`;
    }).join("");

    const g = res.guidance;
    const guidance = $("#guidance");
    guidance.hidden = !g;
    if (g) guidance.innerHTML = `<h2>${esc(g.title)}</h2><ul>${g.tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>`;

    const catalogue = catalogueOn();
    $("#dataProductFilter").hidden = !catalogue;
    $("#dataProductCount").textContent = `(${fmt(res.dataProductViews)})`;
    $("#dpColumn").hidden = !catalogue;
    $("#filterDot").hidden = search.sort === "recommended" && search.includeCustom && !search.withDataProduct;

    const none = res.viewsFound === 0;
    $("#resultsCard").hidden = none;
    if (none) { setPanel(false); return; }

    const total = res.priorities.reduce((n, p) => n + p.count, 0);
    $("#resultTotal").textContent = `(${fmt(res.paging.total)})`;
    $("#priorityFilter").innerHTML = [{ level: null, label: "All", count: total }, ...res.priorities].map((p) => {
      const on = search.priority === p.level;
      return `<button type="button" data-level="${p.level ?? ""}" aria-pressed="${on}" ${!p.count && !on ? "disabled" : ""}
        ${p.level ? `title="${esc(p.label)}"` : ""}>${p.level ? `Priority ${p.level}` : "All"}<span class="count">${fmt(p.count)}</span></button>`;
    }).join("");

    const { paging } = res;
    $("#resultCount").textContent = paging.total
      ? `Showing ${fmt(paging.start)}–${fmt(paging.end)} of ${plural(paging.total, "view")}`
      : "No views";
    pager($("#viewPager"), paging, (page) => { search.page = page; runSearch(); });

    const list = $("#viewList");
    const cols = catalogue ? 7 : 6;
    if (!res.results.length) {
      list.innerHTML = `<tr><td colspan="${cols}"><div class="empty"><h3>No views match these filters</h3>
        <p>${plural(res.viewsFound, "view")} read your tables. Change or clear the filters to see them.</p>
        <button type="button" class="btn" id="clearFilters">Clear filters</button></div></td></tr>`;
      $("#clearFilters").addEventListener("click", clearFilters);
      setPanel(false);
      return;
    }
    list.innerHTML = res.results.map((v) => {
      const notes = [
        v.notCovered.length ? `<span class="partial">Reads ${v.covered.length} of ${v.covered.length + v.notCovered.length} tables</span>` : "",
        v.custom ? "Custom view" : "",
      ].filter(Boolean).join(" · ");
      const products = v.dataProducts.length
        ? `<div class="dp-list">${v.dataProducts.map((p) => productChip(p, v.name)).join("")}</div>`
        : '<span class="no-dp">No data product mapped</span>';
      return `<tr data-name="${esc(v.name)}">
        <td class="c-rank"><span class="rank-num" aria-label="Rank ${v.rank}">${fmt(v.rank)}</span>${prioBadge(v.priority, v.priorityLabel)}</td>
        <td class="c-view"><button type="button" class="item" data-name="${esc(v.name)}" aria-current="false">${esc(v.name)}</button>${v.rank === 1 ? '<span class="pill green best" title="Ranked first for your tables">Best match</span>' : ""}
          ${notes ? `<span class="view-sub">${notes}</span>` : ""}</td>
        <td class="c-desc desc-cell">${esc(v.description) || '<span class="fine">No description</span>'}</td>
        ${catalogue ? `<td class="c-dp">${products}</td>` : ""}
        <td class="c-flag" data-label="Extraction">${flag(v.extraction, "extraction")}</td>
        <td class="c-flag" data-label="Delta">${flag(v.delta, "delta")}</td>
        <td class="c-go">${ICON.chevron}</td>
      </tr>`;
    }).join("");

    const names = res.results.map((v) => v.name);
    if (keepSelection && names.includes(selected)) selectView(selected, { focus: false, open: !$("#viewDetail").hidden });
    else if (wide()) selectView(names[0], { focus: false, open: true });
    else { selected = null; setPanel(false); }
  }

  function clearFilters() {
    Object.assign(search, { priority: null, q: "", sort: "recommended", includeCustom: true, withDataProduct: false, page: 1 });
    $("#viewFilter").value = "";
    $("#viewSort").value = "recommended";
    $("#includeCustom").checked = true;
    $("#withDataProduct").checked = false;
    runSearch();
  }

  async function selectView(name, { focus = true, open = true } = {}) {
    selected = name;
    $$("#viewList tr[data-name]").forEach((row) => {
      const on = row.dataset.name === name;
      row.classList.toggle("current", on);
      $(".item", row).setAttribute("aria-current", String(on));
    });
    const key = tablesKey(search.tables) + "|" + name;
    const seq = ++detailSeq;
    const panel = $("#viewDetail");
    if (open) setPanel(true);
    if (!detailCache.has(key)) {
      panel.innerHTML = SKELETON_PANEL;
      try {
        detailCache.set(key, await api("/api/view", { method: "POST", body: { tables: search.tables, name } }));
      } catch (err) {
        if (seq !== detailSeq) return;
        panel.innerHTML = `<div class="panel-body"><div class="message error"><h2>The view details did not load</h2><p>${esc(err.message)}</p><button type="button" class="btn" id="retryDetail">Try again</button></div></div>`;
        $("#retryDetail").addEventListener("click", () => selectView(name));
        return;
      }
    }
    if (seq !== detailSeq) return;
    renderDetail(detailCache.get(key));
    if (focus && !wide()) panel.focus();
  }

  function closeDetail() {
    const name = selected;
    setPanel(false);
    $$("#viewList tr.current").forEach((row) => row.classList.remove("current"));
    selected = null;
    if (name) $(`#viewList .item[data-name="${CSS.escape(name)}"]`)?.focus();
  }

  // Associations the view defines (DD08B). Null when that file is not loaded: the section is left out.
  const associationsBlock = (list) => `
      <h3>Associations</h3>
      ${list.length ? `<table class="ttable atable">
        <thead><tr><th scope="col">Association</th><th scope="col">Cardinality</th></tr></thead>
        <tbody>${list.map((a) => `<tr>
          <td class="code">${esc(a.name)}<span class="to"><span aria-hidden="true">→&nbsp;</span><span class="sr">points to </span>${esc(a.target)}</span>${a.targetDescription ? `<span class="calc">${esc(a.targetDescription)}</span>` : ""}${a.condition ? `<span class="calc on">on ${esc(a.condition)}</span>` : ""}</td>
          <td class="code">${a.cardinality ? esc(a.cardinality) : '<span class="fine">Not stated</span>'}</td></tr>`).join("")}</tbody>
      </table>` : '<p class="fine">This view defines no associations.</p>'}`;

  function renderDetail(v) {
    const n = v.note;
    const extraction = n.capabilities.find((c) => c.label === "Data extraction");
    const delta = n.capabilities.find((c) => c.label === "Delta loads");
    const released = n.capabilities.find((c) => c.label === "Released by SAP");
    const reads = v.covered.join(", ") + (v.notCovered.length ? ` (not ${v.notCovered.join(", ")})` : "");
    const other = v.tables.filter((t) => !t.yours).map((t) => t.table);
    const checks = n.considerations.length
      ? `<ul class="checks">${n.considerations.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>`
      : '<ul class="checks clear"><li>Nothing further to check.</li></ul>';
    const capValue = (c) => c ? `<span class="status ${c.tone === "positive" ? "yes" : "no"}">${c.tone === "positive" ? ICON.checkCircle : ICON.cross}${esc(c.value)}</span>` : "";

    const overview = `
      <div class="desc-box">${ICON.info}<div><b>${esc(v.description || "View description")}</b><p>${esc(n.summary)}</p></div></div>
      ${productCards(v)}
      <dl class="kv">
        ${kvRow(ICON.kvView, "CDS View", `<span class="code">${esc(v.name)}</span>`)}
        ${kvRow(ICON.kvTable, "Source table(s)", `<span class="code">${esc(reads)}</span>${other.length ? `<span class="fine"> + ${plural(other.length, "other table")}</span>` : ""}`)}
        ${kvRow(ICON.kvExtract, "Extraction", capValue(extraction))}
        ${kvRow(ICON.kvDelta, "Delta", capValue(delta))}
        ${released ? kvRow(ICON.kvRelease, "Release status", released.value === "Yes" ? '<span class="pill green">Released</span>' : '<span class="pill amber">Not released</span>') : ""}
        ${kvRow(ICON.kvLevel, "Level of detail", esc(v.detailLevelText))}
        ${kvRow(ICON.kvFields, "Fields", `${fmt(v.matchedFieldCount)} of ${fmt(v.fieldCount)} from your tables`)}
      </dl>`;

    const fields = `
      <div class="fields-bar">
        <label class="search-field"><span class="sr">Filter fields</span>${ICON.search}<input type="search" id="fieldFilter" placeholder="Filter fields" maxlength="60"></label>
        <label class="switch"><input type="checkbox" id="onlyMine"><span>Only from your tables <span class="switch-count" id="fieldCount"></span></span></label>
      </div>
      <div class="fields-wrap" tabindex="0" role="region" aria-label="Field list">
        <table class="ftable">
          <thead><tr><th scope="col" class="n">#</th><th scope="col">Field</th><th scope="col">Comes from</th></tr></thead>
          <tbody id="fieldRows"></tbody>
        </table>
      </div>`;

    const migration = `
      <h3>Why this priority</h3>
      <p>${esc(n.summary)}</p>
      <h3>Recommendation</h3>
      <p class="recommendation">${esc(n.recommendation)}</p>
      <h3>Before you use it</h3>
      ${checks}`;

    const details = `
      <h3>Definition</h3>
      <dl class="facts">
        <div class="span"><dt>Data definition</dt><dd class="code">${esc(v.dataDefinition || "Not available")}</dd></div>
        <div><dt>Reads your tables</dt><dd class="code">${esc(reads)}</dd></div>
        ${v.buildsOn.length ? `<div><dt>Builds on</dt><dd class="code">${esc(v.buildsOn.join(", "))}</dd></div>` : ""}
      </dl>
      <h3>Tables read</h3>
      <table class="ttable">
        <thead><tr><th scope="col">Table</th><th scope="col" class="n">Fields</th><th scope="col">Access</th></tr></thead>
        <tbody>${v.tables.map((t) => `<tr><td class="code ${t.yours ? "yours" : ""}">${esc(t.table)}${t.yours ? '<span class="mini">Your table</span>' : ""}</td>
          <td class="n">${fmt(t.fields)}${t.calculatedFields ? `<span class="calc">+${fmt(t.calculatedFields)} calculated</span>` : ""}</td>
          <td>${t.direct ? "Direct" : "Through other views"}</td></tr>`).join("")}</tbody>
      </table>
      ${v.associations ? associationsBlock(v.associations) : ""}`;

    const panel = $("#viewDetail");
    panel.innerHTML = `
      <div class="panel-head">
        <span class="panel-icon p${v.priority}">${ICON.product}</span>
        <div class="panel-title">
          <h2 class="d-name${v.name.length > 25 ? " longer" : v.name.length > 20 ? " long" : ""}">${esc(v.name)}</h2>
          <div class="panel-sub">${prioBadge(v.priority, v.priorityLabel)}<span>${esc(v.priorityLabel)}</span>
            ${v.rank && result ? `<span>Rank ${fmt(v.rank)} of ${fmt(result.viewsFound)}</span>` : ""}${v.custom ? '<span class="pill">Custom view</span>' : ""}</div>
        </div>
        <button type="button" class="icon-btn" id="closeDetail" aria-label="Close view details">${ICON.close}</button>
      </div>
      <div class="panel-actions">
        <button type="button" class="btn btn-sm" data-act="fields">${ICON.kvFields}Show fields</button>
        <button type="button" class="btn btn-sm" data-act="compare" aria-haspopup="dialog">${ICON.compare}Compare fields</button>
      </div>
      ${tabBar("vd", ["Overview", "Fields", "Migration", "Details"])}
      <div class="panel-body">
        ${tabPanel("vd", 0, overview)}${tabPanel("vd", 1, fields)}${tabPanel("vd", 2, migration)}${tabPanel("vd", 3, details)}
      </div>`;
    tabs(panel);

    const keysFirst = [...v.fields.filter((f) => f.key), ...v.fields.filter((f) => !f.key)];
    const draw = () => {
      const term = $("#fieldFilter").value.trim().toUpperCase();
      const mine = $("#onlyMine").checked;
      const yours = new Set(v.tables.filter((t) => t.yours).map((t) => t.table));
      const rows = keysFirst.map((f, i) => [f, i + 1]).filter(([f]) => (!mine || f.fromYourTables) &&
        (!term || f.name.toUpperCase().includes(term) || f.sources.some((s) => `${s.table}.${s.field}`.includes(term))));
      $("#fieldCount").textContent = rows.length === keysFirst.length ? `(${fmt(keysFirst.length)})` : `(${fmt(rows.length)} of ${fmt(keysFirst.length)})`;
      $("#fieldRows").innerHTML = rows.length ? rows.map(([f, i]) => `
        <tr class="${f.fromYourTables ? "mine" : ""}">
          <td class="n fine">${i}</td>
          <td><span class="fname">${esc(f.name)}</span>${f.key ? '<span class="mini key">Key</span>' : ""}${f.calculated ? '<span class="mini calc">Calculated</span>' : ""}</td>
          <td>${f.sources.length ? f.sources.map((s) => s.table
            ? `<span class="src-line ${yours.has(s.table) ? "mine" : ""}">${esc(s.table)}.${esc(s.field)}</span>${s.via.length ? `<span class="via">through ${esc(s.via.join(" › "))}</span>` : ""}`
            : '<span class="src-line">Constant value</span>').join("") : '<span class="fine">Calculated in the view</span>'}</td>
        </tr>`).join("") : '<tr><td colspan="3" class="empty">No fields match.</td></tr>';
    };
    $("#fieldFilter").addEventListener("input", debounce(draw, 120));
    $("#onlyMine").addEventListener("change", draw);
    $("#closeDetail").addEventListener("click", closeDetail);
    $('[data-act="fields"]', panel).addEventListener("click", () => { $("#vd-tab-1", panel).click(); $("#fieldFilter").focus(); });
    $('[data-act="compare"]', panel).addEventListener("click", () => openFields(false));
    draw();
  }

  // ------------------------------------------------------------------------
  // Data products
  // ------------------------------------------------------------------------
  function productCards(v) {
    if (!catalogueOn()) return "";
    if (!v.dataProducts.length) {
      return `<div class="dp-card none"><span class="dp-icon">${ICON.product}</span>
        <div class="dp-main"><b>No data product mapping available</b>
          <span>This view is not listed in the data product catalogue.</span></div></div>`;
    }
    return v.dataProducts.map((p) => `
      <div class="dp-card">
        <span class="dp-icon">${ICON.product}</span>
        <div class="dp-main">
          <span class="eyebrow">Data product</span>
          <button type="button" class="dp-link" data-product="${esc(p.name)}" data-view="${esc(v.name)}" data-match="${esc(p.cdsViews.join(","))}" aria-haspopup="dialog">${esc(p.title)}</button>
          <span class="dp-id code" title="${esc(p.name)}">${esc(p.name)}</span>
          <span class="dp-sub">${p.entities.length > 1 ? "Entities" : "Entity"}: ${esc(p.entities.join(", ") || "not named")}</span>
          <button type="button" class="text-btn dp-more" data-product="${esc(p.name)}" data-view="${esc(v.name)}" data-match="${esc(p.cdsViews.join(","))}" aria-haspopup="dialog">View details${ICON.chevron}</button>
        </div>
      </div>`).join("");
  }

  const productCache = new Map();
  let productSeq = 0;

  const flagBadge = (value, yes, no) => value === true ? `<span class="badge yes">${ICON.yes}${yes}</span>`
    : value === false ? `<span class="badge no">${ICON.no}${no}</span>` : '<span class="badge">Not stated</span>';

  // match: the CDS view names, as written in the catalogue, that link the selected view to this product
  const matches = (e, match) => Boolean(e.cdsView) && match.includes(e.cdsView);

  function entityItem(e, match) {
    const mine = matches(e, match);
    const fact = (label, value, code = false) => `<div><dt>${label}</dt><dd${code ? ' class="code"' : ""}>${value}</dd></div>`;
    return `<details class="entity ${mine ? "mine" : ""}" ${mine ? "open" : ""} data-search="${esc((e.entity + " " + e.cdsView + " " + e.keys.join(" ")).toUpperCase())}">
      <summary>
        <span class="entity-name"><b>${esc(e.entity || e.cdsView || "Unnamed entity")}</b><span class="code">${esc(e.cdsView || "No CDS view")}</span></span>
        <span class="badges">${mine ? '<span class="badge mine">This view</span>' : ""}${e.inMetadata ? '<span class="badge meta">In view metadata</span>' : ""}${e.root ? '<span class="badge">Root</span>' : ""}
          ${flagBadge(e.extraction, "Extraction", "No extraction")}</span>
      </summary>
      <div class="entity-body">
        <div><h4>Keys</h4><div class="key-chips">${keyChips(e)}</div></div>
        <div><h4>Extraction and size</h4><dl class="facts">
          ${fact("Data extraction", flagBadge(e.extraction, "Available", "Not available"))}
          ${fact("Size category", esc(e.size || "Not stated"))}
          ${fact("Fields", e.fields ?? "Not stated")}
        </dl></div>
        <div><h4>Identification</h4><dl class="facts">
          ${fact("CDS view", esc(e.cdsView || "Not stated"), true)}
          ${fact("Root entity", e.root ? "Yes" : "No")}
          ${fact("In view metadata", e.inMetadata ? "Yes" : "No")}
          ${e.entityType ? fact("Object type", esc(e.entityType), true) : ""}
        </dl></div>
      </div>
    </details>`;
  }
  const keyChips = (e) => e.keys.length ? e.keys.map((k) => `<span>${esc(k)}</span>`).join("") : '<em class="fine">Not listed</em>';
  const extractionText = (value) => value === true ? status(true, "Supported", "") : value === false ? status(false, "", "Not supported") : '<span class="fine">Not stated</span>';

  async function openProduct(name, view = "", matchText = "") {
    const match = matchText ? matchText.split(",") : [];
    const drawer = $("#productDrawer");
    const body = $("#productBody");
    const seq = ++productSeq;
    $("#productTitle").textContent = "Data product";
    $("#productId").textContent = name;
    body.innerHTML = SKELETON_PANEL;
    if (!drawer.open) drawer.showModal();
    let p = productCache.get(name);
    if (!p) {
      try {
        p = await api(`/api/data-products/${encodeURIComponent(name)}`);
        productCache.set(name, p);
      } catch (err) {
        if (seq !== productSeq) return;
        body.innerHTML = `<div class="panel-body"><div class="message error"><h2>The data product details did not load</h2><p>${esc(err.message)}</p><button type="button" class="btn" id="retryProduct">Try again</button></div></div>`;
        $("#retryProduct").addEventListener("click", () => openProduct(name, view, matchText));
        return;
      }
    }
    if (seq !== productSeq) return;
    renderProduct(p, view, match);
  }

  function renderProduct(p, view, match) {
    $("#productTitle").textContent = p.title;
    $("#productId").textContent = p.name + (p.version ? ` · Version ${p.version}` : "");
    const total = p.entities.length;
    const extraction = p.entities.filter((e) => e.extraction === true).length;
    const roots = p.entities.filter((e) => e.root).length;
    const views = new Set(p.entities.filter((e) => e.cdsView).map((e) => e.cdsView.toUpperCase()));
    const known = new Set(p.entities.filter((e) => e.inMetadata).map((e) => e.cdsView.toUpperCase()));
    const mine = p.entities.filter((e) => matches(e, match));
    const ordered = [...mine, ...p.entities.filter((e) => !mine.includes(e))];

    const used = mine.length ? mine.map((e) => `
      <div class="used-entity"><div class="used-title"><span class="eyebrow">Entity</span><b>${esc(e.entity || "Not named")}</b></div>
      <dl class="kv">
        ${kvRow(ICON.kvView, "CDS View", `<span class="code">${esc(e.cdsView)}</span>`)}
        ${kvRow(ICON.kvExtract, "Extraction", extractionText(e.extraction))}
        ${kvRow(ICON.kvRoot, "Root entity", e.root ? "Yes" : "No")}
        ${kvRow(ICON.kvSize, "Size category", esc(e.size || "Not stated"))}
        ${kvRow(ICON.kvFields, "Fields", e.fields ?? "Not stated")}
        ${kvRow(ICON.kvKey, "Keys", `<div class="key-chips">${keyChips(e)}</div>`)}
      </dl></div>`).join("") : "";

    const overview = `
      <div class="desc-box">${ICON.info}<div><b>Data product</b>
        <p>${esc(p.title)} has ${plural(total, "entity", "entities")}${mine.length ? `. ${esc(view)} is used by ${mine.map((e) => esc(e.entity || e.cdsView)).join(" and ")}` : ""}.</p></div></div>
      <div class="stats">
        <div class="stat"><b>${fmt(total)}</b><span>${total === 1 ? "Entity" : "Entities"}</span></div>
        <div class="stat"><b>${fmt(extraction)} of ${fmt(total)}</b><span>Extraction enabled</span></div>
        <div class="stat"><b>${fmt(roots)}</b><span>Root ${roots === 1 ? "entity" : "entities"}</span></div>
        <div class="stat"><b>${fmt(known.size)} of ${fmt(views.size)}</b><span>Views in metadata</span></div>
      </div>
      ${mine.length ? `<h3>Used by ${esc(view)}</h3>${used}` : ""}`;

    const keys = ordered.map((e) => `
      <div class="key-group"><b>${esc(e.entity || e.cdsView)} <span class="code">${esc(e.cdsView)}</span>${matches(e, match) ? ' <span class="badge mine">This view</span>' : ""}</b>
        <div class="key-chips">${keyChips(e)}</div></div>`).join("");

    const extractionList = `
      <p class="fine">${fmt(extraction)} of ${plural(total, "entity", "entities")} enabled for extraction.</p>
      <ul class="ext-list">${ordered.map((e) => `
        <li><span class="entity-name"><b>${esc(e.entity || e.cdsView)}</b><span class="code">${esc(e.cdsView)}</span></span>${extractionText(e.extraction)}</li>`).join("")}</ul>`;

    const details = `
      ${total > 6 ? `<label class="search-field"><span class="sr">Filter entities</span>${ICON.search}<input type="search" id="entityFilter" placeholder="Filter by entity, CDS view or key" maxlength="60"></label>` : ""}
      <p class="fine" id="entityCount">${plural(total, "entity", "entities")}</p>
      <div id="entityList">${ordered.map((e) => entityItem(e, match)).join("")}</div>`;

    const body = $("#productBody");
    body.innerHTML = `${tabBar("dp", ["Overview", "Keys", "Extraction", "Details"])}
      <div class="panel-body">${tabPanel("dp", 0, overview)}${tabPanel("dp", 1, keys)}${tabPanel("dp", 2, extractionList)}${tabPanel("dp", 3, details)}</div>`;
    tabs(body);
    const filter = $("#entityFilter");
    if (filter) {
      filter.addEventListener("input", debounce(() => {
        const term = filter.value.trim().toUpperCase();
        let shown = 0;
        $$("#entityList .entity").forEach((el) => {
          const hit = !term || el.dataset.search.includes(term);
          el.hidden = !hit;
          shown += hit;
        });
        $("#entityCount").textContent = term ? `${fmt(shown)} of ${plural(total, "entity", "entities")}` : plural(total, "entity", "entities");
      }, 120));
    }
  }

  // A click on the backdrop closes a drawer, but only when the press started there too: selecting
  // text inside and letting go over the backdrop also gives a click on the dialog itself.
  const outside = (d, e) => {
    const r = d.getBoundingClientRect();
    return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
  };
  $$(".drawer").forEach((d) => {
    let pressedOutside = false;
    d.addEventListener("pointerdown", (e) => { pressedOutside = e.target === d && outside(d, e); });
    d.addEventListener("click", (e) => {
      if (pressedOutside && e.target === d && outside(d, e)) d.close();
      pressedOutside = false;
    });
  });
  $("#viewDetail").addEventListener("click", (e) => {
    const b = e.target.closest("[data-product]");
    if (b) openProduct(b.dataset.product, b.dataset.view, b.dataset.match);
  });

  $("#viewList").addEventListener("click", (e) => {
    const chip = e.target.closest("[data-product]");
    if (chip) { openProduct(chip.dataset.product, chip.dataset.view, chip.dataset.match); return; }
    if (e.target.closest("#clearFilters")) return;
    const row = e.target.closest("tr[data-name]");
    if (row) selectView(row.dataset.name);
  });
  $("#viewList").addEventListener("keydown", (e) => {
    if (!["ArrowDown", "ArrowUp"].includes(e.key)) return;
    const items = $$("#viewList .item");
    const i = items.indexOf(document.activeElement);
    if (i < 0) return;
    e.preventDefault();
    items[Math.max(0, Math.min(items.length - 1, i + (e.key === "ArrowDown" ? 1 : -1)))].focus();
  });
  $("#priorityFilter").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b || b.disabled) return;
    search.priority = b.dataset.level ? Number(b.dataset.level) : null;
    search.page = 1;
    runSearch();
  });
  $("#viewFilter").addEventListener("input", debounce((e) => { search.q = e.target.value.trim(); search.page = 1; runSearch(); }, 300));
  // Sort and filter popover
  const filterButton = $("#filterButton");
  const filterPanel = $("#filterPanel");
  const setFilterPanel = (open) => {
    filterPanel.hidden = !open;
    filterButton.setAttribute("aria-expanded", String(open));
  };
  filterButton.addEventListener("click", () => setFilterPanel(filterPanel.hidden));
  document.addEventListener("click", (e) => {
    if (!filterPanel.hidden && !e.target.closest(".popover-anchor")) setFilterPanel(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (!filterPanel.hidden) { setFilterPanel(false); filterButton.focus(); return; }
    if (!$("#viewDetail").hidden && !wide() && !document.querySelector("dialog[open]")) closeDetail();
  });

  $("#viewSort").addEventListener("change", (e) => { search.sort = e.target.value; search.page = 1; runSearch({ keepSelection: true }); });
  $("#includeCustom").addEventListener("change", (e) => { search.includeCustom = e.target.checked; search.page = 1; runSearch({ keepSelection: true }); });
  $("#withDataProduct").addEventListener("change", (e) => { search.withDataProduct = e.target.checked; search.page = 1; runSearch({ keepSelection: true }); });
  $("#exportViews").addEventListener("click", async (e) => {
    const b = e.currentTarget;
    b.setAttribute("aria-busy", "true");
    try { await download("/api/search/export", { method: "POST", body: requestBody({ page: 1 }) }); }
    catch (err) { toast(err.message); }
    finally { b.removeAttribute("aria-busy"); }
  });

  // ------------------------------------------------------------------------
  // Compare fields: which views provide the fields a user needs.
  // The fields stay in this page. They are sent with each request and never saved.
  // ------------------------------------------------------------------------
  const MAX_FIELDS = 500;
  const MAX_COMPARE = 4;
  const FIELD_PAGE = 20;
  const HEADER = /^(TABLE|TABNAME|TABLE NAME|TABLE_NAME|FIELD|FIELDNAME|FIELD NAME|FIELD_NAME|FIELDS)$/;
  const fieldsInput = $("#fieldsInput");
  const cmp = { tables: [], fields: [], res: null, chosen: false, page: 1, picked: new Set(), seq: 0 };

  const clean = (c) => c.trim().replace(/^"(.*)"$/, "$1").trim();
  const unique = (list) => [...new Set(list.filter(Boolean).map((t) => t.toUpperCase()))];
  const words = (text) => text.split(/[\s,;]+/);
  const pair = (table, field) => (table ? `${table}-${field}` : field);

  // Typed or pasted text. A line with two cells (two columns copied from Excel) is TABLE and FIELD;
  // anything else is a list of fields separated by commas, spaces or new lines.
  function readFieldText(text) {
    const out = [];
    String(text || "").split(/\r?\n/).forEach((line, n) => {
      const cells = line.split("\t").map(clean).filter(Boolean);
      if (n === 0 && cells.length && cells.every((c) => HEADER.test(c.toUpperCase()))) return;
      if (cells.length === 2 && !/[\s,;]/.test(cells.join(""))) out.push(pair(cells[0], cells[1]));
      else out.push(...words(cells.join(" ")));
    });
    return unique(out);
  }

  // An uploaded file, read in the browser. With a header the TABLE and FIELD columns are used;
  // without one, two columns are TABLE and FIELD and anything else is a list of fields.
  function readFieldFile(text) {
    const lines = String(text).replace(/^﻿/, "").split(/\r?\n/).filter((l) => l.trim());
    if (!lines.length) return [];
    const d = [";", "\t", ","].find((x) => lines[0].includes(x)) || ",";
    const split = (line) => line.split(d).map(clean);
    const head = split(lines[0]).map((h) => h.toUpperCase().replace(/[^A-Z]/g, ""));
    const t = head.findIndex((h) => ["TABLE", "TABNAME", "TABLENAME"].includes(h));
    const f = head.findIndex((h) => ["FIELD", "FIELDNAME", "FIELDS", "TABLEFIELD"].includes(h));
    const rows = (t >= 0 || f >= 0 ? lines.slice(1) : lines).map(split);
    if (f >= 0) return unique(rows.map((c) => pair(t >= 0 ? c[t] : "", c[f] || "")));
    return unique(rows.flatMap((c) => (c.length === 2 && c[0] && c[1] ? [pair(c[0], c[1])] : c.flatMap(words))));
  }

  // From the results toolbar the searched tables are used; from the search card, the tables typed there
  function openFields(fromSearchCard) {
    let tables = search.tables;
    if (fromSearchCard) {
      const typed = readRows();
      if (typed.problem && typed.tables.length) {
        showMessage($("#findMessage"), { title: "Check your input", text: typed.problem.text });
        typed.problem.el.focus();
        return;
      }
      tables = typed.tables;
      $("#findMessage").hidden = true;
    }
    if (tablesKey(tables) !== tablesKey(cmp.tables)) Object.assign(cmp, { tables, res: null });
    if (!cmp.res) $("#fieldsResult").innerHTML = "";
    const names = tables.map((t) => t.ecc).join(", ");
    $("#fieldsSub").textContent = names ? `Looking in ${names}` : "Write each field with its table";
    $("#fieldsHint").textContent = names
      ? "Type or paste fields, separated by commas, spaces or new lines, or upload a CSV or text file. Field names alone are looked for in your tables; add a table to look elsewhere, for example VBAK-ERDAT."
      : "Write each field with its table, for example VBAP-NETWR, or upload a CSV file with the columns TABLE and FIELD.";
    $("#fieldsError").hidden = true;
    $("#fieldsDrawer").showModal();
    countFields();
    fieldsInput.focus();
  }

  function countFields() {
    const n = readFieldText(fieldsInput.value).length;
    $("#fieldsCount").textContent = n ? plural(n, "field") : "";
  }

  function fieldsError(text) {
    $("#fieldsError").textContent = text;
    $("#fieldsError").hidden = false;
  }

  async function compareFields(compare = []) {
    const fields = readFieldText(fieldsInput.value);
    $("#fieldsError").hidden = true;
    if (!fields.length) { fieldsError("Enter at least one field."); fieldsInput.focus(); return; }
    if (fields.length > MAX_FIELDS) { fieldsError(`Enter at most ${fmt(MAX_FIELDS)} fields at a time.`); return; }
    const seq = ++cmp.seq;
    const out = $("#fieldsResult");
    const button = $("#fieldsRun");
    button.setAttribute("aria-busy", "true");
    if (cmp.res) out.classList.add("refreshing");
    else out.innerHTML = SKELETON_PANEL;
    try {
      const res = await api("/api/coverage", { method: "POST", body: { tables: cmp.tables, fields, compare } });
      if (seq !== cmp.seq) return;
      const fresh = !cmp.res || fields.join() !== cmp.fields.join();
      Object.assign(cmp, { fields, res, chosen: compare.length > 0 });
      if (fresh) { cmp.page = 1; cmp.picked = new Set(res.comparison.views.map((v) => v.name)); }
      renderFields();
    } catch (err) {
      if (seq !== cmp.seq) return;
      fieldsError(err.message);
      if (!cmp.res) out.innerHTML = "";
    } finally {
      if (seq === cmp.seq) { button.removeAttribute("aria-busy"); out.classList.remove("refreshing"); }
    }
  }

  const cover = (n, total) => `<span class="cover">${fmt(n)}<span> of ${fmt(total)}</span></span>`;
  // A view opens in the details panel when it reads the tables of the search on screen
  const canOpen = (v) => v.searched && result && tablesKey(cmp.tables) === tablesKey(search.tables);
  const viewRef = (v) => canOpen(v)
    ? `<button type="button" class="item" data-open="${esc(v.name)}" title="Show the view details">${esc(v.name)}</button>`
    : `<span class="code">${esc(v.name)}</span>`;
  const pickText = () => cmp.picked.size ? `${plural(cmp.picked.size, "view")} chosen, up to ${MAX_COMPARE}` : `Choose up to ${MAX_COMPARE} views to compare`;

  function renderFields() {
    const res = cmp.res;
    const s = res.summary;
    $("#fieldsSub").textContent = `Looking in ${res.inputs.map((i) => i.s4.join(",") === i.ecc ? i.ecc : `${i.ecc} → ${i.s4.join(", ")}`).join(" · ")}`;
    const gaps = res.fields.filter((f) => f.status === "missing");
    const calcOnly = res.fields.filter((f) => f.status === "calculated");
    const names = (list) => `<span class="code">${list.map((f) => esc(f.label)).join(", ")}</span>`;
    const findings = [
      s.best ? `<li><b>Best view</b><span class="code">${esc(s.best.name)}</span> ${prioBadge(s.best.priority, s.best.priorityLabel)} provides ${fmt(s.best.covered)} of ${plural(s.requested, "field")}.
        ${s.moreFields ? `<span class="line"><span class="code">${esc(s.moreFields.name)}</span> ${prioBadge(s.moreFields.priority, s.moreFields.priorityLabel)} provides more (${fmt(s.moreFields.covered)} of ${fmt(s.requested)}), but views with a higher priority come first.</span>` : ""}</li>`
        : '<li class="warn"><b>No view provides these fields</b>Check the table and field names.</li>',
      s.combination ? `<li><b>Together</b>${s.combination.views.map((n) => `<span class="code">${esc(n)}</span>`).join(" + ")} provide ${fmt(s.combination.covered)} of the ${fmt(s.coverable)} fields any view has.
        ${s.combination.joins.filter((j) => j.pairs.length).map((j) => `<span class="line">Join on ${joinOn(j)}. See Side by side for details.</span>`).join("")}</li>` : "",
      gaps.length ? `<li class="warn"><b>In no view (${fmt(gaps.length)})</b>${names(gaps)}. ${gaps.length === 1 ? "No view reads this field from its table. It may be" : "No view reads these fields from their tables. They may be"} renamed in S/4HANA, removed, or not exposed in any view.</li>` : "",
      calcOnly.length ? `<li class="warn"><b>Only used inside calculations (${fmt(calcOnly.length)})</b>${names(calcOnly)}</li>` : "",
    ].join("");

    const out = $("#fieldsResult");
    out.innerHTML = `
      <div class="stats">
        <div class="stat"><b>${fmt(s.best ? s.best.covered : 0)} of ${fmt(s.requested)}</b><span>Fields in the best view</span></div>
        <div class="stat"><b>${fmt(s.coverable)} of ${fmt(s.requested)}</b><span>Fields any view provides</span></div>
        <div class="stat"><b>${fmt(res.views.length)}</b><span>Views with at least one</span></div>
        <div class="stat"><b>${fmt(gaps.length + calcOnly.length)}</b><span>Fields no view provides</span></div>
      </div>
      <ul class="findings">${findings}</ul>
      <div class="fields-tabs">${tabBar("fc", ["Side by side", `All views (${fmt(res.views.length)})`, "Your fields"])}</div>
      <div class="fields-panels">${tabPanel("fc", 0, fieldMatrix())}${tabPanel("fc", 1, fieldViews())}${tabPanel("fc", 2, fieldList())}</div>
      <div class="fields-foot"><button type="button" class="btn" id="fieldsExport">${ICON.download}Export CSV</button>
        <span class="fine">One row per view, with the fields it misses.</span></div>`;
    tabs(out);
    fieldPager();
  }

  // The facts the ranking orders views by, one row each. Rows where the views differ are shaded.
  const FACTS = [
    ["Rank", (v) => fmt(v.rank), false],
    ["Priority", (v) => `${prioBadge(v.priority, v.priorityLabel)} ${esc(v.priorityLabel)}`],
    ["Data extraction", (v) => status(v.extraction, "Yes", "No")],
    ["Delta loads", (v) => status(v.delta, "Yes", "No")],
    ["Released by SAP", (v) => v.released === null ? '<span class="fine">Not stated</span>' : status(v.released, "Yes", "No")],
    ["Built by", (v) => v.custom ? "Your system (custom view)" : "SAP"],
    ["Level of detail", (v) => esc(v.detailText)],
    ["Reads your tables", (v) => `<span class="code">${esc(v.reads.join(", "))}</span>`],
    ["Reads them", (v) => v.direct ? "Directly" : "Through other views"],
    ["Other tables mixed in", (v) => fmt(v.otherTables)],
    ["Fields in the view", (v) => fmt(v.fieldsInView)],
    ["Data products", (v) => v.dataProducts.length ? esc(v.dataProducts.join(", ")) : '<span class="fine">None</span>', true, catalogueOn],
  ];

  const joinOn = (j) => j.pairs.map((p) => `<span class="code">${esc(j.left)}.${esc(p.left)} = ${esc(j.right)}.${esc(p.right)}</span>`).join(", ");
  const joinHint = (j) => `<li class="${j.complete ? "" : "warn"}"><b>How to join ${esc(j.left)} and ${esc(j.right)}</b>
    ${j.pairs.length ? `<span class="join-pairs">${j.pairs.map((p) => `<span><span class="code">${esc(j.left)}.${esc(p.left)}</span><span class="code">= ${esc(j.right)}.${esc(p.right)}</span>
      <span class="fine">${esc(p.via)}</span></span>`).join("")}</span>` : ""}${esc(j.note)}</li>`;

  function fieldMatrix() {
    const { views, rows, recommended, verdict, joins } = cmp.res.comparison;
    if (!views.length) return '<div class="empty"><h3>Nothing to compare</h3><p>No view provides any of these fields.</p></div>';
    const total = cmp.res.summary.requested;
    const several = views.length > 1;
    const cell = (c) => c.status === "yes"
      ? `<span class="cell yes">${ICON.checkCircle}<span class="code">${esc(c.element)}</span></span>`
      : c.status === "calculated"
        ? `<span class="cell calc" title="Used inside a calculation">${ICON.calc}<span><span class="sr">Only in a calculation: </span><span class="code">${esc(c.element)}</span></span></span>`
        : `<span class="cell no">${ICON.cross}<span class="sr">Not in this view</span></span>`;
    const head = (first) => `<thead><tr><th scope="col">${first}</th>${views.map((v) => `<th scope="col"><span class="m-head">${prioBadge(v.priority, v.priorityLabel)}
      ${viewRef(v)}${cover(v.covered, total)}${v.name === recommended ? '<span class="pill green">Recommended</span>' : ""}</span></th>`).join("")}</tr></thead>`;
    const facts = FACTS.filter(([, , , shown]) => !shown || shown()).map(([label, show, mark = true]) => {
      const values = views.map(show);
      const differs = several && mark && new Set(values).size > 1;
      return `<tr class="${differs ? "differs" : ""}"><th scope="row">${label}${differs ? '<span class="sr"> (differs)</span>' : ""}</th>${values.map((h) => `<td>${h}</td>`).join("")}</tr>`;
    }).join("");
    const advice = [
      verdict.length ? `<li class="${recommended ? "pick" : ""}"><b>${recommended ? "Which to choose" : "Use them together"}</b>${verdict.map((l) => `<span class="line">${esc(l)}</span>`).join("")}</li>` : "",
      ...joins.map(joinHint),
    ].join("");
    return `
      ${advice ? `<ul class="findings advice">${advice}</ul>` : ""}
      <p class="fine">${cmp.chosen ? "The views you chose." : several ? "The views that together cover the most fields." : "The view that covers the most fields."}
        Choose up to ${MAX_COMPARE} views under All views.${several ? " Shaded rows show where the views differ." : ""}</p>
      <div class="matrix-wrap" tabindex="0" role="region" aria-label="Fields by view">
        <table class="matrix">${head("Field")}
          <tbody>${rows.map((r) => `<tr><th scope="row" class="code">${esc(r.label)}</th>${r.cells.map((c) => `<td>${cell(c)}</td>`).join("")}</tr>`).join("")}</tbody>
        </table>
      </div>
      <h3 id="factsTitle">How they differ</h3>
      <div class="table-wrap facts-wrap" tabindex="0" role="region" aria-labelledby="factsTitle">
        <table class="matrix">${head("View")}<tbody>${facts}</tbody></table>
      </div>`;
  }

  function fieldViews() {
    const views = cmp.res.views;
    if (!views.length) return '<div class="empty"><h3>No view provides these fields</h3><p>Check the table and field names.</p></div>';
    const total = cmp.res.summary.requested;
    const start = (cmp.page - 1) * FIELD_PAGE;
    const shown = views.slice(start, start + FIELD_PAGE);
    return `
      <div class="pick-bar"><span class="fine" id="pickCount">${pickText()}</span>
        <button type="button" class="btn btn-primary" id="comparePicked" ${cmp.picked.size ? "" : "disabled"}>Compare side by side</button></div>
      <div class="table-wrap">
        <table class="vlist">
          <thead><tr><th scope="col"><span class="sr">Compare</span></th><th scope="col">Rank</th><th scope="col">CDS View</th><th scope="col">Fields provided</th></tr></thead>
          <tbody>${shown.map((v) => `<tr>
            <td><input type="checkbox" data-pick="${esc(v.name)}" aria-label="Compare ${esc(v.name)}" ${cmp.picked.has(v.name) ? "checked" : ""}></td>
            <td><span class="rank-num">${fmt(v.rank)}</span>${prioBadge(v.priority, v.priorityLabel)}</td>
            <td>${viewRef(v)}${v.description ? `<span class="view-sub">${esc(v.description)}</span>` : ""}${v.custom ? '<span class="view-sub">Custom view</span>' : ""}</td>
            <td>${cover(v.covered, total)}${v.calculated ? `<span class="view-sub">+${fmt(v.calculated)} only in calculations</span>` : ""}</td></tr>`).join("")}</tbody>
        </table>
      </div>
      <div class="results-foot"><p>Showing ${fmt(start + 1)}–${fmt(start + shown.length)} of ${plural(views.length, "view")}, P1 first, then the most fields</p>
        <nav class="pager" id="fieldsPager" aria-label="View pages"></nav></div>`;
  }

  function fieldList() {
    return `<ul class="flist">${cmp.res.fields.map((f) => `
      <li><span class="code">${esc(f.label)}</span><span class="fine">in ${esc(f.s4Tables.join(", "))}</span>
        ${f.status === "found" ? `<span class="cell yes">${ICON.checkCircle}In ${plural(f.views, "view")}</span>`
          : f.status === "calculated" ? `<span class="cell calc">${ICON.calc}Only in calculations (${fmt(f.calculatedOnly)})</span>`
          : `<span class="cell no">${ICON.cross}In no view</span>`}</li>`).join("")}</ul>`;
  }

  // All views pages without asking the server again
  function fieldPager() {
    const nav = $("#fieldsPager");
    if (!nav) return;
    pager(nav, { page: cmp.page, pages: Math.ceil(cmp.res.views.length / FIELD_PAGE) }, (page) => {
      cmp.page = page;
      $("#fc-panel-1").innerHTML = fieldViews();
      fieldPager();
      $("#fc-panel-1 .vlist").scrollIntoView({ block: "nearest" });
    });
  }

  $("#compareFields").addEventListener("click", () => openFields(false));
  $("#compareFieldsStart").addEventListener("click", () => openFields(true));
  $("#fieldsForm").addEventListener("submit", (e) => { e.preventDefault(); compareFields(); });
  fieldsInput.addEventListener("input", countFields);
  fieldsInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); compareFields(); }
  });
  $("#fieldsFile").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    if (file.size > 1_000_000) { fieldsError("The file is larger than 1 MB. Upload only the field list."); return; }
    const fields = readFieldFile(await file.text());          // read here, in the browser
    if (!fields.length) { fieldsError("The file has no field names."); return; }
    fieldsInput.value = fields.join("\n");
    countFields();
    compareFields();
  });

  const fieldsResult = $("#fieldsResult");
  fieldsResult.addEventListener("change", (e) => {
    const box = e.target.closest("[data-pick]");
    if (!box) return;
    if (box.checked && cmp.picked.size >= MAX_COMPARE) {
      box.checked = false;
      toast(`Choose up to ${MAX_COMPARE} views`);
      return;
    }
    if (box.checked) cmp.picked.add(box.dataset.pick);
    else cmp.picked.delete(box.dataset.pick);
    $("#pickCount").textContent = pickText();
    $("#comparePicked").disabled = !cmp.picked.size;
  });
  fieldsResult.addEventListener("click", (e) => {
    if (e.target.closest("#comparePicked")) {
      compareFields(cmp.res.views.map((v) => v.name).filter((n) => cmp.picked.has(n))).then(() => $("#fc-tab-0")?.click());
      return;
    }
    const exportButton = e.target.closest("#fieldsExport");
    if (exportButton) {
      exportButton.setAttribute("aria-busy", "true");
      download("/api/coverage/export", { method: "POST", body: { tables: cmp.tables, fields: cmp.fields } })
        .catch((err) => toast(err.message)).finally(() => exportButton.removeAttribute("aria-busy"));
      return;
    }
    const open = e.target.closest("[data-open]");
    if (open) {
      $("#fieldsDrawer").close();
      selectView(open.dataset.open);
    }
  });

  // ------------------------------------------------------------------------
  // Data products page
  // ------------------------------------------------------------------------
  const prods = { q: "", inMetadata: false, page: 1 };
  let prodSeq = 0;

  async function loadProducts() {
    const grid = $("#productGrid");
    if (!catalogueOn()) {
      grid.innerHTML = `<li class="wide"><div class="empty"><h3>No data product catalogue is loaded</h3>
        <p>Add a DataProductCatalogue file to the data folder and restart the app. Finding views and the table mapping work without it.</p></div></li>`;
      $$("#page-products .results-tools input").forEach((i) => { i.disabled = true; });
      return;
    }
    const seq = ++prodSeq;
    if (!grid.childElementCount) {
      grid.innerHTML = '<li><div class="product-card" aria-hidden="true"><span class="skeleton"></span><span class="skeleton"></span><span class="skeleton"></span></div></li>'.repeat(6);
    }
    const params = new URLSearchParams({ q: prods.q, inMetadata: prods.inMetadata, page: prods.page, pageSize: 24 });
    let res;
    try {
      res = await api(`/api/data-products?${params}`);
    } catch (err) {
      if (seq !== prodSeq) return;
      grid.innerHTML = "";
      showMessage($("#productsMessage"), { title: "The data products did not load", text: err.message, retry: loadProducts });
      return;
    }
    if (seq !== prodSeq) return;
    $("#productsMessage").hidden = true;
    prods.page = res.paging.page;
    $("#productTotal").textContent = `(${fmt(res.paging.total)})`;
    grid.innerHTML = res.items.length ? res.items.map((p) => `
      <li><article class="product-card">
        <div class="pc-top"><span class="dp-icon">${ICON.product}</span>${p.version ? `<span class="pill">Version ${esc(p.version)}</span>` : ""}</div>
        <h3><button type="button" class="card-link" data-product="${esc(p.name)}" aria-haspopup="dialog">${esc(p.title)}</button></h3>
        <div class="pc-id" title="${esc(p.name)}">${esc(p.name)}</div>
        <dl class="pc-stats">
          <div><dt>Entities</dt><dd>${fmt(p.entities)}</dd></div>
          <div><dt>Extraction</dt><dd>${fmt(p.extractionEntities)}</dd></div>
          <div><dt>Views in metadata</dt><dd>${fmt(p.viewsInMetadata)} of ${fmt(p.cdsViews)}</dd></div>
        </dl>
        <div class="pc-foot" aria-hidden="true">View details${ICON.chevron}</div>
      </article></li>`).join("")
      : `<li class="wide"><div class="empty"><h3>No data products match</h3><p>Try another product, entity or CDS view name, or clear the filters.</p>
          <button type="button" class="btn" id="clearProductFilters">Clear filters</button></div></li>`;
    $("#clearProductFilters")?.addEventListener("click", () => {
      Object.assign(prods, { q: "", inMetadata: false, page: 1 });
      $("#productFilter").value = "";
      $("#productKnown").checked = false;
      loadProducts();
    });
    $("#productCount").textContent = res.paging.total
      ? `Showing ${fmt(res.paging.start)}–${fmt(res.paging.end)} of ${plural(res.paging.total, "data product")}` : "";
    pager($("#productPager"), res.paging, (page) => { prods.page = page; loadProducts(); $("#productsTitle").scrollIntoView(); });
  }

  $("#productGrid").addEventListener("click", (e) => {
    const b = e.target.closest("[data-product]");
    if (b) openProduct(b.dataset.product);
  });
  $("#productFilter").addEventListener("input", debounce((e) => { prods.q = e.target.value.trim(); prods.page = 1; loadProducts(); }, 250));
  $("#productKnown").addEventListener("change", (e) => { prods.inMetadata = e.target.checked; prods.page = 1; loadProducts(); });

  // ------------------------------------------------------------------------
  // Table mapping page
  // ------------------------------------------------------------------------
  const maps = { q: "", status: "active", sort: "ecc", page: 1 };
  const mapItems = new Map();
  let mapSeq = 0;

  async function loadMappings() {
    const seq = ++mapSeq;
    const body = $("#mapRows");
    if (!body.children.length) body.innerHTML = '<tr><td colspan="5"><span class="skeleton"></span></td></tr>';
    const params = new URLSearchParams({ q: maps.q, status: maps.status, sort: maps.sort, page: maps.page, pageSize: 25 });
    let res;
    try {
      res = await api(`/api/mappings?${params}`);
    } catch (err) {
      if (seq !== mapSeq) return;
      body.innerHTML = "";
      showMessage($("#mapMessage"), { title: "The mappings did not load", text: err.message, retry: loadMappings });
      return;
    }
    if (seq !== mapSeq) return;
    $("#mapMessage").hidden = true;
    mapItems.clear();
    res.items.forEach((m) => mapItems.set(m.ecc, m));
    body.innerHTML = res.items.length ? res.items.map((m) => `
      <tr class="${m.status}" data-ecc="${esc(m.ecc)}">
        <td data-label="ECC table to S/4HANA tables"><span class="map-flow"><span class="obj src">${esc(m.ecc)}</span>
          <span class="map-arrow">${ICON.arrow}</span><span class="sr">maps to</span>
          <span class="s4-list">${m.s4.map((t) => `<span class="obj tgt">${esc(t)}</span>`).join("")}</span></span>
          ${m.status === "retired" ? '<span class="status-tag">Retired</span>' : ""}</td>
        <td data-label="Note" class="note-cell">${esc(m.note) || '<span class="fine">No note</span>'}</td>
        <td data-label="Views" class="n">${fmt(m.views)}</td>
        <td data-label="Last change" class="changed"><b>${esc(m.changedBy || "Not recorded")}</b>${esc(when(m.changedAt))}</td>
        <td><div class="row-actions">
          ${m.status === "active" ? '<button type="button" class="btn" data-act="edit">Edit</button>' : ""}
          <button type="button" class="btn" data-act="history">History</button>
          <button type="button" class="btn" data-act="${m.status === "active" ? "retire" : "restore"}">${m.status === "active" ? "Retire" : "Restore"}</button>
        </div></td>
      </tr>`).join("")
      : `<tr><td colspan="5"><div class="empty"><h3>${maps.q ? "No mappings match your search" : maps.status === "retired" ? "No retired mappings" : "No mappings yet"}</h3>
         <p>${maps.q ? "Try a different table name or clear the search." : "Add a mapping when S/4HANA replaced, merged or split an ECC table."}</p></div></td></tr>`;
    $$("#mapRows [data-act]").forEach((b) => b.setAttribute("aria-label", `${b.textContent} ${b.closest("tr").dataset.ecc}`));
    $("#mapCount").textContent = res.paging.total
      ? `Showing ${fmt(res.paging.start)}–${fmt(res.paging.end)} of ${plural(res.paging.total, "mapping")}` : "";
    pager($("#mapPager"), res.paging, (page) => { maps.page = page; loadMappings(); });
  }

  $("#mapRows").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-act]");
    if (!b) return;
    const m = mapItems.get(b.closest("tr").dataset.ecc);
    if (b.dataset.act === "edit") openMapDialog(m);
    else if (b.dataset.act === "history") openHistory(m.ecc, 1);
    else {
      const retire = b.dataset.act === "retire";
      const ok = await confirmDialog(retire ? `Retire the mapping for ${m.ecc}?` : `Restore the mapping for ${m.ecc}?`,
        retire ? "Searches will treat it as an unmapped table. You can restore it at any time." : "Searches will use this mapping again.",
        retire ? "Retire" : "Restore");
      if (!ok) return;
      try {
        await api(`/api/mappings/${encodeURIComponent(m.ecc)}/${b.dataset.act}`, { method: "POST", body: { version: m.version, changedBy: store.get("cdsFinder.name") } });
        toast(retire ? `${m.ecc} retired` : `${m.ecc} restored`);
        refreshAfterChange();
      } catch (err) {
        showMessage($("#mapMessage"), { title: "The change was not saved", text: err.message });
        loadMappings();
      }
    }
  });

  function refreshAfterChange() {
    loadMappings();
    loadMeta();
    detailCache.clear();
  }

  $("#statusFilter").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    $$("#statusFilter button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    maps.status = b.dataset.value;
    maps.page = 1;
    loadMappings();
  });
  $("#mapFilter").addEventListener("input", debounce((e) => { maps.q = e.target.value.trim(); maps.page = 1; loadMappings(); }, 300));
  $("#mapSort").addEventListener("change", (e) => { maps.sort = e.target.value; maps.page = 1; loadMappings(); });
  $("#exportMappings").addEventListener("click", () => download(`/api/mappings/export?status=${maps.status}`).catch((err) => toast(err.message)));

  // Add or edit dialog
  let editing = null;
  const usageEl = Object.assign(document.createElement("p"), { className: "usage", id: "mUsage" });
  $("#mS4Help").after(usageEl);

  const showUsage = debounce(async () => {
    const tables = splitTables($("#mS4").value).filter(isName);
    if (!tables.length || !meta?.ready) { usageEl.textContent = ""; return; }
    try {
      const res = await api(`/api/tables/usage?names=${encodeURIComponent(tables.join(","))}`);
      usageEl.className = `usage ${res.total ? "" : "none"}`;
      usageEl.textContent = res.total ? `${plural(res.total, "view")} read ${tables.length > 1 ? "these tables" : "this table"}.`
        : `No view reads ${tables.length > 1 ? "these tables" : "this table"} in the loaded metadata. Check the spelling.`;
    } catch { usageEl.textContent = ""; }
  }, 300);
  $("#mS4").addEventListener("input", showUsage);

  function openMapDialog(m = null) {
    editing = m;
    $("#mapDialogTitle").textContent = m ? `Edit mapping for ${m.ecc}` : "Add mapping";
    $("#mEcc").value = m?.ecc || "";
    $("#mEcc").readOnly = Boolean(m);
    $("#mS4").value = m ? m.s4.join("; ") : "";
    $("#mNote").value = m?.note || "";
    $("#mBy").value = store.get("cdsFinder.name");
    $("#mapFormError").hidden = true;
    usageEl.textContent = "";
    $("#mapDialog").showModal();
    (m ? $("#mS4") : $("#mEcc")).focus();
    if (m) showUsage();
  }

  $("#addMapping").addEventListener("click", () => openMapDialog());
  $("#mapForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const error = $("#mapFormError");
    const ecc = $("#mEcc").value.trim().toUpperCase();
    const s4 = splitTables($("#mS4").value);
    const fail = (text, el) => { error.textContent = text; error.hidden = false; el?.focus(); };
    if (!isName(ecc)) return fail("Enter a valid ECC table name: letters, digits, _ and /, up to 30 characters.", $("#mEcc"));
    if (!s4.length) return fail("Enter at least one S/4HANA table.", $("#mS4"));
    const bad = s4.find((t) => !isName(t));
    if (bad) return fail(`${bad} is not a valid table name.`, $("#mS4"));
    const changedBy = $("#mBy").value.trim();
    store.set("cdsFinder.name", changedBy);
    const save = $("#mapSave");
    save.setAttribute("aria-busy", "true");
    try {
      const note = $("#mNote").value.trim();
      if (editing) await api(`/api/mappings/${encodeURIComponent(ecc)}`, { method: "PUT", body: { s4, note, version: editing.version, changedBy } });
      else await api("/api/mappings", { method: "POST", body: { ecc, s4, note, changedBy } });
      $("#mapDialog").close();
      toast(`Mapping for ${ecc} saved`);
      refreshAfterChange();
    } catch (err) {
      if (err.status === 409 && err.current && editing) {
        editing = err.current;
        $("#mS4").value = err.current.s4.join("; ");
        $("#mNote").value = err.current.note;
      }
      fail(err.message);
    } finally {
      save.removeAttribute("aria-busy");
    }
  });

  // History dialog
  const ACTIONS = { create: "Created", update: "Changed", retire: "Retired", restore: "Restored", import: "Imported" };
  async function openHistory(ecc, page) {
    const dlg = $("#historyDialog");
    $("#historyTitle").textContent = `History of ${ecc}`;
    if (!dlg.open) { $("#historyList").innerHTML = '<li><span class="skeleton"></span></li>'; dlg.showModal(); }
    try {
      const res = await api(`/api/mappings/${encodeURIComponent(ecc)}/history?page=${page}&pageSize=20`);
      const show = (s) => s ? `<span class="code">${esc(s.s4.join(", "))}</span>${s.note ? ` · ${esc(s.note)}` : ""}${s.status === "retired" ? " · retired" : ""}` : "nothing";
      $("#historyList").innerHTML = res.items.map((h) => `
        <li><span class="when">${esc(when(h.changedAt))}</span>
          <div class="what"><b>${ACTIONS[h.action] || h.action}</b> by ${esc(h.changedBy || "someone not recorded")}
            <div class="diff">${h.old && h.action !== "retire" && h.action !== "restore" ? `${show(h.old)} → ` : ""}${show(h.new)}</div></div></li>`).join("")
        || '<li class="fine">No changes recorded.</li>';
      pager($("#historyPager"), res.paging, (p) => openHistory(ecc, p));
    } catch (err) {
      $("#historyList").innerHTML = `<li class="form-error">${esc(err.message)}</li>`;
    }
  }

  // Import dialog
  let importRows = null;
  function parseCsv(text) {
    const lines = text.replace(/^﻿/, "").split(/\r?\n/).filter((l) => l.trim() && !l.trimStart().startsWith("#"));
    const header = lines.shift() || "";
    const delim = [",", ";", "\t", "|"].find((d) => header.split(d).some((h) => h.toUpperCase().includes("ECC")) && header.includes(d)) || ",";
    const split = (line) => {
      const out = [];
      let cur = "", quoted = false;
      for (let i = 0; i < line.length; i++) {
        const c = line[i];
        if (quoted) {
          if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (c === '"') quoted = false; else cur += c;
        } else if (c === '"') quoted = true;
        else if (c === delim) { out.push(cur); cur = ""; } else cur += c;
      }
      out.push(cur);
      return out.map((v) => v.trim());
    };
    const cols = split(header).map((h) => h.toUpperCase().replace(/[^A-Z0-9]/g, ""));
    const find = (...names) => cols.findIndex((c) => names.includes(c));
    const ecc = find("ECCTABLE", "ECC");
    const s4 = find("S4TABLES", "S4TABLE", "S4", "S4HANATABLES", "S4HANATABLE");
    const note = find("NOTE", "NOTES", "COMMENT", "DESCRIPTION");
    if (ecc < 0 || s4 < 0) throw new Error("The file needs the columns ECC_TABLE and S4_TABLES in its first line.");
    return lines.map(split).map((r) => ({ ecc: r[ecc] || "", s4: r[s4] || "", note: note >= 0 ? (r[note] || "").slice(0, 400) : "" }));
  }

  async function previewImport(apply) {
    const error = $("#importError");
    error.hidden = true;
    const res = await api("/api/mappings/import", { method: "POST", body: { rows: importRows, apply, changedBy: store.get("cdsFinder.name") } });
    const s = res.summary;
    const labels = { new: "new", change: "changed", restore: "restored", same: "unchanged", error: "with errors" };
    const issues = res.rows.filter((r) => r.action !== "same");
    $("#importPreview").innerHTML = `
      <div class="import-summary">${Object.entries(labels).map(([k, l]) => `<span class="${k === "error" && s[k] ? "bad" : ""}">${fmt(s[k])} ${l}</span>`).join("")}</div>
      ${issues.length ? `<div class="import-rows"><table><thead><tr><th>Row</th><th>ECC table</th><th>S/4HANA tables</th><th>Result</th></tr></thead><tbody>
        ${issues.map((r) => `<tr><td>${r.row}</td><td class="code">${esc(r.ecc)}</td><td class="code">${esc(r.s4.join("; "))}</td>
          <td class="${r.action === "error" ? "err" : ""}">${esc(r.message || labels[r.action])}</td></tr>`).join("")}</tbody></table></div>`
        : '<p class="help">Everything in the file already matches the stored mapping.</p>'}`;
    $("#importApply").disabled = apply || s.error > 0 || s.new + s.change + s.restore === 0;
    return res;
  }

  $("#importButton").addEventListener("click", () => {
    importRows = null;
    $("#importFile").value = "";
    $("#importPreview").innerHTML = "";
    $("#importError").hidden = true;
    $("#importApply").disabled = true;
    $("#importDialog").showModal();
  });
  $("#importFile").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    $("#importPreview").innerHTML = "";
    $("#importApply").disabled = true;
    if (!file) return;
    const error = $("#importError");
    try {
      if (file.size > 2_000_000) throw new Error("The file is larger than 2 MB. Split it into smaller files.");
      importRows = parseCsv(await file.text());
      if (!importRows.length) throw new Error("The file has no mapping rows.");
      if (importRows.length > 5000) throw new Error("The file has more than 5,000 rows. Split it into smaller files.");
      await previewImport(false);
    } catch (err) {
      importRows = null;
      error.textContent = err.message;
      error.hidden = false;
    }
  });
  $("#importForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!importRows) return;
    const b = $("#importApply");
    b.setAttribute("aria-busy", "true");
    try {
      const res = await previewImport(true);
      $("#importDialog").close();
      const s = res.summary;
      toast(`Import saved: ${fmt(s.new)} new, ${fmt(s.change)} changed, ${fmt(s.restore)} restored`);
      refreshAfterChange();
    } catch (err) {
      $("#importError").textContent = err.message;
      $("#importError").hidden = false;
    } finally {
      b.removeAttribute("aria-busy");
    }
  });

  $$("[data-close]").forEach((b) => b.addEventListener("click", () => b.closest("dialog").close()));
  $("#dataButton").addEventListener("click", () => $("#dataDialog").showModal());
  $("#helpButton").addEventListener("click", () => $("#dataDialog").showModal());

  // ------------------------------------------------------------------------
  // Find Views hero: the app's story, told on one canvas. An ECC table sends signals to the CDS
  // views that read it, the views are ranked P1, P2 and P3 and the best match is marked, then each
  // view is looked up in the data product catalogue. Which views have a data product changes from
  // run to run, because any view can have one, whatever its rank. Faint drifting dots sit behind it.
  // About 30 frames a second, only while the hero is on screen and the tab is visible; a still
  // picture when reduced motion is asked for.
  // ------------------------------------------------------------------------
  function heroNetwork() {
    const hero = $("#hero");
    const canvas = $("#heroCanvas");
    const ctx = canvas.getContext("2d");
    if (!ctx) return { show() {} };
    const still = matchMedia("(prefers-reduced-motion: reduce)");
    const CYCLE = 7000;                                     // one search, from ECC table to data products
    const PRODUCTS = [[0, 1], [1], [0, 2]];                 // the views with a data product, run by run
    const RANKS = [["P1", "#8FC93A"], ["P2", "#6AA6EC"], ["P3", "#B29CE9"]];
    const FONT = "600 12.5px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    const SMALL = "700 10.5px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    const REACH = 120;
    const state = { page: true, seen: true, tab: !document.hidden };
    let w = 0, h = 0, fade = 0, dots = [], story = null, raf = 0, last = 0;

    const clamp = (v) => Math.min(1, Math.max(0, v));
    const ease = (v) => (v < 0.5 ? 2 * v * v : 1 - (-2 * v + 2) ** 2 / 2);
    const span = (p, from, to) => clamp((p - from) / (to - from));        // 0 before, 1 after
    const node = (x, y, label, tag = "") => {
      ctx.font = FONT;
      const width = ctx.measureText(label).width + (tag ? 52 : 34);
      return { x, y, label, tag, width };
    };

    function layout() {
      const box = hero.getBoundingClientRect();
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      w = box.width;
      h = box.height;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const speed = () => (Math.random() - 0.5) * 0.2;
      dots = Array.from({ length: Math.round(Math.max(12, Math.min(36, w / 40))) },
        () => ({ x: Math.random() * w, y: Math.random() * h, vx: speed(), vy: speed(), r: 0.8 + Math.random() * 1.3 }));
      const range = document.createRange();                 // where the words end, not the text block
      fade = Math.max(...$$("#heroCopy > *").map((el) => { range.selectNodeContents(el); return range.getBoundingClientRect().right; })) - box.left;
      // the story sits to the right of the text, above the search card, when there is room for it
      const left = fade + 64, right = w - 40, top = 26, bottom = h - 92;
      const ecc = node(0, 0, "ECC table"), product = node(0, 0, "Data products"), view = node(0, 0, "CDS view", "P1");
      const room = right - left - ecc.width - view.width - product.width;
      if (room < 140 || bottom - top < 110) { story = null; return; }   // at least 70 pixels for each link
      const mid = (top + bottom) / 2, gap = Math.min(42, (bottom - top - 28) / 2), link = Math.min(170, room / 2);
      const x0 = left + (right - left - ecc.width - view.width - product.width - 2 * link) / 2;
      ecc.x = x0 + ecc.width / 2;
      ecc.y = mid;
      const vx = x0 + ecc.width + link + view.width / 2;
      product.x = vx + view.width / 2 + link + product.width / 2;
      product.y = mid;
      story = { ecc, product, views: RANKS.map(([tag, color], i) => ({ ...node(vx, mid + (i - 1) * gap, "CDS view", tag), color })) };
    }

    // A gentle curve from the right edge of one pill to the left edge of the next
    function curve(a, b) {
      const x0 = a.x + a.width / 2, x1 = b.x - b.width / 2, dx = (x1 - x0) * 0.45;
      return [x0, a.y, x0 + dx, a.y, x1 - dx, b.y, x1, b.y];
    }
    function point([x0, y0, c1x, c1y, c2x, c2y, x1, y1], t) {
      const u = 1 - t;
      return [u * u * u * x0 + 3 * u * u * t * c1x + 3 * u * t * t * c2x + t * t * t * x1,
              u * u * u * y0 + 3 * u * u * t * c1y + 3 * u * t * t * c2y + t * t * t * y1];
    }
    function link(c, done, color) {                         // dashed when waiting, solid behind the signal
      ctx.lineWidth = 1.2;
      ctx.setLineDash([4, 6]);
      ctx.strokeStyle = "rgba(255, 255, 255, 0.14)";
      ctx.beginPath();
      ctx.moveTo(c[0], c[1]);
      ctx.bezierCurveTo(c[2], c[3], c[4], c[5], c[6], c[7]);
      ctx.stroke();
      ctx.setLineDash([]);
      if (done <= 0) return;
      ctx.strokeStyle = color;
      ctx.beginPath();
      for (let i = 0; i <= 24; i++) {
        const [x, y] = point(c, (done * i) / 24);
        if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
      }
      ctx.stroke();
    }
    function signal(c, t) {
      if (t <= 0 || t >= 1) return;
      const [x, y] = point(c, ease(t));
      ctx.fillStyle = "rgba(143, 201, 58, 0.25)";
      ctx.beginPath();
      ctx.arc(x, y, 7, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = "#C2EA7E";
      ctx.beginPath();
      ctx.arc(x, y, 2.6, 0, Math.PI * 2);
      ctx.fill();
    }
    function pill(n, lit, color) {
      const height = 30, x0 = n.x - n.width / 2, y0 = n.y - height / 2, r = height / 2;
      ctx.beginPath();
      ctx.moveTo(x0 + r, y0);
      ctx.arcTo(x0 + n.width, y0, x0 + n.width, y0 + height, r);
      ctx.arcTo(x0 + n.width, y0 + height, x0, y0 + height, r);
      ctx.arcTo(x0, y0 + height, x0, y0, r);
      ctx.arcTo(x0, y0, x0 + n.width, y0, r);
      ctx.closePath();
      ctx.fillStyle = "rgba(7, 20, 36, 0.92)";
      ctx.fill();
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.35 + 0.65 * lit;
      ctx.strokeStyle = color;
      ctx.stroke();
      let x = x0 + 13;
      if (n.tag) {                                          // the priority tag, as in the results list
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.roundRect ? ctx.roundRect(x - 3, n.y - 8, 24, 16, 8) : ctx.rect(x - 3, n.y - 8, 24, 16);
        ctx.fill();
        ctx.font = SMALL;
        ctx.fillStyle = "#06101D";
        ctx.textBaseline = "middle";
        ctx.fillText(n.tag, x + 2, n.y + 0.5);
        x += 28;
      } else {
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(x, n.y, 3, 0, Math.PI * 2);
        ctx.fill();
        x += 9;
      }
      ctx.font = FONT;
      ctx.textBaseline = "middle";
      ctx.fillStyle = "#E8EEF3";
      ctx.fillText(n.label, x, n.y + 0.5);
      ctx.globalAlpha = 1;
    }
    function ring(n, t, color) {                            // a short pulse around a pill
      if (t <= 0 || t >= 1 || still.matches) return;
      ctx.globalAlpha = 0.55 * (1 - t);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      const grow = 10 * ease(t), height = 30 + grow, width = n.width + grow, r = height / 2;
      const x0 = n.x - width / 2, y0 = n.y - height / 2;
      ctx.beginPath();
      ctx.moveTo(x0 + r, y0);
      ctx.arcTo(x0 + width, y0, x0 + width, y0 + height, r);
      ctx.arcTo(x0 + width, y0 + height, x0, y0 + height, r);
      ctx.arcTo(x0, y0 + height, x0, y0, r);
      ctx.arcTo(x0, y0, x0 + width, y0, r);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }

    function drawDots(moving) {
      for (const d of dots) {
        if (!moving) break;
        d.x += d.vx;
        d.y += d.vy;
        if (d.x < -10) d.x = w + 10; else if (d.x > w + 10) d.x = -10;
        if (d.y < -10) d.y = h + 10; else if (d.y > h + 10) d.y = -10;
      }
      ctx.lineWidth = 1;
      for (let i = 0; i < dots.length; i++) {
        for (let j = i + 1; j < dots.length; j++) {
          const a = dots[i], b = dots[j], d = Math.hypot(a.x - b.x, a.y - b.y);
          if (d >= REACH) continue;
          ctx.strokeStyle = `rgba(150, 200, 110, ${((1 - d / REACH) * 0.12).toFixed(3)})`;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }
      ctx.fillStyle = "rgba(196, 226, 160, 0.4)";
      for (const d of dots) {
        ctx.beginPath();
        ctx.arc(d.x, d.y, d.r, 0, Math.PI * 2);
        ctx.fill();
      }
      if (fade > 0) {                                       // keep the text on a calm background
        const mask = ctx.createLinearGradient(0, 0, fade + 80, 0);
        mask.addColorStop(0, "rgba(0, 0, 0, 0.92)");
        mask.addColorStop(0.75, "rgba(0, 0, 0, 0.75)");
        mask.addColorStop(1, "rgba(0, 0, 0, 0)");
        ctx.globalCompositeOperation = "destination-out";
        ctx.fillStyle = mask;
        ctx.fillRect(0, 0, fade + 80, h);
        ctx.globalCompositeOperation = "source-over";
      }
    }

    function drawStory(p, run) {
      const { ecc, views, product } = story;
      const found = PRODUCTS[run % PRODUCTS.length];
      const out = 1 - span(p, 0.93, 1);                     // the scene settles before the next search
      const lime = `rgba(143, 201, 58, ${(0.55 * out).toFixed(3)})`;
      // 1. the ECC table reaches every CDS view that reads it
      const arrive = views.map((v, i) => {
        const t = span(p, 0.04 + i * 0.06, 0.3 + i * 0.06);
        link(curve(ecc, v), ease(t) * out, lime);
        signal(curve(ecc, v), t);
        return t;
      });
      // 2. the views are ranked and the best match is marked
      const ranked = span(p, 0.46, 0.52) * out;
      // 3. every view is looked up in the catalogue; the ones with a data product connect to it
      views.forEach((v, i) => {
        const go = span(p, 0.58 + i * 0.03, 0.78 + i * 0.03);
        if (found.includes(i)) {
          link(curve(v, product), ease(go) * out, lime);
          signal(curve(v, product), go);
        } else {
          link(curve(v, product), 0, lime);
        }
      });
      pill(ecc, 0.6 + 0.4 * out * (1 - span(p, 0.3, 0.4)), "#AEBBC8");
      views.forEach((v, i) => pill(v, arrive[i] >= 1 ? out : 0, v.color));
      ring(views[0], span(p, 0.46, 0.62), views[0].color);
      if (ranked > 0) {
        ctx.globalAlpha = ranked;
        ctx.font = SMALL;
        ctx.fillStyle = "#A6D85E";
        ctx.textBaseline = "middle";
        ctx.fillText("BEST MATCH", views[0].x - views[0].width / 2 + 6, views[0].y - 25);
        ctx.globalAlpha = 1;
      }
      pill(product, span(p, 0.8, 0.86) * out, "#8FC93A");
      ring(product, span(p, 0.82, 0.95), "#8FC93A");
    }

    function draw(time) {
      const moving = !still.matches;
      ctx.clearRect(0, 0, w, h);
      drawDots(moving);
      if (story) drawStory(moving ? (time % CYCLE) / CYCLE : 0.9, moving ? Math.floor(time / CYCLE) : 0);
    }

    function tick(time) {
      raf = requestAnimationFrame(tick);
      if (time - last < 33) return;
      last = time;
      draw(time);
    }

    function update() {
      const run = state.page && state.seen && state.tab && !still.matches;
      hero.classList.toggle("paused", !run);
      if (run && !raf) raf = requestAnimationFrame(tick);
      if (!run && raf) { cancelAnimationFrame(raf); raf = 0; }
    }

    new ResizeObserver(() => { layout(); draw(performance.now()); }).observe(hero);
    new IntersectionObserver(([entry]) => { state.seen = entry.isIntersecting; update(); }).observe(hero);
    document.addEventListener("visibilitychange", () => { state.tab = !document.hidden; update(); });
    still.addEventListener("change", () => { update(); draw(performance.now()); });
    update();
    return { show(on) { state.page = on; update(); } };
  }

  // ------------------------------------------------------------------------
  // Pages and links
  // ------------------------------------------------------------------------
  const PAGES = { find: "Find Views", mappings: "Table Mapping", products: "Data Products" };
  const LOADERS = { mappings: loadMappings, products: loadProducts };
  const loaded = new Set();
  const navIndicator = $("#navIndicator");
  let currentPage = null;
  let hero = null;

  // The highlight behind the current page's link slides to the page you open
  function moveIndicator(animate) {
    const current = $('.main-nav a[aria-current="page"]');
    if (!current) return;
    navIndicator.classList.toggle("animate", animate);
    navIndicator.style.width = `${current.offsetWidth}px`;
    navIndicator.style.transform = `translateX(${current.offsetLeft}px)`;
  }
  window.addEventListener("resize", debounce(() => moveIndicator(false), 100));

  function route() {
    const [path, query = ""] = location.hash.replace(/^#/, "").split("?");
    const name = path.replace(/^\//, "");
    const page = name in PAGES ? name : "find";
    for (const p of Object.keys(PAGES)) $(`#page-${p}`).hidden = p !== page;
    $$(".main-nav a").forEach((a) => (a.dataset.page === page ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
    moveIndicator(currentPage !== null);
    hero?.show(page === "find");
    if (currentPage !== null && page !== currentPage) window.scrollTo(0, 0);
    currentPage = page;
    document.title = `${PAGES[page]} · CDS View Finder`;
    if (page !== "find") {
      if (!loaded.has(page)) { loaded.add(page); LOADERS[page](); }
      return;
    }
    const tables = new URLSearchParams(query).getAll("t").slice(0, MAX_TABLES).map((t) => {
      const [ecc, s4 = ""] = t.split(":");
      return { ecc: ecc.trim().toUpperCase(), s4: splitTables(s4) };
    }).filter((t) => isName(t.ecc) && t.s4.every(isName));
    if (!tables.length || tablesKey(tables) === tablesKey(search.tables)) return;
    rowsEl.innerHTML = "";
    tables.forEach((t) => addRow(t.ecc, t.s4.join("; ")));
    Object.assign(search, { tables, priority: null, q: "", page: 1 });
    detailCache.clear();
    if (meta?.ready) runSearch();
  }

  window.addEventListener("popstate", route);
  window.addEventListener("hashchange", route);

  addRow();
  hero = heroNetwork();
  loadMeta().finally(() => {
    route();
    if (!location.hash.includes("t=")) $('[data-role="ecc"]', rowsEl)?.focus({ preventScroll: true });
  });
})();
