"""Which T-REF-15 rules a group's bundle carries (05 RCP-15 rev 1.168; dev-guide DG-CMD-04 rev
1.217; item MAP-RULE-FOREIGN-1): the predicate of ``bundles._account_mapping``. A rule that names
a product or an entity is carried only by a bundle that holds what it names; the database
witnesses are ``tests/domain/contracts/test_bundle_account_mapping.py``.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from erev_api.domain.contracts import bundles

US01, DE01 = UUID(int=1), UUID(int=2)
LICENCE, SUPPORT = UUID(int=11), UUID(int=12)
ENTITIES = {US01: "US01"}
PRODUCTS = {LICENCE: "LICENCE-X"}


@pytest.mark.parametrize(
    ("entity_id", "product_id", "carried"),
    [
        (None, None, True),
        (None, LICENCE, True),
        (US01, None, True),
        (US01, LICENCE, True),
        (None, SUPPORT, False),
        (DE01, None, False),
        (US01, SUPPORT, False),
        (DE01, LICENCE, False),
        (str(US01), str(LICENCE), True),  # a row read as text names the same entity and product
        (str(DE01), None, False),
    ],
)
def test_a_rule_is_carried_when_the_bundle_holds_what_it_names(
    entity_id: UUID | str | None, product_id: UUID | str | None, carried: bool
) -> None:
    rule = {"entity_id": entity_id, "product_id": product_id}
    assert bundles._rule_in_bundle(rule, ENTITIES, PRODUCTS) is carried
