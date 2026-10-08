"""The period's own lock request as pure rules (item CLO-LOCK-REQUEST-OWN-GATE-1; 04 §16.8
``blockers`` rev 1.311; PRD BR-CLS-01 rev 1.205; found by lane WEB-QA, row C-10, and measured
through the API on 2026-10-02). CPU-only: ``blockers.approvals_pending`` leaves out the ``PENDING``
``PERIOD_LOCK`` request whose subject is the period state asked. The predicate is the type AND
the subject; it stands once, in the one statement every reader of the count goes through; and
the governed rows say so. Until then the request counted itself: between "Submit for lock" and
the decision the gate read ``FAILED`` "Pending approvals: 1" and the cockpit called the lock
unavailable. The database witnesses are ``tests/api/test_lock_api.py`` and
``tests/domain/close/test_gates.py``.

The same count leaves out a second request (item CLO-APPROVALS-WAIVER-OWN-REQUEST-1; 04 §16.8
``blockers`` rev 1.318; PRD BR-CLS-01 rev 1.206; measured on 2026-10-03): the ``PENDING``
``EXCEPTION_WAIVER`` request whose subject is the period's own ``APPROVALS_CLEARED`` item. A
waiver's request states the count it asks to waive, and this gate's waiver changed that count by
being asked: after any read of the cockpit its approval answered 409 ``stale-approval``.
"""

from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path
from typing import Any, Final
from uuid import UUID

import erev_api
from erev_api.approvals import subjects
from erev_api.domain.close import gates
from erev_api.enums import ApprovalSubjectType
from sqlalchemy.dialects import postgresql

DOCS: Final = Path(__file__).resolve().parents[4] / "docs"
PACKAGE: Final = Path(erev_api.__file__).resolve().parent
ENTITY, PERIOD, STATE = UUID(int=1), UUID(int=2), UUID(int=7)


def _scope(state: str = "closing") -> gates.PeriodScope:
    return gates.PeriodScope(
        state_id=STATE,
        entity_id=ENTITY,
        entity_code="AVM-US",
        functional_currency="USD",
        book_code="ASC606",
        period_id=PERIOD,
        period_key="FY2026-P09",
        period_name="Sep 2026",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        state=state,
        current_lock_id=None,
        row_version=1,
    )


def _sql(clause: Any) -> str:
    """The clause as PostgreSQL would read it, every value written out."""
    compiled = clause.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
    return " ".join(str(compiled).replace("erev.", "").split())


def _counts(text: str, labels: list[str]) -> dict[str, str]:
    """The select list of the one row, cut into the expression of each labelled count."""
    cut: dict[str, str] = {}
    start = 0
    for label in labels:
        end = text.index(f" AS {label}", start)
        cut[label] = text[start:end]
        start = end + len(f" AS {label}")
    return cut


def test_the_own_lock_request_is_named_by_its_type_and_its_subject() -> None:
    """``gates.own_lock_request``: ``PERIOD_LOCK`` on the period state asked — both together. By
    the subject alone a reopen request of the period would be left out as well; by the type
    alone the lock request of every other period state of the entity. One subject type serves
    the lock request of a period in soft close and the permanent-lock request of a closed one,
    so the predicate names both and asks no state."""
    for state in ("closing", "closed"):
        assert _sql(gates.own_lock_request(_scope(state))) == (
            "approval_request.subject_type = 'PERIOD_LOCK' "
            f"AND approval_request.subject_id = '{STATE}'"
        )
    assert subjects.LOCK_FROM_STATE == {"closing": "LOCK", "closed": "PERMANENT_LOCK"}
    assert ApprovalSubjectType.PERIOD_REOPEN is not ApprovalSubjectType.PERIOD_LOCK


def test_the_count_of_pending_approvals_leaves_it_out_and_no_other_count_reads_a_request() -> None:
    """The one row of ``gates.blocker_statement``: ``approvals_pending`` counts the ``PENDING``
    requests of the entity and not the period's own lock request — the predicate negated, once
    — and no other count of the row reads a request, so nothing else of the row can count it
    back in."""
    scope = _scope()
    statement = gates.blocker_statement(scope)
    labels = [column.name for column in statement.selected_columns]
    assert set(gates.BLOCKER_KEYS) <= set(labels)
    counts = _counts(_sql(statement), labels)
    approvals = counts["approvals_pending"]
    own = _sql(gates.own_lock_request(scope))
    assert approvals.count(f"AND NOT ({own})") == 1
    assert approvals.count("approval_request.status = 'PENDING'") == 1
    assert _sql(statement).count(own) == 1
    # rev 1.318: nor the request that asks to waive this very count
    waiver = _sql(gates.own_gate_waiver_request(scope))
    assert approvals.count(f"AND NOT ({waiver})") == 1
    assert _sql(statement).count(waiver) == 1
    reading = [label for label, text in counts.items() if "approval_request" in text]
    assert reading == ["approvals_pending"]


def test_every_reader_of_the_count_goes_through_the_one_statement() -> None:
    """One definition for every reader. The period read and the home's close panel
    (``blocker_counts``) and every evaluation of the gates (``signals`` to ``gate_results``)
    share ``_blocker_populations``; counts and member identities use the same predicates.
    ``request_of_entity`` has three more readers, and they keep the lock request: the cockpit's
    ``pending_requests``,
    which asks two other types; the approvals list's entity filter and the home's
    ``pending_approvals`` — there the lock request is a request someone has to decide."""
    assert "blocker_statement(scope)" in inspect.getsource(gates._counts_row)
    assert "_counts_row(session, scope)" in inspect.getsource(gates.blocker_counts)
    assert "_population_members(session, scope, known_at=known_at)" in inspect.getsource(
        gates.signals
    )
    for reader in (gates.blocker_statement, gates._population_members):
        assert "_blocker_populations(scope)" in inspect.getsource(reader), reader.__name__
    assert 'blockers["approvals_pending"]' in inspect.getsource(gates.gate_results)
    assert inspect.getsource(gates).count("own_lock_request(scope)") == 1
    assert inspect.getsource(gates).count("own_gate_waiver_request(scope)") == 1
    readers = sorted(
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.rglob("*.py")
        if "request_of_entity(" in path.read_text(encoding="utf-8")
    )
    assert readers == [
        "domain/close/gates.py",
        "domain/platform/approval_queries.py",
        "domain/reports/dashboard.py",
    ]
    assert inspect.getsource(gates).count("request_of_entity(scope.entity_id)") == 2
    assert "request_of_entity(scope.entity_id)" in inspect.getsource(gates.pending_request_counts)
    assert ApprovalSubjectType.PERIOD_LOCK not in gates.BLOCKER_REQUEST_TYPES


def test_the_approvals_gates_own_waiver_request_is_named_by_type_subject_and_gate() -> None:
    """``gates.own_gate_waiver_request`` (item CLO-APPROVALS-WAIVER-OWN-REQUEST-1; 04 §16.8
    ``blockers`` rev 1.318): ``EXCEPTION_WAIVER`` on the checklist item of the period asked —
    its entity, book and period — whose template is the gate ``APPROVALS_CLEARED``. By the type
    alone every waiver request would be left out; by the period's items alone, the waiver
    request of every other gate of the period; without the period, the waiver request of
    another period's approvals gate. The request that asks to waive the count is no part of the
    count, and no other request is."""
    text = _sql(gates.own_gate_waiver_request(_scope()))
    kind, subject = text.split(" AND approval_request.subject_id IN (", 1)
    assert kind == "approval_request.subject_type = 'EXCEPTION_WAIVER'"
    assert subject.endswith(")")
    items, conditions = subject[:-1].split(" WHERE ", 1)
    assert items == (
        "SELECT close_checklist_item.id FROM close_checklist_item "
        "JOIN close_checklist_template "
        "ON close_checklist_template.tenant_id = close_checklist_item.tenant_id "
        "AND close_checklist_template.id = close_checklist_item.close_checklist_template_id"
    )
    assert conditions.split(" AND ") == [
        "close_checklist_item.entity_id = " + repr(str(ENTITY)),
        "close_checklist_item.book_code = 'ASC606'",
        "close_checklist_item.period_id = " + repr(str(PERIOD)),
        "close_checklist_template.gate_check_code = 'APPROVALS_CLEARED'",
    ]
    assert gates.APPROVALS_CLEARED not in gates.NEVER_WAIVABLE  # the product offers the waiver


def test_the_rows_state_the_rule() -> None:
    """04 rev 1.311 and rev 1.318 state the count in §16.8 ``blockers``, what the gate reads in
    T-CLS-02 and what the item's trail and its waiver hold in T-CLS-03; the member's row of
    §16.7 holds the sentence owed from register index 265; PRD BR-CLS-01 has its clauses of rev
    1.205 and rev 1.206; and fragment 14 rev 1.86 and rev 1.90 name the witnesses, every rule
    of this module among them."""
    model = (DOCS / "04-DATA_MODEL.md").read_text(encoding="utf-8")
    for sentence in (
        "`approvals_pending` counts the `PENDING` approval requests of the entity — entity-only, "
        "not filtered by book — other than the period's own lock request: the `PERIOD_LOCK` "
        "request whose subject is this period state",
        "Counted as before: a request of another period state of the entity — another period's "
        "or another book's — and every `PERIOD_REOPEN` request, the period's own included: "
        "while a reopen request waits for its approvers no `closing` period of the entity moves "
        "to `closed`",
        "`APPROVALS_CLEARED` reads `blockers.approvals_pending` (§16.8) — the `PENDING` approval "
        "requests of the entity other than the period's own lock request.",
        "a read stores nothing, and the item's trail holds what the commands wrote and no "
        "`FAILED` of the request's own making",
        "A period whose `APPROVALS_CLEARED` item stood `WAIVED` did not meet the case — a final "
        "item is not evaluated again — and the rule removes it for a waiver that covers a count "
        "as well.",
        "on every read, also at `known_at` or `as_of`, `journal_run_id` names the run that "
        "journalises the line at the time of the read — the member is a pointer for the drill, "
        "not a figure of the as-known ledger",
        # rev 1.318, item CLO-APPROVALS-WAIVER-OWN-REQUEST-1
        "`approvals_pending` also leaves out the request that asks to waive this count: the "
        "`PENDING` `EXCEPTION_WAIVER` request whose subject is the period's own "
        "`APPROVALS_CLEARED` item",
        "The waiver request of another gate's item of the period, of another period's "
        "`APPROVALS_CLEARED` item and of an exception item is counted as before.",
        "Rev 1.318: nor does the count hold the request that asks to waive this gate.",
        "the count a waiver of `APPROVALS_CLEARED` states and covers is the other requests "
        "alone, before and after it is asked",
    ):
        assert model.count(sentence) == 1, sentence
    prd = (DOCS / "02-PRD.md").read_text(encoding="utf-8")
    assert (
        prd.count(
            "pending approvals affecting the period 0 (rev 1.205: the period's own lock request "
            "is not one — it asks for the lock, and J-13.14 decides it on the cockpit; 04 §16.8 "
            "`blockers` rev 1.311);"
        )
        == 1
    )
    assert (
        prd.count(
            "nor is the request that asks to waive the pending-approvals gate a pending "
            "approval affecting the period — the request that asks to waive the count is no "
            "part of the count (04 §16.8 `blockers` rev 1.318)."
        )
        == 1
    )
    fragment = (DOCS / "build-spec/14-close-reports-ai-demo-release.md").read_text(encoding="utf-8")
    for witness in (
        "`backend/tests/domain/close/test_gates.py::test_the_periods_own_lock_request_is_no_"
        "pending_approval_of_it`",
        "`backend/tests/api/test_lock_api.py::test_the_lock_request_holds_no_gate_of_its_own_"
        "period`",
        "`::test_another_pending_request_holds_the_lock_after_the_submission`",
        "`backend/tests/unit/close/test_own_lock_request_rules.py::",
        # rev 1.90
        "`backend/tests/api/test_lock_api.py::test_the_waiver_of_the_approvals_gate_is_no_"
        "pending_approval_of_its_period`",
        "`::test_a_waived_approvals_gate_is_not_outgrown_by_the_periods_own_lock_request`",
        "`backend/tests/domain/close/test_gates.py::test_the_approvals_gates_own_waiver_request_"
        "is_no_pending_approval_of_its_period`",
    ):
        assert fragment.count(witness) == 1, witness
    rules = sorted(name for name in globals() if name.startswith("test_"))
    assert len(rules) == 5
    assert all(fragment.count(f"::{name}`") == 1 for name in rules), rules
