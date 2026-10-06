"""DG-MIG-12: a migration never reads a live Python enum (dev-guide §6.5 rev 1.41; D-98 candidate
108; F-ADM-MIG-R1 after the landing d350a37a whose post-check failed on a fresh ``erev_test``).

Revision 0004 created ``security_event_kind`` from the live ``SecurityEventKind``, so on a fresh
database the type already held ``INVITATION_LOOKUP_FAILED`` and revision 0058's ``add_enum_value``
failed with ``DuplicateObject``, while an upgraded 0057 database accepted it — the history was not
reproducible. Two CPU checks, no database:

- the source rule: a revision imports nothing of ``erev_api`` beyond ``ALLOWED_IMPORTS`` — the
  DDL helpers and the DG-MIG-07 seed catalogues — so never ``erev_api.enums``, and every
  ``create_enum`` receives a literal label sequence (inline, a module constant, or the loop
  variable of a ``for name, labels in ENUMS`` / ``.items()`` over a module-level literal of pairs);
- the replay rule: every ``upgrade()`` is replayed in revision order under
  ``migration_ops.recording()`` (DG-ARC-09's twin); per enum type the creating revision's literal
  is applied, then each ``ADD VALUE`` in revision order with PostgreSQL's placement (append, or
  insert after the ``AFTER`` anchor); a repeated label, an unknown anchor or a type created twice
  is a finding, and the resulting ORDERED label list must equal the Python mirror's member order.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from erev_api.db import migration_ops as ops
from support.enum_mirrors import VERSIONS_DIR, database_enums, load_revision

_LABELS: Final = re.compile(r"'((?:[^']|'')*)'")
_CREATE: Final = re.compile(r"^CREATE TYPE erev\.(\w+) AS ENUM \((.*)\)$", re.S)
_ADD: Final = re.compile(
    r"^ALTER TYPE erev\.(\w+) ADD VALUE ('(?:[^']|'')*')(?: AFTER ('(?:[^']|'')*'))?$"
)
ENUM_CALLS: Final = frozenset({"create_enum"})
# The only `erev_api` modules a revision may import: the DDL helpers and the DG-MIG-07 seed
# catalogues (global catalogues seeded by literal rows). `erev_api.enums` is never among them.
ALLOWED_IMPORTS: Final = frozenset(
    {
        "erev_api.db.migration_ops",
        "erev_api.db",  # `from erev_api.db import migration_ops as ops`
        "erev_api.registry.policies",  # DG-MIG-07: POLICY_PARAMETERS seed (0003)
        "erev_api.registry.platform",  # DG-MIG-07: PLATFORM_PARAMETERS seed (0003)
        "erev_api.auth.permissions",  # DG-MIG-07: permission CATALOGUE seed
    }
)


def _revisions() -> list[Path]:
    return sorted(VERSIONS_DIR.glob("[0-9]*.py"))


def _labels(text: str) -> list[str]:
    return [match.replace("''", "'") for match in _LABELS.findall(text)]


# --- source rule --------------------------------------------------------------------------------


@dataclass
class _Module:
    constants: dict[str, ast.expr] = field(default_factory=dict)
    loops: dict[str, ast.expr] = field(default_factory=dict)  # loop target name → the iterated Name


def _literal_sequence(node: ast.expr, module: _Module) -> bool:
    """A tuple or list of string constants, directly or through a module-level constant."""
    if isinstance(node, ast.Name) and node.id in module.constants:
        node = module.constants[node.id]
    return isinstance(node, ast.Tuple | ast.List) and all(
        isinstance(element, ast.Constant) and isinstance(element.value, str)
        for element in node.elts
    )


def _literal_pairs(node: ast.expr, module: _Module) -> bool:
    """A module-level literal of ``(name, labels)`` pairs — a tuple or list of 2-tuples, or a dict
    iterated through ``.items()`` — each label sequence literal."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "items" and not node.args:
            node = node.func.value
    if isinstance(node, ast.Name) and node.id in module.constants:
        node = module.constants[node.id]
    if isinstance(node, ast.Dict):
        return all(
            isinstance(key, ast.Constant) and _literal_sequence(value, module)
            for key, value in zip(node.keys, node.values, strict=True)
        )
    return isinstance(node, ast.Tuple | ast.List) and all(
        isinstance(pair, ast.Tuple)
        and len(pair.elts) == 2
        and isinstance(pair.elts[0], ast.Constant)
        and _literal_sequence(pair.elts[1], module)
        for pair in node.elts
    )


def _index(tree: ast.Module) -> _Module:
    module = _Module()
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                module.constants[target.id] = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.value is not None:
                module.constants[node.target.id] = node.value
    for node in ast.walk(tree):
        if isinstance(node, ast.For) and isinstance(node.target, ast.Tuple):
            if len(node.target.elts) == 2 and isinstance(node.target.elts[1], ast.Name):
                module.loops[node.target.elts[1].id] = node.iter
    return module


def _foreign_imports(tree: ast.Module) -> Iterator[str]:
    """Every ``erev_api`` import outside ``ALLOWED_IMPORTS`` — ``erev_api.enums`` above all."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = ", ".join(alias.name for alias in node.names)
            if module.startswith("erev_api") and module not in ALLOWED_IMPORTS:
                yield f"from {module} import {names}"
            elif module == "erev_api.db" and names != "migration_ops":
                yield f"from {module} import {names}"
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("erev_api") and alias.name not in ALLOWED_IMPORTS:
                    yield f"import {alias.name}"


def _non_literal_create_enum_calls(tree: ast.Module, source: str) -> Iterator[str]:
    module = _index(tree)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr not in ENUM_CALLS or len(node.args) < 2:
            continue
        labels = node.args[1]
        if _literal_sequence(labels, module):
            continue
        if isinstance(labels, ast.Name) and labels.id in module.loops:
            if _literal_pairs(module.loops[labels.id], module):
                continue
        yield ast.get_source_segment(source, node) or ast.dump(node)


def test_dg_mig_12_revisions_never_read_live_enums() -> None:
    """No revision imports anything of ``erev_api`` beyond the DDL helpers and the DG-MIG-07 seed
    catalogues (so never ``erev_api.enums``), and every ``create_enum`` receives literal labels."""
    findings: list[str] = []
    for path in _revisions():
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        findings += [f"{path.name}: {line}" for line in _foreign_imports(tree)]
        findings += [
            f"{path.name}: non-literal labels in {call}"
            for call in _non_literal_create_enum_calls(tree, source)
        ]
    assert findings == [], "\n".join(findings)


# --- replay rule --------------------------------------------------------------------------------


@dataclass
class _EnumHistory:
    created_in: str
    created: list[str]
    labels: list[str]  # the ordered labels after every replayed ADD VALUE, in revision order
    added: list[tuple[str, str]] = field(default_factory=list)  # (label, revision)

    def add(self, label: str, after: str | None) -> None:
        """PostgreSQL semantics: ``ADD VALUE`` appends, ``ADD VALUE … AFTER x`` inserts after x."""
        if after is None:
            self.labels.append(label)
        else:
            self.labels.insert(self.labels.index(after) + 1, label)


def _replay() -> tuple[dict[str, _EnumHistory], list[str]]:
    """Every enum type's created labels and later additions, plus the findings of the replay."""
    history: dict[str, _EnumHistory] = {}
    findings: list[str] = []
    for path in _revisions():
        module = load_revision(path)
        with ops.recording() as statements:
            module.upgrade()  # type: ignore[attr-defined]
        for statement in statements:
            created = _CREATE.match(statement.strip())
            if created is not None:
                name, body = created.groups()
                if name in history:
                    findings.append(f"{path.name}: erev.{name} created twice")
                labels = _labels(body)
                history[name] = _EnumHistory(path.name, labels, list(labels))
                continue
            added = _ADD.match(statement.strip())
            if added is None:
                continue
            name, literal, after_literal = added.groups()
            (label,) = _labels(literal)
            after = None if after_literal is None else _labels(after_literal)[0]
            entry = history.get(name)
            if entry is None:
                findings.append(f"{path.name}: ADD VALUE {label!r} on unknown type erev.{name}")
            elif label in entry.labels:
                findings.append(
                    f"{path.name}: erev.{name} already holds {label!r} "
                    f"(created in {entry.created_in}) — a fresh upgrade fails with DuplicateObject"
                )
            elif after is not None and after not in entry.labels:
                findings.append(
                    f"{path.name}: erev.{name} ADD VALUE {label!r} AFTER unknown {after!r}"
                )
            else:
                entry.add(label, after)
                entry.added.append((label, path.name))
    return history, findings


def test_dg_mig_12_replayed_labels_are_added_once_and_equal_the_mirrors() -> None:
    """Replaying every ``upgrade()`` in revision order: no ``ADD VALUE`` repeats a label the type
    already holds, and the ORDERED label list — the creating revision's literal, then each
    ``add_enum_value`` in revision order with PostgreSQL's append / ``AFTER`` placement — equals
    the Python mirror's member order, type by type (a head-only set union would not prove the
    history)."""
    history, findings = _replay()
    mirrors = database_enums()
    for name, entry in sorted(history.items()):
        mirror = mirrors.get(name)
        if mirror is None:
            continue  # types without a StrEnum mirror are DG-ARC-09's concern (type_gaps)
        expected = [member.value for member in mirror]
        if entry.labels != expected:
            findings.append(
                f"erev.{name}: replayed ordered labels {entry.labels} differ from "
                f"{mirror.__name__} {expected} (created in {entry.created_in}: {entry.created}; "
                f"added: {entry.added})"
            )
    assert findings == [], "\n".join(findings)
    # The defect that motivated the rule is covered by name: the label 0058 adds was not created.
    security = history["security_event_kind"]
    assert "INVITATION_LOOKUP_FAILED" not in security.created
    # 04 E-79 rev 1.108 (supervisor ruling R-50 (b)): revision 0092 appends the two MFA kinds;
    # rev 1.189 (ruling R-111 (6)): revision 0103 appends the passed challenge and the refusal of
    # a session that owes its step outside an open workspace.
    assert [label for label, _ in security.added] == [
        "INVITATION_LOOKUP_FAILED",
        "MFA_ENROLMENT_STARTED",
        "RECOVERY_CODES_REGENERATED",
        "MFA_CHALLENGE_PASSED",
        "MFA_PENDING_DENIED",
    ]
