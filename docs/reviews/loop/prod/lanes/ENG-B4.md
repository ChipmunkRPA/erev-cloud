# Lane ENG-B4 — C606-05h billing identity for taxes and specialist; stage 13 control flows; stage 01 ledger

Status: in flight on `~/dev/erev-wt/l6` (`sprint/l6`), commits 6a938f6 (taxes), ad75a8d (specialist). Record: `docs/reviews/loop/sprint/L9-ENG-B4.md` (named in PROGRESS.md; does not exist yet — write it before reporting). This package restates the scope with the follow-ons the supervisor added on 2026-09-19 (CLAUDE-RESPONSE 09:12, 09:22, 09:26).

## Scope
1. (landed on l6) `taxes.excluded`, `taxes.collected_tax`, `specialist.invoices` read billing lines through `erev_engine.billing_identity.iter_billing_lines` (D-91 `docs/01-DECISIONS.md:704`, :707 "one identity rule, one home"). The five `POST_RC_05H` strict xfails (`backend/tests/engine/kernel/test_billing_identity.py:245-266`) become asserting rows; `test_consumers_share_one_module` extended to taxes and specialist.
2. Follow-on commit A — stage 13 `_control_flows` per-line eligibility and date lineage (PRODUCTION-BILLING-LAYER-REVIEW: sums every in_position line incl. a cancellable memo line with no unconditional date at the minimum date → layers keep 1,000 after revenue while stage 10's position is 0 → S12-INV-03). Producer only; S12-INV-03 guard and stage 10 per-line counting unchanged. Ownership split inside `s13_books/__init__.py`: B4 owns `_control_flows` and helpers; ENG-D1 owns the deposit part sets and attribution — do not touch each other's functions.
3. Follow-on commit B — stage 01 ledger `billed_cum` applies the same identity rule (`s01_canonicalize/ledger.py:128-130`; `REFUND_EXCEEDS_BILLED` :242-245; S01-INV-03; referenced_cover; legacy templates) — D-91's `_fold`/s01 register item (production work in this lane) reopened by the supervisor 09:22.
4. Edge A (ruled provisionally 09:26): a later noncancellable status update applies to the identity's first-seen line; later cancellable repeats stay new lines — fail-first test, return if contradicted by a rule. Edge B (invoice-issue election on a later-eligible ENGINE memo): identify against POL-122 / POL-123 / POL-004 and S10-R-06, RETURN with facts before implementing.

## Files
`backend/erev_engine/stages/s04_transaction_price/taxes.py`, `specialist.py`, `billing_identity.py` (done); `stages/s13_books/__init__.py` (`_control_flows` + helpers only); `stages/s01_canonicalize/ledger.py`; tests `tests/engine/kernel/test_billing_identity.py`, `tests/engine/s04_transaction_price/test_s04_reductions.py`, `test_s04_specialist.py`, new `tests/engine/s13_books/test_s13_control_flows.py`, `tests/engine/s01_canonicalize/test_ledger_identity.py`.

## Fail-first tests and expected figures
- Kernel matrix 61/61 (5 formerly xfail rows assert); lane-reported focused run 146 passed with no xfail marker left (verify on merged main).
- Codex public baseline: ordinary incentive release (S04-R-16) counts a same-identity cancellable repeat — release 300,000 / net revenue 1,700,000 (not 200,000 / 1,800,000); balanced journals; exact replay.
- Stage 13: mixed eligible/memo lines; differing unconditional dates; later update and payment; historical cutoff; replay; FX / IFRS date policy; posting bindings; the ENGINE tax cancellable-repeat case no longer stops at S12-INV-03 (layers_net 100,000 vs net_position 0).
- Stage 01: status update adds nothing to `billed_cum`; cancellable repeat counted; mismatched update unchanged at stage 01; legacy template control; a `REFUND_EXCEEDS_BILLED` world with a re-sent invoice does not fire.
- Corpus: 534 `BILLING_RECORDED` events, one repeated identity (the B1 status-update key) — corpus neutrality is not evidence for this class; the kernel matrix is.

## Gates
Common set; additionally `make ci` must report 0 xfailed.

## Do not change
Any answer-key expected value; `billing_mode_at`; stage 10 per-line counting; the S12-INV-03 guard; D1's deposit part sets; `financing.py` (ENG-C6 owns 05g).

## Questions to return
Edge B facts and the rule they meet; any case where the S10-R-07 identity at stage 01 changes a legacy-template figure (list the key and both figures); whether `specialist.invoices` remains a caller after L9-CPC-Q-1 (AD-18).

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies verbatim (fast-forward from main before starting; never checkout/reset/rebase/stash/amend/clean/push; never `git add -A`; own `.env`, never the dev DB `erev` or ports 8190/5270; fail-first tests shown failing on the base commit; no floats; formula ids additive (DG-ENG-04, P14); never edit answer-key expected values or golden files except under a cited ruling; scratch under `.run/<lane>/`, never `/tmp`; `make lint` not bare ruff; `make parity` alone; one gate slot `~/dev/erev-wt/logs/gate-slot-1|2`; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: snapshot `.run/reports/answer-keys/report.json` into `.run/<lane>/` immediately after every run (the shared path is overwritten by concurrent lanes); record "where it stops next" per key (L5-3 table format) before claiming a key; questions of policy are RETURNED to the supervisor, never decided in the lane; nothing a lane does is accounting approval (G12 is separate). Gate set before reporting: backend/tests/engine (+ new tests), `make answer-keys ID=<rg-selection.txt 182 ids>` 182 of 182, `make answer-keys` all active (base failing set `.run/l9bgate/keys-all-failed.txt`, 58 ids — no new failure; list the ids this lane turns green), `make parity`, `make properties`, `make ci`, `make test-pg`; all measured, none projected.
