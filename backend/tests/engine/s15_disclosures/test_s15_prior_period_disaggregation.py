"""Stage 15 revenue from obligations satisfied in prior periods (EDS-4; lane ENG-C4).

ENGINE_SPEC_B §15.2.4 S15-R-13, S15-R-14; §15.5; ENGINE_SPEC §8.5 S08-R-14 to S08-R-16; POLICIES
POL-204, ALG-10 §2.11.3; 606-10-50-12A. Before this lane stage 08's ``decompose_prior_period`` had
no caller, so no ``revenue_prior_period`` node existed and the keys asserting the row failed on
it alone (DISC-CHK-101-S3-EX23-CASEB-PRIOR-PERIOD-POB-REVENUE, JE-CHK-026-CHK-100-S3-EX21-EXTENDED-
BONUS-CATCH-UP, VC-FS-02-COMMITTED-SPEND-TIERED-OVERAGE). The worlds are the answer keys' checkpoint
bundles computed by the real engine. No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import cast

import erev_engine
import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    BookInput,
    BookOutput,
    EntityInput,
    EstimateVersionInput,
    EventInput,
    InputBundle,
    MappingRuleInput,
    ModificationInput,
    OutputBundle,
    PeriodInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.dates import month_end
from erev_engine.stages import STAGES, s01_canonicalize, s13_books
from erev_engine.stages.s15_disclosures import DisclosureState, prior_period
from erev_engine.stages.state import AllocatedState
from erev_engine.trace import SourceRef, TraceBuilder, reevaluate
from support import bundles
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles
from support.recognition import estimate_version

DISC_101 = ("disc", "DISC-CHK-101-S3-EX23-CASEB-PRIOR-PERIOD-POB-REVENUE", "C-DISC-101")
JE_026 = ("je", "JE-CHK-026-CHK-100-S3-EX21-EXTENDED-BONUS-CATCH-UP", "C-JE-026")
VC_FS_02 = ("vc", "VC-FS-02-COMMITTED-SPEND-TIERED-OVERAGE", "FS-02")
MEASURE = prior_period.MEASURE
SUM = prior_period.SUM_MEASURE


def _checkpoints(family: str, key_id: str, contract: str) -> dict[str, tuple[str, InputBundle]]:
    """checkpoint name -> (book, the bundle holding ``contract``)."""
    out: dict[str, tuple[str, InputBundle]] = {}
    loaded = load(ANSWER_KEY_ROOT / family / f"{key_id}.yaml")
    for checkpoint in _build_checkpoint_bundles(loaded):
        (bundle,) = [
            cast(InputBundle, item)
            for item in checkpoint.bundles
            if any(header.external_id == contract for header in item.contracts)
        ]
        out[checkpoint.name] = (checkpoint.book, bundle)
    return out


def _book(bundle: InputBundle, book_code: str) -> BookOutput:
    output = cast(OutputBundle, erev_engine.compute(bundle))
    (found,) = [item for item in output.books if item.book_code == book_code]
    return found


def _state(bundle: InputBundle) -> DisclosureState:
    cb = s01_canonicalize.run(bundle, TraceBuilder(engine_version=ENGINE_VERSION))
    (result,) = s13_books.run_books(cb, STAGES)
    assert isinstance(result.state, DisclosureState)
    return result.state


def _allocated(bundle: InputBundle) -> AllocatedState:
    cb = s01_canonicalize.run(bundle, TraceBuilder(engine_version=ENGINE_VERSION))
    (result,) = s13_books.run_books(cb, STAGES)
    assert isinstance(result.state, DisclosureState)
    return result.state.allocated


def _rows(book: BookOutput, measure: str) -> dict[tuple[str, str], str]:
    """(subject key, period key) -> node value of every ``measure`` node of the book; the id is
    ``<measure>:<subject>:<period>`` with ``:`` percent-encoded inside the subject (CV-21)."""
    out: dict[tuple[str, str], str] = {}
    for node in book.trace.nodes:
        if node.measure != measure:
            continue
        subject, period = node.id[len(measure) + 1 :].rsplit(":", 1)
        out[(subject, period)] = node.value
    return out


def _replays(book: BookOutput) -> None:
    assert reevaluate(book.trace) == {node.id: node.value for node in book.trace.nodes}


# --- The answer-key rows (fail-first: absent on 2a16cf6) ------------------------------------------

KEY_ROWS = [
    (DISC_101, "february-2027", "C-DISC-101/L1-PRODUCTS", "FY2027-P02", "5000.00"),
    (JE_026, "year-2-january-catch-up", "C-JE-026/L1-BUILD", "FY2027-P01", "60000.00"),
    (JE_026, "year-2-close", "C-JE-026/L1-BUILD", "FY2027-P12", "0.00"),
    (VC_FS_02, "q2-reestimate", "FS-02/L1-COMMIT", "FY2026-P06", "25000.00"),
]


@pytest.mark.parametrize(("key", "checkpoint", "subject", "period", "expected"), KEY_ROWS)
def test_eds4_answer_key_rows_exist(
    key: tuple[str, str, str], checkpoint: str, subject: str, period: str, expected: str
) -> None:
    """S15-R-13 / S08-R-16: the ``revenue_prior_period:<ob>:<period>`` node the key asserts exists
    in the book's trace with the key's value and the stage 08 formula id, and re-evaluates (P14)."""
    book_code, bundle = _checkpoints(*key)[checkpoint]
    book = _book(bundle, book_code)
    nodes = {node.id: node for node in book.trace.nodes}
    node = nodes[f"{MEASURE}:{subject}:{period}"]
    assert (node.value, node.formula_id) == (expected, "estimate.prior_period.v1")
    _replays(book)


def test_eds4_disc_101_estimate_change_cause() -> None:
    """DISC-CHK-101 (CHK-101, FASB Example 23 Case B): the February 2027 node cites the version 2
    ESTIMATE_CHANGED event as its one boundary (rule S08-R-14) with E_before 50,000.00 and E_after
    55,000.00 at the period start (the obligation was satisfied in December 2026, f(s) = 1), part
    5,000.00; December 2026 and January 2027 carry zero nodes; the contract-entity sum equals the
    obligation node."""
    book_code, bundle = _checkpoints(*DISC_101)["february-2027"]
    book = _book(bundle, book_code)
    rows = _rows(book, MEASURE)
    assert rows == {
        ("C-DISC-101/L1-PRODUCTS", "FY2026-P12"): "0.00",
        ("C-DISC-101/L1-PRODUCTS", "FY2027-P01"): "0.00",
        ("C-DISC-101/L1-PRODUCTS", "FY2027-P02"): "5000.00",
    }
    node = {n.id: n for n in book.trace.nodes}[f"{MEASURE}:C-DISC-101/L1-PRODUCTS:FY2027-P02"]
    assert (node.params["boundaries"], node.params["carries"], node.params["rule_1"]) == (
        "1",
        "0",
        "S08-R-14",
    )
    assert (node.params["e_before_1"], node.params["e_after_1"]) == ("50000", "55000")
    (ref,) = [item for item in node.inputs if isinstance(item, SourceRef)]
    assert ref.ref_type == "contract_event"
    event = next(e for e in bundle.events if e.event_key == ref.ref_id)
    assert (event.event_type, event.effective_date) == ("ESTIMATE_CHANGED", date(2027, 2, 15))
    assert dict(ref.detail) == {"member": "prior_period_part", "value": "5000.00"}
    assert _rows(book, SUM) == {
        ("C-DISC-101@US01", "FY2026-P12"): "0.00",
        ("C-DISC-101@US01", "FY2027-P01"): "0.00",
        ("C-DISC-101@US01", "FY2027-P02"): "5000.00",
    }
    state = _state(bundle)
    assert [(t.subject_key, t.period_key, t.value) for t in state.prior_period.targets] == [
        ("C-DISC-101/L1-PRODUCTS", "FY2026-P12", 0),
        ("C-DISC-101/L1-PRODUCTS", "FY2027-P01", 0),
        ("C-DISC-101/L1-PRODUCTS", "FY2027-P02", 500_000),
    ]
    assert [(t.subject_key, t.period_key, t.value) for t in state.prior_period.sums] == [
        ("C-DISC-101@US01", "FY2026-P12", 0),
        ("C-DISC-101@US01", "FY2027-P01", 0),
        ("C-DISC-101@US01", "FY2027-P02", 500_000),
    ]
    _replays(book)


def test_eds4_zero_nodes_through_each_horizon() -> None:
    """S15-R-13 "every period through the horizon": JE-CHK-026's year-2-close bundle (calendar
    2026-01 to 2028-12, all open) carries one node per period from the inception period through
    the horizon, zero except January 2027 (CHK-100: round(150,000 × 0.40) = 60,000.00); the
    year-1-close bundle carries the twelve 2026 nodes at zero (the horizon is its calendar end)."""
    points = _checkpoints(*JE_026)
    book_code, bundle = points["year-2-close"]
    rows = _rows(_book(bundle, book_code), MEASURE)
    entity = next(e for e in bundle.entities if e.code == "US01")
    expected_periods = sorted(p.period_key for p in entity.periods)
    assert sorted(period for (_, period) in rows) == expected_periods
    assert {period: value for (_, period), value in rows.items() if value != "0.00"} == {
        "FY2027-P01": "60000.00"
    }
    book_code, bundle = points["year-1-close"]
    rows = _rows(_book(bundle, book_code), MEASURE)
    assert set(rows.values()) == {"0.00"} and len(rows) == len(expected_periods)


def test_eds4_vc_fs_02_split_of_the_june_catch_up() -> None:
    """VC-FS-02 q2-reestimate: version 2 (30 June) lifts TP 220,000.00 → 280,000.00 on a
    time-elapsed series with f(1 June) = 5/12: prior-period part round(60,000 × 5/12) = 25,000.00
    (ALG-10 §2.11.3); the June posting 48,333.33 splits into 25,000.00 prior and 23,333.33 current.
    Every other period through the horizon is zero."""
    book_code, bundle = _checkpoints(*VC_FS_02)["q2-reestimate"]
    book = _book(bundle, book_code)
    rows = _rows(book, MEASURE)
    assert {period: value for (_, period), value in rows.items() if value != "0.00"} == {
        "FY2026-P06": "25000.00"
    }
    node = {n.id: n for n in book.trace.nodes}[f"{MEASURE}:FS-02/L1-COMMIT:FY2026-P06"]
    assert Fraction(node.params["e_after_1"]) - Fraction(node.params["e_before_1"]) == Fraction(
        25000
    )
    (ref,) = [item for item in node.inputs if isinstance(item, SourceRef)]
    event = next(e for e in bundle.events if e.event_key == ref.ref_id)
    assert event.event_type == "ESTIMATE_CHANGED"
    _replays(book)


def test_eds4_sum_formula_reevaluates_and_matches_the_obligation_nodes() -> None:
    """``disc.prior_period_sum.v1``: the contract-entity node sums its obligation inputs and
    re-evaluates from them; a bundle without estimate boundaries still carries zero sums."""
    book_code, bundle = _checkpoints(*JE_026)["year-2-january-catch-up"]
    book = _book(bundle, book_code)
    nodes = {n.id: n for n in book.trace.nodes}
    total = nodes[f"{SUM}:C-JE-026@US01:FY2027-P01"]
    assert total.formula_id == "disc.prior_period_sum.v1"
    assert total.inputs == (f"{MEASURE}:C-JE-026/L1-BUILD:FY2027-P01",)
    assert (total.value, total.params["count"], total.params["period"]) == (
        "60000.00",
        "1",
        "FY2027-P01",
    )
    values = reevaluate(book.trace)
    assert values[total.id] == "60000.00"
    assert all(values[node.id] == node.value for node in book.trace.nodes if node.measure == SUM)


# --- Late carries and each entity's own calendar (BUILD_SPEC EDS-4 test list) ---------------------

LATE_CONTRACT = "K-LATE"
LATE_ENTITY = "US01"
LATE_KEYS = ("POB-01", "POB-02")
LATE_INCEPTION = date(2026, 1, 5)


def _pit_template(code: str = "TPL-PIT") -> TemplateInput:
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256="0" * 64,
        obligation_kind="STANDARD",
        distinctness="distinct",
        series_increment_unit=None,
        satisfaction_pattern="POINT_IN_TIME",
        over_time_criterion="NOT_APPLICABLE",
        recognition_method="POINT_IN_TIME",
        ratable_convention=None,
        start_date_rule="LINE_START",
        end_date_rule="LINE_END",
        term_months=None,
        principal_agent="PRINCIPAL",
        warranty_type="NONE",
        licence_nature="NOT_APPLICABLE",
        sfc_assessment_required=False,
        revenue_category=None,
        disaggregation={},
        account_role_overrides={},
        stratification_label=None,
        is_excluded_from_netting_attribution=False,
        policy_values={},
        effective_from=date(2020, 1, 1),
        effective_to=None,
    )


def _ssp_version(
    products: Sequence[str], values: Mapping[str, str] | None = None
) -> SspVersionInput:
    """Observable point SSPs, 1,000.00 unless ``values`` names the product's."""
    entries = tuple(
        SspEntryInput(
            entry_key=f"SSP-US@v1/{product}//-/USD",
            product_code=product,
            stratification="",
            region=None,
            channel=None,
            segment=None,
            deal_size_band=None,
            term_band=None,
            currency="USD",
            method="observable",
            value_basis="AMOUNT",
            unit_list_price=None,
            midpoint_discount_ratio=None,
            range_ratio=None,
            cost_basis=None,
            margin_ratio=None,
            distinctness="distinct",
            revenue_account_code=None,
            observable_point=None,
            ranges=(
                SspRangeInput(
                    "NONE",
                    None,
                    None,
                    Decimal((values or {}).get(product, "1000.00")),
                    None,
                    None,
                    None,
                ),
            ),
        )
        for product in products
    )
    return SspVersionInput(
        ssp_book_code="SSP-US",
        version_key="SSP-US@v1",
        version_no=1,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label=None,
        effective_from_date=date(2020, 1, 1),
        effective_to_date=None,
        status="APPROVED",
        approved_at=datetime(2020, 1, 1, tzinfo=UTC),
        content_sha256="0" * 64,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=entries,
    )


def _delivery(stream: int, key: str, on: date) -> EventInput:
    payload = {"obligation_key": key, "quantity": Decimal("1"), "trigger": "CONTROL_TRANSFER"}
    return bundles.event(
        LATE_CONTRACT, stream, "DELIVERY_RECORDED", on, payload, obligation_keys=[key]
    )


def _quarterly(code: str, year: int) -> EntityInput:
    """A calendar-quarter entity (ALG-11 rule 3; the CHK-110 quarters), period keys P01 to P04."""
    periods = tuple(
        PeriodInput(
            period_key=f"FY{year}-P{quarter:02d}",
            fiscal_year=year,
            period_no=quarter,
            start_date=date(year, 3 * quarter - 2, 1),
            end_date=month_end(date(year, 3 * quarter, 1)),
            states=(("ASC606", "open"),),
        )
        for quarter in range(1, 5)
    )
    return EntityInput(code, "USD", "America/New_York", "P445", periods)


def _world(
    deliveries: Sequence[EventInput],
    *,
    states: Mapping[str, str],
    previous_heads: int = 0,
    second_entity: EntityInput | None = None,
) -> InputBundle:
    """Two 1,000.00 point-in-time obligations booked and activated on 5 January 2026; with
    ``second_entity`` POB-02 performs on that entity (its own calendar)."""
    calendar = bundles.entity(months=12, states=states)
    entities = [calendar] + ([second_entity] if second_entity is not None else [])
    header = bundles.contract(LATE_CONTRACT, inception=LATE_INCEPTION)
    booking = []
    for key in LATE_KEYS:
        line = bundles.booking_line(
            key,
            product_code=f"KIT-{key}",
            quantity="1",
            total_price="1000.00",
            start=LATE_INCEPTION,
            end=LATE_INCEPTION,
        )
        if second_entity is not None and key == "POB-02":
            line["performing_entity_code"] = second_entity.code
        booking.append(line)
    events = [
        bundles.event(
            LATE_CONTRACT,
            1,
            "CONTRACT_BOOKED",
            LATE_INCEPTION,
            {"lines": booking},
            obligation_keys=list(LATE_KEYS),
        ),
        bundles.event(LATE_CONTRACT, 2, "CONTRACT_ACTIVATED", LATE_INCEPTION, {"checklist": {}}),
        *deliveries,
    ]
    products = tuple(
        bundles.product(f"KIT-{key}", template_code="TPL-PIT", family=None) for key in LATE_KEYS
    )
    group = dataclasses.replace(
        bundles.group((header,), group_key=f"CG-{LATE_CONTRACT}", products=products),
        previous_stream_heads=((LATE_CONTRACT, previous_heads),) if previous_heads else (),
    )
    policies = list(bundles.policy_set(book_code="ASC606", entity=calendar))
    if second_entity is not None:
        seen = {(p.code, p.scope, p.subject_key) for p in policies}
        for policy in bundles.policy_set(book_code="ASC606", entity=second_entity):
            if (policy.code, policy.scope, policy.subject_key) not in seen:
                policies.append(policy)
    mapping = bundles.account_mapping()
    if second_entity is not None:  # JET-13 intercompany lines of the performing-entity obligation
        extra = tuple(
            MappingRuleInput(role, None, None, None, None, None, code, {}, 0, 0)
            for role, code in (("INTERCOMPANY_DUE_FROM", "1800"), ("INTERCOMPANY_DUE_TO", "2800"))
        )
        rules = sorted(
            (*mapping.rules, *extra),
            key=lambda rule: (rule.account_role, rule.clearing_purpose or "", rule.account_code),
        )
        mapping = dataclasses.replace(mapping, rules=tuple(rules))
    book = BookInput(
        "ASC606",
        True,
        tuple(sorted(entity.code for entity in entities)),
        tuple(sorted(policies, key=lambda p: (p.code, p.scope, p.subject_key))),
        mapping,
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(book,),
        entities=tuple(sorted(entities, key=lambda entity: entity.code)),
        group=group,
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(_ssp_version([f"KIT-{key}" for key in LATE_KEYS]),),
        pob_template_versions=(_pit_template(),),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def test_eds4_late_carry_enters_the_posting_period() -> None:
    """S08-R-15 / ALG-09 step 7 through stage 15: deliveries effective in closed January 2026 and
    recorded afterwards post in February with origin January (S08-R-10). The February node of each
    obligation carries the late attribution — the recomputed January target 1,000.00 less the
    revenue posted with origin January (none in this bundle) — with params late_origin_1 /
    late_target_1 / late_posted_1; the closed January node is zero (nothing posts in a closed
    period); the contract-entity sum is 2,000.00; every node re-evaluates."""
    deliveries = [
        _delivery(3, "POB-01", date(2026, 1, 20)),
        _delivery(4, "POB-02", date(2026, 1, 20)),
    ]
    bundle = _world(deliveries, states={"FY2026-P01": "closed"}, previous_heads=2)
    book = _book(bundle, "ASC606")
    nodes = {n.id: n for n in book.trace.nodes}
    for key in LATE_KEYS:
        january = nodes[f"{MEASURE}:{LATE_CONTRACT}/{key}:FY2026-P01"]
        assert (january.value, january.params["carries"], january.params["boundaries"]) == (
            "0.00",
            "0",
            "0",
        )
        february = nodes[f"{MEASURE}:{LATE_CONTRACT}/{key}:FY2026-P02"]
        assert february.value == "1000.00"
        assert (
            february.params["carries"],
            february.params["late_origin_1"],
            february.params["late_target_1"],
            february.params["late_posted_1"],
        ) == ("1", "FY2026-P01", "100000", "0")
        march = nodes[f"{MEASURE}:{LATE_CONTRACT}/{key}:FY2026-P03"]
        assert march.value == "0.00"
    assert nodes[f"{SUM}:{LATE_CONTRACT}@{LATE_ENTITY}:FY2026-P02"].value == "2000.00"
    _replays(book)
    # The same deliveries with January open: no carry, every node zero.
    open_book = _book(_world(deliveries, states={}), "ASC606")
    assert set(_rows(open_book, MEASURE).values()) == {"0.00"}


def test_eds4_each_entity_decomposes_on_its_own_calendar() -> None:
    """S15-R-13 per performing entity: POB-01 performs on the monthly entity US01 and POB-02 on
    the calendar-quarter entity US02; each obligation carries one node per period of ITS entity's
    calendar from the inception period through that entity's horizon (12 monthly keys against
    4 quarterly keys), and the contract-entity sums are keyed by the contracting entity's
    calendar for POB-01 and the performing entity's for POB-02."""
    quarterly = _quarterly("US02", 2026)
    deliveries = [
        _delivery(3, "POB-01", date(2026, 2, 10)),
        _delivery(4, "POB-02", date(2026, 5, 10)),
    ]
    bundle = _world(deliveries, states={}, second_entity=quarterly)
    book = _book(bundle, "ASC606")
    rows = _rows(book, MEASURE)
    monthly_keys = sorted(period for (subject, period) in rows if subject.endswith("/POB-01"))
    quarterly_keys = sorted(period for (subject, period) in rows if subject.endswith("/POB-02"))
    assert monthly_keys == [f"FY2026-P{month:02d}" for month in range(1, 13)]
    assert quarterly_keys == ["FY2026-P01", "FY2026-P02", "FY2026-P03", "FY2026-P04"]
    assert set(rows.values()) == {"0.00"}  # deliveries are progress, not prior-period changes
    _replays(book)


# --- Disaggregation tags (S15-R-15), other revenue lines (S15-R-16), tie-out (S15-INV-03) ---------


def _revenue_lines(book: BookOutput) -> list[tuple[str, str, str, int, Mapping[str, str]]]:
    """(entity, posting period, subject, signed amount credit positive, dimensions) of every
    REVENUE line."""
    out = []
    for intent in book.posting_intents:
        for line in intent.lines:
            if line.account_role == "REVENUE":
                signed = line.amount_txn if line.side == "C" else -line.amount_txn
                out.append(
                    (
                        intent.entity,
                        intent.posting_period_key,
                        intent.subject_key,
                        signed,
                        line.dimensions,
                    )
                )
    return out


def _assert_inv_03(state: DisclosureState, book: BookOutput) -> None:
    """S15-INV-03: per (entity, period) and dimension, Σ rows = Σ REVENUE lines of the period."""
    journal: dict[tuple[str, str], int] = {}
    for entity, period, _, amount, _ in _revenue_lines(book):
        journal[(entity, period)] = journal.get((entity, period), 0) + amount
    assert dict(state.disaggregation.totals) == journal
    per_dimension: dict[tuple[str, str, str], int] = {}
    for row in state.disaggregation.rows:
        key = (row.entity, row.period_key, row.dimension)
        per_dimension[key] = per_dimension.get(key, 0) + row.amount
    for (entity, period, _), amount in per_dimension.items():
        assert amount == journal[(entity, period)]
    assert set(state.disaggregation.dimensions) >= {
        "performing_entity",
        "timing_of_transfer",
        "revenue_category",
        "product_family",
    }


@pytest.mark.parametrize(
    ("key", "checkpoint"),
    [(DISC_101, "february-2027"), (JE_026, "year-2-close"), (VC_FS_02, "q2-reestimate")],
)
def test_s15_r15_revenue_lines_carry_the_obligation_tags(
    key: tuple[str, str, str], checkpoint: str
) -> None:
    """Every REVENUE line of the answer-key worlds carries its obligation's S15-R-15 tags —
    performing entity and timing of transfer always, product family / revenue category / region /
    channel / contract type where the world names them — and non-REVENUE lines carry none of them;
    the S15-INV-03 tie-out holds for every (entity, period) and dimension."""
    book_code, bundle = _checkpoints(*key)[checkpoint]
    book = _book(bundle, book_code)
    lines = _revenue_lines(book)
    assert lines
    obligations = {ob.subject_key for ob in _state(bundle).allocated.obligations}
    patterns = {
        ob.subject_key: str(ob.satisfaction_pattern) for ob in _state(bundle).allocated.obligations
    }
    for entity, _, subject, _, dims in lines:
        if subject in obligations:
            assert dims["performing_entity"] == entity or dims["performing_entity"] in {
                e.code for e in bundle.entities
            }
            assert dims["timing_of_transfer"] == (
                "OVER_TIME" if patterns[subject] == "OVER_TIME" else "POINT_IN_TIME"
            )
    for intent in book.posting_intents:
        for line in intent.lines:
            if line.account_role != "REVENUE":
                assert "timing_of_transfer" not in line.dimensions
                assert "performing_entity" not in line.dimensions
    _assert_inv_03(_state(bundle), book)


def test_s15_r16_performing_side_lines_carry_tags_and_tie_out() -> None:
    """The two-entity world: POB-02 performs on US02, so its REVENUE line is the JET-13
    performing-side line on US02; it carries performing_entity US02 and the point-in-time tag, and
    the disaggregation totals per (entity, period) equal the revenue journal (S15-INV-03)."""
    quarterly = _quarterly("US02", 2026)
    deliveries = [
        _delivery(3, "POB-01", date(2026, 2, 10)),
        _delivery(4, "POB-02", date(2026, 5, 10)),
    ]
    bundle = _world(deliveries, states={}, second_entity=quarterly)
    book = _book(bundle, "ASC606")
    state = _state(bundle)
    lines = [(e, p, s, a, dict(d)) for e, p, s, a, d in _revenue_lines(book)]
    us02 = [item for item in lines if item[0] == "US02"]
    assert us02 and all(
        d["performing_entity"] == "US02" and d["timing_of_transfer"] == "POINT_IN_TIME"
        for *_, d in us02
    )
    assert sum(a for _, _, _, a, _ in us02) == 100_000
    rows = {
        (r.entity, r.period_key, r.dimension, r.value): r.amount for r in state.disaggregation.rows
    }
    assert rows[("US02", "FY2026-P02", "performing_entity", "US02")] == 100_000
    assert rows[("US01", "FY2026-P02", "performing_entity", "US01")] == 100_000
    _assert_inv_03(state, book)


def _timing_world(*, configured_category: str | None = None) -> InputBundle:
    """EX-15-B's April timing split rebuilt as a bundle: POB-PIT 8,000.00 delivered 10 Apr 2026 on
    a template tagged ``segment: Enterprise`` plus a targeted BONUS of 200.00 effective 25 Apr;
    POB-OT 7,200.00 recognised monthly even over 2026 (600.00 in April). ``configured_category``
    adds ``TPL-OT.disaggregation["revenue_category"]`` (Codex C4-R1: a configured attribute that
    shares a derived code)."""
    inception = date(2026, 1, 1)
    calendar = bundles.entity(months=12)
    header = bundles.contract("K-TIMING", inception=inception)
    pit = dataclasses.replace(
        _pit_template("TPL-PIT-SEG"), disaggregation={"segment": "Enterprise"}
    )
    over_time = dataclasses.replace(
        _pit_template("TPL-OT"),
        satisfaction_pattern="OVER_TIME",
        over_time_criterion="OT_A",
        recognition_method="TIME_ELAPSED",
        ratable_convention="MONTHLY_EVEN",
        revenue_category="SUBSCRIPTION",
        disaggregation=(
            {} if configured_category is None else {"revenue_category": configured_category}
        ),
    )
    booking = [
        bundles.booking_line(
            "POB-PIT",
            product_code="HW",
            quantity="1",
            total_price="8000.00",
            start=inception,
            end=inception,
        ),
        bundles.booking_line(
            "POB-OT",
            product_code="SUB",
            quantity="1",
            total_price="7200.00",
            start=inception,
            end=date(2026, 12, 31),
        ),
    ]
    bonus_key = "K-TIMING/BONUS"
    bonus = EstimateVersionInput(
        estimate_key=bonus_key,
        estimate_kind="VARIABLE_CONSIDERATION",
        element_code="BONUS",
        method="ENTERED_AMOUNT",
        vc_element_type="BONUS",
        allocation_target="OBLIGATIONS",
        target_obligation_keys=("POB-PIT",),
        obligation_key="POB-PIT",
        version_key=f"{bonus_key}@v1",
        version_no=1,
        status="APPROVED",
        effective_date=date(2026, 4, 25),
        scenarios=(),
        parameters={
            "allocation_criteria_evidence": "Bonus relates to the hardware delivery (32-40)."
        },
        unconstrained_amount=None,
        most_conservative_amount=None,
        constrained_amount=Decimal("200.00"),
        rate=None,
        expected_total_amount=None,
        expected_quantity=None,
        amortization_months=None,
        currency="USD",
        supersedes_version_key=None,
        judgement_key=None,
        content_sha256="0" * 64,
        direction="INCREASE",
    )
    events = [
        bundles.event(
            "K-TIMING",
            1,
            "CONTRACT_BOOKED",
            inception,
            {"lines": booking},
            obligation_keys=["POB-PIT", "POB-OT"],
        ),
        bundles.event("K-TIMING", 2, "CONTRACT_ACTIVATED", inception, {"checklist": {}}),
        bundles.event(
            "K-TIMING",
            3,
            "DELIVERY_RECORDED",
            date(2026, 4, 10),
            {"obligation_key": "POB-PIT", "quantity": Decimal("1"), "trigger": "CONTROL_TRANSFER"},
            obligation_keys=["POB-PIT"],
        ),
        dataclasses.replace(
            bundles.event(
                "K-TIMING",
                4,
                "ESTIMATE_CHANGED",
                date(2026, 4, 25),
                {"estimate_version_id": bonus.version_key},
            ),
            estimate_version_key=bonus.version_key,
        ),
    ]
    products = (
        dataclasses.replace(bundles.product("HW", template_code="TPL-PIT-SEG", family="Hardware")),
        dataclasses.replace(
            bundles.product("SUB", template_code="TPL-OT", family="Subscriptions"),
            revenue_category="SUBSCRIPTION",
        ),
    )
    group = bundles.group((header,), group_key="CG-K-TIMING", products=products)
    policies = tuple(  # POL-090: monthly even, so April carries 600.00 of the 7,200.00
        dataclasses.replace(policy, value=bundles.policy_value("MONTHLY_EVEN"))
        if policy.code == "recognition.time_convention"
        else policy
        for policy in bundles.policy_set(book_code="ASC606", entity=calendar)
    )
    book = BookInput("ASC606", True, (calendar.code,), policies, bundles.account_mapping())
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(book,),
        entities=(calendar,),
        group=group,
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(_ssp_version(["HW", "SUB"], {"HW": "8000.00", "SUB": "7200.00"}),),
        pob_template_versions=tuple(sorted((pit, over_time), key=lambda t: t.template_code)),
        rule_set_versions=(),
        estimate_versions=(bonus,),
        fx_rates=(),
        posted=(),
    )


def _money_lines(book: BookOutput) -> list[tuple[str, str, str, str, str, int]]:
    """Every posting line without its dimensions: (entity, period, subject, role, side, txn)."""
    return sorted(
        (
            intent.entity,
            intent.posting_period_key,
            intent.subject_key,
            line.account_role,
            line.side,
            line.amount_txn,
        )
        for intent in book.posting_intents
        for line in intent.lines
    )


def test_c4_r1_configured_revenue_category_reaches_the_journal_and_the_bucket() -> None:
    """Codex C4-R1 (review of f764ca0): with ``TPL-OT.disaggregation["revenue_category"] =
    "CONFIGURED-CATEGORY"`` the allocation keeps the configured value on K-TIMING/POB-OT
    (``disaggregation_tags``: the template is the configured source), so the April REVENUE credit
    of 600.00 (account 4000) must carry it and the disclosure must bucket it there — not under the
    ordinary ``SUBSCRIPTION`` — while every monetary line and total stays identical to the
    positive fixture (April 8,800.00)."""
    positive = _timing_world()
    challenge = _timing_world(configured_category="CONFIGURED-CATEGORY")
    book = _book(challenge, "ASC606")
    state = _state(challenge)
    (obligation,) = [
        ob for ob in _allocated(challenge).obligations if ob.subject_key == "K-TIMING/POB-OT"
    ]
    assert obligation.dimensions["revenue_category"] == "CONFIGURED-CATEGORY"  # native state
    april_ot = [
        (amount, dims)
        for _, period, subject, amount, dims in _revenue_lines(book)
        if period == "FY2026-P04" and subject == "K-TIMING/POB-OT"
    ]
    assert [amount for amount, _ in april_ot] == [60_000]
    assert april_ot[0][1]["revenue_category"] == "CONFIGURED-CATEGORY"  # journal REVENUE tag
    rows = {
        (r.period_key, r.dimension, r.value): r.amount
        for r in state.disaggregation.rows
        if r.entity == bundles.ENTITY_CODE
    }
    assert rows[("FY2026-P04", "revenue_category", "CONFIGURED-CATEGORY")] == 60_000  # bucket
    assert ("FY2026-P04", "revenue_category", "SUBSCRIPTION") not in rows
    assert state.disaggregation.totals[(bundles.ENTITY_CODE, "FY2026-P04")] == 880_000
    # Money unchanged: every posting line without its dimensions, and every total, equals the
    # positive fixture's; the tie-out and the replay hold on both.
    positive_book = _book(positive, "ASC606")
    assert _money_lines(book) == _money_lines(positive_book)
    assert dict(state.disaggregation.totals) == dict(_state(positive).disaggregation.totals)
    _assert_inv_03(state, book)
    _assert_inv_03(_state(positive), positive_book)
    _replays(book)


def test_s15_r15_timing_split_and_template_mapping() -> None:
    """EX-15-B's April timing: point in time 8,200.00 (the 8,000.00 delivery plus the 200.00
    targeted bonus catch-up) and over time 600.00; the template mapping ``segment: Enterprise``
    and the product families reach the REVENUE lines; the prior-period node of April is zero for
    the delivered obligation (the bonus changes its price after delivery: 200.00 of April revenue
    from performance before April? — no: the delivery is in April, so the whole 200.00 is
    current-period) and the tie-out holds."""
    bundle = _timing_world()
    book = _book(bundle, "ASC606")
    state = _state(bundle)
    rows = {
        (r.period_key, r.dimension, r.value): r.amount
        for r in state.disaggregation.rows
        if r.entity == bundles.ENTITY_CODE
    }
    assert rows[("FY2026-P04", "timing_of_transfer", "POINT_IN_TIME")] == 820_000
    assert rows[("FY2026-P04", "timing_of_transfer", "OVER_TIME")] == 60_000
    assert rows[("FY2026-P04", "segment", "Enterprise")] == 820_000
    assert rows[("FY2026-P04", "segment", "-")] == 60_000
    assert rows[("FY2026-P04", "product_family", "Hardware")] == 820_000
    assert rows[("FY2026-P04", "product_family", "Subscriptions")] == 60_000
    assert rows[("FY2026-P04", "revenue_category", "SUBSCRIPTION")] == 60_000
    assert state.disaggregation.totals[(bundles.ENTITY_CODE, "FY2026-P04")] == 880_000
    prior = _rows(book, MEASURE)
    assert prior[("K-TIMING/POB-PIT", "FY2026-P04")] == "0.00"
    assert prior[("K-TIMING/POB-OT", "FY2026-P04")] == "0.00"
    _assert_inv_03(state, book)
    _replays(book)


# --- EX-15-C through the engine (S15-R-13; S08-R-14; D-97 (10)) ----------------------------------

K03 = "K-03"
K03_EAC = f"{K03}/EAC-01"


def _k03_eac(number: int, effective: date, total: str) -> EstimateVersionInput:
    base = estimate_version(K03_EAC, "EAC", number, effective, obligation_key="O1")
    return dataclasses.replace(base, expected_total_amount=Decimal(total))


def _k03_cost(stream: int, on: date, amount: str) -> EventInput:
    payload = {"obligation_key": "O1", "purpose": "PROGRESS_INPUT", "amount": Decimal(amount)}
    return bundles.event(K03, stream, "COST_INCURRED", on, payload, obligation_keys=["O1"])


def _k03_estimate(stream: int, version: EstimateVersionInput) -> EventInput:
    payload = {"estimate_version_id": version.version_key}
    event = bundles.event(K03, stream, "ESTIMATE_CHANGED", version.effective_date, payload)
    return dataclasses.replace(event, estimate_version_key=version.version_key)


def _k03_world(*, correction: bool = False, treatment: str = "CUMULATIVE_CATCH_UP") -> InputBundle:
    """EX-15-C as a bundle: K-03 O1 1,000,000.00 measured cost to cost with EAC 700,000.00; costs
    420,000.00 to 31 Aug 2026; change order +350,000.00 on 10 Sep 2026 (class N, cumulative
    catch-up) with EAC 820,000.00 recorded after it; costs 82,000.00 on 25 Sep; EAC 850,000.00 on
    30 Sep (measure-only). ``correction`` adds the J-14 cost of 20,500.00 dated 29 Sep;
    ``treatment`` is the amendment's chosen treatment (Codex C4-EAC-R1 varies it to PROSPECTIVE)."""
    inception, end, amended = date(2026, 1, 1), date(2027, 12, 31), date(2026, 9, 10)
    calendar = bundles.entity(months=24)
    template = dataclasses.replace(
        _pit_template("TPL-C2C"),
        satisfaction_pattern="OVER_TIME",
        over_time_criterion="OT_A",
        recognition_method="COST_TO_COST",
    )
    line = bundles.booking_line(
        "O1",
        product_code="SKU-BUILD",
        quantity="1",
        total_price="1000000.00",
        start=inception,
        end=end,
    )
    change = {
        "obligation_key": "O1",
        "action": "CHANGE",
        "product_code": "SKU-BUILD",
        "quantity_delta": Decimal("0"),
        "consideration_delta": Decimal("350000.00"),
    }
    modification = ModificationInput(
        modification_key="CR-K03-2026-09",
        effective_date=amended,
        kind="PRICE_CHANGE",
        template_mode=None,
        status="APPLIED",
        reference=None,
        questionnaire={},
        lines=(change,),
        price_change_amount=None,
        noncash_consideration=None,
        consideration_payable=None,
        scope_605_35=None,
        currency="USD",
        proposed_treatments={},
        chosen_treatments={},
        treatment_summary=None,
        ssp_basis={},
        judgement_key=None,
        content_sha256=None,
    )
    header = dataclasses.replace(
        bundles.contract(K03, inception=inception), modifications=(modification,)
    )
    v1 = _k03_eac(1, inception, "700000.00")
    v2 = _k03_eac(2, amended, "820000.00")
    v3 = _k03_eac(3, date(2026, 9, 30), "850000.00")
    amendment = {
        "modification_id": modification.modification_key,
        "treatments": {"O1": treatment},
        "lines": [change],
        "ssp_basis": {},
    }
    events = [
        bundles.event(
            K03, 1, "CONTRACT_BOOKED", inception, {"lines": [line]}, obligation_keys=["O1"]
        ),
        bundles.event(K03, 2, "CONTRACT_ACTIVATED", inception, {"checklist": {}}),
        _k03_estimate(3, v1),
        _k03_cost(4, date(2026, 8, 31), "420000.00"),
        bundles.event(K03, 5, "CONTRACT_AMENDED", amended, amendment, obligation_keys=["O1"]),
        _k03_estimate(6, v2),
        _k03_cost(7, date(2026, 9, 25), "82000.00"),
        _k03_estimate(8, v3),
    ]
    if correction:
        events.append(_k03_cost(9, date(2026, 9, 29), "20500.00"))
    products = (bundles.product("SKU-BUILD", template_code="TPL-C2C", family=None),)
    group = bundles.group((header,), group_key=f"CG-{K03}", products=products)
    policies = tuple(
        sorted(
            bundles.policy_set(book_code="ASC606", entity=calendar),
            key=lambda p: (p.code, p.scope, p.subject_key),
        )
    )
    book = BookInput("ASC606", True, (calendar.code,), policies, bundles.account_mapping())
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2027, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(book,),
        entities=(calendar,),
        group=group,
        contracts=(header,),
        events=tuple(sorted(events, key=lambda e: (e.effective_date, e.record_seq, e.event_key))),
        ssp_versions=(_ssp_version(["SKU-BUILD"], {"SKU-BUILD": "1000000.00"}),),
        pob_template_versions=(template,),
        rule_set_versions=(),
        estimate_versions=(v1, v2, v3),
        fx_rates=(),
        posted=(),
    )


def _september_revenue(book: BookOutput) -> int:
    lines = _revenue_lines(book)
    return sum(amount for _, posting, _, amount, _ in lines if posting == "FY2026-P09")


def test_ex_15_c_prior_period_aggregation() -> None:
    """EX-15-C (S15-R-13; S08-R-14; D-97 (10)): K-03 in September 2026 gives prior-period revenue
    67,058.82 and current-period revenue 130,235.30 of 197,294.12; the cost dated 29 September adds
    nothing to the prior-period measure."""
    book = _book(_k03_world(), "ASC606")
    _replays(book)
    subject, period = f"{K03}/O1", "FY2026-P09"
    assert _rows(book, MEASURE)[(subject, period)] == "67058.82"
    assert _rows(book, SUM)[(f"{K03}@{bundles.ENTITY_CODE}", period)] == "67058.82"
    assert _september_revenue(book) == 19729412
    assert _september_revenue(book) - 6705882 == 13023530
    corrected = _book(_k03_world(correction=True), "ASC606")
    assert _rows(corrected, MEASURE)[(subject, period)] == "67058.82"
    assert _september_revenue(corrected) == 22985294


def test_c4_eac_r1_prospective_amendment_gives_no_prior_period_portion() -> None:
    """Codex C4-EAC-R1: the EX-15-C bundle with ONLY the amendment treatment changed to PROSPECTIVE
    (same world, same costs and EAC versions) gives prior-period revenue 0.00 for September 2026
    — the 25-13(a) boundary resets the basis, so the later measure-only versions add nothing —
    while September revenue is 143,023.26 (600,000.00 base; 750,000.00 × 82,000 ÷ 430,000)."""
    book = _book(_k03_world(treatment="PROSPECTIVE"), "ASC606")
    _replays(book)
    subject, period = f"{K03}/O1", "FY2026-P09"
    assert _rows(book, MEASURE)[(subject, period)] == "0.00"
    assert _rows(book, SUM)[(f"{K03}@{bundles.ENTITY_CODE}", period)] == "0.00"
    assert _september_revenue(book) == 14302326
