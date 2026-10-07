# PROGRESS — eRev Cloud build loop notebook (under 20 KB)

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

## Contract-period policy isolation — October 7, 2026

- PR #5 merged into main (`be91991`), completing the two-policy workbench slice. The owner
  instructed automatic merging after verification and retention of **main only**. GitHub automatic
  merged-branch deletion is enabled; the four older merged branches were deleted locally/remotely.
  Future implementation branches are temporary and must be removed after merge.
- Work continues on `codex/contract-period-policy-scope`. POL-163 needs more than admitting another
  key: the FX engine currently treats the whole group/entity as one liability unit. A contract's
  exception must not change neighboring contracts in that unit.
- Added a CONTRACT_PERIOD bundle identity and resolver precedence over the entity PERIOD default.
  Identity encodes contract, entity and period unambiguously. Pin P and level C are required; both
  entity and period are required to read it. Existing readers without a contract still receive the
  entity default.
- Bundle assembly resolves approved POL-163 rows separately for each member and entity period,
  using the earlier of the known-at cutoff and the entity-local period end. Prior approvals remain
  eligible for their historical periods after supersession; later approvals cannot rewrite an
  earlier period. Forced IFRS15 treatment excludes these rows. Scoped exceptions never become the
  widest-scope persisted policy pin.
- Actual verification: 48 scoped-policy, period-row, resolver and PostgreSQL policy-domain tests
  passed. A further 590 kernel, FX engine, architecture and database period-policy tests passed,
  including the final persisted-pin assertion. Mypy passed for five source files; Ruff lint/format
  and whitespace checks passed. No full-backend or live-release claim is made.
- Initial publication attempts on October 7 returned GitHub internal server errors for both Git
  pushes and PR creation. The local commit is preserved; check the remote PR and main before
  treating this slice as published. Repository metadata confirms push/admin access and no archive.
- This is the isolation foundation, not completion of POL-163. Public authoring stays refused until
  FX liability layers carry their originating contract and use its period-scoped treatment for
  consumption and remeasurement, with monetary/historical transitions and mixed-member tie-outs
  verified. Those readers, actual FX journals, close behavior and UI remain next. No deployment.

## Policy override workbench — October 7, 2026

- PR #4 merged into public main (`51aa535`). Work continues on `codex/policy-override-ui`.
- The contract workbench now offers Policy overrides to users with entity-scoped `config.read`.
  Authoring additionally requires `contract.create` for the contract's entity. Historical views
  expose no command. Drafts can be authored before activation, including financing rates.
- Added POL-122 obligation/right and POL-047 contract/rate forms. Rates remain decimal strings;
  the screen explains inception rates and corrections. Saving creates a durable draft; submission
  is a separate action on that saved record. Reopening or retrying submission reuses the draft.
  The list displays scope, value, rationale, status and an approval-request link where present.
- Commands invalidate the contract override list along with the existing contract reads. Required
  fields, server refusals, network failures, list retry and read-only access have explicit behavior.
  Existing API validation and independent-approval controls remain authoritative.
- Actual verification: all **2,040 frontend tests across 191 files passed**, including six new drawer
  tests and the 66 workbench tests. TypeScript project build, changed-file ESLint, production frontend
  build, formatting and whitespace checks passed. Design check scanned 499 files with no findings.
  Local Chromium screenshots of both forms were inspected with mocked records and no runtime errors;
  this is UI verification, not live-service or accounting sign-off evidence.
- Remaining C-2: POL-163 period-scoped contract exceptions, broader product readers, database
  answer-key coverage, and an optional reviewed-judgement attachment selector in this drawer (the
  API already accepts and validates that link). Wider outstanding items remain in LIMITS-1.0.md.
  Current scope remains repository completion; no deployment or provisioning.

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
