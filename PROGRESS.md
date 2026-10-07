# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

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

## Mandatory product disaggregation — October 7, 2026

- Continued from merged PR #26 (`ed6ea75`). The product usability warning is now enforced at
  booking/draft replacement, activation submission and approval, native modification additions,
  and legacy amendment application. Missing attributes name the product and required codes.
  Catalogue drafts remain editable. Bundle components follow the minimum inception of current
  group members, matching the calculation reference date rather than the group's retained old date.
- **108 database workflow tests passed, one existing parity-entry-point skip** across activation,
  native modification, products, bundles, legacy amendments and mixed amendment integration.
  **Five final database checks passed** after the reference-date refinement: booking/activation,
  native additions, legacy quarantine with rollback, dated bundle components and entity-scoped
  modification approval. No expected accounting amounts changed. CTL-028 tags cover the new
  activation and modification witnesses; B1-16 is closed in LIMITS.
- **267 architecture checks passed** during the change. The final focused run passed **194 tests**
  (147 unit checks plus 47 layer/import-cycle checks). Final source Mypy, Ruff, whitespace and
  design checks (500 files) pass. Initial test failures were fixture expectations/setup: error
  rule/status, a second contract's legitimate combination suggestion, legacy replay prerequisite,
  and the unmapped-product unit's newly required empty-setting/group-date context. They were
  corrected without weakening the existing controls.
- The broader backend run remains pinned to `ed6ea75` in a detached checkout and a dedicated
  loopback database, with passing tests and the existing expected Q11 failure. It is still live,
  not a completed gate, and does not cover this later change. Full-backend/specialist verification,
  other release limitations and independent accounting review remain open. No deployment.

## FX layer index under RLS — October 7, 2026

- Continued from merged PR #25 (`7b4eb69`). The index audit reproduced an existing 0131 schema
  defect: `layer_key` followed `book_code`, whose enum equality is not leakproof under RLS.
  Revision 0136 moves the enum to the final key, preserving the tenant/contract/layer prefix.
  Accounting data, grants and policies are unchanged; downgrade restores the prior key order.
- **17 PostgreSQL checks passed**: complete migration downgrade/upgrade, schema lint, all index
  condition checks and database-doctor checks, including a clean migrated catalogue. Ruff and
  whitespace checks pass. The earlier recorded FX-index finding is resolved; this establishes
  index-key eligibility under policy, not a full-volume performance result.
- Close-task and modification controls are merged; older dated evidence is archived below.
  Full-backend/specialist verification, other release gaps and independent accounting review
  remain open. No deployment.

## Close task sign-offs — October 7, 2026

- Continued from merged PR #24 (`383ef03`). Manual task signing now enforces the template's
  owner role for the period's entity, in addition to permission and MFA. Closed/permanently
  locked periods refuse new signatures. Signing locks the template as well as the item.
- An approved reopen resets passed manual tasks to NOT_STARTED and clears the current signature
  pointer, with an audit event linked to the reopen request. Immutable historical signatures stay.
  A fresh signature binds the close cycle and owner role; revision 0135 permits that history while
  preserving uniqueness for other sign-off subjects. A lossy downgrade explicitly refuses.
- **60 database checks passed across scoped runs**: 53 close/cockpit/waiver/lock/transition-drift
  tests, five migration checks (including complete downgrade/upgrade), and two signoff invariant
  checks. The six new workflow cases cover missing/other-entity/exact/all-entity owner roles,
  reopen/re-sign with immutable history, and closed-period refusal. Lossy downgrade refusal is
  verified with the real owner lacking BYPASSRLS; rollback preserves all signatures and forced RLS.
- **33 transition/locking unit tests passed**; source Mypy, Ruff and the 500-file design check pass.
  A stale migration-head test pin was corrected to 0135. No accounting amounts changed. Closed B1-9;
  the other C-6 controls remain open. Existing rows are not rewritten by the migration: task resets
  occur on an approved reopen through the new command path.
- The separate index audit found an existing 0131 index defect: `ix_fx_layer_movement__layer`
  puts `layer_key` behind the non-leakproof `book_code` enum comparison under RLS. This was not
  waived; the next schema fix must reorder its keys and rerun the index audit. No whole-backend
  pass is claimed. Other release gaps and independent accounting review remain open. No deployment.

## Supported overrides in database answer keys — October 7, 2026

- Continued from merged PR #9 (`88bd20b`). The answer-key plan still omitted all policy
  overrides under the October 3 withdrawal, although POL-122 and POL-047 are now supported.
- Plans use the product's supported-key set, native request validation, committed override IDs,
  route permissions and separate preparer/approver personas. Each supported declaration is
  created, submitted and approved after booking and before activation. Unsupported declarations
  retain a named failure alongside numeric mismatches; in-memory runs cannot pass as database
  evidence. No answer-key files, expected figures or oracle hashes changed.
- Real PostgreSQL POS012 now creates both declared POL-122 rows and approval requests, verifies
  independent approval, compares every checkpoint clean and passes the complete key verdict.
  Existing close-job, posting, reversal and journal assertions remain intact.
- Verification: **379 tests passed** (the complete answer-key unit suite plus the PostgreSQL
  POS012 regression; two warnings), Ruff lint/format, whitespace and design checks passed.
  A standalone strict Mypy invocation of test-support files failed with 119 import/typing errors;
  it is not passing type-check evidence. This is targeted verification, not a full-backend run.
- C-12 remains open: default suite selection still uses memory, GT07's nondistinct review mapping
  is missing, and POS117 needs its balance-aging builder and fresh database verification.
  FX transition accounting review and the other documented repository backlog remain open.
  Repository work only; no deployment.


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

## Originating-contract FX layers — October 7, 2026

- GitHub writes recovered. PR #6 merged into main (`5e74ea3`); its temporary branch was removed.
  The next slice connects the scoped policy input to the layer readers. No deployment.
- Liability layers retain the originating contract through ordinary credits and monetary releases.
  Consumption and period-end remeasurement resolve that contract's policy, even when another
  member's revenue consumes the layer through group FIFO. Encoded external identifiers are decoded
  after structural separators, preserving literal escape-like text.
- Mixed-member regressions cover either member's exception, ordinary/encoded identifiers, ASC606
  and IFRS15, and transaction/functional tie-outs. A later-period approval leaves the earlier
  historical period intact. The database regression uses real approval, computation and the real
  close FX pass: GBP 5,400 liability remeasurement is sealed once at the September closing rate;
  repeated passes and a recomputation add no duplicate. COMMAND correctly leaves TIME journals to
  the close pass. The test does not claim the whole close job or all gates were exercised.
- Actual verification: **571 FX, posting and architecture tests passed**, plus **4 PostgreSQL
  FX journal regressions**. Mypy passed for all three changed source files; Ruff lint/format and
  whitespace checks passed. These are targeted checks, not full-backend readiness evidence.
- Both excluded research directories remain absent from tracked files; root ignore rules now
  cover the whole directories, preventing accidental republication of more than just screenshots.
- Known transition defect reproduced locally: EUR 12,000 credited at 1.10 is carried at USD 13,440
  after a monetary January closing rate of 1.12. Returning to historical treatment and fully
  releasing in February recognizes USD 13,200, removes the open layer and leaves USD 240 of
  cumulative FX unreconciled. No accounting treatment has been invented for this transition.
  Public POL-163 creation remains disabled pending its correction, close invalidation checks,
  authoring validation and independent accounting review. C-2 remains partial.

Earlier October 7 policy-isolation and workbench evidence is archived verbatim in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).

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
