# Repository checks — October 8, 2026 (America/Los_Angeles)

These are local repository checks. No deployment or cloud mutation occurred.
They do not constitute independent accounting sign-off or a full production-readiness result.

## Completed checks

The starting clean revision was `37c4f0c48918a8a72228bbc596061ecfd12f9e99`.

- `make typecheck`: passed, including strict Mypy over all 850 Python source files and
  the frontend TypeScript project build.
- `make build`: passed, including the Vite production bundle and backend imports. Vite
  reported a non-failing large-chunk warning (main bundle about 1.15 MB before gzip).
  This build does not prove browser performance or accessibility.
- Full frontend suite before test corrections: **2 failed, 2,055 passed**, 192 files,
  55.71 seconds. Both failures were obsolete cockpit expectations for error-correction reopen:
  the first omitted the reviewed-judgement query and citation; the second expected inline
  unreviewed judgement creation to satisfy that flow.
- Corrected cockpit/reopen drawer checks: **34 passed**, 2 files, 4.96 seconds. The cockpit
  test now checks entity/book/topic/review status query scope, refuses submission without a
  citation, displays the reviewer and sends the selected judgement ID. The other scenario
  retains optional judgement creation and attachments under the permitted late-source reason,
  asserting that reason and a null correction citation in the request body.
- Full frontend suite after those test-only corrections: **2,057 passed**, 192 files,
  55.65 seconds. Command: `npm --prefix frontend run test -- --run`.
  Prettier, frontend `tsc -b` and whitespace checks also pass. No application code changed.
  The suite logs jsdom's unimplemented full-page navigation diagnostic; it exits successfully.
  Browser journeys and accessibility remain separate release requirements.

The corrected frontend result covers the starting revision plus the cockpit test correction
in this commit. These direct commands are scoped evidence, not a canonical `make ci` report.

## Repository-wide lint follow-up

`make lint` passed on clean revision `1d59f65b026402ec0b4c88745933721c4e3bc730`.
This includes Ruff format checks over 2,006 files, Ruff lint, Prettier, ESLint,
OpenAPI drift, generated registry, legacy fixtures and the single migration head check.
The component results were:

- Design: 501 files, zero errors or warnings.
- Vocabulary: 1,198 files, zero findings.
- Dependency licence scan: 133 packages (77 Python, 56 npm), seven allow-listed,
  zero findings or allow-list errors. This is separate from the repository's licence.
- Secret scan: 3,423 files, eight allow-listed findings, zero unexpected findings or
  unused allow-list entries.
- Legacy fixture integrity: 18 files verified.
- Control marker collection: all 495 tagged tests valid. Collection does not prove these
  tests passed and does not replace the canonical controls-report gate.

The repository licence remains PolyForm Noncommercial 1.0.0; neither `research-harness/`
nor `docs/research/` has tracked files. These checks do not assert a full security audit.
Lint log: `/private/tmp/erev-lint-2026-10-08.log`.
SHA-256: `a8362ac6e3c0f18d74bd901dcf7637c6066d50a3c7bd3260d236b3d17cc127f7`.

## Property gate still running

`make properties` started on the clean starting revision, with the thorough Hypothesis
profile, in immutable context `.run/gates/ctx-properties-37c4f0c48918-6323`.
It collected 48 tests. The first two metamorphic tests have passed; the suite remains active.
Pytest PID 6358 was confirmed live with increasing CPU time; the executor session is
52175. Console output: `/private/tmp/erev-properties-2026-10-08.log`.

Continue polling that exact session/process; do not restart merely because it is slow. No pass
or failure is claimed. On completion inspect `.run/reports/properties/`, including source and
dependency bindings, and replace this pending observation with the actual dated result. The
running immutable context is separate from the cockpit test corrections made afterwards.

## Completed log identities

These local logs are not shipped as repository files. Their hashes bind the observations above.

| Check | Local evidence | SHA-256 |
|---|---|---|
| Full type check | `/private/tmp/erev-typecheck-2026-10-08.log` | `6c35ac3109f960a1dfd03f46d173897fd83f8010a1cda99c66ebc91a0ac86a0c` |
| Build | `/private/tmp/erev-build-2026-10-08.log` | `c9533356d666158c3a3235a63ee6317287ba87a0f7fd2c9cf6acd1712fd82e5e` |
| Initial frontend suite | `/private/tmp/erev-frontend-tests-2026-10-08.log` | `e6e0aee3db1bf7de8c27f9b819f2c73e93506fd8ac89050ce15577b59780e2e8` |
| Corrected reopen checks | `/private/tmp/erev-reopen-ui-corrected.log` | `b07cb2b1c1149f30cf7241ba51cf03e6437b59fd06f42ffcba13ec55f5540dd0` |
| Verified frontend suite | `/private/tmp/erev-frontend-tests-verified-2026-10-08.log` | `ecaf7ca90ea1451d1d190d882b0d2e1ba4784a161405ec0449a6941677907364` |

## Remaining work

The property result is pending. Full current backend/CI, accounting corpus/parity, browser,
volume, container and restore checks still need current release-candidate evidence. Remaining
implementation gaps, engine release cut/replays and independent accounting sign-off stay open.
