"""Golden parity scenario (docs/dev-guide.md §9.6 DG-PAR-04; §9.3 DG-TST-13, DG-TST-16;
BUILD_SPEC GPA-1).

``build`` provisions tenant ``legacy-parity-test`` in the session's test database with real commits
(the ``committed_db`` semantics of DG-TST-13), with two personas: ``ak-preparer`` (Revenue
Accountant, SSP Analyst) and ``ak-approver`` (Revenue Reviewer, SSP Approver, Controller, Tenant
Admin; enrolled in MFA). The application ``FrozenClock`` starts at 2026-01-01T00:00:00Z. Before step
01 the builder does three things:

1. The ``LEGACY_PARITY`` preset version of the TENANT accounting policy set is created
   (``POST /policies/presets/legacy-parity``, DG-KRN-REG-05), dated, tested and submitted by
   ak-preparer, then approved, and so published, by ak-approver. It is authored before any legal
   entity exists, so it is dated as a migrating tenant dates it — at the first day of the legacy
   calendar, 2023-01-01T00:00:00Z (PRD ERR-75 rev 1.178; 04 §16.5; item PINP-PERIOD-VALUE-1): a
   period takes the value in force at its own end (05 RCP-15), so every legacy period takes the
   preset. Dated in 2026, as before that item, the legacy periods computed under the framework
   defaults and nine parity cases moved (58.8462 to 58.85 in "Current Reclass to UAR").
2. The reference data of ``support.legacy_replay.legacy_reference`` is created: calendar FY2023 and
   FY2024; entities ``Mock Entity 1`` and ``Mock Entity 2`` with FY2023-P01 to FY2023-P12 open; the
   setup accounts; mapping ``LEGACY-MAP-2023-01``; and the seeded parity templates. [J] L5-1-Q-33:
   the import resolves ``Selling Entity`` codes and creates no entity, so the entities are created
   before step 01.
3. Book ``LEGACY`` is enabled, and both entities keep it from FY2023-P01 with the same periods open.

``through(NN)`` replays, in order, each golden step up to NN that has not run, through the legacy v1
import pipeline: upload, validate, dry-run diff, submit, approve and commit
(``support.legacy_replay.committed``). ``support.golden_streams.steps`` gives the template of the
step handler, the ``mode`` and the ``date_input`` upload parameter. Before each step the clock
advances one hour, and both personas sign in again, because the session idle limit is 30 minutes
(SAR-10); ak-approver verifies TOTP at the new time step. After the commit the runner records
``known_at[NN] = SELECT clock_timestamp()``. A step that fails marks the scenario broken, and every
later read fails with the same reason instead of uploading the step again.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from uuid import UUID

from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    calc_trace,
    contract,
    contract_event,
    contract_version,
    obligation_version,
)
from erev_api.enums import BookCode
from erev_api.explain import store
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import select, text
from support import golden_streams
from support.factories import ImportWorld, run_import_job, stamp_test_release
from support.legacy_replay import ENTITIES, LegacyWorld, committed, legacy_reference
from support.parity import netting
from support.parity.values import NodeLookup, ValueSourceError
from support.principals import (
    Actor,
    Member,
    colleague,
    enrolled,
    member,
    refreshed,
    sign_in,
    step_up,
    workspace,
)
from support.reference import approve, assign, get, patch, periods, post, put

__all__ = [
    "CLOCK_START",
    "PRESET_FROM",
    "TENANT_CODE",
    "ParityScenario",
    "ScenarioBrokenError",
    "build",
]

TENANT_CODE: Final = "legacy-parity-test"
CLOCK_START: Final = datetime(2026, 1, 1, tzinfo=UTC)
STEP_ADVANCE: Final = timedelta(hours=1)
PRESET_FROM: Final = datetime(2023, 1, 1, tzinfo=UTC)  # the first day of the legacy calendar
PREPARER: Final = "ak-preparer"
APPROVER: Final = "ak-approver"
PREPARER_ROLES: Final = ("revenue_accountant", "ssp_analyst")
APPROVER_ROLES: Final = ("revenue_reviewer", "ssp_approver", "controller", "tenant_admin")
POLICIES: Final = "/api/v1/policies"
PRESET: Final = f"{POLICIES}/presets/legacy-parity"
JOBS: Final = "/api/v1/jobs"
BOOKS: Final = "/api/v1/books"
FIRST_PERIOD: Final = "FY2023-P01"
OPEN_KEYS: Final = tuple(f"FY2023-P{month:02d}" for month in range(1, 13))
# The periods whose JET-06 reclass the parity world posts (support.parity.netting).
OPEN_KEYS_SET: Final = frozenset(OPEN_KEYS)


class ScenarioBrokenError(RuntimeError):
    """A golden step did not commit, so no later state can be read."""


def _iso(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _previous(step: str) -> str | None:
    number = int(step)
    return None if number <= 1 else f"{number - 1:02d}"


@dataclass(slots=True)
class ParityScenario:
    """The DG-PAR-04 world, the steps committed so far and their ``known_at``."""

    world: LegacyWorld
    clock: FrozenClock
    preparer: Member
    approver: Member
    approver_secret: str
    preset_version_id: str
    known_at: dict[str, datetime] = field(default_factory=dict)
    imports: dict[str, Mapping[str, Any]] = field(default_factory=dict)
    broken: str | None = None

    @property
    def app(self) -> FastAPI:
        return self.world.app

    @property
    def tenant_id(self) -> UUID:
        return self.world.tenant_id

    def _context(self) -> DbContext:
        return DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope="*")

    def _signed_in(self) -> LegacyWorld:
        """Both personas signed in again at the current clock; ak-approver verified by TOTP."""
        app = self.app
        preparer = workspace(app, self.preparer, sign_in(app, self.preparer.email))
        signed = sign_in(app, self.approver.email)
        pending = Actor(
            member=self.approver,
            token=signed.token,
            csrf_token=signed.csrf_token,
            secret=self.approver_secret,
        )
        verified = step_up(app, self.clock, pending)
        approver = workspace(
            app, self.approver, refreshed(app, verified.token), self.approver_secret
        )
        return replace(
            self.world,
            imports=replace(self.world.imports, actor=preparer),
            priya=approver,
            marcus=approver,
        )

    def _clock_timestamp(self) -> datetime:
        with tenant_session(self._context(), read_only=True) as session:
            found = session.execute(text("SELECT clock_timestamp()")).scalar_one()
        assert isinstance(found, datetime)
        return found

    def advance(self) -> LegacyWorld:
        """Advance the clock one hour and sign both personas in again; the signed-in world, which
        becomes the scenario's world (the legacy probes of ``support.parity.probes``, GPA-6)."""
        self.clock.advance(STEP_ADVANCE)
        self.world = self._signed_in()
        return self.world

    def through(self, step: str) -> None:
        """Replay each golden step up to ``step`` that has not run (module docstring)."""
        if self.broken is not None:
            raise ScenarioBrokenError(self.broken)
        for golden in golden_streams.steps(step):
            if golden.number in self.known_at:
                continue
            try:
                self.clock.advance(STEP_ADVANCE)
                world = self._signed_in()
                parameters: dict[str, Any] = {}
                if golden.date_input is not None:
                    parameters["effective_date"] = golden.date_input.isoformat()
                if golden.mode is not None:
                    parameters["mode"] = golden.mode
                self.imports[golden.number] = committed(
                    world,
                    golden.workbook.name,
                    golden.workbook.read_bytes(),
                    golden.template_code,
                    parameters or None,
                )
                # The close run's JET-06 step, which the rc platform does not post (L7-1-Q-6).
                netting.post_netting_reclass(world.place(), OPEN_KEYS_SET)
                self.known_at[golden.number] = self._clock_timestamp()
                self.world = world
            except Exception as error:
                self.broken = f"golden step {golden.number} did not commit: {error}"
                raise ScenarioBrokenError(self.broken) from error

    def first_obligation_version(
        self, contract_name: str, pob: str, steps_through: str
    ) -> tuple[dict[str, Any], NodeLookup]:
        """The obligation version of ``contract_name``, ``pob`` in the first ASC606 contract
        version produced by step ``steps_through``: the lowest ``version_no`` of the contract's
        group whose ``known_at`` lies after ``known_at`` of the previous step and at or before that
        of ``steps_through``; with the lookup of its calc_trace nodes."""
        self.through(steps_through)
        upper = self.known_at[steps_through]
        previous = _previous(steps_through)
        lower = None if previous is None else self.known_at[previous]
        with tenant_session(self._context(), read_only=True) as session:
            found = (
                session.execute(
                    select(contract.c.id, contract.c.combination_group_id).where(
                        contract.c.external_id == contract_name
                    )
                )
                .mappings()
                .one_or_none()
            )
            if found is None:
                raise ValueSourceError(f"{contract_name} does not exist after step {steps_through}")
            where = [
                contract_version.c.combination_group_id == found["combination_group_id"],
                contract_version.c.book_code == BookCode.ASC606.value,
                contract_version.c.known_at <= upper,
            ]
            if lower is not None:
                where.append(contract_version.c.known_at > lower)
            version = (
                session.execute(
                    select(contract_version.c.id, contract_version.c.calc_trace_id)
                    .where(*where)
                    .order_by(contract_version.c.version_no)
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            if version is None:
                raise ValueSourceError(
                    f"step {steps_through} produced no ASC606 version of {contract_name}"
                )
            row = (
                session.execute(
                    select(obligation_version).where(
                        obligation_version.c.contract_version_id == version["id"],
                        obligation_version.c.contract_id == found["id"],
                        obligation_version.c.obligation_key == pob,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ValueSourceError(
                    f"the first version of {contract_name} after step {steps_through} holds no "
                    f"obligation {pob}"
                )
            trace_row = (
                session.execute(
                    select(calc_trace).where(calc_trace.c.id == version["calc_trace_id"])
                )
                .mappings()
                .one()
            )
            trace = store.trace_from_row(trace_row)
        nodes = {node.id: node for node in trace.nodes}
        return dict(row), nodes.get

    def latest_obligation_versions(
        self, contract_name: str, steps_through: str
    ) -> tuple[tuple[dict[str, Any], ...], NodeLookup]:
        """Every obligation version of ``contract_name`` in the latest ASC606 contract version of
        its group known after step ``steps_through``: the highest ``version_no`` whose
        ``known_at`` lies at or before that of ``steps_through`` (kind ``contract_position``,
        DG-PAR-05); with the lookup of its calc_trace nodes."""
        self.through(steps_through)
        upper = self.known_at[steps_through]
        with tenant_session(self._context(), read_only=True) as session:
            found = (
                session.execute(
                    select(contract.c.id, contract.c.combination_group_id).where(
                        contract.c.external_id == contract_name
                    )
                )
                .mappings()
                .one_or_none()
            )
            if found is None:
                raise ValueSourceError(f"{contract_name} does not exist after step {steps_through}")
            version = (
                session.execute(
                    select(contract_version.c.id, contract_version.c.calc_trace_id)
                    .where(
                        contract_version.c.combination_group_id == found["combination_group_id"],
                        contract_version.c.book_code == BookCode.ASC606.value,
                        contract_version.c.known_at <= upper,
                    )
                    .order_by(contract_version.c.version_no.desc())
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            if version is None:
                raise ValueSourceError(
                    f"no ASC606 version of {contract_name} is known after step {steps_through}"
                )
            rows = tuple(
                dict(row)
                for row in session.execute(
                    select(obligation_version)
                    .where(
                        obligation_version.c.contract_version_id == version["id"],
                        obligation_version.c.contract_id == found["id"],
                    )
                    .order_by(obligation_version.c.obligation_key)
                ).mappings()
            )
            if not rows:
                raise ValueSourceError(
                    f"the latest version of {contract_name} after step {steps_through} holds no "
                    "obligation"
                )
            trace_row = (
                session.execute(
                    select(calc_trace).where(calc_trace.c.id == version["calc_trace_id"])
                )
                .mappings()
                .one()
            )
            trace = store.trace_from_row(trace_row)
        nodes = {node.id: node for node in trace.nodes}
        return rows, nodes.get

    def modification_obligation_version(
        self, contract_name: str, pob: str, steps_through: str
    ) -> tuple[dict[str, Any], NodeLookup]:
        """The obligation version of ``contract_name``, ``pob`` in the ASC606 contract version
        created by the modification of step ``steps_through`` (kind ``cumulative_catchup``,
        DG-PAR-05): the one version of the contract's group whose ``known_at`` lies after
        ``known_at`` of the previous step and at or before that of ``steps_through``, and whose
        ``cause_event_ids`` hold a ``CONTRACT_AMENDED`` event of the contract; with the lookup of
        its calc_trace nodes."""
        self.through(steps_through)
        upper = self.known_at[steps_through]
        previous = _previous(steps_through)
        lower = None if previous is None else self.known_at[previous]
        with tenant_session(self._context(), read_only=True) as session:
            found = (
                session.execute(
                    select(contract.c.id, contract.c.combination_group_id).where(
                        contract.c.external_id == contract_name
                    )
                )
                .mappings()
                .one_or_none()
            )
            if found is None:
                raise ValueSourceError(f"{contract_name} does not exist after step {steps_through}")
            amended = set(
                session.execute(
                    select(contract_event.c.id).where(
                        contract_event.c.contract_id == found["id"],
                        contract_event.c.event_type == "CONTRACT_AMENDED",
                    )
                ).scalars()
            )
            where = [
                contract_version.c.combination_group_id == found["combination_group_id"],
                contract_version.c.book_code == BookCode.ASC606.value,
                contract_version.c.known_at <= upper,
            ]
            if lower is not None:
                where.append(contract_version.c.known_at > lower)
            versions = [
                version
                for version in session.execute(
                    select(
                        contract_version.c.id,
                        contract_version.c.calc_trace_id,
                        contract_version.c.cause_event_ids,
                    )
                    .where(*where)
                    .order_by(contract_version.c.version_no)
                ).mappings()
                if amended & set(version["cause_event_ids"])
            ]
            if len(versions) != 1:
                raise ValueSourceError(
                    f"step {steps_through} produced {len(versions)} ASC606 versions of "
                    f"{contract_name} caused by a CONTRACT_AMENDED event, not one"
                )
            (version,) = versions
            row = (
                session.execute(
                    select(obligation_version).where(
                        obligation_version.c.contract_version_id == version["id"],
                        obligation_version.c.contract_id == found["id"],
                        obligation_version.c.obligation_key == pob,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise ValueSourceError(
                    f"the modification version of {contract_name} after step {steps_through} "
                    f"holds no obligation {pob}"
                )
            trace_row = (
                session.execute(
                    select(calc_trace).where(calc_trace.c.id == version["calc_trace_id"])
                )
                .mappings()
                .one()
            )
            trace = store.trace_from_row(trace_row)
        nodes = {node.id: node for node in trace.nodes}
        return dict(row), nodes.get


def _publish_preset(world: LegacyWorld) -> str:
    """Step 1 of the module docstring; the id of the PUBLISHED preset version."""
    app, preparer, approver = world.app, world.maya, world.marcus
    created = post(app, PRESET, preparer, {"scope": "TENANT"})
    assert created.status_code == 201, created.text
    version_id = str(created.json()["id"])
    dated = patch(
        app,
        f"{POLICIES}/{version_id}",
        preparer,
        {"effective_from": _iso(PRESET_FROM)},
        if_match=created.headers["ETag"],
    )
    assert dated.status_code == 200, dated.text
    requested = post(app, f"{POLICIES}/{version_id}/test", preparer, {})
    assert requested.status_code == 202, requested.text
    job_id = str(requested.json()["id"])
    run_import_job(world.imports, UUID(job_id))
    tested = get(app, f"{JOBS}/{job_id}", preparer)
    assert (tested.status_code, tested.json()["state"]) == (200, "SUCCEEDED"), tested.text
    submitted = post(
        app, f"{POLICIES}/{version_id}/submit", preparer, {"comment": "Legacy parity (DG-PAR-04)"}
    )
    assert submitted.status_code == 200, submitted.text
    decided = approve(app, str(submitted.json()["approval_request_id"]), approver)
    assert decided.status_code == 200, decided.text
    current = get(app, f"{POLICIES}/{version_id}", preparer).json()
    assert (current["status"], current["preset_code"]) == ("PUBLISHED", "LEGACY_PARITY"), current
    return version_id


def _keep_legacy_book(world: LegacyWorld, entity_ids: Mapping[str, UUID]) -> None:
    """Step 3 of the module docstring."""
    app, preparer, approver = world.app, world.maya, world.marcus
    listed = get(app, BOOKS, approver)
    assert listed.status_code == 200, listed.text
    (legacy,) = [item for item in listed.json()["items"] if item["code"] == BookCode.LEGACY.value]
    enabled = patch(
        app,
        f"{BOOKS}/{BookCode.LEGACY.value}",
        approver,
        {"is_enabled": True},
        if_match=f'"r{legacy["row_version"]}"',
    )
    assert enabled.status_code == 200, enabled.text
    for code in ENTITIES:
        kept = put(
            app,
            f"/api/v1/entities/{entity_ids[code]}/books/{BookCode.LEGACY.value}",
            approver,
            {"is_enabled": True, "first_period_key": FIRST_PERIOD},
        )
        assert kept.status_code == 200, kept.text
        states = {
            item["period"]["period_key"]: item
            for item in periods(app, preparer, entity=code, book=BookCode.LEGACY.value)
        }
        for key in OPEN_KEYS:
            state = states[key]
            if state["state"] == "open":
                continue
            opened = post(
                app,
                f"/api/v1/periods/{state['id']}/open",
                preparer,
                {"comment": "Open for the legacy parity replay"},
                if_match=f'"r{state["row_version"]}"',
            )
            assert opened.status_code == 200, opened.text


def build(
    settings: Settings, keyring: KeyRing, *, tenant_code: str = TENANT_CODE
) -> ParityScenario:
    """The DG-PAR-04 world before step 01 (module docstring); a legacy probe passes its own
    ``tenant_code`` (DG-PAR-06)."""
    clock = FrozenClock(CLOCK_START)
    app = create_app(settings, clock=clock)
    files = LocalFileStore(settings.file_root)
    preparer_member = member(keyring, clock, code=tenant_code, name=PREPARER)
    for code in PREPARER_ROLES:
        assign(preparer_member, code)
    preparer = workspace(app, preparer_member, sign_in(app, preparer_member.email))
    approver_member = colleague(preparer_member.tenant_id, APPROVER)
    for code in APPROVER_ROLES:
        assign(approver_member, code)
    approver = enrolled(app, clock, approver_member)
    assert approver.secret is not None
    world = LegacyWorld(
        imports=ImportWorld(
            app=app,
            actor=preparer,
            runtime=JobRuntime(clock=clock, keyring=keyring, files=files),
            clock=clock,
        ),
        priya=approver,
        marcus=approver,
        entity_ids={},
    )
    version_id = _publish_preset(world)
    entity_ids = legacy_reference(app, preparer, approver)
    _keep_legacy_book(world, entity_ids)
    stamp_test_release()
    return ParityScenario(
        world=replace(world, entity_ids=entity_ids),
        clock=clock,
        preparer=preparer_member,
        approver=approver_member,
        approver_secret=approver.secret,
        preset_version_id=version_id,
    )
