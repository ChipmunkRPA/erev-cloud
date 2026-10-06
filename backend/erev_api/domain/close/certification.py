"""CLO-6 lock gate outcomes as pure functions (BUILD_SPEC CLO-6; REQ-CLS-009; PRD BR-CLS-01, ERR-14;
04 T-CLS-04 ``certification``; BS4-D-08; SCREENS_B §1.1 gate labels).

The DB-bound producers (``gates.evaluate_gates``, the ``request_lock`` command and the
``PERIOD_LOCK`` approval handler of CLO-6) hand their ``GateResult`` rows to this module, which
decides:

- the canonical population (``canonical``, F-CLO-R1): every decision first checks that the
  results hold exactly the fourteen gates provisioning seeds (``SYSTEM_CLOSE_GATES``), once each
  and no other, and raises ``ValueError`` otherwise, so an empty, partial, duplicated or unknown
  gate set never allows a lock;
- which gates fail a lock request (``failing``): every gate that is not cleared, other than
  ``CONTROLLER_CERTIFIED``, which passes only when the Controller's approval executes the lock
  (BR-CLS-01, BR-CLS-02). A gate is cleared when it is ``PASSED``, or when its checklist item is
  ``WAIVED`` through an approved waiver or ``NOT_APPLICABLE`` — except the gates that are never
  waivable (``gates.NEVER_WAIVABLE``), which only ``PASSED`` clears (SC-N4; supervisor ruling
  R-55 (b), (c); D-88 L7-2-Q-16; 04 §16.8 rev 1.106);
- the tenant close tasks that hold the lock beside the gates (``blocking_tasks``; R-55 (a); PRD
  BR-CLS-01 "custom close tasks signed"): ``lock_allowed`` is False while one is unsigned;
- the ERR-14 refusal (``refusal``): 409 ``close-gates-failed`` with ``detail`` "<n> close gates
  have not passed: <gate labels>." and one ``errors[]`` entry per failing gate whose ``rule_id``
  is the gate check code and whose ``message`` is the gate detail (BS4-D-08; SCREENS_B :400),
  then one per unsigned blocking task whose ``rule_id`` is the task's template code and whose
  ``message`` is "Close task not signed: <name>";
- the certification at lock (``certify``): ``CONTROLLER_CERTIFIED`` becomes ``PASSED`` once every
  other gate is cleared; and the T-CLS-04 ``certification`` document (``certification``): every
  gate result in T-CLS-02 order as ``{gate_check_code, status, count, evaluated_at}``, a waived
  gate with ``waiver_approval_request_id`` and ``waived_count`` as well, and a result a sandbox
  load's replay took from the source lock with ``replayed`` true (item CLO-GATE-RUN-1).

Nothing here reads a session; the unit tests in ``tests/unit/close/test_certification.py`` are
the contract (F-CLO preparation record ``docs/reviews/loop/prod/F-CLO-prep.md`` §3, §5).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Final

from erev_api.domain.close import gates
from erev_api.domain.platform.provisioning import SYSTEM_CLOSE_GATES
from erev_api.enums import ChecklistStatus
from erev_api.problems import Problem, ProblemError

# The canonical gate population: the fourteen T-CLS-02 system gates provisioning seeds, in their
# order, with the SCREENS_B §1.1 labels (F-CLO-R1: one validator before every lock or certify
# decision).
CANONICAL_GATES: Final[tuple[str, ...]] = tuple(code for code, _ in SYSTEM_CLOSE_GATES)
GATE_LABELS: Final[Mapping[str, str]] = dict(SYSTEM_CLOSE_GATES)
NOT_CANONICAL: Final = (
    "a lock decision needs each of the fourteen gate results exactly once: {problem}"
)
GATES_FAILED_SLUG: Final = "close-gates-failed"  # 04 §15.2; PRD ERR-14
GATES_FAILED_DETAIL: Final = "{n} close gates have not passed: {gates}."  # ERR-14, verbatim
GATE_SEPARATOR: Final = ", "


@dataclass(frozen=True, slots=True)
class Refusal:
    """A command refusal before any write: the problem slug, ``detail``, the rule that refused, the
    §14.1 code where one exists and the ``errors[]`` entries (04 §15.2)."""

    slug: str
    detail: str
    rule_id: str | None = None
    code: str | None = None
    errors: tuple[ProblemError, ...] = ()

    def problem(self) -> Problem:
        return Problem(self.slug, self.detail, errors=self.errors, code=self.code)


def canonical(results: Sequence[gates.GateResult]) -> tuple[gates.GateResult, ...]:
    """The results in T-CLS-02 order once they hold exactly the fourteen canonical gates;
    ``ValueError`` naming the defect (empty, unknown, duplicate or missing gate) otherwise. Every
    lock and certify decision below passes through here, so a malformed population never allows a
    lock (F-CLO-R1)."""
    codes = [result.gate_check_code for result in results]
    if not codes:
        raise ValueError(NOT_CANONICAL.format(problem="no gate results"))
    seen = set(codes)
    unknown = sorted(seen - set(CANONICAL_GATES))
    if unknown:
        raise ValueError(NOT_CANONICAL.format(problem=f"unknown gate {', '.join(unknown)}"))
    if len(codes) != len(seen):
        duplicates = sorted(code for code in seen if codes.count(code) > 1)
        raise ValueError(NOT_CANONICAL.format(problem=f"duplicate gate {', '.join(duplicates)}"))
    missing = [code for code in CANONICAL_GATES if code not in seen]
    if missing:
        raise ValueError(NOT_CANONICAL.format(problem=f"missing gate {', '.join(missing)}"))
    by_code = {result.gate_check_code: result for result in results}
    return tuple(by_code[code] for code in CANONICAL_GATES)


def cleared(result: gates.GateResult) -> bool:
    """Whether a gate no longer holds the lock (R-55 (b), (c)): ``PASSED``; or ``WAIVED`` /
    ``NOT_APPLICABLE`` — the state of its checklist item, laid over the computed result by
    ``gates.with_final_items`` — unless the gate is never waivable, which only ``PASSED`` clears."""
    if result.status is ChecklistStatus.PASSED:
        return True
    return (
        result.status in gates.CLEARED_STATUSES
        and result.gate_check_code not in gates.NEVER_WAIVABLE
    )


def failing(
    results: Sequence[gates.GateResult], *, at_request: bool
) -> tuple[gates.GateResult, ...]:
    """The gates that are not cleared, in T-CLS-02 order, from a canonical population. At request
    time ``CONTROLLER_CERTIFIED`` is left out: it passes only when the lock executes (BR-CLS-01)."""
    return tuple(
        result
        for result in canonical(results)
        if not cleared(result)
        and not (at_request and result.gate_check_code == gates.CONTROLLER_CERTIFIED)
    )


def blocking_tasks(results: Sequence[gates.GateResult]) -> tuple[gates.BlockingTask, ...]:
    """The tenant close tasks that hold the lock, as ``gates.evaluate_gates`` found them beside
    the results (``gates.GateResults.blocking_tasks``; R-55 (a)). A plain sequence of results —
    the pure rule's own callers — carries none."""
    return tuple(getattr(results, "blocking_tasks", ()))


def lock_allowed(results: Sequence[gates.GateResult]) -> bool:
    """True when every gate of the canonical population (``SYSTEM_CLOSE_GATES``) other than
    ``CONTROLLER_CERTIFIED`` is cleared and no blocking close task is unsigned (REQ-CLS-009; PRD
    BR-CLS-01); ``ValueError`` for a malformed population (F-CLO-R1), never True."""
    return not failing(results, at_request=True) and not blocking_tasks(results)


def refusal(
    results: Sequence[gates.GateResult], *, labels: Mapping[str, str] = GATE_LABELS
) -> Refusal:
    """The ERR-14 refusal for a lock request: the failing gates, then the unsigned blocking close
    tasks (``rule_id`` = the task's template code; 04 §16.8 rev 1.106), all counted in ERR-14's
    number; ``ValueError`` when nothing fails."""
    failed = failing(results, at_request=True)
    tasks = blocking_tasks(results)
    if not failed and not tasks:
        raise ValueError("every gate is cleared and every blocking task signed; nothing to refuse")
    names = [labels.get(result.gate_check_code, result.gate_check_code) for result in failed]
    errors = tuple(
        ProblemError(
            rule_id=result.gate_check_code,
            message=result.detail if result.detail else name,
        )
        for result, name in zip(failed, names, strict=True)
    ) + tuple(ProblemError(rule_id=task.code, message=task.message) for task in tasks)
    names += [task.name for task in tasks]
    detail = GATES_FAILED_DETAIL.format(n=len(names), gates=GATE_SEPARATOR.join(names))
    return Refusal(GATES_FAILED_SLUG, detail, errors=errors)


def certify(results: Sequence[gates.GateResult], *, at: datetime) -> tuple[gates.GateResult, ...]:
    """The canonical results with ``CONTROLLER_CERTIFIED`` ``PASSED`` at ``at`` (the lock
    execution); every other result unchanged — a waived gate stays ``WAIVED`` with its request
    and counts. ``ValueError`` names the first gate that still fails, or the first blocking close
    task that is unsigned."""
    ordered = canonical(results)
    failed = failing(ordered, at_request=True)
    if failed:
        raise ValueError(
            f"gate {failed[0].gate_check_code} has not passed; the lock cannot certify"
        )
    tasks = blocking_tasks(results)
    if tasks:
        raise ValueError(f"close task {tasks[0].code} is not signed; the lock cannot certify")
    return tuple(
        replace(result, status=ChecklistStatus.PASSED, count=0, detail=None, evaluated_at=at)
        if result.gate_check_code == gates.CONTROLLER_CERTIFIED
        else result
        for result in ordered
    )


def certification(results: Sequence[gates.GateResult]) -> list[dict[str, Any]]:
    """T-CLS-04 ``certification``: ``[{gate_check_code, status, count, evaluated_at}]`` for exactly
    the canonical gate check codes, in T-CLS-02 order. A waived gate (R-55 (b)) also carries
    ``waiver_approval_request_id`` and ``waived_count``: ``count`` is what the gate computed at the
    decision, ``waived_count`` what its item held when the waiver was approved. A result the
    replay of a source lock laid over the sandbox's evaluation carries ``replayed`` true."""
    rows: list[dict[str, Any]] = []
    for result in canonical(results):
        row: dict[str, Any] = {
            "gate_check_code": result.gate_check_code,
            "status": result.status.value,
            "count": result.count,
            "evaluated_at": result.evaluated_at.isoformat(),
        }
        if result.status is ChecklistStatus.WAIVED:
            row["waiver_approval_request_id"] = (
                None
                if result.waiver_approval_request_id is None
                else str(result.waiver_approval_request_id)
            )
            row["waived_count"] = result.waived_count
        if result.replayed:
            row["replayed"] = True
        rows.append(row)
    return rows
