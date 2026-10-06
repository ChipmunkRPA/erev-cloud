"""Item JRN-FAILED-CANCEL-1 as pure rules (supervisor ruling R-112 (c); 04 E-34 and §16.7 rev
1.159; 05 §5.6 rev 1.98; dev-guide DG-KRN-JOB-05 rev 1.142; Alembic revision 0108). CPU-only: the
revision's literals against the renderer and the installing revision, the two modes the worker
registers, the shape of a refusal a job returns, and the comparison that keeps a cancel from being
decided on a stale answer of the ledger; and, for item JRN-DISPATCH-DEAD-1 (rulings R-118 (k)
and R-119 (c); 05 ADP-31 rev 1.98), what the death of an export message records for its batch;
and, for item JRN-CANCEL-APPROVED-PENDING-1 (ruling R-119 (c); 04 §16.7 ``cancel`` (c)), which
message of a run a refusal names and the sentences of the command against the documents' rows;
and, for item JRN-RETRY-CLAIMED-1 (the supervisor's ruling of 2026-10-01 08:31; 04 §16.7 rev
1.221), the retry's sentences against its row and the rule that derives ``handed_over_at``.
The database witnesses are ``tests/domain/journals/test_failed_run_exit.py``.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api import worker
from erev_api.auth.principal import system_principal
from erev_api.clock import FrozenClock
from erev_api.db.transitions import TRANSITIONS, transition_trigger_sql
from erev_api.domain.journals import commands, export, failed_exits, ports, queries, summarise
from erev_api.enums import GlAdapter, JobKind, OutboxStatus, OutboxTopic
from erev_api.events import outbox
from erev_api.jobs import registry
from erev_api.jobs.context import JobContext, JobRuntime
from erev_api.problems import TYPE_BASE, Problem, ProblemError

VERSIONS: Final = Path(__file__).resolve().parents[4] / "backend/erev_api/db/migrations/versions"
DOCS: Final = Path(__file__).resolve().parents[4] / "docs"
TENANT: Final = UUID(int=7)
RUN: Final = UUID(int=11)
FIRST, SECOND = UUID(int=21), UUID(int=22)


def _load(stem: str) -> Any:
    spec = importlib.util.spec_from_file_location(stem, VERSIONS / f"{stem}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_0108_re_renders_the_two_journal_transition_functions() -> None:
    """04 E-34 rev 1.159: revision 0108 carries the fresh rendering of
    ``tg_journal_run__transition`` and ``tg_journal_batch__transition`` (DG-ARC-07) and restores
    the literals revision 0046 installed on the way down (DG-MIG-04); nothing but the pair
    ``failed`` → ``cancelled`` differs."""
    revision = _load("0108_jrn_failed_cancel_pairs")
    installer = _load("0046_journal_tables")
    assert revision.revision == "0108"
    for table, body, previous, installed in (
        (
            "journal_run",
            revision.RUN_BODY,
            revision.RUN_PREVIOUS,
            installer.JOURNAL_RUN_TRANSITION_BODY,
        ),
        (
            "journal_batch",
            revision.BATCH_BODY,
            revision.BATCH_PREVIOUS,
            installer.JOURNAL_BATCH_TRANSITION_BODY,
        ),
    ):
        assert body == transition_trigger_sql(table), table
        assert previous == installed, table
        [(old, new)] = [
            (before, after)
            for before, after in zip(previous.splitlines(), body.splitlines(), strict=True)
            if before != after
        ]
        assert "'failed>cancelled'" in new and "'failed>cancelled'" not in old
        assert new.replace("'failed>cancelled', ", "") == old
        assert "$fn$" not in body and "$fn$" not in previous
    assert (
        TRANSITIONS["journal_run"].pairs
        == TRANSITIONS["journal_batch"].pairs
        == {
            ("draft", "approved"),
            ("approved", "exported"),
            ("exported", "acknowledged"),
            ("exported", "failed"),
            ("failed", "exported"),
            ("draft", "cancelled"),
            ("approved", "cancelled"),
            ("failed", "cancelled"),
        }
    )


def test_the_worker_registers_both_modes() -> None:
    """05 §5.6 rev 1.98: ``JOURNAL_EXPORT`` stays one job kind with one handler; the two modes are
    registered by the module the worker imports with its handler modules, so a job a command of
    the API deferred finds its mode in the worker's process."""
    assert "erev_api.domain.journals.failed_exits" in worker.HANDLER_MODULES
    assert export.MODE_HANDLERS == {
        failed_exits.CANCEL: failed_exits.cancel_job,
        failed_exits.HAND_OVER: failed_exits.hand_over_job,
    }
    assert registry.HANDLERS[JobKind.JOURNAL_EXPORT].handler is export.export_job


def _context() -> JobContext:
    clock = FrozenClock(datetime(2026, 9, 30, 12, 0, tzinfo=UTC))
    return JobContext(
        job_id=UUID(int=99),
        tenant_id=TENANT,
        kind=JobKind.JOURNAL_EXPORT,
        principal=system_principal(TENANT),
        runtime=JobRuntime(clock=clock, keyring=None, files=None),
        persisted=False,
    )


def test_a_mode_nobody_registered_is_not_run_as_an_export() -> None:
    """A job that names a mode is never taken for the relay of the run's messages: without a
    handler for the mode the attempt fails (and is retried), it sends nothing."""
    with pytest.raises(LookupError, match="no handler is registered for JOURNAL_EXPORT mode"):
        export.export_job(_context(), {"journal_run_id": str(RUN), export.MODE_PARAM: "PURGE"})


def test_a_refusal_is_the_result_of_the_job_not_its_error() -> None:
    """Dev-guide DG-KRN-JOB-05 rev 1.142: every raised error is retried while attempts remain, so
    a decision that is final is returned. The job ends ``SUCCEEDED_WITH_EXCEPTIONS``;
    ``result.outcome`` says what was not done and ``result.refusal`` is the problem object, its
    instance the job (04 §16.7 rev 1.159: what a screen binds)."""
    sentence = failed_exits.PARTLY_IN_LEDGER.format(run_no="JR-000007", external_id="erev:t:7:1:2")
    problem = Problem(
        "invalid-transition",
        sentence,
        errors=[ProblemError(field="state", rule_id=export.RULE_STATES, message=sentence)],
    )
    jc = _context()
    outcome = export.Refused(failed_exits.NOT_CANCELLED, problem).job_outcome(
        jc, RUN, {"asked": 2, "held": 0, "cancelled": 0}
    )
    assert outcome.state == "SUCCEEDED_WITH_EXCEPTIONS"
    assert outcome.result == {
        "href": f"/api/v1/journal-runs/{RUN}",
        "counts": {"asked": 2, "held": 0, "cancelled": 0},
        "outcome": "NOT_CANCELLED",
        "refusal": {
            "type": f"{TYPE_BASE}invalid-transition",
            "title": "Action not available in this state",
            "status": 409,
            "detail": sentence,
            "instance": f"/api/v1/jobs/{jc.job_id}",
            "code": None,
            "errors": [
                {
                    "field": "state",
                    "sheet": None,
                    "row": None,
                    "rule_id": "E-34",
                    "message": sentence,
                }
            ],
        },
    }
    assert {failed_exits.CANCELLED, failed_exits.NOT_CANCELLED} == {"CANCELLED", "NOT_CANCELLED"}
    assert {failed_exits.HANDED_OVER, failed_exits.NOT_HANDED_OVER} == {
        "HANDED_OVER",
        "NOT_HANDED_OVER",
    }


def _asked(batch_id: UUID, attempts: int) -> failed_exits._Asked:
    return failed_exits._Asked(
        id=batch_id,
        external_id=f"erev:t:7:1:{batch_id.int}",
        adapter=GlAdapter.NETSUITE,
        attempts=attempts,
        ledger="NetSuite",
        context={"base_url": "https://ledger.invalid", "config": {}},
    )


def _batch(batch_id: UUID, state: str, attempts: int) -> dict[str, Any]:
    return {
        "id": batch_id,
        "state": state,
        "attempt_count": attempts,
        "external_id": f"erev:t:7:1:{batch_id.int}",
    }


@pytest.mark.parametrize(
    ("batches", "asked", "named"),
    [
        # the batches the ledger was asked about, as they were: nothing was sent since
        ([(FIRST, "failed", 1), (SECOND, "failed", 3)], [(FIRST, 1), (SECOND, 3)], None),
        # a batch that never failed was not asked and is not compared
        ([(FIRST, "failed", 1), (SECOND, "approved", 0)], [(FIRST, 1)], None),
        # a retry was recorded since the question: its answer may be stale
        ([(FIRST, "failed", 2)], [(FIRST, 1)], FIRST),
        ([(FIRST, "failed", 1), (SECOND, "failed", 4)], [(FIRST, 1), (SECOND, 3)], SECOND),
        # a batch failed after the question: the ledger was never asked about it
        ([(FIRST, "failed", 1), (SECOND, "failed", 1)], [(FIRST, 1)], SECOND),
    ],
)
def test_a_batch_sent_since_the_question_is_named(
    batches: list[tuple[UUID, str, int]], asked: list[tuple[UUID, int]], named: UUID | None
) -> None:
    """The ledger's answer is good for a batch as it stood when it was asked: the transaction
    that cancels or hands over compares each failed batch's attempt count with the one the
    question saw and refuses on the first difference."""
    refused = failed_exits._sent_meanwhile(
        [_batch(*item) for item in batches], [_asked(*item) for item in asked]
    )
    if named is None:
        assert refused is None
        return
    assert refused is not None and refused.slug == "invalid-transition"
    assert refused.detail == (
        f"Batch erev:t:7:1:{named.int} was sent again while the ledger was asked, so nothing "
        "was changed. Ask again."
    )
    assert [(error.field, error.rule_id) for error in refused.errors] == [("state", "E-34")]


def test_the_sentences_end_as_the_documents_state_them() -> None:
    """04 §16.7 rev 1.159: the refusals without a PRD row, word for word."""
    assert failed_exits.UNREACHABLE.format(message="NetSuite answered HTTP 503") == (
        "The ledger could not be reached, so nothing was changed: NetSuite answered HTTP 503. "
        "Ask again when the ledger answers."
    )
    gone = failed_exits.CONNECTION_GONE.format(external_id="erev:t:7:1:1")
    assert failed_exits.NOT_ASKED.format(reason=gone) == (
        "The ledger could not be asked, so nothing was changed: batch erev:t:7:1:1 names a "
        "general ledger connection that no longer exists."
    )
    disabled = failed_exits.CONNECTION_DISABLED.format(code="netsuite-eu")
    assert failed_exits.NOT_ASKED.format(reason=disabled) == (
        "The ledger could not be asked, so nothing was changed: general ledger connection "
        "netsuite-eu is disabled."
    )
    assert (
        failed_exits.CANCEL_UNDER_WAY == "A cancellation of this journal run is already under way."
    )
    assert failed_exits.HAND_OVER_UNDER_WAY == "A hand-over of this batch is already under way."
    assert failed_exits.NOT_FAILED == "Only a failed batch can be handed over."
    assert failed_exits.CSV_BATCH == (
        "A CSV batch is not handed over. Correct what its export named and retry it, or cancel "
        "the journal run."
    )
    assert failed_exits.BATCH_BEING_SENT.format(external_id="erev:t:7:1:1") == (
        "Batch erev:t:7:1:1 is being sent. It cannot be handed over while it is being sent."
    )
    assert commands.EXPORT_ATTEMPTED.format(external_id="erev:t:7:1:1") == (
        "An export of this journal run is in progress: an attempt to send batch erev:t:7:1:1 "
        "failed and it will be sent again. It cannot be cancelled until the batch has been sent "
        "or has failed."
    )


def _row(document: str, start: str) -> str:
    """The one table row of a governed document that starts with ``start``."""
    lines = (DOCS / document).read_text(encoding="utf-8").splitlines()
    [row] = [line for line in lines if line.startswith(start)]
    return row


def test_the_cancel_row_states_every_refusal_of_the_command_word_for_word() -> None:
    """04 §16.7 ``cancel`` rev 1.204 and PRD SM-08 rev 1.133: the sentences the command refuses
    with stand in the data model's row as the code says them — the three of a run without a
    failed batch, and the three more of a run with one — and the first three in the PRD's row of
    ``draft``, ``approved`` → ``cancelled``. A placeholder is the row's own."""
    data_model = _row("04-DATA_MODEL.md", "| `POST /journal-runs/{id}/cancel` |")
    for sentence in (
        commands.LATER_RUN.format(run_no="<run_no>"),
        commands.EXPORT_IN_PROGRESS.format(external_id="<external id>"),
        commands.EXPORT_ATTEMPTED.format(external_id="<external id>"),
        failed_exits.PARTLY_IN_LEDGER.format(run_no="<run no>", external_id="<external id>"),
        failed_exits.EXPORT_WAITING.format(external_id="<external id>"),
        failed_exits.CANCEL_UNDER_WAY,
    ):
        assert f'"{sentence}"' in data_model, sentence
    assert "Three refusals, each 409 `invalid-transition` with `rule_id` `E-34`" in data_model
    state_machine = _row("02-PRD.md", "| `draft`, `approved` | `cancelled` | Cancel journal run |")
    for sentence in (
        commands.LATER_RUN.format(run_no="<run>"),
        commands.EXPORT_IN_PROGRESS.format(external_id="<batch>"),
        commands.EXPORT_ATTEMPTED.format(external_id="<batch>"),
    ):
        assert f'"{sentence}"' in state_machine, sentence


def test_the_retry_row_states_its_refusals_word_for_word() -> None:
    """04 §16.7 ``retry`` rev 1.221 (item JRN-RETRY-CLAIMED-1): the two sentences the command
    refuses with stand in the data model's row as the code says them — the second under
    ``E-34`` by name — and the row states the rule they follow from. A placeholder is the row's
    own."""
    row = _row("04-DATA_MODEL.md", "| `POST /journal-batches/{id}/retry` |")
    for sentence in (
        export.NOT_RETRYABLE,
        export.RETRY_CLAIMED.format(external_id="<external id>"),
    ):
        assert f'"{sentence}"' in row, sentence
    claimed = row.index(export.RETRY_CLAIMED.format(external_id="<external id>"))
    assert "409 `invalid-transition`, `rule_id` `E-34`" in row[:claimed]
    assert "writes its message only when the message the batch names is settled" in row
    # what the job of a retry beside a waiting message says (the supervisor's ruling of
    # 2026-10-01 11:30): the member and its three members, as ``export.waiting`` writes them
    assert "`result.waiting`" in row
    assert "`{journal_batch_id, external_id, next_attempt_at}`" in row
    # PRD SM-08 "Retry export" rev 1.167 says the same: the refusal beside a claim word for word,
    # the retry that writes no second message, and the three batch commands a closed period
    # still takes (witnessed in ``tests/domain/journals/test_failed_run_exit.py``)
    state_machine = _row("02-PRD.md", "| `failed` | `exported` | Retry export (")
    assert f'"{export.RETRY_CLAIMED.format(external_id="<batch>")}"' in state_machine
    assert "answers 202 with its job and writes no second message" in state_machine
    assert "`result.waiting`" in state_machine
    assert (
        "The retry, the hand-over and the acknowledgement of a batch are taken in a closed "
        "period too"
    ) in state_machine


@pytest.mark.parametrize(
    ("adapter", "holds_a_file", "handed_over"),
    [
        (GlAdapter.NETSUITE, True, True),
        (GlAdapter.QUICKBOOKS_ONLINE, True, True),
        (GlAdapter.NETSUITE, False, False),  # posted by its adapter: exported, and no file
        (GlAdapter.CSV, True, False),  # the file of a CSV batch is its export
        (GlAdapter.CSV, False, False),
    ],
)
def test_a_batch_says_when_it_was_handed_over(
    adapter: GlAdapter, holds_a_file: bool, handed_over: bool
) -> None:
    """API-S-JournalRun ``batches`` ``handed_over_at`` (04 §16.7 rev 1.221) is derived, no column
    holds it: the export time of a batch that holds an export file and whose adapter is not
    ``CSV`` — an ERP adapter stores no file, so only the hand-over gave such a batch one."""
    exported = datetime(2026, 10, 1, 15, 0, tzinfo=UTC)
    row = {
        "adapter": adapter.value,
        "export_file_id": UUID(int=5) if holds_a_file else None,
        "exported_at": exported,
    }
    expected = exported if handed_over else None
    assert queries.handed_over_at(row) == expected
    assert queries.handed_over_at({**row, "adapter": adapter}) == expected
    # a batch that was never exported was never handed over
    assert queries.handed_over_at({**row, "export_file_id": None, "exported_at": None}) is None


def test_a_refusal_names_the_first_batch_whose_message_has_the_status() -> None:
    """``export.unsettled`` answers the run's unsettled messages in batch and chunk order; a
    refusal names the first batch of its status. A message no relay has claimed is one the relay
    will still send (``failed_exits``), and is not one that was attempted (``commands``)."""
    held = [
        ("erev:t:7:1:1", OutboxStatus.PENDING),
        ("erev:t:7:1:2", OutboxStatus.FAILED),
        ("erev:t:7:1:3", OutboxStatus.DISPATCHING),
        ("erev:t:7:1:4", OutboxStatus.FAILED),
    ]
    assert export.first_with(held, OutboxStatus.DISPATCHING) == "erev:t:7:1:3"
    assert export.first_with(held, OutboxStatus.FAILED) == "erev:t:7:1:2"
    assert export.first_with(held, *failed_exits.STILL_TO_BE_SENT) == "erev:t:7:1:1"
    assert export.first_with(held[:1], OutboxStatus.DISPATCHING, OutboxStatus.FAILED) is None
    assert export.first_with([], *export.UNSETTLED) is None
    # a settled message — delivered, or dead beside a batch recorded ``failed`` — is not read
    assert set(OutboxStatus) - set(export.UNSETTLED) == {OutboxStatus.DISPATCHED, OutboxStatus.DEAD}
    assert set(failed_exits.STILL_TO_BE_SENT) == {OutboxStatus.PENDING, OutboxStatus.FAILED}


NOT_COMPLETED: Final = (
    "eRev could not complete the export ({error}); the ledger may hold the batch."
)


@pytest.mark.parametrize(
    ("error", "recorded"),
    [
        # an ADP-12 error is the ledger's own word, or its silence at the last attempt
        (ports.Permanent("The ledger period FY2026-P09 is closed."), None),
        (ports.Transient("NetSuite answered HTTP 503."), None),
        # anything else is eRev's own, and the ledger may have accepted before it happened
        (Problem("statement-timeout", "The request took too long."), "statement-timeout"),
        (Problem("lock-conflict", "Another change was being saved."), "lock-conflict"),
        (LookupError("no GL adapter is registered for NETSUITE"), "LookupError"),
    ],
)
def test_what_a_dead_export_message_records_for_its_batch(
    monkeypatch: pytest.MonkeyPatch, error: Exception, recorded: str | None
) -> None:
    """05 ADP-31 rev 1.98 (item JRN-DISPATCH-DEAD-1): the relay's last failed attempt records the
    batch ``failed`` whatever the class of the error. An ADP-12 error keeps the adapter's message;
    any other is named — the slug of a catalogue problem, else the class — in a sentence that
    says the ledger may hold the batch, and the name goes to the notification, which then does
    not say that the ledger rejected the batch (PRD NTF-10 rev 1.133)."""
    seen: list[tuple[UUID, str, str | None]] = []

    def record(jc: JobContext, batch_id: UUID, message: str, *, own_error: str | None) -> None:
        seen.append((batch_id, message, own_error))

    monkeypatch.setattr(export, "_record_failure", record)
    export.batch_died(_context(), {"journal_batch_id": str(FIRST), "external_id": "e"}, error)
    expected = str(error) if recorded is None else NOT_COMPLETED.format(error=recorded)
    assert seen == [(FIRST, expected, recorded)]
    assert outbox.DEAD_HOOKS == {OutboxTopic.JOURNAL_EXPORT: export.batch_died}


def test_the_export_failed_notification_says_who_failed() -> None:
    """PRD NTF-10 rev 1.133: the body of ``EXPORT_FAILED`` has two forms, each word for word in
    the PRD's row. A batch the ledger refused — or that the ledger never answered — says that
    the adapter rejected it and why; a batch whose dispatch ended with an error of eRev's own
    says that eRev could not complete the export and that the ledger may hold the batch, as the
    batch's own message does, and never that the ledger rejected it."""
    row = _row("02-PRD.md", "| NTF-10 | `EXPORT_FAILED` |")
    refused = export.FAILED_BODY.format(adapter="<adapter>", count="<n>", reason="<reason>")
    own = export.NOT_COMPLETED_BODY.format(adapter="<adapter>", error="<slug or class>")
    assert f'"{refused}"' in row and f'"{own}"' in row
    assert f'"{export.FAILED_TITLE.format(run="<run>")}"' in row
    assert "rejected" in refused and "rejected" not in own
    said = export.NOT_COMPLETED.format(error="statement-timeout")
    assert said == NOT_COMPLETED.format(error="statement-timeout")
    # the body opens as the batch's own message does and ends with the same warning
    start, end = "eRev could not complete the export ", "; the ledger may hold the batch."
    assert said.startswith(start) and said.endswith(end)
    shown = export.NOT_COMPLETED_BODY.format(adapter="NETSUITE", error="statement-timeout")
    assert shown == (
        "eRev could not complete the export through NETSUITE (statement-timeout); the ledger "
        "may hold the batch. Retry it: a retry asks the ledger first, so nothing posts twice."
    )
    assert shown.startswith(start) and end in shown


# --- an exit's job that is run again (item JRN-EXIT-JOB-IDEMPOTENT-1; 04 §16.7 rev 1.246) ---------

_DIFFERS: Final = "Batch erev:t:7:1:2 differs from what was calculated and approved: 3 lines."
_CLOSED: Final = "Feb 2023 is closed for E1 in book ASC606. A journal run cannot be cancelled."
_REFUSALS: Final = (
    export._state_problem(failed_exits.NOT_FAILED),
    Problem(
        "invalid-transition",
        _DIFFERS,
        errors=[ProblemError(field="lines", rule_id=export.RULE_RECOUNT, message=_DIFFERS)],
    ),
    Problem(
        "period-closed",
        _CLOSED,
        errors=[ProblemError(rule_id=summarise.RULE_PERIOD_CLOSED, message=_CLOSED)],
    ),
)


@pytest.mark.parametrize("refusal", _REFUSALS, ids=["a state", "the recount", "a closed period"])
def test_a_refusal_rebuilt_from_its_event_is_the_refusal_the_job_returned(refusal: Problem) -> None:
    """04 §16.7 rev 1.246 (review finding F10): the ``detail`` of a ``DENIED`` decision event
    holds what the refusal is rebuilt from — the problem, the field, the rule id, the message —
    and the job's counts, so an attempt that is run again returns the very problem object and
    counts its job returned first; the event stores them as JSON. A refusal on no field (PRD
    ERR-86) and one on ``lines`` (the recount) come back as they were."""
    jc = _context()
    counts = {"asked": 1, "held": 0, "cancelled": 0}
    detail = json.loads(json.dumps(failed_exits._refusal_detail(jc, refusal, counts)))
    assert sorted(detail) == ["counts", "field", "job_id", "message", "problem", "rule_id"]
    assert detail["job_id"] == str(jc.job_id)
    first = export.Refused(failed_exits.NOT_CANCELLED, refusal).job_outcome(jc, RUN, counts)
    again = failed_exits._again(
        jc,
        RUN,
        (False, detail),
        done=failed_exits.CANCELLED,
        not_done=failed_exits.NOT_CANCELLED,
    )
    assert (again.state, again.result) == (first.state, first.result)


def test_a_decision_that_succeeded_is_returned_with_the_counts_of_its_event() -> None:
    """The ``after`` of a ``SUCCESS`` decision event names its job and carries the counts the job
    ended with: the attempt that is run again ends ``SUCCEEDED`` with them, and reads nothing
    else of the event."""
    jc = _context()
    counts = {"asked": 2, "held": 0, "handed_over": 1}
    after = {"state": "exported", "job_id": str(jc.job_id), "counts": counts}
    again = failed_exits._again(
        jc,
        RUN,
        (True, after),
        done=failed_exits.HANDED_OVER,
        not_done=failed_exits.NOT_HANDED_OVER,
    )
    assert (again.state, again.result) == (
        "SUCCEEDED",
        {"href": f"/api/v1/journal-runs/{RUN}", "counts": counts, "outcome": "HANDED_OVER"},
    )


def test_the_exit_rows_state_that_an_attempt_run_again_returns_its_decision() -> None:
    """04 §16.7 ``cancel`` and ``hand-over`` rev 1.246: both rows state the rule and the members
    of the events it reads."""
    cancel = _row("04-DATA_MODEL.md", "| `POST /journal-runs/{id}/cancel` |")
    hand_over = _row("04-DATA_MODEL.md", "| `POST /journal-batches/{id}/hand-over` |")
    assert "**an attempt that is run again returns what its job decided.**" in cancel
    assert "`problem`, `field`, `rule_id`, `message`" in cancel
    assert "`after.counts`, `detail.counts`" in cancel
    assert "returns what its job decided, as the cancel's does" in hand_over
    assert "the `SUCCESS` event carries `job_id` and `counts` since this revision" in hand_over


# --- a batch the ledger may still take (item JRN-EXIT-SETTLE-1; 04 §16.7 rev 1.247) ---------------

_NOW: Final = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def _death(external_id: str, error: str | None, minutes: float) -> tuple[str, str | None, datetime]:
    """A failed batch whose export message died of ``error`` ``minutes`` before ``_NOW``."""
    return external_id, error, _NOW - timedelta(minutes=minutes)


def test_the_settle_rule_names_an_accepted_batch_before_one_that_waits() -> None:
    """04 §16.7 rev 1.247 (review finding F9): of each failed batch of an ERP adapter the exits
    read the name its dead message kept and the instant its last attempt ended. A batch the
    ledger accepted is named at any age, and before a batch that waits — each the first in batch
    and chunk order; the ledger's refusal, and a death 15 minutes old, name nothing, so the
    ledger is asked. The two names are those of the port's classes, which is what the relay
    stores; an acceptance is a ``Transient`` for the relay."""
    land = failed_exits.may_still_land
    assert (failed_exits.ACCEPTED_BY_LEDGER, failed_exits.REFUSED_BY_LEDGER) == (
        "Accepted",
        "Permanent",
    )
    assert outbox.error_name(ports.Accepted("e")) == failed_exits.ACCEPTED_BY_LEDGER
    assert outbox.error_name(ports.Permanent("e")) == failed_exits.REFUSED_BY_LEDGER
    assert issubclass(ports.Accepted, ports.Transient)
    assert not issubclass(ports.Accepted, outbox.Undeliverable)
    assert land([], _NOW) is None
    assert land([_death("b1", "Permanent", 0)], _NOW) is None  # the ledger refused: ask at once
    assert land([_death("b1", "Transient", 15)], _NOW) is None  # the ledger has had its time
    assert land([_death("b1", "Transient", 14)], _NOW) == ("b1", "1 minute")
    assert land([_death("b1", "lock-conflict", 0)], _NOW) == ("b1", "15 minutes")  # eRev's own
    assert land([_death("b1", None, 0)], _NOW) == ("b1", "15 minutes")  # no name is no refusal
    assert land([_death("b1", "Accepted", 600)], _NOW) == ("b1", None)  # at any age
    deaths = [
        _death("b1", "Permanent", 0),
        _death("b2", "Transient", 3),
        _death("b3", "Transient", 1),
        _death("b4", "Accepted", 90),
        _death("b5", "Accepted", 0),
    ]
    assert land(deaths, _NOW) == ("b4", None)
    assert land(deaths[:3], _NOW) == ("b2", "12 minutes")
    # the deaths are taken from the ONE read of the run's named messages: a failed batch of an
    # ERP adapter whose message is dead — a CSV batch has no ledger, and a message that is due
    # again is the other refusals'
    netsuite, quickbooks = GlAdapter.NETSUITE.value, GlAdapter.QUICKBOOKS_ONLINE.value
    named = [
        export.NamedMessage("b1", "failed", netsuite, OutboxStatus.DEAD, "Transient", _NOW),
        export.NamedMessage("b2", "failed", "CSV", OutboxStatus.DEAD, "lock-conflict", _NOW),
        export.NamedMessage("b3", "approved", netsuite, OutboxStatus.PENDING, None, _NOW),
        export.NamedMessage("b4", "failed", quickbooks, OutboxStatus.FAILED, "Transient", _NOW),
        export.NamedMessage("b5", "failed", quickbooks, OutboxStatus.DEAD, "Accepted", _NOW),
    ]
    assert failed_exits.deaths(named) == [("b1", "Transient", _NOW), ("b5", "Accepted", _NOW)]
    assert export.unsettled_of(named) == [
        ("b3", OutboxStatus.PENDING),
        ("b4", OutboxStatus.FAILED),
    ]


@pytest.mark.parametrize(
    ("seconds", "wait"),
    [
        (0, "15 minutes"),
        (59, "15 minutes"),
        (60, "14 minutes"),
        (61, "14 minutes"),
        (839, "2 minutes"),
        (840, "1 minute"),
        (899, "1 minute"),
        (900, None),
        (901, None),
    ],
)
def test_the_wait_is_what_is_left_of_the_fifteen_minutes(seconds: int, wait: str | None) -> None:
    """04 §16.7 rev 1.247: ``seconds`` after the end of the last attempt the answer names what
    is left of the 15 minutes in whole minutes, rounded up — "1 minute" for the last — and at 15
    minutes the ledger is asked. The 15 minutes are the longest wait of the ADP-12 schedule and
    the age at which a stranded claim is taken again (05 ADP-32)."""
    assert failed_exits.SETTLE_AFTER == export.RETRY_CAP == outbox.STRANDED_AFTER
    assert timedelta(minutes=15) == failed_exits.SETTLE_AFTER
    death = ("b1", "Transient", _NOW - timedelta(seconds=seconds))
    assert failed_exits.may_still_land([death], _NOW) == (None if wait is None else ("b1", wait))


def test_the_exit_rows_state_the_settle_refusals_word_for_word() -> None:
    """04 §16.7 ``cancel`` and ``hand-over`` rev 1.247: the four sentences stand in the two rows
    as the code says them, with the rows' placeholders, and name the minutes of
    ``SETTLE_AFTER``; PRD SM-08's two exit rows (rev 1.173) name the guard."""
    cancel = _row("04-DATA_MODEL.md", "| `POST /journal-runs/{id}/cancel` |")
    hand_over = _row("04-DATA_MODEL.md", "| `POST /journal-batches/{id}/hand-over` |")
    places = {"external_id": "<external id>", "wait": "<n> minutes"}
    assert "**not while the ledger may still take a failed batch.**" in cancel
    assert f'"{failed_exits.CANCEL_SETTLING.format(**places)}"' in cancel
    assert f'"{failed_exits.CANCEL_ACCEPTED.format(external_id="<external id>")}"' in cancel
    assert f'"{failed_exits.HAND_OVER_SETTLING.format(**places)}"' in hand_over
    assert f'"{failed_exits.HAND_OVER_ACCEPTED.format(external_id="<external id>")}"' in hand_over
    minutes = failed_exits.SETTLE_AFTER // timedelta(minutes=1)
    assert f"ended less than {minutes} minutes ago" in failed_exits.SETTLING
    guard = "the ledger has had its time (rev 1.173; item JRN-EXIT-SETTLE-1; 04 rev 1.247)"
    for start in (
        "| `failed` | `cancelled` | Cancel journal run |",
        "| `failed` | `exported` | Hand over for manual posting (",
    ):
        assert guard in _row("02-PRD.md", start), start


# --- the run's retry (item JRN-RUN-RETRY-1; 04 §16.7 ``export`` rev 1.244) ------------------------


def test_the_runs_retry_takes_each_failed_batch_by_its_message() -> None:
    """04 §16.7 ``export`` rev 1.244: the run's command decides on the one read of the messages
    its batches name. A ``failed`` batch whose message a relay has claimed refuses the whole
    command and is named — the first in batch and chunk order; a claimed message of a batch that
    is not failed refuses nothing, it is the export under way. Of the other failed batches the
    ones whose message is still to be sent or due again are left to that message, and the ones
    whose message is settled are retried."""
    netsuite = GlAdapter.NETSUITE.value
    claimed, due, dead = OutboxStatus.DISPATCHING, OutboxStatus.FAILED, OutboxStatus.DEAD
    named = [
        export.NamedMessage("b1", "approved", netsuite, claimed, None, _NOW),
        export.NamedMessage("b2", "failed", netsuite, dead, "Permanent", _NOW),
        export.NamedMessage("b3", "failed", netsuite, due, "Transient", _NOW),
        export.NamedMessage("b4", "failed", netsuite, OutboxStatus.PENDING, None, _NOW),
        export.NamedMessage("b5", "acknowledged", netsuite, OutboxStatus.DISPATCHED, None, _NOW),
    ]
    assert export.claimed_failure(named) is None
    left = {external_id for external_id, _ in export.unsettled_of(named)}
    assert {item.external_id for item in named if item.batch_state == "failed"} - left == {"b2"}
    stopped = [
        *named,
        export.NamedMessage("b6", "failed", netsuite, claimed, None, _NOW),
        export.NamedMessage("b7", "failed", netsuite, claimed, None, _NOW),
    ]
    assert export.claimed_failure(stopped) == "b6"
    assert export.claimed_failure([]) is None


def test_the_export_row_states_the_runs_retry_word_for_word() -> None:
    """04 §16.7 ``export`` rev 1.244 and PRD SM-08 "Retry export" rev 1.172: the row states the
    rule, the refusal beside a claimed message in the words of the batch's own retry, and what
    is left to a message still to be sent; the PRD's row names the run's command as a trigger."""
    row = _row("04-DATA_MODEL.md", "| `POST /journal-runs/{id}/export` |")
    assert "**a run with failed batches is retried by this command.**" in row
    assert f'"{export.RETRY_CLAIMED.format(external_id="<external id>")}"' in row
    assert "refuses the WHOLE command" in row and "nothing is written for any batch" in row
    assert "`<external id>#<attempt count>`" in row and "`result.waiting`" in row
    state_machine = _row("02-PRD.md", "| `failed` | `exported` | Retry export (")
    assert "`POST /journal-runs/{id}/export`, which retries every failed batch of the run" in (
        state_machine
    )
    assert "(rev 1.172; item JRN-RUN-RETRY-1; 04 rev 1.244)" in state_machine
