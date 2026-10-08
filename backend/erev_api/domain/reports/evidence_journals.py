"""RPS-16 batch register tied to the frozen JE population and historical run state.

Batch identities and sealed figures are checked against frozen lines. Mutable export
attempts, errors and current states are not exported as historical facts. Completeness
is the lock's saved JE_COMPLETE result, not a fresh assertion over today's ledger.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from erev_engine.canonical import canonical_bytes
from sqlalchemy import select

from erev_api.auth.dependencies import require_for_entity
from erev_api.db.tables import journal_batch, journal_run
from erev_api.domain.close import gates
from erev_api.domain.reports import evidence_certification, evidence_close, locked
from erev_api.domain.reports.builders import je_population
from erev_api.domain.reports.evidence_archive import PackFile
from erev_api.domain.reports.evidence_selection import SourceSelection
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

AMOUNTS = ("debit_txn", "credit_txn", "debit_functional", "credit_functional")
BATCH_FIELDS = (
    "id",
    "journal_run_id",
    "batch_no",
    "chunk_no",
    "external_id",
    "txn_currency",
    "functional_currency",
    "line_count",
    "total_debit_txn",
    "total_credit_txn",
    "total_debit_functional",
    "total_credit_functional",
    "engine_release_id",
)
RUN_FIELDS = (
    "id",
    "run_no",
    "mode",
    "grain",
    "cutoff_known_at",
    "from_chain_seq",
    "to_chain_seq",
    "delta_book_code",
    "delta_from_chain_seq",
    "delta_to_chain_seq",
    "functional_currency",
    "line_count",
    "total_debit_functional",
    "total_credit_functional",
)


def checked_batches(
    population: Sequence[Mapping[str, Any]],
    batches: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Every frozen row belongs to exactly one declared batch; all counts/amounts agree."""
    try:
        declared = {(row["run_no"], row["external_id"]): row for row in batches}
        if len(declared) != len(batches):
            raise ValueError("duplicate batch identities")
        totals = {key: {name: Decimal(0) for name in AMOUNTS} for key in declared}
        counts = dict.fromkeys(declared, 0)
        seen = set()
        for row in population:
            identity = row["row_key"]
            if identity in seen:
                raise ValueError("duplicate frozen journal line")
            seen.add(identity)
            key = (row["run_no"], row["batch_external_id"])
            if key not in declared:
                raise ValueError("a frozen line has no historical batch")
            batch = declared[key]
            for field in ("txn_currency", "functional_currency", "run_state"):
                if row[field] != batch[field]:
                    raise ValueError("frozen journal currency or run state differs")
            counts[key] += 1
            for name in AMOUNTS:
                amount = Decimal(str(row[name]))
                if not amount.is_finite() or amount < 0:
                    raise ValueError("invalid frozen journal amount")
                totals[key][name] += amount
        result = []
        for key, batch in sorted(declared.items()):
            actual = totals[key]
            if counts[key] != batch["line_count"] or any(
                actual[name] != batch[f"total_{name}"] for name in AMOUNTS
            ):
                raise ValueError("batch counts or figures differ from frozen journal lines")
            if any(
                actual[f"debit_{basis}"] != actual[f"credit_{basis}"]
                for basis in ("txn", "functional")
            ):
                raise ValueError("unbalanced historical journal batch")
            result.append(
                {
                    **{name: batch[name] for name in BATCH_FIELDS},
                    "run_no": batch["run_no"],
                    "run_state_at_cutoff": batch["run_state"],
                    "frozen_line_count": counts[key],
                    "balanced": True,
                }
            )
        return result
    except (KeyError, ValueError, TypeError, InvalidOperation) as error:
        raise Problem(
            "validation-failed", f"Invalid historical journal register: {error}"
        ) from error


def collect(uow: UnitOfWork, selection: SourceSelection) -> tuple[PackFile, ...]:
    if "contract.read" not in uow.principal.permissions:
        raise Problem("forbidden")
    if selection.lock is None:
        raise Problem("validation-failed", "A CLOSE source selection is required.")
    require_for_entity(uow.ctx, "contract.read", selection.lock.entity_id)
    source = evidence_close.read_locked(uow, selection)
    scope, cutoff = source.scope, source.record["cutoff_known_at"]
    certification = evidence_certification.verified_gates(
        source.record["certification"], locked_at=source.record["created_at"]
    )
    saved = [
        row.model_dump(mode="json")
        for row in certification
        if row.gate_check_code
        in {
            gates.JE_BALANCED,
            gates.JE_COMPLETE,
        }
    ]
    runs = [
        dict(row)
        for row in uow.session.execute(
            select(journal_run)
            .where(
                journal_run.c.tenant_id == selection.tenant_id,
                journal_run.c.entity_id == scope.entity_id,
                journal_run.c.book_code == scope.book_code,
                journal_run.c.period_id == scope.period_id,
                journal_run.c.created_at <= cutoff,
            )
            .order_by(journal_run.c.id)
        ).mappings()
    ]
    batches = [
        dict(row)
        for row in uow.session.execute(
            select(journal_batch)
            .where(
                journal_batch.c.tenant_id == selection.tenant_id,
                journal_batch.c.journal_run_id.in_([run["id"] for run in runs]),
                journal_batch.c.created_at <= cutoff,
            )
            .order_by(journal_batch.c.id)
        ).mappings()
    ]
    histories = je_population._transitions(
        uow.session,
        [run["id"] for run in runs],
        {batch["id"]: batch["journal_run_id"] for batch in batches},
    )
    active = {}
    cancelled = []
    for run in runs:
        state = je_population.state_as_of(
            {
                "run_no": run["run_no"],
                "run_state": run["state"],
                **{
                    f"run_{field}": run[field]
                    for field in (
                        "updated_at",
                        "approved_at",
                        "exported_at",
                        "acknowledged_at",
                        "cancelled_at",
                    )
                },
                "batch_acknowledged_at": None,
            },
            cutoff,
            histories.get(run["id"], ()),
        )
        if state.cancelled:
            cancelled.append(run["id"])
        else:
            active[run["id"]] = {**run, "state_at_cutoff": state.run_state}
    if not active:
        raise Problem("validation-failed", "The certified close has no historical journal run.")
    declared = []
    for batch in batches:
        batch_run = active.get(batch["journal_run_id"])
        if batch_run is None:
            continue
        if (batch["entity_id"], batch["book_code"], batch["period_id"]) != (
            scope.entity_id,
            scope.book_code,
            scope.period_id,
        ):
            raise Problem(
                "validation-failed", "A historical journal batch differs from the lock scope."
            )
        declared.append(
            {**batch, "run_no": batch_run["run_no"], "run_state": batch_run["state_at_cutoff"]}
        )
    frozen = next(report for report in source.reports if report.report_code == "je_population")
    population = locked.report_data(frozen.dataset).rows
    for row in population:
        if (row["entity_code"], row["book"], row["period_key"]) != (
            scope.entity_code,
            scope.book_code,
            scope.period_key,
        ):
            raise Problem("validation-failed", "A frozen journal line differs from the lock scope.")
    register = checked_batches(population, declared)
    for run in active.values():
        members = [row for row in register if row["journal_run_id"] == run["id"]]
        if (
            sum(row["line_count"] for row in members) != run["line_count"]
            or any(row["functional_currency"] != run["functional_currency"] for row in members)
            or any(
                sum((row[f"total_{name}_functional"] for row in members), Decimal(0))
                != run[f"total_{name}_functional"]
                for name in ("debit", "credit")
            )
        ):
            raise Problem("validation-failed", "Historical journal run and batch totals disagree.")
    return (
        PackFile(
            "journals/batch_register.json",
            canonical_bytes(
                {
                    "period_lock_id": scope.lock_id,
                    "cutoff_known_at": cutoff,
                    "snapshot_id": frozen.snapshot_id,
                    "snapshot_sha256": frozen.dataset.file_sha256,
                    "certification": saved,
                    "cancelled_run_ids_at_cutoff": cancelled,
                    "runs": [
                        {
                            **{field: run[field] for field in RUN_FIELDS},
                            "state_at_cutoff": run["state_at_cutoff"],
                        }
                        for run in active.values()
                    ],
                    "batches": register,
                }
            ),
            report_run_id=frozen.report_run_id,
        ),
    )
