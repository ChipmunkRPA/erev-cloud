# Lane ENG-C2 — ENC-6 right to invoice, usage, minimum commitments, prepaid drawdown

Worktree: `l5` after ENG-C1 merges (shared `components.py` dispatch and `formulas.py`); fast-forward from main first. Record: `docs/reviews/loop/sprint/ENG-C2.md`. Owning item ENC-6 (`docs/BUILD_SPEC.md:5291-5300`); rules S09-R-18..21 (`ENGINE_SPEC_B.md:380-383`); S04-R-06 realised variable amounts (`ENGINE_SPEC.md:1039`); D-87 L6-5-Q-16 (`docs/01-DECISIONS.md:486`) rules "delivered quantity × unit price is the right to invoice … S01-R-17 over-delivery does not apply" — no new accounting decision.

## Scope
`backend/erev_engine/stages/s09_recognition/usage.py`: RIGHT_TO_INVOICE (S09-R-18: source-resolved performance revenue = delivered quantity × unit price), USAGE (S09-R-19 rating; no USAGE_REPORTED uses a quantity × unit-price fallback), S09-R-20 minimum commitments / measurement-period TP (`usage.tier_minimum_method: ESTIMATE_MEASUREMENT_PERIOD_TP`), S09-R-21 prepaid drawdown counting `USAGE_REPORTED.quantity` (shared with ENG-C3's breakage — build once here, C3 consumes); the S04-R-06 realised path (shared with C3's royalties — coordinate: C2 builds the realised-amount hook, C3 adds the royalty producer); S01-R-17 exemption for RTI obligations in `s01_canonicalize/ledger.py:213` (method-aware; genuine unit over-delivery still fires).

## Keys expected to turn green (6)
POB-S2-EX12A-OWNVOLUMES (USAGE), POS-CHK-010 (`PROGRESS_OVER_DELIVERY` delivered 120 vs booked 1; key YAML:180-186 P1-TM qty "1", unit_price 25.00, total_price 0.00; :197 delivery 120), POS-CHK-014-S5-PROGRESS-VARIANTS-RIGHT-TO-INVOICE, REC-CHK-014-S5-PROGRESS-VARIANTS-RTI (BUILD_SPEC.md:5306 names it), REC-FS-08-TM-RIGHT-TO-INVOICE, REC-RB-05-CAPITATION-PMPM-RATE-AMENDMENT. VC-FS-02 reaches its later checkpoints only with ENG-C2a (direction) and ENG-C4 (EDS-4) — record its next stop, do not claim it.

## Fail-first tests and expected figures (BUILD_SPEC.md:5291)
- 120 hours × 25.00 = 3,000.00 recognised even with booking quantity 1; invoices without performance create no revenue.
- Minimum estimate 140,000 → 120,000: Q1 35,000, Q2 25,000, −10,000 catch-up and −5,000 prior-period portion (the prior-period trace node itself is EDS-4 / ENG-C4 — assert the amounts, record the node as the next stop).
- Tier boundaries and period attribution; prepaid drawdown units; a unit over-delivery on a UNITS_DELIVERED obligation still raises `PROGRESS_OVER_DELIVERY` (control).

## Gates
Common set; all-active failing set must shrink by exactly the ids listed (plus none new). Also-needs: RPS-12 names POS-CHK-010 (:9077) — tick belongs to F-RPS.

## Do not change
Expected values (the VC-FS-02 figures TP 220k/280k/295k, revenue 55k/140k/233,333.33/295k are ruled unchanged, CLAUDE-RESPONSE 09:04); ENC-5 code; refund-liability derivation (`refund_liability.py:444` is ENG-C2a's); stage 15.

## Questions to return
The S09-R-20 measurement-period treatment of a VOLUME_TIER INCREASE if S09-R-20 is silent (AD-21 — the refund model scope is ruled: a positive no-target overage creates no refund liability, explicit targets on the five refund-settled types are measured in either direction, BONUS / VOLUME_TIER explicit targets fail closed; already returned by C2a; add facts, do not decide); any RTI key whose `total_price 0.00` line conflicts with S04 pricing rules.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies verbatim (fast-forward from main before starting; never checkout/reset/rebase/stash/amend/clean/push; never `git add -A`; own `.env`, never the dev DB `erev` or ports 8190/5270; fail-first tests shown failing on the base commit; no floats; formula ids additive (DG-ENG-04, P14); never edit answer-key expected values or golden files except under a cited ruling; scratch under `.run/<lane>/`, never `/tmp`; `make lint` not bare ruff; `make parity` alone; one gate slot `~/dev/erev-wt/logs/gate-slot-1|2`; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: snapshot `.run/reports/answer-keys/report.json` into `.run/<lane>/` immediately after every run (the shared path is overwritten by concurrent lanes); record "where it stops next" per key (L5-3 table format) before claiming a key; questions of policy are RETURNED to the supervisor, never decided in the lane; nothing a lane does is accounting approval (G12 is separate). Gate set before reporting: backend/tests/engine (+ new tests), `make answer-keys ID=<rg-selection.txt 182 ids>` 182 of 182, `make answer-keys` all active (base failing set `.run/l9bgate/keys-all-failed.txt`, 58 ids — no new failure; list the ids this lane turns green), `make parity`, `make properties`, `make ci`, `make test-pg`; all measured, none projected.
