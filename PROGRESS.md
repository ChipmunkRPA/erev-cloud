# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

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

## Durable scenario refresh reservation — October 19, 2026

- Revision 0184 adds production-scoped refresh records with immutable source/target tenants,
  selected input/hash, snapshot and job identities. Partial uniqueness admits one queued/running
  refresh per scenario; transition guards freeze terminal evidence and set-once result fields.
- Internal admission serializes on the source scenario, verifies the selected published inputs
  and the requester's queued copy job, and records the reservation. Start/failure transitions
  retain lifecycle audit. Archived or replaced source scenarios cannot start refresh execution.
- A running reservation now associates a held target with its original logical scenario for
  input replay; source pointer replacement is not needed to prepare the new inputs. Archiving
  refuses pending refreshes. Refresh records are operational, excluded from snapshot copying.
- The scenario journey verifies reservation, duplicate refusal, archive protection, repeat start,
  failure and immutable fields. Schema/transition/RLS round-trip and Ruff/Mypy checks pass.
- The request endpoint, worker integration, terminal cleanup and atomic source switch remain
  unfinished. Forecast outputs/actual-vs-forecast still remain open; no deployment/readiness claim.

## Held forecast copy and activation gate — October 19, 2026

- Snapshot loading can now retain SUSPENDED after successful copy/verification when its internal
  caller requests deferred activation for the scenario requester. The load summary records this
  explicitly; ordinary loads still activate immediately.
- Added an internal activation gate for the completion transaction: the expected held snapshot
  must have completed, period replay must permit point-in-time use, the registered scenario's
  expected input publication/hash must match, and the current requester must hold scenario.use.
  The gate updates status and audit without committing or changing the source scenario itself.
- The scenario journey verifies real deferred loading, refusal to open the suspended workspace,
  draft/hash refusals and successful activation. Ordinary scenario creation also passes;
  targeted checks and Ruff/Mypy pass.
- Persisted refresh orchestration, failure recovery and source scenario replacement remain
  unconnected; forecast reporting is still unfinished. No deployment/readiness claim.

## Atomic ordered forecast replay — October 19, 2026

- Connected file materialization, retained mapping consumption and command/file execution into
  one ordered replay operation for an empty target draft. It publishes only after every input
  computes successfully and records source/target publication hashes plus upload bindings.
- The caller owns the transaction; any failure or heartbeat cancellation rolls back the whole
  bundle, including earlier inputs and staged file metadata/audit. The input set cannot be
  replayed twice after publication. No child computation jobs can overtake the sequence.
- The real scenario fixture exercises command → mapped file → command, cancellation after
  the file with complete rollback, successful retry/publication and duplicate refusal.
  Targeted scenario verification, Ruff and source-module Mypy pass.
- Durable refresh job state, fresh-copy lifecycle and atomic scenario replacement still need
  integration. Forecast report outputs and actual-vs-forecast remain unfinished; no deployment.

## Retained forecast import mappings — October 19, 2026

- Revision 0183 retains a forecast replay import's verified original mapping as immutable JSON,
  separate from published target configuration. Internal replay validates its hash/template and
  persists it; ordinary import APIs cannot supply this snapshot and retain publication rules.
- Validation and header preview consume the retained aliases/constants. Published-input reading
  preserves the same mapping for subsequent refreshes, including when the source profile is
  absent or superseded in the new copy. Upload audit identifies its original profile and hash.
- The scenario journey imports an alias column without a target profile, computes successfully,
  then publishes and reads back the retained mapping; ordinary customer import also passes.
  Static checks and forecast schema upgrade/downgrade pass. Snapshot inventory clears this
  operational field with the source forecast binding.
- Durable refresh request/orchestration, scenario replacement and forecast report builders remain
  unfinished. No deployment or production-readiness claim.

## Forecast replay file materialization — October 19, 2026

- Added target file materialization from the authorized published-input bundle. It checks the
  exact file manifest, bounded bytes and retained hashes, and requires a draft of the same
  logical scenario plus tenant-wide scenario permission. Copying uses the normal authorized
  upload path with content checks, encryption, deduplication, uploader access and audit.
- Returns target file bindings and rewritten command evidence/import source references without
  mutating the source bundle. Mapping descriptors remain retained for separate resolution.
  The scenario journey checks deduplication, evidence rebinding/readback and corrupt/missing
  file refusal; targeted verification and Ruff/Mypy pass.
- Mapping-profile resolution, persisted refresh orchestration, final scenario switch and
  forecast report builders remain open. No deployment or production-readiness claim.

## Transactional forecast command replay — October 19, 2026

- Added the internal command executor alongside file replay. Commands authorize and lock the
  current contract in the target copy, apply retained payload/evidence through the normal event
  path and capture the input only after synchronous computation succeeds. Large groups do not
  enqueue deferred work that could overtake subsequent inputs. Ordinary HTTP behavior is unchanged.
- Computation failure rolls back the event, computation, input capture and audit buffers. The
  real scenario journey exercises failure after computation, subsequent successful replay and
  mixed file/command order without new jobs. Targeted checks and Ruff/Mypy pass.
- Resource materialization, durable refresh orchestration, scenario replacement and the forecast
  report builders remain unfinished. No deployment or production-readiness claim.

## Transactional forecast file replay — October 19, 2026

- Added an internal replay executor that creates, validates, previews, submits, commits and
  computes one forecast file in the caller's transaction. No asynchronous stage/compute jobs
  can overtake the next input. Retained quarantine behavior is explicit; normal import routes
  retain their asynchronous execution and approval rules.
- Failed stages roll back facts, captured input order and audit buffers. Existing template,
  draft-set, uploader and contract permissions remain enforced. The scenario journey covers
  successful replay without queued jobs and invalid-input rollback; ordinary import coverage
  is retained. Targeted checks and Ruff/Mypy pass.
- This is an internal building block, not a finished refresh endpoint. Resource copying,
  command replay, durable refresh orchestration and atomic scenario replacement remain open.
  Forecast outputs, actual-vs-forecast and both evidence packs remain reporting priorities.

## Published forecast replay inputs — October 19, 2026

- Added the source reader for refresh: verified publication hash, complete input order and
  published version ancestry; inherited file inputs must belong to that chain and be committed.
  The reader checks the current requester's scenario and underlying event/import permissions.
- Retains original file/evidence bytes with size/hash verification and a combined size limit;
  keeps the committed template version, parameters, quarantine setting and verified mapping
  definition. Only captured contract-event POST commands are admitted, never arbitrary URLs.
  Publication and reading share the same canonical content definition.
- The mixed-input scenario journey verifies inherited source-file materialization, ordered event
  bodies, publication/file corruption rejection and permission refusal; Ruff/Mypy pass.
  Refresh orchestration, applying
  these inputs in a new copy and switching the scenario are still unfinished. Forecast outputs,
  actual-vs-forecast and evidence packs also remain open. No deployment/readiness claim.

## Forecast input application order — October 19, 2026

- Revision 0182 records one sequence across API commands and successful file commits. Both
  capture paths append the sequence under the input-set lock, in the same transaction as facts.
  Publication validates complete, unique coverage and per-source order, then hashes the sequence.
  New versions preserve the sequence alongside their copied command/file inputs.
- Historical populated sets without sequence evidence remain readable but cannot be extended
  or replayed by guessing an order. Empty historical sets can initialize a verified empty order.
- Mixed API/file/API capture, published order and version copying pass the real scenario journey;
  five malformed/legacy order checks and the schema upgrade/downgrade check pass. Python lint,
  type checking and OpenAPI generation pass.
- This supplies a required input for deterministic refresh/replay; the refresh orchestration,
  forecast computation, forecast reports and evidence-pack reports remain unfinished.
  No deployment or production-readiness claim.

## Forecast file input pipeline — October 19, 2026

- Revision 0181 adds an immutable tenant-scoped import-to-input-set binding, exposed in import
  reads. Scenario drafts accept progress, usage, cost and invoice fact files through existing
  validation/diff/commit stages. Other import workflows retain their normal approval path.
- Ready forecast files submit under BR-FC-02 without an approval request. The worker rechecks
  the uploader's current scenario grant/token scope and underlying template write scope, locks
  diff contract bases before applying, and atomically appends successful upload IDs to the set.
- Input-set publication refuses pending files; invalid/failed files add no inputs. Captures and
  publication share a lock. CTL-044 records the scenario approval exemption as not applicable.
- Real scenario/API/worker journey passes file commit, no approval request, pending-publication
  refusal and over-delivery rejection. Two ordinary import regression checks and the forecast
  schema upgrade/downgrade check pass; Ruff/Mypy and OpenAPI generation pass.
- Updated API/client types, snapshot handling, data model and user guide. Scenario refresh and
  ordered replay still need implementation, followed by forecast execution and both forecast
  reports. Evidence-pack reports also remain open. No deployment or production-readiness claim.

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
