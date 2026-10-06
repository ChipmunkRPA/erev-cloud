"""Stage 04 ``noncash_received_cum``: the carrying amount of noncash receipts per contract and
period (ENGINE_SPEC S04-R-18; ENGINE_SPEC_B Table 14-A row "JET-17 unconditional; receipt"; 04
§16.3 ``PAYMENT_RECEIVED`` rev 1.2: with ``form = NONCASH``, ``amount`` is the carrying amount of
the units received; POLICIES JET-17, CHK-135; lane L5-5).

The world is CHK-135 (FASB Example 31): 5,200 customer shares at 10.00 for 52 weekly services, week
1 shares received on 10 January 2026, and one cash receipt that must not count. Stages 01 to 04 run
for real. No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

from erev_engine import ENGINE_VERSION
from erev_engine.bundle import InputBundle, NoncashInput, TemplateInput
from erev_engine.enums import BookCode
from erev_engine.stages import (
    s01_canonicalize,
    s02_contract_identification,
    s03_pob_builder,
    s04_transaction_price,
)
from erev_engine.stages.state import BookContext, PolicyResolver, Target
from erev_engine.trace import TraceBuilder, reevaluate
from support import bundles

CONTRACT = "C-EX31"
ENTITY = bundles.ENTITY_CODE
SUBJECT = f"{CONTRACT}@{ENTITY}"
INCEPTION = date(2026, 1, 1)


def _template() -> TemplateInput:
    return TemplateInput(
        template_code="TPL-UNITS",
        version_key="TPL-UNITS@v1",
        version_no=1,
        content_sha256="0" * 64,
        obligation_kind="STANDARD",
        distinctness="distinct",
        series_increment_unit=None,
        satisfaction_pattern="POINT_IN_TIME",
        over_time_criterion="NOT_APPLICABLE",
        recognition_method="UNITS_DELIVERED",
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
        effective_from=date(2025, 1, 1),
        effective_to=None,
    )


def _world() -> InputBundle:
    header = dataclasses.replace(
        bundles.contract(CONTRACT, inception=INCEPTION),
        noncash_consideration=(
            NoncashInput(
                units=Decimal("5200"),
                fair_value_per_unit=Decimal("10.00"),
                measurement_date=INCEPTION,
                variability="FORM",
                asset_type="SHARES",
            ),
        ),
    )
    line = bundles.booking_line(
        "L1-WEEKS",
        product_code="WEEKLY-SVC",
        quantity="52",
        total_price="0.00",
        end=date(2026, 12, 30),
    )
    keys = ["L1-WEEKS"]
    shares = {
        "receipt_reference": "SHARES-W01",
        "amount": Decimal("1000.00"),
        "receipt_date": date(2026, 1, 10),
        "form": "NONCASH",
        "units_received": Decimal("100"),
        "asset_type": "SHARES",
    }
    cash = {
        "receipt_reference": "CASH-1",
        "amount": Decimal("5.00"),
        "receipt_date": date(2026, 2, 3),
    }
    week = {"obligation_key": "L1-WEEKS", "quantity": Decimal("1"), "trigger": "DELIVERY"}
    events = (
        bundles.event(
            CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": [line]}, obligation_keys=keys
        ),
        bundles.event(CONTRACT, 2, "CONTRACT_ACTIVATED", INCEPTION, {}),
        bundles.event(
            CONTRACT, 3, "DELIVERY_RECORDED", date(2026, 1, 7), week, obligation_keys=keys
        ),
        bundles.event(CONTRACT, 4, "PAYMENT_RECEIVED", date(2026, 1, 10), shares),
        bundles.event(CONTRACT, 5, "PAYMENT_RECEIVED", date(2026, 2, 3), cash),
    )
    calendar = bundles.entity(months=3)
    products = (bundles.product("WEEKLY-SVC", template_code="TPL-UNITS", family=None),)
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 2, 3, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(bundles.book("ASC606", entity=calendar),),
        entities=(calendar,),
        group=bundles.group((header,), products=products),
        contracts=(header,),
        events=events,
        ssp_versions=(),
        pob_template_versions=(_template(),),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def test_noncash_received_cum_counts_noncash_receipts_at_carrying_amount() -> None:
    bundle = _world()
    (book,) = bundle.books
    ctx = BookContext(
        book_code=BookCode(book.book_code),
        framework=BookCode(book.book_code),
        currencies=bundle.currencies,
        txn_currency=bundle.group.transaction_currency,
        entities={entity.code: entity for entity in bundle.entities},
        horizon={entity.code: entity.periods[-1].period_key for entity in bundle.entities},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=bundle.trigger,
        tenant_preset=bundle.tenant_preset,
    )
    cb = s01_canonicalize.run(bundle, TraceBuilder(engine_version=ENGINE_VERSION))
    identified = s02_contract_identification.run(
        ctx, cb, TraceBuilder(engine_version=ENGINE_VERSION)
    )
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    priced = s04_transaction_price.run(ctx, s03_pob_builder.run(ctx, identified, tb), tb)
    received: dict[str, Target] = {
        target.period_key: target
        for target in priced.specialist_targets.noncash
        if target.measure == "noncash_received_cum"
    }
    # The cash receipt of 3 February never counts; the carrying amount carries forward.
    assert {key: target.value for key, target in received.items()} == {
        "FY2026-P01": 100_000,
        "FY2026-P02": 100_000,
        "FY2026-P03": 100_000,
    }
    assert received["FY2026-P01"].subject_key == SUBJECT
    trace = tb.build(root_measures={})
    node = next(n for n in trace.nodes if n.id == f"noncash_received_cum:{SUBJECT}:FY2026-P01")
    assert (node.formula_id, node.value) == ("tp.noncash.v1", "1000.00")
    values = reevaluate(trace)
    assert values[node.id] == node.value
