# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Reopen-basis isolation coverage — October 14, 2026

- Reproduced the catalogue-completeness failure: period_reopen_basis had no shared
  row builder. Added its period/entity/state dependencies and registered the builder.
  The existing sweep now proves own-row visibility, foreign-tenant read/write denial
  and no-context denial. Entity-scope checks include the reopen basis and now verify
  forbidden updates/deletes as well as reads/inserts for all five reference cases.
- Fixed two typing issues in touched helpers: explicit obligation-version UUID inputs
  and a real user identity for the loss-provision fixture instead of None.
- Final focused PostgreSQL run: 10 passed (6.93s); strict Mypy on both touched files,
  Ruff and diff checks pass. Evidence: .run/reopen-rls-baseline.log (failure),
  .run/reopen-rls-verified.log and .run/reopen-rls-types-final.log. Earlier Mypy invocations
  used incomplete module-path configuration; final check uses MYPYPATH and explicit
  package bases. No production runtime or schema change.
- Full CI 165d63c remains live around 32%; this focused repair does not establish a
  passing release gate. Original exclusions/noncommercial license retained; no deployment.

## Material-right replacement and activation routing — October 14, 2026

- Verified native term creation followed by an integration's price-only draft replacement:
  the same obligation retains identical immutable terms and exactly one record.
- Baseline activation omitted MANUAL_ENTRY for the human term preparer. MATERIAL_RIGHT
  still kept that request pending; no auto-approval bypass was demonstrated. Routing now
  reads option authors (including represented preparers) and persisted option records.
- Activation-routing regressions: 12 passed (91.18s), including untouched-integration
  auto-approval. A SYSTEM/AUD-FACT represented-preparer fixture plus import checks:
  31 passed (18.19s). Full typecheck, Ruff and diff checks pass. Logs:
  .run/material-right-replacement-baseline.log, .run/material-right-routing-regression.log,
  .run/material-right-routing-facts.log, .run/material-right-routing-types.log.
- Key/product removal, corrections, races, complete historical replacement, UI and
  migration acceptance remain open. Original CI 165d63c is live in demo/performance
  seeding. Noncommercial licensing and publication exclusions retained. No deployment.

## Native material-right draft entry — October 14, 2026

- Added the immutable option-term POST with contracting-entity permission, group/contract
  locks, parent-stream If-Match, DRAFT/no-pending-review checks and atomic computation.
  Invalid method, currency, likelihood or non-option classification leaves no terms
  or computation. Dedicated reads use the contracting entity's date.
- Reproduced and fixed an approval gap: a different term preparer could approve Maya's
  activation submission. Option authors are now excluded by the approval kernel;
  independent review succeeds. AUD-FACT represented-preparer identities are included.
- Activation and route/import/scope checks: 62 passed (151.74s). Final API regressions:
  2 passed (20.43s), including idempotent replay and one contract-bound creation audit.
  Full typecheck (880 source files plus frontend), Ruff and diff checks pass.
  Logs: .run/material-right-native-regression.log, .run/material-right-native-final.log,
  .run/material-right-native-types.log. OpenAPI/TypeScript and command docs updated.
- Corrections, draft replacement/race acceptance, full method matrix, UI, migration,
  populated snapshot and independent accounting acceptance remain open. Original full
  CI 165d63c remains live and is not current-candidate evidence. No deployment.

## Activation approval binds material rights — October 14, 2026

- Found and repaired a review gap before exposing native term entry: adding T-CON-14
  terms after activation submission previously left the approval hash unchanged.
  The baseline review returned 200. Activation content now binds identities and all
  option accounting fields in deterministic order. Contracts without terms retain
  their existing content shape and pending hashes.
- A real API review now returns 409 stale-approval after injected terms, leaves the
  contract inactive with no postings, and succeeds only after fresh submission and
  review. The regression also checks the full bound content, including null fields.
- Full activation suite: 19 passed (121.46s); .run/material-right-approval-regression.log.
  Focused repair: 1 passed (14.05s). Full typecheck and Ruff pass. Baseline evidence,
  implementation boundaries and next entry requirements are recorded in
  MATERIAL-RIGHTS-IMPLEMENTATION.md. Native entry and corrections remain unfinished.
- Full CI 165d63c is still running independently. No deployment; publish directly to main.

## Material-right bundle and reads — October 14, 2026

- Connected immutable option terms to real engine bundles at known_at, with stable
  obligation/estimate keys. Dedicated and embedded obligation reads now return terms
  and status from non-voided exercise/expiry events at the effective and record cuts.
  Contract visibility still governs access; expiry dates alone do not change status.
- Added dedicated-read as_of/known_at parameters, offset validation and regenerated
  OpenAPI/TypeScript schemas. Four database/API tests pass (22.83s): real computation
  receives stored terms; both reads agree; historical absence, event voids and tenant
  isolation hold. Route/import checks: 38 passed (18.71s). Full typecheck (879 source
  files plus frontend) and Ruff pass. Evidence: MATERIAL-RIGHTS-IMPLEMENTATION.md.
- Corrected fixture transaction/head/query-parameter mistakes found by initial runs;
  production guards and expected results were retained. Tests insert terms explicitly:
  native entry, governed corrections, migration conversion and populated snapshot
  acceptance remain unfinished. Full CI 165d63c remains live. No deployment.

## Material-right persistence foundation — October 14, 2026

- Migration 0145 creates immutable T-CON-14 option terms and E-92 option_type, tenant
  RLS, foreign keys, unique obligation and contract lookup index. Database checks
  enforce required discount terms, amount/ratio bounds, same-contract obligation and
  exercise-likelihood estimate, and currency agreement. A composite FK prevents a
  later parent-currency change. Application and owner mutation attempts are refused.
- Added ORM export, shared row builder, snapshot classification, cutoff, dependency
  order and likelihood-reference remapping. Removed obsolete pending-table entries
  and updated inventory assertions and the data-model specification.
- 77 focused schema/RLS/snapshot/architecture checks passed (9.99s); final parent guard
  and migration downgrade/upgrade: 2 passed (7.59s). Full typecheck (878 source files
  plus frontend), focused Mypy, Ruff and formatting pass. Evidence and remaining
  lifecycle work are in MATERIAL-RIGHTS-IMPLEMENTATION.md.
- A broader check found the existing missing period_reopen_basis test-row builder;
  retain that failure for repair. Native term entry, engine bundle reads, API status,
  migration conversion and populated snapshot acceptance are not yet implemented.
  Full CI 165d63c remains live around 30%. No deployment; direct main publication.

## Native material-right gap confirmed — October 14, 2026

- Source tracing shows B3-24 needs implementation, not only another API test: bundles
  always send empty material_rights, T-CON-14 is absent, the dedicated read always
  returns 404 and the embedded read always returns null. Migration capture refuses
  converted option records. Existing engine regressions bypass these missing paths.
- Corrected the limitation and added MATERIAL-RIGHTS-IMPLEMENTATION.md with required
  persistence, governed entry, historical reads, migration, UI and acceptance coverage.
  Preserve the migration refusal until the complete terms path exists. No runtime
  change or claim of product support; full backend CI remains running.

## Renewal benefit-period engine verification — October 14, 2026

- Added eight B3-24 regressions through canonicalization, obligation construction,
  allocation and full-engine posted revenue, for ASC606 and IFRS15. A 12,000 renewal
  right spans 24 months at 500/month when the inception estimate says 24 months;
  without an estimate it keeps the booked 12-month term at 1,000/month.
- A later 36-month estimate does not change inception pricing. A discount voucher
  keeps its own term rather than inheriting the renewal estimate. Tests check exact
  period keys, posted amounts, total, option SSP and obligation dates.
- Initial fixture omitted the explicit MONTHLY_EVEN policy and therefore produced
  daily amounts; corrected the fixture's convention, preserving expected figures.
  A subsequent negative-case fixture used a nonexistent GroupInput field; corrected
  it to replace only the contract input. No engine implementation changed.
- Entire stage-03 suite: 41 passed (3.02s), .run/benefit-period-s03-final.log.
  Strict Mypy, Ruff and formatting pass. B3-24 now distinguishes this evidence from
  still-missing API-entry, answer-key and independent accounting acceptance.
- Full backend CI 165d63c remains running around 29%; existing known failures have
  later repairs. Repo only, direct main publication, no deployment.

## Point-in-time royalty licences — October 14, 2026

- Repaired the API/DB mismatch that rejected the engine's supported point-in-time
  royalty licence template. Migration 0144 permits only the LICENCE/ROYALTY exception;
  non-licence obligations remain restricted. Updated T-REF-23's documented constraint.
- API-driven RPO tests verify a 15,000 statement against a 12,000 guarantee adds 3,000,
  recognition waits for delivery, April delivery releases 15,000, and a May downward
  correction reverses 1,000. Both initial delivery states reconcile with zero unexplained.
- Initial tests exposed template rejection; the next attempt exposed a missing trigger
  in the new delivery fixture. Corrected fixture and expanded checks: 4 passed (21.56s).
  Final full template/RPO files and DB invariant: 22 passed (70.78s), recorded in
  .run/rpo-royalty-regression.log. Full production typecheck, focused report-test Mypy,
  Ruff and formatting pass. Standalone Mypy of all selected test files encountered
  existing fixture-import/row-typing issues; it is not claimed as passing.
- Fresh closed browser gate bce381c passed 10/10 and retained 22 PNGs after cleanup;
  see BROWSER-2026-10-14.md. Full backend CI 165d63c remains in progress.
- B4-2's combined cases and other release limitations remain open. No deployment or
  accounting sign-off; publish directly to main without a PR.

## Sandbox reset source isolation — October 14, 2026

- B7-5's source-provenance observation is permitted by SBX-02, which requires creation
  events in both tenants. The refused-type audit defect was repaired in 1ab522c.
- Strengthened SNAPSHOT and EMPTY reset acceptance to compare every tenant-scoped source
  row's full contents outside audit head/events, notifications, outbox and snapshot metadata.
  Existing assertions still check the expected provenance events, snapshot successor target,
  source row-count restrictions, old-sandbox archival and successor results. The populated
  K-03 case explicitly requires nonempty contract and subledger rows before comparison.
- First accounting-table comparison: 2 passed (29.63s). Broadened source comparison:
  2 passed (29.44s). Ruff and strict test Mypy pass. Logs .run/sandbox-reset-source-
  {contents,all-rows,types-final}.log. Separate local repair server stopped.
- Updated browser gate documentation to locate screenshots/traces via the report's artifacts
  field. Fresh closed browser gate bce381c and backend CI 165d63c remain live. These checks
  do not establish full CTL-043, release acceptance or accounting sign-off.

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
