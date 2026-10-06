"""CTL-012: ``compute`` fails closed when an allocation or journal identity breaks (dev-guide
DG-ENG-05; ENGINE_SPEC S04-R-02; 04 DB-17 V1, DB-17; D-16; BUILD_SPEC END-9).

Each case wraps one stage entry of ``erev_engine.stages.STAGES`` so that its output breaks exactly
one identity of the kit world (K-12: one point-in-time kit for 1,000.00, delivered in January).
``compute`` must raise ``EngineError("ENGINE_INVARIANT_VIOLATED")`` naming that identity. No
database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from types import MappingProxyType

import erev_engine
import pytest
from erev_engine import (
    ENGINE_VERSION,
    IDENTITY_BASIS,
    IDENTITY_ENTRY,
    IDENTITY_OBLIGATION,
    IDENTITY_PRICE,
    compute,
)
from erev_engine.bundle import (
    InputBundle,
    SspEntryInput,
    SspRangeInput,
    SspVersionInput,
    TemplateInput,
)
from erev_engine.errors import EngineError
from erev_engine.stages import StageSpec
from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.s14_posting import PostingState
from erev_engine.stages.state import Quota1
from support import bundles

CONTRACT = "K-12"
INCEPTION = date(2026, 1, 1)
ZERO_SHA = "0" * 64
TEMPLATE = TemplateInput(
    template_code="TPL-PIT",
    version_key="TPL-PIT@v1",
    version_no=1,
    content_sha256=ZERO_SHA,
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


def kit_world() -> InputBundle:
    calendar = bundles.entity(months=12)
    header = bundles.contract(CONTRACT, inception=INCEPTION)
    line = bundles.booking_line(
        "POB-01", product_code="KIT", quantity="1", total_price="1000.00", end=INCEPTION
    )
    delivery = {"obligation_key": "POB-01", "quantity": Decimal("1"), "trigger": "CONTROL_TRANSFER"}
    booked = bundles.event(
        CONTRACT, 1, "CONTRACT_BOOKED", INCEPTION, {"lines": [line]}, obligation_keys=["POB-01"]
    )
    delivered = bundles.event(
        CONTRACT, 3, "DELIVERY_RECORDED", date(2026, 1, 20), delivery, obligation_keys=["POB-01"]
    )
    events = (
        booked,
        bundles.event(CONTRACT, 2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}}),
        delivered,
    )
    point = SspEntryInput(
        entry_key="SSP-US@v1/KIT//-/USD",
        product_code="KIT",
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
        ranges=(SspRangeInput("NONE", None, None, Decimal("1000.00"), None, None, None),),
    )
    version = SspVersionInput(
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
        entries=(point,),
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=datetime(2026, 12, 31, 23, tzinfo=UTC),
        tenant_preset="DEFAULT",
        currencies=bundles.currencies("USD"),
        books=(bundles.book(entity=calendar),),
        entities=(calendar,),
        group=bundles.group(
            (header,),
            group_key=f"CG-{CONTRACT}",
            products=(bundles.product("KIT", template_code="TPL-PIT", family=None),),
        ),
        contracts=(header,),
        events=events,
        ssp_versions=(version,),
        pob_template_versions=(TEMPLATE,),
        rule_set_versions=(),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def wrap(stage: str, change: Callable[[object], object]) -> tuple[StageSpec, ...]:
    """``STAGES`` with the entry of ``stage`` changing its output."""

    def patched(spec: StageSpec) -> StageSpec:
        entry = spec.entry

        def run(*args: object, **bound: object) -> object:
            return change(entry(*args, **bound))

        return dataclasses.replace(spec, entry=run)

    return tuple(
        patched(spec) if spec.stage == stage else spec for spec in erev_engine.stages.STAGES
    )


def tp_change(**changes: int) -> Callable[[object], object]:
    """Stage 14 output whose latest build-up changes members by minor units (bundled state)."""

    def change(state: object) -> object:
        assert isinstance(state, PostingState)
        allocated = state.allocated
        latest = allocated.tp_history[-1]
        moved = {
            name: Quota1(getattr(latest, name).exact, getattr(latest, name).posted + delta)
            for name, delta in changes.items()
        }
        history = (*allocated.tp_history[:-1], dataclasses.replace(latest, **moved))
        return dataclasses.replace(
            state, allocated=dataclasses.replace(allocated, tp_history=history)
        )

    return change


def scheduled_plus_one(state: object) -> object:
    assert isinstance(state, RecognitionState)
    measures = dict(state.obligation_measures)
    subject = f"{CONTRACT}/POB-01"
    measures[subject] = dataclasses.replace(
        measures[subject], scheduled_amount=measures[subject].scheduled_amount + 1
    )
    return dataclasses.replace(state, obligation_measures=MappingProxyType(measures))


def unbalanced(state: object) -> object:
    assert isinstance(state, PostingState)
    intent = state.posting_intents[0]
    first = intent.lines[0]
    lines = (dataclasses.replace(first, amount_txn=first.amount_txn + 1), *intent.lines[1:])
    return dataclasses.replace(
        state,
        posting_intents=(dataclasses.replace(intent, lines=lines), *state.posting_intents[1:]),
    )


@pytest.mark.control("CTL-012")
def test_ctl_012_compute_identities_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    value = kit_world()
    output = compute(value)  # the unbroken world computes
    (book,) = output.books
    assert [c.columns["allocated_amount"] for c in book.obligation_versions] == [100000]
    assert len(book.posting_intents) == 1
    cases = [
        (wrap("14", tp_change(allocation_basis=1)), IDENTITY_BASIS),
        (wrap("14", tp_change(total=1)), IDENTITY_PRICE),
        (wrap("09", scheduled_plus_one), IDENTITY_OBLIGATION),
        (wrap("14", unbalanced), IDENTITY_ENTRY),
    ]
    for stages, identity in cases:
        monkeypatch.setattr(erev_engine.stages, "STAGES", stages)
        with pytest.raises(EngineError) as raised:
            compute(value)
        assert raised.value.code == "ENGINE_INVARIANT_VIOLATED", identity
        assert raised.value.detail["identity"] == identity
        assert raised.value.detail["book_code"] == "ASC606"
        assert raised.value.detail["expected"] != raised.value.detail["actual"]
