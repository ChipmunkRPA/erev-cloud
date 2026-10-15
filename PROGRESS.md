# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Evidence navigation retains pack context — October 14, 2026

- Browser screenshot review found that successful generation dropped entity/book/period
  from the detail URL: the header then showed the default entity and January while the pack
  named AVM-US/August. Register links, grid row navigation and generation now carry the
  pack's own selectors; the detail breadcrumb returns to that scoped register.
- Component checks: 34 tests passed in three files (2.30s), TypeScript and targeted ESLint
  passed. Production build passed. Focused real-browser workflow passed in 46.0s, including
  the exact scoped URL, successful generation, downloads and light/dark accessibility.
  Reviewed the resulting screenshot: header shows AVM-US/August locked, matching the pack.
  Logs: .run/evidence-context-tests.log and .run/evidence-context-browser.log.
- Browser test servers stopped. Full CI on 165d63c remains live with known failures;
  pending backend identity/IDOR repairs are not part of this frontend change. No deployment
  or complete release-gate claim. Broader release and accounting review gaps remain open.

## First-close browser acceptance — October 14, 2026 (RPS-20 continued)

- Added a real-browser workflow that selects a retained first-close lock, creates a pack,
  waits for successful retention, checks all 12 contents sections, downloads manifest/ZIP,
  compares the downloaded manifest SHA-256 with the displayed value, and checks every file
  path/hash/copy control. Light/dark accessibility checks cover register, form and detail.
- The initial closed-world run passed 9 tests and failed this new test on the register pack
  link target size. Enlarged the link to 24px minimum height. A focused retry then exposed a
  test interaction error: the shared combobox opens with Arrow Down, not input click alone.
  Corrected that interaction and waited for loaded register data before screen capture.
- Final focused browser run: 1 passed in 46.9s against the retained local demo world; this
  is not a fresh full-browser gate. Evidence components: 70 tests passed in four files.
  TypeScript and targeted ESLint passed. Reviewed register, form and detail screenshots.
  All browser test servers stopped. Logs: .run/evidence-browser-retry-2.log and
  .run/evidence-browser-regression.log. Initial full-run failure remains preserved.
- Full immutable CI on 165d63c is still running and has known failures; this entry does not
  claim a passing full release gate. Other pack kinds, re-lock variance, broader acceptance
  and independent accounting approval remain open. No deployment.

## Current CI preflight and direction-aware evidence tables — October 14, 2026

- Immutable make ci on fcbfaa3 reached lint after local-only environment repair: a missing
  demo TOTP seed was generated in ignored .env, and a separate allow-listed local CI dev
  database was created. The existing development database remains unchanged; process-only
  URL overrides select the new database, with no credentials printed or committed.
- CI found three DS-LINT-10 violations: evidence contents, file and auditor-request tables
  used text-left. Changed them to logical text-start for direction-aware alignment.
- Full make lint passes: 2,049 Python files formatted; 510 design-scanned files, zero findings;
  vocabulary, 133-package license scan, 3,478-file secret scan, OpenAPI, registry, 18 fixtures
  and all 497 control markers pass. Marker validity does not prove the controls pass.
  Full make typecheck passes (876 backend source files plus frontend).
- The initial CI run is terminal, failed at design lint before tests. Its source hash is
  fcbfaa365bdfb5ecf7a4b1184cafecb7ffd1eaec, tree b20a7f01135cda47153d1c8dc1b23b0dcbedcddc;
  immutable source and dependency bindings matched. A clean post-fix full CI run is next.
  No complete CI, deployment or production-readiness claim is made.

## Evidence metadata read audit — October 14, 2026 (RPS-16 continued)

- Successful register/detail HTTP reads now commit evidence.read before returning no-store
  responses. Register facts contain only authorized returned-page IDs (the existing AUD-FACT
  digest rule bounds large pages), including empty pages. Detail facts bind status, retained
  lock and manifest hash. Internal header reads during download add no duplicate read event.
- Regression verifies durable actor/object metadata, exact cursor-page populations, empty
  pages, invalid filters/missing records, revoked access, unchanged export counts, and failure
  after audit append rolling back both the event and successful metadata delivery.
- Final evidence/close, audit-writer and complete MFA regression: 37 passed in 170.41s.
  Ruff formatting/lint, source mypy and OpenAPI compatibility passed. Earlier test iterations
  corrected actor identity/count expectations and fault injection before the final passing run.
  All processes are terminal. Frontend unchanged; its earlier results remain historical.
- Archived the oldest publication notebook section verbatim to the build history to preserve
  the 20 KB limit. No deployment or accounting-calculation change. Other pack kinds, re-lock
  variance, browser/release gates and independent accounting approval remain outstanding.

## First-close contents checklist — October 14, 2026 (RPS-20 continued)

- Detail now lists required sections and exact missing payload filenames, identifies the
  retained lock, sorts file paths and provides named keyboard-accessible file/manifest hash
  copy. Manifest presence does not claim byte verification; download verification is unchanged.
  The separately hashed manifest is correctly outside its own payload list.
- Direct comparison with the backend assembler confirmed all 36 required payload paths match.
  Tests cover complete/missing sections, a missing supporting source, manifest treatment,
  retained lock and exact clipboard bytes. Focused: 16 passed (1.68s). Full frontend:
  195 files / 2,093 tests passed (70.48s); TypeScript, full ESLint and production build passed.
  Existing build chunk-size and jsdom navigation warnings remain. All checks are terminal.
- No backend accounting behavior changed, no database tests rerun, no deployment. RPS-20
  remains open for other kinds, re-lock variance, remaining presentation and real browser
  acceptance. Independent accounting approval and broader release gates remain outstanding.

## First-close generation form — October 14, 2026 (RPS-20 continued)

- Added a modal for entity, book, period and explicit retained first-close lock selection,
  using the existing CLOSE API and command pipeline. It follows all entity/period cursors,
  includes authorized inactive historical entities/books, clears dependent selections,
  and requires all export/source permissions for the chosen entity plus selector-read access.
  Re-lock/reopen records and locks without retained snapshot metadata are not offered.
- A successful response opens the new pack. An accepted response without navigation
  headers disables resubmission. Lost-response retries retain the original idempotency key,
  including after closing/reopening the modal or reselecting the same lock. Backend
  refusals remain visible; no optimistic pack or placeholder job is created on the client.
- Final frontend suite: **2,089 passed across 195 files in 65.15 seconds**
  (.run/close-pack-form-final-full.log). The 11 form tests also passed independently in
  1.46 seconds (.run/close-pack-form-final-focused.log). TypeScript, full ESLint and Vite
  build pass; existing jsdom navigation and large-chunk build warnings remain. No backend
  code or accounting result changed, so no database test was restarted for this UI increment.
- Earlier failures were test interactions: the combobox picks on mousedown, and the
  accepted-state button is replaced by its tooltip wrapper. Assertions now target the
  current accessible control. Initial pagination inference errors were fixed with explicit
  ListPage types. All processes terminal. No deployment or new PR; direct main.
- RPS-20 stays incomplete: re-lock variance, other pack kinds/forms, remaining presentation
  and real browser/accessibility acceptance. Independent accounting sign-off remains absent.

## Auditor request navigation — October 14, 2026 (RPS-20 continued)

- Added the 20 specified auditor requests, their available report sources, accessible
  action menus and context-preserving destinations. Reconciliation opens the selected
  entity/book/period; walkthrough opens audit events filtered to the signed-in user.
  Only reports returned by the API get actions. Pack generation is hidden without
  evidence.export and explicitly unavailable where the backend kind is unfinished.
  No placeholder generation commands or claim of complete read auditing is introduced.
- Fixed catalogue pack links from the obsolete /evidence path to /reports/evidence,
  preserving entity/period/book and requiring all evidence read permissions. Added
  catalogue permission/context checks and aligned table/row hooks with SCREENS_B.
- Full frontend: **2,078 passed across 194 files in 60.51 seconds**
  (.run/auditor-requests-full.log); TypeScript, full ESLint and Vite build pass. Existing
  jsdom navigation and Vite large-chunk warnings remain. Final focused checks cover
  table rows, both unavailable pack menus, context encoding, own-actor filtering,
  missing export access and failed definition reads (.run/auditor-requests-final.log).
- RPS-20 remains incomplete: generation forms and missing backend kinds, read-only
  presentation, remaining register details and real browser/accessibility acceptance.
  Repository only; direct main, no new PR or deployment.

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

## Historical release record

The earlier build-loop notebook is preserved in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).
Current outstanding implementation and verification gaps remain in
[the release limitations](docs/release/LIMITS-1.0.md).
