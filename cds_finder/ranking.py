"""Find the views that read the S/4HANA tables behind one or more ECC tables, and rank them.

Every view gets a priority:
  1  supports data extraction and delta loads
  2  standard SAP view (name starts with I_ or C_)
  3  any other view

Within a priority the order is fixed, so the same input always gives the same list:
  reads more of your tables, same level of detail as your table, extraction enabled,
  released by SAP, reads your table directly, more fields from your tables,
  fewer other tables mixed in, then name.

Each view also gets a business note: plain sentences that explain the priority, what
the view supports and what to check before using it in a migration.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property

from .metadata import CLIENT_FIELDS, Catalog, View
from .schemas import (
    BusinessNote, Capability, FieldSource, Guidance, PriorityCount, PriorityInfo, ResolvedTable,
    TableUse, ViewDetail, ViewField, ViewSummary,
)

PRIORITIES = (
    PriorityInfo(level=1, label="Extraction and delta ready",
                 description="Supports data extraction and delta loads, so after one full load "
                             "only changes are transferred."),
    PriorityInfo(level=2, label="Standard SAP view",
                 description="A standard SAP view that does not support delta loads."),
    PriorityInfo(level=3, label="Other view",
                 description="A custom or other view that does not support delta loads."),
)
PRIORITY_LABEL = {p.level: p.label for p in PRIORITIES}

DETAIL_TEXT = {
    "same": "Same level of detail as your table",
    "check": "May be more detailed than your table",
    "different": "Different level of detail from your table",
    "unknown": "Level of detail not confirmed",
}
DETAIL_RANK = {"same": 2, "check": 1, "unknown": 1, "different": 0}


@dataclass(frozen=True)
class Input:
    ecc: str
    s4: tuple[str, ...]
    source: str            # 'mapping' | 'entered' | 'same'
    note: str = ""


def resolve(ecc: str, entered: list[str], mapping: dict[str, tuple[tuple[str, ...], str]]) -> Input:
    """S/4HANA tables for an ECC table: what the user entered, else the mapping, else the same name."""
    mapped = mapping.get(ecc)
    note = mapped[1] if mapped else ""
    if entered:
        return Input(ecc, tuple(entered), "entered", note)
    if mapped:
        return Input(ecc, mapped[0], "mapping", note)
    return Input(ecc, (ecc,), "same")


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# --------------------------------------------------------------------------
# One view, seen from the tables you entered
# --------------------------------------------------------------------------

@dataclass
class InputUse:
    inp: Input
    tables: list[str]          # S/4 tables of this input that the view reads
    depth: int | None          # 1 = reads the table itself
    fields: set[str]

    @property
    def covered(self) -> bool:
        return bool(self.tables)


@dataclass
class Match:
    view: View
    uses: list[InputUse]
    other_tables: list[str]
    detail: str                # 'same' | 'check' | 'different' | 'unknown'
    keys_known: bool           # key fields were available for this view

    @cached_property
    def covered(self) -> list[InputUse]:
        return [u for u in self.uses if u.covered]

    @property
    def all_covered(self) -> bool:
        return len(self.covered) == len(self.uses)

    @property
    def extraction(self) -> bool:
        return self.view.extraction is not None

    @property
    def delta(self) -> bool:
        return bool(self.view.extraction and self.view.extraction.delta)

    @property
    def released(self) -> bool:
        return bool(self.view.extraction and self.view.extraction.released)

    @property
    def priority(self) -> int:
        if self.extraction and self.delta:
            return 1
        return 2 if self.view.standard else 3

    @property
    def depth(self) -> int:
        return max((u.depth for u in self.covered if u.depth), default=99)

    @property
    def matched_fields(self) -> int:
        return sum(len(u.fields) for u in self.covered)

    @cached_property
    def sort_key(self) -> tuple:
        return (self.priority, -len(self.covered), -DETAIL_RANK[self.detail], -self.extraction, -self.released,
                self.depth, -self.matched_fields, len(self.other_tables), self.view.name.lower())


def why_higher(a: Match, b: Match) -> str:
    """The first rule of sort_key that puts view a above view b, in plain words ('because ...')."""
    rule = next((i for i, (x, y) in enumerate(zip(a.sort_key, b.sort_key, strict=True)) if x != y), 8)
    if rule == 0:
        return "it supports data extraction and delta loads" if a.priority == 1 else "it is a standard SAP view"
    if rule == 1:
        return f"it reads more of your tables ({len(a.covered)} against {len(b.covered)})"
    if rule == 2:
        return ("it has the same level of detail as your table" if a.detail == "same"
                else "its level of detail is closer to your table")
    if rule == 3:
        return "it is enabled for data extraction"
    if rule == 4:
        return "it is released by SAP"
    if rule == 5:
        return "it reads your table directly" if a.depth == 1 else "it reads your table through fewer views"
    if rule == 6:
        return f"it has more fields from your tables ({a.matched_fields} against {b.matched_fields})"
    if rule == 7:
        return f"it mixes in fewer other tables ({len(a.other_tables)} against {len(b.other_tables)})"
    return "the two are equal on every ranking rule, so the name decides"


def _detail_level(view: View, s4: set[str], keys_loaded: bool) -> tuple[str, bool]:
    """Compare the view's key fields with your tables.

    'same' when every key field comes from your tables, 'check' when some come from other
    tables (the view may be more detailed, e.g. items instead of documents), 'different'
    when none do.
    """
    if not keys_loaded or not view.keys:
        return "unknown", False
    inside = outside = 0
    for el in view.keys:
        if any(s.table in s4 and s.field and s.field not in CLIENT_FIELDS for s in el.sources):
            inside += 1
        else:
            outside += 1
    if not outside:
        return "same", True
    return ("check" if inside else "different"), True


def evaluate(view: View, inputs: list[Input], keys_loaded: bool) -> Match:
    s4_all = {t for inp in inputs for t in inp.s4}
    uses = []
    for inp in inputs:
        used = [t for t in inp.s4 if t in view.tables]
        fields: set[str] = set()
        for t in used:
            fields |= view.tables[t].fields
        depth = min((view.tables[t].min_depth for t in used), default=None)
        uses.append(InputUse(inp, used, depth, fields))
    covered_s4 = {t for u in uses for t in u.tables}
    detail, known = _detail_level(view, covered_s4, keys_loaded)
    other = sorted(t for t in view.tables if t not in s4_all)
    return Match(view, uses, other, detail, known)


# --------------------------------------------------------------------------
# Business note: plain wording, no technical names
# --------------------------------------------------------------------------

def business_note(m: Match, keys_loaded: bool) -> BusinessNote:
    p = m.priority
    if p == 1:
        summary = ("Priority 1 because it supports both data extraction and delta loads, so after one full "
                   "load only new and changed records need to be transferred.")
    else:
        why = "it is a standard SAP view" if p == 2 else (
            "it is a custom view built in your system" if m.view.custom else "it is not a standard SAP view")
        support = ("It supports data extraction, but not delta loads." if m.extraction
                   else "It is not enabled for data extraction.")
        summary = f"Priority {p} because {why}. {support}"

    capabilities = [
        Capability(label="Data extraction", value="Available" if m.extraction else "Not available",
                   tone="positive" if m.extraction else "caution"),
        Capability(label="Delta loads", value="Supported" if m.delta else "Not supported",
                   tone="positive" if m.delta else "caution"),
    ]
    if m.extraction:
        capabilities.append(Capability(label="Released by SAP", value="Yes" if m.released else "No",
                                       tone="positive" if m.released else "caution"))

    good_fit = m.all_covered and m.detail in ("same", "unknown")
    if p == 1:
        opening = "Strong candidate to replace your table." if good_fit else \
            "Good candidate once the points below are checked."
        recommendation = f"{opening} Run one full load, then keep the data current with delta loads."
    elif m.extraction:
        recommendation = ("Can be used for the migration with full loads. Each load transfers the complete "
                          "data set, so plan how often to reload.")
    else:
        recommendation = ("Useful as a reference for the data it holds, but it cannot be extracted as delivered. "
                          "A custom extraction view based on it would be needed.")

    checks: list[str] = []
    if not m.all_covered:
        missing = len(m.uses) - len(m.covered)
        checks.append(f"Does not read {_plural(missing, 'table')} of the {len(m.uses)} you entered.")
    if m.detail == "check":
        checks.append("Some of its identifying fields come from other tables, so it may hold more detailed "
                      "records than your table. Confirm the level of detail suits your needs.")
    elif m.detail == "different":
        checks.append("Its records are identified by data from other tables, so it holds data at a "
                      "different level of detail than your table.")
    elif keys_loaded and not m.keys_known:
        checks.append("The level of detail could not be confirmed for this view.")
    if m.extraction and not m.released:
        checks.append("Not released by SAP for customer use, so it may change in a future upgrade.")
    if m.view.custom:
        checks.append("Built in your system rather than delivered by SAP. Confirm who maintains it.")
    if m.depth not in (1, 99):
        checks.append("Builds on other views rather than reading your table directly.")
    if m.other_tables:
        checks.append(f"Also brings in data from {_plural(len(m.other_tables), 'other table')}.")
    return BusinessNote(summary=summary, recommendation=recommendation, capabilities=capabilities,
                        considerations=checks)


def summary(m: Match, rank: int | None, keys_loaded: bool) -> ViewSummary:
    return ViewSummary(
        rank=rank, name=m.view.name, description=m.view.description,
        priority=m.priority, priority_label=PRIORITY_LABEL[m.priority],
        extraction=m.extraction, delta=m.delta, released=m.released, custom=m.view.custom,
        covered=[u.inp.ecc for u in m.covered], not_covered=[u.inp.ecc for u in m.uses if not u.covered],
        field_count=len(m.view.elements), matched_field_count=m.matched_fields,
        detail_level=m.detail, note=business_note(m, keys_loaded),
    )


def detail(m: Match, rank: int | None, keys_loaded: bool) -> ViewDetail:
    v = m.view
    s4 = {t for u in m.uses for t in u.inp.s4}
    builds_on = list(dict.fromkeys(name for el in v.elements for s in el.sources for name in s.via))
    tables = sorted((TableUse(table=t, fields=len(u.fields), calculated_fields=len(u.calc_fields),
                              direct=u.min_depth == 1, yours=t in s4) for t, u in v.tables.items()),
                    key=lambda r: (not r.yours, -r.fields, r.table))
    fields = [ViewField(name=el.name, key=el.key, calculated=el.calculated,
                        from_your_tables=any(s.table in s4 for s in el.sources),
                        sources=[FieldSource(table=s.table, field=s.field, calculated=s.calculated, via=list(s.via))
                                 for s in el.sources])
              for el in v.elements]
    return ViewDetail(**summary(m, rank, keys_loaded).model_dump(), data_definition=v.ddlname,
                      detail_level_text=DETAIL_TEXT[m.detail], builds_on=builds_on, tables=tables, fields=fields)


# --------------------------------------------------------------------------
# Ranking all views for a set of inputs
# --------------------------------------------------------------------------

@dataclass
class Ranking:
    """Every view that reads the input tables, in recommended order. Cached between pages."""
    inputs: list[Input]
    matches: list[Match]
    position: dict[str, int] = field(default_factory=dict)      # view key -> rank (1-based)

    def filtered(self, priority: int | None, include_custom: bool, q: str,
                 keep: Callable[[Match], bool] | None = None) -> tuple[list[Match], Counter]:
        """Apply the filters. Counts per priority ignore the priority filter, so every tab shows its size.

        keep is an extra condition from outside the ranking, such as "has a data product".
        """
        term = q.strip().lower()
        counts: Counter = Counter()
        kept = []
        for m in self.matches:
            if not include_custom and m.view.custom:
                continue
            if keep is not None and not keep(m):
                continue
            if term and term not in m.view.name.lower() and term not in m.view.description.lower():
                continue
            counts[m.priority] += 1
            if priority is None or m.priority == priority:
                kept.append(m)
        return kept, counts


def rank(catalog: Catalog, inputs: list[Input]) -> Ranking:
    candidates: set[str] = set()
    for t in {t for inp in inputs for t in inp.s4}:
        candidates.update(catalog.table_index.get(t, ()))
    matches = sorted((evaluate(catalog.views[k], inputs, catalog.keys_loaded) for k in candidates),
                     key=lambda m: m.sort_key)
    return Ranking(inputs, matches, {m.view.key: i for i, m in enumerate(matches, start=1)})


def priority_counts(counts: Counter) -> list[PriorityCount]:
    return [PriorityCount(level=p.level, label=p.label, count=counts[p.level]) for p in PRIORITIES]


def resolved_tables(catalog: Catalog, inputs: list[Input]) -> list[ResolvedTable]:
    return [ResolvedTable(ecc=i.ecc, s4=list(i.s4), source=i.source, note=i.note,
                          views=catalog.views_reading(i.s4),
                          unknown_tables=[t for t in i.s4 if t not in catalog.table_index])
            for i in inputs]


def guidance(ranking: Ranking, catalog: Catalog) -> Guidance | None:
    tables = _join(list(dict.fromkeys(t for i in ranking.inputs for t in i.s4)))
    if not ranking.matches:
        tips = [f"{i.ecc} has no table mapping. If S/4HANA replaced it, enter the new table next to it, "
                "or add a mapping on the Table mapping page." for i in ranking.inputs if i.source == "same"]
        tips.append("Check the spelling of the S/4HANA table name.")
        tips.append(f"The loaded metadata covers {catalog.report['views']:,} views. If a view you expect is "
                    "missing, ask your administrator to refresh the metadata files.")
        return Guidance(title=f"No view reads {tables}", tips=tips)
    if all(m.priority > 1 for m in ranking.matches):
        best = ranking.matches[0].view.name
        return Guidance(title=f"No view for {tables} supports both extraction and delta loads",
                        tips=[f"Start with {best}, the highest ranked view.",
                              "If you need delta loads, plan a custom extraction view based on it."])
    return None
