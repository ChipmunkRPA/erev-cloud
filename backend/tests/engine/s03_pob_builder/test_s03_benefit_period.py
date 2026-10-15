"""B3-24: exercise POL-029 through the engine, including dated renewal estimates."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from erev_engine.bundle import InputBundle
from support import bundles
from tests.engine.s03_pob_builder import test_s03_specialist as base


def renewal_world(*, months: int | None, later_estimate: bool = False) -> InputBundle:
    right = replace(base.voucher(), option_type="RENEWAL_OPTION")
    estimates = [base.likelihood("0.80")]
    events = [
        base.booked(base.line("POB-02", "RENEWAL", "12000.00")),
        base.activated(2),
        bundles.event(
            base.CONTRACT,
            3,
            "ESTIMATE_CHANGED",
            base.INCEPTION,
            {"estimate_version_id": f"{base.LIKELIHOOD}@v1"},
        ),
    ]
    if months is not None:
        expectation = replace(
            base.likelihood("0.80"),
            estimate_key="K-01/RENEWAL",
            version_key="K-01/RENEWAL@v1",
            element_code="RENEWAL",
            estimate_kind="RENEWAL_EXPECTATION",
            rate=None,
            amortization_months=months,
        )
        estimates.append(expectation)
        events.append(
            bundles.event(
                base.CONTRACT,
                4,
                "ESTIMATE_CHANGED",
                base.INCEPTION,
                {"estimate_version_id": expectation.version_key},
            )
        )
        if later_estimate:
            later = replace(
                expectation,
                version_no=2,
                version_key="K-01/RENEWAL@v2",
                effective_date=date(2026, 6, 1),
                amortization_months=36,
                supersedes_version_key=expectation.version_key,
            )
            estimates.append(later)
            events.append(
                bundles.event(
                    base.CONTRACT,
                    5,
                    "ESTIMATE_CHANGED",
                    later.effective_date,
                    {"estimate_version_id": later.version_key},
                )
            )
    return base.world(
        *events,
        products=[base.product("RENEWAL", "TPL-RENEWAL")],
        templates=[
            base.template(
                "TPL-RENEWAL",
                obligation_kind="MATERIAL_RIGHT",
                satisfaction_pattern="OVER_TIME",
                over_time_criterion="OT_A",
                recognition_method="TIME_ELAPSED",
                ratable_convention="MONTHLY_EVEN",
            )
        ],
        contract=base.header(material_rights=(right,)),
        ssp=[base.ssp_book(base.entry("RENEWAL", "12.00"))],
        estimates=estimates,
        months=36,
        books=base.BOTH_BOOKS,
        policies={
            book: {"recognition.time_convention": "MONTHLY_EVEN"} for book in base.BOTH_BOOKS
        },
    )


@pytest.mark.parametrize("book", base.BOTH_BOOKS)
@pytest.mark.parametrize(
    ("months", "later_estimate", "end", "monthly_minor", "period_count"),
    [
        (None, False, date(2026, 12, 31), 100000, 12),
        (24, False, date(2027, 12, 31), 50000, 24),
        (24, True, date(2027, 12, 31), 50000, 24),
    ],
)
def test_expected_benefit_period_reaches_recognition(
    months: int | None,
    later_estimate: bool,
    end: date,
    monthly_minor: int,
    period_count: int,
    book: str,
) -> None:
    value = renewal_world(months=months, later_estimate=later_estimate)
    assert (
        base.context(value, book).policies.value("upfront_fee.recognition_period")
        == "EXPECTED_BENEFIT_PERIOD"
    )
    pob, _, allocated, _ = base.fold(value, book)
    assert pob.findings == ()
    option = base.by_key(pob)["POB-02"]
    assert (option.start_date, option.end_date) == (date(2026, 1, 1), end)
    assert option.option_ssp == 12  # 50 × 30% × 80%; the term does not reprice the right.
    assert allocated is not None and allocated.findings == ()
    revenue = base.revenue_by_period(value, book)
    assert revenue == {
        f"FY{2026 + index // 12}-P{index % 12 + 1:02d}": monthly_minor
        for index in range(period_count)
    }
    assert sum(revenue.values()) == 1200000


@pytest.mark.parametrize("book", base.BOTH_BOOKS)
def test_discount_voucher_does_not_inherit_renewal_benefit_period(book: str) -> None:
    value = renewal_world(months=24)
    original = value.contracts[0]
    contract = replace(original, material_rights=(base.voucher(),))
    value = replace(value, contracts=(contract,))
    pob, _, _, _ = base.fold(value, book)
    assert base.by_key(pob)["POB-02"].end_date == date(2026, 12, 31)
    assert base.revenue_by_period(value, book) == {
        f"FY2026-P{month:02d}": 100000 for month in range(1, 13)
    }
