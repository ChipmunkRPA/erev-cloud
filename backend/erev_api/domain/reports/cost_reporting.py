"""Monthly reporting-currency projection of verified functional contract costs."""

import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from uuid import UUID

from erev_api.domain.reports import reporting_currency, tie_outs
from erev_api.domain.reports.builders import ReportParams
from erev_api.domain.reports.builders import contract_cost_rollforward as costs
from erev_api.domain.reports.outputs import ReportData
from erev_api.uow import UnitOfWork
from erev_engine.money import largest_remainder, minor_to_decimal, round_half_up

KEY = "cost_reporting_projection_v1"
LINES = (*costs.LINE_CODES[:-1], "FX", "ROUNDING", "CLOSING")
LABELS = {**costs.LINE_LABELS, "FX": "Currency translation", "ROUNDING": "Translation rounding"}


def endpoint(
    monthly: Mapping[tuple[str, str], costs.Lines],
    entity: tie_outs.EntityRef,
    minor: int,
    code: str,
    rate: reporting_currency.Translation | None,
    assets: Mapping[tuple[str, str], tuple[str, str]] | None = None,
) -> dict[tuple[str, str], Decimal]:
    if assets is not None:
        if any(lines[code] < 0 for lines in monthly.values()):
            raise tie_outs.invalid("currency_view", "Cost carrying sources must be nonnegative.")
        categories: dict[tuple[str, str], costs.Lines] = {}
        for key, lines in monthly.items():
            category = (key[0], assets[key][1])
            into = categories.setdefault(category, {code: 0})
            into[code] += lines[code]
        parents = endpoint(categories, entity, minor, code, rate)
        factor = Fraction(str(rate.rates[entity.id]["rate"])) if rate else Fraction(1)
        exact = {
            key: Fraction(lines[code], 10 ** tie_outs.minor_unit(entity.functional_currency))
            * factor
            for key, lines in monthly.items()
        }
        return rounded_assets(exact, assets, minor, parents)
    keys = sorted(monthly)
    amounts = [
        Decimal(monthly[k][code]).scaleb(-tie_outs.minor_unit(entity.functional_currency))
        for k in keys
    ]
    if any(amount < 0 for amount in amounts):
        raise tie_outs.invalid("currency_view", "Cost carrying sources must be nonnegative.")
    if not any(amounts):
        return dict.fromkeys(keys, Decimal(0))
    if rate is None:
        raise tie_outs.invalid("currency_view", "A nonzero cost endpoint requires a rate.")
    weights = [Fraction(amount) for amount in amounts]
    total = round_half_up(sum(weights) * Fraction(str(rate.rates[entity.id]["rate"])), minor)
    allocated = largest_remainder(total, weights, [k[1] for k in keys])
    return {k: minor_to_decimal(value, minor) for k, value in zip(keys, allocated, strict=True)}


def rounded_assets(
    exact: Mapping[tuple[str, str], Fraction],
    assets: Mapping[tuple[str, str], tuple[str, str]],
    minor: int,
    parents: Mapping[tuple[str, str], Decimal] | None = None,
) -> dict[tuple[str, str], Decimal]:
    """Signed largest remainders within each category; totals equal the category view."""
    groups: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for key in exact:
        groups.setdefault((key[0], assets[key][1]), []).append(key)
    result = {}
    for category, keys in groups.items():
        amounts = {key: exact[key] * 10**minor for key in keys}
        floors = {key: value.numerator // value.denominator for key, value in amounts.items()}
        total = (
            int(parents[category].scaleb(minor))
            if parents is not None
            else round_half_up(sum((exact[key] for key in keys), Fraction(0)), minor)
        )
        remainder = total - sum(floors.values())
        if not 0 <= remainder <= len(keys):
            raise tie_outs.invalid("currency_view", "Cost detail rounding does not reconcile.")
        order = sorted(keys, key=lambda key: (-(amounts[key] - floors[key]), key))
        winners = set(order[:remainder])
        result.update(
            {key: minor_to_decimal(floors[key] + (key in winners), minor) for key in keys}
        )
    return result


def build(
    uow: UnitOfWork,
    params: ReportParams,
    entities: Sequence[tie_outs.EntityRef],
    periods: Mapping[UUID, tuple[tie_outs.PeriodRef, ...]],
    before: Mapping[UUID, tie_outs.PeriodRef | None],
    movements: Sequence[costs.CostMovement],
    balances: Sequence[tie_outs.BalanceRow],
    *,
    assets: Mapping[tuple[str, str], tuple[str, str]] | None = None,
) -> ReportData:
    tie_outs.record_evidence(params, KEY, True)
    source_lines, source_currencies = costs.rollforward(movements, by_asset=assets is not None)
    source_check = costs.cost_tie(source_lines, source_currencies, balances)
    totals: dict[tuple[str, str], dict[str, Decimal]] = {}
    currencies: dict[str, str] = {}
    rates: dict[str, reporting_currency.Translation] = {}
    expected: dict[str, Decimal] = {}
    target_currency = None

    def translation(
        entity: tie_outs.EntityRef, period: tie_outs.PeriodRef | None, kind: str
    ) -> reporting_currency.Translation:
        if period is None:
            raise tie_outs.invalid("currency_view", "Cost translation requires a dated period.")
        key = f"cost_reporting_v1:{entity.id}:{period.key}:{kind}"
        if key not in rates:
            rates[key] = reporting_currency.rates_for_period(
                uow.session,
                params,
                tenant_id=uow.principal.tenant_id,
                entities=(entity,),
                periods={entity.id: period},
                rate_type=kind,
                evidence_key=key,
            )
        return rates[key]

    for entity in entities:
        own = [m for m in movements if m.entity_code == entity.code]
        if any(m.period_end is None for m in own):
            raise tie_outs.invalid(
                "currency_view", "Cost translation requires original posting periods."
            )
        previous = before.get(entity.id)
        for index, period in enumerate(periods[entity.id]):
            monthly, _ = costs.rollforward(
                [
                    replace(m, in_range=m.period_end >= period.start)
                    for m in own
                    if m.period_end is not None and m.period_end <= period.end
                ],
                by_asset=assets is not None,
            )
            if not monthly:
                previous = period
                continue
            closing = translation(entity, period, "closing")
            average = translation(entity, period, "average")
            if closing.currency != average.currency or (
                target_currency is not None and target_currency != closing.currency
            ):
                raise tie_outs.invalid("currency_view", "Cost translation target currency changed.")
            target_currency = closing.currency
            currencies[entity.code] = target_currency
            minor = tie_outs.minor_unit(target_currency)

            has_opening = any(lines["OPENING"] for lines in monthly.values())
            if has_opening and previous is None:
                raise tie_outs.invalid(
                    "currency_view", "Nonzero cost opening needs a preceding period."
                )
            opening = translation(entity, previous, "closing") if has_opening else None
            if opening is not None and opening.currency != target_currency:
                raise tie_outs.invalid("currency_view", "Cost opening currency differs.")
            shown_opening = endpoint(monthly, entity, minor, "OPENING", opening, assets)
            shown_closing = endpoint(monthly, entity, minor, "CLOSING", closing, assets)
            detail: dict[str, dict[tuple[str, str], Decimal]] = {}
            if assets is not None:
                scale = 10 ** tie_outs.minor_unit(entity.functional_currency)
                avg_rate = Fraction(str(average.rates[entity.id]["rate"]))
                close_rate = Fraction(str(closing.rates[entity.id]["rate"]))
                open_rate = (
                    Fraction(str(opening.rates[entity.id]["rate"])) if opening else Fraction(1)
                )
                for code in costs.MOVEMENT_LINES:
                    detail[code] = rounded_assets(
                        {
                            key: Fraction(lines[code], scale) * avg_rate
                            for key, lines in monthly.items()
                        },
                        assets,
                        minor,
                    )
                detail["FX"] = rounded_assets(
                    {
                        key: Fraction(lines["CLOSING"], scale) * (close_rate - avg_rate)
                        - Fraction(lines["OPENING"], scale) * (open_rate - avg_rate)
                        for key, lines in monthly.items()
                    },
                    assets,
                    minor,
                )
            for key, lines in monthly.items():
                raw = {
                    k: Decimal(v).scaleb(-tie_outs.minor_unit(entity.functional_currency))
                    for k, v in lines.items()
                }
                shown = {k: average.amount(entity.id, raw[k]) for k in costs.MOVEMENT_LINES}
                shown["OPENING"] = shown_opening[key]
                shown["CLOSING"] = shown_closing[key]
                avg = Fraction(str(average.rates[entity.id]["rate"]))
                close = Fraction(str(closing.rates[entity.id]["rate"]))
                first = Fraction(str(opening.rates[entity.id]["rate"])) if opening else Fraction(1)
                fx = Fraction(raw["CLOSING"]) * (close - avg) - Fraction(raw["OPENING"]) * (
                    first - avg
                )
                shown["FX"] = minor_to_decimal(round_half_up(fx, minor), minor)
                if assets is not None:
                    shown.update({code: values[key] for code, values in detail.items()})
                shown["ROUNDING"] = (
                    shown["CLOSING"]
                    - shown["OPENING"]
                    - sum(shown[k] for k in (*costs.MOVEMENT_LINES, "FX"))
                )
                into = totals.setdefault(key, dict.fromkeys(LINES, Decimal(0)))
                if index == 0:
                    into["OPENING"] = shown["OPENING"]
                into["CLOSING"] = shown["CLOSING"]
                for k in (*costs.MOVEMENT_LINES, "FX", "ROUNDING"):
                    into[k] += shown[k]
            if index == len(periods[entity.id]) - 1:
                carrying = Decimal(0)
                for balance in balances:
                    if balance.entity_id != entity.id:
                        continue
                    if balance.currency != entity.functional_currency and balance.value(
                        costs.CARRYING_MEASURE
                    ):
                        raise tie_outs.invalid(
                            "currency_view", "Cost carrying sources are not in functional currency."
                        )
                    carrying += balance.value(costs.CARRYING_MEASURE)
                tie_outs.add(expected, target_currency, closing.amount(entity.id, carrying))
            previous = period
    rows = []
    control: dict[str, dict[str, Decimal]] = {"opening": {}, "closing": {}}
    for (entity_code, group_key), values in sorted(totals.items()):
        contract_key, kind = (
            assets[(entity_code, group_key)] if assets is not None else ("", group_key)
        )
        currency = currencies[entity_code]
        for code in LINES:
            rows.append(
                {
                    "row_key": (
                        json.dumps([entity_code, group_key, code], separators=(",", ":"))
                        if assets is not None
                        else f"{entity_code}:{kind}:{code}"
                    ),
                    **(
                        {"asset_key": group_key, "contract_external_id": contract_key}
                        if assets is not None
                        else {}
                    ),
                    "section": 1,
                    "entity_code": entity_code,
                    "cost_kind": kind,
                    "line_code": code,
                    "category_label": costs.CATEGORY_LABELS[kind],
                    "line_label": LABELS[code],
                    "currency": currency,
                    "amount": tie_outs.money(values[code], currency),
                }
            )
        for code in ("OPENING", "CLOSING"):
            tie_outs.add(control[code.lower()], currency, values[code])
    check = tie_outs.compared(costs.TO_COST_ROLLFORWARD_BALANCES, expected, control["closing"])
    if source_check["result"] != tie_outs.PASS:
        check["result"] = tie_outs.FAIL
    check["details"] = [{"basis": "original_functional", "result": source_check["result"]}]
    return ReportData(
        costs.detail_columns(assets),
        tuple(rows),
        {
            **{k: tie_outs.by_currency(v) for k, v in control.items()},
            "currency_view": "reporting",
            "functional_source_check": source_check,
            "translation_rates": [
                {
                    "source_key": k,
                    "currency": v.currency,
                    "rates": {str(i): r for i, r in v.rates.items()},
                }
                for k, v in sorted(rates.items())
            ],
        },
        (check,),
    )
