"""The re-lock diff report (BUILD_SPEC CLO-7; PRD BR-CLS-07; REQ-CLS-011; ENGINE_SPEC_B S15-R-18,
S15-R-20; 04 T-CLS-04 ``diff_report_file_id`` rev 1.25; supervisor rulings D-98 81, D-98 85 and
D-98 87).

After a reopen, the lock that closes the period again compares the previous ``LOCK`` with the new
one and stores the comparison as a ``REPORT_OUTPUT`` JSON file in the lock transaction:

- both lock ids and their S15-R-19 manifests;
- per E-64 snapshot kind the previous and current ``file_sha256`` and ``row_count`` and, by row key,
  the rows added, removed and changed; every non-key column of a changed row is compared — a
  declared measure column of the kind (D-98 87) reports previous, current and ``delta`` (a measure
  change), any other column previous and current (an attribute change) whatever its values look
  like — and the report counts measure and attribute changes
  separately, so a name-only change is one ``changed`` row with no money movement, never a removal
  plus an addition;
- the certification (T-CLS-04 ``certification``) per gate before and after.

**Row keys (D-98 81).** ``KEY_COLUMNS`` is an explicit table, one entry per E-64 kind, naming the
CSV header columns that carry the ENGINE_SPEC_B §15.2.7 row key of that kind. Where a kind's header
carries `entity_code` and / or a book column (or the report's equivalent) they are part of that
kind's key, as §15.2.7 lists entity and book; a header that lacks them keeps its entry with the
note saying so (a lock is per entity, book and period, so nothing is lost); the provenance of each
entry is stated (``builder``: the report builder on this tree; ``design``: the SCREENS_B field
names, to be confirmed against the EDS-6 dataset header when it lands). Nothing is inferred from
headers or values: a dataset whose header lacks a key column, a kind outside the table or a key
that repeats within one dataset is a refusal by name (``RelockDiffRefusal`` with ``code``
``RELOCK_DIFF_KEY_MISSING``, ``RELOCK_DIFF_KIND_UNKNOWN``, ``RELOCK_DIFF_KEY_DUPLICATE`` or, for a
declared measure whose non-empty value is not a decimal, ``RELOCK_DIFF_MEASURE_NOT_DECIMAL``),
never a fallback; the lock transaction rolls back with it. The key columns used are stated in the
report (``key_columns``).

``diff`` is pure over the two sides' dataset bytes; ``report`` reads the sides through the lock
transaction's session and file store and ``store_report`` writes the file.
"""

from __future__ import annotations

import csv
import io
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import select

from erev_api.db.tables import lock_snapshot, period_lock
from erev_api.enums import FilePurpose, SnapshotKind
from erev_api.files.store import open_file, store_file
from erev_api.problems import Problem

if TYPE_CHECKING:
    from erev_api.domain.close.snapshots import DatasetFile
    from erev_api.uow import UnitOfWork

FORMAT: Final = "erev.relock_diff.v1"
MEDIA_TYPE: Final = "application/json"
DECIMAL: Final = re.compile(r"^-?\d+(\.\d+)?$")
KIND_UNKNOWN: Final = "RELOCK_DIFF_KIND_UNKNOWN"
KEY_MISSING: Final = "RELOCK_DIFF_KEY_MISSING"
KEY_DUPLICATE: Final = "RELOCK_DIFF_KEY_DUPLICATE"
MEASURE_NOT_DECIMAL: Final = "RELOCK_DIFF_MEASURE_NOT_DECIMAL"


class RelockDiffRefusal(RuntimeError):
    """The diff refuses by name (D-98 81): ``code`` names the rule, ``kind`` the dataset."""

    def __init__(self, code: str, kind: str, detail: str) -> None:
        self.code = code
        self.kind = kind
        super().__init__(f"{code}: {kind}: {detail}")


@dataclass(frozen=True, slots=True)
class KeySpec:
    """The header columns carrying one kind's §15.2.7 row key, where the names come from, and the
    kind's declared measure columns (D-98 87): ``measures`` by name and ``measure_patterns`` by
    header pattern for the report's dynamic money columns (period cells, RPO bands). Every other
    non-key column is an attribute whatever its values look like."""

    columns: tuple[str, ...]
    source: str  # "builder" (report builder on this tree) or "design" (SCREENS_B field names)
    note: str
    measures: tuple[str, ...] = ()
    measure_patterns: tuple[str, ...] = ()

    def is_measure(self, header: str) -> bool:
        return header in self.measures or any(
            re.fullmatch(pattern, header) is not None for pattern in self.measure_patterns
        )


# ENGINE_SPEC_B §15.2.7 row keys as CSV headers (entity and book are constant within a dataset).
KEY_COLUMNS: Final[Mapping[str, KeySpec]] = {
    SnapshotKind.WATERFALL.value: KeySpec(
        ("entity_code", "contract_external_id", "obligation_key", "period_key"),
        "builder",
        "§15.2.7 (entity, contract, obligation, period key); `revenue_waterfall` builder columns "
        "plus the T-REF-06 `period_key` of the long-form dataset row; `entity_code` is in the key, "
        "no book column",
        measures=("scheduled", "recognised", "awaiting_trigger", "total"),
        measure_patterns=(r"period:.+",),
    ),
    SnapshotKind.CONTRACT_BALANCES.value: KeySpec(
        ("entity_code", "contract_external_id"),
        "builder",
        "§15.2.7 (entity, contract); `contract_balances` builder columns; `entity_code` is in the "
        "key, no book column",
        measures=(
            "contract_liability",
            "contract_liability_current",
            "contract_liability_noncurrent",
            "contract_asset",
            "contract_asset_current",
            "unbilled_receivable",
            "accounts_receivable",
            "refund_liability",
            "return_asset",
            "deposit_liability",
            "customer_incentive_asset",
            "consideration_payable",
            "cost_asset_carrying",
            "loss_provision",
        ),
    ),
    SnapshotKind.CONTRACT_BALANCE_ROLLFORWARD.value: KeySpec(
        ("line_code", "contract_external_id", "currency"),
        "builder",
        "§15.2.7 (entity, book, currency, balance, line code); D-98 85: `line_code` (the stable "
        "code the builder writes; `line_label` is a display attribute), the by-contract rows' "
        "`contract_external_id`, `currency`; the balances are measure columns; `section` is a "
        "discriminator, not identity; the header carries neither `entity_code` nor a book column",
        measures=(
            "contract_liability",
            "contract_asset",
            "unbilled_receivable",
            "opening",
            "billings",
            "revenue_from_opening",
            "revenue_from_period_billings",
            "reclassifications",
            "fx_remeasurement",
            "business_combinations",
            "other",
            "closing",
        ),
    ),
    SnapshotKind.RPO.value: KeySpec(
        ("entity_code", "contract_external_id", "obligation_key"),
        "builder",
        "§15.2.7 (entity, contract, obligation); `rpo` builder columns; `section` is a "
        "discriminator, not identity (D-98 85); `entity_code` is in the key, no book column",
        measures=("total", "current", "noncurrent", "excluded_amount", "remaining_duration_months"),
        # rpo.bands_of: within_<b1>_months, months_<a>_to_<b>, after_<bn>_months (CLO-7e)
        measure_patterns=(r"within_\d+_months", r"months_\d+_to_\d+", r"after_\d+_months"),
    ),
    SnapshotKind.RPO_ROLLFORWARD.value: KeySpec(
        ("line_code", "contract_external_id", "currency"),
        "builder",
        "§15.2.7 (entity, book, currency, line code); D-98 85: `line_code` (stable code; "
        "`line_label` is a display attribute), the by-contract rows' `contract_external_id`, "
        "`currency`; `section` is not identity; the header carries neither `entity_code` nor a "
        "book column",
        measures=(
            "rpo",
            "opening",
            "new_contracts",
            "modifications",
            "vc_estimate_changes",
            "late_events",  # ENGINE_SPEC_B S15-R-12 rev 1.161 (item RPT-RPO-ROLLFWD-1)
            "revenue",
            "cancellations",
            "fx",
            "unexplained",
            "closing",
        ),
    ),
    SnapshotKind.DISAGGREGATION.value: KeySpec(
        ("dimension_code", "dimension_value", "timing_code", "currency"),
        "builder",
        "§15.2.7 (entity, dimension code, dimension value); D-98 85: the codes `dimension_code`, "
        "`dimension_value`, `timing_code` (labels `dimension_value_label`, `timing` are display "
        "attributes) and `currency`; the header carries neither `entity_code` nor a book column",
        measures=("total",),
        measure_patterns=(r"period:.+",),
    ),
    SnapshotKind.PRIOR_PERIOD_POB_REVENUE.value: KeySpec(
        ("entity_code", "contract_external_id", "obligation_key"),
        "design",
        "§15.2.7 (entity, contract, obligation) exactly — one row per (performing entity, "
        "contract, obligation); ENG-C4's `revenue_from_prior_period_obligations` builder "
        "(sprint/l4 c646cea9, not on main yet: provenance flips to builder when it lands) "
        "publishes `product_code`, `satisfied_period_key`, `cause` and `currency` as attributes "
        "(a label is never key, D-98 85) and six typed-money measures; `entity_code` is in the "
        "key, no book column",
        measures=(
            "from_price_changes",
            "from_estimate_changes",
            "from_modifications",
            "from_late_events",
            "from_other",
            "revenue",
        ),
    ),
    SnapshotKind.COST_ROLLFORWARD.value: KeySpec(
        ("cost_kind", "line_code"),
        "builder",
        "§15.2.7 (entity, book, cost kind, line code); D-98 candidate 97 (ENG-C8's long dataset "
        "shape): one signed `amount` per (`cost_kind`, `line_code`) and entity with the eight "
        "S15-R-17 line codes OPENING, ADDITIONS, CLAWBACKS, AMORTIZATION, ACCELERATION, "
        "IMPAIRMENT, IMPAIRMENT_REVERSAL, CLOSING; `category_label` / `line_label` are "
        "attributes; the header carries neither `entity_code` nor a book column",
        measures=("amount",),
    ),
    SnapshotKind.JE_POPULATION.value: KeySpec(
        ("entity_code", "book", "je_no", "line_no"),
        "design",
        "§15.2.7 (je_no, line_no); SCREENS_B RPT `je_population` row key `line:<je no>:<line no>`; "
        "the header carries `entity_code` and `book`, so both are part of the key",
        measures=("debit_txn", "credit_txn", "debit_functional", "credit_functional"),
    ),
    SnapshotKind.OUT_OF_PERIOD_REGISTER.value: KeySpec(
        ("origin_period_key", "posting_period_key", "event_key"),
        "design",
        "§15.2.7 (origin period, posting period, event key); D-98 85: `event_key` = "
        "`event:<external id>:<stream version>` (ENGINE_SPEC_B §15.2.7; the file's `row_key` is "
        "the three components in one string, S15-R-18a rev 1.110) — never the proxy tuple "
        "contract / type / date, which distinct events can share; the header carries neither "
        "`entity_code` nor a book column",
        measures=("revenue_effect", "balance_effect"),
    ),
    SnapshotKind.MODIFICATION_REGISTER.value: KeySpec(
        ("contract_external_id", "modification_no", "obligation_key"),
        "builder",
        "§15.2.7 (`contract_external_id`, `modification_no`, `obligation_key`; rev 1.38, "
        "S15-R-20c); SCREENS_B RPT-14 `modification_register` row key "
        "`modification:<no>:<obligation key>`; the header carries neither `entity_code` nor a "
        "book column; the two declared measures are the builder's typed-money columns (lane "
        "F-CTR CTR-17; edit by F-CLO's consent, D-98 140-A1 Q-9)",
        measures=("tp_change", "catch_up_amount"),
    ),
    SnapshotKind.MANUAL_ADJUSTMENT_REGISTER.value: KeySpec(
        ("entity_code", "adjustment_no"),
        "design",
        "§15.2.7 (adjustment_no); SCREENS_B RPT `manual_adjustment_register`; the header carries "
        "`entity_code`, so it is part of the key (no book column)",
        measures=("amount_functional_abs",),
    ),
}


@dataclass(frozen=True, slots=True)
class DatasetSide:
    """One kind's dataset on one side: the T-CLS-05 columns and the stored bytes."""

    kind: str
    file_sha256: str
    row_count: int
    content: bytes


@dataclass(frozen=True, slots=True)
class LockSide:
    """One lock: id, manifest, certification and its datasets by kind."""

    lock_id: UUID
    snapshot_manifest_sha256: str | None
    certification: Sequence[Mapping[str, Any]]
    datasets: Mapping[str, DatasetSide]


# --- pure -----------------------------------------------------------------------------------------


def key_columns_of(kind: str) -> tuple[str, ...]:
    """The table's key columns of ``kind``; ``RelockDiffRefusal`` ``RELOCK_DIFF_KIND_UNKNOWN``."""
    spec = KEY_COLUMNS.get(str(kind))
    if spec is None:
        raise RelockDiffRefusal(KIND_UNKNOWN, str(kind), "not an E-64 snapshot kind of the table")
    return spec.columns


def _decimal(value: str) -> Decimal | None:
    text = value.strip()
    if not text or DECIMAL.fullmatch(text) is None:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:  # pragma: no cover - the pattern admits only decimals
        return None


def _rows(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    reader = csv.DictReader(io.StringIO(content.decode("utf-8")))
    rows = [dict(row) for row in reader]
    return list(reader.fieldnames or []), rows


def _keyed(
    kind: str, headers: Sequence[str], rows: Sequence[Mapping[str, str]], key_columns: Sequence[str]
) -> dict[tuple[str, ...], Mapping[str, str]]:
    missing = [column for column in key_columns if column not in headers]
    if missing:
        raise RelockDiffRefusal(
            KEY_MISSING, kind, f"header lacks the key column(s) {', '.join(missing)}"
        )
    keyed: dict[tuple[str, ...], Mapping[str, str]] = {}
    for row in rows:
        key = tuple(str(row.get(column) or "") for column in key_columns)
        if key in keyed:
            raise RelockDiffRefusal(
                KEY_DUPLICATE, kind, f"row key {dict(zip(key_columns, key, strict=True))} repeats"
            )
        keyed[key] = row
    return keyed


def _column_change(
    kind: str, header: str, previous: str, current: str, *, measure: bool
) -> dict[str, str]:
    """D-98 87: a declared measure reports previous, current and ``delta`` (both cells decimal;
    an empty cell is an absent value and carries no delta; a non-empty non-decimal cell refuses by
    name); any other column is an attribute change whatever its values look like."""
    if not measure:
        return {"kind": "attribute", "previous": previous, "current": current}
    change = {"kind": "measure", "previous": previous, "current": current}
    sides: list[Decimal | None] = []
    for value in (previous, current):
        if not value.strip():
            sides.append(None)
            continue
        parsed = _decimal(value)
        if parsed is None:
            raise RelockDiffRefusal(
                MEASURE_NOT_DECIMAL, kind, f"declared measure {header} holds {value!r}"
            )
        sides.append(parsed)
    before, after = sides
    if before is not None and after is not None:
        change["delta"] = str(after - before)
    return change


def diff_dataset(
    kind: str, previous: DatasetSide | None, current: DatasetSide | None
) -> dict[str, Any]:
    """One kind: hashes, row counts and the row-key comparison (S15-R-20; D-98 81)."""
    key_columns = key_columns_of(kind)
    spec = KEY_COLUMNS[str(kind)]
    out: dict[str, Any] = {
        "previous_file_sha256": None if previous is None else previous.file_sha256,
        "current_file_sha256": None if current is None else current.file_sha256,
        "previous_row_count": None if previous is None else previous.row_count,
        "current_row_count": None if current is None else current.row_count,
        "changed": (previous is None) != (current is None)
        or (
            previous is not None
            and current is not None
            and previous.file_sha256 != current.file_sha256
        ),
        "key_columns": list(key_columns),
    }
    if previous is None or current is None:
        out.update(
            added=[],
            removed=[],
            changed_rows=[],
            totals={
                "added": 0,
                "removed": 0,
                "changed": 0,
                "measure_changes": 0,
                "attribute_changes": 0,
            },
        )
        return out
    before_headers, before_rows = _rows(previous.content)
    after_headers, after_rows = _rows(current.content)
    headers = list(dict.fromkeys([*before_headers, *after_headers]))
    before = _keyed(kind, before_headers, before_rows, key_columns)
    after = _keyed(kind, after_headers, after_rows, key_columns)
    compared = [header for header in headers if header not in key_columns]
    added = [
        {"key": dict(zip(key_columns, key, strict=True)), "row": dict(after[key])}
        for key in after
        if key not in before
    ]
    removed = [
        {"key": dict(zip(key_columns, key, strict=True)), "row": dict(before[key])}
        for key in before
        if key not in after
    ]
    changed_rows: list[dict[str, Any]] = []
    measure_changes = attribute_changes = 0
    for key in before:
        if key not in after:
            continue
        columns: dict[str, dict[str, str]] = {}
        for header in compared:
            was, now = str(before[key].get(header) or ""), str(after[key].get(header) or "")
            if was != now:
                columns[header] = _column_change(
                    kind, header, was, now, measure=spec.is_measure(header)
                )
        if columns:
            measure_changes += sum(1 for change in columns.values() if change["kind"] == "measure")
            attribute_changes += sum(
                1 for change in columns.values() if change["kind"] == "attribute"
            )
            changed_rows.append(
                {"key": dict(zip(key_columns, key, strict=True)), "columns": columns}
            )
    out.update(
        added=added,
        removed=removed,
        changed_rows=changed_rows,
        totals={
            "added": len(added),
            "removed": len(removed),
            "changed": len(changed_rows),
            "measure_changes": measure_changes,
            "attribute_changes": attribute_changes,
        },
    )
    return out


def diff_certification(
    previous: Sequence[Mapping[str, Any]], current: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    before = {str(row["gate_check_code"]): row for row in previous}
    after = {str(row["gate_check_code"]): row for row in current}
    changed = [
        {
            "gate_check_code": code,
            "previous_status": None if code not in before else before[code].get("status"),
            "current_status": None if code not in after else after[code].get("status"),
        }
        for code in sorted(set(before) | set(after))
        if (before.get(code) or {}).get("status") != (after.get(code) or {}).get("status")
    ]
    return {
        "previous": [dict(row) for row in previous],
        "current": [dict(row) for row in current],
        "changed": changed,
    }


def diff(previous: LockSide, current: LockSide) -> dict[str, Any]:
    """The re-lock diff report of ``current`` against ``previous`` (module docstring)."""
    kinds = sorted(set(previous.datasets) | set(current.datasets))
    return {
        "format": FORMAT,
        "previous_lock_id": str(previous.lock_id),
        "lock_id": str(current.lock_id),
        "manifest": {
            "previous": previous.snapshot_manifest_sha256,
            "current": current.snapshot_manifest_sha256,
            "changed": previous.snapshot_manifest_sha256 != current.snapshot_manifest_sha256,
        },
        "kinds": {
            kind: diff_dataset(kind, previous.datasets.get(kind), current.datasets.get(kind))
            for kind in kinds
        },
        "certification": diff_certification(previous.certification, current.certification),
    }


def encode(report: Mapping[str, Any]) -> bytes:
    """Canonical JSON bytes of the report: sorted keys, no insignificant whitespace, UTF-8."""
    return json.dumps(
        report, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")


# --- DB-bound -------------------------------------------------------------------------------------


def _dataset_bytes(uow: UnitOfWork, file_id: UUID) -> bytes:
    _, stream = open_file(uow.session, file_id, files=uow.files, keyring=uow.keyring)
    return stream.read()


def previous_side(uow: UnitOfWork, lock_id: UUID) -> LockSide:
    """The previous ``LOCK`` as stored: its manifest, certification and every T-CLS-05 dataset."""
    session = uow.session
    lock = (
        session.execute(
            select(period_lock.c.snapshot_manifest_sha256, period_lock.c.certification).where(
                period_lock.c.id == lock_id
            )
        )
        .mappings()
        .one_or_none()
    )
    if lock is None:
        raise Problem("not-found", f"period lock {lock_id} is not visible")
    rows = (
        session.execute(
            select(
                lock_snapshot.c.snapshot_kind,
                lock_snapshot.c.file_id,
                lock_snapshot.c.file_sha256,
                lock_snapshot.c.row_count,
            ).where(lock_snapshot.c.period_lock_id == lock_id)
        )
        .mappings()
        .all()
    )
    datasets = {
        str(getattr(row["snapshot_kind"], "value", row["snapshot_kind"])): DatasetSide(
            kind=str(getattr(row["snapshot_kind"], "value", row["snapshot_kind"])),
            file_sha256=str(row["file_sha256"]),
            row_count=int(row["row_count"]),
            content=_dataset_bytes(uow, UUID(str(row["file_id"]))),
        )
        for row in rows
    }
    manifest = lock["snapshot_manifest_sha256"]
    return LockSide(
        lock_id=lock_id,
        snapshot_manifest_sha256=None if manifest is None else str(manifest),
        certification=list(lock["certification"] or []),
        datasets=datasets,
    )


def current_side(
    uow: UnitOfWork,
    *,
    lock_id: UUID,
    manifest_sha256: str,
    certification: Sequence[Mapping[str, Any]],
    datasets: Sequence[DatasetFile],
) -> LockSide:
    """The lock being written: the datasets just frozen, read back from the store."""
    return LockSide(
        lock_id=lock_id,
        snapshot_manifest_sha256=manifest_sha256,
        certification=list(certification),
        datasets={
            dataset.kind: DatasetSide(
                kind=dataset.kind,
                file_sha256=dataset.file_sha256,
                row_count=dataset.row_count,
                content=_dataset_bytes(uow, dataset.file_id),
            )
            for dataset in datasets
        },
    )


def report(
    uow: UnitOfWork,
    *,
    previous_lock_id: UUID,
    lock_id: UUID,
    manifest_sha256: str,
    certification: Sequence[Mapping[str, Any]],
    datasets: Sequence[DatasetFile],
) -> dict[str, Any]:
    """The diff of the lock being written against ``previous_lock_id`` (BR-CLS-07)."""
    return diff(
        previous_side(uow, previous_lock_id),
        current_side(
            uow,
            lock_id=lock_id,
            manifest_sha256=manifest_sha256,
            certification=certification,
            datasets=datasets,
        ),
    )


def store_report(uow: UnitOfWork, report_body: Mapping[str, Any], *, period_key: str) -> UUID:
    """Store the report as a ``REPORT_OUTPUT`` JSON file; its id goes on ``diff_report_file_id``."""
    row = store_file(
        uow,
        purpose=FilePurpose.REPORT_OUTPUT,
        stream=io.BytesIO(encode(report_body)),
        original_filename=f"relock-diff-{period_key}.json",
        media_type=MEDIA_TYPE,
    )
    return UUID(str(row["id"]))
