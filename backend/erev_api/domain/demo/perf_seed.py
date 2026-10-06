"""``erev perf seed`` (BUILD_SPEC PRF-2; dev-guide DG-MK-perf-seed, DG-PERF-01; 05 PERF-04, PERF-11,
PERF-15, PERF-27; REQ-OPS-009; supervisor rulings D-98 candidate 148 AMENDMENT 5 and of 2026-10-01
on item PERF-SEED-LOCK-1).

The persistent volume tenant ``perf-volume`` in database ``erev``: ``kind = production``,
``is_demo =
true``, ``industry_cluster = perf:<first 16 hex of the manifest SHA-256>``. Idempotent: up to date →
"perf-volume up to date", exit 0, no write; another generator version → exit 2 with "perf tenant
built
from another generator version; run make db-reset"; the same hash but incomplete → resume at the
first unfinished step (the resume ledger reads the database; events carry deterministic keys).

The months before the manifest's last — 1 to 23 of 24 — are closed and locked as a person closes
a period, entity by entity and book by book in month order (``closing.close_period``, the helper
of the demo world's close stage): the soft close, the close run, the journal run submitted,
approved, exported as a CSV batch and acknowledged, the lock requested and decided.
``perf-accountant`` prepares, ``perf-reviewer`` approves the journal run and ``perf-controller``
decides the lock (PRD WLD-R-02: nobody decides what she prepared). Three things are the
volume tenant's own:

- ``close.require_reconciliations_for_lock`` is false, by a ``CLOSE`` registry version of scope
  TENANT that the accountant authors and the reviewer approves before anything else is seeded
  (``_lock_without_reconciliations``). The reconciliations of a period are witnessed by the demo
  world's close stage (``tests/domain/demo/test_close_history_seed.py``), not by this dataset.
- An event the generator records a month late (05 PERF-14) arrives after a later-dated event of
  its contract, and the engine answers it with a ``LATE_EVENT`` item that holds every lock of its
  entity. Its input is committed, so it is not dismissed (PRD BR-DAT-04): the accountant asks its
  waiver and the reviewer decides it (``_waive_late_events``). Any other open item that holds a
  lock stops the seed by name (``SeedStopped``), before the lock is asked.
- ``platform.snapshot_retention_families`` states the five families of the product's proposed
  catalogue, by a ``PLATFORM`` registry version of scope TENANT that the accountant authors and
  the reviewer approves (``_confirm_retention``): the export of a snapshot asks a confirmed
  policy with a named human approval (PRD ERR-77). It is the seed's confirmation of a proposal
  for its own synthetic dataset — nobody's legal judgement, and no default for real data.

A run that finds a month in soft close or locked — resumed after its lock phase began, or
extending an earlier ``--through-month`` — appends what is missing and does not repeat the bulk
recompute of the groups, which 05 PERF-15 places before the first close, with every period open
(``volume.recompute_due``).

The events of the manifest's last month are held back (``through_month`` defaults to its months
less one). The snapshot of step 5 is a stored backup — purpose ``STORED_BACKUP``: the product
stores it and loads nothing, where a ``SANDBOX_SEED`` request names a sandbox and loads it in the
same job (04 API-R-04); the seed stores, and ``make perf`` restores the row into its sandbox. It
is requested as of the instant captured after the month-23 lock, with the fresh MFA step-up
``request_snapshot`` requires (never bypassed), and exported by the request's own job, run in
place as a worker runs it, so that no job of the request is left queued.

Database-bound throughout: authored for ``make perf-seed`` (Ray-side) and NOT RUN in the lane.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction
from functools import partial
from pathlib import Path
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import and_, select

from erev_api.auth.keyring import KeyRing
from erev_api.clock import Clock
from erev_api.db.session import DbContext, platform_session, tenant_session
from erev_api.db.tables import (
    audit_event,
    contract,
    contract_event,
    event_submission,
    fiscal_calendar,
    legal_entity,
    period,
    period_state,
    pob_template,
    product,
    tenant,
    tenant_snapshot,
)
from erev_api.domain.contracts import events as contract_events
from erev_api.domain.demo import builders, volume
from erev_api.domain.demo.personas import Persona, _everywhere
from erev_api.domain.demo.sessions import PersonaRun, SeedSecrets, authorize, invite
from erev_api.domain.platform import provisioning
from erev_api.enums import (
    ApprovalSubjectType,
    ExceptionSource,
    ModificationStatus,
    PeriodState,
    RegistryCategory,
)
from erev_api.files.store import FileStore
from erev_api.jobs.context import JobRuntime

TENANT_CODE: Final = volume.TENANT_CODE
DISPLAY_NAME: Final = "Volume tenant (performance)"
REPORTING_CURRENCY: Final = "USD"
GROUP: Final = "journey"  # the persona role map is the same for every group
CLUSTER_PATTERN: Final = re.compile(r"^perf:[0-9a-f]{16}$")
UP_TO_DATE: Final = "perf-volume up to date"
OTHER_VERSION: Final = "perf tenant built from another generator version; run make db-reset"
EXIT_UP_TO_DATE: Final = 0
EXIT_OTHER_VERSION: Final = 2
EXIT_PRECONDITION: Final = 1  # --snapshot-only before the months are locked (a named refusal)
SEED_MONTHS: Final = 23  # month 24 is held back for make perf (DG-PERF-01)


def seed_months(manifest: volume.VolumeManifest) -> int:
    """The months a seed of ``manifest`` appends and locks: every month but its last, which is
    held back (DG-PERF-01) — ``SEED_MONTHS`` for the dataset of 24. Only a test seeds fewer."""
    return manifest.months - 1


def last_month(manifest: volume.VolumeManifest, through_month: int | None) -> int:
    """The last month a run appends and locks: ``through_month`` when the caller names one, else
    every month but the manifest's last; never beyond the manifest."""
    return min(manifest.months, seed_months(manifest) if through_month is None else through_month)


def locked_pending_snapshot(month: int) -> str:
    return (
        f"perf-volume seeded and locked through month {month}; snapshot pending "
        "(make perf-seed runs ANALYZE, then erev perf seed --snapshot-only)"
    )


def snapshot_precondition(month: int) -> str:
    return (
        f"perf-volume is not locked through month {month}; "
        "run erev perf seed before --snapshot-only"
    )


TAKING_SNAPSHOT: Final = "taking the stored snapshot of perf-volume"
LOCKED_PENDING_SNAPSHOT: Final = locked_pending_snapshot(SEED_MONTHS)
SNAPSHOT_PRECONDITION: Final = snapshot_precondition(SEED_MONTHS)
WARN_SECONDS: Final = 3_600.0  # 05 PERF-04
# The comment of a month's lock request: this tenant's lock asks no reconciliation (05 PERF-15).
CERTIFICATION: Final = "Journals acknowledged: the month of the volume dataset is complete."
PARAMETER_COMMENT: Final = "The volume dataset locks its months without reconciliations."
# The comment of a waiver names the generator (PRD BR-DAT-04, SM-06: a waiver carries a comment).
WAIVER_COMMENT: Final = (
    "A late event of the volume generator (05 PERF-14): it is recorded a month after its "
    "effective date by design, and the dataset keeps it."
)
LATE_EVENT: Final = "LATE_EVENT"  # 04 §15.4; PRD IMP-39
# T-PLT-34: the snapshot of step 5 is stored and loads nothing (04 API-R-04; DG-MK-perf-seed).
SNAPSHOT_PURPOSE: Final = "STORED_BACKUP"
SNAPSHOT_SUCCEEDED: Final = "SUCCEEDED"
# E-13: the states of a job that has not ended — the snapshot's job did not run in this process.
JOB_UNFINISHED: Final = frozenset({"QUEUED", "RUNNING"})
RETENTION_COMMENT: Final = (
    "The volume dataset confirms the proposed snapshot retention families for its own "
    "synthetic data."
)
ITEMS_NAMED: Final = 5  # the items a stopped seed names before "and N more"
REPORT_DIR: Final = "perf-seed"
# The cast (Codex 0105 P7-PRF2-PERSONA-1): four personas whose default roles are SoD-clean under
# the default rules (``sod_conflicts``) and together hold every permission the seed uses
# (``REQUIRED_PERMISSIONS``); the approver is never the preparer (WLD-R-02). The admin is the
# provisioning Tenant Admin and holds nothing else (SoD-1). The accountant prepares: the reference
# data, the contracts and their events, and each month's close — the soft close, the close run,
# the journal run and its export, the lock request, the waiver request of a late event. The
# controller opens the periods, decides the locks and requests the snapshot. The reviewer
# approves: its controller role carries config.approve for the published versions, its
# revenue_reviewer role event.approve for the accountant's manual events (BUILD_SPEC CTR-6), and
# either role journal.approve for the journal runs and exception.waive for the waivers.
PERF_ADMIN: Final = Persona(
    "perf-admin", "PRF-U-01", "Perf Admin", "perf-admin@demo.erev", _everywhere("tenant_admin")
)
PERF_ACCOUNTANT: Final = Persona(
    "perf-accountant",
    "PRF-U-02",
    "Perf Accountant",
    "perf-accountant@demo.erev",
    _everywhere("revenue_accountant", "ssp_analyst"),
)
PERF_CONTROLLER: Final = Persona(
    "perf-controller",
    "PRF-U-03",
    "Perf Controller",
    "perf-controller@demo.erev",
    _everywhere("controller"),
)
PERF_REVIEWER: Final = Persona(
    "perf-reviewer",
    "PRF-U-04",
    "Perf Reviewer",
    "perf-reviewer@demo.erev",
    _everywhere("revenue_reviewer", "ssp_approver", "controller"),
)
CAST: Final = (PERF_ADMIN, PERF_ACCOUNTANT, PERF_CONTROLLER, PERF_REVIEWER)
# The permissions the seed exercises as each persona (volume.py command guards, the close and
# snapshot commands, the approval subjects' required permissions); ``_require_grants`` reads the
# EFFECTIVE grants after provisioning and refuses by name when any is missing.
REQUIRED_PERMISSIONS: Final[Mapping[str, frozenset[str]]] = {
    PERF_ADMIN.key: frozenset({"settings.manage", "user.manage", "access.approve"}),
    # ``period.close``, ``journal.run`` and ``journal.export``: a month's close as its preparer
    # (``closing``); ``exception.resolve``: the waiver request of a late event.
    PERF_ACCOUNTANT.key: frozenset(
        {
            "masterdata.maintain",
            "config.author",
            "ssp.create",
            "contract.create",
            "event.record",
            "modification.create",
            "estimate.create",
            "judgement.create",
            "period.close",
            "journal.run",
            "journal.export",
            "exception.resolve",
        }
    ),
    # ``period.close``: opening the periods (volume.py); ``period.lock``: the lock decisions;
    # ``estimate.approve`` and ``contract.approve``: the Controller's second step of an estimate
    # version and of an activation of USD 1,000,000.00 and more (volume.py).
    PERF_CONTROLLER.key: frozenset(
        {"period.close", "period.lock", "tenant.snapshot", "estimate.approve", "contract.approve"}
    ),
    # ``journal.approve``: the journal runs; ``exception.waive``: the waivers. The lock is the
    # controller's to decide, so the reviewer is asked no ``period.lock``.
    PERF_REVIEWER.key: frozenset(
        {
            "config.approve",
            "ssp.approve",
            "judgement.review",
            "contract.approve",
            "estimate.approve",
            "modification.approve",
            "event.approve",
            "journal.approve",
            "exception.waive",
        }
    ),
}


class SeedStopped(RuntimeError):
    """The seed met a state it does not act on and says which (``erev perf seed`` prints it,
    exit 1): an open exception item that holds a lock and is not a late event of the generator,
    or a snapshot of step 5 whose job did not succeed."""


class GrantsMissing(RuntimeError):
    """A persona's effective grants lack a permission the seed uses (refused by name)."""


def expected_permissions(persona: Persona) -> frozenset[str]:
    """The permissions the persona's default roles grant (``auth.permissions.DEFAULT_ROLES``)."""
    from erev_api.auth.permissions import DEFAULT_ROLES

    return frozenset().union(*(DEFAULT_ROLES[code] for code in persona.roles_in(GROUP)))


def sod_conflicts(persona: Persona) -> tuple[str, ...]:
    """The default SoD rules the persona's combined roles would meet (both functions held):
    empty for every cast member, so the invitations pass ``sod.assert_assignments_allowed``."""
    from erev_api.domain.platform.sod_seed import DEFAULT_SOD_RULES

    held = expected_permissions(persona)
    return tuple(
        rule.code for rule in DEFAULT_SOD_RULES if held & rule.function_a and held & rule.function_b
    )


# seeded / resumed: steps 1-3 ran; locked: steps 1-3 were already complete, the snapshot (step 5)
# is pending; snapshot: --snapshot-only took it; refused: --snapshot-only before the lock.
Outcome = Literal[
    "up_to_date", "other_version", "seeded", "resumed", "locked", "snapshot", "refused"
]


def cluster_valid(value: str | None) -> bool:
    """05 PERF-11: a ``perf:`` cluster is exactly ``perf:<16 hex>`` (provisioning validation)."""
    return (
        value is None
        or not value.startswith("perf:")
        or CLUSTER_PATTERN.fullmatch(value) is not None
    )


@dataclass(frozen=True, slots=True)
class TenantFacts:
    tenant_id: UUID
    industry_cluster: str | None
    is_demo: bool
    kind: str


@dataclass(frozen=True, slots=True)
class Ledger:
    """What the database already holds for this manifest (the resume ledger)."""

    calendar: bool
    products: int
    templates: int
    contracts: frozenset[str]  # external ids present
    months_appended: Mapping[str, frozenset[int]]  # external id → recorded months appended
    months_locked: frozenset[int]  # months locked for every entity and book
    seed_snapshot: UUID | None  # a SUCCEEDED snapshot of ``SNAPSHOT_PURPOSE``
    # external id → (recorded month, part) of the earlier appends of a month that a command of
    # its own divides (``volume.append_comment``); the month's last append is ``months_appended``.
    parts_appended: Mapping[str, frozenset[tuple[int, int]]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Decision:
    outcome: Outcome
    message: str
    exit_code: int


def decide(
    facts: TenantFacts | None,
    ledger: Ledger | None,
    manifest: volume.VolumeManifest,
    *,
    snapshot_only: bool = False,
) -> Decision:
    """The DG-MK-perf-seed decision, pure. ``erev perf seed`` is steps 1-3 (provision, months
    1-23, the month locks); ``--snapshot-only`` is step 5, run by ``make perf-seed`` AFTER the
    ANALYZE of step 4 (D-98 148 A5, Q6 ruling: the governed order exactly). Both modes: same
    cluster and complete → up to date (exit 0, no write); another cluster → exit 2. The messages
    name the last month the seed locks (``seed_months``: 23 of the dataset's 24)."""
    last = seed_months(manifest)
    if facts is None:
        if snapshot_only:
            return Decision("refused", snapshot_precondition(last), EXIT_PRECONDITION)
        return Decision("seeded", "provisioning perf-volume", 0)
    if facts.industry_cluster != manifest.industry_cluster:
        return Decision("other_version", OTHER_VERSION, EXIT_OTHER_VERSION)
    if ledger is not None and complete(ledger, manifest):
        return Decision("up_to_date", UP_TO_DATE, EXIT_UP_TO_DATE)
    if ledger is not None and locked_through(ledger, manifest):
        if snapshot_only:
            return Decision("snapshot", TAKING_SNAPSHOT, 0)
        return Decision("locked", locked_pending_snapshot(last), 0)
    if snapshot_only:
        return Decision("refused", snapshot_precondition(last), EXIT_PRECONDITION)
    return Decision("resumed", "resuming perf-volume at the first unfinished step", 0)


def locked_through(ledger: Ledger, manifest: volume.VolumeManifest) -> bool:
    """Steps 1-3 complete: reference data, products, templates, every contract, and every month
    the seed locks (``seed_months``: 1-23 of the dataset's 24) locked for every entity and book."""
    return (
        ledger.calendar
        and ledger.products >= len(manifest.products)
        and ledger.templates >= len(manifest.templates)
        and all(c.external_id in ledger.contracts for c in manifest.contracts)
        and set(range(1, seed_months(manifest) + 1)) <= ledger.months_locked
    )


def complete(ledger: Ledger, manifest: volume.VolumeManifest) -> bool:
    """Steps 1-3 and the step-5 snapshot: the DG-MK-perf-seed "up to date" condition."""
    return locked_through(ledger, manifest) and ledger.seed_snapshot is not None


@dataclass
class PerfSeedResult:
    outcome: Outcome
    exit_code: int
    message: str
    manifest_sha256: str
    industry_cluster: str
    contracts: int
    obligations: int
    events_appended: int  # newly appended by the run
    events_reused: int  # already persisted by an earlier run (a resume), not re-appended
    events_deferred: int  # counted, not appended (SEPARATE_CONTRACT modifications)
    months_locked: int
    snapshot_id: str | None
    seconds: float
    warning: str | None = None
    notes: list[str] = field(default_factory=list)
    phase: str = "seed"  # "seed" (steps 1-3) or "snapshot" (step 5, --snapshot-only)

    def document(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "outcome": self.outcome,
            "exit_code": self.exit_code,
            "message": self.message,
            "manifest_sha256": self.manifest_sha256,
            "industry_cluster": self.industry_cluster,
            "contracts": self.contracts,
            "obligations": self.obligations,
            "events_appended": self.events_appended,
            "events_reused": self.events_reused,
            "events_deferred": self.events_deferred,
            "months_locked": self.months_locked,
            "snapshot_id": self.snapshot_id,
            "seconds": self.seconds,
            "warning": self.warning,
            "notes": list(self.notes),
        }


def merge_report(prior: Mapping[str, Any] | None, current: Mapping[str, Any]) -> dict[str, Any]:
    """The step-6 report after ``--snapshot-only``: the seed phase's counts, seconds and notes are
    kept from the earlier document (when there is one) and the snapshot phase adds its id, outcome,
    message, exit code and its own seconds. Pure."""
    if prior is None or str(current.get("phase")) != "snapshot":
        return dict(current)
    merged = dict(prior)
    merged.update(
        {
            "phase": "snapshot",
            "outcome": current["outcome"],
            "exit_code": current["exit_code"],
            "message": current["message"],
            "snapshot_id": current.get("snapshot_id"),
            "snapshot_seconds": current.get("seconds"),
            "warning": current.get("warning") or prior.get("warning"),
            "notes": [*prior.get("notes", []), *current.get("notes", [])],
        }
    )
    return merged


def write_report(result: PerfSeedResult, reports_dir: Path) -> Path:
    path = reports_dir / REPORT_DIR / "report.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    prior: dict[str, Any] | None = None
    if result.phase == "snapshot" and path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = None
        prior = loaded if isinstance(loaded, dict) else None
    document = merge_report(prior, result.document())
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


# --- reads (two scopes: directory, then the tenant's own context; no bypass) ----------------------


def read_tenant(request_id: str) -> TenantFacts | None:
    with platform_session("tenant_directory", actor_user_id=None, request_id=request_id) as db:
        row = db.execute(
            select(tenant.c.id, tenant.c.industry_cluster, tenant.c.is_demo, tenant.c.kind).where(
                tenant.c.code == TENANT_CODE
            )
        ).one_or_none()
    if row is None:
        return None
    return TenantFacts(UUID(str(row.id)), row.industry_cluster, bool(row.is_demo), str(row.kind))


def read_ledger(tenant_id: UUID, manifest: volume.VolumeManifest) -> Ledger:
    scope = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(scope, read_only=True) as db:
        calendar = db.execute(
            select(fiscal_calendar.c.id).where(fiscal_calendar.c.code == volume.CALENDAR_CODE)
        ).first()
        products = db.execute(select(product.c.code)).scalars().all()
        templates = db.execute(select(pob_template.c.code)).scalars().all()
        by_contract_id = {
            str(row_id): str(external_id)
            for row_id, external_id in db.execute(
                select(contract.c.id, contract.c.external_id)
            ).tuples()
        }
        external_ids = frozenset(by_contract_id.values())
        # Codex 0246: an ORDINARY append leaves no event_submission row — its durable effects are
        # the contract_event rows and the record_events AUDIT detail carrying the Volume comment
        # and the appended event ids. The month is done only when every appended event persists.
        audit_rows = [
            (row.object_id, row.detail)
            for row in db.execute(
                select(audit_event.c.object_id, audit_event.c.detail).where(
                    audit_event.c.action == contract_events.RECORD_ACTION,
                    audit_event.c.object_type == contract_events.CONTRACT_OBJECT,
                    audit_event.c.detail.op("->>")("comment").like("Volume month %"),
                )
            ).all()
        ]
        # BUILD_SPEC CTR-6: a contract-month that holds a manual event is stored as an event
        # submission and appended by its approval, so its durable effects are the APPLIED
        # submission — the Volume comment and the applied event ids — and the contract_event
        # rows. A submission still SUBMITTED marks nothing: the resume approves it
        # (``volume._record_batch``).
        applied_rows = [
            (row.contract_id, {"comment": row.comment, "event_ids": list(row.applied_event_ids)})
            for row in db.execute(
                select(
                    event_submission.c.contract_id,
                    event_submission.c.comment,
                    event_submission.c.applied_event_ids,
                ).where(
                    event_submission.c.status == ModificationStatus.APPLIED.value,
                    event_submission.c.comment.like("Volume month %"),
                )
            ).all()
        ]
        persisted = {str(v) for v in db.execute(select(contract_event.c.id)).scalars()}
        months = {
            by_contract_id[contract_id]: found
            for contract_id, found in months_from_audit(
                [*audit_rows, *applied_rows], persisted, manifest.industry_cluster
            ).items()
            if contract_id in by_contract_id
        }
        parts = {
            by_contract_id[contract_id]: found
            for contract_id, found in parts_from_audit(
                [*audit_rows, *applied_rows], persisted, manifest.industry_cluster
            ).items()
            if contract_id in by_contract_id
        }
        locked = _locked_months(db, manifest)
        snapshot = db.execute(
            select(tenant_snapshot.c.id)
            .where(
                tenant_snapshot.c.purpose == SNAPSHOT_PURPOSE,
                tenant_snapshot.c.status == SNAPSHOT_SUCCEEDED,
            )
            .order_by(tenant_snapshot.c.known_at.desc())
            .limit(1)
        ).scalar_one_or_none()
    known_products = {p.code for p in manifest.products}
    known_templates = {t.code for t in manifest.templates}
    return Ledger(
        calendar=calendar is not None,
        products=sum(1 for code in products if str(code) in known_products),
        templates=sum(1 for code in templates if str(code) in known_templates),
        contracts=external_ids,
        months_appended={k: frozenset(v) for k, v in months.items()},
        months_locked=locked,
        seed_snapshot=None if snapshot is None else UUID(str(snapshot)),
        parts_appended={k: frozenset(v) for k, v in parts.items()},
    )


_MONTH_COMMENT: Final = re.compile(r"^Volume month (\d+) \((perf:[0-9a-f]{16})\)$")


def months_from_audit(
    rows: Iterable[tuple[Any, Mapping[str, Any] | None]], persisted: Collection[str], cluster: str
) -> dict[str, set[int]]:
    """The resume ledger's appended months per contract id, from the DURABLE effects of the
    appends (Codex 0246): each ``record_events`` audit row carries the append's ``comment`` and
    ``event_ids`` — and each APPLIED event submission its comment and the ids its approval
    applied, read into the same shape (BUILD_SPEC CTR-6); a (contract, month) is done only when
    the comment names this manifest's month and EVERY appended event id still persists as a
    ``contract_event`` row — a comment alone, or an audit whose events are gone, marks nothing.
    Pure."""
    done: dict[str, set[int]] = {}
    persisted_ids = set(persisted)
    for contract_id, detail in rows:
        detail = detail or {}
        month = _appended_month(str(detail.get("comment") or ""), cluster)
        if month is None:
            continue
        event_ids = [str(v) for v in (detail.get("event_ids") or [])]
        if not event_ids or not set(event_ids) <= persisted_ids:
            continue
        done.setdefault(str(contract_id), set()).add(month)
    return done


def _appended_month(comment: str, cluster: str) -> int | None:
    """The recorded month of a volume append submission (``volume._append_month`` comments)."""
    found = _MONTH_COMMENT.match(comment)
    if found is None or found.group(2) != cluster:
        return None
    return int(found.group(1))


_PART_COMMENT: Final = re.compile(
    r"^Volume month (\d+) part (\d+) of (\d+) \((perf:[0-9a-f]{16})\)$"
)


def parts_from_audit(
    rows: Iterable[tuple[Any, Mapping[str, Any] | None]], persisted: Collection[str], cluster: str
) -> dict[str, set[tuple[int, int]]]:
    """The earlier appends of the divided months, per contract id, as (recorded month, part):
    a contract-month that an estimate change or an amendment divides is sent as several appends
    (``volume.month_steps``), the last under the month's plain comment — ``months_from_audit``
    reads that one — and each earlier one under ``Volume month <n> part <k> of <parts>``. The rule
    is the month's: a part is done only when the comment names this manifest and EVERY event id
    of the append still persists. Pure."""
    done: dict[str, set[tuple[int, int]]] = {}
    persisted_ids = set(persisted)
    for contract_id, detail in rows:
        detail = detail or {}
        found = _PART_COMMENT.match(str(detail.get("comment") or ""))
        if found is None or found.group(4) != cluster:
            continue
        event_ids = [str(v) for v in (detail.get("event_ids") or [])]
        if not event_ids or not set(event_ids) <= persisted_ids:
            continue
        done.setdefault(str(contract_id), set()).add((int(found.group(1)), int(found.group(2))))
    return done


def _elapsed(now: datetime, started: datetime) -> float:
    """Seconds between two clock reads, rounded to milliseconds."""
    return round((now - started).total_seconds(), 3)


def _locked_months(db: Any, manifest: volume.VolumeManifest) -> frozenset[int]:
    rows = db.execute(
        select(
            legal_entity.c.code, period_state.c.book_code, period.c.start_date, period_state.c.state
        ).select_from(
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
    ).all()
    wanted = {(e.code, book) for e in manifest.entities for book in e.books}
    locked: frozenset[int] = frozenset()
    for month in range(1, manifest.months + 1):
        start = volume.month_start(month)
        states = {
            (str(code), str(book)): str(state)
            for code, book, start_date, state in rows
            if start_date == start and (str(code), str(book)) in wanted
        }
        if len(states) == len(wanted) and all(
            s in {PeriodState.CLOSED.value, PeriodState.PERMANENTLY_LOCKED.value}
            for s in states.values()
        ):
            locked |= {month}
    return locked


# --- the run -------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Services:
    clock: Clock
    keyring: KeyRing
    files: FileStore
    runtime: JobRuntime  # the configured key ring and file store for the inline snapshot export
    secrets: SeedSecrets
    request_id: str
    os_user: str | None
    key_provisioner: Any = None


def run(
    services: Services,
    *,
    reports_dir: Path,
    scale: Fraction = Fraction(1),
    through_month: int | None = None,
    months: int = volume.MONTHS,
    guard: Callable[[Any, str], None] = authorize,
    snapshot_only: bool = False,
) -> PerfSeedResult:
    """DG-MK-perf-seed steps 1-3 (``snapshot_only=False``: provision, months, locks) or step 5
    (``snapshot_only=True``: the stored snapshot as of a ``known_at`` after the month-23
    lock, once ``make perf-seed`` has run the step-4 ANALYZE); returns the result the CLI prints
    and ``write_report`` stores. ``months`` is the manifest's horizon — 24, the dataset's; a
    test seeds fewer — and ``through_month`` the last month appended and locked, by default every
    month but the manifest's last (``seed_months``)."""
    started = services.clock.now()  # elapsed time from the injected clock (DG-ARC-05)
    manifest = volume.manifest(scale, months=months)
    last = last_month(manifest, through_month)
    facts = read_tenant(services.request_id)
    ledger = None if facts is None else read_ledger(facts.tenant_id, manifest)
    decision = decide(facts, ledger, manifest, snapshot_only=snapshot_only)
    result = PerfSeedResult(
        outcome=decision.outcome,
        exit_code=decision.exit_code,
        message=decision.message,
        manifest_sha256=manifest.sha256,
        industry_cluster=manifest.industry_cluster,
        contracts=len(manifest.contracts),
        obligations=manifest.counts.obligations,
        events_appended=0,
        events_reused=0,
        events_deferred=0,
        months_locked=0 if ledger is None else len(ledger.months_locked),
        snapshot_id=None
        if ledger is None or ledger.seed_snapshot is None
        else str(ledger.seed_snapshot),
        seconds=0.0,
        phase="snapshot" if snapshot_only else "seed",
    )
    if decision.outcome in ("up_to_date", "other_version", "locked", "refused"):
        result.seconds = _elapsed(services.clock.now(), started)
        return result
    persona_run = PersonaRun(
        clock=services.clock,
        keyring=services.keyring,
        files=services.files,
        secrets=services.secrets,
        request_id=services.request_id,
    )
    try:
        if facts is None:
            assert not snapshot_only  # decide() refused that combination above
            tenant_id = _provision(services, persona_run, manifest)
        else:
            tenant_id = facts.tenant_id
            _sign_in_existing(services, persona_run, tenant_id)
        ctx = build_context(services, persona_run, tenant_id, guard=guard)
        if snapshot_only:
            # Step 5: the lock happened earlier (steps 1-3), so this known_at is after it. A
            # tenant seeded before the seed confirmed its retention families gets them here.
            _confirm_retention(ctx)
            known_at = services.clock.now()
            result.snapshot_id = str(_seed_snapshot(services, ctx, known_at, ledger))
        else:
            # Before anything else is seeded: a settings version is simulated when it is tested,
            # and an empty tenant has nothing to simulate.
            _lock_without_reconciliations(ctx)
            _confirm_retention(ctx)
            report = volume.seed(
                ctx,
                months=months,
                scale=scale,
                cast=volume.PERF_CAST,
                through_month=last,
                runtime=services.runtime,  # the modification previews run inline with it
                ledger=None
                if ledger is None
                else volume.SeedLedger(
                    calendar=ledger.calendar,
                    products=ledger.products,
                    templates=ledger.templates,
                    contracts=ledger.contracts,
                    months_appended=ledger.months_appended,
                    parts_appended=ledger.parts_appended,
                ),
            )
            result.events_appended = report.events_appended
            result.events_reused = report.events_reused
            result.events_deferred = report.events_deferred
            result.notes.extend(
                f"deferred {kind}: {count}" for kind, count in report.deferred_by_type.items()
            )
            result.months_locked = _close_and_lock(ctx, manifest, last, ledger)
            # The snapshot (step 5) is NOT taken here: make perf-seed runs ANALYZE (step 4) and
            # then `erev perf seed --snapshot-only` (DG-MK-perf-seed order; D-98 148 A5 Q6).
    finally:
        persona_run.sign_out_all()
    result.seconds = _elapsed(services.clock.now(), started)
    if result.seconds > WARN_SECONDS:
        result.warning = f"perf seed took {result.seconds:.0f} s, above 3,600 s (05 PERF-04)"
    return result


def build_context(
    services: Services,
    persona_run: PersonaRun,
    tenant_id: UUID,
    *,
    guard: Callable[[Any, str], None] = authorize,
) -> builders.BuildContext:
    """The seed's command context over the signed-in cast (also the DB witnesses' entry point,
    so they drive the very same per-event paths the seed uses). A persona whose second-factor
    verification has grown stale verifies again before a decision that asks a fresh one — a lock,
    a waiver (``PersonaRun.step_up``; PRD BR-PLT-06): the seed of 24 months runs for an hour."""
    return builders.BuildContext(
        tenant_id=tenant_id,
        tenant_code=TENANT_CODE,
        wld_id="PRF",
        cast={p.key: p for p in CAST},
        clock=services.clock,
        keyring=services.keyring,
        files=services.files,
        request_id=services.request_id,
        principal_context=persona_run.context,
        guard=guard,
        verify_again=persona_run.step_up,
    )


def _provision(
    services: Services, persona_run: PersonaRun, manifest: volume.VolumeManifest
) -> UUID:
    """DG-MK-perf-seed step 3: provision ``perf-volume`` (kind production, is_demo true,
    industry_cluster perf:<hash16>), invite the cast with its declared roles and join every
    persona with MFA."""
    provisioned = provisioning.provision_tenant(
        provisioning.TenantProvisionRequest(
            code=TENANT_CODE,
            display_name=DISPLAY_NAME,
            reporting_currency=REPORTING_CURRENCY,
            is_demo=True,
            admin_email=PERF_ADMIN.email,
            industry_cluster=manifest.industry_cluster,
        ),
        actor=provisioning.OperatorActor(
            channel="CLI",
            operator_user_id=None,
            os_user=services.os_user,
            request_id=services.request_id,
        ),
        clock=services.clock,
        keyring=services.keyring,
        key_provisioner=services.key_provisioner,
    )
    tenant_id = UUID(str(provisioned.tenant["id"]))
    # The bootstrap membership is the Tenant Admin's only. Every other persona is INVITED by the
    # admin with its declared roles through the supported command (``users.invite_user`` → one
    # ROLE_ASSIGNMENT request per role, approved by the bootstrap AUTO-BOOTSTRAP rule while setup
    # is incomplete, 04 §14.3) and joins with MFA; the effective grants are then read back.
    persona_run.join(PERF_ADMIN, tenant_id, provisioned.admin_membership_id, mfa=True)
    for persona in (PERF_ACCOUNTANT, PERF_CONTROLLER, PERF_REVIEWER):
        membership_id = invite(persona_run, PERF_ADMIN, persona, GROUP, tenant_id)
        persona_run.join(persona, tenant_id, membership_id, mfa=True)
    _require_grants(services, persona_run, tenant_id)
    return tenant_id


def _require_grants(services: Services, persona_run: PersonaRun, tenant_id: UUID) -> None:
    """Read each persona's EFFECTIVE grants (``auth.permissions.effective_grants`` in the tenant's
    read context, as ``PersonaRun.context`` does) and refuse by name when a permission the seed
    uses is missing — the CPU role tuples prove nothing about provisioned grants (Codex 0105)."""
    from erev_api.auth.permissions import effective_grants
    from erev_api.db.session import tenant_session
    from erev_api.domain.demo.sessions import read_only

    now = services.clock.now()
    missing: list[str] = []
    for persona in CAST:
        membership_id = persona_run.context(persona, tenant_id).principal.membership_id
        assert membership_id is not None
        with tenant_session(read_only(tenant_id), read_only=True) as session:
            held = effective_grants(session, membership_id, at=now).permissions
        lacking = sorted(REQUIRED_PERMISSIONS[persona.key] - held)
        if lacking:
            missing.append(f"{persona.key} lacks {', '.join(lacking)}")
    if missing:
        raise GrantsMissing("perf personas' effective grants are incomplete: " + "; ".join(missing))


def _sign_in_existing(services: Services, persona_run: PersonaRun, tenant_id: UUID) -> None:
    """A resumed run signs the personas in again through the product's sign-in (the invitation was
    accepted by the first run): reuse the persona sessions machinery's join on a fresh invitation is
    not possible, so the resume re-invites nothing and signs in with the password + TOTP."""
    from erev_api.auth import mfa, sessions, totp

    for persona in CAST:
        auth = sessions.sign_in(
            email=persona.email,
            password=services.secrets.password,
            facts=persona_run.facts(),
            keyring=services.keyring,
            previous_token=None,
        )
        step = totp.time_step(auth.facts.now)
        verified = mfa.verify(
            auth,
            code=totp.code_at(services.secrets.totp_secret, step),
            recovery_code=None,
            keyring=services.keyring,
        ).auth
        persona_run.sessions[persona.key] = sessions.select_tenant(
            persona_run._refreshed(verified),
            tenant_id,
            keyring=services.keyring,  # noqa: SLF001
        )
        persona_run.verified.add(persona.key)
    _require_grants(services, persona_run, tenant_id)


def _publish_setting(
    ctx: builders.BuildContext,
    *,
    category: RegistryCategory,
    values: Mapping[str, Any],
    comment: str,
    missing: Callable[[], bool],
    what: str,
) -> None:
    """A settings version of ``category`` and scope TENANT stating ``values``, as its people make
    it: the accountant authors, tests and submits it (``config.author``) and the reviewer
    approves it (``config.approve``) — a named person, never an automatic approval. A settings
    version names no date and is in force when it is approved (04 §16.5 "Order of effective
    instants"). ``missing`` answers whether the tenant still lacks what the version states;
    ``what`` names it in an error.

    Resumed by persisted state, as every configuration of the seed: nothing missing → nothing;
    an open version of the category — DRAFT or TESTED → tested, submitted, approved; SUBMITTED
    with its pending request → approved; anything else raises by name."""
    from erev_api.db.tables import approval_request, registry_version
    from erev_api.domain.policies import lifecycle, registry_versions
    from erev_api.enums import ApprovalRequestStatus, ConfigStatus, RegistryScope

    accountant, reviewer = PERF_ACCOUNTANT.key, PERF_REVIEWER.key
    if not missing():
        return
    with ctx.read() as session:
        versions = [
            (UUID(str(version_id)), str(status))
            for version_id, status in session.execute(
                select(registry_version.c.id, registry_version.c.status)
                .where(
                    registry_version.c.category == category.value,
                    registry_version.c.scope == RegistryScope.TENANT.value,
                )
                .order_by(registry_version.c.version_no.desc())
            ).tuples()
        ]
    unfinished = (
        ConfigStatus.DRAFT.value,
        ConfigStatus.TESTED.value,
        ConfigStatus.SUBMITTED.value,
    )
    live = [(version_id, status) for version_id, status in versions if status in unfinished]
    if live:
        version_id, status = live[0]
    else:
        with ctx.command(accountant, volume.CONFIG_AUTHOR) as uow:
            version_id = registry_versions.create_policy(
                uow,
                category=category,
                scope=RegistryScope.TENANT,
                entity_code=None,
                book_code=None,
                values=dict(values),
                effective_from=None,
            )
        status = ConfigStatus.DRAFT.value
    if status in (ConfigStatus.DRAFT.value, ConfigStatus.TESTED.value):
        # The POLICY_SIMULATION runner in place, as the preparer: no worker runs beside a seed.
        with ctx.command(accountant, volume.CONFIG_AUTHOR) as uow:
            digest = lifecycle.current_sha256(uow.session, registry_versions.KIND, version_id)
            registry_versions.run_test(
                uow,
                version_id,
                {
                    "subject_type": registry_versions.SUBJECT_TYPE,
                    "subject_id": str(version_id),
                    "run_simulation": True,
                    "content_sha256": digest,
                },
            )
        with ctx.command(accountant, volume.CONFIG_AUTHOR) as uow:
            registry_versions.submit_policy(uow, version_id, comment=comment)
        status = ConfigStatus.SUBMITTED.value
    with ctx.read() as session:
        pending = session.execute(
            select(approval_request.c.id).where(
                approval_request.c.subject_type == ApprovalSubjectType.REGISTRY_VERSION.value,
                approval_request.c.subject_id == version_id,
                approval_request.c.status == ApprovalRequestStatus.PENDING.value,
            )
        ).first()
    if pending is None:
        raise LookupError(
            f"the {category.value} version of {what} is {status} without a pending request"
        )
    ctx.approve(ApprovalSubjectType.REGISTRY_VERSION, version_id, [reviewer])
    if missing():
        raise LookupError(f"{what} is still missing after its version {version_id} was approved")


def _lock_without_reconciliations(ctx: builders.BuildContext) -> None:
    """05 PERF-15: the locks of the volume tenant ask no reconciliation —
    ``close.require_reconciliations_for_lock`` false, at both scales, by a ``CLOSE`` registry
    version of scope TENANT (``_publish_setting``: the accountant's, approved by the reviewer,
    resumed by its persisted state)."""
    from erev_api.domain.close import gates
    from erev_api.registry.resolve import setting

    code = gates.REQUIRE_RECONCILIATIONS

    def asked() -> bool:
        with ctx.read() as session:
            return setting(session, code, known_at=ctx.clock.now()) is not False

    _publish_setting(
        ctx,
        category=RegistryCategory.CLOSE,
        values={code: False},
        comment=PARAMETER_COMMENT,
        missing=asked,
        what=code,
    )


def _confirm_retention(ctx: builders.BuildContext) -> None:
    """The export of a snapshot asks a confirmed retention policy (PRD ERR-77; 04 T-PLT-31 rule
    2): a PUBLISHED version of scope TENANT that states the five families of
    ``platform.snapshot_retention_families`` and carries a named human approval, in force at the
    snapshot's ``known_at``. No seed of the product publishes one, so step 5 of this seed stopped
    at its export. The volume tenant states the families of the product's own catalogue
    (``snapshot_dataset.RETENTION_FAMILIES`` — marked PROPOSED there: counsel owns the periods)
    by a ``PLATFORM`` version (``_publish_setting``). It is the seed's confirmation of a proposal
    for its own synthetic dataset — nobody's legal judgement, and no default for a workspace of
    real data. The seed asks the product's own reading whether a policy is confirmed
    (``snapshot_job.retention_policy_for``)."""
    from erev_api.domain.platform import snapshot_dataset, snapshot_job

    def unconfirmed() -> bool:
        with ctx.read() as session:
            return snapshot_job.retention_policy_for(session, ctx.clock.now()).policy is None

    _publish_setting(
        ctx,
        category=RegistryCategory.PLATFORM,
        values={snapshot_dataset.RETENTION_PARAMETER: dict(snapshot_dataset.RETENTION_FAMILIES)},
        comment=RETENTION_COMMENT,
        missing=unconfirmed,
        what=snapshot_dataset.RETENTION_PARAMETER,
    )


def _text(value: object) -> str:
    return str(getattr(value, "value", value))


def foreign_items(items: Sequence[Any]) -> list[Any]:
    """Of the open items that hold a lock, those the seed does not waive: every one that is not
    a ``LATE_EVENT`` of source ``ENGINE`` — the engine's answer to an event that arrives after a
    later-dated event of its contract, which the generator plans (05 PERF-14). Pure."""
    engine = ExceptionSource.ENGINE.value
    return [
        item for item in items if _text(item.code) != LATE_EVENT or _text(item.source) != engine
    ]


def stopped_message(name: str, foreign: Sequence[Any]) -> str:
    """What a stopped seed says: the period, how many items hold its lock, and the first
    ``ITEMS_NAMED`` of them by number, code, source, severity and message. Pure."""
    named = "; ".join(
        f"{item.exception_no} {_text(item.code)} ({_text(item.source)}, "
        f"{_text(item.severity)}): {item.message}"
        for item in foreign[:ITEMS_NAMED]
    )
    more = len(foreign) - ITEMS_NAMED
    return (
        f"{name} cannot be locked: {len(foreign)} open exception item(s) hold it that are not "
        f"late events of the generator — {named}"
        + (f"; and {more} more" if more > 0 else "")
        + ". The seed waives nothing else: clear them and run it again."
    )


def _waive_late_events(ctx: builders.BuildContext, state_id: UUID, name: str) -> int:
    """Before the lock of a period is asked: the open exception items that hold it — the
    predicate of the gate "Exceptions resolved, waived or dismissed" itself
    (``gates.blocking_exceptions``) — are read. An item of code ``LATE_EVENT`` and source
    ``ENGINE`` is a late event of the generator (05 PERF-14; ``volume.late_arrivals`` counts
    them): its input is committed, so the clearance by a person is a waiver (PRD BR-DAT-04,
    SM-06) — the accountant asks it (``exception.resolve``) with a comment that names the
    generator, and the reviewer decides it (``exception.waive``), verifying again first when her
    verification is stale. A request an interrupted run left pending is decided, not asked twice.
    Any other item raises ``SeedStopped`` by name before one waiver is asked. Returns the number
    of items waived."""
    from erev_api.db.tables import approval_request, exception_item
    from erev_api.domain.close import gates
    from erev_api.domain.imports import exceptions
    from erev_api.enums import ApprovalRequestStatus

    with ctx.read() as session:
        scope = gates.period_scope(session, state_id)
        if scope is None:
            raise LookupError(f"{name} has no period state")
        items = session.execute(
            select(
                exception_item.c.id,
                exception_item.c.exception_no,
                exception_item.c.code,
                exception_item.c.source,
                exception_item.c.severity,
                exception_item.c.message,
            )
            .where(gates.blocking_exceptions(scope))
            .order_by(exception_item.c.exception_no)
        ).all()
        asked = (
            {
                UUID(str(value))
                for value in session.execute(
                    select(approval_request.c.subject_id).where(
                        approval_request.c.subject_type
                        == ApprovalSubjectType.EXCEPTION_WAIVER.value,
                        approval_request.c.status == ApprovalRequestStatus.PENDING.value,
                        approval_request.c.subject_id.in_([item.id for item in items]),
                    )
                ).scalars()
            }
            if items
            else set()
        )
    foreign = foreign_items(items)
    if foreign:
        raise SeedStopped(stopped_message(name, foreign))
    accountant, reviewer = PERF_ACCOUNTANT.key, PERF_REVIEWER.key
    for item in items:
        item_id = UUID(str(item.id))
        if item_id not in asked:
            with ctx.command(accountant, exceptions.RESOLVE_PERMISSION) as uow:
                exceptions.request_waiver(uow, item_id=item_id, comment=WAIVER_COMMENT)
        ctx.step_up(reviewer)
        ctx.approve(ApprovalSubjectType.EXCEPTION_WAIVER, item_id, [reviewer])
    return len(items)


def _close_and_lock(
    ctx: builders.BuildContext,
    manifest: volume.VolumeManifest,
    through_month: int,
    ledger: Ledger | None,
) -> int:
    """Months 1 to ``through_month`` in order, each for every entity and book: the period is
    closed as its people close it (``closing.close_period`` — the soft close, the close run, the
    journal run, the lock request by ``perf-accountant``, the journal run's approval by
    ``perf-reviewer``, the lock decision by ``perf-controller``), with the generator's late events
    waived before the lock is asked (``_waive_late_events``). A month the ledger holds as locked
    is passed, and the helper reads the state each step finds, so a seed interrupted inside a
    month resumes there and repeats nothing. A refused lock propagates with its gates; the period
    stays in soft close and the next run resumes at it. Returns the number of months locked."""
    from erev_api.domain.demo import closing
    from erev_api.enums import BookCode

    cast = closing.ClosingCast(
        preparer=PERF_ACCOUNTANT.key, reviewer=PERF_REVIEWER.key, controller=PERF_CONTROLLER.key
    )
    already = frozenset() if ledger is None else ledger.months_locked
    locked = 0
    for month in range(1, through_month + 1):
        if month in already:
            locked += 1
            continue
        period_key = manifest.periods[month - 1]
        for entity in manifest.entities:
            for book in entity.books:
                name = f"{entity.code} {book} {period_key}"
                closing.close_period(
                    ctx,
                    cast,
                    entity_code=entity.code,
                    book=BookCode(book),
                    period_key=period_key,
                    certification=CERTIFICATION,
                    before_lock=partial(_waive_late_events, ctx, name=name),
                )
        locked += 1
    return locked


def snapshot_stopped(status: str, problem: Mapping[str, Any] | None, *, job_state: str) -> str:
    """What a stopped step 5 says, by the state its job is in when ``run_job`` returns. Pure.

    The job is ``QUEUED`` or ``RUNNING``: it did not run in the command — ``run_job`` leaves a
    job a worker took, and one that found no free job slot of the workspace — so the snapshot
    has not ended; the sentence says so, and what the next run does. The job has ended: the
    state the snapshot ended in and the job's own sentences — its problem's detail, else its
    title, then the messages of its ``errors`` that add to it, each once."""
    if job_state in JOB_UNFINISHED:
        return (
            f"the snapshot of {TENANT_CODE} is {status}: its job is {job_state} and did not run "
            "in this command — a worker beside the seed holds it or fills the job slots of the "
            "workspace. Run make perf-seed again: a snapshot that has succeeded by then is used, "
            "and otherwise a new one is asked."
        )
    said: list[str] = []
    found = problem or {}
    for sentence in (
        found.get("detail") or found.get("title"),
        *(
            error.get("message")
            for error in found.get("errors") or ()
            if isinstance(error, Mapping)
        ),
    ):
        text = str(sentence).strip() if sentence else ""
        if text and text not in said:
            said.append(text)
    return (
        f"the snapshot of {TENANT_CODE} ended {status}"
        + (": " + " ".join(said) if said else ".")
        + " Nothing of it is used: clear the cause and run make perf-seed again, which asks"
        " a new one."
    )


def _seed_snapshot(
    services: Services, ctx: builders.BuildContext, known_at: datetime, ledger: Ledger | None
) -> UUID:
    """The stored snapshot of step 5 as of ``known_at`` (after the month-23 lock): a
    ``STORED_BACKUP`` — the product stores it and loads nothing; a ``SANDBOX_SEED`` request names
    a sandbox and loads it in the same job (04 API-R-04) — requested by the controller with a
    fresh second factor (``request_snapshot`` enforces it; she verifies again first when hers is
    stale) and exported by the request's own job, run in place as a worker runs it
    (``jobs.registry.run_job``), so that no job of the request is left queued. A snapshot that
    is not ``SUCCEEDED`` when its job returns raises ``SeedStopped``: with the job's own sentence
    when the job ended — the retention refusal of PRD ERR-77 among them — and, when the job did
    not run here, with that (``snapshot_stopped``). A request an earlier run left unfinished is
    not taken up: the ledger reads a succeeded snapshot, and without one a new request is made."""
    from erev_api.db.tables import job
    from erev_api.domain.platform import snapshot_job, snapshots
    from erev_api.jobs.registry import run_job

    if ledger is not None and ledger.seed_snapshot is not None:
        return ledger.seed_snapshot
    # Imported for its registration: ``run_job`` dispatches the request's job to this handler.
    assert callable(snapshot_job.tenant_snapshot_export)
    controller = volume.PERF_CAST.controller
    ctx.step_up(controller)
    with ctx.command(controller) as uow:
        row, deferred = snapshots.request_snapshot(uow, known_at=known_at, purpose=SNAPSHOT_PURPOSE)
        snapshot_id = UUID(str(row["id"]))
    run_job(deferred.id, ctx.tenant_id, attempt=1, runtime=services.runtime)
    with ctx.read() as session:
        status = _text(
            session.execute(
                select(tenant_snapshot.c.status).where(tenant_snapshot.c.id == snapshot_id)
            ).scalar_one()
        )
        state, problem = session.execute(
            select(job.c.state, job.c.problem).where(job.c.id == deferred.id)
        ).one()
    if status != SNAPSHOT_SUCCEEDED:
        raise SeedStopped(snapshot_stopped(status, problem, job_state=_text(state)))
    return snapshot_id
