"""A period end that is locked at the run's cutoff is the lock's (ENGINE_SPEC_B S15-R-20 rev
1.168; 04 §16.9 rev 1.313; item RPT-ROLLFWD-LOCKED-CLOSING-1, the supervisor's rulings of
2026-10-02; ruling R-72 (b)).

``contract_balance_rollforward`` and ``contract_balances`` read the balances at a period's end
through ``tie_outs.balances_at``. Until this rule both ends of a run were the balances of the
contract versions known at the run's cutoff, while the movements are the lines by posting period:
after a contract was activated late, the closing of the locked months held it by its schedule and
their movements did not, and the run of the following period counted it in its opening and again
in its lines. The balances of a locked period do not move with what is learned later.

*Which lock.* The ``LOCK`` record whose datasets stand for the entity, book and period
(``lock_records.dataset_lock_of``, the one statement of that rule), and only where its
``cutoff_known_at`` is not later than the run's cutoff. Else the end is read from the versions: a
period never locked, a period under a ``REOPEN`` record, a run as of an instant before the lock's
cutoff — and a historical run dated under an earlier lock of a period since reopened and locked
again, which reads the versions at its own cutoff. A ``LOCK`` record that names no manifest
froze nothing and is read from the versions too (``stands``): the product never writes one.

*What is read.* Per contract the row of the lock's ``CONTRACT_BALANCES`` dataset: the
roll-forward dataset states one balance role per contract and the three balances as totals. The
three roll-forward balances of the rows read are compared per currency with the closing control
totals of the same lock's ``CONTRACT_BALANCE_ROLLFORWARD`` dataset.

*Refused by name* (``LockedEndRefused``; nothing is served and the versions' figures never stand
in for a lock's): a lock that holds no such dataset, a file that fails its hash or its row count,
two datasets of one lock that differ, a row of a contract the read does not hold.

*What a run records* (S15-R-24): per period end asked, the lock and the two files' hashes, or
that no lock stood — evidence kind ``locked_ends``. A bound run reads those locks and no other,
whatever was reopened or locked since; a binding without the kind was recorded before this rule
and is read from the versions it bound.

The freeze of a period builds its datasets through the same two builders before its own record is
written (``close.commands``): it reads its own period's end from the versions and the opening of
its roll-forward from the datasets of the period before (05 PERF-25).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import lock_snapshot
from erev_api.domain.close import lock_records
from erev_api.domain.reports import locked, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.outputs import ROW_KEY
from erev_api.domain.reports.tie_outs import ZERO, LockedEnd, LockedRow, PeriodRef
from erev_api.enums import SnapshotKind
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork

RULE: Final = "S15-R-20"
EVIDENCE: Final = "locked_ends"  # evidence kind: "<entity id>|<period id>" → the lock read, or None
BALANCES_REPORT: Final = "contract_balances"
BALANCES_KIND: Final = SnapshotKind.CONTRACT_BALANCES.value
ROLLFORWARD_KIND: Final = SnapshotKind.CONTRACT_BALANCE_ROLLFORWARD.value
# The balances the roll-forward dataset states as closing control totals (``closing_<balance>``).
CHECKED: Final = tie_outs.ROLLFORWARD_BALANCES
CONTRACT: Final = "contract_external_id"
CURRENCY: Final = "currency"
# Identity and label columns of the dataset: every other column is a money measure.
NOT_A_MEASURE: Final = frozenset({ROW_KEY, CONTRACT, "customer_name", "entity_code", CURRENCY})
RECORDED: Final = ((BALANCES_KIND, "balances_sha256"), (ROLLFORWARD_KIND, "rollforward_sha256"))

NO_DATASET: Final = (
    "Lock {lock} of period {period} holds no {kind} dataset. The balances of a locked period end "
    "are the lock's and are not read from the contract versions in its place."
)
UNREADABLE: Final = (
    "The {kind} dataset of lock {lock} of period {period} cannot be read as frozen: {reason}"
)
DIFFER: Final = (
    "The datasets of lock {lock} of period {period} do not agree: {balance} is {balances} "
    "{currency} in its CONTRACT_BALANCES dataset and {rollforward} {currency} as the closing of "
    "its CONTRACT_BALANCE_ROLLFORWARD dataset."
)
UNKNOWN_CONTRACT: Final = (
    "The CONTRACT_BALANCES dataset of lock {lock} of period {period} names contract {contract}, "
    "which the run does not read for this entity."
)
NOT_AS_RECORDED: Final = (
    "The {kind} dataset of lock {lock} of period {period} is not the file this run recorded "
    "(S15-R-24). Run the report current instead."
)
CELL: Final = "row {row}: column {column} holds {text!r}, which is not an amount"


class LockedEndRefused(Problem):
    """The named refusal of a locked period end that cannot be read from its lock: 422
    ``validation-failed`` with rule ``S15-R-20`` on ``balances[<entity code>@<period key>]``."""

    def __init__(self, entity_code: str, period_key: str, message: str) -> None:
        super().__init__(
            "validation-failed",
            message,
            errors=[
                ProblemError(
                    field=f"balances[{entity_code}@{period_key}]", rule_id=RULE, message=message
                )
            ],
        )


# --- pure -----------------------------------------------------------------------------------------


def rows_of(rows: Sequence[Mapping[str, str]]) -> dict[str, LockedRow]:
    """The dataset's rows by contract external id: every column that is not an identity or a
    label is a money measure, an empty cell 0. ``ValueError`` names a cell that is no amount, a
    row without a contract and a contract stated twice."""
    found: dict[str, LockedRow] = {}
    for row in rows:
        key = str(row.get(ROW_KEY) or "")
        contract = str(row.get(CONTRACT) or "")
        if not contract:
            raise ValueError(f"row {key}: no {CONTRACT}")
        if contract in found:
            raise ValueError(f"row {key}: contract {contract} is stated twice")
        values: dict[str, Decimal] = {}
        for column, text in row.items():
            if column in NOT_A_MEASURE:
                continue
            try:
                values[column] = Decimal(text) if text else ZERO
            except InvalidOperation as error:
                raise ValueError(CELL.format(row=key, column=column, text=text)) from error
        found[contract] = LockedRow(currency=str(row.get(CURRENCY) or ""), values=values)
    return found


def differences(
    rows: Mapping[str, LockedRow], control_totals: Mapping[str, Any]
) -> list[tuple[str, str, Decimal, Decimal]]:
    """Where the rows' three roll-forward balances, summed per currency, differ from the closing
    control totals of the lock's roll-forward dataset: (balance, currency, the rows' sum, the
    closing total). A currency either side leaves out counts as 0."""
    found: list[tuple[str, str, Decimal, Decimal]] = []
    for balance in CHECKED:
        summed: dict[str, Decimal] = {}
        for row in rows.values():
            tie_outs.add(summed, row.currency, row.values.get(balance, ZERO))
        stated = {
            str(code): Decimal(str(amount))
            for code, amount in dict(control_totals.get(f"closing_{balance}") or {}).items()
        }
        for currency in sorted(set(summed) | set(stated)):
            ours, theirs = summed.get(currency, ZERO), stated.get(currency, ZERO)
            if ours != theirs:
                found.append((balance, currency, ours, theirs))
    return found


def stands(manifest_sha256: str | None, frozen_at: datetime | None, cutoff: datetime) -> bool:
    """Whether the ``LOCK`` record ``dataset_lock_of`` names is read by a run at ``cutoff``: it
    froze its datasets — it names their manifest — at or before the run's cutoff.

    The two instants can be equal: a cutoff is the later of an application instant and the
    transaction's timestamp (``freeze.freeze_cutoff``, ``tie_outs.effective_cutoff``), so under
    an application clock that runs ahead of the server's — every frozen-clock world — a run
    started after the lock carries the lock's own cutoff (measured in the witness world). A run
    that finds the record at its own cutoff was started after the lock was taken, and reads it;
    the freeze of the period itself is not met, since its record is written after its datasets.

    A ``LOCK`` record without a manifest froze nothing, and for it no datasets stand: the end is
    read from the versions (the supervisor's ruling of 2026-10-02). The product never writes
    one — the lock decision and the sandbox replay both write the manifest with the twelve
    datasets, and the seeds lock through ``request_lock``; the one place it is met is a test
    fixture (``support.close_world.periods_closed_before``: "No gate is evaluated and nothing is
    frozen"). A record that NAMES a manifest and lacks a dataset is refused by name."""
    return manifest_sha256 is not None and frozen_at is not None and frozen_at <= cutoff


def key_of(entity_id: UUID, period: PeriodRef) -> str:
    return f"{entity_id}|{period.id}"


def recorded(end: LockedEnd) -> dict[str, str]:
    """What a run records of a lock it read (S15-R-24)."""
    return {
        "lock_id": str(end.lock_id),
        "frozen_at": end.frozen_at.isoformat(),
        "balances_sha256": end.balances_sha256,
        "rollforward_sha256": end.rollforward_sha256,
    }


# --- the reader -----------------------------------------------------------------------------------


class Reader:
    """The locked period ends of one build (``tie_outs.LockedEnds``): each end is resolved once,
    recorded with the run on a live build and read from the run's record on a bound one.
    ``entity_codes`` are the codes the build consumed, by entity id, for the refusal's field."""

    def __init__(
        self,
        uow: UnitOfWork,
        params: ReportParams,
        *,
        book_code: str,
        cutoff: datetime,
        entity_codes: Mapping[UUID, str],
    ) -> None:
        self._uow = uow
        self._params = params
        self._book_code = book_code
        self._cutoff = cutoff
        self._entity_codes = entity_codes
        self._ends: dict[str, LockedEnd | None] = {}

    def at(self, entity_id: UUID, period: PeriodRef) -> LockedEnd | None:
        """The lock's statement of the entity's balances at the end of ``period``; None where the
        end is read from the versions."""
        key = key_of(entity_id, period)
        if key not in self._ends:
            self._ends[key] = self._resolve(entity_id, period, key)
            # the whole record so far: the collector keeps one value a kind (S15-R-24)
            tie_outs.record_evidence(
                self._params,
                EVIDENCE,
                {
                    name: (None if end is None else recorded(end))
                    for name, end in sorted(self._ends.items())
                },
            )
        return self._ends[key]

    def unknown(self, entity_id: UUID, period: PeriodRef, contract: str) -> Problem:
        """The refusal of a dataset row whose contract the run's read does not hold."""
        end = self._ends[key_of(entity_id, period)]
        assert end is not None
        return self._refused(
            entity_id,
            period,
            UNKNOWN_CONTRACT.format(lock=end.lock_id, period=period.key, contract=contract),
        )

    def _resolve(self, entity_id: UUID, period: PeriodRef, key: str) -> LockedEnd | None:
        binding = self._params.binding
        if binding is None:
            standing = self._standing(entity_id, period)
            return None if standing is None else self._read(entity_id, period, *standing)
        bound = binding.evidence.get(EVIDENCE)
        if bound is None:
            return None  # a run recorded before the rule: the versions it bound
        if key not in bound:
            raise tie_outs.missing_input(EVIDENCE, [key])
        entry = bound[key]
        if entry is None:
            return None
        end = self._read(
            entity_id,
            period,
            UUID(str(entry["lock_id"])),
            datetime.fromisoformat(str(entry["frozen_at"])),
        )
        for kind, name in RECORDED:
            if getattr(end, name) != str(entry[name]):
                raise self._refused(
                    entity_id,
                    period,
                    NOT_AS_RECORDED.format(kind=kind, lock=end.lock_id, period=period.key),
                )
        return end

    def _standing(self, entity_id: UUID, period: PeriodRef) -> tuple[UUID, datetime] | None:
        """The ``LOCK`` whose datasets stand for the period (``lock_records.dataset_lock_of``,
        with two more columns of the record it names), where a run at this cutoff reads it."""
        named = lock_records.DATASET_LOCK.c
        row = self._uow.session.execute(
            lock_records.dataset_lock_of(
                entity_id=entity_id, book_code=self._book_code, period_id=period.id
            ).add_columns(named.cutoff_known_at, named.snapshot_manifest_sha256)
        ).one_or_none()
        if row is None or not stands(
            row.snapshot_manifest_sha256, row.cutoff_known_at, self._cutoff
        ):
            return None
        return UUID(str(row.id)), row.cutoff_known_at

    def _read(
        self, entity_id: UUID, period: PeriodRef, lock_id: UUID, frozen_at: datetime
    ) -> LockedEnd:
        session = self._uow.session
        try:
            dataset = locked.locked_dataset(self._uow, report_code=BALANCES_REPORT, lock_id=lock_id)
            data = locked.report_data(dataset)
        except locked.LockedRefusal as refused:
            held = session.execute(
                select(lock_snapshot.c.id).where(
                    lock_snapshot.c.period_lock_id == lock_id,
                    lock_snapshot.c.snapshot_kind == BALANCES_KIND,
                )
            ).first()
            message = (
                NO_DATASET.format(lock=lock_id, period=period.key, kind=BALANCES_KIND)
                if held is None
                else UNREADABLE.format(
                    kind=BALANCES_KIND, lock=lock_id, period=period.key, reason=refused.detail
                )
            )
            raise self._refused(entity_id, period, message) from refused
        closing = (
            session.execute(
                select(lock_snapshot.c.file_sha256, lock_snapshot.c.control_totals).where(
                    lock_snapshot.c.period_lock_id == lock_id,
                    lock_snapshot.c.snapshot_kind == ROLLFORWARD_KIND,
                )
            )
            .mappings()
            .one_or_none()
        )
        if closing is None:
            raise self._refused(
                entity_id,
                period,
                NO_DATASET.format(lock=lock_id, period=period.key, kind=ROLLFORWARD_KIND),
            )
        try:
            rows = rows_of([{str(k): str(v) for k, v in row.items()} for row in data.rows])
        except ValueError as error:
            raise self._refused(
                entity_id,
                period,
                UNREADABLE.format(
                    kind=BALANCES_KIND, lock=lock_id, period=period.key, reason=str(error)
                ),
            ) from error
        apart = differences(rows, dict(closing["control_totals"] or {}))
        if apart:
            balance, currency, ours, theirs = apart[0]
            raise self._refused(
                entity_id,
                period,
                DIFFER.format(
                    lock=lock_id,
                    period=period.key,
                    balance=balance,
                    currency=currency,
                    balances=ours,
                    rollforward=theirs,
                ),
            )
        return LockedEnd(
            lock_id=lock_id,
            period_key=period.key,
            frozen_at=frozen_at,
            balances_sha256=dataset.file_sha256,
            rollforward_sha256=str(closing["file_sha256"]),
            rows=rows,
        )

    def _refused(self, entity_id: UUID, period: PeriodRef, message: str) -> LockedEndRefused:
        code = self._entity_codes.get(entity_id, str(entity_id))
        return LockedEndRefused(code, period.key, message)
