"""The answer-key runner evaluates SSP populations through DG-AK-45 (docs/dev-guide.md §9.5.3
``ssp_books.population``, §9.5.6 ``exceptions.subject``, §9.5.8 DG-AK-45; POLICIES §3.3 CHK-031;
BUILD_SPEC RFD-13, BS3-D-11)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import erev_engine
import pytest
from erev_api.domain.ssp import range_validation
from support.answer_keys.loader import ANSWER_KEY_ROOT, LoadedKey, load
from support.answer_keys.runners import (
    ABSENT,
    CheckpointBundles,
    CheckpointRun,
    _CheckpointComparison,
    assert_checkpoints,
    population_findings,
    run_engine,
)

KEY = "SSP-CHK-031-RANGE-VALIDATION-AT-PUBLICATION"
SUBJECT = "ssp:SSP-MAIN:2026-07-01:LIC-31"


def _load() -> LoadedKey:
    return load(ANSWER_KEY_ROOT / "ssp" / f"{KEY}.yaml")


def _refuse(_bundle: object) -> object:
    raise AssertionError("compute must not run")


def test_dg_ak_45_chk_031() -> None:
    """AKS-1: the CHK-031 population rows through ``validate_ranges``, compared through the
    checkpoint ``exceptions`` rows with ``subject``, and the key through the real engine."""
    loaded = _load()
    world = loaded.key.world
    (book,) = world.ssp_books
    first, second = (version.entries[0] for version in book.versions)
    policy = world.policies.tenant[range_validation.PARAMETER]

    def row(entry: object, label: str) -> range_validation.RangeRow:
        band = entry.ranges[0]  # type: ignore[attr-defined]
        population = entry.population  # type: ignore[attr-defined]
        return range_validation.RangeRow(
            subject=f"ssp:{book.code}:{label}:LIC-31",
            label="LIC-31",
            low_value=Decimal(band.low_value),
            mid_value=Decimal(band.mid_value),
            high_value=Decimal(band.high_value),
            population=range_validation.Population(
                int(population.observation_count), int(population.inside_count)
            ),
        )

    narrow, wide = row(first, "2026-01-01"), row(second, "2026-07-01")
    # Midpoint 160.00, ±15%, 23 of 40 inside: h 0.15 and c 0.575 pass POL-073 (0.20, > 0.50).
    assert narrow.mid_value == Decimal("160.00")
    assert range_validation.half_width(narrow.low_value, narrow.mid_value, narrow.high_value) == (
        Decimal("0.15")
    )
    assert range_validation.coverage(narrow.population) == Decimal("0.575")
    assert range_validation.validate_ranges([narrow], policy) == ()
    # ±25%, 20 of 40 inside: h 0.25 is too wide, and c 0.50 is not greater than 0.50.
    assert range_validation.half_width(wide.low_value, wide.mid_value, wide.high_value) == (
        Decimal("0.25")
    )
    assert range_validation.coverage(wide.population) == Decimal("0.5")
    findings = population_findings(loaded)
    assert findings == range_validation.validate_ranges([narrow, wide], policy)
    assert [(f.code, f.severity, f.subject, f.half_width, f.coverage) for f in findings] == [
        ("RANGE_TOO_WIDE", "WARNING", SUBJECT, Decimal("0.25"), Decimal("0.5")),
        ("COVERAGE_TOO_LOW", "WARNING", SUBJECT, Decimal("0.25"), Decimal("0.5")),
    ]
    # Each finding meets its checkpoint exceptions row with subject ssp:<book>:<label>:<product>.
    checkpoint = loaded.key.checkpoints[0]
    rows = [row for row in checkpoint.exceptions or () if row.subject is not None]
    assert [(r.code, r.severity, r.subject) for r in rows] == [
        (f.code, f.severity, f.subject) for f in findings
    ]
    result = run_engine(loaded)
    assert result.range_findings == findings
    assert_checkpoints(loaded, result)  # the booked licence and both subject rows pass


def test_run_engine_population_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(erev_engine, "compute", _refuse, raising=False)
    loaded = _load()
    findings = population_findings(loaded)
    assert [(f.code, f.severity, f.subject) for f in findings] == [
        ("RANGE_TOO_WIDE", "WARNING", SUBJECT),
        ("COVERAGE_TOO_LOW", "WARNING", SUBJECT),
    ]
    assert [(f.half_width, f.coverage) for f in findings] == [(Decimal("0.25"), Decimal("0.5"))] * 2


def test_run_engine_carries_population_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    # run_engine keeps its signature; its result carries the findings next to the computations.
    computed: list[object] = []
    monkeypatch.setattr(erev_engine, "compute", computed.append, raising=False)
    loaded = _load()
    result = run_engine(loaded)
    assert result.range_findings == population_findings(loaded)
    assert len(computed) == sum(len(run.checkpoint.bundles) for run in result.checkpoints)


def test_parity_preset_and_tenant_value() -> None:
    loaded = _load()
    world = loaded.key.world
    # Without a tenant value the preset decides: DEFAULT gives POL-073 WARN, parity NOT_ENFORCED.
    unset = world.policies.model_copy(update={"tenant": {}})
    default = world.model_copy(update={"policies": unset})
    parity = default.model_copy(
        update={"tenant": world.tenant.model_copy(update={"preset": "LEGACY_PARITY"})}
    )
    blocked = world.policies.model_copy(
        update={
            "tenant": {
                range_validation.PARAMETER: {
                    "max_half_width_pct": "0.30",
                    "min_coverage_pct": "0.40",
                    "mode": "BLOCK",
                }
            }
        }
    )

    def with_world(new_world: object) -> LoadedKey:
        key = loaded.key.model_copy(update={"world": new_world})
        return LoadedKey(key, loaded.path, loaded.sha256)

    assert [f.code for f in population_findings(with_world(default))] == [
        "RANGE_TOO_WIDE",
        "COVERAGE_TOO_LOW",
    ]
    assert population_findings(with_world(parity)) == ()
    # Under 0.30 and 0.40 the ±25% row passes; nothing else is evaluated.
    assert population_findings(with_world(world.model_copy(update={"policies": blocked}))) == ()


def test_subject_rows_compare_range_findings() -> None:
    loaded = _load()
    checkpoint = loaded.key.checkpoints[0]
    assert checkpoint.exceptions is not None
    bundles = CheckpointBundles(
        name=checkpoint.name,
        after_seq=checkpoint.after_seq,
        as_of=date(2026, 2, 28),
        book=checkpoint.book,
        known_at=datetime(2026, 2, 28, tzinfo=UTC),
        bundles=(),
    )
    run = CheckpointRun(bundles, ())
    findings = population_findings(loaded)

    def mismatches(given: tuple[range_validation.RangeFinding, ...]) -> list[tuple[str, str, str]]:
        comparison = _CheckpointComparison(loaded.key, checkpoint, run, (), given)
        comparison.exceptions(checkpoint.exceptions or ())
        return [(m.subject, m.expected, m.actual) for m in comparison.found]

    assert mismatches(findings) == []
    assert mismatches(()) == [
        (f"exception RANGE_TOO_WIDE {SUBJECT}", f"RANGE_TOO_WIDE WARNING {SUBJECT}", ABSENT),
        (f"exception COVERAGE_TOO_LOW {SUBJECT}", f"COVERAGE_TOO_LOW WARNING {SUBJECT}", ABSENT),
    ]
    other = range_validation.RangeFinding(
        "RANGE_TOO_WIDE", "WARNING", "ssp:SSP-MAIN:2026-01-01:LIC-31", "wide", None, None
    )
    unknown = range_validation.RangeFinding(
        "COVERAGE_UNKNOWN", "WARNING", SUBJECT, "none", None, None
    )
    assert mismatches((*findings, other, unknown)) == [
        (
            "exception RANGE_TOO_WIDE ssp:SSP-MAIN:2026-01-01:LIC-31",
            ABSENT,
            "RANGE_TOO_WIDE WARNING ssp:SSP-MAIN:2026-01-01:LIC-31",
        )
    ]
    blocking = tuple(
        range_validation.RangeFinding(f.code, "ERROR", f.subject, f.message, None, None)
        for f in findings
    )
    assert [actual for _, _, actual in mismatches(blocking)] == [
        ABSENT,
        ABSENT,
        f"RANGE_TOO_WIDE ERROR {SUBJECT}",
        f"COVERAGE_TOO_LOW ERROR {SUBJECT}",
    ]
