# Local readiness verification — October 15, 2026

This development verification starts from `519de8c`, with the exact synthetic-key scanner
exception and AI prompt-test module rename described below. It is not an immutable full-CI
release result, accounting sign-off or deployment approval. The separate dependency audit below
was subsequently run in an immutable context on `621d412fcaa21bd35af898b5d48aec3761908309`.

## Completed checks

- `make audit-deps` on clean `621d412`: passed in an immutable source context. All 86 pinned
  Python dependencies were audited; eight environment markers were removed to include packages
  used by other target platforms. Python vulnerabilities: zero. npm advisories: zero at every
  severity. The context hashes before/after matched; dependency installations remained consistent.
  Result digest: `89ed52d71a2a2afbb288e638b931f0d0021ad18719856b59ce7f2631d9ebd203`.
  Logs/report: `.run/readiness-audit-deps-oct15.log`, `.run/reports/audit-deps/report.json`.
  This is dependency-advisory evidence as of the run, not proof that all application security
  and release requirements are satisfied.

- `make lint`: passed after the repairs below, including formatting, source lint, design,
  vocabulary, dependency licences, secrets, OpenAPI, seed/fixture checks, control-marker
  validation (502 tagged tests out of 12,015 collected), and the single migration head check.
  Log: `.run/readiness-lint-oct15.log`.

- `make typecheck`: passed, including strict Python typing for 917 sources and frontend TypeScript.
  Log: `.run/readiness-types-oct15.log`.
- `make build`: passed frontend production build and backend imports. Vite reported its existing
  large-chunk warning. No application was deployed. Log: `.run/readiness-build-oct15.log`.
- `npm --prefix frontend run test -- --run`: 196 files, 2,109 tests passed (174.31s).
  Log: `.run/readiness-frontend-oct15.log`. The run includes jsdom navigation diagnostics;
  the test process exited successfully.
- Collection of the AI prompt and policy-template modules together: 28 tests collected without
  import mismatch. Log: `.run/readiness-collection-collision-oct15.log`.
- Publication checks: GitHub repository remains public with default branch `main`; neither
  `research-harness/` nor `docs/research/` is tracked. The PolyForm Noncommercial licence remains.

## Repairs discovered by broader verification

The secret scan flagged a synthetic key literal asserted against a mocked SDK constructor.
Its exception is limited to that file, pattern and exact stripped-line hash. Real credentials,
other files and edited lines remain subject to the scan; no scanner rule was relaxed.

Full test collection imported two un-packaged `test_templates` modules under the same name.
The AI prompt module is now `test_ai_prompt_templates.py`; its assertions are unchanged.
Focused AI runs did not expose this collision with the policy-template suite.

## Backend unit/architecture result and repairs

The complete unit and architecture directories finished with **5,609 passed, two failed,
two Linux-only skips** in 1,364.71s (22m44s). Log:
`.run/readiness-unit-architecture-oct15.log`. This is the original result, not a green run.

- The migration-walk guard found that `test_ai_call_intent.py` and `test_ai_job_binding.py`
  did not reset to a data-free head before attempting downgrades. They now call `fresh_head()`
  first, and the guarded inventory includes them. The actual constraint/immutability/downgrade
  assertions remain intact.
- The process-script lifecycle test inherited the repair runner's `EREV_RUN_DIR` while looking
  for its PID file under the default `.run` directory. Its subprocess environment now explicitly
  matches the probe paths; production process-script behavior is unchanged.

Focused revalidation: **15 passed** (44.72s), covering both failed unit checks, all process-script
checks, both AI database guards and the full migration round trip. Strict typing for the four
changed test modules and Ruff/diff checks passed. Logs:
`.run/readiness-isolation-repairs-oct15.log`, `.run/readiness-isolation-types-oct15.log`.
The full 5,613-test selection has not been repeated after these repairs.

## Remaining scope

- The backend unit/architecture selection above does not include all backend API/domain/engine/PG
  test directories. Fresh complete CI and release-gate results remain outstanding.
- Full immutable CI, PostgreSQL/release gates, outstanding implementation, unknown AI usage
  reconciliation and independent accounting sign-off remain required. Historical evidence in
  `CI-2026-10-14.md` does not establish current-main completion.
