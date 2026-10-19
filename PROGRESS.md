# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## Retained computation execution for close variance — October 19, 2026

- Added the transaction-free execution phase: original retained inputs must reproduce their
  output hashes and monetary endpoints before DRY_RUN. Common earlier posted amounts and
  previous stream heads are explicit counterfactual adjustments, with original source hashes
  and normalized input identity retained. The final replay must match later frozen money.
- Identical saved computations produce a zero-change result without inventing a later cutoff.
  Reference/calendar/FX changes still refuse. Actual first recomputation adds recorded SSP
  policies, demonstrating a remaining reference-replay requirement rather than a posting change.
- Real-engine carried-posting/delivery, retained hash/endpoint refusal and same-source checks:
  20 passed. Actual database source selection/reuse: 1 passed. Ruff and source/test Mypy pass.
- Group aggregation, reference replay, job/report registration, output formats, UI and full
  frozen-close accounting acceptance remain outstanding. Seven builders remain unregistered.

## Retained inputs for close variance — October 19, 2026

- Added the source read phase: complete frozen closes, historical per-contract computation
  candidates, original evidence verification and whole-group entity authorization. Required
  access entities accompany the result. Missing retained evidence never uses current inputs.
- Filter computation availability before latest-version selection: a later recompute with no
  new event must not replace the computation available at an earlier close cutoff.
- Monetary frozen reads use report.run; evidence packs retain their extra audit.read requirement.
  Five focused frozen-source checks and one retained-computation selection check pass; the latter
  uses a population shell, not a full close. Source Mypy and changed-file Ruff pass.
- Candidate selection is not endpoint reproduction. Job integration, operational input
  normalization, other replay phases, report/UI and accounting acceptance remain required.
  Seven missing report builders remain unregistered. No deployment/readiness claim.

## Dated RPO in close variance replay — October 19, 2026

- Connected RPO through the existing dated trace reader: selected period-end scheduled/awaiting
  remainder, disclosure-entry/status checks and retained duration/right-to-invoice exemptions.
  The projection now receives each executed input bundle, including new activation events.
- Real engine: May delivery leaves April RPO at 795, moves May RPO to 736.16, and attributes
  revenue +58.84/RPO -58.84 to LATE_EVENT. Activation, duration exemption and missing-trace
  cases are covered. Nineteen focused tests, Ruff and Mypy pass; no database writes in projection.
- Amount-specific VC exemptions and foreign functional RPO remain unsupported and refuse.
  Retained-source loading, other replay phases, report/job/UI and financial acceptance remain
  required. Seven missing report builders remain unregistered. No deployment/readiness claim.

## Fixed-period variance revenue/balance projection — October 19, 2026

- Connected event replay to a server-owned monetary projection for recognized revenue, contract
  liability and contract asset plus unbilled receivable. Revenue is signed posted basis plus
  posting intents in the selected posting period; schedules never substitute for revenue.
- Transaction/functional views use exact minor-unit conversion. Missing monetary values,
  inconsistent currencies, unknown subjects and duplicate balance identities refuse.
- Real-engine late-invoice replay now uses this adapter. Fifteen focused checks, Ruff and
  Mypy pass. Dated RPO is explicitly unsupported by this entry point, not silently omitted.
- Retained source loading, RPO projection, other replay phases and report/job/UI integration
  remain required. Seven missing report builders remain unregistered. No deployment/readiness claim.

## Event-only close variance replay — October 19, 2026

- Added the DRY_RUN execution core: ENG-06 event order, maximal driver runs, separate time
  progression, exact reconciliation to both frozen monetary endpoints and execution provenance.
  Endpoint mismatch refuses; no balancing OTHER residual. Inputs remain unchanged.
- Real engine: two late invoices move contract liability from 20 to 170, with 150 assigned to
  LATE_EVENT and both event identities retained. Nine focused tests, Ruff and Mypy pass.
- This is not wired to a report/job yet. Authorized retained source loading, complete monetary
  projection, reference/FX/membership/posting-basis replay phases and RPT-38 report/UI remain
  required. Changed reference inputs and unsupported event classifications currently refuse.
  Seven missing report builders remain unregistered. No deployment or readiness claim.

## Frozen monetary changes for re-lock evidence — October 19, 2026

- Added contract/currency comparison of frozen revenue, contract liability, contract asset plus
  unbilled receivable and disclosed RPO. Exact arithmetic retains both lock/file identities and
  contributing row keys; currencies remain separate and exempt RPO is excluded.
- Re-lock evidence now includes `relock/frozen_measure_changes.json` beside the verified original
  stored comparison. Rejects mismatched/unordered locks, missing sources, corrupt bytes and
  invalid/duplicate monetary rows. No current-contract values or guessed driver attribution.
- Focused monetary/source checks: 23 passed; real lock/reopen/re-lock path: 1 passed. Ruff passes;
  the two implementation modules and new test pass Mypy. The two existing integration test files
  have seven Mypy errors also reproduced from HEAD; they are not new and remain outstanding.
- RPT-38 remains incomplete: ordered DRY_RUN driver replay, report registration/formats, cell
  explanations, browser and K-03 financial acceptance still required. Seven missing report
  builders remain unregistered. No deployment or accounting/production-readiness claim.

## Versioned forecast input set API — October 19, 2026

- Added scenario-only GET/POST /forecast-event-sets, GET/PATCH by id, and publish. Drafts carry
  ordered upload/command fields, source scenario linkage and row ETags. New versions retain the
  previous version reference and input arrays; one draft per code is admitted under a code lock.
- Migration 0179 installs a forecast-specific DRAFT -> PUBLISHED -> SUPERSEDED lifecycle with
  DB-04 immutable publication contents/stamps and one published version per tenant/code.
  Publishing hashes canonical content and atomically supersedes the old version. No production
  approval request is fabricated; shared production configuration approval rules are unchanged.
  This scenario-specific rule is now explicit in T-FC-02.
- Actual HTTP checks inside both created-scenario membership cases cover production refusal,
  request replay, draft edit, stale ETag rejection, publish, API/direct-SQL publication freeze,
  version 2 publication, retained old hash and published-only listing. With the scenario flow
  and empty migration round trip: 4 passed (12.75s). Ruff, mypy (5 files, explicit package bases)
  and OpenAPI/types generation pass. Existing OpenAPI paths/operations are unchanged.
- FCS-2 remains incomplete: no committed-import linkage, automatic recording of successful
  business commands, ordered input replay or refresh yet. These APIs currently manage input-set
  versions; they do not execute or populate forecasts. Forecast runs/output and UI remain open.
  Seven missing report builders remain missing. No deployment or readiness claim.

## Scenario archive and read-only command/worker gate — October 19, 2026

- Added POST /scenarios/{id}/archive with row ETag, creator or tenant-wide Controller admission,
  replay authorization, pending-job refusal and atomic audit records in source and sandbox.
  The sandbox remains ACTIVE/selectable for reading; its source scenario becomes ARCHIVED.
- HTTP commands check the exact source scenario before cached replay and acquire a shared lock
  during business transactions. Worker attempt units of work use the same gate; operational
  failure settlement remains possible. This source-row lock orders normal writes against archive.
- Migration 0178 freezes archived scenario fields and forbids reactivation. The scope trigger
  rechecks sandbox provenance only when its pointer/source changes: a Controller need not also
  hold a membership in the sandbox merely to archive an existing relationship.
- Actual API/worker + migration checks: creator/Controller archive, non-owner denial, queued-job
  refusal, successful archive replay, rejected replay of a formerly successful sandbox write,
  retained reads, delayed worker refusal with FAILED settlement/no business audit, mirrored
  archive audit, migration round trip and ordinary saved-view regression: 5 passed (11.26s).
  Ruff, mypy (7 files), OpenAPI/types generation passed.
- Concurrent races across every custom write path and direct copy transaction are not yet
  acceptance-tested. Nonempty/closed-period scenario copy, refresh, event sets, forecast runs,
  report builders and UI remain open. No production-readiness or deployment claim.

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
