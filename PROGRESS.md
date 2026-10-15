# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**


## Administrator AI version discovery — October 15, 2026

- Added GET /ai/settings/versions with workspace-wide settings.manage, fixed tenant AI scope,
  status filtering, sorting, counts and cursor pagination. It shares the individual-read scope
  predicate, so refresh can rediscover drafts, pending requests and publication history.
- Tenant Admin already includes config.read; those broader read grants are unchanged. This
  endpoint gives the AI workflow its own scoped read boundary. Accounting authoring is unchanged.
  The settings editor, effective-status presentation and standard J-19/demo journey remain open.
- OpenAPI and TypeScript contracts regenerated. Route/scope architecture checks pass (11),
  backend typing passes 795 files, frontend typing and full lint pass (503 control markers).
  API verification and evidence are recorded in docs/release/CI-2026-10-15.md.
- No deployment or provider calls; frozen CI on 3cf8f5b remains active on its own database.

## Independent administrator AI approvals — October 15, 2026

- New AI submissions use AI_SETTINGS_VERSION with workspace-wide settings.manage review.
  A different Tenant Admin can approve without accounting privileges; self-approval remains
  refused. Retained REGISTRY_VERSION requests keep their original routing and publication hooks.
  Emergency disable, model/text review and immutable content checks remain in the lifecycle.
- settings.manage is an approval permission, so API clients cannot request or retain it in
  effective grants. Migration 0156 updates permission metadata and report filters; upgrade,
  downgrade, enum order and immutable catalogue triggers pass 12 focused checks.
- The broader regression selection passes 95 checks, including API clients, legacy routing,
  emergency disable and earlier report-filter migration compatibility. Evidence:
  .run/ai-admin-approval-{release,migration,release-types,frontend,lint}.log.
- Approval UI subject labels, OpenAPI/TypeScript and the data model are aligned. Frontend typing
  and 55 focused tests pass; backend typing passes 797 files. Full lint passes (503 control
  markers). The settings editor and standard J-19/demo journey remain unfinished.
- No deployment or provider calls. Frozen CI on 3cf8f5b remains running and predates this work;
  broader release verification and independent accounting sign-off remain outstanding.

## Administrator AI version authoring — October 15, 2026

- Added AI-scoped create/read/edit/test/submit/withdraw endpoints under /ai/settings/versions.
  Workspace-wide settings.manage and MFA are required; category and scope cannot be changed.
  Existing registry validation, hashes, simulation jobs, audit and If-Match behavior are reused.
  No publish endpoint or enable shortcut. General accounting authoring remains restricted.
- Admin-only authoring now passes instead of xfail. Lifecycle coverage confirms submission keeps
  AI disabled; isolation checks cover other categories/tenants and invalid accounting values.
  The independent administrator approval-read regression remains strict xfail because generic
  REGISTRY_VERSION routing still needs config.approve. AI-specific routing/visibility and UI are
  next; the standard demo/J-19 workflow is not claimed complete.
- Generated OpenAPI/TypeScript contracts add five paths (six operations); existing paths are
  unchanged. Eight API checks pass and one approval-read check is strict xfail; 34 other
  authority/governance/route checks passed in the expanded run. Typing (794 files) and full
  lint pass. Evidence: .run/ai-settings-author-{api-final,verified-final,types-final,openapi,lint}.log.
  Earlier expanded runs caught test-fixture enum/key-reuse mistakes, corrected in the API rerun.
- No deployment or provider calls. Frozen CI on 3cf8f5b remains active; independent accounting
  sign-off and broader release verification remain outstanding.

## Expose administrator-only AI configuration gap — October 15, 2026

- Preparing the standard J-19/demo fixture revealed that its Tomas/Grace Tenant Admin personas
  cannot author or approve general registry policies. They hold settings.manage, not config.author
  or config.approve. Existing AI re-enable tests add admin rights to accounting-role actors.
- Added a strict expected-failure API regression for admin-only AI draft creation, accepting only
  the confirmed forbidden response as the known failure. Other failures remain errors; success
  becomes a strict XPASS requiring removal of the marker. A companion protects accounting-policy
  denial. This records an unfinished workflow, not a production-readiness pass.
- The corrective scope is an AI-specific admin lifecycle with independent approval and retained
  policy evidence, without broadening accounting privileges or bypassing the emergency switch.
  The standard demo fixture/E2E journey is not added through a permission bypass. Release
  limitations now distinguish this gap from the successful local browser probe.
- Six existing governance/boundary checks pass; the new workflow check is a confirmed strict
  expected failure. Focused typing and full lint pass. Evidence: .run/ai-admin-workflow-{tests,types,lint}.log.
  Frozen CI on 3cf8f5b remains active.
  No deployment, provider call or independent accounting sign-off.

## Future-starting draft reader and browser acceptance — October 15, 2026

- Real browser acceptance exposed GET contract returning 422 after a successful creation:
  October inception followed the fixture's September open-period horizon. The engine correctly
  emitted no member balance (C-05), but the reader treated this as missing trace evidence.
- The reader now recognizes the explicit no-measured-period formula plus V4 draft zero-revenue
  guard, with stored revenue/billing/progress all zero. It shows no measured period and does
  not waive missing-trace refusals. No engine, posting or accounting-policy change.
- 74 reader/acceptance checks pass; the existing damaged-trace API refusal also passes.
  Full lint and backend/API typing pass (791 files). Explicit typing of the older unit module found
  pre-existing Decimal/int comparison and optional-string errors; that module is not claimed clean.
- Chromium with real API/PostgreSQL and the b4b8210 worker image's isolated Linux PDF parser
  passed upload, extraction, nine decisions, confirmation and opening the accepted obligation.
  Source attachment and zero new ledger postings verified. Synthetic provider; seeded session;
  queued handler pumped in-process; Vite frontend. This does not prove standalone worker,
  production web image, login, live-model quality or standard seeded E2E acceptance.
- Evidence: .run/future-draft-reader-{tests,types-final,lint}.log;
  .run/future-draft-browser-{tests,final}.log and .run/ai-live-browser-created.png.
  Full frozen CI remains active on 3cf8f5b; Compose and independent accounting sign-off remain open.
  No deployment. Temporary browser harness retained privately under .run.

## Bound stalled Compose startup and retain failure evidence — October 15, 2026

- Compose verification now bounds up -d (600s default, configurable separately from health
  polling). It stops the client/plugin group, records startup exit 124 and attempts cleanup.
  Eleven Compose checks, focused typing, shell syntax and full lint pass. The first test run
  had one manifest failure during source editing; the stable full selection passes.
- An actual development run at 30s reproduced the host-mount startup stall and failed cleanly;
  cleanup removed all test containers, volumes and network. Logs:
  .run/compose-start-timeout-{verified,types,lint,local}.log; Compose report remains failed.
- Earlier unbounded runs, including a temporary checkout outside Documents, were interrupted
  and cleaned up. That checkout was removed; diagnostics retained. Container hardening/Linux
  PDF checks remain passed on b4b8210, but Compose readiness is unverified. Frozen CI on
  3cf8f5b remains active. No deployment or independent accounting sign-off.

## Container build and Linux extraction verification — October 15, 2026

- Clean b4b8210 passed make docker-build: API/worker/web image hardening and embedded-manifest
  checks passed. The manifest is non-strict. Image identities are in CI-2026-10-15.md.
- The actual worker image, Linux Python 3.12.15 / UID 10001, passed a no-network, read-only
  probe for isolated four-page PDF extraction, nine bundled fields with upload-bound citations,
  memory and CPU limits, credential stripping and timeout child reaping. Logs:
  .run/docker-build-oct15-fixtures.log; .run/ai-image-linux-probe-stdin.log.
- Docker now runs locally. A credential-helper stall was avoided with a task-local anonymous
  config; a stalled host mount was replaced with stdin. No saved credentials changed or images
  pushed. Local Compose verification on b4b8210 and frozen CI on 3cf8f5b remain active.
  Full browser acceptance and independent accounting sign-off remain open; no deployment.

## Package synthetic AI evidence in runtime images — October 15, 2026

- API and worker builds now copy only the synthetic AI fixture bundle needed by FakeProvider.
  Previously local extraction tests passed but image inputs omitted the PDF and response files.
  A behavioral packaging regression reconstructs each Dockerfile's directory COPY inputs and
  invokes the provider from that isolated copy, checking a new upload ID and cited customer value.
- Seventeen packaging/PDF checks, focused typing, Ruff and full lint pass. Logs:
  .run/ai-image-fixtures-{tests,types,lint}.log. This is host-side copied-tree verification.
- Docker Desktop is now running. The first image build was deliberately interrupted to fix this
  packaging defect; Linux base-image pull session remains active, without a completed image.
  Container hardening, Linux PDF limits and full browser upload/acceptance remain unverified.
  Frozen CI on 3cf8f5b continues independently. No deployment or live provider calls.

## Source-page navigation for retained contract review — October 15, 2026

- The document pane now renders one selected source page instead of every page. The labelled
  selector is available for multipage documents; citations select their page and focus its
  highlight. Manual navigation clears the old highlight without changing field decisions.
- Twelve route tests and a cached-data Chromium probe cover page navigation, citation jumps,
  Escape focus and retained edits. Screenshots inspected at 1280/1440 px. Logs:
  .run/ai-review-pages-{tests,types-final,lint,browser}.log. Frontend typing and full lint pass;
  the initial type-check caught two Field API mistakes corrected before the final run.
- Updated release limitations for the responsive panes and page navigation. Full release evidence,
  live browser acceptance and independent accounting sign-off remain outstanding. Frozen CI on
  3cf8f5b is still live; Docker daemon remains unavailable. No deployment or live provider calls.

## Responsive contract review panes — October 15, 2026

- SF-20 now uses Document / Proposed fields panel tabs below 1440 px and two columns above,
  with pane=document|fields in the URL. Field decisions, edited values and reasons survive pane
  and viewport changes. Citations open Document and focus the source highlight; Escape waits
  for the fields pane to become visible before returning focus to the originating citation.
- 24 focused review/decision/tab tests, frontend type checking and full lint pass. A cached-data
  Chromium preview verifies citation/Escape focus and retained edits at 768/1280/1440 px;
  screenshots inspected. Logs: .run/ai-review-panes-{tests,types,lint,browser}.log.
- This browser witness uses retained synthetic data, not a live upload-to-acceptance workflow.
  Full frozen CI on 3cf8f5b remains active; repository readiness and accounting sign-off remain open.

## Bundled extraction fixture through upload and draft acceptance — October 15, 2026

- Strengthened the worker/acceptance witness: source now enters through POST /files and the
  configured fake provider serves the complete nine-field bundled document fixture, replacing
  the test-only one-field provider. The uploaded ID is checked in every citation. Explicit human
  customer/product edits, accepted date/payment terms and rejected terms/second line are recorded
  separately from unchanged original evidence. Persisted booking values, attachment-based access,
  AI_ASSISTED review provenance, one provider call and zero revenue postings are asserted.
- Both acceptance regressions pass on isolated PostgreSQL 55441, with focused strict typing
  (791 sources), Ruff and full lint. Logs: .run/ai-bundled-acceptance-{final,types,lint}.log.
  Earlier attempts retain two corrected fixture assumptions: the test tenant uses a different
  product code, and stored ACCEPT decisions also snapshot their accepted values.
- This is API/worker/database evidence using an in-process PDF parser, not browser interaction,
  Linux isolation, live-model accuracy or independent activation/accounting sign-off. Demo/browser
  fixture setup remains unfinished. Frozen CI on 3cf8f5b remains live on separate PostgreSQL 55439.
  No deployment or live provider calls.

## Repair AI lifecycle audit references and worker inventories — October 15, 2026

- Narrative rejection and expiry now pass distinct source contract IDs to the audit writer
  inside their tenant transaction; missing source contracts refuse rather than writing an
  unlinked event. Extraction creation/rejection explicitly names no pre-existing draft contract.
  Database tests verify hashed detail, the contract audit index, rollback and retained evidence.
- Reviewed expiry's limited tenant-directory read and bounded tenant SYSTEM transitions; added
  the reasons to TXN-07 and caller inventories. Removed the implemented AI_TASK from the pending
  registry while preserving detector checks for omissions, duplication and wrong build phases.
- 24 targeted architecture checks, eight PostgreSQL lifecycle/API checks, strict typing (793
  sources) and full lint pass. Separate cross-tenant source check: .run/ai-audit-keys-tenant-check.log.
  PostgreSQL verification ran on a new isolated instance at 55441; initial encoding setup errors
  are retained separately from the verified UTF-8 run. Logs: .run/ai-audit-architecture.log and
  .run/ai-audit-keys-{pg-verified,types,lint}.log. See docs/release/CI-2026-10-15.md.
- The full frozen CI on 3cf8f5b remains live on 55439 and predates these repairs. No restart,
  deployment or live model call. Browser fixtures/acceptance, remaining implementation and release
  gates, and independent accounting sign-off remain open.

## Bind the known extraction fixture to real upload requests — October 15, 2026

- Found that the bundled fake extraction response matched only its original fixed document ID,
  model and nine-path request. Real upload IDs/full worker catalogues had no fixture. Added a
  bundled-only fallback that reconstructs the complete known redacted-document request before
  reusing retained values, filtering allowed fields and rebinding citations to the upload ID.
  Arbitrary source text, prompts and inconsistent hashes still fail. Custom fixture roots retain
  exact/default semantics. No network calls or accounting writes are introduced.
- AI unit suite: 250 passed, two Linux resource checks skipped on macOS. Focused strict typing
  passes 790 sources; full lint passes. Evidence: .run/ai-upload-fixture-first-failure.log (completed unit run),
  .run/ai-upload-fixture-types.log. Combined AI/architecture run: 508 passed, 12 failed,
  two skipped in .run/ai-upload-fixture-tests.log. Failures identify existing AI audit writers
  without contract keys, unlisted expiry SYSTEM/platform-directory callers and AI_TASK still
  marked pending after registration. No broad pass is claimed; these require follow-up repair.
- Full frozen CI remains live on 3cf8f5b against isolated PostgreSQL 55439, in engine tests.
  Do not restart it or run other database tests there. Known-document fixture adaptation does
  not complete demo/browser seeding, Linux parser proof, browser acceptance or accounting sign-off.
  No deployment or live provider calls.

## Broad frontend verification and frozen CI — October 15, 2026

- Full frontend testing found two inventory failures: omitted SF-20 route IDs and no crawl
  proposal lookup. Added both without a skip/exclusion; a live crawl still requires accessible
  retained extraction evidence. The repaired full suite passes 2,143 tests in 200 files.
  Frontend typing, focused ESLint and formatting pass. Evidence and limits:
  docs/release/CI-2026-10-15.md; .run/frontend-full-oct15-repaired.{log,xml}.
- Frozen make ci on 3cf8f5b has passed environment, full lint and typecheck (938 Python files)
  and is running the broad test stage against isolated local PostgreSQL 55439. Live log:
  .run/production-readiness-ci-oct15.log. Do not restart the live run. This snapshot predates
  the inventory repair; its eventual results must remain attributed to that snapshot.
- No full CI pass is claimed. Real retained-proposal browser fixtures, complete acceptance,
  broader release gates and accounting sign-off remain open. No deployment/provider calls.

## Review round-trip preserves draft work — October 15, 2026

- Added Back to field review with an in-memory draft snapshot. Continuing preserves unrelated
  human inputs and applies changed decisions to corresponding headers and source rows. Rejected
  source rows are removed; human-added rows remain. Renamed obligation keys are rebound explicitly
  when returning to the draft. No field decision is inferred from a changed draft value.
- Fixed row identity collisions when restoring deleted retained rows and when adding rows after
  reopening a draft with gaps in its local row identities. Tests exercise both failures plus
  field-review/form round trips and changed customer/amount decisions.
- 50 focused tests, frontend typing and full lint passed. Evidence:
  .run/ai-review-recovery-{tests,types,lint}.log. Recovery is local component state,
  not persistence across reloads or live browser/API acceptance evidence. Existing server version
  preconditions remain authoritative; returning to review captures the current displayed ETag
  only on explicit continuation. Broader release verification and accounting sign-off remain open.
  No deployment or live provider calls.


## Outstanding release verification

These checks need current release-candidate evidence. Historical October 3 results
remain in the dated build history; they do not verify current main. This list does
not authorize deployment, provisioning or changes to a live database.

- SUPERVISOR VERIFICATION NEEDED: make audit-deps (October 14 development audit passed; rerun on a clean final candidate).
- make docker-build passed on clean b4b8210 (October 15); rerun on the final candidate.
- SUPERVISOR VERIFICATION NEEDED: make compose-verify
- SUPERVISOR VERIFICATION NEEDED: make zap-baseline
- SUPERVISOR VERIFICATION NEEDED: make tf-validate (October 14 backend-disabled development validation passed; rerun on a clean final candidate).
- SUPERVISOR VERIFICATION NEEDED: make backup, make restore-verify (isolated local drill only)

## Historical release record

The earlier build-loop notebook is preserved in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).
Current outstanding implementation and verification gaps remain in
[the release limitations](docs/release/LIMITS-1.0.md).
