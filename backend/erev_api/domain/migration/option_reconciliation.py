"""Explain exact POL-212 unit changes without rewriting either reconciliation value."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import InvalidOperation
from fractions import Fraction

from erev_engine.bundle import InputBundle

from erev_api.domain.migration import field_mapping
from erev_api.domain.migration.exact_values import ExactSourceError
from erev_api.domain.migration.legacy_db import LegacyRow, decimal_of
from erev_api.domain.migration.reconciliation import Deviation, DeviationIndex, LineKey

REFERENCE = "POL-212:CONVERT_TO_OPTION_RECORD"


def explanations(
    index: DeviationIndex, latest: Iterable[LegacyRow], verified_bundles: Iterable[InputBundle]
) -> DeviationIndex:
    """Bind a quantity-only explanation to source facts and verified producing input.

    The caller must verify bundle hashes, batch/cutover, membership and event identity first.
    No bundle, absent/ambiguous terms, an unconverted booking or an unequal explicit SSP gives
    no explanation. Exact equality (zero tolerance) prevents conversion from masking drift.
    Raw source/eRev values and their difference remain visible in the reconciliation report.
    """
    bundles = tuple(verified_bundles)
    refs = dict(index.refs)
    for source in latest:
        if not field_mapping.is_material_right(source):
            continue
        quantity = decimal_of(source.values.get("Original POB Total Qty"))
        remaining = decimal_of(source.values.get("Current Remaining Qty"))
        if quantity is None or remaining is None or not 0 <= remaining <= quantity:
            continue
        matching = [
            (bundle, header)
            for bundle in bundles
            for header in bundle.contracts
            if header.external_id == source.contract_external_id
        ]
        if len(matching) != 1:
            continue
        bundle, header = matching[0]
        rights = [
            right
            for right in header.material_rights
            if right.obligation_key == source.obligation_key
        ]
        if len(rights) != 1:
            continue
        (right,) = rights
        if (
            right.ssp_method != "ENTERED_AMOUNT"
            or right.entered_ssp_amount != quantity
            or right.is_legacy_quantity_ssp_dollars
            or right.currency != header.transaction_currency
        ):
            continue
        booked: list[Mapping[str, object]] = []
        for event in bundle.events:
            if event.contract_key != header.external_id or event.event_type != "CONTRACT_BOOKED":
                continue
            lines = event.payload.get("lines")
            for line in lines if isinstance(lines, list | tuple) else ():
                if (
                    isinstance(line, Mapping)
                    and line.get("obligation_key") == source.obligation_key
                ):
                    booked.append(line)
        if len(booked) != 1 or booked[0].get("product_code") != source.values.get("SKU Name"):
            continue
        booked_quantity = booked[0].get("quantity")
        if not isinstance(booked_quantity, str):
            continue
        try:
            if decimal_of(booked_quantity) != 1:
                continue
        except InvalidOperation:
            continue
        key = (source.contract_external_id, source.obligation_key, "REMAINING_QTY")
        explained = Deviation(
            REFERENCE, Fraction(remaining), Fraction(remaining) / Fraction(quantity), Fraction(0)
        )
        if key in refs and refs[key] != explained:
            raise ExactSourceError(f"{key[0]} / {key[1]}: conflicting quantity explanations")
        refs[key] = explained
    return DeviationIndex(refs, index.source_digests, index.unmeasured)


def require_exact_quantities(index: DeviationIndex, actual: Mapping[LineKey, Fraction]) -> None:
    """Do not let equal raw numbers pass when their units differ (e.g. 10 options vs $10)."""
    for key, explanation in index.refs.items():
        if explanation.dev_id != REFERENCE:
            continue
        if actual.get(key) != explanation.corrected_value:
            raise ExactSourceError(
                f"{key[0]} / {key[1]}: captured option quantity does not equal the exact "
                "POL-212 source-unit conversion"
            )
