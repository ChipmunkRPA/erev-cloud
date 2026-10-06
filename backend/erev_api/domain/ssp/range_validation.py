"""SSP range validation at publication (POLICIES §3.3 POL-073, CHK-031, U-02; 04 table 15.4-C
``RANGE_TOO_WIDE``, ``COVERAGE_TOO_LOW``, ``COVERAGE_UNKNOWN``; PRD §5.5 IMP-56 to IMP-58,
BR-SSP-05; dev-guide DG-AK-45, §9.5.6 ``exceptions.subject``; BUILD_SPEC RFD-13, BS3-D-11).

``validate_ranges`` is pure and imports no database module, so the SSP publication command and the
answer-key runner evaluate ranges through the same function (DG-AK-45).

For each range row, a band holding low, mid and high values, the half-width is
h = max(high − mid, mid − low) ÷ mid, and when the row carries the statistics of its attached
population the coverage is c = inside ÷ observations. Under POL-073 ``ssp.range_validation``:

- h above ``max_half_width_pct`` gives ``RANGE_TOO_WIDE``;
- c not above ``min_coverage_pct`` gives ``COVERAGE_TOO_LOW`` (coverage must be strictly greater);
- a row without a population gives ``COVERAGE_UNKNOWN``.

The severity is ``WARNING`` under ``mode = WARN`` and ``ERROR`` under ``BLOCK``. The legacy parity
value ``NOT_ENFORCED`` gives no finding. A band lacking a low, mid or high value is not a range and
is skipped. [J] A row whose mid value is not positive has no half-width; it is too wide unless its
low, mid and high values are equal. One finding is kept per code and subject.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Context, Decimal
from types import MappingProxyType
from typing import Final

PARAMETER: Final = "ssp.range_validation"  # POL-073
NOT_ENFORCED: Final = "NOT_ENFORCED"
MODE_WARN: Final = "WARN"
MODE_BLOCK: Final = "BLOCK"
WARNING: Final = "WARNING"
ERROR: Final = "ERROR"
RANGE_TOO_WIDE: Final = "RANGE_TOO_WIDE"
COVERAGE_TOO_LOW: Final = "COVERAGE_TOO_LOW"
COVERAGE_UNKNOWN: Final = "COVERAGE_UNKNOWN"
# 04 §15.4: the POL-073 mode gives the finding severity.
SEVERITY: Final[Mapping[str, str]] = MappingProxyType({MODE_WARN: WARNING, MODE_BLOCK: ERROR})
# Wide enough that no difference or ratio of two NUMERIC(38,18) values is rounded.
_WIDE: Final = Context(prec=80)
_PERCENT: Final = Decimal(100)
_ONE_DECIMAL: Final = Decimal("0.1")

# PRD §5.5 IMP-56 to IMP-58; [J] NO_MIDPOINT is copy the documents leave open.
TOO_WIDE: Final = "{label}: the range extends {width}% from the midpoint, above the {limit}% limit."
NO_MIDPOINT: Final = (
    "{label}: the range has no positive midpoint, so it extends above the {limit}% limit."
)
TOO_LOW: Final = "Fewer than {limit}% of observations fall inside the range ({coverage}%)."
UNKNOWN: Final = (
    "{label}: no transaction population is attached, so range coverage cannot be checked."
)


@dataclass(frozen=True, slots=True)
class Population:
    """The statistics of the standalone transactions attached to a range (04 T-REF-33)."""

    observation_count: int
    inside_count: int

    def __post_init__(self) -> None:
        if self.observation_count < 1 or not 0 <= self.inside_count <= self.observation_count:
            raise ValueError("a population has at least one observation and 0 to that many inside")


@dataclass(frozen=True, slots=True)
class RangeRow:
    """One band to validate. ``subject`` names the finding's object; ``label`` names the product in
    the message."""

    subject: str
    label: str
    low_value: Decimal | None
    mid_value: Decimal | None
    high_value: Decimal | None
    population: Population | None = None


@dataclass(frozen=True, slots=True)
class RangeValidation:
    """A POL-073 value other than ``NOT_ENFORCED``."""

    max_half_width_pct: Decimal
    min_coverage_pct: Decimal
    mode: str


@dataclass(frozen=True, slots=True)
class RangeFinding:
    """One 04 table 15.4-C finding with the statistics it rests on."""

    code: str
    severity: str
    subject: str
    message: str
    half_width: Decimal | None
    coverage: Decimal | None


def parse_policy(value: object) -> RangeValidation | None:
    """The POL-073 value: None for ``NOT_ENFORCED``; ``ValueError`` for a malformed value."""
    if value == NOT_ENFORCED:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{PARAMETER} is NOT_ENFORCED or an object, not {value!r}")
    mode = value.get("mode")
    if mode not in SEVERITY:
        raise ValueError(f"{PARAMETER}.mode is WARN or BLOCK, not {mode!r}")
    try:
        width = Decimal(str(value["max_half_width_pct"]))
        coverage_limit = Decimal(str(value["min_coverage_pct"]))
    except (KeyError, ArithmeticError) as error:
        raise ValueError(
            f"{PARAMETER} needs decimal max_half_width_pct and min_coverage_pct"
        ) from error
    return RangeValidation(width, coverage_limit, str(mode))


def half_width(low: Decimal, mid: Decimal, high: Decimal) -> Decimal | None:
    """h = max(high − mid, mid − low) ÷ mid; None when mid is not positive (POLICIES §3.3)."""
    if mid <= 0:
        return None
    spread = max(_WIDE.subtract(high, mid), _WIDE.subtract(mid, low))
    return _WIDE.divide(spread, mid)


def coverage(population: Population) -> Decimal:
    """c = inside ÷ observations (POLICIES §3.3)."""
    return _WIDE.divide(Decimal(population.inside_count), Decimal(population.observation_count))


def _limit(ratio: Decimal) -> str:
    """A threshold ratio as a percentage without trailing zeros: 0.20 gives "20"."""
    percent = _WIDE.multiply(ratio, _PERCENT).normalize(_WIDE)
    return format(percent, "f")


def _measured(ratio: Decimal) -> str:
    """A measured ratio as a percentage with one decimal, half up: 0.41025… gives "41.0"."""
    return format(_WIDE.multiply(ratio, _PERCENT).quantize(_ONE_DECIMAL, ROUND_HALF_UP), "f")


def validate_ranges(rows: Iterable[RangeRow], policy: object) -> tuple[RangeFinding, ...]:
    """The POL-073 findings of ``rows`` in row order: ``RANGE_TOO_WIDE``, then ``COVERAGE_TOO_LOW``
    or ``COVERAGE_UNKNOWN``, once per code and subject."""
    settings = parse_policy(policy)
    if settings is None:
        return ()
    severity = SEVERITY[settings.mode]
    width_limit = _limit(settings.max_half_width_pct)
    findings: list[RangeFinding] = []
    seen: set[tuple[str, str]] = set()

    def add(code: str, row: RangeRow, message: str, h: Decimal | None, c: Decimal | None) -> None:
        if (code, row.subject) in seen:
            return
        seen.add((code, row.subject))
        findings.append(RangeFinding(code, severity, row.subject, message, h, c))

    for row in rows:
        low, mid, high = row.low_value, row.mid_value, row.high_value
        if low is None or mid is None or high is None:
            continue
        h = half_width(low, mid, high)
        c = None if row.population is None else coverage(row.population)
        if h is None:
            if not low == mid == high:
                add(
                    RANGE_TOO_WIDE,
                    row,
                    NO_MIDPOINT.format(label=row.label, limit=width_limit),
                    h,
                    c,
                )
        elif h > settings.max_half_width_pct:
            message = TOO_WIDE.format(label=row.label, width=_measured(h), limit=width_limit)
            add(RANGE_TOO_WIDE, row, message, h, c)
        if c is None:
            add(COVERAGE_UNKNOWN, row, UNKNOWN.format(label=row.label), h, c)
        elif c <= settings.min_coverage_pct:
            message = TOO_LOW.format(limit=_limit(settings.min_coverage_pct), coverage=_measured(c))
            add(COVERAGE_TOO_LOW, row, message, h, c)
    return tuple(findings)


def finding_json(finding: RangeFinding) -> dict[str, str | None]:
    """A finding as audit detail: the statistics as decimal text."""
    return {
        "code": finding.code,
        "severity": finding.severity,
        "subject": finding.subject,
        "message": finding.message,
        "half_width": None if finding.half_width is None else format(finding.half_width, "f"),
        "coverage": None if finding.coverage is None else format(finding.coverage, "f"),
    }
