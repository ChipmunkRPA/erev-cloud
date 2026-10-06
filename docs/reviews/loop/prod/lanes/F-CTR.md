# Lane F-CTR — contracts platform completion

Required 1.0 backlog (00-GOAL G1 `docs/00-GOAL.md:83`, G8 `:90`, G10 `:92`): every item below is inside the authorised objective, so no product decision precedes the worktree; the "yes" set of `spec-completeness.md` §1 is extended by the items that investigation marked "no — product decision" (Codex coverage review 2026-09-19 §2, applied by the docs agent). Sequencing: after wave 1 as capacity frees — authorised 1.0 scope sequenced by capacity; no confirmation hold precedes this lane. Record: `docs/reviews/loop/sprint/F-CTR.md`. Items: CTR-6 (manual event maker-checker, CTL-009), CTR-11 (void with reversal lines, CTL-046), CTR-13 (portfolios), CTR-14 (contract costs, material rights, loss provisions, FX layers, billing plans as platform objects), CTR-16 (policy impact simulation, CTL-031), CTR-17 (modifications object, guided classification, impact preview, regroup; D-90b option (i) needs the AD-19 removal-attribution sign-off), CTR-18 (subscription changes/terminations), CTR-24 (SF-03:new draft form, modifications/history tabs), CTR-25 (estimates screens), CTR-27 (modification wizard); plus PR-1.3 (S10-R-07 422 clause on event commands and CSV v2 import), PR-3.2 POL-247 adoption profile, PR-3.5 per-element promise link, PR-7.2 CSV v2 modifications template, PR-7.5 all-excluded booking path, PR-7.6 API guard on `CG-CON-<n>`, ENA-4b licence-nature drawer. Spec anchors: `docs/BUILD_SPEC.md:6466-7033`; `01-DECISIONS.md` D-90b/D-90c; `04-DATA_MODEL.md:5137,5590` (S10-R-07 422).

**Added 2026-09-19 (former 'product decision' items, now required 1.0 backlog):** CTR-28 (search and the command palette results; `docs/BUILD_SPEC.md:7033`; after CTR-27).

## Scope
Serial by prerequisite (CTR-6 → 11 → 13 → 14 → 16 → 17 → 18 → 24 → 25 → 27); migrations serialised with P4/F-CLO; `PENDING_SUBJECTS` entries CONTRACT_VOID and MODIFICATION removed as their subjects land; CTR-17 rejects repeated obligation keys in T-CON-06 lines and carries the fail-closed FIXED-boundary quantity invariant with the OPENING_BALANCE carve-out.

## Fail-first tests and evidence
BUILD_SPEC:6766-6780 (`test_classify_k02_upgrade`, `test_preview_k02_upgrade_figures`, `test_separate_contract_books_new_contract`, `test_regroup_*`, CTL-007); `make answer-keys ID=MOD-S6-EX5-CASEA,…` 5 of 5 through the native path; API 422 matrix for `INVOICE_STATUS_UPDATE_MISMATCH` (amount; both obligation keys non-null and different; null accepted; same-amount accepted; batch and stored-stream; CSV import); D-90b/D-90c `MOD_UNIT_HISTORY_AMBIGUOUS` exercised through the native path.
Each item's BUILD_SPEC acceptance block (tests, answer keys, journeys, screens) is the closing evidence; ticks in PROGRESS/ticks.md with commit ids.

## Notes and shared files
Shares `erev_api/domain/contracts/*`, migrations, `PENDING_SUBJECTS` with F-CLO; frontend routes with F-WEB-R; option (i) unit layers touch `s06_modifications` (coordinate with any ENG lane in stage 06).

## Dependencies
CTR-16 before CTR-17 (BUILD_SPEC prerequisite); AD-19 before option (i); ENG-B4 kernel helper for PR-1.3.

## Do not change
Engine behaviour (return engine questions to the owning ENG lane); answer-key expected values; approval semantics without the owning control's test.

## Questions to return
Any control (CTL) whose tagged test cannot be written without a policy statement; any screen whose SCREENS row is ambiguous.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies (own worktree and `.env`; never the dev DB `erev` or ports 8190/5270; no git write beyond commits on the lane branch; fail-first tests; scratch under `.run/<lane>/`, never `/tmp`; never print `.env` or secret values; `make lint` not bare ruff; one gate slot for DB gates; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: supervisor-only targets (Docker, network, Terraform provider download, live databases) are RUN by the supervisor on request and recorded in `docs/reviews/loop/supervisor-verification.md`; `skipped-no-daemon` / `skipped-not-installed` are never passes; live cloud provisioning, image publishing, remote pushes and paid actions need Ray's explicit authorisation at that step (00-GOAL.md:75,102; PRODUCTION-CONTINUATION §Work boundaries). Every lane adding a Makefile target extends `BUILT_TARGETS`/`BUILT_PHASES` in `backend/tests/unit/test_makefile_targets.py` in the same commit (BS1-D-11). Gates before reporting: `make ci`, `make test-pg` where DB code changed, plus the lane-specific evidence below; measured, none projected.
