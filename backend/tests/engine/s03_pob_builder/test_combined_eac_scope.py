"""Combined EAC preserves original sources and refuses ambiguous component totals."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from support import bundles
from support.recognition import estimate_version

from erev_engine import compute
from erev_engine.errors import EngineError
from erev_engine.trace import SourceRef, reevaluate
from tests.engine.s03_pob_builder.test_lessor_combination import example
from tests.engine.s03_pob_builder.test_s03_elections import CONTRACT, INCEPTION, points


def scenario(host_scope="MEMBERS", member=True):
    value = example()
    specs = [("SERVICE", "400", host_scope)]
    if member:
        specs.append(("LEASE", "600", "MEMBERS"))
    versions = tuple(
        replace(
            estimate_version(f"{CONTRACT}/EAC-{key}", "EAC", 1, INCEPTION, obligation_key=key),
            expected_total_amount=Decimal(amount),
            parameters={} if scope is None else {"eac_scope": scope},
        )
        for key, amount, scope in specs
    )
    events = [bundles.event(CONTRACT, 2, "CONTRACT_ACTIVATED", INCEPTION, {"checklist": {}})]
    for i, version in enumerate(versions, 3):
        events.append(
            replace(
                bundles.event(
                    CONTRACT,
                    i,
                    "ESTIMATE_CHANGED",
                    INCEPTION,
                    {"estimate_version_id": version.version_key},
                ),
                estimate_version_key=version.version_key,
            )
        )
    for i, key, amount in [(5, "SERVICE", "100"), (6, "LEASE", "200")]:
        events.append(
            bundles.event(
                CONTRACT,
                i,
                "COST_INCURRED",
                date(2026, 1, 31),
                {"obligation_key": key, "purpose": "PROGRESS_INPUT", "amount": amount},
                obligation_keys=[key],
            )
        )
    return replace(
        value,
        evidence_revision=6,
        events=tuple(
            sorted(
                (*value.events, *events),
                key=lambda e: (e.effective_date, e.record_seq, e.event_key),
            )
        ),
        estimate_versions=tuple(sorted(versions, key=lambda v: v.estimate_key)),
        ssp_versions=(points(EQUIP="7500", MAINT="2500"),),
        pob_template_versions=tuple(
            replace(t, recognition_method="COST_TO_COST", ratable_convention=None)
            for t in value.pob_template_versions
        ),
    )


def test_complete_member_eac_aggregates_with_original_trace_sources():
    value = scenario()
    result = compute(value).books[0]
    assert result.contract_version.columns["revenue_cum"] == 300_000
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    nodes = [n for n in result.trace.nodes if n.formula_id == "rec.progress.cost_to_cost.v3"]
    assert nodes
    for node in nodes:
        assert {
            s.ref_id
            for s in node.inputs
            if isinstance(s, SourceRef) and s.ref_type == "estimate_version"
        } == {v.version_key for v in value.estimate_versions}


def test_explicit_whole_eac_does_not_add_component_eac():
    result = compute(scenario("COMBINATION")).books[0]
    assert result.contract_version.columns["revenue_cum"] == 750_000
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}


@pytest.mark.parametrize("scope,member", [(None, True), (None, False), ("MEMBERS", False)])
def test_ambiguous_or_incomplete_scope_requires_clarification(scope, member):
    with pytest.raises(EngineError, match="scope|Scope|MEMBERS"):
        compute(scenario(scope, member))


def test_member_revision_recomputes_total_and_retains_original_version_sources():
    value = scenario()
    original = next(v for v in value.estimate_versions if v.obligation_key == "LEASE")
    revised = replace(
        original,
        version_no=2,
        version_key=original.version_key.replace("@v1", "@v2"),
        effective_date=date(2026, 2, 1),
        expected_total_amount=Decimal("800"),
    )
    event = replace(
        bundles.event(
            CONTRACT,
            7,
            "ESTIMATE_CHANGED",
            revised.effective_date,
            {"estimate_version_id": revised.version_key},
        ),
        estimate_version_key=revised.version_key,
    )
    value = replace(
        value,
        estimate_versions=tuple(
            sorted(
                (*value.estimate_versions, revised), key=lambda v: (v.estimate_key, v.version_no)
            )
        ),
        events=(*value.events, event),
    )
    result = compute(value).books[0]
    assert result.contract_version.columns["revenue_cum"] == 250_000
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}


@pytest.mark.parametrize("case", ["overlap", "currency", "duplicate_whole"])
def test_overlapping_or_incompatible_member_eac_is_rejected(case):
    value = scenario()
    versions = list(value.estimate_versions)
    if case == "overlap":
        versions[0] = replace(versions[0], target_obligation_keys=("SERVICE",))
    elif case == "currency":
        versions[0] = replace(versions[0], currency="EUR")
    else:
        versions = [replace(v, parameters={"eac_scope": "COMBINATION"}) for v in versions]
    with pytest.raises(EngineError):
        compute(replace(value, estimate_versions=tuple(versions)))


def test_eac_api_parameters_preserve_scope_and_reject_unknown_values():
    from pydantic import ValidationError
    from erev_api.enums import EstimateKind
    from erev_api.schemas.db_json import EstimateParameters

    for scope in ("MEMBERS", "COMBINATION"):
        assert EstimateParameters.validate(EstimateKind.EAC, {"eac_scope": scope}) == {
            "eac_scope": scope
        }
    assert EstimateParameters.validate(EstimateKind.EAC, {}) == {}
    with pytest.raises(ValidationError):
        EstimateParameters.validate(EstimateKind.EAC, {"eac_scope": "GUESS"})


@pytest.mark.parametrize("scope,total", [("MEMBERS", 1500000), ("COMBINATION", 800000)])
def test_loss_scope_uses_same_combined_eac_without_double_counting(scope, total):
    value = scenario(scope)
    value = replace(
        value,
        estimate_versions=tuple(
            replace(
                v,
                expected_total_amount=Decimal("8000" if v.obligation_key == "SERVICE" else "7000"),
            )
            for v in value.estimate_versions
        ),
        events=tuple(
            replace(e, payload={**e.payload, "scope_605_35": True})
            if e.event_type == "CONTRACT_BOOKED"
            else e
            for e in value.events
        ),
    )
    result = compute(value).books[0]
    nodes = [n for n in result.trace.nodes if n.measure == "expected_margin"]
    assert nodes
    assert {n.params["eac"] for n in nodes} == {str(total)}
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}


@pytest.mark.parametrize("missing_hours", [False, True])
def test_combined_expected_hours_do_not_require_cost_estimates(missing_hours):
    value = scenario()
    versions = tuple(
        replace(
            v,
            expected_quantity=None
            if missing_hours and v.obligation_key == "LEASE"
            else v.expected_total_amount,
            expected_total_amount=None,
        )
        for v in value.estimate_versions
    )
    progress = bundles.event(
        CONTRACT,
        7,
        "PROGRESS_RECORDED",
        date(2026, 1, 31),
        {
            "obligation_key": "SERVICE",
            "measure": "LABOUR_HOURS",
            "hours_to_date": "300",
            "cumulative_progress_ratio": "0.3",
        },
        obligation_keys=["SERVICE"],
    )
    value = replace(
        value,
        estimate_versions=versions,
        events=tuple(e for e in value.events if e.event_type != "COST_INCURRED") + (progress,),
        pob_template_versions=tuple(
            replace(t, recognition_method="LABOUR_HOURS") for t in value.pob_template_versions
        ),
    )
    if missing_hours:
        with pytest.raises(EngineError) as error:
            compute(value)
        assert "EXPECTED_HOURS_MISSING" in error.value.detail["findings"]
        return
    result = compute(value).books[0]
    assert result.contract_version.columns["revenue_cum"] == 300000
    assert reevaluate(result.trace) == {n.id: n.value for n in result.trace.nodes}
    measured = [
        n
        for n in result.trace.nodes
        if n.formula_id == "rec.progress.labour_hours.v1" and n.params.get("hours") == "300"
    ]
    assert measured
    assert all(n.params.get("expected_hours") == "1000" for n in measured)


def test_member_cost_total_is_not_summed_when_one_member_has_no_cost_estimate():
    value = scenario()
    versions = tuple(
        replace(v, expected_total_amount=None) if v.obligation_key == "LEASE" else v
        for v in value.estimate_versions
    )
    with pytest.raises(EngineError, match="no expected_total_amount"):
        compute(replace(value, estimate_versions=versions))
