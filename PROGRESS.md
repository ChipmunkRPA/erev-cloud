# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Retained replay difference details — October 15, 2026

- Candidate comparisons now carry full difference rows and check them against their summary.
  Persistence stores an encrypted, identity-bound difference artifact in the same transaction
  as the result and accepted pointer, including an explicit empty comparison for MATCH.
- Rollback, retry reuse, encryption, evidence holds and generic download denial passed database
  checks. Unit/typing evidence is in the dated CI record. Historical results are not backfilled.
- Attempt datasets, reports, final acceptance, approvals and admission remain unfinished.

## Encrypted validation artifact storage — October 15, 2026

- Added VALIDATION_DATASET purpose/migration, per-file encryption and internal-only owner
  rules for attempt datasets and verification difference datasets. Generic file routes deny
  reads; existing non-overridable evidence holds protect referenced artifacts.
- Database encryption/read/hold and empty migration round-trip tests passed, with file-access,
  policy and registry checks. CI evidence is in the dated release record.
- Dataset production, report publication, final acceptance, approvals and admission remain open.

## Persisted validation assessment — October 15, 2026

- Added assessment of frozen selections, accepted evidence and actual child-job completion
  under validation/attempt locks. Changed populations or incomplete selections are refused.
- Accepted evidence while its job still runs remains pending; cancellation and exhausted
  retries make the assessment INCOMPLETE. The assessment makes no enablement transition.
- Database lifecycle verification and typing/lint evidence are in the dated CI record.
  Dataset/report publication, final acceptance, approvals and admission remain outstanding.

## Validation aggregate refusal checks — October 15, 2026

- Reproduced and fixed ERROR evidence counting toward a pass in the pure aggregator. It now
  makes an otherwise terminal attempt INCOMPLETE, including alongside MAJOR differences.
- PATCH validations are refused before population evaluation. All 22 aggregation/state-machine
  tests and typing passed; dated CI evidence records the checks. Persisted job aggregation,
  artifact publication, approval resolution and admission remain unfinished.

## Frozen validation job fan-out — October 15, 2026

- Added transactional job binding for each frozen selection, with population/release checks
  and reuse of existing jobs on retry. Lost dispatch recovery and concurrent callbacks create
  one queue entry; rollback leaves no partial bindings. No sample is redrawn.
- Seven fan-out database cases and 17 scheduler regressions passed, alongside unit/architecture,
  typing and lint checks. Evidence: docs/release/CI-2026-10-15.md.
- Aggregation, artifacts, approval resolution and final admission remain open.

## Replay worker lifecycle — October 15, 2026

- Registered REPLAY_VERIFY with frozen group binding, audited RUNNING/RETRYABLE transitions,
  three-attempt retry policy, required exhaustion cleanup and cancellation hooks.
- Cancellation fences acceptance; its guard uses a nonblocking job-unit lock to avoid waiting
  on a worker commit, and refuses cancellation after acceptance. Registry checks also corrected
  the stale AI_SETTINGS_VERSION phase inventory. CI evidence is in the dated release record.
- Fan-out, aggregation/artifact publication, approval resolution and admission remain open.

## Frozen replay execution service — October 15, 2026

- Connected source loading, pure replay and atomic result persistence. The engine runs outside
  database units; committed results are reused before evidence access or re-execution.
- NO_SOURCE records absence without execution. ERROR evidence stays unaccepted for scheduler
  retry handling; changed heads are refused at persistence. Verification is in the CI record.
- Scheduler adapter/state transitions, fan-out, approval resolution and admission remain open.

## Frozen replay evidence reader — October 15, 2026

- Added a worker evidence reader bound to the persisted execution, running attempt and frozen
  source. It checks tenant/task/release/scope before file access and never rebuilds missing input.
- File metadata disagreement reaches the verifier as an integrity mismatch. Storage failures
  propagate; acceptance still rechecks the head and attempt under locks.
- Handler/fan-out, approval resolution and admission remain unfinished. Verification evidence
  is recorded in docs/release/CI-2026-10-15.md.

## Replay identity checks before comparison — October 15, 2026

- Reproduced six wrong source/executed identities that candidate normalisation previously
  reported MATCH. Both replay paths now bind versions, trace versions and input hashes before
  comparison; input codec/source disagreement also fails as an integrity incident.
- Legitimate cross-version comparison remains supported. Test evidence is in
  docs/release/CI-2026-10-15.md. Replay handler/fan-out and release admission remain unfinished.

## Unapproved validation attempt supersession — October 15, 2026

- Added audited, idempotent supersession under the same parent/attempt locks as result writers.
  Replacement selection can share its transaction; historical selections and evidence remain.
- Linked approvals and non-retryable parent states fail closed. The release approval subject,
  stale-approval invalidation, fan-out, replay handler and final admission remain outstanding.
- Verification evidence is recorded in docs/release/CI-2026-10-15.md.

## Validation start and full-population fence — October 15, 2026

- Frozen attempts now retain a versioned full-population fingerprint, including unsampled
  heads and current member stream versions. Start refuses population drift or legacy attempts
  lacking that fingerprint, and atomically marks parent/attempt RUNNING with an audit event.
- A matching running retry is read-only; final acceptance still needs a fresh population check.
  Verification is recorded in docs/release/CI-2026-10-15.md.
- Supersession, replay fan-out/handler, datasets and release admission remain unfinished.

## Configured replay seed — October 15, 2026

- Added platform.replay_seed to the tenant configuration registry with default 20260912 and
  signed-bigint validation. Revision 0162 seeds existing databases without deleting historical
  catalogue metadata on downgrade. New attempts resolve configuration; retries keep their seed.
- Corrected the missing composite primary-key declarations for the three validation tables in
  the data model. Exact migration, attempt and schema evidence is in docs/release/CI-2026-10-15.md.
- Supersession/start orchestration, replay fan-out/handler, dataset publication and admission
  remain outstanding. This setting does not enable a release or deploy anything.

## Frozen validation-attempt persistence — October 15, 2026

- A parent-locked writer saves attempt metadata and selected group/head rows atomically before
  any job dispatch. Retrying the same attempt preserves its seed and selection, including
  NO_SOURCE. A new attempt requires the predecessor to be superseded explicitly.
- The writer records a tenant-level freeze audit event and refuses partial entity scopes,
  cross-tenant lookups, seed changes, skipped attempt numbers and active predecessors.
- Exact verification is recorded in docs/release/CI-2026-10-15.md. The orchestrator still needs
  replay-seed configuration resolution, supersession/start commands, fan-out/handler, dataset
  publication and release admission. No release is enabled by freezing an attempt.

## Release-validation population reader — October 15, 2026

- Added a tenant-wide, single-statement reader for current heads, open-period member events,
  sealed ledger activity, enabled-book recognition-method strata and member entity ids.
  Partial entity scopes are refused; the reader does not widen caller scope.
- Current membership uses active database rows rather than application-clock comparisons.
  Verification evidence is recorded in docs/release/CI-2026-10-15.md.
- Frozen-attempt persistence, fan-out/handler, dataset publication and release admission remain
  outstanding. This reader does not dispatch jobs or enable releases.

## AI command audit coverage — October 15, 2026

- Registered all ten AI command routes and added real API scenarios to the shared audit walk:
  settings author/test/submit/withdraw, extraction/explanation requests, proposal accept/reject,
  and the workspace kill switch. Retained synthetic proposal evidence needs no provider call.
- Draft acceptance exposed a missing computation-evidence audit classification; it now names
  the source computation's contract members. Pending-category negative controls remain active
  through a synthetic pending catalogue, with a separate missing-live-AI-evidence assertion.
- Verification evidence is recorded in docs/release/CI-2026-10-15.md. Full candidate acceptance,
  replay orchestration/release admission and independent accounting sign-off remain open.

## Verification helper typing — October 15, 2026

- Resolved all nine errors found by the explicit scan of five regression-test modules:
  separate AST owner/callee variables, concrete row mappings, typed route traversal, and
  explicit optional-value assertions. The approval-race test imports the helper from its
  defining module and still patches the production call site.
- Evidence is recorded in docs/release/CI-2026-10-15.md. AI audit catalogue and lifecycle-walk
  integration remain the next known CI gap; full candidate verification is still outstanding.

## Frozen-CI failure triage — October 15, 2026

- Rechecked the old failure nodes against current main: report-source scope inventory and
  estimate-upload permission assertions needed updates. Upload-for-AI does not grant estimate
  attachment rights. The settings fixture now uses independent administrator author/approver.
- Job heartbeat verification now includes AI and release-verification foreign keys. Expanded
  job/settings database checks pass; exact evidence is in docs/release/CI-2026-10-15.md.
- Ten AI command routes still lack audit catalogue/walk integration; the AI lifecycle category
  remains pending. The nine helper typing errors found during triage were resolved above.

## Verification result persistence — October 15, 2026

- The runtime store binds each decision to the actual scheduler task, process release and
  frozen group/source selection. Result, accepted pointer, state and contract audit event
  commit together; duplicate delivery writes no duplicate evidence. ERROR remains retryable.
- Targeted verification is recorded in docs/release/CI-2026-10-15.md. Handler/fan-out,
  dataset publication, selection creation and release admission remain unfinished.
- The older full CI on frozen 3cf8f5b ended with 11,567 passed and 22 failed. Its failures
  require current-main triage; it is not current-candidate acceptance.

## Release verification schema — October 15, 2026

- Revision 0161 adds per-release validation, frozen attempts/group selections and immutable
  verification results. Tenant RLS, execution identity, task deduplication, set-once acceptance,
  same-selection guards and retained file holds are enforced by the schema.
- Existing privacy/snapshot inventories now classify these four tables; synthetic parser controls
  preserve coverage of their former prose/hybrid declarations. Populated downgrade is refused.
- Verification evidence is in docs/release/CI-2026-10-15.md. Fan-out/handler,
  validation dataset publication and release admission remain unfinished; schema is not enablement.

## Verification write transaction safeguards — October 15, 2026

- Recording an ERROR preserves the group's nonterminal state so aggregation waits for retry
  or exhaustion. Only an accepted non-error result marks the group COMPLETE.
- A PostgreSQL adapter now implements the execution-lock port in the writer's existing
  transaction. The lock lasts through commit/rollback, beyond the Python acquire block.
- Verification results are recorded in docs/release/CI-2026-10-15.md. The database store and
  replay handler remain outstanding; the adapter is not yet wired to a production write path.

## Durable scheduler execution locks — October 15, 2026

- Job creation accepts an execution lock retained in immutable, reserved metadata. Every
  dispatch reloads it, including retries and stranded-task recovery; handlers do not receive it.
  A dispatch cannot replace the stored lock. Per-job waiting deduplication remains separate.
- Database verification exercises the actual scheduler fetch function for same-group exclusion
  and independent-group progress. Final results are recorded in docs/release/CI-2026-10-15.md.
- Replay fan-out must supply verify:<group id>; persisted verification and its transactional
  advisory lock remain outstanding. No replay handler is newly registered by this change.

## Replay job execution identity — October 15, 2026

- Handlers can read the registry's exact task_id and attempt number through read-only context
  properties. Inline work has neither, including when it inherits a guarded parent runtime.
- Database coverage checks retry identity, stale-task fencing and duplicate delivery. The
  transaction inventory now names the existing SCH-11 tenant-directory read; writes stay guarded.
- Persistence tables, verification handler and same-group scheduler locking remain outstanding.
  Verification evidence is recorded in docs/release/CI-2026-10-15.md.

## Malformed replay evidence — October 15, 2026

- Malformed input/output evidence now produces an integrity mismatch before engine execution,
  including missing input bodies, invalid decimal tags, invalid JSON/UTF-8 and non-object outputs.
  The shared codec also rejects non-finite decimals. No current-state fallback is introduced.
- Ten failure-first regressions reproduced uncaught parsing exceptions. Replay/codec checks and
  final typing/lint evidence are recorded in docs/release/CI-2026-10-15.md.
- Persisted replay verification, release orchestration and RPT-38 remain outstanding.

## Verified computation sources for report replay — October 15, 2026

- The internal reader checks report.run over the complete stored group and performing entities
  before opening files, then validates raw/logical hashes, codec/cutoff, group membership,
  output book coverage, predecessor heads and ledger-cutoff shape. SYSTEM has no implicit grant.
- Old inputs remain stable after the group advances. Missing evidence never rebuilds from current
  state. Corruption and scope checks pass; final verification is in CI-2026-10-15.md.
- This reader is not yet wired to RPT-38. Replay orchestration, ledger cross-checks and persisted
  replay verification remain outstanding. Local recovery on frozen 659314a passed.

## Typed computation evidence — October 15, 2026

- Revision 0160 retains encrypted typed inputs and canonical outputs for new computations,
  with original file digests, logical hashes, book coverage, predecessor and ledger cutoffs
  captured before their own postings. Storage failure rolls back the computation.
- Existing computations are not reconstructed or backfilled. Evidence has no generic download
  route and remains held against deletion. Verified backfill and replay jobs remain open.
- Fourteen database regressions pass, including the close/reopen/re-lock workflow. Schema,
  privacy, typing and lint verification is recorded in docs/release/CI-2026-10-15.md.
- This supplies new source evidence needed by RPT-38; its replay integration and report remain open.

## Close comparison navigation — October 15, 2026

- The history grid, drawer and keyboard action now traverse reopen records to the prior
  freezing lock before constructing RPT-38 selectors. Incomplete, cyclic or out-of-order
  history produces no comparison link; permanent-lock records are not report snapshots.
- Correcting the synthetic history to the real backend chain reproduced two link failures.
  All 16 history tests, frontend typing and repository lint pass.
- The missing RPT-38 builder and driver attribution remain open. This repairs its entry path.

## Re-lock snapshot integrity — October 15, 2026

- Re-lock comparisons now verify the stored hash and row count of both the previous and newly
  frozen datasets before comparing them. A mismatch refuses the comparison; no live fallback.
- Focused corruption and comparison tests and backend typing pass. The database re-lock workflow and lint
  pass; evidence is recorded in docs/release/CI-2026-10-15.md.
- RPT-38 driver attribution and the pre-approval diff remain outstanding.

## Current report availability — October 15, 2026

- Reconciled LIMITS B4-6/C-11 against the runtime registry: 40 builders among 57 definitions,
  with 17 generic builders still absent. First-close evidence packs use their separate API.
- Labelled the old fifteen-test failure list as historical; registration is not accounting
  acceptance. Four catalogue checks pass; details are in docs/release/CI-2026-10-15.md.
- The isolated all-workspace recovery drill passed on frozen d7e8715: eight tenants, 306 files,
  702 tables, no missing or reduced table counts, and verified cleanup. No deployment.

## Worker container health probe — October 15, 2026

- A live baseline run exposed five-second probe timeouts despite a fresh heartbeat. The image
  now calls a small module using the existing freshness function, without importing worker
  handlers or the CLI. The 60-second freshness rule and Docker timeout remain unchanged.
- Unit/process and Linux-container checks pass. The committed 4c4b583 baseline passes too;
  the real Docker health command completed in about 0.92 seconds.
  Evidence is in docs/release/CI-2026-10-15.md. No deployment.

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
