"""Engine test support: bundle builders, strategies and Hypothesis profiles.

dev-guide §9.7 (DG-PROP-01, DG-PROP-03); POLICIES §0.4, §6.3; BUILD_SPEC EKC-7.
"""

from __future__ import annotations

import pytest
from erev_api.registry.policies import POLICY_PARAMETERS
from erev_engine import guards
from erev_engine.dates import period_of
from erev_engine.stages.state import PolicyResolver
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from support import bundles, strategies


def _scope(code: str) -> dict[str, str]:
    """Pin P codes resolve through the PERIOD scope of the builder entity (CV-17)."""
    if POLICY_PARAMETERS[code].pin != "P":
        return {}
    entity = bundles.default_entity()
    return {"entity": entity.code, "period": entity.periods[0].period_key}


def test_policy_sets() -> None:
    parity = PolicyResolver(bundles.policy_set("LEGACY_PARITY"))
    assert parity.value("ssp.outside_range_point", **_scope("ssp.outside_range_point")) == (
        "NEAREST_BOUND"
    )
    assert parity.value("billing.posting", **_scope("billing.posting")) == "ERP"
    assert parity.value("material_right.exercise", **_scope("material_right.exercise")) == (
        "MODIFICATION"
    )

    default = PolicyResolver(bundles.policy_set("DEFAULT"))
    code = "recognition.time_convention"
    assert default.value(code, **_scope(code)) == "DAILY"
    assert default.value("billing.posting", **_scope("billing.posting")) == "ERP"
    assert default.value("material_right.exercise", **_scope("material_right.exercise")) == (
        "CONTINUATION"
    )

    # Every code with a framework default resolves, pin P codes per period of the builder entity.
    for code, spec in POLICY_PARAMETERS.items():
        if spec.default_asc606 is None:
            with pytest.raises(ValueError, match="absent"):
                default.value(code)
            continue
        resolved = default.resolved(code, **_scope(code))
        assert (resolved.source_ref, resolved.level, resolved.pin) == (
            spec.source_ref,
            "DEFAULT",
            spec.pin,
        )
    with pytest.raises(ValueError, match="preset"):
        bundles.policy_set("PARITY")


def test_builders_deterministic() -> None:
    first, second = bundles.minimal_contract(), bundles.minimal_contract()
    assert first.sha256() == second.sha256()
    assert bundles.minimal_contract("LEGACY_PARITY").sha256() != first.sha256()
    guards.no_floats(first)
    entity = first.entities[0]
    assert period_of(entity, first.group.inception_date).period_key == "FY2026-P01"
    assert first.events[0].event_type == "CONTRACT_BOOKED"
    assert first.books[0].policies == bundles.policy_set("DEFAULT", entity=entity)


STRATEGIES = {
    "allocation_cases": strategies.allocation_cases(),
    "arrival_orders": strategies.arrival_orders(strategies.obligation_keys(5)),
    "billing_paths": strategies.billing_paths(),
    "currencies": strategies.currencies(),
    "fx_rate_paths": strategies.fx_rate_paths(),
    "progress_paths": strategies.progress_paths(),
    "progress_paths_with_returns": strategies.progress_paths_with_returns(),
    "ssp_weights": strategies.ssp_weights(),
    "transaction_totals": strategies.transaction_totals(),
    "world_specs": strategies.world_specs(),
}


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_strategies_emit_no_floats(name: str) -> None:
    @settings(
        max_examples=200,
        derandomize=True,
        database=None,
        deadline=None,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    )
    @given(value=STRATEGIES[name])
    def draw(value: object) -> None:
        guards.no_floats(value)

    draw()


def test_hypothesis_profiles_match_dg_prop_01() -> None:
    dev, ci, thorough = (settings.get_profile(name) for name in ("dev", "ci", "thorough"))
    assert (dev.max_examples, dev.derandomize, dev.database is not None) == (20, False, True)
    assert dev.deadline is not None and dev.deadline.total_seconds() == 2
    assert (ci.max_examples, ci.deadline, ci.derandomize, ci.database) == (100, None, True, None)
    assert HealthCheck.too_slow in ci.suppress_health_check
    assert (thorough.max_examples, thorough.deadline, thorough.derandomize) == (1000, None, False)
    assert thorough.database is not None
    assert all(profile.print_blob for profile in (dev, ci, thorough))
    assert st.integers  # the strategies module is hypothesis's own
