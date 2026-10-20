# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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

## Report export recovery — October 19, 2026

- Export menus now guard duplicate submissions during the request, the accepted-but-not-yet-
  loaded job interval and job execution. Running jobs keep format choices visibly unavailable.
- Network failures and malformed accepted responses now show a recovery message. Cancellation
  has its own message. A completed export whose report record cannot be loaded offers a retry
  against the same report; it never queues another report or announces successful preparation.
- Three focused interaction checks cover duplicate requests, same-report recovery and network
  errors; TypeScript and ESLint pass. Other reporting workflows and independent accounting
  acceptance remain open. No deployment or production-readiness claim.

## Saved report column metadata — October 19, 2026

- Ordinary report grids now use saved column order where no dedicated layout applies, and
  use the saved title for fields without an existing translated title. RPO, waterfall and
  close/parallel comparison layouts retain their specialized section rules.
- Added saved date/timestamp/boolean types, decimal quantity versus integer formatting,
  actor display names and readable code lists. Nullable money fields keep their declared
  money type when their populated values are money objects. Legacy exports retain literal
  field naming and values; frozen textual data is not reinterpreted as a money object.
- Fifty-one focused report-page, grid and specialized-layout checks pass; TypeScript and
  ESLint pass. Reporting content and populated accounting acceptance remain open.
  No deployment or production-readiness claim.

## Forecast comparison entry points — October 19, 2026

- The comparison form now defaults to the latest authorized succeeded forecast and its full
  saved horizon, matching RPT-40's specified initial selection. Explicit selection, parameter
  edits, submission and paging retain the selected record instead of following list refreshes.
- Each succeeded forecast history entry offers an inline comparison form preselected to that
  exact record, including a record absent from the current choices page. It preserves the
  saved entity/currency scope and only offers the entry with report access for every entity.
- Eight focused forecast/comparison interaction checks pass. Broader reporting content,
  populated accounting acceptance and independent accounting sign-off remain open.
  No deployment or production-readiness claim.

## Actual-versus-forecast percentage display — October 19, 2026

- Completed RPT-40's signed variance percentage presentation. API values are already scaled
  percentages; the formatter shifts decimal strings exactly before percentage rendering,
  avoiding double scaling and numeric precision loss. Positive values show a plus sign;
  negatives follow tenant style and zero-base null values retain the no-value dash.
- Report columns now classify the comparison percentage as a right-aligned numeric value.
  Currency totals preserve the backend's saved variance percentage and render it as a
  percentage instead of treating it as currency or omitting it.
- Twenty-two focused format/report-grid/totals checks pass, along with TypeScript and ESLint.
  Populated production-posting accounting acceptance and other reporting workflows remain
  open; no full reporting or production-readiness claim. No deployment.

## Forecast file-format viewing — October 19, 2026

- Fixed the report-centre mismatch where CSV/XLSX forecast detail requested section data but
  the data route accepted only JSON. Forecast file formats now read their own saved canonical
  datasets, with parent/publication/digest verification and current export authorization.
  Other report formats retain their existing data-route rules.
- The forecast history page offers inline figures for completed CSV/XLSX outputs when the
  viewer holds export permission for the report's entities. Original forecast publications
  and ordinary catalogue reports both use the saved format's visibility, without recapture.
- Real forecast workflow passes with original-publication reads and public catalogue section
  metadata/paged revenue rows for JSON/CSV/XLSX. Four focused UI checks and backend lint/type
  checks pass. Broader reporting features and accounting acceptance remain open.
- Next: continue the RPS/FCS reporting workflow/content gap audit; registration coverage is
  not a completion claim. No deployment.

## Public forecast catalogue reports — October 19, 2026

- Registered forecast_outputs for JSON/CSV/XLSX through ordinary POST /report-runs and
  REPORT_RUN execution. Creation pins the completed publication before INSERT; execution
  reauthorizes the requester and renders all five saved sections without recapturing sources.
- Read/detail/list/download and cached-command access use current scenario/source grants.
  JSON data reads also authorize the bound publication. CSV remains a five-section ZIP;
  output_sha256 follows the forecast convention of hashing the canonical five-section dataset.
- Same-source catalogue reruns preserve the publication and dataset hash. Original forecast
  computation reruns remain explicitly unsupported; the UI/API must not imply recomputation.
- Real API creation, worker execution, download and rerun pass for all three formats; removal
  of scenario.use refuses retained-source access. Twenty-four focused source/export checks
  and Ruff/Mypy pass. User guide describes saved scope, format retention and hash semantics.
- Catalogue audit: all 59 definitions now have registered execution paths. This is not full
  report content, populated business workflow or independent accounting acceptance. Next:
  audit reporting feature/content gaps and complete the outstanding workflows, including
  multi-contract samples, reopen/relock, forecast comparisons and report-centre usability.
  No deployment or production-readiness claim.

## Bound forecast catalogue exports — October 19, 2026

- Added pre-insert forecast publication binding and per-use authorization. Bindings pin the
  forecast workspace, parent, published report, dataset file/hash and format; entity/book/
  currency scope must match. Historical cutoffs cannot silently select another publication.
- Refactored the existing JSON/CSV/XLSX renderer to render verified saved sections directly.
  Catalogue re-export uses the saved five-section dataset and current report stamp without
  reading today's scenario or recalculating forecast results.
- The real forecast-event capture scenario passes with binding and re-export of all three
  formats, identical retained dataset bytes/hash and rejection of changed format. Eight
  focused export checks and Ruff/Mypy also pass.
- Remaining: public catalogue admission, REPORT_RUN worker and read/list access integration.
  This is an internal completed path, not a publicly registered forecast_outputs report yet.
  Broader reporting workflows and accounting acceptance remain open. No deployment.

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
