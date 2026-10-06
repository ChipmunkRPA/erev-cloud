"""Trace-link checks of one ``BookOutput`` (DG-KRN-EXP-01 to 03; ENGINE_SPEC CV-50 links; D-97 (8);
BUILD_SPEC END-13; lane ENG-T1F).

``check_book`` enumerates the expected value columns of every T-CON-11 obligation version, the
T-CON-08 contract version and every T-CON-09 balance row the book publishes (``erev.money`` and
``erev.exact`` columns with a stored value, zeros included) and asserts, per column: a link exists
(unless the column is a documented exception), the linked node exists in the book's trace, its
measure is the column or the column's boundary form ``<column>@<event key>``, its subject is the
row's subject, its value ties to the stored value (posted minor units for money, the 18-place
encoding for exact values), its currency is the row's transaction currency (functional columns:
the functional currency), and a boundary node is the LAST reallocating boundary of that column on
or before the version date (T1-F-2). A detached, mistargeted or stale link fails with the family,
subject and column named.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import BookOutput, InputBundle
from erev_engine.money import EXACT_PLACES, to_fraction
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.trace import (
    ABSENT_PREFIX,
    TraceNode,
    absence_state,
    exact_companion_failures,
    reevaluate,
)
from support.answer_keys import loader

__all__ = [
    "ALIASES",
    "DIMENSIONLESS_EXACT_COLUMNS",
    "MONEY_EXACT_COLUMNS",
    "VALUE_TYPES",
    "Exceptions",
    "balance_link_columns",
    "check_book",
    "check_sources",
    "expected_columns",
]

VALUE_TYPES: Final = frozenset({"erev.money", "erev.exact"})
ENCODING_HALF_UNIT: Final = Fraction(1, 2 * 10**EXACT_PLACES)
# R-SGN-01 / L4-3-Q-33: the column is the magnitude of the signed build-up member.
MAGNITUDE_CONTRACT_COLUMNS: Final = frozenset({"vc_constrained_amount"})
# T-CON-11 columns defined over the obligation's contract and contracting entity: their node's
# subject is the member ``<contract>@<entity>`` (REQ-ENT-002; ``position_contract_entity``).
MEMBER_SUBJECT_COLUMNS: Final = frozenset({"position_contract_entity"})
FUNCTIONAL: Final = "_functional"
# CV-50 / DG-KRN-EXP-02: the period slot of a version-date re-measurement beside a boundary node
# of the same event and measure (``allocation_adjustment@<event>:<ob>:returns``).
RETURNS_QUALIFIER: Final = "returns"
# T1F-Q5-G1 (Codex; supervisor ruling): the two classes partition the ``erev.exact`` columns of
# T-CON-08 and T-CON-11. A money class node carries the transaction currency (an exact amount, a
# unit price or a per-unit rate in transaction currency); a dimensionless class node carries none
# (quantities, allocation weights, ratios). An exact column in neither class fails as unclassified,
# so a new exact column is classified before the checker accepts it (test_trace_linkage pins the
# partition against the loader's column tables).
MONEY_EXACT_COLUMNS: Final = frozenset(
    {
        "allocated_exact",
        "original_allocated_exact",
        "original_ssp_high",
        "original_ssp_low",
        "original_ssp_mid",
        "original_ssp_selected",
        "original_total_contract_ssp",
        "original_unit_revenue_rate",
        "original_unit_ssp",
        "remaining_ssp",
        "remaining_unit_revenue_rate",
        "ssp_delivered",
        "ssp_delivered_cum",
        "ssp_unit_list_price",
        "total_ssp",
        "unit_ssp",
    }
)
DIMENSIONLESS_EXACT_COLUMNS: Final = frozenset(
    {
        "allocation_weight",
        "delivered_quantity",
        "delivered_quantity_cum",
        "original_quantity",
        "progress_ratio",
        "quantity",
        "remaining_quantity",
        "returned_quantity_cum",
        "ssp_midpoint_discount_ratio",
        "ssp_range_ratio",
    }
)
TXN: Final = "_txn"

# family -> columns documented as unlinked (ENGINE_SPEC CV-50 links: "only explicitly documented
# exceptions stay unlinked"). Empty until a ruling documents one.
Exceptions = Mapping[str, frozenset[str]]
NO_EXCEPTIONS: Final[Exceptions] = {}


def expected_columns(columns: Mapping[str, object], types: Mapping[str, str]) -> set[str]:
    """The value-typed columns of ``types`` the row publishes with a stored value (zeros too)."""
    return {
        name
        for name, held in columns.items()
        if held is not None and types.get(name) in VALUE_TYPES
    }


def balance_link_columns(columns: Mapping[str, object]) -> dict[str, str]:
    """T-CON-09 link key → column. A ``<measure>_txn`` column links under ``<measure>`` (the key
    stage 10 publishes today; the explain service reconstructs ``<measure>:<subject>:<period>``);
    a ``<measure>_functional`` column links under its full name."""
    found: dict[str, str] = {}
    for name, held in columns.items():
        if not isinstance(held, int) or isinstance(held, bool):
            continue
        if name.endswith(TXN):
            found[name[: -len(TXN)]] = name
        elif name.endswith(FUNCTIONAL):
            found[name] = name
    return found


def _posted(node: TraceNode, minor_unit: int, where: tuple[object, ...]) -> int:
    scaled = to_fraction(node.value) * 10**minor_unit
    assert scaled.denominator == 1, (*where, node.id, "not a whole number of minor units")
    return scaled.numerator


def _subject_of(node_id: str) -> tuple[str, str]:
    """(subject, period) of a node id ``<measure>:<subject>:<period or '-'>`` (CV-50; the measure
    never contains ':' and the subject is CV-21 encoded, so the first and last ':' delimit)."""
    _, rest = node_id.split(":", 1)
    subject, period = rest.rsplit(":", 1)
    return subject, period


def _boundary_event(measure: str) -> str | None:
    return measure.split("@", 1)[1] if "@" in measure else None


# CV-53 aliases (D-98 candidate 23, T1F-Q-5): a column that links the node of another measure
# because that node produced its value — one value, one node.
ALIASES: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {"original_ssp_selected": frozenset({"residual_ssp"})}
)


def _assert_measure(node: TraceNode, column: str, where: tuple[object, ...]) -> None:
    ok = (
        node.measure == column
        or node.measure.startswith(f"{column}@")
        or node.measure in ALIASES.get(column, frozenset())
    )
    assert ok, (*where, f"link names measure {node.measure!r}, not {column!r}")


def _assert_last_boundary(
    nodes: Mapping[str, TraceNode],
    node: TraceNode,
    column: str,
    subject: str,
    period: str,
    dates: Mapping[str, date],
    as_of: date | None,
    where: tuple[object, ...],
) -> None:
    """A boundary link names the latest ``<column>@<event>`` node of the subject on or before the
    version date (never an earlier boundary; the inception node when they differ is caught by the
    value tie)."""
    event = _boundary_event(node.measure)
    if event is None:
        return
    assert event in dates, (*where, f"boundary event {event!r} is not an event of the bundle")
    if as_of is not None:
        assert dates[event] <= as_of, (*where, f"boundary {event!r} is after the version date")
    later = [
        other.id
        for other in nodes.values()
        if other.measure.startswith(f"{column}@")
        and _subject_of(other.id)[0] == subject
        and (_boundary_event(other.measure) or "") in dates
        and dates[_boundary_event(other.measure) or ""] > dates[event]
        and (as_of is None or dates[_boundary_event(other.measure) or ""] <= as_of)
    ]
    assert later == [], (*where, f"a later boundary node exists: {later}")


def _assert_exact(
    node: TraceNode, held: object, where: tuple[object, ...], column: str, currency: str
) -> None:
    """An ``erev.exact`` link holds the stored value and the right currency for its class
    (T1F-Q5-G1): the transaction currency on a money column, none on a dimensionless one."""
    if column in MONEY_EXACT_COLUMNS:
        assert node.currency == currency, (
            *where,
            f"node currency {node.currency!r} on the exact money column (expected {currency!r})",
        )
    elif column in DIMENSIONLESS_EXACT_COLUMNS:
        assert node.currency is None, (
            *where,
            f"node currency {node.currency!r} on a dimensionless exact column (expected none)",
        )
    else:
        raise AssertionError(
            (*where, f"exact column {column!r} is classified neither as money nor as dimensionless")
        )
    assert isinstance(held, Fraction | Decimal | int) and not isinstance(held, bool), where
    assert abs(to_fraction(node.value) - to_fraction(held)) <= ENCODING_HALF_UNIT, (
        *where,
        f"node {node.id} = {node.value}, column = {held}",
    )


def _assert_money(
    node: TraceNode, held: object, minor_unit: int, where: tuple[object, ...], *, magnitude: bool
) -> None:
    assert isinstance(held, int) and not isinstance(held, bool), (*where, "not integer minor units")
    posted = _posted(node, minor_unit, where)
    assert (abs(posted) if magnitude else posted) == held, (
        *where,
        f"node {node.id} = {posted}, column = {held}",
    )


def _event_dates(bundle: InputBundle) -> Mapping[str, date]:
    return {event.event_key: event.effective_date for event in bundle.events}


def check_book(
    book: BookOutput,
    bundle: InputBundle,
    *,
    exceptions: Exceptions = NO_EXCEPTIONS,
    sources: bool = True,
) -> None:
    """Assert the DG-KRN-EXP-01 links of every published value column of ``book`` (see module)
    and the canonical-member rule of every source reference (CV-53; ``check_sources``)."""
    nodes = {node.id: node for node in book.trace.nodes}
    currency = bundle.group.transaction_currency
    minor_units = {code: item.minor_unit for code, item in bundle.currencies.items()}
    dates = _event_dates(bundle)
    _check_obligation_versions(book, nodes, currency, minor_units[currency], dates, exceptions)
    _check_contract_version(book, nodes, currency, minor_units[currency], dates, exceptions)
    _check_balances(book, nodes, currency, minor_units, exceptions)
    # ENGINE_SPEC CV-64 rev 1.30: every posted node naming an exact companion reconstructs it,
    # and the companion replays (the residue is trace data reevaluate never recomputes).
    companions = exact_companion_failures(book.trace, reevaluate(book.trace))
    assert companions == [], (book.book_code, "exact companions", companions[:8])
    if sources:
        check_sources(book, bundle)


ECHO_FORMULA: Final = "input.echo.v1"
# T-CON-11 SSP snapshot columns: their nodes cite canonical ``ssp_entry`` / ``ssp_range`` members
# (lane ENG-T1F; Codex T1F-R1).
SNAPSHOT_MEASURES: Final = frozenset(
    {
        "ssp_unit_list_price",
        "ssp_midpoint_discount_ratio",
        "ssp_range_ratio",
        "original_ssp_mid",
        "original_ssp_high",
        "original_ssp_low",
    }
)


def _decimal_equal(cited: str, held: object) -> bool:
    return to_fraction(cited) == to_fraction(held)  # type: ignore[arg-type]


def check_sources(book: BookOutput, bundle: InputBundle) -> list[str]:
    """CV-53 (Codex T1F-R1): a source ``member`` names only a canonical input member that holds
    the cited value. Checked for every source of an ``input.echo.v1`` node and of a SSP snapshot
    node (``SNAPSHOT_MEASURES``), resolved against the input bundle (member exists AND value
    equals, compared as numbers). An ``input.echo.v1`` node cites exactly one node or one
    member-bearing source. Other stages' details that label derived amounts with ``member``
    (stage 10 billing ``unconditional_billing`` / ``unreferenced_total`` / ``amount`` / ``tax``;
    stage 06 legacy templates ``mod_ssp@`` ``line:<i>``) predate the lane and are outside its
    scope (recorded for the supervisor). Returns the sorted offending ``<node id> -> <ref>``
    list and asserts it is empty."""
    entries = {
        entry.entry_key: entry for version in bundle.ssp_versions for entry in version.entries
    }
    events = {event.event_key: event for event in bundle.events}
    failures: list[str] = []
    for node in book.trace.nodes:
        sources = [item for item in node.inputs if not isinstance(item, str)]
        echo = node.formula_id == ECHO_FORMULA
        if echo and (len(node.inputs) != 1 or (sources and "member" not in sources[0].detail)):
            failures.append(f"{node.id} -> echo without one node or one member source")
        for ref in sources:
            member = ref.detail.get("member")
            in_scope = echo or node.measure in SNAPSHOT_MEASURES
            if member is None or not in_scope:
                continue
            cited = ref.detail.get("value")
            held: object = None
            if ref.ref_type == "ssp_entry":
                entry = entries.get(ref.ref_id)
                found = entry is not None and hasattr(entry, member)
                held = getattr(entry, member, None) if found else None
            elif ref.ref_type == "ssp_range":
                head, _, band_from = ref.ref_id.rpartition("/")
                entry_key, _, dimension = head.rpartition("/")
                entry = entries.get(entry_key)
                row = None
                for candidate in () if entry is None else entry.ranges:
                    start = "" if candidate.band_from is None else str(candidate.band_from)
                    if candidate.band_dimension == dimension and start == band_from:
                        row = candidate
                        break
                found = row is not None and hasattr(row, member)
                held = getattr(row, member, None) if found else None
            elif ref.ref_type == "contract_event":
                event = events.get(ref.ref_id)
                found = event is not None and member in event.payload
                held = event.payload.get(member) if found else None
            else:
                failures.append(f"{node.id} -> {ref.ref_type} {ref.ref_id!r}.{member}: unresolved")
                continue
            where = f"{node.id} -> {ref.ref_type} {ref.ref_id!r}"
            if not found:
                failures.append(f"{where} has no member {member!r}")
            elif held is None or cited is None or not _decimal_equal(cited, held):
                failures.append(f"{where}.{member} = {held!r}, cited {cited!r}")
    failures.sort()
    assert failures == [], (book.book_code, len(failures), failures[:8])
    return failures


def _check_obligation_versions(
    book: BookOutput,
    nodes: Mapping[str, TraceNode],
    currency: str,
    minor_unit: int,
    dates: Mapping[str, date],
    exceptions: Exceptions,
) -> None:
    types = loader.obligation_columns()
    allowed = exceptions.get("obligation_version", frozenset())
    for item in book.obligation_versions:
        where: tuple[object, ...] = ("obligation_version", book.book_code, item.subject_key)
        as_of = item.columns.get("effective_date")
        expected = expected_columns(item.columns, types) - allowed
        missing = sorted(expected - set(item.trace_nodes))
        assert missing == [], (*where, "unlinked value columns", missing)
        for column, node_id in item.trace_nodes.items():
            at = (*where, column)
            if node_id.startswith(ABSENT_PREFIX):
                # CV-50 rev 1.29: a contract-permitted absence published AS the link (DEV-054's
                # Σw = 0 ratio; a LEGACY-VC created line) — the one reason admitted for this
                # column, by identity, over the column's 0 display; never a node, never an
                # exception.
                assert absence_state(column, node_id, item.columns[column]) == "absent", (
                    *at,
                    f"absence {node_id!r} is not admitted for this column over "
                    f"{item.columns[column]!r} (the shared recognition: identity + the 0 display)",
                )
                continue
            node = nodes.get(node_id)
            assert node is not None, (*at, f"link {node_id!r} is not a node of the trace")
            _assert_measure(node, column, at)
            subject, period = _subject_of(node.id)
            expected_subject = item.subject_key
            if column in MEMBER_SUBJECT_COLUMNS:
                contract_key = item.subject_key.rsplit("/", 1)[0]
                entity = str(item.columns["contracting_entity_code"])
                expected_subject = contract_entity_subject_key(contract_key, entity)
            qualified = period == RETURNS_QUALIFIER and "@" in node.measure  # CV-50 qualifier
            assert subject == expected_subject and (period == "-" or qualified), (
                *at,
                f"link {node_id!r} is not a version-state node of the obligation",
            )
            _assert_last_boundary(nodes, node, column, subject, period, dates, _date(as_of), at)
            kind = types.get(column)
            if kind == "erev.money":
                assert node.currency == currency, (*at, f"node currency {node.currency!r}")
                _assert_money(node, item.columns[column], minor_unit, at, magnitude=False)
            elif kind == "erev.exact":
                _assert_exact(node, item.columns[column], at, column, currency)


def _check_contract_version(
    book: BookOutput,
    nodes: Mapping[str, TraceNode],
    currency: str,
    minor_unit: int,
    dates: Mapping[str, date],
    exceptions: Exceptions,
) -> None:
    version = book.contract_version
    if version is None:
        return
    types = loader.contract_version_columns()
    allowed = exceptions.get("contract_version", frozenset())
    where: tuple[object, ...] = ("contract_version", book.book_code, version.subject_key)
    expected = expected_columns(version.columns, types) - allowed
    missing = sorted(expected - set(version.trace_nodes))
    assert missing == [], (*where, "unlinked value columns", missing)
    as_of = max(
        (item.columns.get("effective_date") for item in book.obligation_versions), default=None
    )
    for column, node_id in version.trace_nodes.items():
        at = (*where, column)
        node = nodes.get(node_id)
        assert node is not None, (*at, f"link {node_id!r} is not a node of the trace")
        _assert_measure(node, column, at)
        subject, period = _subject_of(node.id)
        qualified = period == RETURNS_QUALIFIER and "@" in node.measure  # CV-50 qualifier
        assert subject == version.subject_key and (period == "-" or qualified), (
            *at,
            f"link {node_id!r} is not a version-state node of the group",
        )
        _assert_last_boundary(nodes, node, column, subject, period, dates, _date(as_of), at)
        kind = types.get(column)
        if kind == "erev.money":
            assert node.currency == currency, (*at, f"node currency {node.currency!r}")
            _assert_money(
                node,
                version.columns[column],
                minor_unit,
                at,
                magnitude=column in MAGNITUDE_CONTRACT_COLUMNS,
            )
        elif kind == "erev.exact":
            _assert_exact(node, version.columns[column], at, column, currency)


def _check_balances(
    book: BookOutput,
    nodes: Mapping[str, TraceNode],
    currency: str,
    minor_units: Mapping[str, int],
    exceptions: Exceptions,
) -> None:
    allowed = exceptions.get("contract_version_balance", frozenset())
    types = loader.balance_columns()
    for row in book.balances:
        where: tuple[object, ...] = (
            "contract_version_balance",
            book.book_code,
            row.subject_key,
            row.period_key,
        )
        links = balance_link_columns(row.columns)
        unknown = sorted(column for column in links.values() if column not in types)
        assert unknown == [], (*where, "columns outside T-CON-09", unknown)
        missing = sorted(
            column
            for key, column in links.items()
            if column not in allowed and key not in row.trace_nodes
        )
        assert missing == [], (*where, "unlinked value columns", missing)
        functional = str(row.columns["functional_currency"])
        for key, node_id in row.trace_nodes.items():
            column = links.get(key)
            at = (*where, key)
            assert column is not None, (*at, "link without a published column")
            node = nodes.get(node_id)
            assert node is not None, (*at, f"link {node_id!r} is not a node of the trace")
            base = key[: -len(FUNCTIONAL)] if key.endswith(FUNCTIONAL) else key
            assert node.measure in (key, base), (*at, f"link names measure {node.measure!r}")
            subject, period = _subject_of(node.id)
            assert (subject, period) == (row.subject_key, row.period_key), (
                *at,
                f"link {node_id!r} is not a node of the member and period",
            )
            expected_currency = functional if key.endswith(FUNCTIONAL) else currency
            assert node.currency == expected_currency, (*at, f"node currency {node.currency!r}")
            _assert_money(
                node, row.columns[column], minor_units[expected_currency], at, magnitude=False
            )


def _date(value: object) -> date | None:
    return value if isinstance(value, date) else None


def unlinked_summary(book: BookOutput) -> dict[str, list[str]]:
    """Per family, the sorted value columns without a link (for records and fail-first logs)."""
    otypes, ctypes = loader.obligation_columns(), loader.contract_version_columns()
    out: dict[str, set[str]] = {
        "obligation_version": set(),
        "contract_version": set(),
        "contract_version_balance": set(),
    }
    for item in book.obligation_versions:
        out["obligation_version"] |= expected_columns(item.columns, otypes) - set(item.trace_nodes)
    if book.contract_version is not None:
        out["contract_version"] |= expected_columns(book.contract_version.columns, ctypes) - set(
            book.contract_version.trace_nodes
        )
    for row in book.balances:
        links = balance_link_columns(row.columns)
        out["contract_version_balance"] |= {c for k, c in links.items() if k not in row.trace_nodes}
    return {family: sorted(columns) for family, columns in out.items()}


def iter_books(
    bundle: InputBundle, books: Iterable[BookOutput]
) -> Iterable[tuple[str, BookOutput]]:
    for book in books:
        yield book.book_code, book
