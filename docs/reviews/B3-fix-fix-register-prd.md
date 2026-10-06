# B3 fix pass: requirements register, glossary and PRD (slug `fix-register-prd`)

| Field | Value |
|---|---|
| Author | Owner-editor, design phase B3 (slug `fix-register-prd`) |
| Date | 2026-09-12 |
| Files edited | `docs/03-REQUIREMENTS.md` rev 1.1 → 1.2 (1,259 lines; SHA-256 `10113ff56b873f285ecceec9da3e443de7b24f8c5db4d664bbcff005b307fd52`). `docs/GLOSSARY.md` rev 1.1 → 1.2 (226 lines; SHA-256 `254b837616d946510282804a5525974feac2dd90247dff9732280fe20ad172a1`). `docs/02-PRD.md` rev 1.1 → 1.2 (1,993 lines; SHA-256 `0b9a141a3a0d64244376084a41ed0fb1abf4b78c8da6c3a208f8a872b3e111c7`). Baseline copies: `.scratch/b3-fix-register-prd/baseline-rev1.1/` |
| Binding inputs | `docs/01-DECISIONS.md` D-25b, D-76, D-77; `docs/design/SCREENS.md` §4.1, §16 (OQ-S-01, -02, -10, -11, -17), SCR-LTH-10 to -13; `docs/design/SCREENS_B.md` §3.2, §9.7, §11.2, §16, §18 (OQ-B-19, -29, -31, -32); `docs/accounting/POLICIES.md` rev 1.2 (POL-047, POL-164, JET-10d, ALG-02, JET-11, CHK-022, CHK-137); `docs/04-DATA_MODEL.md` rev 1.2 (E-86, E-110, table 1.2-D); `docs/accounting/ENGINE_SPEC.md` OQ-A-11 to -13, -20; `docs/accounting/ENGINE_SPEC_B.md` OQ-B-04, -08, -09, S09-R-14, S11-R-09; `docs/05-ARCHITECTURE.md` OQ-ARC-12; `docs/legacy/golden/deviations.json` (SHA-256 `a8ac329dccc955ca46de75f30868f668d343641612fa279fd2d1b23cfadd53ae`) |
| Self-check | `.scratch/b3-fix-register-prd/`: `register_glossary_check.py` (tables and undefined ids in 03 and GLOSSARY), `prd_check.py` (the B2 PRD checker, extended so that codes adopted by D-76 but not yet published in 04 §15.4 are reported, not failed), `b3_probes.py` (applied-text probes, superseded-text probes, IMP contiguity, SF sub-ids against the SCREENS pair, WLD-X-26 and J-01.14 against `deviations.json`). Final logs: `register_glossary_final.log`, `prd_final.log`, `probes_final.log` |

Statuses: **applied**; **verified** (checked, no change needed); **not applicable** (no text in these three files is affected); **dependency** (the change here is complete, and another owner must publish the matching text).

## 1. Assigned rulings and questions

| Ruling or question | Change (file, section, id) | Status |
|---|---|---|
| D-76 workbench tabs and KPI strip (`SCREENS:OQ-S-01`, `OQ-S-02`) | 03 §3.28 REQ-UX-004: six KPI cells, where the contract liability cell carries contract asset and unbilled receivable; route tabs Obligations, Estimates, Schedules, Billing, Journals, Modifications, History; the header "Documents" drawer; the History "Audit trail" view (SCREENS §4.1, §4.1.4, §4.7, §4.8). PRD §3 SF-03 aligned | applied |
| D-76 financing interest in the net position (`ENGINE_SPEC_B:OQ-B-09`, `OQ-AK-04`) | 03 §3.11 REQ-BIL-007: JET-11 accretion is part of the net position (ALG-02, CHK-137); financed balance tracked separately (S04-R-13); acceptance adds AK:S3-EX28-CASEB. 03 REQ-TP-011 cross-reference. GLOSSARY §2 "Net position" | applied |
| D-76 uninstalled materials (`POLICIES:OQ-15`) | 03 §3.9 REQ-REC-007: excluded from progress; revenue equals cost; the ERP posts the cost; no COST_OF_REVENUE line (POL-091, S09-R-14). GLOSSARY "Cost of revenue" (JET-07c, JET-16 claim release; no uninstalled-materials use) | applied |
| D-25b monetary liabilities | 03 §3.15 REQ-FX-003: refund liabilities, deposit liabilities and consideration payable remeasured at the closing rate at every period end and at settlement, in every book; POL-164 `ASSET_POSITIONS_ENGINE_AR_AND_MONETARY_LIABILITIES`; JET-10d; E-86 `LIABILITY_LAYER_REMEASURED`. REQ-FX-002: contract liabilities stay non-monetary. GLOSSARY "Remeasurement", "FX layer" | applied (03, GLOSSARY) |
| D-25b in the PRD | No PRD text states FX remeasurement. K-05 and K-06, the refund-liability contracts, are EUR contracts of the EUR entity AVM-DE, so no seeded figure changes | not applicable |
| `03:§11 Q4` RPO bands | 03 §11 Q4 status: **Resolved by D-76**, POL-201 governs and DS-CH-03 renders the bands the API returns; REQ-RPT-009 unchanged | applied |
| PRD J-18.5 (`SCREENS_B:OQ-B-31`) | PRD J-18 J-18.5: SF-06:run in the scenario shows the SB-R-08 reason line and no enabled export control; the API returns 403 `sandbox-restricted` (ERR-17); rule for approved runs: "Export to <adapter label>" or "Export journals", `aria-disabled="true"` | applied |
| PRD J-20.1 (`SCREENS_B:OQ-B-32`) | PRD J-20 J-20.1: "Import a legacy database" (SCR-LTH-13) | applied |
| PRD J-25 (`SCREENS_B` §16 J-25 rows, §18) | PRD J-25.1, J-25.3, J-25.4 (SF-15:sandbox; known at "Now"; "Back to the copy taken on <DD MMM YYYY HH:mm UTC>"; "Restore into a new sandbox"; no Reset rendered in production); J-25-AC-2 (disabled export control and 403). PRD §7.1 LTM-10 to LTM-12 (SF-15:sandbox; LTM-11 "Restore into a new sandbox") | applied |
| PRD §9 Q11 routing defaults (§2.5) | PRD §9 Q11: **Resolved by D-76**; §2.5 rows, SM-06, ACT-17, ACT-18, ACT-22, ACT-52, ACT-54, ACT-55 stand as written | applied (confirmed, no body change) |
| PRD §9 Q10 combination suggestion code | PRD §5.3 BR-CON-03 cites `COMBINATION_SUGGESTED` (`WARNING`, X `ENGINE`, `remediable`); §5.5 IMP-89 carries the Q10 message; §9 Q10 resolved | applied; dependency (04 §15.4 row) |
| PRD §9 Q12 ERR and IMP drift test | PRD §9 Q12 resolved; IMP-89 to IMP-96 keep one IMP row per adopted code | applied; dependency (dev-guide drift test) |
| PRD §9 Q13 DG-FE-02 fallback | PRD §9 Q13 resolved; §3 carries no route path | applied |
| PRD §9 Q14 permanent-lock subject | PRD §9 Q14 resolved; §2.5 `PERIOD_LOCK` row and ACT-27 already conform | applied |
| WLD-X-26 and J-01.14 January 2023 JE values | Checked against `deviations.json` case `je-month-2023-01` (gross by account: Dr 21001 295.69, Dr 15002 58.85 / Cr 5001 187.69, Cr 5002 118.53, Cr 5003 48.32; totals 354.54) and POLICIES CHK-022. WLD-X-26 cites the current SHA-256 prefix and suffix; J-01.14 batches 295.69 and 58.85; WLD-X-27 and J-20.5 (295.69, 58.85, 4.31) agree. No stale figure found | verified |
| SF-01 "Take the tour" banner (`SCREENS_B` §11.2, OQ-B-29) | PRD §3 SF-25 and J-24.1: banner "This is a demo workspace with sample data. The tour shows six places where eRev Cloud keeps revenue auditable." with "Take the tour" and "Dismiss"; J-24.2 starts from the banner | applied |

## 2. Other D-76 rulings and adopted defaults that touch these files

| Ruling or adopted default | Change (file, section, id) | Status |
|---|---|---|
| Contract-cost impairment (industries D-6) | 03 §3.12 REQ-CST-004: remaining consideration includes anticipated renewals and extensions (340-40-35-4 as amended by ASU 2016-20; S11-R-09) | applied |
| Significant financing component rate (`OQ-AK-05`, `OQ-AKT-13`, `ENGINE_SPEC:OQ-A-16`) | 03 §3.7 REQ-TP-011: POL-047 member `compounding` ∈ {`MONTHLY` (default), `ANNUAL`}, as POLICIES rev 1.2 publishes | applied |
| `ENGINE_SPEC:OQ-A-20` | 03 §3.10 REQ-MOD-021: `MOD_ATTRIBUTE_CONFLICT` is `ERROR` (04 table 15.4-A; DEV-035) and blocks the upload | applied |
| Loop network use (`dev-guide:DG-OQ-13`) | 03 §3.27 REQ-OPS-007: dependency installation in `make setup` is the loop's only network use | applied |
| Answer-key schema (CHK containment case-insensitive) | 03 §12 list C coverage condition | applied |
| Codes adopted by D-76 (`PRD:Q10`; `ENGINE_SPEC:OQ-A-11` to `-13`; `ENGINE_SPEC_B:OQ-B-04`, `-08`; `05:OQ-ARC-12`) | PRD §5.5 IMP intro and IMP-89 to IMP-96 (`COMBINATION_SUGGESTED`, `PRINCIPAL_AGENT_NOT_ASSESSED`, `VC_TARGET_TOLERANCE_EXCEEDED`, `OPENING_BALANCE_INCONSISTENT`, `BILL_AND_HOLD_CRITERIA_UNMET`, `INVOICE_STATUS_UPDATE_MISMATCH`, `TRACE_TOO_LARGE`, `FORMULA_NO_CACHED_VALUE`) | applied; dependency (04 §15.4 rows) |
| `SCREENS:OQ-S-10` About placement | PRD §3 SF-27: Help menu item "About eRev Cloud" | applied |
| `SCREENS:OQ-S-11` Q&A trigger | PRD §3 SF-28: ghost icon button "Ask about revenue", AI enabled and `ai.use` | applied |
| `SCREENS:OQ-S-17`, `SCREENS_B:OQ-B-06` reason codes | PRD J-26.2: reason code `DUPLICATE` (04 E-110) | applied |
| `SCREENS_B:OQ-B-19` setup permissions | PRD §5.6 ACT-44: `settings.manage` opens periods while `setup_completed_at` is null | applied |
| Perf protocol (`05:OQ-ARC-10`) | 03 REQ-CLS-014, REQ-OPS-008, REQ-OPS-009 state G9 thresholds, not the harness | not applicable |
| `DESIGN_SYSTEM:OQ-06` negative style key | PRD §2.5 already cites `ui.negative_number_style`, which 04 table 1.2-D B3-D01 keeps | not applicable |
| `DEVIATIONS:OQ-D11`; `04:OQ-08` to `-12`; `dev-guide:DG-OQ-12`; `05:OQ-ARC-11`, `-13`, `-14`; `POLICIES:OQ-13`, `-14`; `DESIGN_SYSTEM:OQ-07`; the other `SCREENS` and `SCREENS_B` defaults | No text in these three files is affected | not applicable |
| D-77 design freeze | No new open question in 03 §11 or PRD §9; PRD §9 intro states it | applied |

## 3. Decisions taken in B3

| # | File | Decision |
|---|---|---|
| B3-RP-01 | 03, GLOSSARY | POL-164, JET-10d, E-86 and POL-047 `compounding` are cited verbatim from D-25b and D-76; POLICIES rev 1.2 and 04 rev 1.2 publish the same literals |
| B3-RP-02 | 03 | REQ-BIL-007 keeps its id and title; the text names both the excluded balances and the included financing accretion |
| B3-RP-03 | 03 | REQ-CLS-014, REQ-OPS-008 and REQ-OPS-009 are unchanged under the perf-protocol ruling |
| B3-RP-04 | GLOSSARY | The D-25b rule is stated once, in "Remeasurement", and cross-referenced from "FX layer"; the liability terms keep their definitions |
| B3-RP-05 | PRD | J-18.5 asserts the sandbox banner and the API refusal on the copied Sep 2026 run, which is acknowledged and renders no export control; the disabled-control rule is stated for approved runs (SCREENS_B §3.2 action bar) |
| B3-RP-06 | PRD | IMP-89 to IMP-96 use the severity of the proposing document; 04 owns the table placement (D-73). BR-CON-03 and §9 Q10 no longer name a table, because 04 table 1.2-D moves one proposal (B3-D08) |
| B3-RP-07 | PRD | The §2.5 routing notes "§9 Q11" are kept; §9 Q11 records the ruling |
| B3-RP-08 | PRD | SF sub-ids (`SF-06:run`, `SF-15:sandbox`) are cited only where SCREENS defines them |

## 4. Self-check results

| Script | Scope | Final result |
|---|---|---|
| `register_glossary_check.py` | 03 and GLOSSARY: table cell counts; REQ, CTL, POL, ALG, JET, CHK, E, T, D, DG, BR, SF, J ids; AK hints; list A and B ids | 0 problems (both runs) |
| `prd_check.py` | PRD: 150 tables; cross-document and internal ids; 47 problem slugs; 88 published §15.4 codes; state-machine literals; 52 permissions; 30 E-08 subjects; 12 E-69 kinds | 0 problems. Review items: 8 pending codes (IMP-89 to IMP-96, see §5) and the 8 B2 review cases carried over (`/explain` shorthand, E-44 `OPEN`, E-59 `REOPENED`) |
| `b3_probes.py` | Applied text present; superseded text absent; 96 contiguous IMP ids; SF sub-ids in the SCREENS pair; `deviations.json` case and SHA-256 against WLD-X-26 and J-01.14 | 0 problems. The first run flagged "known at now", which was in J-18.1 (scenario creation), not J-25.1; the probe was narrowed to J-25.1. The document was correct |

## 5. Dependencies and residue in other documents (not edited)

| Document | Residue | Owner action |
|---|---|---|
| `docs/04-DATA_MODEL.md` §15.4 | The rev 1.2 log adopts the eight codes, but at the final run tables 15.4-B to -D had no rows for them. `prd_check.py` reports IMP-89 to IMP-96 as pending until they appear | 04 owner publishes the rows; rerun `prd_check.py` |
| `docs/04-DATA_MODEL.md` E-01 row 29 | `COST_OF_REVENUE` still lists "zero-margin uninstalled materials", which D-76 retires | 04 owner |
| `docs/accounting/ENGINE_SPEC_B.md` S12-R-11 | Still says refund and deposit liabilities are not remeasured, which D-25b supersedes | ENGINE_SPEC_B owner |
| dev-guide drift test (PRD §9 Q12) | Every §15.2 slug has one ERR row, and every non-withdrawn §15.4 code has one IMP row | dev-guide owner |
