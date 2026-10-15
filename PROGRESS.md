# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Privacy catalogue coverage gate — October 15, 2026

- Classified the new private navigation history and the retained AI file references/export
  authorization binding using existing catalogue rules. Corrected its documentation header and
  kept the file-hold test's complete list of retained AI sources.
- Added make privacy-check to lint: 90 source-only checks cover catalogue/doc agreement,
  shredding rules, anonymisation names, patterns and offsets. This executes assertions rather
  than relying on collection. Verification is in docs/release/CI-2026-10-15.md.
- No deployment or accounting-policy change. Broader release checks and sign-off remain open.

## Private recently viewed contracts — October 15, 2026

- Revision 0159 stores the last 50 successful contract opens per caller, with tenant and owner
  RLS and serialized updates/pruning. Failed reads and lists never record visits.
- Recently viewed uses that history, rechecks current contract scope and supports ordinary
  filters, counts and pagination. Reopening a contract moves it to the front.
- Verification is recorded in docs/release/CI-2026-10-15.md. No accounting events or contract
  versions are changed. No deployment; full release gates and independent sign-off remain open.

## Applied-modification contract filters — October 15, 2026

- Modified-in-period and Modified this period now read APPLIED modification effective dates
  within the contracting entity's fiscal calendar. The quick list follows as_of, falling back
  to entity-local today. EXISTS avoids duplicate contracts and filters before page/count logic.
- Verification is recorded in docs/release/CI-2026-10-15.md. Recently viewed remains open;
  this does not reconstruct historical modification status or change accounting calculations.
- No deployment; broader release verification and independent accounting sign-off remain open.

## Contract exception counts and filtering — October 15, 2026

- Replaced the hard-coded zero in contract headers/list rows with current related open-item
  counts. Has exceptions now supports both true and false before pagination and totals.
- Attribution includes explicit contracts, obligation owners, current group members and
  combination-suggestion payloads. Explicit contract attribution does not spread to the group;
  repeated occurrences count once. Tenant/entity RLS remains in force.
- Integration, scope and contract API regression evidence is recorded in
  docs/release/CI-2026-10-15.md. Modified-in-period and recent-view quick lists remain open.
- No deployment or accounting-policy change; full release gates and independent sign-off remain.

## Call-log proposal links and hash copying — October 15, 2026

- Proposal lists accept ai_model_log_id while preserving source authorization, counts and
  cursor binding. The call drawer shows authorized links, without rendering proposal content.
- Extraction links open contract review; number explanations open their bound trace with a
  freshly authorized retained narrative and same-trace citation links. Cached content stays
  hidden during reauthorization and on refusal or a source mismatch.
- Hash buttons copy complete retained hashes, hide absent response hashes and report clipboard
  refusal. Verification is recorded in docs/release/CI-2026-10-15.md.
- No deployment or live provider calls. Explain submission, other planned AI operations,
  standard demo/J-19, broader release gates and independent accounting sign-off remain open.

## Call-log CSV/XLSX download controls — October 15, 2026

- The call-log toolbar creates requester-bound exports, polls their jobs, reads completed runs
  and saves authorized output bytes. It explains that hidden grid columns are included.
- Export requires the matching source/export scopes; source-only users stay on the call-log
  screen. Duplicate submissions are disabled, failures are shown, and leaving the screen
  suppresses late downloads. The command helper exposes job polling errors to this flow.
- Frontend and real local Chromium/API/worker verification is recorded in
  docs/release/CI-2026-10-15.md. No deployment or live provider calls; overall release gates,
  remaining call-log navigation/copy controls and independent accounting sign-off remain open.

## Public call-export catalogue — October 15, 2026

- Migration 0158 registers ai_call_log_export for CSV/XLSX through the existing report API.
  Its closed, empty parameter schema refuses misleading entity/history/owner filters; the
  requester binding supplies scope, and reruns evaluate the current authorized population.
- Worker tests now use the actual migration seed instead of temporary registration. Catalogue
  metadata, specification inventories and default-role visibility expectations include the code.
- Definition removal must refuse while retained runs reference it. Migration/worker verification
  is recorded in docs/release/CI-2026-10-15.md. The call-log download menu remains pending.
- No deployment or live provider calls. Overall release gates and accounting sign-off remain open.

## Call-export API authorization and cached replies — October 15, 2026

- Source-only AI users/settings administrators can use this export with report.export; these
  grants do not admit accounting reports. Source MFA and requester binding guard reads.
- Per-subject commands can guard the actual cached reply after lookup. Export replay checks its
  retained scope and refreshes session/grants after that potentially waiting lookup. OWN stays
  OWN after promotion; a retained TENANT reply refuses demotion. No duplicate route guards.
- Public catalogue registration and the download UI remain pending. Verification details are in
  docs/release/CI-2026-10-15.md. No deployment/provider calls/sign-off; broader gates remain open.

## Queued call-export execution and revocation — October 15, 2026

- Internal run creation captures the requester binding; reruns preserve its maximum scope.
  REPORT_RUN reloads the human's current grants before start, completed replay, build and output
  storage. Dataset reads use that human context, not SYSTEM. API-client execution refuses.
- Call exports omit ledger-head metadata and declare live/open source capture. Real queued
  CSV/XLSX tests cover promotion, retained OWN scope, replay and permission loss before execution
  and during rendering. Public catalogue/API activation and the download UI remain unfinished.
- Report unit verification passes 941 checks; detailed worker, typing and lint evidence is in
  docs/release/CI-2026-10-15.md. No deployment/provider calls/sign-off; broader gates remain open.

## Retained export ownership across report and job reads — October 15, 2026

- Migration 0157 adds an immutable, validated requester binding to report_run. It refuses
  malformed/cross-owner bindings and downgrade while bindings survive. A partial tenant/job
  index supports job visibility checks.
- Shared report and job read predicates now require the original actor and current source/
  export grants for bound exports, including for audit readers. Existing unbound reports keep
  their rules. Submission, worker capture/build and UI integration remain unfinished.
- Verification evidence and the migration round trip are recorded in docs/release/CI-2026-10-15.md.
  No deployment, provider calls or accounting sign-off; production readiness remains unproven.

## Current requester grants for export workers — October 15, 2026

- Extracted persisted-job requester reconstruction for AI_TASK and REPORT_RUN: active human,
  current grants and live matching attempt required; no reconstructed login/MFA session.
  AI jobs still narrow entity access to ai.use before reading sources.
- Export capture/build guards now require report.export; TENANT requires its workspace-wide
  scope. Source visibility remains required. Thirteen focused tests, backend typing (797 files)
  and full lint pass; evidence: docs/release/CI-2026-10-15.md.
- These are prerequisites, not a completed queued export. Persisted bindings, worker integration,
  every output/replay read and the download menu remain open. No deployment/provider calls.

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
