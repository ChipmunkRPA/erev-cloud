# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Approval availability and access-admin alerts — October 7, 2026

- Previous goal turn made progress: B1-12 was tested and pushed directly to main as `ab4fa7d`.
  Continued from that clean commit. B1-15 is now implemented and verified for direct publication.
- Fail-first tests reproduced no alert when only the preparer held the approval permission and
  the absence of queue availability. Submission/next-step activation now emits APPROVAL_UNASSIGNED
  to active direct role.manage holders covering every entity. Its title/body contain no accounting
  summary or amounts. Revision 0138 adds the kind; preferences default to app/email with existing
  deduplication and sandbox restrictions. Preference input length follows the enum's actual size.
- API assignment_blocked is computed from current eligibility using the same logic as assigned
  recipients: preparer/prior-decision exclusions, delegation, subject rules and later-step
  reservations. It is separate from routing flags and clears after a valid grant is restored.
  Closed requests answer false; content-withheld headers and unsupported subjects answer null.
  Queue/detail display the warning; unsupported subject requests retain their named refusal.
- **43 backend compatibility tests passed** in 36.43 seconds (approval engine, notifications,
  approval API and preferences). **8 notification tests passed** in the final 5.55-second run, including
  entity-specific and all-entity admin scope and redacted alert content. Initial compatibility
  caught the unsupported-subject read and old 12-kind input cap; both were fixed and reverified.
- **79 frontend tests passed** in 3.04 seconds, including queue/detail visibility, preferences
  and notification panel. TypeScript and ESLint pass. **5 migration checks passed** in 16.22
  seconds (full up/down/up and lint). Unit/architecture run: 504 passes and one obsolete enum
  count assertion; corrected count and all 245 affected unit/schema checks passed in 4.08 seconds.
  Mypy: five source files clean. Logs: `/private/tmp/approval-availability-*.log`.
- Final approval API recheck: **20 passed** in 34.03 seconds. A caller who can decide already
  proves availability, so the queue avoids another recipient search for those rows. Alert titles
  include the request reference so the email (which omits the in-app body) can identify it.
- The extra scope test first tried changing a grant in place; PostgreSQL correctly refused it.
  The fixture now revokes the old grant and inserts the scoped replacement; product rules unchanged.
- Independent full-backend baseline remains live on `7c9b22d`, PID 36126 / session 28842, separate
  DB `erev_rv_waivers`, around 30%, with earlier failures. Preserve it until terminal diagnostics.
  It does not cover B1-11, B1-12 or this work. No full-backend pass or production-readiness claim.
- Remaining LIMITS and independent accounting sign-off are still open. Main-only workflow,
  research-folder exclusions, noncommercial license and no-deployment scope remain in force.

## Approvals-gate waiver sequencing — October 7, 2026

- Continued on main `88de370`. Reproduced B1-11 with two failing decision-order cases;
  five controls already passed. A pending approvals-gate waiver now retains its submitted
  request identities while other requests complete. Final approval refreshes the gate under
  the existing locks and requires the live pending population to be a subset of that scope.
- New or replacement pending requests still void the waiver, including at the same count
  and without a cockpit refresh. Renewal reviews the new scope. If all requests complete,
  the gate passes and the unneeded waiver is voided. Other gates keep strict pending-basis
  checks. Rejection/voiding clears the temporary basis; approval retains reviewed coverage.
  Existing JSONB storage suffices; no migration or historical lock rewrite.
- **56 PostgreSQL close/lock checks passed** in 235.98 seconds, including all 18 waiver
  cases and seven new sequencing controls. **678 close-unit/architecture checks passed**
  in 171.83 seconds. Source Mypy, Ruff lint/format, whitespace and design checks pass;
  secret scan: 3,391 files, zero findings. B1-11 is closed for completed-request sequencing.
- GitHub has no open PRs and only main. Automatic merge and merged-branch deletion are
  enabled. Following the owner's instruction, this tested change goes directly to main.
- The separate backend run remains live on `7c9b22d` (about 20% through), excluding parity,
  answer-key and performance markers. It does not cover this change and is not a completed
  passing gate. Other limitations, specialist verification and accounting sign-off remain.
  Archived the mandatory-product section verbatim. Repository only; no deployment.

## Estimate FX approval drift — October 7, 2026

- Continued from main `252c5d9`. Reproduced B1-7: EUR 46,000 was routed with one reviewer
  at USD 49,910 (1.085), then the same request approved after a rate of 1.09 made its impact
  USD 50,140. The unpublished-rate and unchanged-rate controls already passed.
- Final estimate approval now repeats its dry run and compares current functional amount,
  currency and threshold flags with the stored request before any version/event changes.
  Drift uses the existing stale-request rollback/void path: the version is WITHDRAWN and a
  fresh submission routes the Controller step. No accounting expectations were changed.
- A tenant-specific transaction gate prevents an FX publication between that check and posting.
  Estimate submission/final approval take its shared side before group/contract locks; FX
  publication takes its exclusive side before mutation and group/period hooks. It covers new
  rate sets as well. Current routing reads also include a committed publication whose application
  timestamp is later than the decision transaction's start. Historical bundle reads keep their
  time cutoffs. Automatic approval inside submission holds the gate too; a stale refusal there
  rolls back the submission. The final dry run adds work; no full-volume latency claim is made.
- **53 PostgreSQL workflow checks passed**: 51 across the complete estimate, FX-reference and
  rate-change-after-lock files, plus the linked J-06 modification journey and its K-03 report.
  Six new CTL-013 cases cover the threshold crossing, unpublished and unchanged controls, both
  ordering races observed waiting in PostgreSQL, and a publication overtaking an earlier-started
  decision. A refused request appends no estimate event; resubmission needs the Controller and
  applies once. The original J-06 monetary assertions remain intact.
- **273 architecture/routing-unit checks passed**. Four-source Mypy, Ruff lint/format, whitespace
  and design checks (500 files) pass. Control markers validate (440 tagged tests); secret scan:
  3,391 files, zero findings. B1-7 is closed in LIMITS, with the lock and API behavior documented.
- The broader backend run is still live on detached `ed6ea75` with its separate loopback database;
  it excludes specialist markers and does not cover these later changes. Full-backend/specialist
  verification, remaining limitations and independent accounting sign-off stay open. Publication
  exclusions and noncommercial licensing are preserved. No deployment.

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
