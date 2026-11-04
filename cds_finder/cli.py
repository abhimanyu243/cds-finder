"""Command line.

  cds-finder serve    [--data-dir DIR] [--db-path FILE] [--host HOST] [--port PORT]
  cds-finder check    [--data-dir DIR] [--db-path FILE]
  cds-finder mappings export FILE.csv [--status active|retired|all] [--db-path FILE]
  cds-finder mappings import FILE.csv [--apply] [--by NAME] [--db-path FILE]

Every option can also be set with a CDS_FINDER_* environment variable (see .env.example).
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from . import __version__
from .errors import AppError
from .mappings import MappingRepository, read_mapping_csv
from .metadata import TEXTS_FILE, LoadError, build_catalog
from .products import load_catalogue
from .settings import Settings


def _settings(args: argparse.Namespace) -> Settings:
    return Settings.from_env(data_dir=getattr(args, "data_dir", None), db_path=args.db_path,
                             host=getattr(args, "host", None), port=getattr(args, "port", None))


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from .api import create_app

    settings = _settings(args)
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_config=None)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    settings = _settings(args)
    catalog = build_catalog(settings.data_dir)
    r = catalog.report
    print(f"Metadata folder: {r['dataDir']}")
    for f in r["files"]:
        skipped = f", {f['skipped']:,} rows skipped" if f["skipped"] else ""
        print(f"  {f['name']}: {f['rows']:,} rows, {f['delimiter']}, {f['encoding']}{skipped}")
        for key, header in f["columns"].items():
            print(f"      {key:<14} <- {header}")
    print(f"Views: {r['views']:,}   fields: {r['elements']:,}   tables: {r['tables']:,}")
    print(f"Extraction views: {r['extractionViews']:,} "
          f"({r['extractionViewsWithoutLineage']:,} without field origin rows)")
    if r["extractionViewsWithoutLineageList"]:
        print("  for example: " + ", ".join(r["extractionViewsWithoutLineageList"][:10]))
    if r.get("dd03nFile"):
        print(f"Key fields: {r['keysMatched']:,} matched in {r['viewsWithKeys']:,} views")
        if r["keyFieldsNotInFieldOrigin"]:
            print(f"  {r['keyFieldsNotInFieldOrigin']:,} key fields not found in the field origin file, for example "
                  + ", ".join(r["keyFieldsNotInFieldOriginList"][:5]))
    else:
        print("No key fields file: the level of detail is not compared")
    print(f"Descriptions: {r['viewsWithDescription']:,} of {r['views']:,} views"
          + ("" if r.get("textsFile") else f" (add a {TEXTS_FILE} file for the rest)"))
    if r["duplicateRows"] or r["rowsWithoutName"]:
        print(f"Rows ignored: {r['duplicateRows']:,} repeated, {r['rowsWithoutName']:,} without a view or field name")
    print(f"Loaded in {r['loadSeconds']} s")
    _check_products(settings, catalog)
    repo = MappingRepository(settings.db_path)
    repo.seed(settings.initial_mapping)
    print(f"Table mapping: {repo.count():,} rows in {settings.db_path} ({len(repo.active()):,} active)")
    return 0


def _check_products(settings: Settings, catalog) -> None:
    try:
        products, report = load_catalogue(settings.data_dir)
    except LoadError as exc:
        print(f"Data product catalogue not used: {exc}")
        return
    if report is None:
        print("No data product catalogue: views are shown without data products")
        return
    p = products.report
    names = {v.key for v in catalog.views.values()} | {v.ddlname for v in catalog.views.values()}
    found = [view for view in products.by_view if view in names]
    print(f"Data product catalogue {report.name}: {p['products']:,} products, {p['entities']:,} entities, "
          f"{p['views']:,} CDS views")
    print(f"  {len(found):,} of those CDS views are in the field origin file and get linked")
    if p["duplicateRows"] or p["rowsWithoutProduct"]:
        print(f"  Rows ignored: {p['duplicateRows']:,} repeated, {p['rowsWithoutProduct']:,} without a product")


def cmd_mappings(args: argparse.Namespace) -> int:
    settings = _settings(args)
    repo = MappingRepository(settings.db_path)
    repo.seed(settings.initial_mapping)
    if args.action == "export":
        items = repo.export(args.status)
        with Path(args.file).open("w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["ECC_TABLE", "S4_TABLES", "NOTE"])
            writer.writerows([m.ecc, ";".join(m.s4), m.note] for m in items)
        print(f"Wrote {len(items)} mappings to {args.file}")
        return 0
    result = repo.import_rows(read_mapping_csv(Path(args.file)), apply=args.apply, by=args.by)
    s = result.summary
    print(f"new {s.new}, changed {s.change}, restored {s.restore}, unchanged {s.same}, errors {s.error}")
    for row in result.rows:
        if row.action == "error":
            print(f"  row {row.row}: {row.message}")
    print("Saved." if result.applied else "Nothing saved. Run again with --apply to save.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cds-finder", description="Find the S/4HANA view for an ECC table.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser, data: bool = True) -> None:
        if data:
            p.add_argument("--data-dir", type=Path, help="folder with the metadata files (default: ./data)")
        p.add_argument("--db-path", type=Path,
                       help="SQLite file with the table mapping (default: ./data/cds_finder.db)")

    p = sub.add_parser("serve", help="start the web app")
    common(p)
    p.add_argument("--host", help="default 127.0.0.1")
    p.add_argument("--port", type=int, help="default 8000")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("check", help="read the metadata files and print what was found")
    common(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("mappings", help="export or import the table mapping as CSV")
    p.add_argument("action", choices=("export", "import"))
    p.add_argument("file", help="CSV with ECC_TABLE, S4_TABLES (separated by ;) and NOTE")
    p.add_argument("--status", default="active", choices=("active", "retired", "all"), help="export only")
    p.add_argument("--apply", action="store_true", help="import only: save the changes (otherwise only check)")
    p.add_argument("--by", default="", help="import only: name stored in the change history")
    common(p, data=False)
    p.set_defaults(func=cmd_mappings)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (LoadError, AppError, OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
