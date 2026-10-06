"""Stage 14 account resolution (ENGINE_SPEC_B §14.2.4 S14-R-09, S14-R-14; 04 T-REF-15; END-6).

Private to stage 14 (DG-ENG-07). The override key of a line is its role literal, or
``BILLING_CLEARING:<purpose>`` for a clearing line. Resolution order (T-REF-15):

1. the obligation's account override for the key; stage 03 merges the template version's
   ``account_role_overrides`` into ``ObligationState.account_overrides`` below the line's own
   overrides, so steps 1 and 2 read one mapping (L2-5-Q-33);
3. the rule of the mapping version pinned for the computation (``BookContext.mapping``) that matches
   the role and clearing purpose exactly and whose entity, book, product and revenue category are
   absent or equal to the line's, highest ``specificity``, then highest ``priority``;
4. otherwise ``ACCOUNT_MAPPING_MISSING`` (``ERROR``): nothing posts (REQ-JE-022; DEV-042).

A mapping change therefore never reposts history: posted amounts carry no account, and a new delta
resolves with the version pinned for its computation (S14-R-09). Every resolved line has an
``account_resolution`` node (§14.6). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.s14_posting.targets import RoleKey
from erev_engine.stages.state import AllocatedState, BookContext, Finding, ObligationState
from erev_engine.trace import SourceRef, TraceBuilder

__all__ = ["ACCOUNT_MAPPING_MISSING", "Resolution", "emit", "missing", "override_key", "resolve"]

ACCOUNT_MAPPING_MISSING: Final = "ACCOUNT_MAPPING_MISSING"
STAGE: Final = 14
OVERRIDE_STEP: Final = 1
RULE_STEP: Final = 3


@dataclass(frozen=True, slots=True)
class Resolution:
    """The account of a line and how T-REF-15 found it."""

    account_code: str
    step: int  # 1 override, 3 mapping rule
    source: SourceRef  # the override or the mapping rule
    default_dimensions: Mapping[str, str]  # of the resolved rule (T-REF-15)


def override_key(account_role: str, clearing_purpose: str | None) -> str:
    """``<role>`` or ``BILLING_CLEARING:<purpose>`` (T-REF-15, rev 1.1)."""
    return account_role if clearing_purpose is None else f"{account_role}:{clearing_purpose}"


def resolve(
    ctx: BookContext,
    obligation: ObligationState | None,
    key: RoleKey,
    *,
    subject_scope: tuple[str | None, str | None] = (None, None),
) -> Resolution | None:
    """The account of a role key's line, or None when T-REF-15 finds none (S14-R-14).

    ``subject_scope`` is the (product, revenue category) of a line whose subject is not an
    obligation, the JET rule R3 dimensions its contract's obligations share (L5-5-Q-8).
    """
    label = override_key(key.account_role, key.clearing_purpose)
    if obligation is not None:
        code = obligation.account_overrides.get(label)
        if code is not None:
            ref_id = f"{obligation.subject_key}#account_overrides/{label}"
            source = SourceRef("source_record", ref_id, {"value": str(OVERRIDE_STEP)})
            return Resolution(code, OVERRIDE_STEP, source, {})
    product = subject_scope[0] if obligation is None else obligation.product_code
    category = subject_scope[1] if obligation is None else obligation.revenue_category
    candidates = [
        rule
        for rule in ctx.mapping.rules
        if rule.account_role == key.account_role
        and rule.clearing_purpose == key.clearing_purpose
        and rule.entity_code in (None, key.entity)
        and rule.book_code in (None, key.book_code)
        and rule.product_code in (None, product)
        and rule.revenue_category in (None, category)
    ]
    if not candidates:
        return None
    best = min(candidates, key=lambda rule: (-rule.specificity, -rule.priority, rule.account_code))
    scope = best.product_code or best.revenue_category or "*"
    ref_id = (
        f"{ctx.mapping.version_key}/{label}/{best.entity_code or '*'}/{best.book_code or '*'}"
        f"/{scope}/{best.priority}"
    )
    source = SourceRef("rule", ref_id, {"value": str(RULE_STEP)})
    return Resolution(best.account_code, RULE_STEP, source, best.default_dimensions)


def missing(
    ctx: BookContext, st: AllocatedState, obligation: ObligationState | None, key: RoleKey
) -> Finding:
    """``ACCOUNT_MAPPING_MISSING`` naming contract, obligation, role, entity and book (S14-R-14)."""
    if obligation is not None:
        contract = obligation.contract_key
    else:
        contract = next(
            (
                view.header.external_id
                for view in st.contracts
                # CV-21: the subject is <encoded external id>@<encoded entity> (ENG-COST-ENC-1).
                if key.subject_key
                == contract_entity_subject_key(view.header.external_id, key.entity)
            ),
            st.group_code,
        )
    detail = {
        "book": key.book_code,
        "contract": contract,
        "entity": key.entity,
        "obligation": "" if obligation is None else obligation.obligation_key,
        "role": key.account_role,
        "rule": "S14-R-14",
    }
    if key.clearing_purpose is not None:
        detail["clearing_purpose"] = key.clearing_purpose
    return Finding(ACCOUNT_MAPPING_MISSING, "ERROR", key.subject_key, detail, STAGE, None)


def emit(
    ctx: BookContext, tb: TraceBuilder, resolution: Resolution, line_key: str, period_key: str
) -> str:
    """The ``account_resolution`` node of a line (§14.6)."""
    return tb.node(
        measure="account_resolution",
        subject_key=line_key,
        period_key=period_key,
        value=resolution.step,
        currency=None,
        minor_unit=None,
        formula_id="post.account_resolution.v1",
        inputs=[resolution.source],
        params={
            "account_code": resolution.account_code,
            "mapping_version_key": ctx.mapping.version_key,
            "step": str(resolution.step),
        },
        narrative_key="post.account_resolution",
    )
