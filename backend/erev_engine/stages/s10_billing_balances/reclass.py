"""Stage 10 receivables, contra, presentation split and reclass attribution (ENC-13, ENC-14).

ENGINE_SPEC_B §10.2.6 and §10.2.7 (S10-R-18 to S10-R-23); POLICIES ALG-02 steps 1 to 6, ALG-03,
JET-04c and JET-06. In ``ENGINE`` mode the receivable contra of a member contract is round(B_u × κ),
with κ the ``rate`` of the APPROVED ``IMPLICIT_PRICE_CONCESSION`` version in force, else (stated
consideration − ``expected_total_amount``) ÷ stated consideration (S10-R-18; CHK-138). Accounts
receivable are the unconditional invoices including tax, less credit memos and cash payments
applied to the named invoices, else to open invoices by ascending (issue date, invoice number)
(S10-R-19). Neither exists in ``ERP`` mode (S10-INV-06). A credit position is presented as contract
liability; a debit position D = −NP is an unbilled receivable up to U = Σ max(0, R_p − B_p) over the
obligations whose right is unconditional, and a contract asset for the rest (S10-R-20;
S10-INV-01). R_p is the revenue relief of the obligation plus the net JET-11 accretion attributed
to it by posted allocation, then resolved SSP (D-76); B_p is its billing that enters the position
and is unconditional by the period end. ``right_class`` derives ALG-03 table 2.4-A from the data
the model holds unless POL-122 is set at product, contract or obligation level (S10-R-21).

The reclass attribution follows POL-121 at each period end (ALG-02 step 5). Under
``POB_DEBIT_POSITIONS`` UR is apportioned over the unconditional obligations by max(0, R_p − B_p)
and CA over the conditional ones by the same weights, then by posted allocation, over every
obligation by posted allocation, and by resolved SSP. Under ``CUMULATIVE_SSP_DELIVERED`` D is
apportioned over the non-VC obligations by cumulative SSP delivered, cumulative revenue, posted
allocation, then resolved SSP, and each share is presented by the obligation's class, so UR and CA
are the sums of the shares (DEV-057, DEV-058; L2-4-Q-22). Each obligation's
``netting_reclass_amount`` is a trace node per period and at ``-`` (the period containing the
version date); its exact value is the quota before largest remainder (Table 0.9-A; S10-R-22). Every
non-zero part gives a JET-06 target: a presentation-role debit with a paired ``CONTRACT_LIABILITY``
credit on the same obligation string at the period end, and its reversal on the next day with
``reason_code = RECLASS_REVERSAL``. Member-contract balances sum the attributions of the member's
obligations and apportion the contract liability by max(0, Σ (B_p − R_p)) (S10-R-23). Every value
comes from a registered formula (DG-KRN-EXP-04). Standard library only (DG-ARC-02).

A contracting entity none of whose periods from the group's inception period lies inside its
horizon — a contract booked ahead of the entity's open periods — has no period end to present
(C-05 rev 1.100): no target, entry or member balance, and each of its obligations the version-date
``netting_reclass_amount`` of zero with a node of ``NO_PERIOD_FORMULA`` (S10-R-22 rev 1.100).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import money
from erev_engine.bundle import EstimateVersionInput, PeriodInput, ResolvedPolicyInput
from erev_engine.errors import EngineError
from erev_engine.formulas import rational_param
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.s10_billing_balances import billing, classification
from erev_engine.stages.s10_billing_balances.billing import (
    BalanceMeasures,
    Billed,
    BillingDocumentOut,
)
from erev_engine.stages.s10_billing_balances.classification import ENGINE, INVOICE, Line, Receipt
from erev_engine.stages.s10_billing_balances.position import (
    EXPENSE_CAUSE,
    FINANCING_MEASURE,
    INCOME_CAUSE,
    PositionComponents,
    Positions,
    latest_target,
    series,
)
from erev_engine.stages.state import (
    AllocatedState,
    AllocationSegment,
    BookContext,
    ContractView,
    EventView,
    ObligationState,
    OrderKey,
    Target,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "ACCRETION_FORMULA",
    "AR_FORMULA",
    "ATTRIBUTION_POLICY",
    "CONDITIONAL",
    "CONTRACT_ASSET",
    "CONTRACT_LIABILITY",
    "CONTRA_FORMULA",
    "CUMULATIVE_SSP_DELIVERED",
    "NETTING_RECLASS",
    "NETTING_RECLASS_REVERSAL",
    "NO_PERIOD_FORMULA",
    "POB_DEBIT_FORMULA",
    "POB_DEBIT_POSITIONS",
    "RECLASS_REVERSAL",
    "SPLIT_FORMULA",
    "SSP_DELIVERED_FORMULA",
    "UNBILLED_RECEIVABLE",
    "UNCONDITIONAL",
    "Presentation",
    "ReclassAttribution",
    "ReclassEntry",
    "accounts_receivable",
    "present",
    "receivable_contra",
    "revenue_date",
    "right_class",
    "ssp_delivered_cum",
    "version_measures",
]

SPLIT_FORMULA: Final = "pos.split_ca_ur.v1"
CONTRA_FORMULA: Final = "pos.receivable_contra.v1"
AR_FORMULA: Final = "bil.ar_balance.v1"
ACCRETION_FORMULA: Final = "pos.accretion_attribution.v1"
POB_DEBIT_FORMULA: Final = "pos.reclass_attribution.pob_debit_positions.v1"
SSP_DELIVERED_FORMULA: Final = "pos.reclass_attribution.cumulative_ssp_delivered.v1"
NO_PERIOD_FORMULA: Final = "pos.reclass_attribution.no_measured_period.v1"  # C-05 rev 1.100
RIGHT_POLICY: Final = "balance.right_to_consideration"  # POL-122
ATTRIBUTION_POLICY: Final = "position.reclass_attribution_key"  # POL-121
POB_DEBIT_POSITIONS: Final = "POB_DEBIT_POSITIONS"
CUMULATIVE_SSP_DELIVERED: Final = "CUMULATIVE_SSP_DELIVERED"
CONDITIONAL: Final = "CONDITIONAL"
UNCONDITIONAL: Final = "UNCONDITIONAL"
UNBILLED_RECEIVABLE: Final = "UNBILLED_RECEIVABLE"  # 04 E-01 account roles
CONTRACT_ASSET: Final = "CONTRACT_ASSET"
CONTRACT_LIABILITY: Final = "CONTRACT_LIABILITY"
NETTING_RECLASS: Final = "NETTING_RECLASS"  # ENGINE_SPEC_B table 14-A entry kinds
NETTING_RECLASS_REVERSAL: Final = "NETTING_RECLASS_REVERSAL"
RECLASS_REVERSAL: Final = "RECLASS_REVERSAL"  # JET-06 reversal reason code
# ALG-03 table 2.4-A row 1: right to invoice, usage billed in arrears, royalties on occurred sales.
UNCONDITIONAL_METHODS: Final = frozenset({"RIGHT_TO_INVOICE", "USAGE", "ROYALTY"})
_OVERRIDE_LEVELS: Final = frozenset({"O", "P", "C"})  # POL-122 levels P, O; contract overrides
_IMPLICIT_PRICE_CONCESSION: Final = "IMPLICIT_PRICE_CONCESSION"
_BILLED_UNCONDITIONAL: Final = "billed_unconditional_cum"
_SPLIT_MEASURES: Final = (
    ("contract_liability", "cl"),
    ("contract_asset", "ca"),
    ("unbilled_receivable", "ur"),
)
# Measure events that move revenue carry its date; billing, credit memos and receipts do not.
_NOT_REVENUE_EVENTS: Final = frozenset(
    {"BILLING_RECORDED", "CREDIT_MEMO_RECORDED", "PAYMENT_RECEIVED"}
)
_QUANTITY_SIGN: Final[Mapping[str, int]] = MappingProxyType(
    {"DELIVERY_RECORDED": 1, "RETURN_RECORDED": -1}
)


@dataclass(frozen=True, slots=True)
class ReclassAttribution:
    """One obligation's share of the period-end netting reclass (T-CON-11; S10-R-22; CHK-117)."""

    subject_key: str  # obligation
    contract_key: str
    entity: str  # contracting entity
    period_key: str | None  # None: the version-state node at "-"
    as_of: date  # the period end whose reclass is attributed
    receivable: int  # UNBILLED_RECEIVABLE part, minor units
    asset: int  # CONTRACT_ASSET part, minor units
    exact: Fraction  # quota before largest remainder, currency units (Table 0.9-A)
    role: str | None  # netting_reclass_role: the role of the larger part, None when 0
    revenue_date: date  # effective date of the latest revenue event (CHK-117; B3-AK-09)
    node_id: str

    @property
    def amount(self) -> int:
        """``netting_reclass_amount``: both parts, minor units."""
        return self.receivable + self.asset


@dataclass(frozen=True, slots=True)
class ReclassEntry:
    """A JET-06 target: the reclass debits a presentation role and credits ``CONTRACT_LIABILITY``
    on the same obligation string; its reversal swaps the sides on the next day."""

    kind: str  # NETTING_RECLASS | NETTING_RECLASS_REVERSAL (table 14-A)
    subject_key: str  # obligation string of both lines
    entity: str
    period_key: str  # the period t whose reclass is posted or reversed
    posting_date: date  # last day of t; first day of t + 1 for the reversal
    debit_role: str
    credit_role: str
    amount: int  # > 0, minor units
    reason_code: str | None  # RECLASS_REVERSAL on the reversal
    node_id: str  # the netting_reclass_amount node


@dataclass(frozen=True, slots=True)
class Presentation:
    """Presented balances, reclass attributions and member balances of one book (§10.1)."""

    targets: tuple[Target, ...]  # contract_liability, contract_asset, unbilled_receivable
    accretion: tuple[Target, ...]  # accretion_attributed_cum per obligation and period (S10-R-20)
    rights: Mapping[tuple[str, str], str]  # (obligation, period key) -> CONDITIONAL | UNCONDITIONAL
    reclass: tuple[ReclassAttribution, ...] = ()  # per obligation and period (ENC-14)
    version_reclass: tuple[ReclassAttribution, ...] = ()  # per obligation at "-"
    entries: tuple[ReclassEntry, ...] = ()  # JET-06 reclass and reversal targets
    members: tuple[Target, ...] = ()  # T-CON-09 balances per "<contract>@<entity>" (S10-R-23)


@dataclass(frozen=True, slots=True)
class _Point:
    """The inputs of one (group, contracting entity) period end."""

    period: PeriodInput
    parts: PositionComponents
    relief: Mapping[str, int]  # R_p: revenue relief plus attributed accretion (S10-R-20)
    revenue: Mapping[str, int]  # revenue relief without accretion (the parity revenue weight)
    billed: Mapping[str, int]  # B_p
    classes: Mapping[str, str]  # ALG-03 class per obligation

    @property
    def debit(self) -> int:
        return max(0, -self.parts.net_position)


@dataclass(frozen=True, slots=True)
class _Plan:
    """The attribution of one period end under POL-121 (ALG-02 steps 3 and 5)."""

    formula_id: str
    receivable: int  # UR
    asset: int  # CA
    parts: Mapping[str, tuple[int, int]]  # obligation -> (UR part, CA part)
    exact: Mapping[str, Fraction]  # obligation -> exact quota, currency units
    params: Mapping[str, str]  # node params other than as_of and key


def _invariant(message: str, subject_key: str | None, **detail: str) -> EngineError:
    return EngineError("ENGINE_INVARIANT_VIOLATED", message, subject_key=subject_key, detail=detail)


def _narrative(formula_id: str) -> str:
    return formula_id.rsplit(".v", 1)[0]


def _override(ctx: BookContext, ob: ObligationState) -> ResolvedPolicyInput | None:
    """The most specific POL-122 value present for ``ob``, or None when the bundle holds none."""
    by_scope = {
        (policy.scope, policy.subject_key): policy
        for policy in ctx.policies.all()
        if policy.code == RIGHT_POLICY
    }
    for scope in (
        ("OBLIGATION", ob.subject_key),
        ("CONTRACT", ob.contract_key),
        ("ENTITY", ob.contracting_entity),
        ("GROUP", ""),
    ):
        found = by_scope.get(scope)
        if found is not None:
            return found
    return None


def right_class(
    ctx: BookContext,
    contract: ContractView,
    ob: ObligationState,
    obligations: Sequence[ObligationState],
    t: date,
) -> str:
    """ALG-03 class of ``ob`` at ``t`` (§10.2.7 ``right_class``; S10-R-21; POL-122 CV-17)."""
    found = _override(ctx, ob)
    if found is not None and found.level in _OVERRIDE_LEVELS:
        if found.value not in (CONDITIONAL, UNCONDITIONAL):
            raise _invariant(
                "the right-to-consideration value is unknown", ob.subject_key, rule="S10-R-21"
            )
        return str(found.value)
    header = contract.header
    if header.termination_party in ("CUSTOMER", "BOTH") and header.termination_has_penalty is False:
        return CONDITIONAL  # table 2.4-A row 5
    method = str(ob.recognition_method)
    if method in UNCONDITIONAL_METHODS:
        return UNCONDITIONAL
    if method == "POINT_IN_TIME":
        nonzero = [
            other.subject_key
            for other in obligations
            if other.contract_key == ob.contract_key
            and other.contracting_entity == ob.contracting_entity
            and billing.posted_allocation(other, t) != 0
        ]
        if nonzero == [ob.subject_key]:
            return UNCONDITIONAL  # row 3: payment cannot depend on another obligation
    return CONDITIONAL


def _kappa(version: EstimateVersionInput, stated: Fraction, contract_key: str) -> Fraction:
    """κ of S10-R-18 from the version in force (ENGINE_SPEC S04-R-09)."""
    if version.rate is not None:
        kappa = money.to_fraction(version.rate)
    elif version.expected_total_amount is not None and stated != 0:
        kappa = (stated - money.to_fraction(version.expected_total_amount)) / stated
    elif version.constrained_amount is not None and stated != 0:  # D-87 L6-5-Q-12 (ii)
        kappa = money.to_fraction(version.constrained_amount) / stated
    else:
        raise _invariant(
            "an implicit price concession has no rate and no expected total",
            contract_key,
            rule="S10-R-18",
            version_key=version.version_key,
        )
    if not 0 <= kappa <= 1:
        raise _invariant(
            "an implicit price concession rate lies outside [0, 1]",
            contract_key,
            rule="S10-R-18",
            version_key=version.version_key,
        )
    return kappa


def receivable_contra(
    ctx: BookContext, recognition: RecognitionState, billed: Billed, tb: TraceBuilder
) -> tuple[Target, ...]:
    """``receivable_contra:<contract>@<entity>:<period>`` in ``ENGINE`` mode (S10-R-18; JET-04c)."""
    st = recognition.allocated
    mu = classification.minor_unit(ctx)
    scale: int = 10**mu
    unconditional = {
        (target.subject_key, target.period_key): target
        for target in billed.targets
        if target.measure == _BILLED_UNCONDITIONAL
    }
    out: list[Target] = []
    for contract in sorted(st.contracts, key=lambda view: view.header.external_id):
        contract_key = contract.header.external_id
        keys = [
            key
            for key in st.estimates.of_contract(contract_key)  # CV-21 encoded lookup
            if any(
                pin.version.estimate_kind == _IMPLICIT_PRICE_CONCESSION
                for pin in st.estimates.pins[key]
            )
        ]
        if not keys:
            continue
        entity = contract.header.contracting_entity_code
        stated = sum(
            (
                ob.stated_price
                for ob in st.obligations
                if ob.contract_key == contract_key
                and ob.contracting_entity == entity
                and not billing.is_vc_line(ob)
            ),
            Fraction(0),
        )
        subject_key = contract_entity_subject_key(contract_key, entity)
        for period in billing.periods(ctx, st, entity):
            t = period.end_date
            billed_target = unconditional.get((subject_key, period.period_key))
            if billed_target is None or classification.mode_at(ctx, contract, t) != ENGINE:
                continue
            versions = [
                version
                for version in (st.estimates.pin(key, t) for key in keys)
                if version is not None
            ]
            version = max(
                versions, key=lambda item: (item.effective_date, item.version_no), default=None
            )
            params = {"as_of": t.isoformat()}
            kappa = Fraction(0)
            if version is not None:
                kappa = _kappa(version, stated, contract_key)
                params["version_key"] = version.version_key
            params["kappa"] = rational_param(kappa)
            value = money.round_half_up(Fraction(billed_target.value, scale) * kappa, mu)
            node_id = tb.node(
                measure="receivable_contra",
                subject_key=subject_key,
                period_key=period.period_key,
                value=value,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=CONTRA_FORMULA,
                inputs=[billed_target.node_id],
                params=params,
                narrative_key=_narrative(CONTRA_FORMULA),
            )
            out.append(
                Target(
                    ctx.book_code,
                    entity,
                    subject_key,
                    "receivable_contra",
                    period.period_key,
                    None,
                    value,
                    None,
                    node_id,
                )
            )
    return tuple(out)


def _apply(
    open_amounts: dict[str, int], issued: Mapping[str, date], named: Sequence[str], amount: int
) -> int:
    """Apply ``amount`` to the named open invoices, else to open invoices by ascending (issue date,
    invoice number); returns the amount applied (S10-R-19)."""
    order = (
        [number for number in named if number in open_amounts]
        if named
        else sorted(open_amounts, key=lambda number: (issued[number], number))
    )
    left = amount
    for number in order:
        if left == 0:
            break
        take = min(open_amounts[number], left)
        open_amounts[number] -= take
        left -= take
    return amount - left


def _receivable_at(
    documents: Sequence[BillingDocumentOut], receipts: Sequence[Receipt], t: date, mu: int
) -> tuple[int, list[str | SourceRef]]:
    """AR at ``t`` and the signed source references it sums (S10-R-19)."""
    flows: list[tuple[date, int, OrderKey, Line | Receipt]] = []
    for document in documents:
        for line in document.lines:
            if line.mode != ENGINE or not line.in_position:
                continue
            if line.kind == INVOICE:
                if line.unconditional_date is not None and line.unconditional_date <= t:
                    flows.append((line.unconditional_date, 0, line.event.order_key, line))
            elif line.event.effective_date <= t:
                flows.append((line.event.effective_date, 1, line.event.order_key, line))
    for receipt in receipts:
        if receipt.event.effective_date <= t:
            flows.append((receipt.event.effective_date, 1, receipt.event.order_key, receipt))
    open_amounts: dict[str, int] = {}
    issued: dict[str, date] = {}
    refs: list[str | SourceRef] = []

    def cite(event_key: str, member: str, amount: int) -> None:
        detail = {"member": member, "value": money.format_money(amount, mu)}
        refs.append(SourceRef("contract_event", event_key, detail))

    for _, _, _, item in sorted(flows, key=lambda flow: (flow[0], flow[1], flow[2])):
        if isinstance(item, Receipt):
            applied = _apply(open_amounts, issued, item.applied_invoice_numbers, item.amount)
            if applied:
                cite(item.event.event_key, "applied", -applied)
        elif item.kind == INVOICE:
            total = item.amount + item.tax_amount
            open_amounts[item.number] = open_amounts.get(item.number, 0) + total
            issued.setdefault(item.number, item.event.effective_date)
            cite(item.event.event_key, "invoice_total", total)
        else:
            named = () if item.credited_invoice_number is None else (item.credited_invoice_number,)
            applied = _apply(open_amounts, issued, named, item.amount)
            if applied:
                cite(item.event.event_key, "credited", -applied)
    return sum(open_amounts.values()), refs


def accounts_receivable(
    ctx: BookContext,
    recognition: RecognitionState,
    billed: Billed,
    receipts: Sequence[Receipt],
    tb: TraceBuilder,
) -> tuple[Target, ...]:
    """``accounts_receivable:<contract>@<entity>:<period>`` in ``ENGINE`` mode (S10-R-19)."""
    st = recognition.allocated
    mu = classification.minor_unit(ctx)
    out: list[Target] = []
    for contract in sorted(st.contracts, key=lambda view: view.header.external_id):
        contract_key = contract.header.external_id
        entity = contract.header.contracting_entity_code
        subject_key = contract_entity_subject_key(contract_key, entity)
        documents = [
            document for document in billed.documents if document.contract_key == contract_key
        ]
        cash = [
            receipt
            for receipt in receipts
            if receipt.contract_key == contract_key and receipt.form == "CASH"
        ]
        for period in billing.periods(ctx, st, entity):
            t = period.end_date
            if classification.mode_at(ctx, contract, t) != ENGINE:
                continue
            value, refs = _receivable_at(documents, cash, t, mu)
            node_id = tb.node(
                measure="accounts_receivable",
                subject_key=subject_key,
                period_key=period.period_key,
                value=value,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=AR_FORMULA,
                inputs=refs,
                params={"as_of": t.isoformat()},
                narrative_key=_narrative(AR_FORMULA),
            )
            out.append(
                Target(
                    ctx.book_code,
                    entity,
                    subject_key,
                    "accounts_receivable",
                    period.period_key,
                    None,
                    value,
                    None,
                    node_id,
                )
            )
    return tuple(out)


def _accretion(
    ctx: BookContext,
    st: AllocatedState,
    tb: TraceBuilder,
    financing: Mapping[tuple[str, str], Sequence[tuple[date, Target]]],
    own: Sequence[ObligationState],
    period: PeriodInput,
    mu: int,
    out: list[Target],
) -> dict[str, int]:
    """``accretion_attributed`` of §10.2.7: the net JET-11 accretion of each member contract by
    posted allocation, then resolved SSP, over its obligations (S10-R-20; L2-4-Q-18)."""
    shares_by: dict[str, int] = {}
    t = period.end_date
    for contract_key in sorted({ob.contract_key for ob in own}):
        entity = own[0].contracting_entity
        interest = latest_target(
            financing.get(
                (FINANCING_MEASURE, contract_entity_subject_key(contract_key, entity)), ()
            ),
            t,
        )
        if interest is None or interest.value == 0:
            continue
        # Stage 04 names the schedule kind: DEFERRED is JET-11a, ADVANCE is JET-11b (L4-3-Q-18).
        if interest.cause in (INCOME_CAUSE, "DEFERRED"):
            sign, net = "+", interest.value
        elif interest.cause in (EXPENSE_CAUSE, "ADVANCE"):
            sign, net = "-", -interest.value
        else:
            raise _invariant(
                "a financing target names no JET-11 part",
                interest.subject_key,
                rule="S10-R-10",
                cause=str(interest.cause),
            )
        carriers = [
            ob for ob in own if ob.contract_key == contract_key and not billing.is_vc_line(ob)
        ]
        keys = [ob.subject_key for ob in carriers]
        weights = [Fraction(max(0, billing.posted_allocation(ob, t))) for ob in carriers]
        if sum(weights, Fraction(0)) == 0:
            weights = [ob.resolved_ssp for ob in carriers]
        if not keys or sum(weights, Fraction(0)) <= 0:
            continue  # no obligation carries the adjustment: nothing to attribute
        params = {
            "as_of": t.isoformat(),
            "keys": "|".join(keys),
            "signs": sign,
            "weights": "|".join(rational_param(weight) for weight in weights),
        }
        for subject_key, share in zip(
            keys, money.largest_remainder(net, weights, keys), strict=True
        ):
            node_id = tb.node(
                measure="accretion_attributed_cum",
                subject_key=subject_key,
                period_key=period.period_key,
                value=share,
                currency=ctx.txn_currency,
                minor_unit=mu,
                formula_id=ACCRETION_FORMULA,
                inputs=[interest.node_id],
                params={**params, "key": subject_key},
                narrative_key=_narrative(ACCRETION_FORMULA),
            )
            shares_by[subject_key] = shares_by.get(subject_key, 0) + share
            out.append(
                Target(
                    ctx.book_code,
                    entity,
                    subject_key,
                    "accretion_attributed_cum",
                    period.period_key,
                    None,
                    share,
                    None,
                    node_id,
                )
            )
    return shares_by


def _concerns(ev: EventView, ob: ObligationState) -> bool:
    """The event names the obligation, by subject key or by its payload ``obligation_key``."""
    if ob.subject_key in ev.obligation_subject_keys:
        return True
    return ev.contract_key == ob.contract_key and ev.payload.get("obligation_key") == (
        ob.obligation_key
    )


def _segment_at_position(
    st: AllocatedState, ob: ObligationState, ev: EventView
) -> AllocationSegment | None:
    """The ``FIXED`` segment in force at the ENG-06 position of ``ev`` (CV-20, CV-60)."""
    boundaries = {item.event_key: item.order_key for item in st.events}
    found: AllocationSegment | None = None
    for seg in ob.segments:
        if seg.component != "FIXED" or seg.effective_date > ev.effective_date:
            continue
        if seg.event_key is not None:
            boundary = boundaries.get(seg.event_key)
            if boundary is None:
                raise _invariant(
                    "the boundary event of a segment is absent", ob.subject_key, rule="CV-60"
                )
            if boundary > ev.order_key:
                continue
        found = seg
    return found


def ssp_delivered_cum(st: AllocatedState, ob: ObligationState, t: date) -> Fraction:
    """Cumulative SSP delivered through ``t``: each delivery less each return at the unit SSP of the
    segment in force at its position (legacy 02 §3.8; S09-R-47; L2-4-Q-4)."""
    total = Fraction(0)
    for ev in st.measure_events:
        sign = _QUANTITY_SIGN.get(ev.event_type)
        if sign is None or ev.effective_date > t or not _concerns(ev, ob):
            continue
        raw = ev.payload.get("quantity")
        if isinstance(raw, bool) or raw is None:
            raise _invariant(
                "a measure event carries no quantity",
                ob.subject_key,
                rule="CV-45",
                event_key=ev.event_key,
            )
        seg = _segment_at_position(st, ob, ev)
        unit = Fraction(0) if seg is None or seg.unit_ssp is None else seg.unit_ssp
        total += sign * money.to_fraction(raw) * unit  # type: ignore[arg-type]
    return total


def revenue_date(st: AllocatedState, ob: ObligationState, t: date) -> date:
    """The effective date of the latest revenue event of ``ob`` through ``t`` (CHK-117; B3-AK-09):
    measure events other than billing, credit memos and receipts, boundaries of its segments, and
    the passage of time of a time-elapsed segment; ``t`` when none (L2-4-Q-27)."""
    found = [
        ev.effective_date
        for ev in st.measure_events
        if ev.effective_date <= t and ev.event_type not in _NOT_REVENUE_EVENTS and _concerns(ev, ob)
    ]
    for seg in ob.segments:
        if seg.effective_date > t:
            continue
        if seg.event_key is not None:
            found.append(seg.effective_date)
        start, end = seg.totals.start_date, seg.totals.end_date
        if seg.progress_measure == "TIME_ELAPSED" and start is not None and start <= t:
            found.append(t if end is None else min(t, end))
    return max(found, default=t)


def _asset_pool(
    own: Sequence[ObligationState], point: _Point, unconditional: Sequence[str]
) -> tuple[list[str], list[Fraction], str]:
    """The ALG-02 step 5 ``POB_DEBIT_POSITIONS`` chain for CA: conditional obligations by max(0,
    R_p − B_p), then by posted allocation; every obligation by posted allocation, then resolved
    SSP (positive by POL-077)."""
    t = point.period.end_date
    everyone = [ob.subject_key for ob in own]
    by_key = {ob.subject_key: ob for ob in own}
    conditional = [key for key in everyone if key not in set(unconditional)]
    chain: tuple[tuple[str, list[str], Callable[[str], Fraction]], ...] = (
        ("positions", conditional, lambda k: Fraction(max(0, point.relief[k] - point.billed[k]))),
        (
            "allocation",
            conditional,
            lambda k: Fraction(max(0, billing.posted_allocation(by_key[k], t))),
        ),
        (
            "allocation_all",
            everyone,
            lambda k: Fraction(max(0, billing.posted_allocation(by_key[k], t))),
        ),
        ("resolved_ssp", everyone, lambda k: max(Fraction(0), by_key[k].resolved_ssp)),
    )
    for basis, keys, weigh in chain:
        weights = [weigh(key) for key in keys]
        if keys and sum(weights, Fraction(0)) > 0:
            return keys, weights, basis
    raise _invariant(
        "the contract asset has no obligation to attribute to",
        point.parts.subject_key,
        rule="S10-R-22",
        period_key=point.period.period_key,
    )


def _pob_debit_plan(own: Sequence[ObligationState], point: _Point, mu: int) -> _Plan:
    """ALG-02 steps 3 and 5 under ``POB_DEBIT_POSITIONS`` (CHK-010)."""
    scale: int = 10**mu
    debit = point.debit
    unconditional = [ob.subject_key for ob in own if point.classes[ob.subject_key] == UNCONDITIONAL]
    ur_weights = [max(0, point.relief[key] - point.billed[key]) for key in unconditional]
    receivable = min(debit, sum(ur_weights))
    asset = debit - receivable
    parts = {ob.subject_key: [0, 0] for ob in own}
    exact = {ob.subject_key: Fraction(0) for ob in own}
    params = {
        "relief": "",
        "billed": "",
        "ur_keys": "",
        "ca_keys": "",
        "ca_weights": "",
        "ca_basis": "none",
    }
    if debit:
        params["relief"] = "|".join(str(point.relief[key]) for key in unconditional)
        params["billed"] = "|".join(str(point.billed[key]) for key in unconditional)
        params["ur_keys"] = "|".join(unconditional)
    if receivable:
        weights = [Fraction(weight) for weight in ur_weights]
        total = sum(weights, Fraction(0))
        shares = money.largest_remainder(receivable, weights, unconditional)
        for key, share, weight in zip(unconditional, shares, weights, strict=True):
            parts[key][0] = share
            exact[key] += Fraction(receivable, scale) * weight / total
    if asset:
        keys, weights, basis = _asset_pool(own, point, unconditional)
        total = sum(weights, Fraction(0))
        params["ca_keys"] = "|".join(keys)
        params["ca_weights"] = "|".join(rational_param(weight) for weight in weights)
        params["ca_basis"] = basis
        shares = money.largest_remainder(asset, weights, keys)
        for key, share, weight in zip(keys, shares, weights, strict=True):
            parts[key][1] = share
            exact[key] += Fraction(asset, scale) * weight / total
    return _Plan(
        POB_DEBIT_FORMULA,
        receivable,
        asset,
        MappingProxyType({key: (ur, ca) for key, (ur, ca) in parts.items()}),
        MappingProxyType(exact),
        MappingProxyType(params),
    )


def _ssp_delivered_plan(
    st: AllocatedState,
    own: Sequence[ObligationState],
    point: _Point,
    residue: Fraction,
    mu: int,
) -> _Plan:
    """ALG-02 step 5 under ``CUMULATIVE_SSP_DELIVERED``: D over the non-VC obligations by the first
    weight set whose sum is not 0; each share takes its obligation's class (DEV-057, DEV-058).
    The exact quota apportions the exact debit D + ``residue`` (L2-4-Q-24)."""
    t = point.period.end_date
    scale: int = 10**mu
    debit = point.debit
    parts = {ob.subject_key: (0, 0) for ob in own}
    exact = {ob.subject_key: Fraction(0) for ob in own}
    params = {"keys": "", "weights": "", "basis": "none"}
    if debit:
        carriers = [ob for ob in own if not billing.is_vc_line(ob)]
        keys = [ob.subject_key for ob in carriers]
        chain: tuple[tuple[str, Callable[[ObligationState], Fraction]], ...] = (
            ("ssp_delivered", lambda ob: ssp_delivered_cum(st, ob, t)),
            ("revenue", lambda ob: Fraction(point.revenue[ob.subject_key])),
            ("allocation", lambda ob: Fraction(billing.posted_allocation(ob, t))),
            ("resolved_ssp", lambda ob: ob.resolved_ssp),
        )
        chosen: tuple[str, list[Fraction]] | None = None
        for basis, weigh in chain:
            weights = [max(Fraction(0), weigh(ob)) for ob in carriers]
            if keys and sum(weights, Fraction(0)) > 0:
                chosen = (basis, weights)
                break
        if chosen is None:
            raise _invariant(
                "the netting reclass has no obligation to attribute to",
                point.parts.subject_key,
                rule="S10-R-22",
                period_key=point.period.period_key,
            )
        basis, weights = chosen
        total = sum(weights, Fraction(0))
        exact_debit = Fraction(debit, scale) + residue
        params = {
            "keys": "|".join(keys),
            "weights": "|".join(rational_param(weight) for weight in weights),
            "basis": basis,
        }
        shares = money.largest_remainder(debit, weights, keys)
        for key, share, weight in zip(keys, shares, weights, strict=True):
            parts[key] = (share, 0) if point.classes[key] == UNCONDITIONAL else (0, share)
            exact[key] = exact_debit * weight / total
    return _Plan(
        SSP_DELIVERED_FORMULA,
        sum(ur for ur, _ in parts.values()),
        sum(ca for _, ca in parts.values()),
        MappingProxyType(parts),
        MappingProxyType(exact),
        MappingProxyType(params),
    )


def _residue(
    revenue: Mapping[tuple[str, str], Sequence[tuple[date, Target]]],
    own: Sequence[ObligationState],
    t: date,
    scale: int,
) -> Fraction:
    """Σ (exact − posted) revenue of the obligations at ``t``: exact D = D + this (Table 0.9-A)."""
    total = Fraction(0)
    for ob in own:
        found = latest_target(revenue.get(("revenue_cum", ob.subject_key), ()), t)
        if found is not None and found.exact is not None:
            total += found.exact - Fraction(found.value, scale)
    return total


def _version_period(measured: Sequence[PeriodInput], v: date) -> PeriodInput:
    """The measured period containing the version date: the latest that starts on or before it."""
    found = measured[0]
    for period in measured:
        if period.start_date <= v:
            found = period
    return found


class _Emitter:
    """Nodes and targets of one book's presentation (§10.5)."""

    def __init__(self, ctx: BookContext, st: AllocatedState, tb: TraceBuilder) -> None:
        self.ctx = ctx
        self.st = st
        self.tb = tb
        self.mu = classification.minor_unit(ctx)
        self.targets: list[Target] = []
        self.reclass: list[ReclassAttribution] = []
        self.version_reclass: list[ReclassAttribution] = []
        self.entries: list[ReclassEntry] = []
        self.members: list[Target] = []

    def target(
        self,
        out: list[Target],
        entity: str,
        subject_key: str,
        measure: str,
        period_key: str,
        value: int,
        node_id: str,
    ) -> None:
        out.append(
            Target(
                self.ctx.book_code,
                entity,
                subject_key,
                measure,
                period_key,
                None,
                value,
                None,
                node_id,
            )
        )

    def attributions(
        self, own: Sequence[ObligationState], point: _Point, plan: _Plan, version: bool
    ) -> dict[str, str]:
        """``netting_reclass_amount`` per obligation at the period end, and at ``-`` when the
        period contains the version date; JET-06 targets for every non-zero part (S10-R-22)."""
        t = point.period.end_date
        nodes: dict[str, str] = {}
        for ob in own:
            key = ob.subject_key
            receivable, asset = plan.parts[key]
            amount = receivable + asset
            role = (
                None
                if amount == 0
                else (UNBILLED_RECEIVABLE if receivable > asset else CONTRACT_ASSET)
            )
            revenue_on = revenue_date(self.st, ob, t)
            params = {
                **plan.params,
                "as_of": t.isoformat(),
                "key": key,
                "aging_contract": ob.contract_key,
                "aging_entity": ob.contracting_entity,
                "aging_revenue_date": revenue_on.isoformat(),
                "aging_receivable": money.format_money(receivable, self.mu),
                "aging_asset": money.format_money(asset, self.mu),
            }
            for period_key in (
                (point.period.period_key, None) if version else (point.period.period_key,)
            ):
                node_id = self.tb.node(
                    measure="netting_reclass_amount",
                    subject_key=key,
                    period_key=period_key,
                    value=amount,
                    currency=self.ctx.txn_currency,
                    minor_unit=self.mu,
                    formula_id=plan.formula_id,
                    inputs=[point.parts.node_id],
                    params=params,
                    exact=plan.exact[key],
                    narrative_key=_narrative(plan.formula_id),
                )
                item = ReclassAttribution(
                    subject_key=key,
                    contract_key=ob.contract_key,
                    entity=ob.contracting_entity,
                    period_key=period_key,
                    as_of=t,
                    receivable=receivable,
                    asset=asset,
                    exact=plan.exact[key],
                    role=role,
                    revenue_date=revenue_on,
                    node_id=node_id,
                )
                if period_key is None:
                    self.version_reclass.append(item)
                    continue
                nodes[key] = node_id
                self.reclass.append(item)
                for debit_role, part in (
                    (UNBILLED_RECEIVABLE, receivable),
                    (CONTRACT_ASSET, asset),
                ):
                    if part == 0:
                        continue
                    self.entries.append(
                        ReclassEntry(
                            NETTING_RECLASS,
                            key,
                            ob.contracting_entity,
                            point.period.period_key,
                            t,
                            debit_role,
                            CONTRACT_LIABILITY,
                            part,
                            None,
                            node_id,
                        )
                    )
                    self.entries.append(
                        ReclassEntry(
                            NETTING_RECLASS_REVERSAL,
                            key,
                            ob.contracting_entity,
                            point.period.period_key,
                            t + timedelta(days=1),
                            CONTRACT_LIABILITY,
                            debit_role,
                            part,
                            RECLASS_REVERSAL,
                            node_id,
                        )
                    )
        return nodes

    def unmeasured(self, own: Sequence[ObligationState], v: date) -> None:
        """S10-R-22 rev 1.100: the version-state ``netting_reclass_amount`` of the obligations of a
        contracting entity without a measured period (C-05) — zero over no input, with a node of
        its own formula, so that every stored figure links the node that produced it (CV-56) and
        the exact-column exports bind it (DG-PAR-05). The entity gets no period node, target,
        entry or member balance."""
        for ob in own:
            key = ob.subject_key
            node_id = self.tb.node(
                measure="netting_reclass_amount",
                subject_key=key,
                period_key=None,
                value=0,
                currency=self.ctx.txn_currency,
                minor_unit=self.mu,
                formula_id=NO_PERIOD_FORMULA,
                inputs=[],
                params={"as_of": v.isoformat(), "key": key},
                exact=Fraction(0),
                narrative_key=_narrative(NO_PERIOD_FORMULA),
            )
            self.version_reclass.append(
                ReclassAttribution(
                    subject_key=key,
                    contract_key=ob.contract_key,
                    entity=ob.contracting_entity,
                    period_key=None,
                    as_of=v,
                    receivable=0,
                    asset=0,
                    exact=Fraction(0),
                    role=None,
                    revenue_date=revenue_date(self.st, ob, v),
                    node_id=node_id,
                )
            )

    def split(
        self,
        own: Sequence[ObligationState],
        point: _Point,
        plan: _Plan,
        attribution_nodes: Mapping[str, str],
        parity: bool,
    ) -> dict[str, tuple[int, str]]:
        """Presented CL, CA, UR of the group and contracting entity (ALG-02 steps 2, 3 and 6)."""
        t = point.period.end_date
        parts = point.parts
        values = {
            "contract_liability": max(0, parts.net_position),
            "contract_asset": plan.asset,
            "unbilled_receivable": plan.receivable,
        }
        presented = (
            values["contract_liability"] - values["contract_asset"] - values["unbilled_receivable"]
        )
        if presented != parts.net_position or min(values.values()) < 0:
            raise _invariant(
                "presented CL − CA − UR differs from NP or a balance is negative",
                parts.subject_key,
                rule="S10-INV-01",
                period_key=point.period.period_key,
            )
        unconditional = [
            ob.subject_key for ob in own if point.classes[ob.subject_key] == UNCONDITIONAL
        ]
        relief = [point.relief[key] for key in unconditional]
        billed = [point.billed[key] for key in unconditional]
        common = {
            "as_of": t.isoformat(),
            "billed": "|".join(str(value) for value in billed),
            "keys": "|".join(unconditional),
            "relief": "|".join(str(value) for value in relief),
        }
        keys = [ob.subject_key for ob in own]
        out: dict[str, tuple[int, str]] = {}
        for measure_name, mode in _SPLIT_MEASURES:
            inputs: list[str | SourceRef] = [parts.node_id]
            params = {**common, "mode": mode}
            if parity and mode in ("ca", "ur"):
                index = 1 if mode == "ca" else 0
                inputs = [attribution_nodes[key] for key in keys]
                params = {
                    "as_of": t.isoformat(),
                    "keys": "|".join(keys),
                    "mode": "parts",
                    "parts": "|".join(str(plan.parts[key][index]) for key in keys),
                }
            node_id = self.tb.node(
                measure=measure_name,
                subject_key=parts.subject_key,
                period_key=point.period.period_key,
                value=values[measure_name],
                currency=self.ctx.txn_currency,
                minor_unit=self.mu,
                formula_id=SPLIT_FORMULA,
                inputs=inputs,
                params=params,
                narrative_key=_narrative(SPLIT_FORMULA),
            )
            self.target(
                self.targets,
                parts.entity,
                parts.subject_key,
                measure_name,
                point.period.period_key,
                values[measure_name],
                node_id,
            )
            out[measure_name] = (values[measure_name], node_id)
        return out

    def member_balances(
        self,
        own: Sequence[ObligationState],
        point: _Point,
        plan: _Plan,
        attribution_nodes: Mapping[str, str],
        liability: tuple[int, str],
    ) -> None:
        """T-CON-09 balances per member contract (S10-R-23; L2-4-Q-26)."""
        t = point.period.end_date
        members = sorted({ob.contract_key for ob in own})
        by_member = {key: [ob for ob in own if ob.contract_key == key] for key in members}
        total, liability_node = liability
        weights = [Fraction(1)] * len(members)
        basis = "sole"
        if len(members) > 1:
            candidates: tuple[tuple[str, Callable[[ObligationState], int | Fraction]], ...] = (
                (
                    "positions",
                    lambda ob: point.billed[ob.subject_key] - point.relief[ob.subject_key],
                ),
                ("allocation", lambda ob: billing.posted_allocation(ob, t)),
                ("resolved_ssp", lambda ob: ob.resolved_ssp),
            )
            for name, weigh in candidates:
                basis = name
                weights = [
                    max(
                        Fraction(0),
                        sum((Fraction(weigh(ob)) for ob in by_member[key]), Fraction(0)),
                    )
                    for key in members
                ]
                if sum(weights, Fraction(0)) > 0:
                    break
            else:
                if total:
                    raise _invariant(
                        "the contract liability has no member to attribute to",
                        point.parts.subject_key,
                        rule="S10-R-23",
                        period_key=point.period.period_key,
                    )
        shares = money.largest_remainder(total, weights, members) if total else [0] * len(members)
        entity = point.parts.entity
        for member, share in zip(members, shares, strict=True):
            subject_key = contract_entity_subject_key(member, entity)
            node_id = self.tb.node(
                measure="contract_liability",
                subject_key=subject_key,
                period_key=point.period.period_key,
                value=share,
                currency=self.ctx.txn_currency,
                minor_unit=self.mu,
                formula_id=SPLIT_FORMULA,
                inputs=[liability_node],
                params={
                    "as_of": t.isoformat(),
                    "basis": basis,
                    "key": member,
                    "keys": "|".join(members),
                    "mode": "member_cl",
                    "weights": "|".join(rational_param(weight) for weight in weights),
                },
                narrative_key=_narrative(SPLIT_FORMULA),
            )
            self.target(
                self.members,
                entity,
                subject_key,
                "contract_liability",
                point.period.period_key,
                share,
                node_id,
            )
            keys = [ob.subject_key for ob in by_member[member]]
            for measure_name, index in (("contract_asset", 1), ("unbilled_receivable", 0)):
                values = [plan.parts[key][index] for key in keys]
                node_id = self.tb.node(
                    measure=measure_name,
                    subject_key=subject_key,
                    period_key=point.period.period_key,
                    value=sum(values),
                    currency=self.ctx.txn_currency,
                    minor_unit=self.mu,
                    formula_id=SPLIT_FORMULA,
                    inputs=[attribution_nodes[key] for key in keys],
                    params={
                        "as_of": t.isoformat(),
                        "keys": "|".join(keys),
                        "mode": "parts",
                        "parts": "|".join(str(value) for value in values),
                    },
                    narrative_key=_narrative(SPLIT_FORMULA),
                )
                self.target(
                    self.members,
                    entity,
                    subject_key,
                    measure_name,
                    point.period.period_key,
                    sum(values),
                    node_id,
                )


def present(
    ctx: BookContext,
    recognition: RecognitionState,
    billed: Billed,
    positions: Positions,
    tb: TraceBuilder,
) -> Presentation:
    """``split_and_attribute`` of §10.2.7 (ALG-02 steps 2 to 6; S10-R-20 to S10-R-23)."""
    st = recognition.allocated
    mu = classification.minor_unit(ctx)
    scale: int = 10**mu
    contracts = {view.header.external_id: view for view in st.contracts}
    obligations = sorted(st.obligations, key=lambda ob: ob.subject_key)
    financing = series(ctx, st.specialist_targets.financing)
    revenue = series(ctx, recognition.revenue_targets)
    v = billing.version_date(st)
    emitter = _Emitter(ctx, st, tb)
    accretion: list[Target] = []
    rights: dict[tuple[str, str], str] = {}
    for entity in sorted({ob.contracting_entity for ob in obligations}):
        own = [ob for ob in obligations if ob.contracting_entity == entity]
        measured = billing.periods(ctx, st, entity)
        if not measured:
            # C-05 rev 1.100: the group's inception period lies after this entity's horizon.
            emitter.unmeasured(own, v)
            continue
        version_period = _version_period(measured, v)
        for period in measured:
            t = period.end_date
            attributed = _accretion(ctx, st, tb, financing, own, period, mu, accretion)
            billed_by = billing.unconditional_attributed(st, billed, t)
            classes: dict[str, str] = {}
            for ob in own:
                classes[ob.subject_key] = right_class(
                    ctx, contracts[ob.contract_key], ob, obligations, t
                )
                rights[(ob.subject_key, period.period_key)] = classes[ob.subject_key]
            point = _Point(
                period=period,
                parts=positions.components[(entity, period.period_key)],
                relief=MappingProxyType(
                    {
                        ob.subject_key: positions.relief[(ob.subject_key, period.period_key)]
                        + attributed.get(ob.subject_key, 0)
                        for ob in own
                    }
                ),
                revenue=MappingProxyType(
                    {
                        ob.subject_key: positions.relief[(ob.subject_key, period.period_key)]
                        for ob in own
                    }
                ),
                billed=MappingProxyType(
                    {ob.subject_key: billed_by.get(ob.subject_key, 0) for ob in own}
                ),
                classes=MappingProxyType(classes),
            )
            option = ctx.policies.value(ATTRIBUTION_POLICY, entity=entity, period=period.period_key)
            if option == POB_DEBIT_POSITIONS:
                plan = _pob_debit_plan(own, point, mu)
            elif option == CUMULATIVE_SSP_DELIVERED:
                plan = _ssp_delivered_plan(st, own, point, _residue(revenue, own, t, scale), mu)
            else:
                raise _invariant(
                    "the reclass attribution key is unknown",
                    point.parts.subject_key,
                    rule="S10-R-22",
                    value=str(option),
                )
            sum_ur = sum(ur for ur, _ in plan.parts.values())
            sum_ca = sum(ca for _, ca in plan.parts.values())
            if (sum_ur, sum_ca) != (plan.receivable, plan.asset):
                raise _invariant(
                    "the attributions do not sum to the presented balances",
                    point.parts.subject_key,
                    rule="S10-INV-03",
                    period_key=period.period_key,
                )
            nodes = emitter.attributions(own, point, plan, period is version_period)
            split = emitter.split(own, point, plan, nodes, option == CUMULATIVE_SSP_DELIVERED)
            emitter.member_balances(own, point, plan, nodes, split["contract_liability"])
    return Presentation(
        targets=tuple(emitter.targets),
        accretion=tuple(accretion),
        rights=MappingProxyType(rights),
        reclass=tuple(emitter.reclass),
        version_reclass=tuple(emitter.version_reclass),
        entries=tuple(emitter.entries),
        members=tuple(emitter.members),
    )


def version_measures(
    measures: Mapping[str, BalanceMeasures], presentation: Presentation
) -> Mapping[str, BalanceMeasures]:
    """T-CON-11 ``netting_reclass_amount`` and ``netting_reclass_role`` at the version date."""
    out = dict(measures)
    for item in presentation.version_reclass:
        found = out.get(item.subject_key)
        if found is None:
            continue
        out[item.subject_key] = dataclasses.replace(
            found,
            netting_reclass_amount=item.amount,
            netting_reclass_amount_exact=item.exact,
            netting_reclass_role=item.role,
            trace_nodes=MappingProxyType(
                {**found.trace_nodes, "netting_reclass_amount": item.node_id}
            ),
        )
    return MappingProxyType(out)
