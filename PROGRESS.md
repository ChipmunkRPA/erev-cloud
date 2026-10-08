# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

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

## Container probe fixture and release-check visibility — October 7, 2026

- Continued from d44d5c5. Reproduced the container probe and progress-list failures:
  **2 failed in 0.16 seconds**, /private/tmp/release-probes-before.log. On this host,
  files under the scratch root inherit group 0 while the process uses group 20; macOS
  silently removes setgid on chmod. A local probe confirmed mode 0755 before changing
  to the caller's group and 02755 afterward.
- The fixture now assigns its setgid file/directory the caller's group and explicitly
  asserts all privileged mode bits before running the unchanged container probe. The
  probe must still report both privileged files and exclude directories and symlinks.
  Restored the outstanding supervisor-target list below, with historical results kept
  dated and current release-candidate evidence still required.
- Full container-script module plus progress-list check: **20 passed in 15.36 seconds**,
  /private/tmp/release-probes-verified.log. Ruff/format and whitespace checks pass.
  These use Docker stand-ins; no images were built, deployed or certified by this run.
- Two original baseline failures resolved; 12 remain without current-main disposition.
  The seven-case tooling rerun started here completed in the continuation below;
  session 71400 is terminal. Its results supersede this entry's pending status.
  Accounting sign-off and implementation gaps remain open. No deployment.

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

## Migration verification alignment — October 7, 2026

- Continued from 9622f13. Scoped current-main run reproduced two migration-check failures
  (2 failed, 42 passed in 1.56 seconds, /private/tmp/migration-pins-before.log). The task
  signature downgrade test omitted fresh_head; revision 0130's historical transition body
  was incorrectly compared with the current renderer, which includes 0135's reopen pair.
- The downgrade case now starts with a data-free head before creating its own signature
  history. Updated the static walk inventory for this case and the existing Step 1 report
  filter round-trip (the latter already resets correctly). No guard exemption was added.
  Revision 0130 is checked against 0135's literal previous body; the new 0135 check requires
  today's renderer and exactly one added PASSED>NOT_STARTED pair. No migration was rewritten.
- Final verification: **47 passed in 12.62 seconds**, /private/tmp/migration-pins-final.log.
  Includes the real PostgreSQL lossy-downgrade refusal with signature retention and RLS
  restoration, installed transition-function drift check, complete migration-entry/transition
  unit modules and snapshot-export module. The snapshot baseline failure was already fixed
  by dbb3e57 and now has fresh verification. An intermediate run found the missing Step 1
  inventory entry; the final run includes that correction. Ruff/format/whitespace pass.
- Three more original baseline failures resolved, leaving 14 without current-main disposition.
  All runs terminal. This is scoped evidence, not a full migration walk or backend baseline.
  Implementation gaps and independent accounting sign-off remain open. No deployment.

## Portable backup archives — October 7, 2026

- Continued from f9f5683. Reproduced the restore baseline failure: macOS BSD tar adds
  an AppleDouble ._files entry outside the declared files/ root, so restore correctly
  refuses the backup before reaching subsequent checks. The new archive regression
  adds explicit macOS extended attributes and failed against the old script with that
  exact refusal (/private/tmp/backup-archive-regression.log, 1 failed in 1.15 seconds).
- Backup tar creation now sets COPYFILE_DISABLE=1 for that command, suppressing host
  AppleDouble metadata. Restore validation is unchanged. The regression checks exact
  archive members, preserved ciphertext bytes and acceptance by the real archive validator;
  partial uploads remain excluded. The runbook documents the archive contents.
- Complete backup/restore script module: **29 passed in 77.31 seconds**,
  /private/tmp/backup-restore-verified.log. Recovery preflight module: **25 passed in
  0.11 seconds**, /private/tmp/recovery-preflight-verified.log. Bash syntax, Ruff/format
  and whitespace checks pass; all processes are terminal. These scratch-repository runs
  stub database/verification commands; they do not prove a live backup or restore drill.
- All 14 original backup/restore baseline failures are resolved, leaving 17 original
  failures without current-main disposition. Broader verification, implementation gaps
  and independent accounting sign-off remain open. No deployment or cloud changes.

## Older backend baseline completed — October 7, 2026

- PID 36126 is terminal and absent. The uninterrupted isolated run on revision 7c9b22d
  ended with **51 failed, 9,970 passed, 1 skipped, 640 deselected, 3 xfailed in 3h46m**.
  See docs/release/BACKEND-BASELINE-2026-10-07.md for the complete failure inventory and
  local evidence paths. No reset/restart occurred. This older run does not verify current main.
- Next: compare failures with current code, rerun scoped cases, and classify from evidence.
  Monetary import reconciliation and independent accounting sign-off remain outstanding.

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
