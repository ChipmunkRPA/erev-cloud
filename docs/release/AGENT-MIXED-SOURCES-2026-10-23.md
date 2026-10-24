# Mixed original sources in agent opening-income reports — October 23, 2026

New reports retain verified net income and the complete original source set even when a net
posting combines opening and current receipts. No per-layer net amount is inferred. The portion
from opening receipts is null where the original evidence cannot determine it; it is not zero.

Contract and POB FIFO use this presentation in transaction, functional and reporting currencies.
Affected currency summaries are null, incomplete currencies are omitted from complete opening
totals, and control metadata labels the result INCOMPLETE. Known subtotals contain only fully
resolved rows and are not a complete currency total. The viewer explains this distinction;
CSV and other table exports carry the row explanation. Net-income drill-down remains available
with complete sources; an unavailable opening cell does not produce a fabricated numeric drill.

The new availability evidence is retained and compared on rerun. Older saved reports lacking
that evidence retain their prior admission rules. Neither journal amounts nor revenue timing
change. Original source identity/date verification remains mandatory; missing evidence still
fails rather than becoming an unavailable allocation.

## Necessary verification

65 focused backend cases and 3 viewer cases pass; scoped Python/TypeScript checks and lint pass.
One populated API scenario passes across both FIFO policies and all three currency views.
Focused backend and viewer cases cover mixed sources, unknown values, period evidence, CSV,
net-income drill-down and saved evidence comparison. The populated API scenario uses two
45,000 receipts, one before the opening date and one in-period, followed by deliveries and a
return; both FIFO policies and all three currency views are exercised, including saved reruns.
Its reviewed principal/agent judgement is seeded in the fixture; this is not a claim that the
principal/agent approval workflow was exercised by this scenario.

## Remaining boundary

The original postings still do not specify a unique per-layer or opening/current net allocation;
the owner-selected aggregate presentation makes that uncertainty explicit. Cross-entity/acquired
sources and source owners outside the selected historical group remain separate unfinished work.
No deployment. No claim that all Reporting or repository work is complete.
