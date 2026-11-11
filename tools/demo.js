"use strict";

// Stands in for the server in the one-file demo. Every answer was recorded from the real app by
// tools/build_demo.py; lists are filtered, sorted and paged here the same way the server does it.
// Anything that was not recorded gets a short message instead, and nothing is ever saved.
(() => {
  const DATA = JSON.parse(document.getElementById("demo-data").textContent);
  const key = (tables) => (tables || []).map((t) => `${t.ecc}:${(t.s4 || []).join(";")}`).join(",");
  const json = (body, status = 200) =>
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  const file = ({ name, text }) =>
    new Response(text, { headers: { "Content-Type": "text/csv", "Content-Disposition": `attachment; filename="${name}"` } });
  const notHere = (detail, status = 400) => json({ detail }, status);
  const MSG = {
    search: `This demo only has the example tables${DATA.together ? `, one at a time or ${DATA.together}` : ""}. Try ${DATA.tryTables}, or run the app to search your own tables.`,
    fields: "This demo only has answers for the prepared list of fields. Clear the box and open Compare fields again to get it back, or run the app to compare your own fields.",
    pick: `This demo can compare only the first ${DATA.compareTop} views on the list. Run the app to compare any view.`,
    view: "The details of this view are not in this demo. Run the app to see them.",
    change: "Changes are switched off in this demo. Run the app to add or change mappings.",
  };

  // The same paging as the server: the page is kept within range, start and end count from 1
  function pageOf(items, page, size) {
    const pages = Math.max(1, Math.ceil(items.length / size));
    page = Math.min(Math.max(1, page), pages);
    const shown = items.slice((page - 1) * size, page * size);
    const first = (page - 1) * size;
    return { items: shown, paging: { page, pageSize: size, pages, total: items.length,
      start: shown.length ? first + 1 : 0, end: first + shown.length } };
  }

  // The same filters as the server. Counts per priority ignore the priority filter.
  let lastSearch = [];
  function search(b) {
    const full = DATA.search[key(b.tables)];
    if (!full) return notHere(MSG.search);
    lastSearch = b.tables;
    const q = (b.q || "").trim().toLowerCase();
    const counts = { 1: 0, 2: 0, 3: 0 };
    let kept = [];
    for (const v of full.results) {
      if (!b.includeCustom && v.custom) continue;
      if (b.withDataProduct && !v.dataProducts.length) continue;
      if (q && !v.name.toLowerCase().includes(q) && !v.description.toLowerCase().includes(q)) continue;
      counts[v.priority] += 1;
      if (b.priority == null || v.priority === b.priority) kept.push(v);
    }
    if (b.sort === "name") kept = [...kept].sort((x, y) => (x.name.toLowerCase() < y.name.toLowerCase() ? -1 : 1));
    const { items, paging } = pageOf(kept, b.page || 1, b.pageSize || 20);
    return json({ ...full, results: items, paging, priorities: full.priorities.map((p) => ({ ...p, count: counts[p.level] })) });
  }

  function coverage(b) {
    const cov = DATA.coverage[`${key(b.tables)}|${(b.fields || []).join(" ")}`];
    if (!cov) return notHere(MSG.fields);
    const comparison = cov.comparisons[(b.compare || []).join(",") + (b.driver ? `|${b.driver}` : "")];
    return comparison ? json({ ...cov.base, comparison }) : notHere(MSG.pick);
  }

  function mappings(p) {
    const status = p.get("status") || "active";
    const term = (p.get("q") || "").replace(/[^A-Za-z0-9_/ ]/g, "").trim().toUpperCase();
    const items = DATA.mappings[p.get("sort") === "changed" ? "changed" : "ecc"].filter((m) =>
      (status === "all" || m.status === status) &&
      (!term || m.ecc.includes(term) || m.note.toUpperCase().includes(term) || m.s4.some((t) => t.includes(term))));
    return json(pageOf(items, Number(p.get("page")) || 1, Number(p.get("pageSize")) || 25));
  }

  window.fetch = async (input, init = {}) => {
    const url = new URL(String(input), "http://demo.local");
    const path = url.pathname;
    const method = (init.method || "GET").toUpperCase();
    const b = init.body ? JSON.parse(init.body) : {};
    if (method === "GET" && path === "/api/meta") return json(DATA.meta);
    if (path === "/api/search") return search(b);
    if (path === "/api/search/export") return DATA.exports[key(b.tables)] ? file(DATA.exports[key(b.tables)]) : notHere(MSG.search);
    if (path === "/api/view") {
      const view = DATA.views[`${key(b.tables)}|${String(b.name).toUpperCase()}`];
      return view ? json(view) : notHere(MSG.view, 404);
    }
    if (path === "/api/coverage") return coverage(b);
    if (path === "/api/coverage/export") {
      const exp = DATA.coverageExports[`${key(b.tables)}|${(b.fields || []).join(" ")}`];
      return exp ? file(exp) : notHere(MSG.fields);
    }
    if (method !== "GET" && path.startsWith("/api/mappings")) return notHere(MSG.change);
    if (path === "/api/mappings") return mappings(url.searchParams);
    if (path === "/api/mappings/export") return file(DATA.mappingExports[url.searchParams.get("status") || "active"]);
    const history = /^\/api\/mappings\/(.+)\/history$/.exec(path);
    if (history) {
      const items = DATA.history[decodeURIComponent(history[1])] || [];
      return json(pageOf(items, Number(url.searchParams.get("page")) || 1, Number(url.searchParams.get("pageSize")) || 20));
    }
    if (path === "/api/tables/usage") {
      const usage = DATA.usage[url.searchParams.get("names") || ""];
      return usage ? json(usage) : notHere("Not in this demo.", 404);
    }
    return notHere("This is not part of the demo.", 404);
  };

  // Compare fields opens with the prepared list for the tables on screen. What the visitor typed is kept.
  const box = document.getElementById("fieldsInput");
  const prepared = new Set(Object.values(DATA.presets).map((p) => p.join("\n")));
  const typedTables = () => [...document.querySelectorAll("#tableRows .trow")].map((row) => ({
    ecc: row.querySelector('[data-role="ecc"]').value.trim().toUpperCase(),
    s4: [...new Set(row.querySelector('[data-role="s4"]').value.toUpperCase().split(/[\s,;+]+/).filter(Boolean))],
  })).filter((t) => t.ecc || t.s4.length);
  const prefill = (tables) => {
    const preset = DATA.presets[key(tables)];
    if (preset && (!box.value.trim() || prepared.has(box.value))) box.value = preset.join("\n");
  };
  document.getElementById("compareFields").addEventListener("click", () => prefill(lastSearch));
  document.getElementById("compareFieldsStart").addEventListener("click", () => prefill(typedTables()));
})();
