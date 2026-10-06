"""A row that belongs to a contract and carries no entity is read through the contract, or the
line, that binds it (head R28-READS; supervisor ruling R-28, rows 1 to 3 of its remainder, and
the supervisor's rulings of 2026-10-02 on lane F-RPS-REG's measurement; 03 REQ-PLT-012; 04 §15.1
API-C-03, API-R-28, API-R-33, API-R-36, §16.1).

Three kinds of row carry no entity and were every member's to read, whatever they were about:

- a judgement record (T-CON-19) — read with the contract it names; the proposal of a combination
  (topic ``COMBINATION``) by a session that reads every contract it names; another record of a
  combination group with the group; a record that names no contract is the workspace's;
- a combination group (T-CON-03) — read through a contract the session reads that is or was a
  member of it, or that its proposal names; ``member_contract_ids`` holds the members the
  session reads and ``member_count`` says how many the group has in all;
- a posting (T-SL-01) read by id — read with a line the session reads, and its control totals
  are those of the entities whose lines the session reads.
The judgement register (RPT-28) states such a record by the same rule, with the run's entities
in the place of the session: a run is read by every member whose scope covers its entities.

Measured before the head (lane F-RPS-REG's probes, 2026-10-02), each as a member whose roles all
name ONE entity, against rows of another: Dee, Revenue Accountant of AVM-DE alone, listed both
judgement records of US01's contract with their conclusions and read each by id; listed and read
US01's combination group with its member contract; and read each of US01's four postings by id
with the seal's control totals. In the world of two entities each reader — of one order, of
the other, of a third entity — listed the group with both orders' ids and its proposal with the
conclusion "Combine NS-SO-AT-5001, NS-SO-DE-5004.", and a register run for AVM-DE stated it.

Worlds.
- ``reads``: ``worlds.ifrs_sw01`` — US01 keeps ASC606 and IFRS15; ``C-IFRS-SW01`` with two reviewed
  judgement records, computed in both books — and a second entity AVM-DE on the same calendar,
  made by Maya through the product. Dee is Revenue Accountant of AVM-DE alone.
- ``worlds.k04_saltmarsh``: ``SF-ORD-UK-2001`` is AVM-UK's and its first obligation is performed
  by AVM-US, so its postings hold lines of two entities. Uma is Revenue Accountant of AVM-US
  alone, Kay of AVM-UK alone, Dee of a third entity.
- ``pair`` of ``test_activation_suggestion_scope_db``: an order of AVM-DE and an order of AVM-AT of
  one customer group; Dee reads the German order, Ana the Austrian one, Bea both, Maya every
  entity; Cho is Revenue Accountant of a third entity, AVM-CH.
The scoped members' roles are assignment rows.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import (
    combination_group,
    customer,
    job,
    judgement_record,
    legal_entity,
    obligation,
    product,
    subledger_line,
    subledger_posting,
)
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.jobs.registry import run_job
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support import worlds
from support.db import TestDatabase
from support.principals import Actor, colleague, enrolled
from support.reference import approve, assign, entity, get, holding, patch, post
from support.worlds import _TASK_FETCHED, REPORT_RUN_ID_HEADER, REPORT_RUNS, ReportWorld
from tests.domain.contracts.test_activation_suggestion_scope_db import (  # noqa: F401 - fixture
    Pair,
    pair,
)
from tests.domain.contracts.test_combination import _k05

API: Final = "/api/v1"
OTHER: Final = "AVM-DE"
GROUPS: Final = f"{API}/combination-groups"
JUDGEMENTS: Final = f"{API}/judgements"
POSTINGS: Final = f"{API}/subledger-postings"
TOPIC: Final = "ESTIMATE_VS_ERROR"  # its questionnaire is evidence: no member is required


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def member_of(
    app: FastAPI, clock: FrozenClock, tenant_id: UUID, name: str, role_code: str, entity_id: UUID
) -> Actor:
    someone = colleague(tenant_id, name)
    assign(someone, role_code, entity_ids=[entity_id])
    return enrolled(app, clock, someone)


def another_entity(world: ReportWorld, like: UUID) -> UUID:
    """AVM-DE on the calendar of the entity ``like``, made by Maya through the product."""
    calendar_id = str(
        world.place.scalar(select(legal_entity.c.calendar_id).where(legal_entity.c.id == like))
    )
    created = entity(
        world.app,
        world.maya,
        code=OTHER,
        calendar_id=calendar_id,
        functional_currency="USD",
        time_zone="Europe/Berlin",
    )
    return UUID(str(created["id"]))


@dataclass(frozen=True, slots=True)
class Reads:
    world: ReportWorld
    contract_id: UUID
    group_id: UUID
    dee: Actor  # Revenue Accountant of AVM-DE alone: every row of the world is US01's


@pytest.fixture
def reads(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> Reads:
    world = worlds.ifrs_sw01(app, keyring, clock, files)
    de_id = another_entity(world, world.entity_id)
    booked = world.contracts[worlds.C_IFRS_SW01]
    dee = member_of(app, clock, world.tenant_id, "dee", "revenue_accountant", de_id)
    # the precondition of every case: nothing of US01 is hers to read
    assert get(app, f"{API}/contracts/{booked.contract['id']}", dee).status_code == 404
    assert get(app, f"{API}/subledger-lines", dee).json()["items"] == []
    return Reads(
        world=world,
        contract_id=UUID(str(booked.contract["id"])),
        group_id=UUID(str(booked.combination_group["id"])),
        dee=dee,
    )


def listed(app: FastAPI, path: str, actor: Actor, **query: str) -> list[dict[str, Any]]:
    answer = get(app, path, actor, {"limit": "200", **query})
    assert answer.status_code == 200, answer.text
    items: list[dict[str, Any]] = answer.json()["items"]
    return items


def record_body(subject_type: str, subject_id: Any, **more: Any) -> dict[str, Any]:
    return {
        "topic": TOPIC,
        "subject_type": subject_type,
        "subject_id": str(subject_id),
        "conclusion": "An estimate was revised; no error of a prior period.",
        "rationale": "The facts that changed arose after the period was reported.",
        **more,
    }


def stored_records(world: ReportWorld) -> list[dict[str, Any]]:
    return world.place.rows(select(judgement_record).order_by(judgement_record.c.judgement_no))


def test_a_judgement_record_is_read_with_the_contract_it_names(reads: Reads) -> None:
    """``GET /judgements`` and ``GET /judgements/{id}``. Both records of ``C-IFRS-SW01`` name the
    contract: Maya lists and reads them as before; Dee, who does not read the contract, is listed
    none — with the filter of that contract as without — and answered 404 for each. Before: Dee
    listed both with their conclusions and read each by id."""
    app, world = reads.world.app, reads.world
    stored = stored_records(world)
    assert [row["contract_id"] for row in stored] == [reads.contract_id, reads.contract_id]
    ids = sorted(str(row["id"]) for row in stored)
    of_contract = {"subject_type": "contract", "subject_id": str(reads.contract_id)}

    assert sorted(item["id"] for item in listed(app, JUDGEMENTS, world.maya)) == ids
    assert listed(app, JUDGEMENTS, reads.dee) == []
    assert listed(app, JUDGEMENTS, reads.dee, **of_contract) == []
    for record_id in ids:
        assert get(app, f"{JUDGEMENTS}/{record_id}", world.maya).status_code == 200
        assert get(app, f"{JUDGEMENTS}/{record_id}", reads.dee).status_code == 404


def test_a_judgement_record_is_not_written_for_a_group_the_caller_does_not_read(
    reads: Reads,
) -> None:
    """``POST /judgements`` with a combination group as its subject. Dee holds
    ``judgement.create`` for AVM-DE and reads no contract of US01's group: 404, and nothing is
    stored. Maya, who reads the contract, writes the record. Before: Dee's was taken (201)."""
    app, world = reads.world.app, reads.world
    before = [row["id"] for row in stored_records(world)]

    refused = post(app, JUDGEMENTS, reads.dee, record_body("combination_group", reads.group_id))
    assert refused.status_code == 404, refused.text
    assert [row["id"] for row in stored_records(world)] == before

    written = post(app, JUDGEMENTS, world.maya, record_body("combination_group", reads.group_id))
    assert written.status_code == 201, written.text
    assert get(app, f"{JUDGEMENTS}/{written.json()['id']}", reads.dee).status_code == 404


def test_a_judgement_record_does_not_supersede_one_the_caller_does_not_read(
    reads: Reads,
) -> None:
    """``POST /judgements`` with ``supersedes_id``. Dee names a record of US01's contract as the
    one her record of a product replaces: 404, and nothing is stored. Before: 201, with the id
    of the other entity's record stored on hers."""
    app, world = reads.world.app, reads.world
    before = stored_records(world)
    (service,) = world.place.rows(select(product.c.id).where(product.c.code == "SVC-12M"))
    body = record_body("product", service["id"], supersedes_id=str(before[0]["id"]))

    refused = post(app, JUDGEMENTS, reads.dee, body)
    assert refused.status_code == 404, refused.text
    assert [row["id"] for row in stored_records(world)] == [row["id"] for row in before]

    replaced = post(app, JUDGEMENTS, world.maya, body)
    assert replaced.status_code == 201, replaced.text
    assert replaced.json()["supersedes_id"] == str(before[0]["id"])


def test_a_draft_of_a_contract_is_read_and_changed_by_a_reader_of_the_contract(
    reads: Reads,
) -> None:
    """``GET``, ``PATCH /judgements/{id}`` and ``POST /judgements/{id}/submit`` of a DRAFT Maya
    wrote for US01's contract: Dee is answered 404 for each, and the draft is as Maya left it.
    Before: her ``GET`` answered 200 with the conclusion; the two commands answered 404 already
    (their first read of the contract)."""
    app, world, dee = reads.world.app, reads.world, reads.dee
    drafted = post(app, JUDGEMENTS, world.maya, record_body("contract", reads.contract_id))
    assert drafted.status_code == 201, drafted.text
    draft = f"{JUDGEMENTS}/{drafted.json()['id']}"

    assert get(app, draft, dee).status_code == 404
    changed = patch(
        app, draft, dee, {"conclusion": "A conclusion rewritten by Dee."}, if_match=None
    )
    assert changed.status_code == 404, changed.text
    sent = post(app, f"{draft}/submit", dee, {"comment": "Review"})
    assert sent.status_code == 404, sent.text

    shown = get(app, draft, world.maya)
    assert shown.status_code == 200, shown.text
    assert (shown.json()["status"], shown.json()["conclusion"]) == (
        "DRAFT",
        "An estimate was revised; no error of a prior period.",
    )


def test_a_judgement_record_is_not_written_for_a_contract_the_caller_does_not_read(
    reads: Reads,
) -> None:
    """``POST /judgements`` for US01's contract, for an obligation of it and for a product with
    that contract: 404 each for Dee, and nothing is stored. These answered 404 before the head
    as well — the command's first read is the contract — and are held here beside the cases
    the head closes."""
    app, world = reads.world.app, reads.world
    before = [row["id"] for row in stored_records(world)]
    (line,) = world.place.rows(
        select(obligation.c.id).where(obligation.c.contract_id == reads.contract_id)
    )
    (service,) = world.place.rows(select(product.c.id).where(product.c.code == "SVC-12M"))
    for body in (
        record_body("contract", reads.contract_id),
        record_body("obligation", line["id"]),
        record_body("product", service["id"], contract_id=str(reads.contract_id)),
    ):
        refused = post(app, JUDGEMENTS, reads.dee, body)
        assert refused.status_code == 404, (body["subject_type"], refused.text)
    assert [row["id"] for row in stored_records(world)] == before


def test_a_record_that_names_no_contract_stays_the_workspaces(reads: Reads) -> None:
    """A record of a product that names no contract is about no entity's contract: Dee lists it
    — alone, of the three records stored — reads it by id, and writes one herself, which Maya
    reads. Unchanged by the head, but for the two records of US01's contract she no longer
    lists."""
    app, world, dee = reads.world.app, reads.world, reads.dee
    (service,) = world.place.rows(select(product.c.id).where(product.c.code == "SVC-12M"))
    made = post(app, JUDGEMENTS, world.maya, record_body("product", service["id"]))
    assert made.status_code == 201, made.text
    record_id = made.json()["id"]
    assert made.json()["contract_id"] is None

    assert [item["id"] for item in listed(app, JUDGEMENTS, dee)] == [record_id]
    assert get(app, f"{JUDGEMENTS}/{record_id}", dee).status_code == 200
    own = post(app, JUDGEMENTS, dee, record_body("product", service["id"]))
    assert own.status_code == 201, own.text
    assert get(app, f"{JUDGEMENTS}/{own.json()['id']}", world.maya).status_code == 200
    assert len(listed(app, JUDGEMENTS, world.maya)) == 4


def test_a_combination_group_is_read_through_a_contract_the_session_reads(reads: Reads) -> None:
    """``GET /combination-groups``, ``GET /combination-groups/{id}`` and ``POST
    /combination-groups/{id}/submit``. The group of ``C-IFRS-SW01`` has one member, which Dee does
    not read: she is listed no group — with the filter of that contract as without — and
    answered 404 by id and for the command; Maya is listed it with its member, one member in
    all. Before: Dee listed the group with the contract's id and read it by id."""
    app, world = reads.world.app, reads.world
    of_contract = {"contract": str(reads.contract_id)}
    assert listed(app, GROUPS, reads.dee) == []
    assert listed(app, GROUPS, reads.dee, **of_contract) == []
    assert get(app, f"{GROUPS}/{reads.group_id}", reads.dee).status_code == 404
    assert post(app, f"{GROUPS}/{reads.group_id}/submit", reads.dee, {}).status_code == 404

    (mine,) = listed(app, GROUPS, world.maya)
    assert (mine["id"], mine["member_contract_ids"], mine["member_count"]) == (
        str(reads.group_id),
        [str(reads.contract_id)],
        1,
    )
    assert [item["id"] for item in listed(app, GROUPS, world.maya, **of_contract)] == [mine["id"]]
    assert get(app, f"{GROUPS}/{reads.group_id}", world.maya).status_code == 200


def group_as(app: FastAPI, actor: Actor, group_id: str) -> dict[str, Any]:
    answer = get(app, f"{GROUPS}/{group_id}", actor)
    assert answer.status_code == 200, answer.text
    body: dict[str, Any] = answer.json()
    return body


def own_group(app: FastAPI, actor: Actor, contract_id: UUID) -> dict[str, Any]:
    """``combination_group`` of ``GET /contracts/{id}``."""
    answer = get(app, f"{API}/contracts/{contract_id}", actor)
    assert answer.status_code == 200, answer.text
    group: dict[str, Any] = answer.json()["combination_group"]
    return group


@pytest.mark.slow
def test_a_group_of_two_entities_names_to_each_reader_the_members_it_reads(
    pair: Pair,  # noqa: F811
) -> None:
    """An order of AVM-DE and an order of AVM-AT are proposed for combination by Maya, and the
    combination is approved. The reader of one order reads the group — her order among the
    contracts of the proposal, then among the members, with the count of all — and neither the
    other order's id nor the ``COMBINATION`` record, whose conclusion names both orders; her
    ``GET /contracts/{id}`` states ``combination_group`` the same way, and the list's filter
    finds nothing for the order she does not read. A member of both entities reads both
    members and the record. A member of a third entity is listed no group. Before: each of
    them listed the group with both ids and the record with its conclusion."""
    app, world = pair.app, pair.world
    de, at = str(pair.de_contract), str(pair.at_contract)
    (swiss,) = world.place.rows(select(legal_entity.c.id).where(legal_entity.c.code == "AVM-CH"))
    cho = holding(
        app, colleague(world.place.tenant_id, "cho"), "revenue_accountant", entity_ids=[swiss["id"]]
    )
    proposed = post(
        app,
        GROUPS,
        pair.maya,
        {
            "contract_ids": [de, at],
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: both orders serve a single commercial objective.",
        },
    )
    assert proposed.status_code == 201, proposed.text
    group_id = proposed.json()["id"]
    record_id = proposed.json()["proposal"]["judgement_record_id"]
    (record,) = world.place.rows(
        select(judgement_record).where(judgement_record.c.id == UUID(record_id))
    )
    assert (record["contract_id"], record["conclusion"]) == (
        None,
        "Combine NS-SO-AT-5001, NS-SO-DE-5004.",
    )
    one_reader = ((pair.dee, de, at), (pair.ana, at, de))

    # proposed: no member yet; the contracts of the proposal, and how many it names
    for actor, own, other in one_reader:
        assert other not in get(app, GROUPS, actor, {"limit": "200"}).text
        assert record_id not in [item["id"] for item in listed(app, JUDGEMENTS, actor)]
        assert get(app, f"{JUDGEMENTS}/{record_id}", actor).status_code == 404
        shown = group_as(app, actor, group_id)
        assert (shown["status"], shown["member_contract_ids"], shown["member_count"]) == (
            "PROPOSED",
            [],
            0,
        )
        assert (shown["proposal"]["contract_ids"], shown["proposal"]["contract_count"]) == (
            [own],
            2,
        )
        assert group_id in [item["id"] for item in listed(app, GROUPS, actor)]
    for actor in (pair.bea, pair.maya):
        shown = group_as(app, actor, group_id)
        assert sorted(shown["proposal"]["contract_ids"]) == sorted([de, at])
        assert shown["proposal"]["contract_count"] == 2
        assert get(app, f"{JUDGEMENTS}/{record_id}", actor).status_code == 200
    assert listed(app, GROUPS, cho) == []
    assert get(app, f"{GROUPS}/{group_id}", cho).status_code == 404
    assert listed(app, JUDGEMENTS, cho) == []

    submitted = post(app, f"{GROUPS}/{group_id}/submit", pair.maya, {})
    assert submitted.status_code == 200, submitted.text
    approved = approve(app, submitted.json()["approval_request_id"], world.marcus)
    assert approved.status_code == 200, approved.text
    status = world.place.scalar(
        select(combination_group.c.status).where(combination_group.c.id == UUID(group_id))
    )
    assert str(status) == "APPLIED"

    # applied: the members a reader reads, and how many the group has in all
    for actor, own, other in one_reader:
        shown = group_as(app, actor, group_id)
        assert (shown["member_contract_ids"], shown["member_count"]) == ([own], 2)
        of_own = own_group(app, actor, UUID(own))
        assert (of_own["id"], of_own["is_singleton"]) == (group_id, False)
        assert (of_own["member_contract_ids"], of_own["member_count"]) == ([own], 2)
        assert [item["id"] for item in listed(app, GROUPS, actor, contract=own)] == [group_id]
        assert listed(app, GROUPS, actor, contract=other) == []
        assert other not in get(app, GROUPS, actor, {"limit": "200"}).text
        assert get(app, f"{JUDGEMENTS}/{record_id}", actor).status_code == 404
    for actor in (pair.bea, pair.maya):
        shown = group_as(app, actor, group_id)
        assert (sorted(shown["member_contract_ids"]), shown["member_count"]) == (
            sorted([de, at]),
            2,
        )
        assert sorted(own_group(app, actor, pair.de_contract)["member_contract_ids"]) == sorted(
            [de, at]
        )
        assert [item["id"] for item in listed(app, GROUPS, actor, contract=at)] == [group_id]
        assert get(app, f"{JUDGEMENTS}/{record_id}", actor).status_code == 200
    assert listed(app, GROUPS, cho) == []
    assert get(app, f"{GROUPS}/{group_id}", cho).status_code == 404


def proposed_combination(app: FastAPI, actor: Actor, contract_ids: Sequence[str]) -> str:
    """``POST /combination-groups``: the judgement number of the proposal's record."""
    made = post(
        app,
        GROUPS,
        actor,
        {
            "contract_ids": list(contract_ids),
            "criterion": "606-10-25-9(b)",
            "rationale": "One package: the orders serve a single commercial objective.",
        },
    )
    assert made.status_code == 201, made.text
    record = get(app, f"{JUDGEMENTS}/{made.json()['proposal']['judgement_record_id']}", actor)
    assert record.status_code == 200, record.text
    return str(record.json()["judgement_no"])


def register_run(
    app: FastAPI, runtime: JobRuntime, tenant_id: UUID, actor: Actor, codes: Sequence[str]
) -> tuple[str, list[str], dict[str, Any]]:
    """``POST /report-runs`` of the judgement register for ``codes`` as ``actor``, its job run as
    the worker runs it: (run id, the judgement numbers it states, its control totals)."""
    started = post(
        app,
        REPORT_RUNS,
        actor,
        {
            "report_code": "judgement_register",
            "parameters": {"entity_codes": list(codes), "book": "ASC606"},
            "output_format": "JSON",
        },
    )
    assert started.status_code == 202, started.text
    run_id = started.headers[REPORT_RUN_ID_HEADER]
    job_id = UUID(str(started.json()["id"]))
    with tenant_session(DbContext(tenant_id=tenant_id, user_id=None, entity_scope="*")) as session:
        task_id = session.execute(
            select(job.c.procrastinate_job_id).where(job.c.id == job_id)
        ).scalar_one()
        session.execute(_TASK_FETCHED, {"id": task_id})
    run_job(job_id, tenant_id, attempt=1, runtime=runtime)
    numbers, totals = stated_by(app, actor, run_id)
    return run_id, numbers, totals


def stated_by(app: FastAPI, actor: Actor, run_id: str) -> tuple[list[str], dict[str, Any]]:
    """What ``actor`` reads of a finished run: the judgement numbers and the control totals."""
    shown = get(app, f"{REPORT_RUNS}/{run_id}", actor)
    assert shown.status_code == 200, shown.text
    assert shown.json()["status"] == "SUCCEEDED", shown.text
    rows = get(app, f"{REPORT_RUNS}/{run_id}/data", actor, {"limit": "200"})
    assert rows.status_code == 200, rows.text
    totals: dict[str, Any] = shown.json()["control_totals"]
    return [str(item["judgement_no"]) for item in rows.json()["items"]], totals


@pytest.mark.slow
def test_the_register_states_a_proposal_in_a_run_that_holds_every_contract_it_names(
    pair: Pair,  # noqa: F811
    keyring: KeyRing,
    clock: FrozenClock,
    files: LocalFileStore,
) -> None:
    """RPT-28 ``judgement_register``. Two proposals of a combination: one across an order of
    AVM-DE and an order of AVM-AT, one of two Austrian orders. A run for AVM-DE states neither —
    the first is counted, because the run holds one of its two contracts: ``record_count`` 1
    beside ``row_count`` 0 — whether a member of all entities or of AVM-DE alone runs it, and the
    member of AVM-DE reads the other's run as her own. The run for AVM-AT states the Austrian
    proposal and counts the other; the run for both entities states both. Before: every run
    stated both proposals with their conclusions."""
    app, world = pair.app, pair.world
    tenant_id = world.place.tenant_id
    runtime = JobRuntime(clock=clock, keyring=keyring, files=files)
    (buyer,) = world.place.rows(select(customer.c.id).where(customer.c.code == "C-05"))
    more: list[str] = []
    for external_id in ("NS-SO-AT-5002", "NS-SO-AT-5003"):
        booked = post(
            app,
            f"{API}/contracts",
            pair.maya,
            {**_k05(buyer["id"]), "external_id": external_id, "contracting_entity_code": "AVM-AT"},
        )
        assert booked.status_code == 201, booked.text
        more.append(str(booked.json()["id"]))
    across = proposed_combination(app, pair.maya, [str(pair.de_contract), str(pair.at_contract)])
    austrian = proposed_combination(app, pair.maya, more)

    def totals_of(found: dict[str, Any]) -> tuple[int, int]:
        return int(found["row_count"]), int(found["record_count"])

    german_run, numbers, totals = register_run(app, runtime, tenant_id, pair.maya, ["AVM-DE"])
    assert numbers == []  # before the head: both proposals, with their conclusions
    assert totals_of(totals) == (0, 1)
    _, numbers, totals = register_run(app, runtime, tenant_id, pair.dee, ["AVM-DE"])
    assert (numbers, totals_of(totals)) == ([], (0, 1))
    numbers, totals = stated_by(app, pair.dee, german_run)  # Maya's run, opened by Dee
    assert (numbers, totals_of(totals)) == ([], (0, 1))

    _, numbers, totals = register_run(app, runtime, tenant_id, pair.maya, ["AVM-AT"])
    assert (numbers, totals_of(totals)) == ([austrian], (1, 2))
    _, numbers, totals = register_run(app, runtime, tenant_id, pair.ana, ["AVM-AT"])
    assert (numbers, totals_of(totals)) == ([austrian], (1, 2))
    _, numbers, totals = register_run(app, runtime, tenant_id, pair.maya, ["AVM-DE", "AVM-AT"])
    assert (numbers, totals_of(totals)) == (sorted([across, austrian]), (2, 2))


def test_a_posting_is_read_with_a_line_the_session_reads(reads: Reads) -> None:
    """``GET /subledger-postings/{id}``. Every line of US01's postings is US01's: Maya reads each
    posting with its seal; Dee is answered 404 for each. Before: Dee read each with the seal's
    control totals by entity and period."""
    app, world = reads.world.app, reads.world
    postings = [str(row["id"]) for row in world.place.rows(select(subledger_posting.c.id))]
    assert len(postings) >= 2
    for posting_id in postings:
        mine = get(app, f"{POSTINGS}/{posting_id}", world.maya)
        assert mine.status_code == 200, mine.text
        assert mine.json()["seal"]["control_totals"]
        assert get(app, f"{POSTINGS}/{posting_id}", reads.dee).status_code == 404


@dataclass(frozen=True, slots=True)
class Shared:
    """WLD-K-04 with its posting of two entities and a reader of each kind."""

    app: FastAPI
    us: str
    uk: str
    posting: str  # the path of a posting with lines of AVM-US and of AVM-UK
    lines: int  # the lines of that posting, of both entities
    maya: Actor  # all entities
    uma: Actor  # AVM-US alone
    kay: Actor  # AVM-UK alone
    dee: Actor  # a third entity: none of the posting's lines is hers


@pytest.fixture
def shared(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> Shared:
    world = worlds.k04_saltmarsh(app, keyring, clock, files)
    report = world.report
    de_id = another_entity(report, world.us_entity_id)
    counted = report.place.rows(
        select(
            subledger_line.c.subledger_posting_id,
            func.count(func.distinct(subledger_line.c.entity_id)).label("entities"),
            func.count().label("lines"),
        ).group_by(subledger_line.c.subledger_posting_id)
    )
    mixed = [row for row in counted if int(row["entities"]) == 2]
    assert mixed, counted  # the world's point: a posting with lines of two entities
    tenant_id = report.tenant_id
    return Shared(
        app=app,
        us=str(world.us_entity_id),
        uk=str(world.uk_entity_id),
        posting=f"{POSTINGS}/{mixed[0]['subledger_posting_id']}",
        lines=int(mixed[0]["lines"]),
        maya=report.maya,
        uma=member_of(app, clock, tenant_id, "uma", "revenue_accountant", world.us_entity_id),
        kay=member_of(app, clock, tenant_id, "kay", "revenue_accountant", world.uk_entity_id),
        dee=member_of(app, clock, tenant_id, "dee", "revenue_accountant", de_id),
    )


def test_a_posting_of_two_entities_states_the_totals_of_the_entities_the_session_reads(
    shared: Shared,
) -> None:
    """WLD-K-04: a posting with lines of AVM-US and of AVM-UK. Uma, of AVM-US alone, and Kay, of
    AVM-UK alone, each read it — each reads a line of it — with the control totals of the own
    entity alone; Maya reads the totals of both. The seal's line count is the whole posting's
    for every reader. Before: each read the totals of both entities."""

    def totals_of(actor: Actor) -> set[str]:
        answer = get(shared.app, shared.posting, actor)
        assert answer.status_code == 200, answer.text
        seal = answer.json()["seal"]
        assert seal["line_count"] == shared.lines
        return {str(item["entity_id"]) for item in seal["control_totals"]}

    assert totals_of(shared.maya) == {shared.us, shared.uk}
    assert totals_of(shared.uma) == {shared.us}
    assert totals_of(shared.kay) == {shared.uk}


def test_a_posting_of_two_entities_is_not_read_by_a_member_of_a_third(shared: Shared) -> None:
    """WLD-K-04: Dee, Revenue Accountant of a third entity, reads no line of the posting and is
    answered 404 for it. Before: 200, with the control totals of AVM-US and of AVM-UK."""
    assert get(shared.app, f"{API}/subledger-lines", shared.dee).json()["items"] == []
    assert get(shared.app, shared.posting, shared.dee).status_code == 404
    assert get(shared.app, shared.posting, shared.maya).status_code == 200
