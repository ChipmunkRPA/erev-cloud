# Lane F-WEB-R — frontend ruling-register items (production work), K-04 activation / CTR-20, L6 QA notes

Required 1.0 backlog (00-GOAL G1 `docs/00-GOAL.md:83`, G8 `:90`, G10 `:92`): every item below is inside the authorised objective, so no product decision precedes the worktree; the "yes" set of `spec-completeness.md` §1 is extended by the items that investigation marked "no — product decision" (Codex coverage review 2026-09-19 §2, applied by the docs agent). Sequencing: after wave 1 as capacity frees — authorised 1.0 scope sequenced by capacity; no confirmation hold precedes this lane. Record: `docs/reviews/loop/sprint/F-WEB-R.md`. Items: PR-8.1 (`report_run.job_id` + SF-04 Reference line), PR-8.2 (`create.problem` bound to its run), PR-8.3(i) (SF-12:all honours `entity`/`f.status`), PR-8.4 (CONTRACT_ACTIVATION body view), PR-8.5 (`X:contract-redirect` id check first), PR-8.6 (audit verb catalogue), PR-8.7 (Currency cell on per-currency totals rows), PR-8.8 (K-04 `activates=True` under the D-88 L7-6-Q-1 gate clause → CTR-20 tick), PR-8.10 (L8-C-Q-3, L8-R-Q-1, L8-R-Q-3, L7-4-Q-8 flaky await, L7-4-Q-6 xato corpus licence check, IMPORT_COMMIT diff Removed rows, QA-L9-5c, RPS-23 SSP book version line, PRD J-13.8/9), QA-7 L6 notes (SF-11 truncation, SF-12:request Is-active removal); PR-8.9 after its product decision. Spec anchors: `01-DECISIONS.md` D-90/D-90a/D-90e; `L9-merge.md:104-120`; `docs/BUILD_SPEC.md:6836-6862` (CTR-20); `docs/qa/G12-multi-role-qa-2026-09-17.md:31,67`.

**Added 2026-09-19 (former 'product decision' items, now required 1.0 backlog):** WEB-16 (bulk approval and approval delegations; `docs/BUILD_SPEC.md:3398`; after WEB-15), WEB-18 (shell placement captures: About, session expiry, narrow viewport and not found; `:3442`; after WEB-17), WEB-24 (design gallery and design project — the `design` e2e project that QA-5 designer evidence needs; `:3575`; after F-ADM WEB-23). CTR-20 stays CONDITIONAL on the D-88 L7-6-Q-1 gate clause (PR-8.7 Currency cell first, then PR-8.8 K-04 activation only if the seed tests, `screens.spec.ts` and `avenmoor-serial.spec.ts` pass with the GBP lines).

## Scope
Frontend (vitest + e2e rows) with one backend/OpenAPI member (`ReportRunOut.job_id`, `make openapi`, `schema.d.ts`); K-04 activation only if seed tests, `screens.spec.ts` and `avenmoor-serial.spec.ts` pass with the GBP lines (gate clause).

## Fail-first tests and evidence
Vitest cases named per item in `engineering-deferrals.md` §8 (A→B→A problem isolation; `entity=AVM-US&f.status=is:PENDING` → two pending requests; malformed id → NotFound; two-currency totals render the Currency cell per row; every backend audit action has a catalogue key or is listed raw); `make e2e` screens 52/52 (+ new rows) and avenmoor-serial; the drill on a GBP line (b90646d rate stamp) covered by a seed regression test.
Each item's BUILD_SPEC acceptance block (tests, answer keys, journeys, screens) is the closing evidence; ticks in PROGRESS/ticks.md with commit ids.

## Notes and shared files
Shares `frontend/src/routes/**`, `messages/en.json`, `DataGrid.tsx` with F-ADM/F-CTR/F-CLO; `useReportRun.ts` for PR-8.1/8.2 (one hook); backend `report_run` schema with F-RPS.

## Dependencies
PR-8.7 before PR-8.8; PR-8.9 waits for its product decision; ESLint `--max-warnings 0`.

## Do not change
Engine behaviour (return engine questions to the owning ENG lane); answer-key expected values; approval semantics without the owning control's test.

## Questions to return
Any control (CTL) whose tagged test cannot be written without a policy statement; any screen whose SCREENS row is ambiguous.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies (own worktree and `.env`; never the dev DB `erev` or ports 8190/5270; no git write beyond commits on the lane branch; fail-first tests; scratch under `.run/<lane>/`, never `/tmp`; never print `.env` or secret values; `make lint` not bare ruff; one gate slot for DB gates; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: supervisor-only targets (Docker, network, Terraform provider download, live databases) are RUN by the supervisor on request and recorded in `docs/reviews/loop/supervisor-verification.md`; `skipped-no-daemon` / `skipped-not-installed` are never passes; live cloud provisioning, image publishing, remote pushes and paid actions need Ray's explicit authorisation at that step (00-GOAL.md:75,102; PRODUCTION-CONTINUATION §Work boundaries). Every lane adding a Makefile target extends `BUILT_TARGETS`/`BUILT_PHASES` in `backend/tests/unit/test_makefile_targets.py` in the same commit (BS1-D-11). Gates before reporting: `make ci`, `make test-pg` where DB code changed, plus the lane-specific evidence below; measured, none projected.
