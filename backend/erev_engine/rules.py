"""Decision-table rule evaluation (04 T-REF-26; ENGINE_SPEC S03-R-02, S05-R-02; BUILD_SPEC EKC-5).

A rule set of kind E-55 holds rules with ``conditions`` (``field``, ``op``, ``value``) and
kind-specific ``outputs``. A rule matches when every condition holds; the match with the greatest
specificity wins, then the greatest ``priority``, then the ascending ``rule_key`` (S03-R-02;
S05-R-02 evaluates ``SSP_ASSIGNMENT`` the same way). The rule set is read through read-only
protocols, so any frozen dataclass with the ``RuleSetInput`` and ``RuleInput`` fields of
ENGINE_SPEC §0.4 satisfies them.

Malformed rules or facts raise ``ValueError`` or ``TypeError`` (CV-45); a float anywhere raises
``TypeError`` (DG-ENG-03). Standard library only (DG-ARC-02).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction
from types import MappingProxyType
from typing import Final, Protocol

from erev_engine.enums import RuleSetKind
from erev_engine.money import to_fraction

__all__ = [
    "FIELDS",
    "OPERATORS",
    "RuleLike",
    "RuleMatch",
    "RuleSetLike",
    "match",
    "validate_conditions",
]

# Facts of a booking line (04 T-REF-26; S03-R-02); SSP book selection uses them too (S05-R-02).
_LINE_FACTS: Final = (
    "product.code",
    "product.product_family",
    "bundle_parent.code",
    "contract.region",
    "contract.channel",
    "customer.segment",
    "contract.contract_type",
    "line.term_band",
    "contract.currency",
    "effective_date",
)

# Allowed condition fields per E-55 kind. APPROVAL_ROUTING and AUTO_APPROVAL carry the BS1-D-05
# entries; later items extend kinds additively. A kind without fields takes no condition.
# BS4-D-09 (BUILD_SPEC CLO-17; 03 REQ-CLS-017): the three ``reconciliation.*`` facts of an
# auto-certification rule such as ``AUTO-REC-01``.
FIELDS: Final[Mapping[str, tuple[str, ...]]] = MappingProxyType(
    {
        RuleSetKind.POB_ASSIGNMENT: _LINE_FACTS,
        RuleSetKind.SSP_ASSIGNMENT: _LINE_FACTS,
        RuleSetKind.APPROVAL_ROUTING: ("subject.type", "entity.code", "amount.functional", "flags"),
        RuleSetKind.AUTO_APPROVAL: (
            "subject.type",
            "preparer.role_codes",
            "tenant.setup_completed",
            "source.channel",
            "reconciliation.kind",
            "reconciliation.variance_count",
            "reconciliation.unexplained_other_amount",
        ),
        RuleSetKind.COMBINATION_DETECTION: (),
        # BUILD_SPEC CTR-10 (REQ-POL-010): user hold rules match booking lines; additive.
        RuleSetKind.HOLD: _LINE_FACTS,
        RuleSetKind.DATA_QUALITY: (),
    }
)

OPERATORS: Final = ("eq", "in", "range", "prefix", "gte", "lte")

_ISO_DATE: Final = re.compile(r"\d{4}-\d{2}-\d{2}")


class RuleLike(Protocol):
    """The ``RuleInput`` fields evaluation reads (ENGINE_SPEC §0.4; 04 T-REF-26)."""

    @property
    def rule_key(self) -> str: ...

    @property
    def priority(self) -> int: ...

    @property
    def specificity(self) -> int: ...

    @property
    def conditions(self) -> Sequence[Mapping[str, object]]: ...

    @property
    def outputs(self) -> Mapping[str, object]: ...


class RuleSetLike(Protocol):
    """The ``RuleSetInput`` fields evaluation reads (ENGINE_SPEC §0.4; 04 T-REF-25)."""

    @property
    def kind(self) -> str: ...

    @property
    def rules(self) -> Sequence[RuleLike]: ...


@dataclass(frozen=True, slots=True)
class RuleMatch:
    """The chosen rule; trace params record ``rule_key`` (S03-R-02)."""

    rule_key: str
    priority: int
    specificity: int
    outputs: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _Condition:
    field: str
    op: str
    # eq, gte, lte, prefix: one operand; in: the members; range: (lower, upper), None = unbounded.
    operands: tuple[object, ...]


def validate_conditions(kind: str, conditions: Sequence[Mapping[str, object]]) -> int:
    """Validate ``conditions`` for ``kind`` and return their specificity (distinct fields).

    Unknown kinds, fields outside ``FIELDS[kind]``, unknown operators and malformed values raise
    ``ValueError``; float or datetime values raise ``TypeError``.
    """
    parsed = _parse_all(RuleSetKind(kind), conditions)
    return len({condition.field for condition in parsed})


def match(rule_set: RuleSetLike, facts: Mapping[str, object]) -> RuleMatch | None:
    """The most specific matching rule of ``rule_set`` for ``facts``, or ``None``.

    A fact that is absent or ``None`` fails every condition on it. Every rule is validated, so a
    malformed rule raises even when another rule matches.
    """
    kind = RuleSetKind(rule_set.kind)
    allowed = FIELDS[kind]
    unknown = sorted(name for name in facts if name not in allowed)
    if unknown:
        raise ValueError(f"facts {unknown} are not {kind} fields")
    best: tuple[tuple[int, int, str], RuleMatch] | None = None
    keys: set[str] = set()
    for rule in rule_set.rules:
        key = rule.rule_key
        if not isinstance(key, str) or key in keys:
            raise ValueError(f"rule key {key!r} is malformed or repeated")
        keys.add(key)
        if isinstance(rule.priority, bool) or not isinstance(rule.priority, int):
            raise TypeError(f"rule {key} priority must be an int")
        conditions = _parse_all(kind, rule.conditions)
        specificity = len({condition.field for condition in conditions})
        if rule.specificity != specificity:
            raise ValueError(
                f"rule {key} declares specificity {rule.specificity}, "
                f"but its conditions name {specificity} fields"
            )
        results = [_holds(condition, facts) for condition in conditions]
        if not all(results):
            continue
        rank = (-specificity, -rule.priority, key)
        if best is None or rank < best[0]:
            best = (rank, RuleMatch(key, rule.priority, specificity, dict(rule.outputs)))
    return None if best is None else best[1]


def _parse_all(kind: RuleSetKind, conditions: Sequence[Mapping[str, object]]) -> list[_Condition]:
    if isinstance(conditions, str | bytes) or not isinstance(conditions, Sequence):
        raise TypeError("conditions must be a sequence of mappings")
    return [
        _parse(condition, kind, f"conditions[{index}]")
        for index, condition in enumerate(conditions)
    ]


def _parse(condition: object, kind: RuleSetKind, where: str) -> _Condition:
    if not isinstance(condition, Mapping) or set(condition) != {"field", "op", "value"}:
        raise ValueError(f"{where} must be a mapping with exactly field, op and value")
    field, op, value = condition["field"], condition["op"], condition["value"]
    if not isinstance(field, str) or field not in FIELDS[kind]:
        raise ValueError(f"{where}.field {field!r} is not a {kind} field")
    if op not in OPERATORS:
        raise ValueError(f"{where}.op {op!r} is not one of {', '.join(OPERATORS)}")
    if op in ("in", "range"):
        if isinstance(value, str | bytes) or not isinstance(value, Sequence):
            raise ValueError(f"{where}.value must be a list for {op}")
        operands = tuple(value)
        if op == "in" and not operands:
            raise ValueError(f"{where}.value must list at least one member")
        if op == "range" and (len(operands) != 2 or operands == (None, None)):
            raise ValueError(f"{where}.value must be [lower, upper] with at least one bound")
        for operand in operands:
            if op == "in" or operand is not None:
                _check_operand(operand, where)
        return _Condition(field, op, operands)
    _check_operand(value, where)
    if op == "prefix" and not isinstance(value, str):
        raise ValueError(f"{where}.value must be a string for prefix")
    return _Condition(field, op, (value,))


def _check_operand(value: object, where: str) -> None:
    if isinstance(value, float | datetime):
        raise TypeError(f"{where}.value holds a {type(value).__qualname__}")
    if not isinstance(value, str | int | Decimal | Fraction | date):
        raise ValueError(f"{where}.value holds an unsupported {type(value).__qualname__}")


def _holds(condition: _Condition, facts: Mapping[str, object]) -> bool:
    fact = facts.get(condition.field)
    if fact is None:
        return False
    op, operands = condition.op, condition.operands
    if isinstance(fact, list | tuple | set | frozenset):
        if op not in ("eq", "in"):
            raise ValueError(
                f"operator {op} does not apply to the collection fact {condition.field}"
            )
        members = sorted(fact, key=str) if isinstance(fact, set | frozenset) else list(fact)
        return any(_equal(m, o, condition.field) for m in members for o in operands)
    if op in ("eq", "in"):
        return any(_equal(fact, operand, condition.field) for operand in operands)
    if op == "prefix":
        if not isinstance(fact, str):
            raise ValueError(f"prefix needs a string fact for {condition.field}")
        prefix = operands[0]
        return isinstance(prefix, str) and fact.startswith(prefix)
    if op == "gte":
        return _order(fact, operands[0], condition.field) >= 0
    if op == "lte":
        return _order(fact, operands[0], condition.field) <= 0
    lower, upper = operands
    return (lower is None or _order(fact, lower, condition.field) >= 0) and (
        upper is None or _order(fact, upper, condition.field) < 0
    )


def _normalise(fact: object, operand: object, field: str) -> tuple[object, object]:
    """``fact`` and ``operand`` as comparable values of one type."""
    mismatch = f"the condition value for {field} does not match the fact type"
    if isinstance(fact, float | datetime):
        raise TypeError(f"fact {field} holds a {type(fact).__qualname__}")
    if isinstance(fact, bool) or isinstance(operand, bool):
        if isinstance(fact, bool) and isinstance(operand, bool):
            return fact, operand
        raise ValueError(mismatch)
    if isinstance(fact, date):
        if isinstance(operand, str) and _ISO_DATE.fullmatch(operand):
            return fact, date.fromisoformat(operand)
        if isinstance(operand, date) and not isinstance(operand, datetime):
            return fact, operand
        raise ValueError(mismatch)
    if isinstance(fact, int | Decimal | Fraction):
        if isinstance(operand, str | int | Decimal | Fraction):
            return to_fraction(fact), to_fraction(operand)
        raise ValueError(mismatch)
    if isinstance(fact, str):
        if isinstance(operand, str):
            return fact, operand
        raise ValueError(mismatch)
    raise TypeError(f"fact {field} holds an unsupported {type(fact).__qualname__}")


def _equal(fact: object, operand: object, field: str) -> bool:
    left, right = _normalise(fact, operand, field)
    return left == right


def _order(fact: object, operand: object, field: str) -> int:
    left, right = _normalise(fact, operand, field)
    if isinstance(left, bool):
        raise ValueError(f"fact {field} is not ordered")
    if isinstance(left, Fraction) and isinstance(right, Fraction):
        return (left > right) - (left < right)
    if isinstance(left, date) and isinstance(right, date):
        return (left > right) - (left < right)
    if isinstance(left, str) and isinstance(right, str):
        return (left > right) - (left < right)
    raise ValueError(f"fact {field} is not ordered")
