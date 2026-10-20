# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## Dated fixed allocation for historical RPO — October 20, 2026

- Stage 09 retains original fixed allocations by reporting period and version date, including
  returns. Historical reads reconcile this evidence to version remainders without counting
  return reductions twice; legacy traces keep their existing behavior.
- Earlier RPO excludes later fixed estimate changes. Same-version rollforwards attribute VC
  movements only when complete original event shares match the dated allocation difference.
  Positive and negative first-batch estimates are covered using real engine trace output.
- Historical future schedule reconstruction after later modifications remains open; the
  scheduled-remainder check still refuses unsupported schedules rather than prorating them.
  Compound competing causes and independent accounting acceptance also remain open.
- 109 focused tests plus two database report journeys pass; Ruff and targeted mypy pass.
  Migration 0213 describes the evidence. No deployment.


## First-entry batch estimate attribution — October 20, 2026

- Initial disclosure entry now separates later original estimate-event shares from NEW_CONTRACTS
  into VC_ESTIMATE_CHANGES, including signed decreases. Event dates and shares come from the
  original version's causes and retained trace; inception estimates remain part of entry.
- This path requires complete shares, all later changes through the range end, and no competing
  modification/cancellation. Earlier cuts before a batched fixed-price change still need dated
  fixed-allocation/remainder evidence; this change does not repair those earlier balances.
- 27 focused tests and the DB first-batch usage test pass; lint/types and migration 0212 checked.
  No deployment or independent accounting sign-off.


## Explicit measurement-only estimate evidence — October 20, 2026

- Stage 08 now retains whether an estimate changes measurement only, is absorbed at inception,
  or routes a later allocation change. The report accepts a measurement-only pin as explicit
  zero allocation impact after verifying its original estimate-version reference. Missing or
  legacy pins and inception changes remain unsupported for this decomposition.
- The flag is emitted after contract royalty-accrual routing is resolved, so those reallocating
  estimates are not incorrectly labelled measurement-only. No posting amounts were changed.
- The actual J-06 approval-to-report journey passes: September modification 150,000.00,
  VC change 200,000.00, revenue/restatement -91,463.41 and closing RPO 658,536.59 USD.
  This journey applies approvals separately; it does not claim one combined approval.
- 56 scoped engine/report tests, Ruff and targeted mypy pass. Migration 0211 updates the report
  calculation description. Independent accounting acceptance remains open; no deployment.


## Event-backed mixed RPO changes — October 20, 2026

- Mixed modification/estimate versions now split original estimate-event allocations into
  VC_ESTIMATE_CHANGES and the remaining modification amount. Every event's shares must sum to
  its retained price delta; missing/non-routed events or incomplete shares stay unexplained.
- Signed changes and offsetting zero-net changes are covered. Dated usage remains separately
  attributed. Other competing cause sets and fully batched first-entry decomposition remain open.
- 32 targeted tests pass, including real engine estimate traces and missing-share rejection.
  DB currency/rate replay, lint and types pass. Migration 0210 matches catalogue. No deployment.


## RPO cancellation and re-entry segments — October 20, 2026

- Revenue and late restatement are now measured within each retained disclosure segment.
  Re-entry adds the remaining balance, excluding cumulative revenue already recognized;
  changes while excluded do not become in-scope revenue. A range starting after cancellation
  does not recreate that earlier cancellation. Repeated cancellation/re-entry is covered.
- Cancellation attribution now also runs when the fixed allocation delta is zero, retaining
  recognition for obligations funded entirely by dated realized consideration.
- 29 targeted exemption, source-history and catalogue cases pass, plus three database cases
  for activation and late revenue after restoring the missing EXEMPTIONS zero-row expectation.
  Ruff and targeted mypy pass.
  Migration 0209 records the segmented calculation. These history-level cases do not establish
  that every public contract lifecycle can create every tested history; public lifecycle
  acceptance and competing cause decomposition remain open. No deployment.


## Terminal cancellation RPO attribution — October 20, 2026

- Terminal cancellation now uses retained cancelled-version cumulative revenue to remove only
  remaining RPO. Current-period recognition and prior-period restatement stay in REVENUE and
  LATE_EVENTS. Subsequent cancelled versions retain the latest available revenue evidence.
- Four focused cases cover retained revenue, new revenue, late restatement and reversal;
  missing cancellation evidence is not replaced by a guessed recognized amount. This does not
  complete multi-exit/re-entry histories or competing cause decomposition.
- 21 focused exemption/cancellation/catalogue tests and the database multi-currency RPO
  movement/retained-rate test pass; Ruff and targeted mypy pass. Migration 0208 aligns the
  calculation description. No deployment or accounting sign-off.


## RPO exemption eligibility transitions — October 20, 2026

- Rollforward opening and closing now use their own retained versions for full exemption
  eligibility. A newly exempt closing cannot erase a disclosed opening; leaving an exemption
  is attributed to EXEMPTIONS. Obligations fully exempt throughout remain omitted.
- Four targeted cases cover entering, leaving, unelected and continuing right-to-invoice
  exemptions; endpoint balances agree with standalone RPO. Partial VC exclusions and original
  term evidence remain unchanged. Ten focused exemption tests and seven catalogue tests pass;
  backend lint/type checks pass. The database RPO rollforward tie-out test passes after migration
  0207, which aligns the stored report calculation description.
- This covers changes present in retained obligation versions, not historical policy-election
  changes or every public amendment workflow. Independent accounting acceptance remains open.

## Retained TIME/EVENT input classes — October 20, 2026

- Engine traces retain each input's class and functional TIME total; reporting verifies
  both currencies before attribution. Internally mixed inputs remain unsupported.
- See [scope and verification](docs/release/REPORTING-SOURCE-CLASSES-2026-10-20.md).

## Reporting GL source navigation and inventory — October 20, 2026

- New GL tie-out details retain the source book and period key and link to that exact
  reconciliation in the viewer. Earlier retained evidence without the route metadata still
  renders its amounts without guessing a destination. Re-runs use retained source evidence.
- Incomplete GL comparisons also retain the source link and distinguish missing role,
  unstated amount, missing amount and currency mismatch. Two GL tests, lint and types pass.
- Corrected obsolete B4-3/4/6/8/12 and C-11 inventory claims: 59 of 59 definitions have
  execution paths (55 builders plus four composed reports). Registration is not accounting
  acceptance; the detailed scenario limitations and independent accounting review remain open.
- Necessary verification: two focused GL backend tests and the offsetting-role viewer test
  passed; backend lint/type checking and frontend TypeScript checking passed. No deployment.

## Contracting intercompany revenue counterparts and reversals — October 20, 2026

- Revenue control attribution now resolves the contracting entity's INTERCOMPANY_DUE_TO leg
  within the same posting/entry/entity/contract. Original target, selected line, both currency
  amounts and recursively retained paid history must agree. It does not substitute the other
  entity's REVENUE leg or currency. Report evidence explicitly identifies the counterpart role.
- Ordinary computation history captures due-to lines at the original sealed cutoff. New close
  evidence declares the retained revenue roles; old close documents without due-to coverage
  refuse intercompany attribution rather than treating missing history as zero.
- Transaction reversal disclosure now uses the same original counterpart sources and separates
  asset/new-liability effects from consumed opening liabilities. Earlier legacy bindings retain
  their original builder. Functional/reporting intercompany relief uses the retained source proof.
- Presentation bridge v6 includes source-backed same-currency groups as well as foreign groups,
  including a return-month-only range whose original consumption predates the range. Earlier
  v1-v5 bindings retain their scope. Migration 0206 describes the expanded report logic.
- Real approved cross-company progress scenario: one member advances GBP 8,000; another member
  performs through AVM-US and recognizes GBP 4,000 in May, then revises progress to recognize
  GBP 2,000 cumulatively in June. Full-range opening relief remains GBP 4,000; June alone has
  GBP -2,000 revenue and zero opening relief because the reversal creates a new liability.
- Necessary checks passed: approved intercompany progress reversal in transaction/functional/
  reporting views, full-range and reversal-month-only identical reruns, ordinary cross-member
  return regression, real FX close evidence, catalogue migration, scoped lint and types.
- Mixed TIME/EVENT source allocation remains unimplemented in the generic close-release part
  interface. Current public ordinary revenue binding leaves released_at_close empty and posts
  relief as EVENT; do not infer TIME ownership from period-end source dates. Performing-side
  cross-calendar cases, close-only revenue histories, complex group changes and other documented
  release gaps still require work. No deployment or production-readiness claim.

## Cross-member billing asset settlement and excess liabilities — October 20, 2026

- Functional/reporting billings now retain signed asset-settlement amounts and both sides of
  cross-member asset transfers from the original billing layers. Layer currencies, transaction
  totals, functional amounts and trace identities must already reconcile before presentation.
- Asset bridge v2 distinguishes billing that settles an asset from excess billing that creates
  a liability, including when the invoice issuer has no asset of its own. Both billing roles
  and corresponding member adjustments follow original source amounts, never unexplained OTHER.
  Monthly and whole-range amounts are bound; earlier asset-bridge v1 bindings retain their path.
- Billing and revenue-return asset transfers are combined without replacing either population.
  The billing source method is recorded even for empty populations, preserving rerun scope.
  Migration 0205 documents the expanded report logic.
- The real foreign combined scenario invoices USD 60,000 after another member recognizes
  USD 54,000: at retained spot .84 it settles GBP 45,360 of the other member's asset and creates
  GBP 5,040 of liability for the issuer. Asset balances close to zero; issuer billing remains
  split across the two roles and no member has unexplained OTHER.
- Necessary checks passed: asset and liability report views in functional/reporting currency
  with identical reruns, cross-member revenue-return regression, catalogue migration consistency,
  scoped lint and types.
- Mixed TIME/EVENT source allocation, intercompany counterparts, remaining close-only histories
  and other documented implementation/release gaps remain open. More complex membership and
  mixed billing/credit-memo histories still need end-to-end coverage. No deployment or claim
  of production readiness; independent accounting sign-off remains outstanding.

## Cross-member asset settlement from revenue returns — October 20, 2026

- Functional/reporting revenue returns can now settle another authorized group member's asset.
  The original signed posting replay identifies that asset owner and retains both sides of the
  settlement transfer. Asset settlement is never classified as opening-liability consumption.
- A new asset presentation bridge independently reconciles retained asset-layer carrying with
  presented contract-asset plus unbilled balances at each opening, closing and monthly endpoint.
  Creation, settlement and remeasurement amounts must match their original trace; member
  transfers and group endpoint differences must conserve zero. OTHER does not determine the
  adjustment. Every consumed layer and endpoint/source-transfer amount is bound for rerun.
- The revenue asset-source method is retained even when no transfer occurs, preserving scope
  on rerun. Earlier bindings keep their original method. Migration 0204 records the expanded
  report logic. Cross-member billing asset settlements still need their own source presentation;
  this change covers revenue-return settlements.
- The real combined foreign scenario recognizes revenue for two members and then returns the
  second member's delivery, settling the first member's asset at retained spot .84. The return
  generates GBP 45,360 of equal/opposite member transfers and zero opening-liability relief.
- Necessary checks passed: full-range and return-month-only functional/reporting outputs and
  identical reruns, the existing asset-to-new-liability return case, catalogue migration
  consistency, scoped lint and types.
  Mixed TIME/EVENT attribution, intercompany counterparts, remaining close-only histories and
  the other release gaps remain open. No deployment or production-readiness claim.

## Cross-period returns: asset settlement and new liability sources — October 20, 2026

- Original revenue attribution now presents the recognizing member's asset settlements and
  newly created liability sources as well as liability consumption and asset creation.
  Signed liability effects drive the member presentation bridge; newly created liabilities
  do not become opening-liability relief. Foreign-owner asset/new-liability sources remain
  refused until their separate transfer presentation is implemented.
- Bridge v5 includes cross-member relationships whose original consumption predates the selected
  range, so a return-month-only report retains the same original paid history as a full-range
  report. Earlier v1-v4 report bindings retain their scope and presentation path.
- Fixed S14 EVENT classification when a full return leaves zero cumulative transaction revenue
  but a nonzero functional amount from historical rates. A non-time-released obligation now
  keeps that amount in EVENT instead of incorrectly routing it into TIME because zero equals
  zero. This does not invent per-layer mixed TIME/EVENT attribution or repair old sealed journals.
- Real foreign combined scenario: USD 45,000 advance and USD 54,000 delivery produce GBP 43,470
  revenue, including GBP 36,000 original opening relief. A full September return at retained
  spot .84 reverses GBP 45,360, settling the asset and creating a new liability. Full-range net
  revenue is GBP -1,890; September alone reports GBP -45,360 and zero opening relief.
- Necessary checks passed: both currency views and identical reruns for full-range and
  return-month-only disclosures, the prior combined delivery/return sequence, catalogue
  migration consistency, 16 S14 checks, scoped lint and types.
- Migration 0203 describes the source method. Mixed TIME/EVENT source allocation, intercompany
  counterparts, foreign-owner asset settlement, remaining close-only histories and the other
  documented release gaps remain open. No deployment or production-readiness claim.

## Mixed liability relief and own-member asset revenue — October 20, 2026

- Functional/reporting cross-member revenue now accepts original sources that both consume
  another member's liability and create the recognizing member's own contract asset. The full
  posted revenue delta is verified; only liability-consumption sources must match retained
  owner/layer relief. Asset creation remains separately evidenced and is not opening relief.
- Presentation bridge v4 uses the verified total liability relief to correct local member
  replay that initially presents cross-member consumption as asset revenue. The amount comes
  from original source layers, never from OTHER. Opening/current-range relief, asset revenue
  and member transfers reconcile independently; original v1-v3 bindings retain their path.
- A real foreign-currency combined scenario consumes USD 45,000 of July advances and recognizes
  USD 54,000 in August, creating an asset for the excess. After the actual FX close, functional
  disclosure reports GBP 43,470 revenue and GBP 36,000 opening relief. Functional/reporting
  reruns retain their original source amounts. Catalogue migration 0202 describes this method.
- Necessary verification passed: the mixed-source scenario, existing multi-period delivery/return
  disclosure and reruns, catalogue migration consistency, scoped lint and types.
- Mixed TIME/EVENT source allocation remains open: S14 currently computes a proportional
  functional TIME amount without retaining per-source allocation. Do not infer TIME ownership
  from S12 source dates, which also represent EVENT revenue. Cross-owner asset settlement,
  new-liability reversal presentation, remaining close-only histories and other release gaps
  still need work. No deployment or production-readiness claim.


## Outstanding release verification

These checks need current release-candidate evidence. Historical October 3 results
remain in the dated build history; they do not verify current main. This list does
not authorize deployment, provisioning or changes to a live database.

- make audit-deps passed on clean 74bd148 (October 15): all 86 pinned Python runtime packages and npm runtime dependencies report zero advisories. Rerun on the final candidate.
- make docker-build passed on clean b4b8210 (October 15); rerun on the final candidate.
- make compose-verify passed on clean 74bd148 (October 15), including cleanup. Rerun on the final candidate.
- make zap-baseline passed on clean 4c4b583 (October 15), including cleanup; one documented low COEP warning and three informational alerts remain. Unauthenticated surface only; rerun on the final candidate.
- SUPERVISOR VERIFICATION NEEDED: make tf-validate (October 14 backend-disabled development validation passed; rerun on a clean final candidate).
- make restore-drill passed on frozen d7e8715 (October 15), exercising backup and restore-verify
  on a fresh disposable server. Rerun on the final candidate; hosted recovery is outside this scope.

## Historical release record

The earlier build-loop notebook is preserved in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).
Current outstanding implementation and verification gaps remain in
[the release limitations](docs/release/LIMITS-1.0.md).
