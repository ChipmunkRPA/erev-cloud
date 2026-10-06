# B3 fix pass: `docs/accounting/POLICIES.md` (slug `fix-policies`)

| Field | Value |
|---|---|
| Author | Owner-editor, design phase B3 (slug `fix-policies`) |
| Date | 2026-09-12 |
| File edited | `docs/accounting/POLICIES.md` only (rev 1.1 → rev 1.2; revision log row 1.2 with "Applied" and "Decisions taken in B3") |
| Binding inputs | `docs/00-GOAL.md`; `docs/01-DECISIONS.md` §7 and §8 (D-25b, D-76, D-77); `docs/reviews/objections-engine-spec-b.md`; open questions of ENGINE_SPEC, ENGINE_SPEC_B and the three `_coverage/` files |
| Scratch | `.scratch/b3-fix-policies/`: `POLICIES.rev1.1.bak.md` (backup), `verify_checks_b3.py` (recomputation), `lint_policies_b3.py` (self-check) |

## 1. Rulings and questions → changes

| Ruling or question | Change (file `docs/accounting/POLICIES.md`: section, id) | Status |
|---|---|---|
| D-25b (OBJ-B-01; `ENGINE_SPEC_B:OQ-B-15`) | §1.10 POL-164 literal `ASSET_POSITIONS_ENGINE_AR_AND_MONETARY_LIABILITIES` and engine effect; §2.3 new JET-10d; table 2.3-B JET-10 triggers; §2.9 ALG-08 heading, §2.9.1 recognition, period-end and settlement rows, §2.9.2 bullet, §2.9.3 CHK-084 row; JET-10 CHK-084 posting view; §6.4 D-25b row; §7 M-RA-02 and OBJ-B-01 rows | Applied |
| D-76 financing interest (`ENGINE_SPEC_B:OQ-B-09`, `OQ-AK-04`, industries D-5, `OQ-AKI-12`) | §2.2 ALG-02 definition (JET-11 accretion is in NP) and step 3 (R_p includes the net JET-11 accretion); JET-11 CHK-137 explanation | Applied |
| D-76 SFC rate (`ENGINE_SPEC:OQ-A-16`, `OQ-AK-05`, `OQ-AKT-13`) | §1.4 POL-047 value `{basis, annual_rate, compounding}`, `compounding` ∈ {`MONTHLY` (default), `ANNUAL`}; JET-11 11a and 11b amounts; CHK-136 table: `MONTHLY` 246.71 / 261.93 / 4,508.64, `ANNUAL` 240.00 / 254.40 / 4,494.40 | Applied; both rows recomputed by script |
| D-76 CHK re-baselines (`OQ-AKT-01`, `OQ-AK-02`) | §2.6.5 CHK-053 (P2 3,492.91; CL end P2 1,073.30); §2.1.5 CHK-006 rows S2-WARRANTY-OWN, S5-EX63-OWNSSP and S12-FRANCHISOR-OWN to D-11a values | Applied; verified against `MR-CHK-053-S2-EX52`, `RND-CHK-006-S2-WARRANTY-OWN-EXTENDED-WARRANTY`, `RND-CHK-006-S5-EX63-OWNSSP-CUSTODY`, `RND-CHK-006-S12-FRANCHISOR-OWN-LICENCE-TEN-YEARS` |
| D-76 contract-cost impairment (industries D-6, `OQ-AKI-13`) | JET-09c: remaining expected consideration and costs include anticipated renewals and extensions (340-40-35-3, 35-4 as amended by ASU 2016-20) | Applied |
| D-76 uninstalled materials (`POLICIES:OQ-15`, industries D-7) | POL-091; new JET-02 row "Uninstalled materials"; §0.8 `COST_OF_REVENUE`; §8 OQ-15 | Applied |
| `_coverage/answer-keys-topics:OQ-AKT-02` | POL-076 test (c): discount amounts compared as shares of S_B; Example 34 Cases A and B figures | Applied |
| `OQ-AKT-03` | ALG-06 step 6 (step 2 governs; rate r); POL-052 (applies only under `RESTORE_REMAINING_QUANTITY`); §2.7.3 | Applied |
| `OQ-AKT-04` | §2.1.2 Uses: one apportionment over exact quotas | Applied |
| `_coverage/answer-keys-fx-entity-books:OQ-AK-01`, `OQ-AK-03`, `OQ-AK-12` | §0.3 case-insensitive CHK containment; ALG-02 step 3 per-document attribution; ALG-08 same-day order | Applied |
| `_coverage/answer-keys-industries:OQ-AKI-05`, `OQ-AKI-08`, `OQ-AKI-16` | JET-02 agent gross relief; ALG-04 §2.5.5 post-modification progress; JET-12 margin to date | Applied |
| `ENGINE_SPEC:OQ-A-06`, `OQ-A-12`, `OQ-A-14`, `OQ-A-15`, `OQ-A-17`, `OQ-A-18` | POL-022 and JET-16 `assurance_cost_per_unit`; POL-044 override judgement; POL-045 IFRS taxes; POL-051 levels P, C, O and returnable rule; POL-076 approval judgement; JET-05 settlement mode | Applied |
| `ENGINE_SPEC_B:OQ-B-03` | New POL-095 `recognition.control_trigger` (§1.6) | Applied |
| `ENGINE_SPEC_B:OQ-B-04`, `OQ-B-05`, `OQ-B-07`, `OQ-B-18`, `OQ-B-20`, `OQ-B-21` | POL-094; POL-091; JET-04b and ALG-10 §2.11.1 `refund_liability_target`; JET-04c entry kind `RECEIVABLE_CONTRA`; ALG-10 §2.11.3 boundary formula; POL-200 | Applied |
| `ENGINE_SPEC_B:OQ-B-06` | PT-01 CHK-110 column renamed "Of which revenue from prior-period performance"; note on `revenue_prior_period` −5,000.00 and `catch_up_tp_change_cum` −10,000.00 | Applied |
| `ENGINE_SPEC_B:OQ-B-11` | New JET-09f (clawback, Dr `CONTRACT_COST_CLEARING` / Cr asset role); table 2.3-B; §0.8 | Applied |
| `ENGINE_SPEC_B:OQ-B-14` | New JET-10c (credit-memo settlement difference); §2.9.1 row; table 2.3-B | Applied |
| 04:OQ-10 | JET-01b: `INVOICE_ON_NOT_A_CONTRACT` severity `WARNING` confirmed | Applied |
| PRD:§9 Q10 | POL-016 cites `COMBINATION_SUGGESTED` | Applied |
| `POLICIES:OQ-13`, `OQ-14` | JET-16, JET-17, table 2.3-B, POL-022 (`WARRANTY_CLAIM`, noncash `PAYMENT_RECEIVED`); ALG-10 §2.11.1 and PT-10 (`SHARE_BASED_CONSIDERATION`); §8 "Resolved by D-76" | Applied |
| Assignment: JET-01b refund on termination | JET-01b row `CONTRACT_TERMINATED` with `refund_amount`: Dr `DEPOSIT_LIABILITY` / Cr `BILLING_CLEARING` (`UNAPPLIED_CASH`); table 0.8-A; table 2.3-B | Applied |
| Assignment: JET-07 07d entry kind | JET-07 paragraph: 07c and 07d post with E-29 `RETURN_ASSET` | Applied |
| Assignment: ALG-02 step 5 terminal step | POL-121; §6.1; §6.3; §6.4 D-12 row | Applied |
| D-77 | Revision log "Decisions taken in B3"; no new open question; §8 intro | Applied |
| Other D-76 items (ENGINE_SPEC OQ-A-01 to 05, 07 to 11, 13, 19 to 24; ENGINE_SPEC_B OQ-B-01, 02, 08, 10, 12, 13, 16, 17, 19, 22 to 24; OQ-AKI-01 to 04, 06, 07, 09 to 11, 14, 15, 17 to 21; OQ-AKT-05 to 12, 14 to 20; OQ-AK-02, 06 to 11, 13 to 16; SCREENS, SCREENS_B, 03:§11 Q4, DG, DS, DEVIATIONS) | None | Not applicable: schema, loader, UI or other owners; POL-201, §3 and the remaining sections already agree |

## 2. Decisions taken in B3 (D-77)

| # | Decision | Where |
|---|---|---|
| 1 | The `ANNUAL` variant keeps the id CHK-136 as a second table row, so any key whose id contains CHK-136 covers it | JET-11; §0.3 |
| 2 | The D-25b check takes the free id CHK-084 in the ALG-08 range | JET-10; §2.9.3 |
| 3 | A monetary-liability layer is created at spot on recognition. A difference from the historical relief of contract-liability layers posts by JET-10d at recognition. A refund-liability increase beyond the open contract-liability layers creates an asset layer at spot | §2.9.1 |
| 4 | At settlement, the settled portion is remeasured to spot on its cumulatively rounded carrying share and relieved at spot. Window expiry, criteria met, refund on termination and 25-7 derecognition are settlements. A deposit transferred on criteria met creates a contract-liability layer at the transfer-date spot (IFRIC 22.8) | §2.9.1; CHK-084 (b) |
| 5 | A consideration-payable promise with no recorded settlement stays open and is remeasured at every period end | §2.9.1; CHK-084 (c) |
| 6 | Financing accretion is attributed to POBs by posted allocation over the POBs that carry the financing adjustment | ALG-02 step 3 |
| 7 | POL-076 test (c) counts a residual-eligible POB at the residual computed with the proposed exception | POL-076 |
| 8 | POL-095 permits `CONTROL_TRANSFER` under both restricted options, rejects other triggers with 422 `validation-failed`; parity n/a | POL-095 |
| 9 | POL-051 gains levels C and O, with OVR approval, to match ENGINE_SPEC S04-R-08a | POL-051 |
| 10 | ALG-04 §2.5.5 applies OQ-AKI-08 with the exact segment share X′_p − R_p (D-11a), not the posted share s_p | ALG-04 §2.5.5 |
| 11 | Under `ENGINE`, JET-10c posts the difference as an `FX_GAIN_LOSS` line of the JET-03 credit-memo entry | JET-10c |
| 12 | §2.7.3 notation X → N (a residue of B1-001 item 5) | ALG-06 §2.7.3 |

## 3. Verification

| Check | Result |
|---|---|
| `.scratch/b3-fix-policies/verify_checks_b3.py` (exact rationals, half-up) | 62 checks, all pass. They cover: the CHK-006 three rows (and that the rev 1.1 values were round(A × f)); unchanged CHK-006 rows S2-EX11 and S8; CHK-053; CHK-136 `MONTHLY` (months 1, 12 and 24; year totals; liabilities; revenue) and `ANNUAL`; CHK-137 (NP −837,959.00, UR 837,959.00 under rev 1.2 versus 829,475.53 under rev 1.1 step 3); CHK-084 (a) to (c), including the cash tie-out; POL-076 test (c) (rev 1.1 11.4 pp → rev 1.2 0 pp); CHK-110 (−5,000.00 and −10,000.00) |
| Answer-key agreement | CHK-136 `MONTHLY` equals `JE-CHK-136-S3-EX29-ADVANCE-PAYMENT-ACCRETION` (4,246.71; 4,508.64; 20.00; 21.13; 22.43) and `SFC-S3-EX29` (4,508.64). CHK-053 equals `MR-CHK-053-S2-EX52`. The CHK-006 rows equal the three `RND-CHK-006-*` keys. CHK-137 equals `SFC-S3-EX28-CASEB` (UR 837,959.00) |
| `.scratch/b3-fix-policies/lint_policies_b3.py` | 0 undefined ids, 0 undefined JET parts, 0 malformed table rows, every OQ row resolved, every `BILLING_CLEARING` posting has a purpose, JET roles among the 33 roles, event literals in 04 E-03. One expected multi-row part: JET-10a gain and loss rows, as in rev 1.1. Counts: POL 131, CHK 76, ALG 11, PT 11, ASU 27, OQ 15 |
| `.scratch/design-fix-policies/lint_policies.py` (B2) | No undefined references; 0 wrong column counts |

## 4. Gaps and follow-ups for other owners (not edited here)

| Owner | Needed change | Reason |
|---|---|---|
| Answer keys (fx-entity-books slice) | Author a key for CHK-084, and one for the CHK-136 `ANNUAL` row (no key uses `compounding: ANNUAL`) | §0.3 CHK containment; D-76 |
| Answer keys | Keys whose ids contain CHK-031, CHK-117, CHK-120, CHK-121, CHK-133, CHK-134, CHK-135 and CHK-137 were not found. `SFC-S3-EX28-CASEB` asserts the CHK-137 figures, but its id does not contain the id | Pre-existing; G4 coverage |
| `docs/04-DATA_MODEL.md` | At the time of this pass, 04 did not yet carry these D-76 literals that POLICIES cites verbatim: `WARRANTY_CLAIM`; noncash `PAYMENT_RECEIVED`; E-09 `SHARE_BASED_CONSIDERATION`; `compounding`; `cost_adjustment` `CLAWBACK`; E-56 `BILL_AND_HOLD`; `BILL_AND_HOLD_CRITERIA_UNMET`; `assurance_cost_per_unit`; `refund_liability_target`; `uninstalled_materials_cost`; E-29 `RECEIVABLE_CONTRA`; `VC_TARGET_TOLERANCE_EXCEEDED`; `COMBINATION_SUGGESTED`; E-86 `LIABILITY_LAYER_REMEASURED`. 04 governs spelling (D-73) | D-76 schema and API additions |
| `docs/04-DATA_MODEL.md`, `docs/accounting/ENGINE_SPEC_B.md` | A settlement record for consideration payable settled by accounts payable; POLICIES remeasures open promises at every period end until one is recorded | D-25b "at settlement" |
| `docs/accounting/ENGINE_SPEC_B.md` | §10.2.7 and S10-R-20: R_p includes the net JET-11 accretion (ALG-02 step 3). S12-R-11 is superseded by D-25b; stage 12 needs recognition and settlement layers for the three monetary liabilities (§2.9.1). JET-10c and JET-09f are now published | D-76; D-25b |
| `docs/05-ARCHITECTURE.md`, `docs/03-REQUIREMENTS.md` | EMOD-18 position and rounding rows, EMOD-16 impairment with renewals, REQ-BIL-007 and REQ-REC-007 (D-76 amendments) | D-76 |
| Naming conflicts noted | OQ-AKI-14 proposes `assurance_cost_rate`, but POLICIES uses `assurance_cost_per_unit` (ENGINE_SPEC:OQ-A-06, named in the D-76 schema ruling). OQ-AKT-05 (`settlement`) and OQ-A-18 (`price_change_settlement`) differ, so JET-05 cites no literal | D-73 |
