"""RPT-27 ``api_client_inventory`` API client inventory (SCREENS_B §5.6.5 RPT-27; 04 T-PLT-15,
T-RPT-01 ``ipe_logic``; 03 REQ-PLT-033; CTL-037; BUILD_SPEC RPS-2).

One row per OAuth2 client-credentials client created at or before ``known_at``, ordered by name and
client id; revoked clients appear only with ``include_revoked``. A client covering all entities is
always listed; any other client when its entity scope includes an entity of the run. Secret hashes
are never selected. Control total ``client_count``. Grid filters ``name`` and ``status``.

A client's scopes are an access grant (REQ-PLT-033 rev 1.83; supervisor ruling R-38 (iii)), and
the inventory is the evidence of control CTL-037, so each row shows the grant: ``approval`` is the
number of the client's latest ``ROLE_ASSIGNMENT`` request by ``known_at``, ``approved_by`` its
approvers — or ``Rule <key>`` when a rule approved it at submission — and ``approved_at`` the
instant it was approved; all three are empty while the request is pending or after it was
rejected (the status says which), and for a client that has no request. ``secret_rotated_at`` is
the instant the current secret was issued; ``Not issued`` marks a client that cannot authenticate
because no secret was issued yet.

[J] L5-2-Q-13: ``api_client`` is IM-M, so status, last use and rotation are the values at run time;
``known_at`` limits the population to the clients created by then. The row field ``entity_scope`` is
the list of entity codes, empty for a client covering all entities, which XLSX and PDF show as "All
entities"; ``created_by`` is API-S-Actor.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Final
from uuid import UUID

from sqlalchemy import ColumnElement, Uuid, literal, or_, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session

from erev_api.db.tables import api_client, legal_entity, rule
from erev_api.domain.platform import approval_queries
from erev_api.domain.reports import tie_outs
from erev_api.domain.reports.builders import ReportParams, filter_problem, unknown_filter
from erev_api.domain.reports.builders import register_support as support
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.enums import ApiClientStatus, ApprovalSubjectType
from erev_api.uow import UnitOfWork

CODE: Final = "api_client_inventory"
CONTROL_TOTAL: Final = "client_count"
ROW_KEY_PREFIX: Final = "client:"
INCLUDE_REVOKED: Final = "include_revoked"
ALL_ENTITIES: Final = "All entities"
NEVER: Final = "Never"
NOT_ISSUED: Final = "Not issued"
RULE: Final = "Rule {rule_key}"
COLUMNS: Final = (
    Column("name", "Name", "text"),
    Column("client_id", "Client id", "code"),
    Column("status", "Status", "code"),
    Column("scopes", "Scopes", "codes"),
    Column("entity_scope", "Entity scope", "codes", empty_text=ALL_ENTITIES),
    Column("rate_limit_per_minute", "Rate limit per minute", "integer"),
    Column("expires_at", "Expires", "timestamp"),
    Column("last_used_at", "Last used", "timestamp", empty_text=NEVER),
    Column("secret_rotated_at", "Secret issued", "timestamp", empty_text=NOT_ISSUED),
    Column("approval", "Approval", "code"),
    Column("approved_by", "Approved by", "text"),
    Column("approved_at", "Approved", "timestamp"),
    Column("created_by", "Created by", "actor"),
    Column("created_at", "Created", "timestamp"),
)
FILTERS: Final[dict[str, ColumnElement[Any]]] = {
    "name": api_client.c.name,
    "status": api_client.c.status,
}
_STATUSES: Final = frozenset(status.value for status in ApiClientStatus)
_SPACES: Final = re.compile(r"\s+")


def row_key(name: str) -> str:
    """``client:<name normalised>``: trimmed, lower case, whitespace runs as one hyphen."""
    return ROW_KEY_PREFIX + _SPACES.sub("-", name.strip().lower())


EVIDENCE: Final = "api_client_inventory"  # the retained input facts (Codex 2225)
_INSTANTS: Final = ("expires_at", "last_used_at", "secret_rotated_at", "created_at")


def _grants(
    session: Session, client_ids: list[UUID], *, cutoff: datetime
) -> dict[UUID, dict[str, Any]]:
    """The grant of each client: its latest ``ROLE_ASSIGNMENT`` request by ``cutoff`` with the
    approving deciders by then and, for a rule's approval, the rule key (ruling R-38 (iii))."""
    found = support.requests_of_subjects(
        session, ApprovalSubjectType.ROLE_ASSIGNMENT.value, client_ids, cutoff=cutoff
    )
    latest = {client_id: requests[-1] for client_id, requests in found.items()}
    rule_ids = sorted(
        {
            decision.auto_rule_id
            for request in latest.values()
            for decision in request.decisions
            if decision.approving and decision.auto_rule_id is not None
        },
        key=str,
    )
    keys: dict[UUID, str] = {}
    if rule_ids:
        keys = {
            UUID(str(rule_id)): str(rule_key)
            for rule_id, rule_key in session.execute(
                select(rule.c.id, rule.c.rule_key).where(rule.c.id.in_(rule_ids))
            )
        }
    grants: dict[UUID, dict[str, Any]] = {}
    for client_id, request in latest.items():
        approving = [decision for decision in request.decisions if decision.approving]
        rule_key = next(
            (keys.get(d.auto_rule_id) for d in approving if d.auto_rule_id is not None), None
        )
        grants[client_id] = {
            "request_no": request.request_no,
            "approved_at": request.approved_at,
            "approvers": [
                [None if d.approver_id is None else str(d.approver_id), d.approver_kind]
                for d in approving
                if d.auto_rule_id is None
            ],
            "rule_key": rule_key,
        }
    return grants


def approved_by(grant: Mapping[str, Any] | None, names: Mapping[UUID, str]) -> str | None:
    """Who approved a client's grant: ``Rule <key>`` for a rule's approval at submission, else the
    approvers' names in decision order; None while it is not approved. Pure."""
    if grant is None or grant["approved_at"] is None:
        return None
    if grant["rule_key"] is not None:
        return RULE.format(rule_key=grant["rule_key"])
    return support.joined(
        support.actor_names(
            [
                (None if user_id is None else UUID(str(user_id)), str(kind))
                for user_id, kind in grant["approvers"]
            ],
            names,
        )
    )


def _live_inputs(
    session: Session, params: ReportParams
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    """The CURRENT rows — each with its grant — entity codes and display names the report
    consumes."""
    statement = select(
        api_client.c.id,
        api_client.c.name,
        api_client.c.client_id,
        api_client.c.status,
        api_client.c.scopes,
        api_client.c.is_all_entities,
        api_client.c.entity_ids,
        api_client.c.rate_limit_per_minute,
        api_client.c.expires_at,
        api_client.c.last_used_at,
        api_client.c.secret_rotated_at,
        api_client.c.created_by,
        api_client.c.created_by_kind,
        api_client.c.created_at,
    ).where(api_client.c.created_at <= params.known_at)
    if not params.parameters.get(INCLUDE_REVOKED, False):
        statement = statement.where(api_client.c.status != ApiClientStatus.REVOKED.value)
    covered: ColumnElement[bool] = api_client.c.is_all_entities.is_(True)
    if params.entity_ids:
        run_entities = literal(list(params.entity_ids), type_=ARRAY(Uuid()))
        covered = or_(covered, api_client.c.entity_ids.op("&&")(run_entities))
    statement = statement.where(covered)
    for name, value in sorted(params.filters.items()):
        column = FILTERS.get(name)
        if column is None:
            raise unknown_filter(name, FILTERS)
        if name == "status" and value not in _STATUSES:
            raise filter_problem(name, f"status must be one of {', '.join(sorted(_STATUSES))}.")
        statement = statement.where(column == value)
    rows = [
        dict(row)
        for row in session.execute(
            statement.order_by(api_client.c.name, api_client.c.client_id)
        ).mappings()
    ]
    grants = _grants(session, [UUID(str(row["id"])) for row in rows], cutoff=params.known_at)
    for row in rows:
        row["grant"] = grants.get(UUID(str(row.pop("id"))))
    entity_ids = sorted({UUID(str(value)) for row in rows for value in row["entity_ids"] or ()})
    codes: dict[str, str] = {}
    if entity_ids:
        codes = {
            str(found.id): str(found.code)
            for found in session.execute(
                select(legal_entity.c.id, legal_entity.c.code).where(
                    legal_entity.c.id.in_(entity_ids)
                )
            )
        }
    people: list[UUID | None] = [row["created_by"] for row in rows]
    for row in rows:
        for user_id, _kind in (row["grant"] or {}).get("approvers", ()):
            people.append(None if user_id is None else UUID(str(user_id)))
    names = {
        str(user_id): name
        for user_id, name in approval_queries.display_names(session, people).items()
    }
    return rows, codes, names


def _json_safe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The consumed rows as JSON-safe evidence: ids as text, instants RFC 3339, arrays lists."""
    safe: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["client_id"] = str(item["client_id"])
        item["created_by"] = None if item["created_by"] is None else str(item["created_by"])
        item["scopes"] = list(item["scopes"] or ())
        item["entity_ids"] = [str(value) for value in item["entity_ids"] or ()]
        for name in _INSTANTS:
            item[name] = None if item[name] is None else item[name].isoformat()
        if item["grant"] is not None:
            approved = item["grant"]["approved_at"]
            item["grant"] = {
                **item["grant"],
                "approved_at": None if approved is None else approved.isoformat(),
            }
        safe.append(item)
    return safe


def _from_evidence(
    evidence: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, str]]:
    """The retained inputs restored to the shapes the builder logic consumes."""
    rows: list[dict[str, Any]] = []
    for item in evidence["rows"]:
        row = dict(item)
        for name in _INSTANTS:
            row[name] = None if row[name] is None else datetime.fromisoformat(str(row[name]))
        grant = row.get("grant")
        if grant is not None:
            approved = grant["approved_at"]
            row["grant"] = {
                **grant,
                "approved_at": None if approved is None else datetime.fromisoformat(str(approved)),
            }
        rows.append(row)
    return rows, dict(evidence["codes"]), dict(evidence["names"])


def build(uow: UnitOfWork, params: ReportParams) -> ReportData:
    """S15-R-24 / Codex 2202 / 2225 — strategy ``retained_inputs``: no contract version binds this
    report (it reads mutable client fields and drops revoked clients by default), so a live build
    records the rows, entity codes and creator names it consumed as evidence, and a bound run
    REBUILDS from that evidence through the same logic below — never a live re-read, never a
    replay of the saved output (a calculation change still shows as a CTL-029 mismatch)."""
    if params.binding is not None:
        rows, codes, names = _from_evidence(tie_outs.bound_evidence(params, EVIDENCE))
    else:
        rows, codes, names = _live_inputs(uow.session, params)
        tie_outs.record_members(params, "api_client", (row["client_id"] for row in rows))
        tie_outs.record_evidence(
            params, EVIDENCE, {"rows": _json_safe(rows), "codes": codes, "names": names}
        )
    display = {UUID(user_id): name for user_id, name in names.items()}
    items = tuple(
        {
            "row_key": row_key(str(row["name"])),
            "name": str(row["name"]),
            "client_id": str(row["client_id"]),
            "status": str(row["status"]),
            "scopes": tuple(sorted(str(scope) for scope in row["scopes"])),
            "entity_scope": ()
            if row["is_all_entities"]
            else tuple(sorted(codes.get(str(value), str(value)) for value in row["entity_ids"])),
            "rate_limit_per_minute": int(row["rate_limit_per_minute"]),
            "expires_at": row["expires_at"],
            "last_used_at": row["last_used_at"],
            "secret_rotated_at": row["secret_rotated_at"],
            "approval": None if row.get("grant") is None else str(row["grant"]["request_no"]),
            "approved_by": approved_by(row.get("grant"), display),
            "approved_at": None if row.get("grant") is None else row["grant"]["approved_at"],
            "created_by": approval_queries.actor(
                None if row["created_by"] is None else UUID(str(row["created_by"])),
                str(row["created_by_kind"]),
                display,
            ),
            "created_at": row["created_at"],
        }
        for row in rows
    )
    return ReportData(columns=COLUMNS, rows=items, control_totals={CONTROL_TOTAL: len(items)})
