# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





## Deal preview report presentation — October 19, 2026

- Detail reads now expose typed allocation rows, SSP bounds/range position, selected SSP,
  weights and adjustments, per-book transaction/allocation totals, material-right and variable
  consideration indicators, and revenue grouped by entity/period/subject. Only REVENUE
  schedules contribute; billing and costs are excluded. Currency precision comes from retained
  input evidence and all displayed money remains decimal strings.
- Scheduled and awaiting-trigger totals explain previews whose revenue schedule is empty.
  Projection uses hash-verified saved evidence, without resolving current configuration again.
  OpenAPI and frontend types are regenerated.
- Reporting remains a development priority. This completes only the result data layer; SF-18
  screen, scenario save, actual-versus-forecast populated K11 and multi-contract K03/close
  variance remain open. Tamsin acceptance and independent sign-off are also outstanding.
  No deployment; direct main workflow.

## Asynchronous deal preview API and worker — October 19, 2026

- Added POST /deal-previews with idempotent command admission and a reserved preview identity;
  registered DEAL_PREVIEW worker execution. It reloads the active human initiator and current
  grants, uses fenced units of work, checks cancellation and retains the computed evidence.
  Already-retained previews refuse later cancellation; job results carry identity/hash/link only.
- Added scoped GET list and detail. Entity authorization filters before pagination/counting;
  lists return proposal metadata without engine traces, details verify input/result hashes
  and return retained result/pins without exposing the internal input bundle. Both use no-store.
- Migration 0189 adds deal_preview to the job subject constraint. Downgrade refuses while such
  jobs remain. Removed the pending-handler entry and retained registry negative-case checks.
- Real API/worker/database journey passes duplicate-request identity, successful USD 120000.00
  allocation, one retained preview, zero production contracts, summary/detail reads and entity
  scope filtering. Five registry checks, Python lint/types and OpenAPI generation pass.
- Scenario save, user-facing allocation/range/indicator projection and SF-18 UI still need
  implementation. Tamsin accounting acceptance, broader release verification and independent
  sign-off remain open. No deployment.

## Immutable deal preview retention — October 19, 2026

- Added retain service under a tenant/preview advisory lock. Every attempt rechecks scenario
  permission and entity currency. A matching existing record returns only after proposal and
  input/result fingerprints verify; reuse of an identity with changed input is refused.
- First execution resolves the scratch bundle and its reference index, uses the DRY_RUN engine,
  and stores the proposal plus complete engine bundle, full canonical result, both hashes,
  registered release ID and standard pinned_refs. Exactly one deal_preview.run audit is added.
  No commit occurs inside the service; the future worker owns attempt fencing and commit.
- Real database verification passes saved SSP references, exact request retention, repeated
  result identity, one audit and changed-proposal refusal alongside scratch rollback checks.
  Python lint/types pass. No production contract/customer survives the enclosing commit.
- Asynchronous request/worker wiring, authorized read APIs, user-facing result projection,
  scenario save and SF-18 UI remain unimplemented. No deployment or accounting-signoff claim.

## Deal preview authorized bundle assembly — October 19, 2026

- Added deal_bundle booking conversion and assembly: resolve the active contracting entity,
  enforce its scenario.use scope and functional currency, then use existing booking and
  bundle resolution for products, approved SSP, templates, policies and accounting books.
- Internal booking runs in a savepoint under system authority only after authorization. Both
  success and errors roll back temporary contract/group/customer/obligation rows and buffered
  audits; no computation persistence, file write or job enqueue is invoked inside the boundary.
- Proposed lines get stable keys and term end dates. Synthetic booking evidence uses the
  proposal's customer reference and sequence, removing rolled-back surrogate/sequence IDs
  that initially caused repeated-input fingerprints to differ. Calendar overflow is refused.
- Real database verification covers ASC606 allocation of USD 120000.00, repeatable input hashes,
  permission refusal, injected resolution failure and unchanged row/audit counts after commit.
  Python lint/types pass. Sequence allocation may leave harmless gaps after scratch rollback.
- Job/API retention, result presentation, scenario save and SF-18 UI remain unfinished, as do
  Tamsin acceptance and independent accounting sign-off. No deployment.

## Deal preview input and engine boundary — October 19, 2026

- Code inspection confirmed deal preview had only its persisted table, without an API,
  worker, engine adapter or screen. Added proposed-deal/create/save request schemas: exactly
  one customer identity/name, bounded nonempty lines, positive decimal-string quantities,
  nonnegative API money, one currency, strict positive terms and calendar-date input.
- Added pure deal_compute boundary using the complete revenue engine in DRY_RUN mode. It
  rejects multiple contracts or posted ledger baselines, preserves engine refusals, returns
  the full engine result/trace and verifies input/result fingerprints. No database writes.
- Four targeted schema/refusal checks pass. A separate real ASC606 kit-world computation
  confirms two USD 1000.00 allocations, DRY_RUN isolation and both fingerprints; lint/types pass.
- This is the compute foundation, not a working deal-preview feature. Authorized product/SSP
  resolution and bundle construction, retained audited jobs/API, result presentation, scenario
  save and SF-18 UI remain to implement. Tamsin acceptance and accounting sign-off remain open.
  No deployment or production-readiness claim.

## Direct forecast event capture from contract forms — October 19, 2026

- Existing delivery/progress/milestone/cost/return drawers now offer a paginated draft selector
  in sandbox workspaces with tenant-wide scenario.use. Normal approval remains the default;
  selecting a draft explicitly changes the action and explains scenario recording/replay.
- Submission carries forecast_event_set_id to the existing atomic capture endpoint, retains
  contract stream concurrency and evidence validation, then invalidates assumption reads.
  An unavailable selected draft blocks submission; the target is locked while submitting.
  Draft management links to contracts with instructions to select that draft in the event form.
- Ten existing/extended event-drawer checks pass, including the selected target in the request,
  retained-input refresh and forecast-specific success message; frontend types/lint pass.
- Usage/invoice input continues through forecast imports. Effective-date controls on input-set
  metadata, populated comparison/report accounting acceptance, deal preview and independent
  sign-off remain open. No deployment or production-readiness claim.

## Captured forecast input review — October 19, 2026

- Assumption versions now expand a read-only review of captured contract event bodies and
  committed import sources in their retained interleaved application order. Event dates,
  obligations, payloads, comments and evidence IDs remain visible as captured; decimal strings
  are not coerced, rounded or truncated, and text is never interpreted as HTML.
- Contract/import links respect available read permission and use local routes. The page states
  that linked current records may differ from captured version evidence. Empty baselines and
  populated legacy sets without valid sequence evidence are explicitly distinguished.
- Six focused review/lifecycle checks pass, covering interleaving, exact numeric strings,
  literal markup, source links, missing order and baseline handling; frontend types/lint pass.
- Direct event-entry capture UI, effective-date controls, populated report accounting acceptance
  and independent sign-off remain open. Import sources use the existing authorized row viewer.
  No deployment or production-readiness claim.

## Forecast fact import entry and correction continuity — October 19, 2026

- Draft assumption records now link to the import wizard for import.upload readers, carrying
  the selected input-set ID. The upload page reads that set, displays code/name/version/status,
  blocks unavailable or non-draft targets before file upload and lists only backend-supported
  progress_events, usage, cost_events and invoices templates.
- Import creation retains the same forecast_event_set_id. Corrected-file navigation now keeps
  that association alongside template/mode; previously it silently fell back to ordinary import.
  Validation/commit and backend draft/permission checks continue to govern attachment.
- Seven focused import/assumption checks cover the link, displayed target, template restriction,
  publication guard, submitted ID and corrected-file identity. Frontend types/lint pass.
- This supplies forecast fact import authoring through the existing pipeline. Direct business
  command capture, richer input review and accounting acceptance remain open. No deployment.

## Forecast assumption lifecycle controls — October 19, 2026

- Forecast runs now include a lazy-loaded, paginated assumption manager within the existing
  scenario-workspace permission gate. Users can create a draft, rename a saved draft and
  explicitly confirm publication; published and superseded versions remain read-only.
- Shows captured-command/import counts, version/status and publication fingerprints. Empty
  sets explicitly identify baseline publication. Reusing a code invokes the existing backend
  next-version/copy semantics; an existing draft is handled by the server's refusal.
- Updates carry the saved row version. Publication refreshes the shared forecast input cache,
  making the new published version selectable for report runs. Lost responses preserve fields
  and permit idempotent retry; no optimistic publication state is shown.
- Eight targeted manager/forecast checks pass, with TypeScript and ESLint. Business-change
  capture controls, import attachment selection, effective-date editing and richer input review
  remain open; this implements lifecycle management, not the entire assumption authoring flow.
  Reporting accounting acceptance and independent sign-off remain open. No deployment.

## Scenario refresh reporting workflow — October 19, 2026

- Production scenario cards now select searchable, paginated published assumptions and request
  refresh with the displayed row version. The page explains replacement, guards pending
  submissions and displays durable QUEUED/RUNNING/SUCCEEDED/FAILED outcomes plus job details.
  Reopening the panel recovers an existing refresh; terminal outcomes reload scenario bindings
  and choices. A successful copy job alone is not used as proof of the complete refresh.
- Added source-owned GET /scenarios/{id}/refreshes with cursor paging/counts and no-store;
  returns outcome metadata only, excluding raw failures and replay/internal workspace payloads.
- Real forecast journey passes queued, failed and successful outcomes and sandbox denial.
  Eight focused scenario UI checks pass after correcting a test's tooltip/text ambiguity;
  frontend types/lint and backend types/lint pass. No deployment.
- Reporting remains unfinished: assumption editing/publishing UI, deal preview, populated
  actual-versus-forecast and close-variance accounting acceptance remain outstanding. Catalogue
  coverage is not completion of all reporting workflows or independent accounting sign-off.

## Authorized scenario refresh choices — October 19, 2026

- Added GET /scenarios/{id}/published-inputs for production USER callers with tenant-wide
  scenario.use. Resolves an active source-owned scenario, checks its current active sandbox
  belongs to that production tenant, then lists only that scenario's published input versions.
  Tenant context is restored even on refusal; no arbitrary target workspace parameter exists.
- Returns only ID/code/name/version/hash/publication metadata, not captured API commands or
  uploaded payloads. Supports keyset paging/counts and no-store responses. OpenAPI and generated
  frontend types are updated. This supplies the missing refresh selector read contract.
- Real scenario/database journey passes current published choices, draft exclusion, paging,
  counts, hidden command payloads and sandbox-call denial; existing forecast capture/refresh
  checks also pass. Python lint/types pass. Disposable database stopped after verification.
- Refresh UI still needs input selection and refresh-stage tracking; event editing and wider
  accounting acceptance remain open. No deployment or independent-signoff claim.

## Scenario archive and status filtering — October 19, 2026

- Active scenario records now offer an explicit archive confirmation describing read-only
  retained evidence. The POST carries the displayed row version; success refreshes the
  scenario cache. Backend creator/Controller authorization and idle-job checks remain
  authoritative. Refusals, version conflicts and lost responses remain visible without
  claiming success. Archived scenarios keep their workspace-read entry.
- Added URL-backed ACTIVE/ARCHIVED status filtering through the server's list filter before
  pagination. Creation still invalidates every scenario-list variant.
- Six focused creation/list/archive checks pass plus frontend type/lint checks. Refresh needs
  a published-input selector from the source scenario, and event-editing UI remains open.
  Populated accounting acceptance and independent sign-off remain outstanding. No deployment.

## Scenario creation and forecast entry — October 19, 2026

- Added /reports/scenarios for production workspace members with tenant-wide scenario.use:
  named creation with purpose, async copy progress and refusal/network feedback, paginated
  active/archived scenarios, source cutoff and refresh timestamp. Creation uses the current
  production cutoff; accepted jobs prevent repeated submission while job metadata loads.
- Existing scenarios open through the established workspace-session switch, clearing the
  previous tenant's cache and then navigating to forecasts. The shared helper retains its
  original home destination for sandbox settings. Forecasts now link to scene management
  when a scenario workspace is required; a Reports tab exposes the new page.
- Eighteen scenario/sandbox checks and eight scenario/forecast checks pass (three overlap),
  plus frontend TypeScript/ESLint. Refresh/event editing, archive UI, populated forecast
  accounting acceptance and independent sign-off remain open. No deployment.

## Complete report catalogue coverage — October 19, 2026

- Compared frontend catalogue groups with current backend DEFINITIONS and found four missing
  entries: disclosure_pack, engine_trueup_register, upgrade_validation and ai_call_log_export.
  Added the first three to their business groups and normal report viewers. AI call log export
  opens its existing dedicated settings page and is visible only to settings admins/AI users.
- All 59 backend definitions now occur exactly once in catalogue groups. Conditional forecast,
  migration and AI permissions still apply; registration/visibility is not accounting acceptance.
- Forty-eight report-page checks pass, covering the added links and AI access, with frontend
  type/lint checks. Other functional gaps, populated accounting acceptance and independent
  sign-off remain open. No deployment.

## Single-table PDF clipping fix — October 19, 2026

- Ordinary report PDFs now retain the compact layout only when every cell/header and source
  stamp fits. Otherwise they reuse the chapter renderer's wrapped rows, repeated identifiers,
  horizontal column groups and full source text. Large amounts and long identifiers are no
  longer silently replaced by ellipses. Existing chapter behavior is reused unchanged.
- Six focused output checks pass, including extracted large negative values/currencies,
  continued-page headers and footer page counts; Python typing/lint pass. Rendered a four-page
  wide sample and visually checked the first two groups: values, currencies and identifiers
  remain legible with no overlap. Wide reports may now use more pages.
- This fixes clipping, not the existing WinAnsi font character-set limitation. Full populated
  accounting acceptance and independent sign-off remain open. No deployment.

## Disclosure source filtering and status correction — October 19, 2026

- Added API source=DRAFT|LOCKED filtering from immutable period_lock_id before pagination and
  counts, plus a source selector on the snapshot register. Updated generated OpenAPI/client
  types. The source state is computed from the record, never caller-supplied classification.
- Revalidated the real disclosure child/parent journey: draft list/count filtering, atomic
  locked snapshots, opposite-source empty results, frozen JSON/XLSX/PDF rebuild and retained
  reruns all pass in the existing database scenario with added source-filter assertions.
- Corrected stale status carried forward in recent notes/LIMITS: lock-time capture and frozen
  disclosure execution were already implemented in 54bb6fa / 41c8278. They are not remaining
  development work. Full populated accounting acceptance and independent sign-off remain open.
- Two focused register tests, Python typing/lint, frontend TypeScript/ESLint and the real
  disclosure journey pass. No deployment; the disposable verification database was stopped.

## Outstanding release verification

These checks need current release-candidate evidence. Historical October 3 results
remain in the dated build history; they do not verify current main. This list does
not authorize deployment, provisioning or changes to a live database.

- make audit-deps passed on clean 74bd148 (October 15): all 86 pinned Python runtime packages and npm runtime dependencies report zero advisories. Rerun on the final candidate.
- make docker-build passed on clean b4b8210 (October 15); rerun on the final candidate.
- make compose-verify passed on clean 74bd148 (October 15), including cleanup. Rerun on the final candidate.
- make zap-baseline passed on clean 4c4b583 (October 15), including cleanup; one documented low COEP warning and three informational alerts remain. Unauthenticated surface only; rerun on the final candidate.
- SUPERVISOR VERIFICATION NEEDED: make tf-validate (October 14 backend-disabled development validation passed; rerun on a clean final candidate).
- make restore-drill passed on frozen d7e8715 (October 15), exercising backup and restore-verify
  on a fresh disposable server. Rerun on the final candidate; hosted recovery is outside this scope.

## Historical release record

The earlier build-loop notebook is preserved in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).
Current outstanding implementation and verification gaps remain in
[the release limitations](docs/release/LIMITS-1.0.md).
