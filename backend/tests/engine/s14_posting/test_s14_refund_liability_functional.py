"""Foreign-currency refund liability: JET-04b and T-CON-09 functional amounts (L6-5; CHK-084 a).

Stage 14 posts JET-04b per refund-liability component and S14-R-01 takes its functional amount from
stage 12, which layered the component (S12-R-19, S12-R-20) but published no functional target, so a
EUR returns estimate of a USD entity raised ``ENGINE_INVARIANT_VIOLATED`` "stage 12 publishes no
functional amount for a foreign-currency part target" (``refund_liability``, FY2026-P03), and
T-CON-09 held no ``refund_liability_functional``.

The world is FX-CHK-084-A with the invoice line naming ``L1-GADGET``: as keyed, the obligation's
billing arrives unreferenced and stage 01 refuses the referenced credit memo with
``REFUND_EXCEEDS_BILLED`` (L6-5-Q-15). ``may-close`` expires the right on ``window_end_date``
(D-87 L6-5-Q-25). No database.
"""

from __future__ import annotations

import dataclasses
import decimal
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import erev_engine
import pytest
import yaml
from erev_engine.bundle import BookOutput, EventInput, InputBundle, OutputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.errors import EngineError
from erev_engine.money import DECIMAL_CONTEXT
from erev_engine.trace import reevaluate
from support import intent_totals
from support.answer_keys import runners
from support.answer_keys.loader import ANSWER_KEY_ROOT, load, parse_yaml

FX_084_A = "FX-CHK-084-A-REFUND-LIABILITY-REMEASURED"
CL, RL, GAIN_LOSS = "CONTRACT_LIABILITY", "REFUND_LIABILITY", "FX_GAIN_LOSS"


def _checkpoints() -> tuple[runners.LoadedKey, list[runners.CheckpointBundles]]:
    loaded = load(ANSWER_KEY_ROOT / "fx" / f"{FX_084_A}.yaml")
    out = []
    for checkpoint in runners._build_checkpoint_bundles(loaded):
        bundles = []
        for bundle in checkpoint.bundles:
            events = []
            for event in cast(InputBundle, bundle).events:
                if event.event_type == "BILLING_RECORDED" and "obligation_key" not in event.payload:
                    payload = {**event.payload, "obligation_key": "L1-GADGET"}
                    event = dataclasses.replace(
                        event, payload=payload, payload_sha256=sha256_hex(payload)
                    )
                events.append(event)
            bundles.append(dataclasses.replace(cast(InputBundle, bundle), events=tuple(events)))
        out.append(dataclasses.replace(checkpoint, bundles=tuple(bundles)))
    return loaded, out


def _lines(output: OutputBundle, kind: str, period: str) -> list[tuple[str, str, int, int]]:
    (book,) = [item for item in output.books if item.book_code == "ASC606"]
    return sorted(
        (
            intent.posting_class,
            line.account_role,
            line.amount_txn if line.side == "D" else -line.amount_txn,
            line.amount_functional if line.side == "D" else -line.amount_functional,
        )
        for intent in book.posting_intents
        if intent.entry_kind == kind and intent.posting_period_key == period
        for line in intent.lines
    )


def test_l6_5_foreign_refund_liability_posts_jet_04b_at_the_historical_relief() -> None:
    """`march-close`: the EUR 300.00 returns estimate posts JET-04b Dr CONTRACT_LIABILITY / Cr
    REFUND_LIABILITY USD 330.00 at compute (the contract-liability layer at 1.1000; no recognition
    difference); the pass remeasures the component at the March closing 1.1200 (JET-10d loss 6.00),
    and T-CON-09 holds the refund liability at USD 336.00."""
    _loaded, checkpoints = _checkpoints()
    (bundle,) = checkpoints[0].bundles
    command = cast(OutputBundle, erev_engine.compute(bundle))
    assert _lines(command, RL, "FY2026-P03") == [
        ("EVENT", CL, 30000, 33000),
        ("EVENT", RL, -30000, -33000),
    ]
    with decimal.localcontext(DECIMAL_CONTEXT):
        remeasured = intent_totals.close_pass(bundle, [command], "FX_REMEASUREMENT")
    assert _lines(remeasured, "FX_REMEASUREMENT", "FY2026-P03") == [
        ("TIME", GAIN_LOSS, 0, 600),
        ("TIME", RL, 0, -600),
    ]
    (book,) = [item for item in command.books if item.book_code == "ASC606"]
    (row,) = [item for item in book.balances if item.period_key == "FY2026-P03"]
    assert (row.columns["refund_liability_txn"], row.columns["refund_liability_functional"]) == (
        30000,
        33600,
    )


def test_l6_5_refund_liability_checkpoints_match_through_april() -> None:
    """With the close passes, `march-close` and `april-close` match the key (the 15 April return
    releases 230.00 at spot, loss 6.00 at settlement and gain 4.00 at the April closing), and
    `may-close` matches the expiry on the window-end date (D-87 L6-5-Q-25: revenue 9,800.00,
    refund liability nil, JET-10d loss 2.00)."""
    loaded, checkpoints = _checkpoints()
    runs = tuple(
        runners._checkpoint_run(erev_engine.compute, checkpoint, runners.CLOSE_PASSES)
        for checkpoint in checkpoints
    )
    runners.assert_checkpoints(loaded, runners.RunResult(loaded.key.id, "engine", runs))


# --- D-91 C606-01: the refund liability after a status update, by billing mode (full compute) -----
#
# World W1 through ``erev_engine.compute`` on the RET-CHK-029 end-of-january bundle rewritten by the
# answer-key assembler: the invoice a 1,000.00 cancellable line INV-RET-1 / INV-RET-1-1 dated 10
# Jan, E 20 (rate 0.20), POL-004 per case; the 20 Jan same-amount noncancellable repeat injected
# with a canonical key. Figures derived in .run/l9/d91-c606-01/derive.py: revenue 8,000.00 in every
# run; ERP: REFUND_LIABILITY net credit 1,000.00, billed_cum 1,000.00, position −8,000.00 (a
# contract asset of 8,000.00) with and without the update; ENGINE without the update RL 0.00 /
# billed_cum 0 / −8,000.00, with it 1,000.00 / 1,000.00 / −8,000.00. Main posted RL 2,000.00 and
# −9,000.00 (ERP with update) and RL 1,000.00 and −9,000.00 (ENGINE without update).

RET_029 = ANSWER_KEY_ROOT / "ret" / "RET-CHK-029-S3-EX22.yaml"
C_RET = "C-RET"
JAN20 = date(2026, 1, 20)
BASIS = {"ERP": "ERP_POSTED_INVOICES", "ENGINE": "UNCONDITIONAL_INVOICES_ONLY"}


def _january(path: Path = RET_029, name: str = "end-of-january") -> InputBundle:
    checkpoint = next(c for c in runners._build_checkpoint_bundles(load(path)) if c.name == name)
    (bundle,) = checkpoint.bundles
    return cast(InputBundle, bundle)


def _in_mode(bundle: InputBundle, mode: str) -> InputBundle:
    """POL-004 ``mode`` in every period (pin P), and POL-123 to match when the bundle holds it."""
    books = []
    for book in bundle.books:
        policies = []
        for policy in book.policies:
            if policy.code == "billing.posting":
                policy = dataclasses.replace(policy, value=mode)
            elif policy.code == "balance.position_invoice_basis":
                policy = dataclasses.replace(policy, value=BASIS[mode])
            policies.append(policy)
        books.append(dataclasses.replace(book, policies=tuple(policies)))
    return dataclasses.replace(bundle, books=tuple(books))


def _billing(
    base: EventInput,
    seq: int,
    on: date,
    *,
    cancellable: bool,
    amount: str = "1000.00",
    key: str | None = "L1-PROD",
) -> EventInput:
    payload = {
        **{k: v for k, v in base.payload.items() if k != "obligation_key"},
        "amount": Decimal(amount),
        "is_cancellable": cancellable,
    }
    if key is not None:
        payload["obligation_key"] = key
    return dataclasses.replace(
        base,
        event_key=f"{base.contract_key}/EV-{seq:06d}",
        record_seq=seq,
        stream_version=seq,
        effective_date=on,
        recorded_at=datetime(on.year, on.month, on.day, 17, tzinfo=UTC),
        obligation_keys=() if key is None else (key,),
        payload=payload,
        payload_sha256=sha256_hex(payload),
    )


def _w1(mode: str, *, direct: bool = True, extra: tuple[EventInput, ...] = ()) -> InputBundle:
    """The W1 bundle: the invoice a 1,000.00 cancellable line (direct or unreferenced), E 20."""
    bundle = _in_mode(_january(), mode)
    bill = next(e for e in bundle.events if e.event_type == "BILLING_RECORDED")
    line = _billing(
        bill,
        bill.record_seq,
        bill.effective_date,
        cancellable=True,
        key="L1-PROD" if direct else None,
    )
    events = tuple(
        sorted(
            (*(line if e is bill else e for e in bundle.events), *extra),
            key=lambda e: (e.effective_date, e.record_seq, e.event_key),
        )
    )
    estimates = tuple(
        dataclasses.replace(v, expected_quantity=Decimal("20"), rate=Decimal("0.20"))
        if v.estimate_kind == "RETURN_RATE"
        else v
        for v in bundle.estimate_versions
    )
    known_at = max([bundle.known_at, *(e.recorded_at for e in events)])
    return dataclasses.replace(
        bundle, events=events, estimate_versions=estimates, known_at=known_at
    )


def _bill_of(bundle: InputBundle) -> EventInput:
    return next(e for e in bundle.events if e.event_type == "BILLING_RECORDED")


def _compute(bundle: InputBundle) -> BookOutput:
    """The ASC606 book; no diagnostic; every trace node re-evaluates (PROP:P14; DG-AK-54)."""
    output = cast(OutputBundle, erev_engine.compute(bundle))
    assert output.diagnostics == ()
    (book,) = [item for item in output.books if item.book_code == "ASC606"]
    assert reevaluate(book.trace) == {node.id: node.value for node in book.trace.nodes}
    return book


def _refund_liability(book: BookOutput, period: str = "FY2026-P01") -> int:
    """Net credit posted to REFUND_LIABILITY in ``period`` (minor units)."""
    return sum(
        line.amount_txn if line.side == "C" else -line.amount_txn
        for intent in book.posting_intents
        if intent.posting_period_key == period
        for line in intent.lines
        if line.account_role == "REFUND_LIABILITY"
    )


def _figures(
    book: BookOutput, contract: str = C_RET, period: str = "FY2026-P01"
) -> tuple[int, int, int, int]:
    """(revenue_cum, billed_cum, contract asset, contract liability) of the contract at a period
    end."""
    assert book.contract_version is not None
    (row,) = [
        b for b in book.balances if b.subject_key == f"{contract}@US01" and b.period_key == period
    ]
    return (
        cast(int, book.contract_version.columns["revenue_cum"]),
        cast(int, book.contract_version.columns["billed_cum"]),
        cast(int, row.columns["contract_asset_txn"]),
        cast(int, row.columns["contract_liability_txn"]),
    )


@pytest.mark.parametrize("direct", [True, False], ids=["direct", "unreferenced"])
@pytest.mark.parametrize("mode", ["ERP", "ENGINE"])
def test_d91_refund_liability_after_status_update_by_mode(mode: str, direct: bool) -> None:
    """D-91 C606-01 (4) and (5). Revenue 8,000.00 in every run. ERP: refund liability 1,000.00,
    billed_cum 1,000.00 and a contract asset of 8,000.00 (position −8,000.00) with and without the
    update. ENGINE without the update: the cancellable unpaid line is memo-only, RL 0.00, billed_cum
    0, position −8,000.00; with the update RL 1,000.00, billed_cum 1,000.00, −8,000.00. A 900.00
    update is ``INVOICE_STATUS_UPDATE_MISMATCH`` (CV-15) in every mode; an ERP repeated cancellable
    identity bills 2,000.00 and refunds 2,000.00."""
    base = _w1(mode, direct=direct)
    bill = _bill_of(base)
    update = _billing(bill, 6, JAN20, cancellable=False, key="L1-PROD" if direct else None)
    without = _compute(base)
    updated = _compute(_w1(mode, direct=direct, extra=(update,)))
    counted = mode == "ERP"
    assert (_refund_liability(without), _figures(without)) == (
        100_000 if counted else 0,
        (800_000, 100_000 if counted else 0, 800_000, 0),
    )
    assert (_refund_liability(updated), _figures(updated)) == (
        100_000,
        (800_000, 100_000, 800_000, 0),
    )
    mismatched = _billing(
        bill, 6, JAN20, cancellable=False, amount="900.00", key="L1-PROD" if direct else None
    )
    with pytest.raises(EngineError) as raised:
        _compute(_w1(mode, direct=direct, extra=(mismatched,)))
    assert raised.value.code == "INVOICE_STATUS_UPDATE_MISMATCH"
    if mode == "ERP":
        repeat = _billing(bill, 6, JAN20, cancellable=True, key="L1-PROD" if direct else None)
        doubled = _compute(_w1(mode, direct=direct, extra=(repeat,)))
        assert (_refund_liability(doubled), _figures(doubled)) == (
            200_000,
            (800_000, 200_000, 800_000, 0),
        )


TWO_OBLIGATIONS_ID = "RET-CHK-029-D91-TWO-OBLIGATIONS-A-TO-B"  # DG-AK-04: contains CHK-029


def _two_obligation_key(tmp_path: Path) -> Path:
    """RET-CHK-029's world with two returnable obligations L1-PROD and L2-PROD (100 units at 100.00
    each, E 20 each) and one 1,000.00 cancellable line INV-RET-1 on L1-PROD, written as a scratch
    key so the assembler builds the bundle (DG-AK-40); no checkpoint values are asserted from it."""
    data = cast(dict[str, object], parse_yaml(RET_029.read_text(encoding="utf-8"), path=RET_029))
    data["id"] = TWO_OBLIGATIONS_ID
    data["title"] = "D-91 C606-01 two-obligation A→B status update world (test scratch key)"
    data["summary"] = (
        "Test scratch world for test_d91_status_update_naming_another_obligation_full_compute."
    )
    contract = cast(dict[str, object], cast(list[object], data["contracts"])[0])
    contract["external_id"] = "C-RET-2"
    lines = cast(list[dict[str, object]], contract["lines"])
    lines.append({**lines[0], "obligation_key": "L2-PROD"})
    estimates = cast(list[dict[str, object]], contract["estimates"])
    version = cast(dict[str, object], cast(list[object], estimates[0]["versions"])[0])
    version["rate"], version["expected_quantity"] = "0.20", "20"
    second = yaml.safe_load(yaml.safe_dump(estimates[0]))
    second["element_code"], second["obligation_key"] = "RET-L2", "L2-PROD"
    estimates.append(second)

    def event(seq: int, event_type: str, on: str, payload: dict[str, object]) -> dict[str, object]:
        return {
            "seq": seq,
            "kind": "event",
            "contract": "C-RET-2",
            "event_type": event_type,
            "effective_date": on,
            "payload": payload,
        }

    data["timeline"] = [
        event(1, "CONTRACT_BOOKED", "2026-01-10", {}),
        event(2, "CONTRACT_ACTIVATED", "2026-01-10", {}),
        event(3, "ESTIMATE_CHANGED", "2026-01-10", {"estimate": "RET-JAN", "version_no": "1"}),
        event(4, "ESTIMATE_CHANGED", "2026-01-10", {"estimate": "RET-L2", "version_no": "1"}),
        event(
            5,
            "DELIVERY_RECORDED",
            "2026-01-10",
            {"obligation_key": "L1-PROD", "quantity": "100", "trigger": "DELIVERY"},
        ),
        event(
            6,
            "DELIVERY_RECORDED",
            "2026-01-10",
            {"obligation_key": "L2-PROD", "quantity": "100", "trigger": "DELIVERY"},
        ),
        event(
            7,
            "BILLING_RECORDED",
            "2026-01-10",
            {
                "invoice_number": "INV-RET-1",
                "line_external_id": "INV-RET-1-1",
                "obligation_key": "L1-PROD",
                "amount": "1000.00",
                "issue_date": "2026-01-10",
                "is_cancellable": True,
            },
        ),
    ]
    data["checkpoints"] = [
        {"name": "end-of-january", "after_seq": 7, "as_of": "2026-01-31", "book": "ASC606"}
    ]
    path = tmp_path / "ret" / f"{TWO_OBLIGATIONS_ID}.yaml"
    path.parent.mkdir()
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _obligation_column(book: BookOutput, subject: str, column: str) -> int:
    (version,) = [v for v in book.obligation_versions if v.subject_key == subject]
    return cast(int, version.columns[column])


def _return_component(book: BookOutput, subject: str, period: str = "FY2026-P01") -> str:
    (node,) = [
        n
        for n in book.trace.nodes
        if n.id.endswith(f"/RETURN/{subject}:{period}") and n.id.startswith("refund_liability:")
    ]
    return node.value


@pytest.mark.parametrize("mode", ["ERP", "ENGINE"])
def test_d91_status_update_naming_another_obligation_full_compute(
    mode: str, tmp_path: Path
) -> None:
    """D-91 C606-01 (3), Codex six public cases: two returnable obligations L1-PROD / L2-PROD (100
    units at 100.00 each, E 20 each); INV-RET-1 1,000.00 cancellable on L1-PROD; a 20 Jan update
    naming L2-PROD is blocked by ``INVOICE_STATUS_UPDATE_MISMATCH``. Control (the update naming
    L1-PROD, or none): the RETURN component is 1,000.00 on L1 and 0 on L2 (ENGINE without the
    update: memo-only, 0 on both), billed_cum L1 1,000.00 / L2 0 (ENGINE without update 0 / 0),
    revenue
    8,000.00 each, position −16,000.00 (a contract asset of 16,000.00). Main attributed 1,000.00 to
    both (−17,000.00)."""
    bundle = _in_mode(_january(_two_obligation_key(tmp_path)), mode)
    bill = _bill_of(bundle)
    with pytest.raises(EngineError) as raised:
        _compute(_with(bundle, _billing(bill, 8, JAN20, cancellable=False, key="L2-PROD")))
    assert raised.value.code == "INVOICE_STATUS_UPDATE_MISMATCH"
    l1, l2 = "C-RET-2/L1-PROD", "C-RET-2/L2-PROD"
    for label, extra in (
        ("update naming L1", (_billing(bill, 8, JAN20, cancellable=False, key="L1-PROD"),)),
        ("no update", ()),
    ):
        book = _compute(_with(bundle, *extra))
        counted = mode == "ERP" or bool(extra)
        assert (_return_component(book, l1), _return_component(book, l2)) == (
            "1000.00" if counted else "0.00",
            "0.00",
        ), label
        assert (
            _obligation_column(book, l1, "billed_cum"),
            _obligation_column(book, l2, "billed_cum"),
        ) == (
            100_000 if counted else 0,
            0,
        ), label
        assert (
            _obligation_column(book, l1, "revenue_cum"),
            _obligation_column(book, l2, "revenue_cum"),
        ) == (
            800_000,
            800_000,
        ), label
        assert _figures(book, "C-RET-2")[2:] == (1_600_000, 0), label
        assert _refund_liability(book) == (100_000 if counted else 0), label


def _with(bundle: InputBundle, *extra: EventInput) -> InputBundle:
    events = tuple(
        sorted(
            (*bundle.events, *extra), key=lambda e: (e.effective_date, e.record_seq, e.event_key)
        )
    )
    known_at = max([bundle.known_at, *(e.recorded_at for e in events)])
    return dataclasses.replace(bundle, events=events, known_at=known_at)
