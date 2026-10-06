"""Golden parity value sources and kind readers (docs/dev-guide.md §9.6 DG-PAR-05 and the kind
table; DG-KRN-EXP-03; BUILD_SPEC GPA-1).

``exact`` gives the full-precision value of an obligation version measure. An ``erev.exact`` column
is read as stored. An ``erev.money`` column is read from its trace node
``obligation_version.trace_nodes[m]`` as ``Fraction(Decimal(node.value)) +
Fraction(node.rounding_residue)``, because the posted column is rounded. [J] L5-1-Q-34: a money
column that ENGINE_SPEC defines as a posted amount, and that DG-OQ-05 does not list among the
measures with trace nodes, is its own exact value and is read as stored
(``original_total_contract_price`` = ``total.posted`` of the inception build-up, S05-R-16). Any
other money measure without a trace node has no DG-PAR-05 source, so the reader raises
:class:`ValueSourceError` instead of comparing a rounded amount.

``READERS`` maps each built kind to its reader. GPA-1 builds ``initial_allocation``, GPA-2
``contract_position``, GPA-3 ``cumulative_catchup`` and GPA-5 ``pob_position``. GPA-6 runs
``legacy_probe`` through ``support.parity.probes`` instead, because each probe has its own tenant. A
kind without a reader fails its cases and names the item that builds it (DG-PAR-09: nothing is
skipped). ``point_in_time_equivalence`` (GPB-3) is read and compared by
``support.parity.equivalence`` in its own tenant, like the probes.

``journal_entry_totals`` (GPB-1) is read and compared by ``journal_check``, because its values are
journal views rather than unit-level measures. After step ``steps_through`` the scenario runs report
``legacy_je_summary`` (RPT-13) through API-R-41 ``POST /report-runs`` with ``from_date =
window[0]``, ``to_date = window[1]``, book ``ASC606``, both entities, and ``mode`` ``GROSS`` (the
gross view) then ``DELTA`` (the adjustment view). ``journal_view`` reads a run's control totals and
its ``by_account`` and ``line_items`` rows; ``journal_mismatches`` compares ``lines``,
``by_account[] {account, debit, credit, net}``, ``total_debit``, ``total_credit``, ``net`` and
``line_items[] {key, account, amount}`` field by field, amounts exactly to the cent and codes,
keys and counts equal (DG-PAR-07). The probes of ``support.parity.probes`` reuse both.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Final, Protocol
from uuid import UUID

from erev_api.db.tables import obligation_version
from erev_api.db.types import ExactType, MoneyType
from support.factories import run_import_job
from support.legacy_replay import ENTITIES
from support.parity.compare import Mismatch, exact_equal, fraction_of, journal_equal
from support.parity.integrity import GoldenCase
from support.reference import get, post

if TYPE_CHECKING:
    from support.legacy_replay import LegacyWorld
    from support.parity.scenario import ParityScenario

__all__ = [
    "CUMULATIVE_CATCHUP",
    "INITIAL_ALLOCATION",
    "JOURNAL_KIND",
    "JOURNAL_MODES",
    "JOURNAL_REPORT",
    "PENDING",
    "POB_POSITION",
    "READERS",
    "JournalView",
    "NodeLookup",
    "TraceNodeLike",
    "ValueSourceError",
    "column_kind",
    "contract_position",
    "cumulative_catchup",
    "exact",
    "initial_allocation",
    "journal_check",
    "journal_entry_totals",
    "journal_mismatches",
    "journal_view",
    "node_exact",
    "pob_position",
    "run_journal",
]


class TraceNodeLike(Protocol):
    """The two members of an ``erev_engine.trace.TraceNode`` that DG-PAR-05 reads."""

    @property
    def value(self) -> str: ...

    @property
    def rounding_residue(self) -> str | None: ...


type NodeLookup = Callable[[str], TraceNodeLike | None]


class ValueSourceError(LookupError):
    """A measure without its DG-PAR-05 source."""


# Kind table: initial_allocation field -> obligation_version column.
INITIAL_ALLOCATION: Final[Mapping[str, str]] = {
    "ssp_midpoint": "original_ssp_mid",
    "extended_ssp": "original_ssp_selected",
    "allocation": "original_allocated_exact",
    "contract_price": "original_total_contract_price",
    "contract_ssp": "original_total_contract_ssp",
}
# Kind table: cumulative_catchup field -> obligation_version column.
CUMULATIVE_CATCHUP: Final[Mapping[str, str]] = {
    "catchup": "catch_up_amount",
    "remaining_allocation": "remaining_allocation",
    "revenue_cum": "revenue_cum",
}
# Kind table: pob_position field -> obligation_version column read by ``exact``. ``Final
# allocation (rev cum + remaining)`` is the sum of two of them, and ``Billing cum`` is
# ``billed_cum`` as stored, as in ``contract_position``.
POB_POSITION: Final[Mapping[str, str]] = {
    "Original allocation": "original_allocated_exact",
    "Qty delivered cum": "delivered_quantity_cum",
    "Revenue cum": "revenue_cum",
    "Remaining qty": "remaining_quantity",
    "Remaining allocation": "remaining_allocation",
    "Position POB": "position_obligation",
    "Catch-up cum (disclosure)": "catch_up_cum",
}
# erev.money columns that ENGINE_SPEC defines as posted amounts, without a DG-OQ-05 trace node.
POSTED_MEASURES: Final = frozenset({"original_total_contract_price"})  # S05-R-16, S06-R-31
# Kinds whose reader a later item builds (BUILD_SPEC §13): none since GPB-3, whose kind
# ``point_in_time_equivalence`` ``support.parity.equivalence`` reads in its own tenant.
PENDING: Final[Mapping[str, str]] = {}
# Kind table row ``journal_entry_totals`` (BUILD_SPEC GPB-1).
JOURNAL_KIND: Final = "journal_entry_totals"
JOURNAL_REPORT: Final = "legacy_je_summary"  # RPT-13
JOURNAL_BOOK: Final = "ASC606"
# Expected view name -> report parameter ``mode`` (gross view, adjustment view).
JOURNAL_MODES: Final[Mapping[str, str]] = {"gross": "GROSS", "delta": "DELTA"}
JOURNAL_MONEY: Final = frozenset({"debit", "credit", "net", "amount"})
REPORT_RUNS: Final = "/api/v1/report-runs"
REPORT_RUN_ID_HEADER: Final = "x-erev-report-run-id"
DATA_PAGE_LIMIT: Final = 200
# [J] A window without lines holds no currency row, so its totals read zero at the minor unit of
# the parity world's one currency, USD (L6-3-Q-36).
NO_LINES_TOTAL: Final = "0.00"


def column_kind(column: str) -> str:
    """``exact`` or ``money``: the domain type of an ``obligation_version`` column."""
    if column not in obligation_version.c:
        raise ValueSourceError(f"obligation_version has no column {column}")
    kind = obligation_version.c[column].type
    if isinstance(kind, ExactType):
        return "exact"
    if isinstance(kind, MoneyType):
        return "money"
    raise ValueSourceError(f"obligation_version.{column} is neither erev.exact nor erev.money")


def node_exact(node: TraceNodeLike) -> Fraction:
    """DG-KRN-EXP-03: the exact value of a trace node is ``value + rounding_residue``."""
    value = Fraction(Decimal(node.value))
    if node.rounding_residue is not None:
        value += Fraction(Decimal(node.rounding_residue))
    return value


def exact(row: Mapping[str, Any], column: str, nodes: NodeLookup) -> Fraction | None:
    """DG-PAR-05 ``exact(m)`` of one obligation version row."""
    if column_kind(column) == "exact" or column in POSTED_MEASURES:
        stored = row[column]
        return None if stored is None else Fraction(Decimal(str(stored)))
    names: Mapping[str, Any] = row.get("trace_nodes") or {}
    node_id = names.get(column)
    if not isinstance(node_id, str):
        raise ValueSourceError(
            f"obligation_version.trace_nodes has no node for the erev.money column {column} "
            "(DG-PAR-05, DG-OQ-05)"
        )
    node = nodes(node_id)
    if node is None:
        raise ValueSourceError(f"trace node {node_id} of {column} is not in the calc_trace")
    return node_exact(node)


def initial_allocation(scenario: ParityScenario, case: GoldenCase) -> dict[str, Fraction | None]:
    """Kind ``initial_allocation``: the obligation version of ``contract``, ``pob`` in the first
    contract version produced by step ``steps_through``."""
    assert case.contract is not None and case.pob is not None and case.steps_through is not None
    row, nodes = scenario.first_obligation_version(case.contract, case.pob, case.steps_through)
    return {name: exact(row, column, nodes) for name, column in INITIAL_ALLOCATION.items()}


def _total(
    rows: Sequence[Mapping[str, Any]], column: str, nodes: NodeLookup, *, stored: bool = False
) -> Fraction:
    """Σ over ``rows`` of ``exact(column)``, or of the stored column when ``stored``."""
    total = Fraction(0)
    for row in rows:
        value = (
            (None if row[column] is None else Fraction(Decimal(str(row[column]))))
            if stored
            else exact(row, column, nodes)
        )
        if value is None:
            raise ValueSourceError(f"obligation {row['obligation_key']} has no {column}")
        total += value
    return total


def contract_position(scenario: ParityScenario, case: GoldenCase) -> dict[str, Fraction | None]:
    """Kind ``contract_position``: sums over the latest obligation versions of every obligation of
    ``contract`` after step ``steps_through``. ``contract_asset`` is CONTRACT_ASSET +
    UNBILLED_RECEIVABLE combined (D-15)."""
    assert case.contract is not None and case.steps_through is not None
    rows, nodes = scenario.latest_obligation_versions(case.contract, case.steps_through)
    revenue = _total(rows, "revenue_cum", nodes)
    billed = _total(rows, "billed_cum", nodes, stored=True)
    remaining = _total(rows, "remaining_allocation", nodes)
    position = _total(rows, "position_obligation", nodes)
    return {
        "tp_allocation_basis": revenue + remaining,
        "tp_billing_basis": billed + _total(rows, "remaining_billing", nodes),
        "revenue_cum": revenue,
        "billing_cum": billed,
        "remaining_allocation": remaining,
        "position": position,
        "contract_liability": max(position, Fraction(0)),
        "contract_asset": max(-position, Fraction(0)),
        "uar_reclass_field": _total(rows, "netting_reclass_amount", nodes),
        "catchup_cum_disclosure": _total(rows, "catch_up_cum", nodes),
    }


def cumulative_catchup(scenario: ParityScenario, case: GoldenCase) -> dict[str, Fraction | None]:
    """Kind ``cumulative_catchup``: the obligation version of ``contract``, ``pob`` in the contract
    version created by the modification of step ``steps_through``. ``catchup`` is the exact
    ``catch_up_amount``, Σ CU_exact of the events first included in that version (ENGINE_SPEC
    Table 0.9-A)."""
    assert case.contract is not None and case.pob is not None and case.steps_through is not None
    row, nodes = scenario.modification_obligation_version(
        case.contract, case.pob, case.steps_through
    )
    return {name: exact(row, column, nodes) for name, column in CUMULATIVE_CATCHUP.items()}


def pob_position(scenario: ParityScenario, case: GoldenCase) -> dict[str, Fraction | None]:
    """Kind ``pob_position``: the latest obligation version of ``contract``, ``pob`` after step
    ``steps_through``, which is the obligation's row in the latest contract version of the group
    (``latest_obligation_versions``). For an obligation added by a modification, ``Original
    allocation`` is the creation-time allocation (DEV-052; D-75, OQ-D5)."""
    assert case.contract is not None and case.pob is not None and case.steps_through is not None
    rows, nodes = scenario.latest_obligation_versions(case.contract, case.steps_through)
    matching = [row for row in rows if row["obligation_key"] == case.pob]
    if len(matching) != 1:
        raise ValueSourceError(
            f"the latest version of {case.contract} after step {case.steps_through} holds "
            f"{len(matching)} obligation versions of {case.pob}, not one"
        )
    (row,) = matching
    found = {name: exact(row, column, nodes) for name, column in POB_POSITION.items()}
    revenue, remaining = found["Revenue cum"], found["Remaining allocation"]
    found["Final allocation (rev cum + remaining)"] = (
        None if revenue is None or remaining is None else revenue + remaining
    )
    found["Billing cum"] = _total((row,), "billed_cum", nodes, stored=True)
    return found


type Reader = Callable[["ParityScenario", GoldenCase], Mapping[str, Fraction | None]]
READERS: Final[Mapping[str, Reader]] = {
    "initial_allocation": initial_allocation,
    "contract_position": contract_position,
    "cumulative_catchup": cumulative_catchup,
    "pob_position": pob_position,
}


# --- journal_entry_totals (BUILD_SPEC GPB-1) -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class JournalView:
    """One ``legacy_je_summary`` run in the shape of the kind table: amounts as the report's
    decimal strings."""

    lines: int
    by_account: tuple[Mapping[str, str], ...]  # account, debit, credit, net
    total_debit: str
    total_credit: str
    net: str
    line_items: tuple[Mapping[str, str], ...]  # key, account, amount


def _amount(value: Any) -> str:
    """The ``amount`` of an API-S-Money object, or a plain decimal string."""
    return str(value["amount"]) if isinstance(value, Mapping) else str(value)


def journal_view(
    control_totals: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]
) -> JournalView:
    """The kind-table members of a ``legacy_je_summary`` run's control totals and data rows (RPT-13
    sections ``by_account`` and ``line_items``; ``by_entity`` is not asserted)."""
    currencies: set[str] = set()
    for name in ("total_debit", "total_credit", "net"):
        currencies |= set(control_totals.get(name) or {})
    if len(currencies) > 1:
        raise ValueSourceError(f"the journal view holds several currencies {sorted(currencies)}")
    currency = next(iter(currencies), None)

    def total(name: str) -> str:
        found: Mapping[str, Any] = control_totals.get(name) or {}
        return NO_LINES_TOTAL if currency is None else str(found[currency])

    by_account = tuple(
        {
            "account": str(row["account"]),
            "debit": _amount(row["debit"]),
            "credit": _amount(row["credit"]),
            "net": _amount(row["net"]),
        }
        for row in rows
        if row["section"] == "by_account"
    )
    line_items = tuple(
        {"key": str(row["key"]), "account": str(row["account"]), "amount": _amount(row["amount"])}
        for row in rows
        if row["section"] == "line_items"
    )
    return JournalView(
        lines=int(control_totals.get("lines") or 0),
        by_account=by_account,
        total_debit=total("total_debit"),
        total_credit=total("total_credit"),
        net=total("net"),
        line_items=line_items,
    )


def _member_equal(name: str, actual: object, expected: object) -> bool:
    if name in JOURNAL_MONEY:
        return isinstance(actual, str) and journal_equal(fraction_of(actual), expected)
    return exact_equal(actual, expected)


def _journal_rows(
    field: str,
    expected: Any,
    actual: Sequence[Mapping[str, str]],
    legacy: Any,
) -> list[Mismatch]:
    """An ordered list of journal rows, member by member (DG-PAR-07)."""
    old = legacy if isinstance(legacy, list) else []
    if not isinstance(expected, list):
        return [Mismatch(field, expected, "not a list of rows", legacy)]
    found: list[Mismatch] = []
    if len(expected) != len(actual):
        rendered = [" ".join(row.values()) for row in actual]
        found.append(Mismatch(f"{field}.count", len(expected), rendered, len(old) or None))
    for index, (want, got) in enumerate(zip(expected, actual, strict=False)):
        before = old[index] if index < len(old) and isinstance(old[index], Mapping) else {}
        for name, value in want.items():
            if not _member_equal(name, got.get(name), value):
                member = f"{field}[{index}].{name}"
                found.append(Mismatch(member, value, got.get(name), before.get(name)))
    return found


def journal_mismatches(
    expected: Mapping[str, Any],
    view: JournalView,
    *,
    prefix: str,
    legacy: Mapping[str, Any] | None = None,
) -> list[Mismatch]:
    """Every member of one expected journal view against ``view`` (kind table, DG-PAR-07). A member
    without a rule fails (DG-PAR-09)."""
    old: Mapping[str, Any] = legacy or {}
    found: list[Mismatch] = []
    for name, value in expected.items():
        field = f"{prefix}.{name}"
        match name:
            case "lines":
                if not exact_equal(view.lines, value):
                    found.append(Mismatch(field, value, view.lines, old.get(name)))
            case "total_debit" | "total_credit" | "net":
                actual = getattr(view, name)
                if not _member_equal(name if name == "net" else "amount", actual, value):
                    found.append(Mismatch(field, value, actual, old.get(name)))
            case "by_account" | "line_items":
                found.extend(_journal_rows(field, value, getattr(view, name), old.get(name)))
            case _:
                found.append(
                    Mismatch(field, value, "no journal_entry_totals rule for this key", None)
                )
    return found


def _data_rows(world: LegacyWorld, run_id: str) -> Iterator[Mapping[str, Any]]:
    cursor: str | None = None
    while True:
        query: dict[str, Any] = {"limit": str(DATA_PAGE_LIMIT)}
        if cursor is not None:
            query["cursor"] = cursor
        listed = get(world.app, f"{REPORT_RUNS}/{run_id}/data", world.maya, query)
        if listed.status_code != 200:
            raise ValueSourceError(f"report run {run_id} data answered {listed.text}")
        body = listed.json()
        yield from body["items"]
        cursor = body.get("next_cursor")
        if not cursor:
            return


def run_journal(world: LegacyWorld, window: tuple[str, str], mode: str) -> JournalView:
    """Report ``legacy_je_summary`` over ``window`` in ``mode`` for both entities in book ASC606,
    through API-R-41 and the job run as the worker runs it (module docstring)."""
    parameters = {
        "entity_codes": list(ENTITIES),
        "book": JOURNAL_BOOK,
        "from_date": window[0],
        "to_date": window[1],
        "mode": mode,
    }
    started = post(
        world.app,
        REPORT_RUNS,
        world.maya,
        {"report_code": JOURNAL_REPORT, "parameters": parameters, "output_format": "JSON"},
    )
    if started.status_code != 202:
        raise ValueSourceError(f"POST /report-runs answered {started.status_code}: {started.text}")
    run_import_job(world.imports, UUID(str(started.json()["id"])))
    run_id = str(started.headers[REPORT_RUN_ID_HEADER])
    shown = get(world.app, f"{REPORT_RUNS}/{run_id}", world.maya)
    if shown.status_code != 200:
        raise ValueSourceError(f"report run {run_id} answered {shown.text}")
    run = shown.json()
    if run["status"] != "SUCCEEDED":
        raise ValueSourceError(f"report run {run_id} ended {run['status']}: {run.get('problem')}")
    return journal_view(run["control_totals"], list(_data_rows(world, run_id)))


def journal_entry_totals(scenario: ParityScenario, case: GoldenCase) -> dict[str, JournalView]:
    """Kind ``journal_entry_totals``: the gross and adjustment views over ``window`` after step
    ``steps_through``."""
    assert case.steps_through is not None and case.window is not None
    scenario.through(case.steps_through)
    return {
        name: run_journal(scenario.world, case.window, mode) for name, mode in JOURNAL_MODES.items()
    }


def journal_check(scenario: ParityScenario, case: GoldenCase) -> list[Mismatch]:
    """Every expected view of a ``journal_entry_totals`` case against the report runs."""
    views = journal_entry_totals(scenario, case)
    found: list[Mismatch] = []
    for name, expected in case.expected.items():
        view = views.get(name)
        legacy = case.legacy.get(name)
        if view is None or not isinstance(expected, Mapping):
            found.append(Mismatch(name, expected, "no journal view of this name", legacy))
            continue
        found.extend(
            journal_mismatches(
                expected, view, prefix=name, legacy=legacy if isinstance(legacy, Mapping) else None
            )
        )
    return found
