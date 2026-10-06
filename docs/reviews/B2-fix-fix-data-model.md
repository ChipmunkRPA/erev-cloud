# B2 fix pass: `docs/04-DATA_MODEL.md` (slug `fix-data-model`)

| Field | Value |
|---|---|
| Author | Owner-editor, design phase B2 (slug `fix-data-model`) |
| Date | 2026-09-12 |
| File edited | `docs/04-DATA_MODEL.md` (rev 1.0 → rev 1.1; the revision log is in the header) |
| Binding inputs | `docs/01-DECISIONS.md` D-11a to D-75; `docs/reviews/B1-consistency.md`; 05 OQ-ARC-01 to OQ-ARC-09; DG-OQ-01 to DG-OQ-10; 04 §20 OQ-01 to OQ-07 |
| Self-check | `.scratch/design-fix-data-model/check_04.py`: table cell counts, undefined internal ids, duplicate ids, slugs used against §15.2, codes used against §15.4. Result: 0 findings (428 ids, 47 slugs, 12 synonyms, 89 codes). `.scratch/design-fix-data-model/crossdoc.py` compares other documents with 04 (advisory; see §3). |

## 1. Findings and decisions applied

| Finding or decision | Change made (section and id) | Status |
|---|---|---|
| B1-003; D-13a | §2.1 reconciliation row: `journal_run.mode = DELTA`. §3.2 E-02 `LEGACY` meaning cites the `DELTA` mode. T-REF-02 `posting_target` note: "`DELTA` runs". T-SL-06 `delta_from_chain_seq`: "when `mode = 'DELTA'`". T-CON-09 `accounts_receivable_txn`: `billing.posting = ENGINE`. §20 OQ-07 resolved. | applied |
| B1-003 (03, GLOSSARY, PRD, POL parts) | Not in this file | not applicable |
| B1-004; D-75 ratable conventions | §3.4 E-21 = `DAILY`, `MONTHLY_EVEN`, `MID_MONTH`, citing POL-090 and ALG-11 (CHK-140 to CHK-145). §15.4-H withdraws `TERM_NOT_WHOLE_MONTHS`. §18 rule 5 (rename path). §20 OQ-04 resolved. | applied |
| B1-006; D-73 | Header precedence row (identifier authority). New §0.5: authority table and the PRD state-machine mapping rule. SMAP-01 to SMAP-15 map SM-02 `COMBINED`, SM-07 upper-case and `PERMANENTLY_CLOSED`, SM-08 `CALCULATING`/`CALCULATED`/`SUBMITTED`/`EXPORTING`/`PARTIALLY_ACKNOWLEDGED`, SM-11 upper-case and `SUBMITTED`, SM-03 quarantined, SM-05 "Rejected", SM-13 role assignment and SM-14 hold. No PRD-only state was added to any enum. §0.2 adds the `SMAP-nn` family. | applied |
| B1-007 | §15.2 rules (union, one status, one type URI, DG `PROBLEMS` equality). The `self-approval` row is split: `approver-already-decided` now owns `EREV-APR-002`. 20 slugs appended: 18 PRD slugs plus `job-stalled` and `release-mismatch` from 05. Table 15.2-S maps 12 PRD synonyms and the 05 `internal-error`, `eng-internal-error` and 413 forms. API-C-05 fixes `https://erev.dev/problems/<slug>` and 500 `about:blank`. | applied |
| B1-013 | §3.4 E-69 appends `ITEM_APPROVED`, `PERIOD_LOCKED`, `PERIOD_REOPENED`. T-PLT-25 seeds email defaults from PRD §5.4 and adds CHECK `ck_notification_preference__mandatory` for `CHAIN_VERIFICATION_FAILED`, with back-fill of appended kinds. | applied |
| B1-013 (05 §5.8 deference) | Not in this file | not applicable |
| B1-014 | New §15.4: code format, finding severities `ERROR`/`WARNING`/`INFO`, mapping to E-43, and the raised-as legend. The catalogue covers:<br>- 15.4-A: 40 DEVIATIONS §5 codes, verbatim;<br>- 15.4-B: `PRODUCT_UNMAPPED`, `IMPORT_ROW_LIMIT_EXCEEDED`, 05 codes renamed, registry and platform codes;<br>- 15.4-C: POLICIES codes;<br>- 15.4-D: 05 engine failure codes renamed;<br>- 15.4-E: data-quality monitors;<br>- 15.4-F: anomaly detectors;<br>- 15.4-G: AI codes;<br>- 15.4-H: withdrawn;<br>- 15.4-S: synonyms.<br>E-43 states the inverse mapping. T-IMP-05 `code` holds catalogue codes only (CHECK plus `erev_api.findings.CODES`). T-REF-15 step 4 raises `ACCOUNT_MAPPING_MISSING`. §16.6 `messages.severity` is the finding severity. | applied |
| B1-015; D-14a | §3.1 E-01 appends values 29 to 33 (`COST_OF_REVENUE`, `CONTRACT_COST_CLEARING`, `RECEIVABLE_CONTRA`, reserved `RETAINED_EARNINGS`, `FINANCING_OBLIGATION`), with demo accounts and rules (order, reserved-role checks, clearing purpose, OBJ-01 resolved). New E-109 `clearing_purpose`. T-REF-15 and T-SL-04 gain `clearing_purpose` with a biconditional CHECK plus the reserved-role CHECKs. The T-REF-15 index, lint and resolution match on purpose. Override keys `BILLING_CLEARING:<purpose>` in T-REF-23 and T-CON-11. §19 C-04 row updated. §20 OQ-03 resolved. | applied |
| B1-016; D-75 Q10 | T-PLT-29 per-purpose limits table declared authoritative, with SQL CHECK `ck_file_object__size_limit`, uploadable purposes, media types and 50,000 rows per sheet (`IMPORT_ROW_LIMIT_EXCEEDED`). API-C-17 body limits. `upload-type-not-allowed` names the purpose limit. | applied |
| B1-022 | §3.4 E-25 appends `EARLY_RENEWAL` and maps subscription-change actions to kinds. The API-R-31 note is updated. | applied |
| B1-033; DG-OQ-01; DG-OQ-02 | §18 rewritten: one self-contained revision per BUILD_SPEC item, dependency-order step table, downgrades implemented but run only in the round-trip test on test databases, forward-fix otherwise (DG-MIG-08). Steps 0008 to 0012 retired with notes (ids kept). §1.2, §1.4 and §1.6 rule 1 no longer cite fixed revision numbers. | applied |
| B1-036 | T-PLT-31 platform parameters `ai.anomaly.revenue_change_ratio` `"0.50"`, `ai.anomaly.revenue_ahead_of_billing_days` 60, `ai.anomaly.allocation_adjustment_ratio` `"0.20"`, `close.dq_revenue_without_billing_days` 60 and `close.dq_inactive_contract_days` 90, each linked to its §15.4 code. | applied |
| 05 OQ-ARC-03 | T-CON-13 `parameters jsonb` (object CHECK, Pydantic union on `estimate_kind`, included in `content_sha256`), with a JSON Schema table per E-09 kind. `RETURN_RATE` requires `carrying_cost_per_unit`, `recovery_cost_per_unit`, `window_end_date`; `VARIABLE_CONSIDERATION` has `no_change_attestation`; `ROYALTY_ACCRUAL` has usage period dates; the other kinds take `{}`. The interim `scenarios` element is not used. | applied |
| 05 OQ-ARC-06 | API-R-05 `POST /users/{membership_id}/anonymise` (`user.manage`, MFA-gated). API-R-12 `POST /files/{id}/shred` (`settings.manage`, MFA-gated; `FILE_RETENTION_ACTIVE`). T-PLT-29 shred columns and `FILE_SHREDDED`. | applied |
| 05 OQ-ARC-09 | API-R-53 `GET /metrics` outside `/api/v1`: bearer token, `EREV_METRICS_ENABLED`, not proxied, no tenant labels. API-C-01 names it as the only route outside `/api/v1`. | applied |
| D-72; DG-OQ-09 | API-C-01 and a note after the §15.3 table exclude `/api/v1/__mocks__/<adapter>` from the catalogue and OpenAPI | applied |
| D-75 Q9 (REQ-PLT-038); B1-012 part for 04 | §14.3 invocation and bootstrap: CLI and `POST /operator/tenants` (new API-R-54), admin user, INVITED membership, tenant-admin role assignment approved by `AUTO-BOOTSTRAP`, EMAIL outbox invitation, and the `AUTO-BOOTSTRAP` rule set seed. T-PLT-01 `setup_completed_at` (BR-PLT-02). T-PLT-07 invitation token columns and acceptance rule. API-R-01 `POST /session/accept-invitation`. API-R-05 `resend-invitation`. `TENANT_CODE_EXISTS`. | applied |
| D-75 Q8 (local keys) | T-PLT-01 `audit_hmac_key_id` note: HKDF context under `EnvSecretStore` locally | applied |
| D-75 PRD Q8; B1-030 | T-PLT-31 `ui.negative_number_style` ∈ {`PARENTHESES`, `MINUS`}, default `PARENTHESES` | applied |
| D-75 PRD Q4 | Same as B1-013 (E-69) | applied |
| D-75 PRD Q5, Q7 (B1-026) | E-74 already has `failed`; E-08 already has `MIGRATION_PROMOTION` | not applicable (no change needed) |
| D-75 Q12 (reopen approvers) | Role grants are PRD §5.6. T-PLT-11 `period.reopen_approve` needs no change. | not applicable |
| D-75 POLICIES OQ-05 (CA and UR presentation balances) | T-CON-09 already stores labelled balances; E-29 `NETTING_RECLASS` and `NETTING_RECLASS_REVERSAL` exist | not applicable (no change needed) |
| D-75 03 Q3 (single currency per group) | T-CON-01 and T-CON-03 already enforce REQ-CON-019 | not applicable (no change needed) |
| DG-OQ-06 | API-C-04: a missing key returns 422 `validation-failed` with `rule_id = "API-C-04"`. API-C-06 cites `rule_id = "API-C-06"`. | applied |
| DG-OQ-07 | API-C-09 `count=true` with `X-Erev-Total-Count`, capped at `100000+` | applied |
| DG-OQ-10; 04 OQ-02 | §20 OQ-02 resolved (supervisor confirms CREATE on the three databases) | applied |
| B1-002 (04 part) | §15.2 `duplicate-import` carries `errors[0].rule_id = "IMPORT_FILE_DUPLICATE"`. SMAP-13 names DG-PAR-06 as owner of the probe status mapping. | applied |
| B1-025; 04 OQ-01 | §20 OQ-01 resolved (`app_user.external_id`) | applied |
| B1-020; 04 OQ-05 | §20 OQ-05 resolved; E-33 unchanged | applied |
| B1-021; 04 OQ-06 | §20 OQ-06 resolved; no SSP book column (E-48 stays withdrawn) | applied |
| 05 OQ-ARC-01 (default adopted: table in a later amendment) | No `rate_limit_window` table in rev 1.1. §20 OQ-12 records the trigger for adding it. | deferred: the adopted default places the table in a later data-model amendment |
| 05 OQ-ARC-02, OQ-ARC-04, OQ-ARC-05, OQ-ARC-07, OQ-ARC-08 | Deployment, POL, retention, port and performance-database questions; none touches 04 | not applicable |
| 04 §20 OQ-01 to OQ-07 | Each marked "Resolved by D-75" with its ruling | applied |

## 2. New open questions raised in rev 1.1 (04 §20)

| Id | Subject | Recommended default |
|---|---|---|
| OQ-08 | Invitation acceptance (token columns, accept and resend routes) was undefined everywhere | Adopt as written; 7-day tokens |
| OQ-09 | SMAP-08 journal-run acknowledgement roll-up | Adopt as written |
| OQ-10 | Severity of `INVOICE_ON_NOT_A_CONTRACT` | `WARNING`, confirmed by the POLICIES owner |
| OQ-11 | 05 §2.5 413 `validation-failed` contradicts one status per slug | Adopt API-C-17 (422); 05 aligns |
| OQ-12 | `rate_limit_window` table timing (05 OQ-ARC-01) | Keep per-process limiting in 1.0 |

## 3. Cross-document residue observed (other owners; not edited)

`crossdoc.py`, run after the edits:

| Document | Residue | Owner action (per B1 finding) |
|---|---|---|
| `docs/02-PRD.md` | Still uses the 12 synonym slugs of table 15.2-S (for example `permission-denied`, `sandbox-cannot-post`, `fx-rate-missing`) and CPY-07 `urn:erev:problem:` | PRD fixer applies B1-007 renames and CPY-07 |
| `docs/05-ARCHITECTURE.md` | Still uses `internal-error`, the hyphenated codes (`DAT-CONTROL-TOTALS`, `INT-STALE-VERSION`, `ENG-INVARIANT`, `COST-NO-EAC`, `SFC-REVIEW-REQUIRED`, `ROY-ACCRUAL-MISSING`, `VC-REASSESSMENT-MISSING`, `SBX-DETERMINISM` and the other table 15.4-S rows) and 413 `validation-failed` | 05 fixer renames per table 15.4-S and adopts API-C-17 |
| `docs/dev-guide.md`, `docs/03-REQUIREMENTS.md`, `docs/accounting/POLICIES.md`, `docs/legacy/DEVIATIONS.md` | No slug or code outside 04 §15.2 and §15.4 detected | none |
