"""POS-CHK-117 ``balance_aging`` — the builder's database acceptance test over the ORIGINAL key
(record §42; ruling Q-2; RPS-12 / CTR-14). DB-bound: written for the lane's ``erev_rv_l17_test``
and recorded **not run — databases not provisioned** by this lane (the database is Ray-side); it
runs in an admitted database stage (the integrated batch's ``ci`` stage collects this directory).

Ruling Q-2 accepts the T-SL-04 subledger as the builder's interim source and keeps the builder out
of ``framework.BUILDERS`` until its database tests have passed in an admitted run. This is that
test: POS-CHK-117's world, contracts and timeline run through the real adapter under the four
stand-in personas (ACT-1 / ACT-2 on every call), the checkpoint's ``known_at`` is the ledger's
server stamp of item 7 (READ-1), the *unregistered* ``balance_aging.build`` is called directly with
the parameters ``framework.report_params`` would derive from the key's report block, and the four
original cells are compared through ``report_cells.compare_block`` — the key's own oracle, loaded
by hash, never narrowed or substituted. Registration itself is a separate, later commit.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import api_client, contract_version
from erev_api.domain.reports import catalogue, framework, tie_outs
from erev_api.domain.reports.builders import balance_aging
from erev_api.domain.reports.catalogue import HISTORICAL_BASIS, KNOWN_AT_BASIS_KEY, RECORD_BASIS
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import FastAPI
from sqlalchemy import Select, insert, select
from support.answer_keys import report_cells
from support.answer_keys.db_personas import PERSONA_ROLES, principal_map
from support.answer_keys.ledger_resolver import LedgerResolver
from support.answer_keys.loader import LoadedKey
from support.answer_keys.platform_plan import (
    APPROVER,
    INTEGRATION,
    INTEGRATION_SCOPES,
    PLATFORM_KEY_IDS,
    PREPARER,
    SSP_ANALYST,
    SSP_APPROVER,
    load_platform_key,
    plan,
)
from support.answer_keys.workspace_adapter import WorkspaceAdapter
from support.db import TestDatabase
from support.factories import stamp_test_release, workspace
from support.principals import colleague, enrolled, member
from support.reference import assign
from support.rows import api_client_values

POS_117 = PLATFORM_KEY_IDS[4]
# The runner's own phases (marker, provisioning, persona creation) and the checkpoint reads are
# not run here: the fixture tenant and the stand-in members take their place.
STAND_IN_PHASES = frozenset({"RUNNER", "PROVISION", "PERSONAS", "CHECKPOINT"})


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


class _SelectorObserver:
    """Forwarding observer (Codex 1952) over the two selectors ``balance_aging.build`` uses through
    ``tie_outs``: records each ``version_cutoff`` call's arguments and result and each
    ``latest_versions`` call's cutoff and statement, then forwards to the real function."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.cutoff_calls: list[tuple[datetime, bool]] = []
        self.cutoffs: list[datetime] = []
        self.selections: list[tuple[datetime, Select[Any]]] = []
        real_cutoff, real_latest = tie_outs.version_cutoff, tie_outs.latest_versions

        def cutoff(session: Any, known_at: datetime, *, historical: bool = False) -> datetime:
            self.cutoff_calls.append((known_at, historical))
            result = real_cutoff(session, known_at, historical=historical)
            self.cutoffs.append(result)
            return result

        def latest(session: Any, *, book_code: str, cutoff: datetime) -> Select[Any]:
            statement = real_latest(session, book_code=book_code, cutoff=cutoff)
            self.selections.append((cutoff, statement))
            return statement

        monkeypatch.setattr(tie_outs, "version_cutoff", cutoff)
        monkeypatch.setattr(tie_outs, "latest_versions", latest)

    def reset(self) -> None:
        self.cutoff_calls.clear()
        self.cutoffs.clear()
        self.selections.clear()


def _at_plan_setup(clock: FrozenClock, loaded: LoadedKey) -> None:
    """D-98 138-A4 (POS117-STANDIN-CLOCK-1): the stand-in fixture filters out PROVISION — the only
    step carrying ``assembler.setup_at`` — so the tenant, personas and WORLD steps would otherwise
    run on the default 12 Sep clock, and the dated ``create_policy`` (the first period start, a
    period-pinned value) would be refused as already past. The stand-in world therefore starts at
    the plan's setup clock BEFORE tenant / persona / WORLD setup; the planned item clocks and the
    server checkpoint cutoffs are unchanged."""
    provision = next(step for step in plan(loaded).steps if step.phase == "PROVISION")
    assert provision.clock_at is not None
    clock.set(datetime.strptime(provision.clock_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC))


def test_pos_117_balance_aging_cells_from_the_unregistered_builder(
    app: FastAPI,
    keyring: KeyRing,
    clock: FrozenClock,
    app_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = load_platform_key(POS_117)
    _at_plan_setup(clock, loaded)  # D-98 138-A4: the stand-in world starts at the plan's setup_at
    stamp_test_release()  # the release a computation names (CTL-032), as every world stamps it
    maya = member(keyring, clock)
    for code in PERSONA_ROLES[PREPARER]:
        assign(maya, code)
    stand_ins = {}
    for persona, name in ((APPROVER, "marcus"), (SSP_ANALYST, "sasha"), (SSP_APPROVER, "priya")):
        someone = colleague(maya.tenant_id, name)
        for code in PERSONA_ROLES[persona]:
            assign(someone, code)
        stand_ins[persona] = someone
    marcus = stand_ins[APPROVER]
    author = enrolled(app, clock, marcus)
    place = workspace(app, clock, keyring, LocalFileStore(app_settings.file_root), author)
    # BUILD_SPEC CTR-6: the key's events are an integrated source's and are sent by the world's API
    # client (``ak-integration``). Its PERSONAS step is not run here, so a row stands in for it,
    # as the imports tests build their client.
    client = api_client_values(maya.tenant_id, name=INTEGRATION, scopes=list(INTEGRATION_SCOPES))
    with tenant_session(
        DbContext(tenant_id=maya.tenant_id, user_id=None, entity_scope="*")
    ) as session:
        session.execute(insert(api_client).values(**client))
    # ACT-1: every persona the plan names, proven by name (marcus is also the operator stand-in).
    principals = principal_map(
        maya,
        marcus,
        ssp_analyst=stand_ins[SSP_ANALYST],
        ssp_approver=stand_ins[SSP_APPROVER],
        integration=UUID(str(client["id"])),
        verified_at=clock.now(),  # the verified session approvals require (engine.py mfa-required)
    )
    adapter = WorkspaceAdapter.for_database(loaded, place, principals)
    steps = [step for step in plan(loaded).steps if step.phase not in STAND_IN_PHASES]
    # 90 WORLD-onward steps: the 70 of PLAT-G4-1b plus the DB-03 lifecycle steps (a case and a test
    # run per template, the mapping lint run, the policy test), the products' template binding
    # after publication (batch #5 returned items; record §4.20), the study of the SSP version —
    # its upload and its link, without which the submission is refused (REQ-SSP-008) — and what
    # the activation checklist asks of a three-line contract whose key states no Step 1 (04 table
    # 15.4-I): a distinct review per obligation with its approval (six steps) and the Step 1
    # record, its submission, its approval and the assessment event (four); the approval of the
    # activation is the activation, so the separate activate step is gone (one fewer). And,
    # since dev-guide rev 1.246 (item AK-CLOSE-RUN-STEP-1), the close run of March that the
    # checkpoint's subledger block expects, right after item 7 (one more): the checkpoint's
    # ``known_at`` below is the stamp taken after it.
    assert len(steps) == 91 and all(step.gap is None for step in steps)
    assert [(step.phase, step.subject, step.seq) for step in steps if step.phase == "CLOSE"] == [
        ("CLOSE", "close run US01 ASC606 FY2026-P03", 7)
    ]
    for step in steps:
        adapter.run(step)  # the application clock per item; ACT-1 / ACT-2; RES-2 approvals

    (checkpoint,) = loaded.key.checkpoints
    (block,) = checkpoint.reports or ()
    assert block.report_code == balance_aging.CODE and len(block.cells) == 4
    known_at = adapter.known_at_of(checkpoint.after_seq, f"checkpoint {checkpoint.name}")
    resolver = LedgerResolver(adapter.ledger, adapter.reads)
    entity_codes = [str(code) for code in block.parameters["entity_codes"]]  # type: ignore[union-attr]
    definition = catalogue.DEFINITIONS_BY_CODE[balance_aging.CODE]
    # The parameters as ``_resolve`` would store them for a run created with this block's
    # ``known_at`` (the caller supplied the cutoff → basis ``historical``), read back through the
    # real ``framework.report_params`` — the same path the job, a rerun and the explain route use.
    stored_run = {
        "report_code": balance_aging.CODE,
        "report_version": definition.version,
        "parameters": {
            **dict(block.parameters),
            framework.KNOWN_AT: framework.utc_text(known_at),
            KNOWN_AT_BASIS_KEY: HISTORICAL_BASIS,
        },
        "entity_ids": [str(resolver.entity_id(code)) for code in entity_codes],
        "known_at": known_at,
        "book_code": str(block.parameters["book"]),
        "as_of_date": None,
        "period_lock_id": None,
        "output_format": "json",
    }
    params = framework.report_params(stored_run)
    assert params.historical is True and params.known_at == known_at
    # Codex 1952: a forwarding observer records the REAL selector arguments and results the
    # builder uses (``tie_outs.version_cutoff`` → ``tie_outs.latest_versions``), so a builder-only
    # loss of ``historical=params.historical`` cannot pass on equal March money.
    observed = _SelectorObserver(monkeypatch)
    with place.uow(principals[APPROVER]) as uow:  # the report persona (report.run), never a default
        data = balance_aging.build(uow, params)
        assert observed.cutoff_calls == [(known_at, True)]  # the strict cutoff, once
        assert observed.cutoffs == [known_at]
        (built_selection,) = observed.selections
        assert built_selection[0] == known_at  # latest_versions received the strict cutoff
        # F-RPS-CUTOFF-R1 (record §43) — version identity, not only money. The April items
        # (seqs 8 / 9) committed versions after the March checkpoint, so the two bases differ:
        # READ-1 selects the latest version recorded by the checkpoint stamp; L6-3-Q-19's record
        # basis widens to the job's transaction time and selects a later version.
        session = uow.session
        versions = session.execute(
            select(
                contract_version.c.id, contract_version.c.version_no, contract_version.c.known_at
            )
            .where(contract_version.c.book_code == "ASC606")
            .order_by(contract_version.c.version_no)
        ).all()
        as_of_checkpoint = [row for row in versions if row.known_at <= known_at]
        later = [row for row in versions if row.known_at > known_at]
        assert as_of_checkpoint and later, "the witness needs versions on both sides of the stamp"
        strict = tie_outs.version_cutoff(session, known_at, historical=True)
        assert strict == known_at
        widened = tie_outs.version_cutoff(session, known_at)
        assert widened > known_at
        selected_strict = set(
            session.execute(
                tie_outs.latest_versions(session, book_code="ASC606", cutoff=strict)
            ).scalars()
        )
        selected_widened = set(
            session.execute(
                tie_outs.latest_versions(session, book_code="ASC606", cutoff=widened)
            ).scalars()
        )
        assert selected_strict == {as_of_checkpoint[-1].id}  # READ-1 identity
        assert selected_widened == {versions[-1].id} and selected_widened != selected_strict
        # The builder's OWN selection (the observed statement) is the strict set, not the widened.
        built_selected = set(session.execute(built_selection[1]).scalars())
        assert built_selected == selected_strict
        # Control: the record basis yields the same March money — amounts alone prove nothing
        # about version provenance; the identity assertions above do.
        observed.reset()
        recorded = framework.report_params(
            {
                **stored_run,
                "parameters": {**stored_run["parameters"], KNOWN_AT_BASIS_KEY: RECORD_BASIS},
            }
        )
        assert recorded.historical is False
        control = balance_aging.build(uow, recorded)
        assert observed.cutoff_calls == [(known_at, False)] and observed.cutoffs == [widened]
        (control_selection,) = observed.selections
        assert set(session.execute(control_selection[1]).scalars()) == selected_widened
    rows = [dict(row) for row in data.rows]
    assert report_cells.compare_block(loaded.key, block, rows) == []
    (tie,) = data.tie_out_results
    assert tie["code"] == balance_aging.TO_AGING_EQ_BALANCES and tie["result"] == tie_outs.PASS
    control_rows = [dict(row) for row in control.rows]
    assert report_cells.compare_block(loaded.key, block, control_rows) == []


def test_an_unstamped_persona_principal_is_refused_by_the_approval_engine(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    """The control witnessed, not bypassed (batch #6; BR-PLT-06): a persona principal built without
    the verified-session stamp is refused by name by ``approvals/engine.decide`` (``mfa-required``)
    at the first approval step; the stamped principals of the witness above pass it."""
    loaded = load_platform_key(POS_117)
    _at_plan_setup(clock, loaded)  # D-98 138-A4: same plan-derived setup clock as the witness above
    maya = member(keyring, clock)
    for code in PERSONA_ROLES[PREPARER]:
        assign(maya, code)
    marcus = colleague(maya.tenant_id, "marcus")
    for code in PERSONA_ROLES[APPROVER]:
        assign(marcus, code)
    author = enrolled(app, clock, marcus)
    place = workspace(app, clock, keyring, LocalFileStore(app_settings.file_root), author)
    unstamped = {
        persona: replace(principal, mfa_verified_at=None)
        for persona, principal in principal_map(maya, marcus, verified_at=clock.now()).items()
    }
    adapter = WorkspaceAdapter.for_database(loaded, place, unstamped)
    steps = [step for step in plan(loaded).steps if step.phase not in STAND_IN_PHASES]
    with pytest.raises(Problem, match="mfa-required"):
        for step in steps:
            adapter.run(step)
