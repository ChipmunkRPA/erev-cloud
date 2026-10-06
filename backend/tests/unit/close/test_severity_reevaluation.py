"""D-98 58 (Codex CLO-5 review R2): an existing unresolved exception item re-evaluated at a
different
effective severity takes the current severity with an auditable history entry; status never changes.
Pure part: ``imports.exceptions.severity_change`` decides the transition the DB path records."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from erev_api.domain.imports import exceptions
from erev_api.enums import ExceptionSeverity

AT = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)


def test_escalation_and_lowering_are_recorded_status_untouched() -> None:
    up = exceptions.severity_change("WARNING", ExceptionSeverity.BLOCKING, at=AT, cause="DQ-TENANT")
    assert up is not None
    assert (up.previous, up.current, up.evaluated_at, up.cause) == (
        "WARNING",
        "BLOCKING",
        AT,
        "DQ-TENANT",
    )
    down = exceptions.severity_change(
        "BLOCKING", ExceptionSeverity.WARNING, at=AT, cause="DQ-SYSTEM"
    )
    assert down is not None and (down.previous, down.current) == ("BLOCKING", "WARNING")
    assert up.history_entry() == {
        "from": "WARNING",
        "to": "BLOCKING",
        "evaluated_at": AT.isoformat(),
        "cause": "DQ-TENANT",
    }
    assert "status" not in up.history_entry()


def test_same_severity_is_no_change() -> None:
    assert (
        exceptions.severity_change("BLOCKING", ExceptionSeverity.BLOCKING, at=AT, cause="x") is None
    )
    assert (
        exceptions.severity_change(
            ExceptionSeverity.WARNING, ExceptionSeverity.WARNING, at=AT, cause="x"
        )
        is None
    )


def test_severity_changed_action_is_named() -> None:
    assert exceptions.SEVERITY_ACTION == "exception_item.severity_changed"
    with pytest.raises(ValueError):
        exceptions.severity_change("LOUD", ExceptionSeverity.BLOCKING, at=AT, cause="x")
