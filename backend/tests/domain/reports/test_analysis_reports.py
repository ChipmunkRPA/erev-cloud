"""Contract cost rollforward, book and adoption bridges, intercompany pairs and balance aging
(SCREENS_B §5.6.1 RPT-32, RPT-36, §5.6.6 RPT-33 to RPT-35; ENGINE_SPEC_B §15.2.6, §12, §13; 04
table 10-T; POLICIES CHK-010, CHK-117; PRD J-12.4, J-13-AC-7, WLD-X-08, WLD-X-14, WLD-X-20; 03
REQ-BK-006, REQ-BK-007, REQ-ENT-005, REQ-BIL-013, REQ-CST-006; BUILD_SPEC RPS-12).

Worlds, each built through the product's commands (``support.worlds``); every report runs through
``POST /report-runs`` and its ``REPORT_RUN`` job; the frozen clock starts at 2026-09-12T12:00:00Z.

- ``k02_marrowby_commission`` then ``k09_orrin_vale``: WLD-K-02 with ``COM-2026-0002`` and
  WLD-K-09 with ``COM-K09`` in AVM-US.
- ``onb_s11_modretro_own``: ``C-ADOPT`` of answer key ONB-S11-MODRETRO-OWN with a ``LEGACY`` book.
- ``ifrs_sw01``: ``C-IFRS-SW01`` of answer key IFRS-SW01-COLLECTIBILITY-THRESHOLD-PER-BOOK.
- ``k04_saltmarsh``: WLD-K-04 ``SF-ORD-UK-2001`` across AVM-UK and AVM-US.
- ``chk_010_position``: the contract of POLICIES CHK-010.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import legal_entity, subledger_line, subledger_posting
from erev_api.domain.reports import framework
from erev_api.domain.reports.builders import (
    ReportParams,
    adoption_bridge,
    book_bridge,
    intercompany_pairs,
)
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.http import call
from support.principals import cookie_headers
from support.worlds import (
    AUGUST_2026,
    AVM_UK,
    AVM_US,
    C_ADOPT,
    C_IFRS_SW01,
    C_POS,
    K02,
    K04,
    K09,
    REPORT_RUNS,
    SEPTEMBER_2026,
    US01,
    ReportWorld,
    chk_010_position,
    ifrs_sw01,
    k02_marrowby_commission,
    k04_saltmarsh,
    k09_orrin_vale,
    onb_s11_modretro_own,
    report_run,
)

D = Decimal
COST_LINES: Final = (
    "OPENING",
    "ADDITIONS",
    "CLAWBACKS",
    "AMORTIZATION",
    "ACCELERATION",
    "IMPAIRMENT",
    "IMPAIRMENT_REVERSAL",
    "CLOSING",
)
ZERO_BUCKETS: Final = ("bucket_31_90", "bucket_91_180", "bucket_181_365", "bucket_over_365")


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    found = {str(row["row_key"]): row for row in rows}
    assert len(found) == len(rows)  # a row key occurs once
    return found


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def gbp(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "GBP"}


def stated(row: Mapping[str, Any]) -> dict[str, Any]:
    """The cells of a row that hold a value (a row of one section leaves the others' empty)."""
    return {key: value for key, value in row.items() if value is not None and key != "row_key"}


def tie_of(run: Mapping[str, Any], code: str) -> Mapping[str, Any]:
    (tie,) = run["tie_out_results"]
    assert tie["code"] == code
    return dict(tie)


def file_outputs(world: ReportWorld, code: str, parameters: Mapping[str, Any]) -> list[str]:
    """The header row of the report's CSV output, after the report has also been rendered as XLSX
    and PDF (SCREENS_B "Kind, formats": every format the definition offers is served)."""
    header = ""
    for output_format in ("XLSX", "PDF", "CSV"):
        run, _ = report_run(world, code, parameters, output_format=output_format)
        output = call(
            world.app,
            "GET",
            f"{REPORT_RUNS}/{run['id']}/output",
            headers=cookie_headers(world.maya.token, key=False),
        )
        assert output.status_code == 200, (output_format, output.text)
        assert output.content, output_format
        if output_format == "CSV":
            header = output.text.split("\r\n")[0]
    return next(csv.reader([header]))


def refused(
    world: ReportWorld,
    code: str,
    parameters: Mapping[str, Any],
    *,
    entity_ids: Sequence[UUID] | None = None,
) -> tuple[str, str]:
    """(field, message) of the refusal the builder of ``code`` raises in a unit of work: the way
    a refusal by name is read (a refused run ends its job FAILED)."""
    with world.place.uow() as uow, pytest.raises(Problem) as found:
        framework.BUILDERS[code](
            uow,
            ReportParams(
                report_code=code,
                report_version=1,
                parameters=dict(parameters),
                entity_ids=(world.entity_id,) if entity_ids is None else tuple(entity_ids),
                known_at=world.place.clock.now(),
            ),
        )
    (error,) = found.value.errors
    return str(error.field), str(error.message)


# --- RPT-32 -----------------------------------------------------------------------------------


def cost_lines(rows: Sequence[Mapping[str, Any]]) -> dict[str, Decimal]:
    """Line code → amount of the ``OBTAIN`` rows of a contract cost rollforward in USD."""
    found = keyed(rows)
    assert list(found) == [f"OBTAIN:{line}" for line in COST_LINES]  # S15-R-17 order; no FULFILL
    assert {row["currency"] for row in rows} == {"USD"}
    assert {row["entity_code"] for row in rows} == {AVM_US}
    return {line: D(found[f"OBTAIN:{line}"]["amount"]["amount"]) for line in COST_LINES}


def carrying(world: ReportWorld, period_key: str) -> dict[str, Decimal]:
    """Contract external id → T-CON-09 contract cost assets at the end of ``period_key``, from
    the contract balances report (RPT-02)."""
    _, rows = report_run(
        world,
        "contract_balances",
        {"entity_codes": [AVM_US], "book": "ASC606", "period_key": period_key},
    )
    return {
        str(row["contract_external_id"]): D(row["cost_asset_carrying"]["amount"])
        for row in rows
        if row["contract_external_id"] is not None
    }


@pytest.mark.slow
def test_cost_rollforward_k09_k02(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """PRD J-12.4, September 2026, cost kind Obtain. K-02: opening 8,005.48, amortisation
    (493.15), closing 7,512.33 (WLD-X-08). K-09: opening 0.00, additions 6,480.00, amortisation
    (177.37), impairment 0.00, closing 6,302.63 (WLD-X-20). ``TO_COST_ROLLFORWARD_BALANCES``
    passes. The dataset holds one row per cost kind and line (SCREENS_B RPT-32 rev 1.14: the
    section by cost asset is deferred), so K-02 is read before K-09 is booked and K-09 is the
    change its booking makes; each contract's carrying amount is read from the contract balances
    report at both ends."""
    september = {
        "entity_codes": [AVM_US],
        "book": "ASC606",
        "from_period_key": SEPTEMBER_2026,
        "to_period_key": SEPTEMBER_2026,
    }
    world = k02_marrowby_commission(app, keyring, clock, files)
    run, rows = report_run(world, "contract_cost_rollforward", september)
    assert run["parameters"]["currency_view"] == "functional"  # SCREENS_B RPT-32 default
    k02 = cost_lines(rows)
    assert k02 == {
        "OPENING": D("8005.48"),  # 12,000.00 less 3,994.52 amortised through 31 Aug (WLD-X-08)
        "ADDITIONS": D("0.00"),
        "CLAWBACKS": D("0.00"),
        "AMORTIZATION": D("-493.15"),
        "ACCELERATION": D("0.00"),
        "IMPAIRMENT": D("0.00"),
        "IMPAIRMENT_REVERSAL": D("0.00"),
        "CLOSING": D("7512.33"),
    }
    assert {row["category_label"] for row in rows} == {"Costs to obtain a contract"}
    assert run["control_totals"] == {"opening": {"USD": "8005.48"}, "closing": {"USD": "7512.33"}}
    tie = tie_of(run, "TO_COST_ROLLFORWARD_BALANCES")
    assert tie["result"] == "PASS"
    assert tie["expected"] == tie["actual"] == [usd("7512.33")]
    assert carrying(world, AUGUST_2026) == {K02: D("8005.48")}

    both = k09_orrin_vale(world)
    run, rows = report_run(both, "contract_cost_rollforward", september)
    combined = cost_lines(rows)
    assert combined == {
        "OPENING": D("8005.48"),
        "ADDITIONS": D("6480.00"),
        "CLAWBACKS": D("0.00"),
        "AMORTIZATION": D("-670.52"),
        "ACCELERATION": D("0.00"),
        "IMPAIRMENT": D("0.00"),
        "IMPAIRMENT_REVERSAL": D("0.00"),
        "CLOSING": D("13814.96"),
    }
    # K-09: what its booking adds to every line (its opening is 0.00: inception 01 Sep 2026)
    assert {line: combined[line] - k02[line] for line in COST_LINES} == {
        "OPENING": D("0.00"),
        "ADDITIONS": D("6480.00"),
        "CLAWBACKS": D("0.00"),
        "AMORTIZATION": D("-177.37"),  # round(6,480.00 × 30 ÷ 1,096) (WLD-X-20)
        "ACCELERATION": D("0.00"),
        "IMPAIRMENT": D("0.00"),
        "IMPAIRMENT_REVERSAL": D("0.00"),
        "CLOSING": D("6302.63"),
    }
    assert run["control_totals"] == {
        "opening": {"USD": "8005.48"},
        "closing": {"USD": "13814.96"},
    }
    tie = tie_of(run, "TO_COST_ROLLFORWARD_BALANCES")
    assert tie["result"] == "PASS"
    assert tie["expected"] == tie["actual"] == [usd("13814.96")]
    # each contract's carrying amount at both ends (T-CON-09): K-09 holds none before September
    assert carrying(both, AUGUST_2026) == {K02: D("8005.48")}
    assert carrying(both, SEPTEMBER_2026) == {K02: D("7512.33"), K09: D("6302.63")}


# --- RPT-34 -----------------------------------------------------------------------------------


def _line_count(world: ReportWorld, *where: Any) -> int:
    return int(world.place.scalar(select(func.count()).select_from(subledger_line).where(*where)))


@pytest.mark.slow
def test_adoption_bridge_s11_modretro_own(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Answer key ONB-S11-MODRETRO-OWN with a date of initial application of 1 Jan 2026:
    ``C-ADOPT`` revenue to date legacy GAAP 100,000.00 and ASC 606 220,000.00, cumulative effect
    120,000.00; contract liability legacy GAAP 200,000.00 and ASC 606 80,000.00. The report posts
    nothing and no line uses ``RETAINED_EARNINGS`` (D-14a; REQ-BK-007)."""
    world = onb_s11_modretro_own(app, keyring, clock, files)
    postings = world.place.scalar(select(func.count()).select_from(subledger_posting))
    run, rows = report_run(
        world,
        "adoption_bridge",
        {"entity_codes": [US01], "date_of_initial_application": "2026-01-01"},
    )
    found = keyed(rows)
    assert list(found) == [
        f"contract:{C_ADOPT}",
        "line:REVENUE",
        "line:CONTRACT_LIABILITY",
        "line:CONTRACT_ASSET",
        "line:UNBILLED_RECEIVABLE",
        "line:COST_ASSETS",
    ]
    assert stated(found[f"contract:{C_ADOPT}"]) == {
        "section": 1,
        "contract_external_id": C_ADOPT,
        "customer_name": "Example Customer (Demo)",
        "currency": "USD",
        "revenue_legacy": usd("100000.00"),  # legacy GAAP: 100,000.00 a year, the year 2025
        "revenue_asc606": usd("220000.00"),  # licence 180,000.00 + support 12 × 3,333.33…
        "cumulative_effect": usd("120000.00"),
        "contract_liability_legacy": usd("200000.00"),  # billed 300,000.00 less 100,000.00
        "contract_liability_asc606": usd("80000.00"),
        "asset_asc606": usd("0.00"),
    }
    lines = {
        str(row["line_code"]): (row["line_label"], row["legacy_amount"], row["asc606_amount"])
        + (row["effect"],)
        for row in rows
        if row["section"] == 2
    }
    assert lines == {
        "REVENUE": ("Revenue", usd("100000.00"), usd("220000.00"), usd("120000.00")),
        "CONTRACT_LIABILITY": (
            "Contract liability",
            usd("200000.00"),
            usd("80000.00"),
            usd("-120000.00"),
        ),
        "CONTRACT_ASSET": ("Contract asset", usd("0.00"), usd("0.00"), usd("0.00")),
        "UNBILLED_RECEIVABLE": ("Unbilled receivable", usd("0.00"), usd("0.00"), usd("0.00")),
        # the LEGACY book records no contract cost asset: empty, never 0.00
        "COST_ASSETS": ("Contract cost assets", None, usd("0.00"), None),
    }
    assert run["control_totals"] == {
        "contract_count": 1,
        "revenue_legacy_total": {"USD": "100000.00"},
        "revenue_asc606_total": {"USD": "220000.00"},
        "cumulative_effect_total": {"USD": "120000.00"},
        "legacy_only_contract_count": 0,
        "legacy_only_revenue": {},
        "date_of_initial_application": "2026-01-01",
        "as_of": "2025-12-31",
    }
    assert run["tie_out_results"] == []  # SCREENS_B RPT-34: no tie-out
    # D-14a: the cumulative effect is exported, never posted — no posting by the run, and no line
    # of any book carries the Retained earnings role
    assert world.place.scalar(select(func.count()).select_from(subledger_posting)) == postings
    assert _line_count(world, subledger_line.c.account_role == "RETAINED_EARNINGS") == 0
    # the LEGACY book holds 150,000.00 of pre-standard revenue by the run: the 50,000.00 of 2026
    # lies after the date and stays outside the bridge
    legacy = world.place.scalar(
        select(func.sum(subledger_line.c.amount_txn)).where(
            subledger_line.c.book_code == "LEGACY",
            subledger_line.c.account_role == "PRE_STANDARD_REVENUE",
        )
    )
    assert D(legacy) == D("150000.00")

    # a date inside a period, or before the entity's first ASC 606 period, is refused by name
    assert refused(world, "adoption_bridge", {"date_of_initial_application": "2026-01-15"}) == (
        "parameters.date_of_initial_application",
        adoption_bridge.DATE_NOT_PERIOD_START,
    )
    assert refused(world, "adoption_bridge", {"date_of_initial_application": "2024-12-01"}) == (
        "parameters.date_of_initial_application",
        adoption_bridge.DATE_TOO_EARLY,
    )
    # the default date is the first day of the entity's first ASC 606 period: no day before it
    run, rows = report_run(world, "adoption_bridge", {"entity_codes": [US01]})
    assert rows == []
    assert run["control_totals"]["date_of_initial_application"] == "2025-01-01"
    assert run["control_totals"]["as_of"] is None
    # the contract filter
    filtered = {
        "entity_codes": [US01],
        "date_of_initial_application": "2026-01-01",
        "contract_external_id": C_ADOPT,
    }
    run, rows = report_run(world, "adoption_bridge", filtered)
    assert keyed(rows)[f"contract:{C_ADOPT}"]["cumulative_effect"] == usd("120000.00")
    # XLSX, PDF and CSV; the CSV header is the specification grid with the currency (RPT-R-03)
    assert file_outputs(world, "adoption_bridge", filtered) == [
        "Section",
        "Contract",
        "Customer",
        "Currency",
        "Revenue to date, legacy GAAP (USD)",
        "Revenue to date, ASC 606 (USD)",
        "Cumulative effect (USD)",
        "Contract liability, legacy GAAP (USD)",
        "Contract liability, ASC 606 (USD)",
        "Contract asset and unbilled receivable, ASC 606 (USD)",
        "Line code",
        "Line item",
        "Under legacy GAAP (USD)",
        "Under Topic 606 (USD)",
        "Effect (USD)",
    ]
    # US01 keeps ASC606 and LEGACY, not IFRS15: the book bridge names the entity it needs
    assert refused(world, "book_bridge", {}) == (
        "parameters.entity_codes",
        book_bridge.ENTITY_REQUIRED,
    )


# --- RPT-33 -----------------------------------------------------------------------------------


def _driver_rows(rows: Sequence[Mapping[str, Any]]) -> dict[str, tuple[Any, Any]]:
    """``<DRIVER>:<MEASURE>`` → (effect, contracts affected) of section 2."""
    return {
        f"{row['driver_code']}:{row['measure_code']}": (row["effect"], row["contracts_affected"])
        for row in rows
        if row["section"] == 2
    }


@pytest.mark.slow
def test_book_bridge_drivers_sum(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """Answer key IFRS-SW01-COLLECTIBILITY-THRESHOLD-PER-BOOK, January to March 2026: revenue
    0.00 in ASC 606 and 3,000.00 in IFRS 15. Section 2 driver ``COLLECTIBILITY`` carries the whole
    ASC 606 − IFRS 15 revenue difference, (3,000.00); every other driver is 0.00;
    ``TO_BRIDGE_DRIVERS_EQ_DIFFERENCE`` passes (REQ-BK-006)."""
    world = ifrs_sw01(app, keyring, clock, files)
    run, rows = report_run(
        world,
        "book_bridge",
        {"entity_codes": [US01], "from_period_key": "FY2026-P01", "to_period_key": "FY2026-P03"},
    )
    assert run["parameters"]["currency_view"] == "functional"  # SCREENS_B RPT-33 default
    found = keyed(rows)
    measures = {
        str(row["measure_code"]): (row["asc606_amount"], row["ifrs15_amount"], row["difference"])
        for row in rows
        if row["section"] == 1
    }
    nil = (usd("0.00"), usd("0.00"), usd("0.00"))
    assert measures == {
        "REVENUE": (usd("0.00"), usd("3000.00"), usd("-3000.00")),
        # 3,000.00 invoiced and paid: no contract balance in IFRS 15; ASC 606 holds the receipts
        # as a deposit liability, which is not a bridge measure
        "CONTRACT_LIABILITY": nil,
        "CONTRACT_ASSET": nil,
        "UNBILLED_RECEIVABLE": nil,
        "COST_ASSETS": nil,
        "LOSS_PROVISION": nil,
    }
    assert found["measure:REVENUE"]["measure_label"] == "Revenue"
    assert _driver_rows(rows) == {
        "COLLECTIBILITY:REVENUE": (usd("-3000.00"), 1),
        "COST_IMPAIRMENT_REVERSAL:REVENUE": (usd("0.00"), 0),
        "FRAMEWORK_ELECTIONS:REVENUE": (usd("0.00"), 0),
        "LICENCE_RENEWALS:REVENUE": (usd("0.00"), 0),
        "ONEROUS_CONTRACTS:REVENUE": (usd("0.00"), 0),
        "ADVANCE_CONSIDERATION_FX:REVENUE": (usd("0.00"), 0),
        "OTHER:REVENUE": (usd("0.00"), 0),
    }
    assert found["driver:COLLECTIBILITY:REVENUE"]["driver_label"] == "Collectibility"
    contract_row = found[f"contract:{C_IFRS_SW01}:REVENUE"]
    assert (
        contract_row["section"],
        contract_row["driver_code"],
        contract_row["asc606_amount"],
        contract_row["ifrs15_amount"],
        contract_row["difference"],
    ) == (3, "COLLECTIBILITY", usd("0.00"), usd("3000.00"), usd("-3000.00"))
    assert [key for key in found if key.startswith("contract:")] == [
        f"contract:{C_IFRS_SW01}:REVENUE"
    ]
    tie = tie_of(run, "TO_BRIDGE_DRIVERS_EQ_DIFFERENCE")
    assert tie["result"] == "PASS"
    assert tie["expected"] == tie["actual"] == [usd("-3000.00")]
    assert run["control_totals"] == {
        "contract_count": 1,
        "revenue_asc606": {"USD": "0.00"},
        "revenue_ifrs15": {"USD": "3000.00"},
        "revenue_difference": {"USD": "-3000.00"},
        "other_effect": {"USD": "0.00"},
    }

    # September 2026 (the default range): IFRS 15 recognises the month and carries the revenue
    # not yet invoiced, 9,000.00 less 3,000.00; both differences are the contract's Step 1
    run, rows = report_run(world, "book_bridge", {"entity_codes": [US01]})
    drivers = _driver_rows(rows)
    balance = keyed(rows)[f"contract:{C_IFRS_SW01}:CONTRACT_ASSET"]
    assert (
        balance["driver_code"],
        balance["asc606_amount"],
        balance["ifrs15_amount"],
        balance["difference"],
    ) == ("COLLECTIBILITY", usd("0.00"), usd("6000.00"), usd("-6000.00"))
    assert {key: value for key, value in drivers.items() if value[1]} == {
        "COLLECTIBILITY:REVENUE": (usd("-1000.00"), 1),
        "COLLECTIBILITY:CONTRACT_ASSET": (usd("-6000.00"), 1),
    }
    assert len(drivers) == 2 * len(book_bridge.DRIVERS)  # the two measures that differ
    tie = tie_of(run, "TO_BRIDGE_DRIVERS_EQ_DIFFERENCE")
    assert tie["result"] == "PASS"
    assert tie["expected"] == tie["actual"] == [usd("-7000.00")]
    # XLSX, PDF and CSV; the CSV header is the specification grid with the currency (RPT-R-03)
    assert file_outputs(world, "book_bridge", {"entity_codes": [US01]}) == [
        "Section",
        "Measure code",
        "Measure",
        "Driver code",
        "Driver",
        "Contract",
        "Currency",
        "ASC 606 (USD)",
        "IFRS 15 (USD)",
        "Difference (USD)",
        "Effect (USD)",
        "Contracts affected",
    ]
    # US01 keeps ASC606 and IFRS15, not LEGACY: the adoption bridge names the entity it needs
    assert refused(world, "adoption_bridge", {}) == (
        "parameters.entity_codes",
        adoption_bridge.ENTITY_REQUIRED,
    )


# --- RPT-35 -----------------------------------------------------------------------------------


@pytest.mark.slow
def test_intercompany_pairs_k04(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """PRD J-13-AC-7 (WLD-X-14), September 2026: ``SF-ORD-UK-2001`` O1 performed by AVM-US for
    AVM-UK, pairs of 4,790.61 GBP, unmatched 0.00; ``TO_IC_UNMATCHED_ZERO`` passes."""
    k04 = k04_saltmarsh(app, keyring, clock, files)
    world = k04.report
    september = {
        "book": "ASC606",
        "from_period_key": SEPTEMBER_2026,
        "to_period_key": SEPTEMBER_2026,
    }
    run, rows = report_run(world, "intercompany_pairs", september)
    assert run["parameters"]["entity_codes"] == [AVM_UK, AVM_US]  # default: all entities
    assert run["parameters"]["currency_view"] == "transaction"  # SCREENS_B RPT-35 default
    found = keyed(rows)
    assert list(found) == [f"pair:{AVM_US}:{AVM_UK}:GBP", f"contract:{K04}:O1:{SEPTEMBER_2026}"]
    assert stated(found[f"pair:{AVM_US}:{AVM_UK}:GBP"]) == {
        "section": 1,
        "due_from_entity_code": AVM_US,  # the performing entity
        "due_to_entity_code": AVM_UK,  # the contracting entity
        "currency": "GBP",
        "due_from_amount": gbp("4790.61"),  # 58,285.71 × (183 − 153) ÷ 365, cumulative rounding
        "due_to_amount": gbp("4790.61"),
        "unmatched_amount": gbp("0.00"),
    }
    assert stated(found[f"contract:{K04}:O1:{SEPTEMBER_2026}"]) == {
        "section": 2,
        "contract_external_id": K04,
        "obligation_key": "O1",
        "contracting_entity_code": AVM_UK,
        "performing_entity_code": AVM_US,
        "period_key": SEPTEMBER_2026,
        "currency": "GBP",
        "pair_amount": gbp("4790.61"),
        "unmatched_amount": gbp("0.00"),
    }
    tie = tie_of(run, "TO_IC_UNMATCHED_ZERO")
    assert tie["result"] == "PASS"
    assert tie["expected"] == tie["actual"] == [gbp("4790.61")]
    assert tie["difference"] == [gbp("0.00")]
    assert run["control_totals"] == {
        "pair_count": 1,
        "incomplete_pair_count": 0,
        "due_from_total": {"GBP": "4790.61"},
        "due_to_total": {"GBP": "4790.61"},
        "unmatched_total": {"GBP": "0.00"},
    }
    # WLD-X-14 "O1 schedule Sep 2026 (recognised by AVM-US)": the revenue line of the pair is
    # AVM-US's, 4,790.61 GBP at its own September rate of 1.28
    (revenue,) = world.place.rows(
        select(subledger_line.c.amount_txn, subledger_line.c.amount_functional)
        .select_from(
            subledger_line.join(legal_entity, legal_entity.c.id == subledger_line.c.entity_id)
        )
        .where(
            legal_entity.c.code == AVM_US,
            subledger_line.c.account_role == "REVENUE",
            subledger_line.c.period_end_date == date(2026, 9, 30),
        )
    )
    assert (D(revenue["amount_txn"]), D(revenue["amount_functional"])) == (
        D("-4790.61"),
        D("-6131.98"),
    )

    # the contract's life to date, April to September 2026: six periods on each side
    run, rows = report_run(
        world, "intercompany_pairs", {**september, "from_period_key": "FY2026-P04"}
    )
    found = keyed(rows)
    assert found[f"pair:{AVM_US}:{AVM_UK}:GBP"]["due_from_amount"] == gbp("29222.70")
    assert found[f"pair:{AVM_US}:{AVM_UK}:GBP"]["unmatched_amount"] == gbp("0.00")
    assert [key for key in found if key.startswith("contract:")] == [
        f"contract:{K04}:O1:FY2026-P{month:02d}" for month in range(4, 10)
    ]
    assert tie_of(run, "TO_IC_UNMATCHED_ZERO")["result"] == "PASS"

    # XLSX, PDF and CSV; the CSV header is the specification grid with the currency (RPT-R-03)
    assert file_outputs(world, "intercompany_pairs", september) == [
        "Section",
        "Due from entity",
        "Due to entity",
        "Currency",
        "Due from (GBP)",
        "Due to (GBP)",
        "Unmatched (GBP)",
        "Contract",
        "Obligation",
        "Contracting entity",
        "Performing entity",
        "Period",
        "Pair amount (GBP)",
    ]

    # a run for the contracting entity alone does not read AVM-US: its side is empty, never 0.00,
    # and the tie-out has no pair to test
    run, rows = report_run(world, "intercompany_pairs", {**september, "entity_codes": [AVM_UK]})
    pair = keyed(rows)[f"pair:{AVM_US}:{AVM_UK}:GBP"]
    assert (pair["due_from_amount"], pair["due_to_amount"], pair["unmatched_amount"]) == (
        None,
        gbp("4790.61"),
        None,
    )
    assert keyed(rows)[f"contract:{K04}:O1:{SEPTEMBER_2026}"]["pair_amount"] == gbp("4790.61")
    tie = tie_of(run, "TO_IC_UNMATCHED_ZERO")
    assert (tie["result"], tie["expected"], tie["actual"]) == ("NOT_APPLICABLE", None, None)
    assert run["control_totals"]["incomplete_pair_count"] == 1
    # AVM-US carries its side in GBP, not in its functional currency: the functional view is
    # refused by name
    assert refused(
        world,
        "intercompany_pairs",
        {**september, "currency_view": "functional"},
        entity_ids=(k04.us_entity_id, k04.uk_entity_id),
    ) == ("parameters.currency_view", intercompany_pairs.FUNCTIONAL_ONLY)


# --- RPT-36 -----------------------------------------------------------------------------------


def test_balance_aging_chk_010(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """POLICIES CHK-117 on the CHK-010 contract at 31 Jan 2026: unbilled receivable 3,000.00 and
    contract asset 2,000.00, both in the 0 to 30 day bucket (the revenue arose in the period);
    the totals equal the balances, ``TO_AGING_EQ_BALANCES`` passes (REQ-BIL-013).

    October 7: the registered builder reads persisted liability movements and engine
    presentation attributions without requiring a close-run journal."""
    world = chk_010_position(app, keyring, clock, files)
    run, rows = report_run(
        world,
        "balance_aging",
        {"entity_codes": [US01], "book": "ASC606", "period_key": "FY2026-P01"},
    )
    found = keyed(rows)
    assert list(found) == [
        f"contract:{C_POS}:CONTRACT_ASSET",
        f"contract:{C_POS}:UNBILLED_RECEIVABLE",
        "TOTAL:CONTRACT_ASSET:USD",
        "TOTAL:UNBILLED_RECEIVABLE:USD",
    ]
    for role, label, amount in (
        ("CONTRACT_ASSET", "Contract asset", "2000.00"),
        ("UNBILLED_RECEIVABLE", "Unbilled receivable", "3000.00"),
    ):
        row = found[f"contract:{C_POS}:{role}"]
        assert (row["contract_external_id"], row["entity_code"], row["balance_role"]) == (
            C_POS,
            US01,
            label,
        )
        assert (row["bucket_0_30"], row["total"]) == (usd(amount), usd(amount))
        assert {row[bucket]["amount"] for bucket in ZERO_BUCKETS} == {"0.00"}
        total = found[f"TOTAL:{role}:USD"]
        assert (total["bucket_0_30"], total["total"]) == (usd(amount), usd(amount))
    tie = tie_of(run, "TO_AGING_EQ_BALANCES")
    assert tie["result"] == "PASS"
    assert tie["expected"] == tie["actual"] == [usd("5000.00")]
    assert run["control_totals"] == {"total": {"USD": "5000.00"}}
    headers = file_outputs(
        world,
        "balance_aging",
        {"entity_codes": [US01], "book": "ASC606", "period_key": "FY2026-P01"},
    )
    assert headers[:5] == ["Contract", "Customer", "Entity", "Balance", "Currency"]


def test_balance_aging_rerun_keeps_versions_after_later_billing(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    from erev_api.db.tables import contract
    from erev_api.enums import ContractEventType
    from erev_api.events.payloads import BillingRecordedV1
    from erev_api.events.stream import EventIn
    from support.factories import appended, computed
    from support.reference import get, post
    from support.worlds import REPORT_RUN_ID_HEADER, run_now

    world = chk_010_position(app, keyring, clock, files)
    parameters = {"entity_codes": [US01], "book": "ASC606", "period_key": "FY2026-P01"}
    original, rows = report_run(world, "balance_aging", parameters)
    booked = world.contracts[C_POS]
    contract_id = UUID(str(booked.contract["id"]))
    head = world.place.scalar(
        select(contract.c.head_stream_version).where(contract.c.id == contract_id)
    )
    appended(
        world.place,
        contract_id,
        int(head),
        [
            EventIn(
                event_type=ContractEventType.BILLING_RECORDED,
                effective_date=date(2026, 1, 31),
                payload=BillingRecordedV1.model_validate(
                    {
                        "invoice_number": "INV-AGING-LATER",
                        "line_external_id": "INV-AGING-LATER-1",
                        "obligation_key": "P1-TM",
                        "amount": {"amount": "5000.00", "currency": "USD"},
                        "issue_date": "2026-01-31",
                    }
                ),
            )
        ],
    )
    computed(world.place, UUID(str(booked.combination_group["id"])))
    current, current_rows = report_run(world, "balance_aging", parameters)
    assert current_rows != rows
    assert tie_of(current, "TO_AGING_EQ_BALANCES")["result"] == "PASS"
    started = post(app, f"{REPORT_RUNS}/{original['id']}/rerun", world.maya, {})
    assert started.status_code == 202, started.text
    finished = run_now(world, UUID(str(started.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    assert finished["result"]["output_sha256_equal"] is True
    rerun_id = started.headers[REPORT_RUN_ID_HEADER]
    data = get(app, f"{REPORT_RUNS}/{rerun_id}/data", world.maya, {"limit": "200"})
    assert data.status_code == 200, data.text
    assert data.json()["items"] == rows
