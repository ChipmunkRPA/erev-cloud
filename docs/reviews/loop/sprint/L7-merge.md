# Sprint L7 merge: gates, integration fixes and remaining failures

Supervisor record of the Level 7 merge on main (2026-09-17). The merge workflow (erev-sprint-L7-merge) merged the six lanes in order and fixed integration defects. The supervisor ran the release gate on main at f5dd350 with `.run/l7merge/gates.sh` (logs `.run/l7merge/g/`).

## Merges and integration fixes

- Merges: 3dcebd3 (L7-1), 5ff3b2d (L7-2), 0e2659b (L7-3; conflicts in router.tsx, router.test.tsx and run-batches.tsx, both sides kept), 670daea (L7-4), 3f51cd2 (L7-5), c826db7 (L7-6; conflicts in answer_keys/runners.py and test_runner_engine.py, both sides kept).
- 44a1e2b: the SF-06 source-lines drawer test fixture carries journal_batch_id, source_grouping_sha256 and txn_currency, which the generated JournalLineOut now requires.
- f5dd350: the SF-01 kpi drill targets test uses the real SF-04 and SF-08:report routes (its probe routes collided on id SF-04).
- 7966014: D-88 merge-time amendments (04 T-CON-09 functional columns after SC-C; 04 API-S-ReportRun tie_out_results difference; the test_dg_arc_09 carve-out removed).
- Main's frontend install was re-synced with npm ci (vitest 4.1.11).

## Release gate on main at f5dd350

| Gate | Result |
|---|---|
| openapi no drift | OK |
| single Alembic head (test-pg heads selection) | OK, 3 passed; chain 0049 to 0053 |
| make ci | OK: backend 2109 passed, vitest 595 passed, 0 failed, 0 skipped |
| make test-pg | OK: 290 passed |
| make properties K="p01 or p04 or p10 or p12 or p05 or p13 or p07" | FAIL: 9 passed, 1 failed (P12 FX layers; see below) |
| make parity K="not point_in_time_equivalence" | OK: 121 of 121 |
| make parity with the L7 merge_gates selection | OK: 121 of 121 |
| make answer-keys, release selection (D-87, 175 ids) | 158 of 175; D-89a takes the binding selection to 174 (VC-CHK-113-TC-POBVC-16 out), so main passes 158 of 174 |
| make answer-keys, all active | 159 of 232 |
| make e2e screens.spec.ts | OK: 52 passed, 0 failed, 0 flaky, 0 skipped |
| make e2e avenmoor-serial.spec.ts (SUP-RC-SMOKE) | FAIL on soft assertions only: 0 passed, 1 failed (one serial test). Every hard assertion of RC-SMOKE.1 to RC-SMOKE.10 passes, and the RC-SMOKE.1 soft errors cleared once RPS-22 merged. Three soft assertions fail, each rewritten by D-89 in lane L8-J: RC-SMOKE.2 SF-10-diff "SSP book version 2023-01-01 · 7 entries · method Legacy range" (L7-3-Q-27, rc deviation), RC-SMOKE.8 chip Approved and RC-SMOKE.9 primary "Export journals" (L7-3-Q-31: approval exports as built) |

## Remaining release-selection failures (17 of 175) and their owners

All are ruled in D-88 or D-89 and assigned to Level 8:
- Lane L8-D (engine D): ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT (L7-5-Q-6, one Alembic revision), ALC-CHK-032-S4-EX34-CASEC-REJECTED (Q-7), ALC-S4-EX35-CASEB (Q-8), ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION (Q-9; post-rc with ENB-9 if its probe stops further on), ONB-RB-06-RELIEF-GRANT-ROUTED-OUT (Q-10), REC-S5-UPFRONTFEE-OWN-A (Q-11), REC-S5-UPFRONTFEE-OWN-B (Q-12), MOD-CHK-112 (Q-13 with lane E Q-2 (i)), MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION (Q-2 (ii)), FX-CHK-084-A-REFUND-LIABILITY-REMEASURED (Q-3), RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION (Q-1).
- Lane L8-E (engine E): MOD-FS-09-CANCELLATION-REFUND-COMMISSION (Q-2 (i)), RND-CHK-003C (Q-4 with lane D (iii)), COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT (D-89 L7-6-Q-7), DLT-NATIVE-SUBSCRIPTION-PRE-STANDARD-UPFRONT (Q-8), JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE (Q-9).
- Leaves the selection (D-89a, 175 to 174): VC-CHK-113-TC-POBVC-16. The binding selection is `docs/reviews/loop/sprint/rg-selection.txt` (174 ids).

## P12 (FX layers) property failure

The properties stage failed on P12 (`backend/tests/properties/test_prop_p12_fx_layers.py::test_p12_fx_layers`): a `LIABILITY_LAYER_CREATED` CONTRACT_LIABILITY movement carried 1873 where the property expects round(amount × spot) = 1872. A diagnosis workflow (investigator plus adversarial verifier) reproduced it and classified it PROPERTY_OUTDATED: the engine follows D-87 L6-5-Q-26 (merged 099bf88).

- Falsifying case: spot 239647/128 in every period. A refund-liability release of 64 on 2026-03-15 consumes the refund layer at round(64 × spot) = 119824, settles a contract-asset layer at round(63 × spot) = 117951, and creates the contract-liability layer for the remaining 1 at 119824 − 117951 = 1873. The release ties exactly; the pre-099bf88 path gives 1872 but leaves a GL-to-layer residue of 1, the defect L6-5-Q-26 fixed.
- Other suspects cleared: 6e1f2e4 (stage 13, not reached by the property), 046dd65 (platform bundles), lane D stages.
- Fix (D-89b; owner lane L8-E, same batch as D-88 L7-6-Q-2; property only, no engine change):
  1. In `test_p12_fx_layers`, before the contract-liability loop, collect `releases = {f.source_key for f in case.flows.monetary if f.direction == "DECREASE" and f.control == "CREDIT"}` and a helper `of_source(key, kind, roles)` returning the movements of that source, kind and roles. For a created CONTRACT_LIABILITY layer whose source is a release, `expected` = Σ amount_functional of `LIABILITY_LAYER_CONSUMED` (monetary roles) − Σ amount_functional of `ASSET_LAYER_SETTLED` (CONTRACT_ASSET) for that source, and additionally `abs(expected − _at(amount_txn, spot)) <= len(consumed) + len(settled)` (the bound keeps the check tied to spot). Otherwise `expected = _at(amount_txn, spot)`. Assert `amount_functional == expected`. Add D-87 L6-5-Q-26 and D-88 L7-6-Q-2 to the module docstring; the comment "created at spot" reads "created at spot, or at the release carrying".
  2. With L7-6-Q-2 (the residue folded into the last asset settlement): for CONTRACT_ASSET `ASSET_LAYER_SETTLED` movements of a release source, replace the per-movement spot equality with the release tie per source: consumed == settled + created, with the same bound on each settlement against spot. The "fully settled layer ends at 0" check stays.
- Gates: `make properties K=p12` (thorough; backend/.hypothesis replays this example first) and `backend/tests/engine/s12_fx_entities/`.
- Supervisor editorial (D-89b): ENGINE_SPEC_B S12-R-20 ("at that spot amount" becomes the release carrying of D-87 L6-5-Q-26), the PROP:P12 statement, and POLICIES ALG-08 §2.9.1 settlement row, following the D-79 PROP:P4 precedent.

## Screens and smoke journey failures

- Screens (`frontend/e2e/projects/screens.spec.ts`): 52 passed, 0 failed, 0 flaky, 0 skipped. The rows that first ran at this gate pass: RPS-6 legacy_contract_history_export, RPS-7 SF-06:entries, RPS-22 SF-01 rail and favourite maya, L7-4 SF-10:detail maya (errors first).
- Smoke journey (`frontend/e2e/projects/avenmoor-serial.spec.ts`): FAIL on soft assertions only: 0 passed, 1 failed (one serial test). Every hard assertion of RC-SMOKE.1 to RC-SMOKE.10 passes, and the RC-SMOKE.1 soft errors cleared once RPS-22 merged. Three soft assertions fail, each rewritten by D-89 in lane L8-J: RC-SMOKE.2 SF-10-diff "SSP book version 2023-01-01 · 7 entries · method Legacy range" (L7-3-Q-27, rc deviation), RC-SMOKE.8 chip Approved and RC-SMOKE.9 primary "Export journals" (L7-3-Q-31: approval exports as built).
- Supervisor capture read on main: sf-06-run-lines (light) is clean: no filter banner, no clipped figure, docked drawer, rail in DS-CMP-02 order.
