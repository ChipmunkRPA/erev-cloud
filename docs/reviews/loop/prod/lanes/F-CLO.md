# Lane F-CLO — close, lock, reconciliation and close-run orchestration

Required 1.0 backlog (00-GOAL G1 `docs/00-GOAL.md:83`, G8 `:90`, G10 `:92`): every item below is inside the authorised objective, so no product decision precedes the worktree; the "yes" set of `spec-completeness.md` §1 is extended by the items that investigation marked "no — product decision" (Codex coverage review 2026-09-19 §2, applied by the docs agent). Sequencing: after wave 1 as capacity frees — authorised 1.0 scope sequenced by capacity; no confirmation hold precedes this lane. Record: `docs/reviews/loop/sprint/F-CLO.md`. Items: CLO-5 (data-quality monitors), CLO-6 (lock with certification, snapshots, permanent lock; CTL-015/016), CLO-7 (reopen with dual approval, re-lock diff; CTL-018), CLO-10 (journal line validation/completeness; CTL-019/020), CLO-12 (manual adjustments; CTL-014; MANUAL_ADJUSTMENTS_CLEARED gate), CLO-14 (batch acknowledgements; CTL-021), CLO-16 (billing-to-subledger reconciliation; CTL-024), CLO-17 (subledger-to-GL + auto-certification; CTL-025/026), CLO-18 (per-contract AR tie-out), CLO-19 (close run orchestration, recompute, quarantine), CLO-20 (period-end steps, summarisation, dataset freeze), CLO-24 (close run / history / multi-entity screens), CLO-25 (reconciliation screens); SCH-05/06/10 periodic tasks; PR-7.10 waterfall tie-out; PR-8.3(ii) `approval_request.entity_id` for PERIOD_LOCK/REOPEN. Spec anchors: `docs/BUILD_SPEC.md:8088-8622`; 05 SCH-05/06/10 (`05:940-947`); D-90a waterfall tie-out paragraph.

**Added 2026-09-19 (former 'product decision' items, now required 1.0 backlog):** CLO-15 (NetSuite and QuickBooks Online mock adapters and trial-balance pull; `docs/BUILD_SPEC.md:8367`; after CLO-14 and GATE-DIN; mocks only, no live calls — 00-GOAL §4), CLO-21 (multi-entity close command; `:8524`; after CLO-20), CLO-22 (demo seed close history; `:8547`; after CLO-21 and GATE-WEB; consumed by F-DMO DMO-1), CLO-27 (journey J-23 integration setup against the mock Salesforce, Stripe and NetSuite; `:8673`; after CLO-26, GATE-DIN and GATE-WEB; J-23.1 to J-23.9, J-23-AC-1/2; needs F-DIN DIN-12/13/14).

## Scope
Serial by prerequisite (CLO-5 → 6 → 7 → 10 → 12 → 14 → 16 → 17 → 18 → 19 → 20 → 24 → 25); GATE-EDS prerequisites for CLO-6/7 (EDS-4 from ENG-C4; EDS-5/6 from F-RPS); `PENDING_SUBJECTS` MANUAL_ADJUSTMENT, PERIOD_LOCK, PERIOD_REOPEN removed as they land; close gates that fail closed today (journal completeness, manual adjustments) become real gates.

## Fail-first tests and evidence
Each CLO item's acceptance tests; CTL-014/015/016/018/019/020/021/024/025/026 tagged failure-path tests (P4 records them as owed to this lane); P11 closed-period immutability property (ENG-E2) becomes meaningful after CLO-6/7; PRF-4 month-24 close (P7) measures CLO-19/20.
Each item's BUILD_SPEC acceptance block (tests, answer keys, journeys, screens) is the closing evidence; ticks in PROGRESS/ticks.md with commit ids.

## Notes and shared files
Shares migrations with P4/F-CTR; `erev_api/domain/close/*`, `journals/summarise.py`; frontend SF-05 tabs with F-WEB-R.

## Dependencies
ENG-C4 (EDS-4) and F-RPS (EDS-5/6) for CLO-6/7 (GATE-EDS prerequisite); P7 measures after CLO-19/20.

## Do not change
Engine behaviour (return engine questions to the owning ENG lane); answer-key expected values; approval semantics without the owning control's test.

## Questions to return
Any control (CTL) whose tagged test cannot be written without a policy statement; any screen whose SCREENS row is ambiguous.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies (own worktree and `.env`; never the dev DB `erev` or ports 8190/5270; no git write beyond commits on the lane branch; fail-first tests; scratch under `.run/<lane>/`, never `/tmp`; never print `.env` or secret values; `make lint` not bare ruff; one gate slot for DB gates; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: supervisor-only targets (Docker, network, Terraform provider download, live databases) are RUN by the supervisor on request and recorded in `docs/reviews/loop/supervisor-verification.md`; `skipped-no-daemon` / `skipped-not-installed` are never passes; live cloud provisioning, image publishing, remote pushes and paid actions need Ray's explicit authorisation at that step (00-GOAL.md:75,102; PRODUCTION-CONTINUATION §Work boundaries). Every lane adding a Makefile target extends `BUILT_TARGETS`/`BUILT_PHASES` in `backend/tests/unit/test_makefile_targets.py` in the same commit (BS1-D-11). Gates before reporting: `make ci`, `make test-pg` where DB code changed, plus the lane-specific evidence below; measured, none projected.
