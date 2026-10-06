"""RPT-33 to RPT-35 builders — CPU witnesses (BUILD_SPEC RPS-12; SCREENS_B §5.6.6). The
specification grids are parsed from SCREENS_B, so a specification edit or a builder column drift
fails here; the row shaping, the driver rule and the tie-outs are proven on pure inputs. The
acceptance over worlds built through the product's commands is
``tests/domain/reports/test_analysis_reports.py`` (database). RPT-32 and RPT-36 have their own CPU
modules; RPT-36 ``balance_aging`` stays unregistered until its source exists.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.domain.reports import framework, tie_outs
from erev_api.domain.reports.builders import adoption_bridge as adoption
from erev_api.domain.reports.builders import balance_aging as aging
from erev_api.domain.reports.builders import book_bridge as bridge
from erev_api.domain.reports.builders import contract_cost_rollforward as costs
from erev_api.domain.reports.builders import intercompany_pairs as pairs
from erev_api.domain.reports.builders.contract_balance_rollforward import FUNCTIONAL_ONLY
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE
from erev_api.domain.reports.tie_outs import PeriodRef
from erev_api.problems import Problem
from support import report_specs

D = Decimal
MODULES = ((33, bridge), (34, adoption), (35, pairs))


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def gbp(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "GBP"}


def keyed(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    found = {str(row["row_key"]): row for row in rows}
    assert len(found) == len(rows)  # a row key occurs once
    return found


def refusal(error: pytest.ExceptionInfo[Problem]) -> tuple[str, str]:
    (item,) = error.value.errors
    return str(item.field), str(item.message)


# --- specification and registration ---------------------------------------------------------------


@pytest.mark.parametrize(("number", "module"), MODULES)
def test_columns_are_the_specification_grid(number: int, module: Any) -> None:
    """SCREENS_B §5.6.6 rev 1.25: the builder's columns are the dataset grid's fields in its
    order, under the grid's headers (the ``(<ISO>)`` of a money header is presentation)."""
    keys = [column.key for column in module.COLUMNS]
    assert keys == report_specs.fields(number, module.CODE)
    assert len(set(keys)) == len(keys) and "row_key" not in keys
    headers = {column.key: column.header for column in module.COLUMNS}
    for header, names in report_specs.grid(number, module.CODE):
        assert len(names) == 1
        assert headers[names[0]] == header.replace(" (<ISO>)", ""), names


@pytest.mark.parametrize(("number", "module"), MODULES)
def test_registration_and_catalogue(number: int, module: Any) -> None:
    assert framework.BUILDERS[module.CODE] is module.build
    contract = framework.SOURCE_CONTRACTS[module.CODE]
    assert contract.strategy == "open" and len(contract.open) == 1
    assert f"RPT-{number}" in contract.open[0]
    definition = DEFINITIONS_BY_CODE[module.CODE]
    section = report_specs.section(number, module.CODE)
    assert f"| Kind, formats | `{definition.kind}`;" in section


def test_tie_out_literals_and_defaults() -> None:
    """BUILD_SPEC RPS-12: the four tie-out codes live in ``tie_outs`` and are the catalogue's;
    the two currency-view defaults are SCREENS_B's."""
    assert DEFINITIONS_BY_CODE[bridge.CODE].tie_outs == (tie_outs.TO_BRIDGE_DRIVERS_EQ_DIFFERENCE,)
    assert DEFINITIONS_BY_CODE[pairs.CODE].tie_outs == (tie_outs.TO_IC_UNMATCHED_ZERO,)
    assert DEFINITIONS_BY_CODE[adoption.CODE].tie_outs == ()  # SCREENS_B RPT-34 "Tie-out: none"
    assert DEFINITIONS_BY_CODE[costs.CODE].tie_outs == (tie_outs.TO_COST_ROLLFORWARD_BALANCES,)
    assert DEFINITIONS_BY_CODE[aging.CODE].tie_outs == (tie_outs.TO_AGING_EQ_BALANCES,)
    assert costs.TO_COST_ROLLFORWARD_BALANCES is tie_outs.TO_COST_ROLLFORWARD_BALANCES
    assert aging.TO_AGING_EQ_BALANCES is tie_outs.TO_AGING_EQ_BALANCES
    assert bridge.TO_BRIDGE_DRIVERS_EQ_DIFFERENCE is tie_outs.TO_BRIDGE_DRIVERS_EQ_DIFFERENCE
    assert pairs.TO_IC_UNMATCHED_ZERO is tie_outs.TO_IC_UNMATCHED_ZERO
    assert framework.PARAMETER_DEFAULTS[bridge.CODE] == {"currency_view": "functional"}
    assert framework.PARAMETER_DEFAULTS[pairs.CODE] == {"currency_view": "transaction"}
    assert adoption.CODE not in framework.PARAMETER_DEFAULTS  # "Currency view: no"
    assert "| Currency view | yes; default `functional` |" in report_specs.section(33, bridge.CODE)
    assert "| Currency view | yes; default `transaction` |" in report_specs.section(35, pairs.CODE)
    assert "| Currency view | no |" in report_specs.section(34, adoption.CODE)
    # RPT-36 stays out of the framework until its source exists (ruling Q-2; CLO-19, CTR-14)
    assert aging.CODE not in framework.BUILDERS


def test_specification_literals() -> None:
    """The codes, labels, row keys and copy the builders print are the specification's."""
    section = report_specs.section(33, bridge.CODE)
    for code, label in {**bridge.MEASURE_LABELS, **bridge.DRIVER_LABELS}.items():
        assert f'`{code}` "{label}"' in section, code
    assert tuple(bridge.MEASURE_LABELS) == bridge.MEASURES
    assert tuple(bridge.DRIVER_LABELS) == bridge.DRIVERS
    for key in (
        "measure:<MEASURE>",
        "driver:<DRIVER>:<MEASURE>",
        "contract:<external id>:<MEASURE>",
    ):
        assert f"`{key}`" in section, key
    assert f'"{bridge.ENTITY_REQUIRED}"' in section
    section = report_specs.section(34, adoption.CODE)
    for label in adoption.LINE_LABELS.values():
        assert f'"{label}"' in section, label
    assert tuple(adoption.LINE_LABELS) == adoption.LINES
    for code in adoption.LINES:
        assert f"`{code}`" in section, code
    for copy in (adoption.ENTITY_REQUIRED, adoption.DATE_TOO_EARLY, adoption.DATE_NOT_PERIOD_START):
        assert f'"{copy}"' in section, copy
    assert "`contract:<external id>`" in section and "`line:<LINE>`" in section
    section = report_specs.section(35, pairs.CODE)
    assert "`pair:<due from entity>:<due to entity>:<currency>`" in section
    assert "`contract:<external id>:<obligation key>:<period key>`" in section
    assert f"`{pairs.DUE_FROM}`" in section and f"`{pairs.DUE_TO}`" in section


# --- RPT-35 -----------------------------------------------------------------------------------


def _line(
    entity: str,
    counterparty: str,
    role: str,
    amount: str,
    *,
    currency: str = "GBP",
    functional: str | None = None,
    contract: str = "SF-ORD-UK-2001",
    obligation: str | None = "O1",
    period: str = "FY2026-P09",
) -> pairs.Line:
    return pairs.Line(
        entity_code=entity,
        counterparty_code=counterparty,
        account_role=role,
        currency=currency,
        amount=D(amount),
        functional_currency=functional or currency,
        contract_external_id=contract,
        obligation_key=obligation,
        period_key=period,
    )


def _k04(period: str = "FY2026-P09", amount: str = "4790.61") -> list[pairs.Line]:
    """The JET-13 pair of WLD-X-14: AVM-UK credits the due-to role, AVM-US debits the due-from
    role, in GBP."""
    return [
        _line("AVM-UK", "AVM-US", pairs.DUE_TO, f"-{amount}", period=period),
        _line("AVM-US", "AVM-UK", pairs.DUE_FROM, amount, functional="USD", period=period),
    ]


def test_intercompany_pair_of_wld_x_14() -> None:
    """One pair row and one contract row; due from = due to = 4,790.61 GBP, unmatched 0.00;
    ``TO_IC_UNMATCHED_ZERO`` passes."""
    rows, totals, tie = pairs.dataset_rows(_k04(), run_entities={"AVM-US", "AVM-UK"})
    found = keyed(rows)
    assert list(found) == ["pair:AVM-US:AVM-UK:GBP", "contract:SF-ORD-UK-2001:O1:FY2026-P09"]
    pair = found["pair:AVM-US:AVM-UK:GBP"]
    assert (pair["section"], pair["due_from_entity_code"], pair["due_to_entity_code"]) == (
        1,
        "AVM-US",
        "AVM-UK",
    )
    assert (pair["due_from_amount"], pair["due_to_amount"], pair["unmatched_amount"]) == (
        gbp("4790.61"),
        gbp("4790.61"),
        gbp("0.00"),
    )
    detail = found["contract:SF-ORD-UK-2001:O1:FY2026-P09"]
    assert (
        detail["section"],
        detail["contracting_entity_code"],
        detail["performing_entity_code"],
        detail["period_key"],
        detail["pair_amount"],
        detail["unmatched_amount"],
    ) == (2, "AVM-UK", "AVM-US", "FY2026-P09", gbp("4790.61"), gbp("0.00"))
    assert (tie["code"], tie["result"]) == ("TO_IC_UNMATCHED_ZERO", "PASS")
    assert tie["expected"] == tie["actual"] == [gbp("4790.61")]
    assert totals == {
        "pair_count": 1,
        "incomplete_pair_count": 0,
        "due_from_total": {"GBP": "4790.61"},
        "due_to_total": {"GBP": "4790.61"},
        "unmatched_total": {"GBP": "0.00"},
    }
    assert pairs.pair_of(_k04()[0]) == pairs.pair_of(_k04()[1]) == ("AVM-US", "AVM-UK", "GBP")


def test_intercompany_breaks_do_not_offset() -> None:
    """A pair whose sides differ fails the tie-out, and two pairs that break by opposite amounts
    are two breaks: the totals agree, the result is ``FAIL``."""
    short = [
        _line("AVM-UK", "AVM-US", pairs.DUE_TO, "-100.00"),
        _line("AVM-US", "AVM-UK", pairs.DUE_FROM, "90.00", functional="USD"),
    ]
    rows, totals, tie = pairs.dataset_rows(short, run_entities={"AVM-US", "AVM-UK"})
    assert keyed(rows)["pair:AVM-US:AVM-UK:GBP"]["unmatched_amount"] == gbp("-10.00")
    assert keyed(rows)["contract:SF-ORD-UK-2001:O1:FY2026-P09"]["unmatched_amount"] == gbp("-10.00")
    assert tie["result"] == "FAIL" and totals["unmatched_total"] == {"GBP": "-10.00"}
    opposite = [
        *short,
        _line("AVM-DE", "AVM-US", pairs.DUE_TO, "-90.00", contract="NS-SO-DE-1"),
        _line(
            "AVM-US", "AVM-DE", pairs.DUE_FROM, "100.00", functional="USD", contract="NS-SO-DE-1"
        ),
    ]
    rows, totals, tie = pairs.dataset_rows(opposite, run_entities={"AVM-US", "AVM-UK", "AVM-DE"})
    assert totals["unmatched_total"] == {"GBP": "0.00"} and totals["pair_count"] == 2
    assert tie["expected"] == tie["actual"] == [gbp("190.00")]
    assert tie["result"] == "FAIL"


def test_intercompany_side_outside_the_run_is_empty() -> None:
    """A run for the contracting entity alone reads its due-to lines only: the due-from cell and
    the unmatched cell are empty (not 0.00), the pair amount is the side that was read, and the
    tie-out is ``NOT_APPLICABLE``."""
    rows, totals, tie = pairs.dataset_rows(_k04()[:1], run_entities={"AVM-UK"})
    pair = keyed(rows)["pair:AVM-US:AVM-UK:GBP"]
    assert (pair["due_from_amount"], pair["due_to_amount"], pair["unmatched_amount"]) == (
        None,
        gbp("4790.61"),
        None,
    )
    detail = keyed(rows)["contract:SF-ORD-UK-2001:O1:FY2026-P09"]
    assert (detail["pair_amount"], detail["unmatched_amount"]) == (gbp("4790.61"), None)
    assert tie == {
        "code": "TO_IC_UNMATCHED_ZERO",
        "result": "NOT_APPLICABLE",
        "expected": None,
        "actual": None,
    }
    assert totals["incomplete_pair_count"] == 1
    assert totals["due_from_total"] == {} and totals["unmatched_total"] == {}
    # the performing entity alone: the pair amount is its own side
    rows, _, _ = pairs.dataset_rows(_k04()[1:], run_entities={"AVM-US"})
    detail = keyed(rows)["contract:SF-ORD-UK-2001:O1:FY2026-P09"]
    assert detail["pair_amount"] == gbp("4790.61")
    # an entity of the run without a line on its side carries 0.00, and the pair breaks
    rows, _, tie = pairs.dataset_rows(_k04()[:1], run_entities={"AVM-US", "AVM-UK"})
    pair = keyed(rows)["pair:AVM-US:AVM-UK:GBP"]
    assert (pair["due_from_amount"], pair["unmatched_amount"]) == (gbp("0.00"), gbp("-4790.61"))
    assert tie["result"] == "FAIL"


def test_intercompany_periods_rows_and_view() -> None:
    """Section 2 has one row per contract, obligation and period in key order; an empty run has
    no pair and no tie to test; the functional view is refused when a line is not in its entity's
    functional currency."""
    lines = [*_k04("FY2026-P09", "4790.61"), *_k04("FY2026-P08", "4950.29")]
    rows, totals, tie = pairs.dataset_rows(lines, run_entities={"AVM-US", "AVM-UK"})
    assert [row["row_key"] for row in rows] == [
        "pair:AVM-US:AVM-UK:GBP",
        "contract:SF-ORD-UK-2001:O1:FY2026-P08",
        "contract:SF-ORD-UK-2001:O1:FY2026-P09",
    ]
    assert rows[0]["due_from_amount"] == gbp("9740.90") and tie["result"] == "PASS"
    assert pairs.dataset_rows([], run_entities={"AVM-US"}) == (
        [],
        {
            "pair_count": 0,
            "incomplete_pair_count": 0,
            "due_from_total": {},
            "due_to_total": {},
            "unmatched_total": {},
        },
        tie_outs.not_applicable("TO_IC_UNMATCHED_ZERO"),
    )
    pairs.check_view("transaction", lines)
    pairs.check_view("functional", lines[:1])  # AVM-UK carries GBP, its functional currency
    with pytest.raises(Problem) as refused:
        pairs.check_view("functional", lines)  # AVM-US carries GBP; its functional is USD
    assert refusal(refused) == ("parameters.currency_view", pairs.FUNCTIONAL_ONLY)


# --- RPT-34 -----------------------------------------------------------------------------------


def _period(year: int, month: int) -> PeriodRef:
    start = date(year, month, 1)
    following = date(year + month // 12, month % 12 + 1, 1)
    return PeriodRef(
        id=UUID(int=year * 100 + month),
        key=f"FY{year}-P{month:02d}",
        name=start.strftime("%b %Y"),
        fiscal_year=year,
        period_no=month,
        quarter_no=(month - 1) // 3 + 1,
        start=start,
        end=date.fromordinal(following.toordinal() - 1),
    )


PERIODS = tuple(_period(year, month) for year in (2025, 2026) for month in range(1, 13))


def test_application_date_is_the_first_day_of_a_period() -> None:
    first = PERIODS[0]
    # the default: the first day of the first ASC 606 period; nothing lies before it
    assert adoption.application_date(None, first_asc606=first, periods=PERIODS) == (
        date(2025, 1, 1),
        None,
    )
    day, before = adoption.application_date("2026-01-01", first_asc606=first, periods=PERIODS)
    assert (day, before.key if before else None) == (date(2026, 1, 1), "FY2025-P12")
    assert before is not None and before.end == date(2025, 12, 31)
    with pytest.raises(Problem) as inside:
        adoption.application_date("2026-01-15", first_asc606=first, periods=PERIODS)
    assert refusal(inside) == (
        "parameters.date_of_initial_application",
        adoption.DATE_NOT_PERIOD_START,
    )
    with pytest.raises(Problem) as early:
        adoption.application_date("2025-06-01", first_asc606=PERIODS[11], periods=PERIODS)
    assert refusal(early) == ("parameters.date_of_initial_application", adoption.DATE_TOO_EARLY)


def test_legacy_position_and_measure_at() -> None:
    """Billed less legacy revenue is deferred revenue when positive and an unbilled receivable
    when negative; a trace measure holds its last value at or before the period."""
    assert adoption.legacy_position(D("300000.00"), D("100000.00")) == (D("200000.00"), D(0))
    assert adoption.legacy_position(D("1000.00"), D("1500.00")) == (D(0), D("500.00"))
    assert adoption.legacy_position(D("0"), D("0")) == (D(0), D(0))
    nodes = {
        ("revenue_cum", "C-ADOPT/L2-PCS"): [
            ("FY2025-P11", D("36666.67")),
            ("FY2025-P12", D("40000.00")),
            ("FY2026-P01", D("43333.33")),
        ]
    }
    at = adoption.measure_at
    assert at(nodes, "revenue_cum", "C-ADOPT/L2-PCS", "FY2025-P12") == D("40000.00")
    assert at(nodes, "revenue_cum", "C-ADOPT/L2-PCS", "FY2026-P09") == D("43333.33")  # last node
    assert at(nodes, "revenue_cum", "C-ADOPT/L2-PCS", "FY2025-P10") == D(0)  # before the first
    assert at(nodes, "billed_cum", "C-ADOPT/L2-PCS", "FY2025-P12") == D(0)  # no such measure


def test_adoption_bridge_of_onb_s11_modretro_own() -> None:
    """``C-ADOPT`` at 31 Dec 2025: legacy GAAP revenue 100,000.00 against 220,000.00 under Topic
    606; cumulative effect 120,000.00; contract liability 200,000.00 against 80,000.00; the
    legacy cost-asset cells are empty."""
    found = adoption.Source(
        contract_external_id="C-ADOPT",
        customer_name="Example Customer (Demo)",
        currency="USD",
        revenue_legacy=D("100000.00"),
        revenue_asc606=D("220000.00"),
        billed=D("300000.00"),
        contract_liability=D("80000.00"),
    )
    rows, totals = adoption.dataset_rows([found])
    by_key = keyed(rows)
    assert list(by_key) == ["contract:C-ADOPT"] + [f"line:{code}" for code in adoption.LINES]
    contract_row = by_key["contract:C-ADOPT"]
    assert (
        contract_row["revenue_legacy"],
        contract_row["revenue_asc606"],
        contract_row["cumulative_effect"],
        contract_row["contract_liability_legacy"],
        contract_row["contract_liability_asc606"],
        contract_row["asset_asc606"],
    ) == (
        usd("100000.00"),
        usd("220000.00"),
        usd("120000.00"),
        usd("200000.00"),
        usd("80000.00"),
        usd("0.00"),
    )
    assert {
        code: (row["legacy_amount"], row["asc606_amount"], row["effect"])
        for code, row in ((code, by_key[f"line:{code}"]) for code in adoption.LINES)
    } == {
        "REVENUE": (usd("100000.00"), usd("220000.00"), usd("120000.00")),
        "CONTRACT_LIABILITY": (usd("200000.00"), usd("80000.00"), usd("-120000.00")),
        "CONTRACT_ASSET": (usd("0.00"), usd("0.00"), usd("0.00")),
        "UNBILLED_RECEIVABLE": (usd("0.00"), usd("0.00"), usd("0.00")),
        "COST_ASSETS": (None, usd("0.00"), None),
    }
    assert totals == {
        "contract_count": 1,
        "revenue_legacy_total": {"USD": "100000.00"},
        "revenue_asc606_total": {"USD": "220000.00"},
        "cumulative_effect_total": {"USD": "120000.00"},
        "legacy_only_contract_count": 0,
        "legacy_only_revenue": {},
    }


def test_adoption_bridge_currencies_and_contracts_outside() -> None:
    """Legacy revenue ahead of billing is a legacy unbilled receivable; the Topic 606 cost asset
    stands against an empty legacy cell; two currencies give two line sets; a contract without a
    figure is not listed; a contract the LEGACY book holds without an ASC 606 version in the
    disclosures is counted in the control totals, not listed."""
    ahead = adoption.Source(
        contract_external_id="C-AHEAD",
        customer_name=None,
        currency="USD",
        revenue_legacy=D("1500.00"),
        revenue_asc606=D("1200.00"),
        billed=D("1000.00"),
        contract_asset=D("150.00"),
        unbilled_receivable=D("50.00"),
        cost_assets=D("75.00"),
    )
    euro = adoption.Source(
        contract_external_id="C-EUR",
        customer_name="Hollenbrand Maschinenbau GmbH (Demo)",
        currency="EUR",
        revenue_asc606=D("10.00"),
        billed=D("10.00"),
    )
    silent = adoption.Source(contract_external_id="C-NONE", customer_name=None, currency="USD")
    outside = adoption.Source(
        contract_external_id="C-DRAFT", customer_name=None, currency="USD", revenue_legacy=D("40")
    )
    rows, totals = adoption.dataset_rows([euro, silent, ahead], [outside])
    by_key = keyed(rows)
    assert [key for key in by_key if key.startswith("contract:")] == [
        "contract:C-AHEAD",
        "contract:C-EUR",
    ]
    row = by_key["contract:C-AHEAD"]
    assert (row["cumulative_effect"], row["contract_liability_legacy"], row["asset_asc606"]) == (
        usd("-300.00"),
        usd("0.00"),
        usd("200.00"),
    )
    line = by_key["line:UNBILLED_RECEIVABLE:USD"]
    assert (line["legacy_amount"], line["asc606_amount"], line["effect"]) == (
        usd("500.00"),
        usd("50.00"),
        usd("-450.00"),
    )
    assets = by_key["line:CONTRACT_ASSET:USD"]
    assert (assets["legacy_amount"], assets["effect"]) == (usd("0.00"), usd("150.00"))
    costs_line = by_key["line:COST_ASSETS:USD"]
    assert (costs_line["legacy_amount"], costs_line["asc606_amount"], costs_line["effect"]) == (
        None,
        usd("75.00"),
        None,
    )
    assert by_key["line:REVENUE:EUR"]["asc606_amount"] == {"amount": "10.00", "currency": "EUR"}
    assert totals["contract_count"] == 2
    assert totals["cumulative_effect_total"] == {"EUR": "10.00", "USD": "-300.00"}
    assert (totals["legacy_only_contract_count"], totals["legacy_only_revenue"]) == (
        1,
        {"USD": "40.00"},
    )
    assert adoption.dataset_rows([]) == (
        [],
        {
            "contract_count": 0,
            "revenue_legacy_total": {},
            "revenue_asc606_total": {},
            "cumulative_effect_total": {},
            "legacy_only_contract_count": 0,
            "legacy_only_revenue": {},
        },
    )


# --- RPT-33 -----------------------------------------------------------------------------------


def _compared(
    external_id: str,
    asc606: dict[str, str] | None = None,
    ifrs15: dict[str, str] | None = None,
    *,
    currency: str = "USD",
    **facts: bool,
) -> bridge.Compared:
    return bridge.Compared(
        contract_external_id=external_id,
        currency=currency,
        asc606={measure: D(amount) for measure, amount in (asc606 or {}).items()},
        ifrs15={measure: D(amount) for measure, amount in (ifrs15 or {}).items()},
        **facts,
    )


def _drivers(rows: list[dict[str, Any]], measure: str) -> dict[str, tuple[Any, Any]]:
    return {
        str(row["driver_code"]): (row["effect"], row["contracts_affected"])
        for row in rows
        if row["section"] == 2 and row["measure_code"] == measure
    }


def test_driver_rule_order() -> None:
    """Step 1 in exactly one book carries every measure; then the loss provision is the onerous
    contract regime, the cost assets the impairment reversal when the IFRS 15 book posted one;
    everything else is ``OTHER``."""
    one_book = _compared("C-1", step1_differs=True, impairment_reversed=True)
    for measure in bridge.MEASURES:
        assert bridge.driver_of(one_book, measure) == "COLLECTIBILITY"
    plain = _compared("C-4")
    assert bridge.driver_of(plain, "REVENUE") == "OTHER"
    assert bridge.driver_of(plain, "LOSS_PROVISION") == "ONEROUS_CONTRACTS"
    assert bridge.driver_of(plain, "COST_ASSETS") == "OTHER"
    reversed_asset = _compared("C-5", impairment_reversed=True)
    assert bridge.driver_of(reversed_asset, "COST_ASSETS") == "COST_IMPAIRMENT_REVERSAL"
    assert bridge.driver_of(reversed_asset, "REVENUE") == "OTHER"
    assert bridge.driver_of(reversed_asset, "LOSS_PROVISION") == "ONEROUS_CONTRACTS"


def test_step1_differs_over_the_versions_of_both_books() -> None:
    """Rule 1: a computation that left exactly one book holding the contract as not a contract,
    or both books holding it so at their latest version (606-10-25-7 event (c), POL-012); equal
    Step 1 histories, and a computation that wrote one book only, are not a difference."""
    differs = bridge.step1_differs
    # IFRS-SW01: the first two computations keep both books as drafts; the third splits them
    sw01 = [
        ("c1", "ASC606", 1, "DRAFT"),
        ("c1", "IFRS15", 1, "DRAFT"),
        ("c2", "ASC606", 2, "DRAFT"),
        ("c2", "IFRS15", 2, "DRAFT"),
        ("c3", "ASC606", 3, "NOT_A_CONTRACT"),
        ("c3", "IFRS15", 3, "ACTIVE"),
    ]
    assert differs(sw01) is True
    # the criteria are met later in ASC 606: the books agree again, the history still differed
    assert differs([*sw01, ("c4", "ASC606", 4, "ACTIVE"), ("c4", "IFRS15", 4, "ACTIVE")]) is True
    same = [
        ("c1", "ASC606", 1, "NOT_A_CONTRACT"),
        ("c1", "IFRS15", 1, "NOT_A_CONTRACT"),
        ("c2", "ASC606", 2, "ACTIVE"),
        ("c2", "IFRS15", 2, "ACTIVE"),
    ]
    assert differs(same) is False  # failed and met Step 1 together: no switch acted
    assert differs(same[:2]) is True  # neither book holds a contract: only 25-7 can differ
    assert differs([("c1", "ASC606", 1, "ACTIVE"), ("c1", "IFRS15", 1, "ACTIVE")]) is False
    # IFRS 15 kept from the second computation on: the first compares nothing
    later = [
        ("c1", "ASC606", 1, "NOT_A_CONTRACT"),
        ("c2", "ASC606", 2, "ACTIVE"),
        ("c2", "IFRS15", 1, "ACTIVE"),
    ]
    assert differs(later) is False
    assert differs([("c1", "ASC606", 1, "NOT_A_CONTRACT")]) is False  # one book: no bridge
    assert differs([]) is False


def test_book_bridge_of_ifrs_sw01() -> None:
    """``C-IFRS-SW01`` January to March 2026: revenue 0.00 in ASC 606 and 3,000.00 in IFRS 15;
    ``COLLECTIBILITY`` carries (3,000.00), every other driver 0.00; the tie-out passes."""
    found = _compared("C-IFRS-SW01", ifrs15={"REVENUE": "3000.00"}, step1_differs=True)
    rows, totals, tie = bridge.dataset_rows([found])
    by_key = keyed(rows)
    assert list(by_key) == [
        *(f"measure:{measure}" for measure in bridge.MEASURES),
        *(f"driver:{driver}:REVENUE" for driver in bridge.DRIVERS),
        "contract:C-IFRS-SW01:REVENUE",
    ]
    revenue = by_key["measure:REVENUE"]
    assert (revenue["asc606_amount"], revenue["ifrs15_amount"], revenue["difference"]) == (
        usd("0.00"),
        usd("3000.00"),
        usd("-3000.00"),
    )
    assert by_key["measure:LOSS_PROVISION"]["difference"] == usd("0.00")
    assert _drivers(rows, "REVENUE") == {
        "COLLECTIBILITY": (usd("-3000.00"), 1),
        "COST_IMPAIRMENT_REVERSAL": (usd("0.00"), 0),
        "FRAMEWORK_ELECTIONS": (usd("0.00"), 0),
        "LICENCE_RENEWALS": (usd("0.00"), 0),
        "ONEROUS_CONTRACTS": (usd("0.00"), 0),
        "ADVANCE_CONSIDERATION_FX": (usd("0.00"), 0),
        "OTHER": (usd("0.00"), 0),
    }
    contract_row = by_key["contract:C-IFRS-SW01:REVENUE"]
    assert (contract_row["section"], contract_row["driver_code"], contract_row["driver_label"]) == (
        3,
        "COLLECTIBILITY",
        "Collectibility",
    )
    assert (tie["code"], tie["result"]) == ("TO_BRIDGE_DRIVERS_EQ_DIFFERENCE", "PASS")
    assert tie["expected"] == tie["actual"] == [usd("-3000.00")]
    assert totals == {
        "contract_count": 1,
        "revenue_asc606": {"USD": "0.00"},
        "revenue_ifrs15": {"USD": "3000.00"},
        "revenue_difference": {"USD": "-3000.00"},
        "other_effect": {"USD": "0.00"},
    }


def test_book_bridge_unidentified_drivers_are_empty_when_other_holds_a_difference() -> None:
    """A loss provision in IFRS 15 alone is the onerous-contract regime; a reversed cost asset is
    the impairment reversal; a revenue difference no stored fact identifies is ``OTHER`` — then
    the two drivers the platform cannot identify show an empty cell for that measure, never 0.00,
    while the identified drivers keep their amounts. Section 2 lists a measure only when a
    contract differs in it; equal contracts are in section 1 only."""
    onerous = _compared("C-LOSS", ifrs15={"LOSS_PROVISION": "500.00"})
    reversal = _compared(
        "C-COST",
        asc606={"COST_ASSETS": "10000.00", "REVENUE": "100.00"},
        ifrs15={"COST_ASSETS": "20000.00", "REVENUE": "100.00"},
        impairment_reversed=True,
    )
    timing = _compared("C-LIC", asc606={"REVENUE": "0.00"}, ifrs15={"REVENUE": "250.00"})
    failed = _compared("C-STEP1", ifrs15={"REVENUE": "40.00"}, step1_differs=True)
    rows, totals, tie = bridge.dataset_rows([timing, onerous, failed, reversal])
    by_key = keyed(rows)
    assert _drivers(rows, "LOSS_PROVISION") == {
        "COLLECTIBILITY": (usd("0.00"), 0),
        "COST_IMPAIRMENT_REVERSAL": (usd("0.00"), 0),
        "FRAMEWORK_ELECTIONS": (usd("0.00"), 0),
        "LICENCE_RENEWALS": (usd("0.00"), 0),
        "ONEROUS_CONTRACTS": (usd("-500.00"), 1),
        "ADVANCE_CONSIDERATION_FX": (usd("0.00"), 0),
        "OTHER": (usd("0.00"), 0),
    }
    assert _drivers(rows, "COST_ASSETS")["COST_IMPAIRMENT_REVERSAL"] == (usd("-10000.00"), 1)
    assert _drivers(rows, "REVENUE") == {
        "COLLECTIBILITY": (usd("-40.00"), 1),
        "COST_IMPAIRMENT_REVERSAL": (usd("0.00"), 0),
        "FRAMEWORK_ELECTIONS": (None, None),  # inside OTHER: not an unsupported 0.00
        "LICENCE_RENEWALS": (None, None),
        "ONEROUS_CONTRACTS": (usd("0.00"), 0),
        "ADVANCE_CONSIDERATION_FX": (usd("0.00"), 0),
        "OTHER": (usd("-250.00"), 1),
    }
    assert [row["row_key"] for row in rows if row["section"] == 2 and row["effect"] is None] == [
        "driver:FRAMEWORK_ELECTIONS:REVENUE",
        "driver:LICENCE_RENEWALS:REVENUE",
    ]
    # no contract differs in the contract liability: section 1 only
    assert "measure:CONTRACT_LIABILITY" in by_key
    assert not any(
        key.endswith(":CONTRACT_LIABILITY") and key != "measure:CONTRACT_LIABILITY"
        for key in by_key
    )
    assert [key for key in by_key if key.startswith("contract:")] == [
        "contract:C-COST:COST_ASSETS",
        "contract:C-LIC:REVENUE",
        "contract:C-LOSS:LOSS_PROVISION",
        "contract:C-STEP1:REVENUE",
    ]
    assert by_key["contract:C-LIC:REVENUE"]["driver_code"] == "OTHER"
    assert tie["result"] == "PASS"
    assert tie["expected"] == tie["actual"] == [usd("-10790.00")]
    assert totals["other_effect"] == {"USD": "-250.00"} and totals["contract_count"] == 4


def test_book_bridge_currencies_offsets_and_view() -> None:
    """Two currencies give two row sets with ``:<ISO>`` keys; two contracts whose differences
    offset are both listed and their driver carries both; a contract without an amount is not in
    the bridge; the functional view is refused when a contract is in another currency."""
    up = _compared("C-UP", asc606={"REVENUE": "100.00"}, ifrs15={"REVENUE": "60.00"})
    down = _compared("C-DOWN", asc606={"REVENUE": "60.00"}, ifrs15={"REVENUE": "100.00"})
    pound = _compared(
        "C-GBP",
        asc606={"REVENUE": "0.00"},
        ifrs15={"REVENUE": "7.00"},
        currency="GBP",
        step1_differs=True,
    )
    nothing = _compared("C-NONE")
    rows, totals, tie = bridge.dataset_rows([up, down, pound, nothing])
    by_key = keyed(rows)
    assert by_key["measure:REVENUE:USD"]["difference"] == usd("0.00")
    assert by_key["driver:OTHER:REVENUE:USD"]["effect"] == usd("0.00")
    assert by_key["driver:OTHER:REVENUE:USD"]["contracts_affected"] == 2
    assert by_key["driver:FRAMEWORK_ELECTIONS:REVENUE:USD"]["effect"] is None
    assert by_key["driver:COLLECTIBILITY:REVENUE:GBP"]["effect"] == gbp("-7.00")
    assert by_key["driver:LICENCE_RENEWALS:REVENUE:GBP"]["effect"] == gbp("0.00")
    assert {key for key in by_key if key.startswith("contract:")} == {
        "contract:C-UP:REVENUE",
        "contract:C-DOWN:REVENUE",
        "contract:C-GBP:REVENUE",
    }
    assert totals["contract_count"] == 3 and tie["result"] == "PASS"
    assert tie["expected"] == tie["actual"] == [gbp("-7.00"), usd("0.00")]
    assert bridge.dataset_rows([nothing]) == (
        [],
        {
            "contract_count": 0,
            "revenue_asc606": {},
            "revenue_ifrs15": {},
            "revenue_difference": {},
            "other_effect": {},
        },
        {"code": "TO_BRIDGE_DRIVERS_EQ_DIFFERENCE", "result": "PASS", "expected": [], "actual": []},
    )
    bridge.check_view("transaction", [up, pound], functional_currency="USD")
    bridge.check_view("functional", [up, down], functional_currency="USD")
    with pytest.raises(Problem) as refused:
        bridge.check_view("functional", [up, pound], functional_currency="USD")
    assert refusal(refused) == ("parameters.currency_view", FUNCTIONAL_ONLY)
