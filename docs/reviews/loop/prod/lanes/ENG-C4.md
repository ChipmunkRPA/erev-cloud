# Lane ENG-C4 — EDS-4 revenue from obligations satisfied in prior periods, disaggregation tags; EDS-7; DISC-CATCH-UP input clarification

Worktree: `l4` after ENG-C2a (or any free worktree — touches only stage 15 and the two DISC/JE keys' runner path). Record: `docs/reviews/loop/sprint/ENG-C4.md`. Owning items EDS-4 (`docs/BUILD_SPEC.md:7845-7868`), EDS-7 (`:7918`, names DISC-CHK-101 at :7931); rules S15-R-13/14 (`ENGINE_SPEC_B.md:2201-2202`), S08-R-16 (`ENGINE_SPEC.md:1584`, node defined at `s08 decompose.py:65,291`, "called by stage 15" per `s08 __init__.py:12-13`); D-87 L6-5-Q-27 alias ruled (`docs/01-DECISIONS.md:484`). Note the plan.json stale `in_scope` status of EDS-4 (I-13).

## Scope
`s15_disclosures/prior_period.py` (consumer of `decompose_prior_period`; emits `estimate.prior_period.v1` / `disc.prior_period_sum.v1` and publishes `revenue_prior_period:<ob>:<period>` per entity calendar from `RecognitionState.allocated` and posted origins), `disaggregation.py` (tags); RPT-05 builder inputs that moved with EDS-4 (L6-3.md:318) — expose the engine measure; the platform report itself is F-RPS/ENG-E1. Second half (after the supervisor's input-clarification ruling AD-22): DISC-CATCH-UP-BY-CAUSE key notes carry the explicit `quantity_delta 0` (or unchanged total quantity 1) for MOD-DISC-01 (YAML:112-118) — an input clarification with a recorded trail, not an oracle change; `NEGATIVE_WEIGHT` guard untouched.

## Keys expected to turn green
DISC-CHK-101-S3-EX23-CASEB-PRIOR-PERIOD-POB-REVENUE (`trace revenue_prior_period:C-DISC-101/L1-PRODUCTS:FY2027-P02` 5,000.00 — its only mismatch), JE-CHK-026-CHK-100-S3-EX21-EXTENDED-BONUS-CATCH-UP (FY2027-P01 60,000.00; FY2027-P12 0.00). After the ruling: DISC-CATCH-UP-BY-CAUSE-ESTIMATE-CHANGE-AND-MODIFICATION (expected cumulative 78,000.00, April 28,000.00, causes 5,000 + 10,000 + 13,000, prior-period 15,000 — unproven beyond the first blocker; record where it stops next). VC-FS-02's `revenue_prior_period` assertion (YAML:244) becomes reachable (with C2/C2a).

## Fail-first tests and figures
Zero nodes; late carry; cause separation (estimate change vs modification vs progress); report totals; replay; each entity's actual calendar (BUILD_SPEC.md:7845 test list). `reevaluate` exact on the new nodes (P14).

## Gates
Common set. Also-needs: RPS-3 names DISC-CATCH-UP, DISC-CHK-101, DISC-S10-REPORTS-EX21 (:8804); RPS-4 names DISC-S10-RPO-EX42 — platform keys stay with ENG-E1.

## Do not change
Stage 06 weights (`weights.py:285`) or the runner `_convert_terms` semantics (`runners.py:645-706`) — the DISC-CATCH-UP fix is an input clarification, not a runner change, unless the supervisor rules otherwise; expected values.

## Questions to return
The AD-22 ruling request with the verified mechanism (ΔQ = quantity − in-force → −1 → nondistinct weight −50,000); any disaggregation tag whose source field is not in T-CON.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies verbatim (fast-forward from main before starting; never checkout/reset/rebase/stash/amend/clean/push; never `git add -A`; own `.env`, never the dev DB `erev` or ports 8190/5270; fail-first tests shown failing on the base commit; no floats; formula ids additive (DG-ENG-04, P14); never edit answer-key expected values or golden files except under a cited ruling; scratch under `.run/<lane>/`, never `/tmp`; `make lint` not bare ruff; `make parity` alone; one gate slot `~/dev/erev-wt/logs/gate-slot-1|2`; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: snapshot `.run/reports/answer-keys/report.json` into `.run/<lane>/` immediately after every run (the shared path is overwritten by concurrent lanes); record "where it stops next" per key (L5-3 table format) before claiming a key; questions of policy are RETURNED to the supervisor, never decided in the lane; nothing a lane does is accounting approval (G12 is separate). Gate set before reporting: backend/tests/engine (+ new tests), `make answer-keys ID=<rg-selection.txt 182 ids>` 182 of 182, `make answer-keys` all active (base failing set `.run/l9bgate/keys-all-failed.txt`, 58 ids — no new failure; list the ids this lane turns green), `make parity`, `make properties`, `make ci`, `make test-pg`; all measured, none projected.
