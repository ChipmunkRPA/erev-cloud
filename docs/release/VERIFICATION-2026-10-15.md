# Local readiness verification — October 15, 2026

This development verification starts from `519de8c`, with the exact synthetic-key scanner
exception and AI prompt-test module rename described below. It is not an immutable full-CI
release result, accounting sign-off or deployment approval. The separate dependency audit below
was subsequently run in an immutable context on `621d412fcaa21bd35af898b5d48aec3761908309`.

## Completed checks

- `make audit-deps` on clean `621d412`: passed in an immutable source context. All 86 pinned
  Python dependencies were audited; eight environment markers were removed to include packages
  used by other target platforms. Python vulnerabilities: zero. npm advisories: zero at every
  severity. The context hashes before/after matched; dependency installations remained consistent.
  Result digest: `89ed52d71a2a2afbb288e638b931f0d0021ad18719856b59ce7f2631d9ebd203`.
  Logs/report: `.run/readiness-audit-deps-oct15.log`, `.run/reports/audit-deps/report.json`.
  This is dependency-advisory evidence as of the run, not proof that all application security
  and release requirements are satisfied.

- `make lint`: passed after the repairs below, including formatting, source lint, design,
  vocabulary, dependency licences, secrets, OpenAPI, seed/fixture checks, control-marker
  validation (502 tagged tests out of 12,015 collected), and the single migration head check.
  Log: `.run/readiness-lint-oct15.log`.

- `make typecheck`: passed, including strict Python typing for 917 sources and frontend TypeScript.
  Log: `.run/readiness-types-oct15.log`.
- `make build`: passed frontend production build and backend imports. Vite reported its existing
  large-chunk warning. No application was deployed. Log: `.run/readiness-build-oct15.log`.
- `npm --prefix frontend run test -- --run`: 196 files, 2,109 tests passed (174.31s).
  Log: `.run/readiness-frontend-oct15.log`. The run includes jsdom navigation diagnostics;
  the test process exited successfully.
- Collection of the AI prompt and policy-template modules together: 28 tests collected without
  import mismatch. Log: `.run/readiness-collection-collision-oct15.log`.
- Publication checks: GitHub repository remains public with default branch `main`; neither
  `research-harness/` nor `docs/research/` is tracked. The PolyForm Noncommercial licence remains.

## Repairs discovered by broader verification

The secret scan flagged a synthetic key literal asserted against a mocked SDK constructor.
Its exception is limited to that file, pattern and exact stripped-line hash. Real credentials,
other files and edited lines remain subject to the scan; no scanner rule was relaxed.

Full test collection imported two un-packaged `test_templates` modules under the same name.
The AI prompt module is now `test_ai_prompt_templates.py`; its assertions are unchanged.
Focused AI runs did not expose this collision with the policy-template suite.

## Backend unit/architecture result and repairs

The complete unit and architecture directories finished with **5,609 passed, two failed,
two Linux-only skips** in 1,364.71s (22m44s). Log:
`.run/readiness-unit-architecture-oct15.log`. This is the original result, not a green run.

- The migration-walk guard found that `test_ai_call_intent.py` and `test_ai_job_binding.py`
  did not reset to a data-free head before attempting downgrades. They now call `fresh_head()`
  first, and the guarded inventory includes them. The actual constraint/immutability/downgrade
  assertions remain intact.
- The process-script lifecycle test inherited the repair runner's `EREV_RUN_DIR` while looking
  for its PID file under the default `.run` directory. Its subprocess environment now explicitly
  matches the probe paths; production process-script behavior is unchanged.

Focused revalidation: **15 passed** (44.72s), covering both failed unit checks, all process-script
checks, both AI database guards and the full migration round trip. Strict typing for the four
changed test modules and Ruff/diff checks passed. Logs:
`.run/readiness-isolation-repairs-oct15.log`, `.run/readiness-isolation-types-oct15.log`.
The full 5,613-test selection has not been repeated after these repairs.

## Historical subledger insertion cutoff

Development validation on the working tree based on `99cef00`; these are not immutable release
candidate gates. Migration 0151 adds a database-owned insertion stamp to the sealed line document.
Historical report and explicit API cutoffs use it; record/current/close reads keep the application
clock. Upgrade and downgrade refuse populated ledgers without rewriting rows or seals.

- Focused migration/cutoff checks: **9 passed** (72.72s), including the 0124 historical fixture,
  both 0151 populated-ledger refusals, and insertion after a cutoff within a transaction begun
  before it. `.run/server-time-migration-guards.log`.
- Broad report, ledger, subledger API, privacy, snapshot and migration selection: **379 passed,
  1 failed** (1,701.70s). The failed API assertion expected visibility at the frozen application
  time. It now checks actual database instants before/after posting and excludes the earlier
  business-clock timestamp. `.run/server-time-report-ledger-regressions.log`.
- Follow-up selection: **26 passed, 1 expected failure** (123.56s). Includes the revised API test,
  actual historical versus record-basis disaggregation totals, both migration guards, server
  timestamp immutability against application/owner mutation, seal-chain verification, ledger
  invariants, tenant isolation, and contract/schedule APIs. `.run/server-time-followup.log`.
- The expected failure is the separate overlapping-commit case: insertion occurs before the
  cutoff, while commit occurs afterward. Preconditions run before applying the strict expected
  failure marker. The missing exclusion remains a release gap, not passing evidence.
- Report/journal unit selection: **1,141 passed** (7.04s). `.run/server-time-unit-reports.log`.
- Architecture: **269 passed, 1 failed** (231.36s). The data-model documentation listed the appended
  column in the wrong order. After correction the exact failed check passed (1.22s).
  `.run/server-time-architecture.log`, `.run/server-time-drift-recheck.log`.
- Strict typing: **771 source files passed**. Changed Python formatting, Ruff and diff checks
  passed. Full `make lint` passed, including license/secret scans, registry and fixture checks,
  and 502 control-tagged tests collected. `.run/server-time-types-final.log`,
  `.run/server-time-lint.log`.

The full broad and architecture selections were not repeated after their test/documentation
repairs. Insertion time is not PostgreSQL commit time and may split a posting when a cutoff falls
between line inserts. Neither historical transaction visibility nor production readiness is claimed.
No deployment or live provider call occurred.

## Historical posting completion

Follow-up development work based on `ea5a29c`. Migration 0152 adds immutable database-owned
`sealed_server_at` metadata to each completed posting seal, after its balance and chain guard.
Historical queries retain the line insertion cutoff and additionally require the seal by that
cutoff. The correlated tenant/posting keys use the tenant-scoped seal while preserving the outer
line's entity scope. A cutoff cannot expose only the earlier lines of an unfinished posting.
Record/current/close reads retain their previous application-time behavior.

The timestamp is outside the canonical line hash, like the existing seal metadata `sealed_at`.
Both migration directions refuse populated seals: upgrade cannot invent their historical server
completion instant, and downgrade cannot discard retained completion evidence. No sealed rows
are rewritten or deleted. This remains a pre-release populated-database migration boundary.

- Core database checks: **19 passed, 1 expected failure** (140.88s). Covers a cutoff after lines
  but before sealing, exact-seal-time inclusion, historical/record report totals, both migration
  refusal directions, older insertion-stamp protection and a full migration round trip.
  `.run/seal-time-core.log`.
- Final database selection: **9 passed** (52.00s). Covers forged timestamp replacement,
  application and owner mutation refusal, subledger/schedule APIs, cross-tenant and entity
  isolation, the 0124 historical fixture and retained AI call-intent downgrade evidence.
  `.run/seal-time-followup.log`.
- Report/journal/privacy unit and selected architecture checks: **1,192 passed** (17.77s).
  `.run/seal-time-unit.log`. Strict typing passed **771 source files**;
  `.run/seal-time-types-final.log`. Full `make lint` passed, including the license/secret scans,
  registry/fixture checks and 502 control-tagged tests collected; `.run/seal-time-lint.log`.

The expected failure still proves the missing overlapping-commit exclusion. A server sealing
instant is not a PostgreSQL commit timestamp. Full release CI, broader gates and independent
accounting sign-off remain outstanding; no deployment occurred.

## Complete PostgreSQL run and index repair

The complete PostgreSQL selection on unchanged `80fba4c` finished with **669 passed, 6 failed**
(439.45s); `.run/seal-time-full-pg.log`. The full typecheck on that snapshot passed 919 Python
sources and the frontend target; `.run/seal-time-full-typecheck.log`.

Four failures exposed one real index-order defect: `ai_proposal.ix_ai_proposal__status` put enum
keys ahead of `created_at`, so the date did not bound an application scan under row-level
security. Migration 0153 moves the timestamp immediately after the tenant key. It preserves
rows and constraints and reversibly recreates the prior index on downgrade. The index-condition
allowlist is unchanged. A new application-role EXPLAIN test proves the tenant and date are the
leading index conditions while kind/status remain filters; it tests admissible bounds, not a
production-volume performance claim.

The remaining two failures were test assumptions. The exact subledger trigger inventory now
includes both server timestamp triggers. The AI-log retention test separately verifies plain
TRUNCATE's foreign-key refusal and TRUNCATE CASCADE reaching the append-only guard, then checks
all retained log rows are unchanged. No production permission or retention rule was relaxed.

Focused revalidation: **21 passed** (31.41s), including all six failures, the new plan test and a
full migration round trip; `.run/full-pg-repairs-recheck.log`. An initial repair attempt exposed a
missing explicit `unique=False` helper argument; it was corrected before that successful run.
Strict typing passed 772 sources; `.run/full-pg-repair-types-recheck.log`. Full lint passed with
502 control-tagged tests collected; `.run/full-pg-repairs-lint.log`.

The complete PostgreSQL rerun passed: **676 passed** (496.12s),
`.run/full-pg-repairs-all.log`. The extra test is the application-role AI proposal index-plan
regression. Production/test sources stayed unchanged during this rerun; verification prose was
updated separately. These are development checks, not immutable complete CI or production-readiness
evidence. No deployment occurred.

## Remaining scope

- The backend unit/architecture selection above does not include all backend API/domain/engine/PG
  test directories. Fresh complete CI and release-gate results remain outstanding.
- Full immutable CI, PostgreSQL/release gates, outstanding implementation, unknown AI usage
  reconciliation and independent accounting sign-off remain required. Historical evidence in
  `CI-2026-10-14.md` does not establish current-main completion.

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
