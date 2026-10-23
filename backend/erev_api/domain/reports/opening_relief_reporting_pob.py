"""Translate signed POB attribution changes at retained posting-period average rates."""

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any
from uuid import UUID

from . import reporting_currency, tie_outs
from .builders.contract_balance_rollforward import ASSET, LIABILITY, UNBILLED, ContractRollforward

KEY = "opening_relief_reporting_pob_v1"
ZERO = Decimal(0)


def translate(
    rows: list[dict[str, Any]],
    slices: Mapping[str, Any],
    projected: Sequence[ContractRollforward],
    periods: Mapping[UUID, tuple[tie_outs.PeriodRef, ...]],
    rates: Sequence[dict[str, Any]],
) -> None:
    sources = {(item.contract_id, item.entity_id): item for item in projected}
    by_row = {item["row_key"]: item for item in slices.values()}
    for row in rows:
        source = by_row[row["row_key"]]
        entity = source["entity"]
        members = [sources[key] for key in source["members"]]
        currency = members[0].currency
        if any(item.currency != currency for item in members):
            raise tie_outs.invalid("currency_view", "POB reporting currencies differ.")
        relief = ZERO
        for period in periods[entity]:
            found = [
                fact
                for fact in rates
                if fact["entity_code"] == row["entity_code"]
                and fact["period_key"] == period.key
                and fact["rate_type"] == "average"
            ]
            if (
                len(found) != 1
                or found[0]["base_currency"] != source["currency"]
                or found[0]["quote_currency"] != currency
            ):
                raise tie_outs.invalid("currency_view", "POB reporting rate source differs.")
            translation = reporting_currency.Translation(currency, {entity: found[0]})
            relief += translation.amount(entity, source["periods"][period.id])
        opening = sum((item.lines["OPENING"][LIABILITY] for item in members), ZERO)
        recognized = sum(
            (
                values[ASSET] + values[UNBILLED] - values[LIABILITY]
                for item in members
                for code, values in item.lines.items()
                if code in {"REVENUE_FROM_OPENING", "REVENUE_FROM_PERIOD_BILLINGS"}
            ),
            ZERO,
        )
        row.update(
            currency=currency,
            opening_contract_liability=tie_outs.money(opening, currency),
            revenue_recognized=tie_outs.money(recognized, currency),
            revenue_from_opening=tie_outs.money(relief, currency),
        )
