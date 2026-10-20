# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





## Partial RPO targeted-VC exemptions — October 20, 2026

- POL-200 now excludes the dated targeted-VC quota only for wholly unsatisfied obligations
  with zero recognized revenue. Inception allocation nodes and later allocated deltas supply
  amounts; immutable estimate identities/version evidence distinguishes targeted from ordinary
  price changes. Fixed and untargeted consideration remain in disclosed RPO.
- Net bands and cell contributors are apportioned at currency precision. Reports list the
  excluded portion; dashboard uses the net amount. Frozen RPO retains net and excluded amounts
  on one obligation identity. Rollforward has an EXEMPTIONS movement for exclusion/release;
  close-variance replay shares the quota reader instead of refusing these elections.
- Three focused checks cover real-engine positive/negative/untargeted changes, historical caps,
  partial report rows and release on performance; 27 affected replay checks pass. Existing
  approved-policy and rollforward API journeys pass, with the new movement included. Lint/types pass.
- Full populated partial-exemption API/lock/export acceptance remains to be completed. This does
  not complete multi-currency movement translation, population replay or all release acceptance.
  No deployment; direct main publication.

## Dated functional contract balances and GL comparison — October 20, 2026

- Contract balances now reads retained engine functional targets at the selected period,
  preserving historical-layer liability valuation and monetary asset remeasurement. Foreign
  balances without dated evidence are refused rather than converted with a current rate.
- GL reconciliation uses the same dated targets. Actual EUR 10,000 receivable reports show
  USD 11,050 in August and USD 11,200 in September, both matching uploaded GL balances.
- Locked endpoints select computations available at the lock cutoff and verify the frozen
  transaction endpoint before projecting functional values; selected versions are retained
  for reruns. Locked-endpoint report/rerun and missing-evidence controls pass targeted journeys.
- Full functional movement attribution, reporting-currency translation, additional captions
  without engine functional targets, population replay and RPO partial exclusions remain open.
  This is a functional balance checkpoint, not completion of all reporting currencies. No deployment.

## Reporting reference/FX attribution and GL tie-out — October 20, 2026

- Close variance now replays retained reference inputs before business events and FX rates
  afterward. Each phase retains its input/output hashes and changed fields; cell details expose
  the changed inputs. Original/final frozen endpoints must still match exactly. Group additions,
  removals/regrouping and calendar changes remain outstanding.
- Contract balances and balance rollforward now consume cutoff-qualified uploaded/pulled GL reconciliation
  role totals, compares each entity/role independently and retains those source facts for reruns.
  Missing sources, unsupported currencies and shared/unavailable role bases remain explicit;
  offsetting differences cannot pass. Viewer and XLSX/PDF expose comparison details.
- Necessary validation: 27 variance checks (including real-engine policy and FX changes), two
  GL comparison/rebuild checks, real upload/reconciliation/report and existing rollforward API
  journeys, and targeted viewer checks pass. Python/TypeScript checks are recorded with the commit.
- User priority remains completing attribution, multi-currency, RPO exemptions and GL matching.
  This is an implementation checkpoint, not completion of those four workstreams. Foreign-currency
  rollforward valuation, broader GL coverage, population replay and dated POL-200 exclusions remain.
  POL-199's zero royalty exclusion can be correct under the engine's realization model; the older
  blanket description of both exemptions as missing was too broad. No deployment.

## Tamsin deal acceptance and missing schedule fix — October 19, 2026

- Ran the FCS-6 Tamsin proposal against real published product templates and approved US-LIST
  2026-H2 ranges. SSP selection/range flags and 94,225.26 / 21,774.74 allocations already matched;
  the required November revenue schedule failed because the dry-run bundle stayed DRAFT.
- Deal computation now adds a deterministic hypothetical activation at inception to a single
  booking-only DRY_RUN input. The synthetic event stays in retained evidence, never the database
  event stream. Real save still creates a DRAFT. UI explicitly states the activation assumption.
- Added simulated revenue-to-calculation-date to per-book totals, so backdated proposals reconcile
  allocation = simulated revenue + future scheduled + awaiting trigger. Prior retained previews
  are not recomputed. OpenAPI/frontend types updated.
- Tamsin now passes exact SSP/range/allocation, no MR/VC, November start and deterministic input.
  API/worker journey passes no production contract and total reconciliation. Scratch rollback,
  four computation boundary checks, frontend rendering, Python lint/types and API generation pass.
  This is concrete FCS-6 case evidence, not independent accounting sign-off or full browser/release
  acceptance. No deployment.

## Retained deal preview history — October 19, 2026

- Added a lazy, paginated history panel on SF-18 using the existing entity-scoped summary API.
  Displays creation time, proposed customer/reference, entity, start date, product codes and
  saved state; opens retained calculations and saved draft contracts in new tabs so current
  proposal input is preserved. The list does not fetch full engine traces for every row.
- Supports manual refresh and retry of a failed later page without discarding loaded entries.
  Preview completion and draft-save commands invalidate the shared history query.
- Seven focused history/page/save checks pass, including lazy load, cursor pagination, new-tab
  navigation and later-page retry. Types and lint pass. Broader business/browser acceptance and
  independent accounting sign-off remain open. No deployment; direct main publication.

## Forecast assumption effective-window editing — October 19, 2026

- Added optional UTC start/end controls to draft creation and editing, and saved-window display
  for every version. Blank edited boundaries send explicit null; untouched boundaries are omitted
  from PATCH, preserving original offset/precision when changing other fields.
- Invalid reversed/equal ranges block submission, and unsaved metadata changes block publication.
  All edits retain If-Match/version protection. Published versions stay read-only. Copy makes clear
  this is version metadata and does not rewrite captured event dates or filter replay events.
- Five focused assumption-manager tests pass, covering lifecycle, UTC conversion, preserving
  untouched timestamps, clearing boundaries and invalid-range refusal. TypeScript and lint pass.
  Remaining report/accounting acceptance and independent sign-off are still open. No deployment.

## Scenario refresh continuation fix — October 19, 2026

- Fixed a live Reporting workflow defect: acceptedJob previously remained pinned after its
  refresh appeared in the durable register. A later refresh then appeared to be a missing
  outcome forever, blocked new submissions and kept polling/displaying the old job.
- Acknowledged requests now release that local pin and follow the latest durable refresh.
  A terminal accepted job also releases it when a newer register row is dated at/after that
  job's completion, handling a completed refresh skipped between polls. Timestamp ordering
  compares instants, not lexicographic strings with potentially different offsets.
- Focused checks cover repeat refreshes, reopened in-flight work and a skipped terminal
  outcome followed by newer work. Existing backend authorization and row-version guards remain.
- Code review confirms variance_between_closes has prepare/replay/presentation and retained
  binding support. Its remaining business acceptance must not be described as absent code.
  Independent accounting acceptance and other release gaps remain open. No deployment.

## Deal product selection — October 19, 2026

- Replaced manual product-code entry with the shared searchable combobox. Choices show code
  and name, include only active products, and follow the complete catalogue pagination.
  Every deal line must have an explicit valid selection before preview submission.
- Added catalogue loading/empty/refusal retry states. Product lookup runs only for new proposal
  entry; reopening retained evidence does not require current product catalogue availability.
  Start over clears selections and network retry retains the selected products.
- Four focused selector/submission/pagination checks pass; TypeScript and ESLint pass.
  Real browser/Tamsin accounting acceptance and independent sign-off remain open. Report gaps
  still require the broader implementation/evidence review. No deployment; main-only publication.

## Scenario draft save UI — October 19, 2026

- Preview detail now advertises save_allowed only for an unsaved preview in an active registered
  scenario where the caller holds entity-scoped contract.create. The save command still locks
  and rechecks the scenario and preview; the read flag is not an authorization token.
- SF-18 exposes external-ID entry and Save as scenario draft only when eligible. Keeps input
  through network errors, uses the common idempotent command flow, invalidates preview/contracts,
  and presents the saved draft link after save or on reopening. Start over is blocked during save.
  Copy distinguishes current-reference draft calculation from retained preview evidence.
- Six focused frontend tests and two real scenario/production API journeys pass, including
  eligibility before/after save and production refusal. Python/TypeScript checks and lint pass.
- Product picker and real Tamsin/browser acceptance remain open; independent accounting sign-off
  is not obtained. Other report acceptance/implementation gaps remain under the broader goal.
  No deployment; changes go directly to main.

## Scenario-only deal preview save API — October 19, 2026

- Added POST /deal-previews/{id}/save. Requires an ACTIVE registered scenario whose current
  sandbox is the caller's workspace; production, ordinary sandboxes and stale scenario targets
  refuse with DEAL_PREVIEW_SAVE_NOT_ALLOWED. The scenario row stays share-locked through commit.
- Locks the preview, verifies saved input/result fingerprints, rechecks scenario entity access,
  and creates a normal DRAFT contract with contract.create validation, provisional computation,
  combination suggestions and holds. Updates saved_contract_id once and records the save audit.
  The original preview evidence is unchanged; the draft uses current reference validation.
- Real scenario/API checks pass first save, same-key replay, new-key duplicate refusal and DRAFT
  status; the production journey passes the explicit 409 refusal. Python types/lint and generated
  API schema pass. The UI save action and independent accounting acceptance remain open.
- Reporting correction from current code: Actual vs Forecast already has a registered builder,
  retained-source capture/rebuild, comparison calculation and UI entry. Populated K11 remains an
  acceptance gap, not an absent report implementation. K03/close-variance gaps still need specific
  code/evidence review before classification. No deployment; direct main publication.

## Deal revenue period matrix and chart — October 19, 2026

- Added per-product/per-period revenue matrix, period totals and all-period product/grand
  totals to SF-18. Entity/currency scopes are selected separately within each book; obligations
  for the same product aggregate while unassigned subjects retain their own identity.
- Added signed revenue bars with exact labels and an accessible table. Twenty-four periods
  display per page; page changes retain all-period totals and a fixed chart scale, and changing
  entity/currency resets the page. Awaiting-trigger balances are explicitly outside the schedule.
- Decimal-string totals use scaled BigInt arithmetic; only bounded chart ratios become Number.
  Grouping indexes rows once instead of repeatedly scanning the schedule for every matrix cell.
- Four focused calculation/render/pagination checks pass, including large signed amounts,
  mixed decimal precision, separate entity/currency scopes and cross-page totals. TypeScript
  and ESLint pass. Scenario save, product picker and Tamsin/browser acceptance remain open;
  populated K11, multi-contract K03 and close variance remain Reporting priorities. No deployment.

## Deal preview page — October 19, 2026

- Registered SF-18 at /contracts/deal-preview, enabling the existing Contracts list entry.
  Scoped users can enter existing/proposed customers, entity, start date, multiple product
  lines, decimal quantity/price, optional term and performing entity; currency follows entity.
- Asynchronous submission retains the job ID in the URL for reload/reconnect. Saved previews
  also open by preview ID. Result tables show per-book allocations, SSP bounds/range, weights,
  adjustments, indicators, scheduled/awaiting-trigger totals and entity/period revenue rows.
- Includes permission gating, input retention after network errors, retry controls, invalid-link
  handling and start-over confirmation. No contract creation or scenario-save button is implied.
- Nine targeted page/result/permission checks pass; TypeScript and ESLint checks pass.
  Scenario save, product-picker polish, revenue chart/period totals and real browser/accounting
  acceptance remain open. K11, multi-contract K03 and close variance remain Reporting priorities.
  No deployment; main-only publication.

## Deal preview report presentation — October 19, 2026

- Detail reads now expose typed allocation rows, SSP bounds/range position, selected SSP,
  weights and adjustments, per-book transaction/allocation totals, material-right and variable
  consideration indicators, and revenue grouped by entity/period/subject. Only REVENUE
  schedules contribute; billing and costs are excluded. Currency precision comes from retained
  input evidence and all displayed money remains decimal strings.
- Scheduled and awaiting-trigger totals explain previews whose revenue schedule is empty.
  Projection uses hash-verified saved evidence, without resolving current configuration again.
  OpenAPI and frontend types are regenerated.
- Reporting remains a development priority. This completes only the result data layer; SF-18
  screen, scenario save, actual-versus-forecast populated K11 and multi-contract K03/close
  variance remain open. Tamsin acceptance and independent sign-off are also outstanding.
  No deployment; direct main workflow.

## Asynchronous deal preview API and worker — October 19, 2026

- Added POST /deal-previews with idempotent command admission and a reserved preview identity;
  registered DEAL_PREVIEW worker execution. It reloads the active human initiator and current
  grants, uses fenced units of work, checks cancellation and retains the computed evidence.
  Already-retained previews refuse later cancellation; job results carry identity/hash/link only.
- Added scoped GET list and detail. Entity authorization filters before pagination/counting;
  lists return proposal metadata without engine traces, details verify input/result hashes
  and return retained result/pins without exposing the internal input bundle. Both use no-store.
- Migration 0189 adds deal_preview to the job subject constraint. Downgrade refuses while such
  jobs remain. Removed the pending-handler entry and retained registry negative-case checks.
- Real API/worker/database journey passes duplicate-request identity, successful USD 120000.00
  allocation, one retained preview, zero production contracts, summary/detail reads and entity
  scope filtering. Five registry checks, Python lint/types and OpenAPI generation pass.
- Scenario save, user-facing allocation/range/indicator projection and SF-18 UI still need
  implementation. Tamsin accounting acceptance, broader release verification and independent
  sign-off remain open. No deployment.

## Immutable deal preview retention — October 19, 2026

- Added retain service under a tenant/preview advisory lock. Every attempt rechecks scenario
  permission and entity currency. A matching existing record returns only after proposal and
  input/result fingerprints verify; reuse of an identity with changed input is refused.
- First execution resolves the scratch bundle and its reference index, uses the DRY_RUN engine,
  and stores the proposal plus complete engine bundle, full canonical result, both hashes,
  registered release ID and standard pinned_refs. Exactly one deal_preview.run audit is added.
  No commit occurs inside the service; the future worker owns attempt fencing and commit.
- Real database verification passes saved SSP references, exact request retention, repeated
  result identity, one audit and changed-proposal refusal alongside scratch rollback checks.
  Python lint/types pass. No production contract/customer survives the enclosing commit.
- Asynchronous request/worker wiring, authorized read APIs, user-facing result projection,
  scenario save and SF-18 UI remain unimplemented. No deployment or accounting-signoff claim.

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
