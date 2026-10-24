"""Read complete original nonposting acquisition observations; never recompute a saved run."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from erev_engine.bundle import InputBundle
from erev_engine.stages.s01_canonicalize import contract_entity_subject_key
from erev_engine.stages.state import PolicyResolver

from . import tie_outs


def read(
    bundle: InputBundle,
    output: Mapping[str, Any],
    *,
    member: str,
    entity: str,
    book: str,
    period: tie_outs.PeriodRef,
    event_key: str,
) -> tuple[dict[str, Decimal], dict[str, Any]] | None:
    grouped = len(bundle.group.member_contract_keys) > 1
    if (
        (bundle.evidence_revision or 0) < 44
        or (grouped and (bundle.evidence_revision or 0) < 62)
        or member not in bundle.group.member_contract_keys
    ):
        return None
    original = next(item for item in output["books"] if item["book_code"] == book)
    candidates = [
        item
        for item in (original.get("acquisition_balance_observations") or ())
        if item["member"] == member
        and item["entity"] == entity
        and item["as_of"] <= period.end.isoformat()
    ]
    if len(candidates) != 1:
        return None
    snapshot = candidates[0]
    if grouped and (
        snapshot.get("members") != sorted(bundle.group.member_contract_keys)
        or sorted(
            item["member"]
            for item in original.get("acquisition_balance_observations", ())
            if item["entity"] == entity and item["as_of"] == snapshot["as_of"]
        )
        != sorted(bundle.group.member_contract_keys)
        or output.get("input_sha256") != bundle.sha256()
        or output.get("engine_version") != bundle.engine_version
    ):
        raise tie_outs.invalid("currency_view", "Original acquisition member population differs.")
    original_entity = next(item for item in bundle.entities if item.code == entity)
    original_book = next(item for item in bundle.books if item.book_code == book)
    currency = bundle.group.transaction_currency
    mu = bundle.currencies[currency].minor_unit
    unmeasured = snapshot.get("unmeasured", {})
    if (
        snapshot.get("basis") != "ORIGINAL_NONPOSTING_CUTOVER_EVALUATION"
        or snapshot["currency"] != currency
        or snapshot["minor_unit"] != mu
        or set(snapshot["amounts"]) != set(tie_outs.BALANCE_MEASURES)
        or unmeasured not in ({}, {"accounts_receivable": "ERP_MODE_EXTERNAL_BALANCE"})
        or set(snapshot["nodes"]) != set(tie_outs.BALANCE_MEASURES) - set(unmeasured)
        or not any(
            p.period_key == snapshot["period_key"] and p.end_date.isoformat() == snapshot["as_of"]
            for p in original_entity.periods
        )
        or not any(
            e.event_key == event_key
            and e.contract_key == member
            and str(e.payload.get("cutover_date")) == snapshot["as_of"]
            for e in bundle.events
        )
    ):
        raise tie_outs.invalid(
            "currency_view", "Original complete acquisition balance scope differs."
        )
    nodes = {item["id"]: item for item in original["trace"]["nodes"]}
    amounts = {}
    member_prefix = f"acquisition-cutover/{snapshot['period_key']}/"
    subject = contract_entity_subject_key(member, entity)
    scale = Decimal(10) ** -mu
    for measure, amount in snapshot["amounts"].items():
        if measure in unmeasured:
            if type(amount) is not int or amount != 0:
                raise tie_outs.invalid(
                    "currency_view", "Unmeasured ERP balance differs from its reporting default."
                )
            amounts[measure] = Decimal(0)
            continue
        node = nodes.get(snapshot["nodes"][measure])
        if (
            type(amount) is not int
            or node is None
            or (
                grouped
                and snapshot["nodes"][measure]
                != f"{measure}:{member_prefix}{subject}:{snapshot['period_key']}"
            )
            or node["measure"] != measure
            or node["currency"] != currency
            or Decimal(node["value"]) != Decimal(amount) * scale
        ):
            raise tie_outs.invalid(
                "currency_view", "Original complete acquisition balance source differs."
            )
        amounts[measure] = Decimal(amount) * scale
    functional = snapshot.get("functional")
    if original_entity.functional_currency != currency:
        if (
            not isinstance(functional, dict)
            or (bundle.evidence_revision or 0) < 45
            or (grouped and "shared_liability_members" not in functional)
            or (
                functional.get("currency") != original_entity.functional_currency
                or functional.get("minor_unit")
                != bundle.currencies[original_entity.functional_currency].minor_unit
                or set(functional.get("amounts", {})) != set(functional.get("nodes", {}))
                or not set(tie_outs.ROLLFORWARD_BALANCES) <= set(functional.get("amounts", {}))
                or not set(functional.get("amounts", {})) <= set(tie_outs.BALANCE_MEASURES)
            )
        ):
            raise tie_outs.invalid(
                "currency_view", "Original acquisition functional scope differs."
            )
        fn_scale = Decimal(10) ** -functional["minor_unit"]
        for role, amount in functional["amounts"].items():
            node = nodes.get(functional["nodes"][role])
            if (
                type(amount) is not int
                or node is None
                or (
                    grouped
                    and functional["nodes"][role]
                    != f"{role}_functional:{member_prefix}{subject}:{snapshot['period_key']}"
                )
                or node["measure"] != f"{role}_functional"
                or node["currency"] != functional["currency"]
                or Decimal(node["value"]) != Decimal(amount) * fn_scale
            ):
                raise tie_outs.invalid(
                    "currency_view", "Original acquisition functional source differs."
                )
    if functional is not None:
        from .acquisition_layer_sources import verify

        verify(bundle, snapshot, nodes, book=book)
    return amounts, {
        **snapshot,
        "nodes": sorted(snapshot["nodes"].values()),
        "event_key": event_key,
        "maturity": {
            "policy": PolicyResolver(original_book.policies).value(
                "balance.current_noncurrent", entity=entity, period=snapshot["period_key"]
            )
        },
    }
