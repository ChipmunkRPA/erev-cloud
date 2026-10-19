# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## Event BI extract and reporting backlog — October 19, 2026

- Registered extract_events with fixed schema v1, explicit entity scope, inclusive source cutoff,
  exclusive incremental start, contact redaction and retained-input rebuilds. Added JSON/CSV
  metadata and CSV byte-hash manifests; source time stays fixed across worker execution.
- Added report-page full/incremental controls and documented field types and operating limits.
  Actual API/worker delivery, incremental validation and rerun passed; existing viewer checks
  and focused Python/frontend typing passed. Evidence is in CI-2026-10-19.md.
- Reporting remains a development priority: 16 catalogue definitions still lack builders.
  Extract lock snapshots, previous-run watermark defaults and true-up register remain open.
  No deployment; no claim of reporting or production-readiness completion.

## Tenant release creation and resumable API — October 19, 2026

- Added authoritative tenant validation creation: empty tenants bootstrap; historical tenants
  require preparation; skipped stronger releases retain their level; downgrades are refused.
- Added POST /release-validations/current/advance with all-entity report permission and command
  idempotency. It resumes frozen replay jobs, JSON reports, attachment and final acceptance;
  MAJOR differences enter independent approval. Repeated calls reuse persisted work.
- Seven focused database cases passed, including the actual API/replay/report/enable path.
  Generated API and frontend types are updated. Detailed usage and evidence are in CI-2026-10-19.
- This is caller-driven advancement. Automatic scheduling, explicit baseline preparation,
  computation admission and the true-up register remain development priorities. No deployment.

## Release acceptance and independent approval — October 19, 2026

- Added finalization from an attached frozen report: matching results enable and seed atomically;
  MINOR differences fail; MAJOR differences create a SYSTEM-prepared independent approval.
- Approval binds the frozen dataset, population and entity set, rechecks current population,
  enables/seeds atomically and dirties only DIFFERENCES groups while preserving prior stamps.
  Rejection keeps the release disabled; stale/withdrawn reviews return it to INCOMPLETE.
- Pending approval supersession now voids STALE_SUBJECT and permits a replacement attempt.
  Revision 0169 adds the approval type and stale-review transition. Existing approval API,
  inbox labels, generated schema and report filters recognize the new subject.
- Targeted checks are recorded in the dated CI log. Release preparation/automatic orchestration,
  baseline/bootstrap handling, computation admission and the true-up register remain development
  priorities; current-candidate release verification and independent accounting sign-off remain open.

## Atomic upgrade computation persistence — October 19, 2026

- Computation persistence now writes posting attribution and append-only portion outcomes in
  the same transaction as postings and head updates, under the shared upgrade-group guard.
- Attribution checks retained predecessor input integrity and records actual posting origins;
  unavailable historical inputs retain the conservative context label. Exact replay adds no rows.
- Database probes cover first computation, no-posting recomputation, changed billing,
  corrupted input refusal and rollback. Full computation regression results are recorded in CI.
- Deferred portion handling uses the existing conservative origin rule; runtime closed-period
  and period-open rescheduling coverage remain outstanding, as do the true-up register,
  final acceptance, approval/admission integration and independent accounting sign-off.

## Immutable posting attribution schema — October 19, 2026

- Migration 0168 adds tenant-isolated, append-only posting_attribution with one row per
  posting. Inserts require the accepted, enabled release and an unsettled processing group,
  matching posting/computation ownership and valid cause-comparison metadata.
- Processing events and attribution share a nonblocking group transaction guard so their
  checks cannot race settlement. Privacy and sandbox snapshot inventories are reconciled.
- Database probes cover attribution, duplicate/mutation/unsupported-cause refusal, terminal
  groups, contention and migration round-trip. Persistence/report integration remains open,
  alongside final acceptance, approval routing and admission. No deployment.

## Atomic upgrade processing queue seed — October 19, 2026

- Added seeding of every current group/entity/enabled-book portion after an accepted upgrade,
  under the tenant population fence. It checks the accepted attempt's population before the
  first write and commits initial PENDING events with a write-once count/digest manifest.
- Retries verify retained initial rows without drawing today's population; partial rows without
  a manifest are refused. Migration 0167 seals the initial queue against later additions.
- Database checks cover unsampled groups, empty populations, rollback, manifest immutability,
  retries after activity and migration round-trip. Final acceptance and approval/admission
  integration remain unfinished; callers must accept and seed in the same transaction.

## Upgrade processing event schema — October 19, 2026

- Migration 0166 adds the tenant-isolated, append-only release_group_processing event log
  per group/entity/book portion, reusing the existing processing-state enum. Its privacy
  catalogue entry is reconciled with the implemented schema.
- Guards require the accepted attempt of an enabled upgrade, valid initial portions,
  sequential events, preserved prior postings and bound computation/posting evidence.
  Outcome checks distinguish deferrals, posted portions and verified no-posting settlement.
- Migration, database schema and lifecycle probes passed; details are in the dated CI record.
  Automatic seeding, computation persistence, posting attribution and final acceptance remain
  unfinished. No deployment or independent accounting sign-off occurred.

## Tenant population transaction fence — October 19, 2026

- Migration 0165 adds shared transaction guards to writes on all 12 population-reader
  tables and their partitions. The acceptance helper reserves the tenant exclusively;
  conflicts refuse immediately and map to retryable lock-conflict responses.
- Database checks cover concurrent shared writers, both contention directions, commit/
  rollback release, tenant isolation, trigger/partition coverage, migration round-trip and
  existing validation/report workflows. Six cases passed; typing and lint also passed.
- Final acceptance must acquire the fence before validation locks and reread under READ
  COMMITTED. The helper is not yet connected to final acceptance or approval/admission.

## Completed-attempt population reassessment — October 19, 2026

- Assessment now accepts COMPLETE/INCOMPLETE attempts while the parent remains RUNNING.
  It rechecks the full population fingerprint and actual job outcomes, requires retained
  dataset references and rejects lifecycle/outcome disagreement.
- Matching/differing completed attempts retain their decisions until contract activity changes;
  changed populations fail reassessment while the original audit reports remain reproducible.
  Cancellation and retry exhaustion remain INCOMPLETE after dataset publication.
- Final acceptance still needs report verification, concurrent population-writer fencing,
  approval routing and admission integration. This change performs no release enablement.

## Verified attempt report attachment — October 19, 2026

- Added transaction-bound report attachment under parent/attempt locks. It requires a
  completed report job for the exact attempt, rechecks caller permissions, rebuilds frozen
  source rows/totals, and verifies the output binding and file integrity before attachment.
- The reference is write-once. Retries recheck evidence without updating the row; rollback,
  replacement refusal, revoked access and corrupted output are covered by database tests.
- Final population acceptance, approval routing and admission remain unfinished. Attachment
  is an internal operation awaiting final orchestration; it never enables the release.

## Validation report catalogue and worker integration — October 19, 2026

- Registered upgrade_validation and its retained-source contract, with migration 0164.
  Jobs reload the human or API-client initiator and enforce current report/export grants
  over the complete frozen entity population before reading or publishing evidence.
- Actual JSON/CSV jobs and reruns passed, including API-client revocation and retry exhaustion
  without output. Required report parameters now fail validation when absent. Catalogue,
  framework, typing and lint evidence is in CI-2026-10-19.md.
- Official attempt report attachment, final acceptance, approvals and admission remain open.
  Repository work only; no deployment or independent accounting sign-off.

## Bound upgrade-validation report builder — October 15, 2026

- Added the report builder over the verified dataset, typed change-count columns and canonical
  text for structured before/after values. Its source binding records the exact file, hash,
  attempt and frozen entity set; reruns rebuild rows rather than reuse cached output.
- JSON/CSV reproducibility and requester-grant checks passed database tests. Unsupported modes
  and incomplete/incompatible bindings fail before evidence reads. Dated CI evidence records
  the checks. Catalogue/job registration and requester reload wiring remain unfinished.
- Final acceptance, approvals and admission remain open; no deployment.

## Authorized validation report source — October 15, 2026

- Added a retained-dataset reader that checks current report.run permission across the full
  frozen entity set before file access. Partial entity selection, wrong tenant and mismatched
  rerun file/hash bindings are refused; SYSTEM has no implicit reader grant.
- Dataset metadata, digest, canonical JSON, source identity and record cutoff are checked.
  Matching/differing report data reproduces after later contract activity; database and typing
  evidence is in the dated CI record. Report catalogue/job integration remains unfinished.
- Final acceptance, approvals and admission also remain open; no deployment.

## Frozen attempt dataset publication — October 15, 2026

- Added terminal-job dataset assembly from frozen selections and retained comparisons. It
  verifies artifact identities, digests and detail counts; failed and no-source rows remain.
- Dataset reference and COMPLETE/INCOMPLETE attempt status commit together. Retries read the
  original file; rollback leaves neither the reference nor a completed attempt. Parent release
  enablement is unchanged. Lifecycle/integrity verification is in the dated CI record.
- Report publication, final population acceptance, approvals and admission remain unfinished.

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
