"""Which job kinds leave the exception item ``JOB_FAILED``, the two readers that read the job's
params, and the operator alert of a job that no user started (05 JOB-07 rev 1.165, OPR-24; 04
§15.4 ``JOB_FAILED`` rev 1.226; dev-guide DG-KRN-JOB-05 rev 1.212; item JOB-FAILED-ITEM-1).

No database: the readers that read a row are witnessed on real rows in
``tests/pg/test_job_failed_readers.py``, the settlement in
``tests/domain/platform/test_job_failed_items.py``.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

import erev_api.worker  # noqa: F401 - registers every handler of the worker (HANDLER_MODULES)
import pytest
from erev_api.clock import FrozenClock
from erev_api.controls.operator_alerts import (
    RUNBOOK,
    SEVERITY,
    FileSink,
    LogSink,
    OperatorAlertKind,
    ValuesNotFree,
    job_failed_alert,
)
from erev_api.domain.close import reconciliations
from erev_api.domain.imports import job_items
from erev_api.domain.imports.exceptions import DISMISSABLE_CODES, JOB_FAILED
from erev_api.domain.journals import summarise
from erev_api.enums import ExceptionSource, JobKind
from erev_api.jobs import registry
from erev_api.jobs.registry import FailedSubject
from sqlalchemy.orm import Session
from support.guides import ROOT

ENTITY = UUID("01900000-0000-7000-8000-00000000e001")
PERIOD = UUID("01900000-0000-7000-8000-00000000b009")
RUN = UUID("01900000-0000-7000-8000-00000000a001")
# The readers under test read their params alone.
NO_SESSION = cast(Session, None)

# 04 §15.4 ``JOB_FAILED`` "Raised as": the kinds whose record can name one legal entity, and the
# E-42 source of their item. A kind is added here when its handler registers a reader.
WITH_AN_ITEM = {
    JobKind.CONTRACT_COMPUTE: ExceptionSource.ENGINE,
    JobKind.POLICY_SIMULATION: ExceptionSource.ENGINE,
    JobKind.JOURNAL_RUN_CALCULATE: ExceptionSource.JOURNAL,
    JobKind.RECONCILIATION_GENERATE: ExceptionSource.RECONCILIATION,
    JobKind.SYNC_RUN: ExceptionSource.SYNC,
    JobKind.PERIOD_OPEN_REDIRTY: ExceptionSource.CLOSE,
}
# Kinds that raise an item of their own when they fail, in their failure hook or dead hook. The
# three import kinds end their upload with ``IMPORT_PROCESSING_FAILED`` (05 §5.6 rev 1.185; 04
# §15.4 rev 1.270; the supervisor's ruling of 2026-10-02): ``IMPORT_VALIDATE`` and ``IMPORT_DIFF``
# registered a reader until their hooks gave them that item.
WITH_THEIR_OWN_ITEM = {
    JobKind.CLOSE_RUN,
    JobKind.JOURNAL_EXPORT,
    JobKind.IMPORT_COMMIT,
    JobKind.IMPORT_VALIDATE,
    JobKind.IMPORT_DIFF,
}


def test_job_failed_item_1_the_documents_state_the_code_its_sources_and_its_copy() -> None:
    """04 §15.4 names the kinds and the sources the handlers register, at severity ``INFO``; PRD
    IMP-137 states the title and the message the queue writes, placeholder for placeholder."""
    model = (ROOT / "docs" / "04-DATA_MODEL.md").read_text(encoding="utf-8")
    (row,) = [line for line in model.splitlines() if line.startswith(f"| `{JOB_FAILED}` |")]
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert cells[1] == "INFO"
    assert set(re.findall(r"X `([A-Z_]+)`", cells[2])) == {
        source.value for source in WITH_AN_ITEM.values()
    }
    for kind in (*WITH_AN_ITEM, *WITH_THEIR_OWN_ITEM):
        assert f"`{kind.value}`" in cells[4], kind
    prd = (ROOT / "docs" / "02-PRD.md").read_text(encoding="utf-8")
    (copy,) = [line for line in prd.splitlines() if line.startswith("| IMP-137 |")]
    assert f"| `{JOB_FAILED}` | INFO |" in copy
    assert f'Title "{registry.JOB_FAILED_TITLE.format(label="<job label>")}"' in copy
    message = job_items.MESSAGE.format(
        label="<job label>", attempt="<n>", reason="<reason>", job_id="<job id>"
    )
    assert f'"{message}"' in copy


def test_job_failed_item_1_the_kinds_that_leave_an_item_are_a_closed_list() -> None:
    """Every registered handler either names its item's source with a reader, or leaves none: a
    kind with an item of its own, a transport kind, or a kind whose record names no legal entity
    (05 JOB-07: the notification or the operator alert stands for those)."""
    found = {
        kind: spec.failed_item.source
        for kind, spec in registry.HANDLERS.items()
        if spec.failed_item is not None
    }
    assert found == WITH_AN_ITEM
    assert not WITH_THEIR_OWN_ITEM & set(found) and not registry.TRANSPORT_KINDS & set(found)
    for kind in WITH_THEIR_OWN_ITEM - {JobKind.JOURNAL_EXPORT}:
        assert registry.HANDLERS[kind].on_failure is not None, kind  # the hook raises its item
    # The two kinds whose record a dead worker left as it was end it in their hook (05 §5.6).
    for kind in (JobKind.IMPORT_COMMIT, JobKind.SSP_CALCULATOR):
        assert registry.HANDLERS[kind].on_failure is not None, kind
    # The queue's functions come with the registration, bound to the kind's source.
    for kind, spec in registry.HANDLERS.items():
        item = spec.failed_item
        if item is not None:
            assert cast(Any, item.raise_item).func is job_items.raise_item, kind
            assert cast(Any, item.raise_item).args == (item.source,), kind


def test_job_failed_item_1_the_item_is_dismissable_by_its_code() -> None:
    """04 §16.14 rev 1.226: ``DISMISS`` is available for a ``JOB_FAILED`` item whatever its
    source, as for a combination suggestion."""
    assert JOB_FAILED == "JOB_FAILED"
    assert frozenset({"COMBINATION_SUGGESTED", "JOB_FAILED"}) == DISMISSABLE_CODES
    key = job_items.item_key(ExceptionSource.JOURNAL, JobKind.JOURNAL_RUN_CALCULATE, "a:b:c")
    assert key == "JOURNAL:JOB_FAILED:JOURNAL_RUN_CALCULATE:a:b:c"


def test_job_failed_item_1_a_calculation_and_a_generation_are_read_from_their_params() -> None:
    """The run of a calculation and the reconciliation of a generation on demand are created by
    the job under an id its command chose, so a failed job leaves no row: the readers answer from
    the job's params, and the record is the entity, the book and the period (with the kind of
    reconciliation) — what a later job works on again, under another id."""
    params = {"entity_id": str(ENTITY), "period_id": str(PERIOD), "book_code": "ASC606"}
    assert summarise.failed_calculation(NO_SESSION, "journal_run", RUN, params) == FailedSubject(
        entity_id=ENTITY, period_id=PERIOD, key=f"{ENTITY}:ASC606:{PERIOD}"
    )
    assert summarise.failed_calculation(NO_SESSION, "journal_run", RUN, {}) is None
    generation = {**params, "kind": "BILLING_TO_INVOICE", "reconciliation_id": str(RUN)}
    assert reconciliations.failed_generation(
        NO_SESSION, "reconciliation", RUN, generation
    ) == FailedSubject(
        entity_id=ENTITY, period_id=PERIOD, key=f"BILLING_TO_INVOICE:{ENTITY}:ASC606:{PERIOD}"
    )
    assert reconciliations.failed_generation(NO_SESSION, "reconciliation", RUN, {}) is None
    # Two runs of one entity, book and period are one record; another period is another.
    other = {**params, "period_id": str(RUN)}
    first = summarise.failed_calculation(NO_SESSION, "journal_run", RUN, params)
    second = summarise.failed_calculation(NO_SESSION, "journal_run", ENTITY, params)
    third = summarise.failed_calculation(NO_SESSION, "journal_run", RUN, other)
    assert first is not None and second is not None and third is not None
    assert first.key == second.key != third.key


def test_job_failed_item_1_the_alert_of_a_job_nobody_started(tmp_path: Any) -> None:
    """05 OPR-24: the fourth alert kind is a warning with runbook RB-07; its fields are
    identifiers and codes, and a field that could carry a value is refused before any sink."""
    assert (SEVERITY[OperatorAlertKind.JOB_FAILED], RUNBOOK[OperatorAlertKind.JOB_FAILED]) == (
        "WARNING",
        "RB-07",
    )
    # five kinds since FILE_SHRED_INCOMPLETE (05 OPR-24 rev 1.171; item
    # FILE-SHRED-DURABLE-ORDER-1): every kind keeps its severity and its runbook
    assert set(SEVERITY) == set(RUNBOOK) == set(OperatorAlertKind) and len(OperatorAlertKind) == 5
    at = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    alert = job_failed_alert(
        tenant_id=ENTITY,
        job_id=RUN,
        job_kind="AUDIT_CHAIN_VERIFY",
        queue="maintenance",
        attempt=3,
        problem="job-stalled",
        initiator="SYSTEM",
        raised_at=at,
    )
    assert (alert.kind, alert.severity, alert.runbook) == (
        OperatorAlertKind.JOB_FAILED,
        "WARNING",
        "RB-07",
    )
    assert dict(alert.fields) == {
        "tenant_id": str(ENTITY),
        "job_id": str(RUN),
        "job_kind": "AUDIT_CHAIN_VERIFY",
        "queue": "maintenance",
        "attempt": 3,
        "problem": "job-stalled",
        "initiator": "SYSTEM",
    }
    # An unexpected error has no slug of the catalogue; its ``about:blank`` is values-free.
    blank = job_failed_alert(
        tenant_id=ENTITY,
        job_id=RUN,
        job_kind="REPORT_RUN",
        queue="reports",
        attempt=1,
        problem="about:blank",
        initiator="API_CLIENT",
        raised_at=at,
    )
    assert blank.fields["problem"] == "about:blank"
    assert LogSink().deliver(alert) == f"log:{alert.id}"
    assert FileSink(tmp_path, FrozenClock(at)).deliver(alert).startswith("file:20260912.jsonl:")
    with pytest.raises(ValuesNotFree):
        job_failed_alert(
            tenant_id=ENTITY,
            job_id=RUN,
            job_kind="REPORT_RUN",
            queue="reports",
            attempt=1,
            problem="postgresql://erev_app:secret@127.0.0.1:5432/erev",
            initiator="SYSTEM",
            raised_at=at,
        )
