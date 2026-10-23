"""Opening-disclosure explanations use their original entity policy population on rerun."""

from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from erev_api.domain.reports import opening_consumption_policy as policy
from erev_api.domain.reports import opening_relief_currency as opening
from erev_api.domain.reports.builders import ReportParams, SourceCollector
from erev_api.problems import Problem

ENTITY = UUID(int=1)
CUT = datetime(2026, 9, 30, tzinfo=UTC)


@pytest.mark.parametrize("view", ["transaction", "functional", "reporting"])
def test_saved_explanation_never_resolves_current_policy(monkeypatch, view):
    collector = SourceCollector()
    collector.record_cutoff(CUT)
    params = ReportParams(
        "revenue_from_opening_liability", 1, {}, (ENTITY,), CUT, sources=collector
    )
    entities = [SimpleNamespace(id=ENTITY)]
    monkeypatch.setattr(policy, "resolve", lambda *a, **k: SimpleNamespace(value="FIFO_WITHIN_POB"))
    args = dict(
        contracts=[],
        totals={},
        entities=entities,
        periods={},
        book="ASC606",
        view=view,
        rates=[],
        source_key=opening.KEY if view != "transaction" else "opening_relief_transaction_v1",
    )
    first = opening.finish(SimpleNamespace(session=None), params, **args)
    bound = collector.binding(row_keys=[])
    assert bound.evidence[policy.KEY] == {
        "book": "ASC606",
        "entities": {str(ENTITY): "FIFO_WITHIN_POB"},
    }

    def no_current_read(*args, **kwargs):
        raise AssertionError("Saved explanation consulted current policy")

    monkeypatch.setattr(policy, "resolve", no_current_read)
    replay = opening.finish(SimpleNamespace(session=None), replace(params, binding=bound), **args)
    assert replay.control_totals == first.control_totals
    assert "Per-obligation consumption is not provided" in replay.control_totals["footnote"]
    for invalid in (
        {"book": "IFRS15", "entities": {str(ENTITY): "FIFO_WITHIN_POB"}},
        {"book": "ASC606", "entities": {}},
        {"book": "ASC606", "entities": {str(ENTITY): "UNKNOWN"}},
        {"book": "ASC606", "entities": {str(ENTITY): []}},
    ):
        with pytest.raises(Problem) as raised:
            policy.read(
                None,
                replace(params, binding=replace(bound, evidence={policy.KEY: invalid})),
                entities,
                "ASC606",
            )

        assert (
            raised.value.errors[0].message == "Retained opening-consumption policies are invalid."
        )
