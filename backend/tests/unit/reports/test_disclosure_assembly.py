"""Rendering elections preserve authorized source facts while hiding suppressed sections."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from erev_api.domain.reports import disclosure_assembly, disclosure_plan, elections
from erev_api.domain.reports.disclosure_plan import ChildSource
from erev_api.domain.reports.disclosure_results import Collected, CompletedChild
from erev_api.domain.reports.outputs import Column, ReportData
from erev_api.problems import Problem


def test_reliefs_keep_balance_stock_but_hide_rollforward_and_rpo() -> None:
    cutoff = datetime(2026, 10, 1, tzinfo=UTC)
    parent = {
        "tenant_id": UUID(int=1),
        "entity_ids": [UUID(int=2)],
        "book_code": "ASC606",
        "known_at": cutoff,
        "parameters": {"quarter": False},
        "child_report_run_ids": [UUID(int=i) for i in range(10, 19)],
    }
    data = ReportData(
        (Column("amount", "Amount", "money"),),
        ({"row_key": "total", "amount": {"amount": "100.00", "currency": "USD"}},),
        {"total": "100.00"},
    )
    children = tuple(
        CompletedChild(
            ChildSource(
                f"{code}:PERIOD", sections, "PERIOD", UUID(int=i), UUID(int=i + 100), "a" * 64
            ),
            data,
            {**parent, "report_code": code},
            "b" * 64,
        )
        for i, (code, sections) in enumerate(disclosure_plan.SECTIONS.items(), start=10)
    )
    policies = {
        "version": 1,
        "tenant_id": str(parent["tenant_id"]),
        "entity_id": str(parent["entity_ids"][0]),
        "book": "ASC606",
        "known_at": cutoff.isoformat(),
        "elected_reliefs": [
            elections.CONTRACT_BALANCES_RELIEF,
            elections.RPO_RELIEF,
            "disclosure.nonpublic_cost_relief",
        ],
        "rows": [],
        "omitted": False,
        "omission_note": None,
        "interim_pack": elections.TOPIC_270_LIST,
    }
    inputs = Collected((), children)
    pack = disclosure_assembly.assemble(parent, inputs, policies)
    assert len(pack.sections) == 7
    balances, rollforward = pack.sections[1].tables
    assert not balances.omitted and balances.data.rows
    assert rollforward.omitted and rollforward.data.rows == ()
    assert rollforward.data.control_totals == {}
    for section in pack.sections[2:6]:
        assert all(
            table.omitted and not table.data.rows and table.notes for table in section.tables
        )
    assert all(child.data.rows for child in pack.children)
    with pytest.raises(Problem, match="scope"):
        disclosure_assembly.assemble(
            parent,
            inputs,
            {
                **policies,
                "known_at": (cutoff + timedelta(seconds=1)).isoformat(),
            },
        )
    with pytest.raises(Problem, match="still running"):
        disclosure_assembly.assemble(parent, Collected((UUID(int=10),), ()), policies)
    with pytest.raises(Problem, match="complete attached"):
        disclosure_assembly.assemble(parent, Collected((), children[:-1]), policies)
