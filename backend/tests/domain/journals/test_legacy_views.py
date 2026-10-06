"""CLO-9 legacy gross and adjustment date-range journal views (ENGINE_SPEC_B S14-R-23; DEVIATIONS
§3 PJR-2 to PJR-5, §4.2, DEV-001 to DEV-003; legacy 06 §7.3 TC-JE-01 to TC-JE-15; legacy 07 GT-17,
GT-18, GT-25; POLICIES CHK-020, CHK-022, CHK-091, ALG-01 §2.1.3; BUILD_SPEC CLO-9).

Worlds, each built once per module:

- ``uat``: ``support.worlds.uat_ledger_world``. The DG-PAR-04 world of
  ``support.parity.scenario`` with golden steps 01 to 03 replayed through the legacy v1 import
  pipeline, and the engine's posting intents of the legacy UAT through step 14 sealed as subledger
  postings (L6-3-Q-37).
- ``variants``: ``support.worlds.journal_world`` (steps 01 to 03 in a fresh tenant) with the
  TC-JE-11 stream of Contract 2 and the TC-JE-14 and TC-JE-15 components.

Figures use the legacy notation of the item: ``C1 21001 +295.69`` is the line of key ``Contract 1``
on account 21001 with net debit 295.69. The corrected values of DEVIATIONS §7.1 apply (DEV-001,
DEV-002).
"""

from __future__ import annotations

import calendar
import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.config import Settings, get_settings
from erev_api.db.tables import entity_book
from erev_api.domain.journals import views
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.problems import Problem
from erev_engine.bundle import EventInput, InputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.money import cumulative_posted, round_half_up
from sqlalchemy import update
from support import intent_totals
from support.clock import frozen_clock
from support.db import TestDatabase
from support.worlds import (
    ENTITY_1,
    ENTITY_2,
    JournalWorld,
    journal_world,
    post_engine_intents,
    post_lines,
    uat_bundle,
    uat_computations,
    uat_ledger_world,
)

pytestmark = pytest.mark.slow

YEAR: int = 2023
GROSS = "GROSS"
DELTA = "DELTA"
ASC606 = "ASC606"
USD = "USD"
C1 = "Contract 1"
C2 = "Contract 2"
C3 = "Contract 3"
C4 = "Contract 4"
C1_POB1 = "Contract 1 POB #1 Hardware 1"
C1_POB2 = "Contract 1 POB #2 Software 1"
C1_POB3 = "Contract 1 POB #3 Consulting 1"
C1_POB4 = "Contract 1 POB #4 Material Right - Hardware"
C2_POB1 = "Contract 2 POB #1 Hardware 1"
C2_POB2 = "Contract 2 POB #2 Software 1"
C2_POB3 = "Contract 2 POB #3 Consulting 1"
C3_POB1 = "Contract 3 POB #1 Hardware 1"
C3_POB2 = "Contract 3 POB #2 Software 1"
C3_POB3 = "Contract 3 POB #3 Consulting 1"
C3_POB5 = "Contract 3 POB #5 Consulting 1"
C4_POB1 = "Contract 4 POB #1 Hardware 1"
C4_POB2 = "Contract 4 POB #2 Software 1"
C4_POB3 = "Contract 4 POB #3 Consulting 1"
# The legacy keys of the January 2023 obligations (engine totals of the shipped state).
SHIPPED_KEYS = {
    (C1, "POB #1"): C1_POB1,
    (C1, "POB #2"): C1_POB2,
    (C1, "POB #3"): C1_POB3,
    (C2, "POB #1"): C2_POB1,
}

SKU_ACCOUNTS = {"POB #1": "5001", "POB #2": "5002", "POB #3": "5003"}
OBLIGATIONS = ("POB #1", "POB #2", "POB #3")
THIRDS = dict.fromkeys(OBLIGATIONS, Fraction("0.335"))
SUB_CENT = dict.fromkeys(OBLIGATIONS, Fraction("0.004"))
HALF_CENT = dict.fromkeys(OBLIGATIONS, Fraction("0.005"))

type Items = dict[tuple[str, str], str]


def _settings(tmp_path_factory: pytest.TempPathFactory, name: str) -> Settings:
    root: Path = tmp_path_factory.mktemp(name)
    return get_settings().model_copy(update={"file_root": root})


@pytest.fixture(scope="module")
def uat(
    test_database: TestDatabase, keyring: KeyRing, tmp_path_factory: pytest.TempPathFactory
) -> JournalWorld:
    del test_database  # the session's migrated database, which the world commits to
    return uat_ledger_world(_settings(tmp_path_factory, "clo-9-uat"), keyring)


@pytest.fixture(scope="module")
def variants(
    test_database: TestDatabase, keyring: KeyRing, tmp_path_factory: pytest.TempPathFactory
) -> JournalWorld:
    del test_database
    settings = _settings(tmp_path_factory, "clo-9-variants")
    clock = frozen_clock()
    app = create_app(settings, clock=clock)
    world = journal_world(app, keyring, clock, LocalFileStore(settings.file_root))
    post_engine_intents(world, key="tc-je-11", computed=uat_computations(_tc_je_11_bundle()))
    # TC-JE-14: three components of exact 0.335 in Contract 1, March 2023.
    _post_components(world, "tc-je-14", C1, "FY2023-P03", THIRDS)
    # TC-JE-15: three components of exact 0.004 in Contract 3, June 2023; exact 0.005 in July.
    _post_components(world, "tc-je-15-june", C3, "FY2023-P06", SUB_CENT)
    _post_components(world, "tc-je-15-july", C3, "FY2023-P07", HALF_CENT)
    return world


def _posted_cents(exact: Mapping[str, Fraction]) -> dict[str, int]:
    """The posted cumulative revenue of each component (ALG-01 §2.1.3, ``cumulative_posted``):
    exact allocation X = 2 × component, progress 1/2, posted allocation round(X)."""
    half = Fraction(1, 2)
    return {
        obligation: cumulative_posted(2 * value, round_half_up(2 * value, 2), half, 2)
        for obligation, value in exact.items()
    }


def _post_components(
    world: JournalWorld,
    key: str,
    contract_key: str,
    period_key: str,
    exact: Mapping[str, Fraction],
) -> dict[str, int]:
    """Post one recognition pair per component from one amount (S14-R-10): Dr CONTRACT_LIABILITY /
    Cr REVENUE at the golden setup and SKU accounts. A component posted at 0 is not an intent and
    writes no line (``ck_subledger_line__amounts``). Returns the posted cents by obligation."""
    cents = _posted_cents(exact)
    liability = "21001" if contract_key in (C1, C3) else "21002"
    entries = []
    for obligation, amount in cents.items():
        if amount == 0:
            continue
        money = format(Decimal(amount).scaleb(-2), "f")
        entries.append(
            (
                "REVENUE_RECOGNITION",
                [
                    ("CONTRACT_LIABILITY", liability, money, obligation),
                    ("REVENUE", SKU_ACCOUNTS[obligation], f"-{money}", obligation),
                ],
            )
        )
    if entries:
        post_lines(
            world,
            key=f"clo-9:{key}",
            contract_key=contract_key,
            period_key=period_key,
            entries=entries,
        )
    return cents


def _tc_je_11_bundle() -> InputBundle:
    """The shipped stream of Contract 2 (golden step 04) plus POB #2 delivery of 1 unit dated
    2023-03-31, recorded first, and POB #1 billing 500.00 dated 2023-02-28, recorded second
    (legacy 06 TC-JE-11; POLICIES CHK-091)."""
    value = uat_bundle(C2, "04")
    template = next(event for event in value.events if event.event_type == "DELIVERY_RECORDED")
    head = max(event.stream_version for event in value.events)
    sequence = max(event.record_seq for event in value.events)
    recorded = max(event.recorded_at for event in value.events)

    def event(
        offset: int, kind: str, day: date, key: str, payload: dict[str, object]
    ) -> EventInput:
        return dataclasses.replace(
            template,
            event_key=f"{C2}/EV-{head + offset:06d}",
            stream_version=head + offset,
            event_type=kind,
            effective_date=day,
            recorded_at=recorded + timedelta(seconds=offset),
            record_seq=sequence + offset,
            obligation_keys=(key,),
            payload=payload,
            payload_sha256=sha256_hex(payload),
            idempotency_key=None,
        )

    delivery = event(
        1,
        "DELIVERY_RECORDED",
        date(YEAR, 3, 31),
        "POB #2",
        {"obligation_key": "POB #2", "quantity": Decimal(1), "trigger": "DELIVERY"},
    )
    billing = event(
        2,
        "BILLING_RECORDED",
        date(YEAR, 2, 28),
        "POB #1",
        {
            "invoice_number": "tc-je-11:Contract 2:POB #1",
            "line_external_id": "tc-je-11:Contract 2:POB #1",
            "obligation_key": "POB #1",
            "amount": Decimal(500),
            "issue_date": date(YEAR, 2, 28),
            "source_invoice_id": "tc-je-11:Contract 2:POB #1",
        },
    )
    events = sorted(
        (*value.events, delivery, billing),
        key=lambda item: (item.effective_date, item.record_seq, item.event_key),
    )
    return dataclasses.replace(value, events=tuple(events))


def _month(month: int) -> tuple[date, date]:
    return date(YEAR, month, 1), date(YEAR, month, calendar.monthrange(YEAR, month)[1])


def _view(
    world: JournalWorld,
    start: date,
    end: date,
    *,
    mode: str = GROSS,
    entities: Sequence[str] = (ENTITY_1, ENTITY_2),
    book: str = ASC606,
) -> views.LegacyView:
    with world.legacy.place().uow() as uow:
        return views.legacy_view(uow, entities, book, start, end, mode)


def _items(found: views.LegacyView) -> Items:
    return {(item.key, item.account): format(item.amount, "f") for item in found.line_items}


def _by_account(found: views.LegacyView) -> list[tuple[str, str, str, str]]:
    return [
        (row.account, format(row.debit, "f"), format(row.credit, "f"), format(row.net, "f"))
        for row in found.by_account
    ]


def _totals(found: views.LegacyView) -> tuple[int, str, str, str]:
    row = found.total(USD)
    return (
        row.lines,
        format(row.total_debit, "f"),
        format(row.total_credit, "f"),
        format(row.net, "f"),
    )


def _entities(found: views.LegacyView) -> list[tuple[str, str, str, bool]]:
    return [
        (row.entity_code, format(row.debit, "f"), format(row.credit, "f"), row.balanced)
        for row in found.by_entity
    ]


def _shipped_totals(view: str) -> Items:
    """The engine totals of Contracts 1 and 2 after golden step 04 over January 2023, in the
    legacy keys (``support.intent_totals``; the shipped state of legacy 06 §4.4)."""
    computed = [
        *uat_computations(uat_bundle(C1, "04")),
        *uat_computations(uat_bundle(C2, "04")),
    ]
    start, end = _month(1)
    found = intent_totals.totals(computed, view=view, start=start, end=end)
    return {
        (contract if obligation is None else SHIPPED_KEYS[(contract, obligation)], account): format(
            Decimal(amount).scaleb(-2), "f"
        )
        for (contract, obligation, account), amount in found.items()
    }


def _problem(error: pytest.ExceptionInfo[Problem]) -> tuple[str, str, str]:
    (first,) = error.value.errors
    return error.value.slug, str(first.field), str(first.message)


def test_tc_je_01_january_gross(uat: JournalWorld) -> None:
    found = _view(uat, *_month(1))
    expected = {
        (C1, "21001"): "295.69",
        (C1_POB1, "5001"): "-128.84",
        (C1_POB2, "5002"): "-118.53",
        (C1_POB3, "5003"): "-48.32",
        (C2, "15002"): "58.85",
        (C2_POB1, "5001"): "-58.85",
    }
    assert _items(found) == expected
    assert (C2, "21002") not in _items(found)  # recognition and JET-06 net to 0.00 (PJR-5)
    assert _totals(found) == (6, "354.54", "354.54", "0.00")
    assert _by_account(found) == [
        ("5001", "0.00", "187.69", "-187.69"),
        ("5002", "0.00", "118.53", "-118.53"),
        ("5003", "0.00", "48.32", "-48.32"),
        ("15002", "58.85", "0.00", "58.85"),
        ("21001", "295.69", "0.00", "295.69"),
    ]
    assert _entities(found) == [
        (ENTITY_1, "295.69", "295.69", True),
        (ENTITY_2, "58.85", "58.85", True),
    ]
    # The shipped state (golden step 04) posts the same January journal.
    assert _shipped_totals(intent_totals.GROSS) == expected
    # The view reads only the named entities.
    assert _items(_view(uat, *_month(1), entities=[ENTITY_2])) == {
        (C2, "15002"): "58.85",
        (C2_POB1, "5001"): "-58.85",
    }


def test_tc_je_02_january_delta(uat: JournalWorld) -> None:
    found = _view(uat, *_month(1), mode=DELTA)
    expected = {
        (C1, "21001"): "141.69",
        (C1_POB1, "5001"): "-128.84",
        (C1_POB2, "5002"): "-52.53",
        (C1_POB3, "5003"): "39.68",
        (C2, "15002"): "58.85",
        (C2_POB1, "5001"): "-58.85",
    }
    assert _items(found) == expected
    assert _totals(found) == (6, "240.22", "240.22", "0.00")  # CHK-020
    assert found.mode == DELTA and found.book_code == ASC606
    assert _shipped_totals(intent_totals.DELTA) == expected


def test_tc_je_03_end_date_inclusive(uat: JournalWorld) -> None:
    empty = _view(uat, date(YEAR, 1, 1), date(YEAR, 1, 30))
    assert (empty.line_items, empty.by_account, empty.by_entity, empty.totals) == ((), (), (), ())
    assert _totals(empty) == (0, "0.00", "0.00", "0.00")
    # Both ends are inclusive: the window of the 31st alone holds the six January lines.
    assert _totals(_view(uat, date(YEAR, 1, 31), date(YEAR, 1, 31))) == (
        6,
        "354.54",
        "354.54",
        "0.00",
    )


def test_tc_je_04_april_return(uat: JournalWorld) -> None:
    assert _items(_view(uat, *_month(4))) == {
        (C1, "21001"): "-193.26",
        (C1_POB1, "5001"): "193.26",
        (C2, "15002"): "-20.00",
        (C2, "21002"): "20.00",
    }


def test_tc_je_05_may_balanced(uat: JournalWorld) -> None:
    found = _view(uat, *_month(5))
    assert _by_account(found) == [
        ("5001", "5.31", "0.00", "5.31"),
        ("5003", "0.00", "10.49", "-10.49"),
        ("15002", "5.18", "0.00", "5.18"),
    ]
    assert _totals(found) == (3, "10.49", "10.49", "0.00")  # legacy Dr 10.50 / Cr 10.49 (DEV-001)
    assert _items(found) == {
        (C2, "15002"): "5.18",
        (C2_POB1, "5001"): "5.31",
        (C2_POB3, "5003"): "-10.49",
    }


def test_tc_je_06_monthly_feb_to_sep(uat: JournalWorld) -> None:
    expected: Mapping[int, Items] = {
        2: {
            (C1, "21001"): "64.42",
            (C1_POB1, "5001"): "-64.42",
            (C3, "21001"): "48.32",
            (C3_POB3, "5003"): "-48.32",
            (C4, "21002"): "111.29",
            (C4_POB1, "5001"): "-111.29",
        },
        3: {
            (C2, "15002"): "46.15",
            (C2_POB3, "5003"): "-46.15",
            (C3, "21001"): "118.53",
            (C3_POB2, "5002"): "-118.53",
            (C4, "21002"): "98.93",
            (C4_POB2, "5002"): "-98.93",
        },
        6: {(C1, "21001"): "-5.30", (C1_POB3, "5003"): "5.30"},
        7: {(C3, "21001"): "6.99", (C3_POB3, "5003"): "-6.99"},
        8: {
            (C3, "21001"): "42.10",
            (C3_POB2, "5002"): "-34.88",
            (C3_POB3, "5003"): "-7.22",
            (C4, "21002"): "16.30",
            (C4_POB1, "5001"): "-8.63",
            (C4_POB2, "5002"): "-7.67",
        },
        9: {(C3, "21001"): "32.14", (C3_POB3, "5003"): "-32.14"},
    }
    for month, lines in expected.items():
        assert _items(_view(uat, *_month(month))) == lines, month


def test_tc_je_07_october_balanced(uat: JournalWorld) -> None:
    found = _view(uat, *_month(10))
    assert _by_account(found) == [
        ("5001", "0.00", "2060.35", "-2060.35"),
        ("5002", "0.00", "1108.63", "-1108.63"),
        ("5003", "0.00", "1784.69", "-1784.69"),
        ("15002", "0.00", "90.18", "-90.18"),
        ("21001", "2990.37", "0.00", "2990.37"),
        ("21002", "2053.48", "0.00", "2053.48"),
    ]
    assert _totals(found) == (18, "5043.85", "5043.85", "0.00")  # legacy 5,043.84 / 5,043.85
    assert _entities(found) == [
        (ENTITY_1, "2990.37", "2990.37", True),
        (ENTITY_2, "2053.48", "2053.48", True),
    ]
    assert _items(found) == {
        (C1, "21001"): "638.45",
        (C1_POB2, "5002"): "-92.54",
        (C1_POB3, "5003"): "-43.01",
        (C1_POB4, "5001"): "-502.90",
        (C2, "15002"): "-90.18",
        (C2, "21002"): "1080.00",
        (C2_POB1, "5001"): "-519.66",
        (C2_POB2, "5002"): "-385.19",
        (C2_POB3, "5003"): "-84.97",
        (C3, "21001"): "2351.92",
        (C3_POB1, "5001"): "-678.02",
        (C3_POB2, "5002"): "-311.11",
        (C3_POB3, "5003"): "-94.68",
        (C3_POB5, "5003"): "-1268.11",
        (C4, "21002"): "973.48",
        (C4_POB1, "5001"): "-359.77",
        (C4_POB2, "5002"): "-319.79",
        (C4_POB3, "5003"): "-293.92",
    }


def test_tc_je_08_full_year(uat: JournalWorld) -> None:
    found = _view(uat, date(YEAR, 1, 1), date(YEAR, 12, 31))
    items = _items(found)
    assert {key: amount for key, amount in items.items() if key[1] in ("21001", "21002")} == {
        (C1, "21001"): "800.00",
        (C2, "21002"): "1100.00",
        (C3, "21001"): "2600.00",
        (C4, "21002"): "1200.00",
    }
    assert not [key for key in items if key[1] in ("15001", "15002")]  # no unbilled receivable line
    assert _by_account(found) == [
        ("5001", "0.00", "2233.81", "-2233.81"),
        ("5002", "0.00", "1487.17", "-1487.17"),
        ("5003", "0.00", "1979.02", "-1979.02"),
        ("21001", "3400.00", "0.00", "3400.00"),
        ("21002", "2300.00", "0.00", "2300.00"),
    ]
    assert _totals(found) == (17, "5700.00", "5700.00", "0.00")  # GT-18


def test_tc_je_09_monthly_sum_equals_full_year(uat: JournalWorld) -> None:
    summed: dict[tuple[str, str], Decimal] = {}
    for month in range(1, 13):
        for item in _view(uat, *_month(month)).line_items:
            summed[(item.key, item.account)] = (
                summed.get((item.key, item.account), Decimal(0)) + item.amount
            )
    monthly = {key: format(amount, "f") for key, amount in summed.items() if amount != 0}
    assert monthly == _items(_view(uat, date(YEAR, 1, 1), date(YEAR, 12, 31)))
    # The reclassification of Contract 2 moves in five months and is 0.00 over the year.
    assert (C2, "15002") in summed and summed[(C2, "15002")] == 0


def test_tc_je_11_events_out_of_order(variants: JournalWorld) -> None:
    february = _view(variants, *_month(2), entities=[ENTITY_2])
    assert _items(february) == {(C2, "15002"): "-58.85", (C2, "21002"): "58.85"}
    march = _view(variants, *_month(3), entities=[ENTITY_2])
    assert _items(march) == {(C2, "21002"): "104.62", (C2_POB2, "5002"): "-104.62"}
    # Unbilled receivable 0.00 at both month-ends.
    for end in (date(YEAR, 2, 28), date(YEAR, 3, 31)):
        to_date = _items(_view(variants, date(YEAR, 1, 1), end, entities=[ENTITY_2]))
        assert (C2, "15002") not in to_date, end


def test_tc_je_14_three_components_balance(variants: JournalWorld) -> None:
    assert _posted_cents(THIRDS) == dict.fromkeys(OBLIGATIONS, 34)  # round(0.335) half-up
    found = _view(variants, *_month(3), entities=[ENTITY_1])
    assert _items(found) == {
        (C1, "21001"): "1.02",
        (C1_POB1, "5001"): "-0.34",
        (C1_POB2, "5002"): "-0.34",
        (C1_POB3, "5003"): "-0.34",
    }
    assert _totals(found) == (4, "1.02", "1.02", "0.00")


def test_tc_je_15_sub_cent_components(variants: JournalWorld) -> None:
    assert _posted_cents(SUB_CENT) == dict.fromkeys(OBLIGATIONS, 0)
    june = _view(variants, *_month(6), entities=[ENTITY_1])
    assert (june.line_items, june.by_account, june.totals) == ((), (), ())
    assert _totals(june) == (0, "0.00", "0.00", "0.00")
    # Nothing non-zero is dropped: components of exact 0.005 post one cent each (DEV-003).
    assert _posted_cents(HALF_CENT) == dict.fromkeys(OBLIGATIONS, 1)
    july = _view(variants, *_month(7), entities=[ENTITY_1])
    assert _items(july) == {
        (C3, "21001"): "0.03",
        (C3_POB1, "5001"): "-0.01",
        (C3_POB2, "5002"): "-0.01",
        (C3_POB3, "5003"): "-0.01",
    }
    assert _totals(july) == (4, "0.03", "0.03", "0.00")


def test_gt_17_month_totals(uat: JournalWorld) -> None:
    listed = {
        1: "354.54",
        2: "224.03",
        3: "263.61",
        4: "213.26",
        5: "10.49",
        8: "58.40",
        9: "32.14",
        10: "5043.85",
    }
    for month in range(1, 13):
        found = _view(uat, *_month(month))
        _, debit, credit, net = _totals(found)
        assert (debit == credit, net) == (True, "0.00"), month  # May and October balance (GT-25)
        assert all(row.balanced for row in found.by_entity), month
        if month in listed:
            assert debit == listed[month], month


def test_legacy_view_parameter_problems(uat: JournalWorld) -> None:
    start, end = _month(1)
    with pytest.raises(Problem) as raised:
        _view(uat, start, end, entities=[])
    assert _problem(raised) == ("validation-failed", "entity_codes", "Choose at least one entity.")
    with pytest.raises(Problem) as raised:
        _view(uat, start, end, entities=[ENTITY_1, "Mock Entity 9"])
    assert _problem(raised)[2] == "No entity has the code Mock Entity 9."
    with pytest.raises(Problem) as raised:
        _view(uat, end, start)
    assert _problem(raised) == (
        "validation-failed",
        "to_date",
        "Start date must be on or before end date.",
    )
    with pytest.raises(Problem) as raised:
        _view(uat, start, end, mode="NET")
    assert _problem(raised)[1] == "mode"
    with pytest.raises(Problem) as raised:
        _view(uat, start, end, book="IFRS16")
    assert _problem(raised)[1] == "book"
    with pytest.raises(Problem) as raised:
        _view(uat, start, end, mode=DELTA, book="LEGACY")
    assert _problem(raised)[1:] == (
        "book",
        views.DELTA_OF_LEGACY,
    )
    # An entity without an enabled LEGACY book has no adjustment view (SCREENS_B RPT-13).
    with uat.legacy.place().uow() as uow:
        uow.session.execute(
            update(entity_book)
            .where(
                entity_book.c.entity_id == uat.entities[ENTITY_2],
                entity_book.c.book_code == "LEGACY",
            )
            .values(is_enabled=False)
        )
        with pytest.raises(Problem) as raised:
            views.legacy_view(uow, [ENTITY_1, ENTITY_2], ASC606, start, end, DELTA)
        assert _problem(raised) == (
            "validation-failed",
            "mode",
            "Enable the Legacy book for Mock Entity 2 before viewing adjustment journals.",
        )
        uow.session.rollback()
    assert _totals(_view(uat, start, end, mode=DELTA)) == (6, "240.22", "240.22", "0.00")
