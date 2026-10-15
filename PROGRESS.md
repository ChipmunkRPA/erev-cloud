# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## AI provider foundation — October 14, 2026

- Implemented the DG §6.7 request/response protocol and deterministic FakeProvider.
  Exact input-hash fixtures precede version-local defaults; malformed exact fixtures fail
  without fallback. Digests cover exact UTF-8 response text; token/latency fields and path
  selectors are validated. No sockets, sleeps, accounting writes or external calls.
- Provider/configuration/architecture checks: 92 passed (20.88s); strict typing: three
  sources; Ruff/formatting pass. Evidence: .run/ai-provider-final.log and
  .run/ai-provider-types.log.
- AIX remains incomplete: provider selection/live adapter, retained fixtures, schema,
  gateway/jobs, human acceptance and audit lifecycle still required. No AI enablement,
  audit-category exemption, deployment or readiness claim.

## Reopening report verification — October 14, 2026

- Updated the lock/relock regression for required independently reviewed reopening evidence:
  preserve the hold/release versions, verify the billing version at the latest event date,
  and independently approve the specific late-event waiver through the normal API.
- The real re-close leaves September revenue and RPO unchanged, while contract balances
  reflect the invoice. All five report-figure cases pass (44.05s); strict test typing,
  Ruff and formatting pass. Evidence: .run/report-lock-recheck.log and .run/report-lock-types.log.
- AI audit coverage, other documented implementation gaps and full candidate verification
  remain open. No production-readiness claim or deployment.

## Migrated report catalogue verification — October 14, 2026

- Revalidated the remaining 12 integration failures on c8bc3fc: 10 passed, 2 failed
  (142.69s). AI audit lifecycle coverage and lock/relock version expectations remain open.
- Corrected the historical seed test to preserve migration 0048. The full migration-chain
  PostgreSQL comparison verifies all current catalogue fields; four catalogue checks pass
  (6.77s), Ruff/formatting pass. No historical migration changes.
- Evidence and remaining gaps: docs/release/CI-2026-10-14.md. No deployment or readiness claim.

## Full CI results and catalogue/isolation repairs — October 14, 2026

- Immutable 165d63c backend run finished in 5h 11m 13s: 10,843 passed, 33 failed,
  1 skipped, 3 xfailed, 640 deselected; CI failed at backend tests. This is an older snapshot.
  Full failure/revalidation inventory: docs/release/CI-2026-10-14.md.
- Reconciled privacy classifications with the current schema/native option terms; updated
  reviewed scope/lock/preview inventories and integration response fixtures, clarified guide
  API paths, and regenerated the frontend as-locked fixture from its API source.
- Downgrade tests start from fresh head. Reset disposes idle app/owner pools to prevent stale
  enum type OIDs after schema recreation; the checked-out database lock remains held.
- Final affected CI-unit recheck: 20 passed (13.61s); privacy/migration isolation suite:
  22 passed (35.33s); frontend as-locked checks: 90 passed (8.13s). Strict production/DB
  support typing (890 sources, explicit package bases) and Ruff pass.
- Remaining: historical report-seed equality, current-main revalidation of 12 other snapshot
  failures, AI audit coverage, lock/relock figure expectations, three expected-failure gaps,
  migration promotion and other release work. No deployment or readiness claim.

## Proposed migration judgement content — October 14, 2026

- Basis v4 includes exact proposed conclusions/rationales/questionnaires and stable targets.
  Distinctness follows published templates, binding version ids/hashes; collectibility has
  one proposed probable assessment per enabled book at inception (BS3-D-23/26). These remain
  proposals, with no fabricated reviewer or reviewed records. Fresh target resolution refuses
  a missing obligation instead of falling back to the contract.
- Real PostgreSQL witness: two obligation proposals and ASC606 collectibility, IFRS15 adds
  its own proposal, no judgement rows persist, and rollback restores the original plan.
  Final domain/PG/architecture suite: 84 passed (26.30s); strict production plus changed
  tests (891 sources) and Ruff pass. Logs: .run/migration-judgement-plan-*.log.
- Approved record creation, assessment events and their resulting output proof, final
  activation, policy/report checks and atomic promotion remain unfinished. Older immutable
  full CI is live at 94%. Publish directly to main; no deployment/readiness claim.

## Approved status for composed activation — October 14, 2026

- consume_fresh_basis now shares the direct approval-hook guard: the request must name the
  subject, be APPROVED and still hash to its reviewed content before it can confer authority
  on a child action. Non-approved requests refuse before content evaluation. Existing import
  activation benefits; the migration promotion subject remains unregistered.
- PostgreSQL tests cover all five request states. Final unit/PG suite: 106 passed (9.01s).
  All 18 import commit cases also passed; 124 unique cases verified across the two runs.
  Four new test-only recorder assertions were corrected before the final successful run.
  Strict production plus PG-test typing (889 sources) and Ruff pass. Evidence:
  .run/approval-consumption-status-{tests,final,types}.log.
- Judgement creation under independent approval, policy/report checks, final activation and
  atomic promotion remain outstanding. Publish directly to main; no deployment/readiness claim.

## Migration activation prerequisites — October 14, 2026

- Review basis v3 binds each reproduced contract's complete pre-activation checklist. Missing,
  duplicate, foreign, incomplete and malformed evidence refuses. Failed mandatory/source,
  product/template/SSP, combination or existing-judgement prerequisites refuse by rule code.
- An inactive product can reproduce accounting output but now fails activation preflight.
  Distinctness/collectibility judgements required by BS3-D-23/26 stay explicitly pending and
  failed, with ready_for_activation false. No approval or waiver is fabricated.
- Three PostgreSQL cases passed (17.78s); 101 domain/capture/architecture checks passed
  (17.04s); strict production plus changed tests (890 sources) and Ruff pass. Evidence:
  .run/migration-activation-review-{pg,unit,types}.log.
- Creating/reviewing judgements under approval, final activation admission, policy/report
  checks and atomic live creation remain unfinished. Current full CI is still running on
  an older snapshot at 64%. No deployment/readiness claim; publish directly to main.

## Named principal-agent migration refusal — October 14, 2026

- Stage 03 now distinguishes incomplete reviewed agent terms with PrincipalAgentInputError,
  preserving the ValueError contract. Migration capture maps these failures to named 422
  validation; output replay refuses by name. Arithmetic and range invariants are unchanged.
- Real PostgreSQL reproduction verifies an unreviewed AGENT product refuses and rolls back
  temporary contracts/options/audits. An injected unexpected ValueError remains unexpected,
  rolls back, and leaves the original review basis reproducible.
- Engine/agent-billing/capture suite: 46 passed (16.49s); final PG/architecture suite: 66 passed
  (31.00s), with three overlapping database cases. Strict production plus PG-test typing
  passes (888 sources); Ruff passes. The specialist test's 28 existing helper typing errors
  reproduce unchanged from prior main. Logs: .run/agent-input-refusal-*.log.
- Promotion approval, policy/report/activation checks and independent accounting sign-off
  remain outstanding. No deployment; verified changes published directly to main.

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

## Outstanding release verification

These checks need current release-candidate evidence. Historical October 3 results
remain in the dated build history; they do not verify current main. This list does
not authorize deployment, provisioning or changes to a live database.

- SUPERVISOR VERIFICATION NEEDED: make audit-deps (October 14 development audit passed; rerun on a clean final candidate).
- SUPERVISOR VERIFICATION NEEDED: make docker-build
- SUPERVISOR VERIFICATION NEEDED: make compose-verify
- SUPERVISOR VERIFICATION NEEDED: make zap-baseline
- SUPERVISOR VERIFICATION NEEDED: make tf-validate (October 14 backend-disabled development validation passed; rerun on a clean final candidate).
- SUPERVISOR VERIFICATION NEEDED: make backup, make restore-verify (isolated local drill only)

## Historical release record

The earlier build-loop notebook is preserved in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).
Current outstanding implementation and verification gaps remain in
[the release limitations](docs/release/LIMITS-1.0.md).
