# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## Asynchronous scenario creation and creator access — October 19, 2026

- POST /scenarios now accepts name, purpose and optional known_at, returns a TENANT_SNAPSHOT
  job with preallocated scenario/snapshot ids, and registers the source scenario only after the
  sandbox copy succeeds. Completion audits both tenants; job results link to the scenario list.
- Preserves copied memberships. A creator absent from the historical snapshot receives only
  Viewer plus a dedicated scenario.use role before period replay; inactive copied membership
  refuses. Scenario sandbox codes use the allocated tenant id so equal names do not collide.
- scenario.use does not inherit tenant.snapshot's step-up requirement; the ordinary snapshot
  command still enforces it. Purpose input is limited to the database memo's 4000 characters.
- Actual API + worker checks: copied creator, historical snapshot without creator (minimum grants),
  idempotent request replay, source/sandbox audit records, populated tenant-isolated listing,
  and ordinary snapshot permission/step-up regression: 4 passed, 4 deselected (10.92s).
  Ruff, mypy (10 files), make openapi passed; generated frontend API types updated.
- These are empty-business-data copies, not the Q4 world with contracts and closed periods.
  Closed-period replay for a requester with only scenario.use, nonempty determinism, worker
  interruption/failure boundaries, archive, refresh, event sets, forecasting and UI remain open.
  FCS-1 is not complete and no forecast report builder is newly delivered. No deployment.

## Scenario catalogue API and refresh-compatible pointer — October 19, 2026

- Added GET /scenarios with scenario.use authorization across the tenant, status filtering,
  stable cursor pagination and named creator output. Tenant identity/internal actor fields are
  omitted. OpenAPI and frontend API types regenerated.
- Migration 0177 removes the unintended immutable scenario_tenant_id check from 0176: FCS-2
  refresh must be able to replace the sandbox. Production/source-sandbox relationship checks
  remain; this migration does not implement refresh or permit cross-production targets.
- Actual HTTP check covers denial without permission, populated ACTIVE/ARCHIVED listing,
  status filtering and exclusion of another tenant's scenario. Together with forecast migration
  round trip: 2 passed (7.70s). Ruff, mypy (4 files) and make openapi passed.
- Scenario creation, archive, refresh, creator grants, event-set replay and forecast jobs are
  still absent. No browser workflow or refresh business acceptance claimed. Seven missing
  report builders and engine_trueup_register remain outstanding; no deployment.

## Forecast persistence foundation; reporting backlog retained — October 19, 2026

- Migration 0176 adds scenario, versioned forecast_event_set, forecast_run and deal_preview,
  with tenant-bound keys/RLS, sandbox guards, published-input freeze, terminal run freeze and
  write-once preview save linkage. Privacy and snapshot inventories now include these tables.
- This is schema groundwork only. Scenario creation/refresh APIs, input replay, forecast jobs,
  output builders and UI remain unfinished; FCS-1 is not complete.
- Reporting priorities remain: forecast_outputs, actual_vs_forecast, parallel_run_comparison,
  variance_between_closes, contract_sample_pack, period_evidence_pack and disclosure_pack.
  Separately, engine_trueup_register and existing-report acceptance gaps remain open.
- Focused verification: PostgreSQL migration round trip and installed RLS/transition bodies pass;
  database lint passes; privacy/snapshot checks: 76 passed. Architecture replay: 68 passed,
  5 failed at the existing multiline CHECK parser in migration 0166, before 0176; not waived.
- No deployment, forecast execution, financial acceptance or production-readiness claim.

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
