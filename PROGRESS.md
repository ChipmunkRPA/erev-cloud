# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## BBR actual FX admission fix; forecast dependency audit — October 19, 2026

- Fixed a real cross-currency defect: BBR matched `SPOT`, while E-51 and approved database
  rate rows use `spot`. Both live and retained readers now use RateType.SPOT.value. The old
  authored uppercase fixture masked the mismatch and has been corrected.
- Actual API-created, submitted and independently approved spot versions now exercise BBR:
  100.01 EUR × 1.2345 = 123.46 USD; after approval of 1.3000 the old cutoff still uses v1 and
  the new cutoff uses v2 (130.01 USD), preserving the exact version identities.
- Forecast audit found no implemented scenario/event-set/run tables or domain runtime; these
  are still pending in privacy/snapshot catalogues and FCS-1 to FCS-3. Forecast reports require
  that foundation before a genuine output builder. No forecast implementation is claimed yet.
- Seven report builders remain unregistered; count does not represent the size of the forecast
  subsystem work. Independent accounting sign-off and broad acceptance remain open. No deployment.

## BBR cell contributions and business-record navigation — October 19, 2026

- Retain valued pre-aggregation contributions beside the original raw sources. All four BBR
  money cells rebuild their amounts from those inputs and list source IDs and contributions.
  New contract-event/modification owner rules use the existing reader-scope redaction path.
- Enabled four drills in the report grid. The contributor panel links business records to
  contract history/billing, modification detail or contract journals; it does not send these
  records to unsupported calculation-graph routes. Source IDs remain visible.
- Actual API revenue totals, zero cell, new booking and billing contributions pass; a later
  invoice does not change an earlier report's contributions. Frontend drill/link tests pass,
  as do frontend typing and targeted backend typing/lint. See CI-2026-10-19.md.
- Seven report builders remain missing. BBR complex attribution, locked/reporting-currency
  sources, wider scope/modification-cell/browser acceptance and accounting sign-off remain open.
  Existing BBR runs without aggregation evidence refuse a drill instead of reading live data.

## BBR report delivery, currency valuation and journal comparison — October 19, 2026

- Registered bookings_billings_revenue in the report framework with functional/month defaults,
  fiscal ranges, scoped sources and retained-input reruns. JSON/CSV use the common report flow;
  standard XLSX/PDF writers are available but were not separately exercised in this slice.
- Added historical approved spot-rate valuation for contract/billing contributions, preserving
  rate/version identities. Posted revenue keeps its stored functional amount. Missing or
  ambiguous rates refuse. Journal revenue uses retained lifecycle evidence at the same cutoff.
- Actual API report, PASS journal tie-out, CSV hash and identical rerun passed; migration 0175
  reconciles IPE source disclosure. Evidence is in CI-2026-10-19.md.
- Seven catalogue definitions still lack registered builders. BBR contributor cell routes,
  reporting-currency and lock datasets, complex/shared attribution, cross-currency database
  acceptance, browser acceptance and independent accounting approval remain open. No deployment.

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
