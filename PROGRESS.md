# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Operational first-close manifest control — October 14, 2026 (CTL-041)

- From clean 0dfb9ec, added the exact RPS-16 CTL-041 test path/marker. AVM-US September uses
  real close execution, journal calculation/approval/export/acknowledgement, billing and GL
  reconciliation generation and distinct preparer/reviewer sign-offs, lock approval, automatic
  preparation/audit/report/build workers, and an Auditor's API download. No current-period
  journal/close result or reconciliation review is seeded, and no close gate is waived.
- The archive names the real close journal and both reviewed statements. The required path
  prefixes are present; every payload hash and the separately stored manifest hash match.
  Changed payload and manifest bytes each fail verification. Targeted marked control run:
  **1 passed in 18.51 seconds** (.run/operational-close-pack-control.log).
- Setup corrections followed the actual interfaces: enroll the preparer in MFA; retain her
  session on ReportWorld.place.author; attach an initial GL reference before reading comparison
  totals; generate a new reconciliation to attach the final source (replacement is forbidden).
  The corruption helper copies ZipInfo metadata because writestr mutates offsets. Earlier
  failure logs .run/operational-close-pack{,-mfa,-persona,-reference,-regenerated}.log are terminal;
  no production code, accounting oracle, permission rule or transition was changed to pass.
- Prior periods are fixture-closed. ERP acknowledgement uses the test adapter; the GL upload is
  a synthetic matching reference derived from the comparison, not an independent amount oracle.
  This supplies the missing first-close control witness, not accounting sign-off or a full
  controls/release pass. Re-lock variance, other pack kinds, browser/release gates and independent
  accounting approval remain. Control-tag validation passes (497 tagged tests collected, not
  executed by that check); log .run/evidence-control-tags.log. Ruff lint/format and whitespace
  checks pass. All processes terminal. Direct main; no deployment or readiness claim.

## Automatic close-pack availability notification — October 14, 2026

- From clean 43c55a4, approval-driven locks now defer NTF-06 until successful automatic pack
  retention. The worker checks its preparation/lock association, stores the archive and notifies
  active Controller, Revenue Reviewer and Auditor role holders in the entity's scope in one
  transaction. Copy identifies the locking actor and confirms availability; link is the period
  cockpit. A period_lock subject prevents separate closes merging within the notification window.
- Already-SUCCEEDED retries verify the archive without notifying again; manual packs never
  send this notice. Cancellation/failure before retention makes no availability claim. Sandbox
  replay's existing separate snapshots-only notice remains; replay pack availability is unclaimed.
- Focused actual-worker and rollback regression: **4 passed in 59.95 seconds**. The witness
  injects failure after notification insertion (archive metadata and notifications both roll back),
  then a crash after commit (retry retains one notice per recipient). Each of the three roles is
  present in-scope and in another entity; only the in-scope members receive completion notices.
  The lock rollback test now checks that preparation was queued before its late failure.
- Broader lock/notification regression: **54 passed in 196.55 seconds**, including manual pack
  suppression, the existing role-scope scenario, reopen/approval notification flows, and generic
  notification preferences/delivery checks. Logs .run/close-notification.log and
  .run/close-notification-regression.log; all processes terminal. Three source files pass Mypy;
  five changed Python files pass Ruff lint/format. Whitespace clean. Direct main; no deployment.
  Re-lock variance, other kinds, operational CTL-041, current release checks and independent
  accounting sign-off remain outstanding. No production-readiness claim.

## Automatic first-close preparation — October 14, 2026 (RPS-16 continued)

- From clean ae545bc, lock approval now defers EVIDENCE_PACK/PREPARE_CLOSE in its transaction.
  Preparation reads committed approval/freeze/audit sources, validates the job/lock/period-state
  association and grants only the selected entity's internal source capabilities. It creates
  one bound pack and seven source/build jobs. The build's immutable parent_job_id retains its
  preparation association; the preparation row lock serializes creation and crash retry reuses
  the exact saved pack. No source rebinding, migration or public request change.
- Initial actual-worker/crash/lock-rollback tests: **3 passed in 56.25 seconds**. A simulated
  post-commit crash retained one pack, one evidence.create event and the same seven jobs; real
  audit/report/build workers completed its 36-file archive. Lock rollback leaves no preparation
  job. Expanded tests add invalid selectors/job associations and cancellation before creation.
- Preparation success only means queued; cancellation after creation is refused there while the
  build job keeps its own cancellation lifecycle. Existing lock notices still promise snapshots.
  Re-lock jobs are queued but fail the explicit variance prerequisite. Completion notification,
  variance, other kinds, operational CTL-041, release gates and accounting approval remain open.
- Full lock-module plus retained-binding regression: **81 passed in 183.79 seconds**. This
  includes automatic preparation crash/reuse, exact source job completion, pre-creation
  cancellation without children, invalid selector/job rejection and prior manual pack paths.
  Logs .run/automatic-close-preparation.log and .run/automatic-close-regression.log; all terminal.
  Five source files pass Mypy; six changed Python files pass Ruff lint/format; whitespace clean.
  Public schemas unchanged. Direct main, no deployment or production-readiness claim.

## Lock rollback and independent verification — October 14, 2026

- Broader lock-workflow baseline on 052e907: **39 passed, 2 failed in 145.30 seconds**.
  Both failures were the queued audit worker in the first-close evidence test: the test module
  did not import its real handler and previously passed only when another collected test did.
  Production worker already imports it. Added explicit test registration; no worker replacement.
- Extended rollback coverage to fail at the final lock audit after real notifications exist,
  as well as at the earlier control recorder. Both cases compare retained lock/state/snapshot/
  reconciliation/approval data plus jobs, packs, report runs, notifications, outbox messages and
  lock audits with their pre-decision values. This guards transaction atomicity; it does not
  establish automatic pack generation, which remains unimplemented.
- Corrected worker registration run: **41 passed, 1 failed in 175.04 seconds**. The new fault
  injector initially matched the earlier period-state audit, which shares the period.lock action.
  Restricted it to object_type=period_lock so it reaches the final audit after notifications;
  both rollback cases then **passed in 51.42 seconds**. Other cases were not rerun after this
  test-only correction. Ruff lint/format and whitespace checks pass. Logs under .run:
  lock-workflow-baseline.log, lock-workflow-final.log, lock-rollback-corrected.log; all terminal.
  No deployment, full release-suite or production-readiness claim.
- Automatic lock generation still needs a durable post-commit preparation job: source validation
  depends on committed approval/audit/freeze records. A process-only after-commit callback is
  insufficient; queued preparation must retain stable identity across retries. Availability
  notification must follow successful pack retention. Re-lock variance and other pack kinds,
  operational CTL-041 acceptance, current release gates and independent accounting approval remain.

## Checkout recovery and dependency remediation — October 14, 2026

- Re-established current state from GitHub main 37e21a7: the old temporary checkout had lost
  tracked source/Git metadata and the prior Platonick workspace path no longer existed. Restored
  a clean clone at /Users/raysang/Documents/eRev-Cloud. Keep future work here, outside /tmp.
  Rechecked public visibility, main as the only remote branch and zero open PRs. No source was
  recovered from the obsolete Desktop original, and no hosted environment was changed.
- Reinstalled locked Python 3.12 and Node 24.5 dependencies. Created an isolated PostgreSQL 17
  cluster at .run/postgres on loopback port 55438, with fresh local owner/app roles, disposable
  test database erev_rv_oct14 and generated ignored .env keys. Prior credentials/processes/data
  were not assumed or reused. This is a new test environment, not a backup-restoration drill.
- On the recovered 37e21a7 backend, the close-pack/audit/source-binding baseline passed:
  **52 tests in 39.59 seconds**, using the fresh database and migrations. This is scoped current
  evidence, not a full backend or operational accounting acceptance run.
- npm audit reported two high-severity dependency groups. Updated only four locked entries:
  brace-expansion 1.1.18 → 1.1.21, 2.1.4 → 2.1.7, 5.0.9 → 5.0.12; source-map-js 1.2.1 → 1.2.2.
  Preserved unrelated optional-platform metadata. Reinstalled from the patched lock; npm audit
  reports zero known vulnerabilities across the dependency tree on October 14. Dependency
  manifests, application code, noncommercial licensing and research exclusions are unchanged.
- Full frontend suite: **192 files / 2,057 tests passed in 70.33 seconds**. TypeScript project
  build (`tsc -b`), ESLint with zero warnings, Vite production build, official OpenAPI staleness
  check and git whitespace check pass. A plain noEmit check initially lacked fresh referenced
  project declarations; the documented build-mode check creates them and passes. Build retains
  its >500 kB chunk warning; jsdom retains its unsupported-navigation warning. No browser,
  accessibility, volume, full backend or hosted release gate is claimed by these results.
- Published scope is the four dependency entries plus dated evidence. All test/tool processes
  are terminal; the isolated local PostgreSQL server remains available for subsequent work.
  .env, database files, dependencies and test logs are ignored. Public research paths remain
  absent and PolyForm Noncommercial 1.0.0 remains unchanged. Direct main; no PR or deployment.
- Local logs/evidence live under the new checkout's ignored .run/. Earlier October 8 evidence
  remains historical. Automatic pack enqueue/availability notification, other pack kinds,
  variance and current release/accounting gates remain outstanding. No deployment/readiness claim.

## Queued audit verification for CLOSE packs — October 8, 2026 (RPS-16 continued)

- Continued from clean published 7fc16e5. New POST /evidence-packs requests no longer need a
  completed verification beforehand. Creation atomically inserts the pack, five supporting
  report runs, a dedicated AUDIT_CHAIN_VERIFY job and its parent: seven jobs, one transaction.
  Idempotent replay returns the original response without adding jobs or changing the binding.
- Added versioned sources v2: pack_id and audit_verification_job_id replace the completed
  verification_id. The audit job's evidence_pack subject and retained period_lock_id are checked;
  a pending tenant-wide job is never reused. Parent readiness waits for the exact job, then
  resolves its result.verification_id and verifies the PASS row/job/digest association. Assembly
  still verifies digest bytes, recorded prefix and lock anchor. Failed/cancelled/missing or
  mismatched results fail the parent; an unrelated PASS cannot substitute. V1 binding parsing
  and canonical bytes remain unchanged, and explicit completed-verification callers still work.
- Initial scoped run: **37 passed, 2 failed in 19.31 seconds** exposed the unsupported period_lock
  job subject; changed to the pack's existing supported subject. Next **37 passed, 4 failed in
  26.56 seconds** exposed the reserved release parameter and a timestamp-serialization fixture
  mismatch; used registry.handler_params and preserved canonical UTC strings. Next **38 passed,
  3 failed in 25.03 seconds** caught a missed test-helper pack_id argument. Corrected it and added
  actual parent wait/failure cleanup; final expanded regression: **68 passed in 58.53 seconds**.
- Tests cover no prior completed verification, atomic seven-job creation/rollback, exact replay,
  waiting/failed/cancelled/foreign-result refusals, failed-parent cleanup without ZIP, successful
  audit and report workers, v1/v2 output, interrupted completion, cancellation, register/download
  and role revocation. The inherited seeded-journal/close-gate caveat remains; not CTL-041 proof.
  Logs /private/tmp/evidence-queued-audit-{db,corrected,final,regression}.log; all terminal.
- Source Mypy, Ruff lint/format, whitespace, regenerated OpenAPI/client types, staleness check
  and frontend tsc --noEmit pass. Updated model/architecture/guide/build status/limits; archived
  earlier readiness/download-boundary notes verbatim. Automatic pack enqueue on lock and truthful
  availability notification, other kinds, re-lock variance and current release/accounting gates
  remain open. RPS-16/CTL-041 and production readiness unclaimed. Direct main; no deployment.

## Stable audit verification job results — October 8, 2026 (RPS-16 prerequisite)

- Continued from clean published abc0514. Reviewed NTF-06: the existing lock notification
  truthfully promises stored snapshots; pack availability must follow successful automatic
  generation. That depends on a stable queued audit result. Found and fixed an audit worker
  retry gap: a crash after verification commit could repeat verification before job settlement.
- AUDIT_CHAIN_VERIFY now returns result.verification_id and reuses the single committed
  tenant/job/trigger result, including FAIL. It does not reverify a newer prefix, create another
  digest/control result, or notify again. Multiple retained rows or trigger mismatch refuse;
  the normal three-attempt policy remains. This proves a historical verification, not current
  chain integrity. No schema migration or public request change; JobResultOut permits this member.
- Initial audit domain/API run: **16 passed in 13.78 seconds**. Expanded ambiguous-result cases
  first had **47 passed, 4 failed in 16.10 seconds** because the test expected final failure on
  attempt two of three. Corrected the witness to fetch/run attempt three without changing the
  retry policy; final audit/API/digest/audit-classification regression: **51 passed in 16.05
  seconds**. PASS/FAIL crash cases retain exact IDs and row/file/control/notification/outbox
  counts; inconsistent cases settle FAILED without new verification. API exposes the exact ID.
- Logs /private/tmp/audit-result-{retry,final,corrected}.log; all processes terminal. Source Mypy,
  Ruff lint/format and whitespace checks pass. Updated architecture/limits and archived earlier
  retention notes verbatim. Next: bind a queued audit job in versioned pack sources, wait for
  that exact successful verification, then integrate automatic lock enqueue and availability.
  Current creation still requires a completed verification; no NTF-06/RPS-16/CTL-041 completion
  or production-readiness claim. Other kinds, variance and release/accounting gates remain open.
  Direct main; no deployment or external notifications.

## Outstanding release verification

These checks need current release-candidate evidence. Historical October 3 results
remain in the dated build history; they do not verify current main. This list does
not authorize deployment, provisioning or changes to a live database.

- make audit-deps: passed on 87f53d1 October 7; rerun for the final release candidate.
- SUPERVISOR VERIFICATION NEEDED: make docker-build
- SUPERVISOR VERIFICATION NEEDED: make compose-verify
- SUPERVISOR VERIFICATION NEEDED: make zap-baseline
- make tf-validate: passed on 40ae405 October 7 (validation only); rerun for final candidate.
- SUPERVISOR VERIFICATION NEEDED: make backup, make restore-verify (isolated local drill only)

## Public repository publication — October 5, 2026 (America/Los_Angeles)

- Owner requested public publication with commercial use prohibited. Prepared the supplied directory
  snapshot for `https://github.com/ChipmunkRPA/erev-cloud`, using PolyForm Noncommercial 1.0.0.
- Updated LICENSE, NOTICE, bundled web copies, Python/npm package metadata, README and About dialog.
  Third-party notices remain intact. Previously granted MIT rights are not revoked.
- Excluded the entire `research-harness/` and `docs/research/` directories at the owner's explicit request; retained application
  source, fixtures, screenshots and documentation. See `docs/release/PUBLICATION-2026-10-05.md`.
- Actual validation: locked `npm ci --ignore-scripts --no-audit --no-fund`; AboutDialog vitest 4/4 passed;
  frontend Vite production build passed (existing large-chunk warning). `python3 scripts/secrets_check.py`:
  4,053 files scanned, 8 allow-listed, zero findings and zero unused entries before this note.
- Additional redacted Gitleaks scan reviewed: test constants, placeholder JWT, accounting identifiers
  and historical test references; research-harness findings removed with the entire directory.
  Targeted credential-pattern scan found only intentional self-test fixtures. These are targeted
  publication checks, not a full security audit. No generated dependencies or real environment/state
  files are staged.
- Backend/integration/accounting suites were not rerun for this licensing/publication change. Earlier
  results below remain historical. No deployment or cloud mutation; production/accounting blockers
  in LIMITS-1.0.md remain. Publication supersedes the earlier private-only instruction in this notebook.

### Publication correction — October 5, 2026

- Removed the entire research-harness and docs/research directories from the publication and replaced the initial root
  commit, so main has no ancestor containing those files. Used an exact force-with-lease against the
  previously verified remote commit. No application code changed; application tests were not rerun
  for this directory removal. External clones and GitHub cached/unreachable objects cannot be recalled
  by a branch rewrite alone.

### Public report website cleanup — October 5, 2026

- Scanned the repository for website references and reviewed documentation matches. Removed 155
  external website URLs plus bare domains across 12 documents and removed the design source
  bibliography. Kept explicit citation-removal markers, mandatory third-party notices, dependency
  metadata and operational endpoints. This does not revalidate the remaining historical prose.
- Follow-up documentation URL scan found only owner links, internal/example addresses and a local
  URL-validation regex. `git diff --check` passed. No application source changed; no application
  tests rerun. Replaced the public root with an exact force-with-lease against the verified head.

## Historical release record

The earlier build-loop notebook is preserved in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).
Current outstanding implementation and verification gaps remain in
[the release limitations](docs/release/LIMITS-1.0.md).
