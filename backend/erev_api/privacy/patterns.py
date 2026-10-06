"""05 PRV-08 AI minimisation patterns (BUILD_SPEC SOP-5; 03 REQ-AI-009; 05 AIA-04 step 4).

REQ-AI-009 redaction replaces e-mail addresses and phone numbers with ``[email]`` and ``[phone]``
before any provider call; this module holds the patterns and the replacement, and nothing else.
It is a kernel module with no imports from the rest of ``erev_api`` (DG-LAY-03), so the AI
adapter, the prompt builders and the tests share one definition.

Scope and limits, stated so that the privacy owner can review them rather than infer them:

- E-mail: a practical RFC 5322 subset — a local part of word characters and ``. + % -``, an ``@``,
  one or more domain labels and a top-level label of two or more letters. Bare local parts, IP
  literals and quoted local parts are not matched.
- Phone, North American form: ``(415) 555-0100``, ``415-555-0100``, ``415.555.0100`` and
  ``415 555 0100`` (three, three and four digits with one separator kind), not inside a longer
  digit run.
- Phone, international form: a leading ``+``, a country code and 7 to 15 digits in all, separated
  by spaces, hyphens or parentheses only, not followed by a decimal or thousands continuation
  (``.5`` or ``,5``).
- Not matched, by construction: amounts (``1,234,567.89``, ``+1 234 567.89``), ISO and slashed
  dates, document numbers (``INV-2026-000123``), UUIDs, IBANs, percentages, and local numbers
  without a ``+`` outside the North American form. A tenant whose numbers use another local form
  gets no redaction for them; that limit is recorded in the lane record, not silently widened.

E-mails are replaced first, so an address with a numeric local part is one ``[email]`` and never a
partial ``[phone]``; the international form is replaced before the North American one.
Replacement is idempotent: the placeholders contain no digits or ``@``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

__all__ = [
    "EMAIL",
    "EMAIL_PLACEHOLDER",
    "PHONE_INTERNATIONAL",
    "PHONE_NORTH_AMERICAN",
    "PHONE_PLACEHOLDER",
    "Redaction",
    "redact",
    "redact_text",
    "redact_value",
]

EMAIL_PLACEHOLDER: Final = "[email]"
PHONE_PLACEHOLDER: Final = "[phone]"

EMAIL: Final = re.compile(
    r"(?<![\w.+%-])"  # not the tail of a longer token
    r"[\w.+%-]+@"  # local part
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?\.)+"  # domain labels
    r"[A-Za-z]{2,}"  # top-level label
    r"(?![\w-])"
)
# Three, three and four digits with one separator kind, or a parenthesised area code.
PHONE_NORTH_AMERICAN: Final = re.compile(
    r"(?<![\w+])"
    r"(?:\(\d{3}\)[ .-]?\d{3}[ .-]\d{4}"
    r"|\d{3}( |\.|-)\d{3}\1\d{4})"
    r"(?![\w.,]?\d)"  # not a longer digit run and not a decimal or thousands continuation
)
# ``+`` country code and digit groups; the digit total is checked in code (7 to 15, E.164).
# Up to two separator characters between digits admit ``+49 (30) 901820``.
PHONE_INTERNATIONAL: Final = re.compile(r"(?<![\w+])\+\d(?:[ \-()]{0,2}\d){6,14}(?![\w]|[.,]\d)")
_MIN_DIGITS: Final = 7
_MAX_DIGITS: Final = 15


@dataclass(frozen=True, slots=True)
class Redaction:
    """A redacted text and how many e-mail and phone matches were replaced."""

    text: str
    emails: int
    phones: int

    @property
    def changed(self) -> bool:
        return bool(self.emails or self.phones)


def _international_replacement(match: re.Match[str]) -> str:
    digits = sum(character.isdigit() for character in match.group(0))
    return PHONE_PLACEHOLDER if _MIN_DIGITS <= digits <= _MAX_DIGITS else match.group(0)


def redact(text: str) -> Redaction:
    """Replace every e-mail address and phone number in ``text`` (05 PRV-08)."""
    redacted, emails = EMAIL.subn(EMAIL_PLACEHOLDER, text)
    # International first: ``+1 415 555 0100`` is one number, not a ``+1`` and a North American one.
    international = sum(
        _international_replacement(match) == PHONE_PLACEHOLDER
        for match in PHONE_INTERNATIONAL.finditer(redacted)
    )
    redacted = PHONE_INTERNATIONAL.sub(_international_replacement, redacted)
    redacted, north_american = PHONE_NORTH_AMERICAN.subn(PHONE_PLACEHOLDER, redacted)
    return Redaction(text=redacted, emails=emails, phones=international + north_american)


def redact_text(text: str) -> str:
    """``redact(text).text``."""
    return redact(text).text


def redact_value(value: Any) -> Any:
    """Redact every string inside a JSON-like value: mapping values (keys untouched), sequence
    items and strings; other scalars are returned unchanged."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {key: redact_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [redact_value(item) for item in value]
    return value
