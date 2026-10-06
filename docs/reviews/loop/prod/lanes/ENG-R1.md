# Lane ENG-R1 — engine ruling-register items (production work): engineering-only hardening and coverage (S items)

Worktree: any free. Record: `docs/reviews/loop/sprint/ENG-R1.md`. Source rows `engineering-deferrals.md` (class ENG, no ruling needed): PR-1.6 (WARNING catalogue items a–e: each needs a 04 T-15.4 row, PRD IMP row and the DG-ARC-13 drift pin — a product-decision-light batch the supervisor pre-approves as codes), PR-1.8, PR-2.3 (shared evidence predicate; 11 routing keys keep passing), PR-2.5, PR-2.6, PR-3.6 (oracle `akt_engine.py` RETURN_RECORDED/JET-05c model for the two CPC keys; figures ruled), PR-3.7 (oracle POL-122 default follows ALG-03; accounting confirmation noted), PR-3.10 (nonzero credit-memo FIFO fixture: proposed control 20,000 + 30,000 created, 10,000 eligible FIFO consumption → 40,000 remaining; earlier-component-first 10,000/30,000 — a proposed fixture expectation to derive from the input facts, not an observed result), PR-3.11, PR-3.12, PR-3.14, PR-4.2 (engineering half), PR-4.4 (`unit_rate` divisor sibling with an independent Fraction derivation of the termination world), PR-4.5, PR-7.4 (`books.relief.v1`), PR-7.6 (loader DG-AK-58), PR-7.8; plus the AD-16 dated-journal bridge (event → entity calendar → journal → reporting) produced as evidence with NO behaviour change.

## Fail-first
One unit test per item as named in `engineering-deferrals.md`; corpus all-active failing set unchanged; 182 selection unchanged; parity unchanged; trace `reevaluate` exact.

## Gates
Common set; `test_copy_catalogue_drift.py` pin moved with each new code.

## Do not change
Any posting timing (AD-15/AD-16 are decisions); expected values; `_concession_event` selection (ENG-J1).

## Questions to return
Any item whose fix moves a corpus cent (→ ENG-R2 with a D-number request); any WARNING code text the supervisor must approve.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies verbatim (fast-forward from main before starting; never checkout/reset/rebase/stash/amend/clean/push; never `git add -A`; own `.env`, never the dev DB `erev` or ports 8190/5270; fail-first tests shown failing on the base commit; no floats; formula ids additive (DG-ENG-04, P14); never edit answer-key expected values or golden files except under a cited ruling; scratch under `.run/<lane>/`, never `/tmp`; `make lint` not bare ruff; `make parity` alone; one gate slot `~/dev/erev-wt/logs/gate-slot-1|2`; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: snapshot `.run/reports/answer-keys/report.json` into `.run/<lane>/` immediately after every run (the shared path is overwritten by concurrent lanes); record "where it stops next" per key (L5-3 table format) before claiming a key; questions of policy are RETURNED to the supervisor, never decided in the lane; nothing a lane does is accounting approval (G12 is separate). Gate set before reporting: backend/tests/engine (+ new tests), `make answer-keys ID=<rg-selection.txt 182 ids>` 182 of 182, `make answer-keys` all active (base failing set `.run/l9bgate/keys-all-failed.txt`, 58 ids — no new failure; list the ids this lane turns green), `make parity`, `make properties`, `make ci`, `make test-pg`; all measured, none projected.
