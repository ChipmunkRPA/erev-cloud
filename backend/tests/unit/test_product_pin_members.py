"""The product pin of a computation reproduces what it computed (security finding SN-7, supervisor
ruling R-21; 04 T-CON-07 ``pinned_refs.products`` rev 1.110; dev-guide DG-KRN-REG-02 rev 1.93; 05
RCP-15 rev 1.49; POLICIES §0.5 rule 3 pin K; 03 REQ-POL-007).

A product is a master-data row without versions, so a computation pins the value: the
``ProductInput`` it was computed with and the level-P values of the product's obligations.
``bundles.product_pin_members`` derives the member from the computed bundle, and the next bundle of
the group is built from it (``bundles.pinned_product``, ``bundles._policies``). These tests hold
the two halves together without a database: a pin written as JSON and read back gives the same
engine input, member for member and hash for hash. The database half — the pin read from the
group's latest SUCCEEDED computation, the DRAFT exception and the combination — is
``tests/domain/contracts/test_product_pins.py``.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import erev_engine
import pytest
from erev_api.domain.contracts import bundles
from erev_api.registry.resolve import ResolvedValue
from erev_engine.bundle import BundleComponentInput, InputBundle, OutputBundle, ProductInput
from erev_engine.canonical import sha256_hex
from erev_engine.stages.s01_canonicalize import obligation_subject_key
from support.answer_keys import runners
from support.answer_keys.loader import ANSWER_KEY_ROOT, load

# (answer key, a product it pins, what that product shows)
KEYS = (
    ("pob/POB-CHK-134-S2-WARRANTY-OWN", "EQUIP"),  # an assurance cost per unit
    ("pob/POB-S2-EX45-AGENT-AGENT", "MKT-ORDER"),  # an agent
    ("alc/ALC-CHK-002-GT01-GT03", "CONS-1"),  # level-P values on the product
    ("alc/ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT", "DAAS-SVC-36M"),  # values of its obligations
)


def _stored(pins: dict[str, Any]) -> dict[str, Any]:
    """The member as the jsonb column returns it."""
    stored: dict[str, Any] = json.loads(json.dumps(pins))
    return stored


def _computed(key: str) -> list[tuple[InputBundle, OutputBundle]]:
    loaded = load(ANSWER_KEY_ROOT / f"{key}.yaml")
    found = runners._build_checkpoint_bundles(loaded)[-1].bundles
    return [(bundle, erev_engine.compute(bundle)) for bundle in found]


def _obligation_policies(bundle: InputBundle) -> dict[str, dict[str, tuple[Any, str]]]:
    """Per obligation subject key, the OBLIGATION-scope policies of the bundle's first book."""
    found: dict[str, dict[str, tuple[Any, str]]] = {}
    for policy in bundle.books[0].policies:
        if policy.scope == "OBLIGATION":
            found.setdefault(policy.subject_key, {})[policy.code] = (
                policy.value,
                policy.source_ref,
            )
    return found


@pytest.mark.parametrize(("key", "code"), KEYS, ids=[key for key, _ in KEYS])
def test_sn7_the_pin_of_a_computation_reproduces_its_products(key: str, code: str) -> None:
    """For the last checkpoint of ``key``: every product the computation pins reads back as the
    ``ProductInput`` it was computed with (same canonical hash), and the level-P values pinned with
    a product are those of each of its obligations in the bundle."""
    pinned_codes: set[str] = set()
    for bundle, output in _computed(key):
        pins = _stored(bundles.product_pin_members(bundle, output))
        by_code = {item.code: item for item in bundle.group.products}
        pinned_codes |= set(pins)
        for pinned_code, pin in pins.items():
            restored = bundles.pinned_product(pinned_code, pin)
            assert restored == by_code[pinned_code]
            assert sha256_hex(restored) == sha256_hex(by_code[pinned_code])
        have = _obligation_policies(bundle)
        for contract_key, line in bundles._lines(bundle.events):
            pin = pins.get(str(line.get("product_code")))
            if pin is None:
                continue
            subject = obligation_subject_key(contract_key, str(line.get("obligation_key")))
            rebuilt = {
                name: (bundles._stored_value(item["value"]), str(item["source"]))
                for name, item in pin[bundles.OBLIGATION_POLICIES].items()
            }
            assert rebuilt == have.get(subject, {}), subject
    assert code in pinned_codes


def test_sn7_a_pinned_bundle_product_keeps_its_components_and_exact_decimals() -> None:
    """``product_pin`` and ``pinned_product`` are inverse for every member, the scale of a decimal
    included (the canonical hash of the bundle reads it), and a product without a computed line
    carries no ``obligation_policies`` member."""
    item = ProductInput(
        code="AVM-KIT",
        sku_number="K-100",
        product_family=None,
        revenue_category="PRODUCT",
        default_template_code="TPL-PROD-UNITS",
        principal_agent="PRINCIPAL",
        distinctness_default="distinct",
        unit_of_measure="EA",
        is_bundle=True,
        policy_values={"returns.model": "EXPECTED_VALUE", "costs.obtain_expedient": "false"},
        assurance_cost_per_unit=Decimal("12.500000000000"),
        components=(
            BundleComponentInput(
                "AVM-PART-A",
                Decimal("2.000000"),
                "fixed_percentage",
                Decimal("0.400000000000"),
                1,
                date(2026, 1, 1),
                None,
            ),
            BundleComponentInput(
                "AVM-PART-B",
                Decimal("1"),
                "fixed_percentage",
                Decimal("0.6"),
                2,
                date(2026, 1, 1),
                date(2027, 1, 1),
            ),
        ),
        is_franchisor_preopening_service=True,
    )
    pin = _stored({"AVM-KIT": bundles.product_pin(item, None)})["AVM-KIT"]
    assert bundles.OBLIGATION_POLICIES not in pin
    restored = bundles.pinned_product("AVM-KIT", pin)
    assert restored == item
    assert sha256_hex(restored) == sha256_hex(item)
    assert str(restored.assurance_cost_per_unit) == "12.500000000000"
    assert [str(component.quantity_per_bundle) for component in restored.components] == [
        "2.000000",
        "1",
    ]
    with_values = bundles.product_pin(
        item, {"recognition.time_convention": {"value": "DAILY", "source": "TPL-PROD-UNITS@v1"}}
    )
    assert with_values[bundles.OBLIGATION_POLICIES] == {
        "recognition.time_convention": {"value": "DAILY", "source": "TPL-PROD-UNITS@v1"}
    }
    assert bundles.product_pin(item, {})[bundles.OBLIGATION_POLICIES] == {}


def test_sn7_only_products_of_a_contract_past_draft_are_pinned() -> None:
    """``product_pin_members``: nothing is pinned while every member is DRAFT in every book — a
    repaired product must still reach a draft (REQ-REF-014) — and once a member is past DRAFT the
    member lists what that contract carries: its lines' products and the components of a bundle
    among them, but no product nothing of it carries."""
    ((bundle, output),) = _computed("pob/POB-CHK-134-S2-WARRANTY-OWN")
    carried = {str(line.get("product_code")) for _, line in bundles._lines(bundle.events)}
    assert set(bundles.product_pin_members(bundle, output)) == carried

    drafts = dataclasses.replace(
        output,
        books=tuple(
            dataclasses.replace(
                book, status_in_book=tuple((key, "DRAFT") for key, _ in book.status_in_book)
            )
            for book in output.books
        ),
    )
    assert bundles.product_pin_members(bundle, drafts) == {}

    # One carried product becomes a bundle of a part; a product no line names stands beside them.
    first = sorted(carried)[0]
    part = dataclasses.replace(
        next(item for item in bundle.group.products if item.code == first),
        code="ZZ-PART",
        components=(),
        is_bundle=False,
    )
    products = tuple(
        dataclasses.replace(
            item,
            is_bundle=True,
            components=(
                BundleComponentInput(
                    "ZZ-PART", Decimal("1"), "relative_ssp", None, 1, date(2020, 1, 1), None
                ),
            ),
        )
        if item.code == first
        else item
        for item in bundle.group.products
    )
    unrelated = dataclasses.replace(part, code="ZZ-UNRELATED")
    widened = dataclasses.replace(
        bundle, group=dataclasses.replace(bundle.group, products=(*products, part, unrelated))
    )
    pins = bundles.product_pin_members(widened, output)
    assert set(pins) == carried | {"ZZ-PART"}
    assert bundles.OBLIGATION_POLICIES in pins[first]
    assert bundles.OBLIGATION_POLICIES not in pins["ZZ-PART"]


def test_pin_k_a_parameter_the_recorded_values_do_not_hold_resolves_at_the_computation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item PIN-K-COMBINATION-1 (supervisor ruling R-112 (i); DG-KRN-REG-02 rev 1.143): the first
    version of a group inherits the recorded pin-K values of a member's former group. A parameter
    those values hold is read from them, whatever the registry answers now; one they do not hold
    — a parameter the registry gained since, say — resolves at this computation."""
    held, missing = "ssp.outside_range_point", "ssp.inside_range_point"
    asked: list[str] = []

    def answers_now(_session: object, code: str, **_scope: object) -> ResolvedValue:
        asked.append(code)
        return ResolvedValue(code=code, value="RESOLVED-NOW", level="T", source_id=None)

    monkeypatch.setattr(bundles.registry, "resolve", answers_now)
    resolved = bundles._policies(
        None,  # type: ignore[arg-type]  # the registry is the stub above
        book_code="ASC606",
        entity_id=None,
        entities=(),
        known_at=datetime(2026, 9, 12, 12, tzinfo=UTC),
        pinned={held: {"value": "NEAREST_BOUND", "level": "DEFAULT", "source_id": "POL-072"}},
        lines=(),
        product_rows={},
        template_values={},
    )
    at_group = {item.code: item for item in resolved if item.scope == "GROUP"}
    assert (at_group[held].value, at_group[held].level, at_group[held].source_ref) == (
        "NEAREST_BOUND",
        "DEFAULT",
        "POL-072",
    )
    assert (at_group[missing].value, at_group[missing].level) == ("RESOLVED-NOW", "T")
    assert held not in asked and missing in asked
