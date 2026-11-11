"""Build a one-file clickable demo of the app, for showing it without a server.

The real app runs in memory on a metadata folder (the bundled examples by default). This script
records its answers to everything a visitor can click: each table's search, the details of each
view, a prepared field comparison per table with every choice of up to three of the first views,
and the table mapping with its history and exports. It writes one HTML file holding the real page,
styles, script and logo, plus tools/demo.js, which answers the page from those recordings. Nothing
is invented: every answer in the file came from the app. Nothing a visitor does is saved.

    uv run python tools/build_demo.py
    uv run python tools/build_demo.py --data-dir data --tables MSEG ACDOCA VBUK --out demo.html
"""

from __future__ import annotations

import argparse
import base64
import itertools
import json
import re
import tempfile
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

from cds_finder.api import create_app
from cds_finder.coverage import MAX_COMPARE
from cds_finder.settings import PACKAGE_DIR, Settings

WEB = PACKAGE_DIR / "web"
HERE = Path(__file__).resolve().parent
PAGE = 100                  # the largest page the API serves
MAX_TABLES = 40             # without --tables, record every suggested table when there are at most this many
PRESET_FIELDS = 6           # fields in each prepared comparison


def key(tables: list[dict]) -> str:
    """The same key as tools/demo.js: ECC:S4;S4 per table, comma separated."""
    return ",".join(f"{t['ecc']}:{';'.join(t.get('s4', []))}" for t in tables)


def download(response) -> dict:
    name = re.search(r'filename="([^"]+)"', response.headers["content-disposition"]).group(1)
    return {"name": name, "text": response.text}


def preset(details: list[dict], s4: set[str]) -> list[str]:
    """Fields for the prepared comparison, taken from the views themselves: the fields most views
    read from your tables, then the ones the fewest views read, so the comparison shows both the
    best view and views that must be used together."""
    readers = Counter()
    for d in details:
        readers.update({s["field"] for f in d["fields"] for s in f["sources"]
                        if s["table"] in s4 and s["field"] and not s["calculated"]})
    common = [f for f, _ in sorted(readers.items(), key=lambda kv: (-kv[1], kv[0]))]
    picked = common[:PRESET_FIELDS - 2]
    picked += [f for f in reversed(common) if f not in picked][:PRESET_FIELDS - len(picked)]
    return picked


def record_search(c: TestClient, data: dict, tables: list[dict], details_cap: int) -> list[dict]:
    k = key(tables)
    body = {"tables": tables, "pageSize": PAGE}
    res = c.post("/api/search", json=body).json()
    for page in range(2, res["paging"]["pages"] + 1):
        res["results"] += c.post("/api/search", json={**body, "page": page}).json()["results"]
    data["search"][k] = res
    data["exports"][k] = download(c.post("/api/search/export", json={"tables": tables}))
    details = []
    for v in res["results"][:details_cap]:
        d = c.post("/api/view", json={"tables": tables, "name": v["name"]}).json()
        data["views"][f"{k}|{v['name'].upper()}"] = d
        details.append(d)
    return details


def record_comparison(c: TestClient, data: dict, tables: list[dict], fields: list[str], top: int) -> None:
    body = {"tables": tables, "fields": fields}
    base = c.post("/api/coverage", json=body).json()
    comparisons = {"": base.pop("comparison")}
    names = [v["name"] for v in base["views"][:top]]
    for size in range(1, MAX_COMPARE + 1):
        for chosen in itertools.combinations(names, size):
            comparisons[",".join(chosen)] = c.post("/api/coverage", json={**body, "compare": list(chosen)}).json()[
                "comparison"]
    # every P1/P2/P3 choice under By table, with each table as the driver, as the page sends it:
    # views in table order without repeats, and the driver table's view
    tops = [[p["view"]["name"] for p in t["picks"]] for t in base["byTable"] if t["picks"]]
    for choice in itertools.product(*tops):
        chosen = list(dict.fromkeys(choice))
        if len(chosen) > MAX_COMPARE:
            continue
        for driver in chosen:
            answer = c.post("/api/coverage", json={**body, "compare": chosen, "driver": driver}).json()
            comparisons[f"{','.join(chosen)}|{driver}"] = answer["comparison"]
    k = f"{key(tables)}|{' '.join(fields)}"
    data["coverage"][k] = {"base": base, "comparisons": comparisons}
    data["coverageExports"][k] = download(c.post("/api/coverage/export", json=body))
    data["presets"][key(tables)] = fields


def record_mappings(c: TestClient, data: dict) -> None:
    for sort in ("ecc", "changed"):
        items, page, pages = [], 1, 1
        while page <= pages:
            res = c.get("/api/mappings", params={"status": "all", "sort": sort, "page": page, "pageSize": PAGE}).json()
            items += res["items"]
            pages = res["paging"]["pages"]
            page += 1
        data["mappings"][sort] = items
    for m in data["mappings"]["ecc"]:
        history = c.get(f"/api/mappings/{m['ecc']}/history", params={"pageSize": PAGE})
        data["history"][m["ecc"]] = history.json()["items"]
        names = ",".join(m["s4"])
        data["usage"][names] = c.get("/api/tables/usage", params={"names": names}).json()
    for status in ("active", "retired", "all"):
        data["mappingExports"][status] = download(c.get("/api/mappings/export", params={"status": status}))


def record(data_dir: Path, tables: list[str], combos: list[list[str]], details_cap: int, top: int) -> dict:
    data = {k: {} for k in ("search", "exports", "views", "coverage", "coverageExports", "presets", "mappings",
                            "history", "usage", "mappingExports")}
    with tempfile.TemporaryDirectory() as tmp, TestClient(create_app(Settings(
            data_dir=data_dir, db_path=Path(tmp) / "cds_finder.db", log_level="WARNING"))) as c:
        data["meta"] = c.get("/api/meta").json()
        if not data["meta"]["ready"]:
            raise SystemExit(f"No view metadata in {data_dir}.")
        suggested = data["meta"]["suggestions"]
        if not tables:
            if len(suggested) > MAX_TABLES:
                raise SystemExit(f"{len(suggested)} tables can be searched. Name the ones to record with --tables.")
            tables = suggested
        sets = [[{"ecc": t.upper(), "s4": []}] for t in tables]
        sets += [[{"ecc": t.upper(), "s4": []} for t in combo] for combo in combos]
        for s in sets:
            details = record_search(c, data, s, details_cap)
            s4 = {t for i in data["search"][key(s)]["inputs"] for t in i["s4"]}
            fields = preset(details, s4)
            if fields:
                record_comparison(c, data, s, fields, top)
        # the single tables with the most views: named in the demo note, and the first one is used when
        # Compare fields is opened before any search (fields written with their table)
        mapped = data["meta"]["mappings"]
        singles = sorted((s[0]["ecc"] for s in sets if len(s) == 1 and key(s) in data["presets"]),
                         key=lambda t: (-data["search"][f"{t}:"]["viewsFound"], t not in mapped))
        if singles:
            record_comparison(c, data, [], [f"{singles[0]}-{f}" for f in data["presets"][f"{singles[0]}:"]], top)
        record_mappings(c, data)
    data["compareTop"] = top
    data["tryTables"] = ", ".join(singles[:4]) or "another table"
    pairs = [" with ".join(t["ecc"] for t in s) for s in sets if len(s) > 1 and key(s) in data["presets"]]
    data["together"] = ", ".join(pairs)
    return data


def build(data: dict) -> str:
    page = (WEB / "index.html").read_text(encoding="utf-8")
    css = (WEB / "app.css").read_text(encoding="utf-8")
    logo = base64.b64encode((WEB / "brand-logo.svg").read_bytes()).decode()
    icon = base64.b64encode((WEB / "icon.svg").read_bytes()).decode()
    note = ('<div class="notice demo-note"><h2>Demo</h2><p>This page answers from the app\'s bundled example '
            f'files, recorded when the demo was built. Try {data["tryTables"]}. '
            'Nothing you do here is saved.</p></div>')
    swaps = [
        ('<link rel="icon" href="/assets/icon.svg" type="image/svg+xml">',
         f'<link rel="icon" href="data:image/svg+xml;base64,{icon}" type="image/svg+xml">'),
        ('<link rel="stylesheet" href="/assets/app.css">', f"<style>\n{css}\n{DEMO_CSS}</style>"),
        ('<script src="/assets/app.js" defer></script>\n', ""),
        ('<img class="brand-logo" id="brandLogo" alt="Deloitte" hidden>',
         f'<img class="brand-logo" id="brandLogo" alt="Deloitte" src="data:image/svg+xml;base64,{logo}">'),
        ('id="brandDivider" aria-hidden="true" hidden>', 'id="brandDivider" aria-hidden="true">'),
        ('<div class="notice" id="setupNotice" hidden>',
         f'{note}\n          <div class="notice" id="setupNotice" hidden>'),
        ('<div id="mapMessage" class="message" role="alert" hidden></div>',
         '<div class="notice demo-note"><h2>Demo</h2><p>Changes are switched off in this demo. Run the app to add '
         'or change mappings.</p></div>\n        <div id="mapMessage" class="message" role="alert" hidden></div>'),
    ]
    for old, new in swaps:
        if page.count(old) != 1:
            raise SystemExit(f"index.html has changed; update build_demo.py: {old[:60]}")
        page = page.replace(old, new)
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    scripts = (f'<script type="application/json" id="demo-data">{blob}</script>\n'
               f'<script>\n{(HERE / "demo.js").read_text(encoding="utf-8")}</script>\n'
               f'<script>\n{(WEB / "app.js").read_text(encoding="utf-8")}</script>\n</body>')
    return page.replace("</body>", scripts)


DEMO_CSS = """.notice.demo-note { border-color: var(--green-line); background: #F1F8EE; }
.notice.demo-note h2 { color: var(--green-dark); }
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a one-file clickable demo of the app.")
    parser.add_argument("--data-dir", type=Path, default=PACKAGE_DIR.parent / "examples")
    parser.add_argument("--tables", nargs="*", default=[], help="ECC tables to record (default: every suggested one)")
    parser.add_argument("--together", nargs="*", default=["MSEG+MKPF", "VBAK+VBAP", "BKPF+BSEG"],
                        help="Tables searched together, for example MSEG+MKPF")
    parser.add_argument("--details", type=int, default=60, help="View details recorded per search")
    parser.add_argument("--compare-top", type=int, default=7, help="Views that can be compared side by side")
    parser.add_argument("--out", type=Path, default=Path("cds-finder-demo.html"))
    args = parser.parse_args()
    data = record(args.data_dir, args.tables, [c.split("+") for c in args.together], args.details, args.compare_top)
    args.out.write_text(build(data), encoding="utf-8")
    print(f"Wrote {args.out} ({args.out.stat().st_size / 1_000_000:.1f} MB): "
          f"{len(data['search'])} searches, {len(data['views'])} view details, "
          f"{sum(len(c['comparisons']) for c in data['coverage'].values())} comparisons")


if __name__ == "__main__":
    main()
