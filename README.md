# CDS View Finder

Part of the BW-to-BDC Accelerator. Enter one or more ECC tables and get every S/4HANA view that reads the matching S/4HANA tables, ranked for migration, with a plain-language note for each view and the full field list.

The ranking is a fixed set of rules (no AI), so the same input always gives the same order and every position can be explained. The app is a FastAPI service with a built-in web page. The table mapping lives in SQLite and is maintained by users in the app; the view metadata comes from CSV extracts.

## How views are ranked

Every view gets a priority:

| Priority | Label | Rule |
|---|---|---|
| 1 | Extraction and delta ready | The view supports data extraction **and** delta loads |
| 2 | Standard SAP view | The view name starts with `I_` or `C_` |
| 3 | Other view | Everything else, including custom views |

Within a priority, views are ordered by these rules, and the first rule that tells two views apart decides:

1. Reads more of the tables you entered
2. Same level of detail as your table (all of its key fields come from your tables), then partly, then not at all
3. Data extraction enabled
4. Released by SAP
5. Reads your table directly rather than through other views
6. More fields from your tables
7. Fewer other tables mixed in
8. Name, A to Z

The rank shown for a view is its position in this full order. It stays the same when you filter or sort the list.

### Business notes

Each view comes with a note written for business readers. It never shows table names, field names or technical terms:

- **Why this priority**, for example "Priority 1 because it supports both data extraction and delta loads, so after one full load only new and changed records need to be transferred."
- **What it supports:** data extraction, delta loads, released by SAP.
- **How it fits a migration**, for example "Strong candidate to replace your table. Run one full load, then keep the data current with delta loads."
- **Before you use it:** points to check, such as a different level of detail, a view built in your own system, a view not released by SAP, or extra tables mixed in.

The technical detail (tables read, data definition, every field and the table field it comes from) is shown below the note.

## Quick start

You need Python 3.10 or newer and [uv](https://docs.astral.sh/uv/).

```bash
cd cds-view-finder
uv run cds-finder serve --data-dir examples
```

Open http://localhost:8000. The `examples` folder holds a small set of illustrative metadata files with the real column layouts, so you can try the app before loading your own extracts. For real use, put your extracts in `data/` and start without `--data-dir`:

```bash
uv run cds-finder serve
```

Without uv: `python3 -m venv .venv && . .venv/bin/activate && pip install . && cds-finder serve`.

## Metadata files

Put these files in the metadata folder (`data/` by default). File names only need to contain these words, in any case. Restart the app after replacing them.

| File | Required | Columns | Used for |
|---|---|---|---|
| `CDS_FIELD_ORIGIN` | Yes | DDLNAME, LEVEL, ENTITY_NAME, ELEMENT_NAME, BASE_OBJECT, BASE_FIELD, IS_CALCULATED | Which tables and fields each view reads |
| `IXTRCTNENBLDVW` | Yes | DATAEXTRACTIONVIEWNAME, DATAEXTRACTIONVIEWDESCRIPTION, ISSAPRELEASEDVIEW, DELTACHGDATACAPTUREISSUPPORTED | Extraction, delta and release status |
| `DD03N` | Recommended | STRUCOBJN, FIELDNAME, KEYFLAG | Key fields of each view, for the level of detail check |
| `DDDDLSRCT` | Optional | DDLNAME, DDLANGUAGE, AS4LOCAL, DDTEXT | Description of each view, used when the extraction file has none |
| `DD08B` | Optional | STRUCOBJN, ASSOCIATIONNAME, ASSOCNAME_RAW, STRUCOBJN_T, CARD_MIN, CARD_MAX, ON_SOURCE, AS4LOCAL | Associations each view defines, shown in the Details tab |
| `DataProductCatalogue` | Optional | Product, Entity, CDS view, Entity type, Extraction, Root, Size, Elements, Keys | Which data products use each view, with their keys and extraction details |

The reader is forgiving: column names may differ in case, spaces and underscores (`DELTACHANGEDCAPTUREISSUPPORTED` and `STRUCOBJNM` also work); comma, semicolon, tab and SE16 pipe layouts work, with or without title lines; UTF-8 and Windows-1252 both work; flags count as true for `X`, `TRUE`, `1` or `YES`.

DD03N rows with `KEYFLAG = X` are joined on `DDLNAME = STRUCOBJN` and `ELEMENT_NAME = FIELDNAME`. Client fields (MANDT) are ignored.

DDDDLSRCT rows are joined on `DDLNAME`. Only the active version (`AS4LOCAL = A`) is used, and English text wins when there are several languages. The extraction file's description still comes first; DDDDLSRCT only fills the views that have none.

DD08B rows are joined on `STRUCOBJN` = the view's CDS or DDL name, active version only. Each view shows only the associations it defines itself, not those of the views it builds on. The name comes from `ASSOCNAME_RAW` (SAP's spelling), the cardinality from `CARD_MIN` and `CARD_MAX` (an open upper bound shows as `*`), and the ON condition from `ON_SOURCE` when the system fills it. Without a DD08B file the Details tab looks as before.

If the required files are missing, the app still starts: the page explains that the metadata is not loaded, searches return `503`, and the table mapping can still be maintained.

To see what was read, with row counts and rows that could not be joined:

```bash
uv run cds-finder check --data-dir data
```

## The page

- **Header:** the Deloitte logo and the app name (CDS & Data Product Compass), the three pages (Find Views, Table Mapping, Data Products) with a highlight that slides to the page you open, the data status and the help button. Click either of the last two for the ranking rules, the loaded files and any notes on the data, such as a missing key fields file or repeated catalogue rows. Below 1200 pixels the pages move to a second row.
- **Find Views:** a short dark hero ("From ECC Tables to the Right CDS View.") with the search card rising into its lower edge. Enter ECC tables, the source (the S/4HANA table, the target, comes from the table mapping unless you type one). The best ranked view is marked "Best match"; extraction and delta show as green pills when available. Below the search card are the ranking rules (P1 green, P2 blue, P3 purple) and the results table with rank, priority, CDS view, description, data product, extraction and delta. The search box, the filter button (sort, custom views, with data product), Compare fields and the export button sit above the table; priorities are tabs; pages are numbered.
- **Details panel:** selecting a view opens a panel on the right with Show fields and Compare fields buttons and the tabs Overview, Fields, Migration and Details. On narrower screens it opens over the list and closes with Escape.
- **Associations:** with a DD08B file, the Details tab lists the associations the view defines: name, the view it points to (with its description when known), cardinality, and the ON condition when DD08B has it.
- **Data product drawer:** selecting a data product anywhere opens a drawer from the right with the tabs Overview, Keys, Extraction and Details, and how many of the product's CDS views are in the loaded view metadata.
- **Table Mapping:** each row shows the ECC table (grey, the source), an arrow and its S/4HANA tables (green, the target).
- **Data Products:** every product in the catalogue as a card with its entities, how many are enabled for extraction and how many of its CDS views are in the loaded view metadata. Search by product, entity or CDS view name, or show only products with views in the metadata.

Without a catalogue file, the Data Products page says so and explains how to add one; the rest of the app works as before.

### Look and motion

Navy and black frame the app, Deloitte green is the accent, and the work happens on light surfaces with soft shadows. The type is the system font (San Francisco on a Mac).

| Kind | Duration | Used for |
|---|---|---|
| Micro | 160 ms | Hover, focus, pressing a button, switching tabs |
| Standard | 240 ms | Pages, results, dialogs and the details panel fading in |
| Slow | 320 ms | Drawers, the page highlight in the header |
| Continuous | about 30 frames a second on one canvas | Only the Find Views hero, which shows what the app does: an ECC table sends signals to the CDS views that read it, the views are ranked P1, P2 and P3 and the best match is marked, then each view is looked up in the data product catalogue. Which views have a data product changes from run to run (P1 and P2, then only P2, then P1 and P3), because any view can have one whatever its rank. One run takes seven seconds. Faint drifting dots and a slowly moving gradient sit behind it |

- The hero stops drawing when it is scrolled out of view, when another page is open or the browser tab is hidden. With "reduce motion" switched on in the operating system it is a still picture and nothing else moves either.
- Rows of the results and mapping tables are never animated, and hover feedback uses shadows and colour rather than moving cards, so text never blurs. Something that fades in ends with no transform left on it.

### Logo

The header shows the official Deloitte logo (`cds_finder/web/brand-logo-original.svg`). The dark header uses `cds_finder/web/brand-logo.svg`, the same file with the lettering in white and the green dot unchanged, which is the usual form on dark backgrounds. If your brand team has an official reversed (white) logo file, put it in the data folder as `brand-logo.svg` or point `CDS_FINDER_BRAND_LOGO` at it, and it replaces the bundled one.

## Data products

With a `DataProductCatalogue` file in the metadata folder (the name may also be spelled `DataProductCatalog`), every view in the results shows the data products that use it.

- **Matching is exact.** A view is linked to a data product only when its name appears in the catalogue's CDS view column, compared in upper case against the view's entity name and its data definition name. Nothing is guessed. A view without a catalogue row is shown as "No data product".
- **One view, several products or entities.** All of them are shown. For example, I_CURRENCY is linked through both the TCURC and TCURX entities of the HANA currency product.
- **Repeated rows** (same product, entity and CDS view) are read once; rows without a product name are skipped. `cds-finder check` reports both.
- **Filter:** the "With data product" switch above the list shows only views that belong to a data product, with their number next to it. The priority counts and the CSV export follow the switch, and the ranks stay the same. The switch only appears when a catalogue is loaded.
- **Details:** select a data product to open a side panel with its entities, the ones used by the selected view first. Each entity shows its keys, whether extraction is enabled, its size category, number of fields, CDS view, root flag, object type and whether its CDS view is in the loaded view metadata. An empty Extraction cell is shown as "Not stated".
- **Browse the whole catalogue** on the Data Products page. The list is built once at start-up from the catalogue file, so searching, filtering and paging thousands of products takes a few milliseconds.

The catalogue is optional. Without it, or if it cannot be read, the app works as before and the log says why. Save it as CSV (comma or semicolon); Excel's "CSV UTF-8" works.

## Compare fields

"Compare fields" answers which view gives you the fields you need. Open it from the results toolbar after a search (it uses the tables you searched), or from the search card (it uses the tables typed there, if any).

- **Enter the fields:** type or paste many at once (a column copied from Excel works), or upload a CSV or text file with the list.
  - Write a field alone (`NETWR`) to look for it in the tables you searched, or with its table (`VBAP-NETWR`) to look anywhere.
  - Two columns pasted from Excel, or a CSV with `TABLE` and `FIELD` columns, are read as table and field.
  - Up to 500 fields and 10 tables at a time.
- **Matching:** each field is looked for in the S/4HANA tables its ECC table maps to, using the table mapping. A view provides a field when one of its fields is a copy of it, read directly or through other views. A field the view only uses inside a calculation is shown separately and doesn't count.
- **Priority comes first.** P1 views are always considered before P2, and P2 before P3, for one table or several:
  - the best view is the P1 view with the most fields (equal counts follow the recommended order); only when no P1 view has any of the fields is it a P2 view, then a P3 view. When a lower priority view has more fields, the summary names it, so nothing is hidden
  - the views used together (at most four) are taken from P1 views first, adding a P2 view and then a P3 view only for fields no higher priority view provides
  - "All views" lists P1 views first, then P2 and P3, each with the most fields first; the export follows the same order
- **Summary:** the best view, the views to use together and how to join them, and the fields no view provides, which may be renamed in S/4HANA, removed, or not exposed in any view.
- **Side by side:** up to four views, one row per field, with the name each view gives it. Tick up to four under "All views" to compare others.
- **Which to choose:** under the fields, "How they differ" lists what the ranking looks at for each view: priority, extraction, delta, released by SAP, built by SAP or in your system, level of detail, which of your tables it reads and how, other tables mixed in, number of fields and data products. Rows where the views differ are shaded. Above the grid a short verdict says which view to choose and why:
  - same fields: the first ranking rule that separates the views, for example "ranks higher because it is released by SAP", and a note when the other view is a custom one
  - a view that adds fields the main view lacks: use the two together
- **How to join:** for views used together, a suggestion to look one view up by its key fields, matched on the table field both come from (ACDOCA-MATNR and MARA-MATNR are both MATNR) or, failing that, the same field name in both views. It says whether that is the view's full key (each row finds at most one row) or only part of it. Key fields come from the DD03N file; without it no join is suggested. It is a suggestion matched on names: confirm it before you build on it.
- **Export:** a CSV with one row per view and the fields it misses.
- **Nothing is stored.** A CSV is read in the browser, and only the field names are sent with the request. The server keeps nothing and logs only the address, status and time of each request. Reloading the page clears the fields.
- The P1, P2 and P3 ranking itself is unchanged; Compare fields uses it.

## Table mapping

The mapping (ECC table to S/4HANA tables, for example MSEG to MATDOC or VBUK to VBAK, LIKP and VBRK) is stored in SQLite at `data/cds_finder.db`. The first time the app starts with an empty database, it copies `cds_finder/initial_mapping.csv` into it. After that the database is the only source.

On the **Table mapping** page users can search, filter by status, sort by name or last change, add, edit, retire and restore mappings, see each mapping's history, import a CSV (with a preview; nothing is saved while any row has an error) and export the mapping as CSV.

- Searches use a changed mapping straight away (each search checks a version counter with one small query).
- Nobody overwrites another person's change unseen: every row has a version, and a save based on an old version is refused with `409` and the current row.
- Mappings are retired, never deleted, so the history stays complete.
- Each change runs in one transaction; the database runs in WAL mode so reads never wait for writes.

## Configuration

Settings come from environment variables (see `.env.example`). Command line options override them.

| Variable | Default | Meaning |
|---|---|---|
| `CDS_FINDER_DATA_DIR` | `data` | Folder with the metadata files |
| `CDS_FINDER_DB_PATH` | `data/cds_finder.db` | SQLite file with the mapping and its history |
| `CDS_FINDER_HOST` | `127.0.0.1` | Address to listen on |
| `CDS_FINDER_PORT` | `8000` | Port |
| `CDS_FINDER_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` or `ERROR` |
| `CDS_FINDER_LOG_JSON` | `false` | One JSON object per log line (method, path, status, duration) |
| `CDS_FINDER_DOCS_ENABLED` | `true` | Interactive API documentation at `/api/docs` |
| `CDS_FINDER_BRAND_LOGO` | none | Logo file for the header (SVG or PNG). Without it, a `brand-logo.svg` or `brand-logo.png` in the data folder is used if present, otherwise the bundled Deloitte logo |

## Command line

```bash
cds-finder serve    [--data-dir DIR] [--db-path FILE] [--host HOST] [--port PORT]
cds-finder check    [--data-dir DIR] [--db-path FILE]
cds-finder mappings export FILE.csv [--status active|retired|all]
cds-finder mappings import FILE.csv [--apply] [--by NAME]
```

`mappings import` without `--apply` only checks the file.

The app can also run under uvicorn directly (settings from the environment):

```bash
uvicorn cds_finder.api:create_app --factory --host 0.0.0.0 --port 8000
```

## API

Interactive documentation is at `/api/docs` (OpenAPI schema at `/api/openapi.json`). JSON uses camelCase. Errors always come back as `{"detail": "message"}`, with a message that is safe to show; a conflict also returns `"current"`.

| Method and path | What it does |
|---|---|
| `GET /api/health` | `{"status": "ok", "ready": true}`; `ready` is false when the metadata is not loaded |
| `GET /api/meta` | Loaded files and what each holds, notes on the data, active mapping, table suggestions, priority labels |
| `POST /api/search` | One page of ranked views. Body: `{"tables": [{"ecc": "MSEG", "s4": []}], "priority": null, "includeCustom": true, "withDataProduct": false, "q": "", "sort": "recommended", "page": 1, "pageSize": 20}` |
| `POST /api/view` | One view in full, with every field. Body: `{"tables": [...], "name": "I_MaterialDocumentItem_2"}` |
| `POST /api/search/export` | Every matching view as CSV (same body as the search), including its data products |
| `GET /api/data-products?q=&inMetadata=false&page=1&pageSize=24` | One page of data products with entity, extraction and view counts |
| `GET /api/data-products/{name}` | One data product from the catalogue with all its entities, keys and extraction details |
| `GET /api/tables/usage?names=MATDOC,ACDOCA` | How many views read each table |
| `POST /api/coverage` | Compare fields. Body: `{"tables": [{"ecc": "VBAP"}], "fields": ["NETWR", "VBAK-ERDAT"], "compare": []}`; `compare` names up to four views to show side by side |
| `POST /api/coverage/export` | The same comparison as CSV, one row per view |
| `GET /api/mappings?q=&status=active&sort=ecc&page=1&pageSize=25` | Paginated mapping list |
| `POST /api/mappings` | Add: `{"ecc", "s4": [...], "note", "changedBy"}` |
| `GET`, `PUT /api/mappings/{ecc}` | Read or change one mapping. `PUT` needs `{"s4", "note", "version", "changedBy"}` |
| `POST /api/mappings/{ecc}/retire`, `/restore` | `{"version", "changedBy"}` |
| `GET /api/mappings/{ecc}/history` | Paginated change history |
| `POST /api/mappings/import` | `{"rows": [{"ecc", "s4", "note"}], "apply": false}`: preview, then `"apply": true` |
| `GET /api/mappings/export?status=active` | Mapping as CSV |

Status codes: `400` rejected change, `404` not found, `409` conflict, `422` invalid input, `503` metadata not loaded.

## Deployment

### Docker

```bash
docker build -t cds-view-finder .
docker run -d --name cds-view-finder -p 8000:8000 -v /srv/cds-finder:/data cds-view-finder
```

Put the metadata files in `/srv/cds-finder`; the mapping database is created there too. The image installs the locked dependencies only (`uv sync --frozen --no-dev`), runs as a non-root user, logs JSON to stdout and has a health check on `/api/health`.

### Without Docker

```bash
uv sync --frozen --no-dev
CDS_FINDER_HOST=0.0.0.0 .venv/bin/cds-finder serve
```

Run it under your process manager (systemd or similar) behind your usual reverse proxy for TLS.

### Operating notes

- **There is no sign-in.** Anyone who can reach the app can change the mapping. Keep it on an internal network or behind your reverse proxy's sign-in until authentication is added.
- **Run one process.** Each process holds its own copy of the metadata in memory. One process serves many users, because request work runs in a thread pool.
- **Back up `cds_finder.db`.** It is the live mapping. Copy it while the app is stopped, or run `cds-finder mappings export` at any time. Keep the database on a local disk, not a network share.
- **Sizing.** With 960,000 field origin rows (12,000 views), start-up took about 8 seconds and the process used about 740 MB. A first search over 1,572 matching views took 0.1 seconds; further pages, filters and sorting about 7 milliseconds; exporting all 1,572 views about 50 milliseconds.

## Known limits

- **Row filters are not visible.** The field origin file shows where fields come from, not how a view filters rows. A view limited to sales orders looks like a full match for the item table. Check the description before choosing.
- **No field rename mapping.** Fields are matched by table field name, so renamed fields count as not found.
- **Header and item in one table.** When an ECC header and item table became one S/4HANA table (MKPF and MSEG became MATDOC), header and item views both read it at the same level of detail. The view with more matching fields comes first, usually the item view, so check the result for header tables.

## Demo file

`tools/build_demo.py` writes one HTML file that shows the whole app without a server, for demos. It runs the app in memory, records its answers to every search, view, field comparison and mapping a visitor can click, and puts them in the file with the page itself. Searches or fields that were not recorded, and any change to the mapping, get a short message instead.

```bash
uv run python tools/build_demo.py                                          # bundled examples
uv run python tools/build_demo.py --data-dir data --tables MSEG ACDOCA VBUK --out demo.html
```

## Development

```bash
uv sync                      # includes the test tools
uv run pytest                # unit and API tests
uvx ruff check cds_finder tests
```

## Project layout

```
cds_finder/
  api/                 FastAPI app: create_app, routers for search and mappings, dependencies
  service.py           the finder: metadata catalog, mapping cache, ranking cache
  ranking.py           priorities, ranking order, business notes
  coverage.py          compare fields: which views provide a list of fields
  metadata.py          reads the CSV extracts, follows stacked views, joins key fields
  products.py          reads the data product catalogue and links it to CDS views
  mappings.py          SQLite table mapping: list, add, change, retire, history, import
  schemas.py           Pydantic request and response models
  settings.py          settings from CDS_FINDER_* environment variables
  errors.py, logs.py   error types and logging set-up
  cli.py               command line
  initial_mapping.csv  mapping copied into an empty database
  web/                 the web page (index.html, app.css, app.js; no external resources) and the Deloitte logo files
examples/              illustrative metadata files with the real column layouts
data/                  your metadata files and the mapping database (not in version control)
tests/                 pytest suite
```
