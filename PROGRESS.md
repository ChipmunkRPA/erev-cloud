# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Step 1 publication checks — October 7, 2026

- Previous goal turn verified zero open PRs and only main remotely. Direct-main workflow
  remains in effect; the verified Step 1 implementation is included in this direct-main commit.
- Physical 201-obligation case passed (1 in 18.73 seconds), without lowering the obligation
  budget: `/private/tmp/step1-date-review-201-obligations.log`. This proves the functional
  approval path, not a production latency or load guarantee.
- Repository-wide `make lint` passed, including design, licence, secrets, OpenAPI drift and
  migration-head checks: `/private/tmp/step1-date-review-release-lint-complete.log`.
  Two existing formatting failures were corrected in the import-job and AboutDialog tests.
- Event/evidence compatibility: 36 passed, one old subject-list assertion failed. Updated it
  to retain STEP1_EVENT evidence. Evidence-registry plus snapshot-export recheck: 25 passed,
  one genuine pre-existing monetary-comparison gap remains (1.69 seconds). New Step 1
  subject-reference checks passed. Log: `/private/tmp/step1-date-review-evidence-snapshot-final.log`.
- Do not remove that failing drift guard: stored loss_provision_version and fx_layer_movement
  remain absent from snapshot_export.MONETARY_TABLES and sandboxes._monetary_rows. They are
  regenerated on load but omitted from monetary verification. Implement a state comparison
  that handles cumulative state versus incremental movements, with real sandbox coverage.
- Full Step 1/registry/data-model/preparer/evidence compatibility passed: **93 in 486.28
  seconds**, `/private/tmp/step1-date-review-final-compatibility.log`. Source Mypy passes
  all six changed backend modules. Terminal-decision/mixed-batch regression: **1 passed in
  16.56 seconds**, `/private/tmp/step1-date-review-terminal-decisions.log`: reject/withdraw
  change no accounting state; resubmission applies once and repeat approval is refused. All
  current scoped runs are terminal; erev_rv_cont is free. Older baseline PID 36126 was verified live at 3h00m54s
  on its separate DB with failures; preserve it.
- B1-13 remaining scope/evidence/snapshot coverage, broader B1-2 producers, full-suite failures and
  independent accounting sign-off remain open. No deployment or production-readiness claim.

## Performing-entity Step 1 review — October 7, 2026

- Previous goal turn made progress with draft-gate review and 5 backend/59 frontend checks.
  Continued local unpublished work on main `5ca602f`; added real cross-entity API verification.
- AVM-US contracts the subscription; AVM-OPS performs it in USD. With both periods open,
  the assessment applies immediately. With only AVM-OPS in soft close, it waits for approval
  while the owner's period remains open. Locking AVM-OPS's period produces a retryable
  conflict without changing the stream, ledger or hold; retry applies reviewed postings.
  The ledger comparison retains entity, book, account role and debit/credit, and equals the
  retained preview amounts. **2 passed in 22.88 seconds**:
  `/private/tmp/step1-date-review-performing-entity.log`.
- Performing-period-change case: **1 passed in 17.33 seconds**. Canceling the performer's
  close after submission makes approval stale and leaves the stream, ledger and hold unchanged.
  Log: `/private/tmp/step1-date-review-performing-period-change.log`; primary DB erev_rv_cont
  is available. Approval authority continues to use contracting/group entities as accepted
  subject-scope rules require; this work checks posting windows for performers.
- Source changes were unnecessary for the first two cases. Ruff and whitespace checks pass.
  FX/other configuration races, physical large-group performance and final publication checks
  remain open. B1-13/B1-2 and independent accounting sign-off remain open. No deployment,
  publication or readiness claim. Earlier Step 1 implementation evidence archived verbatim.

## Draft Step 1 gate review — October 7, 2026

- Previous goal turn made progress with 77 compatibility checks, API-client verification and
  both SSP publication interleavings. Continued unpublished changes on main `5ca602f`.
- Added before/after contract status to the retained Step 1 preview and readable contract
  status labels to the approval screen. A draft's proposed gate is now visible, including
  Draft remaining unchanged when the existing obligation-budget gate guard withholds it.
- Two new public-API cases cover a derived draft gate and its size-budget boundary. Initial
  tests reproduced missing preview status. Subsequent assertions exposed fixture assumptions:
  draft judgements create no active-contract hold, and counting every job includes unrelated
  jobs. Corrected the expected event list and scoped the no-deferral assertion to CONTRACT_COMPUTE.
- Frontend: **59 passed in 2.92 seconds**; source Mypy, TypeScript, ESLint, Ruff and whitespace
  checks pass. Backend compatibility: **5 passed in 39.64 seconds**, covering draft outcomes,
  two-book/API-client decisions and existing immediate-append budget behavior. Log:
  `/private/tmp/step1-date-review-draft-gate-compatibility.log`. Primary test DB erev_rv_cont
  is free. Lowering the budget exercises the boundary, not real-volume performance.
- Actual performing-entity behavior, FX/configuration interleavings and physical large-group
  performance remain open, along with B1-2's other producers and accounting sign-off. No
  publication/deployment/readiness claim. Earlier preview notes archived verbatim.

## Atomic Step 1 computation — October 7, 2026

- Previous goal turn made progress: all-book previews and 13 backend/58 frontend checks.
  This turn reproduced deferred approval: with the fact-capture obligation budget forced
  below the group size, the request approved while its book still had the old ACTIVE state.
  Regression: **1 failed in 14.28 seconds** (`step1-date-review-deferred-regression.log`).
- STEP1_EVENT now computes successfully inside the approval transaction, without the ordinary
  fact-capture deferral budget. It compares the actual persisted-event input bundle with the
  previously validated proposal before running the engine. Only SYSTEM append attribution,
  recorded time and assigned record sequence are normalized for this comparison; actual event
  order and accounting inputs remain checked. The unmodified actual bundle is computed and
  persisted with its normal hash. Other event approvals retain their existing computation path.
- Failed calculation rolls back approval, events and hold releases; changed inputs use stale
  approval handling. The single-book, two-book and forced-deferral cases passed: **3 in 30.37
  seconds**. Failure/late-input boundary checks passed: **2 in 23.63 seconds**, including a
  successful retry after engine failure and unchanged computation count on refusals. Their
  first run only failed the fixture expectation of null instead of an empty applied-id array.
  The late-input test injects an engine-version change; it is not real publication-race proof.
- Source Mypy (two files), Ruff and whitespace checks pass. Expanded compatibility finished:
  **77 passed in 374.20 seconds**, `/private/tmp/step1-date-review-atomic-compatibility.log`.
  API-client case passed: automated submissions still wait for date approval and retain
  non-manual attribution. Both real SSP-publication interleavings passed in **23.96 seconds**:
  before the final input read the decision is stale; after it, actual postings match the reviewed
  amounts. Initial publication probes stopped at the fixture's old session after MFA enrolment;
  using the preparer's current enrolled session fixed the fixture. Logs:
  `/private/tmp/step1-date-review-publication-client.log` (one pass, two fixture failures) and
  `/private/tmp/step1-date-review-publication-interleavings.log` (two passes). All scoped runs
  are terminal; primary test DB erev_rv_cont is available. The older baseline PID 36126 remains
  live on its separate DB with earlier failures. Updated the data-model contract for decisions.
- Remaining: FX and other configuration interleavings, actual performing-entity coverage,
  draft-gate and large-group decision verification, final compatibility and publication checks.
  Synchronous decisions can take longer; no performance claim. B1-13/B1-2 remain open, all
  changes unpublished. No deployment or production-readiness claim. FX evidence archived.


## Constraint review basis — October 7, 2026

- Continued from main `72aaa2b`. Reproduced both B1-5 paths: a changed version accepted an
  earlier version's reviewed constraint, and a draft accepted figures edited after review.
  The two new API regressions failed against the prior implementation with HTTP 200 submissions.
- Constraint judgement content now includes the specific estimate version and financial inputs.
  Its existing submitted hash seals that basis; the submission audit retains the figures.
  Estimate submission and approval verify the binding. Editing figures during a pending review
  makes that review stale. No-change attestations retain their existing path; no posted history
  is rewritten. Older unbound pending requests need a fresh review and resubmission.
- The drawer offers a replacement conclusion after the API refuses an outdated review, even
  while the old record remains REVIEWED. API copy and the data-model contract describe the new
  requirement. B1-5 is closed for estimate-version submission/approval; other limitations remain.
- **55 distinct database workflow checks verified across scoped runs**: 26 estimate tests,
  19 judgement tests, two amendment integration tests and eight judgement/estimate/loss report
  tests. Five new CTL-049 cases cover both reuse paths, pending edits with version/contract
  subjects, recorded basis figures, and refusal of an old-release pending request without
  changing its history. Fresh independent reviews restore the ordinary approval path.
- The K-03 report fixture previously reviewed the constraint before creating its target version.
  It now creates the draft first, then reviews and links the record. All original accounting
  expectations are retained. An intermediate rerun also caught a missing fixture import; the
  final eight-report rerun passed. This is scoped evidence, not a green whole-backend gate.
- Architecture verification found PR #27's missing declaration for the authorized, same-tenant
  `product_reference_date` scope entry. Added its explicit reason and developer-guide contract;
  all six scope checks passed. The broader rerun passed **274 architecture/unit checks** and
  caught the changed error copy's stale PRD row; after synchronizing it, that check passed too
  (**267 architecture plus eight focused unit checks verified across these runs**).
- **61 frontend drawer/form tests passed**, including recovery from a refused reviewed record.
  TypeScript, ESLint, Vite build (existing chunk-size warning), source Mypy, Ruff, whitespace and
  design checks (500 files) pass. Control markers validate (434 tagged tests). Secret scan:
  3,391 files, zero findings. Publication exclusions and noncommercial licensing are preserved.
- The broader backend verification remains live in the detached `ed6ea75` checkout and its own
  loopback database. It excludes specialist markers and does not cover these later changes.
  Full-backend/specialist verification, other release gaps and independent accounting sign-off
  remain open. No deployment or external accounting contact.

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
