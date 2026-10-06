"""RPT-03 ``contract_balance_rollforward``: the path over the flows of the control role, the
billing that posts no line and the line of each kind (SCREENS_B §5.6.1 RPT-03 "kind → line";
ENGINE_SPEC_B §15.2.2 S15-R-03, S15-R-03a, S15-R-07, EX-15-B; S10-R-07, S10-R-08; POLICIES POL-004;
03 REQ-RPT-006; supervisor ruling R-72). CPU: the builder's pure functions over flat records
(DG-TST-18); the report runs through the product in ``tests/domain/reports``."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.reports import catalogue, framework, tie_outs
from erev_api.domain.reports.builders import contract_balance_rollforward as cbr
from erev_api.domain.reports.tie_outs import PeriodRef
from erev_api.enums import SubledgerEntryKind
from support import report_specs

D = Decimal
LIABILITY, ASSET, UNBILLED = "contract_liability", "contract_asset", "unbilled_receivable"
NONE = {LIABILITY: D(0), ASSET: D(0), UNBILLED: D(0)}
AUGUST = PeriodRef(
    UUID(int=8), "FY2026-P08", "Aug 2026", 2026, 8, 3, date(2026, 8, 1), date(2026, 8, 31)
)
SEPTEMBER = PeriodRef(
    UUID(int=9), "FY2026-P09", "Sep 2026", 2026, 9, 3, date(2026, 9, 1), date(2026, 9, 30)
)


def column(lines: Any, balance: str) -> dict[str, Decimal]:
    """The non-zero cells of one balance, by line code in report order."""
    return {line: lines[line][balance] for line in cbr.LINES if lines[line][balance] != 0}


def ties(lines: Any) -> bool:
    return all(lines["OTHER"][balance] == 0 for balance in NONE)


def line(period: PeriodRef, kind: str, amount: str, day: date) -> cbr.Entry:
    return cbr.Entry(
        order=(day, cbr.LINE_RANK),
        flow=cbr.line_flow(kind, D(amount)),
        period_id=period.id,
        entry_kind=kind,
    )


# --- the kinds and their lines (R-72 (c)) ---------------------------------------------------------


def test_every_entry_kind_has_a_family_and_every_family_a_line() -> None:
    """A subledger line's family follows its entry kind (04 E-29; ENGINE_SPEC_B Table 14-A):
    JET-03 invoices and credit memos are billing; revenue relief and its reversal, the contracting
    side of an intercompany pair included, are revenue; every other kind is a reclassification."""
    assert cbr.FAMILIES == {
        "BILLING": cbr.BILLING,
        "CREDIT_MEMO": cbr.BILLING,
        "REVENUE_RECOGNITION": cbr.REVENUE,
        "INTERCOMPANY": cbr.REVENUE,
    }
    assert set(cbr.FAMILIES) <= {kind.value for kind in SubledgerEntryKind}
    assert cbr.FAMILY_LINES == {
        cbr.BILLING: "BILLINGS",
        cbr.REVENUE: "REVENUE_FROM_PERIOD_BILLINGS",
        cbr.RECLASSIFICATION: "RECLASSIFICATIONS",
    }
    assert set(cbr.FAMILY_LINES.values()) <= set(cbr.LINES)
    for kind in SubledgerEntryKind:
        flow = cbr.line_flow(kind.value, D("1.00"))
        expected = cbr.FAMILIES.get(kind.value, cbr.RECLASSIFICATION)
        assert (cbr.family_of(flow), flow.is_revenue) == (expected, expected == cbr.REVENUE), kind
    # the reading before kinds, which EX-15-B's flows use: a credit is billing, a debit revenue
    # relief or another decrease
    assert cbr.family_of(cbr.Flow(D("-1.00"), False)) == cbr.BILLING
    assert cbr.family_of(cbr.Flow(D("1.00"), True)) == cbr.REVENUE
    assert cbr.family_of(cbr.Flow(D("1.00"), False)) == cbr.RECLASSIFICATION


def test_the_specification_states_the_table_kind_to_line() -> None:
    """SCREENS_B RPT-03 names the line of every kind of ENGINE_SPEC_B S15-R-03, and ENGINE_SPEC_B
    S15-R-03a the flows that post no line."""
    section = report_specs.section(3, cbr.CODE)
    assert "supervisor ruling R-72" in section
    for kind in (
        "BILLING",
        "CREDIT_MEMO",
        "NEGATIVE_REVENUE",
        "DEPOSIT_TRANSFER",
        "NONCASH",
        "FINANCING",
        "REFUND_LIABILITY",
        "REFUND_RELEASE",
        "CONTRA",
    ):
        assert f"`{kind}`" in section, kind
    rule = next(
        row
        for row in report_specs.read("docs/accounting/ENGINE_SPEC_B.md").splitlines()
        if row.startswith("| S15-R-03a |")
    )
    assert "`billed_unconditional_cum`" in rule and "R-72 (a)" in rule


def test_each_family_is_shown_under_its_line_on_both_sides() -> None:
    """A deposit transfer (credit), a refund-liability increase (debit), a credit memo (debit),
    negative revenue (credit) and the relief of an obligation another entity performs (debit)
    against an opening liability of 100.00."""
    flows = [
        cbr.line_flow("DEPOSIT", D("-50.00")),
        cbr.line_flow("REFUND_LIABILITY", D("20.00")),
        cbr.line_flow("CREDIT_MEMO", D("10.00")),
        cbr.line_flow("REVENUE_RECOGNITION", D("-5.00")),
        cbr.line_flow("INTERCOMPANY", D("90.00")),
    ]
    lines = cbr.path({**NONE, LIABILITY: D("100.00")}, flows, {**NONE, LIABILITY: D("35.00")})
    # first in first out: the refund increase and the credit memo take 30.00 of the opening layer,
    # the relief its other 70.00 and 20.00 of the deposit layer
    assert column(lines, LIABILITY) == {
        "OPENING": D("100.00"),
        "BILLINGS": D("-10.00"),
        "REVENUE_FROM_OPENING": D("-70.00"),
        "REVENUE_FROM_PERIOD_BILLINGS": D("-15.00"),  # +5.00 negative revenue, -20.00 relief
        "RECLASSIFICATIONS": D("30.00"),  # +50.00 deposit transfer, -20.00 refund liability
        "CLOSING": D("35.00"),
    }
    assert column(lines, ASSET) == {} and ties(lines)


@pytest.mark.parametrize(
    ("kind", "line_code"),
    [
        ("DEPOSIT", "RECLASSIFICATIONS"),  # JET-01b criteria met
        ("NONCASH_CONSIDERATION", "RECLASSIFICATIONS"),  # JET-17
        ("FINANCING_INTEREST", "RECLASSIFICATIONS"),  # JET-11b accretion of an advance
        ("REFUND_LIABILITY", "RECLASSIFICATIONS"),  # JET-04b release
        ("RECEIVABLE_CONTRA", "RECLASSIFICATIONS"),  # JET-04c release
        ("BILLING", "BILLINGS"),  # JET-03 invoice, ENGINE mode
        ("REVENUE_RECOGNITION", "REVENUE_FROM_PERIOD_BILLINGS"),  # negative revenue
    ],
)
def test_a_credit_of_each_kind_settles_the_asset_then_opens_a_layer(
    kind: str, line_code: str
) -> None:
    opening = {**NONE, ASSET: D("40.00")}
    lines = cbr.path(opening, [cbr.line_flow(kind, D("-100.00"))], {**NONE, LIABILITY: D("60.00")})
    assert column(lines, ASSET) == {"OPENING": D("40.00"), line_code: D("-40.00")}
    assert column(lines, LIABILITY) == {line_code: D("60.00"), "CLOSING": D("60.00")}
    assert ties(lines)


@pytest.mark.parametrize(
    ("kind", "line_code"),
    [
        ("REFUND_LIABILITY", "RECLASSIFICATIONS"),  # JET-04b increase
        ("RECEIVABLE_CONTRA", "RECLASSIFICATIONS"),  # JET-04c
        ("FINANCING_INTEREST", "RECLASSIFICATIONS"),  # JET-11a
        ("CREDIT_MEMO", "BILLINGS"),  # JET-03 credit memo, ENGINE mode
    ],
)
def test_a_debit_of_each_kind_consumes_the_layers_then_becomes_an_asset(
    kind: str, line_code: str
) -> None:
    opening = {**NONE, LIABILITY: D("30.00")}
    lines = cbr.path(opening, [cbr.line_flow(kind, D("50.00"))], {**NONE, ASSET: D("20.00")})
    assert column(lines, LIABILITY) == {"OPENING": D("30.00"), line_code: D("-30.00")}
    assert column(lines, ASSET) == {line_code: D("20.00"), "CLOSING": D("20.00")}
    assert ties(lines)


def test_negative_revenue_is_not_a_billing() -> None:
    """The one credit on the role of the demo's AVM-US in Sep 2026: revenue reversed on a contract
    that was never billed. It reduces the contract asset under the revenue line."""
    opening = {**NONE, ASSET: D("500.00")}
    closing = {**NONE, ASSET: D("361.92")}
    lines = cbr.path(opening, [cbr.line_flow("REVENUE_RECOGNITION", D("-138.08"))], closing)
    assert column(lines, ASSET) == {
        "OPENING": D("500.00"),
        "REVENUE_FROM_PERIOD_BILLINGS": D("-138.08"),
        "CLOSING": D("361.92"),
    }
    assert lines["BILLINGS"] == NONE and ties(lines)


# --- the billing that posts no line (R-72 (a)) ----------------------------------------------------


def test_k09_september_with_its_invoice_on_the_path() -> None:
    """WLD-K-09: INV-US-3101 36,000.00 of 01 Sep 2026 posts no line under ``billing.posting =
    ERP``; September's revenue is 2,956.20. With the document on the path the period ties."""
    document = cbr.Document(date(2026, 9, 1), 3, UUID(int=3), D("36000.00"))
    revenue = line(SEPTEMBER, "REVENUE_RECOGNITION", "2956.20", date(2026, 9, 1))
    closing = {**NONE, LIABILITY: D("33043.80")}
    # the lines alone: what the builder read before — nothing explains the closing
    alone = cbr.path(NONE, [revenue.flow], closing)
    assert (alone["OTHER"][LIABILITY], alone["OTHER"][ASSET]) == (D("33043.80"), D("-2956.20"))
    wanted = cbr.unposted_periods([(SEPTEMBER, D("36000.00"))], [revenue])
    assert wanted == [SEPTEMBER]
    entries = sorted(
        [revenue, *cbr.document_entries(wanted, [document])], key=lambda entry: entry.order
    )
    lines = cbr.path(NONE, [entry.flow for entry in entries], closing)
    assert column(lines, LIABILITY) == {
        "BILLINGS": D("36000.00"),
        "REVENUE_FROM_PERIOD_BILLINGS": D("-2956.20"),
        "CLOSING": D("33043.80"),
    }
    assert column(lines, ASSET) == {} and ties(lines)


def test_a_period_names_its_documents_only_when_its_billing_is_not_on_the_role() -> None:
    revenue = line(SEPTEMBER, "REVENUE_RECOGNITION", "2956.20", date(2026, 9, 1))
    invoice = line(SEPTEMBER, "BILLING", "-36000.00", date(2026, 9, 1))
    memo = line(SEPTEMBER, "CREDIT_MEMO", "500.00", date(2026, 9, 20))
    # ERP: the engine counted billing and the role holds none of it
    assert cbr.unposted_periods([(AUGUST, D(0)), (SEPTEMBER, D("36000.00"))], [revenue]) == [
        SEPTEMBER
    ]
    # ENGINE: JET-03 posted it — the lines are the flows
    assert cbr.unposted_periods([(SEPTEMBER, D("36000.00"))], [revenue, invoice]) == []
    assert cbr.unposted_periods([(SEPTEMBER, D("35500.00"))], [revenue, invoice, memo]) == []
    # nothing billed in the period, or an invoice the engine does not count yet (ENGINE mode, a
    # cancellable line before it is unconditional): no document enters
    assert cbr.unposted_periods([(SEPTEMBER, D(0))], [revenue]) == []
    # billing lines that differ from the delta: no document is added on top — the difference
    # stays unexplained
    assert cbr.unposted_periods([(SEPTEMBER, D("40000.00"))], [invoice]) == []
    # a net credit of the period (credit memos above the invoices) is billing not on the role too
    assert cbr.unposted_periods([(SEPTEMBER, D("-500.00"))], [revenue]) == [SEPTEMBER]


def test_documents_enter_at_their_dates_and_before_the_lines_of_that_date() -> None:
    documents = [
        cbr.Document(date(2026, 8, 31), 7, UUID(int=1), D("100.00")),
        cbr.Document(date(2026, 9, 1), 8, UUID(int=2), D("36000.00")),
        cbr.Document(date(2026, 9, 20), 9, UUID(int=3), D("-500.00")),
    ]
    entries = cbr.document_entries([SEPTEMBER], documents)
    # an invoice credits the role, a credit memo debits it; August's document is not September's
    assert [(entry.order[0], entry.flow.amount, entry.flow.kind) for entry in entries] == [
        (date(2026, 9, 1), D("-36000.00"), cbr.BILLING),
        (date(2026, 9, 20), D("500.00"), cbr.BILLING),
    ]
    assert all(entry.period_id is None and entry.entry_kind is None for entry in entries)
    revenue = line(SEPTEMBER, "REVENUE_RECOGNITION", "2956.20", date(2026, 9, 1))
    ordered = sorted([revenue, *entries], key=lambda entry: entry.order)
    assert [entry.flow.amount for entry in ordered] == [D("-36000.00"), D("2956.20"), D("500.00")]
    assert cbr.document_entries([], documents) == []


def test_a_difference_between_the_documents_and_the_engines_delta_is_never_plugged() -> None:
    """The engine counted 36,000.00; the documents of the period say 30,000.00. They enter as
    recorded and the difference stays ``OTHER``: the tie-out fails."""
    document = cbr.Document(date(2026, 9, 1), 3, UUID(int=3), D("30000.00"))
    entries = cbr.document_entries([SEPTEMBER], [document])
    lines = cbr.path(NONE, [entry.flow for entry in entries], {**NONE, LIABILITY: D("36000.00")})
    assert lines["BILLINGS"][LIABILITY] == D("30000.00")
    assert lines["OTHER"][LIABILITY] == D("6000.00") and not ties(lines)


def event(number: int, event_type: str, day: date, payload: dict[str, Any]) -> Any:
    return cbr._StoredEvent(UUID(int=number), UUID(int=99), event_type, day, number, payload)


def test_kept_documents_follow_the_engines_identity_rule() -> None:
    """ENGINE_SPEC_B S10-R-07 through ``erev_engine.billing_identity``: the first event of an
    invoice line is the line, a repeat is a status update that adds no billing; a credit memo is
    negative; an event an ``EVENT_VOIDED`` names is gone."""
    usd = {"amount": "100.00", "currency": "USD"}
    invoice = {"invoice_number": "INV-1", "line_external_id": "1", "amount": usd}
    first = event(1, "BILLING_RECORDED", date(2026, 9, 1), invoice)
    update = event(2, "BILLING_RECORDED", date(2026, 9, 5), invoice)
    second = event(3, "BILLING_RECORDED", date(2026, 9, 6), {**invoice, "invoice_number": "INV-2"})
    memo = event(
        4,
        "CREDIT_MEMO_RECORDED",
        date(2026, 9, 9),
        {"credit_memo_number": "CM-1", "amount": {"amount": "30.00", "currency": "USD"}},
    )
    found = cbr.kept_documents([first, update, second, memo], voided=[])
    assert [(item.event_id.int, item.effective_date.day, item.amount) for item in found] == [
        (1, 1, D("100.00")),
        (3, 6, D("100.00")),
        (4, 9, D("-30.00")),
    ]
    voided = cbr.kept_documents([first, update, second, memo], voided=[UUID(int=3)])
    assert [item.event_id.int for item in voided] == [1, 4]
    with pytest.raises(ValueError, match="no amount"):
        cbr.kept_documents([event(5, "BILLING_RECORDED", date(2026, 9, 1), {})], voided=[])


# --- the engine's billed amount (S10-R-08) --------------------------------------------------------


def test_billed_through_reads_the_engines_node_as_a_balance_is_read() -> None:
    """``billed_unconditional_cum:<contract>@<entity>:<period>`` (ENGINE_SPEC_B §10.5), read as
    S15-R-07a reads a balance: the latest node at or before the period, 0 before the first and
    for no period; the subject key is the engine's (CV-21 on each component)."""
    traced = tie_outs.traced_balances(
        [
            ("billed_unconditional_cum:SF-ORD-10417@AVM-US:FY2026-P09", "36000.00"),
            ("billed_unconditional_cum:SF-ORD-10417@AVM-US:FY2026-P11", "72000.00"),
            ("billed_unconditional_cum:A%3AB@AVM%2FUS:FY2026-P09", "5.00"),
            ("contract_liability:SF-ORD-10417@AVM-US:FY2026-P09", "33043.80"),
            ("billed_cum:SF-ORD-10417/O1:FY2026-P09", "36000.00"),  # per obligation: not read
        ]
    )

    def billed(period_key: str | None, external_id: str = "SF-ORD-10417") -> Decimal:
        return tie_outs.billed_through(
            traced, external_id=external_id, entity_code="AVM-US", period_key=period_key
        )

    assert [billed(key) for key in (None, "FY2026-P08", "FY2026-P09", "FY2026-P10")] == [
        D(0),
        D(0),
        D("36000.00"),
        D("36000.00"),
    ]
    assert billed("FY2026-P12") == D("72000.00")
    assert billed("FY2026-P09", "SF-ORD-10001") == D(0)  # a subject without a node: nothing billed
    assert tie_outs.billed_through(
        traced, external_id="A:B", entity_code="AVM/US", period_key="FY2026-P09"
    ) == D("5.00")
    # the balances are read as before: the billed nodes are no balance measure
    assert set(traced.nodes) == {"contract_liability:SF-ORD-10417@AVM-US"}
    assert traced.latest == {"SF-ORD-10417@AVM-US": "FY2026-P09"}


# --- the declarations -----------------------------------------------------------------------------


def test_the_billing_events_are_a_bound_source_and_an_ipe_source() -> None:
    """S15-R-24: the billing events the path consumed are members of the run's binding; the
    definition names the events and the engine's node among its sources (REQ-RPT-027)."""
    contract = framework.SOURCE_CONTRACTS[cbr.CODE]
    assert contract.open == ()
    assert any("billing-event membership" in item for item in contract.bound)
    logic = catalogue.DEFINITIONS_BY_CODE[cbr.CODE].ipe_logic
    assert {"contract_event", "calc_trace"} <= set(logic["source_tables"])
    assert any("billed_unconditional_cum" in item for item in logic["filters"])
