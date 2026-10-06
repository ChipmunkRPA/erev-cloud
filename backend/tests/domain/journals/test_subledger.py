"""Subledger postings, seals and ledger chains (04 T-SL-01 to T-SL-04, §14.1 DB-06; dev-guide
DG-CMD-10; 05 RCP-04 to RCP-06, RCP-21; ENGINE_SPEC S02-R-02; ENGINE_SPEC_B §14.2 S14-R-12,
S14-R-15; PRD WLD-K-11, WLD-X-22, J-04.1; 03 REQ-JE-006; CTL-023; BUILD_SPEC CTR-3, BS3-D-19).

``support.factories.k11_world`` creates PRD §2.6 for K-11 through the RFD routes: AVM-DE (EUR,
Europe/Berlin) with FY2026-P01 to P09 open, customer C-11, AVM-GW (TPL-PROD-UNITS; DE-LIST 2026
observable 405.00 / 450.00 / 495.00 EUR per unit), AVM-SUP-12 (TPL-SUB-DAILY; cost plus margin
19,000.00 / 20,000.00 / 21,000.00 EUR) and AVM-MAP-2026-01 (4000 revenue, 2100 contract liability).
K-11 ``NS-SO-DE-5004`` is booked through ``book_contract``, activated by the SYSTEM principal
(BS3-D-19) and receives ``DELIVERY_RECORDED`` of 120 O1 units effective 2026-09-12.
``support.factories.engine()`` computes: the ENGINE_SPEC §0.5 fake until END-9 lands in this
checkout, ``erev_engine.compute`` in the L3 merge gate (V-C). The frozen clock reads
2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db import new_id
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    audit_event,
    contract_version,
    gl_account,
    ledger_chain_head,
    obligation,
    period,
    subledger_line,
    subledger_posting,
    subledger_posting_seal,
)
from erev_api.domain.contracts import computation
from erev_api.domain.journals import subledger
from erev_api.enums import ContractEventType, ControlResult, SubledgerPostingKind
from erev_api.events.payloads import ReturnRecordedV1
from erev_api.events.stream import EventIn
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from fastapi import FastAPI
from sqlalchemy import and_, exc, func, insert, select, update
from support.db import TestDatabase
from support.factories import (
    K11_EXTERNAL_ID,
    K11World,
    appended,
    computed,
    delivered_k11,
    k11_world,
)

BOOK = "ASC606"
REVENUE = "REVENUE"
LIABILITY = "CONTRACT_LIABILITY"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def world(app: FastAPI, keyring: KeyRing, clock: FrozenClock, app_settings: Settings) -> K11World:
    return k11_world(app, keyring, clock, LocalFileStore(app_settings.file_root))


def _lines(world: K11World, posting_id: UUID | str) -> list[dict[str, Any]]:
    """The posting's lines with their period key and account code, by entry and role."""
    tenant = subledger_line.c.tenant_id
    return world.place.rows(
        select(subledger_line, period.c.period_key, gl_account.c.code.label("account_code"))
        .select_from(
            subledger_line.join(
                period,
                and_(period.c.tenant_id == tenant, period.c.id == subledger_line.c.period_id),
            ).join(
                gl_account,
                and_(
                    gl_account.c.tenant_id == tenant,
                    gl_account.c.id == subledger_line.c.gl_account_id,
                ),
            )
        )
        .where(subledger_line.c.subledger_posting_id == UUID(str(posting_id)))
        .order_by(subledger_line.c.entry_no, subledger_line.c.account_role)
    )


def _counts(world: K11World) -> tuple[int, ...]:
    return tuple(
        int(world.place.scalar(select(func.count()).select_from(table)))
        for table in (subledger_posting, subledger_line, subledger_posting_seal)
    )


def _verify(world: K11World) -> subledger.LedgerChainVerification:
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context, read_only=True) as session:
        return subledger.verify_ledger_chain(session, book_code=BOOK)


def _o1(world: K11World) -> UUID:
    return UUID(
        str(world.place.scalar(select(obligation.c.id).where(obligation.c.obligation_key == "O1")))
    )


def test_active_contract_posts_sealed_balanced_posting(world: K11World) -> None:
    booked = delivered_k11(world)
    group_id = booked.combination_group["id"]
    _, _, stored = computed(world.place, group_id)
    computation_id = stored["id"]

    # One ENGINE_COMPUTE posting keyed compute:<computation id> (T-SL-01; DG-CMD-10).
    (posting,) = world.place.rows(select(subledger_posting))
    assert (
        posting["book_code"],
        posting["posting_kind"],
        posting["idempotency_key"],
        posting["contract_computation_id"],
        posting["combination_group_id"],
        posting["close_run_id"],
    ) == (BOOK, "ENGINE_COMPUTE", f"compute:{computation_id}", computation_id, group_id, None)
    assert stored["subledger_posting_ids"] == {BOOK: str(posting["id"])}

    # Balanced per (entity, book, period, entry, currency) in both currencies (D-16).
    lines = _lines(world, posting["id"])
    sums: dict[tuple[Any, ...], list[Decimal]] = {}
    for line in lines:
        key = (
            line["entity_id"],
            line["book_code"],
            line["period_id"],
            line["entry_no"],
            line["txn_currency"],
        )
        totals = sums.setdefault(key, [Decimal(0), Decimal(0)])
        totals[0] += line["amount_txn"]
        totals[1] += line["amount_functional"]
    assert sums and all(values == [0, 0] for values in sums.values())

    # PRD WLD-X-22: O1 revenue for 120 of 200 units is 89,174.31 × 120 ÷ 200 = 53,504.59 EUR in
    # FY2026-P09, credited to revenue against the contract liability (JET-02 principal).
    o1 = _o1(world)
    (revenue,) = [
        line for line in lines if line["account_role"] == REVENUE and line["obligation_id"] == o1
    ]
    (liability,) = [
        line
        for line in lines
        if line["account_role"] == LIABILITY
        and line["obligation_id"] == o1
        and line["entry_no"] == revenue["entry_no"]
    ]
    version_id = UUID(stored["contract_version_ids"][BOOK])
    trace_id = world.place.scalar(
        select(contract_version.c.calc_trace_id).where(contract_version.c.id == version_id)
    )
    assert (
        revenue["amount_txn"],
        revenue["txn_currency"],
        revenue["amount_functional"],
        revenue["functional_currency"],
        revenue["dr_cr"],
        revenue["period_key"],
        revenue["period_end_date"],
        revenue["origin_period_id"],
        revenue["reason_code"],
        revenue["is_post_reopen"],
        revenue["entry_kind"],
        revenue["account_code"],
        revenue["effective_date"],
        revenue["entity_id"],
        revenue["contract_id"],
        revenue["contract_version_id"],
        revenue["calc_trace_id"],
        revenue["legacy_key"],
    ) == (
        Decimal("-53504.5900"),
        "EUR",
        Decimal("-53504.5900"),
        "EUR",
        "C",
        "FY2026-P09",
        date(2026, 9, 30),
        None,
        None,
        False,
        "REVENUE_RECOGNITION",
        "4000",
        date(2026, 9, 12),
        world.entity_id,
        booked.contract["id"],
        version_id,
        trace_id,
        "NS-SO-DE-5004 O1 AVM-GW",
    )
    assert (
        liability["amount_txn"],
        liability["dr_cr"],
        liability["account_code"],
        liability["entry_no"],
    ) == (Decimal("53504.5900"), "D", "2100", revenue["entry_no"])
    assert revenue["dimension_set_sha256"] == subledger.dimension_set_sha256(revenue["dimensions"])

    # The seal: chain_seq 1 without a previous seal, the trigger's control totals, the application's
    # hash, and the ASC606 chain head naming it (T-SL-02, T-SL-03).
    (seal,) = world.place.rows(select(subledger_posting_seal))
    totals = subledger.control_totals(lines)
    assert (seal["subledger_posting_id"], seal["chain_seq"], seal["prev_seal_sha256"]) == (
        posting["id"],
        1,
        None,
    )
    assert seal["line_count"] == len(lines)
    assert seal["control_totals"] == totals
    (total,) = totals
    assert (total["entity_id"], total["period_id"], total["currency"]) == (
        str(world.entity_id),
        str(revenue["period_id"]),
        "EUR",
    )
    assert total["debit_txn"] == total["credit_txn"] == total["credit_functional"]
    assert Decimal(total["credit_txn"]) >= Decimal("53504.59")
    assert seal["seal_sha256"] == subledger.seal_sha256(None, posting, totals, lines)
    heads = world.place.rows(select(ledger_chain_head).order_by(ledger_chain_head.c.book_code))
    assert [
        (row["book_code"], row["last_chain_seq"], row["last_seal_sha256"]) for row in heads
    ] == [
        (BOOK, 1, seal["seal_sha256"]),
        ("IFRS15", 0, None),
        ("LEGACY", 0, None),
    ]
    verified = _verify(world)
    assert (verified.result, verified.seals_checked, verified.last_seal_sha256) == (
        ControlResult.PASS,
        1,
        seal["seal_sha256"],
    )

    # AUD-FACT summaries of the posting, its lines and its seal.
    actions = world.place.rows(
        select(audit_event.c.action)
        .where(
            audit_event.c.object_type.in_(
                ["subledger_posting", "subledger_line", "subledger_posting_seal"]
            )
        )
        .order_by(audit_event.c.chain_seq)
    )
    assert [row["action"] for row in actions] == [
        "subledger_posting.create",
        "subledger_line.create",
        "subledger_posting_seal.create",
    ]


def test_draft_contract_posts_nothing(world: K11World) -> None:
    # ENGINE_SPEC S02-R-02: a DRAFT contract's computation is provisional and emits no posting.
    booked = delivered_k11(world, activate=False)
    _, output, stored = computed(world.place, booked.combination_group["id"])
    assert [book.posting_intents for book in output.books] == [()]
    assert stored["subledger_posting_ids"] == {}
    assert _counts(world) == (0, 0, 0)
    assert (
        world.place.scalar(
            select(contract_version.c.status_in_book).where(
                contract_version.c.id == UUID(stored["contract_version_ids"][BOOK])
            )
        )
        == "DRAFT"
    )
    head = world.place.rows(
        select(ledger_chain_head.c.last_chain_seq, ledger_chain_head.c.last_seal_sha256).where(
            ledger_chain_head.c.book_code == BOOK
        )
    )
    assert head == [{"last_chain_seq": 0, "last_seal_sha256": None}]


def test_retried_persist_does_not_double_post(world: K11World) -> None:
    booked = delivered_k11(world)
    bundle, output, stored = computed(world.place, booked.combination_group["id"])
    posting_id = UUID(stored["subledger_posting_ids"][BOOK])
    before = _counts(world)
    assert (before[0], before[2]) == (1, 1)

    # RCP-21: the same bundle and engine version persist nothing, and name the stored posting.
    with world.place.uow() as uow:
        again = computation.persist(uow, bundle, output)
        uow.commit()
    assert (again["replayed"], again["id"], again["subledger_posting_ids"]) == (
        True,
        stored["id"],
        stored["subledger_posting_ids"],
    )

    # A retried post under the key compute:<computation id> returns the stored posting.
    with world.place.uow() as uow:
        retried = subledger.post(
            uow,
            book_code=BOOK,
            posting_kind=SubledgerPostingKind.ENGINE_COMPUTE,
            idempotency_key=subledger.compute_key(stored["id"]),
            description="Retried computation",
            lines=[],
            contract_computation_id=stored["id"],
        )
        uow.commit()
    assert (retried.replayed, retried.posting_id, retried.chain_seq, len(retried.line_ids)) == (
        True,
        posting_id,
        1,
        before[1],
    )
    assert _counts(world) == before

    # ux_subledger_posting__idempotency refuses a second row of the key.
    with world.place.uow() as uow:
        duplicate = dict(world.place.rows(select(subledger_posting))[0])
        duplicate["id"] = new_id()
        del duplicate["created_txid"]
        savepoint = uow.session.begin_nested()
        with pytest.raises(exc.IntegrityError) as excinfo:
            uow.session.execute(insert(subledger_posting).values(**duplicate))
        savepoint.rollback()
    assert "ux_subledger_posting__idempotency" in str(excinfo.value)
    assert _counts(world) == before


@pytest.mark.control("CTL-023")
def test_ctl_023_correction_posts_delta_lines(world: K11World) -> None:
    booked = delivered_k11(world)
    group_id = booked.combination_group["id"]
    _, _, first = computed(world.place, group_id)
    first_id = UUID(first["subledger_posting_ids"][BOOK])
    before = _lines(world, first_id)

    appended(
        world.place,
        booked.contract["id"],
        3,
        [
            EventIn(
                event_type=ContractEventType.RETURN_RECORDED,
                effective_date=date(2026, 9, 12),
                payload=ReturnRecordedV1(obligation_key="O1", quantity="20"),
            )
        ],
    )
    bundle, _, second = computed(world.place, group_id)

    # RCP-05: the recomputation reads the first posting's amounts in minor units.
    subject = obligation_subject_key(K11_EXTERNAL_ID, "O1")
    assert [
        (
            item.book_code,
            item.entity_code,
            item.subject_key,
            item.entry_kind,
            item.account_role,
            item.period_key,
            item.origin_period_key,
            item.posting_class,
            item.txn_currency,
            item.amount_txn,
            item.amount_functional,
        )
        for item in bundle.posted
        if item.subject_key == subject
    ] == [
        (
            BOOK,
            "AVM-DE",
            subject,
            "REVENUE_RECOGNITION",
            LIABILITY,
            "FY2026-P09",
            None,
            "EVENT",
            "EUR",
            5350459,
            5350459,
        ),
        (
            BOOK,
            "AVM-DE",
            subject,
            "REVENUE_RECOGNITION",
            REVENUE,
            "FY2026-P09",
            None,
            "EVENT",
            "EUR",
            -5350459,
            -5350459,
        ),
    ]

    # REQ-JE-006: a new posting reverses 89,174.31 × 20 ÷ 200 = 8,917.43 of O1 revenue; the first
    # posting's lines are unchanged.
    second_id = UUID(second["subledger_posting_ids"][BOOK])
    assert second_id != first_id
    o1 = _o1(world)
    corrections = _lines(world, second_id)
    assert sorted(
        (
            line["account_role"],
            line["obligation_id"],
            line["amount_txn"],
            line["dr_cr"],
            line["period_key"],
        )
        for line in corrections
        if line["obligation_id"] == o1
    ) == [
        (LIABILITY, o1, Decimal("-8917.4300"), "C", "FY2026-P09"),
        (REVENUE, o1, Decimal("8917.4300"), "D", "FY2026-P09"),
    ]
    assert _lines(world, first_id) == before
    revenue_total = world.place.scalar(
        select(func.sum(subledger_line.c.amount_txn)).where(
            subledger_line.c.obligation_id == o1, subledger_line.c.account_role == REVENUE
        )
    )
    assert revenue_total == Decimal("-44587.1600")
    seals = world.place.rows(
        select(
            subledger_posting_seal.c.subledger_posting_id,
            subledger_posting_seal.c.chain_seq,
            subledger_posting_seal.c.prev_seal_sha256,
            subledger_posting_seal.c.seal_sha256,
        ).order_by(subledger_posting_seal.c.chain_seq)
    )
    assert [(row["subledger_posting_id"], row["chain_seq"]) for row in seals] == [
        (first_id, 1),
        (second_id, 2),
    ]
    assert seals[1]["prev_seal_sha256"] == seals[0]["seal_sha256"]
    verified = _verify(world)
    assert (verified.result, verified.seals_checked) == (ControlResult.PASS, 2)

    # CTL-023: an UPDATE of a posted line fails (erev_app holds SELECT and INSERT only).
    context = DbContext(tenant_id=world.place.tenant_id, user_id=None, entity_scope="*")
    target = and_(
        subledger_line.c.period_end_date == before[0]["period_end_date"],
        subledger_line.c.id == before[0]["id"],
    )
    with tenant_session(context) as session:
        savepoint = session.begin_nested()
        with pytest.raises(exc.DBAPIError) as excinfo:
            session.execute(update(subledger_line).where(target).values(amount_txn=Decimal("0.01")))
        savepoint.rollback()
    assert getattr(excinfo.value.orig, "sqlstate", None) == "42501"
    assert _lines(world, first_id) == before


def test_posted_amounts_keep_repeated_compute_a_no_op(world: K11World) -> None:
    # RCP-06, PROP:P9: once the delivery has posted, a recomputation over the unchanged stream
    # writes a new version but no posting, because every delta against the posted amounts is 0.
    booked = delivered_k11(world)
    group_id = booked.combination_group["id"]
    computed(world.place, group_id)
    posted_once = _counts(world)
    bundle, output, stored = computed(world.place, group_id)
    assert stored["replayed"] is False
    assert [len(item.posting_intents) for item in output.books] == [0]
    assert stored["subledger_posting_ids"] == {}
    assert obligation_subject_key(K11_EXTERNAL_ID, "O1") in {
        item.subject_key for item in bundle.posted
    }
    assert _counts(world) == posted_once
    assert _verify(world).result == ControlResult.PASS


def test_a_product_posting_stores_the_subject_of_every_line_and_the_door_requires_it(
    world: K11World,
) -> None:
    """04 T-SL-04 ``subject_key`` (rev 1.282; supervisor ruling R-11 as amended on 2026-10-02;
    dev-guide DG-CMD-10; item ENG-COST-READBACK-1). The lines of a computation store the subject
    their intent was posted under — here each line the subject of its own obligation, the
    delivered units of O1 and the support of O2 — as a member of the sealed line document, and
    the chain verifies. A posting whose caller requires the key, as every caller inside
    ``erev_api`` does, is refused by name before anything is written when a line names none; the
    default of the door keeps the lines of a test builder, which store no key."""
    booked = delivered_k11(world)
    _, _, stored = computed(world.place, booked.combination_group["id"])
    subject = obligation_subject_key(K11_EXTERNAL_ID, "O1")
    lines = _lines(world, stored["subledger_posting_ids"][BOOK])
    keys = {
        row["id"]: str(row["obligation_key"])
        for row in world.place.rows(select(obligation.c.id, obligation.c.obligation_key))
    }
    assert lines and all(
        line["subject_key"] == obligation_subject_key(K11_EXTERNAL_ID, keys[line["obligation_id"]])
        for line in lines
    )
    assert {line["subject_key"] for line in lines} == {
        subject,
        obligation_subject_key(K11_EXTERNAL_ID, "O2"),
    }
    assert subledger.SUBJECT_KEY in subledger.LINE_MEMBERS
    assert _verify(world).result == ControlResult.PASS

    before = _counts(world)
    with (
        world.place.uow() as uow,
        pytest.raises(ValueError, match="line 2 of a ENGINE_COMPUTE posting names no subject key"),
    ):
        subledger.post(
            uow,
            book_code=BOOK,
            posting_kind=SubledgerPostingKind.ENGINE_COMPUTE,
            idempotency_key="compute:a-line-without-a-subject",
            description="A posting whose second line names no subject",
            lines=[{subledger.SUBJECT_KEY: subject}, {}],
            require_subject_key=True,
        )
    assert _counts(world) == before
