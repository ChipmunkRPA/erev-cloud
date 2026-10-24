"""Reconcile the original open liability layers without allocating future income."""

from collections.abc import Mapping
from decimal import Decimal
from fractions import Fraction
from typing import Any

from erev_engine.bundle import InputBundle

from . import tie_outs


def verify(
    bundle: InputBundle,
    snapshot: Mapping[str, Any],
    nodes: Mapping[str, Any],
    *,
    book: str | None = None,
) -> None:
    if (bundle.evidence_revision or 0) < 46:
        return
    functional = snapshot["functional"]
    layers = functional.get("liability_layers")
    if not isinstance(layers, list):
        raise tie_outs.invalid(
            "currency_view", "Original acquisition liability layers are unavailable."
        )
    keys = set()
    total = 0
    scale = Decimal(10) ** -functional["minor_unit"]
    rates = {(rate.rate_key, rate.version_key): rate for rate in bundle.fx_rates}
    for layer in layers:
        key = layer["layer_key"]
        if key in keys or not layer["movements"]:
            raise tie_outs.invalid(
                "currency_view", "Original acquisition liability layer population differs."
            )
        keys.add(key)
        txn, carrying = 0, 0
        for move in layer["movements"]:
            node = nodes.get(move["node"])
            rate = rates.get((move["rate_key"], move["version_key"]))
            if (
                type(move["amount_txn"]) is not int
                or type(move["amount_functional"]) is not int
                or move["effective_date"] > snapshot["as_of"]
                or node is None
                or node["currency"] != functional["currency"]
                or Decimal(node["value"]) != Decimal(move["amount_functional"]) * scale
                or rate is None
                or rate.base_currency != snapshot["currency"]
                or rate.quote_currency != functional["currency"]
                or Fraction(rate.rate) != Fraction(move["rate"])
            ):
                raise tie_outs.invalid(
                    "currency_view", "Original acquisition liability movement source differs."
                )
            if move["kind"] == "LIABILITY_LAYER_CREATED":
                txn += move["amount_txn"]
                carrying += move["amount_functional"]
            elif move["kind"] == "LIABILITY_LAYER_CONSUMED":
                txn -= move["amount_txn"]
                carrying -= move["amount_functional"]
            elif move["kind"] == "LIABILITY_LAYER_REMEASURED":
                carrying += move["amount_functional"]
            else:
                raise tie_outs.invalid(
                    "currency_view", "Original liability movement kind is unsupported."
                )
        if (
            type(layer["txn_open"]) is not int
            or type(layer["functional_carrying"]) is not int
            or (txn, carrying) != (layer["txn_open"], layer["functional_carrying"])
        ):
            raise tie_outs.invalid(
                "currency_view", "Original acquisition liability layer does not reconcile."
            )
        total += carrying
    if total != functional["amounts"]["contract_liability"]:
        raise tie_outs.invalid(
            "currency_view", "Original acquisition liability layers differ from total carrying."
        )

    if (bundle.evidence_revision or 0) >= 47:
        from erev_engine.stages.s12_fx_entities.current_layers import classify
        from erev_engine.stages.state import PolicyResolver

        original = next(item for item in bundle.books if item.book_code == book)
        policies = PolicyResolver(original.policies)
        policy = str(
            policies.value(
                "fx.cl_layer_consumption", entity=snapshot["entity"], period=snapshot["period_key"]
            )
        )
        monetary = (
            book == "ASC606"
            and policies.value(
                "fx.cl_historical_layering",
                contract=snapshot["member"],
                entity=snapshot["entity"],
                period=snapshot["period_key"],
            )
            == "DISABLED_REMEASURE_AS_MONETARY"
        )
        try:
            parts = classify(
                layers,
                snapshot["amounts"]["contract_liability_current"],
                policy=policy,
                minor_unit=functional["minor_unit"],
                monetary=monetary,
            )
        except ValueError as error:
            raise tie_outs.invalid("currency_view", str(error)) from error
        expected = {"policy": policy, "monetary": monetary, "allocations": list(parts)}
        if functional.get("liability_current") != expected or sum(
            int(part["current_functional"]) for part in parts
        ) != functional["amounts"].get("contract_liability_current"):
            raise tie_outs.invalid("currency_view", "Original current liability layers differ.")
