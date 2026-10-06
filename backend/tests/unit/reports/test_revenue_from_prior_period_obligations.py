"""RPT-05 ``revenue_from_prior_period_obligations`` pure core, registration and specification
cross-check (SCREENS_B §5.6.1 RPT-05 rev 1.12 and 1.16; ENGINE_SPEC_B §15.2.4 S15-R-13, S15-R-14,
§15.2.7 ``PRIOR_PERIOD_POB_REVENUE``; 04 T-CLS-05 rev 1.40 and 1.51; D-98 candidates 85, 87, 96,
104; Codex C4-PP-R1, C4-PP-R2; lane ENG-C4).

No database. Two sources feed the pure half: ``revenue_prior_period`` nodes built here as stage 08
emits them (parts as ``contract_event`` source references with ``rule_<k>`` / ``version_<k>``
params; late carries as ``late_*`` params), and ACTUAL native traces computed by the engine over
``support.prior_period_worlds`` — the admitted cross-entity, distinct-calendar world whose stage 15
sum node lives under the CONTRACTING entity (C4-PP-R1). The fixture header carries the KeySpec
names. ``build`` (the database reader) is exercised by
``tests/domain/reports/test_prior_period_report.py`` in an admitted DB slot.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Final, cast
from uuid import UUID, uuid4

import erev_engine
import pytest
from erev_api.domain.reports import framework
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import revenue_from_prior_period_obligations as pp
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE
from erev_api.problems import Problem
from erev_engine.bundle import BookOutput, OutputBundle
from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    contract_subject_key,
    encode_key,
    obligation_subject_key,
)
from erev_engine.stages.s08_estimates_late_events import decompose
from erev_engine.stages.s15_disclosures.prior_period import MEASURE, SUM_MEASURE
from erev_engine.trace import SourceRef, TraceNode
from support import prior_period_worlds as worlds
from support.architecture import read

ENTITY: Final = "AVM-DE"
CONTRACT: Final = "NS-SO-DE-5002"
P09, P10 = "FY2026-P09", "FY2026-P10"
EVENT_TYPES: Final[Mapping[str, str]] = {
    f"{CONTRACT}/EV-000004": "ESTIMATE_CHANGED",
    f"{CONTRACT}/EV-000005": "ESTIMATE_CHANGED",
    f"{CONTRACT}/EV-000006": "CONTRACT_AMENDED",
    f"{CONTRACT}/EV-000007": "CONTRACT_AMENDED",
    f"{CONTRACT}/EV-000008": "CONTRACT_TERMINATED",
}
RPT_05: Final = (
    "##### RPT-05 `revenue_from_prior_period_obligations` Revenue from obligations satisfied in "
    "prior periods"
)
# The "Satisfied in" row renders the key through its label ("`satisfied_period_key` → label").
_GRID_ROW: Final = re.compile(r"^\| ([A-Z0-9][^|`]*?) \| `([a-z_0-9]+)`(?: → label)? \|")
FEBRUARY: Final = "FY2026-P02"  # US01's February and US02's second quarter share this key string


def _node(
    obligation_key: str,
    period: str,
    value: str,
    parts: Sequence[tuple[str, str, str, str | None]] = (),
    carries: Sequence[tuple[str, int, int]] = (),
) -> TraceNode:
    """A stage 08 ``revenue_prior_period`` node: ``parts`` are (event key, amount, rule, EAC
    version), ``carries`` are (origin period, target minor, posted minor)."""
    params: dict[str, str] = {
        "as_of": "2026-08-31",
        "boundaries": str(len(parts)),
        "carries": str(len(carries)),
        "period_start": "2026-09-01",
    }
    inputs: list[str | SourceRef] = []
    for index, (event_key, amount, rule, version) in enumerate(parts, start=1):
        params[f"e_after_{index}"] = "0"
        params[f"e_before_{index}"] = "0"
        params[f"rule_{index}"] = rule
        if version is not None:
            params[f"version_{index}"] = version
        inputs.append(
            SourceRef("contract_event", event_key, {"member": "prior_period_part", "value": amount})
        )
    for index, (origin, target, posted) in enumerate(carries, start=1):
        params[f"late_origin_{index}"] = origin
        params[f"late_target_{index}"] = str(target)
        params[f"late_posted_{index}"] = str(posted)
    subject = obligation_subject_key(CONTRACT, obligation_key)
    return TraceNode(
        id=f"{MEASURE}:{subject}:{period}",
        measure=MEASURE,
        value=value,
        currency="USD",
        formula_id="estimate.prior_period.v1",
        inputs=tuple(inputs),
        params=params,
        rounding_residue=None,
        narrative_key="estimate.prior_period",
    )


def _ref(
    obligation_key: str,
    period: str,
    node: TraceNode,
    *,
    product: str | None = "SVC-DE",
    satisfied: str | None = None,
) -> pp.NodeRef:
    return pp.NodeRef(
        entity_code=ENTITY,
        contract_external_id=CONTRACT,
        obligation_key=obligation_key,
        product_code=product,
        satisfied_period_key=satisfied,
        currency="USD",
        minor_unit=2,
        period_key=period,
        node=node,
        event_types=EVENT_TYPES,
    )


def _world() -> list[tuple[pp.NodeRef, pp.Split]]:
    """O1: an EAC re-pricing in September (−750.00), then a price change (+120.00), a modification
    (+30.00) and a late carry (+5.00) in October; O2: a CV-63 zero part in September and a
    termination (−20.00) in October."""
    o1_p09 = _node(
        "O1", P09, "-750.00", [(f"{CONTRACT}/EV-000004", "-750.00", "S08-R-14", "EAC-2")]
    )
    o1_p10 = _node(
        "O1",
        P10,
        "155.00",
        [
            (f"{CONTRACT}/EV-000005", "120.00", "S08-R-14", None),
            (f"{CONTRACT}/EV-000006", "30.00", "S08-R-14", None),
        ],
        [("FY2026-P08", 10000, 9500)],
    )
    o2_p09 = _node("O2", P09, "0.00", [(f"{CONTRACT}/EV-000007", "0.00", "CV-63", None)])
    o2_p10 = _node("O2", P10, "-20.00", [(f"{CONTRACT}/EV-000008", "-20.00", "S09-R-06", None)])
    reads = []
    for key, period, node, satisfied in (
        ("O1", P09, o1_p09, "FY2026-P07"),
        ("O1", P10, o1_p10, "FY2026-P07"),
        ("O2", P09, o2_p09, None),
        ("O2", P10, o2_p10, None),
    ):
        reads.append(
            (_ref(key, period, node, satisfied=satisfied), pp.split_node(node, 2, EVENT_TYPES))
        )
    return reads


def _section(title: str) -> str:
    return read("docs/design/SCREENS_B.md").split(title, 1)[1].split("#####", 1)[0]


def _grid(section: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in section.splitlines():
        match = _GRID_ROW.match(line)
        if match is not None:
            rows.append((match.group(1).replace(" (<ISO>)", "").strip(), match.group(2)))
    return rows


def _rule_id(excinfo: pytest.ExceptionInfo[Problem]) -> str | None:
    (error,) = excinfo.value.errors
    return error.rule_id


# --- native traces (C4-PP-R1) ---------------------------------------------------------------------


def _native_book() -> BookOutput:
    output = cast(OutputBundle, erev_engine.compute(worlds.cross_entity_late_world()))
    (book,) = [item for item in output.books if item.book_code == worlds.BOOK]
    return book


def _native_obligations(book: BookOutput) -> dict[str, pp.ObligationRef]:
    """``ObligationRef`` per trace subject from the engine's own obligation versions (T-CON-11
    columns ``contracting_entity_code`` / ``performing_entity_code``)."""
    refs: dict[str, pp.ObligationRef] = {}
    for version in book.obligation_versions:
        columns = version.columns
        refs[version.subject_key] = pp.ObligationRef(
            subject_key=version.subject_key,
            contract_external_id=worlds.CONTRACT,
            obligation_key=str(columns["obligation_key"]),
            product_code=None if columns["product_code"] is None else str(columns["product_code"]),
            performing_entity_code=str(columns["performing_entity_code"]),
            contracting_entity_code=str(columns["contracting_entity_code"]),
            satisfied_period_key=None,
            currency=str(columns["txn_currency"]),
            minor_unit=2,
        )
    return refs


@pytest.fixture(scope="module")
def native() -> tuple[BookOutput, dict[str, pp.ObligationRef]]:
    book = _native_book()
    return book, _native_obligations(book)


def test_native_world_is_the_admitted_cross_entity_distinct_calendar_case(
    native: tuple[BookOutput, dict[str, pp.ObligationRef]],
) -> None:
    """POB-01 performs on US01 (monthly), POB-02 on US02 (calendar quarters); the header stays on
    US01; ``FY2026-P02`` is February on one calendar and the second quarter on the other; both
    late carries (1,000.00) land on that key and the stage 15 sum node collects both under the
    CONTRACTING entity — no sum node exists under the performing entity US02."""
    book, refs = native
    bundle = worlds.cross_entity_late_world()
    by_code = {entity.code: entity for entity in bundle.entities}
    us01 = next(p for p in by_code["US01"].periods if p.period_key == FEBRUARY)
    us02 = next(p for p in by_code["US02"].periods if p.period_key == FEBRUARY)
    assert (us01.start_date, us01.end_date) == (date(2026, 2, 1), date(2026, 2, 28))
    assert (us02.start_date, us02.end_date) == (date(2026, 4, 1), date(2026, 6, 30))
    pob_01 = refs[obligation_subject_key(worlds.CONTRACT, "POB-01")]
    pob_02 = refs[obligation_subject_key(worlds.CONTRACT, "POB-02")]
    assert (pob_01.performing_entity_code, pob_01.contracting_entity_code) == ("US01", "US01")
    assert (pob_02.performing_entity_code, pob_02.contracting_entity_code) == ("US02", "US01")
    nodes = {node.id: node for node in book.trace.nodes}
    assert nodes[f"{MEASURE}:{pob_01.subject_key}:{FEBRUARY}"].value == "1000.00"
    assert nodes[f"{MEASURE}:{pob_02.subject_key}:{FEBRUARY}"].value == "1000.00"
    contracting = f"{SUM_MEASURE}:{contract_entity_subject_key(worlds.CONTRACT, 'US01')}:{FEBRUARY}"
    performing = f"{SUM_MEASURE}:{contract_entity_subject_key(worlds.CONTRACT, 'US02')}:{FEBRUARY}"
    assert nodes[contracting].value == "2000.00"
    assert set(nodes[contracting].inputs) == {
        f"{MEASURE}:{pob_01.subject_key}:{FEBRUARY}",
        f"{MEASURE}:{pob_02.subject_key}:{FEBRUARY}",
    }
    assert performing not in nodes


def test_identity_is_checked_under_the_contracting_entity_over_the_complete_population(
    native: tuple[BookOutput, dict[str, pp.ObligationRef]],
) -> None:
    """C4-PP-R1, all entities in scope: one identity item per (contract, key) naming the
    contracting entity's sum node, its inputs exactly the two nodes read; both rows; the two control
    totals agree."""
    book, refs = native
    scope = frozenset({("US01", FEBRUARY), ("US02", FEBRUARY)})
    found = pp.read_trace(book.trace, refs, [FEBRUARY], scope, {})
    (item,) = found.identity
    assert item.subject == f"{contract_entity_subject_key(worlds.CONTRACT, 'US01')}:{FEBRUARY}"
    assert (item.obligation_total, item.sum_value) == (200000, 200000)
    assert item.sum_inputs == item.obligation_nodes and len(item.obligation_nodes) == 2
    pp.check_identity(found.identity)
    assert found.sum_nodes == {("USD", 2): 200000}
    cores = pp.aggregate(found.reads)
    assert [core.key for core in cores] == [
        ("US01", worlds.CONTRACT, "POB-01"),
        ("US02", worlds.CONTRACT, "POB-02"),
    ]
    assert all(core.amounts["from_late_events"] == 100000 for core in cores)
    assert all(core.causes == (pp.LABEL_LATE,) for core in cores)
    assert pp.control_totals(cores, found.sum_nodes) == {
        "row_count": 2,
        "revenue_total": {"USD": "2000.00"},
        "prior_period_sum_total": {"USD": "2000.00"},
    }


@pytest.mark.parametrize(
    ("entity_code", "obligation_key"), [("US01", "POB-01"), ("US02", "POB-02")]
)
def test_single_entity_scope_filters_rows_after_the_identity_holds(
    native: tuple[BookOutput, dict[str, pp.ObligationRef]], entity_code: str, obligation_key: str
) -> None:
    """C4-PP-R1: an entity-filtered run reconciles the same complete population (the identity item
    is identical, 2,000.00 under US01) and only then keeps the rows of the scope, so the sum total
    exceeds the revenue total by the out-of-scope row; the sum is never sought under US02."""
    book, refs = native
    found = pp.read_trace(book.trace, refs, [FEBRUARY], frozenset({(entity_code, FEBRUARY)}), {})
    (item,) = found.identity
    assert item.subject.startswith(contract_entity_subject_key(worlds.CONTRACT, "US01"))
    assert (item.obligation_total, item.sum_value, len(item.obligation_nodes)) == (
        200000,
        200000,
        2,
    )
    pp.check_identity(found.identity)
    cores = pp.aggregate(found.reads)
    assert [core.key for core in cores] == [(entity_code, worlds.CONTRACT, obligation_key)]
    assert pp.control_totals(cores, found.sum_nodes) == {
        "row_count": 1,
        "revenue_total": {"USD": "1000.00"},
        "prior_period_sum_total": {"USD": "2000.00"},
    }


def test_complete_sum_input_coverage_is_enforced(
    native: tuple[BookOutput, dict[str, pp.ObligationRef]],
) -> None:
    """The identity refuses by name when the sum node's inputs are not exactly the population read,
    when its value differs, or when it is absent; an obligation the version does not carry refuses
    the key column by name before any identity (never a silent subset)."""
    book, refs = native
    found = pp.read_trace(book.trace, refs, [FEBRUARY], frozenset(), {})
    (item,) = found.identity
    pp.check_identity([item])
    partial = pp.IdentityItem(
        subject=item.subject,
        obligation_total=item.obligation_total,
        obligation_nodes=item.obligation_nodes,
        sum_value=item.sum_value,
        sum_inputs=frozenset(sorted(item.obligation_nodes)[:1]),
    )
    with pytest.raises(Problem) as excinfo:
        pp.check_identity([partial])
    assert (
        _rule_id(excinfo) == pp.SUM_NODE_MISMATCH and "collects" in excinfo.value.errors[0].message
    )
    with pytest.raises(Problem) as excinfo:
        pp.check_identity(
            [pp.IdentityItem(item.subject, 100000, item.obligation_nodes, 200000, item.sum_inputs)]
        )
    assert _rule_id(excinfo) == pp.SUM_NODE_MISMATCH
    with pytest.raises(Problem) as excinfo:
        pp.check_identity(
            [pp.IdentityItem(item.subject, 200000, item.obligation_nodes, None, None)]
        )
    assert _rule_id(excinfo) == pp.SUM_NODE_MISMATCH
    missing = {key: value for key, value in refs.items() if not key.endswith("/POB-02")}
    with pytest.raises(Problem) as excinfo:
        pp.read_trace(book.trace, missing, [FEBRUARY], frozenset(), {})
    assert _rule_id(excinfo) == pp.KEY_COLUMN_UNRESOLVED
    # A key no calendar carries yields no identity item and no rows; December (US01 only) yields
    # one zero item over POB-01 alone, which the US01 sum node collects exactly.
    assert pp.read_trace(book.trace, refs, ["FY2027-P01"], frozenset(), {}).identity == ()
    (december,) = pp.read_trace(book.trace, refs, ["FY2026-P12"], frozenset(), {}).identity
    assert (december.obligation_total, december.sum_value, len(december.obligation_nodes)) == (
        0,
        0,
        1,
    )


def test_zero_nodes_of_the_population_are_reconciled_and_omitted_from_rows(
    native: tuple[BookOutput, dict[str, pp.ObligationRef]],
) -> None:
    """January is closed on both calendars: both obligations carry zero nodes, the contracting
    entity's sum is 0.00 over exactly those nodes, and no row survives."""
    book, refs = native
    january = "FY2026-P01"
    found = pp.read_trace(
        book.trace, refs, [january], frozenset({("US01", january), ("US02", january)}), {}
    )
    (item,) = found.identity
    assert (item.obligation_total, item.sum_value, len(item.obligation_nodes)) == (0, 0, 2)
    pp.check_identity(found.identity)
    assert len(found.reads) == 2 and pp.aggregate(found.reads) == ()
    # The empty-report rule (integrated-batch ci on main 0cb36c14; K-01 September): a population of
    # zero-valued sum nodes with no published row adds no currency — both totals are ``{}``.
    assert found.sum_nodes == {("USD", 2): 0}
    assert pp.control_totals((), found.sum_nodes) == {
        "row_count": 0,
        "revenue_total": {},
        "prior_period_sum_total": {},
    }


# --- registration and specification -------------------------------------------------------------


def test_registered_in_builders_and_catalogued() -> None:
    """The producer of the E-64 kind PRIOR_PERIOD_POB_REVENUE (D-98 85; CLO-7C-PRODUCERS)."""
    assert framework.BUILDERS[pp.CODE] is pp.build
    definition = DEFINITIONS_BY_CODE[pp.CODE]
    assert definition.kind == "DISCLOSURE"
    assert {"entity_codes", "book", "period_lock_id", "from_period_key", "to_period_key"} <= set(
        definition.parameters_schema["properties"]
    )
    assert "currency_view" in definition.parameters_schema["properties"]
    assert pp.CODE not in framework.PARAMETER_DEFAULTS


def test_rpt_05_grid_matches_the_builder_columns() -> None:
    section = _section(RPT_05)
    assert _grid(section) == [(column.header, column.key) for column in pp.COLUMNS]
    assert "`row_key` `obligation:<entity code>:<external id>:<key>`" in section
    assert pp.IDENTITY in section and "`prior_period_sum_total`" in section
    assert "CONTRACTING entity" in section and "complete obligation population" in section
    for code in (pp.SUM_NODE_MISMATCH, pp.LOCK_SOURCE_NOT_SUPPORTED):
        assert f"`{code}`" in section
    labels = re.search(r"\| Cause \| `cause` \| ([^|]+) \|", section)
    assert labels is not None
    quoted = set(re.findall(r'"([^"]+)"', labels.group(1))) - {pp.CAUSE_SEPARATOR}
    assert quoted == set(pp.LABEL_ORDER) - {pp.LABEL_OTHER}


def test_key_columns_are_the_dataset_identity_and_measures_are_money() -> None:
    """D-98 85 / 87: the KeySpec keys on the three code columns; the money columns are the declared
    measures; ``cause`` is an attribute."""
    kinds = {column.key: column.kind for column in pp.COLUMNS}
    assert pp.KEY_COLUMNS == ("entity_code", "contract_external_id", "obligation_key")
    assert all(kinds[name] == "code" for name in pp.KEY_COLUMNS)
    assert all(kinds[name] == "money" for name in pp.MEASURE_COLUMNS)
    assert kinds["cause"] == "text"
    pp.require_key_columns([column.key for column in pp.COLUMNS])


def test_rule_and_type_literals_match_the_engine() -> None:
    """The node params the builder reads are the stage 08 literals (S08-R-14 to S08-R-16)."""
    assert (pp.RULE_BOUNDARY, pp.RULE_PROSPECTIVE, pp.RULE_TERMINATION) == (
        decompose.RULE_BOUNDARY,
        decompose.RULE_PROSPECTIVE,
        decompose.RULE_TERMINATION,
    )
    assert (
        pp.MODIFICATION_TYPES
        | {pp.ESTIMATE_CHANGED, pp.CONTRACT_TERMINATED, pp.MATERIAL_RIGHT_EXERCISED}
        == decompose.CHANGE_TYPES
    )
    assert (MEASURE, SUM_MEASURE) == ("revenue_prior_period", "revenue_prior_period_sum")


# --- the pure core -------------------------------------------------------------------------------


def test_split_node_attributes_parts_and_carries_by_cause() -> None:
    reads = dict(((ref.obligation_key, ref.period_key), split) for ref, split in _world())
    assert reads[("O1", P09)].amounts == {
        "from_price_changes": 0,
        "from_estimate_changes": -75000,
        "from_modifications": 0,
        "from_late_events": 0,
        "from_other": 0,
    }
    assert reads[("O1", P09)].labels == {pp.LABEL_ESTIMATE}
    assert reads[("O1", P10)].amounts == {
        "from_price_changes": 12000,
        "from_estimate_changes": 0,
        "from_modifications": 3000,
        "from_late_events": 500,
        "from_other": 0,
    }
    assert reads[("O1", P10)].labels == {pp.LABEL_PRICE, pp.LABEL_MODIFICATION, pp.LABEL_LATE}
    assert (reads[("O2", P09)].total, reads[("O2", P09)].labels) == (0, frozenset())
    assert reads[("O2", P10)].amounts["from_other"] == -2000
    assert reads[("O2", P10)].labels == {pp.LABEL_TERMINATION}


def test_classify_follows_the_screens_b_attribution() -> None:
    assert pp.classify("S08-R-14", "ESTIMATE_CHANGED", None) == (
        "from_price_changes",
        pp.LABEL_PRICE,
    )
    assert pp.classify("S08-R-14", "ESTIMATE_CHANGED", "EAC-3") == (
        "from_estimate_changes",
        pp.LABEL_ESTIMATE,
    )
    for event_type in sorted(pp.MODIFICATION_TYPES):
        assert pp.classify("S08-R-14", event_type, None) == (
            "from_modifications",
            pp.LABEL_MODIFICATION,
        )
    assert pp.classify("S08-R-14", "MATERIAL_RIGHT_EXERCISED", None) == (
        "from_other",
        pp.LABEL_MATERIAL_RIGHT,
    )
    assert pp.classify("S09-R-06", "CONTRACT_TERMINATED", None) == (
        "from_other",
        pp.LABEL_TERMINATION,
    )
    assert pp.classify("CV-63", None, None) == ("from_other", pp.LABEL_OTHER)


def test_rows_aggregate_the_range_with_typed_money_and_control_totals() -> None:
    reads = _world()
    cores = pp.aggregate(reads)
    assert [core.key for core in cores] == [(ENTITY, CONTRACT, "O1"), (ENTITY, CONTRACT, "O2")]
    o1, o2 = cores
    assert o1.amounts == {
        "from_price_changes": 12000,
        "from_estimate_changes": -75000,
        "from_modifications": 3000,
        "from_late_events": 500,
        "from_other": 0,
        "revenue": -59500,
    }
    assert o1.causes == (pp.LABEL_PRICE, pp.LABEL_ESTIMATE, pp.LABEL_MODIFICATION, pp.LABEL_LATE)
    assert (o1.satisfied_period_key, o2.satisfied_period_key) == ("FY2026-P07", None)
    assert o2.amounts["revenue"] == o2.amounts["from_other"] == -2000 and o2.causes == (
        pp.LABEL_TERMINATION,
    )
    rows = pp.section_rows(cores)
    assert [row["row_key"] for row in rows] == [
        f"obligation:{ENTITY}:{CONTRACT}:O1",
        f"obligation:{ENTITY}:{CONTRACT}:O2",
    ]
    first = rows[0]
    assert (first["entity_code"], first["contract_external_id"], first["obligation_key"]) == (
        ENTITY,
        CONTRACT,
        "O1",
    )
    assert first["cause"] == "Transaction price change; Estimate change; Modification; Late event"
    assert first["revenue"] == {"amount": "-595.00", "currency": "USD"}
    assert first["from_estimate_changes"] == {"amount": "-750.00", "currency": "USD"}
    assert first["from_other"] == {"amount": "0.00", "currency": "USD"}
    assert all(isinstance(row[field], dict) for row in rows for field in pp.MEASURE_COLUMNS)
    totals = pp.control_totals(cores, {("USD", 2): -61500})
    assert totals == {
        "row_count": 2,
        "revenue_total": {"USD": "-615.00"},
        "prior_period_sum_total": {"USD": "-615.00"},
    }


def test_all_zero_rows_are_omitted() -> None:
    zero = _node("O3", P09, "0.00", [(f"{CONTRACT}/EV-000007", "0.00", "CV-63", None)])
    cores = pp.aggregate([(_ref("O3", P09, zero), pp.split_node(zero, 2, EVENT_TYPES))])
    assert cores == ()
    assert pp.control_totals(cores, {}) == {
        "row_count": 0,
        "revenue_total": {},
        "prior_period_sum_total": {},
    }


def test_control_total_currencies_follow_the_empty_report_rule() -> None:
    """04 T-CLS-05 empty-report rule: ``prior_period_sum_total`` carries a currency when a published
    row carries it or its Σ is non-zero; rows netting to 0.00 keep "0.00" in both totals; a non-zero
    out-of-scope population shows in the sum total alone (the signed-difference rule)."""
    assert pp.control_totals((), {("USD", 2): 0}) == {
        "row_count": 0,
        "revenue_total": {},
        "prior_period_sum_total": {},
    }
    netting = [
        (
            _ref(
                "O1",
                P09,
                _node("O1", P09, "10.00", [(f"{CONTRACT}/EV-000005", "10.00", "S08-R-14", None)]),
            ),
            None,
        ),
        (
            _ref(
                "O2",
                P09,
                _node("O2", P09, "-10.00", [(f"{CONTRACT}/EV-000006", "-10.00", "S08-R-14", None)]),
            ),
            None,
        ),
    ]
    reads = [(ref, pp.split_node(ref.node, 2, EVENT_TYPES)) for ref, _ in netting]
    cores = pp.aggregate(reads)
    assert [core.amounts["revenue"] for core in cores] == [1000, -1000]
    assert pp.control_totals(cores, {("USD", 2): 0}) == {
        "row_count": 2,
        "revenue_total": {"USD": "0.00"},
        "prior_period_sum_total": {"USD": "0.00"},
    }
    assert pp.control_totals((), {("USD", 2): 0, ("EUR", 2): -500}) == {
        "row_count": 0,
        "revenue_total": {},
        "prior_period_sum_total": {"EUR": "-5.00"},
    }


def test_row_key_is_injective_with_a_same_contract_witness() -> None:
    """D-98 104: the joined key never merges two identities; a contract or obligation key holding
    the delimiter is percent-encoded (CV-21)."""
    assert pp.row_key("AVM-DE", "K:1", "A") != pp.row_key("AVM-DE", "K", "1:A")
    assert pp.row_key("AVM-DE", "K:1|event:K", "A") == "obligation:AVM-DE:K%3A1|event%3AK:A"
    assert pp.row_key("US:01", "K", "A") == "obligation:US%3A01:K:A"
    assert encode_key("a/b@c#d:e%") == "a%2Fb%40c%23d%3Ae%25"
    assert pp.row_key("AVM-DE", CONTRACT, "O1").split(":") == [
        "obligation",
        "AVM-DE",
        CONTRACT,
        "O1",
    ]


# --- event keys (C4-PP-R2) -----------------------------------------------------------------------


def test_event_refs_match_encoded_prefixes_never_raw_ids() -> None:
    """The CV-22 key carries the CV-21-encoded contract id (``bundles._event_key``); two admitted
    raw ids ``C@x`` and ``C%40x`` have distinct native prefixes ``C%40x`` and ``C%2540x``, and each
    key resolves to its own contract — never to the other's raw id, never by decoding."""
    raw_ids = ["C@x", "C%40x", "A/B", "K#1", "P:Q", "50%", "plain"]
    index = {contract_subject_key(raw): raw for raw in raw_ids}
    assert len(index) == len(raw_ids)  # the encoding is injective over the witnesses
    keys = {raw: f"{contract_subject_key(raw)}/EV-000004" for raw in raw_ids}
    assert (keys["C@x"], keys["C%40x"]) == ("C%40x/EV-000004", "C%2540x/EV-000004")
    resolved = pp.event_refs(keys.values(), index)
    assert resolved == {key: (raw, 4) for raw, key in keys.items()}
    # A raw id in the prefix position is not a candidate; malformed tails resolve to nothing.
    assert pp.event_refs(["C@x/EV-000004", "C%40x/EV-x", "/EV-000001", "C%40x"], index) == {}
    # Distinct same-version contracts keep their own event types through the mapping.
    types = {("C@x", 4): "ESTIMATE_CHANGED", ("C%40x", 4): "CONTRACT_AMENDED"}
    by_key = {key: types[pair] for key, pair in resolved.items() if pair in types}
    assert by_key == {
        "C%40x/EV-000004": "ESTIMATE_CHANGED",
        "C%2540x/EV-000004": "CONTRACT_AMENDED",
    }


def test_event_types_drive_the_cause_of_adversarial_contract_ids() -> None:
    """End to end on nodes: the same stream version on ``C@x`` (an estimate change) and ``C%40x``
    (an amendment) is attributed per contract; a boundary whose key resolves to no stored event is
    refused by name."""
    estimate_key = f"{contract_subject_key('C@x')}/EV-000004"
    amended_key = f"{contract_subject_key('C%40x')}/EV-000004"
    event_types = {estimate_key: "ESTIMATE_CHANGED", amended_key: "CONTRACT_AMENDED"}
    price = _node("O1", P09, "10.00", [(estimate_key, "10.00", "S08-R-14", None)])
    modification = _node("O2", P09, "10.00", [(amended_key, "10.00", "S08-R-14", None)])
    assert pp.split_node(price, 2, event_types).labels == {pp.LABEL_PRICE}
    assert pp.split_node(modification, 2, event_types).labels == {pp.LABEL_MODIFICATION}
    with pytest.raises(Problem) as excinfo:
        pp.split_node(price, 2, {amended_key: "CONTRACT_AMENDED"})
    assert _rule_id(excinfo) == pp.EVENT_UNRESOLVED


# --- historical membership (C4-PP-R3) ------------------------------------------------------------


class _Memberships:
    """A fake T-CON-04 ``combination_group_member`` store with the CURRENT ``contract`` field, moved
    the way ``contracts/combination._move`` does: the current row is closed at the event's
    ``recorded_at``, a new row opens in the target and the current group field is updated."""

    def __init__(self, rows: Sequence[tuple[UUID, UUID, datetime]]) -> None:
        self.rows: list[tuple[UUID, UUID, datetime, datetime | None]] = [
            (group_id, contract_id, valid_from, None) for group_id, contract_id, valid_from in rows
        ]
        self.current: dict[UUID, UUID] = {
            contract_id: group_id for group_id, contract_id, _ in rows
        }

    def move(self, contract_id: UUID, target: UUID, recorded_at: datetime) -> None:
        self.rows = [
            (
                group_id,
                member,
                valid_from,
                recorded_at if member == contract_id and to is None else to,
            )
            for group_id, member, valid_from, to in self.rows
        ]
        self.rows.append((target, contract_id, recorded_at, None))
        self.current[contract_id] = target

    def historical(self) -> list[tuple[UUID, UUID, datetime]]:
        return [(group_id, member, valid_from) for group_id, member, valid_from, _ in self.rows]


_G, _H = UUID("00000000-0000-0000-0000-00000000000a"), UUID("00000000-0000-0000-0000-00000000000b")
_C, _D, _E = (UUID(f"00000000-0000-0000-0000-0000000000{n}") for n in ("c1", "d1", "e1"))
_KNOWN_AT: Final = datetime(2026, 9, 30, 12, tzinfo=UTC)
_NAMES: Final = {_C: "C@x", _D: "D", _E: "E"}


def _cited_node(cited_key: str) -> TraceNode:
    return _node("O1", P09, "10.00", [(cited_key, "10.00", "S08-R-14", None)])


def _resolution(candidates: set[UUID], node: TraceNode) -> tuple[frozenset[str], int]:
    """Event resolution → (cause labels, revenue) of ``node`` through the candidate population."""
    index = pp.encoded_index((contract_id, _NAMES[contract_id]) for contract_id in candidates)
    refs = pp.event_refs(
        [item.ref_id for item in node.inputs if isinstance(item, SourceRef)], index
    )
    events = {(_C, 4): "ESTIMATE_CHANGED", (_D, 4): "CONTRACT_AMENDED", (_E, 4): "CONTRACT_AMENDED"}
    types = {key: events[pair] for key, pair in refs.items() if pair in events}
    split = pp.split_node(node, 2, types)
    return split.labels, split.total


def test_historical_membership_keeps_a_fixed_known_at_report_reproducible() -> None:
    """C4-PP-R3: version V of group G (selected, known_at fixed) cites contract C's event; C JOINs H
    after known_at, later LEAVEs; the candidate population as of known_at is identical before and
    after, so event resolution, causes and revenue are identical — the current group field is never
    consulted."""
    store = _Memberships(
        [(_G, _C, datetime(2026, 1, 5, tzinfo=UTC)), (_G, _D, datetime(2026, 1, 5, tzinfo=UTC))]
    )
    node = _cited_node(f"{contract_subject_key('C@x')}/EV-000004")
    before = pp.historical_candidates(store.historical(), {_G}, _KNOWN_AT)
    assert before == {_C, _D}
    resolved_before = _resolution(before, node)
    assert resolved_before == (frozenset({pp.LABEL_PRICE}), 1000)
    store.move(_C, _H, datetime(2026, 10, 15, tzinfo=UTC))  # JOIN H after known_at
    assert store.current[_C] == _H  # what 01b66504 filtered on — and would now miss C
    after_join = pp.historical_candidates(store.historical(), {_G}, _KNOWN_AT)
    assert after_join == before and _resolution(after_join, node) == resolved_before
    store.move(_C, _G, datetime(2026, 11, 1, tzinfo=UTC))  # and back (a LEAVE of H)
    after_leave = pp.historical_candidates(store.historical(), {_G}, _KNOWN_AT)
    assert after_leave == before and _resolution(after_leave, node) == resolved_before
    # The current-membership rule of 01b66504, emulated, loses C after the first move.
    current_only = {c for c, g in {_C: _H, _D: _G}.items() if g == _G}
    with pytest.raises(Problem) as excinfo:
        _resolution(current_only, node)
    assert _rule_id(excinfo) == pp.EVENT_UNRESOLVED


def test_historical_candidates_are_validated_as_of_known_at() -> None:
    """A contract whose membership in G started after known_at is not a candidate; one that left G
    before known_at still is (a version recorded by known_at can cite its LEAVE event); other groups
    contribute nothing."""
    rows = [
        (_G, _C, datetime(2026, 1, 5, tzinfo=UTC)),
        (_G, _D, datetime(2026, 10, 1, tzinfo=UTC)),  # joined after known_at
        (_H, _E, datetime(2026, 1, 5, tzinfo=UTC)),  # another group
    ]
    store = _Memberships(rows)
    store.move(_C, _H, datetime(2026, 6, 1, tzinfo=UTC))  # C left G before known_at
    assert pp.historical_candidates(store.historical(), {_G}, _KNOWN_AT) == {_C}
    assert pp.historical_candidates(store.historical(), {_G, _H}, _KNOWN_AT) == {_C, _E}
    assert pp.historical_candidates(store.historical(), set(), _KNOWN_AT) == set()
    assert pp.encoded_index([(_C, "C@x"), (_D, "D")]) == {"C%40x": _C, "D": _D}


# --- refusals by name ----------------------------------------------------------------------------


def test_missing_key_column_is_refused_by_name() -> None:
    with pytest.raises(Problem) as excinfo:
        pp.require_key_columns(["entity_code", "contract_external_id", "cause", "revenue"])
    assert _rule_id(excinfo) == pp.KEY_COLUMN_MISSING
    assert "obligation_key" in excinfo.value.errors[0].message


def test_node_whose_parts_do_not_sum_to_its_value_is_refused_by_name() -> None:
    broken = _node(
        "O1", P09, "-700.00", [(f"{CONTRACT}/EV-000004", "-750.00", "S08-R-14", "EAC-2")]
    )
    with pytest.raises(Problem) as excinfo:
        pp.split_node(broken, 2, EVENT_TYPES)
    assert _rule_id(excinfo) == pp.NODE_SPLIT_MISMATCH


def test_boundary_event_not_stored_is_refused_by_name() -> None:
    node = _node("O1", P09, "10.00", [(f"{CONTRACT}/EV-000099", "10.00", "S08-R-14", None)])
    with pytest.raises(Problem) as excinfo:
        pp.split_node(node, 2, EVENT_TYPES)
    assert _rule_id(excinfo) == pp.EVENT_UNRESOLVED


def test_as_locked_run_is_refused_by_name_before_any_read() -> None:
    """D-98 96: the locked-dataset source is the framework's (CLO-8); until it lands the builder
    refuses a run naming ``period_lock_id`` without touching the unit of work."""
    params = ReportParams(
        report_code=pp.CODE,
        report_version=1,
        parameters={"entity_codes": [ENTITY], "book": "ASC606"},
        entity_ids=(uuid4(),),
        known_at=datetime(2026, 9, 30, 12, tzinfo=UTC),
        book_code="ASC606",
        period_lock_id=uuid4(),
    )
    with pytest.raises(Problem) as excinfo:
        pp.build(object(), params)  # type: ignore[arg-type]
    assert _rule_id(excinfo) == pp.LOCK_SOURCE_NOT_SUPPORTED


# --- item RPT-FORMER-GROUP-VERSIONS-1: one version per contract and period ------------------------


def test_the_version_recorded_last_states_a_contract_for_a_period() -> None:
    """A contract computed in its own group and combined within September has revenue lines of
    that period under versions of both groups; the combined group's version, recorded later,
    restates the period for it, so the own group's version does not state it there. August,
    before the combination, is still read from the group that posted it; a contract one version
    alone holds is nobody else's. Before: both versions were read for September — the rule was
    one version per (group, period)."""
    own, joint, other = UUID(int=1), UUID(int=2), UUID(int=3)
    august, september = UUID(int=11), UUID(int=12)
    selected = {
        own: pp._Selected(
            group_id=UUID(int=21),
            period_ids=frozenset({august, september}),
            known_at=datetime(2026, 9, 5, tzinfo=UTC),
            version_no=3,
        ),
        joint: pp._Selected(
            group_id=UUID(int=22),
            period_ids=frozenset({september}),
            known_at=datetime(2026, 9, 12, tzinfo=UTC),
            version_no=1,
        ),
        other: pp._Selected(
            group_id=UUID(int=23),
            period_ids=frozenset({september}),
            known_at=datetime(2026, 9, 2, tzinfo=UTC),
            version_no=1,
        ),
    }
    contracts = {
        own: ["SF-ORD-10417"],
        joint: ["SF-ORD-10417", "SF-ORD-10418"],
        other: ["SF-ORD-10002"],
    }
    assert pp.stated_elsewhere(selected, contracts) == {
        own: frozenset({("SF-ORD-10417", september)})
    }


def test_two_versions_recorded_together_are_ranked_by_number_then_id() -> None:
    """The order is total: the record time, then ``version_no``, then the id."""
    first, second = UUID(int=1), UUID(int=2)
    period = UUID(int=11)
    at = datetime(2026, 9, 12, tzinfo=UTC)
    selected = {
        first: pp._Selected(
            group_id=UUID(int=21), period_ids=frozenset({period}), known_at=at, version_no=2
        ),
        second: pp._Selected(
            group_id=UUID(int=22), period_ids=frozenset({period}), known_at=at, version_no=1
        ),
    }
    contracts = {first: ["K"], second: ["K"]}
    assert pp.stated_elsewhere(selected, contracts) == {second: frozenset({("K", period)})}


def test_a_contract_stated_elsewhere_is_not_read_from_this_version(
    native: tuple[BookOutput, dict[str, pp.ObligationRef]],
) -> None:
    """``read_trace`` leaves out a (contract, period) another version states: no identity item, no
    row and no sum node of it — the population stays complete, so an unknown subject is still
    refused."""
    book, refs = native
    scope = frozenset({("US01", FEBRUARY), ("US02", FEBRUARY)})
    found = pp.read_trace(
        book.trace, refs, [FEBRUARY], scope, {}, frozenset({(worlds.CONTRACT, FEBRUARY)})
    )
    assert (found.identity, found.reads, found.sum_nodes) == ((), (), {})
    kept = pp.read_trace(book.trace, refs, [FEBRUARY], scope, {}, frozenset({("OTHER", FEBRUARY)}))
    assert len(kept.identity) == 1 and len(kept.reads) == 2
