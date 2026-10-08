# Exact reconciliation role freshness — October 8, 2026

Continued from main `364ba52520dfc942a17c678004c0eee94145c052`. Repository-only work;
no deployment, cloud mutation or independent accounting sign-off.

## Finding and change

B1-29: a reviewed GL reconciliation was considered current using only ledger chain
position and document counts. Publishing another contract-liability account mapping
can change its comparison basis while neither proxy changes. The PostgreSQL/API
regression reproduced this: the prior gate still returned PASSED with both required
reconciliations reviewed. Baseline: **one failed in 11.38 seconds**.

The attachment's existing account/role/balance readers now live in
`backend/erev_api/domain/close/reconciliation_balances.py`. Their function/class ASTs
were compared with the prior definitions and were unchanged by extraction. Both the
attachment and freshness check use those readers; no accounting formula was recreated.

The gate re-reads contract liability, contract asset and unbilled receivable using the
current committed ledger chain and a knowledge cutoff covering the server timestamp,
its supplied application timestamp and the signed snapshot. It compares signed role
amounts with Decimal precision, account codes, currency, and not-stated reasons and
contract identities. The trial-balance comparison omits roles where neither side nor
an item holds anything; an omitted zero role continues to mean zero. A newly nonzero
or unreadable role cannot be mistaken for that omitted zero.

The resulting outdated IDs join the existing unsigned population without double
counting. The blocker count, gate member identities and reviewed KPI all use this
comparison. Existing chain/count predicates remain necessary. Historical CERTIFIED
rows retain their lock semantics; this change targets current REVIEWED/AUTO_CERTIFIED
rows with a trial balance attached. Billing reconciliation behavior is unchanged.

## Verification

- New mapping-change witness against the old gate: **one failed, 11.38 seconds**;
  `/private/tmp/recon-role-freshness-baseline.log`.
- Initial fixed witness: **one passed, 11.83 seconds**;
  `/private/tmp/recon-role-freshness-fixed.log`.
- Reconciliation freshness, GL comparison, gates and lock domain suites:
  **72 passed, 227.16 seconds**; `/private/tmp/recon-role-freshness-domain.log`.
- Extended API witness, including actual lock-request refusal and successful regeneration,
  preparation and review: **one passed, 12.65 seconds**;
  `/private/tmp/recon-role-freshness-recovery.log`.
- Final close-unit suite: **420 passed, one failed, 1.74 seconds**;
  `/private/tmp/recon-role-freshness-unit-final.log`. The failure is the existing
  `test_the_producer_keys_pin_summarise_and_completeness_read_the_same_facts`:
  the producer includes `validation_execution_id`, while the close-world fixture
  does not. Its test, producer and fixture files are unchanged by this repair.
  This is still an open verification issue; no full unit-suite pass is claimed.
- Ten new pure comparison tests are included among those passing units: changes to
  each role in both directions below the currency minor unit, account/currency/role
  identity, duplicate or missing rows, zero omission and not-stated evidence.
- Mypy for the three affected source modules, Ruff and whitespace checks pass.

The API witness uses the normal mapping submission/approval and reconciliation
preparer/reviewer workflows. It explicitly verifies unchanged chain position and
ledger-document counts. This evidence does not assert a full current backend/CI,
large-volume or concurrent policy-transition pass. Those gates and independent
accounting sign-off remain outstanding.
