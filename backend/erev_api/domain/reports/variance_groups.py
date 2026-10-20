"""Reconcile a frozen close pair across authorized retained contract groups.

This worker calculation runs after source loading has closed its transaction. It
keeps currency/measure totals separate and retains each group's execution evidence.
Independent groups entering/leaving the population have explicit source-backed
contributions. Merges/splits replay membership, references, business events and FX
on connected groups; mixed contract/estimate records still require separate phases.
No empty bundle is invented.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from fractions import Fraction
from types import MappingProxyType
from uuid import UUID

from erev_engine import compute
from erev_engine.stages.s15_disclosures.variance import Decomposition

from erev_api.problems import Problem

from . import variance_execution, variance_measures, variance_membership, variance_population
from .computation_sources import VerifiedComputation
from .variance_measures import MeasureKey
from .variance_replay import Engine
from .variance_sources import Pair, Side


@dataclass(frozen=True)
class GroupReplay:
    groups: Mapping[UUID, variance_execution.RetainedReplay | variance_population.PopulationReplay]
    measures: Mapping[MeasureKey, Decomposition]
    driver_totals: Mapping[tuple[str, str, str], Fraction]  # currency, measure, driver
    required_entity_ids: tuple[UUID, ...]
    contract_groups: Mapping[str, UUID] = field(default_factory=dict)


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Close variance groups: {detail}")


def _groups(side: Side) -> dict[UUID, VerifiedComputation]:
    if set(side.contract_computations.values()) != set(side.computations):
        raise _refuse(
            "the selected computation population is incomplete or contains unused sources."
        )
    groups: dict[UUID, VerifiedComputation] = {}
    for name, identity in side.contract_computations.items():
        source = side.computations[identity]
        if (
            identity != source.computation_id
            or name not in source.bundle.group.member_contract_keys
        ):
            raise _refuse("a contract does not belong to its selected computation.")
        previous = groups.setdefault(source.group_id, source)
        if previous.computation_id != identity:
            raise _refuse("one group selects inconsistent computations at the same close.")
    return groups


def execute(pair: Pair, *, engine: Engine = compute) -> GroupReplay:
    """Reproduce every monetary endpoint and then aggregate exact driver effects."""
    # Also verifies lock ordering, scope and complete frozen monetary datasets.
    variance_measures.compare(pair.earlier.frozen, pair.later.frozen)
    earlier = variance_measures.endpoints(pair.earlier.frozen)
    later = variance_measures.endpoints(pair.later.frozen)
    for side, amounts in ((pair.earlier, earlier), (pair.later, later)):
        if any(key.contract_external_id not in side.contract_computations for key in amounts):
            raise _refuse("a frozen monetary contract has no retained source.")
    old, new = _groups(pair.earlier), _groups(pair.later)
    scope = pair.earlier.frozen.scope
    runs: dict[UUID, variance_execution.RetainedReplay | variance_population.PopulationReplay] = {}
    measures = {}
    totals: dict[tuple[str, str, str], Fraction] = {}
    affected: set[UUID] = set()
    for name in pair.earlier.contract_computations.keys() & pair.later.contract_computations.keys():
        a = pair.earlier.computations[pair.earlier.contract_computations[name]]
        b = pair.later.computations[pair.later.contract_computations[name]]
        if (
            a.group_id != b.group_id
            or a.bundle.group.member_contract_keys != b.bundle.group.member_contract_keys
            or a.bundle.group.group_key != b.bundle.group.group_key
            or a.bundle.group.criterion != b.bundle.group.criterion
        ):
            affected.update((a.group_id, b.group_id))
    while affected:
        names = {
            name
            for key, source in (*old.items(), *new.items())
            if key in affected
            for name in source.bundle.group.member_contract_keys
        }
        expanded = affected | {
            key
            for key, source in (*old.items(), *new.items())
            if names.intersection(source.bundle.group.member_contract_keys)
        }
        if expanded == affected:
            break
        affected = expanded
    aliases: dict[str, UUID] = {}
    if affected:
        names = {
            name
            for key, source in (*old.items(), *new.items())
            if key in affected
            for name in source.bundle.group.member_contract_keys
        }
        membership, aliases = variance_membership.execute(
            {key: source for key, source in old.items() if key in affected},
            {key: source for key, source in new.items() if key in affected},
            {
                key: point.amount
                for key, point in earlier.items()
                if key.contract_external_id in names
            },
            {
                key: point.amount
                for key, point in later.items()
                if key.contract_external_id in names
            },
            entity_code=scope.entity_code,
            book_code=scope.book_code,
            period_key=scope.period_key,
            engine=engine,
        )
        runs.update(membership)
        for result in membership.values():
            for key, decomposition in result.replay.measures.items():
                if key in measures:
                    raise _refuse("membership replay duplicates an attributed contract.")
                measures[key] = decomposition
                for effect in decomposition.effects:
                    total_key = key.currency, key.measure, effect.driver
                    totals[total_key] = totals.get(total_key, Fraction(0)) + effect.amount
    for group_id in sorted((old.keys() | new.keys()) - affected, key=str):
        if group_id not in old or group_id not in new:
            entering = group_id not in old
            side = pair.later if entering else pair.earlier
            source = new[group_id] if entering else old[group_id]
            names = {
                name
                for name, identity in side.contract_computations.items()
                if identity == source.computation_id
            }
            endpoint = later if entering else earlier
            population = variance_population.execute(
                source,
                {
                    key: point.amount
                    for key, point in endpoint.items()
                    if key.contract_external_id in names
                },
                entering=entering,
                entity_code=scope.entity_code,
                book_code=scope.book_code,
                period_key=scope.period_key,
                engine=engine,
            )
            runs[group_id] = population
            for key, decomposition in population.replay.measures.items():
                if key in measures or key.contract_external_id not in names:
                    raise _refuse("a population change duplicates an attributed contract.")
                measures[key] = decomposition
                for effect in decomposition.effects:
                    total_key = key.currency, key.measure, effect.driver
                    totals[total_key] = totals.get(total_key, Fraction(0)) + effect.amount
            continue
        names = {
            name
            for name, identity in pair.earlier.contract_computations.items()
            if identity == old[group_id].computation_id
        }
        result = variance_execution.execute(
            old[group_id],
            new[group_id],
            entity_code=scope.entity_code,
            book_code=scope.book_code,
            period_key=scope.period_key,
            earlier_metrics={
                key: point.amount
                for key, point in earlier.items()
                if key.contract_external_id in names
            },
            later_metrics={
                key: point.amount
                for key, point in later.items()
                if key.contract_external_id in names
            },
            engine=engine,
        )
        runs[group_id] = result
        for key, decomposition in result.replay.measures.items():
            if key in measures or key.contract_external_id not in names:
                raise _refuse("a replay duplicates or introduces an unattributed contract.")
            measures[key] = decomposition
            for effect in decomposition.effects:
                total_key = key.currency, key.measure, effect.driver
                totals[total_key] = totals.get(total_key, Fraction(0)) + effect.amount
    return GroupReplay(
        MappingProxyType(runs),
        MappingProxyType(measures),
        MappingProxyType(totals),
        pair.required_entity_ids,
        MappingProxyType(aliases),
    )
