# Contract FIFO agent net disclosure — October 23, 2026

This extends [multi-currency agent reporting](AGENT-MULTICURRENCY-OPENING-2026-10-23.md)
from FIFO_WITHIN_POB to FIFO_WITHIN_CONTRACT.

## Implemented behavior

Contract FIFO reports now read the verified original net income, including net/supplier
reallocations without a gross control movement. The opening-income calculation applies
one contract/combination cap over original opening-source net income, range-net revenue,
opening liability and actual liability consumption. It does not apply POB-level caps.

For combinations, original source owners may be any member of the selected computation
group. The report presents one combination amount with the complete member set; it does
not allocate that amount to the receiving or recognizing members. Source owners outside
the selected group are refused. Principal revenue in a mixed group retains its original
signed layer amounts and dates; no agent net amount is prorated over its source set.

Functional amounts use original net postings. Reporting currency translates each period's
signed cumulative opening-eligibility change and original net income at its retained
average rate. Original gross-control reconciliation and engine postings are unchanged.

A non-positive range consumption proves zero opening relief. Reporting uses this shortcut
only when every period has no positive consumption; an intervening positive period still
requires original attribution. Net income and full source sets remain visible.

New reports retain agent_contract_opening_v1 plus original paid-line membership. Earlier
bound reports retain their previous contract-policy calculation. Cell explanations identify
the single group cap, original principal sources and complete agent net source sets.

## Verification

54 focused cases cover the group cap, mixed principal/agent evidence, signed period sources,
zero-consumption safeguards, original owner checks, net-only reallocations and old-binding
selection. Populated API scenarios exercise original prepayments and combined cross-member
funding, three currency views, refund/return behavior, explanations and retained report reruns.
Four populated database cases pass in total, including ordinary-contract POB report/rerun
compatibility. Scoped lint, types and whitespace checks pass.

## Remaining scope

Mixed opening/non-opening agent source sets with positive consumption still have no retained
per-source net amounts and are refused. Cross-owner agent POB attribution, cross-entity and
acquired sources, and sources outside the selected historical group remain unfinished.
These limitations are not removed by displaying an aggregate source set.

No deployment and no posting changes.
