"""Accounting books (04 T-REF-02, T-REF-03, E-02, §14.3; 03 REQ-BK-001; D-24; SCREENS_B
SF-15:entities; BUILD_SPEC RFD-2).

A tenant has the three E-02 books, written by provisioning: ``ASC606`` primary and enabled, posting
to the primary general ledger; ``IFRS15`` disabled, posting to a secondary ledger; ``LEGACY``
disabled, posting nothing, because its lines leave only through ``DELTA`` runs (E-32). An entity
keeps the primary book from its creation and other books from ``PUT /entities/{id}/books/{code}``.
This module is pure: no database and no clock.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Final
from uuid import UUID

from erev_api.db import new_id
from erev_api.enums import BookCode
from erev_api.problems import ProblemError

RULE_BOOK: Final = "T-REF-02"
RULE_ENTITY_BOOK: Final = "T-REF-03"
POSTING_TARGETS: Final = ("GL_PRIMARY", "GL_SECONDARY", "NONE")
# SCREENS_B SF-15:entities "Books" column labels.
BOOK_NAMES: Final[Mapping[BookCode, str]] = MappingProxyType(
    {BookCode.ASC606: "ASC 606", BookCode.IFRS15: "IFRS 15", BookCode.LEGACY: "Legacy"}
)
# 04 §14.3: (code, is_primary, is_enabled, posting_target), in provisioning order.
SEED: Final[tuple[tuple[BookCode, bool, bool, str], ...]] = (
    (BookCode.ASC606, True, True, "GL_PRIMARY"),
    (BookCode.IFRS15, False, False, "GL_SECONDARY"),
    (BookCode.LEGACY, False, False, "NONE"),
)
LEGACY_TARGET: Final = (
    "The Legacy book posts nothing to the general ledger, so its posting target stays NONE."
)
PRIMARY_ENABLED: Final = "The primary book stays enabled."
BOOK_KEPT: Final = "Entities keep this book: {codes}. Disable it for them first."
PRIMARY_KEPT: Final = "Every entity keeps the primary book."
FIRST_PERIOD_FIXED: Final = "The first period of a book an entity keeps does not change."
NOT_KEPT: Final = "The entity does not keep this book."
PERIOD_UNKNOWN: Final = "Use the key of a period of the entity's calendar, such as FY2026-P01."
# 04 T-REF-03 rev 1.123; PRD ERR-61 (supervisor ruling R-58 (b)).
FIRST_PERIOD_AFTER_CONTRACT: Final = (
    "{entity} has a contract that began on {date} ({contract}), before {period_key} starts. "
    "Keep {book} from a period that starts on or before that date."
)
# 04 T-REF-03 rev 1.123; PRD ERR-62 (supervisor ruling R-61 (f), STEP1-BOOK-ADOPTION-1).
CONTRACT_BEHIND_GATE: Final = (
    "{contract} is not yet a contract under Step 1. "
    "Activate or void it before {entity} keeps {book}."
)


def book_rows(tenant_id: UUID, *, stamp: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The 04 §14.3 ``book`` rows of a new tenant."""
    return [
        {
            "tenant_id": tenant_id,
            "id": new_id(),
            "code": code.value,
            "name": BOOK_NAMES[code],
            "is_primary": is_primary,
            "is_enabled": is_enabled,
            "posting_target": posting_target,
            **stamp,
        }
        for code, is_primary, is_enabled, posting_target in SEED
    ]


def posting_target_errors(code: BookCode, posting_target: str) -> list[ProblemError]:
    """T-REF-02 ``CHECK (code <> 'LEGACY' OR posting_target = 'NONE')``."""
    if code is BookCode.LEGACY and posting_target != "NONE":
        return [ProblemError(field="posting_target", rule_id=RULE_BOOK, message=LEGACY_TARGET)]
    return []
