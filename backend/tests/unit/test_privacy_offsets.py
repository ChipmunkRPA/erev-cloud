"""Source citations survive length-changing PRV-08 redaction without guessing."""

from __future__ import annotations

import pytest
from erev_api.privacy.patterns import redact, redact_with_offsets


@pytest.mark.parametrize(
    "contact", ["long.name@example.com", "a@b.co", "+49 (30) 901820", "415-555-0100"]
)
def test_spans_before_after_and_across_a_contact(contact: str) -> None:
    original = f"Café 😀 {contact} owes 120.00."
    mapped = redact_with_offsets(original)
    text = mapped.redaction.text
    for selected in ("Café 😀", "owes 120.00.", text):
        start = text.index(selected)
        left, right = mapped.original_span(start, start + len(selected))
        assert original[left:right] == (original if selected == text else selected)
    start = text.index("[")
    end = text.index("]") + 1
    left, right = mapped.original_span(start, end)
    assert original[left:right] == contact
    assert mapped.redaction == redact(original)
    assert contact not in repr(mapped)
    with pytest.raises(ValueError, match="AMBIGUOUS_REDACTED_SPAN"):
        mapped.original_span(start + 1, end)
    with pytest.raises(ValueError, match="AMBIGUOUS_REDACTED_SPAN"):
        mapped.original_span(start, end - 1)


def test_multiple_phases_and_contacts_preserve_every_visible_word() -> None:
    original = "zero 415-555-0100 one a@b.co two +49 (30) 901820 three long.name@example.com four"
    mapped = redact_with_offsets(original)
    assert mapped.redaction.emails == 2
    assert mapped.redaction.phones == 2
    for word in ("zero", "one", "two", "three", "four"):
        start = 0 if word == "zero" else mapped.redaction.text.index(f" {word}") + 1
        left, right = mapped.original_span(start, start + len(word))
        assert original[left:right] == word
        assert left == original.index(word)
    assert mapped.original_span(0, len(mapped.redaction.text)) == (0, len(original))


@pytest.mark.parametrize("span", [(-1, 2), (0, 0), (2, 1), (0, 100), (True, 2)])
def test_invalid_spans_refused(span: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="INVALID_REDACTED_SPAN"):
        redact_with_offsets("abc").original_span(*span)


def test_literal_placeholder_and_noncontact_figures_are_unchanged() -> None:
    original = "[email] invoice INV-2026-000123: 1,234,567.89 on 2026-10-14"
    mapped = redact_with_offsets(original)
    assert mapped.redaction.text == original
    assert mapped.original_span(1, 3) == (1, 3)
