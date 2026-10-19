# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

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

## Disclosure chapter workbook adapter — October 19, 2026

- Added render_xlsx_chapters with multiple independently typed/stamped tables per worksheet.
  Existing single-table exports reuse the same grid writer. Contents lists chapter/table status,
  source run/hash and worksheet; only the first table sets each chapter's frozen grid header.
- Added disclosure_workbook.render over the assembled seven chapters. Validates entity/book,
  policy hash and original child stamps/parameter hashes; re-encodes child data against its output
  hash and rejects changed displayed data. Omissions keep notes and no hidden source amounts.
- Database journey executes 16 child jobs, assembles the pack, generates a workbook and reopens
  it to verify Contents plus seven sheets and displayed source IDs/hashes. A mismatched displayed
  source stamp refuses. Three focused workbook/single-XLSX checks pass; Ruff and Mypy pass.
- Period and quarter-to-date are explicitly labelled separate tables at this stage. Required
  side-by-side presentation, PDF/viewer, frozen disclosures and parent worker publication remain
  open. The fixture has no booked accounting population; no full accounting acceptance claimed.
  Five catalogue builders remain unregistered; no deployment.

## Seven-section disclosure assembly — October 19, 2026

- Added disclosure_assembly.prepare/assemble: verifies complete attached child population and
  common tenant/entity/book/cutoff, captures entity policy facts at that exact cutoff, and groups
  verified child tables into all seven disclosure chapters with source run/hash references.
- Captures all nonpublic relief and interim policy values. Applies POL-192/193/196 at table level:
  balances remain while rollforward/other suppressed tables hide rows and totals. POL-195 hides
  the expedient table. Original child inputs remain available separately; interim-required chapter
  flags follow the resolved pack election. Disaggregation retains its existing timing-only handling.
- The database journey now assembles seven chapters after executing all 16 child tasks; fixture
  clock advances before parent creation so policy and child cutoffs match. It remains a no-booked-
  population journey, not full accounting acceptance. Two focused assembly/omission checks pass;
  Ruff and production-module Mypy pass.
- Still open: final side-by-side period/quarter presentation, chapter workbook/PDF and viewer
  integration, frozen disclosures and durable parent worker/dependency/publication lifecycle.
  Five catalogue builders remain unregistered. This assembly model is not a finished disclosure pack.

## Practical expedient disclosure inputs — October 19, 2026

- Added disclosure_expedients.capture for the ten PRACTICAL_EXPEDIENT registry parameters.
  Requires current scoped report permission and an entity existing at the aware cutoff; resolves
  published entity/book policy values and retains their source IDs/levels, labels and references.
- ASC606 and IFRS15 references follow the local POLICIES table; forced IFRS exclusions are
  preserved. No website links are emitted. A nonpublic-only franchisor election on a public entity
  refuses rather than implying eligibility. These are entity policies, not contract-use assertions.
- POL-195 suppression hides rendered rows while retaining the full facts and omission note.
  Registry category/reference drift refuses rather than silently dropping a newly added expedient.
- Real registry reads verify ten ASC606 rows, the applied cost expedient with 340-40-25-4 and
  IFRS forced royalty exclusion; the existing 16-child database journey passes. Focused omission
  check passes; Ruff and Mypy pass for the new module.
- Still required: bind these facts to the parent's exact cutoff and frozen disclosure snapshots,
  assemble all seven sections, parent worker scheduling/publication, PDF and viewer. Policy test
  cutoff uses DB observation time separately from the child-run fixture; full pack acceptance
  is not implied. Five catalogue builders remain unregistered.

## Verified disclosure child results — October 19, 2026

- Added disclosure_results.collect: authorize/resolve attached children, return pending IDs
  without partial sections, refuse failed children, then verify the complete finished population.
  Reads original child JSON files under readable-file locks with bounded aggregate input size.
- Validates purpose/media type/size/file digest and run output hash, canonical report envelope,
  parameter binding, row count, control totals and tie-outs. Restores date/timestamp cells to typed
  ReportData; rejects duplicate row keys and envelopes that do not round-trip canonically.
- Real database journey now executes all 16 child report jobs and collects their verified outputs,
  after first observing pending children. This fixture has no booked accounting population; it
  validates task/output integration, not populated disclosure accounting acceptance. Three focused
  plan/decoder checks pass; Ruff and new-module Mypy pass.
- Remaining: registered parent worker/dependency scheduling, seven-section assembly, frozen
  disclosures, practical expedients, PDF and viewer. Five catalogue builders remain unregistered;
  no disclosure_pack completion or production-readiness claim.

## Durable disclosure parent-child attachment — October 19, 2026

- Added disclosure_children.ensure: locks the parent run, checks the initiating actor's current
  run/export permission, creates and attaches the complete child population in one transaction.
  Existing attachments are reused without fresh calendar resolution or replacement child runs.
- Reuse checks child identities/order, code/version, creator, entity/book/cutoff, output format,
  historical currency basis and matching period/quarter intervals. Missing, duplicated or mismatched
  children refuse. Locked parents explicitly require the separate frozen-disclosure source path.
- Real database check passes for 16 children, repeated calls and reuse after commit in a fresh
  transaction, plus permission denial and corrupted attachment refusal without new rows. Ruff and
  new-module Mypy pass. Concurrent callers serialize on the parent row; no concurrent stress test
  or completed pack publication is claimed.
- This helper is not yet wired to a registered parent builder/worker. Parent dependency waiting,
  child output verification and assembly, frozen snapshots, expedients, PDF and viewer remain open.
  Five catalogue builders remain unregistered; this does not complete RPS-15.

## Disclosure child report planning — October 19, 2026

- Added disclosure_plan.requests for the eight core reports plus contract_cost_rollforward
  required by section 6. Month-only plans contain nine children; quarter-to-date adds seven flow
  reports, using the entity's fiscal quarter. Closing balances and RPO reuse the period-end stock.
- Child selectors explicitly bind one entity, book, historical known_at and transaction currency
  view. Disaggregation requests revenue category/timing; waterfall preserves recognized/scheduled
  states. Every request passes the existing report parameter schema checks.
- Added queue through framework.create_run with a savepoint around the full plan. Returned child
  records retain section/basis, run/job IDs and the normalized parameter hash. The caller owns
  parent attachment, durable plan reuse and retry idempotency; this helper never commits.
- Two focused plan checks pass. A real database case verifies 16 scoped child runs and rollback
  on a later invalid child; Ruff and new-module Mypy pass.
- Remaining disclosure work: parent scheduling/child persistence, result verification/assembly,
  frozen snapshots, practical expedients, PDF and viewer. Nine live child inputs cover section 6
  in addition to the spec's older eight-core-child acceptance; full pack acceptance remains open.
  Five catalogue builders remain unregistered; no deployment.

## Disclosure workbook output foundation — October 19, 2026

- Added WorkbookSection and render_xlsx_pack: a contents worksheet identifies each section's
  source run/hash/status, followed by separately typed worksheets with their original source stamps,
  totals and tie-outs. Indexed names remain unique after Excel's 31-character truncation.
- Sections omitted under an election require a note and cannot carry rendered rows, totals or
  tie-outs. Their undisplayed source data must remain in retained evidence, outside the workbook.
- Shared the existing cell/grid writer with single-report exports, preserving numeric money,
  formula guards and disabled automatic URL conversion. Apostrophes at worksheet-name edges are
  sanitized. A seven-section workbook round-trip and existing single-report checks pass (4 checks);
  Ruff and Mypy pass for the changed output code.
- This is the output component, not a registered disclosure_pack builder. Child-run orchestration,
  frozen disclosure snapshot binding, seven-section assembly, PDF and viewer remain unfinished.
  Five catalogue builders remain unregistered. No new PR or deployment.

## Parallel comparison worker and export integration — October 19, 2026

- Registered parallel_run_comparison and its retained-input source contract. Builder captures
  authorized sources, records exact cutoff/parameter selection and rebuilds from hash-verified
  retained facts. Changing entity, migration or period selection cannot reuse an unrelated binding.
- Worker reloads the original initiator's current report/export grants before building and output
  persistence. Source readers accept that verified principal with an explicit same-tenant check;
  no impersonation or implicit SYSTEM report grant is introduced.
- Real import -> CSV worker -> same-source rerun passes for identity and renamed entity mappings,
  with identical output hashes/control totals. Revoking permissions after queueing prevents file
  publication. These are empty comparisons because dry-run imports create no posted population.
- Targeted catalogue/source/parallel suites: 35 passed; changed production modules pass Mypy and
  Ruff. No schema change: the existing global definition already includes the output formats.
- Five catalogue builders remain unregistered: actual_vs_forecast, forecast_outputs,
  contract_sample_pack, period_evidence_pack and disclosure_pack. Populated RPT-42 worker/browser
  acceptance, XLSX/PDF journeys and migration replay/sandbox lifecycle remain unfinished.

## Parallel comparison period and currency selection — October 19, 2026

- Source admission now verifies original import input-evidence hashes, requires full contract
  population coverage and derives the single reporting currency from captured contract inputs.
  Today's tenant currency cannot silently relabel a legacy source. Capture refuses other currencies.
- Added period resolution from the first period starting after cutover through the latest open
  period at known_at, using recorded state transitions. Explicit ranges may include closed periods;
  reversed or pre-cutover ranges refuse. Missing open periods produce empty coverage, not zeros.
- Connected defaults/ranges to parallel_inputs.capture and retained the requested period boundaries.
  Calendar resolution uses current definitions at capture; the resulting selection is retained.
- Targeted unit checks: 12 passed; three changed modules pass Mypy and changed files pass Ruff.
  Real import capture/rebuild checks cover identity and renamed mappings; dry-run imports correctly
  have no compared actuals. Worker registration, publication grants and export integration remain
  next, along with complete replay/sandbox lifecycle. Six catalogue builders remain unregistered.

## Retained parallel comparison inputs — October 19, 2026

- Added parallel_inputs.capture to compose authorized migration admission, independent legacy
  projection and historical eRev reading into a detached JSON input bundle. Period/currency
  selection remains explicit; current support requires the complete mapped entity scope.
- Saved inputs include both full snapshots, original source evidence, tenant/migration/entity
  scope and cutoff. Rebuild checks the server-bound digest, version, scope and source linkage,
  then recomputes the comparison without consulting mutable source tables.
- Targeted comparison suite: 10 passed, including JSON round-trip, changed amount digest refusal
  and changed entity scope refusal. New module passes Mypy; changed files pass Ruff.
- Still open: report parameter resolution, worker registration, persistence/export integration,
  current permission checks on publication and full migration replay/sandbox acceptance. The
  capture composition is type-checked but still needs a real database integration journey.
  Six catalogue builders remain unregistered; RPT-42 is not yet a completed user-facing report.

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
