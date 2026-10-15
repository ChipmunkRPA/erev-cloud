# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Persisted entered option SSP and native workflow — October 14, 2026

- Revision 0146 adds immutable optional total SSP with method/nonnegative constraints.
  Native entry enforces contract currency; reads, bundle assembly, activation approval
  content and workbench entry/display preserve the amount. Absence retains catalogue
  selection and old approval content. Updated OpenAPI/types and user/data-model docs.
- Native entry proves USD 123.45 persists as selected SSP for quantity 50, with idempotent
  retry, separate activation reviewer and bound approval content. Final native/migration
  checks: 5 passed (46.85s). Four snapshot cases (explicit/discount, open/expired) and
  approval binding passed in preceding runs. Invalid method/currency/negative entry and
  API/bundle reads also passed. Initial downgrade fixtures had shared data and owner RLS
  issues; corrected with transaction-scoped fixture data and verified refusal/round-trip.
- Schema/ORM/migration/snapshot checks: 80 passed; removed a stale pending option_type
  enum entry now implemented by 0145. UI: 16 passed; full typecheck: 881 sources/frontend;
  strict test types, Ruff, ESLint and production build pass (existing chunk advisory).
  Logs: .run/entered-option-persisted-final.log, .run/entered-option-native-final.log,
  .run/entered-option-native.log, .run/entered-option-schema-final.log,
  .run/entered-option-ui-final.log and .run/entered-option-native-types.log.
- Migration capture/promotion remains unfinished and refuses option records. No deployment
  or readiness claim. Older immutable CI 165d63c remains live at 37%.

## Explicit entered option SSP engine path — October 14, 2026

- Added optional per-option total SSP in contract currency. Stages 03 and 05 preserve
  the entered amount instead of repricing against a shared catalogue; quantity does not
  multiply it. Wrong method/currency and negative/nonfinite values refuse computation.
- Input hashes bind explicit values while absent values keep the previous hash shape.
  Old evidence decodes with None. Source-record trace evidence and formula reevaluation
  preserve the actual option amount without claiming it came from the catalogue.
- 397 engine stage-03/stage-05/kernel/upgrade tests passed (29.12s), including 13 new
  tests covering allocation, ASC606/IFRS15 shared catalogue options, total semantics,
  hash compatibility, codec replay and invalid inputs. Strict Mypy: 880 production
  sources plus the new test file; Ruff passes. Logs: .run/entered-option-engine-final.log,
  .run/entered-option-production-types.log and .run/entered-option-types.log.
- Persistence, command/read/UI, adapter, snapshot/export and migration promotion remain
  unfinished. Capture's option refusal remains. No readiness claim or deployment.
  Older CI 165d63c is still running at 36%; it is not current-main release evidence.

## Entity-scope reconciliation verification — October 14, 2026

- Reproduced two CI failures in entity-scoped CSV contract quarantine. Both correctly
  committed the admitted contract; exact legacy total assertions rejected the newer
  amount_sums and monetary_checks fields. Assertions now require only EVE-UK-0002/0003
  in the respective stored evidence, matching source/stored lines of USD 96,000 and
  24,000, USD 120,000 total, and exact loaded/quarantined counts. Refused contracts and
  partial contract writes remain prohibited by the existing persisted-row checks.
- Initial full file: 40 passed, 2 stale assertions failed (246.11s). Both corrected cases
  plus out-of-scope submit/cancel denial: 3 passed (24.61s). Strict test Mypy and Ruff pass;
  an empty command-body tuple received an explicit type. Logs: .run/import-scope-baseline.log,
  .run/import-scope-fixed.log and .run/import-scope-types.log.
- Audited migration conversion: staged option SSP equals original quantity times price,
  but T-CON-14/bundle inputs do not preserve that per-option entered amount. Quantity-one
  conversion cannot safely reuse a shared catalogue point. Recorded the dependency and
  two-options/same-catalogue acceptance case in MATERIAL-RIGHTS-IMPLEMENTATION.md.
  Conversion refusal remains until the complete amount/promotion/replay path is implemented.
- Older full CI 165d63c remains live at 35%. No readiness claim or deployment; publish to main.

## Native option workbench controls — October 14, 2026

- Obligation Overview now displays persisted option terms/status and links its likelihood
  estimate. Entity-scoped, current-view controls permit draft entry and active/open expiry.
  Forms support the three SSP methods, approved applicable likelihood selection, decimal
  strings, dates, expiry reasons/evidence, ETag/idempotency and cache refresh/refusal handling.
- Queued expiry retains job progress, prevents duplicate submission, and distinguishes
  recorded expiry from failed computation. A failure never claims the event rolled back.
  Embedded terms now use MaterialRightOut in OpenAPI instead of an untyped dictionary.
- UI/workbench regressions: 79 passed; final option/evidence-link suite: 14 passed.
  API/read/import-cycle checks: 34 passed (27.93s). Full typecheck (880 sources/frontend),
  final frontend types, ESLint and Ruff pass. Desktop/mobile form captures were inspected;
  five screenshots in .run/option-*.png, browser reported no page errors.
- Logs: .run/material-right-ui-tests-final.log, .run/material-right-ui-tests-last-fixed.log,
  .run/material-right-ui-api-fixed.log, .run/material-right-ui-full-types.log and
  .run/material-right-ui-visual.log. Initial checks caught a closed drawer and loose schema;
  fixture corrections covered select events, currency reference and the API test filename.
- This is component/API evidence, not live full-browser accounting acceptance. Governed
  exercise/correction, migration and release/accountant sign-off remain open. Build passed; no deployment.

## Native option creation failure recovery — October 14, 2026

- Reproduced an injected engine crash being returned as cached 422 during native option
  entry. Creation now aborts FAILED computation with sanitized 500, rolls back its facts
  and abandons that idempotency attempt. The identical request/key succeeds after recovery.
- Known incomplete option inputs/missing dated likelihood pins use a specific ValueError
  subtype, caught as validation by native entry. Unrelated ValueError crashes are not
  classified as bad terms. Missing approved likelihood and business refusals retain 422.
- The regression checks unchanged DRAFT/head, terms, computations, events, ledger and
  exceptions after failure, then successful retry/replay and independent activation review.
  API entry/invalid/discount cases plus the stage-03 suite: 45 passed (62.35s).
- Full typecheck (880 source files plus frontend), strict test Mypy, Ruff and diff checks
  pass. Logs: .run/material-right-create-retry-baseline.log,
  .run/material-right-create-retry-fixed.log and .run/material-right-create-retry-types.log.
- Full CI on older 165d63c remains live at 34%. Exercise, correction, migration/UI,
  broader release acceptance and independent accounting review remain open. No deployment;
  publish reviewed changes directly to main.

## CSV quarantine reconciliation assertions — October 14, 2026

- Reproduced two failures observed in the ongoing backend CI. Contract-header conflict
  and bundle quarantine imports correctly committed only valid objects, but their tests
  rejected the newer amount_sums and monetary_checks fields in control totals.
- Updated assertions retain exact loaded/quarantined counts and now require matching
  source/stored reconciliation evidence. Only SF-ORD-31004 contributes its USD 96,000
  and 24,000 lines (USD 120,000 total); only the accepted bundle component is reported.
  Existing checks still require no refused contract and no partial bundle replacement.
- Both complete files pass: 14 tests in 64.80s. Strict test Mypy, Ruff and diff checks pass.
  Logs: .run/csv-quarantine-baseline.log (2 failed, 12 passed),
  .run/csv-quarantine-fixed.log and .run/csv-quarantine-types.log.
- Rechecked publication: repository PUBLIC, default branch main, PolyForm Noncommercial
  retained, and neither research-harness nor docs/research tracked. Full CI on older
  165d63c remains live; release acceptance and accounting sign-off remain outstanding.
  No deployment. Publish reviewed changes directly to main.

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
