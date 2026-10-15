# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Complete opening output reproduction — October 14, 2026

- Promotion preflight replays verified retained inputs and requires the captured full output
  hash. It rebooks the confirmed plan against current configuration inside a child savepoint
  and compares every output field except the input hash (fresh identities/time). No book,
  trace, posting, schedule or diagnostic is excluded. Review basis v2 binds result hashes.
- PostgreSQL witness: 3 cases passed (12.78s), including later observation time, bad output
  hash, missing template, IFRS15 enabled after capture, changed diagnostics and rollback.
  126 domain/job/repository/architecture checks passed (17.23s); strict production Mypy
  (887 sources), changed-file Mypy and Ruff pass. Logs: .run/migration-reproduction-*.log.
- Policy/report/activation checks, configuration locking, atomic live creation and independent
  approval/MFA remain unfinished. Public option import/promotion remain guarded. Negative
  testing also found stage 03's raw ValueError for AGENT without reviewed PRINCIPAL_AGENT;
  typed admission handling remains outstanding. Older immutable CI remains live at 53%.
- Published directly to main; no deployment, readiness or accounting sign-off claim.

## Retained opening choices and input reconstruction — October 14, 2026

- Successful imports retain complete confirmed parameters/entity mapping and staging/plan
  hashes. Promotion review restores from retained source/cutover and compares bookings,
  opening balances, customer identity and immutable option terms with captured input.
  Missing plans require re-import; no current defaults are substituted.
- A newly hashed plan with changed conversion or entity mapping refuses against the original
  capture. Decimal option terms compare exactly (25 equals stored 25.0000); no rounding.
- The registered import worker with non-identity mapping retains a reconstructable four-
  contract plan: 1 check passed (12.72s). Domain/import/reconciliation/architecture checks:
  70 passed (9.96s). Three converted-option database checks passed (12.10s), covering
  missing/changed plans and review invariants. Strict production Mypy (886 files), two test
  files, the final plan helper and Ruff pass. Evidence: .run/migration-opening-plan-*.log.
- Output reproduction under current configuration, policy publication, activation admission
  and independent approval/live creation remain unfinished. Public option import/promotion
  stay unavailable. Older immutable CI is live at 52%; no deployment/readiness claim.

## Durable migration promotion review basis — October 14, 2026

- Extracted the shared read-only reconciliation assessment and added promotion review of
  retained evidence. It requires RECONCILED/SUBMITTED opening-balance status, reassesses all
  figures, verifies source-row hashes and requires the complete stored line set to match.
- The review fingerprint binds source/capture/reconciliation artifacts and the recorded
  profile, including replayed SSP references. It stays stable across SUBMITTED and changes
  with the SSP profile. Review alone writes no audit events or live contracts.
- Three PostgreSQL cases passed (9.56s), including missing/duplicate/changed stored-line
  refusals and status/profile binding. 68 related checks passed (9.20s); strict production
  Mypy (885 files), test Mypy and Ruff passed. Logs: .run/migration-promotion-review-*.log.
- This is a foundation for promotion, not the approval subject: current configuration/report
  checks, policy publication, activation admission, reproduction and atomic live creation,
  independent reviewer/MFA and submit route remain unfinished. Public option import stays
  unavailable. Older immutable CI remains live at 46%; no deployment/readiness claim.

## Evidence-bound option quantity reconciliation — October 14, 2026

- Reconciliation consumes verified producing bundles and explains only the exact POL-212
  quantity conversion. Contract/obligation/product, quantity-one booking, currency and total
  option SSP must match source facts. Reports retain source 10, actual 0.4 and difference
  -9.6 with a named policy explanation; no source, trace, money value or golden file changes.
- Exact expected-quantity checks reject drift and the deceptive case of 10 native options
  numerically matching 10 source dollar-units. Conflicting quantity explanations refuse.
  No monetary discrepancy receives the conversion explanation; replay behavior is unchanged.
- The actual platform-capture/database witness now runs default reconciliation readers over
  retained evidence and reaches RECONCILED. Two altered-quantity/digest cases refuse without
  lines or status transition. Three database checks passed (13.30s); 93 focused domain,
  repository/job/report/architecture checks passed (10.57s). Logs:
  .run/option-reconciliation-pg.log and .run/option-reconciliation-unit.log.
- Strict production Mypy (884 files), two test files and Ruff pass. Logs:
  .run/option-reconciliation-types.log and .run/option-reconciliation-test-types.log.
- Full import/approved promotion remains incomplete, and the public option refusal stays.
  Older immutable CI 165d63c remains live at 46%; no deployment or readiness claim.

## Converted option platform capture witness — October 14, 2026

- Added a PostgreSQL witness through the real platform booking, activation-event, engine,
  persistence and capture-reader path. Published parity templates and an approved legacy
  SSP catalogue support a paid product plus converted option, without mocking computation.
- The option retains total SSP/allocation 25, remaining quantity 0.4, revenue 15 and remaining
  allocation 10. Contract billed total 100, revenue 15 and remaining allocation 85 agree.
  Verified retained input hash/batch/cutover, contract-keyed audit facts, and rollback leaving
  no contracts or option terms. One integration test passed (9.21s); strict test Mypy/Ruff pass.
  Logs: .run/converted-option-capture.log and .run/converted-option-capture-types.log.
- Earlier setup attempts exposed an incomplete stage-only fixture (free option with no paid
  line funding allocation) and missing period-state setup. The final fixture represents the
  complete two-line contract. No engine checks or approval guards were weakened.
- The public capture refusal stays: reconciliation still compares raw legacy dollar-unit
  quantity 10 against option quantity 0.4, and MIGRATION_PROMOTION is unimplemented. Full
  import/reconcile/promotion acceptance remains open. Older CI 165d63c is live at 45%.

## Shared option term persistence — October 14, 2026

- Native entry and the migration applier share validated immutable term insertion. Converted
  records carry their explicit total SSP, quantity-one convention and unclassified OTHER
  subtype; no renewal, expiry or likelihood is invented. Native guards and compute/audit
  ordering remain intact. The migration applier audits only after successful computation.
- 25 focused migration/database checks passed (8.09s), including stored adapter values,
  savepoint parent/term rollback, cross-contract refusal and exact money precision. Six
  native entry/approval/likelihood/rollback cases passed (65.49s). Logs:
  .run/shared-option-writer.log and .run/shared-option-writer-final.log.
- 19 architecture/lock-order checks passed; strict production Mypy (883 files), test
  Mypy and Ruff passed. See .run/shared-option-writer-architecture.log and *-types.log.
- Converted-option capture still refuses until full platform capture, reconciliation and
  approved promotion are verified. MIGRATION_PROMOTION remains unimplemented. This change
  verifies term persistence, not complete import acceptance. No deployment/readiness claim.
- Older immutable CI 165d63c remains live at 44%; it is not current-main release evidence.

## Native command audit coverage — October 14, 2026

- Current catalogue checks exposed missing option-entry, option-expiry and evidence-pack
  create commands. Added successful request scenarios to the full audit walk and catalogue:
  238 command operations, 232 required after the existing six exemptions. Scenarios bind
  audit evidence to the response request id, expected action, actor kind and contract key.
- Material-right facts now require their contract key in the audit writer. Verified the
  stored AUD-FACT summary names the created fact id and contract; it intentionally has no
  single object id/label. Added display labels for evidence packs and control executions.
  CLOSE packs explicitly exercise the existing period-level, no-contract audit shape.
- 26 focused database/catalogue/architecture/read-model checks passed (51.54s); strict
  production Mypy (881 sources), three test files and Ruff pass. Logs:
  .run/audit-catalogue-current.log, .run/audit-new-routes-release.log,
  .run/audit-new-routes-types.log and .run/audit-contract-production-types.log.
  Initial scenarios exposed fixture permissions/combination setup and a mistaken single-
  object label expectation for AUD-FACT; corrected without weakening product checks.
- The category sweep still requires the unimplemented AI proposal lifecycle. No exemption
  or success claim was added. Full current-main route walk/release gates remain open.
  Older immutable CI 165d63c remains live at 42%; no deployment or readiness claim.

## Converted option opening units — October 14, 2026

- Found that POL-212 books quantity one but opening payloads retained dollar-unit quantities.
  Converted payload quantities now divide by source quantity and per-unit rates multiply
  by it. Monetary balances and immutable source/staging rows remain unchanged. Legacy
  KEEP behavior is unchanged; inexact conversions refuse rather than round.
- Regression reproduced 10 remaining units instead of 0.4 for source quantity 25.
  Real API-to-engine adapter and stage-07 witnesses pass under ASC606/IFRS15, preserving
  remaining SSP 10, allocation 62.5 and posted baseline revenue 37.50.
- 45 migration/capture/onboarding tests passed (1.33s); strict production Mypy (881 sources),
  test Mypy and Ruff pass. Logs: .run/option-opening-baseline.log,
  .run/option-opening-final.log, .run/option-opening-types.log and
  .run/option-opening-test-types.log.
- Capture still refuses option records: its writer and MIGRATION_PROMOTION approval
  subject remain missing. No deployment or readiness claim. Older immutable CI remains
  live at 39%, with a new audit-coverage failure to investigate when its evidence is ready.

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
