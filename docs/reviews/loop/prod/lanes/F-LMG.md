# Lane F-LMG — legacy migration and onboarding from other systems

Required 1.0 backlog (00-GOAL G1 `docs/00-GOAL.md:83`, G8 `:90`, G10 `:92`): every item below is inside the authorised objective, so no product decision precedes the worktree; the "yes" set of `spec-completeness.md` §1 is extended by the items that investigation marked "no — product decision" (Codex coverage review 2026-09-19 §2, applied by the docs agent). Sequencing: after wave 1 as capacity frees — authorised 1.0 scope sequenced by capacity; no confirmation hold precedes this lane. Record: `docs/reviews/loop/sprint/F-LMG.md`. Items: LMG-1 (batches, profiling, source handling), LMG-2 (opening balances staging + field mapping), LMG-3 (migration reconciliation + promotion; CTL-048), LMG-4 (template replay into a sandbox + promotion; GPB-3 prerequisite), LMG-6 (onboarding from other systems), LMG-7 (acquired contracts from business combinations; names ONB-CHK-121). Spec anchors: `docs/BUILD_SPEC.md:9567-9749`; `docs/legacy/DEVIATIONS.md`; GPB-3 (`:9936`).

**Added 2026-09-19 (former 'product decision' items, now required 1.0 backlog):** LMG-5 (parallel-run comparison report; `docs/BUILD_SPEC.md:9676`; after LMG-4), LMG-8 (migrations list and new migration screens; `:9749`; after LMG-7), LMG-9 (migration detail screen; `:9773`; after LMG-8), LMG-10 (journey J-20 legacy `ASC606.db` import with opening balances; `:9798`; after LMG-9; J-20.1 to J-20.5), LMG-11 (journey J-21 legacy template replay into a sandbox, then promotion; `:9829`; after LMG-10; J-21.1 to J-21.5).

## Scope
Serial LMG-1 → 2 → 3 → 4 → 6 → 7; `PENDING_SUBJECTS` MIGRATION_PROMOTION removed at LMG-3; `migration-guide.md` (P8/DEP-7) documents modes (a)/(b) as built.

## Fail-first tests and evidence
LMG acceptance tests; CTL-048 tagged test; `make parity K=point_in_time_equivalence` becomes runnable (T1 writes the reader); ONB-CHK-121 through the platform path after ENG-C5.
Each item's BUILD_SPEC acceptance block (tests, answer keys, journeys, screens) is the closing evidence; ticks in PROGRESS/ticks.md with commit ids.

## Notes and shared files
Shares `domain/imports/*` with ENG-C2a (direction) and F-CTR (CSV v2); migrations serialised.

## Dependencies
F-SNP (SNP-1..3) before LMG-4; ENG-C5 before LMG-7's key evidence.

## Do not change
Engine behaviour (return engine questions to the owning ENG lane); answer-key expected values; approval semantics without the owning control's test.

## Questions to return
Any control (CTL) whose tagged test cannot be written without a policy statement; any screen whose SCREENS row is ambiguous.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies (own worktree and `.env`; never the dev DB `erev` or ports 8190/5270; no git write beyond commits on the lane branch; fail-first tests; scratch under `.run/<lane>/`, never `/tmp`; never print `.env` or secret values; `make lint` not bare ruff; one gate slot for DB gates; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: supervisor-only targets (Docker, network, Terraform provider download, live databases) are RUN by the supervisor on request and recorded in `docs/reviews/loop/supervisor-verification.md`; `skipped-no-daemon` / `skipped-not-installed` are never passes; live cloud provisioning, image publishing, remote pushes and paid actions need Ray's explicit authorisation at that step (00-GOAL.md:75,102; PRODUCTION-CONTINUATION §Work boundaries). Every lane adding a Makefile target extends `BUILT_TARGETS`/`BUILT_PHASES` in `backend/tests/unit/test_makefile_targets.py` in the same commit (BS1-D-11). Gates before reporting: `make ci`, `make test-pg` where DB code changed, plus the lane-specific evidence below; measured, none projected.
