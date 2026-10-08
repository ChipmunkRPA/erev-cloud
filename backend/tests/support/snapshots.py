"""Snapshot test support (lane F-SNP; record §13.2.24): the retention confirmation ruling D-98
candidate 86 requires, built in the order the database admits.

``confirm_retention`` walks a TENANT ``registry_version`` carrying
``platform.snapshot_retention_families`` through ``DRAFT → TESTED → SUBMITTED`` with one content
hash, opens its approval request ``PENDING`` for subject ``REGISTRY_VERSION`` with that hash and an
``ACTIVE`` step, records the human ``APPROVE`` decision (an ``ACTIVE`` member of the tenant, never
the SYSTEM preparer; the request's hash; ``mfa_verified_at`` set — the DB-10 trigger of migration
0013 checks each of these), then closes step and request (``ACTIVE → APPROVED``,
``PENDING → APPROVED``, the DB-03 pairs) and publishes the version with ``published_at`` and
``published_by`` = the approver. ``human=False`` publishes the version with **no decision at all
and no publisher** (request ``APPROVED``, step left ``ACTIVE``) — the narrower
missing-human-evidence case; it is not the shape ``approvals.engine.record_auto_approval`` leaves,
which writes a SYSTEM
``AUTO_APPROVE`` decision and approves the step (Codex I55-DOC1; that shape is pinned by the pure
test and a DB-bound case is owed) — so ``TENANT_SNAPSHOT`` refuses ``RETENTION_UNCONFIRMED``. No
trigger is disabled, no rule relaxed. WRITTEN, NOT RUN: the lane databases are Ray-side.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Final
from uuid import UUID

from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    approval_decision,
    approval_request,
    approval_step,
    audit_event,
    registry_version,
    tenant_membership,
)
from erev_api.db.tables import job as job_table
from erev_api.domain.close import commands as close
from erev_api.domain.contracts import computation
from erev_api.domain.imports import exceptions
from erev_api.domain.journals import subledger
from erev_api.domain.platform import sandboxes as sb
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.domain.reference import periods as period_rules
from erev_api.enums import (
    ApprovalRequestStatus,
    ApprovalStepStatus,
    ApprovalSubjectType,
    ConfigStatus,
    JobKind,
    PrincipalKind,
    RegistryCategory,
    RegistryScope,
)
from erev_api.jobs import registry
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from sqlalchemy import func, insert, select, text, update
from sqlalchemy.orm import Session
from support.rows import (
    approval_decision_values,
    insert_approval_request,
    insert_approval_step,
    registry_version_values,
)

_FETCHED = text("UPDATE procrastinate_jobs SET status = 'doing' WHERE id = :id")


def active_member(session: Session, tenant_id: UUID) -> UUID:
    """A user with an ACTIVE membership in the tenant (the approver the DB-10 trigger admits)."""
    return UUID(
        str(
            session.execute(
                select(tenant_membership.c.user_id)
                .where(
                    tenant_membership.c.tenant_id == tenant_id,
                    tenant_membership.c.status == "ACTIVE",
                )
                .order_by(tenant_membership.c.created_at)
                .limit(1)
            ).scalar_one()
        )
    )


def confirm_retention(
    session: Session,
    tenant_id: UUID,
    *,
    at: datetime,
    human: bool = True,
    effective_from: datetime | None = None,
) -> UUID:
    """The confirming registry version, approved and published at ``at`` and in force from
    ``effective_from`` — from ``at`` when none is given; returns its id. Like a version the
    product's commands make, it holds the whole PLATFORM value set (04 T-PLT-32 "Whole value
    set"): the published values with the retention families."""
    table = registry_version
    key = [
        table.c.tenant_id == tenant_id,
        table.c.category == RegistryCategory.PLATFORM.value,
        table.c.scope == RegistryScope.TENANT.value,
        table.c.book_code.is_(None),
        table.c.entity_id.is_(None),
    ]
    highest = session.execute(select(func.max(table.c.version_no)).where(*key)).scalar_one()
    published = (
        session.execute(
            select(table.c.id, table.c["values"]).where(
                *key, table.c.status == ConfigStatus.PUBLISHED.value
            )
        )
        .mappings()
        .one_or_none()
    )
    current = None if published is None else published["id"]
    if current is not None:
        session.execute(
            update(table)
            .where(table.c.id == current)
            .values(status=ConfigStatus.SUPERSEDED.value, effective_to=effective_from or at)
        )
    content = secrets.token_hex(32)
    version = registry_version_values(
        tenant_id,
        category=RegistryCategory.PLATFORM,
        scope=RegistryScope.TENANT,
        values={
            **({} if published is None else published["values"]),
            sd.RETENTION_PARAMETER: dict(sd.RETENTION_FAMILIES),
        },
        version_no=int(highest or 0) + 1,
        effective_from=effective_from or at,
        supersedes_version_id=current,
    )
    version_id = UUID(str(version["id"]))
    session.execute(insert(table).values(**version))
    where = table.c.id == version_id
    session.execute(
        update(table).where(where).values(status=ConfigStatus.TESTED.value, content_sha256=content)
    )
    session.execute(update(table).where(where).values(status=ConfigStatus.SUBMITTED.value))
    # the approval request opens PENDING for the version with the same hash and an ACTIVE step
    request_id = insert_approval_request(
        session,
        tenant_id=tenant_id,
        status=ApprovalRequestStatus.PENDING,
        subject_type=ApprovalSubjectType.REGISTRY_VERSION.value,
        subject_id=version_id,
        subject_content_sha256=content,
        current_step_no=1,
        submitted_at=at,
    )
    step_id = insert_approval_step(
        session,
        tenant_id=tenant_id,
        approval_request_id=request_id,
        step_no=1,
        status=ApprovalStepStatus.ACTIVE,
        required_permission="config.approve",
        activated_at=at,
    )
    approver: UUID | None = None
    if human:
        approver = active_member(session, tenant_id)
        session.execute(
            insert(approval_decision).values(
                **approval_decision_values(
                    tenant_id,
                    approval_request_id=request_id,
                    approval_step_id=step_id,
                    approver_id=approver,
                    subject_content_sha256=content,
                    mfa_verified_at=at,
                    decided_at=at,
                )
            )
        )
        session.execute(
            update(approval_step)
            .where(approval_step.c.id == step_id)
            .values(status=ApprovalStepStatus.APPROVED.value, completed_at=at)
        )
    # the request closes APPROVED (with the human decision, or — human=False — with none at all)
    session.execute(
        update(approval_request)
        .where(approval_request.c.id == request_id)
        .values(status=ApprovalRequestStatus.APPROVED.value, decided_at=at)
    )
    session.execute(
        update(table)
        .where(where)
        .values(status=ConfigStatus.APPROVED.value, approval_request_id=request_id)
    )
    session.execute(
        update(table)
        .where(where)
        .values(status=ConfigStatus.PUBLISHED.value, published_at=at, published_by=approver)
    )
    return version_id


def load_outcome(counts: Mapping[str, Any]) -> str:
    """The outcome of a sandbox load in one short line, for an assertion message (pytest cuts a
    long mapping): a recompute that ended FAILED or QUARANTINED shows as ``not recomputed`` — and
    as one ONE-SIDED mismatch per book of its group — which is not a differing result."""
    return (
        f"groups recomputed {counts.get('groups_recomputed')}, "
        f"not recomputed {counts.get('groups_not_recomputed')}, "
        f"mismatches {counts.get('derived_mismatches')}, "
        f"blocked periods {counts.get('blocked_periods')}"
    )


def cutoff_after(tenant_id: UUID, clock: FrozenClock) -> datetime:
    """The snapshot cutoff of a world that is complete: the DATABASE clock, read now, with the
    injected application clock moved to it. A test world lives on two clocks — the frozen
    application clock stamps what the product writes from ``uow.now``, while the database clock
    (real time, later) stamps DB-08 ``recorded_at`` and every ``created_at`` a directly inserted
    row leaves to its default. The ``known_at`` cutoff (04 T-PLT-34; ruling Q-6) keeps only what
    was recorded at or before it, and the SNP-1 params check refuses a ``known_at`` later than
    now, so a cutoff on the frozen clock silently cuts the database-stamped part of the world.
    The cutoff is therefore taken from the database AFTER the world and the clock follows — the
    ``test_known_at_cutoff`` precedent of ``tests/domain/platform/test_snapshots.py``."""
    ctx = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        known_at: datetime = session.execute(text("SELECT now()")).scalar_one()
    clock.set(known_at)
    return known_at


def run_dispatched_snapshot(
    tenant_id: UUID, params: dict[str, object], *, runtime: JobRuntime, now: datetime
) -> dict[str, object]:
    """The persisted dispatch path (Codex PREP-S1): insert the TENANT_SNAPSHOT job QUEUED, dispatch
    it, mark its task fetched as the worker does, run it through ``run_job`` — which catches the
    handler's refusal, ends the job FAILED with its problem and runs ``on_failure`` — and return
    the job row (``state``, ``problem``). ``registry.run_inline`` never does this: it calls the
    handler directly and lets the refusal escape."""
    ctx = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(ctx) as session:
        row = registry.insert_job(
            session,
            JobKind.TENANT_SNAPSHOT,
            params,
            tenant_id=tenant_id,
            now=now,
            created_by=None,
            created_by_kind=PrincipalKind.SYSTEM,
        )
        registry.dispatch(
            session, job_id=row["id"], tenant_id=tenant_id, queue=str(row["queue"]), now=now
        )
        job_id = UUID(str(row["id"]))
    with tenant_session(ctx) as session:
        task_id = session.execute(
            select(job_table.c.procrastinate_job_id).where(job_table.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    run_job(job_id, tenant_id, attempt=1, runtime=runtime)
    with tenant_session(ctx, read_only=True) as session:
        return dict(
            session.execute(select(job_table).where(job_table.c.id == job_id)).mappings().one()
        )


# --- 04 §1.5: the immutability class of the copied tables -----------------------------------------

_DATA_MODEL: Final = Path(__file__).resolve().parents[3] / "docs/04-DATA_MODEL.md"


def immutability_classes() -> dict[str, str]:
    """The 04 ``Class.`` of every LOAD_ORDER table, read from its table section: IM-A, IM-S, IM-P,
    ``IM-P child``, IM-M or IM-X. The snapshot guards decide from it which columns a fixup UPDATE
    can never restore."""
    sections = re.split(r"\n### T-[A-Z]+-\d+ `([a-z_]+)`", _DATA_MODEL.read_text(encoding="utf-8"))
    classes: dict[str, str] = {}
    for index in range(1, len(sections), 2):
        name, body = sections[index], sections[index + 1].split("\n### ")[0]
        found = re.search(r"- \*\*Class\.\*\* (IM-[A-Z](?: child)?)", body)
        if name in sd.LOAD_ORDER and found is not None:
            classes[name] = found.group(1)
    return classes


# --- 05 SBX-06 rev 1.34 (supervisor ruling R-7): the load's audit events in the sandbox -----------

# What a load writes into the sandbox's audit chain BEFORE its summary event: its own period replay
# and its own recompute, nothing else. Enumerated from the code that writes them — never a
# wildcard, so a new writer on either path is named here first.
LOAD_REPLAY_ACTIONS: Final = frozenset(
    {
        period_rules.CREATE_TRANSITIONS_ACTION,  # sandbox_periods._create_states
        period_rules.OPEN_ACTION,  # sandbox_periods._open
        close.START_CLOSE_ACTION,  # sandbox_periods._move
        close.CANCEL_CLOSE_ACTION,
        # sandbox_periods._lock / _reopen / _permanent_lock. No load reaches a lock before SNP-2b
        # (ruling R-10); the lane that makes the path reachable adds what its freeze, gate-result,
        # reconciliation and re-lock report writers record.
        close.LOCK_ACTION,
        close.REOPEN_ACTION,
        close.PERMANENT_LOCK_ACTION,
    }
)
LOAD_RECOMPUTE_ACTIONS: Final = frozenset(
    {
        # computation.persist (the computation and its facts); compute_job._refused (a QUARANTINED
        # or FAILED computation is stored too)
        *(
            f"{name}.{computation.CREATE}"
            for name in (
                computation.COMPUTATION_OBJECT,
                computation.VERSION_OBJECT,
                computation.TRACE_OBJECT,
                computation.OBLIGATION_VERSION_OBJECT,
                computation.BALANCE_OBJECT,
                computation.SCHEDULE_OBJECT,
                computation.SCHEDULE_LINE_OBJECT,
                "fx_layer_movement",
                "loss_provision_version",
                "loss_provision_eac",
            )
        ),
        # subledger.post (the computation's ENGINE_COMPUTE posting)
        *(
            f"{name}.create"
            for name in (subledger.POSTING_OBJECT, subledger.LINE_OBJECT, subledger.SEAL_OBJECT)
        ),
        # the recompute's diagnostics (raise_exception_item): a new item, or a copied open item of
        # the same finding re-evaluated at another severity
        exceptions.CREATE_ACTION,
        exceptions.SEVERITY_ACTION,
    }
)
_REPLAY: Final = "replay"
_RECOMPUTE: Final = "recompute"
_REPORT: Final = "report"


@dataclass(frozen=True, slots=True)
class LoadChain:
    """A loaded sandbox's audit chain around the load's single summary event."""

    before: tuple[Mapping[str, Any], ...]  # chain order
    summary: Mapping[str, Any]  # ``tenant.snapshot_loaded``
    after: tuple[Mapping[str, Any], ...]

    def of(self, action: str) -> tuple[Mapping[str, Any], ...]:
        """The events before the summary with ``action``, in chain order."""
        return tuple(event for event in self.before if event["action"] == action)


def load_chain(sandbox_id: UUID) -> LoadChain:
    """The sandbox's whole audit chain split at ``tenant.snapshot_loaded``; ``ValueError`` unless
    the chain holds EXACTLY one such event (05 SBX-06 rev 1.34: the load's single summary)."""
    ctx = DbContext(tenant_id=sandbox_id, user_id=None, entity_scope="*")
    with tenant_session(ctx, read_only=True) as session:
        events = [
            dict(row)
            for row in session.execute(
                select(
                    audit_event.c.chain_seq,
                    audit_event.c.action,
                    audit_event.c.object_type,
                    audit_event.c.object_id,
                    audit_event.c.request_id,
                    audit_event.c.actor_kind,
                    audit_event.c.detail,
                ).order_by(audit_event.c.chain_seq)
            ).mappings()
        ]
    found = [index for index, event in enumerate(events) if event["action"] == sb.ACTION_LOADED]
    if len(found) != 1:
        raise ValueError(f"the sandbox chain holds {len(found)} {sb.ACTION_LOADED} events, not one")
    (at,) = found
    return LoadChain(tuple(events[:at]), events[at], tuple(events[at + 1 :]))


def load_step(event: Mapping[str, Any], job_id: object) -> str | None:
    """The step of load job ``job_id`` that wrote ``event``, by the request id its transaction
    carried (``job-<job id>-<step>``): ``replay`` (``periods``, ``replay-<transition>``),
    ``recompute`` (``recompute-<group>``) or ``report``; None for anything else."""
    prefix = f"job-{job_id}-"
    request_id = str(event["request_id"])
    if not request_id.startswith(prefix):
        return None
    step = request_id.removeprefix(prefix)
    if step == "periods" or step.startswith("replay-"):
        return _REPLAY
    if step.startswith("recompute-"):
        return _RECOMPUTE
    return _REPORT if step == _REPORT else None


def unexplained_load_events(chain: LoadChain, job_id: object) -> list[Mapping[str, Any]]:
    """The events of a loaded sandbox's chain that the load's own steps do NOT explain (05 SBX-06
    rev 1.34; ruling R-7) — empty for a sound load. Before the summary: anything but an enumerated
    replay action written by the period replay, or an enumerated recompute action written by a
    group's recompute. The summary itself unless the report step wrote it. After it: anything but
    the creation of the warning items the report step raises in the same transaction."""
    allowed = {_REPLAY: LOAD_REPLAY_ACTIONS, _RECOMPUTE: LOAD_RECOMPUTE_ACTIONS}
    unexplained = [
        event
        for event in chain.before
        if event["action"] not in allowed.get(load_step(event, job_id) or "", frozenset())
    ]
    if load_step(chain.summary, job_id) != _REPORT:
        unexplained.append(chain.summary)
    unexplained.extend(
        event
        for event in chain.after
        if load_step(event, job_id) != _REPORT or event["action"] != exceptions.CREATE_ACTION
    )
    return unexplained


# --- sandbox tenants and their jobs (BUILD_SPEC SNP-3, SNP-4) -------------------------------------


def seeded_sandbox(keyring: Any, clock: FrozenClock) -> UUID:
    """A bare sandbox tenant as a load's first steps leave it for an API scenario (05 SBX-04): the
    ``tenant`` row of kind ``sandbox`` (the kind is immutable, 04 T-PLT-01, so a provisioned
    production tenant cannot become one), its ``audit_chain_head`` and the ten system roles with
    their grants (the COPIED ``role`` / ``role_permission`` datasets; here the product's own
    ``default_role_rows``). It has no source tenant and holds no business row: enough for a member
    to hold a role, sign in and have a refusal audited."""
    from erev_api.db.session import name_platform_tenant, platform_session, set_tenant_context
    from erev_api.db.tables import audit_chain_head, role, role_permission
    from erev_api.domain.platform.provisioning import default_role_rows
    from support.rows import insert_sandbox_tenant

    sandbox = insert_sandbox_tenant(keyring)
    now = clock.now()
    stamp = {
        "created_at": now,
        "created_by": None,
        "created_by_kind": PrincipalKind.SYSTEM.value,
        "updated_at": now,
        "updated_by": None,
        "updated_by_kind": PrincipalKind.SYSTEM.value,
    }
    roles, grants = default_role_rows(sandbox, stamp=stamp)
    with platform_session(
        "provisioning", actor_user_id=None, request_id="tests-seeded-sandbox", keyring=keyring
    ) as session:
        name_platform_tenant(session, sandbox)
        set_tenant_context(session, DbContext(tenant_id=sandbox, user_id=None, entity_scope="*"))
        session.execute(insert(role), roles)
        session.execute(insert(role_permission), grants)
        session.execute(
            insert(audit_chain_head).values(tenant_id=sandbox, last_chain_seq=0, updated_at=now)
        )
    return sandbox


def work_job(tenant_id: UUID, job_id: UUID, runtime: JobRuntime) -> dict[str, Any]:
    """The worker fetches the job's task and runs it (the jobs API test's pattern); the job row
    afterwards."""
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        task_id = session.execute(
            select(job_table.c.procrastinate_job_id).where(job_table.c.id == job_id)
        ).scalar_one()
        session.execute(_FETCHED, {"id": task_id})
    run_job(job_id, tenant_id, attempt=1, runtime=runtime)
    with tenant_session(context, read_only=True) as session:
        return dict(
            session.execute(select(job_table).where(job_table.c.id == job_id)).mappings().one()
        )


def enter_workspace(app: Any, clock: FrozenClock, someone: Any, tenant_id: UUID) -> Any:
    """``someone`` (an enrolled ``support.principals.Actor``) signed in afresh, verified by TOTP at
    the clock's next step and with ``tenant_id`` opened through ``POST /session/tenant``: an
    ``Actor`` whose session is inside that workspace. A snapshot cutoff moves the frozen clock to
    the database's (``cutoff_after``), past the absolute limit of every session opened before it,
    so the members of a copied world sign in again to work in its sandbox."""
    from dataclasses import replace

    from erev_api.auth import totp
    from support.http import call
    from support.principals import (
        SESSION_MFA,
        Actor,
        cookie_headers,
        cookie_of,
        refreshed,
        select_tenant,
        sign_in,
    )

    assert someone.secret is not None
    clock.advance(totp.STEP)  # a code is accepted once per step (T-PLT-04 last_used_step)
    signed = sign_in(app, someone.member.email)
    verified = call(
        app,
        "POST",
        SESSION_MFA,
        json={"code": totp.code_at(someone.secret, totp.time_step(clock.now()))},
        headers=cookie_headers(signed.token, signed.csrf_token),
    )
    assert verified.status_code == 200, verified.text
    opened = select_tenant(app, refreshed(app, cookie_of(verified)), tenant_id)
    assert opened.status_code == 200, opened.text
    return Actor(
        member=replace(someone.member, tenant_id=tenant_id),
        token=cookie_of(opened),
        csrf_token=opened.json()["csrf_token"],
        secret=someone.secret,
    )
