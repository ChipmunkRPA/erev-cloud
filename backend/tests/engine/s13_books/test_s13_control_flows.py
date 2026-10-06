"""Stage 13 billing control flows follow each line's S10-R-06 eligibility (S12-R-04; S12-INV-03).

Codex's observation on 0104e86 (``PRODUCTION-BILLING-LAYER-REVIEW-20260919.md``):
``_control_flows`` summed every in-position line of a document and dated the total by the earliest
eligible line, so a cancellable memo-only line (no unconditional date) entered the
contract-liability layers on the eligible line's date while stage 10's position excluded it, and
the S12-INV-03 guard failed closed (layers 1,000.00 against NP 0); two ERP lines of one invoice with
payload due dates shared one POL-160 date and rate (IFRS15 March contract liability USD 9,900
instead of 9,930 / 10,020, ``PRODUCTION-BILLING-LAYER-INDEPENDENT-ACCEPTANCE-20260919.md``). The
producer now emits one BILLING flow per eligible in-position line with the line's own S10-R-06
unconditional date, POL-160 "unconditional due", first receipt and event key as source lineage;
a memo-only line contributes no flow until a status update or an applied receipt gives it a date.
The flow's effective date, which the POL-160 ``INVOICE_ISSUE_DATE`` election reads, is the
invoice issue date for an ERP-mode line and the S10-R-06 date the line becomes billing for an
ENGINE-mode line (supervisor ruling on policy edge B, adopting the lane's proposal: a cancellable
ENGINE line is issued as billing when a receipt is applied or a noncancellable update arrives, so
the election ties to NP under S12-INV-03). Stage 10 ``_counted`` and the S12-INV-03 guard are
unchanged. Worlds: the frozen
JE-CHK-023 (ENGINE, USD, January), JE-CHK-024 case A (ENGINE, cancellable, receipt 1 March),
FX-CHK-083 (ENGINE, EUR invoice, USD functional) and FX-POL-160 (ERP, EUR, both books). No
database.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from erev_engine.bundle import BookOutput, FxRateInput, InputBundle
from erev_engine.stages import s13_books
from erev_engine.stages.s10_billing_balances import BalanceState
from erev_engine.stages.s12_fx_entities.layers import ControlFlow
from erev_engine.stages.state import AllocatedState, BookContext, Target
from support.billing_lines import (
    billing_after,
    checkpoint_bundle,
    compute_book,
    first_billing,
    journal,
    period_balance,
    replace_payload,
    with_events,
    with_policy,
)

TAX = ("je", "JE-CHK-023-S3-SALESTAX-OWN-ENGINE-BILLING", "january-close")
A38 = ("je", "JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE")
FX_083 = ("fx", "FX-CHK-083-ENGINE-RECEIVABLE-REMEASUREMENT", "january-close")
FX_160 = ("fx", "FX-POL-160-IFRIC22-LAYER-DATE-ASC606-VS-IFRS15", "ifrs15-march-close")
JAN_1, JAN_10, JAN_15, JAN_20, JAN_31 = (
    date(2026, 1, 1),
    date(2026, 1, 10),
    date(2026, 1, 15),
    date(2026, 1, 20),
    date(2026, 1, 31),
)
FEB_20, MAR_1 = date(2026, 2, 20), date(2026, 3, 1)
P01, P02, P03 = "FY2026-P01", "FY2026-P02", "FY2026-P03"
AR, CL, TAX_PAYABLE = "ACCOUNTS_RECEIVABLE", "CONTRACT_LIABILITY", "SALES_TAX_PAYABLE"
JET_03 = "BILLING"  # the E-29 entry kind of the JET-03 invoice posting

# (amount, effective date, unconditional due, first receipt, source key) of a BILLING flow.
Flow = tuple[int, date, date | None, date | None, str]


def _billing_flows(
    monkeypatch: pytest.MonkeyPatch, bundle: InputBundle, book_code: str = "ASC606"
) -> tuple[BookOutput, list[Flow], list[BalanceState]]:
    """Compute one book; capture its BILLING control flows as the book loop emitted them."""
    captured: list[tuple[str, BalanceState, tuple[ControlFlow, ...]]] = []
    original = s13_books._control_flows

    def capture(
        ctx: BookContext, allocated: AllocatedState, st: BalanceState, relief: Sequence[Target]
    ) -> tuple[ControlFlow, ...]:
        flows = original(ctx, allocated, st, relief)
        captured.append((str(ctx.book_code), st, flows))
        return flows

    monkeypatch.setattr(s13_books, "_control_flows", capture)
    book = compute_book(bundle, book_code)
    flows = sorted(
        (
            flow.amount,
            flow.effective_date,
            flow.unconditional_date,
            flow.first_receipt_date,
            flow.source_key,
        )
        for code, _, found in captured
        if code == book_code
        for flow in found
        if flow.kind == "BILLING"
    )
    states = [st for code, st, _ in captured if code == book_code]
    return book, flows, states


def _positions(st: BalanceState) -> dict[str, int]:
    return {target.period_key: target.value for target in st.positions}


def _liability_layers(book: BookOutput, amount: int) -> set[tuple[str, int]]:
    """(source event key, functional amount) of the ``LIABILITY_LAYER_CREATED`` movements of
    ``amount`` transaction minor units (T-CON-18 columns): one row per source line."""
    return {
        (str(m.columns["source_key"]), int(str(m.columns["amount_functional"])))
        for m in book.fx_layer_movements
        if m.columns.get("movement_kind") == "LIABILITY_LAYER_CREATED"
        and m.columns.get("balance_role") == "CONTRACT_LIABILITY"
        and int(str(m.columns["amount_txn"])) == amount
    }


# --- Mixed eligible and memo-only lines on one document (the Codex tax case) --------------------


@pytest.mark.parametrize(
    "line_id",
    [
        pytest.param(None, id="same_identity_cancellable_repeat"),
        pytest.param("INV-TAX-0001-2", id="distinct_line_memo"),
    ],
)
def test_memo_only_line_on_an_eligible_document_creates_no_layer(
    monkeypatch: pytest.MonkeyPatch, line_id: str | None
) -> None:
    """JE-CHK-023 plus a cancellable 1,000.00 / 80.00 line on the same invoice and date (a
    repeated identity flagged ``true``, D-91 C606-01 (2), or a distinct line id): the memo line is
    outside ``billed_cum`` (S10-R-06), so the one BILLING flow is the eligible line's 100,000 minor
    with its own lineage; layers tie to NP 0 (S12-INV-03 holds, no abort); JET-03 posts the
    eligible line only; the 05h tax memo counts both lines (160.00)."""
    base = checkpoint_bundle(*TAX)
    bill = first_billing(base)
    changes = {} if line_id is None else {"line_external_id": line_id}
    bundle = with_events(base, billing_after(base, bill, JAN_15, cancellable=True, **changes))
    book, flows, states = _billing_flows(monkeypatch, bundle)
    assert flows == [(100_000, JAN_15, JAN_15, None, bill.event_key)]
    assert _positions(states[-1]) == {P01: 0}
    assert book.contract_version is not None
    columns = book.contract_version.columns
    assert (columns["billed_cum"], columns["sales_tax_excluded_amount"]) == (100_000, 16_000)
    assert journal(book, JET_03, P01) == [
        (AR, "D", 108_000),
        (CL, "C", 100_000),
        (TAX_PAYABLE, "C", 8_000),
    ]
    assert period_balance(book, P01, "contract_liability_txn") == 0
    assert period_balance(book, P01, "accounts_receivable_txn") == 108_000


# --- Lines of one document with different unconditional dates ------------------------------------


def _two_lines(name: str) -> tuple[InputBundle, str, str]:
    """JE-CHK-024 case A with the cancellable line at 600.00 and a noncancellable 400.00 second
    line (INV-38A-1-2) on the same invoice and date; the 1,000.00 receipt of 1 March applies to
    the invoice. Returns the bundle and the two line event keys."""
    base = checkpoint_bundle(*A38, name)
    bill = first_billing(base)
    base = replace_payload(base, bill.event_key, amount=Decimal("600.00"))
    second = billing_after(
        base,
        first_billing(base),
        JAN_31,
        cancellable=False,
        line_external_id="INV-38A-1-2",
        amount=Decimal("400.00"),
    )
    return with_events(base, second), bill.event_key, second.event_key


def test_lines_with_different_unconditional_dates_are_separate_flows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """At ``march-close``: the noncancellable 400.00 line is billing from 31 January (its own
    flow and lineage, dated its issue date); the cancellable 600.00 line becomes billing when the
    receipt is applied on 1 March (a second flow dated 1 March, unconditional 1 March, first
    receipt 1 March, its own lineage). NP 400 / 400 / 0; JET-03 posts 400.00 in January and
    600.00 in March; CL 400.00 / 400.00 / 0.00."""
    bundle, first, second = _two_lines("march-close")
    book, flows, states = _billing_flows(monkeypatch, bundle)
    assert flows == [
        (40_000, JAN_31, JAN_31, MAR_1, second),
        (60_000, MAR_1, MAR_1, MAR_1, first),
    ]
    assert _positions(states[-1]) == {P01: 40_000, P02: 40_000, P03: 0}
    assert journal(book, JET_03, P01) == [(AR, "D", 40_000), (CL, "C", 40_000)]
    assert journal(book, JET_03, P02) == []
    assert journal(book, JET_03, P03) == [(AR, "D", 60_000), (CL, "C", 60_000)]
    assert [period_balance(book, p, "contract_liability_txn") for p in (P01, P02, P03)] == [
        40_000,
        40_000,
        0,
    ]
    assert book.contract_version is not None
    columns = book.contract_version.columns
    assert (columns["billed_cum"], columns["revenue_cum"]) == (100_000, 100_000)


def test_historical_cutoff_holds_only_the_eligible_line(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same two-line document replayed at ``january-close`` (the receipt is not yet in the
    stream): one flow, the 400.00 line; billed_cum 400.00; CL 400.00; the memo line waits."""
    bundle, _first, second = _two_lines("january-close")
    book, flows, states = _billing_flows(monkeypatch, bundle)
    assert flows == [(40_000, JAN_31, JAN_31, None, second)]
    assert _positions(states[-1]) == {P01: 40_000, P02: 40_000, P03: 40_000}
    assert book.contract_version is not None
    assert book.contract_version.columns["billed_cum"] == 40_000
    assert period_balance(book, P01, "contract_liability_txn") == 40_000


# --- A later status update or receipt moves the line in on its date ------------------------------


def test_later_receipt_dates_the_cancellable_line_at_the_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JE-CHK-024 case A as keyed at ``receipt-1-march``: the flow is dated 1 March, the S10-R-06
    date the receipt made the line billing (its unconditional date and first receipt too); the
    layer is dated 1 March under either POL-160 option; NP 0 / 0 / 1,000."""
    bundle = checkpoint_bundle(*A38, "receipt-1-march")
    bill = first_billing(bundle)
    book, flows, states = _billing_flows(monkeypatch, bundle)
    assert flows == [(100_000, MAR_1, MAR_1, MAR_1, bill.event_key)]
    assert _positions(states[-1]) == {P01: 0, P02: 0, P03: 100_000}
    assert [period_balance(book, p, "contract_liability_txn") for p in (P01, P02, P03)] == [
        0,
        0,
        100_000,
    ]


def test_later_status_update_dates_the_cancellable_line_at_the_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JE-CHK-024 case A without the receipt and with a same-amount noncancellable status update
    on 20 February (S10-R-07): the line is billing from 20 February (S10-R-06); one flow dated 20
    February with the line's own lineage, unconditional 20 February; JET-03 posts in February; CL
    0.00 / 1,000.00 / 1,000.00."""
    base = checkpoint_bundle(*A38, "receipt-1-march")
    bill = first_billing(base)
    base = dataclasses.replace(
        base, events=tuple(e for e in base.events if e.event_type != "PAYMENT_RECEIVED")
    )
    bundle = with_events(base, billing_after(base, bill, FEB_20, cancellable=False))
    book, flows, states = _billing_flows(monkeypatch, bundle)
    assert flows == [(100_000, FEB_20, FEB_20, None, bill.event_key)]
    assert _positions(states[-1]) == {P01: 0, P02: 100_000, P03: 100_000}
    assert journal(book, JET_03, P01) == []
    assert journal(book, JET_03, P02) == [(AR, "D", 100_000), (CL, "C", 100_000)]
    assert [period_balance(book, p, "contract_liability_txn") for p in (P01, P02, P03)] == [
        0,
        100_000,
        100_000,
    ]


# --- POL-160 date policy ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("family", "key_id", "checkpoint"),
    [
        pytest.param("je", A38[1], "receipt-1-march", id="JE-CHK-024-CASEA"),
        pytest.param("pos", "POS-S9-PRESENTATION-EX38-CASEA", "1-march", id="POS-S9-CASEA"),
    ],
)
def test_invoice_issue_date_election_dates_an_engine_line_when_it_becomes_billing(
    monkeypatch: pytest.MonkeyPatch, family: str, key_id: str, checkpoint: str
) -> None:
    """Policy edge B (supervisor ruling): under the ASC606 POL-160 ``INVOICE_ISSUE_DATE`` election
    the "issue date" of an ENGINE-mode cancellable line is the S10-R-06 date it becomes billing
    (1 March, the receipt), so the layer is created when NP counts the line and S12-INV-03 ties:
    CL 0 / 0 / 1,000.00 on both Example 38 case A worlds. On d98b62d the flow carried the 31
    January memo issue date, the layer predated NP and the guard aborted the January close."""
    bundle = with_policy(
        checkpoint_bundle(family, key_id, checkpoint), "fx.cl_layer_date", "INVOICE_ISSUE_DATE"
    )
    bill = first_billing(bundle)
    book, flows, states = _billing_flows(monkeypatch, bundle)
    assert flows == [(100_000, MAR_1, MAR_1, MAR_1, bill.event_key)]
    assert _positions(states[-1]) == {P01: 0, P02: 0, P03: 100_000}
    assert [period_balance(book, p, "contract_liability_txn") for p in (P01, P02, P03)] == [
        0,
        0,
        100_000,
    ]


def test_invoice_issue_date_election_fx_engine_line_takes_the_rate_of_its_billing_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FX-CHK-083 (EUR 12,000 invoiced 1 January at 1.1000; closing 1.1200; January revenue EUR
    1,000) with the line cancellable, a same-amount noncancellable update on 20 January and a 20
    January spot of 1.1500, under the ``INVOICE_ISSUE_DATE`` election: the line becomes billing on
    20 January, so its layer takes 1.1500 (13,800.00), the FIFO relief 1,150.00 and the January
    contract liability USD 12,650.00; the receivable, created at the S10-R-06 date, is remeasured
    to 13,440.00. Both dates fall in January, so the memo-date reading (layer at 1.1000, CL
    12,100.00, the d98b62d figure) differs by rate alone, not by the S12-INV-03 tie."""
    base = checkpoint_bundle(*FX_083)
    bill = first_billing(base)
    base = replace_payload(base, bill.event_key, is_cancellable=True)
    spot = next(r for r in base.fx_rates if r.rate_type == "spot")
    added = FxRateInput(
        rate_key="SPOT-EURUSD/EUR/USD/2026-01-20/",
        version_key=spot.version_key,
        rate_type="spot",
        base_currency="EUR",
        quote_currency="USD",
        effective_date=JAN_20,
        period_key=None,
        rate=Decimal("1.1500"),
    )
    rates = tuple(
        sorted(
            (*base.fx_rates, added),
            key=lambda r: (
                r.rate_type,
                r.base_currency,
                r.quote_currency,
                r.effective_date,
                r.version_key,
            ),
        )
    )
    base = with_policy(
        dataclasses.replace(base, fx_rates=rates), "fx.cl_layer_date", "INVOICE_ISSUE_DATE"
    )
    bundle = with_events(base, billing_after(base, first_billing(base), JAN_20, cancellable=False))
    book, flows, states = _billing_flows(monkeypatch, bundle)
    assert flows == [(1_200_000, JAN_20, JAN_20, None, bill.event_key)]
    assert _positions(states[-1]) == {P01: 1_100_000}
    assert _liability_layers(book, 1_200_000) == {(bill.event_key, 1_380_000)}
    assert period_balance(book, P01, "contract_liability_txn") == 1_100_000
    assert period_balance(book, P01, "contract_liability_functional") == 1_265_000
    assert period_balance(book, P01, "accounts_receivable_functional") == 1_344_000


def test_erp_lines_keep_their_issue_date_and_due_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """ERP mode (JE-CHK-024 case A under ``billing.posting`` ERP): every line is unconditional at
    issue, so the flow keeps the 31 January issue date and its payload due date (D-87 L6-5-Q-14);
    the receipt of 1 March stays the first receipt."""
    bundle = with_policy(checkpoint_bundle(*A38, "receipt-1-march"), "billing.posting", "ERP")
    bill = first_billing(bundle)
    _, flows, _ = _billing_flows(monkeypatch, bundle)
    assert flows == [(100_000, JAN_31, JAN_31, MAR_1, bill.event_key)]


# --- ERP lines of one invoice with different due dates: per-line POL-160 dates and rates --------


def _two_due_dates(receipt: date | None) -> tuple[InputBundle, str, str]:
    """FX-POL-160 (ERP, EUR 12,000 invoiced 1 January, ASC606 ``INVOICE_ISSUE_DATE`` election,
    IFRS15 forced earlier-of) with the invoice split into two EUR 6,000 lines due 10 January and
    31 January, and the receipt removed or moved to ``receipt`` (a 20 January spot of 1.1200 is
    added to the rate set for that date)."""
    base = checkpoint_bundle(*FX_160)
    bill = first_billing(base)
    base = replace_payload(base, bill.event_key, amount=Decimal("6000.00"), due_date=JAN_10)
    second = billing_after(
        base,
        first_billing(base),
        JAN_1,
        line_external_id="INV-EU-0401-2",
        amount=Decimal("6000.00"),
        due_date=JAN_31,
    )
    events = []
    for event in base.events:
        if event.event_type != "PAYMENT_RECEIVED":
            events.append(event)
        elif receipt is not None:
            payload = {**event.payload, "receipt_date": receipt}
            events.append(
                dataclasses.replace(
                    event,
                    effective_date=receipt,
                    recorded_at=datetime(receipt.year, receipt.month, receipt.day, 17, tzinfo=UTC),
                    payload=payload,
                )
            )
    rates = tuple(base.fx_rates)
    if receipt is not None and not any(
        r.rate_type == "spot" and r.effective_date == receipt for r in rates
    ):
        spot = next(r for r in rates if r.rate_type == "spot")
        added = FxRateInput(
            rate_key=f"SPOT-EURUSD/EUR/USD/{receipt.isoformat()}/",
            version_key=spot.version_key,
            rate_type="spot",
            base_currency="EUR",
            quote_currency="USD",
            effective_date=receipt,
            period_key=None,
            rate=Decimal("1.1200"),
        )
        rates = tuple(  # the bundle's rate order (rate type, base, quote, date, version)
            sorted(
                (*rates, added),
                key=lambda r: (
                    r.rate_type,
                    r.base_currency,
                    r.quote_currency,
                    r.effective_date,
                    r.version_key,
                ),
            )
        )
    base = dataclasses.replace(base, events=tuple(events), fx_rates=rates)
    return with_events(base, second), bill.event_key, second.event_key


@pytest.mark.parametrize(
    ("receipt", "ifrs_liability", "ifrs_layers"),
    [
        pytest.param(None, 993_000, {660_000, 663_000}, id="no_receipt"),
        pytest.param(JAN_20, 1_002_000, {660_000, 672_000}, id="receipt_20_jan_at_1_1200"),
    ],
)
def test_erp_lines_with_different_due_dates_take_their_own_layer_dates(
    monkeypatch: pytest.MonkeyPatch,
    receipt: date | None,
    ifrs_liability: int,
    ifrs_layers: set[int],
) -> None:
    """Two EUR 6,000 lines issued 1 January, due 10 January and 31 January; EUR 1,000 of revenue a
    month relieved FIFO through March. IFRS15 (earlier-of): line 1 layers at 10 January (1.1000,
    USD 6,600.00) and line 2 at 31 January (1.1050, 6,630.00), or at the 20 January receipt
    (1.1200, 6,720.00) when it comes first; after the 3,000 × 1.1000 relief the March contract
    liability is USD 9,930.00 / 10,020.00 (one document-level layer at 10 January gave 9,900.00).
    ASC606 (``INVOICE_ISSUE_DATE``): both at 1 January 1.0900, 9,810.00 either way. One flow per
    line with its own due date, receipt and lineage; the layers name their lines."""
    bundle, first, second = _two_due_dates(receipt)
    _, flows, _ = _billing_flows(monkeypatch, bundle, "ASC606")
    assert flows == [
        (600_000, JAN_1, JAN_10, receipt, first),
        (600_000, JAN_1, JAN_31, receipt, second),
    ]
    asc = compute_book(bundle, "ASC606")
    assert period_balance(asc, P03, "contract_liability_functional") == 981_000
    assert _liability_layers(asc, 600_000) == {(first, 654_000), (second, 654_000)}
    ifrs = compute_book(bundle, "IFRS15")
    assert period_balance(ifrs, P03, "contract_liability_functional") == ifrs_liability
    assert period_balance(ifrs, P03, "contract_liability_txn") == 900_000
    assert _liability_layers(ifrs, 600_000) == {
        (first, 660_000),
        (second, max(ifrs_layers)),
    }


# --- Foreign currency: a memo line adds no layer and moves no functional figure ------------------


def test_fx_entity_memo_line_keeps_every_functional_figure(monkeypatch: pytest.MonkeyPatch) -> None:
    """FX-CHK-083 (EUR 12,000 invoiced 1 January at 1.1000, January revenue EUR 1,000, closing
    1.1200) plus a cancellable memo repeat of EUR 12,000 (distinct line id): no second layer, no
    receivable item, no JET-03; CL functional 12,100.00, AR functional 13,440.00 and the 240.00 FX
    gain are exactly the keyed figures (on 0104e86 the document flow of 24,000 aborted the run on
    S12-INV-03: layers 23,000 against NP 11,000)."""
    base = checkpoint_bundle(*FX_083)
    bill = first_billing(base)
    keyed = compute_book(base)
    bundle = with_events(
        base,
        billing_after(base, bill, JAN_1, cancellable=True, line_external_id="INV-EU-0301-9"),
    )
    book, flows, states = _billing_flows(monkeypatch, bundle)
    assert flows == [(1_200_000, JAN_1, JAN_1, None, bill.event_key)]
    assert _positions(states[-1]) == {P01: 1_100_000}
    for column in (
        "contract_liability_txn",
        "contract_liability_functional",
        "accounts_receivable_txn",
        "accounts_receivable_functional",
    ):
        assert period_balance(book, P01, column) == period_balance(keyed, P01, column), column
    assert period_balance(book, P01, "contract_liability_functional") == 1_210_000
    assert period_balance(book, P01, "accounts_receivable_functional") == 1_344_000
    assert journal(book, JET_03, P01) == journal(keyed, JET_03, P01)
    assert sorted(
        (intent.entry_kind, line.account_role, line.side, line.amount_functional)
        for intent in book.posting_intents
        for line in intent.lines
    ) == sorted(
        (intent.entry_kind, line.account_role, line.side, line.amount_functional)
        for intent in keyed.posting_intents
        for line in intent.lines
    )
