# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

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

## Forecast manual event capture — October 19, 2026

- Added explicit `forecast_event_set_id` on the contract event append API. Registered scenario
  drafts apply facts under BR-FC-02 and retain ordered method/path/body inputs atomically.
  Requires tenant-wide scenario.use plus the ordinary contract event permission and validation.
- Publication and command capture share the input-set lock; published versions reject new
  events. A capture failure rolls back facts, computations and buffered audit work. Existing
  ordinary event approval behavior remains the default when no input set is selected.
- Real snapshot-to-scenario/API journey passes manual progress capture, same-key retry,
  failed-capture rollback and published-set rejection. Two production approval/evidence checks
  also pass. Ruff/Mypy and OpenAPI generation pass.
- Updated API schema/client types and user guide. Import association, ordered refresh/replay,
  forecast jobs, forecast outputs and actual-vs-forecast remain unimplemented; FCS-2 stays open.
  Contract sample and period evidence packs also remain outstanding. No deployment.

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
