"""The migration jobs: ``MIGRATION_IMPORT`` (BUILD_SPEC LMG-2; 04 T-MIG-01 note, T-MIG-02,
T-MIG-04 / T-MIG-05 rev 1.60; ENGINE_SPEC S07-R-11; D-98 candidates 122 and 126) and
``MIGRATION_RECONCILE`` (BUILD_SPEC LMG-3; 04 T-MIG-01 / T-MIG-03; PRD SM-12, BR-MIG-02, WLD-X-27).

``import_batch`` (mode (a)): the batch must be ``PROFILED``; ``PROFILED → IMPORTING`` with the job
id; the legacy rows are read from the batch's stored source copy (``legacy_source``); the opening
balances are staged (``opening_balances.stage``, S07-R-11; the cutover validated); every legacy row
is stored as T-MIG-02; the S07-R-03 findings become exception items (source ``MIGRATION``); the
staged contracts are booked, activated, established and computed inside a savepoint and the
computed result is captured DURABLY (``capture.dry_run`` → ``repository.insert_population``,
T-MIG-04 / T-MIG-05) while the engine rows roll back — no ``contract`` row survives (BS3-D-26);
``IMPORTING → IMPORTED`` with the profile counts. Refusals are by name (``capture``): pending
POL-211 rows, option records, missing booking prerequisites, a legacy money value the
``OPENING_BALANCE_ESTABLISHED`` payload cannot carry, a refused computation — nothing is invented
or rounded.

``reconcile_batch`` reads the batch (status ``IMPORTED``), the legacy side (T-MIG-02 rows → the
latest version per record key → ``reconciliation.legacy_values``) and the eRev side — the batch's
BOUND comparison population (``population.ComparisonPopulation``: its own mode and cutover, the
book, the contract / version / trace identities of the captured computation), whose obligation
versions and own calc traces ``exact_values.erev_values`` reads (exact, trace-sourced values, the
same sources the parity reader reads; SCREENS_B RPT-41 "Value representation"). It compares them
with the deviation binding, control totals and tie-out of ``reconciliation``, writes the T-MIG-03
lines once and moves the batch ``IMPORTED → RECONCILED``. The eRev side is never "the latest
version as of now" (Codex F1 on a2aad104): a later live computation cannot change the comparison.

Interim refusals, each explicit (no silent zero, no silent pass, no substitution): a batch that is
not ``IMPORTED``; a comparison population not yet captured — refused BY NAME of the mode's source
(mode (a) the import's dry-run computation at the cutover, job ``MIGRATION_IMPORT``; mode (b) the
replay's committed versions in the sandbox, LMG-4) — the state until those slices land; a
population that is not the batch's own; rows that are not exactly the captured expected output of
the bound versions (a non-member's row, an unexpected row, an expected row that did not load — a
version's membership and its output are captured separately, never inferred, and an admitted
EMPTY output binds with no rows; ``population``); a measure whose exact source or trace evidence
is missing or wrong (``ExactSourceError``; every bound version's own trace is validated, empty
output included); unexplained
differences — their exception items are created by the exception slice, so until it lands the
lines are not written and the job refuses with the count. Readers are ports with repository
defaults so the composition is testable without a database.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Any, Final
from uuid import UUID

from erev_api.domain.migration import (
    capture,
    exact_values,
    field_mapping,
    legacy_db,
    opening_balances,
    prerequisites,
    reconciliation,
    repository,
)
from erev_api.domain.migration.exact_values import ExactSourceError, NodeLookup
from erev_api.domain.migration.legacy_db import LegacyRow, latest_rows
from erev_api.domain.migration.population import (
    ComparisonPopulation,
    PopulationError,
    VersionRef,
    not_captured_copy,
)
from erev_api.domain.migration.reconciliation import ControlTotals, DeviationIndex
from erev_api.enums import JobKind, MigrationMode, MigrationStatus
from erev_api.jobs.context import JobContext, system_unit_of_work
from erev_api.jobs.registry import JobOutcome, task
from erev_api.problems import Problem, ProblemError
from erev_api.uow import UnitOfWork

__all__ = [
    "NOT_IMPORTED_COPY",
    "NOT_PROFILED_COPY",
    "RECOVERABLE_STATES",
    "REPLAY_IMPORT_COPY",
    "UNEXPLAINED_COPY",
    "DeviationSource",
    "EvidenceVerifier",
    "LegacyRowsReader",
    "LegacySource",
    "PopulationReader",
    "TraceLoader",
    "VersionsReader",
    "deviation_source",
    "import_batch",
    "import_failed",
    "import_migration",
    "reconcile",
    "reconcile_batch",
]

NOT_IMPORTED_COPY: Final = "Reconcile an imported migration; this one is {status}."
UNEXPLAINED_COPY: Final = (
    "{count} difference(s) above tolerance carry no deviation reference; their exception items are "
    "required before the lines are stored (04 T-MIG-03)."
)
NOT_PROFILED_COPY: Final = "Import a profiled migration; this one is {status}."
# E-76 states a captured batch may have reached when a retry of its import arrives (04 T-MIG-01
# note rev 1.60, Codex 0515 C1): recovery recognises the same operation's capture in any of them.
RECOVERABLE_STATES: Final = frozenset(
    {
        MigrationStatus.IMPORTED.value,
        MigrationStatus.RECONCILED.value,
        MigrationStatus.SUBMITTED.value,
        MigrationStatus.PROMOTED.value,
    }
)
REPLAY_IMPORT_COPY: Final = (
    "The replay import (mode b) is the LMG-4 slice; this job imports OPENING_BALANCES migrations."
)
_RULE: Final = "T-MIG-03"
_IMPORT_RULE: Final = "T-MIG-01"

type LegacyRowsReader = Callable[[UnitOfWork, UUID], Sequence[LegacyRow]]
# The batch's legacy rows from its stored source copy (T-MIG-01 ``source_file_id``): the job hands
# the runtime's file store and key ring; the default opens the file and reads it read-only.
type LegacySource = Callable[[JobContext, UnitOfWork, Mapping[str, Any]], Sequence[LegacyRow]]
type PopulationReader = Callable[[UnitOfWork, Mapping[str, Any]], ComparisonPopulation | None]
type VersionsReader = Callable[[UnitOfWork, ComparisonPopulation], Sequence[Mapping[str, Any]]]
type TraceLoader = Callable[[UnitOfWork, VersionRef], NodeLookup]
type DeviationSource = Callable[[], DeviationIndex]
# The retained input evidence of every bound version verified before extraction (Codex 0515 R1).
type EvidenceVerifier = Callable[[UnitOfWork, ComparisonPopulation], None]


def deviation_source() -> DeviationIndex:
    """The deviation index the reconcile explains lines with. The golden documents
    (``docs/legacy/golden``) are repository files, not part of the installed package; until the
    LMG configuration names their location the default index is empty — every difference above
    tolerance is then unexplained and refused, never silently passed."""
    return DeviationIndex.empty()


def _refuse(detail: str) -> Problem:
    return Problem(
        "invalid-transition",
        detail,
        errors=[ProblemError(field="migration_id", rule_id=_RULE, message=detail)],
    )


def _evidence_failure(error: Exception) -> Problem:
    return Problem(
        "validation-failed",
        "1 field needs attention.",
        errors=[ProblemError(field="migration_id", rule_id="DG-PAR-05", message=str(error))],
    )


def reconcile_batch(
    uow: UnitOfWork,
    batch_id: UUID,
    *,
    job_id: UUID | None = None,
    legacy_rows_reader: LegacyRowsReader = repository.legacy_records,
    population_reader: PopulationReader = repository.comparison_population,
    versions_reader: VersionsReader = repository.population_obligation_versions,
    trace_loader: TraceLoader = repository.trace_nodes,
    evidence_verifier: EvidenceVerifier = repository.verify_capture_evidence,
    deviations: DeviationSource = deviation_source,
) -> ControlTotals:
    """Reconcile one batch inside ``uow``: legacy values against the exact eRev values of the
    batch's bound comparison population, T-MIG-03 lines written once, status
    ``IMPORTED → RECONCILED``; returns the control totals."""
    batch = repository.get_batch(uow, batch_id)
    status = str(batch["status"])
    if status != MigrationStatus.IMPORTED.value:
        raise _refuse(NOT_IMPORTED_COPY.format(status=status))
    source = reconciliation.legacy_values(latest_rows(legacy_rows_reader(uow, batch_id)))
    try:
        # the capture / read boundary: a known population-validation failure (a supplier that
        # materialises an invalid binding, a foreign population, rows outside or short of the
        # captured output) names itself here; an unexpected error stays sanitized upstream
        population = population_reader(uow, batch)
        if population is None:
            raise _refuse(not_captured_copy(MigrationMode(str(batch["mode"]))))
        population.check_batch(batch)
        rows = population.bind(versions_reader(uow, population))
    except PopulationError as error:
        raise _refuse(str(error)) from error
    except ExactSourceError as error:
        # Codex 0629 N1: the reader's retained kind / parent / batch / operation / duplicate checks
        # raise ExactSourceError — mapped to the same named DG-PAR-05 refusal as the evidence and
        # trace checks below, never left to the registry's sanitized generic failure
        raise _evidence_failure(error) from error
    try:
        # the retained producing input of every bound version is verified first (Codex 0515 R1),
        # then every bound version's OWN trace is validated (id / book / hash), including a version
        # whose captured output is empty — a check driven by rows alone would skip it
        evidence_verifier(uow, population)
        lookups: dict[UUID, NodeLookup] = {
            ref.contract_version_id: trace_loader(uow, ref) for ref in population.versions
        }
        erev = exact_values.erev_values(
            rows, lambda row: lookups[UUID(str(row["contract_version_id"]))]
        )
    except ExactSourceError as error:
        raise _evidence_failure(error) from error
    lines = reconciliation.lines(source, erev, deviations())
    totals = reconciliation.control_totals(lines)
    if totals.unexplained:
        raise _refuse(UNEXPLAINED_COPY.format(count=totals.unexplained))
    repository.insert_reconciliation_lines(uow, batch_id, lines, exception_items={})
    repository.transition(
        uow,
        batch_id,
        to_status=MigrationStatus.RECONCILED,
        expected_status=MigrationStatus.IMPORTED,
        job_id=job_id,
    )
    return totals


def _import_refuse(detail: str) -> Problem:
    return Problem(
        "invalid-transition",
        detail,
        errors=[ProblemError(field="migration_id", rule_id=_IMPORT_RULE, message=detail)],
    )


@contextmanager
def spooled_source(jc: JobContext, uow: UnitOfWork, batch: Mapping[str, Any]) -> Iterator[Path]:
    """ONE read-only spool lifetime for the batch's stored source (Codex 0727 follow-through (a)):
    the object is opened through the runtime's file store (``files.store.open_file``; REQ-MIG-004:
    opened from a copy, never modified), spooled to a temporary file that lives for the block —
    rows are materialised and the profile computed and digest-checked while it exists — and is
    removed on exit, on success or failure."""
    import tempfile

    from erev_api.files.store import open_file

    runtime = jc.runtime
    if runtime.files is None or runtime.keyring is None:
        raise _import_refuse("The worker has no file store or key ring; the source cannot be read.")
    _row, stream = open_file(
        uow.session,
        UUID(str(batch["source_file_id"])),
        files=runtime.files,
        keyring=runtime.keyring,
    )
    spooled = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    path = Path(spooled.name)
    try:
        with spooled:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                spooled.write(chunk)
        yield path
    finally:
        path.unlink(missing_ok=True)


def legacy_source(
    jc: JobContext, uow: UnitOfWork, batch: Mapping[str, Any]
) -> tuple[LegacyRow, ...]:
    """The legacy rows of the batch's stored source, materialised inside the spool lifetime."""
    with spooled_source(jc, uow, batch) as path:
        return legacy_db.rows(path)


def legacy_source_with_ssp(
    jc: JobContext, uow: UnitOfWork, batch: Mapping[str, Any]
) -> tuple[tuple[LegacyRow, ...], tuple[Mapping[str, str | None], ...]]:
    """The legacy rows AND the ``SKU_SSP`` rows of the stored source, both materialised inside ONE
    spool lifetime (04 rev 1.72: the import re-verifies the ``SKU_SSP`` digest the profile bound).

    This is the import's read of its source, and the import moves the batch to ``IMPORTING`` —
    from where it holds the file (``file_evidence``: ``MIGRATION_CAPTURED``) — in the same
    transaction. The file's row is therefore locked first, to the end of that transaction, so
    that the import and a shred of the file see each other: an import that waited finds the file
    shredded at the read below (``open_file``: ``FILE_SHREDDED``), and a shred that waited finds
    the migration holding the file (04 T-PLT-29 "A document a rule asks for"; dev-guide
    DG-KRN-FILE-08; item EVIDENCE-COUNT-SHREDDED-1)."""
    from erev_api.files.store import lock_readable

    lock_readable(uow.session, [batch["source_file_id"]])
    with spooled_source(jc, uow, batch) as path:
        return legacy_db.rows(path), legacy_db.sku_ssp_rows(path)


def import_batch(
    uow: UnitOfWork,
    batch_id: UUID,
    *,
    job_id: UUID | None = None,
    params: Mapping[str, Any] | None = None,
    rows: Sequence[LegacyRow],
    applier: capture.Applier | None = None,
    sku_ssp_rows: Sequence[Mapping[str, str | None]] = (),
) -> Mapping[str, Any]:
    """Import one OPENING_BALANCES batch inside ``uow`` from its legacy ``rows``: stage, store the
    legacy rows (T-MIG-02), raise the S07-R-03 findings, dry-run and capture (T-MIG-04 / T-MIG-05),
    ``PROFILED → IMPORTING → IMPORTED``. Returns the profile counts written."""
    batch = repository.get_batch(uow, batch_id)
    status = str(batch["status"])
    if str(batch["mode"]) != MigrationMode.OPENING_BALANCES.value:
        raise _import_refuse(REPLAY_IMPORT_COPY)
    if status in RECOVERABLE_STATES and job_id is not None:
        # a retry after the durable commit — before the job settled, or after later phases moved
        # the batch on (Codex 0422 lifecycle; 0515 C1): the SAME operation's complete capture is
        # recognised and its result returned — no re-run, no re-insert, no numbers consumed, no
        # later job_id overwritten, no status moved backward; another operation's capture is
        # refused by name
        if str(batch.get("capture_operation_id")) != str(job_id):
            raise _import_refuse(
                repository.FOREIGN_CAPTURE_COPY.format(
                    what=f"operation {batch.get('capture_operation_id')} vs this job {job_id}"
                )
            )
        recovered = repository.captured_operation(uow, batch)
        if recovered is None:
            raise _import_refuse(
                repository.FOREIGN_CAPTURE_COPY.format(what=f"{status} without a capture")
            )
        return {**dict(batch.get("profile") or {}), **recovered, "recovered": True}
    if status != MigrationStatus.PROFILED.value:
        raise _import_refuse(NOT_PROFILED_COPY.format(status=status))
    if job_id is None:
        raise _import_refuse(capture.NO_OPERATION_COPY)
    cutover = batch["cutover_date"]
    if cutover is None:
        # D-98 candidate 128 / Codex 0727: the CHECK admits a NULL until /import binds the date; the
        # import phase never consumes one — refused by name before staging, dry run or capture
        raise _import_refuse(NO_CUTOVER_COPY)
    # 04 rev 1.72 (D-98 133 AMENDMENT 4): the spooled source's SKU_SSP digest must equal the one the
    # PROFILE bound and the /import confirmation carried — a mismatch refuses by name BEFORE
    # staging,
    # the dry run or any write
    bound_digest = str(
        (params or {}).get("sku_ssp_sha256")
        or (batch.get("profile") or {}).get("sku_ssp_sha256")
        or ""
    )
    found_digest = legacy_db.sku_ssp_digest(sku_ssp_rows)
    if not bound_digest:
        raise _import_refuse(SKU_SSP_UNBOUND_COPY)
    if found_digest != bound_digest:
        raise _import_refuse(SKU_SSP_CHANGED_COPY.format(found=found_digest, expected=bound_digest))
    parameters = batch_parameters(dict((params or {}).get("batch_parameters") or {}))
    # Codex 1227 F1: the CONFIRMED entity mapping (immutable in the job params and the /import
    # audit) is applied to every staged contracting / performing entity identity; the legacy rows
    # keep the original Selling Entity text (T-MIG-02) — the dry run then requires the TARGET code
    entity_codes = {
        str(row["legacy_name"]): str(row["entity_code"])
        for row in (params or {}).get("entity_mapping") or []
    }
    staging = opening_balances.stage(rows, cutover, parameters, entity_codes=entity_codes)
    problem = opening_balances.validate_cutover(cutover, staging_latest(staging))
    if problem is not None:
        raise Problem("validation-failed", opening_balances.CUTOVER_COPY, errors=[problem])
    # IMPORTING with the operation identity (= this job's id, durable in its own column — later
    # phases overwrite job_id, never capture_operation_id); all of it commits with IMPORTED in ONE
    # outer transaction after the savepoint rollback, or none of it persists (Codex 0408)
    repository.transition(
        uow,
        batch_id,
        to_status=MigrationStatus.IMPORTING,
        expected_status=MigrationStatus.PROFILED,
        job_id=job_id,
        capture_operation_id=job_id,
        started_at=uow.now,
    )
    batch = {**batch, "capture_operation_id": job_id, "status": MigrationStatus.IMPORTING.value}
    stored = repository.insert_legacy_rows(uow, batch_id, rows)
    _raise_findings(uow, batch, staging)
    # 04 LM-CL-09 / LM-CL-03 rev 1.64 (D-98 candidate 133): the CONFIRMED entity and product
    # writers run here — the outer transaction (durable with IMPORTED, or nothing), before the dry
    # run, under the job's principal; idempotent by code; _check_prerequisites stays unchanged
    confirmed = dict(params or {})
    replay_request = confirmed.get("ssp_replay_request_id")
    plan = prerequisites.plan(
        uow.session,
        staging,
        resolved_entities=list(confirmed.get("resolved_entities") or []),
        create_missing_entities=bool(confirmed.get("create_missing_entities", True)),
        create_missing_products=bool(confirmed.get("create_missing_products", True)),
        sku_ssp_rows=sku_ssp_rows,
    )
    created = prerequisites.apply(
        uow,
        batch_id,
        plan,
        replay_request_id=None if replay_request is None else UUID(str(replay_request)),
        migration_no=str(batch.get("migration_no") or ""),
        sku_ssp_sha256=bound_digest,
    )
    captured = capture.dry_run(uow, batch, staging, applier=applier)
    versions, obligations = repository.insert_population(uow, batch_id, captured)
    profile = {
        **dict(batch.get("profile") or {}),
        "contracts": len(staging.contracts),
        "legacy_pob_rows": staging.legacy_pob_rows,
        "obligations": staging.obligation_count,
        "vc_elements": staging.vc_count,
        "migrated_rows": stored,
        "captured_versions": versions,
        "captured_obligation_versions": obligations,
        "findings": len(staging.findings),
        # 04 LM-CL-09 / LM-CL-03 rev 1.64: what the confirmed writers created for this batch
        "created_entities": sorted(created.entity_ids),
        "created_products": sorted(created.product_ids),
        # 04 rev 1.72: the replayed LEGACY-SKU-SSP versions the MIGRATION_PROMOTION content will
        # name
        "replayed_ssp_versions": created.replayed_ssp_versions(bound_digest),
    }
    repository.transition(
        uow,
        batch_id,
        to_status=MigrationStatus.IMPORTED,
        expected_status=MigrationStatus.IMPORTING,
        profile=profile,
        finished_at=uow.now,
    )
    return profile


def batch_parameters(values: Mapping[str, object]) -> field_mapping.BatchParameters:
    """The POLICIES §1.13 batch parameters of the import request (API-R-48 ``/import``
    ``batch_parameters``), validated as the route validates them; the FORCED values stay fixed."""
    errors = field_mapping.validate_batch_parameters(values)
    if errors:
        raise Problem("validation-failed", errors=errors)
    defaults = field_mapping.BatchParameters()
    return field_mapping.BatchParameters(
        nondistinct_mapping=str(
            values.get(field_mapping.NONDISTINCT_MAPPING, defaults.nondistinct_mapping)
        ),
        material_right_convention=str(
            values.get(field_mapping.MATERIAL_RIGHT_CONVENTION, defaults.material_right_convention)
        ),
    )


def staging_latest(staging: opening_balances.Staging) -> Any:
    """The latest legacy period of the staged contracts (None when no period is dated)."""
    periods = [item.latest_period for item in staging.contracts]
    return max(periods) if periods else None


def _raise_findings(
    uow: UnitOfWork, batch: Mapping[str, Any], staging: opening_balances.Staging
) -> None:
    """S07-R-03 findings as exception items (04 table 15.4-C, source MIGRATION), one per finding."""
    from erev_api.domain.imports.exceptions import raise_exception_item, severity_of
    from erev_api.enums import ExceptionSource

    for finding in staging.findings:
        raise_exception_item(
            uow,
            source=ExceptionSource.MIGRATION,
            code=finding.code,
            severity=severity_of("ERROR"),
            message=f"{finding.subject_key}: {dict(finding.detail)}",
            dedupe=f"{ExceptionSource.MIGRATION.value}:{finding.code}:{batch['id']}:{finding.subject_key}",
            business_key=finding.subject_key,
        )


def import_failed(uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
    """The import's terminal hook (``registry.task(on_failure=…)``; runs in the transaction that
    ends the job FAILED after its last attempt): a batch still PROFILED moves to FAILED with the
    problem (E-76); a batch IMPORTED with a verified capture of THIS job's operation is left as it
    is — a completed capture is never degraded (Codex 0422 lifecycle); anything else is left for
    the operator with the problem recorded on the job only."""
    batch_id = UUID(str(params["migration_id"]))
    batch = repository.get_batch(uow, batch_id)
    status = str(batch["status"])
    job_id = str(problem.get("instance", "")).rsplit("/", 1)[-1]
    if status in RECOVERABLE_STATES:
        if str(batch.get("capture_operation_id")) == job_id:
            repository.captured_operation(uow, batch)  # raises when the capture is not complete
        return
    if status == MigrationStatus.PROFILED.value:
        repository.transition(
            uow,
            batch_id,
            to_status=MigrationStatus.FAILED,
            expected_status=MigrationStatus.PROFILED,
            problem=dict(problem),
            finished_at=uow.now,
        )


PHASE_PROFILE: Final = "PROFILE"
PHASE_IMPORT: Final = "IMPORT"
PHASES: Final = frozenset({PHASE_PROFILE, PHASE_IMPORT})
NOT_UPLOADED_COPY: Final = (
    "The migration is {status}; profiling needs an UPLOADED migration (SCREENS_B §10.2)."
)
SOURCE_CHANGED_COPY: Final = (
    "The stored legacy database's SHA-256 {found} is not the migration's source digest {expected}."
)
UNKNOWN_PHASE_COPY: Final = 'MIGRATION_IMPORT phase {phase!r} is not one of "PROFILE", "IMPORT".'
NO_CUTOVER_COPY: Final = (
    "The migration has no cutover date; confirm the mapping (POST /migrations/{id}/import) before "
    "the import runs."
)
FOREIGN_PROFILE_COPY: Final = "The profiling job {job_id} is not the migration's job {claimed}."
# 04 rev 1.72 (D-98 133 AMENDMENT 4): the SKU_SSP digest re-verification before the replay writer
# runs
SKU_SSP_CHANGED_COPY: Final = (
    "The legacy database's SKU_SSP table (digest {found}) is not the one the profile bound "
    "({expected}); "
    "profile the migration again before importing."
)
SKU_SSP_UNBOUND_COPY: Final = (
    "The migration's profile carries no SKU_SSP digest (profiled before the legacy SSP replay "
    "existed); "
    "profile the migration again before importing."
)


def profile_batch(
    uow: UnitOfWork, batch_id: UUID, *, job_id: UUID, source: Path | None
) -> Mapping[str, Any]:
    """The profiling phase (API-R-48 ``POST /migrations/{id}/profile``; SCREENS_B §10.2 "Upload and
    profile", §10.3 "Key figures"): ``legacy_db.profile`` over the read-only spooled copy at
    ``source``, the profile's SHA-256 checked against the batch's ``source_sha256`` (REQ-MIG-004),
    T-MIG-01 ``profile`` written, ``PROFILING → PROFILED``. Writes no T-MIG-02 to T-MIG-05 row; the
    import phase's one-import-per-batch rule is untouched."""
    batch = repository.get_batch(uow, batch_id)
    status = str(batch["status"])
    claimed = str(batch.get("job_id"))
    if status == MigrationStatus.PROFILED.value and claimed == str(job_id):
        # success re-entry (Codex 0727 (b) / 0801 R3): THIS job's profiling already committed — the
        # stored profile is returned after its provenance is checked (the profile's digest is the
        # batch's source digest); no rework, no second transition, nothing degraded
        stored = dict(batch.get("profile") or {})
        expected = str(batch["source_sha256"]).strip()
        if str(stored.get("source_sha256")) != expected:
            raise _import_refuse(
                SOURCE_CHANGED_COPY.format(found=stored.get("source_sha256"), expected=expected)
            )
        return {**stored, "recovered": True}
    if status != MigrationStatus.PROFILING.value:
        raise _import_refuse(NOT_UPLOADED_COPY.format(status=status))
    if claimed != str(job_id):
        raise _import_refuse(FOREIGN_PROFILE_COPY.format(job_id=job_id, claimed=claimed))
    if source is None:
        raise _import_refuse("The profiling phase needs the spooled source.")
    found = legacy_db.profile(source)
    expected = str(batch["source_sha256"]).strip()
    if found.source_sha256 != expected:
        raise _import_refuse(
            SOURCE_CHANGED_COPY.format(found=found.source_sha256, expected=expected)
        )
    profile = found.as_json()
    repository.transition(
        uow,
        batch_id,
        to_status=MigrationStatus.PROFILED,
        expected_status=MigrationStatus.PROFILING,
        profile=profile,
        finished_at=uow.now,
    )
    return profile


def profile_failed(uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]) -> None:
    """The profiling phase's share of the terminal hook: a batch still PROFILING under this job
    moves to FAILED with the problem (E-76; SCREENS_B §10.3 "<job label> failed. Nothing was
    committed.")."""
    batch_id = UUID(str(params["migration_id"]))
    batch = repository.get_batch(uow, batch_id)
    job_id = str(problem.get("instance", "")).rsplit("/", 1)[-1]
    # operation-bound (Codex 0727 (b)): only the job holding the PROFILING claim settles it
    if (
        str(batch["status"]) == MigrationStatus.PROFILING.value
        and str(batch.get("job_id")) == job_id
    ):
        repository.transition(
            uow,
            batch_id,
            to_status=MigrationStatus.FAILED,
            expected_status=MigrationStatus.PROFILING,
            problem=dict(problem),
            finished_at=uow.now,
        )


def migration_failed(
    uow: UnitOfWork, params: Mapping[str, Any], problem: Mapping[str, Any]
) -> None:
    """``MIGRATION_IMPORT`` terminal hook, dispatched on ``params.phase`` (default IMPORT)."""
    if str((params or {}).get("phase") or PHASE_IMPORT) == PHASE_PROFILE:
        profile_failed(uow, params, problem)
    else:
        import_failed(uow, params, problem)


def import_unit_of_work(jc: JobContext) -> AbstractContextManager[UnitOfWork]:
    """The import phase's OUTER unit of work under the LIMITED migration writer authority (Codex
    1106 R1; 04 §17.2 rev 1.64 LM-CL-09): the registered worker runs every job as the plain SYSTEM
    principal, whose permission set is EMPTY, so the confirmed entity / product writers
    (``prerequisites.apply`` → the reference writers → ``_authorize_reference``) would be refused
    on the real path. This opens the SAME persistent outer transaction — tenant and on-behalf-of
    attribution, audit buffer, after-commit hooks unchanged — as ``capture.migration_principal``
    (SYSTEM with exactly ``MIGRATION_PERMISSIONS``, the ``imports.diff.import_principal`` pattern);
    no other job kind gains a permission, reference authorization is not bypassed, and the isolated
    capture child is untouched. The profiling phase and the reconcile keep the plain job
    principal."""
    principal = capture.migration_principal(
        jc.principal.tenant_id, on_behalf_of=jc.principal.on_behalf_of_id
    )
    return system_unit_of_work(jc.runtime, principal, request_id=f"job-{jc.job_id}", clock=jc.clock)


@task(JobKind.MIGRATION_IMPORT, on_failure=migration_failed)
def import_migration(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``MIGRATION_IMPORT``: ``params.phase`` ``"PROFILE"`` profiles the UPLOADED migration named by
    ``params.migration_id`` (API-R-48 ``/profile``); ``"IMPORT"`` (the default) imports the
    OPENING_BALANCES migration with ``params.batch_parameters`` (API-R-48 ``/import``)."""
    batch_id = UUID(str(params["migration_id"]))
    phase = str(params.get("phase") or PHASE_IMPORT)
    if phase not in PHASES:
        raise _import_refuse(UNKNOWN_PHASE_COPY.format(phase=phase))
    if phase == PHASE_PROFILE:
        with jc.unit_of_work() as uow:
            batch = repository.get_batch(uow, batch_id)
            re_entry = str(batch["status"]) == MigrationStatus.PROFILED.value and str(
                batch.get("job_id")
            ) == str(jc.job_id)
            if re_entry:
                # success re-entry is settled from the stored profile BEFORE the source is reopened
                profile = profile_batch(uow, batch_id, job_id=jc.job_id, source=None)
            else:
                with spooled_source(jc, uow, batch) as source:
                    profile = profile_batch(uow, batch_id, job_id=jc.job_id, source=source)
            uow.commit()
        return JobOutcome(
            state="SUCCEEDED",
            result={"href": f"/api/v1/migrations/{batch_id}", "profile": dict(profile)},
        )
    with import_unit_of_work(jc) as uow:
        batch = repository.get_batch(uow, batch_id)
        # completed-operation recovery needs only the stored capture: it is checked BEFORE the
        # stored legacy source is reopened, so a source that cannot be read never blocks it
        # (Codex 0533 L2)
        recoverable = str(batch["status"]) in RECOVERABLE_STATES and str(
            batch.get("capture_operation_id")
        ) == str(jc.job_id)
        rows: Sequence[LegacyRow] = ()
        ssp_rows: Sequence[Mapping[str, str | None]] = ()
        if not recoverable:
            rows, ssp_rows = legacy_source_with_ssp(jc, uow, batch)
        profile = import_batch(
            uow, batch_id, job_id=jc.job_id, params=params, rows=rows, sku_ssp_rows=ssp_rows
        )
        uow.commit()
    return JobOutcome(
        state="SUCCEEDED",
        result={"href": f"/api/v1/migrations/{batch_id}", "profile": dict(profile)},
    )


@task(JobKind.MIGRATION_RECONCILE)
def reconcile(jc: JobContext, params: Mapping[str, Any]) -> JobOutcome:
    """``MIGRATION_RECONCILE``: reconcile the migration named by ``params.migration_id``."""
    batch_id = UUID(str(params["migration_id"]))
    with jc.unit_of_work() as uow:
        totals = reconcile_batch(uow, batch_id, job_id=jc.job_id)
        uow.commit()
    return JobOutcome(
        state="SUCCEEDED",
        result={"href": f"/api/v1/migrations/{batch_id}", "counts": totals.as_json()},
    )
