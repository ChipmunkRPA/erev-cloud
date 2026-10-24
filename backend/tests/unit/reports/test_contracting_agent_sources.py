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
