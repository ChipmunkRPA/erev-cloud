"""Who may tell the engine that a withdrawal came through the subject (PRD SM-01; 04 §16.10
"Entity scope of a request", §16.14 API-R-37 shapes; dev-guide DG-KRN-APR-02; supervisor ruling
R-41 (8)).

``engine.withdraw`` answers 404 for a request its caller cannot read, so that
``POST /approvals/{id}/withdraw`` confirms no id the read denies. A withdraw route of a subject's
own domain names the SUBJECT: it has authorised the caller for it, the subject's read shows its
pending request, and the documented answer for anyone but the preparer is 403 — also for a second
preparer, who holds the route's permission and cannot read the request. Those commands pass
``through_subject=True``. The two sides must not drift: every domain call passes it, and nothing
under ``erev_api/api`` does.
"""

from __future__ import annotations

import ast

from support.architecture import iter_files, read

# The domain commands that withdraw the pending request of their own subject, with the number of
# calls each makes (a modification withdraws on its route and when a submitted row is edited).
THROUGH_SUBJECT = {
    "backend/erev_api/domain/contracts/estimates.py": 1,
    "backend/erev_api/domain/contracts/events.py": 1,
    "backend/erev_api/domain/contracts/modifications.py": 2,
    "backend/erev_api/domain/journals/adjustments.py": 1,
    "backend/erev_api/domain/policies/registry_versions.py": 1,
    "backend/erev_api/domain/reference/commands.py": 1,
    "backend/erev_api/domain/ssp/publication.py": 1,
}
# The route of the approvals API: it names the request.
BY_REQUEST = {"backend/erev_api/api/v1/approvals.py": 1}


def engine_withdrawals() -> dict[str, list[bool]]:
    """Every call of the engine's ``withdraw`` in the product (recognised by its keyword
    ``approval_request_id``), per file: whether it passes ``through_subject=True``."""
    found: dict[str, list[bool]] = {}
    for path in iter_files("backend/erev_api", suffixes=frozenset({".py"})):
        for node in ast.walk(ast.parse(read(path))):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "withdraw"
            ):
                continue
            keywords = {keyword.arg: keyword.value for keyword in node.keywords}
            if "approval_request_id" not in keywords:
                continue
            flag = keywords.get("through_subject")
            found.setdefault(path, []).append(isinstance(flag, ast.Constant) and flag.value is True)
    return found


def test_every_domain_withdrawal_goes_through_its_subject() -> None:
    found = engine_withdrawals()
    through = {path: flags for path, flags in found.items() if "/domain/" in path}
    assert {path: len(flags) for path, flags in through.items()} == THROUGH_SUBJECT
    assert all(all(flags) for flags in through.values()), through


def test_the_approvals_api_never_withdraws_through_a_subject() -> None:
    found = engine_withdrawals()
    by_request = {path: flags for path, flags in found.items() if "/domain/" not in path}
    assert {path: len(flags) for path, flags in by_request.items()} == BY_REQUEST
    assert not any(any(flags) for flags in by_request.values()), by_request


def test_nothing_reaches_past_withdraw_to_its_body() -> None:
    """Since 04 rev 1.319 ``engine.withdraw`` chooses the scope its body runs under — the
    tenant's through a subject, the caller's on the approvals routes, where the lock stays
    behind the row policy (R-41 (8)) — and the body is ``engine._withdraw``, which takes the flag
    without the scope. A caller of the body would pass the walker above and answer 403 for an id
    its caller cannot read; so the body is named by ``withdraw`` alone (lane SECFIX-APR's
    reading of index 301)."""
    engine = "backend/erev_api/approvals/engine.py"
    named: list[str] = []
    for path in iter_files("backend/erev_api", suffixes=frozenset({".py"})):
        for node in ast.walk(ast.parse(read(path))):
            if isinstance(node, ast.Attribute) and node.attr == "_withdraw":
                named.append(path)
            elif isinstance(node, ast.Name) and node.id == "_withdraw":
                named.append(path)
            elif isinstance(node, ast.alias) and node.name == "_withdraw":
                named.append(path)
    # the two calls of ``withdraw`` itself: through a subject, and not
    assert named == [engine, engine]
