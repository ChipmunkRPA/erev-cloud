"""Export-time filters and the determinism comparison of a tenant snapshot, pure part (F-SNP
preparation; 05 §10 SBX-03 "approval requests and decisions referenced by copied rows",
"``file_object`` rows", SBX-05 ``derived_mismatches``; T-PLT-34).

The integration lane reads the source rows; these functions decide, without a database, which
approval and file rows a snapshot carries (only those the copied rows reference, so an unrelated
approval or an orphaned file never leaves the source) and compare the sandbox's recomputed
result per (combination group, book) with the source's latest version as of ``known_at`` (05
SBX-05 rev 1.50; supervisor rulings R-9 and R-43 (a)). What is verified is the MONETARY STATE —
the stored version, balances, obligation versions and schedule lines, without the per-version
activity columns (:func:`monetary_state`, :func:`first_difference`): the engine is incremental
and the sandbox computes each group once, so nothing else of a later source version can be
equal. For a group's FIRST computation the output itself is compared too, hashed with the source
computation's ``input_sha256`` in place of its own (:func:`comparable_hashes`) — the two raw
hashes can never be equal. :func:`judge` puts the two together. The reference columns are derived
from the 04 metadata by name and pinned by a test, so a new reference column on a copied table
forces a decision here.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from sqlalchemy import MetaData

from erev_api.approvals.subjects import PENDING_SUBJECTS, SUBJECTS
from erev_api.db.tables import metadata as model_metadata
from erev_api.domain.platform.snapshot_dataset import (
    LOAD_ORDER,
    PENDING,
    POLYMORPHIC_SUBJECTS,
    RULES,
    SnapshotClass,
)
from erev_api.enums import ApprovalSubjectType

if TYPE_CHECKING:
    from erev_engine.bundle import OutputBundle

__all__ = [
    "ACTIVITY_COLUMNS",
    "APPROVAL_REFERENCE",
    "ATTACHMENT_SUBJECTS",
    "COMPARISON_HASH",
    "COMPARISON_ONE_SIDED",
    "COMPARISON_STATE",
    "FILE_REFERENCE",
    "MONETARY_EXCLUDED",
    "MONETARY_KEYS",
    "MONETARY_TABLES",
    "POLYMORPHIC_SUBJECTS",
    "ApprovalRule",
    "Approvals",
    "DeterminismReport",
    "Difference",
    "ExportSelection",
    "Finding",
    "Mismatch",
    "PairFacts",
    "SourceVersion",
    "approval_rules",
    "comparable_hashes",
    "compare_determinism",
    "first_difference",
    "judge",
    "monetary_members",
    "monetary_state",
    "filter_approvals",
    "filter_attachments",
    "filter_files",
    "filter_polymorphic",
    "reference_columns",
    "referenced_approvals",
    "referenced_ids",
    "select_export",
    "subject_references",
]

_APPROVAL_COLUMN: Final = "approval_request_id"
_FILE_SUFFIX: Final = "_file_id"  # ``mapping_profile_id`` is not a file
_FILE_OBJECT_COLUMN: Final = "file_object_id"
# Reference columns of copied tables that point at rows the copy carries only when referenced.
APPROVAL_REFERENCE: Final = "approval_request"
FILE_REFERENCE: Final = "file_object"
# The approval's own rows name their request without being a "copied row that references it".
_APPROVAL_OWN: Final = frozenset({"approval_request", "approval_step", "approval_decision"})
# T-PLT-30 ``file_attachment.subject_type`` literal → the subject table (F-SNP-R3): the attachment
# case of the polymorphic-subject rule (ruling D-98 candidate 34, ``POLYMORPHIC_SUBJECTS``).
ATTACHMENT_SUBJECTS: Final[Mapping[str, str]] = POLYMORPHIC_SUBJECTS["file_attachment"]


def reference_columns(metadata: MetaData | None = None) -> Mapping[str, Mapping[str, str]]:
    """Per referenced table (``approval_request``, ``file_object``): copied table → the column that
    names it, derived from the 04 metadata by column name (``approval_request_id``; ``*_file_id``
    and ``file_object_id``); the approval's own tables are not references to it."""
    tables = {t.name: t for t in (metadata or model_metadata).tables.values()}
    approvals: dict[str, str] = {}
    files: dict[str, str] = {}
    for name in LOAD_ORDER:
        for column in tables[name].columns:
            if column.name == _APPROVAL_COLUMN and name not in _APPROVAL_OWN:
                approvals[name] = column.name
            if column.name == _FILE_OBJECT_COLUMN or column.name.endswith(_FILE_SUFFIX):
                files.setdefault(name, column.name)
                if column.name != files[name]:
                    # a table with several file columns is listed once per column, joined
                    files[name] = "|".join(sorted({*files[name].split("|"), column.name}))
    return MappingProxyType(
        {
            APPROVAL_REFERENCE: MappingProxyType(dict(sorted(approvals.items()))),
            FILE_REFERENCE: MappingProxyType(dict(sorted(files.items()))),
        }
    )


def referenced_ids(
    rows_by_table: Mapping[str, Iterable[Mapping[str, Any]]], columns: Mapping[str, str]
) -> frozenset[UUID]:
    """The ids the copied rows name through ``columns`` (table → column or ``a|b`` columns)."""
    found: set[UUID] = set()
    for table, spec in columns.items():
        for row in rows_by_table.get(table, ()):
            for column in spec.split("|"):
                value = row.get(column)
                if value is None:
                    continue
                if not isinstance(value, UUID):
                    raise TypeError(f"{table}.{column}: a reference is a UUID")
                found.add(value)
    return frozenset(found)


@dataclass(frozen=True, slots=True)
class ApprovalRule:
    """One reference rule of the SBX-03 "approval requests referenced by copied rows" filter
    (ruling D-98 candidate 25 on Q-2: the rules are data per approval-bearing table; the filter is
    pure; export runs in the integration lane). ``column``: a copied row names the request through
    ``approval_request_id``. ``subject``: the request's own ``subject_type`` / ``subject_id``
    names a copied row of ``table`` (``approvals.subjects.SUBJECTS``)."""

    kind: str  # "column" | "subject"
    table: str  # the copied table
    column: str | None = None  # column rule
    subject_type: str | None = None  # subject rule (E-08 literal)


def approval_rules(metadata: MetaData | None = None) -> tuple[ApprovalRule, ...]:
    """The column rules (from ``reference_columns``) and the subject rules (every registered
    subject spec whose table is copied), in a stable order."""
    columns = reference_columns(metadata)[APPROVAL_REFERENCE]
    rules = [ApprovalRule("column", table, column=column) for table, column in columns.items()]
    copied = set(LOAD_ORDER)
    for subject_type, spec in sorted(SUBJECTS.items(), key=lambda item: item[0].value):
        if spec.table in copied:
            rules.append(ApprovalRule("subject", spec.table, subject_type=subject_type.value))
    return tuple(rules)


def subject_references(
    requests: Iterable[Mapping[str, Any]], copied_ids: Mapping[str, Iterable[UUID]]
) -> frozenset[UUID]:
    """The requests whose subject is a copied row: ``SUBJECTS[subject_type].table`` is a copied
    table and ``subject_id`` is among that table's copied ids. A request whose subject type has no
    spec yet (``PENDING_SUBJECTS``) is refused — the copy fails closed rather than guessing."""
    by_table = {table: frozenset(ids) for table, ids in copied_ids.items()}
    copied_tables = set(LOAD_ORDER)
    pending = {name for name, _ in PENDING_SUBJECTS}
    found: set[UUID] = set()
    for row in requests:
        literal = str(row["subject_type"])
        if literal in pending:
            raise ValueError(
                f"approval_request {row['id']}: subject type {literal} has no SubjectSpec yet; "
                "the copy cannot decide whether its subject is copied"
            )
        try:
            spec = SUBJECTS.get(ApprovalSubjectType(literal))
        except ValueError as error:
            raise ValueError(
                f"approval_request {row['id']}: unknown subject type {literal}"
            ) from error
        if spec is None:
            raise ValueError(f"approval_request {row['id']}: unknown subject type {literal}")
        subject_id = row["subject_id"]
        if not isinstance(subject_id, UUID):
            raise TypeError(f"approval_request {row['id']}: subject_id is a UUID")
        # A subject table that is never copied (support_grant, exception_item, journal_run) cannot
        # anchor a copied approval, whatever ids the caller passes for it.
        if spec.table in copied_tables and subject_id in by_table.get(spec.table, frozenset()):
            found.add(row["id"])
    return frozenset(found)


def referenced_approvals(
    rows_by_table: Mapping[str, Iterable[Mapping[str, Any]]],
    requests: Iterable[Mapping[str, Any]],
    copied_ids: Mapping[str, Iterable[UUID]],
    metadata: MetaData | None = None,
) -> frozenset[UUID]:
    """Ruling D-98 candidate 26 on Q-2, both readings as a union: the requests a copied row names
    through ``approval_request_id`` OR whose own subject is a copied row. No status filter:
    rejected and superseded requests travel with their steps and decisions
    (``filter_approvals``)."""
    columns = reference_columns(metadata)[APPROVAL_REFERENCE]
    return referenced_ids(rows_by_table, columns) | subject_references(requests, copied_ids)


@dataclass(frozen=True, slots=True)
class Approvals:
    """The approval rows a snapshot carries: requests referenced by copied rows, with every step
    and decision of those requests (SBX-03)."""

    requests: tuple[Mapping[str, Any], ...]
    steps: tuple[Mapping[str, Any], ...]
    decisions: tuple[Mapping[str, Any], ...]


def filter_approvals(
    requests: Iterable[Mapping[str, Any]],
    steps: Iterable[Mapping[str, Any]],
    decisions: Iterable[Mapping[str, Any]],
    referenced: frozenset[UUID],
) -> Approvals:
    """Keep the referenced requests and their steps and decisions. Refused: a referenced request
    absent from ``requests`` (the population is incomplete; same shape as the missing-file
    refusal) and a step or decision of an unknown request. Each input is read once (F-SNP-R2)."""
    population = tuple(requests)
    kept = tuple(row for row in population if row["id"] in referenced)
    known = {row["id"] for row in kept}
    missing = referenced - known
    if missing:
        raise ValueError(
            f"approval_request rows missing for referenced ids {sorted(map(str, missing))}"
        )
    all_requests = {row["id"] for row in population}
    kept_steps = []
    for step in tuple(steps):
        request = step["approval_request_id"]
        if request not in all_requests:
            raise ValueError(f"approval_step {step['id']}: unknown request {request}")
        if request in known:
            kept_steps.append(step)
    kept_decisions = []
    for decision in tuple(decisions):
        request = decision["approval_request_id"]
        if request not in all_requests:
            raise ValueError(f"approval_decision {decision['id']}: unknown request {request}")
        if request in known:
            kept_decisions.append(decision)
    return Approvals(kept, tuple(kept_steps), tuple(kept_decisions))


def filter_polymorphic(
    table: str,
    rows: Iterable[Mapping[str, Any]],
    copied_ids: Mapping[str, Iterable[UUID]] | None = None,
) -> tuple[Mapping[str, Any], ...]:
    """Rows of a copied dataset with a polymorphic ``subject_type`` / ``subject_id`` (ruling D-98
    candidate 34). A subject type outside the 04 CHECK or naming a PENDING table refuses the export
    (never a dangling reference). A REGENERATED subject: an attachment is excluded (its subject row
    does not exist in the sandbox, F-SNP-R3), a judgement record or rule test case is kept with
    ``subject_id`` nulled (``REBUILD_STEPS``: stays NULL). A copied subject: an attachment is kept
    when its subject row is among ``copied_ids``, other rows are kept as is (SBX-03 copies judgement
    records in their own right)."""
    literals = POLYMORPHIC_SUBJECTS.get(table)
    if literals is None:
        raise ValueError(f"{table} has no polymorphic subject column")
    attachments = table == "file_attachment"
    by_table = {t: frozenset(ids) for t, ids in (copied_ids or {}).items()}
    kept: list[Mapping[str, Any]] = []
    for row in rows:
        if "subject_type" not in row or "subject_id" not in row:
            raise ValueError(f"{table} {row.get('id')}: row lacks subject_type / subject_id")
        literal = str(row["subject_type"])
        target = literals.get(literal)
        if target is None:
            raise ValueError(f"{table} {row['id']}: unsupported {table} subject type {literal!r}")
        if target in PENDING:
            raise ValueError(
                f"{table} {row['id']}: subject table {target} is PENDING (lane "
                f"{PENDING[target].lane}); the copy cannot decide whether its subject is copied"
            )
        subject_id = row["subject_id"]
        if not isinstance(subject_id, UUID):
            raise TypeError(f"{table} {row['id']}: subject_id is a UUID")
        if RULES[target].snapshot_class is not SnapshotClass.COPIED:
            if not attachments:
                kept.append({**row, "subject_id": None})
            continue
        if attachments and subject_id not in by_table.get(target, frozenset()):
            continue
        kept.append(row)
    return tuple(kept)


def filter_attachments(
    attachments: Iterable[Mapping[str, Any]], copied_ids: Mapping[str, Iterable[UUID]]
) -> tuple[Mapping[str, Any], ...]:
    """The ``file_attachment`` rows whose subject is a copied row (F-SNP-R3): the attachment case of
    ``filter_polymorphic``, applied before ``filter_files`` so an attachment's file is referenced
    only through a kept attachment."""
    return filter_polymorphic("file_attachment", attachments, copied_ids)


def filter_files(
    files: Iterable[Mapping[str, Any]], referenced: frozenset[UUID]
) -> tuple[Mapping[str, Any], ...]:
    """Keep the ``file_object`` rows the copied rows reference (SBX-03: rows only — storage keys
    and sidecars are shared, PRV-06); a referenced id absent from ``files`` is refused."""
    kept = tuple(row for row in files if row["id"] in referenced)
    missing = referenced - {row["id"] for row in kept}
    if missing:
        raise ValueError(f"file_object rows missing for referenced ids {sorted(map(str, missing))}")
    return kept


@dataclass(frozen=True, slots=True)
class ExportSelection:
    """What a snapshot export carries after the selectors ran (Codex retest of b00a7df): the copied
    rows per dataset (attachments already filtered; the approval tables replaced by the kept
    approvals), the approvals and the ``file_object`` rows referenced only through kept rows."""

    rows: Mapping[str, Sequence[Mapping[str, Any]]]
    approvals: Approvals
    files: tuple[Mapping[str, Any], ...]


def select_export(
    rows_by_table: Mapping[str, Iterable[Mapping[str, Any]]],
    requests: Iterable[Mapping[str, Any]],
    steps: Iterable[Mapping[str, Any]],
    decisions: Iterable[Mapping[str, Any]],
    files: Iterable[Mapping[str, Any]],
    copied_ids: Mapping[str, Iterable[UUID]],
    metadata: MetaData | None = None,
) -> ExportSelection:
    """The export chain in one call, in the only safe order: (1) attachments are filtered to
    copied subjects (``filter_attachments``) before any file reference is read; (2) approval
    requests are selected by both readings (``referenced_approvals``) and completed with their
    steps and decisions; (3) ``file_object`` rows are selected only through the kept attachments,
    the kept approvals and the other file-reference columns of the copied rows. A dataset name
    outside the copied set is refused.

    F-SNP-R5 (ruling D-98 candidate 41): the copied-id populations are materialised exactly once
    here — one ``frozenset`` per subject table — and every downstream consumer reads those stable
    values, so list and iterator inputs give the same export."""
    populations: Mapping[str, frozenset[UUID]] = MappingProxyType(
        {table: frozenset(ids) for table, ids in copied_ids.items()}
    )
    rows: dict[str, Sequence[Mapping[str, Any]]] = {}
    for table, table_rows in rows_by_table.items():
        if table not in LOAD_ORDER:
            raise ValueError(f"select_export: {table} is not a copied dataset")
        rows[table] = table_rows if isinstance(table_rows, Sequence) else tuple(table_rows)
    for table in POLYMORPHIC_SUBJECTS:
        if table in rows:  # attachments first: their files are referenced only through kept rows
            rows[table] = filter_polymorphic(table, rows[table], populations)
    population = tuple(requests)
    referenced = referenced_approvals(rows, population, populations, metadata)
    approvals = filter_approvals(population, steps, decisions, referenced)
    rows["approval_request"] = approvals.requests
    rows["approval_step"] = approvals.steps
    rows["approval_decision"] = approvals.decisions
    file_ids = referenced_ids(rows, reference_columns(metadata)[FILE_REFERENCE])
    kept_files = filter_files(files, file_ids)
    # The file_object dataset is the kept files: an export that encodes ``rows`` table by table
    # never sees an unreferenced file (found by the I-2 handler test).
    rows["file_object"] = kept_files
    return ExportSelection(MappingProxyType(rows), approvals, kept_files)


@dataclass(frozen=True, slots=True)
class SourceVersion:
    """A source ``contract_version`` as SBX-05 reads it (T-CON-08), with the ``input_sha256`` of
    the computation that wrote it (T-CON-07) — the hash SBX-05 substitutes into the sandbox's
    output."""

    combination_group_id: UUID
    book_code: str
    version_no: int
    known_at: datetime
    output_sha256: str
    input_sha256: str
    version_id: UUID | None = None  # the row whose monetary state is read (``monetary_state``)
    # The computation that wrote the version is the group's FIRST succeeded one: its bundle had
    # no ``previous_stream_heads`` and nothing ``posted``, as the sandbox's single recompute has.
    first_computation: bool = False


@dataclass(frozen=True, slots=True)
class Mismatch:
    combination_group_id: UUID
    book_code: str
    source_sha256: str | None  # None: the source has no version as of known_at
    # The sandbox's COMPARABLE hash (:func:`comparable_hashes`), never its stored raw hash.
    sandbox_sha256: str | None  # None: the sandbox recomputed nothing for the pair


@dataclass(frozen=True, slots=True)
class DeterminismReport:
    """SBX-05: the pairs compared, the mismatches and ``derived_mismatches``."""

    compared: int
    mismatches: tuple[Mismatch, ...]

    @property
    def derived_mismatches(self) -> int:
        return len(self.mismatches)


def latest_as_of(
    versions: Iterable[SourceVersion], known_at: datetime
) -> Mapping[tuple[UUID, str], SourceVersion]:
    """The source's latest version per (group, book) with ``known_at`` at or before the snapshot's
    (the highest ``version_no``); later versions are not part of the copy."""
    latest: dict[tuple[UUID, str], SourceVersion] = {}
    for version in versions:
        if version.known_at > known_at:
            continue
        key = (version.combination_group_id, version.book_code)
        current = latest.get(key)
        if current is None or version.version_no > current.version_no:
            latest[key] = version
    return MappingProxyType(latest)


def comparable_hashes(
    group_id: UUID,
    output: OutputBundle,
    expected: Mapping[tuple[UUID, str], SourceVersion],
) -> Mapping[tuple[UUID, str], str]:
    """SBX-05 (rev 1.34; supervisor ruling R-9): per book of the sandbox's recomputed ``output``
    that carries a contract version, CV-26 of that output with the SOURCE computation's stored
    ``input_sha256`` in place of its own — equal to the source version's stored ``output_sha256``
    exactly when the two outputs are identical in every member but the input hash.

    The raw hashes can never be equal: ``input_sha256`` is a member of the output (CV-26) and
    covers the events' ``record_seq`` / ``recorded_at`` and the trigger (CV-25), which the load
    re-stamps (05 SBX-04, DB-08) and sets to ``MIGRATION``. Nothing else is substituted — the
    engine version, every amount, schedule line, posting intent, trace node and diagnostic stay
    hashed. A book the source has no version for (``expected`` holds the source's latest versions
    as of ``known_at``, :func:`latest_as_of`) keeps the output's own hash: there is nothing to
    substitute and the one-sided pair is a mismatch (:func:`compare_determinism`)."""
    hashes: dict[tuple[UUID, str], str] = {}
    by_input: dict[str, str] = {}  # one canonicalisation per distinct substituted hash
    for book in output.books:
        if book.contract_version is None:
            continue  # no T-CON-08 row is written for the book (computation._persist_book)
        key = (group_id, book.book_code)
        source = expected.get(key)
        substitute = output.input_sha256 if source is None else source.input_sha256
        if substitute not in by_input:
            by_input[substitute] = dataclasses.replace(output, input_sha256=substitute).sha256()
        hashes[key] = by_input[substitute]
    return MappingProxyType(hashes)


def compare_determinism(
    source: Iterable[SourceVersion],
    sandbox: Mapping[tuple[UUID, str], str],
    known_at: datetime,
) -> DeterminismReport:
    """Per (group, book): the sandbox's comparable hash (:func:`comparable_hashes`) against the
    ``output_sha256`` of the source's latest version as of ``known_at``; a pair present on one
    side only is a mismatch too (SBX-05)."""
    expected = latest_as_of(source, known_at)
    mismatches: list[Mismatch] = []
    for key in sorted(set(expected) | set(sandbox), key=lambda k: (str(k[0]), k[1])):
        source_sha = expected[key].output_sha256 if key in expected else None
        sandbox_sha = sandbox.get(key)
        if source_sha != sandbox_sha:
            mismatches.append(Mismatch(key[0], key[1], source_sha, sandbox_sha))
    return DeterminismReport(len(set(expected) | set(sandbox)), tuple(mismatches))


# --- SBX-05 rev 1.50 (supervisor ruling R-43 (a)): the monetary state ----------------------------

# The stored result of one contract version that SBX-05 compares — RCP-28a L2 category M as far
# as the platform stores it. T-CON-16 / 17 / 18 (cost asset versions, loss provision versions, FX
# layer movements) belong to the category and are PENDING tables: each joins here when it lands
# (a test fails the day one is in the model and not in this tuple). The order is the order in
# which a difference is looked for and named: a schedule line before its header, whose count and
# total only sum the lines.
MONETARY_TABLES: Final = (
    "contract_version",
    "contract_version_balance",
    "obligation_version",
    "schedule_line",
    "schedule",
)
# T-CON-11 columns that state the ACTIVITY OF ONE VERSION — what the events first included in it
# (``EventView.is_new``; ENGINE_SPEC Table 0.9-A, CV-64) delivered, recognised, billed and caught
# up. The source's latest version carries the activity of its last computation, the sandbox's
# single version the activity of the whole stream: history, not state. Excluded by name.
ACTIVITY_COLUMNS: Final = frozenset(
    {
        "revenue_amount",
        "billed_amount",
        "pre_standard_revenue_amount",
        "delivered_quantity",
        "ssp_delivered",
        "catch_up_amount",
    }
)
_STAMPS: Final = frozenset({"created_at", "created_by", "created_by_kind"})
# Per table, the columns that are NOT monetary state, by name and for a stated reason: the
# remapped tenant and the row's own surrogate id; the pair the state belongs to (the comparison's
# key, not its content); the orchestrator's lineage of the computation history (version numbers,
# previous versions, the computation, the events behind it, the pinned policy inputs); the trace
# (RCP-28a category T); the stamps; and the activity columns.
MONETARY_EXCLUDED: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "contract_version": _STAMPS
        | {
            "tenant_id",
            "id",
            "combination_group_id",
            "book_code",
            "contract_computation_id",
            "version_no",
            "previous_version_id",
            "known_at",
            "cause_event_ids",
            "output_sha256",
            "calc_trace_id",
            "pinned_policies",
        },
        "contract_version_balance": _STAMPS
        | {"tenant_id", "id", "contract_version_id", "book_code"},
        "obligation_version": _STAMPS
        | ACTIVITY_COLUMNS
        | {
            "tenant_id",
            "id",
            "contract_version_id",
            "combination_group_id",
            "book_code",
            "version_no",
            "previous_obligation_version_id",
            "previous_effective_date",
            "trace_nodes",
        },
        "schedule": _STAMPS
        | {"tenant_id", "id", "contract_version_id", "combination_group_id", "book_code"},
        "schedule_line": frozenset(
            {
                "tenant_id",
                "id",
                "schedule_id",
                "contract_version_id",
                "book_code",
                "trace_node_id",
                "created_at",
            }
        ),
    }
)
# Per table, what identifies a row within ONE version, in both tenants alike: copied ids and
# natural keys, never a surrogate id the recompute assigned. ``schedule_kind`` of a line is its
# header's (the reader joins it in).
MONETARY_KEYS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        "contract_version": (),
        "contract_version_balance": ("contract_id", "entity_id"),
        "obligation_version": ("obligation_id",),
        "schedule": ("schedule_kind",),
        "schedule_line": (
            "schedule_kind",
            "subject_type",
            "subject_id",
            "entity_id",
            "period_id",
            "line_type",
        ),
    }
)
COMPARISON_STATE: Final = "MONETARY_STATE"
COMPARISON_HASH: Final = "OUTPUT_HASH"
COMPARISON_ONE_SIDED: Final = "ONE_SIDED"
_HASH_MEMBER: Final = "output_sha256"

type MonetaryState = Mapping[str, Mapping[tuple[str, ...], Mapping[str, Any]]]


def monetary_members(table: str, metadata: MetaData | None = None) -> tuple[str, ...]:
    """The columns of ``table`` that are monetary state, in table order: every column the table
    has except ``MONETARY_EXCLUDED`` — so a column added to the table is compared until someone
    excludes it by name."""
    columns = (metadata or model_metadata).tables[f"erev.{table}"].columns
    return tuple(str(c.name) for c in columns if c.name not in MONETARY_EXCLUDED[table])


def monetary_state(
    rows: Mapping[str, Sequence[Mapping[str, Any]]], metadata: MetaData | None = None
) -> MonetaryState:
    """The monetary state of one contract version from its stored rows (``rows``: per table of
    ``MONETARY_TABLES`` the rows of that version; a ``schedule_line`` row carries its header's
    ``schedule_kind``): per table, per row key (``MONETARY_KEYS``), the member columns
    (:func:`monetary_members`). Two rows of one table with the same key are refused — the key
    would not identify a member."""
    state: dict[str, Mapping[tuple[str, ...], Mapping[str, Any]]] = {}
    for table in MONETARY_TABLES:
        members = monetary_members(table, metadata)
        keyed: dict[tuple[str, ...], Mapping[str, Any]] = {}
        for row in rows.get(table, ()):
            key = tuple(str(row[column]) for column in MONETARY_KEYS[table])
            if key in keyed:
                raise ValueError(f"{table}: two rows of one version carry the key {key}")
            keyed[key] = MappingProxyType(
                {column: row[column] for column in members if column not in MONETARY_KEYS[table]}
            )
        state[table] = MappingProxyType(keyed)
    return MappingProxyType(state)


@dataclass(frozen=True, slots=True)
class Difference:
    """The first member in which two monetary states differ."""

    table: str
    key: tuple[str, ...]
    column: str | None  # None: the row exists on one side only
    source: Any
    sandbox: Any

    @property
    def member(self) -> str:
        """``<table>[<key>].<column>`` — the name the load report and the warning carry."""
        row = f"{self.table}[{', '.join(self.key)}]" if self.key else self.table
        return row if self.column is None else f"{row}.{self.column}"


def first_difference(source: MonetaryState, sandbox: MonetaryState) -> Difference | None:
    """The first differing member of two monetary states, in a fixed order — the tables of
    ``MONETARY_TABLES``, their row keys sorted, the columns in table order — or None when the
    states are equal. A row present on one side only is a difference of that row."""
    for table in MONETARY_TABLES:
        ours, theirs = source.get(table, {}), sandbox.get(table, {})
        for key in sorted(set(ours) | set(theirs)):
            if key not in ours or key not in theirs:
                present, absent = "present", "absent"
                return Difference(
                    table,
                    key,
                    None,
                    present if key in ours else absent,
                    present if key in theirs else absent,
                )
            for column, value in ours[key].items():
                if theirs[key][column] != value:
                    return Difference(table, key, column, value, theirs[key][column])
    return None


@dataclass(frozen=True, slots=True)
class PairFacts:
    """What the load read for one (group, book) pair that has a version on BOTH sides."""

    first_computation: bool  # the source version is its group's first succeeded computation
    difference: Difference | None  # of the two monetary states


@dataclass(frozen=True, slots=True)
class Finding:
    """One ``derived_mismatches`` entry of SBX-05: the pair, which comparison found it and the
    first differing member with both values (None for a one-sided pair)."""

    combination_group_id: UUID
    book_code: str
    comparison: str  # COMPARISON_STATE | COMPARISON_HASH | COMPARISON_ONE_SIDED
    member: str | None
    source: Any
    sandbox: Any


def judge(
    report: DeterminismReport, facts: Mapping[tuple[UUID, str], PairFacts]
) -> tuple[Finding, ...]:
    """SBX-05 rev 1.50: the findings of a load, from the hash comparison ``report``
    (:func:`compare_determinism` over the comparable hashes — it also finds the one-sided pairs)
    and the monetary ``facts`` of every pair present on both sides.

    * a pair on one side only is a finding (``ONE_SIDED``);
    * a pair whose monetary states differ is a finding naming the first differing member
      (``MONETARY_STATE``) — whatever its hashes say;
    * a pair whose monetary states are equal is VERIFIED — unless the source version is a FIRST
      computation and the comparable hash differs all the same: there a one-shot recompute must
      reproduce the whole output, so the difference (posting intents, trace, an activity column)
      is a finding (``OUTPUT_HASH``);
    * a hash mismatch the load read no facts for is reported as it is (``OUTPUT_HASH``): it is
      never dropped unverified."""
    findings: dict[tuple[UUID, str], Finding] = {}
    for mismatch in report.mismatches:
        key = (mismatch.combination_group_id, mismatch.book_code)
        source, sandbox = mismatch.source_sha256, mismatch.sandbox_sha256
        known = facts.get(key)
        if source is None or sandbox is None:
            findings[key] = Finding(*key, COMPARISON_ONE_SIDED, None, source, sandbox)
        elif known is None or known.first_computation:
            findings[key] = Finding(*key, COMPARISON_HASH, _HASH_MEMBER, source, sandbox)
    for key, known in facts.items():
        if known.difference is not None:
            found = known.difference
            findings[key] = Finding(
                *key, COMPARISON_STATE, found.member, found.source, found.sandbox
            )
    return tuple(findings[key] for key in sorted(findings, key=lambda k: (str(k[0]), k[1])))
