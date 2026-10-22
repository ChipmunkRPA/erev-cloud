# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: prioritize finishing missing features. Use targeted checks during development; reserve full-suite verification for feature completion/release. Commit and push directly to main; no new PRs unless protection requires one. No deployment.**

## Current owner-authorized goal — October 21, 2026

Finish the repository for public source publication under its noncommercial license;
prioritize feature completion with necessary targeted validation. Continue directly on main,
review and publish changes without PR accumulation, and do not deploy.

- Reporting priorities remain difference attribution, multi-currency, RPO exemptions and GL
  reconciliation. Combined contracts now retain original receiving-contract aging and separately
  show member allocation adjustments; continue the remaining evidenced Reporting gaps.
- Migration-to-live promotion/replay completion is outside scope; no actual business launch.
- Keep key financial permissions, segregation of duties and audit evidence; full approval
  coverage is not required. Implementation is not a SOX certification.
- Sandbox goal: refresh from production and allow experimentation isolated from production.
  Reproduction of production lock history and sandbox locking are not completion requirements.
- Independent accounting review belongs to the owner and is not a development completion gate.
- Owner resumed development October 21. The app goal tool cannot edit the existing objective
  text; this section records the superseding scope while the goal remains active.

## Legacy journal summary retained reconstruction — October 22, 2026

- New GROSS/DELTA summary runs retain original per-book aggregates, resolved entity/account/key
  labels, window and source line/partition/posting references. Shared pure view calculation
  rebuilds line nets, debit/credit sides, entity balances and currency totals. Bound reruns
  validate tenant/entity scope and mode/book/date selection without current ledger reads.
- DELTA keeps the existing primary-plus-LEGACY convention. Current book-enable validation applies
  to original runs; reconstruction uses their retained inputs. Source membership includes original
  subledger line IDs. Older explicit OPEN bindings keep their original semantics. Migration 0322
  freezes the report IPE; this does not change journal posting or add financial-currency views.
- Necessary verification passed: 18 focused reconstruction/source-binding cases, including
  USD/EUR, same key across entities and sign changes that recalculate debit/credit totals.
  Actual GROSS and DELTA API/worker runs reproduce rows and output hashes. Scoped lint/types and
  migration metadata parity passed. No deployment; final repository verification remains open.

## Legacy contract exports retained reconstruction — October 22, 2026

- Both legacy contract history and latest-contract exports now retain current/predecessor
  obligation-version inputs, original labels and the verified exact trace texts used by the
  71-column format. Shared reconstruction restores source dates/timestamps and reruns the legacy
  column calculations without reading current contracts or trace storage.
- Tenant/entity scope, report identity and date/book/contract selection are checked. Current and
  predecessor obligation IDs are retained as source membership. Exact-text refusals still apply
  when the original run reads its trace; unavailable activity remains explicitly unavailable.
  Older OPEN runs keep their original behavior. Migration 0321 freezes both IPE definitions.
- Necessary verification passed: 32 focused exact-export/source-binding cases, including
  database-free reconstruction, scope refusals and recalculated remaining SSP. Actual API/worker
  runs of both 71-column exports and latest-status reproduce original rows/output hashes; scoped
  lint/types and both metadata checks passed. No deployment. Legacy JE summary, other documented
  gaps and final repository verification remain outside this completed batch.

## Latest contract status retained reconstruction — October 22, 2026

- New latest-status runs retain selected contract-version inputs, original contract/product/entity
  labels, resolved as-of obligation cuts and member/entity balance cuts. Bound reruns validate
  tenant/entity scope and book/as-of/contract selection, then recalculate reported allocation,
  remaining allocation and deduplicated balance totals without live contract reads.
- This is reconstruction from retained resolved cuts, not a new engine computation. The live
  as-of calculation, transaction-currency presentation and legacy export behavior are unchanged.
  Older OPEN runs retain their original live-evaluation behavior. Migration 0320 updates IPE.
- Necessary verification passed: 17 focused source-binding/reconstruction cases and the actual
  16-obligation latest-status API/worker workflow, including identical rerun rows/output hash;
  scoped lint/types and frozen metadata parity. No deployment; remaining documented work and
  final repository verification are not claimed complete.

## SoD conflict retained reconstruction — October 22, 2026

- New runs retain the original scoped conflict population, rule functions, held role permissions,
  delegation permissions/names/end dates and candidate exception approval/revocation/validity
  inputs. Same-source reruns validate tenant/entity scope and as-of selection, recalculate
  conflict predicates and exception coverage, and rebuild rows/totals without live access reads.
- Necessary verification passed: 61 focused access/source-binding cases plus the actual report
  API/worker exception-revocation flow. Fresh reports show an uncovered conflict; saved covered
  and empty runs reproduce identical rows/output hashes. Scoped lint/types and migration 0319
  catalogue parity passed. Original historical-cutoff limits and older OPEN-run behavior remain.
- This preserves selected report inputs; it does not add role-permission history or expand
  approvals. Saved-run access still uses current authorization. No deployment.

## User access retained reconstruction — October 22, 2026

- New runs retain member names/status, role/entity grants, MFA state, last login, grantor,
  revocation timestamps and SoD exception references with the resolved as-of instant. Bound
  reruns validate tenant/entity scope and selection, restore typed members/grants and rebuild
  rows and membership/assignment totals without current identity or access-state reads.
- Necessary verification passed: all 60 focused access/source-binding cases and actual membership
  removal/report API and worker workflow. Fresh reports omit the removed member; the saved report
  reconstructs original grants and identical rows/output hash. Scoped lint/types and migration
  0318 IPE parity passed. Existing ad-hoc historical limitations remain; older OPEN runs keep
  their original behavior. Reading saved runs still requires current report authorization.
- Resolved the three previously recorded stale permission tests: expected inventory now includes
  both composite evidence packs and their audit/contract/export requirements; visibility checks
  distinguish the run-permission split from additional evidence-pack SQL predicates. The entire
  focused access test file now passes. No production permission policy was changed.
  No deployment; other documented Reporting/repository gaps remain.

## Configuration change retained reconstruction — October 22, 2026

- New runs retain configuration subjects, approval requests/decisions, actor identities/names,
  changed-field and test-evidence counts, simulation flags and resolved dates. Bound reruns
  validate scope/filters, restore typed inputs and recompute author/approver separation and
  displayed rows without current source reads. Request membership is captured.
- Necessary verification passed: 56 focused access/source-binding cases and actual configuration
  approval/report API and worker flow. A later rejected SSP request adds a fresh report row;
  the saved report preserves its original three rows and identical output hash. Scoped lint/types
  and migration 0317 IPE parity passed. Older OPEN runs retain new-evaluation behavior.
- Three older permission tests fail because they assume the old report inventory/SQL shape
  (test_the_reports_declare_their_permissions, test_a_declared_permission_is_held_at_its_scope,
  test_a_run_is_visible_under_the_run_permission_of_its_report). All three also fail when executing
  the preceding committed framework, so this feature does not introduce them. They remain an
  explicit verification cleanup item; the full access test file is not claimed green.
  No deployment; other documented Reporting/repository gaps remain.

## Allocation lineage retained reconstruction — October 22, 2026

- New allocations-by-SSP-version runs retain each segment's first/latest obligation-version
  inputs, cause, allocation date and contract-chain number, with version membership. Bound reruns
  validate tenant/entity scope and book/date/SSP selection, then recalculate original or remaining
  SSP lineage, range status, adjustments, currency totals and TOTAL rows without live reads.
- Necessary validation passed: 45 focused SSP/source-binding cases; actual override approval,
  recomputation and report API/worker flow. Fresh allocation rows use the corrected SSP pin and
  override flag, while the saved report reproduces the original allocation rows and identical
  output hash. No-session checks cover chain numbering, amount/adjustment/total recalculation,
  date selection and scope refusal. Scoped lint/types and migration 0316 IPE parity passed.
- All four SSP reports now support retained same-source reconstruction for new runs. Older OPEN
  runs keep their original behavior. This report remains transaction-currency-only as specified;
  the change does not add functional allocation measures. Other documented Reporting/repository
  gaps remain open. No deployment.

## SSP override retained reconstruction — October 22, 2026

- New runs retain obligation/product identifiers, original default/override version labels,
  approval requests/decisions, justification and actor names. Same-source reruns validate
  tenant/entity scope and date filters, restore approval inputs, reapply the approved-date
  selection and rebuild rows without live reads. Request membership is recorded.
- Necessary verification passed: 44 focused SSP/source-binding cases; actual SSP override
  approval/computation/report API and worker workflow. After approval, fresh reports show the
  override while the pre-approval saved report still rebuilds empty; both pre/post approval
  saved reports reproduce original rows and hashes. No-session checks cover labels, reasons,
  actor display, approval timestamps, status selection and scope refusal. Scoped lint/types and
  migration 0315 frozen IPE parity passed. Older OPEN runs retain new-evaluation behavior.
- This report lists version overrides and approval evidence, not monetary allocation amounts.
  Remaining allocation and other documented Reporting gaps remain open. No deployment.

## SSP change-log retained reconstruction — October 22, 2026

- New runs retain version lifecycle/status inputs, effective dates, entry counts, diff summaries,
  successor labels, study filenames, full approval requests/decisions and original actor names.
  Same-source reruns validate tenant/entity scope and filters, restore typed inputs, reapply the
  lifecycle-date selection and rebuild rows without live reads. Source version IDs are captured.
- Approval restoration preserves decision IDs, actor identities, timestamps, flags and amounts;
  no current approval or user lookup is used. Older OPEN runs keep new-evaluation behavior.
- Necessary validation passed: 43 focused SSP/source-binding cases and actual draft SSP/report
  API and worker flow. Removing a draft entry changes the fresh log count from seven to six;
  the saved log reproduces seven and identical rows/output hash. No-session checks cover approval
  display, timestamps, studies, date selection and scope/filter refusal. Scoped lint/types and
  migration 0314 frozen IPE parity passed. Ad-hoc historical mutable-state limitations remain.
  No deployment; remaining SSP and other documented Reporting gaps are still open.

## SSP version diff retained reconstruction — October 22, 2026

- New SSP-diff runs retain the resolved chosen/comparison version IDs and complete entries/ranges
  from both sides. Same-source reruns validate tenant/entity scope and comparison filters, then
  recompute entry classification, exact values, mid-change ratios and totals without live reads.
  Default prior-version selection is resolved once. Older OPEN runs keep new-evaluation behavior.
- Necessary verification passed: 42 focused SSP/source-binding cases; actual draft SSP API and
  report worker workflow. Deleting AVM-PLAT-100 from the draft produces Removed in a fresh report;
  the saved comparison reproduces its original no-difference rows and identical output hash.
  No-session tests verify ratios recalculate when retained values change, removed-entry counts
  and scope/filter refusal. Scoped lint/types and migration 0313 frozen IPE parity passed.
- Ad-hoc historical reads of editable draft entries still require evidence and retain their
  existing refusal. Remaining SSP registers and other documented Reporting gaps remain open.
  No deployment.

## Late-entry retained reconstruction — October 21, 2026

- New runs retain event inputs and import/uploader provenance, entity period boundaries, first-lock
  timestamps and the applied window. Same-source reruns validate tenant/entity scope and filters,
  restore typed values and recalculate both sections and counts without current source reads.
  Older OPEN runs preserve their new-evaluation behavior.
- Necessary validation passed: 39 focused late-entry/source-binding cases; actual K07 close,
  import and report API/worker flow. A newly appended period-end memo appears in a fresh report;
  the saved report reproduces its original rows and identical hash. Pure reconstruction verifies
  both-section membership, window/lock changes and scope/filter refusal. Scoped lint/types and
  migration 0312 IPE parity passed.
- Corrected K07 fixture clock drift: FX preparation unnecessarily advanced the application clock
  two minutes, making the lock appear later than subsequent database-recorded events. Removing
  that advance restores the intended chronology without changing production lock behavior.
  No deployment; other documented Reporting and repository gaps remain.

## Judgement register retained reconstruction — October 21, 2026

- New runs retain judgement source records, subject/actor labels, conclusions, references,
  reviewer timestamps, supersession labels, resolved dates and withheld-population counts.
  Same-source reruns validate tenant/entity scope and book/date/topic/status selection, then
  rebuild typed rows and totals without current judgement, subject or user reads.
- Captures judgement-record membership. Withheld combination proposals contribute only the
  original count, not restricted record details. Older OPEN runs keep new-evaluation behavior;
  ad-hoc historical queries still refuse unavailable mutable-state history.
- Necessary verification passed: 41 focused register/source-binding cases and actual report
  API/worker flow across SUBMITTED-to-REVIEWED approval. Fresh judgement rows show the reviewer;
  the saved run rebuilds the original SUBMITTED row with identical output hash. No-session tests
  cover typed values, names, counts and scope/filter refusal. Scoped lint/types and migration 0311
  frozen IPE parity passed. No deployment.

## Scope exclusion reporting and retained inputs — October 21, 2026

- Reporting now preserves original out-of-scope amounts and adds explicitly labelled equivalents
  at each entity's selected report-period closing rate, with a separate reporting control total.
  These are analytical equivalents, not carrying balances. Missing per-line amounts remain empty;
  shared exclusions are not apportioned. Foreign-contract functional conversion remains refused.
- New runs retain scope amounts, judgement numbers/rationales, source version membership, resolved
  as-of date and reporting rates. Bound reruns validate tenant/entity scope and filters, then rebuild
  typed rows and totals without current source reads. Older OPEN runs keep new-evaluation behavior.
- Necessary checks passed: 40 focused register/source-binding cases, including USD-to-GBP and
  retained reconstruction in all three views; actual BR06 report API/worker flow before and after
  judgement approval. Fresh rows show the new rationale while all three saved views reproduce
  original rows and identical hashes. Scoped lint/types and migration 0310 frozen IPE parity pass.
  Lock-source and ad-hoc historical limitations remain unchanged. No deployment.

## Estimate change retained reconstruction — October 21, 2026

- New estimate-change runs retain selected version inputs, predecessor measures, attributed P&L
  effects, approval actors/timestamps, attachment counts, resolved dates and reporting rates.
  Same-source reruns validate tenant/entity scope and filters, restore typed source values and
  rebuild rows and totals without live estimate, approval, attachment, actor or FX reads.
- Captures estimate-version membership. Older OPEN runs keep their original new-evaluation
  behavior. This supersedes the preceding live-rerun limitation; ad-hoc historical queries still
  cannot reconstruct mutable state without evidence. Foreign-contract functional effects remain
  outside this change; analytical reporting equivalents remain explicitly labelled.
- Necessary verification passed: 37 focused register/source-binding cases (all three currency
  views reconstruct without a database); real K06 approval/report API and worker flows. Replacing
  approved EUR/USD average 1.20 with 1.30 changes fresh P&L equivalents from USD -6,900 to -7,475;
  saved transaction and reporting runs reproduce their original rows and identical output hashes.
  Scoped lint/types and migration 0309 frozen IPE parity passed. No deployment.

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
