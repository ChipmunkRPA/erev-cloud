"""PRF-2 ``erev perf seed`` acceptance (BUILD_SPEC PRF-2; DG-MK-perf-seed; DG-PERF-01, DG-PERF-06;
Codex 0105 P7-PRF2-PERSONA-1 / RESUME-1 / DB-WITNESS-1).

Database-bound: one ordered story over the session's test database, seeding a 1/1000-scale volume
tenant through the product's commands and reading back. ONE credential set, ONE frozen clock
(advanced past a TOTP step before every phase, so every sign-in verifies a fresh code), ONE file
store and runtime carry every phase. NOT RUN in the lane (the DB stage is Ray-side / the
supervisor's gates); `slow`.

The story seeds a manifest of SEVEN months (item PERF-SEED-LOCK-1; the supervisor's ruling of
2026-10-01): every month a seed locks is closed as a person closes it — the soft close, the close
run, the journal run, the lock — for four entity-books, and 23 months of that are not a test. Six
months are locked and the seventh is held back, as the dataset of 24 locks 23. Seven and not
fewer: the manifest's one estimate change falls in month 6, after run C's five months and inside
the locked ones, which run D's crash needs; and one event the generator records a month late
lies inside the six, so the waiver is witnessed where it happens.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from fractions import Fraction
from pathlib import Path
from typing import Any
from uuid import UUID

import pyotp
import pytest
from erev_api.adapters.gl.csv import CsvGl
from erev_api.auth.permissions import effective_grants
from erev_api.clock import FrozenClock
from erev_api.db.session import DbContext, platform_session, tenant_session
from erev_api.db.tables import (
    app_user,
    approval_decision,
    approval_request,
    close_run,
    contract,
    contract_computation,
    contract_event,
    contract_version,
    estimate_version,
    exception_item,
    job,
    journal_batch,
    journal_run,
    judgement_record,
    legal_entity,
    modification,
    period,
    period_lock,
    period_state,
    pob_template,
    pob_template_version,
    registry_version,
    tenant,
    tenant_membership,
    tenant_snapshot,
)
from erev_api.domain.demo import closing, perf_seed, volume
from erev_api.domain.demo.sessions import SeedSecrets
from erev_api.domain.journals import ports as gl_ports
from erev_api.enums import GlAdapter
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from sqlalchemy import and_, func, select
from support.clock import frozen_clock
from support.db import TestDatabase
from support.factories import stamp_test_release
from support.snapshots import cutoff_after

pytestmark = pytest.mark.slow
SCALE = Fraction(1, 1000)
MONTHS = 7  # the manifest's horizon here (module docstring); the dataset's is 24
LOCKED = MONTHS - 1  # the months a seed appends and locks: all but the manifest's last
FRESH_STEP = timedelta(seconds=90)  # three TOTP steps: never a reused or windowed code
# The entity-book and month whose close is interrupted (``_interrupted_lock_phase``): the first
# lock of the entity that holds the story's late event, where its waiver is asked.
CRASHED_ENTITY, CRASHED_BOOK, CRASHED_MONTH = "VOL-UK", "ASC606", 1


def _manifest() -> volume.VolumeManifest:
    return volume.manifest(SCALE, months=MONTHS)


@dataclass
class Shared:
    """The one credential set, clock, file store and runtime of the story (DB-WITNESS-1)."""

    keyring: Any
    root: Path
    clock: FrozenClock = field(default_factory=frozen_clock)
    secrets: SeedSecrets = field(
        default_factory=lambda: SeedSecrets(
            password=f"Seed-{secrets.token_urlsafe(12)}", totp_secret=pyotp.random_base32()
        )
    )

    def __post_init__(self) -> None:
        self.files = LocalFileStore(self.root / "files")
        self.runtime = JobRuntime(clock=self.clock, keyring=self.keyring, files=self.files)
        self.demo_before: dict[str, dict[str, int]] = {}
        self.events_appended = 0
        self.events_reused = 0
        self.persona_run: Any = None
        self.ids_before_d: set[str] | None = None  # persisted event ids right before run D
        self.ids_after_crash: set[str] | None = None  # persisted event ids right after run D
        self.crashed_event: volume.VolumeEvent | None = None  # the ACTUAL interrupted event
        self.crashed_identity: dict[str, Any] | None = None  # its version / applied events
        self.completion: perf_seed.PerfSeedResult | None = None
        self.c_appended: int | None = None  # run C's returned appended count (months 1-5)
        self.close_at_crash: dict[str, Any] | None = None  # the interrupted close, as persisted
        self.waivers_at_crash: list[dict[str, Any]] | None = None  # the late items, waiver asked
        self.lock_refused_at_crash: tuple[str, list[str]] | None = None  # slug, failing gates
        # The computations of the tenant (``_computations``) as run C left them — every period
        # open until its lock phase — and right before and after the completion, which finds
        # months 1 to 5 locked.
        self.computed_by_c: list[tuple[str, int]] | None = None
        self.computed_before_completion: list[tuple[str, int]] | None = None
        self.computed_by_completion: list[tuple[str, int]] | None = None
        # The exception items as the completed seed left them (``_open_items``, ``_late_items``),
        # before a later test of the story records anything in the tenant.
        self.items_after_seed: tuple[list[tuple[str, ...]], set[tuple[str, str]]] | None = None
        self.late_after_seed: list[dict[str, Any]] | None = None
        self.distinct_after_submit: dict[str, Any] | None = None  # B1: record + request ids
        self.distinct_after_review: dict[str, Any] | None = None  # B2: record + request ids
        self.draft_review: dict[str, Any] | None = None  # the separately created DRAFT record

    def services(self) -> perf_seed.Services:
        """A phase's services: the shared pieces, a fresh TOTP step, a new request id — and the
        engine release stamped, the composition root's part (05 REL-03): ``erev perf seed``
        stamps it at every invocation, and a snapshot is exported only by a stamped process
        (``snapshot_job.RELEASE_UNSTAMPED``, in every environment). Every phase stamps:
        ``tests/conftest.py`` forgets a stamp after every test, so one made when the module
        starts covers the phases of its first test alone. Computing tolerates an unstamped
        process in the test environment; step 5 stopped there."""
        stamp_test_release()
        self.clock.advance(FRESH_STEP)
        return perf_seed.Services(
            clock=self.clock,
            keyring=self.keyring,
            files=self.files,
            runtime=self.runtime,
            secrets=self.secrets,
            request_id=f"prf2-{secrets.token_hex(4)}",
            os_user="pytest",
        )

    def run(self, **kwargs: Any) -> perf_seed.PerfSeedResult:
        result = perf_seed.run(
            self.services(),
            reports_dir=self.root / "reports",
            scale=SCALE,
            months=MONTHS,
            **kwargs,
        )
        self.events_appended += result.events_appended
        self.events_reused += result.events_reused
        return result

    def context(self) -> Any:
        """The seed's own command context over the signed-in cast (perf_seed.build_context), for
        the witnesses that drive the per-event paths directly."""
        from erev_api.domain.demo.sessions import PersonaRun

        services = self.services()
        tenant_id = _perf_tenant_id()
        run = PersonaRun(
            clock=services.clock,
            keyring=services.keyring,
            files=services.files,
            secrets=services.secrets,
            request_id=services.request_id,
        )
        perf_seed._sign_in_existing(services, run, tenant_id)  # noqa: SLF001
        self.persona_run = run
        return perf_seed.build_context(services, run, tenant_id), services


class Interrupted(RuntimeError):
    """The simulated crash of a seeding run."""


def _demo_populations() -> dict[str, dict[str, int]]:
    """Per demo tenant (every tenant but perf-volume): contracts, events and snapshots."""
    with platform_session("tenant_directory", actor_user_id=None, request_id="prf2-demo") as db:
        rows = db.execute(
            select(tenant.c.id, tenant.c.code).where(tenant.c.code != perf_seed.TENANT_CODE)
        ).all()
    populations: dict[str, dict[str, int]] = {}
    for tenant_id, code in rows:
        scope = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
        with tenant_session(scope, read_only=True) as db:
            populations[str(code)] = {
                table.name: int(db.execute(select(func.count()).select_from(table)).scalar_one())
                for table in (contract, contract_event, tenant_snapshot)
            }
    return populations


def _event_ids() -> set[str]:
    """The persisted contract_event ids of perf-volume (durable event identity)."""
    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        return {str(value) for value in db.execute(select(contract_event.c.id)).scalars()}


def _estimate_identity(event: volume.VolumeEvent) -> dict[str, Any]:
    """The durable identity of one manifest ESTIMATE_CHANGED event: the version carrying its
    marker (id, status, applied_event_ids) — read from the database, exactly one row expected."""
    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        rows = (
            db.execute(
                select(
                    estimate_version.c.id,
                    estimate_version.c.status,
                    estimate_version.c.applied_event_ids,
                ).where(estimate_version.c.rationale == volume.estimate_rationale(event))
            )
            .mappings()
            .all()
        )
    assert len(rows) == 1, f"{len(rows)} versions carry the marker of event {event.seq}"
    row = rows[0]
    return {
        "version_id": str(row["id"]),
        "status": str(row["status"]),
        "applied_event_ids": sorted(str(value) for value in (row["applied_event_ids"] or [])),
    }


def _computations() -> list[tuple[str, int]]:
    """The computations of the tenant in the order they were made — a computation's id is
    time-ordered — each as the external id of its group's contract and the number of events it
    was the first to include: the cause events of its contract versions, none for a
    recomputation that no new event caused."""
    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        members = db.execute(select(contract.c.combination_group_id, contract.c.external_id)).all()
        names = {str(group_id): str(external_id) for group_id, external_id in members}
        assert len(names) == len(members)  # the dataset combines no contracts: one a group
        included: dict[str, int] = {}
        for computation_id, cause_event_ids in db.execute(
            select(contract_version.c.contract_computation_id, contract_version.c.cause_event_ids)
        ):
            key = str(computation_id)
            included[key] = included.get(key, 0) + len(cause_event_ids or ())
        rows = db.execute(
            select(contract_computation.c.id, contract_computation.c.combination_group_id).order_by(
                contract_computation.c.id
            )
        ).all()
    return [(names[str(group_id)], included.get(str(row_id), 0)) for row_id, group_id in rows]


def _snapshot_facts(snapshot_id: Any) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """What step 5 left: the snapshot's row — its purpose, status and target, who asked for it
    and the state of the job her request deferred — and the tenant's ``TENANT_SNAPSHOT`` jobs
    that have not ended, each as kind and state."""
    users = _users()
    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        row = db.execute(
            select(
                tenant_snapshot.c.purpose,
                tenant_snapshot.c.status,
                tenant_snapshot.c.target_tenant_id,
                tenant_snapshot.c.created_by,
                tenant_snapshot.c.job_id,
            ).where(tenant_snapshot.c.id == snapshot_id)
        ).one()
        state = db.execute(select(job.c.state).where(job.c.id == row.job_id)).scalar_one()
        waiting = db.execute(
            select(job.c.kind, job.c.state)
            .where(job.c.kind == "TENANT_SNAPSHOT", job.c.state.in_(["QUEUED", "RUNNING"]))
            .order_by(job.c.created_at)
        ).all()
    facts = {
        "purpose": str(row.purpose),
        "status": str(row.status),
        "target_tenant_id": row.target_tenant_id,
        "requested_by": users.get(str(row.created_by)),
        "job_state": str(state),
    }
    return facts, [(str(kind), str(job_state)) for kind, job_state in waiting]


def _persisted_by_type() -> dict[str, int]:
    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        rows = db.execute(
            select(contract_event.c.event_type, func.count()).group_by(contract_event.c.event_type)
        ).all()
    return {str(kind): int(count) for kind, count in rows}


def _is_distinct_review(judgement_id: Any) -> bool:
    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        topic = db.execute(
            select(judgement_record.c.topic).where(judgement_record.c.id == judgement_id)
        ).scalar_one_or_none()
    return str(topic) == "POB_DISTINCT_OVERRIDE"


def _distinct_review_identity(judgement_id: str) -> dict[str, Any]:
    """The persisted record and its review requests: exactly one record, one request expected."""
    from erev_api.db.tables import approval_request

    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        record = (
            db.execute(
                select(
                    judgement_record.c.id,
                    judgement_record.c.subject_id,
                    judgement_record.c.status,
                    judgement_record.c.approval_request_id,
                ).where(judgement_record.c.id == judgement_id)
            )
            .mappings()
            .one()
        )
        siblings = int(
            db.execute(
                select(func.count())
                .select_from(judgement_record)
                .where(
                    judgement_record.c.subject_type == "obligation",
                    judgement_record.c.topic == "POB_DISTINCT_OVERRIDE",
                    judgement_record.c.subject_id == record["subject_id"],
                )
            ).scalar_one()
        )
        requests = db.execute(
            select(approval_request.c.id, approval_request.c.status).where(
                approval_request.c.subject_type == "JUDGEMENT_RECORD",
                approval_request.c.subject_id == judgement_id,
            )
        ).all()
    return {
        "status": str(record["status"]),
        "records_for_obligation": siblings,
        "request_ids": sorted(str(rid) for rid, _ in requests),
        "pending_request_ids": sorted(str(rid) for rid, st in requests if str(st) == "PENDING"),
        "approval_request_id": None
        if record["approval_request_id"] is None
        else str(record["approval_request_id"]),
    }


def _create_draft_distinct_review(shared: Shared) -> dict[str, Any]:
    """A DRAFT POB_DISTINCT_OVERRIDE record for the next distinct obligation without one, through
    the real generic judgement command as the accountant (the seed's own context)."""
    from erev_api.domain.policies import judgements
    from erev_api.enums import JudgementTopic
    from erev_api.schemas.judgements import JudgementCreateIn

    manifest = _manifest()
    ctx, _services = shared.context()
    scope = DbContext(tenant_id=ctx.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        contract_ids = {
            str(external_id): row_id
            for external_id, row_id in db.execute(select(contract.c.external_id, contract.c.id))
        }
        from erev_api.db.tables import obligation

        obligation_ids = {
            (str(cid), str(key)): oid
            for cid, key, oid in db.execute(
                select(obligation.c.contract_id, obligation.c.obligation_key, obligation.c.id)
            )
        }
        reviewed_subjects = {
            str(value)
            for value in db.execute(
                select(judgement_record.c.subject_id).where(
                    judgement_record.c.subject_type == "obligation",
                    judgement_record.c.topic == "POB_DISTINCT_OVERRIDE",
                )
            ).scalars()
        }
    target: tuple[Any, Any, str] | None = None
    for spec in manifest.contracts:
        contract_id = contract_ids.get(spec.external_id)
        if contract_id is None:
            continue
        for key in volume.distinct_reviews_needed(manifest, spec):
            oid = obligation_ids[(str(contract_id), key)]
            if str(oid) not in reviewed_subjects:
                target = (contract_id, oid, key)
                break
        if target is not None:
            break
    assert target is not None, "an unreviewed distinct obligation is needed for the DRAFT witness"
    contract_id, obligation_id, obligation_key = target
    with ctx.command(volume.PERF_CAST.accountant, volume.JUDGEMENT_CREATE) as uow:
        created = judgements.create_judgement(
            uow,
            body=JudgementCreateIn(
                topic=JudgementTopic.POB_DISTINCT_OVERRIDE,
                subject_type="obligation",
                subject_id=obligation_id,
                contract_id=contract_id,
                conclusion="distinct",
                rationale="DRAFT witness (Codex 0447): synthetic seed data, not a judgement.",
                # Codex 0522 §2: the topic's questionnaire (schemas/db_json.py
                # PobDistinctOverrideQuestionnaire) is validated before insertion.
                questionnaire={"obligation_key": obligation_key, "distinctness": "distinct"},
            ),
        )
    shared.persona_run.sign_out_all()
    identity = _distinct_review_identity(str(created.id))
    assert identity["status"] == "DRAFT" and identity["request_ids"] == []
    return {"judgement_record_id": str(created.id), "obligation_id": str(obligation_id)}


def _perf_tenant_id() -> Any:
    with platform_session("tenant_directory", actor_user_id=None, request_id="prf2-read") as db:
        return db.execute(
            select(tenant.c.id).where(tenant.c.code == perf_seed.TENANT_CODE)
        ).scalar_one()


def _users() -> dict[str, str]:
    """User id → persona key of the perf cast."""
    emails = {persona.email: persona.key for persona in perf_seed.CAST}
    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        rows = db.execute(
            select(app_user.c.id, app_user.c.email).where(app_user.c.email.in_(sorted(emails)))
        ).all()
    return {str(user_id): emails[str(email)] for user_id, email in rows}


def _requests(db: Any, subject_type: str, subject_ids: list[Any]) -> list[dict[str, Any]]:
    """The approval requests of the subjects with who prepared and who decided each, by persona
    key, in submission order."""
    users = _users()
    rows = db.execute(
        select(
            approval_request.c.id,
            approval_request.c.subject_id,
            approval_request.c.status,
            approval_request.c.preparer_id,
            approval_request.c.comment,
        )
        .where(
            approval_request.c.subject_type == subject_type,
            approval_request.c.subject_id.in_(subject_ids),
        )
        .order_by(approval_request.c.submitted_at, approval_request.c.request_no)
    ).all()
    found = []
    for row in rows:
        deciders = db.execute(
            select(approval_decision.c.approver_id, approval_decision.c.decision)
            .where(approval_decision.c.approval_request_id == row.id)
            .order_by(approval_decision.c.decided_at, approval_decision.c.id)
        ).all()
        found.append(
            {
                "id": str(row.id),
                "subject_id": str(row.subject_id),
                "status": str(row.status),
                "preparer": users.get(str(row.preparer_id)),
                "comment": row.comment,
                "decisions": [
                    (users.get(str(approver_id)), str(decision))
                    for approver_id, decision in deciders
                ],
            }
        )
    return found


def _close_facts(entity_code: str, book: str, month: int) -> dict[str, Any]:
    """What the database holds of one period's close: the period's state, its close runs, its
    journal runs (cancelled ones too) with their batches, and its lock requests."""
    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        state = db.execute(
            select(period_state.c.id, period_state.c.state, period_state.c.period_id)
            .select_from(
                period_state.join(
                    period,
                    and_(
                        period.c.tenant_id == period_state.c.tenant_id,
                        period.c.id == period_state.c.period_id,
                    ),
                ).join(
                    legal_entity,
                    and_(
                        legal_entity.c.tenant_id == period_state.c.tenant_id,
                        legal_entity.c.id == period_state.c.entity_id,
                    ),
                )
            )
            .where(
                legal_entity.c.code == entity_code,
                period_state.c.book_code == book,
                period.c.start_date == volume.month_start(month),
            )
        ).one()
        entity_id = db.execute(
            select(legal_entity.c.id).where(legal_entity.c.code == entity_code)
        ).scalar_one()
        of_period = (
            journal_run.c.entity_id == entity_id,
            journal_run.c.book_code == book,
            journal_run.c.period_id == state.period_id,
        )
        runs = db.execute(
            select(journal_run.c.id, journal_run.c.state)
            .where(*of_period)
            .order_by(journal_run.c.created_at, journal_run.c.id)
        ).all()
        batches = db.execute(
            select(journal_batch.c.id, journal_batch.c.state, journal_batch.c.adapter)
            .where(journal_batch.c.journal_run_id.in_([run_id for run_id, _ in runs]))
            .order_by(journal_batch.c.batch_no, journal_batch.c.chunk_no)
        ).all()
        close_runs = db.execute(
            select(close_run.c.id, close_run.c.status)
            .where(
                close_run.c.entity_id == entity_id,
                close_run.c.book_code == book,
                close_run.c.period_id == state.period_id,
            )
            .order_by(close_run.c.created_at, close_run.c.id)
        ).all()
        return {
            "state": str(state.state),
            "close_runs": [(str(run_id), str(status)) for run_id, status in close_runs],
            "journal_runs": [(str(run_id), str(run_state)) for run_id, run_state in runs],
            "batches": [
                (str(batch_id), str(batch_state), str(adapter))
                for batch_id, batch_state, adapter in batches
            ],
            "journal_requests": _requests(db, "JOURNAL_RUN", [run_id for run_id, _ in runs]),
            "lock_requests": _requests(db, "PERIOD_LOCK", [state.id]),
        }


def _late_items() -> list[dict[str, Any]]:
    """The ``LATE_EVENT`` items of the tenant, in number order, each with its waiver requests."""
    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        items = db.execute(
            select(
                exception_item.c.id,
                exception_item.c.source,
                exception_item.c.severity,
                exception_item.c.status,
                exception_item.c.message,
                exception_item.c.resolution,
                exception_item.c.waiver_approval_request_id,
                exception_item.c.period_id,
            )
            .where(exception_item.c.code == perf_seed.LATE_EVENT)
            .order_by(exception_item.c.exception_no)
        ).all()
        return [
            {
                "id": str(item.id),
                "source": str(item.source),
                "severity": str(item.severity),
                "status": str(item.status),
                "message": str(item.message),
                "resolution": item.resolution,
                "waiver_approval_request_id": None
                if item.waiver_approval_request_id is None
                else str(item.waiver_approval_request_id),
                "period_id": item.period_id,
                "requests": _requests(db, "EXCEPTION_WAIVER", [item.id]),
            }
            for item in items
        ]


def _open_items() -> tuple[list[tuple[str, ...]], set[tuple[str, str]]]:
    """Of the tenant's exception items: those that hold a lock — the predicate of the gate
    "Exceptions resolved, waived or dismissed" itself (``gates.blocking_exceptions``), asked for
    every period state, each item as its number, code, source and severity — and the source and
    severity of every item that is still open."""
    from erev_api.domain.close import gates

    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    holding: list[tuple[str, ...]] = []
    with tenant_session(scope, read_only=True) as db:
        state_ids = db.execute(select(period_state.c.id)).scalars().all()
        assert len(state_ids) >= 4 * MONTHS  # four entity-books for every month, at the least
        for state_id in state_ids:
            of_period = gates.period_scope(db, state_id)
            assert of_period is not None
            holding += [
                tuple(str(value) for value in row)
                for row in db.execute(
                    select(
                        exception_item.c.exception_no,
                        exception_item.c.code,
                        exception_item.c.source,
                        exception_item.c.severity,
                    ).where(gates.blocking_exceptions(of_period))
                )
            ]
        still_open = {
            (str(source), str(severity))
            for source, severity in db.execute(
                select(exception_item.c.source, exception_item.c.severity).where(
                    exception_item.c.status.in_(["OPEN", "IN_PROGRESS"])
                )
            )
        }
    return holding, still_open


@contextmanager
def _interrupted_lock_phase(shared: Shared) -> Iterator[None]:
    """The interruption witness of a close (item PERF-SEED-LOCK-1; the supervisor's ruling of
    2026-10-01, point 5, and word of 21:24 on the waiver): while this context stands, the lock
    phase of a run is interrupted twice in the first lock of ``CRASHED_ENTITY``.

    1. After the journal run of the period is exported and before its batch is acknowledged —
       so before its lock is requested.
    2. After the waiver of the generator's late event is asked and before it is decided. There
       the lock is asked once, as the accountant would: the item is still open, and the product
       refuses the lock by its gates (kept on ``shared`` too).

    After each interruption what the database holds is kept on ``shared`` and the lock phase is
    entered again with the ledger a second run would read. It is entered again INSIDE the run:
    a crashed run returns no counters, and a second ``erev perf seed`` in its place would make
    the run that appended months 1 to 5 a crashed one — the returned counters the story
    reconciles across run D's crash would no longer be run C's. What a second run does before
    its lock phase — the seed's steps again behind a lock, the bulk recompute not repeated — is
    therefore not witnessed here but by the completion, which finds months 1 to 5 locked
    (``test_a_run_that_finds_months_locked_recomputes_no_group_without_a_new_event``)."""
    from erev_api.domain.demo import builders
    from erev_api.domain.journals import export as journal_export

    real_lock_phase = perf_seed._close_and_lock  # noqa: SLF001
    real_acknowledge = journal_export.acknowledge_batch
    real_approve = builders.BuildContext.approve
    period_key = _manifest().periods[CRASHED_MONTH - 1]
    # The reference the preparer records for a CSV batch names its entity and period.
    documents = closing.document_reference(CRASHED_ENTITY, period_key, 1, 1).removesuffix("01-01")

    def lock_refusal(ctx: Any) -> tuple[str, list[str]]:
        """Ask the lock of the interrupted period as the preparer; the refusal's slug and the
        codes of the gates that have not passed. A refused command writes nothing."""
        from erev_api.domain.close import commands as close_commands
        from erev_api.enums import BookCode
        from erev_api.problems import Problem
        from erev_api.schemas.periods import PeriodLockRequestIn

        at = closing._period(ctx, CRASHED_ENTITY, BookCode(CRASHED_BOOK), period_key)  # noqa: SLF001
        with (
            pytest.raises(Problem) as refused,
            ctx.command(perf_seed.PERF_ACCOUNTANT.key, closing.CLOSE) as uow,
        ):
            close_commands.request_lock(
                uow,
                state_id=at.state_id,
                body=PeriodLockRequestIn(certification_comment=perf_seed.CERTIFICATION),
                check_version=closing._expect(at.row_version),  # noqa: SLF001
            )
        return refused.value.slug, sorted(str(error.rule_id) for error in refused.value.errors)

    def lock_phase(ctx: Any, manifest: Any, through_month: int, ledger: Any) -> int:
        def crash_before_acknowledgement(uow: Any, batch_id: Any, body: Any) -> Any:
            if str(body.gl_document_id).startswith(documents):
                raise Interrupted("after the journal run was exported, before its lock is asked")
            return real_acknowledge(uow, batch_id, body)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(journal_export, "acknowledge_batch", crash_before_acknowledgement)
            with pytest.raises(Interrupted):
                real_lock_phase(ctx, manifest, through_month, ledger)
        assert journal_export.acknowledge_batch is real_acknowledge
        shared.close_at_crash = _close_facts(CRASHED_ENTITY, CRASHED_BOOK, CRASHED_MONTH)
        # A second run reads the ledger again: the month is not locked for every entity and
        # book, so its close starts again at the first of them.
        again = perf_seed.read_ledger(ctx.tenant_id, manifest)
        assert again.months_locked == frozenset()

        def crash_before_the_waiver_is_decided(
            self: Any, subject_type: Any, subject_id: Any, approvers: Any
        ) -> Any:
            if str(getattr(subject_type, "value", subject_type)) == "EXCEPTION_WAIVER":
                raise Interrupted("after the waiver was asked, before it is decided")
            return real_approve(self, subject_type, subject_id, approvers)

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(builders.BuildContext, "approve", crash_before_the_waiver_is_decided)
            with pytest.raises(Interrupted):
                real_lock_phase(ctx, manifest, through_month, again)
        assert builders.BuildContext.approve is real_approve
        shared.waivers_at_crash = _late_items()
        shared.lock_refused_at_crash = lock_refusal(ctx)
        again = perf_seed.read_ledger(ctx.tenant_id, manifest)
        assert again.months_locked == frozenset()
        return real_lock_phase(ctx, manifest, through_month, again)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(perf_seed, "_close_and_lock", lock_phase)
        yield
    assert perf_seed._close_and_lock is real_lock_phase  # noqa: SLF001


@pytest.fixture(scope="module")
def csv_ledger() -> Iterator[None]:
    """The composition root's part (DG-LAY-03): ``erev perf seed`` registers the CSV
    general-ledger adapter before it seeds, because the jobs of a close run in its process; here
    the fixture does."""
    previous = gl_ports.GL_ADAPTERS.get(GlAdapter.CSV)
    gl_ports.register_gl_adapter(GlAdapter.CSV, CsvGl)
    yield
    if previous is None:
        gl_ports.GL_ADAPTERS.pop(GlAdapter.CSV, None)
    else:
        gl_ports.register_gl_adapter(GlAdapter.CSV, previous)


@pytest.fixture(scope="module")
def shared(
    test_database: TestDatabase,
    keyring: Any,
    tmp_path_factory: pytest.TempPathFactory,
    csv_ledger: None,
) -> Shared:
    story = Shared(keyring=keyring, root=tmp_path_factory.mktemp("prf-2"))
    story.demo_before = _demo_populations()  # BEFORE any perf write (the isolation comparison)
    return story


@pytest.fixture(scope="module")
def interrupted(shared: Shared) -> Shared:
    """RESUME-1 witnesses, first in the story: run A crashes after the first template HEADER
    commits (before its version); run B crashes after the first contract DRAFT, judgement and
    assessments commit (before its activation submit); run C resumes both from their persisted
    lifecycle state through month 5. Run C's lock phase is itself interrupted twice in the first
    lock of VOL-UK and entered again (``_interrupted_lock_phase``)."""
    from erev_api.domain.contracts import activation
    from erev_api.domain.policies import commands as policy_commands

    real_version = policy_commands.create_pob_template_version
    real_submit = activation.submit_activation
    with pytest.MonkeyPatch.context() as patch:

        def crash_before_version(*args: Any, **kwargs: Any) -> Any:
            raise Interrupted("after the template header, before its version")

        patch.setattr(policy_commands, "create_pob_template_version", crash_before_version)
        with pytest.raises(Interrupted):
            shared.run(through_month=5)
    with pytest.MonkeyPatch.context() as patch:

        def crash_before_activation(*args: Any, **kwargs: Any) -> Any:
            raise Interrupted("after the contract draft, before its activation submit")

        patch.setattr(activation, "submit_activation", crash_before_activation)
        with pytest.raises(Interrupted):
            shared.run(through_month=5)
    assert policy_commands.create_pob_template_version is real_version
    assert activation.submit_activation is real_submit
    # Codex 0431 §1 (a) with the 0447 §2 correction: run B1 crashes BEFORE the first distinct
    # review's approval decision — after its create-and-submit COMMITTED (a raise inside the
    # command's unit of work would roll the record back and prove nothing); the SUBMITTED record
    # and its PENDING request are read from the database at the interception. Run B2 crashes
    # right AFTER the first distinct review is approved (REVIEWED). The resume must decide the
    # EXISTING request (B1) and reuse the REVIEWED record (B2) — no second record, no second
    # request. A separately created DRAFT record (below) covers the DRAFT → submit branch.
    from erev_api.domain.demo import builders

    submit_state: dict[str, Any] = {}
    real_approve = builders.BuildContext.approve

    def crash_before_first_distinct_approval(
        self: Any, subject_type: Any, subject_id: Any, approvers: Any
    ) -> Any:
        if (
            str(getattr(subject_type, "value", subject_type)) == "JUDGEMENT_RECORD"
            and not submit_state
            and _is_distinct_review(subject_id)
        ):
            persisted = _distinct_review_identity(str(subject_id))  # committed rows only
            assert persisted["status"] == "SUBMITTED", persisted
            assert (
                len(persisted["request_ids"]) == 1
                and persisted["pending_request_ids"] == (persisted["request_ids"])
            )
            submit_state["judgement_record_id"] = str(subject_id)
            submit_state["approval_request_id"] = persisted["request_ids"][0]
            raise Interrupted("before the first distinct review's approval decision")
        return real_approve(self, subject_type, subject_id, approvers)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(builders.BuildContext, "approve", crash_before_first_distinct_approval)
        with pytest.raises(Interrupted):
            shared.run(through_month=5)
    assert builders.BuildContext.approve is real_approve
    assert submit_state.get("judgement_record_id") and submit_state.get("approval_request_id")
    shared.distinct_after_submit = dict(submit_state)

    review_state: dict[str, Any] = {}

    def crash_after_first_distinct_review(
        self: Any, subject_type: Any, subject_id: Any, approvers: Any
    ) -> Any:
        request_id = real_approve(self, subject_type, subject_id, approvers)
        if str(getattr(subject_type, "value", subject_type)) == "JUDGEMENT_RECORD":
            if not review_state and _is_distinct_review(subject_id):
                review_state["judgement_record_id"] = str(subject_id)
                review_state["approval_request_id"] = str(request_id)
                raise Interrupted("after the first distinct review was approved")
        return request_id

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(builders.BuildContext, "approve", crash_after_first_distinct_review)
        with pytest.raises(Interrupted):
            shared.run(through_month=5)
    assert builders.BuildContext.approve is real_approve
    assert review_state.get("judgement_record_id") and review_state.get("approval_request_id")
    shared.distinct_after_review = dict(review_state)
    # B2's record is B1's: the resume decided B1's PENDING request (same record, same request).
    assert review_state["judgement_record_id"] == submit_state["judgement_record_id"]
    assert review_state["approval_request_id"] == submit_state["approval_request_id"]

    # The DRAFT branch: a POB_DISTINCT_OVERRIDE record created separately as a DRAFT (the generic
    # judgement command, as the accountant, through the seed's own context) for the next distinct
    # obligation still without a record; run C must submit and approve THAT record (same id, one
    # request), never create a second one.
    shared.draft_review = _create_draft_distinct_review(shared)

    with _interrupted_lock_phase(shared):
        resumed = shared.run(through_month=5)
    assert shared.close_at_crash is not None and shared.waivers_at_crash is not None
    assert shared.lock_refused_at_crash is not None
    assert resumed.outcome == "resumed" and resumed.months_locked == 5
    shared.c_appended = resumed.events_appended  # C: the successful earlier run's population
    shared.computed_by_c = _computations()
    # Codex 0246: the resume ledger is read from the DURABLE effects of the ordinary appends (the
    # contract_event rows + the record_events audit detail), so months 1-5 are marked done for
    # every contract that had events in them — no event_submission row exists for them.
    ledger = perf_seed.read_ledger(_perf_tenant_id(), _manifest())
    manifest = _manifest()
    by_seq = {c.seq: c for c in manifest.contracts}
    expected_months: dict[str, set[int]] = {}
    for e in manifest.events():
        if e.recorded_month <= 5 and e.event_type not in {"ESTIMATE_CHANGED", "CONTRACT_AMENDED"}:
            expected_months.setdefault(by_seq[e.contract_seq].external_id, set()).add(
                e.recorded_month
            )
    for external_id, months in expected_months.items():
        assert months <= set(ledger.months_appended.get(external_id, frozenset())), external_id
    early = shared.run(snapshot_only=True)
    assert (early.outcome, early.exit_code) == ("refused", 1)  # step 5 before the lock
    return shared


@pytest.fixture(scope="module")
def after_event_approval(interrupted: Shared) -> Shared:
    """Codex 0206 §5 witness: run D crashes right AFTER the first ESTIMATE_CHANGED of the manifest
    is approved (the version APPROVED, the event appended), before its month's batch; the
    completion then finds that version complete and must report it REUSED, not appended."""
    real = volume._apply_estimate  # noqa: SLF001
    state: dict[str, Any] = {"approved": 0, "event": None}
    interrupted.ids_before_d = _event_ids()

    def crash_after_first_approval(*args: Any, **kwargs: Any) -> str:
        outcome = real(*args, **kwargs)
        if outcome == volume.APPLIED:
            state["approved"] += 1
            if state["approved"] == 1:
                state["event"] = args[4]  # (ctx, cast, contract_id, spec, event)
                raise Interrupted("after the first estimate version was approved")
        return outcome

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(volume, "_apply_estimate", crash_after_first_approval)
        with pytest.raises(Interrupted):
            interrupted.run()
    assert volume._apply_estimate is real  # noqa: SLF001
    assert state["approved"] == 1 and state["event"] is not None
    # The crashed run returned nothing (its counters are lost with the exception); its DURABLE
    # effects are what the resume must find: snapshot the persisted event ids and the ACTUAL
    # interrupted event's identity (its version and applied events) now, at the crash (Codex 0236).
    interrupted.crashed_event = state["event"]
    interrupted.crashed_identity = _estimate_identity(state["event"])
    assert interrupted.crashed_identity["status"] in volume.DONE_CONFIG
    assert interrupted.crashed_identity["applied_event_ids"], "the approval appended its event"
    interrupted.ids_after_crash = _event_ids()
    assert set(interrupted.crashed_identity["applied_event_ids"]) <= interrupted.ids_after_crash
    return interrupted


@pytest.fixture(scope="module")
def completed(after_event_approval: Shared) -> Shared:
    """Steps 1-3 to the last locked month: the completion, resumed after the interrupted story
    and the post-approval crash. What the tenant holds then is kept on the story, before a
    later test records anything in it."""
    interrupted = after_event_approval
    interrupted.computed_before_completion = _computations()
    seed = interrupted.run()
    interrupted.completion = seed
    interrupted.computed_by_completion = _computations()
    interrupted.items_after_seed = _open_items()
    interrupted.late_after_seed = _late_items()
    assert seed.events_reused >= 1  # the approved-then-crashed estimate version, found complete
    assert seed.outcome == "resumed" and seed.exit_code == 0 and seed.snapshot_id is None
    assert seed.months_locked == LOCKED == perf_seed.seed_months(_manifest())
    return interrupted


@pytest.fixture(scope="module")
def seeded(completed: Shared) -> perf_seed.PerfSeedResult:
    """Step 5 (``--snapshot-only``) on the completed seed, as make perf-seed runs it after the
    step-4 ANALYZE. A fixture of its own (item PERF-SEED-LOCK-1): a test that reads nothing of
    the snapshot stands on ``completed``, so a refusal of step 5 is the red of the tests that
    read it — the up-to-date run, and the demo tenants "after the whole story" — and of no
    other.

    The story lives on two clocks (``support.snapshots.cutoff_after``): its frozen clock stamps
    what the product writes from ``uow.now``, and the database's — real time, later — stamps
    the record time of every event (DB-08). A snapshot keeps what was recorded at or before its
    ``known_at``, which step 5 takes from the application clock, as the command takes it from
    the system clock after the locks. On the frozen clock that cutoff lies before every event
    of the world: the snapshot held ten contracts and no event, and a sandbox restored from it
    computed nothing. So the story's clock moves to the database's first, as the product's
    sandbox modules do — one phase step short of it, because every phase of the story begins
    by advancing the clock a step (``Shared.services``): step 5 then takes ``known_at`` at the
    database's instant, not a step into its future."""
    database_now = cutoff_after(_perf_tenant_id(), completed.clock)
    completed.clock.set(database_now - FRESH_STEP)
    seed = completed.run(snapshot_only=True)
    assert completed.clock.now() == database_now  # the cutoff of step 5
    return seed


def test_distinct_reviews_resume_by_persisted_state(interrupted: Shared) -> None:
    """Codex 0431 §1 (a): the distinct review interrupted right after its submit (B1) and the one
    interrupted right after its approval (B2) keep their judgement and request identities across
    the resume — one POB_DISTINCT_OVERRIDE record per obligation, one review request per record,
    both REVIEWED; the resume decided the EXISTING request (B1) and reused the REVIEWED record
    (B2); no second record, no second request. The activation checklist refused before the
    reviews existed (the 5929592d measurement) and the real activation succeeds after them."""
    assert interrupted.distinct_after_submit and interrupted.distinct_after_review
    assert interrupted.draft_review
    after_submit = _distinct_review_identity(
        interrupted.distinct_after_submit["judgement_record_id"]
    )
    assert after_submit["status"] == "REVIEWED" and after_submit["records_for_obligation"] == 1
    assert after_submit["request_ids"] == [interrupted.distinct_after_submit["approval_request_id"]]
    after_review = _distinct_review_identity(
        interrupted.distinct_after_review["judgement_record_id"]
    )
    assert after_review["status"] == "REVIEWED" and after_review["records_for_obligation"] == 1
    assert after_review["request_ids"] == [interrupted.distinct_after_review["approval_request_id"]]
    # The DRAFT branch: the separately created DRAFT record was submitted and approved as ITSELF.
    draft = _distinct_review_identity(interrupted.draft_review["judgement_record_id"])
    assert draft["status"] == "REVIEWED" and draft["records_for_obligation"] == 1
    assert len(draft["request_ids"]) == 1
    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        duplicates = db.execute(
            select(judgement_record.c.subject_id, func.count())
            .where(
                judgement_record.c.subject_type == "obligation",
                judgement_record.c.topic == "POB_DISTINCT_OVERRIDE",
            )
            .group_by(judgement_record.c.subject_id)
            .having(func.count() > 1)
        ).all()
        assert duplicates == []
        statuses = {
            str(value)
            for value in db.execute(
                select(judgement_record.c.status).where(
                    judgement_record.c.topic == "POB_DISTINCT_OVERRIDE"
                )
            ).scalars()
        }
        assert statuses <= {"REVIEWED"}


def test_interrupted_header_and_draft_resume_without_duplicates(interrupted: Shared) -> None:
    """RESUME-1: after the two crashes and the resume, every template has exactly one header and
    one PUBLISHED version; every contract external id has exactly one row, ACTIVE, with one
    reviewed COLLECTIBILITY judgement and one COLLECTIBILITY_ASSESSED event per enabled book."""
    manifest = _manifest()
    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        headers = db.execute(
            select(pob_template.c.code, func.count()).group_by(pob_template.c.code)
        ).all()
        assert sorted(code for code, _ in headers) == sorted(t.code for t in manifest.templates)
        assert all(count == 1 for _, count in headers)
        versions = db.execute(
            select(pob_template_version.c.pob_template_id, pob_template_version.c.status)
        ).all()
        assert len(versions) == len(manifest.templates)
        assert {str(status) for _, status in versions} <= {"PUBLISHED", "APPROVED"}
        rows = db.execute(
            select(contract.c.external_id, contract.c.id, contract.c.status, func.count()).group_by(
                contract.c.external_id, contract.c.id, contract.c.status
            )
        ).all()
        assert sorted(row.external_id for row in rows) == sorted(
            c.external_id for c in manifest.contracts
        )
        assert all(row.count == 1 and str(row.status) == "ACTIVE" for row in rows)
        for row in rows:
            judgements = (
                db.execute(
                    select(judgement_record.c.status).where(
                        judgement_record.c.subject_type == "contract",
                        judgement_record.c.subject_id == row.id,
                    )
                )
                .scalars()
                .all()
            )
            assert [str(s) for s in judgements] == ["REVIEWED"]
            books = int(
                db.execute(
                    select(func.count())
                    .select_from(contract_event)
                    .where(
                        contract_event.c.contract_id == row.id,
                        contract_event.c.event_type == "COLLECTIBILITY_ASSESSED",
                    )
                ).scalar_one()
            )
            assert books >= 1  # one per enabled book, appended once (all or nothing)
        # The event paths hold the same property: one estimate version per (element, marker) and
        # one modification row per reference, after the crashes and the resume.
        duplicate_versions = db.execute(
            select(estimate_version.c.estimate_id, estimate_version.c.rationale, func.count())
            .group_by(estimate_version.c.estimate_id, estimate_version.c.rationale)
            .having(func.count() > 1)
        ).all()
        assert duplicate_versions == []
        duplicate_modifications = db.execute(
            select(modification.c.contract_id, modification.c.reference, func.count())
            .group_by(modification.c.contract_id, modification.c.reference)
            .having(func.count() > 1)
        ).all()
        assert duplicate_modifications == []


def test_up_to_date_exit_0(seeded: perf_seed.PerfSeedResult, interrupted: Shared) -> None:
    """A small-scale tenant with the current hash, its last seeded month locked (month 23 of the
    dataset; month 6 of this story's seven) and a succeeded stored snapshot makes both phases
    print "perf-volume up to date" and exit 0 without writes. Step 5 stored a backup and loaded
    nothing (DG-MK-perf-seed (5); 05 PERF-15 rev 1.182): the row is a ``STORED_BACKUP``,
    ``SUCCEEDED``, with no target tenant, asked by perf-controller; the job her request deferred
    ran in place and succeeded, and no snapshot job of the tenant is left waiting for a worker.
    The third database run of this story stopped here: the seed asked a ``SANDBOX_SEED`` without
    the sandbox name the product asks of that purpose (04 API-R-04 rev 1.67)."""
    assert seeded.outcome == "snapshot" and seeded.exit_code == 0 and seeded.snapshot_id
    assert seeded.message == "taking the stored snapshot of perf-volume"
    snapshot, waiting = _snapshot_facts(seeded.snapshot_id)
    assert snapshot == {
        "purpose": "STORED_BACKUP",
        "status": "SUCCEEDED",
        "target_tenant_id": None,
        "requested_by": "perf-controller",
        "job_state": "SUCCEEDED",
    }
    assert waiting == []
    with platform_session("tenant_directory", actor_user_id=None, request_id="prf2-read") as db:
        row = db.execute(
            select(tenant.c.id, tenant.c.industry_cluster).where(
                tenant.c.code == perf_seed.TENANT_CODE
            )
        ).one()
    assert row.industry_cluster == _manifest().industry_cluster
    scope = DbContext(tenant_id=row.id, user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        before = int(db.execute(select(func.count()).select_from(contract)).scalar_one())
        events_before = int(
            db.execute(select(func.count()).select_from(contract_event)).scalar_one()
        )
        snapshots_before = int(
            db.execute(select(func.count()).select_from(tenant_snapshot)).scalar_one()
        )
    for mode in (False, True):
        again = interrupted.run(snapshot_only=mode)
        assert (again.outcome, again.exit_code, again.message) == (
            "up_to_date",
            0,
            "perf-volume up to date",
        )
    with tenant_session(scope, read_only=True) as db:
        assert int(db.execute(select(func.count()).select_from(contract)).scalar_one()) == before
        assert (
            int(db.execute(select(func.count()).select_from(contract_event)).scalar_one())
            == events_before
        )
        assert (
            int(db.execute(select(func.count()).select_from(tenant_snapshot)).scalar_one())
            == snapshots_before
        )


def test_events_persisted_once_and_counted_across_the_crash_boundary(
    completed: Shared, interrupted: Shared
) -> None:
    """Codex 0233 POSTCOMMIT-WITNESS-1 with the 0236 §2 precision — DURABLE identity and the
    RETURNED counters reconciled separately across the crash boundary. Durable: the ACTUAL
    interrupted event's version (captured at the crash: id, applied_event_ids) exists exactly once
    after the retry with the same identity — no second version, no second event; every event id
    persisted before the crash is still there afterwards; the completion added exactly as many
    rows as it reported appended; per manifest event type the persisted count equals the
    manifest's locked months (1-23 of the dataset; 1-6 here). Returned (Codex 0255 §3 arithmetic):
    with C = the successful earlier
    run's population (months 1-5, returned) and U = the events run D committed before crashing,
    the runs that RETURNED report appended == N − U (not N: the crashed run's appends returned
    nothing); the completion reports reused == C + U (months 1-5 from C and run D's months are
    both found again by the repaired ledger, plus the approved estimate — none re-appended); and
    accumulated appended + reused == N + C, not N (the C events are counted once as appended by
    run C and once as reused by the completion)."""
    manifest = _manifest()
    events = [e for e in manifest.events() if e.recorded_month <= LOCKED]
    expected_by_type: dict[str, int] = {}
    for e in events:
        expected_by_type[e.event_type] = expected_by_type.get(e.event_type, 0) + 1
    assert interrupted.ids_before_d is not None and interrupted.ids_after_crash is not None
    assert interrupted.completion is not None and interrupted.crashed_event is not None
    assert interrupted.crashed_identity is not None
    committed_by_d = interrupted.ids_after_crash - interrupted.ids_before_d
    u = len(committed_by_d)
    assert u >= 1  # the approved estimate's event at least
    # Durable identity of the interrupted event, bound across the retry.
    after_retry = _estimate_identity(interrupted.crashed_event)
    assert after_retry["version_id"] == interrupted.crashed_identity["version_id"]
    assert after_retry["applied_event_ids"] == interrupted.crashed_identity["applied_event_ids"]
    final_ids = _event_ids()
    assert set(after_retry["applied_event_ids"]) <= final_ids
    assert interrupted.ids_after_crash <= final_ids  # nothing lost, nothing re-appended
    assert len(final_ids) - len(interrupted.ids_after_crash) == (
        interrupted.completion.events_appended
    )
    persisted = _persisted_by_type()
    for kind, count in expected_by_type.items():
        assert persisted.get(kind, 0) == count, kind  # exactly once, across every run
    # Codex 0246: after the completion the ledger marks every contract-month with ordinary events
    # done from the durable effects, and a further seed phase is a no-op ("up to date" is asserted
    # by test_up_to_date_exit_0; here the ledger itself).
    ledger = perf_seed.read_ledger(_perf_tenant_id(), manifest)
    by_seq = {c.seq: c for c in manifest.contracts}
    for e in events:
        if e.event_type in {"ESTIMATE_CHANGED", "CONTRACT_AMENDED"}:
            continue
        external_id = by_seq[e.contract_seq].external_id
        assert e.recorded_month in ledger.months_appended.get(external_id, frozenset()), (
            external_id,
            e.recorded_month,
        )
    # Returned counters, reconciled against C and U (0236 §2 (a); 0255 §3 arithmetic).
    n = len(events)
    assert interrupted.c_appended is not None
    c = interrupted.c_appended
    assert c == sum(1 for e in events if e.recorded_month <= 5)  # run C appended months 1-5 once
    assert interrupted.events_appended == n - u
    assert interrupted.completion.events_reused == c + u
    assert interrupted.events_appended + interrupted.events_reused == n + c


def test_event_paths_report_reuse_after_approval(
    completed: Shared,
    interrupted: Shared,
    record_property: Callable[[str, object], None],
) -> None:
    """Codex 0206 §5, the per-event boundary driven directly through the seed's own paths and
    context: a complete estimate version is REUSED (one row per (element, rationale) stays one);
    a modification applied by a first call is REUSED (or SEPARATE, never APPLIED) by a second call
    with exactly one row per (contract, reference). The 1/1000 manifest draws no CONTRACT_AMENDED,
    so the modification boundary is witnessed with a synthetic event of the manifest's last month
    — the one a seed holds back, open and not locked — on a seeded contract, through the same real
    CTR-17 commands."""
    from erev_api.db.tables import estimate as estimate_table

    manifest = _manifest()
    ctx, services = interrupted.context()
    scope = DbContext(tenant_id=ctx.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        contract_ids = {
            str(external_id): row_id
            for external_id, row_id in db.execute(select(contract.c.external_id, contract.c.id))
        }
    by_seq = {c.seq: c for c in manifest.contracts}
    # The INTERRUPTED event itself (0236 §2 (c)), not the manifest's first estimate.
    assert interrupted.crashed_event is not None and interrupted.crashed_identity is not None
    event = interrupted.crashed_event
    spec = by_seq[event.contract_seq]
    before_call = _estimate_identity(event)
    assert before_call == interrupted.crashed_identity
    with tenant_session(scope, read_only=True) as db:
        versions_before = int(
            db.execute(select(func.count()).select_from(estimate_version)).scalar_one()
        )
    outcome = volume._apply_estimate(  # noqa: SLF001
        ctx, volume.PERF_CAST, contract_ids[spec.external_id], spec, event
    )
    assert outcome == volume.REUSED
    assert _estimate_identity(event) == before_call  # same version, same applied events
    with tenant_session(scope, read_only=True) as db:
        assert int(db.execute(select(func.count()).select_from(estimate_version)).scalar_one()) == (
            versions_before
        )
        assert (
            db.execute(
                select(func.count())
                .select_from(
                    estimate_version.join(
                        estimate_table, estimate_table.c.id == estimate_version.c.estimate_id
                    )
                )
                .where(estimate_version.c.rationale == volume.estimate_rationale(event))
            ).scalar_one()
        ) == 1
    spec = manifest.contracts[0]
    synthetic = volume.VolumeEvent(
        seq=900_001,
        contract_seq=spec.seq,
        obligation_key=None,
        event_type="CONTRACT_AMENDED",
        effective_month=MONTHS,
        # The manifest's last month: open, not locked.
        effective_date=volume.month_start(MONTHS).replace(day=15),
        recorded_month=MONTHS,
        late=False,
        detail=(("treatment", "PROSPECTIVE"),),
    )
    first = volume._apply_modification(  # noqa: SLF001
        ctx,
        volume.PERF_CAST,
        manifest,
        contract_ids[spec.external_id],
        spec,
        synthetic,
        services.runtime,
    )
    assert first in {volume.APPLIED, volume.SEPARATE}
    reference = volume.modification_body(manifest, spec, synthetic)["reference"]

    def modification_rows() -> list[dict[str, Any]]:
        with tenant_session(scope, read_only=True) as db:
            return [
                {
                    "id": str(row["id"]),
                    "status": str(row["status"]),
                    "applied_event_id": None
                    if row["applied_event_id"] is None
                    else str(row["applied_event_id"]),
                    "treatment_summary": None
                    if row["treatment_summary"] is None
                    else str(row["treatment_summary"]),
                }
                for row in db.execute(
                    select(
                        modification.c.id,
                        modification.c.status,
                        modification.c.applied_event_id,
                        modification.c.treatment_summary,
                    ).where(
                        modification.c.contract_id == contract_ids[spec.external_id],
                        modification.c.reference == reference,
                    )
                ).mappings()
            ]

    (after_first,) = modification_rows()  # exactly one row, identity captured after call one
    assert after_first["status"] == "APPLIED"
    # 0236 §2 (d): say which branch the engine took — recorded in the junit properties of the
    # slot-2 run (DG-LOG-06: no print); the other branch did NOT run here.
    branch = "SEPARATE_CONTRACT" if first == volume.SEPARATE else "AMENDED"
    record_property("synthetic_modification_branch", branch)
    record_property("synthetic_modification_row", after_first["id"])
    if first == volume.SEPARATE:
        assert after_first["treatment_summary"] == "SEPARATE_CONTRACT"
    else:
        assert after_first["applied_event_id"] is not None  # CONTRACT_AMENDED appended
        assert after_first["applied_event_id"] in _event_ids()
    second = volume._apply_modification(  # noqa: SLF001
        ctx,
        volume.PERF_CAST,
        manifest,
        contract_ids[spec.external_id],
        spec,
        synthetic,
        services.runtime,
    )
    assert second == (volume.SEPARATE if first == volume.SEPARATE else volume.REUSED)
    (after_second,) = modification_rows()  # still exactly one row …
    assert after_second == after_first  # … with the same id and the same applied_event_id
    interrupted.persona_run.sign_out_all()


def test_effective_grants_of_the_cast(completed: Shared, interrupted: Shared) -> None:
    """PERSONA-1: the EFFECTIVE grants (role assignments in force) of every persona hold the
    permissions the seed used as that persona; the admin holds only the Tenant Admin role; the
    accountant holds no approval permission (preparer / approver separation)."""
    from erev_api.approvals.subjects import SUBJECTS

    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    approvals = {spec.required_permission for spec in SUBJECTS.values()}
    with tenant_session(scope, read_only=True) as db:
        for persona in perf_seed.CAST:
            membership_id = db.execute(
                select(tenant_membership.c.id)
                .select_from(
                    tenant_membership.join(app_user, app_user.c.id == tenant_membership.c.user_id)
                )
                .where(tenant_membership.c.status == "ACTIVE", app_user.c.email == persona.email)
            ).scalar_one()
            grants = effective_grants(db, membership_id, at=interrupted.clock.now())
            assert perf_seed.REQUIRED_PERMISSIONS[persona.key] <= grants.permissions, persona.key
            assert set(grants.roles) == set(persona.roles_in(perf_seed.GROUP)), persona.key
            if persona is perf_seed.PERF_ADMIN:
                assert set(grants.roles) == {"tenant_admin"}
            if persona is perf_seed.PERF_ACCOUNTANT:
                assert not (grants.permissions & approvals)


def test_other_generator_version_exit_2(
    completed: Shared, interrupted: Shared, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another industry_cluster makes it exit 2 with the db-reset message."""
    monkeypatch.setattr(volume, "FX_BASE", {"GBP": "1.300000", "EUR": "1.100000"})  # another hash
    other = interrupted.run()
    assert other.exit_code == 2
    assert other.message == "perf tenant built from another generator version; run make db-reset"


def test_never_touches_demo_tenants(seeded: perf_seed.PerfSeedResult, interrupted: Shared) -> None:
    """DG-PERF-06: the demo tenants' populations (contracts, events, snapshots) are the same before
    the first perf write and after the whole story, and the perf tenant is not a demo catalogue
    member (make seed skips it)."""
    from erev_api.domain.demo import tenants

    assert perf_seed.TENANT_CODE not in {t.code for t in tenants.catalogue()}
    assert _demo_populations() == interrupted.demo_before


# --- PERF-SEED-LOCK-1: the months are closed as their people close them ---------------------------


def test_a_close_interrupted_after_its_export_resumes_without_a_second_journal_run(
    interrupted: Shared,
) -> None:
    """The supervisor's ruling of 2026-10-01, point 5: a seed interrupted after a month's journal
    run is exported and before its lock is requested, in one entity-book — VOL-UK ASC606, month
    1, in run C (``_interrupted_lock_phase``). At the interruption the period stands in soft
    close with its one close run succeeded, its one journal run approved by the reviewer and
    exported as CSV batches, and no lock asked. The resumed lock phase makes no second close run,
    no second journal run and no second batch for that period: it records the ledger's reference
    on the batches it finds, asks the lock and has it decided."""
    at_crash = interrupted.close_at_crash
    assert at_crash is not None
    assert at_crash["state"] == "closing"
    assert [status for _, status in at_crash["close_runs"]] == ["SUCCEEDED"]
    assert [state for _, state in at_crash["journal_runs"]] == ["exported"]
    assert at_crash["batches"], "the month posts, so its journal run holds a batch"
    assert {(state, adapter) for _, state, adapter in at_crash["batches"]} == {("exported", "CSV")}
    assert at_crash["lock_requests"] == []
    (journal_request,) = at_crash["journal_requests"]
    assert journal_request["status"] == "APPROVED"
    assert journal_request["preparer"] == "perf-accountant"
    assert journal_request["decisions"] == [("perf-reviewer", "APPROVE")]
    assert journal_request["comment"] == closing.JOURNAL_COMMENT
    after = _close_facts(CRASHED_ENTITY, CRASHED_BOOK, CRASHED_MONTH)
    assert after["state"] == "closed"
    assert after["close_runs"] == at_crash["close_runs"]  # the run of the interrupted seed
    assert [run_id for run_id, _ in after["journal_runs"]] == [
        run_id for run_id, _ in at_crash["journal_runs"]
    ]
    assert [state for _, state in after["journal_runs"]] == ["acknowledged"]
    assert [batch_id for batch_id, _, _ in after["batches"]] == [
        batch_id for batch_id, _, _ in at_crash["batches"]
    ]
    assert {state for _, state, _ in after["batches"]} == {"acknowledged"}
    assert after["journal_requests"] == at_crash["journal_requests"]  # asked once, decided once
    (lock,) = after["lock_requests"]
    assert (lock["status"], lock["preparer"], lock["decisions"], lock["comment"]) == (
        "APPROVED",
        "perf-accountant",
        [("perf-controller", "APPROVE")],
        perf_seed.CERTIFICATION,
    )


def test_every_locked_month_was_closed_by_a_preparer_a_reviewer_and_a_controller(
    completed: Shared, interrupted: Shared
) -> None:
    """05 PERF-15 (rev 1.182): months 1 to 6 are ``closed`` for every entity and book and month
    7 is open; each close holds one succeeded close run, one lock request of perf-accountant
    decided by perf-controller, and one journal run (PRD WLD-R-02: nobody decides what she
    prepared). Where the month posts, the run is perf-accountant's, approved by perf-reviewer,
    exported as CSV batches and acknowledged. Where it posts nothing — VOL-DE's six months: its
    one contract begins in month 7 — the run holds no line and stands as the close run
    calculated it, ``draft`` and without a request (``closing.stands_as_calculated``): the lock
    asks a run of the period that is not cancelled, and item JRN-EMPTY-RUN-1 refuses the
    submission of a run without lines. No reconciliation is made: none is asked."""
    from erev_api.db.tables import reconciliation

    manifest = _manifest()
    books = [(entity.code, book) for entity in manifest.entities for book in entity.books]
    assert len(books) == 4
    posting = 0
    quiet: list[tuple[str, str, int]] = []
    for month in range(1, LOCKED + 1):
        for entity_code, book in books:
            facts = _close_facts(entity_code, book, month)
            where = (entity_code, book, month)
            assert facts["state"] == "closed", where
            assert [status for _, status in facts["close_runs"]] == ["SUCCEEDED"], where
            (lock,) = facts["lock_requests"]
            assert (lock["status"], lock["preparer"], lock["decisions"]) == (
                "APPROVED",
                "perf-accountant",
                [("perf-controller", "APPROVE")],
            ), where
            ((_, run_state),) = facts["journal_runs"]
            if facts["batches"]:
                posting += 1
                assert run_state == "acknowledged", where
                assert {(state, adapter) for _, state, adapter in facts["batches"]} == {
                    ("acknowledged", "CSV")
                }, where
                (request,) = facts["journal_requests"]
                assert (request["status"], request["preparer"], request["decisions"]) == (
                    "APPROVED",
                    "perf-accountant",
                    [("perf-reviewer", "APPROVE")],
                ), where
            else:
                quiet.append(where)
                assert run_state == "draft", where
                assert facts["journal_requests"] == [], where
    assert posting == 3 * LOCKED  # VOL-US and both books of VOL-UK post in every month
    assert quiet == [("VOL-DE", "ASC606", month) for month in range(1, LOCKED + 1)]
    for entity_code, book in books:
        assert _close_facts(entity_code, book, MONTHS)["state"] == "open", (entity_code, book)
    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        assert db.execute(select(func.count()).select_from(reconciliation)).scalar_one() == 0


def test_no_reconciliation_is_asked_by_a_close_version_the_reviewer_approved(
    completed: Shared, interrupted: Shared
) -> None:
    """05 PERF-15 (rev 1.182): ``close.require_reconciliations_for_lock`` is false in the volume
    tenant by ONE ``CLOSE`` registry version of scope TENANT — authored and submitted by
    perf-accountant, approved by perf-reviewer, published without a date (a settings version is
    in force when it is approved) — however often the seed was interrupted and resumed. It
    stands beside the workspace's first version of the category, which holds nothing and which
    it superseded."""
    from erev_api.domain.close import gates
    from erev_api.registry.resolve import setting

    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        versions = db.execute(
            select(
                registry_version.c.id,
                registry_version.c.status,
                registry_version.c["values"],
                registry_version.c.effective_from,
            )
            .where(registry_version.c.category == "CLOSE", registry_version.c.scope == "TENANT")
            .order_by(registry_version.c.version_no)
        ).all()
        (_, first_status, first_values, _), (version_id, status, values, effective_from) = versions
        assert (str(first_status), first_values) == ("SUPERSEDED", {})
        assert str(status) == "PUBLISHED" and effective_from is None
        assert values == {gates.REQUIRE_RECONCILIATIONS: False}
        (request,) = _requests(db, "REGISTRY_VERSION", [version_id])
        assert (request["status"], request["preparer"], request["decisions"]) == (
            "APPROVED",
            "perf-accountant",
            [("perf-reviewer", "APPROVE")],
        )
        assert request["comment"] == perf_seed.PARAMETER_COMMENT
        now = interrupted.clock.now()
        assert setting(db, gates.REQUIRE_RECONCILIATIONS, known_at=now) is False


def test_the_generator_s_late_events_are_the_items_raised_and_each_is_waived(
    completed: Shared, interrupted: Shared
) -> None:
    """05 PERF-14 and PERF-15 (rev 1.182): sent by effective date, the events of the locked
    months raise exactly the ``LATE_EVENT`` items of the events the generator records a month
    late — ``volume.late_arrivals`` counts them on the manifest: one in these six months, where
    the order before raised one for three fifths of all events. Its input is committed, so it is
    not dismissed (PRD BR-DAT-04): perf-accountant asked its waiver with a comment that names the
    generator and perf-reviewer decided it. The seed was interrupted between the two
    (``_interrupted_lock_phase``): the request it left pending is the one decided — it is not
    asked twice. No open exception item holds a lock of the tenant; what stays open holds none
    (04 Table 15.4-E): the warnings of the data-quality monitors — revenue recognised without
    billing — and the engine's information items."""
    manifest = _manifest()
    by_seq = {c.seq: c for c in manifest.contracts}
    (event,) = volume.late_arrivals(manifest, LOCKED)
    assert event.late and by_seq[event.contract_seq].entity_code == CRASHED_ENTITY
    # At the interruption: the item open, its waiver asked by the accountant and not decided.
    assert interrupted.waivers_at_crash is not None
    (open_item,) = interrupted.waivers_at_crash
    (pending,) = open_item["requests"]
    assert open_item["status"] == "OPEN" and open_item["waiver_approval_request_id"] is None
    assert (pending["status"], pending["preparer"], pending["decisions"]) == (
        "PENDING",
        "perf-accountant",
        [],
    )
    # While the waiver waited the item held the lock: asked then, the lock was refused by the
    # gate of the exceptions — and by that of the approvals, the waiver being one.
    from erev_api.domain.close import gates

    assert interrupted.lock_refused_at_crash is not None
    slug, failing = interrupted.lock_refused_at_crash
    assert slug == "close-gates-failed" and gates.EXCEPTIONS_CLEARED in failing
    assert set(failing) <= {gates.EXCEPTIONS_CLEARED, gates.APPROVALS_CLEARED}
    # As the completed seed left the tenant, before a later test of this story records anything
    # in it: the same item, waived by the decision of that request.
    assert interrupted.late_after_seed is not None and interrupted.items_after_seed is not None
    (item,) = interrupted.late_after_seed
    assert item["id"] == open_item["id"]
    assert (item["source"], item["severity"]) == ("ENGINE", "WARNING")
    assert item["period_id"] is None  # it holds every lock of its entity
    assert item["message"] == (
        f"Effective {event.effective_date.isoformat()} is earlier than a committed later event "
        f"of {by_seq[event.contract_seq].external_id}."
    )
    assert item["status"] == "WAIVED" and item["resolution"] == perf_seed.WAIVER_COMMENT
    (request,) = item["requests"]
    assert request["id"] == pending["id"] == item["waiver_approval_request_id"]
    assert (request["status"], request["preparer"], request["decisions"]) == (
        "APPROVED",
        "perf-accountant",
        [("perf-reviewer", "APPROVE")],
    )
    assert request["comment"] == pending["comment"] == perf_seed.WAIVER_COMMENT
    holding, still_open = interrupted.items_after_seed
    assert holding == []
    assert still_open <= {("DATA_QUALITY", "WARNING"), ("ENGINE", "INFO")}, still_open


def test_a_run_that_finds_months_locked_recomputes_no_group_without_a_new_event(
    completed: Shared, interrupted: Shared
) -> None:
    """05 PERF-15 (rev 1.182): the bulk recompute of every group is made with every period open
    and is not repeated behind a lock. Run C found every period open: when its appends were done
    it recomputed every group, so the latest computation of every contract that recorded an
    event in months 1 to 5 includes no new event. The completion found months 1 to 5 locked: it
    made no computation without a new event — each one it made is an append's or a command's —
    and the latest computation of every contract that recorded an event in month 6 includes its
    events. The second database run of this story met the other order: the completion recomputed
    all ten groups, the recomputation of a contract with a capitalised cost posted that cost's
    lines of May into June without a source event, and the close run of June stopped at its
    dataset freeze (ENGINE_SPEC_B S15-R-18b). What the engine posts there is its own defect
    (item ENG-COST-READBACK-1, witnessed in the engine's lane); the seed's order is PERF-15's
    condition and no answer to it."""
    manifest = _manifest()
    by_seq = {c.seq: c for c in manifest.contracts}

    def recorded(months: range) -> set[str]:
        return {
            by_seq[e.contract_seq].external_id
            for e in manifest.events()
            if e.recorded_month in months
        }

    by_c = interrupted.computed_by_c
    before, after = interrupted.computed_before_completion, interrupted.computed_by_completion
    assert by_c is not None and before is not None and after is not None
    assert {name for name, _ in by_c} == {c.external_id for c in manifest.contracts}
    early, sixth = recorded(range(1, 6)), recorded(range(6, 7))
    assert len(early) >= 8 and len(sixth) >= 8  # most of the ten contracts, in either part
    # A contract's last entry is its latest computation: ``dict`` keeps the last of each name.
    assert {name: new for name, new in dict(by_c).items() if name in early} == dict.fromkeys(
        early, 0
    )
    assert after[: len(before)] == before  # computations are only added, and in order
    added = after[len(before) :]
    assert added and [entry for entry in added if entry[1] == 0] == []
    assert all(dict(after)[name] > 0 for name in sixth), dict(after)


def test_an_activation_of_a_million_takes_its_second_step_from_the_controller(
    interrupted: Shared,
) -> None:
    """PRD §2.5: an activation of USD 1,000,000.00 and more routes a second step, held by a
    Controller. One contract of the story's manifest is booked at that (the unit module pins
    which): perf-reviewer decided one step of its activation and perf-controller the other, and
    every other activation is the reviewer's alone. The first run of this story stopped here —
    the seed named one approver for an activation, and the 24 months' manifest holds no such
    contract at this scale."""
    manifest = _manifest()
    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        ids = {
            str(external_id): row_id
            for external_id, row_id in db.execute(select(contract.c.external_id, contract.c.id))
        }
        decided: dict[str, list[tuple[str | None, str]]] = {}
        for spec in manifest.contracts:
            (request,) = _requests(db, "CONTRACT_ACTIVATION", [ids[spec.external_id]])
            assert (request["status"], request["preparer"]) == ("APPROVED", "perf-accountant")
            decided[spec.external_id] = sorted(request["decisions"])
    twice = [("perf-controller", "APPROVE"), ("perf-reviewer", "APPROVE")]
    assert {name for name, decisions in decided.items() if decisions == twice} == {"VOL-C-000003"}
    assert all(
        decisions == [("perf-reviewer", "APPROVE")]
        for name, decisions in decided.items()
        if name != "VOL-C-000003"
    )


def test_the_retention_families_are_confirmed_by_a_platform_version_the_reviewer_approved(
    completed: Shared, interrupted: Shared
) -> None:
    """05 PERF-15 (rev 1.182), DG-MK-perf-seed: the export of a snapshot asks a confirmed
    retention policy — a PUBLISHED version of scope TENANT that states the five families of
    ``platform.snapshot_retention_families``, with a named human approval, in force at the
    snapshot's ``known_at`` (PRD ERR-77). The seed states the families of the product's own
    catalogue by ONE ``PLATFORM`` version — perf-accountant's, approved by perf-reviewer —
    beside the workspace's empty first version, which it superseded, however often the seed was
    interrupted and resumed; the product's own reading finds the policy confirmed."""
    from erev_api.domain.platform import snapshot_dataset, snapshot_job

    scope = DbContext(tenant_id=_perf_tenant_id(), user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        versions = db.execute(
            select(
                registry_version.c.id,
                registry_version.c.status,
                registry_version.c["values"],
                registry_version.c.effective_from,
            )
            .where(registry_version.c.category == "PLATFORM", registry_version.c.scope == "TENANT")
            .order_by(registry_version.c.version_no)
        ).all()
        (_, first_status, first_values, _), (version_id, status, values, effective_from) = versions
        assert (str(first_status), first_values) == ("SUPERSEDED", {})
        assert str(status) == "PUBLISHED" and effective_from is None
        assert values == {
            snapshot_dataset.RETENTION_PARAMETER: dict(snapshot_dataset.RETENTION_FAMILIES)
        }
        (request,) = _requests(db, "REGISTRY_VERSION", [version_id])
        assert (request["status"], request["preparer"], request["decisions"]) == (
            "APPROVED",
            "perf-accountant",
            [("perf-reviewer", "APPROVE")],
        )
        assert request["comment"] == perf_seed.RETENTION_COMMENT
        confirmed = snapshot_job.retention_policy_for(db, interrupted.clock.now())
        assert confirmed.policy is not None and confirmed.refusal is None


# ``sandboxes.load_sandbox``: "period <period id> (<book>) could not replay <from> → <to>:
# <slug> [<gate>, …]: <detail>; it stays <state>." — the warning of one blocked period state.
_BLOCKED_REPLAY = re.compile(
    r"^period (?P<period>[0-9a-f-]{36}) \((?P<book>[A-Z0-9]+)\) could not replay "
    r"(?P<attempted>.+?): (?P<refusal>[a-z-]+) \[(?P<gates>[A-Z_, ]+)\]: .*; "
    r"it stays (?P<stays>[a-z_]+)\.$",
    re.DOTALL,
)
# The gates a journal run of the period answers; a sandbox holds none (journals are never copied).
_JOURNAL_GATES = ("BATCHES_ACKNOWLEDGED", "JE_BALANCED", "JE_COMPLETE")


def _sandbox_facts(sandbox_id: Any) -> dict[str, Any]:
    """What a load left in the sandbox: the tenant's kind and status (the directory's row), its
    period states by entity, book and month start, its lock rows, its ``LATE_EVENT`` items and
    the warnings of the period replay — each as entity, book, month start, severity and the
    gates its refusal names."""
    with platform_session("tenant_directory", actor_user_id=None, request_id="prf2-sandbox") as db:
        kind, status = db.execute(
            select(tenant.c.kind, tenant.c.status).where(tenant.c.id == sandbox_id)
        ).one()
    scope = DbContext(tenant_id=sandbox_id, user_id=None, entity_scope="*")
    of_period = period_state.join(
        period,
        and_(
            period.c.tenant_id == period_state.c.tenant_id, period.c.id == period_state.c.period_id
        ),
    ).join(
        legal_entity,
        and_(
            legal_entity.c.tenant_id == period_state.c.tenant_id,
            legal_entity.c.id == period_state.c.entity_id,
        ),
    )
    with tenant_session(scope, read_only=True) as db:
        states = {
            (str(code), str(book), start): str(found)
            for code, book, start, found in db.execute(
                select(
                    legal_entity.c.code,
                    period_state.c.book_code,
                    period.c.start_date,
                    period_state.c.state,
                ).select_from(of_period)
            )
        }
        locks = int(db.execute(select(func.count()).select_from(period_lock)).scalar_one())
        entity_codes = {
            row_id: str(code)
            for row_id, code in db.execute(select(legal_entity.c.id, legal_entity.c.code))
        }
        starts = {
            str(row_id): start
            for row_id, start in db.execute(select(period.c.id, period.c.start_date))
        }
        late = [
            (str(item_status), str(source), entity_codes.get(entity_id))
            for item_status, source, entity_id in db.execute(
                select(exception_item.c.status, exception_item.c.source, exception_item.c.entity_id)
                .where(exception_item.c.code == perf_seed.LATE_EVENT)
                .order_by(exception_item.c.exception_no)
            )
        ]
        blocked: list[dict[str, Any]] = []
        for severity, message, entity_id in db.execute(
            select(exception_item.c.severity, exception_item.c.message, exception_item.c.entity_id)
            .where(exception_item.c.code == "SANDBOX_REPLAY_BLOCKED")
            .order_by(exception_item.c.exception_no)
        ):
            said = _BLOCKED_REPLAY.match(str(message))
            assert said is not None, message
            blocked.append(
                {
                    "where": (
                        entity_codes.get(entity_id),
                        said["book"],
                        starts.get(said["period"]),
                    ),
                    "severity": str(severity),
                    "attempted": said["attempted"],
                    "refusal": said["refusal"],
                    "gates": tuple(said["gates"].split(", ")),
                    "stays": said["stays"],
                }
            )
    return {
        "kind": str(kind),
        "status": str(status),
        "states": states,
        "locks": locks,
        "late": late,
        "blocked": blocked,
    }


def test_the_stored_snapshot_restores_into_a_sandbox_that_leaves_its_locked_months_in_soft_close(
    seeded: perf_seed.PerfSeedResult, interrupted: Shared
) -> None:
    """DG-PERF-02 (1), which ``make perf`` does not measure: the snapshot the seed stored is
    restored into a new sandbox by the product's own command — ``POST /tenant/sandboxes``, a
    ``TENANT_SNAPSHOT`` job in load-only mode that never exports again (04 API-R-04). Here
    perf-controller asks it over the seed's snapshot and the job runs in place.

    What the product delivers today, pinned exactly, as its own module pins it for a lock chain
    written by hand (``tests/domain/platform/test_sandbox_replay.py``; supervisor ruling R-10:
    the sandbox-side close replay, SNP-2b, is not built). The load SUCCEEDS; the sandbox is an
    ACTIVE tenant of kind ``sandbox``; every group is recomputed and none is left; no (group,
    book) differs from the source in its monetary state. The periods open and their soft close
    is replayed; each lock the seed made is then refused by the close gates, which the replay
    evaluates in the sandbox: it holds no journal run of its own — journals are never copied
    (05 SBX-03) — so the three gates a journal run answers fail for every period, and the
    recompute of the load answers the generator's late event of VOL-UK with ``LATE_EVENT``
    again, open, because the waiver is the source's, so that entity's periods fail the
    exceptions gate too. ``CLOSE_RUN_COMPLETED`` is not among them: the seed's locks certified
    their close run, and the replay lays that result over the sandbox's (R-116 (e)). Every
    period state the seed locked is named once in ``blocked_periods`` and stands at ``closing``
    with one warning and no lock row; month 7 is open.

    The pin is exact on purpose: the day a gate stops failing here, SNP-2b has moved, and the
    pin turns to ``closed``.

    Last in the module: it adds a tenant, which the count of the demo tenants must not meet."""
    from erev_api.domain.platform import snapshots
    from erev_api.jobs.registry import run_job

    manifest = _manifest()
    ctx, services = interrupted.context()
    snapshot_id = UUID(str(seeded.snapshot_id))
    with ctx.command(perf_seed.PERF_CONTROLLER.key, "tenant.snapshot") as uow:
        sandbox_id, deferred = snapshots.request_sandbox(
            uow, tenant_snapshot_id=snapshot_id, name="perf-run-story"
        )
    run_job(deferred.id, ctx.tenant_id, attempt=1, runtime=services.runtime)
    interrupted.persona_run.sign_out_all()
    scope = DbContext(tenant_id=ctx.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        state, problem, result = db.execute(
            select(job.c.state, job.c.problem, job.c.result).where(job.c.id == deferred.id)
        ).one()
        row = db.execute(
            select(
                tenant_snapshot.c.status,
                tenant_snapshot.c.purpose,
                tenant_snapshot.c.target_tenant_id,
            ).where(tenant_snapshot.c.id == snapshot_id)
        ).one()
    assert str(state) == "SUCCEEDED", problem
    counts = result["counts"]
    found = _sandbox_facts(sandbox_id)
    said = {entry["where"]: entry["gates"] for entry in found["blocked"]}
    context = f"{counts}; late {found['late']}; blocked {said}"
    assert counts["already_done"] == 1, context  # the stored snapshot is loaded, never exported
    assert (counts["groups_recomputed"], counts["groups_not_recomputed"]) == (
        len(manifest.contracts),
        0,
    ), context
    assert counts["derived_mismatches"] == 0, context
    assert (str(row.status), str(row.purpose), row.target_tenant_id) == (
        "SUCCEEDED",
        "STORED_BACKUP",
        sandbox_id,
    )
    assert (found["kind"], found["status"]) == ("sandbox", "ACTIVE")
    books = [(entity.code, book) for entity in manifest.entities for book in entity.books]
    locked = [
        (entity_code, book, volume.month_start(month))
        for month in range(1, LOCKED + 1)
        for entity_code, book in books
    ]
    # Where the path stops: every period state the seed locked, at its soft close.
    assert counts["blocked_periods"] == len(locked) == LOCKED * 4, context
    for where in locked:
        assert found["states"][where] == "closing", (where, context)
    for entity_code, book in books:
        where = (entity_code, book, volume.month_start(MONTHS))
        assert found["states"][where] == "open", (where, context)
    assert found["locks"] == 0, context
    # The generator's one late event inside the six months: answered again, and nobody's waiver.
    assert found["late"] == [("OPEN", "ENGINE", "VOL-UK")], context
    # One warning for each blocked period state, with the gates that refused its lock.
    assert sorted(said, key=str) == sorted(locked, key=str), context
    assert len(found["blocked"]) == len(locked), context
    for entry in found["blocked"]:
        entity_code = entry["where"][0]
        assert (entry["severity"], entry["attempted"], entry["refusal"], entry["stays"]) == (
            "WARNING",
            "closing → closed",
            "close-gates-failed",
            "closing",
        ), entry
        wanted = (
            tuple(sorted((*_JOURNAL_GATES, "EXCEPTIONS_CLEARED")))
            if entity_code == "VOL-UK"
            else _JOURNAL_GATES
        )
        assert entry["gates"] == wanted, (entry, context)
