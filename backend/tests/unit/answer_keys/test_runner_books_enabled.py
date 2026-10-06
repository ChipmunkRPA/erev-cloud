"""Engine runner: POL-007 ``books.enabled`` is the entity's ``books`` (lane L5-5; dev-guide §9.5.3
``entities[].books``, DG-AK-23; POLICIES POL-005, POL-007; ENGINE_SPEC_B S13-INV-05).

The keys' world build never carried POL-007, so every book resolved the framework default
{``ASC606``}. Under POL-005 ``DELTA`` stage 13 then raised S13-INV-05 "POL-005 DELTA requires the
LEGACY book in POL-007" although the entity computes ASC606 and LEGACY
(DLT-NATIVE-SUBSCRIPTION-PRE-STANDARD-UPFRONT).
"""

from __future__ import annotations

from erev_engine.bundle import BookInput, ResolvedPolicyInput
from support.answer_keys.loader import ANSWER_KEY_ROOT, LoadedKey, load
from support.answer_keys.runners import _build_checkpoint_bundles

DLT = "DLT-NATIVE-SUBSCRIPTION-PRE-STANDARD-UPFRONT"


def _load(key_id: str) -> LoadedKey:
    family = key_id.split("-", 1)[0].lower()
    return load(ANSWER_KEY_ROOT / family / f"{key_id}.yaml")


def _enabled(book: BookInput) -> dict[str, ResolvedPolicyInput]:
    return {
        policy.subject_key: policy
        for policy in book.policies
        if policy.code == "books.enabled" and policy.scope == "PERIOD"
    }


def test_books_enabled_is_the_entity_books() -> None:
    checkpoint = _build_checkpoint_bundles(_load(DLT))[0]
    books = {book.book_code: book for book in checkpoint.bundles[0].books}
    assert sorted(books) == ["ASC606", "LEGACY"]
    for book in books.values():
        enabled = _enabled(book)
        assert enabled, book.book_code
        for subject, policy in enabled.items():
            assert subject.startswith("US01@FY")
            assert (policy.value, policy.level, policy.pin) == (
                {"primary": "ASC606", "set": "ASC606,LEGACY"},
                "E",
                "P",
            )
