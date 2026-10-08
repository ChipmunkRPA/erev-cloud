# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## First-close pack worker lifecycle — October 8, 2026 (RPS-16 continued)

- Continued from clean published 5ba0f2d; previous turn added verified dependency readiness.
  Registered `reports/evidence.py::build_pack` for EVIDENCE_PACK with the CLOSE readiness hook,
  three attempts, encrypted completion, required failure cleanup and queued cancellation.
  Uses internal SYSTEM source-reader capabilities restricted to the immutable entity; these
  grant no public caller access. Other pack kinds and re-lock variance still refuse.
- Added an optional cancellation guard under the job row lock. Completion locks job then pack:
  a pre-handler cancellation stops without output, while late cancellation after SUCCEEDED
  refuses 409. Failure cleanup requires the pack's own FAILED job/subject/params association;
  malformed foreign jobs cannot stop another pack. E-67 has no CANCELLED, so unfinished packs
  end FAILED with an evidence.stop reason; job state distinguishes failure from cancellation.
- Initial worker/registry/audit tests: **10 passed in 17.02 seconds**. Queue/release/stall/API/
  registry/close regression: **57 passed in 31.85 seconds**. Added a post-commit crash/retry
  witness: **9 passed in 23.73 seconds**; fresh QUEUED, interrupted RUNNING and retained
  SUCCEEDED completions reuse verified output, with one finish event per pack. An injected
  running cancellation produces no file; API tests cover queued and late cancellation, plus
  unsupported-kind cleanup and foreign-job isolation. Existing import cancellation/cleanup
  rollback tests: **2 passed in 24.14 seconds**. Source Mypy, Ruff lint/format, whitespace pass.
- Logs `/private/tmp/evidence-worker-{db,final,retry,cancel-regression}.log`; all terminal.
  Close witness retains seeded journal/close-run setup and approved reconciliation omissions;
  it is not full operational accounting acceptance. Archived waiver-population notes verbatim.
  Public creation/download and request idempotency, automatic enqueue/NTF-06, other kinds,
  variance, current release gates and independent accounting approval remain open. No
  RPS-16/CTL-041 or production-readiness claim. Validated direct main; no deployment.

## Dependency-aware queue readiness — October 8, 2026 (RPS-16 continued)

- Continued from clean published d7c27f8; previous turn retained verified first-close output.
  Added optional read-only `ready` hooks to job registration. After release/delivery fencing,
  before a slot/attempt, False keeps QUEUED and redispatches after 30 seconds with the same
  attempt/release budget. Stale/cancelled deliveries do nothing. A domain Problem settles via
  the normal terminal failure hook; unexpected reader errors preserve the queued task for
  existing stranded-task recovery. No handler attempt is spent on dependency wait.
- Added `evidence_readiness.close_ready`: checks pack/job subject identity and immutable CLOSE
  binding, then only the five bound report/run/job pairs. Pending pairs wait; missing, failed,
  cancelled or inconsistent sources refuse. This is a worker preflight, not authorization or
  evidence integrity proof; completion must still invoke the source readers and storage step.
- Queue suite **14 passed in 5.86 seconds**; source/queue/release/unit integration **30 passed in
  20.64 seconds**. Added source terminal-state fault cases, then full scoped queue, release,
  stall, cancellation API, registry and close witness: **50 passed in 23.48 seconds**. Seven
  waits preserve attempt 1 without taking a slot; stale delivery does not recheck/redispatch;
  completion runs once and produces one job.finish. Source checks use actual five report jobs;
  kernel readiness tests register probe handlers. No complete EVIDENCE_PACK handler claim.
- Logs `/private/tmp/job-readiness-{db,integrated,final}.log`; all processes terminal. Ruff,
  source Mypy and whitespace pass. Archived GL freshness notes verbatim. Pack handler wiring,
  creation/idempotency, failure/cancellation lifecycle, download/API, automatic generation,
  other kinds and variance remain open. Current release gates/accounting sign-off still needed;
  RPS-16/CTL-041 unclaimed. Direct main; no deployment or external notifications.

## Atomic first-close retention — October 8, 2026 (RPS-16 continued)

- Continued from clean published 7f04236; previous turn closed the generic-file access bypass.
  Added `evidence_storage.finish_close`: explicitly checks evidence export/entity scope, locks
  the pack, reauthorizes and assembles all retained sources, stores encrypted ZIP output, then
  writes SUCCEEDED/file/manifest/separate hash and `evidence.finish` in the caller's transaction.
  QUEUED/FAILED and partial preexisting output refuse. SUCCEEDED repeats verify/reuse the exact
  file; hashes, metadata, canonical ZIP and freshly verified source bytes must all agree.
- Actual local database/encrypted-store witness: **2 passed in 15.04 seconds**. Rollback retains
  RUNNING with no file-object row/manifest; commit produces one file and one finish audit event;
  repeat creates neither, and each revoked source/export permission refuses. This uses the
  earlier approved-omission/seeded-journal close witness, not full operational close acceptance.
  Transaction atomicity concerns database references; object-store orphan recovery remains the
  existing file-store responsibility. No completion helper commits or exposes bytes via API.
- Broader regression: **90 passed, one failed in 16.42 seconds**; architecture correctly found
  the new evidence_pack audit object unclassified. Classified it WHERE_NAMED and explicitly
  supplied its contract_ids (empty for CLOSE, supporting future samples). Final regression:
  **99 passed in 16.45 seconds**; source Mypy, Ruff lint/format and whitespace pass. Logs:
  `/private/tmp/evidence-storage-{db,final,corrected}.log`; all processes terminal.
- Archived older control/RPO notes verbatim. Dependency scheduling, creation/idempotency,
  failure/cancellation lifecycle, download/API and export audit, automatic generation, other
  kinds and variance remain open. RPS-16/CTL-041 and production readiness remain unclaimed;
  release gates and accounting sign-off remain required. Direct main; no deployment.

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
