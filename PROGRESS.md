# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## BBR activated bookings and application value attribution — October 19, 2026

- Added activated-contract values from each contract's own signed booking line consideration,
  with booking/activation provenance. Drafts and voided contracts contribute no new bookings.
  Separate-contract modifications are identified through their applied booking event and
  excluded from the new-contract column, preventing later activation from double counting.
- Added original application-group/version reads and predecessor-based modification price
  differences, retained for rebuilds and counted once per modification, not per obligation.
  Missing predecessors, ambiguous applications and shared valuation causes refuse attribution.
- Real K01 booking value 135,000 and K02 applied modification 60,000 checks pass. Targeted
  evidence and two pre-existing test-module typing findings are in CI-2026-10-19.md.
- BBR still needs FX valuation, journal comparator sourcing, source adapter/registration,
  contributor routes and broader acceptance. Pre-activation changes and shared valuation
  causes need further attribution support; independent accounting sign-off is still absent.
  Eight reports remain without complete registered builders. No deployment.

## Bookings/billings/revenue source and aggregation implementation — October 19, 2026

- Implemented scoped, cutoff-bound raw source capture for RPT-37, retaining event identity
  decisions and sealed revenue lines. Billing reuses the engine-aligned invoice identity,
  credit and void handling of the balance rollforward. Revenue preserves posting periods,
  transaction/functional amounts and line identities, including signed reversals.
- Implemented fiscal month/quarter/year presentation, entity/currency splits, signed totals
  and journal-revenue comparison. Missing measure populations or FX valuation refuse.
- Real source reads prove later invoices do not change an earlier cutoff or retained inputs;
  scoped reads and retained scope/book mismatches are exercised. Targeted evidence is in
  CI-2026-10-19.md. No full-suite rerun or deployment.
- RPT-37 is not registered yet: activation-value and applied-modification attribution, FX
  valuation, journal comparator sourcing, contributor routes and end-to-end publication remain.
  Eight reports still lack complete registered builders; do not mark this report finished.

## Contract BI extract and source history — October 19, 2026

- Added extract_contracts v1: fixed header columns, historical customer/entity codes,
  JSON/CSV, creation-time incremental windows and retained inputs for identical reruns.
- Migration 0174 captures contract/header and code changes atomically in append-only source
  revisions; existing rows receive migration-time baselines. Missing earlier coverage refuses.
  Capture time is not commit time; restored sandboxes start new history.
- Actual API export, subsequent contract update, historical read, rerun, CSV hash and database
  capture protections passed. Source disclosure matches the migrated catalogue. Targeted
  inventory/privacy checks and typing passed; details in CI-2026-10-19.md.
- All nine extract builders now exist; eight other catalogue builders remain. Locked datasets,
  watermarks, true-up, broader acceptance and independent accounting sign-off remain open.
  Continue unfinished reporting development; no deployment.

## Journal line BI extract — October 19, 2026

- Added extract_journal_lines v1 with entity/book scope, source-time lifecycle reconstruction,
  full/incremental creation windows, fixed typed columns and per-currency debit/credit totals.
  A later cancellation does not erase an earlier historical population; unknown state refuses.
- Registered JSON/CSV and retained line/label/lifecycle evidence for reruns. The existing JE
  population shares its transition-history reader. Migration 0173 updates source disclosure.
- Real API cancellation, historical reads, CSV hash, totals and rerun checks pass. Evidence is
  in CI-2026-10-19.md. Nine builders remain missing, including the contract extract; locked
  datasets, watermarks, true-up and browser acceptance remain unfinished. No deployment.

## Legacy Contract_Live BI extract — October 19, 2026

- Added extract_legacy_contract_live v1 over all effective dates of ASC606 history with
  creation/source cutoffs and incremental row selection. Other books are refused explicitly.
- Preserved the 71-column formatter and original exact trace texts. Retained current and
  predecessor inputs supply reruns without querying today's history. CSV/JSON metadata and
  source contracts are registered; migration 0172 reconciles disclosed query sources.
- Actual API checks match the existing legacy history output and verify CSV hash and rerun;
  evidence is in CI-2026-10-19.md. Ten builders remain missing, including contract and journal
  extracts. Locked datasets, watermarks, true-up and browser acceptance remain open.

## Sealed subledger BI extract — October 19, 2026

- Added extract_subledger_lines v1 with explicit business/server recording and server seal
  cutoffs, entity/book scope, exact decimals and retained contract/period/account labels.
- Added JSON/CSV metadata and per-currency plus entity/book/currency/period control totals.
  Registered source retention and reruns; migration 0171 updates disclosed query sources.
- Actual API checks cover CSV hash, grouped balance, incremental selection, pre-seal exclusion
  and reproduction. Evidence is in CI-2026-10-19.md. The guide explicitly distinguishes
  recorded-time incremental output from commit-time change capture.
- Reporting remains open: 11 missing builders, three of them extracts. Locked datasets,
  watermark defaults, true-up and live browser acceptance remain unfinished. No deployment.

## Contract balance BI extract — October 19, 2026

- Added extract_balances v1 over latest per-contract versions, scoped by balance entity.
  Fixed columns preserve transaction/functional currency amounts, with contract/entity labels.
- Registered full/incremental JSON/CSV delivery and retained-input reruns. Control totals group
  contract liability, contract asset and unbilled receivable by functional currency. Existing
  extract controls expose the report; the guide states field types and snapshot-delta semantics.
- Reporting remains open: 12 missing builders, four of them extracts. Locked datasets,
  automatic watermarks, true-up and live browser acceptance remain unfinished. No deployment.

## Schedule line BI extract — October 19, 2026

- Added extract_schedule_lines v1 over latest per-contract versions, scoped by schedule entity,
  with period and contract identifiers. Known/created cutoffs and incremental line creation
  windows use the SQL chain reader. Row identity includes the source partition date.
- Registered JSON/CSV metadata and retained-input rebuilding; exact decimal values and
  per-currency amount totals use existing extract page controls. User guide documents types
  and snapshot-delta semantics. Targeted evidence is in CI-2026-10-19.md.
- Reporting remains unfinished: 13 missing builders, five of them extracts. Locked extracts,
  automatic watermarks, true-up and live browser acceptance remain open. No deployment.

## Obligation BI extract — October 19, 2026

- Added extract_obligations v1 with latest-per-contract chain selection, all book statuses,
  explicit created/known cutoff and incremental created-time filtering. Former group versions
  do not duplicate contracts, and after-cutoff candidates cannot displace earlier versions.
- Exported fixed typed columns and exact decimal strings, with per-currency allocation and
  cumulative-revenue sums. Registered JSON/CSV delivery and retained-source reruns; existing
  extract page controls expose the report. User guide states snapshot-delta semantics.
- Reporting remains open: 14 catalogue builders missing, six of them extracts. Locked extracts,
  watermark defaults, true-up and live browser acceptance remain unfinished. No deployment.

## Contract version BI extract — October 19, 2026

- Added extract_contract_versions v1: all versions in one book, fixed source cutoff,
  created-time incremental window, exact decimal strings and original computation members.
  Partial combined-entity scope is refused; membership reads are batched.
- Registered retained-input rebuilds and JSON/CSV metadata; existing extract controls expose
  the report. Migration 0170 reconciles disclosed query sources. User guide documents types.
- Actual delivery and rerun checks pass alongside event-extract regression. Reporting still
  has 15 catalogue definitions without builders; locked extracts and true-up remain unfinished.
  Evidence is in CI-2026-10-19.md. No deployment or readiness claim.

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
