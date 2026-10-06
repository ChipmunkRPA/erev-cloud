"""Stage 15 contract balances rollforward (ENGINE_SPEC_B §15.2.2; S15-R-03 to S15-R-07;
S15-INV-01, S15-INV-05; POLICIES POL-126; 03 REQ-FX-007; EDS-3).

Private to stage 15 (DG-ENG-07). ``rollforward_balances`` gives, per (combination group, contracting
entity, book) and period of the contracting entity's calendar, the lines of the contract liability,
the contract asset and the unbilled receivable in one view (L4-3-Q-3):

- ``TRANSACTION``: the path attribution of ``rollforward_contract`` in the transaction currency.
  ``OPENING`` is the stage 10 presented balance at the previous period end, the day before the
  period starts, unless the caller passes a lock snapshot (``opening``). ``CLOSING`` is the
  presented balance at the period end (CTL-030). The flows are the control-role flows of the
  contracting entity (stage 12 input records, ENGINE_SPEC_B §12.1), in stage 12 order: date,
  time-driven releases first, then ENG-06 order. A billing credit enters on the earlier of its
  unconditional date and its first receipt (S10-R-06, S12-R-04). A credit settles the unbilled
  receivable, then the contract asset, and the rest enters the liability as a new layer. A debit
  consumes the opening layer before the new layers (POL-126, FIFO within the contract), and the
  rest is revenue in excess of billing, or an increase, of the obligation's right class
  (S10-R-21: ``UNCONDITIONAL`` gives the unbilled receivable, anything else the contract asset).
- ``FUNCTIONAL``: the same lines from the stage 12 layer movements, in the contracting entity's
  functional currency (REQ-FX-007). Created, consumed and settled layers carry their functional
  amounts, and every remeasurement, at period end or on settlement, is the separate ``FX`` line.
  ``OPENING`` and ``CLOSING`` are the carrying amounts of the open layers at the previous and the
  current period end. An asset layer is presented by the right class of the obligation whose
  revenue created it (L4-3-Q-4). When the functional currency is the transaction currency, the view
  equals ``TRANSACTION``.
- Lines (S15-R-03): ``BALANCE_LINES``. ``RECLASSIFIED_BETWEEN_ASSET_CAPTIONS`` carries only what
  leaves one asset caption for the other. Any other difference from the closing balance is
  ``OTHER``, shown and never absorbed (S15-R-07; L4-3-Q-5).
- Memo lines (S15-R-04), transaction view: Σ the period's ``REVENUE`` schedule lines of the
  contracting entity's obligations by E-28 line type, plus ``LATE_EVENT``, the revenue posted in the
  period with an earlier origin period. They do not enter the tie.
- POL-126 (S15-R-05): under ``FIFO_WITHIN_CONTRACT`` the path gives min(opening presented
  liability, revenue relief). Under ``FIFO_WITHIN_POB`` the line is Σ over obligations of
  min(opening liability, revenue relief), with stage 10 obligation-attributed billing, capped by the
  liability revenue of the path (L4-3-Q-6).
- Business combinations (S15-R-06): an ``OPENING_BALANCE_ESTABLISHED`` with reason
  ``BUSINESS_COMBINATION`` enters the period holding its cutover as ``BUSINESS_COMBINATIONS``, at
  the acquisition-date presented amounts of the stage 07 baselines (billed − revenue). It creates
  no journal line. Periods ending before the latest cutover of the unit hold nothing, and flows on
  or before it are pre-acquisition (L4-3-Q-7).

§15.5 names no rollforward node, so none is emitted. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from types import MappingProxyType
from typing import Final

from erev_engine.bundle import PeriodInput, PostingIntent
from erev_engine.errors import EngineError
from erev_engine.stages.s01_canonicalize import group_entity_subject_key
from erev_engine.stages.s07_onboarding import baseline_of
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.s12_fx_entities import ControlFlow, FxState, LayerMovement
from erev_engine.stages.s15_disclosures.rpo import period_of
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    ObligationState,
    PostedIndex,
    ScheduleLineOut,
    Target,
)

__all__ = [
    "BALANCES",
    "BALANCE_LINES",
    "FUNCTIONAL",
    "MEMO_CAUSES",
    "TRANSACTION",
    "VIEWS",
    "BalanceInputs",
    "BalanceRollforward",
    "balance_inputs",
    "rollforward_balances",
]

TRANSACTION: Final = "TRANSACTION"
FUNCTIONAL: Final = "FUNCTIONAL"
VIEWS: Final = (TRANSACTION, FUNCTIONAL)
CONTRACT_LIABILITY: Final = "CONTRACT_LIABILITY"
CONTRACT_ASSET: Final = "CONTRACT_ASSET"
UNBILLED_RECEIVABLE: Final = "UNBILLED_RECEIVABLE"
BALANCES: Final = (CONTRACT_LIABILITY, CONTRACT_ASSET, UNBILLED_RECEIVABLE)  # E-01 roles
# The stage 10 presentation measure of each balance (S10-R-20).
_MEASURES: Final[Mapping[str, str]] = MappingProxyType(
    {
        CONTRACT_LIABILITY: "contract_liability",
        CONTRACT_ASSET: "contract_asset",
        UNBILLED_RECEIVABLE: "unbilled_receivable",
    }
)
OPENING: Final = "OPENING"
OTHER: Final = "OTHER"
CLOSING: Final = "CLOSING"
_FROM_OPENING: Final = "REVENUE_FROM_OPENING_BALANCE"
_FROM_OTHER: Final = "REVENUE_FROM_OTHER_INCREASES"
_IN_EXCESS: Final = "REVENUE_IN_EXCESS_OF_BILLING"
_TRANSFERRED: Final = "TRANSFERRED_TO_RECEIVABLES_OR_SETTLED"
_RECLASSIFIED: Final = "RECLASSIFIED_BETWEEN_ASSET_CAPTIONS"
_COMBINATIONS: Final = "BUSINESS_COMBINATIONS"
_FX: Final = "FX"
# S15-R-03 lines in report order.
LIABILITY_LINES: Final = (
    OPENING,
    "INCREASES_BILLING",
    "INCREASES_DEPOSIT_TRANSFER",
    "INCREASES_NONCASH",
    "INCREASES_FINANCING",
    "INCREASES_REFUND_RELEASE",
    "INCREASES_NEGATIVE_REVENUE",
    _FROM_OPENING,
    _FROM_OTHER,
    "DECREASES_REFUND_LIABILITY",
    "DECREASES_CONTRA",
    "DECREASES_FINANCING",
    "DECREASES_CREDIT_MEMO",
    _COMBINATIONS,
    _FX,
    OTHER,
    CLOSING,
)
ASSET_LINES: Final = (
    OPENING,
    _IN_EXCESS,
    "INCREASES_REFUND_LIABILITY",
    "INCREASES_CONTRA",
    "INCREASES_FINANCING",
    "INCREASES_CREDIT_MEMO",
    _TRANSFERRED,
    _RECLASSIFIED,
    _COMBINATIONS,
    _FX,
    OTHER,
    CLOSING,
)
BALANCE_LINES: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        CONTRACT_LIABILITY: LIABILITY_LINES,
        CONTRACT_ASSET: ASSET_LINES,
        UNBILLED_RECEIVABLE: ASSET_LINES,
    }
)
_EDGES: Final = frozenset({OPENING, OTHER, CLOSING})
# The S15-R-03 kind of each stage 12 control-flow kind (S12-R-03).
_KINDS: Final[Mapping[str, str]] = MappingProxyType(
    {
        "BILLING": "BILLING",
        "DEPOSIT_TRANSFER": "DEPOSIT_TRANSFER",
        "NONCASH": "NONCASH",
        "INTEREST_EXPENSE": "FINANCING",
        "REFUND_RELEASE": "REFUND_RELEASE",
        "NEGATIVE_REVENUE": "NEGATIVE_REVENUE",
        "REVENUE": "REVENUE",
        "REFUND_INCREASE": "REFUND_LIABILITY",
        "CONTRA_INCREASE": "CONTRA",
        "CONTRA_RELEASE": "CONTRA",
        "INTEREST_INCOME": "FINANCING",
        "CREDIT_MEMO": "CREDIT_MEMO",
    }
)
# S15-R-04 memo causes: the E-28 line types, then late events.
MEMO_CAUSES: Final = (
    "NORMAL",
    "MODIFICATION",
    "TP_CHANGE",
    "CATCH_UP",
    "RETURN",
    "BREAKAGE",
    "ROYALTY",
    "OPENING_BALANCE",
    "LATE_EVENT",
)
_POL_126: Final = "rollforward.opening_liability_consumption"
_WITHIN_CONTRACT: Final = "FIFO_WITHIN_CONTRACT"
_WITHIN_POB: Final = "FIFO_WITHIN_POB"
_UNCONDITIONAL: Final = "UNCONDITIONAL"  # S10-R-21
_BUSINESS_COMBINATION: Final = "BUSINESS_COMBINATION"  # OPENING_BALANCE_ESTABLISHED reason
_REVENUE: Final = "REVENUE"
_NEGATIVE_REVENUE: Final = "NEGATIVE_REVENUE"
_CREDIT: Final = "CREDIT"
_DEBIT: Final = "DEBIT"


@dataclass(frozen=True, slots=True)
class BalanceInputs:
    """The records the rollforward of one book reads (ENGINE_SPEC_B §15.1; L4-3-Q-3)."""

    flows: tuple[ControlFlow, ...]  # stage 12 input records (§12.1), every contracting entity
    presented: tuple[
        Target, ...
    ]  # stage 10 contract_liability, contract_asset, unbilled_receivable
    # stage 10 (obligation subject key, period key) -> CONDITIONAL | UNCONDITIONAL (S10-R-21)
    right_classes: Mapping[tuple[str, str], str] = field(
        default_factory=lambda: MappingProxyType({})
    )
    schedule_lines: tuple[ScheduleLineOut, ...] = ()  # stage 09, for the memo lines
    # stage 10 document key -> obligation subject key -> signed minor units (S10-INV-04)
    attribution: Mapping[str, Mapping[str, int]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    # (obligation subject key, entity, posting period key) -> revenue posted with an earlier origin
    late_revenue: Mapping[tuple[str, str, str], int] = field(
        default_factory=lambda: MappingProxyType({})
    )
    fx: FxState | None = None  # stage 12 state, for the functional view


@dataclass(frozen=True, slots=True)
class BalanceRollforward:
    """The S15-R-03 lines of one (group, contracting entity, book) over one period in one view."""

    unit: str  # "<group>@<contracting entity>"
    entity: str
    book_code: str
    period_key: str
    view: str  # TRANSACTION | FUNCTIONAL
    currency: str
    opening_date: date  # the day before the period starts
    closing_date: date  # the period end
    lines: Mapping[str, Mapping[str, int]]  # balance -> line code -> signed minor units
    memo: Mapping[str, int]  # S15-R-04 revenue by cause, MEMO_CAUSES order; not in the tie
    revenue_relief: int  # revenue less negative revenue of the period, in the view's currency

    @property
    def revenue_from_opening_liability(self) -> int:
        """S15-R-05: revenue recognised from the opening contract liability (POL-126)."""
        return -self.lines[CONTRACT_LIABILITY][_FROM_OPENING]

    @property
    def balanced(self) -> bool:
        """S15-R-07: no balance shows an unexplained difference."""
        return all(values[OTHER] == 0 for values in self.lines.values())


def balance_inputs(
    ctx: BookContext,
    balances: BalanceState,
    fx: FxState,
    intents: Sequence[PostingIntent],
    posted: PostedIndex | None,
) -> BalanceInputs:
    """The rollforward records of one book from the stage 10 and stage 12 states, the stage 14
    intents and the posted amounts."""
    source = getattr(fx.costs, "fx_flows", None)
    flows = getattr(source, "control", ())
    starts = {
        (code, period.period_key): period.start_date
        for code, calendar in ctx.entities.items()
        for period in calendar.periods
    }
    ends = {
        (code, period.period_key): period.end_date
        for code, calendar in ctx.entities.items()
        for period in calendar.periods
    }
    late: dict[tuple[str, str, str], int] = {}

    def carry(subject: str, entity: str, period_key: str, origin: str | None, amount: int) -> None:
        if origin is None or origin == period_key:
            return
        origin_end, start = ends.get((entity, origin)), starts.get((entity, period_key))
        if origin_end is None or start is None or origin_end >= start:
            return
        key = (subject, entity, period_key)
        late[key] = late.get(key, 0) + amount

    book = str(ctx.book_code)
    if posted is not None:
        for record in posted.amounts:
            if record.book_code == book and record.account_role == _REVENUE:
                carry(
                    record.subject_key,
                    record.entity_code,
                    record.period_key,
                    record.origin_period_key,
                    -record.amount_txn,
                )
    for intent in intents:
        if intent.book_code != book:
            continue
        for line in intent.lines:
            if line.account_role == _REVENUE:
                signed = line.amount_txn if line.side == "C" else -line.amount_txn
                carry(
                    intent.subject_key,
                    intent.entity,
                    intent.posting_period_key,
                    intent.origin_period_key,
                    signed,
                )
    return BalanceInputs(
        flows=tuple(flow for flow in flows if isinstance(flow, ControlFlow)),
        presented=balances.presentation,
        right_classes=balances.right_classes,
        schedule_lines=balances.recognition.schedule_lines,
        attribution=MappingProxyType(
            {document.document_key: document.attribution for document in balances.documents}
        ),
        late_revenue=MappingProxyType(dict(sorted(late.items()))),
        fx=fx,
    )


def rollforward_balances(
    ctx: BookContext,
    st: AllocatedState,
    records: BalanceInputs,
    entity: str,
    period_key: str,
    *,
    view: str = TRANSACTION,
    opening: Mapping[str, int] | None = None,
) -> BalanceRollforward:
    """S15-R-03 to S15-R-07 lines of the balances ``entity`` presents for the group over
    ``period_key`` of its calendar, in ``view``.

    ``opening`` holds a previous lock snapshot's closing per balance role (S15-R-20), 0 for a role
    it does not hold; without it the opening is restated from the version.
    """
    if view not in VIEWS:
        raise ValueError(f"unknown rollforward view {view!r}; expected one of {', '.join(VIEWS)}")
    calendar = ctx.entities.get(entity)
    ordered = [] if calendar is None else sorted(calendar.periods, key=lambda item: item.start_date)
    index = next((i for i, item in enumerate(ordered) if item.period_key == period_key), None)
    if calendar is None or index is None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the contracting entity keeps no such period",
            detail={"entity": entity, "period_key": period_key, "rule": "CV-12", "stage": "15"},
        )
    period = ordered[index]
    previous = None
    if index > 0 and ordered[index - 1].end_date == period.start_date - timedelta(days=1):
        previous = ordered[index - 1]
    unit = group_entity_subject_key(st.group_code, entity)
    own = tuple(ob for ob in st.obligations if ob.contracting_entity == entity)
    cutover = _cutover(own)
    lines = {balance: dict.fromkeys(BALANCE_LINES[balance], 0) for balance in BALANCES}
    memo = dict.fromkeys(MEMO_CAUSES, 0)
    functional = view == FUNCTIONAL and calendar.functional_currency != ctx.txn_currency
    relief = 0
    if cutover is None or period.end_date >= cutover:
        if functional:
            relief = _functional(ctx, records, entity, unit, period, previous, cutover, lines)
        else:
            relief = _transaction(ctx, records, own, entity, unit, period, previous, cutover, lines)
            memo = _memo(ctx, records, own, period, cutover)
    if opening is not None:
        for balance in BALANCES:
            lines[balance][OPENING] = opening.get(balance, 0)
    for values in lines.values():
        moved = sum(amount for code, amount in values.items() if code not in _EDGES)
        values[OTHER] = values[CLOSING] - values[OPENING] - moved
    return BalanceRollforward(
        unit=unit,
        entity=entity,
        book_code=str(ctx.book_code),
        period_key=period.period_key,
        view=view,
        currency=calendar.functional_currency if view == FUNCTIONAL else ctx.txn_currency,
        opening_date=period.start_date - timedelta(days=1),
        closing_date=period.end_date,
        lines=MappingProxyType(
            {balance: MappingProxyType(values) for balance, values in lines.items()}
        ),
        memo=MappingProxyType(memo),
        revenue_relief=relief,
    )


def _transaction(
    ctx: BookContext,
    records: BalanceInputs,
    own: Sequence[ObligationState],
    entity: str,
    unit: str,
    period: PeriodInput,
    previous: PeriodInput | None,
    cutover: date | None,
    lines: dict[str, dict[str, int]],
) -> int:
    """The path attribution in the transaction currency (§15.2.2 ``rollforward_contract``)."""
    start, end = period.start_date, period.end_date
    acquired = cutover is not None and start <= cutover <= end
    presented = {
        (target.measure, target.period_key): target.value
        for target in records.presented
        if target.subject_key == unit
    }
    first = dict.fromkeys(BALANCES, 0)
    if previous is not None and not acquired:
        first = {
            role: presented.get((_MEASURES[role], previous.period_key), 0) for role in BALANCES
        }
    for role in BALANCES:
        lines[role][OPENING] = first[role]
    layers: list[list[int]] = [[1, first[CONTRACT_LIABILITY]]] if first[CONTRACT_LIABILITY] else []
    asset = {UNBILLED_RECEIVABLE: first[UNBILLED_RECEIVABLE], CONTRACT_ASSET: first[CONTRACT_ASSET]}
    if acquired and cutover is not None:
        established = _established(ctx, records, own, entity, cutover)
        for role in BALANCES:
            lines[role][_COMBINATIONS] = established[role]
        if established[CONTRACT_LIABILITY]:
            layers.append([0, established[CONTRACT_LIABILITY]])
        for role in (UNBILLED_RECEIVABLE, CONTRACT_ASSET):
            asset[role] += established[role]
    relief = 0
    for flow in _period_flows(records.flows, entity, start, end, cutover):
        kind = _KINDS[flow.kind]
        if flow.kind == _REVENUE:
            relief += flow.amount
        elif flow.kind == _NEGATIVE_REVENUE:
            relief -= flow.amount
        if flow.side == _CREDIT:
            left = flow.amount
            for role in (UNBILLED_RECEIVABLE, CONTRACT_ASSET):  # receivable-like balances first
                take = min(asset[role], left)
                asset[role] -= take
                left -= take
                lines[role][_TRANSFERRED] -= take
            if left:
                layers.append([0, left])
                lines[CONTRACT_LIABILITY][f"INCREASES_{kind}"] += left
            continue
        need = flow.amount
        for layer in layers:  # FIFO within the contract: the opening layer first (POL-126)
            take = min(layer[1], need)
            if take == 0:
                continue
            layer[1] -= take
            need -= take
            if flow.kind == _REVENUE:
                lines[CONTRACT_LIABILITY][_FROM_OPENING if layer[0] else _FROM_OTHER] -= take
            else:
                lines[CONTRACT_LIABILITY][f"DECREASES_{kind}"] -= take
            if need == 0:
                break
        if need:
            role = _debit_role(ctx, records, flow, entity)
            code = _IN_EXCESS if flow.kind == _REVENUE else f"INCREASES_{kind}"
            asset[role] += need
            lines[role][code] += need
    closing = {role: presented.get((_MEASURES[role], period.period_key), 0) for role in BALANCES}
    for role in BALANCES:
        lines[role][CLOSING] = closing[role]
    _captions(asset, closing, lines)
    consumption = ctx.policies.value(_POL_126, entity=entity, period=period.period_key)
    if consumption == _WITHIN_POB:
        _within_obligations(records, own, entity, start, end, cutover, lines)
    elif consumption != _WITHIN_CONTRACT:
        raise ValueError(f"{_POL_126} is {_WITHIN_CONTRACT} or {_WITHIN_POB} (POL-126)")
    return relief


def _functional(
    ctx: BookContext,
    records: BalanceInputs,
    entity: str,
    unit: str,
    period: PeriodInput,
    previous: PeriodInput | None,
    cutover: date | None,
    lines: dict[str, dict[str, int]],
) -> int:
    """The lines from the stage 12 layer movements in the functional currency (REQ-FX-007)."""
    fx = records.fx
    if fx is None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the functional rollforward reads the stage 12 layer movements",
            subject_key=unit,
            detail={"rule": "REQ-FX-007", "stage": "15"},
        )
    start, end = period.start_date, period.end_date
    by_source: dict[str, list[ControlFlow]] = {}
    for item in records.flows:
        if item.entity == entity:
            by_source.setdefault(item.source_key, []).append(item)
    movements = [
        move
        for move in fx.layer_movements
        if move.entity == entity and move.balance_role in (CONTRACT_LIABILITY, CONTRACT_ASSET)
    ]
    creators = {
        move.layer_key: _flow_of(by_source, move, _DEBIT)
        for move in movements
        if move.movement_kind == "ASSET_LAYER_CREATED"
    }

    def role_of(layer_key: str, period_key: str) -> str:
        flow = creators.get(layer_key)
        if flow is None or flow.kind != _REVENUE:
            return CONTRACT_ASSET
        found = records.right_classes.get((flow.subject_key, period_key))
        return UNBILLED_RECEIVABLE if found == _UNCONDITIONAL else CONTRACT_ASSET

    acquired = cutover is not None and start <= cutover <= end
    opening_layers: set[str] = set()
    first = dict.fromkeys(BALANCES, 0)
    if previous is not None and not acquired:
        for held in fx.layer_balances:
            if held.entity != entity or held.period_key != previous.period_key:
                continue
            if held.balance_role == CONTRACT_LIABILITY:
                first[CONTRACT_LIABILITY] += held.fn_carrying
                opening_layers.add(held.layer_key)
            elif held.balance_role == CONTRACT_ASSET:
                first[role_of(held.layer_key, previous.period_key)] += held.fn_carrying
    for role in BALANCES:
        lines[role][OPENING] = first[role]
    asset = {UNBILLED_RECEIVABLE: first[UNBILLED_RECEIVABLE], CONTRACT_ASSET: first[CONTRACT_ASSET]}
    relief = 0
    for move in movements:
        when = move.effective_date
        if not start <= when <= end or (cutover is not None and when <= cutover):
            continue
        amount = move.amount_functional
        kind = move.movement_kind
        if kind == "LIABILITY_LAYER_CREATED":
            flow = _flow_of(by_source, move, _CREDIT)
            if flow is not None:
                lines[CONTRACT_LIABILITY][f"INCREASES_{_KINDS[flow.kind]}"] += amount
                relief -= amount if flow.kind == _NEGATIVE_REVENUE else 0
        elif kind == "LIABILITY_LAYER_CONSUMED":
            flow = _flow_of(by_source, move, _DEBIT)
            if flow is not None and flow.kind == _REVENUE:
                code = _FROM_OPENING if move.layer_key in opening_layers else _FROM_OTHER
                lines[CONTRACT_LIABILITY][code] -= amount
                relief += amount
            elif flow is not None:
                lines[CONTRACT_LIABILITY][f"DECREASES_{_KINDS[flow.kind]}"] -= amount
        elif kind == "LIABILITY_LAYER_REMEASURED":
            lines[CONTRACT_LIABILITY][_FX] += amount
        elif kind in ("ASSET_LAYER_CREATED", "ASSET_LAYER_SETTLED", "ASSET_LAYER_REMEASURED"):
            role = role_of(move.layer_key, period_of(ctx, entity, when))
            if kind == "ASSET_LAYER_REMEASURED":
                asset[role] += amount
                lines[role][_FX] += amount
            elif kind == "ASSET_LAYER_SETTLED":
                asset[role] -= amount
                lines[role][_TRANSFERRED] -= amount
                flow = _flow_of(by_source, move, _CREDIT)
                relief -= amount if flow is not None and flow.kind == _NEGATIVE_REVENUE else 0
            else:
                flow = creators.get(move.layer_key)
                if flow is not None:
                    revenue = flow.kind == _REVENUE
                    code = _IN_EXCESS if revenue else f"INCREASES_{_KINDS[flow.kind]}"
                    asset[role] += amount
                    lines[role][code] += amount
                    relief += amount if revenue else 0
    closing = dict.fromkeys(BALANCES, 0)
    for held in fx.layer_balances:
        if held.entity != entity or held.period_key != period.period_key:
            continue
        if held.balance_role == CONTRACT_LIABILITY:
            closing[CONTRACT_LIABILITY] += held.fn_carrying
        elif held.balance_role == CONTRACT_ASSET:
            closing[role_of(held.layer_key, period.period_key)] += held.fn_carrying
    for role in BALANCES:
        lines[role][CLOSING] = closing[role]
    _captions(asset, closing, lines)
    return relief


def _within_obligations(
    records: BalanceInputs,
    own: Sequence[ObligationState],
    entity: str,
    start: date,
    end: date,
    cutover: date | None,
    lines: dict[str, dict[str, int]],
) -> None:
    """POL-126 ``FIFO_WITHIN_POB``: Σ min(opening liability, relief) per obligation, with the
    obligation-attributed billing of stage 10, capped by the liability revenue of the path."""
    subjects = {ob.subject_key for ob in own}
    billed: dict[str, int] = {}
    before: dict[str, int] = {}
    during: dict[str, int] = {}
    for flow in records.flows:
        when = _entered(flow)
        if flow.entity != entity or when is None or when > end:
            continue
        if cutover is not None and when <= cutover:
            continue
        if flow.kind in ("BILLING", "CREDIT_MEMO"):
            if when < start:
                for subject, amount in sorted(records.attribution.get(flow.source_key, {}).items()):
                    if subject in subjects:
                        billed[subject] = billed.get(subject, 0) + amount
        elif flow.kind in (_REVENUE, _NEGATIVE_REVENUE) and flow.subject_key in subjects:
            signed = flow.amount if flow.kind == _REVENUE else -flow.amount
            found = before if when < start else during
            found[flow.subject_key] = found.get(flow.subject_key, 0) + signed
    formula = sum(
        min(
            max(0, billed.get(subject, 0) - before.get(subject, 0)),
            max(0, during.get(subject, 0)),
        )
        for subject in sorted(subjects)
    )
    liability = lines[CONTRACT_LIABILITY]
    consumed = -(liability[_FROM_OPENING] + liability[_FROM_OTHER])
    from_opening = min(consumed, liability[OPENING], formula)
    liability[_FROM_OPENING] = -from_opening
    liability[_FROM_OTHER] = -(consumed - from_opening)


def _memo(
    ctx: BookContext,
    records: BalanceInputs,
    own: Sequence[ObligationState],
    period: PeriodInput,
    cutover: date | None,
) -> dict[str, int]:
    """S15-R-04: the period's revenue by cause of the contracting entity's obligations."""
    subjects = {ob.subject_key for ob in own}
    ends = {
        (code, item.period_key): item.end_date
        for code, calendar in ctx.entities.items()
        for item in calendar.periods
    }

    def within(entity: str, period_key: str) -> bool:
        found = ends.get((entity, period_key))
        if found is None or not period.start_date <= found <= period.end_date:
            return False
        return cutover is None or found > cutover

    memo = dict.fromkeys(MEMO_CAUSES, 0)
    for line in records.schedule_lines:
        if str(line.schedule_kind) != _REVENUE or line.subject_key not in subjects:
            continue
        if within(line.entity, line.period_key):
            cause = str(line.line_type)
            memo[cause] = memo.get(cause, 0) + line.amount
    for (subject, entity, period_key), amount in sorted(records.late_revenue.items()):
        if subject in subjects and within(entity, period_key):
            memo["LATE_EVENT"] += amount
    return memo


def _established(
    ctx: BookContext,
    records: BalanceInputs,
    own: Sequence[ObligationState],
    entity: str,
    cutover: date,
) -> dict[str, int]:
    """S15-R-06: acquisition-date presented balances of the business combination at ``cutover``,
    from the stage 07 baselines (billed − revenue; S10-R-20 split of a debit position)."""
    position = 0
    unconditional = 0
    period_key = period_of(ctx, entity, cutover)
    for ob in own:
        if not _acquired(ob) or ob.opening is None or ob.opening.get("cutover_date") != cutover:
            continue
        baseline = baseline_of(ob)
        if baseline is None:
            continue
        position += baseline.billed_cum - baseline.revenue_cum
        if records.right_classes.get((ob.subject_key, period_key)) == _UNCONDITIONAL:
            unconditional += max(0, baseline.revenue_cum - baseline.billed_cum)
    debit = max(0, -position)
    receivable = min(debit, unconditional)
    return {
        CONTRACT_LIABILITY: max(0, position),
        UNBILLED_RECEIVABLE: receivable,
        CONTRACT_ASSET: debit - receivable,
    }


def _acquired(ob: ObligationState) -> bool:
    return ob.opening is not None and ob.opening.get("reason") == _BUSINESS_COMBINATION


def _cutover(own: Sequence[ObligationState]) -> date | None:
    """The latest business-combination cutover of the unit's obligations (L4-3-Q-7)."""
    found = [
        value
        for ob in own
        if _acquired(ob) and ob.opening is not None
        for value in (ob.opening.get("cutover_date"),)
        if isinstance(value, date)
    ]
    return max(found) if found else None


def _entered(flow: ControlFlow) -> date | None:
    """The date a flow enters the position: a billing credit on the earlier of its unconditional
    date and first receipt (S10-R-06, S12-R-04), when it has either; other flows on their date."""
    if flow.kind != "BILLING":
        return flow.effective_date
    candidates = [item for item in (flow.unconditional_date, flow.first_receipt_date) if item]
    return min(candidates) if candidates else None


def _order(flow: ControlFlow) -> tuple[int, int, str, str, str]:
    # Stage 12 order on a date: time-driven releases first, then ENG-06 order (ALG-08 §2.9.1).
    seq = flow.record_seq
    return (0 if seq is None else 1, seq or 0, flow.source_key, flow.subject_key, flow.kind)


def _period_flows(
    flows: Sequence[ControlFlow], entity: str, start: date, end: date, cutover: date | None
) -> list[ControlFlow]:
    """The entity's flows entering the position in [start, end] after the cutover, in order."""
    found: list[tuple[date, tuple[int, int, str, str, str], ControlFlow]] = []
    for flow in flows:
        when = _entered(flow)
        if flow.entity != entity or when is None or not start <= when <= end:
            continue
        if cutover is not None and when <= cutover:
            continue
        found.append((when, _order(flow), flow))
    return [item[2] for item in sorted(found, key=lambda item: (item[0], item[1]))]


def _debit_role(ctx: BookContext, records: BalanceInputs, flow: ControlFlow, entity: str) -> str:
    """The asset caption of a debit left after the liability: revenue follows the right class of
    its obligation at the period of the flow (S10-R-21); other debits the contract asset."""
    if flow.kind != _REVENUE:
        return CONTRACT_ASSET
    period_key = period_of(ctx, entity, flow.effective_date)
    found = records.right_classes.get((flow.subject_key, period_key))
    return UNBILLED_RECEIVABLE if found == _UNCONDITIONAL else CONTRACT_ASSET


def _flow_of(
    by_source: Mapping[str, Sequence[ControlFlow]], move: LayerMovement, side: str
) -> ControlFlow | None:
    """The flow behind a movement: its source's first flow of that side in stage 12 order."""
    candidates = [flow for flow in by_source.get(move.source_key or "", ()) if flow.side == side]
    return min(candidates, key=_order) if candidates else None


def _captions(
    asset: Mapping[str, int], closing: Mapping[str, int], lines: dict[str, dict[str, int]]
) -> None:
    """What leaves one asset caption for the other; the rest of a difference stays unexplained."""
    receivable = closing[UNBILLED_RECEIVABLE] - asset[UNBILLED_RECEIVABLE]
    contract = closing[CONTRACT_ASSET] - asset[CONTRACT_ASSET]
    moved = 0
    if receivable > 0 > contract:
        moved = min(receivable, -contract)
    elif contract > 0 > receivable:
        moved = -min(contract, -receivable)
    lines[UNBILLED_RECEIVABLE][_RECLASSIFIED] = moved
    lines[CONTRACT_ASSET][_RECLASSIFIED] = -moved
