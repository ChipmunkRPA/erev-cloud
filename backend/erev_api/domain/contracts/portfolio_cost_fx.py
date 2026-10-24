"""Freeze shared return unit-cost conversion; replay never resolves a newer FX publication."""

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.db.tables import contract
from erev_api.problems import Problem
from erev_api.schemas.estimates import SharedEstimateCostConversion
from erev_engine.stages.s12_fx_entities.rates import RateMissing, Rates

COSTS = ("carrying_cost_per_unit", "recovery_cost_per_unit")


def _costs(row: Mapping[str, Any]) -> dict[str, Decimal]:
    try:
        result = {key: Decimal(str((row.get("parameters") or {}).get(key, 0))) for key in COSTS}
    except (InvalidOperation, TypeError, ValueError) as error:
        raise Problem("validation-failed", "Shared unit costs must be finite decimals.") from error
    if any(not value.is_finite() for value in result.values()):
        raise Problem("validation-failed", "Shared unit costs must be finite decimals.")
    return result


def _converted(costs: Mapping[str, Decimal], rate: Decimal) -> dict[str, str]:
    # Unit costs are exact inputs. Rounding belongs to the existing final amount calculation.
    with localcontext() as context:
        context.prec = max(
            60,
            max(len(v.as_tuple().digits) for v in costs.values()) + len(rate.as_tuple().digits) + 2,
        )
        return {key: format(value * rate, "f") for key, value in costs.items()}


def capture(
    session: Session, row: Mapping[str, Any], recipients: Sequence[UUID]
) -> list[SharedEstimateCostConversion]:
    costs = _costs(row)
    if not any(costs.values()):
        return []
    source = str(row["currency"]).strip()
    currencies = {
        str(c).strip()
        for c in session.scalars(
            select(contract.c.transaction_currency).where(contract.c.id.in_(recipients))
        )
    }
    foreign = currencies - {source}
    if not foreign:
        return []
    if row.get("scenarios") or any(
        row.get(key) not in (None, 0, Decimal(0))
        for key in (
            "unconstrained_amount",
            "constrained_amount",
            "most_conservative_amount",
            "expected_total_amount",
        )
    ):
        raise Problem(
            "validation-failed",
            "Shared return FX conversion supports unit costs, not other monetary amounts.",
        )
    from erev_api.domain.contracts import bundles

    rates = bundles.fx_rate_inputs(session, currencies | {source}, None)
    result = []
    for target in sorted(foreign):
        try:
            selected = Rates(rates, source, target).spot(row["effective_date"])
        except RateMissing as error:
            raise Problem(
                "validation-failed",
                f"Publish a direct {source}/{target} spot rate "
                "on or before the estimate effective date.",
            ) from error
        rate = Decimal(selected.text)
        if not rate.is_finite() or rate <= 0 or not selected.rate_key or not selected.version_key:
            raise Problem("validation-failed", "A positive published spot-rate source is required.")
        original = next(r for r in rates if r.rate_key == selected.rate_key)
        result.append(
            SharedEstimateCostConversion(
                source_currency=source,
                target_currency=target,
                rate_key=selected.rate_key,
                rate_version_key=selected.version_key,
                rate_date=original.effective_date,
                rate=selected.text,
                original_costs={k: format(v, "f") for k, v in costs.items()},
                converted_costs=_converted(costs, rate),
            )
        )
    return result


def apply(row: Mapping[str, Any], currencies: set[str]) -> Mapping[str, Any]:
    basis = row.get("portfolio_application_basis") or {}
    saved = basis.get("cost_conversions", [])
    if not saved or currencies == {str(row["currency"]).strip()}:
        return row
    if len(currencies) != 1:
        raise Problem(
            "validation-failed",
            "Shared cost conversion requires one transaction currency per computation group.",
        )
    target = next(iter(currencies))
    matches = [
        SharedEstimateCostConversion.model_validate(c)
        for c in saved
        if c["target_currency"] == target
    ]
    if len(matches) != 1:
        raise Problem(
            "validation-failed",
            "The shared estimate lacks a unique frozen member-currency conversion.",
        )
    conversion = matches[0]
    costs = _costs(row)
    rate = Decimal(conversion.rate)
    if (
        conversion.source_currency != str(row["currency"]).strip()
        or not rate.is_finite()
        or rate <= 0
        or conversion.rate_date > row["effective_date"]
        or {k: Decimal(v) for k, v in conversion.original_costs.items()} != costs
        or {k: Decimal(v) for k, v in conversion.converted_costs.items()}
        != {k: Decimal(v) for k, v in _converted(costs, rate).items()}
    ):
        raise Problem("validation-failed", "Frozen shared unit-cost evidence does not reconcile.")
    return {
        **row,
        "currency": target,
        "parameters": {
            **(row.get("parameters") or {}),
            **conversion.converted_costs,
            "shared_unit_cost_fx": conversion.model_dump(mode="json"),
        },
    }
