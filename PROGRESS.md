# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Integration mismatch recipient fallback — October 7, 2026

- Continued from clean main e12dcfd; prior turn published verified FX checks (progress).
  Sync mismatches now prefer the configured eligible owner, then the connection's human
  creator if still an active tenant member with manage/read scope over every affected entity.
  Assign the exception and notify once; do not rewrite connection ownership. No broad role
  broadcast or API-client/system-to-human identifier fallback. With no qualified recipient,
  preserve the unassigned blocking exception for authorized queue review.
- Existing sync/reconciliation tests plus new fallback/priority/deduplication matrix:
  **11 passed in 23.65 seconds**, /private/tmp/integration-owner-fallback-first.log, terminal.
  Added narrowed-creator-scope refusal and updated owner help/missing-owner UI copy.
  Expanded backend/architecture run: **58 passed, 1 failed in 35.08 seconds**,
  /private/tmp/integration-owner-fallback-final.log. The new scoped-role fixture attempted
  a duplicate active assignment. First correction: **11 passed, 1 failed in 25.49 seconds**,
  /private/tmp/integration-owner-fallback-corrected.log: assignment scope is immutable.
  Changed the fixture to revoke then regrant within the failure transaction. Final scoped
  matrix: **12 passed in 25.25 seconds**, /private/tmp/integration-owner-fallback-verified.log.
  All backend runs are terminal; the expanded run passed all 47 architecture checks. Integration settings UI: **27 passed in 3.19 seconds**,
  /private/tmp/integration-owner-fallback-ui.log, terminal. Source Mypy, Ruff lint/format,
  JSON Prettier and whitespace checks pass.
- Source inspection confirmed file uploads deliberately retain uploader visibility; that
  existing rule is preserved. Updated B1-19/developer guidance and archived older amendment
  evidence verbatim. AI, other implementation gaps, remaining release checks and independent
  accounting sign-off remain open. No full-suite/readiness claim or deployment. Preserve
  exclusions and noncommercial licensing; push verified changes directly to main.

## FX import rate reconciliation — October 7, 2026

- Continued from clean main 8667084; prior turn published bundle reconciliation (progress).
  Added an independent FX version reader: compare set/coverage/upload/status, the complete
  entered/derived rate list, pair/type/day/period identity and per-source lineage targets.
  Reconstruct inverse rates with independent decimal arithmetic and 12-place half-up rounding;
  explicit reverse pairs suppress derivation. Period keys resolve closing/average end dates.
- Initial matrix plus existing approval workflow: **15 passed in 31.02 seconds**,
  /private/tmp/fx-readback-first.log, terminal. Covers spot/closing/average, precision,
  explicit inverse and rounding tie; changed rate/currency/day/period/coverage/set, changed
  inverse, missing inverse and missing targets all roll back versions, FX approval requests,
  source records and lineage. Added swapped targets and a multi-version batch (including
  failure of the second version). Expanded matrix, CSV workflows and layer/import-cycle
  regressions: **74 passed in 69.18 seconds**, /private/tmp/fx-readback-final.log, terminal.
  Source Mypy, Ruff lint/format and whitespace checks pass.
- Updated inventory, B1-19 and developer guidance; archived older legacy progress evidence
  verbatim. Listed financial CSV and legacy readers now have defined scope, not a claim of
  full accounting coverage. Integration-owner fallback, AI and other implementation gaps,
  remaining release checks and independent accounting sign-off remain open. No deployment
  or full-suite/readiness claim. Preserve exclusions/licensing; push verified changes to main.

## Bundle replacement reconciliation — October 7, 2026

- Continued from clean main 74e3437 (prior turn made verified invoice progress). Bundle
  imports now independently read the full stored replacement and bind each source row to
  its declared component target. Compare bundle/component identity, quantity, split basis/
  ratio, sequence and effective windows; derive the next-set end boundary from source rows.
  Reject missing/extra targets or stored components. A mismatch restores the previous list.
- Added a PostgreSQL replacement matrix: high-precision and omitted/default fields succeed;
  changed quantity, ratio, component, bundle, date, sequence, missing target and extra row
  must fail with CONTROL_TOTALS_MISMATCH and leave no new source records/lineage.
- First run: **1 passed, 9 failed in 21.61 seconds**, /private/tmp/bundle-readback-first.log.
  The new fixture used 19 decimal places, beyond the command's 18-place input limit;
  corrected it. Second run: **10 passed, 1 failed in 23.40 seconds**,
  /private/tmp/bundle-readback-second.log. Blank CSV cells normalize to null; corrected
  the reader to apply quantity/split-basis defaults to omitted source values. Both runs
  are terminal. Final matrix, CSV workflows and layer/import-cycle regressions:
  **67 passed in 53.00 seconds**, /private/tmp/bundle-readback-final.log, terminal.
  Source Mypy, Ruff lint/format and whitespace checks pass.
- Updated coverage inventory, B1-19 and developer guidance. FX-rate read-back remains next;
  integration-owner fallback, AI, broader implementation/release checks and independent
  accounting sign-off remain open. No full-suite/readiness claim or deployment. Preserve
  publication exclusions/noncommercial licensing; publish tested changes directly to main.

## Invoice quantity and identity reconciliation — October 7, 2026

- Continued from main 2fcf380. Invoice read-back now compares source-line quantities at
  database precision (absent versus zero preserved), contract/obligation/product identities,
  service dates, header dates/cancellation/credit reference, and event contract/date/source,
  obligation, invoice/line references and source-invoice link. Tax roles/types/jurisdictions
  are checked alongside amounts. Expectations come from original validated rows.
- First run: **5 passed, 5 failed in 44.83 seconds**, /private/tmp/invoice-fields-first.log.
  Fixed the new reader's expectation of CSV boolean text versus stored booleans. Expanded
  invoice replay: **18 passed in 64.51 seconds**, /private/tmp/invoice-fields-second.log.
  Final invoice matrix: **28 passed in 98.51 seconds**, /private/tmp/invoice-fields-final.log.
  Includes changed quantities, wrong contracts/obligations/products/references, changed tax
  classifications/dates, credit memos, absent/zero quantities and 18-place database rounding.
  Each injected mismatch rolls back documents/events/source records/lineage/calculation jobs.
  Shared import/template and layer/import-cycle regressions: **75 passed in 84.09 seconds**,
  /private/tmp/invoice-fields-regression.log. All runs terminal. Source Mypy, Ruff lint/format
  and whitespace pass. Archived older late-event evidence verbatim in the build history.
- Updated coverage inventory, B1-19 and developer guidance. FX-rate and bundle readers,
  integration-owner fallback, AI, other implementation/release checks and independent
  accounting sign-off remain open. No full-suite or production-readiness claim. No deployment.
- Confirmed GitHub has no open PRs, only main locally/remotely, and automatic deletion of
  merged branches enabled. Continue testing and pushing directly to main; no new PRs.

## CSV progress and event field reconciliation — October 7, 2026

- Continued from clean main 31e2d1b. Prior turn published legacy modification checks and
  identified additional CSV gaps (progress). Extended the shared event reader to compare
  explicit numeric and identity fields from original validated rows, using wide decimals.
- CSV progress now checks all four event kinds: delivery, return, progress and milestone.
  Reconciles refund amount/currency (absent versus zero), quantity, progress ratio, hours,
  milestone weight/code, obligation, trigger/measure, references, contract/date/source identity.
  The expected event kind is taken from the source row, not the emitter's modified body.
- Usage now also checks quantity, period dates, metric and obligation. Cost/pre-standard
  events bind their obligation; costs also compare purpose, flags, payee and plan. Source
  amounts continue to reconcile to stored events before verified file-column totals are kept.
- Original monetary regression module: **15 passed in 55.28 seconds**,
  /private/tmp/csv-event-fields-first.log. Expanded progress/refund and event-field tests,
  CSV template workflows and layer/import-cycle checks: **95 passed in 180.38 seconds**,
  /private/tmp/csv-event-fields-final.log. Changed refunds, quantities, ratios, hours, weights,
  wrong obligations and missing event targets all roll back without source/event/lineage or
  calculation children. Null/zero refund and rated-usage cases retain their distinction.
  All runs terminal. Source Mypy, Ruff lint/format and whitespace pass; no full backend claim.
- Updated the coverage inventory, B1-19 and developer guidance; preserved older setup
  evidence in build history. Next: FX rates, bundle quantities and CSV invoice quantity/
  contract/obligation checks. Integration-owner fallback, AI, other implementation and
  verification gaps and independent accounting sign-off remain open. No deployment.
  Publication exclusions/noncommercial licensing are unchanged.

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
