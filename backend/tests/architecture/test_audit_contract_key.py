"""DG-KRN-AUD-09: an audit event of an object that belongs to a contract names the contract
(dev-guide §5.5, rev 1.137; 04 T-PLT-19 and §1.7, rev 1.154; supervisor ruling R-108).

``erev_api.audit.contract_key`` holds three closed lists of object types — ``ALWAYS``,
``WHERE_NAMED`` and ``OTHER``. This test reads every call of the audit writer in ``erev_api``
(``uow.audit``, ``record``, ``record_facts``, ``record_now``, ``record_denied``, ``build_event``;
and ``guards.ensure_production``, which writes a sandbox's refusal under its caller's object type):

- the object type of the call is in one of the three lists — a new object type is classified
  before it is written;
- a call for an ``ALWAYS`` or ``WHERE_NAMED`` type passes ``contract_id=`` or ``contract_ids=``
  (for ``WHERE_NAMED`` the value may be None; an ``ALWAYS`` event without a contract is refused by
  the writer when it is built, a ``DENIED`` event excepted);
- no call puts ``contract_id`` or ``contract_ids`` into ``detail`` itself: the key has one way in;
- a call whose object type is computed is one of ``COMPUTED``, each with what it may write.

The audit-coverage walk (``tests/domain/platform/test_audit_coverage.py``, CTL-038) holds the
same lists against the events every command route writes.
"""

from __future__ import annotations

import ast
import importlib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Final

from erev_api.audit import contract_key
from erev_api.db.tables import metadata
from support.architecture import ROOT

PACKAGE: Final = ROOT / "backend" / "erev_api"
WRITERS: Final = frozenset(
    {
        "audit",
        "record",
        "record_facts",
        "record_now",
        "record_denied",
        "build_event",
        # The sandbox guard (05 SBX-08): its caller names the object of the DENIED event.
        "ensure_production",
    }
)
KEYWORDS: Final = frozenset({"contract_id", "contract_ids"})
# The writer's own forwarding calls pass the caller's object type on; so does the sandbox guard,
# whose callers are read as writer calls.
FORWARDING: Final = frozenset(
    {"backend/erev_api/audit/writer.py", "backend/erev_api/domain/platform/guards.py"}
)
# Calls whose object type is computed where they stand: {file: (what it writes, scoped)}. A scoped
# one passes the key like any other call.
COMPUTED: Final[dict[str, tuple[str, bool]]] = {
    "backend/erev_api/approvals/subjects.py": (
        "the table of a grant subject (sod_exception, support_grant): approved, rejected, voided",
        False,
    ),
    "backend/erev_api/domain/contracts/computation.py": (
        "the facts of a computation by object type: contract_version, obligation_version, "
        "contract_version_balance, schedule, schedule_line, calc_trace — of the group's members",
        True,
    ),
    "backend/erev_api/domain/integrations/commands.py": (
        "the refusal of an inbound connection in a sandbox, handed to the sandbox guard under "
        "the object of the refused command (integration_connection, sync_run)",
        False,
    ),
    "backend/erev_api/domain/platform/attachments.py": (
        "a refused guard (DENIED): the object is the subject the request named, of any attachment "
        "subject type; the permission is refused before the subject is read, so no contract is "
        "held and a DENIED event is not refused for want of a key",
        False,
    ),
    "backend/erev_api/domain/policies/lifecycle.py": (
        "the versioned configuration kinds (rule set, template, registry, mapping versions)",
        False,
    ),
    "backend/erev_api/domain/ssp/commands.py": (
        "SSP entries and ranges of a book version",
        False,
    ),
}


@dataclass(frozen=True, slots=True)
class Call:
    path: str
    line: int
    object_type: str | None  # None: computed where the call stands
    keyed: bool  # passes contract_id= or contract_ids=
    key_in_detail: bool  # a detail literal that carries the key itself

    def __str__(self) -> str:
        return f"{self.path}:{self.line}"


def _module(path: Path) -> Any:
    relative = path.relative_to(ROOT / "backend").with_suffix("")
    return importlib.import_module(".".join(relative.parts))


def _resolved(node: ast.expr, namespace: Any) -> str | None:
    """The string a module-level name or attribute chain stands for; None for anything computed."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.Name):
        value = getattr(namespace, node.id, None)
    elif isinstance(node, ast.Attribute):
        chain: list[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            chain.append(current.attr)
            current = current.value
        if not isinstance(current, ast.Name):
            return None
        value = getattr(namespace, current.id, None)
        for attribute in reversed(chain):
            value = getattr(value, attribute, None)
    else:
        return None
    if isinstance(value, Enum):
        value = value.value
    return value if isinstance(value, str) else None


def _detail_carries_key(node: ast.expr | None) -> bool:
    if not isinstance(node, ast.Dict):
        return False
    return any(
        isinstance(key, ast.Constant) and key.value in KEYWORDS
        for key in node.keys
        if key is not None
    )


def writer_calls() -> list[Call]:
    """Every audit writer call of ``erev_api`` that names an action and an object type."""
    found: list[Call] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if "/db/migrations/" in relative or relative in FORWARDING:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (
                node.func.attr
                if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            in WRITERS
        ]
        calls = [
            node
            for node in calls
            if {"action", "object_type"} <= {keyword.arg for keyword in node.keywords}
        ]
        if not calls:
            continue
        namespace = _module(path)
        for node in calls:
            keywords = {keyword.arg: keyword.value for keyword in node.keywords if keyword.arg}
            found.append(
                Call(
                    path=relative,
                    line=node.lineno,
                    object_type=_resolved(keywords["object_type"], namespace),
                    keyed=bool(KEYWORDS & set(keywords)),
                    key_in_detail=_detail_carries_key(keywords.get("detail")),
                )
            )
    return found


def findings(calls: list[Call]) -> list[str]:
    known = contract_key.ALWAYS | contract_key.WHERE_NAMED | contract_key.OTHER
    problems: list[str] = []
    for call in calls:
        if call.key_in_detail:
            problems.append(f"{call}: the contract key is inside detail; pass contract_id=")
        if call.object_type is None:
            reason = COMPUTED.get(call.path)
            if reason is None:
                problems.append(f"{call}: a computed object type outside COMPUTED")
            elif reason[1] and not call.keyed:
                problems.append(f"{call}: writes contract objects without contract_id(s)=")
            continue
        if call.object_type not in known:
            problems.append(f"{call}: object type {call.object_type!r} is in none of the lists")
        elif contract_key.scoped(call.object_type) and not call.keyed:
            problems.append(
                f"{call}: an event of {call.object_type} passes no contract_id= / contract_ids="
            )
    return problems


def test_dg_krn_aud_09_the_three_lists_are_closed_and_disjoint() -> None:
    always, named, other = contract_key.ALWAYS, contract_key.WHERE_NAMED, contract_key.OTHER
    assert not (always & named) and not (always & other) and not (named & other)
    # A table that carries `contract_id` is classified by name: scoped, or OTHER on purpose.
    with_contract = {table.name for table in metadata.sorted_tables if "contract_id" in table.c}
    unclassified = sorted(with_contract - always - named - other - NOT_AUDIT_OBJECTS)
    assert unclassified == [], f"tables with contract_id in no list: {unclassified}"


# Tables with a `contract_id` column that no audit event is written for: rows of imports and
# migrations, whose evidence is the import's or the batch's own events, and the index of the key
# itself (T-PLT-48: derived from the event, AUD-OPS).
NOT_AUDIT_OBJECTS: Final = frozenset(
    {"audit_event_contract", "migrated_legacy_row", "migration_population_obligation"}
)


def test_dg_krn_aud_09_every_writer_classifies_its_object_and_names_its_contract() -> None:
    calls = writer_calls()
    assert len(calls) > 300, "the reader found too few audit writer calls to be trusted"
    assert findings(calls) == []
    computed = {call.path for call in calls if call.object_type is None}
    assert computed == set(COMPUTED), sorted(computed ^ set(COMPUTED))


def test_dg_krn_aud_09_the_reader_reports_each_kind_of_finding() -> None:
    calls = [
        Call("a.py", 1, "contract", keyed=True, key_in_detail=False),
        Call("a.py", 2, "modification", keyed=False, key_in_detail=False),
        Call("a.py", 3, "judgement_record", keyed=False, key_in_detail=False),
        Call("a.py", 4, "tenant", keyed=False, key_in_detail=False),
        Call("a.py", 5, "brand_new_table", keyed=False, key_in_detail=False),
        Call("a.py", 6, "contract", keyed=True, key_in_detail=True),
        Call("a.py", 7, None, keyed=False, key_in_detail=False),
        Call("backend/erev_api/domain/contracts/computation.py", 8, None, False, False),
        Call("backend/erev_api/domain/policies/lifecycle.py", 9, None, False, False),
    ]
    assert findings(calls) == [
        "a.py:2: an event of modification passes no contract_id= / contract_ids=",
        "a.py:3: an event of judgement_record passes no contract_id= / contract_ids=",
        "a.py:5: object type 'brand_new_table' is in none of the lists",
        "a.py:6: the contract key is inside detail; pass contract_id=",
        "a.py:7: a computed object type outside COMPUTED",
        "backend/erev_api/domain/contracts/computation.py:8: writes contract objects without "
        "contract_id(s)=",
    ]
