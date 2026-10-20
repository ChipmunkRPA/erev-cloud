"""Display the retained preview evidence without resolving mutable configuration again."""

from collections import defaultdict
from typing import Any

from erev_engine.money import format_money

from erev_api.domain.contracts.queries import range_position
from erev_api.money import MoneyOut
from erev_api.schemas.deal_previews import DealAllocationOut, DealBookOut, DealRevenueOut


def project(inputs: dict[str, Any], result: dict[str, Any]) -> list[DealBookOut]:
    bundle = inputs["engine_bundle"]

    def money(value: int, currency: str) -> MoneyOut:
        return MoneyOut(
            amount=format_money(value, bundle["currencies"][currency]["minor_unit"]),
            currency=currency,
        )

    books = []
    for book in result["books"]:
        contract = book["contract_version"]
        if contract is None:  # Legacy records have no proposed-contract allocation.
            continue
        columns = contract["columns"]
        currency = columns["transaction_currency"]
        obligations = {row["subject_key"]: row["columns"] for row in book["obligation_versions"]}
        allocations = []
        for key, row in obligations.items():
            stated = money(row["original_stated_price"], row["txn_currency"])
            allocations.append(
                DealAllocationOut(
                    subject_key=key,
                    obligation_key=row["obligation_key"],
                    product_code=row["product_code"],
                    stated_price=stated,
                    ssp_low=row["original_ssp_low"],
                    ssp_mid=row["original_ssp_mid"],
                    ssp_high=row["original_ssp_high"],
                    range_position=range_position(
                        row["original_ssp_low"], row["original_ssp_high"], stated.amount
                    ),
                    selected_ssp=row["original_ssp_selected"],
                    allocation_weight=row["allocation_weight"],
                    allocated_amount=money(row["allocated_amount"], row["txn_currency"]),
                    allocation_adjustment=money(row["allocation_adjustment"], row["txn_currency"]),
                )
            )
        revenue: dict[tuple[str, str, str], int] = defaultdict(int)
        for line in book["schedules"]:
            if line["schedule_kind"] == "REVENUE":
                revenue[(line["entity"], line["period_key"], line["subject_key"])] += line["amount"]
        books.append(
            DealBookOut(
                book_code=book["book_code"],
                transaction_price=money(columns["transaction_price"], currency),
                total_allocated=money(
                    sum(row["allocated_amount"] for row in obligations.values()), currency
                ),
                revenue_to_date=money(
                    sum(row["revenue_cum"] for row in obligations.values()), currency
                ),
                scheduled=money(
                    sum(row["scheduled_amount"] for row in obligations.values()), currency
                ),
                awaiting_trigger=money(
                    sum(row["awaiting_trigger_amount"] for row in obligations.values()), currency
                ),
                has_material_right=any(
                    row["obligation_kind"] == "MATERIAL_RIGHT" for row in obligations.values()
                ),
                has_variable_consideration=bool(
                    any(
                        estimate["estimate_kind"] == "VARIABLE_CONSIDERATION"
                        for estimate in bundle["estimate_versions"]
                    )
                    or columns["vc_constrained_amount"]
                    or columns["vc_excluded_amount"]
                    or any(row["obligation_kind"] == "VC_LINE" for row in obligations.values())
                ),
                allocations=allocations,
                revenue_by_period=[
                    DealRevenueOut(
                        entity_code=entity,
                        period_key=period,
                        subject_key=subject,
                        product_code=obligations.get(subject, {}).get("product_code"),
                        amount=money(amount, currency),
                    )
                    for (entity, period, subject), amount in sorted(revenue.items())
                ],
            )
        )
    return books
