"""RPT-28 to RPT-30 builders — CPU witnesses (BUILD_SPEC RPS-11; SCREENS_B §5.6.2). The
specification grids are parsed from SCREENS_B, so a specification edit or a builder column drift
fails here; the row shaping is proven on pure inputs. The acceptance over worlds built through the
product's commands is ``tests/domain/reports/test_registers_judgement.py`` (database). RPT-31
``loss_provision_register`` has no builder: its projection and loss-test modification correction
remain outstanding.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from erev_api.db import tables
from erev_api.domain.reports import framework
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import estimate_change_listing as estimates
from erev_api.domain.reports.builders import judgement_register as judgements
from erev_api.domain.reports.builders import scope_exclusion_register as exclusions
from erev_api.domain.reports.catalogue import DEFINITIONS_BY_CODE
from erev_api.enums import EstimateKind, EstimateMethod, JudgementStatus, JudgementTopic, ScopeFlag
from erev_api.problems import Problem
from support import report_specs

MAYA: UUID = UUID("00000000-0000-4000-8000-00000000000a")
PRIYA: UUID = UUID("00000000-0000-4000-8000-00000000000b")
NAMES = {MAYA: "Maya Chen", PRIYA: "Priya Raman"}
AT: datetime = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
MODULES = ((28, judgements), (29, estimates), (30, exclusions))


def _id(number: int) -> UUID:
    return UUID(int=number)


# --- specification and registration ---------------------------------------------------------------


@pytest.mark.parametrize(("number", "module"), MODULES)
def test_columns_are_the_specification_grid(number: int, module: Any) -> None:
    """SCREENS_B §5.6.2: the builder's columns are the grid's fields in its order; RPT-29 carries
    the preparer and RPT-30 the judgement's rationale the grids gained in rev 1.25."""
    keys = [column.key for column in module.COLUMNS]
    assert keys == report_specs.fields(number, module.CODE)
    assert len(set(keys)) == len(keys) and "row_key" not in keys
    headers = {column.key: column.header for column in module.COLUMNS}
    for header, names in report_specs.grid(number, module.CODE):
        if len(names) == 1:
            assert headers[names[0]] == header, names


@pytest.mark.parametrize(("number", "module"), MODULES)
def test_registration_and_catalogue(number: int, module: Any) -> None:
    assert framework.BUILDERS[module.CODE] is module.build
    contract = framework.SOURCE_CONTRACTS[module.CODE]
    assert contract.strategy == "open" and len(contract.open) == 1
    assert f"RPT-{number}" in contract.open[0]
    definition = DEFINITIONS_BY_CODE[module.CODE]
    section = report_specs.section(number, module.CODE)
    assert f"| Kind, formats | `{definition.kind}`;" in section
    assert f"`row_key` `{module.ROW_KEY_PREFIX}" in section


def test_specification_literals_and_the_unbuilt_loss_register() -> None:
    section = report_specs.section(29, estimates.CODE)
    for literal in (estimates.CONSTRAINED, estimates.EXPECTED_TOTAL, estimates.RATE):
        assert f'"{literal}"' in section
    assert "`estimate:<contract external id>:<element code>:<version no>`" in section
    assert framework.PARAMETER_DEFAULTS[estimates.CODE] == {"currency_view": "transaction"}
    assert framework.PARAMETER_DEFAULTS[exclusions.CODE] == {"currency_view": "transaction"}
    assert '"All books"' in report_specs.section(28, judgements.CODE)
    assert {column.key: column for column in judgements.COLUMNS}["book"].empty_text == "All books"
    # the enumerations the registers print are 04's (E-09, E-10, E-56, E-57, E-77)
    assert EstimateKind.EAC.value == "EAC" and EstimateMethod.COST_BUILDUP.value == "COST_BUILDUP"
    assert JudgementTopic.ESTIMATE_VS_ERROR.value == "ESTIMATE_VS_ERROR"
    assert exclusions.LEASE == ScopeFlag.LEASE_842.value
    # RPT-31: T-CON-17 is persisted; the report projection and calculation fix remain open;
    # this pin flips when CTR-14 lands and the register can be built on its source
    assert "loss_provision_register" in DEFINITIONS_BY_CODE
    assert (
        "loss_provision_version"
        in DEFINITIONS_BY_CODE["loss_provision_register"].ipe_logic["source_tables"]
    )
    assert hasattr(tables, "loss_provision_version")
    assert "loss_provision_register" not in framework.BUILDERS


# --- RPT-28 -----------------------------------------------------------------------------------


def test_judgement_rows_in_number_order() -> None:
    reviewed = judgements.Source(
        judgement_no="JDG-000002",
        topic="CONSTRAINT",
        subject_type="contract",
        subject_label="PRJ-CB-2026-01",
        contract_external_id="PRJ-CB-2026-01",
        book=None,
        conclusion="No significant reversal expected.",
        codification_refs=("606-10-32-11", "606-10-32-12"),
        created_by=(MAYA, "USER"),
        reviewer_id=PRIYA,
        status=JudgementStatus.REVIEWED.value,
        reviewed_at=AT,
        supersedes_no="JDG-000001",
    )
    waiting = judgements.Source(
        judgement_no="JDG-000001",
        topic="PRINCIPAL_AGENT",
        subject_type="product",
        subject_label="BG-AVM-0023",
        contract_external_id=None,
        book="ASC606",
        conclusion="Principal.",
        codification_refs=(),
        created_by=(None, "SYSTEM"),
        reviewer_id=None,
        status=JudgementStatus.SUBMITTED.value,
        reviewed_at=None,
        supersedes_no=None,
    )
    rows, totals = judgements.dataset_rows([reviewed, waiting], NAMES)
    assert [row["row_key"] for row in rows] == ["judgement:JDG-000001", "judgement:JDG-000002"]
    first, second = rows
    assert (first["created_by"], first["reviewer"], first["reviewed_at"]) == ("System", None, None)
    assert (first["book"], first["contract_external_id"], first["subject_label"]) == (
        "ASC606",
        None,
        "BG-AVM-0023",
    )
    assert (second["created_by"], second["reviewer"], second["supersedes_no"]) == (
        "Maya Chen",
        "Priya Raman",
        "JDG-000001",
    )
    assert (second["book"], second["codification_refs"]) == (
        None,
        ("606-10-32-11", "606-10-32-12"),
    )
    assert totals == {"row_count": 2}


# --- RPT-29 -----------------------------------------------------------------------------------


def _version(**values: Any) -> dict[str, Any]:
    row: dict[str, Any] = {"constrained_amount": None, "expected_total_amount": None, "rate": None}
    return row | values


def test_measure_follows_the_populated_column() -> None:
    rebate = estimates.measure_of(
        _version(constrained_amount=Decimal("5750.0000")),
        _version(constrained_amount=Decimal("0.0000")),
        currency="EUR",
    )
    assert rebate == estimates.Measure("Constrained amount", "EUR", "0.00", "5750.00")
    eac = estimates.measure_of(
        _version(expected_total_amount=Decimal("820000")),
        _version(expected_total_amount=Decimal("700000")),
        currency="USD",
    )
    assert eac == estimates.Measure("Expected total", "USD", "700000.00", "820000.00")
    yen = estimates.measure_of(
        _version(expected_total_amount=Decimal("1200")), None, currency="JPY"
    )
    assert yen == estimates.Measure("Expected total", "JPY", None, "1200")  # no minor unit
    rate = estimates.measure_of(
        _version(rate=Decimal("0.050000000000000000")), _version(rate=None), currency="USD"
    )
    assert rate == estimates.Measure("Rate", None, None, "0.05")  # a ratio, no currency
    assert estimates.measure_of(_version(), None, currency="USD") == estimates.Measure(
        None, None, None, None
    )
    assert estimates.version_pair(2, 1) == "v1 → v2"
    assert estimates.version_pair(3, 1) == "v1 → v3"  # a rejected version lies between
    assert estimates.version_pair(1, None) == "v1"


def test_effects_attribute_a_contract_version_to_its_one_boundary_owner() -> None:
    eac_v2, bonus_v2 = _id(2), _id(3)
    eac_event, bonus_event, amendment, costs = _id(11), _id(12), _id(13), _id(14)
    boundaries = {eac_event: eac_v2, bonus_event: bonus_v2, amendment: None}
    versions = [
        (_id(101), [eac_event], Decimal("-87804.88")),
        (_id(102), [bonus_event, costs], Decimal("102439.03")),  # a cost event is no boundary
        (_id(103), [amendment], Decimal("91463.41")),  # the modification's own: not an estimate's
        (_id(104), [eac_event], Decimal("-0.12")),  # a second book-keeping version of the event
    ]
    assert estimates.attributed_effects(versions, boundaries) == {
        eac_v2: Decimal("-87804.88") + Decimal("-0.12"),
        bonus_v2: Decimal("102439.03"),
    }
    # a catch-up shared with another estimate version or a modification is not apportioned
    joint = [
        (_id(105), [eac_event, bonus_event], Decimal("14634.15")),
        (_id(106), [eac_event, amendment], Decimal("91463.41")),
        (_id(107), [costs], Decimal("0")),
    ]
    assert estimates.attributed_effects(joint, boundaries) == {}


def _estimate(**values: Any) -> estimates.Source:
    source: dict[str, Any] = {
        "element_code": "EAC",
        "estimate_kind": "EAC",
        "contract_external_id": "PRJ-CB-2026-01",
        "obligation_key": "O1",
        "version_no": 3,
        "previous_version_no": 2,
        "effective_date": date(2026, 9, 30),
        "method": "COST_BUILDUP",
        "no_change_attestation": False,
        "measure": estimates.Measure("Expected total", "USD", "820000.00", "850000.00"),
        "currency": "USD",
        "functional_currency": "USD",
        "pnl_effect": Decimal("-29169.29"),
        "preparer": (MAYA, "USER"),
        "approvers": ((PRIYA, "USER"),),
        "approved_at": AT,
        "attachment_count": 1,
    }
    return estimates.Source(**(source | values))


def test_estimate_rows_totals_and_empty_effect() -> None:
    rebate = _estimate(
        element_code="REBATE-DR-01",
        estimate_kind="VARIABLE_CONSIDERATION",
        contract_external_id="NS-SO-DE-5002",
        obligation_key=None,
        version_no=2,
        previous_version_no=1,
        method="MOST_LIKELY_AMOUNT",
        measure=estimates.Measure("Constrained amount", "EUR", "0.00", "5750.00"),
        currency="EUR",
        functional_currency="EUR",
        pnl_effect=Decimal("-5750"),
    )
    joint = _estimate(version_no=2, previous_version_no=1, pnl_effect=None, approvers=())
    rows, totals = estimates.dataset_rows([_estimate(), rebate, joint], NAMES)
    assert [row["row_key"] for row in rows] == [
        "estimate:NS-SO-DE-5002:REBATE-DR-01:2",
        "estimate:PRJ-CB-2026-01:EAC:2",
        "estimate:PRJ-CB-2026-01:EAC:3",
    ]
    first, second, third = rows
    assert first["pnl_effect"] == {"amount": "-5750.00", "currency": "EUR"}
    assert (first["before_value"], first["after_value"], first["currency"]) == (
        "0.00",
        "5750.00",
        "EUR",
    )
    assert (first["preparer"], first["approver"], first["version_pair"]) == (
        "Maya Chen",
        "Priya Raman",
        "v1 → v2",
    )
    # an effect that is joint or not computed is an empty cell, never 0.00, and adds to no total
    assert (second["pnl_effect"], second["approver"]) == (None, None)
    assert third["pnl_effect"] == {"amount": "-29169.29", "currency": "USD"}
    assert totals == {
        "row_count": 3,
        "pnl_effect_total": {"EUR": "-5750.00", "USD": "-29169.29"},
    }


def test_estimate_view_other_than_transaction_needs_functional_rows() -> None:
    foreign = _estimate(currency="GBP", functional_currency="USD")
    estimates.check_view("transaction", [foreign])
    estimates.check_view("functional", [_estimate()])
    with pytest.raises(Problem) as refused:
        estimates.check_view("functional", [_estimate(), foreign])
    (error,) = refused.value.errors
    assert (error.field, error.message) == ("parameters.currency_view", estimates.FUNCTIONAL_ONLY)


# --- RPT-30 -----------------------------------------------------------------------------------


def test_out_of_scope_amount_is_never_apportioned() -> None:
    lease = exclusions.amount_of(
        "LEASE_842",
        allocated_amount=Decimal("81000"),
        version_amount=Decimal("81000"),
        version_lines=2,
    )
    assert lease == Decimal("81000")  # its allocation, whatever else the version routes out
    grant = exclusions.amount_of(
        "CONTRIBUTION_958_605",
        allocated_amount=Decimal("0"),
        version_amount=Decimal("250000"),
        version_lines=1,
    )
    assert grant == Decimal("250000")  # the one routed-out line carries the version's amount
    shared = exclusions.amount_of(
        "INSURANCE_944",
        allocated_amount=Decimal("0"),
        version_amount=Decimal("250000"),
        version_lines=2,
    )
    assert shared is None


def test_latest_open_judgement_of_an_obligation() -> None:
    records = [
        {"judgement_no": "JDG-000001", "status": "SUPERSEDED"},
        {"judgement_no": "JDG-000004", "status": "REJECTED"},
        {"judgement_no": "JDG-000002", "status": "REVIEWED"},
        {"judgement_no": "JDG-000003", "status": "SUBMITTED"},
    ]
    assert exclusions.latest_judgement(records) == records[3]
    assert exclusions.latest_judgement(records[:2]) is None
    assert exclusions.latest_judgement([]) is None


def test_jdg_discard_1_a_discarded_record_is_no_judgement_of_its_line() -> None:
    """E-57 ``VOIDED`` (04 rev 1.242; PRD SM-10): a discarded draft is passed over as a rejected
    record is, so the register shows the latest record that still is a judgement of the line."""
    records = [
        {"judgement_no": "JDG-000002", "status": "REVIEWED"},
        {"judgement_no": "JDG-000005", "status": "VOIDED"},
    ]
    assert exclusions.latest_judgement(records) == records[0]
    assert exclusions.latest_judgement(records[1:]) is None


def _excluded(**values: Any) -> exclusions.Source:
    source: dict[str, Any] = {
        "contract_external_id": "BR-06",
        "obligation_key": "L1-LEASE",
        "product_code": "ROBOT-LEASE-36M",
        "scope_flag": "LEASE_842",
        "currency": "USD",
        "functional_currency": "USD",
        "out_of_scope_amount": Decimal("81000"),
        "judgement_no": "JDG-000001",
        "rationale": "The customer controls the identified robot.",
        "effective_date": date(2026, 1, 1),
    }
    return exclusions.Source(**(source | values))


def test_scope_rows_totals_and_view() -> None:
    grant = _excluded(
        contract_external_id="AA-01",
        obligation_key="L2",
        scope_flag="INSURANCE_944",
        out_of_scope_amount=None,
        judgement_no=None,
        rationale=None,
    )
    rows, totals = exclusions.dataset_rows([_excluded(), grant])
    assert [row["row_key"] for row in rows] == ["obligation:AA-01:L2", "obligation:BR-06:L1-LEASE"]
    bare, lease = rows
    assert (bare["out_of_scope_amount"], bare["judgement_no"], bare["rationale"]) == (
        None,
        None,
        None,
    )
    assert lease["out_of_scope_amount"] == {"amount": "81000.00", "currency": "USD"}
    assert (lease["scope_flag"], lease["judgement_no"], lease["effective_date"]) == (
        "LEASE_842",
        "JDG-000001",
        date(2026, 1, 1),
    )
    assert totals == {"row_count": 2, "out_of_scope_amount_total": {"USD": "81000.00"}}
    exclusions.check_view("transaction", [_excluded(currency="GBP")])
    with pytest.raises(Problem) as refused:
        exclusions.check_view("reporting", [_excluded(currency="GBP")])
    assert refused.value.errors[0].message == exclusions.FUNCTIONAL_ONLY


def test_scope_register_refuses_a_lock_source() -> None:
    params = ReportParams(
        report_code=exclusions.CODE,
        report_version=1,
        parameters={},
        entity_ids=(),
        known_at=AT - timedelta(minutes=1),
        period_lock_id=_id(9),
    )
    with pytest.raises(Problem) as refused:
        exclusions.build(None, params)  # type: ignore[arg-type]  # refused before any read
    assert refused.value.errors[0].field == "parameters.period_lock_id"
