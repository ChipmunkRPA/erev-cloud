"""Stage 13: the book loop, stage keys and framework switches (ENGINE_SPEC_B §13; END-7).

``run_books(cb, stages)`` runs the stages once per book, in ``BOOK_ORDER``, for every book whose
entity set is not empty (S13-R-01; RCP-11). Before any book runs, POL-005 ``DELTA`` requires
``LEGACY`` in POL-007 for the entity and period (S13-INV-05). Each framework book gets its
``BookContext`` (horizon per CV-13) and its own trace builder. A stage whose key
(``memo.stage_key``) another book already computed in this call reuses that output, relabelled for
the book, and aliases its nodes (S13-R-02, S13-R-04; RCP-12, RCP-13). Stage 02 receives the
canonical bundle and folds statuses and terms; its deposit ledger folds once after stage 03
(``run_deposits``), so the 25-7(a) time test reads the classification and the refined state replaces
``published["02"]`` before stage 04 (D-91 gaps (iii)); stages 06 to 08 run as the boundary fold of
Table 0.3-A over the stage 05 state, keyed by the chained keys of stages 06, 07 and 08 (CV-11);
stage 12 receives ``rates`` and stage 14 ``posted``, ``voided`` (the member contracts whose new
events include a ``CONTRACT_VOIDED``) and ``new_events`` (the first-included events per contract,
in ENG-06 order, from the bundle stream before the S01-R-12 removal; S14-R-13a) from the canonical
bundle (L2-5-Q-11, L2-5-Q-4, L2-5-Q-30; D-98 80, D-98 95). The stage 09 to 11 flows stage 12
reads bind in END-9, so the real stage 12 fails closed without them (L2-5-Q-21). The ``LEGACY``
book runs after the framework books: ``legacy_book`` folds the pre-standard revenue events and,
when the stage list holds stage 14, posts its JET-15 lines over the primary book's obligations; the
primary book's result carries the version measures of S13-R-10 (§13.2.4; END-8). ``switches``
holds POLICIES §6.2 as data (S13-R-06). Standard library only (DG-ARC-02)."""

from __future__ import annotations

import dataclasses
import functools
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from fractions import Fraction
from types import MappingProxyType
from typing import Final

from erev_engine import ENGINE_VERSION, dates
from erev_engine.bundle import BookInput, EntityInput, PayableInput, ProposalOut
from erev_engine.canonical import sha256_hex
from erev_engine.enums import BookCode
from erev_engine.errors import EngineError
from erev_engine.money import format_exact, round_half_up, to_fraction
from erev_engine.stages import (
    BOUNDARY_HANDLERS,
    StageSpec,
    s02_contract_identification,
    s04_transaction_price,
    s06_modifications,
    s08_estimates_late_events,
    s12_fx_entities,
    s14_posting,
    s15_disclosures,
)
from erev_engine.stages.s01_canonicalize import (
    contract_entity_subject_key,
    encode_key,
    member_in_force,
    payload_date,
    payload_fraction,
    payload_text,
)
from erev_engine.stages.s02_contract_identification import (
    DepositPoint,
    IdentifiedState,
    run_deposits,
)
from erev_engine.stages.s03_pob_builder import PobState
from erev_engine.stages.s05_allocation import provenance
from erev_engine.stages.s07_onboarding import baseline_of
from erev_engine.stages.s09_recognition import RecognitionState
from erev_engine.stages.s10_billing_balances import BalanceState, BillingDocumentOut
from erev_engine.stages.s10_billing_balances.billing import engine_lines_through
from erev_engine.stages.s10_billing_balances.classification import Line
from erev_engine.stages.s10_billing_balances.refund_liability import (
    CONCESSION as _CONCESSION,
)
from erev_engine.stages.s10_billing_balances.refund_liability import (
    RefundComponent,
)
from erev_engine.stages.s11_costs_loss import CostLossState
from erev_engine.stages.s12_fx_entities import ControlFlow, FxFlows, MonetaryFlow, ReceivableFlow
from erev_engine.stages.s13_books import legacy_book, output_measures
from erev_engine.stages.s13_books.memo import FOLD_STAGES, Memo, chain
from erev_engine.stages.s14_posting import DEPOSIT_PART_MEASURES, PartInputs
from erev_engine.stages.state import (
    AllocatedState,
    BookContext,
    CanonicalBundle,
    ContractView,
    EventView,
    ObligationState,
    PolicyResolver,
    Quota1,
    Target,
    TpBuildUp,
)
from erev_engine.trace import SourceRef, Trace, TraceBuilder

__all__ = [
    "BOOK_ORDER",
    "BookResult",
    "Check",
    "CostsView",
    "book_context",
    "costs_view",
    "fold",
    "run_books",
]

# Called after every stage (and the boundary fold) with the book code and the stage state; compute
# raises CV-15 from it (CV-42). ``None`` names the book-independent stage 01.
Check = Callable[[str | None, object], None]
# Table 14-A producer measures the book loop binds for stage 14 (L2-5-Q-24).
_RELIEF: Final = "revenue_relief_cum"
# The stage 10 agent relief max(G_t, R_t) and supplier share S_t (D-87 L4-3-Q-24 (c)).
_AGENT_RELIEF: Final = "agent_relief_cum"
_AGENT_SUPPLIER: Final = "supplier_share_cum"
_RELIEF_BY_CAUSE: Final = "revenue_relief"
_RECLASS: Final = "netting_reclass_amount"
_INVOICE: Final = "billed_unconditional_cum"
_INVOICE_TAX: Final = "sales_tax_billed_cum"  # JET-03 tax side per obligation (S10-R-02)
_ENGINE_BILLING: Final = "ENGINE"
_ERP_BILLING: Final = "ERP"  # D-87 L6-5-Q-14
# ENGINE_SPEC_B S09-R-02: the components whose realised amounts the transaction price carries
# (ROYALTY, ENC-8; PERIOD_VC, ENC-6), re-priced at the version date by _version_price.
REALISED_COMPONENTS: Final = frozenset({"ROYALTY", "PERIOD_VC"})
# The S10-INV-05 components outside billing and relief, as stages 02, 04 and 10 publish them.
_FINANCING: Final = "financing_interest_cum"  # EMOD-18 (S04-R-12, S04-R-13)
_DEPOSIT: Final = "deposit_to_contract_liability_cum"  # EMOD-12 (S02-R-08)
# The EMOD-22 measures stage 14 posts by JET-14 promised, release and share-based, plus the
# composed release it checks (Table 14-A; ENGINE_SPEC_B S10-R-26, S14-R-11; D-91).
_CPC_PARTS_BOUND: Final = frozenset(
    {
        "consideration_payable",
        "incentive_release_ordinary_cum",
        "share_based_reduction_cum",
        "incentive_release_cum",
    }
)
_PAYABLE_MEMBER: Final = "consideration_payable"  # 04 API-S-ConsiderationPayable list (S04-R-14)
# The stage 02 dated deposit movements as monetary flows (S02-R-08; S12-R-19, S12-R-20; L6-5):
# (DepositPoint member, flow reason, direction, control side).
_DEPOSIT_MOVES: Final = (
    ("received_cum", "RECEIPT", "INCREASE", None),
    ("refunded_cum", "REFUND", "DECREASE", None),
    ("to_revenue_cum", "EVENT_25_7", "DECREASE", None),
    ("to_contract_liability_cum", "CRITERIA_MET", "DECREASE", "CREDIT"),
)
_NONCASH: Final = "noncash_asset_recognised_cum"  # EMOD-23 (S04-R-18)
# The EMOD-23 measures stage 14 posts by JET-17 unconditional and receipt (Table 14-A).
_NONCASH_PARTS_BOUND: Final = frozenset({"noncash_asset_recognised_cum", "noncash_received_cum"})
# The stage 11 measures stage 14 posts by JET-09a to JET-09f (Table 14-A; lane L5-5).
_COST_PARTS_BOUND: Final = frozenset(
    {
        "cost_accelerated_cum",
        "cost_amortised_cum",
        "cost_capitalised",
        "cost_clawback_cum",
        "cost_impaired_cum",
        "cost_impairment_reversed_cum",
    }
)
_WARRANTY_ACCRUAL: Final = "warranty_accrual_cum"  # EMOD-21 (S04-R-19; JET-16 accrual)
# The stage 11 required provision stage 14 posts by JET-12 (§11.5; S11-R-14; Table 14-A; D-92 (3)).
_LOSS_PROVISION: Final = "loss_provision_required"
_CONTRA: Final = "receivable_contra"  # S10-R-18
_REFUND_LIABILITY: Final = "refund_liability"  # §10.2.4
# Stage 04 names the schedule kind, stage 10 tests the part id (L4-3-Q-18).
_INCOME_CAUSES: Final = frozenset({"JET-11a", "DEFERRED"})
_EXPENSE_CAUSES: Final = frozenset({"JET-11b", "ADVANCE"})

BOOK_ORDER: Final = ("ASC606", "IFRS15", "LEGACY")  # RCP-11
_LEGACY: Final = "LEGACY"
_DELTA: Final = "DELTA"
# Boundary events whose T-CON-06 lines add consideration (S06-R-07, S06-R-21).
_WITH_LINES: Final = frozenset({"CONTRACT_AMENDED", "CONTRACT_TERMINATED"})
# ``BookResult.states`` key of the stage 08 ``LateEvents`` of the book (S08-R-10; L4-1-Q-8).
LATE_EVENTS_STATE: Final = "08/late_events"


@dataclass(frozen=True, slots=True)
class BookResult:
    """One book of ``run_books`` (§13.1): the last stage's state and the book's trace."""

    book: str  # E-02
    state: object  # the last stage's state; ``legacy_book.LegacyState`` for LEGACY (§13.2.4)
    trace: Trace
    # S13-R-10: the primary book's pre-standard version measures, when the bundle keeps LEGACY
    pre_standard: tuple[legacy_book.PreStandard, ...] = ()
    # The state of every stage the book ran, by stage number (06 to 08: the fold); assemble_output
    # reads stages 09 to 14 from it (ENGINE_SPEC §0.5)
    states: Mapping[str, object] = MappingProxyType({})


def run_books(
    cb: CanonicalBundle,
    stages: Sequence[StageSpec],
    *,
    order: Sequence[str] = BOOK_ORDER,
    check: Check | None = None,
) -> tuple[BookResult, ...]:
    """Every enabled book of the bundle through ``stages`` (ENGINE_SPEC_B §13.2.1).

    ``order`` is the processing order, a permutation of ``BOOK_ORDER`` (S13-INV-04 swaps the
    framework books); the results always follow ``BOOK_ORDER``. The LEGACY book runs last, over
    the primary book's obligations (S13-R-07, S13-R-08). ``check`` sees every stage state of every
    book, a memoised output once per book that uses it (S13-R-03). The memo is created here and
    dropped on return (S13-R-02).
    """
    if sorted(order) != sorted(BOOK_ORDER):
        raise ValueError(f"order must be a permutation of {BOOK_ORDER}")
    _assert_delta_books(cb)
    memo = Memo()
    found: dict[str, BookResult] = {}
    legacy = cb.books.get(_LEGACY)
    with_legacy = legacy is not None and bool(legacy.entity_codes)
    for code in order:
        book = cb.books.get(code)
        if code == _LEGACY or book is None or not book.entity_codes:
            continue  # S13-R-01: a book with no entity produces no result
        tb = TraceBuilder(engine_version=ENGINE_VERSION)
        ctx = book_context(cb, book)
        state, published, last_key = _run_book(ctx, cb, stages, tb, memo, check)
        allocated = _allocated(state)
        measures: tuple[legacy_book.PreStandard, ...] = ()
        if allocated is not None:
            # The post-stage output step (pre-standard measures, T-CON-08 output measures; D-97 (8)
            # T1F-Q-1 (A)) runs through the memo like a stage: a book whose chain ends on the same
            # key reuses the other book's step and ALIASES its nodes (S13-R-02; S13-INV-01 "every
            # node aliased" — lane ENG-T1F, chain 47043 P13 failure). The key covers the chain end,
            # the step's formulas and whether the book keeps pre-standard measures.
            primary = with_legacy and book.is_primary
            step = memo.run(
                _output_step_key(last_key, primary),
                code,
                tb,
                functools.partial(_output_step, ctx, cb, published, allocated, tb, primary),
            )
            measures, output = _output_step_result(step)
            if output is not None:
                published = MappingProxyType({**published, output_measures.OUTPUT_KEY: output})
        found[code] = BookResult(code, state, tb.build(root_measures={}), measures, published)
    if legacy is not None and with_legacy:
        found[_LEGACY] = _run_legacy(cb, legacy, stages, found, check)
    return tuple(found[code] for code in BOOK_ORDER if code in found)


def fold(
    ctx: BookContext,
    cb: CanonicalBundle,
    state: AllocatedState,
    tb: TraceBuilder,
    *,
    identified: IdentifiedState,
    pob: PobState,
) -> AllocatedState:
    """The boundary fold of Table 0.3-A over the stage 05 state (ENGINE_SPEC §0.3; CV-11)."""
    return _fold(ctx, cb, state, tb, identified, pob)


def _allocated(state: object) -> AllocatedState | None:
    """The ``AllocatedState`` a stage state carries unchanged (ENGINE_SPEC_B §0.4)."""
    if isinstance(state, AllocatedState):
        return state
    found = getattr(state, "allocated", None)
    return found if isinstance(found, AllocatedState) else None


def _run_legacy(
    cb: CanonicalBundle,
    book: BookInput,
    stages: Sequence[StageSpec],
    framework: Mapping[str, BookResult],
    check: Check | None,
) -> BookResult:
    """S13-R-07, S13-R-08: the LEGACY fold, posted by stage 14 over the primary book's obligations
    (the first framework book in ``BOOK_ORDER`` when none is primary)."""
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    ctx = book_context(cb, book)
    ordered = [framework[code] for code in BOOK_ORDER if code in framework]
    primary = next((item for item in ordered if cb.books[item.book].is_primary), None)
    if primary is None and ordered:
        primary = ordered[0]
    allocated = None if primary is None else _allocated(primary.state)
    spec = next((item for item in stages if item.stage == "14"), None)
    post = None if spec is None else _post_call(spec, ctx, cb, tb)
    state = legacy_book.run(ctx, cb, tb, allocated=allocated, post=post)
    if check is not None:
        check(_LEGACY, state)
    return BookResult(_LEGACY, state, tb.build(root_measures={}))


def _post_call(
    spec: StageSpec, ctx: BookContext, cb: CanonicalBundle, tb: TraceBuilder
) -> Callable[[object], object]:
    """Stage 14 over the LEGACY targets, with the posted amounts and the newly voided members
    bound (L2-5-Q-4; D-98 80)."""
    entry = spec.entry
    voided = voided_members(cb)
    new_events = new_event_keys(cb)
    return lambda fx: entry(ctx, fx, tb, posted=cb.posted, voided=voided, new_events=new_events)


def voided_members(cb: CanonicalBundle) -> tuple[str, ...]:
    """The member contracts whose NEW events include a ``CONTRACT_VOIDED`` (``EventView.is_new``:
    the stream version is past the previous stream head), sorted — the ``voided`` keyword stage 14
    binds so every reversal a void produces carries ``reason_code = VOID`` (S14-R-08; D-98 80). A
    void already behind the previous head produced its reversal in an earlier computation and
    binds nothing here."""
    return tuple(
        sorted(
            {
                event.contract_key
                for event in cb.events
                if event.event_type == "CONTRACT_VOIDED" and event.is_new
            }
        )
    )


def new_event_keys(cb: CanonicalBundle) -> tuple[tuple[str, str], ...]:
    """The ``(contract key, event key)`` pairs of the events first included in this computation —
    stream version past the previous stream head (Table 0.9-A ``is_new``) — in ENG-06 (bundle)
    order, read from the bundle stream before the S01-R-12 removal so an ``EVENT_VOIDED`` names
    itself; the ``new_events`` keyword stage 14 binds so every intent line carries the lineage of
    its cumulative delta (S14-R-13a; D-98 95). Nothing is new on a replay whose heads cover the
    stream, and a stage 14 call without the binding yields empty sets."""
    heads = cb.group.previous_stream_heads
    return tuple(
        (event.contract_key, event.event_key)
        for event in cb.bundle.events
        if event.stream_version > heads.get(event.contract_key, 0)
    )


def book_context(cb: CanonicalBundle, book: BookInput) -> BookContext:
    """The ``BookContext`` of ``book``: every entity calendar and the CV-13 horizon per entity."""
    entities = {entity.code: entity for entity in cb.bundle.entities}
    code = BookCode(book.book_code)
    return BookContext(
        book_code=code,
        framework=code,
        currencies=cb.currencies,
        txn_currency=cb.group.group.transaction_currency,
        entities=entities,
        horizon={key: _horizon(entity, book.book_code) for key, entity in sorted(entities.items())},
        policies=PolicyResolver(book.policies),
        mapping=book.account_mapping,
        trigger=cb.bundle.trigger,
        tenant_preset=cb.bundle.tenant_preset,
    )


def _horizon(entity: EntityInput, book_code: str) -> str:
    """CV-13: the last period whose state for the book is open, closing or reopened, else the last
    period of the calendar."""
    found = entity.periods[-1].period_key
    postable = [
        period.period_key
        for period in entity.periods
        if dict(period.states).get(book_code) in dates.POSTABLE_STATES
    ]
    return postable[-1] if postable else found


def _assert_delta_books(cb: CanonicalBundle) -> None:
    """S13-INV-05: POL-005 ``DELTA`` implies ``LEGACY`` in POL-007 for the entity and period."""
    for book in cb.books.values():
        enabled = {
            policy.subject_key: _book_set(policy.value)
            for policy in book.policies
            if policy.code == "books.enabled"
        }
        for policy in book.policies:
            if policy.code != "je.posting_mode" or policy.value != _DELTA:
                continue
            books = enabled.get(policy.subject_key, enabled.get("", frozenset()))
            if _LEGACY not in books:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "POL-005 DELTA requires the LEGACY book in POL-007",
                    subject_key=policy.subject_key or None,
                    detail={
                        "book_code": book.book_code,
                        "invariant": "S13-INV-05",
                        "policy": "je.posting_mode",
                        "scope": policy.subject_key,
                    },
                )


def _book_set(value: object) -> frozenset[str]:
    members: object = value.get("set", "") if isinstance(value, Mapping) else value
    if isinstance(members, str):
        return frozenset(item for item in members.split(",") if item)
    if isinstance(members, tuple):
        return frozenset(str(item) for item in members)
    return frozenset()


def _output_step_key(last_key: str, primary: bool) -> str:
    """S13-R-04 key of the post-stage output step: the chain end, the step's formula ids and the
    pre-standard measure mode (the primary book of a bundle with a LEGACY book keeps them)."""
    return sha256_hex(
        {
            "formulas": sorted(
                {
                    legacy_book.FORMULA_ID,
                    output_measures.SUM_FORMULA,
                    output_measures.ADJUSTMENT_FORMULA,
                    output_measures.UNIT_RATE_FORMULA,
                }
            ),
            "previous": last_key,
            "primary_with_legacy": primary,
            "stage": "13/output",
        }
    )


def _output_step(
    ctx: BookContext,
    cb: CanonicalBundle,
    published: Mapping[str, object],
    allocated: AllocatedState,
    tb: TraceBuilder,
    primary: bool,
) -> tuple[tuple[legacy_book.PreStandard, ...], output_measures.OutputMeasures | None]:
    """The post-stage emissions of one book: the T-CON-11 pre-standard measures (S13-R-10; zeros
    with nodes for a book that keeps none, DG-KRN-EXP-01) and the T-CON-08 output measures."""
    if primary:
        measures = legacy_book.version_measures(ctx, cb, allocated, tb)
    else:
        measures = legacy_book.zero_measures(ctx, allocated, tb)
    return measures, output_measures.publish(ctx, published, allocated, tb)


def _output_step_result(
    step: object,
) -> tuple[tuple[legacy_book.PreStandard, ...], output_measures.OutputMeasures | None]:
    if not (isinstance(step, tuple) and len(step) == 2 and isinstance(step[0], tuple)):
        raise TypeError("the output step returns (pre-standard measures, output measures)")
    measures, output = step
    if output is not None and not isinstance(output, output_measures.OutputMeasures):
        raise TypeError("the output step's second member is OutputMeasures or None")
    return tuple(measures), output


def _run_book(
    ctx: BookContext,
    cb: CanonicalBundle,
    stages: Sequence[StageSpec],
    tb: TraceBuilder,
    memo: Memo,
    check: Check | None = None,
) -> tuple[object, Mapping[str, object], str]:
    """The book's final state, its published stage states and the key of its last stage (the chain
    end, which the post-stage output step's memo key covers; S13-R-02, S13-INV-01)."""
    keys = chain(cb, ctx, stages)
    book = str(ctx.book_code)
    state: object = cb
    identified: object = None
    pob: object = None
    published: dict[str, object] = {}
    index = 0
    while index < len(stages):
        spec = stages[index]
        if spec.stage in FOLD_STAGES:
            end = index
            while end < len(stages) and stages[end].stage in FOLD_STAGES:
                end += 1
            key = keys[end - 1][1]
            state = memo.run(key, book, tb, _fold_call(ctx, cb, state, tb, identified, pob))
            published.update((item.stage, state) for item in stages[index:end])
            if check is not None:
                check(book, state)
            late = _late_events(ctx, state, tb)
            if late is not None:
                published[LATE_EVENTS_STATE] = late
            index = end
            continue
        key = keys[index][1]
        consumed = state
        state = memo.run(key, book, tb, _stage_call(spec, ctx, cb, consumed, tb, published))
        published[spec.stage] = state
        if check is not None:
            check(book, state)
        if spec.stage == "02":
            identified = state
        elif spec.stage == "03":
            state = _refine_deposits(ctx, tb, identified, state, published, book, check)
            identified = published["02"]  # the refined state, read by the fold and stage 12
            pob = state
        index += 1
    return state, MappingProxyType(published), keys[-1][1] if keys else "root"


def _refine_deposits(
    ctx: BookContext,
    tb: TraceBuilder,
    identified: object,
    pob: object,
    published: dict[str, object],
    book: str,
    check: Check | None,
) -> object:
    """The deposit fold after stage 03 (ENGINE_SPEC S02-R-07 rev 1.6; D-91 gaps (iii)).

    Stage 02 ran without its deposit ledger (``_stage_call``); with the stage 03 classification in
    scope ``run_deposits`` folds the ledger once per book, the refined ``IdentifiedState`` replaces
    ``published["02"]`` and ``PobState.identified``, and stage 04 reads the refined state. A
    stage 03 stand-in without the members leaves the states as they are.
    """
    if not isinstance(identified, IdentifiedState) or not isinstance(pob, PobState):
        return pob
    if any(identified.deposits.get(key) for key in identified.member_contract_keys):
        return pob  # a stage 02 entry that folded its own ledger (no second pass, CV-50)
    refined = run_deposits(ctx, identified, pob, tb)
    replaced = dataclasses.replace(pob, identified=refined)
    published["02"] = refined
    published["03"] = replaced
    if check is not None:
        check(book, refined)
    return replaced


def _stage_call(
    spec: StageSpec,
    ctx: BookContext,
    cb: CanonicalBundle,
    state: object,
    tb: TraceBuilder,
    published: Mapping[str, object] | None = None,
) -> Callable[[], object]:
    """The stage call with its bound keyword arguments (L2-5-Q-4, L2-5-Q-11, L2-5-Q-21).

    Stage 12 reads the stage 11 state through ``costs_view``, which binds the §12.1 flows and the
    Table 14-A producer targets stage 14 reads later from ``FxState.costs`` (END-9). Stage 15 reads
    the stage 09 state the book published, bound as ``recognition`` (L3-2-Q-26; EDS-1), the
    posted amounts, bound as ``posted`` (L3-2-Q-31; EDS-2), and the stage 10 and stage 12 states,
    bound as ``balances`` and ``fx`` (L4-3-Q-3; EDS-3).
    """
    if spec.stage == "15" and spec.entry is s15_disclosures.run:
        recognition = None if published is None else published.get("09")
        balances = None if published is None else published.get("10")
        fx = None if published is None else published.get("12")
        return lambda: spec.entry(
            ctx,
            state,
            tb,
            recognition=recognition,
            posted=cb.posted,
            balances=balances,
            fx=fx,
        )
    if spec.stage == "02" and spec.entry is s02_contract_identification.run:
        # D-91 gaps (iii): the deposit fold runs after stage 03 (``_run_book``), so stage 02 folds
        # the statuses and terms only here; ``run_deposits`` refines the state with the
        # classification in scope and replaces ``published["02"]`` before stage 04.
        return lambda: s02_contract_identification.run(ctx, cb, tb, deposits=False)
    if spec.stage == "12":
        source = state
        if spec.entry is s12_fx_entities.run and not hasattr(state, "fx_flows"):
            if not isinstance(state, CostLossState):
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "stage 12 consumes the stage 11 state",
                    detail={"rule": "L2-5-Q-21", "stage": "12"},
                )
            source = costs_view(ctx, state)
            identified = None if published is None else published.get("02")
            source = _bind_deposit_flows(ctx, source, identified)  # L6-5, FX-CHK-084-B
        return lambda: spec.entry(ctx, source, tb, rates=cb.fx)
    if spec.stage == "14":
        if spec.entry is s14_posting.run and not hasattr(state, "costs"):
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "stage 14 consumes the stage 12 state",
                detail={"rule": "L2-5-Q-24", "stage": "14"},
            )
        voided = voided_members(cb)  # S14-R-08 reason_code VOID (D-98 80)
        new_events = new_event_keys(cb)  # S14-R-13a source event lineage (D-98 95)
        return lambda: spec.entry(
            ctx, state, tb, posted=cb.posted, voided=voided, new_events=new_events
        )
    return lambda: spec.run(ctx, state, tb)


def _fold_call(
    ctx: BookContext,
    cb: CanonicalBundle,
    state: object,
    tb: TraceBuilder,
    identified: object,
    pob: object,
) -> Callable[[], object]:
    """The boundary fold over the stage 05 state as one memoised step (CV-11)."""
    return lambda: _fold(ctx, cb, state, tb, identified, pob)


def _late_events(
    ctx: BookContext, state: object, tb: TraceBuilder
) -> s08_estimates_late_events.LateEvents | None:
    """S08-R-10, S08-R-11: the stage 08 late-event findings and register facts of one book, once
    after the boundary fold (Table 0.2-A names no entry for them; L2-5-Q-1). ``_diagnostics``
    publishes the ``LATE_EVENT`` findings through ``compute`` (L4-1-Q-8)."""
    allocated = _allocated(state)
    if allocated is None:
        return None
    return s08_estimates_late_events.late_events(ctx, allocated, tb)


def _fold(
    ctx: BookContext,
    cb: CanonicalBundle,
    state: object,
    tb: TraceBuilder,
    identified: object,
    pob: object,
) -> AllocatedState:
    """The boundary fold of Table 0.3-A over the stage 05 state in ENG-06 order (CV-11)."""
    if not isinstance(state, AllocatedState):
        raise ValueError("the boundary fold consumes the stage 05 AllocatedState")
    if not isinstance(identified, IdentifiedState) or not isinstance(pob, PobState):
        raise ValueError("the boundary fold needs the stage 02 and stage 03 states")
    price = price_binding(pob)
    st = state
    proposals: list[ProposalOut] = []
    for ev in cb.boundary_events:
        priced = len(st.tp_history)
        handler = BOUNDARY_HANDLERS[ev.event_type]
        before = st
        if handler is s06_modifications.apply:
            st = s06_modifications.apply(ctx, st, ev, tb, identified=identified, price_at=price)
        elif handler is s08_estimates_late_events.apply:
            st = s08_estimates_late_events.apply(ctx, st, ev, tb, price_at=price)
        else:
            found = handler(ctx, st, ev, tb)
            if not isinstance(found, AllocatedState):
                raise TypeError(f"the {ev.event_type} handler returned {type(found).__name__}")
            st = found
        if ev.event_type == "CONTRACT_AMENDED":
            # Over the state before the event, once stage 06 accepted it (S06-R-07 refuses first).
            proposals.extend(_amendment_proposal(ctx, before, ev, tb, identified))
        if len(st.tp_history) > priced:
            _trace_boundary_price(ctx, pob, st, ev, tb)
            # CV-50 rev 1.29 (D-98 124): the created obligations' total-price echoes over the
            # build-up just traced (their ids were reserved at creation).
            provenance.emit_price_echoes(
                ctx,
                tb,
                ev,
                st.obligations,
                total=st.tp_history[-1].total,
                price_node=f"transaction_price@{ev.event_key}:{encode_key(pob.group_key)}:-",
            )
    st = _version_price(ctx, pob, st, tb, price)
    proposals.extend(_pending_proposals(ctx, st, tb, identified))
    if not proposals:
        return st
    merged = sorted((*st.proposals, *proposals), key=_proposal_order)
    return dataclasses.replace(st, proposals=tuple(merged))


def _version_price(
    ctx: BookContext,
    pob: PobState,
    st: AllocatedState,
    tb: TraceBuilder,
    price: s06_modifications.PriceAt,
) -> AllocatedState:
    """The price at the end of the stream for a group with realised amounts (ENC-8; ENC-6).

    S04-R-01 measures the price at a date and position, ``None`` for the end of the stream, and
    ENGINE_SPEC_B S09-R-02 requires the transaction price to carry the realised amounts the
    recognition targets carry — royalties (``ROYALTY``, ENC-8) and right-to-invoice amounts or
    POL-240 ``DERIVED`` usage fees (``PERIOD_VC``, ENC-6; S09-R-18, S09-R-19) — so that 04 DB-17
    V1 holds at every version. A group with a ``ROYALTY`` or ``PERIOD_VC`` component is therefore
    re-priced at the version date d_v (the latest event date), and the build-up is appended to
    ``tp_history`` when it differs from the last boundary price.
    It is traced under the last event of the stream, ``<column>@<its event key>``, the price after
    that event (CV-50), while the version-state nodes keep the inception price stage 05 cites
    (L4-3-Q-15). Groups without the component keep their history unchanged.
    """
    if not st.tp_history or not st.events:
        return st
    if not any(
        seg.component in REALISED_COMPONENTS for ob in st.obligations for seg in ob.segments
    ):
        return st
    last_event = max(st.events, key=lambda ev: ev.order_key)
    version_date = max(last_event.effective_date, st.inception_date)
    measured = price(ctx, st, version_date, None)
    last = st.tp_history[-1]
    if (measured.total, measured.allocation_basis) == (last.total, last.allocation_basis):
        return st
    basis_node = f"tp_allocation_basis@{last_event.event_key}:{encode_key(pob.group_key)}:-"
    if tb.value(basis_node) is None:
        s04_transaction_price.price_at(
            ctx,
            pob,
            version_date,
            tb,
            before=None,
            rates=_rates(st, version_date, None),
            boundary=last_event,
            added=_added_references(st, version_date, None),
        )
    return dataclasses.replace(st, tp_history=(*st.tp_history, measured))


def _amendment_proposal(
    ctx: BookContext,
    st: AllocatedState,
    ev: EventView,
    tb: TraceBuilder,
    identified: IdentifiedState,
) -> tuple[ProposalOut, ...]:
    """S06-R-01: the proposal of the modification a ``CONTRACT_AMENDED`` applies, measured over the
    state before the event. It changes no accounting (CV-16; L4-3-Q-23, L5-3-Q-18)."""
    key = payload_text(ev.payload, "modification_id")
    header = next(
        (view.header for view in st.contracts if view.header.external_id == ev.contract_key), None
    )
    found = (
        None
        if key is None or header is None
        else next((item for item in header.modifications if item.modification_key == key), None)
    )
    if found is None:
        return ()  # stage 06 refuses the event (S06-R-07; CV-45)
    view = s06_modifications.ModificationView.of(ev.contract_key, found, event=ev)
    return (s06_modifications.propose(ctx, st, view, tb, identified=identified).out(),)


def _pending_proposals(
    ctx: BookContext, st: AllocatedState, tb: TraceBuilder, identified: IdentifiedState
) -> tuple[ProposalOut, ...]:
    """The proposals of the bundle modifications that no event of the stream applies, measured over
    the state after the fold: a modification awaiting its choice, or one chosen as a separate
    contract, which appends nothing to the original stream (S06-R-01, S06-R-03; L5-3-Q-18)."""
    applied = {(ev.contract_key, payload_text(ev.payload, "modification_id")) for ev in st.events}
    found: list[ProposalOut] = []
    for view in st.contracts:
        contract_key = view.header.external_id
        for item in view.header.modifications:
            if (contract_key, item.modification_key) in applied:
                continue
            mod = s06_modifications.ModificationView.of(contract_key, item)
            found.append(s06_modifications.propose(ctx, st, mod, tb, identified=identified).out())
    return tuple(found)


def _proposal_order(proposal: ProposalOut) -> tuple[str, str, str]:
    return (proposal.kind, proposal.subject_key, proposal.detail.get("modification_key", ""))


def _trace_boundary_price(
    ctx: BookContext, pob: PobState, st: AllocatedState, ev: EventView, tb: TraceBuilder
) -> None:
    """CV-50 boundary nodes ``<column>@<event key>`` of the price a boundary appended (S04-R-01).

    The version-state nodes keep the inception price that stage 05 cites, so the price after a
    reallocating boundary is traced under the boundary's own names, measured where the handler
    measured it: at the event date before the next event (L4-3-Q-15; L5-3-Q-2). The consideration
    that the binding adds (T-CON-06 line deltas, a price-only concession, the additional
    consideration of an exercise) enters ``fixed_consideration@<event key>`` as source references
    to its events (CV-53; L5-3-Q-17). The handler prices the state before its event, so the unit
    rates of the returnable obligations are those in force before the event when the rates after
    it do not reproduce the appended entry (a modification re-pricing a returnable line: the
    appended expected returns stand at the pre-event rate, the version-date memo at the new one;
    CV-50 qualifier ``returns``; lane ENG-T1F). A measure that neither reproduces is not traced.
    """
    appended = st.tp_history[-1]
    following = next((item for item in st.events if item.order_key > ev.order_key), None)
    added = _added_references(st, appended.at, following)
    for position in (following, ev):
        rates = _rates(st, appended.at, position)
        measured = s04_transaction_price.price_at(
            ctx, pob, appended.at, None, before=following, rates=rates, added=added
        )
        if (measured.total, measured.allocation_basis) == (
            appended.total,
            appended.allocation_basis,
        ):
            s04_transaction_price.price_at(
                ctx, pob, appended.at, tb, before=following, rates=rates, boundary=ev, added=added
            )
            return


def price_binding(pob: PobState) -> s06_modifications.PriceAt:
    """The stage 04 price function the boundary handlers call (§4.2; S06-R-18; L2-3-Q-1).

    Stage 04 ``price_at`` over the stage 03 state at ``at`` before ``before``, with r of every
    returnable obligation from its ``FIXED`` segment in force (L2-2-Q-6), plus the consideration
    the boundary events before the position add: stage 04 reads booking lines only, so the binding
    adds Σ ``consideration_delta`` of the T-CON-06 lines of each ``CONTRACT_AMENDED`` and
    ``CONTRACT_TERMINATED``, and ``additional_consideration`` of each ``MATERIAL_RIGHT_EXERCISED``
    (S06-R-23), to ``fixed``, ``total`` and ``allocation_basis`` (L3-2-Q-2).
    """

    def price(
        ctx: BookContext, st: AllocatedState, at: date, before: EventView | None
    ) -> TpBuildUp:
        rates = _rates(st, at, before)
        found = s04_transaction_price.price_at(ctx, pob, at, None, before=before, rates=rates)
        added = _added_consideration(st, at, before)
        if added == 0:
            return found
        minor_unit = ctx.currencies[ctx.txn_currency].minor_unit

        def plus(quota: Quota1) -> Quota1:
            exact = quota.exact + added
            return Quota1(exact, round_half_up(exact, minor_unit))

        return dataclasses.replace(
            found,
            fixed=plus(found.fixed),
            total=plus(found.total),
            allocation_basis=plus(found.allocation_basis),
        )

    return price


def _before(
    order: Mapping[str, tuple[date, int, str]], key: str | None, ev: EventView | None
) -> bool:
    if key is None or ev is None:
        return True
    found = order.get(key)
    return found is not None and found < ev.order_key


def _rates(st: AllocatedState, at: date, before: EventView | None) -> dict[str, Fraction]:
    """r = x_exact ÷ Q of the ``FIXED`` segment in force for each returnable obligation."""
    order = {item.event_key: item.order_key for item in st.events}
    rates: dict[str, Fraction] = {}
    for ob in st.obligations:
        if ob.subject_key not in st.return_paths or ob.quantity == 0:
            continue
        in_force = [
            seg
            for seg in ob.segments
            if seg.component == "FIXED"
            and seg.effective_date <= at
            and _before(order, seg.event_key, before)
        ]
        if in_force:
            rates[ob.subject_key] = in_force[-1].x_exact / ob.quantity
    return rates


def _added_consideration(st: AllocatedState, at: date, before: EventView | None) -> Fraction:
    return sum((amount for _, amount in _added_references(st, at, before)), Fraction(0))


def _added_references(
    st: AllocatedState, at: date, before: EventView | None
) -> tuple[tuple[SourceRef, Fraction], ...]:
    """The consideration the boundary events before the position add, one source reference per
    addition with its value (CV-53): member ``additional_consideration`` of an exercise, member
    ``consideration_delta`` of each T-CON-06 line, or ``price_change_amount`` of a price-only
    concession (L5-3-Q-17)."""
    headers = {view.header.external_id: view.header for view in st.contracts}
    found: list[tuple[SourceRef, Fraction]] = []

    def add(ev: EventView, amount: Fraction, **detail: str) -> None:
        if amount != 0:
            members = {**detail, "value": format_exact(amount)}
            found.append((SourceRef("contract_event", ev.event_key, members), amount))

    for ev in st.events:
        if ev.effective_date > at or (before is not None and ev.order_key >= before.order_key):
            continue
        if ev.event_type == "MATERIAL_RIGHT_EXERCISED":
            amount = payload_fraction(ev.payload, "additional_consideration") or Fraction(0)
            add(ev, amount, member="additional_consideration")
            continue
        if ev.event_type not in _WITH_LINES:
            continue
        key = payload_text(ev.payload, "modification_id")
        header = headers.get(ev.contract_key)
        if key is None or header is None:
            continue  # stage 06 refuses the event (S06-R-07; CV-45)
        modification = next(
            (item for item in header.modifications if item.modification_key == key), None
        )
        if modification is None:
            continue
        view = s06_modifications.ModificationView.of(ev.contract_key, modification)
        for index, line in enumerate(view.lines):
            add(
                ev,
                line.consideration_delta,
                member="consideration_delta",
                line=str(index),
                obligation_key=line.obligation_key,
            )
        if not view.lines and view.price_change_amount is not None:
            # A price-only concession without lines: ΔC_sat is its own change of consideration,
            # which no line delta carries (S06-R-07, S06-R-09; POLICIES ALG-04 §2.5.2; L4-3-Q-12).
            add(ev, view.price_change_amount, member="price_change_amount")
    return tuple(found)


# --- Stage 12 and stage 14 bindings (L2-5-Q-10, L2-5-Q-21, L2-5-Q-24; END-9) ---------------------


@dataclass(frozen=True, slots=True)
class CostsView:
    """The stage 11 state as stages 12 and 14 read it: ``FxSource`` and ``PartSource``."""

    allocated: AllocatedState  # consumed state, unchanged (ENGINE_SPEC_B §0.4)
    costs: CostLossState  # the stage 11 output itself
    fx_flows: FxFlows  # §12.1 input flows (L2-5-Q-10)
    part_inputs: PartInputs  # Table 14-A producer targets (L2-5-Q-24)
    balances: BalanceState  # the stage 10 documents for the S07-R-07 billing predicate (S10-R-03)


def costs_view(ctx: BookContext, st: CostLossState) -> CostsView:
    """Derive the stage 12 flows and the stage 14 producer targets from stages 09 to 11.

    - Relief (S10-R-09) is the stage 09 ``revenue_cum`` target of the obligation, in its contracting
      entity's calendar (the latest performing-entity target on or before each period end).
    - Relief by cause is the stage 09 ``revenue`` decomposition, dated in the contracting calendar.
    - Refund liabilities, netting reclass attributions and ``ENGINE`` mode unconditional billing
      come from stage 10.
    - Control flows are the stage 10 invoices and credit memos in position, at their dates, plus the
      period movement of relief at each contracting period end. Positions are stage 10 NP.
    - No obligation is released at close: compute posts relief as EVENT deltas, so the engine
      answer keys see the revenue lines of open periods (L3-2-Q-15).
    - The other S10-INV-05 components move the control role at each contracting period end, so
      stage 12 layers tie to NP (S12-INV-03; L4-3-Q-29): the refund-liability components as
      monetary flows that debit the control role on an increase and credit it on a decrease
      (S12-R-19, S12-R-20), and the JET-11 accretion, the receivable contra, the deposit transfers
      and the noncash consideration as control flows (S12-R-03). Stage 14 reads the accretion as
      the JET-11 part targets (L4-3-Q-30).
    - Receivable flows are not bound, so a foreign-currency part without its stage 12 amount fails
      closed in stage 14 (L3-2-Q-14).
    - Except for a contracting entity whose functional currency differs from the transaction
      currency: its ``ENGINE`` mode invoices, receipts and credit memos bind as receivable flows,
      so stage 12 gives JET-03 its functional amount and remeasures the receivable (JET-10a′;
      S10-R-19; L6-5, FX-CHK-083).
    - Such an entity's consideration-payable promises bind as monetary-liability increases at
      their promise dates, so stage 12 creates the payable layers at spot, gives JET-14 promised
      its functional amount and remeasures the payable (JET-10d; S12-R-19, S12-R-21; L6-5,
      FX-CHK-084-C).
    - The stage 11 required provision of every loss unit the book tests binds as the JET-12 part
      target (S11-R-14, S11-R-15; Table 14-A; D-92 (3)): ``TIME``, posted by the ``CLOSE_RELEASE``
      pass, so compute posts no JET-12 line of an open period (RCP-08(a)).
    """
    balances = st.balances
    recognition = balances.recognition
    obligations = {ob.subject_key: ob for ob in st.allocated.obligations}
    relief = _relief_targets(
        ctx, recognition, obligations, balances.agent_relief, balances.concessions
    )
    specialist = st.allocated.specialist_targets
    financing = tuple(target for target in specialist.financing if target.measure == _FINANCING)
    flows = FxFlows(
        control=(
            *_control_flows(ctx, st.allocated, balances, relief),
            *_position_flows(ctx, st.allocated, balances),
            *_opening_flows(ctx, st.allocated, balances),
        ),
        positions=MappingProxyType(
            {key: item.net_position for key, item in sorted(balances.position_components.items())}
        ),
        monetary=(*_monetary_flows(ctx, balances), *_payable_flows(ctx, st.allocated)),
        receivables=_receivable_flows(ctx, st.allocated, balances),
    )
    inputs = PartInputs(
        relief=relief,
        relief_by_cause=_relief_by_cause(ctx, recognition, obligations),
        # JET-02 agent weights (R_t, S_t) (D-87 L4-3-Q-24 (e)).
        agent_supplier=tuple(
            target for target in balances.agent_relief if target.measure == _AGENT_SUPPLIER
        ),
        refund_liabilities=balances.refund_liabilities,
        # JET-05c from the stage 10 CONCESSION components (S06-R-09; Table 14-A; L4-3-Q-42).
        concessions=balances.concessions,
        reclass=_reclass_targets(ctx, balances),
        invoices=_invoice_targets(ctx, balances, obligations),
        # JET-03 tax and JET-04c in ENGINE mode (Table 14-A; L4-3-Q-19, L5-3-Q-12, L5-5-Q-9).
        invoice_tax=_invoice_tax_targets(ctx, balances, obligations),
        receivable_contra=balances.receivable_contra,
        financing=financing,
        return_assets=balances.return_assets,
        # JET-01b receipt, criteria met, refund and 25-7 revenue (S02-R-08; Table 14-A; L4-1-Q-15;
        # D-91 gaps (x): the four measures bound through the one stage 14 constant, END-4b).
        deposits=tuple(
            target for target in specialist.deposit if target.measure in DEPOSIT_PART_MEASURES
        ),
        # The stage 09 S14-R-25 shares per obligation, dated in the contracting calendar (D-91).
        deposit_revenue=_contracting_dated(ctx, recognition.deposit_revenue_shares, obligations),
        # JET-17 unconditional and receipt from the EMOD-23 measures (S04-R-18; CHK-135).
        noncash=tuple(
            target for target in specialist.noncash if target.measure in _NONCASH_PARTS_BOUND
        ),
        # JET-16 accrual from the EMOD-21 assurance-warranty accrual (S04-R-19; CHK-134).
        warranties=tuple(
            target for target in specialist.warranty if target.measure == _WARRANTY_ACCRUAL
        ),
        # JET-14 promised, release and share-based from the stage 10 set: the stage 04 payable and
        # ordinary release rows and the stage 10 share-based and composed release rows
        # (S04-R-14 to S04-R-17; S10-R-26; CHK-133, CHK-120; D-91 amending D-88 L7-6-Q-6).
        customer_consideration=tuple(
            target
            for target in balances.customer_consideration
            if target.measure in _CPC_PARTS_BOUND
        ),
        # JET-09a to JET-09f from the stage 11 cost assets (S11-R-01 to S11-R-13; lane L5-5).
        cost_assets=_cost_asset_targets(st),
        # JET-12 from the stage 11 loss provisions (S11-R-14, S11-R-15; D-92 (3); lane ENG-C7).
        loss_provisions=_loss_provision_targets(st),
    )
    return CostsView(
        allocated=st.allocated,
        costs=st,
        fx_flows=flows,
        part_inputs=inputs,
        balances=st.balances,
    )


def _contracting_dated(
    ctx: BookContext, targets: Sequence[Target], obligations: Mapping[str, ObligationState]
) -> tuple[Target, ...]:
    """Obligation targets re-dated to the contracting entity's period ends: a target of the
    contracting calendar is kept; one of another calendar is read at the latest performing period
    end on or before each contracting period end (C-04; as ``_relief_targets`` dates relief)."""
    ends = _period_ends(ctx)
    by_subject: dict[tuple[str, str], list[Target]] = {}
    for target in targets:
        by_subject.setdefault((target.subject_key, target.measure), []).append(target)
    out: list[Target] = []
    for (subject_key, _measure), items in sorted(by_subject.items()):
        contracting = _obligation(obligations, subject_key).contracting_entity
        if all(target.entity == contracting for target in items):
            out.extend(sorted(items, key=lambda t: ends[(t.entity, t.period_key)]))
            continue
        dated = sorted(items, key=lambda t: ends[(t.entity, t.period_key)])
        for period in ctx.entities[contracting].periods:
            before = [t for t in dated if ends[(t.entity, t.period_key)] <= period.end_date]
            if before:
                out.append(
                    dataclasses.replace(
                        before[-1], entity=contracting, period_key=period.period_key
                    )
                )
    return tuple(out)


def _loss_provision_targets(st: CostLossState) -> tuple[Target, ...]:
    """The stage 11 ``loss_provision_required`` per loss unit and period end, the JET-12 part
    target (Table 14-A; S11-R-14; D-92 (3)). Stage 11 publishes measures only for the units in
    the book's loss scope (S11-R-15: the ASC606 book tests the contracts flagged ``scope_605_35``
    under POL-151 ``SCOPED_605_35_ONLY``, the IFRS15 book every contract with an approved ``EAC``
    version under the FORCED ``ALL_CONTRACTS_WITH_EAC``), so a contract outside the book's scope
    binds nothing and posts no JET-12 line (IFRS-SW11)."""
    return tuple(target for target in st.loss_provisions if target.measure == _LOSS_PROVISION)


def _cost_asset_targets(st: CostLossState) -> tuple[Target, ...]:
    """The stage 11 cost measures with the asset's E-83 cost kind as ``cause`` (T-CON-15)."""
    kinds = {spec.asset_key: spec.cost_kind for spec in st.cost_asset_specs}
    return tuple(
        dataclasses.replace(target, cause=kinds[target.subject_key])
        for target in st.cost_assets
        if target.measure in _COST_PARTS_BOUND and target.subject_key in kinds
    )


def _movements(ctx: BookContext, targets: Sequence[Target]) -> list[tuple[Target, date, int]]:
    """Each cumulative target with its period end and its movement since the previous period."""
    ends = _period_ends(ctx)
    grouped: dict[tuple[str, str, str, str], list[tuple[date, Target]]] = {}
    for target in targets:
        end = ends.get((target.entity, target.period_key))
        if end is None:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "a target names a period absent from its entity's calendar",
                subject_key=target.subject_key,
                detail={"period_key": target.period_key, "rule": "CV-12"},
            )
        key = (target.measure, target.subject_key, target.entity, target.cause or "")
        grouped.setdefault(key, []).append((end, target))
    out: list[tuple[Target, date, int]] = []
    for key in sorted(grouped):
        previous = 0
        for end, target in sorted(grouped[key], key=lambda item: item[0]):
            movement, previous = target.value - previous, target.value
            if movement != 0:
                out.append((target, end, movement))
    return out


def _position_kind(target: Target, movement: int) -> str:
    """The S12-R-03 flow kind of a movement of an S10-INV-05 component (L4-3-Q-29)."""
    rising = movement > 0
    if target.measure == _FINANCING:
        if target.cause in _INCOME_CAUSES:  # JET-11a debits the control role
            return "INTEREST_INCOME" if rising else "INTEREST_EXPENSE"
        if target.cause in _EXPENSE_CAUSES:  # JET-11b credits it
            return "INTEREST_EXPENSE" if rising else "INTEREST_INCOME"
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "a financing target names no JET-11 part",
            subject_key=target.subject_key,
            detail={"cause": str(target.cause), "rule": "S10-R-10"},
        )
    if target.measure == _CONTRA:
        return "CONTRA_INCREASE" if rising else "CONTRA_RELEASE"
    if not rising:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "a cumulative deposit transfer or noncash target decreases",
            subject_key=target.subject_key,
            detail={"measure": target.measure, "period_key": target.period_key, "rule": "S12-R-03"},
        )
    return "DEPOSIT_TRANSFER" if target.measure == _DEPOSIT else "NONCASH"


def _position_flows(
    ctx: BookContext, allocated: AllocatedState, st: BalanceState
) -> tuple[ControlFlow, ...]:
    """The period movements of IE, II, RC, DT and NC as control-role flows (S10-INV-05)."""
    specialist = allocated.specialist_targets
    items = [
        *(target for target in specialist.financing if target.measure == _FINANCING),
        *(target for target in specialist.deposit if target.measure == _DEPOSIT),
        *(target for target in specialist.noncash if target.measure == _NONCASH),
        *(target for target in st.receivable_contra if target.measure == _CONTRA),
    ]
    return tuple(
        ControlFlow(
            kind=_position_kind(target, movement),
            entity=target.entity,
            subject_key=target.subject_key,
            source_key=f"{target.subject_key}@{target.period_key}/{target.measure}",
            effective_date=end,
            record_seq=None,
            amount=abs(movement),
        )
        for target, end, movement in _movements(ctx, items)
    )


def _monetary_flows(ctx: BookContext, st: BalanceState) -> tuple[MonetaryFlow, ...]:
    """The period movements of each refund-liability component (S12-R-19, S12-R-20; L4-3-Q-29).

    A ``CONCESSION`` component binds two flows instead (D-88 L7-5-Q-4 (3)): its creation, the
    created amount at its creation period end as an INCREASE with no control side (JET-05c credits
    REVENUE, so ``_increase`` debits no control role), and its consumption, each period's movement
    of Σ consumed as a DECREASE with control CREDIT. The consumption source key sorts after the
    creation's, so on one date the creation is processed first (ALG-08 §2.9.1).
    """
    components = {component.key: component for component in st.refund_components}
    items = [target for target in st.refund_liabilities if target.measure == _REFUND_LIABILITY]
    concessions: dict[str, list[Target]] = {}
    for target in items:
        component = components.get(target.subject_key)
        if component is not None and component.kind == _CONCESSION:
            concessions.setdefault(target.subject_key, []).append(target)
    items = [target for target in items if target.subject_key not in concessions]
    flows: list[MonetaryFlow] = _concession_flows(ctx, components, concessions)
    for target, end, movement in _movements(ctx, items):
        component = components.get(target.subject_key)
        rising = movement > 0
        flows.append(
            MonetaryFlow(
                role="REFUND_LIABILITY",
                direction="INCREASE" if rising else "DECREASE",
                entity=target.entity,
                subject_key=target.subject_key if component is None else component.subject_key,
                component_key=target.subject_key,
                source_key=f"{target.subject_key}@{target.period_key}",
                effective_date=end,
                record_seq=None,
                amount=abs(movement),
                reason=target.cause or "ESTIMATE",
                control="DEBIT" if rising else "CREDIT",
            )
        )
    return tuple(flows)


def _concession_flows(
    ctx: BookContext,
    components: Mapping[str, RefundComponent],
    balances: Mapping[str, Sequence[Target]],
) -> list[MonetaryFlow]:
    """The creation and consumption flows of each ``CONCESSION`` component (D-88 L7-5-Q-4 (3)).

    The component's first balance target dates the creation (stage 10 publishes from the creation
    period on); Σ consumed at a period end is the created amount less the balance.
    """
    ends = _period_ends(ctx)
    flows: list[MonetaryFlow] = []
    for key in sorted(balances):
        component = components[key]
        dated = sorted(balances[key], key=lambda t: ends[(t.entity, t.period_key)])
        first = dated[0]
        if component.created_amount > 0:
            flows.append(
                MonetaryFlow(
                    role="REFUND_LIABILITY",
                    direction="INCREASE",
                    entity=first.entity,
                    subject_key=component.subject_key,
                    component_key=key,
                    source_key=f"{key}@{first.period_key}",
                    effective_date=ends[(first.entity, first.period_key)],
                    record_seq=None,
                    amount=component.created_amount,
                    reason=_CONCESSION,
                    control=None,
                )
            )
        consumed = 0
        for target in dated:
            now = component.created_amount - target.value
            movement, consumed = now - consumed, now
            if movement == 0:
                continue
            if movement < 0:
                raise EngineError(
                    "ENGINE_INVARIANT_VIOLATED",
                    "a concession's consumption falls",
                    subject_key=key,
                    detail={"period_key": target.period_key, "rule": "S10-INV-07"},
                )
            flows.append(
                MonetaryFlow(
                    role="REFUND_LIABILITY",
                    direction="DECREASE",
                    entity=target.entity,
                    subject_key=component.subject_key,
                    component_key=key,
                    source_key=f"{key}@{target.period_key}#consumed",
                    effective_date=ends[(target.entity, target.period_key)],
                    record_seq=None,
                    amount=movement,
                    reason=_CONCESSION,
                    control="CREDIT",
                )
            )
    return flows


def _payable_flows(
    ctx: BookContext,
    allocated: AllocatedState,
    *,
    entities: Collection[str] | None = None,
) -> tuple[MonetaryFlow, ...]:
    """The consideration-payable promises as monetary-liability increases (S12-R-19, S12-R-21;
    POLICIES ALG-08 §2.9.1; L6-5, FX-CHK-084-C).

    Each non-share-based promise of the list in force at the stream end, as stage 04 reads it (the
    member of the latest booking or amendment payload carrying it, else the header; S01-R-20),
    creates a layer at spot on its promise date for its reduction R (S04-R-14). R is rounded
    cumulatively per contract in (promise date, list position) order, so the flows through each
    period end sum to the stage 04 ``consideration_payable`` target, which stage 14 checks
    (S14-R-01). A promise records no settlement. ``entities`` names the contracting entities to
    bind; by default those whose functional currency differs from the transaction currency.
    """
    if entities is None:
        entities = {
            code
            for code, view in ctx.entities.items()
            if view.functional_currency != ctx.txn_currency
        }
    end = _stream_end(ctx, allocated)
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    flows: list[MonetaryFlow] = []
    for view in sorted(allocated.contracts, key=lambda item: item.header.external_id):
        contract_key = view.header.external_id
        entity = view.header.contracting_entity_code
        if entity not in entities:
            continue
        source, listed = _payables_in_force(allocated, view, end)
        if source is None:
            continue
        subject = contract_entity_subject_key(contract_key, entity)
        ordinary = sorted(
            (on, index, reduction)
            for index, (on, reduction, share_based) in enumerate(listed)
            if not share_based
        )
        exact, posted = Fraction(0), 0
        for on, index, reduction in ordinary:
            exact += reduction
            amount = round_half_up(exact, minor_unit) - posted
            posted += amount
            if amount <= 0:
                continue
            flows.append(
                MonetaryFlow(
                    role="CONSIDERATION_PAYABLE",
                    direction="INCREASE",
                    entity=entity,
                    subject_key=subject,
                    component_key=f"{subject}#PROMISE-{index + 1}",
                    source_key=source.event_key,
                    effective_date=on,
                    record_seq=source.record_seq,
                    amount=amount,
                    reason="PROMISE",
                )
            )
    return tuple(flows)


def _payables_in_force(
    allocated: AllocatedState, view: ContractView, at: date
) -> tuple[EventView | None, list[tuple[date, Fraction, bool]]]:
    """The source event and (promise date, R, share-based) per list position (S01-R-20)."""
    contract_key = view.header.external_id
    value = member_in_force(allocated.events, contract_key, _PAYABLE_MEMBER, at)
    source: EventView | None = None
    for event in allocated.events:
        if event.contract_key != contract_key or event.effective_date > at:
            continue
        if value is not None and _PAYABLE_MEMBER in event.payload:
            source = event
        elif source is None and event.event_type == "CONTRACT_BOOKED":
            source = event
    items: Sequence[object]
    if value is None:
        items = view.header.consideration_payable
    elif isinstance(value, list | tuple):
        items = value
    else:
        raise ValueError(f"{contract_key}: consideration_payable is not a list (CV-45)")
    return source, [_payable(contract_key, item) for item in items]


def _payable(contract_key: str, item: object) -> tuple[date, Fraction, bool]:
    """(promise date, R, share-based) of one API-S-ConsiderationPayable item (S04-R-14): R is the
    amount without a distinct good or an estimable fair value, else max(0, amount − fair value)."""
    if isinstance(item, PayableInput):
        amount, on, share_based = to_fraction(item.amount), item.promise_date, item.share_based
        fair = (
            None
            if item.distinct_good_fair_value is None
            else to_fraction(item.distinct_good_fair_value)
        )
    elif isinstance(item, Mapping):
        found_amount = payload_fraction(item, "amount")
        found_on = payload_date(item, "promise_date")
        if found_amount is None or found_on is None:
            raise ValueError(f"{contract_key}: a payable promise needs amount and promise_date")
        amount, on = found_amount, found_on
        fair = payload_fraction(item, "distinct_good_fair_value")
        share_based = item.get("share_based") in (True, "true")
    else:
        raise ValueError(f"{contract_key}: a payable promise is not an object (CV-45)")
    return on, (amount if fair is None else max(Fraction(0), amount - fair)), share_based


def _stream_end(ctx: BookContext, allocated: AllocatedState) -> date:
    """The latest horizon end date of the book's entities, else the group inception (CV-13)."""
    found = allocated.inception_date
    for code, key in ctx.horizon.items():
        view = ctx.entities.get(code)
        if view is None:
            continue
        for period in view.periods:
            if period.period_key == key and period.end_date > found:
                found = period.end_date
    return found


def _bind_deposit_flows(ctx: BookContext, view: CostsView, identified: object) -> CostsView:
    """Bind the dated deposit movements of stage 02 as monetary-liability flows (L6-5).

    A contracting entity whose functional currency differs from the transaction currency holds its
    deposit liability as a monetary item (S02-R-08 rev 1.2; D-25b; POLICIES CHK-084 (b)): stage 12
    creates a layer at spot per receipt, remeasures it at every period end, and settles it at spot
    at criteria met, at a refund on termination and at 25-7 derecognition (S12-R-19, S12-R-20).
    Such an entity's deposits bind as the monetary flows of ``_deposit_flows``, and its period-end
    ``DEPOSIT_TRANSFER`` control flows of ``_position_flows`` are withdrawn, because the transfer
    releases to the control role at spot on the transfer date (IFRIC 22.8). Other entities keep
    the period-end control flows. Without the stage 02 state the view is returned unchanged.
    """
    if not isinstance(identified, IdentifiedState):
        return view
    entities = {
        code
        for code, entity in ctx.entities.items()
        if entity.functional_currency != ctx.txn_currency
    }
    deposits = _deposit_flows(ctx, identified, entities=entities)
    if not deposits:
        return view
    bound = {flow.entity for flow in deposits}
    control = tuple(
        flow
        for flow in view.fx_flows.control
        if not (flow.kind == "DEPOSIT_TRANSFER" and flow.entity in bound)
    )
    flows = dataclasses.replace(
        view.fx_flows, control=control, monetary=(*view.fx_flows.monetary, *deposits)
    )
    return dataclasses.replace(view, fx_flows=flows)


def _deposit_flows(
    ctx: BookContext, identified: IdentifiedState, *, entities: Collection[str]
) -> tuple[MonetaryFlow, ...]:
    """The deposit movements of ``entities`` as ``DEPOSIT_LIABILITY`` flows (S02-R-08; S12-R-19,
    S12-R-20; POLICIES ALG-08 §2.9.1; L6-5, FX-CHK-084-B).

    Each ascending deposit point of a member (``IdentifiedState.deposits``) moves one EMOD-12
    measure at its ENG-06 position: a receipt increases the liability; a refund, a 25-7 recognition
    and a criteria-met transfer decrease it, and the transfer releases to the control role
    (JET-01b criteria met). Amounts are the cumulatively rounded measures (CV-35), so the flows
    through each period end sum to the stage 02 targets stage 14 checks (S14-R-01). The component
    is ``<contract>@<entity>``. A 25-7 recognition without an event takes the source key
    ``<contract>@<entity>@<date>``, and every 25-7 flow adds ``/deposit_to_revenue`` to its
    source, so a termination that refunds and recognises keeps two flow keys (S02-R-07 (b)).
    """
    minor_unit = ctx.currencies[ctx.txn_currency].minor_unit
    flows: list[MonetaryFlow] = []
    for contract_key in identified.member_contract_keys:
        entity = identified.canonical.contracts[contract_key].header.contracting_entity_code
        if entity not in entities:
            continue
        subject = contract_entity_subject_key(contract_key, entity)
        previous = DepositPoint.zero()
        for point in identified.deposits.get(contract_key, ()):
            on, record_seq, event_key = point.order_key
            for member, reason, direction, control in _DEPOSIT_MOVES:
                amount = round_half_up(getattr(point, member), minor_unit) - round_half_up(
                    getattr(previous, member), minor_unit
                )
                if amount == 0:
                    continue
                if amount < 0:
                    raise EngineError(
                        "ENGINE_INVARIANT_VIOLATED",
                        "a cumulative deposit measure decreases",
                        subject_key=subject,
                        detail={"measure": f"deposit_{member}", "rule": "S02-R-08"},
                    )
                source = event_key or f"{subject}@{on.isoformat()}"
                timed = False
                if reason == "EVENT_25_7":
                    source = f"{source}/deposit_to_revenue"
                    # A dated point (no event) moves the sixth measure by the same amount; stage
                    # 12 then publishes its conversion separately (S12-R-20; D1-R04).
                    moved = round_half_up(point.to_revenue_time_cum, minor_unit) - round_half_up(
                        previous.to_revenue_time_cum, minor_unit
                    )
                    if moved not in (0, amount):
                        raise EngineError(
                            "ENGINE_INVARIANT_VIOLATED",
                            "a 25-7 recognition mixes a dated and an event amount",
                            subject_key=subject,
                            detail={"measure": "deposit_to_revenue_time_cum", "rule": "S02-R-08"},
                        )
                    timed = moved == amount
                flows.append(
                    MonetaryFlow(
                        role="DEPOSIT_LIABILITY",
                        direction=direction,
                        entity=entity,
                        subject_key=subject,
                        component_key=subject,
                        source_key=source,
                        effective_date=on,
                        record_seq=record_seq,
                        amount=amount,
                        reason=reason,
                        control=control,
                        timed=timed,
                    )
                )
            previous = point
    return tuple(flows)


def _period_ends(ctx: BookContext) -> dict[tuple[str, str], date]:
    return {
        (code, period.period_key): period.end_date
        for code, calendar in ctx.entities.items()
        for period in calendar.periods
    }


def _through_horizon(ctx: BookContext, entity: str) -> list[object]:
    calendar = ctx.entities[entity]
    horizon = ctx.horizon[entity]
    found: list[object] = []
    for period in sorted(calendar.periods, key=lambda item: item.start_date):
        found.append(period)
        if period.period_key == horizon:
            break
    return found


def _obligation(obligations: Mapping[str, ObligationState], subject_key: str) -> ObligationState:
    ob = obligations.get(subject_key)
    if ob is None:
        raise ValueError(f"a stage 09 or 10 target names the obligation {subject_key!r}, absent")
    return ob


def _relief_targets(
    ctx: BookContext,
    st: RecognitionState,
    obligations: Mapping[str, ObligationState],
    agent: Sequence[Target] = (),
    concessions: Sequence[Target] = (),
) -> tuple[Target, ...]:
    """Relief per obligation and contracting period end (S10-R-09).

    D-88 L7-5-Q-4 (1): relief(o, t) = stage 09 ``revenue_cum``(o, t) (max(G_t, R_t) for an agent)
    + Σ CONCESSION created on o by t, the stage 10 ``concession_created_cum`` targets, which
    position.py adds as ``Refunds.concession_total``. The target keeps the revenue node; stage 14
    cites the concession nodes beside it.
    """
    created: dict[tuple[str, str], int] = {}
    for item in concessions:
        key = (item.subject_key, item.period_key)
        created[key] = created.get(key, 0) + item.value
    # D-87 L4-3-Q-24 (c): an agent obligation relieves max(G_t, R_t), which stage 10 publishes.
    gross = {(t.subject_key, t.period_key): t for t in agent if t.measure == _AGENT_RELIEF}
    by_subject: dict[str, list[Target]] = {}
    for target in st.revenue_targets:
        if target.measure == "revenue_cum":
            by_subject.setdefault(target.subject_key, []).append(target)
    ends = _period_ends(ctx)
    out: list[Target] = []
    for subject_key in sorted(by_subject):
        contracting = _obligation(obligations, subject_key).contracting_entity
        targets = by_subject[subject_key]
        if all(target.entity == contracting for target in targets):
            for target in sorted(targets, key=lambda t: ends[(t.entity, t.period_key)]):
                base = gross.get((target.subject_key, target.period_key), target)
                concession = created.get((target.subject_key, target.period_key), 0)
                out.append(
                    dataclasses.replace(base, measure=_RELIEF, value=base.value + concession)
                )
            continue
        dated = sorted(targets, key=lambda t: ends[(t.entity, t.period_key)])
        for period in ctx.entities[contracting].periods:
            before = [t for t in dated if ends[(t.entity, t.period_key)] <= period.end_date]
            if before:
                concession = created.get((subject_key, period.period_key), 0)
                out.append(
                    dataclasses.replace(
                        before[-1],
                        entity=contracting,
                        period_key=period.period_key,
                        measure=_RELIEF,
                        value=before[-1].value + concession,
                    )
                )
    return tuple(out)


def _relief_by_cause(
    ctx: BookContext, st: RecognitionState, obligations: Mapping[str, ObligationState]
) -> tuple[Target, ...]:
    ends = _period_ends(ctx)
    out: list[Target] = []
    for target in st.revenue_by_cause:
        contracting = _obligation(obligations, target.subject_key).contracting_entity
        if target.entity == contracting:
            out.append(dataclasses.replace(target, measure=_RELIEF_BY_CAUSE))
            continue
        end = ends[(target.entity, target.period_key)]
        period = next(
            (p for p in ctx.entities[contracting].periods if p.start_date <= end <= p.end_date),
            None,
        )
        if period is None:
            raise EngineError(
                "ENGINE_INVARIANT_VIOLATED",
                "the contracting calendar covers no period of a performing-entity revenue date",
                subject_key=target.subject_key,
                detail={"rule": "CV-12", "entity": contracting, "date": end.isoformat()},
            )
        out.append(
            dataclasses.replace(
                target,
                entity=contracting,
                period_key=period.period_key,
                measure=_RELIEF_BY_CAUSE,
            )
        )
    return tuple(out)


def _reclass_targets(ctx: BookContext, st: BalanceState) -> tuple[Target, ...]:
    return tuple(
        Target(
            ctx.book_code,
            item.entity,
            item.subject_key,
            _RECLASS,
            item.period_key,
            item.role,
            item.amount,
            item.exact,
            item.node_id,
        )
        for item in st.netting_reclass
        if item.period_key is not None and item.role is not None and item.amount != 0
    )


def _invoice_targets(
    ctx: BookContext, st: BalanceState, obligations: Mapping[str, ObligationState]
) -> tuple[Target, ...]:
    out: list[Target] = []
    for target in st.billing:
        if target.measure != _INVOICE or target.subject_key not in obligations:
            continue
        ob = obligations[target.subject_key]
        mode = ctx.policies.value(
            "billing.posting",
            contract=ob.contract_key,
            entity=target.entity,
            period=target.period_key,
        )
        if mode == _ENGINE_BILLING:
            out.append(target)
    return tuple(out)


def _invoice_tax_targets(
    ctx: BookContext, st: BalanceState, obligations: Mapping[str, ObligationState]
) -> tuple[Target, ...]:
    """Stage 10 ``sales_tax_billed_cum`` per obligation in the periods posted under
    ``billing.posting = ENGINE``, the tax side of JET-03 (S10-R-02, S04-R-20; lanes L5-3 and
    L5-5)."""
    out: list[Target] = []
    for target in st.billing:
        if target.measure != _INVOICE_TAX or target.subject_key not in obligations:
            continue
        ob = obligations[target.subject_key]
        mode = ctx.policies.value(
            "billing.posting",
            contract=ob.contract_key,
            entity=target.entity,
            period=target.period_key,
        )
        if mode == _ENGINE_BILLING:
            out.append(target)
    return tuple(out)


def _opening_flows(
    ctx: BookContext, allocated: AllocatedState, st: BalanceState
) -> tuple[ControlFlow, ...]:
    """The stage 07 opening baselines as control-role flows at their cutover (ENGINE_SPEC
    S07-R-05; ENGINE_SPEC_B S10-R-03, S12-R-03, S14-R-26 rev 1.11; ENB-9).

    Per ``<contract>@<entity>`` whose obligations all carry a baseline with one cutover date D, the
    ERP's cumulative billing at D (Σ baseline ``billed_cum``) replaces the ledger's in-position
    lines dated on or before D, which ``_control_flows`` (ENG-B4, untouched) has already emitted
    line by line: the flow is the difference, a ``BILLING`` credit when the baseline exceeds those
    lines and a ``CREDIT_MEMO`` debit when it falls short, dated D with ``record_seq`` None and
    source ``<contract>@<entity>@<D>/opening_billed_cum``, so the stage 12 layers tie to the net
    position that counts the baseline in B_u (S12-INV-03). It posts nothing by itself: stage 14
    deems the baseline posted (S14-R-26).
    """
    baselines: dict[tuple[str, str], list[tuple[date | None, int]]] = {}
    for ob in allocated.obligations:
        baseline = baseline_of(ob)
        baselines.setdefault((ob.contract_key, ob.contracting_entity), []).append(
            (None, 0) if baseline is None else (baseline.cutover_date, baseline.billed_cum)
        )
    flows: list[ControlFlow] = []
    for (contract_key, entity), found in sorted(baselines.items()):
        if entity not in ctx.entities:
            continue
        cutovers = {cutover for cutover, _ in found}
        if None in cutovers or len(cutovers) != 1:
            continue
        (cutover,) = cutovers
        assert cutover is not None
        recompute = any(
            (b := baseline_of(ob)) is not None and b.method == "RECOMPUTE_FROM_INCEPTION"
            for ob in allocated.obligations
            if ob.contract_key == contract_key and ob.contracting_entity == entity
        )
        if recompute and engine_lines_through(st.documents, contract_key, cutover):
            continue  # ENGINE lines recomputed through the cutover: no baseline in B_u (S10-R-03)
        pre = 0
        for document in st.documents:
            if document.contract_key != contract_key:
                continue
            for line in document.lines:
                if not line.in_position:
                    continue
                dated = (
                    line.event.effective_date
                    if line.kind == "CREDIT_MEMO"
                    else line.unconditional_date
                )
                if dated is None or dated > cutover:
                    continue
                pre += -line.amount if line.kind == "CREDIT_MEMO" else line.amount
        amount = sum(value for _, value in found) - pre
        if amount == 0:
            continue
        flows.append(
            ControlFlow(
                kind="BILLING" if amount > 0 else "CREDIT_MEMO",
                entity=entity,
                subject_key=contract_entity_subject_key(contract_key, entity),
                source_key=f"{contract_key}@{entity}@{cutover.isoformat()}/opening_billed_cum",
                effective_date=cutover,
                record_seq=None,
                amount=abs(amount),
                unconditional_date=cutover if amount > 0 else None,
            )
        )
    return tuple(flows)


def _control_flows(
    ctx: BookContext, allocated: AllocatedState, st: BalanceState, relief: Sequence[Target]
) -> tuple[ControlFlow, ...]:
    entities = {
        view.header.external_id: view.header.contracting_entity_code for view in allocated.contracts
    }
    flows: list[ControlFlow] = []
    # D-87 L6-5-Q-14: the first receipt applied to each invoice (S12-R-04), in the order stage 10
    # dates the payments it applies (S10-R-06).
    first_receipts: dict[tuple[str, str], date] = {}
    for receipt in st.receipts:
        for number in receipt.applied_invoice_numbers:
            key = (receipt.contract_key, number)
            on = receipt.event.effective_date
            if key not in first_receipts or on < first_receipts[key]:
                first_receipts[key] = on
    for document in st.documents:
        kind = {"INVOICE": "BILLING", "CREDIT_MEMO": "CREDIT_MEMO"}.get(document.kind)
        if kind is None:
            continue
        entity = entities[document.contract_key]
        subject_key = contract_entity_subject_key(document.contract_key, entity)
        if kind == "CREDIT_MEMO":
            amount = sum(line.amount for line in document.lines if line.in_position)
            if amount <= 0:
                continue
            flows.append(
                ControlFlow(
                    kind=kind,
                    entity=entity,
                    subject_key=subject_key,
                    source_key=document.document_key,
                    effective_date=document.effective_date,
                    record_seq=document.lines[0].event.record_seq if document.lines else None,
                    amount=amount,
                )
            )
            continue
        # An invoice enters the layers line by line as each line becomes billing (S10-R-06;
        # S12-INV-03): one flow per eligible in-position line with the line's own POL-160 date
        # and event key, none for a memo-only line (``_eligible_lines``). The flow's effective
        # date, which the POL-160 ``INVOICE_ISSUE_DATE`` election reads, is the invoice issue date
        # for an ``ERP`` line and the S10-R-06 date an ``ENGINE`` line became billing (supervisor
        # ruling on the election for a cancellable ENGINE line; ENG-B4).
        first_receipt = first_receipts.get((document.contract_key, document.number))
        for line in _eligible_lines(document):
            flows.append(
                ControlFlow(
                    kind=kind,
                    entity=entity,
                    subject_key=subject_key,
                    source_key=line.event.event_key,
                    effective_date=(
                        document.effective_date
                        if line.mode == _ERP_BILLING
                        else _unconditional_of(line)
                    ),
                    record_seq=line.event.record_seq,
                    amount=line.amount,
                    unconditional_date=_unconditional_due(
                        line.mode, _unconditional_of(line), line.event
                    ),
                    first_receipt_date=first_receipt,
                )
            )
    ends = _period_ends(ctx)
    by_subject: dict[str, list[Target]] = {}
    for target in relief:
        by_subject.setdefault(target.subject_key, []).append(target)
    for subject_key, targets in sorted(by_subject.items()):
        previous = 0
        for target in sorted(targets, key=lambda t: ends[(t.entity, t.period_key)]):
            movement, previous = target.value - previous, target.value
            if movement == 0:
                continue
            flows.append(
                ControlFlow(
                    kind="REVENUE" if movement > 0 else "NEGATIVE_REVENUE",
                    entity=target.entity,
                    subject_key=subject_key,
                    source_key=f"{subject_key}@{target.period_key}",
                    effective_date=ends[(target.entity, target.period_key)],
                    record_seq=None,
                    amount=abs(movement),
                )
            )
    return tuple(flows)


def _unconditional_due(mode: str, unconditional: date, event: EventView) -> date:
    """POL-160 "unconditional due" of a billing line, for the layer date only (S12-R-04).

    D-87 L6-5-Q-14: in ``ERP`` mode it is the payload ``due_date`` when present (606-10-55-284,
    noncancellable), else the S10-R-06 date; ``ENGINE`` mode keeps the S10-R-06 date. S10-R-06
    still governs balances and tie-outs.
    """
    if mode != _ERP_BILLING:
        return unconditional
    due = event.payload.get("due_date")
    if type(due) is date:
        return due
    if isinstance(due, str) and due:
        try:
            return date.fromisoformat(due)
        except ValueError:
            return unconditional
    return unconditional


def _unconditional_of(line: Line) -> date:
    """The S10-R-06 date of an eligible line (never ``None`` after ``_eligible_lines``)."""
    if line.unconditional_date is None:  # pragma: no cover - guarded by _eligible_lines
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "a memo-only line reached the billing control flows",
            subject_key=line.event.contract_key,
            detail={"event_key": line.event.event_key, "rule": "S10-R-06"},
        )
    return line.unconditional_date


def _eligible_lines(document: BillingDocumentOut) -> tuple[Line, ...]:
    """The in-position lines of one invoice that are billing under S10-R-06, in ENG-06 order.

    Each becomes its own BILLING control flow: the line's event key is the flow's source (a
    distinct, stable lineage per retained line, which the stage 12 flow-key guard requires and
    which layer creation cites), its S10-R-06 unconditional date under POL-160
    (``_unconditional_due``: the payload due date in ``ERP`` mode, D-87 L6-5-Q-14) dates its layer
    together with the invoice's first applied receipt, and the flow's effective date, which the
    S12-R-04 ``INVOICE_ISSUE_DATE`` election reads, is the invoice issue date for an ``ERP`` line
    and, for an ``ENGINE`` line, the S10-R-06 date it became billing (a receipt applied or a
    noncancellable update; the supervisor's ruling on the election, ENG-B4: a cancellable ENGINE
    line is issued as billing on that date, so the election ties to NP). A memo-only line (no
    unconditional date) is outside ``billed_cum`` and NP, so it contributes no flow until a status
    update or an applied receipt gives it a date, when it enters on that date (D-89 L7-6-Q-9) and
    stage 12's layers tie to NP at every period end (S12-INV-03). Two ERP lines of one invoice with
    different due dates therefore take their own dates and rates. Every corpus invoice holds one
    line, so its flow is byte-identical to the document-level flow of 0104e86, which summed every
    in-position line and dated the total by its earliest eligible line (Codex,
    PRODUCTION-BILLING-LAYER-REVIEW-20260919 and the independent acceptance of 19 September);
    stage 10 ``_counted`` and the S12-INV-03 guard are unchanged (ENG-B4).
    """
    return tuple(
        line
        for line in document.lines
        if line.in_position and line.unconditional_date is not None and line.amount > 0
    )


def _receivable_flows(
    ctx: BookContext,
    allocated: AllocatedState,
    st: BalanceState,
    *,
    entities: Collection[str] | None = None,
) -> tuple[ReceivableFlow, ...]:
    """The ``ENGINE`` mode receivable movements of S10-R-19 per invoice (JET-10a′; L6-5).

    Every unconditional invoice line, billing plus tax, creates a receivable item at its
    unconditional date; a cash receipt and a credit memo reduce the named invoices, else the open
    invoices by ascending (issue date, invoice number), in the order stage 10 applies them
    (``accounts_receivable``). ``entities`` names the contracting entities to bind; by default those
    whose functional currency differs from the transaction currency.
    """
    if entities is None:
        entities = {
            code
            for code, view in ctx.entities.items()
            if view.functional_currency != ctx.txn_currency
        }
    flows: list[ReceivableFlow] = []
    for view in sorted(allocated.contracts, key=lambda item: item.header.external_id):
        contract_key = view.header.external_id
        entity = view.header.contracting_entity_code
        if entity not in entities:
            continue
        subject = contract_entity_subject_key(contract_key, entity)
        invoice_keys: dict[str, str] = {}
        totals: dict[tuple[str, str], int] = {}
        # (date, invoices first, ENG-06 order, kind, event, invoice numbers, amount)
        items: list[tuple[date, int, tuple[date, int, str], str, EventView, tuple[str, ...], int]]
        items = []
        for document in st.documents:
            if document.contract_key != contract_key:
                continue
            for line in document.lines:
                if line.mode != _ENGINE_BILLING or not line.in_position:
                    continue
                if line.kind == "INVOICE":
                    invoice_keys.setdefault(line.number, document.document_key)
                    if line.unconditional_date is None:
                        continue
                    key = (line.event.event_key, line.number)
                    if key not in totals:
                        items.append(
                            (
                                line.unconditional_date,
                                0,
                                line.event.order_key,
                                "INVOICE",
                                line.event,
                                (line.number,),
                                0,
                            )
                        )
                    totals[key] = totals.get(key, 0) + line.amount + line.tax_amount
                else:
                    credited: tuple[str, ...] = ()
                    if line.credited_invoice_number is not None:
                        credited = (line.credited_invoice_number,)
                    items.append(
                        (
                            line.event.effective_date,
                            1,
                            line.event.order_key,
                            "CREDIT",
                            line.event,
                            credited,
                            line.amount,
                        )
                    )
        for receipt in st.receipts:
            if receipt.contract_key == contract_key and receipt.form == "CASH":
                items.append(
                    (
                        receipt.event.effective_date,
                        1,
                        receipt.event.order_key,
                        "RECEIPT",
                        receipt.event,
                        tuple(receipt.applied_invoice_numbers),
                        receipt.amount,
                    )
                )
        open_amounts: dict[str, int] = {}
        issued: dict[str, date] = {}
        for when, _, _, tag, event, named, amount in sorted(items, key=lambda entry: entry[:3]):
            if tag == "INVOICE":
                number = named[0]
                total = totals[(event.event_key, number)]
                open_amounts[number] = open_amounts.get(number, 0) + total
                issued.setdefault(number, event.effective_date)
                if total > 0:
                    flows.append(
                        ReceivableFlow(
                            kind="INVOICE",
                            entity=entity,
                            subject_key=subject,
                            invoice_key=invoice_keys[number],
                            source_key=event.event_key,
                            effective_date=when,
                            record_seq=None,
                            amount=total,
                        )
                    )
                continue
            for number, take in _applications(open_amounts, issued, named, amount):
                flows.append(
                    ReceivableFlow(
                        kind="REDUCTION",
                        entity=entity,
                        subject_key=subject,
                        invoice_key=invoice_keys[number],
                        source_key=event.event_key,
                        effective_date=when,
                        record_seq=event.record_seq,
                        amount=take,
                    )
                )
    return tuple(flows)


def _applications(
    open_amounts: dict[str, int], issued: Mapping[str, date], named: Sequence[str], amount: int
) -> list[tuple[str, int]]:
    """S10-R-19: apply ``amount`` to the named open invoices, else by ascending (issue date,
    invoice number); returns the positive amount taken from each invoice."""
    order = (
        [number for number in named if number in open_amounts]
        if named
        else sorted(open_amounts, key=lambda number: (issued[number], number))
    )
    left = amount
    taken: list[tuple[str, int]] = []
    for number in order:
        if left == 0:
            break
        take = min(open_amounts[number], left)
        if take > 0:
            open_amounts[number] -= take
            left -= take
            taken.append((number, take))
    return taken
