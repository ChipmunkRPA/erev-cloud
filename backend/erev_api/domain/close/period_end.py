"""The period-end passes of a close run: FX remeasurement, the release of what only a period end
decides, and the netting reclass (05 RCP-05 to RCP-08 rev 1.9; ENGINE_SPEC_B §14.2 S14-R-04,
S14-R-05, S14-R-07, Table 14-A; POLICIES JET-01b, JET-06, JET-10, JET-12; 04 T-SL-01, T-SL-04,
T-CON-03; supervisor rulings R-79 (a) to (e), R-112 (a), R-114 (a), (b) and R-116 (e); BUILD_SPEC
CLO-20, CLO-GATE-RUN-1).

What a pass posts. The engine posts the revenue of a deterministic schedule when the contract is
computed, in every open period (R-79 (a); ``erev_engine.stages.s13_books.costs_view``). A pass
posts what only a period end decides — the ``TIME`` amounts of Table 14-A: the period-end FX
remeasurements (JET-10), loss provisions (JET-12), the dated 606-10-25-7 releases (JET-01b) and
the parts with a ``TIME`` share, and the netting reclass with its reversal (JET-06). Every path
posts "cumulative target minus posted" (RCP-06), so a pass with nothing new posts nothing.

``engine_pass`` is the engine entry (R-79 (c)); it lives beside the bundles
(``contracts.period_ends``), where a computation runs the same passes dry.

``post_pass`` is one close-run step (R-79 (d), (e)), in the caller's unit of work. Every computed
group that touches the entity — a member contract is the entity's, it carries ledger lines of the
entity (an obligation it performs for another contracting entity), or it holds a mark of the
entity and book (below) — is taken in id order: its row is locked (RCP-22), its bundle built at
the step's record time with the sealed ledger as ``posted``, and the pass run. The pass's ``TIME``
intents of the run's entity, book and period are sealed once every group has been computed, so
the book's chain head is held for the writes and not for the computation (05 PERF-26): one
posting per group for the release
(``release:<close run>:<group>``, kind ``CLOSE_RELEASE``), one posting per entity for the FX
remeasurement (``fx:<close run>:<entity>``) and one for the netting reclass
(``reclass:<close run>:<entity>``). The reclass posting also carries the reversal the engine dates
the first day of the next period, when that period is open (RCP-08 (b)); when it is not, the next
period's own pass posts it. A line is dated the last day of its period, a reversal line the first
day of its period (ENGINE_SPEC_B L2-5-Q-31).

Periods close in order (supervisor ruling R-112). The engine's pass emits the ``TIME`` amounts of
every postable period through the horizon (S14-R-04); a close run takes its own period's. An
amount of an earlier period — a period end no close run has posted — refuses the step by name
(409 ``invalid-transition``, ``EARLIER_UNPOSTED``): nothing of the step is sealed, the run ends
``FAILED`` there and is resumed after the earlier period's own run. A later period's amounts are
left to its own run.

An earlier period has such an amount when a group's ``TIME`` intents for it do not net to zero in
some account role and currency, transaction or functional (supervisor ruling R-114 (a)). A set
that nets to zero in every role is no unposted period end, and a later period closes over it. The
rule was made for a posted amount the engine emitted again together with its own reversal where
it could not read the amount back under the key it posted it with — a loss unit's provision,
until the ledger stored the subject key (04 T-SL-04 rev 1.282; ruling R-11 as amended, item
ENG-COST-READBACK-1) — and it stands as it is. No run seals such a set outside its own period.

[J] The net is taken per contract group — the pass runs group by group — so the amounts of two
groups never cancel each other.

The mark of a group's period ends (04 T-CON-03 ``period_ends_open``; item CLO-GATE-RUN-1). The
first period-end step of a run — the pass ``PASSES[0]`` — sets, for a group it passed, the
entry of the run's entity and book to the day after the period's last day
(``contracts.period_ends.passed``), in the step's transaction and under the group locks it holds.
A step that is refused keeps nothing of it. The lock's gate ``CLOSE_RUN_COMPLETED`` reads the
entries (``close.gates``); a computation lowers them again (``contracts.period_ends``).

The mark moves forward only by the run of the period it stands at (item CLO-GATE-RUN-2; 04
T-CLS-01 rev 1.228; review finding F1 of 2026-10-01). A group that holds a mark BEFORE the run's
period refuses the first step, with R-112's sentence and before anything is sealed: the mark says
that a period end of an earlier period is to post, and a pass sees only the amounts of its own
kind — the FX pass does not see an unposted release or reclass. A group without a mark is marked
only when the run's period is the earliest postable one; otherwise it is passed and left
unmarked, with no refusal, since nothing recorded says that an amount exists. Measured before:
February's first step wrote a mark lowered into January as 1 March, its reclass step then
refused naming January, and January's gate passed — the lock was approved with January's reclass
unposted.

A mark in a closed period says no more than the closed periods do (04 T-CLS-01 rev 1.228, second
part). The refusal over a mark names a POSTABLE period — the earliest one that ends on or after
the mark and starts before the run's period — as R-112's refusal over an amount does: a pass
emits the ``TIME`` amounts of postable periods only. What a closed period lacks is the engine's
to carry, never a close run's of that period (ENGINE_SPEC_B S14-R-05 to S14-R-07): the FX pass
of the first later open period posts the cumulative ``TIME`` difference of the locked periods,
a computation posts the other closed-period amounts as carries, and a locked period's reclass
is not carried. So a group whose mark lies in a closed period, with no postable period between
it and the run's, is passed and marked like a group without one. Such a mark is what a waived
quarantine leaves (T-CLS-01 "Ends of a run"): the group is dirty, every step skips it, and its
period locks by the two waivers. Without this reading the first step of every later run was
refused naming the locked period once the group computed again — and no close run starts in a
closed period.

What a run read (item CLO-RATE-AFTER-RUN-1; 04 T-CLS-01 "What a run read", rev 1.291). The first
period-end step — the pass ``PASSES[0]``, the step that writes the marks — reads FIRST, before it
lists a group, what its passes can read of the tenant's reference data (``run_inputs.read``: the
exchange rates in force through the period's last day and the period-pinned policy values, as
two digests) and hands them to the run, which stores them with the step. The gate
``CLOSE_RUN_COMPLETED`` compares them with the same read later (``close.gates``): a rate replaced
after the run, or a policy value of the period that changes after it, asks for another run; a
policy value that takes effect after the period's last instant is not the period's and asks for
nothing. First, because a version that commits while the step runs must count as not read.

A group the bundle is behind is left out (item CLOSE-PASS-BEHIND-GROUP-1; the supervisor's
ruling of 2026-10-02 17:30; 04 T-CLS-01 "Period-end steps" rev 1.304; 05 RCP-08 rev 1.209). A
step is one transaction over every group of the entity, and it builds each group's bundle at the
STEP's cutoff: what was recorded by the start of the step. A command recorded and computed for a
group after the step began and before the pass reached that group leaves the group clean — the
pass did not skip it — and the bundle without the command's facts: the pass posted target minus
posted against a state the group had left. Measured before the item (SF-ORD-EU-3002, an invoice
of EUR 2,000.00 dated 31 Aug 2026 computed while a step stood between two groups): the FX step
posted a remeasurement of 50.00 where 40.00 is right and wrote the group's mark forward, so the
run ``SUCCEEDED`` and the gate ``CLOSE_RUN_COMPLETED`` passed; the reclass step, held the same
way, posted 11,050.00 where 8,840.00 is right, caught only because the computation's mark stood.

So, under the group's row lock and before the engine runs, a pass asks whether its bundle is
behind the group — ``contracts.computation.behind_its_group``, the rule a computation is held to
(04 §14.1 "A computation behind its group"): a member's stream head beyond the bundle's, a mark
set after the cutoff, or a head computation made after it — and such a group is LEFT OUT and
counted with the skipped ones, as a dirty group is. Nothing is posted from that bundle in any of
the three steps. In the first step the group is not passed, so it is not marked: the mark the
computation left stands, the gate reads the run as out of date, and the next run — on a later
cutoff — posts the group. The cutoff is not moved: what a step read stays one instant.

[J] Known limitation CLOSE-PASS-TRACE-1 (R-79 (d)): a pass stores sealed postings only — no
computation row, no contract version and no calculation trace — so a close-run line carries its
contract, period, role and trace node id and has no stored trace or replay evidence until the pass
is a member of the canonical input (item ENG-PASS-CANONICAL-1).

[J] A group that is dirty (a waived quarantine, or an event recorded since ``RECOMPUTE_DIRTY``) is
left out and counted: its ledger is not what its events say, so a pass over it would post against
stale figures; ``NO_DIRTY_GROUPS`` keeps the lock closed for it.

[J] A group the engine refuses stops the step, by name: nothing of the step is kept (04 T-CLS-01
"Ends of a run") and the run is resumed once the cause — a closing rate that is not published, say
— is corrected.

[J] The passes run group by group in the job's process (R-79 (e)); batch loading (RCP-16) and the
process pool (RCP-23) are item PERF-CLOSE-FANOUT-1.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine import dates
from erev_engine.bundle import InputBundle, PostingIntent
from erev_engine.errors import EngineError
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from erev_api.db.tables import combination_group, contract, period, period_state, subledger_line
from erev_api.domain.close import run_inputs
from erev_api.domain.contracts import bundles, computation, period_ends, repo
from erev_api.domain.contracts.period_ends import (
    CLOSE_RELEASE,
    FX_REMEASUREMENT,
    NETTING_RECLASS,
    PASSES,
    TIME,
    engine_pass,
)
from erev_api.domain.journals import subledger
from erev_api.enums import ComputationTrigger, SubledgerPostingKind
from erev_api.logging import get_logger
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from erev_api.domain.close.gates import PeriodScope
    from erev_api.uow import UnitOfWork

__all__ = [
    "CLOSE_RELEASE",
    "FX_REMEASUREMENT",
    "NETTING_RECLASS",
    "PASSES",
    "PassResult",
    "engine_pass",
    "fx_key",
    "post_pass",
    "reclass_key",
]

# 04 E-31: the posting kind of each pass (T-SL-01 requires the close run for the three).
POSTING_KINDS: Final[Mapping[str, SubledgerPostingKind]] = {
    FX_REMEASUREMENT: SubledgerPostingKind.FX_REMEASUREMENT,
    CLOSE_RELEASE: SubledgerPostingKind.CLOSE_RELEASE,
    NETTING_RECLASS: SubledgerPostingKind.NETTING_RECLASS,
}
REVERSAL_KIND: Final = "NETTING_RECLASS_REVERSAL"  # E-29: JET-06, dated the next period's first day
DESCRIPTIONS: Final[Mapping[str, str]] = {
    FX_REMEASUREMENT: "FX remeasurement of {entity} {period} ({no})",
    CLOSE_RELEASE: "Period-end release of {group} for {entity} {period} ({no})",
    NETTING_RECLASS: "Contract balance reclassification of {entity} {period} ({no})",
}
PASS_LABELS: Final[Mapping[str, str]] = {
    FX_REMEASUREMENT: "FX remeasurement",
    CLOSE_RELEASE: "period-end release",
    NETTING_RECLASS: "contract balance reclassification",
}
REFUSED: Final = "The {label} of contract group {group} stopped: {code}: {message}"
# Supervisor ruling R-112: periods close in order; the period is named as PRD IMP-132 names one.
EARLIER_UNPOSTED: Final = (
    "{period} has period-end amounts no close run has posted; run its close first."
)
RULE_ORDER: Final = "T-CLS-01"


def fx_key(close_run_id: UUID, entity_id: UUID) -> str:
    """T-SL-01 idempotency key of a close run's FX remeasurement posting."""
    return f"fx:{close_run_id}:{entity_id}"


def reclass_key(close_run_id: UUID, entity_id: UUID) -> str:
    """T-SL-01 idempotency key of a close run's netting reclass posting."""
    return f"reclass:{close_run_id}:{entity_id}"


# --- one step ------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PassResult:
    """What a pass posted for a close run: the postings and lines it sealed, the groups it ran
    over and the dirty groups it left out; and, from the first period-end step, what the run's
    passes could read beside the contracts (``run_inputs.read``; None from the other two)."""

    postings: int
    lines: int
    groups: int
    groups_skipped: int
    inputs: run_inputs.RunInputs | None = None


@dataclass(frozen=True, slots=True)
class _Planned:
    """One posting to seal: its key, its description, its group when it is a group's, its lines."""

    key: str
    description: str
    group_id: UUID | None
    lines: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class _GroupPass:
    """The pass over one group: its code, the T-SL-04 line values and the entries the run takes,
    and the earliest earlier period the pass has an amount for — (last day, period key) — which
    refuses the step (R-112)."""

    code: str
    lines: list[dict[str, Any]]
    entries: int
    earlier: tuple[date, str] | None


def _groups(session: Session, scope: PeriodScope) -> list[tuple[UUID, bool]]:
    """(group id, dirty) of the computed groups that touch the entity, in id order: a member
    contract is the entity's, or carries subledger lines of the entity in the run's book, or the
    group holds a mark of the entity and book (04 T-CON-03 ``period_ends_open``) — an entry a
    computation set must be met by a pass, or it would hold the lock's gate for good.

    A mark lists a group only while the group holds a member (item CLO-GROUPS-EMPTY-MEMBER-1; 04
    T-CLS-01 rev 1.255; 05 RCP-08 rev 1.183).
    The group a combination left empty keeps its head computation and its mark and has no
    contract: no bundle can be built of it (``bundles.build`` raises), it has no period end,
    and the gate ``CLOSE_RUN_COMPLETED`` never counts it (04 §16.8 rev 1.228). Until this guard
    only its ``dirty_since`` — set by the combination and never cleared — kept every step from
    reading it."""
    of_entity = exists().where(
        subledger_line.c.tenant_id == contract.c.tenant_id,
        subledger_line.c.contract_id == contract.c.id,
        subledger_line.c.entity_id == scope.entity_id,
        subledger_line.c.book_code == scope.book_code,
    )
    member = exists().where(
        contract.c.tenant_id == combination_group.c.tenant_id,
        contract.c.combination_group_id == combination_group.c.id,
        or_(contract.c.contracting_entity_id == scope.entity_id, of_entity),
    )
    holds_a_member = exists().where(
        contract.c.tenant_id == combination_group.c.tenant_id,
        contract.c.combination_group_id == combination_group.c.id,
    )
    marked = and_(
        combination_group.c.period_ends_open.has_key(
            period_ends.scope_key(scope.entity_code, scope.book_code)
        ),
        holds_a_member,
    )
    return [
        (UUID(str(group_id)), dirty_since is not None)
        for group_id, dirty_since in session.execute(
            select(combination_group.c.id, combination_group.c.dirty_since)
            .where(combination_group.c.head_computation_id.is_not(None), or_(member, marked))
            .order_by(combination_group.c.id)
        )
    ]


def _next_period(session: Session, scope: PeriodScope) -> str | None:
    """The key of the period that follows the run's period in its calendar."""
    found = session.execute(
        select(period.c.period_key)
        .where(
            period.c.calendar_id
            == select(period.c.calendar_id).where(period.c.id == scope.period_id).scalar_subquery(),
            period.c.start_date > scope.end_date,
        )
        .order_by(period.c.start_date)
        .limit(1)
    ).scalar_one_or_none()
    return None if found is None else str(found)


def _postable_from(session: Session, scope: PeriodScope, day: date) -> tuple[date, str] | None:
    """(last day, period key) of the earliest POSTABLE period of the run's entity and book that
    ends on or after ``day`` and starts before the run's period: the period whose own run a
    mark at ``day`` waits for. None when every such period is closed — a mark that lies there
    says no more than the closed periods do (module docstring)."""
    found = session.execute(
        select(period.c.end_date, period.c.period_key)
        .select_from(
            period_state.join(
                period,
                (period.c.tenant_id == period_state.c.tenant_id)
                & (period.c.id == period_state.c.period_id),
            )
        )
        .where(
            period_state.c.entity_id == scope.entity_id,
            period_state.c.book_code == scope.book_code,
            period_state.c.state.in_(sorted(dates.POSTABLE_STATES)),
            period.c.end_date >= day,
            period.c.start_date < scope.start_date,
        )
        .order_by(period.c.start_date)
        .limit(1)
    ).first()
    return None if found is None else (found[0], str(found[1]))


def _no_earlier_postable(session: Session, scope: PeriodScope) -> bool:
    """Whether the run's period is the earliest postable period of its entity and book: the
    first step then marks every group it passed; otherwise only a group whose mark stands on or
    after the period's first day (item CLO-GATE-RUN-2)."""
    earlier = session.execute(
        select(period_state.c.id)
        .select_from(
            period_state.join(
                period,
                (period.c.tenant_id == period_state.c.tenant_id)
                & (period.c.id == period_state.c.period_id),
            )
        )
        .where(
            period_state.c.entity_id == scope.entity_id,
            period_state.c.book_code == scope.book_code,
            period_state.c.state.in_(sorted(dates.POSTABLE_STATES)),
            period.c.start_date < scope.start_date,
        )
        .limit(1)
    ).first()
    return earlier is None


def _period_name(session: Session, scope: PeriodScope, period_key: str) -> str:
    """The name of the period ``period_key`` in the calendar of the run's period."""
    found = session.execute(
        select(period.c.name).where(
            period.c.calendar_id
            == select(period.c.calendar_id).where(period.c.id == scope.period_id).scalar_subquery(),
            period.c.period_key == period_key,
        )
    ).scalar_one_or_none()
    return period_key if found is None else str(found)


def _wanted(
    intent: PostingIntent, scope: PeriodScope, pass_name: str, next_period_key: str | None
) -> bool:
    """A ``TIME`` intent of the run's entity in the run's period; for the netting reclass also
    the reversal dated the first day of the next period (RCP-08 (b)). A later period's own
    amounts are left to its own close run; an earlier period's refuse the step (``_earlier``)."""
    if intent.posting_class != TIME or intent.entity != scope.entity_code:
        return False
    if intent.posting_period_key == scope.period_key:
        return True
    return (
        pass_name == NETTING_RECLASS
        and intent.entry_kind == REVERSAL_KIND
        and next_period_key is not None
        and intent.posting_period_key == next_period_key
    )


def _earlier(
    intents: Iterable[PostingIntent], scope: PeriodScope, days: Mapping[str, tuple[date, date]]
) -> tuple[date, str] | None:
    """(last day, period key) of the earliest period before the run's whose period end the pass
    still holds for the run's entity: its ``TIME`` intents for that period do not net to zero in
    some account role and currency, transaction or functional (supervisor rulings R-112 (a),
    R-114 (a); ``period_ends.unposted``). A set that nets to zero in every role is no unposted
    period end."""
    return min(
        (
            (days[period_key][1], period_key)
            for entity, period_key in period_ends.unposted(intents)
            if entity == scope.entity_code
            and period_key in days
            and days[period_key][1] < scope.start_date
        ),
        default=None,
    )


def _unposted(session: Session, scope: PeriodScope, period_key: str) -> Problem:
    """409 ``invalid-transition`` naming the earlier period whose close comes first (R-112)."""
    message = EARLIER_UNPOSTED.format(period=_period_name(session, scope, period_key))
    return Problem(
        "invalid-transition",
        message,
        errors=[ProblemError(field="period_id", rule_id=RULE_ORDER, message=message)],
    )


def _period_days(bundle: InputBundle, entity_code: str) -> Mapping[str, tuple[date, date]]:
    """(first day, last day) of each period of the entity's calendar, by period key."""
    return {
        item.period_key: (item.start_date, item.end_date)
        for entity in bundle.entities
        if entity.code == entity_code
        for item in entity.periods
    }


def _refused(pass_name: str, group_code: str, error: EngineError) -> Problem:
    """422 ``validation-failed`` naming the pass, the group and the engine's code (DG-CMD-04)."""
    message = REFUSED.format(
        label=PASS_LABELS[pass_name], group=group_code, code=error.code, message=error.message
    )
    return Problem(
        "validation-failed",
        message,
        code=error.code,
        errors=[ProblemError(field=error.subject_key, rule_id=error.code, message=message)],
    )


def _group_lines(
    uow: UnitOfWork,
    scope: PeriodScope,
    group_id: UUID,
    pass_name: str,
    next_period_key: str | None,
    *,
    first_entry_no: int,
    waited_for: dict[date, tuple[date, str] | None] | None,
) -> _GroupPass | None:
    """The pass over one group, or None for a group that is left out: one that became dirty
    since it was selected, or one whose bundle is behind it (module docstring; the engine does
    not run for it). The group row is locked before its bundle is assembled (RCP-22) and stays
    locked to the end of the step. A group whose pass has an amount of an earlier period carries
    that period and no lines: the step is refused (R-112). ``waited_for`` is the first
    period-end step's — None in
    the other two: per mark it met, the postable period that mark waits for
    (``_postable_from``), read once in the step."""
    session = uow.session
    group = repo.lock_group(session, group_id)
    if group["dirty_since"] is not None:
        return None
    code = str(group["code"])
    if waited_for is not None:
        # item CLO-GATE-RUN-2 (review finding F1): a mark before the run's period is a recorded
        # fact that an earlier period end is to post, whichever pass would post it, and this is
        # the step that would write the mark forward — it is refused, by R-112's order, naming
        # the postable period the mark waits for; a mark with none says no more than the
        # closed periods do, and the group is passed
        held = (group["period_ends_open"] or {}).get(
            period_ends.scope_key(scope.entity_code, scope.book_code)
        )
        day = None if held is None else date.fromisoformat(str(held))
        if day is not None and day < scope.start_date:
            if day not in waited_for:
                waited_for[day] = _postable_from(session, scope, day)
            holder = waited_for[day]
            if holder is not None:
                return _GroupPass(code=code, lines=[], entries=0, earlier=holder)
    bundle = bundles.build(session, group_id, uow.now, (), ComputationTrigger.CLOSE_RELEASE)
    found = bundles.index(session, bundle)
    behind = computation.behind_its_group(uow, bundle, found)
    if behind:
        # item CLOSE-PASS-BEHIND-GROUP-1: something was committed for the group after the
        # step's cutoff — the bundle does not hold it and the ledger does. Nothing is posted
        # from this bundle and the group is not passed; the next run's cutoff covers it.
        get_logger(__name__).info(
            "close.pass_behind_group",
            combination_group_id=str(group_id),
            behind_codes=list(behind),
            trigger_code=bundle.trigger,
        )
        return None
    try:
        output = engine_pass(bundle, pass_name)
    except EngineError as error:
        raise _refused(pass_name, code, error) from error
    days = _period_days(bundle, scope.entity_code)
    books = [book for book in output.books if book.book_code == scope.book_code]
    earlier = _earlier((intent for book in books for intent in book.posting_intents), scope, days)
    if earlier is not None:
        return _GroupPass(code=code, lines=[], entries=0, earlier=earlier)
    lines: list[dict[str, Any]] = []
    entries = 0
    for book_output in books:
        intents = sorted(
            (
                intent
                for intent in book_output.posting_intents
                if _wanted(intent, scope, pass_name, next_period_key)
            ),
            key=lambda intent: intent.entry_key,
        )
        if not intents:
            continue
        first = first_entry_no + entries
        book_lines = computation.book_lines(
            session, bundle, found, book_output, intents, stored=None, first_entry_no=first
        )
        # L2-5-Q-31: a period-end amount is dated the last day of its period, the reversal of a
        # netting reclass the first day of its period.
        dated = {
            first + offset: days[intent.posting_period_key][
                0 if intent.entry_kind == REVERSAL_KIND else 1
            ]
            for offset, intent in enumerate(intents)
        }
        for line in book_lines:
            line["effective_date"] = dated[int(line["entry_no"])]
        lines += book_lines
        entries += len(intents)
    return _GroupPass(code=code, lines=lines, entries=entries, earlier=None)


def post_pass(
    uow: UnitOfWork,
    *,
    close_run_id: UUID,
    close_run_no: str,
    scope: PeriodScope,
    pass_name: str,
    beat: Callable[[], None] = lambda: None,
) -> PassResult:
    """Run ``pass_name`` for the close run of ``scope`` and seal what it posts (module
    docstring). ``beat`` is called after every group (the job's heartbeat)."""
    if pass_name not in PASSES:
        raise ValueError(f"unknown close-run pass {pass_name!r} (S14-R-05)")
    session = uow.session
    # item CLO-RATE-AFTER-RUN-1: read FIRST, before a group is listed — a rate or a policy value
    # that commits while the step runs is then one the run did not read
    inputs = run_inputs.read(session, scope, uow.now) if pass_name == PASSES[0] else None
    groups = _groups(session, scope)
    next_period_key = _next_period(session, scope) if pass_name == NETTING_RECLASS else None
    per_group = pass_name == CLOSE_RELEASE
    named = {"entity": scope.entity_code, "period": scope.period_key, "no": close_run_no}
    planned: list[_Planned] = []
    pooled: list[dict[str, Any]] = []
    passed: list[UUID] = []
    entries = skipped = 0
    earliest: tuple[date, str] | None = None
    waited_for: dict[date, tuple[date, str] | None] | None = {} if pass_name == PASSES[0] else None
    for group_id, dirty in groups:
        found = (
            None
            if dirty
            else _group_lines(
                uow,
                scope,
                group_id,
                pass_name,
                next_period_key,
                first_entry_no=1 if per_group else entries + 1,
                waited_for=waited_for,
            )
        )
        beat()
        if found is None:
            skipped += 1
            continue
        passed.append(group_id)
        if found.earlier is not None:
            earliest = found.earlier if earliest is None else min(earliest, found.earlier)
        if not found.lines:
            continue
        if per_group:
            planned.append(
                _Planned(
                    key=subledger.release_key(close_run_id, group_id),
                    description=DESCRIPTIONS[pass_name].format(group=found.code, **named),
                    group_id=group_id,
                    lines=found.lines,
                )
            )
        else:
            pooled += found.lines
            entries += found.entries
    if earliest is not None:
        # R-112: the earliest such period over every group, so that the closes are run in order
        raise _unposted(session, scope, earliest[1])
    if pooled:
        key = (
            fx_key(close_run_id, scope.entity_id)
            if pass_name == FX_REMEASUREMENT
            else reclass_key(close_run_id, scope.entity_id)
        )
        planned.append(
            _Planned(
                key=key,
                description=DESCRIPTIONS[pass_name].format(**named),
                group_id=None,
                lines=pooled,
            )
        )
    line_count = 0
    for item in planned:
        posted = subledger.post(
            uow,
            book_code=scope.book_code,
            posting_kind=POSTING_KINDS[pass_name],
            idempotency_key=item.key,
            description=item.description,
            lines=item.lines,
            combination_group_id=item.group_id,
            close_run_id=close_run_id,
            require_subject_key=True,
        )
        if posted.replayed:
            # A step is one transaction, so a key of this run and pass is never met twice; met
            # with amounts still to post, the stored posting is not what the ledger needs.
            raise ValueError(
                f"posting {item.key} exists and the {PASS_LABELS[pass_name]} still has amounts "
                "to post (T-SL-01)"
            )
        line_count += len(posted.line_ids)
    if pass_name == PASSES[0]:
        # item CLO-GATE-RUN-1: the first period-end step marks the period ends of its scope
        period_ends.passed(
            uow,
            passed,
            period_ends.scope_key(scope.entity_code, scope.book_code),
            scope.start_date,
            scope.end_date,
            earliest_postable=_no_earlier_postable(session, scope),
        )
    return PassResult(
        postings=len(planned),
        lines=line_count,
        groups=len(groups) - skipped,
        groups_skipped=skipped,
        inputs=inputs,
    )
