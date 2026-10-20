# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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

## Release provenance and access-role evidence — October 19, 2026

- CHANGE source v2 now captures requesting-process release registry facts and all registrations
  in the requested range, preserving recorded gates and explicitly distinguishing registered
  facts from original build-manifest bytes and independent approval.
- ACCESS source v3 now captures the complete role/permission matrix, including inactive roles,
  at its selected instant. Missing historical definitions refuse. Capture/read require
  tenant-wide evidence grants; a list of current entity IDs is not treated as that grant.
- Both emit fixed JSON evidence alongside retained report CSV/IPE outputs. Retries do not
  replace snapshots with current release/role values. v1 sources remain readable.
- Actual CHANGE/ACCESS report-worker collection and 17 focused checks pass; Mypy/Ruff pass.
- Still open: access-review evidence, parent job/storage, public CHANGE/ACCESS API/UI,
  populated re-lock acceptance and the wider reporting backlog. No deployment.

## Change/access report-source implementation — October 19, 2026

- Added immutable CHANGE/ACCESS report-source preparation and retained collection. CHANGE
  captures configuration/SSP logs; ACCESS captures user-access/SoD reports, including removed
  members. All use explicit dates, known-at and captured entity scopes through the report framework.
- Original CSV, IPE manifest and source identities are verified and collected without requeueing.
  Current source/export permissions are checked on every retained read; newer entities are not
  silently added. Future dates and empty scopes refuse.
- Two actual PostgreSQL report-worker journeys and five date/scope checks pass; access output
  includes real memberships. Revoked export is refused; Mypy and Ruff pass.
- This is the retained report section, not completed CHANGE/ACCESS packs. Release evidence,
  role matrix/access reviews, parent retention/API/UI remain next development work. No deployment.

## Re-lock variance report integration — October 19, 2026

- Close-pack creation now queues the existing variance-between-closes builder for re-locks.
  New v3 bindings retain the previous/current locks, report run and request cutoff; ordinary
  supporting reports retain the freeze cutoff. v1/v2 first-close bindings remain unchanged.
- Readiness waits for the variance job and audit verification; assembly includes the retained
  CSV, IPE manifest, source identity, original stored comparison and frozen measure changes.
  Frontend now permits re-lock selection and describes the additional evidence.
- Actual queue/worker/retained-output acceptance over seeded empty locks passes, as does the
  real first-close command journey. Focused binding/assembly checks and 34 UI checks pass.
- Still open: populated re-open/re-lock end-to-end acceptance, cross-contract driver evidence,
  catalogue PACK builders, change/access packs and independent accounting sign-off. No deployment.

## Contract sample history register — October 19, 2026

- Added sample history to the API and evidence page, with contract IDs, effective/known cutoffs,
  status, file count, manifest hash and links back to retained details/downloads.
- Counts and cursor pages include only packs whose full source/document scope is currently
  authorized. SQL prefilters entity scope; streamed composite checks avoid locking documents.
  Source-only internal bindings are excluded. CLOSE remains the default view.
- 14 focused PostgreSQL checks (including real K01 lifecycle/list), 34 evidence register/generation UI checks,
  TypeScript, Mypy and lint pass. No deployment.
- Reporting remains unfinished: broader sample accounting acceptance, period-pack completion,
  relock variance, change/access packs and forecast/report orchestration remain tracked.

## Contract sample creation form — October 19, 2026

- Added the sample-generation action to the evidence page. Users paste 1–50 exact external
  contract IDs (one per line), select an explicit effective cutoff, and submit through the shared
  idempotent command pipeline. Duplicate/blank-only IDs, excess counts and future dates are refused.
- All evidence permissions are required to offer the action; configuration permission is not.
  Server source-scope checks remain authoritative. Field refusals use the shared form mapping.
- Accepted requests open the sample detail page. If the response lacks its pack header, the
  form follows the job and recovers the result link without permitting duplicate submission.
- 22 focused generation/register UI checks, TypeScript and ESLint pass. The evidence register
  still lists CLOSE packs only; authorized sample-list pagination and discovery remain next.

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
