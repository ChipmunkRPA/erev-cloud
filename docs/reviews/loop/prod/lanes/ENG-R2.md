# Lane ENG-R2 — ruling-register items requiring a D-number re-baseline (production work; blocked on the D-number)

Items: PR-2.1 L9-C606-02-Q4 (one apportionment over exact quotas on the targeted path; `routing._incremental`; ±1 minor unit in up to 10 targeted keys; SSP 100/200, fixed 210, three targeted +0.01 → 70.00/140.03 vs exact 70.01/140.02) and PR-2.2 L9-C606-02-Q5 (`targeted.totals` double rounding, `targeted.py:169-183`; 100.01 / 33.33 → 66.68/66.66 vs 66.67/66.67). Class ENG + D-number (D-77: keys change only through new D-numbers).

## Before the D-number (allowed now)
Measure the corpus impact: which keys carry a Q5-affected inception state or a Q4-affected targeted sequence; derive the new cents with Fraction in `.run/ENG-R2/derive.py`; return the list and derivation to the supervisor.

## After the D-number
S05-INV-02 property-style test after n targeted changes; one `largest_remainder` over exact totals; the affected keys regenerated with the filed derivation; formula ids kept with additive params or v3 registered.

## Gates, do-not-change, questions
Common set; no key edit before the D-number; return the impact list. Record `docs/reviews/loop/sprint/ENG-R2.md`.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies verbatim (fast-forward from main before starting; never checkout/reset/rebase/stash/amend/clean/push; never `git add -A`; own `.env`, never the dev DB `erev` or ports 8190/5270; fail-first tests shown failing on the base commit; no floats; formula ids additive (DG-ENG-04, P14); never edit answer-key expected values or golden files except under a cited ruling; scratch under `.run/<lane>/`, never `/tmp`; `make lint` not bare ruff; `make parity` alone; one gate slot `~/dev/erev-wt/logs/gate-slot-1|2`; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: snapshot `.run/reports/answer-keys/report.json` into `.run/<lane>/` immediately after every run (the shared path is overwritten by concurrent lanes); record "where it stops next" per key (L5-3 table format) before claiming a key; questions of policy are RETURNED to the supervisor, never decided in the lane; nothing a lane does is accounting approval (G12 is separate). Gate set before reporting: backend/tests/engine (+ new tests), `make answer-keys ID=<rg-selection.txt 182 ids>` 182 of 182, `make answer-keys` all active (base failing set `.run/l9bgate/keys-all-failed.txt`, 58 ids — no new failure; list the ids this lane turns green), `make parity`, `make properties`, `make ci`, `make test-pg`; all measured, none projected.
