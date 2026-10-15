# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Workspace-type refusal audit — October 14, 2026

- Refused PATCH /tenant requests naming kind now append tenant.update / DENIED in the
  caller's tenant and preserve the 409 tenant-kind-immutable response. The event identifies
  the actor, tenant, refused field and problem; it survives rollback of the command.
- Refusals read without an update lock, avoiding a conflict with the independent audit
  transaction's tenant foreign key. Normal changes still lock and check row versions.
  Permission and If-Match checks remain in place; refused mixed changes do not rename a tenant.
- Isolated PostgreSQL API and sandbox tests: 2 passed (10.36s). Final actor assertion:
  1 passed (9.76s). The first attempt could not connect because the local repair server
  restarted on its default port; rerun used the intended separate port 55439. Server stopped.
  Logs: .run/tenant-kind-audit-{tests-fixed-server,actor-final}.log. Full lint/typecheck
  pass; audit/guard architecture checks: 8 passed (8.61s), logs with suffixes lint, types
  and architecture.
- A focused browser attempt against the old demo database found its temporary encrypted
  snapshot files were gone, so its 500 response is not an application acceptance result.
  Screenshots and failure trace were retained. A fresh closed gate on bce381c is now running
  with a matching local database/file store; full backend CI on 165d63c also remains live.

## Retained browser artifacts — October 14, 2026

- Browser gate reports now name a unique artifact directory for each run. Each Playwright
  invocation writes screenshots and failure traces below it, so immutable-context cleanup
  copies them with the report. Earlier runs cannot supply screenshots to a later result.
- Authentication/network runtime state has a separate invocation directory and is removed
  on completion. Direct Playwright usage retains its existing default paths.
- Regression checks: 43 script/context tests passed (34.69s), including successful/failed
  gates retaining nested files after context deletion. A real Chromium probe produced both
  PNG captures and a valid trace ZIP from an intentional failure after capture; this is
  artifact verification, not an application acceptance pass. Final script checks also cover
  runtime-session cleanup: 10 passed (5.74s). Ruff, ESLint, shell syntax and full typecheck pass.
- Logs: .run/e2e-artifact-{all-tests,script-final,typecheck-final,real-browser}.log.
  The earlier closed-world gate remains bound to 3e60e6a and its lost screenshots cannot be
  recovered. Full backend CI on 165d63c is still live; broader readiness remains open.

## Fresh closed-world browser gate — October 14, 2026

- Immutable make e2e CLOSE=1 PROJECT=closed on 3e60e6a passed all 10 tests in
  58.7 seconds after a fresh local schema reset, migration, closed-world seed and build.
  Zero failed, flaky or skipped tests. Coverage includes locked schedules/reports,
  permanent-lock workflows and first-close generation with verified retained downloads.
- Source tree and context hashes match before/after; dependency bindings are consistent.
  The test servers stopped normally. Logs: .run/e2e-3e60e6a-full.log and
  .run/reports/e2e/{report,playwright-1-closed}.json. Exact binding and limits:
  docs/release/BROWSER-2026-10-14.md. This is the closed project, not every browser project.
- The gate retains JSON results but its temporary context cleanup removed newly generated
  screenshots. Existing worktree screenshots predate this run and cannot prove its visuals.
  Artifact retention needs repair. Backend CI on 165d63c remains live with known failures;
  later backend repairs and independent accounting acceptance are not covered by this gate.

## Evidence identity and authorization repairs — October 14, 2026

- Automatic pack availability resolves the validated locking actor through the shared
  record-actor reader; the identity architecture rule needs no exception.
- IDOR coverage includes all 49 GET-by-ID routes. A shared operational fixture builds actual
  retained packs. Tests cover foreign-tenant denial, authorized controls, manifest/ZIP reads,
  matching/excluded entity scopes and register visibility. Generic rows use a separate fresh
  tenant pair; no source validator or permission guard is bypassed.
- Integration create/update checks owner eligibility after proposed entity scope is valid.
  Invalid scope previously also produced a dependent owner error. Valid scope expansion still
  requires an eligible owner; scope refusal and denial auditing remain enforced.
- Focused tests used a separate local PostgreSQL instance and file/runtime paths, leaving
  CI/browser databases untouched. Initial run: 38 passed, 1 failed (279.75s); only the new IDOR
  setup failed. Fixed clock rollback/MFA reuse, generic version collisions with operational
  data, and uppercase persona email. Final IDOR: 4 passed (55.73s). Operational pack acceptance
  also passed after the shared-clock correction. Assertions were not weakened.
- Architecture: 267 passed (215.81s). Full lint/typecheck pass; final fixture/test edits pass
  Ruff/Mypy. Actor/integration unit checks: 25 passed. Logs under .run: isolated-repairs-first,
  isolated-idor-{clock-fixed,worlds-fixed,final}, pending-repairs-{architecture,full-lint,full-types}
  and idor-repair-types-final (all .log). Temporary repair server stopped. CI on 165d63c and
  browser gate on 3e60e6a remain live; no full-gate, deployment or accounting-approval claim.

## Integration command unit fixture — October 14, 2026

- Three CPU-only integration command tests failed because their fake human principal lacked
  membership_id after connection ownership was introduced. Added the distinct membership ID
  and explicit unassigned owner to the fake connection row; no permission assertion changed.
- Actor and integration command unit regression: 25 passed in 1.03s after repair (previously
  3 failed, 22 passed). Ruff lint/format pass. Logs .run/pending-repairs-units{,-fixed}.log.
  Run used the working tree, including pending scope/identity repairs; only this fixture fix
  is published here. Full architecture, backend CI and fresh closed-browser runs are ongoing.

## Runtime dependency and infrastructure validation — October 14, 2026

- make audit-deps passes on HEAD 4542527 with pending backend edits: all 77 pinned Python
  runtime distributions audited, zero vulnerabilities; npm production audit reports zero
  advisories at every severity. Five environment markers removed so the audit includes the
  whole pinned runtime set. Installed dependency bindings are consistent with both lockfiles.
- make tf-validate passes using Terraform 1.16.4: backend-disabled init, format check and
  validation of ten files/four providers. Input hashes agree before/after; provider versions
  google/google-beta 6.50.0, archive 2.8.1 and random 3.9.1. No cloud state or credentials used.
- Both runs are explicitly worktree-dirty development evidence, not immutable release gates.
  Reports remain in .run/reports/{audit-deps,tf-validate}/report.json; logs are
  .run/{audit-deps,tf-validate}-oct14-current.log. Docker client exists but its local daemon
  is unavailable (.run/docker-availability.log), so no container validation is claimed.
- Full backend CI on 165d63c remains live. Pending source/test repairs await database access;
  independent accounting approval and broader release checks remain open. No deployment.

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
- Full frontend on df95848: 195 files / 2,093 tests passed (108.82s);
  log .run/frontend-df95848-full.log. Existing jsdom navigation warning remains.
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
