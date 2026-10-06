# Lane ENG-E2 — platform properties PRP-4..8, AKS-1..8 closure, unfiltered corpus and G5

Worktree: any free; DB-bound; after ENG-E1 and after C1/C2/C3/C4/C5/D1 merge. Record: `docs/reviews/loop/sprint/ENG-E2.md`. Items PRP-4 (P5 journal balance, P6 rollforward ties), PRP-5 (P7 RPO/waterfall, P9 idempotency), PRP-6 (P11 closed-period immutability), PRP-7 (stateful machine with a reference oracle), PRP-8 (full corpus G4 + full invariant suite G5) — `docs/BUILD_SPEC.md:10080-10194`; AKS-1..7 ticks (`:6080-6243`, in scope, unticked) and AKS-8 (`:6269`, 221-key sweep, "cannot pass while ENC-5/6/8 are deferred").

## Scope
`backend/tests/properties/test_prop_p05_*`, `p06`, `p07`, `p09`, `p11` (platform, DB-backed) and the `RuleBasedStateMachine`; `make properties` with no `K` filter (0 deselected) under `thorough`; `make answer-keys` all active 0 failed (2 withdrawn); AKS family ticks with measured family counts; AK hint closure record.

## Fail-first
Each property shown finding a seeded mutation (`.run/mutations.py`) then passing; PRP-8: `.run/reports/answer-keys/report.json` selected 243, passed 241, failed 0, withdrawn 2 (review status stays pending until G12).

## Gates
Common set with the unfiltered variants; ENG-J1's two keys are excluded from "0 failed" only by a recorded ruling — otherwise this lane cannot close.

## Do not change
Engine or platform behaviour (a property that finds a defect returns it to the owning lane); expected values.

## Questions to return
Any property whose oracle needs a policy statement (e.g., P11 reopen semantics before CLO-7 exists).

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies verbatim (fast-forward from main before starting; never checkout/reset/rebase/stash/amend/clean/push; never `git add -A`; own `.env`, never the dev DB `erev` or ports 8190/5270; fail-first tests shown failing on the base commit; no floats; formula ids additive (DG-ENG-04, P14); never edit answer-key expected values or golden files except under a cited ruling; scratch under `.run/<lane>/`, never `/tmp`; `make lint` not bare ruff; `make parity` alone; one gate slot `~/dev/erev-wt/logs/gate-slot-1|2`; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: snapshot `.run/reports/answer-keys/report.json` into `.run/<lane>/` immediately after every run (the shared path is overwritten by concurrent lanes); record "where it stops next" per key (L5-3 table format) before claiming a key; questions of policy are RETURNED to the supervisor, never decided in the lane; nothing a lane does is accounting approval (G12 is separate). Gate set before reporting: backend/tests/engine (+ new tests), `make answer-keys ID=<rg-selection.txt 182 ids>` 182 of 182, `make answer-keys` all active (base failing set `.run/l9bgate/keys-all-failed.txt`, 58 ids — no new failure; list the ids this lane turns green), `make parity`, `make properties`, `make ci`, `make test-pg`; all measured, none projected.
