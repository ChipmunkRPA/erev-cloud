# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## Retained subledger / GL / report bridge — October 20, 2026

- Balance and rollforward GL controls now expose retained subledger balances, subledger-minus-GL
  and report-minus-subledger per entity/role in functional currency. Either nonzero leg fails,
  even if the report and GL agree. Missing subledger evidence remains explicitly unavailable.
- The viewer shows both backend-calculated legs alongside the original GL source link. New v2
  bindings retain three-way semantics; v1 reruns preserve the original two-way control without
  live GL reads. Migration 0219 documents both consumers and repairs stale balance FX sources.
- Three focused backend cases, the viewer case and uploaded-trial-balance DB journey pass;
  lint/types and migrated catalogue checks pass. The foreign-balance DB journey fails during
  close DATASET_FREEZE before report comparison, including with the original GL implementation.
  That existing failure remains open; this is not full multicurrency acceptance.
- Multi-provenance TIME/EVENT attribution, broader lifecycle coverage and independent accounting
  sign-off remain open. Direct main publication only; no deployment.


## Mixed TIME/EVENT input with unique source — October 20, 2026

- Stage 14 retains signed TIME amounts in both currencies for each single-input part. A
  multi-input part explicitly remains unresolved; the report introduces no allocation ratio.
- Revenue attribution can split an internally mixed input when every original source agrees
  on contract, layer, movement kind, effective date and source key. Both currency TIME totals,
  transaction sources, prior targets and paid history remain reconciled to original evidence.
- 35 scoped posting/source tests pass, including negative input amounts, offsetting TIME/EVENT,
  zero-net figures and ambiguous provenance rejection. Original S14 functional allocation is
  preserved. The DB intercompany progress-reversal journey, lint/types and both migrated IPE
  definitions pass. Migration 0218 describes the balance/opening-liability consumers.
- Mixed multiple-provenance sources, legacy traces without exact input amounts, split-role
  inputs and non-revenue components remain open. This is not acceptance of every public mixed
  workflow; independent accounting sign-off remains outstanding. No deployment.


## Original-cut manual schedule projection — October 20, 2026

- Fixed-only deterministic schedules now replay manual release, manual defer and schedule
  override formulas against original allocation segments and events effective by the report
  cut. Future manual changes and later estimate allocations do not backfill that projection.
  Every applied adjustment retains its formula, parameters and input chain for trace replay.
- Six real engine cases compare each adjustment kind with a later release or estimate change;
  projected future periods match the original pre-change calculation. Frozen contract-status
  cuts are excluded from time-based projection. 99 scoped tests pass, including hold/manual
  ordering and rejection of explicit unavailable evidence. Two DB report journeys, lint/types
  and all three migrated IPE definitions also pass verification.
- Mixed fixed/realized or netted adjustments and snapshots that cannot reproduce original
  revenue retain an explicit projection error; reports do not silently use the latest schedule.
  Missing calendar/terms, legacy evidence gaps, compound lifecycle/API acceptance and independent
  accounting sign-off remain open. Migration 0217 records scope. No deployment.


## Dated recognition-hold remainder classification — October 20, 2026

- Stage 09 retains the scheduled remainder and its hold/pattern evidence at each measured
  period, plus a version-state reconciliation. Contract/report reads use that dated amount
  and derive awaiting-trigger remainder from the independently reconciled total.
- A later hold no longer changes an earlier cut's scheduled/awaiting split. Held cuts show
  awaiting-trigger remainder; release restores the time-based scheduled remainder. Future
  hold/release events also trigger the original-segment schedule projection for earlier cuts.
- Real engine hold-only and hold-then-release cases cover January before hold, February held,
  and March held/released; all trace nodes replay. Missing state/series and mismatched states
  are refused. 117 scoped tests pass; DB regressions and migration 0216 verified before publish.
- This does not complete arbitrary manual adjustment projection or combined hold/modification
  lifecycle acceptance. Legacy evidence gaps, missing original calendar/terms, broader mixed
  attribution and independent accounting sign-off remain open. No deployment.


## Historical periods survive removed schedule lines — October 20, 2026

- Original fixed period projections now have independent trace nodes, including periods whose
  current schedule line disappeared after a later allocation change. The engine projects over
  the retained performing-entity calendar and original segment term.
- RPO and revenue waterfall read these periods directly, reconcile their sum, and explain each
  through its obligation version, reporting cut and future period. Existing currency conversion
  uses the same projected contributions; no synthetic posted schedule line is created.
- A real engine case reduces the later allocation to zero: original January future amounts
  remain in RPO and waterfall even with no current schedule rows. Trace replay, trimming,
  incomplete-evidence refusal and explain selection are covered. 115 scoped tests and two DB
  journeys pass; lint/types and migration 0215 checked against all three IPE definitions.
- Missing original calendar/terms, held or manually adjusted cuts, legacy traces without the
  new evidence and complex mixed lifecycles remain open. Independent accounting acceptance is
  outstanding. No deployment.


## Historical time-based schedule projection — October 20, 2026

- Stage 09 now freezes the original deterministic allocation segment at cuts before later
  fixed-allocation changes, retaining progress, exact targets and posted differences. RPO bands
  and revenue-waterfall future periods use this dated evidence and reconcile it to the remainder.
- Explain links name the exact cut, so a historical projected amount does not open the latest
  fixed schedule. The original retained schedule source remains available for drill-through.
- Real engine increase/decrease cases reproduce the pre-change future schedule by period;
  all trace nodes replay. Targeted report, reader and explain checks and two DB journeys pass.
- Still open: periods absent from the retained source schedule, missing original segment terms,
  adjusted/held cuts and broader compound lifecycle attribution. These paths retain explicit
  refusal, not proportional reconstruction. Independent accounting acceptance remains open.
  Migration 0214 records the calculation for RPO, its rollforward and the waterfall. No deployment.


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
