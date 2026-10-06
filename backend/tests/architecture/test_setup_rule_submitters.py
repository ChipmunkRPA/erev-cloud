"""dev-guide DG-KRN-APR-08 (04 T-PLT-01 rev 1.224, item APR-SETUP-RULE-2; supervisor ruling R-38
(iii)): a ``ROLE_ASSIGNMENT`` request is submitted with the setup state read first.

Rule ``AUTO-BOOTSTRAP`` ends when the conditions of PRD BR-PLT-02 hold. The engine reads the stamp
``tenant.setup_completed_at``; the conditions themselves are read by the command that submits,
before it submits (``setup.completion_due``), and handed to ``approvals.submit`` as
``auto_approval``. A submitter that forgets lets the rule approve a grant — a role, or the scopes
of an API client — in a workspace whose setup is complete in all but the stamp. This test finds the
calls that submit the subject by what they pass, and fails for one that does not state
``auto_approval``; and it holds the list of the functions that take the reading.
"""

from __future__ import annotations

import ast
from pathlib import Path

from support.architecture import ROOT

APPLICATION = ROOT / "backend" / "erev_api"
SUBJECT = "ROLE_ASSIGNMENT"
READING = "completion_due"
STAMP = "evaluate_setup_completion"
# ``<module path under erev_api>:<function>`` of every function that takes the reading: it asks
# ``setup.completion_due`` before the request is submitted and ``setup.evaluate_setup_completion``
# after it, as its last lock (dev-guide DG-KRN-DB-08 (3a)).
READERS = frozenset(
    {
        "domain/platform/users.py:request_role_assignment",
        "api/v1/api_clients.py:api_clients_create",
    }
)
# A submitter that is handed the reading by its caller instead of taking it: the parameter has no
# default, so every caller states it.
HANDED = frozenset({"auth/api_clients.py:create_api_client"})


def _called(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return call.func.id if isinstance(call.func, ast.Name) else None


def _submits_the_subject(call: ast.Call) -> bool:
    """``…submit(…, subject_type=ApprovalSubjectType.ROLE_ASSIGNMENT, …)``."""
    if _called(call) != "submit":
        return False
    return any(
        keyword.arg == "subject_type"
        and isinstance(keyword.value, ast.Attribute)
        and keyword.value.attr == SUBJECT
        for keyword in call.keywords
    )


def submitters(root: Path = APPLICATION) -> dict[str, dict[str, bool]]:
    """``<module>:<function>`` of every top-level function that submits the subject → what it
    does about the setup state: ``states`` (the call passes ``auto_approval``), ``reads`` and
    ``stamps`` (the function calls the reading and the evaluation), ``handed`` (``auto_approval``
    is a keyword-only parameter without a default). A nested function counts with the function
    that holds it."""
    found: dict[str, dict[str, bool]] = {}
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            calls = [inner for inner in ast.walk(node) if isinstance(inner, ast.Call)]
            submits = [call for call in calls if _submits_the_subject(call)]
            names = {_called(call) for call in calls}
            if not submits and READING not in names:
                continue
            required = {
                argument.arg
                for argument, default in zip(
                    node.args.kwonlyargs, node.args.kw_defaults, strict=True
                )
                if default is None
            }
            found[f"{path.relative_to(root).as_posix()}:{node.name}"] = {
                "submits": bool(submits),
                "states": all(
                    any(keyword.arg == "auto_approval" for keyword in call.keywords)
                    for call in submits
                ),
                "reads": READING in names,
                "stamps": STAMP in names,
                "handed": "auto_approval" in required,
            }
    return found


def test_dg_krn_apr_08_every_submitter_of_a_role_assignment_states_the_setup_reading() -> None:
    found = submitters()
    submitting = {ref for ref, facts in found.items() if facts["submits"]}
    assert len(submitting) >= 2, sorted(found)
    silent = {ref for ref in submitting if not found[ref]["states"]}
    assert not silent, {"submits a ROLE_ASSIGNMENT without auto_approval": sorted(silent)}
    # Whoever submits takes the reading itself, or is handed it by a parameter without a default.
    reading = {ref for ref, facts in found.items() if facts["reads"]}
    assert reading == READERS, {
        "takes the reading and is not listed": sorted(reading - READERS),
        "listed and takes no reading": sorted(READERS - reading),
    }
    assert all(found[ref]["stamps"] for ref in READERS), {
        "reads the conditions and never sets the stamp": sorted(
            ref for ref in READERS if not found[ref]["stamps"]
        )
    }
    handed = {ref for ref in submitting if not found[ref]["reads"]}
    assert handed == HANDED, {
        "submits without the reading and is not listed": sorted(handed - HANDED),
        "listed and takes the reading itself, or submits nothing": sorted(HANDED - handed),
    }
    assert all(found[ref]["handed"] for ref in HANDED), {
        "auto_approval has a default, so a caller can forget it": sorted(
            ref for ref in HANDED if not found[ref]["handed"]
        )
    }


def test_the_scan_sees_a_submitter_that_forgets(tmp_path: Path) -> None:
    """The check can fail: a function that submits the subject without ``auto_approval`` is found
    as silent, one that reads and states it as a reader, and another subject is not its business."""
    module = tmp_path / "domain" / "platform"
    module.mkdir(parents=True)
    (module / "example.py").write_text(
        "def forgets(uow):\n"
        "    approvals.submit(uow, subject_type=ApprovalSubjectType.ROLE_ASSIGNMENT)\n"
        "\n"
        "def remembers(uow):\n"
        "    due = setup.completion_due(uow)\n"
        "    approvals.submit(\n"
        "        uow, subject_type=ApprovalSubjectType.ROLE_ASSIGNMENT, auto_approval=not due\n"
        "    )\n"
        "    setup.evaluate_setup_completion(uow)\n"
        "\n"
        "def handed(uow, *, auto_approval):\n"
        "    approvals.submit(\n"
        "        uow,\n"
        "        subject_type=ApprovalSubjectType.ROLE_ASSIGNMENT,\n"
        "        auto_approval=auto_approval,\n"
        "    )\n"
        "\n"
        "def other(uow):\n"
        "    approvals.submit(uow, subject_type=ApprovalSubjectType.ROLE_CHANGE)\n",
        encoding="utf-8",
    )
    assert submitters(tmp_path) == {
        "domain/platform/example.py:forgets": {
            "submits": True,
            "states": False,
            "reads": False,
            "stamps": False,
            "handed": False,
        },
        "domain/platform/example.py:remembers": {
            "submits": True,
            "states": True,
            "reads": True,
            "stamps": True,
            "handed": False,
        },
        "domain/platform/example.py:handed": {
            "submits": True,
            "states": True,
            "reads": False,
            "stamps": False,
            "handed": True,
        },
    }
