"""RPT-31 projection and coverage of stored period loss tests."""

from decimal import Decimal

import pytest
from erev_api.domain.reports.builders import loss_provision_register as loss
from erev_api.problems import Problem
from erev_engine import ENGINE_VERSION
from erev_engine.trace import TraceBuilder


def source(**changes):
    return {
        "external_id": "C-1",
        "obligation_key": None,
        "unit": "CONTRACT",
        "measurement_basis": "ASC_605_35",
        "currency": "USD",
        "eac_versions": [("EAC-A", 2)],
        **dict.fromkeys(loss.MONEY, Decimal("10.00")),
        **changes,
    }


def test_projection_keeps_all_eac_contributors_and_totals_by_currency():
    data = loss.dataset_rows(
        [
            source(unit="POB", obligation_key="P1", eac_versions=[("EAC-A", 2), ("EAC-B", 3)]),
            source(external_id="C-2", currency="EUR", measurement_basis="IAS_37"),
        ]
    )
    assert data.rows[0]["row_key"] == "obligation:C-1:P1"
    assert data.rows[0]["eac_version_no"] is None
    assert data.rows[0]["eac_versions"] == ["EAC-A@v2", "EAC-B@v3"]
    assert data.rows[1]["eac_version_no"] == 2
    assert data.rows[1]["measurement_basis"] == "IAS 37"
    assert data.control_totals["provision_balance"] == {"EUR": "10.00", "USD": "10.00"}
    assert data.control_totals["provision_movement"] == {"EUR": "10.00", "USD": "10.00"}


@pytest.mark.parametrize("subject", ["C-1", "C-1/P1"])
def test_missing_stored_loss_is_refused_even_when_trace_amount_is_zero(subject):
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    key = tb.node(
        measure="loss_provision_required",
        subject_key=subject,
        period_key="P09",
        value=0,
        currency="USD",
        minor_unit=2,
        formula_id="loss.required.v1",
        inputs=[],
        params={},
        narrative_key="loss.required",
    )
    trace = tb.build(root_measures={})
    with pytest.raises(Problem) as caught:
        loss.check_coverage(trace, external_id="C-1", period_key="P09", rows=[])
    assert "incomplete stored loss" in caught.value.errors[0].message
    loss.check_coverage(
        trace,
        external_id="C-1",
        period_key="P09",
        rows=[{"trace_nodes": {"loss_provision_required": key}}],
    )
    loss.check_coverage(trace, external_id="C-OTHER", period_key="P09", rows=[])
    loss.check_coverage(trace, external_id="C-1", period_key="P08", rows=[])


def test_empty_register_has_explicit_zero_row_count():
    result = loss.dataset_rows([])
    assert result.rows == ()
    assert result.control_totals == {
        "row_count": 0,
        "provision_balance": {},
        "provision_movement": {},
    }


def test_columns_match_the_register_specification():
    from support import report_specs

    assert [column.key for column in loss.COLUMNS] == report_specs.fields(31, loss.CODE)
    headers = {column.key: column.header for column in loss.COLUMNS}
    for header, fields in report_specs.grid(31, loss.CODE):
        assert headers[fields[0]] == header
