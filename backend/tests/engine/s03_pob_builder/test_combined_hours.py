"""Explicit cumulative-hour scopes retain one latest original reading per member."""

from dataclasses import replace
from datetime import date

import pytest
from support import bundles

from erev_engine import compute
from erev_engine.errors import EngineError
from erev_engine.trace import SourceRef, reevaluate
from tests.engine.s03_pob_builder.test_combined_eac_scope import scenario
from tests.engine.s03_pob_builder.test_s03_elections import CONTRACT


def hours(readings, revision=9):
    value = scenario()
    events = tuple(e for e in value.events if e.event_type != "COST_INCURRED")
    for i, (key, amount, scope) in enumerate(readings, 7):
        events += (
            bundles.event(
                CONTRACT,
                i,
                "PROGRESS_RECORDED",
                date(2026, 1, 31),
                {
                    "obligation_key": key,
                    "measure": "LABOUR_HOURS",
                    "hours_to_date": amount,
                    "cumulative_progress_ratio": "0.3",
                    **({"hours_scope": scope} if scope else {}),
                },
                obligation_keys=[key],
            ),
        )
    return replace(
        value,
        evidence_revision=revision,
        events=events,
        estimate_versions=tuple(
            replace(v, expected_quantity=v.expected_total_amount, expected_total_amount=None)
            for v in value.estimate_versions
        ),
        pob_template_versions=tuple(
            replace(t, recognition_method="LABOUR_HOURS") for t in value.pob_template_versions
        ),
    )


def test_latest_member_hours_sum_and_retain_original_sources():
    value = hours(
        [("SERVICE", "50", "MEMBERS"), ("LEASE", "200", "MEMBERS"), ("SERVICE", "100", "MEMBERS")]
    )
    result = compute(value).books[0]
    assert result.contract_version.columns["revenue_cum"] == 300000
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    node = next(
        n
        for n in result.trace.nodes
        if n.formula_id == "rec.progress.labour_hours.v3" and n.params.get("hours") == "300"
    )
    sources = [
        s for s in node.inputs if isinstance(s, SourceRef) and s.ref_type == "contract_event"
    ]
    assert {s.ref_id for s in sources} == {e.event_key for e in value.events[-2:]}
    assert node.params["hours_source_count"] == "2"
    assert {s.detail["hours_scope"] for s in sources} == {"MEMBERS"}


def test_whole_reading_and_explicit_zero_member_are_supported():
    for rows in [
        [("SERVICE", "300", "COMBINATION")],
        [("SERVICE", "0", "MEMBERS"), ("LEASE", "300", "MEMBERS")],
    ]:
        assert compute(hours(rows)).books[0].contract_version.columns["revenue_cum"] == 300000


@pytest.mark.parametrize(
    "rows",
    [
        [("SERVICE", "100", "MEMBERS")],
        [("SERVICE", "100", None)],
        [("SERVICE", "100", "COMBINATION"), ("LEASE", "200", "MEMBERS")],
        [("SERVICE", "100", "COMBINATION"), ("LEASE", "200", "COMBINATION")],
    ],
)
def test_missing_or_ambiguous_member_scope_is_not_a_partial_numerator(rows):
    with pytest.raises(EngineError) as caught:
        compute(hours(rows))
    assert caught.value.detail["rule"] == "COMBINED_HOURS_SCOPE"


def test_retained_legacy_bundle_keeps_host_reading():
    result = compute(hours([("SERVICE", "100", None), ("LEASE", "200", None)], revision=8)).books[0]
    assert result.contract_version.columns["revenue_cum"] == 100000
