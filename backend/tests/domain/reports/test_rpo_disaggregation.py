"""Remaining performance obligations, RPO rollforward, disaggregation and disclosure elections
(SCREENS_B §5.6.1 RPT-06 to RPT-08, §0.5 RV-12; 04 §16.9 API-S-RpoReportData, table 10-T;
ENGINE_SPEC_B §15.2.3, §15.2.5; POLICIES POL-190 to POL-203; D-76; 03 REQ-RPT-003, REQ-RPT-009 to
REQ-RPT-011, REQ-RPT-025, REQ-RPT-026, REQ-REF-016; CTL-027, CTL-028, CTL-030; BUILD_SPEC RPS-4).

Worlds: ``support.worlds.report_world`` (PRD §2.6, §2.7) at the frozen clock 2026-09-12T12:00:00Z
with FY2026-P01 to P09 of AVM-US open; K-01 ``SF-ORD-10001`` and K-02 ``SF-ORD-10002`` booked,
activated, billed and computed once. Registry versions are published as the configuration commands
publish them (``support.rows.publish_registry_version``); a DRAFT version is only inserted.

R-RC-1 (spec questions under XR-14): ``test_rpo_k02_bands`` and
``test_ctl_030_rpo_rollforward_ties`` run K-02 without modification CR-MARROWBY-2026-09 (CTR-17
post-rc, L6-3-Q-18). The figures follow from WLD-K-02 and WLD-X-05 without it: 240,000.00 over 730
days, cumulatively rounded; revenue to 31 Aug 2026 79,890.41 and to 30 Sep 2026 89,753.42
(September 9,863.01); RPO at 31 Aug 2026 160,109.59 and at 30 Sep 2026 150,246.58; revenue to
30 Sep 2027 209,753.42 (638 days), so within 12 months 120,000.00 and 13 to 24 months 30,246.58.
``test_rpo_k09_total`` moves post-rc with CTR-14.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.auth.keyring import KeyRing
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import contract, obligation_version, schedule_line
from erev_api.domain.reports import elections, tie_outs
from erev_api.domain.reports.builders.rpo import NO_EXEMPTIONS, ROLLFORWARD_LINES, bands_of
from erev_api.enums import ConfigStatus, RegistryCategory, RegistryScope
from erev_api.files.store import LocalFileStore
from erev_api.main import create_app
from fastapi import FastAPI
from sqlalchemy import func, select
from support.db import TestDatabase
from support.reference import get, post
from support.rows import insert_registry_version, publish_registry_version
from support.worlds import (
    AVM_US,
    JOURNAL_RUNS,
    K01,
    K02,
    SEPTEMBER_2026,
    ReportWorld,
    journal_run,
    k01_pellworth,
    k02_marrowby,
    recalculated_journal,
    report_run,
    report_world,
    revenue_without_contributors,
    run_now,
)

CELL: Final = "/api/v1/explain/report-runs/{run_id}/cell"
AT_SEPTEMBER: Final = {"entity_codes": [AVM_US], "book": "ASC606", "period_key": SEPTEMBER_2026}
SEPTEMBER: Final = {
    "entity_codes": [AVM_US],
    "book": "ASC606",
    "from_period_key": SEPTEMBER_2026,
    "to_period_key": SEPTEMBER_2026,
}
ONE_YEAR: Final = "rpo.exemption_original_duration_one_year"
ONE_YEAR_DESCRIPTION: Final = (
    "consideration of a contract with an original expected duration of one year or less "
    "(606-10-50-14(a))"
)


@pytest.fixture
def app(committed_db: TestDatabase, app_settings: Settings, clock: FrozenClock) -> FastAPI:
    return create_app(app_settings, clock=clock)


@pytest.fixture
def files(app_settings: Settings) -> LocalFileStore:
    return LocalFileStore(app_settings.file_root)


def usd(amount: str) -> dict[str, str]:
    return {"amount": amount, "currency": "USD"}


def keyed(rows: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {str(row["row_key"]): row for row in rows}


def tie(run: Mapping[str, Any], code: str) -> Mapping[str, Any]:
    (found,) = [item for item in run["tie_out_results"] if item["code"] == code]
    return found


def publish(world: ReportWorld, category: RegistryCategory, values: Mapping[str, Any]) -> None:
    """Publish an entity version at the world's clock; a successor needs a later clock, because
    the superseded version ends when it starts (``ck_registry_version__effective_range``)."""
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        publish_registry_version(
            session,
            tenant_id=world.tenant_id,
            category=category,
            scope=RegistryScope.ENTITY,
            entity_id=world.entity_id,
            values=values,
            at=world.place.clock.now(),
        )


@pytest.mark.slow
def test_rpo_k02_bands(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k02_marrowby(app, keyring, clock, files)
    run, rows = report_run(world, "rpo", AT_SEPTEMBER)
    row = keyed(rows)[f"contract:{K02}"]
    assert (row["section"], row["contract_external_id"], row["entity_code"]) == (1, K02, AVM_US)
    assert row["total"] == usd("150246.58")
    bands = (row["within_12_months"], row["months_13_to_24"], row["after_24_months"])
    assert bands == (usd("120000.00"), usd("30246.58"), usd("0.00"))
    assert sum(Decimal(item["amount"]) for item in bands) == Decimal(row["total"]["amount"])
    assert (row["current"], row["noncurrent"]) == (usd("120000.00"), usd("30246.58"))
    assert run["control_totals"]["as_of"] == "2026-09-30"
    assert run["control_totals"]["bands"] == [
        {"index": 0, "key": "within_12_months", "from_month": 1, "to_month": 12},
        {"index": 1, "key": "months_13_to_24", "from_month": 13, "to_month": 24},
        {"index": 2, "key": "after_24_months", "from_month": 25, "to_month": None},
    ]
    assert run["control_totals"]["total"] == {"USD": "150246.58"}
    assert tie(run, tie_outs.TO_RPO_ROLLFORWARD_EQ_RPO) == {
        "code": "TO_RPO_ROLLFORWARD_EQ_RPO",
        "result": "PASS",
        "expected": [usd("150246.58")],
        "actual": [usd("150246.58")],
        "difference": [usd("0.00")],
    }
    explained = get(
        world.app,
        CELL.format(run_id=run["id"]),
        world.maya,
        {"row_key": f"contract:{K02}", "column_key": "within_12_months"},
    )
    assert explained.status_code == 200, explained.text
    body = explained.json()
    assert body["value"] == usd("120000.00")
    items = body["contributors"]["items"]
    assert {item["object_type"] for item in items} == {"schedule_line"}
    assert len(items) == 12  # October 2026 to September 2027
    assert sum(Decimal(item["value"]["amount"]) for item in items) == Decimal("120000.00")


@pytest.mark.slow
def test_custom_time_bands(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    assert [band.key for band in bands_of([6, 12])] == [
        "within_6_months",
        "months_7_to_12",
        "after_12_months",
    ]
    assert [(band.from_month, band.to_month) for band in bands_of([12, 24, 36])] == [
        (1, 12),
        (13, 24),
        (25, 36),
        (37, None),
    ]
    world = k02_marrowby(app, keyring, clock, files)
    run, rows = report_run(world, "rpo", {**AT_SEPTEMBER, "time_bands": [6, 12]})
    assert [band["key"] for band in run["control_totals"]["bands"]] == [
        "within_6_months",
        "months_7_to_12",
        "after_12_months",
    ]
    row = keyed(rows)[f"contract:{K02}"]
    # add_months(30 Sep 2026, 6) = 30 Mar 2027, so March 2027 ends in the second band (S15-R-10).
    assert (row["within_6_months"], row["months_7_to_12"], row["after_12_months"]) == (
        usd("49643.84"),
        usd("70356.16"),
        usd("30246.58"),
    )
    assert row["total"] == usd("150246.58")


@pytest.mark.slow
@pytest.mark.control("CTL-027")
def test_ctl_027_rpo_derived_and_exemption_needs_approved_flag(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = report_world(app, keyring, clock, files, contracts=(K01, K02))
    rows_of = world.place.rows
    for external_id, expected in ((K02, "150246.58"), (K01, "29944.11")):
        (o1,) = rows_of(
            select(
                obligation_version.c.contract_version_id,
                obligation_version.c.obligation_id,
                obligation_version.c.allocated_amount,
            )
            .select_from(
                obligation_version.join(contract, contract.c.id == obligation_version.c.contract_id)
            )
            .where(
                contract.c.external_id == external_id, obligation_version.c.obligation_key == "O1"
            )
        )
        revenue = world.place.scalar(
            select(func.sum(schedule_line.c.amount)).where(
                schedule_line.c.contract_version_id == o1["contract_version_id"],
                schedule_line.c.subject_id == o1["obligation_id"],
                schedule_line.c.period_end_date <= date(2026, 9, 30),
            )
        )
        derived = Decimal(o1["allocated_amount"]) - Decimal(revenue)
        assert format(derived.quantize(Decimal("0.01")), "f") == expected
    run, rows = report_run(world, "rpo", AT_SEPTEMBER)
    found = keyed(rows)
    assert (found[f"contract:{K02}"]["total"], found[f"contract:{K01}"]["total"]) == (
        usd("150246.58"),
        usd("29944.11"),
    )
    assert [row for row in rows if row["section"] == 2] == []
    assert run["control_totals"]["notes"] == [
        {"entity_code": AVM_US, "section": 2, "note": NO_EXEMPTIONS.format(entity=AVM_US)}
    ]
    # POL-197 APPLY in a DRAFT registry version is not in force (PRD J-15-AC-4).
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")
    with tenant_session(context) as session:
        insert_registry_version(
            session,
            tenant_id=world.tenant_id,
            category=RegistryCategory.PRACTICAL_EXPEDIENT,
            scope=RegistryScope.ENTITY,
            entity_id=world.entity_id,
            values={ONE_YEAR: "APPLY"},
            status=ConfigStatus.DRAFT,
        )
    _, rows = report_run(world, "rpo", AT_SEPTEMBER)
    assert [row for row in rows if row["section"] == 2] == []
    assert f"contract:{K01}" in keyed(rows)
    # Approved and published: K-01 (1 Jan 2026 to 31 Dec 2026) moves to section 2 with its 50-15
    # descriptors. POL-199 and POL-200 exclude no fixed consideration (606-10-50-14B).
    publish(
        world,
        RegistryCategory.PRACTICAL_EXPEDIENT,
        {
            ONE_YEAR: "APPLY",
            "rpo.exemption_royalty_vc": "APPLY",
            "rpo.exemption_vc_wholly_unsatisfied": "APPLY",
        },
    )
    run, rows = report_run(world, "rpo", AT_SEPTEMBER)
    found = keyed(rows)
    assert f"contract:{K01}" not in found
    assert found[f"contract:{K02}"]["total"] == usd("150246.58")
    exempt = [row for row in rows if row["section"] == 2]
    assert [
        (
            row["row_key"],
            row["contract_external_id"],
            row["obligation_key"],
            row["expedient"],
            row["expedient_label"],
            row["nature"],
            row["remaining_duration_months"],
            row["excluded_amount"],
            row["excluded_descriptor"],
        )
        for row in exempt
    ] == [
        (
            f"exempt:{K01}:O1:POL-197",
            K01,
            "O1",
            "POL-197",
            "Original expected duration of one year or less",
            "Platform, enterprise tier",
            3,
            usd("29944.11"),
            ONE_YEAR_DESCRIPTION,
        )
    ]
    assert (run["control_totals"]["total"], run["control_totals"]["excluded_total"]) == (
        {"USD": "150246.58"},
        {"USD": "29944.11"},
    )
    assert tie(run, tie_outs.TO_RPO_ROLLFORWARD_EQ_RPO)["result"] == "PASS"


@pytest.mark.slow
@pytest.mark.control("CTL-030")
def test_ctl_030_rpo_rollforward_ties(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k02_marrowby(app, keyring, clock, files)
    run, rows = report_run(world, "rpo_rollforward", SEPTEMBER)
    found = keyed(rows)
    assert [(line, found[line]["rpo"]["amount"]) for line in ROLLFORWARD_LINES] == [
        ("OPENING", "160109.59"),
        ("NEW_CONTRACTS", "0.00"),
        ("MODIFICATIONS", "0.00"),  # +60,000.00 waits for CR-MARROWBY-2026-09 (R-RC-1)
        ("VC_ESTIMATE_CHANGES", "0.00"),
        ("LATE_EVENTS", "0.00"),  # the row of S15-R-12 rev 1.161 (supervisor ruling R-121 (g))
        ("REVENUE", "-9863.01"),
        ("CANCELLATIONS", "0.00"),
        ("FX", "0.00"),
        ("UNEXPLAINED", "0.00"),
        ("CLOSING", "150246.58"),
    ]
    assert found["UNEXPLAINED"]["line_label"] == "Unexplained difference"
    by_contract = found[f"contract:{K02}"]
    assert (by_contract["section"], by_contract["opening"], by_contract["closing"]) == (
        2,
        usd("160109.59"),
        usd("150246.58"),
    )
    assert tie(run, tie_outs.TO_RPO_ROLLFORWARD_EQ_RPO) == {
        "code": "TO_RPO_ROLLFORWARD_EQ_RPO",
        "result": "PASS",
        "expected": [usd("150246.58")],
        "actual": [usd("150246.58")],
        "difference": [usd("0.00")],
    }
    assert tie(run, tie_outs.TO_ROLLFORWARD_BALANCES)["result"] == "PASS"
    assert run["control_totals"]["unexplained"] == {"USD": "0.00"}
    year, rows = report_run(
        world,
        "rpo_rollforward",
        {**SEPTEMBER, "from_period_key": "FY2026-P01", "to_period_key": SEPTEMBER_2026},
    )
    found = keyed(rows)
    assert [
        (line, found[line]["rpo"]["amount"])
        for line in ("OPENING", "NEW_CONTRACTS", "REVENUE", "UNEXPLAINED", "CLOSING")
    ] == [
        ("OPENING", "0.00"),
        ("NEW_CONTRACTS", "240000.00"),
        ("REVENUE", "-89753.42"),
        ("UNEXPLAINED", "0.00"),
        ("CLOSING", "150246.58"),
    ]
    assert tie(year, tie_outs.TO_ROLLFORWARD_BALANCES)["result"] == "PASS"


@pytest.mark.slow
@pytest.mark.control("CTL-028")
def test_ctl_028_disaggregation_ties_to_journal_revenue(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k01_pellworth(app, keyring, clock, files)
    first = journal_run(world)
    parameters = {**SEPTEMBER, "include_timing": True}
    run, rows = report_run(world, "disaggregation", parameters)
    row = keyed(rows)["SUBSCRIPTION:OVER_TIME"]
    assert (
        row["dimension_value_label"],
        row["timing"],
        row["period:FY2026-P09"],
        row["total"],
    ) == ("SUBSCRIPTION", "Over time", usd("9764.38"), usd("9764.38"))
    assert tie(run, tie_outs.TO_DISAGGREGATION_EQ_JE_REVENUE) == {
        "code": "TO_DISAGGREGATION_EQ_JE_REVENUE",
        "result": "PASS",
        "expected": [usd("9764.38")],
        "actual": [usd("9764.38")],
        "difference": [usd("0.00")],
    }
    revenue_without_contributors(world, "250.00")
    second = recalculated_journal(world, first)
    assert second["totals"]["credit_functional"] == usd("10014.38")
    run, _ = report_run(world, "disaggregation", parameters)
    assert tie(run, tie_outs.TO_DISAGGREGATION_EQ_JE_REVENUE) == {
        "code": "TO_DISAGGREGATION_EQ_JE_REVENUE",
        "result": "FAIL",
        "expected": [usd("10014.38")],
        "actual": [usd("9764.38")],
        "difference": [usd("-250.00")],
    }


@pytest.mark.slow
def test_disaggregation_timing_default_and_posting_mode_revenue(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    """D-87 L6-3-Q-29: a run without ``include_timing`` stores true and groups by timing.
    Supervisor ruling R-52 (a), which supersedes D-87 L6-3-Q-32: the revenue journal total sums
    every non-cancelled run whatever its mode, and a run requested in the mode that is not the
    POL-005 posting mode is counted once. Until revision 0085 (security finding SC-7) a DELTA run
    journalised the same seals as the GROSS run beside it and this test asserted that the DELTA run
    was left out; now a seal is journalised by one run only, so the DELTA run that journalises
    September here is the period's revenue journal, and a GROSS run after it would add nothing:
    since item JRN-EMPTY-RUN-1 it is refused by name (PRD ERR-96), where until then a GROSS run
    without a line was calculated."""
    world = k01_pellworth(app, keyring, clock, files)
    started = post(
        world.app,
        JOURNAL_RUNS,
        world.maya,
        {"entity_code": AVM_US, "period_key": SEPTEMBER_2026, "mode": "DELTA"},
    )
    assert started.status_code == 202, started.text
    finished = run_now(world, UUID(str(started.json()["id"])))
    assert finished["state"] == "SUCCEEDED", finished
    passed = {
        "code": "TO_DISAGGREGATION_EQ_JE_REVENUE",
        "result": "PASS",
        "expected": [usd("9764.38")],
        "actual": [usd("9764.38")],
        "difference": [usd("0.00")],
    }
    run, rows = report_run(world, "disaggregation", SEPTEMBER)
    assert run["parameters"]["include_timing"] is True
    assert keyed(rows)["SUBSCRIPTION:OVER_TIME"]["total"] == usd("9764.38")
    # The only run of the period is a DELTA run in a GROSS-policy workspace: its revenue counts.
    assert tie(run, tie_outs.TO_DISAGGREGATION_EQ_JE_REVENUE) == passed
    # The POL-005 run after it would start where the DELTA run ended (DB-16) and journalise
    # nothing, so none is made: the total is the same 9,764.38 — once, from the run that covered
    # the seals.
    refused = post(
        world.app, JOURNAL_RUNS, world.maya, {"entity_code": AVM_US, "period_key": SEPTEMBER_2026}
    )
    assert refused.status_code == 409, refused.text  # until item JRN-EMPTY-RUN-1: 202
    assert refused.json()["errors"][0]["rule_id"] == "RUN_NOTHING_PENDING"
    again, _ = report_run(world, "disaggregation", SEPTEMBER)
    assert tie(again, tie_outs.TO_DISAGGREGATION_EQ_JE_REVENUE) == passed


@pytest.mark.slow
def test_built_in_tie_outs_present(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k01_pellworth(app, keyring, clock, files)
    required = {
        "revenue_waterfall": "TO_WATERFALL_EQ_JE_REVENUE",
        "contract_balances": "TO_ROLLFORWARD_EQ_GL",
        "rpo_rollforward": "TO_RPO_ROLLFORWARD_EQ_RPO",
        "disaggregation": "TO_DISAGGREGATION_EQ_JE_REVENUE",
    }
    for code in (
        "revenue_waterfall",
        "contract_balances",
        "contract_balance_rollforward",
        "rpo",
        "rpo_rollforward",
        "disaggregation",
    ):
        definition = get(world.app, f"/api/v1/report-definitions/{code}", world.maya)
        assert definition.status_code == 200, definition.text
        declared = set(definition.json()["tie_outs"])
        parameters = AT_SEPTEMBER if code in ("contract_balances", "rpo") else SEPTEMBER
        run, _ = report_run(world, code, parameters)
        computed = {item["code"] for item in run["tie_out_results"]}
        assert computed == declared, code
        if code in required:
            assert required[code] in computed, code


@pytest.mark.slow
def test_nonpublic_elections_suppress_sections(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = report_world(app, keyring, clock, files, contracts=(K01, K02))
    publish(
        world,
        RegistryCategory.DISCLOSURE_ELECTION,
        {"entity.reporting_type": "NONPUBLIC", elections.DISAGGREGATION_RELIEF: "ELECT"},
    )
    run, rows = report_run(world, "disaggregation", {**SEPTEMBER, "include_timing": True})
    assert [row["row_key"] for row in rows] == ["timing:OVER_TIME", "TOTAL:USD"]
    timing = rows[0]
    assert (timing["dimension_value_label"], timing["timing"], timing["total"]) == (
        None,
        "Over time",
        usd("19627.39"),
    )
    assert run["control_totals"]["notes"] == [
        {
            "entity_code": AVM_US,
            "section": 1,
            "registry_key": elections.DISAGGREGATION_RELIEF,
            "note": "Omitted under the nonpublic disaggregation relief election.",
        }
    ]
    clock.advance(timedelta(minutes=1))
    publish(
        world,
        RegistryCategory.DISCLOSURE_ELECTION,
        {
            "entity.reporting_type": "NONPUBLIC",
            elections.DISAGGREGATION_RELIEF: "ELECT",
            elections.RPO_RELIEF: "ELECT",
        },
    )
    run, rows = report_run(world, "rpo", AT_SEPTEMBER)
    assert rows == []
    assert run["control_totals"]["notes"] == [
        {
            "entity_code": AVM_US,
            "section": section,
            "registry_key": elections.RPO_RELIEF,
            "note": "Omitted under the nonpublic RPO relief election.",
        }
        for section in (1, 2)
    ]
    # The RPO dataset stays exportable to holders of report.export.
    exported, _ = report_run(world, "rpo", AT_SEPTEMBER, output_format="CSV")
    output = get(world.app, exported["output"]["href"], world.maya)
    assert output.status_code == 200, output.text
    text = output.content.decode("utf-8")
    assert K01 in text and K02 in text
    assert run["control_totals"]["total"] == {"USD": "180190.69"}


@pytest.mark.slow
def test_interim_pack_flag(
    app: FastAPI, keyring: KeyRing, clock: FrozenClock, files: LocalFileStore
) -> None:
    world = k01_pellworth(app, keyring, clock, files)
    context = DbContext(tenant_id=world.tenant_id, user_id=None, entity_scope="*")

    def pack() -> dict[str, Any]:
        with tenant_session(context, read_only=True) as session:
            return elections.quarterly_pack_parameters(
                session, entity_id=world.entity_id, book_code="ASC606", known_at=clock.now()
            )

    public = pack()
    assert (public["reporting_type"], public["interim_revenue_pack"]) == ("PBE", "TOPIC_270_LIST")
    assert public["required_reports"] == [
        "disaggregation",
        "contract_balances",
        "revenue_from_prior_period_obligations",
        "rpo",
    ]
    assert public["omitted_sections"] == []
    publish(
        world,
        RegistryCategory.DISCLOSURE_ELECTION,
        {
            "entity.reporting_type": "NONPUBLIC",
            elections.RPO_RELIEF: "ELECT",
            elections.INTERIM_PACK: "TOPIC_270_LIST",
        },
    )
    nonpublic = pack()
    assert nonpublic["required_reports"] == [
        "disaggregation",
        "contract_balances",
        "revenue_from_prior_period_obligations",
    ]
    assert nonpublic["omitted_sections"] == [
        {
            "report_code": "rpo",
            "section": 1,
            "registry_key": elections.RPO_RELIEF,
            "note": "Omitted under the nonpublic RPO relief election.",
        }
    ]
