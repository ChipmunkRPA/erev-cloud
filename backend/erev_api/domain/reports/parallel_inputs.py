"""Versioned retained comparison facts; replay never consults mutable source tables.

The report worker must authorize the current requester before using this codec.
The expected digest and context come from the server-owned run binding, not callers.
"""

import json
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any
from uuid import UUID

from erev_engine.canonical import sha256_hex
from pydantic import TypeAdapter, ValidationError

from erev_api.domain.reports.parallel_comparison import Comparison, Period, Snapshot, compare
from erev_api.problems import Problem
from erev_api.uow import UnitOfWork

_ADAPTER = TypeAdapter(Snapshot)


def context(
    *, tenant_id: UUID, migration_id: UUID, entity_ids: tuple[UUID, ...], known_at: datetime
) -> dict[str, Any]:
    if known_at.tzinfo is None or not entity_ids or len(set(entity_ids)) != len(entity_ids):
        raise _refuse("an aware cutoff and unique nonempty entity scope are required.")
    return {
        "tenant_id": str(tenant_id),
        "migration_id": str(migration_id),
        "entity_ids": sorted(str(value) for value in entity_ids),
        "known_at": known_at.isoformat(),
    }


def _refuse(detail: str) -> Problem:
    return Problem("validation-failed", f"Parallel-run retained inputs: {detail}")


def _encode(snapshot: Snapshot) -> dict[str, Any]:
    value = _ADAPTER.dump_python(snapshot, mode="json")
    # A frozenset's iteration order must not affect the retained digest.
    value["periods"] = sorted(
        value["periods"],
        key=lambda item: tuple(
            item[key] for key in ("entity_code", "book_code", "currency", "key", "start", "end")
        ),
    )
    return dict(value)


def retain(
    *,
    scope: Mapping[str, Any],
    legacy: Snapshot,
    actual: Snapshot,
    migration_evidence: Mapping[str, Any],
    actual_evidence: Mapping[str, Any],
) -> dict[str, Any]:
    compare(legacy, actual)
    for evidence in (migration_evidence, actual_evidence):
        for key in ("tenant_id", "entity_ids", "known_at"):
            if evidence.get(key) != scope.get(key):
                raise _refuse("source evidence differs from the run scope.")
    if migration_evidence.get("migration_id") != scope.get("migration_id"):
        raise _refuse("the migration identity differs from the run.")
    if (
        actual_evidence.get("expected_source") != {"id": legacy.source_id, "sha256": legacy.sha256}
        or sha256_hex(actual_evidence) != actual.sha256
    ):
        raise _refuse("the actual source is not bound to the legacy comparison input.")
    # JSON round-trip detaches mutable dictionaries from the reader's lifetime.
    return dict(
        json.loads(
            json.dumps(
                {
                    "version": 1,
                    "scope": dict(scope),
                    "legacy": _encode(legacy),
                    "actual": _encode(actual),
                    "migration_evidence": dict(migration_evidence),
                    "actual_evidence": dict(actual_evidence),
                }
            )
        )
    )


def rebuild(
    retained: Mapping[str, Any], *, expected_sha256: str, scope: Mapping[str, Any]
) -> Comparison:
    if sha256_hex(retained) != expected_sha256:
        raise _refuse("the saved input digest differs from the run binding.")
    if retained.get("version") != 1 or retained.get("scope") != dict(scope):
        raise _refuse("the saved input version or run scope differs.")
    try:
        legacy = _ADAPTER.validate_json(json.dumps(retained["legacy"]))
        actual = _ADAPTER.validate_json(json.dumps(retained["actual"]))
        canonical = retain(
            scope=scope,
            legacy=legacy,
            actual=actual,
            migration_evidence=retained["migration_evidence"],
            actual_evidence=retained["actual_evidence"],
        )
        if canonical != retained:
            raise _refuse("the saved input contains unsupported or noncanonical facts.")
    except (KeyError, TypeError, ValueError, ValidationError) as error:
        raise _refuse("the saved input is malformed.") from error
    return compare(legacy, actual)


def capture(
    uow: UnitOfWork,
    *,
    migration_id: UUID,
    entity_ids: tuple[UUID, ...],
    known_at: datetime,
    periods: tuple[Period, ...] | None = None,
    from_period_key: str | None = None,
    to_period_key: str | None = None,
) -> dict[str, Any]:
    """Compose authorized source readers into a detached, replayable input bundle.

    Period ranges resolve against calendars and recorded open states. Currency comes
    from the original import evidence because the legacy database has no currency column.
    """
    from erev_api.domain.migration import parallel_legacy
    from erev_api.domain.reports import parallel_actual, parallel_periods, parallel_sources
    from erev_api.domain.reports.builders import ReportParams

    scope = context(
        tenant_id=uow.principal.tenant_id,
        migration_id=migration_id,
        entity_ids=entity_ids,
        known_at=known_at,
    )
    admitted = parallel_sources.read_for_report(
        uow,
        migration_id,
        entity_ids=entity_ids,
        known_at=known_at,
    )
    if periods is not None and (from_period_key is not None or to_period_key is not None):
        raise _refuse("choose either explicit periods or period range parameters.")
    if periods is None:
        periods = parallel_periods.resolve(
            uow,
            ReportParams(
                "parallel_run_comparison",
                1,
                {"from_period_key": from_period_key, "to_period_key": to_period_key},
                entity_ids,
                known_at,
                historical=True,
            ),
            migration_evidence=admitted.evidence,
        )
    cutover = admitted.evidence.get("cutover_date")
    if cutover is None or any(p.start <= date.fromisoformat(cutover) for p in periods):
        raise _refuse("comparison periods must start after the migration cutover.")
    if any(period.currency != admitted.evidence["reporting_currency"] for period in periods):
        raise _refuse("comparison currency differs from the original import.")
    legacy = parallel_legacy.snapshot(
        admitted.rows,
        source_id=f"migration:{migration_id}:file:{admitted.evidence['file_id']}",
        periods=periods,
        entity_mapping=admitted.entity_mapping,
    )
    actual = parallel_actual.read(
        uow,
        expected=legacy,
        entity_ids=entity_ids,
        known_at=known_at,
    )
    return retain(
        scope=scope,
        legacy=legacy,
        actual=actual.snapshot,
        migration_evidence={
            **admitted.evidence,
            "requested_periods": [
                {
                    "entity": p.entity_code,
                    "book": p.book_code,
                    "currency": p.currency,
                    "key": p.key,
                    "start": p.start.isoformat(),
                    "end": p.end.isoformat(),
                }
                for p in sorted(periods)
            ],
        },
        actual_evidence=actual.evidence,
    )
