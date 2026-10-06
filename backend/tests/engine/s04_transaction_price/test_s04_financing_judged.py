"""S04-R-10a: a significant financing component judged without a payment schedule (D-87 L5-3-Q-8).

With no payment schedule in force and a reviewed ``SFC_ASSESSMENT`` with ``significant = true`` and
``exception_32_17 = NONE``, the payment points are the contract's receipts, else its billing less
credit memos (trace ``reason = JUDGEMENT_SIGNIFICANT``, ``payment_source``). A point-in-time
transfer is the line start date, else the delivery at which net delivered reaches the quantity,
else open: the advance accretes with no relief and no CSP. The advance CSP is
X = Σ pay_i·v^(n_i) ÷ Σ_k g_k·v^k, and B_k = B_(k−1)(1 + j) + pay_k − X·g_k settles at the last
revenue month. Before the fix every figure below stayed at the stated price with no interest
(SFC-FS-11-CASEB 270,000.00; SFC-S3-EX29 4,000.00).

The worlds are the answer keys, built by the engine runner; no database.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast

import erev_engine
import pytest
from erev_engine.bundle import BookOutput, EventInput, InputBundle, OutputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.errors import EngineError
from erev_engine.trace import SourceRef, TraceNode, reevaluate
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles
from support.billing_lines import with_events


def _book(path: str, name: str) -> tuple[BookOutput, dict[str, TraceNode], dict[str, str]]:
    checkpoint = next(
        c for c in _build_checkpoint_bundles(load(ANSWER_KEY_ROOT / path)) if c.name == name
    )
    (bundle,) = checkpoint.bundles
    output = cast(OutputBundle, erev_engine.compute(cast(InputBundle, bundle)))
    (book,) = [b for b in output.books if b.book_code == checkpoint.book]
    nodes = {node.id: node for node in book.trace.nodes}
    return book, nodes, dict(reevaluate(book.trace))


def _values(nodes: dict[str, TraceNode], again: dict[str, str], *ids: str) -> list[str]:
    for node_id in ids:
        assert again[node_id] == nodes[node_id].value, node_id  # DG-AK-54
    return [nodes[node_id].value for node_id in ids]


def test_l7_5_over_time_advance_relieved_by_revenue_shares() -> None:
    # SFC-FS-11-CASEB: 270,000.00 received on 1 January 2026 for 36 months of service, 6% monthly.
    book, nodes, again = _book(
        "sfc/SFC-FS-11-CASEB-UPFRONT-ADVANCE-ACCRETION.yaml", "first-year-end"
    )
    gap = nodes["financing_gap_test:FS-11/L1-SUB:-"]
    assert (gap.params["reason"], gap.params["payment_source"], gap.params["adjust"]) == (
        "JUDGEMENT_SIGNIFICANT",
        "PAYMENT_RECEIVED",
        "true",
    )
    csp = nodes["cash_selling_price:FS-11/L1-SUB:-"]
    assert (csp.params["kind"], csp.params["counts"]) == ("ADVANCE", "0")
    assert csp.params["shares"] == ",".join(f"{k}:1/36" for k in range(1, 37))
    assert _values(
        nodes,
        again,
        "cash_selling_price:FS-11/L1-SUB:-",
        "financing_adjustment_amount:CG-FS-11:-",
        "financing_interest_cum:FS-11@FS-US:FY2026-P01",
        "financing_interest_cum:FS-11@FS-US:FY2026-P12",
        "financed_balance:FS-11@FS-US:FY2026-P12",
    ) == ["295701.23", "25701.23", "1350.00", "13896.73", "185329.65"]
    assert book.contract_version is not None
    assert book.contract_version.columns["transaction_price"] == 29_570_123  # minor units


def test_l7_5_point_in_time_advance_open_until_delivery() -> None:
    # SFC-S3-EX29: 4,000.00 billed on 1 January 2026, no start date, delivered on 31 December 2027.
    _, nodes, again = _book("sfc/SFC-S3-EX29.yaml", "end-of-january-2026")
    gap = nodes["financing_gap_test:C-FIN-ADV/L1-ASSET:-"]
    assert (gap.params["reason"], gap.params["payment_source"], gap.params["transfer_open"]) == (
        "JUDGEMENT_SIGNIFICANT",
        "BILLING_RECORDED",
        "true",
    )
    assert not any(node_id.startswith("cash_selling_price:") for node_id in nodes)
    assert _values(
        nodes,
        again,
        "financing_interest_cum:C-FIN-ADV@US01:FY2026-P01",
        "financed_balance:C-FIN-ADV@US01:FY2026-P01",
    ) == ["20.00", "4020.00"]
    _, delivered, again = _book("sfc/SFC-S3-EX29.yaml", "transfer")
    assert "transfer_open" not in delivered["financing_gap_test:C-FIN-ADV/L1-ASSET:-"].params
    assert _values(
        delivered,
        again,
        "cash_selling_price:C-FIN-ADV/L1-ASSET:-",
        "financing_interest_cum:C-FIN-ADV@US01:FY2026-P12",
        "financing_interest_cum:C-FIN-ADV@US01:FY2027-P12",
    ) == ["4508.64", "246.71", "508.64"]


def test_l7_5_not_significant_judgement_keeps_no_adjustment() -> None:
    # SFC-FS-11-CASEA: the judgement concludes no significant financing component.
    _, nodes, _ = _book("sfc/SFC-FS-11-CASEA-UPFRONT-NO-FINANCING.yaml", "first-year-end")
    gap = nodes["financing_gap_test:FS-11/L1-SUB:-"]
    assert (gap.params["reason"], "payment_source" in gap.params) == ("NO_PAYMENT_SCHEDULE", False)
    assert nodes["financing_adjustment_amount:CG-FS-11:-"].value == "0.00"


# --- D-91 C606-05: an S10-R-07 status update adds no S04-R-10a payment point ---------------------
#
# World: SFC-S3-EX29 (4,000.00 billed 1 January 2026, 6 % MONTHLY, transfer 31 December 2027) with
# events appended to the runner-built bundle through dataclasses.replace (public compute, canonical
# keys, known_at advanced so no diagnostic is raised). Figures derived in
# .run/l9/d91-c606-01/derive.py: one 4,000.00 point accretes 20.00 in January (balance 4,020.00),
# 246.71 / 4,246.71 at the end of 2026 and 508.64 to the 24th month end (cash selling price
# 4,508.64, adjustment 508.64); two 4,000.00 points give 40.00 / 8,040.00 / 1,017.28 / 9,017.28;
# 3,000.00 net of a credit memo gives 15.00 / 3,015.00 / 381.48 / 3,381.48. On main (cdd84a4)
# `_judged_points` summed every raw BILLING_RECORDED, so a status update doubled the point.

CONTRACT = "C-FIN-ADV"
JAN1, JAN5, JAN10, JAN20, FEB10 = (
    date(2026, 1, 1),
    date(2026, 1, 5),
    date(2026, 1, 10),
    date(2026, 1, 20),
    date(2026, 2, 10),
)
GAP = f"financing_gap_test:{CONTRACT}/L1-ASSET:-"
I_P01 = f"financing_interest_cum:{CONTRACT}@US01:FY2026-P01"
B_P01 = f"financed_balance:{CONTRACT}@US01:FY2026-P01"
I_P12 = f"financing_interest_cum:{CONTRACT}@US01:FY2026-P12"
B_P12 = f"financed_balance:{CONTRACT}@US01:FY2026-P12"
I_END = f"financing_interest_cum:{CONTRACT}@US01:FY2027-P12"
CSP = f"cash_selling_price:{CONTRACT}/L1-ASSET:-"
ONE_POINT = ["20.00", "4020.00", "508.64"]
Build = Callable[[EventInput, list[EventInput], int], list[EventInput]]


def _event(
    base: EventInput,
    seq: int,
    event_type: str,
    on: date,
    payload: dict[str, object],
    *,
    obligation_keys: Sequence[str] | None = None,
    supersedes: str | None = None,
) -> EventInput:
    """An injected event with the CV-22 key of its ``seq`` and a record time on its date."""
    return dataclasses.replace(
        base,
        event_key=f"{CONTRACT}/EV-{seq:06d}",
        record_seq=seq,
        stream_version=seq,
        event_type=event_type,
        effective_date=on,
        recorded_at=datetime(on.year, on.month, on.day, 17, tzinfo=UTC),
        obligation_keys=base.obligation_keys if obligation_keys is None else tuple(obligation_keys),
        payload=payload,
        payload_sha256=sha256_hex(payload),
        supersedes_event_key=supersedes,
    )


def _update(bill: EventInput, seq: int, on: date, **changes: object) -> EventInput:
    """The S10-R-07 status update: same identity and amount, ``is_cancellable`` false."""
    return _event(
        bill, seq, "BILLING_RECORDED", on, {**bill.payload, "is_cancellable": False, **changes}
    )


def _world(name: str, build: Build) -> tuple[BookOutput, dict[str, TraceNode], dict[str, str]]:
    """(book, nodes, re-evaluated values) of the SFC-S3-EX29 checkpoint ``name`` with its events
    rebuilt by ``build(bill, others, next_seq)``."""
    checkpoint = next(
        c
        for c in _build_checkpoint_bundles(load(ANSWER_KEY_ROOT / "sfc/SFC-S3-EX29.yaml"))
        if c.name == name
    )
    (bundle,) = checkpoint.bundles
    bundle = cast(InputBundle, bundle)
    bill = next(e for e in bundle.events if e.event_type == "BILLING_RECORDED")
    others = [e for e in bundle.events if e is not bill]
    events = _resequenced(build(bill, others, max(e.record_seq for e in bundle.events) + 1))
    known_at = max([bundle.known_at, *(e.recorded_at for e in events)])
    output = cast(
        OutputBundle,
        erev_engine.compute(dataclasses.replace(bundle, events=events, known_at=known_at)),
    )
    assert output.diagnostics == ()
    (book,) = [b for b in output.books if b.book_code == checkpoint.book]
    nodes = {node.id: node for node in book.trace.nodes}
    return book, nodes, dict(reevaluate(book.trace))


def _resequenced(events: Sequence[EventInput]) -> tuple[EventInput, ...]:
    """The events renumbered in ENG-06 order (effective date, then the order given) with CV-22 keys
    and strictly increasing record times, so an injected event dated before a later-dated base
    event is not a late event (S08-R-10 ``OUT_OF_ORDER``); void targets are remapped."""
    ordered = sorted(enumerate(events), key=lambda item: (item[1].effective_date, item[0]))
    renamed = {
        event.event_key: f"{CONTRACT}/EV-{seq:06d}" for seq, (_, event) in enumerate(ordered, 1)
    }
    out: list[EventInput] = []
    recorded = datetime(2000, 1, 1, tzinfo=UTC)
    for seq, (_, event) in enumerate(ordered, 1):
        on = event.effective_date
        recorded = max(
            datetime(on.year, on.month, on.day, 17, tzinfo=UTC), recorded + timedelta(seconds=1)
        )
        out.append(
            dataclasses.replace(
                event,
                event_key=renamed[event.event_key],
                record_seq=seq,
                stream_version=seq,
                recorded_at=recorded,
                supersedes_event_key=None
                if event.supersedes_event_key is None
                else renamed[event.supersedes_event_key],
            )
        )
    return tuple(out)


def _financing(nodes: dict[str, TraceNode], again: dict[str, str], *ids: str) -> list[str]:
    return _values(nodes, again, *ids)


def _gap(nodes: dict[str, TraceNode]) -> tuple[str, str, str, str]:
    params = nodes[GAP].params
    return (
        params["payment_source"],
        params.get("transfer_open", "false"),
        params["payment_points"],
        params["status_updates_ignored"],
    )


def _interest_expense(book: BookOutput) -> int:
    return sum(
        line.amount_txn
        for intent in book.posting_intents
        for line in intent.lines
        if line.account_role == "INTEREST_EXPENSE" and line.side == "D"
    )


def _after(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
    return [*others, bill, _update(bill, n, JAN20)]


def _naming_no_obligation(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
    payload = {
        k: v for k, v in {**bill.payload, "is_cancellable": False}.items() if k != "obligation_key"
    }
    return [*others, bill, _event(bill, n, "BILLING_RECORDED", JAN20, payload, obligation_keys=())]


def _dated_before(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
    # The 5 January event is first seen and is the line; the 10 January noncancellable event is its
    # status update; the single point is dated 5 January with the same 24 month ends.
    line = _event(bill, n + 1, "BILLING_RECORDED", JAN10, dict(bill.payload))
    return [*others, line, _update(bill, n, JAN5)]


def _cancellable_then_update(
    bill: EventInput, others: list[EventInput], n: int
) -> list[EventInput]:
    cancellable = dataclasses.replace(bill, payload={**bill.payload, "is_cancellable": True})
    return [*others, cancellable, _update(bill, n, JAN20)]


@pytest.mark.parametrize(
    ("label", "build", "point_date"),
    [
        ("after the invoice", _after, JAN1),
        ("naming no obligation", _naming_no_obligation, JAN1),
        ("dated before the line", _dated_before, JAN5),
        ("cancellable original then update", _cancellable_then_update, JAN1),
    ],
    ids=["after", "no_obligation", "dated_before", "cancellable_original"],
)
def test_c606_05_status_update_adds_no_payment_point(
    label: str, build: Build, point_date: date
) -> None:
    """S04-R-10a (D-91 C606-05): a same-identity, same-amount repeat whose ``is_cancellable`` is not
    true adds no point. One 4,000.00 point: `payments` "0:4000", 20.00 / 4,020.00 in January,
    508.64 at FY2027-P12; at transfer the cash selling price is 4,508.64 (adjustment 508.64), the
    transaction price and revenue 450,864 minor, Dr INTEREST_EXPENSE 50,864 minor over the horizon;
    `billed_cum` stays 400,000 minor. Main: "0:4000,0:4000", 40.00 / 8,040.00 / 1,017.28 /
    9,017.28."""
    book, nodes, again = _world("end-of-january-2026", build)
    assert _gap(nodes) == ("BILLING_RECORDED", "true", f"{point_date.isoformat()}:4000", "1")
    assert nodes[I_P01].params["payments"] == "0:4000", label
    assert _financing(nodes, again, I_P01, B_P01, I_END) == ONE_POINT, label
    assert book.contract_version is not None
    assert book.contract_version.columns["billed_cum"] == 400_000
    delivered, nodes, again = _world("transfer", build)
    assert _financing(nodes, again, CSP, I_END) == ["4508.64", "508.64"], label
    assert delivered.contract_version is not None
    assert (
        delivered.contract_version.columns["transaction_price"],
        delivered.contract_version.columns["revenue_cum"],
        delivered.contract_version.columns["financing_adjustment_amount"],
    ) == (450_864, 450_864, 50_864)
    assert _interest_expense(delivered) == 50_864
    # The CSP node's per-point SourceRef names the line event, not the contract key (D-91).
    refs = [
        ref
        for ref in nodes[CSP].inputs
        if isinstance(ref, SourceRef) and ref.ref_type == "contract_event"
    ]
    assert [ref.ref_id.startswith(f"{CONTRACT}/EV-") for ref in refs] == [True]
    assert refs[0].detail["date"] == point_date.isoformat()


@pytest.mark.parametrize("flag", ["absent", "false"], ids=["absent", "string_false"])
def test_c606_05_absent_or_string_false_flag_repeat_is_a_status_update(flag: str) -> None:
    """A repeat with ``is_cancellable`` absent (the 04 default) or the string ``"false"`` is a
    status update as the literal ``false`` is (04:2648; L2-4-Q-8): one point, the base world's
    figures."""

    def build(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
        payload = dict(bill.payload)
        if flag == "absent":
            payload.pop("is_cancellable", None)
        else:
            payload["is_cancellable"] = "false"
        return [*others, bill, _event(bill, n, "BILLING_RECORDED", JAN20, payload)]

    _, nodes, again = _world("end-of-january-2026", build)
    assert (nodes[I_P01].params["payments"], _gap(nodes)[3]) == ("0:4000", "1")
    assert _financing(nodes, again, I_P01, B_P01, I_END) == ONE_POINT


def test_c606_05_two_updates_add_nothing_and_voided_first_line_makes_the_update_the_line() -> None:
    """Two updates (20 Jan, 10 Feb) add no point: "0:4000" and both are ignored. With the 1 January
    line voided (EVENT_VOIDED, S01-R-12), the 20 January event is first seen and is the line: one
    point dated 20 January with the same 24 month ends through 31 December 2027, so 20.00 /
    4,020.00 / 4,508.64."""

    def two_updates(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
        return [*others, bill, _update(bill, n, JAN20), _update(bill, n + 1, FEB10)]

    _, nodes, again = _world("end-of-january-2026", two_updates)
    assert (nodes[I_P01].params["payments"], _gap(nodes)[2:]) == (
        "0:4000",
        ("2026-01-01:4000", "2"),
    )
    ignored = nodes[GAP].params["status_updates_ignored_keys"].split("|")
    assert len(ignored) == 2 and all(key.startswith(f"{CONTRACT}/EV-") for key in ignored)
    assert _financing(nodes, again, I_P01, B_P01, I_END) == ONE_POINT

    def voided(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
        void = _event(
            bill, n, "EVENT_VOIDED", JAN1, {}, obligation_keys=(), supersedes=bill.event_key
        )
        return [*others, bill, void, _update(bill, n + 1, JAN20)]

    _, nodes, again = _world("end-of-january-2026", voided)
    assert _gap(nodes) == ("BILLING_RECORDED", "true", "2026-01-20:4000", "0")
    assert nodes[I_P01].params["payments"] == "0:4000"
    assert _financing(nodes, again, I_P01, B_P01, I_END) == ONE_POINT
    _, nodes, again = _world("transfer", voided)
    assert _financing(nodes, again, CSP) == ["4508.64"]


def test_c606_05_changed_amount_update_is_rejected_by_stage_10() -> None:
    """A 4,500.00 update is stage 10's ``INVOICE_STATUS_UPDATE_MISMATCH`` (CV-15 stops the
    computation, no book is published); stage 04 neither re-validates nor raises."""
    with pytest.raises(EngineError) as raised:
        _world(
            "end-of-january-2026",
            lambda bill, others, n: [
                *others,
                bill,
                _update(bill, n, JAN20, amount=Decimal("4500.00")),
            ],
        )
    assert raised.value.code == "INVOICE_STATUS_UPDATE_MISMATCH"


@pytest.mark.parametrize(
    ("label", "changes"),
    [
        ("repeated cancellable True", {"is_cancellable": True}),
        ('repeated cancellable "true"', {"is_cancellable": "true"}),
        ("a different line id", {"line_external_id": "INV-ADV-1-2"}),
    ],
    ids=["cancellable_true", "cancellable_string_true", "different_line_id"],
)
def test_c606_05_another_line_is_another_payment_point(
    label: str, changes: dict[str, object]
) -> None:
    """Stage-10 parity (D-91 C606-01 (2), C606-05e): a repeat flagged cancellable, or another line
    id, is another line: `billed_cum` 800,000 minor, payments "0:4000,0:4000", 40.00 / 8,040.00 /
    1,017.28, cash selling price 9,017.28. Stage 04 never deduplicates a record only because it
    shares an identifier."""

    def build(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
        return [
            *others,
            bill,
            _event(bill, n, "BILLING_RECORDED", JAN20, {**bill.payload, **changes}),
        ]

    book, nodes, again = _world("end-of-january-2026", build)
    assert book.contract_version is not None
    assert book.contract_version.columns["billed_cum"] == 800_000, label
    assert (nodes[I_P01].params["payments"], _gap(nodes)[2:]) == (
        "0:4000,0:4000",
        ("2026-01-01:4000|2026-01-20:4000", "0"),
    )
    assert _financing(nodes, again, I_P01, B_P01, I_END) == ["40.00", "8040.00", "1017.28"], label
    _, nodes, again = _world("transfer", build)
    assert _financing(nodes, again, CSP) == ["9017.28"]


def test_c606_05_receipts_keep_priority_over_billing() -> None:
    """S04-R-10a (a): a cash receipt applied to INV-ADV-1 replaces the invoice-derived points; the
    line and its update never combine with it (D-87 L5-3-Q-8): `payment_source PAYMENT_RECEIVED`,
    "0:4000", 20.00 / 4,020.00."""

    def build(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
        receipt = _event(
            bill,
            n,
            "PAYMENT_RECEIVED",
            JAN1,
            {
                "receipt_reference": "RCPT-1",
                "amount": Decimal("4000.00"),
                "receipt_date": JAN1,
                "applied_invoice_numbers": ["INV-ADV-1"],
            },
            obligation_keys=(),
        )
        return [*others, receipt, bill, _update(bill, n + 1, JAN20)]

    _, nodes, again = _world("end-of-january-2026", build)
    assert _gap(nodes) == ("PAYMENT_RECEIVED", "true", "2026-01-01:4000", "1")
    assert nodes[I_P01].params["payments"] == "0:4000"
    assert _financing(nodes, again, I_P01, B_P01) == ["20.00", "4020.00"]


def test_c606_05_credit_memo_still_nets_and_update_adds_nothing() -> None:
    """A 1,000.00 credit memo on 1 January nets the point to 3,000.00 while the update adds nothing:
    `billed_cum` 300,000 minor, "0:3000", 15.00 / 3,015.00 / 381.48, cash selling price 3,381.48.
    The resulting transaction price (S04-R-12 mechanics on an unsupported input) is not asserted
    (D-91)."""

    def build(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
        memo = _event(
            bill,
            n,
            "CREDIT_MEMO_RECORDED",
            JAN1,
            {
                "credit_memo_number": "CM-1",
                "credited_invoice_number": "INV-ADV-1",
                "obligation_key": "L1-ASSET",
                "amount": Decimal("1000.00"),
                "issue_date": JAN1,
            },
        )
        return [*others, bill, memo, _update(bill, n + 1, JAN20)]

    book, nodes, again = _world("end-of-january-2026", build)
    assert book.contract_version is not None
    assert book.contract_version.columns["billed_cum"] == 300_000
    assert (nodes[I_P01].params["payments"], _gap(nodes)[2:]) == (
        "0:3000",
        ("2026-01-01:3000", "1"),
    )
    assert _financing(nodes, again, I_P01, B_P01, I_END) == ["15.00", "3015.00", "381.48"]
    _, nodes, again = _world("transfer", build)
    assert _financing(nodes, again, CSP) == ["3381.48"]


def test_c606_05_end_of_2026_check_figure_with_status_update() -> None:
    """The S04-R-10a check figures at the end of 2026 hold with a matching status update in the
    stream: 246.71 of cumulative interest and a 4,246.71 balance (main 493.42 / 8,493.42)."""
    _, nodes, again = _world("end-of-2026", _after)
    assert _financing(nodes, again, I_P12, B_P12) == ["246.71", "4246.71"]


# --- D-91 C606-05g: ENGINE-mode payment-point eligibility and date basis (lane ENG-C6) -----------
#
# Ruling (docs/01-DECISIONS.md D-91 05g; ENGINE_SPEC S04-R-10a [J]): in ENGINE mode (POL-004
# ENGINE, POL-123 UNCONDITIONAL_INVOICES_ONLY) a billing payment point is dated its S10-R-06
# unconditional date: a noncancellable line its effective date; a cancellable line the effective
# date of its first same-amount noncancellable status update, or the applied receipt, which then
# already governs under (a); a line with no unconditional date at the position is memo-only and
# contributes no point; zero eligible points under a significant = true judgement raise
# SFC_REVIEW_REQUIRED (ERROR) and post nothing, replacing the silent no-schedule path. ERP mode is
# unchanged. Figures derived in .run/eng-c6/derive.py: the 20 February update dates the point 20
# February, 23 month ends to 31 December 2027, P02 interest 20.00, balance 4,020.00, end-of-2026
# balance 4,225.58, cash selling price 4,000 × 1.005^23 = 4,486.21, adjustment 486.21, revenue
# 4,486.21 (main: 1 January, P01 20.00, 4,508.64).

BASIS = {"ERP": "ERP_POSTED_INVOICES", "ENGINE": "UNCONDITIONAL_INVOICES_ONLY"}
FEB20 = date(2026, 2, 20)
CSP_05G = ["4486.21", "486.21"]
BILLED_P01 = f"billed_cum:{CONTRACT}/L1-ASSET:FY2026-P01"
BILLED_P02 = f"billed_cum:{CONTRACT}/L1-ASSET:FY2026-P02"
I_P02 = f"financing_interest_cum:{CONTRACT}@US01:FY2026-P02"
B_P02 = f"financed_balance:{CONTRACT}@US01:FY2026-P02"


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


def _engine_world(
    name: str, build: Build
) -> tuple[BookOutput, dict[str, TraceNode], dict[str, str]]:
    """``_world`` under POL-004 ENGINE (the SFC-S3-EX29 world, every event re-sequenced)."""
    checkpoint = next(
        c
        for c in _build_checkpoint_bundles(load(ANSWER_KEY_ROOT / "sfc/SFC-S3-EX29.yaml"))
        if c.name == name
    )
    (bundle,) = checkpoint.bundles
    bundle = _in_mode(cast(InputBundle, bundle), "ENGINE")
    bill = next(e for e in bundle.events if e.event_type == "BILLING_RECORDED")
    others = [e for e in bundle.events if e is not bill]
    events = _resequenced(build(bill, others, max(e.record_seq for e in bundle.events) + 1))
    known_at = max([bundle.known_at, *(e.recorded_at for e in events)])
    output = cast(
        OutputBundle,
        erev_engine.compute(dataclasses.replace(bundle, events=events, known_at=known_at)),
    )
    assert output.diagnostics == ()
    (book,) = [b for b in output.books if b.book_code == checkpoint.book]
    nodes = {node.id: node for node in book.trace.nodes}
    return book, nodes, dict(reevaluate(book.trace))


def _cancellable(bill: EventInput) -> EventInput:
    return dataclasses.replace(bill, payload={**bill.payload, "is_cancellable": True})


def _jan_line_feb_update(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
    """The 05g world: a cancellable 4,000.00 line, 1 January, made noncancellable on 20 February."""
    return [*others, _cancellable(bill), _update(bill, n, FEB20)]


def _memo_only(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
    """A cancellable line never made noncancellable and never paid."""
    return [*others, _cancellable(bill)]


def _period_lines(book: BookOutput, period: str, role: str) -> list[tuple[str, int]]:
    """(side, minor units) of ``role`` in the intents posted to ``period``
    (``PostingIntent.posting_period_key``)."""
    return sorted(
        (line.side, line.amount_txn)
        for intent in book.posting_intents
        if intent.posting_period_key == period
        for line in intent.lines
        if line.account_role == role
    )


def test_c606_05g_engine_cancellable_line_is_a_point_when_made_noncancellable() -> None:
    """At ``end-of-2026`` (the stream holds the 20 February update): the point is dated 20 February
    (`payment_points` "2026-02-20:4000", the update counted as the eligibility source, not as a
    second point); no January interest node exists (the grid starts at the first point) and the
    period-dated ``billed_cum`` node is 0.00 in January and 4,000.00 in February; February
    interest 20.00, balance 4,020.00; JET-03 and JET-11b post in February, nothing in January;
    the end-of-2026 balance is 4,225.58. At ``transfer``: cash selling price 4,486.21, adjustment
    486.21, transaction price and revenue 448,621 minor, Dr INTEREST_EXPENSE 48,621 minor over the
    horizon. Main dated the point 1 January: 20.00 in January, 4,508.64."""
    book, nodes, again = _engine_world("end-of-2026", _jan_line_feb_update)
    assert _gap(nodes) == ("BILLING_RECORDED", "true", "2026-02-20:4000", "1")
    assert I_P01 not in nodes and B_P01 not in nodes
    assert _values(nodes, again, BILLED_P01, BILLED_P02) == ["0.00", "4000.00"]
    assert _financing(nodes, again, I_P02, B_P02, I_P12, B_P12) == [
        "20.00",
        "4020.00",
        "225.58",
        "4225.58",
    ]
    assert _period_lines(book, "FY2026-P01", "INTEREST_EXPENSE") == []
    assert _period_lines(book, "FY2026-P01", "CONTRACT_LIABILITY") == []
    assert _period_lines(book, "FY2026-P02", "INTEREST_EXPENSE") == [("D", 2_000)]
    assert _period_lines(book, "FY2026-P02", "ACCOUNTS_RECEIVABLE") == [("D", 400_000)]
    assert _period_lines(book, "FY2026-P02", "CONTRACT_LIABILITY") == [("C", 2_000), ("C", 400_000)]
    delivered, nodes, again = _engine_world("transfer", _jan_line_feb_update)
    assert _financing(nodes, again, CSP, I_END) == CSP_05G
    assert delivered.contract_version is not None
    assert (
        delivered.contract_version.columns["transaction_price"],
        delivered.contract_version.columns["revenue_cum"],
        delivered.contract_version.columns["financing_adjustment_amount"],
    ) == (448_621, 448_621, 48_621)
    assert _interest_expense(delivered) == 48_621
    refs = [
        ref
        for ref in nodes[CSP].inputs
        if isinstance(ref, SourceRef) and ref.ref_type == "contract_event"
    ]
    assert [ref.detail["date"] for ref in refs] == ["2026-02-20"]


@pytest.mark.parametrize("name", ["end-of-january-2026", "end-of-2026", "transfer"])
def test_c606_05g_memo_only_line_raises_sfc_review_required(name: str) -> None:
    """A cancellable line never made noncancellable and never paid has no unconditional date, so
    under the significant = true judgement no eligible point exists: ``SFC_REVIEW_REQUIRED``
    (ERROR, CV-15) at every checkpoint and nothing is posted. Main accreted 508.64 on 0.00 of
    billing (cash selling price 4,508.64)."""
    with pytest.raises(EngineError) as raised:
        _engine_world(name, _memo_only)
    assert raised.value.code == "SFC_REVIEW_REQUIRED"
    assert "JUDGEMENT_SIGNIFICANT" in str(raised.value.detail)
    assert "memo_only" in str(raised.value.detail)


def test_c606_05g_historical_cutoff_and_replay() -> None:
    """The January bundle of the 05g world holds the cancellable line and no update: memo-only,
    ``SFC_REVIEW_REQUIRED`` (the historical position fails closed rather than accreting on a
    liability that does not exist). The same bundle with the 20 February update in its stream
    dates the point 20 February; every node re-evaluates (``_values``)."""
    with pytest.raises(EngineError) as raised:
        _engine_world("end-of-january-2026", _memo_only)
    assert raised.value.code == "SFC_REVIEW_REQUIRED"
    _, nodes, again = _engine_world("end-of-january-2026", _jan_line_feb_update)
    assert _gap(nodes) == ("BILLING_RECORDED", "true", "2026-02-20:4000", "1")
    assert I_P01 not in nodes
    assert _financing(nodes, again, I_P02, B_P02) == ["20.00", "4020.00"]


def test_c606_05g_erp_mode_is_unchanged() -> None:
    """The same cancellable-then-update world under ERP (the key's mode): the point stays at the 1
    January effective date, 20.00 / 4,020.00 / 508.64, as `cancellable_original` pins above."""
    _, nodes, again = _world("end-of-january-2026", _jan_line_feb_update)
    assert _gap(nodes) == ("BILLING_RECORDED", "true", "2026-01-01:4000", "1")
    assert _financing(nodes, again, I_P01, B_P01, I_END) == ONE_POINT


def _receipt(bill: EventInput, seq: int, on: date, amount: str, applied: list[str]) -> EventInput:
    return _event(
        bill,
        seq,
        "PAYMENT_RECEIVED",
        on,
        {
            "receipt_reference": f"RCPT-{seq}",
            "amount": Decimal(amount),
            "receipt_date": on,
            "applied_invoice_numbers": applied,
        },
        obligation_keys=(),
    )


@pytest.mark.parametrize(
    ("applied", "billed"),
    [pytest.param(["INV-ADV-1"], 400_000, id="applied"), pytest.param([], 0, id="unapplied")],
)
def test_c606_05g_partial_receipt_keeps_the_receipts_first_fallback(
    applied: list[str], billed: int
) -> None:
    """A18 (returned with these figures): a 1,000.00 cash receipt on 1 January against the
    cancellable 4,000.00 line. D-87's whole-contract receipts-first fallback stands (D-91): the
    points are the receipts alone, 1,000.00 at 1 January (P01 interest 5.00, balance 1,005.00,
    cash selling price 1,127.16 at transfer); the unpaid 3,000.00 remainder is neither counted
    twice nor a point. Stage 10 dates the cancellable line by the APPLIED receipt (billed_cum
    4,000.00) and leaves it memo-only when the receipt is unapplied (0.00)."""

    def build(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
        return [*others, _cancellable(bill), _receipt(bill, n, JAN1, "1000.00", applied)]

    book, nodes, again = _engine_world("end-of-january-2026", build)
    assert _gap(nodes) == ("PAYMENT_RECEIVED", "true", "2026-01-01:1000", "0")
    assert _financing(nodes, again, I_P01, B_P01) == ["5.00", "1005.00"]
    assert book.contract_version is not None
    assert book.contract_version.columns["billed_cum"] == billed
    _, nodes, again = _engine_world("transfer", build)
    assert _financing(nodes, again, CSP) == ["1127.16"]


def test_c606_05g_explicit_schedule_keeps_priority_over_receipt_and_update() -> None:
    """SFC-CHK-137-S3-EX28-CASEB (60 scheduled instalments) under ENGINE with a cash receipt dated
    15 February applied to INST-01 and a same-amount noncancellable status update of INST-01 on 10
    February: the payment schedule in force governs (S04-R-10, no S04-R-10a derivation, no
    `payment_source`), no second point arises from the update or the receipt, and the January
    interest and cash selling price equal the keyed ERP compute."""
    path = ANSWER_KEY_ROOT / "sfc/SFC-CHK-137-S3-EX28-CASEB.yaml"
    checkpoint = next(
        c for c in _build_checkpoint_bundles(load(path)) if c.name == "end-of-month-2"
    )
    (base,) = checkpoint.bundles
    base = cast(InputBundle, base)
    erp = cast(OutputBundle, erev_engine.compute(base)).books[0]
    bill = next(e for e in base.events if e.event_type == "BILLING_RECORDED")
    contract = bill.contract_key
    n = max(e.record_seq for e in base.events) + 1

    def keyed(seq: int) -> str:
        return f"{contract}/EV-{seq:06d}"

    update = dataclasses.replace(
        bill,
        event_key=keyed(n),
        record_seq=n,
        stream_version=n,
        effective_date=date(2026, 2, 10),
        recorded_at=datetime(2026, 2, 10, 17, tzinfo=UTC),
        payload={**bill.payload, "is_cancellable": False},
        payload_sha256=sha256_hex({**bill.payload, "is_cancellable": False}),
    )
    receipt_payload = {
        "receipt_reference": "RCPT-137",
        "amount": Decimal("18871.00"),
        "receipt_date": date(2026, 2, 15),
        "applied_invoice_numbers": ["INST-01"],
    }
    receipt = dataclasses.replace(
        bill,
        event_key=keyed(n + 1),
        record_seq=n + 1,
        stream_version=n + 1,
        event_type="PAYMENT_RECEIVED",
        effective_date=date(2026, 2, 15),
        recorded_at=datetime(2026, 2, 15, 17, tzinfo=UTC),
        obligation_keys=(),
        payload=receipt_payload,
        payload_sha256=sha256_hex(receipt_payload),
    )
    bundle = _in_mode(with_events(base, update, receipt), "ENGINE")  # ENG-06 re-sequenced
    output = cast(OutputBundle, erev_engine.compute(bundle))
    assert output.diagnostics == ()
    (book,) = output.books
    nodes = {node.id: node for node in book.trace.nodes}
    erp_nodes = {node.id: node for node in erp.trace.nodes}
    gap = next(node for node_id, node in nodes.items() if node_id.startswith("financing_gap_test:"))
    assert "payment_source" not in gap.params and gap.params["reason"] == "SIGNIFICANT_GAP"
    for measure in (
        "cash_selling_price:",
        "financing_interest_cum:",
        "financing_adjustment_amount:",
    ):
        ids = [node_id for node_id in nodes if node_id.startswith(measure)]
        assert ids and all(nodes[i].value == erp_nodes[i].value for i in ids), measure


# --- D-97 (15): a credit memo against a still-memo-only ENGINE line fails closed (lane ENG-C6) ---
#
# Ruling (D-97 (15); ENGINE_SPEC S04-R-10a [J] rev 1.9; 04 table 15.4-B rev 1.16): a credit memo
# follows its document — against a memo-only line it is memo-only with the line and enters the
# schedule, netted, only when and where the line becomes unconditional; it is never a negative
# point at its own date while the line contributes nothing. Until that netting is built the engine
# raises CREDIT_MEMO_ON_MEMO_ONLY_LINE (ERROR, CV-15). ERP figures and a noncancellable ENGINE line
# keep the existing netting (15.00 / 3,015.00 / 381.48 / 3,381.48; derive.py §E2).

JAN15, MAR1 = date(2026, 1, 15), date(2026, 3, 1)


def _credit_memo(bill: EventInput, seq: int, on: date, amount: str = "1000.00") -> EventInput:
    return _event(
        bill,
        seq,
        "CREDIT_MEMO_RECORDED",
        on,
        {
            "credit_memo_number": "CM-1",
            "credited_invoice_number": "INV-ADV-1",
            "obligation_key": "L1-ASSET",
            "amount": Decimal(amount),
            "issue_date": on,
        },
    )


def _memo_against_memo_only(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
    """A cancellable line never made noncancellable, credited 1,000.00 on 15 January."""
    return [*others, _cancellable(bill), _credit_memo(bill, n, JAN15)]


@pytest.mark.parametrize("name", ["end-of-january-2026", "end-of-2026", "transfer"])
def test_d97_15_credit_memo_on_memo_only_line_fails_closed(name: str) -> None:
    """The memo names an invoice whose only kept line is still memo-only at every checkpoint:
    ``CREDIT_MEMO_ON_MEMO_ONLY_LINE`` (ERROR, CV-15; the first blocking finding in CV-43 order)
    with the memo, the invoice and the memo-only line in its detail; the position also has no
    eligible point, so ``SFC_REVIEW_REQUIRED`` is collected beside it; nothing posts. Before D-97
    (15) the memo entered as a −1,000.00 point on 15 January."""
    with pytest.raises(EngineError) as raised:
        _engine_world(name, _memo_against_memo_only)
    assert raised.value.code == "CREDIT_MEMO_ON_MEMO_ONLY_LINE"
    findings = str(raised.value.detail["findings"])
    assert "CM-1" in findings and "INV-ADV-1" in findings and "S04-R-10a" in findings
    assert f"{CONTRACT}/EV-" in findings and "SFC_REVIEW_REQUIRED" in findings


def test_d97_15_credit_memo_nets_once_the_line_is_unconditional() -> None:
    """The line made noncancellable on 20 February and credited on 1 March: no finding; the memo
    nets at its own date beside the 20 February point (two points, the update ignored as before)."""

    def build(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
        return [
            *others,
            _cancellable(bill),
            _update(bill, n, FEB20),
            _credit_memo(bill, n + 1, MAR1),
        ]

    _, nodes, _ = _engine_world("end-of-2026", build)
    source, _, points, ignored = _gap(nodes)
    assert (source, ignored) == ("BILLING_RECORDED", "1")
    assert "2026-02-20:4000" in points and "2026-03-01:-1000" in points


def test_d97_15_engine_noncancellable_line_with_credit_memo_keeps_the_erp_figures() -> None:
    """A noncancellable ENGINE line is unconditional at its date, so the 1 January memo nets the
    point to 3,000.00 exactly as in ERP mode: 15.00 / 3,015.00 / 381.48 and 3,381.48."""

    def build(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
        return [*others, bill, _credit_memo(bill, n, JAN1)]

    _, nodes, again = _engine_world("end-of-january-2026", build)
    assert _gap(nodes)[2] == "2026-01-01:3000"
    assert _financing(nodes, again, I_P01, B_P01, I_END) == ["15.00", "3015.00", "381.48"]
    _, nodes, again = _engine_world("transfer", build)
    assert _financing(nodes, again, CSP) == ["3381.48"]


# --- D-97 (5) v2: the four SFC_REVIEW_REQUIRED boundaries (lane ENG-C6) ---------------------------
#
# (i) no billing line at the position -> the S04-R-10 no-schedule outcome, no finding; (ii) lines
# exist and every kept line is memo-only -> the finding (test_c606_05g_memo_only_line_raises_
# sfc_review_required); (iii) unconditional lines netting to zero beside memo-only lines -> NOT the
# finding (the predicate reads the kept lines, not the netted points; trace param eligible_lines);
# (iv) a receipts-first position never raises it. Codex: a source-derived boundary, not an executed
# monetary defect; (iii) is the only boundary whose behaviour changes (fail-first on 60281e3).


def _second_invoice(bill: EventInput, seq: int, on: date, amount: str) -> EventInput:
    """A noncancellable second invoice INV-2 / INV-2-1 of the same obligation."""
    return _event(
        bill,
        seq,
        "BILLING_RECORDED",
        on,
        {
            **bill.payload,
            "invoice_number": "INV-2",
            "line_external_id": "INV-2-1",
            "amount": Decimal(amount),
            "is_cancellable": False,
        },
    )


def _credit_against(bill: EventInput, seq: int, on: date, number: str, amount: str) -> EventInput:
    memo = _credit_memo(bill, seq, on, amount)
    return dataclasses.replace(
        memo,
        payload={
            **memo.payload,
            "credit_memo_number": f"CM-{number}",
            "credited_invoice_number": number,
        },
        payload_sha256=sha256_hex(
            {
                **memo.payload,
                "credit_memo_number": f"CM-{number}",
                "credited_invoice_number": number,
            }
        ),
    )


def test_d97_5_boundary_i_no_billing_line_raises_no_finding() -> None:
    """(i) The SFC-S3-EX29 world with its invoice removed: the position holds no billing line, so
    the significant judgement finds no schedule and no point — the S04-R-10 outcome, no
    ``SFC_REVIEW_REQUIRED``, no interest node."""
    _, nodes, _ = _engine_world("end-of-january-2026", lambda bill, others, n: list(others))
    source, _, points, _ = _gap(nodes)
    assert (source, points) == ("BILLING_RECORDED", "")
    assert nodes[GAP].params["memo_only_lines"] == "0"
    assert I_P01 not in nodes  # a control: the same outcome before and after D-97 (5) v2


def test_d97_5_boundary_iii_netted_zero_beside_memo_only_is_not_the_finding() -> None:
    """(iii) The cancellable 4,000.00 line stays memo-only while a noncancellable 500.00 invoice
    INV-2 of 1 January is credited in full the same day: INV-2's line is eligible and its date nets
    to zero, so ``points`` is empty but the population is not memo-only — no finding, no interest,
    ``eligible_lines`` 1 and ``memo_only_lines`` 1. On 60281e3 the netted-points predicate raised
    ``SFC_REVIEW_REQUIRED`` here."""

    def build(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
        return [
            *others,
            _cancellable(bill),
            _second_invoice(bill, n, JAN1, "500.00"),
            _credit_against(bill, n + 1, JAN1, "INV-2", "500.00"),
        ]

    _, nodes, _ = _engine_world("end-of-january-2026", build)
    source, _, points, _ = _gap(nodes)
    assert (source, points) == ("BILLING_RECORDED", "")
    assert nodes[GAP].params["eligible_lines"] == "1"
    assert nodes[GAP].params["memo_only_lines"] == "1"
    assert I_P01 not in nodes


def test_d97_5_boundary_iv_receipts_first_never_raises_the_finding() -> None:
    """(iv) The cancellable line stays memo-only but a 1,000.00 unapplied receipt on 1 January
    exists: branch (a) governs (``payment_source`` PAYMENT_RECEIVED), ``memo_only`` is empty by
    construction and the position computes (P01 interest 5.00, balance 1,005.00)."""

    def build(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
        return [*others, _cancellable(bill), _receipt(bill, n, JAN1, "1000.00", [])]

    _, nodes, again = _engine_world("end-of-january-2026", build)
    assert _gap(nodes)[:3] == ("PAYMENT_RECEIVED", "true", "2026-01-01:1000")
    assert nodes[GAP].params["memo_only_lines"] == "0"
    assert _financing(nodes, again, I_P01, B_P01) == ["5.00", "1005.00"]


def test_d97_15_credit_memo_recorded_before_the_line_became_unconditional_fails_closed() -> None:
    """The memo-only → unconditional transition (D-97 (15) v3 scope): the memo of 15 January
    precedes the 20 February update that makes the line unconditional. At ``end-of-2026`` the line
    is eligible, yet netting the memo at its own date would put a −1,000.00 point before the line
    contributes anything, so the engine fails closed (``CREDIT_MEMO_ON_MEMO_ONLY_LINE``) until the
    netting at the line's unconditional date is built; ``SFC_REVIEW_REQUIRED`` is NOT raised
    (an eligible line exists). Before this rule the memo entered at 15 January."""

    def build(bill: EventInput, others: list[EventInput], n: int) -> list[EventInput]:
        return [
            *others,
            _cancellable(bill),
            _credit_memo(bill, n, JAN15),
            _update(bill, n + 1, FEB20),
        ]

    with pytest.raises(EngineError) as raised:
        _engine_world("end-of-2026", build)
    assert raised.value.code == "CREDIT_MEMO_ON_MEMO_ONLY_LINE"
    findings = str(raised.value.detail["findings"])
    assert "CM-1" in findings and "SFC_REVIEW_REQUIRED" not in findings
