"""Numeric evidence check for AI narratives (AIA-11; DG-AI-07).

The caller supplies values from authorized trace nodes/cited cells and the currency's
minor unit. This validates numeric membership, not semantic support or citation access.
Percentages must be supplied in displayed units; no implicit ratio/percentage conversion.
Only valid ISO calendar dates are exempt. Other identifier digits are checked conservatively.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from erev_engine.money import round_half_up

MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_VALUES = 10000
MAX_NUMBER_LENGTH = 128
_LOCALES = {"en-US": (".", ","), "de-DE": (",", "."), "fr-FR": (",", " ")}
_DATE = re.compile(r"(?<![\w./+-])\d{4}-\d{2}-\d{2}(?![\w/+-]|\.\d)", re.ASCII)
# Capture malformed grouping as one token rather than accepting its smaller pieces.
_TOKEN = re.compile(r"[+\-−]?(?:\d[\d.,]*(?:[eE][+\-]?\d+)?|[.,]\d+)")


@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    code: str | None
    numbers: tuple[Decimal, ...] = ()


def _bounded(value: Decimal) -> bool:
    _, digits, exponent = value.as_tuple()
    return (
        value.is_finite()
        and isinstance(exponent, int)
        and len(digits) + abs(exponent) <= MAX_NUMBER_LENGTH
    )


def validate_numbers(
    text: str,
    allowed: Iterable[Decimal | int],
    *,
    minor_unit: int,
    locale: str = "en-US",
) -> ValidationResult:
    """Return a fixed refusal code for unsupported/untraced model figures.

    Invalid trusted configuration raises ValueError. No float conversion or local
    rounding is used: both sides use the engine's currency-aware half-up kernel.
    The caller must discard the entire narrative on ``valid=False``.
    """
    if type(minor_unit) is not int or not 0 <= minor_unit <= 18 or locale not in _LOCALES:
        raise ValueError("AI_INVALID_NUMBER_CONFIGURATION")
    evidence: set[int] = set()
    for index, value in enumerate(allowed):
        if index >= MAX_VALUES or type(value) not in (int, Decimal):
            raise ValueError("AI_INVALID_NUMBER_EVIDENCE")
        number = Decimal(value)
        if not _bounded(number):
            raise ValueError("AI_INVALID_NUMBER_EVIDENCE")
        evidence.add(round_half_up(number, minor_unit))
    try:
        if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
            return ValidationResult(False, "AI_NARRATIVE_TOO_LARGE")
    except UnicodeEncodeError:
        return ValidationResult(False, "AI_INVALID_ENCODING")
    if any(char.isnumeric() and not char.isdecimal() for char in text):
        return ValidationResult(False, "AI_UNSUPPORTED_NUMBER")
    normalized = unicodedata.normalize("NFKC", text).replace("−", "-")
    # Unicode decimal digits are normalized explicitly; other numeric glyphs refuse.
    normalized_chars: list[str] = []
    for char in normalized:
        if char.isdecimal():
            normalized_chars.append(str(unicodedata.decimal(char)))
        elif char.isnumeric():
            return ValidationResult(False, "AI_UNSUPPORTED_NUMBER")
        else:
            normalized_chars.append(char)
    normalized = "".join(normalized_chars)

    def hide_date(match: re.Match[str]) -> str:
        try:
            date.fromisoformat(match.group())
        except ValueError:
            return match.group()
        return " " * len(match.group())

    normalized = _DATE.sub(hide_date, normalized)
    if re.search(r"\d\s*[/⁄]\s*\d", normalized):
        return ValidationResult(False, "AI_UNSUPPORTED_NUMBER")
    decimal, grouping = _LOCALES[locale]
    if grouping != " " and re.search(r"\d\s+\d", normalized):
        return ValidationResult(False, "AI_UNSUPPORTED_NUMBER")
    token_pattern = _TOKEN
    if grouping == " ":
        token_pattern = re.compile(r"[+\-]?(?:\d(?:[\d.,]| (?=\d))*(?:[eE][+\-]?\d+)?|[.,]\d+)")
    integer = rf"(?:[0-9]+|[0-9]{{1,3}}(?:{re.escape(grouping)}[0-9]{{3}})+)"
    grammar = re.compile(rf"[+-]?{integer}(?:{re.escape(decimal)}[0-9]+)?")
    numbers: list[Decimal] = []
    for index, match in enumerate(token_pattern.finditer(normalized)):
        if index >= MAX_VALUES:
            return ValidationResult(False, "AI_TOO_MANY_NUMBERS")
        token = match.group()
        # A sentence-ending dot/comma is punctuation, not a decimal separator.
        if token[-1:] in {".", ","}:
            token = token[:-1]
        if len(token) > MAX_NUMBER_LENGTH or grammar.fullmatch(token) is None:
            return ValidationResult(False, "AI_UNSUPPORTED_NUMBER")
        value = Decimal(token.replace(grouping, "").replace(decimal, "."))
        # Scan only adjacent whitespace/currency markers; do not copy whole prefixes.
        left, right = match.start() - 1, match.end()
        while left >= 0 and normalized[left].isspace():
            left -= 1
        if left >= 0 and normalized[left] in "$€£¥":
            left -= 1
        elif left >= 2 and re.fullmatch(r"[A-Z]{3}", normalized[left - 2 : left + 1]):
            left -= 3
        while left >= 0 and normalized[left].isspace():
            left -= 1
        if left >= 0 and normalized[left] in "+-":
            return ValidationResult(False, "AI_UNSUPPORTED_NUMBER")
        while right < len(normalized) and normalized[right].isspace():
            right += 1
        if (
            left >= 0
            and normalized[left] == "("
            and right < len(normalized)
            and normalized[right] == ")"
        ):
            if token.startswith(("-", "+")):
                return ValidationResult(False, "AI_UNSUPPORTED_NUMBER")
            value = value.copy_negate()
        numbers.append(value)
        if round_half_up(value, minor_unit) not in evidence:
            return ValidationResult(False, "AI_UNTRACED_FIGURE", tuple(numbers))
    return ValidationResult(True, None, tuple(numbers))
