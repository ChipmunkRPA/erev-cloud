from decimal import Decimal
from types import SimpleNamespace as NS
from uuid import UUID

import pytest

from erev_api.domain.reports import acquisition_cells as cells
from erev_api.domain.reports.builders import SourceCollector
from erev_api.problems import Problem


def fixture():
    collector = SourceCollector()
    identity = f"{UUID(int=1)}:{UUID(int=2)}:{UUID(int=3)}:FY2026-P08"
    node = "contract_liability_functional:ACQUIRED@US:FY2026-P08"
    collector.record_evidence(
        cells.FLOW_KEY,
        {
            identity: {
                "event_key": "ACQUIRED/EV-000003",
                "input_sha256": "input",
                "output_sha256": "output",
                "currency": "USD",
                "amounts": {"contract_liability": "110"},
                "nodes": [node],
            }
        },
    )
    amounts = {
        "contract_liability": Decimal(100),
        "contract_asset": Decimal(0),
        "unbilled_receivable": Decimal(0),
    }
    item = NS(
        contract_id=UUID(int=2),
        entity_id=UUID(int=3),
        external_id="ACQUIRED",
        entity_code="US",
        currency="EUR",
        lines={"BUSINESS_COMBINATIONS": amounts},
    )
    values = {name: {"currency": "EUR", "amount": str(value)} for name, value in amounts.items()}
    rows = [
        {
            "row_key": "BUSINESS_COMBINATIONS",
            "line_code": "BUSINESS_COMBINATIONS",
            "currency": "EUR",
            **values,
        },
        {
            "row_key": "contract:ACQUIRED:US",
            "line_code": None,
            "business_combinations": values["contract_liability"],
        },
    ]
    return NS(binding=None, sources=collector), item, rows


def test_retained_presented_amounts_and_original_trace_links():
    params, item, rows = fixture()
    cells.retain(params, [item], rows, "contract_liability", [])
    held = NS(binding=NS(evidence=params.sources.evidence))
    session = NS(execute=lambda _: [(UUID(int=1), UUID(int=4))])
    value, contributors = cells.cell(session, held, "BUSINESS_COMBINATIONS", "contract_liability")
    assert value == {"amount": "100", "currency": "EUR"}
    assert contributors[0]["value"] == {"amount": "100.00", "currency": "EUR"}
    assert any("110 USD" in line for line in contributors[0]["_source_set_details"])
    assert any(
        f"/trace/{UUID(int=4)}?node=" in link["href"]
        for link in contributors[0]["_source_set_links"]
    )
    cells.retain(held, [item], rows, "contract_liability", [])
    with pytest.raises(Problem, match="not-found"):
        cells.cell(session, held, "OPENING", "contract_liability")
    with pytest.raises(Problem, match="not-found"):
        cells.cell(NS(execute=lambda _: []), held, "BUSINESS_COMBINATIONS", "contract_liability")


def test_inconsistent_cells_refuse_and_old_bindings_do_not_gain_explanations():
    params, item, rows = fixture()
    rows[0]["contract_liability"] = {"amount": "200", "currency": "EUR"}
    with pytest.raises(Problem, match="validation-failed"):
        cells.retain(params, [item], rows, "contract_liability", [])
    old = NS(binding=NS(evidence={}))
    cells.retain(old, [item], rows, "contract_liability", [])
    with pytest.raises(Problem, match="not-found"):
        cells.cell(NS(), old, "BUSINESS_COMBINATIONS", "contract_liability")
    cells.retain(NS(binding=None, sources=None), [item], rows, "contract_liability", [])
