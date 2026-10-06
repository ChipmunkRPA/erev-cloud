"""Item JR-CLOSED-PERIOD-GUARD-1 as pure rules (supervisor rulings R-97 (7) and R-112 (b) (6); 04
§14.1 DB-07 and DB-16 rev 1.205; Alembic revision 0104). CPU-only: what the revision's two bodies
say, and that the named refusal reads the states the guard reads. The triggers themselves are
witnessed at the database in ``tests/pg/test_journal_guards.py`` and the commands in
``tests/domain/journals/test_closed_period_guard.py``.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from typing import Any, Final

from erev_api import periods
from erev_api.db.lint import PERIOD_GUARD_TABLES
from erev_api.domain.journals import commands, summarise
from erev_api.enums import PeriodState
from erev_api.problems import PROBLEMS

VERSIONS: Final = Path(__file__).resolve().parents[4] / "backend/erev_api/db/migrations/versions"
DOCS: Final = Path(__file__).resolve().parents[4] / "docs"
TESTS: Final = Path(__file__).resolve().parents[2]


def _load(stem: str) -> Any:
    spec = importlib.util.spec_from_file_location(stem, VERSIONS / f"{stem}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _flat(body: str) -> str:
    return " ".join(body.split())


def test_0104_guards_a_run_by_its_period_and_a_line_by_its_batch() -> None:
    """Revision 0104: the run guard decides an insert and a move to ``cancelled`` only, reads the
    period's state row ``FOR SHARE`` and refuses the two closed states under the code of DB-07;
    the line guard reads the line's batch ``FOR SHARE`` and admits ``draft`` alone under a code of
    its own. Both leave a row outside the session's scope to row-level security, as the DB-07
    line guards do."""
    revision = _load("0104_jr_closed_period_guard")
    assert revision.revision == "0104"
    run, line = _flat(revision.RUN_PERIOD_GUARD_BODY), _flat(revision.LINE_BATCH_DRAFT_BODY)
    scope = (
        "IF NEW.tenant_id IS DISTINCT FROM erev.current_tenant_id() OR NOT "
        "coalesce(erev.entity_in_scope(NEW.entity_id), false) THEN RETURN NEW; END IF;"
    )
    assert scope in run and scope in line
    assert (
        "IF TG_OP = 'UPDATE' AND (NEW.state::text <> 'cancelled' OR OLD.state::text = "
        "'cancelled') THEN RETURN NEW; END IF;"
    ) in run
    assert (
        "FROM erev.period_state s WHERE s.tenant_id = NEW.tenant_id AND s.entity_id = "
        "NEW.entity_id AND s.book_code = NEW.book_code AND s.period_id = NEW.period_id FOR SHARE;"
    ) in run
    assert "IF period_state_now IN ('closed', 'permanently_locked') THEN" in run
    assert "EREV-LED-003: period %s of entity %s is %s in book %s, so journal run %s " in run
    assert (
        "FROM erev.journal_batch b WHERE b.tenant_id = NEW.tenant_id AND b.id = "
        "NEW.journal_batch_id FOR SHARE;"
    ) in line
    assert "IF batch_state IS DISTINCT FROM 'draft' THEN" in line
    assert "EREV-JE-003: journal batch %s is %s, so journal line %s cannot join it" in line
    assert "$fn$" not in revision.RUN_PERIOD_GUARD_BODY + revision.LINE_BATCH_DRAFT_BODY


def test_the_named_refusal_reads_the_states_the_guard_reads() -> None:
    """The application refuses by name what the trigger refuses by code: the two closed states of
    E-04 and no other — a ``future`` period is the command's own refusal, not the guard's — and
    the codes have their owners in the problem catalogue (04 §15.2)."""
    assert summarise.CLOSED_STATES == {state.value for state in periods.CLOSED_STATES}
    assert summarise.CLOSED_STATES == {
        PeriodState.CLOSED.value,
        PeriodState.PERMANENTLY_LOCKED.value,
    }
    assert PeriodState.FUTURE.value not in summarise.CLOSED_STATES
    assert "EREV-LED-003" in PROBLEMS["period-closed"].db_codes
    assert "EREV-JE-003" in PROBLEMS["ledger-integrity"].db_codes
    assert PROBLEMS["period-closed"].status == 409
    assert "journal_run" in PERIOD_GUARD_TABLES
    for consequence in (summarise.NOT_CALCULATED, summarise.NOT_CANCELLED):
        sentence = summarise.RUN_PERIOD_CLOSED.format(
            period="Sep 2026", entity="AVM-US", book="ASC606", consequence=consequence
        )
        assert sentence.startswith("Sep 2026 is closed for AVM-US in book ASC606. A journal run ")
    assert summarise.RULE_PERIOD_CLOSED == "RUN_PERIOD_CLOSED"


def _row(document: str, start: str) -> str:
    """The one table row of a governed document that starts with ``start``."""
    lines = (DOCS / document).read_text(encoding="utf-8").splitlines()
    [row] = [line for line in lines if line.startswith(start)]
    return row


def test_the_documents_state_what_a_period_that_takes_no_run_answers() -> None:
    """PRD SM-08 "Run journals" and 04 §16.7 API-S-JournalRunCreate ``period_key`` (PRD rev 1.134;
    04 rev 1.205): the sentence of a ``future`` period — which has no catalogue row, as the
    command's other 422 answers have none — and the sentence of a closed one stand in both rows
    as the code says them; the cancel's sentence stands in 04's ``cancel`` row and in the PRD's
    row of ``draft``, ``approved`` → ``cancelled``."""
    future = commands.FUTURE_PERIOD.format(
        period_key="<period key>", entity="<entity>", book="<book>"
    )
    closed = {
        consequence: summarise.RUN_PERIOD_CLOSED.format(
            period="<period>", entity="<entity>", book="<book>", consequence=consequence
        )
        for consequence in (summarise.NOT_CALCULATED, summarise.NOT_CANCELLED)
    }
    run_journals = _row(
        "02-PRD.md", '| none | none (job `QUEUED` then `RUNNING`; label "Calculating")'
    )
    create = _row("04-DATA_MODEL.md", "| `period_key` | string | R | Rev 1.205")
    assert f'"{future}"' in run_journals and f'"{future}"' in create
    assert "ERR-86" in run_journals and f'"{closed[summarise.NOT_CALCULATED]}"' in create
    cancel = _row("04-DATA_MODEL.md", "| `POST /journal-runs/{id}/cancel` |")
    cancelled = _row("02-PRD.md", "| `draft`, `approved` | `cancelled` | Cancel journal run |")
    assert f'"{closed[summarise.NOT_CANCELLED]}"' in cancel
    assert f'"{closed[summarise.NOT_CANCELLED]}"' in cancelled
    assert "**(d) Not in a closed period**" in cancel
    # the cancel of a run with a failed batch meets the same guard, at the command and in its
    # job (``failed_exits._standing``): the PRD's row of ``failed`` → ``cancelled`` names it too
    failed_cancel = _row("02-PRD.md", "| `failed` | `cancelled` | Cancel journal run |")
    assert "409 `period-closed`, at the command and in the job (ERR-86; rev 1.134)" in failed_cancel


def test_the_sentinel_is_the_first_test_of_the_guards_module() -> None:
    """The supervisor's condition of 2026-10-01 on the acceptance of this item: the first test of
    ``tests/pg/test_journal_guards.py`` asserts that both triggers are enabled before it does
    anything else, so that a trigger left disabled by a test that died is seen. Pure: the
    module's first test is the sentinel, and its body is one assertion that names both guards."""
    module = ast.parse((TESTS / "pg/test_journal_guards.py").read_text(encoding="utf-8"))
    tests = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]
    first = tests[0]
    assert first.name == "test_both_guards_are_enabled_before_anything_else_here_runs"
    body = first.body[1:] if ast.get_docstring(first) else first.body
    assert [type(statement) for statement in body] == [ast.Assert]
    named = {node.id for node in ast.walk(body[0]) if isinstance(node, ast.Name)}
    assert {"RUN_GUARD", "LINE_GUARD", "_enabled"} <= named
