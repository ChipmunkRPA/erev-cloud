"""Map saved obligation-period forecast values to comparison facts without recalculation."""

from decimal import Decimal, InvalidOperation, localcontext
from uuid import UUID

from erev_api.domain.reports.forecast_actuals_saved import Actuals
from erev_api.domain.reports.forecast_comparison import Revenue
from erev_api.domain.reports.forecast_saved import SavedRevenue
from erev_api.problems import Problem


def forecast_rows(saved: SavedRevenue, *, require_category: bool) -> tuple[Revenue, ...]:
    parameters = saved.forecast.run["parameters"]
    horizon = parameters["horizon_periods"]
    selected = {str(identity) for identity in saved.entities.values()}
    if selected != set(parameters["entity_ids"]):
        raise Problem("precondition-failed", "The forecast entity mapping is incomplete.")
    output: list[Revenue] = []
    seen: set[str] = set()
    try:
        for row in saved.revenue["rows"]:
            row_key = row["row_key"]
            if row_key in seen:
                raise ValueError("duplicate forecast row")
            seen.add(row_key)
            if row_key.startswith("TOTAL:"):
                continue
            entity_id = saved.entities[row["entity_code"]]
            contract = row["contract_external_id"]
            if not isinstance(contract, str) or not contract:
                raise ValueError("contract")
            if require_category and "revenue_category" not in row:
                raise ValueError("legacy forecast has no saved category")
            category = row.get("revenue_category")
            if category is not None and (not isinstance(category, str) or not category):
                raise ValueError("category")
            for period in horizon:
                cell = row[f"period:{period}"]
                currency = cell["currency"]
                amount = Decimal(cell["amount"])
                if not currency or not amount.is_finite():
                    raise ValueError("money")
                output.append(Revenue(entity_id, contract, category, period, currency, amount))
    except (KeyError, TypeError, ValueError, InvalidOperation) as error:
        raise Problem(
            "precondition-failed", "The saved forecast dimensions are incomplete."
        ) from error
    return tuple(output)


def actual_rows(saved: Actuals, *, require_category: bool) -> tuple[Revenue, ...]:
    parameters = saved.forecast.run["parameters"]
    view = parameters.get("currency_view", "transaction")
    if view not in ("transaction", "functional"):
        raise Problem("validation-failed", "Choose transaction or functional currency.")
    suffix = "txn" if view == "transaction" else "functional"
    output: list[Revenue] = []
    seen: set[str] = set()
    try:
        with localcontext() as context:
            context.prec = 80
            for row in saved.rows:
                if (
                    row["id"] in seen
                    or row["entity_id"] not in parameters["entity_ids"]
                    or row["period_key"] not in parameters["horizon_periods"]
                    or row.get("contract_label_known") is not True
                ):
                    raise ValueError("actual source identity")
                seen.add(row["id"])
                contract = row["contract_external_id"]
                if not isinstance(contract, str) or not contract:
                    raise ValueError("contract")
                if require_category and row.get("revenue_category_known") is not True:
                    raise ValueError("historical category unavailable")
                category = row.get("revenue_category")
                if category is not None and (not isinstance(category, str) or not category):
                    raise ValueError("category")
                debit, credit = Decimal(row[f"debit_{suffix}"]), Decimal(row[f"credit_{suffix}"])
                currency = row[f"{suffix}_currency"]
                if not currency or not debit.is_finite() or not credit.is_finite():
                    raise ValueError("money")
                output.append(
                    Revenue(
                        UUID(row["entity_id"]),
                        contract,
                        category,
                        row["period_key"],
                        currency,
                        credit - debit,
                    )
                )
    except (KeyError, TypeError, ValueError, InvalidOperation) as error:
        raise Problem(
            "precondition-failed", "The retained actuals dimensions are incomplete."
        ) from error
    return tuple(output)
