"""The engine's readers of the level P values no computation reads, held against the source: the
witness of ``reference.products.LEVEL_P_NOT_READ`` (item PRODUCT-POLICY-VALUE-NOT-READ-1, register
index 309; POLICIES §0.5 rule 1 rev 1.125; 04 T-REF-20 and T-REF-23 rev 1.323; PRD ERR-103).

A product and an obligation template are refused a value of three parameters because the engine
reads each of them for a contract, and bundle assembly gives a product's and a template's value
for an obligation (``tests/unit/policies/test_level_p_not_read.py`` holds that half on the
product's assembly). That is a statement about the engine's code, so it is read from the code:

* every read of the three through the policy resolver — ``policies.value``, ``.resolved``,
  ``.has`` — with the function that makes it and the scope it passes: the contract alone;
* every other place of the engine that names one of the three, by its literal or by a constant
  bound to it: the stages' declarations of the keys they read and the tables of stage 13, none
  of which takes a value for a rule. A read that went round the resolver, or a reader that is
  handed the key by another function, would name the key in a place that is not listed here.

WHEN THIS MODULE TURNS RED the door is looked at again. A reader that passes the obligation meets
the product's and the template's value: its parameter leaves ``LEVEL_P_NOT_READ`` by name, with
its sentence of PRD ERR-103 and its row of POLICIES §0.5 rule 1. A new place that only declares
the key joins the lists below.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from functools import cache
from pathlib import Path

from erev_api.domain.reference import products

ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / "backend" / "erev_engine"
TIER = "usage.tier_minimum_method"  # POL-240
BENEFIT = "upfront_fee.recognition_period"  # POL-029
SHIPPING = "pob.shipping_as_fulfilment"  # POL-021
THE_SET = frozenset({TIER, BENEFIT, SHIPPING})
RESOLVER_READS = frozenset({"value", "resolved", "has"})
# (parameter, module under erev_engine, function, resolver method, the scope passed)
Read = tuple[str, str, str, str, tuple[str, ...]]
# (parameter, module under erev_engine, function or <module>, "literal" or the constant's name)
Naming = tuple[str, str, str, str]

READS: tuple[Read, ...] = (
    (SHIPPING, "stages/s03_pob_builder/elections.py", "shipping", "value", ("contract",)),
    (BENEFIT, "stages/s03_pob_builder/options.py", "_benefit_period", "value", ("contract",)),
    (TIER, "stages/s04_transaction_price/buildup.py", "realised", "value", ("contract",)),
    (TIER, "stages/s04_transaction_price/vc.py", "elements", "value", ("contract",)),
    (TIER, "stages/s05_allocation/original.py", "_realised_component", "value", ("contract",)),
)
# Where the engine names the three: the five reads above, the constant each of two is bound to,
# and the declarations — ``POLICY_KEYS`` of a stage (CV-17: the bundle must hold the key), the
# stage keys of the memo (S13-R-04) and the IFRS switch table of stage 13 (S13-R-06).
NAMINGS: tuple[Naming, ...] = (
    (SHIPPING, "stages/s03_pob_builder/__init__.py", "<module>", "literal"),
    (SHIPPING, "stages/s03_pob_builder/elections.py", "shipping", "literal"),
    (SHIPPING, "stages/s13_books/memo.py", "<module>", "literal"),
    (SHIPPING, "stages/s13_books/switches.py", "<module>", "literal"),
    (BENEFIT, "stages/s03_pob_builder/__init__.py", "<module>", "literal"),
    (BENEFIT, "stages/s03_pob_builder/options.py", "<module>", "literal"),
    (BENEFIT, "stages/s03_pob_builder/options.py", "_benefit_period", "UPFRONT_FEE_POLICY"),
    (BENEFIT, "stages/s13_books/memo.py", "<module>", "literal"),
    (TIER, "stages/s04_transaction_price/__init__.py", "<module>", "literal"),
    (TIER, "stages/s04_transaction_price/buildup.py", "realised", "TIER_MINIMUM_POLICY"),
    (TIER, "stages/s04_transaction_price/vc.py", "elements", "literal"),
    (TIER, "stages/s05_allocation/original.py", "_realised_component", "TIER_MINIMUM_POLICY"),
    (TIER, "stages/s09_recognition/__init__.py", "<module>", "literal"),
    (TIER, "stages/s13_books/memo.py", "<module>", "literal"),
    (TIER, "stages/s13_books/memo.py", "<module>", "literal"),
    (TIER, "usage.py", "<module>", "literal"),
)


@cache
def _modules() -> dict[str, ast.Module]:
    """Every module of the engine, parsed, by its path under ``backend/erev_engine``."""
    return {
        path.relative_to(ENGINE).as_posix(): ast.parse(path.read_text(encoding="utf-8"))
        for path in sorted(ENGINE.rglob("*.py"))
    }


@cache
def _constants() -> dict[str, str]:
    """The module-level names of the engine that are bound to a key of the set, each with its
    key. Such a name is bound to nothing else anywhere in the engine, so a use of it — in its
    own module, or imported, or as ``module.NAME`` — is a naming of the key."""
    bound: dict[str, set[str]] = {}
    for tree in _modules().values():
        for node in tree.body:
            if isinstance(node, ast.AnnAssign):
                targets, value = [node.target], node.value
            elif isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            else:
                continue
            if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    bound.setdefault(target.id, set()).add(value.value)
    found = {name: values for name, values in bound.items() if values & THE_SET}
    assert all(len(values) == 1 for values in found.values()), found
    return {name: next(iter(values)) for name, values in found.items()}


def _key(node: ast.expr) -> tuple[str, str] | None:
    """The key of the set an expression names, with how: its literal, or a constant bound to it
    (``NAME`` or ``module.NAME``)."""
    if isinstance(node, ast.Constant) and node.value in THE_SET:
        return str(node.value), "literal"
    name = node.id if isinstance(node, ast.Name) else None
    if isinstance(node, ast.Attribute):
        name = node.attr
    if name is not None and name in _constants():
        return _constants()[name], name
    return None


def _walk(node: ast.AST, scope: tuple[str, ...]) -> Iterator[tuple[ast.AST, str]]:
    """Every node below ``node`` with the function that encloses it (``<module>`` for none)."""
    for child in ast.iter_child_nodes(node):
        inner = scope
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
            inner = (*scope, child.name)
        yield child, ".".join(inner) or "<module>"
        yield from _walk(child, inner)


def reads() -> list[Read]:
    """Every call of the policy resolver whose first argument names a key of the set."""
    found: list[Read] = []
    for module, tree in _modules().items():
        for node, function in _walk(tree, ()):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            receiver = ast.unparse(node.func.value)
            if node.func.attr not in RESOLVER_READS or "policies" not in receiver:
                continue
            named = _key(node.args[0]) if node.args else None
            if named is None:
                continue
            passed = tuple(
                f"**{ast.unparse(keyword.value)}" if keyword.arg is None else keyword.arg
                for keyword in node.keywords
            )
            found.append((named[0], module, function, node.func.attr, passed))
    return sorted(found)


def namings() -> list[Naming]:
    """Every place of the engine that names a key of the set: a literal, or a load of a constant
    bound to it. The assignment that binds the constant is the literal of its module."""
    found: list[Naming] = []
    for module, tree in _modules().items():
        for node, function in _walk(tree, ()):
            if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
                continue
            if not isinstance(node, ast.Constant | ast.Name | ast.Attribute):
                continue
            named = _key(node)
            if named is not None:
                found.append((named[0], module, function, named[1]))
    return sorted(found)


def test_the_door_and_this_witness_name_the_same_parameters() -> None:
    """A parameter joins or leaves the door's set with its witness."""
    assert set(products.LEVEL_P_NOT_READ) == THE_SET
    assert {read[0] for read in READS} == THE_SET
    assert _constants() == {"UPFRONT_FEE_POLICY": BENEFIT, "TIER_MINIMUM_POLICY": TIER}


def test_every_read_of_the_three_passes_the_contract_alone() -> None:
    """Five reads, each by the resolver's ``value`` with ``contract=`` and nothing else: the
    resolver takes an ``OBLIGATION`` row only for a read that passes ``obligation=``
    (``erev_engine.stages.state.PolicyResolver.resolved``), so none of them meets a value that a
    product or a template states."""
    found = reads()
    assert found == sorted(READS)
    for parameter, module, function, _method, passed in found:
        assert passed == ("contract",), (parameter, module, function)


def test_the_engine_names_the_three_nowhere_else() -> None:
    """Beside the five reads the engine names the three only where a stage declares the keys it
    needs in the bundle and in the tables of stage 13; a new naming is a new reader until it is
    read and listed."""
    assert namings() == sorted(NAMINGS)
