# B3 fix pass: `docs/dev-guide.md` (slug `fix-dev-guide`)

| Field | Value |
|---|---|
| Owner | Owner-editor, design phase B3 |
| Date | 2026-09-12 |
| File edited | `docs/dev-guide.md`, rev 1.1 → rev 1.2 (Revision log at the top of the file, with the table "Decisions taken in B3", B3-DG-01 to B3-DG-24) |
| Inputs | `docs/01-DECISIONS.md` §8 (D-25b, D-76, D-77); the 221 answer keys and `_coverage/answer-keys-{topics,industries,fx-entity-books}.md`; `docs/03-REQUIREMENTS.md` §12; ENGINE_SPEC OQ-A-01 to OQ-A-24, S04-R-02, S04-R-14, S04-R-16; ENGINE_SPEC_B OQ-B-02, OQ-B-12; POLICIES POL-049, POL-073, §3.3; `docs/04-DATA_MODEL.md` rev 1.2 as observed during this pass (table 1.2-D B3-D02 to B3-D07, B3-D16, B3-D18, B3-D19, B3-D21; T-CON-06, T-CON-11, T-CON-12, T-CON-13, T-CON-19, T-CON-21, T-CON-22, T-REF-20, T-REF-30, T-REF-33, T-SRC-05, §15.2, §15.4, §16.3, §17 LM-CL); 05 OQ-ARC-10 to OQ-ARC-14, PERF-01, PERF-20, PERF-30, JOB-03, RCP-19, SAR-18, TZ-09, TZ-10, AIA-02, CFG-28, CFG-29; SCREENS SCR-IA-06, OQ-S-09; SCREENS_B RPT-03, RPT-04, RPT-06, RPT-08; PRD §5.5, §9 Q12, Q13; DEVIATIONS OQ-D11; `docs/legacy/golden/deviations.json` as regenerated |
| Evidence scripts | `.scratch/b3-fix-dev-guide/ak_inventory.py` (field-path inventory of all 221 keys through a DG-AK-31 loader: 0 load errors), `ak_inspect.py` (rule checks, report cells, group balances, value shapes), `ak_mods.py` (modification line forms), `ak_cpc.py` (`EXPECTED_PURCHASES` encodings), `selfcheck.py` |
| Self-check (final run) | 0 table problems; 0 undefined DG ids (479 defined, 479 referenced); 0 cross-document ids missing from their owners (REQ, CTL, POL, CHK, E-nn, T-, API-R, API-C, SF, J, WLD, BR, LTM, E2E, 05 ids, DS, D-); schema coverage: 0 field names used by the corpus that §9.5 does not describe or delegate to an existing 04 table |

## 1. D-76 rulings and D-25b

| Ruling or question | Change (file, section, id) | Status |
|---|---|---|
| D-76 answer-key schema: estimate `parameters` (OQ-AKI-01, OQ-AKT-16) | dev-guide §9.5.4 `estimates` row (`parameters`, `scenarios`, `direction`); DG-AK-32 validation against the T-CON-13 schemas | Applied |
| D-76: `world.portfolios` (OQ-AKT-07) | §9.5.3 new `portfolios` row (T-CON-21, T-CON-22, T-CON-12 `portfolio_id`, handle resolution); DG-AK-32; DG-AK-40; B3-DG-11 | Applied |
| D-76: observable point (OQ-AKT-17, ENGINE_SPEC:OQ-A-10) | §9.5.3 `ssp_books` entry field `observable_point` (T-REF-30, 04 B3-D06); B3-DG-05 | Applied |
| D-76: `scope_605_35` (OQ-AK-10, OQ-AKI-03, ENGINE_SPEC_B:OQ-B-12) | §9.5.4 new row `scope_605_35` (T-CON-01 column, present in 04); B3-DG-10 | Applied |
| D-76: billing plan (OQ-AK-09, OQ-AKI-19, ENGINE_SPEC:OQ-A-09) | §9.5.4 new row `payment_schedule: [{date, amount}]` (04 B3-D05); B3-DG-01 | Applied |
| D-76: noncash consideration (OQ-AK-07, ENGINE_SPEC:OQ-A-07) | §9.5.4 new row `noncash_consideration` (04 B3-D03); B3-DG-03 | Applied |
| D-76: consideration payable (OQ-AK-08, OQ-AKI-04, ENGINE_SPEC:OQ-A-08) | §9.5.4 new row `consideration_payable`; new DG-AK-34 mapping the `EXPECTED_PURCHASES` encoding of four keys (04 B3-D04 delegates it to this loader); B3-DG-02 | Applied |
| D-76: warranty cost rate (OQ-AK-06, OQ-AKI-14, ENGINE_SPEC:OQ-A-06) | §9.5.3 `products.assurance_cost_per_unit` (04 B3-D02); B3-DG-04 | Applied |
| D-76: per-book judgements (OQ-AK-13) | §9.5.4 `judgements.book_code` (T-CON-19 column); B3-DG-07 | Applied |
| D-76: tax lines (OQ-AK-13) | §9.5.5 `payload` row: `BILLING_RECORDED.tax_lines [{tax_type, jurisdiction?, amount}]` (T-SRC-05 members), exclusive with `tax_amount`; DG-AK-32; B3-DG-08 | Applied |
| D-76: renewal handle (OQ-AK-14) | §9.5.4 new row `renewal_of` → `renewal_of_contract_id` (04 B3-D18); also `products.is_franchisor_preopening_service` (04 B3-D21); B3-DG-06, B3-DG-09 | Applied |
| D-76: report cell keys (OQ-AK-11) | §9.5.6 `reports` row; new table "Report cell keys" (rpo, contract_balance_rollforward, revenue_from_opening_liability, disaggregation, other codes); new DG-AK-35 row-key normalisation per 04 B3-D19; B3-DG-14 | Applied |
| Inputs the corpus already used but §9.5 did not describe | §9.5.3 `pob_templates.is_excluded_from_netting_attribution`, SSP literal and unit rules, `policies` value shapes (OQ-AK-16); §9.5.4 modification line forms and `questionnaire` (OQ-AKI-06), `contract_type` free text (OQ-AKI-17), VC `direction` derivation (OQ-AKT-10, 04 B3-D16); §9.5.5 handle substitutions; §9.5.6 empty exact subledger blocks and net grain (OQ-AKI-02, DG-AK-56); B3-DG-15 to B3-DG-17 | Applied |
| D-76 loader: ignore `_coverage/` (OQ-AK-15, OQ-AKT-15, OQ-AKI-21) | DG-AK-01; DG-AK-30 | Applied |
| D-76 loader: CHK containment case-insensitive (OQ-AK-01) | DG-AK-04; DG-AK-32; DG-AK-33 List C | Applied |
| D-76 loader: timelines order by (effective_date, seq) (OQ-AKT-20) | §9.5.5 `effective_date` row; new DG-AK-44 | Applied |
| DG-AK-33 coverage against 03 §12 | DG-AK-33 rewritten: parses 03 §12.1 List A, §12.2 List B conditions and List C at run time; the former restated lists and the `r04-s<n>` tag route are removed; DG-AK-15 keeps other tags without coverage meaning | Applied |
| OQ-AKT-06 group balances | §9.5.6 new `groups` block; new DG-AK-57; B3-DG-13 | Applied |
| OQ-AKT-08 CHK-031 population | §9.5.3 `population` (engine runner only); new DG-AK-45 (pure helper `erev_api.domain.ssp.range_validation.validate_ranges`); `exceptions[].subject`; B3-DG-12 | Applied |
| OQ-AKT-05 and ENGINE_SPEC:OQ-A-18 price-change settlement | §9.5.4 `questionnaire.price_change_settlement` (04 B3-D07); B3-DG-16 | Applied |
| OQ-AKI-07, OQ-AKT-12 SSP semantics | §9.5.3 `ssp_books` row (unit SSPs; residual bounds) | Applied |
| ENGINE_SPEC:OQ-A-01 public engine modules | §1.1 `erev_engine/progress.py`, `stages/__init__.py` (`STAGES`, `BOUNDARY_HANDLERS`), `stages/state.py`; DG-ENG-07 public module list | Applied |
| ENGINE_SPEC:OQ-A-04 and ENGINE_SPEC_B:OQ-B-02 allocation basis | DG-ENG-05; §9.7 P1; DG-AK-54 | Applied |
| 05 AIA-02: fake provider under `test`, `e2e` and perf | DG-AI-01; §5.1 `Settings.perf_run`, `engine_processes`; DG-KRN-CFG-02; B3-DG-21 | Applied |
| PRD:Q12 ERR and IMP copy-coverage drift test | new DG-ARC-13 `test_copy_catalogue_drift.py` | Resolved by D-76: default adopted |
| PRD:Q13 and SCREENS:OQ-S-09 routes | DG-FE-02: PRD §3 fallback removed (unlisted SF id is `BLOCKED:`), route ids `SF-nn` and `SF-nn:<slug>`, `handle = {sf, screen, titleKey}` | Resolved by D-76: default adopted |
| 05:OQ-ARC-10 performance protocol | new DG-RUN-09 `api-perf`, DG-RUN-09a `perf-worker-<n>`; DG-MK-perf; DG-KRN-JOB-09; DG-PERF-02 (PERF-01 steps through workers, every entity, primary book), DG-PERF-03 (pass criterion kept), DG-PERF-04 (PERF-30 mix reported), DG-PERF-05; new DG-PERF-08; B3-DG-20, B3-DG-24 | Resolved by D-76: default adopted |
| dev-guide:DG-OQ-12 perf sandboxes accumulate | DG-PERF-07 archive and runbook note; §12 row | Resolved by D-76: default adopted |
| dev-guide:DG-OQ-13 loop network use | DG-ENV-08; DG-MK-setup `LOCK=1`; DG-MK-00f; DG-FORBID-08; §12 row; B3-DG-18 | Resolved by D-76: only `make setup` may use the network |
| 05:OQ-ARC-11 compose environment | DG-ENV-10 (`production` + `EREV_KEY_PROVIDER=local` reads `EREV_DB_*` from the environment); DG-KRN-CFG-02 | Resolved by D-76: default adopted |
| 05:OQ-ARC-13 lints | new DG-MK-secrets-check (`scripts/secrets_check.py`, allow-list, fixtures) and DG-MK-lint; §1.1 scripts; DG-ARC-05 TZ-09 tokens with `TZ09_ALLOWLIST`; new DG-FE-20 (TZ-10); B3-DG-19, B3-DG-23 | Resolved by D-76: default adopted |
| 05:OQ-ARC-14 close-run children and slots | DG-KRN-JOB-03 exemption for children of a `RUNNING` `CLOSE_RUN` | Resolved by D-76: default adopted |
| DG-MK-design-check and DS-LINT-19 | DG-MK-design-check step (2) excludes DS-LINT-19 (vocab-check) and DS-LINT-21 (self-test) | Applied |
| DG-PAR-10 and DG-PAR-11 against the actual `deviations.json` | DG-PAR-03 (`posting_rule_id` = `EXACT-CUM`, `probe_status_mapping` key set; stale [F] note replaced); DG-PAR-06 (`import_status_basis.condition` and `.mapping`, `error_code_source` as provenance; `watched_latest` legacy columns through LM-CL; `je_gross_<label>` and `je_delta_<label>` windows from `probe.json`); DG-PAR-10 (`probe_status_mapping` not parsed); B3-DG-22 | Applied |
| DEVIATIONS:OQ-D11 `worksheet_rows` | DG-PAR-11 | Resolved by D-76: default adopted |
| D-25b monetary liabilities | §9.7 P12 | Applied |
| ENGINE_SPEC:OQ-A-05 bundle nesting | §7 already fixes field detail by ENGINE_SPEC | No change needed |
| 04:OQ-08 invitation routes | DG-KRN-AUTH-03 already defers to the API-C-01 allow-list | No change needed |
| OQ-AKI-19 receivable class per billing-plan line | Not added: 04 B3-D05 adopted `payment_schedule` without a class member | Not applied: owner ruling in 04 |

## 2. Decisions taken in B3

Recorded in the dev-guide revision log as B3-DG-01 to B3-DG-24 (D-77). None opens a question.

## 3. Items not applied or dependent on other owners

| Item | Reason | Status |
|---|---|---|
| 04 §16.1 `API-S-NoncashConsideration`, `API-S-ConsiderationPayable` and the `API-S-ContractCreate` members `payment_schedule`, `renewal_of_contract_id`, `scope_605_35` | T-CON-06 already cites them, but §16.1 did not define them when this pass ended (04 was being edited concurrently). The dev guide uses the ENGINE_SPEC:OQ-A-07 to OQ-A-09 members, which 04 B3-D03 to B3-D05 say 04 adopts verbatim. If 04's final spelling differs, the loader follows 04 (DG-READ-03) and records a SPEC-Q | Dependent: 04 owner |
| 05 notes that still read "until OQ-ARC-10 is ruled" (PERF-01, PERF-02, PERF-20, the perf row of §2.3) and SAR-18, TZ-09, TZ-10 pointers | 05 owner | Not applicable: 05 owner |
| DESIGN_SYSTEM DS-LINT rule for TZ-10 (05:OQ-ARC-13 default) | DESIGN_SYSTEM owner; DG-FE-20 is the dev-guide contract and adds to any DS rule | Not applicable: DESIGN_SYSTEM owner |
| No active key yet uses `portfolios`, `scope_605_35`, `payment_schedule`, `noncash_consideration`, `consideration_payable`, `observable_point`, `population`, `tax_lines`, `renewal_of` or `groups`; CHK-031, CHK-133 to CHK-135 and CHK-137 stay uncovered | The schema now accepts these inputs. Authoring the keys is corpus work (B3 adjudicator, D-76 "Duplicate keys across slices") | Not applicable: answer-key owners |
