# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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

## Disclosure snapshot register — October 19, 2026

- Added /reports/disclosures and a Reports tab for report.run readers. The register queries
  retained snapshot metadata using entity/book/period context and disclosure-type selection,
  pages older records, and links each record to its original report run.
- Reuses the lazy verified snapshot detail panel. Draft versus locked source remains explicit;
  metadata browsing does not fetch all payloads or imply lock-time capture is complete.
  Source-status filtering was added in the subsequent source-filter update.
- Four focused register/detail checks pass with TypeScript/ESLint. Actual-versus-forecast
  populated-posting acceptance remains unproven; review found existing computation/cutoff UI,
  so no speculative calculation rewrite was made. Disclosure lock-time orchestration was
  already implemented (see archived publication/frozen-execution entries); the earlier status
  here was stale. Populated accounting acceptance and independent sign-off remain open.

## Close variance snapshot selection — October 19, 2026

- Variance-between-closes parameters now choose Earlier close and Later close from authorized
  history for the selected entity, book and period. Options show the recorded timestamp,
  actor and approval number; only dataset-freezing LOCK records are offered, not REOPEN or
  PERMANENT_LOCK. Both selectors share the existing period-history cache.
- Explicit saved IDs remain intact outside the current context/list. Without a resolvable
  period or config.read scope, the manual parameter remains and no history read is made.
  Loading, empty and retry states are shown; the backend still validates source compatibility
  and chronological ordering before executing the comparison.
- Seven focused selector/toolbar checks pass with TypeScript/ESLint. Populated close-variance
  acceptance, remaining report workflows and independent accounting sign-off are still open.
  No deployment.

## Migration report record selector — October 19, 2026

- Migration report parameters now offer searchable authorized records by migration number,
  mode, status and cutover date, with cursor-based loading of older batches. Choosing a record
  writes its exact ID into the existing report parameter flow.
- A saved ID outside loaded pages is retained. Readers without migration.run do not request
  migration metadata and retain the manual parameter field; locked parameters remain disabled.
  List loading, errors/retry and empty workspaces have explicit states.
- Eight focused selector/toolbar checks pass, covering older-page selection, retained IDs and
  permission gating, plus TypeScript/ESLint. Other report selectors, populated accounting
  acceptance and independent sign-off remain open. No deployment.

## Retained migration comparison lines — October 19, 2026

- Reconciled migration details now display retained contract/obligation comparison lines,
  legacy and eRev values, difference, tolerance, within-tolerance result, deviation reference
  and exception identifier. Decimal strings are preserved without guessing a currency or
  rounding small differences. The grid is available under migration read permission.
- Added an outside-tolerance filter using the authoritative flag, not nonzero difference.
  The query is scoped by batch, record version and filter; empty results and read errors
  remain distinct. Report exports continue through the report-authorized viewer links.
- Fifteen focused migration screen checks pass, including exact decimal rendering and a
  nonzero-but-within-tolerance case; TypeScript and ESLint pass. Populated accounting
  acceptance, other report workflows and independent sign-off remain open. No deployment.

## Migration reconciliation workflow — October 19, 2026

- Replaced the empty migration Reconciliation step with a runnable workflow for opening-balance
  and replay batches: POST reconcile, persisted job recovery/polling, failure display and retry,
  and migration refresh at task completion. In-flight or successful reconciliation prevents a
  duplicate submission while the batch state refreshes.
- Imported/reconciled/submitted/promoted batches can navigate to this step. Report-authorized
  readers can open the retained reconciliation report or the report viewer with migration_id
  pinned, plus parallel comparison with the same batch selected. Period inputs remain editable
  in the report toolbar. Profile, promotion and other migration UI gaps remain separate work.
- Twenty-three focused migration checks, TypeScript and ESLint pass. Full populated accounting
  acceptance and independent sign-off remain outstanding; no deployment or readiness claim.

## Conditional reporting catalogue — October 19, 2026

- Removed the obsolete unconditional hiding of forecast outputs, actual-versus-forecast,
  migration reconciliation and parallel-run comparison. Forecast entries follow the existing
  sandbox/scenario-use access gate. Migration entries require migration.run and an authorized
  migration list with at least one record; unauthorized readers do not request that list.
- Forty-eight focused report-page checks pass, including workspace/access/empty-migration
  visibility, with TypeScript and ESLint. This completes catalogue access, not the remaining
  populated reporting workflows, accounting acceptance or independent sign-off. No deployment.

## Saved report identity and entity scope — October 19, 2026

- Forecast CSV/XLSX Open report view links now retain run=<id>, using the saved-format reader
  instead of implicitly creating a JSON report (which may not exist for that forecast).
- Multi-entity links retain p.entity_codes alongside the all-entities context marker. Previously
  reopening a file report could expand the selected subset to every entity in the reader's scope.
  The toolbar displays the saved subset and provides an explicit Use all permitted entities action.
  Selecting a single context entity takes precedence over the saved subset.
- Thirty-three focused run-record/parameter checks pass. Other reporting business workflows,
  populated accounting acceptance and independent sign-off remain open. No deployment.

## Report filters and saved-link preservation — October 19, 2026

- Added field/value filter rows to report toolbars whose schema declares filters. Users can
  add/remove conditions without entering JSON. Incomplete/duplicate fields remain editable
  and block live report submission instead of overwriting another condition.
- Report parameter conversion now produces the filters object; saved-report links retain
  string-valued objects. Previously opening a file report could omit its filters when creating
  the view run. Values containing punctuation survive the full saved-link round trip.
- Four focused toolbar checks and twenty-six run-record checks pass; TypeScript/ESLint pass.
  Backend authorization and supported-field validation remain authoritative. Richer record
  selectors, other reporting workflows and independent accounting acceptance remain open.
  No deployment or production-readiness claim.

## Declared report parameter controls — October 19, 2026

- Removed the fixed-toolbar-only limitation for ordinary scalar/list report parameters.
  Declared strings, dates, integers, booleans, enums and arrays now receive controls after
  the existing ordered fields. Entity/book/period/source controls remain in their context UI.
  Contract-sample IDs, forecast references and close-comparison lock IDs can be entered on
  the report page rather than requiring manually constructed p.* URL parameters.
- New fields use declared titles or readable labels, required flags, date inputs, enum/boolean
  choices and comma-separated list help. Lists trim separator whitespace. Invalid integers
  and booleans are preserved for API rejection rather than silently converted/truncated.
- Forty-five existing report-page checks and three focused parameter checks pass, plus
  TypeScript/ESLint. Object-valued advanced filters and richer record pickers remain separate
  UI work; broader reporting and accounting acceptance remain open. No deployment.

## Forecast run-record re-export — October 19, 2026

- Original succeeded forecast records now offer Re-export saved forecast instead of an
  unsupported new-computation rerun. The action creates a catalogue report with the original
  parameters/version/format, follows its REPORT_RUN job and opens the new record.
- Re-export navigation does not invent CTL-029 comparison results for an original catalogue
  creation. Bound catalogue reports retain the normal same-source rerun action; incomplete
  or unbound forecast records do not offer unsupported computation reruns.
- Forecast record and report-view stamps identify a saved forecast cutoff, and source text
  explains that exports reuse original figures. Twenty-six run-record checks pass, including
  the POST /report-runs action and navigation without a misleading equality banner.
- Broader reporting/business acceptance and independent accounting sign-off remain open.
  No deployment or production-readiness claim.

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
