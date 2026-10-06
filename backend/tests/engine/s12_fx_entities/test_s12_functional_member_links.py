"""Stage 12 functional member nodes of a foreign-currency entity (D-97 (8) T1F-Q-4; Codex
T1F-R2; lane ENG-T1F): the ``customer_incentive_asset_functional`` condition is the TRANSACTION
payable (the asset exists while the transaction payable is non-zero; its functional amount is the
historical measure), never the closing functional payable, which can round to 0 while the
transaction payable does not; the node cites the promised (and release) functional targets.

World: FX-CHK-084-C (entity US01 functional USD, EUR contract, a consideration-payable promise at
inception) with the promise amount and the rates varied through the booking event payload:
EUR 0.01 at spot 0.51 / closing 0.49 → historical USD 1 cent, closing USD 0 (Codex's native
case); EUR 1.00 → 51 cents = 51 cents; no promise → 0 = 0. No database (DG-TST-18).
"""

from __future__ import annotations

import dataclasses
import functools
from collections.abc import Sequence
from decimal import Decimal

from erev_engine import compute
from erev_engine.bundle import InputBundle, OutputBundle
from support.answer_keys.loader import ANSWER_KEY_ROOT, load
from support.answer_keys.runners import _build_checkpoint_bundles

KEY = "FX-CHK-084-C-CONSIDERATION-PAYABLE-REMEASURED"
MEMBER = "C-FX-084-C@US01"
PERIOD = "FY2026-P06"


@functools.cache
def _base() -> InputBundle:
    (bundle,) = _build_checkpoint_bundles(load(ANSWER_KEY_ROOT / "fx" / f"{KEY}.yaml"))[-1].bundles
    return bundle


def _variant(amount: Decimal | None, *, spot: str, closing: str) -> InputBundle:
    """The world with the promise amount replaced (``None`` removes the promise) and the EUR→USD
    spot / average rates at ``spot`` and the closing rate at ``closing``."""
    bundle = _base()
    # The promise lives in the booking payload and in the contract header (both canonical carriers
    # of API-S-ConsiderationPayable); stage 04 reads the payload when present, else the header.
    contracts = tuple(
        dataclasses.replace(
            contract,
            consideration_payable=()
            if amount is None
            else tuple(
                dataclasses.replace(item, amount=amount) for item in contract.consideration_payable
            ),
        )
        for contract in bundle.contracts
    )
    events = []
    for event in bundle.events:
        promises = event.payload.get("consideration_payable")
        if promises is None:
            events.append(event)
            continue
        payload = dict(event.payload)
        if amount is None:
            del payload["consideration_payable"]
        else:
            assert isinstance(promises, Sequence)
            payload["consideration_payable"] = [{**item, "amount": amount} for item in promises]
        events.append(dataclasses.replace(event, payload=payload))
    rates = tuple(
        dataclasses.replace(
            rate, rate=Decimal(closing) if rate.rate_type == "closing" else Decimal(spot)
        )
        for rate in bundle.fx_rates
    )
    return dataclasses.replace(bundle, contracts=contracts, events=tuple(events), fx_rates=rates)


def _incentive(output: OutputBundle) -> tuple[dict[str, object], tuple[str, ...], str]:
    book = output.books[0]
    row = next(item for item in book.balances if item.period_key == PERIOD)
    assert row.subject_key == MEMBER
    nodes = {node.id: node for node in book.trace.nodes}
    node = nodes[row.trace_nodes["customer_incentive_asset_functional"]]
    cited = tuple(item for item in node.inputs if isinstance(item, str))
    return dict(row.columns), cited, node.value


def test_tiny_promise_keeps_the_incentive_at_the_historical_cent() -> None:
    """EUR 0.01 at 0.51 / 0.49: the transaction payable is 1 cent, so the incentive exists and its
    functional amount is the historical USD 1 cent although the closing functional payable is 0
    (Codex T1F-R2: the closing payable is not the condition)."""
    columns, cited, value = _incentive(
        compute(_variant(Decimal("0.01"), spot="0.51", closing="0.49"))
    )
    assert (
        columns["consideration_payable_txn"],
        columns["consideration_payable_functional"],
        columns["customer_incentive_asset_txn"],
        columns["customer_incentive_asset_functional"],
    ) == (1, 0, 1, 1)
    assert value == "0.01"
    assert cited == (f"fx_payable_functional:{MEMBER}:{PERIOD}",)  # the promised target


def test_one_euro_promise_measures_51_cents() -> None:
    columns, _, value = _incentive(compute(_variant(Decimal("1.00"), spot="0.51", closing="0.49")))
    assert columns["customer_incentive_asset_functional"] == 51
    assert value == "0.51"


def test_no_promise_measures_zero() -> None:
    columns, cited, value = _incentive(compute(_variant(None, spot="0.51", closing="0.49")))
    assert (
        columns["consideration_payable_txn"],
        columns["customer_incentive_asset_functional"],
    ) == (
        0,
        0,
    )
    assert value == "0.00" and cited == ()
