"""Item JRN-EMPTY-RUN-1 as pure rules (the supervisor's ruling of 2026-10-01; 04 §16.7
API-S-JournalRunCreate and ``submit`` rev 1.248; PRD SM-08 and ERR-96 rev 1.174). CPU-only: when a
journal run calculated now is made, that the command and the calculation ask that one rule over
the lines the run itself would read, and the two sentences against the documents' rows. The
database witnesses are ``tests/domain/journals/test_empty_run.py``.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Final

import pytest
from erev_api.domain.journals import commands, summarise

DOCS: Final = Path(__file__).resolve().parents[4] / "docs"


@pytest.mark.parametrize(
    ("live_run", "lines", "wanted"),
    [
        (False, 0, True),  # the first run of a period without activity: the lock gates need it
        (False, 4, True),
        (True, 4, True),  # a posting beyond what the runs cover
        (True, 1, True),
        (True, 0, False),  # a run stands and nothing is left to summarize
    ],
)
def test_a_run_is_pending_when_it_would_be_the_first_or_hold_a_posting(
    live_run: bool, lines: int, wanted: bool
) -> None:
    """04 §16.7 API-S-JournalRunCreate rev 1.248: a journal run calculated now is made when it
    would be the first run of its entity, book and period that is not cancelled — with or
    without lines, because a period needs such a run to lock — or when it would hold a line.
    Otherwise there is nothing to summarize and no run is made (PRD ERR-96)."""
    assert summarise.run_wanted(live_run=live_run, lines=lines) is wanted


def test_the_command_and_the_calculation_ask_one_rule_over_the_runs_own_lines() -> None:
    """The lines are those the run itself would read — ``read_detail``: the book's range beyond
    what the key's runs cover and, for a ``DELTA`` run, the LEGACY book's, through the cutoff, a
    held contract's left out. A ``DELTA`` run beside ``GROSS`` runs therefore has lines where the
    book's own postings are all covered. ``POST /journal-runs`` asks with its mode and cutoff on
    a plain read; the calculation asks with what it read under the coverage lock."""
    rule = inspect.getsource(summarise.nothing_pending)
    assert "if run_wanted(live_run=True, lines=len(found.kept)):" in rule
    assert "found = read_detail(" in rule and "if latest is None:\n        return None" in rule
    command = inspect.getsource(commands.create_run)
    assert "summarise.nothing_pending(" in command
    assert "mode=mode," in command and "cutoff=cutoff," in command
    calculation = inspect.getsource(summarise.calculate)
    assert calculation.index("found = read_detail(") < calculation.index("nothing_pending(")
    assert "period_id=period_id, found=found" in calculation
    assert calculation.index("refuse_closed_period(") < calculation.index("found = read_detail(")
    detail = inspect.getsource(summarise.read_detail)
    assert "if mode is JournalRunMode.DELTA:" in detail and "BookCode.LEGACY.value" in detail
    assert "kept = [line for line in lines if line.contract_id not in holds]" in detail


def _line(document: str, start: str) -> str:
    """The one line of a governed document that starts with ``start``."""
    lines = (DOCS / document).read_text(encoding="utf-8").splitlines()
    [found] = [line for line in lines if line.startswith(start)]
    return found


def test_the_rows_state_the_two_sentences_word_for_word() -> None:
    """04 §16.7 API-S-JournalRunCreate and ``submit`` rev 1.248, PRD SM-08 rev 1.174: the refusal
    of a run that would summarize nothing and the refusal of the submission of a run without
    lines stand in the documents as the code says them, with each document's placeholders; the
    rule id is the one PRD ERR-96 names. The first sentence names the latest run and claims no
    coverage — the period may hold postings no run journalised — and the row lists the four
    cases in which the refusal is met."""
    places = {"period": "<period>", "entity": "<entity>", "book": "<book>"}
    create = _line("04-DATA_MODEL.md", "**API-S-JournalRunCreate** (`POST /journal-runs`;")
    assert f'"{summarise.NOTHING_PENDING.format(run="<run no>", **places)}"' in create
    assert f"`errors[].rule_id` `{summarise.RULE_NOTHING_PENDING}`" in create
    assert "**no further run without a line.**" in create
    assert "covers every posting" not in summarise.NOTHING_PENDING
    assert "it does not say that the period is journalised, which `JE_COMPLETE` says" in create
    for case in (
        "(1) Every posting of the period is journalised by its runs",
        "(2) The postings beyond the runs are all of contracts under a journal-export hold",
        "(3) A run left postings out because their contract was under a journal-export hold",
        "(4) A `cutoff_known_at` before the postings beyond the runs",
    ):
        assert case in create, case
    assert "**The first run of a period without activity is made.**" in create
    assert "the period locks on it as it stands" in create
    submit = _line("04-DATA_MODEL.md", "| `POST /journal-runs/{id}/submit` |")
    assert f'"{commands.NO_LINES.format(run_no="<run no>")}"' in submit
    asked = _line("02-PRD.md", '| none | none (job `QUEUED` then `RUNNING`; label "Calculating")')
    assert "answers 409 `invalid-transition` and starts no job (ERR-96)" in asked
    submitted = _line("02-PRD.md", '| `draft` | `draft` (label "Submitted") | Submit |')
    assert f'"{commands.NO_LINES.format(run_no="<run>")}"' in submitted
