"""Shared API schemas (04 §16.0: API-S-Money, Ref, Actor, List, Problem, Job, Context).

Class names drop the ``API-S-`` prefix and append ``Out`` (DG-API-03). API-S-Money is
``erev_api.money.MoneyOut``, re-exported here.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date, datetime
from types import MappingProxyType
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field

from erev_api.enums import BookCode, JobKind, JobState, PrincipalKind
from erev_api.money import MoneyOut

__all__ = [
    "ActorOut",
    "ContextOut",
    "JobOut",
    "JobProgressOut",
    "JobResultOut",
    "ListOut",
    "MeasuredPeriodOut",
    "MoneyOut",
    "ProblemErrorOut",
    "ProblemOut",
    "RefOut",
    "job_out",
]


class RefOut(BaseModel):
    """API-S-Ref: EntityRef, CustomerRef, ProductRef, AccountRef."""

    id: uuid.UUID
    code: str
    name: str


class ActorOut(BaseModel):
    """API-S-Actor."""

    id: uuid.UUID | None
    kind: PrincipalKind
    display_name: str


class ListOut[ItemT](BaseModel):
    """API-S-List (API-C-09)."""

    items: list[ItemT]
    next_cursor: str | None


class ProblemErrorOut(BaseModel):
    field: str | None = None
    sheet: str | None = None
    row: int | None = None
    rule_id: str | None = None
    message: str = ""


class ProblemOut(BaseModel):
    """API-S-Problem (API-C-05); ``detail`` is absent on about:blank responses."""

    type: str
    title: str
    status: int
    detail: str | None = None
    instance: str
    code: str | None = None
    errors: list[ProblemErrorOut] = Field(default_factory=list)


class JobProgressOut(BaseModel):
    done: int
    total: int | None


class JobResultOut(BaseModel):
    """``{href, counts}``; ``href`` is null for a job that produces no resource (SPEC-Q-187). Other
    members a job stores pass through, such as ``summary`` (API-S-ImpactSummary) of an event preview
    (04 §16.3; BUILD_SPEC CTR-5)."""

    model_config = ConfigDict(extra="allow")

    href: str | None = None
    counts: dict[str, Any] = Field(default_factory=dict)


class JobOut(BaseModel):
    """API-S-Job (API-C-12)."""

    id: uuid.UUID
    kind: JobKind
    state: JobState
    progress: JobProgressOut
    result: JobResultOut | None
    problem: ProblemOut | None
    created_by: ActorOut
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    # 04 rev 1.67 (D-98 candidate 137 (1)): derived from the params of a TENANT_SNAPSHOT job —
    # "export" or "restore" — never a stored column. Rev 1.281 (item JRN-JOB-MODE-1): and from
    # the params of a JOURNAL_EXPORT job (``JOURNAL_EXPORT_MODES``). Null for every other kind,
    # and for a JOURNAL_EXPORT job deferred before rev 1.281 without a mode.
    mode: str | None = None


JOB_MODE_EXPORT: Final = "export"
JOB_MODE_RESTORE: Final = "restore"
# 04 API-S-Job rev 1.281 (item JRN-JOB-MODE-1): what a ``JOURNAL_EXPORT`` job answers as its mode,
# by the word its ``params.mode`` stores — the run's export, a batch's retry, and the two ways out
# of ``failed`` (T-SL-07). The member answers a kind's words as that kind states them: these four
# in upper case, as an enumerated literal of this product is (``kind``, ``state``,
# ``result.outcome`` beside it); the snapshot's two above are lower case since rev 1.67. The
# spelling of the answer is this mapping and nothing else; the job's ``result.mode`` reads it too
# (``journals.export``).
JOURNAL_EXPORT_MODE_PARAM: Final = "mode"
JOURNAL_EXPORT_MODES: Final[Mapping[str, str]] = MappingProxyType(
    {"EXPORT": "EXPORT", "RETRY": "RETRY", "CANCEL": "CANCEL", "HAND_OVER": "HAND_OVER"}
)


def job_mode(kind: object, params: Mapping[str, Any] | None) -> str | None:
    """API-S-Job ``mode`` (04 rev 1.67): ``restore`` when a ``TENANT_SNAPSHOT`` job carries
    ``params.load`` (``POST /tenant/sandboxes``), ``export`` for every other ``TENANT_SNAPSHOT``
    job. Rev 1.281 (item JRN-JOB-MODE-1): the mode of a ``JOURNAL_EXPORT`` job by its
    ``params.mode`` (``JOURNAL_EXPORT_MODES``) — ``None`` for a job that stores none, which is
    every export and retry deferred before rev 1.281: it may have been either, and the member
    does not guess. ``None`` for other kinds."""
    name = str(getattr(kind, "value", kind))
    if name == JobKind.JOURNAL_EXPORT.value:
        stored = None if params is None else params.get(JOURNAL_EXPORT_MODE_PARAM)
        return None if stored is None else JOURNAL_EXPORT_MODES.get(str(stored))
    if name != JobKind.TENANT_SNAPSHOT.value:
        return None
    return JOB_MODE_RESTORE if params is not None and "load" in params else JOB_MODE_EXPORT


def job_out(row: Mapping[str, Any], *, created_by: Mapping[str, Any]) -> JobOut:
    """API-S-Job of a ``job`` row (T-PLT-27); ``created_by`` is its API-S-Actor."""
    return JobOut(
        id=row["id"],
        kind=row["kind"],
        state=row["state"],
        progress=JobProgressOut(done=row["progress_done"], total=row["progress_total"]),
        result=None if row["result"] is None else JobResultOut.model_validate(row["result"]),
        problem=None if row["problem"] is None else ProblemOut.model_validate(row["problem"]),
        created_by=ActorOut.model_validate(created_by),
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        mode=job_mode(row["kind"], row.get("params")),
    )


class MeasuredPeriodOut(BaseModel):
    """API-S-Context ``measured_period``: the period the to-date measures were read at."""

    period_key: str
    end_date: date


class ContextOut(BaseModel):
    """API-S-Context: present on computed reads. ``computed_at`` is the time of the computation
    that produced the version; ``measured_period`` the period at which the to-date measures of the
    response were read (04 API-C-10 rev 1.132), null on a read that answers the version as
    stored."""

    book: BookCode
    as_of: date
    known_at: datetime
    contract_version_id: uuid.UUID
    version_no: int
    computed_at: datetime | None = None
    measured_period: MeasuredPeriodOut | None = None
