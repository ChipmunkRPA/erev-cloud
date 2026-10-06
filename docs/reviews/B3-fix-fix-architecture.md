# B3 fix pass: `docs/05-ARCHITECTURE.md` (slug `fix-architecture`)

| Field | Value |
|---|---|
| Owner | Owner-editor, design phase B3 (slug `fix-architecture`) |
| Date | 2026-09-12 |
| File edited | `docs/05-ARCHITECTURE.md`, rev 1.1 → rev 1.2 (Revision log rows "Applied" and "Decisions taken in B3", decision table B3D-ARC-01 to B3D-ARC-08) |
| Inputs | `docs/01-DECISIONS.md` §8 (D-25b, D-76, D-77); `docs/accounting/ENGINE_SPEC.md` Table 0.3-A, CV-10, CV-11, CV-50, S01-R-14, S04-R-12, S04-R-13, S08-R-14, §16; `docs/accounting/ENGINE_SPEC_B.md` S10-R-10, S11-R-09, S11-R-12, S11-R-14, S11-R-15, S12-R-09 to S12-R-12, S13-R-11, S14-R-04, S14-R-05, Table 14-A, §17; `docs/accounting/answer-keys/_coverage/*` (industries D-5, D-6; OQ-AK-04, OQ-AK-05; OQ-AKT-13); `docs/dev-guide.md` DG-AI-01, DG-KRN-CFG-02, DG-KRN-JOB-03, DG-PERF-02, DG-PERF-03, DG-ENV-10, DG-OQ-13; `docs/03-REQUIREMENTS.md` REQ-BIL-007 (amended in B3); `docs/04-DATA_MODEL.md` rev 1.2 row; `docs/accounting/POLICIES.md` POL-047, POL-164 |
| Backup | `.scratch/b3-fix-architecture/05-ARCHITECTURE.rev1.1.bak.md` |
| Self-check | `.scratch/b3-fix-architecture/selfcheck.py`, final run exit 0: 0 table problems; 0 undefined 05 ids (535 referenced); 0 cross-document ids missing from their owners (REQ, CTL, POL, ALG, JET, CHK, E-nn, T-, DB-, API-C, API-R, NC, TY, RLS/IM/AUD, DG, D-, WLD, BR, PRD NTF, DS, ENGINE_SPEC CV, S-rules, OQ-A/OQ-B, coverage OQ); 0 missing answer-key ids; 0 unknown problem slugs; 0 OQ-ARC rows open. Every residue hit reviewed and confirmed to be a withdrawal note, a question's history or a still-valid rule. Advisory: POL-164 `ASSET_POSITIONS_ENGINE_AR_AND_MONETARY_LIABILITIES` and JET-10d not yet published by the POLICIES owner (B3D-ARC-08) |

Statuses: **applied**; **not applicable** (no 05 text affected); **owner follow-up** (05 applied; the owning document publishes the literal or contract).

## 1. Assigned rulings

| Ruling or question | Change (file, section, id) | Status |
|---|---|---|
| D-25b Monetary liabilities (OBJ-B-01; `ENGINE_SPEC_B:OQ-B-15`) in stage-12 architecture text | 05 §3.1 ADO-D09; §3.3 STG-10 outputs and governing ids; §3.4 RCP-07 (period-end FX remeasurement of monetary liabilities time-driven, settlement differences event-driven), RCP-08(b) (group selection adds open foreign-currency refund liability, deposit liability or consideration payable; JET-10d in the `FX_REMEASUREMENT` pass); §3.5 EMOD-14; §3.6.4 new "Foreign currency" row (refund liability remeasured through JET-10d; return asset not remeasured, B3D-ARC-05); §3.6.7 "Foreign currency" row (rev 1.1 no-remeasurement rule withdrawn); §13 OQ-ARC-04 marked superseded by D-25b | Applied; owner follow-up: POLICIES POL-164 literal and JET-10d |
| `ENGINE_SPEC_B:OQ-B-14` JET-10c and E-86 `LIABILITY_LAYER_REMEASURED` | 05 RCP-07 (settlement differences event-driven); §3.6.4 and §3.6.7 cite E-86 `LIABILITY_LAYER_REMEASURED` | Applied (04 rev 1.2 publishes the literal) |
| D-76 Contract-cost impairment (industries D-6): anticipated renewals and extensions | 05 §3.5 EMOD-16; §3.6.1 Triggers (`RENEWAL_EXPECTATION` feeds the impairment test), Period-end measurement (remaining expected consideration plus `expected_total_amount` of the `RENEWAL_EXPECTATION` version effective at period end; ASC 340-40-35-4 as amended by ASU 2016-20; S11-R-09; rev 1.1 rule withdrawn), Acceptance (key `COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT`) | Applied |
| D-76 Financing interest in the net position (`ENGINE_SPEC_B:OQ-B-09`, `OQ-AK-04`, industries D-5) | 05 §3.3 STG-10 (position includes accretion); §3.5 EMOD-18; §3.6.3 Position (JET-11 accretion in the carrying amount and position; `financed_balance` separate measure, S04-R-13; rev 1.1 exclusion withdrawn); §11 new row REQ-BIL-007 | Applied |
| D-76 SFC rate compounding (`OQ-AK-05`, `OQ-AKT-13`, `ENGINE_SPEC:OQ-A-16`) | 05 §3.6.3 Rate (`compounding` ∈ {`MONTHLY` default, `ANNUAL`} in the `sfc.discount_rate_basis` value), Schedule construction (periodic rate per `compounding`, S04-R-12; posted cumulative interest = round(exact cumulative interest), no final-period plug; rev 1.1 `round_minor(opening × monthly rate)` withdrawn), Acceptance (CHK-136 re-baselined to `MONTHLY`; `ANNUAL` variant a second CHK row; key `SFC-CAP-DEFERRED-PAYMENT-ROBOT-SALE`) | Applied |
| `ENGINE_SPEC_B:OQ-B-13` Loss provisions time-driven | 05 §3.4 RCP-07 (loss provision movements move to time-driven), RCP-08(a) (the `CLOSE_RELEASE` pass runs for groups with loss units in scope and adds JET-12; computes post JET-12 only as a closed-period carry; part list delegated to S14-R-05 and Table 14-A, B3D-ARC-06); §3.6.2 Triggers (period end), Measurement (EAC effective at period end, S11-R-14), Postings (time-driven; rev 1.1 "event-driven" withdrawn) | Applied |
| `ENGINE_SPEC:OQ-A-03` RCP-01 boundary events | 05 §3.4 RCP-01: boundary events = ENGINE_SPEC Table 0.3-A except the first `CONTRACT_BOOKED` of each member (S01-R-14), adding `COLLECTIBILITY_ASSESSED`, `SIGNIFICANT_CHANGE_FLAGGED` and `OPENING_BALANCE_ESTABLISHED`, with `MATERIAL_RIGHT_EXERCISED` under both POL-028 options; `COMBINATION_CHANGED` not a boundary (membership through RCP-15; CV-10, S02-R-09); handler semantics per CV-11; `BOUNDARY_HANDLERS` executable list | Applied |
| `ENGINE_SPEC:OQ-A-23` §3.6.8 catch-up node name | 05 §3.6.8 Trace: `catch_up@<global event key>:<obligation key>:-` per CV-50, sibling nodes `estimate_pin@…`, `tp_delta@…`, `tp_share@…`; rev 1.1 name withdrawn. §3.10 RCP-24: boundary-event node form `<name>@<global event key>` | Applied |
| AIA-02 alignment with DG-AI-01 (fake provider under test, e2e and perf) | 05 §5.10 AIA-02: `fake` is the only value `Settings` accepts when `EREV_ENV` is `test` or `e2e` or `EREV_PERF_RUN = 1` (B3D-ARC-04); rev 1.1 harness-side check replaced. §2.8 CFG-14 values column | Applied; owner follow-up: dev guide DG-AI-01 and DG-KRN-CFG-02 state `e2e` and `EREV_PERF_RUN = 1` |
| `05:OQ-ARC-10` Perf-worker protocol ("Perf protocol" ruling) | 05 §2.3 perf row (`perf-worker-1` to `perf-worker-4`, PID files, `run_inline` only for the unmeasured restore); §2.7 perf pool row (B3D-ARC-03); §4.1 PERF-01 (every entity and the primary book; concurrent close runs submitted to `api-perf`, B3D-ARC-01), PERF-02 (DG-PERF-03 pass criterion; PERF-30 mix reported, not asserted); §4.3 PERF-20 (process model, B3D-ARC-02); §4.6 PERF-52; §13 Resolution | Applied; owner follow-up: DG-PERF-02 and DG §3.1 perf-worker entries |
| `05:OQ-ARC-11` Compose environment | 05 §2.8 CFG-01, CFG-11 (`local` permitted under `production` for compose); §7.1 OPR-06; §8.2 DPL-13 (DG-ENV-10 reads `EREV_DB_*` from the environment when `EREV_KEY_PROVIDER=local`; `EnvSecretStore` serves the master keys); §13 Resolution | Applied; owner follow-up: DG-ENV-10, DG-KRN-KEY-03 |
| `05:OQ-ARC-12` Codes | 05 §3.9 "Trace too large" row (exception code `TRACE_TOO_LARGE`, table 15.4-D; `NO_DIRTY_GROUPS` and `EXCEPTIONS_CLEARED` block lock); §6.13 UPL-06 (`FORMULA_NO_CACHED_VALUE`, table 15.4-B; upload `INVALID`); §13 Resolution | Applied (04 rev 1.2 adopts both codes with the same spelling) |
| `05:OQ-ARC-13` Lint contracts | 05 §6.6 SAR-18 (`scripts/secrets_check.py` from `make lint`, DG-MK-lint as amended); §9 TZ-09 (DG-ARC-05 tokens and allow-list); TZ-10 (DESIGN_SYSTEM DS-LINT rule run by `make design-check`); §13 Resolution | Applied; owner follow-up: DG-MK-lint, DG-ARC-05, DESIGN_SYSTEM DS-LINT rule number |
| `05:OQ-ARC-14` Job slot exemption | 05 §5.6 JOB-03 (a job whose `parent_job_id` names a `RUNNING` `CLOSE_RUN` job skips slot acquisition; D-76 adopts it for DG-KRN-JOB-03); §13 Resolution | Applied; owner follow-up: DG-KRN-JOB-03 text |

## 2. Other D-76 rulings touching this file

| Ruling or question | Change (file, section, id) | Status |
|---|---|---|
| `ENGINE_SPEC_B:OQ-B-11` Clawback payload and JET-09f | 05 §3.6.1 Triggers (`cost_adjustment = CLAWBACK`, `payee`, `plan_code`; rev 1.1 `has_clawback` wording withdrawn), Postings (JET-09f with `reason_code = 'CLAWBACK'`; acceleration cites JET-09e) | Applied |
| `ENGINE_SPEC_B:OQ-B-12` `scope_605_35` column; `EAC_IAS37` element | 05 §3.6.2 Scope | Applied |
| `ENGINE_SPEC_B:OQ-B-19` Posted amounts by origin period key and posting class | 05 §3.4 RCP-05 (grouping members, `posting_class` from E-31 posting kinds per S14-R-04); §3.2 `posted` comment | Applied |
| `ENGINE_SPEC_B:OQ-B-20` Prior-period part of every boundary | 05 §3.6.8 Prior-period decomposition (every boundary including measure-only versions, S08-R-14) | Applied |
| `ENGINE_SPEC:OQ-A-04`, `ENGINE_SPEC_B:OQ-B-02` Allocation basis and DB-17 V1 | 05 §1.1 attribute 2 (posted allocations sum to the allocation basis); §3.9 invariant row (V1 compares Σ `allocated_amount` with `transaction_price − consideration_payable_amount`) | Applied |
| `ENGINE_SPEC_B:OQ-B-16` LEGACY book without a contract version | 05 §3.2 OutputBundle `contract_version` absent for LEGACY (S13-R-11) | Applied |
| `OQ-AKT-13` S3-EX26 stays a documentation example | 05 §3.6.3 and §3.6.4 Acceptance (B3D-ARC-07) | Applied |
| `dev-guide:DG-OQ-13` Loop network use | 05 §1.2 ARC-13 (dependency installation in `make setup` is the only loop network use) | Applied |
| D-76 uninstalled materials; workbench tabs; answer-key schema; duplicate keys; CHK-053 and CHK-006 re-baselines; RPO bands | No 05 text | Not applicable |
| Schema and API additions (`SCREENS:R-01`–`R-40`, `SCREENS_B:OQ-B-*`, `ENGINE_SPEC:OQ-A-06`–`13`, `POLICIES:OQ-13`–`14`, `PRD:Q10`, `DESIGN_SYSTEM:OQ-06`–`07`) | 04 owns the catalogue; no 05 rule depends on them | Not applicable |
| `ENGINE_SPEC:OQ-A-01`, `-02`, `-05`, `-14`, `-15`, `-17` to `-22`, `-24`; `ENGINE_SPEC_B:OQ-B-01`, `-03` to `-08`, `-10`, `-17`, `-18`, `-21` to `-24`; `04:OQ-08` to `-12`; `PRD:§9 Q11`–`Q13`; `03:§11 Q4`; `POLICIES:OQ-15`; `DEVIATIONS:OQ-D11`; `dev-guide:DG-OQ-12` | No 05 text | Not applicable |

## 3. Revision log and decisions

| Item | Change | Status |
|---|---|---|
| Header | Revision 1.2; Inputs add D-25b, D-76, D-77, ENGINE_SPEC and ENGINE_SPEC_B sections, coverage files, `objections-engine-spec-b.md` | Applied |
| §0.2 citation rules | Prefixed open questions cited `<document>:OQ-…`; coverage questions bare; `B3D-ARC-nn` family | Applied |
| Revision log | Ten rev 1.2 rows: nine "Applied" rows and one "Decisions taken in B3" row; table B3D-ARC-01 to B3D-ARC-08 | Applied |
| §13 | Intro: D-76 closes OQ-ARC-10 to OQ-ARC-14; D-25b supersedes OQ-ARC-04; no open question remains and none is opened (D-77) | Applied |
