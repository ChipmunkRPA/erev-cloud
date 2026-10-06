"""PROP:P7, engine part: RPO = allocated transaction price − cumulative revenue for unsatisfied or
partially satisfied obligations; RPO before exemptions = scheduled + awaiting trigger; the bands sum
to the RPO after exemptions; waterfall totals equal schedule totals (dev-guide §9.7 P7;
ENGINE_SPEC_B S15-R-02, S15-R-08, S15-R-10, S15-INV-02; REQ-REC-021; BUILD_SPEC EDS-1).

Generated groups: 1 to 3 obligations of one contract in US01, each a time-elapsed subscription
(``DAILY`` or ``MONTHLY_EVEN`` for the whole group) or a point-in-time good, with random prices,
SSP points, starts and terms; goods are delivered on the version date or not at all; a memo dates
the version d_v anywhere in 2026; POL-197 is drawn. The real engine computes the bundle and the
stage 15 state is read from the book loop over the same bundle.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import (
    EventInput,
    InputBundle,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.dates import add_months
from erev_engine.stages import STAGES, s01_canonicalize, s13_books
from erev_engine.stages.s15_disclosures import DisclosureState
from erev_engine.trace import TraceBuilder
from hypothesis import given
from hypothesis import strategies as st
from support import bundles, platform_props, strategies
from support.prop_worlds import WorldSpec, bundle

pytestmark = pytest.mark.property

CONTRACT = "K-P7"
INCEPTION = date(2026, 1, 1)
ZERO_SHA = "0" * 64
INCLUDED = ("UNSATISFIED", "PARTIALLY_SATISFIED")


def template(code: str, method: str, pattern: str, convention: str | None) -> TemplateInput:
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256=ZERO_SHA,
        obligation_kind="STANDARD",
        distinctness="distinct",
        series_increment_unit=None,
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


TEMPLATES = (
    template("TPL-PIT", "POINT_IN_TIME", "POINT_IN_TIME", None),
    template("TPL-SAAS", "TIME_ELAPSED", "OVER_TIME", "DAILY"),
)


def point(product_code: str, amount: int) -> SspEntryInput:
    return SspEntryInput(
        entry_key=f"SSP-US@v1/{product_code}//-/USD",
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
        ranges=(SspRangeInput("NONE", None, None, Decimal(amount) / 100, None, None, None),),
    )


@st.composite
def rpo_groups(draw: st.DrawFn) -> InputBundle:
    count = draw(st.integers(min_value=1, max_value=3))
    as_of = INCEPTION + timedelta(days=draw(st.integers(min_value=0, max_value=364)))
    convention = draw(st.sampled_from(("DAILY", "MONTHLY_EVEN")))
    lines: list[dict[str, object]] = []
    products = []
    entries = []
    events: list[EventInput] = []
    for index in range(1, count + 1):
        key = f"POB-{index:02d}"
        goods = draw(st.booleans())
        code = f"SKU-{index}"
        price = draw(st.integers(min_value=0, max_value=5_000_000))
        start = add_months(INCEPTION, draw(st.integers(min_value=0, max_value=6)))
        end = add_months(start, draw(st.integers(min_value=1, max_value=18))) - timedelta(days=1)
        lines.append(
            bundles.booking_line(
                key,
                product_code=code,
                quantity="1",
                total_price=str(Decimal(price) / 100),
                start=start,
                end=end,
            )
        )
        products.append(
            bundles.product(code, template_code="TPL-PIT" if goods else "TPL-SAAS", family=None)
        )
        entries.append(point(code, draw(st.integers(min_value=1, max_value=5_000_000))))
        if goods and draw(st.booleans()):
            payload = {"obligation_key": key, "quantity": Decimal("1"), "trigger": "DELIVERY"}
            events.append(
                bundles.event(
                    CONTRACT, 10 + index, "DELIVERY_RECORDED", as_of, payload, obligation_keys=[key]
                )
            )
    booked = bundles.event(
        CONTRACT,
        1,
        "CONTRACT_BOOKED",
        INCEPTION,
        {"lines": lines},
        obligation_keys=[str(line["obligation_key"]) for line in lines],
    )
    activated = bundles.event(CONTRACT, 2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}})
    memo = {"obligation_key": "POB-01", "memo_1": "version date"}
    dated = bundles.event(CONTRACT, 9, "MEMO_UPDATED", as_of, memo, obligation_keys=["POB-01"])
    calendar = bundles.entity(start=INCEPTION, months=36)
    base = bundles.book("ASC606", entity=calendar)
    values = {
        "recognition.time_convention": convention,
        "rpo.exemption_original_duration_one_year": draw(
            st.sampled_from(("APPLY", "DO_NOT_APPLY"))
        ),
    }
    book = dataclasses.replace(
        base,
        policies=tuple(
            dataclasses.replace(policy, value=values[policy.code])
            if policy.code in values
            else policy
            for policy in base.policies
        ),
    )
    header = bundles.contract(CONTRACT, inception=INCEPTION)
    ordered = sorted(
        (booked, activated, dated, *events),
        key=lambda event: (event.effective_date, event.record_seq, event.event_key),
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2030, 1, 1, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(book,),
        entities=(calendar,),
        group=bundles.group((header,), products=products),
        contracts=(header,),
        events=tuple(ordered),
        ssp_versions=(
            SspVersionInput(
                ssp_book_code="SSP-US",
                version_key="SSP-US@v1",
                version_no=1,
                resolution_mode="EFFECTIVE_DATE",
                legacy_version_label=None,
                effective_from_date=date(2020, 1, 1),
                effective_to_date=None,
                status="APPROVED",
                approved_at=datetime(2020, 1, 1, tzinfo=UTC),
                content_sha256=ZERO_SHA,
                scope_entity_code=None,
                scope_currency=None,
                scope_channel=None,
                scope_segment=None,
                entries=tuple(sorted(entries, key=lambda entry: entry.product_code)),
            ),
        ),
        pob_template_versions=TEMPLATES,
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


@given(value=rpo_groups())
def test_p07_engine_rpo(value: InputBundle) -> None:
    output = compute(value)
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    (result,) = s13_books.run_books(cb, STAGES)
    state = result.state
    assert isinstance(state, DisclosureState)
    (book,) = output.books
    columns = {version.subject_key: version.columns for version in book.obligation_versions}
    assert {row.subject_key for row in state.rpo} == set(columns)
    for row in state.rpo:
        version = columns[row.subject_key]
        allocated, revenue = version["allocated_amount"], version["revenue_cum"]
        scheduled, awaiting = version["scheduled_amount"], version["awaiting_trigger_amount"]
        assert all(isinstance(item, int) for item in (allocated, revenue, scheduled, awaiting))
        assert isinstance(allocated, int) and isinstance(revenue, int)
        assert isinstance(scheduled, int) and isinstance(awaiting, int)
        included = version["satisfaction_status"] in INCLUDED
        assert row.included is included
        # RPO = allocated constrained transaction price − cumulative revenue (S15-R-08).
        assert row.total == (allocated - revenue if included else 0)
        # RPO before exemptions = scheduled + awaiting trigger (REQ-REC-021 split).
        assert row.total == (scheduled + awaiting if included else 0)
        assert sum(row.placed) == row.total
        assert sum(row.bands) == row.total - row.excluded  # S15-INV-02
        # Waterfall totals equal schedule totals: recognised + scheduled = Σ schedule lines.
        lines = [line for line in book.schedules if line.subject_key == row.subject_key]
        assert sum(line.amount for line in lines) == revenue + scheduled
    # D-98 91a: ``rpo_amount`` is gross of the exemptions; ``rpo_after_exemptions`` is the net.
    gross = sum(row.total for row in state.rpo)
    after = sum(row.total - row.excluded for row in state.rpo)
    assert (state.rpo_amount, state.rpo_after_exemptions) == (gross, after)
    assert book.contract_version is not None
    assert book.contract_version.columns["rpo_amount"] == gross


# --- platform part (BUILD_SPEC PRP-5; S15-R-01, S15-R-02, S15-R-08) -------------------------------


@platform_props.platform_settings()
@given(spec=strategies.world_specs())
def test_p07_platform_rpo_and_waterfall(spec: WorldSpec) -> None:
    """PROP:P7 platform part: over a generated world closed as the platform closes it, every
    obligation's RPO = allocated transaction price − cumulative revenue when unsatisfied or
    partially satisfied (S15-R-08), scheduled + awaiting trigger = RPO before exemptions
    (REQ-REC-021 split; S09-INV-03), the contract's ``rpo_amount`` is the sum, and the waterfall
    ties: recognised per period (Σ REVENUE lines by posting period, S15-R-01) equals the schedule's
    amount of that period, and per obligation Σ schedule lines = recognised to date + scheduled
    (S15-R-02). The report runs ``rpo`` and ``revenue_waterfall`` through the report framework are
    DB-bound (reported not run until the lane databases exist)."""
    run = platform_props.close_run(bundle(spec, books=("ASC606", "LEGACY")))
    book = run.primary()
    rows = platform_props.rpo_rows(book)
    assert rows, "every world has obligations"
    for row in rows:
        assert row.rpo == (row.allocated - row.revenue_cum if row.included else 0)
        if row.included:
            assert row.scheduled + row.awaiting == row.rpo, row
        assert (
            platform_props.schedule_total(book, row.subject_key) == row.revenue_cum + row.scheduled
        ), row
    assert book.contract_version is not None
    columns = book.contract_version.columns
    assert columns["rpo_amount"] == sum(row.rpo for row in rows)
    assert columns["scheduled_amount"] == sum(row.scheduled for row in rows if row.included)
    assert columns["awaiting_trigger_amount"] == sum(row.awaiting for row in rows if row.included)
    entity = run.bundle.entities[0].code
    recognised = platform_props.recognised_by_period(run, entity)
    scheduled = platform_props.scheduled_by_period(book)
    assert recognised == scheduled, {
        period: (recognised.get(period, 0), scheduled.get(period, 0))
        for period in sorted(set(recognised) | set(scheduled))
        if recognised.get(period, 0) != scheduled.get(period, 0)
    }
