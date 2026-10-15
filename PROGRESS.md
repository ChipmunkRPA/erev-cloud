# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Populated option snapshot recovery — October 14, 2026

- Added stored-export/load acceptance for native entered-amount and approved
  discount-times-likelihood options, each OPEN and EXPIRED. Actual commands prepare
  and independently approve activation; stored backup is restored into a new sandbox.
- Four cases passed (42.27s): one exported terms row, unchanged manifest, export reused,
  one group recomputed, no reported derived mismatch, identical terms except tenant id,
  preserved status and revenue credits of zero/open or USD 12,000/expired in both tenants.
- Shared expiry security/rollback/concurrency cases also passed in the preceding run.
  Strict test Mypy, Ruff and diff checks pass. Logs: .run/material-right-snapshot-final.log,
  .run/material-right-snapshot-fixed.log and .run/material-right-snapshot-types.log.
  Initial fixture failures used the wrong ledger column and reused a sandbox name;
  corrected the fixture, without changing restore or accounting behavior.
- Renewal methods, IFRS15 native lifecycle, correction/exercise, migration conversion,
  UI, full release gates and independent accounting acceptance remain open. Full CI on
  165d63c is still live and has a new CSV contract-header conflict failure to investigate.
  Publish verified work directly to main; no deployment.

## Seeded Step 1 event routing — October 14, 2026

- Reproduced the demo-reference failure from the ongoing backend CI: STEP1_EVENT
  lacked a seeded human-review routing rule. Added ROUTE-STEP1-01 with one
  event.approve approver, matching the subject specification and existing kernel floor.
  This closes a seed-coverage gap; the kernel already supplied fallback routing.
- Reference coverage verifies the exact permission/count; evaluation/submission parity
  now covers 39 subject/rule combinations. Seed determinism, routing parity and approval
  floors: 73 passed (24.58s). Strict Mypy for all three changed files and Ruff pass.
  Logs: .run/demo-routing-baseline.log, .run/demo-routing-regression-fixed.log,
  .run/demo-routing-types.log. Initial regression assertions were corrected for the
  output field name and the additional routing case.
- GitHub has no open PRs and only remote main. Continue verified direct-main publication,
  without deployment. Full CI on the older 165d63c snapshot remains in progress;
  its results will not establish acceptance of current main. Release gaps remain open.

## Expiry isolation, rollback and concurrent requests — October 14, 2026

- Added native refusal checks for DRAFT, premature declared expiry, read-only access,
  another entity and another tenant. Injected an engine crash and verified no change
  to head, expiry events, computations, subledger lines, exception rows or OPEN status.
- Reproduced a retry defect: a crashed expiry computation became cached 422. FAILED
  now returns sanitized 500 and abandons that idempotency attempt; the same request/key
  succeeds after recovery. Business quarantine remains validation failure.
- Two competing requests were observed as distinct PostgreSQL waiters on the group
  lock. The holder then took the contract lock without inversion. After release:
  one 201, one 412, one expiry event/head increment and USD 12,000 revenue.
- Both boundary tests passed (44.53s), full typecheck (880 source files plus frontend),
  strict test Mypy and Ruff pass. Logs: .run/material-right-expire-boundaries.log
  (retry baseline), .run/material-right-expire-boundaries-fixed.log and
  .run/material-right-expire-boundary-production-types.log.
- Other-command races, closed-period/deferred failures, exercise/reversal and release
  acceptance remain open. Full CI 165d63c remains live at 32%. No deployment.

## Dedicated material-right expiry — October 14, 2026

- Added expire-material-right with event.record permission, stream preconditions,
  idempotency, group/contract locks, ACTIVE/open/current-kind guards and actual-date
  bounds. Reused posting-period/evidence validation, audit, append/compute and deferred
  jobs. Synchronous computation refusal rolls back; generic event append stays restricted.
- Reproduced and repaired duplicate expiry caused by filtering committed events at the
  request timestamp. Locked guards and current option reads now use latest records;
  explicit known_at reads preserve their cutoff. The two native pricing/activation cases
  now expire, recognize USD 12,000, leave zero allocation and verify balanced subledger
  lines with a 12,000 revenue credit. Replay creates no second event; repeat closure,
  missing/stale preconditions and future dates are refused.
- Broad event/obligation/route/import/read regressions: 56 passed (112.14s). Final lifecycle
  and historical-period assertions: 2 passed (32.49s). Revenue reads are period-end totals,
  while status is daily; a first test incorrectly expected daily revenue and was corrected
  against API-C-10, with a separate prior-period-zero assertion. Full typecheck (880 files
  plus frontend), strict test Mypy and Ruff pass. Logs: .run/material-right-expire-regression.log,
  .run/material-right-expire-period-cuts.log, .run/material-right-expire-types.log.
- OpenAPI, TypeScript, specification and limitations updated. Exercise/reversal, specific
  race/security/closed-period/failure cases and complete release/accounting acceptance remain
  open. Full CI 165d63c is live around 32%, with another demo-reference failure awaiting
  diagnostics. No deployment; publish directly to main.

## Native discount-option calculation — October 14, 2026

- Added ASC606 API cases for discount-times-likelihood: USD 100 expected purchases,
  0.5 incremental discount and likelihoods 0.8/0.5 produce persisted selected SSP 40/25.
  Missing approved likelihood refuses entry with no retained terms; evidence-backed
  estimate approval permits entry, and independent activation retains the USD 12,000
  allocation with zero revenue before exercise/expiry.
- Final cases: 2 passed (31.40s), strict test-file Mypy and Ruff pass. Logs:
  .run/material-right-discount-final.log and .run/material-right-discount-types.log.
  Added an explicit heterogeneous-input annotation found by the strict check.
- Attempting native expiry failed with 422 API-R-30: the generic route requires an
  absent dedicated command. Retained .run/material-right-discount-expiry.log and
  documented the required governed expiry/exercise commands and ledger acceptance.
  These missing commands remain implementation work; no expiry support is claimed.
- Full CI 165d63c is live around 32%. No deployment; direct-main publication.

## Reopen-basis isolation coverage — October 14, 2026

- Reproduced the catalogue-completeness failure: period_reopen_basis had no shared
  row builder. Added its period/entity/state dependencies and registered the builder.
  The existing sweep now proves own-row visibility, foreign-tenant read/write denial
  and no-context denial. Entity-scope checks include the reopen basis and now verify
  forbidden updates/deletes as well as reads/inserts for all five reference cases.
- Fixed two typing issues in touched helpers: explicit obligation-version UUID inputs
  and a real user identity for the loss-provision fixture instead of None.
- Final focused PostgreSQL run: 10 passed (6.93s); strict Mypy on both touched files,
  Ruff and diff checks pass. Evidence: .run/reopen-rls-baseline.log (failure),
  .run/reopen-rls-verified.log and .run/reopen-rls-types-final.log. Earlier Mypy invocations
  used incomplete module-path configuration; final check uses MYPYPATH and explicit
  package bases. No production runtime or schema change.
- Full CI 165d63c remains live around 32%; this focused repair does not establish a
  passing release gate. Original exclusions/noncommercial license retained; no deployment.

## Material-right replacement and activation routing — October 14, 2026

- Verified native term creation followed by an integration's price-only draft replacement:
  the same obligation retains identical immutable terms and exactly one record.
- Baseline activation omitted MANUAL_ENTRY for the human term preparer. MATERIAL_RIGHT
  still kept that request pending; no auto-approval bypass was demonstrated. Routing now
  reads option authors (including represented preparers) and persisted option records.
- Activation-routing regressions: 12 passed (91.18s), including untouched-integration
  auto-approval. A SYSTEM/AUD-FACT represented-preparer fixture plus import checks:
  31 passed (18.19s). Full typecheck, Ruff and diff checks pass. Logs:
  .run/material-right-replacement-baseline.log, .run/material-right-routing-regression.log,
  .run/material-right-routing-facts.log, .run/material-right-routing-types.log.
- Key/product removal, corrections, races, complete historical replacement, UI and
  migration acceptance remain open. Original CI 165d63c is live in demo/performance
  seeding. Noncommercial licensing and publication exclusions retained. No deployment.

## Native material-right draft entry — October 14, 2026

- Added the immutable option-term POST with contracting-entity permission, group/contract
  locks, parent-stream If-Match, DRAFT/no-pending-review checks and atomic computation.
  Invalid method, currency, likelihood or non-option classification leaves no terms
  or computation. Dedicated reads use the contracting entity's date.
- Reproduced and fixed an approval gap: a different term preparer could approve Maya's
  activation submission. Option authors are now excluded by the approval kernel;
  independent review succeeds. AUD-FACT represented-preparer identities are included.
- Activation and route/import/scope checks: 62 passed (151.74s). Final API regressions:
  2 passed (20.43s), including idempotent replay and one contract-bound creation audit.
  Full typecheck (880 source files plus frontend), Ruff and diff checks pass.
  Logs: .run/material-right-native-regression.log, .run/material-right-native-final.log,
  .run/material-right-native-types.log. OpenAPI/TypeScript and command docs updated.
- Corrections, draft replacement/race acceptance, full method matrix, UI, migration,
  populated snapshot and independent accounting acceptance remain open. Original full
  CI 165d63c remains live and is not current-candidate evidence. No deployment.

## Activation approval binds material rights — October 14, 2026

- Found and repaired a review gap before exposing native term entry: adding T-CON-14
  terms after activation submission previously left the approval hash unchanged.
  The baseline review returned 200. Activation content now binds identities and all
  option accounting fields in deterministic order. Contracts without terms retain
  their existing content shape and pending hashes.
- A real API review now returns 409 stale-approval after injected terms, leaves the
  contract inactive with no postings, and succeeds only after fresh submission and
  review. The regression also checks the full bound content, including null fields.
- Full activation suite: 19 passed (121.46s); .run/material-right-approval-regression.log.
  Focused repair: 1 passed (14.05s). Full typecheck and Ruff pass. Baseline evidence,
  implementation boundaries and next entry requirements are recorded in
  MATERIAL-RIGHTS-IMPLEMENTATION.md. Native entry and corrections remain unfinished.
- Full CI 165d63c is still running independently. No deployment; publish directly to main.

## Material-right bundle and reads — October 14, 2026

- Connected immutable option terms to real engine bundles at known_at, with stable
  obligation/estimate keys. Dedicated and embedded obligation reads now return terms
  and status from non-voided exercise/expiry events at the effective and record cuts.
  Contract visibility still governs access; expiry dates alone do not change status.
- Added dedicated-read as_of/known_at parameters, offset validation and regenerated
  OpenAPI/TypeScript schemas. Four database/API tests pass (22.83s): real computation
  receives stored terms; both reads agree; historical absence, event voids and tenant
  isolation hold. Route/import checks: 38 passed (18.71s). Full typecheck (879 source
  files plus frontend) and Ruff pass. Evidence: MATERIAL-RIGHTS-IMPLEMENTATION.md.
- Corrected fixture transaction/head/query-parameter mistakes found by initial runs;
  production guards and expected results were retained. Tests insert terms explicitly:
  native entry, governed corrections, migration conversion and populated snapshot
  acceptance remain unfinished. Full CI 165d63c remains live. No deployment.

## Material-right persistence foundation — October 14, 2026

- Migration 0145 creates immutable T-CON-14 option terms and E-92 option_type, tenant
  RLS, foreign keys, unique obligation and contract lookup index. Database checks
  enforce required discount terms, amount/ratio bounds, same-contract obligation and
  exercise-likelihood estimate, and currency agreement. A composite FK prevents a
  later parent-currency change. Application and owner mutation attempts are refused.
- Added ORM export, shared row builder, snapshot classification, cutoff, dependency
  order and likelihood-reference remapping. Removed obsolete pending-table entries
  and updated inventory assertions and the data-model specification.
- 77 focused schema/RLS/snapshot/architecture checks passed (9.99s); final parent guard
  and migration downgrade/upgrade: 2 passed (7.59s). Full typecheck (878 source files
  plus frontend), focused Mypy, Ruff and formatting pass. Evidence and remaining
  lifecycle work are in MATERIAL-RIGHTS-IMPLEMENTATION.md.
- A broader check found the existing missing period_reopen_basis test-row builder;
  retain that failure for repair. Native term entry, engine bundle reads, API status,
  migration conversion and populated snapshot acceptance are not yet implemented.
  Full CI 165d63c remains live around 30%. No deployment; direct main publication.

## Native material-right gap confirmed — October 14, 2026

- Source tracing shows B3-24 needs implementation, not only another API test: bundles
  always send empty material_rights, T-CON-14 is absent, the dedicated read always
  returns 404 and the embedded read always returns null. Migration capture refuses
  converted option records. Existing engine regressions bypass these missing paths.
- Corrected the limitation and added MATERIAL-RIGHTS-IMPLEMENTATION.md with required
  persistence, governed entry, historical reads, migration, UI and acceptance coverage.
  Preserve the migration refusal until the complete terms path exists. No runtime
  change or claim of product support; full backend CI remains running.

## Renewal benefit-period engine verification — October 14, 2026

- Added eight B3-24 regressions through canonicalization, obligation construction,
  allocation and full-engine posted revenue, for ASC606 and IFRS15. A 12,000 renewal
  right spans 24 months at 500/month when the inception estimate says 24 months;
  without an estimate it keeps the booked 12-month term at 1,000/month.
- A later 36-month estimate does not change inception pricing. A discount voucher
  keeps its own term rather than inheriting the renewal estimate. Tests check exact
  period keys, posted amounts, total, option SSP and obligation dates.
- Initial fixture omitted the explicit MONTHLY_EVEN policy and therefore produced
  daily amounts; corrected the fixture's convention, preserving expected figures.
  A subsequent negative-case fixture used a nonexistent GroupInput field; corrected
  it to replace only the contract input. No engine implementation changed.
- Entire stage-03 suite: 41 passed (3.02s), .run/benefit-period-s03-final.log.
  Strict Mypy, Ruff and formatting pass. B3-24 now distinguishes this evidence from
  still-missing API-entry, answer-key and independent accounting acceptance.
- Full backend CI 165d63c remains running around 29%; existing known failures have
  later repairs. Repo only, direct main publication, no deployment.

## Point-in-time royalty licences — October 14, 2026

- Repaired the API/DB mismatch that rejected the engine's supported point-in-time
  royalty licence template. Migration 0144 permits only the LICENCE/ROYALTY exception;
  non-licence obligations remain restricted. Updated T-REF-23's documented constraint.
- API-driven RPO tests verify a 15,000 statement against a 12,000 guarantee adds 3,000,
  recognition waits for delivery, April delivery releases 15,000, and a May downward
  correction reverses 1,000. Both initial delivery states reconcile with zero unexplained.
- Initial tests exposed template rejection; the next attempt exposed a missing trigger
  in the new delivery fixture. Corrected fixture and expanded checks: 4 passed (21.56s).
  Final full template/RPO files and DB invariant: 22 passed (70.78s), recorded in
  .run/rpo-royalty-regression.log. Full production typecheck, focused report-test Mypy,
  Ruff and formatting pass. Standalone Mypy of all selected test files encountered
  existing fixture-import/row-typing issues; it is not claimed as passing.
- Fresh closed browser gate bce381c passed 10/10 and retained 22 PNGs after cleanup;
  see BROWSER-2026-10-14.md. Full backend CI 165d63c remains in progress.
- B4-2's combined cases and other release limitations remain open. No deployment or
  accounting sign-off; publish directly to main without a PR.

## Sandbox reset source isolation — October 14, 2026

- B7-5's source-provenance observation is permitted by SBX-02, which requires creation
  events in both tenants. The refused-type audit defect was repaired in 1ab522c.
- Strengthened SNAPSHOT and EMPTY reset acceptance to compare every tenant-scoped source
  row's full contents outside audit head/events, notifications, outbox and snapshot metadata.
  Existing assertions still check the expected provenance events, snapshot successor target,
  source row-count restrictions, old-sandbox archival and successor results. The populated
  K-03 case explicitly requires nonempty contract and subledger rows before comparison.
- First accounting-table comparison: 2 passed (29.63s). Broadened source comparison:
  2 passed (29.44s). Ruff and strict test Mypy pass. Logs .run/sandbox-reset-source-
  {contents,all-rows,types-final}.log. Separate local repair server stopped.
- Updated browser gate documentation to locate screenshots/traces via the report's artifacts
  field. Fresh closed browser gate bce381c and backend CI 165d63c remain live. These checks
  do not establish full CTL-043, release acceptance or accounting sign-off.

## Outstanding release verification

These checks need current release-candidate evidence. Historical October 3 results
remain in the dated build history; they do not verify current main. This list does
not authorize deployment, provisioning or changes to a live database.

- make audit-deps: October 14 development audit passed; rerun on a clean final candidate.
- SUPERVISOR VERIFICATION NEEDED: make docker-build
- SUPERVISOR VERIFICATION NEEDED: make compose-verify
- SUPERVISOR VERIFICATION NEEDED: make zap-baseline
- make tf-validate: October 14 development validation passed; rerun on a clean final candidate.
- SUPERVISOR VERIFICATION NEEDED: make backup, make restore-verify (isolated local drill only)

## Historical release record

The earlier build-loop notebook is preserved in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).
Current outstanding implementation and verification gaps remain in
[the release limitations](docs/release/LIMITS-1.0.md).
