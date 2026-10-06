"""The opening-balance import's dry run and its DURABLE capture (BUILD_SPEC LMG-2
``MIGRATION_IMPORT``; 04 T-MIG-01 note, T-MIG-04, T-MIG-05 — rev 1.60; ENGINE_SPEC S07-R-02,
S07-R-11; D-98 candidates 122 (durable capture) and 126 (the O2 shape); lane record
``docs/reviews/loop/prod/F-LMG.md`` §24).

Mode (a) creates no ``contract`` row before promotion (BS3-D-26): the import books, activates and
establishes every staged contract INSIDE A SAVEPOINT through the platform's own commands
(``commands.book_contract``, the VC element of every staged ``VC`` row — S07-R-11 / POL-213,
``vc_elements``, 04 rev 1.97 —, ``events/stream.append_events`` with ``CONTRACT_ACTIVATED`` and
``OPENING_BALANCE_ESTABLISHED``, ``compute_job.compute_group`` — the engine computes synchronously,
never deferred), READS the computed result while the rows exist — the contract version, its
computation's provenance, its own calc trace, its obligation versions, the group's member contracts
at ``known_at`` and the ``OPENING_BALANCE_ESTABLISHED`` input that names the batch and cutover —
then ROLLS THE SAVEPOINT BACK and hands the capture to the repository, which stores it in T-MIG-04 /
T-MIG-05. The reconcile (``MIGRATION_RECONCILE``) binds and reads that capture, never a live
version (``population``).

Refusals are by name (no silent substitution, no fabrication): a staged row pending a POL-211
decision; POL-212 option records (their writer is a later slice); a booking prerequisite the tenant
lacks — a ``Selling Entity`` code, a product for a legacy SKU, a product whose default template is
not the row's parity template, the reporting currency not enabled (creating them is the LMG-2
import-phase follow-up: LM-CL-09 ``create_missing_entities`` needs calendar / time-zone inputs the
mapping does not carry; products come from the SKU import in mode (b)); a legacy money value the
REGISTERED ``OPENING_BALANCE_ESTABLISHED`` payload version cannot carry — under version 1
``money.MoneyStr`` admits four decimal places while S07-R-11 says "values as stored" (the conflict
D-98 candidate 127 resolved with payload version 2, ``ExactMoneyIn``, 04 rev 1.61 — the registered
latest, under which only an amount beyond the API-C-06 bound is refused); a computation the engine
refused. The customer of a migrated contract follows the
legacy_v1 import's convention (``LEGACY-<contract>``, T-REF-19 legacy note).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final, Protocol
from uuid import UUID

from erev_engine.errors import EngineError
from erev_engine.upgrade import encode_input, raw_digest
from sqlalchemy import and_, or_, select

from erev_api import money
from erev_api.auth.principal import Principal, system_principal
from erev_api.db.tables import (
    calc_trace,
    combination_group_member,
    contract,
    contract_computation,
    contract_version,
    obligation_version,
    pob_template,
    product,
    tenant,
    tenant_currency,
)
from erev_api.db.tables.migration import POPULATION_BOOK
from erev_api.domain.contracts import activation, bundles, computation, repo
from erev_api.domain.contracts.commands import book_contract
from erev_api.domain.imports.legacy_v1.contract_setup import (
    VC_ELEMENT,
    VcElement,
    write_vc_element,
)
from erev_api.domain.imports.legacy_v1.sku_ssp import approved_midpoints
from erev_api.domain.migration.opening_balances import (
    ContractOpening,
    Staging,
    booking_payload,
    opening_payload,
)
from erev_api.domain.migration.population import ComparisonPopulation, VersionRef
from erev_api.domain.reference.commands import create_customer
from erev_api.enums import ComputationTrigger, ContractEventType, MigrationMode, SourceSystem
from erev_api.events.payloads import (
    LATEST_SCHEMA_VERSION,
    PAYLOADS,
    ContractActivatedV1,
    ContractBookedV1,
)
from erev_api.events.stream import EventIn, append_events
from erev_api.problems import Problem, ProblemError
from erev_api.schemas.customers import CustomerIn
from erev_api.uow import UnitOfWork

__all__ = [
    "CUSTOMER_PREFIX",
    "DOCUMENT_REF",
    "MONEY_PLACES",
    "OPENING_MONEY_MEMBERS",
    "OPENING_QUANTITY_MEMBERS",
    "RULE",
    "MIGRATION_PERMISSIONS",
    "Applied",
    "Applier",
    "Capture",
    "CaptureError",
    "CapturedObligation",
    "CapturedVersion",
    "Member",
    "PlatformApplier",
    "booking_body",
    "canonical_row",
    "dry_run",
    "migration_principal",
    "migration_unit",
    "exact_text",
    "opening_body",
    "opening_effective_date",
    "opening_event_binding",
    "opening_payload_model",
    "platform_applier",
    "read_version",
    "vc_elements",
]

RULE: Final = "LMG-2"
CUSTOMER_PREFIX: Final = "LEGACY-"  # the legacy_v1 import's convention (T-REF-19 legacy note)
DOCUMENT_REF: Final = "migration:{migration_no}"  # BS3-D-26
MONEY_PLACES: Final = 4  # money.MoneyStr: ^-?[0-9]{1,20}(\\.[0-9]{1,4})?$
# OPENING_BALANCE_ESTABLISHED.obligations[] members (events/payloads.OpeningObligationV1).
OPENING_QUANTITY_MEMBERS: Final = (
    "delivered_quantity_cum",
    "ssp_delivered_cum",
    "remaining_quantity",
    "remaining_ssp",
)
OPENING_MONEY_MEMBERS: Final = (
    "revenue_cum",
    "billed_cum",
    "catch_up_cum",
    "pre_standard_revenue_cum",
    "remaining_allocation",
    "remaining_billing",
    "position_obligation",
    "netting_reclass_amount",
)
_MEASURE_COLUMNS: Final = (
    "original_allocated_exact",
    "remaining_quantity",
    "billed_cum",
    "revenue_cum",
    "remaining_allocation",
    "position_obligation",
    "netting_reclass_amount",
)
PENDING_COPY: Final = (
    "{count} staged row(s) await a POL-211 decision ({keys}); the import cannot book them."
)
OPTIONS_COPY: Final = (
    "{count} POL-212 option record(s) are staged; the option writer is a later slice, so the "
    "import refuses rather than book without them."
)
PREREQUISITE_COPY: Final = (
    "The tenant lacks a booking prerequisite of {contract}: {what}. Creating it is the "
    "import-phase follow-up (LM-CL-09 create_missing_entities; products from the SKU import); "
    "nothing is invented."
)
PRECISION_COPY: Final = (
    "{contract} {key} {member} = {value} has {places} decimal places; the "
    "OPENING_BALANCE_ESTABLISHED money members accept at most 4 (money.MoneyStr) while "
    "ENGINE_SPEC S07-R-11 says 'values as stored' — a specification conflict raised to the "
    "supervisor; the import does not round."
)
COMPUTATION_COPY: Final = (
    "The dry-run computation of {contract} ended {status}; the import captures nothing for it."
)
NOT_OPENING_COPY: Final = "The dry run captures OPENING_BALANCES migrations; this one is {mode}."
NO_OPERATION_COPY: Final = (
    "The migration carries no capture_operation_id; the import job writes it with IMPORTING before "
    "the dry run (04 T-MIG-01 rev 1.60)."
)
# The internal migration principal (Codex 0422 (c); the imports.diff.import_principal pattern):
# SYSTEM with the scopes the dry run's commands need, every entity.
MIGRATION_PERMISSIONS: Final = frozenset({"contract.create", "masterdata.maintain"})


class CaptureError(ValueError):
    """The dry run's computed result cannot be read as one capture (no version, several versions,
    no trace, no OPENING_BALANCE_ESTABLISHED input naming the batch): the import refuses."""


def _refuse(detail: str, *, findings: str | None = None) -> Problem:
    errors = [ProblemError(field="migration_id", rule_id=RULE, message=detail)]
    if findings:
        # the engine's CV-15 finding JSON (rule, sub-check, reason, figures) travels with the
        # refusal so the job problem names WHY the dry run refused (integrated batch #9)
        errors.append(ProblemError(field="migration_id", rule_id=RULE, message=findings))
    return Problem("validation-failed", detail, errors=errors)


def computation_refusal(external_id: str, error: EngineError) -> Problem:
    """The dry-run computation's refusal: the detail names the contract and the engine code; the
    engine's finding JSON (``EngineError.detail["findings"]``, CV-15) rides as a second error."""
    findings = error.detail.get("findings")
    return _refuse(
        COMPUTATION_COPY.format(contract=external_id, status=f"refused: {error}"),
        findings=str(findings) if findings else None,
    )


@dataclass(frozen=True, slots=True)
class Member:
    contract_id: UUID
    contract_external_id: str


@dataclass(frozen=True, slots=True)
class CapturedVersion:
    """One T-MIG-04 row before storage: the identities (tokens once the savepoint rolls back), the
    computation's provenance, the batch / cutover read back from the OPENING_BALANCE_ESTABLISHED
    input, the authoritative members, the expected output and the trace mirror."""

    contract_version_id: UUID
    version_no: int
    book_code: str
    combination_group_id: UUID
    status_in_book: str
    contract_computation_id: UUID
    input_sha256: str
    output_sha256: str
    engine_version: str
    engine_release_id: UUID | None
    known_at: datetime
    bundle_known_at: datetime
    cutover_date: date
    payload_migration_batch_id: UUID
    opening_event_id: UUID
    opening_event_key: str
    opening_event_binding_sha256: str
    members: tuple[Member, ...]
    expected_output_captured: bool
    obligation_version_ids: tuple[UUID, ...]
    capture_operation_id: UUID
    calc_trace_id: UUID
    format_version: int
    node_count: int
    root_measures: Mapping[str, Any]
    trace_sha256: str
    trace: Mapping[str, Any]
    input_evidence: Mapping[str, Any]  # the parsed T-CON-25 evidence document
    input_evidence_sha256: str  # raw_digest of its canonical bytes

    def ref(self) -> VersionRef:
        return VersionRef(
            contract_ids=frozenset(member.contract_id for member in self.members),
            contract_version_id=self.contract_version_id,
            calc_trace_id=self.calc_trace_id,
            book_code=self.book_code,
            obligation_version_ids=frozenset(self.obligation_version_ids),
            cutover_date=self.cutover_date,
            payload_migration_batch_id=self.payload_migration_batch_id,
            trace_sha256=self.trace_sha256,
            expected_output_captured=self.expected_output_captured,
        )


@dataclass(frozen=True, slots=True)
class CapturedObligation:
    """One T-MIG-05 row before storage: the nine-measure sources as ``obligation_version`` stores
    them, the trace-node binding and the full row as canonical evidence."""

    contract_version_id: UUID
    obligation_version_id: UUID
    contract_id: UUID
    contract_external_id: str
    obligation_key: str
    obligation_kind: str
    capture_operation_id: UUID
    original_allocated_exact: Decimal
    remaining_quantity: Decimal
    billed_cum: Decimal
    revenue_cum: Decimal
    remaining_allocation: Decimal
    position_obligation: Decimal
    netting_reclass_amount: Decimal
    trace_nodes: Mapping[str, Any]
    row: Mapping[str, Any]
    row_sha256: str


@dataclass(frozen=True, slots=True)
class Capture:
    batch_id: UUID
    capture_operation_id: UUID
    cutover_date: date
    versions: tuple[CapturedVersion, ...]
    obligations: tuple[CapturedObligation, ...]

    def population(self, batch: Mapping[str, Any]) -> ComparisonPopulation:
        return ComparisonPopulation(
            batch_id=UUID(str(batch["id"])),
            mode=MigrationMode(str(batch["mode"])),
            cutover_date=batch.get("cutover_date"),
            book_code=POPULATION_BOOK,
            versions=tuple(version.ref() for version in self.versions),
        )


@dataclass(frozen=True, slots=True)
class Applied:
    """What the applier hands the reader: the contract and group it created, the ACTUAL producing
    bundle's record-time cutoff and selected member ids (Codex 0422 (a)), the stream version of the
    OPENING_BALANCE_ESTABLISHED event it appended and the event key the bundle shows it under
    ((b), (g)), and the persisted computation's input hash (= ``bundle.sha256()``)."""

    contract_id: UUID
    combination_group_id: UUID
    bundle_known_at: datetime
    bundle_member_keys: frozenset[str]  # GroupInput.member_contract_keys: external ids
    opening_event_key: str
    opening_payload_sha256: str  # the bundle event's payload hash (the hash-bound side, Codex 0605)
    input_sha256: str
    input_evidence: bytes  # encode_input(bundle): the T-CON-25 evidence bytes (Codex 0515 R1)


class Applier(Protocol):
    """Books, activates, establishes and computes one staged contract inside the caller's
    savepoint; the platform default is ``PlatformApplier``."""

    def apply(
        self, uow: UnitOfWork, *, batch: Mapping[str, Any], contract: ContractOpening
    ) -> Applied: ...


# --- evidence encoding ----------------------------------------------------------------------------


def _plain(value: object) -> object:
    """The stored representation as JSON text: decimals and dates as text, ids as text."""
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]
    if value is None or isinstance(value, str | bool | int | float):
        return value
    return str(getattr(value, "value", value))


def opening_event_binding(event_id: UUID, event_key: str, payload_sha256: str) -> str:
    """The capture-time association of the declared opening event UUID (a token of a rolled-back
    row) with its hash-bound logical event in the retained bundle: SHA-256 of
    ``<event id> | <event key> | <payload_sha256>`` (04 T-MIG-04 rev 1.60; Codex 0605 R1). The
    reader recomputes it from the row's UUID and the decoded event; a token-only change
    mismatches."""
    return hashlib.sha256(f"{event_id}|{event_key}|{payload_sha256}".encode()).hexdigest()


def canonical_row(row: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    """The T-MIG-05 ``row`` document (every column, values as stored text) and its SHA-256 over the
    canonical JSON (sorted keys, no spaces)."""
    document = {str(key): _plain(value) for key, value in row.items()}
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return document, hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# --- the read, inside the savepoint ---------------------------------------------------------------


def _members(session: Any, group_id: UUID, known_at: datetime) -> tuple[Member, ...]:
    member = combination_group_member
    statement = (
        select(member.c.contract_id, contract.c.external_id)
        .select_from(
            member.join(
                contract,
                and_(
                    contract.c.tenant_id == member.c.tenant_id,
                    contract.c.id == member.c.contract_id,
                ),
            )
        )
        .where(
            member.c.combination_group_id == group_id,
            member.c.valid_from_known_at <= known_at,
            or_(member.c.valid_to_known_at.is_(None), member.c.valid_to_known_at > known_at),
        )
        .order_by(contract.c.external_id)
    )
    return tuple(Member(UUID(str(row[0])), str(row[1])) for row in session.execute(statement).all())


def _opening_input(
    session: Any, contract_id: UUID, expected_key: str
) -> tuple[UUID, Mapping[str, Any]]:
    """The one OPENING_BALANCE_ESTABLISHED event of the contract: its id and payload. The event
    must be the one the producing bundle consumed (``expected_key`` = the bundle's event key
    ``<external_id>/EV-<stream_version>``, CV-22) and must name a migration (Codex 0422 (b))."""
    events = [
        row
        for row in repo.stream(session, contract_id)
        if str(getattr(row["event_type"], "value", row["event_type"]))
        == ContractEventType.OPENING_BALANCE_ESTABLISHED.value
    ]
    if len(events) != 1:
        raise CaptureError(
            f"contract {contract_id} carries {len(events)} OPENING_BALANCE_ESTABLISHED events; the "
            "dry run appends exactly one"
        )
    event = events[0]
    payload = dict(event["payload"] or {})
    if payload.get("migration_batch_id") is None:
        raise CaptureError(
            f"the OPENING_BALANCE_ESTABLISHED input of contract {contract_id} names no migration"
        )
    version = int(event["stream_version"])
    if not expected_key.endswith(f"/EV-{version:06d}"):
        raise CaptureError(
            f"the OPENING_BALANCE_ESTABLISHED event of contract {contract_id} (stream version "
            f"{version}) is not the event the producing bundle consumed ({expected_key})"
        )
    return UUID(str(event["id"])), payload


def read_version(
    session: Any, *, applied: Applied, capture_operation_id: UUID
) -> tuple[CapturedVersion, tuple[CapturedObligation, ...]]:
    """The dry run's computed result of one applied contract, read while its rows exist: exactly
    one contract version of the group in the migration book, its computation (whose
    ``input_sha256`` must be the applied bundle's), its own trace, its obligation versions
    (possibly none — D-98-78; ``expected_output_captured`` records that they were read), the
    members the producing bundle selected at its record-time cutoff (Codex 0422 (a)) and the
    OPENING_BALANCE_ESTABLISHED input that bundle consumed ((b), (g)). Anything else raises
    ``CaptureError``."""
    group_id = applied.combination_group_id
    versions = (
        session.execute(
            select(contract_version).where(
                contract_version.c.combination_group_id == group_id,
                contract_version.c.book_code == POPULATION_BOOK,
            )
        )
        .mappings()
        .all()
    )
    if len(versions) != 1:
        raise CaptureError(
            f"group {group_id} holds {len(versions)} versions in {POPULATION_BOOK}; the dry run "
            "computes exactly one"
        )
    version = dict(versions[0])
    version_id = UUID(str(version["id"]))
    computation = (
        session.execute(
            select(contract_computation).where(
                contract_computation.c.id == version["contract_computation_id"]
            )
        )
        .mappings()
        .one_or_none()
    )
    if computation is None:
        raise CaptureError(f"version {version_id} names no contract_computation")
    if str(computation["input_sha256"]) != applied.input_sha256:
        raise CaptureError(
            f"version {version_id} was computed from another bundle "
            f"({computation['input_sha256']} is not the applied {applied.input_sha256})"
        )
    trace = (
        session.execute(select(calc_trace).where(calc_trace.c.contract_version_id == version_id))
        .mappings()
        .one_or_none()
    )
    if trace is None or version["calc_trace_id"] is None:
        raise CaptureError(f"version {version_id} has no calc trace")
    if UUID(str(trace["id"])) != UUID(str(version["calc_trace_id"])):
        raise CaptureError(f"version {version_id}: calc_trace_id does not name its stored trace")
    rows = (
        session.execute(
            select(obligation_version, contract.c.external_id.label("contract_external_id"))
            .join(contract, contract.c.id == obligation_version.c.contract_id)
            .where(obligation_version.c.contract_version_id == version_id)
            .order_by(contract.c.external_id, obligation_version.c.obligation_key)
        )
        .mappings()
        .all()
    )
    members = _members(session, group_id, applied.bundle_known_at)
    if not members:
        raise CaptureError(
            f"group {group_id} has no member contract at {applied.bundle_known_at.isoformat()}"
        )
    if {member.contract_external_id for member in members} != applied.bundle_member_keys:
        raise CaptureError(
            f"group {group_id}: the members at the bundle cutoff are not the members the producing "
            "bundle selected"
        )
    opening_event_id, payload = _opening_input(
        session, applied.contract_id, applied.opening_event_key
    )
    obligations = tuple(
        _captured_obligation(dict(row), version_id, capture_operation_id) for row in rows
    )
    captured = CapturedVersion(
        contract_version_id=version_id,
        version_no=int(version["version_no"]),
        book_code=str(version["book_code"]),
        combination_group_id=group_id,
        status_in_book=str(getattr(version["status_in_book"], "value", version["status_in_book"])),
        contract_computation_id=UUID(str(version["contract_computation_id"])),
        input_sha256=str(computation["input_sha256"]),
        output_sha256=str(version["output_sha256"]),
        engine_version=str(computation["engine_version"]),
        engine_release_id=None
        if computation["engine_release_id"] is None
        else UUID(str(computation["engine_release_id"])),
        known_at=version["known_at"],
        bundle_known_at=applied.bundle_known_at,
        cutover_date=date.fromisoformat(str(payload["cutover_date"])),
        payload_migration_batch_id=UUID(str(payload["migration_batch_id"])),
        opening_event_id=opening_event_id,
        opening_event_key=applied.opening_event_key,
        opening_event_binding_sha256=opening_event_binding(
            opening_event_id, applied.opening_event_key, applied.opening_payload_sha256
        ),
        members=members,
        expected_output_captured=True,  # the rows were read (an empty tuple is observed, D-98-78)
        obligation_version_ids=tuple(item.obligation_version_id for item in obligations),
        capture_operation_id=capture_operation_id,
        calc_trace_id=UUID(str(trace["id"])),
        format_version=int(trace["format_version"]),
        node_count=int(trace["node_count"]),
        root_measures=dict(trace["root_measures"]),
        trace_sha256=str(trace["trace_sha256"]),
        trace=dict(trace["trace"]),
        input_evidence=json.loads(applied.input_evidence.decode("utf-8")),
        input_evidence_sha256=raw_digest(applied.input_evidence),
    )
    return captured, obligations


def _captured_obligation(
    stored: Mapping[str, Any], version_id: UUID, capture_operation_id: UUID
) -> CapturedObligation:
    row = dict(stored)
    external_id = str(row.pop("contract_external_id"))
    document, digest = canonical_row(row)
    measures = {column: Decimal(str(row[column])) for column in _MEASURE_COLUMNS}
    return CapturedObligation(
        contract_version_id=version_id,
        obligation_version_id=UUID(str(row["id"])),
        contract_id=UUID(str(row["contract_id"])),
        contract_external_id=external_id,
        obligation_key=str(row["obligation_key"]),
        obligation_kind=str(getattr(row["obligation_kind"], "value", row["obligation_kind"])),
        capture_operation_id=capture_operation_id,
        trace_nodes=dict(row["trace_nodes"] or {}),
        row=document,
        row_sha256=digest,
        **measures,
    )


# --- the dry run ----------------------------------------------------------------------------------


def migration_principal(tenant_id: UUID, on_behalf_of: UUID | None = None) -> Principal:
    """The internal principal of the dry run: SYSTEM with ``MIGRATION_PERMISSIONS`` on every
    entity (the ``imports.diff.import_principal`` pattern; Codex 0422 (c)) — a justified limited
    path, not a fixture bypass: admission, checklist evaluation and bounds run unchanged."""
    import dataclasses
    from types import MappingProxyType

    base = system_principal(tenant_id, on_behalf_of_id=on_behalf_of)
    return dataclasses.replace(
        base,
        permissions=MIGRATION_PERMISSIONS,
        permission_scopes=MappingProxyType({code: "*" for code in MIGRATION_PERMISSIONS}),
    )


def migration_unit(uow: UnitOfWork) -> UnitOfWork:
    """An ISOLATED child unit of work of the migration principal in the caller's transaction and
    instant: its own audit buffer and after-commit hooks, which are never committed nor handed
    over — the savepoint rollback discards the rows, the unit's discard drops the callbacks
    (Codex 0422 (e); the ``imports.diff.import_unit`` pattern)."""
    import dataclasses

    ctx = dataclasses.replace(
        uow.ctx, principal=migration_principal(uow.principal.tenant_id, uow.principal.id)
    )
    unit = UnitOfWork(
        ctx=ctx, session=uow.session, clock=uow.clock, keyring=uow.keyring, files=uow.files
    )
    unit.now = uow.now
    return unit


def dry_run(
    uow: UnitOfWork,
    batch: Mapping[str, Any],
    staging: Staging,
    *,
    applier: Applier | None = None,
    unit_factory: Any = None,
) -> Capture:
    """Book, activate, establish and compute every staged contract inside one savepoint through
    ``applier`` — running in an isolated child unit of work of the migration principal — read the
    computed results, roll the savepoint back (no ``contract`` row survives — BS3-D-26) and return
    the capture. The child's audit events and after-commit hooks are discarded with it; the
    caller's are untouched (the ``imports/diff._dry_run`` isolated-child pattern)."""
    mode = str(batch["mode"])
    if mode != MigrationMode.OPENING_BALANCES.value:
        raise _refuse(NOT_OPENING_COPY.format(mode=mode))
    operation = batch.get("capture_operation_id")
    if operation is None:
        raise _refuse(NO_OPERATION_COPY)
    if staging.pending:
        keys = ", ".join(f"{contract} {key}" for contract, key, _ in staging.pending)
        raise _refuse(PENDING_COPY.format(count=len(staging.pending), keys=keys))
    if staging.option_records:
        raise _refuse(OPTIONS_COPY.format(count=len(staging.option_records)))
    worker = platform_applier if applier is None else applier
    make_unit = migration_unit if unit_factory is None else unit_factory
    unit: UnitOfWork = make_unit(uow)
    session = unit.session
    savepoint = session.begin_nested()
    versions: list[CapturedVersion] = []
    obligations: list[CapturedObligation] = []
    try:
        applied = [worker.apply(unit, batch=batch, contract=item) for item in staging.contracts]
        for item in applied:
            version, rows = read_version(
                session, applied=item, capture_operation_id=UUID(str(operation))
            )
            versions.append(version)
            obligations.extend(rows)
    except CaptureError as error:
        raise _refuse(str(error)) from error
    finally:
        savepoint.rollback()
        unit.drain_audit_events()  # discarded with the child; its hooks die with the object
    return Capture(
        batch_id=UUID(str(batch["id"])),
        capture_operation_id=UUID(str(operation)),
        cutover_date=staging.cutover_date,
        versions=tuple(versions),
        obligations=tuple(obligations),
    )


# --- the platform applier -------------------------------------------------------------------------


def _places(value: Decimal) -> int:
    exponent = value.normalize().as_tuple().exponent
    return max(0, -int(exponent)) if isinstance(exponent, int) else 0


def booking_body(
    contract: ContractOpening, *, batch: Mapping[str, Any], currency: str, customer_id: UUID
) -> ContractBookedV1:
    """``CONTRACT_BOOKED`` of a staged contract (S07-R-02) as the platform's payload: the staged
    lines without ``pob_template_code`` (the template is the product's default, checked by the
    applier), prices as money in the reporting currency, ``document_ref = migration:<no>``."""
    staged = booking_payload(contract)
    lines = []
    for line in staged["lines"]:
        item = dict(line)
        item.pop("pob_template_code", None)
        item["total_price"] = {"amount": str(item["total_price"]), "currency": currency}
        if not item.get("account_overrides"):
            item["account_overrides"] = None
        lines.append(item)
    return ContractBookedV1.model_validate(
        {
            "external_id": staged["external_id"],
            "customer_id": str(customer_id),
            "contracting_entity_code": staged["contracting_entity_code"],
            "transaction_currency": currency,
            "inception_date": staged["inception_date"],
            "document_ref": DOCUMENT_REF.format(migration_no=batch["migration_no"]),
            "lines": lines,
        }
    )


def opening_payload_model() -> tuple[int, type[Any]]:
    """The registered LATEST ``OPENING_BALANCE_ESTABLISHED`` payload version and model (the append
    path validates against it): version 1 carries ``MoneyIn`` money members (four decimal places),
    version 2 — D-98 127, 04 rev 1.61 (ENG-C6 / B4) — ``ExactMoneyIn`` (plain decimal text, 20 / 18
    digits). The applier is a consumer of that registry, never a hard-coded version."""
    version = int(LATEST_SCHEMA_VERSION[ContractEventType.OPENING_BALANCE_ESTABLISHED])
    return version, PAYLOADS[(ContractEventType.OPENING_BALANCE_ESTABLISHED, version)]


def exact_text(value: object, *, what: str) -> str:
    """The plain decimal text of a stored legacy value: exponent forms (``repr(float)``) go
    through ``money.exact_plain_decimal`` when the payload owner's helper is present (04 rev 1.61)
    and are refused by name otherwise; plain text is returned as ``format(Decimal, "f")``."""
    text = str(value)
    if "e" in text.lower():
        helper = getattr(money, "exact_plain_decimal", None)
        if helper is None:
            raise _refuse(
                f"{what} = {text} is exponent text; the exact plain form needs "
                "money.exact_plain_decimal (04 rev 1.61) — the import does not guess."
            )
        try:
            return str(helper(text))
        except ValueError as error:
            raise _refuse(f"{what} = {text}: {error}") from error
    return format(Decimal(text), "f")


def opening_body(contract: ContractOpening, *, batch: Mapping[str, Any], currency: str) -> Any:
    """``OPENING_BALANCE_ESTABLISHED`` of a staged contract (S07-R-11) as the registered LATEST
    payload version: the staged rows' members the payload defines, quantities as decimal strings,
    money as ``{amount, currency}`` in the reporting currency, ``migration_batch_id`` = the batch
    (the provenance the capture reads back); ``fair_value_contract_liability`` omitted (Q-C6-127-1).
    While the latest version is 1 (``MoneyIn``, four places) a money value beyond four decimal
    places is refused by name — never rounded (D-98 127 interim); at version 2 the exact text is
    handed to ``ExactMoneyIn`` and the model refuses an out-of-bound amount by name (API-C-06)."""
    version, model = opening_payload_model()
    staged = opening_payload(contract, date.fromisoformat(str(batch["cutover_date"])))
    rows = []
    for row in staged["rows"]:
        item: dict[str, Any] = {"obligation_key": row["obligation_key"]}
        for member in OPENING_QUANTITY_MEMBERS:
            item[member] = exact_text(
                row[member], what=f"{contract.external_id} {row['obligation_key']} {member}"
            )
        for member in OPENING_MONEY_MEMBERS:
            text = exact_text(
                row[member], what=f"{contract.external_id} {row['obligation_key']} {member}"
            )
            amount = Decimal(text)
            if version == 1 and _places(amount) > MONEY_PLACES:
                raise _refuse(
                    PRECISION_COPY.format(
                        contract=contract.external_id,
                        key=row["obligation_key"],
                        member=member,
                        value=text,
                        places=_places(amount),
                    )
                )
            item[member] = {"amount": text, "currency": currency}
        rows.append(item)
    try:
        return model.model_validate(
            {
                "reason": staged["reason"],
                "cutover_date": staged["cutover_date"],
                "migration_batch_id": str(batch["id"]),
                "obligations": rows,
            }
        )
    except ValueError as error:  # pydantic ValidationError: the registered model refused
        raise _refuse(
            f"{contract.external_id}: the OPENING_BALANCE_ESTABLISHED payload (version {version}) "
            f"refused the staged values: {error}"
        ) from error


def opening_effective_date(contract: ContractOpening, cutover_date: date) -> date:
    """S07-R-01: ``OPENING_BALANCE_ESTABLISHED`` is effective on the cutover date. A contract whose
    legacy inception (S07-R-02) is after the cutover holds no history at it; its inception is never
    moved, so its one opening event — the batch's ``cutover_date`` and the rows as stored, nil in
    every cumulative member — is effective on that inception, the later of the two dates."""
    return max(cutover_date, contract.inception_date)


def vc_elements(
    uow: UnitOfWork, contract: ContractOpening, *, contract_id: UUID, currency: str
) -> int:
    """S07-R-11 / POL-213: the contract-level VC element of every staged ``VC`` row, written as the
    legacy template import writes it (S01-R-06: ``VC-<obligation key>``, ``ENTERED_AMOUNT``,
    version 1 constrained amount = the row's stated price as a magnitude, a negative price a
    ``DECREASE`` element, effective on the inception date, ``allocation_target = CONTRACT``) with
    origin ``MIGRATION``, after the booking and before the activation. Without it the engine's
    transaction price lacks the row's amount and S07-R-03 refuses the opening balance (WLD-F-15
    Contract 2: Σ X_i 900 against 1,000.00). The rows live inside the dry run's savepoint; no
    approval request exists yet (the promotion approves what it appends, BS3-D-26). Returns the
    number of ``ESTIMATE_CHANGED`` events appended to the contract's stream."""
    for row in contract.vc_elements:
        price = row.mapped.stated_price
        write_vc_element(
            uow,
            VcElement(
                contract_id=contract_id,
                contract_external_id=contract.external_id,
                element_code=VC_ELEMENT.format(obligation_key=row.mapped.obligation_key),
                obligation_key=row.mapped.obligation_key,
                direction="DECREASE" if price < 0 else "INCREASE",
                constrained_amount=abs(price),
                currency=currency,
                effective_date=contract.inception_date,
            ),
            origin="MIGRATION",
        )
    return len(contract.vc_elements)


class PlatformApplier:
    """The platform path: prerequisites checked by name, the customer of the legacy convention,
    ``book_contract`` (origin MIGRATION), the VC element of every staged ``VC`` row
    (``vc_elements``), ``CONTRACT_ACTIVATED`` with the truthfully evaluated checklist (the dry run
    is not gated — promotion is, BS3-D-26), ``OPENING_BALANCE_ESTABLISHED`` naming the batch, then
    one synchronous ``compute_group``."""

    def apply(
        self, uow: UnitOfWork, *, batch: Mapping[str, Any], contract: ContractOpening
    ) -> Applied:
        session = uow.session
        currency = str(
            session.execute(
                select(tenant.c.reporting_currency).where(tenant.c.id == uow.principal.tenant_id)
            ).scalar_one()
        ).strip()
        self._check_prerequisites(session, contract, currency)
        customer_id = self._customer(uow, contract.external_id)
        body = booking_body(contract, batch=batch, currency=currency, customer_id=customer_id)
        booked = book_contract(uow, body=body, origin="MIGRATION")
        contract_id = UUID(str(booked.contract["id"]))
        group_id = UUID(str(booked.combination_group["id"]))
        # S07-R-11 / POL-213: a staged VC row is a VC line of the booking AND its contract-level VC
        # element (S01-R-06), so the transaction price carries the row's amount before the
        # opening balance is checked against it (S07-R-03)
        head = int(booked.event["stream_version"]) + vc_elements(
            uow, contract, contract_id=contract_id, currency=currency
        )
        checklist = activation.evaluate(session, booked.contract, now=uow.now)
        established = opening_body(contract, batch=batch, currency=currency)
        append_events(
            uow,
            contract_id=contract_id,
            expected_stream_version=head,
            events=[
                EventIn(
                    event_type=ContractEventType.CONTRACT_ACTIVATED,
                    effective_date=contract.inception_date,
                    payload=ContractActivatedV1(checklist=checklist.payload()),
                ),
                EventIn(
                    event_type=ContractEventType.OPENING_BALANCE_ESTABLISHED,
                    effective_date=opening_effective_date(contract, established.cutover_date),
                    payload=established,
                    obligation_keys=tuple(item.obligation_key for item in established.obligations),
                ),
            ],
            origin="MIGRATION",
        )
        opening_version = head + 2
        # the platform's own computation, held here so the ACTUAL producing bundle is read (Codex
        # 0422 (a), (b), (d)): bundle → engine → persist — the ``computation.recompute`` triple
        # (DG-CMD-04, one engine call), synchronous by construction, never deferred
        try:
            bundle = bundles.build(session, group_id, uow.now, (), ComputationTrigger.COMMAND)
            output = computation.default_engine()(bundle)
            stored = computation.persist(uow, bundle, output)
        except EngineError as error:
            raise computation_refusal(contract.external_id, error) from error
        if POPULATION_BOOK not in dict(stored.get("contract_version_ids") or {}):
            raise _refuse(
                COMPUTATION_COPY.format(
                    contract=contract.external_id, status=f"without a {POPULATION_BOOK} version"
                )
            )
        opening_key = f"{contract.external_id}/EV-{opening_version:06d}"
        opening_events = [
            event
            for event in bundle.events
            if event.event_key == opening_key
            and event.event_type == ContractEventType.OPENING_BALANCE_ESTABLISHED.value
            and str(event.payload.get("migration_batch_id")) == str(batch["id"])
        ]
        if len(opening_events) != 1:
            raise _refuse(
                COMPUTATION_COPY.format(
                    contract=contract.external_id,
                    status="without the OPENING_BALANCE_ESTABLISHED input naming this migration",
                )
            )
        return Applied(
            contract_id=contract_id,
            combination_group_id=group_id,
            bundle_known_at=bundle.known_at,
            bundle_member_keys=frozenset(str(key) for key in bundle.group.member_contract_keys),
            opening_event_key=opening_key,
            opening_payload_sha256=str(opening_events[0].payload_sha256),
            input_sha256=bundle.sha256(),
            input_evidence=encode_input(bundle),
        )

    @staticmethod
    def _check_prerequisites(session: Any, contract: ContractOpening, currency: str) -> None:
        what: list[str] = []
        codes = sorted({contract.entity_code} | {row.mapped.entity_code for row in contract.rows})
        found = {
            str(code)
            for code in session.execute(
                select(_legal_entity().c.code).where(_legal_entity().c.code.in_(codes))
            ).scalars()
        }
        for code in codes:
            if code not in found:
                what.append(f"entity {code!r}")
        skus = sorted({row.mapped.product_code for row in contract.rows})
        products = {
            str(row["code"]): row
            for row in session.execute(
                select(product.c.code, product.c.default_pob_template_id).where(
                    product.c.code.in_(skus)
                )
            ).mappings()
        }
        template_ids = {
            row["default_pob_template_id"]
            for row in products.values()
            if row["default_pob_template_id"] is not None
        }
        templates = {
            UUID(str(row[0])): str(row[1])
            for row in session.execute(
                select(pob_template.c.id, pob_template.c.code).where(
                    pob_template.c.id.in_(list(template_ids))
                )
            ).all()
        }
        for row in contract.rows:
            sku = row.mapped.product_code
            if sku not in products:
                what.append(f"product {sku!r}")
                continue
            template_id = products[sku]["default_pob_template_id"]
            template_code: str | None = (
                None if template_id is None else templates.get(UUID(str(template_id)))
            )
            if template_code != row.mapped.template_code:
                what.append(
                    f"product {sku!r} default template {template_code!r} is not the row's "
                    f"{row.mapped.template_code!r}"
                )
        # 04 rev 1.72 (D-98 133 AMENDMENTS 3 and 4): every staged line's (label, SKU,
        # stratification)
        # must be an entry of an APPROVED LEGACY-SKU-SSP version — the legacy replay the
        # prerequisite
        # writer made or an equal version already in the tenant; otherwise S05 would refuse the
        # whole
        # dry run with SSP_KEY_NOT_FOUND after the booking, so the gap is named here first
        approved = approved_midpoints(session)
        for row in contract.rows:
            key = (
                str(row.mapped.ssp_version_label or ""),
                row.mapped.product_code,
                row.mapped.stratification or "",
            )
            if key not in approved:
                what.append(
                    f"SSP version {key[0]!r} for {key[1]!r} / {key[2] or '-'!r} has no approved "
                    f"LEGACY-SKU-SSP entry"
                )
        enabled = session.execute(
            select(tenant_currency.c.currency_code).where(
                tenant_currency.c.currency_code == currency, tenant_currency.c.is_enabled.is_(True)
            )
        ).first()
        if enabled is None:
            what.append(f"reporting currency {currency!r} not enabled")
        if what:
            raise _refuse(
                PREREQUISITE_COPY.format(
                    contract=contract.external_id, what="; ".join(dict.fromkeys(what))
                )
            )

    @staticmethod
    def _customer(uow: UnitOfWork, external_id: str) -> UUID:
        code = f"{CUSTOMER_PREFIX}{external_id}"
        found = uow.session.execute(
            select(_customer_table().c.id).where(_customer_table().c.code == code)
        ).first()
        if found is not None:
            return UUID(str(found[0]))
        created = create_customer(
            uow,
            body=CustomerIn(code=code, name=code),
            source_system=SourceSystem.LEGACY_TEMPLATE_V1,
        )
        return created.id


def _legal_entity() -> Any:
    from erev_api.db.tables import legal_entity

    return legal_entity


def _customer_table() -> Any:
    from erev_api.db.tables import customer

    return customer


platform_applier: Final = PlatformApplier()


def population_of(capture: Capture, batch: Mapping[str, Any]) -> ComparisonPopulation:
    """Convenience for callers that hold a capture and its batch row."""
    return capture.population(batch)


def as_rows(items: Iterable[Mapping[str, Any]]) -> Sequence[Mapping[str, Any]]:
    return tuple(items)
