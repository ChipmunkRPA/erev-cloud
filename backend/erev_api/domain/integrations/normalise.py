"""Stage 01 platform part: source identity, version order, idempotency keys and the raw source
store (ENGINE_SPEC §1.3 S01-R-01 to S01-R-04; 05 ADP-02 to ADP-04; 04 T-SRC-01, §16.14; 03
REQ-DAT-011; PHASES BS-D-16; BUILD_SPEC DIN-2).

``store_source_record`` writes one ``source_record`` in the caller's unit of work:

1. A transaction-scoped advisory lock on (tenant, ``source_system``, ``object_type``,
   ``external_id``) serialises the versions of one source object.
2. An identity already stored (``ux_source_record__identity``) is logged and skipped; the stored
   row answers (S01-R-01, REQ-DAT-011). A concurrent insert of the same identity takes the same
   path through ``ON CONFLICT DO NOTHING``.
3. The payload is tokenised (ADP-04) and ``payload_sha256`` is the SHA-256 of the canonical
   tokenised payload (dev-guide §5.17).
4. A version whose ``version_order`` is lower than the highest stored one is stored and skipped
   with the exception item ``STALE_SOURCE_VERSION`` (WARNING, source INTEGRATION; S01-R-02,
   ADP-02, PRD IMP-44).

The key builders are pure: adapter events ``'src:' ‖ hex(SHA-256(...))``, import events
``'imp:' ‖ hex(SHA-256(...))`` and API events ``Idempotency-Key ‖ ':' ‖ ordinal`` (S01-R-03). A
replay with the same key creates no event (``ux_contract_event__idempotency``, CTL-001).
S01-R-04 needs no code here: the database assigns ``recorded_at`` and ``record_seq`` at append
(DB-08).

[J] L5-1-Q-3: every stored record counts as processed, so "the highest processed version" is the
highest stored ``version_order`` of the object.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine.canonical import sha256_hex
from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from erev_api.audit import writer as audit_writer
from erev_api.auth import entity_scope
from erev_api.auth.principal import Principal, RequestContext
from erev_api.db import new_id
from erev_api.db.session import tenant_session
from erev_api.db.tables import api_client, contract, contract_source_link, import_row, source_record
from erev_api.domain.imports.exceptions import dedupe_key, raise_exception_item, severity_of
from erev_api.domain.integrations.tokenise import token_key, tokenise
from erev_api.enums import ExceptionSource, PrincipalKind, SourceObjectType, SourceSystem
from erev_api.logging import get_logger, register_logger_fields
from erev_api.problems import Problem
from erev_api.redaction import redact_contacts
from erev_api.schemas.source_records import (
    ContractSourceOut,
    SourceRecordApiClientOut,
    SourceRecordOut,
)

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

__all__ = [
    "FILE_ROW_VERSION",
    "STALE_CODE",
    "SourceIdentity",
    "StoreOutcome",
    "StoredRecord",
    "adapter_event_key",
    "api_event_key",
    "contract_sources",
    "file_row_external_id",
    "file_row_identity",
    "get_source_record",
    "import_event_key",
    "read",
    "store_source_record",
]

_LOGGER: Final = "erev_api.domain.integrations.normalise"
register_logger_fields(
    _LOGGER, ("source_record_id", "source_system", "object_type", "external_version")
)

FILE_ROW_VERSION: Final = "1"
STALE_CODE: Final = "STALE_SOURCE_VERSION"
STORE_ACTION: Final = "source_record.store"
OBJECT_TYPE: Final = "source_record"
ADAPTER_PREFIX: Final = "src:"
IMPORT_PREFIX: Final = "imp:"


class StoreOutcome(StrEnum):
    """What ``store_source_record`` did with one record."""

    STORED = "STORED"
    DUPLICATE = "DUPLICATE"
    STALE = "STALE"


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """T-SRC-01 identity: (``source_system``, ``object_type``, ``external_id``,
    ``external_version``)."""

    source_system: SourceSystem
    object_type: SourceObjectType
    external_id: str
    external_version: str

    def __post_init__(self) -> None:
        if not self.external_id or not self.external_version:
            raise ValueError("a source identity needs an external id and version")


@dataclass(frozen=True, slots=True)
class StoredRecord:
    """The stored row that answers a record: inserted now, or the one already stored."""

    id: UUID
    outcome: StoreOutcome
    payload_sha256: str
    exception_item_id: UUID | None = None

    @property
    def applies(self) -> bool:
        """True when the caller should act on the record (not a duplicate, not stale)."""
        return self.outcome is StoreOutcome.STORED


def file_row_external_id(import_upload_id: UUID, sheet_name: str, row_number: int) -> str:
    """S01-R-01: ``<import_upload id>:<sheet name>:<row number>``."""
    if row_number < 1:
        raise ValueError("row numbers start at 1")
    return f"{import_upload_id}:{sheet_name}:{row_number}"


def file_row_identity(
    *,
    source_system: SourceSystem,
    object_type: SourceObjectType,
    import_upload_id: UUID,
    sheet_name: str,
    row_number: int,
) -> SourceIdentity:
    """The identity of one file row; its version is ``'1'`` (S01-R-01)."""
    return SourceIdentity(
        source_system=source_system,
        object_type=object_type,
        external_id=file_row_external_id(import_upload_id, sheet_name, row_number),
        external_version=FILE_ROW_VERSION,
    )


def _ordinal(ordinal: int) -> int:
    if ordinal < 1:
        raise ValueError("event ordinals start at 1")
    return ordinal


def _hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def adapter_event_key(identity: SourceIdentity, ordinal: int) -> str:
    """S01-R-03, ADP-03: ``'src:' ‖ hex(SHA-256(source_system ‖ ':' ‖ object_type ‖ ':' ‖
    external_id ‖ ':' ‖ external_version ‖ ':' ‖ ordinal))``."""
    parts = (
        identity.source_system.value,
        identity.object_type.value,
        identity.external_id,
        identity.external_version,
        str(_ordinal(ordinal)),
    )
    return ADAPTER_PREFIX + _hex(":".join(parts))


def import_event_key(
    *,
    file_sha256: str,
    template_code: str,
    template_version: int,
    business_key: str,
    ordinal: int,
) -> str:
    """S01-R-03: ``'imp:' ‖ hex(SHA-256(file_sha256 ‖ ':' ‖ template_code ‖ ':' ‖
    template_version ‖ ':' ‖ business_key ‖ ':' ‖ ordinal))``."""
    parts = (
        file_sha256.strip(),
        template_code,
        str(template_version),
        business_key,
        str(_ordinal(ordinal)),
    )
    return IMPORT_PREFIX + _hex(":".join(parts))


def api_event_key(idempotency_key: str, ordinal: int) -> str:
    """S01-R-03: the request ``Idempotency-Key`` ‖ ``':'`` ‖ ordinal."""
    if not idempotency_key:
        raise ValueError("an API event key needs the request Idempotency-Key")
    return f"{idempotency_key}:{_ordinal(ordinal)}"


def _lock(uow: UnitOfWork, identity: SourceIdentity) -> None:
    subject = ":".join(
        (
            "source_record",
            str(uow.principal.tenant_id),
            identity.source_system.value,
            identity.object_type.value,
            identity.external_id,
        )
    )
    uow.session.execute(select(func.pg_advisory_xact_lock(func.hashtextextended(subject, 0))))


def _object_filter(identity: SourceIdentity) -> tuple[Any, ...]:
    return (
        source_record.c.source_system == identity.source_system.value,
        source_record.c.object_type == identity.object_type.value,
        source_record.c.external_id == identity.external_id,
    )


def _stored(uow: UnitOfWork, identity: SourceIdentity) -> Mapping[str, Any] | None:
    row = (
        uow.session.execute(
            select(source_record.c.id, source_record.c.payload_sha256).where(
                *_object_filter(identity),
                source_record.c.external_version == identity.external_version,
            )
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)


def _highest(uow: UnitOfWork, identity: SourceIdentity) -> Mapping[str, Any] | None:
    row = (
        uow.session.execute(
            select(source_record.c.version_order, source_record.c.external_version)
            .where(*_object_filter(identity))
            .order_by(source_record.c.version_order.desc(), source_record.c.id.desc())
            .limit(1)
        )
        .mappings()
        .one_or_none()
    )
    return None if row is None else dict(row)


def _duplicate(identity: SourceIdentity, row: Mapping[str, Any]) -> StoredRecord:
    get_logger(_LOGGER).info(
        "source_record.duplicate_skipped",
        source_record_id=str(row["id"]),
        source_system=identity.source_system.value,
        object_type=identity.object_type.value,
        external_version=identity.external_version,
    )
    return StoredRecord(
        id=UUID(str(row["id"])),
        outcome=StoreOutcome.DUPLICATE,
        payload_sha256=str(row["payload_sha256"]).strip(),
    )


def stale_message(identity: SourceIdentity, processed_version: str) -> str:
    """PRD IMP-44."""
    return (
        f"{identity.source_system.value} {identity.object_type.value} {identity.external_id} "
        f"version {identity.external_version} is older than the processed version "
        f"{processed_version}. It was recorded and not applied."
    )


def store_source_record(
    uow: UnitOfWork,
    *,
    identity: SourceIdentity,
    version_order: int,
    payload: Mapping[str, Any],
    import_upload_id: UUID | None = None,
    import_row_id: UUID | None = None,
    sync_run_id: UUID | None = None,
    request_id: str | None = None,
    idempotency_key: str | None = None,
) -> StoredRecord:
    """Store one inbound object once per identity, tokenised, in version order (S01-R-01, 02)."""
    _lock(uow, identity)
    existing = _stored(uow, identity)
    if existing is not None:
        return _duplicate(identity, existing)
    highest = _highest(uow, identity)
    stored_payload = tokenise(token_key(uow), dict(payload))
    digest = sha256_hex(stored_payload)
    principal = uow.principal
    record_id = new_id()
    statement = (
        insert(source_record)
        .values(
            tenant_id=principal.tenant_id,
            id=record_id,
            source_system=identity.source_system.value,
            object_type=identity.object_type.value,
            external_id=identity.external_id,
            external_version=identity.external_version,
            version_order=version_order,
            payload=stored_payload,
            payload_sha256=digest,
            received_at=uow.now,
            import_upload_id=import_upload_id,
            import_row_id=import_row_id,
            sync_run_id=sync_run_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            created_at=uow.now,
            created_by=principal.id,
            created_by_kind=principal.kind.value,
        )
        .on_conflict_do_nothing(
            index_elements=[
                source_record.c.tenant_id,
                source_record.c.source_system,
                source_record.c.object_type,
                source_record.c.external_id,
                source_record.c.external_version,
            ]
        )
        .returning(source_record.c.id)
    )
    inserted = uow.session.execute(statement).scalar_one_or_none()
    if inserted is None:
        concurrent = _stored(uow, identity)
        if concurrent is None:  # pragma: no cover - the conflicting row is visible after the lock
            raise RuntimeError("source record conflict without a stored row")
        return _duplicate(identity, concurrent)
    audit_writer.record_facts(
        uow,
        action=STORE_ACTION,
        object_type=OBJECT_TYPE,
        ids=[record_id],
        detail={
            "source_system": identity.source_system.value,
            "object_type": identity.object_type.value,
            "external_version": identity.external_version,
        },
    )
    if highest is None or version_order >= int(highest["version_order"]):
        return StoredRecord(id=record_id, outcome=StoreOutcome.STORED, payload_sha256=digest)
    item = raise_exception_item(
        uow,
        source=ExceptionSource.INTEGRATION,
        code=STALE_CODE,
        severity=severity_of("WARNING"),
        message=stale_message(identity, str(highest["external_version"])),
        dedupe=dedupe_key(ExceptionSource.INTEGRATION, STALE_CODE, record_id),
        business_key=identity.external_id,
        source_record_id=record_id,
        import_upload_id=import_upload_id,
        import_row_id=import_row_id,
    )
    get_logger(_LOGGER).info(
        "source_record.stale_skipped",
        source_record_id=str(record_id),
        source_system=identity.source_system.value,
        object_type=identity.object_type.value,
        external_version=identity.external_version,
    )
    return StoredRecord(
        id=record_id, outcome=StoreOutcome.STALE, payload_sha256=digest, exception_item_id=item.id
    )


def read[T](ctx: RequestContext, fn: Callable[[Session], T]) -> T:
    """Run ``fn`` in a read-only tenant session of the caller (DG-CMD-13)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return fn(session)


READ_PERMISSION: Final = "contract.read"  # 04 API-R-56


def _named_by_a_contract_in_reach(session: Session, principal: Principal, record_id: UUID) -> bool:
    """Whether a T-CON-02 link ties the record to a contract the caller reads: the contract row is
    RLS-TE, and ``contract.read`` is held for its contracting entity."""
    statement = (
        select(contract.c.contracting_entity_id)
        .select_from(
            contract_source_link.join(
                contract,
                and_(
                    contract.c.tenant_id == contract_source_link.c.tenant_id,
                    contract.c.id == contract_source_link.c.contract_id,
                ),
            )
        )
        .where(contract_source_link.c.source_record_id == record_id)
    )
    return any(
        entity_scope.holds_for(principal, (READ_PERMISSION,), UUID(str(entity_id)))
        for (entity_id,) in session.execute(statement)
    )


def get_source_record(session: Session, principal: Principal, record_id: UUID) -> SourceRecordOut:
    """API-S-SourceRecord; 404 ``not-found`` when absent or not visible (04 §16.14).

    A source record carries no entity and its payload may be any entity's, so it is read with
    ``contract.read`` for all entities, or through a contract the caller reads that names it
    (T-CON-02; supervisor ruling R-28, item SCOPE-WORKSPACE-LISTS-1). To anyone else it is
    absent: a by-id read answers 404 for a row out of reach (03 REQ-PLT-012)."""
    row = (
        session.execute(select(source_record).where(source_record.c.id == record_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    if not entity_scope.holds_all(principal, READ_PERMISSION) and not (
        _named_by_a_contract_in_reach(session, principal, record_id)
    ):
        raise Problem("not-found")
    client: SourceRecordApiClientOut | None = None
    if str(getattr(row["created_by_kind"], "value", row["created_by_kind"])) == (
        PrincipalKind.API_CLIENT.value
    ):
        found = session.execute(
            select(api_client.c.id, api_client.c.name).where(api_client.c.id == row["created_by"])
        ).one_or_none()
        if found is not None:
            client = SourceRecordApiClientOut(id=found.id, name=str(found.name))
    return SourceRecordOut(
        id=row["id"],
        source_system=row["source_system"],
        object_type=row["object_type"],
        external_id=str(row["external_id"]),
        external_version=str(row["external_version"]),
        received_at=row["received_at"],
        api_client=client,
        idempotency_key=row["idempotency_key"],
        request_id=row["request_id"],
        payload_sha256=str(row["payload_sha256"]).strip(),
        payload=redact_contacts(dict(row["payload"])),
        import_upload_id=row["import_upload_id"],
        import_row_id=row["import_row_id"],
        sync_run_id=row["sync_run_id"],
    )


def contract_sources(session: Session, contract_id: UUID) -> list[ContractSourceOut]:
    """``GET /contracts/{id}/sources``: the contract's T-CON-02 links with the identity of each
    source record and the sheet and row number of its import row, in sheet and row order (04
    API-R-28; BUILD_SPEC DIN-4). 404 ``not-found`` when the contract is not visible."""
    visible = session.execute(select(contract.c.id).where(contract.c.id == contract_id)).first()
    if visible is None:
        raise Problem("not-found")
    statement = (
        select(
            contract_source_link.c.id,
            contract_source_link.c.link_role,
            contract_source_link.c.contract_event_id,
            contract_source_link.c.created_at,
            source_record.c.id.label("source_record_id"),
            source_record.c.source_system,
            source_record.c.object_type,
            source_record.c.external_id,
            source_record.c.external_version,
            source_record.c.received_at,
            source_record.c.import_upload_id,
            source_record.c.import_row_id,
            import_row.c.sheet_name,
            import_row.c.row_number,
        )
        .select_from(
            contract_source_link.join(
                source_record,
                (source_record.c.tenant_id == contract_source_link.c.tenant_id)
                & (source_record.c.id == contract_source_link.c.source_record_id),
            ).outerjoin(
                import_row,
                (import_row.c.tenant_id == source_record.c.tenant_id)
                & (import_row.c.id == source_record.c.import_row_id),
            )
        )
        .where(contract_source_link.c.contract_id == contract_id)
        .order_by(
            source_record.c.received_at,
            import_row.c.sheet_name,
            import_row.c.row_number,
            contract_source_link.c.link_role,
            contract_source_link.c.id,
        )
    )
    return [
        ContractSourceOut(
            id=row["id"],
            link_role=str(row["link_role"]),
            contract_event_id=row["contract_event_id"],
            source_record_id=row["source_record_id"],
            source_system=row["source_system"],
            object_type=row["object_type"],
            external_id=str(row["external_id"]),
            external_version=str(row["external_version"]),
            received_at=row["received_at"],
            import_upload_id=row["import_upload_id"],
            import_row_id=row["import_row_id"],
            sheet_name=None if row["sheet_name"] is None else str(row["sheet_name"]),
            row_number=None if row["row_number"] is None else int(row["row_number"]),
            created_at=row["created_at"],
        )
        for row in session.execute(statement).mappings()
    ]
