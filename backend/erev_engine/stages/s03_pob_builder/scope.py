"""Stage 03 scope routing and repurchase outcomes (ENGINE_SPEC S03-R-11, S03-R-12; PT-09).

Private to stage 03. ``apply`` records a reviewed ``REPURCHASE_CLASSIFICATION`` outcome (POL-233)
and flags a ``LEASE_842`` line as routed out. ``split`` keeps ``IN_SCOPE_606`` and ``LEASE_842``
lines as allocation targets and returns every other scope flag as excluded from obligations
(POL-230, POL-234), whose ``out_of_scope_amount`` stage 04 removes first (S04-R-03). Standard
library only (DG-ARC-02).
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from typing import Final

from erev_engine.enums import ScopeFlag
from erev_engine.stages.s02_contract_identification import IdentifiedState
from erev_engine.stages.s03_pob_builder.distinct import obligation_judgement
from erev_engine.stages.s03_pob_builder.templates import PobDraft
from erev_engine.stages.state import BookContext

__all__ = ["ALLOCATION_TARGET_FLAGS", "REPURCHASE_OUTCOMES", "apply", "split"]

# S03-R-11: flags that stay allocation targets (PT-09 keeps LEASE_842 in the allocation).
ALLOCATION_TARGET_FLAGS: Final = frozenset({ScopeFlag.IN_SCOPE_606, ScopeFlag.LEASE_842})
# Table 0.4-A REPURCHASE_CLASSIFICATION outcomes (POL-233; 606-10-55-66 to 55-78).
REPURCHASE_OUTCOMES: Final = frozenset({"FINANCING", "LEASE", "RIGHT_OF_RETURN", "SALE"})


def apply(ctx: BookContext, st: IdentifiedState, draft: PobDraft) -> PobDraft:
    """S03-R-12, then S03-R-11: outcome ``LEASE`` sets ``LEASE_842``; ``LEASE_842`` is routed out.

    ``FINANCING``, ``RIGHT_OF_RETURN`` and ``SALE`` keep the scope flag and are carried for stage 09
    (ENGINE_SPEC_B S09-R-13). Any other outcome raises ``ValueError`` (CV-45).
    """
    header = st.canonical.contracts[draft.contract_key].header
    record = obligation_judgement(
        header, "REPURCHASE_CLASSIFICATION", ctx.book_code, draft.obligation_key
    )
    outcome = None if record is None else record.outcome.get("outcome")
    if record is not None and outcome not in REPURCHASE_OUTCOMES:
        raise ValueError(f"{record.judgement_key}: outcome is not a POL-233 repurchase outcome")
    flag = ScopeFlag.LEASE_842 if outcome == "LEASE" else draft.scope_flag
    return dataclasses.replace(
        draft,
        scope_flag=flag,
        routed_out=flag == ScopeFlag.LEASE_842,
        repurchase_outcome=outcome,
    )


def split(drafts: Sequence[PobDraft]) -> tuple[list[PobDraft], list[PobDraft]]:
    """(allocation targets, lines excluded from obligations by their scope flag) (S03-R-11)."""
    kept = [draft for draft in drafts if draft.scope_flag in ALLOCATION_TARGET_FLAGS]
    routed = [draft for draft in drafts if draft.scope_flag not in ALLOCATION_TARGET_FLAGS]
    return kept, routed
