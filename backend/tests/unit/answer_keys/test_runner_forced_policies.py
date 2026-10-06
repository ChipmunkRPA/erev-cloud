"""Engine runner: a FORCED framework value admits no key value for that book (lane L5-5; POLICIES §1
"FORCED"; erev_api.registry.resolve.resolve and is_forced).

The platform resolver answers ``framework_default`` for a code forced in the book, whatever the
tenant, entity, book, product, contract or obligation values say (``LEGACY`` follows the ASC 606
flags). The keys' world build overlaid the tenant value on every book, so
``pob.shipping_as_fulfilment: TRUE`` reached the IFRS15 book, where POL-021 is ``FALSE FORCED``,
and the shipping line merged into its host there (IFRS-SW04, IFRS-S13-SWITCH-SHIPPING).
"""

from __future__ import annotations

from erev_engine.bundle import BookInput
from erev_engine.stages.state import PolicyResolver
from support.answer_keys.loader import ANSWER_KEY_ROOT, LoadedKey, load
from support.answer_keys.runners import _build_checkpoint_bundles

SW04 = "IFRS-SW04-SHIPPING-FULFILMENT-ELECTION-VS-SEPARATE-OBLIGATION"


def _load(key_id: str) -> LoadedKey:
    family = key_id.split("-", 1)[0].lower()
    return load(ANSWER_KEY_ROOT / family / f"{key_id}.yaml")


def _books(key_id: str) -> dict[str, BookInput]:
    checkpoint = _build_checkpoint_bundles(_load(key_id))[0]
    return {book.book_code: book for book in checkpoint.bundles[0].books}


def test_a_forced_framework_value_ignores_the_tenant_value() -> None:
    books = _books(SW04)
    code = "pob.shipping_as_fulfilment"
    us = PolicyResolver(books["ASC606"].policies).resolved(code, contract="C-IFRS-SW04")
    ifrs = PolicyResolver(books["IFRS15"].policies).resolved(code, contract="C-IFRS-SW04")
    # POL-021: the ASC606 election is the tenant's; IFRS15 is FALSE FORCED.
    assert (us.value, us.level) == ("TRUE", "T")
    assert (ifrs.value, ifrs.level) == ("FALSE", "DEFAULT")
