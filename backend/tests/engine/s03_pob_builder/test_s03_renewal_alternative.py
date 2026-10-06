"""S03-R-07 ``RENEWAL_ALTERNATIVE``: the expected renewal line stays an obligation (lane L5-5,
MR-S2-EX51).

POLICIES ALG-05 §2.6.1: under the 606-10-55-45 practical alternative "the contract includes the
expected renewals; the transaction price is the expected consideration over them; allocation
weights are the expected costs per period adjusted for renewal likelihood". S03-R-07: no option
obligation, and the preparer books the expected renewal lines with their expected consideration.
Stage 03 dropped every line whose option record names ``RENEWAL_ALTERNATIVE``, so the renewal
line booked by the preparer vanished, and its billing raised "a billing line names an obligation
absent from the contract" (S10-R-01). The line now keeps its template terms and option record, with
no option SSP. FASB Example 51 cohort: year 1 at 100,000.00, expected renewal year 2 at 90,000.00
(weights 60,000 and 67,500). No database.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

from erev_engine import ENGINE_VERSION, dates
from erev_engine.bundle import (
    ContractInput,
    EventInput,
    InputBundle,
    MaterialRightInput,
    ProductInput,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.enums import BookCode, ObligationKind, RecognitionMethod
from erev_engine.stages import s01_canonicalize, s02_contract_identification, s03_pob_builder
from erev_engine.stages.s03_pob_builder import PobState
from erev_engine.stages.state import BookContext, PolicyResolver
from erev_engine.trace import TraceBuilder
from support import bundles

CONTRACT = "K-01"
INCEPTION = date(2026, 1, 1)
ZERO = "0" * 64


def _template(code: str, kind: str) -> TemplateInput:
    return TemplateInput(
        template_code=code,
        version_key=f"{code}@v1",
        version_no=1,
        content_sha256=ZERO,
        obligation_kind=kind,
        distinctness="distinct",
        series_increment_unit=None,
        satisfaction_pattern="OVER_TIME",
        over_time_criterion="OT_A",
        recognition_method="TIME_ELAPSED",
        ratable_convention="MONTHLY_EVEN",
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
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )


def _entry(product_code: str, point: str) -> SspEntryInput:
    return SspEntryInput(
        entry_key=f"SSP/{product_code}//-/USD",
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
        ranges=(SspRangeInput("NONE", None, None, Decimal(point), None, None, None),),
    )


def _ssp() -> SspVersionInput:
    return SspVersionInput(
        ssp_book_code="SSP-US",
        version_key="SSP-US@v1",
        version_no=1,
        resolution_mode="EFFECTIVE_DATE",
        legacy_version_label=None,
        effective_from_date=date(2025, 1, 1),
        effective_to_date=None,
        status="APPROVED",
        approved_at=datetime(2025, 12, 1, tzinfo=UTC),
        content_sha256=ZERO,
        scope_entity_code=None,
        scope_currency=None,
        scope_channel=None,
        scope_segment=None,
        entries=(_entry("MAINT-Y1", "60000"), _entry("MAINT-Y2", "67500")),
    )


def _option(method: str) -> MaterialRightInput:
    return MaterialRightInput(
        obligation_key="Y2",
        option_type="RENEWAL_OPTION",
        incremental_discount_ratio=None,
        is_discount_available_without_contract=False,
        expected_purchase_amount=None,
        currency="USD",
        ssp_method=method,
        expiry_date=None,
        likelihood_estimate_key=None,
        is_legacy_quantity_ssp_dollars=False,
    )


def _bundle(header: ContractInput) -> InputBundle:
    calendar = bundles.entity(start=INCEPTION, months=24)
    lines = [
        bundles.booking_line(
            "Y1",
            product_code="MAINT-Y1",
            total_price="100000.00",
            start=INCEPTION,
            end=date(2026, 12, 31),
        ),
        bundles.booking_line(
            "Y2",
            product_code="MAINT-Y2",
            total_price="90000.00",
            start=date(2027, 1, 1),
            end=date(2027, 12, 31),
        ),
    ]
    booked: EventInput = bundles.event(
        CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": lines}, obligation_keys=["Y1", "Y2"]
    )
    products: tuple[ProductInput, ...] = (
        bundles.product("MAINT-Y1", template_code="TPL-RATABLE", family=None),
        bundles.product("MAINT-Y2", template_code="TPL-RENEWAL", family=None),
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(bundles.book("ASC606", entity=calendar),),
        entities=(calendar,),
        group=bundles.group((header,), products=products),
        contracts=(header,),
        events=(booked,),
        ssp_versions=(_ssp(),),
        pob_template_versions=(
            _template("TPL-RATABLE", "STANDARD"),
            _template("TPL-RENEWAL", "MATERIAL_RIGHT"),
        ),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def _context(value: InputBundle) -> BookContext:
    book_input = value.books[0]
    horizon = {}
    for entity in value.entities:
        postable = [
            p for p in entity.periods if dates.period_state(p, "ASC606") in dates.POSTABLE_STATES
        ]
        horizon[entity.code] = postable[-1].period_key
    return BookContext(
        book_code=BookCode.ASC606,
        framework=BookCode.ASC606,
        currencies=value.currencies,
        txn_currency=value.group.transaction_currency,
        entities={entity.code: entity for entity in value.entities},
        horizon=horizon,
        policies=PolicyResolver(book_input.policies),
        mapping=book_input.account_mapping,
        trigger=value.trigger,
        tenant_preset=value.tenant_preset,
    )


def _fold(value: InputBundle) -> PobState:
    cb = s01_canonicalize.run(value, TraceBuilder(engine_version=ENGINE_VERSION))
    ctx = _context(value)
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    return s03_pob_builder.run(ctx, identified, TraceBuilder(engine_version=ENGINE_VERSION))


def _header(*options: MaterialRightInput) -> ContractInput:
    return dataclasses.replace(
        bundles.contract(CONTRACT, inception=INCEPTION), material_rights=options
    )


def test_renewal_alternative_keeps_the_expected_renewal_line() -> None:
    st = _fold(_bundle(_header(_option("RENEWAL_ALTERNATIVE"))))
    assert [ob.obligation_key for ob in st.obligations] == ["Y1", "Y2"]
    renewal = next(ob for ob in st.obligations if ob.obligation_key == "Y2")
    assert renewal.obligation_kind == ObligationKind.MATERIAL_RIGHT
    assert renewal.material_right is not None
    assert renewal.material_right.ssp_method == "RENEWAL_ALTERNATIVE"
    # No option SSP: the weight is the line's own SSP entry (expected costs, 67,500).
    assert renewal.option_ssp is None
    # The template terms stay: time elapsed over the renewal year.
    assert renewal.recognition_method == RecognitionMethod.TIME_ELAPSED


def test_a_material_right_line_without_an_option_record_is_unchanged() -> None:
    st = _fold(_bundle(_header()))
    assert [ob.obligation_key for ob in st.obligations] == ["Y1", "Y2"]
    renewal = next(ob for ob in st.obligations if ob.obligation_key == "Y2")
    assert (renewal.material_right, renewal.option_ssp) == (None, None)
