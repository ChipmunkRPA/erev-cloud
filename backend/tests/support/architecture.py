"""Source scanning for the architecture tests (docs/dev-guide.md §6.8; BUILD_SPEC FND-13).

The tests read files with ``ast`` and ``re`` only; nothing scanned is imported or executed. Findings
carry repository-relative POSIX paths, so a snippet can pose as any file of the tree.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[3]
# Build outputs, caches and dependency trees are never source (DG-LAY-08).
PRUNED_DIRS: Final = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".hypothesis",
        "dist",
        "coverage",
        ".screens",
        ".results",
    }
)


@dataclass(frozen=True, slots=True, order=True)
class Finding:
    path: str
    line: int
    rule: str
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line} {self.rule} {self.message}"


# DG-ENV-14 and DG-ARC-05 as ruled by D-78: each verb with each object, and the server-settings
# statement, fail the build. test_forbidden_patterns builds its rule from these, and test_guides
# checks the ITGC guide against them.
DATABASE_ADMINISTRATION_VERBS: Final = ("CREATE", "ALTER", "DROP")
DATABASE_ADMINISTRATION_OBJECTS: Final = (
    "DATABASE",
    "ROLE",
    "USER",
    "GROUP",
    "EXTENSION",
    "TABLESPACE",
)
# Joined at import so that this source line does not itself match the rule it feeds.
DATABASE_ADMINISTRATION_SERVER_STATEMENT: Final = " ".join(("ALTER", "SYSTEM"))


@dataclass(frozen=True, slots=True)
class Import:
    line: int
    module: str
    names: tuple[str, ...]  # empty for ``import module``
    # One alias per name for ``from module import a as b``; ``(alias,)`` for ``import module as b``.
    asnames: tuple[str | None, ...] = ()


def report(findings: Iterable[Finding]) -> str:
    return "\n".join(finding.render() for finding in sorted(findings))


def iter_files(
    *roots: str, suffixes: frozenset[str], names: frozenset[str] = frozenset()
) -> Iterator[str]:
    """Repository-relative paths under ``roots`` whose suffix or file name matches, sorted."""
    for root in roots:
        base = ROOT / root
        if base.is_file():
            yield root
            continue
        for directory, subdirs, files in os.walk(base):
            subdirs[:] = sorted(name for name in subdirs if name not in PRUNED_DIRS)
            for name in sorted(files):
                if Path(name).suffix in suffixes or name in names:
                    yield (Path(directory) / name).relative_to(ROOT).as_posix()


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def module_name(path: str) -> str:
    """``backend/erev_api/db/session.py`` → ``erev_api.db.session``; packages drop ``__init__``."""
    parts = list(Path(path).with_suffix("").parts)
    if parts and parts[0] == "backend":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def imports(path: str, tree: ast.AST) -> list[Import]:
    """Every import of ``tree``, including nested and ``TYPE_CHECKING`` ones; relative imports
    are resolved against the package of ``path``."""
    package = module_name(path).split(".")
    if not path.endswith("__init__.py"):
        package = package[:-1]
    found: list[Import] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [Import(node.lineno, alias.name, (), (alias.asname,)) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package[: len(package) - (node.level - 1)]
                module = ".".join([*base, *([node.module] if node.module else [])])
            else:
                module = node.module or ""
            found.append(
                Import(
                    node.lineno,
                    module,
                    tuple(alias.name for alias in node.names),
                    tuple(alias.asname for alias in node.names),
                )
            )
    return sorted(found, key=lambda item: (item.line, item.module))


def callee(node: ast.Call) -> str | None:
    """The called name: ``text`` for ``text(...)`` and ``sa.text(...)``."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None
