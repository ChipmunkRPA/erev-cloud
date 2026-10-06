"""Foreign-currency deposit liability: JET-01b and JET-10d (L6-5; FX-CHK-084-B).

Stage 14 posts JET-01b receipt, criteria met and refund per ``<contract>@<entity>`` from the
stage 02 EMOD-12 targets, and S14-R-01 takes their functional amounts from stage 12. The book loop
bound the criteria-met transfer only as a period-end control flow and no receipt at all, so a EUR
receipt of a USD entity while ``NOT_A_CONTRACT`` raised ``ENGINE_INVARIANT_VIOLATED`` "stage 12
publishes no functional amount for a foreign-currency part target" (``deposit_received_cum``,
FY2026-P01), and the deposit was never remeasured (ENGINE_SPEC S02-R-08 rev 1.2; ENGINE_SPEC_B
S12-R-19, S12-R-20, EX-12-B; POLICIES CHK-084 (b)). The book loop now binds the dated stage 02
deposit movements; stage 12 creates the deposit layer at spot, remeasures it at the closing rate,
settles it at spot at criteria met and creates the contract-liability layer dated the transfer
(IFRIC 22.8).

The world is FX-CHK-084-B with ``CONTRACT_ACTIVATED`` after the collectibility assessment: the key
never activates, so the answer-key runner supplies the event (D-87 L6-5-Q-12 (i)). No database.
"""

from __future__ import annotations

import dataclasses
import decimal
from collections.abc import Callable
from datetime import date
from fractions import Fraction
from typing import cast

import erev_engine
import pytest
from erev_engine.bundle import InputBundle, OutputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.money import DECIMAL_CONTEXT
from erev_engine.stages import s13_books
from erev_engine.stages.s02_contract_identification import DepositPoint, IdentifiedState
from erev_engine.stages.state import BookContext
from support import intent_totals
from support.answer_keys import runners
from support.answer_keys.loader import ANSWER_KEY_ROOT, load

FX_084_B = "FX-CHK-084-B-DEPOSIT-LIABILITY-REMEASURED"
CONTRACT = "C-FX-084-B"
SUBJECT = f"{CONTRACT}@US01"
CL, DL, GAIN_LOSS, CLEARING = (
    "CONTRACT_LIABILITY",
    "DEPOSIT_LIABILITY",
    "FX_GAIN_LOSS",
    "BILLING_CLEARING",
)


def _activated(bundle: InputBundle) -> InputBundle:
    """The bundle with ``CONTRACT_ACTIVATED`` after the collectibility assessment (L6-5-Q-12); the
    runner already supplies it (D-87 L6-5-Q-12 (i)), so a bundle that has one is kept as built."""
    events = list(bundle.events)
    if any(event.event_type == "CONTRACT_ACTIVATED" for event in events):
        return bundle
    assessed = next(event for event in events if event.event_type == "COLLECTIBILITY_ASSESSED")
    payload = {"checklist": [dict(item) for item in runners.PASSING_CHECKLIST]}
    activation = dataclasses.replace(
        assessed,
        event_type="CONTRACT_ACTIVATED",
        event_key=f"{CONTRACT}/EV-000099",
        stream_version=99,
        payload=payload,
        payload_sha256=sha256_hex(payload),
    )
    events.insert(events.index(assessed) + 1, activation)
    return dataclasses.replace(bundle, events=tuple(events))


def _checkpoints() -> tuple[runners.LoadedKey, list[runners.CheckpointBundles]]:
    loaded = load(ANSWER_KEY_ROOT / "fx" / f"{FX_084_B}.yaml")
    out = []
    for checkpoint in runners._build_checkpoint_bundles(loaded):
        bundles = tuple(_activated(cast(InputBundle, bundle)) for bundle in checkpoint.bundles)
        out.append(dataclasses.replace(checkpoint, bundles=bundles))
    return loaded, out


def _lines(output: OutputBundle, period: str) -> list[tuple[str, str, str, int, int]]:
    """(entry kind, class, role, signed txn, signed functional) of the ASC606 ``period`` intents."""
    (book,) = [item for item in output.books if item.book_code == "ASC606"]
    return sorted(
        (
            intent.entry_kind,
            intent.posting_class,
            line.account_role,
            line.amount_txn if line.side == "D" else -line.amount_txn,
            line.amount_functional if line.side == "D" else -line.amount_functional,
        )
        for intent in book.posting_intents
        if intent.posting_period_key == period
        for line in intent.lines
    )


def _balance(output: OutputBundle, period: str) -> tuple[int, int, int, int]:
    (book,) = [item for item in output.books if item.book_code == "ASC606"]
    (row,) = [item for item in book.balances if item.period_key == period]
    columns = row.columns
    return (
        cast(int, columns["deposit_liability_txn"]),
        cast(int, columns["deposit_liability_functional"]),
        cast(int, columns["contract_liability_txn"]),
        cast(int, columns["contract_liability_functional"]),
    )


def test_l6_5_foreign_deposit_posts_jet_01b_at_spot_and_remeasures_the_deposit() -> None:
    """`january-close`: the EUR 1,000.00 receipt of 10 January posts JET-01b Dr BILLING_CLEARING /
    Cr DEPOSIT_LIABILITY USD 1,100.00 at compute; the pass remeasures the deposit at the January
    closing 1.1200 (JET-10d loss 20.00). `february-close`: criteria met on 15 February at spot
    1.1300 settles the deposit (JET-10d loss 10.00, EVENT) and posts JET-01b Dr DEPOSIT_LIABILITY /
    Cr CONTRACT_LIABILITY USD 1,130.00; T-CON-09 holds the contract liability at 1,130.00."""
    _loaded, (january, february) = _checkpoints()
    (bundle,) = january.bundles
    command = cast(OutputBundle, erev_engine.compute(bundle))
    assert _lines(command, "FY2026-P01") == [
        ("DEPOSIT", "EVENT", CLEARING, 100000, 110000),
        ("DEPOSIT", "EVENT", DL, -100000, -110000),
    ]
    with decimal.localcontext(DECIMAL_CONTEXT):
        remeasured = intent_totals.close_pass(bundle, [command], "FX_REMEASUREMENT")
    assert _lines(remeasured, "FY2026-P01") == [
        ("FX_REMEASUREMENT", "TIME", DL, 0, -2000),
        ("FX_REMEASUREMENT", "TIME", GAIN_LOSS, 0, 2000),
    ]
    assert _balance(command, "FY2026-P01") == (100000, 112000, 0, 0)
    (bundle,) = february.bundles
    command = cast(OutputBundle, erev_engine.compute(bundle))
    assert _lines(command, "FY2026-P02") == [
        ("DEPOSIT", "EVENT", CL, -100000, -113000),
        ("DEPOSIT", "EVENT", DL, 100000, 113000),
        ("FX_REMEASUREMENT", "EVENT", DL, 0, -1000),
        ("FX_REMEASUREMENT", "EVENT", GAIN_LOSS, 0, 1000),
    ]
    assert _balance(command, "FY2026-P02") == (0, 0, 100000, 113000)


def test_l6_5_deposit_checkpoints_match_once_the_contract_activates() -> None:
    """With the close passes and the activation of L6-5-Q-12, both checkpoints match the key."""
    loaded, checkpoints = _checkpoints()
    runs = tuple(
        runners._checkpoint_run(erev_engine.compute, checkpoint, runners.CLOSE_PASSES)
        for checkpoint in checkpoints
    )
    runners.assert_checkpoints(loaded, runners.RunResult(loaded.key.id, "engine", runs))


def _captured(
    monkeypatch: pytest.MonkeyPatch, bundle: InputBundle
) -> tuple[BookContext, s13_books.CostsView, IdentifiedState, s13_books.CostsView]:
    captured: list[tuple[BookContext, s13_books.CostsView, object, s13_books.CostsView]] = []
    original: Callable[[BookContext, s13_books.CostsView, object], s13_books.CostsView] = (
        s13_books._bind_deposit_flows
    )

    def capture(
        ctx: BookContext, view: s13_books.CostsView, identified: object
    ) -> s13_books.CostsView:
        bound = original(ctx, view, identified)
        captured.append((ctx, view, identified, bound))
        return bound

    monkeypatch.setattr(s13_books, "_bind_deposit_flows", capture)
    erev_engine.compute(bundle)
    ctx, view, identified, bound = captured[0]
    assert isinstance(identified, IdentifiedState)
    return ctx, view, identified, bound


def test_l6_5_deposit_flows_follow_the_stage_02_points(monkeypatch: pytest.MonkeyPatch) -> None:
    """The receipt binds as an increase at its date and the transfer as a decrease releasing to the
    control role at the criteria-met date, which replaces the period-end ``DEPOSIT_TRANSFER``
    control flow. A same-currency book binds nothing, and a termination that refunds and recognises
    keeps two flow keys (S02-R-07 (b))."""
    _loaded, (_january, february) = _checkpoints()
    (bundle,) = february.bundles
    ctx, view, identified, bound = _captured(monkeypatch, bundle)
    deposits = [flow for flow in bound.fx_flows.monetary if flow.role == DL]
    assert [
        (
            flow.reason,
            flow.direction,
            flow.control,
            flow.effective_date,
            flow.amount,
            flow.source_key,
        )
        for flow in deposits
    ] == [
        # The runner's CONTRACT_ACTIVATED is stream version 3 (D-87 L6-5-Q-12 (i)).
        ("RECEIPT", "INCREASE", None, date(2026, 1, 10), 100000, f"{CONTRACT}/EV-000004"),
        ("CRITERIA_MET", "DECREASE", "CREDIT", date(2026, 2, 15), 100000, f"{CONTRACT}/EV-000005"),
    ]
    assert {(flow.subject_key, flow.component_key) for flow in deposits} == {(SUBJECT, SUBJECT)}
    assert [flow.kind for flow in view.fx_flows.control] == ["DEPOSIT_TRANSFER"]
    assert [flow.kind for flow in bound.fx_flows.control] == []
    same = dataclasses.replace(ctx, txn_currency="USD")
    assert s13_books._bind_deposit_flows(same, view, identified) is view
    assert s13_books._bind_deposit_flows(ctx, view, None) is view
    on = date(2026, 3, 1)
    termination = (on, 5, f"{CONTRACT}/EV-000005")
    nothing = Fraction(0)
    points = (
        DepositPoint(
            (date(2026, 1, 10), 3, f"{CONTRACT}/EV-000003"), Fraction(100), *[nothing] * 3
        ),
        DepositPoint(termination, Fraction(100), Fraction(30), nothing, nothing),
        DepositPoint(termination, Fraction(100), Fraction(30), Fraction(70), nothing),
    )
    terminated = dataclasses.replace(identified, deposits={CONTRACT: points})
    flows = s13_books._deposit_flows(ctx, terminated, entities={"US01"})
    assert [(flow.reason, flow.direction, flow.amount, flow.flow_key) for flow in flows] == [
        ("RECEIPT", "INCREASE", 10000, f"{CONTRACT}/EV-000003#INCREASE@{SUBJECT}"),
        ("REFUND", "DECREASE", 3000, f"{CONTRACT}/EV-000005#DECREASE@{SUBJECT}"),
        (
            "EVENT_25_7",
            "DECREASE",
            7000,
            f"{CONTRACT}/EV-000005/deposit_to_revenue#DECREASE@{SUBJECT}",
        ),
    ]
    assert s13_books._deposit_flows(ctx, terminated, entities=()) == ()
