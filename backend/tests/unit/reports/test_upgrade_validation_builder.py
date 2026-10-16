"""The frozen validation builder refuses incompatible report modes before reading evidence."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from erev_api.domain.reports.builders import (
    RETAINED,
    ReportParams,
    SourceCollector,
    upgrade_validation,
)
from erev_api.problems import Problem


@pytest.mark.parametrize(
    "fault",
    [
        "code",
        "version",
        "format",
        "filter",
        "lock",
        "attempt",
        "binding_version",
        "binding_strategy",
        "missing_evidence",
    ],
)
def test_invalid_report_mode_does_not_read_evidence(
    monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    params = ReportParams(
        "upgrade_validation",
        1,
        {"release_validation_attempt_id": str(UUID(int=1))},
        (),
        datetime(2026, 10, 15, tzinfo=UTC),
        output_format="JSON",
    )
    if fault == "code":
        params = replace(params, report_code="other")
    elif fault == "version":
        params = replace(params, report_version=2)
    elif fault == "format":
        params = replace(params, output_format="PDF")
    elif fault == "filter":
        params = replace(params, filters={"outcome": "MATCH"})
    elif fault == "lock":
        params = replace(params, period_lock_id=UUID(int=2))
    elif fault == "attempt":
        params = replace(params, parameters={"release_validation_attempt_id": "not-a-uuid"})
    else:
        collector = SourceCollector()
        collector.record_cutoff(params.known_at)
        binding = collector.binding(row_keys=[], strategy=RETAINED, report_version=1)
        if fault == "binding_version":
            binding = replace(binding, report_version=2)
        elif fault == "binding_strategy":
            binding = replace(binding, strategy="open")
        params = replace(params, binding=binding)

    def unread(*args: object, **kwargs: object) -> None:
        pytest.fail("Invalid report mode reached its source reader")

    monkeypatch.setattr(upgrade_validation, "read_for_report", unread)
    with pytest.raises(Problem):
        upgrade_validation.build(None, params)  # type: ignore[arg-type]
