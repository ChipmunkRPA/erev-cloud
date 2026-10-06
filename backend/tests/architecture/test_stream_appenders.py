"""DG-ARC-19: every function that appends to a contract's stream is named with how its
transaction ends (dev-guide rev 1.218; 04 §14.1 "A command recorded before a lock" rev 1.229; PRD
ERR-72; supervisor rulings R-122 (j) and of 2026-10-02; item PIN-WINDOW-APPENDER-1).

An event keeps the stamp of the transaction that records it. A period lock decided after that
stamp froze its datasets without the event, so the transaction must not commit it as if it had
been known at the lock's cutoff: the period pin. The pin stands where a computation is stored
(``computation.persist``) and, for a transaction that stores none, in the tail check
``period_ends.refuse_appends_a_lock_met``. Which of the two an appender reaches is decided when
it is written — the tail check was missing at five places because nobody had asked — so this
test names every function that calls ``events.stream.append_events`` with its ending and reads
the ending from the source:

- ``COMPUTES``: the function computes the group in its own body. A computation that is stored
  meets the pin in ``persist``; one that is deferred, refused or crashed meets the tail check,
  which ``compute_job.defer_compute`` and ``compute_job._refused`` make themselves.
- ``CALLER``: the function appends for a command that computes after it; each named function is
  that command and computes in its own body.
- ``TAIL``: the transaction stores no computation of what was appended; the named function — the
  appender itself, or the function that ends the appender's transaction or savepoint — calls the
  tail check.
- ``DRAFT``: the function acts on a draft, and its transaction ends without the check: nothing of
  a draft is in a frozen dataset or in the ledger, and an activation records events of its own
  (class D of the supervisor's ruling; the tail check itself judges no draft).

A new appender fails until it is named, and a named one fails when its ending is no longer in
its source.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Final

from support.architecture import Finding, callee, imports, iter_files, read, report

RULE: Final = "DG-ARC-19"
PY: Final = frozenset({".py"})
PACKAGE_ROOT: Final = "backend/erev_api"
APPEND: Final = "append_events"
STREAM: Final = "backend/erev_api/events/stream.py"
STREAM_MODULE: Final = "erev_api.events.stream"
TAIL_CHECK: Final = "refuse_appends_a_lock_met"
COMPUTE_JOB: Final = "backend/erev_api/domain/contracts/compute_job.py"
# The calls that compute a combination group, or hand it to the job that does.
COMPUTING: Final = frozenset(
    {
        "compute",
        "compute_group",
        "defer_compute",
        "persist",
        "provisional_compute",
        "recompute",
        "_compute",
        "_recompute_contract",
    }
)
COMPUTES: Final = "COMPUTES"
CALLER: Final = "CALLER"
TAIL: Final = "TAIL"
DRAFT: Final = "DRAFT"
CONTRACTS: Final = "backend/erev_api/domain/contracts/"
IMPORTS: Final = "backend/erev_api/domain/imports/"


@dataclass(frozen=True, slots=True)
class Ending:
    kind: str
    why: str
    # CALLER: the commands that compute after the append; TAIL: the function that asks the tail
    # check when it is not the appender itself. (file, function) pairs.
    where: tuple[tuple[str, str], ...] = ()


# (file, function) → how the transaction of what it appends ends.
APPENDERS: Final[dict[tuple[str, str], Ending]] = {
    ("backend/erev_api/approvals/subjects.py", "_apply_event_submission"): Ending(
        CALLER,
        "an approved manual event is appended, then its group computed as after an append",
        ((CONTRACTS + "events.py", "_approve_submission"),),
    ),
    (CONTRACTS + "activation.py", "activate"): Ending(COMPUTES, "an activation recomputes"),
    (CONTRACTS + "combination.py", "_change"): Ending(
        CALLER,
        "a combination's change of membership, then each group computed or deferred",
        ((CONTRACTS + "combination.py", "apply_combination"),),
    ),
    (CONTRACTS + "commands.py", "book_contract"): Ending(
        DRAFT, "a booking creates a draft; its callers compute it provisionally or leave it"
    ),
    (CONTRACTS + "commands.py", "replace_draft"): Ending(
        COMPUTES, "a draft's replacement computes provisionally"
    ),
    (CONTRACTS + "estimates.py", "_approve_version"): Ending(
        COMPUTES, "an approved estimate version recomputes"
    ),
    (CONTRACTS + "events.py", "record_events"): Ending(
        COMPUTES, "a recorded fact computes its group or defers it beyond the budget"
    ),
    (CONTRACTS + "holds.py", "apply_hold"): Ending(COMPUTES, "unit of work B: compute or defer"),
    (CONTRACTS + "holds.py", "release_hold"): Ending(COMPUTES, "unit of work B: compute or defer"),
    (CONTRACTS + "holds.py", "apply_system_hold"): Ending(
        COMPUTES, "unit of work B: compute or defer"
    ),
    (CONTRACTS + "holds.py", "release_system_holds"): Ending(
        CALLER,
        "a release by the system: for a recorded assessment, and for a reviewed judgement",
        (
            (CONTRACTS + "events.py", "record_events"),
            ("backend/erev_api/domain/policies/judgements.py", "review_judgement"),
        ),
    ),
    (CONTRACTS + "holds.py", "apply_rule_holds"): Ending(
        DRAFT, "the hold rules of a contract at its creation, before any activation"
    ),
    (CONTRACTS + "locks.py", "update_memos"): Ending(COMPUTES, "unit of work B: compute or defer"),
    (CONTRACTS + "modifications.py", "_apply_row"): Ending(
        COMPUTES, "an approved modification computes what it applies"
    ),
    (CONTRACTS + "regroup.py", "regroup"): Ending(COMPUTES, "a regroup recomputes"),
    (CONTRACTS + "void.py", "_approved"): Ending(COMPUTES, "an approved void recomputes"),
    (IMPORTS + "csv_v2/recorded.py", "append"): Ending(
        TAIL,
        "an import of recorded facts computes in its dry run only; its commit asks after its plans",
        ((IMPORTS + "commit.py", "_apply_plans"),),
    ),
    (IMPORTS + "legacy_v1/contract_setup.py", "write_vc_element"): Ending(
        DRAFT, "an estimated element of a contract that is being set up, before its activation"
    ),
    (IMPORTS + "legacy_v1/contract_setup.py", "_prepare_records"): Ending(
        DRAFT, "the records of a contract that is being set up, before its activation"
    ),
    (IMPORTS + "legacy_v1/modification.py", "apply"): Ending(
        COMPUTES, "a legacy modification computes its contract's group in the commit"
    ),
    (IMPORTS + "legacy_v1/progress.py", "apply"): Ending(
        COMPUTES, "a legacy progress row computes its contract's group in the commit"
    ),
    ("backend/erev_api/domain/integrations/documents.py", "append_document"): Ending(
        TAIL,
        "an adapter's invoice or credit note; the run asks inside the document's savepoint, and "
        "a refusal ends the run's transaction, which its job applies once more",
        (("backend/erev_api/domain/integrations/sync.py", "ingest_document"),),
    ),
    ("backend/erev_api/domain/journals/adjustments.py", "_approved"): Ending(
        COMPUTES, "an approved manual adjustment recomputes"
    ),
    ("backend/erev_api/domain/migration/capture.py", "apply"): Ending(
        COMPUTES, "a migration capture persists the computation it carries"
    ),
    ("backend/erev_api/domain/policies/overrides.py", "_apply_ssp_override"): Ending(
        TAIL, "an approved SSP override appends its line attributes and computes nothing"
    ),
}
# Where a computation is not stored, the tail check is made by the computation's own module.
WITHOUT_A_VERSION: Final = ((COMPUTE_JOB, "defer_compute"), (COMPUTE_JOB, "_refused"))


def _functions(source: str) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef)
    }


def _calls(function: ast.AST) -> set[str]:
    found = {callee(node) for node in ast.walk(function) if isinstance(node, ast.Call)}
    return {name for name in found if name is not None}


def appenders(sources: dict[str, str]) -> set[tuple[str, str]]:
    """Every (file, function) whose body calls the STREAM's ``append_events``: the name, in a
    module that imports it from ``erev_api.events.stream`` — at its top or inside a function. The
    audit chain has an ``append_events`` of its own, which records no contract event."""
    found: set[tuple[str, str]] = set()
    for path, source in sources.items():
        if path == STREAM or APPEND not in source:
            continue
        from_the_stream = any(
            item.module == STREAM_MODULE and APPEND in item.names
            for item in imports(path, ast.parse(source))
        )
        if not from_the_stream:
            continue
        for name, function in _functions(source).items():
            if APPEND in _calls(function):
                found.add((path, name))
    return found


def check(sources: dict[str, str], listed: dict[tuple[str, str], Ending]) -> list[Finding]:
    findings: list[Finding] = []

    def body_calls(where: tuple[str, str], names: frozenset[str]) -> bool:
        path, name = where
        function = _functions(sources.get(path, "")).get(name)
        return function is not None and bool(_calls(function) & names)

    def line(where: tuple[str, str]) -> int:
        function = _functions(sources.get(where[0], "")).get(where[1])
        return 1 if function is None else function.lineno

    found = appenders(sources)
    for where in sorted(found - set(listed)):
        findings.append(
            Finding(
                where[0],
                line(where),
                RULE,
                f"{where[1]} appends to a contract's stream and is not named with its ending",
            )
        )
    for where in sorted(set(listed) - found):
        findings.append(Finding(where[0], 1, RULE, f"{where[1]} is named and appends to no stream"))
    tail = frozenset({TAIL_CHECK})
    for where, ending in sorted(listed.items()):
        if where not in found:
            continue
        if ending.kind == COMPUTES and not body_calls(where, COMPUTING):
            findings.append(
                Finding(
                    where[0],
                    line(where),
                    RULE,
                    f"{where[1]} is named COMPUTES and computes nothing",
                )
            )
        if ending.kind == CALLER:
            if not ending.where:
                findings.append(
                    Finding(
                        where[0], line(where), RULE, f"{where[1]} is named CALLER and names none"
                    )
                )
            for caller in ending.where:
                if not body_calls(caller, COMPUTING):
                    findings.append(
                        Finding(
                            caller[0],
                            line(caller),
                            RULE,
                            f"{caller[1]} computes for {where[1]} by the list and computes nothing",
                        )
                    )
        if ending.kind == TAIL:
            for asker in ending.where or (where,):
                if not body_calls(asker, tail):
                    findings.append(
                        Finding(
                            asker[0],
                            line(asker),
                            RULE,
                            f"{asker[1]} ends the transaction of {where[1]} without {TAIL_CHECK}",
                        )
                    )
        if ending.kind not in (COMPUTES, CALLER, TAIL, DRAFT):
            findings.append(Finding(where[0], line(where), RULE, f"{where[1]}: no such ending"))
    for where in WITHOUT_A_VERSION:
        if not body_calls(where, tail):
            findings.append(
                Finding(
                    where[0], line(where), RULE, f"{where[1]} stores no version and asks nothing"
                )
            )
    return findings


def _sources() -> dict[str, str]:
    return {path: read(path) for path in iter_files(PACKAGE_ROOT, suffixes=PY)}


def test_dg_arc_19_every_appender_is_named_with_how_its_transaction_ends() -> None:
    findings = check(_sources(), APPENDERS)
    assert not findings, report(findings)


def test_the_list_names_each_ending_at_least_once() -> None:
    """The four endings are in use: a list of one kind would mean the door reads nothing."""
    assert {ending.kind for ending in APPENDERS.values()} == {COMPUTES, CALLER, TAIL, DRAFT}


APPENDER: Final = """
from erev_api.events.stream import append_events


def record(uow, contract_id, events):
    append_events(uow, contract_id=contract_id, events=events)
"""
COMPUTING_APPENDER: Final = APPENDER + "    compute_group(uow, contract_id)\n"
ASKING_APPENDER: Final = (
    APPENDER + "    period_ends.refuse_appends_a_lock_met(uow, [contract_id])\n"
)
VERSIONLESS: Final = """
def defer_compute(uow, group_id):
    period_ends.refuse_appends_a_lock_met(uow, [group_id])


def _refused(uow, group_id):
    period_ends.refuse_appends_a_lock_met(uow, [group_id])
"""
NEW: Final = ("backend/erev_api/domain/new.py", "record")


def _rules(sources: dict[str, str], listed: dict[tuple[str, str], Ending]) -> list[str]:
    return [finding.message for finding in check({COMPUTE_JOB: VERSIONLESS, **sources}, listed)]


def test_an_appender_nobody_named_is_found() -> None:
    assert _rules({NEW[0]: APPENDER}, {}) == [
        "record appends to a contract's stream and is not named with its ending"
    ]
    assert _rules({NEW[0]: APPENDER}, {NEW: Ending(DRAFT, "a draft")}) == []
    # Imported inside the function, as the packages that the contract commands reach do it.
    inside = (
        "def record(uow, contract_id, events):\n"
        "    from erev_api.events.stream import append_events\n\n"
        "    append_events(uow, contract_id=contract_id, events=events)\n"
    )
    assert len(_rules({NEW[0]: inside}, {})) == 1
    # The audit chain's function of the same name records no contract event.
    chain = APPENDER.replace("erev_api.events.stream", "erev_api.audit.chain")
    assert _rules({NEW[0]: chain}, {}) == []


def test_an_ending_that_left_the_source_is_found() -> None:
    computes = {NEW: Ending(COMPUTES, "computes")}
    assert _rules({NEW[0]: APPENDER}, computes) == ["record is named COMPUTES and computes nothing"]
    assert _rules({NEW[0]: COMPUTING_APPENDER}, computes) == []
    asks = {NEW: Ending(TAIL, "asks at its end")}
    assert _rules({NEW[0]: APPENDER}, asks) == [
        "record ends the transaction of record without refuse_appends_a_lock_met"
    ]
    assert _rules({NEW[0]: ASKING_APPENDER}, asks) == []
    other = ("backend/erev_api/domain/other.py", "command")
    for_a_caller = {NEW: Ending(CALLER, "its command computes", (other,))}
    silent = {NEW[0]: APPENDER, other[0]: "def command(uow):\n    record(uow, 1, [])\n"}
    assert _rules(silent, for_a_caller) == [
        "command computes for record by the list and computes nothing"
    ]
    computing = {**silent, other[0]: silent[other[0]] + "    recompute(uow, 1)\n"}
    assert _rules(computing, for_a_caller) == []
    assert _rules({}, {NEW: Ending(DRAFT, "gone")}) == ["record is named and appends to no stream"]


def test_a_computation_without_a_version_that_asks_nothing_is_found() -> None:
    silent = VERSIONLESS.replace(
        "def _refused(uow, group_id):\n    period_ends.refuse_appends_a_lock_met(uow, [group_id])",
        "def _refused(uow, group_id):\n    return None",
    )
    assert [finding.message for finding in check({COMPUTE_JOB: silent}, {})] == [
        "_refused stores no version and asks nothing"
    ]
