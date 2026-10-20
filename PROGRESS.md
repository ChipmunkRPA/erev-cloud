# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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

## Contract sample API and worker lifecycle — October 19, 2026

- Human requests can now create CONTRACT_SAMPLE packs through POST /evidence-packs, atomically
  retaining source dependencies, a stable render stamp and the EVIDENCE_PACK job. The worker
  rehydrates the active initiator's current grants instead of granting SYSTEM source access.
- Added atomic encrypted final retention, current-scope detail/manifest/ZIP reads and audited
  downloads. Successful retries reuse verified bytes; missing/damaged sources never trigger
  recollection. Existing failure/cancellation hooks settle sample packs too.
- Detail UI now handles sample contracts/cutoffs and scoped downloads; generated API schemas
  include the sample response. The register still lists CLOSE only; sample creation UI and
  sample-list pagination remain next feature work. Creation captures sources synchronously.
- Real K01 API/worker/download journey passes, including encrypted output, no re-render on
  retained reads, queued cancellation and permission-revoked terminal attempt/download refusal.
  17 evidence UI checks, 121 focused schema/file/storage checks, TypeScript, lint and Mypy pass.
- Fixed a stale transition-history function reference in period-pack journal collection; the
  existing real CTL-041 close-pack journey passes again.
- Broader multi-contract/combined-group acceptance and independent accounting sign-off remain.

## Contract sample PDF/XLSX assembly — October 19, 2026

- Added stamped nine-chapter PDF/XLSX workpapers from the authorized retained sample archive.
  Accounting grids show allocations, schedules, journal lines/contributions, events and documents;
  complete source-field tables preserve versions, trace nodes, approvals and linked audit evidence.
- Exact JSON values retain decimal precision, empty/null fields and long text in numbered parts.
  Unicode/control values use explicit escapes for the PDF standard font. Source file hashes and
  cutoff/basis notes accompany sections; binary originals remain byte-for-byte in the final ZIP.
- The populated K01 journey assembles both formats with live collectors disabled and verifies
  ZIP contents and unchanged originals. Precision/long-text check, Ruff/Mypy and PDF preview pass.
- Public sample create/worker/read/download and UI remain unfinished; rendering is an assembly
  component, not a claim that RPS-16 or the production-readiness goal is complete.

## Contract sample dependency retention — October 19, 2026

- Added immutable tenant FK links from sample packs to captured snapshots and original
  documents (0188). Pack creation retains dependency files in the same transaction under
  file locks; retained reads refuse missing/extra/scope-inconsistent links.
- Integrated deletion holds and internal-only file ownership, preserving current document
  authorization. Also registered the existing forecast actuals capture file as retained evidence.
- The populated K01 sample journey passes with persisted dependency holds and missing-link
  refusal; 11 file-registry checks plus Ruff/Mypy pass. No broad suite rerun or deployment.
- Reporting remains feature work: public sample create/job/download and rendered PDF/XLSX/UI,
  period pack/relock completion, and populated actual-versus-forecast acceptance remain open.

## Unified contract sample source snapshot — October 19, 2026

- Combined event/computation/journal/decision/document collectors at one cutoff; merged all
  dependency identities and permission scopes, including journal approval references. Captures
  a canonical scope alongside the source manifest in an encrypted SNAPSHOT_DATASET archive.
- Added typed immutable source binding/pack values and authorized retained reads. File metadata,
  bytes, manifest and embedded scope must agree; retries do not recollect business evidence.
- The real K01 journey persists a pack binding and encrypted snapshot, then reads it across UOWs
  with collectors disabled; digest tampering and revoked export scope are refused. Ruff/Mypy pass.
- Source-file deletion/retention registry integration must precede public release. Public create/
  worker/read/download, stamped PDF/XLSX and broader acceptance remain; no complete-pack claim.

## Contract sample journal evidence — October 19, 2026

- Added journal collection through the existing retained grouping/drill-back reader, including
  aggregated lines whose contract ID is absent. Separates whole-line amounts from sampled
  contributions and checks source counts, cutoff/currency/entity consistency and net amounts.
- Resolves posting entities beyond contracting scope and authorizes every source companion.
  Retains as-of run/batch state, labelled cancellations and journal approval references.
- The K01 journey now commits real journal calculation, traces populated draft lines and
  reconciles source amounts in the combined evidence archive. Ruff/Mypy pass. Multi-contract,
  cross-entity and historical journal lifecycle acceptance remain; public retention/jobs and
  PDF/XLSX rendering are still unfinished. No deployment.

## Contract sample retained documents — October 19, 2026

- Added attachment collection for sampled contracts/events, related modification/estimate/
  adjustment evidence and referenced approvals/attachable subjects, including SSP studies.
  Applies the original attachment cutoff plus current subject/file grants; missing, unreadable
  or inconsistent bytes fail explicitly. External document URLs are never fetched.
- Deduplicates payloads, uses ID-based archive paths, retains filename/media/hash metadata,
  checks decrypted size/SHA-256 and takes file locks against concurrent shredding. File-count
  and payload limits apply before collection. The real K01 archive journey verifies encrypted
  attachment collection, duplicate references and safe paths; Ruff/Mypy pass. Public lifecycle/
  rendering and journals remain.

## Contract sample approvals and audit slice — October 19, 2026

- Added cutoff-bound approval requests/decisions and deduplicated contract audit trails. Shared
  audit events authorize every linked contract; approval content requires its whole entity scope.
  Original decision hashes/MFA/delegation details are retained, credentials/contacts redacted.
- Computation evidence now supplies SSP/template and override approval references. The real K01
  journey verifies populated decisions/audit rows and combines them with events, allocation and
  schedule evidence into a hash-verified archive. Ruff/Mypy pass.
- This is a linked audit slice, not complete-chain verification. Journal/documents, source retention,
  public jobs/read/download, PDF/XLSX and broader historical/multi-entity acceptance remain open.

## Contract sample computation evidence — October 19, 2026

- Added immutable version history, allocation detail/trace and full schedule collection at
  the sample's effective date and knowledge cutoff. Combined-group companions are labelled
  and every contracting/performing entity is authorized; source scope is returned for retention.
- Validates trace digests/references and schedule counts/currencies/amounts. A real K01 command
  journey collects two obligations, future planned periods and an archive with event evidence;
  earlier-effective selection and revoked export permission checks pass. Ruff/Mypy pass.
- Public jobs, PDF/XLSX, documents, journal/approval/audit sections and combined-group acceptance
  remain. This collector is not a completed sample pack. No deployment.

## Contract sample event evidence — October 19, 2026

- Added the contract-sample event collector with exact contract/entity authorization, effective
  date and knowledge cutoffs, deterministic ordering, original-payload integrity checks and
  separate redacted-payload hashes. Superseded events remain in the evidence history.
- Produces per-contract event files, selected identity/date stamps and referenced source-record
  metadata. Shared raw import payloads are excluded; this is not document-byte collection.
- Targeted database collection/archive verification and two integrity/redaction checks pass.
  Computed versions/allocation/schedules, journals, decisions, audit slice, actual documents,
  stamped PDF/XLSX and public job/read/download integration remain. No complete-pack claim.

## Comparison report presentation — October 19, 2026

- Saved and rebuilt comparison controls now retain forecast ID, refresh time, book and currency
  basis. The viewer shows actuals cutoff, refresh time, variance definitions and a specific
  empty-actuals message; columns use the saved report's labels and order.
- Six focused calculation/rebuild checks, TypeScript and lint pass. Populated accounting
  acceptance remains open. Contract sample and period evidence packs remain development gaps.

## Actual-vs-forecast selection and report screen flow — October 19, 2026

- Added the SF-17 comparison form: saved forecast (including earlier refreshes), contract/category
  rows, periods within its horizon, permission-gated formats, task progress/cancellation and
  completed report links. Entity scope, book and currency basis follow the saved forecast.
  Completion refreshes the choice list; membership changes reset form state.
- Added paginated forecast-comparison-runs. It follows only successful scenario predecessors,
  checks current permissions, returns succeeded publications only and binds cursors to the
  current snapshot/workspace. Superseded/foreign lineage cursors are refused. OpenAPI regenerated.
- Five focused frontend checks, TypeScript/ESLint, Ruff/Mypy and the real scenario journey pass.
  The journey checks archived choices, pagination and invalid cursors, then runs JSON/XLSX/CSV/
  PDF report jobs and same-source rebuilding with no actuals. Populated accounting acceptance
  and rendered populated-report review are still outstanding. No deployment.

## Actual-vs-forecast standard report execution — October 19, 2026

- Registered actual_vs_forecast in the standard report framework (56 registered definitions,
  including disclosure; 55 ordinary builders). Workers reload current scenario/report access.
  Live builds use the requesting user for authorized source reads and restore worker context.
- Added retained-fact rebuilding with digest, tenant/run/entity/book/currency/selection and
  cutoff checks. It recomputes variances from original facts without live-source reads or saved
  output replay. Revision 0187 updates report IPE to the real retained snapshot/file sources.
- The real scenario journey creates a standard REPORT_RUN, executes it to SUCCEEDED JSON and
  rebuilds the same empty-actuals result with live reads forbidden. Migration and 17 focused
  source-contract/rebuild checks pass; Ruff/Mypy pass.
- Dedicated UI selection, all file-format verification and populated accounting acceptance
  remain. FCS-4 is now registered/runnable, but its acceptance is not complete. No deployment.
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
