# Lane F-SNP — sandbox tenants

Required 1.0 backlog (00-GOAL G1 `docs/00-GOAL.md:83`, G8 `:90`, G10 `:92`): every item below is inside the authorised objective, so no product decision precedes the worktree; the "yes" set of `spec-completeness.md` §1 is extended by the items that investigation marked "no — product decision" (Codex coverage review 2026-09-19 §2, applied by the docs agent). Sequencing: after wave 1 as capacity frees — authorised 1.0 scope sequenced by capacity; no confirmation hold precedes this lane. Record: `docs/reviews/loop/sprint/F-SNP.md`. Items: SNP-1 (tenant snapshots + dataset), SNP-2 (sandbox load + determinism verification), SNP-3 (reset by supersession), SNP-4 (restrictions, immutable tenant kind; CTL-043; 403 `sandbox-restricted`, DB-15), SNP-5 (sandbox copies screen + banner BR-UX-03). Spec anchors: `docs/BUILD_SPEC.md:9416-9521`.

## Scope
Serial SNP-1 → 5; snapshots also serve LMG-4 replay, PRF `SANDBOX_SEED` (P7) and OPR-11 restore verification (P6) — coordinate the snapshot dataset format with P7 early.

## Fail-first tests and evidence
SNP acceptance tests; CTL-043 tagged test (a sandbox never posts/exports over production); determinism: load twice → identical hashes; P9 idempotency property (ENG-E2) reuses the snapshot.
Each item's BUILD_SPEC acceptance block (tests, answer keys, journeys, screens) is the closing evidence; ticks in PROGRESS/ticks.md with commit ids.

## Notes and shared files
Migrations serialised; `domain/tenants/*`; frontend banner with F-WEB-R.

## Dependencies
None hard; F-LMG and T1 (GPB-3) depend on it.

Annotation (docs lane; supervisor ruling 2026-09-20; docs first, the line above kept as written): the "None hard" prerequisite wording does not govern — BUILD_SPEC SNP-1's GATE-RPS and GATE-PLF are integration gates of this lane (readiness matrix rows SNP-1 to SNP-5 and CTL-043); the preparation slice on sprint/l23-fsnp (worktree l23) is CPU-only until the databases are provisioned.

## Do not change
Engine behaviour (return engine questions to the owning ENG lane); answer-key expected values; approval semantics without the owning control's test.

## Questions to return
Any control (CTL) whose tagged test cannot be written without a policy statement; any screen whose SCREENS row is ambiguous.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies (own worktree and `.env`; never the dev DB `erev` or ports 8190/5270; no git write beyond commits on the lane branch; fail-first tests; scratch under `.run/<lane>/`, never `/tmp`; never print `.env` or secret values; `make lint` not bare ruff; one gate slot for DB gates; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: supervisor-only targets (Docker, network, Terraform provider download, live databases) are RUN by the supervisor on request and recorded in `docs/reviews/loop/supervisor-verification.md`; `skipped-no-daemon` / `skipped-not-installed` are never passes; live cloud provisioning, image publishing, remote pushes and paid actions need Ray's explicit authorisation at that step (00-GOAL.md:75,102; PRODUCTION-CONTINUATION §Work boundaries). Every lane adding a Makefile target extends `BUILT_TARGETS`/`BUILT_PHASES` in `backend/tests/unit/test_makefile_targets.py` in the same commit (BS1-D-11). Gates before reporting: `make ci`, `make test-pg` where DB code changed, plus the lane-specific evidence below; measured, none projected.
