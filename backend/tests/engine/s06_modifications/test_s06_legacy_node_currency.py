"""Stage 06 legacy templates: every amount node of a template boundary carries the transaction
currency (lane ENG-T1F, supervisor item raised by lane T1 from its scaling law).

``mod_ssp@<event>`` (S06-R-28) and ``allocated_exact@<event>`` (the exact allocation after the
template) are exact nodes holding transaction-currency amounts, like ``allocated_amount@<event>``
beside them; a currency-less amount node cannot be validated by a currency assertion (T1F-Q5-G1
class rule) and is classified by measure in T1's scaling law only for that reason. The three built
templates are exercised on the golden streams: prospective (Contract 3 step 11), retrospective
(Contract 2 step 08) and POB-specific VC (Contract 2 step 09). No figure changes: the values of the
nodes are asserted by ``test_tc_prospective``, ``test_s06_legacy_retro`` and ``test_tc_pob_vc``.
"""

from __future__ import annotations

import pytest
from erev_engine import ENGINE_VERSION
from erev_engine.trace import TraceBuilder
from test_s06_prospective import checked
from test_tc_rm import amendments, apply, golden

AMOUNT_MEASURES = ("mod_ssp@", "allocated_exact@", "allocated_amount@")


@pytest.mark.parametrize(
    ("contract", "step", "template"),
    [
        ("Contract 3", "11", "prospective"),
        ("Contract 2", "08", "retrospective"),
        ("Contract 2", "09", "pob_vc"),
    ],
)
def test_legacy_template_amount_nodes_carry_the_transaction_currency(
    contract: str, step: str, template: str
) -> None:
    folded = golden(contract, step)
    tb = TraceBuilder(engine_version=ENGINE_VERSION)
    state = folded.state
    for ev in amendments(state):
        state = apply(folded, state, ev, tb)
    assert state.findings == (), template
    nodes = checked(tb)
    by_measure = {
        prefix: [node for node in nodes.values() if node.measure.startswith(prefix)]
        for prefix in AMOUNT_MEASURES
    }
    assert all(by_measure[prefix] for prefix in ("mod_ssp@", "allocated_exact@")), template
    currency = folded.ctx.txn_currency
    wrong = sorted(
        (node.id, node.currency)
        for prefix in AMOUNT_MEASURES
        for node in by_measure[prefix]
        if node.currency != currency
    )
    assert wrong == [], (template, currency, wrong)
