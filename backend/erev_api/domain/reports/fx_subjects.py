"""Resolve sealed FX subjects under the retained computation's group membership."""

from erev_engine.bundle import InputBundle
from erev_engine.stages.s01_canonicalize import contract_subject_key, group_entity_subject_key
from erev_engine.stages.s14_posting.assign import regrouped_subject_key


def retained_subject(stored: str | None, bundle: InputBundle, entity: str) -> str:
    """Apply the same keyless and regrouping rules used by S14's posted totals.

    Only a comparison key changes. The retained line and its own historical
    calculation still verify under their original group and source identities.
    """
    group = bundle.group
    if stored is None:
        return group_entity_subject_key(group.group_key, entity)
    return regrouped_subject_key(
        stored,
        group.group_key,
        frozenset(contract_subject_key(key) for key in group.member_contract_keys),
    )
