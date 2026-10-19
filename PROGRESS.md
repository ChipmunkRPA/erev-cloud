# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

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

## Migration source admission for parallel comparison — October 19, 2026

- Added parallel_sources.read_for_report. It binds the migration's original successful import
  operation, subject/parameters and cutoff; retrieves the confirmed entity mapping; and requires
  report permission for the complete mapped source population before opening plaintext.
- Verifies original LEGACY_DATABASE purpose, size and SHA-256 against the migration, then compares
  every retained history row's identity/raw hash with the original SQLite record. Temporary source
  copies and streams close on failure. Evidence retains file, operation, mapping and row identities.
- Linked sandboxes require their own authorized context; no tenant switch is performed. Current
  support is same-tenant complete-source admission, not partial-entity or replay-sandbox completion.
- Two real import scenarios pass (identity and renamed entity mappings), including incomplete-scope
  denial and a same-size altered-file digest refusal. The fixture now carries the actual source hash
  and job subject instead of placeholders. Ruff and new-module Mypy pass; checking the existing PG
  test module also reports five pre-existing type diagnostics outside this change.
- Next RPT-42 work: persist/rebuild the complete retained inputs, compose both readers with the
  comparison, register the worker and exports, and finish migration replay/sandbox lifecycle.
  Six catalogue builders remain unregistered; full LMG-4/5 accounting acceptance remains open.

## Authorized eRev parallel-run inputs — October 19, 2026

- Added parallel_actual.read: requires report.run for the requested entity IDs, resolves exact
  calendar boundaries, reads historical sealed journal facts through the existing legacy journal
  consolidation, and reads traced/frozen contract balances through the standard balance reader.
  It never switches tenant or implicitly authorizes a migration sandbox.
- Journal groups optionally retain composite line/partition/posting references. Their normal view
  behavior is unchanged when source capture is off. Actual facts retain period/currency, source
  version or frozen-lock/hash references, cutoff and a deterministic source-evidence digest.
- Missing expected contract balances withhold the period and record the missing population;
  unmatched currencies and calendar boundaries refuse. Missing actuals are never fabricated zeros.
- A real booking/computation/ledger case proves account totals match legacy_je_summary, repeat
  reads retain the same digest, missing population is excluded and report permission is required.
  Targeted PostgreSQL check: 1 passed; Ruff and Mypy pass. This is not LMG-5's complete migration
  acceptance or a cross-entity/locked-period browser journey.
- Still required: migration source-file/database admission, confirmed mapping retrieval, full
  retained binding/rebuild, worker/export integration and current grants at publication. Migration
  replay import and its sandbox lifecycle remain unfinished. Six builders remain unregistered.

## Independent legacy monthly comparison inputs — October 19, 2026

- Implemented migration.parallel_legacy.snapshot over retained Contract_Live history. Gross
  journal construction follows component-major ordering, binary64 four-place rounding, the
  two-place zero filter, compensated grouped sums and final cents; no eRev engine output is used.
  Compatibility floating arithmetic is isolated from the exact comparison layer.
- Period-end contract balances sum latest obligation positions, never repeated contract totals.
  Coverage stops at the last source economic date. Entity mappings, duplicate identities,
  nonfinite amounts and unsupported currency/book selections refuse. Cross-entity contracts
  refuse rather than misattribute a legacy consolidated journal. Only two-decimal source currency
  is supported; the legacy format has no per-row currency column.
- Source identity includes raw-row digests, requested period boundaries and confirmed entity
  mapping. Journal/balance facts carry exact source-row references. Authorization and retained
  file/database integrity admission still belong to the upcoming report source reader.
- All ten archived monthly legacy gross exports (Jan–Oct 2023) match by account/debit/credit,
  preserving October's 5,043.84 debit / 5,043.85 credit imbalance. SQLite January Contract 2
  balance is -58.85. Focused checks: 17 passed; Ruff and Mypy pass.
- Remaining RPT-42 work: authorized eRev period/journal/balance selection, complete retained
  binding and report worker/export integration. Migration replay import remains unfinished
  (jobs.py explicitly refuses it); sandbox access must retain tenant/grant boundaries. These
  source checks do not complete LMG-4/5 or independent accounting acceptance.

## Parallel-run comparison calculation and viewer — October 19, 2026

- Added parallel_comparison.compare for independently produced journal and contract-balance
  snapshots. Both sources must declare complete entity/book/currency period coverage and retained
  identities. Missing coverage is excluded rather than converted to zero; calendar disagreements,
  duplicate rows, incomplete balance components and sub-minor-unit input amounts refuse.
- Journal differences are eRev debit-minus-credit less legacy debit-minus-credit. Balance
  differences are eRev liability less asset/unbilled less legacy billed-minus-recognized.
  Fraction arithmetic preserves cents independently of Decimal context; no balancing plug.
- Separate section/currency totals and source-row contributor references are retained. Viewer
  sections, readable columns and the specified no-periods empty copy are implemented.
- Nine focused arithmetic/coverage checks and a frontend section check pass; type/lint checks pass.
  These use explicit source facts, not command-driven LMG-5 January/October acceptance evidence.
- Still required: independent legacy monthly-output reader preserving legacy rounding, authorized
  eRev journal/balance source selection, retained binding and worker registration/export journeys.
  RPT-42 remains unregistered; six catalogue builders remain. No readiness claim or deployment.

## Engine true-up register — October 19, 2026

- Implemented and registered engine_trueup_register (migration 0180): latest processing portions
  at exact known_at, unresolved origin periods, sampled flag and actual attributed sealed lines.
  Signed transaction/functional amounts remain separate by entity/book/period/currency/account role.
- No-posting portions carry no invented amounts. A deferred portion remains deferred even when
  it has postings. Whole-group terminal is withheld when an entity is outside the selected scope.
- Retained input facts and hash supply same-source reruns. Workers reload current report/export
  grants. JSON/CSV/XLSX use the normal report pipeline; viewer uses readable ordered column metadata.
- Real computation cases: 3 passed (posted and no-posting outcomes); CSV worker plus bound rerun:
  1 passed; database catalogue: 6 passed; catalogue/source contract: 23 passed; deferred/multicurrency
  arithmetic and missing-attribution refusal: 1 passed. Type/lint checks pass.
- Six catalogue builders remain: actual_vs_forecast, forecast_outputs, parallel_run_comparison,
  contract_sample_pack, period_evidence_pack and disclosure_pack. Full upgrade lifecycle,
  deferred-period reopening, cross-entity browser acceptance and accounting sign-off stay open.

## Close variance header, totals and empty state — October 19, 2026

- Added earlier/later lock timestamps and copyable IDs to the report header, from hash-checked
  retained evidence. Export source labels name both locks; the viewer says Frozen close comparison.
- Both sections show separate totals by measure and currency; revenue and RPO cannot cancel each
  other in a shared footer. Identical frozen figures retain zero rows and explicit no-change copy.
- Fixed column ordering and added optional lock_comparison API metadata; regenerated client types.
- Targeted real-engine presentation: 1 passed; worker/rerun and permission-loss: 2 passed after
  correcting SQL result materialization. Frontend: 3 passed; Ruff, Mypy, tsc and ESLint pass.
- Remaining report development: actual_vs_forecast, forecast_outputs, parallel_run_comparison,
  contract_sample_pack, period_evidence_pack, disclosure_pack, and engine_trueup_register.
  Wider variance replay and populated close/cell/browser accounting acceptance remain open.

## Close variance cell explanations and viewer sections — October 19, 2026

- Connected Change cells in both variance sections to retained contributor evidence. Contract
  amounts reconcile exactly; identity/hash/scope checks bind them to original groups, and SQL
  resolves contracts only through the retained computation/book. A run effect is not split into
  invented per-event amounts. Current contributor visibility applies to contract records.
- Added optional plain-text contributor details: contract name, drivers, event keys, both lock
  IDs and source-row keys where available. The viewer links to internal contract history.
  OpenAPI/client types are regenerated. Older evidence without cell facts refuses by name.
- Fixed numeric section routing; exports retain readable section labels. Both sections expose
  only Change as drillable and hide internal measure/driver fields. Reruns refresh derived
  contributor evidence while still validating and recomputing the original source identities.
- Real-engine replay/presentation suite: 25 passed, including cell arithmetic/hash refusal with
  a lookup seam (not an HTTP/DB cell journey). Worker/rerun/permission-loss regression: 2 passed;
  frontend variance/BBR checks: 3 passed. Mypy, tsc, Ruff, ESLint and make openapi pass.
- Six catalogue builders remain unregistered. Populated close-to-report/cell browser acceptance,
  headers/empty-state polish, broader reference/FX/population replay and accounting sign-off
  remain open. No deployment or production readiness claim.

## Registered close variance worker — October 19, 2026

- Registered variance_between_closes with an adapter source contract. Creation authorizes both
  frozen locks and complete retained groups; stored run scope includes every required entity.
  Locks unavailable at the requested cutoff refuse. No schema/API shape change is required.
- REPORT_RUN now reads/authorizes, closes its UOW, computes with attempt-fenced heartbeats,
  then reopens a UOW and reauthorizes before rendering/storage. The builder compares original
  source identities again. Same-source reruns reread and recompute; no saved-output replay.
- Source bindings retain lock manifests, contract/computation mappings, runtime/input/output
  identities, complete entity requirements and contributor evidence. Direct in-transaction
  calls without the phased calculation result refuse.
- Seeded empty locks with real snapshot files: actual job/output/rerun passes; an injected
  post-compute permission loss prevents output publication. The calculation hook proves all
  read sessions are outside transactions. Both cases pass; existing report/rerun regression,
  catalogue/source-contract checks, source Mypy and changed-file Ruff pass.
- Six catalogue builders remain unregistered. RPT-38 still needs populated close-to-report
  financial acceptance, cell explanation routing, UI/header polish, wider reference/FX and
  new/regrouped contract replay. No production readiness or deployment claim.

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
