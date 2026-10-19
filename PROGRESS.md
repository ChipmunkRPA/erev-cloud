# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## Practical expedient disclosure inputs — October 19, 2026

- Added disclosure_expedients.capture for the ten PRACTICAL_EXPEDIENT registry parameters.
  Requires current scoped report permission and an entity existing at the aware cutoff; resolves
  published entity/book policy values and retains their source IDs/levels, labels and references.
- ASC606 and IFRS15 references follow the local POLICIES table; forced IFRS exclusions are
  preserved. No website links are emitted. A nonpublic-only franchisor election on a public entity
  refuses rather than implying eligibility. These are entity policies, not contract-use assertions.
- POL-195 suppression hides rendered rows while retaining the full facts and omission note.
  Registry category/reference drift refuses rather than silently dropping a newly added expedient.
- Real registry reads verify ten ASC606 rows, the applied cost expedient with 340-40-25-4 and
  IFRS forced royalty exclusion; the existing 16-child database journey passes. Focused omission
  check passes; Ruff and Mypy pass for the new module.
- Still required: bind these facts to the parent's exact cutoff and frozen disclosure snapshots,
  assemble all seven sections, parent worker scheduling/publication, PDF and viewer. Policy test
  cutoff uses DB observation time separately from the child-run fixture; full pack acceptance
  is not implied. Five catalogue builders remain unregistered.

## Verified disclosure child results — October 19, 2026

- Added disclosure_results.collect: authorize/resolve attached children, return pending IDs
  without partial sections, refuse failed children, then verify the complete finished population.
  Reads original child JSON files under readable-file locks with bounded aggregate input size.
- Validates purpose/media type/size/file digest and run output hash, canonical report envelope,
  parameter binding, row count, control totals and tie-outs. Restores date/timestamp cells to typed
  ReportData; rejects duplicate row keys and envelopes that do not round-trip canonically.
- Real database journey now executes all 16 child report jobs and collects their verified outputs,
  after first observing pending children. This fixture has no booked accounting population; it
  validates task/output integration, not populated disclosure accounting acceptance. Three focused
  plan/decoder checks pass; Ruff and new-module Mypy pass.
- Remaining: registered parent worker/dependency scheduling, seven-section assembly, frozen
  disclosures, practical expedients, PDF and viewer. Five catalogue builders remain unregistered;
  no disclosure_pack completion or production-readiness claim.

## Durable disclosure parent-child attachment — October 19, 2026

- Added disclosure_children.ensure: locks the parent run, checks the initiating actor's current
  run/export permission, creates and attaches the complete child population in one transaction.
  Existing attachments are reused without fresh calendar resolution or replacement child runs.
- Reuse checks child identities/order, code/version, creator, entity/book/cutoff, output format,
  historical currency basis and matching period/quarter intervals. Missing, duplicated or mismatched
  children refuse. Locked parents explicitly require the separate frozen-disclosure source path.
- Real database check passes for 16 children, repeated calls and reuse after commit in a fresh
  transaction, plus permission denial and corrupted attachment refusal without new rows. Ruff and
  new-module Mypy pass. Concurrent callers serialize on the parent row; no concurrent stress test
  or completed pack publication is claimed.
- This helper is not yet wired to a registered parent builder/worker. Parent dependency waiting,
  child output verification and assembly, frozen snapshots, expedients, PDF and viewer remain open.
  Five catalogue builders remain unregistered; this does not complete RPS-15.

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
