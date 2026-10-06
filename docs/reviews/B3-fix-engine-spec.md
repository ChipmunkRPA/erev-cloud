# B3 fix pass: `docs/accounting/ENGINE_SPEC.md` and `docs/accounting/ENGINE_SPEC_B.md` (slug `fix-engine-spec`)

| Field | Value |
|---|---|
| Author | Owner-editor, design phase B3 (slug `fix-engine-spec`) |
| Date | 2026-09-12 |
| Files edited | `docs/accounting/ENGINE_SPEC.md` (rev 1.0 → rev 1.2); `docs/accounting/ENGINE_SPEC_B.md` (rev 1.0 → rev 1.2). Each revision log row 1.2 holds "Applied" and "Decisions taken in B3" |
| Binding inputs | `docs/01-DECISIONS.md` D-25b, D-76, D-77; `docs/reviews/B3-fix-fix-data-model.md` (04 rev 1.2 literals); `docs/reviews/B3-fix-fix-policies.md` (POLICIES rev 1.2 POL, JET, ALG and CHK values); `docs/reviews/objections-engine-spec-b.md`; the open questions OQ-A-01 to OQ-A-24 and OQ-B-01 to OQ-B-24; `_coverage/answer-keys-fx-entity-books:OQ-AK-03`, `OQ-AK-04`, `OQ-AK-05`; `_coverage/answer-keys-industries` D-6, `OQ-AKI-12` |
| Scratch | `.scratch/b3-fix-engine-spec/`: rev 1.0 backups `ENGINE_SPEC.rev1.0.bak.md` and `ENGINE_SPEC_B.rev1.0.bak.md`; `verify_examples_a.py` and `verify_examples_b.py` (copies of the B2 scripts, extended); `check_engine_spec_b3.py` (self-check); run logs `run_*_final.txt`, `check_run_final.txt` |
| Size | ENGINE_SPEC.md 1,631 → 1,650 lines; ENGINE_SPEC_B.md 2,326 → 2,420 lines |

## 1. Rulings and questions → changes

| Ruling or question | Change (file, section, id) | Status |
|---|---|---|
| D-25b monetary liabilities (OBJ-B-01; `ENGINE_SPEC_B:OQ-B-15`) | ENGINE_SPEC_B §12 intro; §12.1 input row and `layer_movements`, `functional_targets`, `remeasurement_targets` (JET-10d); §12.2.2 `Layer.role`, `MONETARY_ROLES`, `process_monetary_liability_flows`; new S12-R-19 (recognition at spot, JET-10d difference), S12-R-20 (settlement and decrease at spot; criteria-met layer dated the transfer date), S12-R-21 (consideration payable stays open); S12-R-06 (refund-liability increase beyond layers at spot); §12.2.3 heading and pseudocode loop; S12-R-11 rewritten; S12-INV-03 and S12-INV-06 amended; new S12-INV-08; §12.5 formula ids; §12.6; new EX-12-B (CHK-084); S10-R-13; Table 14-A JET-10d row; S14-R-05 | applied |
| D-25b (deposit side in stages 01 to 08) | ENGINE_SPEC S02-R-08 (deposit liability remeasured by stage 12); §2.5 references JET-10d, CHK-084 (b) | applied |
| `ENGINE_SPEC_B:OQ-B-14` (JET-10c; E-86 `LIABILITY_LAYER_REMEASURED`) | ENGINE_SPEC_B S12-R-08 (JET-10c published); S12-R-12 amended (every liability remeasurement stored as `LIABILITY_LAYER_REMEASURED`; interim storage withdrawn); §16.3 | applied |
| D-76 financing interest in the position (`OQ-B-09`, `OQ-AK-04`, industries D-5, `OQ-AKI-12`) | ENGINE_SPEC_B S10-R-10; §10.2.7 `accretion_attributed` and R_p; S10-R-20; §10.5 node `accretion_attributed_cum`; new EX-10-C (CHK-137: NP −837,959.00; UR 837,959.00; CA 0.00). ENGINE_SPEC S04-R-13 | applied |
| D-76 significant financing component rate (`ENGINE_SPEC:OQ-A-16`, `OQ-AK-05`, `OQ-AKT-13`) | ENGINE_SPEC S04-R-11 cites POL-047 and 04 T-CON-23 `compounding`; EX-04-B re-baselined to `MONTHLY` (month 1 20.00; month 12 246.71 / 21.13; month 24 508.64 / 22.43; years 246.71 and 261.93; revenue at transfer 4,508.64), with the `ANNUAL` variant (240.00 / 254.40 / 4,494.40) as the CHK-136 second row; §16 OQ-A-16 | applied; recomputed by script |
| D-76 contract-cost impairment with renewals (industries D-6, `OQ-AKI-13`) | ENGINE_SPEC_B §11.2.4 pseudocode comments; S11-R-09 (anticipated renewal consideration and costs; 340-40-35-4 as amended by ASU 2016-20) | applied |
| D-76 uninstalled materials (`POLICIES:OQ-15`, industries D-7) | ENGINE_SPEC_B S09-R-14 (revenue equal to cost through JET-02; no `COST_OF_REVENUE` line); Table 14-A JET-02 row | applied |
| D-76 allocation basis (`ENGINE_SPEC:OQ-A-04`, `ENGINE_SPEC_B:OQ-B-02`) | ENGINE_SPEC S04-R-02 (member signs; persisted V1 of 04 DB-17); S04-R-08 (`expected_returns` memo on Y + E); §5.5 S05-INV-01. ENGINE_SPEC_B S09-R-02, S09-R-23 | applied |
| Cross-file: ENGINE_SPEC_B §0.5 wording (`OQ-A-22`) | `recognition_start_date` by stage 03 was already correct; `tp_unconstrained` comment cites S04-R-21; no `§4.5` reference remains; OQ-A-22 marked resolved | applied |
| Cross-file: `BookOutput.contract_version` optional for LEGACY (`OQ-B-16`) | ENGINE_SPEC §0.5 comment (resolved); ENGINE_SPEC_B S13-R-11 | applied |
| Cross-file: `billed_cum` attribution per document (`OQ-B-17`, `OQ-AK-03`) | ENGINE_SPEC S01-R-19; ENGINE_SPEC_B §9.1 paragraph; §10.2.1 `attribute_document` (\|T\| apportioned once per document, sign applied after); S10-R-01; S10-R-03; S10-INV-04; §10.5 `billed_cum` and `billed_attributed_cum` nodes | applied |
| Cross-file: `PostedAmountInput.origin_period_key`, `posting_class` (`OQ-B-19`) | ENGINE_SPEC §0.4 comment (resolved); ENGINE_SPEC_B S14-R-04 | applied |
| Cross-file: `decompose_prior_period` covers measure changes (`OQ-B-20`) | ENGINE_SPEC S08-R-14 (resolved); ENGINE_SPEC_B S15-R-13 | applied |
| Cross-file: stage 08 signatures used by ENGINE_SPEC_B | ENGINE_SPEC Table 0.2-A and §8.5 type `decompose_prior_period(ctx: BookContext, st: AllocatedState, period_key: str, tb: TraceBuilder)`; ENGINE_SPEC_B §0.4 (stages 14 and 15 call the stage 08 exports with the published signatures; member `allocated`); §9.1 output row `allocated`; S15-R-13. `assign_posting_period(ctx, entity, effective_date)` in derive_intents already matched | applied |
| `ENGINE_SPEC:OQ-A-06` to `OQ-A-10` (04 members) | ENGINE_SPEC §0.4 `ProductInput.assurance_cost_per_unit`, `ContractInput.noncash_consideration`, `consideration_payable`, `payment_schedule`, `scope_605_35`, `SspEntryInput.observable_point`; §4.1; S03-R-08; S04-R-10; S04-R-14; S04-R-18; S05-R-07 | applied |
| `ENGINE_SPEC:OQ-A-11` to `OQ-A-13` (codes) | ENGINE_SPEC Table 0.8-A rows `PRINCIPAL_AGENT_NOT_ASSESSED`, `VC_TARGET_TOLERANCE_EXCEEDED`, `OPENING_BALANCE_INCONSISTENT`; interim branches removed from S03-R-09, S05-R-14, S07-R-03; §3.4, §5.5, §7.5 | applied |
| `ENGINE_SPEC:OQ-A-18`, `OQ-A-19`, `OQ-A-20`, `OQ-A-21`, `OQ-A-24`, `OQ-A-02` | S06-R-07 (`price_change_settlement`; `MOD_ATTRIBUTE_CONFLICT` `ERROR`); S07-R-08 (`fair_value_contract_liability`); Table 0.4-A (04 T-CON-19 schemas; new row `BILL_AND_HOLD`); §2.1 `StatusSegment.reason` → `status_reason_in_book`; CV-22 (T-CON-18 `layer_key`) | applied |
| `ENGINE_SPEC:OQ-A-01`, `-03`, `-05`, `-14`, `-15`, `-17`, `-23` | Owned by DG, 05 or POLICIES (applied there in rev 1.2) or already followed by this file; §16 status column cites where | applied (status marked) |
| `ENGINE_SPEC_B:OQ-B-03` | S09-R-11 applies POL-095 `recognition.control_trigger`; Table 13-A row 09 | applied |
| `ENGINE_SPEC_B:OQ-B-04` | S09-R-12 (E-56 `BILL_AND_HOLD` with the four 55-83 members; `BILL_AND_HOLD_CRITERIA_UNMET`); §9.4 | applied |
| `ENGINE_SPEC_B:OQ-B-05`, `OQ-B-07`, `OQ-B-08` | S09-R-14 and pseudocode comment; §10.2.4 VC row; S10-R-07 and §10.4 | applied |
| `ENGINE_SPEC_B:OQ-B-06` | EX-09-E cites the renamed CHK-110 column | applied |
| `ENGINE_SPEC_B:OQ-B-11`, `OQ-B-12`, `OQ-B-13`, `OQ-B-18` | S11-R-04; S11-R-12 and Table 14-A JET-09f; §11.1, `loss_units` pseudocode, S11-R-15 (`scope_605_35`, `EAC_IAS37`), §11.6; Table 14-A JET-12; Table 14-A JET-04c entry kind `RECEIVABLE_CONTRA` | applied |
| `POLICIES:OQ-13` triggers cited by ENGINE_SPEC_B | Table 14-A JET-16 (`WARRANTY_CLAIM`) and JET-17 (`form = NONCASH`) | applied |
| `ENGINE_SPEC_B:OQ-B-01`, `-10`, `-21`, `-22`, `-23`, `-24` | Defaults kept; S10-R-21 wording; §17 status column | applied (status marked) |
| Resolution markers (D-76) | ENGINE_SPEC §16 intro and new "Status (rev 1.2)" column for OQ-A-01 to OQ-A-24; ENGINE_SPEC_B §17 intro and status column for OQ-B-01 to OQ-B-24; CV-04 and C-08 record that no proposed identifier remains; ENGINE_SPEC_B §16.3 retitled "Identifiers adopted by D-76" with the published owners; §16 title; §16.4 rows D-25b, D-76, D-77; ENGINE_SPEC §17 closure rows | applied |
| D-77 | Header status "frozen after B3"; revision log "Decisions taken in B3" in both files; no new open question | applied |
| Section I index (D-74) | ENGINE_SPEC Section I rows for ENGINE_SPEC §16 and ENGINE_SPEC_B §16 and §17 | applied |
| Self-check defects found in rev 1.0 | ENGINE_SPEC_B S09-R-41 row had 3 cells in a 4-column table (cell added); S11-R-07 cited acceleration as S11-R-11 (→ S11-R-13); ENGINE_SPEC EX-08-D was referenced but never defined (split into its own paragraph) | applied |

## 2. Decisions taken in B3

ENGINE_SPEC rev 1.2 logs 6 decisions and ENGINE_SPEC_B rev 1.2 logs 10. The material ones:

| # | Decision | Where |
|---|---|---|
| A-2 | The `expected_returns` memo is −Σ round(r_p × (Y_p + E_p)), so 04 DB-17 V1 holds exactly after actual returns | ENGINE_SPEC S04-R-08 |
| A-6, B-10 | `RecognitionState.allocated` (carried by every later state) supplies the `AllocatedState` argument of `decompose_prior_period` | ENGINE_SPEC §8.5; ENGINE_SPEC_B §0.4, §9.1 |
| B-2 | A non-permitted POL-095 trigger that reaches the engine transfers no control; trace reason `TRIGGER_NOT_PERMITTED`; no finding | S09-R-11 |
| B-3 | Stage 10 emits `billed_cum` for every obligation | S10-R-03; §10.5 |
| B-5 | Net JET-11 accretion is attributed over the obligations for which S04-R-10 requires an adjustment, by posted allocation, then resolved SSP | S10-R-20 |
| B-6 | Renewal costs in the impairment test are those in the `EAC` version in force; no data member added | S11-R-09 |
| B-8 | A consideration-payable layer has no settlement event in 04 rev 1.2; it stays open and is remeasured at every period end | S12-R-21 |

## 3. Verification

| Check | Result |
|---|---|
| `verify_examples_a.py` (exact rationals) | 133 checks, all pass (rev 1.0: 127). New checks: EX-04-B `MONTHLY` month 1, month 12, month 24, year totals, liabilities, financing adjustment and revenue at transfer |
| `verify_examples_b.py` | 107 checks, all pass (rev 1.0: 92). New: EX-10-C (CHK-137 NP, R_p, U, UR, CA and the withdrawn rev 1.0 split) and EX-12-B (CHK-084 (a) to (c): layers, remeasurements, settlement shares, revenue 10,780.00, net FX loss 10.00, deposit 20.00 and 10.00, consideration payable gain 500.00) |
| Agreement with POLICIES rev 1.2 | EX-04-B equals CHK-136 both rows; EX-10-C equals CHK-137; EX-12-B equals CHK-084 |
| `check_engine_spec_b3.py` | 0 findings: table cell counts in both files; internal ids (CV, C, S-rules, invariants, EX, OQ-A, OQ-B; 574 defined); POL, ALG, CHK and JET parts against POLICIES; E-nn and T-tables against 04; D-numbers; REQ; DEV; finding codes of every findings table against 04 §15.4; Section I covers every section and subsection of both files |

## 4. Not applied, and gaps for other owners

| Item | Reason or owner action |
|---|---|
| Settlement record for consideration payable | 04 rev 1.2 holds no event for an AP settlement of a promised payment. The engine therefore remeasures open foreign-currency promises at every period end (S12-R-21; POLICIES decision 5), and the subledger `CONSIDERATION_PAYABLE` functional balance can drift from the ERP after the ERP pays. This is not a build blocker; it is raised here for the supervisor (D-77 permits no new open question) |
| Answer key for EX-12-B and for the CHK-136 `ANNUAL` row | POLICIES B3 report already asks the answer-key owner for CHK-084 and CHK-136 `ANNUAL` keys |
| `_coverage` keys still using `billing_plan`, `assurance_cost_rate`, `observable_point_value` | dev-guide B3-DG mappings and the B3 adjudicator own them |
