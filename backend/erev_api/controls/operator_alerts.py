"""Operator alerts (05 OPR-24, rev 1.27; RB-07, RB-08, RB-12, RB-14; CFG-31; SAR-40
``operator-alerts``).

Five alert kinds reach the platform operators through every configured sink: the log (always),
a NON-DURABLE local JSON-lines trail under ``<EREV_RUN_DIR>/operator-alerts/`` (never audit
evidence — the audit and security chains are) and, when ``EREV_OPERATOR_ALERT_EMAIL`` is set, the
NTR-05 ``EmailSender`` port (the fake sender under dev / test / e2e, so no test ever sends live).
No chat or pager adapter exists in source (UI-9 is the hosted operator's). Alert summaries and
fields are VALUES-FREE — identifiers, scopes, sequence ranges, table names and codes only; a field
that looks like a DSN, URL, address, secret or key material is refused before any sink writes. One
sink's failure never masks another: it is logged as ``operator_alert.sink_failed`` with the sink
and the exception type only.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, Literal, Protocol
from uuid import UUID, uuid4

from erev_api.clock import Clock
from erev_api.logging import get_logger, register_logger_fields

Severity = Literal["SEV-1", "WARNING"]
FieldValue = str | int | None

TRAIL_DIRECTORY: Final = "operator-alerts"
_LOGGER: Final = "erev_api.controls.operator_alerts"
register_logger_fields(
    _LOGGER,
    (
        "alert_id",
        "kind",
        "severity",
        "runbook",
        "summary",
        "alert_fields",
        "sink",
        "error_type",
        "delivered",
    ),
)
# Values-free rule (05 OPR-24): field names that would carry a value, and value shapes that are
# never an identifier — a URL or DSN, an address, key material.
_FORBIDDEN_NAME_PARTS: Final = (
    "password",
    "secret",
    "token",
    "dsn",
    "url",
    "credential",
    "amount",
    "total",
    "balance",
    "email",
    "phone",
    "address",
    "payee",
    "salary",
)
_FORBIDDEN_VALUE: Final = re.compile(r"://|@|[0-9a-fA-F]{32,}")
_MAX_VALUE_LENGTH: Final = 200


class OperatorAlertKind(StrEnum):
    SECURITY_CHAIN_VERIFICATION_FAILED = "SECURITY_CHAIN_VERIFICATION_FAILED"  # SCH-02; RB-08
    AUDIT_CHAIN_VERIFICATION_FAILED = "AUDIT_CHAIN_VERIFICATION_FAILED"  # SCH-01 job; RB-08
    PARTITION_WINDOW_NEAR_END = "PARTITION_WINDOW_NEAR_END"  # SCH-13; RB-12
    JOB_FAILED = "JOB_FAILED"  # 05 JOB-07 rev 1.165: a job that no user started; RB-07
    # 05 PRV-07 b rev 1.171, SCH-16: a decided shred not completed after 60 minutes; RB-14
    FILE_SHRED_INCOMPLETE = "FILE_SHRED_INCOMPLETE"


SEVERITY: Final[Mapping[OperatorAlertKind, Severity]] = {
    OperatorAlertKind.SECURITY_CHAIN_VERIFICATION_FAILED: "SEV-1",
    OperatorAlertKind.AUDIT_CHAIN_VERIFICATION_FAILED: "SEV-1",
    OperatorAlertKind.PARTITION_WINDOW_NEAR_END: "WARNING",
    OperatorAlertKind.JOB_FAILED: "WARNING",
    OperatorAlertKind.FILE_SHRED_INCOMPLETE: "WARNING",
}
RUNBOOK: Final[Mapping[OperatorAlertKind, str]] = {
    OperatorAlertKind.SECURITY_CHAIN_VERIFICATION_FAILED: "RB-08",
    OperatorAlertKind.AUDIT_CHAIN_VERIFICATION_FAILED: "RB-08",
    OperatorAlertKind.PARTITION_WINDOW_NEAR_END: "RB-12",
    OperatorAlertKind.JOB_FAILED: "RB-07",
    OperatorAlertKind.FILE_SHRED_INCOMPLETE: "RB-14",
}


class ValuesNotFree(ValueError):
    """A field name or value that could carry a secret, an address or a financial value."""


def assert_values_free(summary: str, fields: Mapping[str, FieldValue]) -> None:
    """05 OPR-24: identifiers, scopes, sequence ranges, table names and codes only."""
    if _FORBIDDEN_VALUE.search(summary) or len(summary) > _MAX_VALUE_LENGTH:
        raise ValuesNotFree("the alert summary is not values-free")
    for name, value in fields.items():
        lowered = name.lower()
        if any(part in lowered for part in _FORBIDDEN_NAME_PARTS):
            raise ValuesNotFree(f"alert field {name!r} would carry a value")
        if value is None or isinstance(value, int):
            continue
        if not isinstance(value, str):
            raise ValuesNotFree(f"alert field {name!r} is not a string, an integer or None")
        if len(value) > _MAX_VALUE_LENGTH or _FORBIDDEN_VALUE.search(value):
            raise ValuesNotFree(f"alert field {name!r} is not values-free")


@dataclass(frozen=True, slots=True)
class OperatorAlert:
    kind: OperatorAlertKind
    summary: str
    raised_at: datetime
    fields: Mapping[str, FieldValue] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        assert_values_free(self.summary, self.fields)

    @property
    def severity(self) -> Severity:
        return SEVERITY[self.kind]

    @property
    def runbook(self) -> str:
        return RUNBOOK[self.kind]

    def as_record(self) -> dict[str, object]:
        return {
            "alert_id": str(self.id),
            "kind": self.kind.value,
            "severity": self.severity,
            "runbook": self.runbook,
            "summary": self.summary,
            "raised_at": self.raised_at.astimezone(UTC).isoformat(),
            "fields": dict(self.fields),
        }


class AlertSink(Protocol):
    def deliver(self, alert: OperatorAlert) -> str:
        """Deliver ``alert`` and return a delivery reference; a failure raises."""
        ...


class LogSink:
    """``operator_alert.raised`` at ERROR for SEV-1 and WARNING otherwise (the destination every
    deployment has)."""

    def deliver(self, alert: OperatorAlert) -> str:
        logger = get_logger(_LOGGER)
        emit = logger.error if alert.severity == "SEV-1" else logger.warning
        emit(
            "operator_alert.raised",
            alert_id=str(alert.id),
            kind=alert.kind.value,
            severity=alert.severity,
            runbook=alert.runbook,
            summary=alert.summary,
            alert_fields=dict(alert.fields),
        )
        return f"log:{alert.id}"


class FileSink:
    """One JSON line per alert under ``<root>/operator-alerts/<YYYYMMDD>.jsonl`` — a NON-DURABLE
    local trail (container disk in a hosted environment), never audit evidence."""

    def __init__(self, root: Path, clock: Clock) -> None:
        self._root = root / TRAIL_DIRECTORY
        self._clock = clock

    def deliver(self, alert: OperatorAlert) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._root / f"{self._clock.now().astimezone(UTC):%Y%m%d}.jsonl"
        with path.open("a", encoding="utf-8") as trail:
            trail.write(json.dumps(alert.as_record(), sort_keys=True) + "\n")
        return f"file:{path.name}:{alert.id}"


class AlertRaiser(Protocol):
    """What a job runtime carries: fan out one alert (``operator_alert_sinks.AlertSinks``)."""

    def raise_alert(self, alert: OperatorAlert) -> tuple[str, ...]: ...


# --- the alerts the SCH periodics raise ----------------------------------------------------------


def security_chain_alert(
    *, scope: str, from_seq: int, to_seq: int, first_failure_seq: int | None, raised_at: datetime
) -> OperatorAlert:
    return OperatorAlert(
        kind=OperatorAlertKind.SECURITY_CHAIN_VERIFICATION_FAILED,
        summary="The global security event chain failed verification (SCH-02)",
        raised_at=raised_at,
        fields={
            "scope": scope,
            "from_chain_seq": from_seq,
            "to_chain_seq": to_seq,
            "first_failure_seq": first_failure_seq,
        },
    )


def audit_chain_alert(
    *,
    tenant_id: UUID,
    verification_id: UUID,
    events_checked: int,
    first_failure_seq: int | None,
    raised_at: datetime,
) -> OperatorAlert:
    return OperatorAlert(
        kind=OperatorAlertKind.AUDIT_CHAIN_VERIFICATION_FAILED,
        summary="A tenant audit chain failed verification (SCH-01)",
        raised_at=raised_at,
        fields={
            "tenant_id": str(tenant_id),
            "verification_id": str(verification_id),
            "events_checked": events_checked,
            "first_failure_seq": first_failure_seq,
        },
    )


def partition_window_alert(
    *, summary: str, tables: Iterable[str], failures: int, horizon_months: int, raised_at: datetime
) -> OperatorAlert:
    return OperatorAlert(
        kind=OperatorAlertKind.PARTITION_WINDOW_NEAR_END,
        summary="A partition window ends within the horizon or is unbounded (SCH-13)",
        raised_at=raised_at,
        fields={
            "check_summary": summary,
            "tables": ",".join(sorted(tables)),
            "failures": failures,
            "horizon_months": horizon_months,
        },
    )


# --- the alert the jobs registry raises ----------------------------------------------------------


def job_failed_alert(
    *,
    tenant_id: UUID,
    job_id: UUID,
    job_kind: str,
    queue: str,
    attempt: int,
    problem: str | None,
    initiator: str,
    raised_at: datetime,
) -> OperatorAlert:
    """05 JOB-07 rev 1.165 (item JOB-FAILED-ITEM-1): a job that no user started — a periodic job
    of the scheduler, a job of an API client — ended FAILED after its last attempt. A user's job
    notifies its initiator instead (PRD NTF-05). ``problem`` is the slug of the job's problem and
    ``initiator`` the kind of the principal that started it; neither carries a value."""
    return OperatorAlert(
        kind=OperatorAlertKind.JOB_FAILED,
        summary="A job that no user started ended FAILED after its last attempt (JOB-07)",
        raised_at=raised_at,
        fields={
            "tenant_id": str(tenant_id),
            "job_id": str(job_id),
            "job_kind": job_kind,
            "queue": queue,
            "attempt": attempt,
            "problem": problem,
            "initiator": initiator,
        },
    )


# --- the alert the shred completion sweep raises --------------------------------------------------


def file_shred_incomplete_alert(
    *, tenant_id: UUID, files: int, oldest_minutes: int, raised_at: datetime
) -> OperatorAlert:
    """05 PRV-07 b and OPR-24 rev 1.171 (item FILE-SHRED-DURABLE-ORDER-1): a workspace holds
    files whose shred was decided and whose key the sweep SCH-16 could not destroy within 60
    minutes — the store, its credentials or a lock. A warning: every reader of the workspace
    refuses such a file by its row already; what is late is the destruction of its key. It names
    the workspace, how many files and the age of the oldest decision — no file, no storage key
    (a key holds the content's SHA-256, which the values-free rule refuses)."""
    return OperatorAlert(
        kind=OperatorAlertKind.FILE_SHRED_INCOMPLETE,
        summary="A decided shred is not completed 60 minutes after its decision (SCH-16)",
        raised_at=raised_at,
        fields={
            "tenant_id": str(tenant_id),
            "files": files,
            "oldest_minutes": oldest_minutes,
        },
    )
