# Noncurrent contract assets — October 24, 2026

Contract balances now includes a Contract asset, noncurrent money column alongside
its total and current amounts. Contract rows, currency totals, control totals and
the shared report output columns all include it. Re-lock dataset comparisons treat
it as a money measure. The existing report renderer/export paths consume these
columns without a new UI or output-specific schema.

Noncurrent equals displayed total less displayed current. For reporting currency,
both operands have already been translated and rounded; the remainder is not
translated independently. This preserves total = current + noncurrent even when
independent conversion would introduce a minor-unit difference. The change does
not add a financial target or change GL tie-outs.

New reports retain `contract_asset_noncurrent_v1`. Same-source runs lacking that
marker retain their old columns and totals. New close snapshots include the column;
reading an older lock can derive it from its existing frozen total/current amounts.

Necessary checks: the public two-period contract balances case verifies the new
row, total and control amounts and successfully reruns both saved reports. The
original acquisition tests verify nonzero current/noncurrent parts under both
attribution policies. A translation rounding case verifies the displayed identity.
Nine focused native/unit cases and one public database case pass; changed runtime
files pass Ruff/mypy and the diff check. No new cell-explanation endpoint or claim
of completing the separate absent-balance-row gap. No deployment.
