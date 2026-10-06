"""RPT-26 ``approvals_register`` Approvals register (SCREENS_B §5.6.5 RPT-26; 04 T-PLT-17,
T-PLT-18, T-PLT-20, T-REF-25, T-REF-26, E-05, E-07, E-08; PRD §2.5, J-14; 03 REQ-RPT-022,
REQ-PLT-011, REQ-PLT-013 to REQ-PLT-017; research 07 A-12; BUILD_SPEC RPS-10).

One row per approval decision of the requests submitted in ``from_date`` .. ``to_date`` (UTC days;
defaults: the first day of the context period and the run's day), and one row for a request that
has no decision yet, so every request appears. The population is the requests whose every
entity is among the run's and the tenant-level requests (``register_support.requests_in_scope``;
a request of all entities only in a run that names every entity), narrowed by ``subject_types``
(E-08) and ``status`` (E-05) when given. Rows are ordered by request number, step and decision;
``row_key``
``decision:<request no>:<step no>:<sequence>`` — the sequence counts the decisions of a step from
1; the row of a request without a decision carries its first step and sequence 0.

- ``status`` is the request's E-05 status at the run's record cutoff, derived from its
  ``decided_at`` and ``voided_at`` (T-PLT-17 is IM-S with timestamped terminal transitions);
  decisions after the cutoff are not read.
- ``preparer`` and ``approver`` are display names, "System" for the SYSTEM principal (an
  auto-approval); ``on_behalf_of`` names the delegator of a delegated decision; ``auto_rule_key``
  and ``auto_rule_version`` name the rule and the rule set version of an ``AUTO_APPROVE``.
- ``subject_id`` and ``subject_content_sha256`` (export and API only; SCREENS_B rev 1.25) are the
  subject's id and the SHA-256 of the subject content the decision covered (T-PLT-20); a row
  without a decision carries the request's hash. ``comment`` is the decision's comment.
- ``amount_functional`` is the request's amount in its entity's functional currency
  (``amount_currency``); the served view is ``functional`` and any other view is refused by name.

Control totals ``request_count``, ``decision_count``, ``auto_approval_count`` and the date range
applied.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.orm import Session

from erev_api.db.tables import approval_request, approval_step, legal_entity, rule, rule_set_version
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import ApprovalDecisionKind
from erev_api.uow import UnitOfWork

CODE: Final = "approvals_register"
ROW_KEY_PREFIX: Final = "decision:"  # RPT-26: row_key `decision:<request no>:<step no>:<sequence>`
DEFAULT_CURRENCY_VIEW: Final = "functional"  # SCREENS_B RPT-26 "functional amounts of requests"
AUTO_APPROVE: Final = ApprovalDecisionKind.AUTO_APPROVE.value
FIRST_STEP: Final = 1  # T-PLT-17 ``current_step_no`` starts at 1
VIEW_UNSUPPORTED: Final = (
    "The approvals register serves the functional view only: T-PLT-17 carries the amount of a "
    "request in its entity's functional currency and no other amount."
)
COLUMNS: Final = (
    Column("request_no", "Request", "code"),
    Column("subject_type", "Type", "code"),
    Column("subject_id", "Subject", "code"),
    Column("summary", "Summary", "text"),
    Column("entity_code", "Entity", "code"),
    Column("amount_currency", "Currency", "code"),
    Column("amount_functional", "Amount", "money"),
    Column("flags", "Flags", "codes"),
    Column("preparer", "Preparer", "text"),
    Column("submitted_at", "Submitted", "timestamp"),
    Column("step_name", "Step", "text"),
    Column("step_no", "Step no", "integer"),
    Column("approver", "Approver", "text"),
    Column("on_behalf_of", "On behalf of", "text"),
    Column("decision", "Decision", "code"),
    Column("auto_rule_key", "Rule", "code"),
    Column("auto_rule_version", "Rule version", "integer"),
    Column("decided_at", "Decided", "timestamp"),
    Column("comment", "Comment", "text"),
    Column("status", "Status", "code"),
    Column("subject_content_sha256", "Content hash", "code"),
)


@dataclass(frozen=True, slots=True)
class Source:
    """One request with its entity code and first step resolved — the input of
    ``dataset_rows``."""

    request: support.Request
    entity_code: str | None
    first_step: tuple[int, str] | None  # (step no, name); read for a request without a decision


def check_view(params: ReportParams) -> None:
    """RPT-26 serves the functional view; any other view is refused by name (no silent fallback)."""
    view = str(params.parameters.get("currency_view") or DEFAULT_CURRENCY_VIEW)
    if view != DEFAULT_CURRENCY_VIEW:
        raise tie_outs.invalid("currency_view", VIEW_UNSUPPORTED)


def _request_cells(item: Source, names: Mapping[UUID, str]) -> dict[str, Any]:
    request = item.request
    amount = None
    if request.amount_functional is not None and request.amount_currency is not None:
        amount = tie_outs.money(request.amount_functional, request.amount_currency)
    return {
        "request_no": request.request_no,
        "subject_type": request.subject_type,
        "subject_id": str(request.subject_id),
        "summary": request.summary,
        "entity_code": item.entity_code,
        "amount_currency": request.amount_currency,
        "amount_functional": amount,
        "flags": request.flags,
        "preparer": support.actor_names([request.preparer], names)[0],
        "submitted_at": request.submitted_at,
        "status": request.status,
    }


def dataset_rows(
    found: Iterable[Source],
    names: Mapping[UUID, str],
    *,
    rule_keys: Mapping[UUID, str],
    rule_versions: Mapping[UUID, int],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(rows in request-number, step and decision order, control totals). Pure."""
    rows: list[dict[str, Any]] = []
    requests = decisions = automatic = 0
    for item in sorted(found, key=lambda source: source.request.request_no):
        requests += 1
        request = item.request
        shared = _request_cells(item, names)
        if not request.decisions:
            step_no, step_name = item.first_step or (FIRST_STEP, None)
            rows.append(
                {
                    "row_key": f"{ROW_KEY_PREFIX}{request.request_no}:{step_no}:0",
                    **shared,
                    "step_name": step_name,
                    "step_no": step_no,
                    "subject_content_sha256": request.subject_content_sha256,
                }
            )
            continue
        taken: dict[int, int] = {}
        ordered = sorted(enumerate(request.decisions), key=lambda pair: (pair[1].step_no, pair[0]))
        for _, decision in ordered:
            decisions += 1
            automatic += 1 if decision.decision == AUTO_APPROVE else 0
            sequence = taken[decision.step_no] = taken.get(decision.step_no, 0) + 1
            delegator = None
            if decision.on_behalf_of_id is not None:
                delegator = names.get(decision.on_behalf_of_id)
            rows.append(
                {
                    "row_key": (
                        f"{ROW_KEY_PREFIX}{request.request_no}:{decision.step_no}:{sequence}"
                    ),
                    **shared,
                    "step_name": decision.step_name,
                    "step_no": decision.step_no,
                    "approver": support.actor_names(
                        [(decision.approver_id, decision.approver_kind)], names
                    )[0],
                    "on_behalf_of": delegator,
                    "decision": decision.decision,
                    "auto_rule_key": (
                        None
                        if decision.auto_rule_id is None
                        else rule_keys.get(decision.auto_rule_id)
                    ),
                    "auto_rule_version": (
                        None
                        if decision.auto_rule_set_version_id is None
                        else rule_versions.get(decision.auto_rule_set_version_id)
                    ),
                    "decided_at": decision.decided_at,
                    "comment": decision.comment,
                    "subject_content_sha256": decision.subject_content_sha256,
                }
            )
    return rows, {
        "request_count": requests,
        "decision_count": decisions,
        "auto_approval_count": automatic,
    }


def _entity_codes(session: Session, found: Sequence[support.Request]) -> dict[UUID, str]:
    ids = sorted({item.entity_id for item in found if item.entity_id is not None}, key=str)
    if not ids:
        return {}
    statement = select(legal_entity.c.id, legal_entity.c.code).where(legal_entity.c.id.in_(ids))
    return {UUID(str(entity_id)): str(code) for entity_id, code in session.execute(statement)}


def _first_steps(session: Session, found: Sequence[support.Request]) -> dict[UUID, tuple[int, str]]:
    ids = sorted({item.id for item in found if not item.decisions}, key=str)
    if not ids:
        return {}
    statement = (
        select(approval_step.c.approval_request_id, approval_step.c.step_no, approval_step.c.name)
        .where(approval_step.c.approval_request_id.in_(ids))
        .order_by(approval_step.c.approval_request_id, approval_step.c.step_no)
    )
    steps: dict[UUID, tuple[int, str]] = {}
    for request_id, step_no, name in session.execute(statement):
        steps.setdefault(UUID(str(request_id)), (int(step_no), str(name)))
    return steps


def _rules(
    session: Session, found: Sequence[support.Request]
) -> tuple[dict[UUID, str], dict[UUID, int]]:
    rule_ids = sorted(
        {d.auto_rule_id for item in found for d in item.decisions if d.auto_rule_id is not None},
        key=str,
    )
    version_ids = sorted(
        {
            d.auto_rule_set_version_id
            for item in found
            for d in item.decisions
            if d.auto_rule_set_version_id is not None
        },
        key=str,
    )
    keys: dict[UUID, str] = {}
    versions: dict[UUID, int] = {}
    if rule_ids:
        statement = select(rule.c.id, rule.c.rule_key).where(rule.c.id.in_(rule_ids))
        keys = {UUID(str(rule_id)): str(key) for rule_id, key in session.execute(statement)}
    if version_ids:
        numbered = select(rule_set_version.c.id, rule_set_version.c.version_no).where(
            rule_set_version.c.id.in_(version_ids)
        )
        versions = {UUID(str(found_id)): int(no) for found_id, no in session.execute(numbered)}
    return keys, versions


def sources(
    uow: UnitOfWork, params: ReportParams, *, bounds: tuple[datetime, datetime]
) -> list[support.Request]:
    """The requests in scope submitted in the range, as they stood at the record cutoff."""
    session = uow.session
    cutoff = tie_outs.cutoff_for(session, params)
    where: list[ColumnElement[bool]] = [
        support.requests_in_scope(session, params, cutoff=cutoff),
        approval_request.c.submitted_at >= bounds[0],
        approval_request.c.submitted_at < bounds[1],
    ]
    subject_types = params.parameters.get("subject_types")
    if subject_types:
        where.append(approval_request.c.subject_type.in_([str(value) for value in subject_types]))
    statuses = params.parameters.get("status")
    found = support.requests(session, cutoff=cutoff, where=where)
    if statuses:
        wanted = {str(value) for value in statuses}
        found = [item for item in found if item.status in wanted]
    return found


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    check_view(params)
    session = uow.session
    first, last = support.date_range(session, params, year=False, today=True)
    found = sources(uow, params, bounds=support.instants(first, last))
    codes = _entity_codes(session, found)
    steps = _first_steps(session, found)
    rule_keys, rule_versions = _rules(session, found)
    rows, totals = dataset_rows(
        [
            Source(
                request=item,
                entity_code=None if item.entity_id is None else codes.get(item.entity_id),
                first_step=steps.get(item.id),
            )
            for item in found
        ],
        support.names_of(session, found),
        rule_keys=rule_keys,
        rule_versions=rule_versions,
    )
    totals["from_date"], totals["to_date"] = first.isoformat(), last.isoformat()
    return ReportData(columns=COLUMNS, rows=tuple(rows), control_totals=totals)


__all__ = [
    "CODE",
    "COLUMNS",
    "DEFAULT_CURRENCY_VIEW",
    "Source",
    "build",
    "check_view",
    "dataset_rows",
    "sources",
]
