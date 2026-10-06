# Lane ENG-J1 — decision-first keys and the concession dating root (blocked on G12)

Worktree: assigned when a ruling lands. Record: `docs/reviews/loop/sprint/ENG-J1.md`. Blocking decisions: AD-13 (SFC-S3-EX26-RETURN-RIGHT window-end-day measurement; D-87 L6-5-Q-25 `docs/01-DECISIONS.md:482`), AD-14 (VC-CHK-113 POB #2 `billed_cum` attribution and JET-05c refund vs contract liability; D-88 L7-5-Q-4 `:554`, D-90 `:598`), AD-15 (`_concession_event` dating, `refund_liability.py:234-262`).

## Preparatory engineering allowed now (no assertion of green)
- A switchable posting for a targeted concession on a satisfied POB (JET-05c REFUND_LIABILITY vs CONTRACT_LIABILITY reduction) behind a policy switch with both branches tested; default = current behaviour.
- Per-producing-event dating of the aggregate concession (PR-3.8) as a switchable path; per-(obligation, event) conservation assertion (PR-3.11); L9-RUN-Q-7 group-member boundary (PR-7.7).
- The G12 evidence: for SFC-S3-EX26 the engine's `return-right-open` figures (TP 100.00, revenue 100.00, UNBILLED_RECEIVABLE 100.00, COST_OF_REVENUE/RETURN_ASSET 80.00 in P03) against the key (0.00 / −100.00 / 0.00 / 80.00 return asset) and the three agreeing keys; for VC-CHK-113 the S10-R-01/ALG-02 step 3 derivation of 35.02 / 364.98 and the after-concession / after-credit-memo figures (D-88-rulings :108: RL Cr 60.00 / REVENUE Dr 60.00; CL Cr 60.00 / RL Dr 60.00).

## After the ruling
Either an evidence-backed oracle regeneration (research-harness `akt_run.py`; the key header's generator) with the review trail (reviewer, date, facts, authority, figure), or an amended S09-R-26 / S10-R-13 rule with fail-first tests and new keys. Never a hand edit of an expected value.

## Gates
Common set; MOD-CHK-112 and RND-CHK-003C-USD-NEGATIVE re-measured under any dating change.

## Do not change
Anything asserted by the 182 selection without a D-number.

## Questions to return
None — this lane receives rulings; it returns derivations.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies verbatim (fast-forward from main before starting; never checkout/reset/rebase/stash/amend/clean/push; never `git add -A`; own `.env`, never the dev DB `erev` or ports 8190/5270; fail-first tests shown failing on the base commit; no floats; formula ids additive (DG-ENG-04, P14); never edit answer-key expected values or golden files except under a cited ruling; scratch under `.run/<lane>/`, never `/tmp`; `make lint` not bare ruff; `make parity` alone; one gate slot `~/dev/erev-wt/logs/gate-slot-1|2`; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: snapshot `.run/reports/answer-keys/report.json` into `.run/<lane>/` immediately after every run (the shared path is overwritten by concurrent lanes); record "where it stops next" per key (L5-3 table format) before claiming a key; questions of policy are RETURNED to the supervisor, never decided in the lane; nothing a lane does is accounting approval (G12 is separate). Gate set before reporting: backend/tests/engine (+ new tests), `make answer-keys ID=<rg-selection.txt 182 ids>` 182 of 182, `make answer-keys` all active (base failing set `.run/l9bgate/keys-all-failed.txt`, 58 ids — no new failure; list the ids this lane turns green), `make parity`, `make properties`, `make ci`, `make test-pg`; all measured, none projected.
