"""Select original EAC versions with explicit, non-overlapping combined scope."""

from collections.abc import Sequence

from erev_engine.bundle import EstimateVersionInput
from erev_engine.errors import EngineError
from erev_engine.stages.state import ObligationState


def names(version: EstimateVersionInput) -> frozenset[str]:
    return frozenset(version.target_obligation_keys) | (
        frozenset((version.obligation_key,)) if version.obligation_key else frozenset()
    )


def select(
    versions: Sequence[EstimateVersionInput],
    ob: ObligationState,
    *,
    allow_incomplete: bool = False,
    strict: bool = True,
) -> tuple[EstimateVersionInput, ...]:
    members = frozenset(ob.combined_component_keys)
    found = tuple(v for v in versions if not names(v) or names(v) & members)
    if not members or not found:
        return tuple(versions) if not members else ()

    def fail(reason: str) -> None:
        raise EngineError(
            "ENGINE_INVARIANT_VIOLATED",
            reason,
            subject_key=ob.subject_key,
            detail={
                "rule": "COMBINED_EAC_SCOPE",
                "estimate_versions": ",".join(v.version_key for v in found),
            },
        )

    for version in found:
        if version.parameters.get("eac_scope") not in (None, "COMBINATION", "MEMBERS"):
            fail("Unknown EAC scope; specify COMBINATION or MEMBERS")
        if names(version) - members:
            fail("EAC scope includes members outside this combination")
    whole = tuple(v for v in found if v.parameters.get("eac_scope") == "COMBINATION")
    if whole:
        if len(whole) != 1:
            fail("More than one EAC covers the entire combination; clarify scope")
        return whole
    # Historical single-host EAC remains replayable. Multiple sources never inherit this
    # convention: the host must explicitly say MEMBERS before component aggregation.
    if (
        not strict
        and len(found) == 1
        and found[0].parameters.get("eac_scope") is None
        and (not names(found[0]) or names(found[0]) == {ob.obligation_key})
    ):
        return found
    covered: set[str] = set()
    for version in found:
        scope = names(version)
        if not scope or (
            ob.obligation_key in scope and version.parameters.get("eac_scope") != "MEMBERS"
        ):
            fail("Specify whether the host EAC covers MEMBERS or the entire COMBINATION")
        if covered & scope:
            fail("Member EAC scopes overlap; clarify scope before aggregation")
        covered.update(scope)
    if covered != members:
        if allow_incomplete:
            return ()
        fail("Member EAC scope is incomplete; provide EAC for every combined member")
    if len({v.currency for v in found}) != 1:
        fail("Combined member EAC currencies differ")
    return found


def for_obligations(
    versions: Sequence[EstimateVersionInput],
    obligations: Sequence[ObligationState],
    *,
    strict: bool = True,
) -> tuple[EstimateVersionInput, ...]:
    """Apply the same scope selection to loss and impairment totals."""
    chosen = list(versions)
    for ob in obligations:
        if not ob.combined_component_keys:
            continue
        members = frozenset(ob.combined_component_keys)
        candidates = [
            v for v in chosen if names(v) & members or (not names(v) and len(obligations) == 1)
        ]
        if not strict and not any(v.parameters.get("eac_scope") for v in candidates):
            continue
        selected = select(candidates, ob, strict=strict)
        discarded = {v.version_key for v in candidates if v not in selected}
        chosen = [v for v in chosen if v.version_key not in discarded]
    return tuple(chosen)
