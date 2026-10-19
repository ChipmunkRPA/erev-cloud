# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

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

## Forecast run creation and history screen — October 19, 2026

- Added `/reports/forecasts` with published-input selection, scoped entities, consecutive
  calendar horizon, transaction/functional currency and JSON/XLSX/CSV output choices.
- Connected idempotent submission, job progress/cancellation, paginated run history, saved
  report links and JSON table previews. Errors and missing permissions are visible; production
  workspaces cannot create forecasts. Three focused UI checks cover submission and access.
- Scenario creation/refresh and input editing UI remain open, along with forecast revenue
  chart, actual-vs-forecast, contract sample pack and period evidence pack. No deployment.

## Forecast-run API and worker — October 19, 2026

- Added POST/GET/list forecast-runs in scenario workspaces, with idempotent admission,
  published-input hash verification, scoped report/export permissions and consecutive horizon
  validation. Requested formats default to JSON; callers may select XLSX/CSV too.
- Registered FORECAST_RUN: reloads the active requester, validates the queued input/state hash,
  recomputes activated scenario groups and publishes all selected five-section reports with
  the parent success transition in one transaction. It does not reapply already-applied inputs.
  Cancellation checkpoints roll back partial work; the final job-row check serializes cancellation
  with publication. Queued cancellation/failure settles the parent and completed publication
  cannot be cancelled. Revision 0185 admits forecast_run as the durable job subject.
- Real API/worker verification covers idempotency, three reports, production refusal, listing,
  completed-cancel refusal, queued cancellation and computation failure without partial reports.
  OpenAPI/client schemas and the user guide now describe the runnable API.
- FCS-3 remains open: K-11 specified accounting acceptance, broader concurrency/crash coverage,
  creation screens, revenue chart, general report-catalogue execution and same-source reruns
  are still unfinished. Actual-vs-forecast and evidence packs remain priorities. No deployment.

## Atomic forecast report publication — October 19, 2026

- Added an internal publisher for a running forecast: verifies its published input identity/hash,
  current scenario and requested entity/book/horizon scope, then stores an ordinary report run,
  encrypted output and CTL-029/CTL-030/audit evidence in the caller's transaction. Reports are
  attached to the parent forecast. Duplicate formats are refused under the parent row lock.
- JSON, XLSX and CSV publication preserve the captured currency view, output visibility basis,
  cutoff, engine release, actual scenario name and tenant negative-number style. CSV also saves
  its manifest for the normal manifest download route. Independent child source evidence is
  retained internally; computation reruns remain explicitly open rather than claiming a rebuild.
- The real scenario journey verifies rollback after file storage, successful publication,
  duplicate refusal, three-format persistence, saved JSON API reading and CSV/manifest downloads.
  Targeted source/export checks and Ruff/Mypy pass. Public admission/computation orchestration
  is still missing; this is an internal transaction primitive, not a completed forecast workflow.
  Revenue chart, actual-vs-forecast, evidence packs and accounting acceptance remain open.

## Forecast report data API and viewer — October 19, 2026

- Aligned forecast JSON with the existing report-data chapter/table envelope, including a
  five-row section index, typed table datasets and per-table hashes. Added typed forecast
  header metadata to GET report-runs/{id}/data; existing chapter pagination can serve each
  forecast table independently and rejects cursors reused across the index and a table.
- Added the forecast viewer branch with saved scenario/publication, horizon and cutoff,
  expandable tables, currency-aware columns and retry/empty states. Reused the disclosure
  table renderer without its policy/snapshot controls. CSV download filenames now use .zip
  for forecast outputs, matching the archive format.
- Four targeted backend checks, forecast/disclosure component checks, Ruff/Mypy, ESLint,
  TypeScript and OpenAPI generation pass. No deployment or full-suite run.
- Run admission/computation, durable report publication and end-to-end creation remain open;
  the report is still unregistered. The viewer requires a saved forecast report and does not
  yet make one available through the UI. Revenue chart, actual-vs-forecast and both evidence
  packs remain unfinished. Production readiness and independent accounting acceptance remain open.

## Forecast output download rendering — October 19, 2026

- Added internal RPT-39 JSON, XLSX and CSV rendering from the captured five-section dataset.
  XLSX uses the established workbook renderer with a contents page, five typed tables and
  run metadata. CSV is a deterministic ZIP of five separate schemas plus a manifest with
  each file's hash, byte count, controls and run stamp. JSON preserves section boundaries.
- Exports carry scenario, input publication/version/hash, horizon and source cutoff. The
  dataset hash accompanies XLSX/CSV output. Raw source evidence is not exposed. Scope,
  missing sections, unsupported PDF and output-format visibility changes are refused;
  format changes require a new capture so RPO election visibility is preserved.
- Targeted renderer checks cover metadata, signed numeric money, safe literal contract text,
  CSV file hashes and refusals. Real scenario capture-to-JSON and Ruff/Mypy also pass.
  Durable report publication/download routes, forecast execution,
  charts/UI, actual-vs-forecast and both evidence packs remain unfinished. No deployment.

## Forecast output source capture and five-section assembly — October 19, 2026

- Connected the internal RPT-39 assembly to the existing revenue waterfall, net billing,
  period-end balance, RPO and sealed-subledger readers. All reads share an exact cutoff,
  book and authorized entity scope. Each child keeps independent source evidence; multiple
  balance-period reads cannot overwrite one another. Same-source reruns remain open.
- Billing uses each entity's own calendar boundaries; balance stocks are grouped by actual
  end date. Horizons must be consecutive in every selected calendar. Functional billing uses
  the governed spot-rate adapter; unsupported report-currency conversion is refused.
- The five tables omit report tie-outs; projected RPO includes section 1 only and preserves
  underlying election controls. Journal preview creates no posting or journal batch.
- Real computed scenario capture passes within the existing replay/refresh journey; four
  focused projection checks and Ruff/Mypy pass. No full-suite run or deployment.
- Still unfinished: forecast-run API/worker, durable report publication and exports, chart/UI,
  actual-vs-forecast, contract sample pack and period evidence pack. This internal assembly
  is not yet a registered report and does not establish production readiness.

## Forecast output section projections — October 19, 2026

- Added RPT-39 table projections for billing by contract/horizon period, projected balances
  by entity/currency/period end, and journal preview by period/account role/currency.
- Billing consumes effective net document contributions (void/credit handling stays in the
  existing billing reader), preserves signed credits and excludes dates outside the horizon.
  Balance stocks remain separate by end date and skip input TOTAL rows to avoid double counting.
  Journal preview retains gross debit/credit activity, including reversals, from signed sealed
  ledger inputs; it does not create journal batches. Every total is currency-specific.
- Three focused checks cover credit amounts, USD/JPY precision, multiple period-end stocks,
  reversals and stored functional-currency amounts. Ruff/Mypy pass.
- These are data projections, not a registered/completed forecast report. Five-section assembly,
  source capture, forecast-run execution, retained report exports and UI remain open. Journal
  reporting-currency valuation still needs its governed source adapter; no parity conversion is
  assumed. Forecast and actual-vs-forecast remain unfinished. No deployment/readiness claim.

## Scenario refresh API, worker and atomic switch — October 19, 2026

- Added POST /scenarios/{id}/refresh with source row precondition, published input selection,
  idempotency and atomic snapshot-job/reservation creation. OpenAPI/client types regenerated.
- Reserved snapshot jobs now reauthorize the requester, read the selected publication, export
  current production, load a held copy and replay the ordered inputs. Completed held copies can
  be reused; an already-completed refresh returns its retained result. Partial copy failures
  settle the refresh and archive the incomplete target while keeping the old scenario usable.
- Publication, target activation, old-copy archive, source pointer/base/last-refreshed update,
  refresh result and three-workspace audit commit together. Retired old-copy worker writes are
  refused even after their source pointer moves. Cancellation settles queued reservations and
  cannot undo an already-completed switch.
- Real API/worker checks cover failed completion with old-copy preservation, a subsequent
  successful refresh, mixed mapped-file/event replay, idempotent HTTP retry, old-write refusal
  and queued cancellation. Ordinary scenario creation also passes; Ruff/Mypy/OpenAPI pass.
- Refresh UI, broader concurrency/crash recovery and specified accounting acceptance remain
  open. Forecast output and actual-vs-forecast report builders remain unfinished. No deployment.

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
