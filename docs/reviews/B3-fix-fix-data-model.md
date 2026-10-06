# B3 fix pass: `docs/04-DATA_MODEL.md` (slug `fix-data-model`)

| Field | Value |
|---|---|
| Author | Owner-editor, design phase B3 (slug `fix-data-model`) |
| Date | 2026-09-12 |
| File edited | `docs/04-DATA_MODEL.md` (rev 1.1 → rev 1.2; revision log and table 1.2-D "Decisions taken in B3" in the header) |
| Binding inputs | `docs/01-DECISIONS.md` D-25b, D-76, D-77; SCREENS §16 (OQ-S, R-01 to R-40); SCREENS_B §18; ENGINE_SPEC §16; ENGINE_SPEC_B §16.3, §17; 05 §13; POLICIES §8; PRD §9; DESIGN_SYSTEM §15; DEVIATIONS OQ-D11; answer-key `_coverage/*.md`; 04 §20 OQ-08 to OQ-12 |
| Self-check | `.scratch/b3-fix-data-model/check_04_b3.py` extends the B2 checker. It checks table cell counts, undefined internal ids (including qualified cross-document open-question ids), duplicate ids, slugs against §15.2, codes against §15.4, `API-S-*` references against schema definitions, and consecutive E ids. Result: **0 findings**; 447 ids, 152 tables, 47 slugs, 12 synonyms, 106 codes. Rev 1.1 backup: `.scratch/b3-fix-data-model/04-DATA_MODEL.rev1.1.md` |
| Size | 5,953 → 6,387 lines; 548 lines added or replaced |

## 1. Rulings and questions → changes

| Ruling or question | Change (section, id) | Status |
|---|---|---|
| D-25b | §3.4 E-86 `LIABILITY_LAYER_REMEASURED`; T-CON-18 purpose (monetary liability layers in every book), `balance_role` adds `REFUND_LIABILITY`, `DEPOSIT_LIABILITY`, `CONSIDERATION_PAYABLE`, checks `ck_fx_layer_movement__liability_kinds` and `__asset_kinds` | applied |
| ENGINE_SPEC_B:OQ-B-14 | E-86 as above; the S12-R-12 interim storage is retired | applied |
| ENGINE_SPEC:OQ-A-04; ENGINE_SPEC_B:OQ-B-02 | §14.1 DB-17 V1: Σ `allocated_amount` = `transaction_price` − `consideration_payable_amount`; §15.2 `allocation-invariant` wording | applied |
| ENGINE_SPEC:OQ-A-02 | T-CON-18 `layer_key` = `<balance role>:<global event key>` | applied |
| ENGINE_SPEC:OQ-A-06 | T-REF-20 `assurance_cost_per_unit` (B3-D02) | applied |
| ENGINE_SPEC:OQ-A-07 | API-S-NoncashConsideration; `noncash_consideration` on API-S-ContractCreate, `CONTRACT_BOOKED`, `CONTRACT_AMENDED`, T-CON-06 (B3-D03) | applied |
| ENGINE_SPEC:OQ-A-08 | API-S-ConsiderationPayable; same carriers (B3-D04) | applied |
| ENGINE_SPEC:OQ-A-09 | API-S-PaymentPoint; `payment_schedule` on API-S-ContractCreate (B3-D05) | applied |
| ENGINE_SPEC:OQ-A-10 | T-REF-30 `observable_point`; API-S-SspEntry (B3-D06) | applied |
| ENGINE_SPEC:OQ-A-11, OQ-A-12, OQ-A-13 | Table 15.4-C `PRINCIPAL_AGENT_NOT_ASSESSED`, `VC_TARGET_TOLERANCE_EXCEEDED`, `OPENING_BALANCE_INCONSISTENT` (X `MIGRATION`) | applied |
| ENGINE_SPEC:OQ-A-16 | T-CON-23 `value`: POL-047 `{basis, annual_rate, compounding}`, `compounding` ∈ {`MONTHLY` default, `ANNUAL`} | applied |
| ENGINE_SPEC:OQ-A-18 | T-CON-06 questionnaire member `price_change_settlement`; `CONTRACT_AMENDED` payload (B3-D07) | applied |
| ENGINE_SPEC:OQ-A-19 | `OPENING_BALANCE_ESTABLISHED.fair_value_contract_liability` | applied |
| ENGINE_SPEC:OQ-A-20 | §17.4 LM-TPL-MOD: attribute conflicts raise `MOD_ATTRIBUTE_CONFLICT` (`ERROR`) | applied |
| ENGINE_SPEC:OQ-A-21 | T-CON-19 questionnaire schemas by E-56 topic (Table 0.4-A members) | applied |
| ENGINE_SPEC:OQ-A-24 | T-CON-08 `status_reason_in_book`; API-S-ContractVersion; API-S-Contract `status_reason` | applied |
| ENGINE_SPEC:OQ-A-01, -03, -05, -14, -15, -17, -22, -23 | Engine-internal or owned by DG, 05, POLICIES | not applicable |
| ENGINE_SPEC_B:OQ-B-04 | E-56 `BILL_AND_HOLD`; T-CON-19 schema; table 15.4-D `BILL_AND_HOLD_CRITERIA_UNMET` | applied |
| ENGINE_SPEC_B:OQ-B-05 | T-CON-13 `EAC` parameter `uninstalled_materials_cost` | applied |
| ENGINE_SPEC_B:OQ-B-07 | T-CON-13 `VARIABLE_CONSIDERATION` parameter `refund_liability_target` | applied |
| ENGINE_SPEC_B:OQ-B-08 | Table 15.4-B `INVOICE_STATUS_UPDATE_MISMATCH`; `BILLING_RECORDED` status-update rule (B3-D08) | applied |
| ENGINE_SPEC_B:OQ-B-11 | `COST_INCURRED.cost_adjustment` `CLAWBACK`; E-03 row | applied |
| ENGINE_SPEC_B:OQ-B-12 | T-CON-01 `scope_605_35`; T-CON-06; API-S-ContractCreate; T-CON-12 `EAC_IAS37` | applied |
| ENGINE_SPEC_B:OQ-B-18 | E-29 `RECEIVABLE_CONTRA` | applied |
| ENGINE_SPEC_B:OQ-B-03, -06, -09, -10, -13, -15 to -17, -19 to -24 | POLICIES, 03, 05 or engine-internal | not applicable |
| 05:OQ-ARC-12 | Table 15.4-B `FORMULA_NO_CACHED_VALUE`; table 15.4-D `TRACE_TOO_LARGE` | applied |
| 05:OQ-ARC-10, -11, -13, -14 | No 04 change | not applicable |
| POLICIES:OQ-13 | `COST_INCURRED.purpose` `WARRANTY_CLAIM`; `PAYMENT_RECEIVED` `form` (`CASH`, `NONCASH`), `units_received`, `asset_type`; E-03 rows | applied |
| POLICIES:OQ-14 | E-09 `SHARE_BASED_CONSIDERATION`; T-CON-13 parameter schema (B3-D17) | applied |
| POLICIES:OQ-15 | No new POL | not applicable |
| PRD:Q10 | Table 15.4-C `COMBINATION_SUGGESTED` (`WARNING`, X `ENGINE`, `remediable`) | applied |
| PRD:Q14 | E-08 note: permanent lock = subject `PERIOD_LOCK` with `PERMANENT_LOCK` | applied |
| PRD:Q11, Q12, Q13 | PRD and DG owners; E-08 already holds the subjects | not applicable |
| DESIGN_SYSTEM:OQ-06 | T-PLT-31 note; API-S-Me `tenant_settings.negative_number_style`; 04 name kept (B3-D01) | applied |
| DESIGN_SYSTEM:OQ-07 | API-R-03 `POST /me/notifications/read-all` `{before}`; §16.12 | applied |
| SCREENS:R-01 | API-R-55; E-120; API-S-SearchResult (§16.13; B3-D11) | applied |
| SCREENS:R-02 | API-R-50; API-S-DashboardHome (§16.13) | applied |
| SCREENS:R-03, R-04 | API-R-09 `preparer` and sort; API-R-44 sort; API-C-09 sort direction | applied |
| SCREENS:R-05 | API-S-Contract `steps[]`; E-112, E-113; §16.14 step rule; `GET /contracts/{id}/activation-checklist`; table 15.4-I (B3-D22) | applied |
| SCREENS:R-06 | Allocation walk and API-S-Obligation `ssp` `range_position`, `outside_range_point`; E-114 | applied |
| SCREENS:R-07 | API-S-Contract `kpis_ratios`; API-S-Obligation `ratios` | applied |
| SCREENS:R-08 | Combination suggestion list and dismiss (§16.14); T-IMP-05 `dedupe_key` (B3-D14) | applied |
| SCREENS:R-09 | T-PLT-27 `subject_type`, `subject_id`, `ix_job__subject`; API-R-11 filters | applied |
| SCREENS:R-10 | API-S-ScheduleLine `obligation_key`; API-R-35 `schedule_kind`; API-S-SubledgerLine `journal_run_id` (B3-D12) | applied |
| SCREENS:R-11 | API-R-34 `period` and `period_amortization` | applied |
| SCREENS:R-12 | API-S-UsageCommitment (§16.14; B3-D13) | applied |
| SCREENS:R-13, R-16, R-23 | API-S-ImpactSummary (§16.0); API-S-Modification with `prefill_reasons`; event and estimate-version previews | applied |
| SCREENS:R-14 | API-S-ContractHistoryItem; E-116 | applied |
| SCREENS:R-15 | API-R-12 attachments filter `contract_id` | applied |
| SCREENS:R-17 | `POST /contracts/{id}/obligations/{obligation_key}/distinct-review` (§16.1) | applied |
| SCREENS:R-18 | `POST /contracts/{id}/replace-draft` (§16.1); `CONTRACT_BOOKED` rule | applied |
| SCREENS:R-19, R-20, R-21 | API-S-Explain `history`; `verify`; `GET /calc-traces/{id}`; API-S-CalcTrace | applied |
| SCREENS:R-22 | API-R-56; T-SRC-01 `idempotency_key`; API-S-SourceRecord | applied |
| SCREENS:R-24 | Estimate list and version additions (§16.14) | applied |
| SCREENS:R-25 | `material_right.status` (E-115), `status_date` | applied |
| SCREENS:R-26 | `POST /obligations/{id}/request-ssp-override` (§16.2); `LINE_ATTRIBUTES_CHANGED.changes.ssp_book_version_id` | applied |
| SCREENS:R-27, R-28 | API-R-43 row filters and `sort=status`; API-R-22 and API-R-23 filters and sort; `member_count` | applied |
| SCREENS:R-29, R-30, R-31 | API-S-VersionSummary; rule upsert by `rule_key`; API-R-57 configuration test cases; API-S-SimulationSummary | applied |
| SCREENS:R-32, R-33, R-34, R-35 | T-PLT-31 `section`; SSP diff `mid_change_ratio`; T-REF-33 `inside_count` and observations route; `rule_count` | applied |
| SCREENS:R-36, R-37, R-38 | API-S-Import `finding_counts`, `header_match` (E-119); error report; API-S-ImportDiff (E-118) | applied |
| SCREENS:R-39, R-40 | Exception `available_actions` (E-117), `dismiss_blocked_reason`; connection `last_sync_run`, sync-run `duration_seconds`, `connection` filters | applied |
| SCREENS:OQ-S-04 | E-111 `contract_quick_list` with semantics | applied |
| SCREENS:OQ-S-07 | §16.5 `publish` note (approval publishes) | applied |
| SCREENS:OQ-S-15 | T-PLT-37 favourites `config = {target, path, label}` | applied |
| SCREENS:OQ-S-17; SCREENS_B:OQ-B-06 | E-110 `reason_code` and table 3.4-R subsets; T-REF-07 and T-CLS-04 column type; void, reopen and cancel-close rows; `REASON_CODE_NOT_ALLOWED` | applied |
| SCREENS:OQ-S-18 | API-C-10 note (lock id → `known_at`) | applied |
| SCREENS:OQ-S-21 | T-IMP-05 `title` from `finding.<code>.title` | applied |
| SCREENS:OQ-S-01 to -03, -05, -06, -08 to -14, -16, -19, -20 | SCREENS, DESIGN_SYSTEM, 03 owners, or client behaviour | not applicable |
| SCREENS_B:OQ-B-02 | T-RPT-01 table 10-T (13 tie-out codes); `tie_outs` rule; T-RPT-02 results as E-98 | applied |
| SCREENS_B:OQ-B-03 | E-62 note; T-CLS-01 `steps[].status` | applied |
| SCREENS_B:OQ-B-07 | `GET /journal-runs/{id}/summary`; API-S-JournalRunSummary (B3-D20) | applied |
| SCREENS_B:OQ-B-08, OQ-B-17 | T-RPT-01 rule 1 (`parameters_schema` keys); API-S-ReportRunCreate keys | applied |
| SCREENS_B:OQ-B-09 | `disclosure_pack` code and rule 2; T-RPT-02 `child_report_run_ids`, `disclosure_snapshot_ids` | applied |
| SCREENS_B:OQ-B-10, OQ-B-11 | API-S-EvidencePackCreate; T-RPT-04 `as_of_date`, `from_date`, `to_date`, per-kind checks, manifest layout | applied |
| SCREENS_B:OQ-B-13 | `POST /deal-previews/{id}/save`; T-FC-04 IM-S; `DEAL_PREVIEW_SAVE_NOT_ALLOWED` (B3-D23) | applied |
| SCREENS_B:OQ-B-14 | `GET /ai/proposals/{id}/document-text`; accept body; T-AI-01 `document_text_file_id`, `field_decisions`; E-68 `AI_DOCUMENT_TEXT`; E-121 | applied |
| SCREENS_B:OQ-B-18 | `POST /tenant/ai/disable`; T-PLT-01 `ai_disabled_at`, `ai_disabled_by`, `ai_disabled_by_kind` (B3-D09) | applied |
| SCREENS_B:OQ-B-19 | API-C-03 any-of sets; API-R-17, API-R-18, API-R-19; period `open` during setup | applied |
| SCREENS_B:OQ-B-20, OQ-B-24 | T-PLT-02 `preferences`; T-PLT-07 `last_opened_at`; API-S-Session, API-S-Me with `engine_release`; E-123, E-124 (B3-D15) | applied |
| SCREENS_B:OQ-B-22 | API-S-PeriodCockpit `derived_blockers`; E-122 | applied |
| SCREENS_B:OQ-B-23 | `POST /close-runs/multi-entity` schema (§16.8) | applied |
| SCREENS_B:OQ-B-25 | T-CLS-07 `gl_document_reference` | applied |
| SCREENS_B:OQ-B-26 | `POST /ai/explanations` subject `exception_item` (§16.14) | applied |
| SCREENS_B:OQ-B-28 | `POST /me/password`; password reset and confirm; invitation lookup; T-PLT-42; E-79 kinds; API-C-01 (B3-D10) | applied |
| SCREENS_B:OQ-B-04, -05, -12, -21 | No 04 change needed: `period_lock_id` already on report runs; client-side checkbox; client dashboards; role matrix is a section of `user_access_listing` | not applicable |
| SCREENS_B:OQ-B-01, -15, -16, -27, -29 to -32 | DESIGN_SYSTEM, SCREENS, PRD owners | not applicable |
| 03:§11 Q4 | API-S-RpoReportData: ordered `bands` with `from_month`/`to_month` from POL-201, row and cell keys (B3-D19) | applied |
| DEVIATIONS:OQ-D11 | T-IMP-05 `message`: aggregated rows, lowest row, `worksheet_rows` | applied |
| `OQ-AK-06` to `-10`, `-13`, `-14`, `-16` | B3-D02 to B3-D05; `scope_605_35`; `tax_lines`; `renewal_of_contract_id` on create; `is_franchisor_preopening_service` (B3-D21); registry value shapes | applied with the B3 choices |
| `OQ-AK-11` | RPO band keys, row keys, column keys (B3-D19) | applied |
| `OQ-AKI-03`, `-04`, `-10`, `-14`, `-20` | `scope_605_35`; `EXPECTED_PURCHASES` note; net-of-tax rule; product cost rate; lapse and rollover expressed with existing members (B3-D18) | applied with the B3 choices |
| `OQ-AKT-05`, `-10`, `-12`, `-17` | `price_change_settlement` (B3-D07); T-CON-12 `direction` (B3-D16); `RESIDUAL_REJECTED` condition; observable point (B3-D06) | applied with the B3 choices |
| Other coverage open questions | DG, POLICIES, engine or key adjudication | not applicable |
| 04:OQ-08 to OQ-12 | §20 rows marked "Resolved by D-76" with the ruling; no new question (D-77) | applied |
| §15.4 single catalogue | 17 new codes, each with severity and remediation; scope bullet for checklist codes | applied |

## 2. Decisions taken in B3

Table 1.2-D in the 04 header records B3-D01 to B3-D23. Each picks one proposal where adopted proposals differ, or fixes a detail a proposal left open. None opens a question.

## 3. Cross-document residue (other owners; not edited)

| Document | Residue | Owner action |
|---|---|---|
| `docs/design/DESIGN_SYSTEM.md` | OQ-06 names `ui.negative_money_style` | Cite `ui.negative_number_style` (B3-D01) |
| `docs/design/SCREENS.md` | R-12 `status_label` | Bind `status` (`IN_PROGRESS`, `MET`, `SHORTFALL`) and render the label as copy (B3-D13) |
| `docs/accounting/ENGINE_SPEC_B.md` | Interim clauses: S12-R-12 storage, `custom_attributes.scope_605_35`, `bill_and_hold_55_83`; "proposed" markers on adopted literals | Drop the interim clauses and markers |
| `docs/accounting/ENGINE_SPEC.md` | "proposed" markers on OQ-A-06 to OQ-A-13, OQ-A-18, OQ-A-19 members and codes | Mark them adopted |
| `docs/accounting/POLICIES.md` | OQ-13 and OQ-14 still "Open" | Mark resolved by D-76 |
| `docs/02-PRD.md` | Q10 IMP row; IMP copy for the other 16 new codes (PRD Q12 drift rule: one IMP row per code) | Append IMP rows; no new ERR row is needed, since rev 1.2 adds no slug |
| `docs/05-ARCHITECTURE.md` | UPL-06 "code pending"; RCP-20 | Cite `FORMULA_NO_CACHED_VALUE` and `TRACE_TOO_LARGE` |
| `docs/03-REQUIREMENTS.md` | REQ-MOD-021 warning wording | `ERROR` per ENGINE_SPEC OQ-A-20 |
| `_coverage/*.md` and keys | `billing_plan`, `NONCASH_FAIR_VALUE`, `assurance_cost_rate`, `observable_point_value`, `settlement`/`CREDIT_MEMO` | dev-guide B3-DG-01 to B3-DG-05 already map these to the 04 names; the B3 adjudicator aligns the keys |

## 4. Not applied

| Item | Reason |
|---|---|
| `OQ-AKI-19` receivable class per billing-plan line | `ENGINE_SPEC_B:OQ-B-10` and `OQ-B-23` (adopted) keep the S10-R-21 and S10-R-25 derivations for 1.0 (B3-D05) |
| `OQ-AK-07` estimate kind `NONCASH_FAIR_VALUE` | The OQ-A-07 payload member carries the measurement-date fair value (B3-D03) |
| `OQ-AKI-20` new lapse literal | Expressible with `CONTRACT_TERMINATED` `FULL` or `PARTIAL` and no refund; the engine defines no third kind (B3-D18) |
| `OQ-AKT-05` literals `settlement`, `CREDIT_MEMO` | Replaced by the engine's `price_change_settlement` literals (B3-D07) |
| 04 OQ-12 `rate_limit_window` table | The adopted default defers it to the amendment that requires more than one api instance |
| Remediation text for rev 1.0 and 1.1 codes | Only the rev 1.2 codes carry remediation in §15.4; earlier codes rely on the PRD IMP copy. Back-filling 89 rows was outside the D-76 scope |
