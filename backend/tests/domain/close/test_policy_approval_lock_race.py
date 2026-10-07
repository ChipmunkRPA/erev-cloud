"""Policy approval and a real period lock must serialize before either publishes its result."""

from __future__ import annotations

import dataclasses
import threading
from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from erev_api.approvals import subjects
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import audit_event, combination_group, policy_override
from erev_api.domain.close import commands as close_commands
from erev_api.enums import ApprovalSubjectType
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.uow import UnitOfWork
from fastapi import FastAPI
from sqlalchemy import func, select
from support import close_run_worlds, worlds
from support import close_runs as runs
from support.close_world import actor_with_role
from support.db import TestDatabase
from support.interleave import await_lock_wait, backend_pid, observing_checkouts
from support.reference import PERIODS, approve, get, post, slug

AUGUST = "FY2026-P08"
ENTITY = worlds.AVM_US
KIND = ApprovalSubjectType.POLICY_OVERRIDE


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def _pending(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[worlds.ReportWorld, str, UUID, str]:
    world = close_run_worlds.august_in_soft_close(app, keyring, clock, files)
    world = worlds.on_record_clock(world, clock)
    run = runs.closed(world, monkeypatch, entity_code=ENTITY, period_key=AUGUST)
    assert run["status"] == "SUCCEEDED", run
    world = close_run_worlds.journal_and_reconciliations(world, clock, run)
    contract_id = next(iter(world.contracts.values())).contract["id"]
    created = post(
        app,
        "/api/v1/policy-overrides",
        world.maya,
        {
            "contract_id": str(contract_id),
            "policy_key": "balance.right_to_consideration",
            "obligation_key": "O1",
            "value": "UNCONDITIONAL",
            "rationale": "Order form reviewed",
        },
    )
    assert created.status_code == 201, created.text
    identifier = UUID(created.json()["id"])
    sent = post(app, f"/api/v1/policy-overrides/{identifier}/submit", world.maya, {})
    assert sent.status_code == 200, sent.text
    # Pending approvals normally block a lock. Exercise the supported waiver path so
    # that gate does not conceal the concurrent policy-change race.
    state = worlds.period_state(world, ENTITY, AUGUST)
    cockpit = get(app, f"{PERIODS}/{state['id']}/cockpit", world.maya)
    assert cockpit.status_code == 200, cockpit.text
    (item,) = [row for row in cockpit.json()["checklist"] if row["code"] == "APPROVALS_CLEARED"]
    assert item["result"]["count"] == 1
    state = worlds.period_state(world, ENTITY, AUGUST)
    waiver = post(
        app,
        f"{PERIODS}/{state['id']}/checklist/{item['id']}/waive",
        world.maya,
        {"reason": "Policy decision will be processed after this close"},
        if_match=f'"r{state["row_version"]}"',
    )
    assert waiver.status_code == 200, waiver.text
    waived = approve(app, waiver.json()["approval_request_id"], world.marcus)
    assert waived.status_code == 200, waived.text
    requested = close_run_worlds.request_lock(world)
    assert requested.status_code == 200, requested.text
    return (
        world,
        requested.json()["approval_request_id"],
        identifier,
        sent.json()["approval_request_id"],
    )


def test_lock_waits_for_policy_approval_then_refuses_the_dirty_group(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world, lock_request, identifier, request = _pending(app, keyring, clock, files, monkeypatch)
    cora = actor_with_role(app, clock, world.tenant_id, "controller", name="cora")
    outcome: dict[str, Any] = {}
    observed: dict[str, Any] = {}

    def decide() -> None:
        try:
            outcome["response"] = approve(app, lock_request, cora)
        except Exception as error:  # noqa: BLE001 - propagated to the assertion below
            outcome["error"] = error

    deciding = threading.Thread(target=decide, name="policy-period-lock")
    spec = subjects.SUBJECTS[KIND]

    def approved_then_lock(uow: UnitOfWork, subject_id: UUID, request_id: UUID) -> None:
        spec.on_approved(uow, subject_id, request_id)
        with observing_checkouts() as backends:
            deciding.start()
            _, observed["statement"] = await_lock_wait(
                uow.session,
                holder_pid=backend_pid(uow.session),
                backends=backends,
                timeout=8.0,
                expect="period_state",
            )
        observed["waiting"] = deciding.is_alive() and not outcome

    monkeypatch.setitem(
        subjects.SUBJECTS, KIND, dataclasses.replace(spec, on_approved=approved_then_lock)
    )
    try:
        result = approve(app, request, world.marcus)
    finally:
        if deciding.ident is not None:
            deciding.join(timeout=30)
    assert result.status_code == 200, result.text
    assert not deciding.is_alive() and "error" not in outcome, outcome
    assert observed["waiting"] and "for update" in observed["statement"].lower()
    refused = outcome["response"]
    assert (refused.status_code, slug(refused)) == (409, "close-gates-failed"), refused.text
    assert "NO_DIRTY_GROUPS" in [item["rule_id"] for item in refused.json()["errors"]]
    assert worlds.period_state(world, ENTITY, AUGUST)["state"] == "closing"
    assert (
        str(
            world.place.scalar(
                select(policy_override.c.status).where(policy_override.c.id == identifier)
            )
        )
        == "APPROVED"
    )


def test_policy_approval_overtaken_by_a_lock_rolls_back_and_can_be_retried(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world, lock_request, identifier, request = _pending(app, keyring, clock, files, monkeypatch)
    cora = actor_with_role(app, clock, world.tenant_id, "controller", name="cora")
    spec = subjects.SUBJECTS[KIND]
    observed: dict[str, Any] = {}
    # Put the application clock ahead of the server so the later decision's cutoff is
    # unambiguously later than the policy approval transaction's record cutoff.
    clock.set(world.place.scalar(select(func.clock_timestamp())) + timedelta(seconds=5))

    def lock_then_approve(uow: UnitOfWork, subject_id: UUID, request_id: UUID) -> None:
        clock.advance(timedelta(seconds=30))
        observed["lock"] = approve(app, lock_request, cora)
        spec.on_approved(uow, subject_id, request_id)

    monkeypatch.setitem(
        subjects.SUBJECTS, KIND, dataclasses.replace(spec, on_approved=lock_then_approve)
    )
    refused = approve(app, request, world.marcus)
    assert observed["lock"].status_code == 200, observed["lock"].text
    assert refused.status_code == 409, refused.text
    assert slug(refused) == "lock-conflict"
    assert [item["rule_id"] for item in refused.json()["errors"]] == ["PERIOD_STATE_MOVED"]
    assert "Decide again" in refused.json()["detail"]
    assert worlds.period_state(world, ENTITY, AUGUST)["state"] == "closed"
    assert (
        str(
            world.place.scalar(
                select(policy_override.c.status).where(policy_override.c.id == identifier)
            )
        )
        == "SUBMITTED"
    )
    assert (
        world.place.scalar(
            select(func.count())
            .select_from(audit_event)
            .where(
                audit_event.c.object_id == identifier,
                audit_event.c.action == "policy_override.approve",
            )
        )
        == 0
    )
    assert all(
        row["dirty_since"] is None
        for row in world.place.rows(select(combination_group.c.dirty_since))
    )
    monkeypatch.setitem(subjects.SUBJECTS, KIND, spec)
    clock.advance(timedelta(seconds=1))
    retried = approve(app, request, world.marcus)
    assert retried.status_code == 200, retried.text
    assert (
        str(
            world.place.scalar(
                select(policy_override.c.status).where(policy_override.c.id == identifier)
            )
        )
        == "APPROVED"
    )


def test_policy_approval_waits_for_an_earlier_lock_and_commits_after_it(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world, lock_request, identifier, request = _pending(app, keyring, clock, files, monkeypatch)
    cora = actor_with_role(app, clock, world.tenant_id, "controller", name="cora")
    outcome: dict[str, Any] = {}
    observed: dict[str, Any] = {}

    def approve_policy() -> None:
        try:
            outcome["response"] = approve(app, request, world.marcus)
        except Exception as error:  # noqa: BLE001 - propagated to the assertion below
            outcome["error"] = error

    approving = threading.Thread(target=approve_policy, name="policy-after-period-lock")
    freeze = close_commands.snapshots.freeze_datasets

    def freeze_then_approve(uow: UnitOfWork, *args: Any, **kwargs: Any) -> Any:
        result = freeze(uow, *args, **kwargs)
        if approving.ident is None:
            with observing_checkouts() as backends:
                approving.start()
                _, observed["statement"] = await_lock_wait(
                    uow.session,
                    holder_pid=backend_pid(uow.session),
                    backends=backends,
                    timeout=8.0,
                    expect="period_state",
                )
            observed["waiting"] = approving.is_alive() and not outcome
        return result

    monkeypatch.setattr(close_commands.snapshots, "freeze_datasets", freeze_then_approve)
    try:
        locked = approve(app, lock_request, cora)
    finally:
        if approving.ident is not None:
            approving.join(timeout=30)
    assert locked.status_code == 200, locked.text
    assert not approving.is_alive() and "error" not in outcome, outcome
    assert observed["waiting"] and "for share" in observed["statement"].lower()
    approved = outcome["response"]
    assert approved.status_code == 200, approved.text
    assert worlds.period_state(world, ENTITY, AUGUST)["state"] == "closed"
    assert (
        str(
            world.place.scalar(
                select(policy_override.c.status).where(policy_override.c.id == identifier)
            )
        )
        == "APPROVED"
    )
    assert any(
        row["dirty_since"] is not None
        for row in world.place.rows(select(combination_group.c.dirty_since))
    )
