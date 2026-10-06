"""Golden parity comparison (docs/dev-guide.md §9.6 DG-PAR-07; docs/legacy/DEVIATIONS.md §2.2;
D-17; BUILD_SPEC GPA-1).

Unit-level amounts and quantities pass when ``|exact − Fraction(expected)| ≤ 1/10000``. Journal
amounts pass only when they equal the expected amount exactly to the cent. Codes, counts and texts
must be equal. Negative zero equals zero, and an expected ``null`` requires a null actual. Expected
values are the ``deviations.json`` strings and are never edited (DG-PAR-09).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Any, Final

__all__ = [
    "JOURNAL_TOLERANCE",
    "UNIT_TOLERANCE",
    "Mismatch",
    "ParityMismatchError",
    "exact_equal",
    "fraction_of",
    "journal_equal",
    "render",
    "unit_equal",
    "unit_fields",
]

UNIT_TOLERANCE: Final = Fraction(1, 10000)
JOURNAL_TOLERANCE: Final = Fraction(0)
_RENDER_PLACES: Final = 12


@dataclass(frozen=True, slots=True)
class Mismatch:
    """One DG-PAR-08 mismatch: the field, the expected and actual values and the legacy value."""

    field: str
    expected: Any
    actual: Any
    legacy: Any

    def to_json(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "expected": self.expected,
            "actual": render(self.actual),
            "legacy": self.legacy,
        }


class ParityMismatchError(AssertionError):
    """A case whose actual values differ from ``deviations.json`` beyond the DG-PAR-07 rules."""

    def __init__(self, case_id: str, mismatches: Sequence[Mismatch]) -> None:
        self.case_id = case_id
        self.mismatches = tuple(mismatches)
        lines = [
            f"{item.field}: expected {item.expected}, actual {render(item.actual)}, "
            f"legacy {item.legacy}"
            for item in self.mismatches
        ]
        super().__init__(f"{case_id}: {len(lines)} mismatches\n" + "\n".join(lines))


def fraction_of(value: object) -> Fraction:
    """An exact fraction of a decimal string, integer, ``Decimal`` or ``Fraction``."""
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool) or not isinstance(value, str | int | Decimal):
        raise TypeError(f"not a decimal amount: {value!r}")
    return Fraction(Decimal(str(value)))


def render(value: object) -> Any:
    """A JSON value for the report: a fraction as a decimal string at up to 12 places."""
    if not isinstance(value, Fraction):
        return value
    if value.denominator == 1:
        return str(value.numerator)
    places = Decimal(value.numerator) / Decimal(value.denominator)
    text = format(places.quantize(Decimal(1).scaleb(-_RENDER_PLACES)), "f").rstrip("0")
    return text.rstrip(".")


def unit_equal(actual: Fraction | None, expected: object) -> bool:
    """DG-PAR-07 unit-level amount or quantity."""
    if expected is None or actual is None:
        return expected is None and actual is None
    return abs(actual - fraction_of(expected)) <= UNIT_TOLERANCE


def journal_equal(actual: Fraction | None, expected: object) -> bool:
    """DG-PAR-07 journal amount: equal to the cent, and the actual amount holds whole cents."""
    if expected is None or actual is None:
        return expected is None and actual is None
    return (actual * 100).denominator == 1 and actual == fraction_of(expected)


def exact_equal(actual: object, expected: object) -> bool:
    """DG-PAR-07 codes, counts and texts."""
    return bool(actual == expected)


def unit_fields(
    expected: Mapping[str, Any], actual: Mapping[str, Fraction | None], legacy: Mapping[str, Any]
) -> list[Mismatch]:
    """Every expected unit-level field whose actual value is outside the D-17 tolerance."""
    return [
        Mismatch(field=name, expected=value, actual=actual.get(name), legacy=legacy.get(name))
        for name, value in expected.items()
        if not unit_equal(actual.get(name), value)
    ]
