# Lane ENG-C8 — END-11 / END-12 JET template check tests (re-labelled from ENG-C7 on 2026-09-19: lane ENG-C7 is the ENC-16 loss-provision lane dispatched under D-92 (3))

Worktree: `l3` after ENG-C3 (or any free). Record: `docs/reviews/loop/sprint/ENG-C8.md`. Items END-11 (`docs/BUILD_SPEC.md:5947`: deposits, sales tax, cancellable invoices, rebates, catch-ups) and END-12 (`:5972`: contract costs, loss, consideration payable, warranties, noncash, financing, concessions, terminations). Test-only items over templates already built by END-4..6; END-12's concession part (JET-05c) interacts with AD-14/AD-15 — assert only the ruled figures and mark the disputed leaf.

## Scope
Per-template check tests named in the two item bodies; JET-05c cases limited to the ruled D-88-rulings :108 figures; deposits part after ENG-D1 (END-4b).

## Fail-first
Each check test shown failing against a mutated template (mutation probe via `.run/mutations.py`) then passing; corpus unchanged.

## Gates
Common set.

## Do not change
Templates themselves (a failing check that reveals a template defect is RETURNED with the figures, not fixed silently unless the rule is unambiguous — then fail-first, fix, record).

## Questions to return
Any template whose check cannot be written without the AD-14/AD-15 ruling.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies verbatim (fast-forward from main before starting; never checkout/reset/rebase/stash/amend/clean/push; never `git add -A`; own `.env`, never the dev DB `erev` or ports 8190/5270; fail-first tests shown failing on the base commit; no floats; formula ids additive (DG-ENG-04, P14); never edit answer-key expected values or golden files except under a cited ruling; scratch under `.run/<lane>/`, never `/tmp`; `make lint` not bare ruff; `make parity` alone; one gate slot `~/dev/erev-wt/logs/gate-slot-1|2`; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: snapshot `.run/reports/answer-keys/report.json` into `.run/<lane>/` immediately after every run (the shared path is overwritten by concurrent lanes); record "where it stops next" per key (L5-3 table format) before claiming a key; questions of policy are RETURNED to the supervisor, never decided in the lane; nothing a lane does is accounting approval (G12 is separate). Gate set before reporting: backend/tests/engine (+ new tests), `make answer-keys ID=<rg-selection.txt 182 ids>` 182 of 182, `make answer-keys` all active (base failing set `.run/l9bgate/keys-all-failed.txt`, 58 ids — no new failure; list the ids this lane turns green), `make parity`, `make properties`, `make ci`, `make test-pg`; all measured, none projected.
