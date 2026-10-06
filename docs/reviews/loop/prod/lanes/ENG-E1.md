# Lane ENG-E1 — PRP-1..3 platform answer-key runner and the five platform keys

Worktree: any free; DB-bound (own `.env` database; gate slot for `make test-pg`-class runs). Record: `docs/reviews/loop/sprint/ENG-E1.md`. Items PRP-1 (`docs/BUILD_SPEC.md:10009-10022`, names POS-CHK-012; hint closure REQ-BIL-002/003/005/007), PRP-2 (`:10033-10045`, DLT-CHK-020), PRP-3 (`:10056-10067`, the five report-block ids of PHASES §8.2.3); dev-guide DG-AK-22 (:2001) "platform: commands on erev_test", DG-AK-41 (:2181) `run_platform`; XR-12 fail-closed (`BUILD_SPEC.md:163`).

## Scope
`backend/tests/support/answer_keys/runners.py::run_platform` and `platform_world.py`: fresh isolated tenants, preparer/approver personas, configuration lifecycle through commands, real `known_at` timestamps, server event order, persisted `journals` / `period_states` / `reports` blocks and report cell keys (dev-guide §9.5.5-9.5.6); remove the fail-closed guard at `tests/answer_keys/test_answer_keys.py:27` (and `runners.py:2662`) only when the runner exists. No engine-runner bypass; no row inserts around approvals.

## Keys (5)
POS-CHK-012-S9-PRESENTATION-NETTING-PER-CONTRACT (PRP-1), DLT-CHK-020-CHK-022-GT07-JANUARY-2023-GROSS-AND-DELTA-JOURNALS (PRP-2), DISC-S10-DISCLOSURES-REPORTS-EX21-ROLLFORWARD-AND-TIMING, DISC-S10-DISCLOSURES-RPO-EX42-TIME-BANDS-AND-EXPEDIENT, POS-CHK-117-BALANCE-AGING-EXPORT-TIES-TO-RECLASS (PRP-3).

## Fail-first figures (BUILD_SPEC.md:10009-10083)
Netting key 80,000 revenue / 50,000 billing / 30,000 reclass; delta journal debits = credits = 240.22; rollforward/timing, RPO time bands, balance aging export ties to reclass; failed commands leave state unchanged. Current failures prove nothing about these assertions — expect product gaps (RPT-05 rows moved with EDS-4 → needs ENG-C4; balance aging RPS-12 → F-RPS) and record each as a next stop.

## Gates
Common set plus `make test-pg`; serialised with other DB work.

## Do not change
Engine; expected values; approvals code paths.

## Questions to return
Any platform behaviour a key asserts that no built item provides (name the item).

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies verbatim (fast-forward from main before starting; never checkout/reset/rebase/stash/amend/clean/push; never `git add -A`; own `.env`, never the dev DB `erev` or ports 8190/5270; fail-first tests shown failing on the base commit; no floats; formula ids additive (DG-ENG-04, P14); never edit answer-key expected values or golden files except under a cited ruling; scratch under `.run/<lane>/`, never `/tmp`; `make lint` not bare ruff; `make parity` alone; one gate slot `~/dev/erev-wt/logs/gate-slot-1|2`; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: snapshot `.run/reports/answer-keys/report.json` into `.run/<lane>/` immediately after every run (the shared path is overwritten by concurrent lanes); record "where it stops next" per key (L5-3 table format) before claiming a key; questions of policy are RETURNED to the supervisor, never decided in the lane; nothing a lane does is accounting approval (G12 is separate). Gate set before reporting: backend/tests/engine (+ new tests), `make answer-keys ID=<rg-selection.txt 182 ids>` 182 of 182, `make answer-keys` all active (base failing set `.run/l9bgate/keys-all-failed.txt`, 58 ids — no new failure; list the ids this lane turns green), `make parity`, `make properties`, `make ci`, `make test-pg`; all measured, none projected.
