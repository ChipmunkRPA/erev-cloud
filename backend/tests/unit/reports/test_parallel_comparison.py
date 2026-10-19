"""RPT-42 arithmetic and missing-source handling, independent of source adapters."""

from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext

import pytest
from erev_api.domain.reports.outputs.csv import render_csv
from erev_api.domain.reports.parallel_comparison import Balance, Journal, Period, Snapshot, compare
from erev_api.problems import Problem

P = Period("US", "ASC606", "USD", "FY2023-P01", date(2023, 1, 1), date(2023, 1, 31))
D = Decimal


def sources() -> tuple[Snapshot, Snapshot]:
    journal = tuple(
        Journal(P, code, D(debit), D(credit), ("row:" + code,))
        for code, debit, credit in (
            ("21001", "295.69", "0"),
            ("15002", "58.85", "0"),
            ("5001", "0", "187.69"),
            ("5002", "0", "118.53"),
            ("5003", "0", "48.32"),
        )
    )
    legacy = Snapshot(
        "legacy-file",
        "a" * 64,
        frozenset({P}),
        journal,
        (Balance(P, "Contract 2", D("-58.85"), ("legacy-balance",)),),
    )
    actual = Snapshot(
        "erev-evidence",
        "b" * 64,
        frozenset({P}),
        journal,
        (Balance(P, "Contract 2", D("-58.85"), ("erev-balance",), D(0), D("58.85")),),
    )
    return legacy, actual


def test_both_sections_keep_exact_signed_totals_and_contributors() -> None:
    # The amounts exercise the specified comparison; this is not command-driven LMG-5 acceptance.
    old, new = sources()
    with localcontext() as context:
        context.prec = 3
        result = compare(old, new)
    rows = {r["row_key"]: r for r in result.data.rows}
    assert rows["je:FY2023-P01:21001"]["legacy_debit"]["amount"] == "295.69"
    assert rows["balance:Contract 2:FY2023-P01"]["difference"]["amount"] == "0.00"
    assert rows["TOTAL:USD:1"]["legacy_debit"]["amount"] == "354.54"
    assert rows["TOTAL:USD:1"]["legacy_credit"]["amount"] == "354.54"
    assert result.evidence["contributors"]["balance:Contract 2:FY2023-P01"] == {
        "legacy": ["legacy-balance"],
        "erev": ["erev-balance"],
    }
    assert render_csv(result.data)


def test_cent_difference_is_itemised_without_balancing_plug() -> None:
    old, new = sources()
    changed = replace(new.journals[0], debit=D("295.70"))
    result = compare(old, replace(new, journals=(changed, *new.journals[1:])))
    rows = {r["row_key"]: r for r in result.data.rows}
    assert rows["je:FY2023-P01:21001"]["difference"]["amount"] == "0.01"
    assert rows["TOTAL:USD:1"]["erev_debit"]["amount"] == "354.55"
    assert rows["TOTAL:USD:1"]["erev_credit"]["amount"] == "354.54"


def test_unavailable_period_is_not_a_zero_counterpart() -> None:
    old, new = sources()
    absent = replace(new, periods=frozenset(), journals=(), balances=())
    assert compare(old, absent).data.rows == ()
    # A complete zero-activity source is different from an unavailable source.
    zero = replace(new, journals=(), balances=())
    rows = {r["row_key"]: r for r in compare(old, zero).data.rows}
    assert rows["je:FY2023-P01:21001"]["difference"]["amount"] == "-295.69"
    assert rows["balance:Contract 2:FY2023-P01"]["difference"]["amount"] == "58.85"


def test_currencies_and_entities_are_not_netted() -> None:
    old, new = sources()
    other = replace(P, entity_code="JP", currency="JPY")
    old = replace(
        old,
        periods=frozenset({P, other}),
        journals=(*old.journals, Journal(other, "21001", D(100), D(0), ("jp-old",))),
    )
    new = replace(
        new,
        periods=frozenset({P, other}),
        journals=(*new.journals, Journal(other, "21001", D(101), D(0), ("jp-new",))),
    )
    result = compare(old, new)
    rows = {r["row_key"]: r for r in result.data.rows}
    assert len(rows) == len(result.data.rows)
    assert rows["TOTAL:JPY:1"]["difference"] == {"amount": "1", "currency": "JPY"}
    assert rows["TOTAL:USD:1"]["difference"]["amount"] == "0.00"


@pytest.mark.parametrize("fault", ["duplicate", "precision", "coverage", "dates", "balance"])
def test_inconsistent_sources_refuse(fault: str) -> None:
    old, new = sources()
    if fault == "duplicate":
        new = replace(new, journals=(*new.journals, new.journals[0]))
    elif fault == "precision":
        new = replace(new, journals=(replace(new.journals[0], debit=D("295.691")),))
    elif fault == "coverage":
        new = replace(new, periods=frozenset())
    elif fault == "dates":
        new = replace(
            new, periods=frozenset({replace(P, end=date(2023, 1, 30))}), journals=(), balances=()
        )
    else:
        new = replace(new, balances=(replace(new.balances[0], liability=D(1)),))
    with pytest.raises(Problem):
        compare(old, new)
