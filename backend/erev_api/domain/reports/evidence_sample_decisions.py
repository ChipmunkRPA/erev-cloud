"""Contract sample approval decisions and linked audit slice (REQ-RPT-015).

The slice retains chain identifiers but is not a full audit-chain verification. Shared
contract events and multi-entity approvals require access to their complete population.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import func, select

from erev_api.approvals.engine import request_entities
from erev_api.audit.redact import redact
from erev_api.auth.dependencies import require_for_entity
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import approval_decision, approval_request, audit_event_contract, contract
from erev_api.domain.platform.audit_log import trail_source
from erev_api.domain.reports.builders import audit_log_export, register_support
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.domain.reports.evidence_commands import PERMISSIONS
from erev_api.domain.reports.evidence_selection import SourceSelection
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class SampleDecisions:
    files: tuple[PackFile, ...]
    contract_ids: tuple[UUID, ...]
    entity_ids: tuple[UUID, ...]
    approval_request_ids: tuple[UUID, ...]
    all_entities: bool


def collect(
    uow: UnitOfWork,
    selected: SourceSelection,
    *,
    approval_request_ids: tuple[UUID, ...] = (),
) -> SampleDecisions:
    if (
        selected.tenant_id != uow.principal.tenant_id
        or not selected.contract_ids
        or selected.known_at.tzinfo is None
        or selected.known_at > uow.now
        or not PERMISSIONS <= uow.principal.permissions
    ):
        raise Problem("forbidden")
    tenant = selected.tenant_id
    cutoff = selected.known_at
    entities = set(selected.entity_ids)
    for entity in entities:
        for permission in PERMISSIONS:
            require_for_entity(uow.ctx, permission, entity)
    rows: dict[UUID, dict[str, Any]] = {}
    links: dict[str, list[str]] = {}
    for contract_id in selected.contract_ids:
        source = trail_source(contract_id)
        committed_at = func.erev.source_commit_time("audit_event", source.columns["id"])
        statement = source.statement.with_only_columns(
            *(source.columns[key].label(key) for key in audit_log_export.FIELDS),
            committed_at.label("committed_server_at"),
        ).where(
            source.columns["tenant_id"] == tenant,
            source.columns["occurred_at"] <= cutoff,
            committed_at <= cutoff,
        )
        found = uow.session.execute(statement).mappings().all()
        links[str(contract_id)] = [
            str(row["id"]) for row in sorted(found, key=lambda row: row["chain_seq"])
        ]
        rows.update((row["id"], dict(row)) for row in found)
    # The link table is tenant-scoped. Verify every contract named by shared events before
    # returning any event payload; a visible contract cannot disclose a hidden companion.
    linked = (
        set(
            uow.session.execute(
                select(audit_event_contract.c.contract_id).where(
                    audit_event_contract.c.tenant_id == tenant,
                    audit_event_contract.c.audit_event_id.in_(rows),
                )
            ).scalars()
        )
        if rows
        else set()
    )
    contracts = set(selected.contract_ids) | linked
    with system_entity_scope(uow.session):
        identities = uow.session.execute(
            select(contract.c.id, contract.c.contracting_entity_id).where(
                contract.c.tenant_id == tenant,
                contract.c.id.in_(contracts),
            )
        ).all()
    if {row.id for row in identities} != contracts:
        raise Problem("not-found")
    for identity in identities:
        if (
            uow.principal.entity_scope != "*"
            and identity.contracting_entity_id not in uow.principal.entity_scope
        ):
            raise Problem("not-found")
        for permission in PERMISSIONS:
            require_for_entity(uow.ctx, permission, identity.contracting_entity_id)
        entities.add(identity.contracting_entity_id)
    wanted = set(approval_request_ids)
    for row in rows.values():
        if row["approval_request_id"] is not None:
            wanted.add(row["approval_request_id"])
        if row["object_type"] == "approval_request" and row["object_id"] is not None:
            wanted.add(row["object_id"])
    requests = (
        uow.session.execute(
            select(approval_request).where(
                approval_request.c.tenant_id == tenant,
                approval_request.c.id.in_(wanted),
                approval_request.c.submitted_at <= cutoff,
            )
        )
        .mappings()
        .all()
        if wanted
        else []
    )
    if {row["id"] for row in requests} != wanted:
        raise Problem("validation-failed", "A sample approval is unavailable at its source cutoff.")
    all_entities = False
    for request in requests:
        scope = request_entities(dict(request))
        visible = uow.principal.entity_scope
        if not scope.covered_by("*" if visible == "*" else frozenset(visible)):
            raise Problem("not-found")
        for permission in PERMISSIONS:
            granted = uow.principal.permission_scopes.get(permission)
            if granted is None or not scope.covered_by(granted):
                raise Problem("not-found")
        entities.update(scope.ids)
        all_entities |= scope.all_entities
    historical = register_support.requests_by_id(uow.session, wanted, cutoff=cutoff, committed=True)
    if set(historical) != wanted:
        raise Problem("validation-failed", "A sample approval is unavailable at its source cutoff.")
    decisions = (
        [
            dict(row)
            for row in uow.session.execute(
                select(
                    approval_decision,
                    func.erev.source_commit_time("approval_decision", approval_decision.c.id).label(
                        "committed_server_at"
                    ),
                )
                .where(
                    approval_decision.c.tenant_id == tenant,
                    approval_decision.c.approval_request_id.in_(wanted),
                    approval_decision.c.decided_at <= cutoff,
                    func.erev.source_commit_time("approval_decision", approval_decision.c.id)
                    <= cutoff,
                )
                .order_by(approval_decision.c.decided_at, approval_decision.c.id)
            ).mappings()
        ]
        if wanted
        else []
    )
    for decision in decisions:
        decision.pop("tenant_id")
        if (
            decision["subject_content_sha256"]
            != historical[decision["approval_request_id"]].subject_content_sha256
        ):
            raise Problem(
                "validation-failed", "The approval decision covers different subject content."
            )
    request_rows = []
    for request_id in sorted(wanted):
        row = asdict(historical[request_id])
        request_rows.append(row)
    audit_rows, controls = audit_log_export.dataset_rows(
        redact_contacts(row) for row in rows.values()
    )
    common = {"schema_version": 2, "known_at": cutoff}
    files = (
        PackFile(
            "sample/approvals.json",
            canonical_bytes(
                redact_contacts(
                    redact(
                        {
                            **common,
                            "requests": request_rows,
                            "decisions": decisions,
                            "scope": {"entity_ids": sorted(entities), "all_entities": all_entities},
                        }
                    )
                )
            ),
        ),
        PackFile(
            "sample/audit.json",
            canonical_bytes(
                {
                    **common,
                    "contracts": links,
                    "events": audit_rows,
                    "control_totals": controls,
                    "commit_evidence": {
                        str(identity): row["committed_server_at"]
                        for identity, row in sorted(rows.items())
                    },
                    "basis": "Linked contract audit slice; not a full-chain verification.",
                }
            ),
        ),
    )
    return SampleDecisions(
        files,
        tuple(sorted(contracts)),
        tuple(sorted(entities)),
        tuple(sorted(wanted)),
        all_entities,
    )
