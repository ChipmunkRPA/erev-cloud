"""CLO-10 journal line validation on a database (03 REQ-JE-022; BUILD_SPEC CLO-10 acceptance; 04
§15.2 ``unmapped-account-role`` / ``missing-fx-rate``, §15.4 ``ACCOUNT_MAPPING_MISSING`` /
``FX_RATE_MISSING``; CTL-020; F-CLO record §25.18).

DB-bound (``CloseWorld``): NOT RUN on the authoring worktree (databases not provisioned); measured
by the integrated batch on merged main. Each scenario seeds genuine sealed activity of AVM-US in
September (``close_world.sealed_activity``), requests a journal run through the API and runs the
``JOURNAL_RUN_CALCULATE`` job as the worker does: the generation fails by name, one exception item
of source ``JOURNAL`` names contract, obligation and role, no ``journal_run`` row or line is
committed, and the sealed lines are still there (nothing dropped). Every posting is balanced with a
genuine counterpart line on a distinct account (0040's seal; Codex 1317 CLO-FIXTURE-SEAL-1), so
exactly one line of each posting fails.

TC-JE-12 (legacy 06 §7.3): "Contract 2's Unbilled A/R account empty" is staged as the account the
unbilled line names being inactive — a deactivated account is what an empty account column
resolves to in eRev, where every sealed line carries an account id (T-SL-04 ``gl_account_id`` is
not null): the validation refuses it as an unmapped role, never a dropped line.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    exception_item,
    fx_rate,
    fx_rate_set,
    fx_rate_set_version,
    gl_account,
    journal_run,
    subledger_line,
)
from erev_api.domain.journals import validation
from erev_api.enums import ConfigStatus
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import insert, select, update
from support.close_world import (
    CloseWorld,
    close_world,
    published_version,
    requested_journal_run,
    run_journal_job,
    sealed_activity,
    system_session,
)
from support.db import TestDatabase
from support.rows import (
    fx_rate_set_values,
    fx_rate_set_version_values,
    fx_rate_values,
    gl_account_values,
)

PERIOD_END: Final = date(2026, 9, 30)
PROBLEM_BASE: Final = "https://erev.dev/problems/"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> CloseWorld:
    return close_world(app, keyring, clock, files)


def _account(world: CloseWorld, code: str, **extra: Any) -> dict[str, Any]:
    with system_session(world) as session:
        account = gl_account_values(world.tenant_id, code=code)
        account.update(extra)
        session.execute(insert(gl_account).values(**account))
    return account


def _items(world: CloseWorld, code: str) -> list[dict[str, Any]]:
    with system_session(world) as session:
        return [
            dict(row)
            for row in session.execute(
                select(exception_item).where(exception_item.c.code == code)
            ).mappings()
        ]


def _runs(world: CloseWorld) -> int:
    with system_session(world) as session:
        return len(
            session.execute(
                select(journal_run.c.id).where(
                    journal_run.c.entity_id == world.entity_id,
                    journal_run.c.period_id == world.period_id,
                )
            ).all()
        )


def _line_exists(world: CloseWorld, line_id: UUID) -> bool:
    with system_session(world) as session:
        return (
            session.execute(
                select(subledger_line.c.id).where(subledger_line.c.id == line_id)
            ).scalar_one_or_none()
            is not None
        )


def _failed(world: CloseWorld, slug: str, rule_id: str) -> dict[str, Any]:
    job_id, _ = requested_journal_run(world)
    outcome = run_journal_job(world, job_id)
    assert str(outcome["state"]) == "FAILED", outcome
    problem = outcome["problem"]
    assert problem is not None and problem["type"] == PROBLEM_BASE + slug, problem
    assert problem["errors"][0]["rule_id"] == rule_id, problem
    return dict(problem)


def test_tc_je_12_null_unbilled_account(world: CloseWorld) -> None:
    """The unbilled A/R line of Contract 2 / POB #1 names an account that is not active for the
    entity: the job ends FAILED with 422 ``unmapped-account-role``; one ``ACCOUNT_MAPPING_MISSING``
    item (source JOURNAL) names Contract 2, POB #1 and UNBILLED_RECEIVABLE; no run, no drop."""
    unbilled = _account(world, "1201")
    revenue = _account(world, "5001")
    with system_session(world) as session:
        # A balanced posting (1317 CLO-FIXTURE-SEAL-1): the unbilled debit and its REVENUE credit on
        # the active 5001 — only the 1201 line fails validation.
        activity = sealed_activity(
            session,
            world,
            account=unbilled,
            period_id=world.period_id,
            period_end_date=PERIOD_END,
            amounts=[Decimal("100.00")],
            account_role="UNBILLED_RECEIVABLE",
            offset_account=revenue,
            offset_columns={"account_role": "REVENUE"},
        )
        session.execute(
            update(gl_account).where(gl_account.c.id == unbilled["id"]).values(is_active=False)
        )
    problem = _failed(world, "unmapped-account-role", validation.ACCOUNT_MAPPING_MISSING)
    assert "UNBILLED_RECEIVABLE" in str(problem["detail"]) and len(problem["errors"]) == 1
    (item,) = _items(world, validation.ACCOUNT_MAPPING_MISSING)
    assert (str(item["source"]), item["contract_id"], item["obligation_id"]) == (
        "JOURNAL",
        activity.contract_id,
        activity.obligation_id,
    )
    for named in ("Contract 2", "POB #1", "UNBILLED_RECEIVABLE"):
        assert named in item["message"], item["message"]
    assert _runs(world) == 0
    assert all(_line_exists(world, line_id) for line_id in activity.line_ids)


@pytest.mark.control("CTL-020")
def test_ctl_020_missing_fx_rate_fails_generation(world: CloseWorld) -> None:
    """The admitted missing-rate boundary (Codex production-20260921-1054 R4): a EUR line of the
    USD entity carries both rate ids — ``ck_subledger_line__fx`` admits it — but the rate it names
    is GBP->USD of an APPROVED version, so no in-force rate from EUR to USD backs the line: 422
    ``missing-fx-rate``, one ``FX_RATE_MISSING`` item (source JOURNAL), nothing committed. The
    id-less shape is refused by the CHECK before any job and is a pure-rule witness only
    (``tests/unit/journals/test_validation_rules.py``), not this control's evidence."""
    revenue = _account(world, "5001")
    unbilled = _account(world, "1201")
    with system_session(world) as session:
        rate_set = fx_rate_set_values(world.tenant_id)
        session.execute(insert(fx_rate_set).values(**rate_set))
        version = fx_rate_set_version_values(world.tenant_id, fx_rate_set_id=rate_set["id"])
        other_pair = fx_rate_values(
            world.tenant_id,
            fx_rate_set_version_id=version["id"],
            base_currency="GBP",
            quote_currency="USD",
            effective_date=PERIOD_END,
        )
        good_pair = fx_rate_values(
            world.tenant_id,
            fx_rate_set_version_id=version["id"],
            base_currency="EUR",
            quote_currency="USD",
            effective_date=PERIOD_END,
        )
        published_version(
            session,
            world,
            fx_rate_set_version,
            version,
            children=[(fx_rate, other_pair), (fx_rate, good_pair)],
            final=ConfigStatus.APPROVED,
        )
        # A balanced EUR posting (1317 CLO-FIXTURE-SEAL-1): the REVENUE credit names the wrong-pair
        # rate (the single invalid line), its UNBILLED_RECEIVABLE counterpart the valid EUR->USD
        # rate of the same APPROVED version.
        activity = sealed_activity(
            session,
            world,
            account=revenue,
            period_id=world.period_id,
            period_end_date=PERIOD_END,
            amounts=[Decimal("-100.00")],
            txn_currency="EUR",
            fx_rate_id=other_pair["id"],
            fx_rate_set_version_id=version["id"],
            offset_account=unbilled,
            offset_columns={
                "account_role": "UNBILLED_RECEIVABLE",
                "fx_rate_id": good_pair["id"],
                "fx_rate_set_version_id": version["id"],
            },
        )
    problem = _failed(world, "missing-fx-rate", validation.FX_RATE_MISSING)
    assert "EUR" in str(problem["detail"]) and "GBP->USD" in str(problem["detail"])
    assert [error["field"] for error in problem["errors"]] == [
        f"lines.{activity.target_line_ids[0]}"
    ]
    (item,) = _items(world, validation.FX_RATE_MISSING)
    assert (str(item["source"]), item["contract_id"]) == ("JOURNAL", activity.contract_id)
    assert _runs(world) == 0
    assert all(_line_exists(world, line_id) for line_id in activity.line_ids)


def test_mandatory_dimension_missing(world: CloseWorld) -> None:
    """The revenue account requires dimension ``department``; a line without it fails generation
    with an item naming contract, obligation, role and the dimension; nothing committed."""
    revenue = _account(world, "5001", required_dimensions=["department"])
    unbilled = _account(world, "1201")
    with system_session(world) as session:
        # A balanced posting (1317 CLO-FIXTURE-SEAL-1): the counterpart on 1201 requires no
        # dimension, so only the 5001 line fails.
        activity = sealed_activity(
            session,
            world,
            account=revenue,
            period_id=world.period_id,
            period_end_date=PERIOD_END,
            amounts=[Decimal("-100.00")],
            dimensions={},
            offset_account=unbilled,
            offset_columns={"account_role": "UNBILLED_RECEIVABLE", "dimensions": {}},
        )
    problem = _failed(world, "unmapped-account-role", validation.DIMENSION_MISSING_CODE)
    assert "department" in str(problem["detail"]) and len(problem["errors"]) == 1
    (item,) = _items(world, validation.DIMENSION_MISSING_CODE)
    assert (item["contract_id"], item["obligation_id"]) == (
        activity.contract_id,
        activity.obligation_id,
    )
    for named in ("Contract 2", "POB #1", "REVENUE", "department"):
        assert named in item["message"], item["message"]
    assert _runs(world) == 0
