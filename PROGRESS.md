# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Evidence-pack download boundary — October 8, 2026 (RPS-16 continued)

- Continued from clean published d558514; previous turn published verified assembly work.
  Found that generic file metadata/content routes could serve evidence-pack files under
  `evidence.export` without the pack-specific source checks and `evidence.export` audit fact.
  Reserved this purpose for API-R-42's dedicated download route, following the report/journal
  file pattern. Preserved the owner entity for destruction-scope checks. Updated the data-model
  registry and its API sweep; the dedicated pack route itself remains unimplemented.
- Two new entity/tenant-wide Auditor cases failed on the old generic route in **7.42 seconds**.
  After the repair, all file API and registry architecture tests passed: **29 in 22.33 seconds**.
  Both all-entity and scoped Auditors receive the same 404 as an unknown file for metadata and
  bytes; retained entity/whole-tenant destruction scopes are checked. Ruff lint/format, source
  Mypy and whitespace pass. Logs: `/private/tmp/evidence-file-route-{red,green}.log`.
- All processes terminal. Archived older control/relock notes verbatim. Pack lifecycle/storage,
  audited download/API, automatic generation, other kinds and variance remain open, along with
  release gates and independent accounting approval. Direct main; no deployment/readiness claim.

## First-close ZIP assembly — October 8, 2026 (RPS-16 continued)

- Continued from clean published 9fe1bd0. Added `reports/evidence_assembly.py`: reloads a
  pack's immutable source binding, reauthorizes scope/export, then invokes all frozen-close,
  certification/approval, journal, reconciliation statement/population, audit and supporting
  report readers. Includes the binding in `lock/source_binding.json`. Missing required paths,
  mismatched report populations, duplicate/unsafe files or any source refusal yield no ZIP.
- First-close output uses the deterministic archive builder and separately hashed manifest.
  Re-lock assembly explicitly refuses until the separate driver-variance report is available;
  a valid stored raw comparison alone is not substituted. This boundary creates no jobs,
  verification records or stored files and does not commit or expose an endpoint.
- Initial two database cases: **one passed, one failed in 14.26 seconds**; the assembled ZIP
  reached verification, but the new test used the wrong verifier keyword. Corrected it to
  `expected_manifest_sha256`. Final assembly/archive/close/re-lock regression:
  **79 passed in 24.33 seconds**. Actual independent waiver/lock approvals, twelve freeze
  datasets, audit digest and five report jobs feed a reproducible 36-payload ZIP. Each byte
  count/hash and source binding is checked; journal evidence is nonempty and omissions retain
  their approved identities. Journal and close-run gate setup is seeded, not full operational
  accounting acceptance. Unsigned reconciliation fixtures, pending reports, removed permissions
  and a genuine approved re-lock without its variance report all refuse assembly.
- Logs: `/private/tmp/evidence-assembly-{db,final}.log`. All processes terminal. Source Mypy,
  Ruff lint/format and whitespace pass. RPS-16/CTL-041 are unclaimed: complete job lifecycle,
  encrypted storage, creation/idempotency, audited download/API, automatic generation, other
  pack kinds and re-lock variance reporting remain open. Current release gates and independent
  accounting approval remain required. Direct-main publication; no deployment or notifications.

## Durable CLOSE source bindings — October 8, 2026 (RPS-16 continued)

- Continued from clean published a622467. Migration 0142 adds immutable
  `evidence_pack.source_binding`: an object or legacy NULL, with no UPDATE grant. DB-03
  protects it even before success; downgrade validates across all tenants and refuses to
  discard any retained binding. Existing rows are not backfilled from current sources.
- Added `reports/evidence_sources.py`. Preparation verifies an explicit audit digest, queues
  the five supporting reports through the existing planner, and returns a versioned binding
  for atomic pack insertion. It retains the request, tenant/entity/period, request/freeze
  instants, snapshot manifest, frozen run IDs, supporting run/job IDs and normalized selector
  hashes, plus the digest verification ID. Loading reauthorizes the selected close and checks
  the pack row, frozen source and report/job associations without selecting or enqueueing anew.
- Initial database witnesses: **two passed in 8.81 seconds**. Real report jobs/outputs and
  audit verification are used around a seeded close. Newer report/digest candidates do not
  replace the saved selection; repeated loads preserve output bytes. A failed enclosing pack
  transaction rolls back the pack, reports and jobs together. Legacy NULL, revoked scope,
  wrong identities/cutoffs, duplicate/missing sources and unversioned documents refuse.
- Broader source/PG/migration run: **88 passed, one failed in 82.19 seconds**. The failure found
  pre-existing out-of-period report metadata drift. Migration 0143 corrects its description
  and IPE sources for the already implemented computed late events; stored runs/outputs stay
  intact. Next run: **88 passed, one failed in 82.55 seconds** because the owner-role trigger
  test saw no tenant row under RLS. A role-switch attempt then gave **48 passed, one failed
  in 23.72 seconds** (owner cannot SET ROLE erev_app). The final fixture temporarily removes
  FORCE RLS for the table owner in a rolled-back transaction, verifies the row is visible,
  and proves the trigger refuses the mutation. **Final affected run: 49 passed in 24.25 seconds**,
  including full upgrade/downgrade/upgrade, catalogue equality, application grants, downgrade
  refusal and the extended binding/rollback witness. All processes terminal.
- Logs: `/private/tmp/evidence-binding-{db,final,corrected,verified,guards}.log`. Source/migration
  Mypy, Ruff lint/format and whitespace pass. Audit-digest and supporting-source-plan notes
  archived verbatim. Snapshot sandbox rules regenerate evidence packs/report runs instead of copying them.
- The creation command and job lifecycle/idempotency still need integration with these bindings.
  Full assembly, audited downloads/routes, automatic generation, other kinds and variance report
  remain open. Collectors must still validate output/audit bytes and export permissions. No
  pack endpoint, CTL-041, RPS-16 or production-readiness claim. Current release verification and
  independent accounting sign-off remain required. Direct main; no deployment or notifications.

## Reconciliation population and retained waiver basis — October 8, 2026 (RPS-16 continued)

- Continued from clean published 4a9de2a. New checklist-waiver submission audit events retain
  the exact subject hashed by the approval request, before submission changes pending counts.
  The certification collector checks that retained document against the approved hash, gate,
  entity/book/period, reviewed count/members and the selected lock's audit prefix. Exported
  proof includes the original subject and audit event identity; later checklist state is unused.
- Added `reports/evidence_reconciliation_population.py`: resolves the reconciliation requirement
  at the lock freeze cutoff, retaining its setting source identity; enumerates only that lock's
  certified/reopened statements. Rejects duplicate kinds/IDs, wrong scope/time and unexplained
  required omissions. Approved missing/unreviewed member identities can cover absent kinds;
  an equal-count waiver of another kind or an outdated statement cannot. Omissions remain
  explicit `waived_absent_kinds`, never mislabeled as certified statements. Full assembly must
  invoke both this population reader and the existing statement/signature collector.
- Initial waiver witness: **one passed in 12.20 seconds**. Initial population/subject checks:
  **53 passed in 18.09 seconds**. Broader lock/re-lock, waiver and evidence regression:
  **149 passed in 171.95 seconds**. Extended policy-history run: **67 passed, two failed in
  18.57 seconds** because the test advanced September's frozen clock, still before the actual
  October database freeze cutoff. Corrected the fixture to publish after the recorded cutoff;
  final affected run: **69 passed in 18.51 seconds**. Covers real waiver/lock approvals,
  unchanged output after a later disabled policy, revoked scope, hash/member/scope mismatch,
  duplicate sources and explicit approved omissions. Journal/reconciliation gate setup is seeded;
  these are not complete operational close or accounting acceptance witnesses.
- Logs: `/private/tmp/waiver-basis-db.log` and `/private/tmp/waiver-population-{db,final,history,
  corrected}.log`. All processes terminal. Source Mypy, Ruff lint/format and whitespace pass.
  Saved supporting-report notes archived verbatim. No API contract or availability change.
- Legacy waiver audit events without the exact subject document cannot supply this proof;
  collection refuses rather than inventing historical details. Full pack assembly, persisted
  state/bindings/retry reuse, jobs/routes/audited downloads/automatic generation, other pack kinds
  and the separate variance-between-closes report remain open. Current release gates and
  independent accounting approval remain required; RPS-16/CTL-041 and production readiness
  are unclaimed. Validated direct-main publication; no deployment or external notifications.

## Control gate result and RPO closing defect — October 8, 2026

- Completed the preserved control gate on immutable 68d9607: **494 passed, one failed,
  10,483 deselected in 820.68 seconds**. Report: 45 controls pass, CTL-018 fails, CTL-041,
  CTL-045 and CTL-048 lack evidence. The sole test failure is the relock witness already
  corrected in 7c83cb4 and verified separately. No canonical rerun/pass is claimed.
  Source/dependency bindings verify; hashes are in the dated repository-checks note.
- Measured an additional B4-2 defect on clean 7c83cb4 using real recognition and disclosure
  stages with allocated-state fixtures. A 12,000 fixed fee plus 150 March usage has 9,000
  remaining in recognition, but rollforward closing is 8,850 with zero unexplained difference.
  Pure usage produces the known 150 unexplained amount. This is engine-scoped evidence,
  not an API measurement. Recorded inputs, outputs, reproduction and full repair scope in
  docs/release/RPO-REALISED-FEES-2026-10-08.md; updated B4-2. A cause-map-only patch would
  miss the incorrect closing; dated realized allocation must also be carried into measurement.
- Control session 36008 is terminal. Property session 52175 / PID 6358 is confirmed live,
  still in determinism, in its original immutable context. Keep that run; no database test
  process is active. Archived invitation-erasure evidence verbatim. No deployment/readiness claim.

## GL reconciliation ledger-history freshness — October 8, 2026

- Continued from clean published main 8579c6b (previous turn made verified progress).
  Closed B2-8: GL reconciliation freshness now watches later seals across ledger history
  through the reconciled period end, matching the comparison's account/role population.
  An earlier-period posting invalidates review even without a reversal into the current period.
  Older rows retain timestamp fallback over the same range. Billing stays period-scoped;
  other entities/books and future periods do not invalidate either comparison.
- First regression run: **8 failed, 25 deselected in 14.32 seconds**, all fixture transition
  calls missing set_values. Corrected baseline: **6 failed, 2 passed, 25 deselected in
  15.23 seconds**: two cases reproduced the missed earlier-period posting; four were fixture
  period-state errors. Corrected fixtures and implementation: **8 passed, 25 deselected in
  13.51 seconds**. Logs: /private/tmp/reconciliation-history-{before,baseline,fixed}.log.
- Added entity isolation and unsigned-cockpit checks. Broader lock/reconciliation and query
  coverage: **48 passed in 142.38 seconds**, /private/tmp/reconciliation-history-expanded.log.
  Strengthened the matrix with amounts moved between distinct accounts: **10 passed,
  25 deselected in 15.82 seconds**, /private/tmp/reconciliation-history-final.log. All processes
  terminal. Ruff lint/format, source Mypy and whitespace checks pass. Existing concurrent
  posting/generation cases remain covered by the broad run. No current full-suite claim.
- Updated the model, B2-8 and developer guidance; archived prior repository-gate evidence
  verbatim. Exact role-balance recomparison (B1-29), volume/release checks, remaining product
  gaps and independent accounting sign-off remain open. No deployment; preserve exclusions
  and noncommercial licensing. Publish tested changes directly to main.

## Durable completeness refusal evidence — October 8, 2026

- Continued from published main c0e4fc6. Failed JE_COMPLETE evaluations now retain CTL-019
  FAIL observations after the refused lock request or approval transaction rolls back. Evidence
  cites the existing period state, so missing journal runs are covered. The original refusal and
  pending approval remain; no period lock or business write survives. Same caller/tenant scope,
  nested refusals retained once, and evidence-write failure rolls back partial observations.
- Migration 0141 adds PERIOD_STATE and refuses downgrade while such evidence exists. Updated
  generated API types, control registry, audit classification and B1-24 guidance. Completed the
  prior currency finding's missing IMP-149 PRD catalogue row and matching architecture counts.
- Initial PostgreSQL cases: **2 passed, 21 deselected in 10.10 seconds**. Expanded lock/UOW/
  validation/all-architecture run: **329 passed, 2 failed in 203.69 seconds**; fixed missing audit
  object classification and currency catalogue drift. Final affected run: **98 passed, 1 failed
  in 85.53 seconds**; only catalogue row count remained and was corrected. Corrected catalogue/
  validation: **65 passed in 1.00 seconds**; control registry/report: **6 passed in 35.88 seconds**.
  Logs: /private/tmp/completeness-refusal-{first,expanded,final,corrected,registry}.log. All terminal.
  Coverage includes real PostgreSQL rollback, approval refusal, nested handling, migration head,
  downgrade protection and failure after evidence insert. Source Mypy, Ruff lint/format, generated
  OpenAPI, frontend tsc --noEmit and whitespace checks pass. npm run typecheck was unavailable;
  the direct TypeScript compiler check succeeded instead.
- Archived integration fallback evidence verbatim. Verified no open PRs and only remote main;
  continue tested direct-main publication. No deployment or full-suite/readiness claim. Remaining
  implementation, final release checks, engine cut/replays and independent accounting sign-off
  remain open; preserve publication exclusions and noncommercial licensing.

## Outstanding release verification

These checks need current release-candidate evidence. Historical October 3 results
remain in the dated build history; they do not verify current main. This list does
not authorize deployment, provisioning or changes to a live database.

- make audit-deps: passed on 87f53d1 October 7; rerun for the final release candidate.
- SUPERVISOR VERIFICATION NEEDED: make docker-build
- SUPERVISOR VERIFICATION NEEDED: make compose-verify
- SUPERVISOR VERIFICATION NEEDED: make zap-baseline
- make tf-validate: passed on 40ae405 October 7 (validation only); rerun for final candidate.
- SUPERVISOR VERIFICATION NEEDED: make backup, make restore-verify (isolated local drill only)

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
