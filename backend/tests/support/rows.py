"""Raw row builders for the pg suite (dev-guide DG-TST-16, DG-TST-20; BUILD_SPEC PLF-1, PLF-3,
PLF-4).

``ROW_BUILDERS`` maps every tenant table to a builder that returns the column values of one valid
row of a given tenant; the isolation suite inserts those rows as ``erev_app`` under tenant context.
Builders receive the open session, because a chained row continues the tenant's chain head and a
row with tenant foreign keys references rows provisioning wrote (the admin membership, the
``viewer`` role). Where the session's context hides those rows, a fresh id stands in: such an
insert must fail on row-level security before any foreign key is checked.
``PROVISIONED_TABLES`` holds one row per tenant written by provisioning; for them the builder names
that row's key and the suite checks it instead of inserting a second one (SPEC-Q-134).
Raw inserts are allowed only in this module (DG-TST-16). Other tests create data through commands
(``support.factories``), or through ``insert_role_assignment`` until assignment commands exist.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from erev_api.audit.chain import append_events
from erev_api.audit.writer import AuditActor, build_event
from erev_api.auth.keyring import KeyRing, adapter_secret_namespace
from erev_api.auth.permissions import role_content_sha256
from erev_api.db import new_id
from erev_api.db.session import (
    DbContext,
    name_platform_tenant,
    platform_session,
    set_tenant_context,
)
from erev_api.db.tables import (
    access_review_campaign,
    account_mapping_version,
    api_client,
    app_user,
    approval_delegation,
    approval_request,
    approval_step,
    audit_chain_head,
    book,
    calc_trace,
    close_checklist_template,
    combination_group,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    customer,
    dimension_definition,
    engine_release,
    estimate,
    file_object,
    fiscal_calendar,
    gl_account,
    import_row,
    import_upload,
    integration_connection,
    journal_batch,
    journal_entry,
    journal_line,
    journal_run,
    legal_entity,
    metadata,
    migration_batch,
    migration_population_version,
    obligation,
    period,
    period_lock,
    period_state,
    period_state_transition,
    pob_template,
    pob_template_version,
    policy_override,
    product,
    reconciliation,
    registry_version,
    report_run,
    role,
    role_assignment,
    role_permission,
    rule,
    rule_set,
    rule_set_version,
    schedule,
    sod_exception,
    sod_rule,
    source_invoice,
    source_order,
    source_record,
    ssp_book,
    ssp_book_version,
    ssp_calculator_run,
    ssp_entry,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
    support_grant,
    tenant,
    tenant_membership,
    user_mfa_factor,
    webhook_endpoint,
)
from erev_api.db.tables import fx_rate_set as fx_rate_set_table
from erev_api.db.tables import fx_rate_set_version as fx_rate_set_version_table
from erev_api.db.tables import ledger_chain_head as ledger_chain_head_table
from erev_api.domain.journals.subledger import control_totals, dimension_set_sha256, seal_sha256
from erev_api.enums import (
    AccessReviewDecision,
    AccountRole,
    AccountType,
    ApprovalDecisionKind,
    ApprovalRequestStatus,
    ApprovalStepStatus,
    ApprovalSubjectType,
    AuditOutcome,
    BookCode,
    CalendarPattern,
    ChecklistGateKind,
    ChecklistStatus,
    ClearingPurpose,
    CloseRunStatus,
    ConfigStatus,
    ControlResult,
    DisclosureKind,
    EvidencePackKind,
    FilePurpose,
    GlAdapter,
    GrantStatus,
    JeType,
    JobKind,
    JournalRunGrain,
    JournalRunMode,
    JournalState,
    ManualAdjustmentKind,
    ManualAdjustmentStatus,
    MembershipStatus,
    MigrationMode,
    MigrationStatus,
    NotificationKind,
    OutboxTopic,
    PostingAckKind,
    PrincipalKind,
    RateType,
    ReconciliationKind,
    ReconciliationStatus,
    RegistryCategory,
    RegistryScope,
    RuleSetKind,
    RunStatus,
    SnapshotKind,
    SourceSystem,
    TenantKind,
    TenantStatus,
)
from erev_engine import ENGINE_VERSION
from erev_engine.canonical import sha256_hex
from erev_engine.rules import validate_conditions
from sqlalchemy import (
    ColumnElement,
    Connection,
    Engine,
    Select,
    Table,
    exc,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.orm import Session

INVITED_AT: Final = datetime(2026, 9, 12, 12, tzinfo=UTC)
# Assignments start before the frozen test clock, never at the wall-clock default now().
ASSIGNED_FROM: Final = datetime(2026, 1, 1, tzinfo=UTC)
_SYSTEM: Final = MappingProxyType(
    {"created_by_kind": PrincipalKind.SYSTEM.value, "updated_by_kind": PrincipalKind.SYSTEM.value}
)
_CREATED: Final = MappingProxyType({"created_by_kind": PrincipalKind.SYSTEM.value})


@dataclass(frozen=True, slots=True)
class RowContext:
    tenant_id: UUID
    user_id: UUID  # an app_user row that builders may reference


RowBuilder = Callable[[RowContext, Session], dict[str, Any]]


def membership_row(
    ctx: RowContext, *, status: MembershipStatus = MembershipStatus.INVITED
) -> dict[str, Any]:
    """T-PLT-07: an ``INVITED`` row carries a token hash and expiry; other states carry neither."""
    invited = status is MembershipStatus.INVITED
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "user_id": ctx.user_id,
        "status": status.value,
        "invited_at": INVITED_AT,
        "invitation_token_sha256": secrets.token_hex(32) if invited else None,
        "invitation_expires_at": INVITED_AT + timedelta(days=7) if invited else None,
        "activated_at": None if invited else INVITED_AT,
        **_SYSTEM,
    }


def audit_event_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-19: continues the chain head visible to ``session``; the HMAC is not recomputed, so
    the tenant's chain verification fails after this insert (DB-09 checks position only)."""
    head = session.execute(
        select(audit_chain_head.c.last_chain_seq, audit_chain_head.c.last_hmac).where(
            audit_chain_head.c.tenant_id == ctx.tenant_id
        )
    ).one_or_none()
    seq, prev_hmac = (0, None) if head is None else (int(head.last_chain_seq), head.last_hmac)
    return {
        "tenant_id": ctx.tenant_id,
        "occurred_at": INVITED_AT,
        "id": new_id(),
        "chain_seq": seq + 1,
        "actor_kind": PrincipalKind.SYSTEM.value,
        "request_id": "tests-row-builder",
        "action": "audit_event.probe",
        "object_type": "audit_event",
        "outcome": AuditOutcome.SUCCESS.value,
        "detail": {},
        "prev_hmac": prev_hmac,
        "hmac": secrets.token_hex(32),
        "hmac_key_id": f"audit-hmac:{ctx.tenant_id}:1",
    }


def audit_chain_head_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    """T-PLT-22: provisioning writes the head, so this row serves only refused inserts."""
    return {"tenant_id": ctx.tenant_id, "last_chain_seq": 0, "last_hmac": None}


def audit_event_contract_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    """T-PLT-48: the link of one event to one contract. The table carries no key to either (04
    T-PLT-48), so the probe names an event and a contract of its own."""
    return {
        "tenant_id": ctx.tenant_id,
        "contract_id": new_id(),
        "chain_seq": 1,
        "occurred_at": INVITED_AT,
        "audit_event_id": new_id(),
    }


def control_execution_values(
    tenant_id: UUID, *, engine_release_id: UUID, entity_id: UUID | None = None, **extra: Any
) -> dict[str, Any]:
    """T-PLT-39: a PASS of CTL-039 over one chain verification of the running release."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "control_id": "CTL-039",
        "run_ref_type": "AUDIT_CHAIN_VERIFICATION",
        "run_ref_id": new_id(),
        "entity_id": entity_id,
        "book_code": None,
        "period_id": None,
        "population_count": 1,
        "exception_count": 0,
        "result": ControlResult.PASS.value,
        "detail": {},
        "exceptions_file_id": None,
        "engine_release_id": engine_release_id,
        "executed_at": INVITED_AT,
        **extra,
    }


def control_execution_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-39: an execution of an engine release the builder inserts."""
    release_id = _insert_visible(session, engine_release, engine_release_values())
    return control_execution_values(ctx.tenant_id, engine_release_id=release_id)


def insert_engine_release(session: Session) -> UUID:
    """A probe T-PLT-38 release row for producers that record SOP-1 evidence (REL-03).

    A row is not a stamp: the process that runs a producer must have stamped its own release
    (``support.factories.stamp_test_release``), or ``controls.stamping.process_release_id`` fails
    closed with ``release-mismatch`` — no environment is remembered without a stamp (D-98 60;
    P5-DOCTOR-R1)."""
    return _insert_visible(session, engine_release, engine_release_values())


def audit_chain_verification_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    """T-PLT-23: a scheduled PASS of one event, without digest file or job."""
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "trigger": "SCHEDULED",
        "from_chain_seq": 1,
        "to_chain_seq": 1,
        "events_checked": 1,
        "result": ControlResult.PASS.value,
        "digest_last_hmac": secrets.token_hex(32),
        "started_at": INVITED_AT,
        "finished_at": INVITED_AT,
        **_CREATED,
    }


def insert_audited_tenant(keyring: KeyRing, *, events: int, at: datetime) -> UUID:
    """An ACTIVE tenant holding only its row, its chain head and ``events`` SYSTEM audit events.

    Provisioning writes 12 events (PLF-12, PLF-13), so tests that need an exact chain length use
    this tenant. It publishes no registry values and seeds no roles.
    """
    tenant_id = new_id()
    code = f"audited-{secrets.token_hex(6)}"
    request_id = f"tests-{code}"
    with platform_session(
        "provisioning", actor_user_id=None, request_id=request_id, keyring=keyring
    ) as session:
        session.execute(
            insert(tenant).values(
                id=tenant_id,
                code=code,
                kind=TenantKind.PRODUCTION.value,
                status=TenantStatus.ACTIVE.value,
                display_name=f"Tenant {code}",
                reporting_currency="USD",
                is_demo=False,
                audit_hmac_key_id=keyring.new_tenant_audit_key_id(tenant_id),
                setup_completed_at=None,
                **_SYSTEM,
            )
        )
        name_platform_tenant(session, tenant_id)
        set_tenant_context(session, DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*"))
        session.execute(
            insert(audit_chain_head).values(tenant_id=tenant_id, last_chain_seq=0, updated_at=at)
        )
        actor = AuditActor(
            kind=PrincipalKind.SYSTEM,
            id=None,
            roles=(),
            auth_method=None,
            mfa_verified=None,
            on_behalf_of_id=None,
            api_client_id=None,
            support_grant_id=None,
            source_ip=None,
            request_id=request_id,
        )
        append_events(
            session,
            tenant_id=tenant_id,
            keyring=keyring,
            events=[
                build_event(
                    tenant_id=tenant_id,
                    actor=actor,
                    occurred_at=at,
                    action="tenant.update",
                    object_type="tenant",
                    object_id=tenant_id,
                    detail={"probe": number},
                )
                for number in range(1, events + 1)
            ],
        )
    return tenant_id


def tamper_audit_event(owner_engine: Engine, *, tenant_id: UUID, chain_seq: int) -> None:
    """Change the ``detail`` of one committed audit event the way a provider data fix would, as
    ``erev_owner`` with a data-fix ticket (runbook "Audit log and hash chain"), so verification
    fails from ``chain_seq`` (DG-TST-22)."""
    with owner_engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE erev.audit_event NO FORCE ROW LEVEL SECURITY")
        connection.execute(text("SELECT set_config('app.data_fix_ticket', 'DF-PLF-23', true)"))
        changed = connection.execute(
            text(
                "UPDATE erev.audit_event "
                "SET detail = detail || jsonb_build_object('tampered', true) "
                "WHERE tenant_id = :tenant_id AND chain_seq = :chain_seq"
            ),
            {"tenant_id": tenant_id, "chain_seq": chain_seq},
        ).rowcount
        connection.exec_driver_sql("ALTER TABLE erev.audit_event FORCE ROW LEVEL SECURITY")
    assert changed == 1


def _visible_id(session: Session, statement: Select[Any]) -> UUID:
    value = session.execute(statement).scalar_one_or_none()
    return new_id() if value is None else UUID(str(value))


def _role_id(session: Session, tenant_id: UUID, code: str) -> UUID:
    return _visible_id(
        session, select(role.c.id).where(role.c.tenant_id == tenant_id, role.c.code == code)
    )


def role_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    """T-PLT-09: a custom role without permissions."""
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "code": f"probe_{secrets.token_hex(4)}",
        "name": "Probe role",
        "is_system": False,
        "is_active": True,
        "content_sha256": role_content_sha256(()),
        **_SYSTEM,
    }


def assignment_row(
    tenant_id: UUID,
    *,
    membership_id: UUID,
    role_id: UUID,
    entity_ids: Sequence[UUID] = (),
    valid_to: datetime | None = None,
    revoked_at: datetime | None = None,
) -> dict[str, Any]:
    """T-PLT-10: all entities without ``entity_ids``, else the named entities."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "membership_id": membership_id,
        "role_id": role_id,
        "is_all_entities": not entity_ids,
        "entity_ids": list(entity_ids),
        "valid_from": ASSIGNED_FROM,
        "valid_to": valid_to,
        "revoked_at": revoked_at,
        "revoked_by_kind": None if revoked_at is None else PrincipalKind.SYSTEM.value,
        **_CREATED,
    }


def role_assignment_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-10: the provisioned admin membership holding ``viewer`` for all entities."""
    membership_id = _visible_id(
        session,
        select(tenant_membership.c.id)
        .where(tenant_membership.c.tenant_id == ctx.tenant_id)
        .order_by(tenant_membership.c.id)
        .limit(1),
    )
    return assignment_row(
        ctx.tenant_id,
        membership_id=membership_id,
        role_id=_role_id(session, ctx.tenant_id, "viewer"),
    )


def role_permission_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-12: ``ssp.create`` for the provisioned ``viewer`` role, which lacks it."""
    return {
        "tenant_id": ctx.tenant_id,
        "role_id": _role_id(session, ctx.tenant_id, "viewer"),
        "permission_code": "ssp.create",
        **_CREATED,
    }


def sod_rule_values(
    tenant_id: UUID,
    *,
    code: str,
    function_a: Sequence[str] = ("ssp.create",),
    function_b: Sequence[str] = ("ssp.approve",),
    status: ConfigStatus = ConfigStatus.DRAFT,
    version_no: int = 1,
    **extra: Any,
) -> dict[str, Any]:
    """T-PLT-13: a rule version; outside DRAFT it carries a content hash (DB-04)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": code,
        "name": f"Probe rule {code}",
        "function_a_permissions": list(function_a),
        "function_b_permissions": list(function_b),
        "rationale": "Probe rule",
        **_SYSTEM,
        "version_no": version_no,
        "status": status.value,
        "content_sha256": None if status is ConfigStatus.DRAFT else secrets.token_hex(32),
        **extra,
    }


def sod_rule_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    """T-PLT-13: a DRAFT tenant rule."""
    return sod_rule_values(ctx.tenant_id, code=f"probe-{secrets.token_hex(4)}")


def sod_exception_values(
    tenant_id: UUID,
    *,
    membership_id: UUID,
    rule_code: str = "SoD-3",
    status: GrantStatus = GrantStatus.REQUESTED,
    valid_from: datetime = ASSIGNED_FROM,
    valid_to: datetime = ASSIGNED_FROM + timedelta(days=366),
) -> dict[str, Any]:
    """T-PLT-14: an exception of ``rule_code`` for a membership."""
    approved = status is GrantStatus.APPROVED
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "sod_rule_code": rule_code,
        "membership_id": membership_id,
        "compensating_control": "Controller reviews every approval monthly.",
        "status": status.value,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "approved_at": valid_from if approved else None,
        **_CREATED,
    }


def sod_exception_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-14: a REQUESTED exception for the provisioned admin membership."""
    membership_id = _visible_id(
        session,
        select(tenant_membership.c.id)
        .where(tenant_membership.c.tenant_id == ctx.tenant_id)
        .order_by(tenant_membership.c.id)
        .limit(1),
    )
    return sod_exception_values(ctx.tenant_id, membership_id=membership_id)


def file_object_values(
    tenant_id: UUID,
    *,
    purpose: FilePurpose = FilePurpose.ATTACHMENT,
    size_bytes: int = 1024,
    **extra: Any,
) -> dict[str, Any]:
    """T-PLT-29: metadata of a stored PDF; no object is written to the file store."""
    sha256 = secrets.token_hex(32)
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "sha256": sha256,
        "size_bytes": size_bytes,
        "media_type": "application/pdf",
        "original_filename": "probe.pdf",
        "purpose": purpose.value,
        "storage_backend": "local",
        "storage_key": f"{tenant_id}/{purpose.value}/{sha256}",
        **_CREATED,
        **extra,
    }


def file_object_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return file_object_values(ctx.tenant_id)


def file_attachment_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-30: attaches a file of the tenant to a soft-referenced SoD exception id.

    Provisioning writes no file, so the builder inserts one where the session's context allows it
    and otherwise names a fresh id, which row-level security refuses first.
    """
    visible = session.execute(
        select(file_object.c.id).where(file_object.c.tenant_id == ctx.tenant_id).limit(1)
    ).scalar_one_or_none()
    file_id = new_id() if visible is None else UUID(str(visible))
    if visible is None:
        file_row = file_object_values(ctx.tenant_id)
        savepoint = session.begin_nested()
        try:
            session.execute(insert(file_object).values(**file_row))
        except exc.DBAPIError:
            savepoint.rollback()
        else:
            savepoint.commit()
            file_id = UUID(str(file_row["id"]))
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "file_object_id": file_id,
        "subject_type": "sod_exception",
        "subject_id": new_id(),
        **_CREATED,
    }


def file_upload_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-49: the user's upload of a file of the tenant. As ``file_attachment_row``, the
    builder inserts the file where the session's context allows it and otherwise names a fresh
    id, which row-level security refuses first."""
    attachment = file_attachment_row(ctx, session)
    return {
        "tenant_id": ctx.tenant_id,
        "file_object_id": attachment["file_object_id"],
        "uploaded_by": ctx.user_id,
        "uploaded_by_kind": PrincipalKind.USER.value,
        "original_filename": "probe.pdf",
        "uploaded_at": INVITED_AT,
    }


def numbering_series_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    """T-PLT-26: the gapless ``JE`` series of a stand-in entity id."""
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "series_code": "JE",
        "scope_key": str(new_id()),
        "prefix": "JE-PROBE-",
        "next_value": 1,
        "padding": 6,
        "is_gapless": True,
        "updated_by_kind": PrincipalKind.SYSTEM.value,
    }


def job_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    """T-PLT-27: a QUEUED job that no worker was told about."""
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "kind": JobKind.AUDIT_CHAIN_VERIFY.value,
        "params": {},
        "queue": "maintenance",
        **_SYSTEM,
    }


def _first_membership(ctx: RowContext, session: Session) -> UUID:
    """The provisioned admin membership, or a fresh id where the context hides it."""
    return _visible_id(
        session,
        select(tenant_membership.c.id)
        .where(tenant_membership.c.tenant_id == ctx.tenant_id)
        .order_by(tenant_membership.c.id)
        .limit(1),
    )


def notification_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-24: an unread notification of the provisioned admin membership."""
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "recipient_membership_id": _first_membership(ctx, session),
        "kind": NotificationKind.ITEM_APPROVED.value,
        "title": "Probe notification",
        **_CREATED,
    }


def notification_preference_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-25: the ``ITEM_APPROVED`` preference of the provisioned admin membership."""
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "membership_id": _first_membership(ctx, session),
        "kind": NotificationKind.ITEM_APPROVED.value,
        "in_app": True,
        "email": False,
        "updated_by_kind": PrincipalKind.SYSTEM.value,
    }


def saved_view_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-37: a private SF-02 view of the provisioned admin membership."""
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "membership_id": _first_membership(ctx, session),
        "screen_code": "SF-02",
        "name": f"Probe view {secrets.token_hex(4)}",
        "config": {"sort": "-id"},
        **_SYSTEM,
    }


def outbox_message_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    """T-INT-03: a PENDING probe message that no relay was told about."""
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "topic": OutboxTopic.WEBHOOK.value,
        "aggregate_type": "probe",
        "aggregate_id": new_id(),
        "dedupe_key": f"probe:{secrets.token_hex(8)}",
        "payload": {},
        **_SYSTEM,
    }


def integration_connection_values(tenant_id: UUID, **values: Any) -> dict[str, Any]:
    """T-INT-01: a DISABLED inbound Salesforce connection over the in-process mock; ``secret_ref``
    is a reference name, never a value (REQ-INT-006), in the tenant's own namespace of the secret
    store (rev 1.108)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": f"sf-probe-{secrets.token_hex(4)}",
        "name": "Salesforce (probe)",
        "adapter": "SALESFORCE",
        "direction": "INBOUND",
        "entity_ids": [],
        "base_url": "/api/v1/__mocks__/salesforce",
        "config": {},
        "secret_ref": f"{adapter_secret_namespace(tenant_id)}sf-probe-webhook-secret",
        "status": "DISABLED",
        "checkpoint": {},
        **_SYSTEM,
        **values,
    }


def integration_connection_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return integration_connection_values(ctx.tenant_id)


def sync_run_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-INT-02: a QUEUED poll of a connection the builder inserts where the context allows."""
    connection_id = _insert_visible(
        session, integration_connection, integration_connection_values(ctx.tenant_id)
    )
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "integration_connection_id": connection_id,
        "kind": "INBOUND_POLL",
        "status": "QUEUED",
        "checkpoint_before": {},
        **_SYSTEM,
    }


def external_id_map_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-INT-04: a live customer link of a connection the builder inserts where the context
    allows."""
    connection_id = _insert_visible(
        session, integration_connection, integration_connection_values(ctx.tenant_id)
    )
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "integration_connection_id": connection_id,
        "object_type": "customer",
        "internal_id": new_id(),
        "external_id": f"ACC-P{secrets.token_hex(5)}",
        **_CREATED,
    }


def api_client_values(tenant_id: UUID, **values: Any) -> dict[str, Any]:
    """T-PLT-15: an ACTIVE all-entities client reading contracts, with a placeholder hash."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "name": "svc-probe",
        "client_id": f"erevc_{tenant_id.hex}_{secrets.token_urlsafe(16)}",
        "secret_hash": "$argon2id$probe",
        "scopes": ["contract.read"],
        "expires_at": datetime(2027, 9, 12, 12, tzinfo=UTC),
        **_SYSTEM,
        **values,
    }


def api_client_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return api_client_values(ctx.tenant_id)


def api_token_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-16: an open token of a client the builder inserts where the context allows."""
    client_id = _insert_visible(session, api_client, api_client_values(ctx.tenant_id))
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "api_client_id": client_id,
        "token_sha256": secrets.token_hex(32),
        "scopes": ["contract.read"],
        "issued_at": INVITED_AT,
        "expires_at": INVITED_AT + timedelta(minutes=60),
    }


def webhook_endpoint_values(tenant_id: UUID, *, keyring: KeyRing | None = None) -> dict[str, Any]:
    """T-PLT-35: an active endpoint for ``period.locked`` with a placeholder sealed secret, or with
    a real SAR-07 envelope under ``keyring`` (the recovery verifier probes it; review P6-R5)."""
    endpoint_id = new_id()
    ciphertext: bytes = b"erev1probe"
    key_id = "kek:1"
    if keyring is not None:
        from erev_api.events.webhooks import secret_context

        ciphertext = keyring.encrypt(
            b"whsec_probe_secret", context=secret_context(tenant_id, endpoint_id)
        )
        key_id = keyring.envelope_key_id(ciphertext)
    return {
        "tenant_id": tenant_id,
        "id": endpoint_id,
        "url": "https://hooks.example/erev",
        "event_kinds": ["period.locked"],
        "secret_ciphertext": ciphertext,
        "secret_key_id": key_id,
        **_SYSTEM,
    }


def insert_sealed_webhook_endpoint(session: Session, tenant_id: UUID, *, keyring: KeyRing) -> UUID:
    """A webhook endpoint whose secret is a real envelope under ``keyring`` (P6-R5 probes)."""
    values = webhook_endpoint_values(tenant_id, keyring=keyring)
    session.execute(insert(webhook_endpoint).values(**values))
    return UUID(str(values["id"]))


def insert_sealed_mfa_factor(
    session: Session,
    user_id: UUID,
    *,
    keyring: KeyRing,
    seed: str = "JBSWY3DPEHPK3PXP",
    at: datetime = datetime(2026, 9, 12, 12, tzinfo=UTC),
) -> UUID:
    """T-PLT-04: a confirmed TOTP factor whose seed is a real envelope under ``keyring``, inserted
    through an identity session (global table); the recovery verifier probes it (P6-R5), and
    ``support.principals.authenticator`` gives a member who must use MFA their factor with it
    (``seed`` in base32, ``at`` the confirmation time)."""
    from erev_api.auth.mfa import secret_context

    factor_id = new_id()
    ciphertext = keyring.encrypt(seed.encode("ascii"), context=secret_context(factor_id))
    session.execute(
        insert(user_mfa_factor).values(
            id=factor_id,
            user_id=user_id,
            factor_kind="TOTP",
            secret_ciphertext=ciphertext,
            secret_key_id=keyring.envelope_key_id(ciphertext),
            confirmed_at=at,
            **_SYSTEM,
        )
    )
    return factor_id


def webhook_endpoint_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return webhook_endpoint_values(ctx.tenant_id)


def webhook_delivery_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-36: a PENDING delivery to an endpoint the builder inserts where the context allows."""
    endpoint_id = _insert_visible(session, webhook_endpoint, webhook_endpoint_values(ctx.tenant_id))
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "webhook_endpoint_id": endpoint_id,
        "event_kind": "period.locked",
        "payload": {},
        "payload_sha256": "0" * 64,
        "abandon_at": datetime(2026, 9, 13, 12, tzinfo=UTC),
        **_CREATED,
    }


def idempotency_record_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return {
        "tenant_id": ctx.tenant_id,
        "principal_id": ctx.user_id,
        "idempotency_key": f"rows-{secrets.token_hex(8)}",
        "principal_kind": PrincipalKind.USER.value,
        "method": "POST",
        "path": "/api/v1/rows",
        "request_sha256": "0" * 64,
        "created_at": INVITED_AT,
        "expires_at": INVITED_AT + timedelta(days=7),
    }


PROBE_CONTENT_SHA256: Final = "c" * 64


def _insert_visible(session: Session, table: Table, row: Mapping[str, Any]) -> UUID:
    """Insert ``row`` in a savepoint and return its id, or a fresh id when the session's context
    refuses the insert (row-level security then refuses the dependent row first)."""
    savepoint = session.begin_nested()
    try:
        session.execute(insert(table).values(**row))
    except exc.DBAPIError:
        savepoint.rollback()
        return new_id()
    savepoint.commit()
    return UUID(str(row["id"]))


def approval_request_values(
    tenant_id: UUID,
    *,
    status: ApprovalRequestStatus = ApprovalRequestStatus.PENDING,
    preparer_id: UUID | None = None,
    subject_id: UUID | None = None,
    entity_id: UUID | None = None,
    subject_content_sha256: str = PROBE_CONTENT_SHA256,
    **extra: Any,
) -> dict[str, Any]:
    """T-PLT-17: a ``ROLE_CHANGE`` request of ``preparer_id``, or of the system without one."""
    decided = status is not ApprovalRequestStatus.PENDING
    preparer_kind = PrincipalKind.SYSTEM if preparer_id is None else PrincipalKind.USER
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "request_no": f"APR-P{secrets.token_hex(5)}",
        "subject_type": ApprovalSubjectType.ROLE_CHANGE.value,
        "subject_id": subject_id or new_id(),
        "subject_content_sha256": subject_content_sha256,
        "summary": "Probe approval request",
        "entity_id": entity_id,
        "status": status.value,
        "preparer_id": preparer_id,
        "preparer_kind": preparer_kind.value,
        "submitted_at": INVITED_AT,
        "decided_at": INVITED_AT if decided else None,
        **_CREATED,
        **extra,
    }


def approval_step_values(
    tenant_id: UUID,
    *,
    approval_request_id: UUID,
    step_no: int = 1,
    status: ApprovalStepStatus = ApprovalStepStatus.ACTIVE,
    **extra: Any,
) -> dict[str, Any]:
    """T-PLT-18: an ``access.approve`` step with one approver."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "approval_request_id": approval_request_id,
        "step_no": step_no,
        "name": "Approval",
        "required_permission": "access.approve",
        "min_approvers": 1,
        "status": status.value,
        "activated_at": INVITED_AT if status is ApprovalStepStatus.ACTIVE else None,
        **extra,
    }


def approval_decision_values(
    tenant_id: UUID,
    *,
    approval_request_id: UUID,
    approval_step_id: UUID,
    approver_id: UUID,
    subject_content_sha256: str = PROBE_CONTENT_SHA256,
    **extra: Any,
) -> dict[str, Any]:
    """T-PLT-20: an MFA-verified APPROVE of a user."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "approval_request_id": approval_request_id,
        "approval_step_id": approval_step_id,
        "decision": ApprovalDecisionKind.APPROVE.value,
        "approver_id": approver_id,
        "approver_kind": PrincipalKind.USER.value,
        "subject_content_sha256": subject_content_sha256,
        "mfa_verified_at": INVITED_AT,
        "decided_at": INVITED_AT,
        **extra,
    }


def approval_delegation_values(
    tenant_id: UUID,
    *,
    delegator_membership_id: UUID,
    delegate_membership_id: UUID,
    valid_from: datetime = ASSIGNED_FROM,
    valid_to: datetime = ASSIGNED_FROM + timedelta(days=30),
) -> dict[str, Any]:
    """T-PLT-21: a delegation of ``access.approve``."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "delegator_membership_id": delegator_membership_id,
        "delegate_membership_id": delegate_membership_id,
        "permissions": ["access.approve"],
        "valid_from": valid_from,
        "valid_to": valid_to,
        "reason": "Annual leave",
        **_CREATED,
    }


def approval_request_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return approval_request_values(ctx.tenant_id)


def approval_step_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-18: the first step of a request the builder inserts where the context allows it."""
    request_id = _insert_visible(session, approval_request, approval_request_values(ctx.tenant_id))
    return approval_step_values(ctx.tenant_id, approval_request_id=request_id)


def approval_delegation_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-21: the provisioned admin membership delegates to an ACTIVE membership of the user."""
    delegator = _visible_id(
        session,
        select(tenant_membership.c.id)
        .where(tenant_membership.c.tenant_id == ctx.tenant_id)
        .order_by(tenant_membership.c.id)
        .limit(1),
    )
    delegate = _insert_visible(
        session, tenant_membership, membership_row(ctx, status=MembershipStatus.ACTIVE)
    )
    return approval_delegation_values(
        ctx.tenant_id, delegator_membership_id=delegator, delegate_membership_id=delegate
    )


def approval_decision_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-20: the user, with an ACTIVE membership, approves the active step of a system
    request; every prerequisite is inserted where the context allows it (DB-10)."""
    tenant_id = ctx.tenant_id
    request_id = _insert_visible(session, approval_request, approval_request_values(tenant_id))
    step_id = _insert_visible(
        session, approval_step, approval_step_values(tenant_id, approval_request_id=request_id)
    )
    _insert_visible(session, tenant_membership, membership_row(ctx, status=MembershipStatus.ACTIVE))
    return approval_decision_values(
        tenant_id,
        approval_request_id=request_id,
        approval_step_id=step_id,
        approver_id=ctx.user_id,
    )


def rule_set_values(
    tenant_id: UUID, *, code: str | None = None, kind: RuleSetKind = RuleSetKind.APPROVAL_ROUTING
) -> dict[str, Any]:
    """T-REF-24: a decision table of ``kind``."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": code or f"PROBE-{secrets.token_hex(4).upper()}",
        "name": "Probe rule set",
        "kind": kind.value,
        "description": None,
        **_SYSTEM,
    }


def rule_set_version_values(
    tenant_id: UUID,
    *,
    rule_set_id: UUID,
    kind: RuleSetKind = RuleSetKind.APPROVAL_ROUTING,
    status: ConfigStatus = ConfigStatus.DRAFT,
    version_no: int = 1,
    **extra: Any,
) -> dict[str, Any]:
    """T-REF-25: a version; outside DRAFT it carries a content hash (DB-04)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "rule_set_id": rule_set_id,
        "kind": kind.value,
        **_SYSTEM,
        "version_no": version_no,
        "status": status.value,
        "content_sha256": None if status is ConfigStatus.DRAFT else secrets.token_hex(32),
        **extra,
    }


PROBE_ROUTING_CONDITIONS: Final = ({"field": "subject.type", "op": "eq", "value": "ROLE_CHANGE"},)
PROBE_ROUTING_OUTPUTS: Final = MappingProxyType(
    {"steps": [{"name": "Approval", "permission": "access.approve", "min_approvers": 1}]}
)


def rule_values(
    tenant_id: UUID,
    *,
    rule_set_version_id: UUID,
    rule_key: str = "PROBE-RULE",
    kind: RuleSetKind = RuleSetKind.APPROVAL_ROUTING,
    conditions: Sequence[Mapping[str, Any]] = PROBE_ROUTING_CONDITIONS,
    outputs: Mapping[str, Any] = PROBE_ROUTING_OUTPUTS,
    priority: int = 0,
) -> dict[str, Any]:
    """T-REF-26: a rule whose specificity counts its distinct condition fields."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "rule_set_version_id": rule_set_version_id,
        "rule_key": rule_key,
        "priority": priority,
        "conditions": [dict(condition) for condition in conditions],
        "outputs": dict(outputs),
        "specificity": validate_conditions(kind.value, conditions),
        "description": None,
    }


def rule_test_case_values(
    tenant_id: UUID, *, subject_id: UUID, subject_type: str = "rule_set_version"
) -> dict[str, Any]:
    """T-REF-27: an example case of a configuration version."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "subject_type": subject_type,
        "subject_id": subject_id,
        "name": "Probe case",
        "input": {"subject.type": "ROLE_CHANGE"},
        "expected_output": {"steps": 1},
        **_SYSTEM,
    }


def rule_set_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return rule_set_values(ctx.tenant_id)


def rule_set_version_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-25: a DRAFT version of a rule set the builder inserts where the context allows it."""
    rule_set_id = _insert_visible(session, rule_set, rule_set_values(ctx.tenant_id))
    return rule_set_version_values(ctx.tenant_id, rule_set_id=rule_set_id)


def _draft_rule_set_version(ctx: RowContext, session: Session) -> UUID:
    return _insert_visible(session, rule_set_version, rule_set_version_row(ctx, session))


def rule_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-26: a rule of a DRAFT version, which DB-04 lets change."""
    return rule_values(ctx.tenant_id, rule_set_version_id=_draft_rule_set_version(ctx, session))


def rule_test_case_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-27: a test case of a DRAFT rule set version."""
    return rule_test_case_values(ctx.tenant_id, subject_id=_draft_rule_set_version(ctx, session))


def pob_template_values(tenant_id: UUID, *, code: str | None = None) -> dict[str, Any]:
    """T-REF-22: an obligation template."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": code or f"TPL-{secrets.token_hex(4).upper()}",
        "name": "Probe template",
        "description": None,
        **_SYSTEM,
    }


def pob_template_version_values(
    tenant_id: UUID,
    *,
    pob_template_id: UUID,
    status: ConfigStatus = ConfigStatus.DRAFT,
    version_no: int = 1,
    **extra: Any,
) -> dict[str, Any]:
    """T-REF-23: a point-in-time version; outside DRAFT it carries a content hash (DB-04)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "pob_template_id": pob_template_id,
        "satisfaction_pattern": "POINT_IN_TIME",
        "recognition_method": "POINT_IN_TIME",
        **_SYSTEM,
        "version_no": version_no,
        "status": status.value,
        "content_sha256": None if status is ConfigStatus.DRAFT else secrets.token_hex(32),
        **extra,
    }


def pob_template_version_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-23: a DRAFT version of a template the builder inserts where the context allows it."""
    template_id = _insert_visible(session, pob_template, pob_template_values(ctx.tenant_id))
    return pob_template_version_values(ctx.tenant_id, pob_template_id=template_id)


def publish_rule_set(
    session: Session,
    *,
    tenant_id: UUID,
    kind: RuleSetKind,
    rules: Sequence[Mapping[str, Any]],
    code: str | None = None,
    at: datetime = INVITED_AT,
) -> tuple[UUID, dict[str, UUID]]:
    """Walk a new rule set version DRAFT → TESTED → SUBMITTED → APPROVED → PUBLISHED, as the
    configuration lifecycle will once rule set commands exist (DB-04; RFD). ``rules`` holds
    ``rule_values`` keyword arguments. Returns the version id and the rule ids by rule key."""
    set_row = rule_set_values(tenant_id, code=code, kind=kind)
    session.execute(insert(rule_set).values(**set_row))
    version = rule_set_version_values(tenant_id, rule_set_id=set_row["id"], kind=kind)
    session.execute(insert(rule_set_version).values(**version))
    rule_ids: dict[str, UUID] = {}
    for values in rules:
        row = rule_values(tenant_id, rule_set_version_id=version["id"], kind=kind, **values)
        session.execute(insert(rule).values(**row))
        rule_ids[row["rule_key"]] = row["id"]
    where = rule_set_version.c.id == version["id"]
    session.execute(
        update(rule_set_version)
        .where(where)
        .values(status=ConfigStatus.TESTED.value, content_sha256=secrets.token_hex(32))
    )
    session.execute(
        update(rule_set_version).where(where).values(status=ConfigStatus.SUBMITTED.value)
    )
    request_id = insert_approval_request(
        session,
        tenant_id=tenant_id,
        status=ApprovalRequestStatus.APPROVED,
        subject_type=ApprovalSubjectType.RULE_SET_VERSION.value,
        subject_id=version["id"],
    )
    session.execute(
        update(rule_set_version)
        .where(where)
        .values(status=ConfigStatus.APPROVED.value, approval_request_id=request_id)
    )
    session.execute(
        update(rule_set_version)
        .where(where)
        .values(status=ConfigStatus.PUBLISHED.value, published_at=at)
    )
    return UUID(str(version["id"])), rule_ids


def registry_version_values(
    tenant_id: UUID,
    *,
    category: RegistryCategory = RegistryCategory.PLATFORM,
    scope: RegistryScope = RegistryScope.TENANT,
    values: Mapping[str, Any] | None = None,
    status: ConfigStatus = ConfigStatus.DRAFT,
    version_no: int = 2,
    book_code: BookCode | None = None,
    entity_id: UUID | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """T-PLT-32: a version; provisioning holds version 1 of every TENANT category (DEFAULT).
    Outside DRAFT it carries a content hash (DB-04)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "category": category.value,
        "scope": scope.value,
        "book_code": None if book_code is None else book_code.value,
        "entity_id": entity_id,
        "values": dict(values or {}),
        "preset_code": None,
        "test_evidence": None,
        "impact_simulation_file_id": None,
        **_SYSTEM,
        "version_no": version_no,
        "status": status.value,
        "content_sha256": None if status is ConfigStatus.DRAFT else secrets.token_hex(32),
        **extra,
    }


def registry_version_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return registry_version_values(ctx.tenant_id)


def insert_registry_version(session: Session, *, tenant_id: UUID, **values: Any) -> UUID:
    row = registry_version_values(tenant_id, **values)
    session.execute(insert(registry_version).values(**row))
    return UUID(str(row["id"]))


def publish_registry_version(
    session: Session,
    *,
    tenant_id: UUID,
    category: RegistryCategory,
    values: Mapping[str, Any],
    scope: RegistryScope = RegistryScope.TENANT,
    book_code: BookCode | None = None,
    entity_id: UUID | None = None,
    at: datetime = INVITED_AT,
    preset_code: str | None = None,
    published_by: UUID | None = None,
    **extra: Any,
) -> UUID:
    """Supersede the PUBLISHED version of the scope key at ``at``, then walk a new version from
    ``at`` DRAFT → TESTED → SUBMITTED → APPROVED → PUBLISHED, as the configuration commands will
    once they exist (DB-04; RFD). ``preset_code`` names a preset such as ``LEGACY_PARITY``
    (T-PLT-32; BUILD_SPEC DIN-4). ``published_by`` is the publisher SC-V records (none: an
    automatic approval) and ``extra`` other columns of the new row, such as its author. Returns the
    new version id."""
    table = registry_version
    key: list[ColumnElement[bool]] = [
        table.c.tenant_id == tenant_id,
        table.c.category == category.value,
        table.c.scope == scope.value,
        table.c.book_code.is_(None) if book_code is None else table.c.book_code == book_code.value,
        table.c.entity_id.is_(None) if entity_id is None else table.c.entity_id == entity_id,
    ]
    highest = session.execute(select(func.max(table.c.version_no)).where(*key)).scalar_one()
    current = session.execute(
        select(table.c.id).where(*key, table.c.status == ConfigStatus.PUBLISHED.value)
    ).scalar_one_or_none()
    if current is not None:
        session.execute(
            update(table)
            .where(table.c.id == current)
            .values(status=ConfigStatus.SUPERSEDED.value, effective_to=at)
        )
    version = registry_version_values(
        tenant_id,
        category=category,
        scope=scope,
        values=values,
        version_no=int(highest or 0) + 1,
        book_code=book_code,
        entity_id=entity_id,
        effective_from=at,
        supersedes_version_id=current,
        preset_code=preset_code,
        **extra,
    )
    session.execute(insert(table).values(**version))
    where = table.c.id == version["id"]
    session.execute(
        update(table)
        .where(where)
        .values(status=ConfigStatus.TESTED.value, content_sha256=secrets.token_hex(32))
    )
    session.execute(update(table).where(where).values(status=ConfigStatus.SUBMITTED.value))
    request_id = insert_approval_request(
        session,
        tenant_id=tenant_id,
        status=ApprovalRequestStatus.APPROVED,
        subject_type=ApprovalSubjectType.REGISTRY_VERSION.value,
        subject_id=version["id"],
    )
    session.execute(
        update(table)
        .where(where)
        .values(status=ConfigStatus.APPROVED.value, approval_request_id=request_id)
    )
    session.execute(
        update(table)
        .where(where)
        .values(status=ConfigStatus.PUBLISHED.value, published_at=at, published_by=published_by)
    )
    return UUID(str(version["id"]))


def access_review_campaign_values(
    tenant_id: UUID, *, reviewer_membership_ids: Sequence[UUID]
) -> dict[str, Any]:
    """T-PLT-40: a DRAFT campaign as of ``INVITED_AT``."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "name": "Probe access review",
        "as_of": INVITED_AT,
        "reviewer_membership_ids": list(reviewer_membership_ids),
        **_SYSTEM,
    }


def access_review_item_values(
    tenant_id: UUID,
    *,
    access_review_campaign_id: UUID,
    membership_id: UUID,
    reviewer_id: UUID | None = None,
) -> dict[str, Any]:
    """T-PLT-41: a PENDING item, or a CERTIFIED one when ``reviewer_id`` is given."""
    decision = (
        AccessReviewDecision.PENDING if reviewer_id is None else AccessReviewDecision.CERTIFIED
    )
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "access_review_campaign_id": access_review_campaign_id,
        "membership_id": membership_id,
        "user_email_snapshot": "probe@members.test",
        "roles_snapshot": [],
        "decision": decision.value,
        "reviewer_id": reviewer_id,
        "decided_at": None if reviewer_id is None else INVITED_AT,
        **_SYSTEM,
    }


def access_review_campaign_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-40: a campaign reviewed by the provisioned admin membership."""
    return access_review_campaign_values(
        ctx.tenant_id, reviewer_membership_ids=[_first_membership(ctx, session)]
    )


def access_review_item_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-PLT-41: the provisioned admin membership under a campaign the builder inserts where the
    context allows it."""
    campaign_id = _insert_visible(
        session, access_review_campaign, access_review_campaign_row(ctx, session)
    )
    return access_review_item_values(
        ctx.tenant_id,
        access_review_campaign_id=campaign_id,
        membership_id=_first_membership(ctx, session),
    )


def fiscal_calendar_values(tenant_id: UUID, *, code: str | None = None) -> dict[str, Any]:
    """T-REF-04: a monthly calendar starting in January."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": code or f"CAL-{secrets.token_hex(4).upper()}",
        "name": "Probe calendar",
        "pattern": CalendarPattern.MONTHLY.value,
        "fiscal_year_start_month": 1,
        "week_end_day": None,
        "year_end_anchor": None,
        **_SYSTEM,
    }


def period_values(
    tenant_id: UUID,
    *,
    calendar_id: UUID,
    fiscal_year: int = 2026,
    period_no: int = 1,
    start_date: date = date(2026, 1, 1),
    end_date: date = date(2026, 1, 31),
) -> dict[str, Any]:
    """T-REF-05: a period of ``calendar_id``; the defaults are FY2026-P01 of a January calendar."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "calendar_id": calendar_id,
        "fiscal_year": fiscal_year,
        "period_no": period_no,
        "quarter_no": min((period_no - 1) // 3 + 1, 4),
        "period_key": f"FY{fiscal_year}-P{period_no:02d}",
        "name": "Probe period",
        "start_date": start_date,
        "end_date": end_date,
        **_SYSTEM,
    }


def fiscal_calendar_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return fiscal_calendar_values(ctx.tenant_id)


def period_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-05: the first period of a calendar the builder inserts where the context allows it."""
    calendar_id = _insert_visible(session, fiscal_calendar, fiscal_calendar_values(ctx.tenant_id))
    return period_values(ctx.tenant_id, calendar_id=calendar_id)


def gl_account_values(tenant_id: UUID, *, code: str | None = None) -> dict[str, Any]:
    """T-REF-13: an active debit asset account for all entities."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": code or f"ACC-{secrets.token_hex(4).upper()}",
        "name": "Probe account",
        "account_type": AccountType.ASSET.value,
        "normal_balance": "D",
        **_SYSTEM,
    }


def dimension_definition_values(
    tenant_id: UUID, *, code: str | None = None, is_builtin: bool = False, position: int = 6
) -> dict[str, Any]:
    """T-REF-16: a custom dimension; provisioning already wrote the five built-in ones."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": code or f"probe_{secrets.token_hex(4)}",
        "name": "Probe dimension",
        "is_builtin": is_builtin,
        "position": position,
        **_SYSTEM,
    }


def dimension_value_values(
    tenant_id: UUID, *, dimension_definition_id: UUID, code: str | None = None
) -> dict[str, Any]:
    """T-REF-17: a value without a parent of ``dimension_definition_id``."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "dimension_definition_id": dimension_definition_id,
        "code": code or f"V-{secrets.token_hex(4).upper()}",
        "name": "Probe value",
        "parent_value_id": None,
        **_SYSTEM,
    }


def gl_account_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return gl_account_values(ctx.tenant_id)


def dimension_definition_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return dimension_definition_values(ctx.tenant_id)


def dimension_value_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-17: a value of a custom dimension the builder inserts where the context allows it."""
    definition_id = _insert_visible(
        session, dimension_definition, dimension_definition_values(ctx.tenant_id)
    )
    return dimension_value_values(ctx.tenant_id, dimension_definition_id=definition_id)


def legal_entity_values(
    tenant_id: UUID,
    *,
    calendar_id: UUID,
    entity_id: UUID | None = None,
    code: str | None = None,
    functional_currency: str = "USD",
    time_zone: str = "America/New_York",
) -> dict[str, Any]:
    """T-REF-01: an active entity of ``calendar_id``."""
    return {
        "tenant_id": tenant_id,
        "id": entity_id or new_id(),
        "code": code or f"ENT-{secrets.token_hex(4).upper()}",
        "name": "Probe entity",
        "functional_currency": functional_currency,
        "time_zone": time_zone,
        "calendar_id": calendar_id,
        **_SYSTEM,
    }


def entity_book_values(
    tenant_id: UUID,
    *,
    entity_id: UUID,
    first_period_id: UUID,
    book_code: BookCode = BookCode.ASC606,
) -> dict[str, Any]:
    """T-REF-03: an enabled book of ``entity_id`` from ``first_period_id``."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "entity_id": entity_id,
        "book_code": book_code.value,
        "first_period_id": first_period_id,
        **_SYSTEM,
    }


def period_state_values(
    tenant_id: UUID,
    *,
    entity_id: UUID,
    period_id: UUID,
    period_end_date: date = date(2026, 1, 31),
    book_code: BookCode = BookCode.ASC606,
    state: str = "future",
) -> dict[str, Any]:
    """T-REF-06: the state of a period for an entity and book (SC-M only)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "entity_id": entity_id,
        "book_code": book_code.value,
        "period_id": period_id,
        "period_end_date": period_end_date,
        "state": state,
        "updated_by_kind": PrincipalKind.SYSTEM.value,
    }


def period_state_transition_values(
    tenant_id: UUID,
    *,
    period_state_id: UUID,
    entity_id: UUID,
    period_id: UUID,
    from_state: str | None = None,
    to_state: str = "future",
    book_code: BookCode = BookCode.ASC606,
    **values: Any,
) -> dict[str, Any]:
    """T-REF-07: a transition row, by default the creation pair NULL → future."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "period_state_id": period_state_id,
        "entity_id": entity_id,
        "book_code": book_code.value,
        "period_id": period_id,
        "from_state": from_state,
        "to_state": to_state,
        **_CREATED,
        **values,
    }


def _entity_chain(ctx: RowContext, session: Session) -> tuple[UUID, UUID]:
    """(period id, entity id) of a calendar, its FY2026-P01 and an entity of that calendar, each
    inserted where the context allows it."""
    calendar_id = _insert_visible(session, fiscal_calendar, fiscal_calendar_values(ctx.tenant_id))
    period_id = _insert_visible(
        session, period, period_values(ctx.tenant_id, calendar_id=calendar_id)
    )
    entity_id = _insert_visible(
        session, legal_entity, legal_entity_values(ctx.tenant_id, calendar_id=calendar_id)
    )
    return period_id, entity_id


def legal_entity_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-01: an entity of a calendar the builder inserts where the context allows it."""
    calendar_id = _insert_visible(session, fiscal_calendar, fiscal_calendar_values(ctx.tenant_id))
    return legal_entity_values(ctx.tenant_id, calendar_id=calendar_id)


def book_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-02: the provisioned primary book ASC606 (``PROVISIONED_TABLES``; 04 §14.3)."""
    book_id = _visible_id(
        session,
        select(book.c.id).where(
            book.c.tenant_id == ctx.tenant_id, book.c.code == BookCode.ASC606.value
        ),
    )
    return {
        "tenant_id": ctx.tenant_id,
        "id": book_id,
        "code": BookCode.ASC606.value,
        "name": "ASC 606",
        "is_primary": True,
        "is_enabled": True,
        "posting_target": "GL_PRIMARY",
        **_SYSTEM,
    }


def entity_book_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    period_id, entity_id = _entity_chain(ctx, session)
    return entity_book_values(ctx.tenant_id, entity_id=entity_id, first_period_id=period_id)


def period_state_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    period_id, entity_id = _entity_chain(ctx, session)
    return period_state_values(ctx.tenant_id, entity_id=entity_id, period_id=period_id)


def period_state_transition_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-07: the creation transition of a state the builder inserts where the context allows."""
    period_id, entity_id = _entity_chain(ctx, session)
    state_id = _insert_visible(
        session,
        period_state,
        period_state_values(ctx.tenant_id, entity_id=entity_id, period_id=period_id),
    )
    return period_state_transition_values(
        ctx.tenant_id, period_state_id=state_id, entity_id=entity_id, period_id=period_id
    )


def tenant_currency_values(
    tenant_id: UUID, *, currency_code: str = "EUR", is_enabled: bool = True
) -> dict[str, Any]:
    """T-REF-09: a currency of the tenant; provisioning already enabled the reporting currency."""
    return {
        "tenant_id": tenant_id,
        "currency_code": currency_code,
        "is_enabled": is_enabled,
        **_SYSTEM,
    }


def fx_rate_set_values(
    tenant_id: UUID, *, code: str | None = None, rate_type: RateType = RateType.SPOT
) -> dict[str, Any]:
    """T-REF-10: a manual rate series."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": code or f"RATES-{secrets.token_hex(4).upper()}",
        "name": "Probe rates",
        "rate_type": rate_type.value,
        "source": "MANUAL",
        **_SYSTEM,
    }


def fx_rate_set_version_values(
    tenant_id: UUID,
    *,
    fx_rate_set_id: UUID,
    status: ConfigStatus = ConfigStatus.DRAFT,
    version_no: int = 1,
    coverage_from: date = date(2026, 9, 1),
    coverage_to: date = date(2026, 9, 30),
    **extra: Any,
) -> dict[str, Any]:
    """T-REF-11: a version covering September 2026; outside DRAFT it carries a hash (DB-04)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "fx_rate_set_id": fx_rate_set_id,
        "coverage_from": coverage_from,
        "coverage_to": coverage_to,
        "rate_count": 0,
        **_SYSTEM,
        "version_no": version_no,
        "status": status.value,
        "content_sha256": None if status is ConfigStatus.DRAFT else secrets.token_hex(32),
        **extra,
    }


def fx_rate_values(
    tenant_id: UUID,
    *,
    fx_rate_set_version_id: UUID,
    base_currency: str = "EUR",
    quote_currency: str = "USD",
    effective_date: date = date(2026, 9, 15),
    rate: Decimal = Decimal("1.105"),
) -> dict[str, Any]:
    """T-REF-12: an entered spot rate of a version."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "fx_rate_set_version_id": fx_rate_set_version_id,
        "rate_type": RateType.SPOT.value,
        "base_currency": base_currency,
        "quote_currency": quote_currency,
        "effective_date": effective_date,
        "period_id": None,
        "rate": rate,
        "is_derived": False,
    }


def fx_rate_set_version_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-11: a DRAFT version of a set the builder inserts where the context allows it."""
    set_id = _insert_visible(session, fx_rate_set_table, fx_rate_set_values(ctx.tenant_id))
    return fx_rate_set_version_values(ctx.tenant_id, fx_rate_set_id=set_id)


def fx_rate_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-12: a rate of a DRAFT version, which DB-04 lets change."""
    version_id = _insert_visible(
        session, fx_rate_set_version_table, fx_rate_set_version_row(ctx, session)
    )
    return fx_rate_values(ctx.tenant_id, fx_rate_set_version_id=version_id)


def related_party_group_values(tenant_id: UUID, *, code: str | None = None) -> dict[str, Any]:
    """T-REF-18: a related-party group without a description."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": code or f"GROUP-{secrets.token_hex(4).upper()}",
        "name": "Probe group",
        "description": None,
        **_SYSTEM,
    }


def customer_values(
    tenant_id: UUID,
    *,
    code: str | None = None,
    source_system: SourceSystem = SourceSystem.MANUAL_UI,
    external_id: str | None = None,
    related_party_group_id: UUID | None = None,
) -> dict[str, Any]:
    """T-REF-19: an active customer, by default without a group, parent or external id."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": code or f"CUST-{secrets.token_hex(4).upper()}",
        "name": "Probe customer",
        "related_party_group_id": related_party_group_id,
        "source_system": source_system.value,
        "external_id": external_id,
        **_SYSTEM,
    }


def account_mapping_version_values(
    tenant_id: UUID,
    *,
    status: ConfigStatus = ConfigStatus.DRAFT,
    version_no: int = 1,
    **extra: Any,
) -> dict[str, Any]:
    """T-REF-14: a mapping version; outside DRAFT it carries a hash (DB-04)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "name": "Probe mapping",
        "notes": None,
        "impact_simulation_file_id": None,
        **_SYSTEM,
        "version_no": version_no,
        "status": status.value,
        "content_sha256": None if status is ConfigStatus.DRAFT else secrets.token_hex(32),
        **extra,
    }


def account_mapping_rule_values(
    tenant_id: UUID,
    *,
    account_mapping_version_id: UUID,
    gl_account_id: UUID,
    account_role: AccountRole = AccountRole.CONTRACT_LIABILITY,
    clearing_purpose: ClearingPurpose | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """T-REF-15: a rule for any entity, book and product; ``specificity`` is generated."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "account_mapping_version_id": account_mapping_version_id,
        "account_role": account_role.value,
        "clearing_purpose": None if clearing_purpose is None else clearing_purpose.value,
        "gl_account_id": gl_account_id,
        "default_dimensions": {},
        "priority": 0,
        **extra,
    }


def product_values(
    tenant_id: UUID, *, code: str | None = None, is_bundle: bool = False, **extra: Any
) -> dict[str, Any]:
    """T-REF-20: an active product with the column defaults."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": code or f"PROD-{secrets.token_hex(4).upper()}",
        "name": "Probe product",
        "is_bundle": is_bundle,
        **_SYSTEM,
        **extra,
    }


def product_bundle_component_values(
    tenant_id: UUID, *, bundle_product_id: UUID, component_product_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-REF-21: a relative-SSP component valid from 2026-01-01."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "bundle_product_id": bundle_product_id,
        "component_product_id": component_product_id,
        "sequence": 1,
        "valid_from": date(2026, 1, 1),
        **_SYSTEM,
        **extra,
    }


def product_bundle_component_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-21: a component of a probe bundle, both products inserted where the context allows."""
    bundle_id = _insert_visible(session, product, product_values(ctx.tenant_id, is_bundle=True))
    component_id = _insert_visible(session, product, product_values(ctx.tenant_id))
    return product_bundle_component_values(
        ctx.tenant_id, bundle_product_id=bundle_id, component_product_id=component_id
    )


def ssp_book_values(tenant_id: UUID, *, code: str | None = None, **extra: Any) -> dict[str, Any]:
    """T-REF-28: an effective-date book for any entity and currency."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": code or f"SSP-{secrets.token_hex(4).upper()}",
        "name": "Probe SSP book",
        **_SYSTEM,
        **extra,
    }


def ssp_book_version_values(
    tenant_id: UUID,
    *,
    ssp_book_id: UUID,
    status: ConfigStatus = ConfigStatus.DRAFT,
    version_no: int = 1,
    **extra: Any,
) -> dict[str, Any]:
    """T-REF-29: a version effective 2026-01-01; outside DRAFT it carries a hash (DB-04)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "ssp_book_id": ssp_book_id,
        "effective_from_date": date(2026, 1, 1),
        "methodology_label": "Probe methodology",
        **_SYSTEM,
        "version_no": version_no,
        "status": status.value,
        "content_sha256": None if status is ConfigStatus.DRAFT else secrets.token_hex(32),
        **extra,
    }


def ssp_entry_values(
    tenant_id: UUID, *, ssp_book_version_id: UUID, product_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-REF-30: an observable USD entry without dimension keys."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "ssp_book_version_id": ssp_book_version_id,
        "product_id": product_id,
        "currency": "USD",
        "method": "observable",
        "distinctness": "distinct",
        "created_by_kind": PrincipalKind.SYSTEM.value,
        **extra,
    }


def ssp_range_values(tenant_id: UUID, *, ssp_entry_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-REF-31: a ``NONE`` band with a point value."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "ssp_entry_id": ssp_entry_id,
        "point_value": Decimal("100"),
        "created_by_kind": PrincipalKind.SYSTEM.value,
        **extra,
    }


def ssp_book_version_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-29: a DRAFT version of a book the builder inserts where the context allows it."""
    book_id = _insert_visible(session, ssp_book, ssp_book_values(ctx.tenant_id))
    return ssp_book_version_values(ctx.tenant_id, ssp_book_id=book_id)


def ssp_entry_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-30: an entry of a DRAFT version, which DB-04 lets change, for a probe product."""
    version_id = _insert_visible(session, ssp_book_version, ssp_book_version_row(ctx, session))
    product_id = _insert_visible(session, product, product_values(ctx.tenant_id))
    return ssp_entry_values(ctx.tenant_id, ssp_book_version_id=version_id, product_id=product_id)


def ssp_range_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-31: a band of an entry of a DRAFT version."""
    entry_id = _insert_visible(session, ssp_entry, ssp_entry_row(ctx, session))
    return ssp_range_values(ctx.tenant_id, ssp_entry_id=entry_id)


def ssp_calculator_run_values(tenant_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-REF-32: a QUEUED run over committed contract lines, which needs no pool file."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "name": "Probe calculator run",
        "parameters": {
            "source": "committed_obligations",
            "product_ids": [],
            "dimensions": {},
            "date_from": "2026-01-01",
            "date_to": "2026-08-31",
            "band_ratio": "0.15",
            "currency": "USD",
            "ssp_book_id": str(new_id()),
            "pool_file_id": None,
        },
        **_CREATED,
        **extra,
    }


def ssp_calculator_result_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-33: the statistics of one probe product of a run the builder inserts where the context
    allows it."""
    run_id = _insert_visible(session, ssp_calculator_run, ssp_calculator_run_values(ctx.tenant_id))
    product_id = _insert_visible(session, product, product_values(ctx.tenant_id))
    prices = {
        name: Decimal("100")
        for name in (
            "median_unit_price",
            "mean_unit_price",
            "p10_unit_price",
            "p25_unit_price",
            "p75_unit_price",
            "p90_unit_price",
            "proposed_mid",
        )
    }
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "ssp_calculator_run_id": run_id,
        "product_id": product_id,
        "currency": "USD",
        "observation_count": 1,
        "excluded_count": 0,
        **prices,
        "band_ratio": Decimal("0.15"),
        "compliance_ratio": Decimal("1"),
        "inside_count": 1,
        "proposed_low": Decimal("85"),
        "proposed_high": Decimal("115"),
        "histogram": [{"from": "100", "to": "100", "count": 1}],
    }


def ssp_calculator_exclusion_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-34: an excluded pool observation of a run the builder inserts where the context allows
    it."""
    run_id = _insert_visible(session, ssp_calculator_run, ssp_calculator_run_values(ctx.tenant_id))
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "ssp_calculator_run_id": run_id,
        "source_ref_type": "source_order_line",
        "source_ref_id": new_id(),
        "reason": "Probe exclusion reason",
        **_CREATED,
    }


def account_mapping_rule_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-REF-15: a rule of a DRAFT version, which DB-04 lets change, mapping a probe account."""
    version_id = _insert_visible(
        session, account_mapping_version, account_mapping_version_values(ctx.tenant_id)
    )
    account_id = _insert_visible(session, gl_account, gl_account_values(ctx.tenant_id))
    return account_mapping_rule_values(
        ctx.tenant_id, account_mapping_version_id=version_id, gl_account_id=account_id
    )


def combination_group_values(
    tenant_id: UUID, *, code: str | None = None, **extra: Any
) -> dict[str, Any]:
    """T-CON-03: an APPLIED singleton group in USD."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": code or f"CG-{secrets.token_hex(4).upper()}",
        "is_singleton": True,
        "status": "APPLIED",
        "transaction_currency": "USD",
        "inception_date": date(2026, 1, 1),
        **_SYSTEM,
        **extra,
    }


def contract_values(
    tenant_id: UUID,
    *,
    customer_id: UUID,
    contracting_entity_id: UUID,
    combination_group_id: UUID,
    head_stream_version: int = 0,
    **extra: Any,
) -> dict[str, Any]:
    """T-CON-01: a DRAFT USD contract with the given head (an INSERT is not guarded by DB-18)."""
    token = secrets.token_hex(4).upper()
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "contract_no": f"CON-{token}",
        "external_id": f"EXT-{token}",
        "customer_id": customer_id,
        "contracting_entity_id": contracting_entity_id,
        "transaction_currency": "USD",
        "inception_date": date(2026, 1, 1),
        "combination_group_id": combination_group_id,
        "head_stream_version": head_stream_version,
        "source_system": SourceSystem.API.value,
        **_SYSTEM,
        **extra,
    }


PROBE_EVENT_PAYLOAD: Final = MappingProxyType({"description": "Probe change"})


def contract_event_values(
    tenant_id: UUID,
    *,
    contract_id: UUID,
    contracting_entity_id: UUID,
    stream_version: int,
    **extra: Any,
) -> dict[str, Any]:
    """T-CON-05: a ``SIGNIFICANT_CHANGE_FLAGGED`` event; DB-08 sets ``recorded_at`` and
    ``record_seq``."""
    payload = dict(PROBE_EVENT_PAYLOAD)
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "contract_id": contract_id,
        "contracting_entity_id": contracting_entity_id,
        "stream_version": stream_version,
        "event_type": "SIGNIFICANT_CHANGE_FLAGGED",
        "effective_date": date(2026, 1, 1),
        "origin": "SYSTEM",
        "payload": payload,
        "payload_sha256": sha256_hex(payload),
        "request_id": "tests-rows",
        **_CREATED,
        **extra,
    }


def combination_group_member_values(
    tenant_id: UUID,
    *,
    combination_group_id: UUID,
    contract_id: UUID,
    join_event_id: UUID,
    **extra: Any,
) -> dict[str, Any]:
    """T-CON-04: a current membership."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "combination_group_id": combination_group_id,
        "contract_id": contract_id,
        "valid_from_known_at": ASSIGNED_FROM,
        "join_event_id": join_event_id,
        **_CREATED,
        **extra,
    }


def obligation_values(
    tenant_id: UUID,
    *,
    contract_id: UUID,
    product_id: UUID,
    created_by_event_id: UUID,
    obligation_key: str = "O1",
    **extra: Any,
) -> dict[str, Any]:
    """T-CON-10: the first line of a contract."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "contract_id": contract_id,
        "obligation_key": obligation_key,
        "product_id": product_id,
        "legacy_record_key": f"EXT {obligation_key} PROD",
        "created_by_event_id": created_by_event_id,
        "line_sequence": 1,
        **_CREATED,
        **extra,
    }


def event_submission_values(
    tenant_id: UUID, *, contract_id: UUID, contracting_entity_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-CON-24: a DRAFT submission of one manual delivery."""
    delivery = {"obligation_key": "O1", "quantity": "1", "trigger": "DELIVERY"}
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "contract_id": contract_id,
        "contracting_entity_id": contracting_entity_id,
        "events": [
            {
                "event_type": "DELIVERY_RECORDED",
                "effective_date": "2026-02-01",
                "obligation_key": "O1",
                "payload": delivery,
            }
        ],
        **_SYSTEM,
        **extra,
    }


@dataclass(frozen=True, slots=True)
class ContractRows:
    """The ids of a contract chain inserted by ``insert_contract_rows``."""

    entity_id: UUID
    customer_id: UUID
    group_id: UUID
    contract_id: UUID


def insert_contract_rows(
    session: Session,
    tenant_id: UUID,
    *,
    head_stream_version: int = 0,
    entity_id: UUID | None = None,
) -> ContractRows:
    """A calendar, an entity, a customer, a singleton group and a contract, each inserted where the
    session's context allows it (a refused insert leaves a fresh id, as ``_insert_visible``)."""
    calendar_id = _insert_visible(session, fiscal_calendar, fiscal_calendar_values(tenant_id))
    entity = legal_entity_values(tenant_id, calendar_id=calendar_id, entity_id=entity_id)
    entity_row_id = _insert_visible(session, legal_entity, entity)
    customer_id = _insert_visible(session, customer, customer_values(tenant_id))
    group_id = _insert_visible(session, combination_group, combination_group_values(tenant_id))
    row = contract_values(
        tenant_id,
        customer_id=customer_id,
        contracting_entity_id=entity_row_id,
        combination_group_id=group_id,
        head_stream_version=head_stream_version,
    )
    contract_id = _insert_visible(session, contract, row)
    return ContractRows(
        entity_id=entity_row_id, customer_id=customer_id, group_id=group_id, contract_id=contract_id
    )


def modification_values(
    tenant_id: UUID, *, contract_id: UUID, contracting_entity_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-CON-06 (CTR-17): a DRAFT USD modification of the contract with no lines yet."""
    token = secrets.token_hex(4).upper()
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "modification_no": f"MOD-{token}",
        "contract_id": contract_id,
        "contracting_entity_id": contracting_entity_id,
        "effective_date": date(2026, 9, 16),
        "kind": "UPGRADE",
        "status": "DRAFT",
        "lines": [],
        "currency": "USD",
        **_SYSTEM,
        **extra,
    }


def modification_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-06: a modification of a probe contract chain (CTR-17; RLS-TE on the entity)."""
    chain = insert_contract_rows(session, ctx.tenant_id)
    return modification_values(
        ctx.tenant_id, contract_id=chain.contract_id, contracting_entity_id=chain.entity_id
    )


def contract_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-01: a contract of a probe entity, customer and group."""
    calendar_id = _insert_visible(session, fiscal_calendar, fiscal_calendar_values(ctx.tenant_id))
    entity_id = _insert_visible(
        session, legal_entity, legal_entity_values(ctx.tenant_id, calendar_id=calendar_id)
    )
    customer_id = _insert_visible(session, customer, customer_values(ctx.tenant_id))
    group_id = _insert_visible(session, combination_group, combination_group_values(ctx.tenant_id))
    return contract_values(
        ctx.tenant_id,
        customer_id=customer_id,
        contracting_entity_id=entity_id,
        combination_group_id=group_id,
    )


def _event_chain(ctx: RowContext, session: Session) -> tuple[ContractRows, UUID]:
    """A contract at head 1 and its first event."""
    rows = insert_contract_rows(session, ctx.tenant_id, head_stream_version=1)
    event = contract_event_values(
        ctx.tenant_id,
        contract_id=rows.contract_id,
        contracting_entity_id=rows.entity_id,
        stream_version=1,
    )
    return rows, _insert_visible(session, contract_event, event)


def contract_event_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-05: the first event of a contract at head 1."""
    rows = insert_contract_rows(session, ctx.tenant_id, head_stream_version=1)
    return contract_event_values(
        ctx.tenant_id,
        contract_id=rows.contract_id,
        contracting_entity_id=rows.entity_id,
        stream_version=1,
    )


def combination_group_member_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-04: the membership of a contract joined by its first event."""
    rows, event_id = _event_chain(ctx, session)
    return combination_group_member_values(
        ctx.tenant_id,
        combination_group_id=rows.group_id,
        contract_id=rows.contract_id,
        join_event_id=event_id,
    )


def obligation_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-10: an obligation created by a contract's first event."""
    rows, event_id = _event_chain(ctx, session)
    product_id = _insert_visible(session, product, product_values(ctx.tenant_id))
    return obligation_values(
        ctx.tenant_id,
        contract_id=rows.contract_id,
        product_id=product_id,
        created_by_event_id=event_id,
    )


def event_submission_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-24: a DRAFT submission of a probe contract."""
    rows = insert_contract_rows(session, ctx.tenant_id)
    return event_submission_values(
        ctx.tenant_id, contract_id=rows.contract_id, contracting_entity_id=rows.entity_id
    )


def judgement_record_values(tenant_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-CON-19: a DRAFT ``COLLECTIBILITY`` record on a contract id (soft subject reference)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "judgement_no": f"JDG-P{secrets.token_hex(5)}",
        "topic": "COLLECTIBILITY",
        "subject_type": "contract",
        "subject_id": new_id(),
        "conclusion": "Collection of the consideration is probable.",
        "rationale": "Probe judgement record.",
        **_SYSTEM,
        **extra,
    }


def judgement_record_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return judgement_record_values(ctx.tenant_id)


def contract_hold_values(
    tenant_id: UUID, *, contract_id: UUID, applied_event_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-CON-20: an open MANUAL recognition hold whose id is its HOLD_APPLIED event (L4-1-Q-22)."""
    return {
        "tenant_id": tenant_id,
        "id": applied_event_id,
        "contract_id": contract_id,
        "hold_type": "recognition",
        "hold_source": "MANUAL",
        "reason": "Probe recognition hold.",
        "applied_event_id": applied_event_id,
        "applied_at": INVITED_AT,
        **extra,
    }


def contract_hold_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    rows, event_id = _event_chain(ctx, session)
    return contract_hold_values(
        ctx.tenant_id, contract_id=rows.contract_id, applied_event_id=event_id
    )


def exception_item_values(tenant_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-IMP-05: an OPEN, tenant-wide ``ENGINE`` item (``entity_id`` null; BS3-D-02)."""
    item_id = new_id()
    return {
        "tenant_id": tenant_id,
        "id": item_id,
        "exception_no": f"EXC-P{secrets.token_hex(5)}",
        "source": "ENGINE",
        "code": "ENGINE_INVARIANT_VIOLATION",
        "severity": "BLOCKING",
        "title": "Calculation quarantined",
        "message": "Probe exception item.",
        "dedupe_key": f"ENGINE:ENGINE_INVARIANT_VIOLATION:{item_id}",
        **_SYSTEM,
        **extra,
    }


def exception_item_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return exception_item_values(ctx.tenant_id)


# --- import uploads, rows and lineage (BUILD_SPEC DIN-1) ------------------------------------


def _inserted_id(session: Session, table: Table, values: Mapping[str, Any]) -> UUID:
    """Insert a chained row where the session's context allows it, else a fresh id that row-level
    security refuses first (as ``file_attachment_row``)."""
    savepoint = session.begin_nested()
    try:
        session.execute(insert(table).values(**values))
    except exc.DBAPIError:
        savepoint.rollback()
        return new_id()
    savepoint.commit()
    return UUID(str(values["id"]))


def import_upload_values(tenant_id: UUID, *, file_object_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-IMP-02: an UPLOADED ``legacy_sku_ssp`` upload of a stored file."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "import_no": f"IMP-P{secrets.token_hex(5)}",
        "template_code": "legacy_sku_ssp",
        "template_version": 1,
        "file_object_id": file_object_id,
        "file_sha256": secrets.token_hex(32),
        **_SYSTEM,
        **extra,
    }


def import_upload_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    file_row = file_object_values(ctx.tenant_id, purpose=FilePurpose.IMPORT_SOURCE)
    file_id = _inserted_id(session, file_object, file_row)
    return import_upload_values(ctx.tenant_id, file_object_id=file_id)


def import_row_values(tenant_id: UUID, *, import_upload_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-IMP-03: one VALID row numbered from Excel row 2."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "import_upload_id": import_upload_id,
        "sheet_name": "SKU Setup",
        "row_number": 2,
        "raw": {"SKU Name": "Hardware 1"},
        "normalized": {"SKU Name": "Hardware 1"},
        "row_sha256": secrets.token_hex(32),
        "status": "VALID",
        **_CREATED,
        **extra,
    }


def import_row_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    upload = import_upload_row(ctx, session)
    upload_id = _inserted_id(session, import_upload, upload)
    return import_row_values(ctx.tenant_id, import_upload_id=upload_id)


def import_row_lineage_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-IMP-04: the row's lineage to a soft-referenced product id."""
    upload = import_upload_row(ctx, session)
    upload_id = _inserted_id(session, import_upload, upload)
    row_id = _inserted_id(
        session, import_row, import_row_values(ctx.tenant_id, import_upload_id=upload_id)
    )
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "import_row_id": row_id,
        "import_upload_id": upload_id,
        "target_type": "product",
        "target_id": new_id(),
        **_CREATED,
    }


def import_mapping_profile_values(tenant_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-IMP-06: a DRAFT version of a ``contracts`` mapping profile (BUILD_SPEC DIN-10)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": f"MAP-P{secrets.token_hex(4).upper()}",
        "name": "Mapping profile",
        "template_code": "contracts",
        "mappings": {
            "aliases": {"Order Ref": "external_id"},
            "constants": {},
            "custom_attributes": [],
        },
        **_SYSTEM,
        "version_no": 1,
        "status": ConfigStatus.DRAFT.value,
        **extra,
    }


def import_mapping_profile_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    return import_mapping_profile_values(ctx.tenant_id)


def source_record_values(tenant_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-SRC-01: version 1 of an API order."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "source_system": "API",
        "object_type": "ORDER",
        "external_id": f"SO-P{secrets.token_hex(5)}",
        "external_version": "1",
        "version_order": 1,
        "payload": {"order_number": "SO-1"},
        "payload_sha256": secrets.token_hex(32),
        **_CREATED,
        **extra,
    }


def _source_record_id(ctx: RowContext, session: Session) -> UUID:
    return _inserted_id(session, source_record, source_record_values(ctx.tenant_id))


def source_order_values(tenant_id: UUID, *, source_record_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-SRC-02: the order header of a source record."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "source_record_id": source_record_id,
        "source_system": "API",
        "external_order_id": f"SO-P{secrets.token_hex(5)}",
        "external_version": "1",
        "order_number": "SO-1",
        "order_date": date(2026, 1, 1),
        "customer_external_id": "C-01",
        "transaction_currency": "USD",
        "grouping_values": {},
        **_CREATED,
        **extra,
    }


def source_order_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    return source_order_values(ctx.tenant_id, source_record_id=_source_record_id(ctx, session))


def source_order_line_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SRC-03: line O1 of an order."""
    order = source_order_values(ctx.tenant_id, source_record_id=_source_record_id(ctx, session))
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "source_order_id": _inserted_id(session, source_order, order),
        "line_external_id": "O1",
        "line_no": 1,
        "product_code": "AVM-PLAT-ENT",
        "quantity": Decimal("1"),
        "total_price": Decimal("120000.00"),
        **_CREATED,
    }


def source_invoice_values(
    tenant_id: UUID, *, source_record_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-SRC-04: an invoice header of a source record."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "source_record_id": source_record_id,
        "source_system": "API",
        "external_invoice_id": f"INV-P{secrets.token_hex(5)}",
        "external_version": "1",
        "invoice_number": "INV-1",
        "document_kind": "INVOICE",
        "issue_date": date(2026, 1, 31),
        "legal_entity_code": "AVM-US",
        "currency": "USD",
        "total_amount": Decimal("10000.00"),
        **_CREATED,
        **extra,
    }


def source_invoice_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    return source_invoice_values(ctx.tenant_id, source_record_id=_source_record_id(ctx, session))


def source_invoice_line_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SRC-05: line 1 of an invoice."""
    invoice = source_invoice_values(ctx.tenant_id, source_record_id=_source_record_id(ctx, session))
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "source_invoice_id": _inserted_id(session, source_invoice, invoice),
        "line_external_id": "1",
        "amount": Decimal("10000.00"),
        **_CREATED,
    }


def source_usage_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SRC-06: one usage record."""
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "source_record_id": _source_record_id(ctx, session),
        "source_system": "API",
        "external_usage_id": f"U-P{secrets.token_hex(5)}",
        "external_version": "1",
        "usage_date": date(2026, 1, 31),
        "metric": "API_CALLS",
        "quantity": Decimal("1000"),
        **_CREATED,
    }


def source_payment_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SRC-07: one cash receipt."""
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "source_record_id": _source_record_id(ctx, session),
        "source_system": "API",
        "external_payment_id": f"PAY-P{secrets.token_hex(5)}",
        "external_version": "1",
        "receipt_date": date(2026, 2, 15),
        "legal_entity_code": "AVM-US",
        "currency": "USD",
        "amount": Decimal("10000.00"),
        **_CREATED,
    }


def source_match_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SRC-08: a manual match to a soft-referenced customer id."""
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "source_record_id": _source_record_id(ctx, session),
        "target_type": "customer",
        "target_id": new_id(),
        "match_method": "MANUAL",
        **_CREATED,
    }


def contract_source_link_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-02: the booking link of a contract's first event to a source record (DIN-4)."""
    rows, event_id = _event_chain(ctx, session)
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "contract_id": rows.contract_id,
        "source_record_id": _source_record_id(ctx, session),
        "link_role": "BOOKING",
        "contract_event_id": event_id,
        **_CREATED,
    }


def policy_override_values(tenant_id: UUID, *, contract_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-CON-23: a DRAFT contract-level override of POL-051 ``returns.model`` (CTR-15)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "contract_id": contract_id,
        "level": "CONTRACT",
        "policy_key": "returns.model",
        "value": "EXPECTED_RETURNS",
        "rationale": "Returns are expected under this probe contract.",
        **_SYSTEM,
        **extra,
    }


def policy_override_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-23: a DRAFT override of a probe contract."""
    rows = insert_contract_rows(session, ctx.tenant_id)
    return policy_override_values(ctx.tenant_id, contract_id=rows.contract_id)


def insert_policy_override(
    session: Session,
    tenant_id: UUID,
    *,
    contract_id: UUID,
    obligation_key: str | None = None,
    created_by: UUID | None = None,
    **extra: Any,
) -> UUID:
    """T-CON-23: the DRAFT override a test of the kept code stands on (04 T-CON-23 "Not offered in
    release 1.0", rev 1.322; item POLICY-OVERRIDE-WITHDRAW-1). The product creates no policy
    override in release 1.0 — ``POST /policy-overrides`` refuses every creation — so what follows a
    creation (the submit, the approval, the resolution, the mark of the group, the trail, the
    reads) is exercised on this row, through the product's own submit and approval.
    ``obligation_key`` makes it an OBLIGATION-level row of that obligation; ``created_by`` writes
    it as that person's, as the creation did; ``extra`` states ``policy_key``, ``value`` and
    ``rationale`` where the defaults of ``policy_override_values`` do not serve."""
    values = policy_override_values(tenant_id, contract_id=contract_id, **extra)
    if obligation_key is not None:
        values["level"] = "OBLIGATION"
        values["obligation_id"] = session.execute(
            select(obligation.c.id).where(
                obligation.c.contract_id == contract_id,
                obligation.c.obligation_key == obligation_key,
            )
        ).scalar_one()
    if created_by is not None:
        person = PrincipalKind.USER.value
        values.update(
            created_by=created_by,
            created_by_kind=person,
            updated_by=created_by,
            updated_by_kind=person,
        )
    session.execute(insert(policy_override).values(**values))
    return UUID(str(values["id"]))


def estimate_values(tenant_id: UUID, *, contract_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-CON-12: a variable consideration bonus element of a probe contract (CTR-12)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "contract_id": contract_id,
        "estimate_kind": "VARIABLE_CONSIDERATION",
        "element_code": f"VC-P{secrets.token_hex(4)}",
        "vc_element_type": "BONUS",
        "method": "MOST_LIKELY_AMOUNT",
        **_CREATED,
        **extra,
    }


def estimate_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-12: an element of a probe contract."""
    rows = insert_contract_rows(session, ctx.tenant_id)
    return estimate_values(ctx.tenant_id, contract_id=rows.contract_id)


def estimate_version_values(tenant_id: UUID, *, estimate_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-CON-13: a DRAFT version 1 of an element (CTR-12)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "estimate_id": estimate_id,
        "version_no": 1,
        "effective_date": date(2026, 1, 1),
        "rationale": "Probe estimate version.",
        **_SYSTEM,
        **extra,
    }


def estimate_version_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-13: a DRAFT version of a probe element."""
    rows = insert_contract_rows(session, ctx.tenant_id)
    element_id = _inserted_id(
        session, estimate, estimate_values(ctx.tenant_id, contract_id=rows.contract_id)
    )
    return estimate_version_values(ctx.tenant_id, estimate_id=element_id)


# --- computed versions, schedules and traces (BUILD_SPEC CTR-2) ----------------------------------

PROBE_ENGINE_VERSION: Final = "0.1.0"


def engine_release_values(**extra: Any) -> dict[str, Any]:
    """T-PLT-38: a probe release (erev_app holds INSERT on the global table, 04 §14.2).

    REL-03 compliant (D-96 (3); team-lead ruling D-98 candidate 94, 2026-09-20): the version is the
    running ``ENGINE_VERSION`` — a plain MAJOR.MINOR.PATCH — and the probe identity lives in
    ``build_sha`` (``probe-<token>``) and the ``schema_revision`` marker ``"probe"``, never in the
    version string. A probe row is often the latest ``engine_release`` when a world factory stamps
    next in a shared test database: sharing the engine version makes that stamp a recorded
    SAME_VERSION_REBUILD (or a RESTART), whereas a lower plain version such as ``0.0.0`` would put
    the factories' undeclared PATCH below the semver floor and be refused
    (``tests/unit/test_probe_release_support.py``)."""
    token = secrets.token_hex(6)
    return {
        "id": new_id(),
        "engine_version": ENGINE_VERSION,
        "build_sha": f"probe-{token}",
        "schema_revision": "probe",
        "validation_level": "PATCH",
        **extra,
    }


def contract_computation_values(
    tenant_id: UUID, *, combination_group_id: UUID, engine_release_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-CON-07: a SUCCEEDED computation of a group."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "combination_group_id": combination_group_id,
        "stream_heads": {},
        "known_at": INVITED_AT,
        "trigger": "COMMAND",
        "engine_release_id": engine_release_id,
        "engine_version": PROBE_ENGINE_VERSION,
        "input_sha256": secrets.token_hex(32),
        "pinned_refs": {},
        "status": "SUCCEEDED",
        "problem": None,
        "duration_ms": 0,
        **_CREATED,
        **extra,
    }


def calc_trace_values(
    tenant_id: UUID, *, contract_version_id: UUID, combination_group_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-ENG-03: an empty ASC606 trace; its key to the version is checked at commit."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "contract_version_id": contract_version_id,
        "combination_group_id": combination_group_id,
        "book_code": BookCode.ASC606.value,
        "format_version": 1,
        "engine_version": PROBE_ENGINE_VERSION,
        "trace_sha256": secrets.token_hex(32),
        "node_count": 0,
        "root_measures": {},
        "trace": {"nodes": []},
        **_CREATED,
        **extra,
    }


def contract_version_values(
    tenant_id: UUID,
    *,
    combination_group_id: UUID,
    contract_computation_id: UUID,
    calc_trace_id: UUID,
    transaction_price: Decimal = Decimal(0),
    **extra: Any,
) -> dict[str, Any]:
    """T-CON-08: version 1 in ASC606 whose price is awaiting trigger; DB-17 checks at commit that
    its obligation versions allocate ``transaction_price``."""
    zero = Decimal(0)
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "combination_group_id": combination_group_id,
        "contract_computation_id": contract_computation_id,
        "book_code": BookCode.ASC606.value,
        "version_no": 1,
        "known_at": INVITED_AT,
        "cause_event_ids": [],
        "output_sha256": secrets.token_hex(32),
        "calc_trace_id": calc_trace_id,
        "transaction_currency": "USD",
        "status_in_book": "DRAFT",
        "transaction_price": transaction_price,
        "fixed_consideration": transaction_price,
        "total_ssp": transaction_price,
        "revenue_cum": zero,
        "billed_cum": zero,
        "net_position": zero,
        "rpo_amount": transaction_price,
        "scheduled_amount": zero,
        "awaiting_trigger_amount": transaction_price,
        "pinned_policies": {},
        **_CREATED,
        **extra,
    }


def obligation_version_values(
    tenant_id: UUID,
    *,
    contract_version_id: UUID,
    obligation_id: UUID,
    contract_id: UUID,
    combination_group_id: UUID,
    product_id: UUID,
    pob_template_version_id: UUID,
    entity_id: UUID,
    allocated_amount: Decimal = Decimal("100"),
    **extra: Any,
) -> dict[str, Any]:
    """T-CON-11: an unsatisfied point-in-time obligation whose allocation awaits its trigger."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "contract_version_id": contract_version_id,
        "obligation_id": obligation_id,
        "contract_id": contract_id,
        "combination_group_id": combination_group_id,
        "book_code": BookCode.ASC606.value,
        "version_no": 1,
        "obligation_key": "O1",
        "legacy_record_key": "EXT O1 PROD",
        "product_id": product_id,
        "product_code": "PROD",
        "obligation_kind": "STANDARD",
        "distinctness": "distinct",
        "pob_template_version_id": pob_template_version_id,
        "satisfaction_pattern": "POINT_IN_TIME",
        "over_time_criterion": "NOT_APPLICABLE",
        "recognition_method": "POINT_IN_TIME",
        "principal_agent": "PRINCIPAL",
        "licence_nature": "NOT_APPLICABLE",
        "warranty_type": "NONE",
        "contracting_entity_id": entity_id,
        "performing_entity_id": entity_id,
        "txn_currency": "USD",
        "original_quantity": Decimal(1),
        "original_stated_price": allocated_amount,
        "quantity": Decimal(1),
        "stated_price": allocated_amount,
        "original_ssp_selected": allocated_amount,
        "original_total_contract_price": allocated_amount,
        "original_total_contract_ssp": allocated_amount,
        "original_allocated_amount": allocated_amount,
        "original_allocated_exact": allocated_amount,
        "allocation_weight": Decimal(1),
        "allocated_amount": allocated_amount,
        "allocated_exact": allocated_amount,
        "allocation_adjustment": Decimal(0),
        "remaining_quantity": Decimal(1),
        "remaining_ssp": allocated_amount,
        "remaining_allocation": allocated_amount,
        "remaining_billing": allocated_amount,
        "awaiting_trigger_amount": allocated_amount,
        "position_obligation": Decimal(0),
        "position_contract_entity": Decimal(0),
        "satisfaction_status": "UNSATISFIED",
        "effective_date": date(2026, 1, 1),
        **_CREATED,
        **extra,
    }


def contract_version_balance_values(
    tenant_id: UUID, *, contract_version_id: UUID, contract_id: UUID, entity_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-CON-09: zero balances of a member contract and entity."""
    zero = Decimal(0)
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "contract_version_id": contract_version_id,
        "contract_id": contract_id,
        "entity_id": entity_id,
        "book_code": BookCode.ASC606.value,
        "txn_currency": "USD",
        "functional_currency": "USD",
        "revenue_cum_txn": zero,
        "billed_cum_txn": zero,
        "net_position_txn": zero,
        **_CREATED,
        **extra,
    }


def schedule_values(
    tenant_id: UUID, *, contract_version_id: UUID, combination_group_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-ENG-01: an empty revenue schedule."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "contract_version_id": contract_version_id,
        "combination_group_id": combination_group_id,
        "book_code": BookCode.ASC606.value,
        "schedule_kind": "REVENUE",
        "currency": "USD",
        "line_count": 0,
        "total_amount": Decimal(0),
        **_CREATED,
        **extra,
    }


def schedule_line_values(
    tenant_id: UUID,
    *,
    schedule_id: UUID,
    contract_version_id: UUID,
    contract_id: UUID,
    entity_id: UUID,
    period_id: UUID,
    **extra: Any,
) -> dict[str, Any]:
    """T-ENG-02: a January 2026 revenue line of the contract."""
    return {
        "tenant_id": tenant_id,
        "period_end_date": date(2026, 1, 31),
        "id": new_id(),
        "schedule_id": schedule_id,
        "contract_version_id": contract_version_id,
        "contract_id": contract_id,
        "book_code": BookCode.ASC606.value,
        "subject_type": "contract",
        "subject_id": contract_id,
        "entity_id": entity_id,
        "period_id": period_id,
        "line_type": "NORMAL",
        "amount": Decimal("10.00"),
        "cumulative_amount": Decimal("10.00"),
        "cumulative_exact": Decimal(10),
        "currency": "USD",
        "is_released_at_close": True,
        "trace_node_id": "revenue:EXT:FY2026-P01",
        **extra,
    }


@dataclass(frozen=True, slots=True)
class VersionRows:
    """The ids of a computed version inserted by ``insert_version_rows``."""

    chain: ContractRows
    computation_id: UUID
    version_id: UUID
    trace_id: UUID


def _computation(session: Session, tenant_id: UUID, chain: ContractRows) -> UUID:
    release_id = _insert_visible(session, engine_release, engine_release_values())
    values = contract_computation_values(
        tenant_id, combination_group_id=chain.group_id, engine_release_id=release_id
    )
    return _insert_visible(session, contract_computation, values)


def insert_version_rows(
    session: Session,
    tenant_id: UUID,
    *,
    transaction_price: Decimal = Decimal(0),
    entity_id: UUID | None = None,
    **version_columns: Any,
) -> VersionRows:
    """A contract chain, a computation, a calc trace and version 1 of the chain's group; the trace
    and the version name each other, and both keys are checked at commit. ``version_columns``
    override T-CON-08 values."""
    chain = insert_contract_rows(session, tenant_id, head_stream_version=1, entity_id=entity_id)
    computation_id = _computation(session, tenant_id, chain)
    version_id, trace_id = new_id(), new_id()
    trace = calc_trace_values(
        tenant_id, contract_version_id=version_id, combination_group_id=chain.group_id, id=trace_id
    )
    _insert_visible(session, calc_trace, trace)
    version = contract_version_values(
        tenant_id,
        combination_group_id=chain.group_id,
        contract_computation_id=computation_id,
        calc_trace_id=trace_id,
        transaction_price=transaction_price,
        id=version_id,
        **version_columns,
    )
    _insert_visible(session, contract_version, version)
    return VersionRows(
        chain=chain, computation_id=computation_id, version_id=version_id, trace_id=trace_id
    )


def insert_obligation_rows(
    session: Session, tenant_id: UUID, rows: VersionRows, *, obligation_key: str = "O1"
) -> dict[str, UUID]:
    """An obligation of the chain's contract with its product, template version and first event."""
    chain = rows.chain
    event = contract_event_values(
        tenant_id,
        contract_id=chain.contract_id,
        contracting_entity_id=chain.entity_id,
        stream_version=1,
    )
    event_id = _visible_id(
        session,
        select(contract_event.c.id).where(
            contract_event.c.contract_id == chain.contract_id, contract_event.c.stream_version == 1
        ),
    )
    if not session.execute(
        select(func.count()).select_from(contract_event).where(contract_event.c.id == event_id)
    ).scalar_one():
        event_id = _insert_visible(session, contract_event, event)
    product_id = _insert_visible(session, product, product_values(tenant_id))
    template_id = _insert_visible(session, pob_template, pob_template_values(tenant_id))
    template_version_id = _insert_visible(
        session,
        pob_template_version,
        pob_template_version_values(tenant_id, pob_template_id=template_id),
    )
    obligation_id = _insert_visible(
        session,
        obligation,
        obligation_values(
            tenant_id,
            contract_id=chain.contract_id,
            product_id=product_id,
            created_by_event_id=event_id,
            obligation_key=obligation_key,
        ),
    )
    return {
        "obligation_id": obligation_id,
        "product_id": product_id,
        "pob_template_version_id": template_version_id,
    }


def contract_computation_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-07: a computation of a probe group."""
    chain = insert_contract_rows(session, ctx.tenant_id)
    release_id = _insert_visible(session, engine_release, engine_release_values())
    return contract_computation_values(
        ctx.tenant_id, combination_group_id=chain.group_id, engine_release_id=release_id
    )


def contract_version_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-08: version 1 of a probe group at price 0, named by a trace the builder inserts."""
    chain = insert_contract_rows(session, ctx.tenant_id)
    computation_id = _computation(session, ctx.tenant_id, chain)
    version_id = new_id()
    trace = calc_trace_values(
        ctx.tenant_id, contract_version_id=version_id, combination_group_id=chain.group_id
    )
    trace_id = _insert_visible(session, calc_trace, trace)
    return contract_version_values(
        ctx.tenant_id,
        combination_group_id=chain.group_id,
        contract_computation_id=computation_id,
        calc_trace_id=trace_id,
        id=version_id,
    )


def calc_trace_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-ENG-03: the trace of a version the builder inserts naming it (both keys at commit)."""
    chain = insert_contract_rows(session, ctx.tenant_id)
    computation_id = _computation(session, ctx.tenant_id, chain)
    trace_id = new_id()
    version = contract_version_values(
        ctx.tenant_id,
        combination_group_id=chain.group_id,
        contract_computation_id=computation_id,
        calc_trace_id=trace_id,
    )
    version_id = _insert_visible(session, contract_version, version)
    return calc_trace_values(
        ctx.tenant_id,
        contract_version_id=version_id,
        combination_group_id=chain.group_id,
        id=trace_id,
    )


def obligation_version_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-11: the one obligation version of a version at price 100."""
    rows = insert_version_rows(session, ctx.tenant_id, transaction_price=Decimal("100"))
    parts = insert_obligation_rows(session, ctx.tenant_id, rows)
    return obligation_version_values(
        ctx.tenant_id,
        contract_version_id=rows.version_id,
        contract_id=rows.chain.contract_id,
        combination_group_id=rows.chain.group_id,
        entity_id=rows.chain.entity_id,
        **parts,
    )


def contract_version_balance_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-09: the balances of a version's contract and entity."""
    rows = insert_version_rows(session, ctx.tenant_id)
    return contract_version_balance_values(
        ctx.tenant_id,
        contract_version_id=rows.version_id,
        contract_id=rows.chain.contract_id,
        entity_id=rows.chain.entity_id,
    )


def loss_provision_version_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    rows = insert_version_rows(session, ctx.tenant_id)
    period_id = _insert_visible(session, period, period_row(ctx, session))
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "contract_version_id": rows.version_id,
        "contract_id": rows.chain.contract_id,
        "entity_id": rows.chain.entity_id,
        "book_code": "ASC606",
        "unit": "CONTRACT",
        "unit_key": "probe",
        "obligation_id": None,
        "period_id": period_id,
        "period_key": "FY2026-P01",
        "as_of": date(2026, 1, 31),
        "measurement_basis": "ASC_605_35",
        "currency": "USD",
        "in_scope": False,
        "trace_nodes": {},
        **dict.fromkeys(
            (
                "expected_consideration",
                "expected_total_costs",
                "costs_to_date",
                "revenue_to_date",
                "expected_margin",
                "provision_balance",
                "provision_movement",
            ),
            Decimal(0),
        ),
        **_CREATED,
    }


def loss_provision_eac_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    from erev_api.db.tables import estimate_version, loss_provision_version

    parent = loss_provision_version_row(ctx, session)
    _insert_visible(session, loss_provision_version, parent)
    eac_id = _insert_visible(session, estimate_version, estimate_version_row(ctx, session))
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "loss_provision_version_id": parent["id"],
        "estimate_version_id": eac_id,
        "entity_id": parent["entity_id"],
        **_CREATED,
    }


def fx_layer_movement_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CON-18: a same-currency layer of an immutable calculation version."""
    rows = insert_version_rows(session, ctx.tenant_id)
    return {
        "tenant_id": ctx.tenant_id,
        "id": new_id(),
        "contract_version_id": rows.version_id,
        "contract_id": rows.chain.contract_id,
        "book_code": "ASC606",
        "entity_id": rows.chain.entity_id,
        "layer_key": "CONTRACT_ASSET:fixture",
        "movement_kind": "ASSET_LAYER_CREATED",
        "balance_role": "CONTRACT_ASSET",
        "effective_date": date(2026, 1, 1),
        "txn_currency": "USD",
        "functional_currency": "USD",
        "amount_txn": Decimal("1"),
        "amount_functional": Decimal("1"),
        "rate": Decimal("1"),
        **_CREATED,
    }


def schedule_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-ENG-01: a schedule of a version."""
    rows = insert_version_rows(session, ctx.tenant_id)
    return schedule_values(
        ctx.tenant_id, contract_version_id=rows.version_id, combination_group_id=rows.chain.group_id
    )


def schedule_line_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-ENG-02: a January line of a version's schedule."""
    rows = insert_version_rows(session, ctx.tenant_id)
    header = schedule_values(
        ctx.tenant_id, contract_version_id=rows.version_id, combination_group_id=rows.chain.group_id
    )
    schedule_id = _insert_visible(session, schedule, header)
    calendar_id = _visible_id(
        session,
        select(legal_entity.c.calendar_id).where(legal_entity.c.id == rows.chain.entity_id),
    )
    period_id = _insert_visible(
        session, period, period_values(ctx.tenant_id, calendar_id=calendar_id)
    )
    return schedule_line_values(
        ctx.tenant_id,
        schedule_id=schedule_id,
        contract_version_id=rows.version_id,
        contract_id=rows.chain.contract_id,
        entity_id=rows.chain.entity_id,
        period_id=period_id,
    )


# --- subledger (T-SL-01 to T-SL-04; CTR-3) --------------------------------------------------------

PROBE_RECORDED_AT: Final = datetime(2026, 1, 20, 12, tzinfo=UTC)
_FROM_HEAD: Final = object()


@dataclass(frozen=True, slots=True)
class LedgerParts:
    """The rows a probe posting references, inserted by ``insert_ledger_parts``."""

    chain: ContractRows
    computation_id: UUID
    period_id: UUID
    period_end_date: date
    account_id: UUID


def insert_ledger_parts(
    session: Session, tenant_id: UUID, *, state: str = "open", entity_id: UUID | None = None
) -> LedgerParts:
    """A contract chain with a computation, FY2026-P01 of the entity's calendar in ``state`` for
    ASC606, and a GL account, each inserted where the session's context allows it."""
    chain = insert_contract_rows(session, tenant_id, head_stream_version=1, entity_id=entity_id)
    computation_id = _computation(session, tenant_id, chain)
    calendar_id = _visible_id(
        session, select(legal_entity.c.calendar_id).where(legal_entity.c.id == chain.entity_id)
    )
    january = period_values(tenant_id, calendar_id=calendar_id)
    period_id = _insert_visible(session, period, january)
    _insert_visible(
        session,
        period_state,
        period_state_values(
            tenant_id,
            entity_id=chain.entity_id,
            period_id=period_id,
            period_end_date=january["end_date"],
            state=state,
        ),
    )
    account_id = _insert_visible(session, gl_account, gl_account_values(tenant_id))
    return LedgerParts(
        chain=chain,
        computation_id=computation_id,
        period_id=period_id,
        period_end_date=january["end_date"],
        account_id=account_id,
    )


def subledger_posting_values(
    tenant_id: UUID, *, parts: LedgerParts, **extra: Any
) -> dict[str, Any]:
    """T-SL-01: the ENGINE_COMPUTE posting of the probe computation."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "book_code": BookCode.ASC606.value,
        "posting_kind": "ENGINE_COMPUTE",
        "combination_group_id": parts.chain.group_id,
        "contract_computation_id": parts.computation_id,
        "close_run_id": None,
        "manual_adjustment_id": None,
        "reverses_posting_id": None,
        "idempotency_key": f"compute:{parts.computation_id}",
        "description": "Probe computation",
        "created_at": PROBE_RECORDED_AT,
        "created_by": None,
        **_CREATED,
        **extra,
    }


def subledger_line_values(
    tenant_id: UUID,
    *,
    posting: Mapping[str, Any],
    parts: LedgerParts,
    amount: Decimal = Decimal("10.00"),
    **extra: Any,
) -> dict[str, Any]:
    """T-SL-04: a USD line of entry 1 in FY2026-P01; a debit on CONTRACT_LIABILITY, a credit on
    REVENUE. Every column is named, so the row hashes as the stored line (T-SL-02)."""
    return {
        "tenant_id": tenant_id,
        "period_end_date": parts.period_end_date,
        "id": new_id(),
        "subledger_posting_id": posting["id"],
        "book_code": posting["book_code"],
        "entity_id": parts.chain.entity_id,
        "period_id": parts.period_id,
        "origin_period_id": None,
        "is_post_reopen": False,
        "effective_date": date(2026, 1, 15),
        "recorded_at": PROBE_RECORDED_AT,
        "entry_no": 1,
        "entry_kind": "REVENUE_RECOGNITION",
        "account_role": (
            AccountRole.CONTRACT_LIABILITY.value if amount > 0 else AccountRole.REVENUE.value
        ),
        "clearing_purpose": None,
        "gl_account_id": parts.account_id,
        "dimensions": {},
        "dimension_set_sha256": dimension_set_sha256({}),
        "txn_currency": "USD",
        "amount_txn": amount,
        "functional_currency": "USD",
        "amount_functional": amount,
        "fx_rate_set_version_id": None,
        "fx_rate_id": None,
        "fx_rate": None,
        "fx_layer_key": None,
        "contract_id": parts.chain.contract_id,
        "obligation_id": None,
        "contract_version_id": None,
        "contract_event_id": None,
        "schedule_line_id": None,
        "schedule_period_end_date": None,
        "contract_cost_asset_id": None,
        "counterparty_entity_id": None,
        "reverses_line_id": None,
        "reverses_period_end_date": None,
        "reason_code": None,
        "legacy_key": None,
        "calc_trace_id": None,
        "trace_node_id": None,
        "description": None,
        "created_at": PROBE_RECORDED_AT,
        "created_by": None,
        **_CREATED,
        **extra,
    }


def ledger_seal_values(
    session: Session,
    tenant_id: UUID,
    *,
    posting: Mapping[str, Any],
    lines: Sequence[Mapping[str, Any]],
    previous: object = _FROM_HEAD,
    **extra: Any,
) -> dict[str, Any]:
    """T-SL-02: the seal of ``posting`` over ``lines``; ``previous`` defaults to the last seal of
    the book's chain head visible to ``session``."""
    if previous is _FROM_HEAD:
        head = session.execute(
            select(ledger_chain_head_table.c.last_seal_sha256).where(
                ledger_chain_head_table.c.tenant_id == tenant_id,
                ledger_chain_head_table.c.book_code == posting["book_code"],
            )
        ).scalar_one_or_none()
        previous_sha = None if head is None else str(head)
    else:
        previous_sha = None if previous is None else str(previous)
    totals = control_totals(lines)
    return {
        "tenant_id": tenant_id,
        "subledger_posting_id": posting["id"],
        "book_code": posting["book_code"],
        "line_count": len(lines),
        "control_totals": totals,
        "prev_seal_sha256": previous_sha,
        "seal_sha256": seal_sha256(previous_sha, posting, totals, lines),
        "sealed_at": PROBE_RECORDED_AT,
        "created_at": PROBE_RECORDED_AT,
        "created_by": None,
        **_CREATED,
        **extra,
    }


@dataclass(frozen=True, slots=True)
class LedgerRows:
    """A sealed probe posting inserted by ``insert_ledger_rows``."""

    parts: LedgerParts
    posting: Mapping[str, Any]
    lines: tuple[Mapping[str, Any], ...]
    seal_sha256: str

    @property
    def posting_id(self) -> UUID:
        return UUID(str(self.posting["id"]))


def insert_ledger_rows(
    session: Session,
    tenant_id: UUID,
    *,
    amounts: Sequence[Decimal] = (Decimal("10.00"), Decimal("-10.00")),
    state: str = "open",
    entity_id: UUID | None = None,
) -> LedgerRows:
    """A sealed posting of one entry with a line per amount, its parts and its seal (DB-06)."""
    parts = insert_ledger_parts(session, tenant_id, state=state, entity_id=entity_id)
    posting = subledger_posting_values(tenant_id, parts=parts)
    session.execute(insert(subledger_posting).values(**posting))
    lines = tuple(
        subledger_line_values(tenant_id, posting=posting, parts=parts, amount=amount)
        for amount in amounts
    )
    session.execute(insert(subledger_line), [dict(line) for line in lines])
    seal = ledger_seal_values(session, tenant_id, posting=posting, lines=lines)
    session.execute(insert(subledger_posting_seal).values(**seal))
    return LedgerRows(
        parts=parts, posting=posting, lines=lines, seal_sha256=str(seal["seal_sha256"])
    )


# Probe postings a builder opened, keyed by the returned row's id, for ``ROW_COMPLETERS``.
_PROBE_POSTINGS: Final[dict[UUID, tuple[LedgerParts, Mapping[str, Any]]]] = {}
_PROBE_AMOUNTS: Final = (Decimal("10.00"), Decimal("-10.00"))


def ledger_chain_head_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    """T-SL-03: the provisioned ASC606 head (``PROVISIONED_TABLES``; 04 §14.3)."""
    return {
        "tenant_id": ctx.tenant_id,
        "book_code": BookCode.ASC606.value,
        "last_chain_seq": 0,
        "last_seal_sha256": None,
    }


def subledger_posting_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SL-01: a probe posting; its completer adds two lines and the seal (DB-06 (3))."""
    parts = insert_ledger_parts(session, ctx.tenant_id)
    posting = subledger_posting_values(ctx.tenant_id, parts=parts)
    _PROBE_POSTINGS[UUID(str(posting["id"]))] = (parts, posting)
    return posting


def _seal_probe_posting(ctx: RowContext, session: Session, row: Mapping[str, Any]) -> None:
    parts, posting = _PROBE_POSTINGS.pop(UUID(str(row["id"])))
    lines = [
        subledger_line_values(ctx.tenant_id, posting=posting, parts=parts, amount=amount)
        for amount in _PROBE_AMOUNTS
    ]
    session.execute(insert(subledger_line), lines)
    seal = ledger_seal_values(session, ctx.tenant_id, posting=posting, lines=lines)
    session.execute(insert(subledger_posting_seal).values(**seal))


def subledger_line_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SL-04: the debit line of a probe posting the builder inserts; its completer adds the credit
    and the seal (DB-06 (3))."""
    parts = insert_ledger_parts(session, ctx.tenant_id)
    posting = subledger_posting_values(ctx.tenant_id, parts=parts)
    _insert_visible(session, subledger_posting, posting)
    line = subledger_line_values(ctx.tenant_id, posting=posting, parts=parts)
    _PROBE_POSTINGS[UUID(str(line["id"]))] = (parts, posting)
    return line


def subledger_line_event_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SL-12: the first-included event of a probe line the builder inserts with its posting,
    credit and seal (the line's own completer is not run for a dependent row, so the balanced
    posting is completed here). The seal is keyless (T-SL-02: ``subledger_posting_id``), so it is
    never handed to ``_insert_visible`` (which returns ``row["id"]``); the lines and the seal are
    inserted plainly only when the posting itself was visible to the session — under another
    tenant's context (CTL-036 steps (b) and (e)) the posting is refused, the dependents are
    skipped, and the returned row is what the caller then tries and fails to insert."""
    parts = insert_ledger_parts(session, ctx.tenant_id)
    posting = subledger_posting_values(ctx.tenant_id, parts=parts)
    visible = _insert_visible(session, subledger_posting, posting) == UUID(str(posting["id"]))
    debit = subledger_line_values(ctx.tenant_id, posting=posting, parts=parts)
    credit = subledger_line_values(
        ctx.tenant_id, posting=posting, parts=parts, amount=Decimal("-10.00")
    )
    if visible:
        session.execute(insert(subledger_line).values(**debit))
        session.execute(insert(subledger_line).values(**credit))
        seal = ledger_seal_values(session, ctx.tenant_id, posting=posting, lines=[debit, credit])
        session.execute(insert(subledger_posting_seal).values(**seal))
    event = contract_event_values(
        ctx.tenant_id,
        contract_id=parts.chain.contract_id,
        contracting_entity_id=parts.chain.entity_id,
        stream_version=1,
    )
    event_id = _insert_visible(session, contract_event, event)
    return {
        "tenant_id": ctx.tenant_id,
        "subledger_line_id": debit["id"],
        "subledger_line_period_end_date": parts.period_end_date,
        "contract_event_id": event_id,
        "ordinal": 1,
        **_CREATED,
    }


def _seal_probe_line(ctx: RowContext, session: Session, row: Mapping[str, Any]) -> None:
    parts, posting = _PROBE_POSTINGS.pop(UUID(str(row["id"])))
    credit = subledger_line_values(
        ctx.tenant_id, posting=posting, parts=parts, amount=Decimal("-10.00")
    )
    session.execute(insert(subledger_line).values(**credit))
    seal = ledger_seal_values(session, ctx.tenant_id, posting=posting, lines=[row, credit])
    session.execute(insert(subledger_posting_seal).values(**seal))


def subledger_posting_seal_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SL-02: the seal of a probe posting whose two lines the builder inserts."""
    parts = insert_ledger_parts(session, ctx.tenant_id)
    posting = subledger_posting_values(ctx.tenant_id, parts=parts)
    _insert_visible(session, subledger_posting, posting)
    lines = [
        subledger_line_values(ctx.tenant_id, posting=posting, parts=parts, amount=amount)
        for amount in _PROBE_AMOUNTS
    ]
    for line in lines:
        _insert_visible(session, subledger_line, line)
    return ledger_seal_values(session, ctx.tenant_id, posting=posting, lines=lines)


def manual_adjustment_values(
    tenant_id: UUID, *, contract_id: UUID, entity_id: UUID, period_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-SL-05: a DRAFT manual journal of 10.00 USD on ``contract_id`` in ``period_id``."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "adjustment_no": f"ADJ-{secrets.token_hex(4).upper()}",
        "kind": ManualAdjustmentKind.MANUAL_JOURNAL.value,
        "status": ManualAdjustmentStatus.DRAFT.value,
        "contract_id": contract_id,
        "obligation_id": None,
        "entity_id": entity_id,
        "book_code": BookCode.ASC606.value,
        "period_id": period_id,
        "effective_date": date(2026, 1, 15),
        "payload": {
            "lines": [
                {"account_role": "CONTRACT_LIABILITY", "amount_txn": "10.00", "dimensions": {}},
                {"account_role": "REVENUE", "amount_txn": "-10.00", "dimensions": {}},
            ]
        },
        "amount_functional_abs": Decimal("10.00"),
        "currency": "USD",
        "reason_code": "PROBE",
        "memo": "Probe adjustment",
        "impact_preview_file_id": None,
        "content_sha256": None,
        "approval_request_id": None,
        "applied_event_id": None,
        "subledger_posting_id": None,
        "is_deferred_past_lock": False,
        **_SYSTEM,
        **extra,
    }


@dataclass(frozen=True, slots=True)
class JournalParts:
    """The rows a probe journal run references, inserted by ``insert_journal_parts``."""

    calendar_id: UUID
    entity_id: UUID
    period_id: UUID
    account_id: UUID
    release_id: UUID


def insert_journal_parts(
    session: Session, tenant_id: UUID, *, state: str = "open", entity_id: UUID | None = None
) -> JournalParts:
    """A January calendar with FY2026-P01, an entity of it whose ASC606 period is in ``state``, a GL
    account and an engine release, each inserted where the session's context allows it."""
    calendar_id = _insert_visible(session, fiscal_calendar, fiscal_calendar_values(tenant_id))
    period_id = _insert_visible(session, period, period_values(tenant_id, calendar_id=calendar_id))
    entity = legal_entity_values(tenant_id, calendar_id=calendar_id, entity_id=entity_id)
    entity_row_id = _insert_visible(session, legal_entity, entity)
    _insert_visible(
        session,
        period_state,
        period_state_values(tenant_id, entity_id=entity_row_id, period_id=period_id, state=state),
    )
    return JournalParts(
        calendar_id=calendar_id,
        entity_id=entity_row_id,
        period_id=period_id,
        account_id=_insert_visible(session, gl_account, gl_account_values(tenant_id)),
        release_id=_insert_visible(session, engine_release, engine_release_values()),
    )


def journal_run_values(tenant_id: UUID, *, parts: JournalParts, **extra: Any) -> dict[str, Any]:
    """T-SL-06: a draft GROSS run of FY2026-P01 covering the chain sequences (0, 0]."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "run_no": f"JR-{secrets.token_hex(4).upper()}",
        "entity_id": parts.entity_id,
        "book_code": BookCode.ASC606.value,
        "period_id": parts.period_id,
        "mode": JournalRunMode.GROSS.value,
        "delta_book_code": None,
        "grain": JournalRunGrain.ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS.value,
        "state": JournalState.DRAFT.value,
        "cutoff_known_at": PROBE_RECORDED_AT,
        "from_chain_seq": 0,
        "to_chain_seq": 0,
        "delta_from_chain_seq": None,
        "delta_to_chain_seq": None,
        "functional_currency": "USD",
        "line_count": 0,
        "total_debit_functional": Decimal("0"),
        "total_credit_functional": Decimal("0"),
        "close_run_id": None,
        "job_id": None,
        "approval_request_id": None,
        "approved_at": None,
        "exported_at": None,
        "acknowledged_at": None,
        "cancelled_at": None,
        **_SYSTEM,
        **extra,
    }


def journal_batch_values(
    tenant_id: UUID, *, parts: JournalParts, run: Mapping[str, Any], **extra: Any
) -> dict[str, Any]:
    """T-SL-07: batch 1, chunk 1 of ``run``, an empty draft USD batch for the CSV adapter."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "journal_run_id": run["id"],
        "batch_no": 1,
        "chunk_no": 1,
        "entity_id": parts.entity_id,
        "book_code": run["book_code"],
        "period_id": parts.period_id,
        "txn_currency": "USD",
        "functional_currency": "USD",
        "state": JournalState.DRAFT.value,
        "line_count": 0,
        "total_debit_txn": Decimal("0"),
        "total_credit_txn": Decimal("0"),
        "total_debit_functional": Decimal("0"),
        "total_credit_functional": Decimal("0"),
        "engine_release_id": parts.release_id,
        "adapter": GlAdapter.CSV.value,
        "integration_connection_id": None,
        "external_id": f"erev:probe-{secrets.token_hex(4)}:{run['run_no']}:1:1",
        "export_file_id": None,
        "export_sha256": None,
        "detail_file_id": None,
        "detail_sha256": None,
        "outbox_message_id": None,
        "attempt_count": 0,
        "last_error": None,
        "exported_at": None,
        "acknowledged_at": None,
        **_SYSTEM,
        **extra,
    }


def journal_entry_values(
    tenant_id: UUID, *, parts: JournalParts, batch_id: UUID, je_seq: int = 1, **extra: Any
) -> dict[str, Any]:
    """T-SL-08: the automated entry ``je_seq`` of the probe entity in ``batch_id``."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "journal_batch_id": batch_id,
        "entity_id": parts.entity_id,
        "je_seq": je_seq,
        "je_no": f"JE-{parts.entity_id.hex.upper()}-{je_seq:06d}",
        "je_type": JeType.AUTOMATED.value,
        "entry_kind": "REVENUE_RECOGNITION",
        "description": "Probe journal entry",
        "source_event_ids": [],
        "manual_adjustment_id": None,
        "reverses_journal_entry_id": None,
        "is_post_close": False,
        **_CREATED,
        **extra,
    }


def journal_line_values(
    tenant_id: UUID,
    *,
    parts: JournalParts,
    entry_id: UUID,
    batch_id: UUID,
    line_no: int = 1,
    debit: Decimal = Decimal("10.00"),
    credit: Decimal = Decimal("0"),
    **extra: Any,
) -> dict[str, Any]:
    """T-SL-09: a USD line of FY2026-P01 with ``debit`` and ``credit`` in both currencies; a debit
    on CONTRACT_LIABILITY, otherwise a credit on REVENUE."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "journal_entry_id": entry_id,
        "journal_batch_id": batch_id,
        "line_no": line_no,
        "entity_id": parts.entity_id,
        "book_code": BookCode.ASC606.value,
        "period_id": parts.period_id,
        "account_role": (
            AccountRole.CONTRACT_LIABILITY.value if debit > 0 else AccountRole.REVENUE.value
        ),
        "gl_account_id": parts.account_id,
        "gl_account_code": "PROBE",
        "dimensions": {},
        "dimension_set_sha256": dimension_set_sha256({}),
        "txn_currency": "USD",
        "debit_txn": debit,
        "credit_txn": credit,
        "functional_currency": "USD",
        "debit_functional": debit,
        "credit_functional": credit,
        "contract_id": None,
        "obligation_id": None,
        "legacy_key": None,
        "counterparty_entity_id": None,
        "origin_period_id": None,
        "fx_rate_set_version_ids": [],
        "fx_rate_ids": [],
        "memo": None,
        "source_line_count": 1,
        "source_grouping_sha256": secrets.token_hex(32),
        **_CREATED,
        **extra,
    }


def posting_ack_values(tenant_id: UUID, *, batch_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-SL-10: the manual confirmation of ``batch_id`` with an ERP reference (BR-JE-03)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "journal_batch_id": batch_id,
        "ack_kind": PostingAckKind.MANUAL_CONFIRMATION.value,
        "gl_document_id": "JE-000123",
        "gl_posted_date": date(2026, 1, 31),
        "response_sha256": None,
        "response_file_id": None,
        "message": None,
        "received_at": PROBE_RECORDED_AT,
        **_CREATED,
        **extra,
    }


# POLICIES CHK-022 (Contract 1): a debit and a credit of 295.69, as (debit, credit) pairs.
CHK_022_LINES: Final = ((Decimal("295.69"), Decimal("0")), (Decimal("0"), Decimal("295.69")))


@dataclass(frozen=True, slots=True)
class JournalRows:
    """A draft probe run with one batch, its entries and its lines, inserted by
    ``insert_journal_rows``."""

    parts: JournalParts
    run: Mapping[str, Any]
    batch: Mapping[str, Any]
    entries: tuple[Mapping[str, Any], ...]
    lines: tuple[Mapping[str, Any], ...]


def insert_journal_rows(
    session: Session,
    tenant_id: UUID,
    *,
    parts: JournalParts | None = None,
    lines: Sequence[tuple[Decimal, Decimal]] = CHK_022_LINES,
    je_seqs: Sequence[int] = (1,),
    state: str = "open",
    entity_id: UUID | None = None,
    **batch_values: Any,
) -> JournalRows:
    """A draft run of ``parts`` (inserted when None) with one USD batch holding an entry per
    ``je_seqs`` value and, on the first entry, a line per (debit, credit) pair of ``lines``. The
    batch totals sum the lines; the run header carries the debit total on both sides (its check)."""
    parts = parts or insert_journal_parts(session, tenant_id, state=state, entity_id=entity_id)
    debit = sum((pair[0] for pair in lines), Decimal("0"))
    credit = sum((pair[1] for pair in lines), Decimal("0"))
    run = journal_run_values(
        tenant_id,
        parts=parts,
        line_count=len(lines),
        total_debit_functional=debit,
        total_credit_functional=debit,
    )
    session.execute(insert(journal_run).values(**run))
    batch = journal_batch_values(
        tenant_id,
        parts=parts,
        run=run,
        line_count=len(lines),
        total_debit_txn=debit,
        total_credit_txn=credit,
        total_debit_functional=debit,
        total_credit_functional=credit,
        **batch_values,
    )
    session.execute(insert(journal_batch).values(**batch))
    entries = tuple(
        journal_entry_values(tenant_id, parts=parts, batch_id=batch["id"], je_seq=seq)
        for seq in je_seqs
    )
    if entries:
        session.execute(insert(journal_entry), [dict(entry) for entry in entries])
    rows = tuple(
        journal_line_values(
            tenant_id,
            parts=parts,
            entry_id=entries[0]["id"],
            batch_id=batch["id"],
            line_no=number,
            debit=pair_debit,
            credit=pair_credit,
        )
        for number, (pair_debit, pair_credit) in enumerate(lines, start=1)
    )
    if rows:
        session.execute(insert(journal_line), [dict(line) for line in rows])
    return JournalRows(parts=parts, run=run, batch=batch, entries=entries, lines=rows)


def insert_sandbox_tenant(keyring: KeyRing) -> UUID:
    """A tenant row of kind ``sandbox`` (T-PLT-01) inserted under ``app.platform_scope =
    'provisioning'``, without the roles, books and chain heads provisioning writes (DB-15)."""
    tenant_id = new_id()
    code = f"sandbox-{secrets.token_hex(6)}"
    with platform_session(
        "provisioning", actor_user_id=None, request_id=f"tests-{code}", keyring=keyring
    ) as session:
        session.execute(
            insert(tenant).values(
                id=tenant_id,
                code=code,
                kind=TenantKind.SANDBOX.value,
                status=TenantStatus.ACTIVE.value,
                display_name=f"Tenant {code}",
                reporting_currency="USD",
                is_demo=False,
                audit_hmac_key_id=keyring.new_tenant_audit_key_id(tenant_id),
                setup_completed_at=None,
                **_SYSTEM,
            )
        )
        name_platform_tenant(session, tenant_id)
    return tenant_id


def manual_adjustment_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SL-05: a DRAFT adjustment of a probe contract and period the builder inserts where the
    context allows it."""
    parts = insert_ledger_parts(session, ctx.tenant_id)
    return manual_adjustment_values(
        ctx.tenant_id,
        contract_id=parts.chain.contract_id,
        entity_id=parts.chain.entity_id,
        period_id=parts.period_id,
    )


def journal_run_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SL-06: a draft run of parts the builder inserts where the context allows it."""
    return journal_run_values(ctx.tenant_id, parts=insert_journal_parts(session, ctx.tenant_id))


def journal_batch_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SL-07: a draft batch of a run the builder inserts where the context allows it."""
    parts = insert_journal_parts(session, ctx.tenant_id)
    run = journal_run_values(ctx.tenant_id, parts=parts)
    _insert_visible(session, journal_run, run)
    return journal_batch_values(ctx.tenant_id, parts=parts, run=run)


def _probe_batch(ctx: RowContext, session: Session) -> tuple[JournalParts, dict[str, Any]]:
    """Parts, a run and its batch, each inserted where the context allows it."""
    parts = insert_journal_parts(session, ctx.tenant_id)
    run = journal_run_values(ctx.tenant_id, parts=parts)
    _insert_visible(session, journal_run, run)
    batch = journal_batch_values(ctx.tenant_id, parts=parts, run=run)
    _insert_visible(session, journal_batch, batch)
    return parts, batch


def journal_entry_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SL-08: entry 1 of a batch the builder inserts where the context allows it."""
    parts, batch = _probe_batch(ctx, session)
    return journal_entry_values(ctx.tenant_id, parts=parts, batch_id=batch["id"])


def journal_line_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SL-09: a debit line of an entry the builder inserts where the context allows it."""
    parts, batch = _probe_batch(ctx, session)
    entry = journal_entry_values(ctx.tenant_id, parts=parts, batch_id=batch["id"])
    _insert_visible(session, journal_entry, entry)
    return journal_line_values(
        ctx.tenant_id, parts=parts, entry_id=entry["id"], batch_id=batch["id"]
    )


def posting_ack_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-SL-10: a manual confirmation of a batch the builder inserts where the context allows it."""
    _, batch = _probe_batch(ctx, session)
    return posting_ack_values(ctx.tenant_id, batch_id=batch["id"])


# --- close tables (BUILD_SPEC CLO-2) -------------------------------------------------------------

# 04 T-CLS-01 ``steps``: the fixed step order (REQ-CLS-012).
CLOSE_RUN_STEP_CODES: Final = (
    "CUTOFF",
    "INTERFACE_COMPLETENESS",
    "EXCEPTION_CHECK",
    "RECOMPUTE_DIRTY",
    "RELEASE_SCHEDULES",
    "FX_REMEASUREMENT",
    "NETTING_RECLASS",
    "INVARIANTS",
    "JOURNAL_SUMMARIZATION",
    "EXPORT",
    "ACKNOWLEDGEMENT_WAIT",
    "GL_TIE_OUT",
    "DATASET_FREEZE",
    "LOCK",
)


def close_run_steps(status: str = "PENDING", *, lock_status: str | None = None) -> list[Any]:
    """T-CLS-01 ``steps``: the fourteen steps in their fixed order, each in ``status``, and the
    ``LOCK`` step in ``lock_status`` when given."""
    return [
        {
            "step_code": code,
            "status": lock_status if code == "LOCK" and lock_status is not None else status,
            "started_at": None,
            "finished_at": None,
            "counts": {},
            "problem": None,
        }
        for code in CLOSE_RUN_STEP_CODES
    ]


def close_run_values(
    tenant_id: UUID, *, entity_id: UUID, period_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-CLS-01: a PENDING ASC606 run with its fourteen steps PENDING."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "close_run_no": f"CLS-P{secrets.token_hex(5)}",
        "entity_id": entity_id,
        "book_code": BookCode.ASC606.value,
        "period_id": period_id,
        "status": CloseRunStatus.PENDING.value,
        "cutoff_known_at": PROBE_RECORDED_AT,
        "current_step_code": None,
        "steps": close_run_steps(),
        "counts": {},
        "job_id": None,
        "started_at": None,
        "finished_at": None,
        **_SYSTEM,
        **extra,
    }


def close_checklist_template_values(
    tenant_id: UUID, *, code: str | None = None, **extra: Any
) -> dict[str, Any]:
    """T-CLS-02: a blocking tenant-defined manual close task due three business days after period
    end."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "code": code or f"PROBE-TASK-{secrets.token_hex(4).upper()}",
        "name": "Probe close task",
        "description": None,
        "gate_kind": ChecklistGateKind.MANUAL.value,
        "gate_check_code": None,
        "is_blocking": True,
        "is_system": False,
        "owner_role_id": None,
        "due_offset_days": 3,
        "sequence": 100,
        "is_active": True,
        **_SYSTEM,
        **extra,
    }


def close_checklist_item_values(
    tenant_id: UUID, *, template_id: UUID, entity_id: UUID, period_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-CLS-03: a NOT_STARTED item of a template for an entity's ASC606 period."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "close_checklist_template_id": template_id,
        "entity_id": entity_id,
        "book_code": BookCode.ASC606.value,
        "period_id": period_id,
        "status": ChecklistStatus.NOT_STARTED.value,
        "owner_membership_id": None,
        "due_date": None,
        "result": None,
        "control_execution_id": None,
        "signoff_id": None,
        "waiver_approval_request_id": None,
        "comment": None,
        **_SYSTEM,
        **extra,
    }


@dataclass(frozen=True, slots=True)
class CloseParts:
    """The rows a probe period lock references, inserted by ``insert_close_parts``."""

    calendar_id: UUID
    entity_id: UUID
    period_id: UUID
    period_state_transition_id: UUID
    approval_request_id: UUID
    file_id: UUID


def insert_close_parts(
    session: Session, tenant_id: UUID, *, state: str = "open", entity_id: UUID | None = None
) -> CloseParts:
    """A January calendar with FY2026-P01, an entity whose ASC606 period is in ``state`` with a
    creation transition, an approval request of the entity and a file, each inserted where the
    session's context allows it."""
    calendar_id = _insert_visible(session, fiscal_calendar, fiscal_calendar_values(tenant_id))
    period_id = _insert_visible(session, period, period_values(tenant_id, calendar_id=calendar_id))
    entity = legal_entity_values(tenant_id, calendar_id=calendar_id, entity_id=entity_id)
    entity_row_id = _insert_visible(session, legal_entity, entity)
    state_row = period_state_values(
        tenant_id, entity_id=entity_row_id, period_id=period_id, state=state
    )
    state_id = _insert_visible(session, period_state, state_row)
    transition = period_state_transition_values(
        tenant_id, period_state_id=state_id, entity_id=entity_row_id, period_id=period_id
    )
    return CloseParts(
        calendar_id=calendar_id,
        entity_id=entity_row_id,
        period_id=period_id,
        period_state_transition_id=_insert_visible(session, period_state_transition, transition),
        approval_request_id=_insert_visible(
            session, approval_request, approval_request_values(tenant_id, entity_id=entity_row_id)
        ),
        file_id=_insert_visible(session, file_object, file_object_values(tenant_id)),
    )


PROBE_LOCK_CUTOFF: Final = datetime(2026, 9, 12, 12, tzinfo=UTC)  # the frozen test clock


def period_lock_values(
    tenant_id: UUID, *, parts: CloseParts, kind: str = "LOCK", **extra: Any
) -> dict[str, Any]:
    """T-CLS-04: a lock of the parts' period with an empty certification at chain sequence 0; a
    ``LOCK`` row — and no other kind — names its freeze cutoff (rev 1.113,
    ``ck_period_lock__cutoff_known_at``): the ``created_at`` the caller gives, else the frozen
    probe instant."""
    cutoff = extra.get("created_at", PROBE_LOCK_CUTOFF) if kind == "LOCK" else None
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "kind": kind,
        "entity_id": parts.entity_id,
        "book_code": BookCode.ASC606.value,
        "period_id": parts.period_id,
        "period_state_transition_id": parts.period_state_transition_id,
        "approval_request_id": parts.approval_request_id,
        "reason_code": None,
        "comment": None,
        "certification": [],
        "ledger_head_chain_seq": 0,
        "ledger_head_sha256": None,
        "audit_head_chain_seq": 0,
        "audit_head_hmac": None,
        "snapshot_manifest_sha256": None,
        "previous_lock_id": None,
        "diff_report_file_id": None,
        "cutoff_known_at": cutoff,
        **_CREATED,
        **extra,
    }


def insert_reopen_record(
    session: Session,
    tenant_id: UUID,
    *,
    entity_id: UUID,
    period_id: UUID,
    book_code: BookCode = BookCode.ASC606,
) -> UUID:
    """Put the entity's period of ``book_code`` under a ``REOPEN`` record as the reopen decision
    leaves it (``close.commands._record_transition``): the T-CLS-04 row, its ``closed →
    reopened`` transition and the state row's ``current_lock_id``. The state literal stays what
    the caller made it — 04 T-REF-06 rev 1.184: "locked once and not locked now" is this record,
    which DB-07 reads for ``is_post_reopen``, whatever the state reads. Returns the lock id."""
    state_id = session.execute(
        select(period_state.c.id).where(
            period_state.c.entity_id == entity_id,
            period_state.c.period_id == period_id,
            period_state.c.book_code == book_code.value,
        )
    ).scalar_one()
    transition_id = new_id()
    parts = CloseParts(
        calendar_id=UUID(int=0),
        entity_id=entity_id,
        period_id=period_id,
        period_state_transition_id=transition_id,
        approval_request_id=insert_approval_request(
            session, tenant_id=tenant_id, entity_id=entity_id
        ),
        file_id=UUID(int=0),
    )
    lock = period_lock_values(
        tenant_id,
        parts=parts,
        kind="REOPEN",
        reason_code="ERROR_CORRECTION",
        book_code=book_code.value,
    )
    session.execute(insert(period_lock).values(**lock))
    session.execute(
        insert(period_state_transition).values(
            **period_state_transition_values(
                tenant_id,
                period_state_id=state_id,
                entity_id=entity_id,
                period_id=period_id,
                from_state="closed",
                to_state="reopened",
                book_code=book_code,
                id=transition_id,
                reason_code="ERROR_CORRECTION",
                approval_request_id=parts.approval_request_id,
                period_lock_id=lock["id"],
            )
        )
    )
    session.execute(
        update(period_state)
        .where(period_state.c.id == state_id)
        .values(current_lock_id=lock["id"], updated_by_kind=PrincipalKind.SYSTEM.value)
    )
    return UUID(str(lock["id"]))


def lock_snapshot_values(
    tenant_id: UUID, *, period_lock_id: UUID, file_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-CLS-05: the empty ``JE_POPULATION`` dataset of a lock."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "period_lock_id": period_lock_id,
        "snapshot_kind": SnapshotKind.JE_POPULATION.value,
        "report_run_id": None,
        "file_id": file_id,
        "file_sha256": PROBE_CONTENT_SHA256,
        "row_count": 0,
        "control_totals": {},
        **_CREATED,
        **extra,
    }


def reconciliation_values(
    tenant_id: UUID, *, entity_id: UUID, period_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-CLS-06: a DRAFT subledger-to-GL reconciliation of an entity's ASC606 period."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "reconciliation_no": f"REC-P{secrets.token_hex(5)}",
        "kind": ReconciliationKind.SUBLEDGER_TO_GL.value,
        "entity_id": entity_id,
        "book_code": BookCode.ASC606.value,
        "period_id": period_id,
        "status": ReconciliationStatus.DRAFT.value,
        "as_of_known_at": PROBE_RECORDED_AT,
        "period_lock_id": None,
        "source_file_id": None,
        "sync_run_id": None,
        "totals": [],
        "variance_count": 0,
        "unexplained_other_amount": None,
        "auto_certify_rule_set_version_id": None,
        "auto_certify_rule_id": None,
        "report_run_id": None,
        "certified_at": None,
        **_SYSTEM,
        **extra,
    }


def reconciliation_item_values(
    tenant_id: UUID, *, reconciliation_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-CLS-07: an unexplained USD 0.01 amount variance on account 4000."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "reconciliation_id": reconciliation_id,
        "item_kind": "AMOUNT_VARIANCE",
        "account_code": "4000",
        "contract_id": None,
        "invoice_number": None,
        "subledger_amount": Decimal("100.00"),
        "source_amount": Decimal("99.99"),
        "difference": Decimal("0.01"),
        "currency": "USD",
        "is_high_risk": False,
        "gl_document_reference": None,
        "explanation": None,
        "resolved_at": None,
        "resolved_by": None,
        "resolved_by_kind": None,
        **_SYSTEM,
        **extra,
    }


def signoff_values(
    tenant_id: UUID,
    *,
    subject_id: UUID,
    signer_id: UUID,
    role: str = "PREPARER",
    subject_type: str = "reconciliation",
    **extra: Any,
) -> dict[str, Any]:
    """T-CLS-08: a sign-off of ``subject_id`` by ``signer_id``, MFA-verified at ``INVITED_AT``."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "subject_type": subject_type,
        "subject_id": subject_id,
        "role": role,
        "signer_id": signer_id,
        "statement": f"I signed this {subject_type} as {role.lower()}.",
        "subject_content_sha256": PROBE_CONTENT_SHA256,
        "mfa_verified_at": INVITED_AT,
        "signed_at": INVITED_AT,
        **extra,
    }


def close_run_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CLS-01: a PENDING run of an entity and period the builder inserts where the context allows
    it."""
    period_id, entity_id = _entity_chain(ctx, session)
    return close_run_values(ctx.tenant_id, entity_id=entity_id, period_id=period_id)


def close_checklist_item_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CLS-03: an item of a task, entity and period the builder inserts where the context allows
    it."""
    period_id, entity_id = _entity_chain(ctx, session)
    template_id = _insert_visible(
        session, close_checklist_template, close_checklist_template_values(ctx.tenant_id)
    )
    return close_checklist_item_values(
        ctx.tenant_id, template_id=template_id, entity_id=entity_id, period_id=period_id
    )


def period_lock_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CLS-04: a lock of parts the builder inserts where the context allows it."""
    return period_lock_values(ctx.tenant_id, parts=insert_close_parts(session, ctx.tenant_id))


def lock_snapshot_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CLS-05: a dataset of a lock the builder inserts where the context allows it."""
    parts = insert_close_parts(session, ctx.tenant_id)
    lock_id = _insert_visible(session, period_lock, period_lock_values(ctx.tenant_id, parts=parts))
    return lock_snapshot_values(ctx.tenant_id, period_lock_id=lock_id, file_id=parts.file_id)


def reconciliation_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CLS-06: a DRAFT reconciliation of an entity and period the builder inserts where the
    context allows it."""
    period_id, entity_id = _entity_chain(ctx, session)
    return reconciliation_values(ctx.tenant_id, entity_id=entity_id, period_id=period_id)


def reconciliation_item_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-CLS-07: an item of a reconciliation the builder inserts where the context allows it."""
    period_id, entity_id = _entity_chain(ctx, session)
    parent = reconciliation_values(ctx.tenant_id, entity_id=entity_id, period_id=period_id)
    reconciliation_id = _insert_visible(session, reconciliation, parent)
    return reconciliation_item_values(ctx.tenant_id, reconciliation_id=reconciliation_id)


def signoff_row(ctx: RowContext, _: Session) -> dict[str, Any]:
    """T-CLS-08: a PREPARER sign-off of a soft-referenced reconciliation by the builder's user."""
    return signoff_values(ctx.tenant_id, subject_id=new_id(), signer_id=ctx.user_id)


# T-RPT-01 code of the probe runs: a seeded definition without entity-scoped sources (RPS-1).
PROBE_REPORT_CODE: Final = "api_client_inventory"


def report_run_values(tenant_id: UUID, *, engine_release_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-RPT-02: a QUEUED JSON run of the seeded ``api_client_inventory`` definition, version 1."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "report_run_no": f"RPT-P{secrets.token_hex(5)}",
        "report_code": PROBE_REPORT_CODE,
        "report_version": 1,
        "status": RunStatus.QUEUED.value,
        "parameters": {
            "entity_codes": [],
            "include_revoked": False,
            "known_at": PROBE_RECORDED_AT.isoformat(),
        },
        "entity_ids": [],
        "book_code": None,
        "as_of_date": None,
        "known_at": PROBE_RECORDED_AT,
        "period_lock_id": None,
        "engine_release_id": engine_release_id,
        "output_format": "JSON",
        "output_file_id": None,
        "output_sha256": None,
        "manifest_file_id": None,
        "row_count": None,
        "control_totals": None,
        "tie_out_results": None,
        "ledger_heads": None,
        "source_binding": None,  # frps3b (04 T-RPT-02 rev 1.55): unbound until SUCCEEDED
        "child_report_run_ids": [],
        "disclosure_snapshot_ids": [],
        "job_id": None,
        "started_at": None,
        "finished_at": None,
        "problem": None,
        **_SYSTEM,
        **extra,
    }


def disclosure_snapshot_values(
    tenant_id: UUID, *, entity_id: UUID, period_id: UUID, report_run_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-RPT-03: an on-demand draft RPO dataset of an entity's ASC606 period, without a lock."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "disclosure_kind": DisclosureKind.RPO.value,
        "entity_id": entity_id,
        "book_code": BookCode.ASC606.value,
        "period_id": period_id,
        "period_lock_id": None,
        "report_run_id": report_run_id,
        "data": {"rows": []},
        "data_sha256": PROBE_CONTENT_SHA256,
        **_CREATED,
        **extra,
    }


def evidence_pack_values(tenant_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-RPT-04: a QUEUED ACCESS pack as of 30 Sep 2026."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "pack_no": f"EVP-P{secrets.token_hex(5)}",
        "kind": EvidencePackKind.ACCESS.value,
        "entity_id": None,
        "book_code": None,
        "period_id": None,
        "period_lock_id": None,
        "contract_ids": [],
        "as_of_date": date(2026, 9, 30),
        "from_date": None,
        "to_date": None,
        "status": RunStatus.QUEUED.value,
        "manifest": None,
        "manifest_sha256": None,
        "file_id": None,
        "report_run_ids": [],
        "job_id": None,
        **_SYSTEM,
        **extra,
    }


def insert_report_run(session: Session, tenant_id: UUID, **extra: Any) -> UUID:
    """A probe engine release and a QUEUED run of it, each inserted where the context allows it."""
    release_id = _insert_visible(session, engine_release, engine_release_values())
    run = report_run_values(tenant_id, engine_release_id=release_id, **extra)
    return _insert_visible(session, report_run, run)


def report_run_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-RPT-02: a QUEUED run of an engine release the builder inserts."""
    release_id = _insert_visible(session, engine_release, engine_release_values())
    return report_run_values(ctx.tenant_id, engine_release_id=release_id)


def disclosure_snapshot_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    """T-RPT-03: a dataset of an entity, period and run the builder inserts where the context
    allows it."""
    period_id, entity_id = _entity_chain(ctx, session)
    run_id = insert_report_run(session, ctx.tenant_id)
    return disclosure_snapshot_values(
        ctx.tenant_id, entity_id=entity_id, period_id=period_id, report_run_id=run_id
    )


def migration_batch_values(
    tenant_id: UUID, *, source_file_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-MIG-01: an UPLOADED opening-balance migration of a stored legacy database (LMG-1)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "migration_no": f"MIG-P{secrets.token_hex(5)}",
        "mode": MigrationMode.OPENING_BALANCES.value,
        "status": MigrationStatus.UPLOADED.value,
        "source_file_id": source_file_id,
        "source_sha256": secrets.token_hex(32),
        "cutover_date": date(2023, 1, 31),
        "sandbox_tenant_id": None,
        "profile": None,
        "import_upload_ids": [],
        "registry_version_id": None,
        "reconciliation_id": None,
        "reconciliation_report_run_id": None,
        "approval_request_id": None,
        "job_id": None,
        "started_at": None,
        "finished_at": None,
        "capture_operation_id": None,
        "problem": None,
        **_SYSTEM,
        **extra,
    }


def migration_batch_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    file_row = file_object_values(ctx.tenant_id, purpose=FilePurpose.LEGACY_DATABASE)
    file_id = _inserted_id(session, file_object, file_row)
    return migration_batch_values(ctx.tenant_id, source_file_id=file_id)


def _legacy_row_payload() -> dict[str, str | None]:
    """The 71 legacy names (``legacy_columns.CONTRACT_LIVE``) with the identifying values set."""
    from erev_api.domain.reports import legacy_columns

    payload: dict[str, str | None] = {c.name: None for c in legacy_columns.CONTRACT_LIVE}
    payload.update(
        {
            "Contract Unique Name": "Contract 1",
            "POB Unique ID": "POB #1",
            "SKU Name": "Hardware 1",
            "Current Period": "2023-01-01",
            "Processing Time Log": "2023-01-15 09:11:44",
            "Record Unique ID without time": "Contract 1/POB #1",
            "Record Unique ID": "2023-01-15 09:11:44 Contract 1/POB #1",
        }
    )
    return payload


def migrated_legacy_row_values(
    tenant_id: UUID, *, migration_batch_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-MIG-02: SQLite rowid 1 of the batch, all 71 columns as stored text (LMG-1)."""
    payload = _legacy_row_payload()
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "migration_batch_id": migration_batch_id,
        "source_rowid": 1,
        "contract_external_id": "Contract 1",
        "obligation_key": "POB #1",
        "product_code": "Hardware 1",
        "current_period": date(2023, 1, 1),
        "processing_time_log": "2023-01-15 09:11:44",
        "record_unique_id": "2023-01-15 09:11:44 Contract 1/POB #1",
        "legacy_row": payload,
        "legacy_row_sha256": sha256_hex(payload),
        "contract_id": None,
        "obligation_id": None,
        "label": "migrated, unattributed",
        **_CREATED,
        **extra,
    }


def migrated_legacy_row_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    batch_id = _inserted_id(session, migration_batch, migration_batch_row(ctx, session))
    return migrated_legacy_row_values(ctx.tenant_id, migration_batch_id=batch_id)


def migration_reconciliation_line_values(
    tenant_id: UUID, *, migration_batch_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-MIG-03: the contract-level TRANSACTION_PRICE line of Contract 1, within tolerance
    (LMG-3; PRD WLD-X-27)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "migration_batch_id": migration_batch_id,
        "contract_external_id": "Contract 1",
        "obligation_key": None,
        "measure": "TRANSACTION_PRICE",
        "source_value": Decimal("1300"),
        "erev_value": Decimal("1300"),
        "difference": Decimal("0"),
        "tolerance": Decimal("0.0001"),
        "is_within_tolerance": True,
        "deviation_ref": None,
        "exception_item_id": None,
        **_CREATED,
        **extra,
    }


def migration_reconciliation_line_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    batch_id = _inserted_id(session, migration_batch, migration_batch_row(ctx, session))
    return migration_reconciliation_line_values(ctx.tenant_id, migration_batch_id=batch_id)


def migration_population_version_values(
    tenant_id: UUID, *, migration_batch_id: UUID, **extra: Any
) -> dict[str, Any]:
    """T-MIG-04 (rev 1.60): one captured contract version of the import's dry run — Contract 1 of
    WLD-F-15 at cutover 2023-01-31, a singleton member, one expected obligation version, a trace
    mirror of one node whose hash is consistent (the reconcile rebuilds and checks it)."""
    node = {
        "id": "revenue_cum:POB #1",
        "measure": "revenue_cum",
        "value": "295.69",
        "currency": "USD",
        "formula_id": "f",
        "inputs": [],
        "params": {},
        "rounding_residue": "0.000000000000000000",
        "narrative_key": "k",
    }
    trace = {"nodes": [node]}
    contract_version_id = new_id()
    # the retained producing input (Codex 0515 R1): a real, decodable bundle whose facts the row
    # repeats — input_sha256, bundle_known_at, the member key, the opening event's batch / cutover
    from erev_api.domain.migration.capture import opening_event_binding
    from support.migration_capture import capture_world

    world = capture_world(migration_batch_id)
    opening_event_id = new_id()
    row: dict[str, Any] = {
        "tenant_id": tenant_id,
        "id": new_id(),
        "migration_batch_id": migration_batch_id,
        "contract_version_id": contract_version_id,
        "version_no": 1,
        "book_code": "ASC606",
        "combination_group_id": new_id(),
        "status_in_book": "ACTIVE",
        "contract_computation_id": new_id(),
        "input_sha256": world.input_sha256,
        "output_sha256": secrets.token_hex(32),
        "engine_version": world.bundle.engine_version,
        "engine_release_id": None,
        "known_at": world.bundle.known_at,
        "bundle_known_at": world.bundle.known_at,
        "cutover_date": date(2023, 1, 31),
        "payload_migration_batch_id": migration_batch_id,
        "opening_event_id": opening_event_id,
        "opening_event_key": world.opening_event_key,
        "opening_event_binding_sha256": opening_event_binding(
            opening_event_id, world.opening_event_key, world.opening_payload_sha256
        ),
        "members": [{"contract_id": str(new_id()), "contract_external_id": world.contract_key}],
        "expected_output_captured": True,
        "obligation_version_ids": [new_id()],
        "capture_operation_id": new_id(),
        "calc_trace_id": new_id(),
        "format_version": 1,
        "node_count": 1,
        "root_measures": {},
        "trace": trace,
        "input_evidence": world.evidence_document,
        "input_evidence_sha256": world.evidence_sha256,
        **_CREATED,
        **extra,
    }
    # batch #7 test-pg return (D-98 133 AMENDMENT 2, B7-LMG-PG-3): the digest covers the row's FINAL
    # identity — format_version, engine_version, trace, root_measures, overrides included — and the
    # actual checking reader accepts it; an explicit ``trace_sha256`` override (a wrong-hash
    # witness) is kept as given
    if "trace_sha256" not in extra:
        row["trace_sha256"] = _trace_sha256(row)
        from erev_api.explain.store import trace_from_row  # local: keeps rows.py import-light

        assert trace_from_row({**row, "id": row["calc_trace_id"]}).sha256() == row["trace_sha256"]
    return row


def _trace_sha256(row: Mapping[str, Any]) -> str:
    """The stored trace hash as ``explain.store`` computes it (DG-KRN-EXP-05): the canonical
    JSON hash of the ``Trace`` rebuilt from the ROW — its ``format_version``, ``engine_version``,
    ``trace`` nodes and ``root_measures`` (the digest covers the engine version, so a placeholder
    version can never match the stored row — batch #7 test-pg return, B7-LMG-PG-3)."""
    from erev_engine.trace import Trace, TraceNode  # local: keeps rows.py import-light

    document = row["trace"]
    nodes = tuple(
        TraceNode(
            id=str(item["id"]),
            measure=str(item["measure"]),
            value=str(item["value"]),
            currency=None if item["currency"] is None else str(item["currency"]),
            formula_id=str(item["formula_id"]),
            inputs=(),
            params={},
            rounding_residue=None
            if item["rounding_residue"] is None
            else str(item["rounding_residue"]),
            narrative_key=str(item["narrative_key"]),
        )
        for item in document["nodes"]
    )
    return Trace(
        format_version=int(row["format_version"]),
        engine_version=str(row["engine_version"]),
        nodes=nodes,
        root_measures={str(k): str(v) for k, v in sorted(dict(row["root_measures"]).items())},
    ).sha256()


def migration_population_version_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    batch_id = _inserted_id(session, migration_batch, migration_batch_row(ctx, session))
    return migration_population_version_values(ctx.tenant_id, migration_batch_id=batch_id)


def migration_population_obligation_values(
    tenant_id: UUID,
    *,
    migration_batch_id: UUID,
    population_version_id: UUID,
    **extra: Any,
) -> dict[str, Any]:
    """T-MIG-05 (rev 1.60): the captured obligation version of Contract 1 POB #1 (WLD-X-27: revenue
    to date 295.69, billed 300.00) bound to its T-MIG-04 row. The retained ``row`` document and its
    ``row_sha256`` are derived from the FINAL typed values through ``capture.canonical_row`` — after
    ``extra`` is applied — so the representation check (``repository._check_row_representation``)
    sees one identity (integrated batch #6 test-pg return (4): the earlier form built the document
    first with its own fresh id, and a caller's ``obligation_version_id`` / ``contract_version_id``
    / ``contract_id`` overrides changed the columns but not the document)."""
    from erev_api.domain.migration.capture import canonical_row
    from support.migration_capture import capture_world

    typed: dict[str, Any] = {
        "tenant_id": tenant_id,
        "id": new_id(),
        "migration_batch_id": migration_batch_id,
        "population_version_id": population_version_id,
        "capture_operation_id": new_id(),
        "contract_version_id": new_id(),
        "obligation_version_id": new_id(),
        "contract_id": new_id(),
        "contract_external_id": capture_world(migration_batch_id).contract_key,
        "obligation_key": "POB #1",
        "obligation_kind": "STANDARD",
        "original_allocated_exact": Decimal("1300"),
        "remaining_quantity": Decimal("0"),
        "billed_cum": Decimal("300.00"),
        "revenue_cum": Decimal("295.69"),
        "remaining_allocation": Decimal("1004.31"),
        "position_obligation": Decimal("4.31"),
        "netting_reclass_amount": Decimal("0.00"),
        "trace_nodes": {"revenue_cum": "revenue_cum:POB #1"},
        **_CREATED,
    }
    overrides = {key: value for key, value in extra.items() if key not in ("row", "row_sha256")}
    typed.update(overrides)
    # the obligation_version row as the capture reads it: its own id and identities, the measures
    # and the node bindings (the stored representation; DG-KRN-EXP-05 / Codex 0440b923 boundary)
    source = {
        "id": typed["obligation_version_id"],
        "contract_version_id": typed["contract_version_id"],
        "contract_id": typed["contract_id"],
        "contract_external_id": typed["contract_external_id"],
        "obligation_key": typed["obligation_key"],
        "obligation_kind": typed["obligation_kind"],
        "original_allocated_exact": Decimal(str(typed["original_allocated_exact"])).quantize(
            Decimal(1).scaleb(-18)
        ),
        "remaining_quantity": Decimal(str(typed["remaining_quantity"])).quantize(
            Decimal(1).scaleb(-18)
        ),
        "billed_cum": typed["billed_cum"],
        "revenue_cum": typed["revenue_cum"],
        "remaining_allocation": typed["remaining_allocation"],
        "position_obligation": typed["position_obligation"],
        "netting_reclass_amount": typed["netting_reclass_amount"],
        "trace_nodes": typed["trace_nodes"],
    }
    document, digest = canonical_row(source)
    typed["row"] = extra.get("row", document)
    typed["row_sha256"] = extra.get("row_sha256", digest)
    return typed


def migration_population_obligation_row(ctx: RowContext, session: Session) -> dict[str, Any]:
    batch_id = _inserted_id(session, migration_batch, migration_batch_row(ctx, session))
    version_id = _inserted_id(
        session,
        migration_population_version,
        migration_population_version_values(ctx.tenant_id, migration_batch_id=batch_id),
    )
    return migration_population_obligation_values(
        ctx.tenant_id, migration_batch_id=batch_id, population_version_id=version_id
    )


ROW_BUILDERS: Final[Mapping[str, RowBuilder]] = MappingProxyType(
    {
        "access_review_campaign": access_review_campaign_row,
        "access_review_item": access_review_item_row,
        "account_mapping_rule": account_mapping_rule_row,
        "account_mapping_version": lambda ctx, _: account_mapping_version_values(ctx.tenant_id),
        "api_client": api_client_row,
        "api_token": api_token_row,
        "approval_decision": approval_decision_row,
        "approval_delegation": approval_delegation_row,
        "approval_request": approval_request_row,
        "approval_step": approval_step_row,
        "control_execution": control_execution_row,
        "audit_chain_head": audit_chain_head_row,
        "audit_chain_verification": audit_chain_verification_row,
        "audit_event": audit_event_row,
        "audit_event_contract": audit_event_contract_row,
        "book": book_row,
        "calc_trace": calc_trace_row,
        "close_checklist_item": close_checklist_item_row,
        "close_checklist_template": lambda ctx, _: close_checklist_template_values(ctx.tenant_id),
        "close_run": close_run_row,
        "combination_group": lambda ctx, _: combination_group_values(ctx.tenant_id),
        "combination_group_member": combination_group_member_row,
        "contract": contract_row,
        "contract_computation": contract_computation_row,
        "contract_event": contract_event_row,
        "contract_hold": contract_hold_row,
        "contract_version": contract_version_row,
        "contract_version_balance": contract_version_balance_row,
        "customer": lambda ctx, _: customer_values(ctx.tenant_id),
        "dimension_definition": dimension_definition_row,
        "dimension_value": dimension_value_row,
        "disclosure_snapshot": disclosure_snapshot_row,
        "estimate": estimate_row,
        "estimate_version": estimate_version_row,
        "entity_book": entity_book_row,
        "event_submission": event_submission_row,
        "evidence_pack": lambda ctx, _: evidence_pack_values(ctx.tenant_id),
        "exception_item": exception_item_row,
        "external_id_map": external_id_map_row,
        "file_attachment": file_attachment_row,
        "file_object": file_object_row,
        "file_upload": file_upload_row,
        "fiscal_calendar": fiscal_calendar_row,
        "fx_rate": fx_rate_row,
        "fx_rate_set": lambda ctx, _: fx_rate_set_values(ctx.tenant_id),
        "fx_rate_set_version": fx_rate_set_version_row,
        "gl_account": gl_account_row,
        "idempotency_record": idempotency_record_row,
        "import_mapping_profile": import_mapping_profile_row,
        "import_row": import_row_row,
        "import_row_lineage": import_row_lineage_row,
        "import_upload": import_upload_row,
        "integration_connection": integration_connection_row,
        "job": job_row,
        "journal_batch": journal_batch_row,
        "journal_entry": journal_entry_row,
        "journal_line": journal_line_row,
        "journal_run": journal_run_row,
        "judgement_record": judgement_record_row,
        "ledger_chain_head": ledger_chain_head_row,
        "legal_entity": legal_entity_row,
        "lock_snapshot": lock_snapshot_row,
        "manual_adjustment": manual_adjustment_row,
        "modification": modification_row,  # T-CON-06 (CTR-17)
        "migrated_legacy_row": migrated_legacy_row_row,
        "migration_population_obligation": migration_population_obligation_row,
        "migration_population_version": migration_population_version_row,
        "migration_batch": migration_batch_row,
        "migration_reconciliation_line": migration_reconciliation_line_row,
        "notification": notification_row,
        "notification_preference": notification_preference_row,
        "numbering_series": numbering_series_row,
        "obligation": obligation_row,
        "obligation_version": obligation_version_row,
        "outbox_message": outbox_message_row,
        "period": period_row,
        "period_lock": period_lock_row,
        "period_state": period_state_row,
        "period_state_transition": period_state_transition_row,
        "pob_template": lambda ctx, _: pob_template_values(ctx.tenant_id),
        "pob_template_version": pob_template_version_row,
        "policy_override": policy_override_row,
        "posting_ack": posting_ack_row,
        "product": lambda ctx, _: product_values(ctx.tenant_id),
        "product_bundle_component": product_bundle_component_row,
        "reconciliation": reconciliation_row,
        "reconciliation_item": reconciliation_item_row,
        "registry_version": registry_version_row,
        "related_party_group": lambda ctx, _: related_party_group_values(ctx.tenant_id),
        "report_run": report_run_row,
        "role": role_row,
        "role_assignment": role_assignment_row,
        "role_permission": role_permission_row,
        "rule": rule_row,
        "rule_set": rule_set_row,
        "rule_set_version": rule_set_version_row,
        "rule_test_case": rule_test_case_row,
        "saved_view": saved_view_row,
        "schedule": schedule_row,
        "schedule_line": schedule_line_row,
        "fx_layer_movement": fx_layer_movement_row,
        "loss_provision_version": loss_provision_version_row,
        "loss_provision_eac": loss_provision_eac_row,
        "signoff": signoff_row,
        "sod_exception": sod_exception_row,
        "sod_rule": sod_rule_row,
        "contract_source_link": contract_source_link_row,
        "source_invoice": source_invoice_row,
        "source_invoice_line": source_invoice_line_row,
        "source_match": source_match_row,
        "source_order": source_order_row,
        "source_order_line": source_order_line_row,
        "source_payment": source_payment_row,
        "source_record": lambda ctx, _: source_record_values(ctx.tenant_id),
        "source_usage": source_usage_row,
        "ssp_book": lambda ctx, _: ssp_book_values(ctx.tenant_id),
        "ssp_book_version": ssp_book_version_row,
        "ssp_calculator_exclusion": ssp_calculator_exclusion_row,
        "ssp_calculator_result": ssp_calculator_result_row,
        "ssp_calculator_run": lambda ctx, _: ssp_calculator_run_values(ctx.tenant_id),
        "ssp_entry": ssp_entry_row,
        "ssp_range": ssp_range_row,
        "subledger_line": subledger_line_row,
        "subledger_line_event": subledger_line_event_row,
        "subledger_posting": subledger_posting_row,
        "subledger_posting_seal": subledger_posting_seal_row,
        "sync_run": sync_run_row,
        "support_grant": lambda ctx, _: support_grant_values(
            ctx.tenant_id, operator_user_id=ctx.user_id
        ),
        "tenant_currency": lambda ctx, _: tenant_currency_values(ctx.tenant_id),
        "tenant_membership": lambda ctx, _: membership_row(ctx),
        "tenant_snapshot": lambda ctx, _: tenant_snapshot_values(ctx.tenant_id),
        "webhook_delivery": webhook_delivery_row,
        "webhook_endpoint": webhook_endpoint_row,
    }
)


def tenant_snapshot_values(tenant_id: UUID, **extra: Any) -> dict[str, Any]:
    """T-PLT-34: a QUEUED STORED_BACKUP snapshot as of 30 Jun 2026 with no target (SNP-1)."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "known_at": datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC),
        "purpose": "STORED_BACKUP",
        "status": RunStatus.QUEUED.value,
        "target_tenant_id": None,
        "manifest_file_id": None,
        "manifest_sha256": None,
        "row_counts": None,
        "job_id": None,
        "started_at": None,
        "finished_at": None,
        **_CREATED,
        **extra,
    }


PROVISIONED_TABLES: Final = frozenset({"audit_chain_head", "book", "ledger_chain_head"})

type RowCompleter = Callable[[RowContext, Session, Mapping[str, Any]], None]
# Tables whose inserted row needs more rows before commit: a posting is sealed over balanced lines
# in its creating transaction (DB-06 (3); CTR-3).
ROW_COMPLETERS: Final[Mapping[str, RowCompleter]] = MappingProxyType(
    {"subledger_line": _seal_probe_line, "subledger_posting": _seal_probe_posting}
)


def support_grant_values(
    tenant_id: UUID,
    *,
    operator_user_id: UUID,
    status: GrantStatus = GrantStatus.REQUESTED,
    valid_from: datetime = INVITED_AT,
    valid_to: datetime = INVITED_AT + timedelta(hours=8),
) -> dict[str, Any]:
    """T-PLT-33: a read-only grant of eight hours for ``operator_user_id``."""
    return {
        "tenant_id": tenant_id,
        "id": new_id(),
        "operator_user_id": operator_user_id,
        "reason": "Investigate export failure",
        "ticket_ref": "SUP-2291",
        "status": status.value,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "approved_at": valid_from if status is GrantStatus.APPROVED else None,
        **_CREATED,
    }


def insert_support_grant(
    session: Session, *, tenant_id: UUID, operator_user_id: UUID, **values: Any
) -> UUID:
    """Insert a ``support_grant`` built by ``support_grant_values``."""
    row = support_grant_values(tenant_id, operator_user_id=operator_user_id, **values)
    session.execute(insert(support_grant).values(**row))
    return UUID(str(row["id"]))


def insert_api_client(session: Session, *, tenant_id: UUID, **values: Any) -> UUID:
    """Insert an ``api_client`` built by ``api_client_values``."""
    row = api_client_values(tenant_id, **values)
    session.execute(insert(api_client).values(**row))
    return UUID(str(row["id"]))


def insert_app_user(bind: Session | Connection, *, email: str | None = None) -> UUID:
    """A global ``app_user`` row (RLS-NONE-U) that builders may reference."""
    user_id = new_id()
    bind.execute(
        insert(app_user).values(
            id=user_id,
            email=email or f"user-{user_id.hex}@rows.test",
            display_name="Row builder user",
            **_SYSTEM,
        )
    )
    return user_id


def insert_role_assignment(
    session: Session,
    *,
    tenant_id: UUID,
    membership_id: UUID,
    role_code: str,
    entity_ids: Sequence[UUID] = (),
    valid_to: datetime | None = None,
    revoked_at: datetime | None = None,
) -> UUID:
    """Assign the tenant's role ``role_code`` to a membership, valid from ``ASSIGNED_FROM``."""
    role_id = session.execute(
        select(role.c.id).where(role.c.tenant_id == tenant_id, role.c.code == role_code)
    ).scalar_one()
    row = assignment_row(
        tenant_id,
        membership_id=membership_id,
        role_id=UUID(str(role_id)),
        entity_ids=entity_ids,
        valid_to=valid_to,
        revoked_at=revoked_at,
    )
    session.execute(insert(role_assignment).values(**row))
    return UUID(str(row["id"]))


def insert_custom_role(
    session: Session, *, tenant_id: UUID, code: str, permissions: Sequence[str]
) -> UUID:
    """Insert an active custom role ``code`` (T-PLT-09) holding exactly ``permissions``
    (T-PLT-12). The default roles hold permissions in bundles — every one with ``import.upload``
    also holds ``contract.read`` — so a rule about ONE permission is witnessed by a member whose
    role holds that one alone."""
    role_id = new_id()
    session.execute(
        insert(role).values(
            tenant_id=tenant_id,
            id=role_id,
            code=code,
            name=code.replace("_", " ").capitalize(),
            is_system=False,
            is_active=True,
            content_sha256=role_content_sha256(permissions),
            **_SYSTEM,
        )
    )
    session.execute(
        insert(role_permission),
        [
            {"tenant_id": tenant_id, "role_id": role_id, "permission_code": permission, **_CREATED}
            for permission in permissions
        ],
    )
    return role_id


def revoke_role_assignments(
    session: Session, *, tenant_id: UUID, membership_id: UUID, at: datetime
) -> None:
    """Revoke every unrevoked assignment of a membership, such as the provisioned ``tenant_admin``
    grant (04 §14.3 item 2), so a test starts from a membership without roles."""
    session.execute(
        update(role_assignment)
        .where(
            role_assignment.c.tenant_id == tenant_id,
            role_assignment.c.membership_id == membership_id,
            role_assignment.c.revoked_at.is_(None),
        )
        .values(revoked_at=at, revoked_by_kind=PrincipalKind.SYSTEM.value)
    )


def insert_sod_rule(session: Session, *, tenant_id: UUID, **values: Any) -> UUID:
    """Insert a ``sod_rule`` version built by ``sod_rule_values``."""
    row = sod_rule_values(tenant_id, **values)
    session.execute(insert(sod_rule).values(**row))
    return UUID(str(row["id"]))


def publish_sod_rule_version(
    session: Session,
    *,
    tenant_id: UUID,
    code: str,
    function_a: Sequence[str],
    function_b: Sequence[str],
    at: datetime,
) -> UUID:
    """Supersede the PUBLISHED version of ``code`` at ``at``, then walk the next version from ``at``
    to PUBLISHED along E-12 with an APPROVED ``ROLE_CHANGE`` request (DB-04; D-80)."""
    current = session.execute(
        select(sod_rule.c.id).where(
            sod_rule.c.tenant_id == tenant_id,
            sod_rule.c.code == code,
            sod_rule.c.status == ConfigStatus.PUBLISHED.value,
        )
    ).scalar_one()
    session.execute(
        update(sod_rule)
        .where(sod_rule.c.id == current)
        .values(status=ConfigStatus.SUPERSEDED.value, effective_to=at)
    )
    version_id, request_id = submit_sod_rule_version(
        session,
        tenant_id=tenant_id,
        code=code,
        function_a=function_a,
        function_b=function_b,
        effective_from=at,
        supersedes_version_id=current,
    )
    where = sod_rule.c.id == version_id
    session.execute(
        update(sod_rule)
        .where(where)
        .values(status=ConfigStatus.APPROVED.value, approval_request_id=request_id)
    )
    session.execute(
        update(sod_rule).where(where).values(status=ConfigStatus.PUBLISHED.value, published_at=at)
    )
    return version_id


def submit_sod_rule_version(
    session: Session,
    *,
    tenant_id: UUID,
    code: str,
    function_a: Sequence[str],
    function_b: Sequence[str],
    request: Mapping[str, Any] = MappingProxyType({}),
    **values: Any,
) -> tuple[UUID, UUID]:
    """Insert the next version of ``code`` DRAFT, walk it to SUBMITTED and record an APPROVED
    ``ROLE_CHANGE`` request of it with the ``request`` columns, as
    ``POST /sod-rules/{code}/versions`` and a decision would (BS1-D-29). Returns the version id
    and the request id."""
    highest = session.execute(
        select(func.max(sod_rule.c.version_no)).where(
            sod_rule.c.tenant_id == tenant_id, sod_rule.c.code == code
        )
    ).scalar_one()
    version_id = insert_sod_rule(
        session,
        tenant_id=tenant_id,
        code=code,
        function_a=function_a,
        function_b=function_b,
        version_no=int(highest or 0) + 1,
        **values,
    )
    where = sod_rule.c.id == version_id
    session.execute(
        update(sod_rule)
        .where(where)
        .values(status=ConfigStatus.TESTED.value, content_sha256=secrets.token_hex(32))
    )
    session.execute(update(sod_rule).where(where).values(status=ConfigStatus.SUBMITTED.value))
    request_id = insert_approval_request(
        session,
        tenant_id=tenant_id,
        status=ApprovalRequestStatus.APPROVED,
        subject_id=version_id,
        **request,
    )
    return version_id, request_id


def insert_file_object(session: Session, *, tenant_id: UUID, **values: Any) -> UUID:
    """Insert a ``file_object`` row built by ``file_object_values``."""
    row = file_object_values(tenant_id, **values)
    session.execute(insert(file_object).values(**row))
    return UUID(str(row["id"]))


def insert_import_upload(
    session: Session, *, tenant_id: UUID, file_object_id: UUID, **values: Any
) -> UUID:
    """Insert an ``import_upload`` built by ``import_upload_values``: an import of the stored
    file, which then owns it (04 T-PLT-29 Read access)."""
    row = import_upload_values(tenant_id, file_object_id=file_object_id, **values)
    session.execute(insert(import_upload).values(**row))
    return UUID(str(row["id"]))


def insert_probe_row(session: Session, table_name: str, ctx: RowContext) -> dict[str, Any]:
    """Insert the catalogue's probe row of ``table_name`` (``ROW_BUILDERS``) with the rows that
    complete it (``ROW_COMPLETERS``), under the session's context; returns the row."""
    row = dict(ROW_BUILDERS[table_name](ctx, session))
    session.execute(insert(metadata.tables[f"erev.{table_name}"]).values(**row))
    complete = ROW_COMPLETERS.get(table_name)
    if complete is not None:
        complete(ctx, session, row)
    return row


def insert_sod_exception(
    session: Session, *, tenant_id: UUID, membership_id: UUID, **values: Any
) -> UUID:
    """Insert a ``sod_exception`` built by ``sod_exception_values``."""
    row = sod_exception_values(tenant_id, membership_id=membership_id, **values)
    session.execute(insert(sod_exception).values(**row))
    return UUID(str(row["id"]))


def insert_active_membership(session: Session, *, tenant_id: UUID, user_id: UUID) -> UUID:
    """An ACTIVE membership of ``user_id``, until invitation acceptance exists as a command."""
    row = membership_row(RowContext(tenant_id, user_id), status=MembershipStatus.ACTIVE)
    session.execute(insert(tenant_membership).values(**row))
    return UUID(str(row["id"]))


def insert_approval_delegation(
    session: Session,
    *,
    tenant_id: UUID,
    delegator_membership_id: UUID,
    delegate_membership_id: UUID,
    valid_from: datetime,
    valid_to: datetime,
    permissions: Sequence[str] = ("contract.approve",),
    revoked_at: datetime | None = None,
    created_at: datetime | None = None,
) -> UUID:
    """A delegation (T-PLT-21) of ``permissions``, created at ``valid_from`` as the command
    creates one that starts at once — or at ``created_at``: before ``valid_from`` for one given
    for a later start, after it for one whose start was dated back — and revoked at
    ``revoked_at`` when given. A row, not the command: a test world states what stands,
    whatever the command would refuse."""
    row = approval_delegation_values(
        tenant_id,
        delegator_membership_id=delegator_membership_id,
        delegate_membership_id=delegate_membership_id,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    row |= {"permissions": list(permissions), "created_at": created_at or valid_from}
    if revoked_at is not None:
        row |= {"revoked_at": revoked_at, "revoked_by_kind": PrincipalKind.SYSTEM.value}
    session.execute(insert(approval_delegation).values(**row))
    return UUID(str(row["id"]))


def insert_approval_request(session: Session, *, tenant_id: UUID, **values: Any) -> UUID:
    """Insert an ``approval_request`` built by ``approval_request_values``."""
    row = approval_request_values(tenant_id, **values)
    session.execute(insert(approval_request).values(**row))
    return UUID(str(row["id"]))


def insert_approval_step(
    session: Session, *, tenant_id: UUID, approval_request_id: UUID, **values: Any
) -> UUID:
    """Insert an ``approval_step`` built by ``approval_step_values``."""
    row = approval_step_values(tenant_id, approval_request_id=approval_request_id, **values)
    session.execute(insert(approval_step).values(**row))
    return UUID(str(row["id"]))
