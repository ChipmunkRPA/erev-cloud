"""Admit a migration's independent legacy inputs under current report permission.

Verify the immutable import operation, confirmed mapping, original file and complete
retained row population before handing history to the comparison projector. This
same-tenant reader does not authorize a linked sandbox or bypass its grants.
"""

import hashlib
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from erev_engine.canonical import canonical_bytes, sha256_hex
from erev_engine.upgrade import decode_input
from sqlalchemy import select

from erev_api.auth.principal import Principal
from erev_api.db.tables import job, legal_entity, migrated_legacy_row, migration_population_version
from erev_api.domain.migration import legacy_db, repository
from erev_api.files.store import lock_readable, open_file
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork


@dataclass(frozen=True)
class Admitted:
    rows: tuple[legacy_db.LegacyRow, ...]
    entity_mapping: dict[str, str]
    evidence: dict[str, Any]


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Parallel-run migration source: {detail}")


def read_for_report(
    uow: UnitOfWork,
    migration_id: UUID,
    *,
    entity_ids: tuple[UUID, ...],
    known_at: datetime,
    requester: Principal | None = None,
) -> Admitted:
    if known_at.tzinfo is None:
        raise _refuse("the cutoff must include a time zone.")
    principal = requester or uow.principal
    scope = principal.permission_scopes.get("report.run")
    if (
        principal.tenant_id != uow.principal.tenant_id
        or "report.run" not in principal.permissions
        or not scope
        or (scope != "*" and not set(entity_ids) <= scope)
    ):
        raise Problem("forbidden")
    batch = repository.get_batch(uow, migration_id)
    if batch["created_at"] > known_at or batch.get("capture_operation_id") is None:
        raise _refuse("the migration has no imported source at this cutoff.")
    if batch.get("sandbox_tenant_id") not in (None, principal.tenant_id):
        raise _refuse("the migration sandbox requires its own authorized comparison context.")
    operation = (
        uow.session.execute(
            select(job).where(
                job.c.tenant_id == principal.tenant_id,
                job.c.id == batch["capture_operation_id"],
            )
        )
        .mappings()
        .one_or_none()
    )
    if (
        operation is None
        or operation["kind"] != "MIGRATION_IMPORT"
        or operation["subject_type"] != "migration_batch"
        or operation["subject_id"] != migration_id
        or operation["created_at"] > known_at
        or operation["state"] != "SUCCEEDED"
        or operation["finished_at"] is None
        or operation["finished_at"] > known_at
    ):
        raise _refuse("the original import operation is unavailable at this cutoff.")
    params = operation["params"]
    mapping: dict[str, str] = {}
    try:
        if params["migration_id"] != str(migration_id) or params["phase"] != "IMPORT":
            raise ValueError("import subject")
        for item in params["entity_mapping"]:
            legacy, code = item["legacy_name"], item["entity_code"]
            if (
                not isinstance(legacy, str)
                or not isinstance(code, str)
                or not legacy
                or not code
                or legacy in mapping
            ):
                raise ValueError("mapping")
            mapping[legacy] = code
        if not mapping:
            raise ValueError("empty mapping")
    except (KeyError, TypeError, ValueError) as error:
        raise _refuse("the confirmed import mapping is invalid.") from error
    targets = dict(
        uow.session.execute(
            select(legal_entity.c.code, legal_entity.c.id).where(
                legal_entity.c.code.in_(set(mapping.values())),
                legal_entity.c.id.in_(entity_ids),
                legal_entity.c.created_at <= known_at,
            )
        )
        .tuples()
        .all()
    )
    if set(targets) != set(mapping.values()):
        raise Problem("forbidden")
    # Full confirmed source scope is authorized before plaintext is opened.
    file_id = UUID(str(batch["source_file_id"]))
    lock_readable(uow.session, [file_id])
    meta, stream = open_file(uow.session, file_id, files=uow.files, keyring=uow.keyring)
    with stream:
        if meta["purpose"] != "LEGACY_DATABASE" or meta["created_at"] > known_at:
            raise _refuse("the retained source file has the wrong purpose or cutoff.")
        digest = hashlib.sha256()
        size = 0
        with tempfile.NamedTemporaryFile(suffix=".db") as spool:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                size += len(chunk)
                if size > meta["size_bytes"]:
                    raise _refuse("the source file size differs from its retained metadata.")
                digest.update(chunk)
                spool.write(chunk)
            spool.flush()
            if (
                size != meta["size_bytes"]
                or digest.hexdigest() != meta["sha256"]
                or digest.hexdigest() != batch["source_sha256"]
            ):
                raise _refuse("the source file digest differs from the migration.")
            rows = legacy_db.rows(Path(spool.name))
    raw = (
        uow.session.execute(
            select(migrated_legacy_row)
            .where(
                migrated_legacy_row.c.migration_batch_id == migration_id,
                migrated_legacy_row.c.created_at <= known_at,
            )
            .order_by(migrated_legacy_row.c.source_rowid)
        )
        .mappings()
        .all()
    )
    if len(raw) != len(rows):
        raise _refuse("the retained history population differs from the source database.")
    references = []
    for stored, original in zip(raw, rows, strict=True):
        if (
            stored["source_rowid"] != original.source_rowid
            or stored["legacy_row_sha256"] != original.sha256
            or sha256_hex(stored["legacy_row"]) != original.sha256
            or stored["contract_external_id"] != original.contract_external_id
            or stored["record_unique_id"] != original.record_unique_id
        ):
            raise _refuse("a retained history row does not match the original database.")
        if original.values.get("Selling Entity") not in mapping:
            raise _refuse("the imported history contains an unconfirmed selling entity.")
        references.append(
            {"id": str(stored["id"]), "rowid": original.source_rowid, "sha256": original.sha256}
        )
    # The legacy format has no currency column. Bind the currency used by the
    # original import, never today's tenant reporting-currency configuration.
    captures = (
        uow.session.execute(
            select(migration_population_version)
            .where(
                migration_population_version.c.migration_batch_id == migration_id,
                migration_population_version.c.capture_operation_id == operation["id"],
                migration_population_version.c.created_at <= known_at,
            )
            .order_by(migration_population_version.c.id)
        )
        .mappings()
        .all()
    )
    currencies: set[str] = set()
    captured_contracts: set[str] = set()
    capture_references = []
    for captured in captures:
        document = captured["input_evidence"]
        if sha256_hex(document) != captured["input_evidence_sha256"]:
            raise _refuse("the original import input evidence digest differs.")
        try:
            bundle = decode_input(canonical_bytes(document))
        except (ValueError, TypeError, KeyError) as error:
            raise _refuse("the original import input evidence is malformed.") from error
        for contract in bundle.contracts:
            if contract.contracting_entity_code not in mapping.values():
                raise _refuse("the original import contains an unconfirmed entity.")
            currencies.add(contract.transaction_currency)
            captured_contracts.add(contract.external_id)
        capture_references.append(
            {
                "id": str(captured["id"]),
                "sha256": captured["input_evidence_sha256"],
            }
        )
    if captured_contracts != {row.contract_external_id for row in rows} or len(currencies) != 1:
        raise _refuse("the original import must establish one currency for the full population.")
    evidence = {
        "version": 1,
        "reporting_currency": next(iter(currencies)),
        "capture_inputs": capture_references,
        "tenant_id": str(principal.tenant_id),
        "migration_id": str(migration_id),
        "mode": str(batch["mode"]),
        "cutover_date": None
        if batch["cutover_date"] is None
        else batch["cutover_date"].isoformat(),
        "known_at": known_at.isoformat(),
        "file_id": str(file_id),
        "file_sha256": digest.hexdigest(),
        "import_operation_id": str(operation["id"]),
        "import_params_sha256": sha256_hex(params),
        "entity_mapping": dict(sorted(mapping.items())),
        "entity_ids": sorted(str(value) for value in targets.values()),
        "rows": references,
    }
    return Admitted(rows, mapping, evidence)
