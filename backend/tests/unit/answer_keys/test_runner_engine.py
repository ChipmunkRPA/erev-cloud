"""Engine runner: checkpoint bundle assembly (docs/dev-guide.md §9.5.8 DG-AK-40, DG-AK-44;
ENGINE_SPEC §0.4; BUILD_SPEC EKC-11)."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from fractions import Fraction
from typing import cast

import erev_engine
import pytest
from erev_api.db.tables.reference import product as product_table
from erev_api.enums import PrincipalAgent
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_api.schemas.products import ProductIn
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import (
    BookOutput,
    ContractVersionOut,
    InputBundle,
    ObligationVersionOut,
    OutputBundle,
)
from erev_engine.canonical import canonical_bytes
from erev_engine.errors import EngineError
from erev_engine.stages.state import Finding, PolicyResolver
from erev_engine.trace import SourceRef, Trace, TraceNode, reevaluate
from sqlalchemy.schema import DefaultClause
from support.answer_keys.loader import ANSWER_KEY_ROOT, AnswerKeyError, LoadedKey, load
from support.answer_keys.runners import (
    CheckpointBundles,
    CheckpointMismatchError,
    RunResult,
    _Assembler,
    _build_checkpoint_bundles,
    _build_step_bundles,
    _CheckpointComparison,
    _largest_remainder,
    _render_grain,
    _starts_no_segment,
    assert_checkpoints,
    run_engine,
)
from support.bundles import policy_value

REJECTED = "ALC-CHK-032-S4-EX34-CASEC-REJECTED"


def _load(key_id: str) -> LoadedKey:
    family = key_id.split("-", 1)[0].lower()
    return load(ANSWER_KEY_ROOT / family / f"{key_id}.yaml")


def _bundle_of(checkpoint: CheckpointBundles, contract_key: str) -> InputBundle:
    matches = [b for b in checkpoint.bundles if contract_key in b.group.member_contract_keys]
    assert len(matches) == 1
    return matches[0]


def test_build_bundles_rnd_chk_001() -> None:
    loaded = _load("RND-CHK-001")
    checkpoints = _build_checkpoint_bundles(loaded)
    assert [c.name for c in checkpoints] == ["after-activation"]
    assert [len(c.bundles) for c in checkpoints] == [1]
    bundle = checkpoints[0].bundles[0]

    # §9.5.5 default record times: local noon of 2026-01-01 in America/New_York, then + 1 second.
    assert bundle.known_at == datetime(2026, 1, 1, 17, 0, 1, tzinfo=UTC)
    assert checkpoints[0].known_at == bundle.known_at
    assert [(e.record_seq, e.event_type) for e in bundle.events] == [
        (1, "CONTRACT_BOOKED"),
        (2, "CONTRACT_ACTIVATED"),
    ]
    assert [e.event_key for e in bundle.events] == ["C-RND-1/EV-000001", "C-RND-1/EV-000002"]
    assert [e.recorded_at for e in bundle.events] == [
        datetime(2026, 1, 1, 17, 0, 0, tzinfo=UTC),
        datetime(2026, 1, 1, 17, 0, 1, tzinfo=UTC),
    ]

    assert list(bundle.currencies) == ["USD"]
    (entity,) = bundle.entities
    assert entity.code == "US01"
    assert [p.period_key for p in entity.periods] == [f"FY2026-P{n:02d}" for n in range(1, 13)]
    assert {p.states for p in entity.periods} == {(("ASC606", "open"),)}

    assert [c.external_id for c in bundle.contracts] == ["C-RND-1"]
    lines = bundle.events[0].payload["lines"]
    assert isinstance(lines, list)
    assert [(line["obligation_key"], line["total_price"]) for line in lines] == [
        ("POB-001", Decimal("40.00")),
        ("POB-002", Decimal("30.00")),
        ("POB-003", Decimal("30.00")),
    ]
    assert bundle.events[0].obligation_keys == ("POB-001", "POB-002", "POB-003")

    (book,) = bundle.books
    assert (book.book_code, book.is_primary, book.entity_codes) == ("ASC606", True, ("US01",))
    policies = PolicyResolver(book.policies)
    assert policies.value("billing.posting", entity="US01", period="FY2026-P01") == "ERP"
    assert [p.product_code for p in bundle.ssp_versions[0].entries] == [
        "PROD-1",
        "PROD-2",
        "PROD-3",
    ]
    assert [p.code for p in bundle.group.products] == ["PROD-1", "PROD-2", "PROD-3"]

    # DG-AK-44: events apply in (effective_date, seq) order, whatever the seq order.
    first, second = loaded.key.timeline
    backdated = loaded.key.model_copy(
        update={"timeline": (first, second.model_copy(update={"effective_date": "2025-12-31"}))}
    )
    variant = _build_checkpoint_bundles(LoadedKey(backdated, loaded.path, loaded.sha256))
    assert [e.record_seq for e in variant[0].bundles[0].events] == [2, 1]


def test_period_state_items() -> None:
    loaded = _load("LATE-CHK-090-GOLDEN-CONTRACT1-DELIVERY-AFTER-JANUARY-LOCK")
    (checkpoint,) = _build_checkpoint_bundles(loaded)
    bundle = _bundle_of(checkpoint, "CONTRACT-1")
    assert bundle.known_at == datetime(2023, 2, 5, 15, 2, tzinfo=UTC)
    states = {p.period_key: p.states for p in bundle.entities[0].periods}
    assert states == {"FY2023-P01": (("ASC606", "closed"),), "FY2023-P02": (("ASC606", "open"),)}
    assert [e.record_seq for e in bundle.events] == [1, 2, 3, 4, 5, 7, 8, 9]
    resolved = PolicyResolver(bundle.books[0].policies).resolved(
        "billing.posting", entity="ME1", period="FY2023-P02"
    )
    assert (resolved.value, resolved.level) == ("ERP", "T")

    # A checkpoint before the period_state item sees January open.
    earlier = loaded.key.checkpoints[0].model_copy(update={"after_seq": 5})
    key = loaded.key.model_copy(update={"checkpoints": (earlier,)})
    (before,) = _build_checkpoint_bundles(LoadedKey(key, loaded.path, loaded.sha256))
    before_states = {p.period_key: p.states for p in before.bundles[0].entities[0].periods}
    assert before_states["FY2023-P01"] == (("ASC606", "open"),)


@pytest.mark.parametrize("key_id", ["VC-CHK-110", "POB-S2-EX61"])
def test_contract_override_of_period_pinned_code(key_id: str) -> None:
    loaded = _load(key_id)
    (contract,) = loaded.key.contracts
    override = (contract.policy_overrides or ())[0]
    bundle = _bundle_of(_build_checkpoint_bundles(loaded)[0], contract.external_id)
    resolver = PolicyResolver(bundle.books[0].policies)
    # A code FORCED in the book keeps its framework value (POLICIES §1; erev_api.registry.resolve):
    # VC-CHK-110's POL-041 override equals the forced value, so only the level differs (L5-5).
    spec = POLICY_PARAMETERS[override.policy_key]
    ifrs = bundle.books[0].book_code == "IFRS15"
    forced = spec.is_forced_ifrs15 if ifrs else spec.is_forced_asc606
    for period in bundle.entities[0].periods:
        resolved = resolver.resolved(
            override.policy_key, entity=contract.contracting_entity, period=period.period_key
        )
        assert (resolved.value, resolved.level, resolved.pin) == (
            policy_value(override.value),
            "DEFAULT" if forced else "C",
            "P",
        )


def test_members_enter_bundle() -> None:
    sfc = _build_checkpoint_bundles(_load("SFC-CHK-137-S3-EX28-CASEB"))[0]
    (contract,) = sfc.bundles[0].contracts
    assert len(contract.payment_schedule) == 60
    assert {point.amount for point in contract.payment_schedule} == {Decimal("18871.00")}

    cpc = _build_checkpoint_bundles(_load("CPC-CHK-133-S3-EX32"))[0]
    (contract,) = cpc.bundles[0].contracts
    assert [item.amount for item in contract.consideration_payable] == [Decimal("1500000.00")]
    assert contract.consideration_payable[0].committed_purchases == Decimal("15000000.00")

    ret = _build_checkpoint_bundles(_load("RET-CHK-116"))[0]
    codes = {portfolio.code for bundle in ret.bundles for portfolio in bundle.group.portfolios}
    assert codes == {"PF-WIDGET-JAN-2026"}


def test_judgement_questionnaire_enters_outcome() -> None:
    sfc = _build_checkpoint_bundles(_load("SFC-CHK-137-S3-EX28-CASEB"))[0]
    (contract,) = sfc.bundles[0].contracts
    records = [j for j in contract.judgements if j.topic == "SFC_ASSESSMENT"]
    assert len(records) == 1
    assert records[0].outcome == {
        "obligation_key": "",
        "significant": "true",
        "exception_32_17": "NONE",
    }

    rec = _build_checkpoint_bundles(_load("REC-BR-04-BILL-AND-HOLD-CUSTODIAL"))[0]
    (contract,) = rec.bundles[0].contracts
    (record,) = [j for j in contract.judgements if j.topic == "BILL_AND_HOLD"]
    assert record.outcome == {
        "obligation_key": "L1-ROBOTS",
        "reason_substantive": "true",
        "identified_as_customer_product": "true",
        "ready_for_physical_transfer": "true",
        "cannot_use_or_direct_to_another_customer": "true",
    }
    assert record.subject_key == "BR-04/L1-ROBOTS"


def _draft_book(group: str) -> BookOutput:
    """The `activation-refused` book: DRAFT, transaction price 105.00, DG-AK-54 identities met."""
    allocations = {"L1-A": 3000, "L2-B": 3000, "L3-C": 2500, "L4-D": 2000}
    obligations = tuple(
        ObligationVersionOut(
            f"C-EX34/{key}",
            {
                "allocated_amount": amount,
                "revenue_cum": 0,
                "scheduled_amount": 0,
                "awaiting_trigger_amount": amount,
            },
            {},
        )
        for key, amount in allocations.items()
    )
    node = TraceNode(
        id=f"tp_allocation_basis:{group}:-",
        measure="tp_allocation_basis",
        value="105.00",
        currency="USD",
        formula_id="sched.period_difference.v1",
        inputs=(
            SourceRef("source_record", "SRC-0", {"value": "105.00"}),
            SourceRef("source_record", "SRC-1", {"value": "0"}),
        ),
        params={"minor_unit": "2"},
        rounding_residue="0",
        narrative_key="sched.period_difference",
    )
    version = ContractVersionOut(
        group,
        {
            "transaction_price": 10500,
            "consideration_payable_amount": 0,
            "expected_returns_amount": 0,
        },
        {},
    )
    return BookOutput(
        book_code="ASC606",
        contract_version=version,
        status_in_book=(("C-EX34", "DRAFT"),),
        obligation_versions=obligations,
        balances=(),
        schedules=(),
        cost_asset_versions=(),
        loss_provision_versions=(),
        fx_layer_movements=(),
        posting_intents=(),
        proposals=(),
        time_triggers=(),
        trace=Trace(
            format_version=1, engine_version=ENGINE_VERSION, nodes=(node,), root_measures={}
        ),
    )


def test_expect_problem_leaves_state_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded = _load(REJECTED)
    (checkpoint,) = _build_checkpoint_bundles(loaded)
    assert checkpoint.name == "activation-refused"
    (bundle,) = checkpoint.bundles
    assert [(e.record_seq, e.event_type) for e in bundle.events] == [(1, "CONTRACT_BOOKED")]
    (step,) = _build_step_bundles(loaded)
    assert (step.seq, step.expected_code, step.known_at) == (
        2,
        "RESIDUAL_REJECTED",
        checkpoint.known_at,
    )
    assert [(e.record_seq, e.event_type) for e in step.bundle.events] == [
        (1, "CONTRACT_BOOKED"),
        (2, "CONTRACT_ACTIVATED"),
    ]

    group = bundle.group.group_key
    finding = Finding(
        code="RESIDUAL_REJECTED",
        severity="ERROR",
        subject_key="C-EX34/L4-D",
        detail={},
        stage=5,
        event_key=None,
    )
    findings = canonical_bytes((finding,)).decode("utf-8")

    def install(step_behaviour: Callable[[], None]) -> None:
        def compute(input_bundle: InputBundle) -> OutputBundle:
            if len(input_bundle.events) == 2:  # the step bundle
                step_behaviour()
            return OutputBundle(ENGINE_VERSION, "0" * 64, (_draft_book(group),), ())

        monkeypatch.setattr(erev_engine, "compute", compute, raising=False)

    def rejected() -> None:
        detail = {"findings": findings}
        raise EngineError("RESIDUAL_REJECTED", "the residual is below the range", detail=detail)

    install(rejected)
    result = run_engine(loaded)
    assert [(outcome.step.seq, outcome.actual) for outcome in result.steps] == [
        (2, "RESIDUAL_REJECTED")
    ]
    assert_checkpoints(loaded, result)

    def expect_problem_mismatches(run: RunResult | None = None) -> list[tuple[str, str, str, str]]:
        with pytest.raises(CheckpointMismatchError) as raised:
            assert_checkpoints(loaded, run_engine(loaded) if run is None else run)
        return [
            (m.subject, m.field, m.expected, m.actual)
            for m in raised.value.mismatches
            if m.field == "expect_problem"
        ]

    # A result without the step outcome fails closed.
    assert expect_problem_mismatches(dataclasses.replace(result, steps=())) == [
        ("timeline seq 2", "expect_problem", "RESIDUAL_REJECTED", "<absent>")
    ]

    install(lambda: None)
    assert expect_problem_mismatches() == [
        ("timeline seq 2", "expect_problem", "RESIDUAL_REJECTED", "computed")
    ]

    def other_code() -> None:
        raise EngineError("TOTAL_SSP_ZERO", "every selected SSP is zero")

    install(other_code)
    assert expect_problem_mismatches() == [
        ("timeline seq 2", "expect_problem", "RESIDUAL_REJECTED", "TOTAL_SSP_ZERO")
    ]


def test_d83_key_products_default_to_principal() -> None:
    """D-83 ruling 1: a key product without ``principal_agent`` resolves as PRINCIPAL, a stated
    value stays, and a platform product row keeps the T-REF-20 default NOT_ASSESSED (S03-R-09)."""
    loaded = _load("RND-CHK-001")
    world = loaded.key.world
    assert world.products and all(p.principal_agent is None for p in world.products)
    (checkpoint,) = _build_checkpoint_bundles(loaded)
    assert {p.code: p.principal_agent for p in checkpoint.bundles[0].group.products} == {
        p.code: "PRINCIPAL" for p in world.products
    }

    first, *rest = world.products
    agent = first.model_copy(update={"principal_agent": "AGENT"})
    stated = loaded.key.model_copy(
        update={"world": world.model_copy(update={"products": (agent, *rest)})}
    )
    (variant,) = _build_checkpoint_bundles(LoadedKey(stated, loaded.path, loaded.sha256))
    assert {p.code: p.principal_agent for p in variant.bundles[0].group.products}[first.code] == (
        "AGENT"
    )

    # Platform products: the T-REF-20 column default and the API-S-Product input default.
    default = cast(DefaultClause, product_table.c.principal_agent.server_default)
    assert str(default.arg) == "'NOT_ASSESSED'"
    assert ProductIn(code="SKU-1", name="Product").principal_agent is PrincipalAgent.NOT_ASSESSED


def test_d85_key_implied_price_change_settlement() -> None:
    """D-85 ruling 3: RND-CHK-003C names no ``price_change_settlement`` and its checkpoint expects
    REFUND_LIABILITY credits in FY2026-P02 per obligation (D-90 erratum: POB-001 Cr 33.34, POB-002
    Cr 33.33, POB-003 Cr 33.33; total 100.00), so the runner supplies CREDIT_OR_REFUND in the
    modification questionnaire and the CONTRACT_AMENDED payload, and records the run note, which
    quotes the first credit line. A modification without ``price_change_amount`` gets no member
    (MOD-CHK-027-S6-EX8)."""
    loaded = _load("RND-CHK-003C")
    modifications = loaded.key.contracts[0].modifications
    assert modifications is not None and modifications[0].questionnaire == {}
    (checkpoint,) = _build_checkpoint_bundles(loaded)
    bundle = _bundle_of(checkpoint, "C-CREDIT")
    (built,) = bundle.contracts[0].modifications
    assert built.questionnaire == {"price_change_settlement": "CREDIT_OR_REFUND"}
    (amended,) = [event for event in bundle.events if event.event_type == "CONTRACT_AMENDED"]
    assert amended.payload["price_change_settlement"] == "CREDIT_OR_REFUND"
    assert run_engine(loaded).notes == (
        "D-85: C-CREDIT MOD-CREDIT-1 price_change_settlement CREDIT_OR_REFUND, implied by "
        "checkpoint after-credit subledger FY2026-P02 US01 REFUND_LIABILITY cr 33.34 (JET-05c)",
    )

    other = _Assembler(_load("MOD-CHK-027-S6-EX8"))  # derivation only, no compute (ENC-5)
    assert (other.settlements, other.notes) == ({}, [])


def test_l6_5_performing_only_entity_reads_zero_balances() -> None:
    """S10-INV-08: UK01 only performs the ENT-CHK-070 line, so the engine publishes no T-CON-09 row
    for it and the key's zero balances for UK01 compare equal. The contracting entity keeps the
    strict comparison: an absent row there stays absent."""
    loaded = _load("ENT-CHK-070-CONTRACTING-ENTITY-RECOGNISES-REVENUE")
    result = run_engine(loaded)
    assert_checkpoints(loaded, result)
    comparison = _CheckpointComparison(loaded.key, loaded.key.checkpoints[0], result.checkpoints[0])
    assert comparison.performing_only(("C-ENT-070",), "UK01")
    assert not comparison.performing_only(("C-ENT-070",), "US01")


def test_template_convention_enters_level_p() -> None:
    """As the platform bundle does, a template's ``ratable_convention`` enters POL-090 at level P
    on the OBLIGATION scope, above the framework default DAILY (POLICIES §0.5 rule 2; L4-3-Q-2)."""
    (checkpoint,) = _build_checkpoint_bundles(_load("RND-CHK-005-USD-100-OVER-THREE-MONTHS"))
    resolver = PolicyResolver(checkpoint.bundles[0].books[0].policies)
    code = "recognition.time_convention"
    resolved = resolver.resolved(
        code, contract="C-RND-005", obligation="C-RND-005/POB-001", entity="US01"
    )
    assert (resolved.value, resolved.level, resolved.scope) == ("MONTHLY_EVEN", "P", "OBLIGATION")
    group = resolver.resolved(code)
    assert (group.value, group.level) == ("DAILY", "DEFAULT")


def test_run_engine_fails_closed_without_compute(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delattr(erev_engine, "compute", raising=False)
    with pytest.raises(AnswerKeyError, match="BUILD_SPEC END-9"):
        run_engine(_load("RND-CHK-001"))


# AKS-3 corrections (docs/reviews/loop/sprint/L4-3.md, batch L4-3-B4)


def _computed(key_id: str, name: str, contract_key: str) -> BookOutput:
    """The key's book output at checkpoint ``name`` for the group of ``contract_key``."""
    checkpoint = next(c for c in _build_checkpoint_bundles(_load(key_id)) if c.name == name)
    output = cast(OutputBundle, erev_engine.compute(_bundle_of(checkpoint, contract_key)))
    (book,) = [b for b in output.books if b.book_code == checkpoint.book]
    return book


def _posted(book: BookOutput) -> dict[tuple[str, str, str, str], int]:
    """Σ line amounts per (posting period, entry kind, side, role or role:purpose)."""
    found: dict[tuple[str, str, str, str], int] = {}
    for intent in book.posting_intents:
        for line in intent.lines:
            role = line.account_role
            if line.clearing_purpose is not None:
                role = f"{role}:{line.clearing_purpose}"
            key = (intent.posting_period_key, intent.entry_kind, line.side, role)
            found[key] = found.get(key, 0) + line.amount_txn
    return found


def _balance(book: BookOutput, subject_key: str, period_key: str) -> Mapping[str, object]:
    (row,) = [
        b for b in book.balances if (b.subject_key, b.period_key) == (subject_key, period_key)
    ]
    return row.columns


def test_aks3_refund_liability_flows_and_return_asset_parts() -> None:
    """RET-CHK-029-S3-EX22 at 28 February 2026 (FASB Example 22).

    Stage 12 reads the refund-liability movements as monetary flows, so S12-INV-03 holds beside a
    refund liability (L4-3-Q-29). T-CON-09 carries the refund liability and the return asset
    (L4-3-Q-32), JET-07c and JET-07d post the return asset (S10-R-16), and the delivered quantity
    is gross under POL-053 REDUCE_CONTRACT_QUANTITY (D-87 L5-3-Q-5, replacing L4-3-Q-28's net).
    """
    book = _computed("RET-CHK-029-S3-EX22", "end-of-february", "C-RET")
    january = _balance(book, "C-RET@US01", "FY2026-P01")
    february = _balance(book, "C-RET@US01", "FY2026-P02")
    assert (january["refund_liability_txn"], january["return_asset_txn"]) == (30000, 18000)
    assert (february["refund_liability_txn"], february["return_asset_txn"]) == (10000, 6000)
    posted = _posted(book)
    assert posted[("FY2026-P01", "RETURN_ASSET", "D", "RETURN_ASSET")] == 18000
    assert posted[("FY2026-P01", "RETURN_ASSET", "C", "COST_OF_REVENUE")] == 18000
    assert posted[("FY2026-P02", "RETURN_ASSET", "D", "BILLING_CLEARING:INVENTORY")] == 12000
    assert posted[("FY2026-P02", "RETURN_ASSET", "C", "RETURN_ASSET")] == 12000
    assert posted[("FY2026-P01", "REFUND_LIABILITY", "C", "REFUND_LIABILITY")] == 30000
    (obligation,) = book.obligation_versions
    columns = obligation.columns
    assert (columns["delivered_quantity_cum"], columns["returned_quantity_cum"]) == (100, 2)


def test_aks3_financing_accretion_posts_jet_11a() -> None:
    """SFC-S3-EX26-RETURN-RIGHT at 30 April 2026 (EX-04-H; S04-R-12a).

    The stage 04 accretion enters stage 12 as ``INTEREST_INCOME`` flows (S12-INV-03) and stage 14
    as JET-11a (S10-R-10; L4-3-Q-29, L4-3-Q-30). Nothing accretes while the return right is open.
    The right expires at the end of its window end date, 31 March 2026, so the return asset is
    released in FY2026-P03 (D-87 L6-5-Q-25).
    """
    book = _computed("SFC-S3-EX26-RETURN-RIGHT", "right-lapsed", "C-EX26R")
    posted = _posted(book)
    assert posted[("FY2026-P04", "FINANCING_INTEREST", "D", "CONTRACT_LIABILITY")] == 95
    assert posted[("FY2026-P04", "FINANCING_INTEREST", "C", "INTEREST_INCOME")] == 95
    early = ("FY2026-P01", "FY2026-P02", "FY2026-P03")
    assert not [key for key in posted if key[0] in early and key[1] == "FINANCING_INTEREST"]
    assert posted[("FY2026-P01", "RETURN_ASSET", "D", "RETURN_ASSET")] == 8000
    assert posted[("FY2026-P03", "RETURN_ASSET", "C", "RETURN_ASSET")] == 8000
    assert ("FY2026-P04", "RETURN_ASSET", "C", "RETURN_ASSET") not in posted
    assert _balance(book, "C-EX26R@US01", "FY2026-P04")["unbilled_receivable_txn"] == 10095


def test_aks3_expected_value_without_scenarios_carries_stored_amount() -> None:
    """VC-S3-EX23-CASEA: an ``EXPECTED_VALUE`` version that stores U without scenarios carries U,
    and its node re-evaluates (S04-R-05; L4-3-Q-27); ``vc_constrained_amount`` is a magnitude
    (L4-3-Q-33)."""
    book = _computed("VC-S3-EX23-CASEA", "end-of-december", "C-EX23")
    assert book.contract_version is not None
    columns = book.contract_version.columns
    assert (columns["transaction_price"], columns["vc_constrained_amount"]) == (8000000, 2000000)
    node = next(n for n in book.trace.nodes if n.id.startswith("vc_unconstrained:"))
    assert (node.formula_id, node.params["probabilities"]) == ("tp.vc_expected_value.v1", "1")
    assert Decimal(node.value) == Decimal("-20000")
    assert reevaluate(book.trace)[node.id] == node.value


def test_aks3_usage_estimate_enters_price_under_derived() -> None:
    """VC-CHK-110 at the end of Q1: POL-240 ``DERIVED`` prices the usage obligation by its pinned
    estimate (PT-01; S04-R-06; L4-3-Q-34): transaction price 140,000.00, and revenue 35,000.00 at
    the FY2026-P03 period node the runner reads at ``as_of`` (L4-3-Q-10)."""
    book = _computed("VC-CHK-110", "end-q1", "C-USAGE")
    assert book.contract_version is not None
    assert book.contract_version.columns["transaction_price"] == 14000000
    nodes = {node.id: node for node in book.trace.nodes}
    assert Decimal(nodes["revenue_cum:C-USAGE/L1-PLAN:FY2026-P03"].value) == Decimal("35000")


def test_aks3_legacy_template_names_every_obligation() -> None:
    """VC-CHK-113-TC-POBVC-16: a legacy template applies to every obligation of the contract, so
    ``CONTRACT_AMENDED.treatments`` names each obligation (S06-R-28; L4-3-Q-31)."""
    checkpoint = _build_checkpoint_bundles(_load("VC-CHK-113-TC-POBVC-16"))[-1]
    bundle = _bundle_of(checkpoint, "Contract 2")
    treatments = {
        str(event.payload["modification_id"]): event.payload["treatments"]
        for event in bundle.events
        if event.event_type == "CONTRACT_AMENDED"
    }
    everyone = ("POB #1", "POB #2", "POB #3")
    assert treatments["MOD-C2-0515"] == dict.fromkeys(everyone, "LEGACY_RETROSPECTIVE")
    assert treatments["MOD-C2-0531"] == dict.fromkeys(everyone, "LEGACY_POB_VC")


# Engine fix lane A (docs/reviews/loop/sprint/L5-3.md, batch L5-3-B1)


def test_l5_3_returns_memo_at_the_version_date() -> None:
    """RET-CHK-060-S3-EX22-REVISED: the 31 January RETURN_RATE revision is measure-only (S08-R-02),
    so no boundary re-prices the group. The version memo is measured at d_v on the Y + E that
    stage 09 nets from ``allocated_amount`` (S04-R-08, S09-R-23; EX-04-G2), and S04-R-02 holds
    (L5-3-Q-1). Neither column cites the inception node, whose value is the earlier memo."""
    for name, returned in (("end-of-january", 0), ("end-of-february", 2)):
        book = _computed("RET-CHK-060-S3-EX22-REVISED", name, "C-RET")
        assert book.contract_version is not None
        version = book.contract_version
        columns = version.columns
        assert (columns["transaction_price"], columns["expected_returns_amount"]) == (
            960000,
            -40000,
        )
        # D-97 (8) T1F-Q-1 (A): the version-date re-measurement links its own node
        # ``<column>@<event>:<group>:-`` holding the stored value (books.version_adjustment.v1),
        # never the last build-up node whose value differs.
        traced = {node.id: node for node in book.trace.nodes}
        for column in ("expected_returns_amount", "transaction_price"):
            node = traced[version.trace_nodes[column]]
            assert node.measure.startswith(f"{column}@"), column
            assert node.formula_id == "books.version_adjustment.v1"
            assert Decimal(node.value) * 100 == columns[column], column
        (obligation,) = book.obligation_versions
        assert obligation.columns["allocated_amount"] == 960000
        assert obligation.columns["returned_quantity_cum"] == returned
    unrevised = _computed("RET-CHK-029-S3-EX22", "end-of-january", "C-RET")
    assert unrevised.contract_version is not None
    assert unrevised.contract_version.trace_nodes["expected_returns_amount"] == (
        "expected_returns_amount:CG-C-RET:-"
    )


# Engine fix lane A (docs/reviews/loop/sprint/L5-3.md, batch L5-3-B2)


def test_l5_3_billed_cum_to_date_at_as_of() -> None:
    """SFC-CHK-137-S3-EX28-CASEB: every checkpoint knows all 60 instalments, while `as_of` ends
    month 1, month 2 or month 60. The engine emits the version at d_v (31 December 2030), and the
    runner reads ``billed_cum`` at `as_of` from the stage 10 period node (API-C-10; L5-3-Q-11):
    18,871.00, 37,742.00 and 1,132,260.00, so no ``billed_cum`` mismatch remains."""
    loaded = _load("SFC-CHK-137-S3-EX28-CASEB")
    book = _computed("SFC-CHK-137-S3-EX28-CASEB", "end-of-month-1", "C-FIN-B")
    assert book.contract_version is not None
    assert book.contract_version.columns["billed_cum"] == 113226000  # emitted at d_v
    rendered: list[str] = []
    try:
        assert_checkpoints(loaded, run_engine(loaded))
    except CheckpointMismatchError as error:
        rendered = [item.render() for item in error.mismatches if item.field == "billed_cum"]
    assert rendered == []


# Engine fix lane A (docs/reviews/loop/sprint/L5-3.md, batch L5-3-B3)


def test_l5_3_calendar_covers_the_amortisation_period() -> None:
    """COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT: the world and the lines end in December
    2026, while the commission amortises over 36 months from 1 January 2026. Stage 11 places the
    last amortisation on 31 December 2028, so the calendar reaches FY2028-P12 (CV-12; L5-3-Q-21)."""
    loaded = _load("COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT")
    checkpoint = _build_checkpoint_bundles(loaded)[0]
    (bundle,) = checkpoint.bundles
    (entity,) = bundle.entities
    last = entity.periods[-1]
    assert (last.period_key, last.end_date.isoformat()) == ("FY2028-P12", "2028-12-31")


def test_l5_3_revenue_to_date_before_the_version_date() -> None:
    """MOD-CHK-043-S6-EX7: the end-2028 and end-2029 checkpoints know every instalment through 2031,
    so the engine emits the version at d_v, 1 January 2031 (revenue 410,000.00). No boundary event
    falls after `as_of`, so the runner reads the obligation at `as_of` from the stage 09 period
    nodes (API-C-10; L5-3-Q-11): 270,000.00 and 340,000.00, and no revenue_cum mismatch remains."""
    loaded = _load("MOD-CHK-043-S6-EX7")
    book = _computed("MOD-CHK-043-S6-EX7", "end-2028", "C-EX7")
    assert book.contract_version is not None
    assert book.contract_version.columns["revenue_cum"] == 41000000  # emitted at d_v
    rendered: list[str] = []
    try:
        assert_checkpoints(loaded, run_engine(loaded))
    except CheckpointMismatchError as error:
        rendered = [item.render() for item in error.mismatches if item.field == "revenue_cum"]
    assert rendered == []


# Engine fix lane A (docs/reviews/loop/sprint/L5-3.md, batch L5-3-B4)


def test_l5_3_parity_material_right_product_takes_the_seeded_template() -> None:
    """MR-CHK-052-GT15-CONTINUATION: under LEGACY_PARITY, product MR-SVC names the key template
    TPL-LEGACY-MR-ND, of kind MATERIAL_RIGHT. S03-R-18 gives LEGACY-MATERIAL-RIGHT to "a product
    the migration mapping profile marks as a material right", as the golden tenant does for its
    "Material Right" SKUs (L5-3-Q-24). The runner therefore names the seeded code for that product,
    and the other products keep their key template codes."""
    checkpoint = _build_checkpoint_bundles(_load("MR-CHK-052-GT15-CONTINUATION"))[0]
    (bundle,) = checkpoint.bundles
    codes = {item.code: item.default_template_code for item in bundle.group.products}
    assert codes["MR-SVC"] == "LEGACY-MATERIAL-RIGHT"
    assert codes["HW-1"] == "TPL-LEGACY-DISTINCT"
    loaded = _load("MR-CHK-054-S2-EX49")
    declared = {product.code: product.pob_template for product in loaded.key.world.products}
    native = _build_checkpoint_bundles(loaded)[0]
    for item in native.bundles[0].group.products:  # a DEFAULT-preset key keeps its codes
        assert item.default_template_code == declared[item.code]


def test_l5_3_forced_book_value_is_never_overridden() -> None:
    """IFRS-S13-SWITCH-SHIPPING sets tenant POL-021 ``pob.shipping_as_fulfilment`` TRUE. The
    registry marks the code FORCED in the IFRS15 book (POLICIES POL-021 "FALSE FORCED"), and the
    platform resolver returns the framework default for a forced code (``registry.resolve``:
    "Forced defaults are never overridden"). The runner assembles the book policies the same way:
    the ASC606 book takes the tenant value and the IFRS15 book keeps FALSE (L5-3-Q-26)."""
    checkpoint = _build_checkpoint_bundles(_load("IFRS-S13-SWITCH-SHIPPING"))[0]
    (bundle,) = checkpoint.bundles
    found = {}
    for book in bundle.books:
        (policy,) = [p for p in book.policies if p.code == "pob.shipping_as_fulfilment"]
        found[book.book_code] = (policy.value, policy.level)
    assert found == {"ASC606": ("TRUE", "T"), "IFRS15": ("FALSE", "DEFAULT")}


# Golden parity lane L6-2 (docs/reviews/loop/sprint/L6-2.md, batch L6-2-B1)


def test_l6_2_checkpoint_runs_the_netting_reclass_pass() -> None:
    """MOD-LEGACY-RETRO-GT10 `end-may-after-retrospective`. RCP-08(b), S14-R-05 and S14-R-07 post
    JET-06 and its reversal in the NETTING_RECLASS close pass, and POLICIES JET-06 posts both at
    every period end. The runner runs that pass over each bundle's compute intents and compares the
    subledger over both, so FY2023-P05 nets to UNBILLED_RECEIVABLE Dr 23.86 with CONTRACT_LIABILITY
    0.00 (L5-3-Q-6, L5-5-Q-3; D-85). Compute itself posts no reclass."""
    loaded = _load("MOD-LEGACY-RETRO-GT10")
    result = run_engine(loaded)
    (run,) = result.checkpoints
    (output,) = run.outputs
    # D-85a: FX_REMEASUREMENT runs first (L6-5); CLOSE_RELEASE runs between (D-91; ENG-D1).
    ((_remeasured, _release, reclass),) = run.passes
    kinds = {intent.entry_kind for book in output.books for intent in book.posting_intents}
    assert kinds & {"NETTING_RECLASS", "NETTING_RECLASS_REVERSAL"} == set()
    (book,) = [item for item in reclass.books if item.book_code == "ASC606"]
    assert {(i.entry_kind, i.posting_class) for i in book.posting_intents} == {
        ("NETTING_RECLASS", "TIME"),
        ("NETTING_RECLASS_REVERSAL", "TIME"),
    }
    assert_checkpoints(loaded, result)
    without = dataclasses.replace(result, checkpoints=(dataclasses.replace(run, passes=()),))
    with pytest.raises(CheckpointMismatchError) as error:
        assert_checkpoints(loaded, without)
    assert sorted(item.render() for item in error.value.mismatches) == [
        "MOD-LEGACY-RETRO-GT10 end-may-after-retrospective subledger FY2023-P05 US01 "
        "CONTRACT_LIABILITY/21002 line: expected <absent>, actual dr 23.86; functional dr 23.86",
        "MOD-LEGACY-RETRO-GT10 end-may-after-retrospective subledger FY2023-P05 US01 "
        "UNBILLED_RECEIVABLE/15002 dr: expected 23.86, actual <absent>",
    ]


# Lane L6-3 (docs/reviews/loop/sprint/L6-3.md, batch L6-3-B3): answer keys named by RPS-4


def test_l6_3_world_starts_at_the_earliest_inception() -> None:
    """DISC-S10-DISCLOSURES-RPO-EX42: the world's periods start in July 2026, while contracts B
    and C are signed on 30 June 2026. The template versions and the entity calendar start with the
    month of the earliest inception, so stage 03 resolves TPL-SERIES-RATABLE at the inception date
    (S03-R-02, no PRODUCT_UNMAPPED) and every engine date has a period (CV-12; L6-3-Q-16). A key
    whose contracts start within the world keeps ``world.periods.from``."""
    loaded = _load("DISC-S10-DISCLOSURES-RPO-EX42")
    checkpoint = _build_checkpoint_bundles(loaded)[0]
    for bundle in checkpoint.bundles:
        (entity,) = bundle.entities
        assert (entity.periods[0].period_key, entity.periods[0].start_date.isoformat()) == (
            "FY2026-P06",
            "2026-06-01",
        )
        assert {item.effective_from.isoformat() for item in bundle.pob_template_versions} == {
            "2026-06-01"
        }
    assert_checkpoints(loaded, run_engine(loaded))
    within = _build_checkpoint_bundles(_load("DISC-GE-06-IDIQ-TASK-ORDERS-OPTIONS-RPO"))[0]
    assert within.bundles[0].entities[0].periods[0].period_key == "FY2026-P02"


# Engine fix lane C (docs/reviews/loop/sprint/L6-5.md, batch L6-5-B2, resumed run)


def test_l6_5_checkpoint_runs_the_fx_remeasurement_pass_first() -> None:
    """FX-CHK-082 `asc606-january-close`. D-85a (L6-2-Q-2): a checkpoint runs every pass RCP-08(b)
    orders after compute, FX_REMEASUREMENT, then CLOSE_RELEASE (D-91 gaps (iii); ENG-D1), then
    NETTING_RECLASS, and each reads the earlier passes as posted. JET-10b posts Dr FX_GAIN_LOSS
    230.00 / Cr CONTRACT_LIABILITY 230.00 in the pass, so the January contract liability debit
    nets to 880.00 (S12-R-10; S14-R-05; CHK-082)."""
    loaded = _load("FX-CHK-082-REFUNDABLE-ADVANCE-MONETARY-OVERRIDE-VS-IFRIC22")
    result = run_engine(loaded)
    run = result.checkpoints[0]
    ((remeasured, _release, _reclass),) = run.passes  # then CLOSE_RELEASE (D-91; ENG-D1)
    (book,) = [item for item in remeasured.books if item.book_code == "ASC606"]
    assert {(i.entry_kind, i.posting_class) for i in book.posting_intents} == {
        ("FX_REMEASUREMENT", "TIME")
    }
    assert_checkpoints(loaded, result)
    first = dataclasses.replace(run, passes=())
    without = dataclasses.replace(result, checkpoints=(first, *result.checkpoints[1:]))
    with pytest.raises(CheckpointMismatchError) as error:
        assert_checkpoints(loaded, without)
    assert sorted(item.render() for item in error.value.mismatches) == [
        "FX-CHK-082-REFUNDABLE-ADVANCE-MONETARY-OVERRIDE-VS-IFRIC22 asc606-january-close subledger "
        "FY2026-P01 US01 CONTRACT_LIABILITY/2100 functional_dr: expected 880.00, actual dr 1110.00",
        "FX-CHK-082-REFUNDABLE-ADVANCE-MONETARY-OVERRIDE-VS-IFRIC22 asc606-january-close subledger "
        "FY2026-P01 US01 FX_GAIN_LOSS/7200 dr: expected 0.00, actual <absent>",
    ]


# Engine fix lane D (docs/reviews/loop/sprint/L7-5.md, batch L7-5-B1)


def test_l7_5_runner_supplies_contract_activated_after_the_assessment() -> None:
    """D-87 L6-5-Q-12 (i): STP1-S1-EX1-CASEA books and assesses collectibility (not probable) but
    never activates, so the runner supplies CONTRACT_ACTIVATED with a passing checklist right after
    the first assessment, at its effective date and record time, and records the run note. The
    contract enters NOT_A_CONTRACT and the deposits post JET-01b. A key that activates gets none."""
    loaded = _load("STP1-S1-EX1-CASEA")
    assembler = _Assembler(loaded)
    assert assembler.activations == {"C-BLDG": 2}
    first, second = assembler.checkpoints()
    bundle = _bundle_of(first, "C-BLDG")
    assert [(e.record_seq, e.stream_version, e.event_type) for e in bundle.events] == [
        (1, 1, "CONTRACT_BOOKED"),
        (2, 2, "COLLECTIBILITY_ASSESSED"),
        (2, 3, "CONTRACT_ACTIVATED"),
        (3, 4, "PAYMENT_RECEIVED"),
    ]
    assessed, activated = bundle.events[1], bundle.events[2]
    assert (activated.effective_date, activated.recorded_at) == (
        assessed.effective_date,
        assessed.recorded_at,
    )
    assert activated.payload == {"checklist": [{"code": "ANSWER_KEY_WORLD", "status": "PASSED"}]}
    assert [e.event_type for e in _bundle_of(second, "C-BLDG").events].count(
        "CONTRACT_ACTIVATED"
    ) == 1
    result = run_engine(loaded)
    assert result.notes == (
        "L6-5-Q-12: C-BLDG CONTRACT_ACTIVATED with a passing checklist supplied after "
        "COLLECTIBILITY_ASSESSED seq 2 (effective 2026-01-01); the key books and assesses "
        "collectibility but never activates",
    )
    assert_checkpoints(loaded, result)

    # Without the supplied event the contract stays DRAFT (Table 2.2-A).
    runs = tuple(
        dataclasses.replace(
            run,
            checkpoint=dataclasses.replace(
                run.checkpoint,
                bundles=tuple(
                    dataclasses.replace(
                        b, events=tuple(e for e in b.events if e.event_type != "CONTRACT_ACTIVATED")
                    )
                    for b in run.checkpoint.bundles
                ),
            ),
            outputs=tuple(
                cast(
                    OutputBundle,
                    erev_engine.compute(
                        dataclasses.replace(
                            b,
                            events=tuple(
                                e for e in b.events if e.event_type != "CONTRACT_ACTIVATED"
                            ),
                        )
                    ),
                )
                for b in run.checkpoint.bundles
            ),
            passes=(),
        )
        for run in result.checkpoints
    )
    with pytest.raises(CheckpointMismatchError, match="status_in_book: expected NOT_A_CONTRACT"):
        assert_checkpoints(loaded, dataclasses.replace(result, checkpoints=runs))

    assert _Assembler(_load("RND-CHK-001")).activations == {}


def test_l7_5_catch_up_estimate_reads_the_tp_change_share() -> None:
    """D-87 L6-5-Q-27: VC-CHK-101-S3-EX23-CASEB asserts ``catch_up_estimate_cum`` 5,000.00 for a
    variable consideration change, which S09-R-36 publishes as ``catch_up_tp_change_cum``. The
    comparison reads the sum of both engine columns and the run note names the row; a row that
    also asserts ``catch_up_tp_change_cum`` compares strictly."""
    loaded = _load("VC-CHK-101-S3-EX23-CASEB")
    result = run_engine(loaded)
    note = (
        "L6-5-Q-27: checkpoint end-of-february obligation C-EX23/L1-PROD catch_up_estimate_cum "
        "compares with catch_up_tp_change_cum + catch_up_estimate_cum"
    )
    assert note in result.notes
    assert_checkpoints(loaded, result)
    checkpoint = next(c for c in loaded.key.checkpoints if c.name == "end-of-february")
    run = next(r for r in result.checkpoints if r.checkpoint.name == "end-of-february")
    (book,) = [b for output in run.outputs for b in output.books if b.book_code == checkpoint.book]
    (obligation,) = [o for o in book.obligation_versions if o.subject_key == "C-EX23/L1-PROD"]
    assert (
        obligation.columns["catch_up_tp_change_cum"],
        obligation.columns["catch_up_estimate_cum"],
    ) == (500000, 0)

    blocks = []
    for block in checkpoint.contracts or ():
        rows = tuple(
            {**row, "catch_up_tp_change_cum": row["catch_up_estimate_cum"]}
            if "catch_up_estimate_cum" in row
            else row
            for row in block.obligations or ()
        )
        blocks.append(block.model_copy(update={"obligations": rows}))
    strict = checkpoint.model_copy(update={"contracts": tuple(blocks)})
    found = _CheckpointComparison(loaded.key, strict, run).mismatches()
    assert [m.render() for m in found] == [
        "VC-CHK-101-S3-EX23-CASEB end-of-february obligation C-EX23/L1-PROD catch_up_estimate_cum: "
        "expected 5000.00, actual 0.00"
    ]


def test_l7_5_runner_supplies_the_returns_immaterial_judgement() -> None:
    """D-87 L5-3-Q-9: RET-BR-03 sells ARM-200 (``returns.model`` EXPECTED_RETURNS at level P) with
    a price protection element but no RETURN_RATE element and no return, so S04-R-08 raises
    RETURN_ESTIMATE_MISSING for L1-ARMS. The runner supplies the REVIEWED OTHER judgement
    ``returns_immaterial`` true and records the run note; L1-SPARES has its RETURN_RATE element and
    gets none. Without the judgement compute raises the finding."""
    loaded = _load("RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION")
    assembler = _Assembler(loaded)
    assert assembler.immaterial == {"BR-03-ARMS": ("L1-ARMS",)}
    assert [note for note in assembler.notes if note.startswith("L5-3-Q-9")] == [
        "L5-3-Q-9: BR-03-ARMS L1-ARMS REVIEWED judgement OTHER returns_immaterial true supplied; "
        "returns.model EXPECTED_RETURNS at level P, no RETURN_RATE element targets the obligation, "
        "no RETURN_RECORDED names it and no such judgement exists"
    ]
    checkpoint = assembler.checkpoints()[0]
    bundle = _bundle_of(checkpoint, "BR-03-ARMS")
    contracts = {c.external_id: c for c in bundle.contracts}
    (supplied,) = contracts["BR-03-ARMS"].judgements
    assert (supplied.judgement_key, supplied.topic, supplied.subject_key, supplied.book_code) == (
        "BR-03-ARMS/RUNNER-RETURNS-IMMATERIAL-L1-ARMS",
        "OTHER",
        "BR-03-ARMS/L1-ARMS",
        None,
    )
    assert dict(supplied.outcome) == {"obligation_key": "L1-ARMS", "returns_immaterial": "true"}
    assert erev_engine.compute(bundle) is not None
    without = dataclasses.replace(
        bundle,
        contracts=tuple(dataclasses.replace(c, judgements=()) for c in bundle.contracts),
    )
    with pytest.raises(EngineError, match="RETURN_ESTIMATE_MISSING"):
        erev_engine.compute(without)

    assert _Assembler(_load("RET-CHK-029-S3-EX22")).immaterial == {}


def _deltas(assembler: _Assembler, contract: str, reference: str) -> list[tuple[object, ...]]:
    return [
        (
            line["obligation_key"],
            line["action"],
            line["quantity_delta"],
            line["consideration_delta"],
            line.get("end_date"),
        )
        for line in assembler.terms[(contract, reference)]
    ]


def test_l7_5_runner_converts_terms_form_modification_lines() -> None:
    """D-87 L5-3-Q-19 = L5-5-Q-17: terms-form lines become T-CON-06 delta lines. A kind TERMINATION
    or REMOVE_OBLIGATION line, or one ending before d, is REMOVE with ΔQ = −(in force − net
    delivered); a key not in force is ADD at its terms; the in-force lines share D =
    price_change_amount − Σ ADD total price. The converted price_change_amount is null, no D-85
    settlement is implied for it, and the run note lists the deltas."""
    fs09 = _Assembler(_load("MOD-FS-09-CANCELLATION-REFUND-COMMISSION"))
    assert _deltas(fs09, "FS-09", "MOD-FS09-TERM") == [
        ("L1-SUB", "REMOVE", Decimal("-1"), Decimal("-72000.00"), date(2027, 3, 31))
    ]
    assert fs09.settlements == {}
    assert [n for n in fs09.notes if n.startswith("L5-3-Q-19")] == [
        "L5-3-Q-19: FS-09 MOD-FS09-TERM terms-form lines converted to delta form at 2027-03-31 "
        "(price_change_amount -72000.00 -> null): L1-SUB REMOVE quantity_delta -1 "
        "consideration_delta -72000.00"
    ]
    checkpoint = next(c for c in fs09.checkpoints() if c.name == "termination")
    (modification,) = _bundle_of(checkpoint, "FS-09").contracts[0].modifications
    assert modification.price_change_amount is None
    assert [line["action"] for line in modification.lines] == ["REMOVE"]

    fs10 = _Assembler(_load("MOD-FS-10-CLOUD-CONVERSION-CREDIT"))
    assert _deltas(fs10, "FS-10", "MOD-FS10-CONVERT") == [
        ("L2-PCS", "REMOVE", Decimal("-1"), Decimal("0.00"), date(2026, 12, 31)),
        ("L3-SAAS", "ADD", Decimal("1"), Decimal("80000.00"), date(2028, 12, 31)),
    ]
    js06 = _Assembler(_load("MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION"))
    assert _deltas(js06, "JS-06", "MOD-JS06-SCHEDULE") == [
        ("L3-STORE3", "REMOVE", Decimal("-1"), Decimal("-10000.00"), date(2038, 6, 30))
    ]
    # Delta-form keys are not converted.
    assert _Assembler(_load("MOD-CHK-027-S6-EX8")).terms == {}


def test_l7_5_largest_remainder_apportionment() -> None:
    """L5-3-Q-19: D by largest remainder over |terms − in-force| weights, equal when all are 0."""
    assert _largest_remainder(-1000, [Decimal(1), Decimal(1), Decimal(1)]) == [-334, -333, -333]
    assert _largest_remainder(500, [Decimal(0), Decimal(0)]) == [250, 250]
    assert _largest_remainder(101, [Decimal(3), Decimal(1)]) == [76, 25]
    assert _largest_remainder(0, [Decimal(2)]) == [0]
    assert _largest_remainder(7, []) == []


# Engine fix lane E (docs/reviews/loop/sprint/L7-6.md, batch 3)


def test_l7_6_revenue_to_date_before_a_later_eac_version() -> None:
    """COST-S8-CONTRACT-COSTS-IMPAIRMENT `end-2026`: the checkpoint knows EAC-SVC version 2 of
    31 December 2028, so the engine emits the version at d_v, 31 December 2028 (revenue
    300,000.00). An EAC version starts no allocation segment, so that event does not stop the
    runner from reading the obligation at `as_of` from the stage 09 period node (API-C-10;
    L5-3-Q-11): 100,000.00, and no revenue_cum mismatch remains. The same event pinning a
    VARIABLE_CONSIDERATION version would still stop the overlay."""
    loaded = _load("COST-S8-CONTRACT-COSTS-IMPAIRMENT")
    book = _computed("COST-S8-CONTRACT-COSTS-IMPAIRMENT", "end-2026", "C-COST-IMP")
    assert book.contract_version is not None
    assert book.contract_version.columns["revenue_cum"] == 30000000  # emitted at d_v
    (bundle,) = _build_checkpoint_bundles(loaded)[0].bundles
    (later,) = [
        event
        for event in bundle.events
        if event.event_type == "ESTIMATE_CHANGED"
        and event.effective_date.isoformat() > "2026-12-31"
    ]
    assert _starts_no_segment(bundle, later)
    as_vc = tuple(
        dataclasses.replace(version, estimate_kind="VARIABLE_CONSIDERATION")
        for version in bundle.estimate_versions
    )
    assert not _starts_no_segment(dataclasses.replace(bundle, estimate_versions=as_vc), later)
    rendered: list[str] = []
    try:
        assert_checkpoints(loaded, run_engine(loaded))
    except CheckpointMismatchError as error:
        rendered = [item.render() for item in error.mismatches if item.field == "revenue_cum"]
    assert rendered == []


# Engine fix lane D, Level 8 (docs/reviews/loop/sprint/L8-D.md, batch 1)


def test_l8_d_subledger_block_compares_its_own_period_whatever_as_of() -> None:
    """D-88 L7-5-Q-12 (b): REC-S5-UPFRONTFEE-OWN-B `end-of-january` (as_of 2026-01-31) lists the
    FY2026-P02 lines. The block compares the entries of its own period from the checkpoint's
    outputs, whatever as_of (L1-SUB 2100 Dr / 4010 Cr 1,000.00; L2-FEE 83.34), while as_of still
    selects the labelled balances of FY2026-P01. No other corpus key has a block of a period that
    ends after its as_of."""
    loaded = _load("REC-S5-UPFRONTFEE-OWN-B")
    result = run_engine(loaded)
    (checkpoint,) = [c for c in loaded.key.checkpoints if c.name == "end-of-january"]
    (run,) = [r for r in result.checkpoints if r.checkpoint.name == checkpoint.name]
    comparison = _CheckpointComparison(loaded.key, checkpoint, run)
    assert comparison.period_of("US01") == "FY2026-P01"
    (block,) = checkpoint.subledger or ()
    assert block.period_key == "FY2026-P02"
    found = {
        _render_grain(grain): net.txn for grain, net in comparison.aggregate(block, False).items()
    }
    assert found == {
        "CONTRACT_LIABILITY/2100/L1-SUB": Fraction("1000.00"),
        "CONTRACT_LIABILITY/2100/L2-FEE": Fraction("83.34"),
        "REVENUE/4010/L1-SUB": Fraction("-1000.00"),
        "REVENUE/4010/L2-FEE": Fraction("-83.34"),
    }
    assert comparison.mismatches() == []
    assert_checkpoints(loaded, result)


def test_l8_d_termination_change_line_ending_by_d_reads_as_remove() -> None:
    """D-88 L7-5-Q-13 (a): MOD-CHK-112 keys its TERMINATION in delta form, L1-SUB CHANGE with
    quantity_delta 0, consideration_delta −60,000.00 and end_date 2027-06-30 = d. The runner reads
    the line as REMOVE with quantity_delta −(1 in force − 0 delivered) = −1; consideration_delta,
    the dates and price_change_amount stay as keyed, and the run note records the conversion.
    Terms-form keys and delta-form keys of other kinds are unchanged."""
    assembler = _Assembler(_load("MOD-CHK-112"))
    assert assembler.terms == {}
    assert [
        (
            line["obligation_key"],
            line["action"],
            line["quantity_delta"],
            line["consideration_delta"],
            line.get("start_date"),
            line.get("end_date"),
        )
        for line in assembler.terminations[("C-TERM", "MOD-TERM")]
    ] == [
        (
            "L1-SUB",
            "REMOVE",
            Decimal("-1"),
            Decimal("-60000.00"),
            date(2026, 1, 1),
            date(2027, 6, 30),
        )
    ]
    assert [n for n in assembler.notes if n.startswith("L7-5-Q-13")] == [
        "L7-5-Q-13: C-TERM MOD-TERM delta-form TERMINATION line L1-SUB CHANGE quantity_delta 0 "
        "with end_date 2027-06-30 on or before 2027-06-30 read as REMOVE quantity_delta -1 "
        "(quantity in force 1 less net delivered 0); consideration_delta and dates as keyed"
    ]
    checkpoint = next(c for c in assembler.checkpoints() if c.name == "at-termination")
    (modification,) = _bundle_of(checkpoint, "C-TERM").contracts[0].modifications
    assert modification.price_change_amount is None  # as keyed
    assert [
        (line["action"], line["quantity_delta"], line["consideration_delta"])
        for line in modification.lines
    ] == [("REMOVE", Decimal("-1"), Decimal("-60000.00"))]

    assert _Assembler(_load("MOD-FS-09-CANCELLATION-REFUND-COMMISSION")).terminations == {}
    assert _Assembler(_load("MOD-CHK-027-S6-EX8")).terminations == {}


def test_l8_d_runner_supplies_the_remaining_goods_distinct_answer() -> None:
    """D-88 L7-5-Q-2 (ii) (D-85 pattern): MOD-JS-06's modification answers no questionnaire, and
    checkpoint schedule-revised lists proposed_treatments L1-STORE1 and L2-STORE2 PROSPECTIVE. The
    runner supplies remaining_goods_distinct_from_transferred true for both existing obligations
    with a run note, so stage 06 classes L1-STORE1 D by QUESTIONNAIRE (f 0.025; the S06-R-05
    default was N, CUMULATIVE_CATCH_UP). CUMULATIVE_CATCH_UP supplies false; keys that answer the
    member or list SEPARATE_CONTRACT get nothing."""
    js06 = _Assembler(_load("MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION"))
    assert js06.distinct_answers == {
        ("JS-06", "MOD-JS06-SCHEDULE"): {"L1-STORE1": True, "L2-STORE2": True}
    }
    assert [n for n in js06.notes if n.startswith("L7-5-Q-2 (ii)")] == [
        f"L7-5-Q-2 (ii): JS-06 MOD-JS06-SCHEDULE {key} questionnaire "
        "remaining_goods_distinct_from_transferred true supplied; checkpoint schedule-revised "
        "proposed_treatments PROSPECTIVE and the key modification gives no answer"
        for key in ("L1-STORE1", "L2-STORE2")
    ]
    checkpoint = next(c for c in js06.checkpoints() if c.name == "schedule-revised")
    bundle = _bundle_of(checkpoint, "JS-06")
    (modification,) = bundle.contracts[0].modifications
    assert dict(modification.questionnaire) == {
        "L1-STORE1": {"remaining_goods_distinct_from_transferred": True},
        "L2-STORE2": {"remaining_goods_distinct_from_transferred": True},
    }
    (book,) = [b for b in erev_engine.compute(bundle).books if b.book_code == "ASC606"]
    params = {node.id: node.params for node in book.trace.nodes}
    l1 = params["mod_class@JS-06/EV-000005:JS-06/L1-STORE1:-"]
    assert (l1["class"], l1["reason"], l1["value"]) == ("D", "QUESTIONNAIRE", "0.025")

    disc = _Assembler(_load("DISC-CATCH-UP-BY-CAUSE-ESTIMATE-CHANGE-AND-MODIFICATION"))
    assert disc.distinct_answers == {("C-DISC-CAUSE", "MOD-DISC-01"): {"L1-BUILD": False}}
    assert _Assembler(_load("MOD-CHK-027-S6-EX8")).distinct_answers == {}
    assert _Assembler(_load("MOD-FS-03-CASEA-UPSELL-AT-SSP-SEPARATE")).distinct_answers == {}


def test_l8_d_runner_supplies_the_bundle_parent_nondistinct_override() -> None:
    """D-88 L7-5-Q-11 (D-85 pattern): REC-S5-UPFRONTFEE-OWN-A's L2-FEE (SETUP-FEE, template
    TPL-RATABLE of kind STANDARD) names bundle_parent_obligation_key L1-SUB, and no checkpoint row
    or timeline payload names L2-FEE. The runner supplies the REVIEWED POB_DISTINCT_OVERRIDE
    {distinctness nondistinct, integrates_into_obligation_key L1-SUB} with a run note, so stage 03
    merges the fee into the subscription: L1-SUB allocated 15,000.00, 1,250.00 a month, and the key
    passes. Shipping lines (kind SHIPPING, or named in the rows) get none."""
    loaded = _load("REC-S5-UPFRONTFEE-OWN-A")
    assembler = _Assembler(loaded)
    assert [n for n in assembler.notes if n.startswith("L7-5-Q-11")] == [
        "L7-5-Q-11: C-FEE L2-FEE REVIEWED judgement POB_DISTINCT_OVERRIDE distinctness "
        "nondistinct integrates_into_obligation_key L1-SUB supplied; template TPL-RATABLE is "
        "STANDARD, the line names bundle_parent_obligation_key L1-SUB and no checkpoint row or "
        "timeline payload names L2-FEE"
    ]
    checkpoint = assembler.checkpoints()[0]
    bundle = _bundle_of(checkpoint, "C-FEE")
    (supplied,) = bundle.contracts[0].judgements
    assert (supplied.judgement_key, supplied.topic, supplied.subject_key, supplied.book_code) == (
        "C-FEE/RUNNER-POB-NONDISTINCT-L2-FEE",
        "POB_DISTINCT_OVERRIDE",
        "C-FEE/L2-FEE",
        None,
    )
    assert dict(supplied.outcome) == {
        "distinctness": "nondistinct",
        "integrates_into_obligation_key": "L1-SUB",
        "obligation_key": "L2-FEE",
    }
    (book,) = [b for b in erev_engine.compute(bundle).books if b.book_code == "ASC606"]
    assert [
        (item.subject_key, item.columns["allocated_amount"]) for item in book.obligation_versions
    ] == [("C-FEE/L1-SUB", 1500000)]
    assert_checkpoints(loaded, run_engine(loaded))

    for key_id in ("POB-S2-SHIPPING-OWN-ON", "POB-S2-SHIPPING-OWN-OFF", "REC-S5-UPFRONTFEE-OWN-B"):
        assert _Assembler(_load(key_id)).nondistinct == {}


# Answer-key runner lane, Level 9 (docs/reviews/loop/sprint/L9-RUN.md)


def test_l9_ret_br_03_contract_blocks_include_jet_04b() -> None:
    """D-90 (RET-BR-03): stage 14 posts JET-04b one entry per refund-liability component, on the
    component key `<group>@<entity>/<KIND>/<source>` (refund_liability.py), with lines carrying
    `contract_key` (intents.py `_dimensions`). A contract-filtered block attributes by that
    dimension, so `price-protection` FY2026-P05 BR-03-ARMS nets REFUND_LIABILITY 2110 Cr 12,000.00
    and REVENUE 4000 Dr 12,000.00 (the revenue reduction Dr REVENUE / Cr CONTRACT_LIABILITY with
    JET-04b Dr CONTRACT_LIABILITY / Cr REFUND_LIABILITY), and the key passes. The head-only
    attribution dropped the five JET-04b entries (10 mismatches: March 2,000.00; May 12,000.00;
    June 12,000.00 and 1,600.00; August 400.00)."""
    loaded = _load("RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION")
    result = run_engine(loaded)
    (checkpoint,) = [c for c in loaded.key.checkpoints if c.name == "price-protection"]
    (run,) = [r for r in result.checkpoints if r.checkpoint.name == checkpoint.name]
    comparison = _CheckpointComparison(loaded.key, checkpoint, run)
    (block,) = checkpoint.subledger or ()
    assert block.contract == "BR-03-ARMS"
    found = {
        _render_grain(grain): net.txn for grain, net in comparison.aggregate(block, False).items()
    }
    assert found == {
        "REFUND_LIABILITY/2110": Fraction("-12000.00"),
        "REVENUE/4000": Fraction("12000.00"),
    }
    assert comparison.mismatches() == []
    assert_checkpoints(loaded, result)


def test_enc_vc_direction_runner_transmits_the_loaded_direction() -> None:
    """ENC-VC-direction: the runner carries the key's T-CON-12 ``direction`` — explicit in the
    key, or the loader's B3-DG-17 derivation (``models.Estimate``) — onto every
    ``EstimateVersionInput`` of the element, and the amounts stay magnitudes (B3-D16). VC-S3-EX24
    (VOLUME_TIER, no direction in the key) derives DECREASE; VC-FS-02 carries whatever its fixture
    states (the supervisor-ruled INCREASE once recorded there)."""
    ex24 = _load("VC-S3-EX24")
    bundle = _bundle_of(_build_checkpoint_bundles(ex24)[-1], "C-EX24")
    (element,) = ex24.key.contracts[0].estimates
    assert element.direction == "DECREASE"  # derived by the loader, not written in the key
    assert {item.direction for item in bundle.estimate_versions} == {"DECREASE"}
    fs02 = _load("VC-FS-02-COMMITTED-SPEND-TIERED-OVERAGE")
    (overage,) = fs02.key.contracts[0].estimates
    for checkpoint in _build_checkpoint_bundles(fs02):
        versions = _bundle_of(checkpoint, "FS-02").estimate_versions
        assert {item.direction for item in versions} == {overage.direction}
        for item in versions:
            assert item.constrained_amount is not None and item.constrained_amount > 0
            assert all(scenario["amount"] >= 0 for scenario in item.scenarios)
