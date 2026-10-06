"""Report-block cell resolution and comparison for the PRP-3 platform keys (dev-guide §9.5.6
"Report cell keys", DG-AK-35, DG-AK-51 to DG-AK-55; BUILD_SPEC PRP-3 prep, lane F-RPS + ENG-E1).

The rows are shaped as the builders on main emit them (``rpo`` flat band fields, rollforward line
rows, ``revenue_from_opening_liability`` section 2 rows, ``disaggregation`` timing rows); no run is
executed and ``PLATFORM_RUNNER_MISSING`` stays in force. The two DISC keys and POS-CHK-117 supply
the cells; their expected values are the keys' own oracles, never engine output.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

import pytest
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.models import ReportBlock, ReportCell
from support.answer_keys.report_cells import (
    ABSENT,
    INCONSISTENT_CURRENCY,
    NO_CURRENCY_CONTEXT,
    CellRef,
    compare_block,
    resolve,
    row_matches,
)

EX21 = "disc/DISC-S10-DISCLOSURES-REPORTS-EX21-ROLLFORWARD-AND-TIMING.yaml"
EX42 = "disc/DISC-S10-DISCLOSURES-RPO-EX42-TIME-BANDS-AND-EXPEDIENT.yaml"
CHK117 = "pos/POS-CHK-117-BALANCE-AGING-EXPORT-TIES-TO-RECLASS.yaml"


def _key(path: str):  # noqa: ANN202 - the loader's AnswerKey
    return load(ANSWER_KEY_ROOT / path).key


def _blocks(path: str, checkpoint: str) -> tuple[Any, tuple[ReportBlock, ...]]:
    key = _key(path)
    found = next(item for item in key.checkpoints if item.name == checkpoint)
    assert found.reports is not None
    return key, found.reports


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def _rollforward_rows(revenue_from_opening: str = "-17500.00") -> list[dict[str, Any]]:
    """Section 1 rows of ``contract_balance_rollforward`` for one USD entity (signed activity)."""
    lines = {
        "OPENING": ("17500.00", "0.00", "0.00"),
        "BILLINGS": ("0.00", "0.00", "0.00"),
        "REVENUE_FROM_OPENING": (revenue_from_opening, "0.00", "0.00"),
        "REVENUE_FROM_PERIOD_BILLINGS": ("0.00", "0.00", "0.00"),
        "RECLASSIFICATIONS": ("0.00", "0.00", "0.00"),
        "FX_REMEASUREMENT": ("0.00", "0.00", "0.00"),
        "BUSINESS_COMBINATIONS": ("0.00", "0.00", "0.00"),
        "OTHER": ("0.00", "0.00", "0.00"),
        "CLOSING": ("0.00", "0.00", "0.00"),
    }
    return [
        {
            "row_key": line,
            "section": 1,
            "currency": "USD",
            "contract_liability": usd(liability),
            "contract_asset": usd(asset),
            "unbilled_receivable": usd(unbilled),
        }
        for line, (liability, asset, unbilled) in lines.items()
    ] + [
        {
            "row_key": "contract:C-DISC-S10R:US01",
            "section": 2,
            "opening": usd("17500.00"),
            "closing": usd("0.00"),
        }
    ]


def test_ex21_rollforward_cells_read_the_line_rows_signed() -> None:
    """DG §9.5.6: ``revenue_from_opening_liability`` reads row ``REVENUE_FROM_OPENING``, field
    ``contract_liability``, signed negative, so the key's "-17500.00" matches the run's −17,500.00
    without a sign flip; the other five columns read their line rows."""
    key, blocks = _blocks(EX21, "reports-after-year-2")
    block = blocks[0]
    assert block.report_code == "contract_balance_rollforward"
    refs = {cell.column_key: resolve(key, block, cell) for cell in block.cells}
    assert refs["revenue_from_opening_liability"] == CellRef(
        "contract_balance_rollforward",
        "entity:US01",
        "revenue_from_opening_liability",
        "contract_liability",
        "row",
        ("REVENUE_FROM_OPENING", "REVENUE_FROM_OPENING:USD"),
    )
    assert refs["opening_contract_liability"].candidates[0] == "OPENING"
    assert refs["closing_contract_liability"].candidates[0] == "CLOSING"
    assert compare_block(key, block, _rollforward_rows()) == []
    # A sign flip (a positive revenue line) is a mismatch that shows the actual signed value.
    (found,) = compare_block(key, block, _rollforward_rows(revenue_from_opening="17500.00"))
    assert (found.column_key, found.expected, found.actual) == (
        "revenue_from_opening_liability",
        "-17500.00",
        "17500.00",
    )
    # Mixed-currency runs suffix the line rows with the ISO code; the same cells still resolve.
    mixed = [{**row, "row_key": f"{row['row_key']}:USD"} for row in _rollforward_rows()[:9]]
    assert compare_block(key, block, mixed) == []


def test_ex21_revenue_from_opening_liability_entity_row_sums_contract_rows() -> None:
    key, blocks = _blocks(EX21, "reports-after-year-2")
    block = blocks[1]
    assert block.report_code == "revenue_from_opening_liability"
    (ref,) = [resolve(key, block, cell) for cell in block.cells]
    assert (ref.field, ref.mode, ref.suffix) == ("revenue_from_opening", "sum", ":US01")
    rows = [
        {
            "row_key": "contract:C-DISC-S10R:US01",
            "section": 2,
            "opening_contract_liability": usd("17500.00"),
            "revenue_recognized": usd("17500.00"),
            "revenue_from_opening": usd("10000.00"),
        },
        {
            "row_key": "contract:C-OTHER:US01",
            "section": 2,
            "opening_contract_liability": usd("0.00"),
            "revenue_recognized": usd("7500.00"),
            "revenue_from_opening": usd("7500.00"),
        },
        {"row_key": "summary:USD", "section": 1, "revenue_from_opening": usd("17500.00")},
    ]
    assert compare_block(key, block, rows) == []
    # A contract row key reads one contract only.
    single = ReportBlock(
        report_code="revenue_from_opening_liability",
        parameters={},
        cells=(
            ReportCell(
                row_key="C-DISC-S10R", column_key="revenue_from_opening_liability", value="10000.00"
            ),
        ),
    )
    assert compare_block(key, single, rows) == []


def test_ex21_disaggregation_timing_rows_sum_every_matching_row() -> None:
    """``timing:<pattern>`` matches every row whose key ends with ``:<pattern>`` (timing-only rows
    and dimension rows alike); column ``revenue`` reads field ``total``."""
    key, blocks = _blocks(EX21, "reports-after-year-2")
    year_one = blocks[2]
    assert year_one.report_code == "disaggregation"
    rows = [
        {"row_key": "LICENCE:POINT_IN_TIME", "total": usd("87500.00")},
        {"row_key": "SERVICES:OVER_TIME", "total": usd("35000.00")},
        {"row_key": "TOTAL:USD", "total": usd("122500.00")},
    ]
    assert compare_block(key, year_one, rows) == []
    timing_only = [
        {"row_key": "timing:POINT_IN_TIME", "total": usd("87500.00")},
        {"row_key": "timing:OVER_TIME", "total": usd("35000.00")},
    ]
    assert compare_block(key, year_one, timing_only) == []
    # Two rows of one timing sum; the TOTAL row never contributes.
    split = [
        {"row_key": "LICENCE:POINT_IN_TIME", "total": usd("80000.00")},
        {"row_key": "HARDWARE:POINT_IN_TIME", "total": usd("7500.00")},
        {"row_key": "SERVICES:OVER_TIME", "total": usd("35000.00")},
        {"row_key": "TOTAL:USD", "total": usd("122500.00")},
    ]
    assert compare_block(key, year_one, split) == []
    dimension = ReportBlock(
        report_code="disaggregation",
        parameters={"dimension_code": "revenue_category"},
        cells=(
            ReportCell(row_key="revenue_category:LICENCE", column_key="revenue", value="80000.00"),
        ),
    )
    assert compare_block(key, dimension, split) == []
    year_two = blocks[3]  # the year-2 block expects 0.00 / 17500.00 against the year-1 rows
    found = compare_block(key, year_two, rows)
    assert [(item.row_key, item.expected, item.actual) for item in found] == [
        ("timing:POINT_IN_TIME", "0.00", "87500.00"),
        ("timing:OVER_TIME", "17500.00", "35000.00"),
    ]


def test_ex42_rpo_cells_read_flat_band_fields_and_total_rows() -> None:
    """The run rows carry the bands as flat fields named by the band key (``within_12_months``…),
    beside ``total``; contract handles normalise to ``contract:<id>`` and TOTAL to ``TOTAL:USD``
    (DG-AK-35). The dev-guide's "field ``bands.<k>``" is the API data shape, not the row shape
    (recorded for the docs lane)."""
    key, blocks = _blocks(EX42, "december-2026-rpo")
    (block,) = blocks
    refs = [resolve(key, block, cell) for cell in block.cells]
    assert {ref.row_key for ref in refs} == {"contract:C-EX42-B", "contract:C-EX42-C", "TOTAL:USD"}
    assert {ref.field for ref in refs} == {
        "within_12_months",
        "months_13_to_24",
        "after_24_months",
        "total",
    }
    rows = [
        {
            "row_key": "contract:C-EX42-A",
            "section": 1,
            "total": usd("9000.00"),
            "within_12_months": usd("6000.00"),
            "months_13_to_24": usd("3000.00"),
            "after_24_months": usd("0.00"),
        },
        {
            "row_key": "contract:C-EX42-B",
            "section": 1,
            "total": usd("7200.00"),
            "within_12_months": usd("4800.00"),
            "months_13_to_24": usd("2400.00"),
            "after_24_months": usd("0.00"),
        },
        {
            "row_key": "contract:C-EX42-C",
            "section": 1,
            "total": usd("2362.50"),
            "within_12_months": usd("1575.00"),
            "months_13_to_24": usd("787.50"),
            "after_24_months": usd("0.00"),
        },
        {
            "row_key": "TOTAL:USD",
            "section": 1,
            "total": usd("9562.50"),
            "within_12_months": usd("6375.00"),
            "months_13_to_24": usd("3187.50"),
            "after_24_months": usd("0.00"),
        },
    ]
    assert compare_block(key, block, rows) == []
    with pytest.raises(ValueError, match="column"):
        resolve(
            key, block, ReportCell(row_key="C-EX42-B", column_key="months_25_to_36", value="0.00")
        )
    custom = ReportBlock(
        report_code="rpo",
        parameters={"time_bands": ["6", "12"]},
        cells=(ReportCell(row_key="TOTAL", column_key="months_7_to_12", value="0.00"),),
    )
    assert resolve(key, custom, custom.cells[0]).field == "months_7_to_12"


def test_chk117_balance_aging_cells_read_row_and_field_as_written() -> None:
    """Any other code: ``row_key`` ``contract:<id>:<role>``, the column key as the field (CHK-117;
    RPT-36 buckets). Absent rows are ``<absent>``; a wrong bucket shows the actual."""
    key, blocks = _blocks(CHK117, "march-close")
    (block,) = blocks
    assert block.report_code == "balance_aging"
    rows = [
        {
            "row_key": "contract:C-POS-117:UNBILLED_RECEIVABLE",
            "balance_role": "UNBILLED_RECEIVABLE",
            "bucket_0_30": usd("3000.00"),
            "bucket_31_90": usd("0.00"),
            "total": usd("3000.00"),
        },
        {
            "row_key": "contract:C-POS-117:CONTRACT_ASSET",
            "balance_role": "CONTRACT_ASSET",
            "bucket_0_30": usd("2000.00"),
            "bucket_31_90": usd("0.00"),
            "total": usd("2000.00"),
        },
    ]
    assert compare_block(key, block, rows) == []
    absent = compare_block(key, block, rows[:1])
    assert [(item.row_key, item.actual) for item in absent] == [
        ("contract:C-POS-117:CONTRACT_ASSET", ABSENT),
        ("contract:C-POS-117:CONTRACT_ASSET", ABSENT),
    ]
    aged = [dict(rows[0]), {**rows[1], "bucket_0_30": usd("0.00"), "bucket_31_90": usd("2000.00")}]
    found = compare_block(key, block, aged)
    assert [(item.column_key, item.expected, item.actual) for item in found] == [
        ("bucket_0_30", "2000.00", "0.00"),
        ("bucket_31_90", "0.00", "2000.00"),
    ]


def test_a_row_of_zeros_the_report_does_not_state_compares_clean() -> None:
    """Dev-guide §9.5.6 "Report cell keys" (rev 1.219). EX21 expects ``timing:POINT_IN_TIME``
    revenue 0.00 for its second year; the report of that year states the rows it has figures
    for — an over-time row and no point-in-time row. A row of a report block whose every
    expected measure is exactly zero compares clean when no row of the run matches it. The rule
    is narrow: a zero row the report does state is compared as stated; a row with any other
    expected measure that the report lacks is a mismatch in every cell, its zero cells too; and
    an expected value that is no number is no zero."""
    key, blocks = _blocks(EX21, "reports-after-year-2")
    year_two = blocks[3]
    assert [(cell.row_key, cell.column_key, cell.value) for cell in year_two.cells] == [
        ("timing:POINT_IN_TIME", "revenue", "0.00"),
        ("timing:OVER_TIME", "revenue", "17500.00"),
    ]
    stated = [
        {"row_key": "SERVICES:OVER_TIME", "total": usd("17500.00")},
        {"row_key": "TOTAL:USD", "total": usd("17500.00")},
    ]
    assert compare_block(key, year_two, stated) == []
    # The same row stated by the report is compared as stated: a zero is clean, a figure is not.
    with_zero = [{"row_key": "LICENCE:POINT_IN_TIME", "total": usd("0.00")}, *stated]
    assert compare_block(key, year_two, with_zero) == []
    with_figure = [{"row_key": "LICENCE:POINT_IN_TIME", "total": usd("1.00")}, *stated]
    (found,) = compare_block(key, year_two, with_figure)
    assert (found.row_key, found.expected, found.actual) == ("timing:POINT_IN_TIME", "0.00", "1.00")
    # A row with a figure that the report lacks stays a mismatch: an empty report is not clean.
    (lacking,) = compare_block(key, year_two, [])
    assert (lacking.row_key, lacking.expected, lacking.actual) == (
        "timing:OVER_TIME",
        "17500.00",
        ABSENT,
    )
    # A row with one figure among zeros that the report lacks: every cell is absent, the zero
    # cells too (CHK-117: 3000.00 and 0.00; 2000.00 and 0.00).
    aging_key, (aging,) = _blocks(CHK117, "march-close")
    assert [
        (item.row_key.rsplit(":", 1)[1], item.column_key, item.expected, item.actual)
        for item in compare_block(aging_key, aging, [])
    ] == [
        ("UNBILLED_RECEIVABLE", "bucket_0_30", "3000.00", ABSENT),
        ("UNBILLED_RECEIVABLE", "bucket_31_90", "0.00", ABSENT),
        ("CONTRACT_ASSET", "bucket_0_30", "2000.00", ABSENT),
        ("CONTRACT_ASSET", "bucket_31_90", "0.00", ABSENT),
    ]

    def lacked(*values: str) -> list[tuple[str, str]]:
        """The mismatches of one row with ``values`` in its buckets against an empty report."""
        columns = ("bucket_0_30", "bucket_31_90", "total")
        block = ReportBlock(
            report_code="balance_aging",
            parameters={},
            cells=tuple(
                ReportCell(row_key="contract:C-9:CONTRACT_ASSET", column_key=column, value=value)
                for column, value in zip(columns, values, strict=False)
            ),
        )
        return [(item.expected, item.actual) for item in compare_block(aging_key, block, [])]

    assert lacked("0.00", "0.00", "0.00") == []  # every measure of the row is zero
    assert lacked("0.00", "-0.00", "0") == []  # zero however it is written
    assert lacked("0.00", "0.01") == [("0.00", ABSENT), ("0.01", ABSENT)]
    assert lacked("0.00", "n/a") == [("0.00", ABSENT), ("n/a", ABSENT)]  # no number, no zero


def test_money_places_and_plain_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    """DG-AK-51: the expected string carries the currency's places; a plain decimal string cell
    value compares like a money mapping; an unreadable field is ``<absent>``."""
    key, blocks = _blocks(CHK117, "march-close")
    (block,) = blocks
    plain = [
        {
            "row_key": "contract:C-POS-117:UNBILLED_RECEIVABLE",
            "bucket_0_30": "3000.00",
            "bucket_31_90": "0",
        },
        {
            "row_key": "contract:C-POS-117:CONTRACT_ASSET",
            "bucket_0_30": "2000.00",
            "bucket_31_90": "0.00",
        },
    ]
    assert compare_block(key, block, plain, currency="USD") == []
    malformed = [{**plain[0], "bucket_0_30": "three thousand"}, plain[1]]
    (found,) = compare_block(key, block, malformed, currency="USD")
    assert (found.column_key, found.actual) == ("bucket_0_30", ABSENT)
    one_place = ReportBlock(
        report_code="balance_aging",
        parameters={},
        cells=(
            ReportCell(
                row_key="contract:C-POS-117:CONTRACT_ASSET",
                column_key="bucket_0_30",
                value="2000.0",
            ),
        ),
    )
    (found,) = compare_block(key, one_place, plain, currency="USD")
    assert (found.expected, found.actual) == (
        "2000.0",
        "2000.00",
    )  # the authoring defect, not the run


def test_row_matches_handles_mixed_currency_suffixes() -> None:
    key, blocks = _blocks(EX21, "reports-after-year-2")
    ref = resolve(key, blocks[2], blocks[2].cells[0])
    assert row_matches(ref, "LICENCE:POINT_IN_TIME:USD", "USD")
    assert not row_matches(ref, "LICENCE:POINT_IN_TIME:EUR", "USD")  # another currency's row (R1)
    assert not row_matches(ref, "SERVICES:OVER_TIME:USD", "USD")
    assert not row_matches(ref, "TOTAL:USD", "USD")
    entity_ref = resolve(key, blocks[1], blocks[1].cells[0])
    assert row_matches(entity_ref, "contract:X:US01", "USD")
    assert not row_matches(entity_ref, "contract:X:UK01", "USD")
    assert not row_matches(entity_ref, "summary:USD", "USD")


def _sum(rows: Sequence[Mapping[str, Any]], field: str) -> Decimal:
    return sum((Decimal(row[field]["amount"]) for row in rows), Decimal(0))


def test_platform_runner_guard_is_unchanged() -> None:
    """XR-12: the runner is not built; the guard message and both raise sites stand."""
    from support.answer_keys import runners

    assert "never the engine runner" in runners.PLATFORM_RUNNER_MISSING
    assert not hasattr(runners, "run_platform")


# --- Codex review F-RPS-E1-R1 (PRODUCTION-F-RPS-E1-INDEPENDENT-642363e.md): currency identity ---


def _timing_rows(
    currency: str, point: str = "87500.00", over: str = "35000.00"
) -> list[dict[str, Any]]:
    return [
        {
            "row_key": "LICENCE:POINT_IN_TIME",
            "currency": currency,
            "total": {"amount": point, "currency": currency},
        },
        {
            "row_key": "SERVICES:OVER_TIME",
            "currency": currency,
            "total": {"amount": over, "currency": currency},
        },
    ]


def test_r1_rows_of_another_currency_are_not_accepted() -> None:
    """EX21 year-one cells are USD 87,500.00 / 35,000.00; rows whose row metadata and money
    mappings say EUR carry the same figures and must not match (R1 negative)."""
    key, blocks = _blocks(EX21, "reports-after-year-2")
    year_one = blocks[2]
    assert compare_block(key, year_one, _timing_rows("USD"), currency="USD") == []
    found = compare_block(key, year_one, _timing_rows("EUR"), currency="USD")
    assert [(item.row_key, item.actual) for item in found] == [
        ("timing:POINT_IN_TIME", ABSENT),
        ("timing:OVER_TIME", ABSENT),
    ]


def _with_eur_probe(key: Any) -> Any:
    """Codex R1 control: the key with one copied contract ``C-PROBE-EUR`` in EUR, so the run mixes
    currencies; the original cells and expected figures are untouched."""
    probe = key.contracts[0].model_copy(
        update={"external_id": "C-PROBE-EUR", "transaction_currency": "EUR"}
    )
    return key.model_copy(update={"contracts": (*key.contracts, probe)})


def test_r1_mixed_currency_rows_restrict_the_sum_to_the_selected_currency() -> None:
    """A run over a key that mixes currencies suffixes the row keys with the ISO code (``:USD`` /
    ``:EUR``). Correct USD figures beside equal EUR figures match the USD cells without doubling;
    zero USD figures beside EUR figures equal to the USD oracles are a mismatch (R1 positive and
    negative controls, Codex review of 642363e)."""
    key, blocks = _blocks(EX21, "reports-after-year-2")
    mixed_key = _with_eur_probe(key)
    year_one = blocks[2]
    usd = [{**row, "row_key": f"{row['row_key']}:USD"} for row in _timing_rows("USD")]
    eur = [{**row, "row_key": f"{row['row_key']}:EUR"} for row in _timing_rows("EUR")]
    assert compare_block(mixed_key, year_one, usd + eur, currency="USD") == []
    zero_usd = [
        {**row, "row_key": f"{row['row_key']}:USD"} for row in _timing_rows("USD", "0.00", "0.00")
    ]
    found = compare_block(mixed_key, year_one, zero_usd + eur, currency="USD")
    assert [(item.row_key, item.expected, item.actual) for item in found] == [
        ("timing:POINT_IN_TIME", "87500.00", "0.00"),
        ("timing:OVER_TIME", "35000.00", "0.00"),
    ]
    with pytest.raises(ValueError, match="currency"):
        compare_block(mixed_key, year_one, usd + eur)  # a mixed key needs the explicit currency


def test_r1_inconsistent_row_money_and_suffix_metadata_is_diagnosed() -> None:
    """A ``:USD`` row key whose money mapping says EUR, or a USD row field beside a EUR money
    mapping, is a comparison failure, never a silent acceptance."""
    key, blocks = _blocks(EX21, "reports-after-year-2")
    year_one = blocks[2]
    suffix_vs_money = [
        {
            "row_key": "LICENCE:POINT_IN_TIME:USD",
            "total": {"amount": "87500.00", "currency": "EUR"},
        },
        {"row_key": "SERVICES:OVER_TIME:USD", "total": {"amount": "35000.00", "currency": "USD"}},
    ]
    found = compare_block(key, year_one, suffix_vs_money, currency="USD")
    assert [(item.row_key, item.actual) for item in found] == [
        ("timing:POINT_IN_TIME", INCONSISTENT_CURRENCY)
    ]
    field_vs_money = [
        {
            "row_key": "LICENCE:POINT_IN_TIME",
            "currency": "USD",
            "total": {"amount": "87500.00", "currency": "EUR"},
        },
        {
            "row_key": "SERVICES:OVER_TIME",
            "currency": "USD",
            "total": {"amount": "35000.00", "currency": "USD"},
        },
    ]
    found = compare_block(key, year_one, field_vs_money, currency="USD")
    assert [(item.row_key, item.actual) for item in found] == [
        ("timing:POINT_IN_TIME", INCONSISTENT_CURRENCY)
    ]


def test_r1_plain_strings_need_an_explicit_trusted_currency() -> None:
    """Plain decimal strings carry no currency; they compare only under an explicit ``currency``
    argument (the trusted context), otherwise the cell is ``<no currency context>``."""
    key, blocks = _blocks(CHK117, "march-close")
    (block,) = blocks
    plain = [
        {
            "row_key": "contract:C-POS-117:UNBILLED_RECEIVABLE",
            "bucket_0_30": "3000.00",
            "bucket_31_90": "0.00",
        },
        {
            "row_key": "contract:C-POS-117:CONTRACT_ASSET",
            "bucket_0_30": "2000.00",
            "bucket_31_90": "0.00",
        },
    ]
    assert compare_block(key, block, plain, currency="USD") == []
    found = compare_block(key, block, plain)
    assert len(found) == 4 and {item.actual for item in found} == {NO_CURRENCY_CONTEXT}
