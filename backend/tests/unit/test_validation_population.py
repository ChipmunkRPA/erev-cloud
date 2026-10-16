"""The start fence covers the whole population, not just sampled groups."""

from dataclasses import replace
from uuid import UUID

from erev_api.domain.contracts.release_validation import GroupFacts, select_population
from erev_api.domain.contracts.validation_population import PopulationFacts


def test_population_fingerprint_covers_unsampled_heads_and_members() -> None:
    tenant = UUID(int=1)
    groups = tuple(
        GroupFacts(UUID(int=i), UUID(int=100 + i), False, frozenset({("ASC606", "TIME_ELAPSED")}))
        for i in range(2, 32)
    )
    facts = PopulationFacts(
        groups,
        (UUID(int=50),),
        tuple(
            (group.group_id, UUID(int=200 + i), UUID(int=50), 1) for i, group in enumerate(groups)
        ),
    )
    sampled = select_population(groups, seed=20260912, tenant_id=tenant)
    selected = {group.group_id for group in sampled.selected}
    unsampled = next(group for group in groups if group.group_id not in selected)
    changed = replace(
        facts,
        groups=tuple(
            replace(group, head_computation_id=UUID(int=999)) if group == unsampled else group
            for group in groups
        ),
    )
    assert select_population(changed.groups, seed=20260912, tenant_id=tenant) == sampled
    assert changed.fingerprint() != facts.fingerprint()
    member = facts.members[0]
    assert (
        replace(facts, members=((*member[:3], 2), *facts.members[1:])).fingerprint()
        != facts.fingerprint()
    )
    assert (
        replace(
            facts, groups=tuple(reversed(groups)), members=tuple(reversed(facts.members))
        ).fingerprint()
        == facts.fingerprint()
    )
