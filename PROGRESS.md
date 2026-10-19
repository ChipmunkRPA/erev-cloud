# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## Readable wide disclosure PDFs — October 19, 2026

- Replaced chapter-table ellipsis clipping with wrapped cells and horizontal column groups.
  Repeats row ordinals/identifying context and headers, keeps currencies beside amounts, and
  groups adjacent period/QTD measures where they fit. Ordinary rows stay together; long rows
  continue under the same ordinal. Very long labels get full-text legends, not clipped headers.
- Wrapped chapter stamps/notes and corrected contents offsets against final pagination.
  Added table header rules and compact currency headings. Omitted sections remain amount-free.
  Existing single-table PDF layout and canonical JSON accounting dataset hashes are unchanged.
- Six focused checks pass, including large negatives, mixed currency, long IDs, oversize
  narratives/labels, page/column geometry and legacy footer behavior; Ruff/Mypy pass. Rendered
  and inspected all five pages of a synthetic wide disclosure PDF with the PDF skill workflow.
- This verifies the layout sample, not accounting acceptance. The current standard-font
  WinAnsi limitation, broad browser/release checks and independent accounting sign-off remain.
  Four unregistered report families and the other system backlog still need development.
  No deployment; publish directly to main.

## Frozen disclosure execution and exports — October 19, 2026

- Added a verified E-65 reader: complete seven-kind population, single synchronous origin,
  immutable attachment/scope/cutoff, payload hashes, typed child data/stamps and reconstructed
  document equality. All original inputs, including supporting waterfalls, come from snapshots.
- Ordinary report creation and rerun now admit lock-backed disclosure packs, deriving the exact
  lock cutoff and checking explicit selectors. Period-only uses nine inputs, quarter uses sixteen.
  The normal worker renders JSON/XLSX/PDF with current requester permissions. Existing frozen
  inputs are reused; no source jobs, new snapshots, child file reads or live-policy fallback.
- Snapshot listing follows attachments for derived exports. Closed-period report views default
  to frozen disclosures and saved quarter inputs, without forwarding an unrelated global timestamp.
  Locks without complete E-65 evidence refuse rather than reconstructing past disclosures today.
- Real database/API/worker journey passes all formats, matching original quarterly JSON digest,
  same-source rerun, monthly selection and unchanged snapshot count. Python lint/type checks
  and focused frontend parameter/type/lint checks pass. PDF byte-format verification is not
  visual acceptance: wide tables, full browser/accounting validation and release checks remain.
- RPS-15 remains open; other missing reports and system work remain. No deployment or readiness
  claim; changes published directly on main.

## Atomic disclosure publication at lock — October 19, 2026

- ASC606/IFRS15 lock approval now captures sixteen period/QTD inputs and policies through the
  shared read-only SYSTEM reader, then publishes actual synchronous source reports, a seven-
  chapter JSON disclosure parent and seven immutable snapshots within the lock transaction.
  Source reports have null jobs, normal historical source bindings and actual output files;
  the parent/snapshots alone claim the period lock. CTL-029/030 and audit evidence are recorded.
- Validates lock/entity/calendar/book/cutoff, child plan/selectors, policy and dataset hashes,
  source bindings and row identities. Uses UoW savepoints so failed publication drops records,
  audit buffers and hooks. Repeated publication of an existing lock refuses. The seventh
  snapshot also retains supporting waterfall inputs for later frozen reconstruction.
- Existing twelve E-64 datasets keep their formats. Scope readers admit boolean quarter only
  for disclosure parents; the report viewer distinguishes saved lock evidence from drafts.
  The existing API serves the stored JSON chapters and seven scoped verified snapshots.
- Targeted database journeys cover draft/rerun, late-child failure rollback, genuine source
  identities, snapshot/parent HTTP reads, duplicate refusal and actual close approval capture.
  Production Python typing/lint and frontend component/type checks pass. Independent accounting
  acceptance, full browser/release checks and performance verification remain open.
- Next: admission/rebuild from saved lock snapshots, locked XLSX/PDF exports and rerun; no
  historical-lock backfill or current-data fallback. Other reporting/system backlog remains.
  No deployment, new PR or production-readiness claim.

## Disclosure snapshot viewer — October 19, 2026

- Disclosure report pages now expose a saved-snapshot panel: lazy paginated metadata,
  seven named kinds, explicit draft/locked classification, entity/book/period and individual
  verified detail reads. Expanded records show cutoff, reporting basis, snapshot ID and digest;
  verification failures offer retry without claiming successful validation.
- Retained suppressed source amounts are not rendered in this panel. Original disclosure
  tables continue to apply their elections. No new export permission or raw-data download.
- Three focused component checks cover lazy loading, failure/retry and retained-input hiding;
  TypeScript and targeted ESLint checked. Full browser acceptance remains open.
- This is a per-report viewer, not a cross-report snapshot register. Lock approval persistence
  and as-locked execution still remain open; no deployment or readiness claim.

## Read-only lock disclosure capture — October 19, 2026

- Added disclosure_freeze.capture over the existing SnapshotScope and one read-only SYSTEM
  reader. It executes the nine period/seven quarter source producers, normalizes parameters,
  fixes historical cutoff, preserves typed canonical datasets and their input bindings, and
  captures practical-expedient/nonpublic/interim policy facts at the same instant.
- Enforces entity-calendar membership, accounting book, aware/equal freeze cutoff, schema,
  unique row identities and bounded retained payload size. Does not enqueue jobs or invent
  report/job IDs. Policies expose a separate lock-only entry requiring SYSTEM plus a read-only
  transaction; ordinary SYSTEM calls still fail the existing report permission gate.
- Real database journey captures sixteen inputs under freeze.system_unit and compares every
  dataset against ordinary child jobs at the same cutoff; no report count change. Caller
  context and ordinary SYSTEM policy access refuse. Ruff/Mypy pass. Fixture has no booked
  accounting population, so independent accounting correctness is not implied.
- The collector is not yet invoked by lock approval: atomic persistence of genuine source report
  identities/seven locked snapshots and as-locked parent rendering remain to integrate. Existing
  draft snapshots stay drafts. No lock support, deployment or production-readiness claim.

## Disclosure snapshot read APIs — October 19, 2026

- Added API-R-42 disclosure snapshot list/detail with report.run authorization, entity/book/
  period/kind/source-report filters and keyset pagination. Metadata lists avoid loading dataset
  JSON; detail verifies digest, schema and snapshot/parent scope. Both return no-store responses.
- Reads require a successful disclosure parent, actual snapshot attachment, matching entity,
  book, period/calendar and lock identity, plus the parent's complete report permission scope.
  Missing/out-of-scope records return 404; unpublished or unattached rows stay out of counts/pages.
- Real API journey verifies seven draft records, filtering, count, disjoint pagination, detail
  digest and explicit draft classification. An empty report permission scope yields no rows and
  refuses detail. Ruff/Mypy pass; OpenAPI and generated frontend types updated.
- Lock-time capture/as-locked execution, snapshot register UI and full accounting acceptance remain
  open. Existing draft evidence is not relabelled as locked. No deployment.

## Immutable draft disclosure snapshots — October 19, 2026

- Added disclosure_snapshots.write_draft: locks the running parent and saves all seven E-65
  kinds with entity/book/period/cutoff, original per-section child inputs/stamps, policies and
  supporting source digests. Suppression affects published tables, not retained snapshot inputs.
- The normal worker attaches snapshot IDs in the same transaction as report output, source
  binding and SUCCEEDED. Repeated writes reuse a complete identical set; duplicate/partial,
  mismatched or unavailable attachments refuse. Drafts explicitly have no period_lock_id.
- Real API/16-child/parent/rebuild journey now verifies seven rows per parent, hashes and
  attachments, repeated-writer reuse, and new rerun IDs with identical per-kind data hashes.
  Ruff and production-module Mypy pass. Snapshot rows use the existing append-only table.
- Lock-time capture remains incomplete: current E-64 files cannot alone supply opening-liability
  revenue and policy facts. The lock job must capture these at its exact cutoff and atomically
  publish genuinely locked disclosures; drafts must never be promoted/relabeled as locked.
  Snapshot read APIs and as-locked parent integration also remain open. No deployment.

## Quarterly disclosure comparison summaries — October 19, 2026

- Added semantic period/QTD comparison for the six displayed flow reports. Row identities use
  section/contract/obligation/dimension/line codes and currency instead of source row positions or
  conditional currency suffixes. Different labels receive separate columns; missing population
  stays blank with presence flags. Duplicate identities or schema/election mismatch refuse.
- Disaggregation uses each source's existing range total, excluding its varying monthly buckets.
  No money is summed or rounded. Comparison summaries precede original source tables in JSON,
  workbook and PDF chapters; canonical parent hashes include comparison output. Summary digests
  identify their dataset and notes retain both original source run/hash references.
- The viewer labels combined-basis tables and their comparison digest separately from policies.
  Two populated alignment checks pass. The real 16-child/API/parent/rerun journey verifies six
  summaries, their hashes and workbook period/QTD headers; same-source rerun remains identical.
  Ruff/Mypy and frontend type/lint/component checks pass.
- Full populated accounting acceptance, PDF wide-table readability, browser acceptance, frozen
  snapshots and remaining export worker journeys remain open. No deployment or readiness claim.

## Disclosure chapter viewer — October 19, 2026

- Added seven-chapter disclosure view with expandable tables, period/QTD labels, interim flags,
  original source IDs/digests and omission notes. Only expanded, included tables load rows;
  amount columns identify shared currencies or carry companion currency columns when mixed.
- Report data now includes typed chapter/table metadata and optional section_table selection.
  Selected tables use normal pagination; cursor identity includes the table key. Unknown tables,
  duplicate selections and cross-table cursors refuse. Reads keep report permission/entity scope
  checks and verify the saved JSON digest before serving data. Ordinary directory reads remain.
- Real API journey verifies seven sections, ten expedient rows, pagination and wrong-table cursor
  refusal. Component check verifies lazy loading and omitted-table suppression. Ruff/Mypy,
  frontend TypeScript and targeted ESLint pass; OpenAPI/client types regenerated.
- Full browser/accessibility acceptance, frozen snapshots, quarter side-by-side layout, populated
  accounting acceptance and remaining export worker journeys remain open. No deployment.

## Draft disclosure public API admission — October 19, 2026

- Registered the composed disclosure worker separately from single-table BUILDERS. Creation
  and rerun use REGISTERED_REPORTS; its retained source contract is exposed through normal run
  metadata. There are 55 registered execution paths and four still-unregistered catalogue entries.
- Require one entity, ASC606/IFRS15 and explicit period. Initial attachment requires an open
  period at the source cutoff; missing/non-open/ambiguous state refuses. Explicit locked sources
  retain their existing no-frozen-dataset refusal. No live fallback for frozen requests.
- Converted the real 16-child/parent/rerun journey to HTTP creation and rerun, and verified run
  detail and JSON output download. Missing book/period and LEGACY requests return 422.
  The retained rerun still adds only one parent and reproduces hashes/totals with live capture
  forbidden. Source-contract/catalogue checks pass (23); Ruff/Mypy pass.
- User guide and release limitations describe the draft API and its boundaries. Frozen snapshots,
  chapter viewer, side-by-side quarter layout, export worker journeys and populated accounting
  acceptance remain open. This enables usable draft generation, not completed RPS-15/readiness.

## Retained disclosure rerun reconstruction — October 19, 2026

- Added version-2 disclosure input codec retaining original child stamps alongside typed JSON
  inputs, identities, parameter/output hashes and policies. Rebuild validates scope, cutoff,
  version, digests, stamp/dataset agreement and full population, then executes section/election
  assembly again. It does not replay the saved parent output or resolve current child/policy data.
- Internal rerun insertion attaches original child IDs without queuing new children. Readiness
  validates retained inputs independently of current child job/file availability. Worker output
  rendering consumes the reconstructed pack and preserves original input evidence.
- The real parent/16-child journey now publishes a second parent with live capture forbidden;
  hashes, totals, tie-outs, child IDs and evidence match. Scope/digest corruption refuses. The
  newly retained stamp fields require evidence version 2; earlier internal version-1 captures
  refuse rather than silently adding current stamps. Ruff/Mypy pass.
- Public catalogue/API admission remains closed; frozen snapshots, viewer, quarter-column layout,
  export worker journeys and populated accounting acceptance remain open. Five catalogue builders
  are still unregistered. This internal rerun journey is not full disclosure completion.

## Disclosure parent artifact publication — October 19, 2026

- Added disclosure_execution to turn verified children/policies into a canonical seven-section
  JSON document, a table directory and original retained inputs. XLSX/PDF use the same verified
  chapter model. The parent hash identifies the canonical dataset; ordinary atomic report output
  storage, success audit and CTL-029/030 recording publish the result and binding together.
- Worker reloads the initiating user's current report/export grants, then assembles under that
  context. Original source inputs/policies stay in the binding; omitted rows/totals stay out of
  public sections. Aggregate child tie-outs include supporting inputs but expose only code/result,
  not suppressed source amounts. Rendering rejects unsupported formats and retained reruns.
- Real database journey now delivers the waiting parent again after 16 children finish, verifies
  job/report SUCCEEDED, reads the stored seven-section JSON and reconciles file/output hashes,
  counts and retained-input digest/cutoff. Ruff and production-module Mypy pass.
- Public registration remains closed: retained rerun reconstruction, frozen snapshots, viewer,
  side-by-side quarter layout and populated accounting acceptance are still required. The journey
  has no booked accounting population and currently publishes JSON; worker XLSX/PDF journeys
  remain to verify. Five catalogue builders remain unregistered. No deployment.

## Disclosure dependency scheduling — October 19, 2026

- REPORT_RUN now uses a read-only readiness gate for disclosure parents. It checks the exact
  attached child population, scope/initiator, tenant/job/subject bindings and both job/report
  completion. Pending children defer delivery before taking an attempt; failed, cancelled,
  missing or inconsistent dependencies refuse instead of leaving the parent waiting indefinitely.
- Internal report insertion attaches disclosure children before transaction commit/dispatch.
  The public disclosure builder remains unregistered until rendering/publication and source
  binding are integrated; this change does not enable a partially implemented public report.
- Database journey covers a real parent delivery rescheduled at attempt 1 while remaining QUEUED,
  sixteen completed child jobs, readiness after completion and wrong-job/attachment refusal.
  Parent output persistence, retained reruns, frozen snapshots and viewer integration remain open.

## Disclosure chapter PDF adapter — October 19, 2026

- Added PDF chapter export with an index whose page destinations follow actual pagination,
  original child stamps, per-table headings, repeated continuation grid headers, wrapped notes
  and parent-run page numbering. Tables start on separate pages; omitted amounts cannot render.
- XLSX/PDF reuse the same disclosure source/policy validation and chapter omission checks.
  Five focused PDF/workbook/single-report checks pass; production modules pass Ruff and Mypy.
- This is an internal export adapter, not end-to-end disclosure delivery. Parent scheduling and
  publication, frozen snapshots, viewer and side-by-side period/QTD layout remain outstanding.
  All five unregistered reports remain explicitly unfinished: disclosure_pack, actual_vs_forecast,
  forecast_outputs, contract_sample_pack and period_evidence_pack. No deployment.
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
