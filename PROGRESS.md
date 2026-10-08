# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Estimate monetary reconciliation — October 7, 2026

- Continued from clean main 2b1c477. The prior turn published contract price/provenance
  checks (progress). Added estimate imports to the transactional read-back gate.
- Reconstructs scalar money values, rates, quantities, amortization months, typed parameters
  and full scenario rows from validated source rows. Compares the stored version plus
  contract/element identity, kind, method, currency, direction, allocation target and obligation.
  Scalar columns use their database precision; JSON scenarios retain their decimal precision.
  Source rows, not the emitter's altered plan body, supply the expected financial inputs.
- New-element defaults follow the existing command. Existing elements inherit omitted
  settings; explicit file settings still must agree. A regression preserves an existing
  INCREASE direction when the new version's file omits it, avoiding an unintended change
  to the established existing-element import behavior.
- Tests inject changed constrained amount, changed refund parameter, offsetting scenario
  amounts with unchanged aggregate, and a rebate direction flipped to INCREASE after approval.
  Each leaves a blocking mismatch with no estimate element/version or source lineage committed.
  Valid imports retain matching evidence, scenario zero and default contract currency.
- Initial existing end-to-end witness: **1 passed in 15.78 seconds**. Expanded workflows plus
  layer/import-cycle checks: **53 passed in 39.53 seconds**, /private/tmp/estimate-reconcile-complete.log.
  Final inherited-setting and full financial workflow rerun: **7 passed in 31.16 seconds**,
  /private/tmp/estimate-reconcile-inherited.log. Source Mypy and Ruff/format/whitespace pass.
  All runs terminal; no whole-backend pass claimed.
- B1-19 and developer guidance retain legacy monetary readers as incomplete. Integration-owner
  fallback notification, AI, broader verification, other documented gaps and independent
  accounting sign-off remain open. No deployment. Publication exclusions/noncommercial
  licensing are unchanged; tested changes continue directly to main.

## Contract monetary reconciliation — October 7, 2026

- Continued from clean main 3577d81; prior turn published SSP read-back checks (progress).
  Added the contract template to the transactional monetary gate for new and replacement
  draft bookings. Reads actual CONTRACT_BOOKED targets bound to the current import.
- Each obligation/product line's price, out-of-scope amount, quantity, unit price and scope
  flag is compared against validated source rows. Contract and payload transaction currencies
  and the source-record identity are checked. Offsetting line errors cannot hide behind a
  matching aggregate total. Verified file-column totals retain the existing IPL-06 check.
- Inspection found that replacement imports omitted upload/source-record provenance even
  though replace_draft already accepts it. They now pass those identifiers, IMPORT origin and
  the import idempotency key; new and replacement bookings share the provenance contract.
- Existing shared commit tests: **14 passed in 40.99 seconds**,
  /private/tmp/contract-reconcile-first.log. New/replacement success and offsetting-error
  workflows plus layers/import cycles/stream-appender architecture: **56 passed in 32.58 seconds**,
  /private/tmp/contract-reconcile-final.log. A 1,000 decrease on one line and increase on the
  other rolls back despite unchanged 120,000 total. No source records, events, lineage or
  calculation children survive; failed replacements preserve the complete previous contract.
  Successful replacements carry their import source. Source Mypy, Ruff/format and whitespace
  pass. All runs terminal; no complete backend pass or deployment claimed.
- B1-19 and developer guidance reflect contract coverage. Estimate and legacy monetary
  readers, integration-owner fallback notification, AI, broader current verification,
  other documented gaps and independent accounting sign-off remain outstanding.
  Publication exclusions and noncommercial licensing remain unchanged.

## SSP monetary reconciliation — October 7, 2026

- Continued from clean main 3e5f9dc. The prior turn published cost/revenue/usage event
  read-back checks (progress). Added CSV SSP values to the transactional reconciliation gate.
- Reconstructs expected entry prices/ratios, currency, business dimensions, value basis,
  quantity unit and complete band sets from validated source rows, independently of the
  emitter's plan body. Reads actual entries/bands for the emitted book version. Missing,
  additional or changed values trigger CONTROL_TOTALS_MISMATCH and roll back the batch.
- Independently derives legacy-range low/mid/high values with wide decimal arithmetic,
  then compares at TY-02 NUMERIC(38,18) precision, including PostgreSQL rounding. SSP numeric
  fields are flattened text, so explicit monetary_checks carry coverage even though
  amount_sums is empty. Bands are grouped by entry without a quadratic scan.
- Existing declarations/scope tests first passed **10 in 33.98 seconds**. Final module plus
  layer/import-cycle checks: **61 passed in 52.11 seconds**,
  /private/tmp/ssp-reconcile-final.log. Tests include valid multi-band entries, deliberately
  changed points and missing bands after approval, batch rollback/no version or source
  lineage, and a derived legacy range with an 18-decimal discount ratio. Source Mypy,
  Ruff/format and whitespace pass. All runs terminal; no complete backend pass claimed.
- B1-19 and the developer guide now reflect SSP coverage. Contract, estimate and legacy
  monetary reconciliation, integration-owner fallback notification, AI, broader current
  verification, other documented gaps and independent accounting sign-off remain open.
  No deployment. Noncommercial licensing and publication exclusions are unchanged.

## Event-import monetary reconciliation — October 7, 2026

- Continued from clean main 257533d. The preceding turn implemented and published invoice
  read-back checks (progress). Extended the existing transaction gate to CSV costs,
  pre-standard revenue and rated usage using an independent reader of persisted events.
- The reader checks contract, event type, effective date and source-record identity as well
  as amount/currency. It reads validated source rows, not the emitter's possibly altered
  plan body. Signed revenue remains signed; absent rated usage amounts stay distinct from
  explicit zero. All declared amount columns of each covered template have a reader.
- Real import tests inject altered amounts or missing target references after approval.
  Every failed batch retains a blocking monetary mismatch but no events, source records,
  lineage or calculation children. Successful imports retain matching source/stored evidence
  and file-column totals. Cases cover cost, negative pre-standard revenue, positive rated
  usage, absent rated amount and explicit zero.
- Final new workflows plus existing cost/usage/estimate/modification and quarantine tests:
  **21 passed in 67.91 seconds**, /private/tmp/event-amounts-final.log. The first run's three
  successful-path assertions expected scientific notation; corrected to decimal strings.
  Its six rollback cases already passed. Source Mypy and Ruff pass. A direct registry check
  confirms all three readers cover their complete declared monetary columns.
- Architecture import/layer checks: **47 passed in 8.95 seconds**,
  /private/tmp/event-amounts-architecture.log. All runs terminal. B1-19 and the developer guide retain
  contracts, SSP, estimate and legacy monetary reconciliation as outstanding, along with
  ineligible integration-owner notification fallback. AI, full current verification,
  other documented gaps and independent accounting sign-off remain open. No deployment;
  publication exclusions and noncommercial licensing are preserved.

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
