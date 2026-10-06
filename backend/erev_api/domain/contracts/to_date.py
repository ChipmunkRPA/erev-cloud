"""To-date measures of a contract version at the cut of ``as_of`` (04 API-C-10 rev 1.132, 1.174,
1.178 and 1.179, API-S-Context; 03 REQ-REC-021, REQ-PLT-030; ENGINE_SPEC CV-50, S04-R-02, Table
0.9-A; ENGINE_SPEC_B S09-R-23, S09-R-26, S09-R-44 to S09-R-46, S10-R-05, S10-R-26, S15-R-07a;
supervisor rulings R-76 (a), R-85, R-114 (f), R-116 (a) and R-118 (a)).

A contract version stores its measures at its effective date d_v. A read serves the to-date
measures at the *cut* instead: the end of the period that contains ``as_of`` in the calendar of the
entity a measure belongs to, and not later than the *horizon*, the last period the member-balance
nodes of the obligation's contract carry. They are read from the period nodes of the version's
calculation trace:

- ``revenue_cum:<obligation>:<period>`` and ``progress_ratio:<obligation>:<period>`` (the periods
  of the performing entity), ``billed_cum:<obligation>:<period>`` (those of the contracting one);
- the member balances ``<measure>:<contract>@<entity>:<period>`` through
  ``reports.tie_outs.period_balances``, the reader supervisor ruling R-16 established;
- ``incentive_release_cum:<contract>@<entity>:<period>``, the cumulative JET-14 release the
  contract's revenue is net of (ENGINE_SPEC S04-R-02).

Every revenue, progress, billing and balance node carries the end date of its period
(``params.as_of``), so the period that contains a date is found among the nodes themselves and no
entity's calendar is read: ``legal_entity`` is RLS-TE, and a caller whose entities exclude the
performing entity of an obligation, or another member of the group, reads the same figures as
anyone else (``calc_trace``, ``obligation_version`` and ``period`` are tenant-wide). Only the start
of the first period a series measures is not in the trace; it is read from ``period`` by that
period's key and end date.

With Δ = an obligation's revenue at the cut less its revenue at d_v, the remaining allocation and
the gross RPO fall by Δ, and an obligation satisfied at the cut leaves the RPO. The remainder at
the cut decides in the other direction as well (rev 1.213; item RPT-RPO-ROLLFWD-1; supervisor
ruling R-121 (g)): an obligation that stage 15 left out at d_v because it was satisfied by
then is in the RPO of a cut before its satisfaction, with its remainder of that cut — as the RPO
report states it at that date (ENGINE_SPEC_B S15-R-08). The contract's
figures move by the sum over the group's obligations, its revenue also by the movement of the
JET-14 release between the period of d_v and the cut. The returns reduction of a returnable
obligation (S09-R-23) moves without an event when its window expires (S09-R-26), so the reported
allocation and the transaction price follow it to the cut.

The remainder has two parts (S09-R-45), and ``remainder_at`` says which one a movement leaves
(rev 1.174 and 1.179): revenue recognised since d_v leaves the scheduled amount first and the
awaiting-trigger amount for the rest, whatever the pattern; revenue a cut before d_v gives back
returns to the part the obligation's pattern names — the pattern the version's own trace states
(rev 1.178; ``Nodes.patterns``), so that the reader repeats no predicate of the engine. The
answer-key runner applies its own overlay to its checkpoints on the same nodes (L4-3-Q-10,
L5-3-Q-1): it takes Δ from the scheduled amount alone. It is the oracle's side, and no leaf of
the corpus tells the two apart (``tests/answer_keys/test_answer_key_reads.py``).

A measure the trace cannot answer is refused by name (``Unreadable``, rule id ``API-C-10``; the
balances keep the refusal of S15-R-07a) and is never replaced by the version's stored figure.
``load_nodes`` reads; ``nodes_of``, ``nodes_at``, ``version_at``, ``remainder_at``, ``balance_at``
and ``measured_at`` are pure.

A contract read takes the nodes of a page of versions whole. A report states every version of an
entity at one or two dates, and a trace holds a node per measure, subject and period: read whole,
a population's nodes are its periods times too many. ``load_nodes(..., days=...)`` therefore keeps,
of each period series, only the nodes a read at those dates can reach (``nodes_at``), and reads
the versions in portions.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any, Final, Protocol
from uuid import UUID

from erev_engine.currencies import ISO_4217
from erev_engine.money import minor_to_decimal, round_half_up
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key, obligation_subject_key
from sqlalchemy import select, text, tuple_
from sqlalchemy.orm import Session

from erev_api.db.tables import period
from erev_api.domain.reports import tie_outs
from erev_api.problems import Problem, ProblemError

__all__ = [
    "EMPTY",
    "BalanceAt",
    "Measured",
    "Node",
    "Nodes",
    "ObligationAt",
    "Point",
    "TraceNode",
    "Unreadable",
    "VersionAt",
    "balance_at",
    "firsts",
    "load_nodes",
    "measured_at",
    "net_moved",
    "nodes_at",
    "nodes_of",
    "version_at",
]

type Starts = Mapping[tuple[str, date], tuple[date, ...]]

RULE: Final = "API-C-10"
ZERO: Final = Decimal(0)
REVENUE: Final = "revenue_cum"
BILLED: Final = "billed_cum"
PROGRESS: Final = "progress_ratio"
RPO: Final = "rpo_amount"
RELEASE: Final = "incentive_release_cum"  # ENGINE_SPEC_B S10-R-26, per ``<contract>@<entity>``
TARGET: Final = "revenue_target_exact"
FIXED: Final = "#FIXED"  # the component of the returns reduction (ENGINE_SPEC_B S09-R-23)
REDUCE: Final = "REDUCE_CONTRACT_QUANTITY"  # POL-053
STATE: Final = "-"  # the period slot of a version-state node (ENGINE_SPEC CV-50)
# The obligation measures read by date: each of their period nodes carries its period's end.
DATED: Final = (REVENUE, BILLED, PROGRESS)
# The ``<contract>@<entity>`` measures read by the period key of that subject's cut.
KEYED: Final = (RELEASE,)
# The two parts of an obligation's remainder (04 T-CON-11). ``SCHEDULED`` is also the measure of
# the version-state node the reader takes the obligation's pattern from (``PATTERN``).
SCHEDULED: Final = "scheduled_amount"
AWAITING: Final = "awaiting_trigger_amount"
MEASURES: Final = (*DATED, *KEYED, RPO, TARGET, SCHEDULED, *tie_outs.BALANCE_MEASURES)
# What a read without balances needs of them: the periods a member subject carries, which one
# balance the engine publishes for every member and period end gives (zeros included).
HORIZON: Final = "contract_liability"
WITHOUT_BALANCES: Final = (*DATED, *KEYED, RPO, TARGET, SCHEDULED, HORIZON)
# ENGINE_SPEC_B S09-R-46; the statuses whose obligations carry RPO (04 T-CON-08 ``rpo_amount``).
CANCELLED: Final = "CANCELLED"
SATISFIED: Final = "SATISFIED"
UNSATISFIED: Final = "UNSATISFIED"
PARTIALLY_SATISFIED: Final = "PARTIALLY_SATISFIED"
RPO_STATUSES: Final = frozenset({UNSATISFIED, PARTIALLY_SATISFIED})
# ENGINE_SPEC_B S09-R-45 (stage 09 ``is_deterministic``; rev 1.126): time alone places the
# remainder of a deterministic component in later periods — it is scheduled; S09-R-44: unless a
# recognition hold is open (04 E-45), when it awaits a trigger as every other remainder does. The
# engine states both on the version-state node ``scheduled_amount:<obligation>:-`` of the trace
# (``rec.scheduled.v1``; ENGINE_SPEC_B §9.5): ``pattern`` is ``DETERMINISTIC`` or ``EVENT_DRIVEN``
# at d_v and ``held`` says whether a recognition hold is open there. The reader takes the pattern
# from that node (04 API-C-10 rev 1.178; supervisor ruling R-118 (a)) and repeats no predicate of
# the engine; it asks for it only where the stored split cannot answer: a look-back
# (``remainder_at``).
PATTERN: Final = ("pattern", "held")
DETERMINISTIC: Final = ("DETERMINISTIC", "false")  # time alone places the remainder; no hold
NOT_SERVED: Final = "Nothing is answered from the version's figure at {effective_date}."
STORED_NOT_SERVED: Final = "Nothing is answered from the version's stored figures."
UNTRACED: Final = (
    "Contract {contract}, obligation {obligation}: the calculation trace of contract version "
    "{version_no} holds no {measure} node per period, so the figure at {day} cannot be read. "
    + NOT_SERVED
)
UNDATED: Final = (
    "Contract {contract}, obligation {obligation}: a {measure} period node of contract version "
    "{version_no} carries no period end date, so the period that contains {day} cannot be found. "
    + NOT_SERVED
)
UNPLACED: Final = (
    "Contract {contract}, obligation {obligation}: {day} cannot be placed against {period}, the "
    "first period contract version {version_no} measures {measure} for; the tenant's calendars "
    "give that period {starts}. " + NOT_SERVED
)
REMAINDER_NEGATIVE: Final = (
    "Contract {contract}, obligation {obligation}: at {day} the revenue read from the calculation "
    "trace of contract version {version_no} leaves a scheduled amount of {scheduled} and an "
    "awaiting-trigger amount of {awaiting}; neither can be below zero (04 DB-17). " + NOT_SERVED
)
PATTERN_UNTRACED: Final = (
    "Contract {contract}, obligation {obligation}: the calculation trace of contract version "
    "{version_no} holds no scheduled_amount node of the obligation, so the part of its "
    "remainder that the revenue recognised after {day} had left cannot be named. " + NOT_SERVED
)
UNBOUND: Final = (
    "Obligation {obligation} of a member contract outside your entities: contract version "
    "{version_no} binds no node to it, so its figures at {day} cannot be read. " + STORED_NOT_SERVED
)
HORIZON_UNTRACED: Final = (
    "Contract {contract}: the calculation trace of contract version {version_no} holds no dated "
    "member-balance node of the contract, so the period its figures reach cannot be read. "
    + STORED_NOT_SERVED
)
MEMBER_UNPLACED: Final = (
    "Contract {contract} in entity {entity}: {day} cannot be placed against {period}, the first "
    "period contract version {version_no} measures its balances for; the tenant's calendars give "
    "that period {starts}. " + STORED_NOT_SERVED
)
RELEASE_UNTRACED: Final = (
    "The calculation trace of contract version {version_no} holds the consideration-payable "
    "release of {subject} without a dated period of that contract and entity, so the contract's "
    "revenue at {day} cannot be read. " + STORED_NOT_SERVED
)
# The node parameters the reader takes, in the order ``NODES`` selects them: the period's end
# date, the stage 15 inclusion of an obligation's RPO, the parameters of the returns reduction
# (ENGINE_SPEC_B S09-R-23), stage 15's reason for leaving an obligation out whatever its
# satisfaction (``excluded``: a contract that is not a contract in the book, D-91 (vii)) and what
# stage 09 decided of the obligation's remainder at d_v (``PATTERN``).
PARAMS: Final = (
    "as_of",
    "included",
    "scope",
    "unit_rate",
    "returned",
    "expected",
    "excluded",
    *PATTERN,
)
NODES: Final = text(
    "SELECT ct.contract_version_id, node ->> 'id' AS node_id, node ->> 'measure' AS measure, "
    "node ->> 'value' AS value, node -> 'params' ->> 'as_of' AS as_of, "
    "node -> 'params' ->> 'included' AS included, node -> 'params' ->> 'scope' AS scope, "
    "node -> 'params' ->> 'unit_rate' AS unit_rate, node -> 'params' ->> 'returned' AS returned, "
    "node -> 'params' ->> 'expected' AS expected, node -> 'params' ->> 'excluded' AS excluded, "
    "node -> 'params' ->> 'pattern' AS pattern, node -> 'params' ->> 'held' AS held "
    "FROM erev.calc_trace ct CROSS JOIN LATERAL jsonb_array_elements(ct.trace -> 'nodes') AS node "
    "WHERE ct.contract_version_id = ANY(:version_ids) "
    "AND node ->> 'measure' = ANY(:measures)"
)


class Unreadable(Problem):
    """04 API-C-10 (supervisor ruling R-76 (a)): a to-date measure the version's trace cannot
    answer at the cut — 422 ``validation-failed`` naming the contract, the obligation or entity,
    the measure and the date. No figure is served in its place."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(
            "validation-failed",
            "1 field needs attention.",
            errors=[ProblemError(field=field, rule_id=RULE, message=message)],
        )


# --- trace nodes ----------------------------------------------------------------------------------


class TraceNode(Protocol):
    """What the reader takes of a trace node; ``erev_engine.trace.TraceNode`` is one."""

    @property
    def id(self) -> str: ...
    @property
    def measure(self) -> str: ...
    @property
    def value(self) -> str: ...
    @property
    def params(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class Node:
    """A trace node as ``load_nodes`` reads it from ``calc_trace``."""

    id: str
    measure: str
    value: str
    params: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Point:
    """One period node of a series: the period's key, its end date and the node's value."""

    key: str
    end: date
    value: str


@dataclass(frozen=True, slots=True)
class Measured:
    """The period a to-date measure was read at (API-S-Context ``measured_period``)."""

    period_key: str
    end_date: date


@dataclass(frozen=True, slots=True)
class Nodes:
    """The to-date nodes of one version's trace.

    ``periods`` maps ``<measure>:<subject>`` of a ``DATED`` measure to its period nodes in date
    order and ``undated`` names the series, and the member subjects, that hold a node without an end
    date. ``keyed`` maps ``<measure>:<subject>`` of a ``KEYED`` measure to its (period key, value)
    pairs in period order. ``states`` maps ``<measure>:<subject>`` to the (value, ``included``
    parameter, ``excluded`` parameter) of its version-state node. ``balances`` are the
    member-balance nodes as the S15-R-07a reader takes them and ``members`` the periods each
    ``<contract>@<entity>`` subject carries. ``reductions`` maps the node id of a returnable
    obligation's ``revenue_target_exact`` node to its (unit rate, returned, expected) parameters.
    ``starts`` gives, for the first period of every series, the start dates the tenant's calendars
    hold for a period of that key and end date. ``patterns`` maps an obligation's subject to the
    (``pattern``, ``held``) parameters of its version-state ``scheduled_amount`` node.
    """

    periods: Mapping[str, tuple[Point, ...]]
    undated: frozenset[str]
    keyed: Mapping[str, tuple[tuple[str, str], ...]]
    states: Mapping[str, tuple[str, str | None, str | None]]
    balances: tie_outs.TracedBalances
    members: Mapping[str, tuple[Point, ...]]
    reductions: Mapping[str, tuple[str, str, str]]
    starts: Starts
    patterns: Mapping[str, tuple[str, str]]

    def at_key(self, measure: str, subject: str, period_key: str) -> Decimal | None:
        """A ``KEYED`` measure at the end of ``period_key``: its latest node not after that period
        (period keys sort in period order), 0 before its first node; None when the trace holds no
        period node of it."""
        series = self.keyed.get(f"{measure}:{subject}")
        if not series:
            return None
        value = ZERO
        for key, amount in series:
            if key > period_key:
                break
            value = Decimal(amount)
        return value


EMPTY: Final = Nodes({}, frozenset(), {}, {}, tie_outs.traced_balances(()), {}, {}, {}, {})


def _day(value: object) -> date | None:
    """The end date a period node carries in ``params.as_of``; None when it carries none (the
    member sums of stage 10 name their period key there)."""
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _in_order(point: Point) -> tuple[date, str]:
    return (point.end, point.key)


def firsts(nodes: Nodes) -> set[tuple[str, date]]:
    """The (period key, end date) of the first period of every dated series and member subject."""
    return {
        (points[0].key, points[0].end)
        for source in (nodes.periods, nodes.members)
        for points in source.values()
        if points
    }


def nodes_of(trace_nodes: Iterable[TraceNode], starts: Starts | None = None) -> Nodes:
    """``Nodes`` of the ``MEASURES`` nodes of one trace; ``starts`` as ``Nodes`` documents it
    (``firsts`` names the periods it must cover). Pure."""
    series: dict[str, list[Point]] = defaultdict(list)
    undated: set[str] = set()
    keyed: dict[str, list[tuple[str, str]]] = defaultdict(list)
    states: dict[str, tuple[str, str | None, str | None]] = {}
    pairs: list[tuple[str, str]] = []
    ends: dict[str, dict[str, date | None]] = defaultdict(dict)
    reductions: dict[str, tuple[str, str, str]] = {}
    patterns: dict[str, tuple[str, str]] = {}
    for node in trace_nodes:
        if node.measure not in MEASURES:
            continue
        head, _, slot = node.id.rpartition(":")
        params = node.params
        if node.measure == TARGET:
            reduction = tuple(params.get(name) for name in ("unit_rate", "returned", "expected"))
            if params.get("scope") == REDUCE and all(item is not None for item in reduction):
                reductions[node.id] = (str(reduction[0]), str(reduction[1]), str(reduction[2]))
            continue
        if node.measure == SCHEDULED:
            # the obligation's node states the pattern; the group's sum of the amounts does not
            stated = tuple(params.get(name) for name in PATTERN)
            if slot == STATE and all(item is not None for item in stated):
                patterns[head.partition(":")[2]] = (str(stated[0]), str(stated[1]))
            continue
        if slot == STATE:
            included, excluded = params.get("included"), params.get("excluded")
            states[head] = (
                node.value,
                None if included is None else str(included),
                None if excluded is None else str(excluded),
            )
            continue
        if node.measure in KEYED:
            keyed[head].append((slot, node.value))
            continue
        end = _day(params.get("as_of"))
        if node.measure in DATED:
            if end is None:
                undated.add(head)
            else:
                series[head].append(Point(slot, end, node.value))
            continue
        pairs.append((node.id, node.value))
        subject = head.partition(":")[2]
        if "@" in subject:
            known = ends[subject]
            known[slot] = known.get(slot) or end
    members: dict[str, tuple[Point, ...]] = {}
    for subject, keys in ends.items():
        dated = [Point(key, end, "") for key, end in keys.items() if end is not None]
        if len(dated) != len(keys):
            undated.add(subject)
        members[subject] = tuple(sorted(dated, key=_in_order))
    return Nodes(
        periods={head: tuple(sorted(points, key=_in_order)) for head, points in series.items()},
        undated=frozenset(undated),
        keyed={head: tuple(sorted(found)) for head, found in keyed.items()},
        states=states,
        balances=tie_outs.traced_balances(pairs),
        members=members,
        reductions=reductions,
        starts={} if starts is None else starts,
        patterns=patterns,
    )


def _starts(session: Session, wanted: set[tuple[str, date]]) -> Starts:
    """The start dates of the periods of ``wanted`` (period key, end date) in the tenant's
    calendars: one read over ``period``, which is tenant-wide."""
    if not wanted:
        return {}
    rows = session.execute(
        select(period.c.period_key, period.c.end_date, period.c.start_date).where(
            tuple_(period.c.period_key, period.c.end_date).in_(sorted(wanted))
        )
    )
    found: dict[tuple[str, date], set[date]] = defaultdict(set)
    for key, end, start in rows:
        found[(str(key), end)].add(start)
    return {pair: tuple(sorted(values)) for pair, values in found.items()}


# The versions one statement reads when a population is read at given dates: the rows of a
# portion are held at once, the kept nodes of every portion until the report is built.
PORTION: Final = 250


def _kept[T](
    items: Iterable[T],
    facts: Callable[[T], tuple[str, str, object, object]],
    days: Collection[date],
) -> list[T]:
    """``items`` — trace nodes in any shape, ``facts`` giving the (id, measure, ``params.as_of``,
    ``params.scope``) of one — without the nodes a read at the cuts of ``days`` cannot reach.

    A period series is the nodes of one measure and subject that carry an end date. The reader
    finds a date in a series by its neighbours (``_locate``: the first node ending on or after
    it), takes the horizon and ``latest`` from a last node and the first period's start for a
    first node; and the date it looks for is the day itself or the last period end of a
    member-balance series, which caps it (``_horizon``, ``_member``). So of every series the
    first and the last node stay, and around each of those dates the last node ending before it
    and the first ending on or after it.

    The balances of a member ``<contract>@<entity>`` are read by period key: the latest node of
    a measure at or before the period of the cut (``tie_outs.period_balances``), and the member
    sums of stage 10 carry that key and no date — a period of theirs is dated by the member's
    other nodes of the same key. So a member keeps, of every measure, the nodes of the periods
    its dated series keep, and of a measure without dates the latest node at or before each of
    those periods. A member one of whose periods no node dates is refused by the reader whatever
    the date: it keeps every node, so that the refusal names what the whole trace would.

    Every other node stays — a version state, a node of an obligation's series without an end
    date, which the reader must still see to refuse the series by name — and of the returns
    targets those the reader takes (``nodes_of``). The release of a consideration payable goes:
    its movement is measured from the version's own date, which is no date of the read."""
    found: list[T] = []
    dated: dict[str, list[tuple[date, str, T]]] = defaultdict(list)
    undated: dict[str, list[tuple[str, T]]] = defaultdict(list)
    parsed: dict[object, date | None] = {}
    for item in items:
        node_id, measure, as_of, scope = facts(item)
        if measure == TARGET:
            if scope == REDUCE:
                found.append(item)
            continue
        if measure in KEYED or measure not in MEASURES:
            continue
        head, _, slot = node_id.rpartition(":")
        if slot == STATE:
            found.append(item)
            continue
        if as_of not in parsed:
            parsed[as_of] = _day(as_of)
        ended = parsed[as_of]
        if ended is None:
            undated[head].append((slot, item))
        else:
            dated[head].append((ended, slot, item))
    # member subject → (the heads of its dated series, those of its undated ones)
    members: dict[str, tuple[list[str], list[str]]] = {}
    for head in dated:
        subject = head.partition(":")[2]
        if "@" in subject:
            members.setdefault(subject, ([], []))[0].append(head)
    for head in undated:
        subject = head.partition(":")[2]
        if "@" in subject:
            members.setdefault(subject, ([], []))[1].append(head)
    for points in dated.values():
        points.sort(key=lambda point: (point[0], point[1]))
    caps = {dated[head][-1][0] for of_dated, _ in members.values() for head in of_dated}
    wanted = sorted(set(days) | caps)

    def reached(points: Sequence[tuple[date, str, T]]) -> list[int]:
        ends = [point[0] for point in points]
        keep = {0, len(points) - 1}
        for day in wanted:
            index = bisect_left(ends, day)
            if index < len(points):
                keep.add(index)
            if index:
                keep.add(index - 1)
        return sorted(keep)

    for head, points in dated.items():
        if "@" not in head.partition(":")[2]:
            found.extend(points[index][2] for index in reached(points))
    for head, nodes in undated.items():
        if "@" not in head.partition(":")[2]:
            found.extend(item for _, item in nodes)
    for of_dated, of_undated in members.values():
        slots = {slot for head in of_dated for _, slot, _ in dated[head]}
        named = {slot for head in of_undated for slot, _ in undated[head]}
        if not named <= slots:
            # a period no node dates: the reader refuses the member; nothing of it is dropped
            found.extend(item for head in of_dated for _, _, item in dated[head])
            found.extend(item for head in of_undated for _, item in undated[head])
            continue
        kept = {dated[head][index][1] for head in of_dated for index in reached(dated[head])}
        for head in of_undated:
            nodes = sorted(undated[head], key=lambda node: node[0])
            keys = [slot for slot, _ in nodes]
            latest = {bisect_right(keys, slot) - 1 for slot in kept} - {-1}
            found.extend(nodes[index][1] for index in sorted(latest))
            kept |= {keys[index] for index in latest}
        for head in of_dated:
            found.extend(item for _, slot, item in dated[head] if slot in kept)
    return found


def _node_facts(node: TraceNode) -> tuple[str, str, object, object]:
    params = node.params
    return node.id, node.measure, params.get("as_of"), params.get("scope")


def nodes_at(trace_nodes: Iterable[TraceNode], days: Collection[date]) -> list[TraceNode]:
    """The nodes of one trace a read at the cuts of ``days`` needs (``_kept``). ``nodes_of`` of
    the result answers ``version_at(...).obligations``, ``balance_at`` and ``measured_at`` at each
    of ``days`` as ``nodes_of`` of the whole trace does; it holds no release of a consideration
    payable, so ``VersionAt.release_moved`` is the whole read's alone. Pure."""
    return _kept(trace_nodes, _node_facts, days)


def _node(row: Sequence[Any]) -> Node:
    """One row of ``NODES`` as a node; the parameters the trace does not carry are left out."""
    named = zip(PARAMS, row[4:], strict=True)
    return Node(
        id=str(row[1]),
        measure=str(row[2]),
        value=str(row[3]),
        params={name: item for name, item in named if item is not None},
    )


def _row_facts(row: Sequence[Any]) -> tuple[str, str, object, object]:
    # contract_version_id, node id, measure, value, then ``PARAMS``: as_of, included, scope, …
    return str(row[1]), str(row[2]), row[4], row[6]


def load_nodes(
    session: Session,
    version_ids: Sequence[Any],
    *,
    balances: bool = True,
    days: Collection[date] | None = None,
) -> dict[UUID, Nodes]:
    """``Nodes`` of each contract version of ``version_ids`` that has a trace: one read over
    ``calc_trace``, filtered to the measures in the database, and one over ``period``. Without
    ``balances`` (a list page, which shows none) the balance nodes are left in the database but
    for ``HORIZON``, about a third of the rows; ``balance_at`` needs them all.

    With ``days`` — a report, which states a population at those dates and at no other — the
    versions are read ``PORTION`` at a time and of each trace only the nodes ``nodes_at`` keeps
    become ``Nodes``; such ``Nodes`` answer a read at one of ``days`` only."""
    wanted = sorted({UUID(str(value)) for value in version_ids})
    if not wanted:
        return {}
    measures = list(MEASURES if balances else WITHOUT_BALANCES)
    found: dict[UUID, Nodes] = {}
    portions = (
        [wanted]
        if days is None
        else [wanted[index : index + PORTION] for index in range(0, len(wanted), PORTION)]
    )
    for portion in portions:
        traces: dict[UUID, list[Sequence[Any]]] = defaultdict(list)
        for row in session.execute(NODES, {"version_ids": portion, "measures": measures}):
            traces[UUID(str(row[0]))].append(row)
        for version_id, rows in traces.items():
            kept = rows if days is None else _kept(rows, _row_facts, days)
            found[version_id] = nodes_of(_node(row) for row in kept)
    starts = _starts(session, {pair for nodes in found.values() for pair in firsts(nodes)})
    return {version_id: replace(nodes, starts=starts) for version_id, nodes in found.items()}


# --- the cut --------------------------------------------------------------------------------------


class _Unplaced(Exception):
    """``day`` is not after the first period of a series and the tenant's calendars do not settle
    whether it lies inside that period."""

    def __init__(self, first: Point, known: tuple[date, ...]) -> None:
        super().__init__(first.key)
        self.first = first
        self.known = known

    def starts(self) -> str:
        if not self.known:
            return "no start date"
        listed = " and ".join(item.isoformat() for item in self.known)
        return f"the start dates {listed}"


def _locate(series: Sequence[Point], day: date, starts: Starts) -> Point | None:
    """The point of the period that contains ``day``: the first whose period ends on or after it
    (the periods of a series are consecutive), the last one when ``day`` lies beyond the series,
    None when ``day`` precedes the first period. ``_Unplaced`` when the calendars do not settle
    the start of the first period."""
    if day > series[-1].end:
        return series[-1]
    for index, point in enumerate(series):
        if point.end < day:
            continue
        if index:
            return point
        known = starts.get((point.key, point.end), ())
        if known and day >= known[-1]:
            return point
        if known and day < known[0]:
            return None
        raise _Unplaced(point, known)
    return series[-1]


def _measured(point: Point | None) -> Measured | None:
    return None if point is None else Measured(point.key, point.end)


@dataclass(frozen=True, slots=True)
class _Named:
    """What a refusal names: the contract, the obligation and the version."""

    contract: str
    obligation: str
    version_no: object
    effective_date: object

    def facts(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "obligation": self.obligation,
            "version_no": self.version_no,
            "effective_date": self.effective_date,
        }


def _measures(nodes: Nodes, measure: str, subject: str) -> bool:
    """Whether the trace holds a period node of the obligation's measure, dated or not."""
    head = f"{measure}:{subject}"
    return head in nodes.periods or head in nodes.undated


def _read(
    nodes: Nodes, measure: str, subject: str, day: date, named: _Named, *, stored: Any
) -> tuple[Decimal, Point | None]:
    """An obligation's measure at the end of the period that contains ``day`` and the node read:
    (0, None) before the first period the version measures. ``stored`` is the version's figure.

    The engine measures nothing per period for an obligation outside Topic 606 (S09-INV-05;
    REQ-CON-016) or routed to Topic 842 (S09-R-13), and its figure stays 0: a measure without a
    period node whose stored figure is 0 answers (0, None), as the S15-R-07a reader treats a
    balance the engine does not publish. ``Unreadable`` when a non-zero figure has no period node,
    a node carries no end date or the first period cannot be placed."""
    head = f"{measure}:{subject}"
    field = f"obligations[{subject}].{measure}"
    if head in nodes.undated:
        raise Unreadable(field, UNDATED.format(measure=measure, day=day, **named.facts()))
    series = nodes.periods.get(head)
    if not series:
        if Decimal(stored) == 0:
            return ZERO, None
        raise Unreadable(field, UNTRACED.format(measure=measure, day=day, **named.facts()))
    try:
        point = _locate(series, day, nodes.starts)
    except _Unplaced as unplaced:
        message = UNPLACED.format(
            measure=measure,
            day=day,
            period=unplaced.first.key,
            starts=unplaced.starts(),
            **named.facts(),
        )
        raise Unreadable(field, message) from None
    return (ZERO, None) if point is None else (Decimal(point.value), point)


def _subject(row: Mapping[str, Any], external_id: str | None) -> str | None:
    """The obligation's subject key: the engine's own key of the contract and obligation (CV-21),
    or, for a member contract the caller's entities exclude, the subject of a version-state node
    the obligation version binds (``<column>:<subject>:-``; ENGINE_SPEC CV-50) — its revenue node,
    its billing node when it has no revenue target, else any. None when it binds none."""
    if external_id is not None:
        return obligation_subject_key(external_id, str(row["obligation_key"]))
    bound: Mapping[str, Any] = row.get("trace_nodes") or {}
    for name in (REVENUE, BILLED, *sorted(bound)):
        anchor = bound.get(name)
        if isinstance(anchor, str) and anchor.startswith(f"{name}:") and anchor.endswith(":-"):
            return anchor[len(name) + 1 : -2]
    return None


def _unmeasured(nodes: Nodes, subject: str | None, row: Mapping[str, Any]) -> bool:
    """An obligation the engine takes no measure per period of: no period node of its revenue,
    billing or progress, and the version's three figures 0 (a line outside Topic 606 that was
    never billed). It stays as the version holds it and needs no horizon."""
    if any(Decimal(row[name]) != 0 for name in DATED):
        return False
    return subject is None or not any(_measures(nodes, name, subject) for name in DATED)


def _horizon(nodes: Nodes, subject: str, named: _Named) -> date:
    """The horizon of the obligation's contract: the end of the last period the member-balance
    nodes of that contract carry, whichever entity holds them. ``Unreadable`` when the trace holds
    no dated one."""
    prefix = f"{subject.partition('/')[0]}@"
    found = [
        points[-1].end
        for member, points in nodes.members.items()
        if member.startswith(prefix) and points and member not in nodes.undated
    ]
    if not found:
        raise Unreadable(
            f"balances[{prefix}]",
            HORIZON_UNTRACED.format(contract=named.contract, version_no=named.version_no),
        )
    return max(found)


def _status(stored: str, revenue: Decimal, progress: Decimal) -> str:
    # ENGINE_SPEC_B S09-R-46, as the answer-key runner's overlay applies it (L4-3-Q-10).
    if stored == CANCELLED:
        return stored
    if progress == 1:
        return SATISFIED
    if revenue == 0 and progress == 0:
        return UNSATISFIED
    return PARTIALLY_SATISFIED


def _reduction(parameters: tuple[str, str, str], minor_unit: int) -> int:
    """round(r × (Y + E)) of a returnable obligation in minor units (ENGINE_SPEC_B S09-R-23)."""
    rate, returned, expected = parameters
    return round_half_up(Fraction(rate) * (Fraction(returned) + Fraction(expected)), minor_unit)


def _returns_shift(nodes: Nodes, subject: str, at: Point | None, currency: str) -> Decimal:
    """The returns reduction at the cut less the reduction at d_v (ENGINE_SPEC_B S09-R-23,
    S09-R-26; L5-3-Q-1): 0 unless the obligation is returnable under POL-053
    ``REDUCE_CONTRACT_QUANTITY`` and both nodes exist."""
    spec = ISO_4217.get(currency)
    before = nodes.reductions.get(f"{TARGET}:{subject}{FIXED}:{STATE}")
    after = None if at is None else nodes.reductions.get(f"{TARGET}:{subject}{FIXED}:{at.key}")
    if spec is None or before is None or after is None:
        return ZERO
    unit = spec.minor_unit
    return minor_to_decimal(_reduction(after, unit) - _reduction(before, unit), unit)


def _release_moved(nodes: Nodes, version: Mapping[str, Any], d_v: date, as_of: date) -> Decimal:
    """The cumulative JET-14 release at the cut less the release the version's revenue is net of.

    ENGINE_SPEC S04-R-02: ``contract_version.revenue_cum`` is Σ obligation ``revenue_cum`` less
    ``incentive_release_cum`` of each member ``<contract>@<entity>`` at the contracting entity's
    period holding d_v. At the cut it is net of the release of the period of the cut, so the
    contract's revenue moves by the difference as well as by the obligations' Δ. 0 for a group
    without consideration payable to a customer."""
    moved = ZERO
    for head in nodes.keyed:
        measure, _, subject = head.partition(":")
        if measure != RELEASE:
            continue
        periods = nodes.members.get(subject)
        if not periods or subject in nodes.undated:
            message = RELEASE_UNTRACED.format(
                version_no=version["version_no"], subject=subject, day=as_of
            )
            raise Unreadable(f"balances[{subject}].{RELEASE}", message)
        found: list[Decimal] = []
        for day in (min(as_of, periods[-1].end), d_v):
            try:
                point = _locate(periods, day, nodes.starts)
            except _Unplaced as unplaced:
                contract, _, entity = subject.partition("@")
                message = MEMBER_UNPLACED.format(
                    contract=contract,
                    entity=entity,
                    day=day,
                    period=unplaced.first.key,
                    version_no=version["version_no"],
                    starts=unplaced.starts(),
                )
                raise Unreadable(f"balances[{subject}].{RELEASE}", message) from None
            at = None if point is None else nodes.at_key(RELEASE, subject, point.key)
            found.append(ZERO if at is None else at)
        moved += found[0] - found[1]
    return moved


# --- the overlay ----------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ObligationAt:
    """One obligation at the cut. ``delta`` is its revenue at the cut less its revenue at d_v,
    ``billed_delta`` the same for billing and ``shift`` the movement of its returns reduction.
    ``scheduled`` and ``awaiting`` are the two parts of its remainder at the cut: ``delta + shift``
    has left them as ``remainder_at`` says. ``measured`` is the period its revenue
    was read at and ``billed_measured`` the period of its billing; None before the first period
    the version measures, and for a measure the engine does not take per period."""

    revenue: Decimal
    billed: Decimal
    progress_ratio: Decimal
    delta: Decimal
    billed_delta: Decimal
    shift: Decimal
    scheduled: Decimal
    awaiting: Decimal
    satisfaction_status: str
    measured: Measured | None
    billed_measured: Measured | None


@dataclass(frozen=True, slots=True)
class VersionAt:
    """A contract version at the cut: its obligations by obligation-version id and the movement
    of the group's figures — revenue rises by ``revenue_moved − release_moved``, billing by
    ``billed_moved``; the scheduled amount falls by ``scheduled_moved`` and the awaiting-trigger
    amount by ``awaiting_moved``, which together are ``revenue_moved + returns_moved``; the RPO
    falls by ``rpo_moved`` — below zero at a cut before d_v, where revenue is given back and an
    obligation satisfied only later is in again — and the transaction price by
    ``returns_moved``."""

    obligations: Mapping[UUID, ObligationAt]
    revenue_moved: Decimal
    billed_moved: Decimal
    rpo_moved: Decimal
    returns_moved: Decimal
    release_moved: Decimal
    scheduled_moved: Decimal
    awaiting_moved: Decimal


@dataclass(frozen=True, slots=True)
class BalanceAt:
    """The balances of one member contract and entity at the cut: ``values`` per T-CON-09 balance
    name and ``net_position``, billed less revenue (D-12); ``latest`` when the cut is the version's
    latest period (the stored functional amounts then hold)."""

    values: Mapping[str, Decimal]
    net_position: Decimal
    latest: bool
    measured: Measured | None


def remainder_at(
    row: Mapping[str, Any],
    moved: Decimal,
    named: _Named,
    day: date,
    pattern: tuple[str, str] | None,
) -> tuple[Decimal, Decimal]:
    """The scheduled and the awaiting-trigger amount of an obligation at the cut (04 API-C-10 rev
    1.174, 1.178 and 1.179; items CTR-TODATE-AWAITING-1, RPT-ASOF-FIGURES-1 and
    ENG-USAGE-FIXED-SCHEDULE-1; supervisor ruling R-118 (a)): its remainder at d_v, less ``moved``
    — the revenue recognised since d_v and the movement of the returns reduction.

    ENGINE_SPEC_B S09-R-45 splits a remainder at d_v: what time alone still places in later
    periods is scheduled; every other part awaits a trigger, a held one included (S09-R-44).
    Between d_v and a later cut nothing but time passes, so what was recognised in between leaves
    the scheduled amount first — it is what S09-R-45 calls scheduled — and the awaiting-trigger
    amount only for what the scheduled one cannot cover: a computation recognises through its
    horizon also amounts the engine did not schedule (a transfer dated after d_v). No pattern is
    asked for that: the reader follows the split the engine stored and does not repeat its
    predicate.

    A cut before d_v gives revenue back (``moved`` below zero), and the stored columns do not say
    which part it had left. The obligation's pattern does, and ``pattern`` is the engine's own
    word for it: the (``pattern``, ``held``) parameters of the version-state ``scheduled_amount``
    node (``Nodes.patterns``). The revenue returns to the scheduled amount when the node says
    ``DETERMINISTIC`` and not held, to the awaiting-trigger amount otherwise — an event-driven
    remainder, a held one, and a time-elapsed obligation the engine does not call scheduled at d_v
    (its contract is not a contract in the book, its custodial term has not begun). ``Unreadable``
    when revenue is given back and the trace holds no such node of the obligation.

    The two stay the remainder (04 DB-17) and neither is negative; ``Unreadable`` when the
    remainder itself is below zero.
    """
    scheduled, awaiting = Decimal(row[SCHEDULED]), Decimal(row[AWAITING])
    if moved == 0:
        return scheduled, awaiting
    if moved > 0:
        scheduled -= moved
        if scheduled < 0:
            scheduled, awaiting = ZERO, awaiting + scheduled
    elif pattern is None:
        message = PATTERN_UNTRACED.format(day=day, **named.facts())
        raise Unreadable(f"obligations[{named.obligation}].{SCHEDULED}", message)
    elif pattern == DETERMINISTIC:
        scheduled -= moved
    else:
        awaiting -= moved
    if scheduled < 0 or awaiting < 0:
        message = REMAINDER_NEGATIVE.format(
            contract=named.contract,
            obligation=named.obligation,
            day=day,
            version_no=named.version_no,
            scheduled=scheduled,
            awaiting=awaiting,
            effective_date=named.effective_date,
        )
        raise Unreadable(f"obligations[{named.obligation}].{SCHEDULED}", message)
    return scheduled, awaiting


def version_at(
    version: Mapping[str, Any],
    obligations: Sequence[Mapping[str, Any]],
    *,
    nodes: Nodes,
    external_ids: Mapping[UUID, str],
    as_of: date,
) -> VersionAt:
    """The version's obligations at the cut of ``as_of`` and the movement of the group's figures.

    ``obligations`` are every ``obligation_version`` row of the version (the group's, since the
    version's figures are the group's); ``external_ids`` the external id of each member contract
    the caller sees. ``Unreadable`` when the trace cannot answer a measure.
    """
    found: dict[UUID, ObligationAt] = {}
    revenue_moved = billed_moved = rpo_moved = returns_moved = ZERO
    scheduled_moved = awaiting_moved = ZERO
    for row in obligations:
        external_id = external_ids.get(UUID(str(row["contract_id"])))
        subject = _subject(row, external_id)
        stored = row["satisfaction_status"]
        status = at_version = str(getattr(stored, "value", stored))
        if _unmeasured(nodes, subject, row):
            found[UUID(str(row["id"]))] = ObligationAt(
                revenue=ZERO,
                billed=ZERO,
                progress_ratio=ZERO,
                delta=ZERO,
                billed_delta=ZERO,
                shift=ZERO,
                scheduled=Decimal(row[SCHEDULED]),
                awaiting=Decimal(row[AWAITING]),
                satisfaction_status=status,
                measured=None,
                billed_measured=None,
            )
            continue
        if subject is None:
            field = f"obligations[{row['obligation_key']}].{REVENUE}"
            message = UNBOUND.format(
                obligation=row["obligation_key"], version_no=version["version_no"], day=as_of
            )
            raise Unreadable(field, message)
        named = _Named(
            contract=external_id or subject.partition("/")[0],
            obligation=str(row["obligation_key"]),
            version_no=version["version_no"],
            effective_date=row["effective_date"],
        )
        day = min(as_of, _horizon(nodes, subject, named))
        revenue, revenue_at = _read(nodes, REVENUE, subject, day, named, stored=row["revenue_cum"])
        billed, billed_at = _read(nodes, BILLED, subject, day, named, stored=row["billed_cum"])
        progress, _ = _read(nodes, PROGRESS, subject, day, named, stored=row["progress_ratio"])
        delta = revenue - Decimal(row["revenue_cum"])
        billed_delta = billed - Decimal(row["billed_cum"])
        shift = _returns_shift(nodes, subject, revenue_at, str(row["txn_currency"]).strip())
        recognised = _measures(nodes, REVENUE, subject)
        if recognised:  # an obligation the engine measures no revenue for keeps its status
            status = _status(status, revenue, progress)
        pattern = nodes.patterns.get(subject)
        scheduled, awaiting = remainder_at(row, delta + shift, named, day, pattern)
        found[UUID(str(row["id"]))] = ObligationAt(
            revenue=revenue,
            billed=billed,
            progress_ratio=progress,
            delta=delta,
            billed_delta=billed_delta,
            shift=shift,
            scheduled=scheduled,
            awaiting=awaiting,
            satisfaction_status=status,
            measured=_measured(revenue_at),
            billed_measured=_measured(billed_at),
        )
        revenue_moved += delta
        billed_moved += billed_delta
        returns_moved += shift
        scheduled_moved += Decimal(row[SCHEDULED]) - scheduled
        awaiting_moved += Decimal(row[AWAITING]) - awaiting
        # 04 T-CON-08 ``rpo_amount``: the obligations stage 15 included keep their inclusion; one
        # that is satisfied at the cut leaves the gross RPO, the others fall by Δ and by the
        # movement of the returns reduction (ENGINE_SPEC_B S15-R-12, basis).
        state = nodes.states.get(f"{RPO}:{subject}")
        if recognised and state is not None and state[1] == "true":
            before = Decimal(state[0])
            after = before - delta - shift if status in RPO_STATUSES else ZERO
            rpo_moved += before - after
        elif (
            recognised
            and state is not None
            and state[2] is None
            and at_version == SATISFIED
            and status in RPO_STATUSES
        ):
            # Rev 1.213 (supervisor ruling R-121 (g)): the remainder AT THE CUT decides. Stage
            # 15 left this obligation out at d_v because it was satisfied by then — and for no
            # other reason: its node carries no ``excluded`` — and at a cut before that it has a
            # remainder, which the RPO report states at that date (S15-R-08). It enters with it.
            rpo_moved -= scheduled + awaiting
    release_moved = ZERO
    if obligations:
        d_v = max(row["effective_date"] for row in obligations)
        release_moved = _release_moved(nodes, version, d_v, as_of)
    return VersionAt(
        obligations=found,
        revenue_moved=revenue_moved,
        billed_moved=billed_moved,
        rpo_moved=rpo_moved,
        returns_moved=returns_moved,
        release_moved=release_moved,
        scheduled_moved=scheduled_moved,
        awaiting_moved=awaiting_moved,
    )


def _member(
    nodes: Nodes,
    *,
    subject: str,
    external_id: str,
    entity_code: str,
    version: Mapping[str, Any],
    as_of: date,
) -> Point | None:
    """The period of a member subject the cut of ``as_of`` falls in (its last one when ``as_of``
    lies beyond it); None before its first period. The subject has dated periods."""
    periods = nodes.members[subject]
    day = min(as_of, periods[-1].end)
    try:
        return _locate(periods, day, nodes.starts)
    except _Unplaced as unplaced:
        message = MEMBER_UNPLACED.format(
            contract=external_id,
            entity=entity_code,
            day=day,
            period=unplaced.first.key,
            version_no=version["version_no"],
            starts=unplaced.starts(),
        )
        raise Unreadable(f"balances[{subject}]", message) from None


def _traced(nodes: Nodes, subject: str) -> bool:
    return bool(nodes.members.get(subject)) and subject not in nodes.undated


def net_moved(
    obligations: Sequence[Mapping[str, Any]],
    at: Mapping[UUID, ObligationAt],
    row: Mapping[str, Any],
) -> Decimal:
    """The movement of a balance row's net position between d_v and the cut: the billing less the
    revenue, since d_v, of the obligations the row summarises — those of its contract whose
    contracting entity is the row's (04 T-CON-09 ``entity_id``; ENGINE_SPEC_B S10-R-12)."""
    moved = ZERO
    for item in obligations:
        if (item["contract_id"], item["contracting_entity_id"]) != (
            row["contract_id"],
            row["entity_id"],
        ):
            continue
        found = at[UUID(str(item["id"]))]
        moved += found.billed_delta - found.delta
    return moved


def balance_at(
    row: Mapping[str, Any],
    *,
    version: Mapping[str, Any],
    nodes: Nodes,
    external_id: str,
    moved: Decimal,
    as_of: date,
) -> BalanceAt:
    """The balances of one ``contract_version_balance`` row at the cut of ``as_of``.

    The labelled balances are read from the member-balance nodes of the cut's period
    (``tie_outs.BalanceUnreadable``, S15-R-07a, when the trace cannot answer one). The net
    position of the row is billed less revenue of its obligations at d_v (04 T-CON-09
    ``net_position_txn``; D-12), beside balances of the version's latest period; ``moved``
    (``net_moved``) brings it to the cut.
    """
    code = str(row["entity_code"])
    subject = contract_entity_subject_key(external_id, code)

    def balances(period_key: str) -> dict[str, Decimal]:
        return tie_outs.period_balances(
            nodes.balances,
            external_id=external_id,
            entity_code=code,
            period_key=period_key,
            stored=row,
            version_id=version["id"],
        )

    if not _traced(nodes, subject):
        balances("")  # an untraced subject: the S15-R-07a reader names it, whatever the period
        raise Unreadable(
            f"balances[{subject}]",
            HORIZON_UNTRACED.format(contract=external_id, version_no=version["version_no"]),
        )
    point = _member(
        nodes,
        subject=subject,
        external_id=external_id,
        entity_code=code,
        version=version,
        as_of=as_of,
    )
    if point is None:
        # ``as_of`` precedes the first period the version measures: nothing was measured yet
        zero = dict.fromkeys(tie_outs.BALANCE_MEASURES, ZERO)
        return BalanceAt(zero, ZERO, latest=False, measured=None)
    return BalanceAt(
        values=balances(point.key),
        net_position=Decimal(row["net_position_txn"]) + moved,
        latest=point.key == nodes.balances.latest.get(subject),
        measured=_measured(point),
    )


def measured_at(
    version: Mapping[str, Any],
    *,
    nodes: Nodes,
    external_id: str,
    entity_code: str,
    as_of: date,
) -> Measured | None:
    """The period the to-date measures of a contract are read at in the periods of its contracting
    entity (API-S-Context ``measured_period``): None when the version measures no balance of the
    contract in that entity, or ``as_of`` precedes the first period it measures."""
    subject = contract_entity_subject_key(external_id, entity_code)
    if not _traced(nodes, subject):
        return None
    return _measured(
        _member(
            nodes,
            subject=subject,
            external_id=external_id,
            entity_code=entity_code,
            version=version,
            as_of=as_of,
        )
    )
