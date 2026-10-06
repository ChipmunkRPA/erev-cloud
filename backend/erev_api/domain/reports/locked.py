"""As-locked report runs (ENGINE_SPEC_B S15-R-19 rev 1.31; supervisor ruling D-98 candidate 96;
BUILD_SPEC CLO-8; 04 T-RPT-02 rev 1.53; SCREENS_B RV-04 rev 1.17).

A run given ``period_lock_id`` reads the immutable ``lock_snapshot`` dataset of its report's E-64
kind (the §15.2.7 kinds table, ``SNAPSHOT_KIND_BY_REPORT``) and no live table:

- the CSV output is the frozen rows rendered through the export formula guard (REQ-SEC-011;
  ``export_csv``; RPS-SNAP A4 13.1): every cell guarded by its DECLARED DS-FMT-25 kind (text kinds
  guarded, machine kinds never — Codex 1739 §3 (c)); byte-identical to the frozen file — so
  ``output_sha256`` equals the snapshot's ``file_sha256`` — whenever no text cell begins with a
  formula trigger; otherwise ``output_sha256`` is the served bytes' hash while the frozen
  ``file_sha256`` remains the dataset's identity (verified first); ``row_count`` and
  ``control_totals`` are the snapshot's (a rerun from the same snapshot reproduces all of them,
  CTL-029);
- JSON, XLSX and PDF render the frozen rows as text-kind columns under the frozen header, each row
  keyed by the dataset's own S15-R-18 ``row_key`` column (the engine's sort key, written first).

It refuses by name and never falls back to live data or to a live label when the report has no
lock dataset kind, when the lock holds no snapshot of that kind, when the stored bytes do not hash
to ``file_sha256`` (S15-INV-06), when the row count differs from the snapshot's or when the
``row_key`` column is missing. A run without ``period_lock_id`` is untouched.

The record a run names is a ``LOCK`` (S15-R-19 rev 1.167; 04 §16.9 rev 1.301; item
PERMLOCK-DATASETS-1). A ``REOPEN`` and a ``PERMANENT_LOCK`` record freeze nothing (T-CLS-05), and
a permanently locked period's current record is its ``PERMANENT_LOCK``: a run that named it was
created, queued and ended ``FAILED`` on the missing dataset (measured on 2026-10-02) — every
as-locked report of a period that is final. Such a record is refused when the run is created, and
when a stored run that names one is rerun, by a sentence that names the ``LOCK`` whose datasets
stand for the period where one does (``close.lock_records``; API-S-Period ``dataset_lock``).
"""

from __future__ import annotations

import csv
import hashlib
import io
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import legal_entity, lock_snapshot, period, period_lock
from erev_api.domain.close import lock_records
from erev_api.domain.reports.outputs import ROW_KEY, Column, ReportData
from erev_api.domain.reports.outputs.csv import export_cell
from erev_api.enums import LockKind
from erev_api.files.store import open_file
from erev_api.problems import Problem, ProblemError

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from erev_api.uow import UnitOfWork

RULE: Final = "S15-R-19"
FIELD: Final = "parameters.period_lock_id"
# ENGINE_SPEC_B §15.2.7: snapshot kind → source report code, inverted.
SNAPSHOT_KIND_BY_REPORT: Final[Mapping[str, str]] = {
    "revenue_waterfall": "WATERFALL",
    "contract_balances": "CONTRACT_BALANCES",
    "contract_balance_rollforward": "CONTRACT_BALANCE_ROLLFORWARD",
    "rpo": "RPO",
    "rpo_rollforward": "RPO_ROLLFORWARD",
    "disaggregation": "DISAGGREGATION",
    "revenue_from_prior_period_obligations": "PRIOR_PERIOD_POB_REVENUE",
    "contract_cost_rollforward": "COST_ROLLFORWARD",
    "je_population": "JE_POPULATION",
    "out_of_period_register": "OUT_OF_PERIOD_REGISTER",
    "modification_register": "MODIFICATION_REGISTER",
    "manual_adjustment_register": "MANUAL_ADJUSTMENT_REGISTER",
}
NO_DATASET: Final = (
    "{code} has no lock dataset (E-64): an as-locked run of this report is not supported; run it "
    "current (known_at) instead."
)
SNAPSHOT_MISSING: Final = "Lock {lock} holds no {kind} dataset for {code}."
HASH_MISMATCH: Final = (
    "The stored {kind} dataset of lock {lock} does not hash to its file_sha256 (S15-INV-06)."
)
ROW_COUNT_MISMATCH: Final = (
    "The stored {kind} dataset of lock {lock} holds {actual} rows; the snapshot records {expected}."
)
KEY_MISSING: Final = "The {kind} dataset of lock {lock} lacks the S15-R-18 {column} column."
EXPLAIN_LOCKED: Final = (
    "Cell explanation reads live contributors; an as-locked run has none. Run the report current "
    "to explain a cell."
)
# CLO8-SCOPE-R1 (S15-R-19 rev 1.31): the scope of an as-locked run is the lock's entity, book and
# period; only these selectors, the lock, known_at and its stored read basis known_at_basis
# (F-RPS-CUTOFF-R1, 04 §16.9 rev 1.54: a stored run parameter, not a selector — it never widens or
# changes the frozen dataset's scope) are admitted on such a run.
PERIOD_KEYS: Final = ("period_key", "from_period_key", "to_period_key")
SELECTOR_KEYS: Final = ("entity_codes", "book", *PERIOD_KEYS)
ADMITTED_KEYS: Final = frozenset({"period_lock_id", "known_at", "known_at_basis", *SELECTOR_KEYS})
NOT_A_LOCK_SELECTOR: Final = (
    "{key} cannot be applied to an as-locked run: the frozen {kind} dataset of lock {lock} carries "
    "no such selector. Run the report current to apply it."
)
ENTITY_MISMATCH: Final = (
    "entity_codes must be [{entity}], the entity of lock {lock}: its frozen dataset holds that "
    "entity only."
)
BOOK_MISMATCH: Final = "book must be {book}, the book of lock {lock}."
PERIOD_MISMATCH: Final = "{key} must be {period}, the period of lock {lock}."
RUN_SCOPE_INCONSISTENT: Final = (
    "Report run {run_no} is an as-locked run whose persisted scope differs from its lock's; it is "
    "served to no one (S15-R-19)."
)
RUN_LOCK_MISSING: Final = "Lock {lock} of report run {run_no} is not in this workspace."
# S15-R-19 rev 1.167 (04 §16.9 rev 1.301; item PERMLOCK-DATASETS-1): only a LOCK record freezes
# datasets (T-CLS-05). A run that names another record is refused where it is created: the record
# and its kind, then the LOCK whose datasets stand for the period, or that none stands.
RECORD_WORDS: Final[Mapping[str, str]] = MappingProxyType(
    {
        LockKind.REOPEN.value: "a reopen record",
        LockKind.PERMANENT_LOCK.value: "the permanent lock",
    }
)
NOT_A_LOCK: Final = "Lock {lock} is {record} of {period}: it froze no dataset (E-63 {kind})."
PASS_DATASET_LOCK: Final = (
    "The datasets of {period} are those of lock {dataset_lock}; pass that lock."
)
NO_DATASET_LOCK: Final = (
    "No lock's datasets stand for {period}: run the report current (known_at) instead, or pass "
    "a LOCK record of the period (GET /periods/{{id}}/locks)."
)


class LockedRefusal(Problem):
    """A refusal by name of the as-locked branch: 422 ``validation-failed`` on
    ``parameters.period_lock_id`` with rule ``S15-R-19``."""

    def __init__(self, message: str) -> None:
        super().__init__(
            "validation-failed",
            message,
            errors=[ProblemError(field=FIELD, rule_id=RULE, message=message)],
        )


@dataclass(frozen=True, slots=True)
class LockedDataset:
    """One frozen dataset as stored: the T-CLS-05 columns and the bytes read back."""

    lock_id: UUID
    kind: str
    file_id: UUID
    file_sha256: str
    row_count: int
    control_totals: Mapping[str, Any]
    content: bytes


@dataclass(frozen=True, slots=True)
class LockScope:
    """What a period lock froze: one entity, one book, one period (T-CLS-04). ``kind`` is the
    record's E-63 kind as ``lock_scope`` read it: a ``LOCK`` froze the period's datasets, a
    ``REOPEN`` or a ``PERMANENT_LOCK`` record froze nothing (T-CLS-05)."""

    lock_id: UUID
    entity_id: UUID
    entity_code: str
    book_code: str
    period_id: UUID
    period_key: str
    kind: str = LockKind.LOCK.value


# --- pure -----------------------------------------------------------------------------------------


def snapshot_kind_of(report_code: str) -> str | None:
    """The E-64 kind whose dataset an as-locked run of ``report_code`` reads; None for a report
    without a lock dataset."""
    return SNAPSHOT_KIND_BY_REPORT.get(report_code)


def not_a_lock(scope: LockScope, dataset_lock_id: UUID | None) -> str | None:
    """The refusal of a run that names ``scope``'s record, or None for a ``LOCK`` record: the
    record, what it is and its period, then the ``LOCK`` whose datasets stand for the period
    (``dataset_lock_id``) or, where none stands, what the caller can do instead."""
    if scope.kind == LockKind.LOCK.value:
        return None
    named = NOT_A_LOCK.format(
        lock=scope.lock_id,
        record=RECORD_WORDS[scope.kind],
        period=scope.period_key,
        kind=scope.kind,
    )
    if dataset_lock_id is None:
        return f"{named} {NO_DATASET_LOCK.format(period=scope.period_key)}"
    passed = PASS_DATASET_LOCK.format(period=scope.period_key, dataset_lock=dataset_lock_id)
    return f"{named} {passed}"


def verify(dataset: LockedDataset) -> LockedDataset:
    """The stored bytes hash to the snapshot's ``file_sha256`` and hold its ``row_count`` rows;
    ``LockedRefusal`` otherwise."""
    if hashlib.sha256(dataset.content).hexdigest() != dataset.file_sha256:
        raise LockedRefusal(HASH_MISMATCH.format(kind=dataset.kind, lock=dataset.lock_id))
    headers, rows = _rows(dataset.content)
    if len(rows) != dataset.row_count:
        raise LockedRefusal(
            ROW_COUNT_MISMATCH.format(
                kind=dataset.kind,
                lock=dataset.lock_id,
                actual=len(rows),
                expected=dataset.row_count,
            )
        )
    return dataset


def _rows(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    rows = [dict(row) for row in reader]
    return list(reader.fieldnames or []), rows


def report_data(dataset: LockedDataset) -> ReportData:
    """The frozen rows as ``ReportData``: text-kind columns under the frozen header (the
    ``row_key`` column becomes each row's key, not a column), the snapshot's control totals and no
    tie-outs (the freeze evaluated them). ``LockedRefusal`` when the header lacks ``row_key``."""
    headers, rows = _rows(dataset.content)
    if ROW_KEY not in headers:
        raise LockedRefusal(
            KEY_MISSING.format(kind=dataset.kind, lock=dataset.lock_id, column=ROW_KEY)
        )
    shown = tuple(header for header in headers if header != ROW_KEY)
    columns = tuple(Column(header, header, "text") for header in shown)
    keyed = tuple(
        {
            ROW_KEY: str(row.get(ROW_KEY) or ""),
            **{header: str(row.get(header) or "") for header in shown},
        }
        for row in rows
    )
    return ReportData(columns=columns, rows=keyed, control_totals=dict(dataset.control_totals))


def reconcile_selectors(
    given: Mapping[str, Any], scope: LockScope, properties: Mapping[str, Any], *, kind: str
) -> tuple[dict[str, Any], list[ProblemError]]:
    """The parameters an as-locked run persists, and the findings against the caller's ``given``
    (S15-R-19 rev 1.31, CLO8-SCOPE-R1): every explicit entity, book or period selector must equal
    the lock's, omitted ones are derived from it, and no other parameter is admitted — the frozen
    dataset carries no filter, dimension, view, band or as-of choice. The persisted parameters are
    exactly the lock, ``known_at`` when given, and the lock-derived selectors the report defines."""
    errors: list[ProblemError] = []

    def refuse(key: str, message: str) -> None:
        errors.append(ProblemError(field=f"parameters.{key}", rule_id=RULE, message=message))

    for key in sorted(given):
        if key not in ADMITTED_KEYS:
            refuse(key, NOT_A_LOCK_SELECTOR.format(key=key, kind=kind, lock=scope.lock_id))
    if "entity_codes" in given:
        codes = [str(code) for code in given["entity_codes"]]
        if codes != [scope.entity_code]:
            refuse(
                "entity_codes", ENTITY_MISMATCH.format(entity=scope.entity_code, lock=scope.lock_id)
            )
    if "book" in given and str(given["book"]) != scope.book_code:
        refuse("book", BOOK_MISMATCH.format(book=scope.book_code, lock=scope.lock_id))
    for key in PERIOD_KEYS:
        if key in given and str(given[key]) != scope.period_key:
            refuse(
                key, PERIOD_MISMATCH.format(key=key, period=scope.period_key, lock=scope.lock_id)
            )
    parameters: dict[str, Any] = {"period_lock_id": str(scope.lock_id)}
    if "known_at" in given:
        parameters["known_at"] = given["known_at"]
    if "entity_codes" in properties:
        parameters["entity_codes"] = [scope.entity_code]
    if "book" in properties:
        parameters["book"] = scope.book_code
    for key in PERIOD_KEYS:
        if key in properties:
            parameters[key] = scope.period_key
    return parameters, errors


def run_mismatch(run: Mapping[str, Any], scope: LockScope) -> str | None:
    """The first persisted field of ``run`` that differs from what its lock froze, or None when the
    run's scope is the lock's: the lock itself, ``entity_ids`` (exactly the lock's entity),
    ``book_code``, then the parameters (no key outside the admitted set; the selectors equal)."""
    if UUID(str(run["period_lock_id"])) != scope.lock_id:
        return "period_lock_id"
    if [UUID(str(value)) for value in run["entity_ids"]] != [scope.entity_id]:
        return "entity_ids"
    if run["book_code"] != scope.book_code:
        return "book_code"
    parameters = dict(run["parameters"] or {})
    for key in sorted(parameters):
        if key not in ADMITTED_KEYS:
            return f"parameters.{key}"
    if "entity_codes" in parameters and [str(code) for code in parameters["entity_codes"]] != [
        scope.entity_code
    ]:
        return "parameters.entity_codes"
    if "book" in parameters and str(parameters["book"]) != scope.book_code:
        return "parameters.book"
    for key in PERIOD_KEYS:
        if key in parameters and str(parameters[key]) != scope.period_key:
            return f"parameters.{key}"
    return None


def csv_bytes(dataset: LockedDataset) -> tuple[bytes, str]:
    """The frozen artefact itself: the stored bytes and their hash (= ``file_sha256``), verified."""
    verify(dataset)
    return dataset.content, dataset.file_sha256


def _field(text: str) -> str:
    """RFC 4180 quoting only when needed — the engine encoder's rule (S15-R-18), so a re-serialised
    trigger-free dataset is byte-identical to the frozen file."""
    if any(ch in text for ch in (",", '"', "\n", "\r")):
        return '"' + text.replace('"', '""') + '"'
    return text


def headers_of(dataset: LockedDataset) -> list[str]:
    """The frozen header row (the declared kinds of the export boundary are keyed by it)."""
    return _rows(dataset.content)[0]


def export_csv(dataset: LockedDataset, kinds: Mapping[str, str]) -> tuple[bytes, str]:
    """The CSV OUTPUT of an as-locked run (RPS-SNAP A4 13.1; S15-R-19; Codex 1739 §3 (c)): the
    verified frozen rows re-serialised with the engine's field quoting and ``\n``, every cell
    guarded by its DECLARED DS-FMT-25 kind (``kinds``: header → column kind,
    ``csv_output.export_cell`` — text kinds guarded, machine kinds never; an undeclared header is
    text). The header row is
    written as stored. Byte-identical to the frozen file — hence the hash equals ``file_sha256`` —
    whenever no cell needs the guard; otherwise the served bytes' own hash. The stored artefact is
    never altered: identity lives in the frozen bytes, the guard in the export."""
    verify(dataset)
    headers, rows = _rows(dataset.content)
    lines = [",".join(_field(header) for header in headers)]
    for row in rows:
        lines.append(
            ",".join(
                _field(export_cell(kinds.get(header, "text"), str(row.get(header) or "")))
                for header in headers
            )
        )
    content = ("\n".join(lines) + "\n").encode("utf-8")
    return content, hashlib.sha256(content).hexdigest()


# --- DB-bound -------------------------------------------------------------------------------------


def lock_scope(session: Session, lock_id: UUID) -> LockScope | None:
    """The entity, book and period a lock froze, and the record's kind; None when the lock is
    not in this workspace."""
    row = (
        session.execute(
            select(
                period_lock.c.id,
                period_lock.c.kind,
                period_lock.c.entity_id,
                period_lock.c.book_code,
                period_lock.c.period_id,
                legal_entity.c.code.label("entity_code"),
                period.c.period_key,
            )
            .select_from(period_lock)
            .join(legal_entity, legal_entity.c.id == period_lock.c.entity_id)
            .join(period, period.c.id == period_lock.c.period_id)
            .where(period_lock.c.id == lock_id)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        return None
    return LockScope(
        lock_id=UUID(str(row["id"])),
        entity_id=UUID(str(row["entity_id"])),
        entity_code=str(row["entity_code"]),
        book_code=str(row["book_code"]),
        period_id=UUID(str(row["period_id"])),
        period_key=str(row["period_key"]),
        kind=str(getattr(row["kind"], "value", row["kind"])),
    )


def froze_nothing(session: Session, scope: LockScope) -> str | None:
    """``not_a_lock`` for ``scope``'s record with the ``LOCK`` whose datasets stand for its
    period read from the period's state row (``lock_records.dataset_lock_of``); None, and no
    read, for a ``LOCK`` record."""
    if scope.kind == LockKind.LOCK.value:
        return None
    standing = session.execute(
        lock_records.dataset_lock_of(
            entity_id=scope.entity_id, book_code=scope.book_code, period_id=scope.period_id
        )
    ).scalar_one_or_none()
    return not_a_lock(scope, None if standing is None else UUID(str(standing)))


def assert_run_matches(session: Session, run: Mapping[str, Any]) -> LockScope:
    """Before an as-locked run reads its dataset: the lock exists and the run's persisted scope is
    the lock's (``run_mismatch`` None); ``LockedRefusal`` by name otherwise."""
    lock_id = UUID(str(run["period_lock_id"]))
    scope = lock_scope(session, lock_id)
    if scope is None:
        raise LockedRefusal(RUN_LOCK_MISSING.format(lock=lock_id, run_no=run["report_run_no"]))
    if run_mismatch(run, scope) is not None:
        raise LockedRefusal(RUN_SCOPE_INCONSISTENT.format(run_no=run["report_run_no"]))
    return scope


def locked_dataset(uow: UnitOfWork, *, report_code: str, lock_id: UUID) -> LockedDataset:
    """The lock's snapshot of the report's kind, read back from the store and verified;
    ``LockedRefusal`` by name when the report has no kind or the lock holds no such snapshot."""
    kind = snapshot_kind_of(report_code)
    if kind is None:
        raise LockedRefusal(NO_DATASET.format(code=report_code))
    row = (
        uow.session.execute(
            select(
                lock_snapshot.c.file_id,
                lock_snapshot.c.file_sha256,
                lock_snapshot.c.row_count,
                lock_snapshot.c.control_totals,
            ).where(
                lock_snapshot.c.period_lock_id == lock_id,
                lock_snapshot.c.snapshot_kind == kind,
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise LockedRefusal(SNAPSHOT_MISSING.format(lock=lock_id, kind=kind, code=report_code))
    file_id = UUID(str(row["file_id"]))
    _, stream = open_file(uow.session, file_id, files=uow.files, keyring=uow.keyring)
    with stream:
        content = stream.read()
    return verify(
        LockedDataset(
            lock_id=lock_id,
            kind=kind,
            file_id=file_id,
            file_sha256=str(row["file_sha256"]),
            row_count=int(row["row_count"]),
            control_totals=dict(row["control_totals"] or {}),
            content=content,
        )
    )
