"""Chart of accounts (04 T-REF-13, API-R-20; 03 REQ-REF-007, REQ-REF-009; PRD §2.6; BUILD_SPEC
RFD-6).

``applicable`` and ``missing_dimensions`` are the checks journal line validation applies to an
account (REQ-JE-022, CTL-020); the reference commands create and change accounts.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import gl_account
from erev_api.schemas.accounts import GlAccountOut

RULE_ACCOUNT: Final = "T-REF-13"
CODE_TAKEN: Final = "Another account already uses this code."
ENTITY_REPEATED: Final = "List each entity once."
DIMENSION_REPEATED: Final = "List each dimension once."
DIMENSION_UNKNOWN: Final = "Use the codes of active dimensions. Not found: {codes}."


def applicable(session: Session, *, code: str, entity_id: UUID) -> bool:
    """Whether entity ``entity_id`` may post to account ``code``.

    [J] An account applies when it is active and its ``entity_ids`` are empty (all entities) or
    name the entity. An unknown or inactive account applies to no entity (SCREENS_B §9.5: journal
    generation fails for a deactivated account; L1-1-Q-9).
    """
    statement = select(gl_account.c.entity_ids, gl_account.c.is_active).where(
        gl_account.c.code == code
    )
    row = session.execute(statement).mappings().first()
    if row is None or not row["is_active"]:
        return False
    entity_ids = list(row["entity_ids"])
    return not entity_ids or entity_id in entity_ids


def missing_dimensions(
    account: GlAccountOut | Mapping[str, Any], dimensions: Mapping[str, str | None]
) -> list[str]:
    """The account's required dimension codes that have no value in ``dimensions``, in the
    account's order (REQ-REF-009). ``account`` is an API-R-20 account body or row."""
    required = (
        account.required_dimensions
        if isinstance(account, GlAccountOut)
        else account["required_dimensions"]
    )
    return [str(code) for code in required if not dimensions.get(str(code))]
