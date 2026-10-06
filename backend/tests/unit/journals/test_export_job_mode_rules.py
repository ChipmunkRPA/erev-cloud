"""Item JRN-JOB-MODE-1 as pure rules (register index 244; 04 API-S-Job and §16.7 ``retry`` rev
1.281; the supervisor's ruling of 2026-10-02 on lane F-CLO-WEB's judgement K3). CPU-only: which
mode a ``JOURNAL_EXPORT`` job answers, that the four words are the ones the four commands store,
and what the relay's result states. The database witnesses are in
``tests/domain/journals/test_failed_run_exit.py``.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import pytest
from erev_api.domain.journals import export, failed_exits
from erev_api.schemas.common import (
    JOB_MODE_EXPORT,
    JOB_MODE_RESTORE,
    JOURNAL_EXPORT_MODE_PARAM,
    JOURNAL_EXPORT_MODES,
    job_mode,
)

DOCS: Final = Path(__file__).resolve().parents[4] / "docs"
RUN, BATCH = UUID(int=1), UUID(int=2)
KIND: Final = "JOURNAL_EXPORT"
STORED: Final = (export.MODE_EXPORT, export.MODE_RETRY, failed_exits.CANCEL, failed_exits.HAND_OVER)


class _Batches:
    """A session that answers the external id of one batch, and counts what it is asked."""

    def __init__(self, external_id: str | None) -> None:
        self.external_id = external_id
        self.statements = 0

    def execute(self, statement: Any) -> _Batches:
        self.statements += 1
        return self

    def scalar_one_or_none(self) -> str | None:
        return self.external_id


def test_a_journal_export_job_answers_the_mode_its_params_store() -> None:
    """API-S-Job ``mode`` rev 1.281: derived from ``params.mode`` of a ``JOURNAL_EXPORT`` job,
    one answer for each of the four stored words. A job that stores none — every export and
    retry deferred before rev 1.281 — answers null: it may have been either. An unknown word
    answers null too, and no other kind reads the param."""
    for stored in STORED:
        params = {"journal_run_id": str(RUN), JOURNAL_EXPORT_MODE_PARAM: stored}
        assert job_mode(KIND, params) == JOURNAL_EXPORT_MODES[stored]
    assert len(set(JOURNAL_EXPORT_MODES.values())) == 4  # four commands, four answers
    assert job_mode(KIND, {"journal_run_id": str(RUN)}) is None
    assert job_mode(KIND, None) is None
    assert job_mode(KIND, {JOURNAL_EXPORT_MODE_PARAM: "PURGE"}) is None
    assert job_mode("CLOSE_RUN", {JOURNAL_EXPORT_MODE_PARAM: export.MODE_EXPORT}) is None
    # the snapshot's two words are untouched (04 rev 1.67)
    assert job_mode("TENANT_SNAPSHOT", {"load": {}}) == JOB_MODE_RESTORE
    assert job_mode("TENANT_SNAPSHOT", None) == JOB_MODE_EXPORT


def test_the_four_words_are_the_ones_the_four_commands_store() -> None:
    """The mapping's keys are the stored modes and nothing else: the two the relay runs for
    (``export_run``, ``retry_batch``) and the two exits, which are the registered handlers. The
    param's name and the batch's key are one name in the three modules."""
    assert set(JOURNAL_EXPORT_MODES) == set(STORED)
    assert export.RELAY_MODES == {export.MODE_EXPORT, export.MODE_RETRY}
    assert set(export.MODE_HANDLERS) == {failed_exits.CANCEL, failed_exits.HAND_OVER}
    assert not export.RELAY_MODES & set(export.MODE_HANDLERS)
    assert export.MODE_PARAM == JOURNAL_EXPORT_MODE_PARAM == "mode"
    assert failed_exits.BATCH_PARAM == export.BATCH_PARAM == "journal_batch_id"
    run = inspect.getsource(export.export_run)
    assert '{"journal_run_id": str(run_id), MODE_PARAM: MODE_EXPORT}' in run
    retry = inspect.getsource(export.retry_batch)
    assert "MODE_PARAM: MODE_RETRY, BATCH_PARAM: str(batch_id)" in retry


def test_the_relay_states_its_mode_and_a_retry_its_batch() -> None:
    """``result.mode`` in the word API-S-Job answers; for a retry ``result.batch`` — id and
    external id of the batch the command named. A job without a mode states nothing and asks
    nothing; an export asks nothing either."""
    old = _Batches("erev:AVM:JR-000001:1:1")
    assert export.stated_mode(old, {"journal_run_id": str(RUN)}) == {}  # type: ignore[arg-type]
    exported = export.stated_mode(
        old,  # type: ignore[arg-type]
        {"journal_run_id": str(RUN), export.MODE_PARAM: export.MODE_EXPORT},
    )
    assert exported == {"mode": JOURNAL_EXPORT_MODES[export.MODE_EXPORT]}
    assert old.statements == 0
    retry = {
        "journal_run_id": str(RUN),
        export.MODE_PARAM: export.MODE_RETRY,
        export.BATCH_PARAM: str(BATCH),
    }
    named = _Batches("erev:AVM:JR-000001:1:1")
    assert export.stated_mode(named, retry) == {  # type: ignore[arg-type]
        "mode": JOURNAL_EXPORT_MODES[export.MODE_RETRY],
        "batch": {"id": str(BATCH), "external_id": "erev:AVM:JR-000001:1:1"},
    }
    assert named.statements == 1
    # a batch that cannot be read is not invented
    assert export.stated_mode(_Batches(None), retry) == {  # type: ignore[arg-type]
        "mode": JOURNAL_EXPORT_MODES[export.MODE_RETRY]
    }


def test_a_relay_mode_reaches_no_exit_and_an_unknown_mode_is_refused() -> None:
    """The handler hands a job to an exit only for a mode that is not the relay's own, and a
    mode nobody registered is still an error (the rule of rev 1.159, unchanged)."""
    source = inspect.getsource(export.export_job)
    assert "if mode is not None and str(mode) not in RELAY_MODES:" in source
    with pytest.raises(LookupError, match="no handler is registered for JOURNAL_EXPORT mode"):
        export.export_job(
            None,  # type: ignore[arg-type]
            {"journal_run_id": str(RUN), export.MODE_PARAM: "PURGE"},
        )


def test_the_rows_state_the_mode() -> None:
    """04 rev 1.281 states the four words, the snapshot's two beside them, the job without a
    mode and the result's two members word for word; the words of the row are the words the
    member answers; fragment 14 rev 1.72 names the two database witnesses."""
    assert dict(JOURNAL_EXPORT_MODES) == {
        word: word for word in ("EXPORT", "RETRY", "CANCEL", "HAND_OVER")
    }
    model = (DOCS / "04-DATA_MODEL.md").read_text(encoding="utf-8")
    for sentence in (
        "the member answers a kind's words as that kind states them",
        "`TENANT_SNAPSHOT` answers `export` or `restore` (lower case since rev 1.67)",
        "`JOURNAL_EXPORT` answers `EXPORT` for the run's export",
        "`RETRY` for the retry of a batch (`POST /journal-batches/{id}/retry`)",
        "`CANCEL` and `HAND_OVER` for the two ways out of `failed` (T-SL-07)",
        "Null still for a `JOURNAL_EXPORT` job whose params carry no mode",
        "`result.mode`, `RETRY` for this command and `EXPORT` for the run's `export`",
        "`result.batch`: `{id, external_id}` of the batch the command named",
        "The jobs of the two exits state their mode by API-S-Job `mode` alone",
    ):
        assert model.count(sentence) == 1, sentence
    fragment = (DOCS / "build-spec/14-close-reports-ai-demo-release.md").read_text(encoding="utf-8")
    exits = "backend/tests/domain/journals/test_failed_run_exit.py"
    for witness in (
        f"`{exits}::test_the_export_job_states_its_mode_and_a_retry_names_its_batch`",
        "`::test_the_cancel_of_a_failed_run_answers_its_mode` — the cancel's job answers `CANCEL`",
    ):
        assert fragment.count(witness) == 1, witness
