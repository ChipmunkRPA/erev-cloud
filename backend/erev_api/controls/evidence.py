"""Control evidence registry SOP-1 (04 T-PLT-39; 03 REQ-CTL-002; CTL-042).

``RunRefType`` mirrors the T-PLT-39 ``run_ref_type`` check list (text with a check, not a 04 §3
E-enum: DG-ARC-09 pins ``erev_api.enums`` to the E-enums), including ``RECONCILIATION_RUN`` and
``PERIOD_LOCK`` from the supervisor rulings of 2026-09-19. ``validate_execution`` applies the
helper-side rules every producer shares (the shape agreed with lane F-CLO): a producer bug is a
``ValueError``, never a Problem. ``record_execution`` inserts the row (revision 0057 creates the
table; 0057 on 0056, assigned at merge prep 2026-09-20) stamped with the process release
(``controls.stamping.process_release_id``, D-98 60) and returns the new row id.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

from erev_engine import ENGINE_VERSION
from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from erev_api.controls.registry import controls
from erev_api.controls.release import current_environment, current_release
from erev_api.controls.stamping import process_release_id
from erev_api.db import new_id
from erev_api.db.tables import control_execution, engine_release
from erev_api.enums import BookCode, ControlResult
from erev_api.problems import Problem

if TYPE_CHECKING:
    from erev_api.uow import UnitOfWork

# 03 §4.1 control ids; the T-PLT-39 check is ``control_id ~ '^CTL-[0-9]{3}$'``.
CONTROL_ID: Final = re.compile(r"CTL-[0-9]{3}")


class RunRefType(StrEnum):
    """04 T-PLT-39 ``run_ref_type`` (rev 1.21, renumbered from 1.18 at the merge of 2026-09-20)."""

    CLOSE_RUN = "CLOSE_RUN"
    JOURNAL_RUN = "JOURNAL_RUN"
    IMPORT_UPLOAD = "IMPORT_UPLOAD"
    CONTRACT_COMPUTATION = "CONTRACT_COMPUTATION"
    REPORT_RUN = "REPORT_RUN"
    AUDIT_CHAIN_VERIFICATION = "AUDIT_CHAIN_VERIFICATION"
    SYNC_RUN = "SYNC_RUN"
    JOURNAL_BATCH = "JOURNAL_BATCH"
    RECONCILIATION_RUN = "RECONCILIATION_RUN"
    PERIOD_LOCK = "PERIOD_LOCK"
    PERIOD_STATE = "PERIOD_STATE"


@dataclass(frozen=True, slots=True)
class ExecutionRecord:
    """The validated values of one T-PLT-39 row before ``engine_release_id`` and ``executed_at``,
    which the helper fills from the release stamp and ``uow.now``."""

    control_id: str
    run_ref_type: RunRefType
    run_ref_id: UUID
    population_count: int
    exception_count: int
    result: ControlResult
    detail: Mapping[str, Any]
    exceptions_file_id: UUID | None
    entity_id: UUID | None
    book_code: BookCode | None
    period_id: UUID | None


def _count(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative int")
    return value


def _optional_uuid(name: str, value: object) -> UUID | None:
    if value is None or isinstance(value, UUID):
        return value
    raise ValueError(f"{name} must be a UUID or None")


def _check_detail(value: object) -> None:
    """Strict JSON below the top level of ``detail`` (Codex P4-S1-R1/R2): every object has
    string keys and every number is finite, objects inside arrays included. The messages are
    fixed and echo no key or value; ``json.dumps`` catches everything else."""
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("detail nested objects must have string keys")
        for item in value.values():
            _check_detail(item)
    elif isinstance(value, list | tuple):
        for item in value:
            _check_detail(item)
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("detail must not contain non-finite numbers")


def validate_execution(
    *,
    control_id: str,
    run_ref_type: RunRefType,
    run_ref_id: UUID,
    population_count: int,
    exception_count: int,
    result: ControlResult,
    detail: Mapping[str, Any] | None = None,
    exceptions_file_id: UUID | None = None,
    entity_id: UUID | None = None,
    book_code: str | None = None,
    period_id: UUID | None = None,
    known_controls: Mapping[str, object] | None = None,
) -> ExecutionRecord:
    """The helper-side rules of ``record_execution`` (agreed with lane F-CLO): ``control_id``
    matches ``^CTL-[0-9]{3}$`` and exists in ``controls.yaml``; ``PASS`` requires
    ``exception_count == 0``, ``FAIL`` requires ``>= 1``, ``NOT_APPLICABLE`` requires
    ``population_count == 0``; counts are non-negative ints; ``detail`` is a mapping that is
    strict JSON at every depth — string object keys and finite numbers, objects inside arrays
    included (Codex P4-S1-R1/R2) — stored as given (no key normalisation). Any violation is a
    ``ValueError``: a producer bug, not a Problem."""
    if not isinstance(control_id, str) or CONTROL_ID.fullmatch(control_id) is None:
        raise ValueError("control_id must match ^CTL-[0-9]{3}$")
    registry = controls() if known_controls is None else known_controls
    if control_id not in registry:
        raise ValueError(f"control_id {control_id} is not in controls.yaml")
    if not isinstance(run_ref_type, RunRefType):
        raise ValueError("run_ref_type must be a RunRefType")
    if not isinstance(run_ref_id, UUID):
        raise ValueError("run_ref_id must be a UUID")
    population = _count("population_count", population_count)
    exceptions = _count("exception_count", exception_count)
    if not isinstance(result, ControlResult):
        raise ValueError("result must be a ControlResult")
    if result is ControlResult.PASS and exceptions != 0:
        raise ValueError("PASS requires exception_count == 0")
    if result is ControlResult.FAIL and exceptions < 1:
        raise ValueError("FAIL requires exception_count >= 1")
    if result is ControlResult.NOT_APPLICABLE and population != 0:
        raise ValueError("NOT_APPLICABLE requires population_count == 0")
    given: Mapping[str, Any] = {} if detail is None else detail
    if not isinstance(given, Mapping) or not all(isinstance(key, str) for key in given):
        raise ValueError("detail must be a mapping with string keys")
    for item in given.values():
        _check_detail(item)
    try:
        json.dumps(given, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("detail must be JSON-serialisable") from exc
    book: BookCode | None = None
    if book_code is not None:
        try:
            book = BookCode(book_code)
        except ValueError:
            raise ValueError("book_code must be a BookCode value or None") from None
    return ExecutionRecord(
        control_id=control_id,
        run_ref_type=run_ref_type,
        run_ref_id=run_ref_id,
        population_count=population,
        exception_count=exceptions,
        result=result,
        detail=dict(given),
        exceptions_file_id=_optional_uuid("exceptions_file_id", exceptions_file_id),
        entity_id=_optional_uuid("entity_id", entity_id),
        book_code=book,
        period_id=_optional_uuid("period_id", period_id),
    )


def _release_id(session: Session) -> UUID:
    """The ``engine_release_id`` of the row: the release this process stamped at its entrypoint
    (``controls.stamping.process_release_id``, REL-03 / CTL-032; D-98 60), failing closed with
    ``release-mismatch`` outside the dev / test fallback — the same rule as the four other
    consumers (contract computations, journal batches, report runs)."""

    def latest_for_version() -> UUID | None:
        found = session.execute(
            select(engine_release.c.id)
            .where(engine_release.c.engine_version == ENGINE_VERSION)
            .order_by(engine_release.c.deployed_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return None if found is None else UUID(str(found))

    return process_release_id(
        current_release(),
        env=current_environment(),
        engine_version=ENGINE_VERSION,
        latest_for_version=latest_for_version,
    )


def record_execution(
    uow: UnitOfWork,
    *,
    control_id: str,
    run_ref_type: RunRefType,
    run_ref_id: UUID,
    population_count: int,
    exception_count: int,
    result: ControlResult,
    detail: Mapping[str, Any] | None = None,
    exceptions_file_id: UUID | None = None,
    entity_id: UUID | None = None,
    book_code: str | None = None,
    period_id: UUID | None = None,
) -> UUID:
    """Insert one T-PLT-39 row in the unit of work's transaction and return its id (SOP-1; the
    shape agreed with lane F-CLO). ``engine_release_id`` is the process release
    (``process_release_id``; D-98 60) and ``executed_at`` is ``uow.now``; the caller commits.
    The row is AUD-FACT evidence: the producer's command carries the audit event, the helper
    writes none."""
    record = validate_execution(
        control_id=control_id,
        run_ref_type=run_ref_type,
        run_ref_id=run_ref_id,
        population_count=population_count,
        exception_count=exception_count,
        result=result,
        detail=detail,
        exceptions_file_id=exceptions_file_id,
        entity_id=entity_id,
        book_code=book_code,
        period_id=period_id,
    )
    row_id = new_id()
    uow.session.execute(
        insert(control_execution).values(
            tenant_id=uow.principal.tenant_id,
            id=row_id,
            control_id=record.control_id,
            run_ref_type=record.run_ref_type.value,
            run_ref_id=record.run_ref_id,
            entity_id=record.entity_id,
            book_code=None if record.book_code is None else record.book_code.value,
            period_id=record.period_id,
            population_count=record.population_count,
            exception_count=record.exception_count,
            result=record.result.value,
            detail=dict(record.detail),
            exceptions_file_id=record.exceptions_file_id,
            engine_release_id=_release_id(uow.session),
            executed_at=uow.now,
        )
    )
    return row_id


class ControlRefusal(Problem):
    """A refused command with failure observations to retain after its transaction rolls back.

    The payload is control evidence only, never deferred business writes. The outer unit-of-work
    boundary records it with the same caller/tenant after releasing the refused transaction.
    """

    def __init__(self, problem: Problem, records: tuple[ExecutionRecord, ...]) -> None:
        if not records or any(record.result is not ControlResult.FAIL for record in records):
            raise ValueError("a control refusal requires failed control observations")
        super().__init__(
            problem.slug,
            problem.detail,
            errors=problem.errors,
            code=problem.code,
            headers=problem.headers,
            **problem.extensions,
        )
        self.records = records
        self.retained = False

    def retain(self, uow: UnitOfWork) -> None:
        for record in self.records:
            evidence_id = record_execution(
                uow,
                control_id=record.control_id,
                run_ref_type=record.run_ref_type,
                run_ref_id=record.run_ref_id,
                population_count=record.population_count,
                exception_count=record.exception_count,
                result=record.result,
                detail=record.detail,
                exceptions_file_id=record.exceptions_file_id,
                entity_id=record.entity_id,
                book_code=None if record.book_code is None else record.book_code.value,
                period_id=record.period_id,
            )
            uow.audit(
                action="control_execution.refusal",
                object_type="control_execution",
                object_id=evidence_id,
                after={
                    "control_id": record.control_id,
                    "result": "FAIL",
                    "problem": self.slug,
                    "run_ref_type": record.run_ref_type.value,
                    "run_ref_id": str(record.run_ref_id),
                },
            )
