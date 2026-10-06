"""Item SUBLEDGER-LINE-JOURNAL-RUN-1 (register index 265; 04 T-SL-06 drill-back, rev 1.288; the
supervisor's ruling of 2026-10-02 on the lane's measurement): the drill of a journal line names
the lines its run summarized — by the run's own record, not by the holds' timestamps.

A calculation leaves out the lines of the contracts whose ``journal_export`` hold is open in its
transaction and records their ids (the ``CALCULATE`` event; the completeness assertion reads that
record). The drill decided afterwards by timestamps — held when ``applied_at`` is not after the
run's ``created_at`` and ``released_at`` is null or later — so where a hold or a release shares
the run's instant the two answers parted: PRODUCT DEFECT, measured through the product on
2 October 2026 in both directions.

World: the CLO-8 journal world with CHK-022's January postings of ``Contract 1`` of Mock Entity 1
and postings of another contract of that entity on the same accounts; default grain, so both
contracts' lines fall into one journal line an account. The clock stands still.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any, Final
from uuid import UUID, uuid4

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import contract, contract_hold, journal_batch, subledger_line
from erev_api.db.tables.platform import audit_event, file_object
from erev_api.domain.contracts import holds
from erev_api.domain.journals import completeness, queries, summarise, validation
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.schemas.events import HoldApplyIn, HoldReleaseIn
from erev_api.uow import UnitOfWork
from fastapi import FastAPI
from sqlalchemy import select
from support.db import TestDatabase
from support.reference import get, slug
from support.worlds import (
    ENTITY_1,
    FEBRUARY,
    JANUARY,
    JournalWorld,
    calculated_run,
    journal_world,
    post_chk_022,
    post_lines,
)

GRAIN: Final = "ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS"
HELD: Final = "Contract 1"
LIABILITY, REVENUE = "21001", "5001"


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def world(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> Iterator[JournalWorld]:
    built = journal_world(app, keyring, clock, files)
    post_chk_022(built)
    yield built


def _other(world: JournalWorld) -> str:
    """Another contract of the held contract's entity."""
    held = world.contracts[HELD]
    return next(
        key
        for key, item in world.contracts.items()
        if key != HELD and item.entity_id == held.entity_id
    )


def _posted(world: JournalWorld, key: str, contract_key: str, amount: str, **where: Any) -> None:
    """Dr contract liability 21001 / Cr revenue 5001 of POB #1, ``amount`` USD."""
    post_lines(
        world,
        key=key,
        contract_key=contract_key,
        entries=[
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", LIABILITY, amount, "POB #1"),
                    ("REVENUE", REVENUE, f"-{amount}", "POB #1"),
                ],
            )
        ],
        **where,
    )


def _head(world: JournalWorld, contract_id: UUID) -> int:
    return int(
        world.legacy.imports.scalar(
            select(contract.c.head_stream_version).where(contract.c.id == contract_id)
        )
    )


def _hold(world: JournalWorld) -> None:
    held = world.contracts[HELD]
    with world.legacy.place().uow() as uow:
        holds.apply_hold(
            uow,
            contract_id=held.id,
            expected_stream_version=_head(world, held.id),
            body=HoldApplyIn(hold_type="journal_export", reason="Customer dispute on INV-C1"),
        )
        uow.commit()


def _release(world: JournalWorld) -> None:
    held = world.contracts[HELD]
    hold_id = world.legacy.imports.scalar(
        select(contract_hold.c.id).where(
            contract_hold.c.contract_id == held.id, contract_hold.c.released_at.is_(None)
        )
    )
    with world.legacy.place().uow() as uow:
        holds.release_hold(
            uow,
            contract_id=held.id,
            expected_stream_version=_head(world, held.id),
            body=HoldReleaseIn(hold_id=hold_id, comment="Dispute settled"),
        )
        uow.commit()


def _drilled(world: JournalWorld, line: dict[str, Any]) -> list[tuple[str, str]]:
    """(contract, amount) of the lines a journal line drills to, by amount."""
    answered = get(world.app, line["links"]["drill"], world.legacy.maya, {"limit": 200})
    assert answered.status_code == 200, answered.text
    return sorted(
        (
            (item["contract_external_id"], item["amount_txn"]["amount"])
            for item in answered.json()["items"]
        ),
        key=lambda pair: Decimal(pair[1]),
    )


def _ties(line: dict[str, Any], drilled: list[tuple[str, str]]) -> None:
    """The drilled lines are the ones the journal line summarizes: as many, and to its amount."""
    net = Decimal(line["debit_txn"]["amount"]) - Decimal(line["credit_txn"]["amount"])
    assert sum(Decimal(amount) for _, amount in drilled) == net, (line["account"]["code"], drilled)
    assert len(drilled) == line["source_line_count"], (line["account"]["code"], drilled)


@pytest.mark.slow
def test_the_drill_leaves_out_what_the_run_left_out_though_the_hold_was_released_at_its_instant(
    world: JournalWorld, clock: FrozenClock
) -> None:
    """Hold, calculation and release at one instant. The run left ``Contract 1``'s six lines out
    and recorded them; its two journal lines summarize the other contract's posting alone, and
    their drill names that posting's lines and no other. By the timestamps the hold was already
    released at the run's instant, and the drill of 21001 named four lines — 128.84, 118.53 and
    48.32 of ``Contract 1`` beside the 12.00 the journal line holds."""
    other = _other(world)
    _posted(world, "drill-record-jan", other, "12.00")
    at = clock.now()
    _hold(world)
    run, lines = calculated_run(world, entity=ENTITY_1, grain=GRAIN)
    _release(world)
    assert clock.now() == at  # one instant
    by_account = {line["account"]["code"]: line for line in lines}
    assert sorted(by_account) == [LIABILITY, REVENUE] and run["state"] == "draft"
    assert _drilled(world, by_account[LIABILITY]) == [(other, "12.00")]
    assert _drilled(world, by_account[REVENUE]) == [(other, "-12.00")]
    for line in lines:
        _ties(line, _drilled(world, line))


@pytest.mark.slow
def test_the_drill_names_what_the_run_summarized_though_a_hold_was_applied_at_its_instant(
    world: JournalWorld, clock: FrozenClock
) -> None:
    """Calculation and hold at one instant, in that order: the run summarized both contracts'
    February postings — 37.00 a line, two source lines each — and the hold came after it. By the
    timestamps ``Contract 1`` was held at the run's instant, and the drill of 21001 named one
    line, 7.00, of the two the journal line holds."""
    other = _other(world)
    _posted(world, "drill-record-feb-held", HELD, "30.00", period_key=FEBRUARY)
    _posted(world, "drill-record-feb-other", other, "7.00", period_key=FEBRUARY)
    at = clock.now()
    _run, lines = calculated_run(world, entity=ENTITY_1, grain=GRAIN, period_key=FEBRUARY)
    _hold(world)
    assert clock.now() == at  # one instant
    by_account = {line["account"]["code"]: line for line in lines}
    assert sorted(by_account) == [LIABILITY, REVENUE]
    assert _drilled(world, by_account[LIABILITY]) == [(other, "7.00"), (HELD, "30.00")]
    assert _drilled(world, by_account[REVENUE]) == [(HELD, "-30.00"), (other, "-7.00")]
    for line in lines:
        _ties(line, _drilled(world, line))


# --- a run of before the recorded ids: its record is its held detail file -------------------------

UNREADABLE: Final = (
    "Journal run {run} cannot be traced to its source lines: the record of the lines it left out "
    "cannot be read."
)


def _run_of_before_the_ids(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """A run calculated as before its event recorded the ids: the product calculates it, and
    its CALCULATE event is written without ``held_subledger_line_ids`` — it counts the held
    lines and names the held detail file, which is then the run's only record of them."""
    real = UnitOfWork.audit

    def without_the_ids(self: UnitOfWork, **kwargs: Any) -> None:
        if kwargs.get("action") == summarise.CALCULATE_ACTION:
            after = {
                key: value
                for key, value in kwargs["after"].items()
                if key != "held_subledger_line_ids"
            }
            kwargs = {**kwargs, "after": after}
        real(self, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(UnitOfWork, "audit", without_the_ids)
        return calculated_run(world, entity=ENTITY_1, grain=GRAIN)


def _calculate_event(world: JournalWorld, run_id: UUID) -> dict[str, Any]:
    (row,) = world.legacy.imports.rows(
        select(audit_event.c.after).where(
            audit_event.c.action == summarise.CALCULATE_ACTION, audit_event.c.object_id == run_id
        )
    )
    return dict(row["after"])


def _gate(world: JournalWorld) -> completeness.CompletenessResult:
    period_id, _ = world.periods[JANUARY]
    with world.legacy.place().uow() as uow:
        return completeness.assert_completeness(uow, world.entities[ENTITY_1], "ASC606", period_id)


@pytest.mark.slow
def test_a_run_whose_ids_come_from_its_file_answers_the_gate_the_member_and_the_drill_alike(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The run left ``Contract 1``'s six lines out under a hold and its event names no ids: its
    held detail file is its record. A reader of that record that is handed neither the file
    store nor the key ring cannot read it; the gate hands both and reads the six lines as held —
    and so does the drill's route, whose answer is the lines the run summarized. One record, one
    answer."""
    other = _other(world)
    _posted(world, "drill-record-file", other, "12.00")
    _hold(world)
    run, lines = _run_of_before_the_ids(world, monkeypatch)
    run_id = UUID(run["id"])
    after = _calculate_event(world, run_id)
    assert "held_subledger_line_ids" not in after
    assert (after["counts"]["held_lines"], after["held_detail_file_id"] is None) == (6, False)

    with world.legacy.place().uow() as uow:
        assert completeness.run_exclusions(uow.session, [run_id]) == {run_id: None}
        read = completeness.run_exclusions(
            uow.session, [run_id], files=uow.files, keyring=uow.keyring
        )
    left_out = read[run_id]
    assert left_out is not None and len(left_out) == 6
    found = _gate(world)
    assert found.unverifiable_runs == ()
    assert {item.subledger_line_id for item in found.held} == left_out and found.uncovered == ()

    by_account = {line["account"]["code"]: line for line in lines}
    assert _drilled(world, by_account[LIABILITY]) == [(other, "12.00")]
    assert _drilled(world, by_account[REVENUE]) == [(other, "-12.00")]
    for line in lines:
        _ties(line, _drilled(world, line))
    # the member, on the register: the lines the run left out name no run and the lines it
    # summarized name it — read from the same file, which the route hands on as the gate does
    assert _named(world) == {(HELD, None), (other, run["id"])}


def _named(world: JournalWorld) -> set[tuple[str, str | None]]:
    """(contract, ``journal_run_id``) of January's lines of Mock Entity 1 on the register."""
    register = get(
        world.app,
        "/api/v1/subledger-lines",
        world.legacy.maya,
        {"entity": ENTITY_1, "period": JANUARY, "limit": 200},
    )
    assert register.status_code == 200, register.text
    assert len(register.json()["items"]) == 8
    return {
        (item["contract_external_id"], item["journal_run_id"]) for item in register.json()["items"]
    }


@pytest.mark.slow
def test_the_drill_of_a_run_whose_record_cannot_be_read_is_refused(
    world: JournalWorld, monkeypatch: pytest.MonkeyPatch, app_settings: Settings
) -> None:
    """The same run with its held detail file gone: nothing says which lines it left out. The
    gate names the run and counts nothing of its range as journalised, no line of the range
    names the run (``journal_run_id`` null), and the drill of its journal lines answers 409
    ``invalid-transition`` under rule ``RUN_RECORD_UNREADABLE`` (PRD ERR-101) by the run's
    number, where the timestamps of the holds would have answered lines by a guess."""
    other = _other(world)
    _posted(world, "drill-record-gone", other, "12.00")
    _hold(world)
    run, lines = _run_of_before_the_ids(world, monkeypatch)
    run_id = UUID(run["id"])
    file_id = UUID(str(_calculate_event(world, run_id)["held_detail_file_id"]))
    (stored,) = world.legacy.imports.rows(
        select(file_object.c.storage_key).where(file_object.c.id == file_id)
    )
    Path(app_settings.file_root).joinpath(*str(stored["storage_key"]).split("/")).unlink()

    found = _gate(world)
    assert found.unverifiable_runs == (run_id,)
    # the run journalises nothing: no line of its range names it
    assert _named(world) == {(HELD, None), (_other(world), None)}
    sentence = UNREADABLE.format(run=run["run_no"])
    for line in lines:
        refused = get(world.app, line["links"]["drill"], world.legacy.maya, {"limit": 200})
        assert refused.status_code == 409, refused.text  # 200 with lines, before the item
        assert slug(refused) == "invalid-transition"
        assert refused.json()["detail"] == sentence
        assert [
            (item["field"], item["rule_id"], item["message"]) for item in refused.json()["errors"]
        ] == [(None, "RUN_RECORD_UNREADABLE", sentence)]


# --- the ids of a drill: one bound value whatever their number ---------------------------------


@pytest.mark.slow
def test_the_drills_statements_run_over_more_lines_than_can_be_bound_one_by_one(
    world: JournalWorld,
) -> None:
    """The independent review's point 10, measured through the product on 2026-10-02: a journal
    line of 66,000 source lines could not be drilled. The page's statement bound one value an id,
    the driver refuses a statement of more than 65,535 bound values, the kernel read an
    unavailable server, and the drill answered 503. The two statements that are handed the ids
    of subledger lines now bind them as one array (``summarise.among``): over 70,000 ids each
    runs, and finds among them the world's own six lines."""
    held = world.contracts[HELD]
    period_id, _ = world.periods[JANUARY]
    with world.legacy.place().uow() as uow:
        session = uow.session
        own = sorted(
            session.execute(
                select(subledger_line.c.id).where(subledger_line.c.contract_id == held.id)
            ).scalars(),
            key=str,
        )
        assert len(own) == 6
        ids = [*own, *(uuid4() for _ in range(70_000))]
        page = session.execute(queries.drill_statement(ids)).mappings().all()
        assert sorted((row["id"] for row in page), key=str) == own
        taken = summarise.detail_lines(
            session,
            summarise.left_out_statement(
                entity_id=held.entity_id,
                book_codes=["ASC606", "LEGACY"],
                period_id=period_id,
                line_ids=ids,
            ),
        )
        assert sorted((line.id for line in taken), key=str) == own


@pytest.mark.slow
def test_the_calculation_the_runs_list_and_the_findings_bind_their_ids_as_one_value(
    world: JournalWorld,
) -> None:
    """Three more statements of the package were handed ids with no bound on their number and
    bound them one value an id (read on 2026-10-02, once the drill's bound was measured; the
    supervisor's word of that day): the open holds of the contracts of a run's range — on the
    path of every calculation of a journal run —, the acknowledgements of the chunks of a page
    of runs, and the names of the contracts and obligations of a failed generation's findings.
    Each runs over 70,000 ids and finds the world's own row among them. Before, each ended in
    the driver's refusal: "number of parameters must be between 0 and 65535"."""
    held = world.contracts[HELD]
    _posted(world, "bound-other", _other(world), "12.00")
    _hold(world)
    run, _ = calculated_run(world, entity=ENTITY_1, grain=GRAIN)
    many = [uuid4() for _ in range(70_000)]
    outcome: dict[str, Any] = {}

    def attempt(name: str, call: Any) -> None:
        """Each statement in a unit of work of its own: a refusal of one says nothing of the
        next, and its words are kept."""
        try:
            with world.legacy.place().uow() as uow:
                outcome[name] = call(uow.session)
        except Exception as error:
            outcome[name] = f"{type(error).__name__}: {' '.join(str(error).split())[:200]}"

    def holds(session: Any) -> bool:
        return sorted(summarise.open_holds(session, [held.id, *many])) == [held.id]

    def chunks(session: Any) -> bool:
        (real,) = [
            dict(row)
            for row in session.execute(
                select(journal_batch).where(journal_batch.c.journal_run_id == UUID(run["id"]))
            ).mappings()
        ]
        outs = queries.batch_outs(session, [real, *({**real, "id": other} for other in many)])
        return (len(outs), outs[0].id) == (70_001, real["id"])

    def names(session: Any) -> bool:
        obligation_id, _ = held.obligations["POB #1"]
        findings = [
            validation.LineFinding(
                code="ACCOUNT_MAPPING_MISSING",
                problem="unmapped-account-role",
                line_id=uuid4(),
                account_role="REVENUE",
                account_code=REVENUE,
                message="",
                contract_id=contract_id,
                obligation_id=obligation,
            )
            for contract_id, obligation in [(held.id, obligation_id), *zip(many, many, strict=True)]
        ]
        found = validation.names_of(session, findings)
        return (len(found), found[findings[0].line_id]) == (70_001, (HELD, "POB #1"))

    attempt("the open holds of a run's contracts", holds)
    attempt("the acknowledgements of a page's chunks", chunks)
    attempt("the names of the findings' contracts and obligations", names)
    refused = {name: answer for name, answer in outcome.items() if answer is not True}
    assert not refused, refused
    assert len(outcome) == 3
