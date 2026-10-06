"""Notifications (dev-guide §5.11 DG-KRN-EVT-06; 04 T-PLT-24, T-PLT-25, §14.3 item 4; 05 NTR-01 to
NTR-04, SBX-08 rev 1.116; PRD §5.4 NTF-01 to NTF-04, NTF-R1, NTF-R2; BUILD_SPEC PLF-14, SNP-4).

The world is a tenant with three ACTIVE members who each hold ``tenant_admin`` and so
``access.approve``: a preparer and two approvers.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals.engine import decide, submit, void_if_stale
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import Principal, RequestContext, system_principal
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import notification, notification_preference, outbox_message
from erev_api.domain.platform.memberships import on_membership_activated
from erev_api.enums import ApprovalSubjectType, NotificationKind, PrincipalKind, TenantKind
from erev_api.events.notifications import notify
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime, system_unit_of_work
from erev_api.uow import UnitOfWork, unit_of_work
from sqlalchemy import exc, select, update
from support.db import TestDatabase
from support.factories import tenant_factory, tenant_id_of
from support.rows import insert_active_membership, insert_app_user, insert_role_assignment
from support.snapshots import seeded_sandbox
from support.subjects import ProbeSubjects, install

MFA_VERIFIED_AT = datetime(2026, 9, 12, 11, 58, tzinfo=UTC)
PERMISSION = "access.approve"
SUBJECT = ApprovalSubjectType.ROLE_CHANGE
SUMMARY = "Change the access approver role"
# PRD §5.4 NTF-04 body.
VOIDED_BODY = (
    "The item changed after submission, so the approval request was voided. "
    "Resubmit to route it again."
)

Run = Callable[[Principal], AbstractContextManager[UnitOfWork]]


@dataclass(frozen=True, slots=True)
class World:
    tenant_id: UUID
    preparer: Principal
    approver_a: Principal
    approver_b: Principal


def _all_entities(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


def _person(tenant_id: UUID, user_id: UUID, membership_id: UUID, name: str) -> Principal:
    scopes: dict[str, Any] = {PERMISSION: "*"}
    return Principal(
        kind=PrincipalKind.USER,
        id=user_id,
        tenant_id=tenant_id,
        membership_id=membership_id,
        display_name=name,
        roles=("tenant_admin",),
        permissions=frozenset(scopes),
        permission_scopes=MappingProxyType(scopes),
        entity_scope="*",
        auth_method="password",
        mfa_verified_at=MFA_VERIFIED_AT,
        session_id=None,
        support_grant_id=None,
        on_behalf_of_id=None,
    )


@pytest.fixture
def world(committed_db: TestDatabase, keyring: KeyRing, clock: FrozenClock) -> World:
    tenant_id = tenant_id_of(tenant_factory(keyring=keyring, clock=clock))
    with tenant_session(_all_entities(tenant_id)) as session:
        people = []
        for name in ("Maya Preparer", "Priya Approver", "Marcus Approver"):
            user_id = insert_app_user(session)
            membership_id = insert_active_membership(session, tenant_id=tenant_id, user_id=user_id)
            insert_role_assignment(
                session, tenant_id=tenant_id, membership_id=membership_id, role_code="tenant_admin"
            )
            people.append(_person(tenant_id, user_id, membership_id, name))
    return World(
        tenant_id=tenant_id, preparer=people[0], approver_a=people[1], approver_b=people[2]
    )


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch) -> ProbeSubjects:
    subjects = ProbeSubjects()
    install(monkeypatch, subjects.spec(SUBJECT))
    return subjects


@pytest.fixture
def run(clock: FrozenClock, keyring: KeyRing, app_settings: Settings) -> Run:
    @contextmanager
    def open_uow(principal: Principal) -> Iterator[UnitOfWork]:
        ctx = RequestContext(
            principal=principal,
            tenant_kind=TenantKind.PRODUCTION,
            request_id="tests-notifications",
            source_ip=None,
            user_agent=None,
            idempotency_key=None,
            if_match=None,
            now=clock.now(),
            format_locale="en-US",
        )
        files = LocalFileStore(app_settings.file_root)
        with unit_of_work(ctx, clock=clock, keyring=keyring, files=files) as uow:
            yield uow

    return open_uow


def _membership(principal: Principal) -> UUID:
    assert principal.membership_id is not None
    return principal.membership_id


def _notifications(tenant_id: UUID, kind: NotificationKind) -> list[Mapping[str, Any]]:
    with tenant_session(_all_entities(tenant_id)) as session:
        return [
            dict(row)
            for row in session.execute(
                select(notification)
                .where(notification.c.kind == kind.value)
                .order_by(notification.c.created_at, notification.c.recipient_membership_id)
            ).mappings()
        ]


def _emails(tenant_id: UUID) -> list[Mapping[str, Any]]:
    with tenant_session(_all_entities(tenant_id)) as session:
        return [
            dict(row)
            for row in session.execute(
                select(outbox_message)
                .where(outbox_message.c.aggregate_type == "notification")
                .order_by(outbox_message.c.created_at, outbox_message.c.id)
            ).mappings()
        ]


def test_ntr_01_identical_notifications_merged(world: World, run: Run, clock: FrozenClock) -> None:
    recipient = _membership(world.preparer)
    subject_id = new_id()
    start = clock.now()

    def voided() -> None:
        with run(system_principal(world.tenant_id)) as uow:
            notify(
                uow,
                recipient_membership_ids=[recipient],
                kind=NotificationKind.APPROVAL_VOIDED,
                title=f"Approval voided: {SUMMARY}",
                body=VOIDED_BODY,
                subject_type=SUBJECT.value,
                subject_id=subject_id,
            )
            uow.commit()

    voided()
    clock.set(start + timedelta(minutes=9))
    voided()
    rows = _notifications(world.tenant_id, NotificationKind.APPROVAL_VOIDED)
    assert [row["created_at"] for row in rows] == [start]
    clock.set(start + timedelta(minutes=11))
    voided()
    rows = _notifications(world.tenant_id, NotificationKind.APPROVAL_VOIDED)
    assert [row["created_at"] for row in rows] == [start, start + timedelta(minutes=11)]
    # A merged notification sends no second email.
    assert len(_emails(world.tenant_id)) == 2


def test_krn_evt_06_preferences_respected(world: World, run: Run) -> None:
    tenant_id = world.tenant_id
    membership = _membership(world.approver_a)
    with run(system_principal(tenant_id)) as uow:
        assert on_membership_activated(uow, membership) == 12
        uow.commit()

    def send(kind: NotificationKind, title: str, **kwargs: Any) -> None:
        with run(system_principal(tenant_id)) as uow:
            notify(
                uow,
                recipient_membership_ids=[membership],
                kind=kind,
                title=title,
                subject_type=SUBJECT.value,
                subject_id=new_id(),
                **kwargs,
            )
            uow.commit()

    # ITEM_APPROVED: email off, so the in-app row only.
    send(NotificationKind.ITEM_APPROVED, f"Approved: {SUMMARY}")
    assert len(_notifications(tenant_id, NotificationKind.ITEM_APPROVED)) == 1
    assert _emails(tenant_id) == []

    # ITEM_REJECTED: email on; the email carries the title and link, never the body.
    send(
        NotificationKind.ITEM_REJECTED,
        f"Rejected: {SUMMARY}",
        body="Priya Approver rejected it: the impact of 1,200.00 USD is not supported.",
        link_path="/approvals/requests/probe",
    )
    [rejected] = _notifications(tenant_id, NotificationKind.ITEM_REJECTED)
    [email] = _emails(tenant_id)
    payload = email["payload"]
    assert (email["topic"], email["aggregate_id"], email["dedupe_key"]) == (
        "EMAIL",
        rejected["id"],
        f"notification:{rejected['id']}",
    )
    assert payload["to"].endswith("@rows.test")
    assert (payload["subject"], payload["link_path"], payload["notification_id"]) == (
        f"Rejected: {SUMMARY}",
        "/approvals/requests/probe",
        str(rejected["id"]),
    )
    assert "1,200.00" not in payload["text"]

    # A preference with email off stops the email and keeps the in-app row.
    with tenant_session(_all_entities(tenant_id)) as session:
        session.execute(
            update(notification_preference)
            .where(
                notification_preference.c.membership_id == membership,
                notification_preference.c.kind == NotificationKind.ITEM_REJECTED.value,
            )
            .values(email=False)
        )
    send(NotificationKind.ITEM_REJECTED, f"Rejected: {SUMMARY}")
    assert len(_notifications(tenant_id, NotificationKind.ITEM_REJECTED)) == 2
    assert len(_emails(tenant_id)) == 1

    # CHAIN_VERIFICATION_FAILED cannot be turned off (NTF-R2).
    with (
        pytest.raises(exc.IntegrityError) as excinfo,
        tenant_session(_all_entities(tenant_id)) as session,
    ):
        session.execute(
            update(notification_preference)
            .where(
                notification_preference.c.membership_id == membership,
                notification_preference.c.kind == NotificationKind.CHAIN_VERIFICATION_FAILED.value,
            )
            .values(email=False)
        )
    constraint = getattr(getattr(excinfo.value.orig, "diag", None), "constraint_name", None)
    assert constraint == "ck_notification_preference__mandatory"


def test_a_notification_raised_in_a_sandbox_is_delivered_in_the_app_only(
    world: World, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """05 SBX-08 rev 1.116 and NTR-04 (item SBX-EMAIL-1): a sandbox reaches no external system, so
    a notification raised there is delivered in the app only. The same three notifications are
    raised in a sandbox and in a production workspace through the unit of work a job opens, which
    reads the tenant kind from the tenant row (DG-KRN-UOW-04): a kind whose email default is on,
    before any preference is stored; the same kind under its stored preference, email on; and the
    kind that is always sent in the app and by email (PRD NTF-R2). The sandbox writes the three
    in-app rows and no ``EMAIL`` message. Production, the positive control, writes the same rows
    and one email for each."""
    runtime = JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))
    sandbox = seeded_sandbox(keyring, clock)
    with tenant_session(_all_entities(sandbox)) as session:
        user_id = insert_app_user(session)
        in_sandbox = insert_active_membership(session, tenant_id=sandbox, user_id=user_id)
    sent = [
        NotificationKind.ITEM_REJECTED,
        NotificationKind.ITEM_REJECTED,
        NotificationKind.CHAIN_VERIFICATION_FAILED,
    ]

    def raised(tenant_id: UUID, membership: UUID) -> tuple[list[str], list[str]]:
        """The kinds of the in-app rows and the subjects of the emails the three leave."""

        def send(kind: NotificationKind) -> None:
            with system_unit_of_work(
                runtime, system_principal(tenant_id), request_id="tests-sbx-email"
            ) as uow:
                notify(
                    uow,
                    recipient_membership_ids=[membership],
                    kind=kind,
                    title=f"Raised: {kind.value}",
                    link_path="/approvals/requests/probe",
                    subject_type=SUBJECT.value,
                    subject_id=new_id(),
                )
                uow.commit()

        send(sent[0])
        with system_unit_of_work(
            runtime, system_principal(tenant_id), request_id="tests-sbx-email"
        ) as uow:
            assert on_membership_activated(uow, membership) == 12
            uow.commit()
        send(sent[1])
        send(sent[2])
        with tenant_session(_all_entities(tenant_id)) as session:
            kinds = sorted(session.scalars(select(notification.c.kind)))
            stored = session.execute(
                select(notification_preference.c.in_app, notification_preference.c.email).where(
                    notification_preference.c.membership_id == membership,
                    notification_preference.c.kind == sent[1].value,
                )
            ).one()
        assert tuple(stored) == (True, True)  # the preference asks for the email in both
        return kinds, sorted(str(email["payload"]["subject"]) for email in _emails(tenant_id))

    in_app = sorted(kind.value for kind in sent)
    assert raised(sandbox, in_sandbox) == (in_app, [])
    with tenant_session(_all_entities(sandbox)) as session:
        assert session.execute(select(outbox_message.c.id)).all() == []  # nothing queued at all
    assert raised(world.tenant_id, _membership(world.approver_a)) == (
        in_app,
        sorted(f"Raised: {kind.value}" for kind in sent),
    )


def test_membership_activation_seeds_preferences(world: World, run: Run) -> None:
    tenant_id = world.tenant_id
    membership = _membership(world.approver_b)
    with run(system_principal(tenant_id)) as uow:
        assert on_membership_activated(uow, membership) == 12
        uow.commit()
    with tenant_session(_all_entities(tenant_id)) as session:
        rows = session.execute(
            select(
                notification_preference.c.kind,
                notification_preference.c.in_app,
                notification_preference.c.email,
            ).where(notification_preference.c.membership_id == membership)
        ).all()
    assert len(rows) == 12
    assert all(row.in_app for row in rows)
    assert {str(row.kind): bool(row.email) for row in rows} == {
        "APPROVAL_ASSIGNED": True,
        "ITEM_REJECTED": True,
        "APPROVAL_VOIDED": True,
        "JOB_FAILED": True,
        "PERIOD_REOPENED": True,
        "CHAIN_VERIFICATION_FAILED": True,
        "EXPORT_FAILED": True,
        "SUPPORT_GRANT_REQUESTED": True,
        "ITEM_APPROVED": False,
        "PERIOD_LOCKED": False,
        "CLOSE_BLOCKER_RAISED": False,
        "EXCEPTION_ASSIGNED": False,
    }
    # Activating again keeps the stored choices.
    with run(system_principal(tenant_id)) as uow:
        assert on_membership_activated(uow, membership) == 0
        uow.commit()


def test_approval_notifications_ntf_01_to_04(world: World, probe: ProbeSubjects, run: Run) -> None:
    tenant_id = world.tenant_id
    preparer = _membership(world.preparer)
    approvers = sorted([_membership(world.approver_a), _membership(world.approver_b)])

    def submitted(role: str) -> Mapping[str, Any]:
        subject_id = probe.new_subject(role=role)
        with run(world.preparer) as uow:
            request = submit(uow, subject_type=SUBJECT, subject_id=subject_id, summary=SUMMARY)
            uow.commit()
        return request

    def decided(
        principal: Principal, request: Mapping[str, Any], decision: str, comment: str | None
    ) -> None:
        with run(principal) as uow:
            decide(
                uow,
                approval_request_id=request["id"],
                decision=decision,  # type: ignore[arg-type]
                subject_content_sha256=request["subject_content_sha256"],
                impact_preview_sha256=None,
                comment=comment,
                reason_code=None,
            )
            uow.commit()

    # NTF-01: holders of the step permission other than the preparer.
    first = submitted("access_approver")
    assigned = _notifications(tenant_id, NotificationKind.APPROVAL_ASSIGNED)
    assert sorted(row["recipient_membership_id"] for row in assigned) == approvers
    for row in assigned:
        assert (row["title"], row["link_path"], row["subject_type"], row["subject_id"]) == (
            f"Approval needed: {SUMMARY}",
            f"/approvals/requests/{first['id']}",
            "approval_request",
            first["id"],
        )
        assert row["body"].endswith(f"submitted {SUMMARY} for approval.")

    # NTF-03: the preparer learns of a rejection.
    comment = "Attach the customer acceptance before resubmitting."
    decided(world.approver_a, first, "REJECT", comment)
    [rejected] = _notifications(tenant_id, NotificationKind.ITEM_REJECTED)
    assert (rejected["recipient_membership_id"], rejected["title"], rejected["body"]) == (
        preparer,
        f"Rejected: {SUMMARY}",
        f"Priya Approver rejected {SUMMARY}: {comment}",
    )
    assert (rejected["subject_type"], rejected["subject_id"]) == (
        SUBJECT.value,
        first["subject_id"],
    )

    # NTF-02: and of an approval.
    second = submitted("auditor")
    decided(world.approver_b, second, "APPROVE", None)
    [approved] = _notifications(tenant_id, NotificationKind.ITEM_APPROVED)
    assert (approved["recipient_membership_id"], approved["title"], approved["body"]) == (
        preparer,
        f"Approved: {SUMMARY}",
        f"Marcus Approver approved {SUMMARY}.",
    )

    # NTF-04: a changed subject voids the request for the preparer and the assigned approvers.
    third = submitted("viewer")
    probe.contents[third["subject_id"]]["role"] = "controller"
    with run(world.preparer) as uow:
        assert void_if_stale(uow, subject_type=SUBJECT, subject_id=third["subject_id"]) is not None
        uow.commit()
    voided = _notifications(tenant_id, NotificationKind.APPROVAL_VOIDED)
    assert sorted(row["recipient_membership_id"] for row in voided) == sorted(
        [preparer, *approvers]
    )
    for row in voided:
        assert (row["title"], row["body"], row["link_path"], row["subject_id"]) == (
            f"Approval voided: {SUMMARY}",
            VOIDED_BODY,
            f"/approvals/requests/{third['id']}",
            third["subject_id"],
        )
