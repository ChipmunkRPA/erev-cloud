# Lane ENG-C5 — ENB-9 opening-balance flows through stages 10/13/14 (ONB-CHK-121)

Worktree: `l1` after ENG-D1 merges (shared `s13_books` part sets and `s14_posting/targets.py`). Record: `docs/reviews/loop/sprint/ENG-C5.md`. Rules S07-R-08 (`ENGINE_SPEC.md:1450`), S07-INV-01..03; BUILD_SPEC ENB-9 (`docs/BUILD_SPEC.md:4990-5016`, ticked — the stage 07 module exists; the gap is the flow); D-88 L7-5-Q-9 directs the lane; D-90 (`docs/01-DECISIONS.md:572`) deferred the key beyond the rc together with ENB-9 — production work in this lane after ENG-D1; D-91 register "ONB-CHK-121 pre-cutover" (:722). Acquisition-policy approval is separate (AD-27) and does not block the engineering.

## Scope
Measure first (L8-D.md:237 is an inference): trace `s07_onboarding/opening.py` baseline `billed_cum` (240,000.00 ASC606 / 90,000.00 IFRS15) through the stage 10 position, stage 13 part binding and stage 14 posting; then fix so the opening liability is relieved rather than re-recognised: no pre-cutover revenue in the first open period (FY2025-P12 CL Dr / REVENUE Cr 120,000.00 must not appear), no CONTRACT_ASSET 1200 dr 130,000.00, CL C-ACQ-SUB@US01 FY2026-P01 110,000.00 (ASC606) / 82,500.00 (IFRS15).

## Fail-first
`make answer-keys ID=ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION` on the base: 12 mismatches (january-2026-asc606, year-end-2026-asc606, january-2026-ifrs15, year-end-2026-ifrs15; `cutover-no-postings` passes). After: 1 of 1; 120,000 opening ASC606 / 10,000 monthly vs 90,000 IFRS / 7,500 monthly (BUILD_SPEC.md:4990); repeat compute posts nothing new; cutover freeze; FX and delta journals; BUILD_SPEC tests `test_ex_07_a_opening_balances_mode_a`, `test_chk_121_business_combination`, `test_s07_inv_02_allocation_sum` still pass.

## Gates
Common set; key re-enters `rg-selection.txt` at merge (supervisor edits the selection). Also-needs: LMG-7 (:9739), PLF-3 (:1782), AKS-7 (:6265) name this key.

## Do not change
D1's deposit part sets; B4's `_control_flows`; expected values; stage 07 rules.

## Questions to return
Any acquisition-policy question the flow exposes (e.g., IFRS fair-value split basis) with figures — AD-27.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies verbatim (fast-forward from main before starting; never checkout/reset/rebase/stash/amend/clean/push; never `git add -A`; own `.env`, never the dev DB `erev` or ports 8190/5270; fail-first tests shown failing on the base commit; no floats; formula ids additive (DG-ENG-04, P14); never edit answer-key expected values or golden files except under a cited ruling; scratch under `.run/<lane>/`, never `/tmp`; `make lint` not bare ruff; `make parity` alone; one gate slot `~/dev/erev-wt/logs/gate-slot-1|2`; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: snapshot `.run/reports/answer-keys/report.json` into `.run/<lane>/` immediately after every run (the shared path is overwritten by concurrent lanes); record "where it stops next" per key (L5-3 table format) before claiming a key; questions of policy are RETURNED to the supervisor, never decided in the lane; nothing a lane does is accounting approval (G12 is separate). Gate set before reporting: backend/tests/engine (+ new tests), `make answer-keys ID=<rg-selection.txt 182 ids>` 182 of 182, `make answer-keys` all active (base failing set `.run/l9bgate/keys-all-failed.txt`, 58 ids — no new failure; list the ids this lane turns green), `make parity`, `make properties`, `make ci`, `make test-pg`; all measured, none projected.
