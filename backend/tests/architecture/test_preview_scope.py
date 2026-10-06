"""DG-KRN-APR-07: a preview is asked by who could submit the subject, and every preview asks (04
§16.10 rev 1.295 "Who may ask for a preview"; dev-guide rev 1.279; supervisor ruling R-103 (b) (5);
item CTR-PREVIEW-GROUP-SCOPE-1).

A dry run reads its combination group whole, and the summary it answers holds figures of the
whole group. A command that defers one therefore asks the approvals kernel first whether the
caller's own entity scope covers every entity the subject is bound to. That is a property of each
such command, so this test holds it by reading the source — a further preview cannot be added
without the question:

1. Every deferral of ``JobKind.CONTRACT_COMPUTE`` in the product — a call of ``defer``,
   ``defer_single`` or ``run_inline`` — is listed here once: a PREVIEW, with the mode it defers
   and the question it asks; a COMPUTATION, with its reason; or the SEED that plays a preview
   inline. A deferral that is not listed fails, and so does a listed one that is gone.
2. A preview's function calls its question BEFORE it defers.
3. A deferral that names a ``mode`` is a preview; a computation names none, also where its
   parameters are built in a variable.
4. The modes the job answers (``compute_job.contract_compute``) are exactly the modes the
   previews defer: a mode the job learns is a preview until it is classified here.
5. The answer of a job knows every preview (04 API-S-Job rev 1.314; item
   PREVIEW-JOB-RESULT-SCOPE-1): the table by which ``jobs.job_outs`` answers the summary of a dry
   run (``jobs.SUMMARY_SUBJECTS``) names the literal of each mode the previews defer and no
   other, and for each a member of the parameters that preview's function defers. The table
   spells the modes and the members itself — the modules that defer import ``jobs`` — so a
   renamed mode or parameter, and a preview without its reader's rule, fail here and nowhere
   else before a summary is answered to nobody.

The defect it guards against (measured on main a101c4c0): in a combination group of a contract of
AVM-UK and one of AVM-US, the four preview routes answered a Revenue Accountant of AVM-UK alone
202, and the summary of her job held the group's transaction price and the journal lines of both
entities.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from support.architecture import Finding, callee, iter_files, read, report

RULE: Final = "DG-KRN-APR-07"
PY: Final = frozenset({".py"})
PRODUCT: Final = "backend/erev_api"
COMPUTE_JOB: Final = "backend/erev_api/domain/contracts/compute_job.py"
EVENTS: Final = "backend/erev_api/domain/contracts/events.py"
MODIFICATIONS: Final = "backend/erev_api/domain/contracts/modifications.py"
ESTIMATES: Final = "backend/erev_api/domain/contracts/estimates.py"
ADJUSTMENTS: Final = "backend/erev_api/domain/journals/adjustments.py"
EXCEPTIONS: Final = "backend/erev_api/domain/imports/exceptions.py"
CLOSE_RUNS: Final = "backend/erev_api/domain/close/close_runs.py"
VOLUME: Final = "backend/erev_api/domain/demo/volume.py"
JOBS: Final = "backend/erev_api/domain/platform/jobs.py"
TABLE: Final = "SUMMARY_SUBJECTS"  # mode literal → (subject type, the params member naming it)
KIND: Final = ("JobKind", "CONTRACT_COMPUTE")
DEFERRALS: Final = frozenset({"defer", "defer_single", "run_inline"})
STORED: Final = "require_preview_scope"  # the preview of a stored subject
PENDING: Final = "require_contract_preview_scope"  # pending events: the set of their contract
QUESTIONS: Final = frozenset({STORED, PENDING})
# (file, function) → (the mode it defers, the question it asks first).
PREVIEWS: Final = {
    (EVENTS, "request_preview"): ("PREVIEW_MODE", PENDING),
    (MODIFICATIONS, "request_preview"): ("MODIFICATION_PREVIEW_MODE", STORED),
    (ESTIMATES, "request_preview"): ("ESTIMATE_PREVIEW_MODE", STORED),
    (ADJUSTMENTS, "preview"): ("ADJUSTMENT_PREVIEW_MODE", STORED),
}
# (file, function) → why it is no preview: it answers no summary to the caller.
COMPUTATIONS: Final = {
    (COMPUTE_JOB, "defer_compute"): (
        "the computation of a group a command left dirty: stored figures, read under each "
        "reader's own scope"
    ),
    (EXCEPTIONS, "request_reprocess"): (
        "the computation of a group whose exception item is resolved: stored figures"
    ),
    (CLOSE_RUNS, "_recompute_dirty"): (
        "the dirty groups of a close run, computed by its child jobs: stored figures"
    ),
}
# (file, function) → (the mode it plays, why it asks nothing).
SEEDS: Final = {
    (VOLUME, "_apply_modification"): (
        "MODIFICATION_PREVIEW_MODE",
        "the volume seed plays the preview of its own draft inline, through no route: no job "
        "row is left and no summary is answered to anybody",
    ),
}
GONE: Final = "is listed and defers nothing"


@dataclass(frozen=True, slots=True)
class Deferral:
    path: str
    function: str
    line: int
    mode: str | None  # the name the ``mode`` member is given, in a literal or by assignment
    asked: tuple[tuple[str, int], ...]  # the questions the function calls, with their lines


def _functions(tree: ast.AST) -> Iterator[tuple[str, ast.AST]]:
    """Every function of a module with its qualified name (``Class.method`` for a method)."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node.name, node
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield f"{node.name}.{item.name}", item


def _is_kind(node: ast.expr | None) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == KIND[1]
        and isinstance(node.value, ast.Name)
        and node.value.id == KIND[0]
    )


def _mode_of(function: ast.AST, call: ast.Call) -> str | None:
    """The name of the mode a deferral states: in the literal it passes, or anywhere in its
    function when the parameters are built in a variable (a ``"mode"`` key, or an assignment to
    ``params["mode"]``)."""
    params = call.args[1] if len(call.args) > 1 else None
    if isinstance(params, ast.Dict):
        for key, value in zip(params.keys, params.values, strict=True):
            if isinstance(key, ast.Constant) and key.value == "mode":
                return ast.unparse(value)
        return None
    for node in ast.walk(function):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if isinstance(key, ast.Constant) and key.value == "mode":
                    return ast.unparse(value)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.slice, ast.Constant)
                    and target.slice.value == "mode"
                ):
                    return ast.unparse(node.value)
    return None


def deferrals(path: str, source: str) -> list[Deferral]:
    """Every deferral of the kind in one file."""
    found: list[Deferral] = []
    for name, function in _functions(ast.parse(source, filename=path)):
        calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]
        asked = tuple(
            sorted((str(callee(node)), node.lineno) for node in calls if callee(node) in QUESTIONS)
        )
        for node in calls:
            if callee(node) in DEFERRALS and node.args and _is_kind(node.args[0]):
                found.append(Deferral(path, name, node.lineno, _mode_of(function, node), asked))
    return found


def findings(found: list[Deferral]) -> list[Finding]:
    problems: list[Finding] = []
    seen = {(item.path, item.function) for item in found}
    for item in found:
        key = (item.path, item.function)
        if key in PREVIEWS:
            mode, question = PREVIEWS[key]
            if item.mode != mode:
                message = f"{item.function} defers mode {item.mode}, listed with {mode}"
                problems.append(Finding(item.path, item.line, RULE, message))
            before = [line for name, line in item.asked if name == question and line < item.line]
            if not before:
                message = f"{item.function} defers a preview before it asks `{question}`"
                problems.append(Finding(item.path, item.line, RULE, message))
        elif key in SEEDS:
            if item.mode != SEEDS[key][0]:
                message = f"{item.function} plays mode {item.mode}, listed with {SEEDS[key][0]}"
                problems.append(Finding(item.path, item.line, RULE, message))
        elif key in COMPUTATIONS:
            if item.mode is not None:
                message = f"{item.function} is listed as a computation and names mode {item.mode}"
                problems.append(Finding(item.path, item.line, RULE, message))
        else:
            what = "a preview" if item.mode is not None else "a computation"
            message = f"{item.function} defers {what} of a contract group and is not listed"
            problems.append(Finding(item.path, item.line, RULE, message))
    for path, function in sorted({*PREVIEWS, *COMPUTATIONS, *SEEDS} - seen):
        problems.append(Finding(path, 1, RULE, f"{function} {GONE}"))
    return problems


def answered_modes(source: str) -> set[str]:
    """The names ``contract_compute`` compares ``params.get("mode")`` with."""
    functions = dict(_functions(ast.parse(source, filename=COMPUTE_JOB)))
    modes: set[str] = set()
    for node in ast.walk(functions["contract_compute"]):
        if (
            isinstance(node, ast.Compare)
            and isinstance(node.left, ast.Call)
            and callee(node.left) == "get"
            and node.left.args
            and isinstance(node.left.args[0], ast.Constant)
            and node.left.args[0].value == "mode"
        ):
            modes.update(ast.unparse(item) for item in node.comparators)
    return modes


def product_deferrals() -> list[Deferral]:
    found: list[Deferral] = []
    for path in iter_files(PRODUCT, suffixes=PY):
        if "/db/migrations/" not in path:
            found += deferrals(path, read(path))
    return found


def test_dg_krn_apr_07_every_deferral_is_a_preview_that_asks_or_a_listed_computation() -> None:
    found = product_deferrals()
    problems = findings(found)
    assert not problems, report(problems)
    # one deferral each: a second one in a listed function would ride on the first one's question
    assert sorted((item.path, item.function) for item in found) == sorted(
        {*PREVIEWS, *COMPUTATIONS, *SEEDS}
    )
    assert not {*PREVIEWS} & {*COMPUTATIONS} and not {*SEEDS} & ({*PREVIEWS} | {*COMPUTATIONS})


def test_dg_krn_apr_07_the_modes_the_job_answers_are_the_modes_the_previews_defer() -> None:
    answered = answered_modes(read(COMPUTE_JOB))
    assert answered == {mode for mode, _ in PREVIEWS.values()}
    assert len(answered) == len(PREVIEWS) == 4
    assert {mode for mode, _ in SEEDS.values()} <= answered


def mode_literals(source: str) -> dict[str, str]:
    """Name → literal of the module-level ``…_MODE`` strings of the compute job."""
    found: dict[str, str] = {}
    for node in ast.parse(source, filename=COMPUTE_JOB).body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id.endswith("MODE")
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            found[node.target.id] = node.value.value
    return found


def summary_members(source: str) -> dict[str, str]:
    """Mode literal → the params member that names the dry run's subject, as ``TABLE`` of the
    jobs module states them; an entry of another shape is left out and so fails the test."""
    for node in ast.parse(source, filename=JOBS).body:
        if not (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == TABLE
            and isinstance(node.value, ast.Call)
            and node.value.args
            and isinstance(node.value.args[0], ast.Dict)
        ):
            continue
        table = node.value.args[0]
        return {
            str(key.value): str(value.elts[1].value)
            for key, value in zip(table.keys, table.values, strict=True)
            if isinstance(key, ast.Constant)
            and isinstance(value, ast.Tuple)
            and len(value.elts) == 2
            and isinstance(value.elts[1], ast.Constant)
        }
    return {}


def deferred_members(path: str, source: str, function: str) -> set[str]:
    """The members of the parameters ``function`` defers the kind with, where it passes them as
    a literal."""
    functions = dict(_functions(ast.parse(source, filename=path)))
    members: set[str] = set()
    for node in ast.walk(functions[function]):
        if (
            isinstance(node, ast.Call)
            and callee(node) in DEFERRALS
            and len(node.args) > 1
            and _is_kind(node.args[0])
            and isinstance(node.args[1], ast.Dict)
        ):
            members.update(
                str(key.value) for key in node.args[1].keys if isinstance(key, ast.Constant)
            )
    return members


def test_dg_krn_apr_07_the_answer_of_a_job_knows_every_preview() -> None:
    literals = mode_literals(read(COMPUTE_JOB))
    table = summary_members(read(JOBS))
    # both ways: no preview without its subject, and no subject of a mode nothing defers
    assert set(table) == {literals[mode] for mode, _ in PREVIEWS.values()}
    assert len(table) == len(PREVIEWS)
    for (path, function), (mode, _) in sorted(PREVIEWS.items()):
        member = table[literals[mode]]
        assert member in deferred_members(path, read(path), function), (
            f"{TABLE} names `{member}` for {mode}, and {path} {function} defers no such member"
        )


def test_dg_krn_apr_07_the_table_readers_read_what_is_written() -> None:
    assert mode_literals('PREVIEW_MODE: Final = "PREVIEW"\nOTHER: Final = "X"\nN_MODE = "n"\n') == {
        "PREVIEW_MODE": "PREVIEW"
    }
    table = (
        f"{TABLE}: Final[Mapping[str, tuple[str, str]]] = MappingProxyType(\n"
        "    {\n"
        '        "PREVIEW": (CONTRACT_SUBJECT, "contract_id"),\n'
        '        "ADJUSTMENT_PREVIEW": (\n'
        "            ApprovalSubjectType.MANUAL_ADJUSTMENT.value,\n"
        '            "manual_adjustment_id",\n'
        "        ),\n"
        '        "ODD": "contract_id",\n'
        "    }\n"
        ")\n"
    )
    assert summary_members(table) == {
        "PREVIEW": "contract_id",
        "ADJUSTMENT_PREVIEW": "manual_adjustment_id",
    }
    assert summary_members("OTHER: Final = {}\n") == {}
    deferring = (
        "def request_preview(uow, version_id):\n"
        "    uow.defer(JobKind.CLOSE_RUN, {'close_run_id': '1'})\n"
        "    return uow.defer(\n"
        "        JobKind.CONTRACT_COMPUTE,\n"
        "        {'mode': ESTIMATE_PREVIEW_MODE, 'estimate_version_id': str(version_id)},\n"
        "    )\n"
    )
    assert deferred_members(ESTIMATES, deferring, "request_preview") == {
        "mode",
        "estimate_version_id",
    }


def test_dg_krn_apr_07_the_reader_reports_each_kind_of_finding() -> None:
    void = "backend/erev_api/domain/contracts/void.py"
    snippets = {
        # a preview that defers without the question
        MODIFICATIONS: (
            "def request_preview(uow, modification_id):\n"
            "    return uow.defer(JobKind.CONTRACT_COMPUTE, {'mode': MODIFICATION_PREVIEW_MODE})\n"
        ),
        # the question after the deferral
        ESTIMATES: (
            "def request_preview(uow, version_id):\n"
            "    job = uow.defer(JobKind.CONTRACT_COMPUTE, {'mode': ESTIMATE_PREVIEW_MODE})\n"
            "    approvals.require_preview_scope(uow, KIND, version_id)\n"
            "    return job\n"
        ),
        # another question than the listed one, and another mode
        EVENTS: (
            "def request_preview(uow, contract_id):\n"
            "    approvals.require_preview_scope(uow, KIND, contract_id)\n"
            "    return uow.defer(JobKind.CONTRACT_COMPUTE, {'mode': ESTIMATE_PREVIEW_MODE})\n"
        ),
        # a fifth preview, and one whose mode is put into a variable
        void: (
            "def preview(uow, contract_id):\n"
            "    return uow.defer(JobKind.CONTRACT_COMPUTE, {'mode': VOID_PREVIEW_MODE})\n"
            "\n"
            "def other(uow, contract_id):\n"
            "    params = {'contract_id': str(contract_id)}\n"
            "    params['mode'] = VOID_PREVIEW_MODE\n"
            "    return uow.defer_single(JobKind.CONTRACT_COMPUTE, params)\n"
        ),
        # a listed computation that names a mode, and a computation that is not listed
        COMPUTE_JOB: (
            "def defer_compute(uow, group_id):\n"
            "    params = {'combination_group_ids': [str(group_id)], 'mode': PREVIEW_MODE}\n"
            "    return uow.defer(JobKind.CONTRACT_COMPUTE, params)\n"
            "\n"
            "def defer_again(uow, group_id):\n"
            "    return uow.defer(JobKind.CONTRACT_COMPUTE, {'combination_group_ids': []})\n"
        ),
        # no deferral of the kind: another kind, and the kind named by what is no deferral
        "backend/erev_api/domain/close/commands.py": (
            "def close(uow):\n"
            "    uow.defer(JobKind.CLOSE_RUN, {'mode': PREVIEW_MODE})\n"
            "    return task(JobKind.CONTRACT_COMPUTE)\n"
        ),
    }
    found = [item for path, source in snippets.items() for item in deferrals(path, source)]
    rendered = [finding.render() for finding in sorted(findings(found))]
    assert [line for line in rendered if not line.endswith(GONE)] == [
        f"{COMPUTE_JOB}:3 {RULE} defer_compute is listed as a computation and names mode "
        "PREVIEW_MODE",
        f"{COMPUTE_JOB}:6 {RULE} defer_again defers a computation of a contract group and is "
        "not listed",
        f"{ESTIMATES}:2 {RULE} request_preview defers a preview before it asks `{STORED}`",
        f"{EVENTS}:3 {RULE} request_preview defers a preview before it asks `{PENDING}`",
        f"{EVENTS}:3 {RULE} request_preview defers mode ESTIMATE_PREVIEW_MODE, listed with "
        "PREVIEW_MODE",
        f"{MODIFICATIONS}:2 {RULE} request_preview defers a preview before it asks `{STORED}`",
        f"{void}:2 {RULE} preview defers a preview of a contract group and is not listed",
        f"{void}:7 {RULE} other defers a preview of a contract group and is not listed",
    ]
    # what the snippets do not hold is reported as gone
    assert [line for line in rendered if line.endswith(GONE)] == [
        f"{CLOSE_RUNS}:1 {RULE} _recompute_dirty {GONE}",
        f"{VOLUME}:1 {RULE} _apply_modification {GONE}",
        f"{EXCEPTIONS}:1 {RULE} request_reprocess {GONE}",
        f"{ADJUSTMENTS}:1 {RULE} preview {GONE}",
    ]
