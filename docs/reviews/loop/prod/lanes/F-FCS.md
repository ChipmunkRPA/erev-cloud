# Lane F-FCS — forecast, scenarios and deal-desk preview (phase 21 FCS)

Required 1.0 backlog (00-GOAL §2.11 `docs/00-GOAL.md:66` — "What-if runs on the same engine in a scenario tenant; a deal-desk allocation preview"; G1 `:83`, G8 `:90`): the eight FCS items the spec-completeness investigation marked "no — product decision" are inside the authorised objective (Codex coverage review 2026-09-19 §2). Sequencing: after wave 1 as capacity frees; after F-SNP (SNP-2 sandbox load is FCS-1's prerequisite) and GATE-PRP (ENG-E1/E2). Record: `docs/reviews/loop/sprint/F-FCS.md`. Items: FCS-1 (forecast tables and scenario tenants; `docs/BUILD_SPEC.md:10221`; prerequisites GATE-PRP, SNP-2), FCS-2 (forecast event sets and scenario refresh; `:10247`), FCS-3 (forecast runs and forecast outputs; `:10272`), FCS-4 (actual vs forecast report; `:10296`), FCS-5 (what-if modifications in scenario tenants; `:10320`; GATE-CTR — F-CTR CTR-17 modifications object), FCS-6 (deal-desk allocation preview and scenario save; `:10343`; GATE-ENA), FCS-7 (scenario, forecast event set and forecast run screens; `:10367`; consumed by F-DMO DMO-1 and journey J-18), FCS-8 (deal preview screen; `:10391`). Spec anchors: phase 21 `docs/BUILD_SPEC.md:10206-10425`; GATE-FCS `:10414`; GATE-AIX depends on GATE-FCS (AIX-1 prerequisite).

## Scope
Serial FCS-1 → 8; scenario tenants are sandbox-kind tenants (F-SNP) running the unchanged engine; forecast outputs are engine outputs on forecast event sets, never a second calculation path; deal preview reuses stage 05 allocation on a draft.

## Boundary (00-GOAL §4 `docs/00-GOAL.md:98`; §2 item 14 `:75`)
No external data source or third-party call; scenario tenants never post or export over production tenants (CTL-043 sandbox restriction, F-SNP); Terraform artifacts are never applied.

## Fail-first tests and evidence
Each item's BUILD_SPEC acceptance block (tests, answer keys, journeys, screens) on a clean tree; determinism: a forecast run on a frozen event set reproduces byte-identical outputs (P8 replay determinism, T1); FCS screens' vitest/e2e rows; ticks in PROGRESS/ticks.md with commit ids; lane record.

## Notes and shared files
Shares `domain/tenants/*` and the snapshot dataset format with F-SNP and P7 (`SANDBOX_SEED`); reads `s06_modifications` and stage 05 allocation (read-only; engine questions return to the owning ENG lane); frontend routes and `messages/en.json` with F-WEB-R; migrations serialised.

## Dependencies
F-SNP SNP-1..2 before FCS-1; GATE-PRP (ENG-E1 runner, ENG-E2 properties) before FCS-1 per the BUILD_SPEC prerequisite; F-CTR CTR-17 before FCS-5; F-AIX (AIX-1) and F-DMO (DMO-1, DMO-29 J-18) depend on this lane.

## Do not change
Engine behaviour; answer-key expected values; sandbox restrictions (CTL-043) without the owning control's test.

## Questions to return
Whether GATE-PRP must be fully ticked before FCS-1 or only the platform runner (PRP-1..3) it names; scenario-tenant retention and quota defaults (CFG question for P5).

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies (own worktree and `.env`; never the dev DB `erev` or ports 8190/5270; no git write beyond commits on the lane branch; fail-first tests; scratch under `.run/<lane>/`, never `/tmp`; never print `.env` or secret values; `make lint` not bare ruff; one gate slot for DB gates; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: supervisor-only targets (Docker, network, Terraform provider download, live databases) are RUN by the supervisor on request and recorded in `docs/reviews/loop/supervisor-verification.md`; `skipped-no-daemon` / `skipped-not-installed` are never passes; live cloud provisioning, image publishing, remote pushes and paid actions need Ray's explicit authorisation at that step (00-GOAL.md:75,102; PRODUCTION-CONTINUATION §Work boundaries). Every lane adding a Makefile target extends `BUILT_TARGETS`/`BUILT_PHASES` in `backend/tests/unit/test_makefile_targets.py` in the same commit (BS1-D-11). Gates before reporting: `make ci`, `make test-pg` where DB code changed, plus the lane-specific evidence below; measured, none projected.
