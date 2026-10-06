"""Decision-table rules (04 T-REF-26; ENGINE_SPEC S03-R-02, S05-R-02; BS1-D-05; EKC-5)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_engine.enums import RuleSetKind
from erev_engine.rules import FIELDS, OPERATORS, RuleMatch, match, validate_conditions

LINE_FACTS = (
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


@dataclass(frozen=True, slots=True)
class _Rule:
    rule_key: str
    priority: int
    specificity: int
    conditions: tuple[Mapping[str, object], ...]
    outputs: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _RuleSet:
    kind: str
    rules: tuple[_Rule, ...]


def _cond(field: str, op: str, value: object) -> dict[str, object]:
    return {"field": field, "op": op, "value": value}


def _rule(
    key: str,
    *conditions: Mapping[str, object],
    priority: int = 0,
    outputs: Mapping[str, object] | None = None,
) -> _Rule:
    specificity = len({condition["field"] for condition in conditions})
    return _Rule(key, priority, specificity, conditions, outputs or {"pob_template_code": key})


def _holds(kind: str, condition: Mapping[str, object], facts: Mapping[str, object]) -> bool:
    return match(_RuleSet(kind, (_rule("R", condition),)), facts) is not None


def test_fields_per_kind() -> None:
    assert tuple(FIELDS) == tuple(RuleSetKind)
    assert FIELDS["POB_ASSIGNMENT"] == LINE_FACTS
    assert FIELDS["SSP_ASSIGNMENT"] == FIELDS["POB_ASSIGNMENT"]
    assert FIELDS["APPROVAL_ROUTING"] == (
        "subject.type",
        "entity.code",
        "amount.functional",
        "flags",
    )
    # BUILD_SPEC BS4-D-09: CLO-17 added the three reconciliation facts after the PLF-12 fields.
    assert FIELDS["AUTO_APPROVAL"] == (
        "subject.type",
        "preparer.role_codes",
        "tenant.setup_completed",
        "source.channel",
        "reconciliation.kind",
        "reconciliation.variance_count",
        "reconciliation.unexplained_other_amount",
    )
    for names in FIELDS.values():
        assert isinstance(names, tuple)
        assert len(set(names)) == len(names)
    with pytest.raises(TypeError):
        FIELDS["HOLD"] = ("product.code",)  # type: ignore[index]
    assert OPERATORS == ("eq", "in", "range", "prefix", "gte", "lte")


def test_match_most_specific_then_priority_then_key() -> None:
    r1 = _rule("R1", _cond("product.code", "eq", "SKU-1"), outputs={"pob_template_code": "TPL-A"})
    r2 = _rule(
        "R2",
        _cond("product.code", "eq", "SKU-1"),
        _cond("contract.region", "eq", "EMEA"),
        outputs={"pob_template_code": "TPL-B"},
    )
    pob = _RuleSet("POB_ASSIGNMENT", (r1, r2))
    emea = {"product.code": "SKU-1", "contract.region": "EMEA"}
    assert match(pob, emea) == RuleMatch("R2", 0, 2, {"pob_template_code": "TPL-B"})
    assert match(_RuleSet("POB_ASSIGNMENT", (r2, r1)), emea) == match(pob, emea)
    chosen = match(pob, {"product.code": "SKU-1", "contract.region": "APAC"})
    assert chosen == RuleMatch("R1", 0, 1, {"pob_template_code": "TPL-A"})
    assert match(pob, {"product.code": "SKU-2", "contract.region": "EMEA"}) is None

    # Equal specificity: the greater priority wins over the smaller rule key.
    low = _rule("A-LOW", _cond("contract.region", "eq", "EMEA"), priority=1)
    high = _rule("Z-HIGH", _cond("product.code", "eq", "SKU-1"), priority=5)
    chosen = match(_RuleSet("POB_ASSIGNMENT", (low, high)), emea)
    assert chosen is not None and chosen.rule_key == "Z-HIGH"

    # Equal specificity and priority: the ascending rule key wins (S05-R-02 evaluates alike).
    books = _RuleSet(
        "SSP_ASSIGNMENT",
        (
            _rule("R-B", _cond("contract.currency", "eq", "USD"), outputs={"ssp_book_code": "B"}),
            _rule("R-A", _cond("product.code", "eq", "SKU-1"), outputs={"ssp_book_code": "A"}),
        ),
    )
    chosen = match(books, {"product.code": "SKU-1", "contract.currency": "USD"})
    assert chosen == RuleMatch("R-A", 0, 1, {"ssp_book_code": "A"})

    # A rule without conditions is the catch-all of specificity 0.
    fallback = _rule("DEFAULT", priority=100)
    chosen = match(_RuleSet("POB_ASSIGNMENT", (fallback, r1)), {"product.code": "SKU-3"})
    assert chosen is not None and chosen.rule_key == "DEFAULT"
    chosen = match(_RuleSet("POB_ASSIGNMENT", (fallback, r1)), {"product.code": "SKU-1"})
    assert chosen is not None and chosen.rule_key == "R1"


def test_operators() -> None:
    pob = "POB_ASSIGNMENT"
    term = _cond("effective_date", "range", ["2026-01-01", "2027-01-01"])
    assert _holds(pob, term, {"effective_date": date(2026, 1, 1)})
    assert _holds(pob, term, {"effective_date": date(2026, 12, 31)})
    assert not _holds(pob, term, {"effective_date": date(2027, 1, 1)})
    assert not _holds(pob, term, {"effective_date": date(2025, 12, 31)})
    open_upper = _cond("effective_date", "range", [date(2026, 1, 1), None])
    assert _holds(pob, open_upper, {"effective_date": date(2099, 1, 1)})

    kit = _cond("product.code", "prefix", "AVM-")
    assert _holds(pob, kit, {"product.code": "AVM-KIT"})
    assert not _holds(pob, kit, {"product.code": "XAVM-KIT"})

    currencies = _cond("contract.currency", "in", ["USD", "EUR"])
    assert _holds(pob, currencies, {"contract.currency": "EUR"})
    assert not _holds(pob, currencies, {"contract.currency": "GBP"})

    exact = _cond("product.code", "eq", "SKU-1")
    assert _holds(pob, exact, {"product.code": "SKU-1"})
    assert not _holds(pob, exact, {"product.code": "sku-1"})
    assert not _holds(pob, exact, {})
    assert not _holds(pob, exact, {"product.code": None})

    routing = "APPROVAL_ROUTING"
    large = _cond("amount.functional", "gte", "100000.00")
    assert _holds(routing, large, {"amount.functional": Decimal("100000.00")})
    assert not _holds(routing, large, {"amount.functional": Decimal("99999.99")})
    small = _cond("amount.functional", "lte", 100000)
    assert _holds(routing, small, {"amount.functional": Fraction(200000, 2)})
    assert not _holds(routing, small, {"amount.functional": Decimal("100000.0001")})
    assert _holds(routing, _cond("flags", "eq", "LARGE"), {"flags": frozenset({"LARGE", "FX"})})

    auto = "AUTO_APPROVAL"
    bootstrap = _cond("tenant.setup_completed", "eq", False)
    assert _holds(auto, bootstrap, {"tenant.setup_completed": False})
    assert not _holds(auto, bootstrap, {"tenant.setup_completed": True})
    admin = _cond("preparer.role_codes", "in", ["tenant_admin"])
    assert _holds(auto, admin, {"preparer.role_codes": ("viewer", "tenant_admin")})
    assert not _holds(auto, admin, {"preparer.role_codes": ("viewer",)})

    assert validate_conditions(pob, [exact, kit, _cond("contract.region", "eq", "EMEA")]) == 2


@pytest.mark.parametrize(
    ("kind", "conditions", "facts"),
    [
        (
            "POB_ASSIGNMENT",
            [_cond("customer.name", "eq", "Avenmoor")],
            {},
        ),  # field absent from FIELDS[kind]
        ("POB_ASSIGNMENT", [_cond("amount.functional", "gte", "1")], {}),  # another kind's field
        # no fields defined yet (HOLD takes the line facts since BUILD_SPEC CTR-10)
        ("DATA_QUALITY", [_cond("product.code", "eq", "AVM-KIT")], {}),
        ("POB_ASSIGNMENT", [_cond("product.code", "ne", "SKU-1")], {}),  # unknown operator
        ("POB_ASSIGNMENT", [{"field": "product.code", "op": "eq"}], {}),  # missing value
        ("POB_ASSIGNMENT", [_cond("effective_date", "range", ["2026-01-01"])], {}),
        ("POB_ASSIGNMENT", [_cond("effective_date", "range", [None, None])], {}),
        ("POB_ASSIGNMENT", [_cond("contract.currency", "in", [])], {}),
        ("POB_ASSIGNMENT", [_cond("product.code", "prefix", 5)], {}),
        ("PRICING", [], {}),  # unknown kind
    ],
)
def test_malformed_conditions_raise_value_error(
    kind: str, conditions: list[Mapping[str, object]], facts: Mapping[str, object]
) -> None:
    with pytest.raises(ValueError):
        validate_conditions(kind, conditions)
    rules = (_Rule("R", 0, len({c.get("field") for c in conditions}), tuple(conditions), {}),)
    with pytest.raises(ValueError):
        match(_RuleSet(kind, rules), facts)


def test_malformed_rules_and_facts() -> None:
    pob = "POB_ASSIGNMENT"
    exact = _cond("product.code", "eq", "SKU-1")
    with pytest.raises(ValueError, match="not POB_ASSIGNMENT fields"):
        match(_RuleSet(pob, (_rule("R", exact),)), {"customer.name": "Avenmoor"})
    wrong_specificity = _Rule("R", 0, 2, (exact,), {})
    with pytest.raises(ValueError, match="specificity"):
        match(_RuleSet(pob, (wrong_specificity,)), {"product.code": "SKU-1"})
    with pytest.raises(ValueError, match="repeated"):
        match(_RuleSet(pob, (_rule("R", exact), _rule("R", exact))), {})
    with pytest.raises(ValueError, match="does not match the fact type"):
        _holds(pob, _cond("product.code", "eq", 5), {"product.code": "SKU-1"})
    with pytest.raises(ValueError, match="does not match the fact type"):
        _holds(
            "AUTO_APPROVAL",
            _cond("tenant.setup_completed", "eq", "false"),
            {"tenant.setup_completed": False},
        )
    with pytest.raises(ValueError, match="collection"):
        _holds("APPROVAL_ROUTING", _cond("flags", "prefix", "LA"), {"flags": ("LARGE",)})
    with pytest.raises(TypeError):
        validate_conditions("APPROVAL_ROUTING", [_cond("amount.functional", "gte", 0.5)])
    with pytest.raises(TypeError):
        _holds(
            "APPROVAL_ROUTING", _cond("amount.functional", "gte", "1"), {"amount.functional": 0.5}
        )
    with pytest.raises(TypeError):
        _holds(
            pob,
            _cond("effective_date", "gte", "2026-01-01"),
            {"effective_date": datetime(2026, 1, 1, 12)},
        )
    # A malformed later rule raises even though an earlier rule matches.
    bad = _Rule("R-BAD", 0, 1, (_cond("product.code", "eq", 7),), {})
    with pytest.raises(ValueError):
        match(_RuleSet(pob, (_rule("R-OK", exact), bad)), {"product.code": "SKU-1"})
