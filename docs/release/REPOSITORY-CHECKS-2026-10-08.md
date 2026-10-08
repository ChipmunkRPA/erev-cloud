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

## Golden parity gate

`make parity` passed on clean revision `6d33ae174652db51f4400c2219eaa5420f6e570b`.
All 18 legacy fixture files verified. Pytest completed **130 passed in 106.29 seconds**:
122 selected golden cases passed (zero failures/skips), plus eight additional checks.
The golden population comprises 56 class A, nine class B and 57 class C cases.

The immutable-context report confirms unchanged source tree and context hashes, consistent
Python and Node dependencies with no mismatches, and a clean unchanged parent checkout.
Captured tree: `cfaa43a699eefb870a97576c9348b50f5d4d9523`.
Context SHA-256: `f50b15ad04ea2d42ab7f3ceaa60454ee047bc51b2462b1ac87ac642cd9adc93a`.
Run ID: `adf406cc0f7e49afb127da74fb2f2ce0`; finished October 8 at 08:08:33 UTC.

The nine class B cases still require independent revenue-accountant approval across five
units: DEV-002, DEV-052, DEV-010, DEV-050 and DEV-011. Machine parity does not provide that
approval. Rerun the gate for the final release candidate after subsequent source changes.

Local report: `.run/reports/parity/report.json`, SHA-256
`bd84543f6abc41241761383867747749a27d3c0bb27d50caf1e87394fbf82831`.
Local log: `/private/tmp/erev-parity-2026-10-08.log`, SHA-256
`2aeb81f968f2321608c05c4f7f9c49c2cc1c19d163898e3717d5011da11ce31e`.

## Full accounting answer-key gate

`make answer-keys AK_SCOPE=full` completed on clean revision
`177cb682af1c1626e372ac8c1de5e623e1a089f1` with **505 tests passed and two failed
in 352.75 seconds**. The canonical database scope selected all 255 corpus keys:
251 passed, one failed, one could not run, and two were withdrawn. All 255 key review
statuses remain unapproved; this count includes the withdrawn keys.

Coverage has no gaps: List A 49/49, List B 46/46, List C 76/76, hints 50/50,
family slugs 9/9 and family codes 28/28. The release manifest's corpus-membership/hash
and run-chronology validators accept the report. This validates its provenance and scope,
not its outcome: G4 remains failed.

The failures are:

- `DLT-CHK-020-CHK-022-GT07-JANUARY-2023-GROSS-AND-DELTA-JOURNALS`: the database
  runner applied 141 steps, then refused the nondistinct review for CONTRACT-1 / POB #3.
  Its template declares nondistinct; the runner supports confirming distinct conclusions,
  and the fixture does not declare the integration target needed for a nondistinct review.
  The following 57 steps were refused and no checkpoint blocks compared. POL-122 overrides
  are no longer the first blocker. Do not change distinctness or invent a target to force a pass.
- `VC-CHK-113-TC-POBVC-16`: seven mismatches remain. Software billing is 364.98 versus
  expected 400.00; after the concession the engine states a 60.00 contract liability versus
  the expected refund liability, with the corresponding November/December journal differences.
  These are the existing AD-14/AD-15 accounting decisions, still pending independent review.
  Neither key expectations nor engine treatment was changed for this run.

Source tree stayed `88d639280679111b1826a5e3966cb7321dcb2674`; immutable context SHA-256
stayed `9ee4f8b58b02056223f20b628d0ff18188f35756ef2ae8e97e7ae8794dc512f9`.
Python and Node dependency bindings remained consistent with no mismatches; the parent checkout
remained clean. The report finished October 8 at 08:20:34 UTC.

Local report `.run/reports/answer-keys/report.json` SHA-256:
`6c8eecb9fe4e4c7176f8cfe9d50fa71c7325b3abaccd3031a51be415ce4cadb0`.
Local log `/private/tmp/erev-answer-keys-2026-10-08.log` SHA-256:
`bf959b7ab6c0acd438be8c999ffd978ef1ac2c9b2fff05fb0e15b6be1a76ab29`.

## Control gate and relock test correction

`make controls-report` started on clean revision
`68d960754ea25964340d30aa15498ecdf934fae1` in immutable context
`.run/gates/ctx-controls-report-68d960754ea2-9993`. It completed with **494 passed,
one failed, 10,483 deselected and one warning in 820.68 seconds**. The report counts 45 of
49 controls passing, CTL-018 failing, and CTL-041 / CTL-045 / CTL-048 missing tagged evidence.
The failure is the relock witness corrected below; its original immutable source predates that
correction. No rerun or current canonical G7 pass is claimed. The three missing features remain
unimplemented: period evidence pack, AI proposal acceptance and migration promotion.

Source tree stayed `d4c78502232c8a2ec9133d798bf07f704b0a2947`; context SHA-256 stayed
`1d6589094361a11c407fe22d1183ec9bf2603d99d834adda709aebdc914403db`.
Python and Node dependency bindings remained consistent with no mismatches.
Report `.run/reports/controls-report/report.json` SHA-256:
`88fe72bff682edd07d588d610b3cb5eac0ceba9312d5f230935631b3653a64b7`.
Log `/private/tmp/erev-controls-2026-10-08.log` SHA-256:
`0800467b8d1954c88541c51e7c063b32e12d229ec2e9a9931c21a328c890a9d6`.

Reproduced that test in a separate disposable database `erev_rv_controlfix` on the same local
PostgreSQL server, without resetting the gate's `erev_rv_cont` database. The initial attempt
stopped at setup because the new database inherited SQL_ASCII; recreated this empty diagnostic
database with UTF8 to match the primary test database. The actual regression then failed in
18.32 seconds: relock correctly returned 409 / EXCEPTIONS_CLEARED, because the backdated
progress following a later reviewed judgement had raised an OUT_OF_ORDER LATE_EVENT finding.

The journal-chain test now asserts that refusal, checks the exact number and type of findings,
requests their waiver as Maya, approves as Priya, and verifies the retained WAIVED status and
approval reference through the API before expecting relock success. The separate zero-net
journal gap witness performs the same review for both progress events. No application gate
or exception is bypassed. This test repair does not implement the missing per-posting approval
control or close the zero-net journal approval gap.

All three journal-chain tests passed in **42.13 seconds**; Ruff lint/format and whitespace
checks passed. The diagnostic process is terminal and its disposable database was removed.
The full control gate is now terminal; the continuing property gate uses no database.

Local baseline log `/private/tmp/erev-relock-control-baseline-utf8.log`, SHA-256
`e99327255ccbd6836546bfc0db0e07928030d741bbe2f2209b17e675a118c1fe`.
Local corrected log `/private/tmp/erev-relock-control-fixed.log`, SHA-256
`76881d36aca40adcfc1cc8d481611bac9ab08276700b4265a024e25ab1577cfa`.

## Property gate still running

`make properties` started on the clean starting revision, with the thorough Hypothesis
profile, in immutable context `.run/gates/ctx-properties-37c4f0c48918-6323`.
It collected 48 tests. All six metamorphic tests and the subsequent allocation, schedule, journal-balance,
rollforward and RPO tests have passed; the suite remains active in determinism checks.
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

The property result is pending and the full accounting corpus gate has two unresolved failures.
Full current backend/CI, browser,
volume, container and restore checks still need current release-candidate evidence. Remaining
implementation gaps, engine release cut/replays and independent accounting sign-off stay open.
