# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Evidence-pack source selection — October 8, 2026 (RPS-16 continued)

- Continued from clean db1e96f. Added `reports/evidence_selection.py`: resolves complete
  contract samples in submitted order, captures tenant/entity/contract identities and the
  request cutoff, and binds CLOSE to the exact lock/entity/book/period and stored freeze cutoff.
  REOPEN and PERMANENT_LOCK records are refused because they freeze no datasets.
- Selection intersects `report.run` and `audit.read` scopes with transaction RLS. Missing
  permission/scope grants do not become wildcards; SYSTEM has no implicit generation access.
  A missing or hidden sample member refuses the whole sample without naming hidden records.
  A hidden lock is refused before describing its kind or mismatched selectors. CHANGE/ACCESS
  bind the visible entity population for their future collectors.
- **160 tests passed in 17.52 seconds**: nine PostgreSQL/RLS selection cases, 102 request-schema
  tests and 49 archive tests. Same contract key in two tenants resolves only the caller's row;
  role-scope union does not widen report/audit access. Test rows are seeded; no real close or
  full pack is claimed. Log: `/private/tmp/evidence-selection-final.log`. Two-source mypy,
  Ruff and whitespace pass. Initial DB run had nine fixture errors from a missing REOPEN
  reason; corrected the fixture, then nine DB tests passed in 17.38 seconds before the
  stronger cross-tenant case and final combined run. All processes are terminal.
- Next integrate selection with audited command guards, persisted scope/cutoff, complete
  source collection, jobs and files, download reauthorization/audit, automatic lock/re-lock
  packs and the specified end-to-end acceptance. Selection alone does not authorize every
  payload or establish as-of content completeness. EVIDENCE_PACK remains pending, CTL-041
  open, report availability unchanged. Full-current gates and independent accounting sign-off
  remain outstanding. Archived the fixture/freshness notes verbatim to the build history.

## Evidence-pack request contract — October 8, 2026 (RPS-16 continued)

- Continued from clean 4860217. Verified zero open PRs and only remote `main`.
  Added API-S-EvidencePackCreate as a discriminated request union for CLOSE,
  CONTRACT_SAMPLE, CHANGE and ACCESS. Each kind requires exactly its documented
  selectors; unrelated fields (including explicit nulls) are rejected. Sample selection
  preserves exact business keys and order, rejects blank/duplicate IDs and enforces 1–50.
  Change ranges permit one day and reject reversed dates. No default lock/book/date.
- **151 request/archive unit tests passed in 0.17 seconds** (102 request, 49 archive),
  including the required/unused-field matrix, JSON round trips and schema requirements.
  Log: `/private/tmp/evidence-request-units.log`. Mypy on the new schema, Ruff and whitespace
  checks pass. Initial request run: 13 failed, 89 passed because the test fixture used
  nonexistent book `PRIMARY`; corrected it to the actual E-02 code `ASC606`.
- Request shape is now available for the forthcoming routes; this does not verify source
  selection, permissions, HTTP behavior or generation. Next: resolve each selector within
  tenant and permission scope, bind the generation cutoff/source identities, and implement
  complete source collection, jobs, audited downloads, automatic lock/re-lock packs and
  the specified acceptance tests. Keep EVIDENCE_PACK pending and CTL-041 open until then.
  Full-current release gates and independent accounting sign-off remain outstanding.

## Evidence pack integrity foundation — October 8, 2026 (RPS-16 in progress)

- Continued from clean 8a8cdda. RPS-16 / CTL-041 remains unimplemented at the workflow level.
  Started its required archive boundary: deterministic ZIP bytes, canonical payload manifest,
  exact byte counts/report-run IDs, SHA-256 and verification against the separately stored
  trusted manifest hash. The manifest cannot hash itself; clarified the existing detached
  `manifest_sha256` contract in T-RPT-04 and the build acceptance wording.
- `reports/evidence_archive.py` rejects changed/missing/unlisted payloads, altered manifests,
  self-references, duplicates, file/directory and case collisions, unsafe paths, symlinks,
  invalid metadata and over-limit payloads. No filesystem extraction or accounting derivation.
  Export sanitization and authorization remain the caller's responsibilities.
- **49 pure integrity tests passed in 0.11 seconds**; independent ZIP reads recompute payload
  hashes, and tampering/reforging is refused against the trusted hash. Mypy, Ruff and whitespace
  pass. Log: `/private/tmp/evidence-archive-units-final.log`. An earlier command named a
  nonexistent output-test file and collected no tests; the recorded final command is the real run.
- Continue the full RPS-16 workflow next: scoped request schemas/routes, job lifecycle, source
  collection, immutable/as-of reads, encrypted file storage, audited download, automatic lock
  enqueue and re-lock diff, and contract-sample/change/access packs. Use the archive boundary
  in that implementation. Keep EVIDENCE_PACK pending and CTL-041 unclaimed until full tests pass.
  Existing `locked.locked_dataset` verifies frozen bytes; CSV export must use the declared-kind
  formula guard (`locked.export_csv` / snapshot column kinds), not serve raw frozen CSV.
- This is a tested prerequisite, not an available evidence-pack product or readiness claim.
  No deployment; publish reviewed work directly to main. Remaining accounting sign-off and
  full-current verification requirements are unchanged.

## Canonical property gate completed — October 8, 2026

- Preserved session 52175 completed successfully: **48 passed, zero failed/skipped in
  5899.78 seconds (1:38:19)**; `make properties` exit 0. This was the thorough run on
  clean captured 37c4f0c48918a8a72228bbc596061ecfd12f9e99, not the later RPO source.
- Verified immutable source/context start/end bindings and Python/Node dependency bindings;
  no mismatches. Captured tree matches that Git commit. Report/log hashes are recorded in
  REPOSITORY-CHECKS-2026-10-08.md. The process is terminal; no unfinished property run remains.
- Archived the preceding RPO investigation/repair notes verbatim. Full accounting corpus
  failures, control-gate gaps, other product gaps and independent accounting sign-off remain.

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

## Control verification and relock witness — October 8, 2026

- Started canonical `make controls-report` on clean main 68d9607. It remains active in
  .run/gates/ctx-controls-report-68d960754ea2-9993, executor **36008**, PID **10033**;
  log /private/tmp/erev-controls-2026-10-08.log. Collection confirms 495 tagged tests.
  One relock test has failed so far. Keep polling this immutable run; no final G7 claim.
- Reproduced the relock failure on a separate disposable local database, preserving the
  control gate's primary database. Initial setup failed because the new database inherited
  SQL_ASCII; recreated that empty database with UTF8. Actual baseline: **one failed in
  18.32 seconds**. Backdated progress follows a later reviewed judgement, raises LATE_EVENT
  / OUT_OF_ORDER, and the open exception correctly prevents relock.
- Updated the two reopened-period witnesses to assert the exception gate refusal, inspect
  the exact findings, request and independently approve their waivers through the API, and
  verify retained waiver evidence. All **three journal-chain tests passed in 42.13 seconds**.
  Ruff lint/format and whitespace pass. No application control was weakened; per-posting
  approval and the zero-net journal gap remain open. Log hashes are in the dated checks note.
- Diagnostic process is terminal and its database removed. Property session **52175** / PID
  **6358** remains active in the original context, past all six metamorphic tests and through
  RPO checks, now in determinism. Both ongoing gates predate this test correction; preserve
  their handles and inspect final source bindings. No deployment or readiness claim.

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
