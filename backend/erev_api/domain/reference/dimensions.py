"""Dimensions (04 T-REF-16, T-REF-17, DB-12, §14.3; 03 REQ-REF-009; SCREENS_B §9.5; BUILD_SPEC
RFD-6).

The built-in dimensions, the custom-dimension limit and the code rules. Provisioning writes
``builtin_dimension_rows`` in the tenant's provisioning transaction; the reference commands apply
the rules. This module imports no other domain module, so provisioning can import it.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Final
from uuid import UUID

from erev_api.db import new_id

RULE_DIMENSION: Final = "T-REF-16"
RULE_VALUE: Final = "T-REF-17"
RULE_CUSTOM_LIMIT: Final = "DB-12"
# 04 T-REF-16 ``ck_dimension_definition__code``.
DIMENSION_CODE: Final = re.compile(r"^[a-z][a-z0-9_]{1,31}$")
# 04 T-REF-16 and §14.3: the built-in dimensions in display and export order (positions 1 to 5);
# the names are the SCREENS_B §9.5 labels.
BUILTIN_DIMENSIONS: Final[tuple[tuple[str, str], ...]] = (
    ("department", "Department"),
    ("class", "Class"),
    ("location", "Location"),
    ("product", "Product"),
    ("customer", "Customer"),
)
# DB-12; REQ-REF-009.
MAX_CUSTOM_DIMENSIONS: Final = 5
# 04 T-REF-17: product and customer values are ``product.code`` and ``customer.code``.
UNSTORED_VALUE_DIMENSIONS: Final = frozenset({"product", "customer"})
# Key of the transaction-level advisory lock that the DB-12 trigger also takes.
CUSTOM_LIMIT_LOCK: Final = "erev.dimension_definition:{tenant_id}"

# SCREENS_B §9.5 copy.
CUSTOM_LIMIT_REACHED: Final = "A workspace can define at most five custom dimensions."
DIMENSION_CODE_FORMAT: Final = (
    "Use 2 to 32 lowercase letters, digits or underscores, starting with a letter."
)
DIMENSION_CODE_TAKEN: Final = "Another dimension already uses this code."
VALUE_CODE_TAKEN: Final = "Another value of this dimension already uses this code."
VALUES_NOT_STORED: Final = (
    "The values of {code} are the codes of the workspace's {plural}. They are not entered here."
)
PARENT_UNKNOWN: Final = "Choose a value of this dimension."
PARENT_CYCLE: Final = "A value cannot sit below itself."
_PLURALS: Final = {"product": "products", "customer": "customers"}


def builtin_dimension_rows(tenant_id: UUID, *, stamp: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The five built-in ``dimension_definition`` rows of a new tenant (04 §14.3)."""
    return [
        {
            "tenant_id": tenant_id,
            "id": new_id(),
            "code": code,
            "name": name,
            "is_builtin": True,
            "position": position,
            "is_active": True,
            **stamp,
        }
        for position, (code, name) in enumerate(BUILTIN_DIMENSIONS, start=1)
    ]


def values_not_stored(code: str) -> str:
    """The refusal copy for ``POST /dimensions/{code}/values`` of product or customer."""
    return VALUES_NOT_STORED.format(code=code, plural=_PLURALS.get(code, code))
