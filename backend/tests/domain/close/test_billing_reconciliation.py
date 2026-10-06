"""CLO-16 billing-to-subledger reconciliation (BUILD_SPEC CLO-16 acceptance; 03 REQ-CLS-015; 04
T-CLS-06 to T-CLS-08, §16.8 API-S-Reconciliation, T-SRC-04, T-SRC-05, DB-10; PRD SM-09, ACT-33,
ACT-34, SoD-7, WLD-K-01, WLD-F-22; SCREENS_B §2.2; control CTL-024; supervisor ruling R-54).

Worlds, each through the product's own commands:

- ``support.reconciliations.ingested_k01``: ``worlds.k01_pellworth`` with its two invoices
  INGESTED — the CSV v2 ``invoices`` template stores INV-US-1001 and INV-US-1044 as
  ``source_invoice`` rows and applies them as ``BILLING_RECORDED`` events (DIN-9) — and the two O2
  progress events appended after.
- ``_fenwright``: AVM-DE (EUR) with a contract carrying K-07's external id ``NS-SO-DE-5003`` and its
  delivered obligation of 100,000.00 on the world's gateway product; K-07's product AVM-FLEET and
  its option O2 belong to ``worlds.k07_fenwright`` (an RPS item) and play no part in a billing
  reconciliation. INV-DE-4390 100,000.00 (2026-08-31; PRD WLD-F-22) is ingested through the same
  template, and its billing event is voided through ``POST /events/{id}/request-void`` and its
  approval: a source invoice is stored with its events or not at all (DIN-9, DIN-13), so a voided
  event is how the product holds a billing-system document without a billing event.
- ``close_world`` for the sign-off rules, and ``worlds.k01_pellworth`` through January for the
  lock: its INV-US-1001 is recorded as an event only, which the January reconciliation itemises as
  unmatched in the subledger.

The generation job is run as the worker runs it (``support.reconciliations``).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    contract,
    contract_event,
    reconciliation,
    reconciliation_item,
    signoff,
    source_invoice,
)
from erev_api.domain.close import commands as close_commands
from erev_api.enums import ContractEventType
from erev_api.events.payloads import BillingRecordedV1, DeliveryRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.money import MoneyIn
from erev_api.schemas.periods import PeriodLockRequestIn
from fastapi import FastAPI
from sqlalchemy import func, insert, select
from support import reconciliations as recon
from support.close_world import (
    JOURNAL_RUN_ID_HEADER,
    JOURNAL_RUNS,
    CloseWorld,
    acknowledge_run,
    actor_with_role,
    close_run_succeeded_for,
    close_world,
    reviewed_reconciliations_for,
)
from support.db import TestDatabase
from support.factories import (
    GATEWAY,
    K11World,
    activated_contract,
    appended,
    booked_contract,
    computed,
    customer_id,
    k11_world,
)
from support.principals import carrying, colleague, enrolled, step_up
from support.reference import PERIODS, approve, assign, get, periods, post, slug
from support.rows import reconciliation_values
from support.worlds import k01_pellworth, resigned, run_now

EVENTS = "/api/v1/events"
K07 = "NS-SO-DE-5003"
# PRD WLD-F-22: INV-DE-4390 100,000.00 (2026-08-31, K-07).
K07_INVOICE = (
    (K07, "INVOICE", "INV-DE-4390", "2026-08-31", "", "false", "", "", "1",
     "O1", GATEWAY, "200", "100000.00", "EUR", "", "", "", "", ""),
)  # fmt: skip
EXPLANATION = "Invoice recorded in the subledger before the billing system issued it."
REOPEN_REASON = "The preparer asked for a new generation."


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def runtime(clock: FrozenClock, keyring: KeyRing, files: LocalFileStore) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=files)


def _usd(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


def _rows(tenant_id: UUID, statement: Any) -> list[dict[str, Any]]:
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return [dict(row) for row in session.execute(statement).mappings()]


def _total(
    amount_subledger: str | None, amount_source: str | None, difference: str, currency: str
) -> dict[str, Any]:
    # a billing row names no account and no contract balance role (04 §16.8, rev 1.253)
    return {
        "account_code": None,
        "account_role": None,
        "account_codes": [],
        "currency": currency,
        "subledger_amount": None if amount_subledger is None else _usd(amount_subledger, currency),
        "source_amount": None if amount_source is None else _usd(amount_source, currency),
        "difference": _usd(difference, currency),
        "not_stated": None,
    }


def test_zero_variance_k01(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, runtime: JobRuntime
) -> None:
    """BUILD_SPEC CLO-16: with INV-US-1001 120,000.00 and INV-US-1044 15,000.00 ingested and
    applied, a ``BILLING_TO_SUBLEDGER`` reconciliation for AVM-US Feb 2026 has ``variance_count`` 0
    and status ``DRAFT``."""
    world = recon.ingested_k01(app, keyring, clock, files, runtime)
    stored = _rows(
        world.tenant_id,
        select(source_invoice.c.invoice_number, source_invoice.c.total_amount).order_by(
            source_invoice.c.invoice_number
        ),
    )
    assert [(row["invoice_number"], row["total_amount"]) for row in stored] == [
        ("INV-US-1001", Decimal("120000.00")),
        ("INV-US-1044", Decimal("15000.00")),
    ]

    february = recon.generated(
        app, world.maya, runtime, entity_code="AVM-US", period_key="FY2026-P02"
    )
    assert (february["variance_count"], february["status"]) == (0, "DRAFT")
    assert (february["kind"], february["entity"]["code"], february["book"]) == (
        "BILLING_TO_SUBLEDGER",
        "AVM-US",
        "ASC606",
    )
    assert february["period"]["period_key"] == "FY2026-P02"
    assert february["reconciliation_no"].startswith("REC-")
    # INV-US-1044 is February's one document: both sides 15,000.00.
    assert february["totals"] == [_total("15000.00", "15000.00", "0.00", "USD")]
    assert recon.items_of(app, world.maya, february["id"]) == []
    assert (february["is_current"], february["signoffs"], february["auto_certify_rule"]) == (
        True,
        [],
        None,
    )
    # CTL-024 evidence of a clean run: one document compared, no exception.
    (clean,) = recon.control_executions(world.tenant_id, "CTL-024", february["id"])
    assert (
        clean["run_ref_type"],
        clean["population_count"],
        clean["exception_count"],
        str(clean["result"]),
    ) == ("RECONCILIATION_RUN", 1, 0, "PASS")

    # January holds INV-US-1001: 120,000.00 on both sides.
    january = recon.generated(
        app, world.maya, runtime, entity_code="AVM-US", period_key="FY2026-P01"
    )
    assert (january["variance_count"], january["status"]) == (0, "DRAFT")
    assert january["totals"] == [_total("120000.00", "120000.00", "0.00", "USD")]
    # March has no billing document: nothing compared, no variance.
    march = recon.generated(app, world.maya, runtime, entity_code="AVM-US", period_key="FY2026-P03")
    assert (march["variance_count"], march["totals"]) == (0, [])

    # The list answers the period's reconciliations by kind.
    listed = get(
        app,
        recon.RECONCILIATIONS,
        world.maya,
        {"entity": "AVM-US", "period": "FY2026-P02", "kind": "BILLING_TO_SUBLEDGER"},
    )
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()["items"]] == [february["id"]]


def _fenwright(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, runtime: JobRuntime
) -> tuple[K11World, UUID]:
    """AVM-DE with ``NS-SO-DE-5003`` (O1 100,000.00 EUR delivered 2026-08-14), INV-DE-4390
    100,000.00 ingested and its billing event voided (module docstring); the world and the
    contract id."""
    world = k11_world(app, keyring, clock, files)
    assign(world.priya.member, "revenue_reviewer")  # import.approve, event.approve
    buyer = customer_id(app, world.place.author, code="C-07", name="Fenwright Logistik GmbH (Demo)")
    booked = booked_contract(
        world.place,
        {
            "external_id": K07,
            "customer_id": str(buyer),
            "contracting_entity_code": "AVM-DE",
            "transaction_currency": "EUR",
            "inception_date": "2026-08-14",
            "lines": [
                {
                    "obligation_key": "O1",
                    "product_code": GATEWAY,
                    "quantity": "200",
                    "total_price": _usd("100000.00", "EUR"),
                }
            ],
        },
        activate=False,
    )
    booked = activated_contract(world.place, booked, compute=False)
    contract_id = UUID(str(booked.contract["id"]))
    appended(
        world.place,
        contract_id,
        2,
        [
            EventIn(
                event_type=ContractEventType.DELIVERY_RECORDED,
                effective_date=date(2026, 8, 14),
                payload=DeliveryRecordedV1(obligation_key="O1", quantity="200", trigger="DELIVERY"),
            )
        ],
    )
    computed(world.place, UUID(str(booked.combination_group["id"])))
    recon.ingested(
        app,
        world.place.author,
        world.priya,
        runtime,
        "avm-de-invoices-2026-09.csv",
        recon.invoices_csv(K07_INVOICE),
    )
    (billing,) = _rows(
        world.place.tenant_id,
        select(contract_event.c.id).where(
            contract_event.c.contract_id == contract_id,
            contract_event.c.event_type == ContractEventType.BILLING_RECORDED.value,
        ),
    )
    requested = post(
        app,
        f"{EVENTS}/{billing['id']}/request-void",
        world.place.author,
        {"reason_code": "CREATED_IN_ERROR", "comment": "Invoice applied before it was issued."},
    )
    assert requested.status_code == 201, requested.text
    decided = approve(app, str(requested.json()["approval_request_id"]), world.priya)
    assert decided.status_code == 200, decided.text
    return world, contract_id


@pytest.mark.control("CTL-024")
def test_ctl_024_unmatched_source_invoice(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, runtime: JobRuntime
) -> None:
    """BUILD_SPEC CLO-16, control CTL-024 (failure path): a source invoice ``INV-DE-4390``
    100,000.00 with no billing event produces item ``UNMATCHED_SOURCE`` with ``source_amount``
    100,000.00 and ``difference`` 100,000.00; after the billing event is recorded, regenerating
    gives ``variance_count`` 0 (REQ-CLS-015)."""
    world, contract_id = _fenwright(app, keyring, clock, files, runtime)
    maya = world.place.author
    tenant_id = world.place.tenant_id

    first = recon.generated(app, maya, runtime, entity_code="AVM-DE", period_key="FY2026-P08")
    assert (first["variance_count"], first["status"]) == (1, "DRAFT")
    assert first["totals"] == [_total("0.00", "100000.00", "100000.00", "EUR")]
    (item,) = recon.items_of(app, maya, first["id"])
    assert (item["item_kind"], item["invoice_number"], item["currency"]) == (
        "UNMATCHED_SOURCE",
        "INV-DE-4390",
        "EUR",
    )
    assert item["source_amount"] == _usd("100000.00", "EUR")
    assert item["difference"] == _usd("100000.00", "EUR")
    assert item["subledger_amount"] is None
    assert item["contract"] == {"id": str(contract_id), "external_id": K07}
    assert (item["is_high_risk"], item["explanation"], item["resolved_at"]) == (False, None, None)
    # The control failed by name: one document compared, one exception.
    (failed,) = recon.control_executions(tenant_id, "CTL-024", first["id"])
    assert (failed["population_count"], failed["exception_count"], str(failed["result"])) == (
        1,
        1,
        "FAIL",
    )
    assert failed["detail"]["variance_count"] == 1
    # A variance is never signed away unexplained (SM-09): the preparer is refused. Maya works
    # on with the verified session: once she has a factor, the one of before owes the challenge
    # (REQ-PLT-005).
    maya = preparer = enrolled(app, clock, maya.member)
    refused = recon.prepare(app, preparer, first["id"])
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    assert refused.json()["detail"] == "Explain 1 differences above the threshold before signing."

    # The billing event is recorded: INV-DE-4390 100,000.00 on O1, dated as the invoice.
    (head,) = _rows(
        tenant_id, select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    appended(
        world.place,
        contract_id,
        int(head["head_stream_version"]),
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 8, 31),
                payload=BillingRecordedV1(
                    invoice_number="INV-DE-4390",
                    line_external_id="1",
                    obligation_key="O1",
                    amount=MoneyIn(amount="100000.00", currency="EUR"),
                    issue_date=date(2026, 8, 31),
                ),
            )
        ],
    )
    again = recon.generated(app, maya, runtime, entity_code="AVM-DE", period_key="FY2026-P08")
    assert (again["variance_count"], again["status"]) == (0, "DRAFT")
    assert again["totals"] == [_total("100000.00", "100000.00", "0.00", "EUR")]
    assert recon.items_of(app, maya, again["id"]) == []
    (passed,) = recon.control_executions(tenant_id, "CTL-024", again["id"])
    assert (passed["population_count"], passed["exception_count"], str(passed["result"])) == (
        1,
        0,
        "PASS",
    )
    # Every generation is a reconciliation of its own; the later one is the current one, and the
    # earlier one takes no further command (04 T-CLS-06 rev 1.121; supervisor ruling R-54 (b)).
    assert again["id"] != first["id"] and again["reconciliation_no"] != first["reconciliation_no"]
    assert (again["is_current"], recon.shown(app, maya, first["id"])["is_current"]) == (True, False)
    late = recon.explain(app, maya, item, EXPLANATION)
    assert (late.status_code, slug(late)) == (409, "invalid-transition"), late.text
    assert first["reconciliation_no"] in late.json()["detail"]
    assert again["reconciliation_no"] in late.json()["detail"]


def test_preparer_reviewer_separation(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore, runtime: JobRuntime
) -> None:
    """BUILD_SPEC CLO-16: ``maya`` signs as preparer (``PREPARED``); ``maya``'s reviewer signature
    returns 403 ``self-approval`` (DB-10); ``priya`` signs (``REVIEWED``); an Integration Admin's
    reviewer signature returns 403 ``forbidden`` (SoD-7)."""
    world: CloseWorld = close_world(app, keyring, clock, files)
    tenant_id = world.tenant_id
    draft = recon.generated(app, world.maya, runtime, entity_code="AVM-US", period_key="FY2026-P09")
    assert (draft["status"], draft["variance_count"]) == ("DRAFT", 0)

    # A sign-off carries the session's MFA verification (T-CLS-08): Maya, not yet enrolled, is
    # refused; enrolled, she signs as preparer.
    unverified = recon.prepare(app, world.maya, draft["id"])
    assert (unverified.status_code, slug(unverified)) == (403, "mfa-required"), unverified.text
    # Maya also holds ``recon.signoff`` here, so nothing but DB-10 can refuse her review.
    assign(world.maya.member, "revenue_reviewer")
    maya = enrolled(app, clock, world.maya.member)
    prepared = recon.prepare(app, maya, draft["id"])
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["status"] == "PREPARED"
    (preparer,) = prepared.json()["signoffs"]
    assert (preparer["role"], preparer["signer"]["id"]) == ("PREPARER", str(maya.member.user_id))
    assert preparer["statement"] == (
        "I prepared this reconciliation and explained every difference above the threshold."
    )

    own = recon.sign(app, maya, draft["id"])
    assert (own.status_code, slug(own)) == (403, "self-approval"), own.text
    assert own.json()["detail"] == "You prepared this reconciliation. Another user must review it."

    # SoD-7: an Integration Admin holds no sign-off permission ...
    nikhil = actor_with_role(app, clock, tenant_id, "integration_admin", name="nikhil")
    outsider = recon.sign(app, nikhil, draft["id"])
    assert (outsider.status_code, slug(outsider)) == (403, "forbidden"), outsider.text
    # ... and one who was also given ``recon.signoff`` is still refused by the SM-09 guard.
    both_member = colleague(tenant_id, "ines")
    assign(both_member, "integration_admin")
    assign(both_member, "revenue_reviewer")
    both = recon.sign(app, enrolled(app, clock, both_member), draft["id"])
    assert (both.status_code, slug(both)) == (403, "forbidden"), both.text
    assert [error["rule_id"] for error in both.json()["errors"]] == ["SoD-7"]

    priya = actor_with_role(app, clock, tenant_id, "revenue_reviewer", name="priya")
    unaccepted = post(
        app,
        f"{recon.RECONCILIATIONS}/{draft['id']}/sign",
        priya,
        {"role": "REVIEWER", "statement_accepted": False},
    )
    assert (unaccepted.status_code, slug(unaccepted)) == (422, "validation-failed")
    reviewed = recon.sign(app, priya, draft["id"])
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert body["status"] == "REVIEWED"
    assert [(item["role"], item["signer"]["id"]) for item in body["signoffs"]] == [
        ("PREPARER", str(maya.member.user_id)),
        ("REVIEWER", str(priya.member.user_id)),
    ]
    # Both sign-offs carry the hash of the one snapshot that was frozen for review.
    hashes = {item["subject_content_sha256"] for item in body["signoffs"]}
    assert len(hashes) == 1 and len(next(iter(hashes))) == 64
    stored = _rows(
        tenant_id,
        select(signoff.c.role, signoff.c.signer_id, signoff.c.mfa_verified_at).where(
            signoff.c.subject_type == "reconciliation", signoff.c.subject_id == UUID(draft["id"])
        ),
    )
    assert sorted(str(row["role"]) for row in stored) == ["PREPARER", "REVIEWER"]
    assert all(row["mfa_verified_at"] is not None for row in stored)
    # A reviewed reconciliation is signed once: a second review is a refused transition.
    again = recon.sign(app, priya, draft["id"])
    assert (again.status_code, slug(again)) == (409, "invalid-transition"), again.text


def test_certified_reconciliation_frozen(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """BUILD_SPEC CLO-16 with supervisor ruling R-54 (c): ``reopen`` requires ``recon.signoff`` and
    moves a reviewed reconciliation to ``REOPENED``; after lock the current reconciliation is
    ``CERTIFIED``, ``PATCH`` of an item returns 409 ``invalid-transition`` and ``reopen`` returns
    409 — a certified reconciliation leaves that state only through the period reopen (04
    T-CLS-06; SCREENS_B §2.2 "Certified")."""
    pellworth = k01_pellworth(app, keyring, clock, files, through=date(2026, 1, 31))
    assign(pellworth.priya.member, "revenue_reviewer")  # recon.signoff (PRD ACT-34)
    # The close runs on the record-time clock, as the lock's freeze does (the precedent of
    # ``test_lock.py::test_contract_balances_snapshot_k01``); the jump ends every session.
    stamp = pellworth.place.scalar(select(func.clock_timestamp()))
    clock.set(stamp + timedelta(seconds=1))
    pellworth = resigned(pellworth)
    runtime = pellworth.runtime
    tenant_id = pellworth.tenant_id
    maya = enrolled(app, clock, pellworth.maya.member)  # a sign-off needs an MFA-verified session
    # The world works with that session too: with a factor, Maya's earlier one owes the challenge
    # (REQ-PLT-005).
    pellworth = carrying(pellworth, maya=maya)
    priya = step_up(app, clock, pellworth.priya)
    (january,) = [
        item
        for item in periods(app, maya, entity="AVM-US")
        if item["period"]["period_key"] == "FY2026-P01"
    ]
    period_id = UUID(str(january["period"]["id"]))
    started = post(
        app,
        f"{PERIODS}/{january['id']}/start-close",
        maya,
        {"comment": "January close"},
        if_match=f'"r{january["row_version"]}"',
    )
    assert started.status_code == 200, started.text

    def explained_and_prepared() -> tuple[dict[str, Any], dict[str, Any]]:
        """January generated, its one difference explained, signed by Maya as preparer."""
        draft = recon.generated(app, maya, runtime, entity_code="AVM-US", period_key="FY2026-P01")
        # INV-US-1001 is a billing event without a billing-system document in this world.
        (item,) = recon.items_of(app, maya, draft["id"])
        assert (item["item_kind"], item["invoice_number"]) == ("UNMATCHED_SUBLEDGER", "INV-US-1001")
        assert (item["subledger_amount"], item["difference"]) == (
            _usd("120000.00"),
            _usd("-120000.00"),
        )
        explained = recon.explain(app, maya, item, EXPLANATION)
        assert explained.status_code == 200, explained.text
        assert explained.json()["explanation"] == EXPLANATION
        assert explained.json()["resolved_by"]["id"] == str(maya.member.user_id)
        signed = recon.prepare(app, maya, draft["id"])
        assert signed.status_code == 200, signed.text
        return signed.json(), explained.json()

    # --- reopen: recon.signoff, from a reviewed reconciliation ---------------------------------
    first, _ = explained_and_prepared()
    reviewed = recon.sign(app, priya, first["id"])
    assert reviewed.status_code == 200, reviewed.text
    # Maya holds ``recon.prepare`` only: the reopen is refused.
    denied = recon.reopen(app, maya, first["id"], REOPEN_REASON)
    assert (denied.status_code, slug(denied)) == (403, "forbidden"), denied.text
    reopened = recon.reopen(app, priya, first["id"], REOPEN_REASON)
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "REOPENED"
    # The sign-offs stay as history.
    assert [item["role"] for item in reopened.json()["signoffs"]] == ["PREPARER", "REVIEWER"]

    # --- the reconciliation is generated again, reviewed and certified by the lock -------------
    second, item = explained_and_prepared()
    assert second["id"] != first["id"]
    assert recon.sign(app, priya, second["id"]).status_code == 200
    requested = post(app, JOURNAL_RUNS, maya, {"entity_code": "AVM-US", "period_key": "FY2026-P01"})
    assert requested.status_code == 202, requested.text
    calculated = run_now(pellworth, UUID(str(requested.json()["id"])))
    assert calculated["state"] == "SUCCEEDED", calculated
    context = DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        acknowledge_run(
            session, UUID(str(requested.headers[JOURNAL_RUN_ID_HEADER])), now=clock.now()
        )
        # The subledger-to-GL reconciliation is BUILD_SPEC CLO-17's: its reviewed row is fixture
        # state here, as in ``test_lock.py``.
        reviewed_reconciliations_for(
            session,
            tenant_id=tenant_id,
            entity_id=pellworth.entity_id,
            period_id=period_id,
            now=clock.now(),
            kinds=("SUBLEDGER_TO_GL",),
        )
        # The period's close run is fixture state as well (supervisor ruling R-114 (b)): a
        # SUCCEEDED row for the gate CLOSE_RUN_COMPLETED, written here, right before the request.
        close_run_succeeded_for(
            session,
            tenant_id=tenant_id,
            entity_id=pellworth.entity_id,
            period_id=period_id,
            now=clock.now(),
        )
        # Supervisor ruling R-55 (b): a lock can be decided with a reconciliation kind not reviewed
        # (its gate waived). The two rollforward kinds are none the gate requires, so fixture rows
        # of them reach the lock as such a kind does: a REVIEWED RPO rollforward that a later DRAFT
        # generation replaced, and a PREPARED contract balance rollforward.
        fixture = {"tenant_id": tenant_id, "entity_id": pellworth.entity_id, "period_id": period_id}
        (replaced_id,) = reviewed_reconciliations_for(
            session, **fixture, now=clock.now(), kinds=("RPO_ROLLFORWARD",)
        )
        replaced_as_of = session.execute(
            select(reconciliation.c.as_of_known_at).where(reconciliation.c.id == replaced_id)
        ).scalar_one()
        unreviewed = reconciliation_values(
            tenant_id,
            entity_id=pellworth.entity_id,
            period_id=period_id,
            kind="RPO_ROLLFORWARD",
            as_of_known_at=replaced_as_of + timedelta(seconds=1),  # the later generation
        )
        session.execute(insert(reconciliation).values(**unreviewed))
        (prepared_id,) = reviewed_reconciliations_for(
            session,
            **fixture,
            now=clock.now(),
            kinds=("CONTRACT_BALANCE_ROLLFORWARD",),
            status="PREPARED",
        )
    with pellworth.place.uow() as uow:
        out = close_commands.request_lock(
            uow,
            state_id=UUID(str(january["id"])),
            body=PeriodLockRequestIn(certification_comment="January 2026 close complete"),
            check_version=lambda actual: None,
        )
        uow.commit()
    controller = actor_with_role(app, clock, tenant_id, "controller", name="cora")
    decided = approve(app, str(out.approval_request_id), controller)
    assert decided.status_code == 200, decided.text

    certified = recon.shown(app, maya, second["id"])
    assert certified["status"] == "CERTIFIED"
    assert certified["certified_at"] is not None and certified["period_lock_id"] is not None
    # The reopened reconciliation is history: the lock certified the current one only.
    history = recon.shown(app, maya, first["id"])
    assert (history["status"], history["period_lock_id"], history["is_current"]) == (
        "REOPENED",
        None,
        False,
    )
    # R-55 (b): the lock certifies the current REVIEWED and AUTO_CERTIFIED reconciliations only.
    # A current DRAFT or PREPARED one is left as it is, and so is the reviewed generation that a
    # later one replaced — before the current-reconciliation rule the lock certified that row.
    left = _rows(
        tenant_id,
        select(
            reconciliation.c.id,
            reconciliation.c.status,
            reconciliation.c.period_lock_id,
            reconciliation.c.certified_at,
        ).where(reconciliation.c.id.in_([replaced_id, unreviewed["id"], prepared_id])),
    )
    assert {
        row["id"]: (str(row["status"]), row["period_lock_id"], row["certified_at"]) for row in left
    } == {
        replaced_id: ("REVIEWED", None, None),
        unreviewed["id"]: ("DRAFT", None, None),
        prepared_id: ("PREPARED", None, None),
    }
    # Frozen: an item takes no explanation and the reconciliation no reopen.
    fresh = next(row for row in recon.items_of(app, maya, second["id"]) if row["id"] == item["id"])
    patched = recon.explain(app, maya, fresh, "A later explanation of the same difference.")
    assert (patched.status_code, slug(patched)) == (409, "invalid-transition"), patched.text
    refused = recon.reopen(app, priya, second["id"], REOPEN_REASON)
    assert (refused.status_code, slug(refused)) == (409, "invalid-transition"), refused.text
    for response in (patched, refused):
        assert response.json()["detail"].startswith("Certified at lock on ")
        assert response.json()["detail"].endswith("Reopen the period to change it.")
    stored = _rows(
        tenant_id,
        select(reconciliation_item.c.explanation, reconciliation.c.status)
        .join(reconciliation, reconciliation.c.id == reconciliation_item.c.reconciliation_id)
        .where(reconciliation_item.c.id == UUID(item["id"])),
    )
    assert [(row["explanation"], str(row["status"])) for row in stored] == [
        (EXPLANATION, "CERTIFIED")
    ]
