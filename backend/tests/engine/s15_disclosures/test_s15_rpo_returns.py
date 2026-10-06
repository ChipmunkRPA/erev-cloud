"""Stage 15 RPO rollforward on the returns-adjusted basis (D-91 C606-04).

ENGINE_SPEC_B S15-R-12 (rev 1.7), S15-INV-08, S09-R-23, S09-R-26; POLICIES ALG-06 §2.7; 03
REQ-RPT-010 (V9). The worlds are the RET answer keys computed through ``s01_canonicalize`` and
``s13_books.run_books`` (ASC606, US01) and the D-91 variants of RET-CHK-029 (40 units, a genuine
late delivery, booking before the first transfer, the PRICE_MOD_PIN_CCU modification, the
termination fixture and the cross-calendar case J2). Every expected figure is derived from the
rules in ``.run/l9/d91-c606-04/derive_b2.py`` (r = 10,000.00 ÷ 100 = 100.00; ρ = r × (Y + E);
R = r × (N − Y − E); RPO = 10,000.00 − ρ − R), never from engine output. No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from erev_engine import ENGINE_VERSION, compute
from erev_engine.bundle import EntityInput, InputBundle, PeriodInput
from erev_engine.canonical import sha256_hex
from erev_engine.errors import EngineError
from erev_engine.stages import STAGES, s01_canonicalize, s13_books, s15_disclosures
from erev_engine.stages.s09_recognition import RecognitionState, returns
from erev_engine.stages.s15_disclosures import DisclosureState, RpoRollforward, rpo
from erev_engine.stages.state import BookContext
from erev_engine.trace import TraceBuilder, reevaluate
from support.answer_keys.loader import ANSWER_KEY_ROOT, LoadedKey, load, load_all
from support.answer_keys.runners import _build_checkpoint_bundles
from test_s15_rpo import dated_rpo

RET_029 = "ret/RET-CHK-029-S3-EX22.yaml"
SUBJECT = "C-RET/L1-PROD"
US = "US01"
P01, P02, P03 = "FY2026-P01", "FY2026-P02", "FY2026-P03"
Mutator = Callable[[InputBundle], InputBundle]
Doc = dict[str, object]


def _bundle(loaded: LoadedKey, checkpoint: str) -> InputBundle:
    found = next(item for item in _build_checkpoint_bundles(loaded) if item.name == checkpoint)
    (bundle,) = found.bundles
    return bundle


def _run(bundle: InputBundle) -> tuple[BookContext, DisclosureState, RecognitionState]:
    """The ASC606 book context, stage 15 state and stage 09 state of ``bundle``."""
    cb = s01_canonicalize.run(bundle, TraceBuilder(engine_version=ENGINE_VERSION))
    result = next(item for item in s13_books.run_books(cb, STAGES) if str(item.book) == "ASC606")
    assert isinstance(result.state, DisclosureState)
    recognition = result.states["09"]
    assert isinstance(recognition, RecognitionState)
    return s13_books.book_context(cb, cb.books[str(result.book)]), result.state, recognition


def _book(
    path: str, checkpoint: str, mutate: Mutator | None = None
) -> tuple[BookContext, DisclosureState, RecognitionState]:
    bundle = _bundle(load(ANSWER_KEY_ROOT / path), checkpoint)
    return _run(bundle if mutate is None else mutate(bundle))


def _nonzero(lines: Mapping[str, int]) -> dict[str, int]:
    return {name: value for name, value in lines.items() if value}


def _sorted_events(bundle: InputBundle, events: Sequence[object]) -> InputBundle:
    ordered = tuple(
        sorted(events, key=lambda ev: (ev.effective_date, ev.record_seq, ev.event_key))  # type: ignore[attr-defined]
    )
    return dataclasses.replace(bundle, events=ordered)  # type: ignore[arg-type]


def _quantity(units: int) -> Mutator:
    """Every ``DELIVERY_RECORDED`` of the bundle delivers ``units``."""

    def mutate(bundle: InputBundle) -> InputBundle:
        events = [
            dataclasses.replace(ev, payload={**ev.payload, "quantity": Decimal(units)})
            if ev.event_type == "DELIVERY_RECORDED"
            else ev
            for ev in bundle.events
        ]
        return _sorted_events(bundle, events)

    return mutate


def _late_delivery(bundle: InputBundle) -> InputBundle:
    """40 units on 10 January plus 10 units effective 20 January recorded on 20 February."""
    bundle = _quantity(40)(bundle)
    first = next(ev for ev in bundle.events if ev.event_type == "DELIVERY_RECORDED")
    payload = {**first.payload, "quantity": Decimal(10)}
    late = dataclasses.replace(
        first,
        event_key="C-RET/EV-000009",
        stream_version=9,
        record_seq=9,
        effective_date=date(2026, 1, 20),
        recorded_at=datetime(2026, 2, 20, 17, tzinfo=UTC),
        payload=payload,
        payload_sha256=sha256_hex(payload),
    )
    known = dataclasses.replace(bundle, known_at=max(bundle.known_at, late.recorded_at))
    return _sorted_events(known, [*known.events, late])


def _delivery_in_february(bundle: InputBundle) -> InputBundle:
    """Booking on 10 January, the first transfer of the 100 units on 10 February (before the return
    of that day in ENG-06 order); E is capped at the units kept, so ρ is 0 through January."""
    events = [
        dataclasses.replace(ev, effective_date=date(2026, 2, 10))
        if ev.event_type == "DELIVERY_RECORDED"
        else ev
        for ev in bundle.events
    ]
    return _sorted_events(bundle, events)


def _cross_calendar(bundle: InputBundle) -> InputBundle:
    """Case J2: the obligation is performed by UK01 (periods to 28 Jan, 25 Feb, 31 Mar) under a
    US01 (monthly) contract; 5 units come back on 27 February, after UK01's 25 February end."""
    bounds = (
        (date(2026, 1, 1), date(2026, 1, 28)),
        (date(2026, 1, 29), date(2026, 2, 25)),
        (date(2026, 2, 26), date(2026, 3, 31)),
    )
    periods = tuple(
        PeriodInput(f"FY2026-P{index:02d}", 2026, index, start, end, (("ASC606", "open"),))
        for index, (start, end) in enumerate(bounds, start=1)
    )
    uk = EntityInput("UK01", "USD", "Europe/London", "MONTHLY", periods)
    events = []
    for ev in bundle.events:
        if ev.event_type == "CONTRACT_BOOKED":
            lines = [dict(line) for line in ev.payload["lines"]]  # type: ignore[union-attr]
            lines[0]["performing_entity_code"] = "UK01"
            payload = {**ev.payload, "lines": lines}
        elif ev.event_type == "RETURN_RECORDED":
            payload = {**ev.payload, "quantity": Decimal(5), "refund_amount": Decimal("500.00")}
        elif ev.event_type == "CREDIT_MEMO_RECORDED":
            payload = {**ev.payload, "amount": Decimal("500.00"), "issue_date": date(2026, 2, 27)}
        else:
            events.append(ev)
            continue
        moved = ev.event_type in ("RETURN_RECORDED", "CREDIT_MEMO_RECORDED")
        events.append(
            dataclasses.replace(
                ev,
                effective_date=date(2026, 2, 27) if moved else ev.effective_date,
                recorded_at=datetime(2026, 2, 27, 12, tzinfo=UTC) if moved else ev.recorded_at,
                payload=payload,
                payload_sha256=sha256_hex(payload),
            )
        )
    books = []
    for book in bundle.books:
        # UK01 keeps the book: its period-pinned policies copy US01's values per period key.
        copied = tuple(
            dataclasses.replace(policy, subject_key=f"UK01@{policy.subject_key.split('@', 1)[1]}")
            for policy in book.policies
            if policy.scope == "PERIOD" and policy.subject_key.startswith("US01@")
        )
        policies = tuple(
            sorted(
                (*book.policies, *copied),
                key=lambda item: (item.code, item.scope, item.subject_key),
            )
        )
        books.append(
            dataclasses.replace(
                book, entity_codes=tuple(sorted((*book.entity_codes, "UK01"))), policies=policies
            )
        )
    entities = tuple(sorted((*bundle.entities, uk), key=lambda item: item.code))
    known_at = max(bundle.known_at, datetime(2026, 2, 27, 12, tzinfo=UTC))
    moved = dataclasses.replace(bundle, entities=entities, books=tuple(books), known_at=known_at)
    return _sorted_events(moved, events)


def _variant(tmp_path: Path, key_id: str, mutate: Callable[[Doc], None]) -> LoadedKey:
    """RET-CHK-029 as a key ``key_id`` under ``tmp_path`` after ``mutate`` edits its document."""
    document = yaml.safe_load((ANSWER_KEY_ROOT / RET_029).read_text(encoding="utf-8"))
    document["id"] = key_id
    mutate(document)
    for index, item in enumerate(document["timeline"], start=1):
        item["seq"] = index
    last = document["timeline"][-1]["seq"]
    for checkpoint in document["checkpoints"]:
        checkpoint["after_seq"] = min(int(checkpoint["after_seq"]), last)
        if checkpoint["name"] != "end-of-january":
            checkpoint["after_seq"] = last
        # The variants change the monetary picture; the key's own expectations are not asserted.
        checkpoint.pop("subledger", None)
        for contract in checkpoint.get("contracts", ()):
            contract.pop("version", None)
            contract.pop("obligations", None)
            contract.pop("balances", None)
    folder = tmp_path / "ret"
    folder.mkdir(exist_ok=True)
    path = folder / f"{key_id}.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return load(path)


def _forty_units(document: Doc) -> None:
    for item in document["timeline"]:  # type: ignore[union-attr]
        if item["event_type"] == "DELIVERY_RECORDED":
            item["payload"]["quantity"] = "40"


def _return_rate_pin(document: Doc, on: str) -> None:
    estimate = document["contracts"][0]["estimates"][0]  # type: ignore[index]
    estimate["versions"].append(
        {
            "version_no": str(len(estimate["versions"]) + 1),
            "effective_date": on,
            "rate": "0.03",
            "expected_quantity": "3",
            "parameters": {
                "carrying_cost_per_unit": "60.00",
                "recovery_cost_per_unit": "0.00",
                "window_end_date": "2026-03-15",
            },
            "rationale": "Re-pinned at the boundary",
        }
    )
    document["timeline"].append(  # type: ignore[union-attr]
        {
            "seq": 0,
            "kind": "event",
            "contract": "C-RET",
            "event_type": "ESTIMATE_CHANGED",
            "effective_date": on,
            "payload": {
                "estimate": "RET-JAN",
                "version_no": estimate["versions"][-1]["version_no"],
            },
        }
    )


def _price_modification(document: Doc) -> None:
    """PRICE_MOD_PIN_CCU: 40 delivered; +2,000.00 on 15 February, remaining goods not distinct
    (cumulative catch-up), the RETURN_RATE re-pinned at the boundary."""
    _forty_units(document)
    document["contracts"][0]["modifications"] = [  # type: ignore[index]
        {
            "reference": "MOD-PRICE",
            "effective_date": "2026-02-15",
            "kind": "PRICE_CHANGE",
            "questionnaire": {
                "L1-PROD": {
                    "added_goods_distinct": False,
                    "priced_at_ssp": False,
                    "remaining_goods_distinct_from_transferred": False,
                }
            },
            "lines": [
                {
                    "obligation_key": "L1-PROD",
                    "action": "CHANGE",
                    "product_code": "PROD-RET",
                    "quantity_delta": "0",
                    "consideration_delta": "2000.00",
                }
            ],
        }
    ]
    _return_rate_pin(document, "2026-02-15")
    document["timeline"].append(  # type: ignore[union-attr]
        {
            "seq": 0,
            "kind": "event",
            "contract": "C-RET",
            "event_type": "CONTRACT_AMENDED",
            "effective_date": "2026-02-15",
            "payload": {"modification": "MOD-PRICE"},
        }
    )
    document["timeline"].sort(key=lambda item: item["effective_date"])  # type: ignore[union-attr]


def _termination(document: Doc) -> None:
    """The accounting verifier's RET-CHK-029-VERIFY-TERM-40: 40 delivered, TERMINATION/REMOVE of
    the 60 undelivered units on 20 February, remaining goods distinct."""
    _forty_units(document)
    contract = document["contracts"][0]  # type: ignore[index]
    contract["termination"] = {"party": "CUSTOMER", "has_penalty": False, "notice_days": "30"}
    contract["modifications"] = [
        {
            "reference": "MOD-TERM",
            "effective_date": "2026-02-20",
            "kind": "TERMINATION",
            "questionnaire": {
                "L1-PROD": {
                    "added_goods_distinct": False,
                    "priced_at_ssp": False,
                    "remaining_goods_distinct_from_transferred": True,
                }
            },
            "lines": [
                {
                    "obligation_key": "L1-PROD",
                    "action": "REMOVE",
                    "product_code": "PROD-RET",
                    "quantity_delta": "-60",
                    "consideration_delta": "-6000.00",
                }
            ],
        }
    ]
    document["timeline"].append(  # type: ignore[union-attr]
        {
            "seq": 0,
            "kind": "event",
            "contract": "C-RET",
            "event_type": "CONTRACT_TERMINATED",
            "effective_date": "2026-02-20",
            "payload": {
                "modification": "MOD-TERM",
                "termination_kind": "FULL",
                "obligation_keys": ["L1-PROD"],
                "refund_amount": "0.00",
            },
        }
    )
    document["timeline"].sort(key=lambda item: item["effective_date"])  # type: ignore[union-attr]


def _chain(
    ctx: BookContext, state: DisclosureState, recognition: RecognitionState, entity: str
) -> list[RpoRollforward]:
    """Every period of ``entity``: UNEXPLAINED 0, each opening the previous closing, each closing
    the stage 09 measure dated at the period end (S15-INV-08), and a correct snapshot yields
    LATE_EVENTS 0."""
    found: list[RpoRollforward] = []
    previous: RpoRollforward | None = None
    for period in sorted(ctx.entities[entity].periods, key=lambda item: item.start_date):
        current = s15_disclosures.rollforward(
            ctx, state.allocated, recognition, entity, period.period_key
        )
        assert current.unexplained == 0, period.period_key
        subjects = [row.subject_key for row in current.rows]
        assert current.lines["CLOSING"] == dated_rpo(ctx, recognition, period.end_date, subjects), (
            period.period_key
        )
        if previous is not None:
            assert current.lines["OPENING"] == previous.lines["CLOSING"], period.period_key
            snapshot = {row.subject_key: row.lines["CLOSING"] for row in previous.rows}
            with_snapshot = s15_disclosures.rollforward(
                ctx, state.allocated, recognition, entity, period.period_key, opening=snapshot
            )
            assert (with_snapshot.lines["LATE_EVENTS"], with_snapshot.unexplained) == (0, 0)
        found.append(current)
        previous = current
    return found


@pytest.mark.parametrize("checkpoint", ["end-of-january", "end-of-february", "window-expired"])
@pytest.mark.parametrize("units", [100, 40])
def test_s15_r12_returns_adjusted_lines_ret_chk_029(checkpoint: str, units: int) -> None:
    """RET-CHK-029 on the S15-R-08 basis (S15-R-12 rev 1.7): a new contract enters at the
    constrained price allocated 9,700.00; February moves nothing; the 15 March window expiry moves
    ρ 300.00 → 200.00 (or 300.00 → 0 when only the January events are known) as a change in the
    estimate of variable consideration against the same revenue. Main closed at 300.00 / 6,300.00
    on the gross basis."""
    ctx, state, recognition = _book(RET_029, checkpoint, _quantity(units))
    revenue_january = -units * 10000 + 30000  # −(r × (N − 0 − 3))
    closing = 1000000 - 30000 - (-revenue_january)
    periods = _chain(ctx, state, recognition, US)
    by_key = {item.period_key: _nonzero(item.lines) for item in periods}
    expected_p01 = {"NEW_CONTRACTS": 970000, "REVENUE": revenue_january}
    if closing:
        expected_p01["CLOSING"] = closing
    assert by_key[P01] == expected_p01
    assert by_key[P02] == ({"OPENING": closing, "CLOSING": closing} if closing else {})
    expiry = 30000 if checkpoint == "end-of-january" else 10000
    expected_p03 = {"VC_ESTIMATE_CHANGES": expiry, "REVENUE": -expiry}
    if closing:
        expected_p03.update({"OPENING": closing, "CLOSING": closing})
    assert by_key[P03] == expected_p03
    (published,) = state.rpo_rollforwards
    assert published.lines["CLOSING"] == state.rpo_amount == closing


def test_s15_r12_genuine_late_delivery_is_the_whole_late_events_line() -> None:
    """A delivery of 10 units effective 20 January recorded 20 February restates the January RPO
    from 6,000.00 (the snapshot) to 5,000.00: LATE_EVENTS −1,000.00 is the whole line, February
    moves no revenue and the closing 5,000.00 is ``rpo_amount`` (main −700.00 / 5,300.00)."""
    ctx, state, recognition = _book(RET_029, "end-of-february", _late_delivery)
    february = s15_disclosures.rollforward(
        ctx, state.allocated, recognition, US, P02, opening={SUBJECT: 600000}
    )
    assert _nonzero(february.lines) == {
        "OPENING": 600000,
        "LATE_EVENTS": -100000,
        "CLOSING": 500000,
    }
    assert february.unexplained == 0
    january = s15_disclosures.rollforward(ctx, state.allocated, recognition, US, P01)
    assert _nonzero(january.lines) == {
        "NEW_CONTRACTS": 970000,
        "REVENUE": -470000,
        "CLOSING": 500000,
    }
    assert february.lines["CLOSING"] == state.rpo_amount == 500000
    assert dated_rpo(ctx, recognition, date(2026, 2, 28)) == 500000
    _chain(ctx, state, recognition, US)


def test_s15_r12_estimate_revision_ret_chk_060() -> None:
    """RET-CHK-060 end-of-january: E revised 3 → 4 at the period end; the between-boundary
    movement of ρ (300.00 → 400.00) is a VC estimate change of −100.00 and the closing is the
    ``rpo_amount`` 0 (main 400.00)."""
    ctx, state, recognition = _book("ret/RET-CHK-060-S3-EX22-REVISED.yaml", "end-of-january")
    (published,) = state.rpo_rollforwards
    assert published.closing_date == state.as_of
    assert _nonzero(published.lines) == {
        "NEW_CONTRACTS": 970000,
        "VC_ESTIMATE_CHANGES": -10000,
        "REVENUE": -960000,
    }
    assert published.lines["CLOSING"] == state.rpo_amount == 0
    _chain(ctx, state, recognition, US)


def test_s15_r12_window_expiry_ret_js_03() -> None:
    """RET-JS-03 window-expired (r 250.00): 31 March Y 0 E 20 (ρ 5,000.00), 30 April Y 16 E 0
    (ρ 4,000.00): March NEW_CONTRACTS 95,000.00 and REVENUE −95,000.00; April VC +1,000.00 and
    REVENUE −1,000.00; closing 0 = ``rpo_amount`` (main 4,000.00)."""
    ctx, state, recognition = _book(
        "ret/RET-JS-03-ECOMMERCE-REFUND-RETURN-ASSET.yaml", "window-expired"
    )
    (published,) = state.rpo_rollforwards
    assert _nonzero(published.lines) == {"VC_ESTIMATE_CHANGES": 100000, "REVENUE": -100000}
    assert published.lines["CLOSING"] == state.rpo_amount == 0
    march = s15_disclosures.rollforward(
        ctx, state.allocated, recognition, published.entity, "FY2026-P03"
    )
    assert _nonzero(march.lines) == {"NEW_CONTRACTS": 9500000, "REVENUE": -9500000}
    _chain(ctx, state, recognition, published.entity)


def test_s15_r12_booking_before_first_transfer() -> None:
    """Booking in January, the first transfer in February: E is capped at the units kept, so ρ at
    the inception boundary is 0, NEW_CONTRACTS is the gross allocation 10,000.00 and the
    first-transfer reduction −300.00 is a between-boundary VC estimate change of February."""
    ctx, state, recognition = _book(RET_029, "end-of-february", _delivery_in_february)
    january, february, _ = _chain(ctx, state, recognition, US)
    assert _nonzero(january.lines) == {"NEW_CONTRACTS": 1000000, "CLOSING": 1000000}
    assert _nonzero(february.lines) == {
        "OPENING": 1000000,
        "VC_ESTIMATE_CHANGES": -30000,
        "REVENUE": -970000,
    }
    assert february.lines["CLOSING"] == state.rpo_amount == 0


def test_s15_r12_modification_boundary_net(tmp_path: Path) -> None:
    """The engineering verifier's PRICE_MOD_PIN_CCU (40 delivered; +2,000.00 on 15 February with
    cumulative catch-up; RETURN_RATE re-pinned at the boundary): r 100.00 → 120.00 moves ρ at the
    boundary from 300.00 (Y 2, E 1 at r 100 on 14 Feb) to 600.00 (Y 2, E 3 at r 120), so
    MODIFICATIONS takes the jump of A − ρ, (12,000 − 600) − (10,000 − 300) = 1,700.00, nothing is
    left between boundaries (ρ 300 → 600 → 600) and REVENUE −500.00 (3,700 → 4,200); the 15 March
    expiry moves ρ 600.00 → 240.00 on VC_ESTIMATE_CHANGES against REVENUE −360.00."""
    loaded = _variant(tmp_path, "RET-CHK-029-D91-PRICE-MOD-CCU", _price_modification)
    ctx, state, recognition = _run(_bundle(loaded, "window-expired"))
    (ob,) = state.allocated.obligations
    assert [(seg.cause.value, seg.a_posted) for seg in ob.segments if seg.component == "FIXED"] == [
        ("INCEPTION", 1000000),
        ("MODIFICATION", 1200000),
    ]
    january, february, march = _chain(ctx, state, recognition, US)
    assert _nonzero(january.lines) == {
        "NEW_CONTRACTS": 970000,
        "REVENUE": -370000,
        "CLOSING": 600000,
    }
    assert _nonzero(february.lines) == {
        "OPENING": 600000,
        "MODIFICATIONS": 170000,
        "REVENUE": -50000,
        "CLOSING": 720000,
    }
    assert _nonzero(march.lines) == {
        "OPENING": 720000,
        "VC_ESTIMATE_CHANGES": 36000,
        "REVENUE": -36000,
        "CLOSING": 720000,
    }
    (published,) = state.rpo_rollforwards
    assert published.lines["CLOSING"] == state.rpo_amount == 720000
    contract = next(
        view for view in state.allocated.contracts if view.header.external_id == "C-RET"
    )
    segments = [seg for seg in ob.segments if seg.component == "FIXED"]
    assert (
        returns.reduction(ctx, state.allocated, contract, ob, segments[0], date(2026, 2, 14))
        == 30000
    )
    assert (
        returns.reduction(ctx, state.allocated, contract, ob, segments[1], date(2026, 2, 15))
        == 60000
    )


def test_s15_r12_cancelled_obligation_contributes_nothing_after_boundary(tmp_path: Path) -> None:
    """The accounting verifier's RET-CHK-029-VERIFY-TERM-40 (TERMINATION/REMOVE on 20 February,
    remaining goods distinct): history is retained (January's lines and closing), the termination
    period keeps its opening, its pre-boundary movements and the CANCELLATIONS removal and closes at
    0, and later periods carry nothing despite the 15 March window expiry (main P03 REVENUE −100.00
    / UNEXPLAINED +100.00). Reachability and classification evidence only: the fixture's monetary
    amounts are contaminated by the stage 09 ``unit_rate`` divisor sibling (D-91), so no amount is
    asserted beyond the identities the rules impose."""
    loaded = _variant(tmp_path, "RET-CHK-029-D91-TERM-40", _termination)
    ctx, state, recognition = _run(_bundle(loaded, "window-expired"))
    measures = recognition.obligation_measures[SUBJECT]
    assert str(measures.satisfaction_status) == "CANCELLED"
    periods = {
        key: s15_disclosures.rollforward(ctx, state.allocated, recognition, US, key)
        for key in (P01, P02, P03)
    }
    january, february, march = periods[P01], periods[P02], periods[P03]
    assert all(item.unexplained == 0 for item in periods.values())
    assert january.lines["NEW_CONTRACTS"] > 0 > january.lines["REVENUE"]
    assert january.lines["CANCELLATIONS"] == 0
    assert january.lines["CLOSING"] == dated_rpo(ctx, recognition, date(2026, 1, 31))
    assert february.lines["OPENING"] == january.lines["CLOSING"]
    assert february.lines["CANCELLATIONS"] != 0 and february.lines["CLOSING"] == 0
    movements = sum(february.lines[code] for code in rpo.MOVEMENTS)
    assert february.lines["OPENING"] + movements == 0
    assert _nonzero(march.lines) == {}
    (row,) = march.rows
    assert (row.subject_key, _nonzero(row.lines)) == (SUBJECT, {})
    # The published rollforward is the period holding d_v (the 20 February termination) under both
    # checkpoints; the final CANCELLED status erases neither it nor January.
    (published,) = state.rpo_rollforwards
    assert published.period_key == P02 and dict(published.lines) == dict(february.lines)
    assert state.rpo_amount == 0
    # From the February checkpoint: the termination period as published.
    _, state_feb, _ = _run(_bundle(loaded, "end-of-february"))
    (published_feb,) = state_feb.rpo_rollforwards
    assert published_feb.period_key == P02
    assert dict(published_feb.lines) == dict(february.lines)


@pytest.mark.parametrize(
    "path",
    [
        "disc/DISC-S10-DISCLOSURES-ROLLFORWARD-EX21.yaml",
        "disc/DISC-GE-06-IDIQ-TASK-ORDERS-OPTIONS-RPO.yaml",
        "ret/RET-CHK-061-GT08.yaml",
    ],
)
def test_s15_r12_non_reduce_and_k02_lines_unchanged(path: str) -> None:
    """Without a REDUCE return path ρ = 0 by construction: every rollforward keeps UNEXPLAINED 0 and
    a same-cutoff closing equal to ``rpo_amount`` (K-02's lines are asserted in
    ``test_s15_waterfall``)."""
    loaded = load(ANSWER_KEY_ROOT / path)
    for checkpoint in _build_checkpoint_bundles(loaded):
        for bundle in checkpoint.bundles:
            cb = s01_canonicalize.run(bundle, TraceBuilder(engine_version=ENGINE_VERSION))
            for result in s13_books.run_books(cb, STAGES):
                state = result.state
                if not isinstance(state, DisclosureState):
                    continue
                for rollforward in state.rpo_rollforwards:
                    assert rollforward.unexplained == 0, (checkpoint.name, rollforward.period_key)
                    if rollforward.closing_date == state.as_of and len(state.rpo_rollforwards) == 1:
                        assert rollforward.lines["CLOSING"] == state.rpo_after_exemptions


RPO_KEYS = (
    "ALC-S4-EX33",
    "DISC-S10-DISCLOSURES-RPO-EX42",
    "DISC-S10-DISCLOSURES-RPO-EX42-TIME-BANDS-AND-EXPEDIENT",
    "DISC-GE-06-IDIQ-TASK-ORDERS-OPTIONS-RPO",
    "DISC-CHK-006-S10-DISCLOSURES-ROLLFORWARD-EX21",
    "DISC-S10-DISCLOSURES-ROLLFORWARD-EX21",
    "MR-FS-04-EARLY-RENEWAL-PRICE-CAP",
    "POB-S2-EX11-CASEA-OWNPRICES",
    "REC-FS-01-SAAS-RAMP-ANNUAL-BILLING",
    "REC-S5-EX63-OWNSSP",
    "RND-CHK-004-CHK-006-S2-EX11-CASEA-OWNPRICES",
)
KNOWN_RESIDUALS = frozenset(
    {"ENT-PER-ENTITY-NETTING-IN-A-COMBINED-GROUP", "ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION"}
)


def _performing_period_ends(ctx: BookContext, entity: str) -> frozenset[date]:
    return frozenset(period.end_date for period in ctx.entities[entity].periods)


def test_s15_inv_08_closing_equals_dated_rpo_per_entity() -> None:
    """S15-INV-08 over the RET and DISC families and the ``rpo_amount`` keys: for every contracting
    entity and period, over the obligations whose performing-entity period end coincides with the
    period end, Σ CLOSING = the RPO after exemptions of the stage 09 measures dated at that end. 0
    mismatches on every cell holding a REDUCE returnable obligation (275 at 908a5fa); any other
    residual belongs to the two pre-existing non-returns keys; the published rollforward of the
    period holding d_v closes at ``rpo_amount`` when d_v is that period's end."""
    every = {item.key.id: item for item in load_all(families=("RET", "DISC"))}
    every.update({item.key.id: item for item in load_all(ids=RPO_KEYS)})
    keys = [
        item
        for _, item in sorted(every.items())
        if item.key.status == "active" and item.key.runner == "engine"
    ]
    assert len(keys) >= 15  # RET and DISC families plus the rpo_amount keys (19 at D-91)
    returnable_cells = returnable_mismatches = other_cells = 0
    other_mismatches: dict[str, int] = {}
    same_cutoff = ties = skipped = 0
    for loaded in keys:
        for checkpoint in _build_checkpoint_bundles(loaded):
            for bundle in checkpoint.bundles:
                try:
                    cb = s01_canonicalize.run(bundle, TraceBuilder(engine_version=ENGINE_VERSION))
                    results = s13_books.run_books(cb, STAGES)
                except EngineError:
                    skipped += 1
                    continue
                for result in results:
                    state = result.state
                    if not isinstance(state, DisclosureState):
                        continue
                    ctx = s13_books.book_context(cb, cb.books[str(result.book)])
                    recognition = result.states["09"]
                    assert isinstance(recognition, RecognitionState)
                    allocated = state.allocated
                    reduce = {
                        ob.subject_key
                        for ob in allocated.obligations
                        if ob.subject_key in allocated.return_paths
                        and returns.policy(ctx, allocated, ob, returns.SCOPE_POLICY)
                        == returns.REDUCE
                    }
                    performing = {
                        ob.subject_key: ob.performing_entity for ob in allocated.obligations
                    }
                    if state.rpo_rollforwards and all(
                        item.closing_date == state.as_of for item in state.rpo_rollforwards
                    ):
                        same_cutoff += 1
                        ties += (
                            sum(item.lines["CLOSING"] for item in state.rpo_rollforwards)
                            == state.rpo_after_exemptions  # gross − exempt (D-98 91a)
                        )
                    for entity in sorted(
                        {
                            ob.contracting_entity
                            for ob in allocated.obligations
                            if ob.subject_key in recognition.obligation_measures
                        }
                    ):
                        for period in ctx.entities[entity].periods:
                            rollforward = s15_disclosures.rollforward(
                                ctx, allocated, recognition, entity, period.period_key
                            )
                            subjects = [
                                row.subject_key
                                for row in rollforward.rows
                                if period.end_date
                                in _performing_period_ends(ctx, performing[row.subject_key])
                            ]
                            if not subjects:
                                continue
                            closing = sum(
                                row.lines["CLOSING"]
                                for row in rollforward.rows
                                if row.subject_key in subjects
                            )
                            expected = dated_rpo(ctx, recognition, period.end_date, subjects)
                            if any(subject in reduce for subject in subjects):
                                returnable_cells += 1
                                returnable_mismatches += closing != expected
                            else:
                                other_cells += 1
                                if closing != expected:
                                    other_mismatches[loaded.key.id] = (
                                        other_mismatches.get(loaded.key.id, 0) + 1
                                    )
    assert returnable_cells > 0 and returnable_mismatches == 0, (
        returnable_cells,
        returnable_mismatches,
    )
    assert set(other_mismatches) <= KNOWN_RESIDUALS, other_mismatches
    assert same_cutoff == ties, (same_cutoff, ties)
    print(  # noqa: T201  the measured counts of the sweep, for the lane record
        f"S15-INV-08 sweep: keys {len(keys)}, skipped bundles {skipped}, returnable cells "
        f"{returnable_cells} (mismatches {returnable_mismatches}), other cells {other_cells} "
        f"(residual {other_mismatches}), same-cutoff ties {ties}/{same_cutoff}"
    )


def test_s15_r12_cross_calendar_published_basis() -> None:
    """Case J2: ρ and R are read from the states stage 09 publishes at the performing entity's
    period ends (UK01: 28 Jan, 25 Feb, 31 Mar), never recomputed at the contracting entity's ends.
    The 27 February return of 5 units lies after UK01's 25 February end, so US01's February moves
    nothing and March carries VC −200.00 (ρ 300 → 500: E 3 → 0, Y 0 → 5) against REVENUE +200.00;
    the dated variants gave UNEXPLAINED ±200.00."""
    ctx, state, recognition = _book(RET_029, "end-of-february", _cross_calendar)
    january, february, march = _chain(ctx, state, recognition, US)
    assert _nonzero(january.lines) == {"NEW_CONTRACTS": 970000, "REVENUE": -970000}
    assert _nonzero(february.lines) == {}
    assert _nonzero(march.lines) == {"VC_ESTIMATE_CHANGES": -20000, "REVENUE": 20000}
    assert state.rpo_amount == 0
    (published,) = state.rpo_rollforwards
    assert (published.entity, published.period_key, published.lines["CLOSING"]) == (US, P02, 0)


def test_s15_r12_reduction_provenance_and_trace_reevaluation() -> None:
    """ρ at every performing-entity period end is round(r × (Y + E)) of the published return state
    (300.00 / 300.00 / 200.00); at d_v it equals ``ObligationMeasures.returns_reduction`` and
    a_posted − allocated_amount; the ``return_expected_units`` node carries the E used; the trace
    re-evaluates with no node added or changed by the rollforward (§15.5 names none)."""
    bundle = _bundle(load(ANSWER_KEY_ROOT / RET_029), "end-of-february")
    ctx, state, recognition = _run(bundle)
    (ob,) = state.allocated.obligations
    path = state.allocated.return_paths[SUBJECT]
    ends = {period.period_key: period.end_date for period in ctx.entities[US].periods}
    measured = {
        period: returns.reduction_from_state(path, ob, found, ends[period], 2)
        for (subject, period), found in recognition.return_states.items()
        if subject == SUBJECT
    }
    assert measured == {P01: 30000, P02: 30000, P03: 20000}
    for (_subject, period), found in recognition.return_states.items():
        rate = returns.unit_rate(path, ob, ends[period])
        assert rate == 100 and measured[period] == int(rate * (found.Y + found.E) * 100)
    measures = recognition.obligation_measures[SUBJECT]
    contract = next(
        view for view in state.allocated.contracts if view.header.external_id == "C-RET"
    )
    segment = ob.segments[-1]
    assert measures.returns_reduction == 30000 == segment.a_posted - measures.allocated_amount
    assert returns.reduction(ctx, state.allocated, contract, ob, segment, measures.as_of) == 30000
    (book,) = compute(bundle).books
    nodes = {node.id: node for node in book.trace.nodes}
    expected = nodes[f"return_expected_units:{SUBJECT}:{P02}"]
    assert Decimal(expected.value) == recognition.return_states[(SUBJECT, P02)].E == 1
    assert reevaluate(book.trace) == {node.id: node.value for node in book.trace.nodes}
    assert not [node.id for node in book.trace.nodes if "rollforward" in node.measure]
