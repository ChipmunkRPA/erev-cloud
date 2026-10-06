"""An estimate in force at inception is in the inception price at every record position (item
ENG-INCEPTION-ESTIMATE-1; ENGINE_SPEC S01-R-18, S04-R-01, S08-R-01, S08-R-05).

The defect, found by lane QA-BE on the EX42 key run through the product. Stage 04 measures the
inception price before the first boundary event; stage 08 re-measures nothing at an
``ESTIMATE_CHANGED`` effective on or before the inception, because the inception measurement holds
its version; and ``EstimatePins.pin`` admitted a version only where its event preceded the
position. So an approved estimate dated at the inception never reached the transaction price when
another boundary event of that date — the Step 1 assessment the product records before the
activation, a significant-change flag, a line attribute change, an amendment — was recorded
before it. No finding and no diagnostic: the contract computed at its fixed price, or a later
change of the estimate was refused by an invariant.

The witnesses are oracle bundles of answer keys, read and never changed, with the stream the
product writes:

- ALC-S4-EX6 (FASB Example 6) — X and Y for 1,000.00 fixed and 200.00 variable: transaction price
  1,200.00, allocated 600.00 and 600.00; an amendment adds Z for 300.00 (X 600.00, Y and Z 450.00
  each) and the estimate then moves to 240.00 (X 620.00, Y and Z 460.00 each);
- DISC-S10-DISCLOSURES-RPO-EX42-TIME-BANDS-AND-EXPEDIENT, contract C-EX42-C — the stream of the
  finding: 2,400.00 fixed and a bonus constrained to 750.00, transaction price 3,150.00;
- STP1-S1-EX2 (FASB Example 2) — an implicit price concession of 600,000.00 on 1,000,000.00
  stated: transaction price 400,000.00.

With ONE more boundary event dated at the inception and recorded before the estimate change, at
either record position, every checkpoint of a key computes the figures of the key's own stream
to the cent — price, allocation, revenue and posting intents — in one inception build-up: the
estimate change stays no boundary (no ``tp_delta`` node of its own) and its pin node names no
replaced version. With the amendment of Example 6 dated at the inception and the estimate approved
after it, the key's figures stand as well, and the later change of the estimate is routed under
606-10-32-45 through that amendment. The last test is the same statement over every bundle of
the corpus. No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from collections.abc import Mapping
from datetime import date
from typing import Any

import erev_engine
import pytest
from erev_engine.bundle import EventInput, InputBundle, JudgementInput, OutputBundle
from support import bundles
from support.answer_keys import runners
from support.answer_keys.loader import ANSWER_KEY_ROOT, load, load_all

STEP_1 = "COLLECTIBILITY_ASSESSED"
FLAG = "SIGNIFICANT_CHANGE_FLAGGED"
ATTRIBUTES = "LINE_ATTRIBUTES_CHANGED"
KINDS = (STEP_1, FLAG, ATTRIBUTES)
EX6 = "alc/ALC-S4-EX6"
# "<family>/<key id>" -> (contract, transaction price, the version's ``vc_constrained_amount``,
# allocations) at the key's first checkpoint, in minor units
WITNESSES: Mapping[str, tuple[str, int, int, Mapping[str, int]]] = {
    EX6: ("C-EX6", 120000, 20000, {"L1-X": 60000, "L2-Y": 60000}),
    "disc/DISC-S10-DISCLOSURES-RPO-EX42-TIME-BANDS-AND-EXPEDIENT": (
        "C-EX42-C",
        315000,
        75000,
        {"C1-SERVICE": 315000},
    ),
    "stp1/STP1-S1-EX2": ("C-DRUG", 40000000, 60000000, {"L1-DRUG": 40000000}),
}


def _order(event: EventInput) -> tuple[date, int, str]:
    return event.effective_date, event.record_seq, event.event_key


def _inception_estimates(bundle: InputBundle) -> list[EventInput]:
    """The ``ESTIMATE_CHANGED`` events effective on or before the group inception, in ENG-06
    order."""
    return sorted(
        (
            event
            for event in bundle.events
            if event.event_type == "ESTIMATE_CHANGED"
            and event.effective_date <= bundle.group.inception_date
        ),
        key=_order,
    )


def _before(bundle: InputBundle, estimate: EventInput) -> list[EventInput]:
    """The events of the estimate's contract that precede ``estimate``, in ENG-06 order."""
    return sorted(
        (
            event
            for event in bundle.events
            if event.contract_key == estimate.contract_key and _order(event) < _order(estimate)
        ),
        key=_order,
    )


def _payload(
    bundle: InputBundle, kind: str, obligation_key: str, judgement_key: str
) -> dict[str, Any]:
    if kind == STEP_1:
        book = bundle.books[0].book_code
        return {"book": book, "is_probable": True, "judgement_record_id": judgement_key}
    if kind == ATTRIBUTES:
        return {
            "obligation_key": obligation_key,
            "changes": {"account_overrides": {"REVENUE": "4099"}},
            "diff": {"account_overrides.REVENUE": "4000 -> 4099"},
        }
    return {"description": "A flag recorded before the estimate of the same date."}


def with_boundary(bundle: InputBundle, kind: str, after: EventInput) -> InputBundle:
    """``bundle`` with one more boundary event of ``kind`` on the contract of ``after``, dated at
    the group inception and recorded right after ``after``. Every ``record_seq`` is doubled to
    make room; the events of the bundle keep their keys, the new one takes the next stream
    version of its contract. A Step 1 assessment comes with its judgement record."""
    contract = after.contract_key
    events = [
        dataclasses.replace(event, record_seq=event.record_seq * 2) for event in bundle.events
    ]
    own = [event for event in events if event.contract_key == contract]
    booking = next(event for event in own if event.event_type == "CONTRACT_BOOKED")
    lines = booking.payload["lines"]
    assert isinstance(lines, list | tuple)
    obligation_key = str(lines[0]["obligation_key"])
    judgement_key = f"{contract}/JDG-STEP-1"
    added = dataclasses.replace(
        bundles.event(
            contract,
            max(event.stream_version for event in own) + 1,
            kind,
            bundle.group.inception_date,
            _payload(bundle, kind, obligation_key, judgement_key),
            record_seq=after.record_seq * 2 + 1,
            obligation_keys=(obligation_key,) if kind == ATTRIBUTES else (),
        ),
        recorded_at=after.recorded_at,
    )
    contracts = bundle.contracts
    if kind == STEP_1:
        judgement = JudgementInput(
            judgement_key=judgement_key,
            topic="COLLECTIBILITY",
            subject_key=contract,
            book_code=None,
            outcome={},
        )
        contracts = tuple(
            dataclasses.replace(
                header,
                judgements=tuple(
                    sorted((*header.judgements, judgement), key=lambda item: item.judgement_key)
                ),
            )
            if header.external_id == contract
            else header
            for header in contracts
        )
    return dataclasses.replace(
        bundle, events=tuple(sorted([*events, added], key=_order)), contracts=contracts
    )


def amended_at_inception(bundle: InputBundle) -> InputBundle:
    """``bundle`` with its amendment and the amendment's modification dated at the group
    inception — the record position kept — and the estimate change of the inception recorded
    right after the amendment: the estimate is approved after the contract was amended on its
    first day. Both are recorded when the last event of that day was."""
    inception = bundle.group.inception_date
    (amendment,) = [event for event in bundle.events if event.event_type == "CONTRACT_AMENDED"]
    (estimate,) = _inception_estimates(bundle)
    recorded = max(
        event.recorded_at for event in bundle.events if event.effective_date == inception
    )
    events = []
    for event in bundle.events:
        moved = dataclasses.replace(event, record_seq=event.record_seq * 2)
        if event.event_key == amendment.event_key:
            moved = dataclasses.replace(moved, effective_date=inception, recorded_at=recorded)
        elif event.event_key == estimate.event_key:
            moved = dataclasses.replace(
                moved, record_seq=amendment.record_seq * 2 + 1, recorded_at=recorded
            )
        events.append(moved)
    contracts = tuple(
        dataclasses.replace(
            header,
            modifications=tuple(
                dataclasses.replace(modification, effective_date=inception)
                for modification in header.modifications
            ),
        )
        for header in bundle.contracts
    )
    return dataclasses.replace(
        bundle, events=tuple(sorted(events, key=_order)), contracts=contracts
    )


def figures(output: OutputBundle) -> tuple[Any, ...]:
    """What a computation measured, by book: the version's price columns, every obligation's
    allocation and cumulative revenue, and the posting intents summed by period, role and side."""
    books = []
    for book in output.books:
        version = None if book.contract_version is None else book.contract_version.columns
        head = (
            None
            if version is None
            else tuple(
                version.get(name)
                for name in (
                    "transaction_price",
                    "vc_constrained_amount",
                    "vc_excluded_amount",
                    "revenue_cum",
                    "rpo_amount",
                )
            )
        )
        obligations = tuple(
            sorted(
                (
                    item.subject_key,
                    item.columns.get("allocated_amount"),
                    item.columns.get("revenue_cum"),
                )
                for item in book.obligation_versions
            )
        )
        posted: Counter[tuple[str, str, str]] = Counter()
        for intent in book.posting_intents:
            for line in intent.lines:
                key = (intent.posting_period_key, line.account_role, line.side)
                posted[key] += int(line.amount_txn)
        books.append((book.book_code, head, obligations, tuple(sorted(posted.items()))))
    return tuple(books)


def _price(output: OutputBundle) -> tuple[int, int, dict[str, int]]:
    """Transaction price, ``vc_constrained_amount`` and allocations of the first book."""
    book = output.books[0]
    assert book.contract_version is not None
    columns = book.contract_version.columns
    allocations = {
        item.subject_key.split("/")[-1]: item.columns["allocated_amount"]
        for item in book.obligation_versions
    }
    return columns["transaction_price"], columns["vc_constrained_amount"], allocations


def _nodes(output: OutputBundle, prefix: str) -> list[tuple[str, str, str]]:
    """(measure, value, formula) of the trace nodes whose measure starts with ``prefix``."""
    return sorted(
        (node.measure, node.value, node.formula_id)
        for book in output.books
        for node in book.trace.nodes
        if node.measure.startswith(prefix)
    )


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("key", sorted(WITNESSES))
def test_an_estimate_at_inception_behind_another_boundary_is_in_the_inception_price(
    key: str, kind: str
) -> None:
    contract, price, variable, allocations = WITNESSES[key]
    checkpoints = runners._build_checkpoint_bundles(load(ANSWER_KEY_ROOT / f"{key}.yaml"))
    for number, checkpoint in enumerate(checkpoints):
        (oracle,) = [b for b in checkpoint.bundles if contract in b.group.member_contract_keys]
        own = erev_engine.compute(oracle)
        if number == 0:
            assert _price(own) == (price, variable, allocations)
        estimate = _inception_estimates(oracle)[0]
        earlier = _before(oracle, estimate)
        assert [event.event_type for event in earlier] == ["CONTRACT_BOOKED", "CONTRACT_ACTIVATED"]
        for after in earlier:  # either record position before the estimate change
            output = erev_engine.compute(with_boundary(oracle, kind, after))
            at = (checkpoint.name, after.event_type)
            assert figures(output) == figures(own), at
            # one inception build-up: the estimate change is no boundary of its own, and the
            # version it applies replaces none
            assert _nodes(output, "tp_delta@") == _nodes(own, "tp_delta@"), at
            assert not _nodes(output, f"tp_delta@{estimate.event_key}"), at
            pins = [
                node
                for book in output.books
                for node in book.trace.nodes
                if node.measure == f"estimate_pin@{estimate.event_key}"
            ]
            assert pins and all(node.params["v_old"] == "-" for node in pins), at
            assert [d.code for d in output.diagnostics] == [d.code for d in own.diagnostics], at


def test_an_estimate_approved_after_an_inception_amendment_is_in_the_inception_price() -> None:
    """FASB Example 6 with the amendment dated at the inception — X is transferred, then the
    contract is amended, then the estimate of the inception is approved. The version is in the
    inception price (X keeps 600.00 of 1,200.00), the amendment pools Y's 600.00 with Z's 300.00,
    and the later change of the estimate by 40.00 is routed under 606-10-32-45 through the
    amendment: 20.00 to X, and Y's 20.00 over Y and Z. Every checkpoint gives the key's own
    figures. Before the repair the version was lost (1,300.00, no variable consideration) and
    the later change was refused by S04-R-02."""
    checkpoints = runners._build_checkpoint_bundles(load(ANSWER_KEY_ROOT / f"{EX6}.yaml"))
    amended = {
        checkpoint.name: checkpoint.bundles[0]
        for checkpoint in checkpoints
        if any(event.event_type == "CONTRACT_AMENDED" for event in checkpoint.bundles[0].events)
    }
    assert list(amended) == [
        "after-modification",
        "after-vc-change",
        "y-transferred",
        "z-transferred-and-invoiced",
    ]
    outputs = {}
    for name, oracle in amended.items():
        stream = amended_at_inception(oracle)
        inception = [
            event.event_type
            for event in stream.events
            if event.effective_date == stream.group.inception_date
        ]
        assert inception == [
            "CONTRACT_BOOKED",
            "CONTRACT_ACTIVATED",
            "DELIVERY_RECORDED",
            "CONTRACT_AMENDED",
            "ESTIMATE_CHANGED",
        ]
        outputs[name] = erev_engine.compute(stream)
        assert figures(outputs[name]) == figures(erev_engine.compute(oracle)), name
    assert _price(outputs["after-modification"]) == (
        150000,
        20000,
        {"L1-X": 60000, "L2-Y": 45000, "L3-Z": 45000},
    )
    changed = outputs["after-vc-change"]
    assert _price(changed) == (154000, 24000, {"L1-X": 62000, "L2-Y": 46000, "L3-Z": 46000})
    assert [(value, formula) for _, value, formula in _nodes(changed, "tp_delta@")] == [
        ("40.00", "estimate.tp_delta.v1")
    ]
    assert {formula for _, _, formula in _nodes(changed, "tp_share@")} == {
        "estimate.route.32_45.v1"
    }


@pytest.mark.slow
def test_no_key_bundle_moves_when_a_boundary_precedes_its_inception_estimate() -> None:
    """The corpus-wide form: for every checkpoint bundle of every active engine key that holds an
    ``ESTIMATE_CHANGED`` effective on or before its group inception, a Step 1 assessment, a
    significant-change flag or a line attribute change dated at the inception and recorded just
    before the first such estimate change moves no figure. Before the repair one flag made 30 of
    these bundles compute other figures in silence and 38 fail an engine invariant (lane ENG-FX's
    sweep of 2026-10-01 over 349 bundles of 247 keys)."""
    compared = 0
    moved: list[str] = []
    for loaded in load_all():
        if loaded.key.runner != "engine":
            continue
        for number, checkpoint in enumerate(runners._build_checkpoint_bundles(loaded)):
            for bundle in checkpoint.bundles:
                estimates = _inception_estimates(bundle)
                if not estimates:
                    continue
                compared += 1
                own = figures(erev_engine.compute(bundle))
                after = _before(bundle, estimates[0])[-1]
                for kind in KINDS:
                    if figures(erev_engine.compute(with_boundary(bundle, kind, after))) != own:
                        moved.append(
                            f"{kind} {loaded.key.id} checkpoint {number} {bundle.group.group_key}"
                        )
    assert moved == []
    # the bundles with such an estimate change on 2026-10-01; the count grows with the key files
    assert compared >= 349
