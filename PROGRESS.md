# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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
