"""Cross-performer admission requires retained contracting-entity net sources."""

from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from erev_api.domain.reports import opening_agent_sources as sources
from erev_api.problems import Problem
from erev_engine.enums import PrincipalAgent
from erev_engine.stages.s10_billing_balances.agent import is_agent


@pytest.mark.parametrize(
    "enabled,policy,expected",
    [
        (False, "CONTRACTING_ENTITY", False),
        (True, "PERFORMING_ENTITY", False),
        (True, "CONTRACTING_ENTITY", True),
    ],
)
def test_gross_relief_follows_original_book_policy_and_revision(enabled, policy, expected):
    ob = NS(
        principal_agent=PrincipalAgent.AGENT,
        gross_to_net={"amount": "20"},
        performing_entity="PERFORMER",
        contracting_entity="CONTRACTOR",
    )
    ctx = NS(contracting_agent_relief=enabled, policies=NS(value=Mock(return_value=policy)))
    assert is_agent(ob, ctx) is expected
    if enabled:
        ctx.policies.value.assert_called_once_with("ic.revenue_entity", entity="CONTRACTOR")
    assert not is_agent(ob)  # Legacy call sites retain their former interpretation.


def test_saved_reports_preserve_revenue_entity_admission():
    assert not sources.contracting_enabled(NS(binding=NS(evidence={}), sources=None))
    collector = Mock()
    assert sources.contracting_enabled(NS(binding=None, sources=collector))
    key, value = collector.record_evidence.call_args.args
    assert key == sources.CONTRACTING_KEY
    assert sources.contracting_enabled(NS(binding=NS(evidence={key: value}), sources=None))
    with pytest.raises(Problem):
        sources.contracting_enabled(NS(binding=NS(evidence={key: {}}), sources=None))


def test_gross_relief_projects_by_date_when_entity_period_keys_differ():
    from dataclasses import replace
    from datetime import date

    from erev_engine.enums import BookCode
    from erev_engine.stages.s13_books import _relief_targets
    from erev_engine.stages.state import Target

    end = date(2026, 8, 31)
    ctx = NS(
        entities={
            "PERFORMER": NS(periods=[NS(period_key="PERF08", end_date=end)]),
            "CONTRACTOR": NS(periods=[NS(period_key="CONT08", end_date=end)]),
        }
    )
    net = Target(
        BookCode.ASC606, "PERFORMER", "C/S", "revenue_cum", "PERF08", None, 2000, None, "net-source"
    )
    gross = replace(
        net,
        entity="CONTRACTOR",
        period_key="CONT08",
        measure="agent_relief_cum",
        value=10000,
        node_id="gross-source",
    )
    result = _relief_targets(
        ctx, NS(revenue_targets=[net]), {"C/S": NS(contracting_entity="CONTRACTOR")}, [gross]
    )
    assert len(result) == 1
    assert (result[0].entity, result[0].period_key, result[0].value, result[0].node_id) == (
        "CONTRACTOR",
        "CONT08",
        10000,
        "gross-source",
    )


@pytest.mark.parametrize(
    "enabled,policy,role,expected",
    [
        (False, "CONTRACTING_ENTITY", PrincipalAgent.AGENT, "PERF08"),
        (True, "CONTRACTING_ENTITY", PrincipalAgent.AGENT, "CONT08"),
        (True, "PERFORMING_ENTITY", PrincipalAgent.AGENT, "PERF08"),
        (True, "CONTRACTING_ENTITY", PrincipalAgent.PRINCIPAL, "PERF08"),
    ],
)
def test_recognition_calendar_follows_revision_and_original_agent_election(
    enabled, policy, role, expected
):
    from datetime import date

    from erev_engine.enums import RecognitionMethod
    from erev_engine.stages.s09_recognition.components import evaluation_periods

    contractor = NS(
        code="CONTRACTOR",
        periods=[NS(period_key="CONT08", start_date=date(2026, 8, 1), end_date=date(2026, 8, 31))],
    )
    performer = NS(
        code="PERFORMER",
        periods=[NS(period_key="PERF08", start_date=date(2026, 7, 27), end_date=date(2026, 8, 23))],
    )
    ctx = NS(
        contracting_agent_calendar=enabled,
        policies=NS(value=Mock(return_value=policy)),
        entities={"CONTRACTOR": contractor, "PERFORMER": performer},
        horizon={"CONTRACTOR": "CONT08", "PERFORMER": "PERF08"},
    )
    ob = NS(
        principal_agent=role,
        gross_to_net={"amount": "20"},
        performing_entity="PERFORMER",
        contracting_entity="CONTRACTOR",
        recognition_method=RecognitionMethod.UNITS_DELIVERED,
        material_right=None,
        segments=(),
    )
    result = evaluation_periods(ctx, NS(inception_date=date(2026, 8, 1)), ob)
    assert [period.period_key for period in result] == [expected]
    assert ob.performing_entity == "PERFORMER"
