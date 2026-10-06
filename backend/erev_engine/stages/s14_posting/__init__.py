"""Stage 14: journal derivation (ENGINE_SPEC_B §14; BUILD_SPEC END-4 to END-6).

``run`` turns the cumulative targets of stages 09 to 13 into the part targets of Table 14-A: signed
cumulative amounts per (book, owner entity, subject, part) and period end, each with its stage 12
functional amount (S14-R-01 to S14-R-03). The constants ``JET_PARTS`` and ``COUNTER_ROLES``
(templates) and ``AMOUNT_CLASSES`` (amount classes) are the single source of the posting patterns
(POLICIES §2.3; 05 §3.6.1, RCP-07). The role targets of each (book, entity, subject, entry kind,
role, clearing purpose, counterparty) and period end, and the deltas against the posted amounts by
origin period and posting class, follow (S14-R-04 to S14-R-09; END-5). The deltas group into
balanced posting intents with resolved accounts, dimensions and deterministic keys (S14-R-10 to
S14-R-15; END-6).

Integration after merge (D-81; L2-5-Q-24): Table 14-A names the producer targets of stages 09 to
11, but no published member of ``CostLossState`` (ENC-15, lane L2-4) carries them. ``run`` reads
them as ``PartInputs`` from the consumed stage 11 state that ``FxState.costs`` carries (the
``PartSource`` protocol), as stage 12 reads ``FxFlows`` (L2-5-Q-10); the adapter belongs to the book
loop. The book loop binds the keywords ``posted`` (``CanonicalBundle.posted``), ``pass_name`` (the
close-run pass of a ``CLOSE_RELEASE`` computation) and ``voided`` (the member contracts whose new
events include a void), as it binds ``rates`` for stage 12 (L2-5-Q-28, L2-5-Q-30). Submodules are
private (DG-ENG-07). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Final, Protocol, runtime_checkable

from erev_engine.bundle import PostingIntent
from erev_engine.errors import EngineError
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.s12_fx_entities import FxState, RateRef
from erev_engine.stages.s14_posting import manual, onboarding
from erev_engine.stages.s14_posting.accounts import ACCOUNT_MAPPING_MISSING
from erev_engine.stages.s14_posting.amount_classes import (
    AMOUNT_CLASSES,
    EVENT,
    TIME,
    AmountClass,
    amount_class,
)
from erev_engine.stages.s14_posting.assign import (
    COMPUTE_TRIGGERS,
    LATE_EVENT,
    POSTING_CLASSES,
    VOID,
    PostedTotals,
    RoleDelta,
    classes_posted_by,
    derive_deltas,
    posting_class,
)
from erev_engine.stages.s14_posting.intents import entry_key, group_into_entries, line_key
from erev_engine.stages.s14_posting.targets import (
    DEPOSIT_PART_MEASURES,
    DEPOSIT_REVENUE_MEASURE,
    DEPOSIT_REVENUE_PART,
    DEPOSIT_REVENUE_TIME_MEASURE,
    PartInputs,
    PartTarget,
    RoleKey,
    RoleLine,
    RoleTarget,
    RoleVariant,
    part_targets,
    role_lines,
    role_targets,
)
from erev_engine.stages.s14_posting.templates import (
    COUNTER_ROLES,
    JET_PARTS,
    NOT_A_CONTRACT_EVENT,
    TRIGGER_FAMILIES,
    JetPart,
    Role,
    Side,
)
from erev_engine.stages.state import AllocatedState, BookContext, Finding, PostedIndex
from erev_engine.trace import TraceBuilder

__all__ = [
    "ACCOUNT_MAPPING_MISSING",
    "AMOUNT_CLASSES",
    "COMPUTE_TRIGGERS",
    "COUNTER_ROLES",
    "DEPOSIT_PART_MEASURES",
    "DEPOSIT_REVENUE_MEASURE",
    "DEPOSIT_REVENUE_PART",
    "DEPOSIT_REVENUE_TIME_MEASURE",
    "EVENT",
    "FORMULA_IDS",
    "JET_PARTS",
    "LATE_EVENT",
    "NOT_A_CONTRACT_EVENT",
    "POLICY_KEYS",
    "POSTING_CLASSES",
    "TIME",
    "TRIGGER_FAMILIES",
    "VOID",
    "AmountClass",
    "JetPart",
    "PartInputs",
    "PartSource",
    "PartTarget",
    "PostedTotals",
    "PostingState",
    "Role",
    "RoleDelta",
    "RoleKey",
    "RoleLine",
    "RoleTarget",
    "RoleVariant",
    "Side",
    "amount_class",
    "classes_posted_by",
    "entry_key",
    "line_key",
    "posting_class",
    "role_lines",
    "run",
]

# ENGINE_SPEC_B Table 13-A row 14 (STAGE_POLICY_KEYS), sorted.
POLICY_KEYS: Final[tuple[str, ...]] = (
    "billing.posting",
    "je.posting_mode",
    "je.summarization",
    "late_events.posting",
    "pob.assurance_warranty_accrual",
    "pob.principal_or_agent",
    "rounding.posting_mode",
)
# The registered formulas stage 14 emits so far (§14.6), sorted.
FORMULA_IDS: Final[tuple[str, ...]] = (
    "post.account_resolution.v1",
    "post.delta.v1",
    "post.role_target.v1",
)


@runtime_checkable
class PartSource(Protocol):
    """The consumed stage 11 state as stage 14 reads it (integration after merge, L2-5-Q-24)."""

    @property
    def part_inputs(self) -> PartInputs: ...


@runtime_checkable
class BalanceSource(Protocol):
    """The consumed stage 11 state as the S07-R-07 billing predicate reads it (S10-R-03)."""

    @property
    def balances(self) -> BalanceState: ...


@dataclass(frozen=True, slots=True)
class PostingState:
    """Stage 14 output (ENGINE_SPEC_B §14.1), members built so far."""

    allocated: AllocatedState  # consumed state, unchanged (§0.4)
    part_targets: tuple[PartTarget, ...]  # S14-R-01, sorted by key
    role_targets: tuple[RoleTarget, ...]  # S14-R-04, by role key and period
    deltas: tuple[RoleDelta, ...]  # S14-R-04 to S14-R-08, role-key order
    posting_intents: tuple[PostingIntent, ...]  # S14-R-12, ascending entry key; () on a finding
    effective_dates: Mapping[str, date]  # entry key -> effective date (L2-5-Q-31)
    line_rates: Mapping[str, tuple[RateRef, ...]]  # line key -> pinned rates (REQ-FX-006)
    posting_kind: str  # E-31 of the posting the orchestrator persists (S14-R-08)
    findings: tuple[Finding, ...]  # CV-43 order


def run(
    ctx: BookContext,
    st: FxState,
    tb: TraceBuilder,
    *,
    posted: PostedIndex | None = None,
    pass_name: str | None = None,
    voided: Collection[str] = (),
    new_events: Sequence[tuple[str, str]] = (),
) -> PostingState:
    """The part targets, role targets, deltas and posting intents of one book (§14.2).
    ``new_events`` are the ``(contract key, event key)`` pairs of the first-included events in
    ENG-06 order (stage 13 ``new_event_keys``); every intent line carries those of its subject's
    member contracts as ``source_event_keys`` (S14-R-13a; D-98 95)."""
    source = st.costs
    if not isinstance(source, PartSource):
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "stage 14 reads no part inputs from the consumed state",
            subject_key=st.allocated.group_code,
            detail={"rule": "S14-R-01"},
        )
    if posted is None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            "stage 14 derives deltas without the posted amounts of the bundle",
            subject_key=st.allocated.group_code,
            detail={"rule": "S14-R-04"},
        )
    classes_posted_by(str(ctx.trigger), pass_name)
    parts = part_targets(ctx, st, source.part_inputs)
    # S14-R-09a: the approved lines of manual journals and reclassifications join as role targets.
    roles = manual.merged(role_targets(ctx, parts, tb), manual.role_targets(ctx, st.allocated, tb))
    totals = PostedTotals.of(
        ctx,
        posted,
        group_code=st.allocated.group_code,
        contracts=[view.header.external_id for view in st.allocated.contracts],
    )
    # S07-R-07 / S14-R-26: the imported role amounts of the RECOMPUTE openings at their cutover;
    # JET-03 carries a difference only where ENGINE lines are recomputed through it (S10-R-03).
    found = onboarding.openings(st.allocated)
    documents = st.costs.balances.documents if isinstance(st.costs, BalanceSource) else ()
    imported, unposted = onboarding.imported_role_amounts(
        ctx, parts, found, onboarding.recomputed_billing(found, documents)
    )
    deltas = derive_deltas(
        ctx, st.allocated, roles, totals, tb, pass_name=pass_name, voided=voided, imported=imported
    )
    entries = group_into_entries(ctx, st.allocated, deltas, tb, new_events=new_events)
    return PostingState(
        allocated=st.allocated,
        part_targets=parts,
        role_targets=roles,
        deltas=deltas,
        posting_intents=entries.intents,
        effective_dates=entries.effective_dates,
        line_rates=entries.line_rates,
        posting_kind=_posting_kind(ctx, pass_name, deltas),
        findings=tuple(sorted((*entries.findings, *unposted), key=Finding.sort_key)),
    )


def _posting_kind(ctx: BookContext, pass_name: str | None, deltas: Sequence[RoleDelta]) -> str:
    """E-31: the pass of a close run, ``VOID_REVERSAL`` for a void, else ``ENGINE_COMPUTE``."""
    if str(ctx.trigger) == "CLOSE_RELEASE" and pass_name is not None:
        return pass_name
    if any(delta.reason_code == VOID for delta in deltas):
        return "VOID_REVERSAL"
    return "ENGINE_COMPUTE"
