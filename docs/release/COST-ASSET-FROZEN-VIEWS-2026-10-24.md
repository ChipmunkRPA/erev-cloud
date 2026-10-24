# Frozen cost-asset report views — 2026-10-24

New period locks retain category and original-asset cost rollforwards in transaction,
functional and reporting currency at one cutoff. The six variants share one hashed snapshot
file; metadata, row identities, counts and granularity are validated before selecting rows.
Locked report JSON and CSV exports use the selected retained variant without live rebuilding.
Historical snapshots without that variant remain readable in their original view and refuse
unsupported asset/currency selections.

Relock comparisons include all three asset views and identify asset transfers even when
category totals remain unchanged. Mixed old/new locks show which detail is available.

Validation: 57 snapshot/selector/freeze unit checks, the targeted PostgreSQL report worker and
CSV export scenario, plus currency codec and relock checks. Scoped lint and types pass.
Stale relock fixture headers were aligned with existing noncurrent contract asset and RPO eligibility columns.
No deployment or accounting posting changes. Foreign cost impairment, reversal, clawback,
delayed capitalisation and foreign split-layer allocation remain separate unfinished work.
