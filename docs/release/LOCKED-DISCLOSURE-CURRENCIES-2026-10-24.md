# Multi-currency locked disclosure packs — October 24, 2026

## Delivered

New ASC606 and IFRS15 lock approvals capture transaction, functional and reporting disclosure
inputs from the same held read-only transaction and source cutoff. Each view retains its own
parent, original child runs, seven immutable chapter snapshots and original FX evidence.
All three views publish in one decision transaction; a damaged or incomplete variant cannot
leave a partially published lock. The combined capture also respects the retained-input limit.

The report viewer sends the selected currency for locked disclosure packs. Public reads,
exports and reruns apply the same currency scope as the worker and SQL visibility check.
They reconstruct from the selected original snapshots, without current policies, builders,
source rows or rate lookup. Existing transaction-only locks remain readable; requesting an
unavailable currency refuses explicitly. No backfill or silent translation is performed.

## Necessary verification

- Public disclosure lifecycle: all three captured views, separate snapshot identities,
  failed-last-view rollback, selected-view generation and digest-identical reruns. The older
  transaction-only lock rejects functional/reporting requests; legacy JSON/XLSX/PDF exports
  continue to rebuild while live policy capture is disabled.
- Actual close approval: one lock retains three succeeded parents, each with sixteen monthly/
  quarter child sources and seven snapshots; existing close-step audit behavior is preserved.
- Focused lock-selector/planner tests and frontend lock-currency tests; scoped lint and types.

The all-view frozen lifecycle fixture is empty and the close fixture uses its existing business
population. Distinct foreign numerical translations remain covered by the prior live-pack and
cost reporting checks documented in REPORTING-DISCLOSURE-2026-10-24.md; this checkpoint does not
claim every historical foreign/acquisition/agent combination is supported.

## Remaining boundaries

Broader acquired-source public workflows, mixed signed original FX attribution and combined
contract reassessment/partial removal remain separate development items. Shared breakage
application still needs the expected-redemption rule identified in the current scope; the
owner's accepted total/SSP allocation and shared-over-member priority are unchanged.

Published source only; no deployment or real-business promotion is part of this change.
