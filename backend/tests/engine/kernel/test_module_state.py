"""DG-ENG-08: no module-level mutable state in ``erev_engine`` (BUILD_SPEC END-9).

An ``ast`` scan of every module of ``backend/erev_engine/``. A module-level assignment whose value
is a ``dict``, ``list`` or ``set`` (literal, comprehension or constructor call) is a finding, unless
the target is annotated ``Final`` and the value is wrapped in ``types.MappingProxyType``, or is a
tuple or a frozenset. ``__all__`` is the module's export list, never read as state, so it is exempt
(L3-2-Q-17). A module-level call that mutates a module name (``.update``, ``.append`` and the like)
is a finding too. No database (DG-TST-18).
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path
from typing import Final

ENGINE_ROOT: Final = Path(__file__).resolve().parents[3] / "erev_engine"
MUTABLE_CALLS: Final = frozenset({"dict", "list", "set", "defaultdict", "OrderedDict", "Counter"})
MUTATORS: Final = frozenset(
    {"update", "append", "extend", "insert", "add", "setdefault", "pop", "clear", "remove"}
)
EXEMPT_TARGETS: Final = frozenset({"__all__"})


def _call_name(node: ast.expr) -> str | None:
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _mutable(value: ast.expr) -> str | None:
    """The kind of mutable container ``value`` builds, else None."""
    if isinstance(value, ast.Dict | ast.DictComp):
        return "dict"
    if isinstance(value, ast.List | ast.ListComp):
        return "list"
    if isinstance(value, ast.Set | ast.SetComp):
        return "set"
    name = _call_name(value)
    return name if name in MUTABLE_CALLS else None


def _final(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False
    head = annotation.value if isinstance(annotation, ast.Subscript) else annotation
    return (isinstance(head, ast.Name) and head.id == "Final") or (
        isinstance(head, ast.Attribute) and head.attr == "Final"
    )


def findings(source: str, path: str) -> Iterator[str]:
    """Every DG-ENG-08 finding of one module, as ``<path>:<line> <what>``."""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [ast.unparse(target) for target in targets]
            if set(names) <= EXEMPT_TARGETS:
                continue
            annotation = node.annotation if isinstance(node, ast.AnnAssign) else None
            kind = _mutable(node.value)
            if kind is not None:
                yield f"{path}:{node.lineno} module-level {kind} {', '.join(names)}"
            elif _call_name(node.value) == "MappingProxyType" and not _final(annotation):
                yield f"{path}:{node.lineno} MappingProxyType constant not typed Final: {names}"
        elif isinstance(node, ast.Expr):
            call = node.value
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Attribute)
                and call.func.attr in MUTATORS
                and isinstance(call.func.value, ast.Name)
            ):
                yield f"{path}:{node.lineno} module-level mutation {ast.unparse(call.func)}"


def test_no_module_level_mutable_state() -> None:
    modules = sorted(ENGINE_ROOT.rglob("*.py"))
    assert len(modules) > 100  # the scan reaches every stage package
    found = [
        item
        for module in modules
        for item in findings(
            module.read_text(encoding="utf-8"), str(module.relative_to(ENGINE_ROOT))
        )
    ]
    assert found == []


def test_scan_detects_mutable_state() -> None:
    probe = "\n".join(
        [
            "from typing import Final",
            "from types import MappingProxyType",
            "CACHE = {}",
            "ITEMS: Final = [1, 2]",
            "SEEN = set()",
            "VIEW = MappingProxyType({'a': 1})",
            "OK: Final = MappingProxyType({'a': 1})",
            "PAIR: Final = (1, 2)",
            "__all__ = ['OK']",
            "CACHE.update({'b': 2})",
        ]
    )
    assert [item.split(" ", 1)[1] for item in findings(probe, "probe.py")] == [
        "module-level dict CACHE",
        "module-level list ITEMS",
        "module-level set SEEN",
        "MappingProxyType constant not typed Final: ['VIEW']",
        "module-level mutation CACHE.update",
    ]
