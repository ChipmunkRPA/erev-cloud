# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Bound AI export authorization — October 15, 2026

- Added a frozen/versioned server-captured export binding: original tenant, actor id/kind and
  maximum OWN/TENANT scope. Dataset builds require it; subsequent promotion cannot widen an
  own-call request, and a workspace export still requires current workspace-wide settings.manage.
- PostgreSQL/CSV/XLSX verification covers serialized bindings, promotion/demotion, cross-owner,
  cross-tenant, actor-kind and permission/scope loss. Three API checks and backend typing (796
  files) and full lint also pass. Evidence: docs/release/CI-2026-10-15.md.
- Queued export is still unfinished. Next persist the binding, reconstruct current grants in
  the worker, guard replay/download before returning any bytes, and wire the menu. Other release
  gates remain open. No deployment/provider calls; publish directly to main after verification.

## Authorized AI export dataset foundation — October 15, 2026

- Added the internal call-export dataset using current owner/tenant visibility and standard
  CSV/XLSX writers. Unknown usage stays distinct from zero; totals name only known usage.
- Real PostgreSQL plus parsed CSV/XLSX witnesses prove scope, spreadsheet-formula escaping and
  unknown/zero cells. An initial test caught unrestricted system identity access; the builder
  now requires a user/API-client identity and refuses system/operator/missing-ID contexts.
- Six API/export/formula checks, the final identity check, backend typing (796 files) and full
  lint pass. Evidence: docs/release/CI-2026-10-15.md.
- Export is NOT yet public: next wire queued execution/current-grant reconstruction, retained
  output ownership/revocation checks and the download menu. No deployment/provider calls.
  Other call-log and broader release/accounting gates remain open.

## Saved call-log layouts — October 15, 2026

- Connected SF-15:ai-call-log to the shared saved-view selector and controlled grid columns.
  Private layouts persist under the current membership; shared layouts restore presentation
  without changing call visibility. Call records and drawer ids are never saved in view config.
- Opening a call now retains the active view and sort. Twenty-one screen/selector/settings
  checks, frontend typing and full lint pass; evidence is in docs/release/CI-2026-10-15.md.
- Export, linked proposals, hash-copy controls, J-19 and broader release/accounting gates stay
  open. No deployment or provider calls. Publish directly to main after verification.

## Preserve unknown token usage in call evidence — October 15, 2026

- Added usage_known to call-log list/detail, using the exact SQL evidence predicate used by
  budget admission. The screen shows Unknown and a drawer explanation for missing usage;
  reported zero remains zero. Compatibility counters and retained records are not rewritten.
- Twenty-four API/PostgreSQL budget checks and six screen checks pass. Backend typing (796
  files), frontend typing and full lint pass. The prior full frontend result is not relabelled as covering
  this correction. Evidence is recorded in docs/release/CI-2026-10-15.md.
- Usage reconciliation, remaining call-log features and broader release/accounting gates are
  still open. No deployment or provider calls; publish directly to main after verification.

## AI call-log screen and bookmarked evidence — October 15, 2026

- Added /settings/ai/call-log with the shared grid, newest-first 50-row API pages, outcomes,
  token counters, latency and actor/configuration evidence. Named-entity settings grants do not
  open workspace evidence; ai.use opens only the actor's own list through the server's rules.
- A docked drawer reads GET /ai/model-logs/{id}; bookmarks/reloads reauthorize the call instead
  of trusting a retained row. Backend tests prove owner and tenant detail refusal as 404.
- Full frontend suite: 2,164 tests pass in 203 files. Ten API/route checks, 35 focused frontend
  checks, backend typing (795 files), frontend typing and full lint pass. Real Chromium with API/PostgreSQL passes grid, drawer and bookmark reload;
  screenshots inspected and the drawer layout corrected. Details: docs/release/CI-2026-10-15.md.
- CSV/XLSX export, saved views, linked proposals and hash-copy controls remain open, as do J-19,
  broader release gates and independent accounting sign-off. No deployment or provider calls.

## Authorized AI call evidence API — October 15, 2026

- Added GET /ai/model-logs with newest-first cursor pagination, optional counts and typed
  configuration/hash/token/outcome/actor evidence. No provider call or proposal content read.
- Workspace-wide settings.manage sees tenant calls; ai.use sees only its own actor id and kind.
  These predicates apply before counts and pagination. A scoped administrator is refused unless
  also holding ai.use, which still returns only that actor's calls. Unsupported filters refuse.
- Two PostgreSQL API tests and eight route architecture checks pass. Backend typing (795 files),
  frontend typing, generated OpenAPI/types and full lint pass. The full frozen CI remains active
  on 3cf8f5b and is not evidence for this change. See docs/release/CI-2026-10-15.md.
- Call-log UI/drawer/export, standard J-19 and remaining release/accounting gates stay open.
  No deployment or provider call. Published directly to main after verification.

## AI settings without general configuration read access — October 15, 2026

- Added GET /ai/settings/values under workspace-wide settings.manage, returning only effective
  AI values and their reset defaults. The form no longer calls general configuration routes.
  Parameter choices are fixed by the server's AI catalogue; accounting keys cannot be selected.
- A custom role holding only settings.manage now passes form reads, validation-job reads,
  submission and a different custom-role administrator's approval. General policy/catalogue
  reads remain 403; draft values and another tenant's values are excluded. A real Chromium
  submission with this limited role passes and leaves AI off pending approval.
- Fifteen focused frontend tests, frontend typing, backend typing (795 files), route/scope checks
  and full lint pass. API evidence includes the corrected custom-role lifecycle after advancing
  its frozen clock past its predecessor publication. Details: docs/release/CI-2026-10-15.md.
- No deployment, provider call or new role grant. Standard demo/J-19, release gates and independent
  accounting sign-off remain open. Frozen CI on 3cf8f5b continues on its separate database.

## Administrator AI settings screen — October 15, 2026

- Added /settings/ai and its workspace-wide settings.manage navigation guard. The page shows
  effective availability and platform disable, edits the eight documented values, resumes saved
  versions and submits through validation plus independent approval. Emergency disable uses a
  confirmation dialog and remains available during validation. Pending requests show their
  number, preparer and review link.
- Retries retain the original statement, row-version precondition and command keys. A newer read
  cannot silently replace the edit precondition; even a SUBMITTED read replays the caller's own
  submission key. Failed validation stops submission; reset-to-default drafts use catalogue values.
- Full frontend suite: 2,160 tests pass in 202 files; 43 focused checks and typing also pass.
  Real Chromium + API + PostgreSQL verifies creation, validation job and submission while AI
  remains off; desktop and pending screenshots
  inspected. A narrow viewport retains the existing minimum-width gate. Evidence is in
  docs/release/CI-2026-10-15.md. The private browser harness remains excluded in .run.
- No deployment or provider calls. Standard demo/J-19 and accounting sign-off remain open.
  Frozen CI on 3cf8f5b remains running; its snapshot predates these changes.

## Effective AI status for administrator settings — October 15, 2026

- Added read-only GET /ai/settings under workspace-wide settings.manage. It uses the AI job
  settings reader, distinguishing published enablement from effective availability, workspace
  emergency disable and platform disable. Provider identity and model/budget/text/redaction
  values are returned without credentials, provider construction or provider calls.
- API/PostgreSQL checks pass (31), covering draft exclusion, publication, both switches,
  defaults, tenant isolation and administrator denial. Backend typing passes 795 files.
  OpenAPI/TypeScript regenerated; frontend readers cover status and retained version pagination.
  Detailed verification is in docs/release/CI-2026-10-15.md.
- The settings editor and full J-19/demo journey remain unfinished. No deployment. Frozen CI
  on 3cf8f5b remains running; independent accounting sign-off and release gates remain open.

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
