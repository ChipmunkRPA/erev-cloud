# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**



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

## Actual dimensions and comparison assembly — October 19, 2026

- Actuals capture now freezes immutable contract external IDs and category availability. A
  single obligation/product history and a product unchanged since the cutoff establish the
  category; changed/ambiguous/missing history stays explicitly unknown rather than becoming
  Unassigned. Contract mapping still works when only category history is unavailable.
- Added actual-line projection using saved transaction/functional credit minus debit. Connected
  both authorized retained-source readers to the comparison projector, with refresh-race checks
  and pre-aggregation fact/digest evidence for the forthcoming report-framework adapter.
- Seven focused dimension checks pass. The real scenario journey verifies populated obligation
  label lookup, historical absence and archived forecast plus empty actuals comparison. Ruff/
  Mypy pass. Populated production-posting accounting acceptance is still outstanding.
- Report-framework registration, same-source rebuilding and UI remain open; the internal
  comparison path is implemented but the public report is not yet runnable. No deployment.

## Saved forecast dimension mapping — October 19, 2026

- Forecast revenue exports now retain the original revenue category. The archived reader
  validates the saved scope-evidence hash and resolves entity IDs from the retained entity
  configuration, not current names or inferred ordering.
- Added the forecast-side comparison mapper: expands obligation rows over the saved horizon,
  preserves period money signs/currencies, excludes totals and refuses duplicate/incomplete
  rows. Legacy data without category still supports contract mapping but refuses category use.
  Nullable categories remain separate from a literal category named Unassigned.
- Ten focused mapper/comparison checks and the real archived-forecast refresh journey pass;
  Ruff/Mypy pass. Actual-side dimension mapping, report builder/registration and UI still
  remain. FCS-4 is not yet runnable; no deployment.

## Authorized retained-actuals reading — October 19, 2026

- The scenario history result now identifies the exact current actuals snapshot. Added an
  internal actuals reader that reauthorizes the current scenario and historical forecast,
  verifies the snapshot target/status/cutoff and encrypted file digest, and checks retained
  book/entity/cutoff metadata before returning only forecast-scope rows.
- Other books, entities and periods never leave the reader. Duplicated, cancelled, late or
  out-of-capture rows are refused. Missing legacy capture is explicit; no live-source fallback.
  Production SQL context is restored on exit, including errors and revoked permissions.
- Six focused scope/integrity checks pass. The real refreshed-scenario journey reads its
  retained empty actuals and denies access after permission removal. Ruff/Mypy pass.
- Remaining FCS-4 work: contract/category dimension mapping, comparison report builder and
  registration, screen connection and populated accounting acceptance. No deployment.

## Durable actuals capture in creation and refresh — October 19, 2026

- Revision 0186 adds immutable, tenant-scoped forecast_actuals_capture records, unique per
  source snapshot and linked to encrypted SNAPSHOT_DATASET files. Both ASC606/IFRS15 retain
  their own cutoff, entity scope and acknowledged revenue lines. Downgrade refuses evidence loss.
- Scenario creation and refresh workers retain actuals before snapshot completion/replay under
  the requester's current production permissions. Snapshot-row locking serializes retries;
  existing captures are reused. Completed legacy snapshots cannot acquire a later baseline.
  Journals still are not copied into sandboxes; failed-refresh capture evidence is preserved.
- The real creation/refresh journey passes migration, both-book file digest/content checks and
  immutable-update refusal. Ruff/Mypy pass. Source actuals require report.run for every captured
  source entity; no scope is silently omitted.
- Still open: authorized retained-actuals reader, contract/category mapping, comparison report
  builder/registration and UI. No deployment or overall production-readiness claim.

## Snapshot-cutoff production actuals reader — October 19, 2026

- Confirmed SBX-03 snapshots deliberately omit journals. Added a separate production-only
  actuals reader using the journal extract's cutoff-bound lifecycle evidence and current entity
  permissions. It retains acknowledged revenue batches only, preserving transaction/functional
  debits and credits and journal/contract/obligation identities for the comparison mapper.
- Later acknowledgements/cancellations are evaluated at the snapshot cutoff; cancelled lines,
  duplicate lines, out-of-scope books/entities and post-cutoff lines are excluded or refused.
  Scenario journals cannot be passed off as production actuals.
- Six focused checks and the real scenario journey pass, including empty production actuals
  despite scenario computations and refusal of a sandbox source. Ruff/Mypy pass.
- Still required: durable capture retention in creation/refresh, category/contract mapping,
  comparison builder/registration and UI. FCS-4 is not yet runnable. No deployment.

## Retained forecast data and archived revenue reading — October 19, 2026

- Forecast publication now retains encrypted canonical JSON for XLSX/CSV runs as well; JSON
  reuses its existing output file. The dataset reference is saved with the source binding in
  the same publication transaction, so later comparison does not recalculate the original forecast.
- Added an internal reader through the authorized scenario history resolver. It checks the
  saved output hash, scenario/input/parent identities, book/currency/entity/horizon scope and
  revenue-table hash, returning only revenue. Legacy JSON remains readable; old file-only
  outputs without retained data are explicitly refused. Tenant context is restored on exit.
- The real scenario journey passes all three retained formats and archived revenue reading
  after refresh. Ruff/Mypy pass. Production actuals, comparison builder/registration and UI
  remain open; no generic archived-download access or production-readiness claim is added.

## Forecast lookup across scenario refreshes — October 19, 2026

- Added an internal saved-forecast resolver from the active scenario through successful refresh
  predecessors. Failed/disconnected copies are excluded; ambiguous or cyclic lineage is refused.
  Saved runs must be succeeded and belong to a published input set of the same logical scenario.
- Current requester entity permissions are checked again. Tenant SQL context is restored on
  both successful reads and refusals. The result separates production snapshot cutoff from
  refresh completion time, for the eventual posted-actual reader and report header.
- The real scenario/refresh journey passes archived-run resolution, missing-run refusal,
  permission removal and context restoration; three lineage checks and Ruff/Mypy pass.
- Actual-vs-forecast remains unfinished: posted-actual capture, archived output retrieval,
  retained-source report builder, catalogue registration and UI still need connection.

## Actual-vs-forecast comparison projection — October 19, 2026

- Implemented contract/category revenue comparisons, saved-horizon validation, entity scope,
  signed variance and percentage, zero-forecast null percentage and separate currency totals.
  No-actuals output differs from zero-net production postings; no currency conversion is inferred.
- Four focused checks cover population union, credit signs, currencies, zero bases, no actuals,
  category aggregation, period/entity selection and invalid numeric inputs. Ruff/Mypy pass.
- FCS-4 remains unavailable until production actuals are captured at refresh before scenario
  replay, old forecast records can be resolved across refreshes, and the retained builder and
  UI are connected. Current scenario recomputation must not be mistaken for posted actuals.

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
