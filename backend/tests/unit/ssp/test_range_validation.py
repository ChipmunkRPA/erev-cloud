"""SSP range validation at publication (POLICIES §3.3 POL-073, CHK-031; 04 table 15.4-C; PRD §5.5
IMP-56 to IMP-58, J-02.5; dev-guide DG-AK-45; BUILD_SPEC RFD-13, BS3-D-11)."""

from __future__ import annotations

import ast
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import pytest
from erev_api.domain.ssp import range_validation
from erev_api.domain.ssp.range_validation import (
    COVERAGE_TOO_LOW,
    COVERAGE_UNKNOWN,
    ERROR,
    RANGE_TOO_WIDE,
    WARNING,
    Population,
    RangeFinding,
    RangeRow,
    coverage,
    half_width,
    parse_policy,
    validate_ranges,
)
from erev_api.registry.policies import POLICY_PARAMETERS

SUBJECT = "ssp:SSP-MAIN:2026-07-01:LIC-31"
WARN = {"max_half_width_pct": "0.20", "min_coverage_pct": "0.50", "mode": "WARN"}
BLOCK = {**WARN, "mode": "BLOCK"}
STDLIB = frozenset({"__future__", "collections.abc", "dataclasses", "decimal", "types", "typing"})


def row(
    low: str | None,
    mid: str | None,
    high: str | None,
    population: Population | None = None,
    *,
    subject: str = SUBJECT,
) -> RangeRow:
    def value(text: str | None) -> Decimal | None:
        return None if text is None else Decimal(text)

    return RangeRow(
        subject=subject,
        label="LIC-31",
        low_value=value(low),
        mid_value=value(mid),
        high_value=value(high),
        population=population,
    )


def summary(findings: Sequence[RangeFinding]) -> list[tuple[object, ...]]:
    return [(f.code, f.severity, f.subject, f.half_width, f.coverage) for f in findings]


def test_chk_031_range_validation_at_publication() -> None:
    # First row: ±15% around 160.00 with 23 of 40 inside passes (h 0.15, c 0.575).
    narrow = row("136.00", "160.00", "184.00", Population(40, 23))
    assert half_width(Decimal("136.00"), Decimal("160.00"), Decimal("184.00")) == Decimal("0.15")
    assert coverage(Population(40, 23)) == Decimal("0.575")
    assert validate_ranges([narrow], WARN) == ()
    assert validate_ranges([narrow], BLOCK) == ()

    # Second row: ±25% with 20 of 40 inside is too wide (h 0.25) and covers too little (c 0.50 is
    # not greater than 0.50).
    wide = row("120.00", "160.00", "200.00", Population(40, 20))
    warned = validate_ranges([wide], WARN)
    assert summary(warned) == [
        (RANGE_TOO_WIDE, WARNING, SUBJECT, Decimal("0.25"), Decimal("0.5")),
        (COVERAGE_TOO_LOW, WARNING, SUBJECT, Decimal("0.25"), Decimal("0.5")),
    ]
    assert [finding.message for finding in warned] == [
        "LIC-31: the range extends 25.0% from the midpoint, above the 20% limit.",
        "Fewer than 50% of observations fall inside the range (50.0%).",
    ]
    blocked = validate_ranges([wide], BLOCK)
    assert [(f.code, f.severity) for f in blocked] == [
        (RANGE_TOO_WIDE, ERROR),
        (COVERAGE_TOO_LOW, ERROR),
    ]

    # Both rows under distinct subjects: only the second row gives findings.
    both = validate_ranges(
        [narrow, row("120.00", "160.00", "200.00", Population(40, 20), subject="b")], WARN
    )
    assert [(f.code, f.subject) for f in both] == [(RANGE_TOO_WIDE, "b"), (COVERAGE_TOO_LOW, "b")]


def test_coverage_unknown_outside_parity() -> None:
    spec = POLICY_PARAMETERS[range_validation.PARAMETER]
    unattached = row("136.00", "160.00", "184.00")
    findings = validate_ranges([unattached], spec.default_asc606)
    assert summary(findings) == [(COVERAGE_UNKNOWN, WARNING, SUBJECT, Decimal("0.15"), None)]
    assert findings[0].message == (
        "LIC-31: no transaction population is attached, so range coverage cannot be checked."
    )
    assert spec.legacy_parity_value == "NOT_ENFORCED"
    assert validate_ranges([unattached], spec.legacy_parity_value) == ()
    assert (
        validate_ranges([row("120.00", "160.00", "200.00", Population(40, 1))], "NOT_ENFORCED")
        == ()
    )


def test_boundaries_rows_and_copy() -> None:
    # h equal to the limit passes; c must be strictly greater than the limit.
    assert validate_ranges([row("128.00", "160.00", "192.00", Population(100, 51))], WARN) == ()
    at_limit = validate_ranges([row("128.00", "160.00", "192.00", Population(100, 50))], WARN)
    assert [f.code for f in at_limit] == [COVERAGE_TOO_LOW]

    # PRD J-02.5: 16 of the 39 non-excluded observations inside 95,200.00 to 128,800.00.
    j02 = validate_ranges([row("95200.00", "112000.00", "128800.00", Population(39, 16))], WARN)
    assert summary(j02) == [
        (COVERAGE_TOO_LOW, WARNING, SUBJECT, Decimal("0.15"), coverage(Population(39, 16)))
    ]
    assert j02[0].message == "Fewer than 50% of observations fall inside the range (41.0%)."

    # A band without low, mid and high is not a range; an asymmetric range uses the wider side.
    assert validate_ranges([row(None, None, None), row(None, "160.00", None)], WARN) == ()
    assert half_width(Decimal("150.00"), Decimal("160.00"), Decimal("200.00")) == Decimal("0.25")

    # [J] A mid value that is not positive has no half-width: too wide unless the band is a point.
    zero = validate_ranges([row("0", "0", "10", Population(10, 9))], WARN)
    assert summary(zero) == [(RANGE_TOO_WIDE, WARNING, SUBJECT, None, Decimal("0.9"))]
    assert zero[0].message == (
        "LIC-31: the range has no positive midpoint, so it extends above the 20% limit."
    )
    assert validate_ranges([row("0", "0", "0", Population(10, 10))], WARN) == ()

    # One finding per code and subject: a second wide band of the subject adds nothing.
    twice = validate_ranges(
        [row("100", "160", "220"), row("110", "160", "210")],
        {"max_half_width_pct": "0.125", "min_coverage_pct": "0.6", "mode": "BLOCK"},
    )
    assert [(f.code, f.severity) for f in twice] == [
        (RANGE_TOO_WIDE, ERROR),
        (COVERAGE_UNKNOWN, ERROR),
    ]
    assert (
        twice[0].message
        == "LIC-31: the range extends 37.5% from the midpoint, above the 12.5% limit."
    )
    assert range_validation.finding_json(twice[0]) == {
        "code": RANGE_TOO_WIDE,
        "severity": ERROR,
        "subject": SUBJECT,
        "message": twice[0].message,
        "half_width": "0.375",
        "coverage": None,
    }


def test_malformed_policy_and_population() -> None:
    assert parse_policy("NOT_ENFORCED") is None
    assert parse_policy(WARN) == range_validation.RangeValidation(
        Decimal("0.20"), Decimal("0.50"), "WARN"
    )
    for value in (
        "WARN",
        {**WARN, "mode": "SOMETIMES"},
        {"mode": "WARN", "min_coverage_pct": "0.50"},
        {**WARN, "max_half_width_pct": "wide"},
    ):
        with pytest.raises(ValueError, match="ssp.range_validation"):
            validate_ranges([row("136", "160", "184")], value)
    for observations, inside in ((0, 0), (40, 41), (40, -1)):
        with pytest.raises(ValueError, match="population"):
            Population(observations, inside)


def test_helper_imports_no_database_module() -> None:
    # DG-AK-45: the helper is pure, so the runner and the publication command share it.
    path = Path(range_validation.__file__)
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    assert modules <= STDLIB, sorted(modules - STDLIB)
