# Lane ENG-C6 — C606-05g ENGINE-mode financing payment-point eligibility and date basis

Worktree: `l6` after ENG-B4 merges (both touch `financing.py` and `billing_identity.py`). Record: `docs/reviews/loop/sprint/ENG-C6.md`. Ruling D-91 05g (`docs/01-DECISIONS.md:704-705`): a payment point is dated its S10-R-06 unconditional date under the billing mode of its date; a memo-only line contributes no point; zero eligible points with `significant = true` raises `SFC_REVIEW_REQUIRED` (ERROR) and posts nothing, replacing the silent no-schedule path (`financing.py:222-232`). The proxy is a ruled project convention [J] (AD-8) — the build proceeds under it; G12 may overturn the figures.

## Scope
`_judged_points` (`financing.py:586-627`) mode-aware dating via `stages/state.py` `billing_mode_at` and the stage 09 unconditional-date resolution (`returns.py` S09-R-23a) lifted into the kernel rather than re-implemented (D-91 "one identity rule, one home"); explicit schedule priority over a differently dated receipt; partial receipt applied/unapplied; historical cutoff and replay; ERP mode byte-identical; new answer key authored from the rules (0 active SFC keys run in ENGINE mode — every SFC key pins `billing.posting: ERP`, e.g. `SFC-FS-11-CASEA…yaml:75`).

## Fail-first tests and figures (D-91 :704-705)
SFC-S3-EX29 under a POL-004 ENGINE override, 4,000.00 line, 6 %: cancellable 1 Jan line made noncancellable 20 Feb → point dated 20 Feb, 23 month ends, P01 interest 0.00, P02 20.00, cash selling price 4,000 × 1.005^23 = 4,486.21, adjustment 486.21 (main: 1 Jan, P01 20.00, P02 40.10); never-unconditional never-paid line → `SFC_REVIEW_REQUIRED`, nothing posted (main accretes 508.64 on zero billing); the period-dated `billed_cum` node asserted (never the version column); postings by `PostingIntent.posting_period_key`; identity rows already on main (`test_s04_financing_judged.py:287-484`) unchanged.

## Gates
Common set; the new key enters the corpus as `review.status: pending`.

## Do not change
S04-R-10a identity rule; ERP-mode figures; taxes/specialist consumers (B4); any existing SFC key.

## Questions to return
A18 partial-receipt remainder: derive one concrete figure in the lane and return it with the derivation (CLAUDE-RESPONSE 09:08); A19 credit memo without a stated-price change (PR-1.7) if a fixture reaches it.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies verbatim (fast-forward from main before starting; never checkout/reset/rebase/stash/amend/clean/push; never `git add -A`; own `.env`, never the dev DB `erev` or ports 8190/5270; fail-first tests shown failing on the base commit; no floats; formula ids additive (DG-ENG-04, P14); never edit answer-key expected values or golden files except under a cited ruling; scratch under `.run/<lane>/`, never `/tmp`; `make lint` not bare ruff; `make parity` alone; one gate slot `~/dev/erev-wt/logs/gate-slot-1|2`; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: snapshot `.run/reports/answer-keys/report.json` into `.run/<lane>/` immediately after every run (the shared path is overwritten by concurrent lanes); record "where it stops next" per key (L5-3 table format) before claiming a key; questions of policy are RETURNED to the supervisor, never decided in the lane; nothing a lane does is accounting approval (G12 is separate). Gate set before reporting: backend/tests/engine (+ new tests), `make answer-keys ID=<rg-selection.txt 182 ids>` 182 of 182, `make answer-keys` all active (base failing set `.run/l9bgate/keys-all-failed.txt`, 58 ids — no new failure; list the ids this lane turns green), `make parity`, `make properties`, `make ci`, `make test-pg`; all measured, none projected.
