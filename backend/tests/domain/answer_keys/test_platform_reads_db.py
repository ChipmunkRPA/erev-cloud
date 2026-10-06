"""DB-bound (record §19): the read side over a real workspace. Written for the lane's
``erev_rv_l17_test`` database and recorded **not run — databases not provisioned** (§9.1); it runs
in an admitted database stage only.

On the K06 factory world (``test_estimates.py``: Maya prepares, Marcus approves) a booked and
activated contract is computed once; the reads rebuild its ASC606 book from the persisted rows
(READ-2), read the period state as of now (READ-5), observe the row digest moving with a write
(READ-4) and read the pending approval pair of a submitted judgement record by its subject
(READ-3).

The write and the submission were a policy override's until register index 308
(POLICY-OVERRIDE-WITHDRAW-1; supervisor ruling R-126 (c)): release 1.0 offers no policy override
and the plan creates none, so the two reads stand on what the plan still sends — a judgement
record of the contract, built by the runner's own request model (``request_models
.judgement_request``). It is the subject READ-3 exists for: the record's own digest is not its
request's (``ledger_resolver.RESULT_MEMBERS``), so the pair is read from the request.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import (
    approval_request,
    contract_version,
    period_state,
    period_state_transition,
)
from erev_api.domain.policies import judgements
from erev_api.enums import ApprovalSubjectType
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.schemas.judgements import JudgementSubmitIn
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from fastapi import FastAPI
from sqlalchemy import func, select
from support.answer_keys.models import Judgement
from support.answer_keys.platform_runner import NotProvisioned
from support.answer_keys.request_models import judgement_request
from support.answer_keys.workspace_adapter import _server_horizon
from support.answer_keys.workspace_reads import PersistedReads, WorkspaceRows
from support.db import TestDatabase
from support.factories import (
    K11_CHART,
    TPL_PROD_UNITS,
    Workspace,
    activated_contract,
    approved_ssp_version,
    booked_contract,
    customer_id,
    product_with_template,
    published_mapping,
    published_template,
    range_entry,
    set_default_template,
    ssp_book,
    stamp_test_release,
    workspace,
    world_calendar,
)
from support.principals import Actor, colleague, enrolled, member
from support.reference import assign, holding, put

PART: Final = "AVM-PART"
PART_CASE: Final = {
    "obligation_key": "POB-01",
    "product_code": PART,
    "quantity": "575",
    "total_price": "57500.00",
}


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


def _world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> tuple[Workspace, Actor, UUID]:
    maya_member = member(keyring, clock)
    assign(maya_member, "revenue_accountant")
    maya = holding(app, maya_member, "ssp_analyst")
    approvers: dict[str, Actor] = {}
    for name, roles in (
        ("priya", ("revenue_reviewer", "ssp_approver")),
        ("marcus", ("controller", "tenant_admin")),
    ):
        someone = colleague(maya_member.tenant_id, name)
        for code in roles:
            assign(someone, code)
        approvers[name] = enrolled(app, clock, someone)
    marcus = approvers["marcus"]
    enabled = put(app, "/api/v1/tenant-currencies", marcus, {"currency_codes": ["USD", "EUR"]})
    assert enabled.status_code == 200, enabled.text
    world_calendar(
        app, maya, entity_code="AVM-DE", functional_currency="EUR", time_zone="Europe/Berlin"
    )
    buyer = customer_id(app, maya, code="C-06", name="Drossel Fahrzeugtechnik GmbH (Demo)")
    part = product_with_template(
        app, maya, code=PART, name="Drive part, per unit", revenue_category="PRODUCT"
    )
    units = published_template(
        app, maya, marcus, code="TPL-PROD-UNITS", outputs=TPL_PROD_UNITS, case_line=PART_CASE
    )
    set_default_template(app, maya, part, units["template_id"])
    # The approved EUR SSP book of test_estimates.py's K06 world (ENGINE_SPEC S05-R-02): without
    # it the activation compute and the estimate-submission dry run fail closed with
    # SSP_KEY_NOT_FOUND (batch ci on main 065e7f65; test_s05_ssp_book_precondition.py).
    book_id = ssp_book(app, maya, code="DE-LIST", currency="EUR")
    approved_ssp_version(
        app,
        maya,
        [approvers["priya"]],
        book_id,
        label="2026",
        effective_from="2026-01-01",
        entries=[range_entry(PART, "90.00", "100.00", "110.00", currency="EUR")],
    )
    published_mapping(app, maya, marcus, chart=K11_CHART)
    stamp_test_release()
    return workspace(app, clock, keyring, files, maya), marcus, buyer


def _body(customer: UUID) -> dict[str, Any]:
    return {
        "external_id": "NS-SO-DE-5002",
        "customer_id": str(customer),
        "contracting_entity_code": "AVM-DE",
        "transaction_currency": "EUR",
        "inception_date": "2026-07-01",
        "lines": [
            {
                "obligation_key": "O1",
                "product_code": PART,
                "quantity": "575",
                "total_price": {"amount": "57500.00", "currency": "EUR"},
            }
        ],
    }


def test_reads_rebuild_the_book_and_read_state_digest_and_approvals(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings
) -> None:
    place, _marcus, buyer = _world(app, keyring, clock, LocalFileStore(app_settings.file_root))
    booked = activated_contract(place, booked_contract(place, _body(buyer), activate=False))
    contract_id = UUID(str(booked.contract["id"]))
    group_id = UUID(str(booked.combination_group["id"]))
    reads = PersistedReads(WorkspaceRows(place))
    # READ-2: the ASC606 book from rows, as of a moment after the computation committed. The
    # cutoff is the DATABASE clock: DB-08 server-timestamps contract events (`recorded_at =
    # now()`) and the version's known_at derives from them (computation.py), so the frozen
    # application clock — 2026-09-12 here — never reaches a row; the runner's own READ-1 stamp
    # is `clock_timestamp()` after the commit (`known_at_of`).
    committed_at = place.scalar(select(func.clock_timestamp()))
    assert committed_at is not None
    # The persisted version's known_at is a server time: after the frozen clock, at or before
    # the server timestamp read after the commit (no margin, no constant).
    versions = WorkspaceRows(place).table_rows(
        contract_version, combination_group_id=group_id, book_code="ASC606"
    )
    assert versions and all(clock.now() < row["known_at"] <= committed_at for row in versions)
    output = reads.output_bundle(
        group_id=group_id,
        # READ2-R2 by identity: the persisted, system-generated group code (`CG-<contract_no>`)
        # from the booking result — never the contract's external id as a group name.
        group_key=str(booked.combination_group["code"]),
        members=("NS-SO-DE-5002",),
        books=("ASC606",),
        known_at=committed_at,
        where="db read",
    )
    (book,) = output.books
    assert book.book_code == "ASC606" and book.contract_version is not None
    assert book.status_in_book == (("NS-SO-DE-5002", "ACTIVE"),)
    keys = {version.subject_key for version in book.obligation_versions}
    assert keys == {obligation_subject_key("NS-SO-DE-5002", "O1")}
    assert "combination_group_id" not in book.contract_version.columns  # fixed columns dropped
    assert isinstance(book.trace.nodes, tuple)  # hash-verified by trace_from_row
    # A booked and activated POINT_IN_TIME / UNITS_DELIVERED contract with no delivery and no
    # billing has no role deltas (S14 derives intents from deltas), so the engine emits no posting
    # intents and `computation.persist` writes no `subledger_posting` (its rule 4: one sealed
    # posting per book WITH intents) — the read side returns exactly that, `()` (batch #6: the
    # witness expected intents here; the positive rebuild path is the platform keys' checkpoint
    # reads, whose timelines deliver and bill).
    assert book.posting_intents == ()
    # READ-1: before the computation there is no version.
    with pytest.raises(Exception, match="no contract version"):
        reads.output_bundle(
            group_id=group_id,
            group_key=str(booked.combination_group["code"]),
            members=("NS-SO-DE-5002",),
            books=("ASC606",),
            known_at=clock.now() - timedelta(days=365),
            where="db read",
        )
    # READ-5: the state as of now equals the row of THAT period — July, which the world opened
    # (its history: created ``future``, then ``future → open``; 04 T-REF-07), not any row of the
    # book: the calendar's later periods are still ``future``.
    july = reads.period_state_id("AVM-DE", "ASC606", "FY2026-P07")
    row_state = place.scalar(select(period_state.c.state).where(period_state.c.id == july))
    assert row_state == "open"
    # READ-5 as amended (dev-guide rev 1.246): a transition is placed by the transaction that
    # wrote it against the server's transaction horizon — its own stamps are the application
    # clock's. At the horizon read now, every transition of July is past: the row's state.
    horizon = _server_horizon(place)
    assert isinstance(horizon, int)
    july_at = ("AVM-DE", "ASC606", "FY2026-P07", committed_at)
    assert reads.period_state(*july_at, horizon) == row_state
    history = sorted(
        WorkspaceRows(place).table_rows(period_state_transition, period_state_id=july),
        key=lambda row: (int(row["created_txid"]), row["created_at"], str(row["id"])),
    )
    assert [(row["from_state"], str(row["to_state"])) for row in history] == [
        (None, "future"),
        ("future", "open"),
    ]
    created, opened = (int(row["created_txid"]) for row in history)
    assert created < opened < horizon  # two transactions of the world's setup
    # A checkpoint stamped before the opening's transaction began reads the state it found;
    # one stamped after it reads ``open``. The rows' stamps would have answered ``open`` to both.
    assert reads.period_state(*july_at, opened) == "future"
    assert reads.period_state(*july_at, opened + 1) == "open"
    assert all(row["created_at"] <= committed_at for row in history)
    with pytest.raises(NotProvisioned, match="kept no transaction horizon"):
        reads.period_state(*july_at)
    # READ-4: the digest moves with a write, and is stable without one. The write is a judgement
    # record of the contract, as the plan creates one for a key's judgement.
    before = reads.fingerprint()
    assert before == reads.fingerprint()
    stated = Judgement(
        handle="J-READ",
        topic="OTHER",
        conclusion="Consideration depends on completing the services.",
        rationale="FASB Example 39 pattern: the right to consideration is conditional.",
    )
    with place.uow() as uow:
        record = judgements.create_judgement(
            uow, body=judgement_request(stated, contract_id, contract_id)
        )
        uow.commit()
    assert reads.fingerprint() != before
    # READ-3: the submitted record's pending request, read by subject. The request's digest is
    # the subject content's — the record with its contract's group and stream head (04 §16.10
    # rev 1.49) — and not the record's own, which is why the runner reads it from the request.
    with place.uow() as uow:
        submitted = judgements.submit_judgement(
            uow, judgement_id=record.id, body=JudgementSubmitIn()
        )
        uow.commit()
    (pair,) = reads.approval_pairs(
        ApprovalSubjectType.JUDGEMENT_RECORD, [record.id], where="db read"
    )
    stored = place.scalar(
        select(approval_request.c.subject_content_sha256).where(approval_request.c.id == pair[0])
    )
    assert pair[1] == stored
    assert pair[0] == submitted.approval_request_id
    assert submitted.content_sha256 is not None and submitted.content_sha256 != pair[1]
