"""Read-only durable evidence basis for the pending migration promotion implementation.

This does not submit or approve anything. Live configuration, activation, policy publication,
reproduction and atomic promotion still need their own checks before a route can be enabled.
"""

from __future__ import annotations

from collections.abc import Mapping
from fractions import Fraction
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import select

from erev_api.db.tables import (
    migrated_legacy_row,
    migration_population_obligation,
    migration_population_version,
)
from erev_api.domain.migration import opening_plan, reconciliation, repository
from erev_api.domain.migration.legacy_db import LegacyRow
from erev_api.enums import MigrationMode
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork


def _refuse(message: str) -> Problem:
    return Problem(
        "invalid-transition",
        message,
        errors=[
            ProblemError(
                field="migration_id", rule_id="TO_MIGRATION_UNEXPLAINED_ZERO", message=message
            )
        ],
    )


def _stored_line(row: Mapping[str, Any]) -> tuple[object, ...]:
    return (
        str(row["contract_external_id"]),
        None if row["obligation_key"] is None else str(row["obligation_key"]),
        str(row["measure"]),
        *(
            Fraction(str(row[name]))
            for name in ("source_value", "erev_value", "difference", "tolerance")
        ),
        bool(row["is_within_tolerance"]),
        row["deviation_ref"],
        row["exception_item_id"],
    )


def review_basis(uow: UnitOfWork, batch_id: UUID) -> dict[str, Any]:
    """Recheck all captured figures and bind the exact stored source/capture/reconciliation.

    The future command caller must hold its lifecycle lock while using this basis.
    Decision-derived status, approval id and timestamps are not review content. The function
    deliberately admits SUBMITTED as well as RECONCILED so review content can be rechecked
    during a later approval decision without its lifecycle transition changing the fingerprint.
    """
    from erev_api.domain.migration.jobs import assess_batch

    batch = repository.get_batch(uow, batch_id)
    if str(batch["mode"]) != MigrationMode.OPENING_BALANCES.value:
        raise _refuse("Opening-balance promotion review does not support replay migrations.")
    if str(batch["status"]) not in {"RECONCILED", "SUBMITTED"}:
        raise _refuse("Reconcile the migration before requesting promotion review.")
    lines = assess_batch(uow, batch)
    if not lines or reconciliation.control_totals(lines).unexplained:
        raise _refuse(
            "Promotion requires a complete reconciliation with no unexplained differences."
        )
    stored = repository.reconciliation_rows(uow, batch_id)
    expected = {
        (
            line.contract_external_id,
            line.obligation_key,
            line.measure,
            line.source_value,
            line.erev_value,
            line.difference,
            line.tolerance,
            line.is_within_tolerance,
            line.deviation_ref,
            None,
        )
        for line in lines
    }
    actual = {_stored_line(row) for row in stored}
    if len(stored) != len(lines) or actual != expected:
        raise _refuse("The stored reconciliation does not match the retained computation evidence.")
    source_rows = (
        uow.session.execute(
            select(migrated_legacy_row)
            .where(migrated_legacy_row.c.migration_batch_id == batch_id)
            .order_by(migrated_legacy_row.c.source_rowid)
        )
        .mappings()
        .all()
    )
    for row in source_rows:
        source = LegacyRow(int(row["source_rowid"]), dict(row["legacy_row"]))
        if source.sha256 != str(row["legacy_row_sha256"]):
            raise _refuse("A retained legacy row does not match its recorded source hash.")
    plan = opening_plan.restore(
        [LegacyRow(int(row["source_rowid"]), dict(row["legacy_row"])) for row in source_rows],
        batch["cutover_date"],
        dict(batch.get("profile") or {}).get("opening_plan"),
    )
    population = repository.comparison_population(uow, batch)
    if population is None:
        raise _refuse("The migration has no captured population for promotion review.")
    opening_plan.verify_inputs(plan, batch, repository.verify_capture_evidence(uow, population))
    captures = (
        uow.session.execute(
            select(migration_population_version)
            .where(migration_population_version.c.migration_batch_id == batch_id)
            .order_by(migration_population_version.c.contract_version_id)
        )
        .mappings()
        .all()
    )
    obligations = (
        uow.session.execute(
            select(migration_population_obligation)
            .where(migration_population_obligation.c.migration_batch_id == batch_id)
            .order_by(migration_population_obligation.c.obligation_version_id)
        )
        .mappings()
        .all()
    )
    return {
        "basis_schema": 1,
        "migration_id": str(batch_id),
        "mode": str(batch["mode"]),
        "source_file_id": str(batch["source_file_id"]),
        "source_sha256": str(batch["source_sha256"]),
        "cutover_date": batch["cutover_date"],
        "capture_operation_id": batch["capture_operation_id"],
        "profile": dict(batch.get("profile") or {}),
        "registry_version_id": batch.get("registry_version_id"),
        "reconciliation_id": batch.get("reconciliation_id"),
        "reconciliation_report_run_id": batch.get("reconciliation_report_run_id"),
        "source_rows_sha256": sha256_hex([dict(row) for row in source_rows]),
        "capture_sha256": sha256_hex([dict(row) for row in captures]),
        "captured_obligations_sha256": sha256_hex([dict(row) for row in obligations]),
        "reconciliation_sha256": sha256_hex([dict(row) for row in stored]),
        "control_totals": reconciliation.control_totals(lines).as_json(),
    }
