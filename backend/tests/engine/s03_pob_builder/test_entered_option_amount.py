"""Explicit option SSP is local to its obligation, with replayable input evidence."""

import json
from dataclasses import fields, replace
from decimal import Decimal

import pytest
from erev_engine.bundle import InputBundle
from erev_engine.canonical import sha256_hex
from erev_engine.trace import TRACE_FORMAT_VERSION, Trace, reevaluate
from erev_engine.upgrade import decode_input, encode_input
from tests.engine.s03_pob_builder import test_s03_specialist as base


def entered_world(amount: str | None) -> InputBundle:
    value = base.ex_03_b()
    right = replace(
        base.voucher(),
        ssp_method="ENTERED_AMOUNT",
        entered_ssp_amount=None if amount is None else Decimal(amount),
    )
    return replace(value, contracts=(replace(value.contracts[0], material_rights=(right,)),))


@pytest.mark.parametrize(
    "amount,allocations", [("25", [8000, 2000]), ("100", [5000, 5000]), ("0", [10000, 0])]
)
def test_explicit_amount_drives_allocation_without_changing_catalogue(
    amount: str, allocations: list[int]
) -> None:
    value = entered_world(amount)
    pob, _, allocated, nodes = base.fold(value)
    assert base.by_key(pob)["POB-02"].option_ssp == Decimal(amount)
    assert allocated is not None
    assert [ob.original_allocation.a_posted for ob in allocated.obligations] == allocations
    assert value.ssp_versions == base.ex_03_b().ssp_versions
    node = nodes["option_ssp:K-01/POB-02:-"]
    assert node.params["entered_ssp_amount"] == amount
    trace = Trace(TRACE_FORMAT_VERSION, value.engine_version, tuple(nodes.values()), {})
    assert reevaluate(trace) == {key: item.value for key, item in nodes.items()}
    assert all(getattr(ref, "ref_type", None) != "ssp_entry" for ref in node.inputs)
    restored = decode_input(encode_input(value))
    assert restored.sha256() == value.sha256()
    assert base.fold(restored)[3] == nodes


def test_absent_amount_preserves_pre_extension_input_hash() -> None:
    value = entered_world(None)
    old_view = {field.name: getattr(value, field.name) for field in fields(value)}
    del old_view["known_at"]
    old_view["contracts"] = tuple(
        {
            **{field.name: getattr(contract, field.name) for field in fields(contract)},
            "material_rights": tuple(
                {
                    field.name: getattr(right, field.name)
                    for field in fields(right)
                    if field.name != "entered_ssp_amount"
                }
                for right in contract.material_rights
            ),
        }
        for contract in value.contracts
    )
    old_view["ssp_versions"] = tuple(item.hash_view() for item in value.ssp_versions)
    old_view["estimate_versions"] = tuple(item.hash_view() for item in value.estimate_versions)
    old_view["posted"] = tuple(item.hash_view() for item in value.posted)
    assert value.sha256() == sha256_hex(old_view)
    assert len({value.sha256(), entered_world("0").sha256(), entered_world("25").sha256()}) == 3
    pob, _ = base.pob_only(value)
    assert base.by_key(pob)["POB-02"].option_ssp == 0


@pytest.mark.parametrize("amount", ["-1", "NaN", "Infinity"])
def test_invalid_amount_refused(amount: str) -> None:
    with pytest.raises(ValueError):
        base.pob_only(entered_world(amount))


@pytest.mark.parametrize("changes", [{"ssp_method": "DISCOUNT_X_LIKELIHOOD"}, {"currency": "EUR"}])
def test_incompatible_terms_refused(changes: dict[str, str]) -> None:
    value = entered_world("25")
    contract = value.contracts[0]
    right = replace(
        contract.material_rights[0],
        ssp_method=changes.get("ssp_method", "ENTERED_AMOUNT"),
        currency=changes.get("currency", "USD"),
    )
    with pytest.raises(ValueError):
        base.pob_only(replace(value, contracts=(replace(contract, material_rights=(right,)),)))


@pytest.mark.parametrize("book", base.BOTH_BOOKS)
def test_two_options_share_catalogue_without_sharing_entered_amount(book: str) -> None:
    source = entered_world("25")
    first = source.contracts[0].material_rights[0]
    second = replace(first, obligation_key="POB-03", entered_ssp_amount=Decimal("75"))
    value = base.world(
        base.booked(
            base.line("POB-01", "SKU-A", "100.00"),
            base.line("POB-02", "VOUCHER", "0.00"),
            base.line("POB-03", "VOUCHER", "0.00"),
        ),
        products=source.group.products,
        templates=source.pob_template_versions,
        contract=replace(source.contracts[0], material_rights=(first, second)),
        ssp=source.ssp_versions,
        books=base.BOTH_BOOKS,
    )
    _, _, allocated, nodes = base.fold(value, book)
    assert allocated is not None and allocated.findings == ()
    assert [ob.original_allocation.a_posted for ob in allocated.obligations] == [5000, 1250, 3750]
    assert nodes["option_ssp:K-01/POB-02:-"].value == "25.00"
    assert nodes["option_ssp:K-01/POB-03:-"].value == "75.00"
    assert value.ssp_versions == source.ssp_versions


def test_pre_extension_evidence_decodes_with_same_hash() -> None:
    value = entered_world(None)
    encoded = json.loads(encode_input(value))
    for contract in encoded["bundle"]["contracts"]:
        for right in contract["material_rights"]:
            del right["entered_ssp_amount"]
    restored = decode_input(json.dumps(encoded).encode())
    assert restored == value
    assert restored.sha256() == value.sha256()


def test_entered_ssp_is_total_not_per_unit() -> None:
    value = entered_world("25")
    booking = base.booked(
        base.line("POB-01", "SKU-A", "100.00"), base.line("POB-02", "VOUCHER", "0.00", quantity="5")
    )
    value = replace(value, events=(booking, *value.events[1:]))
    pob, _, allocated, _ = base.fold(value)
    assert base.by_key(pob)["POB-02"].quantity == 5
    assert base.by_key(pob)["POB-02"].option_ssp == 25
    assert allocated is not None
    assert [ob.original_allocation.a_posted for ob in allocated.obligations] == [8000, 2000]
