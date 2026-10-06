"""Engine bundles (dev-guide §7; ENGINE_SPEC §0.4, §0.5, CV-25, CV-26; EKC-6)."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from types import ModuleType

import pytest
from erev_engine import ENGINE_VERSION, bundle, guards, rules
from erev_engine.bundle import (
    VC_DECREASE_TYPES,
    AccountMappingInput,
    BookInput,
    BookOutput,
    ContractInput,
    ContractVersionOut,
    Diagnostic,
    EntityInput,
    EstimateVersionInput,
    EventInput,
    GroupInput,
    InputBundle,
    IntentLine,
    MappingRuleInput,
    ObligationVersionOut,
    OutputBundle,
    PayableInput,
    PaymentPointInput,
    PeriodInput,
    PortfolioInput,
    PostedAmountInput,
    PostingIntent,
    ProductInput,
    ProposalOut,
    ResolvedPolicyInput,
    RuleInput,
    RuleSetInput,
    TimeTrigger,
)
from erev_engine.canonical import canonical_bytes, sha256_hex
from erev_engine.currencies import ISO_4217
from erev_engine.dates import month_end, period_of
from erev_engine.enums import ScheduleKind, ScheduleLineType
from erev_engine.stages import state
from erev_engine.stages.state import ScheduleLineOut
from erev_engine.trace import Trace

KNOWN_AT = datetime(2026, 1, 31, 23, 0, tzinfo=UTC)


def _lines(price: str) -> Mapping[str, object]:
    return {
        "lines": [
            {"obligation_key": "POB-01", "quantity": Decimal("1"), "total_price": Decimal(price)}
        ]
    }


def _bundle(payload: Mapping[str, object] | None = None) -> InputBundle:
    policies = (
        ResolvedPolicyInput("billing.posting", "GROUP", "", "ERP", "DEFAULT", "framework", "K"),
    )
    mapping = AccountMappingInput(
        "MAP@v1",
        "0" * 64,
        (MappingRuleInput("REVENUE", None, None, None, None, None, "4000", {}, 0, 0),),
    )
    periods = tuple(
        PeriodInput(
            period_key=f"FY2026-P{n:02d}",
            fiscal_year=2026,
            period_no=n,
            start_date=date(2026, n, 1),
            end_date=month_end(date(2026, n, 1)),
            states=(("ASC606", "open"),),
        )
        for n in range(1, 13)
    )
    product = ProductInput(
        code="SKU-1",
        sku_number=None,
        product_family="SaaS",
        revenue_category=None,
        default_template_code="TPL-RATABLE",
        principal_agent="PRINCIPAL",
        distinctness_default="distinct",
        unit_of_measure="EA",
        is_bundle=False,
        policy_values={},
        assurance_cost_per_unit=None,
        components=(),
    )
    contract = ContractInput(
        external_id="K-01",
        customer_code="C-1",
        related_party_group=None,
        contracting_entity_code="US01",
        transaction_currency="USD",
        inception_date=date(2026, 1, 1),
        signature_date=None,
        document_ref="DOC-1",
        termination_party=None,
        termination_has_penalty=None,
        termination_notice_days=None,
        has_commercial_substance=True,
        region="EMEA",
        channel=None,
        contract_type=None,
        renewal_of_contract_key=None,
        judgements=(),
        material_rights=(),
        modifications=(),
        noncash_consideration=(),
        consideration_payable=(
            PayableInput(Decimal("1500000.00"), date(2026, 1, 1), (), None, None, False),
        ),
        payment_schedule=(PaymentPointInput(date(2026, 2, 1), Decimal("18871.00")),),
        scope_605_35=False,
    )
    event = EventInput(
        event_key="K-01/EV-000001",
        contract_key="K-01",
        stream_version=1,
        event_type="CONTRACT_BOOKED",
        schema_version=1,
        effective_date=date(2026, 1, 1),
        recorded_at=datetime(2026, 1, 2, 9, 0, tzinfo=UTC),
        record_seq=1,
        origin="API",
        is_manual=False,
        obligation_keys=("POB-01",),
        payload=payload if payload is not None else _lines("1200.00"),
        payload_sha256="0" * 64,
        idempotency_key=None,
        supersedes_event_key=None,
        modification_key=None,
        estimate_version_key=None,
        manual_adjustment_key=None,
    )
    rule_set = RuleSetInput(
        rule_set_code="POB-RULES",
        kind="POB_ASSIGNMENT",
        version_key="POB-RULES@v1",
        version_no=1,
        content_sha256="0" * 64,
        effective_from=date(2026, 1, 1),
        effective_to=None,
        rules=(
            RuleInput(
                "R1",
                0,
                1,
                ({"field": "product.code", "op": "eq", "value": "SKU-1"},),
                {"pob_template_code": "TPL-RATABLE"},
            ),
        ),
    )
    return InputBundle(
        format_version=1,
        engine_version=ENGINE_VERSION,
        trigger="COMMAND",
        known_at=KNOWN_AT,
        tenant_preset="DEFAULT",
        currencies={"USD": ISO_4217["USD"]},
        books=(BookInput("ASC606", True, ("US01",), policies, mapping),),
        entities=(EntityInput("US01", "USD", "America/New_York", "MONTHLY", periods),),
        group=GroupInput(
            group_key="CG-1",
            transaction_currency="USD",
            inception_date=date(2026, 1, 1),
            member_contract_keys=("K-01",),
            criterion=None,
            previous_stream_heads=(),
            products=(product,),
            portfolios=(PortfolioInput("PF-1", ("K-01",)),),
        ),
        contracts=(contract,),
        events=(event,),
        ssp_versions=(),
        pob_template_versions=(),
        rule_set_versions=(rule_set,),
        estimate_versions=(),
        fx_rates=(),
        posted=(),
    )


def _output(input_sha256: str) -> OutputBundle:
    node = "revenue_cum:K-01/POB-01:FY2026-P01"
    line = IntentLine(
        line_key="1" * 64,
        side="D",
        account_role="CONTRACT_LIABILITY",
        clearing_purpose=None,
        counterparty_entity=None,
        account_code="2400",
        amount_txn=10000,
        amount_functional=10000,
        txn_currency="USD",
        functional_currency="USD",
        dimensions={"contract": "CG-1"},
        source_event_key=None,
        trace_node_id=node,
    )
    book = BookOutput(
        book_code="ASC606",
        contract_version=ContractVersionOut("CG-1", {"status": "ACTIVE"}, {}),
        status_in_book=(("K-01", "ACTIVE"),),
        obligation_versions=(
            ObligationVersionOut("K-01/POB-01", {"revenue_cum": "100.00"}, {"revenue_cum": node}),
        ),
        balances=(),
        schedules=(
            ScheduleLineOut(
                schedule_kind=ScheduleKind.REVENUE,
                subject_type="obligation",
                subject_key="K-01/POB-01",
                entity="US01",
                period_key="FY2026-P01",
                line_type=ScheduleLineType.NORMAL,
                amount=10000,
                cumulative_amount=10000,
                cumulative_exact=Fraction(100),
                quantity=None,
                is_released_at_close=True,
                trace_node_id=node,
            ),
        ),
        cost_asset_versions=(),
        loss_provision_versions=(),
        fx_layer_movements=(),
        posting_intents=(
            PostingIntent(
                entry_key="2" * 64,
                book_code="ASC606",
                entity="US01",
                posting_period_key="FY2026-P01",
                origin_period_key=None,
                entry_kind="REVENUE_RECOGNITION",
                posting_class="EVENT",
                subject_key="K-01/POB-01",
                reason_code=None,
                lines=(line, dataclasses.replace(line, side="C", account_role="REVENUE")),
            ),
        ),
        proposals=(
            ProposalOut(
                "MODIFICATION_TREATMENT", "K-01", "PROSPECTIVE", {"POB-01": "PROSPECTIVE"}, {}
            ),
        ),
        time_triggers=(TimeTrigger("MATERIAL_RIGHT_EXPIRY", date(2026, 12, 31), "K-01/POB-02"),),
        trace=Trace(format_version=1, engine_version=ENGINE_VERSION, nodes=(), root_measures={}),
    )
    diagnostic = Diagnostic("LATE_EVENT", "WARNING", "ASC606", "K-01/POB-01", "K-01/EV-000002", {})
    return OutputBundle(ENGINE_VERSION, input_sha256, (book,), (diagnostic,))


def test_input_sha256_excludes_known_at() -> None:
    first = _bundle()
    later = dataclasses.replace(first, known_at=datetime(2026, 3, 1, tzinfo=UTC))
    assert later.sha256() == first.sha256()
    assert len(first.sha256()) == 64
    assert _bundle().sha256() == first.sha256()
    changed = _bundle(_lines("1300.00"))
    assert changed.sha256() != first.sha256()
    guards.no_floats(first)
    # The bundle inputs satisfy the EKC-4 and EKC-5 read-only protocols.
    assert period_of(first.entities[0], date(2026, 2, 15)).period_key == "FY2026-P02"
    chosen = rules.match(first.rule_set_versions[0], {"product.code": "SKU-1"})
    assert chosen is not None and chosen.outputs == {"pob_template_code": "TPL-RATABLE"}


def test_output_sha256_covers_input_sha256() -> None:
    output = _output("a" * 64)
    assert output.sha256() == _output("a" * 64).sha256()
    assert _output("b" * 64).sha256() != output.sha256()
    guards.no_floats(output)
    with pytest.raises(TypeError):
        dataclasses.replace(output, diagnostics=(object(),)).sha256()  # type: ignore[arg-type]


BUNDLE_CLASSES = {
    "InputBundle",
    "BookInput",
    "ResolvedPolicyInput",
    "AccountMappingInput",
    "MappingRuleInput",
    "EntityInput",
    "PeriodInput",
    "GroupInput",
    "ProductInput",
    "BundleComponentInput",
    "PortfolioInput",
    "ContractInput",
    "JudgementInput",
    "MaterialRightInput",
    "ModificationInput",
    "NoncashInput",
    "PayableInput",
    "PaymentPointInput",
    "EventInput",
    "SspVersionInput",
    "SspEntryInput",
    "SspRangeInput",
    "TemplateInput",
    "RuleSetInput",
    "RuleInput",
    "EstimateVersionInput",
    "FxRateInput",
    "PostedAmountInput",
    "OutputBundle",
    "BookOutput",
    "Diagnostic",
    "ContractVersionOut",
    "ObligationVersionOut",
    "BalanceOut",
    "CostAssetVersionOut",
    "LossProvisionOut",
    "FxLayerMovementOut",
    "PostingIntent",
    "IntentLine",
    "ProposalOut",
    "TimeTrigger",
}
STATE_CLASSES = {
    "BookContext",
    "PolicyResolver",
    "CanonicalBundle",
    "EventView",
    "QuantityLedger",
    "LedgerPoint",
    "Quota",
    "AllocationSegment",
    "ObligationState",
    "AllocatedState",
    "Target",
    "ScheduleLineOut",
    "Finding",
}


@pytest.mark.parametrize(
    ("module", "required"),
    [(bundle, BUNDLE_CLASSES), (state, STATE_CLASSES)],
    ids=["bundle", "state"],
)
def test_dataclasses_frozen_with_slots(module: ModuleType, required: set[str]) -> None:
    classes = {
        name: value
        for name, value in vars(module).items()
        if isinstance(value, type)
        and dataclasses.is_dataclass(value)
        and value.__module__ == module.__name__
    }
    assert required <= set(classes), sorted(required - set(classes))
    for name, cls in classes.items():
        assert cls.__dataclass_params__.frozen, name  # type: ignore[attr-defined]
        assert "__slots__" in vars(cls), name
    assert set(module.__all__) >= set(classes)


# --- ENC-VC-direction: EstimateVersionInput.direction (04 T-CON-12 B3-D16; B3-DG-17) -------------


def _version(kind: str, vc_type: str | None, direction: str | None) -> EstimateVersionInput:
    return EstimateVersionInput(
        estimate_key="K-01/E",
        estimate_kind=kind,
        element_code="E",
        method="ENTERED_AMOUNT",
        vc_element_type=vc_type,
        allocation_target="CONTRACT",
        target_obligation_keys=(),
        obligation_key=None,
        version_key="K-01/E@v1",
        version_no=1,
        status="APPROVED",
        effective_date=date(2026, 1, 1),
        scenarios=(),
        parameters={},
        unconstrained_amount=None,
        most_conservative_amount=None,
        constrained_amount=Decimal("1.00"),
        rate=None,
        expected_total_amount=None,
        expected_quantity=None,
        amortization_months=None,
        currency="USD",
        supersedes_version_key=None,
        judgement_key=None,
        content_sha256="0" * 64,
        direction=direction,
    )


def test_enc_vc_direction_resolved_direction_defaults_and_checks() -> None:
    """Absent: the B3-DG-17 default (the nine T-03 types and IMPLICIT_PRICE_CONCESSION reduce,
    everything else increases). Explicit: honoured, within the T-CON-12 checks."""
    assert VC_DECREASE_TYPES == {
        "IMPLICIT_PRICE_CONCESSION",
        "REBATE",
        "VOLUME_TIER",
        "PRICE_PROTECTION",
        "SLA_CREDIT",
        "DISCOUNT",
        "RETURN",
        "REFUND",
        "PENALTY",
    }
    for vc_type in VC_DECREASE_TYPES:
        assert _version("VARIABLE_CONSIDERATION", vc_type, None).resolved_direction() == "DECREASE"
    for vc_type in (
        "BONUS",
        "PERFORMANCE_INCENTIVE",
        "MILESTONE",
        "USAGE",
        "ROYALTY",
        "CLAIM",
        None,
    ):
        assert _version("VARIABLE_CONSIDERATION", vc_type, None).resolved_direction() == "INCREASE"
    assert _version("IMPLICIT_PRICE_CONCESSION", None, None).resolved_direction() == "DECREASE"
    for kind in ("EAC", "RETURN_RATE", "BREAKAGE", "RENEWAL_EXPECTATION"):
        assert _version(kind, None, None).resolved_direction() == "INCREASE"
        assert _version(kind, None, "INCREASE").resolved_direction() == "INCREASE"
        with pytest.raises(ValueError, match="is INCREASE"):
            _version(kind, None, "DECREASE").resolved_direction()
    assert (
        _version("VARIABLE_CONSIDERATION", "VOLUME_TIER", "INCREASE").resolved_direction()
        == "INCREASE"
    )
    assert (
        _version("VARIABLE_CONSIDERATION", "BONUS", "DECREASE").resolved_direction() == "DECREASE"
    )
    assert (
        _version("IMPLICIT_PRICE_CONCESSION", None, "DECREASE").resolved_direction() == "DECREASE"
    )
    with pytest.raises(ValueError, match="IMPLICIT_PRICE_CONCESSION element is DECREASE"):
        _version("IMPLICIT_PRICE_CONCESSION", None, "INCREASE").resolved_direction()
    with pytest.raises(ValueError, match="not INCREASE or DECREASE"):
        _version("VARIABLE_CONSIDERATION", "BONUS", "increase").resolved_direction()


def test_enc_vc_direction_hash_view_keeps_historical_hashes() -> None:
    """CV-25 through ``EstimateVersionInput.hash_view`` (D-93 (5)): the member enters the input
    hash only when it differs from the B3-DG-17 default. An absent member and an explicit
    default-equal member hash identically, and identically to the pre-member canonical form (the
    dataclass without the field) — the canonicalisation of pre-0.3.0 bundles; a non-default
    explicit direction is a different input and hashes differently. The version stamp is outside
    this test: every actual 0.3.0 input hash differs from its 0.2.0 one (``engine_version``)."""
    absent = _version("VARIABLE_CONSIDERATION", "VOLUME_TIER", None)
    default_explicit = dataclasses.replace(absent, direction="DECREASE")
    non_default = dataclasses.replace(absent, direction="INCREASE")
    legacy_form = {
        item.name: getattr(absent, item.name)
        for item in dataclasses.fields(absent)
        if item.name != "direction"
    }
    assert canonical_bytes(absent.hash_view()) == canonical_bytes(legacy_form)
    assert canonical_bytes(default_explicit.hash_view()) == canonical_bytes(legacy_form)
    assert "direction" not in absent.hash_view() and "direction" not in default_explicit.hash_view()
    assert non_default.hash_view()["direction"] == "INCREASE"
    assert sha256_hex(non_default.hash_view()) != sha256_hex(legacy_form)
    # The raw dataclass still encodes the field (DG-KRN-CAN-13); only the CV-25 view normalises.
    assert b'"direction":null' in canonical_bytes(absent)
    base = _bundle()
    with_absent = dataclasses.replace(base, estimate_versions=(absent,))
    with_default = dataclasses.replace(base, estimate_versions=(default_explicit,))
    with_increase = dataclasses.replace(base, estimate_versions=(non_default,))
    assert with_absent.sha256() == with_default.sha256()
    assert with_increase.sha256() != with_absent.sha256()
    bonus_default = _version("VARIABLE_CONSIDERATION", "BONUS", "INCREASE")  # default for BONUS
    bonus_decrease = dataclasses.replace(bonus_default, direction="DECREASE")
    assert "direction" not in bonus_default.hash_view()
    assert bonus_decrease.hash_view()["direction"] == "DECREASE"


def test_posted_reason_code_hash_view_keeps_historical_hashes() -> None:
    """CV-25 through ``PostedAmountInput.hash_view`` (S14-R-27; ENGINE_SPEC §0.4 rev 1.16): the
    ``reason_code`` member enters the input hash only when set, so a bundle whose posted lines
    carry no reason hashes as the pre-member form did (the D-93 (5) ``direction`` precedent); a
    tagged line is a different input. The raw dataclass still encodes the field (DG-KRN-CAN-13)."""
    untagged = PostedAmountInput(
        "ASC606", "US01", "K-01/EV-000004", "CONTRACT_COST_CAPITALIZATION", "COST_TO_OBTAIN_ASSET",
        None, None, "FY2026-P01", None, "EVENT", "USD", "USD", 1000000, 1000000,
    )  # fmt: skip
    tagged = dataclasses.replace(
        untagged, amount_txn=-200000, amount_functional=-200000, reason_code="CLAWBACK"
    )
    # The pre-member form: the members of §0.4 before ``reason_code`` (rev 1.16) and ``rate_refs``
    # (rev 1.43) existed.
    legacy_form = {
        item.name: getattr(untagged, item.name)
        for item in dataclasses.fields(untagged)
        if item.name not in ("reason_code", "rate_refs")
    }
    assert canonical_bytes(untagged.hash_view()) == canonical_bytes(legacy_form)
    assert "reason_code" not in untagged.hash_view()
    assert tagged.hash_view()["reason_code"] == "CLAWBACK"
    assert b'"reason_code":null' in canonical_bytes(untagged)
    base = _bundle()
    with_untagged = dataclasses.replace(base, posted=(untagged,))
    with_tagged = dataclasses.replace(base, posted=(untagged, tagged))
    assert with_untagged.sha256() != base.sha256()
    assert with_tagged.sha256() != with_untagged.sha256()
    assert sha256_hex(untagged.hash_view()) == sha256_hex(legacy_form)


def test_posted_rate_refs_hash_view_keeps_historical_hashes() -> None:
    """CV-25 through ``PostedAmountInput.hash_view`` (S14-R-28; ENGINE_SPEC §0.4 rev 1.43): the
    ``rate_refs`` member enters the input hash only when the posted lines carry a rate, so a
    single-currency posted amount hashes as the pre-member form did (the ``reason_code``
    precedent), and the references of a foreign-currency amount are part of the input. The raw
    dataclass still encodes the field (DG-KRN-CAN-13)."""
    plain = PostedAmountInput(
        "ASC606", "US01", "K-01/POB-01", "REVENUE_RECOGNITION", "CONTRACT_LIABILITY",
        None, None, "FY2026-P01", None, "EVENT", "USD", "GBP", 100000, 81000,
    )  # fmt: skip
    stamped = dataclasses.replace(plain, rate_refs=(("USDGBP-AVERAGE-FY2026-P01", "FX@v1"),))
    legacy_form = {
        item.name: getattr(plain, item.name)
        for item in dataclasses.fields(plain)
        if item.name not in ("reason_code", "rate_refs")
    }
    assert canonical_bytes(plain.hash_view()) == canonical_bytes(legacy_form)
    assert "rate_refs" not in plain.hash_view()
    assert stamped.hash_view()["rate_refs"] == (("USDGBP-AVERAGE-FY2026-P01", "FX@v1"),)
    assert b'"rate_refs":[]' in canonical_bytes(plain)
    base = _bundle()
    with_plain = dataclasses.replace(base, posted=(plain,))
    with_stamped = dataclasses.replace(base, posted=(stamped,))
    assert with_stamped.sha256() != with_plain.sha256()
    assert with_plain.sha256() != base.sha256()
