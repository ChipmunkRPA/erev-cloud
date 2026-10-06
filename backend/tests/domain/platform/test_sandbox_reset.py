"""SNP-3 sandbox reset by supersession — the database witnesses (BUILD_SPEC SNP-3 acceptance; 05
§10 SBX-07 and SBX-04 rev 1.64; 04 API-R-04, API-S-Me and §16.14 rev 1.125; PRD J-25.3,
J-25-AC-1, ERR-25, ACT-51; 03 REQ-PLT-024, REQ-PLT-025).

Every case goes through the product: the world is provisioned and its members sign in, the copy
is the dispatched ``TENANT_SNAPSHOT`` job, the reset is ``POST /tenant/reset`` by a signed-in
Controller inside the sandbox, and its ``SANDBOX_RESET`` job is run as the worker runs it.

Two clocks (the note of ``test_sandbox_load.py``): a world is built at the frozen application
clock, its rows carry database stamps of the real clock, so the snapshot cutoff is read from the
database once the world is complete and the frozen clock advances to it. A session opened before
that jump has passed its absolute limit, so the requester signs in again after the copy.

``test_reset_to_copy`` runs on ``worlds.k03_castellan`` at WLD-X-12, the state
``test_sandbox_load.py::test_sandbox_copy_k03`` copies: the successor's cumulative revenue is
797,294.12 as in production. The WLD-X-13 figure BUILD_SPEC first named for this node
(829,852.94 after the J-14 correction in reopened September) is owed to SNP-2b with the rest of
that state (supervisor ruling R-10); it is not asserted here.
"""

from __future__ import annotations

import secrets
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import routing
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.controls.release import current_release
from erev_api.db.session import DbContext, identity_session, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    audit_event,
    contract_version,
    job,
    metadata,
    outbox_message,
    role,
    role_assignment,
    rule_set,
    rule_set_version,
    security_event,
    tenant,
    tenant_membership,
    tenant_snapshot,
    user_session,
)
from erev_api.domain.platform import sandbox_reset
from erev_api.domain.platform import sandboxes as sb
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.domain.platform.provisioning import (
    OperatorActor,
    TenantProvisionRequest,
    provision_tenant,
)
from erev_api.enums import JobKind, NotificationKind
from erev_api.files.store import LocalFileStore
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from support.clock import FROZEN_AT
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.http import HttpResponse
from support.principals import (
    Actor,
    Signed,
    colleague,
    enrolled,
    member,
    select_tenant,
)
from support.reference import assign, get, post, put, slug
from support.rows import tenant_snapshot_values
from support.snapshots import (
    confirm_retention,
    cutoff_after,
    enter_workspace,
    load_outcome,
    run_dispatched_snapshot,
    work_job,
)
from support.worlds import k03_castellan, k03_change_order, k03_september

API = "/api/v1"
RESET = f"{API}/tenant/reset"
REASON = "Rehearsal complete"  # PRD J-25.3
RETENTION_FROM = FROZEN_AT - timedelta(days=1)
# What the reset itself writes in the sandbox it supersedes: its job, its events, the stored
# answer of the request. Everything else must be exactly as it was — nothing is deleted.
_RESET_WRITES = frozenset({"job", "audit_event", "idempotency_record", "outbox_message"})


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    """The app with the release its startup would stamp (05 REL-03): ``GET /me`` answers it."""
    application = create_app(app_settings, clock=clock)
    stamp_test_release()
    application.state.engine_release = current_release()
    return application


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def runtime(app_settings: Settings, keyring: KeyRing, clock: FrozenClock) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=LocalFileStore(app_settings.file_root))


@pytest.fixture(autouse=True)
def handlers() -> Iterator[None]:
    """``TENANT_SNAPSHOT`` and ``SANDBOX_RESET`` registered for the test as the worker's import of
    its handler modules registers them (DG-ARC-08), and the engine release stamped as the
    worker's startup stamps it; only what this fixture registered is removed."""
    from erev_api.domain.platform import sandbox_reset_job, snapshot_job

    stamp_test_release()
    specs = {
        JobKind.TENANT_SNAPSHOT: registry.HandlerSpec(
            handler=snapshot_job.tenant_snapshot_export,
            retry=snapshot_job.SNAPSHOT_RETRY,
            on_failure=snapshot_job.snapshot_failed,
        ),
        JobKind.SANDBOX_RESET: registry.HandlerSpec(
            handler=sandbox_reset_job.sandbox_reset_job,
            retry=sandbox_reset_job.RESET_RETRY,
            on_failure=sandbox_reset.reset_failed,
        ),
    }
    added = [kind for kind in specs if kind not in registry.HANDLERS]
    for kind in added:
        registry.HANDLERS[kind] = specs[kind]
    yield
    for kind in added:
        registry.HANDLERS.pop(kind, None)


def _context(tenant_id: UUID) -> DbContext:
    return DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")


@dataclass(frozen=True, slots=True)
class Copied:
    """A production world with its sandbox copy and the Controller who asked for it."""

    production_id: UUID
    sandbox_id: UUID
    snapshot_id: UUID
    requester: Actor  # as signed in before the copy: member of production, TOTP secret


def _copy(
    requester: Actor, runtime: JobRuntime, clock: FrozenClock, name: str, *, retained: bool = False
) -> Copied:
    """A SANDBOX_COPY of the requester's production tenant through the dispatched job.
    ``retained``: an earlier copy of the world confirmed the retention settings."""
    someone = requester.member
    if not retained:
        with tenant_session(_context(someone.tenant_id)) as session:
            confirm_retention(session, someone.tenant_id, at=RETENTION_FROM)
    known_at = cutoff_after(someone.tenant_id, clock)
    with tenant_session(_context(someone.tenant_id)) as session:
        row = tenant_snapshot_values(someone.tenant_id, known_at=known_at, purpose="SANDBOX_COPY")
        session.execute(insert(tenant_snapshot).values(**row))
    snapshot_id = UUID(str(row["id"]))
    sandbox_id = UUID(int=int(snapshot_id) ^ 1)  # a distinct pre-allocated id
    params = {
        "tenant_snapshot_id": str(snapshot_id),
        "known_at": known_at.isoformat(),
        "purpose": "SANDBOX_COPY",
        **sb.load_params_of(
            sandbox_tenant_id=sandbox_id, name=name, requested_by=someone.user_id, restore=False
        ),
    }
    result = run_dispatched_snapshot(someone.tenant_id, params, runtime=runtime, now=known_at)
    assert result["state"] == "SUCCEEDED", result["problem"]
    return Copied(someone.tenant_id, sandbox_id, snapshot_id, requester)


def _reset(app: FastAPI, actor: Actor, **body: Any) -> HttpResponse:
    return post(app, RESET, actor, body)


def _run_reset(accepted: HttpResponse, sandbox_id: UUID, runtime: JobRuntime) -> dict[str, Any]:
    assert accepted.status_code == 202, accepted.text
    return work_job(sandbox_id, UUID(str(accepted.json()["id"])), runtime)


def _tenant(tenant_id: UUID) -> dict[str, Any]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return dict(
            session.execute(select(tenant).where(tenant.c.id == tenant_id)).mappings().one()
        )


def _row_counts(tenant_id: UUID) -> dict[str, int]:
    """Rows of ``tenant_id`` in every tenant-scoped table of the model."""
    counts: dict[str, int] = {}
    with tenant_session(_context(tenant_id), read_only=True) as session:
        for table in metadata.sorted_tables:
            if "tenant_id" not in table.c or not table.c.tenant_id.primary_key:
                continue  # tenant-scoped tables carry the tenant in their key (04 SC-T)
            counts[table.name] = int(
                session.execute(
                    select(func.count()).select_from(table).where(table.c.tenant_id == tenant_id)
                ).scalar_one()
            )
    return counts


def _events(tenant_id: UUID, action: str) -> list[dict[str, Any]]:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return [
            dict(row)
            for row in session.execute(
                select(audit_event)
                .where(audit_event.c.action == action)
                .order_by(audit_event.c.chain_seq)
            ).mappings()
        ]


def _revenue(tenant_id: UUID, group_id: UUID) -> Decimal:
    with tenant_session(_context(tenant_id), read_only=True) as session:
        return Decimal(
            session.execute(
                select(contract_version.c.revenue_cum)
                .where(
                    contract_version.c.combination_group_id == group_id,
                    contract_version.c.book_code == "ASC606",
                )
                .order_by(contract_version.c.version_no.desc())
                .limit(1)
            ).scalar_one()
        )


def _active_tenant_of(token: str) -> UUID | None:
    """``user_session.active_tenant_id`` of the session a cookie token names."""
    import hashlib

    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    with identity_session(request_id="tests-session-row") as db:
        value = db.execute(
            select(user_session.c.active_tenant_id).where(user_session.c.token_sha256 == digest)
        ).scalar_one()
    return None if value is None else UUID(str(value))


def _controller_world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock
) -> tuple[Actor, Actor, Actor]:
    """A provisioned production tenant with three signed-in members: Marcus (Controller and
    Tenant Admin, MFA — the requester), Cora (a second Controller, MFA) and Maya (Revenue
    Accountant). It holds no contract: these cases are about the workspaces, not their figures."""
    root = member(keyring, clock, name="marcus")
    assign(root, "controller")
    assign(root, "tenant_admin")
    marcus = enrolled(app, clock, root)
    cora_member = colleague(root.tenant_id, "cora")
    assign(cora_member, "controller")
    cora = enrolled(app, clock, cora_member)
    maya_member = colleague(root.tenant_id, "maya")
    assign(maya_member, "revenue_accountant")
    maya = enrolled(app, clock, maya_member)
    return marcus, cora, maya


def test_reset_to_copy(
    app: FastAPI,
    files: LocalFileStore,
    keyring: KeyRing,
    clock: FrozenClock,
    runtime: JobRuntime,
) -> None:
    """PRD J-25.3 on the SNP-2 sandbox (the K-03 copy): Marcus resets it "back to the copy" with
    the reason "Rehearsal complete". The job SUCCEEDS; a NEW sandbox — same name, a code of its
    own, the same source and ``known_at`` — holds ``PRJ-CB-2026-01`` with cumulative revenue
    797,294.12 as in production (WLD-X-12), verified like any load; the old sandbox is
    ``ARCHIVED`` and every one of its tables holds exactly the rows it held, but for the reset's
    own job, events and stored answer — no row is deleted; the three tenants each record their
    part; and the snapshot's target is the successor."""
    k03 = k03_castellan(app, keyring, clock, files)
    k03_change_order(k03, clock)  # J-06: WLD-X-10
    k03_september(k03, clock)  # J-10: WLD-X-11, WLD-X-12
    copied = _copy(k03.report.marcus, runtime, clock, "Avenmoor pre-close snapshot")
    marcus = enter_workspace(app, clock, copied.requester, copied.sandbox_id)
    shown = get(app, f"{API}/tenant", marcus)
    assert shown.status_code == 200, shown.text
    seed = shown.json()["sandbox_load"]
    assert seed["tenant_snapshot_id"] == str(copied.snapshot_id)
    assert (seed["derived_mismatches"], seed["blocked_periods"]) == (0, [])
    old = _tenant(copied.sandbox_id)
    accepted = _reset(
        app, marcus, mode="SNAPSHOT", tenant_snapshot_id=str(copied.snapshot_id), reason=REASON
    )
    assert accepted.status_code == 202, accepted.text
    successor_id = UUID(accepted.headers["X-Erev-Sandbox-Tenant-Id"])
    before = _row_counts(copied.sandbox_id)
    production_before = _row_counts(copied.production_id)
    ended = _run_reset(accepted, copied.sandbox_id, runtime)
    assert ended["state"] == "SUCCEEDED", ended["problem"]
    result = ended["result"]
    assert result["sandbox_tenant_id"] == str(successor_id)
    assert result["archived_tenant_id"] == str(copied.sandbox_id)
    counts = result["counts"]
    assert counts["derived_mismatches"] == 0, load_outcome(counts)
    assert (counts["groups_recomputed"], counts["blocked_periods"]) == (1, 0)
    assert counts["sessions_moved"] == 1
    # the successor: a new sandbox equal to the copy
    successor = _tenant(successor_id)
    assert (successor["kind"], successor["status"]) == ("sandbox", "ACTIVE")
    assert successor["source_tenant_id"] == copied.production_id
    assert successor["source_known_at"] == old["source_known_at"]
    assert successor["display_name"] == old["display_name"]
    assert successor["code"] == sandbox_reset.successor_code(str(old["code"]), successor_id)
    assert _revenue(successor_id, k03.group_id) == Decimal("797294.12")  # WLD-X-12
    assert _revenue(successor_id, k03.group_id) == _revenue(copied.production_id, k03.group_id)
    copied_tables = {
        dataset.name
        for dataset in sd.inventory().datasets
        if dataset.snapshot_class is sd.SnapshotClass.COPIED
    }
    after_successor = _row_counts(successor_id)
    for name in sorted(copied_tables - {"tenant_snapshot", "file_object"}):
        assert after_successor[name] == before[name], name  # the same copy, table by table
    # the superseded sandbox: archived, and nothing of it deleted or changed in number
    archived = _tenant(copied.sandbox_id)
    assert (archived["status"], archived["kind"]) == ("ARCHIVED", "sandbox")
    after = _row_counts(copied.sandbox_id)
    assert {name for name in after if after[name] != before[name]} <= _RESET_WRITES
    assert all(after[name] >= before[name] for name in after)  # no row is deleted
    assert _revenue(copied.sandbox_id, k03.group_id) == Decimal("797294.12")
    # each tenant's record of it
    (left,) = _events(copied.sandbox_id, sandbox_reset.ACTION_RESET)
    assert (left["before"], left["after"]) == ({"status": "ACTIVE"}, {"status": "ARCHIVED"})
    assert left["detail"] == {
        "mode": "SNAPSHOT",
        "tenant_snapshot_id": str(copied.snapshot_id),
        "successor_tenant_id": str(successor_id),
        "reason": REASON,
    }
    (arrived,) = _events(successor_id, sandbox_reset.ACTION_RESET)
    assert arrived["detail"]["superseded_tenant_id"] == str(copied.sandbox_id)
    (summary,) = _events(successor_id, sb.ACTION_LOADED)
    assert summary["chain_seq"] < arrived["chain_seq"]  # after the load's own events
    assert summary["object_id"] == copied.snapshot_id  # the successor's seed is the same snapshot
    restored = _events(copied.production_id, sb.ACTION_RESTORED)
    assert [event["detail"]["sandbox_tenant_id"] for event in restored] == [str(successor_id)]
    with tenant_session(_context(copied.production_id), read_only=True) as session:
        target = session.execute(
            select(tenant_snapshot.c.target_tenant_id).where(
                tenant_snapshot.c.id == copied.snapshot_id
            )
        ).scalar_one()
    assert target == successor_id
    # production: only its own provenance records of the new sandbox were added
    production_after = _row_counts(copied.production_id)
    changed = {n for n in production_after if production_after[n] != production_before[n]}
    assert changed <= {"audit_event", "notification", "outbox_message"}, changed


def test_reset_empty(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """``mode = EMPTY``: the successor holds only the 04 §14.3 provisioning seed. Its rows are
    counted table by table against a workspace ``tenant.provision`` has just created: equal
    everywhere but for what the two documented differences bring — the requester's membership is
    ACTIVE at once (its notification preferences exist, no invitation is queued) and the chain
    carries the successor's ``tenant.sandbox_reset``. It is a sandbox of the same source without
    ``source_known_at``, its first audit event is ``tenant.sandbox_created``, the requester is its
    Tenant Admin by the ``AUTO-BOOTSTRAP`` grant, and it has no seed (``sandbox_load`` is null;
    a ``SNAPSHOT`` reset of a seedless sandbox is refused in
    ``tests/api/test_tenant_snapshots.py::test_reset_permission_and_step_up``)."""
    marcus_in_production, _, _ = _controller_world(app, keyring, clock)
    copied = _copy(marcus_in_production, runtime, clock, "Scratch")
    marcus = enter_workspace(app, clock, copied.requester, copied.sandbox_id)
    named = _reset(
        app, marcus, mode="EMPTY", tenant_snapshot_id=str(copied.snapshot_id), reason=REASON
    )
    assert named.status_code == 422, named.text  # an empty reset names no snapshot
    accepted = _reset(app, marcus, mode="EMPTY", reason=REASON)
    ended = _run_reset(accepted, copied.sandbox_id, runtime)
    assert ended["state"] == "SUCCEEDED", ended["problem"]
    successor_id = UUID(ended["result"]["sandbox_tenant_id"])
    successor = _tenant(successor_id)
    assert (successor["kind"], successor["status"]) == ("sandbox", "ACTIVE")
    assert successor["source_tenant_id"] == copied.production_id
    assert successor["source_known_at"] is None and successor["setup_completed_at"] is None
    reference = provision_tenant(
        TenantProvisionRequest(
            code=f"ref-{secrets.token_hex(6)}",
            display_name="Reference workspace",
            reporting_currency=str(successor["reporting_currency"]),
            is_demo=False,
            admin_email=f"admin-{secrets.token_hex(4)}@reference.test",
        ),
        actor=OperatorActor(
            channel="CLI", operator_user_id=None, os_user="tests", request_id="tests-reference"
        ),
        clock=clock,
        keyring=keyring,
    )
    seed = _row_counts(UUID(str(reference.tenant["id"])))
    held = _row_counts(successor_id)
    differing = {name: held[name] - seed[name] for name in seed if held[name] != seed[name]}
    assert differing == {
        "notification_preference": len(NotificationKind),  # the membership is ACTIVE at once
        "outbox_message": -1,  # no invitation is queued
        "audit_event": 1,  # the successor's tenant.sandbox_reset
    }
    assert held["tenant_membership"] == seed["tenant_membership"] == 1
    with tenant_session(_context(successor_id), read_only=True) as session:
        first = session.execute(
            select(audit_event.c.action).where(audit_event.c.chain_seq == 1)
        ).scalar_one()
        membership = session.execute(select(tenant_membership)).mappings().one()
    assert first == sandbox_reset.ACTION_CREATED
    assert (membership["status"], membership["user_id"]) == ("ACTIVE", marcus.member.user_id)
    assert membership["invitation_token_sha256"] is None
    created = _events(copied.production_id, sandbox_reset.ACTION_CREATED)
    assert [event["object_id"] for event in created] == [successor_id]  # SBX-02: both tenants
    # the requester's session is in the successor as its Tenant Admin — the grant of a newly
    # provisioned workspace, no more: ``sandbox.reset`` there takes a Controller grant
    me = get(app, f"{API}/me", marcus)
    assert me.status_code == 200, me.text
    permissions = set(me.json()["permissions"])
    assert "settings.manage" in permissions and "sandbox.reset" not in permissions
    shown = get(app, f"{API}/tenant", marcus)
    assert shown.status_code == 200, shown.text
    assert (shown.json()["id"], shown.json()["sandbox_load"]) == (str(successor_id), None)


@dataclass(frozen=True, slots=True)
class AdminGrants:
    """What a workspace's rows say about a member's ``tenant_admin`` grants, and what the
    approvals engine answers about the member."""

    membership_id: UUID
    members: int
    setup_completed: bool
    grants: list[dict[str, Any]]  # ascending by who wrote the assignment
    is_bootstrap_admin: bool


def _admin_grants(tenant_id: UUID, user_id: UUID) -> AdminGrants:
    """Each ``tenant_admin`` assignment of the user's membership as its row states it — who wrote
    it, whether it is revoked — with the request it names: who wrote and who prepared that one,
    its status, and each decision with the rule set of the rule that took it."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        membership_id = UUID(
            str(
                session.execute(
                    select(tenant_membership.c.id).where(tenant_membership.c.user_id == user_id)
                ).scalar_one()
            )
        )
        grants: list[dict[str, Any]] = []
        for written_by, revoked_at, request_id in session.execute(
            select(
                role_assignment.c.created_by_kind,
                role_assignment.c.revoked_at,
                role_assignment.c.approval_request_id,
            )
            .select_from(role_assignment.join(role, role.c.id == role_assignment.c.role_id))
            .where(role_assignment.c.membership_id == membership_id, role.c.code == "tenant_admin")
        ).all():
            request: dict[str, Any] | None = None
            if request_id is not None:
                found = (
                    session.execute(
                        select(
                            approval_request.c.subject_type,
                            approval_request.c.created_by_kind,
                            approval_request.c.preparer_kind,
                            approval_request.c.preparer_id,
                            approval_request.c.status,
                        ).where(approval_request.c.id == request_id)
                    )
                    .mappings()
                    .one()
                )
                decided = session.execute(
                    select(
                        approval_decision.c.decision,
                        approval_decision.c.approver_kind,
                        rule_set.c.code,
                    )
                    .select_from(
                        approval_decision.outerjoin(
                            rule_set_version,
                            rule_set_version.c.id == approval_decision.c.auto_rule_set_version_id,
                        ).outerjoin(rule_set, rule_set.c.id == rule_set_version.c.rule_set_id)
                    )
                    .where(approval_decision.c.approval_request_id == request_id)
                    .order_by(approval_decision.c.decided_at, approval_decision.c.id)
                ).all()
                request = {
                    "subject_type": str(found["subject_type"]),
                    "written_by": str(found["created_by_kind"]),
                    "preparer": (str(found["preparer_kind"]), found["preparer_id"]),
                    "status": str(found["status"]),
                    "decided": [(str(kind), str(by), code) for kind, by, code in decided],
                }
            grants.append(
                {
                    "written_by": str(written_by),
                    "revoked": revoked_at is not None,
                    "request": request,
                }
            )
        workspace = session.execute(
            select(tenant.c.setup_completed_at).where(tenant.c.id == tenant_id)
        ).one()
        return AdminGrants(
            membership_id=membership_id,
            members=len(session.execute(select(tenant_membership.c.id)).all()),
            setup_completed=workspace.setup_completed_at is not None,
            grants=sorted(grants, key=lambda grant: str(grant["written_by"])),
            is_bootstrap_admin=routing.is_bootstrap_admin(session, membership_id),
        )


def _viewer_granted(
    app: FastAPI, actor: Actor, tenant_id: UUID, membership_id: UUID
) -> tuple[int, str | None, bool | None]:
    """``POST /role-assignments`` by ``actor`` — Viewer for all entities: the status code, the
    status of the grant and whether it is a setup grant."""
    with tenant_session(_context(tenant_id), read_only=True) as session:
        viewer = session.execute(select(role.c.id).where(role.c.code == "viewer")).scalar_one()
    answered = post(
        app,
        f"{API}/role-assignments",
        actor,
        {"membership_id": str(membership_id), "role_id": str(viewer), "is_all_entities": True},
    )
    body = answered.json()
    return answered.status_code, body.get("status"), body.get("setup_grant")


def test_the_requester_of_an_empty_sandbox_is_its_bootstrap_admin(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """Item SBX-EMPTY-BOOTSTRAP-1 (05 SBX-07 rev 1.181; 04 §14.3 item 2 rev 1.254; BUILD_SPEC
    SNP-3): the sole member of an EMPTY sandbox staffs it as the admin of a newly provisioned
    workspace staffs that one — rule ``AUTO-BOOTSTRAP`` approves the grant that member
    requests, because nobody else exists who could decide it. The same request is made in both
    workspaces, the provisioned one first: it is the control.

    Who the bootstrap Tenant Admin is, is read from the grant the seed of the workspace wrote —
    the ``tenant_admin`` assignment whose request was prepared by SYSTEM with no preparer and
    approved by the rule (``routing.is_bootstrap_admin``) — and both seeds write that pair
    (``provisioning.grant_bootstrap_admin``). The stamps differ and stay the record of who wrote
    the rows: the operator for ``tenant.provision``, the job's SYSTEM principal for the sandbox.
    The control also shows two things every world of the suite stands on: the provisioned
    assignment counts although the world revoked it, and the world's own ``tenant_admin``
    assignment, written without a request, is not what makes its member the bootstrap admin.

    The sandbox COPY between the two holds the pair of its source, the rows as they are, so the
    same user is the bootstrap admin there, before this item and after it — to no effect: a
    loaded sandbox is stamped set up at its load, so the rule is not read in it.

    Fail-first (main ccd57182, where the ``OPERATOR`` stamp of the assignment was the mark):
    every assertion before the last held, and the last read ``(False, (201, "REQUESTED",
    False))``. Measured beside it on 1ecbdf87: that request was PENDING and not decidable by
    its preparer, and nobody else was in the workspace."""
    marcus_in_production, _, maya = _controller_world(app, keyring, clock)
    production_id = marcus_in_production.member.tenant_id
    user_id = marcus_in_production.member.user_id
    seed_request = {
        "subject_type": "ROLE_ASSIGNMENT",
        "preparer": ("SYSTEM", None),
        "status": "APPROVED",
        "decided": [("AUTO_APPROVE", "SYSTEM", "AUTO-BOOTSTRAP")],
    }
    control = _admin_grants(production_id, user_id)
    assert control.grants == [
        {
            "written_by": "OPERATOR",
            "revoked": True,
            "request": seed_request | {"written_by": "OPERATOR"},
        },
        {"written_by": "SYSTEM", "revoked": False, "request": None},  # ``support.reference.assign``
    ]
    assert control.setup_completed is False
    granted = _viewer_granted(app, marcus_in_production, production_id, maya.member.membership_id)
    assert (control.is_bootstrap_admin, granted) == (True, (201, "ACTIVE", True))

    copied = _copy(marcus_in_production, runtime, clock, "Staffing")
    copy = _admin_grants(copied.sandbox_id, user_id)
    assert (copy.grants, copy.is_bootstrap_admin) == (control.grants, True)
    assert copy.setup_completed is True  # stamped at the load: the rule is not read in a copy

    marcus = enter_workspace(app, clock, copied.requester, copied.sandbox_id)
    ended = _run_reset(_reset(app, marcus, mode="EMPTY", reason=REASON), copied.sandbox_id, runtime)
    assert ended["state"] == "SUCCEEDED", ended["problem"]
    successor_id = UUID(ended["result"]["sandbox_tenant_id"])
    sandbox = _admin_grants(successor_id, user_id)
    assert sandbox.grants == [
        {
            "written_by": "SYSTEM",
            "revoked": False,
            "request": seed_request | {"written_by": "SYSTEM"},
        }
    ]
    assert (sandbox.members, sandbox.setup_completed) == (1, False)
    granted = _viewer_granted(app, marcus, successor_id, sandbox.membership_id)
    assert (sandbox.is_bootstrap_admin, granted) == (True, (201, "ACTIVE", True))


def test_production_reset_forbidden(app: FastAPI, keyring: KeyRing, clock: FrozenClock) -> None:
    """PRD J-25-AC-1 / ERR-25 (REQ-PLT-024): ``POST /tenant/reset`` in a production tenant
    answers 409 ``production-reset-forbidden`` with the catalogue copy — to a Controller with a
    fresh verification and, before any step-up is asked, to one whose verification is stale —
    and nothing is deferred."""
    marcus, _, _ = _controller_world(app, keyring, clock)
    for mode in ("SNAPSHOT", "EMPTY"):
        refused = _reset(app, marcus, mode=mode, reason=REASON)
        assert (refused.status_code, slug(refused)) == (409, "production-reset-forbidden")
        assert refused.json()["detail"] == (
            "Production workspaces cannot be reset or restored. Create a sandbox copy instead."
        )
    clock.advance(timedelta(minutes=6))  # past the BR-PLT-06 step-up window
    stale = _reset(app, marcus, mode="EMPTY", reason=REASON)
    assert (stale.status_code, slug(stale)) == (409, "production-reset-forbidden"), stale.text
    with tenant_session(_context(marcus.member.tenant_id), read_only=True) as session:
        deferred = session.execute(
            select(func.count()).select_from(job).where(job.c.kind == JobKind.SANDBOX_RESET.value)
        ).scalar_one()
    assert deferred == 0
    assert _tenant(marcus.member.tenant_id)["status"] == "ACTIVE"


def test_archived_tenant_rejects_commands(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """05 SBX-07: after a reset the archived sandbox takes no command and cannot be opened. Cora
    and Maya are still signed in inside it: their commands answer 409 ``invalid-transition``
    (a reset by Cora, a customer by Maya) and nothing is written, while their reads still answer;
    ``GET /me`` lists the membership with the workspace ``ARCHIVED`` — not among the selectable
    ones, which are those whose membership and workspace are both ACTIVE — and
    ``POST /session/tenant`` for it answers 409 ``invalid-transition``."""
    marcus_in_production, cora_in_production, maya_in_production = _controller_world(
        app, keyring, clock
    )
    copied = _copy(marcus_in_production, runtime, clock, "Superseded")
    marcus = enter_workspace(app, clock, copied.requester, copied.sandbox_id)
    cora = enter_workspace(app, clock, cora_in_production, copied.sandbox_id)
    maya = enter_workspace(app, clock, maya_in_production, copied.sandbox_id)
    customer = {"code": "C-ARCHIVE", "name": "Archived workspace witness"}
    created = post(app, f"{API}/customers", maya, customer)
    assert created.status_code == 201, created.text  # a command the sandbox takes while ACTIVE
    ended = _run_reset(_reset(app, marcus, mode="EMPTY", reason=REASON), copied.sandbox_id, runtime)
    assert ended["state"] == "SUCCEEDED", ended["problem"]
    successor_id = UUID(ended["result"]["sandbox_tenant_id"])
    before = _row_counts(copied.sandbox_id)
    for refused in (
        _reset(app, cora, mode="EMPTY", reason=REASON),
        post(app, f"{API}/customers", maya, {**customer, "code": "C-ARCHIVE-2"}),
    ):
        assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
        assert (
            refused.json()["detail"]
            == "This workspace is archived. It cannot be opened or changed."
        )
    assert _row_counts(copied.sandbox_id) == before  # nothing written, not even a stored answer
    read = get(app, f"{API}/customers", maya)
    assert read.status_code == 200 and len(read.json()["items"]) == 1, read.text
    me = get(app, f"{API}/me", cora)
    assert me.status_code == 200, me.text
    listed = {m["tenant"]["id"]: m for m in me.json()["memberships"]}
    assert listed[str(copied.sandbox_id)]["tenant"]["status"] == "ARCHIVED"
    assert listed[str(copied.sandbox_id)]["tenant"]["source_tenant_id"] == str(copied.production_id)
    selectable = {
        tenant_id
        for tenant_id, m in listed.items()
        if m["status"] == "ACTIVE" and m["tenant"]["status"] == "ACTIVE"
    }
    assert selectable == {str(copied.production_id)}  # Cora is no member of the empty successor
    assert str(successor_id) not in listed
    reopened = select_tenant(app, Signed(cora.token, cora.csrf_token, {}), copied.sandbox_id)
    assert (reopened.status_code, slug(reopened)) == (409, "invalid-transition"), reopened.text
    back = select_tenant(app, Signed(cora.token, cora.csrf_token, {}), copied.production_id)
    assert back.status_code == 200, back.text


def test_session_moves_to_new_sandbox(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """05 SBX-07: after the job the caller's session names the new sandbox — the same cookie now
    answers in the successor, ``TENANT_SELECTED`` is recorded for it naming the tenant it left —
    while Marcus's other session, open in production, stays in production, and Cora's session in
    the old sandbox stays where it was (it is hers to leave)."""
    marcus_in_production, cora_in_production, _ = _controller_world(app, keyring, clock)
    copied = _copy(marcus_in_production, runtime, clock, "Moving")
    elsewhere = enter_workspace(app, clock, copied.requester, copied.production_id)
    cora = enter_workspace(app, clock, cora_in_production, copied.sandbox_id)
    marcus = enter_workspace(app, clock, copied.requester, copied.sandbox_id)
    assert _active_tenant_of(marcus.token) == copied.sandbox_id
    accepted = _reset(app, marcus, mode="SNAPSHOT", reason=REASON)  # the server resolves the seed
    successor_id = UUID(accepted.headers["X-Erev-Sandbox-Tenant-Id"])
    ended = _run_reset(accepted, copied.sandbox_id, runtime)
    assert ended["state"] == "SUCCEEDED", ended["problem"]
    assert ended["result"]["counts"]["sessions_moved"] == 1
    assert _active_tenant_of(marcus.token) == successor_id
    assert _active_tenant_of(elsewhere.token) == copied.production_id
    assert _active_tenant_of(cora.token) == copied.sandbox_id
    shown = get(app, f"{API}/tenant", marcus)  # the same cookie, no new sign-in
    assert shown.status_code == 200, shown.text
    assert shown.json()["id"] == str(successor_id)
    assert shown.headers["X-Erev-Tenant-Kind"] == "sandbox"
    assert shown.json()["sandbox_load"]["tenant_snapshot_id"] == str(copied.snapshot_id)
    with identity_session(request_id="tests-security-events") as db:
        moved = [
            dict(row)
            for row in db.execute(
                select(
                    security_event.c.kind, security_event.c.tenant_id, security_event.c.detail
                ).where(
                    security_event.c.user_id == marcus.member.user_id,
                    security_event.c.request_id == f"job-{ended['id']}-sessions",
                )
            ).mappings()
        ]
    assert [(str(m["kind"]), m["tenant_id"]) for m in moved] == [("TENANT_SELECTED", successor_id)]
    assert moved[0]["detail"] == {
        "moved_from_tenant_id": str(copied.sandbox_id),
        "reason": "SANDBOX_RESET",
    }
    # the job stays in the superseded sandbox as evidence: the moved session no longer sees it
    gone = get(app, f"{API}/jobs/{ended['id']}", marcus)
    assert gone.status_code == 404, gone.text


def test_a_failed_load_leaves_no_workspace(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    runtime: JobRuntime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """05 SBX-04 rev 1.64 (supervisor ruling R-43 (d)): a load that fails leaves no ACTIVE sandbox
    with the requester's membership. The reset's load of the seed is made to fail after the
    copied datasets — the requester's membership is in the successor by then. The job ends
    FAILED; the successor exists, holds that membership and is ``ARCHIVED`` with
    ``tenant.sandbox_load_failed``, so it cannot be opened; the sandbox the reset was to supersede
    is ``ACTIVE`` and untouched, the requester's session is still in it, and a reset can be
    asked again. While the load runs the successor is ``SUSPENDED``: never a workspace."""
    from erev_api.domain.platform import sandbox_periods

    marcus_in_production, _, _ = _controller_world(app, keyring, clock)
    copied = _copy(marcus_in_production, runtime, clock, "Failing")
    marcus = enter_workspace(app, clock, copied.requester, copied.sandbox_id)
    seen: dict[str, Any] = {}

    def failing(references: Mapping[str, Any]) -> Any:
        successor_id = UUID(accepted.headers["X-Erev-Sandbox-Tenant-Id"])
        seen["status"] = _tenant(successor_id)["status"]  # mid-load
        with tenant_session(_context(successor_id), read_only=True) as session:
            seen["memberships"] = session.execute(
                select(func.count())
                .select_from(tenant_membership)
                .where(
                    tenant_membership.c.user_id == marcus.member.user_id,
                    tenant_membership.c.status == "ACTIVE",
                )
            ).scalar_one()
        raise ValueError("planted inconsistency of the exported period states")

    accepted = _reset(app, marcus, mode="SNAPSHOT", reason=REASON)
    monkeypatch.setattr(sandbox_periods, "prepare", failing)
    ended = _run_reset(accepted, copied.sandbox_id, runtime)
    monkeypatch.undo()
    successor_id = UUID(accepted.headers["X-Erev-Sandbox-Tenant-Id"])
    assert ended["state"] == "FAILED", ended["result"]
    assert seen == {"status": "SUSPENDED", "memberships": 1}
    failed = _tenant(successor_id)
    assert (failed["kind"], failed["status"]) == ("sandbox", "ARCHIVED")
    (event,) = _events(successor_id, sb.ACTION_LOAD_FAILED)
    assert (event["before"], event["after"]) == ({"status": "SUSPENDED"}, {"status": "ARCHIVED"})
    assert _events(successor_id, sb.ACTION_LOADED) == []  # a failed load writes no summary
    assert _tenant(copied.sandbox_id)["status"] == "ACTIVE"
    assert _events(copied.sandbox_id, sandbox_reset.ACTION_RESET) == []
    assert _active_tenant_of(marcus.token) == copied.sandbox_id
    refused = select_tenant(app, Signed(marcus.token, marcus.csrf_token, {}), successor_id)
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    me = get(app, f"{API}/me", marcus)
    listed = {m["tenant"]["id"]: m["tenant"]["status"] for m in me.json()["memberships"]}
    assert listed[str(successor_id)] == "ARCHIVED" and listed[str(copied.sandbox_id)] == "ACTIVE"
    again = _reset(app, marcus, mode="SNAPSHOT", reason=REASON)
    assert again.status_code == 202, again.text  # the failed job no longer blocks a reset


def test_point_in_time_consumers_pass_where_no_period_is_blocked(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """05 SBX-04 (rev 1.20; rev 1.64), the positive control of the refusal a consumer needing
    point-in-time equivalence calls first: a production tenant and a sandbox loaded without a
    blocked period pass. The refusal itself — 412 ``SANDBOX_PERIODS_BLOCKED`` naming the blocked
    period states — is witnessed where a sandbox has one:
    ``test_sandbox_replay.py::test_blocked_periods_are_queryable_and_refuse_point_in_time_consumers``."""
    marcus_in_production, _, _ = _controller_world(app, keyring, clock)
    copied = _copy(marcus_in_production, runtime, clock, "Equivalent")
    for tenant_id in (copied.production_id, copied.sandbox_id):
        with tenant_session(_context(tenant_id), read_only=True) as session:
            sb.require_point_in_time(session, tenant_id)  # passes: nothing blocked
    with tenant_session(_context(copied.sandbox_id), read_only=True) as session:
        loaded = sb.sandbox_load_of(session, _tenant(copied.sandbox_id))
    assert loaded is not None and loaded["blocked_periods"] == []
    assert loaded["tenant_snapshot_id"] == copied.snapshot_id


def _listed(app: FastAPI, actor: Actor) -> list[str]:
    """The emails ``GET /users`` lists in ``actor``'s workspace, sorted: a person listed twice is
    here twice."""
    answered = get(app, f"{API}/users", actor, {"limit": 200})
    assert answered.status_code == 200, answered.text
    return sorted(str(item["email"]) for item in answered.json()["items"])


def _shown(app: FastAPI, actor: Actor, membership_id: UUID) -> tuple[int, str]:
    """``GET /users/{id}`` in ``actor``'s workspace: the status with the member's email, or with
    the problem."""
    answered = get(app, f"{API}/users/{membership_id}", actor)
    if answered.status_code == 200:
        return 200, str(answered.json()["email"])
    return answered.status_code, slug(answered)


def _answer(response: HttpResponse, *members: str) -> tuple[Any, ...]:
    """The status of a response with the named members of its body, or with the problem."""
    if response.status_code >= 400:
        return response.status_code, slug(response)
    body = response.json()
    return (response.status_code, *(body[member] for member in members))


def _review_started(
    app: FastAPI, clock: FrozenClock, actor: Actor, reviewer_membership_id: UUID
) -> tuple[Any, ...]:
    """``POST /access-reviews`` and its ``/start`` by ``actor``: the status of the start with the
    item counts, and the emails the review took an item for, sorted."""
    created = post(
        app,
        f"{API}/access-reviews",
        actor,
        {
            "name": "Q3 2026 access review",
            "as_of": clock.now().isoformat(),
            "reviewer_membership_ids": [str(reviewer_membership_id)],
        },
    )
    assert created.status_code == 201, created.text
    review = f"{API}/access-reviews/{created.json()['id']}"
    started = post(app, f"{review}/start", actor, {})
    items = get(app, f"{review}/items", actor, {"limit": 200})
    assert items.status_code == 200, items.text
    return (
        *_answer(started, "counts"),
        sorted(str(item["user_email_snapshot"]) for item in items.json()["items"]),
    )


def _pending(members: int) -> dict[str, int]:
    """The item counts of a review that has just started."""
    return {
        "members": members,
        "pending": members,
        "certified": 0,
        "revoke_requested": 0,
        "revoked": 0,
    }


def _tenant_admin(app: FastAPI, clock: FrozenClock, tenant_id: UUID, name: str) -> Actor:
    """A signed-in member who holds Tenant Admin and nothing else."""
    someone = colleague(tenant_id, name)
    assign(someone, "tenant_admin")
    return enrolled(app, clock, someone)


def test_the_members_of_a_workspace_are_its_own_beside_its_copies(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """Item USERS-MEMBER-TENANT-1 (04 §1.4 RLS-TM rev 1.272; dev-guide DG-KRN-DB-12): ``GET
    /users`` lists the members of the workspace, ``GET /users/{id}`` shows one of them, and an
    access review takes an item for each of them — and for nobody else.

    A person's transaction reads their own memberships of EVERY workspace beside the members of
    the one it is in (RLS-TM: the workspace picker needs them), and a loaded sandbox keeps the
    membership ids of its source. A statement that read the members without naming the tenant
    returned both. Production here has four members and two sandboxes: a loaded copy, and a
    second copy that Marcus reset to EMPTY, where Marcus is the only member, under a new id.

    Fail-first (main a101c4c0 as merged at 2c663b49, the statements without the tenant): every
    fact below differed. Tomas — Tenant Admin of production, so a member of its copies — was
    listed three times in production and in the loaded copy, and Marcus four times in each of
    the three workspaces: once per workspace either belongs to, the archived copy included.
    Tomas's own membership answered 500 in production and in the copy, several rows under one
    id; the EMPTY sandbox's membership was shown in production, 200, and production's answered
    500 in the EMPTY sandbox; and the start of an access review in the EMPTY sandbox answered
    500."""
    marcus, cora, maya = _controller_world(app, keyring, clock)
    production_id = marcus.member.tenant_id
    tomas = _tenant_admin(app, clock, production_id, "tomas")
    people = sorted(someone.member.email for someone in (marcus, cora, maya, tomas))
    # Both copies before anyone signs in again: each cutoff sets the frozen clock to the
    # database's, and a clock that has stepped past it for a sign-in would go back.
    loaded = _copy(marcus, runtime, clock, "Listed members")
    scratch = _copy(marcus, runtime, clock, "Listed members, emptied", retained=True)
    in_scratch = enter_workspace(app, clock, marcus, scratch.sandbox_id)
    ended = _run_reset(
        _reset(app, in_scratch, mode="EMPTY", reason=REASON), scratch.sandbox_id, runtime
    )
    assert ended["state"] == "SUCCEEDED", ended["problem"]
    empty_id = UUID(ended["result"]["sandbox_tenant_id"])
    with tenant_session(_context(empty_id), read_only=True) as session:
        only = UUID(str(session.execute(select(tenant_membership.c.id)).scalar_one()))
    assert only != marcus.member.membership_id  # a new membership, not a copied one

    marcus_in_production = enter_workspace(app, clock, marcus, production_id)
    marcus_in_copy = enter_workspace(app, clock, marcus, loaded.sandbox_id)
    marcus_in_empty = enter_workspace(app, clock, marcus, empty_id)
    tomas_in_production = enter_workspace(app, clock, tomas, production_id)
    tomas_in_copy = enter_workspace(app, clock, tomas, loaded.sandbox_id)
    own = tomas.member.membership_id
    assert {
        "production lists, for Tomas": _listed(app, tomas_in_production),
        "the loaded copy lists, for Tomas": _listed(app, tomas_in_copy),
        "production lists, for Marcus": _listed(app, marcus_in_production),
        "the loaded copy lists, for Marcus": _listed(app, marcus_in_copy),
        "the EMPTY sandbox lists, for Marcus": _listed(app, marcus_in_empty),
        "Tomas in production": _shown(app, tomas_in_production, own),
        "Tomas in the loaded copy": _shown(app, tomas_in_copy, own),
        "the EMPTY sandbox's member, asked in production": _shown(app, marcus_in_production, only),
        "production's member, asked in the EMPTY sandbox": _shown(
            app, marcus_in_empty, marcus.member.membership_id
        ),
        "an access review starts in the EMPTY sandbox": _review_started(
            app, clock, marcus_in_empty, only
        ),
    } == {
        "production lists, for Tomas": people,
        "the loaded copy lists, for Tomas": people,
        "production lists, for Marcus": people,
        "the loaded copy lists, for Marcus": people,
        "the EMPTY sandbox lists, for Marcus": [marcus.member.email],
        "Tomas in production": (200, tomas.member.email),
        "Tomas in the loaded copy": (200, tomas.member.email),
        "the EMPTY sandbox's member, asked in production": (404, "not-found"),
        "production's member, asked in the EMPTY sandbox": (404, "not-found"),
        "an access review starts in the EMPTY sandbox": (200, _pending(1), [marcus.member.email]),
    }


def test_a_member_of_a_workspace_and_its_copy_is_one_member_in_each(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """Item USERS-MEMBER-TENANT-1: the commands and lists that read ONE membership by its id
    read the workspace's. Tomas is Tenant Admin of production; its loaded copy holds the same
    membership under the same id, and Tomas's transaction reads both rows (RLS-TM). What Tomas
    asks about that membership is answered as it is for any other member — in production, and
    the same from inside the copy.

    Fail-first (the same tree): in both workspaces each of the four answered 500 — the role request
    and the exception request where they read the member (``roles.assign_role``,
    ``sod._member``: two rows where one is asked for), the approvals list where the filter
    ``preparer`` turns the membership into its user (one row asked of two), and the
    start of an access review, which took an item for each row it read
    (``access_reviews.snapshot_memberships``)."""
    marcus, cora, maya = _controller_world(app, keyring, clock)
    production_id = marcus.member.tenant_id
    tomas = _tenant_admin(app, clock, production_id, "tomas")
    people = sorted(someone.member.email for someone in (marcus, cora, maya, tomas))
    loaded = _copy(marcus, runtime, clock, "One member in each")
    own = tomas.member.membership_id
    with tenant_session(_context(production_id), read_only=True) as session:
        viewer = session.execute(select(role.c.id).where(role.c.code == "viewer")).scalar_one()

    def asked(tenant_id: UUID) -> dict[str, tuple[Any, ...]]:
        """What Tomas is answered about Tomas's own membership in the workspace."""
        actor = enter_workspace(app, clock, tomas, tenant_id)
        requested = post(
            app,
            f"{API}/role-assignments",
            actor,
            {"membership_id": str(own), "role_id": str(viewer), "is_all_entities": True},
        )
        prepared = get(app, f"{API}/approvals", actor, {"preparer": str(own)})
        excepted = post(
            app,
            f"{API}/sod-exceptions",
            actor,
            {
                "sod_rule_code": "SoD-1",
                "membership_id": str(own),
                "compensating_control": (
                    "The Controller reviews every role Tomas grants, monthly, from the listing."
                ),
                "valid_from": clock.now().isoformat(),
                "valid_to": (clock.now() + timedelta(days=90)).isoformat(),
                "comment": "Small team until a second administrator joins",
            },
        )
        return {
            "Viewer for the member's own membership": _answer(requested, "member_name", "status"),
            "the requests the member prepared": (
                prepared.status_code,
                [item["subject"]["type"] for item in prepared.json().get("items", [])],
            ),
            "an exception for the member's own membership": _answer(
                excepted, "member_name", "status"
            ),
            "an access review starts": _review_started(
                app, clock, actor, marcus.member.membership_id
            ),
        }

    expected = {
        "Viewer for the member's own membership": (201, "Tomas", "REQUESTED"),
        "the requests the member prepared": (200, ["ROLE_ASSIGNMENT"]),
        "an exception for the member's own membership": (201, "Tomas", "REQUESTED"),
        "an access review starts": (200, _pending(4), people),
    }
    assert {
        "production": asked(production_id),
        "the loaded copy": asked(loaded.sandbox_id),
    } == {"production": expected, "the loaded copy": expected}


def test_a_member_of_a_workspace_and_its_copy_is_told_once(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, runtime: JobRuntime
) -> None:
    """Item USERS-MEMBER-TENANT-1: ``notifications.notify`` reads the recipients' memberships of
    the workspace. Marcus — the bootstrap Tenant Admin of production, and so a member of its
    loaded copy under the same id — chose the email of an approval and not its in-app notice. A
    grant Marcus makes while setup is incomplete is approved by rule ``AUTO-BOOTSTRAP`` inside
    Marcus's own request, which tells Marcus of it: once.

    Fail-first (main a101c4c0 as merged at 2c663b49, the statement without the tenant): two
    emails, one for each membership row read under the one id. With the in-app notice on, the
    second recipient is merged away (PRD NTF-R1), which is why the other witnesses did not see
    it."""
    marcus, _, maya = _controller_world(app, keyring, clock)
    production_id = marcus.member.tenant_id
    _copy(marcus, runtime, clock, "Told once")
    marcus_in_production = enter_workspace(app, clock, marcus, production_id)
    stored = put(
        app,
        f"{API}/me/notification-preferences",
        marcus_in_production,
        {"items": [{"kind": "ITEM_APPROVED", "in_app": False, "email": True}]},
    )
    assert stored.status_code == 200, stored.text
    granted = _viewer_granted(app, marcus_in_production, production_id, maya.member.membership_id)
    with tenant_session(_context(production_id), read_only=True) as session:
        emails = sorted(
            str(payload["subject"])
            for (payload,) in session.execute(
                select(outbox_message.c.payload).where(outbox_message.c.topic == "EMAIL")
            )
            if payload.get("to") == marcus.member.email
            and str(payload["subject"]).startswith("Approved")
        )
    assert (granted, emails) == ((201, "ACTIVE", True), ["Approved: Grant Viewer to Maya"])
