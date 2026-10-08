# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Invoice monetary reconciliation — October 7, 2026

- Continued from 644bcfb; the prior turn implemented and published the late-event report
  (progress). Revalidated clean main and B1-19: commit reconciled rows but no stored amounts.
- Added a commit-only template reconciliation callback. CSV invoices/credit memos now
  independently read persisted document totals, signed source lines, positive event amounts,
  tax components and currencies against validated source rows. This runs inside the narrowed
  transaction; any mismatch rolls back the whole batch and raises CONTROL_TOTALS_MISMATCH.
  Loaded monetary_checks retain the expected/stored evidence, with an explicit mismatch
  sentence. Verified file-column amount sums are also compared to validation's source totals.
- Repeated tax rows count once per component and once per logical invoice line. File-column
  totals retain IPL-06 repeated-cell semantics. A two-tax-row fixture verifies a 54,000 invoice
  while the repeated amount column totals 108,000; neither ledger nor document is doubled.
- Three injected emitter defects change source amount, event amount or remove source tax.
  Each leaves FAILED with the blocking mismatch and no events, source documents/records,
  lineage or calculation child. Ordinary signed credit memos retain their existing behavior.
- Invoice plus shared commit modules: **24 passed in 66.78 seconds**,
  /private/tmp/invoice-reconcile-final.log. Final mismatch-copy, repeated-cell and architecture
  checks: **93 passed in 27.81 seconds**, /private/tmp/invoice-reconcile-contracts.log.
  The first invoice-only run passed 9 in 38.61 seconds. Source Mypy and Ruff pass; all runs
  terminal. No full-backend pass or deployment claimed.
- This implements invoice monetary reconciliation, not all templates. B1-19 and the developer
  guide explicitly retain other monetary templates and ineligible integration-owner fallback
  notifications as outstanding. AI, broader verification, other documented implementation
  gaps and independent accounting sign-off remain open. Licensing/publication exclusions
  are preserved; direct-main workflow continues.

## Zero-posting late-event register — October 7, 2026

- Continued from 3705c7c. The previous turn confirmed no open PRs and main as the sole
  remote branch; it made no implementation change. Implemented REG-LATE-NOLINE-1 using
  stored ENGINE LATE_EVENT findings, joined to actual event UUIDs through their dedupe keys.
  New fallback findings pin the primary book. Legacy findings retain the stated primary-book
  fallback; secondary books require their own stored evidence.
- Findings are filtered by entity, book, calendar/period and both finding/event timestamps.
  Closed/resolved status does not erase inclusion evidence. Existing single/cumulative ledger
  attributions suppress additional event rows for the same origin/posting pair. Zero rows do
  not invent ledger lines or effects. Event amount is the explicit payload Money value for a
  single event; it is null for multi-event sets, triggers or events with no explicit amount.
  Column labels explicitly identify revenue/balance amounts posted out of period. Catalogue
  and source-binding declarations name the additional inputs.
- K07 now drives the actual queued import computation. Before that worker, no row is shown;
  after it, the EUR 100,000 invoice is shown with zero effects/line count, uploader and import
  approval. Checks include timestamps immediately before/at finding creation, other periods,
  origin filters and another book. Existing cumulative-attribution and frozen-register tests
  retain their original counts and monetary expectations. CSV keeps event amounts separate.
- Final register/export/provenance/snapshot/source-binding run: **110 passed in 71.39 seconds**,
  /private/tmp/late-register-final.log. Intermediate runs identified missing ReportParams in
  the new test and updated CSV header expectations; both are corrected. Source Mypy and Ruff
  pass. Import-cycle/layer/report-reader architecture checks: **49 passed in 8.86 seconds**,
  /private/tmp/late-register-architecture.log. All runs terminal; no complete backend pass claimed.
- LIMITS B4-7/B3-7 and standing K07 failure are updated. Prior-date balance classification and
  broader secondary-book finding coverage remain limited. One original baseline failure
  remains: the absent AI lifecycle feature. Monetary import reconciliation, other documented
  gaps, full current verification and independent accounting sign-off remain outstanding.
  No deployment. Publication exclusions and PolyForm Noncommercial licensing are unchanged.

## Architecture follow-up — October 7, 2026

- Continued from 906a83e. Full command-route audit plus architecture run: **5 failed,
  263 passed in 169.16 seconds**, /private/tmp/post-import-audit-architecture.log.
  The audit walk passed in 28.52 seconds. Five architecture checks exposed missing
  declarations, a data-model column-order mismatch and an upward kernel/domain import.
- Step 1 approval content now uses a registered SubjectLifecycle.content callback;
  approvals no longer imports contracts to compute the hash. A missing callback refuses
  explicitly. The existing domain function still supplies the exact approved content.
  Sync-total exception assignment explicitly declares no contract IDs: its subject is
  the sync run, not an individual contract. Data-model documentation matches the table's
  owner-membership/entity column order.
- Enumerated the five Step 1 tenant-scope entries with their purposes and the new import
  computation deferral as a stored calculation, not a preview. Documented these boundaries
  in the developer guide. The checks still reject unlisted calls. The preview check's
  own negative-control expectation now includes the new declared call site.
- Final affected architecture modules: **38 passed in 18.74 seconds**,
  /private/tmp/architecture-followup-final.log. Preview negative controls plus actual Step 1
  soft-close approval, book-change staleness, evidence snapshot, performing-entity review,
  draft approval and sync totals: **13 passed in 54.51 seconds**,
  /private/tmp/architecture-workflow-regressions.log. Source Mypy, Ruff/format and whitespace
  pass. All runs terminal. This closes the five new architecture findings; no complete
  backend pass is claimed. The two original baseline failures, remaining implementation
  gaps and independent accounting sign-off remain open. No deployment.

## Post-import computation scheduling — October 7, 2026

- Continued from 3e106e6. AI routes are genuinely absent, so its pending audit category
  remains open. Investigation of B3-7 confirmed CSV commits collect affected groups but
  schedule no computation. A new real import regression failed because no child job existed
  (/private/tmp/import-compute-before.log, 1 failed in 10.27 seconds).
- Successful CSV commits now insert one CONTRACT_COMPUTE child for each distinct affected
  group, linked to the import job and upload. Jobs share the import transaction and dispatch
  after commit. The existing worker computes each group separately; calculation failures
  cannot roll back committed imported events. The period-lock retry carries the parent ID.
- The regression verifies two rows for one contract produce one child and the actual worker
  succeeds. An injected failure after scheduling rolls back both contract and child job;
  an injected worker failure preserves the COMMITTED upload and event. Existing period-pin
  instrumentation forwards the new parent argument, retaining its original race assertions.
- Import commit module plus stream-appender architecture checks: **19 passed in 35.35 seconds**,
  /private/tmp/import-compute-final.log. Transient-error and import period-pin checks:
  **13 passed, 4 deselected in 51.20 seconds**, /private/tmp/import-compute-period-pins.log.
  Final actual lock-race check with exactly-one-child assertion: **1 passed in 43.61 seconds**,
  /private/tmp/import-compute-retry-child.log. Source Mypy, Ruff/format and whitespace pass.
- All runs terminal. LIMITS B3-7 records the scheduling improvement; B1-20 distinguishes
  CSV imports from adapter booking. The zero-posting late-event report (B4-7/K07), general
  dirty-group sweep, monetary import totals, AI feature, broader verification and independent
  accounting sign-off remain open. Both original baseline failures remain unresolved.
  No deployment; publication exclusions and noncommercial licensing are unchanged.

## Tooling revalidation and import cleanup retry — October 7, 2026

- Continued from 09c31ef. Preserved session 71400 and its primary test database until
  terminal. The seven tooling cases passed unchanged: **7 passed in 350.56 seconds**,
  /private/tmp/local-tooling-revalidation.log. Demo fixture setup took 326.84 seconds.
  This verifies missing-demo-password refusal, fixture tamper detection/no writes,
  dependency licensing, Makefile success output, running-stack reset refusal, OpenAPI
  stale/current checks and process start/reuse/stop. Earlier missing-tooling errors do
  not reproduce in this configured checkout. No blanket environment exemption added.
- The import failure test expected settlement to finish despite a held upload. Current
  required-hook behavior deliberately rolls back settlement on cleanup failure. The
  test now checks COMMITTING/RUNNING while held and retries after release, requiring
  FAILED/FAILED plus one IMPORT_PROCESSING_FAILED item. Already committed uploads
  remain committed, and each job emits one job.failed log; the held case logs its
  initial hook failure. Production code is unchanged.
- Full import failure-hook module: **4 passed in 15.88 seconds**,
  /private/tmp/import-failure-cleanup-verified.log. Ruff/format and whitespace checks pass.
  All processes terminal. Eight original baseline failures resolved; four remain:
  close waiver freshness, pending AI audit category, modification audit report expectations,
  and the late-billing out-of-period report. Current full-backend verification and
  implementation gaps remain open, as does independent accounting sign-off. No deployment.

## Outstanding release verification

These checks need current release-candidate evidence. Historical October 3 results
remain in the dated build history; they do not verify current main. This list does
not authorize deployment, provisioning or changes to a live database.

- SUPERVISOR VERIFICATION NEEDED: make audit-deps
- SUPERVISOR VERIFICATION NEEDED: make docker-build
- SUPERVISOR VERIFICATION NEEDED: make compose-verify
- SUPERVISOR VERIFICATION NEEDED: make zap-baseline
- SUPERVISOR VERIFICATION NEEDED: make tf-validate (validation only)
- SUPERVISOR VERIFICATION NEEDED: make backup, make restore-verify (isolated local drill only)

## Older backend baseline completed — October 7, 2026

- PID 36126 is terminal and absent. The uninterrupted isolated run on revision 7c9b22d
  ended with **51 failed, 9,970 passed, 1 skipped, 640 deselected, 3 xfailed in 3h46m**.
  See docs/release/BACKEND-BASELINE-2026-10-07.md for the complete failure inventory and
  local evidence paths. No reset/restart occurred. This older run does not verify current main.
- Next: compare failures with current code, rerun scoped cases, and classify from evidence.
  Monetary import reconciliation and independent accounting sign-off remain outstanding.

## Policy approvals serialized with period locks — October 7, 2026

- Continued from PR #8 on main (`9c5556f`). Policy overrides do not append a contract event,
  so the existing event-appender period pin did not protect their approvals.
- Approval of an override on a non-draft contract now shares the close-window rows of all
  contracting/performing entities under tenant scope, after taking the group/contract locks and
  before publishing approval or supersession. Draft contracts have no frozen calculation and skip
  this control. The new scope entry is explicit in the architecture allowlist and developer guide.
- The pending-approvals gate ordinarily prevents a lock while a policy decision is outstanding.
  The regression uses the real **approved waiver** of that gate to exercise the permitted close
  path. When policy approval comes first, the lock waits, then refuses the committed dirty group.
  When the lock comes first, a later approval waits and can commit after it. When a lock overtakes
  an already-started policy decision, the stale approval is refused with `PERIOD_STATE_MOVED`;
  no approval audit or dirty mark is kept, the override remains submitted, and a retry succeeds.
- Counterfactual verification in an isolated test process bypassed only the new check: the stale
  policy decision returned **200 APPROVED** after the newer lock, where the regression requires
  409. With the check enabled, all three real PostgreSQL race cases passed. An earlier observation
  without a waiver proved lack of waiting but the ordinary pending gate still prevented locking;
  it is not evidence of a completed inconsistent lock.
- Actual verification: **26 policy and PostgreSQL window/race tests passed**, including the three
  new cases; **267 architecture tests passed**. Mypy passed both changed source files; Ruff
  lint/format and whitespace checks passed. These are targeted checks, not full-backend evidence.
- The economic treatment of FX classification transitions remains pending independent accounting
  review; public POL-163 authoring stays disabled. Repository completion only; no deployment.

## FX transition refusal and close-policy inputs — October 7, 2026

- PR #7 merged into main (`dc1c116`). Current work continues from that revision; no deployment.
- Added the missing functional-layer validation before a calculation can emit output. A fully
  consumed layer must carry zero; an open historical contract-liability layer must carry its
  remaining original historical basis. Positive and negative residues, partial releases and no
  release all refuse with the layer, period and expected/actual amounts identified.
- The reproduced monetary-to-historical defect is now blocked, **not implemented as a supported
  transition**. A PostgreSQL regression verifies the refused recomputation leaves the previous
  calculation head and journal lines intact and keeps the group dirty. Public POL-163 authoring
  remains disabled pending reviewed transition treatment and remaining approval/close validation.
- Close-run policy digests now include effective contract exceptions through the same period-scoped
  resolver used by bundles, under tenant scope. Drafts, same-value approvals, approvals after the
  entity-local period end and IFRS-forced treatment do not alter the digest. Existing digests are
  unchanged when no exception differs from the entity default.
- A real database close job records the old inputs, an effective approval makes its gate fail,
  and the next close job recomputes and records the new inputs. The prior period remains valid;
  the asset-position fixture needs no monetary adjustment or duplicate journal. Approval/lock
  concurrency still needs focused review; these tests do not certify the whole close workflow.
- Actual verification: **578 FX engine, posting, property and architecture tests passed**;
  **22 database and close-input unit tests passed**. Mypy passed both source files. Ruff lint,
  formatting and whitespace checks passed. No full-backend or production-readiness claim.
- Added `docs/release/ACCOUNTING-REVIEW.md` with the measured case, required decisions about
  correction versus a change in refund rights, economic timing, basis/rates and closed periods,
  and a pending independent-sign-off record. Reviewer identity was requested; no external contact
  or accounting sign-off occurred. This packet is not an approval.
- Earlier continuation entries were moved unchanged to the dated build history to keep this
  notebook below 20 KB. Publication exclusions and PolyForm Noncommercial licensing are retained.

## Public repository publication — October 5, 2026 (America/Los_Angeles)

- Owner requested public publication with commercial use prohibited. Prepared the supplied directory
  snapshot for `https://github.com/ChipmunkRPA/erev-cloud`, using PolyForm Noncommercial 1.0.0.
- Updated LICENSE, NOTICE, bundled web copies, Python/npm package metadata, README and About dialog.
  Third-party notices remain intact. Previously granted MIT rights are not revoked.
- Excluded the entire `research-harness/` and `docs/research/` directories at the owner's explicit request; retained application
  source, fixtures, screenshots and documentation. See `docs/release/PUBLICATION-2026-10-05.md`.
- Actual validation: locked `npm ci --ignore-scripts --no-audit --no-fund`; AboutDialog vitest 4/4 passed;
  frontend Vite production build passed (existing large-chunk warning). `python3 scripts/secrets_check.py`:
  4,053 files scanned, 8 allow-listed, zero findings and zero unused entries before this note.
- Additional redacted Gitleaks scan reviewed: test constants, placeholder JWT, accounting identifiers
  and historical test references; research-harness findings removed with the entire directory.
  Targeted credential-pattern scan found only intentional self-test fixtures. These are targeted
  publication checks, not a full security audit. No generated dependencies or real environment/state
  files are staged.
- Backend/integration/accounting suites were not rerun for this licensing/publication change. Earlier
  results below remain historical. No deployment or cloud mutation; production/accounting blockers
  in LIMITS-1.0.md remain. Publication supersedes the earlier private-only instruction in this notebook.

### Publication correction — October 5, 2026

- Removed the entire research-harness and docs/research directories from the publication and replaced the initial root
  commit, so main has no ancestor containing those files. Used an exact force-with-lease against the
  previously verified remote commit. No application code changed; application tests were not rerun
  for this directory removal. External clones and GitHub cached/unreachable objects cannot be recalled
  by a branch rewrite alone.

### Public report website cleanup — October 5, 2026

- Scanned the repository for website references and reviewed documentation matches. Removed 155
  external website URLs plus bare domains across 12 documents and removed the design source
  bibliography. Kept explicit citation-removal markers, mandatory third-party notices, dependency
  metadata and operational endpoints. This does not revalidate the remaining historical prose.
- Follow-up documentation URL scan found only owner links, internal/example addresses and a local
  URL-validation regex. `git diff --check` passed. No application source changed; no application
  tests rerun. Replaced the public root with an exact force-with-lease against the verified head.

## Historical release record

The earlier build-loop notebook is preserved in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).
Current outstanding implementation and verification gaps remain in
[the release limitations](docs/release/LIMITS-1.0.md).
