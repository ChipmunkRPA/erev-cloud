"""ISO 4217 table (dev-guide §5.9 DG-KRN-MONEY-04; BUILD_SPEC FND-7, EKC-1)."""

from __future__ import annotations

import ast
import dataclasses
import re
from pathlib import Path

import pytest
from erev_engine.currencies import ISO_4217, CurrencySpec

SEED_REVISION = (
    Path(__file__).resolve().parents[3]
    / "erev_api/db/migrations/versions/0002_global_catalogues.py"
)


def _currency_seed_call() -> ast.Call:
    tree = ast.parse(SEED_REVISION.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "insert_rows"
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "currency"
        ):
            return node
    raise AssertionError("T-REF-08 seed call not found")


def test_iso_4217_minor_units() -> None:
    assert ISO_4217["JPY"].minor_unit == 0
    assert ISO_4217["USD"].minor_unit == 2
    assert ISO_4217["EUR"].minor_unit == 2
    assert ISO_4217["BHD"].minor_unit == 3
    assert ISO_4217["CLF"].minor_unit == 4
    for code, currency in ISO_4217.items():
        assert re.fullmatch(r"^[A-Z]{3}$", code)
        assert currency.code == code
        assert re.fullmatch(r"^[0-9]{3}$", currency.numeric_code)
        assert 1 <= len(currency.name) <= 400
        assert 0 <= currency.minor_unit <= 4
    # The T-REF-08 seed inserts exactly these rows; pg/test_global_catalogues.py reads them back.
    seed = _currency_seed_call()
    assert ast.literal_eval(seed.args[1]) == ("code", "numeric_code", "name", "minor_unit")
    rows = seed.args[2]
    assert isinstance(rows, ast.ListComp)
    assert ast.unparse(rows.generators[0].iter) == "ISO_4217.values()"
    assert ast.unparse(rows.elt) == "(c.code, c.numeric_code, c.name, c.minor_unit)"


def test_iso_4217_is_sorted_and_immutable() -> None:
    assert list(ISO_4217) == sorted(ISO_4217)
    with pytest.raises(TypeError):
        ISO_4217["ZZZ"] = CurrencySpec(code="ZZZ", numeric_code="999", name="Probe", minor_unit=2)  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        ISO_4217["USD"].minor_unit = 3  # type: ignore[misc]
