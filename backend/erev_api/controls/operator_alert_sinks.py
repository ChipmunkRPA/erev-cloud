"""The operator-alert sinks that need the composition root's ports (05 OPR-24, CFG-31): the email
sink over the NTR-05 ``EmailSender`` port, the fan-out with per-sink failure isolation and the
settings-driven composition. ``controls.operator_alerts`` holds the kinds, the alert, the log and
file sinks and the factories without these imports, so kernel modules can raise alerts freely."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from erev_api.clock import Clock
from erev_api.config import Settings
from erev_api.controls.operator_alerts import (
    _LOGGER,
    AlertSink,
    FileSink,
    LogSink,
    OperatorAlert,
)
from erev_api.events.outbox import EmailMessage, EmailSender
from erev_api.logging import get_logger

LOG_ONLY: Final = "log-only"  # CFG-31 EREV_OPERATOR_ALERT_DELIVERY
SENDER_TENANT_CODE: Final = "platform-operators"  # a path-safe workspace code for the fake sender


class EmailSink:
    """The NTR-05 ``EmailSender`` port to the operator address of CFG-31."""

    def __init__(self, sender: EmailSender, to: str) -> None:
        self._sender = sender
        self._to = to

    def deliver(self, alert: OperatorAlert) -> str:
        lines = [f"{alert.summary}", "", f"Runbook: {alert.runbook}", f"Alert id: {alert.id}"]
        lines += [f"{name}: {value}" for name, value in sorted(alert.fields.items())]
        message = EmailMessage(
            tenant_code=SENDER_TENANT_CODE,
            reference=alert.id,
            to=self._to,
            subject=f"[eRev {alert.severity}] {alert.kind.value} ({alert.runbook})",
            text="\n".join(lines),
        )
        return f"email:{self._sender.send(message)}"


@dataclass(frozen=True, slots=True)
class AlertSinks:
    """The configured sinks; ``raise_alert`` fans out with per-sink failure isolation."""

    sinks: tuple[AlertSink, ...]

    def raise_alert(self, alert: OperatorAlert) -> tuple[str, ...]:
        logger = get_logger(_LOGGER)
        delivered: list[str] = []
        for sink in self.sinks:
            try:
                delivered.append(sink.deliver(alert))
            except Exception as raised:  # noqa: BLE001 — one sink never masks another
                logger.error(
                    "operator_alert.sink_failed",
                    alert_id=str(alert.id),
                    kind=alert.kind.value,
                    sink=type(sink).__name__,
                    error_type=type(raised).__name__,
                )
        logger.info(
            "operator_alert.delivered",
            alert_id=str(alert.id),
            kind=alert.kind.value,
            delivered=len(delivered),
        )
        return tuple(delivered)


def build_alert_sinks(settings: Settings, clock: Clock, *, email: EmailSender | None) -> AlertSinks:
    """The composition root's sinks (CFG-31): log and file trail always; email when configured."""
    sinks: list[AlertSink] = [LogSink(), FileSink(settings.run_dir, clock)]
    if settings.operator_alert_email is not None and email is not None:
        sinks.append(EmailSink(email, settings.operator_alert_email))
    return AlertSinks(tuple(sinks))


def delivery_configured(settings: Settings) -> bool:
    """SAR-40 ``operator-alerts``: an email recipient, or the explicit log-only acknowledgement."""
    return settings.operator_alert_email is not None or settings.operator_alert_delivery == LOG_ONLY
