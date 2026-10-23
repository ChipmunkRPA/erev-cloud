"""Replay membership, references/policies, new business events and FX rates.

Both frozen sides are reproduced on the earlier posted basis. Contract records
are replayed as references while accounting identity/currency/inception stay fixed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, replace
from fractions import Fraction
from operator import attrgetter
from types import MappingProxyType
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from erev_engine.bundle import EstimateVersionInput, EventInput, InputBundle, ResolvedPolicyInput
from erev_engine.canonical import canonical_bytes
from erev_engine.stages.s01_canonicalize.convert import contract_key_from_subject

from erev_api.problems import Problem

from .computation_sources import VerifiedComputation
from .variance_execution import RetainedReplay, SourceExecution, verify_source
from .variance_projection import Projection
from .variance_replay import (
    Engine,
    Execution,
    Metrics,
    Replay,
    decompose_steps,
    validate_contract_basis,
    validate_reporting_pair,
)
from .variance_replay import (
    event_runs as classified_runs,
)
from .variance_reporting import Basis


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Close membership replay: {detail}")


def execute(
    old: Mapping[UUID, VerifiedComputation],
    new: Mapping[UUID, VerifiedComputation],
    earlier: Metrics,
    later: Metrics,
    *,
    entity_code: str,
    book_code: str,
    period_key: str,
    engine: Engine,
    event_details: bool = False,
    currency_view: Literal["transaction", "functional", "reporting"] = "transaction",
    earlier_reporting_basis: Basis | None = None,
    later_reporting_basis: Basis | None = None,
) -> tuple[dict[UUID, RetainedReplay], dict[str, UUID]]:
    validate_reporting_pair(currency_view, earlier_reporting_basis, later_reporting_basis)
    old_owner = {
        name: key
        for key, source in old.items()
        for name in source.bundle.group.member_contract_keys
    }
    new_owner = {
        name: key
        for key, source in new.items()
        for name in source.bundle.group.member_contract_keys
    }
    if (
        set(old_owner) != set(new_owner)
        or len(old_owner) != sum(len(s.bundle.contracts) for s in old.values())
        or len(new_owner) != sum(len(s.bundle.contracts) for s in new.values())
    ):
        raise _refuse("membership entry/exit needs complete retained sources on both sides.")
    sources = (*old.values(), *new.values())
    checked = {
        "format_version",
        "engine_version",
        "trigger",
        "known_at",
        "tenant_preset",
        "currencies",
        "books",
        "entities",
        "group",
        "contracts",
        "events",
        "ssp_versions",
        "pob_template_versions",
        "rule_set_versions",
        "estimate_versions",
        "fx_rates",
        "posted",
    }
    if {field.name for field in fields(sources[0].bundle)} != checked:
        raise _refuse("the input schema requires a new membership comparison rule.")
    for source in sources:
        group = source.bundle.group
        if group.inception_date != min(
            contract.inception_date for contract in source.bundle.contracts
        ) or any(
            contract.transaction_currency != group.transaction_currency
            for contract in source.bundle.contracts
        ):
            raise _refuse("group date/currency does not derive from its retained members.")
        if any(
            policy.scope == "GROUP" and policy.subject_key not in ("", group.group_key)
            for book in source.bundle.books
            for policy in book.policies
        ):
            raise _refuse("group policy ownership is inconsistent.")
    # References shared by a computation must not drift between the partitions.
    shared = (
        "engine_version",
        "format_version",
        "tenant_preset",
        "currencies",
        "entities",
    )
    for field in shared:
        if len({canonical_bytes(getattr(source.bundle, field)) for source in sources}) != 1:
            raise _refuse(f"membership is mixed with a {field} change.")
    # Repartitioning needs a coherent earlier FX basis; never select one member's
    # rates arbitrarily when the original groups used different rate sets.
    if len({canonical_bytes(source.bundle.fx_rates) for source in old.values()}) != 1:
        raise _refuse("earlier groups have inconsistent FX bases.")
    earlier_fx = next(iter(old.values())).bundle.fx_rates
    earlier_contracts = tuple(
        contract for source in old.values() for contract in source.bundle.contracts
    )
    later_contracts = tuple(
        contract for source in new.values() for contract in source.bundle.contracts
    )
    validate_contract_basis(earlier_contracts, later_contracts)
    estimate_sides = []
    for side in (old, new):
        versions: dict[str, EstimateVersionInput] = {}
        for source in side.values():
            for version in source.bundle.estimate_versions:
                if version.version_key in versions and versions[version.version_key] != version:
                    raise _refuse("one estimate version has inconsistent retained contents.")
                versions[version.version_key] = version
        estimate_sides.append(versions)
    if any(estimate_sides[1].get(key) != version for key, version in estimate_sides[0].items()):
        raise _refuse("an earlier immutable estimate version changed or disappeared.")
    for field in ("products", "portfolios"):
        before = {
            canonical_bytes(item)
            for source in old.values()
            for item in getattr(source.bundle.group, field)
        }
        after = {
            canonical_bytes(item)
            for source in new.values()
            for item in getattr(source.bundle.group, field)
        }
        if before != after:
            raise _refuse(f"membership is mixed with a group {field} change.")

    def books(source: VerifiedComputation) -> tuple[bytes, ...]:
        return tuple(canonical_bytes(replace(book, policies=())) for book in source.bundle.books)

    if len({books(source) for source in sources}) != 1:
        raise _refuse("book configuration differs between group partitions.")

    reference_fields = ("ssp_versions", "pob_template_versions", "rule_set_versions")
    for field in reference_fields:
        if len({canonical_bytes(getattr(source.bundle, field)) for source in old.values()}) != 1:
            raise _refuse(f"earlier groups have inconsistent {field} bases.")
    old_references = {
        field: getattr(next(iter(old.values())).bundle, field) for field in reference_fields
    }

    def prior_basis(target: InputBundle) -> InputBundle:
        members = set(target.group.member_contract_keys)
        donors = [old[key].bundle for key in sorted({old_owner[name] for name in members})]
        prior_books = []
        for target_book in target.books:
            policies: dict[tuple[str, str, str], ResolvedPolicyInput] = {}
            shared_policy_bases = []
            for donor in donors:
                book = next(b for b in donor.books if b.book_code == target_book.book_code)
                shared_policy_bases.append(
                    {
                        canonical_bytes(
                            replace(policy, subject_key="") if policy.scope == "GROUP" else policy
                        )
                        for policy in book.policies
                        if policy.scope in {"GROUP", "ENTITY", "PERIOD", "PRODUCT"}
                    }
                )
                for policy in book.policies:
                    if policy.scope == "CONTRACT":
                        if policy.subject_key not in members:
                            continue
                    elif policy.scope in {"OBLIGATION", "CONTRACT_PERIOD"}:
                        if contract_key_from_subject(policy.subject_key) not in members:
                            continue
                    elif policy.scope == "GROUP":
                        policy = replace(policy, subject_key="")
                    elif policy.scope not in {"ENTITY", "PERIOD", "PRODUCT"}:
                        raise _refuse("a policy scope requires a membership mapping rule.")
                    identity = (policy.code, policy.scope, policy.subject_key)
                    if identity in policies and policies[identity] != policy:
                        raise _refuse("earlier members have conflicting policy bases.")
                    policies[identity] = policy
            if any(basis != shared_policy_bases[0] for basis in shared_policy_bases[1:]):
                raise _refuse("earlier members have inconsistent shared policy bases.")
            prior_books.append(
                replace(target_book, policies=tuple(policies[k] for k in sorted(policies)))
            )
        portfolios = {"PORTFOLIO:" + p.code for p in target.group.portfolios}
        estimates = tuple(
            sorted(
                (
                    version
                    for version in estimate_sides[0].values()
                    if contract_key_from_subject(version.estimate_key) in members | portfolios
                ),
                key=lambda version: (version.estimate_key, version.version_no),
            )
        )
        return replace(
            target,
            contracts=tuple(
                sorted(
                    (c for c in earlier_contracts if c.external_id in members),
                    key=lambda c: c.external_id,
                )
            ),
            books=tuple(prior_books),
            estimate_versions=estimates,
            **old_references,
        )

    old_events = {
        event.event_key: event for source in old.values() for event in source.bundle.events
    }
    new_events = {
        event.event_key: event for source in new.values() for event in source.bundle.events
    }
    if any(new_events.get(key) != value for key, value in old_events.items()):
        raise _refuse("an earlier immutable event changed or disappeared.")
    added = tuple(sorted(new_events.keys() - old_events.keys()))
    if any(
        new_events[key].recorded_at <= old[old_owner[new_events[key].contract_key]].bundle.known_at
        for key in added
    ):
        raise _refuse(
            "a newly supplied replay event was already known at the earlier source cutoff."
        )
    cutoff = max(source.bundle.known_at for source in new.values())
    if cutoff < max(source.bundle.known_at for source in old.values()):
        raise _refuse("the source cutoffs are reversed.")
    old_verified: dict[UUID, SourceExecution] = {}
    new_verified: dict[UUID, SourceExecution] = {}
    normalized: dict[UUID, str] = {}
    baselines: dict[UUID, Execution] = {}
    phases: dict[UUID, list[tuple[Execution, Metrics]]] = {}
    for side, metrics, verified in ((old, earlier, old_verified), (new, later, new_verified)):
        for key, source in side.items():
            expected = {
                k: v
                for k, v in metrics.items()
                if k.contract_external_id in source.bundle.group.member_contract_keys
            }
            verified[key], _ = verify_source(
                source,
                expected,
                engine=engine,
                entity_code=entity_code,
                book_code=book_code,
                period_key=period_key,
                currency_view=currency_view,
                reporting_basis=earlier_reporting_basis if side is old else later_reporting_basis,
            )
    posted = tuple(line for source in old.values() for line in source.bundle.posted)
    if any(contract_key_from_subject(line.subject_key) not in old_owner for line in posted):
        raise _refuse("group-level posted amounts need an explicit redistribution basis.")
    heads = {
        name: head
        for source in old.values()
        for name, head in source.bundle.group.previous_stream_heads
    }
    for side, metrics in ((old, earlier), (new, later)):
        for key, source in side.items():
            members = source.bundle.group.member_contract_keys
            bundle = replace(source.bundle, known_at=cutoff, trigger="DRY_RUN")
            if side is new:
                bundle = replace(
                    bundle,
                    posted=tuple(
                        line
                        for line in posted
                        if contract_key_from_subject(line.subject_key) in members
                    ),
                    group=replace(
                        bundle.group,
                        previous_stream_heads=tuple(
                            sorted((name, heads[name]) for name in members if name in heads)
                        ),
                    ),
                )
            output = engine(bundle)
            if (
                output.input_sha256 != bundle.sha256()
                or output.engine_version != bundle.engine_version
            ):
                raise _refuse("a dry-run output does not identify its executed input.")
            actual = Projection(
                bundle,
                entity_code,
                book_code,
                period_key,
                currency_view,
                earlier_reporting_basis if side is old else later_reporting_basis,
            )(output)
            expected = {k: v for k, v in metrics.items() if k.contract_external_id in members}
            if any(
                actual.get(k, Fraction(0)) != expected.get(k, Fraction(0))
                for k in actual.keys() | expected.keys()
            ):
                raise _refuse("time/posting normalization does not reproduce the frozen endpoint.")
            if side is new:
                normalized[key] = bundle.sha256()
                period_end = next(
                    period.end_date
                    for entity in bundle.entities
                    if entity.code == entity_code
                    for period in entity.periods
                    if period.period_key == period_key
                )
                membership_events = tuple(
                    event_key
                    for event_key in added
                    if new_events[event_key].contract_key in members
                    and new_events[event_key].event_type == "COMBINATION_CHANGED"
                )
                business = sorted(
                    (
                        new_events[event_key]
                        for event_key in added
                        if new_events[event_key].contract_key in members
                        and new_events[event_key].event_type != "COMBINATION_CHANGED"
                    ),
                    key=lambda event: (event.effective_date, event.record_seq, event.event_key),
                )
                # Validate every driver before running the counterfactual sequence.
                event_runs = classified_runs(business, period_end, event_details=event_details)
                accumulated = [
                    event
                    for event in bundle.events
                    if event.event_key not in added or event.event_key in membership_events
                ]
                states: list[tuple[Execution, Metrics]] = []

                def evaluate(
                    name: str,
                    event_keys: tuple[str, ...],
                    phase_bundle: InputBundle,
                    phase_events: list[EventInput],
                    changed: tuple[str, ...] = (),
                    rate_basis: Basis | None = earlier_reporting_basis,
                ) -> tuple[Execution, Metrics]:
                    candidate = replace(
                        phase_bundle,
                        events=tuple(
                            sorted(
                                phase_events,
                                key=attrgetter("effective_date", "record_seq", "event_key"),
                            )
                        ),
                    )
                    result = engine(candidate)
                    if (
                        result.input_sha256 != candidate.sha256()
                        or result.engine_version != candidate.engine_version
                    ):
                        raise _refuse(
                            "a membership/event phase does not identify its executed input."
                        )
                    state = Projection(
                        candidate, entity_code, book_code, period_key, currency_view, rate_basis
                    )(result)
                    return (
                        Execution(name, event_keys, candidate.sha256(), result.sha256(), changed),
                        state,
                    )

                business_basis = replace(bundle, fx_rates=earlier_fx)
                membership_basis = prior_basis(business_basis)
                states.append(
                    evaluate(
                        "MODIFICATION",
                        membership_events,
                        membership_basis,
                        accumulated,
                        ("group.membership",),
                    )
                )
                changed_references = tuple(
                    field
                    for field in ("contracts", "books", "estimate_versions", *reference_fields)
                    if getattr(membership_basis, field) != getattr(business_basis, field)
                )
                if changed_references:
                    states.append(
                        evaluate("OTHER", (), business_basis, accumulated, changed_references)
                    )
                for name, events in event_runs:
                    accumulated.extend(events)
                    states.append(
                        evaluate(
                            name,
                            tuple(event.event_key for event in events),
                            business_basis,
                            accumulated,
                        )
                    )
                if earlier_fx != bundle.fx_rates:
                    states.append(evaluate("FX", (), bundle, accumulated, ("fx_rates",)))
                if currency_view == "reporting":
                    states.append(
                        evaluate(
                            "FX",
                            (),
                            bundle,
                            accumulated,
                            ("reporting_rates",),
                            later_reporting_basis,
                        )
                    )
                final = states[-1][1]
                if any(
                    final.get(k, Fraction(0)) != expected.get(k, Fraction(0))
                    for k in final.keys() | expected.keys()
                ):
                    raise _refuse("the final phased replay does not reproduce the frozen endpoint.")
                phases[key] = states
            else:
                baselines[key] = Execution(
                    "BASELINE", (), bundle.sha256(), output.sha256(), ("known_at",)
                )
    runs, aliases = {}, {}
    for name in sorted(old_owner):
        old_key, new_key = old_owner[name], new_owner[name]
        identity = uuid5(NAMESPACE_URL, f"erev:membership:{old_key}:{new_key}")
        aliases[name] = identity
        names = {n for n in old_owner if old_owner[n] == old_key and new_owner[n] == new_key}
        states = phases[new_key]
        metric_keys = set(earlier) | set(later)
        for _, state in states:
            metric_keys.update(state)
        measures = {}
        for metric in sorted(metric_keys):
            if metric.contract_external_id not in names:
                continue
            change = decompose_steps(
                earlier.get(metric, Fraction(0)),
                [
                    (step.driver, step.event_keys, state.get(metric, Fraction(0)))
                    for step, state in states
                ],
                event_details=event_details,
            )
            if not change.sums_exactly or change.metric_after != later.get(metric, Fraction(0)):
                raise _refuse("membership/event effects do not reconcile to the frozen change.")
            measures[metric] = change
        input_hash = normalized[new_key]
        runs[identity] = RetainedReplay(
            old_verified[old_key],
            new_verified[new_key],
            ("group.membership", "posted", "group.previous_stream_heads"),
            input_hash,
            Replay(
                new[new_key].bundle.engine_version,
                (baselines[old_key], *(step for step, _ in states)),
                MappingProxyType(measures),
                (earlier_reporting_basis.evidence_sha256, later_reporting_basis.evidence_sha256)
                if earlier_reporting_basis is not None and later_reporting_basis is not None
                else None,
            ),
        )
    return runs, aliases
