"""POL-212 explains only the exact, evidenced unit conversion; raw values stay visible."""

from dataclasses import replace
from decimal import Decimal
from fractions import Fraction

import pytest
from erev_api.domain.migration import option_reconciliation, reconciliation
from erev_api.domain.migration.exact_values import ExactSourceError
from erev_engine.bundle import InputBundle
from support import bundles
from tests.domain.migration.test_option_opening_units import converted
from tests.engine.s03_pob_builder import test_s03_specialist as base


def evidence() -> InputBundle:
    opening = converted()
    value = bundles.minimal_contract()
    right = replace(
        base.voucher(),
        obligation_key="P1",
        ssp_method="ENTERED_AMOUNT",
        entered_ssp_amount=Decimal("25"),
        currency="USD",
    )
    header = replace(value.contracts[0], external_id=opening.external_id, material_rights=(right,))
    booked = replace(
        value.events[0],
        contract_key=opening.external_id,
        payload={"lines": [{"obligation_key": "P1", "quantity": "1", "product_code": "SYN-SKU"}]},
    )
    return replace(value, contracts=(header,), events=(booked,))


def test_exact_conversion_is_explained_but_values_and_difference_remain_visible() -> None:
    source = converted().rows[0].source
    index = option_reconciliation.explanations(
        reconciliation.DeviationIndex.empty(), [source], [evidence()]
    )
    key = (source.contract_external_id, source.obligation_key, "REMAINING_QTY")
    option_reconciliation.require_exact_quantities(index, {key: Fraction(2, 5)})
    (line,) = reconciliation.lines({key: Fraction(10)}, {key: Fraction(2, 5)}, index)
    assert line.source_value == 10 and line.erev_value == Fraction(2, 5)
    assert line.difference == Fraction(-48, 5)
    assert not line.is_within_tolerance
    assert line.deviation_ref == option_reconciliation.REFERENCE and not line.needs_exception
    assert source.values["Current Remaining Qty"] == "10"
    assert reconciliation.control_totals([line]).unexplained == 0


@pytest.mark.parametrize("actual", ["0.40000001", "0.39", "10", "0"])
def test_conversion_does_not_explain_incorrect_native_quantity(actual: str) -> None:
    source = converted().rows[0].source
    index = option_reconciliation.explanations(
        reconciliation.DeviationIndex.empty(), [source], [evidence()]
    )
    key = (source.contract_external_id, source.obligation_key, "REMAINING_QTY")
    with pytest.raises(ExactSourceError, match="exact POL-212"):
        option_reconciliation.require_exact_quantities(index, {key: Fraction(actual)})


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "ambiguous",
        "keep",
        "wrong_ssp",
        "wrong_currency",
        "no_terms",
        "no_booking",
        "wrong_product",
        "wrong_quantity",
        "malformed_quantity",
    ],
)
def test_missing_or_inconsistent_capture_never_explains_a_conversion(fault: str) -> None:
    source = converted().rows[0].source
    value = evidence()
    header = value.contracts[0]
    right = header.material_rights[0]
    if fault == "keep":
        right = replace(right, is_legacy_quantity_ssp_dollars=True)
    elif fault == "wrong_ssp":
        right = replace(right, entered_ssp_amount=Decimal("24"))
    elif fault == "wrong_currency":
        right = replace(right, currency="EUR")
    header = replace(header, material_rights=() if fault == "no_terms" else (right,))
    value = replace(
        value, contracts=(header,), events=() if fault == "no_booking" else value.events
    )
    if fault in {"wrong_product", "wrong_quantity", "malformed_quantity"}:
        line = dict(value.events[0].payload["lines"][0])  # type: ignore[index]
        if fault == "wrong_product":
            line["product_code"] = "FOREIGN"
        else:
            line["quantity"] = "25" if fault == "wrong_quantity" else "invalid"
        value = replace(value, events=(replace(value.events[0], payload={"lines": [line]}),))
    found = [] if fault == "missing" else [value, value] if fault == "ambiguous" else [value]
    index = option_reconciliation.explanations(
        reconciliation.DeviationIndex.empty(), [source], found
    )
    assert not index.refs


def test_conversion_never_explains_a_money_difference() -> None:
    source = converted().rows[0].source
    index = option_reconciliation.explanations(
        reconciliation.DeviationIndex.empty(), [source], [evidence()]
    )
    key = (source.contract_external_id, source.obligation_key, "REVENUE_CUM")
    (line,) = reconciliation.lines({key: Fraction(15)}, {key: Fraction(16)}, index)
    assert line.needs_exception and line.deviation_ref is None


def test_conflicting_quantity_explanation_is_not_silently_preferred() -> None:
    source = converted().rows[0].source
    key = (source.contract_external_id, source.obligation_key, "REMAINING_QTY")
    prior = reconciliation.DeviationIndex(
        {key: reconciliation.Deviation("EXISTING", Fraction(10), Fraction(10))}
    )
    with pytest.raises(ExactSourceError, match="conflicting quantity"):
        option_reconciliation.explanations(prior, [source], [evidence()])
