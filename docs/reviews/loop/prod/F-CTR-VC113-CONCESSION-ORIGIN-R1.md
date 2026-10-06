# F-CTR lane observation — VC113-CONCESSION-ORIGIN-R1 (diagnostic only)

Codex packet production-20260920-1404 item 1 (report PRODUCTION-VC113-CONCESSION-ORIGIN-SOURCE-91575093.md, SHA256 680f04911e85c7dbaacc0da16b6ab1774c640f2d44e36375b505ebbb05527d44; manifest c0446ffd0364fdef5dfe8e1e36f0cd8e7b95eec4b048df76ecd8ae86060fc015; 19 artifacts). Supervisor dispatch to lane F-CTR (lane-p3-terraform) while holding for P5: reproduce the original `VC-CHK-113-TC-POBVC-16` checkpoints on the CPU / in-memory engine path and capture the intermediates Codex's source-composed chain names. **No producer change, no oracle change, no S10-R-26 change; the fix is not implemented here** — the governed correction goes through the spec-question process as D-98 candidate 109 (a question, not a ruling).

## 1. Setup (measured)

| Item | Fact |
|---|---|
| Lane head at capture | `71e46a8c` on `sprint/l20` (code unchanged since b7bc6529; contains main 065e7f65); Codex's source read was main 91575093; the lane touches none of the stage 06 / 08 / 10 paths named below — see §6 (b) for the exact source relation between the two heads (not a blanket "identical source" claim) |
| Key | `docs/accounting/answer-keys/vc/VC-CHK-113-TC-POBVC-16.yaml`, SHA256 `138684b1e6218db9b3e75311c7d5502c4886c491d3bc2a7ee3fa714efbc8a334` — equals Codex's fixture hash; unchanged |
| Path | `support.answer_keys.runners.run_engine` (the answer-key runner's in-memory engine path, `erev_engine.compute` per checkpoint bundle) plus a re-run of the same bundles through `s01_canonicalize.run` → `s13_books.run_books` to read the stage states (`BookResult.states`); stage-10 `_concession_event` called on the ASC606 `AllocatedState`; stage-09 `target_at_position` at the November 15 event for the completeness test |
| Script / raw output | `.run/F-CTR/vc113_diag.py` (scratch, not committed) → `.run/F-CTR/vc113-diag-output.txt`; the raw output is reproduced verbatim in §5 |
| Exit statuses | script exit 0; every step exit 0 (§5 step summary); `date` stamps 2026-09-20 07:15:55 PDT (this capture; the first capture at 07:12:22 – 07:12:25 PDT gave the same values without the compared version columns) |
| Original dispositions | all seven checkpoint mismatches reproduced exactly as recorded (§2), none re-stated |

## 2. The seven original mismatches (retained, verbatim from `assert_checkpoints`)

```
- VC-CHK-113-TC-POBVC-16 full-delivery obligation Contract 2/POB #2 billed_cum: expected 400.00, actual 364.98
- VC-CHK-113-TC-POBVC-16 after-concession balance Contract 2@US01 FY2023-P11 contract_liability: expected 0.00, actual 60.00
- VC-CHK-113-TC-POBVC-16 after-concession balance Contract 2@US01 FY2023-P11 refund_liability: expected 60.00, actual 0.00
- VC-CHK-113-TC-POBVC-16 after-concession subledger FY2023-P11 US01 REFUND_LIABILITY/2110 cr: expected 60.00, actual <absent>
- VC-CHK-113-TC-POBVC-16 after-concession subledger FY2023-P11 US01 CONTRACT_LIABILITY/21002 line: expected <absent>, actual cr 60.00; functional cr 60.00
- VC-CHK-113-TC-POBVC-16 after-credit-memo subledger FY2023-P12 US01 CONTRACT_LIABILITY/21002 cr: expected 60.00, actual <absent>
- VC-CHK-113-TC-POBVC-16 after-credit-memo subledger FY2023-P12 US01 REFUND_LIABILITY/2110 dr: expected 60.00, actual <absent>
```

The first (October software `billed_cum` 400.00 vs 364.98) is the separate October question Codex set aside; it is retained and not analysed here.

## 3. Codex's chain, step by step, against the captured intermediates

| # | Codex's source-composed step | Captured on `71e46a8c` (after-concession and after-credit-memo checkpoints agree) | Confirmed |
|---|---|---|---|
| 1 | The November 15 software `DISCOUNT` (VC-CONC-2 v1, targeted to POB #2) creates the 60 concession quota in stage 08 on a complete obligation | `refund_components["Contract 2/POB %232"]` = `ConcessionQuota(x_exact=60, a_posted=6000, revenue_basis=EMBEDDED)`; `concession_history` holds exactly one entry: event `Contract 2/EV-000015`, effective 2023-11-15, exact 60, posted 6000, producer `08`, EMBEDDED. The November position of POB #2 at that event: selected segment = the `TP_CHANGE` segment (2023-11-15, EV-000015, a_posted 32519), progress 1, complete True, C_p 32519; the resolved share moved the FIXED allocation from 10400/27 (385.185…) / 38519 to 8780/27 (325.185…) / 32519, i.e. −60.00 exact / −6000 posted | Yes |
| 2 | May 31's `LEGACY_POB_VC` (MOD-C2-0531, `pob_price_change`, targeted at POB #1) adds a `MODIFICATION` segment to the untargeted software obligation too | POB #2 segments: INCEPTION 2023-01-01; MODIFICATION 2023-05-15 (EV-000007); **MODIFICATION 2023-05-31 (EV-000008)** with x_exact / a_posted unchanged (10400/27 / 38519); TP_CHANGE 2023-11-15 (EV-000015) | Yes |
| 3 | Stage-10 `_concession_event` selects May 31's MODIFICATION ahead of November's TP_CHANGE (`settled or latest or changed`) | `_concession_event(st, POB #2)` returns `Contract 2/EV-000008` (CONTRACT_AMENDED, 2023-05-31); its payload has no `price_change_settlement` (so no `settled`); `latest` = the May 31 MODIFICATION segment's event wins over `changed` = the November 15 TP_CHANGE segment's event | Yes |
| 4 | `_concessions` uses that older origin for `created_on` / `created_ref` and ignores the actual dated `concession_history` | Stage-10 component `CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232`: kind CONCESSION, created_on **2023-05-31**, created_amount 6000, created_ref (`contract_event`, `Contract 2/EV-000008`); the history's only entry (EV-000015, 2023-11-15) is not the origin the component carries | Yes |
| 5 | The original October 31 unreferenced 100 credit consumes min(60, 100) = 60 because the wrongly inferred origin precedes October | Component consumptions: `[("Contract 2/EV-000014", 2023-10-31, 6000)]` — the October 31 unreferenced credit memo (CM-Contract2-VC, 100.00) took the whole 60. Side observation from the same cause: the `refund_liability` target of the component reads 6000 in FY2023-P05 … P09 — a 60.00 refund liability reported for months before the concession existed — and 0 from P10 on (qualified in §6 (a): a value inside the November / December recomputation, not an actual May posting) | Yes |
| 6 | November: RL becomes 0, CL 60 | `refund_liability` target P11 = 0 (component) and the VC-CONC-2 VARIABLE_CONSIDERATION component is 0; presentation `contract_liability` P11 = 6000; the compared balance row `Contract 2@US01 FY2023-P11` carries `contract_liability_txn 6000`; the P11 engine intent is `REVENUE_RECOGNITION` Dr REVENUE 5002 6000 / **Cr CONTRACT_LIABILITY 21002 6000** — the JET-05c Cr REFUND_LIABILITY 2110 60.00 the key expects is absent | Yes |
| 7 | December: no 60 refund left to release | The December 10 credit memo (EV-000016, 60.00 on POB #2) consumed nothing (the component's consumptions hold the October memo only; RL P12 = 0); no engine posting intent touches REFUND_LIABILITY or CONTRACT_LIABILITY in FY2023-P12; the compared balance P12 shows contract_liability 0 (the ERP-side POB #2 credit memo takes the 60 out of contract liability) — the JET-04b Dr REFUND_LIABILITY / Cr CONTRACT_LIABILITY 60.00 the key expects is absent | Yes |

**Conclusion of the reproduction.** Every step of Codex's chain is confirmed by captured runtime intermediates on this lane's head; the November and December discrepancies (mismatches 2–7 of §2) follow from the stage-10 origin inference (`_concession_event` preferring the latest MODIFICATION segment over the dated TP_CHANGE producer) feeding `_consume` with a May 31 creation date. Not decided here: whether S10-R-26's aggregate-vs-dated-origin sentence or the stage-08 creating-event intent governs (D-98 candidate 109); the October `billed_cum` 400.00 question is separate.

## 4. Expected checkpoint bridge (ORIGINAL expectations, per the supervisor's 1413 context) versus captured values

Codex packet production-20260920-1413 item 3 (PRODUCTION-G12-VC113-DATED-CONCESSION-RECOMMENDATION.md, SHA256 e98bfcf0a22ed3c8cad772a015647940c178caf38fd9ff447ead86f338ae0387; manifest 3b76c54e21b0e2ea3fc81e0d94d7e0f0c54d797994330a294a724afdebe81483; 3 artifacts) is a review RECOMMENDATION — not accounting approval, not an executed engine pass, not a change to any oracle. Facts distinguishing the two credits, as the supervisor states them: October 31 (seq 14) is a credit against the imported VC element VC-ROW-1 (effective January 1); VC-CONC-2 first takes effect on November 15 for defects in the delivered and billed software; December 10 (seq 16) is that software concession's 60 credit; no new structured credit reference exists. Codex's engineering recommendation for D-98 question 109: retain the actual dated producing-event identity / order per addition for consumption (preserving the original November 60 refund and December 60 release); the October 100 credit already reduced October billings and nothing in the facts says it settled the later software concession; multiple additions on one POB need distinct provenance — the latest boundary alone is insufficient; focused checks should include a credit between additions and an earlier same-day credit under the defined event ordering; exact / posted conservation and the currency / contract / obligation rules preserved. S10-R-26's aggregate-origin wording still needs explicit governed resolution. **Nothing below changes anything: the table compares, it does not correct.**

Values are the compared `contract_version` columns (minor units read as USD) and the compared balance row of `Contract 2@US01`; RL = `refund_liability`, CL = `contract_liability`.

| Checkpoint | Measure | Expected (original bridge) | Captured on `71e46a8c` | Agreement |
|---|---|---|---|---|
| October (full-delivery, as of 2023-10-31) | billed | 1,100.00 | `billed_cum` 110000 = 1,100.00 | agrees |
| | revenue | 1,100.00 | `revenue_cum` 110000 = 1,100.00 (TP 1,100.00) | agrees |
| | RL / CL | 0 / 0 | balance row carries no RL or CL column value (0 / 0); the stage-10 CONCESSION component does not exist yet | agrees |
| | (separate) POB #2 `billed_cum` | 400.00 | 36498 = 364.98 | differs — the October software question, retained, not analysed here |
| November (after-concession, as of 2023-11-30) | billed | 1,100.00 carried | `billed_cum` 110000 = 1,100.00 | agrees |
| | revenue | 1,040.00 | `revenue_cum` 104000 = 1,040.00 (TP 1,040.00; POB #2 `revenue_cum` 32519 = 325.19, `allocated_exact` 8780/27) | agrees |
| | RL | 60.00 | 0 — the CONCESSION component (created_on 2023-05-31) was consumed by the October 31 credit | **differs** (mismatches 3 and 4 of §2) |
| | CL | 0.00 | `contract_liability_txn` 6000 = 60.00; P11 intent Dr REVENUE 5002 / Cr CONTRACT_LIABILITY 21002 60.00 | **differs** (mismatches 2 and 5 of §2) |
| December (after-credit-memo, as of 2023-12-31) | billed | 1,040.00 | `billed_cum` 104000 = 1,040.00 (POB #2 `billed_cum` 30498 = 304.98) | agrees |
| | revenue | 1,040.00 carried | `revenue_cum` 104000 = 1,040.00 | agrees |
| | RL | 0.00 | 0 | agrees in value, not in path — no JET-04b release posted; the refund liability never existed in November |
| | CL | 0.00 | 0 (60.00 at P11 → 0 at P12, drained by the ERP-side December 10 memo on POB #2) | agrees in value, not in path — the expected P12 Dr REFUND_LIABILITY 2110 / Cr CONTRACT_LIABILITY 21002 60.00 is absent (mismatches 6 and 7 of §2) |

Reading: the contract-level billed and revenue bridge (1,100 / 1,100 → 1,100 / 1,040 → 1,040 / 1,040) is reproduced exactly; the whole discrepancy is the November refund-liability recognition (RL 60 / CL 0 expected; RL 0 / CL 60 captured) and, as its consequence, the December release. The captured chain in §3 locates it in the stage-10 origin inference; the governed answer is D-98 question 109, not this file.

## 5. Raw captured output (verbatim; `.run/F-CTR/vc113-diag-output.txt`, capture of 2026-09-20 07:15:55 PDT)

```

### start — date: 2026-09-20 07:15:52 PDT
key path: /Users/rsang/dev/erev-wt/l20/docs/accounting/answer-keys/vc/VC-CHK-113-TC-POBVC-16.yaml
key sha256: 138684b1e6218db9b3e75311c7d5502c4886c491d3bc2a7ee3fa714efbc8a334  expected: 138684b1e6218db9b3e75311c7d5502c4886c491d3bc2a7ee3fa714efbc8a334  match: True
[exit 0] fixture hash unchanged

### run_engine + assert_checkpoints (original oracles) — date: 2026-09-20 07:15:54 PDT
answer key VC-CHK-113-TC-POBVC-16: 7 checkpoint mismatches
- VC-CHK-113-TC-POBVC-16 full-delivery obligation Contract 2/POB #2 billed_cum: expected 400.00, actual 364.98
- VC-CHK-113-TC-POBVC-16 after-concession balance Contract 2@US01 FY2023-P11 contract_liability: expected 0.00, actual 60.00
- VC-CHK-113-TC-POBVC-16 after-concession balance Contract 2@US01 FY2023-P11 refund_liability: expected 60.00, actual 0.00
- VC-CHK-113-TC-POBVC-16 after-concession subledger FY2023-P11 US01 REFUND_LIABILITY/2110 cr: expected 60.00, actual <absent>
- VC-CHK-113-TC-POBVC-16 after-concession subledger FY2023-P11 US01 CONTRACT_LIABILITY/21002 line: expected <absent>, actual cr 60.00; functional cr 60.00
- VC-CHK-113-TC-POBVC-16 after-credit-memo subledger FY2023-P12 US01 CONTRACT_LIABILITY/21002 cr: expected 60.00, actual <absent>
- VC-CHK-113-TC-POBVC-16 after-credit-memo subledger FY2023-P12 US01 REFUND_LIABILITY/2110 dr: expected 60.00, actual <absent>
[exit 0] original checkpoints reproduced (7 mismatches; seven expected)
checkpoint full-delivery: after_seq=14 as_of=2023-10-31 book=ASC606 bundles=1 outputs=1
checkpoint after-concession: after_seq=15 as_of=2023-11-30 book=ASC606 bundles=1 outputs=1
checkpoint after-credit-memo: after_seq=16 as_of=2023-12-31 book=ASC606 bundles=1 outputs=1

### intermediates — checkpoint full-delivery (as_of 2023-10-31) — date: 2026-09-20 07:15:55 PDT
book states: ['02', '03', '04', '05', '06', '07', '08', '08/late_events', '09', '10', '11', '12', '14', '15']
POB #2 subject key: Contract 2/POB %232; quantity 3 (~3.000000); is_vc_line False
POB #2 segments (effective_date | event_key | cause | basis | x_exact | a_posted | estimate_pair):
  2023-01-01 | None | INCEPTION | INCEPTION | 4080/13 (~313.846154) | 31385 | (None, None)
  2023-05-15 | Contract 2/EV-000007 | MODIFICATION | PROSPECTIVE | 10400/27 (~385.185185) | 38519 | (None, None)
  2023-05-31 | Contract 2/EV-000008 | MODIFICATION | PROSPECTIVE | 10400/27 (~385.185185) | 38519 | (None, None)
events of the state (event_key | type | effective_date | modification/estimate):
  Contract 2/EV-000001 | CONTRACT_BOOKED | 2023-01-01 | 
  Contract 2/EV-000002 | CONTRACT_ACTIVATED | 2023-01-01 | 
  Contract 2/EV-000003 | ESTIMATE_CHANGED | 2023-01-01 | 
  Contract 2/EV-000004 | DELIVERY_RECORDED | 2023-01-31 | 
  Contract 2/EV-000005 | DELIVERY_RECORDED | 2023-03-31 | 
  Contract 2/EV-000006 | BILLING_RECORDED | 2023-04-30 | 
  Contract 2/EV-000007 | CONTRACT_AMENDED | 2023-05-15 | 
  Contract 2/EV-000008 | CONTRACT_AMENDED | 2023-05-31 | 
  Contract 2/EV-000009 | DELIVERY_RECORDED | 2023-10-31 | 
  Contract 2/EV-000010 | BILLING_RECORDED | 2023-10-31 | 
  Contract 2/EV-000011 | DELIVERY_RECORDED | 2023-10-31 | 
  Contract 2/EV-000012 | BILLING_RECORDED | 2023-10-31 | 
  Contract 2/EV-000013 | DELIVERY_RECORDED | 2023-10-31 | 
  Contract 2/EV-000014 | CREDIT_MEMO_RECORDED | 2023-10-31 | 
refund_components (quota per obligation):
concession_history (dated source subledger):
targeted_vc_quotas:
no November 15 ESTIMATE_CHANGED in this checkpoint's stream
stage-10 refund components (kind | key | created_on | created_amount | created_ref | consumptions):
  VARIABLE_CONSIDERATION | CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | None | 0 | None | []
refund_liability targets (subject | period | value | cause):
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P01 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P02 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P03 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P04 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P05 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P06 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P07 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P08 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P09 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P10 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P11 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P12 | 0 | VARIABLE_CONSIDERATION
concession_created_cum targets (subject | period | value | cause):
presentation targets contract_liability / refund-related (subject | measure | period | value):
  CG-Contract 2@US01 | contract_liability | FY2023-P10 | 0
  CG-Contract 2@US01 | contract_liability | FY2023-P11 | 0
  CG-Contract 2@US01 | contract_liability | FY2023-P12 | 0
contract_version columns (compared) CG-Contract 2: {'transaction_price': '110000', 'revenue_cum': '110000', 'billed_cum': '110000', 'rpo_amount': '0'}
obligation_version columns (compared) — POB #2:
  Contract 2/POB %232: {'original_allocated_amount': '31385', 'original_allocated_exact': '4080/13', 'allocated_amount': '38519', 'allocated_exact': '10400/27', 'delivered_quantity_cum': '3', 'revenue_cum': '38519', 'delivered_quantity': '3', 'billed_cum': '36498', 'pre_standard_revenue_cum': '0'}
OutputBundle balances (what the checkpoint compares) for FY2023-P10..P12:
  Contract 2@US01 FY2023-P10: nonzero columns {'entity': 'US01', 'functional_currency': 'USD', 'txn_currency': 'USD'}
  Contract 2@US01 FY2023-P11: nonzero columns {'entity': 'US01', 'functional_currency': 'USD', 'txn_currency': 'USD'}
  Contract 2@US01 FY2023-P12: nonzero columns {'entity': 'US01', 'functional_currency': 'USD', 'txn_currency': 'USD'}
posting intents touching REFUND_LIABILITY / CONTRACT_LIABILITY / REVENUE in P11..P12 (period | role | account | amount | reason | description):
[exit 0] [full-delivery] intermediates captured

### intermediates — checkpoint after-concession (as_of 2023-11-30) — date: 2026-09-20 07:15:55 PDT
book states: ['02', '03', '04', '05', '06', '07', '08', '08/late_events', '09', '10', '11', '12', '14', '15']
POB #2 subject key: Contract 2/POB %232; quantity 3 (~3.000000); is_vc_line False
POB #2 segments (effective_date | event_key | cause | basis | x_exact | a_posted | estimate_pair):
  2023-01-01 | None | INCEPTION | INCEPTION | 4080/13 (~313.846154) | 31385 | (None, None)
  2023-05-15 | Contract 2/EV-000007 | MODIFICATION | PROSPECTIVE | 10400/27 (~385.185185) | 38519 | (None, None)
  2023-05-31 | Contract 2/EV-000008 | MODIFICATION | PROSPECTIVE | 10400/27 (~385.185185) | 38519 | (None, None)
  2023-11-15 | Contract 2/EV-000015 | TP_CHANGE | PROSPECTIVE | 8780/27 (~325.185185) | 32519 | (None, 'Contract 2/VC-CONC-2@v1')
events of the state (event_key | type | effective_date | modification/estimate):
  Contract 2/EV-000001 | CONTRACT_BOOKED | 2023-01-01 | 
  Contract 2/EV-000002 | CONTRACT_ACTIVATED | 2023-01-01 | 
  Contract 2/EV-000003 | ESTIMATE_CHANGED | 2023-01-01 | 
  Contract 2/EV-000004 | DELIVERY_RECORDED | 2023-01-31 | 
  Contract 2/EV-000005 | DELIVERY_RECORDED | 2023-03-31 | 
  Contract 2/EV-000006 | BILLING_RECORDED | 2023-04-30 | 
  Contract 2/EV-000007 | CONTRACT_AMENDED | 2023-05-15 | 
  Contract 2/EV-000008 | CONTRACT_AMENDED | 2023-05-31 | 
  Contract 2/EV-000009 | DELIVERY_RECORDED | 2023-10-31 | 
  Contract 2/EV-000010 | BILLING_RECORDED | 2023-10-31 | 
  Contract 2/EV-000011 | DELIVERY_RECORDED | 2023-10-31 | 
  Contract 2/EV-000012 | BILLING_RECORDED | 2023-10-31 | 
  Contract 2/EV-000013 | DELIVERY_RECORDED | 2023-10-31 | 
  Contract 2/EV-000014 | CREDIT_MEMO_RECORDED | 2023-10-31 | 
  Contract 2/EV-000015 | ESTIMATE_CHANGED | 2023-11-15 | 
refund_components (quota per obligation):
  Contract 2/POB %232: x_exact=60 (~60.000000) a_posted=6000 revenue_basis=EMBEDDED
concession_history (dated source subledger):
  {'subject_key': 'Contract 2/POB %232', 'event_key': 'Contract 2/EV-000015', 'effective_date': datetime.date(2023, 11, 15), 'order_key': (datetime.date(2023, 11, 15), 15, 'Contract 2/EV-000015'), 'exact': Fraction(60, 1), 'posted': 6000, 'producer': '08', 'revenue_basis': 'EMBEDDED'}
targeted_vc_quotas:
November 15 position of POB #2 at the ESTIMATE_CHANGED event (stage 08 completeness test):
  selected segment: (datetime.date(2023, 11, 15), 'Contract 2/EV-000015', 'TP_CHANGE', 32519)
  progress: 1 (~1.000000)  complete: True  value(C_p minor units): 32519  guard: None
[exit 0] [after-concession] November position captured (complete=True)
stage-10 _concession_event(st, POB #2) — the inferred creating boundary:
  event_key=Contract 2/EV-000008 type=CONTRACT_AMENDED effective_date=2023-05-31 payload.modification=None payload.price_change_settlement=None
[exit 0] [after-concession] inferred concession event = Contract 2/EV-000008 @ 2023-05-31
stage-10 refund components (kind | key | created_on | created_amount | created_ref | consumptions):
  CONCESSION | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | 2023-05-31 | 6000 | ('contract_event', 'Contract 2/EV-000008') | [('Contract 2/EV-000014', '2023-10-31', 6000)]
  VARIABLE_CONSIDERATION | CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-CONC-2 | None | 0 | None | []
  VARIABLE_CONSIDERATION | CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | None | 0 | None | []
refund_liability targets (subject | period | value | cause):
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P05 | 6000 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P06 | 6000 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P07 | 6000 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P08 | 6000 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P09 | 6000 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P10 | 0 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P11 | 0 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P12 | 0 | CONCESSION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-CONC-2 | FY2023-P11 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-CONC-2 | FY2023-P12 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P01 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P02 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P03 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P04 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P05 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P06 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P07 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P08 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P09 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P10 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P11 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P12 | 0 | VARIABLE_CONSIDERATION
concession_created_cum targets (subject | period | value | cause):
  Contract 2/POB %232 | FY2023-P05 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P06 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P07 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P08 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P09 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P10 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P11 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P12 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
presentation targets contract_liability / refund-related (subject | measure | period | value):
  CG-Contract 2@US01 | contract_liability | FY2023-P10 | 0
  CG-Contract 2@US01 | contract_liability | FY2023-P11 | 6000
  CG-Contract 2@US01 | contract_liability | FY2023-P12 | 6000
contract_version columns (compared) CG-Contract 2: {'transaction_price': '104000', 'revenue_cum': '104000', 'billed_cum': '110000', 'rpo_amount': '0'}
obligation_version columns (compared) — POB #2:
  Contract 2/POB %232: {'original_allocated_amount': '31385', 'original_allocated_exact': '4080/13', 'allocated_amount': '32519', 'allocated_exact': '8780/27', 'delivered_quantity_cum': '3', 'revenue_cum': '32519', 'delivered_quantity': '3', 'billed_cum': '36498', 'pre_standard_revenue_cum': '0'}
OutputBundle balances (what the checkpoint compares) for FY2023-P10..P12:
  Contract 2@US01 FY2023-P10: nonzero columns {'entity': 'US01', 'functional_currency': 'USD', 'txn_currency': 'USD'}
  Contract 2@US01 FY2023-P11: nonzero columns {'entity': 'US01', 'functional_currency': 'USD', 'txn_currency': 'USD', 'contract_liability_txn': '6000', 'contract_liability_functional': '6000'}
  Contract 2@US01 FY2023-P12: nonzero columns {'entity': 'US01', 'functional_currency': 'USD', 'txn_currency': 'USD', 'contract_liability_txn': '6000', 'contract_liability_functional': '6000'}
posting intents touching REFUND_LIABILITY / CONTRACT_LIABILITY / REVENUE in P11..P12 (period | role | account | amount | reason | description):
  FY2023-P11 | REVENUE_RECOGNITION | EVENT | Contract 2/POB %232 | reason=None | origin=None
      {'side': 'D', 'account_role': 'REVENUE', 'account_code': '5002', 'amount_txn': '6000', 'amount_functional': '6000'}
      {'side': 'C', 'account_role': 'CONTRACT_LIABILITY', 'account_code': '21002', 'amount_txn': '6000', 'amount_functional': '6000'}
[exit 0] [after-concession] intermediates captured

### intermediates — checkpoint after-credit-memo (as_of 2023-12-31) — date: 2026-09-20 07:15:55 PDT
book states: ['02', '03', '04', '05', '06', '07', '08', '08/late_events', '09', '10', '11', '12', '14', '15']
POB #2 subject key: Contract 2/POB %232; quantity 3 (~3.000000); is_vc_line False
POB #2 segments (effective_date | event_key | cause | basis | x_exact | a_posted | estimate_pair):
  2023-01-01 | None | INCEPTION | INCEPTION | 4080/13 (~313.846154) | 31385 | (None, None)
  2023-05-15 | Contract 2/EV-000007 | MODIFICATION | PROSPECTIVE | 10400/27 (~385.185185) | 38519 | (None, None)
  2023-05-31 | Contract 2/EV-000008 | MODIFICATION | PROSPECTIVE | 10400/27 (~385.185185) | 38519 | (None, None)
  2023-11-15 | Contract 2/EV-000015 | TP_CHANGE | PROSPECTIVE | 8780/27 (~325.185185) | 32519 | (None, 'Contract 2/VC-CONC-2@v1')
events of the state (event_key | type | effective_date | modification/estimate):
  Contract 2/EV-000001 | CONTRACT_BOOKED | 2023-01-01 | 
  Contract 2/EV-000002 | CONTRACT_ACTIVATED | 2023-01-01 | 
  Contract 2/EV-000003 | ESTIMATE_CHANGED | 2023-01-01 | 
  Contract 2/EV-000004 | DELIVERY_RECORDED | 2023-01-31 | 
  Contract 2/EV-000005 | DELIVERY_RECORDED | 2023-03-31 | 
  Contract 2/EV-000006 | BILLING_RECORDED | 2023-04-30 | 
  Contract 2/EV-000007 | CONTRACT_AMENDED | 2023-05-15 | 
  Contract 2/EV-000008 | CONTRACT_AMENDED | 2023-05-31 | 
  Contract 2/EV-000009 | DELIVERY_RECORDED | 2023-10-31 | 
  Contract 2/EV-000010 | BILLING_RECORDED | 2023-10-31 | 
  Contract 2/EV-000011 | DELIVERY_RECORDED | 2023-10-31 | 
  Contract 2/EV-000012 | BILLING_RECORDED | 2023-10-31 | 
  Contract 2/EV-000013 | DELIVERY_RECORDED | 2023-10-31 | 
  Contract 2/EV-000014 | CREDIT_MEMO_RECORDED | 2023-10-31 | 
  Contract 2/EV-000015 | ESTIMATE_CHANGED | 2023-11-15 | 
  Contract 2/EV-000016 | CREDIT_MEMO_RECORDED | 2023-12-10 | 
refund_components (quota per obligation):
  Contract 2/POB %232: x_exact=60 (~60.000000) a_posted=6000 revenue_basis=EMBEDDED
concession_history (dated source subledger):
  {'subject_key': 'Contract 2/POB %232', 'event_key': 'Contract 2/EV-000015', 'effective_date': datetime.date(2023, 11, 15), 'order_key': (datetime.date(2023, 11, 15), 15, 'Contract 2/EV-000015'), 'exact': Fraction(60, 1), 'posted': 6000, 'producer': '08', 'revenue_basis': 'EMBEDDED'}
targeted_vc_quotas:
November 15 position of POB #2 at the ESTIMATE_CHANGED event (stage 08 completeness test):
  selected segment: (datetime.date(2023, 11, 15), 'Contract 2/EV-000015', 'TP_CHANGE', 32519)
  progress: 1 (~1.000000)  complete: True  value(C_p minor units): 32519  guard: None
[exit 0] [after-credit-memo] November position captured (complete=True)
stage-10 _concession_event(st, POB #2) — the inferred creating boundary:
  event_key=Contract 2/EV-000008 type=CONTRACT_AMENDED effective_date=2023-05-31 payload.modification=None payload.price_change_settlement=None
[exit 0] [after-credit-memo] inferred concession event = Contract 2/EV-000008 @ 2023-05-31
stage-10 refund components (kind | key | created_on | created_amount | created_ref | consumptions):
  CONCESSION | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | 2023-05-31 | 6000 | ('contract_event', 'Contract 2/EV-000008') | [('Contract 2/EV-000014', '2023-10-31', 6000)]
  VARIABLE_CONSIDERATION | CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-CONC-2 | None | 0 | None | []
  VARIABLE_CONSIDERATION | CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | None | 0 | None | []
refund_liability targets (subject | period | value | cause):
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P05 | 6000 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P06 | 6000 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P07 | 6000 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P08 | 6000 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P09 | 6000 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P10 | 0 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P11 | 0 | CONCESSION
  CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232 | FY2023-P12 | 0 | CONCESSION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-CONC-2 | FY2023-P11 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-CONC-2 | FY2023-P12 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P01 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P02 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P03 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P04 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P05 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P06 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P07 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P08 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P09 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P10 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P11 | 0 | VARIABLE_CONSIDERATION
  CG-Contract 2@US01/VARIABLE_CONSIDERATION/Contract 2/VC-ROW-1 | FY2023-P12 | 0 | VARIABLE_CONSIDERATION
concession_created_cum targets (subject | period | value | cause):
  Contract 2/POB %232 | FY2023-P05 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P06 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P07 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P08 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P09 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P10 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P11 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
  Contract 2/POB %232 | FY2023-P12 | 6000 | CG-Contract 2@US01/CONCESSION/Contract 2/EV-000008/Contract 2/POB %232
presentation targets contract_liability / refund-related (subject | measure | period | value):
  CG-Contract 2@US01 | contract_liability | FY2023-P10 | 0
  CG-Contract 2@US01 | contract_liability | FY2023-P11 | 6000
  CG-Contract 2@US01 | contract_liability | FY2023-P12 | 0
contract_version columns (compared) CG-Contract 2: {'transaction_price': '104000', 'revenue_cum': '104000', 'billed_cum': '104000', 'rpo_amount': '0'}
obligation_version columns (compared) — POB #2:
  Contract 2/POB %232: {'original_allocated_amount': '31385', 'original_allocated_exact': '4080/13', 'allocated_amount': '32519', 'allocated_exact': '8780/27', 'delivered_quantity_cum': '3', 'revenue_cum': '32519', 'delivered_quantity': '3', 'billed_cum': '30498', 'pre_standard_revenue_cum': '0'}
OutputBundle balances (what the checkpoint compares) for FY2023-P10..P12:
  Contract 2@US01 FY2023-P10: nonzero columns {'entity': 'US01', 'functional_currency': 'USD', 'txn_currency': 'USD'}
  Contract 2@US01 FY2023-P11: nonzero columns {'entity': 'US01', 'functional_currency': 'USD', 'txn_currency': 'USD', 'contract_liability_txn': '6000', 'contract_liability_functional': '6000'}
  Contract 2@US01 FY2023-P12: nonzero columns {'entity': 'US01', 'functional_currency': 'USD', 'txn_currency': 'USD'}
posting intents touching REFUND_LIABILITY / CONTRACT_LIABILITY / REVENUE in P11..P12 (period | role | account | amount | reason | description):
  FY2023-P11 | REVENUE_RECOGNITION | EVENT | Contract 2/POB %232 | reason=None | origin=None
      {'side': 'D', 'account_role': 'REVENUE', 'account_code': '5002', 'amount_txn': '6000', 'amount_functional': '6000'}
      {'side': 'C', 'account_role': 'CONTRACT_LIABILITY', 'account_code': '21002', 'amount_txn': '6000', 'amount_functional': '6000'}
[exit 0] [after-credit-memo] intermediates captured

### end — date: 2026-09-20 07:15:55 PDT

step summary:
  [exit 0] fixture hash unchanged
  [exit 0] original checkpoints reproduced (7 mismatches; seven expected)
  [exit 0] [full-delivery] intermediates captured
  [exit 0] [after-concession] November position captured (complete=True)
  [exit 0] [after-concession] inferred concession event = Contract 2/EV-000008 @ 2023-05-31
  [exit 0] [after-concession] intermediates captured
  [exit 0] [after-credit-memo] November position captured (complete=True)
  [exit 0] [after-credit-memo] inferred concession event = Contract 2/EV-000008 @ 2023-05-31
  [exit 0] [after-credit-memo] intermediates captured
```

## 6. Qualifications appended after Codex packet production-20260920-1430 item 2 (review of this file at b00d22f0; supervisor instruction)

Codex's review (PRODUCTION-VC113-PRODUCER-DIAGNOSTIC-REVIEW-b00d22f0.md, SHA256 e82e5597bd143bdb78fa5c047bec1d091bf3f151ef7192c956d6418a495fff6e; manifest source-observations/vc113-producer-diagnostic-128bafcb/manifest.json, SHA256 aab1e85e2a340166895713238cc7e6844b16770401edfc84cdbd784a5cff6b42; 9 artifacts) found the latest raw capture equal to the 07:15 embedded capture, the seven mismatch strings equal to the 07:12 capture, and the chain confirmed. Two qualifications, recorded as instructed:

(a) **The P05–P09 `refund_liability` target of 6000 (§3 step 5, §5) is a value inside the November / December recomputation** — the checkpoint bundle as of 2023-11-30 or 2023-12-31 recomputed over the whole stream, whose CONCESSION component carries the inferred May 31 origin and is therefore valued from FY2023-P05. It is not evidence of an actual May posting, nor of a separately fixed May `known_at` read; no May-dated computation was run or examined.

(b) **Source relation of this head to Codex's read head, stated exactly.** Between `71e46a8c` (this capture) and main `91575093` (Codex's source read) the stage-08 `estimates.py` and the stage-10 `refund_liability.py` are identical; the WHOLE stage-06 `legacy_templates.py` differs by lane T1F's currency arguments and trace metadata (the amount expressions are preserved). §1 therefore no longer says "unchanged" for the three stages as a whole. Two further limits of the capture: the script's exit 0 is the completion of the diagnostic steps, not an acceptance of the original key (the seven mismatches stand); and the `run_books(check=None)` re-run used to read the stage states is an intermediate inspection, not a new invariant pass — the invariant checks ran only in `run_engine`'s `compute`.
