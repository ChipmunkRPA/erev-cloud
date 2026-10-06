"""Stage 06 record and lineage (ENGINE_SPEC S06-R-16; POL-106; REQ-MOD-020, REQ-MOD-022).

Every obligation of the modified contract receives a version: the obligations with a new segment
take their changed state, and every other obligation of the contract records the modification
key. After a 25-13(a) boundary, ``lineage_pre_modification`` of each obligation with a boundary
segment lists the subject keys of the obligations identified before the modification, which stage
08 uses to route later changes of VC promised before the modification (606-10-32-45; FASB
Example 6). Private to stage 06. Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence

from erev_engine.stages.state import AllocatedState, ObligationState

__all__ = ["pre_modification", "record"]


def pre_modification(existing: Sequence[ObligationState]) -> tuple[str, ...]:
    """Subject keys of the obligations identified before the modification, sorted."""
    return tuple(sorted(ob.subject_key for ob in existing))


def record(
    st: AllocatedState,
    contract_key: str,
    modification_key: str,
    changed: Mapping[str, ObligationState],
    added: Sequence[ObligationState],
) -> tuple[ObligationState, ...]:
    """Every obligation of the group after the modification, in subject-key order."""
    known = {ob.subject_key for ob in st.obligations}
    for ob in added:
        if ob.subject_key in known:
            raise ValueError(f"{ob.subject_key} is added by a modification but already exists")
    result: list[ObligationState] = []
    for ob in st.obligations:
        if ob.subject_key in changed:
            result.append(changed[ob.subject_key])
        elif ob.contract_key == contract_key:
            result.append(dataclasses.replace(ob, last_modification_key=modification_key))
        else:
            result.append(ob)
    result.extend(added)
    return tuple(sorted(result, key=lambda ob: ob.subject_key))
