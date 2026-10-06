# Lane F-RPS — reports, disclosures, registers, evidence packs, audit log screen; EDS-5/6; RPT-06/07 basis

Required 1.0 backlog (00-GOAL G1 `docs/00-GOAL.md:83`, G8 `:90`, G10 `:92`): every item below is inside the authorised objective, so no product decision precedes the worktree; the "yes" set of `spec-completeness.md` §1 is extended by the items that investigation marked "no — product decision" (Codex coverage review 2026-09-19 §2, applied by the docs agent). Sequencing: after wave 1 as capacity frees — authorised 1.0 scope sequenced by capacity; no confirmation hold precedes this lane. Record: `docs/reviews/loop/sprint/F-RPS.md`. Items: RPS-8 (journal/modification/close registers), RPS-10 (access/config/approvals/audit registers), RPS-11 (judgement/estimate/scope-exclusion/loss registers), RPS-12 (contract-cost rollforward, bridges, intercompany pairs, balance aging — POS-CHK-117), RPS-15 (disclosure snapshots + pack), RPS-16 (period evidence packs, contract sample packs; CTL-041), RPS-21 (audit log + chain verification screens); EDS-5 (contract-cost rollforward), EDS-6 (lock snapshot content, manifest hashing, variance between closes); PR-4.3 platform RPT-06/07 on the S15-R-12 basis (snapshot openings; first-period `LATE_EVENTS` −ρ migration note). Spec anchors: `docs/BUILD_SPEC.md:8958-9284` (RPS), `:7869-7894` (EDS-5/6); D-88 L6-3-Q-33; D-91 :700-701.

**Added 2026-09-19 (former 'product decision' items, now required 1.0 backlog):** RPS-9 (SSP reports; `docs/BUILD_SPEC.md:8985`; after RPS-8), RPS-13 (bookings, billings and revenue; variance between closes; `:9087`; after RPS-12 and GATE-EDS), RPS-14 (data extracts for BI; `:9111`; after RPS-13), RPS-18 (report run register, run record and disclosure pack screens; `:9215`; after RPS-17), RPS-19 (revenue and close dashboard screens — carries the home dashboard REQ-RPT-016, P0, 1.0, `docs/03-REQUIREMENTS.md:547`; `:9239`; after RPS-18), RPS-20 (evidence pack screens; `:9261`; after RPS-19), RPS-23 (journey J-01 legacy user onboarding part 1; `:9334`; after RPS-22, GATE-DIN, GATE-RFD, GATE-WEB; needs F-ADM WEB-13/WEB-19/RFD-18/RFD-23 and the fresh-tenant invitation flow), RPS-24 (journey J-01 part 2; `:9362`; after RPS-23; needs RPS-21, F-DIN DIN-18 and the QuickBooks Online realm of F-CLO CLO-15).

## Scope
Report builders on the RV framework (RPS-2 ticked); EDS-5/6 engine measures then platform rows; RPT-07 rows equal the engine rollforward on the demo world (V9 tie); snapshot openings need F-SNP (or a recorded interim opening rule).

## Fail-first tests and evidence
RPS-3/4/12 acceptance keys through ENG-E1's platform runner (DISC-S10-*, POS-CHK-117); CTL-041 tagged test; `test_rpt_07_rows_equal_engine_rollforward`; DEV V9 parity unchanged.
Each item's BUILD_SPEC acceptance block (tests, answer keys, journeys, screens) is the closing evidence; ticks in PROGRESS/ticks.md with commit ids.

## Notes and shared files
Shares `erev_api/domain/reports/builders/*` with ENG-E1 (read-only there); `s15_disclosures` engine measures with ENG-C4 (EDS-4 first).

## Dependencies
ENG-C4 (EDS-4) → EDS-5 → EDS-6; F-SNP for snapshot openings (PR-4.3).

## Do not change
Engine behaviour (return engine questions to the owning ENG lane); answer-key expected values; approval semantics without the owning control's test.

## Questions to return
Any control (CTL) whose tagged test cannot be written without a policy statement; any screen whose SCREENS row is ambiguous.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies (own worktree and `.env`; never the dev DB `erev` or ports 8190/5270; no git write beyond commits on the lane branch; fail-first tests; scratch under `.run/<lane>/`, never `/tmp`; never print `.env` or secret values; `make lint` not bare ruff; one gate slot for DB gates; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: supervisor-only targets (Docker, network, Terraform provider download, live databases) are RUN by the supervisor on request and recorded in `docs/reviews/loop/supervisor-verification.md`; `skipped-no-daemon` / `skipped-not-installed` are never passes; live cloud provisioning, image publishing, remote pushes and paid actions need Ray's explicit authorisation at that step (00-GOAL.md:75,102; PRODUCTION-CONTINUATION §Work boundaries). Every lane adding a Makefile target extends `BUILT_TARGETS`/`BUILT_PHASES` in `backend/tests/unit/test_makefile_targets.py` in the same commit (BS1-D-11). Gates before reporting: `make ci`, `make test-pg` where DB code changed, plus the lane-specific evidence below; measured, none projected.
