# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Close evidence register and retained downloads — October 14, 2026 (RPS-20 partial)

- SF-09 and SF-09:pack now expose the scoped paginated first-close register, status filters,
  retained entity/period labels, file counts and manifest hashes, pending-state refresh,
  manifest file list, and authorized ZIP/manifest downloads. Manifest download verifies
  the archive and returns its exact retained bytes, with a committed export audit before
  serving. Both artifact types require all five source/export permissions in entity scope.
- Register counts/hashes use hash-consistent, schema-valid retained metadata and are null
  before success; listing does not open or verify archive payloads. Download still verifies
  archive/source integrity. Updated API docs, OpenAPI/client types, router inventory and
  crawl seed. Evidence tab requires all three read permissions.
- Actual API/worker/MFA/schema/metadata regression: **118 passed in 58.66 seconds**
  (.run/evidence-screen-api-regression.log). Checks include returned labels/count/hash,
  exact manifest bytes, pending/corrupt archive refusal, export audit artifacts/byte counts,
  each source permission's entity scope, revoked roles, and the operational CTL-041 witness.
- Full frontend suite before the final count/hash columns: **2,069 passed across 193 files
  in 73.48 seconds** (.run/evidence-ui-final-regression.log). Final focused screen suite:
  **12 passed in 1.53 seconds**, including those columns and filters/export refusals
  (.run/evidence-register-columns-tests.log). TypeScript, full ESLint, Vite build, Python
  Ruff/Mypy and OpenAPI checks pass. Existing Vite large-chunk warning remains.
- Earlier full frontend runs found route/crawl/tab integration issues (2,062 pass / 4 fail)
  and a test's incorrect filtered-empty expectation (2,067 pass / 1 fail); both are resolved.
  Ten database-free metadata tests also passed independently. All runs are terminal.
- RPS-20 stays unchecked: auditor-request table, generation forms, other pack kinds,
  remaining register details and real browser/accessibility/volume acceptance are outstanding.
  This is a tested repository increment, not a production-readiness claim. Direct main;
  no deployment, new PR, accounting oracle change or permission relaxation.

## Current control gate evidence — October 14, 2026

- Immutable c214c47 control run: **497 passed in 1,076.97 seconds**. No tagged test failed;
  47/49 controls are covered. CTL-045 (AI proposals) and CTL-048 (legacy migration promotion)
  lack tagged tests, so the gate correctly fails. CTL-018 and CTL-041 now pass in this gate.
- Source/dependency bindings match before/after execution. This result attests c214c47,
  not the subsequent screen increment. See docs/release/CONTROLS-2026-10-14.md and local
  .run/reports/controls-report/report.json. Independent accounting approval is still missing.

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
