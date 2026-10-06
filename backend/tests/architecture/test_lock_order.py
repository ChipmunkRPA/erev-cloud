"""DG-KRN-DB-08 rev 1.36 (D-98 candidates 101a / 101b), source guard: outside the kernel helper
``erev_api.db.locking.lock_group_then_contract`` a contract row may be locked ``FOR UPDATE`` only
where the combination-group row is already locked (an allowlist with the reason), so no future
entry path can reintroduce the contract-then-group order that ``activation``, ``record_events``,
holds, memos, imports and the approval hooks followed before the P5-LOCK slices. Lexical by
construction: it sees explicit ``for_update`` calls and ``select(contract…).with_for_update()``
statements; the implicit ``UPDATE`` locks of ``events/stream.py`` are covered because every path
that reaches them goes through the helper first (``tests/unit/test_activation_lock_order.py``)."""

from __future__ import annotations

import re
from pathlib import Path

import erev_api

ROOT = Path(erev_api.__file__).parent
# module → why a direct contract row lock is allowed there
ALLOWED = {
    "db/locking.py": "the one lock order (group row, then contract row)",
    "domain/contracts/repo.py": "the get_contract primitive's `for_update` parameter",
    "domain/contracts/combination.py": (
        "_lock_groups_then_contracts: every touched group row first (target, originals, leave "
        "singletons; ascending ids), then the member contracts; the only direct lock site"
    ),
}
_EXPLICIT = re.compile(
    r"get_contract\((?:[^()]|\([^()]*\))*?for_update\s*=\s*(?!False\b)[A-Za-z_]+"
)
_STATEMENT = re.compile(
    r"select\(\s*contract(?:\.c\.[a-z_]+)?\b(?:(?!\n\n)[\s\S]){0,400}?\.with_for_update\("
)


def _contract_locks(source: str) -> list[str]:
    hits = [m.group(0).split("\n")[0][:80] for m in _EXPLICIT.finditer(source)]
    hits += [m.group(0).split("\n")[0][:80] for m in _STATEMENT.finditer(source)]
    return hits


def test_contract_row_locks_go_through_the_one_order() -> None:
    findings: dict[str, list[str]] = {}
    for path in sorted(ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith("db/migrations/"):
            continue
        source = path.read_text(encoding="utf-8")
        if relative == "domain/contracts/repo.py":
            source = source.replace("for_update: bool = False", "")  # the parameter, not a call
        hits = _contract_locks(source)
        if hits and relative not in ALLOWED:
            findings[relative] = hits
    assert findings == {}, findings
    present = {relative for relative in ALLOWED if (ROOT / relative).exists()}
    assert present == set(ALLOWED), "an allowlisted module moved; update the reason"


def test_combination_locks_contracts_only_inside_its_group_first_helper() -> None:
    """The allowlist entry for ``combination.py`` is narrow: its one direct contract lock sits
    inside ``_lock_groups_then_contracts``, after the group locks of the same helper."""
    source = (ROOT / "domain/contracts/combination.py").read_text(encoding="utf-8")
    start = source.index("def _lock_groups_then_contracts(")
    end = source.index("\ndef ", start + 1)
    helper, outside = source[start:end], source[:start] + source[end:]
    assert len(_contract_locks(helper)) == 1
    assert _contract_locks(outside) == []
    assert helper.index("repo.lock_group(") < helper.index("for_update=True")
