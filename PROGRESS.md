# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**





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

## Deal preview authorized bundle assembly — October 19, 2026

- Added deal_bundle booking conversion and assembly: resolve the active contracting entity,
  enforce its scenario.use scope and functional currency, then use existing booking and
  bundle resolution for products, approved SSP, templates, policies and accounting books.
- Internal booking runs in a savepoint under system authority only after authorization. Both
  success and errors roll back temporary contract/group/customer/obligation rows and buffered
  audits; no computation persistence, file write or job enqueue is invoked inside the boundary.
- Proposed lines get stable keys and term end dates. Synthetic booking evidence uses the
  proposal's customer reference and sequence, removing rolled-back surrogate/sequence IDs
  that initially caused repeated-input fingerprints to differ. Calendar overflow is refused.
- Real database verification covers ASC606 allocation of USD 120000.00, repeatable input hashes,
  permission refusal, injected resolution failure and unchanged row/audit counts after commit.
  Python lint/types pass. Sequence allocation may leave harmless gaps after scratch rollback.
- Job/API retention, result presentation, scenario save and SF-18 UI remain unfinished, as do
  Tamsin acceptance and independent accounting sign-off. No deployment.

## Deal preview input and engine boundary — October 19, 2026

- Code inspection confirmed deal preview had only its persisted table, without an API,
  worker, engine adapter or screen. Added proposed-deal/create/save request schemas: exactly
  one customer identity/name, bounded nonempty lines, positive decimal-string quantities,
  nonnegative API money, one currency, strict positive terms and calendar-date input.
- Added pure deal_compute boundary using the complete revenue engine in DRY_RUN mode. It
  rejects multiple contracts or posted ledger baselines, preserves engine refusals, returns
  the full engine result/trace and verifies input/result fingerprints. No database writes.
- Four targeted schema/refusal checks pass. A separate real ASC606 kit-world computation
  confirms two USD 1000.00 allocations, DRY_RUN isolation and both fingerprints; lint/types pass.
- This is the compute foundation, not a working deal-preview feature. Authorized product/SSP
  resolution and bundle construction, retained audited jobs/API, result presentation, scenario
  save and SF-18 UI remain to implement. Tamsin acceptance and accounting sign-off remain open.
  No deployment or production-readiness claim.

## Direct forecast event capture from contract forms — October 19, 2026

- Existing delivery/progress/milestone/cost/return drawers now offer a paginated draft selector
  in sandbox workspaces with tenant-wide scenario.use. Normal approval remains the default;
  selecting a draft explicitly changes the action and explains scenario recording/replay.
- Submission carries forecast_event_set_id to the existing atomic capture endpoint, retains
  contract stream concurrency and evidence validation, then invalidates assumption reads.
  An unavailable selected draft blocks submission; the target is locked while submitting.
  Draft management links to contracts with instructions to select that draft in the event form.
- Ten existing/extended event-drawer checks pass, including the selected target in the request,
  retained-input refresh and forecast-specific success message; frontend types/lint pass.
- Usage/invoice input continues through forecast imports. Effective-date controls on input-set
  metadata, populated comparison/report accounting acceptance, deal preview and independent
  sign-off remain open. No deployment or production-readiness claim.

## Captured forecast input review — October 19, 2026

- Assumption versions now expand a read-only review of captured contract event bodies and
  committed import sources in their retained interleaved application order. Event dates,
  obligations, payloads, comments and evidence IDs remain visible as captured; decimal strings
  are not coerced, rounded or truncated, and text is never interpreted as HTML.
- Contract/import links respect available read permission and use local routes. The page states
  that linked current records may differ from captured version evidence. Empty baselines and
  populated legacy sets without valid sequence evidence are explicitly distinguished.
- Six focused review/lifecycle checks pass, covering interleaving, exact numeric strings,
  literal markup, source links, missing order and baseline handling; frontend types/lint pass.
- Direct event-entry capture UI, effective-date controls, populated report accounting acceptance
  and independent sign-off remain open. Import sources use the existing authorized row viewer.
  No deployment or production-readiness claim.

## Forecast fact import entry and correction continuity — October 19, 2026

- Draft assumption records now link to the import wizard for import.upload readers, carrying
  the selected input-set ID. The upload page reads that set, displays code/name/version/status,
  blocks unavailable or non-draft targets before file upload and lists only backend-supported
  progress_events, usage, cost_events and invoices templates.
- Import creation retains the same forecast_event_set_id. Corrected-file navigation now keeps
  that association alongside template/mode; previously it silently fell back to ordinary import.
  Validation/commit and backend draft/permission checks continue to govern attachment.
- Seven focused import/assumption checks cover the link, displayed target, template restriction,
  publication guard, submitted ID and corrected-file identity. Frontend types/lint pass.
- This supplies forecast fact import authoring through the existing pipeline. Direct business
  command capture, richer input review and accounting acceptance remain open. No deployment.

## Forecast assumption lifecycle controls — October 19, 2026

- Forecast runs now include a lazy-loaded, paginated assumption manager within the existing
  scenario-workspace permission gate. Users can create a draft, rename a saved draft and
  explicitly confirm publication; published and superseded versions remain read-only.
- Shows captured-command/import counts, version/status and publication fingerprints. Empty
  sets explicitly identify baseline publication. Reusing a code invokes the existing backend
  next-version/copy semantics; an existing draft is handled by the server's refusal.
- Updates carry the saved row version. Publication refreshes the shared forecast input cache,
  making the new published version selectable for report runs. Lost responses preserve fields
  and permit idempotent retry; no optimistic publication state is shown.
- Eight targeted manager/forecast checks pass, with TypeScript and ESLint. Business-change
  capture controls, import attachment selection, effective-date editing and richer input review
  remain open; this implements lifecycle management, not the entire assumption authoring flow.
  Reporting accounting acceptance and independent sign-off remain open. No deployment.

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
