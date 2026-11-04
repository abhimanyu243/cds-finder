"""Data product catalogue: which SAP data products (and which of their entities) use each CDS view.

Input file (name contains DataProductCatalogue or DataProductCatalog), one row per entity:
  Product, Entity, CDS view, Entity type, Extraction, Root, Size, Elements, Keys

A CDS view is linked to a data product only when its name appears exactly in the CDS view
column (compared in upper case, against the view's entity name and its data definition
name). Nothing is guessed. The catalogue is optional: without it the app works as before.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .metadata import Column, FileReport, find_data_file, is_true, stream_file

CATALOGUE_FILE = "DataProductCatalog"        # matches DataProductCatalogue and DataProductCatalog
FALSE_FLAGS = frozenset({"NO", "FALSE", "0", "N", "-"})

CATALOGUE_COLUMNS = (
    Column("PRODUCT", ("PRODUCT", "DATAPRODUCT", "DATAPRODUCTNAME", "PRODUCTNAME")),
    Column("ENTITY", ("ENTITY", "ENTITYNAME", "ENTITYSET"), required=False),
    Column("CDS_VIEW", ("CDSVIEW", "CDSVIEWNAME", "CDSENTITY", "CDSNAME", "VIEW"), ("CDS",)),
    Column("ENTITY_TYPE", ("ENTITYTYPE", "OBJECTNODETYPE"), required=False),
    Column("EXTRACTION", ("EXTRACTION", "EXTRACTIONENABLED", "DATAEXTRACTION"), required=False),
    Column("ROOT", ("ROOT", "ROOTENTITY", "ISROOT"), required=False),
    Column("SIZE", ("SIZE", "SIZECATEGORY"), required=False),
    Column("ELEMENTS", ("ELEMENTS", "ELEMENTCOUNT", "FIELDS", "FIELDCOUNT"), required=False),
    Column("KEYS", ("KEYS", "KEYFIELDS", "KEY"), required=False),
)

# sap-s4com-AddressConfigurationData-v1 -> name AddressConfigurationData, version 1
_PRODUCT_ID = re.compile(r"^[a-z0-9]+-[a-z0-9]+-(?P<name>.+?)-v(?P<version>\d+)$", re.IGNORECASE)
_WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")


def humanize(name: str) -> str:
    """'AddressConfigurationData' -> 'Address configuration data', 'HANACurrency' -> 'HANA currency'."""
    if not name or "_" in name or " " in name or name.isupper():
        return name
    words = [w if len(w) > 1 and w.isupper() else w.lower() for w in _WORD.findall(name)]
    text = " ".join(words) or name
    return text[:1].upper() + text[1:]


def product_title(product: str) -> tuple[str, str | None]:
    """Readable title and version of a data product name. Unknown formats are shown as they are."""
    m = _PRODUCT_ID.match(product)
    return (humanize(m["name"]), m["version"]) if m else (product, None)


def _flag(value: str) -> bool | None:
    """True, False, or None when the catalogue does not say."""
    text = value.strip().upper()
    if not text:
        return None
    if is_true(text):
        return True
    return False if text in FALSE_FLAGS else None


@dataclass(frozen=True, slots=True)
class ProductEntity:
    product: str
    entity: str
    cds_view: str
    entity_type: str
    extraction: bool | None
    root: bool
    size: str
    elements: int | None
    keys: tuple[str, ...]


@dataclass
class ProductCatalogue:
    products: dict[str, list[ProductEntity]] = field(default_factory=dict)   # product -> entities, file order
    by_view: dict[str, list[ProductEntity]] = field(default_factory=dict)    # CDS view (upper) -> entities
    report: dict = field(default_factory=dict)

    @property
    def loaded(self) -> bool:
        return bool(self.products)

    def has_view(self, *names: str) -> bool:
        return any(name and name.upper() in self.by_view for name in names)

    def for_view(self, *names: str) -> dict[str, list[ProductEntity]]:
        """Data products that use a view, by any of its names: product -> its entities on this view."""
        out: dict[str, list[ProductEntity]] = {}
        seen: set[int] = set()
        for name in names:
            for e in self.by_view.get(name.upper(), ()) if name else ():
                if id(e) not in seen:
                    seen.add(id(e))
                    out.setdefault(e.product, []).append(e)
        return out


def load_catalogue(folder: Path) -> tuple[ProductCatalogue, FileReport | None]:
    """Read the catalogue in folder. Returns an empty catalogue when there is no such file.

    Raises LoadError when the file exists but cannot be read.
    """
    path = find_data_file(folder, CATALOGUE_FILE)
    if path is None:
        return ProductCatalogue(), None
    cat = ProductCatalogue()
    stats = {"duplicateRows": 0, "rowsWithoutProduct": 0}

    def consume(rows) -> None:
        cat.products.clear()
        cat.by_view.clear()
        stats.update(duplicateRows=0, rowsWithoutProduct=0)
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            product = row["PRODUCT"]
            if not product:
                stats["rowsWithoutProduct"] += 1
                continue
            view = row.get("CDS_VIEW", "")
            entity = row.get("ENTITY", "")
            ident = (product, entity.upper(), view.upper())
            if ident in seen:                       # the same entity listed twice: keep the first
                stats["duplicateRows"] += 1
                continue
            seen.add(ident)
            elements = row.get("ELEMENTS", "").replace(",", "").strip()
            item = ProductEntity(
                product=product, entity=entity, cds_view=view, entity_type=row.get("ENTITY_TYPE", ""),
                extraction=_flag(row.get("EXTRACTION", "")), root=_flag(row.get("ROOT", "")) is True,
                size=row.get("SIZE", ""), elements=int(elements) if elements.isdigit() else None,
                keys=tuple(dict.fromkeys(k.strip() for k in row.get("KEYS", "").split(",") if k.strip())),
            )
            cat.products.setdefault(product, []).append(item)
            if view:
                cat.by_view.setdefault(view.upper(), []).append(item)

    report = stream_file(path, CATALOGUE_COLUMNS, consume)
    cat.report = {"products": len(cat.products), "entities": sum(len(v) for v in cat.products.values()),
                  "views": len(cat.by_view), **stats}
    return cat, report
