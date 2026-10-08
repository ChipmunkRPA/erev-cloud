"""The entities a preparer is held to are stated by THREE subjects, each by a ruling (supervisor
rulings R-64 (6) and R-106 (b), and of 2026-10-01 for item MANUAL-EVENT-PREPARER-SCOPE-1; 04
§16.10 rev 1.104 part 10 and rev 1.269; dev-guide DG-KRN-APR-06, DG-KRN-APR-07).

``SubjectSpec.preparer_entities`` narrows the check of a preparer at submission. The preparer of
an import is held to the entities of the rows that commit, while the request names every entity
any row names. The preparer of an event submission — ``MANUAL_EVENT``, ``ATTRIBUTE_CHANGE`` — is
held to the contracting entity of the ONE contract she records the events on, while the request
names the contracting entities of that contract's whole group, which its approval computes. A
narrowing that another subject adopted without a ruling would let a preparer submit what they
cannot read in full, so the seam is pinned: these three specifications state it, and
``domain/imports/commit.py`` and ``domain/contracts/events.py`` are the only modules that
register one. A new use fails here until 04 §16.10 says why that subject's preparer covers less
than its request names.
"""

from __future__ import annotations

import ast

from erev_api.approvals import subjects
from erev_api.domain.contracts import events as contract_events
from erev_api.domain.imports import commit as import_commit
from erev_api.domain.imports import scope as import_scope
from erev_api.enums import ApprovalSubjectType
from support.architecture import iter_files, read

SEAM = "preparer_entities"
# The specification entries of the kernel, and the registrations of the two domains: how often
# each file passes ``preparer_entities=`` to a call.
STATED_IN = {
    "backend/erev_api/approvals/subjects.py": 4,  # import and the three event-submission subjects
    "backend/erev_api/domain/imports/commit.py": 1,
    # one registration in a loop over the three event-submission subjects
    "backend/erev_api/domain/contracts/events.py": 1,
}
# A lifecycle is registered when its module is imported.
REGISTRANTS = (contract_events, import_commit)


def stating_files() -> dict[str, list[int]]:
    """The product files that pass ``preparer_entities=`` to a call, with the lines."""
    found: dict[str, list[int]] = {}
    for path in iter_files("backend/erev_api", suffixes=frozenset({".py"})):
        for node in ast.walk(ast.parse(read(path))):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == SEAM:
                        found.setdefault(path, []).append(node.lineno)
    return found


def test_event_and_import_subjects_state_preparer_entities() -> None:
    stated = sorted(
        subject_type.value
        for subject_type, spec in subjects.SUBJECTS.items()
        if spec.preparer_entities is not None
    )
    assert stated == sorted(
        [
            ApprovalSubjectType.ATTRIBUTE_CHANGE.value,
            ApprovalSubjectType.IMPORT_COMMIT.value,
            ApprovalSubjectType.MANUAL_EVENT.value,
            ApprovalSubjectType.STEP1_EVENT.value,
        ]
    )


def test_r106_only_the_imports_and_the_contracts_domain_register_preparer_entities() -> None:
    found = stating_files()
    assert set(found) == set(STATED_IN), found
    assert {path: len(lines) for path, lines in found.items()} == STATED_IN
    # ... the two domain modules are the registrants this test imports ...
    assert {
        "backend/" + module.__name__.replace(".", "/") + ".py" for module in REGISTRANTS
    } == set(STATED_IN) - {"backend/erev_api/approvals/subjects.py"}
    # ... and what each domain registers is its own statement, for its own subjects
    registered = {
        subject_type: lifecycle.preparer_entities
        for subject_type, lifecycle in subjects.LIFECYCLES.items()
        if lifecycle.preparer_entities is not None
    }
    assert registered == {
        ApprovalSubjectType.ATTRIBUTE_CHANGE: contract_events.preparer_entities,
        ApprovalSubjectType.IMPORT_COMMIT: import_scope.preparer_entities,
        ApprovalSubjectType.MANUAL_EVENT: contract_events.preparer_entities,
        ApprovalSubjectType.STEP1_EVENT: contract_events.preparer_entities,
    }
