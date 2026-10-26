"""Split-group movements from the original routed layers, with explicit gross reclassification."""

from dataclasses import replace

from erev_engine.bundle import PeriodInput
from erev_engine.stages.state import BookContext

from .rollforward import (
    BALANCES,
    CONTRACT_ASSET,
    CONTRACT_LIABILITY,
    UNBILLED_RECEIVABLE,
    BalanceInputs,
    _captions,
    _functional,
)


def fill(
    ctx: BookContext,
    records: BalanceInputs,
    entity: str,
    unit: str,
    period: PeriodInput,
    previous: PeriodInput | None,
    lines: dict[str, dict[str, int]],
    *,
    functional: bool,
    split_sources: frozenset[str],
) -> int:
    fx = records.fx
    if fx is None:
        raise ValueError("Split reporting requires original FX layers")
    if not functional:
        fx = replace(
            fx,
            layer_movements=tuple(
                replace(
                    m,
                    amount_functional=0 if m.movement_kind.endswith("REMEASURED") else m.amount_txn,
                )
                for m in fx.layer_movements
            ),
            layer_balances=tuple(replace(b, fn_carrying=b.txn_open) for b in fx.layer_balances),
        )
    # Member endpoints carry the effective destination presentation. The layer
    # path still supplies every movement and FX difference independently.
    relief = _functional(
        ctx,
        replace(records, fx=fx),
        entity,
        unit,
        period,
        previous,
        None,
        lines,
        split_sources=split_sources,
    )
    suffix = "_functional" if functional else ""
    assert records.fx is not None
    targets = records.fx.functional_member_balances if functional else ()
    if not functional:
        source = getattr(records.fx.costs, "balances", None)
        if source is None:
            source = getattr(getattr(records.fx.costs, "costs", None), "balances", None)
        if source is None:
            raise ValueError("Split reporting lacks native member endpoint sources")
        targets = source.member_balances

    def amounts(key: str) -> dict[str, int]:
        return {
            role: sum(
                t.value
                for t in targets
                if t.entity == entity and t.period_key == key and t.measure == role.lower() + suffix
            )
            for role in BALANCES
        }

    opening = amounts(previous.period_key) if previous is not None else dict.fromkeys(BALANCES, 0)
    closing = amounts(period.period_key)
    for role in BALANCES:
        lines[role]["OPENING"] = opening[role]
    # Only a caption transfer can bridge the asset path to the native destination
    # captions. Never absorb missing liability/asset amounts into that line.
    projected = {
        r: sum(
            v
            for k, v in lines[r].items()
            if k not in {"CLOSING", "OTHER", "RECLASSIFIED_BETWEEN_ASSET_CAPTIONS"}
        )
        for r in (CONTRACT_ASSET, UNBILLED_RECEIVABLE)
    }
    if (
        projected[CONTRACT_ASSET] + projected[UNBILLED_RECEIVABLE]
        != closing[CONTRACT_ASSET] + closing[UNBILLED_RECEIVABLE]
    ):
        raise ValueError("Split asset movements differ from native destination endpoints")
    if (
        sum(v for k, v in lines[CONTRACT_LIABILITY].items() if k not in {"CLOSING", "OTHER"})
        != closing[CONTRACT_LIABILITY]
    ):
        raise ValueError("Split liability movements differ from native destination endpoints")
    _captions(projected, closing, lines)
    for role in BALANCES:
        lines[role]["CLOSING"] = closing[role]
    return relief
