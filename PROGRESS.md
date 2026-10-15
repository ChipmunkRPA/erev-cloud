# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Source citation offsets after redaction — October 14, 2026

- PRV-08 now exposes immutable substitution coordinates alongside its existing redacted
  text/counts. Email and international/local phone precedence stays shared with ordinary
  redaction. The mapping stores no removed contact values and stays outside provider input.
- Extraction validation can validate outgoing redacted pages and restore citations to source
  Unicode coordinates. Boundaries inside replacement placeholders refuse the entire proposal;
  complete placeholders map to complete source spans, subject to human viewing authorization.
- Privacy/extraction/architecture checks: 167 passed; strict API/test typing: 751 sources.
  Logs: .run/ai-offsets-checks.log and .run/ai-offsets-types.log. Ruff/formatting pass.
- The future gateway must retain the exact page mappings used for its prompt. Durable
  document extraction, authorized gateway jobs, value schemas, narrative-number checks,
  budgets, lifecycle auditing and human acceptance remain unfinished. No live calls/deployment.

## AI extraction output validation — October 14, 2026

- Added an atomic extraction validator: response digest/completion, strict JSON and unique
  allowed paths, confidence range, authorised document identity and Unicode page-span bounds.
  Low confidence below 0.75 is marked for review; no field is automatically accepted.
- Invalid fields refuse the entire proposal. Duplicate JSON keys, nonfinite numbers,
  oversized/deep responses and excessive decimal expansion refuse with safe error codes.
  Immutable canonical values preserve exact decimals without binary floating-point rounding.
- AI/provider/architecture checks: 128 passed; strict API/test typing: 750 sources.
  Evidence: .run/ai-extraction-validation.log and .run/ai-extraction-types.log.
- This helper is not connected to a gateway. Command-specific value schemas, redaction-offset
  mapping, semantic citation review, narrative-number checks, authorised jobs, budgets,
  persistence/auditing and human acceptance remain open. No live calls or deployment.

## AI request preparation boundary — October 14, 2026

- Moved provider contracts to domain ports, preserving adapter exports, so the forthcoming
  gateway can depend on the protocol without importing a network adapter.
- Added exact UTF-8 template digest checks and canonical request preparation. The explicit
  document-text argument requires opt-in; existing PRV-08 patterns redact values and system
  text. Contact-bearing field names are refused, not silently leaked or collapsed.
- Outgoing messages and configuration are immutable; the input digest binds template/version,
  actual message bytes, model, system text and generation/redaction settings. Floats are
  refused by canonical encoding. Callers still owe authorised, minimised input selection.
- Provider/preparation/configuration/privacy/architecture checks: 165 passed (23.21s).
  Strict API/test typing: 749 sources; Ruff/formatting pass. Evidence:
  .run/ai-preparation-checks.log and .run/ai-preparation-types.log.
- This is not an enabled gateway: job-only authorization, budget reservation, output
  validation, durable attempt/audit writes and human acceptance remain open. No live calls,
  deployment or readiness claim.

## AI SDK adapter and provider selection — October 14, 2026

- Added the official Anthropic SDK (locked 1.14.0), explicit vendor endpoint, 60-second
  timeout, no SDK retries and no SDK telemetry. Secrets resolve lazily through the scoped
  store. Text blocks, usage, model, stop reason, digest and monotonic latency are mapped;
  typed failures produce safe codes and retryability without provider response bodies.
- Tenant disablement/kill switch returns no provider; fake remains the test default.
  Selection constructs no client. All adapter tests use mocked clients; no live AI calls.
- Adapter/configuration/architecture checks: 110 passed; final adapter/configuration,
  licence and notices checks: 55 passed. Strict API/test typing: 747 sources; Ruff passes.
  Logs: .run/ai-sdk-checks.log, .run/ai-sdk-final.log, .run/ai-sdk-types.log.
  Final SDK network-boundary checks: 16 passed, .run/ai-sdk-network-final.log.
- Licence check: 141 packages, zero findings. Development dependency audit: zero Python
  vulnerabilities across all 85 pinned runtime distributions and zero npm advisories;
  .run/ai-sdk-licences.log and .run/ai-sdk-audit.log. Final clean-candidate audit still owed.
- Gateway/jobs, retained prompt fixtures, human acceptance and lifecycle auditing remain
  unfinished. SUPERVISOR VERIFICATION NEEDED: live Anthropic provider smoke test (not run;
  no live calls authorized here). No deployment or production-readiness claim.

## AI proposal evidence and state guards — October 14, 2026

- Migration 0148 adds T-AI-01, E-73/E-74 and the generated SM-11 transition guard.
  Content/citations and evidence links cannot change. Acceptance/rejection fields are
  set once, complete only in their matching state, and terminal records are frozen.
  Decisions must be a nonempty array; acceptance permissions and decision semantics
  still belong to the forthcoming human command. Expiry is explicitly supplied by its writer.
- Tenant-bound foreign keys reject another tenant's call log or document. Registered
  ORM, privacy, sandbox-regeneration, enum and isolation inventories; updated pinned head.
- Full migration round trip, DB lint, state/immutability/RLS, schema/privacy/snapshot
  and import-cycle checks: 140 passed; single-head check: 1 passed. Strict API/test typing
  passes (745 sources). Evidence: .run/ai-proposal-final.log, .run/ai-proposal-head.log,
  .run/ai-proposal-types.log. Provider/gateway, human acceptance and audit lifecycle
  remain incomplete; AI stays unavailable. No deployment or readiness claim.

## Immutable AI call evidence storage — October 14, 2026

- Migration 0147 adds T-AI-02 ai_model_log with tenant RLS, append-only grants and
  owner mutation guards. Provider/outcome values, SHA-256 digests and nonnegative
  token/latency counters are checked; raw prompt/response text has no column.
- Registered ORM, privacy classification, isolation row builder and sandbox treatment:
  call evidence stays with the source tenant and is regenerated in a sandbox.
- Corrected the migration test's old function count for the existing 0145 ownership
  trigger. API production plus new PG-test strict typing passes (744 sources); Ruff passes.
- Combined migration round trip, DB lint, immutability, RLS, schema/privacy/snapshot
  and import-cycle verification: 127 passed (31.44s), .run/ai-model-log-final.log.
  Typing evidence: .run/ai-model-log-types.log.
- Proposal table/transitions, gateway writes/audit facts and human acceptance remain
  unfinished. The AI lifecycle audit gap remains open; no AI enablement or deployment.

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
