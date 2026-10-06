"""Explain service (dev-guide §5.16 DG-KRN-EXP-01 to DG-KRN-EXP-06; 04 §16.11 API-S-Explain, §16.14
API-S-CalcTrace, T-ENG-03; 05 RCP-24 to RCP-27; 03 REQ-RPT-017, REQ-RPT-018; BUILD_SPEC PLF-20,
CTR-19).

``build_explain`` walks an in-memory ``Trace`` from one node through its node-id inputs, level by
level, to at most ``depth`` levels below the node (default 6, maximum 20), and renders one sentence
per returned node from ``NARRATIVES``. The value is the node's stored string, never recomputed or
reformatted.

``explain_measure`` explains a persisted figure in the caller's read-only tenant session, so
row-level security scopes every read and an object outside the caller's entities answers 404 exactly
as a missing one (REQ-PLT-012). A figure resolves to one contract version, its stored ``calc_trace``
(checked against ``trace_sha256``) and one node:

- ``schedule_line`` (measure ``amount``): the line's ``trace_node_id``.
- ``subledger_line`` (measure ``amount``): the line's ``trace_node_id``. When that names a
  ``posting_target`` node, the one ``posting_delta`` node that cites it and holds the line amount
  ([J] L4-4-Q-12).
- ``obligation_version``: ``trace_nodes[measure]``, or ``<measure>:<subject key>:<period>`` with
  ``period``; ``revenue`` with ``period`` is the single ``revenue_by_cause`` node of the period.
- ``obligation``: the obligation version of the contract version recorded by ``known_at`` in
  ``book`` (default the primary book), then as ``obligation_version``.
- ``contract_version``: ``<measure>:<group code>:<period or '-'>``.
- ``contract_version_balance``: ``<measure>:<contract external id>@<entity code>:<period>``, the
  latest period when ``period`` is absent.
- ``journal_line``: 404 while no journal line exists ([J] L4-4-Q-13).

Measure names are node measures; the SCREENS §6.3 labels ``revenue_to_date``, ``billed_to_date``,
``scheduled``, ``awaiting_trigger`` and ``selected_ssp`` name ``revenue_cum``, ``billed_cum``,
``scheduled_amount``, ``awaiting_trigger_amount`` and ``original_ssp_selected``.

``value`` is the stored column when the object stores the figure, else the node's value: Money for a
node with a currency, otherwise a decimal string. ``history`` lists, newest first, the contract
versions of the group and book up to the explained one in which the node's value changed.
``verify_measure`` recomputes the trace with ``erev_engine.trace.reevaluate`` (DG-KRN-EXP-04) and
writes nothing. ``calc_trace_out`` answers API-S-CalcTrace.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from erev_engine.currencies import ISO_4217
from erev_engine.money import format_exact
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key, obligation_subject_key
from erev_engine.trace import (
    SourceRef,
    Trace,
    TraceNode,
    absence_state,
    exact_companion_failures,
    reevaluate,
)
from sqlalchemy import Select, and_, func, literal, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.dialects.postgresql import JSONB, JSONPATH
from sqlalchemy.orm import Session

from erev_api.clock import to_entity_date
from erev_api.db.tables import (
    book,
    calc_trace,
    combination_group,
    combination_group_member,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    contract_version_balance,
    legal_entity,
    obligation,
    obligation_version,
    period,
    schedule_line,
    subledger_line,
)
from erev_api.enums import BookCode
from erev_api.explain import store
from erev_api.explain.narratives import render
from erev_api.money import money_out
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.common import ContextOut, MeasuredPeriodOut, MoneyOut
from erev_api.schemas.explain import (
    CalcTraceOut,
    EstimateVersionPairOut,
    ExplainDrillOut,
    ExplainHistoryItemOut,
    ExplainNodeInputOut,
    ExplainNodeOut,
    ExplainObjectOut,
    ExplainObjectType,
    ExplainOut,
    ExplainSourceInputOut,
    ExplainVerifyOut,
)

__all__ = [
    "DEFAULT_DEPTH",
    "MAX_DEPTH",
    "MEASURE_ALIASES",
    "ExplainNode",
    "Explanation",
    "NodeInput",
    "SourceInput",
    "build_explain",
    "calc_trace_out",
    "explain_measure",
    "verify_measure",
]

DEFAULT_DEPTH: Final = 6
MAX_DEPTH: Final = 20
DEPTH_FIELD: Final = "depth"
DEPTH_MESSAGE: Final = f"Enter a depth from 0 to {MAX_DEPTH}."
UNKNOWN_NODE: Final = "The calculation trace holds no figure with this id."
NOT_TRACED: Final = "The calculation trace holds no node for this figure."
API: Final = "/api/v1"
LINE_MEASURE: Final = "amount"
REVENUE: Final = "revenue"
REVENUE_BY_CAUSE: Final = "revenue_by_cause"
POSTING_TARGET: Final = "posting_target"
POSTING_DELTA: Final = "posting_delta"
RECOMPUTE: Final = "RECOMPUTE"
EVENT_REF: Final = "contract_event"
EVENT_KEY: Final = "/EV-"
NODE_PATH: Final = "$.nodes[*] ? (@.id == $id)"
MEASURE_ALIASES: Final[Mapping[str, str]] = MappingProxyType(
    {
        "revenue_to_date": "revenue_cum",
        "billed_to_date": "billed_cum",
        "scheduled": "scheduled_amount",
        "awaiting_trigger": "awaiting_trigger_amount",
        "selected_ssp": "original_ssp_selected",
    }
)


@dataclass(frozen=True, slots=True)
class NodeInput:
    node_id: str


@dataclass(frozen=True, slots=True)
class SourceInput:
    """A source reference; ``href`` is filled by the routes that know the source's screen."""

    ref_type: str
    ref_id: str
    label: str
    href: str | None = None


@dataclass(frozen=True, slots=True)
class ExplainNode:
    id: str
    measure: str
    value: str
    currency: str | None
    formula_id: str
    params: Mapping[str, str]
    rounding_residue: str | None
    inputs: tuple[NodeInput | SourceInput, ...]


@dataclass(frozen=True, slots=True)
class Explanation:
    engine_version: str
    root_node_id: str
    measure: str
    value: str
    currency: str | None
    nodes: tuple[ExplainNode, ...]
    narrative: tuple[str, ...]


def _explain_input(item: str | SourceRef) -> NodeInput | SourceInput:
    if isinstance(item, str):
        return NodeInput(node_id=item)
    label = item.detail.get("label", f"{item.ref_type} {item.ref_id}")
    return SourceInput(ref_type=item.ref_type, ref_id=item.ref_id, label=label)


def _explain_node(node: TraceNode) -> ExplainNode:
    return ExplainNode(
        id=node.id,
        measure=node.measure,
        value=node.value,
        currency=node.currency,
        formula_id=node.formula_id,
        params=node.params,
        rounding_residue=node.rounding_residue,
        inputs=tuple(_explain_input(item) for item in node.inputs),
    )


def _levels(nodes: Mapping[str, TraceNode], root: TraceNode, depth: int) -> list[TraceNode]:
    """The root and its inputs breadth first, each node once at its shallowest level."""
    ordered, seen, frontier = [root], {root.id}, [root]
    for _ in range(depth):
        following: list[TraceNode] = []
        for current in frontier:
            for item in current.inputs:
                if not isinstance(item, str) or item in seen:
                    continue
                child = nodes.get(item)
                if child is None:
                    raise ValueError(f"node {current.id!r} names an unknown input {item!r}")
                seen.add(item)
                ordered.append(child)
                following.append(child)
        if not following:
            break
        frontier = following
    return ordered


def _check_depth(depth: int) -> None:
    if isinstance(depth, bool) or not isinstance(depth, int) or not 0 <= depth <= MAX_DEPTH:
        raise Problem(
            "validation-failed",
            errors=[
                ProblemError(field=DEPTH_FIELD, rule_id="DG-KRN-EXP-06", message=DEPTH_MESSAGE)
            ],
        )


def build_explain(trace: Trace, node_id: str, depth: int = DEFAULT_DEPTH) -> Explanation:
    """Explain one node: 404 ``not-found`` for an unknown id, 422 on ``depth`` outside 0 to 20."""
    _check_depth(depth)
    nodes = {node.id: node for node in trace.nodes}
    root = nodes.get(node_id)
    if root is None:
        raise Problem("not-found", UNKNOWN_NODE)
    returned = _levels(nodes, root, depth)
    narrative = tuple(
        render(node, {item: nodes[item] for item in node.inputs if isinstance(item, str)})
        for node in returned
    )
    return Explanation(
        engine_version=trace.engine_version,
        root_node_id=root.id,
        measure=root.measure,
        value=root.value,
        currency=root.currency,
        nodes=tuple(_explain_node(node) for node in returned),
        narrative=narrative,
    )


# --- persisted figures ----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Figure:
    """A figure resolved to its contract version, stored trace and node."""

    object_type: ExplainObjectType
    object_id: UUID
    measure: str
    period_key: str | None
    version: Mapping[str, Any]
    trace_id: UUID
    trace: Trace
    node: TraceNode
    stored: Decimal | None  # the object's stored column; None when the trace holds the figure only
    currency: str | None
    entity_id: UUID | None
    contract_id: UUID | None
    obligation_id: UUID | None


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _text(value: Any) -> str:
    return value.value if isinstance(value, Enum) else str(value)


def _one(session: Session, statement: Select[Any], detail: str | None = None) -> dict[str, Any]:
    found = session.execute(statement).mappings().one_or_none()
    if found is None:
        raise Problem("not-found", detail)
    return dict(found)


def _version(session: Session, version_id: Any) -> dict[str, Any]:
    return _one(session, select(contract_version).where(contract_version.c.id == version_id))


def _trace(session: Session, trace_id: UUID) -> tuple[dict[str, Any], Trace]:
    row = _one(session, select(calc_trace).where(calc_trace.c.id == trace_id))
    return row, store.trace_from_row(row)


def _linked_node_id(column: str, found: object, stored: Decimal | None) -> str | None:
    """The node id a row's ``trace_nodes`` entry binds for ``column`` (None when unbound), read
    through the ONE shared recognition ``erev_engine.trace.absence_state`` (column AND stored
    value; no explain-local prefix test): the absence admitted for the column over the contract
    display 0 binds no node BY CONTRACT — the not-traced problem names it; an unknown or swapped
    reason, a marker on a REQUIRED producer's column, or an admitted reason over a non-zero /
    NULL value is a MALFORMED stored state (the assembler refuses it) — a validation problem, never
    read as a legitimate absence (CV-50 rev 1.29). Anything else is a node id that resolves, or
    not, against the trace."""
    state = absence_state(column, found, stored)
    if state == "absent":
        raise Problem("not-found", f"{NOT_TRACED} {found}")
    if state == "malformed":
        message = (
            f"The stored link {found!r} is not the contract-permitted absence admitted for "
            f"{column} over the stored value {stored!r}."
        )
        raise Problem(
            "validation-failed",
            errors=[ProblemError(field=column, rule_id="CV-50", message=message)],
        )
    return found if isinstance(found, str) else None


def _node(trace: Trace, node_id: str | None) -> TraceNode:
    found = None
    if node_id is not None:
        found = next((node for node in trace.nodes if node.id == node_id), None)
    if found is None:
        raise Problem("not-found", NOT_TRACED)
    return found


def _contract(session: Session, contract_id: Any) -> dict[str, Any]:
    """The contract when the caller's entity scope shows it (RLS-TE), else 404."""
    return _one(session, select(contract).where(contract.c.id == contract_id))


def _members(session: Session, group_id: Any) -> list[dict[str, Any]]:
    """The member contracts of a group, current or past, that the caller's scope shows."""
    member_ids = select(combination_group_member.c.contract_id).where(
        combination_group_member.c.combination_group_id == group_id
    )
    statement = (
        select(contract.c.id, contract.c.external_id, contract.c.contracting_entity_id)
        .where(or_(contract.c.combination_group_id == group_id, contract.c.id.in_(member_ids)))
        .order_by(contract.c.external_id)
    )
    return [dict(row) for row in session.execute(statement).mappings()]


def _stored(table: Any, row: Mapping[str, Any], name: str) -> Decimal | None:
    if name not in table.c:
        return None
    value = row.get(name)
    return Decimal(value) if isinstance(value, Decimal | int) else None


def _figure(
    figure_type: ExplainObjectType,
    object_id: UUID,
    measure: str,
    *,
    period_key: str | None,
    version: Mapping[str, Any],
    trace_id: UUID,
    trace: Trace,
    node: TraceNode,
    stored: Decimal | None,
    currency: str | None,
    entity_id: Any,
    contract_id: Any,
    obligation_id: Any,
) -> _Figure:
    return _Figure(
        object_type=figure_type,
        object_id=object_id,
        measure=measure,
        period_key=period_key,
        version=version,
        trace_id=trace_id,
        trace=trace,
        node=node,
        stored=stored,
        currency=None if currency is None else str(currency).strip(),
        entity_id=None if entity_id is None else _uuid(entity_id),
        contract_id=None if contract_id is None else _uuid(contract_id),
        obligation_id=None if obligation_id is None else _uuid(obligation_id),
    )


def _schedule_line(session: Session, object_id: UUID, measure: str) -> _Figure:
    statement = (
        select(schedule_line, period.c.period_key)
        .select_from(
            schedule_line.join(
                period,
                and_(
                    period.c.tenant_id == schedule_line.c.tenant_id,
                    period.c.id == schedule_line.c.period_id,
                ),
            )
        )
        .where(schedule_line.c.id == object_id)
    )
    row = _one(session, statement)
    if measure != LINE_MEASURE:
        raise Problem("not-found", f"A schedule line explains only {LINE_MEASURE}.")
    version = _version(session, row["contract_version_id"])
    trace_id = _uuid(version["calc_trace_id"])
    _, trace = _trace(session, trace_id)
    return _figure(
        "schedule_line",
        object_id,
        measure,
        period_key=str(row["period_key"]),
        version=version,
        trace_id=trace_id,
        trace=trace,
        node=_node(trace, row["trace_node_id"]),
        stored=Decimal(row["amount"]),
        currency=row["currency"],
        entity_id=row["entity_id"],
        contract_id=row["contract_id"],
        obligation_id=row["subject_id"] if row["subject_type"] == "obligation" else None,
    )


def _posted(trace: Trace, node: TraceNode, amount: Decimal) -> TraceNode:
    """The ``posting_delta`` node behind a line that names its ``posting_target`` node."""
    if node.measure != POSTING_TARGET:
        return node
    deltas = [
        candidate
        for candidate in trace.nodes
        if candidate.measure == POSTING_DELTA
        and candidate.inputs
        and candidate.inputs[0] == node.id
        and Decimal(candidate.value) == amount
    ]
    return deltas[0] if len(deltas) == 1 else node


def _subledger_line(session: Session, object_id: UUID, measure: str) -> _Figure:
    statement = (
        select(subledger_line, period.c.period_key)
        .select_from(
            subledger_line.join(
                period,
                and_(
                    period.c.tenant_id == subledger_line.c.tenant_id,
                    period.c.id == subledger_line.c.period_id,
                ),
            )
        )
        .where(subledger_line.c.id == object_id)
    )
    row = _one(session, statement)
    if measure != LINE_MEASURE:
        raise Problem("not-found", f"A subledger line explains only {LINE_MEASURE}.")
    if row["calc_trace_id"] is None:
        raise Problem("not-found", "The subledger line has no calculation trace.")
    trace_id = _uuid(row["calc_trace_id"])
    trace_row, trace = _trace(session, trace_id)
    version = _version(session, row["contract_version_id"] or trace_row["contract_version_id"])
    amount = Decimal(row["amount_txn"])
    return _figure(
        "subledger_line",
        object_id,
        measure,
        period_key=str(row["period_key"]),
        version=version,
        trace_id=trace_id,
        trace=trace,
        node=_posted(trace, _node(trace, row["trace_node_id"]), amount),
        stored=amount,
        currency=row["txn_currency"],
        entity_id=row["entity_id"],
        contract_id=row["contract_id"],
        obligation_id=row["obligation_id"],
    )


def _subject(
    nodes: Mapping[str, Any], contract_row: Mapping[str, Any], row: Mapping[str, Any]
) -> str:
    """The obligation's subject key: the middle part of its ``revenue_cum`` node id, else the
    engine's own key of the contract and obligation (CV-21; never a join of the raw ids)."""
    anchor = nodes.get("revenue_cum")
    if isinstance(anchor, str) and anchor.count(":") >= 2:
        return anchor.split(":", 1)[1].rsplit(":", 1)[0]
    return obligation_subject_key(str(contract_row["external_id"]), str(row["obligation_key"]))


def _single_cause(trace: Trace, subject: str, period_key: str) -> TraceNode:
    prefix, suffix = f"{REVENUE_BY_CAUSE}:{subject}/", f":{period_key}"
    causes = [
        node for node in trace.nodes if node.id.startswith(prefix) and node.id.endswith(suffix)
    ]
    if not causes:
        raise Problem("not-found", NOT_TRACED)
    if len(causes) > 1:
        message = f"Revenue for {period_key} has {len(causes)} causes; explain each schedule line."
        raise Problem(
            "validation-failed",
            errors=[ProblemError(field="measure", rule_id="DG-KRN-EXP-06", message=message)],
        )
    return causes[0]


def _obligation_version(
    session: Session,
    object_id: UUID,
    measure: str,
    period_key: str | None,
    *,
    figure_type: ExplainObjectType = "obligation_version",
    row: Mapping[str, Any] | None = None,
) -> _Figure:
    if row is None:
        row = _one(session, select(obligation_version).where(obligation_version.c.id == object_id))
    contract_row = _contract(session, row["contract_id"])
    version = _version(session, row["contract_version_id"])
    trace_id = _uuid(version["calc_trace_id"])
    _, trace = _trace(session, trace_id)
    name = MEASURE_ALIASES.get(measure, measure)
    nodes: Mapping[str, Any] = row["trace_nodes"] or {}
    stored: Decimal | None = None
    if period_key is None:
        stored = _stored(obligation_version, row, name)  # read BEFORE the link is classified
        node = _node(trace, _linked_node_id(name, nodes.get(name), stored))
    elif name == REVENUE:
        node = _single_cause(trace, _subject(nodes, contract_row, row), period_key)
    else:
        node = _node(trace, f"{name}:{_subject(nodes, contract_row, row)}:{period_key}")
    return _figure(
        figure_type,
        object_id,
        measure,
        period_key=period_key,
        version=version,
        trace_id=trace_id,
        trace=trace,
        node=node,
        stored=stored,
        currency=node.currency,
        entity_id=contract_row["contracting_entity_id"],
        contract_id=row["contract_id"],
        obligation_id=row["obligation_id"],
    )


def _primary_book(session: Session) -> str:
    found = session.execute(select(book.c.code).where(book.c.is_primary.is_(True))).scalar()
    return BookCode.ASC606.value if found is None else _text(found)


def _group_at(session: Session, contract_row: Mapping[str, Any], known_at: datetime | None) -> Any:
    """The contract's combination group at ``known_at`` (T-CON-04), else its current group."""
    if known_at is None:
        return contract_row["combination_group_id"]
    member = combination_group_member
    statement = (
        select(member.c.combination_group_id)
        .where(
            member.c.contract_id == contract_row["id"],
            member.c.valid_from_known_at <= known_at,
            or_(member.c.valid_to_known_at.is_(None), member.c.valid_to_known_at > known_at),
        )
        .order_by(member.c.valid_from_known_at.desc())
        .limit(1)
    )
    found = session.execute(statement).scalar()
    return contract_row["combination_group_id"] if found is None else found


def _obligation(
    session: Session,
    object_id: UUID,
    measure: str,
    period_key: str | None,
    *,
    book_code: str | None,
    known_at: datetime | None,
) -> _Figure:
    found = _one(session, select(obligation).where(obligation.c.id == object_id))
    contract_row = _contract(session, found["contract_id"])
    book_value = book_code or _primary_book(session)
    statement = select(contract_version.c.id).where(
        contract_version.c.combination_group_id == _group_at(session, contract_row, known_at),
        contract_version.c.book_code == book_value,
    )
    if known_at is not None:
        statement = statement.where(contract_version.c.known_at <= known_at)
    version_id = session.execute(
        statement.order_by(contract_version.c.version_no.desc()).limit(1)
    ).scalar()
    if version_id is None:
        raise Problem("not-found", f"The contract has no computed version in {book_value}.")
    row = _one(
        session,
        select(obligation_version).where(
            obligation_version.c.contract_version_id == version_id,
            obligation_version.c.obligation_id == object_id,
        ),
    )
    return _obligation_version(
        session, object_id, measure, period_key, figure_type="obligation", row=row
    )


def _contract_version(
    session: Session, object_id: UUID, measure: str, period_key: str | None
) -> _Figure:
    version = _version(session, object_id)
    members = _members(session, version["combination_group_id"])
    if not members:
        raise Problem("not-found")
    code = session.execute(
        select(combination_group.c.code).where(
            combination_group.c.id == version["combination_group_id"]
        )
    ).scalar_one()
    trace_id = _uuid(version["calc_trace_id"])
    _, trace = _trace(session, trace_id)
    name = MEASURE_ALIASES.get(measure, measure)
    node = _node(trace, f"{name}:{code}:{period_key or '-'}")
    return _figure(
        "contract_version",
        object_id,
        measure,
        period_key=period_key,
        version=version,
        trace_id=trace_id,
        trace=trace,
        node=node,
        stored=None if period_key is not None else _stored(contract_version, version, name),
        currency=node.currency,
        entity_id=members[0]["contracting_entity_id"],
        contract_id=members[0]["id"] if len(members) == 1 else None,
        obligation_id=None,
    )


def _balance(session: Session, object_id: UUID, measure: str, period_key: str | None) -> _Figure:
    statement = (
        select(contract_version_balance, legal_entity.c.code.label("entity_code"))
        .select_from(
            contract_version_balance.join(
                legal_entity,
                and_(
                    legal_entity.c.tenant_id == contract_version_balance.c.tenant_id,
                    legal_entity.c.id == contract_version_balance.c.entity_id,
                ),
            )
        )
        .where(contract_version_balance.c.id == object_id)
    )
    row = _one(session, statement)
    contract_row = _contract(session, row["contract_id"])
    version = _version(session, row["contract_version_id"])
    trace_id = _uuid(version["calc_trace_id"])
    _, trace = _trace(session, trace_id)
    column = f"{measure}_txn"
    if column not in contract_version_balance.c:
        raise Problem("not-found", NOT_TRACED)
    # The member's balance nodes sit under the engine's subject key — the external id and the
    # entity code each CV-21-encoded (ENGINE_SPEC_B S15-R-07a); a prefix joined from the raw ids
    # found no node for an identifier holding ``%`` ``/`` ``@`` ``#`` ``:`` (R-16).
    subject = contract_entity_subject_key(str(contract_row["external_id"]), str(row["entity_code"]))
    prefix = f"{measure}:{subject}:"
    stored: Decimal | None = None
    if period_key is None:
        periods = [node for node in trace.nodes if node.id.startswith(prefix)]
        node = _node(trace, periods[-1].id if periods else None)  # ids sort by period key
        stored = Decimal(row[column])
    else:
        node = _node(trace, prefix + period_key)
    return _figure(
        "contract_version_balance",
        object_id,
        measure,
        period_key=node.id.rsplit(":", 1)[1],
        version=version,
        trace_id=trace_id,
        trace=trace,
        node=node,
        stored=stored,
        currency=row["txn_currency"],
        entity_id=row["entity_id"],
        contract_id=row["contract_id"],
        obligation_id=None,
    )


def _resolve(
    session: Session,
    *,
    object_type: ExplainObjectType,
    object_id: UUID,
    measure: str,
    book_code: str | None,
    known_at: datetime | None,
    period_key: str | None,
) -> _Figure:
    if object_type == "schedule_line":
        return _schedule_line(session, object_id, measure)
    if object_type == "subledger_line":
        return _subledger_line(session, object_id, measure)
    if object_type == "obligation_version":
        return _obligation_version(session, object_id, measure, period_key)
    if object_type == "obligation":
        return _obligation(
            session, object_id, measure, period_key, book_code=book_code, known_at=known_at
        )
    if object_type == "contract_version":
        return _contract_version(session, object_id, measure, period_key)
    if object_type == "contract_version_balance":
        return _balance(session, object_id, measure, period_key)
    # journal_line: the journal tables arrive with the journals phase ([J] L4-4-Q-13).
    raise Problem("not-found")


# --- response parts -------------------------------------------------------------------------------


def _value(figure: _Figure) -> MoneyOut | str:
    if figure.currency is not None:
        amount = figure.stored if figure.stored is not None else Decimal(figure.node.value)
        return money_out(amount, figure.currency, ISO_4217)
    if figure.stored is not None:
        return format_exact(figure.stored)
    return figure.node.value


def _stored_text(figure: _Figure) -> str:
    value = _value(figure)
    return value.amount if isinstance(value, MoneyOut) else value


def _event_hrefs(session: Session, nodes: Iterable[ExplainNode]) -> dict[str, str]:
    """``/api/v1/events/{id}`` of the ``contract_event`` references ``<external id>/EV-<n>``."""
    wanted: dict[tuple[str, int], str] = {}
    for node in nodes:
        for item in node.inputs:
            if not isinstance(item, SourceInput) or item.ref_type != EVENT_REF:
                continue
            external_id, separator, number = item.ref_id.rpartition(EVENT_KEY)
            if separator and number.isdigit():
                wanted[(external_id, int(number))] = item.ref_id
    if not wanted:
        return {}
    statement = (
        select(contract.c.external_id, contract_event.c.stream_version, contract_event.c.id)
        .select_from(
            contract_event.join(
                contract,
                and_(
                    contract.c.tenant_id == contract_event.c.tenant_id,
                    contract.c.id == contract_event.c.contract_id,
                ),
            )
        )
        .where(contract.c.external_id.in_(sorted({external for external, _ in wanted})))
    )
    hrefs: dict[str, str] = {}
    for found in session.execute(statement):
        ref_id = wanted.get((str(found.external_id), int(found.stream_version)))
        if ref_id is not None:
            hrefs[ref_id] = f"{API}/events/{found.id}"
    return hrefs


def _node_out(node: ExplainNode, event_hrefs: Mapping[str, str]) -> ExplainNodeOut:
    inputs: list[ExplainNodeInputOut | ExplainSourceInputOut] = []
    for item in node.inputs:
        if isinstance(item, NodeInput):
            inputs.append(ExplainNodeInputOut(node_id=item.node_id))
        else:
            href = event_hrefs.get(item.ref_id) if item.ref_type == EVENT_REF else None
            inputs.append(
                ExplainSourceInputOut(
                    ref_type=item.ref_type, ref_id=item.ref_id, label=item.label, href=href
                )
            )
    return ExplainNodeOut(
        id=node.id,
        measure=node.measure,
        value=node.value,
        currency=node.currency,
        formula_id=node.formula_id,
        params=dict(node.params),
        rounding_residue=node.rounding_residue,
        inputs=inputs,
    )


def _estimate_ids(pinned_refs: Any) -> frozenset[str]:
    found = pinned_refs.get("estimate_version_ids") if isinstance(pinned_refs, Mapping) else None
    return frozenset(str(item) for item in found or ())


def _pair(before: frozenset[str], after: frozenset[str]) -> EstimateVersionPairOut | None:
    if before == after:
        return None
    removed, added = sorted(before - after), sorted(after - before)
    return EstimateVersionPairOut(
        before=removed[0] if removed else None, after=added[0] if added else None
    )


def _causes(session: Session, ids: Iterable[Any]) -> dict[UUID, tuple[int, str]]:
    wanted = sorted({_uuid(item) for item in ids})
    if not wanted:
        return {}
    statement = select(
        contract_event.c.id, contract_event.c.record_seq, contract_event.c.event_type
    ).where(contract_event.c.id.in_(wanted))
    return {
        _uuid(found.id): (int(found.record_seq), _text(found.event_type))
        for found in session.execute(statement)
    }


def _cause(ids: Sequence[Any] | None, events: Mapping[UUID, tuple[int, str]]) -> str:
    """The E-03 type of the latest causing event shown to the caller, else ``RECOMPUTE``."""
    found = [events[_uuid(item)] for item in ids or () if _uuid(item) in events]
    return max(found)[1] if found else RECOMPUTE


def _history(session: Session, figure: _Figure) -> list[ExplainHistoryItemOut]:
    node = func.jsonb_path_query_first(
        calc_trace.c.trace,
        sql_cast(literal(NODE_PATH), JSONPATH),
        func.jsonb_build_object("id", figure.node.id),
        type_=JSONB,
    )
    statement = (
        select(
            contract_version.c.id,
            contract_version.c.version_no,
            contract_version.c.known_at,
            contract_version.c.cause_event_ids,
            contract_computation.c.pinned_refs,
            node["value"].astext.label("node_value"),
        )
        .select_from(
            contract_version.join(
                calc_trace,
                and_(
                    calc_trace.c.tenant_id == contract_version.c.tenant_id,
                    calc_trace.c.id == contract_version.c.calc_trace_id,
                ),
            ).join(
                contract_computation,
                and_(
                    contract_computation.c.tenant_id == contract_version.c.tenant_id,
                    contract_computation.c.id == contract_version.c.contract_computation_id,
                ),
            )
        )
        .where(
            contract_version.c.combination_group_id == figure.version["combination_group_id"],
            contract_version.c.book_code == figure.version["book_code"],
            contract_version.c.version_no <= figure.version["version_no"],
        )
        .order_by(contract_version.c.version_no)
    )
    rows = [dict(found) for found in session.execute(statement).mappings()]
    events = _causes(session, (item for row in rows for item in row["cause_event_ids"] or ()))
    items: list[ExplainHistoryItemOut] = []
    previous_value: str | None = None
    previous_refs: frozenset[str] | None = None
    for row in rows:
        refs = _estimate_ids(row["pinned_refs"])
        value = row["node_value"]
        if value is not None and (
            previous_value is None or Decimal(value) != Decimal(previous_value)
        ):
            delta = None if previous_value is None else Decimal(value) - Decimal(previous_value)
            items.append(
                ExplainHistoryItemOut(
                    contract_version_id=row["id"],
                    version_no=row["version_no"],
                    known_at=row["known_at"],
                    value=str(value),
                    delta=None if delta is None else format(delta, "f"),
                    cause=_cause(row["cause_event_ids"], events),
                    estimate_version_pair=None
                    if previous_refs is None
                    else _pair(previous_refs, refs),
                    origin_period_key=None,
                )
            )
        if value is not None:
            previous_value = str(value)
        previous_refs = refs
    items.reverse()
    return items


def _drill(figure: _Figure) -> ExplainDrillOut:
    book_code = _text(figure.version["book_code"])
    contract_id = figure.contract_id
    if contract_id is None:
        contract_href = schedule_href = subledger_href = None
    else:
        contract_href = f"{API}/contracts/{contract_id}"
        schedule_href = f"{contract_href}/schedule?book={book_code}"
        subledger_href = f"{API}/subledger-lines?contract={contract_id}&book={book_code}" + (
            "" if figure.period_key is None else f"&period={figure.period_key}"
        )
    return ExplainDrillOut(
        contract_href=contract_href,
        obligation_href=None
        if figure.obligation_id is None
        else f"{API}/obligations/{figure.obligation_id}",
        schedule_lines_href=schedule_href,
        subledger_lines_href=subledger_href,
        source_rows=[],  # import row lineage arrives with DIN ([J] L4-4-Q-14)
    )


def _computed_at(session: Session, version: Mapping[str, Any]) -> datetime | None:
    """API-S-Context ``computed_at`` (04 rev 1.132): when the computation made the version."""
    statement = select(contract_computation.c.created_at).where(
        contract_computation.c.id == version["contract_computation_id"]
    )
    found: datetime | None = session.execute(statement).scalar()
    return found


def _as_of(session: Session, figure: _Figure, known_at: datetime) -> date:
    """API-C-10 default: the date at ``known_at`` in the figure's entity time zone."""
    if figure.entity_id is None:
        return known_at.date()
    statement = select(legal_entity.c.time_zone).where(legal_entity.c.id == figure.entity_id)
    time_zone = session.execute(statement).scalar()
    return known_at.date() if time_zone is None else to_entity_date(known_at, str(time_zone))


def explain_measure(
    session: Session,
    *,
    object_type: ExplainObjectType,
    object_id: UUID,
    measure: str,
    book_code: str | None,
    as_of: date | None,
    known_at: datetime | None,
    now: datetime,
    period_key: str | None = None,
    depth: int = DEFAULT_DEPTH,
    measured: MeasuredPeriodOut | None = None,
) -> ExplainOut:
    """API-S-Explain of one persisted figure: 404 ``not-found`` for a figure the caller cannot see
    or the trace does not hold, 422 ``validation-failed`` on ``depth``.

    ``book_code`` None takes the primary book; ``known_at`` None takes the latest version and
    ``now`` for the context; ``as_of`` None takes the date at that instant in the figure's entity
    time zone (API-C-10, API-C-11; [J] L4-4-Q-10). ``measured`` is the period a caller resolved
    ``period_key`` to for a to-date measure at the cut of ``as_of`` (04 §16.11 rev 1.132); the
    context names it.
    """
    _check_depth(depth)
    cutoff = known_at if known_at is not None else now
    figure = _resolve(
        session,
        object_type=object_type,
        object_id=object_id,
        measure=measure,
        book_code=book_code,
        known_at=known_at,
        period_key=period_key,
    )
    explanation = build_explain(figure.trace, figure.node.id, depth)
    event_hrefs = _event_hrefs(session, explanation.nodes)
    return ExplainOut(
        object=ExplainObjectOut(
            type=figure.object_type,
            id=figure.object_id,
            measure=figure.measure,
            period_key=figure.period_key,
        ),
        value=_value(figure),
        context=ContextOut(
            book=BookCode(_text(figure.version["book_code"])),
            as_of=as_of if as_of is not None else _as_of(session, figure, cutoff),
            known_at=cutoff,
            contract_version_id=figure.version["id"],
            version_no=figure.version["version_no"],
            computed_at=_computed_at(session, figure.version),
            measured_period=measured,
        ),
        calc_trace_id=figure.trace_id,
        engine_version=explanation.engine_version,
        root_node_id=explanation.root_node_id,
        nodes=[_node_out(node, event_hrefs) for node in explanation.nodes],
        narrative=list(explanation.narrative),
        history=_history(session, figure),
        drill=_drill(figure),
    )


def verify_measure(
    session: Session,
    *,
    object_type: ExplainObjectType,
    object_id: UUID,
    measure: str,
    book_code: str | None,
    known_at: datetime | None,
    period_key: str | None = None,
) -> ExplainVerifyOut:
    """Recompute the figure's node from its stored trace (DG-KRN-EXP-04); writes nothing.

    ``stored_value`` is the figure's stored number at its stored precision; ``matches`` compares the
    two exactly as decimals — and, when the node names an exact companion (ENGINE_SPEC CV-64 rev
    1.30 as amended, ``params["exact_node"]``), also requires the per-field encoding-aware
    validation against the replayed raw exact to hold (``exact_companion_failures``: the
    companion's stored value equals Q18(A_replayed), the node's ``rounding_residue`` equals
    Q18(A_replayed − P), and the companion replays to its stored value).
    """
    figure = _resolve(
        session,
        object_type=object_type,
        object_id=object_id,
        measure=measure,
        book_code=book_code,
        known_at=known_at,
        period_key=period_key,
    )
    replayed = reevaluate(figure.trace)
    recomputed = replayed[figure.node.id]
    stored = _stored_text(figure)
    companion_failures = [
        failure
        for failure in exact_companion_failures(figure.trace, replayed)
        if failure.startswith(f"{figure.node.id}:")
    ]
    return ExplainVerifyOut(
        recomputed_value=recomputed,
        stored_value=stored,
        matches=Decimal(recomputed) == Decimal(stored) and not companion_failures,
    )


def calc_trace_out(session: Session, trace_id: UUID) -> CalcTraceOut:
    """API-S-CalcTrace of a stored trace; 404 unless the caller's scope shows a member contract."""
    row = _one(session, select(calc_trace).where(calc_trace.c.id == trace_id))
    if not _members(session, row["combination_group_id"]):
        raise Problem("not-found")
    return CalcTraceOut(
        id=row["id"],
        contract_version_id=row["contract_version_id"],
        combination_group_id=row["combination_group_id"],
        book=BookCode(_text(row["book_code"])),
        format_version=int(row["format_version"]),
        engine_version=str(row["engine_version"]),
        trace_sha256=str(row["trace_sha256"]).strip(),
        node_count=int(row["node_count"]),
        root_measures={str(key): str(value) for key, value in dict(row["root_measures"]).items()},
        trace=dict(row["trace"]),
    )
