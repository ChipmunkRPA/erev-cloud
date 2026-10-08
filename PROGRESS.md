# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

**Owner workflow: test, then commit and push directly to main. Create no new PRs unless branch protection requires one. No deployment.**

## Idempotent first-close creation API — October 8, 2026 (RPS-16 continued)

- Continued from clean published fbe1eaa; rechecked zero open PRs and main as the only remote
  branch. Added POST /evidence-packs with the documented discriminated selectors, 202 JobOut,
  Location and X-Erev-Evidence-Pack-Id. The command kernel stores the response atomically with
  the pack, sources, five reports, six jobs and numbering. Other kinds explicitly refuse 422.
- Creation preflights caller scope and retained evidence, then selects one completed PASS digest
  covering the frozen audit head, ordered by completion time/ID. It verifies that digest before
  queueing and persists its exact ID. Existing internal callers may still supply an explicit ID.
  A damaged selected digest refuses without older fallback; replay never reselects or queues.
  Missing verification returns actionable 422. The existing audit verify job must finish before
  a new creation key is submitted; the earlier validation response remains tied to its key.
- Initial HTTP/route regression: **14 passed in 35.07 seconds**. Expanded audit/OpenAPI/route/
  classification/close regression: **50 passed in 56.75 seconds**. Witnesses include newer digest
  after creation with unchanged replay IDs/counts, changed-body rejection, damaged digest with
  no queued effects, unsupported kind, missing verification and revoked-role replay refusal.
  Final failed-response replay extension: **3 passed in 25.32 seconds**; all processes terminal.
  The inherited close witness still has seeded journal/close-run setup and approved omissions;
  it does not establish operational CTL-041 acceptance.
- Regenerated OpenAPI/client types and updated the guide/data model/build status/limits.
  Source Mypy, Ruff lint/format, OpenAPI staleness, frontend tsc --noEmit and whitespace pass.
  Archived the older durable-source-binding section verbatim. Logs are local under
  /private/tmp/evidence-post-{db,final,retry}.log. Automatic verification orchestration, listing,
  enqueue on lock/NTF-06, other kinds, re-lock variance and current release/accounting approval
  remain open. RPS-16/CTL-041 and production readiness remain unclaimed. Direct main; no deployment.

## Verified close-pack read/download API — October 8, 2026 (RPS-16 continued)

- Continued from clean published caf33b7; previous turn added atomic internal pack creation.
  Added GET /evidence-packs/{id} and /download for retained CLOSE packs. Header reads expose
  status, source identities and manifest/hash, with a download href only for SUCCEEDED.
  Download rechecks current source/export permissions and entity scope, verifies original
  encrypted file metadata, ZIP/manifest and exact retained-source bytes, then commits one
  evidence.export audit before returning application/zip with attachment/sandbox/no-store.
- Split read-only retained verification from completion: a GET never finishes pending work or
  regenerates damaged output. Pending/failed downloads refuse 409; tampered bytes refuse 422.
  Source permission denials are audited; generic file routes remain closed. Creation/listing
  and other pack kinds are not exposed by this change. Updated user guide, data model and limits.
- Initial real HTTP close/download and route/audit architecture run: **17 passed in 35.57
  seconds**. Added damaged-byte injection and each source-permission scope refusal; final
  archive/storage/OpenAPI/route/audit/close regression: **83 passed in 54.79 seconds**. Two
  downloads return exact saved bytes and two export events; damage creates no export event;
  role revocation blocks header/download. The seeded-journal/approved-omission caveat remains.
- Logs `/private/tmp/evidence-download-{db,final}.log`; all processes terminal. Source Mypy,
  Ruff lint/format, whitespace, regenerated OpenAPI/client types, staleness check and frontend
  tsc --noEmit pass. Archived initial assembly notes verbatim. Public creation/listing with
  request idempotency and verification orchestration, automatic enqueue/NTF-06, other kinds,
  variance and current release/accounting approval remain open. RPS-16/CTL-041 and production
  readiness unclaimed. Direct main; no deployment or external notifications.

## Atomic close-pack creation command — October 8, 2026 (RPS-16 continued)

- Continued from clean published b06824b; previous turn integrated the first-close worker.
  Added `evidence_commands.create_close`: checks caller source/export permissions and entity
  scope, refuses unsupported re-locks, validates approval/journal/reconciliation evidence as
  the caller, prepares immutable sources with an explicit completed audit verification, then
  numbers/inserts the pack and queues its worker. One transaction owns five source report
  runs, six jobs, the binding, numbering and evidence.create audit; caller owns commit.
- Creation deliberately does not choose a latest digest or create one in a separate transaction.
  The pending HTTP/idempotency boundary must orchestrate a completed verification; this internal
  argument is not a new API request field. Other pack kinds and automatic lock enqueue remain
  open. A returned JobOut describes the queued worker; no new public route was exposed.
- Initial creation/worker/audit witnesses: **6 passed in 23.46 seconds**. Final close/re-lock,
  source-binding, storage and audit-classification regression: **55 passed in 27.84 seconds**.
  Commit produces exactly one pack/five reports/six jobs, all dispatched, with source IDs in
  the create audit. Rollback restores rows and numbering. Missing or out-of-scope permissions,
  invalid verification, unsigned reconciliation fixtures and unsupported re-locks refuse.
  Existing encrypted worker/retry/cancellation checks run through command-created close packs.
- Logs `/private/tmp/evidence-create-{db,final}.log`; all processes terminal. Source Mypy,
  Ruff lint/format and whitespace pass. Archived completeness-refusal notes verbatim. The close
  witness still uses seeded journal/close-run setup and approved omissions, not full accounting
  acceptance. Public creation/download with request idempotency, verification orchestration,
  NTF-06/automatic enqueue, other kinds, variance and current release/accounting approvals
  remain open. RPS-16/CTL-041 unclaimed. Direct main; no deployment or external notifications.

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
