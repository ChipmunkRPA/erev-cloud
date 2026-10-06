# eRev Cloud: accounting policies, judgement parameters and posting algorithms

| Field | Value |
|---|---|
| Document | `docs/accounting/POLICIES.md` |
| Owner | Chief technical accountant for ASC 606, IFRS 15 and ASC 340-40 (design slug `ra-policies`) |
| Date | 2026-09-11 (rev 1.0); 2026-09-12 (rev 1.1, rev 1.2 and rev 1.3); 2026-09-17 (rev 1.4, rev 1.5 and rev 1.6); 2026-09-18 (rev 1.7) |
| Revision | 1.125 (2026-10-03, lane SECFIX-CLO, item PRODUCT-POLICY-VALUE-NOT-READ-1 — supervisor ruling R-126 (c) and the supervisor's rulings of 2026-10-03 on the lane's list; number assigned by the supervisor, register index 309: §0.5 rule 1 and the rows of POL-021, POL-029 and POL-240 — the engine reads the three for a contract, so a value at level P is read by no computation, and a product and an obligation template state none of them but the framework's default of POL-240 and POL-029; no option value, default, level or force changes); 1.124 (2026-10-03, lane SECFIX-PLT, item POLICY-OVERRIDE-WITHDRAW-1 — supervisor ruling R-126 (b) (4) and (c) and the supervisor's rulings of 2026-10-03 on the lane's line; number assigned by the supervisor, register index 308: §0.5 rule 5 and table 0.5-A — no contract-level or POB-level policy override is offered in release 1.0, and what decides each of the 23 parameters that list level C or O instead; rule 2 and §0.6 OVR marked; no option value, default or force changes); 1.123 (2026-10-01, lane ENG-FX, item PINP-PERIOD-VALUE-1 — release blocker; the supervisor's ruling (A) of 2026-10-01 on the lane's stop; number assigned by the supervisor, register index 143: §0.5 rule 3, pin P — before a workspace has its first legal entity a version may take effect on an earlier day, which is how a tenant that migrates states the policy of its history; no option value, default or force changes); 1.122 (2026-10-01, lane ENG-FX, item PINP-PERIOD-VALUE-1 — PRODUCT DEFECT, release blocker; supervisor ruling R-121 (e) of 2026-10-01 and the supervisor's rulings of the same day on the lane's measured finding and on its pre-build line; number assigned by the supervisor, register index 143: §0.5 rule 3, pin P — a period of a legal entity takes the value in force for that entity at the period's last instant in the entity's time zone, or at the computation's instant while the period has not ended, among the versions published by then; a first version without an effective date answers for every earlier period and a later one from its publication ([J], candidate AD-79); a parameter without a framework default has no value before its first version; no option value, default or force changes); 1.97 (2026-10-01, lane ENG-FX, item PIN-READBACK-1 — PRODUCT DEFECT, release blocker; supervisor rulings R-116 (d) of 2026-09-30 and of 2026-10-01 on the lane's measured finding; number assigned by the supervisor, register index 89); 1.77 (2026-10-01, lane ENG-FX, item PIN-K-COMBINATION-1, supervisor ruling R-112 (i); number assigned by the supervisor, register index 69); 1.52 (2026-09-30, lane ENG-FX, item ENG-S12-DUE-DATE-1, supervisor ruling R-81; number assigned by the supervisor, register index 44); 1.33 (2026-09-30, lane ACCT, supervisor ruling R-46; number assigned by the supervisor); 1.8 (2026-09-19, D-92 / D-93 supervisor amendments); 1.7 |
| Status | Binding build contract. Read-only for the build loop (`docs/01-DECISIONS.md` §0) |
| Precedence | Shares the "accounting behaviour" tier with `docs/accounting/ENGINE_SPEC.md` and `docs/accounting/ENGINE_SPEC_B.md` (`docs/01-DECISIONS.md` §0, D-74). For numbers, the machine-readable answer keys in `docs/accounting/answer-keys/` win over this prose; a conflict is a spec question |
| Binding inputs | `docs/00-GOAL.md`; `docs/01-DECISIONS.md` (D-10 to D-34, the §7 amendments D-11a to D-75 and the §8 amendments D-25b, D-76 and D-77); `docs/04-DATA_MODEL.md` for enumeration literals and finding and exception codes (D-73) |
| Background inputs | `docs/research/04` (ASC 606 technical), `05` (industry playbooks), `06` (engine architecture), `07` (controls), `99` (gaps); `docs/legacy/01`-`07` and `docs/legacy/golden/` |
| Gaps owned | M-RA-01, M-RA-05, M-RA-06, C-09, C-12, C-15, U-01, U-02, U-03, U-04, U-08; the policy side of C-02, C-03, C-04, C-06, C-07, C-14, M-RA-02, M-RA-03; M-RA-08 in part (section 7) |

## Revision log

| Rev | Date | Author | Findings and decisions applied |
|---|---|---|---|
| 1.0 | 2026-09-11 | ra-policies (design phase B1) | Initial binding build contract |
| 1.1 | 2026-09-12 | fix-policies (design phase B2) | **B1-004, D-75 (Q3):** POL-090 options `DAILY`, `MONTHLY_EVEN` (replaces `MONTHLY_WHOLE_MONTHS`), `MID_MONTH`; new ALG-11 (section 2.12) with CHK-140 to CHK-145. **B1-005:** tables 2.3-A and 2.3-B map event names to 04 E-03 literals and close-run passes; literals used in JET headings, ALG-05, ALG-06, POL-078 and PT-11. **B1-015, D-14a:** section 0.8 adds `COST_OF_REVENUE`, `CONTRACT_COST_CLEARING`, `RECEIVABLE_CONTRA`, reserved roles and table 0.8-A `clearing_purpose`; JET-01b, JET-02, JET-07c, new JET-07d, JET-09a, JET-09a′, JET-14, JET-16, JET-17 and new JET-04c (CHK-138) use them; interim purpose-code text removed. **B1-020:** POL-006 option `CONTRACT_ACCOUNT_DIMENSIONS`. **B1-027:** citation rules in section 0.3; cross-document open questions cited as `<document>:<id>`. **JET-04a notation (B1-001 item 5):** X′_p is the exact allocation, A′_p the posted allocation, in JET-04a, ALG-04, ALG-10; ALG-06 renames units transferred to N. **DEVIATIONS:OQ-D8, OQ-D9:** ALG-02 step 5 fallback chain and POL-052 zero-remaining rate confirmed. **D-11a** (ALG-01 §2.1.3, OQ-12), **D-13a** (POL-004), **D-17a** (POL-001), **D-21a** (POL-026, POL-028, ALG-05), **D-25a** (POL-163), **D-73** (section 0.3 rule 3; POL-074 and section 3 use 04 E-47 literals; ALG-10 kinds are 04 E-09 literals), **D-74** (precedence row), **D-75** (section 8: OQ-01 to OQ-12 resolved; OQ-13 to OQ-15 added). Change record: `docs/reviews/B2-fix-fix-policies.md` |
| 1.2 | 2026-09-12 | fix-policies (design phase B3) | **Applied.**<br>**D-25b:** POL-164 `ASSET_POSITIONS_ENGINE_AR_AND_MONETARY_LIABILITIES`; ALG-08 §2.9.1 and §2.9.2 monetary-liability rows; new JET-10d; new CHK-084; §6.4; §7.<br>**D-76 rulings:**<br>- Financing interest: ALG-02 definition and step 3 include the JET-11 accretion; CHK-137.<br>- SFC rate: POL-047 value `{basis, annual_rate, compounding}` with `MONTHLY` (default) and `ANNUAL`; JET-11 amounts; CHK-136 re-baselined to `MONTHLY` (246.71 / 261.93 / 4,508.64), with `ANNUAL` kept as its second row.<br>- CHK re-baselines: CHK-053 (3,492.91 / 1,073.30); CHK-006 rows S2-WARRANTY-OWN, S5-EX63-OWNSSP and S12-FRANCHISOR-OWN to D-11a.<br>- Contract-cost impairment: JET-09c includes anticipated renewals and extensions.<br>- Uninstalled materials: POL-091, JET-02 row, §0.8, OQ-15.<br>**Adopted defaults that touch this document:**<br>- `_coverage/answer-keys-topics`: OQ-AKT-02 (POL-076 test (c)); OQ-AKT-03 (ALG-06 step 6, POL-052, §2.7.3); OQ-AKT-04 (§2.1.2).<br>- `_coverage/answer-keys-fx-entity-books`: OQ-AK-01 (§0.3); OQ-AK-03 (ALG-02 step 3); OQ-AK-12 (ALG-08 order).<br>- `_coverage/answer-keys-industries`: OQ-AKI-05 (JET-02 agent); OQ-AKI-08 (ALG-04 §2.5.5); OQ-AKI-12 (ALG-02); OQ-AKI-16 (JET-12).<br>- `ENGINE_SPEC`: OQ-A-06 (POL-022, JET-16); OQ-A-12 (POL-044); OQ-A-14 (POL-045); OQ-A-15 (POL-051 levels P, C, O); OQ-A-17 (POL-076); OQ-A-18 (JET-05).<br>- `ENGINE_SPEC_B`: OQ-B-03 (new POL-095 `recognition.control_trigger`); OQ-B-04 (POL-094); OQ-B-05 (POL-091); OQ-B-06 (CHK-110 column); OQ-B-07 (JET-04b, ALG-10); OQ-B-11 (new JET-09f); OQ-B-14 (new JET-10c); OQ-B-18 (JET-04c entry kind); OQ-B-20 (ALG-10 §2.11.3); OQ-B-21 (POL-200).<br>- Others: 04:OQ-10 (JET-01b severity `WARNING`); PRD:§9 Q10 (POL-016); POLICIES OQ-13 to OQ-15 resolved (§8, JET-16, JET-17, ALG-10, PT-10).<br>**Other changes:** JET-01b refund-on-termination row (`UNAPPLIED_CASH`; table 0.8-A, table 2.3-B); JET-07 names entry kind `RETURN_ASSET` for 07c and 07d; the ALG-02 step 5 terminal step is cited in POL-121, §6.1, §6.3 and §6.4; §0.3 document tokens; §2 recomputation note.<br>**Decisions taken in B3 (D-77):**<br>1. The `ANNUAL` variant keeps the id CHK-136 as a second table row, so any key whose id contains CHK-136 covers it.<br>2. The D-25b check takes the free id CHK-084 in the ALG-08 range.<br>3. A monetary-liability layer is created at spot on recognition. A difference from the historical relief of contract-liability layers posts by JET-10d at recognition. A refund-liability increase beyond the open contract-liability layers creates an asset layer at spot.<br>4. At settlement, the settled portion is remeasured to spot on its cumulatively rounded carrying share and relieved at spot. Window expiry, criteria met, refund on termination and 25-7 derecognition count as settlements. A deposit transferred on criteria met creates a contract-liability layer at the transfer-date spot in both books (IFRIC 22.8).<br>5. A consideration-payable promise with no recorded settlement stays open and is remeasured at every period end.<br>6. Financing accretion is attributed by posted allocation over the POBs that carry the financing adjustment.<br>7. POL-076 test (c) counts a residual-eligible POB at the residual computed with the proposed exception.<br>8. POL-095 permits `CONTROL_TRANSFER` under both restricted options and rejects other triggers with 422 `validation-failed`; parity n/a.<br>9. POL-051 gains levels C and O, with OVR approval, to match ENGINE_SPEC S04-R-08a.<br>10. ALG-04 §2.5.5 applies OQ-AKI-08 with the exact segment share X′_p − R_p (D-11a), not the posted share.<br>11. Under `ENGINE`, JET-10c posts the difference as an `FX_GAIN_LOSS` line of the JET-03 credit-memo entry.<br>12. §2.7.3 notation X → N (residue of B1-001 item 5).<br>Change record: `docs/reviews/B3-fix-fix-policies.md` |
| 1.3 | 2026-09-12 | numeric-residue (post-B3 residue sweep) | **Applied (supervisor-directed correction of known residue; D-77 opens no question).**<br>- **JET-09c cap (ADJUDICATION.md R-COST-01, R-COST-03):** the impairment is min(carrying, max(0, carrying − recoverable)), so the asset floors at 0.00; key `COST-S8-CONTRACT-COSTS-IMPAIRMENT` checkpoint `end-2028-floor` (5,000.00).<br>- **Financing month count (R-SFC-02, R-SFC-04):** the POL-047 notes and CHK-136 and CHK-137 state that n counts the calendar month ends between the payment and the transfer, with ⌊n ÷ 12⌋ whole years under `ANNUAL`.<br>- **Suspended accretion (R-SFC-05):** JET-11 11a: nothing accretes while expected returns exclude the whole consideration (ENGINE_SPEC S04-R-12a); the FASB Example 26 figures of key `SFC-S3-EX26-RETURN-RIGHT` follow CHK-137.<br>- §2 recomputation note cites `.scratch/b4-numeric-residue/verify_b4.py`.<br>**Decisions taken in the sweep:**<br>1. JET-09c never impairs beyond the carrying amount. A negative recoverable amount belongs to the loss test (JET-12) when the contract is in the scope of Subtopic 605-35.<br>2. No CHK id is added for the suspended accretion. The key `SFC-S3-EX26-RETURN-RIGHT` carries the figures, so List C coverage does not change.<br>Change record: `docs/reviews/B4-numeric-residue.md` |
| 1.4 | 2026-09-17 | supervisor (D-89 amendments) | **Applied (rulings in `docs/reviews/loop/sprint/D-89-rulings.md`; decision D-89a).**<br>- **D-89 L7-6-Q-7:** JET-09c remaining direct costs = max(0, EAC − costs); without a `PROGRESS_INPUT` cost effective on or before the period end, costs run off with the related obligations' revenue progress since the EAC version's effective date.<br>- **D-89 L7-6-Q-8:** JET-15 reads delta lines = primary-book lines + `LEGACY`-book lines per role; the `LEGACY` book holds the reversal of what the ERP booked |
| 1.5 | 2026-09-17 | supervisor (D-89b editorial; row recorded by D-90) | **Applied (decision D-89b; text on main since 533fcb2).**<br>- **D-89b:** ALG-08 §2.9.1 settlement row: a release to the control role (JET-04b credit, JET-01b criteria met) enters at the release carrying; the contract-liability layer it creates takes that carrying less the asset settlements (D-87 L6-5-Q-26; D-88 L7-6-Q-2) |
| 1.6 | 2026-09-17 | supervisor (D-90b amendment) | **Applied (decision D-90b; MOD-JS-06, L8-D-Q-1).**<br>- **D-90b:** ALG-04 §2.5.4 step 3, D existing row: the `D18_DEFAULT` and `INCEPTION_ALL` weights of a POB measured by time elapsed that is not a series or a VC line scale the carried units by the remaining share ρ_p of their unit layers (§2.12 progress under the pinned convention at the close of d − 1 over the term in force); added units are not scaled; unit histories that net reconstruction cannot represent raise `MOD_UNIT_HISTORY_AMBIGUOUS` (ENGINE_SPEC S06-R-08 and S06-R-11, rev 1.4). MOD-JS-06 weights 39,000.00 / 40,000.00 |
| 1.7 | 2026-09-18 | supervisor (D-91 amendments) | **Applied (decision D-91; no approved answer-key figure changes).** ALG-06 §2.7.2 step 3: E_b on the S10-R-07 identity and the S10-R-06 unconditional date with both proxy legs recorded (supersedes lane note L1-3-Q-13). POL-200 notes: quota in force at the measured date. PT-10: revenue driver, scope, rationale requirement, per-element and per-part rounding, same-population denominator, universal ASU 2025-04 application; CHK-120 invariance sentence. JET-01b rows (rev pending ENA-2b, END-4b): dated 25-7 points, cap and attribution. Change record: `docs/01-DECISIONS.md` D-91 |
| 1.8 | 2026-09-19 | supervisor (D-92 / D-93 amendments) | **Applied (decisions D-92, D-93; no approved answer-key figure changes).** POL-160 note (D-92 (5)): the authority cell gains "D-92 (5): under `INVOICE_ISSUE_DATE` an `ENGINE`-mode cancellable line's issue date is its S10-R-06 billing date … ERP lines keep the invoice issue date; flagged AD-29 for G12" (option values, defaults and force unchanged). §2.5.4 D-series row (D-93 (4)): was "| D series | mod-date SSP of the remaining increments | inception SSP of the remaining increments |" → now "| D series | mod-date SSP of the remaining increments, priced from the SSP entry's declared basis (04 E-49 `PER_INCREMENT` / `PER_BOOKED_TERM` / remaining-increments-at-d; ENGINE_SPEC S06-R-11; D-93 (4)) | inception SSP of the remaining increments, from the entry's basis in the same way |". Change record: `docs/01-DECISIONS.md` D-92, D-93 |
| 1.33 | 2026-09-30 | lane ACCT (supervisor ruling R-46 of 2026-09-30 on G12 AD-13; memo `docs/accounting/reviews/AD-13-14-34-MEMO-2026-09-29.md` §4.5; docs first; number assigned by the supervisor) | **Applied (one paragraph aligned to D-87 L6-5-Q-25; no approved answer-key figure changes — the key `SFC-S3-EX26-RETURN-RIGHT` follows by oracle correction under the same ruling and stays `pending`).** JET-11, the FASB Example 26 paragraph: it read "On 1 April 2026 JET-02 recognises 100.00 and JET-07c reverses the return asset"; the right lapses at the end of `window_end_date`, 31 March 2026, and both entries post at that date. The interest figures (0.95 in April 2026, 8.51 in 2026, 12.49 in 2027) are unchanged. CHK-084 (a), whose window expires on its window-end day (31 May), already states the same convention. The merits of the cut-off remain with the independent accountant (G12 AD-13) |
| 1.52 | 2026-09-30 | lane ENG-FX (item ENG-S12-DUE-DATE-1; supervisor ruling R-81 of 2026-09-30, amending D-87 L6-5-Q-14 and to be transcribed as D-100; docs first; number assigned by the supervisor, register index 44) | **Applied (no approved answer-key figure changes).** POL-160 note: the authority cell gains the definition of D-87 L6-5-Q-14 (in `ERP` mode "unconditional due" is the payload `due_date` when present), which this document had not carried, and the rule of R-81 — the date stays in the accounting period in which the line enters the position (a later date gives that period's end, an earlier date the S10-R-06 date); option values, defaults and force unchanged. ALG-08 §2.9.1, first row: the event date of a billing is that date. Cause: an invoice due, and not paid, after the end of its issue period stood in the position with no layer behind it, so the engine's invariant S12-INV-03 refused the computation of the contract; a receipt dated before the period of the invoice it names did the same. For a foreign-currency contract the liability of such an invoice is measured at the period-end spot of its issue period, a supervisor ruling on a measurement point pending the independent accountant (candidate AD-51); a same-currency figure does not depend on the date. Change record: ENGINE_SPEC_B rev 1.83 (S12-R-04) |
| 1.77 | 2026-10-01 | lane ENG-FX (item PIN-K-COMBINATION-1 — PRODUCT DEFECT; supervisor ruling R-112 (i) of 2026-09-30; docs first; number assigned by the supervisor, register index 69) | **Applied (no approved answer-key figure changes).** §0.5 rule 3, pin K: the rule did not say which values a combination group takes when its member contracts were computed, and pinned, before the combination; the group's first computation resolved every pin-K parameter at the instant of the combination. It now takes the values pinned for the member with the earliest inception date, then external id, and a parameter those values do not hold is resolved at that computation ([J]; candidate AD-58 for the independent accountant; dev-guide DG-KRN-REG-02 rev 1.143). No option value, default or force changes. |
| 1.97 | 2026-10-01 | lane ENG-FX (item PIN-READBACK-1 — PRODUCT DEFECT, release blocker; supervisor rulings R-116 (d) of 2026-09-30 and of 2026-10-01 on the lane's measured finding; docs first; number assigned by the supervisor, register index 89) | **Applied (no approved answer-key figure changes).** POL-070 said "Pins SSP version id and row per POB"; the version was recorded and never read, so an SSP book version approved later with dates covering an earlier pricing date re-allocated posted contracts. The row now says how the pin holds: the version of each pricing — the POB's own and its weight in each modification — is recorded and read back at every later computation; the pin starts at the contract's activation; an approved override wins; a modification computed for the first time prices at its date (POL-080 `D18_DEFAULT` as written). No option value, default or force changes. |
| 1.122 | 2026-10-01 | lane ENG-FX (item PINP-PERIOD-VALUE-1 — PRODUCT DEFECT, release blocker; supervisor ruling R-121 (e) of 2026-10-01 and the supervisor's rulings of the same day on the lane's measured finding and on its pre-build line; docs first; number assigned by the supervisor, register index 143) | **Applied (no approved answer-key figure changes).** §0.5 rule 3, pin P, said "the value in force for the accounting period" and did not say at which instant, for which entity, or among which versions. Finding (the lane's probe of 2026-10-01): the bundle builder resolved every period-pinned parameter once — at the bundle's `known_at`, for the entity of the member with the earliest inception — and stamped that value on every period of every entity. SF-ORD-30201 (O1 30 seats 108,000.00, O2 10 seats 20,000.00, from 1 March 2026), posted with an invoice of 12,000.00 on O1 dated 15 March under POL-004 `ERP`: a TENANT version set `ENGINE` from 1 November, and at the contract's next computation after that day all 48 PERIOD rows read `ENGINE` and a BILLING intent of 12,000.00 was posted in FY2026-P03 (Dr ACCOUNTS_RECEIVABLE, Cr CONTRACT_LIABILITY). The rule now states the instant — the period's last instant in the entity's time zone, or the computation's instant while the period has not ended — the entity (the period's own) and the versions (those published by the computation's instant); what a version without an effective date means ([J], candidate AD-79 for the independent accountant: a first version answers for every earlier period, a later one from its publication); and that a parameter without a framework default has no value before its first version (POL-123 is derived from POL-004 for such a period). No option value, default or force changes. |
| 1.123 | 2026-10-01 | lane ENG-FX (item PINP-PERIOD-VALUE-1 — release blocker; the supervisor's ruling (A) of 2026-10-01 on the lane's stop; number assigned by the supervisor, register index 143) | **Applied (no approved answer-key figure changes; the golden parity figures stand as approved).** Finding (gate C of the lane, 2026-10-01): a period takes the value in force at its own end (05 RCP-15 rev 1.166), and a tenant's first real policy version supersedes the empty default that provisioning writes, so it had to take effect at its submission or later — after the history a tenant migrates. The golden parity scenario is that tenant: its preset was dated 2026, its legacy calendar is FY2023 and FY2024, every legacy period computed under the framework defaults, and nine parity cases moved ("Current Reclass to UAR" 58.8462 to 58.85). Rule 3, pin P, said that changes are effective from the first day of a future open period and did not say how a tenant states the policy its migrated history was kept under. It now says that a version published before the workspace's first legal entity may take effect on an earlier day; the parity scenario dates its preset at the first day of its legacy calendar and the nine cases return to their expected figures. No option value, default or force changes. |
| 1.124 | 2026-10-03 | lane SECFIX-PLT (item POLICY-OVERRIDE-WITHDRAW-1 — the one item placed behind the freeze of release 1.0; supervisor ruling R-126 (b) (4) and (c) and the supervisor's rulings of 2026-10-03 on the lane's line; number assigned by the supervisor, register index 308) | **Applied (no approved answer-key figure changes; the engine reads a value at level C or O as before, and the 41 engine-run keys that state one are untouched).** Finding (supervisor ruling R-124 (b) (8)): §0.5 gives levels C and O to 23 parameters and resolves O → C first, and the platform gave the engine no override — a contract- or POB-level override could be requested, approved and stored, and no computation read it. §0.5 gains rule 5: in release 1.0 no such override is offered and its creation is refused by name (04 T-CON-23 rev 1.322; PRD ERR-102); table 0.5-A states what decides each of the 23 parameters instead, the sentence the refusal answers with — a record of the contract for nine (POL-026, POL-040, POL-041, POL-070, POL-080, POL-233, POL-234, POL-244, POL-246), another level the parameter lists, read there by a computation, for eight (the registry for POL-014 and POL-163; the product or its obligation template for POL-030, POL-051, POL-053, POL-091, POL-095, POL-122), and the framework's default for six (POL-047, POL-049, POL-056, POL-057, POL-240, POL-243). POL-047's default states a basis and no rate: no discount rate can be given in release 1.0, and a contract whose financing needs an adjustment is not computed (`SFC_RATE_MISSING`, an `ERROR` finding). POL-240 lists level P, and the engine reads the parameter for a contract (stage 04 `vc`, `buildup`; stage 05 `original`), where the value of a product or a template, which bundle assembly gives per obligation, is not seen: found while the sentences were read against their readers and placed apart by the supervisor as register index 309 — the read is not changed here. Rule 2 names the two values the engine does meet at O and C, each stated by another record (POL-070, POL-210). §0.6 OVR is marked not offered; the SSP override of a POB is offered. No option value, default or force changes, and no POL row of section 1 is edited. |
| 1.125 | 2026-10-03 | lane SECFIX-CLO (item PRODUCT-POLICY-VALUE-NOT-READ-1 — the second item placed behind the freeze of release 1.0; supervisor ruling R-126 (c) and the supervisor's rulings of 2026-10-03 on the lane's list and words; docs first; number assigned by the supervisor, register index 309) | **Applied (no approved answer-key figure changes; no engine file changes; the four engine-run keys that state POL-240 or POL-029 on a product or a template are untouched).** Finding (lane SECFIX-PLT's, met while it read the sentences of rev 1.124 against their readers; measured and counted by this lane on 783f340ea): §0.5 gives level P to 23 parameters and resolves O → C → P for a POB, and bundle assembly gives a product's and a template's value to the engine for an obligation; the engine reads three of the 23 for a contract — POL-240 in stage 04 (`vc`, `buildup`) and stage 05 (`original`), POL-029 and POL-021 in stage 03 (`options`, `elections`) — and its resolver takes an obligation's row only for a read that names the obligation. Measured on the corpus key REC-USAGE-STAND-READY-FEE-SCHEDULED-TO-TERM-END, a usage obligation with 63,750.00 of reported fees: with `ESTIMATE_MEASUREMENT_PERIOD_TP` stated on its template the row stands in the bundle and every figure is as before; stated for the contract, ten figures move (transaction price 363,750.00 to 300,000.00). On POB-S2-SHIPPING-OWN-ON, `FALSE` stated on the templates moves nothing; stated for the contract, the freight of 50.00 leaves the product's revenue. The engine's reads over the 248 engine-run keys of the corpus, counted: POL-021 3,063 and POL-240 393, none with an obligation; no key reaches the read of POL-029. §0.5 rule 1 gains "Level P in release 1.0": a product and an obligation template state none of the three but the framework's default of POL-240 and POL-029, and any other value is refused by name where it would be stored, with what applies instead (`POLICY_PRODUCT_LEVEL_NOT_READ`; 04 T-REF-20 and T-REF-23 rev 1.323; PRD ERR-103). The rows of POL-021, POL-029 and POL-240 say so in their engine effect. The engine's read is not changed, and the `Levels` column keeps P for the three: when a reader of a later release passes the obligation, the door is lifted for its parameter. Four parameters that list P are read by no computation at any level (POL-015, POL-026, POL-142, POL-231) and are not refused: a stated limit of the release. No option value, default, level or force changes. |

This document is not an accounting opinion for any specific entity. It fixes the policy choices the engine exposes, the defaults it ships and the exact arithmetic it applies. A tenant that changes a default takes responsibility for that judgement under its own review controls (POL approval column).

---

## 0. How to use this document

### 0.1 What this document governs

| Section | Content | Consumers |
|---|---|---|
| 1 | Policy register: every accounting policy choice, practical expedient, election and judgement parameter the engine exposes (POL-NNN) | Engine, data model, Policies UI, answer-key authors |
| 2 | Algorithms with exact numeric checks: rounding (ALG-01), position and netting (ALG-02), posting templates (JET-NN), contract asset vs unbilled receivable (ALG-03), SSP basis for modifications (ALG-04), material rights (ALG-05), returns (ALG-06), cross-entity (ALG-07), FX (ALG-08), late events (ALG-09), estimate versions (ALG-10), time-elapsed conventions (ALG-11) | Engine (`erev_engine`), answer keys |
| 3 | SSP policy: method hierarchy, residual restrictions, range validation, out-of-range point | SSP studio, allocation stage |
| 4 | Codification currency register (D-26): every ASU amending Topics 606, 340-40, 605-35 and 805-20 checked, with engine effect; verification of U-01, U-02, U-04 | Accounting reviewers, engine |
| 5 | Policy-level treatment of the M-RA-05 topics and business-combination onboarding (M-RA-06) (PT-NN) | Engine, answer keys, importers |
| 6 | Cross-reference tables: M-RA-01 items, research 04 §13 IFRS switches, D-32 preset | Reviewers |
| 7 | Gaps closed | Supervisor |
| 8 | Open questions for supervisor | Supervisor |

`docs/accounting/ENGINE_SPEC.md` owns the calculation pipeline (stages, data flow, trace). Where it implements a choice registered here, it cites the POL id and must not add a new choice without a new POL id.

### 0.2 Evidence labels

| Label | Meaning |
|---|---|
| [F] | Fact, with a citation to the Codification, IFRS 15 or a named source |
| [J] | Judgement by this document's owner; the one-line rationale is given beside it |
| [A] | Assumption used only to make an example or check concrete |

Codification citations use the FASB paragraph format (for example 606-10-32-40). Paragraph text was checked against the FASB ASU PDFs listed in section 4 (downloaded copies under `.scratch/04-asc606-technical/asu/` where noted). Practice guidance (Deloitte Roadmap "DART", PwC Viewpoint, TRG and FASB staff Q&A) is labelled as such and never presented as Codification text.

### 0.3 Identifier scheme (stable; never renumber)

| Prefix | Object | Example |
|---|---|---|
| POL-NNN | Accounting policy, election, practical expedient or judgement parameter | POL-071 `ssp.outside_range_point` |
| ALG-NN | Precise algorithm | ALG-04 SSP basis for modifications |
| JET-NN | Journal-entry template per event type | JET-06 period-end netting reclass |
| CHK-NNN | Exact numeric check. Every CHK must be carried into `docs/accounting/answer-keys/` as a key whose id contains the CHK id, matched case-insensitively (D-76; `_coverage/answer-keys-fx-entity-books:OQ-AK-01`). A CHK with several rows (for example CHK-136) is covered by keys whose ids contain that CHK id | CHK-012 |
| ASU-NN | Codification currency register row | ASU-21 (ASU 2021-08) |
| PT-NN | Policy topic (M-RA-05, M-RA-06) | PT-04 concessions on billed amounts |
| OQ-NN | Open question for the supervisor | OQ-03 |

A retired id is marked `Retired` in place and never reused.

Citation rules (rev 1.1; B1-027, D-73):

1. **This document's ids cited elsewhere.** Other documents write `POL PT-NN` for a policy topic, because 04 uses `PT-` for partitioning classes, and `POLICIES:OQ-nn` for an open question. POL-NNN, ALG-NN, JET-NN and CHK-NNN need no prefix.
2. **Other documents' open questions cited here.** This document writes `<document>:<question id>` and keeps the other document's question id, for example `04:OQ-05`, `DEVIATIONS:OQ-D8`, `legacy-02:OQ2`, `research-06:Q8`. Document tokens: `PRD`, `03`, `04`, `05`, `DG`, `DS`, `GLOSSARY`, `DEVIATIONS`, `B1` (`docs/reviews/B1-consistency.md`), `legacy-01` to `legacy-07`, `research-01` to `research-07` and `research-99`; from rev 1.2 (D-76 citation form) also `ENGINE_SPEC`, `ENGINE_SPEC_B`, `SCREENS`, `SCREENS_B` and the answer-key coverage files `_coverage/answer-keys-topics`, `_coverage/answer-keys-industries` and `_coverage/answer-keys-fx-entity-books`. A bare `OQ-NN` in this document means section 8.
3. **Literals and codes.** Registry keys and option literals are defined in section 1 (D-13a); 04 enumerations that mirror a registry option (for example E-21, E-32, E-33) follow them. Every other enumeration literal cited here (for example E-01 `account_role`, `clearing_purpose`, E-03 event types, E-09 estimate kinds, E-31 posting kinds, E-47 SSP methods), and every problem slug and finding or exception code, is owned by `docs/04-DATA_MODEL.md` (§3, §15.2, §15.4) and is cited verbatim (D-73). A difference is a defect of this document.

### 0.4 Books, framework defaults and the legacy-parity preset

| Column in section 1 | Meaning |
|---|---|
| `606` | Default value for a book whose framework is `ASC606` in a new tenant |
| `IFRS` | Default value for a book whose framework is `IFRS15` |
| `Parity` | Value in the `LEGACY_PARITY` policy set (D-32). The preset is applied to the `ASC606` book of a tenant created by legacy migration or replay, and the golden suite (`docs/legacy/golden/golden-tests.json`, G3) runs under it |
| `FORCED` suffix | The framework fixes the value; the tenant cannot change it for that book |
| `n/a` | Legacy inputs never exercise the policy; the parity preset uses the `606` default |

The `LEGACY` book (D-24) holds pre-standard revenue for delta posting. It consumes no Topic 606 policy; its only policy inputs are POL-005 and POL-008 (section 1.1).

### 0.5 Levels, pinning and resolution

| Code | Level | Object that stores the value |
|---|---|---|
| T | Tenant | Tenant policy version |
| E | Legal entity | Entity policy version |
| B | Book | Book policy version (framework-specific) |
| P | Product | Revenue policy template or SKU (`docs/00-GOAL.md` §2 item 2) |
| C | Contract | Contract (or combination group) policy override |
| O | POB | Performance-obligation override |

Rules:

1. **Allowed levels.** Each POL lists the levels at which a value may be set. A value stored at a level not listed is a validation error (`POLICY_LEVEL_NOT_ALLOWED`). **Level P in release 1.0 (rev 1.125; item PRODUCT-POLICY-VALUE-NOT-READ-1, register index 309; supervisor ruling R-126 (c) and the supervisor's rulings of 2026-10-03 on the lane's list and words).** A value at level P reaches the engine for an obligation: a read made for a POB meets it, a read made for a contract does not. Three parameters that list P are read for a contract — POL-021, POL-029 and POL-240 — so a product's or a template's value of them was stored, approved with the template's version and used by no computation. A product and an obligation template therefore state no such value: of POL-240 and POL-029 the framework's default alone, which applies to every contract; of POL-021 none, because the legal entity's or the workspace's value applies where the framework does not fix it. Anything else is refused by name where it would be stored, with what applies instead (`POLICY_PRODUCT_LEVEL_NOT_READ`; 04 T-REF-20 and T-REF-23, rev 1.323; PRD ERR-103). The `Levels` column keeps P for the three as the framework's design. Four parameters that list P are read by no computation at any level — POL-015, POL-026, POL-142 and POL-231: they are not refused, which is a stated limit of the release.
2. **Resolution.** The engine resolves a policy for a POB by taking the first value found in the order O → C → P → B → E → T → framework default (section 0.4), restricted to the allowed levels. In release 1.0 no override stands at O or C (rule 5): the values the engine meets at those two levels are the ones another record states — the SSP versions an obligation was priced from, at O (POL-070), and the onboarding method of an import batch, at C (POL-210).
3. **Pinning (`Pin` column).**
   - `K` (contract-pinned): the value resolved at the contract's inception is pinned on the computed contract version and used for the life of the contract. A later policy version applies only to contracts whose inception date is on or after its effective date. Applying it to existing contracts requires a change record with `apply_to_existing = true`, CFG approval, and a re-run whose differences post under ALG-09 in the first open period (research 07 §5.7 "prospective by default"). A combination group formed from contracts that were computed before takes, for its first version, the values pinned for the member with the earliest inception date, then external id; a parameter those values do not hold is resolved at that computation (rev 1.77; item PIN-K-COMBINATION-1, supervisor ruling R-112 (i); [J], candidate AD-58 for the independent accountant).
   - `P` (period-scoped): the value in force for the accounting period is used for every contract; changes are effective from the first day of a future open period. Before a workspace has its first legal entity nothing has been computed, and a version published then may take effect on an earlier day: a tenant that migrates states the policy its history was kept under by dating its first version at the first day of that history, and every period of the history then takes it (rev 1.123; item PINP-PERIOD-VALUE-1; supervisor ruling of 2026-10-01; PRD ERR-75; [J], with candidate AD-79 for the independent accountant). **The value of a period (rev 1.122; item PINP-PERIOD-VALUE-1; supervisor ruling of 2026-10-01).** A period of a legal entity takes the value in force for that entity at the period's last instant in the entity's time zone — while the period has not ended, at the instant of the computation — among the versions published by the computation's instant. A changed value therefore answers from the first period it is effective in and never for a period that ended before it; the version it replaced keeps answering for the earlier periods, and each entity's periods take that entity's own value. A version without an effective date: the first version of its scope answers for every earlier period — it states the policy the tenant has applied — and a later one answers from the instant its predecessor was closed at, its publication ([J], candidate AD-79 for the independent accountant). A parameter without a framework default has no value in a period before its first version; POL-123 is then derived from POL-004 for that period.
4. **Consistency.** Policies that the Codification requires to be applied consistently to similar contracts (for example POL-021, POL-150) allow only T, E or P levels.
5. **Levels C and O in release 1.0 (rev 1.124; item POLICY-OVERRIDE-WITHDRAW-1, register index 308; supervisor ruling R-126 (b) (4) and (c) and the supervisor's rulings of 2026-10-03 on the lane's line).** No contract-level or POB-level policy override is offered. The engine's bundle is given none (05 RCP-15), so an override would be approved and the books would not use it; `POST /policy-overrides` therefore refuses every creation by name (04 T-CON-23 "Not offered in release 1.0"; PRD ERR-102), and no person sets a value at level C or O. The `Levels` column of section 1 keeps naming C and O as the framework's design. Table 0.5-A states, for each of the 23 parameters that list one of them, what decides the parameter in this release — the sentence the refusal answers with, each read against the code that takes the parameter. Three kinds: a record of the contract decides (an estimate version, a reviewed judgement record, the terms of an option, a modification's SSP basis, an SSP override, the scope flag of a line, the consideration payable recorded on the contract); the value is set at a level the parameter lists besides C and O and a computation reads it there (the policy registry for the workspace or a legal entity, the product or its obligation template); or neither holds, and the framework's default applies to every contract — POL-049, POL-056, POL-057 and POL-243, which list level C alone; POL-047, whose default states a basis and no rate; and POL-240, which lists level P as well, where the engine does not read it: it takes the parameter for a contract, and a product's or a template's value is given to it for an obligation (register index 309).

**Table 0.5-A. What decides a parameter that lists level C or O, in release 1.0**

| Key | POL | What decides it in release 1.0 |
|---|---|---|
| `step1.term_with_termination_rights` | POL-014 | It is set in the policy registry for the workspace. |
| `material_right.ssp_method` | POL-026 | The option terms of the material right decide it. |
| `pob.principal_or_agent` | POL-030 | It is set on the product or on its obligation template. |
| `vc.estimation_method` | POL-040 | The method of the element's estimate version decides it. |
| `vc.constraint` | POL-041 | The framework fixes this value, and the constrained amount of the element's estimate version is what it applies. |
| `sfc.discount_rate_basis` | POL-047 | The framework's default basis applies to every contract in this release, and no discount rate can be given: a contract whose financing needs an adjustment is not computed (SFC_RATE_MISSING). |
| `cpc.incentive_asset_release_basis` | POL-049 | The framework's default applies to every contract in this release. |
| `returns.model` | POL-051 | It is set on the product or on its obligation template. |
| `returns.returned_units_scope` | POL-053 | It is set on the product or on its obligation template. |
| `royalty.unreported_sales` | POL-056 | The framework's default applies to every contract in this release. |
| `royalty.minimum_guarantee` | POL-057 | The framework's default applies to every contract in this release. |
| `ssp.version_basis` | POL-070 | It is set in the policy registry for the workspace, and an SSP override names the version that prices an obligation. |
| `mod.ssp_basis` | POL-080 | It is set in the policy registry for the workspace, and the SSP basis of a modification decides it for an obligation. |
| `recognition.measure_of_progress` | POL-091 | It is set on the product or on its obligation template. |
| `recognition.control_trigger` | POL-095 | It is set on the product or on its obligation template. |
| `balance.right_to_consideration` | POL-122 | It is set on the product or on its obligation template. |
| `fx.cl_historical_layering` | POL-163 | It is set in the policy registry for a legal entity. |
| `scope.repurchase_classification` | POL-233 | The framework fixes this value, and the reviewed judgement record of the repurchase terms decides the outcome. |
| `scope.collaboration_808` | POL-234 | The scope flag of each contract line decides it. |
| `usage.tier_minimum_method` | POL-240 | The framework's default applies to every contract in this release. |
| `concession.allocation_basis` | POL-243 | The framework's default applies to every contract in this release. |
| `claims.recognition_gate` | POL-244 | The framework fixes this value, and a claim enters the transaction price with its estimate version and the reviewed judgement record that attests it enforceable. |
| `cpc.share_based_timing` | POL-246 | The framework fixes this value, and it applies to the consideration payable recorded on the contract as share-based. |

### 0.6 Approval codes

| Code | Control | Evidence |
|---|---|---|
| CFG | Configuration change under change control: versioned, effective-dated, maker-checker with approver different from author, impact simulation attached (research 07 §5.7) | Config change register with field-level diff |
| OVR | Contract- or POB-level override: preparer rationale, reviewer approval before the contract version is committed (research 07 §5.2, §5.3). Not offered in release 1.0 (§0.5 rule 5): the code stays the parameter's class in the registry, and the SSP override of a POB (POL-070; REQ-SSP-006), which has its own request and approval, is offered | Override register |
| EST | Estimate version (D-20): preparer, approver, rationale, evidence | Estimate version record |
| JDG | Judgement record that must be approved before period close (research 04 §14.4 V11) | Judgement record |
| FIX | Not configurable. The row documents a fixed behaviour so that engine and reviewers can cite it | None |

### 0.7 Answer-key family codes

Every answer key in `docs/accounting/answer-keys/` declares `families: [...]` from this list. The `AK` column of section 1 uses the same codes.

| Code | Family | Code | Family |
|---|---|---|---|
| RND | Rounding and apportionment | REC | Recognition patterns (ratable, units, milestones, cost-to-cost, right to invoice, point in time, bill-and-hold, consignment, repurchase) |
| SSP | SSP resolution, ranges, residual | ROY | Sales- or usage-based royalties |
| ALC | Allocation (discount exception, targeted VC, TP changes) | MOD | Contract modifications |
| STP1 | Contract existence, collectibility, term, combination | POS | Contract position, netting, CA vs UR, reclass |
| POB | POB identification (immaterial promises, shipping, warranties, principal vs agent, licences) | JE | Posting templates (gross, billing modes) |
| VC | Variable consideration, constraint, estimate versions | DLT | Delta posting and the LEGACY book |
| RET | Returns, refund liabilities, return assets | FX | Foreign currency |
| MR | Customer options and material rights | ENT | Multi-entity and intercompany |
| BRK | Breakage | COST | Contract costs (ASC 340-40) |
| SFC | Significant financing component | LOSS | Loss provisions (ASC 605-35, IAS 37) |
| NCC | Noncash consideration | LATE | Late and backdated events |
| CPC | Consideration payable to a customer | DISC | Disclosures, RPO, rollforwards |
| TAX | Sales and similar taxes | ONB | Onboarding, migration, business combinations |
| IFRS | Book-difference behaviour | PAR | Legacy parity (golden suite) |

### 0.8 Account-role conventions (D-14, D-14a)

The templates in section 2 use only the 33 `account_role` values of D-14a (04 E-01). `RETAINED_EARNINGS` and `FINANCING_OBLIGATION` are reserved: no 1.0 template posts them (POL-218, POL-233). The roles with semantics specific to this document are fixed as follows; the other roles mean what their names say.

| Role | Semantics in this document | Templates |
|---|---|---|
| `CONTRACT_LIABILITY` | **Gross control role** per contract, entity and book. Every billing or unconditional-due credit and every revenue relief posts here. Its balance before the period-end reclass equals the D-12 `net_position` (ALG-02) | JET-01b to JET-05, JET-06, JET-08, JET-10, JET-11, JET-13, JET-15, JET-17 |
| `CONTRACT_ASSET`, `UNBILLED_RECEIVABLE` | **Presentation roles**. Presentation balances derived at period end and populated only by the auto-reversing netting reclass (D-13; D-75 ruling on OQ-05). They never receive flow entries | JET-06 |
| `ACCOUNTS_RECEIVABLE` | Posted by the engine only when `billing.posting` = `ENGINE` (POL-004), and remeasured by the engine only in that mode | JET-03, JET-10a′ |
| `BILLING_CLEARING` | Counter-entry role for amounts whose other side is owned by another subledger. Every engine line with this role carries a `clearing_purpose` from table 0.8-A, and no other line carries one. Mapping rules may route by purpose, product or revenue category (D-14a) | JET-01b, JET-02, JET-07d, JET-14, JET-17 |
| `COST_OF_REVENUE` | Cost-of-revenue counter-entry: return-asset recognition and remeasurement, and fulfilment-cost release under an election, which in 1.0 is the warranty-claim release under POL-022 `ENGINE` (D-14a). Zero-margin uninstalled materials post no `COST_OF_REVENUE` line: the ERP posts their cost and the engine posts only revenue equal to that cost (D-76 ruling on `POLICIES:OQ-15`; POL-091, JET-02) | JET-07c, JET-16 |
| `CONTRACT_COST_CLEARING` | Credit side of capitalising costs to obtain or fulfil a contract, and debit side of a commission clawback; the ERP has already expensed, accrued or recovered the cost (D-14a; D-76 ruling on `ENGINE_SPEC_B:OQ-B-11`) | JET-09a, JET-09a′, JET-09f |
| `RECEIVABLE_CONTRA` | Implicit price concessions on invoiced consideration when `billing.posting` = `ENGINE` (D-14a). Credit losses never post here (POL-125) | JET-04c |
| `PRE_STANDARD_REVENUE` | Revenue recorded by the ERP under the pre-standard design; used only by the delta template JET-15 | JET-15 |
| `ROUNDING` | FX translation residue of summarised batches only (D-16). Allocation and schedules never post to it (ALG-01 guarantees exactness) | none (batch residue) |

Table 0.8-A: `clearing_purpose` on `BILLING_CLEARING` lines (D-14a; literals owned by 04)

| `clearing_purpose` | Subledger that owns the other side | Templates that emit it |
|---|---|---|
| `BILLING` | Billing system (invoices and credit memos) | None in 1.0. Under POL-004 `ERP` the billing system posts invoices itself; under `ENGINE` JET-03 posts `ACCOUNTS_RECEIVABLE`. Mapping rules may still carry the value |
| `UNAPPLIED_CASH` | Cash application | JET-01b: receipt while the contract is `NOT_A_CONTRACT`, and refund of the deposit on termination |
| `AP_SUPPLIER` | Accounts payable | JET-02: agent's payable to the supplier (POL-030) |
| `INVENTORY` | Inventory | JET-07d: return asset derecognised when returned goods come back |
| `EQUITY` | Stock compensation and equity | JET-14: share-based consideration payable to a customer (PT-10) |
| `INVESTMENTS` | Investments | JET-17: noncash consideration received |

Research 04 journal tables are illustrative. Engine journal lines follow the JET templates, so a research 04 example may show the same closing balances with different intermediate lines (for example research 04 §5.2-B books Dr 1105 / Cr Revenue directly; the engine books Dr CL / Cr Revenue and presents the unbilled receivable through JET-06). Answer keys assert JET-conformant lines and labelled balances (D-12).

### 0.9 Amount and sign conventions

- All amounts in tables are in the transaction currency unless labelled functional (`fn`).
- Journal lines carry a side (Dr or Cr) and a non-negative amount. A negative economic effect is posted by swapping sides, never as a negative line.
- `net_position` follows D-12: positive means contract liability.
- `round()` means ROUND_HALF_UP to the currency's ISO 4217 minor unit, symmetric for negatives (−0.005 USD → −0.01) (D-11).

---

## 1. Policy register

Column key: `Key` is the machine key stored in policy versions. `Levels` and `Pin` follow section 0.5; `Appr` follows section 0.6; `AK` lists answer-key families (section 0.7). Options are enum literals exactly as the engine stores them.

### 1.1 Platform, books, posting and rounding

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-001 | `rounding.posting_mode` | How are posted amounts quantised? | `HALF_UP` | `HALF_UP` FORCED | `HALF_UP` FORCED | `HALF_UP` FORCED | T | P | FIX | D-11. No Codification requirement [F] | Schedules, journal lines and balances quantised by ALG-01 `round()` at the ISO 4217 exponent. Legacy used binary-float round-half-even in JE reports; differences are corrected values under D-17, approved once as deviation class DEV-002 (D-17a) | RND, PAR |
| POL-002 | `rounding.apportionment` | How is an amount split across POBs, entities, periods or layers? | `LARGEST_REMAINDER` | FORCED | FORCED | FORCED | T | P | FIX | D-11 | ALG-01 §2.1.2 | RND, ALC |
| POL-003 | `rounding.schedule` | How are period amounts derived from progress? | `CUMULATIVE` | FORCED | FORCED | FORCED | T | P | FIX | D-11; research 06 §7.3 | ALG-01 §2.1.3. Research 04 keys that plug the last period are re-baselined (CHK-004) | RND, REC |
| POL-004 | `billing.posting` | Who posts invoices and credit memos (Dr AR / Cr contract liability)? | `ERP`, `ENGINE` | `ERP` | `ERP` | `ERP` | T | P | CFG | D-13, D-13a; 606-10-45-2, 45-4 [F] | `ERP`: invoices and credit memos are ingested for position, reconciliation and FX, never posted. `ENGINE`: JET-03 posts them and the per-contract AR tie-out V8 is enabled | JE, POS |
| POL-005 | `je.posting_mode` | Does the GL receive full entries or only the difference from pre-standard revenue already booked by the ERP? | `GROSS`, `DELTA` | `GROSS` | `GROSS` | `GROSS` (the adjustment-format report is always generated, D-33) | T, E | P | CFG | D-34; research 04 §11; legacy 06 §3.7 | `GROSS`: every JET template except JET-15 posts. `DELTA`: JET-15 lines are added and the `LEGACY` book is required (POL-007) | JE, DLT, PAR |
| POL-006 | `je.summarization` | At what grain are journal lines summarised for GL export? | `ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS`, `LEGACY_CONTRACT_POB`, `CONTRACT_ACCOUNT_DIMENSIONS` | `ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS` | same as 606 | `LEGACY_CONTRACT_POB` | T | P | CFG | D-16; REQ-JE-010; 04 E-33 and 04:OQ-05 (B1-020); research 07 §5.5; legacy 06 P-JE-05 | Export grouping only; subledger detail lines are unchanged, and every summarised line links to its contributing subledger lines (REQ-JE-010). `CONTRACT_ACCOUNT_DIMENSIONS` groups lines by entity, book, currency, period, contract (combination group), account and dimensions: the contract-level grain of REQ-JE-010. `LEGACY_CONTRACT_POB` groups balance-sheet roles by contract and revenue by POB (legacy L2647-2651). Every option still balances per entity, book, currency and period (D-16) | JE, PAR |
| POL-007 | `books.enabled` | Which books run for an entity, and which is primary? | set ⊆ {`ASC606`, `IFRS15`, `LEGACY`}; `primary` ∈ set | {`ASC606`}, primary `ASC606` | {`IFRS15`}, primary `IFRS15` (parallel `ASC606` optional) | {`ASC606`, `LEGACY`}, primary `ASC606` | T, E | P | CFG | D-24 | Compute per book with memoised shared stages (research 06 §11.4). `LEGACY` is mandatory when POL-005 = `DELTA` | IFRS, DLT |
| POL-008 | `legacy_book.source` | Where does pre-standard revenue for the `LEGACY` book come from? | `PRE_STANDARD_EVENTS`, `ERP_REVENUE_FEED` | `PRE_STANDARD_EVENTS` | same as 606 | `PRE_STANDARD_EVENTS` | T, E | P | CFG | research 06 §11.3; legacy 06 §3.7; legacy-06:OQ-05 | `PRE_STANDARD_EVENTS`: per-event amounts (legacy template column F). `ERP_REVENUE_FEED`: ingested ERP revenue lines by POB. Modification and estimate events carry a pre-standard amount of 0 unless one is supplied (fixes legacy D-10; GT-23) | DLT, PAR |

### 1.2 Step 1: contract existence, term and combination

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-011 | `step1.collectibility_threshold` | Which collectibility threshold applies, and does the engine compute it? | `US_PROBABLE`, `IFRS_PROBABLE` | `US_PROBABLE` FORCED | `IFRS_PROBABLE` FORCED | n/a | B | K | JDG | 606-10-25-1(e); Master Glossary "probable" (second definition): "The future event or events are likely to occur" [F, ASU 2014-09 §A]. The Boards acknowledged that "probable" has different meanings in US GAAP and IFRS [F, ASU 2014-09 summary]. No numeric threshold exists in the Codification (U-01, section 4.3) | Stores a boolean conclusion per book with checklist, evidence and reviewer. The engine never derives it from a percentage. A book whose conclusion is false keeps the contract `NOT_A_CONTRACT` in that book | STP1, IFRS |
| POL-012 | `step1.event_c_enabled` | May nonrefundable consideration be recognised when the entity has stopped transferring and has no obligation to transfer more (25-7(c))? | `ENABLED`, `DISABLED` | `ENABLED` FORCED | `DISABLED` FORCED | n/a | B | K | FIX | 606-10-25-7(c), added by ASU 2016-12 [F]; IFRS 15.15 lists only events (a) and (b) [F, research 04 §13 #2] | Deposit-to-revenue triggers are evaluated per book (JET-01b) | STP1, IFRS |
| POL-013 | `step1.criteria_met_transition` | When a contract moves from `NOT_A_CONTRACT` to `ACTIVE`, how is performance already rendered treated? | `CATCH_UP_AT_TRANSITION`, `PROSPECTIVE_FROM_TRANSITION` | `CATCH_UP_AT_TRANSITION` | same as 606 | n/a | T | K | CFG | 606-10-25-6, 25-8 [F]. Practice interpretation (research 04 §1.1-B Case C). [J] The five-step model applied from inception measures the revenue the entity is entitled to for goods already transferred | Full five-step run from inception; the deposit liability is reclassified to `CONTRACT_LIABILITY` (JET-01b) and the resulting revenue posts in the transition period with reason `STEP1_MET` | STP1 |
| POL-014 | `step1.term_with_termination_rights` | What is the accounting term when the customer can terminate for convenience? | `TO_EARLIEST_TERMINATION_WITHOUT_SUBSTANTIVE_PENALTY`, `STATED_TERM` | `TO_EARLIEST_TERMINATION_WITHOUT_SUBSTANTIVE_PENALTY` | same as 606 | `STATED_TERM` | T, C | K | OVR (contract value `STATED_TERM` needs rationale) | 606-10-25-3, 25-4 [F]; TRG Agenda Paper 48 [practice] | The enforceable term ends at the earliest date the customer can terminate without a substantive penalty; later periods are customer options tested under POL-026. Allocation and RPO are limited to the enforceable term. `termination_penalty_substantive` is a preparer-entered boolean per contract; the engine never computes it | STP1, MR, DISC |
| POL-015 | `step1.portfolio_approach` | May the guidance be applied to a portfolio of similar contracts or POBs? | `DISABLED`, `ENABLED` | `DISABLED` | `DISABLED` | `DISABLED` | T, P | K | CFG and JDG ("not materially different" assessment) | 606-10-10-4 [F]; IFRS 15.4 | PT-06 | ONB, VC, RET, BRK |
| POL-016 | `combination.detection_window_days` | Within how many days must contracts with the same customer group be signed to be suggested for combination? | integer 0 to 365 | 30 | 30 | 0 (no detection) | T | P | CFG | 606-10-25-9 ("at or near the same time") [F]. [J] 30 days surfaces package deals without flooding the review queue | Suggestion only, raised as finding `COMBINATION_SUGGESTED` (04 table 15.4-C; D-76 ruling on PRD:§9 Q10). A combination is committed by OVR approval and re-runs allocation from the group's inception | STP1 |

### 1.3 Step 2: performance obligations

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-020 | `pob.immaterial_promise_relief` | May promises that are immaterial in the context of the contract be left unassessed? | `ASSESS_ALL`, `APPLY_RELIEF` (parameter `immaterial_threshold_pct`, default 0.01, maximum 0.05) | `ASSESS_ALL` | `ASSESS_ALL` FORCED | `ASSESS_ALL` | T, E | K | CFG | 606-10-25-16A, 25-16B (never for material rights) [F]; no IFRS relief [F, research 04 §13 #3]. [J] Default off because the relief is optional and hides POBs from disclosure | `APPLY_RELIEF`: a line whose SSP share is below the threshold joins the POB it accompanies, and its cost is accrued when revenue precedes transfer. Material-right lines are never eligible | POB, IFRS |
| POL-021 | `pob.shipping_as_fulfilment` | Are shipping and handling activities after control transfers treated as fulfilment costs? | `TRUE`, `FALSE` | `TRUE` | `FALSE` FORCED | `FALSE` | T, E, P | K | CFG | 606-10-25-18A, 25-18B [F]; no IFRS election [F, research 04 §13 #4]. [J] Default on because it is the common US election and avoids an immaterial POB | `TRUE`: the freight charge stays in the product POB's price. The carrier cost, including its accrual when revenue precedes the shipping activity (25-18B), is posted by the ERP; no JET template posts it (OQ-15). `FALSE`: a shipping SKU is its own POB. Rev 1.125 (register index 309; release 1.0): the engine reads the parameter for a contract, so a value at level P is read by no computation; a product and an obligation template state none, and the legal entity's or the workspace's value applies (§0.5 rule 1) | POB, IFRS |
| POL-022 | `pob.assurance_warranty_accrual` | Does the engine post the Subtopic 460-10 cost accrual for assurance-type warranties? | `ENGINE`, `EXTERNAL` | `ENGINE` | `ENGINE` | `EXTERNAL` | T, E | P | CFG | 606-10-55-30 to 55-35 [F]; IFRS 15.B28-B33 and IAS 37 | `ENGINE`: on control transfer, Dr `WARRANTY_EXPENSE` / Cr `WARRANTY_PROVISION` at the product's `assurance_cost_per_unit` × units (04 T-REF-20; D-76 ruling on `ENGINE_SPEC:OQ-A-06`); `COST_INCURRED` events with payload `purpose` `WARRANTY_CLAIM` consume the provision (JET-16; OQ-13). `EXTERNAL`: nothing posted. Service-type warranties are POBs in both cases | POB |
| POL-024 | `licence.nature_model` | Which licence-nature assessment applies? | `FUNCTIONAL_SYMBOLIC`, `ACTIVITIES_SIGNIFICANTLY_AFFECT_IP` | `FUNCTIONAL_SYMBOLIC` FORCED | `ACTIVITIES_SIGNIFICANTLY_AFFECT_IP` FORCED | n/a | B | K | JDG | 606-10-55-58 to 55-63 [F]; IFRS 15.B56-B62 [F, research 04 §13 #7] | Questionnaire per book sets `RIGHT_TO_ACCESS` (over time) or `RIGHT_TO_USE` (point in time) per book | POB, IFRS |
| POL-025 | `licence.renewal_start` | When may revenue for a licence renewal begin? | `RENEWAL_PERIOD_START`, `LATER_OF_AGREEMENT_AND_AVAILABILITY` | `RENEWAL_PERIOD_START` FORCED | `LATER_OF_AGREEMENT_AND_AVAILABILITY` | n/a | B | K | CFG | 606-10-55-58C [F]; IFRS 15.B61 does not address renewals [F, research 04 §13 #8]. [J] IFRS default follows B61's only condition (the customer can use and benefit from the licence) | Recognition of a renewal POB is blocked before the resolved date | REC, IFRS |
| POL-026 | `material_right.ssp_method` | How is the SSP of an option that provides a material right estimated? | `DISCOUNT_X_LIKELIHOOD`, `RENEWAL_ALTERNATIVE`, `ENTERED_AMOUNT` | `DISCOUNT_X_LIKELIHOOD` | `DISCOUNT_X_LIKELIHOOD` | `ENTERED_AMOUNT` (legacy L = 1, d = 0, r = 0, SSP = quantity in dollars; D-21, legacy 01 PAR-04) | P, C, O | K | EST | D-21a; 606-10-55-41 to 55-45 [F]; IFRS 15.B39-B43 | ALG-05 §2.6.1. SSP of an option = expected purchase amount × incremental discount (discount on exercise less the discount available without exercise) × likelihood of exercise (606-10-55-44), or the renewal practical alternative (55-45) (D-21a). The engine flags an option whose incremental discount exceeds the discount typically given to that class of customer (55-42); the preparer confirms (JDG). The SSP enters the allocation weights | MR, SSP |
| POL-028 | `material_right.exercise` | How is the exercise of a material right accounted for? | `CONTINUATION`, `MODIFICATION` | `CONTINUATION` | `CONTINUATION` | `MODIFICATION` | T | K | CFG | D-21, D-21a; 606-10-55-42 [F]; DART 11.7, citing TRG Implementation Q&A 15: continuation "generally preferable", modification "acceptable" [practice] | ALG-05 | MR, MOD, PAR |
| POL-029 | `upfront_fee.recognition_period` | Over what period is a nonrefundable upfront fee recognised when renewal options give the customer a material right? | `CONTRACT_TERM`, `EXPECTED_BENEFIT_PERIOD` | `EXPECTED_BENEFIT_PERIOD` | same as 606 | n/a | P | K | CFG and EST (expected life) | 606-10-55-50 to 55-53 [F]; practice (research 04 §5.8) | Without a material right the fee joins the transaction price and follows the POB pattern over the contract term under either option. Rev 1.125 (register index 309; release 1.0): the engine reads the parameter for a contract, so a value at level P — the one level the parameter lists — is read by no computation; every contract takes `EXPECTED_BENEFIT_PERIOD`, and a product and an obligation template state that value or none (§0.5 rule 1) | MR, REC |
| POL-030 | `pob.principal_or_agent` | Is the entity principal or agent for each specified good or service? | `PRINCIPAL`, `AGENT` | per assessment | per assessment | `PRINCIPAL` | P, O | K | JDG | 606-10-55-36 to 55-40 [F]; IFRS 15.B34-B38 | `AGENT`: revenue is the consideration retained; the remainder of the billing posts to `BILLING_CLEARING` with `clearing_purpose` `AP_SUPPLIER` (payable to the supplier, owned by AP; JET-02) | POB |

POL-023 and POL-027 are `Retired` (merged into POL-022 and POL-026 during drafting).

### 1.4 Step 3: transaction price

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-040 | `vc.estimation_method` | Which method estimates each VC element? | `EXPECTED_VALUE`, `MOST_LIKELY_AMOUNT`, `ENTERED_AMOUNT` | by VC type (table 1.4-A) | same as 606 | `ENTERED_AMOUNT` | C (VC element) | K (locked on the element's first estimate version) | EST | 606-10-32-8, 32-9 [F]; IFRS 15.53-54 | A method change after the first version is an error correction, never a new estimate version | VC |
| POL-041 | `vc.constraint` | How is the constraint applied? | `PREPARER_CONSTRAINED_AMOUNT`, `NOT_APPLIED` | `PREPARER_CONSTRAINED_AMOUNT` FORCED | `PREPARER_CONSTRAINED_AMOUNT` FORCED | `NOT_APPLIED` (entered amounts are final) | C | P | EST | 606-10-32-11 to 32-13 [F]; IFRS 15.56-58 ("highly probable"), treated as converged [F, research 04 §3.2] | The engine validates that the constrained amount lies between the most conservative outcome and the unconstrained estimate, inclusive (V6), mirrored for price-reducing VC. No numeric probability threshold is applied (U-01). The excluded amount feeds the 50-15 narrative | VC, DISC |
| POL-042 | `vc.reassessment_gate` | Must every open VC element have an estimate version for each period end? | `REQUIRE_VERSION_OR_ATTESTATION`, `NOT_ENFORCED` | `REQUIRE_VERSION_OR_ATTESTATION` | same as 606 | `NOT_ENFORCED` | T | P | CFG | 606-10-32-14 [F]; IFRS 15.59 | The close gate blocks the period lock when an open element lacks a version effective at period end or an approved "no change" attestation version | VC, LATE |
| POL-043 | `vc.estimate_import_semantics` | Do imported VC rows carry the full estimate or a change? | `FULL_ESTIMATE`, `DELTA` | `FULL_ESTIMATE` | `FULL_ESTIMATE` | `DELTA` (legacy POB-specific VC `Mod Billing`) | T (per import template) | P | CFG | D-20; legacy 05 §3.4 | The engine always stores full estimate versions (D-20). A `DELTA` row creates version v(n) = v(n−1) + delta; the trace keeps the delta | VC, PAR |
| POL-044 | `vc.targeted_allocation_tolerance` | When VC is allocated entirely to some POBs (32-40), how far may the result depart from relative SSP before review is required? | decimal 0 to 1 | 0.20 | 0.20 | `NOT_ENFORCED` | T | K | OVR above tolerance | 606-10-32-39 to 32-41, 32-44 [F]. [J] 20% matches the SSP-range yardstick (section 3.3) so reviewers use one threshold | For each POB p: r_p = allocation_p ÷ SSP_p and r_c = TP ÷ ΣSSP. If \|r_p − r_c\| > tolerance × r_c, OVR approval is required: the engine raises `VC_TARGET_TOLERANCE_EXCEEDED` (`ERROR`), and a reviewed E-56 `OTHER` judgement with outcome `pol_044_override` clears it (D-76 ruling on `ENGINE_SPEC:OQ-A-12`). The 32-40(a) and (b) attestations are always required outside parity | ALC, VC |
| POL-045 | `tp.sales_tax_exclusion` | Are taxes collected from customers excluded from the transaction price? | `EXCLUDE_ALL_IN_SCOPE`, `ASSESS_EACH_TAX` | `EXCLUDE_ALL_IN_SCOPE` | `ASSESS_EACH_TAX` FORCED | `EXCLUDE_ALL_IN_SCOPE` | E | P | CFG | 606-10-32-2, 32-2A [F]; IFRS 15.47, no election [F, research 04 §13 #5] | Excluded tax lines post to `SALES_TAX_PAYABLE` in `ENGINE` billing mode and are ignored in `ERP` mode; they never enter allocation. IFRS: each tax type carries `principal_or_agent` (default `AGENT`, excluded). In 1.0 the IFRS15 book treats every tax as collected on behalf of the authority and excludes it; a per-tax-type registry parameter is `later` (D-76 ruling on `ENGINE_SPEC:OQ-A-14`) | TAX, IFRS |
| POL-046 | `sfc.one_year_expedient` | Is the financing adjustment skipped when the gap between transfer and payment is one year or less at inception? | `APPLY`, `DO_NOT_APPLY` | `APPLY` | `APPLY` | `APPLY` | T, E | K | CFG | 606-10-32-15 to 32-18; use disclosed under 606-10-50-22 [F]; IFRS 15.63 | Gap per POB = \|weighted-average payment date − transfer date\| (weights = payment amounts; for over-time POBs the transfer date is the midpoint of the schedule). If gap ≤ 12 months and `APPLY`: no adjustment. Otherwise an SFC review flag (JDG) is raised unless a 32-17 exception is attested | SFC, DISC |
| POL-047 | `sfc.discount_rate_basis` | Which rate discounts a significant financing component, and how does it compound? | Value `{basis, annual_rate, compounding}`: `basis` ∈ {`CUSTOMER_CREDIT_RATE`, `ENTITY_BORROWING_RATE`}; `annual_rate` decimal; `compounding` ∈ {`MONTHLY`, `ANNUAL`} (rev 1.2; D-76) | deferred payment `CUSTOMER_CREDIT_RATE`; advance payment `ENTITY_BORROWING_RATE`; `compounding` `MONTHLY` | same as 606 | n/a | C | K (rate and compounding locked at inception) | EST | 606-10-32-19, 32-20 [F]; FASB Examples 28, 29; D-76 ruling on the significant financing component rate (`ENGINE_SPEC:OQ-A-16`, `_coverage/answer-keys-fx-entity-books:OQ-AK-05`, `_coverage/answer-keys-topics:OQ-AKT-13`) | Effective-interest schedule under Subtopic 835-30, posted monthly by JET-11 through ALG-01 §2.1.3 over the exact cumulative interest. Each payment is discounted (deferred payment) or accreted (advance payment) over n = the number of calendar month ends after the earlier and up to the later of the payment date and the transfer date (rev 1.3; ADJUDICATION.md R-SFC-02). `MONTHLY`: the balance compounds each month at annual_rate ÷ 12. `ANNUAL`: discounting over ⌊n ÷ 12⌋ whole years; interest of each contract year = annual_rate × the opening balance of that year, spread evenly over its months (ENGINE_SPEC S04-R-11, S04-R-12). No interest accretes while expected returns exclude the whole consideration (ENGINE_SPEC S04-R-12a). CHK-136 has one row per option | SFC |
| POL-048 | `noncash.measurement_date` | At what date is noncash consideration measured? | `CONTRACT_INCEPTION`, `RECEIPT_DATE`, `SATISFACTION_DATE` | `CONTRACT_INCEPTION` FORCED | `CONTRACT_INCEPTION` | n/a | B | K | CFG (IFRS book only) | 606-10-32-21 as amended by ASU 2016-12 [F]; IFRS 15.66-69 do not specify a date [F, research 04 §13 #6]. [J] IFRS default aligns the books | Changes in fair value due to the form of consideration are excluded from the transaction price (32-23); other variability follows POL-040 and POL-041. Share-based noncash consideration: section 4 (ASU 2025-07) and PT-10 | NCC, IFRS |
| POL-049 | `cpc.incentive_asset_release_basis` | How is an upfront payment to a customer that precedes revenue released against revenue? | `EXPECTED_PURCHASES`, `COMMITTED_PURCHASES` | `EXPECTED_PURCHASES` | same as 606 | n/a | C | K | EST | 606-10-32-25 to 32-27 [F]; FASB Example 32; practice presentation of the asset (research 04 §3.6) | Release rate = incentive ÷ expected (or committed) purchases, applied to each invoice. A change in expected purchases changes the rate prospectively | CPC |
| POL-051 | `returns.model` | Is revenue reduced for expected returns at transfer? | `EXPECTED_RETURNS`, `ACTUAL_RETURNS_ONLY` | `EXPECTED_RETURNS` | `EXPECTED_RETURNS` | `ACTUAL_RETURNS_ONLY` | P, C, O | K | CFG and EST (rate); OVR at levels C and O | D-22; 606-10-32-10, 55-22 to 55-29 [F]; IFRS 15.B20-B27 | ALG-06. `ACTUAL_RETURNS_ONLY` is treated as an expected return rate of 0 and requires a JDG that expected returns are immaterial. A POB is returnable only when `EXPECTED_RETURNS` is set at level O, C or P (on the POB, the contract or the product template) or when a `RETURN_RATE` estimate targets it; the framework default alone never makes a POB returnable (rev 1.2 adds levels C and O; D-76 ruling on `ENGINE_SPEC:OQ-A-15`; ENGINE_SPEC S04-R-08a) | RET, PAR |
| POL-052 | `returns.reversal_rate` | At what rate is revenue reversed for returned units in excess of the refund liability? | `AVERAGE_CARRYING_RATE`, `CURRENT_REMAINING_RATE` | `AVERAGE_CARRYING_RATE` | same as 606 | `CURRENT_REMAINING_RATE` (legacy L1028) | T | K | CFG | 606-10-55-23 [F]; legacy 02 FX-delivery-04 | Applies only under POL-053 `RESTORE_REMAINING_QUANTITY`. Under `REDUCE_CONTRACT_QUANTITY`, every returned unit, including units beyond the previous E, reverses through ALG-06 step 2 at rate r, so this option has no effect (rev 1.2; D-76 ruling on `_coverage/answer-keys-topics:OQ-AKT-03`). `AVERAGE_CARRYING_RATE` = cumulative revenue ÷ cumulative units delivered on the return date. `CURRENT_REMAINING_RATE` = remaining allocation ÷ remaining quantity (legacy). When the remaining quantity is 0, `CURRENT_REMAINING_RATE` falls back to the average carrying rate: cumulative revenue at full precision (X_p × f_p, ALG-01 §2.1.3) ÷ cumulative delivered quantity. The reversal posts through ALG-01 §2.1.3 (`docs/legacy/DEVIATIONS.md` DEV-060; DEVIATIONS:OQ-D9 confirmed in rev 1.1). [J] Exact rationals leave no float residue, so the fallback applies only at zero remaining quantity | RET, PAR |
| POL-053 | `returns.returned_units_scope` | Does a returned unit leave the contract or become deliverable again? | `REDUCE_CONTRACT_QUANTITY`, `RESTORE_REMAINING_QUANTITY` | `REDUCE_CONTRACT_QUANTITY` | same as 606 | `RESTORE_REMAINING_QUANTITY` (legacy L1032-1042) | P, C | K | CFG | 606-10-55-23, 55-28 (exchanges for identical products are not returns) [F] | ALG-06 §2.7.3 | RET, PAR |
| POL-055 | `breakage.method` | How is expected breakage on nonrefundable prepayments recognised? | `PROPORTIONAL_TO_EXERCISE`, `WHEN_REMOTE` | `PROPORTIONAL_TO_EXERCISE` when an approved constrained breakage estimate exists, else `WHEN_REMOTE` | same as 606 | n/a | P | K | EST | 606-10-55-46 to 55-49 [F]; FASB Example 52 | Breakage revenue to date = expected breakage × cumulative redemptions ÷ expected total redemptions, cumulatively rounded. Amounts remittable under unclaimed-property law are never recognised (55-49) | BRK, MR |
| POL-056 | `royalty.unreported_sales` | Are royalties on sales or usage that have occurred but are not yet reported accrued? | `ACCRUE_ESTIMATE`, `AS_REPORTED` | `ACCRUE_ESTIMATE` | same as 606 | n/a | C | P | EST; OVR for `AS_REPORTED` | 606-10-55-65 [F]; practice (research 04 §5.9) | `ACCRUE_ESTIMATE`: a period-end estimate version for occurred sales (JET-02), trued up when the report arrives (JET-04). `AS_REPORTED` requires an approved attestation that the lag effect is immaterial | ROY |
| POL-057 | `royalty.minimum_guarantee` | How is a fixed minimum guarantee in a royalty-bearing licence recognised? | `FIXED_ON_LICENCE_PATTERN`, `ROYALTY_WITH_FLOOR_TRUE_UP` | `FIXED_ON_LICENCE_PATTERN` | same as 606 | n/a | C | K | JDG | 606-10-55-65 to 55-65B [F]; practice alternatives (DART 12.7; research 04 §5.9). [J] The guarantee is fixed consideration and follows the licence's transfer pattern | The guarantee is in the transaction price and allocated. Royalties are recognised only when cumulative royalties exceed the cumulative guarantee | ROY |

POL-050 and POL-054 are `Retired` (covered by PT-10 and PT-01).

Table 1.4-A: default VC estimation method by VC type (POL-040).

| VC type | Default method | Rationale [J] |
|---|---|---|
| `BONUS`, `PENALTY` with two outcomes | `MOST_LIKELY_AMOUNT` | Binary outcomes (606-10-32-8(b)) |
| `PERFORMANCE_INCENTIVE` with more than two outcomes | `EXPECTED_VALUE` | Probability-weighted (32-8(a)) |
| `REBATE`, `VOLUME_TIER`, `PRICE_PROTECTION`, `SLA_CREDIT` | `EXPECTED_VALUE` | Many outcomes |
| `RETURN` | `EXPECTED_VALUE` | Portfolio of similar sales (55-23) |
| `IMPLICIT_PRICE_CONCESSION` | `EXPECTED_VALUE` | Payor-class history (606-10-32-7) |
| `CLAIM`, `UNPRICED_CHANGE_ORDER` | `MOST_LIKELY_AMOUNT` | Negotiated single outcome (25-11) |
| `USAGE` or `ROYALTY` meeting 32-40 or 55-65 | not estimated | Recognised as the usage or sale occurs |

### 1.5 Step 4: allocation and SSP

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-070 | `ssp.version_basis` | Which SSP book version prices a contract at inception? | `LATEST_APPROVED_EFFECTIVE_AT_INCEPTION`, `NAMED_VERSION` | `LATEST_APPROVED_EFFECTIVE_AT_INCEPTION` | same as 606 | `NAMED_VERSION` (legacy per-POB `SSP Version`, legacy 01 PAR-08) | T; override O | K | OVR for a per-POB override | 606-10-32-31 [F]; research 07 §5.1 | Pins SSP version id and row per POB (V7). Overrides are listed in the override register. **Recorded and read back (rev 1.97; item PIN-READBACK-1).** The pin is the version each pricing was made from: the POB's own pricing (04 T-CON-11 `ssp_book_version_id`) and its weight in each modification (04 T-CON-07 `pinned_refs.ssp_weights`). Every later computation prices from the recorded version (ENGINE_SPEC S05-R-03, S06-R-11; 05 RCP-15), so an SSP book version approved afterwards prices only what was not yet priced, whatever its effective dates: the transaction price is not reallocated for later changes in standalone selling prices (606-10-32-43; IFRS 15.88). The pin starts at the contract's activation — a draft is priced from the version in force until then — an approved override wins over it, and a modification computed for the first time prices at its date (POL-080) | SSP, PAR |
| POL-071 | `ssp.inside_range_point` | Which point is the SSP when the stated price is inside the SSP range? | `CONTRACT_PRICE`, `MIDPOINT` | `CONTRACT_PRICE` | `CONTRACT_PRICE` | `CONTRACT_PRICE` | T, E, P | K | CFG | DART 7.3.3.6.2: no reallocation is needed when stated prices fall within the range [practice]; legacy L692-700 | Section 3.4 | SSP |
| POL-072 | `ssp.outside_range_point` | Which point is the SSP when the stated price is outside the range? | `NEAREST_BOUND`, `MIDPOINT`, `LOW_POINT`, `HIGH_POINT`, `OBSERVABLE_POINT` | `NEAREST_BOUND` | `NEAREST_BOUND` | `NEAREST_BOUND` | T, E, P | K | CFG | 606-10-32-31 to 32-33 [F]; DART 7.3.3.6.2 lists midpoint, outer point, low point and high point, applied consistently [practice]; D-32 | Section 3.4; CHK-030 | SSP, ALC, PAR |
| POL-073 | `ssp.range_validation` | Which range statistics are checked when an SSP version is published? | `max_half_width_pct` decimal; `min_coverage_pct` decimal; `mode` ∈ {`WARN`, `BLOCK`} | 0.20; 0.50 (coverage must be strictly greater); `WARN` | same as 606 | `NOT_ENFORCED` | T | P | CFG | U-02 verified [practice, not Codification]: DART 7.3.3.6.1, a range that "encompasses the majority of the relevant transactions (i.e., greater than 50 percent)" and "has a width extending no greater than 20 percent from the midpoint in either direction" | Section 3.3 | SSP |
| POL-074 | `ssp.method_hierarchy` | Which estimation methods may an SSP row use, in what order of preference? | `observable` → `adjusted_market` → `cost_plus_margin` → `residual` (restricted) | FORCED | FORCED | `legacy_range` with the legacy band attributes | P (SSP row) | K | FIX | 606-10-32-32 to 32-35 [F]; IFRS 15.76-80; method literals are 04 E-47 (D-73) | Section 3.1 | SSP |
| POL-075 | `ssp.residual_failure` | What happens when a residual SSP is not permitted or fails its checks? | `REQUIRE_ESTIMATED_SSP`, `BLOCK` | `REQUIRE_ESTIMATED_SSP` | same as 606 | n/a (legacy has no residual) | T | K | OVR (each residual use) | 606-10-32-34(c), 32-35, 32-38 [F]; FASB Example 34 Case C | Section 3.2 | SSP, ALC |
| POL-076 | `alloc.discount_exception` | May a discount be allocated entirely to some POBs? | `DISABLED`, `PROPOSE_WITH_APPROVAL` (parameter `bundle_discount_tolerance_pp`, default 0.02) | `PROPOSE_WITH_APPROVAL` | same as 606 | `DISABLED` | T | K | OVR | 606-10-32-36 to 32-38 [F]; FASB Example 34. [J] Two percentage points separates an observed bundle discount from a coincidental one | Engine tests (a) every item in the bundle has an `observable` SSP row, (b) the bundle book shows the bundle regularly sold at a discount, (c) \|d_B − d_C\| ÷ S_B ≤ tolerance, where S_B = Σ resolved SSP of the bundle's components, d_B = S_B − the regular bundle price, and d_C = Σ resolved SSP of the contract's POBs − the transaction price available for allocation (after targeted VC). Both discount amounts are compared as shares of S_B (rev 1.2 replaces the comparison of percentages on different bases; D-76 ruling on `_coverage/answer-keys-topics:OQ-AKT-02`). A residual-eligible POB enters Σ SSP at the residual R computed with the proposed exception (section 3.2). FASB Example 34 Case A: d_B = d_C = 40 on S_B = 100, difference 0 pp (the rev 1.1 test failed by 11.4 pp); Case B (TP 130, residual D 30): d_C = 170 − 130 = 40, difference 0 pp. It proposes; the reviewer approves through a reviewed E-56 `OTHER` judgement with outcome `discount_exception_bundle` (D-76 ruling on `ENGINE_SPEC:OQ-A-17`). Then residual (section 3.2), then relative SSP | ALC |
| POL-077 | `alloc.zero_total_ssp` | What if every POB of a contract has SSP 0? | `REJECT` | FORCED | FORCED | FORCED | T | K | FIX | 606-10-32-31 [F]; legacy 01 TC-setup-18 | Validation error `TOTAL_SSP_ZERO`; the contract stays in draft | ALC |
| POL-078 | `alloc.negative_booking_lines` | May a booking line carry a negative quantity or price? | `REJECT_ROUTE_TO_RETURNS_OR_VC` | FORCED | FORCED | FORCED (legacy import maps such rows to return or VC events, D-22) | T | K | FIX | D-22; legacy 01 AA-07 | A negative line is never a POB. The legacy importer maps negative rows to `RETURN_RECORDED`, `CREDIT_MEMO_RECORDED` or a VC element (POL-213) | ALC, RET, ONB |
| POL-079 | `ssp.currency_conversion` | How is an SSP expressed in another currency converted to the contract currency? | `CONVERT_AT_INCEPTION_SPOT`, `CURRENCY_SPECIFIC_BOOK_REQUIRED` | `CONVERT_AT_INCEPTION_SPOT` when no row exists for the contract currency | same as 606 | n/a | T | K | CFG | 606-10-32-31 (SSP at inception) [F]; research 06 §9.1 | The converted SSP is stored with its rate id and never reconverted (32-43) | SSP, FX |
| POL-080 | `mod.ssp_basis` | Which SSPs weight a modification's reallocation? | `D18_DEFAULT`, `INCEPTION_ALL`, `LEGACY_CARRIED_PLUS_FILE_VERSION` | `D18_DEFAULT` | `D18_DEFAULT` | `LEGACY_CARRIED_PLUS_FILE_VERSION` | T; override O | K | CFG; OVR for a per-POB override to another approved version with justification (D-18) | D-18; 606-10-25-13(a), (b), 32-43 [F]; DART 9.2.1: the SSP of additional goods is determined at the modification date [practice] | ALG-04 | MOD, SSP, PAR |
| POL-081 | `mod.reduction_ssp` | At what SSP are removed units taken out of the weights? | `CARRIED_UNIT_SSP`, `CLAMPED_MOD_PRICE` | `CARRIED_UNIT_SSP` | same as 606 | `CLAMPED_MOD_PRICE` (legacy L1286-1331, L1770-1815) | T | K | CFG | 606-10-25-13(a) [F]; legacy 03 FX-07; legacy 04 FIX-03 | ALG-04 step 3 | MOD, PAR |

### 1.6 Step 5: recognition

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-090 | `recognition.time_convention` | How is time-elapsed progress measured? | `DAILY`, `MONTHLY_EVEN`, `MID_MONTH` | `DAILY` | `DAILY` | n/a (legacy recognises uploaded quantities) | T, P | K | CFG | 606-10-25-31, 55-20 [F]; research 06 §7.2; REQ-REC-003; D-75 (B1-004). [J] `MONTHLY_EVEN` and `MID_MONTH` are practical approximations of time elapsed; selecting one is a CFG change with the impact simulation of section 0.6 | ALG-11. `DAILY`: actual days in the period over days in the term. `MONTHLY_EVEN`: equal amounts per whole period, with partial first and last periods prorated by days. `MID_MONTH`: equal amounts per counted period under the day-15 rule. Every option posts through ALG-01 §2.1.3 (CHK-140 to CHK-145). Rev 1.1 retires `MONTHLY_WHOLE_MONTHS`, replaced by `MONTHLY_EVEN` with identical results on whole-month terms, and the validation error `TERM_NOT_WHOLE_MONTHS` | REC |
| POL-091 | `recognition.measure_of_progress` | Which measure applies to an over-time POB? | `TIME_ELAPSED`, `UNITS_DELIVERED`, `MILESTONE`, `COST_TO_COST`, `LABOUR_HOURS`, `RIGHT_TO_INVOICE`, `COST_RECOVERY` | per revenue policy template | same as 606 | `UNITS_DELIVERED` | P, O | K (one measure per POB; a change is an error correction) | CFG (template); OVR (POB) | 606-10-25-31 to 25-37, 55-16 to 55-21 [F] | `COST_RECOVERY` recognises revenue equal to recoverable costs incurred until progress can be reasonably measured (25-37). Uninstalled materials meeting 55-21(b) are recognised at zero margin and excluded from the progress ratio (FIX). The ERP posts the materials cost; the engine posts revenue equal to that cost through JET-02 and no `COST_OF_REVENUE` line (D-76 ruling on uninstalled materials, `POLICIES:OQ-15`; REQ-REC-007 amended). The expected materials cost excluded from the ratio is the `EAC` member `uninstalled_materials_cost`, and absent it the materials cost incurred to date (D-76 ruling on `ENGINE_SPEC_B:OQ-B-05`) | REC |
| POL-092 | `recognition.right_to_invoice_guard` | When is the right-to-invoice expedient blocked? | `BLOCK_IF_NONLINEAR_OR_FIXED_COMPONENT`, `ALLOW` | `BLOCK_IF_NONLINEAR_OR_FIXED_COMPONENT` | same as 606 | n/a | T | K | OVR to allow despite the guard | 606-10-55-18 [F]; practice: upfront fees, minimums and tiered or declining rates can stop the invoice from corresponding directly to value (research 05 CAP-24) | The guard blocks `RIGHT_TO_INVOICE` when the POB's pricing terms include any upfront fixed fee, annual minimum, tier, rebate or non-constant rate | REC, DISC |
| POL-094 | `bill_and_hold.custodial_pob` | Does an approved bill-and-hold create a custodial POB? | `CREATE_WHEN_SSP_PROVIDED`, `NEVER` | `CREATE_WHEN_SSP_PROVIDED` | same as 606 | n/a | T | K | JDG (the four 55-83 criteria) | 606-10-55-81 to 55-84 [F] | The custodial POB is recognised `TIME_ELAPSED` over the expected holding period. The four 55-83 criteria are recorded as an E-56 `BILL_AND_HOLD` judgement; a `DELIVERY_RECORDED` with trigger `BILL_AND_HOLD` and no reviewed judgement raises `BILL_AND_HOLD_CRITERIA_UNMET` (`WARNING`) (D-76 ruling on `ENGINE_SPEC_B:OQ-B-04`) | REC |
| POL-095 | `recognition.control_trigger` | Which recorded triggers may transfer control of a POB whose terms include a customer-acceptance clause or a consignment arrangement? | `ANY_TRANSFER`, `ACCEPTANCE_ONLY`, `SELL_THROUGH_ONLY` | `ANY_TRANSFER` | same as 606 | n/a | P, O | K | JDG (the term that justifies a restricted option) | 606-10-25-30; 55-79, 55-80 (consignment); 55-85 to 55-88 (customer acceptance) [F]; D-76 ruling on `ENGINE_SPEC_B:OQ-B-03` (added in rev 1.2) | `ANY_TRANSFER`: every 04 E-03 `DELIVERY_RECORDED` payload `trigger` transfers control, as recorded by the preparer (ENGINE_SPEC_B S09-R-11). `ACCEPTANCE_ONLY` (subjective acceptance clause): only `ACCEPTANCE` and `CONTROL_TRANSFER` (for example a trial that lapses) transfer control. `SELL_THROUGH_ONLY` (consignment): only `SELL_THROUGH` and `CONTROL_TRANSFER` (for example the consignee's obligation to buy at the end of the consignment period) transfer control. A `DELIVERY_RECORDED` whose trigger the resolved option does not permit is rejected with 422 `validation-failed` and posts nothing | REC |

POL-093 is `Retired` (merged into POL-091).

### 1.7 Contract modifications

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-100 | `mod.route_selection` | Who selects the 25-12 or 25-13 route? | `ENGINE_PROPOSES_PREPARER_CONFIRMS`, `USER_SELECTED_TEMPLATE` | `ENGINE_PROPOSES_PREPARER_CONFIRMS` | same as 606 | `USER_SELECTED_TEMPLATE` | T | P | OVR when the preparer departs from the proposal | 606-10-25-10 to 25-13 [F]; research 04 §6.1 | ALG-04 step 1. Parity maps the legacy prospective template to `LEGACY_PROSPECTIVE`, the retrospective template to `LEGACY_RETROSPECTIVE` and the POB-specific VC template to `LEGACY_POB_VC` (ALG-04 §2.5.7) | MOD, PAR |
| POL-101 | `mod.separate_contract_price_test` | When does the price of added distinct goods "reflect SSP" (25-12(b))? | `WITHIN_MOD_DATE_RANGE` (parameter `point_tolerance_pct`, default 0.00) | `WITHIN_MOD_DATE_RANGE` | same as 606 | n/a (legacy has no 25-12 path) | T | K | OVR (preparer attests "SSP adjusted for the circumstances of the contract") | 606-10-25-12(b) [F]; FASB Example 5 Case A | The test uses the modification-date SSP row with inclusive bounds. A point SSP requires an exact match unless a tolerance is configured or the attestation is approved | MOD |
| POL-102 | `mod.catch_up_scope` | Which POBs may receive a cumulative catch-up in a modification that is not a separate contract? | `PARTIALLY_SATISFIED_NONDISTINCT_ONLY`, `ALL_POBS_FULL_REALLOCATION` | `PARTIALLY_SATISFIED_NONDISTINCT_ONLY` | same as 606 | `ALL_POBS_FULL_REALLOCATION` for the retrospective template (D-32) | T | K | CFG | 606-10-25-13(b), (c) [F]; D-32; legacy 04 W1 | ALG-04 | MOD, PAR |
| POL-103 | `mod.mixed_allocation` | In a 25-13(c) modification, which consideration is reallocated? | `REMAINING_TP`, `TOTAL_TP`, `ATTRIBUTE_BY_LINE` | `REMAINING_TP` | `REMAINING_TP` | `TOTAL_TP` for the retrospective template; `REMAINING_TP` with legacy weights for the prospective template | T | K | CFG | 606-10-25-13(c) [F]; DART 9.2.2 Alternative A (total updated transaction price) and Alternative B (remaining updated transaction price) [practice]; research 04 §6.5 (by line). [J] `REMAINING_TP` is the literal 25-13(a) pool for the distinct part and never moves revenue already recognised on satisfied POBs | ALG-04 | MOD, PAR |
| POL-104 | `mod.price_change_on_satisfied_performance` | How is modification consideration that relates to goods already transferred accounted for? | `RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS`, `POOL_WITH_REMAINING` | `RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS` | same as 606 | `POOL_WITH_REMAINING` (legacy pools all `Mod Billing`) | T | K | OVR (the preparer tags the attributable amount) | 606-10-32-42 to 32-45 [F]; FASB Example 5 Case B: the credit for defective units reduces revenue at the modification date [F] | ALG-04 step 2. When every POB is satisfied, the whole amount is recognised in the period (legacy D-06 drops it; corrected value in `docs/legacy/DEVIATIONS.md`) | MOD, ALC |
| POL-105 | `mod.unpriced_change_orders` | How is an approved change in scope with an undetermined price accounted for? | `ESTIMATE_WITH_CONSTRAINT` | FORCED | FORCED | FORCED (not exercised by legacy) | T | K | EST and JDG (enforceability) | 606-10-25-10, 25-11 [F]; FASB Example 9 | PT-05 | MOD, VC |
| POL-106 | `mod.post_modification_vc_routing` | To which POBs is a later change in VC promised before a modification allocated? | `ASC_606_10_32_45` | FORCED | FORCED | not applied (legacy has no POB lineage; latent true-up is a defect, DEVIATIONS) | T | K | FIX | 606-10-32-45 [F]; IFRS 15.90 | VC promised before a 25-13(a) modification is allocated to the POBs identified before the modification; the share of POBs unsatisfied at the modification flows into the post-modification pool and is re-split by the post-modification weights (FASB Example 6). Otherwise the change is allocated to the POBs of the modified contract | MOD, VC |
| POL-107 | `mod.catch_up_progress_basis` | Which progress measure drives catch-ups? | `POB_MEASURE`, `LEGACY_BY_TEMPLATE` | `POB_MEASURE` | `POB_MEASURE` | `LEGACY_BY_TEMPLATE`: SSP-delivered share for the retrospective and POB-specific VC templates; units share for the prospective template | T | K | FIX | legacy 03 §3.5; legacy 04 §3.6; legacy 05 §3.5; legacy 07 J2 | ALG-04 §2.5.7 | MOD, PAR |

### 1.8 Contract balances and presentation

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-120 | `position.netting_unit` | At what unit are contract assets and contract liabilities netted? | `CONTRACT_ENTITY_BOOK` | FORCED | FORCED | FORCED | T | P | FIX | D-12, D-23; 606-10-45-1 [F]; DART 14.1: net within a contract, no netting across contracts [practice]. Contracts combined under 606-10-25-9 are one contract | ALG-02 | POS, ENT |
| POL-121 | `position.reclass_attribution_key` | How is the period-end reclass attributed to POB-level account strings? | `POB_DEBIT_POSITIONS`, `CUMULATIVE_SSP_DELIVERED` | `POB_DEBIT_POSITIONS` | `POB_DEBIT_POSITIONS` | `CUMULATIVE_SSP_DELIVERED` (D-32; legacy L1081-1089; VC lines excluded) | T | P | CFG | 606-10-45-1 fixes the presentation unit; attribution to account strings is not prescribed [F]; legacy-02:OQ2. [J] Attributing to the POBs that carry the debit keeps each account string's sign economically meaningful | ALG-02 step 5, including the terminal resolved-SSP step that ends each fallback chain | POS, PAR |
| POL-122 | `balance.right_to_consideration` | Is an earned but uninvoiced amount a conditional right (contract asset) or an unconditional right (unbilled receivable)? | `CONDITIONAL`, `UNCONDITIONAL` | by measure and billing terms (ALG-03 table 2.4-A) | same as 606 | ALG-03 table 2.4-A, with both roles mapped to the POB's "Unbilled A/R Account" (D-15, D-32), so postings equal legacy | P, O | K | OVR | D-15; 606-10-45-3, 45-4 [F]; DART 14.4: the caption "unbilled receivable" does not decide the classification [practice] | ALG-03 | POS, DISC |
| POL-123 | `balance.position_invoice_basis` | Which invoices count as "billed or unconditionally due" in the position? | `ERP_POSTED_INVOICES`, `UNCONDITIONAL_INVOICES_ONLY` | derived: `ERP_POSTED_INVOICES` when POL-004 = `ERP`; `UNCONDITIONAL_INVOICES_ONLY` when POL-004 = `ENGINE` | same as 606 | `ERP_POSTED_INVOICES` | T | P | FIX (derived from POL-004) | 606-10-45-2, 45-4; FASB Example 38 and 606-10-55-286 [F] | `ENGINE` mode: an invoice issued before the right is unconditional (cancellable advance billing) is memo-only until the earlier of its noncancellable due date and cash receipt (JET-03). `ERP` mode: the engine mirrors what the ERP posted so that the GL contract liability ties to the subledger (research 07 RC-02) | JE, POS |
| POL-124 | `balance.current_noncurrent` | Are contract balances classified as current or noncurrent? | `EXPECTED_TIMING_12_MONTHS`, `NONE` | `EXPECTED_TIMING_12_MONTHS` | same as 606 | `NONE` | E | P | CFG | ASC 210-10-45 (current assets and current liabilities) [F]; IAS 1.66, 1.69 | Reporting view only, no postings. Contract liability expected to be recognised within 12 months of the balance-sheet date is current; contract assets and unbilled receivables expected to become receivable or be collected within 12 months are current; computed from schedules and billing plans | POS, DISC |
| POL-125 | `balance.credit_losses` | Does the engine measure expected credit losses on receivables and contract assets? | `EXTERNAL_MODEL` | `EXTERNAL_MODEL` FORCED | `EXTERNAL_MODEL` FORCED | `EXTERNAL_MODEL` FORCED | E | P | FIX | 606-10-45-3, 45-4 and 50-4 as amended by ASU 2016-13 (Subtopic 326-20) [F]; ASU 2025-05 practical expedient (section 4) [F]; IFRS 15.107 and IFRS 9. [J] D-14a adds no allowance or credit-loss role: `RECEIVABLE_CONTRA` carries implicit price concessions (JET-04c), which reduce the transaction price (606-10-32-7), and credit losses are measured outside revenue | The engine never posts allowances. It exports the population of contract assets, unbilled receivables and (in `ENGINE` mode) receivables by entity, book, currency and age bucket for the tenant's credit-loss model, and records the ASU 2025-05 expedient election for disclosure (PT-07) | POS |
| POL-126 | `rollforward.opening_liability_consumption` | How is "revenue recognised from the opening contract liability" measured? | `FIFO_WITHIN_CONTRACT`, `FIFO_WITHIN_POB` | `FIFO_WITHIN_CONTRACT` | same as 606 | `FIFO_WITHIN_CONTRACT` | T | P | CFG | 606-10-50-8(b) [F]; IFRS 15.116(b); research 04 §10. [J] The contract is the presentation unit | For each (contract, entity, book) and period: revenue from opening liability = min(opening contract liability presented, revenue relief posted in the period). `FIFO_WITHIN_POB` applies the same formula per POB using POB-attributed invoices | DISC |
| POL-127 | `balance.refund_liability_presentation` | Are refund liabilities netted into the contract position? | `SEPARATE` | FORCED | FORCED | FORCED | T | P | FIX | D-15; 606-10-55-27 [F]; DART 14.3 [practice] | `REFUND_LIABILITY` and `RETURN_ASSET` are excluded from ALG-02 | POS, RET |
| POL-128 | `balance.deposit_liability` | Where do receipts go while a contract fails Step 1? | `DEPOSIT_LIABILITY` | FORCED | FORCED | n/a | T | P | FIX | 606-10-25-8 [F]; IFRS 15.16 | JET-01b; excluded from ALG-02 | STP1 |

### 1.9 Contract costs and loss contracts

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-140 | `costs.obtain_expedient` | Are incremental costs of obtaining a contract expensed when the amortisation period would be one year or less? | `APPLY`, `DO_NOT_APPLY` | `APPLY` | `APPLY` | `APPLY` (legacy has no cost events) | T, E, P (by commission plan) | K | CFG | 340-40-25-4; use disclosed under 340-40-50-5 [F]; IFRS 15.94 | Derived amortisation period ≤ 12 months and `APPLY` → no asset; cost stays in expense. Otherwise JET-09 capitalises | COST, DISC |
| POL-141 | `costs.amortisation_period` | Over what period is a cost asset amortised? | `TERM_PLUS_EXPECTED_RENEWALS_UNLESS_COMMENSURATE`, `CONTRACT_TERM`, `EXPECTED_CUSTOMER_LIFE` | `TERM_PLUS_EXPECTED_RENEWALS_UNLESS_COMMENSURATE` | same as 606 | n/a | P | K | EST (expected renewals and life) | 340-40-35-1, 35-2 [F]; FASB staff Implementation Q&A 71 [practice] | If the renewal commission is commensurate (POL-142), the initial commission is amortised over the initial term and each renewal commission over its renewal term. Otherwise the initial commission is amortised over the initial term plus expected renewals | COST |
| POL-142 | `costs.commensurate_ratio` | When is a renewal commission "commensurate" with the initial commission? | decimal ≥ 0 | 1.00 | 1.00 | n/a | T, P | K | OVR | Q&A 71 [practice]. [J] A renewal rate below the initial rate is evidence that part of the initial commission relates to renewals | Commensurate iff (renewal commission ÷ renewal contract value) ≥ ratio × (initial commission ÷ initial contract value) | COST |
| POL-143 | `costs.amortisation_pattern` | Which systematic pattern applies? | `STRAIGHT_LINE`, `PROPORTIONAL_TO_RELATED_REVENUE` | `STRAIGHT_LINE` | same as 606 | n/a | P | K | CFG | 340-40-35-1 [F]. [J] Straight line is deterministic when the period includes anticipated renewals that have no schedule | `STRAIGHT_LINE`: daily (POL-090) over the amortisation period with cumulative rounding. `PROPORTIONAL_TO_RELATED_REVENUE`: allowed only when the period equals the contract term; uses the related POBs' schedules | COST |
| POL-144 | `costs.impairment_reversal` | Is a contract-cost impairment reversed when conditions improve? | `PROHIBITED`, `REQUIRED_CAPPED` | `PROHIBITED` FORCED | `REQUIRED_CAPPED` FORCED | `PROHIBITED` | B | P | FIX | 340-40-35-6 [F]; IFRS 15.104 [F] | JET-09. The IFRS reversal is capped at the carrying amount that would have existed without the impairment | COST, IFRS |
| POL-145 | `costs.termination_acceleration` | On termination for convenience or churn, is the remaining cost asset expensed? | `ACCELERATE_TO_REMAINING_BENEFIT`, `CONTINUE` | `ACCELERATE_TO_REMAINING_BENEFIT` | same as 606 | n/a | T | P | CFG | 340-40-35-2, 35-3 [F] | PT-03 | COST |
| POL-146 | `costs.fulfilment_capitalisation` | When are costs to fulfil a contract capitalised? | `WHEN_25_5_ATTESTED` | FORCED | FORCED | n/a | P (cost pool) | K | JDG | 340-40-25-5 to 25-8 [F]; IFRS 15.95-98 | A cost pool is capitalised only with an approved attestation of the three 25-5 criteria and no other-Topic scope (25-6) | COST |
| POL-150 | `loss.unit` | At what level is an anticipated loss determined? | `CONTRACT`, `POB` | `CONTRACT` | `CONTRACT` FORCED | n/a | T | K | CFG | 605-35-25-47 as amended by ASU 2016-20 [F]; IAS 37.66 | JET-12 | LOSS, IFRS |
| POL-151 | `loss.scope` | Which contracts are tested for anticipated losses? | `SCOPED_605_35_ONLY`, `ALL_CONTRACTS_WITH_EAC` | `SCOPED_605_35_ONLY` | `ALL_CONTRACTS_WITH_EAC` FORCED | n/a | B | K | CFG | 605-35-15, 25-45 to 25-46A [F]; IAS 37.66 [F] | Contract flag `scope_605_35`. The IFRS book tests every contract with an EAC | LOSS, IFRS |
| POL-152 | `loss.cost_basis` | Which costs enter the loss test? | `SUBTOPIC_605_35_COSTS`, `IAS37_68A_COSTS` | `SUBTOPIC_605_35_COSTS` FORCED | `IAS37_68A_COSTS` FORCED | n/a | B | K | FIX | 605-35-25-46A [F]; IAS 37.68A (May 2020 amendment) [F, research 04 S11] | IFRS: incremental costs plus an allocation of other costs that relate directly to fulfilling contracts | LOSS, IFRS |
| POL-153 | `loss.consideration_basis` | Which consideration enters the loss test? | `UNCONSTRAINED_CREDIT_ADJUSTED_TP` | FORCED | FORCED | n/a | T | K | FIX | 605-35-25-46A [F] | Loss = max(0, EAC costs − unconstrained credit-adjusted TP) less loss already recognised through margin to date (ALG in ENGINE_SPEC loss stage) | LOSS |

### 1.10 Foreign currency and legal entities

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-160 | `fx.cl_layer_date` | Which date sets the historical rate of a contract-liability layer? | `EARLIER_OF_RECEIPT_AND_UNCONDITIONAL_DUE`, `INVOICE_ISSUE_DATE` | `EARLIER_OF_RECEIPT_AND_UNCONDITIONAL_DUE` | `EARLIER_OF_RECEIPT_AND_UNCONDITIONAL_DUE` FORCED | `EARLIER_OF_RECEIPT_AND_UNCONDITIONAL_DUE` (single currency: no effect) | E | P | CFG (US book only) | 606-10-45-2 (liability when paid or due, whichever is earlier) [F]; IFRIC 22.8-9: date of initial recognition of the nonmonetary liability [F, research 06 S33]. D-92 (5): under `INVOICE_ISSUE_DATE` an `ENGINE`-mode cancellable line's issue date is its S10-R-06 billing date (a receipt applied or a same-amount noncancellable update) — a layer never predates the liability (ENGINE_SPEC_B S12-R-04, S12-INV-03); ERP lines keep the invoice issue date; flagged AD-29 for G12. D-87 L6-5-Q-14 with supervisor ruling R-81 (rev 1.52; candidate AD-51 for the accountant): under `EARLIER_OF_RECEIPT_AND_UNCONDITIONAL_DUE` the "unconditional due" date of an `ERP`-mode invoice is its payload `due_date` when present, and the resulting date stays in the accounting period in which the line enters the position — a later date gives that period's end, an earlier date the S10-R-06 date (ENGINE_SPEC_B S12-R-04 rev 1.83) | ALG-08 | FX, IFRS |
| POL-161 | `fx.cl_layer_consumption` | In what order are contract-liability layers derecognised? | `FIFO`, `PRO_RATA` | `FIFO` | `FIFO` | `FIFO` | E | P | CFG | research 06 §9.3 flag 2. [J] FIFO matches the order in which advances are consumed by performance and is auditable layer by layer | ALG-08 | FX |
| POL-162 | `fx.unbilled_revenue_rate` | Which rate measures revenue recognised in excess of the available contract liability? | `PERIOD_AVERAGE`, `TRANSACTION_DATE_SPOT` | `PERIOD_AVERAGE` | `PERIOD_AVERAGE` | n/a | E | P | CFG | ASC 830-10-55-10, 55-11 (average rates as an approximation) [F, research 06 S34]; IAS 21.22 | ALG-08 | FX |
| POL-163 | `fx.cl_historical_layering` | Are contract liabilities measured at historical rates (nonmonetary) rather than remeasured? | `ENABLED`, `DISABLED_REMEASURE_AS_MONETARY` | `ENABLED` | `ENABLED` FORCED | `ENABLED` | E, C | P | CFG; OVR at contract level | D-25 (US GAAP layer flag); D-25a (an approved contract-level override may treat refundable advance consideration as monetary, remeasured at the closing rate, in the ASC606 book; the IFRS15 book always applies IFRIC 22); contract liabilities are nonmonetary, contract assets monetary [practice, research 06 S31, S32]; IFRIC 22 [F] | `DISABLED_REMEASURE_AS_MONETARY` is permitted only at contract level, with OVR approval, for advance consideration refundable in cash, and only in the ASC606 book (D-25a); the liability is then remeasured at the closing rate (JET-10b) | FX, IFRS |
| POL-164 | `fx.monetary_remeasurement` | Which balances are remeasured at the closing rate? | `ASSET_POSITIONS_ENGINE_AR_AND_MONETARY_LIABILITIES` (rev 1.2 replaces `ASSET_POSITIONS_AND_ENGINE_AR`; D-25b) | FORCED | FORCED | FORCED (single currency: no effect) | T | P | FIX | D-25, D-25b; ASC 830-20-35-1: monetary balances remeasured at the current rate [F]; IAS 21.16 and 21.23(a): a liability settled in a fixed or determinable number of units of currency is monetary and translated at the closing rate [F]; contract assets classified as monetary [practice, research 06 S31, S32] | Remeasured at the closing rate at every period end and at settlement, non-reversing, against `FX_GAIN_LOSS`, in every book: (1) asset positions, the part of the contract position presented as contract asset or unbilled receivable (JET-10a); (2) in `ENGINE` billing mode, accounts receivable (JET-10a′); (3) refund liabilities, deposit liabilities and consideration payable to a customer denominated in a currency other than the entity's functional currency, which are monetary items (JET-10d; D-25b; ALG-08 §2.9.1). Contract liabilities stay nonmonetary except under the POL-163 override (D-25, D-25a). Return assets, customer incentive assets and noncash consideration assets are not remeasured [J: they are settled by goods or services or transfer out of the engine, so they are nonmonetary] | FX |
| POL-170 | `ic.revenue_entity` | Which legal entity recognises revenue when the performing entity differs from the contracting entity? | `PERFORMING_ENTITY`, `CONTRACTING_ENTITY` | `PERFORMING_ENTITY` | `PERFORMING_ENTITY` | `PERFORMING_ENTITY` (legacy POB `Selling Entity` = performing entity = contracting entity) | T, E | K | CFG and JDG (principal conclusion per entity) | D-23; ASC 810-10-45-1 (eliminations belong to consolidation) [F, research 06 S46]. [J] Matches the legacy per-POB selling entity and supports disaggregation by performing geography; D-23 requires intercompany pairs for cross-entity performance | ALG-07; JET-13 | ENT |
| POL-171 | `ic.pair_amount` | What amount does an intercompany pair carry? | `REVENUE_AMOUNT` | FORCED | FORCED | FORCED | T | K | FIX | D-23. Transfer-pricing charges are outside the engine | The pair equals the revenue relieved from the contracting entity's contract liability, in the transaction currency, converted to each entity's functional currency at the revenue rate (ALG-08) | ENT, FX |

### 1.11 Close, late events and estimates

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-180 | `late_events.posting` | Where does the effect of an event dated in a closed period post? | `FIRST_OPEN_PERIOD_WITH_ORIGIN` | FORCED | FORCED | FORCED (legacy backdating into prior versions is a defect: legacy 06 E-2, TC-JE-11) | T | P | FIX | D-19; research 06 §6.2; research 07 §5.4 | ALG-09 | LATE, DISC |
| POL-181 | `late_events.fx_rates` | Which rates apply to a late event? | `EFFECTIVE_DATE_RATES_CUMULATIVE_DIFFERENCE` | FORCED | FORCED | FORCED | T | P | FIX | D-19, D-25 | ALG-09 step 4 | LATE, FX |
| POL-182 | `estimates.versioning` | How are VC, constraint, return, breakage, EAC and exercise-likelihood estimates stored? | `IMMUTABLE_VERSIONS` | FORCED | FORCED | FORCED (legacy delta rows become versions, POL-043) | T | P | EST | D-20 | ALG-10 | VC, RET, BRK, MR, REC |
| POL-183 | `estimates.change_classification` | Is a change a change in estimate or an error correction? | `PREPARER_CLASSIFIES` (`CHANGE_IN_ESTIMATE`, `ERROR_CORRECTION`) | FORCED | FORCED | FORCED | T | P | JDG | ASC 250-10-45-17, 45-23 [F]; research 06 §6.3 | The engine never decides. `CHANGE_IN_ESTIMATE`: catch-up in the open period (ALG-10). `ERROR_CORRECTION`: reopen with dual approval (research 07 §5.4) and recompute in the reopened period | LATE |

### 1.12 Disclosures, nonpublic-entity reliefs and interim packs

The engine always computes every disclosure dataset; elections change only what the disclosure pack includes, so an election can change without recomputation (research 04 §12).

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-190 | `entity.reporting_type` | Which reporting-entity category applies? | `PBE`, `NFP_CONDUIT`, `EBP_SEC`, `NONPUBLIC` | `PBE` | n/a (IFRS 15 has no category-based relief) | `PBE` | E | P | CFG | Master Glossary "public business entity"; 606-10-50-7, 50-11, 50-16, 50-21, 50-23 [F] | Gates POL-191 to POL-196 and POL-202; drives POL-203 | DISC |
| POL-191 | `disclosure.nonpublic_disaggregation_relief` | May the quantitative disaggregation (50-5, 50-6, 55-89 to 55-91) be omitted? | `ELECT`, `DO_NOT_ELECT` | `DO_NOT_ELECT` (settable only when POL-190 = `NONPUBLIC`) | `DO_NOT_ELECT` FORCED | `DO_NOT_ELECT` | E | P | CFG | 606-10-50-7 [F] | Minimum still produced: revenue by timing of transfer plus qualitative economic factors | DISC, IFRS |
| POL-192 | `disclosure.nonpublic_contract_balances_relief` | May 50-8 to 50-10 and 50-12A be omitted? | `ELECT`, `DO_NOT_ELECT` | `DO_NOT_ELECT` (nonpublic only) | `DO_NOT_ELECT` FORCED | `DO_NOT_ELECT` | E | P | CFG | 606-10-50-11 covers "paragraphs 606-10-50-8 through 50-10 and 606-10-50-12A" (U-04 verified, section 4.3) [F] | Opening and closing receivables, contract assets and contract liabilities remain in the pack | DISC, IFRS |
| POL-193 | `disclosure.nonpublic_rpo_relief` | May the RPO disclosures (50-13 to 50-15) be omitted? | `ELECT`, `DO_NOT_ELECT` | `DO_NOT_ELECT` (nonpublic only) | `DO_NOT_ELECT` FORCED | `DO_NOT_ELECT` | E | P | CFG | 606-10-50-16 [F] | RPO dataset still computed | DISC, IFRS |
| POL-194 | `disclosure.nonpublic_judgements_relief` | May 50-18(b), 50-19 and 50-20 be omitted? | `ELECT`, `DO_NOT_ELECT` | `DO_NOT_ELECT` (nonpublic only) | `DO_NOT_ELECT` FORCED | `DO_NOT_ELECT` | E | P | CFG | 606-10-50-21 [F] | Methods, inputs and assumptions for assessing the constraint remain (research 04 §12) | DISC, IFRS |
| POL-195 | `disclosure.nonpublic_expedient_relief` | May the practical-expedient disclosures (50-22) be omitted? | `ELECT`, `DO_NOT_ELECT` | `DO_NOT_ELECT` (nonpublic only) | `DO_NOT_ELECT` FORCED | `DO_NOT_ELECT` | E | P | CFG | 606-10-50-23 [F] | Pack section suppressed | DISC, IFRS |
| POL-196 | `disclosure.nonpublic_cost_relief` | May the contract-cost disclosures (340-40-50-2, 50-3, 50-5) be omitted? | `ELECT`, `DO_NOT_ELECT` | `DO_NOT_ELECT` (nonpublic only) | `DO_NOT_ELECT` FORCED | `DO_NOT_ELECT` | E | P | CFG | 340-40-50-4, 50-6 [F] | Cost rollforward still computed | DISC, COST, IFRS |
| POL-197 | `rpo.exemption_original_duration_one_year` | Is RPO omitted for POBs in contracts with an original expected duration of one year or less? | `APPLY`, `DO_NOT_APPLY` | `DO_NOT_APPLY` | `DO_NOT_APPLY` | `DO_NOT_APPLY` | E | P | CFG | 606-10-50-14(a), 50-15 [F]; IFRS 15.121(a) [F, IFRS 15 as adopted by Regulation (EU) 2016/1905]. [J] Full RPO by default; the tenant elects knowingly with the 50-15 disclosure | Excluded POBs listed with nature, remaining duration and excluded-amount descriptor | DISC |
| POL-198 | `rpo.exemption_right_to_invoice` | Is RPO omitted for POBs recognised under the right-to-invoice expedient? | `APPLY`, `DO_NOT_APPLY` | `DO_NOT_APPLY` | `DO_NOT_APPLY` | `DO_NOT_APPLY` | E | P | CFG | 606-10-50-14(b) [F]; IFRS 15.121(b) with B16 [F] | As POL-197 | DISC |
| POL-199 | `rpo.exemption_royalty_vc` | Is sales- or usage-based royalty VC on licences omitted from RPO? | `APPLY`, `DO_NOT_APPLY` | `DO_NOT_APPLY` | `DO_NOT_APPLY` FORCED | `DO_NOT_APPLY` | E | P | CFG | 606-10-50-14A(a); not available for fixed consideration (50-14B) [F]. IFRS 15.121 lists only (a) and (b) [F, IFRS 15 text] | As POL-197 | DISC, IFRS |
| POL-200 | `rpo.exemption_vc_wholly_unsatisfied` | Is VC allocated entirely to a wholly unsatisfied POB or series increment (32-40) omitted from RPO? | `APPLY`, `DO_NOT_APPLY` | `DO_NOT_APPLY` | `DO_NOT_APPLY` FORCED | `DO_NOT_APPLY` | E | P | CFG | 606-10-50-14A(b), 50-14B [F]; IFRS 15.121 [F] | As POL-197. The excluded amount is the targeted-VC quota of each wholly unsatisfied POB or series increment in force at the measured date: stage 05 records it per POB and VC element at inception and stage 08 appends the quota after each reallocating version (ENGINE_SPEC S05-R-14, S08-R-07; D-76 ruling on `ENGINE_SPEC_B:OQ-B-21`; D-91). A negative quota exempts nothing | DISC, IFRS |
| POL-201 | `rpo.time_bands` | Which time bands present RPO? | ordered list of month boundaries | [12, 24]: "within 12 months", "13 to 24 months", "after 24 months" | same as 606 | same as 606 | T, E | P | CFG | 606-10-50-13(b) [F]; IFRS 15.120(b) [F] | Bands from current schedules at constrained transaction price; usage-based POBs use the latest estimate version | DISC |
| POL-202 | `franchisor.preopening_expedient` | Does a nonpublic franchisor apply the pre-opening services expedient? | `NOT_ELECTED`, `ELECT_DISTINCT_SERVICES`, `ELECT_SINGLE_SERVICES_POB` | `NOT_ELECTED` (nonpublic only) | `NOT_ELECTED` FORCED | `NOT_ELECTED` | E | K | CFG | 952-606-25-2 to 25-4, 952-606-50-1 to 50-2 (ASU 2021-02) [F] | Eligible SKUs mapped to the 952-606-25-2 list become distinct POBs or one combined services POB before allocation (research 04 §12 key S12-FRANCHISOR-OWN, re-baselined in CHK-006) | POB, IFRS |
| POL-203 | `disclosure.interim_revenue_pack` | Which revenue disclosures does an interim pack contain? | `TOPIC_270_LIST` | derived: 606-10-50-5 to 50-6, 50-8, 50-12A to 50-15, subject to the POL-191 to POL-193 elections for nonpublic entities | `IAS34_16A_L` (disaggregation only) FORCED | as 606 | E | P | FIX | 270-10-50-1A as amended by ASU 2016-20 [F]. ASU 2025-11 supersedes 270-10-50-1A and lists 606-10-50-5 through 50-6, 50-8 and 50-12A through 50-15 in 270-10-50-34, effective for interim periods within annual periods beginning after 15 December 2027 (PBE) and 15 December 2028 (others) [F, ASU 2025-11]. IAS 34.16A(l) [F]. [J] ASU 2025-11 aims to clarify, not expand, interim requirements, so nonpublic elections continue to apply (OQ-06) | Interim pack generator | DISC, IFRS |
| POL-204 | `disclosure.prior_period_pob_revenue_basis` | How is "revenue from POBs satisfied (or partially satisfied) in previous periods" measured? | `ALG10_DECOMPOSITION` | FORCED | FORCED | FORCED (legacy "Cumulative Catchup - Disclosure Only" fields map to it) | T | P | FIX | 606-10-50-12A [F]; IFRS 15.116(c) [F, IFRS 15 text] | ALG-10 §2.11.3 | DISC, VC, MOD, LATE |

### 1.13 Onboarding, migration and business combinations

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-210 | `onboarding.method` | How are in-flight contracts onboarded? | `RECOMPUTE_FROM_INCEPTION`, `OPENING_BALANCES_AT_CUTOVER` | `RECOMPUTE_FROM_INCEPTION` when inception data are complete; otherwise `OPENING_BALANCES_AT_CUTOVER` | same as 606 | legacy database import per D-31: mode (a) `OPENING_BALANCES_AT_CUTOVER`, mode (b) replay = `RECOMPUTE_FROM_INCEPTION` | import batch | K | CFG and OVR (batch approval) | D-31; research 04 §11 | `RECOMPUTE_FROM_INCEPTION`: replay events; the difference between recomputed and imported cumulative balances at cutover posts once, dated the cutover date, with reason `ONBOARDING_DIFFERENCE`. `OPENING_BALANCES_AT_CUTOVER`: imported balances per POB (allocation remaining, revenue to date, billed to date) become opening state; no revenue before cutover | ONB, PAR |
| POL-211 | `migration.nondistinct_mapping` | How is a legacy "Nondistinct" SKU flag mapped? | `SINGLE_POB`, `SERIES`, `REVIEW_QUEUE` | `REVIEW_QUEUE` | `REVIEW_QUEUE` | `SINGLE_POB` | import batch | K | OVR | 606-10-25-14(b), 25-15; series modifications are prospective under 25-13(a) [F]; legacy 03 A-04; legacy-03:OQ-06 | `REVIEW_QUEUE`: each Nondistinct POB is routed to a questionnaire (over time? same measure for each increment? substantially the same?) before commit | ONB, MOD, PAR |
| POL-212 | `migration.material_right_convention` | How are legacy material-right rows (L = 1, d = 0, r = 0, quantity = SSP in dollars) imported? | `CONVERT_TO_OPTION_RECORD`, `KEEP_QUANTITY_CONVENTION` | `CONVERT_TO_OPTION_RECORD` | same as 606 | `KEEP_QUANTITY_CONVENTION` | import batch | K | CFG | D-21, D-32; legacy 01 PAR-04 | `CONVERT_TO_OPTION_RECORD`: option SSP = quantity × 1 as `ENTERED_AMOUNT` (POL-026), quantity 1, exercise per POL-028. `KEEP_QUANTITY_CONVENTION`: dollar units delivered as quantity, allocation identical to legacy | ONB, MR, PAR |
| POL-213 | `migration.legacy_vc_rows` | How are legacy `VC` stratification rows imported? | `VC_ELEMENT_PLUS_CREDIT_EVENTS` | FORCED | FORCED | FORCED | import batch | K | FIX | D-22, D-30; legacy 07 A3, A4 | Each row becomes a contract-level VC element (`ENTERED_AMOUNT`, version 1 = stated price) and its billing rows become credit-memo events. Never a POB. Allocation is identical to legacy because the legacy VC row has SSP 0 (PAR-03) | ONB, VC, PAR |
| POL-214 | `migration.split_upload_allocation` | How are contracts split across legacy uploads allocated? | `ALLOCATE_ACROSS_ALL_POBS` | FORCED | FORCED | FORCED (legacy result is a deviation, D-17) | import batch | K | FIX | D-17; legacy 01 FIX-06, TC-setup-11 | Allocation always spans every POB of the contract | ONB, PAR |
| POL-215 | `bc.acquired_contract_measurement` | How are contract assets and contract liabilities acquired in a business combination measured? | `ASC606_AS_IF_ORIGINATED`, `FAIR_VALUE_IFRS3` | `ASC606_AS_IF_ORIGINATED` FORCED | `FAIR_VALUE_IFRS3` FORCED | n/a | B | K | JDG | 805-20-30-27, 30-28 (ASU 2021-08): recognise and measure in accordance with Topic 606 as if the acquirer had originated the contracts [F]; IFRS 3.18 acquisition-date fair value [F] | PT-11 | ONB, IFRS |
| POL-216 | `bc.expedient_modification_aggregation` | Does the acquirer reflect the aggregate effect of all pre-acquisition modifications? | `APPLY`, `DO_NOT_APPLY` | `APPLY` | n/a | n/a | acquisition (all contracts of one combination) | K | CFG | 805-20-30-29(a), 30-30 (acquisition-by-acquisition; consistently to all contracts of the combination; disclosures 805-20-50-5) [F, ASU 2021-08]. [J] Acquired histories rarely hold modification-level detail | The contract is built once at the acquisition date with its final scope and consideration; no modification events are replayed | ONB, MOD |
| POL-217 | `bc.expedient_ssp_at_acquisition` | Does the acquirer determine SSP at the acquisition date instead of contract inception? | `APPLY`, `DO_NOT_APPLY` | `APPLY` | n/a | n/a | acquisition | K | CFG | 805-20-30-29(b), 30-30 [F, ASU 2021-08]. [J] Inception SSP evidence of the acquiree is rarely available | SSP rows effective at the acquisition date weight the allocation of every POB of the acquired contract (CHK-121) | ONB, SSP |
| POL-218 | `transition.first_time_application` | For an entity first applying Topic 606 or IFRS 15 on the platform, which transition method's reports are produced? | `MODIFIED_RETROSPECTIVE`, `FULL_RETROSPECTIVE` | `MODIFIED_RETROSPECTIVE` | `MODIFIED_RETROSPECTIVE` | n/a | E | K | CFG | 606-10-65-1(d) to (i) [F]; IFRS 15.C3 to C8 [F] | Parallel `LEGACY` and framework books from the date of initial application; cumulative-effect report per contract (65-1(h)); the retained-earnings entry is exported for a manually approved journal (D-14a reserves `RETAINED_EARNINGS`; no 1.0 template posts it); completed-contract definition per framework (research 04 §13 #15) | ONB, DLT |

### 1.14 Scope routing and informational switches

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-230 | `scope.nonfinancial_asset_sale_610_20` | How are transfers of nonfinancial assets to noncustomers treated? | `ROUTE_OUT` | FORCED | FORCED (IAS 16/IAS 38 derecognition) | FORCED | T | K | FIX | Subtopic 610-20 applies the 606 control and measurement guidance to noncustomer transfers; ASU 2017-05 clarified its scope [F]; `docs/00-GOAL.md` §4 (other scopes routed out with a scope flag) | PT-08 | ONB |
| POL-231 | `scope.lessor_combination_expedient` | Does a lessor combine nonlease components with the associated lease component? | `NOT_ELECTED`, `ELECTED` | `NOT_ELECTED` | `NOT_ELECTED` FORCED | `NOT_ELECTED` | E, P | K | CFG | 842-10-15-38 to 15-42 (lessor allocates using 606-10-32-28 to 32-41) [F, ASU 2016-02]; lessor practical expedient 842-10-15-42A to 15-42C [F, ASU 2018-11]; IFRS 16.B32-B33 no lessor expedient [F] | PT-09 | ALC, ONB |
| POL-232 | `licence.combined_pob_nature` | Is the nature of a licence considered when it is part of a combined POB? | `CONSIDER_NATURE` | FORCED | FORCED | n/a | B | K | FIX | 606-10-55-57, 55-64 [F]; IFRS 15 less explicit (research 04 §13 #9). [J] Same behaviour in both books | The combined POB's over-time or point-in-time conclusion and measure consider the licence nature (POL-024) | POB, IFRS |
| POL-233 | `scope.repurchase_classification` | How are repurchase agreements classified? | `DECISION_TABLE_55_66_TO_55_78` | FORCED | FORCED (IFRS 15.B64-B76; IFRS 16 for the lease outcome) | n/a | C | K | JDG | 606-10-55-66 to 55-78 as amended by ASU 2016-02 [F] | Outcome `FINANCING` (asset stays; liability accreted, JET-11 pattern), `LEASE` (routed out after allocation, PT-09), `RIGHT_OF_RETURN` (ALG-06) or `SALE` | REC, ONB |
| POL-234 | `scope.collaboration_808` | When are transactions with a collaborative-arrangement participant revenue under Topic 606? | `UNIT_OF_ACCOUNT_CUSTOMER_TEST` | FORCED | n/a (no IFRS equivalent) | n/a | C | K | JDG | ASU 2018-18: 606 applies when the participant is a customer for a distinct good or service; presentation with 606 revenue is precluded otherwise [F] | Non-customer participant units are routed out and never posted to `REVENUE` | ONB |

---

## 2. Algorithms

Every algorithm operates on exact rationals and posts rounded amounts only through ALG-01. Every CHK in this section was recomputed by `.scratch/design-ra-policies/verify_checks.py` on 2026-09-12 and must be reproduced exactly by an answer key. The rev 1.1 checks (CHK-138, CHK-140 to CHK-145, and the JET-07c and JET-07d split of CHK-029 and CHK-060) were recomputed by `.scratch/design-fix-policies/verify_checks.py` on 2026-09-12. The rev 1.2 checks (the CHK-006 rows S2-WARRANTY-OWN, S5-EX63-OWNSSP and S12-FRANCHISOR-OWN, CHK-053, both CHK-136 rows, the CHK-137 presentation, new CHK-084, the POL-076 test (c) figures and the CHK-110 column) were recomputed by `.scratch/b3-fix-policies/verify_checks_b3.py` on 2026-09-12 and agree with the answer keys that carry them. The rev 1.3 figures (the JET-09c floor, the month counts of CHK-136 and CHK-137, and the FASB Example 26 accretion of JET-11) were recomputed by `.scratch/b4-numeric-residue/verify_b4.py` on 2026-09-12.

### 2.1 ALG-01 Rounding (D-11; POL-001 to POL-003)

#### 2.1.1 Quantisation

For an exact amount x (a `Fraction`) and currency exponent e (ISO 4217 table: JPY 0, USD 2, BHD 3, CLF 4):

- `round(x) = sign(x) × ⌊|x| × 10^e + 1/2⌋ ÷ 10^e`.
- Implemented on integer numerator and denominator (research 06 §7.3). Floats are trapped (D-11).
- Stored as `NUMERIC(24,4)`; the value always has at most e decimals.

#### 2.1.2 Largest-remainder apportionment

Input: a total T in minor units (integer, any sign); weights w_i ≥ 0 (`Fraction`); unique keys k_i (`pob_line_key` or the identifier of the object being split).

1. If any w_i < 0: error `NEGATIVE_WEIGHT`. If Σw = 0: error `TOTAL_WEIGHT_ZERO` (POL-077).
2. s = sign(T); t = |T|.
3. exact_i = t × w_i ÷ Σw; base_i = ⌊exact_i⌋; r = t − Σ base_i (0 ≤ r < n).
4. Order i by (exact_i − base_i descending, w_i descending, k_i ascending by Unicode code point). Add 1 to base_i for the first r entries.
5. Result_i = s × base_i.

Guarantees: Σ result = T; |result_i − s × exact_i| < 1 minor unit; w_i = 0 gives 0; the result is independent of input order.

Uses: allocation across POBs (weights = resolved SSP); targeted VC within a subset (SSP within the subset). When fixed consideration and targeted VC are allocated on different bases, the posted allocation is one apportionment of the transaction price over the exact quotas (D-76; `_coverage/answer-keys-topics:OQ-AKT-04`); modification pools (ALG-04 weights); reclass attribution (POL-121 weights); FX layer derecognition under `PRO_RATA` (layer balances); intercompany splits (configured ratios); portfolio results to contracts (PT-06).

#### 2.1.3 Cumulative schedules

For a POB with exact allocation X (the exact rational quota before apportionment), posted allocation A (its §2.1.2 result, minor units) and exact cumulative progress f_t ∈ [0, 1] at the end of period t:

- Exact cumulative revenue E_t = X × f_t.
- Posted cumulative C_t = round(E_t), bounded to lie between 0 and A (between A and 0 for a negative allocation). When f_t = 1, C_t = A.
- Period amount a_t = C_t − C_(t−1); C_0 = 0, or the posted cumulative at cutover (POL-210).
- When the allocation changes (transaction-price change, modification), X and A take their new values; the difference between the new C and the posted cumulative is the catch-up (ALG-10).
- [J] D-11 rounds the cumulative exact amount, and D-11a confirms this section as published. Rounding the posted allocation first, round(A × f_t), would create half-minor-unit ties and one-cent catch-ups on POBs a modification did not change (`docs/reviews/objections-ra-deviations.md` O-3). Aligning the completion step to A keeps POB and contract totals exactly equal to the allocation. The alignment is at most one minor unit, because both round(X) and A lie within one minor unit of X. No accumulated rounding is carried to the last period, so this is not a plug.

#### 2.1.4 Numeric checks

| CHK | Input | Expected |
|---|---|---|
| CHK-001 | USD 100.00; three POBs, equal SSP; keys POB-001 to POB-003 | 33.34 / 33.33 / 33.33 |
| CHK-002 | Golden GT-01 to GT-03 (Contract 1: TP 1,300, SSP 500 / 368 / 150 / 1,000; Contract 2: TP 900, SSP 612 / 408 / 150 / 0; Contract 4: TP 950, SSP 612 / 544 / 150 / 0) | Exact at 4 dp equals golden (322.1011 / 237.0664 / 96.6303 / 644.2022; 470.7692 / 313.8462 / 115.3846 / 0; 445.1761 / 395.7121 / 109.1118 / 0). Posted: 322.10 / 237.07 / 96.63 / 644.20; 470.77 / 313.85 / 115.38 / 0.00; 445.18 / 395.71 / 109.11 / 0.00 |
| CHK-003a | JPY 10,000; three equal weights | 3,334 / 3,333 / 3,333 |
| CHK-003b | BHD 100.000; weights 1 and 2 | 33.333 / 66.667 |
| CHK-003c | USD −100.00; three equal weights | −33.34 / −33.33 / −33.33 |
| CHK-003d | 3 minor units; weights 1, 2, 3 (remainders 1/2, 0, 1/2) | 0 / 1 / 2 (the tie is broken by the larger weight) |
| CHK-004 | USD 35,000.00 ratable over 24 equal months (research 04 S2-EX11 re-baselined, C-07) | Months 1, 2, 3: 1,458.33 / 1,458.34 / 1,458.33; month-23 cumulative 33,541.67; month 23: 1,458.34; month 24: 1,458.33 (not 1,458.41) |
| CHK-005 | USD 100.00 over three equal months | 33.33 / 33.34 / 33.33 |
| CHK-007 | POB with exact allocation 237.066402… (posted 237.07), quantity 2; one unit delivered in P1, the second in P2, no modification | P1: round(118.533201) = 118.53 (not round(237.07 × 0.5) = 118.54). P2: cumulative aligned to 237.07; period 118.54 |

#### 2.1.5 Research 04 answer keys re-baselined to cumulative rounding (closes C-07)

CHK-006. Research 04 keys that plug the last period are replaced by these values. Periods are numbered from the first period of the schedule. Rev 1.2 re-baselines the rows S2-WARRANTY-OWN, S5-EX63-OWNSSP and S12-FRANCHISOR-OWN to D-11a: rev 1.1 rounded the posted allocation, round(A × f_t), where ALG-01 §2.1.3 rounds the exact allocation, round(X × f_t) (D-76; `_coverage/answer-keys-fx-entity-books:OQ-AK-02`). The other rows have X = A and are unchanged.

| Research 04 key | Research 04 value | Engine value (ALG-01 §2.1.3) |
|---|---|---|
| S2-EX11-CASEA-OWNPRICES (35,000.00 over 24 months) | months 2 to 23: 1,458.33; month 24: 1,458.41 | 1,458.34 in months 2, 5, 8, 11, 14, 17, 20 and 23; 1,458.33 in the other 16 months. `revenue_m24` = 1,458.33; `revenue_m1` = 106,458.33 and `contract_liability_end_m1` = 33,541.67 unchanged |
| S2-WARRANTY-OWN (954.55 over months 13 to 24) | months 13 to 23: 79.55; month 24: 79.50 | X = 10,500 × 1,000 ÷ 11,000 = 954.5454…: 79.55 in months 13, 15, 17, 19, 21, 23 and 24; 79.54 in months 14, 16, 18, 20 and 22. `revenue_month_24` = 79.55 |
| S5-EX63-OWNSSP (custody 29,126.21 over 3 years) | 9,708.74 / 9,708.74 / 9,708.73 | X = 1,000,000 × 30,000 ÷ 1,030,000 = 29,126.2135…: 9,708.74 / 9,708.74 / 9,708.73 (equal to research 04) |
| S8-CONTRACT-COSTS ex2 (commission 10,000.00 over 7 years) | years 1 to 6: 1,428.57; year 7: 1,428.58 | 1,428.58 in year 4; 1,428.57 in the other years. `commission_amortisation_y7` = 1,428.57 |
| S12-FRANCHISOR-OWN (licence 36,363.64 over 10 years) | years 1 to 9: 3,636.36; year 10: 3,636.40 | X = 50,000 × 40,000 ÷ 55,000 = 36,363.6363…: 3,636.37 in years 2, 5, 7 and 10; 3,636.36 in the other years. `licence_year10` = 3,636.37 |
| S5-UPFRONTFEE-OWN option B (fee 3,000.00 over 36 months) | 83.33 monthly | 83.34 in months 2, 5, 8, …, 35 (every third month from month 2); 83.33 otherwise. `year1_revenue` 13,000.00 and `liability_end_year1` 2,000.00 unchanged |
| S6-COMBINED-MOD-OWN (support 70,000.00 over 36 months) | 1,944.44 monthly, last month absorbs | cumulative rounding of 70,000.00 × k ÷ 36: 1,944.44 in 20 months and 1,944.45 in 16 months; `support_monthly` asserts month 1 only (1,944.44) |
| S6-EX5-CASEB (8,400.00 over 90 units) | 93.33 per unit, last unit absorbs | 93.33 / 93.34 / 93.33 repeating; 5,600.00 after 60 units; 8,400.00 after 90 units (CHK-028) |
| S10-DISCLOSURES `rollforward_ex21` | Year 1 revenue 122,499.96; closing 17,500.04; over time 34,999.96 | Year 1 revenue 122,500.00; closing contract liability and RPO 17,500.00; over time 35,000.00; Year 2 revenue from opening liability 17,500.00 |

Legacy note: legacy JE reports round each line to 4 dp and then round grouped lines to 2 dp with binary-float half-even and no plug (legacy 06 §3.3). The engine does not reproduce this. The two unbalanced legacy months (May and October 2023, GT-17) are corrected values in `docs/legacy/DEVIATIONS.md`.

### 2.2 ALG-02 Contract position and netting (D-12, D-23; POL-120, POL-121)

**Unit.** (combination group c, contracting legal entity e, book b), in the contract's transaction currency. Performing entities that do not bill hold no contract balances (ALG-07).

**Definition.** `net_position(c, e, b, t)` = Σ credits − Σ debits posted to the `CONTRACT_LIABILITY` control role for (c, e, b) through the end of period t, excluding JET-06 reclass lines and their reversals. The opening net position established at onboarding (`OPENING_BALANCE_ESTABLISHED`; POL-210, PT-11) is included. Section 2.3 lists every template that touches the control role. Interest accreted under JET-11 posts to the control role, so it is part of the carrying amount and therefore of NP (D-76 ruling on financing interest, `ENGINE_SPEC_B:OQ-B-09`; CHK-137). When no refund, receivable-contra, intercompany or financing flows exist, this equals D-12: cumulative consideration billed or unconditionally due − cumulative revenue recognised.

**Excluded balances** (never posted to the control role): `REFUND_LIABILITY`, `RETURN_ASSET`, `DEPOSIT_LIABILITY`, `CUSTOMER_INCENTIVE_ASSET`, `CONSIDERATION_PAYABLE`, `SALES_TAX_PAYABLE`, `NONCASH_CONSIDERATION_ASSET`, `ACCOUNTS_RECEIVABLE`, `RECEIVABLE_CONTRA`, the clearing roles `BILLING_CLEARING` and `CONTRACT_COST_CLEARING`, `COST_OF_REVENUE`, and the cost, loss and warranty roles.

**Steps at each period end t:**

1. Compute NP = net_position(c, e, b, t) in minor units.
2. If NP ≥ 0: presented contract liability = NP; contract asset = unbilled receivable = 0; no reclass.
3. If NP < 0: D = −NP. For each POB p of (c, e, b): R_p = cumulative revenue relief attributed to p plus the net JET-11 accretion attributed to p (JET-11a debits less JET-11b credits; a financing schedule's accretion is apportioned by ALG-01 over the POBs that carry the financing adjustment, weighted by posted allocation) (rev 1.2; D-76; `_coverage/answer-keys-industries:OQ-AKI-12`); B_p = cumulative invoiced consideration attributed to p (invoice lines that reference p; unreferenced invoice and credit-memo amounts are attributed by ALG-01 over the allocations of the POBs the document covers, per document, on the absolute amount, with the sign applied after apportioning; D-76, `_coverage/answer-keys-fx-entity-books:OQ-AK-03`). U = Σ over POBs whose right is `UNCONDITIONAL` (ALG-03) of max(0, R_p − B_p). Unbilled receivable UR = min(D, U); contract asset CA = D − UR.
4. JET-06 posts on the last day of t: Dr `UNBILLED_RECEIVABLE` UR; Dr `CONTRACT_ASSET` CA; Cr `CONTRACT_LIABILITY` D. The reversal is dated the first day of t + 1.
5. Attribution to account strings (POL-121):
   - `POB_DEBIT_POSITIONS`: UR is apportioned over unconditional POBs with weights max(0, R_p − B_p); CA over conditional POBs with the same weights. If all conditional weights are 0 (for example a debit caused by a credit memo or a refund liability), CA is apportioned over the conditional POBs by posted allocation; if there is no conditional POB or those allocations sum to 0, over every POB of (c, e, b) by posted allocation; if those also sum to 0, by resolved SSP, which POL-077 makes positive. Each debit line has a paired `CONTRACT_LIABILITY` credit line on the same POB string.
   - `CUMULATIVE_SSP_DELIVERED` (parity): D is apportioned over non-VC POBs by the first weight set whose sum is not 0, in this order: cumulative SSP delivered; cumulative revenue; posted allocation; resolved SSP (positive by POL-077). Each POB's share is posted to UR or CA by its ALG-03 class (both roles map to one account under the preset). Rev 1.1 confirms the first three steps as `docs/legacy/DEVIATIONS.md` DEV-058 assumes (DEVIATIONS:OQ-D8). The fourth step only makes the chain total: it applies when every non-VC posted allocation is 0, so it changes no DEV-058 expectation.
6. Invariant: presented CL − CA − UR = NP for every (c, e, b, t).

**Numeric checks.**

| CHK | Input | Expected |
|---|---|---|
| CHK-010 | One contract, one entity. P1 time-and-materials (unconditional): R 3,000.00, B 0. P2 milestone (conditional): R 10,000.00, B 4,000.00. P3 conditional: R 1,000.00, B 5,000.00 | NP = −5,000.00; U = 3,000.00; UR 3,000.00; CA 2,000.00; CA attributed entirely to P2 under `POB_DEBIT_POSITIONS`; JET-06: Dr UR 3,000.00, Dr CA 2,000.00 / Cr CL 5,000.00 |
| CHK-011 | Golden GT-06 (parity). Contract 2 at 2023-03-31: posted revenue POB #1 58.85, POB #3 46.15; billing 0; cumulative SSP delivered 76.5 and 60 | NP = −105.00; reclass 58.85 (POB #1) and 46.15 (POB #3); March movement Dr 15002 46.15 / Cr 5003 46.15 (legacy 02 TC-delivery-04) |
| CHK-012 | Research 04 S9-PRESENTATION: contract X licence (conditional) R 60,000.00, B 10,000.00; services R 20,000.00, B 40,000.00; contract Y (not combined) liability 5,000.00 | X: NP = −30,000.00, CA 30,000.00, CL 0.00. Y: CL 5,000.00, not netted with X |

### 2.3 JET templates: posting patterns per event type (D-13, D-14, D-14a, D-16)

**Common rules.**

| # | Rule |
|---|---|
| R1 | A template produces journal lines for one (entity, book, currency, period). Each line pair derives from one rounded amount; when one debit has several credits, the credits are apportioned from the debit total by ALG-01 (D-16) |
| R2 | The posting period is the period containing the event's effective date if that period is open; otherwise the first open period, with `origin_period` set (D-19, ALG-09) |
| R3 | Dimensions on every line: contract (combination group), POB (where applicable), product or revenue category (drives the D-14 mapping), counterparty entity (intercompany roles only), `reason_code`, `source_event_id`, `calc_run_id` |
| R4 | A negative amount swaps the Dr and Cr roles (section 0.9) |
| R5 | Under POL-005 = `GROSS`, every template except JET-15 posts. Under `DELTA`, JET-15 posts in addition |
| R6 | Every template below applies to every enabled book using that book's resolved policies. The `LEGACY` book posts only its own pre-standard lines (JET-15) |
| R7 | Research 04 journal tables are illustrative (section 0.8). Answer keys assert the lines below |
| R8 | Every engine line with role `BILLING_CLEARING` carries a `clearing_purpose` from table 0.8-A |
| R9 | Templates are keyed to 04 E-03 `contract_event_type` literals and, for time-driven amounts, to close-run passes named by 04 E-31 `subledger_posting_kind` (05 RCP-08). Tables 2.3-A and 2.3-B are normative (B1-005) |

Table 2.3-A: event names used in rev 1.0 and their 04 E-03 literals (B1-005)

| Rev 1.0 name | E-03 literal or close-run pass | Note |
|---|---|---|
| `ContractActivated` | `CONTRACT_ACTIVATED` | |
| `DeliveryRecorded`, `ControlTransferred` | `DELIVERY_RECORDED` | E-03 records a control transfer as a delivery |
| `ProgressUpdated` | `PROGRESS_RECORDED`, `MILESTONE_ACHIEVED`, or `COST_INCURRED` with payload `purpose` `PROGRESS_INPUT` | By measure of progress (POL-091) |
| `UsageReported`, `RoyaltyReportReceived` | `USAGE_REPORTED`; a royalty statement sets payload `is_royalty_statement` | A royalty statement replaces the accrued `ROYALTY_ACCRUAL` estimate |
| `RoyaltyEstimateAccrued` | `ESTIMATE_CHANGED` for E-09 `ROYALTY_ACCRUAL` | |
| `EstimateVersionApproved` | `ESTIMATE_CHANGED` | Any E-09 kind |
| `VcResolved` | `ESTIMATE_CHANGED` for E-09 `VARIABLE_CONSIDERATION` | A resolution is a final estimate version (D-20) |
| `InvoiceIssued` | `BILLING_RECORDED` | |
| `CreditMemoIssued` | `CREDIT_MEMO_RECORDED` | |
| `CashReceived` | `PAYMENT_RECEIVED` | |
| `ContractCriteriaMet` | `CONTRACT_CRITERIA_MET` | |
| `ModificationApproved` | `CONTRACT_AMENDED`; `CONTRACT_TERMINATED` for a termination (PT-03) | |
| `OptionExercised` | `MATERIAL_RIGHT_EXERCISED` | |
| `OptionExpired` | `MATERIAL_RIGHT_EXPIRED` | Appended by the time trigger of 05 RCP-10 |
| `ReturnReceived` | `RETURN_RECORDED` | |
| `BusinessCombinationOnboarded` | `OPENING_BALANCE_ESTABLISHED` with payload `reason` `BUSINESS_COMBINATION` | Engine state only; no journal lines (PT-11) |
| Time elapsed at period end; return-window expiry; amortisation, impairment and financing accretion at period end | Close run, E-31 pass `CLOSE_RELEASE` (05 RCP-08) | No event is appended |
| Period-end netting reclass | Close run, E-31 pass `NETTING_RECLASS` | |
| Period-end FX remeasurement | Close run, E-31 pass `FX_REMEASUREMENT` | |

Table 2.3-B: triggers per template

| Template | Triggers |
|---|---|
| JET-01 | `CONTRACT_ACTIVATED` |
| JET-01b | `PAYMENT_RECEIVED` and `BILLING_RECORDED` while the contract is `NOT_A_CONTRACT`; `CONTRACT_TERMINATED` with payload `refund_amount` while `NOT_A_CONTRACT` (refund); `CONTRACT_CRITERIA_MET`; the 606-10-25-7 evaluation on every event appended while `NOT_A_CONTRACT`, at the term end of a `TIME_ELAPSED` obligation and at `event_c_met_on` (dated points posted in the `CLOSE_RELEASE` pass; D-91, rev pending ENA-2b) |
| JET-02 | `DELIVERY_RECORDED`; `PROGRESS_RECORDED`; `MILESTONE_ACHIEVED`; `COST_INCURRED` (`PROGRESS_INPUT`); `USAGE_REPORTED`; `ESTIMATE_CHANGED` (`ROYALTY_ACCRUAL`); `CLOSE_RELEASE` (time elapsed) |
| JET-03 | `BILLING_RECORDED`; `CREDIT_MEMO_RECORDED` |
| JET-04 | `ESTIMATE_CHANGED`; `USAGE_REPORTED` royalty statements; `BILLING_RECORDED` and `CREDIT_MEMO_RECORDED` (04b and 04c targets); `CLOSE_RELEASE` (return-window expiry) |
| JET-05 | `CONTRACT_AMENDED`; `CONTRACT_TERMINATED` |
| JET-06 | `NETTING_RECLASS` |
| JET-07 | `DELIVERY_RECORDED` (07a to 07c at transfer); `RETURN_RECORDED` (07d, and 07b through JET-04b); `ESTIMATE_CHANGED` (`RETURN_RATE`); `CLOSE_RELEASE` (07c at period end and at window expiry) |
| JET-08 | `MATERIAL_RIGHT_EXERCISED`; `MATERIAL_RIGHT_EXPIRED` |
| JET-09 | `COST_INCURRED` (`COST_TO_OBTAIN`, `COST_TO_FULFILL`) for 09a and 09a′; `CLOSE_RELEASE` for 09b to 09d; `CONTRACT_TERMINATED` for 09e; `COST_INCURRED` (`COST_TO_OBTAIN` with payload `cost_adjustment` `CLAWBACK`) for 09f |
| JET-10 | `FX_REMEASUREMENT`; `BILLING_RECORDED` and `PAYMENT_RECEIVED` for settlement remeasurement (ALG-08); `CREDIT_MEMO_RECORDED` for 10c; for 10d, `FX_REMEASUREMENT` and every settlement of a monetary liability: `CREDIT_MEMO_RECORDED` and `RETURN_RECORDED` (refund liability), `CLOSE_RELEASE` (return-window expiry), `CONTRACT_CRITERIA_MET`, `CONTRACT_TERMINATED` and the 606-10-25-7 derecognition (deposit liability), and the settlement of a consideration-payable promise (ALG-08 §2.9.1) |
| JET-11 | `CLOSE_RELEASE` (accretion); the JET-02 triggers for revenue at transfer |
| JET-12 | `ESTIMATE_CHANGED` (`EAC`); `COST_INCURRED`; `CLOSE_RELEASE` |
| JET-13 | The JET-02 triggers, when the performing entity differs from the contracting entity |
| JET-14 | `CONTRACT_ACTIVATED` and `CONTRACT_AMENDED` (payment promised); `BILLING_RECORDED` and the JET-02 triggers (release against revenue); `ESTIMATE_CHANGED` (share-based consideration, PT-10) |
| JET-15 | `PRE_STANDARD_REVENUE_RECORDED` |
| JET-16 | `DELIVERY_RECORDED` (accrual); `COST_INCURRED` with payload `purpose` `WARRANTY_CLAIM` (claim release; OQ-13, resolved by D-76) |
| JET-17 | The JET-02 triggers when the right to the noncash consideration becomes unconditional; the noncash form of `PAYMENT_RECEIVED` (receipt; OQ-13, resolved by D-76) |

Events without a row post no lines of their own. `CONTRACT_BOOKED`, `COLLECTIBILITY_ASSESSED`, `HOLD_APPLIED`, `HOLD_RELEASED`, `MEMO_UPDATED`, `SIGNIFICANT_CHANGE_FLAGGED`, `COMBINATION_CHANGED`, `REGROUPED`, `LINE_ATTRIBUTES_CHANGED`, `EVENT_VOIDED` and `CONTRACT_VOIDED` post any difference they cause through the templates above as cumulative target minus posted (05 RCP-06). `OPENING_BALANCE_ESTABLISHED` establishes engine state and posts nothing (PT-11). `MANUAL_ADJUSTMENT_APPLIED` posts the approved adjustment's own lines (E-31 `MANUAL_ADJUSTMENT`).

#### JET-01 Contract activation (`CONTRACT_ACTIVATED`)

| Mode | Lines |
|---|---|
| `ERP` and `ENGINE` | None. Activation pins SSP, policy and rate versions, allocates and builds schedules. Postings arise only from later events or from JET-14 and JET-17 when those facts exist at inception |

#### JET-01b Step 1 deposits and transition (POL-012, POL-013, POL-128)

| Event | Dr | Cr | Amount |
|---|---|---|---|
| `PAYMENT_RECEIVED` while the contract is `NOT_A_CONTRACT` | `BILLING_CLEARING` (`clearing_purpose` `UNAPPLIED_CASH`) | `DEPOSIT_LIABILITY` | Receipt |
| `CONTRACT_CRITERIA_MET` (to `ACTIVE`) | `DEPOSIT_LIABILITY` | `CONTRACT_LIABILITY` | Deposit balance; revenue for performance to date then posts through JET-02 in the same period (reason `STEP1_MET`) |
| A 606-10-25-7 condition met while `NOT_A_CONTRACT` (per book, POL-012), evaluated on every event appended to the contract and at the dated points of ENGINE_SPEC S02-R-07 (posted in the `CLOSE_RELEASE` pass) | `DEPOSIT_LIABILITY` | `REVENUE` | Nonrefundable consideration received, up to the stated consideration of the lines, attributed to obligations by ENGINE_SPEC_B S14-R-25 (D-91; rev pending END-4b) |
| `CONTRACT_TERMINATED` with payload `refund_amount` while the contract is `NOT_A_CONTRACT` | `DEPOSIT_LIABILITY` | `BILLING_CLEARING` (`clearing_purpose` `UNAPPLIED_CASH`) | `refund_amount`, limited to the deposit balance; the 606-10-25-7 evaluation of the row above then applies to any remaining nonrefundable balance (rev 1.2; 05 EMOD-12) |
| `BILLING_RECORDED` (ERP invoice ingested) for a `NOT_A_CONTRACT` contract | none | none | Finding `INVOICE_ON_NOT_A_CONTRACT`, severity `WARNING` (04 table 15.4-C; confirmed in rev 1.2 under the D-76 ruling on 04:OQ-10); nothing posts |

CHK-021 (research 04 S1-EX1-CASEB-C, Case C): receipts of 20.00 in months 1 to 6 build `DEPOSIT_LIABILITY` 120.00 (100.00 at month 5). At the end of month 6: Dr `DEPOSIT_LIABILITY` 120.00 / Cr `CONTRACT_LIABILITY` 120.00, then JET-02 Dr `CONTRACT_LIABILITY` 120.00 / Cr `REVENUE` 120.00. Closing deposit liability 0.00, contract liability 0.00, revenue 120.00.

#### JET-02 Revenue recognition (`DELIVERY_RECORDED`, `PROGRESS_RECORDED`, `MILESTONE_ACHIEVED`, `COST_INCURRED`, `USAGE_REPORTED`, `ESTIMATE_CHANGED`; close run `CLOSE_RELEASE`)

| Case | Dr | Cr | Amount |
|---|---|---|---|
| Principal, contracting entity = revenue entity | `CONTRACT_LIABILITY` | `REVENUE` | Period amount a_t per POB (ALG-01 §2.1.3) |
| Agent (POL-030) | `CONTRACT_LIABILITY` | `REVENUE` (retained portion) and `BILLING_CLEARING` (`clearing_purpose` `AP_SUPPLIER`) | Gross period amount. Gross relief = billed consideration attributable to the delivered units of the agent POB; supplier portion = gross − retained revenue, floored at 0, split by ALG-01 on the cumulative gross (D-76; `_coverage/answer-keys-industries:OQ-AKI-05`) |
| Uninstalled materials (POL-091; 606-10-55-21(b)) | `CONTRACT_LIABILITY` | `REVENUE` | Revenue equal to the cost of the uninstalled materials whose control has transferred (`COST_INCURRED` with `is_uninstalled_material`), at zero margin. The ERP posts the materials cost; the engine posts no `COST_OF_REVENUE` line (rev 1.2; D-76 ruling on `POLICIES:OQ-15`) |
| Revenue entity ≠ contracting entity (POL-170) | JET-13 replaces this template | | |

Both billing modes post JET-02.

CHK-022 (golden GT-04, GT-05; legacy 06 TC-JE-01), January 2023, `ERP` mode. Contract 1: Dr 21001 `CONTRACT_LIABILITY` 295.69 / Cr 5001 128.84, Cr 5002 118.53, Cr 5003 48.32 (a_t from exact revenue 128.840436, 118.533201, 48.315164). Contract 2 (delivery, no billing): Dr 21002 58.85 / Cr 5001 58.85, then JET-06 Dr 15002 58.85 / Cr 21002 58.85. The summarised batch equals legacy: Dr 15002 58.85 / Cr 5001 58.85, with 21002 netting to zero.

#### JET-03 Billing and credit memos (`BILLING_RECORDED`, `CREDIT_MEMO_RECORDED`; POL-004, POL-045, POL-123)

| Mode | Dr | Cr | Amount |
|---|---|---|---|
| `ERP` | none | none | Ingested only: position (ALG-02), reconciliation (research 07 RC-01, RC-02), FX layers (ALG-08) |
| `ENGINE`, invoice | `ACCOUNTS_RECEIVABLE` | `CONTRACT_LIABILITY` and `SALES_TAX_PAYABLE` | Invoice total; tax lines excluded under POL-045. Dated at the unconditional date (POL-123) |
| `ENGINE`, credit memo | `CONTRACT_LIABILITY` and `SALES_TAX_PAYABLE` | `ACCOUNTS_RECEIVABLE` | Credit memo total |

CHK-023 (research 04 S3-SALESTAX-OWN, `ENGINE` mode): Dr `ACCOUNTS_RECEIVABLE` 1,080.00 / Cr `CONTRACT_LIABILITY` 1,000.00, Cr `SALES_TAX_PAYABLE` 80.00; JET-02 Dr `CONTRACT_LIABILITY` 1,000.00 / Cr `REVENUE` 1,000.00. The gross-receipts tax is not an engine posting.

CHK-024 (research 04 S9-PRESENTATION Example 38, `ENGINE` mode). Case A (cancellable): the 31 January invoice is memo-only; on 1 March (cash received) Dr AR 1,000.00 / Cr CL 1,000.00; 31 March JET-02 Dr CL 1,000.00 / Cr REVENUE 1,000.00. Receivable at 31 January 0.00. Case B (noncancellable from 31 January): 31 January Dr AR 1,000.00 / Cr CL 1,000.00; receivable and contract liability 1,000.00 each at 31 January.

#### JET-04 Transaction-price and estimate changes (`ESTIMATE_CHANGED`, `USAGE_REPORTED`, `BILLING_RECORDED`, `CREDIT_MEMO_RECORDED`; close run `CLOSE_RELEASE`; ALG-10)

| Part | Dr | Cr | Amount |
|---|---|---|---|
| 04a Revenue catch-up | `CONTRACT_LIABILITY` | `REVENUE` | Per POB: round(X′_p × f_p) − posted cumulative revenue of p, bounded by the posted allocation A′_p (ALG-01 §2.1.3), where X′_p is the exact allocation after the change (inception basis, or targeted under 32-40) and f_p the progress at the effective date |
| 04b Refund-liability remeasurement (VC elements settled by refund or credit: rebates, price protection, returns, explicit concessions on billed amounts) | `CONTRACT_LIABILITY` | `REFUND_LIABILITY` | ΔRL = RL_target − RL posted, where RL_target is the estimate version's refund of consideration already billed or received: for refund-settled VC elements the `VARIABLE_CONSIDERATION` member `refund_liability_target`, net of credit memos issued by the version date (D-76 ruling on `ENGINE_SPEC_B:OQ-B-07`); for returns ALG-06 step 3 |
| 04c Receivable contra for implicit price concessions (`ENGINE` mode only; E-09 `IMPLICIT_PRICE_CONCESSION`) | `CONTRACT_LIABILITY` | `RECEIVABLE_CONTRA` | ΔRC = RC_target − RC posted, with RC_target = round(B × κ): B = cumulative invoiced consideration of the contract excluding taxes (POL-045), and κ = expected implicit concession ÷ stated consideration, both from the approved estimate version (606-10-32-7). Lines post with 04 E-29 entry kind `RECEIVABLE_CONTRA` (D-76 ruling on `ENGINE_SPEC_B:OQ-B-18`) |

[J] Under `ERP` the billing system owns the receivable and its contra: the engine posts no JET-04c line and ingests the ERP's contra adjustment as `CREDIT_MEMO_RECORDED`, so the position still ties (POL-123). A later fall in expected collection caused by the customer's credit deterioration is a credit loss outside the engine (POL-125; 606-10-55-106 to 55-109), never a change to κ.

CHK-025 (research 04 S3-EX24 volume rebate, `ERP` mode). Q1: JET-02 Dr CL 7,500.00 / Cr REVENUE 7,500.00. Q2: JET-02 for 500 units at the revised unit allocation 90.00: Dr CL 45,000.00 / Cr REVENUE 45,000.00; JET-04a for the 75 Q1 units: Dr REVENUE 750.00 / Cr CL 750.00; JET-04b RL_target 5,750.00: Dr CL 5,750.00 / Cr REFUND_LIABILITY 5,750.00. End of Q2: revenue 51,750.00 (Q2 44,250.00); refund liability 5,750.00; position 57,500.00 − 57,500.00 = 0.

CHK-026 (research 04 S3-EX21-EXTENDED, Year 2): JET-04a catch-up 60,000.00 (bonus now unconstrained × Year 1 progress 40%); JET-02 progress revenue 1,062,000.00; Year 2 revenue 1,122,000.00; JET-06 contract asset 124,000.00.

CHK-138 (research 04 S1-EX2, FASB Example 2, `ENGINE` mode): 1,000 units transferred and invoiced 1,000,000.00; expected entitlement 400,000.00, so κ = 0.60. JET-03 Dr ACCOUNTS_RECEIVABLE 1,000,000.00 / Cr CL 1,000,000.00; JET-02 Dr CL 400,000.00 / Cr REVENUE 400,000.00; JET-04c Dr CL 600,000.00 / Cr RECEIVABLE_CONTRA 600,000.00. Revenue 400,000.00; net receivable 400,000.00; contract liability 0.00; no credit-loss line.

#### JET-05 Modifications (`CONTRACT_AMENDED`, `CONTRACT_TERMINATED`; ALG-04)

| Part | Dr | Cr | Amount |
|---|---|---|---|
| 05a Cumulative catch-up on partially satisfied non-distinct POBs (or all POBs under the parity retrospective template) | `CONTRACT_LIABILITY` | `REVENUE` | ALG-04 step 6 |
| 05b Price change attributed to satisfied performance, settled through future pricing (POL-104) | `REVENUE` | `CONTRACT_LIABILITY` | Attributed amount, apportioned to satisfied POBs by inception allocation |
| 05c Price change attributed to satisfied performance, settled by credit memo or refund | `REVENUE` | `REFUND_LIABILITY` | Attributed amount; when the credit memo is ingested, JET-04b brings RL_target to 0 |
| Reallocation of remaining allocations | none | none | Schedules only |

The settlement mode recorded on the modification (04 T-CON-06; D-76 ruling on `ENGINE_SPEC:OQ-A-18`) selects 05b (settled through future pricing, the default) or 05c (settled by credit memo or refund).

CHK-027, posting view (research 04 S6-EX8): Dr CL 91,463.41 / Cr REVENUE 91,463.41 at the modification date; with no billing, JET-06 contract asset 691,463.41.

CHK-028, posting view (research 04 S6-EX5-CASEB, `ENGINE` mode): 05b Dr REVENUE 900.00 / Cr CL 900.00; units 1, 2 and 3 of the 90 remaining units post 93.33, 93.34 and 93.33 (JET-02, cumulative rounding of 8,400.00); contract liability 1,300.00 after 60 units and 0.00 after 90 units; total revenue for the 90 units 8,400.00.

#### JET-06 Period-end netting reclass and reversal (ALG-02)

| Date | Dr | Cr | Amount |
|---|---|---|---|
| Last day of period t | `UNBILLED_RECEIVABLE`; `CONTRACT_ASSET` | `CONTRACT_LIABILITY` | UR and CA from ALG-02 step 3, attributed by POL-121 |
| First day of period t + 1 | `CONTRACT_LIABILITY` | `UNBILLED_RECEIVABLE`; `CONTRACT_ASSET` | Exact reversal (`reason_code = RECLASS_REVERSAL`) |

Both modes post JET-06. The reversal is posted even if period t + 1 has no other activity. CHK-010 to CHK-012.

#### JET-07 Returns (ALG-06)

| Part | Dr | Cr | Amount |
|---|---|---|---|
| 07a Revenue net of expected returns | via JET-02 at the POB allocation after the targeted TP reduction | | |
| 07b Refund liability | via JET-04b | | |
| 07c Return asset recognition and remeasurement | `RETURN_ASSET` | `COST_OF_REVENUE` | ΔRA = RA_target − (RA posted − the 07d amount of the same event); RA_target = expected units still to be returned × carrying cost per unit − expected recovery costs (606-10-55-27) |
| 07d Return asset derecognised when goods come back | `BILLING_CLEARING` (`clearing_purpose` `INVENTORY`) | `RETURN_ASSET` | On `RETURN_RECORDED`: round(max(0, k − c_rec) × min(units returned, E before the return)) (ALG-06 step 4). The inventory subledger records the goods received against the clearing |

Entry kinds (04 E-29): JET-07c and JET-07d lines post with entry kind `RETURN_ASSET` (rev 1.2; ENGINE_SPEC_B table 14-A). Parts 07a and 07b post through JET-02 and JET-04b with their own entry kinds.

CHK-029, posting view (research 04 S3-EX22, `ERP` mode). Transfer: ERP Cr CL 10,000.00; JET-02 Dr CL 9,700.00 / Cr REVENUE 9,700.00; JET-04b Dr CL 300.00 / Cr RL 300.00; JET-07c Dr RA 180.00 / Cr COST_OF_REVENUE 180.00. Two units returned and refunded: ERP credit memo Dr CL 200.00; expected remaining returns 1: JET-04b Dr RL 200.00 / Cr CL 200.00; JET-07d Dr BILLING_CLEARING (INVENTORY) 120.00 / Cr RA 120.00. Window expires: JET-04a Dr CL 100.00 / Cr REVENUE 100.00; JET-04b Dr RL 100.00 / Cr CL 100.00; JET-07c Dr COST_OF_REVENUE 60.00 / Cr RA 60.00. Final: revenue 9,800.00; RL 0.00; RA 0.00; position 0.00.

#### JET-08 Material-right exercise and expiry (ALG-05; POL-028)

| Event | Dr | Cr | Amount |
|---|---|---|---|
| `MATERIAL_RIGHT_EXERCISED`, `CONTINUATION` | none at exercise | | The option POB is closed; an optioned-goods POB is created with allocation = remaining option allocation + additional consideration; revenue through JET-02 when the goods transfer |
| `MATERIAL_RIGHT_EXERCISED`, `MODIFICATION` | via JET-05 | | ALG-04 pool including the option's remaining allocation and the additional consideration |
| `MATERIAL_RIGHT_EXPIRED` | `CONTRACT_LIABILITY` | `REVENUE` | Remaining option allocation (606-10-55-42); for points programmes POL-055 applies instead |

CHK-051, posting view (research 04 S2-EX49, continuation): at redemption the ERP invoices 30.00 (Cr CL); JET-02 Dr CL 40.71 / Cr REVENUE 40.71. Expiry alternative: Dr CL 10.71 / Cr REVENUE 10.71.

#### JET-09 Contract costs (POL-140 to POL-146)

| Part | Dr | Cr | Amount |
|---|---|---|---|
| 09a Capitalise incremental costs | `COST_TO_OBTAIN_ASSET` | `CONTRACT_COST_CLEARING` | `COST_INCURRED` amount (payload `purpose` `COST_TO_OBTAIN`) when POL-140 does not expense it |
| 09a′ Capitalise fulfilment costs | `COST_TO_FULFILL_ASSET` | `CONTRACT_COST_CLEARING` | `COST_INCURRED` amounts (`COST_TO_FULFILL`) of the attested cost pool (POL-146) |
| 09b Amortise | `CONTRACT_COST_AMORTIZATION` | `COST_TO_OBTAIN_ASSET` or `COST_TO_FULFILL_ASSET` | Cumulative rounding of the asset over its period (POL-141, POL-143) |
| 09c Impair | `CONTRACT_COST_IMPAIRMENT` | asset role | min(carrying, max(0, carrying − (remaining expected consideration − remaining direct costs))). The impairment never exceeds the carrying amount, so the asset floors at 0.00; a recoverable amount below zero is a loss-test matter under Subtopic 605-35 (JET-12), not a negative asset (rev 1.3; ADJUDICATION.md R-COST-03; `COST-S8-CONTRACT-COSTS-IMPAIRMENT` checkpoint `end-2028-floor`: carrying 5,000.00, recoverable −115,000.00, impairment 5,000.00). Remaining expected consideration = consideration received and expected for the goods or services to which the asset relates, including consideration from the anticipated renewals and extensions used in the amortisation period (the approved `RENEWAL_EXPECTATION` version), measured on the transaction-price principles without the constraint and adjusted for credit risk, less revenue already recognised. Remaining direct costs include the costs of those anticipated renewals and extensions (340-40-35-3, 35-4 as amended by ASU 2016-20; rev 1.2, D-76 ruling on contract-cost impairment). Remaining direct costs = max(0, the latest `EAC` expected total − costs). Costs are the `PROGRESS_INPUT` costs incurred when such a cost of the related obligations is effective on or before the period end; otherwise costs = cumulative_posted(eac, g), with eac the latest `EAC` expected total effective at the period end and g the related obligations' revenue progress since that version's effective date, so the remaining costs run off with revenue progress (rev 1.4; D-89 L7-6-Q-7; ENGINE_SPEC_B S11-R-09; JE-CHK-131 ASC606 P03 recoverable 12,500.00) |
| 09d Reverse impairment (IFRS book only) | asset role | `CONTRACT_COST_IMPAIRMENT` | min(recoverable, unimpaired carrying) − carrying, if positive (IFRS 15.104) |
| 09e Accelerate on termination (POL-145) | `CONTRACT_COST_AMORTIZATION` | asset role | Carrying amount in excess of the remaining benefit |
| 09f Clawback of a capitalised commission (`COST_INCURRED` with payload `purpose` `COST_TO_OBTAIN` and `cost_adjustment` `CLAWBACK`) | `CONTRACT_COST_CLEARING` | asset role | min(clawback amount, carrying), taken from the oldest capitalisation of the named payee and plan first, with `reason_code = CLAWBACK`; any excess over the carrying amount stays in the ERP. The clawback starts a new amortisation segment (rev 1.2; D-76 ruling on `ENGINE_SPEC_B:OQ-B-11`; ENGINE_SPEC_B S11-R-12) |

CHK-130 (research 04 S8-CONTRACT-COSTS ex2, re-baselined): commission 10,000.00 capitalised (09a: Dr COST_TO_OBTAIN_ASSET 10,000.00 / Cr CONTRACT_COST_CLEARING 10,000.00) and amortised over 7 years (09b): 1,428.57 in years 1, 2, 3, 5, 6 and 7 and 1,428.58 in year 4 (cumulative rounding; research 04 put 1,428.58 in year 7). Fulfilment asset 140,000.00 amortised 20,000.00 a year.

CHK-131 (research 04 S8-CONTRACT-COSTS impairment and expedient): Year 1 09b 10,000.00 and 09c 15,000.00 (carrying 30,000.00 − (100,000.00 − 85,000.00)); Year 2 09b 5,000.00; ASC606 book carrying at the end of Year 2 10,000.00; IFRS15 book 09d reversal 10,000.00 (min(25,000.00, 20,000.00) − 10,000.00), carrying 20,000.00. Expedient case: 1,200.00 commission, 12-month period, commensurate renewal commission, POL-140 `APPLY`: nothing capitalised.

#### JET-10 Foreign-currency remeasurement (ALG-08; POL-163, POL-164)

| Part | Dr | Cr | Amount |
|---|---|---|---|
| 10a Asset position (NP < 0), gain | `CONTRACT_LIABILITY` | `FX_GAIN_LOSS` | Functional carrying of the open asset layers at the closing rate (or at settlement spot on billing) − carrying before remeasurement. Non-reversing. The subsequent JET-06 reclass uses the remeasured functional amount |
| 10a Asset position, loss | `FX_GAIN_LOSS` | `CONTRACT_LIABILITY` | As above, negative difference |
| 10a′ Accounts receivable (`ENGINE` mode) | `ACCOUNTS_RECEIVABLE` or `FX_GAIN_LOSS` | `FX_GAIN_LOSS` or `ACCOUNTS_RECEIVABLE` | Open AR at the closing rate − carrying |
| 10b Monetary contract liability (contract override under POL-163) | `FX_GAIN_LOSS` or `CONTRACT_LIABILITY` | `CONTRACT_LIABILITY` or `FX_GAIN_LOSS` | Open liability at the closing rate − carrying |
| 10c Credit-memo settlement difference (rev 1.2; D-76 ruling on `ENGINE_SPEC_B:OQ-B-14`) | Positive difference: `FX_GAIN_LOSS`; negative: `CONTRACT_LIABILITY` | Positive difference: `CONTRACT_LIABILITY`; negative: `FX_GAIN_LOSS` | For a credit memo of transaction amount m that relieves contract-liability layers: round(m × spot on the memo date) − functional relief of those layers at historical carrying (ENGINE_SPEC_B S12-R-08). Under `ERP` the billing system debits the liability at spot, and this line makes the GL contract liability tie to the layers. Under `ENGINE` the JET-03 credit memo debits `CONTRACT_LIABILITY` at the historical relief and credits `ACCOUNTS_RECEIVABLE` at spot, and the same difference posts to `FX_GAIN_LOSS` within that entry |
| 10d Monetary liabilities: refund liabilities, deposit liabilities and consideration payable (D-25b; POL-164) | Loss: `FX_GAIN_LOSS`; gain: `REFUND_LIABILITY`, `DEPOSIT_LIABILITY` or `CONSIDERATION_PAYABLE` | Loss: `REFUND_LIABILITY`, `DEPOSIT_LIABILITY` or `CONSIDERATION_PAYABLE`; gain: `FX_GAIN_LOSS` | At period end, open balance at the closing rate − functional carrying; at settlement, settled portion at spot − its carrying portion (ALG-08 §2.9.1). Non-reversing; every book (ASC 830-20-35-1; IAS 21.16, 21.23(a)) |

CHK-081, posting view (functional USD, contract EUR, arrears billing, `ERP` mode): 31 Jan JET-02 revenue 1,110.00 (EUR 1,000 at average 1.1100); JET-10a Dr CL 10.00 / Cr FX 10.00 (closing 1.1200); JET-06 Dr CA 1,120.00 / Cr CL 1,120.00. 28 Feb: revenue 1,130.00 (1.1300); JET-10a Dr CL 30.00 / Cr FX 30.00 (EUR 2,000 at 1.1400 = 2,280.00); JET-06 CA 2,280.00. 31 Mar: revenue 1,150.00 (1.1500); ERP invoice EUR 3,000 at spot 1.1600 = 3,480.00; JET-10a settlement Dr CL 50.00 / Cr FX 50.00; position 0. Totals: revenue 3,390.00; FX gain 90.00.

CHK-084 [A] (D-25b; functional USD, contract EUR, `ERP` mode; the same figures in every book).
- **(a) Refund liability.**
  - 1 March 2026: 100 units transfer for EUR 10,000.00 received the same day at spot 1.1000, creating a contract-liability layer of 11,000.00. Expected returns E = 3 at p_ref 100.00; k = c_rec, so there is no return asset. JET-02 revenue EUR 9,700.00 relieves 10,670.00. JET-04b Dr CL 330.00 / Cr REFUND_LIABILITY 330.00 (EUR 300.00 at spot 1.1000, so no recognition difference).
  - 31 March, closing 1.1200: JET-10d Dr FX_GAIN_LOSS 6.00 / Cr REFUND_LIABILITY 6.00 (carrying 336.00).
  - 15 April: two units are returned and credited, EUR 200.00 at spot 1.1500. The settled carrying portion 224.00 is remeasured to 230.00: JET-10d Dr FX_GAIN_LOSS 6.00 / Cr REFUND_LIABILITY 6.00. The ERP credit memo debits CL 230.00 (no contract-liability layer is open, so no JET-10c difference arises). JET-04b Dr REFUND_LIABILITY 230.00 / Cr CL 230.00; carrying 112.00 for EUR 100.00.
  - 30 April, closing 1.0800: JET-10d Dr REFUND_LIABILITY 4.00 / Cr FX_GAIN_LOSS 4.00 (carrying 108.00).
  - 31 May, the window expires; spot, average and closing rates are 1.1000: JET-10d Dr FX_GAIN_LOSS 2.00 / Cr REFUND_LIABILITY 2.00; JET-04b Dr REFUND_LIABILITY 110.00 / Cr CL 110.00; JET-04a Dr CL 110.00 / Cr REVENUE 110.00.
  - Totals: revenue 10,780.00; net FX loss 10.00; refund liability 0.00; contract liability 0.00. Revenue less the FX loss (10,770.00) equals 11,000.00 received less 230.00 refunded.
- **(b) Deposit liability.** EUR 1,000.00 is received on 10 January 2026 at spot 1.1000 while the contract is `NOT_A_CONTRACT` (JET-01b; DEPOSIT_LIABILITY 1,100.00). 31 January, closing 1.1200: JET-10d Dr FX_GAIN_LOSS 20.00 / Cr DEPOSIT_LIABILITY 20.00. `CONTRACT_CRITERIA_MET` on 15 February at spot 1.1300: JET-10d Dr FX_GAIN_LOSS 10.00 / Cr DEPOSIT_LIABILITY 10.00; then JET-01b Dr DEPOSIT_LIABILITY 1,130.00 / Cr CL 1,130.00, creating a contract-liability layer of EUR 1,000.00 at 1,130.00.
- **(c) Consideration payable.** EUR 50,000.00 is promised on 1 June 2026 at spot 1.1000 before related revenue (JET-14; CONSIDERATION_PAYABLE and CUSTOMER_INCENTIVE_ASSET 55,000.00). It is unsettled at 30 June, closing 1.0900: JET-10d Dr CONSIDERATION_PAYABLE 500.00 / Cr FX_GAIN_LOSS 500.00. The incentive asset stays at 55,000.00.

#### JET-11 Significant financing component (POL-046, POL-047)

| Part | Dr | Cr | Amount |
|---|---|---|---|
| 11a Deferred payment: accretion | `CONTRACT_LIABILITY` | `INTEREST_INCOME` | Period change in round(exact cumulative effective-interest income) on the financed balance under POL-047 `compounding` (Subtopic 835-30; ALG-01 §2.1.3). While expected returns exclude the whole consideration nothing accretes; the total interest is then recognised over the remaining months (ENGINE_SPEC S04-R-12a; rev 1.3) |
| 11b Advance payment: accretion | `INTEREST_EXPENSE` | `CONTRACT_LIABILITY` | Period change in round(exact cumulative effective-interest expense) on the advance balance under POL-047 `compounding` |
| Revenue at transfer | via JET-02 | | Cash selling price (deferred) or accreted balance (advance) |

CHK-136 (research 04 S3-EX29, FASB Example 29 re-anchored to 2026). An advance of 4,000.00 is received on 1 January 2026; the asset transfers on 1 January 2028; the entity's borrowing rate is 6%. JET-11b posts Dr INTEREST_EXPENSE / Cr CL. Rev 1.2 re-baselines the default row to `MONTHLY`, with cumulative interest round(4,000.00 × (1.005^m − 1)), and keeps `ANNUAL` as the second row. The advance of 1 January 2026 accretes over the 24 month ends up to the transfer on 1 January 2028 (rev 1.3; R-SFC-02) (D-76 ruling on the significant financing component rate).

| CHK | `compounding` | Year 1 interest | Year 2 interest | Contract liability at the end of year 1 / year 2 | At transfer (JET-02 Dr CL / Cr REVENUE) |
|---|---|---|---|---|---|
| CHK-136 | `MONTHLY` (default) | 246.71 (month 1 20.00; month 12 21.13) | 261.93 (month 24 22.43) | 4,246.71 / 4,508.64 | 4,508.64 |
| CHK-136 | `ANNUAL` | 240.00 (20.00 a month) | 254.40 (21.20 a month) | 4,240.00 / 4,494.40 | 4,494.40 |

CHK-137 (research 04 S3-EX28-CASEB, month 1): JET-02 revenue 848,346.53 (60 instalments of 18,871.00 discounted at 1% a month; instalment k falls at the k-th month end after the transfer on 1 January 2026, so n = k; rev 1.3, R-SFC-02); JET-11a Dr CL 8,483.47 / Cr INTEREST_INCOME 8,483.47; ERP instalment invoice Cr CL 18,871.00; NP = −837,959.00, presented as unbilled receivable 837,959.00 (unconditional right, ALG-03). The accretion is in NP and in R_p of ALG-02 step 3 (D-76), so U = 848,346.53 + 8,483.47 − 18,871.00 = 837,959.00 and the contract asset is 0.00. Without the accretion in R_p, step 3 would present 829,475.53 as unbilled receivable and 8,483.47 as contract asset.

FASB Example 26 with its 90-day return right (rev 1.3; ENGINE_SPEC S04-R-12a and EX-04-H; key `SFC-S3-EX26-RETURN-RIGHT`): 121.00 payable on 31 December 2027 for a product transferred on 1 January 2026, CSP 100.00 at 10% `ANNUAL`. No return history, so expected returns exclude the whole consideration until the window ends on 31 March 2026: until then no revenue, no interest, JET-07c return asset 80.00. The right lapses at the end of 31 March 2026 (rev 1.33; D-87 L6-5-Q-25; ENGINE_SPEC_B S09-R-26): at that date JET-02 recognises 100.00 and JET-07c reverses the return asset. JET-11a then recognises the 21.00 of interest over months 4 to 24 by the inception schedule's weights: 0.95 in April 2026, 8.51 in 2026 and 12.49 in 2027.

#### JET-12 Loss provision (POL-150 to POL-153)

| Part | Dr | Cr | Amount |
|---|---|---|---|
| Increase | `LOSS_EXPENSE` | `LOSS_PROVISION` | Required provision − posted provision, where required = max(0, total expected loss − loss already recognised through margin to date), and the loss already recognised through margin to date = progress-input costs incurred to date (`COST_INCURRED` with `purpose` `PROGRESS_INPUT`) − revenue recognised to date (D-76; `_coverage/answer-keys-industries:OQ-AKI-16`) |
| Release | `LOSS_PROVISION` | `LOSS_EXPENSE` | Negative difference |

CHK-132 (research 04 S7-LOSS-OWN): Year 2 Dr LOSS_EXPENSE 30,000.00 / Cr LOSS_PROVISION 30,000.00 (total loss 100,000.00 − cumulative margin loss 70,000.00); Year 3 release 30,000.00; provision end Years 1 to 3: 0.00 / 30,000.00 / 0.00.

#### JET-13 Intercompany pair (ALG-07; POL-170, POL-171)

| Entity | Dr | Cr | Amount |
|---|---|---|---|
| Contracting entity e_c | `CONTRACT_LIABILITY` | `INTERCOMPANY_DUE_TO` (counterparty e_p) | Period revenue a_t of POBs performed by e_p |
| Performing entity e_p | `INTERCOMPANY_DUE_FROM` (counterparty e_c) | `REVENUE` | Same a_t |

Each entity's batch balances on its own. CHK-070 in ALG-07.

#### JET-14 Consideration payable to a customer (POL-049; PT-10)

| Event | Dr | Cr | Amount |
|---|---|---|---|
| Payment promised before related revenue | `CUSTOMER_INCENTIVE_ASSET` | `CONSIDERATION_PAYABLE` | Promised amount (AP settles the payable) |
| Invoice or revenue for the related purchases | `REVENUE` | `CUSTOMER_INCENTIVE_ASSET` | Invoice × release rate (POL-049) |
| Payment promised after related revenue (606-10-32-27) | `REVENUE` | `CONSIDERATION_PAYABLE` | Promised amount, immediately |
| Share-based consideration payable (606-10-32-25A) | `REVENUE` | `BILLING_CLEARING` (`clearing_purpose` `EQUITY`) | PT-10 |

CHK-133 (research 04 S3-EX32): inception Dr CUSTOMER_INCENTIVE_ASSET 1,500,000.00 / Cr CONSIDERATION_PAYABLE 1,500,000.00; month 1 JET-02 Dr CL 2,000,000.00 / Cr REVENUE 2,000,000.00 and JET-14 Dr REVENUE 200,000.00 / Cr CUSTOMER_INCENTIVE_ASSET 200,000.00. Net revenue 1,800,000.00; incentive asset 1,300,000.00.

#### JET-15 Delta posting against the `LEGACY` book (POL-005, POL-008; D-34)

| Part | Dr | Cr | Amount |
|---|---|---|---|
| Reverse pre-standard revenue booked by the ERP | `PRE_STANDARD_REVENUE` (revenue string of the POB) | `CONTRACT_LIABILITY` (contract string) | L_p = pre-standard revenue of POB p in the period (`LEGACY` book lines) |
| Topic 606 lines | all other templates, unchanged | | |

Equivalently, delta lines = primary-book lines + `LEGACY`-book lines per role; the `LEGACY` book holds the reversal of what the ERP booked (research 06 §11.3; rev 1.4, D-89 L7-6-Q-8). The ERP is assumed to post invoices as Dr AR / Cr `PRE_STANDARD_REVENUE` L and Cr `CONTRACT_LIABILITY` (billing − L); the delta line restores the contract liability to the full billing.

CHK-020 (golden GT-07, January 2023 adjustment JE; legacy 06 TC-JE-02): Contract 1 pre-standard revenue POB #2 66.00, POB #3 88.00. Batch: 21001 Dr 141.69 (295.69 − 154.00); 5002 Cr 52.53 (118.53 − 66.00); 5003 Dr 39.68 (88.00 − 48.32); 5001 Cr 187.69 (Contract 1 128.84 + Contract 2 58.85); 15002 Dr 58.85. Debits 240.22 = credits 240.22.

#### JET-16 Assurance-type warranty (POL-022)

| Event | Dr | Cr | Amount |
|---|---|---|---|
| Control transfer of a product with assurance coverage | `WARRANTY_EXPENSE` | `WARRANTY_PROVISION` | Units × the product's `assurance_cost_per_unit` (POL-022) |
| Warranty claim cost incurred: `COST_INCURRED` with payload `purpose` `WARRANTY_CLAIM` (OQ-13, resolved by D-76) | `WARRANTY_PROVISION` | `COST_OF_REVENUE` | Claim cost, limited to the provision balance; the excess stays in the ERP cost account. [J] The ERP records claim costs in cost of revenue, and this line releases the provision against them (D-14a: fulfilment-cost release where elected, here POL-022 `ENGINE`) |

CHK-134 (research 04 S2-WARRANTY-OWN): Dr WARRANTY_EXPENSE 200.00 / Cr WARRANTY_PROVISION 200.00 at delivery.

#### JET-17 Noncash consideration (POL-048; ASU 2025-07)

| Event | Dr | Cr | Amount |
|---|---|---|---|
| Right to noncash consideration becomes unconditional | `NONCASH_CONSIDERATION_ASSET` | `CONTRACT_LIABILITY` | Units × fair value per unit at the measurement date (POL-048) |
| Noncash consideration received: the noncash form of `PAYMENT_RECEIVED`, with units received and carrying amount (OQ-13, resolved by D-76) | `BILLING_CLEARING` (`clearing_purpose` `INVESTMENTS`) | `NONCASH_CONSIDERATION_ASSET` | Carrying amount. Changes in fair value are recognised by the investments subledger, never as revenue (606-10-32-23) |

CHK-135 (research 04 S3-EX31, week 1): Dr NONCASH_CONSIDERATION_ASSET 1,000.00 / Cr CL 1,000.00; JET-02 Dr CL 1,000.00 / Cr REVENUE 1,000.00; on receipt Dr BILLING_CLEARING (INVESTMENTS) 1,000.00 / Cr NONCASH_CONSIDERATION_ASSET 1,000.00. The 200.00 gain on the shares is outside the engine.

### 2.4 ALG-03 Contract asset vs unbilled receivable (D-15; POL-122, POL-123)

**Rule.** A contract asset is a right to consideration conditioned on something other than the passage of time (606-10-45-3). A receivable is an unconditional right, even if not yet invoiced (606-10-45-4) [F]. The caption "unbilled receivable" does not decide the classification [practice, DART 14.4]. The engine tracks the two separately in every book (D-15).

**Classification object.** Each POB carries `right_to_consideration ∈ {CONDITIONAL, UNCONDITIONAL}`. A POB with several billing-plan lines carries the class per line.

Table 2.4-A: default classification (POL-122; OVR to change).

| POB measure or billing terms | Default | Reason |
|---|---|---|
| `RIGHT_TO_INVOICE`, time and materials, usage billed in arrears, royalties on occurred sales | `UNCONDITIONAL` | Only invoicing and the passage of time remain (45-4) |
| Fixed fee billed in arrears for a completed billing period under a noncancellable contract | `UNCONDITIONAL` | [J] The right for the elapsed period no longer depends on future performance |
| Point-in-time goods whose payment is due on transfer and is not conditional on other POBs | `UNCONDITIONAL` | 45-4 |
| Milestone billing before the milestone; payment conditional on transferring other POBs (FASB Example 39); cost-to-cost revenue ahead of the billing schedule; retention payable on completion or acceptance | `CONDITIONAL` | 45-3 |
| Contract where the customer can terminate for convenience without paying for performance to date | `CONDITIONAL` | No enforceable unconditional right |
| Legacy import under the parity preset | as above; both roles map to the POB's "Unbilled A/R Account" | D-15, D-32 |

**Algorithm.** ALG-02 step 3 computes U from the per-POB classes. For a POB with mixed billing lines: unconditional part = Σ over unconditional lines of max(0, earned amount for the line − invoiced amount for the line); the rest of max(0, R_p − B_p) is conditional.

**`ENGINE` billing mode (POL-123).** An invoice issued before the right is unconditional (for example advance billing on a cancellable contract, FASB Example 38 Case A) is memo-only until the earlier of cash receipt and the date the contract becomes noncancellable, so neither a receivable nor a contract liability is presented gross before then (606-10-55-286).

**Numeric checks.**

| CHK | Input | Expected |
|---|---|---|
| CHK-013 | FASB Example 39: allocation A 400.00, B 600.00; payment of 1,000.00 conditional on transferring both | After A transfers: NP −400.00, U 0, CA 400.00. After B transfers and the invoice (`ENGINE` mode): AR 1,000.00; NP 0; CA 0.00 |
| CHK-014 | Research 04 S5-PROGRESS-VARIANTS right to invoice: 120 hours × 25.00 in December, invoiced in January | December: NP −3,000.00, UR 3,000.00, CA 0.00. January after invoice: UR 0.00 |

### 2.5 ALG-04 SSP basis for modifications (D-18; POL-080, POL-081, POL-100 to POL-107)

#### 2.5.1 Inputs

- The contract version immediately before the modification's effective date d, after every event with an earlier (effective date, sequence).
- For each existing POB p: allocation A_p, posted cumulative revenue R_p, progress f_p (units: q_p ÷ Q_p; cost-to-cost: costs to date ÷ EAC; time: elapsed ÷ term), inception extended SSP SSP0_p and inception unit SSP u0_p = SSP0_p ÷ Q_p, flags `distinct_remaining` and `series`.
- Modification lines m: target (existing POB or new POB), signed quantity ΔQ_m, signed consideration ΔC_m, SSP row effective at d (POL-070 resolution at date d, or a per-POB override under POL-080), and an optional amount tagged `SATISFIED_PERFORMANCE` (POL-104).
- VC estimate versions effective at d that the modification changes (for example a bonus that becomes includable).

#### 2.5.2 Step 1: route (POL-100, POL-101)

1. **Separate contract (25-12).** If every line adds distinct goods as new POBs, every line's ΔC_m passes POL-101, and no existing POB is changed: create a new contract linked by `origin_modification_id`; the existing contract is unchanged. Stop.
2. Otherwise classify every POB after the modification:
   - **S**: satisfied (f_p = 1) and not targeted by a quantity line. A quantity line targeting S is error `MOD_QTY_ON_SATISFIED_POB`; a price-only line targeting S is satisfied performance (step 2).
   - **D**: remaining goods distinct from goods already transferred. This covers unsatisfied POBs, the undelivered units of a partially satisfied POB flagged `distinct_remaining`, the remaining increments of a series POB (606-10-25-13(a) text), and new distinct POBs.
   - **N**: a partially satisfied single POB whose remaining goods are not distinct, including added goods that form part of it.
3. The route label is `PROSPECTIVE_25_13A` when all remaining POBs are D, `CATCH_UP_25_13B` when all are N, and `MIXED_25_13C` otherwise. The engine proposes; the preparer confirms or overrides with OVR.

#### 2.5.3 Step 2: price change on satisfied performance (POL-104)

ΔC_sat = the sum of amounts tagged `SATISFIED_PERFORMANCE`. It is apportioned over the S POBs (and the delivered portions of D POBs when the tag names them) by their inception allocations (ALG-01), added to A_p and R_p, and posted by JET-05b or JET-05c. If no POB remains unsatisfied, every untagged ΔC_m is also treated as satisfied performance (corrects legacy D-06).

#### 2.5.4 Step 3: weights (POL-080, POL-081)

All weights are ≥ 0. "Clamp" means SSP resolution at date d under section 3.4, using the stated unit price given.

| POB class | `D18_DEFAULT` weight | `INCEPTION_ALL` weight |
|---|---|---|
| D existing | ρ_p × RQ_p × clamp_d(carried stated unit price), where RQ_p = Q_p − q_p + ΔQ_p and the carried stated unit price = original stated price ÷ original quantity. Added units at clamp_d(ΔC_m ÷ ΔQ_m) replace the carried price for those units and are not scaled. Removed units simply reduce RQ_p before scaling (`CARRIED_UNIT_SSP`). ρ_p = 1, except for a POB that is not a VC line and not a series, whose segment in force measures time elapsed with a cause other than termination (D-90b). For that POB, ρ_p = Σ_L q_L × (1 − f_L(d − 1)) ÷ Σ_L q_L over its unit layers L, where f_L is §2.12 progress under the POB's pinned convention (else POL-090), measured as on the inception basis at the close of d − 1 over [s_L, e], and [s, e] is the term in force (start not before the recognition start). The booked units start at s; units added at an earlier boundary k start at max(d_k, s); an earlier decrease reduces every layer pro rata. ρ_p is never read from the progress since an earlier boundary and is never compounded. Inside a period under `MONTHLY_EVEN` or `MID_MONTH` the current period counts as remaining. Added units count over [d, e]. When ρ_p = 0, or the layers do not reconcile with the segment history, the engine fails closed (ENGINE_SPEC S06-R-11); a unit history that net reconstruction cannot represent raises `MOD_UNIT_HISTORY_AMBIGUOUS` (ENGINE_SPEC S06-R-08) | ρ_p × RQ_p × u0_p, with added units at clamp_d(ΔC_m ÷ ΔQ_m), not scaled |
| D new | clamp_d(ΔC_m) for its quantity | same |
| D series | mod-date SSP of the remaining increments, priced from the SSP entry's declared basis (04 E-49 `PER_INCREMENT` / `PER_BOOKED_TERM` / remaining-increments-at-d; ENGINE_SPEC S06-R-11; D-93 (4)) | inception SSP of the remaining increments, from the entry's basis in the same way |
| N | (1 − f_p) × SSP0_p + Σ over added goods of clamp_d(ΔC_m) − removed goods × u0_p | same as `D18_DEFAULT` (D-18 (b) already uses inception SSP) |

Parity (`LEGACY_CARRIED_PLUS_FILE_VERSION`): w_p = max(0, carried remaining SSP + ModSSPChanges_p), where ModSSPChanges_p is the modification billing clamped into the file-version band with the sign-aware branch (legacy 03 §3.1, §3.4; `CLAMPED_MOD_PRICE` under POL-081).

#### 2.5.5 Step 4 and step 5: pool and apportionment (POL-103)

| Option | Pool | Shares |
|---|---|---|
| `REMAINING_TP` (default; DART 9.2.2 Alternative B) | Pool = Σ over D and N of (A_p − R_p) + Σ ΔC_m − ΔC_sat + ΔVC from estimate versions effective at d | s_p = ALG-01(Pool, w_p, keys). Posted new allocation A′_p = R_p + s_p for existing D and N POBs and A′_p = s_p for new POBs; exact new allocation X′_p = R_p + Pool × w_p ÷ Σw, or Pool × w_p ÷ Σw for new POBs. The remaining allocation s_p is recognised prospectively by the POB's measure, with no catch-up: posted cumulative revenue after d is C_t = R_p + round((X′_p − R_p) × g_t), bounded by A′_p and equal to A′_p when g_t = 1, where g_t is progress over the remaining term or the remaining units under the POB's convention (for units: units delivered after d ÷ RQ_p) (rev 1.2; D-76; `_coverage/answer-keys-industries:OQ-AKI-08`) |
| `ATTRIBUTE_BY_LINE` | Per POB: (A_p − R_p) + Σ of the lines targeting p | No apportionment |
| `TOTAL_TP` (DART 9.2.2 Alternative A; parity retrospective template) | TP after = TP before + Σ ΔC_m | Total allocation for every POB, including S, by weights over delivered and remaining SSP (legacy 04 §3.5); X′_p is the exact quota and A′_p its ALG-01 result |

If Σ w_p = 0 while Pool ≠ 0, the Pool is treated as satisfied performance (step 2).

#### 2.5.6 Step 6 and step 7: catch-up and record (POL-102)

- `PARTIALLY_SATISFIED_NONDISTINCT_ONLY`: for each N POB, f′_p = updated progress (units: q_p ÷ (Q_p + ΔQ_p); cost-to-cost: costs to date ÷ updated EAC; time: elapsed ÷ updated term); CU_p = round(X′_p × f′_p) − R_p, bounded by A′_p (ALG-01 §2.1.3), posted by JET-05a. D POBs have no catch-up.
- `ALL_POBS_FULL_REALLOCATION` (parity retrospective template): CU_p = round(X′_p × progress_p) − R_p for every POB, bounded by A′_p, where progress_p is the legacy SSP-delivered share (POL-107).
- Record: route, classification, weights, SSP version per POB, pool, shares, catch-ups, attributions, approvals and the pre/post POB lineage used by POL-106 (32-45 routing).

#### 2.5.7 Parity templates (POL-100 `USER_SELECTED_TEMPLATE`; D-17 full-precision internals, cents at posting)

| Template | Formula (legacy reference) | Golden acceptance |
|---|---|---|
| `LEGACY_PROSPECTIVE` | Pool = Σ RemAlloc_old + Σ ModBilling; weights = max(0, RemSSP_old + ModSSPChanges); RemAlloc_i = Pool × w_i ÷ Σw; catch-up only on `Nondistinct` rows with progress = CumDel ÷ (CumDel + RemQty); VC rows weight 0 (legacy 03 §3.4 to §3.6) | GT-12, GT-13, GT-15 |
| `LEGACY_RETROSPECTIVE` | TP_c = Σ CRA + Σ ModBilling + Σ RRC; SSP_c = Σ CRS′ + Σ PSSPD; r_c = TP_c ÷ SSP_c; total_i = r_c × (CRS′_i + PSSPD_i); catch-up_i = r_c × PSSPD_i − RRC_i on every POB (legacy 04 §3.5, §3.6) | GT-10, GT-14 |
| `LEGACY_POB_VC` | A1 = A_old + M on the targeted line only; CU = (A1 + R) ÷ (S + D) × D − R on the targeted line only (legacy 05 §3.4, §3.5). The legacy latent true-up on untouched lines (DEF-pob-vc-01) is a deviation | GT-11 |

The ten golden `cumulative_catchup` cases assert these templates.

#### 2.5.8 Numeric checks

| CHK | Input | Expected |
|---|---|---|
| CHK-027 | FASB Example 8 (pure 25-13(b)): A 1,000,000.00, R 600,000.00; ΔC +150,000.00; bonus estimate version now includes 200,000.00; costs 420,000.00; updated EAC 820,000.00 | Pool = 400,000.00 + 150,000.00 + 200,000.00 = 750,000.00; A′ = 1,350,000.00; f′ = 420,000 ÷ 820,000; CU = 91,463.41 |
| CHK-028 | FASB Example 5 Case B (25-13(a)): 60 original units remaining at 100.00; 30 added at 80.00; credit 15.00 × 60 delivered defective units tagged `SATISFIED_PERFORMANCE` | ΔC_sat = −900.00 (JET-05b); Pool = 6,000.00 + 2,400.00 = 8,400.00 over 90 units; units 93.33 / 93.34 / 93.33 …; contract liability 1,300.00 after 60 units, 0.00 after 90 |
| CHK-042 | Own example (mixed 25-13(c)). Inception: TP 120,000.00; SSP A 50,000.00, B 75,000.00, C 25,000.00; allocation A 40,000.00, B 60,000.00, C 20,000.00. At d: A satisfied; B (N, cost-to-cost) 50% complete, R 30,000.00, EAC 60,000.00; C (D) unstarted. Modification: non-distinct scope added to B for 20,000.00 (mod-date SSP 25,000.00), EAC +15,000.00; C's mod-date SSP 30,000.00 | `D18_DEFAULT`: Pool 70,000.00; weights B 62,500.00 (37,500.00 + 25,000.00), C 30,000.00; shares B 47,297.30, C 22,702.70; A′_B 77,297.30; f′ = 30,000 ÷ 75,000; cumulative 30,918.92; CU +918.92; B remaining 46,378.38. `INCEPTION_ALL`: weights 62,500.00 and 25,000.00; shares 50,000.00 and 20,000.00; CU +2,000.00 |
| CHK-043 | FASB Example 7 (series, 25-13(a)): Year 3 unrecognised 100,000.00; Year 3 fee reduced by 20,000.00; 3 extra years for 200,000.00; mod-date SSP 80,000.00 per year | Pool 280,000.00; four equal weights; 70,000.00 a year; contract liability end of Years 3 to 6: 10,000.00 / 6,667.00 / 3,334.00 / 0.00 (instalments 66,667.00, 66,667.00, 66,666.00) |

### 2.6 ALG-05 Material rights (D-21, D-21a; POL-026, POL-028, POL-055, POL-212)

#### 2.6.1 SSP of an option (POL-026)

| Method | Formula | Validation |
|---|---|---|
| `DISCOUNT_X_LIKELIHOOD` | SSP_opt = E × (d_ex − d_gen) × L, with E = expected purchase amount of the optioned goods, d_ex = discount on exercise, d_gen = discount available without exercising the option, L = likelihood of exercise (estimate version) (606-10-55-44) | 0 ≤ d_gen ≤ d_ex ≤ 1; 0 ≤ L ≤ 1. If d_ex − d_gen = 0 the option is not a material right (55-43) and no POB is created |
| `RENEWAL_ALTERNATIVE` | The contract includes the expected renewals; the transaction price is the expected consideration over them; allocation weights are the expected costs per period adjusted for renewal likelihood, or expected SSPs where costs are unavailable (606-10-55-45; FASB Example 51) | Actual renewals true up the transaction price and cumulative revenue (55-352) through ALG-10 |
| `ENTERED_AMOUNT` | SSP entered by the preparer (parity: quantity × list price 1) | EST approval outside parity |

The option POB enters allocation with weight SSP_opt (ALG-01). `DISCOUNT_X_LIKELIHOOD` is the D-21a formula.

#### 2.6.2 Exercise under `CONTINUATION` (default)

On `MATERIAL_RIGHT_EXERCISED` at date x, with additional consideration C_add and optioned goods G:

1. M = remaining allocation of the option POB (A_opt − R_opt). Close the option POB.
2. Create POB G with allocation M + C_add. If G has several distinct goods, apportion M + C_add over them by their SSPs at x (ALG-01).
3. Other POBs keep their allocations; no catch-up.
4. Revenue for G follows JET-02 as G transfers. For partial exercise (points, vouchers usable in part), M is released in proportion to redemptions ÷ expected redemptions (FASB Example 52).

#### 2.6.3 Exercise under `MODIFICATION`

Exercise is a modification effective at x. ALG-04 runs with two lines: remove the option POB (its remaining allocation M joins the pool) and add POB G with ΔC = C_add. Route per ALG-04 step 1; it is never a separate contract because the consideration includes M. Parity uses `LEGACY_PROSPECTIVE` with the quantity convention (POL-212; golden GT-15).

#### 2.6.4 Expiry

Remaining M posts to revenue on `MATERIAL_RIGHT_EXPIRED` (JET-08). For customer-loyalty points, expected unexercised points follow POL-055.

#### 2.6.5 Numeric checks

| CHK | Input | Expected |
|---|---|---|
| CHK-050 | TP 1,000.00. P1 product (SSP 900, satisfied at inception); P2 support (SSP 200, unstarted); option MR (SSP 100). Exercise: product P3 bought for 300.00; P3 SSP 400; P2 mod-date SSP 200 | Allocation P1 750.00, P2 166.67, MR 83.33. `CONTINUATION`: P3 383.33; P2 166.67. `MODIFICATION` (`D18_DEFAULT`): Pool 550.00; P2 183.33, P3 366.67; no catch-up |
| CHK-051 | FASB Example 49, redemption on a 50.00 purchase paying 30.00 | JET-08 continuation: Dr CL 40.71 / Cr REVENUE 40.71; expiry alternative 10.71 |
| CHK-052 | Golden GT-15 (Contract 3, 2023-09-15 material-right exercise plus new POB #5 for 1,000.00) | `MODIFICATION` (parity): POB #5 1,268.1139; POB #1 678.0182; POB #2 311.1106; POB #3 catch-up +32.1394; TP 2,600.00; JE Dr 21001 32.14 / Cr 5003 32.14. `CONTINUATION` (legacy 03 TC-04): POB #5 1,833.767587; POB #1 334.340803; POB #2 153.413236; POB #3 62.532569; no catch-up; TP 2,600.00 |
| CHK-053 | FASB Example 52: sales 100,000.00; 10,000 points; 9,500 then 9,700 expected; 4,500 then 8,500 redeemed | Allocation 91,324.20 / 8,675.80; points revenue P1 4,109.59, P2 3,492.91; contract liability end P1 4,566.21, end P2 1,073.30. Rev 1.2 re-baseline under D-11a: cumulative P2 = round(X × 8,500 ÷ 9,700) = 7,602.50 with X = 100,000 × 9,500 ÷ 109,500 = 8,675.7990… (rev 1.1 multiplied the posted 8,675.80; D-76, `_coverage/answer-keys-topics:OQ-AKT-01`) |
| CHK-054 | FASB Example 49 SSP: E 50.00, d_ex 0.40, d_gen 0.10, L 0.80; product SSP 100.00; price 100.00 | SSP_opt 12.00; allocation product 89.29, voucher 10.71 |

### 2.7 ALG-06 Returns (D-22; POL-051 to POL-053)

#### 2.7.1 Model

[J] A right of return is variable consideration allocated entirely to the POB of the returnable goods, because the refund terms relate specifically to those goods (606-10-32-39, 32-40). The estimate version (per POB, or per portfolio under PT-06) holds the expected further returns E (units), the carrying cost per unit k, the expected recovery cost per unit c_rec and the return-window end date.

Quantities for a POB: Q contract quantity; N cumulative units transferred; Y cumulative units returned; r = X_p ÷ Q, the exact unit allocation rate, where X_p is the exact allocation (ALG-01 §2.1.3; inception basis, changed only by TP changes and modifications); p_ref = refund price per unit (price billed or received for the transferred units).

#### 2.7.2 Measurement at each transfer, period end, return event and window expiry

1. Update E (estimate version). A return event reduces E by the units returned, floored at 0, unless the preparer approves a new estimate. Window expiry sets E = 0 for the expired cohort.
2. Revenue target C = round(r × (N − Y − E)). The difference from posted cumulative revenue posts by JET-02 (transfers) or JET-04a (estimate changes and expiry).
3. Refund-liability target RL = round(p_ref × E_b), where E_b = max(0, min(E, U_b − Y)) and U_b is the units billed or paid at the measurement date: the amount of the POB's `BILLING_RECORDED` lines that count as billed ÷ p_ref. A line counts when it names the POB or by the POB's ALG-02 step 3 share of its document's unreferenced lines (D-88 L7-5-Q-3); one line per identity (contract, `invoice_number`, `line_external_id`) at contract scope, a same-amount noncancellable repeat being a status update that adds nothing and a repeated line still cancellable being a new line (ENGINE_SPEC_B S10-R-07); and only from its S10-R-06 unconditional date, so in `ERP` mode from its effective date and in `ENGINE` mode a cancellable line counts from the earlier of a payment applied to its invoice and its first same-amount noncancellable status update, and a memo-only line counts nothing. Credit memos never enter U_b; returned units leave through Y. [J] The base is the consideration received or receivable for the transferred units (606-10-55-23, 32-10); within the engine a cancellable unpaid invoice records that the right is not yet unconditional (POL-123; 606-10-45-4, 55-286). Consideration received without an invoice is not attributed to POBs, and unbilled unconditional consideration (ALG-03) is likewise outside this proxy (recorded limitations, D-91). The difference posts by JET-04b (rev 1.7; D-91 supersedes lane note L1-3-Q-13).
4. Return-asset target RA = round(max(0, k − c_rec) × E). On a return event, JET-07d first derecognises round(max(0, k − c_rec) × min(units returned, E before the return)) into inventory; JET-07c then posts the remaining difference between RA and the return asset posted, against `COST_OF_REVENUE`. [J] Units returned in excess of E carry no return asset; the inventory subledger restores their cost.
5. The refund itself is a credit memo: ingested in `ERP` mode, JET-03 in `ENGINE` mode.
6. Units returned in excess of the previous E carry no refund liability, and their revenue reverses through the step 2 target at rate r per unit: Y rises by the units returned and E is floored at 0 (rev 1.2; step 2 governs, D-76 ruling on `_coverage/answer-keys-topics:OQ-AKT-03`). Under POL-053 `REDUCE_CONTRACT_QUANTITY` the POL-052 rate never applies; it applies only under `RESTORE_REMAINING_QUANTITY` (§2.7.3).

#### 2.7.3 Returned-units scope (POL-053)

- `REDUCE_CONTRACT_QUANTITY` (default): returned units leave the contract; the undelivered quantity (Q − N) is unchanged and no redelivery is expected.
- `RESTORE_REMAINING_QUANTITY` (parity): N decreases by the returned units, the units become deliverable again, and revenue is reversed at the POL-052 rate (parity `CURRENT_REMAINING_RATE`). Rev 1.2 writes N, the units transferred of §2.7.1, where rev 1.1 still wrote X. No refund liability or return asset exists (POL-051 `ACTUAL_RETURNS_ONLY`).

#### 2.7.4 Legacy import mapping (D-22)

| Legacy row | eRev Cloud event | Never |
|---|---|---|
| Negative `Current Delivery` | `RETURN_RECORDED` (payload `quantity` = \|q\|) | A negative POB |
| Negative `Current Billing` | `CREDIT_MEMO_RECORDED` (amount = \|b\|) | Negative billing on a POB |
| Negative `Original POB Total Selling Price` at setup | Rejected (POL-078) or mapped to a VC element (POL-213) | A negative POB |

#### 2.7.5 Numeric checks

| CHK | Input | Expected |
|---|---|---|
| CHK-029 | Research 04 S3-EX22 (Q = N = 100, r = p_ref = 100.00, k = 60.00, E = 3; two units returned; window expires) | As in JET-07: revenue 9,700.00 → 9,700.00 → 9,800.00; RL 300.00 → 100.00 → 0.00; RA 180.00 (JET-07c) → 60.00 (JET-07d 120.00) → 0.00 (JET-07c 60.00) |
| CHK-060 | As CHK-029, but at the first period end E is revised to 4 before any return | JET-04a Dr REVENUE 100.00 / Cr CL 100.00; JET-04b Dr CL 100.00 / Cr RL 100.00 (RL 400.00); JET-07c Dr RA 60.00 / Cr COST_OF_REVENUE 60.00 (RA 240.00). Two returns: RL 200.00; JET-07d Dr BILLING_CLEARING (INVENTORY) 120.00 / Cr RA 120.00 (RA 120.00); revenue unchanged at 9,600.00. Expiry: JET-04a Dr CL 200.00 / Cr REVENUE 200.00; RL 0.00; JET-07c Dr COST_OF_REVENUE 120.00 / Cr RA 120.00 (RA 0.00); final revenue 9,800.00 |
| CHK-061 | Golden GT-08 (parity): Contract 1 POB #1, 3 units delivered at 64.420218 (posted 128.84 + 64.42); return −3 units, credit memo −200.00 on 2023-04-30 | JET-02 negative: Dr 5001 193.26 / Cr 21001 193.26; remaining quantity 5; remaining allocation 322.1011 (full precision); cumulative billing 0.00 |

### 2.8 ALG-07 Cross-entity contracts (D-23; POL-170, POL-171)

1. **Allocation** runs per combination group across all entities, in the contract currency (legacy PAR-09).
2. **Roles.** Each POB carries `contracting_entity` e_c (bills; holds contract liability, contract asset and unbilled receivable) and `performing_entity` e_p. Default e_p = e_c.
3. **Balances.** ALG-02 runs per (c, e_c, b). The performing entity holds no contract balances.
4. **Revenue.** `PERFORMING_ENTITY`: when e_p ≠ e_c, JET-13 posts the contracting entity's liability relief against `INTERCOMPANY_DUE_TO` and the performing entity's revenue against `INTERCOMPANY_DUE_FROM`, both tagged with the counterparty. `CONTRACTING_ENTITY`: JET-02 in e_c; no intercompany lines.
5. **Currency.** The pair is measured in the contract currency. In e_c, the functional amount equals the liability relief (layer consumption, ALG-08). In e_p, the transaction amount is converted at e_p's revenue rate (POL-162). Remeasurement of intercompany balances belongs to the ERP intercompany module.
6. **Eliminations** belong to consolidation (ASC 810-10-45-1). The engine only tags counterparties (research 06 §10.3).

| CHK | Input | Expected |
|---|---|---|
| CHK-070 | TP 100,000.00 (USD, one currency). Licence POB: e_c = e_p = US, allocation 60,000.00, transferred in P1. Services POB: e_c = US, e_p = UK, allocation 40,000.00, 50% performed in P1. US invoices 100,000.00 at inception (`ERP` mode) | P1 US: JET-02 Dr CL 60,000.00 / Cr REVENUE 60,000.00; JET-13 Dr CL 20,000.00 / Cr INTERCOMPANY_DUE_TO (UK) 20,000.00. P1 UK: Dr INTERCOMPANY_DUE_FROM (US) 20,000.00 / Cr REVENUE 20,000.00. End P1: US contract liability 20,000.00; UK no contract balance. Each entity's batch balances. `CONTRACTING_ENTITY`: US revenue 80,000.00, no intercompany lines |
| CHK-071 | As CHK-070 with no invoice by the end of P1 | US NP = −80,000.00; contract asset 80,000.00 in US (conditional); UK revenue 20,000.00 and due-from 20,000.00 |

### 2.9 ALG-08 Foreign currency (D-25, D-25a, D-25b; POL-160 to POL-164)

#### 2.9.1 Layer algorithm per (c, e, b)

Amounts are held in the transaction currency with a functional carrying amount per layer.

| Event | Algorithm |
|---|---|
| Billing, unconditional due date or receipt, whichever is earlier (POL-160) | First settle open asset layers FIFO up to the amount: remeasure the consumed asset portion to spot at the event date (JET-10a), then relieve it. Any remainder creates a contract-liability layer at spot on the event date. The event date is the POL-160 date held inside the accounting period in which the billing enters the position (ENGINE_SPEC_B S10-R-06): an invoice neither due nor paid by the end of that period is processed on the period's last day, and a receipt dated in an earlier period than the invoice it names leaves the event on the day the invoice enters the position (rev 1.52; supervisor ruling R-81 of 2026-09-30, amending D-87 L6-5-Q-14; ENGINE_SPEC_B S12-R-04 rev 1.83; candidate AD-51 for the accountant) |
| Revenue relief (JET-02, JET-04a, JET-05a, JET-13) | Consume contract-liability layers in POL-161 order up to the transaction amount. Functional relief of a layer = cumulative-rounded share of the layer's functional carrying amount (ALG-01 §2.1.3 with f = consumed ÷ original layer amount), so a fully consumed layer ends at exactly zero. Any remainder creates an asset layer at the POL-162 rate for the effective date. Functional revenue = functional relief |
| Period end | Remeasure open asset layers to the closing rate (JET-10a). Under a contract-level POL-163 override, remeasure open liability layers too (JET-10b) |
| `ENGINE` billing mode | Accounts receivable recorded at invoice spot and remeasured at the closing rate until the ERP cash-application event reduces it (JET-10a′) |
| JET-06 | Reclass amounts use the functional carrying amount of the asset layers |
| Refund liability, deposit liability or consideration payable recognised (JET-04b, JET-05c, JET-01b receipt, JET-14; D-25b, POL-164) | A monetary layer per balance role and source event is created at spot on the recognition date, with layer key `<balance role>:<global event key>`. Where the recognition relieves contract-liability layers at historical carrying (JET-04b), the difference between the spot measurement and the functional relief posts by JET-10d on the recognition date. A refund-liability increase beyond the open contract-liability layers creates an asset layer at spot on the event date |
| Period end, monetary liabilities (D-25b) | Remeasure every open refund-liability, deposit-liability and consideration-payable layer to the closing rate (JET-10d), non-reversing |
| Settlement of a monetary liability: credit memo or refund, return-window expiry, `CONTRACT_CRITERIA_MET`, refund on termination, 606-10-25-7 derecognition, settlement of a consideration-payable promise (D-25b) | Remeasure the settled portion to spot on the settlement date (JET-10d); its carrying portion is the cumulatively rounded share of the layer's carrying amount (ALG-01 §2.1.3 with f = settled ÷ open before settlement). Then relieve the settled portion at spot. A release to the control role (JET-04b credit, JET-01b criteria met) enters this table as a billing-side credit at the release carrying, Σ per-layer round(take × spot) of the consumed layers; after it settles open contract-asset layers, the contract-liability layer it creates takes that carrying less the settlements (D-87 L6-5-Q-26; D-89b). A deposit transferred on criteria met therefore creates a contract-liability layer dated the transfer date at spot, the date the nonmonetary liability is first recognised (IFRIC 22.8), whatever POL-160 gives for invoices. A consideration-payable promise with no recorded settlement stays open and is remeasured at every period end |
| Credit memo that relieves contract-liability layers (D-76 ruling on `ENGINE_SPEC_B:OQ-B-14`) | Layers are relieved at historical carrying while the billing side debits the liability at spot; JET-10c posts round(m × spot) − the historical relief (ENGINE_SPEC_B S12-R-08) |

Flows on one date are processed in this order: time-driven releases first, then events in 05 ENG-06 order `(effective_date, record_seq, event_id)` (D-76; `_coverage/answer-keys-fx-entity-books:OQ-AK-12`).

#### 2.9.2 Framework differences

- IFRS15 book: layering is forced; the transaction date of each advance is the date the liability is first recognised (IFRIC 22), so multiple advances form separate layers.
- ASC606 book: layering by default (D-25 flag `fx.cl_historical_layering`); override only per POL-163.
- Both books: refund liabilities, deposit liabilities and consideration payable are monetary and remeasured (D-25b; IAS 21.16 and 21.23(a) in the IFRS15 book).
- Reporting currency: views only, balances at closing rate and flows at average or transaction rates, with a translation line in rollforwards (research 06 §9.6). Batch-conversion residue posts to `ROUNDING` (D-16).

#### 2.9.3 Numeric checks (functional USD, contract EUR; CHK-080 to CHK-083 use a contract of EUR 12,000 recognised EUR 1,000 per month)

| CHK | Input | Expected |
|---|---|---|
| CHK-080 | Invoices EUR 6,000 on 1 January at 1.1000 and EUR 6,000 on 1 July at 1.2000 | Layers L1 6,600.00 and L2 7,200.00. Revenue January to June 1,100.00 a month from L1; July to December 1,200.00 a month from L2; L1 exactly zero on 30 June; no FX lines; annual revenue 13,800.00 |
| CHK-081 | Arrears billing: average rates January 1.1100, February 1.1300, March 1.1500; closing rates 1.1200 and 1.1400; EUR 3,000 invoiced 31 March at 1.1600 | As JET-10: revenue 1,110.00 / 1,130.00 / 1,150.00; FX gains 10.00 / 30.00 / 50.00; contract asset presented 1,120.00 (31 January) and 2,280.00 (28 February); receivable at invoice 3,480.00 |
| CHK-082 | Refundable advance EUR 12,000 invoiced 1 January at 1.1000 with the POL-163 contract override; January average 1.1100; closing 1.1200 | January revenue 1,110.00; carrying 12,090.00; remeasured EUR 11,000 at 1.1200 = 12,320.00; JET-10b Dr FX_GAIN_LOSS 230.00 / Cr CL 230.00 |
| CHK-083 | `ENGINE` mode: AR EUR 12,000 invoiced 1 January at 1.1000, unpaid at 31 January; closing 1.1200 | JET-10a′ Dr AR 240.00 / Cr FX_GAIN_LOSS 240.00 (AR 13,440.00) |
| CHK-084 | D-25b monetary liabilities, `ERP` mode, inputs as in the JET-10 posting view: (a) refund liability EUR 300.00 recognised at 1.1000, closings 1.1200 and 1.0800, two units credited at 1.1500, window expiry at 1.1000; (b) deposit EUR 1,000.00 received at 1.1000, closing 1.1200, criteria met at 1.1300; (c) consideration payable EUR 50,000.00 promised at 1.1000, closing 1.0900 | (a) JET-10d losses 6.00 (31 March) and 6.00 (15 April settlement), gain 4.00 (30 April), loss 2.00 (31 May expiry); JET-04b releases 230.00 and 110.00; revenue 10,780.00; net FX loss 10.00; refund liability 0.00. (b) JET-10d losses 20.00 and 10.00; contract-liability layer 1,130.00. (c) JET-10d gain 500.00; customer incentive asset unchanged at 55,000.00 |

### 2.10 ALG-09 Late and backdated events (D-19; POL-180, POL-181)

1. An event E carries `effective_date` d_E (assigned to a period in the entity's time zone) and `recorded_at` (UTC).
2. If the period of d_E is open for (entity, book): post normally.
3. If it is locked: let P_o be the first open period. Replay the contract from inception with E inserted at (d_E, sequence) and compute the cumulative state at the end of P_o.
4. Delta per role and POB = recomputed cumulative through P_o − posted cumulative through P_o. Post the delta in P_o with `origin_period` = the period of d_E, `reason_code = LATE_EVENT`, and an out-of-period register entry (research 07 §5.4).
5. Rates: the replay uses the rates of each event's effective date (POL-181). Remeasurements of intervening locked periods are not reposted; the cumulative difference lands in P_o. JET-06 for P_o is recomputed; reclasses of locked periods are never re-reversed.
6. Locked-period reports stay "as known at lock"; "as currently known" views show the corrected history (research 06 §6.2).
7. Late-event revenue attributable to progress before the start of P_o counts as prior-period POB revenue (POL-204).
8. A material error is corrected through the reopen workflow (POL-183), not through this algorithm.

| CHK | Input | Expected |
|---|---|---|
| CHK-090 | Golden Contract 1 delivery effective 2023-01-31, recorded 2023-02-05 after January is locked; February open | February batch: Dr 21001 295.69 / Cr 5001 128.84, 5002 118.53, 5003 48.32, `origin_period` 2023-01; January locked batch unchanged; register lists 295.69 with origin 2023-01 and posting period 2023-02 |
| CHK-091 | Legacy 06 TC-JE-11, periods open: Contract 2 POB #2 delivery 1 unit dated 2023-03-31 processed first; POB #1 billing 500.00 dated 2023-02-28 processed second | Events ordered by effective date. February: Dr 21002 58.85 / Cr 15002 58.85 (January reclass reversed; position +441.15). March: Dr 21002 104.62 / Cr 5002 104.62; unbilled receivable 0.00 at both month-ends |

### 2.11 ALG-10 Estimate versions and catch-up tracing (D-20; POL-042, POL-043, POL-182, POL-204)

#### 2.11.1 Estimate object

| Field | Content |
|---|---|
| Identity | `estimate_id`, `kind` ∈ 04 E-09 {`VARIABLE_CONSIDERATION`, `RETURN_RATE`, `BREAKAGE`, `EAC`, `EXERCISE_LIKELIHOOD`, `IMPLICIT_PRICE_CONCESSION`, `RENEWAL_EXPECTATION`, `ROYALTY_ACCRUAL`, `EXPECTED_PURCHASES`, `SHARE_BASED_CONSIDERATION`} (D-73; `SHARE_BASED_CONSIDERATION` is added to 04 E-09 by the D-76 ruling on OQ-14), scope (contract, POB, portfolio). The constraint judgement is the constrained amount of a `VARIABLE_CONSIDERATION` version, not a separate kind |
| Version | `version_no`, `supersedes_version`, `effective_date`, `recorded_at` |
| Values | Method (POL-040, locked on version 1), scenario table, unconstrained estimate, constrained amount, refund-liability target where relevant (`refund_liability_target`; D-76 ruling on `ENGINE_SPEC_B:OQ-B-07`) |
| Evidence | Rationale, evidence references, preparer, approver, `approved_at` |
| Rules | Immutable. Only approved versions affect posting (EST). A reassessment creates a version, never an update |

#### 2.11.2 Catch-up and trace

On approval of v_new effective at d:

1. Recompute with v_new pinned from d. Versions effective before d are unchanged.
2. For each POB p: exact new allocation X′_p and posted new allocation A′_p (inception basis, or targeted under 32-40); progress f_p(d); C′_p = round(X′_p × f_p(d)), bounded by A′_p (ALG-01 §2.1.3); catch-up CU_p = C′_p − posted cumulative revenue of p through d. JET-04a posts CU_p in the period of d, or under ALG-09 if that period is locked.
3. Trace record: `estimate_id`, version pair (v_old, v_new), ΔTP, ΔA_p, f_p(d), CU_p, journal line ids. The `/explain` endpoint (D-45) returns this chain.
4. Several versions approved in one period apply in effective-date order, each with its own trace.

#### 2.11.3 Prior-period decomposition (POL-204; 606-10-50-10(b), 50-12A)

For a period t starting at s, the revenue of POB p posted in t that relates to POBs satisfied or partially satisfied in previous periods is:

`prior_period_revenue_p(t) = Σ over boundaries k effective in t of round(E_after,k(s) − E_before,k(s)) + Σ late-event deltas (ALG-09) attributable to progress before s`. E_before,k(s) and E_after,k(s) are the exact cumulative revenue of p at s under the state immediately before and after k, both evaluated with the measure quantities at the end of the day before s. Boundaries are reallocating estimate versions, modifications, terminations, exercises, and measure-only versions that change progress totals (for example `EAC`). For an allocation change k this equals round(ΔX_p,k × f_p(s)), where ΔX_p,k is the change in the exact allocation of p caused by k. For a change in progress totals it captures the effect on performance already satisfied (rev 1.2; D-76 ruling on `ENGINE_SPEC_B:OQ-B-20`; ENGINE_SPEC S08-R-14).

Normal progress revenue is the remainder. The catch-up posted at d, ΔX × f_p(d), is therefore split into ΔX × f_p(s) (prior period) and ΔX × (f_p(d) − f_p(s)) (current period).

| CHK | Input | Expected |
|---|---|---|
| CHK-100 | Research 04 S3-EX21-EXTENDED Year 2: bonus estimate v1 constrained (0.00) → v2 150,000.00; f(s) = 0.40; f(e) = 0.80 | CU 60,000.00; progress revenue 1,062,000.00; Year 2 revenue 1,122,000.00; prior-period revenue 60,000.00; trace ΔTP +150,000.00 |
| CHK-101 | Research 04 S3-EX23 Case B: v1 constrained concession 50% (TP 50,000.00) → v2 resolved 45% (TP 55,000.00) in February 20X8; POB satisfied in December 20X7 | CU +5,000.00; prior-period POB revenue for 20X8 5,000.00; trace ΔTP +5,000.00 |

### 2.12 ALG-11 Time-elapsed conventions (POL-090; B1-004, D-75)

**Inputs.** A POB term [s, e], dates inclusive in the entity time zone (D-19); the entity's accounting periods that intersect the term (04 E-50 calendar pattern); the convention resolved under POL-090. For a period P: D(P) = days in P; n(P) = days of the term in P; the day number of a date x in P = x − (first day of P) + 1.

**Output.** Exact cumulative progress f(d) ∈ [0, 1] at any date d, as a `Fraction`; f(d) = 0 before s. Schedules use f_t = f(last day of period t) and post through ALG-01 §2.1.3 (cumulative rounding; C_t = A when f_t = 1). Catch-ups at an effective date (ALG-04 step 6, ALG-10) use f at that date.

| Convention | Exact progress f(d) |
|---|---|
| `DAILY` | f(d) = clamp((min(d, e) − s + 1) ÷ (e − s + 1), 0, 1) |
| `MONTHLY_EVEN` | A period P is whole when n(P) = D(P), otherwise partial; only the first and last periods of the term can be partial. W = (number of whole periods) + Σ over partial periods of n(P) ÷ D(P). Elapsed(d) = (number of whole periods whose last day ≤ d) + Σ over partial periods of (days of the term in P on or before d) ÷ D(P). f(d) = Elapsed(d) ÷ W |
| `MID_MONTH` | First counted period: the period containing s if the day number of s ≤ 15, otherwise the next period. Last counted period: the period containing e if the day number of e ≥ 15, otherwise the previous period. If the first counted period is later than the last, the period containing e is the only counted period. With m counted periods, f(d) = (number of counted periods whose last day ≤ d) ÷ m |

**Rules.**

1. **Replacement of the retired option.** On a term that starts on the first day of a period and ends on the last day of a period, `MONTHLY_EVEN` gives f(d) = completed periods ÷ total periods at every date, which is the result of the retired option `MONTHLY_WHOLE_MONTHS` (CHK-143). Stored values of the retired option migrate to `MONTHLY_EVEN` with no recomputation difference. The validation error `TERM_NOT_WHOLE_MONTHS` is retired, because no convention restricts the term.
2. **Steps within a period.** `MONTHLY_EVEN` progress steps on the last day of a whole period and accrues by day within a partial period. `MID_MONTH` progress steps on the last day of each counted period.
3. **Threshold.** Day 15 applies to the day number within the accounting period for every E-50 calendar pattern; for `MONTHLY` calendars it is the calendar 15th. [J] One fixed threshold keeps the convention deterministic under 4-4-5 and 13-period calendars.
4. **Start and completion.** [J] `MID_MONTH` may begin revenue in the period after s and complete it in the period before the one containing e. The fallback for a term with no counted period places the whole amount in the period containing e, so revenue never precedes the term and always completes by the end of the period containing e.
5. **Term changes.** The convention is pinned on the POB (POL-090 `K`). A modification or estimate change that changes s or e recomputes f over the updated term with the same convention (ALG-04 step 6).

**Numeric checks** (monthly calendar; USD; one POB, so X = A).

| CHK | Input | Expected |
|---|---|---|
| CHK-140 | `DAILY`: 12,000.00 over 2026-02-10 to 2027-02-09 (365 days) | Periods February 2026 to February 2027: 624.66 / 1,019.18 / 986.30 / 1,019.18 / 986.30 / 1,019.17 / 1,019.18 / 986.30 / 1,019.18 / 986.30 / 1,019.18 / 1,019.18 / 295.89; total 12,000.00. f(2026-06-15) = 126/365 |
| CHK-141 | `MONTHLY_EVEN`: the CHK-140 POB | W = 19/28 + 11 + 9/28 = 12. February 2026 678.57; March 2026 to January 2027 1,000.00 each; February 2027 321.43. f(2026-02-20) = 11/336; f(2026-06-15) = 103/336 (June not yet complete) |
| CHK-142 | `MID_MONTH`: the CHK-140 POB | Day 10 ≤ 15 counts February 2026; day 9 < 15 stops at January 2027; m = 12. February 2026 to January 2027 1,000.00 each; February 2027 0.00. f(2026-06-15) = 1/3 |
| CHK-143 | `MONTHLY_EVEN`: (a) 35,000.00 over 2026-01-01 to 2027-12-31; (b) 3,000.00 over 2026-02-10 to 2026-05-20 | (a) Every period equals CHK-004: months 1 to 3 1,458.33 / 1,458.34 / 1,458.33; cumulative 33,541.67 after month 23; month 24 1,458.33. (b) W = 19/28 + 2 + 20/31 = 2,885/868; periods 612.48 / 902.60 / 902.60 / 582.32. `DAILY` on the same term: 570.00 / 930.00 / 900.00 / 600.00 |
| CHK-144 | `MID_MONTH`: 10,000.00 over 2026-03-20 to 2026-10-10 | Counted periods April to September 2026 (m = 6). March 0.00; April 1,666.67; May 1,666.66; June 1,666.67; July 1,666.67; August 1,666.66; September 1,666.67; October 0.00 |
| CHK-145 | `MID_MONTH` edge cases: (a) 500.00 over 2026-01-20 to 2026-02-10; (b) 500.00 over 2026-01-05 to 2026-01-10; (c) 1,300.00 over 2026-01-15 to 2027-01-15 | (a) The rule counts no period; the fallback counts February 2026: January 0.00, February 500.00. (b) The fallback counts January 2026: 500.00 in January. (c) Both thresholds are inclusive: m = 13; 100.00 in each period from January 2026 to January 2027 |

---

## 3. SSP policy

### 3.1 Method hierarchy (POL-074)

| Rank | Method | Permitted when | Evidence required | Authority |
|---|---|---|---|---|
| 1 | `observable` | Standalone sales to similar customers in similar circumstances | Population, period, coverage statistics (section 3.3) | 606-10-32-32 [F] |
| 2 | `adjusted_market` | No observable standalone price; market information available | Competitor or market prices and the adjustments applied | 606-10-32-34(a) [F] |
| 3 | `cost_plus_margin` | Cost data available | Cost basis and margin rationale | 606-10-32-34(b) [F] |
| 4 | `residual` | Only under section 3.2 | Evidence that the SSP is highly variable or not yet established | 606-10-32-34(c) [F] |

Method labels are the 04 E-47 `ssp_method` literals (D-73; rev 1.1).

Rules:

1. An SSP row carries exactly one method label, a point or a range, optional `observable_point`, segment keys (customer class, geography, channel, currency), effective dates and version.
2. A combination of methods (32-35) is expressed as separate rows with a rationale, never as a blended row.
3. Publication requires the method label, an evidence attachment and an approver different from the preparer (research 07 §5.1).
4. Legacy SKU rows import with method `legacy_range` and the legacy midpoint-discount and range attributes (parity; 04 E-47). E-47 `formula` is reserved (later) and never resolves an SSP in 1.0.

### 3.2 Residual approach (POL-075)

**Eligibility (all required).**

1. The POB's SSP row is flagged `ssp_highly_variable` or `ssp_not_established`, with evidence (606-10-32-34(c)).
2. Every other POB in the contract has a non-residual SSP.
3. Any discount allocated under 606-10-32-37 has been allocated first (32-38; POL-076).
4. If more than one POB is residual-eligible, the residual gives their combined SSP, which another method then splits (32-35).

**Computation.** R = transaction price available for allocation (after targeted VC) − Σ resolved SSPs of the other POBs, where POBs covered by a discount exception count at their discounted bundle allocation.

**Checks.** R > 0, and if the SKU has an observable range [lo, hi], lo ≤ R ≤ hi (FASB Example 34 Case C).

**Failure (POL-075).** `REQUIRE_ESTIMATED_SSP`: the contract stays in draft with exception `RESIDUAL_REJECTED`; the preparer enters an `adjusted_market` or `cost_plus_margin` SSP with OVR; relative SSP allocation then applies to all POBs. `BLOCK`: the contract cannot be activated.

**Allocation.** The residual POB receives R. Other POBs receive their SSPs or discount-exception allocations.

| CHK | Input | Expected |
|---|---|---|
| CHK-032 | FASB Example 34 Case C: SSP A 40, B 55, C 45; bundle B+C sold for 60; D range 15 to 45; TP 105 | Residual R = 5.00 is rejected (below 15). With an estimated SSP for D of 30: A 24.71, B 33.97, C 27.79, D 18.53 |
| CHK-033 | Case B: TP 130 | A 40.00; B 33.00; C 27.00 (discount exception); residual D 30.00, within 15 to 45 |
| CHK-034 | Case A: TP 100, discount exception | A 40.00; B 33.00; C 27.00 |

### 3.3 Range validation at publication (POL-073; U-02)

For each range row: half-width h = max(hi − mid, mid − lo) ÷ mid; coverage c = the share of standalone transactions in the attached population whose unit price lies within [lo, hi], inclusive.

| Test | Default parameter | Failure code |
|---|---|---|
| h ≤ `max_half_width_pct` | 0.20 | `RANGE_TOO_WIDE` |
| c > `min_coverage_pct` | 0.50 | `COVERAGE_TOO_LOW` |
| Population attached | required outside parity | `COVERAGE_UNKNOWN` |

`WARN` publishes with the warning on the approval record; `BLOCK` prevents publication. [F] DART 7.3.3.6.1 describes the heuristic as practice, not Codification text, so the thresholds are tenant parameters.

| CHK | Input | Expected |
|---|---|---|
| CHK-031 | Midpoint 160.00, range ±15%, 23 of 40 transactions inside; then range ±25%, 20 of 40 inside | First row passes (h 0.15, c 0.575). Second row: `RANGE_TOO_WIDE` (h 0.25) and `COVERAGE_TOO_LOW` (c 0.50 is not greater than 0.50) |

### 3.4 SSP point for a stated price (POL-071, POL-072)

For a POB with quantity Q > 0 and stated extended price P:

- Range bounds at quantity: mid = Q × list × (1 − d) (or Q × unit midpoint); lo = mid × (1 − r); hi = mid × (1 + r). Asymmetric rows store lo and hi directly.
- Point rows: SSP = Q × point, whatever the price.

| Stated price | `CONTRACT_PRICE` / `MIDPOINT` (inside) | `NEAREST_BOUND` | `MIDPOINT` | `LOW_POINT` | `HIGH_POINT` | `OBSERVABLE_POINT` |
|---|---|---|---|---|---|---|
| lo ≤ P ≤ hi | P / mid | not applicable | | | | |
| P < lo | | lo | mid | lo | hi | Q × `observable_point`; lo with warning `OBSERVABLE_POINT_MISSING` if absent |
| P > hi | | hi | mid | lo | hi | as above, hi if absent |

Other cases: a $0 stated price is below lo, so `NEAREST_BOUND` gives lo and the free POB still receives an allocation (legacy OK-03). Q < 0 arises only in the parity modification templates, which use the legacy sign-aware branch (legacy 03 §3.1). Material-right rows under `ENTERED_AMOUNT` and legacy VC rows (SSP 0) bypass the range.

**Default [J].** `NEAREST_BOUND` is the smallest adjustment that brings the SSP within the supported range, so allocations stay as close as the evidence allows to negotiated prices. It is an acceptable point under DART 7.3.3.6.2 and it preserves continuity with legacy (D-32).

| CHK | Input | Expected |
|---|---|---|
| CHK-030 | Research 04 S4-SSPRANGE-OWN: licence list 200, d 0.20, r 0.15, price 120 (range 136 to 184, mid 160); services point SSP 300 at price 300; TP 420 | `NEAREST_BOUND` and `LOW_POINT`: 131.01 / 288.99. `MIDPOINT`: 146.09 / 273.91. `HIGH_POINT`: 159.67 / 260.33. `OBSERVABLE_POINT` 150: 140.00 / 280.00 |
| CHK-035 | Golden TC-setup-03 to 06 (parity) | Hardware Q 5 at 500 within [382.5, 517.5] → 500; Software Q 2 at 400 → 368 (hi); Hardware Q 8 at 600 → 612 (lo); prices on the bounds are kept (517.5 and 272) |

---

## 4. Codification currency (D-26; closes U-03)

### 4.1 Method and limitations

| Item | Fact |
|---|---|
| Sources | FASB Accounting Standards Update PDFs from `[external website reference removed]`, downloaded on 2026-09-12 to `.scratch/design-ra-policies/asu/` (ASU 2014-09 Section A and ASU 2016-02 Sections A to C from `.scratch/04-asc606-technical/asu/`). URL pattern: `[external website reference removed]`; ASU 2014-09: [external website reference removed] ASU 2016-02: [external website reference removed] |
| Sweep | Every ASU number from 2014-01 to 2026-05 was requested (`.scratch/design-ra-policies/sweep_asu.py`). For each retrieved ASU the script read the Codification change tables (`606-10-00-1`, `340-40-00-1`, `605-35-00-1`, `805-20-00-1`) and the amendment instructions |
| Latest ASU found | ASU 2026-03 (September 2026). ASU 2026-04 and later returned HTTP 403 on 2026-09-12, which is consistent with not yet issued |
| Not retrieved (HTTP 403 at the standard path) | 2014-01, 2014-02, 2014-04, 2015-07, 2017-04, 2017-14, 2018-06, 2018-10, 2018-16, 2018-20, 2019-01, 2019-07, 2023-01, 2023-02. Their effect on the four Topics was not checked in this session (OQ-07) |
| Not accessed | The online Codification (`[external website reference removed]`, login required). Paragraph text is taken from the ASUs as issued. A later ASU in the sweep that changes the same paragraph is listed in section 4.2 |

### 4.2 Register of ASUs amending Topics 606, 340-40, 605-35 and 805-20 (contract balances)

| ID | ASU (URL) | Issued | Paragraphs added or amended in the four Topics | Effective | Engine effect | POL / PT |
|---|---|---|---|---|---|---|
| ASU-01 | [external website reference removed] | May 2014 | Creates Topic 606 and Subtopic 340-40; retains the Subtopic 605-35 loss guidance | In force | The whole model | All |
| ASU-02 | [external website reference removed] | Aug 2015 | 606-10-65-1 | In force | None (dates) | POL-218 |
| ASU-03 | [external website reference removed] | Jan 2016 | 606-10-15-2 (scope reference) | In force | None | none |
| ASU-04 | [external website reference removed] | Feb 2016 | 606-10-15-2; 606-10-55-68, 55-72, 55-407 (repurchase agreements: lease outcome) | In force | Lease outcomes routed out | POL-233, PT-09 |
| ASU-05 | [external website reference removed] | Mar 2016 | 606-10-55-36 to 55-40; Examples 45 to 48A (research 04 S2) | In force | Gross vs net per specified good or service | POL-030 |
| ASU-06 | [external website reference removed] | Apr 2016 | 606-10-25-16, 25-16A, 25-16B, 25-17, 25-18, 25-18A, 25-18B, 25-19, 25-21; 55-3, 55-54, 55-55, 55-57, 55-58, 55-58A to 55-58C, 55-59, 55-60, 55-61 (superseded), 55-62, 55-63 and later illustrations | In force | Immaterial promises, shipping election, licence nature and renewal timing | POL-020, POL-021, POL-024, POL-025, POL-232 |
| ASU-07 | [external website reference removed] | May 2016 | None of the four Topics (606-10-65-1 referenced only) | In force | None | none |
| ASU-08 | [external website reference removed] | May 2016 | 606-10-25-1, 25-3, 25-5, 25-7; 32-2A added; 32-21, 32-23; 55-3, 55-3A to 55-3C added; 55-94 to 55-98L (Example 1); 55-250; 65-1 | In force | Collectibility, 25-7(c), sales-tax election, noncash measurement date | POL-011, POL-012, POL-045, POL-048 |
| ASU-09 | [external website reference removed] | Jun 2016 | 606-10-45-3, 45-4, 50-4, 55-108, 55-109, 55-231, 55-237, 55-239; 805-20 glossary terms | In force | Credit losses on receivables and contract assets outside revenue | POL-125, PT-07 |
| ASU-10 | [external website reference removed] | Dec 2016 | 606-10-15-2; 50-8; 50-12A added; 50-14; 50-14A, 50-14B added; 50-15; 55-125, 55-127, 55-128 (Example 7); 55-285, 55-286 (Example 38); 55-293; 55-300; 55-305A added; 65-1. 340-40-35-3 to 35-5. 605-35-25-47. 270-10-50-1A | In force | Prior-period POB revenue, RPO exemptions, cost impairment test, loss unit, Examples 7 and 38 | POL-126, POL-150, POL-197 to POL-200, POL-203, POL-204, JET-09 |
| ASU-11 | [external website reference removed] | Jan 2017 | 606-10-65-1 (SEC transition paragraphs) | In force | None | none |
| ASU-12 | [external website reference removed] | Feb 2017 | 606-10-65-1 (transition link); Subtopic 610-20 scope | In force | Noncustomer nonfinancial asset transfers routed out | POL-230, PT-08 |
| ASU-13 | [external website reference removed] | Sep 2017 | 606-10-65-1 | In force | None | none |
| ASU-14 | 2017-14 (not retrieved) | Nov 2017 [not verified] | Not checked (HTTP 403) | In force | None expected for SEC paragraphs [J] | OQ-07 |
| ASU-15 | [external website reference removed] | Jun 2018 | 606-10-32-25 | In force; later amended by ASU-18 and ASU-23 | Superseded in effect by 32-25A | PT-10 |
| ASU-16 | [external website reference removed] | Jun 2018 | 606-10-15-2A added (contributions outside Topic 606) | In force | Contributions routed out at intake (`docs/00-GOAL.md` §4) | none |
| ASU-17 | [external website reference removed] | Nov 2018 | 606-10-15-3 | In force | Collaboration participants that are customers for a distinct good or service follow 606; others routed out | POL-234 |
| ASU-18 | [external website reference removed] | Nov 2019 | Glossary (award, grant date, performance condition, service condition); 606-10-32-25; 32-25A added; 55-3; 55-88A, 55-88B added | In force | Share-based consideration payable measured under Topic 718 | PT-10, JET-14 |
| ASU-19 | [external website reference removed] | Jun 2020 | 606-10-65-1 | In force | None (dates) | none |
| ASU-20 | [external website reference removed] | Jan 2021 | 606-10-25-18C added (link); 952-606-25-2 to 25-4 and 50-1 to 50-2 | In force | Nonpublic franchisor pre-opening services expedient | POL-202 |
| ASU-21 | [external website reference removed] | Oct 2021 | 805-20-25-16, 25-17; 25-28C added; 30-10 to 30-12; 30-27 to 30-30 added; 50-5 added; 65-3 added; glossary (contract liability, performance obligation, standalone selling price, transaction price) | PBE fiscal years beginning after 15 Dec 2022; others after 15 Dec 2023 [F] | Acquired contract balances measured under 606 as if originated; expedients 30-29(a), (b) | POL-215 to POL-217, PT-11 |
| ASU-22 | [external website reference removed] | Nov 2024 | 340-40-50-3 (amortisation and impairment of costs to obtain and to fulfil are listed expense items) | PBE annual periods beginning after 15 Dec 2026; interim periods beginning after 15 Dec 2027; early adoption permitted; prospective [F] | Cost amortisation and impairment reported by expense caption (reporting only) | POL-143, JET-09 |
| ASU-23 | [external website reference removed] | May 2025 | Glossary "performance condition" (now includes customer purchase conditions); 606-10-32-25, 32-25A, 55-3, 55-88A, 55-88AA to 55-88AC added, 55-88B, 55-88C added, 65-2 added | All entities, annual periods beginning after 15 Dec 2026; early adoption permitted; modified retrospective or retrospective [F] | Vesting probability assessed under Topic 718 only; the 606 constraint (32-11, 32-12) is not applied (55-88C); forfeitures are estimated (the as-they-occur election is eliminated for customer awards) | PT-10 |
| ASU-24 | [external website reference removed] | Jul 2025 | None in the four Topics (326-20-30-10A to 30-10H and related) | Annual periods beginning after 15 Dec 2025; early adoption permitted; prospective [F] | Practical expedient for current receivables and current contract assets arising under Topic 606 (current conditions assumed unchanged for the remaining life); non-PBE election to consider collections after the balance-sheet date. The engine records the elections and exports the population | POL-125, PT-07 |
| ASU-25 | [external website reference removed] | Sep 2025 | 606-10-15-3A added; 55-93, 55-247, 55-248 amended; 55-250A to 55-250D added (Example 31A); 65-3 added | All entities, annual periods beginning after 15 Dec 2026; early adoption permitted [F] | Share-based noncash consideration from a customer stays in Topic 606 (32-21 to 32-24) until the right to it is unconditional (assessed only on terms relating to the POBs, consistent with 45-4); Topics 815 and 321 apply afterwards. JET-17 transfers the asset at that point | POL-048, JET-17, PT-10 |
| ASU-26 | [external website reference removed] | Dec 2025 | 606-10-50-5, 50-6, 50-8, 50-12A, 50-13, 50-15; supersedes 270-10-50-1A; 270-10-50-34 lists 606-10-50-5 to 50-6, 50-8, 50-12A to 50-15; 805-20-50 interim references | Interim periods within annual periods beginning after 15 Dec 2027 (PBE) and 15 Dec 2028 (others); prospective or retrospective [F] | Interim pack contents | POL-203 |
| ASU-27 | [external website reference removed] | Dec 2025 | 606-10-55-404 (Issue 11: the call-option lapse date in Example 62 Case A corrected to 31 December 20X7) | Annual periods beginning after 15 Dec 2026 [F] | None. Research 04 key S5-EX62 already uses 31 December 20X7 | POL-233 |

**805-20 ASUs that do not touch contract assets or liabilities.** 2014-18, 2015-10, 2015-16, 2016-03, 2016-19, 2017-01, 2019-06, 2019-11, 2021-03, 2021-05, 2023-05, 2024-02, 2025-03, 2025-08, 2025-10 and 2026-02 amend Subtopic 805-20 elsewhere. None changes 805-20-30-27 to 30-30; no engine effect.

**Related ASUs with no paragraph change in the four Topics.** ASU 2016-04 (breakage for prepaid stored-value products under Subtopic 405-20): stored-value products redeemable only for third-party goods are outside POL-055 and routed out. ASU 2020-10 (Codification Improvements): amends 835-30-15-3 to reference the financing guidance in 606-10-32-15 to 32-20; no engine effect.

**Share-based noncash consideration from customers (D-26).** Issued as ASU 2025-07 (ASU-25).

### 4.3 Verification of unverified claims

| ID | Claim | Result | Evidence | Engine default |
|---|---|---|---|---|
| U-01 | US GAAP "probable" is about 75%; IFRS "more likely than not" | **Unsupported as Codification.** The Master Glossary defines probable as "The future event or events are likely to occur", with no percentage. ASU 2014-09 acknowledges that the Boards gave "probable" different meanings in US GAAP and IFRS | ASU 2014-09 Section A, Master Glossary and summary (local copy) | POL-011 stores a boolean judgement per book; no percentage is encoded anywhere |
| U-02 | An SSP range is acceptable when a majority of transactions fall within about ±20% of the midpoint | **Verified as practice, not Codification.** DART 7.3.3.6.1: "encompasses the majority of the relevant transactions (i.e., greater than 50 percent)" and "has a width extending no greater than 20 percent from the midpoint in either direction"; 7.3.3.6.2 lists midpoint, outer point, low point and high point as policy points | [external website reference removed] (fetched 2026-09-12) | POL-073 `WARN` at 0.20 and 0.50; POL-072 `NEAREST_BOUND` |
| U-03 | Codification currency | **Closed** through ASU 2026-03 by section 4.2, with the limitations in section 4.1 | Section 4.1 | Section 4.2 |
| U-04 | Nonpublic relief for 606-10-50-12A | **Verified.** DART 15.2 quotes 606-10-50-11 as covering "paragraphs 606-10-50-8 through 50-10 and 606-10-50-12A". The ASU 2014-09 text covered 50-8 to 50-10 only, and the ASU 2016-20 text retrieved does not show the conforming change to 50-11 | [external website reference removed] (fetched 2026-09-12); ASU 2014-09 §A; ASU 2016-20 | POL-192 includes 50-12A in the relief (OQ-08 asks for confirmation in the online Codification) |
| research 04 §13 #17 | ASU 2016-20 disclosures 50-12A, 50-14A, 50-14B may be US-only | **Partly verified.** IFRS 15.116(c) requires "revenue recognised in the reporting period from performance obligations satisfied (or partially satisfied) in previous periods", so 50-12A has an IFRS equivalent. IFRS 15.121 offers only (a) original duration one year or less and (b) paragraph B16, so 50-14A is US-only | IFRS 15 as adopted by Regulation (EU) 2016/1905, [external website reference removed] | POL-199, POL-200 forced off for IFRS; POL-204 applies to both books |
| C-15 | SSP-range authority | **Resolved** by U-02 | as U-02 | as U-02 |
| U-08 | Vendor blogs as authority | **Replaced.** This document cites the Codification, IFRS 15 and DART only | Sections 1 to 5 | none |

---

## 5. Policy topics (M-RA-05, M-RA-06)

### 5.0 Additional register entries for the topics

These rows belong to the policy register (section 1) and follow its column key.

| ID | Key | Question | Options | 606 | IFRS | Parity | Levels | Pin | Appr | Authority | Engine effect | AK |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| POL-240 | `usage.tier_minimum_method` | Is usage-based VC allocated to the period of usage, or estimated for the whole measurement period? | `DERIVED`, `ESTIMATE_MEASUREMENT_PERIOD_TP` | `DERIVED` | `DERIVED` | n/a | P, C | K | OVR to depart from the derived result | 606-10-32-39(b), 32-40 [F]; research 05 §2 pitfall 1 [practice] | `DERIVED`: period allocation only when the unit rate is constant within the measurement period and there is no minimum, retrospective tier or carry-over shortfall; otherwise `ESTIMATE_MEASUREMENT_PERIOD_TP` (PT-01). Rev 1.125 (register index 309; release 1.0): the engine reads the parameter for a contract, so a value at level P is read by no computation; every contract takes `DERIVED`, and a product and an obligation template state that value or none (§0.5 rule 1) | VC, REC |
| POL-241 | `credits.rollover_treatment` | How are unused prepaid credits that roll into a renewal accounted for? | `BREAKAGE_INCLUDING_EXPECTED_ROLLOVER_USE`, `FORFEIT_AT_TERM_END` | `BREAKAGE_INCLUDING_EXPECTED_ROLLOVER_USE` | same as 606 | n/a | P | K | EST | 606-10-55-46 to 55-48 [F]. [J] Rolled credits are rights the customer is expected to exercise; only credits expected never to be used are breakage | PT-02 | BRK, MR |
| POL-242 | `termination.refund_settlement` | How is a refund agreed on termination settled in the ledger? | `REFUND_LIABILITY_UNTIL_CREDIT_MEMO` | FORCED | FORCED | n/a | T | P | FIX | 606-10-32-10 [F] | JET-04b to the refund amount; the credit memo brings it to zero | MOD, RET |
| POL-243 | `concession.allocation_basis` | How is a price concession on transferred goods allocated? | `INCEPTION_BASIS`, `TARGETED_WHEN_32_40_ATTESTED` | `INCEPTION_BASIS` | same as 606 | `TARGETED_WHEN_32_40_ATTESTED` (legacy POB-specific VC) | C | K | OVR | 606-10-32-43, 32-44 [F]. [J] 32-43 is the default basis; targeting needs the 32-40 attestation | PT-04 | VC, ALC |
| POL-244 | `claims.recognition_gate` | When is a claim included in the transaction price? | `ENFORCEABLE_ATTESTED_AND_CONSTRAINED` | FORCED | FORCED | n/a | C | K | JDG and EST | 606-10-25-10, 25-11; FASB Example 9 [F] | PT-05 | MOD, VC |
| POL-245 | `portfolio.results_attribution` | How are portfolio estimates applied to contracts? | `PORTFOLIO_RATE_PER_CONTRACT` | FORCED | FORCED | n/a | T | K | FIX | 606-10-10-4 [F]. [J] Per-contract results keep drill-down and D-12 netting per contract | PT-06 | ONB, RET, BRK |
| POL-246 | `cpc.share_based_timing` | When does share-based consideration payable to a customer reduce revenue? | `LATER_OF_RELATED_REVENUE_AND_GRANT` | FORCED | FORCED | n/a | C | K | EST | 606-10-32-25A, 32-27, 55-88A to 55-88C as amended by ASU 2025-04 [F] | PT-10 | CPC |

### 5.1 PT-01 Tiered usage and annual minimum true-up

**Issue.** A usage fee under cumulative tiers, or subject to an annual minimum, cannot be allocated to the period of usage because the fee for a period depends on usage in other periods (32-40(b) fails).

**Policy.** POL-240 `DERIVED` gives `ESTIMATE_MEASUREMENT_PERIOD_TP`.

**Algorithm.** For the stand-ready series POB over the measurement period: TP = max(minimum commitment, expected usage fees under the tier schedule), constrained (EST, POL-041). Revenue is time elapsed (POL-090). Each period's new estimate version triggers ALG-10 (JET-04a). Overage invoices and a shortfall true-up invoice are ingested as billing.

CHK-110 [A]: calendar-year contract; minimum commitment 120,000.00 billed 30,000.00 per quarter in advance; tiers 0.10 per call for the first 1,000,000 calls and 0.08 above, applied to annual cumulative usage; `MONTHLY_EVEN` (a whole-month term, so the values of the retired option are unchanged). At inception expected usage 1,500,000 calls (fees 140,000.00, TP 140,000.00). At the end of Q2 expected usage 1,200,000 calls (fees 116,000.00, TP 120,000.00). Actual usage 1,100,000 calls (fees 108,000.00, no overage).

| Quarter | Revenue | Of which revenue from prior-period performance | Billed | Contract asset (end) |
|---|---|---|---|---|
| Q1 | 35,000.00 | 0.00 | 30,000.00 | 5,000.00 |
| Q2 | 25,000.00 | −5,000.00 | 30,000.00 | 0.00 |
| Q3 | 30,000.00 | 0.00 | 30,000.00 | 0.00 |
| Q4 | 30,000.00 | 0.00 | 30,000.00 | 0.00 |

The third column is the 606-10-50-12A portion of ALG-10 §2.11.3: round((120,000.00 − 140,000.00) × 3/12) = −5,000.00. It is not the sequential catch-up of REQ-MOD-015, which is −10,000.00 when the estimate version is effective on 30 June: round(120,000.00 × 6/12) − 70,000.00 posted at the inception price through 30 June (ENGINE_SPEC_B S09-R-37). The CHK-110 key asserts `revenue_prior_period` −5,000.00 and `catch_up_tp_change_cum` −10,000.00. Rev 1.2 renames the column, which rev 1.1 labelled "Of which catch-up" (D-76 ruling on `ENGINE_SPEC_B:OQ-B-06`).

### 5.2 PT-02 Rollover of unconsumed credits into a renewal

**Policy.** POL-241 and POL-055.

**Algorithm.** Credits consumed → JET-02. Expected breakage B = credits expected never to be used, excluding credits expected to be used after rollover. Breakage revenue to date = B × cumulative credits used ÷ expected total credits used, including expected rollover use (cumulative rounding). If the renewal does not occur, the remaining balance of rolled credits is recognised when the rights lapse.

CHK-111 [A]: 100,000.00 of credits for Year 1; 70,000 used in Year 1; 20,000 expected to be used in Year 2 after renewal; 10,000 expected never to be used. Year 1: revenue 70,000.00 + breakage 7,777.78; contract liability at year end 22,222.22. Year 2 (renewed): revenue 20,000.00 + breakage 2,222.22; liability 0.00. Not renewed: 22,222.22 recognised at lapse.

### 5.3 PT-03 Termination for convenience with refund and commission acceleration

**Policy.** POL-014 (enforceable term), POL-242, POL-145.

**Algorithm.** An agreed termination is a modification that reduces scope (ALG-04, prospective; DART 9.2.2.7: a scope reduction cannot be a separate contract). The refund of prepaid consideration for undelivered service enters the pool as a negative ΔC. JET-04b recognises the refund liability until the credit memo. The remaining cost asset is expensed through JET-09e.

CHK-112 [A]: subscription billed 120,000.00 per year in advance; commission 36,000.00 capitalised and amortised over 36 months (renewal commissions not commensurate, POL-141). At month 18 the customer terminates with a refund of 60,000.00 for months 19 to 24. Pool = 60,000.00 − 60,000.00 = 0.00, so no remaining POB. JET-04b Dr CL 60,000.00 / Cr REFUND_LIABILITY 60,000.00; after the credit memo (ERP Dr CL 60,000.00), JET-04b Dr REFUND_LIABILITY 60,000.00 / Cr CL 60,000.00. JET-09e Dr CONTRACT_COST_AMORTIZATION 18,000.00 / Cr COST_TO_OBTAIN_ASSET 18,000.00. Final: revenue 180,000.00; position 0.00; cost asset 0.00.

### 5.4 PT-04 Concessions and credit memos on billed amounts

**Policy.** POL-243; POL-104; JET-05c or JET-04b.

**Algorithm.** A concession on transferred goods is a transaction-price change (606-10-32-42 to 32-44). It is allocated on the inception basis, or entirely to the POB when the 32-40 criteria are attested. Revenue on satisfied portions changes immediately. The amount to be credited or refunded is a refund liability until the credit memo is ingested (606-10-32-10). The legacy rule blocking negative remaining billing (legacy 05 DEF-pob-vc-07) does not exist in eRev Cloud.

CHK-113 (legacy 05 TC-pob-vc-16 corrected value): golden Contract 2 POB #2 fully delivered and billed (posted cumulative revenue 385.19); concession −60.00 targeted (POL-243 attested). Dr REVENUE 60.00 / Cr REFUND_LIABILITY 60.00; POB #2 cumulative revenue 325.19. On the credit memo: ERP Dr CL 60.00 / Cr AR 60.00; JET-04b Dr REFUND_LIABILITY 60.00 / Cr CL 60.00.

### 5.5 PT-05 Unpriced change orders and claims

**Policy.** POL-105, POL-244.

**Algorithm.** An approved scope change with an undetermined price is a modification (25-10, 25-11). The price change is a VC estimate version of type `UNPRICED_CHANGE_ORDER` (`MOST_LIKELY_AMOUNT`, constrained) used as ΔC in ALG-04. A claim enters the transaction price only after the enforceability attestation. Settlement is ALG-10.

CHK-115 [A]: single cost-to-cost POB; TP 1,000,000.00; EAC 800,000.00; costs 400,000.00; revenue 500,000.00. An approved change adds 100,000.00 of costs; the most likely price increase is 120,000.00, constrained to 90,000.00. ALG-04 (pure 25-13(b)): A′ 1,090,000.00; f′ = 400,000 ÷ 900,000; cumulative 484,444.44; JET-05a −15,555.56. The price is agreed at 110,000.00 when costs are 600,000.00: cumulative before settlement 726,666.67; JET-04a +13,333.33; cumulative 740,000.00.

### 5.6 PT-06 Portfolio approach with actual-versus-estimate true-up

**Policy.** POL-015, POL-245.

**Algorithm.** The portfolio estimate (return rate, breakage rate or redemption rate) is an estimate version with scope `PORTFOLIO`. It is applied to each contract's quantities with exact rationals (fractional expected units allowed), so contract results sum to the portfolio result. At cohort close, the actual outcome replaces the estimate through ALG-10.

CHK-116 [A]: 50 contracts × 10 units at 100.00; portfolio expected return rate 4%. Per contract: E = 0.4 units, revenue 960.00, refund liability 40.00; portfolio revenue 48,000.00 and refund liability 2,000.00. Actual returns 25 units (5%), refunded: at cohort close revenue 47,500.00 (true-up −500.00); refund liability 0.00.

### 5.7 PT-07 ASC 326 credit losses on contract assets

**Policy.** POL-125 `EXTERNAL_MODEL`.

**Algorithm.** At each period end the engine exports, per entity, book and currency, the presented contract assets, unbilled receivables and (in `ENGINE` billing mode) receivables by age bucket (0 to 30, 31 to 60, 61 to 90, 91 to 180, over 180 days since the oldest unconsumed asset layer arose). It records the ASU 2025-05 practical-expedient and collection-activity elections as disclosure metadata. Credit losses never adjust revenue (606-10-45-3, 45-4; research 04 §1.2).

CHK-117 (population export): the export totals equal JET-06 at the same period end (CHK-010: unbilled receivable 3,000.00 and contract asset 2,000.00, both in the 0 to 30 day bucket when the revenue arose in the period).

### 5.8 PT-08 Sale of nonfinancial assets to noncustomers (Subtopic 610-20)

**Policy.** POL-230 `ROUTE_OUT`.

**Algorithm.** Intake flags `counterparty_is_customer = false` together with an asset type of property, plant and equipment, intangible asset or in-substance nonfinancial asset (ASU 2017-05). The item is excluded from every book with scope code `ASC610_20`. The consideration measured under the 606 transaction-price principles is exported for the ERP. No revenue, schedule or journal is produced.

### 5.9 PT-09 Embedded lease components (Topic 842 hand-off)

**Policy.** POL-231.

**Algorithm.** Lease components are allocation targets with SSPs. The lessor allocates the consideration using 606-10-32-28 to 32-41 (842-10-15-38 to 15-42). After allocation, the lease allocation is routed out as `LEASE_COMPONENT_ALLOCATION` for the lease system (no schedules, no journals). When POL-231 = `ELECTED` and the 842-10-15-42A criteria are met, the combined component is accounted for entirely under Topic 606 as a single POB if the nonlease components are predominant; otherwise the whole combined component is routed out as an operating lease (842-10-15-42B, added by ASU 2018-11) [F].

CHK-118 [A]: TP 10,000.00; equipment lease SSP 9,000.00; maintenance SSP 3,000.00. Allocation: lease 7,500.00 (routed out); maintenance 2,500.00 (Topic 606 POB).

### 5.10 PT-10 Share-based consideration payable to a customer

**Policy.** POL-246; ASU-18 and ASU-23.

**Algorithm.** An estimate version of kind `SHARE_BASED_CONSIDERATION` (04 E-09; D-76 on OQ-14) holds the grant-date fair value from the Topic 718 system, the vesting-probability conclusion, expected forfeitures (evidence only) and the expected related revenue; its `rationale` states the basis of `vesting_probable` (Topic 718 probability without the 606 constraint under ASU 2025-04, 55-88C; before adoption, the constraint conclusion). Cumulative reduction = grant-date fair value × (vesting probable ? 1 : 0) × cumulative related revenue ÷ expected related revenue, capped at the fair value, where cumulative related revenue is the posted revenue recognised for the related obligations (the share-based promise's `related_obligation_keys`; empty = the contract; the element's keys when no share-based promise exists), gross of consideration payable, net of returns and of concessions, each concession counted once (ENGINE_SPEC_B S10-R-26), and never measured on invoices; revenue recognised before the grant date counts once the grant exists, so the reduction is recognised at the later of the related revenue and the grant (POL-246; 606-10-32-27). In the rc `expected_total_amount` is measured on the same all-related-revenue population as the numerator (a `related_revenue_start` window is post-rc). The period change posts by JET-14: Dr `REVENUE` / Cr `BILLING_CLEARING` (`clearing_purpose` `EQUITY`), rounded once per element and period on its own (two elements each exact 0.005 post 0.02); an ordinary incentive release on the same contract is rounded and posted separately and the two parts sum to the revenue reduction with no further rounding (ENGINE_SPEC S04-R-16, S04-R-17, ENGINE_SPEC_B S14-R-01; D-91). Changes due to the form of the consideration after grant date are excluded (32-25A). ASU 2025-04 is applied universally in the rc (as ASU 2025-07 is); an adoption profile is post-rc (D-91).

Share-based noncash consideration received from a customer is a different fact pattern: it follows POL-048 and JET-17 under ASU-25.

CHK-120 [A]: warrants with grant-date fair value 50,000.00 vest if the customer buys at least 1,000,000.00 in two years (performance condition, probable). Year 1 purchases 400,000.00 → reduction 20,000.00; Year 2 purchases 600,000.00 → reduction 30,000.00. If vesting becomes not probable at the end of Year 1, the cumulative reduction is reversed to 0.00. The figures are the same whether purchases are invoiced in advance, at delivery or in arrears; a grant on 1 July 2026 after the 400,000.00 purchase reduces revenue by 20,000.00 in July 2026 (D-91).

### 5.11 PT-11 Business-combination onboarding (M-RA-06)

**Policy.** POL-210, POL-215 to POL-217.

**Algorithm.**

1. An `OPENING_BALANCE_ESTABLISHED` event with payload `reason` `BUSINESS_COMBINATION` carries the acquisition id, acquisition date and the POL-216 and POL-217 elections (one set per acquisition, 805-20-30-30).
2. ASC606 book: each acquired contract is computed as if originated (805-20-30-28): inception data, or the expedients (30-29(a) aggregate pre-acquisition modifications; 30-29(b) SSP at the acquisition date). The resulting contract liability, contract asset and unbilled receivable at the acquisition date are established as engine opening state (`OPENING_BALANCE_ESTABLISHED`, payload `reason` `BUSINESS_COMBINATION`), not as journal lines. Purchase accounting in the GL belongs to the ERP or consolidation system (consistent with `docs/reviews/objections-arch-data.md`, note on D-31 opening balances). Refund liabilities acquired are outside ASU 2021-08 and are imported at the acquirer's measurement.
3. IFRS15 book: the acquisition-date fair value of the contract liability is an input from the valuation (IFRS 3.18). It is apportioned over the remaining POBs by their ASC606-measured remaining allocations (ALG-01); revenue thereafter recognises those amounts.
4. The contract-balance rollforward shows the opening amounts on the line "business combinations" (606-10-50-10(a); IFRS 15.118(a)).

CHK-121 [A]: 24-month subscription for 240,000.00 billed upfront on 1 January 2025; acquisition on 1 January 2026. ASC606 book: opening contract liability 120,000.00; 2026 revenue 10,000.00 a month. IFRS15 book with valuation 90,000.00: 7,500.00 a month. Expedient (b): contract TP 200,000.00 billed at inception; inception SSPs licence 150,000.00 and two-year support 50,000.00; acquisition-date SSPs 120,000.00 and 80,000.00; after one year the opening support liability is 25,000.00 as if originated, or 40,000.00 with the expedient.

---

## 6. Cross-reference tables

### 6.1 M-RA-01 policy questions

| M-RA-01 item | Sources in the corpus | POL | 606 default | Parity |
|---|---|---|---|---|
| Material-right exercise approach | legacy-03:OQ-01; legacy-06:OQ-07; legacy 07 J1 | POL-028; ALG-05 | `CONTINUATION` | `MODIFICATION` |
| Returns reversal rate | legacy-02:OQ1 | POL-051, POL-052, POL-053; ALG-06 | `EXPECTED_RETURNS`; `AVERAGE_CARRYING_RATE`; `REDUCE_CONTRACT_QUANTITY` | `ACTUAL_RETURNS_ONLY`; `CURRENT_REMAINING_RATE`; `RESTORE_REMAINING_QUANTITY` |
| Reclass allocation key | legacy-02:OQ2; legacy-03:OQ-04 | POL-121; ALG-02 step 5, whose fallback chains end in the terminal resolved-SSP step (positive by POL-077) | `POB_DEBIT_POSITIONS` | `CUMULATIVE_SSP_DELIVERED` |
| Cross-entity netting | legacy-02:OQ3; legacy-04:OQ4; legacy-06:OQ-09 | POL-120 (fixed: contract × entity × book), POL-170; ALG-07 | per entity; `PERFORMING_ENTITY` | per entity; `PERFORMING_ENTITY` |
| Contract asset vs unbilled receivable | legacy-04:OQ4; legacy-06:OQ-02 | POL-122, POL-123; ALG-03 | table 2.4-A | table 2.4-A, one account |
| SSP out-of-range point | legacy-06:OQ-11; legacy 01 §7.4 | POL-071, POL-072, POL-073; section 3.4 | `CONTRACT_PRICE`; `NEAREST_BOUND` | same |
| Rounding mode | legacy-06:OQ-03; legacy-04:OQ5 | POL-001 to POL-003; ALG-01 | `HALF_UP`, largest remainder, cumulative | same |
| Catch-up scope for retrospective modifications | legacy-04:OQ1 | POL-102, POL-103, POL-107; ALG-04 | `PARTIALLY_SATISFIED_NONDISTINCT_ONLY`; `REMAINING_TP` | `ALL_POBS_FULL_REALLOCATION`; `TOTAL_TP` |
| Series vs single non-distinct in migration | legacy-03:OQ-06 | POL-211 | `REVIEW_QUEUE` | `SINGLE_POB` |
| Price-only changes on satisfied POBs | legacy-03:OQ-07 | POL-104; ALG-04 step 2 | `RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS` | `POOL_WITH_REMAINING` |
| Backdated events | legacy-02:OQ6; legacy-04:OQ6; legacy-06:OQ-06 | POL-180, POL-181; ALG-09 | first open period with origin | same |
| VC estimates held or deltas only | legacy 05 §3.4 | POL-043, POL-182; ALG-10 | full estimate versions | delta import converted to versions |
| SSP basis for modifications (C-09) | legacy-03:OQ-02; legacy-04:OQ2; research-06:Q8 (§22.2) | POL-080, POL-081; ALG-04 | `D18_DEFAULT` | `LEGACY_CARRIED_PLUS_FILE_VERSION` |
| Billing journal ownership (C-03) | legacy-02:OQ4; legacy-06:OQ-01 | POL-004; JET-03 | `ERP` | `ERP` |
| Delta source (pre-standard revenue) | legacy-06:OQ-05; legacy-03:OQ-08 | POL-008; JET-15 | `PRE_STANDARD_EVENTS` | same |
| JE granularity | legacy-06:OQ-04 | POL-006 | entity × book × currency × period × account × dimensions | `LEGACY_CONTRACT_POB` |

### 6.2 Research 04 §13 IFRS 15 switch list (C-12)

| # | Area | POL | IFRS15 book value |
|---|---|---|---|
| 1 | Collectibility threshold | POL-011 | `IFRS_PROBABLE` (no numeric threshold in either book) |
| 2 | Contracts failing Step 1, event (c) | POL-012 | `DISABLED` |
| 3 | Immaterial promises | POL-020 | `ASSESS_ALL` |
| 4 | Shipping and handling after control | POL-021 | `FALSE` |
| 5 | Sales taxes | POL-045 | `ASSESS_EACH_TAX` |
| 6 | Noncash consideration measurement date | POL-048 | tenant choice, default `CONTRACT_INCEPTION` |
| 7 | Nature of a licence | POL-024 | `ACTIVITIES_SIGNIFICANTLY_AFFECT_IP` |
| 8 | Licence renewals | POL-025 | `LATER_OF_AGREEMENT_AND_AVAILABILITY` |
| 9 | Licence inside a combined POB; attributes vs additional rights | POL-232 | same behaviour as ASC606 |
| 10 | Contract cost impairment reversal | POL-144 | `REQUIRED_CAPPED` |
| 11 | Onerous contracts | POL-150, POL-151, POL-152 | contract unit; all contracts with EAC; IAS 37.68A costs |
| 12 | Interim disclosures | POL-203 | IAS 34.16A(l) |
| 13 | Nonpublic relief | POL-191 to POL-196 | not available |
| 14 | Franchisor expedient | POL-202 | not available |
| 15 | Transition expedients and completed-contract definition | POL-218 | IFRS 15.C3 to C8 |
| 16 | Effective date | POL-218 (informational) | none |
| 17 | ASU 2016-20 disclosure additions | POL-199, POL-200, POL-204; section 4.3 | 50-12A equivalent (IFRS 15.116(c)) applies; 50-14A exemptions not available |
| 18 | Repurchase lease outcome | POL-233, POL-231 | IFRS 16 hand-off; no lessor combination expedient |
| extra | Business combinations | POL-215 | `FAIR_VALUE_IFRS3` |
| extra | FX transaction date for advances | POL-160, POL-163 | IFRIC 22 layering forced |

Research 06 §11.2's "75% probable" parameter is not encoded (U-01).

### 6.3 `LEGACY_PARITY` preset (D-32)

| D-32 element | POL values under the preset |
|---|---|
| Clamp out-of-range prices to the nearest SSP range boundary | POL-071 `CONTRACT_PRICE`; POL-072 `NEAREST_BOUND`; POL-073 `NOT_ENFORCED`; POL-081 `CLAMPED_MOD_PRICE` |
| Material-right dollar-quantity convention | POL-026 `ENTERED_AMOUNT`; POL-212 `KEEP_QUANTITY_CONVENTION`; POL-028 `MODIFICATION` |
| Full retrospective re-allocation for 25-13(b) | POL-100 `USER_SELECTED_TEMPLATE`; POL-102 `ALL_POBS_FULL_REALLOCATION`; POL-103 `TOTAL_TP` (retrospective template); POL-107 `LEGACY_BY_TEMPLATE`; POL-080 `LEGACY_CARRIED_PLUS_FILE_VERSION`; POL-104 `POOL_WITH_REMAINING` |
| Reclass allocation keyed on cumulative SSP delivered | POL-121 `CUMULATIVE_SSP_DELIVERED`, with the ALG-02 step 5 weight chain: cumulative SSP delivered, cumulative revenue, posted allocation, then the terminal resolved-SSP step (DEV-058) |
| Single unbilled A/R account per POB | Mapping preset: `CONTRACT_ASSET` and `UNBILLED_RECEIVABLE` → the POB's "Unbilled A/R Account"; `CONTRACT_LIABILITY` → "Deferred Revenue Account"; `REVENUE` → SKU "Revenue Account"; POL-122 table 2.4-A |
| `billing_posting = erp` (D-32 wording; registry literal per D-13a) | POL-004 `ERP` |
| Gross and adjustment JE formats | POL-005 `GROSS` with the adjustment report; POL-006 `LEGACY_CONTRACT_POB`; POL-007 {`ASC606`, `LEGACY`}; POL-008 `PRE_STANDARD_EVENTS` |
| Other legacy policies (not defects) | POL-014 `STATED_TERM`; POL-016 0; POL-021 `FALSE`; POL-022 `EXTERNAL`; POL-030 `PRINCIPAL`; POL-040 `ENTERED_AMOUNT`; POL-041 `NOT_APPLIED`; POL-042 `NOT_ENFORCED`; POL-043 `DELTA`; POL-044 `NOT_ENFORCED`; POL-051 `ACTUAL_RETURNS_ONLY`; POL-052 `CURRENT_REMAINING_RATE`; POL-053 `RESTORE_REMAINING_QUANTITY`; POL-070 `NAMED_VERSION`; POL-076 `DISABLED`; POL-091 `UNITS_DELIVERED`; POL-124 `NONE`; POL-211 `SINGLE_POB`; POL-243 `TARGETED_WHEN_32_40_ATTESTED` |

The preset reproduces legacy policies, not legacy defects (D-32). The corrected values cited in this document (legacy D-06 dropped pool, D-10 and DEF-pob-vc-03 pre-standard carry-forward, DEF-pob-vc-01 latent true-up, DEF-pob-vc-07 concession block, the 0.01 JE imbalances, split-upload allocation, the setup negative-quantity clamp, backdated version order) belong in `docs/legacy/DEVIATIONS.md` (D-17).

### 6.4 Decision coverage

| Decision | Where implemented |
|---|---|
| D-11, D-11a | ALG-01 (§2.1.3 confirmed by D-11a); POL-001 to POL-003; CHK-001 to CHK-007 |
| D-12 | Section 0.9; ALG-02 (step 5 fallback chains with the terminal resolved-SSP step; financing accretion in NP under D-76); POL-120 |
| D-13, D-13a | POL-004 (`billing.posting` `ERP`, `ENGINE`); JET-03; JET-04c; JET-06 |
| D-14, D-14a | Section 0.8 and table 0.8-A; every JET (rule R8) |
| D-15 | ALG-03; POL-122, POL-127; section 6.3 mapping preset |
| D-16 | JET rule R1; section 0.8 `ROUNDING` |
| D-17, D-17a | Section 2.1.5 legacy note; POL-001 (class DEV-002); section 2.5.7; section 6.3 |
| D-18 | ALG-04; POL-080, POL-081 |
| D-19 | ALG-09; POL-180, POL-181 |
| D-20 | ALG-10; POL-043, POL-182 |
| D-21, D-21a | ALG-05; POL-026, POL-028 |
| D-22 | ALG-06; POL-051 to POL-053, POL-078 |
| D-23 | ALG-07; POL-120, POL-170, POL-171 |
| D-24 | POL-007, POL-008; section 6.2 |
| D-25, D-25a | ALG-08; POL-160 to POL-164 (POL-163 contract override) |
| D-25b | POL-164 `ASSET_POSITIONS_ENGINE_AR_AND_MONETARY_LIABILITIES`; ALG-08 §2.9.1 and §2.9.2; JET-10d; CHK-084 |
| D-26 | Section 4 |
| D-32 | Section 6.3 |
| D-34 | JET-15 |
| D-73 | Section 0.3 rule 3; POL-074 and section 3.1 (E-47 literals); tables 2.3-A and 2.3-B (E-03 and E-31 literals); ALG-10 §2.11.1 (E-09 literals) |
| D-74 | Precedence row of the header |
| D-75 | Section 8; POL-090 and ALG-11 (ruling on B1 §8 Q3) |
| D-76 | Financing interest: ALG-02 definition and step 3, CHK-137. SFC rate: POL-047 `compounding`, JET-11, CHK-136. CHK re-baselines: CHK-006, CHK-053. Contract-cost impairment: JET-09c. Uninstalled materials: POL-091, JET-02, section 0.8, OQ-15. Adopted defaults: POL-022, POL-044, POL-045, POL-051, POL-052, POL-076, POL-094, new POL-095, POL-200; ALG-04 §2.5.5; ALG-06 step 6; ALG-08 §2.9.1; ALG-10 §2.11.1 and §2.11.3; JET-01b, JET-02, JET-04, JET-05, JET-07, JET-09f, JET-10c, JET-12, JET-16, JET-17; PT-01 CHK-110; PT-10; section 8 |
| D-77 | Revision log rev 1.2 "Decisions taken in B3"; no open question added |

---

## 7. Gaps closed

| Gap | Closure | Where |
|---|---|---|
| M-RA-01 | Policy register with defaults for both books, parity values, levels, pinning, approval, authority and engine effect | Section 1; section 5.0; section 6.1 |
| C-09 | Exact SSP-basis algorithm for 25-13(a), (b) and (c), including added non-distinct goods and reductions | ALG-04; POL-080, POL-081; CHK-027, CHK-028, CHK-042, CHK-043 |
| C-12 | All 18 research 04 §13 switches mapped to book parameters | Section 6.2 |
| C-15 | SSP-range authority verified (DART 7.3.3.6) | Section 4.3 |
| U-01 | Unsupported as Codification; no numeric threshold encoded | POL-011; section 4.3 |
| U-02 | Verified as practice; tenant parameters with `WARN` defaults | POL-073; section 3.3; section 4.3 |
| U-03 | ASU register through ASU 2026-03 with URLs and engine effect | Section 4 |
| U-04 | 606-10-50-11 covers 50-12A | POL-192; section 4.3 |
| U-08 | Vendor-blog authority replaced by Codification, IFRS 15 and DART | Section 4.3 |
| C-07 (policy side) | Cumulative rounding with no plug; research 04 keys re-baselined | ALG-01; CHK-004, CHK-006 |
| C-06 (policy side) | Currency exponent checks for JPY and BHD | CHK-003a, CHK-003b |
| C-02 (policy side) | Sign convention and labelled balances | Section 0.9; ALG-02 |
| C-03 (policy side) | Billing ownership and posting templates for both modes | POL-004; JET-03; POL-123 |
| C-04 (policy side) | Role semantics fixed, including the D-14a roles and `clearing_purpose` | Section 0.8; table 0.8-A |
| C-14 (policy side) | Delta posting template against the `LEGACY` book | JET-15; CHK-020 |
| M-RA-02 (policy side) | Layering, remeasurement, IFRIC 22, the D-25 flag and the D-25b monetary liabilities with exact checks | ALG-08; JET-10c, JET-10d; CHK-080 to CHK-084 |
| OBJ-B-01 (`docs/reviews/objections-engine-spec-b.md`) | D-25b applied: refund liabilities, deposit liabilities and consideration payable are monetary items remeasured at the closing rate and at settlement in every book | POL-164; ALG-08 §2.9.1; JET-10d; CHK-084 |
| M-RA-03 (policy side) | Cross-entity algorithm with entity-balanced postings | ALG-07; CHK-070, CHK-071 |
| M-RA-05 | Tiered usage and minimums, credit rollover, termination for convenience, concessions on billed amounts, unpriced change orders and claims, portfolio approach, ASC 326 on contract assets, 610-20, embedded leases, share-based consideration payable | PT-01 to PT-10 |
| M-RA-06 | Business-combination onboarding under ASU 2021-08 and IFRS 3 | PT-11; POL-215 to POL-217; ASU-21 |
| M-RA-08 (partial) | Scope routing for 610-20, leases, collaborations and contributions | POL-230, POL-231, POL-234; ASU-16 |

---

## 8. Open questions for supervisor

Rev 1.1: D-75 adopts the recommended default of OQ-01 to OQ-12, with a specific ruling on OQ-05. OQ-13 to OQ-15 are new in rev 1.1.

Rev 1.2: D-76 adopts the recommended defaults of OQ-13 to OQ-15, with a specific ruling on OQ-15 (uninstalled materials). Under D-77 no open question is added; the defaults taken in B3 are logged in the revision log.

| ID | Question | Recommended default | Status and ruling |
|---|---|---|---|
| OQ-01 | Adopt objection O-1, which concurs with `docs/reviews/objections-arch-data.md` OBJ-01 (missing counter-entry roles)? | Adopt one D-14a: `COST_OF_REVENUE`, `CONTRACT_COST_CLEARING`, and a purpose-coded clearing role for supplier payables, equity, unapplied cash and investments | Resolved by D-75 (D-14a): `COST_OF_REVENUE`, `CONTRACT_COST_CLEARING` and `RECEIVABLE_CONTRA` added; `BILLING_CLEARING` kept with `clearing_purpose`; `RETAINED_EARNINGS` and `FINANCING_OBLIGATION` reserved. Applied in section 0.8, table 0.8-A and section 2.3 |
| OQ-02 | Adopt the answer-key family codes (section 0.7) as the `families` vocabulary for `docs/accounting/answer-keys/`? | Adopt as written | Resolved by D-75: adopted; section 0.7 is the `families` vocabulary |
| OQ-03 | POL-170 default revenue entity when performing ≠ contracting entity | `PERFORMING_ENTITY` (legacy per-POB selling entity; D-23 intercompany pairs) | Resolved by D-75: `PERFORMING_ENTITY` (POL-170) |
| OQ-04 | POL-103 default for mixed modifications | `REMAINING_TP` (DART 9.2.2 Alternative B) | Resolved by D-75: `REMAINING_TP` (POL-103) |
| OQ-05 | Treat `CONTRACT_ASSET` and `UNBILLED_RECEIVABLE` as presentation-only roles fed by JET-06, with `CONTRACT_LIABILITY` as the gross control role (section 0.8), in `docs/accounting/ENGINE_SPEC.md` and `docs/04-DATA_MODEL.md` | Adopt; it makes D-12 net_position a ledger balance and keeps ERP-mode tie-out exact | Resolved by D-75 (specific ruling): contract asset and unbilled receivable are presentation balances derived at period end, and the netting reclass (D-13) is still posted as an auto-reversing journal (JET-06; section 0.8) |
| OQ-06 | Do the nonpublic elections (POL-191 to POL-193) continue to limit interim packs once ASU 2025-11 applies? | Yes (POL-203). Confirm against the online Codification before G12 | Resolved by D-75: yes (POL-203); the online-Codification confirmation is a G12 review step |
| OQ-07 | Fourteen ASUs could not be retrieved (section 4.1), including ASU 2017-14 | Treat them as having no engine effect; the supervisor or reviewer confirms in the online Codification before G12 | Resolved by D-75: no engine effect; the online-Codification confirmation is a G12 review step |
| OQ-08 | The ASU that extended 606-10-50-11 to 50-12A was not identified in the texts retrieved | Follow the current text as quoted by DART 15.2 (POL-192 covers 50-12A) | Resolved by D-75: POL-192 covers 50-12A per DART 15.2 |
| OQ-09 | `docs/legacy/DEVIATIONS.md` must carry the corrected values this document relies on (section 6.3 list; CHK-006 re-baselines; CHK-091; CHK-113) | The DEVIATIONS author imports them with a reference to the CHK id | Resolved by D-75: the DEVIATIONS author imports the corrected values with a reference to the CHK id |
| OQ-10 | POL-142 commensurate ratio | 1.00 | Resolved by D-75: 1.00 (POL-142) |
| OQ-11 | RPO exemptions (POL-197 to POL-200) default | `DO_NOT_APPLY` (full RPO computed and disclosed unless the tenant elects) | Resolved by D-75: `DO_NOT_APPLY` (POL-197 to POL-200) |
| OQ-12 | ALG-01 §2.1.3 rounds the exact cumulative revenue (the literal D-11 rule) and aligns the completion step to the posted allocation. This answers `docs/reviews/objections-ra-deviations.md` O-3, whose case list was generated with round(posted allocation × progress) | Regenerate the `docs/legacy/DEVIATIONS.md` case list with the exact-cumulative rule, and approve the remaining one-cent report-rounding differences as a single class (objections-ra-deviations O-2) | Resolved by D-75 (D-11a, D-17a): ALG-01 §2.1.3 confirmed as published; the parity case list is regenerated under posting rule `EXACT-CUM`; the remaining cent differences form one deviation class, DEV-002 |
| OQ-13 | 04 E-03 payloads carry no warranty claim cost (`COST_INCURRED` payload `purpose` ∈ {`PROGRESS_INPUT`, `COST_TO_OBTAIN`, `COST_TO_FULFILL`}) and no noncash receipt (`PAYMENT_RECEIVED` payload `amount` is money), so the JET-16 claim line and the JET-17 receipt line have no trigger | 04 adds `WARRANTY_CLAIM` to `COST_INCURRED.purpose` and a noncash form of `PAYMENT_RECEIVED` (units received and carrying amount). Until 04 does, the engine posts only the JET-16 accrual and the JET-17 unconditional-right line, and the claim release and the receipt stay ERP postings | Resolved by D-76: recommended default adopted; 04 adds `WARRANTY_CLAIM` to `COST_INCURRED.purpose` and a noncash form of `PAYMENT_RECEIVED`. JET-16, JET-17, table 2.3-B and POL-022 cite the triggers (rev 1.2) |
| OQ-14 | 04 E-09 has no estimate kind for share-based consideration payable to a customer (PT-10) | 04 E-09 adds `SHARE_BASED_CONSIDERATION` | Resolved by D-76: recommended default adopted; ALG-10 §2.11.1 and PT-10 cite the literal (rev 1.2) |
| OQ-15 | D-14a lists fulfilment-cost release where elected and zero-margin uninstalled materials among the `COST_OF_REVENUE` uses, but no POL election makes the engine post those costs: carrier-cost accruals (POL-021), costs of immaterial promises (POL-020) and uninstalled materials (POL-091) are ERP postings | No new POL in 1.0. The engine posts `COST_OF_REVENUE` only in JET-07c and in the JET-16 claim release under POL-022 `ENGINE`; uninstalled materials post zero-margin revenue through JET-02 and their cost stays in the ERP | Resolved by D-76 (specific ruling on uninstalled materials): the ERP posts the cost; the engine recognises revenue equal to cost (zero margin) and posts no `COST_OF_REVENUE` line; REQ-REC-007 is amended. Applied in POL-091, JET-02 and section 0.8 (rev 1.2) |
