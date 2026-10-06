"""Tenant provisioning DG-KRN-TEN-01 to 03 (dev-guide §5.20; 04 §14.3; BUILD_SPEC PLF-1, PLF-3,
PLF-4)."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from collections.abc import Mapping
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.adapters.secrets.provision import TenantKeyProvisioningError
from erev_api.audit.verify import verify_tenant_chain
from erev_api.auth.keyring import KeyRing
from erev_api.auth.permissions import DEFAULT_ROLE_NAMES, DEFAULT_ROLES
from erev_api.db.session import DbContext, identity_session, platform_session, tenant_session
from erev_api.db.tables import (
    app_user,
    approval_decision,
    approval_request,
    approval_step,
    audit_chain_head,
    audit_event,
    book,
    close_checklist_template,
    dimension_definition,
    ledger_chain_head,
    numbering_series,
    outbox_message,
    registry_version,
    role,
    role_assignment,
    role_permission,
    rule,
    rule_set,
    rule_set_version,
    security_event,
    sod_rule,
    tenant,
    tenant_currency,
    tenant_membership,
)
from erev_api.domain.close import monitor_rules
from erev_api.domain.platform import provisioning
from erev_api.domain.platform.provisioning import (
    TenantProvisionRequest,
    TenantProvisionResult,
    provision_tenant,
)
from erev_api.enums import ControlResult, RegistryCategory
from erev_api.problems import Problem
from erev_engine.canonical import sha256_hex
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session
from support.clock import frozen_clock
from support.factories import ACME, tenant_factory, tenant_id_of
from support.factories import ACME_ACTOR as ACTOR
from support.links import emailed_token


def test_krn_ten_01_initial_rows(acme: TenantProvisionResult) -> None:
    tenant_id = acme.tenant["id"]
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        row = session.execute(select(tenant).where(tenant.c.id == tenant_id)).mappings().one()
        memberships = session.execute(select(tenant_membership)).mappings().all()
    assert (row["code"], row["kind"], row["status"], row["is_demo"]) == (
        "acme-test",
        "production",
        "ACTIVE",
        False,
    )
    assert row["setup_completed_at"] is None
    assert row["audit_hmac_key_id"] == f"audit-hmac:{tenant_id}:1"
    assert row["created_by_kind"] == "OPERATOR"

    assert len(memberships) == 1
    membership = memberships[0]
    assert membership["id"] == acme.admin_membership_id
    assert membership["status"] == "INVITED"
    assert re.fullmatch(r"[0-9a-f]{64}", membership["invitation_token_sha256"])
    assert membership["invitation_expires_at"] == membership["invited_at"] + timedelta(days=7)
    assert acme.invitation_expires_at == membership["invitation_expires_at"]

    with identity_session(request_id="tests-krn-ten-01") as session:
        user = (
            session.execute(select(app_user).where(app_user.c.id == membership["user_id"]))
            .mappings()
            .one()
        )
        events = session.execute(
            select(
                security_event.c.kind, security_event.c.request_id, security_event.c.detail
            ).where(security_event.c.tenant_id == tenant_id)
        ).all()
    assert (user["email"], user["password_hash"]) == ("admin@acme.test", None)
    assert [tuple(event) for event in events] == [
        ("PLATFORM_SCOPE_USED", "r-12345678", {"scope": "provisioning"})
    ]
    assert dict(acme.tenant) == {
        "id": tenant_id,
        "code": "acme-test",
        "kind": "production",
        "display_name": "Acme Test",
        "reporting_currency": "USD",
        "is_demo": False,
    }


def test_krn_ten_01_first_audit_event(acme: TenantProvisionResult, keyring: KeyRing) -> None:
    tenant_id = acme.tenant["id"]
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        events = (
            session.execute(select(audit_event).order_by(audit_event.c.chain_seq)).mappings().all()
        )
        head = session.execute(select(audit_chain_head)).mappings().one()
        verified = verify_tenant_chain(session, tenant_id=tenant_id, keyring=keyring)
    # ``acme`` lives for the whole session, and a scheduler fan-out another test ran since defers
    # for every ACTIVE tenant: since supervisor ruling R-50 (a) (04 T-PLT-27 rev 1.106) it writes
    # ``job.start`` as SYSTEM in each tenant's chain. The provisioning's events are the first
    # twelve of the chain, in one unbroken sequence; nothing but such fan-out events follows.
    events, later = events[:12], events[12:]
    assert [event["chain_seq"] for event in events] == list(range(1, 13))
    assert {(event["action"], event["actor_kind"]) for event in later} <= {("job.start", "SYSTEM")}
    # PLF-13 and PLF-12: the DEFAULT registry versions, then the bootstrap admin grant, follow the
    # provisioning event.
    assert [event["action"] for event in events] == [
        "tenant.provision",
        *["registry_version.seed"] * 8,
        "approval_request.submit",
        "approval_request.auto_approve",
        "role_assignment.create",
    ]
    assert [event["actor_kind"] for event in events] == [
        "OPERATOR",
        *["SYSTEM"] * 8,
        *["OPERATOR"] * 3,
    ]
    first = events[0]
    assert (first["action"], first["chain_seq"], first["actor_kind"], first["detail"]) == (
        "tenant.provision",
        1,
        "OPERATOR",
        {"channel": "CLI", "os_user": "builder"},
    )
    assert (first["object_type"], first["object_id"], first["request_id"]) == (
        "tenant",
        tenant_id,
        "r-12345678",
    )
    assert first["prev_hmac"] is None
    assert first["hmac_key_id"] == f"audit-hmac:{tenant_id}:1"
    assert first["after"]["code"] == "acme-test"
    last = (later or events)[-1]
    assert (head["last_chain_seq"], head["last_hmac"]) == (12 + len(later), last["hmac"])
    assert (verified.result, verified.events_checked) == (ControlResult.PASS, 12 + len(later))


def test_krn_ten_01_registry_defaults(acme: TenantProvisionResult) -> None:
    tenant_id = acme.tenant["id"]
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        rows = session.execute(select(registry_version)).mappings().all()
        events = (
            session.execute(
                select(audit_event)
                .where(audit_event.c.action == "registry_version.seed")
                .order_by(audit_event.c.chain_seq)
            )
            .mappings()
            .all()
        )
    assert len(rows) == 8
    assert sorted(row["category"] for row in rows) == sorted(
        item.value for item in RegistryCategory
    )
    for row in rows:
        assert (row["scope"], row["status"], row["preset_code"], row["values"]) == (
            "TENANT",
            "PUBLISHED",
            "DEFAULT",
            {},
        ), row["category"]
        assert (row["version_no"], row["book_code"], row["entity_id"]) == (1, None, None)
        assert (row["effective_from"], row["effective_to"], row["approval_request_id"]) == (
            None,
            None,
            None,
        )
        assert (row["created_by_kind"], row["published_by"], row["published_at"]) == (
            "SYSTEM",
            None,
            frozen_clock().now(),
        )
        assert re.fullmatch(r"[0-9a-f]{64}", row["content_sha256"])
    assert len(events) == 8
    assert {event["object_id"] for event in events} == {row["id"] for row in rows}
    for event in events:
        assert (event["actor_kind"], event["actor_id"], event["object_type"]) == (
            "SYSTEM",
            None,
            "registry_version",
        )
        assert (event["after"]["preset_code"], event["after"]["values"]) == ("DEFAULT", {})


def test_krn_ten_01_auto_bootstrap_rows(acme: TenantProvisionResult) -> None:
    tenant_id = acme.tenant["id"]
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        sets = session.execute(select(rule_set)).mappings().all()
        versions = session.execute(select(rule_set_version)).mappings().all()
        rules = session.execute(select(rule)).mappings().all()
        assignments = (
            session.execute(
                select(role_assignment, role.c.code.label("role_code")).join(
                    role,
                    and_(
                        role.c.tenant_id == role_assignment.c.tenant_id,
                        role.c.id == role_assignment.c.role_id,
                    ),
                )
            )
            .mappings()
            .all()
        )
        request = session.execute(select(approval_request)).mappings().one()
        decision = session.execute(select(approval_decision)).mappings().one()
        steps = session.execute(select(approval_step.c.step_no, approval_step.c.status)).all()

    # 04 §14.3 item 2: AUTO-BOOTSTRAP, the DQ-SYSTEM data-quality set (rev 1.21; CLO-5) and the
    # AUTO-MIG-01 legacy SSP replay auto-approval (rev 1.72; D-98 133 AMENDMENT 4) are seeded.
    assert sorted((row["code"], row["kind"]) for row in sets) == [
        ("AUTO-BOOTSTRAP", "AUTO_APPROVAL"),
        ("AUTO-MIG-01", "AUTO_APPROVAL"),
        ("DQ-SYSTEM", "DATA_QUALITY"),
    ]
    bootstrap_set = next(row for row in sets if row["code"] == "AUTO-BOOTSTRAP")
    dq_set = next(row for row in sets if row["code"] == "DQ-SYSTEM")
    mig_set = next(row for row in sets if row["code"] == "AUTO-MIG-01")
    assert len(versions) == 3
    # 04 §14.3 rev 1.72: 'rule_set code AUTO-MIG-01, kind AUTO_APPROVAL, name "Legacy SSP replay",
    # with version 1 PUBLISHED and one rule whose rule_key is AUTO-MIG-01. Its conditions are
    # subject.type eq MIGRATION_SSP_REPLAY and source.channel eq USER; its output is
    # {"auto_approve": true}'.
    assert mig_set["name"] == "Legacy SSP replay"
    mig_version = next(row for row in versions if row["rule_set_id"] == mig_set["id"])
    assert (mig_version["kind"], mig_version["version_no"], mig_version["status"]) == (
        "AUTO_APPROVAL",
        1,
        "PUBLISHED",
    )
    assert mig_version["published_at"] == frozen_clock().now()
    assert re.fullmatch(r"[0-9a-f]{64}", mig_version["content_sha256"])
    (mig_rule,) = [row for row in rules if row["rule_set_version_id"] == mig_version["id"]]
    assert (mig_rule["rule_key"], mig_rule["specificity"]) == ("AUTO-MIG-01", 2)
    assert mig_rule["conditions"] == [
        {"field": "subject.type", "op": "eq", "value": "MIGRATION_SSP_REPLAY"},
        {"field": "source.channel", "op": "eq", "value": "USER"},
    ]
    assert mig_rule["outputs"] == {"auto_approve": True}
    dq_version = next(row for row in versions if row["rule_set_id"] == dq_set["id"])
    assert (dq_version["kind"], dq_version["version_no"], dq_version["status"]) == (
        "DATA_QUALITY",
        1,
        "PUBLISHED",
    )
    dq_rules = sorted(
        (row for row in rules if row["rule_set_version_id"] == dq_version["id"]),
        key=lambda row: row["rule_key"],
    )
    assert [row["rule_key"] for row in dq_rules] == sorted(m.code for m in monitor_rules.MONITORS)
    assert all(row["conditions"] == [] and row["specificity"] == 0 for row in dq_rules)
    assert {row["outputs"]["severity"] for row in dq_rules} == {"ERROR", "WARNING"}
    versions = [row for row in versions if row["rule_set_id"] == bootstrap_set["id"]]
    rules = [row for row in rules if row["rule_set_version_id"] == versions[0]["id"]]
    sets = [bootstrap_set]
    version = versions[0]
    assert (version["rule_set_id"], version["kind"], version["version_no"], version["status"]) == (
        sets[0]["id"],
        "AUTO_APPROVAL",
        1,
        "PUBLISHED",
    )
    assert version["published_at"] == frozen_clock().now()
    assert re.fullmatch(r"[0-9a-f]{64}", version["content_sha256"])
    assert len(rules) == 1
    bootstrap = rules[0]
    assert (bootstrap["rule_set_version_id"], bootstrap["rule_key"], bootstrap["specificity"]) == (
        version["id"],
        "AUTO-BOOTSTRAP",
        3,
    )
    assert bootstrap["conditions"] == [
        {"field": "subject.type", "op": "eq", "value": "ROLE_ASSIGNMENT"},
        {"field": "preparer.role_codes", "op": "in", "value": ["tenant_admin"]},
        {"field": "tenant.setup_completed", "op": "eq", "value": False},
    ]
    assert bootstrap["outputs"] == {"auto_approve": True}

    assert len(assignments) == 1
    grant = assignments[0]
    assert (grant["membership_id"], grant["role_code"], grant["is_all_entities"]) == (
        acme.admin_membership_id,
        "tenant_admin",
        True,
    )
    assert (grant["entity_ids"], grant["approval_request_id"]) == ([], request["id"])
    assert (request["subject_type"], request["subject_id"], request["status"]) == (
        "ROLE_ASSIGNMENT",
        grant["id"],
        "APPROVED",
    )
    assert (request["request_no"], request["preparer_kind"], request["preparer_id"]) == (
        "APR-000001",
        "SYSTEM",
        None,
    )
    assert (decision["decision"], decision["approver_kind"], decision["approver_id"]) == (
        "AUTO_APPROVE",
        "SYSTEM",
        None,
    )
    assert (decision["auto_rule_set_version_id"], decision["auto_rule_id"]) == (
        version["id"],
        bootstrap["id"],
    )
    assert decision["subject_content_sha256"] == request["subject_content_sha256"]
    assert [tuple(step) for step in steps] == [(1, "APPROVED")]


def test_provision_builtin_dimensions(acme: TenantProvisionResult) -> None:
    # 04 §14.3 and T-REF-16 (RFD-6): the five built-in dimensions in positions 1 to 5.
    tenant_id = acme.tenant["id"]
    columns = (
        dimension_definition.c.code,
        dimension_definition.c.name,
        dimension_definition.c.is_builtin,
        dimension_definition.c.position,
        dimension_definition.c.is_active,
        dimension_definition.c.created_by_kind,
    )
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        rows = session.execute(
            select(*columns)
            .where(dimension_definition.c.is_builtin)
            .order_by(dimension_definition.c.position)
        ).all()
    assert [tuple(row) for row in rows] == [
        ("department", "Department", True, 1, True, "OPERATOR"),
        ("class", "Class", True, 2, True, "OPERATOR"),
        ("location", "Location", True, 3, True, "OPERATOR"),
        ("product", "Product", True, 4, True, "OPERATOR"),
        ("customer", "Customer", True, 5, True, "OPERATOR"),
    ]


def test_provision_creates_three_books(acme: TenantProvisionResult) -> None:
    # 04 §14.3 and T-REF-02 (RFD-2; REQ-BK-001): ASC606 primary and enabled on the primary ledger;
    # IFRS15 disabled on a secondary ledger; LEGACY disabled, posting nothing.
    tenant_id = acme.tenant["id"]
    columns = (
        book.c.code,
        book.c.name,
        book.c.is_primary,
        book.c.is_enabled,
        book.c.posting_target,
        book.c.created_by_kind,
    )
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        rows = session.execute(select(*columns).order_by(book.c.code)).all()
    assert [tuple(row) for row in rows] == [
        ("ASC606", "ASC 606", True, True, "GL_PRIMARY", "OPERATOR"),
        ("IFRS15", "IFRS 15", False, False, "GL_SECONDARY", "OPERATOR"),
        ("LEGACY", "Legacy", False, False, "NONE", "OPERATOR"),
    ]


def test_provision_creates_ledger_chain_heads(acme: TenantProvisionResult) -> None:
    # 04 §14.3 and T-SL-03 (CTR-3; BS-D-12): one ledger chain head per book, before any seal.
    tenant_id = acme.tenant["id"]
    columns = (
        ledger_chain_head.c.book_code,
        ledger_chain_head.c.last_chain_seq,
        ledger_chain_head.c.last_seal_sha256,
    )
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        rows = session.execute(select(*columns).order_by(ledger_chain_head.c.book_code)).all()
    assert [tuple(row) for row in rows] == [
        ("ASC606", 0, None),
        ("IFRS15", 0, None),
        ("LEGACY", 0, None),
    ]


def test_provision_creates_system_close_checklist(acme: TenantProvisionResult) -> None:
    # 04 §14.3 and T-CLS-02 (CLO-2; BS-D-12): one automatic, blocking system template per gate
    # check code, in the T-CLS-02 order, labelled as in SCREENS_B §1.1 and without an owner role or
    # due offset.
    tenant_id = acme.tenant["id"]
    template = close_checklist_template
    columns = (
        template.c.sequence,
        template.c.code,
        template.c.gate_check_code,
        template.c.name,
        template.c.gate_kind,
        template.c.is_blocking,
        template.c.is_active,
        template.c.owner_role_id,
        template.c.due_offset_days,
        template.c.created_by_kind,
    )
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        rows = session.execute(
            select(*columns).where(template.c.is_system).order_by(template.c.sequence)
        ).all()
        total = session.execute(select(func.count()).select_from(template)).scalar_one()
    # 04 T-CLS-02 rev 1.172 (item CLO-GATE-RUN-1; supervisor rulings R-114 (b), R-116 (e)): fourteen
    # system gates; CLOSE_RUN_COMPLETED is the thirteenth and the certification stays the last.
    assert total == len(rows) == 14
    assert [row.gate_check_code for row in rows] == [
        "INTERFACES_COMPLETE",
        "JE_BALANCED",
        "JE_COMPLETE",
        "APPROVALS_CLEARED",
        "EXCEPTIONS_CLEARED",
        "HOLDS_REVIEWED",
        "BATCHES_ACKNOWLEDGED",
        "RECONCILIATIONS_GENERATED",
        "JUDGEMENTS_REVIEWED",
        "DATA_QUALITY_CLEAR",
        "NO_DIRTY_GROUPS",
        "MANUAL_ADJUSTMENTS_CLEARED",
        "CLOSE_RUN_COMPLETED",
        "CONTROLLER_CERTIFIED",
    ]
    assert [row.sequence for row in rows] == list(range(1, 15))
    assert all(row.code == row.gate_check_code for row in rows)
    assert (rows[0].name, rows[7].name, rows[12].name, rows[13].name) == (
        "Interface batches complete",
        "Reconciliations generated and reviewed",
        "Close run completed",
        "Controller certification",
    )
    assert {
        (
            row.gate_kind,
            row.is_blocking,
            row.is_active,
            row.owner_role_id,
            row.due_offset_days,
            row.created_by_kind,
        )
        for row in rows
    } == {("AUTOMATIC", True, True, None, None, "OPERATOR")}


def test_provision_enables_reporting_currency(
    acme: TenantProvisionResult, keyring: KeyRing
) -> None:
    # 04 §14.3 and T-REF-09 (RFD-3; REQ-REF-004): `erev tenant create --reporting-currency USD`
    # provisions through provision_tenant, which enables the reporting currency and nothing else.
    columns = (
        tenant_currency.c.currency_code,
        tenant_currency.c.is_enabled,
        tenant_currency.c.created_by_kind,
    )
    assert acme.tenant["reporting_currency"] == "USD"
    with tenant_session(
        DbContext(tenant_id=acme.tenant["id"], user_id=None, entity_scope="*")
    ) as session:
        rows = session.execute(select(*columns)).all()
    assert [tuple(row) for row in rows] == [("USD", True, "OPERATOR")]

    code = f"t-{secrets.token_hex(6)}"
    euro = TenantProvisionRequest(
        code=code,
        display_name="Euro workspace",
        reporting_currency="EUR",
        is_demo=False,
        admin_email=f"admin@{code}.test",
    )
    result = provision_tenant(euro, actor=ACTOR, clock=frozen_clock(), keyring=keyring)
    with tenant_session(
        DbContext(tenant_id=result.tenant["id"], user_id=None, entity_scope="*")
    ) as session:
        rows = session.execute(select(*columns)).all()
    assert [tuple(row) for row in rows] == [("EUR", True, "OPERATOR")]


def test_krn_ten_01_numbering_series(acme: TenantProvisionResult) -> None:
    tenant_id = acme.tenant["id"]
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        rows = session.execute(select(numbering_series)).mappings().all()
    assert len(rows) == 13
    assert "JE" not in {row["series_code"] for row in rows}
    assert sorted(row["prefix"] for row in rows) == sorted(
        ["CON-", "MOD-", "APR-", "IMP-", "JR-", "ADJ-", "REC-", "RPT-", "CLS-", "EXC-", "EVP-"]
        + ["MIG-", "JDG-"]
    )
    for row in rows:
        # The bootstrap admin grant took APR-000001 (04 §14.3 item 2).
        first_free = 2 if row["series_code"] == "APPROVAL" else 1
        assert (row["next_value"], row["padding"], row["is_gapless"], row["scope_key"]) == (
            first_free,
            6,
            False,
            "",
        ), row["series_code"]
        assert row["updated_by_kind"] == "OPERATOR"


def _identity_counts() -> tuple[int, int]:
    with identity_session(request_id="tests-krn-ten-02-counts") as session:
        users = session.execute(select(func.count()).select_from(app_user)).scalar_one()
        events = session.execute(select(func.count()).select_from(security_event)).scalar_one()
    return int(users), int(events)


def _directory_tenant_count() -> int:
    with platform_session(
        "tenant_directory", actor_user_id=None, request_id="tests-krn-ten-02-directory"
    ) as session:
        return int(session.execute(select(func.count()).select_from(tenant)).scalar_one())


def test_krn_ten_02_existing_code_rejected(acme: TenantProvisionResult, keyring: KeyRing) -> None:
    users_before, events_before = _identity_counts()
    tenants_before = _directory_tenant_count()
    with pytest.raises(Problem) as excinfo:
        provision_tenant(ACME, actor=ACTOR, clock=frozen_clock(), keyring=keyring)
    tenants_after = _directory_tenant_count()
    users_after, events_after = _identity_counts()

    problem = excinfo.value
    assert (problem.slug, problem.status) == ("validation-failed", 422)
    assert [(error.field, error.rule_id) for error in problem.errors] == [
        ("code", "TENANT_CODE_EXISTS")
    ]
    assert tenants_after == tenants_before
    assert users_after == users_before
    # Only the two directory reads wrote security events; the failed provisioning wrote none.
    assert events_after == events_before + 2


def test_krn_ten_03_validation_collects_all_fields(keyring: KeyRing) -> None:
    request = TenantProvisionRequest(
        code="Acme_Test",
        display_name="Acme Test",
        reporting_currency="XYZ",
        is_demo=False,
        admin_email="not-an-email",
    )
    with pytest.raises(Problem) as excinfo:
        provision_tenant(request, actor=ACTOR, clock=frozen_clock(), keyring=keyring)
    assert (excinfo.value.slug, excinfo.value.status) == ("validation-failed", 422)
    assert [error.field for error in excinfo.value.errors] == [
        "code",
        "reporting_currency",
        "admin_email",
    ]


def test_krn_ten_01_default_roles(acme: TenantProvisionResult) -> None:
    tenant_id = acme.tenant["id"]
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        roles = session.execute(select(role)).mappings().all()
        pairs = session.execute(
            select(role.c.code, role_permission.c.permission_code).join(
                role_permission,
                and_(
                    role_permission.c.tenant_id == role.c.tenant_id,
                    role_permission.c.role_id == role.c.id,
                ),
            )
        ).all()
    granted: dict[str, set[str]] = {}
    for code, permission_code in pairs:
        granted.setdefault(str(code), set()).add(str(permission_code))

    assert sorted(row["code"] for row in roles) == sorted(DEFAULT_ROLES)
    assert all(row["is_system"] is True and row["is_active"] is True for row in roles)
    assert {row["code"]: row["name"] for row in roles} == dict(DEFAULT_ROLE_NAMES)
    assert {code: len(codes) for code, codes in granted.items()} == {
        "revenue_accountant": 24,
        "revenue_reviewer": 19,
        "controller": 26,
        "ssp_analyst": 5,
        "ssp_approver": 5,
        "integration_admin": 10,
        "tenant_admin": 10,
        "auditor": 7,
        "viewer": 6,
        "service_account": 5,
    }
    for row in roles:
        assert row["content_sha256"] == sha256_hex(sorted(granted[row["code"]]))


# BUILD_SPEC BS1-D-26: names, function A and function B of SoD-2 to SoD-7.
SOD_RULES = {
    "SoD-2": ("creating and approving the same SSP book version", {"ssp.create"}, {"ssp.approve"}),
    "SoD-3": (
        "Revenue Accountant with Revenue Reviewer lets one person create and approve the same "
        "contract or modification",
        {
            "contract.create",
            "modification.create",
            "event.record",
            "estimate.create",
            "judgement.create",
            "adjustment.create",
            "import.upload",
        },
        {
            "contract.approve",
            "modification.approve",
            "event.approve",
            "estimate.approve",
            "judgement.review",
            "adjustment.approve",
            "import.approve",
        },
    ),
    "SoD-4": (
        "preparing manual adjustments or journal runs with locking periods",
        {"adjustment.create", "journal.run"},
        {"period.lock"},
    ),
    "SoD-5": (
        "authoring and approving the same configuration",
        {"config.author"},
        {"config.approve"},
    ),
    "SoD-6": (
        "preparing postings with locking or reopening periods",
        {"import.upload"},
        {"period.lock"},
    ),
    "SoD-7": (
        "managing integrations with signing reconciliations",
        {"integration.manage"},
        {"recon.signoff"},
    ),
}


def test_krn_ten_01_sod_rules_seeded(acme: TenantProvisionResult) -> None:
    tenant_id = acme.tenant["id"]
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        rows = session.execute(select(sod_rule).order_by(sod_rule.c.code)).mappings().all()
    assert [row["code"] for row in rows] == [f"SoD-{n}" for n in range(1, 8)]
    for row in rows:
        assert (row["version_no"], row["status"]) == (1, "PUBLISHED"), row["code"]
        assert row["published_at"] == frozen_clock().now()
        assert re.fullmatch(r"[0-9a-f]{64}", row["content_sha256"])
        assert row["function_a_permissions"] == sorted(row["function_a_permissions"])
    sod_1 = rows[0]
    assert sod_1["name"] == "user administration with transaction or approval permissions"
    assert set(sod_1["function_a_permissions"]) == {
        "user.manage",
        "role.manage",
        "access.approve",
        "support_grant.approve",
        "settings.manage",
        "api_client.manage",
    }
    assert len(sod_1["function_b_permissions"]) == 33
    assert {"contract.create", "migration.approve", "period.lock"} <= set(
        sod_1["function_b_permissions"]
    )
    assert {
        row["code"]: (
            row["name"],
            set(row["function_a_permissions"]),
            set(row["function_b_permissions"]),
        )
        for row in rows[1:]
    } == SOD_RULES


def test_krn_ten_01_invitation_outbox(acme: TenantProvisionResult) -> None:
    tenant_id = acme.tenant["id"]
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        messages = session.execute(select(outbox_message)).mappings().all()
        token_sha256 = session.execute(
            select(tenant_membership.c.invitation_token_sha256)
        ).scalar_one()
    assert len(messages) == 1
    message = messages[0]
    assert (
        message["topic"],
        message["aggregate_type"],
        message["aggregate_id"],
        message["dedupe_key"],
        message["created_by_kind"],
    ) == (
        "EMAIL",
        "tenant_membership",
        acme.admin_membership_id,
        f"invitation:{acme.admin_membership_id}",
        "OPERATOR",
    )
    payload = message["payload"]
    assert (
        payload["to"],
        payload["subject"],
        payload["reference"],
        payload["notification_id"],
    ) == (
        "admin@acme.test",
        "You are invited to Acme Test on eRev",
        str(acme.admin_membership_id),
        None,
    )
    assert "The invitation expires on 19 Sep 2026 at 12:00 UTC." in payload["text"]
    # The email's link carries the token; the row holds neither the token nor its hash: it
    # names the token by reference (04 §14.3 item 2; T-INT-03 ``payload`` rev 1.151).
    assert payload["link_path"] == "/accept-invitation#token={token}"
    token = emailed_token(payload, prefix="/accept-invitation#token=")
    assert hashlib.sha256(token.encode("ascii")).hexdigest() == token_sha256
    assert token_sha256 not in json.dumps(payload)


def _seed_counts(tenant_id: UUID) -> dict[str, int]:
    """Rows of every PLF provisioning row of PHASES §5.3 visible in the tenant's context."""
    filters: Mapping[str, Any] = {
        "tenant": select(func.count()).select_from(tenant),
        "audit_chain_head": select(func.count()).select_from(audit_chain_head),
        "numbering_series": select(func.count()).select_from(numbering_series),
        "role": select(func.count()).select_from(role),
        "role_permission": select(func.count()).select_from(role_permission),
        "sod_rule": select(func.count())
        .select_from(sod_rule)
        .where(sod_rule.c.status == "PUBLISHED"),
        "registry_version": select(func.count())
        .select_from(registry_version)
        .where(registry_version.c.preset_code == "DEFAULT"),
        "dimension_definition": select(func.count())
        .select_from(dimension_definition)
        .where(dimension_definition.c.is_builtin),
        "book": select(func.count()).select_from(book),
        "ledger_chain_head": select(func.count()).select_from(ledger_chain_head),
        "close_checklist_template": select(func.count())
        .select_from(close_checklist_template)
        .where(close_checklist_template.c.is_system),
        "tenant_currency": select(func.count()).select_from(tenant_currency),
        "rule_set": select(func.count())
        .select_from(rule_set)
        .where(rule_set.c.code == "AUTO-BOOTSTRAP"),
        "rule": select(func.count()).select_from(rule).where(rule.c.rule_key == "AUTO-BOOTSTRAP"),
        "tenant_membership": select(func.count())
        .select_from(tenant_membership)
        .where(tenant_membership.c.status == "INVITED"),
        "role_assignment": select(func.count()).select_from(role_assignment),
        "approval_decision": select(func.count())
        .select_from(approval_decision)
        .where(approval_decision.c.decision == "AUTO_APPROVE"),
        "outbox_message": select(func.count())
        .select_from(outbox_message)
        .where(outbox_message.c.topic == "EMAIL"),
        "audit_event": select(func.count())
        .select_from(audit_event)
        .where(audit_event.c.action == "tenant.provision"),
    }
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        return {name: int(session.execute(query).scalar_one()) for name, query in filters.items()}


def _identity_rows(tenant_id: UUID, email: str) -> tuple[int, list[str]]:
    """The users of ``email`` and the security event kinds naming the tenant."""
    with identity_session(request_id="tests-krn-ten-01-identity") as session:
        users = session.execute(
            select(func.count()).select_from(app_user).where(app_user.c.email == email)
        ).scalar_one()
        kinds = session.execute(
            select(security_event.c.kind).where(security_event.c.tenant_id == tenant_id)
        ).scalars()
        return int(users), [str(kind) for kind in kinds]


def test_krn_ten_01_every_plf_seed_row(keyring: KeyRing, monkeypatch: pytest.MonkeyPatch) -> None:
    code = f"t-{secrets.token_hex(6)}"
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring, code=code))
    assert _seed_counts(tenant_id) == {
        "tenant": 1,
        "audit_chain_head": 1,
        "numbering_series": 13,
        "role": 10,
        "role_permission": sum(len(codes) for codes in DEFAULT_ROLES.values()),
        "sod_rule": 7,
        "registry_version": 8,
        "dimension_definition": 5,
        "book": 3,
        "ledger_chain_head": 3,
        "close_checklist_template": 14,  # 04 T-CLS-02 rev 1.172: CLOSE_RUN_COMPLETED
        "tenant_currency": 1,
        "rule_set": 1,
        "rule": 1,
        "tenant_membership": 1,
        "role_assignment": 1,
        "approval_decision": 1,
        "outbox_message": 1,
        "audit_event": 1,
    }
    assert _identity_rows(tenant_id, f"admin@{code}.test") == (1, ["PLATFORM_SCOPE_USED"])

    # An exception after the registry versions are written rolls the whole transaction back.
    named: list[UUID] = []
    name_tenant = provisioning.name_platform_tenant

    def record_name(session: Session, new_tenant_id: UUID) -> None:
        named.append(new_tenant_id)
        name_tenant(session, new_tenant_id)

    def fail_after_registry(*args: object, **kwargs: object) -> None:
        raise RuntimeError("injected after the registry versions")

    monkeypatch.setattr(provisioning, "name_platform_tenant", record_name)
    monkeypatch.setattr(provisioning, "_grant_bootstrap_admin", fail_after_registry)
    failed_code = f"t-{secrets.token_hex(6)}"
    with pytest.raises(RuntimeError, match="injected after the registry versions"):
        tenant_factory(keyring=keyring, code=failed_code)
    assert len(named) == 1
    assert set(_seed_counts(named[0]).values()) == {0}
    assert _identity_rows(named[0], f"admin@{failed_code}.test") == (0, [])
    with platform_session(
        "tenant_directory", actor_user_id=None, request_id="tests-krn-ten-01-directory"
    ) as session:
        remaining = session.execute(
            select(func.count()).select_from(tenant).where(tenant.c.code == failed_code)
        ).scalar_one()
    assert remaining == 0


# ---- lane P2: the KEY-05 provisioning authority runs before any row (hosted runtime contract) --


class RecordingKeyProvisioner:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[UUID] = []
        self.fail = fail

    def provision_audit_key(self, tenant_id: UUID) -> str:
        self.calls.append(tenant_id)
        if self.fail:
            raise TenantKeyProvisioningError(
                "denied", f"erev-audit-hmac-{tenant_id}", "create_secret"
            )
        return f"audit-hmac:{tenant_id}:1"


def test_p2_key_provisioner_runs_before_any_row_and_fails_closed(keyring: KeyRing) -> None:
    request = TenantProvisionRequest(
        code="p2-hosted",
        display_name="P2 Hosted",
        reporting_currency="USD",
        is_demo=False,
        admin_email="p2-admin@demo.erev",
    )
    tenants_before = _directory_tenant_count()
    failing = RecordingKeyProvisioner(fail=True)
    with pytest.raises(TenantKeyProvisioningError):
        provision_tenant(
            request, actor=ACTOR, clock=frozen_clock(), keyring=keyring, key_provisioner=failing
        )
    assert len(failing.calls) == 1
    assert _directory_tenant_count() == tenants_before, "no tenant row without a readable key"

    recording = RecordingKeyProvisioner()
    result = provision_tenant(
        request, actor=ACTOR, clock=frozen_clock(), keyring=keyring, key_provisioner=recording
    )
    tenant_id = UUID(str(result.tenant["id"]))
    assert recording.calls == [tenant_id]
    # The tenant row is visible in its own tenant context (RLS-TN), as the other rows tests read it.
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        stored = session.execute(
            select(tenant.c.audit_hmac_key_id).where(tenant.c.id == tenant_id)
        ).scalar_one()
    assert stored == f"audit-hmac:{tenant_id}:1"
    # A repeated request with the same code creates nothing anywhere: no row and no key.
    with pytest.raises(Problem) as excinfo:
        provision_tenant(
            request, actor=ACTOR, clock=frozen_clock(), keyring=keyring, key_provisioner=recording
        )
    assert [error.rule_id for error in excinfo.value.errors] == ["TENANT_CODE_EXISTS"]
    assert recording.calls == [tenant_id], "the provisioner never ran for the duplicate"
