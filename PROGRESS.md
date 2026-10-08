# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Combined-group reporting verification — October 7, 2026

- Continued from 2ca9791. Reproduced a combined-group monitor failure on current main
  (one failed in 17.02 seconds). The expectations predated individual persisted FX layers.
  T-CON-18 identifies each billing event, while the former test expected a synthetic contract
  net balance. Group FIFO consumes both September recognitions from the first invoice's layer.
- Corrected monitor expectations using fixture events and the independently stated arithmetic:
  36,000 - 3,202.55 - 3,205.48 = 29,591.97; the other invoice's 48,000 stays untouched.
  Existing contract-level report balances, revenue assertions and duplicate-version checks
  remain. Partially recomputed membership cases check each member's actual current layer.
- Complete module: **17 passed in 89.20 seconds**; Ruff/format/whitespace checks pass.
  Evidence and rationale: docs/release/BACKEND-BASELINE-2026-10-07.md. Seven old baseline
  failures resolved as stale expectations; the other 44 await evidence-based disposition.
  No product/calculation code changed. Published directly to main; no deployment. Broader
  verification, import monetary reconciliation and independent accounting sign-off remain open.

## Older backend baseline completed — October 7, 2026

- PID 36126 is terminal and absent. The uninterrupted isolated run on revision 7c9b22d
  ended with **51 failed, 9,970 passed, 1 skipped, 640 deselected, 3 xfailed in 3h46m**.
  See docs/release/BACKEND-BASELINE-2026-10-07.md for the complete failure inventory and
  local evidence paths. No reset/restart occurred. This older run does not verify current main.
- Next: compare failures with current code, rerun scoped cases, and classify from evidence.
  Monetary import reconciliation and independent accounting sign-off remain outstanding.

## Import row coverage — October 7, 2026

- Continued from published a194ef2. Review of B1-19 found a separate equal-count hole: an
  emitter could return one source row twice and omit another while the commit counted every
  response. New regression reproduced COMMITTED on that invalid lineage before the fix
  (/private/tmp/import-duplicate-lineage-before.log).
- Import commit now rejects unknown or repeated source row identities before recording lineage.
  The failure uses CONTROL_TOTALS_MISMATCH and rolls back target/source records and lineage.
  Existing final row-count accounting continues to include quarantined rows.
- Complete import commit module: **11 passed in 34.04 seconds**,
  /private/tmp/import-row-coverage.log. Mypy for commit.py, Ruff formatting/checks and whitespace
  checks pass. Final duplicate/unknown-row negative cases: **2 passed in 9.32 seconds**,
  /private/tmp/import-row-coverage-negative.log. Both runs are terminal. Published directly
  to main after verification.
- This fixes row coverage, not loaded monetary amounts. B1-19 remains open: actual target
  amounts need template-aware reconciliation, including repeated header amounts and quarantine.
  No production claim, deployment or new PR. The independent older baseline was live at
  3h45m12s (94 percent) with failures on its separate database; preserve it until terminal.

## Integration owner notifications — October 7, 2026

- Migration 0140 adds a nullable tenant-bound connection owner. API creation defaults to an
  eligible creator; explicit null remains unassigned. Owner or entity changes validate active
  membership and integration.manage plus contract.read over every served entity. Empty entity
  scope requires both permissions for all entities. Historical connections remain unassigned.
- A control-total mismatch assigns its new blocking OPEN exception and notifies the eligible
  owner transactionally. Recipient authority is rechecked at delivery; repeated handling of
  the same exception does not invoke notification again. Existing notification preferences
  govern email. No external messages were sent by this work.
- Connection editor supports assigning/clearing an owner, retains unchanged ownership on edits,
  and warns about missing owners. Browsing other members retains user.manage protection;
  self-assignment remains available and server-validated. OpenAPI/types and T-INT-01 updated.
- Six migration checks previously passed. Backend API/reconciliation suite: **20 passed in
  39.92 seconds** (/private/tmp/integration-owner-suite-final.log). Additional scope/downgrade
  and owner security checks: **7 passed in 21.05 seconds**
  (/private/tmp/integration-owner-scope-migration.log). Expansion beyond a scoped owner's
  authority is refused atomically, while replacing the owner permits expansion. A nonempty
  downgrade without tenant context refuses to discard the assignment, and rollback preserves it.
- Negative notification cases cover unassigned, suspended and revoked owners; retry coverage
  counts actual delivery calls independently of the generic ten-minute notification merge.
  Initial revoked fixture used nonexistent status rather than revoked_at; corrected. An existing
  outage test falsely matched "503" in a generated UUID; exact safe-message and whole-response
  secret assertions remain, while the invalid substring test was removed.
- Connection UI: **27 passed** (/private/tmp/integration-owner-ui-tests-final.log), including
  self-assignment and existing editing flows. Initial test used click on the component's
  mousedown-driven options; corrected to exercise its actual selection event. Final TypeScript
  and full make lint pass; whitespace checks pass. All scoped processes are terminal. This
  verified increment is published directly to main, without a PR.
- B1-19 remains open for missing/ineligible-owner fallback and import amount reconciliation.
  Existing owners who later lose authority receive nothing; the exception queue remains the
  documented recovery path. No production readiness claim or deployment. Independent accounting
  sign-off remains outstanding. The older backend baseline PID 36126 was live at 3h41m12s on its
  separate database, with failures; preserve it until terminal. Dated sections moved verbatim to
  docs/release/BUILD-HISTORY-2026-10-07.md to keep this notebook below 20 KB.

## Step 1 lifecycle verification complete — October 7, 2026

- Previous goal turn published sandbox loss/FX comparison as dbb3e57. This continuation closes
  B1-13's remaining listed lifecycle/snapshot coverage; implementation is already on main
  in a40d848. The wider B1-2 remains open.
- New public-API cases: enabling another book or independently applying a later assessment
  makes the earlier request stale/VOIDED with no applied event ids or additional accounting
  changes. Revoking a reviewer's role refuses a decision sent from the previously loaded page;
  the request stays pending and another eligible independent reviewer can apply it.
- Real export/load round trip retains the approved STEP1_EVENT request, identical readable
  impact preview, evidence attached to the request and all three resulting events, and exact
  decrypted attachment bytes. The loaded accounting computation verifies with zero mismatches.
- Initial basis run: two passed; the revoked-reviewer case then found the replacement reviewer
  lacked its required role. Corrected that fixture; authority recheck passed in 17.16 seconds.
  Evidence round trip passed in 18.86 seconds. Final combined checks: **7 passed in 64.90
  seconds**, including API-client, two-book and terminal-decision compatibility. Log:
  `/private/tmp/step1-date-review-scope-evidence-final.log`. Ruff, formatting and whitespace
  checks pass. All scoped runs are terminal and erev_rv_cont is free. This direct-main commit
  publishes verification and documentation; no product code changed in this continuation.
- Existing reopened-period coverage uses valid database state fixtures, not a fresh complete
  certification/reopen workflow. Neither scoped tests nor B1-13 closure establish full-system
  production readiness. Independent accounting sign-off and other release gaps remain open.
  Older baseline PID 36126 was live at 3h20m33s, beyond 50% with failures, on its separate DB.
  Preserve it. No deployment.


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
