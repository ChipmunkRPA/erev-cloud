"""Version, allocation-trace and schedule evidence for contract samples (REQ-RPT-015).

A combined version is an indivisible accounting unit. Its companion contracts are
explicitly identified and every contracting/performing entity is authorized before
including the group. No recomputation or current-configuration reconstruction occurs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date
from decimal import Decimal, localcontext
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes
from sqlalchemy import or_, select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.session import system_entity_scope
from erev_api.db.tables import (
    calc_trace,
    contract,
    contract_computation,
    contract_version,
    obligation_version,
    schedule,
    schedule_line,
)
from erev_api.domain.reports.builders.extract_contract_versions import KEYS as VERSION_KEYS
from erev_api.domain.reports.builders.extract_obligations import COLUMNS as OBLIGATION_COLUMNS
from erev_api.domain.reports.builders.extract_schedule_lines import COLUMNS as LINE_COLUMNS
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.domain.reports.evidence_commands import PERMISSIONS
from erev_api.domain.reports.evidence_selection import SourceSelection
from erev_api.explain.store import TraceIntegrityError, trace_from_row
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.uow import UnitOfWork


@dataclass(frozen=True, slots=True)
class SampleComputations:
    files: tuple[PackFile, ...]
    version_ids: tuple[UUID, ...]
    # Includes companion contracts and performing entities needed for whole-group evidence.
    contract_ids: tuple[UUID, ...]
    entity_ids: tuple[UUID, ...]


def _invalid() -> Problem:
    return Problem(
        "validation-failed", "The sample computation evidence is incomplete or inconsistent."
    )


def collect(uow: UnitOfWork, selected: SourceSelection, *, as_of: date) -> SampleComputations:
    if (
        selected.tenant_id != uow.principal.tenant_id
        or not selected.contract_ids
        or selected.known_at.tzinfo is None
        or selected.known_at > uow.now
        or not PERMISSIONS <= uow.principal.permissions
    ):
        raise Problem("forbidden")
    if as_of > selected.known_at.astimezone(UTC).date():
        raise Problem("validation-failed", "The sample date exceeds its source cutoff.")
    for entity in selected.entity_ids:
        for permission in PERMISSIONS:
            require_for_entity(uow.ctx, permission, entity)
    tenant = selected.tenant_id
    cutoff = selected.known_at
    candidates = (
        uow.session.execute(
            select(
                *(contract_version.c[key] for key in VERSION_KEYS),
                contract_computation.c.stream_heads,
            )
            .join(
                contract_computation,
                (contract_computation.c.tenant_id == contract_version.c.tenant_id)
                & (contract_computation.c.id == contract_version.c.contract_computation_id),
            )
            .where(
                contract_version.c.tenant_id == tenant,
                contract_version.c.known_at <= cutoff,
                contract_version.c.created_at <= cutoff,
                contract_computation.c.created_at <= cutoff,
                contract_computation.c.status == "SUCCEEDED",
                or_(
                    *(
                        contract_computation.c.stream_heads.has_key(str(key))
                        for key in selected.contract_ids
                    )
                ),
            )
            .order_by(
                contract_version.c.known_at, contract_version.c.version_no, contract_version.c.id
            )
        )
        .mappings()
        .all()
    )
    files: list[PackFile] = []
    version_ids: list[UUID] = []
    contracts: set[UUID] = set(selected.contract_ids)
    entities: set[UUID] = set(selected.entity_ids)
    latest: dict[tuple[UUID, str], tuple[Any, ...]] = {}
    index = []
    for candidate in candidates:
        version = dict(candidate)
        version_id = version["id"]
        members = {UUID(key) for key in version.pop("stream_heads")}
        # Read complete identity/effective-date metadata before deciding visibility. RLS must
        # not turn a hidden companion into an apparently complete, earlier-effective version.
        with system_entity_scope(uow.session):
            identities = (
                uow.session.execute(
                    select(
                        contract.c.id,
                        contract.c.external_id,
                        contract.c.contracting_entity_id,
                    ).where(contract.c.tenant_id == tenant, contract.c.id.in_(members))
                )
                .mappings()
                .all()
            )
            population = (
                uow.session.execute(
                    select(
                        obligation_version.c.contract_id,
                        obligation_version.c.contracting_entity_id,
                        obligation_version.c.performing_entity_id,
                        obligation_version.c.effective_date,
                        obligation_version.c.created_at,
                    ).where(
                        obligation_version.c.tenant_id == tenant,
                        obligation_version.c.contract_version_id == version_id,
                    )
                )
                .mappings()
                .all()
            )
        if {row["id"] for row in identities} != members or not population:
            raise _invalid()
        effective = max(row["effective_date"] for row in population)
        if effective > as_of:
            continue
        group_entities = {row["contracting_entity_id"] for row in identities}
        group_entities.update(
            row[key]
            for row in population
            for key in ("contracting_entity_id", "performing_entity_id")
        )
        if not {row["contract_id"] for row in population} <= members:
            raise _invalid()
        for entity in group_entities:
            if uow.principal.entity_scope != "*" and entity not in uow.principal.entity_scope:
                raise Problem("not-found")
            for permission in PERMISSIONS:
                require_for_entity(uow.ctx, permission, entity)
        if any(row["created_at"] > cutoff for row in population):
            raise _invalid()
        # All entities in this immutable group have now passed current caller authorization.
        with system_entity_scope(uow.session):
            obligations = [
                dict(row)
                for row in uow.session.execute(
                    select(
                        obligation_version.c.trace_nodes,
                        *(
                            obligation_version.c[col.key]
                            for col in OBLIGATION_COLUMNS
                            if col.key in obligation_version.c
                        ),
                    )
                    .where(
                        obligation_version.c.tenant_id == tenant,
                        obligation_version.c.contract_version_id == version_id,
                    )
                    .order_by(obligation_version.c.contract_id, obligation_version.c.obligation_key)
                ).mappings()
            ]
            headers = [
                dict(row)
                for row in uow.session.execute(
                    select(schedule)
                    .where(
                        schedule.c.tenant_id == tenant,
                        schedule.c.contract_version_id == version_id,
                    )
                    .order_by(schedule.c.id)
                ).mappings()
            ]
            lines = [
                dict(row)
                for row in uow.session.execute(
                    select(
                        *(
                            schedule_line.c[col.key]
                            for col in LINE_COLUMNS
                            if col.key in schedule_line.c
                        ),
                    )
                    .where(
                        schedule_line.c.tenant_id == tenant,
                        schedule_line.c.contract_version_id == version_id,
                    )
                    .order_by(schedule_line.c.period_end_date, schedule_line.c.id)
                ).mappings()
            ]
        trace_row = (
            uow.session.execute(
                select(calc_trace).where(
                    calc_trace.c.tenant_id == tenant,
                    calc_trace.c.id == version["calc_trace_id"],
                    calc_trace.c.contract_version_id == version_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            trace_row is None
            or trace_row["created_at"] > cutoff
            or trace_row["book_code"] != version["book_code"]
            or trace_row["combination_group_id"] != version["combination_group_id"]
        ):
            raise _invalid()
        try:
            trace = trace_from_row(dict(trace_row))
        except (TraceIntegrityError, ValueError, KeyError, TypeError) as error:
            raise _invalid() from error
        node_ids = {node.id for node in trace.nodes}
        if len(trace.nodes) != trace_row["node_count"]:
            raise _invalid()
        for line in lines:
            if (
                line["contract_id"] not in members
                or line["entity_id"] not in group_entities
                or line["created_at"] > cutoff
                or line["book_code"] != version["book_code"]
                or line["trace_node_id"] not in node_ids
            ):
                raise _invalid()
        if {line["schedule_id"] for line in lines} - {header["id"] for header in headers}:
            raise _invalid()
        for header in headers:
            children = [line for line in lines if line["schedule_id"] == header["id"]]
            with localcontext() as context:
                context.prec = 80
                total = sum((line["amount"] for line in children), Decimal(0))
            if (
                header["created_at"] > cutoff
                or header["book_code"] != version["book_code"]
                or len(children) != header["line_count"]
                or any(line["currency"] != header["currency"] for line in children)
                or total != header["total_amount"]
            ):
                raise _invalid()
        for obligation in obligations:
            if not set(obligation["trace_nodes"].values()) <= node_ids:
                raise _invalid()
        prefix = f"computations/{version_id}"
        sections: dict[str, Any] = {
            "version": version,
            "members": [
                {**dict(row), "sampled": row["id"] in selected.contract_ids}
                for row in sorted(identities, key=lambda row: str(row["id"]))
            ],
            "allocations": obligations,
            "schedule": {"headers": headers, "lines": lines},
            "trace": {
                key: trace_row[key]
                for key in (
                    "id",
                    "format_version",
                    "engine_version",
                    "root_measures",
                    "trace_sha256",
                    "trace",
                )
            },
        }
        sections["trace"]["source_trace_sha256"] = sections["trace"].pop("trace_sha256")
        for name, content in sections.items():
            files.append(
                PackFile(f"{prefix}/{name}.json", canonical_bytes(redact_contacts(content)))
            )
        version_ids.append(version_id)
        contracts.update(members)
        entities.update(group_entities)
        index.append(
            {"version_id": version_id, "book": version["book_code"], "effective_date": effective}
        )
        for member in members.intersection(selected.contract_ids):
            key = (member, version["book_code"])
            rank = (effective, version["known_at"], version["version_no"], str(version_id))
            if key not in latest or rank > latest[key]:
                latest[key] = rank
    files.insert(
        0,
        PackFile(
            "sample/computations.json",
            canonical_bytes(
                {
                    "schema_version": 1,
                    "as_of": as_of,
                    "known_at": cutoff,
                    "versions": index,
                    "selected_versions": [
                        {"contract_id": key[0], "book": key[1], "version_id": value[-1]}
                        for key, value in sorted(latest.items())
                    ],
                    "basis": (
                        "Versions effective by the sample date; "
                        "schedules include future planned periods."
                    ),
                }
            ),
        ),
    )
    return SampleComputations(
        tuple(files), tuple(version_ids), tuple(sorted(contracts)), tuple(sorted(entities))
    )
