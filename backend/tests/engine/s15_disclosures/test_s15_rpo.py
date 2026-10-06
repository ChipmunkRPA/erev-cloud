"""Stage 15 RPO, practical-expedient exemptions and time bands (EDS-1).

ENGINE_SPEC_B §15.1, §15.2.3 (S15-R-08 to S15-R-11), §15.3 S15-INV-02, §15.5, §15.7 EX-15-A;
POLICIES POL-197 to POL-201; D-76; 03 REQ-REC-021, REQ-TP-003. The worlds are computed by the real
engine with stage 15 registered; the stage 15 state is read from ``s13_books.run_books`` over the
same bundle. FASB Example 42 contract A is a right-to-invoice obligation, and stage 09 builds no
right-to-invoice measure yet (S09-R-02 fails closed), so contract A runs the real stage 15 over a
stage 09 fake (L3-2-Q-29). No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from unittest import mock

from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import (
    EstimateVersionInput,
    EventInput,
    InputBundle,
    ModificationInput,
    OutputBundle,
    ProductInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.dates import month_end
from erev_engine.enums import SatisfactionStatus
from erev_engine.money import decimal_to_minor
from erev_engine.stages import STAGES, s01_canonicalize, s13_books, s15_disclosures
from erev_engine.stages.s09_recognition import ObligationMeasures, RecognitionState, schedule
from erev_engine.stages.s15_disclosures import (
    DisclosureState,
    PriorPeriod,
    RpoRollforward,
    RpoRow,
    prior_period,
)
from erev_engine.stages.state import BookContext, PolicyResolver
from erev_engine.trace import Trace, TraceBuilder, reevaluate
from support import allocation_worlds as worlds
from support import bundles
from support.recognition import allocated_state, book_context, event_view, obligation, segment

ZERO = "0" * 64
KNOWN_AT = datetime(2030, 1, 1, tzinfo=UTC)
ONE_YEAR = "rpo.exemption_original_duration_one_year"
RIGHT_TO_INVOICE = "rpo.exemption_right_to_invoice"
WHOLLY_UNSATISFIED = "rpo.exemption_vc_wholly_unsatisfied"
STAGE_15_MEASURES = frozenset({"rpo_amount", "rpo_band", "rpo_excluded"})  # §15.5
PolicyValue = str | tuple[str, ...]
ENTITY = bundles.ENTITY_CODE


def usd(amount: str) -> int:
    return decimal_to_minor(Decimal(amount), 2)


# --- World ---------------------------------------------------------------------------------------


def template(
    code: str,
    *,
    method: str,
    pattern: str,
    convention: str | None = None,
    distinctness: str = "distinct",
    series_increment_unit: str = "month",
) -> TemplateInput:
    """A template version; ``series_increment_unit`` applies to ``series`` templates only."""
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256=ZERO,
        obligation_kind="STANDARD",
        distinctness=distinctness,
        series_increment_unit=series_increment_unit if distinctness == "series" else None,
        satisfaction_pattern=pattern,
        over_time_criterion="OT_A" if pattern == "OVER_TIME" else "NOT_APPLICABLE",
        recognition_method=method,
        ratable_convention=convention,
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


TEMPLATES = (  # template code order (§0.4)
    template("TPL-PIT", method="POINT_IN_TIME", pattern="POINT_IN_TIME"),
    # PRD K-02 O1 is a series with increment day (TPL-SUB-DAILY); its mod-date SSP prices the
    # remaining increments, so S06-R-11 does not scale it (D-90b).
    template(
        "TPL-SAAS",
        method="TIME_ELAPSED",
        pattern="OVER_TIME",
        convention="DAILY",
        distinctness="series",
        series_increment_unit="day",
    ),
    template(
        "TPL-SERIES",
        method="TIME_ELAPSED",
        pattern="OVER_TIME",
        convention="MONTHLY_EVEN",
        distinctness="series",
    ),
)


def product(code: str, template_code: str) -> ProductInput:
    return bundles.product(code, template_code=template_code, family=None)


def point(version_key: str, product_code: str, amount: str) -> SspEntryInput:
    """An observable point per line in USD (T-REF-31)."""
    return SspEntryInput(
        entry_key=f"{version_key}/{product_code}//-/USD",
        product_code=product_code,
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
        ranges=(SspRangeInput("NONE", None, None, Decimal(amount), None, None, None),),
    )


def ssp_version(
    number: int, entries: Sequence[SspEntryInput], start: date, end: date | None = None
) -> SspVersionInput:
    return SspVersionInput(
        ssp_book_code="SSP-US",
        version_key=f"SSP-US@v{number}",
        version_no=number,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label=None,
        effective_from_date=start,
        effective_to_date=end,
        status="APPROVED",
        approved_at=datetime(2020, 1, 1, tzinfo=UTC),
        content_sha256=ZERO,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=tuple(sorted(entries, key=lambda entry: entry.product_code)),
    )


def world(
    contract: str,
    events: Sequence[EventInput],
    *,
    products: Sequence[ProductInput],
    ssp: Sequence[SspVersionInput],
    inception: date,
    months: int,
    policies: Mapping[str, PolicyValue] | None = None,
    modifications: Sequence[ModificationInput] = (),
    estimates: Sequence[EstimateVersionInput] = (),
) -> InputBundle:
    """One activated contract in US01 under ``DEFAULT``; ``policies`` replace each scope's value."""
    calendar = bundles.entity(start=inception.replace(day=1), months=months)
    base = bundles.book("ASC606", entity=calendar)
    values = policies or {}
    book = dataclasses.replace(
        base,
        policies=tuple(
            dataclasses.replace(policy, value=values[policy.code])
            if policy.code in values
            else policy
            for policy in base.policies
        ),
    )
    header = dataclasses.replace(
        bundles.contract(contract, inception=inception), modifications=tuple(modifications)
    )
    activated = bundles.event(contract, 2, "CONTRACT_ACTIVATED", inception, {"checklist": {}})
    ordered = sorted(
        (*events, activated), key=lambda e: (e.effective_date, e.record_seq, e.event_key)
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=KNOWN_AT,
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(book,),
        entities=(calendar,),
        group=bundles.group((header,), products=products),
        contracts=(header,),
        events=tuple(ordered),
        ssp_versions=tuple(ssp),
        pob_template_versions=TEMPLATES,
        rule_set_versions=(),
        estimate_versions=tuple(sorted(estimates, key=lambda v: (v.estimate_key, v.version_no))),
        fx_rates=(),
        posted=(),
    )


def booked(contract: str, inception: date, *lines: Mapping[str, object]) -> EventInput:
    keys = [str(line["obligation_key"]) for line in lines]
    return bundles.event(
        contract, 1, "CONTRACT_BOOKED", inception, {"lines": list(lines)}, obligation_keys=keys
    )


def memo(contract: str, stream: int, on: date, key: str = "POB-01") -> EventInput:
    """A memo update that dates the version d_v and changes no measure."""
    payload = {"obligation_key": key, "memo_1": f"close {on.isoformat()}"}
    return bundles.event(contract, stream, "MEMO_UPDATED", on, payload, obligation_keys=[key])


def computed(value: InputBundle) -> tuple[OutputBundle, DisclosureState]:
    """``compute`` over ``value`` and the stage 15 state of the book loop over the same bundle."""
    output = compute(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    (result,) = s13_books.run_books(cb, STAGES)
    assert isinstance(result.state, DisclosureState)
    return output, result.state


def assert_reevaluates(trace: Trace) -> None:
    """Posted nodes exactly; exact nodes within 1e-12 (stage 05 exact inputs, L2-2-Q-40)."""
    recomputed = reevaluate(trace)
    for node in trace.nodes:
        if node.rounding_residue is not None:
            assert recomputed[node.id] == node.value, node.id
        else:
            gap = abs(Fraction(Decimal(recomputed[node.id])) - Fraction(Decimal(node.value)))
            assert gap <= Fraction(1, 10**12), (node.id, node.value, recomputed[node.id])


def assert_inv_02(state: DisclosureState, output: OutputBundle) -> None:
    """S15-INV-02 and S15-R-08 over every row of one book."""
    (book,) = output.books
    columns = {version.subject_key: version.columns for version in book.obligation_versions}
    for row in state.rpo:
        version = columns[row.subject_key]
        included = version["satisfaction_status"] in ("UNSATISFIED", "PARTIALLY_SATISFIED")
        assert row.included is included, row.subject_key
        allocated, revenue = version["allocated_amount"], version["revenue_cum"]
        assert isinstance(allocated, int) and isinstance(revenue, int)
        assert row.total == (allocated - revenue if included else 0), row.subject_key
        assert row.total == row.scheduled + row.awaiting  # before exemptions
        assert sum(row.placed) == row.total
        assert sum(row.bands) == row.after_exemptions == row.total - row.excluded
    # D-98 candidates 91 / 91a (S15-R-08 rev 1.26): ``rpo_amount`` is gross of the exemptions,
    # ``rpo_after_exemptions`` the named net, and the group node carries the exempt amount and
    # its ``rpo_excluded`` nodes as additive params whenever an expedient applies.
    gross = sum(row.total for row in state.rpo)
    net = sum(row.after_exemptions for row in state.rpo)
    assert state.rpo_amount == gross
    assert state.rpo_after_exemptions == net == gross - sum(row.excluded for row in state.rpo)
    assert book.contract_version is not None
    assert book.contract_version.columns["rpo_amount"] == gross
    group = next(node for node in book.trace.nodes if node.id == state.trace_nodes["rpo_amount"])
    assert group.params.get("excluded", "0") == str(gross - net)
    assert ("exempt_nodes" in group.params) is any(row.exemptions for row in state.rpo)


# --- EX-09-A world (K-02) ------------------------------------------------------------------------

K02 = "K-02"
K02_INCEPTION, K02_END, K02_MOD = date(2026, 1, 1), date(2027, 12, 31), date(2026, 9, 16)


def k02() -> InputBundle:
    """O1 240,000.00 DAILY over 2026 and 2027; O2 added on 16 Sep 2026 for 60,000.00 with mod-date
    SSPs 155,000 : 77,500; a memo dates the version on 30 Sep 2026 (EX-09-A). O1 and O2 are series
    with increment day (PRD K-02 O1), so the mod-date SSPs price the remaining increments and
    S06-R-11 weighs them unscaled (D-90b)."""
    line = bundles.booking_line(
        "POB-01", product_code="SKU-SAAS", quantity="1", total_price="240000.00", end=K02_END
    )
    addon = {
        "obligation_key": "POB-02",
        "action": "ADD",
        "product_code": "SKU-SEATS",
        "quantity_delta": Decimal("1"),
        "consideration_delta": Decimal("60000.00"),
        "start_date": K02_MOD,
        "end_date": K02_END,
    }
    modification = ModificationInput(
        modification_key="MOD-1",
        effective_date=K02_MOD,
        kind="ADD_OBLIGATION",
        template_mode=None,
        status="APPLIED",
        reference=None,
        questionnaire={},
        lines=(addon,),
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
    payload = {
        "modification_id": "MOD-1",
        "treatments": {"POB-01": "PROSPECTIVE", "POB-02": "PROSPECTIVE"},
        "lines": [addon],
        "ssp_basis": {},
    }
    amended = bundles.event(
        K02, 3, "CONTRACT_AMENDED", K02_MOD, payload, obligation_keys=["POB-02"]
    )
    return world(
        K02,
        [booked(K02, K02_INCEPTION, line), amended, memo(K02, 4, date(2026, 9, 30))],
        products=[product("SKU-SAAS", "TPL-SAAS"), product("SKU-SEATS", "TPL-SAAS")],
        ssp=[
            ssp_version(
                1,
                [point("SSP-US@v1", "SKU-SAAS", "240000.00")],
                date(2025, 1, 1),
                date(2026, 8, 31),
            ),
            ssp_version(
                2,
                [
                    point("SSP-US@v2", "SKU-SAAS", "155000.00"),
                    point("SSP-US@v2", "SKU-SEATS", "77500.00"),
                ],
                date(2026, 9, 1),
            ),
        ],
        inception=K02_INCEPTION,
        months=24,
        modifications=[modification],
    )


def test_ex_15_a_rpo_time_bands() -> None:
    value = k02()
    output, state = computed(value)
    assert state.as_of == date(2026, 9, 30)
    (book,) = output.books
    columns = {version.subject_key: version.columns for version in book.obligation_versions}
    rows = {row.subject_key: row for row in state.rpo}
    o1, o2 = rows[f"{K02}/POB-01"], rows[f"{K02}/POB-02"]
    # O1 RPO 228,273.97 − 89,380.78; O2 71,726.03 − 2,279.43; total 300,000.00 − 91,660.21.
    assert (
        columns[o1.subject_key]["allocated_amount"],
        columns[o1.subject_key]["revenue_cum"],
    ) == (
        usd("228273.97"),
        usd("89380.78"),
    )
    assert (
        columns[o2.subject_key]["allocated_amount"],
        columns[o2.subject_key]["revenue_cum"],
    ) == (
        usd("71726.03"),
        usd("2279.43"),
    )
    assert (o1.total, o2.total) == (usd("138893.19"), usd("69446.60"))
    assert state.rpo_amount == o1.total + o2.total == usd("208339.79")
    assert book.contract_version is not None
    assert book.contract_version.columns["rpo_amount"] == usd("208339.79")
    # Band boundaries 30 Sep 2027 and 30 Sep 2028 (POL-201 default [12, 24]).
    assert o1.bounds == o2.bounds == (date(2027, 9, 30), date(2028, 9, 30))
    bands = tuple(first + second for first, second in zip(o1.bands, o2.bands, strict=True))
    assert bands == (usd("166398.30"), usd("41941.49"), 0)
    # Within 12 months = Σ schedule amounts for periods ending 31 Oct 2026 to 30 Sep 2027; 13 to 24
    # months = the periods to 31 Dec 2027.
    ends = {period.period_key: period.end_date for period in value.entities[0].periods}
    later = [line for line in book.schedules if ends[line.period_key] > state.as_of]
    assert sum(line.amount for line in later if ends[line.period_key] <= o1.bounds[0]) == bands[0]
    assert sum(line.amount for line in later if ends[line.period_key] > o1.bounds[0]) == bands[1]
    nodes = {node.id: node for node in book.trace.nodes}
    group = nodes["rpo_amount:CG-1:-"]
    assert (group.formula_id, group.value, group.params["signs"]) == (
        "disc.rpo.v1",
        "208339.79",
        "+|+",
    )
    band = nodes[f"rpo_band:{K02}/POB-01/0:-"]
    assert (band.formula_id, band.value, band.params["bounds"]) == (
        "disc.rpo_band.v1",
        "110932.20",
        "2027-09-30|2028-09-30",
    )
    assert nodes[f"rpo_amount:{K02}/POB-01:-"].inputs == (
        f"scheduled_amount:{K02}/POB-01:-",
        f"awaiting_trigger_amount:{K02}/POB-01:-",
    )
    assert book.contract_version.trace_nodes["rpo_amount"] == "rpo_amount:CG-1:-"
    assert_inv_02(state, output)
    # The stage 15 nodes re-evaluate. Stage 09 publishes the MODIFICATION cause of September at
    # the 25-13(a) boundary (−24.84 and +151.96) while citing the stage 06 catch-up node of 0.00,
    # so those stage 09 nodes do not re-evaluate in this world (L3-2-Q-30).
    recomputed = reevaluate(book.trace)
    stage_15 = [node for node in book.trace.nodes if node.measure in STAGE_15_MEASURES]
    assert len(stage_15) == 1 + 2 * (1 + 3)  # the group, and per obligation its RPO and 3 bands
    assert all(recomputed[node.id] == node.value for node in stage_15)


# --- FASB Example 42 -----------------------------------------------------------------------------

EX42_SIGNED, EX42_START, EX42_END = date(2027, 6, 30), date(2027, 7, 1), date(2029, 6, 30)
EX42_AS_OF = date(2027, 12, 31)
MONTHLY: Mapping[str, PolicyValue] = {"recognition.time_convention": "MONTHLY_EVEN"}


def ex42(contract: str, price: str, *, bonus: bool = False) -> InputBundle:
    """A two-year cleaning contract signed on 30 June 2027 and billed to the as-of date."""
    product_code = f"SVC-{contract[-1]}"
    line = bundles.booking_line(
        "POB-01",
        product_code=product_code,
        quantity="1",
        total_price=price,
        start=EX42_START,
        end=EX42_END,
    )
    invoice = {
        "invoice_number": f"INV-{contract}",
        "line_external_id": f"INV-{contract}-1",
        "obligation_key": "POB-01",
        "amount": Decimal("600.00"),
        "issue_date": EX42_AS_OF,
    }
    events = [
        booked(contract, EX42_SIGNED, line),
        bundles.event(
            contract, 3, "BILLING_RECORDED", EX42_AS_OF, invoice, obligation_keys=["POB-01"]
        ),
    ]
    estimates: list[EstimateVersionInput] = []
    if bonus:  # the one-time bonus of 0 to 1,000.00, of which 750.00 passes the constraint
        key = f"{contract}/VC-BONUS"
        estimates.append(
            EstimateVersionInput(
                estimate_key=key,
                estimate_kind="VARIABLE_CONSIDERATION",
                element_code="VC-BONUS",
                method="MOST_LIKELY_AMOUNT",
                vc_element_type="BONUS",
                allocation_target="CONTRACT",
                target_obligation_keys=(),
                obligation_key=None,
                version_key=f"{key}@v1",
                version_no=1,
                status="APPROVED",
                effective_date=EX42_SIGNED,
                scenarios=(
                    {"amount": Decimal("1000.00"), "probability": Decimal("0.75")},
                    {"amount": Decimal("0.00"), "probability": Decimal("0.25")},
                ),
                parameters={},
                unconstrained_amount=Decimal("1000.00"),
                most_conservative_amount=Decimal("750.00"),
                constrained_amount=Decimal("750.00"),
                rate=None,
                expected_total_amount=None,
                expected_quantity=None,
                amortization_months=None,
                currency="USD",
                supersedes_version_key=None,
                judgement_key=None,
                content_sha256=ZERO,
            )
        )
        payload = {"estimate_version_id": estimates[0].version_key}
        events.append(bundles.event(contract, 4, "ESTIMATE_CHANGED", EX42_SIGNED, payload))
    return world(
        contract,
        events,
        products=[product(product_code, "TPL-SERIES")],
        ssp=[ssp_version(1, [point("SSP-US@v1", product_code, price)], date(2020, 1, 1))],
        inception=EX42_SIGNED,
        months=30,
        policies=MONTHLY,
        estimates=estimates,
    )


def with_values(ctx_policies: PolicyResolver, values: Mapping[str, str]) -> PolicyResolver:
    return PolicyResolver(
        tuple(
            dataclasses.replace(policy, value=values[policy.code])
            if policy.code in values
            else policy
            for policy in ctx_policies.all()
        )
    )


def contract_a(elected: str) -> tuple[DisclosureState, Trace]:
    """Contract A: cleaning over the next year invoiced at an hourly rate (right to invoice), with
    1,200.00 expected and 600.00 invoiced and recognised at 31 Dec 2027, over a stage 09 fake."""
    calendar = bundles.entity(start=date(2027, 6, 1), months=30)
    base = book_context(calendar)
    ctx = dataclasses.replace(
        base, policies=with_values(base.policies, {RIGHT_TO_INVOICE: elected})
    )
    inception = segment(Fraction(1200), usd("1200.00"), start=EX42_START, end=date(2028, 6, 30))
    ob = obligation(
        "POB-01", [inception], contract_key="K-EX42-A", method="RIGHT_TO_INVOICE", convention=None
    )
    invoiced = event_view(
        "K-EX42-A",
        3,
        "MEMO_UPDATED",
        EX42_AS_OF,
        {"obligation_key": "POB-01"},
        obligation_keys=["POB-01"],
    )
    allocated = allocated_state([ob], events=[invoiced], inception=EX42_SIGNED)
    measures = ObligationMeasures(
        subject_key=ob.subject_key,
        as_of=EX42_AS_OF,
        allocated_amount=usd("1200.00"),
        progress_ratio=Fraction(1, 2),
        revenue_cum=usd("600.00"),
        remaining_allocation=usd("600.00"),
        remaining_quantity=Fraction(0),
        scheduled_amount=0,
        awaiting_trigger_amount=usd("600.00"),
        catch_up_amount=0,
        catch_up_cum=0,
        catch_up_modification_cum=0,
        catch_up_tp_change_cum=0,
        catch_up_estimate_cum=0,
        satisfaction_status=SatisfactionStatus.PARTIALLY_SATISFIED,
        satisfied_date=None,
        hold_types=(),
        delivered_quantity=Fraction(0),
        revenue_amount=0,
        ssp_delivered=Fraction(0),
        ssp_delivered_cum=Fraction(0),
        trace_nodes={},
    )
    recognition = RecognitionState(
        allocated=allocated,
        revenue_targets=(),
        revenue_by_cause=(),
        return_states={},
        findings=(),
        obligation_measures={ob.subject_key: measures},
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    # L3-2-Q-29: the fake stands in for stage 09, which fails closed on a right-to-invoice measure
    # (S09-R-02). The EDS-4 consumer (`prior_period.build`) reads the same measure through stage
    # 08's `decompose_prior_period`, so the fake bypasses it too (ENG-C4); in the engine such an
    # obligation never reaches stage 15.
    with mock.patch.object(prior_period, "build", return_value=PriorPeriod((), ())):
        state = s15_disclosures.run(ctx, recognition, tb, recognition=recognition)
    return state, tb.build(root_measures={})


def test_ex_15_a_fasb_example_42() -> None:
    # Contract B: 400.00 a month for two years, 2,400.00 recognised by 31 Dec 2027.
    output_b, state_b = computed(ex42("K-EX42-B", "9600.00"))
    (row_b,) = state_b.rpo
    assert (state_b.as_of, row_b.total, row_b.bounds) == (
        EX42_AS_OF,
        usd("7200.00"),
        (date(2028, 12, 31), date(2029, 12, 31)),
    )
    assert row_b.bands == (usd("4800.00"), usd("2400.00"), 0)  # 7,200.00 = 4,800.00 + 2,400.00
    assert_inv_02(state_b, output_b)
    # Contract C: 100.00 a month plus 750.00 of the bonus; 787.50 recognised, 131.25 a month left.
    output_c, state_c = computed(ex42("K-EX42-C", "2400.00", bonus=True))
    (row_c,) = state_c.rpo
    (book_c,) = output_c.books
    assert book_c.contract_version is not None
    assert book_c.contract_version.columns["transaction_price"] == usd("3150.00")
    assert row_c.total == usd("2362.50")
    assert row_c.bands == (usd("1575.00"), usd("787.50"), 0)  # 2,362.50 = 1,575.00 + 787.50
    assert state_c.narrative.vc_excluded_amount == usd("250.00")
    assert_inv_02(state_c, output_c)
    assert_reevaluates(book_c.trace)
    # Contract A is exempt under POL-198 when elected and listed with its nature and remaining
    # duration.
    elected, trace = contract_a("APPLY")
    (row_a,) = elected.rpo
    (exemption,) = row_a.exemptions
    assert (exemption.policy, exemption.code, exemption.subject_key, exemption.amount) == (
        "POL-198",
        RIGHT_TO_INVOICE,
        "K-EX42-A/POB-01",
        usd("600.00"),
    )
    assert (exemption.nature, exemption.end_date, exemption.remaining_months) == (
        "RIGHT_TO_INVOICE STANDARD",
        date(2028, 6, 30),
        6,
    )
    assert "right to invoice" in exemption.description
    # D-98 candidates 91 / 91a: the expedient contract carries its contractual remaining amount
    # as ``rpo_amount`` (gross), reported under the excluded amount and never in the bands; the
    # named net is 0 and the group node states gross = net + exempt.
    assert (row_a.total, row_a.excluded, row_a.bands, elected.rpo_amount) == (
        usd("600.00"),
        usd("600.00"),
        (0, 0, 0),
        usd("600.00"),
    )
    assert elected.rpo_after_exemptions == 0
    group = next(node for node in trace.nodes if node.id == elected.trace_nodes["rpo_amount"])
    assert (group.value, group.params["signs"], group.params["excluded"]) == (
        "600.00",
        "+",
        "60000",
    )
    assert group.params["exempt_nodes"] == exemption.node_id
    assert group.inputs == (row_a.trace_nodes["rpo_amount"],)
    assert elected.narrative.exempt == (exemption,)
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    not_elected, _ = contract_a("DO_NOT_APPLY")
    (row,) = not_elected.rpo
    assert (row.exemptions, row.bands, not_elected.rpo_amount) == (
        (),
        (usd("600.00"), 0, 0),  # awaiting trigger placed by the end date 30 Jun 2028
        usd("600.00"),
    )


# --- One-year exemption and the narrative dataset ------------------------------------------------


def one_year(end: date, elected: str) -> InputBundle:
    """A subscription of 12,000.00 from 1 Jan 2026 to ``end`` and hardware of 3,000.00 not yet
    delivered, versioned on 30 June 2026."""
    inception = date(2026, 1, 1)
    lines = (
        bundles.booking_line(
            "POB-01", product_code="SKU-SAAS", quantity="1", total_price="12000.00", end=end
        ),
        bundles.booking_line(
            "POB-02",
            product_code="SKU-HW",
            quantity="1",
            total_price="3000.00",
            end=date(2026, 3, 31),
        ),
    )
    return world(
        "K-1Y",
        [booked("K-1Y", inception, *lines), memo("K-1Y", 3, date(2026, 6, 30))],
        products=[product("SKU-HW", "TPL-PIT"), product("SKU-SAAS", "TPL-SAAS")],
        ssp=[
            ssp_version(
                1,
                [
                    point("SSP-US@v1", "SKU-HW", "3000.00"),
                    point("SSP-US@v1", "SKU-SAAS", "12000.00"),
                ],
                date(2020, 1, 1),
            )
        ],
        inception=inception,
        months=24,
        policies={ONE_YEAR: elected},
    )


def test_s15_r09_one_year_exemption() -> None:
    output, state = computed(one_year(date(2026, 12, 31), "APPLY"))
    rows: dict[str, RpoRow] = {row.subject_key: row for row in state.rpo}
    assert set(rows) == {"K-1Y/POB-01", "K-1Y/POB-02"}
    for row in rows.values():
        (exemption,) = row.exemptions
        assert (exemption.policy, exemption.code, exemption.amount) == (
            "POL-197",
            ONE_YEAR,
            row.total,
        )
        assert row.total > 0 and row.excluded == row.total
        assert row.bands == (0, 0, 0)  # excluded from the bands
    assert rows["K-1Y/POB-02"].total == usd("3000.00")  # undelivered: awaiting trigger
    assert rows["K-1Y/POB-01"].exemptions[0].remaining_months == 6
    # Gross RPO stays the contractual remaining amount; the net after POL-197 is 0 (D-98 91a).
    assert state.rpo_amount == sum(row.total for row in rows.values()) > 0
    assert state.rpo_after_exemptions == 0
    assert state.narrative.exempt == tuple(item for row in state.rpo for item in row.exemptions)
    assert_inv_02(state, output)
    # Not elected: nothing is exempt and the bands carry the RPO.
    output, not_elected = computed(one_year(date(2026, 12, 31), "DO_NOT_APPLY"))
    assert all(row.exemptions == () for row in not_elected.rpo)
    assert not_elected.rpo_amount == sum(row.total for row in rows.values())
    assert_inv_02(not_elected, output)
    # Thirteen months from inception is not one year or less.
    output, longer = computed(one_year(date(2027, 1, 31), "APPLY"))
    assert all(row.exemptions == () for row in longer.rpo)
    assert longer.rpo_amount == sum(row.total for row in longer.rpo) > 0
    assert_inv_02(longer, output)


def ex_04_a(elected: str) -> InputBundle:
    """EX-04-A: base 2,500,000.00; incentive by EXPECTED_VALUE U = 5,000.00; bonus 150,000.00 by
    MOST_LIKELY_AMOUNT constrained to 0.00; one point-in-time obligation over 2026."""
    contract, inception = "K-01", date(2026, 1, 1)
    versions = []
    for element, method, kind, scenarios, unconstrained, conservative, constrained in (
        (
            "VC-INCENTIVE",
            "EXPECTED_VALUE",
            "PERFORMANCE_INCENTIVE",
            (("100000.00", "0.2"), ("0.00", "0.5"), ("-50000.00", "0.3")),
            "5000.00",
            None,
            "5000.00",
        ),
        (
            "VC-BONUS",
            "MOST_LIKELY_AMOUNT",
            "BONUS",
            (("150000.00", "0.7"), ("0.00", "0.3")),
            "150000.00",
            "0.00",
            "0.00",
        ),
    ):
        key = f"{contract}/{element}"
        versions.append(
            EstimateVersionInput(
                estimate_key=key,
                estimate_kind="VARIABLE_CONSIDERATION",
                element_code=element,
                method=method,
                vc_element_type=kind,
                allocation_target="CONTRACT",
                target_obligation_keys=(),
                obligation_key=None,
                version_key=f"{key}@v1",
                version_no=1,
                status="APPROVED",
                effective_date=inception,
                scenarios=tuple(
                    {"amount": Decimal(amount), "probability": Decimal(probability)}
                    for amount, probability in scenarios
                ),
                parameters={},
                unconstrained_amount=Decimal(unconstrained),
                most_conservative_amount=None if conservative is None else Decimal(conservative),
                constrained_amount=Decimal(constrained),
                rate=None,
                expected_total_amount=None,
                expected_quantity=None,
                amortization_months=None,
                currency="USD",
                supersedes_version_key=None,
                judgement_key=None,
                content_sha256=ZERO,
            )
        )
    line = bundles.booking_line(
        "POB-01",
        product_code="SKU-1",
        quantity="1",
        total_price="2500000.00",
        end=date(2026, 12, 31),
    )
    events = [booked(contract, inception, line)]
    for stream, version in enumerate(sorted(versions, key=lambda v: v.estimate_key), start=3):
        payload = {"estimate_version_id": version.version_key}
        events.append(bundles.event(contract, stream, "ESTIMATE_CHANGED", inception, payload))
    return world(
        contract,
        events,
        products=[product("SKU-1", "TPL-PIT")],
        ssp=[ssp_version(1, [point("SSP-US@v1", "SKU-1", "2500000.00")], date(2020, 1, 1))],
        inception=inception,
        months=24,
        policies={ONE_YEAR: elected},
        estimates=versions,
    )


def test_s15_r11_narrative_dataset() -> None:
    output, state = computed(ex_04_a("APPLY"))
    (book,) = output.books
    assert book.contract_version is not None
    assert book.contract_version.columns["vc_excluded_amount"] == usd("150000.00")
    narrative = state.narrative
    assert (narrative.group_key, narrative.vc_excluded_amount) == ("CG-1", usd("150000.00"))
    (exemption,) = narrative.exempt
    assert (exemption.policy, exemption.subject_key, exemption.amount) == (
        "POL-197",
        "K-01/POB-01",
        usd("2505000.00"),  # allocation basis 2,505,000.00, nothing recognised
    )
    assert exemption.description.startswith("consideration of a contract with an original expected")
    assert (state.rpo_amount, state.rpo_after_exemptions) == (usd("2505000.00"), 0)  # D-98 91a
    _, not_elected = computed(ex_04_a("DO_NOT_APPLY"))
    assert (not_elected.narrative.vc_excluded_amount, not_elected.narrative.exempt) == (
        usd("150000.00"),
        (),
    )
    assert not_elected.rpo_amount == usd("2505000.00")


# --- S15-INV-02 ----------------------------------------------------------------------------------


def partial(elected: str) -> InputBundle:
    """Hardware 800.00 delivered in January 2026; a subscription for 2027 and 2028 at 0.00 with
    variable consideration 1,000.00 allocated entirely to it (32-40 attested); version 30 June
    2026, when the subscription is wholly unsatisfied."""
    contract, inception = "K-VC", date(2026, 1, 1)
    lines = (
        bundles.booking_line(
            "L1-X",
            product_code="SKU-HW",
            quantity="1",
            total_price="800.00",
            end=date(2026, 1, 31),
        ),
        bundles.booking_line(
            "L2-Y",
            product_code="SKU-SUB",
            quantity="1",
            total_price="0.00",
            start=date(2027, 1, 1),
            end=date(2028, 12, 31),
        ),
    )
    key = f"{contract}/VC-1"
    element = EstimateVersionInput(
        estimate_key=key,
        estimate_kind="VARIABLE_CONSIDERATION",
        element_code="VC-1",
        method="ENTERED_AMOUNT",
        vc_element_type=None,
        allocation_target="OBLIGATIONS",
        target_obligation_keys=("L2-Y",),
        obligation_key=None,
        version_key=f"{key}@v1",
        version_no=1,
        status="APPROVED",
        effective_date=inception,
        scenarios=(),
        parameters={"allocation_criteria_evidence": "Reviewer attested 606-10-32-40(a) and (b)"},
        unconstrained_amount=None,
        most_conservative_amount=None,
        constrained_amount=Decimal("1000.00"),
        rate=None,
        expected_total_amount=None,
        expected_quantity=None,
        amortization_months=None,
        currency="USD",
        supersedes_version_key=None,
        judgement_key=None,
        content_sha256=ZERO,
    )
    delivery = {"obligation_key": "L1-X", "quantity": Decimal("1"), "trigger": "DELIVERY"}
    events = [
        booked(contract, inception, *lines),
        bundles.event(
            contract, 3, "ESTIMATE_CHANGED", inception, {"estimate_version_id": element.version_key}
        ),
        bundles.event(
            contract, 4, "DELIVERY_RECORDED", date(2026, 1, 31), delivery, obligation_keys=["L1-X"]
        ),
        memo(contract, 5, date(2026, 6, 30), key="L1-X"),
    ]
    return world(
        contract,
        events,
        products=[product("SKU-HW", "TPL-PIT"), product("SKU-SUB", "TPL-SAAS")],
        ssp=[
            ssp_version(
                1,
                [point("SSP-US@v1", "SKU-HW", "800.00"), point("SSP-US@v1", "SKU-SUB", "1000.00")],
                date(2020, 1, 1),
            )
        ],
        inception=inception,
        months=36,
        policies={WHOLLY_UNSATISFIED: elected},
        estimates=[element],
    )


def test_s15_inv_02_bands_sum_to_rpo() -> None:
    for value in (k02(), one_year(date(2026, 12, 31), "APPLY"), partial("DO_NOT_APPLY")):
        output, state = computed(value)
        assert_inv_02(state, output)
    # A partial exemption (POL-200): the subscription's RPO 1,444.44 less the targeted VC quota
    # 1,000.00, apportioned over the placed amounts with largest_remainder (S15-R-10).
    output, state = computed(partial("APPLY"))
    rows = {row.subject_key: row for row in state.rpo}
    hardware, subscription = rows["K-VC/L1-X"], rows["K-VC/L2-Y"]
    assert (hardware.included, hardware.total, hardware.exemptions) == (False, 0, ())
    assert (subscription.total, subscription.excluded) == (usd("1444.44"), usd("1000.00"))
    assert subscription.bounds == (date(2027, 6, 30), date(2028, 6, 30))
    assert subscription.placed == (usd("357.65"), usd("723.21"), usd("363.58"))
    assert subscription.bands == (usd("110.05"), usd("222.52"), usd("111.87"))
    (exemption,) = subscription.exemptions
    assert (exemption.policy, exemption.remaining_months) == ("POL-200", 30)
    assert (state.rpo_amount, state.rpo_after_exemptions) == (usd("1444.44"), usd("444.44"))
    assert_inv_02(state, output)
    (book,) = output.books
    nodes = {node.id: node for node in book.trace.nodes}
    excluded = nodes["rpo_excluded:K-VC/L2-Y/POL-200:-"]
    assert (excluded.formula_id, excluded.value, excluded.params["amount"]) == (
        "disc.rpo_exemption.v1",
        "1000.00",
        "100000",
    )
    band = nodes["rpo_band:K-VC/L2-Y/1:-"]
    assert (band.value, band.inputs) == ("222.52", ("rpo_amount:K-VC/L2-Y:-", excluded.id))
    assert_reevaluates(book.trace)


# --- D-91 C606-02: POL-200 reads the targeted quota in force at the measured date -------------


def dated_rpo(
    ctx: BookContext,
    recognition: RecognitionState,
    at: date,
    subjects: Iterable[str] | None = None,
) -> int:
    """The RPO after exemptions of the stage 09 obligation measures dated at ``at`` (S15-INV-08),
    over every measured obligation or over ``subjects`` only."""
    chosen = None if subjects is None else set(subjects)
    measures = {
        ob.subject_key: schedule.obligation_measures(ctx, recognition.allocated, ob, at)
        for ob in recognition.allocated.obligations
        if ob.subject_key in recognition.obligation_measures
        and (chosen is None or ob.subject_key in chosen)
    }
    dated = dataclasses.replace(recognition, obligation_measures=measures)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    # D-98 91a: ``Rpo.total`` is gross; S15-INV-08 compares the net after exemptions.
    return s15_disclosures.rpo.build(ctx, recognition.allocated, dated, tb).after_exemptions


def disclosure(value: InputBundle) -> tuple[BookContext, DisclosureState, RecognitionState]:
    """The book context and the stage 15 and stage 09 states of the book loop over ``value``."""
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    (result,) = s13_books.run_books(cb, STAGES)
    assert isinstance(result.state, DisclosureState)
    recognition = result.states["09"]
    assert isinstance(recognition, RecognitionState)
    return s13_books.book_context(cb, cb.books[str(result.book)]), result.state, recognition


def _allocations(output: OutputBundle) -> dict[str, int]:
    (book,) = output.books
    found: dict[str, int] = {}
    for version in book.obligation_versions:
        allocated = version.columns["allocated_amount"]
        assert isinstance(allocated, int)
        found[version.subject_key.rsplit("/", 1)[-1]] = allocated
    return found


def _lines(rollforward: RpoRollforward, *names: str) -> dict[str, int]:
    return {name: rollforward.lines[name] for name in names}


ROLLFORWARD_KEYS = (
    "OPENING",
    "NEW_CONTRACTS",
    "VC_ESTIMATE_CHANGES",
    "EXEMPTIONS",
    "REVENUE",
    "CLOSING",
    "UNEXPLAINED",
    "LATE_EVENTS",
)


def test_s15_r09_pol_200_reads_quota_in_force() -> None:
    """S3: an evidenced targeted element rises 100 → 200 on 1 Feb with both obligations wholly
    unsatisfied under POL-200 APPLY: allocations 250.00/50.00 are right, the exclusion is the quota
    in force at d_v (200.00 with ``quota_as_of`` 2026-02-28) and the RPO stays 100.00 (main 200.00);
    S3b: a targeted 100 → −50 leaves A at 0 with a cap of 0 (a negative quota exempts nothing) and
    RPO_A 0; S4: an evidenced element entering 0 → 100 on 1 Feb followed by an untargeted 0 → 100 on
    1 Mar gives Feb 150.00/50.00 RPO 100.00 and Mar 200.00/100.00 RPO 200.00 (main Mar 150/150,
    RPO 300.00)."""
    targeted = worlds.element("100", keys=["A"])
    value = worlds.targeted_world(estimates=[targeted])
    s3 = worlds.with_changes(
        value,
        [worlds.later_version(targeted, 2, date(2026, 2, 1), "200")],
        memo_on=date(2026, 2, 28),
        policies={WHOLLY_UNSATISFIED: "APPLY"},
    )
    output, state = computed(s3)
    assert _allocations(output) == {"A": 25000, "B": 5000}
    rows = {row.subject_key: row for row in state.rpo}
    assert (rows["K-01/A"].total, rows["K-01/A"].excluded, rows["K-01/B"].excluded) == (
        25000,
        20000,
        0,
    )
    assert (state.rpo_amount, state.rpo_after_exemptions) == (30000, 10000)  # gross / net
    (book,) = output.books
    assert book.contract_version is not None
    assert book.contract_version.columns["rpo_amount"] == 30000
    nodes = {node.id: node for node in book.trace.nodes}
    excluded = nodes["rpo_excluded:K-01/A/POL-200:-"]
    assert (excluded.formula_id, excluded.value, excluded.params["amount"]) == (
        "disc.rpo_exemption.v1",
        "200.00",
        "20000",
    )
    assert excluded.params["quota_as_of"] == "2026-02-28"
    assert excluded.params["quota_nodes"] == (
        "targeted_vc_allocated@K-01%2FVC-1:K-01/A:-|tp_share@K-01/EV-000004:K-01/A:-"
    )
    assert all(node in nodes for node in excluded.params["quota_nodes"].split("|"))
    assert_reevaluates(book.trace)
    # S3b: targeted 100 → −50; the exact quota of A moves 150 → 0 (not negative), the quota in
    # force is −50.00 and exempts nothing.
    s3b = worlds.with_changes(
        value,
        [worlds.later_version(targeted, 2, date(2026, 2, 1), "-50")],
        memo_on=date(2026, 2, 28),
        policies={WHOLLY_UNSATISFIED: "APPLY"},
    )
    output, state = computed(s3b)
    assert _allocations(output) == {"A": 0, "B": 5000}
    rows = {row.subject_key: row for row in state.rpo}
    (exemption,) = rows["K-01/A"].exemptions
    assert (rows["K-01/A"].total, rows["K-01/A"].excluded, exemption.amount) == (0, 0, 0)
    (book,) = output.books
    node = next(n for n in book.trace.nodes if n.id == "rpo_excluded:K-01/A/POL-200:-")
    assert (node.params["amount"], node.value) == ("0", "0.00")
    assert (state.rpo_amount, state.rpo_after_exemptions) == (5000, 5000)
    # S4: the targeted element enters after inception through stage 08.
    entering = worlds.element("0", keys=["A"])
    base = worlds.untargeted_element("0")
    value = worlds.targeted_world(estimates=[entering, base])
    changes = [
        worlds.later_version(entering, 2, date(2026, 2, 1), "100"),
        worlds.later_version(base, 2, date(2026, 3, 1), "100"),
    ]
    february = worlds.with_changes(value, changes[:1], policies={WHOLLY_UNSATISFIED: "APPLY"})
    output, state = computed(february)
    assert (_allocations(output), state.rpo_after_exemptions) == ({"A": 15000, "B": 5000}, 10000)
    march = worlds.with_changes(value, changes, policies={WHOLLY_UNSATISFIED: "APPLY"})
    output, state = computed(march)
    assert (_allocations(output), state.rpo_after_exemptions) == ({"A": 20000, "B": 10000}, 20000)
    rows = {row.subject_key: row for row in state.rpo}
    assert (rows["K-01/A"].excluded, rows["K-01/B"].excluded) == (10000, 0)
    (book,) = output.books
    assert_reevaluates(book.trace)


def _history(months: int) -> InputBundle:
    """The Codex 23-check history: targeted 100 (Jan) → 200 (1 Feb) → 50 (1 Apr) → 0 (1 May) → 100
    (1 Jun) and untargeted 0 → 100 (1 Mar) → 0 (1 Jul), POL-200 APPLY, both obligations wholly
    unsatisfied, dated by a memo on the end of month ``months``; changes after that month are not
    known to the bundle."""
    targeted = worlds.element("100", keys=["A"])
    base = worlds.untargeted_element("0")
    value = worlds.targeted_world(estimates=[targeted, base])
    changes = [
        worlds.later_version(targeted, 2, date(2026, 2, 1), "200"),
        worlds.later_version(base, 2, date(2026, 3, 1), "100"),
        worlds.later_version(targeted, 3, date(2026, 4, 1), "50"),
        worlds.later_version(targeted, 4, date(2026, 5, 1), "0"),
        worlds.later_version(targeted, 5, date(2026, 6, 1), "100"),
        worlds.later_version(base, 3, date(2026, 7, 1), "0"),
    ]
    end = month_end(date(2026, months, 1))
    return worlds.with_changes(
        value,
        [change for change in changes if change.effective_date <= end],
        memo_on=end,
        policies={WHOLLY_UNSATISFIED: "APPLY"},
    )


# month: (OPENING, NEW_CONTRACTS, VC_ESTIMATE_CHANGES, EXEMPTIONS, CLOSING), minor units
HISTORY = {
    1: (0, 20000, 0, -10000, 10000),
    2: (10000, 0, 10000, -10000, 10000),
    3: (10000, 0, 10000, 0, 20000),
    4: (20000, 0, -15000, 15000, 20000),
    5: (20000, 0, -5000, 5000, 20000),
    6: (20000, 0, 10000, -10000, 20000),
    7: (20000, 0, -10000, 0, 10000),
    8: (10000, 0, 0, 0, 10000),
}


def test_s15_r12_rollforward_reads_quota_at_each_end() -> None:
    """S15-R-12 (rev 1.7): the exempt amount at each end follows S15-R-09 read at that end's date,
    never the latest quota. S3 P02: OPENING 100.00 (quota 100.00 in force on 31 Jan), VC +100.00,
    EXEMPTIONS −100.00, CLOSING 100.00 (main EXEMPTIONS 0 / CLOSING 200.00; a latest-only map
    OPENING 50.00); S4 P02 and P03; the Codex 8-month history from the final state and from each
    month's bundle, with and without correct opening snapshots: UNEXPLAINED 0 and LATE_EVENTS 0
    everywhere."""
    targeted = worlds.element("100", keys=["A"])
    value = worlds.targeted_world(estimates=[targeted])
    s3 = worlds.with_changes(
        value,
        [worlds.later_version(targeted, 2, date(2026, 2, 1), "200")],
        memo_on=date(2026, 2, 28),
        policies={WHOLLY_UNSATISFIED: "APPLY"},
    )
    _, state, _ = disclosure(s3)
    (february,) = state.rpo_rollforwards
    assert february.period_key == "FY2026-P02"
    assert _lines(february, *ROLLFORWARD_KEYS) == {
        "OPENING": 10000,
        "NEW_CONTRACTS": 0,
        "VC_ESTIMATE_CHANGES": 10000,
        "EXEMPTIONS": -10000,
        "REVENUE": 0,
        "CLOSING": 10000,
        "UNEXPLAINED": 0,
        "LATE_EVENTS": 0,
    }
    # S4
    entering = worlds.element("0", keys=["A"])
    base = worlds.untargeted_element("0")
    value = worlds.targeted_world(estimates=[entering, base])
    changes = [
        worlds.later_version(entering, 2, date(2026, 2, 1), "100"),
        worlds.later_version(base, 2, date(2026, 3, 1), "100"),
    ]
    _, state, _ = disclosure(
        worlds.with_changes(value, changes[:1], policies={WHOLLY_UNSATISFIED: "APPLY"})
    )
    (february,) = state.rpo_rollforwards
    assert (
        february.period_key,
        _lines(february, "OPENING", "VC_ESTIMATE_CHANGES", "EXEMPTIONS", "CLOSING", "UNEXPLAINED"),
    ) == (
        "FY2026-P02",
        {
            "OPENING": 10000,
            "VC_ESTIMATE_CHANGES": 10000,
            "EXEMPTIONS": -10000,
            "CLOSING": 10000,
            "UNEXPLAINED": 0,
        },
    )
    ctx, state, recognition = disclosure(
        worlds.with_changes(value, changes, policies={WHOLLY_UNSATISFIED: "APPLY"})
    )
    (march,) = state.rpo_rollforwards
    assert (
        march.period_key,
        _lines(march, "OPENING", "VC_ESTIMATE_CHANGES", "EXEMPTIONS", "CLOSING", "UNEXPLAINED"),
    ) == (
        "FY2026-P03",
        {
            "OPENING": 10000,
            "VC_ESTIMATE_CHANGES": 10000,
            "EXEMPTIONS": 0,
            "CLOSING": 20000,
            "UNEXPLAINED": 0,
        },
    )
    again = s15_disclosures.rollforward(ctx, state.allocated, recognition, ENTITY, "FY2026-P02")
    assert dict(again.lines) == dict(february.lines)
    # The 8-month history from the final state, chained, with correct snapshots (LATE_EVENTS 0).
    ctx, state, recognition = disclosure(_history(8))
    previous: RpoRollforward | None = None
    for month, (opening, new, vc, exemptions, closing) in HISTORY.items():
        period = f"FY2026-P{month:02d}"
        found = s15_disclosures.rollforward(ctx, state.allocated, recognition, ENTITY, period)
        assert _lines(found, *ROLLFORWARD_KEYS) == {
            "OPENING": opening,
            "NEW_CONTRACTS": new,
            "VC_ESTIMATE_CHANGES": vc,
            "EXEMPTIONS": exemptions,
            "REVENUE": 0,
            "CLOSING": closing,
            "UNEXPLAINED": 0,
            "LATE_EVENTS": 0,
        }, period
        assert found.lines["CLOSING"] == dated_rpo(ctx, recognition, found.closing_date), period
        if previous is not None:
            assert found.lines["OPENING"] == previous.lines["CLOSING"]
            snapshot = {row.subject_key: row.lines["CLOSING"] for row in previous.rows}
            with_snapshot = s15_disclosures.rollforward(
                ctx, state.allocated, recognition, ENTITY, period, opening=snapshot
            )
            assert (with_snapshot.lines["LATE_EVENTS"], with_snapshot.unexplained) == (0, 0)
            assert dict(with_snapshot.lines) == dict(found.lines)
        previous = found
    # From each month's bundle: the published rollforward of the period holding d_v.
    for month, (opening, new, vc, exemptions, closing) in HISTORY.items():
        _, monthly, _ = disclosure(_history(month))
        (published,) = monthly.rpo_rollforwards
        assert published.period_key == f"FY2026-P{month:02d}"
        assert _lines(
            published,
            "OPENING",
            "NEW_CONTRACTS",
            "VC_ESTIMATE_CHANGES",
            "EXEMPTIONS",
            "CLOSING",
            "UNEXPLAINED",
        ) == {
            "OPENING": opening,
            "NEW_CONTRACTS": new,
            "VC_ESTIMATE_CHANGES": vc,
            "EXEMPTIONS": exemptions,
            "CLOSING": closing,
            "UNEXPLAINED": 0,
        }, month
        assert published.lines["CLOSING"] == monthly.rpo_after_exemptions
