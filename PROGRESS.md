# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Number-explanation submission — October 15, 2026

- Added POST /ai/explanations for the number-explanation form: 202 API-S-Job with Location,
  normal idempotency and the initiating human. HTTP validates source access through overlapping
  ai.use/contract.read scope and the shared narrative read path, but makes no provider call.
- Queue insertion and AI switch admission share the tenant lock. A concurrent disable completes
  before a waiting submission can proceed, causing ai-disabled with no new job. New jobs retain
  selectors, a validated trace ID and a 2048 output-token limit; prompts/model settings are not
  queued. The worker rejects a changed trace before calling; old unbound fingerprints are intact.
- Verification: 21 AI/API database cases passed, followed by both final API cases (including
  real lock contention, idempotency, scope refusal, HTTP-to-worker persistence and changed-trace
  refusal). 40 unit/route/layer checks passed. Full lint, OpenAPI generation and full typecheck
  passed (924 Python sources plus frontend); focused strict typing passed 775 sources. Logs:
  .run/ai-submission-{regressions,api-final,unit,lint,openapi,typecheck,types-final}.log.
- The initial permission fixture was corrected to use an auditor without ai.use; test import
  typing was corrected before the final checks. Anomaly/extraction/Q&A submission, proposal
  read/review and durable AI admission-failure evidence remain open. No deployment/live calls.

## Sensitive AI configuration approval — October 15, 2026

- Model changes, including returning a custom model to the catalogue default, and enabling
  contract-text sending now require independent workspace-administrator review in addition to
  configuration approval. The submitted whole values are compared with their predecessor and
  defaults, so inherited values and unrelated edits do not create extra approval requirements.
- The rule applies while AI is disabled too. Approved model/text changes alone never clear the
  emergency switch. Turning text sending off retains normal routing. Existing first-enable,
  re-enable, publication replay and budget-edit behavior remains covered.
- Verification: 25 database regression cases passed, followed by five API cases checking actual
  resolved settings after publication. 53 unit/layer checks, strict typing (773 sources) and
  full make lint passed. A test's nullable timestamp assertion was made explicit for typing.
  Logs: .run/ai-sensitive-{regressions,effective-settings,unit,types-final,lint}.log.
- Provider selection remains process configuration; tenant approval gating of provider changes
  is still open, along with public submission/review and other release requirements. No live
  provider calls or deployment; this is development evidence, not a full release pass.

## Approved AI re-enable publication — October 15, 2026

- A new AI policy publication with ai.enabled=true clears the emergency switch in the same
  transaction, with ai.enabled audit evidence linked to its approval and registry version.
  Replaying an already-published version cannot undo a later disable; false publications leave
  the switch intact. No direct enable command was added.
- First enablement and clearing a switch require independent human configuration approval plus
  workspace-wide settings.manage. This also covers inherited ai.enabled=true values. A refused
  reviewer rolls back the decision/publication. Budget-only edits while enabled retain normal
  routing; tenant locking serializes switch changes with the publication decision.
- Final verification: 21 database lifecycle/approval/scope/disable cases passed; 53 unit/layer
  checks passed. Full make lint and make typecheck passed (922 Python sources plus frontend).
  Logs: .run/ai-reenable-{regressions-final,unit-final,lint-final,typecheck-final}.log.
  The initial test used an older non-MFA author session; it was corrected to the enrolled session.
- Public submission/review, broader AI sensitive-setting approval coverage, unknown usage/outcome
  reconciliation and the other release gaps remain open. No live provider calls or deployment.

## Immediate tenant AI disable — October 15, 2026

- Added POST /tenant/ai/disable with workspace-wide settings.manage, fresh MFA, a required
  comment and normal command idempotency. It records the human/time, cancels only this tenant's
  queued AI tasks and appends ai.disabled plus per-job cancellation evidence in one transaction.
  Repeats return the original timestamp without duplicating switch/cancellation events.
- Running calls retain evidence under the gateway's existing setting rechecks. The switch
  overrides a published ai.enabled=true policy; other tenants and queued non-AI jobs are intact.
- Verification: five tenant/API/scope regressions passed, then two API cases passed with a
  published-enabled policy; 25 route/layer checks passed. Full typecheck passed 922 Python
  sources and frontend checks. Full lint and OpenAPI generation passed. Logs:
  .run/ai-disable-{api,regressions,enabled-policy,architecture,typecheck,lint,openapi}.log.
- One initial typing issue on a database timestamp was corrected with an explicit type check.
  No deployment or live provider calls. Policy-publication clearing of the emergency switch,
  public AI submission, proposal review and other outstanding readiness work remain open.

## AI cancellation boundaries — October 15, 2026

- Narrative tasks now stop cooperatively before another provider call and during retry waits.
  Waits use one-second chunks with attempt-fenced heartbeats and cancellation checks, outside
  transactions and the tenant budget lease. A lost attempt stops without another wait/call.
- An already-started call retains its usage and outcome; cancellation does not erase logs or
  completed proposals. The handler returns control for the registry to settle CANCELLED.
- Real registry checks passed for cancellation before dispatch and during a retry wait, proving
  zero/one calls respectively and retained evidence without a synthetic proposal. The fixture
  now inserts final immutable queue parameters rather than attempting to rewrite them.
- Unit/worker/layer selection: 36 passed; final focused unit selection: 15 passed. Strict typing
  passed 773 sources. Initial test-only issues (single-call token expectation, immutable fixture
  params and an explicit duplicate mypy source) were corrected. Logs are .run/ai-cancellation-*.log.
- Full AI domain database selection passed all 19 cases (.run/ai-cancellation-all-pg.log);
  full make lint passed (.run/ai-cancellation-lint-final.log).
- Public AI workflows and independent accounting acceptance remain unfinished. No live provider
  calls or deployment; this change is not a full readiness or immutable-CI result.

## Narrative worker dispatch — October 15, 2026

- Registered the narrative AI_TASK handler and connected the worker to the existing gateway.
  Queue payloads admit source selectors only; invalid/extra input is refused without persisting
  its values in validation diagnostics. Provider construction remains lazy after admission.
- The gateway owns provider retries and waiting; registry retry policy remains one attempt.
  Completion returns the durable proposal identity, including a retained provider-failure
  proposal, and does not signify human acceptance or accounting approval.
- Verification: 33 unit/worker/layer checks passed; 13 real-database retry/recovery scenarios
  passed, with completed paths dispatched through the new handler and repeated without a new
  provider call. Strict typing passed 773 sources; full make lint passed. Logs:
  .run/ai-job-dispatch-{tests,pg,types-final,lint}.log. No live provider calls or deployment.
- Public submission, other AI operations, admission-failure evidence, notifications, human
  review and unknown-outcome/usage reconciliation remain open; this does not close AI lifecycle
  verification or establish production readiness.

## Full PostgreSQL revalidation — October 15, 2026

- Complete PostgreSQL selection on unchanged 80fba4c: 669 passed, six failed (439.45s), recorded
  in .run/seal-time-full-pg.log. Full typecheck passed 919 Python sources and frontend checks
  (.run/seal-time-full-typecheck.log). This was a failed database run, not a release pass.
- Four failures came from the AI proposal index placing enum filters before created_at under
  RLS. New migration 0153 moves the date ahead of those filters; ALLOWED is unchanged. A real
  application-role plan now proves the date bounds the scan and enums remain filters.
- The trigger inventory now names both server timestamp triggers. The AI-log retention test
  separately verifies ordinary truncate's FK refusal and CASCADE reaching the append-only guard,
  then checks all retained rows are unchanged. No permission or retention rule was relaxed.
- Focused revalidation: 21 passed (31.41s), including all failed cases and a full migration
  round trip. Strict typing passed 772 sources. An initial missing unique=False migration helper
  argument was caught and corrected before this recheck. Logs: .run/full-pg-repairs-recheck.log
  and .run/full-pg-repair-types-recheck.log.
- Full lint passed (.run/full-pg-repairs-lint.log). Complete PostgreSQL rerun: 676 passed
  (496.12s), .run/full-pg-repairs-all.log. This is development verification; full immutable CI,
  remaining implementation and independent accounting sign-off are still required. No deployment.

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
