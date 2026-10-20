# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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

## Reporting priority and saved forecast reader — October 19, 2026

- Reporting remains a feature-development priority. Catalogue registration counts do not
  establish report completeness or accounting acceptance.
- Added a format-specific saved forecast reader for the upcoming forecast_outputs catalogue
  entry. It reads retained JSON/CSV/XLSX datasets through scenario lineage and current export
  permissions, checks the parent and file identity, and decodes all five saved sections.
  It never recaptures the current scenario or substitutes a different format's disclosure.
- Eight focused forecast-export checks pass, including complete section decoding and rejection
  of changed/missing sections. The new database reader and public catalogue integration still
  need integration verification; forecast_outputs remains unregistered.
- Next development: wire forecast_outputs admission, immutable source binding, worker and
  report-centre access; then complete remaining report workflows and populated acceptance.
  No deployment or production-readiness claim.

## Public contract sample catalogue report — October 19, 2026

- Registered contract_sample_pack with ZIP/PDF/XLSX and the complete evidence permission set.
  Catalogue creation uses the existing source-pack dependency, worker and current-source read
  authorization; source-document permissions still apply to metadata, lists and downloads.
- Threaded optional known_at through sample creation into the existing historical collectors.
  Generation timestamps stay current. Same-source reruns preserve the bound original artifact.
- Real K01 API → source pack → report worker → download/rerun passes for all three formats.
  A later attachment appears in current capture but not in historical PDF/XLSX sources;
  missing SSP-document permission hides rows before count/cursor, and revoked grants refuse
  downloads. Sixteen source-contract checks and Ruff/Mypy pass.
- Catalogue audit: 58 registered report codes; forecast_outputs is the remaining unregistered
  code. This is registration coverage, not full accounting or release acceptance. Next:
  forecast_outputs entry-point integration; broader multi-contract/re-lock/report acceptance
  and independent accounting sign-off remain open. No deployment or readiness claim.

## Public period evidence catalogue report — October 19, 2026

- Registered period_evidence_pack through POST /report-runs. Lock selectors reconcile to the
  frozen entity/book/period and cutoff; declared evidence permissions govern admission/scope.
- Standard list/detail/output/rerun and idempotent replay paths check current source access.
  Lists filter before counts/cursors. Direct framework output reads also reauthorize sources;
  generic file routes remain restricted to their existing report-output route.
- Same-source reruns preserve the bound evidence pack and original archive, with explicit
  provenance. Failed-pack metadata can still be authorized; readiness/download reject failure.
- Actual public API creation, dependencies, worker output, list/detail/download, limited-user
  denial and original-source rerun pass. Existing report lifecycle/rerun regression passes;
  Ruff/Mypy pass. User guide updated.
- Next: contract_sample_pack public catalogue admission and full sample orchestration acceptance;
  fresh historical sample capture and wider accounting/re-lock acceptance remain open.
  No deployment or production-readiness claim.

## Catalogue evidence dependency/execution chain — October 19, 2026

- Ordinary report insertion now prepares and persists an explicit source pack binding in the
  initial INSERT, atomically with its jobs. Immutable report parameters/entity scope are not
  updated later. Retained preparation reuses the same pack; selectors and cutoff remain fixed.
- REPORT_RUN readiness waits for the exact EVIDENCE_PACK job and verifies its subject/hash.
  The worker rehydrates the current requester, verifies source access and stores the original
  artifact plus provenance through normal report completion/control recording.
- Real close acceptance exercises internal report creation, child reports/audit verification,
  source-pack completion and catalogue report worker completion; output bytes/hash match.
  Ruff and Mypy pass. Sample orchestration acceptance remains open.
- Public catalogue admission is still disabled: registration, lock resolution, source contracts
  and addressed/list/download authorization must be integrated before exposing RPT-54/55.
  Fresh sample capture currently requires the creation-time known_at; historical fresh capture
  remains unsupported (retained reruns preserve the original cutoff). No deployment.

## Catalogue evidence source/output adapter — October 19, 2026

- RPT-54/55 now have an internal adapter for an explicitly selected retained pack. It binds
  exact selectors, entity scope, source cutoff, source hash and pack/job identity; reauthorization
  refuses changed sources and requires current evidence permissions in every source entity.
- ZIP output preserves the complete original archive. Sample PDF/XLSX extraction preserves the
  retained chapter bytes and emits provenance linking the artifact to the pack manifest.
- Five focused archive/format checks pass; actual closed-period pack binding/read, altered-source
  refusal and revoked-export refusal pass. Ruff/Mypy pass.
- This is an internal adapter, not catalogue availability: ordinary report creation, persistent
  binding and dependency dispatch still need integration. The catalogue still refuses these codes.
- Reinspection confirms disclosure_pack already has child orchestration and a worker execution
  path. Its remaining acceptance gaps need auditing; do not describe orchestration as absent.
  No deployment or readiness claim.

## CHANGE/ACCESS evidence workflow — October 19, 2026

- Added atomic API creation, retained child-report readiness, current-requester worker
  authorization, encrypted final archives, scoped list/detail and verified ZIP/manifest downloads.
- Reporting now offers change/access generation forms, kind filters and retained detail pages.
  CHANGE uses inclusive dates; ACCESS requires tenant-wide evidence and access.approve grants.
- Real API → report workers → parent worker → list/detail/download passes for both kinds;
  retained repeat downloads keep original bytes. Targeted UI flows, types and lint pass.
- Still open: populated review campaigns through the complete parent flow, cancellation/revocation
  acceptance specific to these kinds, and wider RPS-16 accounting acceptance. Next reporting
  development: catalogue PACK builders and disclosure orchestration; remaining forecast work.
  No deployment or production-readiness claim.

## Encrypted ACCESS review retention — October 19, 2026

- ACCESS v4 now includes encrypted retained review evidence, with only IDs, cutoffs, hashes
  and file metadata in source_binding. Reports, role matrix and review files collect together.
- Reuses the existing immutable pack/file registry for tenant-wide archive/original-file holds;
  retain() belongs to pack creation's transaction. Reads verify complete dependencies,
  campaign associations, current permissions and archive/scope integrity without recollection.
- Actual populated API review capture verifies encryption, source deletion holds, hidden generic
  file routes, hash refusal and repeat reads with the live collector disabled. CHANGE/ACCESS
  report-worker collection also passes; Mypy and Ruff pass.
- Next: parent job/storage and public CHANGE/ACCESS API/UI. No deployment or readiness claim.

## As-of access-review evidence collection — October 19, 2026

- Added campaign/item evidence with original membership snapshots, counts and transition
  references. Historical output distinguishes pending decisions, requested revocation, confirmed
  revocation and later cancellation; future comments/reviewer identities do not leak backwards.
- Verifies source permission, snapshot hash/canonical bytes and complete member population.
  Uses tenant-wide access.approve, matching the source API, plus evidence permissions.
- Actual API create/start/decision/revoke/confirm/cancel collection passes. Seven focused
  timestamp/state checks, Mypy and Ruff pass. The audit slice is not full-chain verification.
- Collector returns personal payloads for encrypted storage; no personal source data is placed
  in source-binding JSON. Encrypted retention/dependency links and public CHANGE/ACCESS
  lifecycle/UI remain next. No deployment or production-readiness claim.

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
