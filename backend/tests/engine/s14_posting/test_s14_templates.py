"""Stage 14 template parts, counter roles and amount classes.

ENGINE_SPEC_B §14.1 and §14.2.1 (Table 14-A; S14-R-01 to S14-R-03); POLICIES §0.8, §0.9 and §2.3
(JET rules R1 to R9, tables 2.3-A and 2.3-B, JET-01 to JET-17); 05 §3.6.1 and RCP-07. Stages 10 and
11 are built in lane L2-4, so the tests pass a fake consumed state carrying ``FxFlows`` and
``PartInputs`` (D-81 integration after merge; L2-5-Q-10, L2-5-Q-24); stage 12 runs for real and
every trace re-evaluates node for node (DG-ENG-04).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.bundle import AccountMappingInput, FxRateInput, MappingRuleInput
from erev_engine.dates import month_end
from erev_engine.enums import AccountRole, BookCode, ContractEventType
from erev_engine.errors import EngineError
from erev_engine.money import format_money
from erev_engine.stages import s12_fx_entities, s14_posting
from erev_engine.stages.s09_recognition.returns import EXPIRY_AMOUNT_CLASS, EXPIRY_POSTING_PASS
from erev_engine.stages.s12_fx_entities import ControlFlow, FxFlows, FxState
from erev_engine.stages.s14_posting import (
    AMOUNT_CLASSES,
    COUNTER_ROLES,
    JET_PARTS,
    NOT_A_CONTRACT_EVENT,
    TRIGGER_FAMILIES,
    AmountClass,
    JetPart,
    PartInputs,
    PartTarget,
    PostingState,
    RoleLine,
    amount_class,
    role_lines,
)
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    ObligationState,
    PostedIndex,
    RateIndex,
    Target,
)
from erev_engine.trace import SourceRef, TraceBuilder, reevaluate
from support import bundles
from support.recognition import (
    CONTRACT_KEY,
    allocated_state,
    book_context,
    obligation,
    segment,
    usd,
)

ENTITY = bundles.ENTITY_CODE
ASSETS = ("COST_TO_OBTAIN_ASSET", "COST_TO_FULFILL_ASSET")
CL = "CONTRACT_LIABILITY"

# POLICIES §2.3, transcribed independently: part -> (template id, debit roles, credit roles) in the
# direction of a positive amount. Split and alternative roles are listed together.
POLICIES_TEMPLATES: Mapping[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {
    "JET-01": ("JET-01", (), ()),
    "JET-01b receipt": ("JET-01b", ("BILLING_CLEARING:UNAPPLIED_CASH",), ("DEPOSIT_LIABILITY",)),
    "JET-01b criteria met": ("JET-01b", ("DEPOSIT_LIABILITY",), (CL,)),
    "JET-01b 25-7 revenue": ("JET-01b", ("DEPOSIT_LIABILITY",), ("REVENUE",)),
    "JET-01b refund": ("JET-01b", ("DEPOSIT_LIABILITY",), ("BILLING_CLEARING:UNAPPLIED_CASH",)),
    "JET-02 principal": ("JET-02", (CL,), ("REVENUE",)),
    "JET-02 agent": ("JET-02", (CL,), ("REVENUE", "BILLING_CLEARING:AP_SUPPLIER")),
    "JET-03 invoice": ("JET-03", ("ACCOUNTS_RECEIVABLE",), (CL, "SALES_TAX_PAYABLE")),
    "JET-03 credit memo": ("JET-03", (CL, "SALES_TAX_PAYABLE"), ("ACCOUNTS_RECEIVABLE",)),
    "JET-04a": ("JET-04a", (CL,), ("REVENUE",)),
    "JET-04b": ("JET-04b", (CL,), ("REFUND_LIABILITY",)),
    "JET-04c": ("JET-04c", (CL,), ("RECEIVABLE_CONTRA",)),
    "JET-05a": ("JET-05a", (CL,), ("REVENUE",)),
    "JET-05b": ("JET-05b", ("REVENUE",), (CL,)),
    "JET-05c": ("JET-05c", ("REVENUE",), ("REFUND_LIABILITY",)),
    "JET-06 reclass": ("JET-06", ("UNBILLED_RECEIVABLE", "CONTRACT_ASSET"), (CL,)),
    "JET-06 reversal": ("JET-06", (CL,), ("UNBILLED_RECEIVABLE", "CONTRACT_ASSET")),
    "JET-07a": ("JET-07a", (), ()),
    "JET-07b": ("JET-07b", (), ()),
    "JET-07c": ("JET-07c", ("RETURN_ASSET",), ("COST_OF_REVENUE",)),
    "JET-07d": ("JET-07d", ("BILLING_CLEARING:INVENTORY",), ("RETURN_ASSET",)),
    "JET-08 exercise": ("JET-08", (), ()),
    "JET-08 expiry": ("JET-08", (CL,), ("REVENUE",)),
    "JET-09a": ("JET-09a", ("COST_TO_OBTAIN_ASSET",), ("CONTRACT_COST_CLEARING",)),
    "JET-09a′": ("JET-09a′", ("COST_TO_FULFILL_ASSET",), ("CONTRACT_COST_CLEARING",)),
    "JET-09b": ("JET-09b", ("CONTRACT_COST_AMORTIZATION",), ASSETS),
    "JET-09c": ("JET-09c", ("CONTRACT_COST_IMPAIRMENT",), ASSETS),
    "JET-09d": ("JET-09d", ASSETS, ("CONTRACT_COST_IMPAIRMENT",)),
    "JET-09e": ("JET-09e", ("CONTRACT_COST_AMORTIZATION",), ASSETS),
    "JET-09f": ("JET-09f", ("CONTRACT_COST_CLEARING",), ASSETS),
    "JET-10a": ("JET-10a", (CL,), ("FX_GAIN_LOSS",)),
    "JET-10a′": ("JET-10a′", ("ACCOUNTS_RECEIVABLE",), ("FX_GAIN_LOSS",)),
    "JET-10b": ("JET-10b", ("FX_GAIN_LOSS",), (CL,)),
    "JET-10c": ("JET-10c", ("FX_GAIN_LOSS",), (CL,)),
    "JET-10d": (
        "JET-10d",
        ("FX_GAIN_LOSS",),
        ("REFUND_LIABILITY", "DEPOSIT_LIABILITY", "CONSIDERATION_PAYABLE"),
    ),
    "JET-11a": ("JET-11a", (CL,), ("INTEREST_INCOME",)),
    "JET-11b": ("JET-11b", ("INTEREST_EXPENSE",), (CL,)),
    "JET-12": ("JET-12", ("LOSS_EXPENSE",), ("LOSS_PROVISION",)),
    "JET-13 contracting": ("JET-13", (CL,), ("INTERCOMPANY_DUE_TO",)),
    "JET-13 performing": ("JET-13", ("INTERCOMPANY_DUE_FROM",), ("REVENUE",)),
    "JET-14 promised": ("JET-14", ("CUSTOMER_INCENTIVE_ASSET",), ("CONSIDERATION_PAYABLE",)),
    "JET-14 release": ("JET-14", ("REVENUE",), ("CUSTOMER_INCENTIVE_ASSET",)),
    "JET-14 after revenue": ("JET-14", ("REVENUE",), ("CONSIDERATION_PAYABLE",)),
    "JET-14 share-based": ("JET-14", ("REVENUE",), ("BILLING_CLEARING:EQUITY",)),
    "JET-15": ("JET-15", ("PRE_STANDARD_REVENUE",), (CL,)),  # the delta view (POLICIES JET-15)
    "JET-16 accrual": ("JET-16", ("WARRANTY_EXPENSE",), ("WARRANTY_PROVISION",)),
    "JET-16 claim release": ("JET-16", ("WARRANTY_PROVISION",), ("COST_OF_REVENUE",)),
    "JET-17 unconditional": ("JET-17", ("NONCASH_CONSIDERATION_ASSET",), (CL,)),
    "JET-17 receipt": (
        "JET-17",
        ("BILLING_CLEARING:INVESTMENTS",),
        ("NONCASH_CONSIDERATION_ASSET",),
    ),
}
COVERED_TEMPLATES = (
    "JET-01 JET-01b JET-02 JET-03 JET-04a JET-04b JET-04c JET-05a JET-05b JET-05c JET-06 JET-07c "
    "JET-07d JET-08 JET-09a JET-09a′ JET-09b JET-09c JET-09d JET-09e JET-09f JET-10a JET-10a′ "
    "JET-10b JET-10c JET-10d JET-11a JET-11b JET-12 JET-13 JET-14 JET-15 JET-16 JET-17"
).split()
# Table 2.3-A E-03 literals and close-run passes -> the table 2.3-B rows they trigger.
TABLE_2_3_B = {
    "CONTRACT_ACTIVATED": ("JET-01", "JET-14"),
    "DELIVERY_RECORDED": ("JET-02", "JET-07", "JET-11", "JET-13", "JET-14", "JET-16", "JET-17"),
    "PROGRESS_RECORDED": ("JET-02", "JET-11", "JET-13", "JET-14", "JET-17"),
    "MILESTONE_ACHIEVED": ("JET-02", "JET-11", "JET-13", "JET-14", "JET-17"),
    "COST_INCURRED": ("JET-02 JET-09 JET-11 JET-12 JET-13 JET-14 JET-16 JET-17".split()),
    "USAGE_REPORTED": ("JET-02", "JET-04", "JET-11", "JET-13", "JET-14", "JET-17"),
    "ESTIMATE_CHANGED": "JET-02 JET-04 JET-07 JET-11 JET-12 JET-13 JET-14 JET-17".split(),
    "BILLING_RECORDED": ("JET-01b", "JET-03", "JET-04", "JET-10", "JET-14"),
    "CREDIT_MEMO_RECORDED": ("JET-03", "JET-04", "JET-10"),
    "PAYMENT_RECEIVED": ("JET-01b", "JET-10", "JET-17"),
    "CONTRACT_CRITERIA_MET": ("JET-01b", "JET-10"),
    "CONTRACT_AMENDED": ("JET-05", "JET-14"),
    "CONTRACT_TERMINATED": ("JET-01b", "JET-05", "JET-09", "JET-10"),
    "MATERIAL_RIGHT_EXERCISED": ("JET-08",),
    "MATERIAL_RIGHT_EXPIRED": ("JET-08",),
    "RETURN_RECORDED": ("JET-07", "JET-10"),
    "OPENING_BALANCE_ESTABLISHED": (),
    "CLOSE_RELEASE": (
        "JET-01b JET-02 JET-04 JET-07 JET-09 JET-10 JET-11 JET-12 JET-13 JET-14 JET-17".split()
    ),
    "NETTING_RECLASS": ("JET-06",),
    "FX_REMEASUREMENT": ("JET-10",),
}


def _labels(part: JetPart) -> tuple[frozenset[str], frozenset[str]]:
    debit = frozenset(() if part.debit is None else part.debit.labels)
    credit = frozenset(() if part.credit is None else part.credit.labels)
    return debit, credit


def test_jet_parts_cover_policies_templates() -> None:
    assert set(JET_PARTS) == set(POLICIES_TEMPLATES)
    assert set(COVERED_TEMPLATES) <= {part.template for part in JET_PARTS.values()}
    for key, (template, debit, credit) in POLICIES_TEMPLATES.items():
        part = JET_PARTS[key]
        assert part.template == template, key
        roles = _labels(part)
        if key == "JET-15":
            # The LEGACY book posts Table 14-A's sides, Dr PRE_STANDARD_REVENUE / Cr
            # CONTRACT_LIABILITY, and the delta view adds them (S14-R-23; D-89 L7-6-Q-8).
            assert part.book == "LEGACY"
        assert roles == (frozenset(debit), frozenset(credit)), key
    # Entry kinds of Table 14-A (04 E-29); parts without lines carry none.
    assert {key: part.entry_kind for key, part in JET_PARTS.items() if key.startswith("JET-1")} == {
        "JET-10a": "FX_REMEASUREMENT",
        "JET-10a′": "FX_REMEASUREMENT",
        "JET-10b": "FX_REMEASUREMENT",
        "JET-10c": "FX_REMEASUREMENT",
        "JET-10d": "FX_REMEASUREMENT",
        "JET-11a": "FINANCING_INTEREST",
        "JET-11b": "FINANCING_INTEREST",
        "JET-12": "LOSS_PROVISION",
        "JET-13 contracting": "INTERCOMPANY",
        "JET-13 performing": "INTERCOMPANY",
        "JET-14 promised": "CONSIDERATION_PAYABLE",
        "JET-14 release": "CONSIDERATION_PAYABLE",
        "JET-14 after revenue": "CONSIDERATION_PAYABLE",
        "JET-14 share-based": "CONSIDERATION_PAYABLE",
        "JET-15": "PRE_STANDARD_REVENUE",
        "JET-16 accrual": "WARRANTY_ACCRUAL",
        "JET-16 claim release": "WARRANTY_ACCRUAL",
        "JET-17 unconditional": "NONCASH_CONSIDERATION",
        "JET-17 receipt": "NONCASH_CONSIDERATION",
    }
    assert JET_PARTS["JET-04c"].entry_kind == "RECEIVABLE_CONTRA"
    assert JET_PARTS["JET-06 reversal"].entry_kind == "NETTING_RECLASS_REVERSAL"
    assert {JET_PARTS["JET-07c"].entry_kind, JET_PARTS["JET-07d"].entry_kind} == {"RETURN_ASSET"}
    assert [key for key, part in JET_PARTS.items() if part.entry_kind is None] == [
        "JET-01",
        "JET-07a",
        "JET-07b",
        "JET-08 exercise",
    ]
    # Templates without a target of their own post through another part (S14-R-02, S14-R-03).
    assert {key: part.through for key, part in JET_PARTS.items() if part.through} == {
        "JET-04a": "JET-02 principal",
        "JET-05a": "JET-02 principal",
        "JET-05b": "JET-02 principal",
        "JET-07a": "JET-02 principal",
        "JET-07b": "JET-04b",
        "JET-08 expiry": "JET-02 principal",
    }
    # Owners and counterparties (Table 14-A; R3).
    assert {key for key, part in JET_PARTS.items() if part.owner == "PERFORMING"} == {
        "JET-13 performing",
        "JET-16 accrual",
        "JET-16 claim release",
    }
    assert {key for key, part in JET_PARTS.items() if part.owner == "ASSET_ENTITY"} == {
        "JET-09a",
        "JET-09a′",
        "JET-09b",
        "JET-09c",
        "JET-09d",
        "JET-09e",
        "JET-09f",
    }
    assert JET_PARTS["JET-13 contracting"].counterparty == "PERFORMING"
    assert JET_PARTS["JET-13 performing"].counterparty == "CONTRACTING"
    # No reserved role; clearing purposes exactly on BILLING_CLEARING (§0.8; R8; D-14a).
    labels = {label for part in JET_PARTS.values() for side in _labels(part) for label in side}
    assert not {"RETAINED_EARNINGS", "FINANCING_OBLIGATION", "ROUNDING"} & labels
    assert {label for label in labels if label.startswith("BILLING_CLEARING")} == {
        "BILLING_CLEARING:UNAPPLIED_CASH",
        "BILLING_CLEARING:AP_SUPPLIER",
        "BILLING_CLEARING:INVENTORY",
        "BILLING_CLEARING:EQUITY",
        "BILLING_CLEARING:INVESTMENTS",
    }
    # Every E-03 literal of table 2.3-A and every close-run pass maps to its templates (R9).
    assert set(TABLE_2_3_B) - set(s14_posting.templates.CLOSE_RUN_PASSES) <= set(ContractEventType)
    for trigger, families in TABLE_2_3_B.items():
        assert TRIGGER_FAMILIES.get(trigger, ()) == tuple(families), trigger
    assert TRIGGER_FAMILIES[NOT_A_CONTRACT_EVENT] == ("JET-01b", "JET-10")
    assert TRIGGER_FAMILIES["PRE_STANDARD_REVENUE_RECORDED"] == ("JET-15",)


def test_counter_roles_and_amount_classes() -> None:
    # 05 §3.6.1 and POLICIES table 0.8-A: the counter-entry roles of other subledgers.
    assert {key: role.label for key, role in COUNTER_ROLES.items()} == {
        ("JET-01b receipt", "DEBIT"): "BILLING_CLEARING:UNAPPLIED_CASH",
        ("JET-01b refund", "CREDIT"): "BILLING_CLEARING:UNAPPLIED_CASH",
        ("JET-02 agent", "CREDIT"): "BILLING_CLEARING:AP_SUPPLIER",
        ("JET-07c", "CREDIT"): "COST_OF_REVENUE",
        ("JET-07d", "DEBIT"): "BILLING_CLEARING:INVENTORY",
        ("JET-09a", "CREDIT"): "CONTRACT_COST_CLEARING",
        ("JET-09a′", "CREDIT"): "CONTRACT_COST_CLEARING",
        ("JET-09f", "DEBIT"): "CONTRACT_COST_CLEARING",
        ("JET-14 share-based", "CREDIT"): "BILLING_CLEARING:EQUITY",
        ("JET-16 claim release", "CREDIT"): "COST_OF_REVENUE",
        ("JET-17 receipt", "DEBIT"): "BILLING_CLEARING:INVESTMENTS",
    }
    for (key, side_name), role in COUNTER_ROLES.items():
        side = JET_PARTS[key].debit if side_name == "DEBIT" else JET_PARTS[key].credit
        assert side is not None and role in side.roles, key
    # RCP-07: every part that produces amounts is classified for each of its triggers.
    assert set(AMOUNT_CLASSES) == {key for key, part in JET_PARTS.items() if part.has_amounts}
    for key, part in JET_PARTS.items():
        if part.has_amounts:
            assert set(part.triggers) <= set(AMOUNT_CLASSES[key]), key
    event, reclass = AmountClass("EVENT", None), AmountClass("TIME", "NETTING_RECLASS")
    assert AMOUNT_CLASSES["JET-06 reclass"] == {"NETTING_RECLASS": reclass}
    assert AMOUNT_CLASSES["JET-06 reversal"] == {"NETTING_RECLASS": reclass}
    assert AMOUNT_CLASSES["JET-10a"]["FX_REMEASUREMENT"] == AmountClass("TIME", "FX_REMEASUREMENT")
    assert AMOUNT_CLASSES["JET-10a"]["BILLING_RECORDED"] == event  # settlement at billing
    assert AMOUNT_CLASSES["JET-02 principal"]["DELIVERY_RECORDED"] == event
    assert AMOUNT_CLASSES["JET-02 principal"]["CLOSE_RELEASE"] == AmountClass(
        "TIME", "CLOSE_RELEASE"
    )
    assert AMOUNT_CLASSES["JET-10d"]["ESTIMATE_CHANGED"] == event  # recognition (rev 1.3)
    assert AMOUNT_CLASSES["JET-10d"]["CLOSE_RELEASE"] == AmountClass("TIME", "CLOSE_RELEASE")
    assert {c.amount_class for c in AMOUNT_CLASSES["JET-12"].values()} == {"TIME"}
    assert {c.amount_class for c in AMOUNT_CLASSES["JET-11a"].values()} == {"TIME"}
    assert AMOUNT_CLASSES["JET-09b"]["CLOSE_RELEASE"].amount_class == "TIME"
    assert AMOUNT_CLASSES["JET-09b"]["DELIVERY_RECORDED"] == event  # proportional amortisation
    # Stage 09 publishes return-window expiry as a TIME amount of CLOSE_RELEASE (L1-3-Q-22).
    expiry = AMOUNT_CLASSES["JET-04a"]["CLOSE_RELEASE"]
    assert (expiry.amount_class, expiry.posting_pass) == (EXPIRY_AMOUNT_CLASS, EXPIRY_POSTING_PASS)
    # A target's class also reads the parts that post through it.
    assert amount_class("JET-02 principal", "MATERIAL_RIGHT_EXPIRED") == event
    assert amount_class("JET-02 principal", "CONTRACT_AMENDED") == event
    assert amount_class("JET-04b", "RETURN_RECORDED") == event
    with pytest.raises(ValueError, match="no single amount class"):
        amount_class("JET-06 reclass", "DELIVERY_RECORDED")
    with pytest.raises(ValueError, match="close-run pass"):
        AmountClass("TIME", None)


@dataclass(frozen=True, slots=True)
class _Costs:
    """A fake stage 11 output as stages 12 and 14 read it (L2-5-Q-10, L2-5-Q-24)."""

    allocated: AllocatedState
    fx_flows: FxFlows
    part_inputs: PartInputs


@dataclass(frozen=True, slots=True)
class _NoParts:
    allocated: AllocatedState
    fx_flows: FxFlows


def _obligation(key: str, amount: str = "3000.00") -> ObligationState:
    minor = usd(amount)
    start, end = date(2026, 1, 1), date(2026, 3, 31)
    return obligation(
        key, [segment(Fraction(minor, 100), minor, start=start, end=end)], start=start, end=end
    )


def _rate(kind: str, on: date, rate: str) -> FxRateInput:
    if kind == "spot":
        key, period_key, effective = f"EURUSD-SPOT-{on.isoformat()}", None, on
    else:
        period_key = f"FY{on.year}-P{on.month:02d}"
        key, effective = f"EURUSD-{kind.upper()}-{period_key}", month_end(on)
    return FxRateInput(key, "EURUSD@v1", kind, "EUR", "USD", effective, period_key, Decimal(rate))


def _target(
    measure: str, subject: str, month: int, value: int, *, cause: str | None = None
) -> Target:
    period_key = f"FY2026-P{month:02d}"
    node = f"{measure}:{subject}" + ("" if cause is None else f"#{cause}") + f":{period_key}"
    return Target(BookCode.ASC606, ENTITY, subject, measure, period_key, cause, value, None, node)


def _producer_nodes(tb: TraceBuilder, inputs: PartInputs, currency: str) -> None:
    """Fake the producer nodes of stages 09 to 11 that part targets cite (D-81)."""
    mu = bundles.currencies(currency)[currency].minor_unit
    # D-88 L7-5-Q-4 (1): relief is revenue_cum plus the concessions created, and cites both nodes,
    # so the faked relief node holds revenue_cum alone.
    created: dict[tuple[str, str], int] = {}
    for item in inputs.concessions:
        key = (item.subject_key, item.period_key)
        created[key] = created.get(key, 0) + item.value
    for group in (inputs.relief, inputs.refund_liabilities, inputs.concessions):
        for target in group:
            measure, subject, period_key = target.node_id.rsplit(":", 2)
            value = target.value
            if group is inputs.relief:
                value -= created.get((target.subject_key, target.period_key), 0)
            detail = {"value": format_money(value, mu)}
            tb.node(
                measure=measure,
                subject_key=subject,
                period_key=period_key,
                value=value,
                currency=currency,
                minor_unit=mu,
                formula_id="rec.catch_up.sum.v1",
                inputs=[SourceRef("source_record", target.node_id, detail)],
                narrative_key="rec.catch_up.sum",
            )


def _release(subject: str, month: int, amount: str) -> ControlFlow:
    on = month_end(date(2026, month, 1))
    return ControlFlow(
        "REVENUE", ENTITY, subject, f"{subject}@FY2026-P{month:02d}", on, None, usd(amount)
    )


def _on_event(kind: str, stream_version: int, on: date, amount: str, subject: str) -> ControlFlow:
    event_key = f"{CONTRACT_KEY}/EV-{stream_version:06d}"
    return ControlFlow(kind, ENTITY, subject, event_key, on, stream_version, usd(amount))


def _post(
    ctx: BookContext,
    obligations: Sequence[ObligationState],
    flows: Iterable[ControlFlow],
    rates: Iterable[FxRateInput],
    inputs: PartInputs,
) -> tuple[FxState, PostingState]:
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    _producer_nodes(tb, inputs, ctx.txn_currency)
    costs = _Costs(allocated_state(obligations), FxFlows(tuple(flows)), inputs)
    fx = s12_fx_entities.run(ctx, costs, tb, rates=RateIndex(tuple(rates)))
    posting = s14_posting.run(ctx, fx, tb, posted=PostedIndex(()))
    trace = tb.build(root_measures={})
    assert reevaluate(trace) == {node.id: node.value for node in trace.nodes}
    return fx, posting


def _rows(parts: Iterable[PartTarget]) -> list[tuple[object, ...]]:
    return [
        (t.subject_key, t.part, t.component, t.period_key, t.amount_txn, t.amount_functional)
        for t in parts
    ]


def _full_mapping() -> AccountMappingInput:
    """One rule per E-01 role and per E-109 purpose, so every derived line resolves (T-REF-15)."""
    purposes = ("AP_SUPPLIER", "BILLING", "EQUITY", "INVENTORY", "INVESTMENTS", "UNAPPLIED_CASH")
    rules = [
        MappingRuleInput(role, purpose, None, None, None, None, f"{index}{offset}", {}, 0, 0)
        for index, role in enumerate(sorted(AccountRole), start=10)
        if role not in ("RETAINED_EARNINGS", "FINANCING_OBLIGATION")
        for offset, purpose in enumerate(purposes if role == "BILLING_CLEARING" else (None,))
    ]
    return AccountMappingInput("MAP-ALL@v1", bundles.ZERO_SHA256, tuple(rules))


def _chk_081(inputs: PartInputs) -> tuple[FxState, PostingState]:
    ctx = book_context(bundles.entity(months=3), currency="EUR")
    ctx = dataclasses.replace(
        ctx, currencies=bundles.currencies("EUR", "USD"), mapping=_full_mapping()
    )
    services = f"{CONTRACT_KEY}/S"
    flows = [_release(services, month, "1000.00") for month in (1, 2, 3)]
    invoice = ControlFlow(
        "BILLING",
        ENTITY,
        f"{CONTRACT_KEY}@{ENTITY}",
        f"{CONTRACT_KEY}/EV-000005",
        date(2026, 3, 31),
        5,
        usd("3000.00"),
        unconditional_date=date(2026, 3, 31),
    )
    rates = [
        *(
            _rate("average", date(2026, m, 1), r)
            for m, r in ((1, "1.1100"), (2, "1.1300"), (3, "1.1500"))
        ),
        *(_rate("closing", date(2026, m, 1), r) for m, r in ((1, "1.1200"), (2, "1.1400"))),
        _rate("spot", date(2026, 3, 31), "1.1600"),
    ]
    return _post(ctx, [_obligation("S"), _obligation("L")], [*flows, invoice], rates, inputs)


def test_s14_r01_part_targets_signed_cumulative() -> None:
    services = f"{CONTRACT_KEY}/S"
    relief = tuple(
        _target("revenue_relief_cum", services, month, 100000 * month) for month in (1, 2, 3)
    )
    by_cause = tuple(
        _target("revenue_relief", services, month, 100000, cause="NORMAL") for month in (1, 2, 3)
    )
    fx, posting = _chk_081(PartInputs(relief=relief, relief_by_cause=by_cause))
    assert posting.findings == ()
    assert posting.allocated is fx.allocated
    # Signed cumulative per (book, owner entity, subject, part) and period end, each with its stage
    # 12 functional amount: relief EUR at the layer and asset-layer amounts (CHK-081), JET-10a.
    assert _rows(posting.part_targets) == [
        (f"CG-1@{ENTITY}", "JET-10a", "CONTRACT_ASSET", "FY2026-P01", 0, 1000),
        (f"CG-1@{ENTITY}", "JET-10a", "CONTRACT_ASSET", "FY2026-P02", 0, 4000),
        (f"CG-1@{ENTITY}", "JET-10a", "CONTRACT_ASSET", "FY2026-P03", 0, 9000),
        (services, "JET-02 principal", None, "FY2026-P01", 100000, 111000),
        (services, "JET-02 principal", None, "FY2026-P02", 200000, 224000),
        (services, "JET-02 principal", None, "FY2026-P03", 300000, 339000),
    ]
    assert {
        (t.book_code, t.entity, t.txn_currency, t.functional_currency) for t in posting.part_targets
    } == {("ASC606", ENTITY, "EUR", "USD")}
    assert len({t.key for t in posting.part_targets}) == len(posting.part_targets)
    february = posting.part_targets[4]
    revenue_node = next(
        t.node_id
        for t in fx.functional_targets
        if t.subject_key == services and t.period_key == "FY2026-P02"
    )
    assert february.node_ids == (relief[1].node_id, revenue_node)
    assert february.by_cause == (("NORMAL", 200000),)
    assert [ref.rate_key for ref in february.rates] == [
        "EURUSD-AVERAGE-FY2026-P01",
        "EURUSD-AVERAGE-FY2026-P02",
    ]
    # A part amount that stage 12 converted differently, or never converted, fails closed.
    wrong = dataclasses.replace(relief[1], value=200001)
    with pytest.raises(EngineError) as mismatch:
        _chk_081(PartInputs(relief=(relief[0], wrong, relief[2])))
    assert (mismatch.value.code, mismatch.value.detail["rule"]) == (
        "ENGINE_INVARIANT_VIOLATED",
        "S14-R-01",
    )
    unconverted = _target("revenue_relief_cum", f"{CONTRACT_KEY}/L", 1, 5000)
    with pytest.raises(EngineError, match="no functional amount"):
        _chk_081(PartInputs(relief=(*relief, unconverted)))
    # The consumed state must carry the part inputs (integration after merge).
    ctx = book_context(bundles.entity(months=1))
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    fx_only = s12_fx_entities.run(ctx, _NoParts(allocated_state([]), FxFlows(())), tb)
    with pytest.raises(EngineError, match="no part inputs"):
        s14_posting.run(ctx, fx_only, tb)


def test_l8_e_jet_04b_nets_the_concession_of_its_own_component() -> None:
    """D-88 L7-5-Q-4 (2): stage 14 indexes the JET-05c created amounts by (entity, cause, period),
    and a CONCESSION JET-04b part nets where its subject (the component key) is that cause.
    Component A was created at 50.00 and holds 20.00 after a credit memo: JET-04b −30.00.
    Component B has no created amount of its own: JET-04b 30.00 unchanged. Relief cites the
    revenue node and the concession node (L7-5-Q-4 (1)). Before the fix the created amounts were
    keyed by obligation, which no component key equals, so nothing netted."""
    ctx = book_context(bundles.entity(months=2))
    p1 = f"{CONTRACT_KEY}/P1"
    a, b = (f"CG-1@{ENTITY}/CONCESSION/{CONTRACT_KEY}/EV-{n:06d}/{p1}" for n in (3, 4))
    flows = [_on_event("REVENUE", 2, date(2026, 1, 15), "1000.00", p1)]
    inputs = PartInputs(
        relief=(
            _target("revenue_relief_cum", p1, 1, 100000),
            _target("revenue_relief_cum", p1, 2, 100000),  # revenue 950.00 + concession 50.00
        ),
        relief_by_cause=(_target("revenue_relief", p1, 1, 100000, cause="NORMAL"),),
        refund_liabilities=(
            _target("refund_liability", a, 2, 2000, cause="CONCESSION"),
            _target("refund_liability", b, 2, 3000, cause="CONCESSION"),
        ),
        concessions=(_target("concession_created_cum", p1, 2, 5000, cause=a),),
    )
    _, posting = _post(ctx, [_obligation("P1")], flows, [], inputs)
    rows = [row for row in _rows(posting.part_targets) if row[1] in ("JET-04b", "JET-05c")]
    assert sorted(rows, key=str) == sorted(
        [
            (a, "JET-04b", "CONCESSION", "FY2026-P02", -3000, -3000),
            (b, "JET-04b", "CONCESSION", "FY2026-P02", 3000, 3000),
            (p1, "JET-05c", None, "FY2026-P02", 5000, 5000),
        ],
        key=str,
    )
    (february,) = [
        part
        for part in posting.part_targets
        if part.part == "JET-02 principal" and part.period_key == "FY2026-P02"
    ]
    assert february.value_inputs == (
        (f"revenue_relief_cum:{p1}:FY2026-P02", 1),
        (f"concession_created_cum:{p1}#{a}:FY2026-P02", 1),
    )


def test_s14_r02_jet_05b_through_revenue_relief() -> None:
    ctx = book_context(bundles.entity(months=2))
    p1 = f"{CONTRACT_KEY}/P1"
    component = f"CG-1@{ENTITY}/CONCESSION/{p1}"
    flows = [
        _on_event("REVENUE", 2, date(2026, 1, 15), "1000.00", p1),
        # Price change of 100.00 on satisfied performance settled through future pricing.
        _on_event("NEGATIVE_REVENUE", 3, date(2026, 2, 10), "100.00", p1),
    ]
    inputs = PartInputs(
        relief=(
            _target("revenue_relief_cum", p1, 1, 100000),
            _target("revenue_relief_cum", p1, 2, 90000),
        ),
        relief_by_cause=(
            _target("revenue_relief", p1, 1, 100000, cause="NORMAL"),
            _target("revenue_relief", p1, 2, -10000, cause="MODIFICATION"),
        ),
        # A concession settled by credit memo posts separately through JET-05c.
        # JET-04b nets it where the component key is the concession's cause (D-88 L7-5-Q-4 (2)).
        refund_liabilities=(_target("refund_liability", component, 2, 5000, cause="CONCESSION"),),
        concessions=(_target("concession_created_cum", p1, 2, 5000, cause=component),),
    )
    _, posting = _post(ctx, [_obligation("P1")], flows, [], inputs)
    assert _rows(posting.part_targets) == [
        # The credit settles the asset layer at rate 1: a JET-10a settlement difference of 0.00.
        (f"CG-1@{ENTITY}", "JET-10a", "CONTRACT_ASSET", "FY2026-P02", 0, 0),
        (component, "JET-04b", "CONCESSION", "FY2026-P02", 0, 0),
        (p1, "JET-02 principal", None, "FY2026-P01", 100000, 100000),
        (p1, "JET-02 principal", None, "FY2026-P02", 90000, 90000),
        (p1, "JET-05c", None, "FY2026-P02", 5000, 5000),
    ]
    assert "JET-05b" not in {t.part for t in posting.part_targets}
    assert JET_PARTS["JET-05b"].through == "JET-02 principal"
    january, february = posting.part_targets[2:4]
    assert february.by_cause == (("MODIFICATION", -10000), ("NORMAL", 100000))
    # The relief falls by 100.00: the derivation posts Dr REVENUE / Cr CONTRACT_LIABILITY (R4).
    movement = february.amount_txn - january.amount_txn
    lines = role_lines(JET_PARTS["JET-02 principal"], movement, movement)
    assert [(line.account_role, line.side, line.amount_txn) for line in lines] == [
        (CL, "C", 10000),
        ("REVENUE", "D", 10000),
    ]
    jet_05b = JET_PARTS["JET-05b"]
    assert jet_05b.debit is not None and jet_05b.credit is not None
    assert {line.side: line.account_role for line in lines} == {
        "D": jet_05b.debit.labels[0],
        "C": jet_05b.credit.labels[0],
    }
    concession = role_lines(JET_PARTS["JET-05c"], 5000, 5000)
    assert [(line.account_role, line.side) for line in concession] == [
        ("REVENUE", "D"),
        ("REFUND_LIABILITY", "C"),
    ]


def test_s14_r03_expiry_through_jet_02() -> None:
    ctx = book_context(bundles.entity(months=3))
    credits, option = f"{CONTRACT_KEY}/CREDITS", f"{CONTRACT_KEY}/MR"
    flows = [
        _release(credits, 1, "400.00"),
        _release(credits, 2, "400.00"),
        _on_event("REVENUE", 2, date(2026, 2, 15), "10.71", option),  # MATERIAL_RIGHT_EXPIRED
        _release(credits, 3, "150.00"),  # prepaid-credit lapse at the end date (S09-R-22)
    ]
    inputs = PartInputs(
        relief=(
            _target("revenue_relief_cum", credits, 1, 40000),
            _target("revenue_relief_cum", credits, 2, 80000),
            _target("revenue_relief_cum", credits, 3, 95000),
            _target("revenue_relief_cum", option, 2, 1071),
            _target("revenue_relief_cum", option, 3, 1071),
        ),
        relief_by_cause=(
            _target("revenue_relief", credits, 1, 40000, cause="NORMAL"),
            _target("revenue_relief", credits, 2, 40000, cause="NORMAL"),
            _target("revenue_relief", credits, 3, 15000, cause="NORMAL"),
            _target("revenue_relief", option, 2, 1071, cause="NORMAL"),
        ),
        # A − C_total at expiry moves to the UNCLAIMED_PROPERTY component (S09-R-28).
        refund_liabilities=(
            _target("refund_liability", credits, 3, 5000, cause="UNCLAIMED_PROPERTY"),
        ),
    )
    _, posting = _post(
        ctx, [_obligation("CREDITS", "1000.00"), _obligation("MR", "10.71")], flows, [], inputs
    )
    assert {t.part for t in posting.part_targets} == {"JET-02 principal", "JET-04b"}
    rows = {(t.subject_key, t.part, t.period_key): t for t in posting.part_targets}
    lapse = rows[(credits, "JET-02 principal", "FY2026-P03")]
    assert (lapse.amount_txn, lapse.by_cause) == (95000, (("NORMAL", 95000),))
    expiry = rows[(option, "JET-02 principal", "FY2026-P02")]
    assert (expiry.amount_txn, expiry.by_cause) == (1071, (("NORMAL", 1071),))
    assert JET_PARTS["JET-08 expiry"].through == "JET-02 principal"
    assert amount_class("JET-02 principal", "MATERIAL_RIGHT_EXPIRED") == AmountClass("EVENT", None)
    unclaimed = rows[(credits, "JET-04b", "FY2026-P03")]
    assert (unclaimed.component, unclaimed.amount_txn, unclaimed.amount_functional) == (
        "UNCLAIMED_PROPERTY",
        5000,
        5000,
    )
    lines = role_lines(JET_PARTS["JET-04b"], unclaimed.amount_txn, unclaimed.amount_functional)
    assert [(line.account_role, line.side, line.amount_txn) for line in lines] == [
        (CL, "D", 5000),
        ("REFUND_LIABILITY", "C", 5000),
    ]


def _sides(lines: Sequence[RoleLine]) -> list[tuple[str, str | None, str, int, int]]:
    assert sum(line.signed_txn for line in lines) == 0
    assert sum(line.signed_functional for line in lines) == 0
    assert all(line.amount_txn >= 0 and line.amount_functional >= 0 for line in lines)
    return [
        (
            line.account_role,
            line.clearing_purpose,
            line.side,
            line.amount_txn,
            line.amount_functional,
        )
        for line in lines
    ]


def test_jet_r4_negative_effect_swaps_sides() -> None:
    principal = JET_PARTS["JET-02 principal"]
    assert _sides(role_lines(principal, 5000, 5500)) == [
        (CL, None, "D", 5000, 5500),
        ("REVENUE", None, "C", 5000, 5500),
    ]
    assert _sides(role_lines(principal, -5000, -5500)) == [
        (CL, None, "C", 5000, 5500),
        ("REVENUE", None, "D", 5000, 5500),
    ]
    # JET-12 release: Dr LOSS_PROVISION / Cr LOSS_EXPENSE (POLICIES JET-12 "Release").
    assert _sides(role_lines(JET_PARTS["JET-12"], -3000000, -3000000)) == [
        ("LOSS_EXPENSE", None, "C", 3000000, 3000000),
        ("LOSS_PROVISION", None, "D", 3000000, 3000000),
    ]
    # JET-10d: a gain on consideration payable swaps to Dr CONSIDERATION_PAYABLE / Cr FX_GAIN_LOSS
    # (CHK-084 (c)); a loss on the refund liability is Dr FX_GAIN_LOSS / Cr REFUND_LIABILITY.
    jet_10d = JET_PARTS["JET-10d"]
    assert _sides(role_lines(jet_10d, 0, -50000, subject_role="CONSIDERATION_PAYABLE")) == [
        ("FX_GAIN_LOSS", None, "C", 0, 50000),
        ("CONSIDERATION_PAYABLE", None, "D", 0, 50000),
    ]
    assert _sides(role_lines(jet_10d, 0, 600, subject_role="REFUND_LIABILITY")) == [
        ("FX_GAIN_LOSS", None, "D", 0, 600),
        ("REFUND_LIABILITY", None, "C", 0, 600),
    ]
    # A split credit apportions with largest_remainder and swaps as a whole (S14-R-01; EX-14-A).
    weights = {"REVENUE": Fraction(3), "BILLING_CLEARING:AP_SUPPLIER": Fraction(17)}
    assert _sides(role_lines(JET_PARTS["JET-02 agent"], -33334, -33334, weights=weights)) == [
        (CL, None, "C", 33334, 33334),
        ("REVENUE", None, "D", 5000, 5000),
        ("BILLING_CLEARING", "AP_SUPPLIER", "D", 28334, 28334),
    ]
    # Intercompany roles carry the counterparty (R3); templates without lines refuse.
    pair = role_lines(JET_PARTS["JET-13 contracting"], 2000000, 2000000, counterparty_entity="UK01")
    assert [(line.account_role, line.counterparty_entity) for line in pair] == [
        (CL, None),
        ("INTERCOMPANY_DUE_TO", "UK01"),
    ]
    with pytest.raises(ValueError, match="counterparty"):
        role_lines(JET_PARTS["JET-13 performing"], 100, 100)
    with pytest.raises(ValueError, match="no lines"):
        role_lines(JET_PARTS["JET-07a"], 100, 100)
    with pytest.raises(ValueError, match="split side"):
        role_lines(JET_PARTS["JET-02 agent"], 100, 100)
