"""Stage 09 returns within the units measures (ENGINE_SPEC_B §9.2.7 S09-R-23 to S09-R-26; ENC-7).

POLICIES ALG-06 §2.7.2 and §2.7.3 (POL-051 to POL-053). An obligation with a return path published
by stage 04 (S04-R-08b) keeps its allocation on the pre-return basis. Under POL-053
``REDUCE_CONTRACT_QUANTITY`` its posted target is ALG-06 step 2 exactly, C = round(r × (N − Y −
E)), posted through ALG-01 §2.1.3 (S09-R-23). E follows step 1: the ``RETURN_RATE`` version in
force less the units returned after its effective date, floored at 0 and never above the units
kept, and 0 from the end of ``window_end_date``, which is time-driven (S09-R-26; D-87 L6-5-Q-25:
a measurement dated on or after the window end has E = 0, and the expiry sorts after that day's
events, so a return on the last day still counts). Without a return
path E = 0 and the units measure already nets the returned units at r.

Under ``RESTORE_REMAINING_QUANTITY`` returned units become deliverable again and E = 0 (S09-R-24).
Each return reverses revenue at the POL-052 rate, and later deliveries earn the refreshed unit rate
remaining allocation ÷ remaining quantity (S09-R-25; legacy 02 §3.7). With
``CURRENT_REMAINING_RATE`` this equals the units measure over the net units.

``ReturnState`` is published per returnable obligation and period end for stage 10 (§9.1). E_b of
ALG-06 step 3 counts the units billed or paid under S09-R-23a: one ``BILLING_RECORDED`` line per
S10-R-07 identity at contract scope (``erev_engine.billing_identity``), each from its S10-R-06
unconditional date under ``state.billing_mode_at`` (D-91 C606-01). Values come from the registered
formulas, so every trace node reproduces them (DG-KRN-EXP-04). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import billing_identity, money
from erev_engine.errors import EngineError
from erev_engine.formulas import FORMULAS, rational_param
from erev_engine.stages.s09_recognition import progress_events
from erev_engine.stages.s09_recognition.progress_events import Position
from erev_engine.stages.state import (
    BILLING_MODE_ENGINE,
    AllocatedState,
    AllocationSegment,
    BookContext,
    ContractView,
    EventView,
    ObligationState,
    ReturnPath,
    ReturnPin,
    billing_mode_at,
)
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = [
    "EXPECTED_FORMULA",
    "EXPIRY_AMOUNT_CLASS",
    "EXPIRY_POSTING_PASS",
    "REDUCE",
    "REFUNDABLE_UNITS_FORMULA",
    "RESTORE",
    "REVERSAL_FORMULA",
    "TARGET_FORMULA",
    "UNITS_BILLED_FORMULA",
    "UNITS_METHODS",
    "BilledLine",
    "Expected",
    "ReturnState",
    "ReturnTarget",
    "Reversal",
    "emit",
    "expected_units",
    "pin_at",
    "policy",
    "reduction",
    "reduction_from_state",
    "refundable_units_node_id",
    "return_state",
    "target",
    "unit_rate",
]

MODEL_POLICY: Final = "returns.model"  # POL-051
RATE_POLICY: Final = "returns.reversal_rate"  # POL-052
SCOPE_POLICY: Final = "returns.returned_units_scope"  # POL-053
REDUCE: Final = "REDUCE_CONTRACT_QUANTITY"
RESTORE: Final = "RESTORE_REMAINING_QUANTITY"
AVERAGE_CARRYING_RATE: Final = "AVERAGE_CARRYING_RATE"
POLICY_OPTIONS: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        MODEL_POLICY: frozenset({"EXPECTED_RETURNS", "ACTUAL_RETURNS_ONLY"}),
        RATE_POLICY: frozenset({AVERAGE_CARRYING_RATE, "CURRENT_REMAINING_RATE"}),
        SCOPE_POLICY: frozenset({REDUCE, RESTORE}),
    }
)
UNITS_METHODS: Final = frozenset({"POINT_IN_TIME", "UNITS_DELIVERED"})
EXPECTED_FORMULA: Final = "returns.expected_units.v1"
TARGET_FORMULA: Final = "returns.revenue_target.v1"
REVERSAL_FORMULA: Final = "returns.excess_reversal.v1"
UNITS_BILLED_FORMULA: Final = "returns.units_billed.v1"  # S09-R-23a (D-91)
REFUNDABLE_UNITS_FORMULA: Final = "returns.refundable_units.v1"  # ALG-06 step 3 E_b (D-91)
UNITS_BILLED_MEASURE: Final = "return_units_billed"
REFUNDABLE_UNITS_MEASURE: Final = "return_refundable_units"
EXPIRY_AMOUNT_CLASS: Final = "TIME"  # 05 RCP-07: return-window expiry is time-driven
EXPIRY_POSTING_PASS: Final = "CLOSE_RELEASE"  # 05 RCP-08; ENGINE_SPEC_B S14-R-05 (JET-04a expiry)


@dataclass(frozen=True, slots=True)
class ReturnState:
    """ALG-06 quantities of a returnable obligation at a date (ENGINE_SPEC_B §9.2.7)."""

    N: Fraction  # cumulative units transferred
    Y: Fraction  # cumulative units returned
    E: Fraction  # expected further returns
    E_b: Fraction  # part of E relating to units billed (ALG-06 step 3)
    k: Fraction  # carrying cost per unit
    c_rec: Fraction  # recovery cost per unit
    p_ref: Fraction  # refund price per unit
    window_end: date | None
    returned_before_E: Fraction  # min(units returned by the latest return event, E before it)
    version_key: str | None  # the RETURN_RATE version in force
    expired: bool  # the return window of that version has ended (S09-R-26)
    expiry_effect: int  # posted revenue effect of the expiry, minor units (TIME, CLOSE_RELEASE)
    # (event key, min(units returned, E before the return)) for every return through the date, in
    # ENG-06 order: the JET-07d quantities of stage 10 (S10-R-16; ENC-12).
    returns_before_E: tuple[tuple[str, Fraction], ...] = ()
    # S09-R-23a (D-91): U_b = the counted lines' amount ÷ p_ref, the lines themselves, the status
    # updates skipped and the memo-only lines at the date, and the billing mode at the date.
    units_billed: Fraction = Fraction(0)
    billed_lines: tuple[BilledLine, ...] = ()
    status_updates_skipped: int = 0
    memo_only_lines: int = 0
    billing_mode: str = "ERP"
    minor_unit: int = 0  # μ of the transaction currency, for the units-billed node params
    as_of: date | None = None  # the measurement date d
    # The ``return_refundable_units`` node stage 09 emitted for this state, which the stage 10
    # RETURN component cites as input 0 (``rl.return.v2``); None when no returns target was traced.
    e_b_node_id: str | None = None


@dataclass(frozen=True, slots=True)
class BilledLine:
    """One input of ``returns.units_billed.v1`` (S09-R-23a; D-91 C606-01 (7)).

    A direct line contributes its amount; a document with unreferenced lines contributes the
    obligation's S10-R-01 share of its unreferenced total, recomputed by ``largest_remainder`` over
    ``keys`` and ``weights`` (D-88 L7-5-Q-3). ``value`` is the amount the trace cites (currency
    units); ``contribution`` is what enters U_b before ÷ p_ref.
    """

    ref_id: str  # the line event key, or the first counted unreferenced line of the document
    value: Fraction  # the direct line amount, or the document's unreferenced total
    contribution: Fraction  # the amount attributed to the obligation
    keys: tuple[str, ...] = ()  # S10-R-01 keys of an unreferenced document; () for a direct line
    weights: tuple[Fraction, ...] = ()
    detail: Mapping[str, str] = MappingProxyType({})  # further SourceRef detail members

    @property
    def apportioned(self) -> bool:
        """Whether the input is an unreferenced document total apportioned under S10-R-01."""
        return bool(self.keys)


@dataclass(frozen=True, slots=True)
class Expected:
    """E at a date, E before window expiry, the version in force and the formula params."""

    value: Fraction
    unexpired: Fraction
    pin: ReturnPin | None
    params: Mapping[str, str]
    base: Fraction | None = None  # the pin's expected units at the date (a portfolio rate × N)


@dataclass(frozen=True, slots=True)
class Reversal:
    """One return under ``RESTORE_REMAINING_QUANTITY``: exact revenue after it (S09-R-25)."""

    event_key: str
    revenue: Fraction
    params: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class ReturnTarget:
    """The exact ``FIXED`` target of a units obligation with returns and its trace inputs."""

    scope: str
    exact: Fraction
    params: Mapping[str, str]  # returns.revenue_target.v1
    expected: Expected | None  # REDUCE_CONTRACT_QUANTITY
    reversals: tuple[Reversal, ...]  # RESTORE_REMAINING_QUANTITY, in ENG-06 order


def _invariant(message: str, ob: ObligationState, **detail: str) -> EngineError:
    return EngineError(
        "ENGINE_INVARIANT_VIOLATED", message, subject_key=ob.subject_key, detail=detail
    )


def _freeze(params: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(sorted(params.items())))


def _evaluate(
    ob: ObligationState, formula_id: str, inputs: Sequence[Fraction], params: Mapping[str, str]
) -> Fraction:
    try:
        return FORMULAS[formula_id](inputs, params)
    except ValueError as error:
        raise EngineError(
            "NON_FINITE_AMOUNT",
            "the returns target is undefined for the obligation",
            subject_key=ob.subject_key,
            formula_id=formula_id,
            detail={"rule": "CV-32"},
        ) from error


def _minor_unit(ctx: BookContext) -> int:
    spec = ctx.currencies.get(ctx.txn_currency)
    if spec is None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "the transaction currency is absent from the currency table",
            detail={"rule": "CV-30", "currency": ctx.txn_currency},
        )
    return spec.minor_unit


def policy(ctx: BookContext, st: AllocatedState, ob: ObligationState, code: str) -> str:
    """A resolved POL-051 to POL-053 value: the return path's, else the book's (S04-R-08b)."""
    path = st.return_paths.get(ob.subject_key)
    value: object = None if path is None else path.policy.get(code)
    if value is None:
        value = ctx.policies.value(
            code, contract=ob.contract_key, obligation=ob.subject_key, entity=ob.performing_entity
        )
    if not isinstance(value, str) or value not in POLICY_OPTIONS[code]:
        raise _invariant("a returns policy value is unknown", ob, rule="S09-R-24", policy=code)
    return value


def pin_at(path: ReturnPath, d: date) -> ReturnPin | None:
    """The ``RETURN_RATE`` pin with the greatest effective date on or before ``d``."""
    found: ReturnPin | None = None
    for pin in path.pins:
        if pin.effective_date <= d:
            found = pin
    return found


def unit_rate(path: ReturnPath, ob: ObligationState, d: date) -> Fraction:
    """r = X ÷ Q of the ``FIXED`` segment in force at ``d`` (ALG-06 §2.7.1; D-88 L7-5-Q-1).

    The latest ``FIXED`` segment of ``ob`` with effective date on or before ``d``, in segment
    order, over ``ob.quantity``: the selection and divisor of stage 13 ``_rates`` (L2-2-Q-6), so
    stage 09 targets and the stage 04 memo use one r (S04-R-08a/b; S09-R-23 [J]). The stage 04
    inception publication ``path.r`` applies only when no ``FIXED`` segment is in force or Q = 0.
    """
    if ob.quantity != 0:
        in_force = [
            seg for seg in ob.segments if seg.component == "FIXED" and seg.effective_date <= d
        ]
        if in_force:
            return in_force[-1].x_exact / ob.quantity
    found: Fraction | None = None
    for when, rate in path.r:
        if when <= d:
            found = rate
    if found is None:
        raise _invariant("the return path has no unit rate at the date", ob, rule="S09-R-23")
    return found


def _returns(
    st: AllocatedState, ob: ObligationState, d: date, position: Position | None
) -> list[EventView]:
    return [
        ev
        for ev in st.measure_events
        if ev.event_type == "RETURN_RECORDED"
        and progress_events.admitted(ev, d, position)
        and progress_events.concerns(ev, ob)
    ]


def expected_units(
    ctx: BookContext,
    st: AllocatedState,
    ob: ObligationState,
    d: date,
    *,
    kept: Fraction,
    position: Position | None = None,
    transferred: Fraction | None = None,
) -> Expected:
    """E of ALG-06 step 1 at ``d`` over ``kept`` = N − Y (§9.2.7 ``return_state``; S09-R-26).

    A portfolio pin stating only a rate expects rate × ``transferred`` units (S04-R-08; PT-06).
    E = 0 from ``window_end_date``; a measurement positioned among the events of that day comes
    before the expiry and carries param ``expiry_pending`` (D-87 L6-5-Q-25).
    """
    path = st.return_paths.get(ob.subject_key)
    pin = None if path is None else pin_at(path, d)
    params: dict[str, str] = {
        "as_of": d.isoformat(),
        "kept": rational_param(kept),
        "model": policy(ctx, st, ob, MODEL_POLICY),
        "scope": policy(ctx, st, ob, SCOPE_POLICY),
    }
    if pin is None:
        frozen = _freeze(params)
        return Expected(_evaluate(ob, EXPECTED_FORMULA, (), frozen), Fraction(0), None, frozen)
    returned_after = sum(
        (
            progress_events.quantity(ev, ob)
            for ev in _returns(st, ob, d, position)
            if ev.effective_date > pin.effective_date
        ),
        Fraction(0),
    )
    params["returned_after"] = rational_param(returned_after)
    if pin.window_end_date is not None:
        params["window_end"] = pin.window_end_date.isoformat()
        if position is not None and d == pin.window_end_date:
            params["expiry_pending"] = "true"  # the expiry sorts after the day's events
    frozen = _freeze(params)
    base = _pinned_units(ob, pin, transferred)
    value = _evaluate(ob, EXPECTED_FORMULA, (base,), frozen)
    unexpired = Fraction(0)
    if params["model"] != "ACTUAL_RETURNS_ONLY" and params["scope"] != RESTORE:
        unexpired = min(max(Fraction(0), base - returned_after), max(Fraction(0), kept))
    return Expected(value, unexpired, pin, frozen, base)


def _pinned_units(ob: ObligationState, pin: ReturnPin, transferred: Fraction | None) -> Fraction:
    """The pin's expected units: ``expected_quantity``, or a portfolio rate × units transferred."""
    if pin.rate is None:
        return pin.expected_quantity
    if transferred is None:
        raise _invariant("a portfolio return rate needs the units transferred", ob, rule="PT-06")
    return pin.rate * transferred


def target(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    *,
    position: Position | None = None,
) -> ReturnTarget | None:
    """The ALG-06 target of a units obligation, or None when the units measure alone applies.

    None for another measure, for ``REDUCE_CONTRACT_QUANTITY`` without a return path (E = 0) and
    for ``RESTORE_REMAINING_QUANTITY`` before the first return since the segment's boundary.
    """
    if str(ob.recognition_method) not in UNITS_METHODS:
        return None
    if policy(ctx, st, ob, SCOPE_POLICY) == RESTORE:
        return _restore(ctx, st, contract, ob, seg, d, position)
    path = st.return_paths.get(ob.subject_key)
    if path is None:
        return None
    if seg.basis != "INCEPTION":
        # ALG-06 step 2 is stated on the inception basis; a prospective segment has no published
        # composition with expected returns (L1-3-Q-12), so it fails closed (C-09).
        raise _invariant("expected returns since a boundary are not specified", ob, rule="S09-R-23")
    counts = progress_events.tally(ctx, st, contract, ob, d, position)
    expected = expected_units(
        ctx,
        st,
        ob,
        d,
        kept=counts.counted - counts.returned,
        position=position,
        transferred=counts.counted,
    )
    params = _freeze(
        {
            "as_of": d.isoformat(),
            "expected": rational_param(expected.value),
            "returned": rational_param(counts.returned),
            "scope": REDUCE,
            "transferred": rational_param(counts.counted),
            "unit_rate": rational_param(unit_rate(path, ob, d)),
        }
    )
    exact = _evaluate(ob, TARGET_FORMULA, (expected.value,), params)
    return ReturnTarget(REDUCE, exact, params, expected, ())


def _restore(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    seg: AllocationSegment,
    d: date,
    position: Position | None,
) -> ReturnTarget | None:
    prospective = seg.basis == "PROSPECTIVE"
    boundary = progress_events.boundary_key(st, ob, seg) if prospective else None
    base_kept = seg.base_progress.delivered_cum if prospective else Fraction(0)
    base_revenue = seg.base_revenue_exact if prospective else Fraction(0)
    option = progress_events.control_trigger_option(ctx, ob)
    outcome = progress_events.repurchase_outcome(ctx, contract, ob)
    rate = policy(ctx, st, ob, RATE_POLICY)
    common = {
        "base_kept": rational_param(base_kept),
        "quantity": rational_param(seg.totals.quantity),
        "x_exact": rational_param(seg.x_exact),
    }
    kept = kept_prev = Fraction(0)
    reversals: list[Reversal] = []
    for ev in st.measure_events:
        if not progress_events.admitted(ev, d, position) or not progress_events.concerns(ev, ob):
            continue
        if boundary is not None and ev.order_key <= boundary:
            continue  # measured in the segment's base (CV-62; L1-3-Q-10)
        if ev.event_type == "DELIVERY_RECORDED":
            reason = progress_events.hold_reason(
                ctx, contract, ob, ev, option=option, outcome=outcome
            )
            if reason is None:
                kept += progress_events.quantity(ev, ob)
        elif ev.event_type == "RETURN_RECORDED":
            returned = progress_events.quantity(ev, ob)
            params = {
                **common,
                "as_of": ev.effective_date.isoformat(),
                "event_key": ev.event_key,
                "kept_before": rational_param(kept),
                "kept_prev": rational_param(kept_prev),
                "rate": rate,
                "returned": rational_param(returned),
            }
            if rate == AVERAGE_CARRYING_RATE:
                params["a_posted"] = str(seg.a_posted)
                params["minor_unit"] = str(_minor_unit(ctx))
            inputs: tuple[Fraction, ...] = ()
            if reversals:
                params["revenue_prev"] = rational_param(reversals[-1].revenue)
                inputs = (reversals[-1].revenue,)
            else:
                params["base_revenue_exact"] = rational_param(base_revenue)
            frozen = _freeze(params)
            revenue = _evaluate(ob, REVERSAL_FORMULA, inputs, frozen)
            reversals.append(Reversal(ev.event_key, revenue, frozen))
            kept -= returned
            kept_prev = kept
    if not reversals:
        return None
    target_params = _freeze(
        {
            "as_of": d.isoformat(),
            "kept": rational_param(kept),
            "kept_at_return": rational_param(kept_prev),
            "quantity": common["quantity"],
            "revenue_at_return": rational_param(reversals[-1].revenue),
            "scope": RESTORE,
            "x_exact": common["x_exact"],
        }
    )
    exact = _evaluate(ob, TARGET_FORMULA, (reversals[-1].revenue,), target_params)
    return ReturnTarget(RESTORE, exact, target_params, None, tuple(reversals))


@dataclass(frozen=True, slots=True)
class _Billing:
    lines: tuple[BilledLine, ...]
    status_updates_skipped: int
    memo_only_lines: int
    mode: str


def _billing(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    d: date,
    position: Position | None,
) -> _Billing:
    """The ``BILLING_RECORDED`` lines counted for ``ob`` at ``d`` (ALG-06 step 3; S09-R-23a).

    One line per S10-R-07 identity (contract, ``invoice_number``, ``line_external_id``) tracked at
    contract scope over the whole ENG-06 stream, before ``admitted()`` and before the direct or
    unreferenced filter (D-88 L7-5-Q-3 as clarified by D-91): a same-amount noncancellable repeat
    is a status update that adds nothing; a repeat still cancellable is another line. A kept line
    counts when its S10-R-06 unconditional date under ``billing_mode_at`` at the line's own date is
    not None and ≤ ``d``: ``ERP`` the line's effective date; ``ENGINE`` a noncancellable line's
    effective date, else max(line date, min(the first applied ``PAYMENT_RECEIVED`` naming its
    invoice, the identity's first same-amount noncancellable update, which dates the FIRST-SEEN
    line only: a repeat flagged cancellable stays memo-only until a receipt applied to its invoice,
    S10-R-07 "never changes the first line's attribution", the supervisor's ruling on policy edge
    A, as stage 10 reads it)); a memo-only line contributes nothing.
    Direct lines name ``ob``; the unreferenced lines of a document (no payload ``obligation_key``)
    are apportioned once by largest remainder over the posted allocations at the document date of
    the contract's non-VC obligations with the header's contracting entity, or over their resolved
    SSPs when those sum to 0 (S10-R-01). Credit memos never enter the base (D-91 C606-01 (6)).
    Computed from this stage's own state; the identity, the first-update map and the S10-R-06
    date are the stage-neutral kernel helpers (``unconditional_source``; D-91 05g).
    """
    mu = _minor_unit(ctx)
    entity_code = contract.header.contracting_entity_code
    entity = ctx.entities.get(entity_code)
    if entity is None:
        raise _invariant("the contracting entity has no calendar", ob, rule="CV-12")
    classified = tuple(
        billing_identity.iter_billing_lines(st.measure_events, contract_key=ob.contract_key)
    )
    # The first same-amount, same-obligation noncancellable update of each identity, keyed by the
    # first-seen line it updates (the kernel's ``BillingLine.line``): it dates that line alone.
    # The map and the date are the kernel's (``first_updates`` / ``unconditional_source``; one
    # home with stages 04 and 10; D-91 05g, lane ENG-C6).
    first_update = billing_identity.first_updates(st.measure_events, contract_key=ob.contract_key)
    skipped = sum(
        1
        for item in classified
        if item.is_status_update and progress_events.admitted(item.event, d, position)
    )
    paid_on: dict[str, list[EventView]] = {}  # invoice number -> applied receipts (S10-R-06)
    for ev in st.measure_events:
        if ev.event_type != "PAYMENT_RECEIVED" or ev.contract_key != ob.contract_key:
            continue
        applied = ev.payload.get("applied_invoice_numbers") or ()
        if isinstance(applied, list | tuple):
            for number in applied:
                paid_on.setdefault(str(number), []).append(ev)
    lines: list[BilledLine] = []
    documents: dict[tuple[str, date], list[tuple[EventView, EventView, int]]] = {}
    memo_only = 0
    for ev in billing_identity.kept_lines(st.measure_events, contract_key=ob.contract_key):
        direct = progress_events.concerns(ev, ob)
        unreferenced = not direct and ev.payload.get("obligation_key") in (None, "")
        if not direct and not unreferenced:
            continue
        amount = ev.payload.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, str | int | Decimal | Fraction):
            raise _invariant(
                "a billing event carries no amount", ob, rule="CV-45", event_key=ev.event_key
            )
        exact = money.to_fraction(amount)
        source: EventView = ev
        mode = billing_mode_at(ctx.policies, entity, ev.effective_date)  # per kept line, its date
        if billing_identity.is_cancellable(ev) and mode == BILLING_MODE_ENGINE:
            number = str(ev.payload.get("invoice_number") or "")
            dated = billing_identity.unconditional_source(
                ev, update=first_update.get(ev.event_key), receipts=paid_on.get(number, ())
            )
            if dated is None:
                if progress_events.admitted(ev, d, position):
                    memo_only += 1
                continue  # memo-only: the right is not yet unconditional (S10-R-06)
            source = dated  # the L2-4-Q-11 line-date floor is the kernel's
        if not progress_events.admitted(ev, d, position):
            continue
        if not progress_events.admitted(source, d, position):
            continue  # unconditional after d
        if direct:
            detail = {"member": "amount", "value": money.format_exact(exact)}
            if source is not ev:
                detail["unconditional_source"] = source.event_key
            lines.append(BilledLine(ev.event_key, exact, exact, detail=MappingProxyType(detail)))
            continue
        key = (str(ev.payload.get("invoice_number") or ""), ev.effective_date)
        documents.setdefault(key, []).append((ev, source, money.round_half_up(exact, mu)))
    for (number, on), parts in documents.items():
        unreferenced_total = sum(part for _, _, part in parts)
        if unreferenced_total == 0:
            continue
        keys, weights = _attribution_weights(st, contract, ob.contract_key, on)
        if ob.subject_key not in keys or sum(weights, Fraction(0)) <= 0:
            continue  # stage 10 owns the S10-R-01 invariant for a document with no weight
        shares = money.largest_remainder(unreferenced_total, weights, keys)
        total = Fraction(unreferenced_total, 10**mu)
        detail = {
            "member": "amount",
            "value": money.format_exact(total),
            "document": number,
            "lines": "|".join(part_ev.event_key for part_ev, _, _ in parts),
        }
        if any(source is not part_ev for part_ev, source, _ in parts):
            detail["unconditional_source"] = "|".join(source.event_key for _, source, _ in parts)
        lines.append(
            BilledLine(
                parts[0][0].event_key,
                total,
                Fraction(shares[keys.index(ob.subject_key)], 10**mu),
                tuple(keys),
                tuple(weights),
                MappingProxyType(detail),
            )
        )
    return _Billing(tuple(lines), skipped, memo_only, billing_mode_at(ctx.policies, entity, d))


def _billed_lines(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    d: date,
    position: Position | None,
) -> tuple[BilledLine, ...]:
    """The counted lines of ``ob`` at ``d`` (S09-R-23a); see ``_billing``."""
    return _billing(ctx, st, contract, ob, d, position).lines


def _billed(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    d: date,
    position: Position | None,
) -> Fraction:
    """Billed amount of ``ob`` at ``d`` for E_b: Σ contributions of ``_billed_lines``."""
    return sum(
        (line.contribution for line in _billed_lines(ctx, st, contract, ob, d, position)),
        Fraction(0),
    )


def _attribution_weights(
    st: AllocatedState, contract: ContractView, contract_key: str, on: date
) -> tuple[list[str], list[Fraction]]:
    """S10-R-01 apportionment keys and weights of an unreferenced document dated ``on``."""
    entity = contract.header.contracting_entity_code
    candidates = sorted(
        (
            other
            for other in st.obligations
            if other.contract_key == contract_key
            and other.contracting_entity == entity
            and not (other.is_vc_line or str(other.obligation_kind) == "VC_LINE")
        ),
        key=lambda other: other.subject_key,
    )
    weights: list[Fraction] = []
    for other in candidates:
        in_force = [
            seg for seg in other.segments if seg.component == "FIXED" and seg.effective_date <= on
        ]
        weights.append(Fraction(in_force[-1].a_posted if in_force else 0))
    if sum(weights, Fraction(0)) == 0:
        weights = [other.resolved_ssp for other in candidates]
    return [other.subject_key for other in candidates], weights


def _posted(ctx: BookContext, seg: AllocationSegment, exact: Fraction) -> int:
    if seg.x_exact == 0:
        return 0
    ratio = min(Fraction(1), max(Fraction(0), exact / seg.x_exact))
    return money.cumulative_posted(seg.x_exact, seg.a_posted, ratio, _minor_unit(ctx))


def return_state(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    seg: AllocationSegment | None,
    d: date,
    *,
    position: Position | None = None,
) -> ReturnState:
    """``ReturnState`` of a returnable obligation at ``d`` (§9.2.7; ALG-06 steps 1 to 4).

    E_b = max(0, min(E, U_b − Y)), with U_b the units billed or paid: the counted lines' amount ÷
    p_ref (S09-R-23a; ``_billing``). The expiry effect is C(d) − C(d) with the unexpired E, the
    TIME amount the close run posts in mode ``CLOSE_RELEASE`` (S09-R-26; RCP-07, RCP-08).
    """
    path = st.return_paths.get(ob.subject_key)
    if path is None:
        raise _invariant("the obligation has no return path", ob, rule="S04-R-08b")
    counts = progress_events.tally(ctx, st, contract, ob, d, position)
    kept = counts.counted - counts.returned
    expected = expected_units(
        ctx, st, ob, d, kept=kept, position=position, transferred=counts.counted
    )
    pin = expected.pin
    billing = _billing(ctx, st, contract, ob, d, position)
    billed_amount = sum((line.contribution for line in billing.lines), Fraction(0))
    billed_units = Fraction(0) if path.p_ref == 0 else billed_amount / path.p_ref
    returned_before = Fraction(0)
    by_event: list[tuple[str, Fraction]] = []
    for ret in _returns(st, ob, d, position):
        before = Position(ret.order_key, inclusive=False)
        prior = progress_events.tally(ctx, st, contract, ob, ret.effective_date, before)
        prior_expected = expected_units(
            ctx,
            st,
            ob,
            ret.effective_date,
            kept=prior.counted - prior.returned,
            position=before,
            transferred=prior.counted,
        )
        by_event.append(
            (ret.event_key, min(progress_events.quantity(ret, ob), prior_expected.value))
        )
    if by_event:
        returned_before = by_event[-1][1]
    window_end = None if pin is None else pin.window_end_date
    # D-87 L6-5-Q-25: expired from the end of the window end date, after that day's events.
    expired = window_end is not None and (d > window_end or (d == window_end and position is None))
    effect = 0
    if expired and seg is not None and policy(ctx, st, ob, SCOPE_POLICY) == REDUCE:
        rate = unit_rate(path, ob, d)
        effect = _posted(ctx, seg, rate * (kept - expected.value)) - _posted(
            ctx, seg, rate * (kept - expected.unexpired)
        )
    return ReturnState(
        N=counts.counted,
        Y=counts.returned,
        E=expected.value,
        E_b=max(Fraction(0), min(expected.value, billed_units - counts.returned)),
        k=Fraction(0)
        if pin is None or pin.carrying_cost_per_unit is None
        else pin.carrying_cost_per_unit,
        c_rec=(
            Fraction(0)
            if pin is None or pin.recovery_cost_per_unit is None
            else pin.recovery_cost_per_unit
        ),
        p_ref=path.p_ref,
        window_end=window_end,
        returned_before_E=returned_before,
        version_key=None if pin is None else pin.version_key,
        expired=expired,
        expiry_effect=effect,
        returns_before_E=tuple(by_event),
        units_billed=billed_units,
        billed_lines=billing.lines,
        status_updates_skipped=billing.status_updates_skipped,
        memo_only_lines=billing.memo_only_lines,
        billing_mode=billing.mode,
        minor_unit=_minor_unit(ctx),
        as_of=d,
    )


def refundable_units_node_id(ob: ObligationState, period_key: str) -> str:
    """The id of the ``return_refundable_units`` node ``emit`` publishes for ``ob`` at a period."""
    return f"{REFUNDABLE_UNITS_MEASURE}:{ob.subject_key}:{period_key}"


def _emit_units(
    tb: TraceBuilder,
    ob: ObligationState,
    period_key: str,
    state: ReturnState,
    expected_node_id: str,
) -> str:
    """``return_units_billed`` and ``return_refundable_units`` of one period (S09-R-23a; D-91).

    U_b cites one ``SourceRef`` per counted line: a direct line with its amount, an unreferenced
    document with its unreferenced total and the S10-R-01 ``keys`` and ``weights`` indexed by input
    position, so ``reevaluate`` recomputes the share by ``largest_remainder`` (DG-KRN-EXP-04). E_b
    cites the expected-units node and the units-billed node; ``rl.return.v2`` cites E_b.
    """
    if state.as_of is None:
        raise _invariant("a return state carries no measurement date", ob, rule="S09-R-23a")
    sources: list[str | SourceRef] = []
    params: dict[str, str] = {
        "as_of": state.as_of.isoformat(),
        "memo_only_lines": str(state.memo_only_lines),
        "minor_unit": str(state.minor_unit),
        "mode": state.billing_mode,
        "p_ref": rational_param(state.p_ref),
        "status_updates_skipped": str(state.status_updates_skipped),
    }
    apportioned: list[str] = []
    for index, line in enumerate(state.billed_lines):
        sources.append(SourceRef("contract_event", line.ref_id, dict(line.detail)))
        if line.apportioned:
            apportioned.append(str(index))
            params[f"keys_{index}"] = "|".join(line.keys)
            params[f"weights_{index}"] = "|".join(rational_param(w) for w in line.weights)
    if apportioned:
        params["apportioned"] = "|".join(apportioned)
        params["key"] = ob.subject_key
    units_id = tb.node(
        measure=UNITS_BILLED_MEASURE,
        subject_key=ob.subject_key,
        period_key=period_key,
        value=state.units_billed,
        currency=None,
        minor_unit=None,
        formula_id=UNITS_BILLED_FORMULA,
        inputs=sources,
        params=params,
        narrative_key=UNITS_BILLED_FORMULA.rsplit(".v", 1)[0],
    )
    return tb.node(
        measure=REFUNDABLE_UNITS_MEASURE,
        subject_key=ob.subject_key,
        period_key=period_key,
        value=state.E_b,
        currency=None,
        minor_unit=None,
        formula_id=REFUNDABLE_UNITS_FORMULA,
        inputs=[expected_node_id, units_id],
        params={"as_of": params["as_of"], "returned_units": rational_param(state.Y)},
        narrative_key=REFUNDABLE_UNITS_FORMULA.rsplit(".v", 1)[0],
    )


def emit(
    tb: TraceBuilder,
    ob: ObligationState,
    period_key: str,
    returns_target: ReturnTarget,
    emitted: set[str],
    state: ReturnState | None = None,
) -> str:
    """Trace nodes of a returns target; returns the ``revenue_target_exact`` node id (§9.5).

    ``return_expected_units:<ob>:<period>`` carries E and cites the ``RETURN_RATE`` version. With a
    ``state`` (a period end), ``return_units_billed`` and ``return_refundable_units`` follow it
    (S09-R-23a; D-91 C606-01 (7)); their id is ``refundable_units_node_id``. A
    ``return_reversal@<event key>:<ob>:-`` node per return is emitted once, whatever the number of
    period ends that cite it (CV-50).
    """
    inputs: list[str | SourceRef] = []
    if returns_target.expected is not None:
        expected = returns_target.expected
        sources: list[str | SourceRef] = []
        if expected.pin is not None:
            base = expected.pin.expected_quantity if expected.base is None else expected.base
            value = money.format_exact(base)
            detail = {"member": "expected_quantity", "value": value}
            if expected.pin.rate is not None:  # a portfolio rate × units transferred (PT-06)
                detail = {"member": "rate", "rate": money.format_exact(expected.pin.rate)}
                detail["value"] = value
            sources.append(SourceRef("estimate_version", expected.pin.version_key, detail))
        expected_id = tb.node(
            measure="return_expected_units",
            subject_key=ob.subject_key,
            period_key=period_key,
            value=expected.value,
            currency=None,
            minor_unit=None,
            formula_id=EXPECTED_FORMULA,
            inputs=sources,
            params=expected.params,
            narrative_key=EXPECTED_FORMULA.rsplit(".v", 1)[0],
        )
        inputs.append(expected_id)
        if state is not None:
            _emit_units(tb, ob, period_key, state, expected_id)
    previous: str | None = None
    for reversal in returns_target.reversals:
        node_id = f"return_reversal@{reversal.event_key}:{ob.subject_key}:-"
        if node_id not in emitted:
            tb.node(
                measure=f"return_reversal@{reversal.event_key}",
                subject_key=ob.subject_key,
                period_key=None,
                value=reversal.revenue,
                currency=None,
                minor_unit=None,
                formula_id=REVERSAL_FORMULA,
                inputs=[] if previous is None else [previous],
                params=reversal.params,
                narrative_key=REVERSAL_FORMULA.rsplit(".v", 1)[0],
            )
            emitted.add(node_id)
        previous = node_id
    if previous is not None:
        inputs.append(previous)
    return tb.node(
        measure="revenue_target_exact",
        subject_key=f"{ob.subject_key}#FIXED",
        period_key=period_key,
        value=returns_target.exact,
        currency=None,
        minor_unit=None,
        formula_id=TARGET_FORMULA,
        inputs=inputs,
        params=returns_target.params,
        narrative_key=TARGET_FORMULA.rsplit(".v", 1)[0],
    )


def reduction_from_state(
    path: ReturnPath, ob: ObligationState, state: ReturnState, d: date, mu: int
) -> int:
    """ρ(d) = round(r × (Y + E)) of a ``ReturnState`` measured at ``d``, in minor units (S09-R-23).

    r is ``unit_rate`` at ``d``. Stage 15 reads the states stage 09 publishes at performing-entity
    period ends through this function (ENGINE_SPEC_B S15-R-12 basis; D-91). No formula id: it
    derives values the ``return_expected_units`` and segment nodes already trace.
    """
    return money.round_half_up(unit_rate(path, ob, d) * (state.Y + state.E), mu)


def reduction(
    ctx: BookContext,
    st: AllocatedState,
    contract: ContractView,
    ob: ObligationState,
    seg: AllocationSegment | None,
    d: date,
    *,
    position: Position | None = None,
) -> int:
    """The S09-R-23 expected-return reduction of ``ob`` dated at ``d``, in minor units.

    0 when the obligation has no return path, when POL-053 is not ``REDUCE_CONTRACT_QUANTITY`` or
    when no ``FIXED`` segment is in force; else ``round_half_up(r × (Y + E), μ)`` over
    ``return_state`` at ``d`` (and ``position``). One composition for the stage 09
    ``ObligationMeasures.returns_reduction`` and the stage 15 RPO basis at a segment boundary
    (ENGINE_SPEC_B S15-R-12; D-91).
    """
    path = st.return_paths.get(ob.subject_key)
    if path is None or seg is None or policy(ctx, st, ob, SCOPE_POLICY) != REDUCE:
        return 0
    state = return_state(ctx, st, contract, ob, seg, d, position=position)
    return reduction_from_state(path, ob, state, d, _minor_unit(ctx))
