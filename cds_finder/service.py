"""The finder: metadata catalog + table mapping + a small cache of rankings.

The catalog is read once at start-up. The mapping lives in SQLite and can change at
any time, so every search asks for its version (one tiny query) and reloads it only
when it changed. Rankings are cached per mapping version and input, so moving between
pages, filters and sort orders does not rank again.
"""

from __future__ import annotations

import logging
import threading
from collections import Counter, OrderedDict
from pathlib import Path
from typing import TypeVar

from . import __version__, ranking
from .errors import NotFound, Unavailable
from .mappings import MappingRepository
from .metadata import (
    ASSOCIATIONS_FILE, EXTRACTION_FILE, FIELD_ORIGIN_FILE, KEY_FIELDS_FILE, TEXTS_FILE, Association, Catalog,
    LoadError, View, build_catalog, has_metadata,
)
from .products import ProductCatalogue, ProductEntity, load_catalogue, product_title
from .schemas import (
    DataFile, DataProduct, DataProductEntity, DataProductRef, Meta, Notice, Paging, ProductPage, ProductQuery,
    ProductSummary, SearchRequest, SearchResponse, TableInput, TableUsage, ViewAssociation, ViewDetail, ViewRequest,
    ViewSummary, clamp_page,
)
from .settings import Settings

log = logging.getLogger("cds_finder")

FILE_DESCRIPTIONS = {
    FIELD_ORIGIN_FILE: "Which tables and fields each view reads",
    EXTRACTION_FILE: "Views enabled for data extraction, with delta and release status",
    KEY_FIELDS_FILE: "Identifying fields of each view, used to compare the level of detail",
    TEXTS_FILE: "Description of each view, used when the extraction file has none",
    ASSOCIATIONS_FILE: "Associations each view defines, shown in the view details",
}
CATALOGUE_DESCRIPTION = "Data products with their entities, keys and extraction details"
RANKING_CACHE_SIZE = 64
LOGO_FILES = ("brand-logo.svg", "brand-logo.png", "brand-logo.jpg", "brand-logo.webp")
BUNDLED_LOGO = "brand-logo.svg"         # in the web folder: the Deloitte logo with white lettering, for the dark header
Item = TypeVar("Item", bound=ViewSummary)


class Finder:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.repository = MappingRepository(settings.db_path)
        added = self.repository.seed(settings.initial_mapping)
        if added:
            log.info("Mapping database created with %d initial mappings", added)
        if has_metadata(settings.data_dir):
            self.catalog = build_catalog(settings.data_dir)
            r = self.catalog.report
            log.info("Metadata loaded: %d views, %d tables in %.1fs", r["views"], r["tables"], r["loadSeconds"])
        else:
            self.catalog = Catalog.empty()
            log.warning("No metadata files in %s. Add %s and %s files and restart.",
                        settings.data_dir, FIELD_ORIGIN_FILE, EXTRACTION_FILE)
        self.products, self._catalogue_file, self._catalogue_error = self._load_products(settings)
        self.brand_logo = self._find_logo(settings)
        self._index_products()
        self._lock = threading.Lock()
        self._mapping: dict[str, tuple[tuple[str, ...], str]] = {}
        self._mapping_version = -1
        self._rankings: OrderedDict[tuple, ranking.Ranking] = OrderedDict()
        self._suggestions = sorted(t for t, keys in self.catalog.table_index.items()
                                   if t.isascii() and any(self.catalog.views[k].extraction for k in keys))

    @staticmethod
    def _load_products(settings: Settings) -> tuple[ProductCatalogue, str | None, str | None]:
        """The catalogue is optional: a missing or unreadable file only switches the data product links off."""
        try:
            catalogue, report = load_catalogue(settings.data_dir)
        except LoadError as exc:
            log.warning("Data product catalogue not loaded: %s", exc)
            return ProductCatalogue(), None, str(exc)
        if report:
            r = catalogue.report
            log.info("Data product catalogue loaded: %d products, %d entities, %d CDS views",
                     r["products"], r["entities"], r["views"])
        return catalogue, report.name if report else None, None

    @staticmethod
    def _find_logo(settings: Settings) -> Path | None:
        """A configured logo, else a logo file in the data folder, else the bundled one."""
        candidates = [settings.brand_logo] if settings.brand_logo else [settings.data_dir / n for n in LOGO_FILES]
        candidates.append(settings.web_dir / BUNDLED_LOGO)
        logo = next((p for p in candidates if p.is_file()), None)
        if settings.brand_logo and logo != settings.brand_logo:
            log.warning("Logo file %s not found, using the default logo", settings.brand_logo)
        return logo

    def _index_products(self) -> None:
        """Built once at start-up (the catalogue does not change while the app runs), so the
        Data products page filters a plain list instead of reading files."""
        self._known_views = set(self.catalog.views) | {v.ddlname for v in self.catalog.views.values() if v.ddlname}
        self._product_rows: list[tuple[str, ProductSummary]] = []
        for name, entities in self.products.products.items():
            title, version = product_title(name)
            views = {e.cds_view.upper(): e for e in entities if e.cds_view}
            summary = ProductSummary(
                name=name, title=title, version=version, entities=len(entities),
                extraction_entities=sum(e.extraction is True for e in entities),
                root_entities=sum(e.root for e in entities), cds_views=len(views),
                views_in_metadata=sum(self._in_metadata(e) for e in views.values()))
            text = " ".join([name, title, *(f"{e.entity} {e.cds_view}" for e in entities)]).lower()
            self._product_rows.append((text, summary))

    # -- mapping and ranking cache ------------------------------------------

    def mapping(self) -> tuple[int, dict[str, tuple[tuple[str, ...], str]]]:
        version = self.repository.version()
        with self._lock:
            if version != self._mapping_version:
                self._mapping, self._mapping_version = self.repository.active(), version
                self._rankings.clear()
            return self._mapping_version, self._mapping

    def ranking(self, tables: list[TableInput]) -> ranking.Ranking:
        if not self.catalog.loaded:
            raise Unavailable("The view metadata is not loaded yet. Ask your administrator to add the metadata files.")
        version, mapping = self.mapping()
        unique = {t.ecc: t for t in tables}.values()            # same ECC table twice counts once
        inputs = [ranking.resolve(t.ecc, t.s4, mapping) for t in unique]
        key = (version, tuple((i.ecc, i.s4) for i in inputs))
        with self._lock:
            hit = self._rankings.get(key)
            if hit is not None:
                self._rankings.move_to_end(key)
                return hit
        result = ranking.rank(self.catalog, inputs)
        with self._lock:
            self._rankings[key] = result
            while len(self._rankings) > RANKING_CACHE_SIZE:
                self._rankings.popitem(last=False)
        return result

    # -- search ---------------------------------------------------------------

    def _results(self, req: SearchRequest) -> tuple[ranking.Ranking, list[ranking.Match], Counter]:
        r = self.ranking(req.tables)
        keep = self._has_product if req.with_data_product else None
        matches, counts = r.filtered(req.priority, req.include_custom, req.q, keep)
        if req.sort == "name":
            matches = sorted(matches, key=lambda m: m.view.name.lower())
        return r, matches, counts

    def search(self, req: SearchRequest) -> SearchResponse:
        r, matches, counts = self._results(req)
        page = clamp_page(req.page, req.page_size, len(matches))
        shown = matches[(page - 1) * req.page_size: page * req.page_size]
        keys = self.catalog.keys_loaded
        return SearchResponse(
            inputs=ranking.resolved_tables(self.catalog, r.inputs),
            views_found=len(r.matches),
            data_product_views=sum(1 for m in r.matches if self._has_product(m)) if self.products.loaded else 0,
            priorities=ranking.priority_counts(counts),
            results=[self._with_products(ranking.summary(m, r.position[m.view.key], keys), m.view) for m in shown],
            paging=Paging.of(page, req.page_size, len(matches), len(shown)),
            guidance=ranking.guidance(r, self.catalog),
        )

    def view(self, req: ViewRequest) -> ViewDetail:
        r = self.ranking(req.tables)
        view = self.catalog.find_view(req.name)
        rank = r.position.get(view.key) if view else None
        if view is None or rank is None:
            raise NotFound(f"{req.name} does not read the tables you searched for.")
        detail = ranking.detail(r.matches[rank - 1], rank, self.catalog.keys_loaded)
        if self.catalog.associations_loaded:
            detail.associations = [self._association(a) for a in view.associations]
        return self._with_products(detail, view)

    def _association(self, a: Association) -> ViewAssociation:
        target = self.catalog.find_view(a.target)
        return ViewAssociation(name=a.name, target=target.name if target else a.target,
                               target_description=target.description if target else "",
                               cardinality=a.cardinality, condition=a.condition)

    def export_rows(self, req: SearchRequest) -> list[list]:
        r, matches, _ = self._results(req)
        yes = ("No", "Yes")
        rows = [["Rank", "View", "Description", "Priority", "Data extraction", "Delta loads", "Released by SAP",
                 "Level of detail", "Reads", "Fields from your tables", "All fields", "Data products", "Notes"]]
        for m in matches:
            note = ranking.business_note(m, self.catalog.keys_loaded)
            rows.append([r.position[m.view.key], m.view.name, m.view.description,
                         f"{m.priority} - {ranking.PRIORITY_LABEL[m.priority]}", yes[m.extraction], yes[m.delta],
                         yes[m.released], ranking.DETAIL_TEXT[m.detail], ", ".join(u.inp.ecc for u in m.covered),
                         m.matched_fields, len(m.view.elements), ", ".join(self.products.for_view(m.view.key,
                                                                                                    m.view.ddlname)),
                         " ".join([note.summary, *note.considerations])])
        return rows

    # -- data products ----------------------------------------------------------

    def _has_product(self, m: ranking.Match) -> bool:
        return self.products.has_view(m.view.key, m.view.ddlname)

    def _with_products(self, item: Item, view: View) -> Item:
        """Attach the data products whose catalogue rows name this view exactly."""
        item.data_products = [
            DataProductRef(name=name, title=product_title(name)[0], entities=[e.entity for e in entities],
                           cds_views=list(dict.fromkeys(e.cds_view for e in entities)))
            for name, entities in self.products.for_view(view.key, view.ddlname).items()]
        return item

    def _in_metadata(self, e: ProductEntity) -> bool:
        return bool(e.cds_view) and e.cds_view.upper() in self._known_views

    def product(self, name: str) -> DataProduct:
        entities = self.products.products.get(name.strip())
        if entities is None:
            raise NotFound(f"The data product {name} is not in the catalogue.")
        title, version = product_title(name.strip())
        return DataProduct(name=name.strip(), title=title, version=version, entities=[
            DataProductEntity(entity=e.entity, cds_view=e.cds_view, entity_type=e.entity_type, extraction=e.extraction,
                              root=e.root, size=e.size, fields=e.elements, keys=list(e.keys),
                              in_metadata=self._in_metadata(e)) for e in entities])

    def products_page(self, query: ProductQuery) -> ProductPage:
        q = query.q.strip().lower()
        items = [p for text, p in self._product_rows
                 if (not q or q in text) and (not query.in_metadata or p.views_in_metadata)]
        page = clamp_page(query.page, query.page_size, len(items))
        shown = items[(page - 1) * query.page_size: page * query.page_size]
        return ProductPage(items=shown, paging=Paging.of(page, query.page_size, len(items), len(shown)))

    # -- reference data -------------------------------------------------------

    def meta(self) -> Meta:
        version, mapping = self.mapping()
        names = [f["name"] for f in self.catalog.report["files"]]
        files = [DataFile(name=n, holds=desc) for key, desc in FILE_DESCRIPTIONS.items()
                 for n in names if key.lower() in n.lower()]
        if self._catalogue_file:
            files.append(DataFile(name=self._catalogue_file, holds=CATALOGUE_DESCRIPTION))
        files.append(DataFile(name=self.settings.db_path.name,
                              holds="Table mapping from ECC to S/4HANA, with its change history"))
        return Meta(app_version=__version__, ready=self.catalog.loaded, views=len(self.catalog.views),
                    loaded_at=self.catalog.report.get("loadedAt"), files=files,
                    data_products=len(self.products.products), notices=self._notices(),
                    brand_logo=self.brand_logo is not None,
                    mappings={k: list(v[0]) for k, v in mapping.items()}, mapping_version=version,
                    suggestions=sorted(set(mapping) | set(self._suggestions)), priorities=list(ranking.PRIORITIES))

    def _notices(self) -> list[Notice]:
        """What is missing or needs attention, in plain words. Shown in the About dialog."""
        notes = []
        if not self.catalog.loaded:
            notes.append(Notice(level="warning", title="View metadata is not loaded",
                                text=f"Add the {FIELD_ORIGIN_FILE} and {EXTRACTION_FILE} files to the data folder "
                                     "and restart the app. Table mapping still works."))
        elif not self.catalog.keys_loaded:
            notes.append(Notice(level="info", title="Key fields are not loaded",
                                text="The level of detail of each view is not compared. Add the "
                                     f"{KEY_FIELDS_FILE} file to the data folder to compare it."))
        if self._catalogue_error:
            notes.append(Notice(level="warning", title="The data product catalogue could not be read",
                                text=self._catalogue_error))
        elif not self.products.loaded:
            notes.append(Notice(level="info", title="No data product catalogue",
                                text="Add a DataProductCatalogue file to the data folder to see which data "
                                     "products use each view."))
        else:
            r = self.products.report
            if r.get("duplicateRows"):
                n = r["duplicateRows"]
                notes.append(Notice(level="info", title="Repeated catalogue rows",
                                    text=f"{n:,} {'row was' if n == 1 else 'rows were'} listed more than once "
                                         "and read once."))
            if r.get("rowsWithoutProduct"):
                n = r["rowsWithoutProduct"]
                notes.append(Notice(level="info", title="Catalogue rows without a product",
                                    text=f"{n:,} {'row has' if n == 1 else 'rows have'} no product name and "
                                         f"{'was' if n == 1 else 'were'} left out."))
        return notes

    def table_usage(self, names: list[str]) -> TableUsage:
        return TableUsage(tables={t: self.catalog.views_reading([t]) for t in names},
                          total=self.catalog.views_reading(names))
