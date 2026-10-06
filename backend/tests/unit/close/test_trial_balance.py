"""The subledger-to-GL comparison and the uploaded trial balance, without a database (BUILD_SPEC
CLO-17; 03 REQ-CLS-016; 04 T-CLS-06 ``totals``, T-CLS-07; SCREENS_B §2.2; PRD WLD-B-07; supervisor
rulings R-69 and R-74 for the role basis).

Figures: account 2100 carries the contract liability (credit, so negative), 4000 revenue, 1200
unbilled receivable. ``difference`` is GL − subledger on totals and items.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from erev_api.domain.close import trial_balance as tb
from erev_api.domain.imports.parse import SheetRows
from erev_api.domain.journals.ports import TrialBalanceDetail, TrialBalanceLine

USD = "USD"
SCOPE = ("1200", "2100", "4000")


def _d(text: str) -> Decimal:
    return Decimal(text)


def _held(**amounts: str) -> list[tb.AccountBalance]:
    return [tb.AccountBalance(account_code=code[1:], amount=_d(amounts[code])) for code in amounts]


def _stated(**amounts: str) -> list[TrialBalanceLine]:
    return [
        TrialBalanceLine(account_code=code[1:], currency=USD, amount=_d(amounts[code]))
        for code in amounts
    ]


def _portion(
    reference: str,
    account: str,
    amount: str,
    *,
    in_subledger: bool = True,
    posted: bool = False,
    in_ledger: bool = False,
    document: str | None = None,
) -> tb.BatchPortion:
    return tb.BatchPortion(
        reference=reference,
        account_code=account,
        amount=_d(amount),
        in_subledger=in_subledger,
        posted=posted,
        in_ledger=in_ledger,
        gl_document_reference=document,
    )


def _facts(item: tb.Item) -> tuple[str, str, Decimal | None, Decimal | None, Decimal, str | None]:
    return (
        item.item_kind,
        item.account_code,
        item.subledger_amount,
        item.source_amount,
        item.difference,
        item.gl_document_reference,
    )


def test_equal_balances_have_no_item() -> None:
    found = tb.compare(
        currency=USD,
        accounts=SCOPE,
        subledger=_held(a1200="3000.00", a2100="-29944.11", a4000="-90055.89"),
        portions=[],
        lines=_stated(a1200="3000.00", a2100="-29944.11", a4000="-90055.89", a6100="815.00"),
    )
    assert found.items == ()
    assert [
        (row.account_code, row.currency, row.subledger_amount, row.source_amount, row.difference)
        for row in found.totals
    ] == [
        ("1200", USD, _d("3000.00"), _d("3000.00"), _d("0.00")),
        ("2100", USD, _d("-29944.11"), _d("-29944.11"), _d("0.00")),
        ("4000", USD, _d("-90055.89"), _d("-90055.89"), _d("0.00")),
    ]
    # Account 6100 is not subledger-controlled: its row is not compared.
    assert (found.ignored_lines, found.direct_entries) == (1, 0)


def test_direct_gl_entry_is_high_risk_with_its_document() -> None:
    """PRD WLD-B-07 / J-13.11: ``JE-NS-88121`` USD 250.00 on account 2100 made in the ERP."""
    found = tb.compare(
        currency=USD,
        accounts=SCOPE,
        subledger=_held(a2100="-29944.11", a4000="-90055.89"),
        portions=[
            _portion("erev:avm:JR-000012:1:1", "2100", "9764.38", posted=True, in_ledger=True),
            _portion("erev:avm:JR-000012:1:1", "4000", "-9764.38", posted=True, in_ledger=True),
        ],
        lines=_stated(a2100="-29694.11", a4000="-90055.89"),
        details=[
            TrialBalanceDetail("2100", USD, _d("9764.38"), "JE-NS-88001", "erev:avm:JR-000012:1:1"),
            TrialBalanceDetail(
                "4000", USD, _d("-9764.38"), "JE-NS-88001", "erev:avm:JR-000012:1:1"
            ),
            TrialBalanceDetail("2100", USD, _d("250.00"), "JE-NS-88121", None, date(2026, 9, 28)),
            TrialBalanceDetail("6100", USD, _d("815.00"), "JE-NS-88122", None),
        ],
        own_references=["erev:avm:JR-000012:1:1"],
    )
    (item,) = found.items
    assert _facts(item) == (
        "DIRECT_GL_ENTRY",
        "2100",
        _d("0"),
        _d("250.00"),
        _d("250.00"),
        "JE-NS-88121",
    )
    assert item.is_high_risk is True
    assert [(row.account_code, row.difference) for row in found.totals] == [
        ("2100", _d("250.00")),
        ("4000", _d("0.00")),
    ]
    assert found.direct_entries == 1


def test_a_document_with_an_unknown_external_id_is_a_direct_entry() -> None:
    found = tb.compare(
        currency=USD,
        accounts=SCOPE,
        subledger=_held(a2100="-100.00"),
        portions=[],
        lines=_stated(a2100="-60.00"),
        details=[TrialBalanceDetail("2100", USD, _d("40.00"), "JE-7", "erev:other:JR-000001:1:1")],
        own_references=[],
    )
    assert [_facts(item) for item in found.items] == [
        ("DIRECT_GL_ENTRY", "2100", _d("0"), _d("40.00"), _d("40.00"), "JE-7")
    ]


def test_unposted_batch_one_item_per_account() -> None:
    """A batch the GL has not acknowledged: its amount on each account is what the GL lacks."""
    found = tb.compare(
        currency=USD,
        accounts=SCOPE,
        subledger=_held(a2100="-29944.11", a4000="-90055.89"),
        portions=[
            _portion("erev:avm:JR-000013:1:1", "2100", "9764.38"),
            _portion("erev:avm:JR-000013:1:1", "4000", "-9764.38"),
            # a batch of a later period is on neither side yet
            _portion("erev:avm:JR-000014:1:1", "4000", "-500.00", in_subledger=False),
            # a line that nets to nothing on its account is no difference
            _portion("erev:avm:JR-000013:1:1", "1200", "0.00"),
        ],
        lines=_stated(a2100="-39708.49", a4000="-80291.51"),
    )
    assert [_facts(item) for item in found.items] == [
        (
            "UNPOSTED_BATCH",
            "2100",
            _d("9764.38"),
            _d("0"),
            _d("-9764.38"),
            "erev:avm:JR-000013:1:1",
        ),
        (
            "UNPOSTED_BATCH",
            "4000",
            _d("-9764.38"),
            _d("0"),
            _d("9764.38"),
            "erev:avm:JR-000013:1:1",
        ),
    ]
    assert all(item.is_high_risk is False for item in found.items)
    assert sum((row.difference for row in found.totals), _d("0")) == _d("0.00")


def test_unacknowledged_batch_the_ledger_already_shows_is_not_itemised() -> None:
    found = tb.compare(
        currency=USD,
        accounts=SCOPE,
        subledger=_held(a2100="-100.00"),
        portions=[_portion("erev:avm:JR-000020:1:1", "2100", "-100.00")],
        lines=_stated(a2100="-100.00"),
        details=[
            TrialBalanceDetail("2100", USD, _d("-100.00"), "JE-NS-1", "erev:avm:JR-000020:1:1")
        ],
        own_references=["erev:avm:JR-000020:1:1"],
    )
    assert found.items == ()


def test_timing_in_both_directions() -> None:
    found = tb.compare(
        currency=USD,
        accounts=SCOPE,
        subledger=_held(a2100="-700.00"),
        portions=[
            # acknowledged, but the GL dated it after the period end
            _portion("erev:avm:JR-000030:1:1", "2100", "-200.00", posted=True, document="JE-NS-9"),
            # a batch of the next period that the GL dated into this one
            _portion(
                "erev:avm:JR-000031:1:1",
                "2100",
                "-50.00",
                in_subledger=False,
                posted=True,
                in_ledger=True,
            ),
            # acknowledged inside the window on both sides: nothing to say
            _portion("erev:avm:JR-000029:1:1", "2100", "-500.00", posted=True, in_ledger=True),
        ],
        lines=_stated(a2100="-550.00"),
    )
    assert [_facts(item) for item in found.items] == [
        ("TIMING", "2100", _d("-200.00"), _d("0"), _d("200.00"), "JE-NS-9"),
        ("TIMING", "2100", _d("0"), _d("-50.00"), _d("-50.00"), "erev:avm:JR-000031:1:1"),
    ]


def test_what_nothing_explains_is_other() -> None:
    """An uploaded trial balance names no document: the difference of WLD-B-07 is ``OTHER``."""
    found = tb.compare(
        currency=USD,
        accounts=SCOPE,
        subledger=_held(a2100="-29944.11", a4000="-90055.89"),
        portions=[],
        lines=_stated(a2100="-29694.11", a4000="-90055.89"),
    )
    assert [_facts(item) for item in found.items] == [
        ("OTHER", "2100", None, None, _d("250.00"), None)
    ]
    assert found.items[0].is_high_risk is False


def test_documents_are_listed_even_when_the_balance_agrees() -> None:
    """The reversal ``JE-NS-88410`` of 01 Oct 2026: October's balance agrees again, the document
    is still a direct entry, and the difference it cleared is the carried-forward one."""
    found = tb.compare(
        currency=USD,
        accounts=SCOPE,
        subledger=_held(a2100="-20179.73"),
        portions=[],
        lines=_stated(a2100="-20179.73"),
        details=[TrialBalanceDetail("2100", USD, _d("-250.00"), "JE-NS-88410", None)],
    )
    assert [_facts(item) for item in found.items] == [
        ("DIRECT_GL_ENTRY", "2100", _d("0"), _d("-250.00"), _d("-250.00"), "JE-NS-88410"),
        ("OTHER", "2100", None, None, _d("250.00"), None),
    ]
    assert [row.difference for row in found.totals] == [_d("0.00")]
    # Two documents of one period that cancel leave no residual.
    paired = tb.compare(
        currency=USD,
        accounts=SCOPE,
        subledger=_held(a2100="-100.00"),
        portions=[],
        lines=_stated(a2100="-100.00"),
        details=[
            TrialBalanceDetail("2100", USD, _d("250.00"), "JE-A", None),
            TrialBalanceDetail("2100", USD, _d("-250.00"), "JE-B", None),
        ],
    )
    assert [item.item_kind for item in paired.items] == ["DIRECT_GL_ENTRY", "DIRECT_GL_ENTRY"]


def test_an_account_on_one_side_only() -> None:
    found = tb.compare(
        currency=USD,
        accounts=SCOPE,
        subledger=_held(a2100="-100.00"),
        portions=[],
        lines=_stated(a1200="75.00"),
    )
    assert [
        (row.account_code, row.subledger_amount, row.source_amount, row.difference)
        for row in found.totals
    ] == [("1200", None, _d("75.00"), _d("75.00")), ("2100", _d("-100.00"), None, _d("100.00"))]
    assert [_facts(item) for item in found.items] == [
        ("OTHER", "1200", None, None, _d("75.00"), None),
        ("OTHER", "2100", None, None, _d("100.00"), None),
    ]


def test_what_is_outside_the_controlled_accounts_is_not_compared() -> None:
    found = tb.compare(
        currency=USD,
        accounts=("2100",),
        subledger=_held(a2100="-100.00"),
        portions=[_portion("erev:avm:JR-000040:1:1", "1000", "100.00")],
        lines=_stated(a2100="-100.00", a1000="4000.00", a6100="1.00"),
        details=[TrialBalanceDetail("1000", USD, _d("4000.00"), "JE-CASH", None)],
    )
    assert (found.items, found.ignored_lines) == ((), 2)
    assert [row.account_code for row in found.totals] == ["2100"]


# --- the role basis (supervisor rulings R-69 (a), R-74) -------------------------------------------

CL = "CONTRACT_LIABILITY"
CA = "CONTRACT_ASSET"
UR = "UNBILLED_RECEIVABLE"


def _row(total: tb.AccountTotal) -> tuple[object, ...]:
    return (
        total.account_role,
        total.account_code,
        total.account_codes,
        total.subledger_amount,
        total.source_amount,
        total.difference,
    )


def _role_facts(item: tb.Item) -> tuple[object, ...]:
    return (item.account_role, *_facts(item))


def test_role_row_states_the_stored_balance_not_the_posted_lines() -> None:
    """Supervisor ruling R-69 (measured on WLD-K-01, January 2026, ``billing.posting = ERP``): the
    subledger posts Dr 2100 / Cr 4010 16,569.86 and no billing line; the ledger holds 2100 at
    −103,430.14 — INV-US-1001 120,000.00 less the month's revenue. On the role basis the row of
    the contract liability states the stored closing balance and ties."""
    found = tb.compare(
        currency=USD,
        accounts=("2100", "4010"),
        subledger=_held(a2100="16569.86", a4010="-16569.86"),
        portions=[],
        lines=_stated(a2100="-103430.14", a4010="-16569.86"),
        roles=[tb.RoleBalance(CL, ("2100",), _d("-103430.14"))],
    )
    assert [_row(total) for total in found.totals] == [
        (CL, "2100", ("2100",), _d("-103430.14"), _d("-103430.14"), _d("0.00")),
        (None, "4010", (), _d("-16569.86"), _d("-16569.86"), _d("0.00")),
    ]
    assert found.items == ()
    assert (found.not_stated, found.erp_billing_documents) == (0, 0)
    # Without the role basis the same ledger differs by the invoice the subledger never posts.
    posted = tb.compare(
        currency=USD,
        accounts=("2100", "4010"),
        subledger=_held(a2100="16569.86", a4010="-16569.86"),
        portions=[],
        lines=_stated(a2100="-103430.14", a4010="-16569.86"),
    )
    assert [_facts(item) for item in posted.items] == [
        ("OTHER", "2100", None, None, _d("-120000.00"), None)
    ]


def test_role_with_several_accounts_is_one_row() -> None:
    """R-74 (c): the stored balance is per contract, not per account, so a role with several
    accounts is one row; its residual names the role and no single account."""
    found = tb.compare(
        currency=USD,
        accounts=(),
        subledger=_held(a2100="5.00", a2110="7.00"),  # posted balances of role accounts: not read
        portions=[_portion("erev:avm:JR-000050:1:1", "2110", "-25.00")],
        lines=_stated(a2100="-60.00", a2110="-15.00"),
        roles=[tb.RoleBalance(CL, ("2100", "2110"), _d("-110.00"))],
    )
    assert [_row(total) for total in found.totals] == [
        (CL, None, ("2100", "2110"), _d("-110.00"), _d("-75.00"), _d("35.00"))
    ]
    assert [_role_facts(item) for item in found.items] == [
        # the batch the ledger has not acknowledged, on its account and under the role
        (
            CL,
            "UNPOSTED_BATCH",
            "2110",
            _d("-25.00"),
            _d("0"),
            _d("25.00"),
            "erev:avm:JR-000050:1:1",
        ),
        # 35.00 less the 25.00 the batch explains
        (CL, "OTHER", None, None, None, _d("10.00"), None),
    ]


def test_role_the_subledger_does_not_state() -> None:
    """R-74 (a): a role whose stored balance is not held in the functional currency carries no
    subledger amount and no difference; one ``NOT_STATED`` item carries the ledger's balance,
    names the role and waits for the preparer's explanation. A batch explains no difference
    there; a document made in the ERP is still a direct entry."""
    reason = tb.NotStated(
        "1 contract holds no balance in USD at FY2026-P08", (("c-1", "SF-ORD-EU-3001"),)
    )
    found = tb.compare(
        currency=USD,
        accounts=("4010",),
        subledger=_held(a4010="-11000.00"),
        portions=[_portion("erev:avm:JR-000060:1:1", "1210", "11050.00")],
        lines=_stated(a1210="11050.00", a4010="-11000.00"),
        details=[TrialBalanceDetail("1210", USD, _d("40.00"), "JE-NS-9", None)],
        roles=[tb.RoleBalance(UR, ("1210",), None, reason)],
    )
    assert [_row(total) for total in found.totals] == [
        (UR, "1210", ("1210",), None, _d("11050.00"), None),
        (None, "4010", (), _d("-11000.00"), _d("-11000.00"), _d("0.00")),
    ]
    assert found.totals[0].not_stated == reason
    assert [_role_facts(item) for item in found.items] == [
        (UR, "NOT_STATED", "1210", None, _d("11050.00"), _d("11050.00"), None),
        (UR, "DIRECT_GL_ENTRY", "1210", _d("0"), _d("40.00"), _d("40.00"), "JE-NS-9"),
    ]
    assert (found.not_stated, found.direct_entries) == (1, 1)
    # A role the ledger does not show either: the item carries 0.00, never nothing.
    silent = tb.compare(
        currency=USD,
        accounts=(),
        subledger=[],
        portions=[],
        lines=[],
        roles=[tb.RoleBalance(CA, (), None, reason)],
    )
    assert [_row(total) for total in silent.totals] == [(CA, None, (), None, None, None)]
    assert [_role_facts(item) for item in silent.items] == [
        (CA, "NOT_STATED", None, None, _d("0"), _d("0"), None)
    ]


def test_erp_billing_documents_raise_no_item() -> None:
    """R-74 (d): a ledger document without an eRev external id whose number is an invoice or
    credit memo number of the entity is ERP billing — the stored balance holds it — and raises
    no item; every other such document stays a direct entry."""
    found = tb.compare(
        currency=USD,
        accounts=("2100",),
        subledger=_held(a2100="16569.86"),
        portions=[],
        lines=_stated(a2100="-103180.14"),
        details=[
            TrialBalanceDetail("2100", USD, _d("-120000.00"), "INV-US-1001", None),
            TrialBalanceDetail("2100", USD, _d("250.00"), "JE-NS-88121", None),
            # an invoice number under another system's external id is not the ERP's own document
            TrialBalanceDetail("2100", USD, _d("-1.00"), "INV-US-1002", "erev:other:JR-1:1:1"),
            TrialBalanceDetail("2100", USD, _d("1.00"), "INV-US-9999", None),
        ],
        roles=[tb.RoleBalance(CL, ("2100",), _d("-103430.14"))],
        billing_references=["INV-US-1001", "INV-US-1002", "CM-US-0001"],
    )
    assert found.erp_billing_documents == 1
    assert [_role_facts(item) for item in found.items] == [
        (CL, "DIRECT_GL_ENTRY", "2100", _d("0"), _d("-1.00"), _d("-1.00"), "INV-US-1002"),
        (CL, "DIRECT_GL_ENTRY", "2100", _d("0"), _d("1.00"), _d("1.00"), "INV-US-9999"),
        (CL, "DIRECT_GL_ENTRY", "2100", _d("0"), _d("250.00"), _d("250.00"), "JE-NS-88121"),
    ]
    assert all(item.is_high_risk for item in found.items)
    assert [_row(total)[3:] for total in found.totals] == [
        (_d("-103430.14"), _d("-103180.14"), _d("250.00"))
    ]


def test_role_rows_are_placed_by_their_first_account() -> None:
    found = tb.compare(
        currency=USD,
        accounts=("4010",),
        subledger=_held(a4010="-10.00"),
        portions=[],
        lines=_stated(a1200="2.00", a1210="3.00", a2100="-5.00", a4010="-10.00"),
        roles=[
            tb.RoleBalance(CL, ("2100",), _d("-5.00")),
            tb.RoleBalance(CA, ("1200",), _d("2.00")),
            tb.RoleBalance(UR, (), _d("3.00")),  # a balance on no account: last, by role
        ],
    )
    assert [(total.account_role, total.account_code) for total in found.totals] == [
        (CA, "1200"),
        (CL, "2100"),
        (None, "4010"),
        (UR, None),
    ]
    # 1210 belongs to no row: it is not compared; the role without an account differs by itself
    assert found.ignored_lines == 1
    assert [_role_facts(item) for item in found.items] == [
        (UR, "OTHER", None, None, None, _d("-3.00"), None)
    ]


def test_a_role_neither_side_holds_anything_for_has_no_row() -> None:
    """As an account neither side states has no row: a stated balance of zero, no ledger line and
    no item. A ledger line, an item or a role that is not stated keeps the row."""
    silent = tb.compare(
        currency=USD,
        accounts=("4010",),
        subledger=_held(a4010="-10.00"),
        portions=[],
        lines=_stated(a4010="-10.00"),
        roles=[tb.RoleBalance(UR, ("1210",), _d("0")), tb.RoleBalance(CL, ("2100",), _d("0"))],
    )
    assert [(total.account_role, total.account_code) for total in silent.totals] == [(None, "4010")]
    stated = tb.compare(
        currency=USD,
        accounts=(),
        subledger=[],
        portions=[],
        lines=_stated(a2100="0.00"),
        details=[TrialBalanceDetail("1210", USD, _d("5.00"), "JE-NS-7", None)],
        roles=[tb.RoleBalance(UR, ("1210",), _d("0")), tb.RoleBalance(CL, ("2100",), _d("0"))],
    )
    assert [_row(total) for total in stated.totals] == [
        # the document on 1210 is an item of the role: its row stays, and what the document put
        # there and the balance does not show is the residual
        (UR, "1210", ("1210",), _d("0"), None, _d("0")),
        (CL, "2100", ("2100",), _d("0"), _d("0.00"), _d("0.00")),
    ]
    assert [_role_facts(item) for item in stated.items] == [
        (UR, "DIRECT_GL_ENTRY", "1210", _d("0"), _d("5.00"), _d("5.00"), "JE-NS-7"),
        (UR, "OTHER", "1210", None, None, _d("-5.00"), None),
    ]


def test_an_account_belongs_to_one_role_row() -> None:
    with pytest.raises(ValueError, match="1200 belongs to two role rows"):
        tb.compare(
            currency=USD,
            accounts=(),
            subledger=[],
            portions=[],
            lines=[],
            roles=[tb.RoleBalance(CA, ("1200",), _d("0")), tb.RoleBalance(UR, ("1200",), _d("0"))],
        )
    with pytest.raises(ValueError, match="an amount or why"):
        tb.RoleBalance(CA, ("1200",), None)
    with pytest.raises(ValueError, match="an amount or why"):
        tb.RoleBalance(CA, ("1200",), _d("1.00"), tb.NotStated("why"))


# --- the uploaded file ----------------------------------------------------------------------------


def _sheet(
    headers: tuple[object, ...],
    *rows: tuple[object, ...],
    formulas: frozenset[tuple[int, int]] = frozenset(),
) -> SheetRows:
    numbered = tuple((index, row) for index, row in enumerate(rows, start=2))
    return SheetRows(sheet_name="CSV", headers=headers, rows=numbered, formula_cells=formulas)


def test_sheet_lines_in_file_order() -> None:
    sheet = _sheet(
        ("Amount", " account ", "CURRENCY", None),
        ("-29694.11", "2100", "USD"),
        (None, None, None),
        ("3000", "1200", "usd"),
        (-90055.89, 4000, "USD"),  # a workbook's numeric cells
        ("0.500", "1300", "USD"),
    )
    assert tb.lines_of_sheet(sheet, functional_currency="USD") == (
        TrialBalanceLine("2100", "USD", _d("-29694.11")),
        TrialBalanceLine("1200", "USD", _d("3000")),
        TrialBalanceLine("4000", "USD", _d("-90055.89")),
        TrialBalanceLine("1300", "USD", _d("0.500")),
    )


@pytest.mark.parametrize(
    "headers",
    [
        ("account", "currency"),
        ("account", "currency", "amount", "name"),
        ("account", "currency", "balance"),
        ("account", "account", "amount"),
        (),
    ],
)
def test_sheet_header_is_exact(headers: tuple[object, ...]) -> None:
    with pytest.raises(tb.SheetError) as refused:
        tb.lines_of_sheet(_sheet(headers, ("2100", "USD", "1.00")), functional_currency="USD")
    assert refused.value.findings == ((1, "file_id", tb.HEADER_EXPECTED),)


def test_sheet_findings_name_every_row() -> None:
    sheet = _sheet(
        tb.HEADERS,
        ("2100", "USD", "-100.00"),
        ("2100", "USD", "5.00"),  # row 3: the account again
        (None, "USD", "1.00"),  # row 4: no account
        ("1200", "EUR", "1.00"),  # row 5: not the functional currency
        ("1300", None, "1.00"),  # row 6: no currency
        ("1400", "USD", "1,000.00"),  # row 7: a thousands separator
        ("1500", "USD", "(100.00)"),  # row 8: brackets
        ("1600", "USD", "1.005"),  # row 9: a third decimal place
        ("1700", "USD", None),  # row 10: no amount
        ("1800", "USD", "1e3"),  # row 11: an exponent
        ("1900", "USD", None),  # row 12: a formula without a stored value
        formulas=frozenset({(12, 2)}),
    )
    with pytest.raises(tb.SheetError) as refused:
        tb.lines_of_sheet(sheet, functional_currency="USD")
    assert refused.value.findings == (
        (3, "account", tb.ACCOUNT_REPEATED.format(account="2100")),
        (4, "account", tb.ACCOUNT_REQUIRED),
        (5, "currency", tb.CURRENCY_FUNCTIONAL.format(functional="USD", currency="EUR")),
        (6, "currency", tb.CURRENCY_REQUIRED.format(functional="USD")),
        (7, "amount", tb.AMOUNT_INVALID),
        (8, "amount", tb.AMOUNT_INVALID),
        (9, "amount", tb.AMOUNT_PLACES.format(currency="USD", places=2)),
        (10, "amount", tb.AMOUNT_INVALID),
        (11, "amount", tb.AMOUNT_INVALID),
        (12, "amount", tb.FORMULA_CELL),
    )
    assert str(refused.value) == "10 trial balance finding(s)"


def test_sheet_without_rows_and_minor_units() -> None:
    with pytest.raises(tb.SheetError) as empty:
        tb.lines_of_sheet(_sheet(tb.HEADERS, (None, None, None)), functional_currency="USD")
    assert empty.value.findings == ((None, "file_id", tb.NO_ROWS),)
    # JPY has no minor unit: a decimal place is one too many, trailing zeros are none.
    yen = _sheet(tb.HEADERS, ("2100", "JPY", "-1500.0"), ("4000", "JPY", "1500.5"))
    with pytest.raises(tb.SheetError) as refused:
        tb.lines_of_sheet(yen, functional_currency="JPY")
    assert refused.value.findings == (
        (3, "amount", tb.AMOUNT_PLACES.format(currency="JPY", places=0)),
    )
