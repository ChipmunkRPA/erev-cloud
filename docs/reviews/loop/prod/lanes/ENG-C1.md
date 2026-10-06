# Lane ENG-C1 — ENC-5 input measures (cost to cost, labour hours, cost recovery, uninstalled materials, waste, EAC revision)

Status: in flight on `~/dev/erev-wt/l5` (`sprint/l5` from 9467de0); no lane commit yet at assembly. Record: `docs/reviews/loop/sprint/ENG-C1.md`. Owning BUILD_SPEC item ENC-5 (`docs/BUILD_SPEC.md:5263-5290`); rules S09-R-14..17 (`docs/accounting/ENGINE_SPEC_B.md:356-359`); D-76 (uninstalled materials) already ruled. Codex triage P1 is the acceptance list (24 keys); no accounting decision precedes this lane.

## Scope
Build `backend/erev_engine/stages/s09_recognition/progress_inputs.py` and register `rec.progress.cost_to_cost.v1`, `rec.progress.labour_hours.v1`, `rec.progress.cost_recovery.v1`, `rec.uninstalled_materials.v1` in `formulas.py`; dispatch COST_TO_COST / LABOUR_HOURS / COST_RECOVERY in `components.segment_target` (`components.py:262-276`, today raises S09-R-02 for them); dated approved EAC/hours pins (stage 06 already reads cost ledgers over the EAC pin, `classify.py:414-422`); waste exclusion (`is_wasted`, BUILD_SPEC.md:5276); S09-R-16 cost recovery until the first EAC pin; S09-R-17 EAC revision as an estimate change; extend `s08_estimates_late_events/decompose.py` for measure-only revisions; finding `NON_FINITE_AMOUNT` where hours are missing (fail closed).

## Keys expected to turn green (24; from `.run/l9bgate/keys-all-failed.txt`)
IFRS-SW11-ONEROUS-CONTRACT-SCOPE-IFRS15-ONLY, JE-CHK-132-S7-LOSS-OWN-PROVISION-AND-RELEASE, LOSS-GE-03-LOSS-CONTRACT-PROVISION, LOSS-S7-LOSS-OWN, MOD-CHK-027-S6-EX8, MOD-CHK-042-D18, MOD-CHK-042-INCEPTION, MOD-CHK-115, MOD-FS-03-CASEA-UPSELL-AT-SSP-SEPARATE, MOD-FS-03-CASEB-UPSELL-DISCOUNT-PROSPECTIVE, MOD-GE-02-CHANGE-ORDERS-UNPRICED-AND-CLAIM, MOD-GE-08-PARTIAL-TERMINATION-FOR-CONVENIENCE, MOD-S6-COMBINED-MOD-OWN, POS-GE-07-RETAINAGE-PRESENTATION, REC-BR-08-CUSTOMISED-TOOLING-COST-TO-COST, REC-FS-07-FIXED-FEE-EAC-HOURS-REVISION, REC-GE-01-EPC-UNINSTALLED-MATERIALS-ZERO-MARGIN, REC-S5-EX19, REC-S5-OVERTIME-OWN-OT, REC-S5-PROGRESS-VARIANTS-COSTRECOVERY, REC-S5-PROGRESS-VARIANTS-WASTE, VC-CHK-100-S3-EX21-EXTENDED, VC-GE-04-CPIF-EAC-REVISIONS, VC-GE-05-AWARD-FEE-POOL-CONSTRAINT.

## Fail-first tests and expected figures (BUILD_SPEC.md:5263 acceptance; derive independently with Fraction before asserting)
- Cost to cost: 600,000.00 before modification → 691,463.41 after modification → 826,463.41 after the cost event → 797,294.12 after EAC revision, with the exact cause split (`test_ex_09_b_*` family; EX-09-B is CHK-027's acceptance, BUILD_SPEC.md:5273).
- Uninstalled materials: revenue 2,200,000.00 with 1,500,000.00 excluded from progress (REC-GE-01; D-76); waste case 375,000.00.
- REC-S5-EX19 asserts `progress_ratio` 0.20 (ENGINE_SPEC_B.md:356).
- Missing expected hours fails closed (`NON_FINITE_AMOUNT`); cost recovery changes only on an approved EAC.
- Public replay / cutoff / FX / modified-terms / termination tests; ASC606 vs IFRS15 loss-scope check (IFRS-SW11).
- Second stops to measure and record (do not claim 24 solved by adding dispatch): stage 11 `loss.py` for LOSS/JE-CHK-132/IFRS-SW11; stage 06 catch-up re-entry for the MOD keys (the L9-ENG-B2 "bundle assembly" raise disappears with the measure); S09-R-16 for MOD-CHK-042-INCEPTION (L5-5.md:414 "a cost-based obligation names no EAC element"); the D-87 L6-5-Q-27 runner alias already applies to VC-CHK-100.

## Gates
Common set. Also-needs list to record (verify/failing-keys.md §4.2): ticks CTR-7 (MOD-GE-08), CTR-12 (VC-CHK-100), CTR-13 (VC-CHK-100), CTR-14 (LOSS-S7), CTR-18 (MOD-FS-03 A/B), ENB-10 (VC-CHK-100), DMO-6 (LOSS-GE-03) become tickable only after this lane and their own acceptance.

## Do not change
Any expected value; `TIME_ELAPSED`/event formulas; ENC-6 (`usage.py`) and ENC-8 (`breakage.py`, `royalty.py`) modules — ENG-C2/C3 own them; `s01` ledger; stage 13/14.

## Questions to return
Any key whose expected value disagrees with the rule after the measure exists (give the key, the figure, the rule id, and the derivation) — an oracle question, never a key edit; any second stop that names a rule outside S09-R-14..17.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies verbatim (fast-forward from main before starting; never checkout/reset/rebase/stash/amend/clean/push; never `git add -A`; own `.env`, never the dev DB `erev` or ports 8190/5270; fail-first tests shown failing on the base commit; no floats; formula ids additive (DG-ENG-04, P14); never edit answer-key expected values or golden files except under a cited ruling; scratch under `.run/<lane>/`, never `/tmp`; `make lint` not bare ruff; `make parity` alone; one gate slot `~/dev/erev-wt/logs/gate-slot-1|2`; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: snapshot `.run/reports/answer-keys/report.json` into `.run/<lane>/` immediately after every run (the shared path is overwritten by concurrent lanes); record "where it stops next" per key (L5-3 table format) before claiming a key; questions of policy are RETURNED to the supervisor, never decided in the lane; nothing a lane does is accounting approval (G12 is separate). Gate set before reporting: backend/tests/engine (+ new tests), `make answer-keys ID=<rg-selection.txt 182 ids>` 182 of 182, `make answer-keys` all active (base failing set `.run/l9bgate/keys-all-failed.txt`, 58 ids — no new failure; list the ids this lane turns green), `make parity`, `make properties`, `make ci`, `make test-pg`; all measured, none projected.
