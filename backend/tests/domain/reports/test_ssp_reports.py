"""SSP reports (SCREENS_B §5.6.4 RPT-19 to RPT-22; PRD §2.6, §2.8 WLD-X-23, J-02-AC-2, J-02-AC-6,
J-03-AC-2, BR-SSP-03; 03 REQ-SSP-006, REQ-SSP-011, REQ-SSP-012; BUILD_SPEC RPS-9).

Worlds, both built through the product's commands (``support.worlds``): ``ssp_h2_publication`` —
the tenant-wide book US-LIST with ``2026-H1`` (the PRD §2.6 entries; prepared by Maya, approved by
Priya) and ``2026-H2`` (a copy with AVM-PLAT-100 at 95,200.00 / 112,000.00 / 128,800.00; approved
by Priya, then Marcus) — and ``k_sf_ord_20417`` — the J-03 order ``SF-ORD-20417`` booked, activated
and computed under ``US-LIST 2026-H1``. Every report runs through ``POST /report-runs`` and its
``REPORT_RUN`` job, as ``test_balances_reports.py`` does; the frozen clock reads
2026-09-12T12:00:00Z.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.tables import obligation, obligation_version, ssp_entry
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import ssp_change_log as change_log
from erev_api.files.store import LocalFileStore
from erev_api.jobs.context import JobRuntime
from erev_api.main import create_app
from erev_api.problems import Problem
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.factories import (
    IMPLEMENTATION_PLUS,
    K02_EXTERNAL_ID,
    PLATFORM_100,
    SEAT_MONTH,
    K02World,
    activated_contract,
    booked_contract,
    computed,
    k02_seat_month_body,
    k02_world,
    range_entry,
)
from support.factories import approved_ssp_version as approved_version
from support.reference import approve, post
from support.worlds import (
    AVM_US,
    H1_LABEL,
    H1_METHODOLOGY,
    H2_LABEL,
    H2_METHODOLOGY,
    SF_ORD_20417_KEY,
    US_LIST,
    US_LIST_H1_ENTRIES,
    ReportWorld,
    SfOrderWorld,
    SspPublicationWorld,
    k_sf_ord_20417,
    report_run,
    ssp_h2_publication,
)

JUSTIFICATION: Final = "Negotiated under the second-half list; the order form cites it."
H1_NAME: Final = f"{US_LIST} {H1_LABEL}"
H2_NAME: Final = f"{US_LIST} {H2_LABEL}"
D = Decimal


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


@pytest.fixture
def publication(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> SspPublicationWorld:
    return ssp_h2_publication(app, keyring, clock, files)


@pytest.fixture
def order(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> SfOrderWorld:
    return k_sf_ord_20417(app, keyring, clock, files)


@pytest.fixture
def runtime(keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> JobRuntime:
    return JobRuntime(clock=clock, keyring=keyring, files=files)


@pytest.fixture
def k02(app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore) -> K02World:
    return k02_world(app, keyring, clock, files)


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    found = {str(row["row_key"]): row for row in rows}
    assert len(found) == len(rows)  # a row key occurs once
    return found


def test_version_diff_avm_plat_100(publication: SspPublicationWorld) -> None:
    """PRD J-02-AC-2: H1 against H2 — AVM-PLAT-100 low 85,000.00 → 95,200.00; mid 100,000.00 →
    112,000.00 (+12.0%); high 115,000.00 → 128,800.00; every other entry "Unchanged"."""
    run, rows = report_run(
        publication.report,
        "ssp_version_diff",
        {
            "ssp_book_version_id": publication.h2["id"],
            "against_version_id": publication.h1["id"],
            "only_changes": False,
        },
    )
    assert run["status"] == "SUCCEEDED"
    found = keyed(rows)
    platform = found["entry:AVM-PLAT-100::||||:USD"]
    assert platform["change"] == "Changed"
    assert (platform["product_code"], platform["currency"]) == ("AVM-PLAT-100", "USD")
    assert (platform["low_before"], platform["low_after"]) == ("85000.00", "95200.00")
    assert (platform["mid_before"], platform["mid_after"]) == ("100000.00", "112000.00")
    assert (platform["high_before"], platform["high_after"]) == ("115000.00", "128800.00")
    assert D(platform["mid_change_ratio"]) == D("0.12")  # +12.0%
    assert (platform["method_before"], platform["method_after"]) == ("observable", "observable")
    others = {key: row for key, row in found.items() if row["product_code"] != "AVM-PLAT-100"}
    assert {row["product_code"] for row in others.values()} == {
        str(entry["product_code"]) for entry in US_LIST_H1_ENTRIES
    } - {"AVM-PLAT-100"}
    assert len(others) == len(US_LIST_H1_ENTRIES) - 1 == 6
    for row in others.values():
        assert row["change"] == "Unchanged", row
        assert row["mid_change_ratio"] is None
        for name in ("method", "low", "mid", "high", "point"):
            assert row[f"{name}_before"] == row[f"{name}_after"], (row["product_code"], name)
    # the unchanged values are H1's own (PRD §2.6): a point, a range and a per-call rate
    enterprise = found["entry:AVM-PLAT-ENT::||||:USD"]
    assert (enterprise["point_after"], enterprise["mid_after"]) == ("132000.00", None)
    assert found["entry:AVM-API-CALL::||||:USD"]["point_after"] == "0.10"
    plus = found["entry:AVM-IMPL-PLUS::||||:USD"]
    assert (plus["method_after"], plus["low_after"], plus["mid_after"], plus["high_after"]) == (
        "cost_plus_margin",
        "18000.00",
        "20000.00",
        "22000.00",
    )
    assert run["control_totals"] == {"added": 0, "removed": 0, "changed": 1}

    # "Only changed entries" is the default (SCREENS_B RPT-20), against the prior approved version.
    default_run, changed = report_run(
        publication.report, "ssp_version_diff", {"ssp_book_version_id": publication.h2["id"]}
    )
    assert default_run["parameters"]["only_changes"] is True
    assert [row["row_key"] for row in changed] == ["entry:AVM-PLAT-100::||||:USD"]
    assert changed[0] == platform
    assert default_run["control_totals"] == run["control_totals"]


def test_change_log_row(publication: SspPublicationWorld, clock: FrozenClock) -> None:
    """PRD J-02-AC-6: the SSP change log lists ``2026-H2`` with preparer, approvers, effective
    dates and the entry diff; ``2026-H1`` shows its supersession."""
    run, rows = report_run(
        publication.report,
        "ssp_change_log",
        {"from_date": "2026-09-01", "to_date": "2026-09-30", "ssp_book_code": US_LIST},
    )
    assert run["status"] == "SUCCEEDED"
    found = keyed(rows)
    assert list(found) == [f"ssp:{US_LIST}:1", f"ssp:{US_LIST}:2"]
    h2 = found[f"ssp:{US_LIST}:2"]
    assert (h2["ssp_book_code"], h2["version_label"], h2["status"]) == (
        US_LIST,
        H2_LABEL,
        "APPROVED",
    )
    assert (h2["effective_from_date"], h2["effective_to_date"]) == ("2026-10-01", None)
    assert (h2["methodology_label"], h2["is_methodology_change"]) == (H2_METHODOLOGY, False)
    assert h2["entry_count"] == len(US_LIST_H1_ENTRIES) == 7
    assert (
        h2["diff_summary.added"],
        h2["diff_summary.removed"],
        h2["diff_summary.changed"],
    ) == (0, 0, 1)
    assert "maya" in h2["preparer"].lower()
    assert h2["approvers"] == "Priya, Marcus"  # J-02-AC-3: two decisions, priya then marcus
    assert h2["approved_at"] == publication.h2["published_at"]
    assert h2["superseded_by_label"] is None
    assert h2["study_file_name"] == "ssp-study-2026.pdf"
    h1 = found[f"ssp:{US_LIST}:1"]
    assert (h1["version_label"], h1["status"], h1["methodology_label"]) == (
        H1_LABEL,
        "APPROVED",
        H1_METHODOLOGY,
    )
    # BR-SSP-02: H1 ends on the day before H2 starts and names its successor
    assert (h1["effective_from_date"], h1["effective_to_date"]) == ("2026-01-01", "2026-09-30")
    assert h1["superseded_by_label"] == H2_LABEL
    assert (
        h1["diff_summary.added"],
        h1["diff_summary.removed"],
        h1["diff_summary.changed"],
    ) == (7, 0, 0)
    assert "maya" in h1["preparer"].lower() and h1["approvers"] == "Priya"
    assert run["control_totals"] == {
        "row_count": 2,
        "from_date": "2026-09-01",
        "to_date": "2026-09-30",
    }

    # REGISTER-CUTOFF-1: T-REF-29 keeps no row history, so an explicit historical read at a cutoff
    # before a version's last change (its approval, recorded on the database clock) is refused by
    # name; the live run above never refuses.
    with publication.report.place.uow() as uow, pytest.raises(Problem) as refused:
        change_log.build(
            uow,
            ReportParams(
                report_code=change_log.CODE,
                report_version=1,
                parameters={"from_date": "2026-09-01", "to_date": "2026-09-30"},
                entity_ids=(publication.report.entity_id,),
                known_at=clock.now(),
                historical=True,
            ),
        )
    (error,) = refused.value.errors
    assert error.field == "parameters.known_at"
    assert f"{US_LIST} {H1_LABEL}" in error.message and "keeps no row history" in error.message

    # a range before the book existed lists nothing; another book code lists nothing
    _, earlier = report_run(
        publication.report, "ssp_change_log", {"from_date": "2026-01-01", "to_date": "2026-08-31"}
    )
    assert earlier == []
    _, other = report_run(publication.report, "ssp_change_log", {"ssp_book_code": "DE-LIST"})
    assert other == []


def test_allocations_by_ssp_version_sf_ord_20417(order: SfOrderWorld) -> None:
    """WLD-X-23; PRD J-03-AC-2: one row per obligation with version ``US-LIST 2026-H1``, entry id,
    low, mid and high, in-range flag, selected SSP 96,000.00 and 22,000.00, exact weight and
    allocated 97,627.12 and 22,372.88."""
    run, rows = report_run(
        order.report,
        "allocations_by_ssp_version",
        {
            "entity_codes": [AVM_US],
            "book": "ASC606",
            "from_date": "2026-09-01",
            "to_date": "2026-09-30",
        },
    )
    assert run["status"] == "SUCCEEDED"
    found = keyed(rows)
    assert list(found) == [
        f"allocation:{SF_ORD_20417_KEY}:O1:1",
        f"allocation:{SF_ORD_20417_KEY}:O2:1",
        "TOTAL:USD",
    ]
    # the SSP entries of US-LIST 2026-H1 the allocation names (REQ-SSP-011 "value row id")
    entries = {
        str(row["code"]): str(row["id"])
        for row in order.report.place.rows(
            select(ssp_entry.c.id, obligation_version.c.product_code.label("code"))
            .select_from(
                ssp_entry.join(
                    obligation_version, obligation_version.c.ssp_entry_id == ssp_entry.c.id
                )
            )
            .where(ssp_entry.c.ssp_book_version_id == UUID(order.h1_version_id))
            .distinct()
        )
    }
    assert set(entries) == {PLATFORM_100, IMPLEMENTATION_PLUS}
    o1 = found[f"allocation:{SF_ORD_20417_KEY}:O1:1"]
    assert (o1["contract_external_id"], o1["obligation_key"], o1["product_code"]) == (
        SF_ORD_20417_KEY,
        "O1",
        PLATFORM_100,
    )
    assert (o1["allocation_date"], o1["cause"]) == ("2026-09-01", "Inception")
    assert (o1["ssp_version_label"], o1["ssp_entry_id"]) == (H1_NAME, entries[PLATFORM_100])
    assert (o1["ssp_method"], o1["currency"]) == ("observable", "USD")
    assert (o1["ssp_low"], o1["ssp_mid"], o1["ssp_high"]) == (
        usd("85000.00"),
        usd("100000.00"),
        usd("115000.00"),
    )
    assert (o1["stated_price"], o1["range_status"], o1["selected_ssp"]) == (
        usd("96000.00"),
        "INSIDE",
        usd("96000.00"),
    )
    o2 = found[f"allocation:{SF_ORD_20417_KEY}:O2:1"]
    assert (o2["obligation_key"], o2["product_code"], o2["cause"]) == (
        "O2",
        IMPLEMENTATION_PLUS,
        "Inception",
    )
    assert (o2["ssp_version_label"], o2["ssp_entry_id"]) == (
        H1_NAME,
        entries[IMPLEMENTATION_PLUS],
    )
    assert o2["ssp_method"] == "cost_plus_margin"
    assert (o2["ssp_low"], o2["ssp_mid"], o2["ssp_high"]) == (
        usd("18000.00"),
        usd("20000.00"),
        usd("22000.00"),
    )
    # 24,000.00 above the high bound: the nearest bound applies (POL-072)
    assert (o2["stated_price"], o2["range_status"], o2["selected_ssp"]) == (
        usd("24000.00"),
        "ABOVE",
        usd("22000.00"),
    )
    # exact weights: the relative SSP of 118,000.00 at the stored 18 places
    places = D(1).scaleb(-18)
    assert D(o1["allocation_weight"]) == (D(96000) / D(118000)).quantize(places)
    assert D(o2["allocation_weight"]) == (D(22000) / D(118000)).quantize(places)
    assert D(o1["allocation_weight"]) + D(o2["allocation_weight"]) == D(1)
    assert (o1["allocated_amount"], o2["allocated_amount"]) == (usd("97627.12"), usd("22372.88"))
    assert (o1["allocation_adjustment"], o2["allocation_adjustment"]) == (
        usd("1627.12"),
        usd("-1627.12"),
    )
    assert (o1["is_override"], o2["is_override"]) == (False, False)
    total = found["TOTAL:USD"]
    assert (total["stated_price"], total["allocated_amount"], total["allocation_adjustment"]) == (
        usd("120000.00"),
        usd("120000.00"),
        usd("0.00"),  # J-03-AC-1: the allocation adjustment totals 0.00
    )
    assert run["control_totals"] == {
        "row_count": 2,
        "stated_price_total": {"USD": "120000.00"},
        "allocated_amount_total": {"USD": "120000.00"},
        "allocation_adjustment_total": {"USD": "0.00"},
        "from_date": "2026-09-01",
        "to_date": "2026-09-30",
    }
    # the rows are the stored lineage of the latest obligation versions (REQ-SSP-011)
    stored = order.report.place.rows(
        select(
            obligation_version.c.obligation_key,
            obligation_version.c.ssp_entry_id,
            obligation_version.c.allocation_weight,
        ).where(
            obligation_version.c.contract_id == order.contract_id,
            obligation_version.c.book_code == "ASC606",
        )
    )
    assert {
        (row["obligation_key"], str(row["ssp_entry_id"]), row["allocation_weight"])
        for row in stored
    } == {
        ("O1", o1["ssp_entry_id"], D(o1["allocation_weight"])),
        ("O2", o2["ssp_entry_id"], D(o2["allocation_weight"])),
    }

    # the version filter and a range before the inception date
    _, by_version = report_run(
        order.report,
        "allocations_by_ssp_version",
        {"entity_codes": [AVM_US], "ssp_book_version_id": order.h1_version_id},
    )
    assert [row["row_key"] for row in by_version] == list(found)
    _, before = report_run(
        order.report,
        "allocations_by_ssp_version",
        {"entity_codes": [AVM_US], "from_date": "2026-01-01", "to_date": "2026-08-31"},
    )
    assert before == []


def test_override_listing(k02: K02World, runtime: JobRuntime, clock: FrozenClock) -> None:
    """REQ-SSP-006, BR-SSP-03: an approved SSP override lists obligation, pinned version,
    justification and approver; a requested override and a contract without one list nothing.
    World: ``support.factories.k02_world`` with K-02 activated and computed under ``US-LIST
    2026-H1``, then O1 pinned to ``US-LIST 2026-H2`` through ``request-ssp-override`` (the CTR-15
    flow; the J-03 order's labour-hours obligation carries no EAC version, which a repin boundary
    needs, S06-R-15)."""
    world = ReportWorld(
        place=k02.place,
        priya=k02.priya,
        marcus=k02.marcus,
        runtime=runtime,
        entity_id=k02.entity_id,
        contracts={},
    )
    maya = world.maya
    booked = activated_contract(
        k02.place, booked_contract(k02.place, k02_seat_month_body(k02.customer_id), activate=False)
    )
    contract_id, group_id = booked.contract["id"], booked.combination_group["id"]
    computed(k02.place, group_id)
    o1 = k02.place.scalar(
        select(obligation.c.id).where(
            obligation.c.contract_id == contract_id, obligation.c.obligation_key == "O1"
        )
    )
    _, none = report_run(world, "ssp_override_listing", {"entity_codes": [AVM_US]})
    assert none == []

    second_half = approved_version(
        world.app,
        maya,
        [k02.priya, k02.marcus],
        k02.book_id,
        label=H2_LABEL,
        effective_from="2026-10-01",
        entries=[range_entry(SEAT_MONTH, "95.00", "105.00", "115.00", value_basis="AMOUNT")],
    )
    clock.advance(timedelta(minutes=1))
    requested = post(
        world.app,
        f"/api/v1/obligations/{o1}/request-ssp-override",
        maya,
        {"ssp_book_version_id": second_half, "justification": JUSTIFICATION},
    )
    assert requested.status_code == 200, requested.text
    request_id = str(requested.json()["approval_request_id"])
    # requested, not approved: the obligation carries no override yet
    _, pending = report_run(world, "ssp_override_listing", {"entity_codes": [AVM_US]})
    assert pending == []

    clock.advance(timedelta(minutes=1))
    approved = approve(world.app, request_id, k02.priya)
    assert (approved.status_code, approved.json()["status"]) == (200, "APPROVED"), approved.text
    decided = approved.json()
    computed(k02.place, group_id)

    clock.advance(timedelta(minutes=1))
    run, rows = report_run(
        world,
        "ssp_override_listing",
        {"entity_codes": [AVM_US], "from_date": "2026-09-01", "to_date": "2026-09-30"},
    )
    assert run["status"] == "SUCCEEDED"
    (row,) = rows
    assert row["row_key"] == f"override:{K02_EXTERNAL_ID}:O1:{decided['request_no']}"
    assert (row["contract_external_id"], row["obligation_key"], row["product_code"]) == (
        K02_EXTERNAL_ID,
        "O1",
        SEAT_MONTH,
    )
    assert (row["default_version_label"], row["override_version_label"]) == (H1_NAME, H2_NAME)
    assert row["justification"] == JUSTIFICATION
    assert "lena" in row["requested_by"].lower()  # the world's author (Maya) signs in as lena@…
    assert row["approved_by"] == "Priya"
    assert row["approved_at"] == decided["decided_at"]
    assert run["control_totals"] == {
        "row_count": 1,
        "from_date": "2026-09-01",
        "to_date": "2026-09-30",
    }

    # S06-R-26: the override corrects the inception allocation — the allocation report shows the
    # one inception event from the corrected lineage, flagged, under the pinned version
    _, allocations = report_run(
        world,
        "allocations_by_ssp_version",
        {"entity_codes": [AVM_US], "from_date": "2026-01-01", "to_date": "2026-09-30"},
    )
    (inception, total) = allocations
    assert total["row_key"] == "TOTAL:USD"
    assert (inception["cause"], inception["allocation_date"]) == ("Inception", "2026-01-01")
    assert (inception["ssp_version_label"], inception["is_override"]) == (H2_NAME, True)
    latest = k02.place.scalar(
        select(func.max(obligation_version.c.version_no)).where(
            obligation_version.c.obligation_id == o1, obligation_version.c.book_code == "ASC606"
        )
    )
    assert inception["row_key"] == f"allocation:{K02_EXTERNAL_ID}:O1:{latest}" and latest > 1
    # a range that excludes the approval day lists nothing
    _, outside = report_run(
        world,
        "ssp_override_listing",
        {"entity_codes": [AVM_US], "from_date": "2026-10-01", "to_date": "2026-10-31"},
    )
    assert outside == []
