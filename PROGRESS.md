# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Historical posting completion — October 15, 2026

- Migration 0152 adds database-owned sealed_server_at after balance/chain validation. Historical
  predicates now require the complete posting's seal by the cutoff, as well as line insertion;
  record/current/close behavior remains on its application-clock basis. Entity scope stays on
  the outer line query; the tenant-scoped seal prevents hidden sibling lines from splitting it.
- Core database checks: 19 passed, one strict expected failure for overlapping commit visibility
  (140.88s). Follow-up: nine passed (52.00s), including forged timestamp override, application/owner
  immutability, APIs, tenant isolation, older migration guards and retained AI intents.
- Unit/architecture selection: 1,192 passed (17.77s). Strict typing passed 771 sources. Logs:
  .run/seal-time-{core,followup,unit,types-final}.log. Full make lint passed;
  .run/seal-time-lint.log (502 control-tagged tests collected).
- Populated seals cannot cross 0152: the earlier server completion instant cannot be reconstructed
  and downgrade cannot discard it. The stamp is immutable seal metadata outside the line hash.
  PostgreSQL commit visibility remains open; no deployment or production-readiness claim.

## Historical line insertion cutoff — October 15, 2026

- Migration 0151 adds a database-owned insertion stamp included in new line seals.
  Historical report/API predicates use it; record/current/close predicates retain recorded_at.
- Nine focused tests passed (72.72s): upgrade/downgrade refuse populated ledgers without
  changing rows or seals; 0124 historical fixture remains valid; a transaction begun before
  the cutoff cannot expose its later insert. Log: .run/server-time-migration-guards.log.
- Mypy passed 771 sources; 1,141 report/journal unit tests passed (7.04s), recorded in
  .run/server-time-unit-reports.log. Changed Python formatting and Ruff checks passed.
- Broad report/ledger/API/privacy/snapshot/migration run finished: 379 passed, one failed
  (1,701.70s). The API test still expected historical visibility at the frozen application clock;
  it now checks database instants before/after posting and excludes the earlier business stamp.
  Follow-up: 26 passed, one strict expected failure for overlapping commit visibility (123.56s).
  Log: .run/server-time-followup.log; full evidence in VERIFICATION-2026-10-15.md.
- Architecture: 269 passed, one column-order mismatch (231.36s); documentation corrected and
  the exact failed check passed (1.22s). Logs: .run/server-time-architecture.log and
  .run/server-time-drift-recheck.log. Full architecture selection not repeated.
- make lint passed (.run/server-time-lint.log): 142 dependency licenses, zero secret findings,
  registry/fixture checks and 502 control-tagged tests collected successfully.
- Insertion time is not commit time. The 0152 follow-up above closes posting splits; overlapping
  commits remain unresolved. See LIMITS-1.0.md. No readiness claim or deployment.

## Backend broad-run isolation repairs — October 15, 2026

- The complete unit/architecture selection finished: 5,609 passed, two failed, two Linux-only
  skips in 1,364.71s. Preserve this as a failed original run, not a full green gate.
- AI intent/job-binding downgrade tests now reset to a data-free head first and are included
  in the migration-walk inventory. The process-script lifecycle test explicitly selects the
  runtime directory matching its probe paths instead of inheriting the repair runner's override.
- Focused revalidation: 15 passed (44.72s), including both failures, process-script checks,
  both actual AI database downgrade guards and the full migration round trip. Strict typing
  for four changed tests, Ruff and diff checks passed. Logs:
  .run/readiness-isolation-{repairs,types}-oct15.log. Full selection not repeated after repairs.
- No broad backend process remains running. Complete CI and other implementation/release gates,
  unknown AI usage reconciliation and independent accounting sign-off remain outstanding.
  Details: docs/release/VERIFICATION-2026-10-15.md. No deployment or readiness claim.

## Immutable dependency audit — October 15, 2026

- make audit-deps passed on clean 621d412 in an immutable context: 86 of 86 pinned Python
  packages audited, zero Python vulnerabilities; zero npm advisories at all severities.
  Eight platform markers were removed for complete pinned-package coverage. Source and
  installed dependency hashes remained unchanged. Report and digest are recorded in
  docs/release/VERIFICATION-2026-10-15.md; log .run/readiness-audit-deps-oct15.log.
- Backend unit/architecture verification has since completed; its failures and focused repairs
  are recorded in the latest note and docs/release/VERIFICATION-2026-10-15.md.
  Historical-report cutoff repair also requires ledger-seal compatibility: LINE_MEMBERS
  dynamically includes every stored line column, so adding a timestamp alone changes hashes.
- Full implementation/release verification and independent accounting sign-off remain open.
  No deployment. Verified dependency audit is not a production-readiness claim.

## Broader readiness verification — October 15, 2026

- Full repository typing passed (917 Python sources plus frontend TypeScript); production build
  and backend imports passed. All 2,109 frontend tests in 196 files passed (174.31s).
- Full lint found a mocked SDK synthetic-key literal requiring an exact-line scanner exception,
  and a test module-name collision between AI prompt and policy-template tests. Added only the
  scoped fixture exception and renamed the AI test module without changing its assertions;
  both modules now collect together (28 tests). Full lint passed, including collection of
  12,015 tests and validation of 502 control-tagged tests.
- Complete backend unit/architecture verification subsequently finished; see the latest note
  and .run/readiness-unit-architecture-oct15.log. Other logs use .run/readiness-*-oct15.log.
- Details: docs/release/VERIFICATION-2026-10-15.md. Public visibility, main default, research
  exclusions and noncommercial licence verified. These development checks are not full CI,
  independent accounting sign-off or production readiness. No deployment.

## Provider response usage preservation — October 15, 2026

- Anthropic message usage now validates strict nonnegative counters and includes cache-read
  plus cache-creation input tokens in the total. Optional absent/null cache fields count as zero;
  output/cache breakdowns are not counted twice, and stored totals must fit int32.
- Rejected response metadata/content preserves valid usage via ProviderError. Missing/malformed
  usage remains UNKNOWN; SDK exceptions never invent counts. No raw response body or fabricated
  response hash is retained on these errors.
- Mocked adapter-to-gateway checks verify a failed proposal links to reported usage and counts
  40 tokens, while invalid counters produce unknown usage and keep tenant admission blocked.
  Unit coverage includes cache totals, invalid/absent counters, overflow, invalid metadata and
  malformed content. Regression: 312 passed, two Linux parser-limit skips (67.12s); typing passed
  for 769 sources; final adapter/import-boundary checks: 69 passed (10.23s); Ruff/diff passed.
  Logs: .run/ai-adapter-usage-{final,types,boundary}.log.
- No live provider calls or deployment. Unknown-usage reconciliation and the remaining product,
  accounting and release-verification gates are still open; this is not production readiness.

## Budget admission for unknown provider usage — October 15, 2026

- Tenant admission now refuses returned errors with unknown usage, including historical
  response-less errors without a marker. The refusal spans jobs and month boundaries; the
  current intent's lease exemption cannot hide a committed unknown-usage outcome.
- ProviderError can carry typed AIUsage. The writer validates counters, rejects conflicting
  response/admission evidence, and retains reported error usage without a response body.
  Fresh admission counts this usage; bounded retries and terminal/restarted failure recovery
  preserve reported counters. Legacy unsent admission records remain distinguishable.
- The current Anthropic adapter reports no usage on exceptions, so those errors block new
  calls. No reconciliation command, automatic expiry, zero estimate or override was added.
  Reconciliation and the remaining public workflows/release gates are still outstanding.
- Broad AI/budget regression: 260 passed, two Linux-only parser-limit skips (84.25s);
  final gateway recovery verification: 12 passed (57.50s), .run/ai-unknown-usage-recovery.log.
  Strict typing passed for 771 sources; Ruff/diff checks passed. Logs:
  .run/ai-unknown-usage-{final,types}.log. No deployment or production-readiness claim.

## Distinguish missing AI usage from reported zero — October 15, 2026

- Attempt logs now derive immutable usage_evidence metadata: REPORTED for validated response
  counters, NOT_SENT for disabled/budget admission refusals, UNKNOWN for response-less errors.
  Caller request parameters cannot supply the marker; historical logs are not rewritten.
- Failed-proposal recovery recognizes the marker while requiring UNKNOWN for a response-less
  provider failure. Exact request hashes and strict metadata comparisons remain enforced.
- Regression: 230 passed, two Linux-only parser skips (66.77s); typing passed for 768 sources;
  Ruff and diff checks passed. Logs: .run/ai-usage-evidence-{final,types}.log. Six zero-counter
  cases distinguish evidence categories; a forged request marker refuses without log/audit writes.
- This is durable evidence groundwork. Budget admission still needs enforcement/reconciliation
  for returned errors with unknown usage, including historical evidence and bounded retries.
  Public AI workflows and all other release gates remain open. No deployment or readiness claim.

## Tenant budget quarantine for unobserved calls — October 15, 2026

- Budget admission now refuses while any tenant call intent lacks an outcome, across month
  boundaries. Another job cannot consume an understated total after a worker crash.
- After successful admission, the live lease binds one newly committed intent of its human
  caller. Only that intent is excluded from the post-response check; another unresolved start,
  replacement lease, different human or anonymous context cannot use the exemption.
- Tests cover old unresolved calls, tenant isolation, current-call completion, fresh-lease
  refusal, known-outcome release/usage accounting, other-human binding refusal and a separate
  gateway job after simulated crash/lost result. AI/session regression: 233 passed, two Linux
  parser-limit skips; two additional ownership tests passed; typing: 769 sources; Ruff/diff pass.
  Logs: .run/ai-uncertain-budget-{final,types}.log and .run/ai-budget-intent-owner.log.
- This blocks unobserved calls; it does not invent usage or add a reconciliation override.
  Returned provider errors without token counts, unknown-usage reconciliation, public workflows
  and other release gates remain open. No deployment or production-readiness claim.

## Gateway call intents and restart recovery — October 15, 2026

- The narrative gateway now commits an intent before calling the provider, then links each
  outcome to that intent. Completed proposals keep their existing idempotent delivery path.
  Unobserved outcomes refuse AI_OUTCOME_UNKNOWN; returned but invalidated results require
  reconciliation. Neither path silently calls again or invents a zero-usage outcome.
- Logs retain allow-listed provider failure codes and retry decisions. Restarted gateways
  honor remaining backoff and the durable three-attempt limit; permanent/exhausted failures
  finalize their failed proposal without another call. Proposal writers verify intent/job/
  source bindings, preventing evidence reuse under another job.
- Tests verify committed starts visible inside provider execution, crash during the call,
  lost result before commit, restarted transient/permanent/exhausted failures, bounded calls,
  waits without budget leases, complete intent/outcome linkage and metadata refusals.
- Full AI/architecture regression: 493 passed, two Linux-only parser-limit skips (262.18s);
  strict typing passed for 770 sources; Ruff/diff passed. Logs: .run/ai-recovery-{final,types}.log.
- Unknown usage/reconciliation, durable admission failures, registered jobs, public AI/human
  workflows and the other release gates remain open. This is not full release CI or accounting
  sign-off. No deployment; verified work is published directly to main.

## Audited AI call-intent writer — October 15, 2026

- Added a transaction-bound writer that locks the human-owned RUNNING AI_TASK job,
  validates exact request/source hashes, assigns consecutive starts up to three and writes
  immutable intent plus AUD-FACT evidence atomically. Unresolved prior starts refuse without
  creating a usage log. The caller must commit before executing a provider call.
- Attempt outcomes can now link to an intent only when provider, request hash and human
  match; duplicate outcomes and budget/disabled admission records cannot close an intent.
  Shared request validation keeps arbitrary parameters and model text out of retained evidence.
- Tests cover rollback/audit atomicity, unknown outcomes, changed input, wrong human/provider,
  duplicate outcomes, attempt exhaustion and invalid/nonrunning job ownership. Broad AI and
  audit-key regression: 224 passed, two Linux parser-limit tests skipped; strict typing:
  768 sources; Ruff/diff passed. Logs: .run/ai-intent-writer-{final,types}.log.
- This is a required writer foundation, not operational crash protection: gateway integration,
  durable retry classification/recovery and unknown-usage handling remain open, as do the
  other implementation/release gates and independent accounting sign-off. No deployment.

## AI document file-read authorization — October 15, 2026

- Registered proposal source references without granting source access. Derived text now
  requires ai.use and current access to an unshredded source attachment of a same-tenant
  CONTRACT_EXTRACTION proposal. Non-extraction, missing-source and recursive text links refuse.
- PostgreSQL tests cover uploader access, another contract reader's entity permissions,
  attachment voiding, lost AI permission, source shredding, operator/foreign-tenant denial,
  reads while AI is disabled and conservative all-entity erasure scope.
- Focused checks: 14 passed; strict typing: 768 sources; Ruff/diff passed. Logs:
  .run/ai-file-read-{final,types}.log. Full architecture plus existing file API checks:
  292 passed in 226.83s (.run/ai-file-access-regression.log); this is not full release CI.
- Consolidated contradictory historical AI paragraphs in LIMITS-1.0.md into current status;
  preserved the superseded notes in BUILD-HISTORY-2026-10-07.md.
- Dedicated proposal/document-text response APIs, extraction job integration and write-ahead
  call recovery remain unfinished, along with other implementation and release gates.
  No deployment or production-readiness claim; independent accounting sign-off is still open.

## AI proposal evidence retention and encrypted text — October 15, 2026

- Source and extracted-text references now hold their files against direct shredding even
  after proposal expiry. Existing Controller-reviewed EVIDENCE_SHRED approvals lift the holds;
  no durable entity binding exists, so review must cover every tenant entity.
- AI_DOCUMENT_TEXT now uses per-file encryption. The integration test proves ciphertext at
  rest, decryption before erasure, direct-refusal audit, separate approval, sidecar destruction,
  FILE_SHREDDED on later reads, and retention of the expired proposal/source references.
- Verification: 33 retention/erasure/registry checks passed; the strengthened byte-level test
  passed separately; strict typing passed for 768 sources; Ruff/diff passed. Logs:
  .run/ai-file-retention-final.log, .run/ai-file-erasure-bytes.log and
  .run/ai-file-retention-types.log. Fixed two pre-existing test typing issues found by that run.
- The evidence-registry failure is resolved. Proposal file-read ownership remains open, as do
  extraction workflow integration, call recovery and other release gaps. Experimental plaintext
  AI_DOCUMENT_TEXT objects from older builds require explicit migration or regeneration;
  there is no plaintext fallback. No deployment or production-readiness claim.

## Architecture repair after broad verification — October 15, 2026

- Provider timing now uses erev_api.clock.monotonic, retaining the injected duration source.
  The absolute-path template rejection fixture no longer names a reserved temporary directory.
- Registered the AI initiator's existing ACTIVE user/membership identity query with its reason.
  Updated computation-scope and stream-ending registries to name the shared _record_events
  function introduced for option expiry; both public event paths retain the same guards.
- Registered MaterialRightExpireIn evidence through the existing evidence_errors/file_access
  binder, matching the route and the authoritative data-model table.
- Verification: 49 provider/template/architecture checks and five file-binding checks passed;
  strict typing passed for 767 sources; Ruff/diff passed. Logs: .run/architecture-repair-
  checks.log and .run/expiry-binding-checks.log. Five of the seven
  outstanding architecture failures are resolved; AI proposal file ownership and evidence
  retention remain open. This is not a complete architecture or release-suite pass.
- Work remains on call-intent gateway integration and the other implementation/release gaps.
  No deployment or readiness claim; direct main publication continues.

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
