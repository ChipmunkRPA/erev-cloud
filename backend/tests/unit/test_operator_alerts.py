"""05 OPR-24 operator alerts (rev 1.27; record §4.31): the three sinks, the fan-out isolation, the
values-free rule with one never-echo witness per sink, the composition and the SCH-02 / SCH-13
wiring. No live provider is ever called: the email sink is exercised through the fake sender."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import UUID

import pytest
from erev_api.adapters.email.fake import FakeEmailSender
from erev_api.audit.verify import ChainVerificationResult
from erev_api.clock import FrozenClock
from erev_api.config import Settings
from erev_api.controls import operator_alert_sinks, partition_window
from erev_api.controls.doctor import PARTITION_COLUMNS, PartitionWindowObservation
from erev_api.controls.operator_alert_sinks import AlertSinks, EmailSink, build_alert_sinks
from erev_api.controls.operator_alerts import (
    FileSink,
    LogSink,
    OperatorAlert,
    OperatorAlertKind,
    ValuesNotFree,
    file_shred_incomplete_alert,
    security_chain_alert,
)
from erev_api.domain.platform import audit_jobs
from erev_api.enums import ControlResult
from erev_api.jobs.context import JobRuntime
from support import log_guard
from support.clock import FROZEN_AT

SENTINEL = "sentinel-secret-9f8e7d6c5b4a39281706f5e4d3c2b1a0"  # never allowed to reach a sink
DSN = f"postgresql://erev_app:{SENTINEL}@127.0.0.1:5432/erev"


def _alert(**fields: object) -> OperatorAlert:
    return OperatorAlert(
        kind=OperatorAlertKind.PARTITION_WINDOW_NEAR_END,
        summary="A partition window ends within the horizon or is unbounded (SCH-13)",
        raised_at=FROZEN_AT,
        fields={"tables": "subledger_line,audit_event", "failures": 1, **fields},  # type: ignore[dict-item]
    )


class Recording:
    def __init__(self) -> None:
        self.alerts: list[OperatorAlert] = []

    def raise_alert(self, alert: OperatorAlert) -> tuple[str, ...]:
        self.alerts.append(alert)
        return ("recorded",)


class Exploding:
    def deliver(self, alert: OperatorAlert) -> str:
        raise RuntimeError(f"cannot reach {DSN}")


def test_the_values_free_rule_refuses_secrets_addresses_and_amount_fields() -> None:
    with pytest.raises(ValuesNotFree):
        _alert(dsn="x")
    with pytest.raises(ValuesNotFree):
        _alert(note=DSN)
    with pytest.raises(ValuesNotFree):
        _alert(contact="ops@erev.example")
    with pytest.raises(ValuesNotFree):
        _alert(digest="a" * 40)
    with pytest.raises(ValuesNotFree):
        _alert(total_amount=12)
    with pytest.raises(ValuesNotFree):
        OperatorAlert(OperatorAlertKind.PARTITION_WINDOW_NEAR_END, f"see {DSN}", FROZEN_AT)
    assert _alert(first_failure_seq=42, scope="global").fields["scope"] == "global"


def test_log_sink_emits_the_alert_at_its_severity_and_never_a_value() -> None:
    with log_guard.capture() as events:
        reference = LogSink().deliver(_alert())
    raised = [e for e in events if e.get("event") == "operator_alert.raised"]
    assert len(raised) == 1 and reference.startswith("log:")
    assert (raised[0]["kind"], raised[0]["severity"], raised[0]["runbook"]) == (
        "PARTITION_WINDOW_NEAR_END",
        "WARNING",
        "RB-12",
    )
    assert SENTINEL not in json.dumps(events, default=str)
    assert "://" not in json.dumps(raised, default=str)


def test_file_sink_appends_one_json_line_to_the_non_durable_trail(tmp_path: Path) -> None:
    sink = FileSink(tmp_path, FrozenClock(FROZEN_AT))
    alert = _alert()
    reference = sink.deliver(alert)
    trail = tmp_path / "operator-alerts" / "20260912.jsonl"
    (line,) = trail.read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    assert reference == f"file:20260912.jsonl:{alert.id}"
    assert (record["kind"], record["runbook"], record["fields"]["failures"]) == (
        "PARTITION_WINDOW_NEAR_END",
        "RB-12",
        1,
    )
    assert SENTINEL not in line and "://" not in line


def test_email_sink_goes_through_the_fake_sender_only(tmp_path: Path) -> None:
    clock = FrozenClock(FROZEN_AT)
    sender = FakeEmailSender(tmp_path / "mail", clock)
    alert = security_chain_alert(
        scope="global", from_seq=1, to_seq=900, first_failure_seq=417, raised_at=FROZEN_AT
    )
    reference = EmailSink(sender, "ops@erev.example").deliver(alert)
    assert reference.startswith("email:")
    (message,) = (tmp_path / "mail" / "platform-operators").iterdir()
    body = message.read_bytes().decode("utf-8", errors="replace")
    assert "[eRev SEV-1] SECURITY_CHAIN_VERIFICATION_FAILED (RB-08)" in body
    assert "first_failure_seq: 417" in body and SENTINEL not in body


def test_one_sink_failure_never_masks_the_others_and_never_echoes_its_message(
    tmp_path: Path,
) -> None:
    sinks = AlertSinks((Exploding(), LogSink(), FileSink(tmp_path, FrozenClock(FROZEN_AT))))
    with log_guard.capture() as events:
        delivered = sinks.raise_alert(_alert())
    assert len(delivered) == 2
    failed = [e for e in events if e.get("event") == "operator_alert.sink_failed"]
    assert [(e["sink"], e["error_type"]) for e in failed] == [("Exploding", "RuntimeError")]
    assert SENTINEL not in json.dumps(events, default=str)


def test_build_alert_sinks_adds_email_only_when_configured(
    tmp_path: Path, app_settings: Settings
) -> None:
    clock = FrozenClock(FROZEN_AT)
    sender = FakeEmailSender(tmp_path / "mail", clock)
    plain = app_settings.model_copy(
        update={"operator_alert_email": None, "operator_alert_delivery": None}
    )
    assert [type(s).__name__ for s in build_alert_sinks(plain, clock, email=sender).sinks] == [
        "LogSink",
        "FileSink",
    ]
    assert not operator_alert_sinks.delivery_configured(plain)
    configured = plain.model_copy(update={"operator_alert_email": "ops@erev.example"})
    assert [type(s).__name__ for s in build_alert_sinks(configured, clock, email=sender).sinks] == [
        "LogSink",
        "FileSink",
        "EmailSink",
    ]
    assert operator_alert_sinks.delivery_configured(configured)
    # No sender port (a runtime without email) never yields an email sink, even when configured.
    assert [type(s).__name__ for s in build_alert_sinks(configured, clock, email=None).sinks] == [
        "LogSink",
        "FileSink",
    ]
    acknowledged = plain.model_copy(update={"operator_alert_delivery": "log-only"})
    assert operator_alert_sinks.delivery_configured(acknowledged)


def _runtime(recording: Recording | None) -> JobRuntime:
    return JobRuntime(clock=FrozenClock(FROZEN_AT), keyring=None, files=None, alerts=recording)


def test_sch_13_raises_the_partition_window_alert_only_on_a_failed_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def windows(ends_on: date) -> tuple[PartitionWindowObservation, ...]:
        return tuple(PartitionWindowObservation(t, ends_on) for t in sorted(PARTITION_COLUMNS))

    near, far = windows(date(2027, 6, 1)), windows(date(2031, 1, 1))
    recording = Recording()
    monkeypatch.setattr(partition_window, "_observe_catalogue", lambda: near)
    checked = partition_window.run(_runtime(recording))
    assert not checked.result.ok and checked.tables == tuple(sorted(PARTITION_COLUMNS))
    (alert,) = recording.alerts
    assert (alert.kind, alert.runbook, alert.fields["tables"]) == (
        OperatorAlertKind.PARTITION_WINDOW_NEAR_END,
        "RB-12",
        ",".join(sorted(PARTITION_COLUMNS)),
    )
    monkeypatch.setattr(partition_window, "_observe_catalogue", lambda: far)
    assert partition_window.run(_runtime(recording)).result.ok and len(recording.alerts) == 1
    # No sinks on the runtime: the check still runs and logs; nothing is raised or swallowed.
    monkeypatch.setattr(partition_window, "_observe_catalogue", lambda: near)
    assert not partition_window.run(_runtime(None)).result.ok


def _chain_result(outcome: ControlResult) -> ChainVerificationResult:
    return ChainVerificationResult(
        scope="global",
        from_chain_seq=1,
        to_chain_seq=900,
        events_checked=900,
        result=outcome,
        first_failure_seq=417 if outcome is ControlResult.FAIL else None,
        failure_detail={"reason": "hmac mismatch"} if outcome is ControlResult.FAIL else None,
        digest_last_hmac=None,
    )


def test_sch_02_raises_the_security_chain_alert_on_fail_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recording = Recording()
    runtime = JobRuntime(
        clock=FrozenClock(FROZEN_AT),
        keyring=object(),
        files=None,
        alerts=recording,  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        audit_jobs,
        "verify_security_chain",
        lambda keyring, *, request_id: _chain_result(ControlResult.FAIL),
    )
    result = audit_jobs.security_chain_verify(runtime)
    assert result.result is ControlResult.FAIL
    (alert,) = recording.alerts
    assert (alert.kind, alert.severity, alert.fields["first_failure_seq"]) == (
        OperatorAlertKind.SECURITY_CHAIN_VERIFICATION_FAILED,
        "SEV-1",
        417,
    )
    monkeypatch.setattr(
        audit_jobs,
        "verify_security_chain",
        lambda keyring, *, request_id: _chain_result(ControlResult.PASS),
    )
    assert audit_jobs.security_chain_verify(runtime).result is ControlResult.PASS
    assert len(recording.alerts) == 1
    assert isinstance(recording.alerts[0].id, UUID)
    assert recording.alerts[0].raised_at == datetime(2026, 9, 12, 12, 0, tzinfo=UTC)


def test_opr_24_the_alert_of_a_shred_that_is_not_completed_names_no_file() -> None:
    """05 OPR-24 rev 1.171 (item FILE-SHRED-DURABLE-ORDER-1): the fifth kind, raised by the sweep
    SCH-16 for a workspace that still holds a decided shred 60 minutes after its decision. A
    warning under RB-14 whose fields are the workspace, how many files and how old the oldest
    decision is. It names no file: a storage key holds the SHA-256 of the content, and the
    values-free rule refuses such a field before any sink writes."""
    tenant_id = UUID(int=0xA1)
    alert = file_shred_incomplete_alert(
        tenant_id=tenant_id, files=3, oldest_minutes=75, raised_at=FROZEN_AT
    )
    assert (alert.kind, alert.severity, alert.runbook) == (
        OperatorAlertKind.FILE_SHRED_INCOMPLETE,
        "WARNING",
        "RB-14",
    )
    assert dict(alert.fields) == {"tenant_id": str(tenant_id), "files": 3, "oldest_minutes": 75}
    assert alert.as_record()["kind"] == "FILE_SHRED_INCOMPLETE"
    storage_key = f"{tenant_id}/ATTACHMENT/{'ab' * 32}"
    with pytest.raises(ValuesNotFree):
        OperatorAlert(alert.kind, alert.summary, FROZEN_AT, fields={"storage_key": storage_key})
