# B1 cross-document consistency review

| Field | Value |
|---|---|
| Author | Cross-document consistency reviewer, design phase B1 (slug `b1-consistency`) |
| Date | 2026-09-12 |
| Status | Complete. Submitted to the supervisor. |
| Scope | `docs/03-REQUIREMENTS.md`, `docs/GLOSSARY.md`, `docs/02-PRD.md`, `docs/accounting/POLICIES.md`, `docs/legacy/DEVIATIONS.md`, `docs/legacy/golden/deviations.json`, `docs/04-DATA_MODEL.md`, `docs/dev-guide.md`, `docs/05-ARCHITECTURE.md`, `docs/design/DESIGN_SYSTEM.md`, `docs/design/tokens.css`, `docs/reviews/objections-*.md` (arch-data, pm-register, ra-deviations, ra-policies) |
| Binding inputs | `docs/00-GOAL.md`, `docs/01-DECISIONS.md`, `docs/research/99-gaps.md` |
| Checks | (1) names of entities, enums, ids, routes, make targets and account roles; (2) conformance to `docs/01-DECISIONS.md`; (3) status of 99-gaps P1 and P2 items; (4) contradictions; (5) ambiguity that forces a builder to guess; (6) testability of acceptance criteria |

Evidence labels: **[F]** fact about a document, cited by section id; **[J]** judgement of this reviewer, with a one-line rationale. Abbreviations: 03 = REQUIREMENTS, 04 = DATA_MODEL, 05 = ARCHITECTURE, DG = dev-guide, DS = DESIGN_SYSTEM, POL = POLICIES.

## 0. Bottom line

1. **The documents are largely consistent at the level that matters most.** [F] The 28 account roles match D-14 everywhere. The 52 permission codes of PRD §5.6 equal T-PLT-11 exactly. CTL-001 to CTL-049, the golden-test kinds and counts (122 = 50/24/17/16/10/4/1), the answer-key family codes, the `AK-FAM` slugs, invariants P1 to P14, book codes, report codes and the gate targets named by D-48 and REQ-OPS-007 all agree across 03, 04, DG, POL and DEVIATIONS.
2. **Two blockers stop a gate from being passable as written.**
   - B1-001: `deviations.json` and DEVIATIONS PJR-1 compute golden journal expectations with round(posted allocation × progress). POL ALG-01 §2.1.3, as published, posts round(exact allocation × progress) and CHK-007 and CHK-022 assert different cents. Both `make parity` and `make answer-keys` cannot pass.
   - B1-002: parity probes assert import statuses (`COMMITTED_WITH_FINDINGS`, `REJECTED`) that neither E-40 nor the PRD import state machine produces.
3. **Seventeen majors force a builder to guess.** The largest groups are:
   - literal and key mismatches between D-13, D-21 and 03 on one side and POL and 04 on the other (B1-003, B1-004, B1-005, B1-014);
   - PRD state machines and problem slugs that contradict 04 enumerations and the problem catalogue that DG-ARC-09 locks (B1-006, B1-007, B1-013);
   - 05 contradicting the dev guide on process model, packaging, configuration, worker queues and make targets (B1-008, B1-009, B1-010);
   - undecided D-14 counter-entry roles and clearing purposes (B1-015).
4. **P1 gaps not yet closed.** C-04, C-11 / M-RA-02, M-RA-03, M-DES-01, U-03 and M-ARCH-02 remain partly open. Each waits on an unwritten deliverable (answer-key corpus, SCREENS.md, ENGINE_SPEC.md) or a supervisor decision. P2 M-RA-04 is untouched by any document (§4).
5. **Recommended D-number amendments (§9):** D-11a, D-13a, D-14a, D-17a, D-21a, D-25a, D-30a, D-40a and D-48a, plus new decisions D-72 (in-process mock adapters) and D-73 (identifier authority).

| Severity | Count | Ids |
|---|---:|---|
| Blocker | 2 | B1-001, B1-002 |
| Major | 17 | B1-003 to B1-019 |
| Minor | 20 | B1-020 to B1-039 |

## 1. Method and limits

- **Read in full:** 00-GOAL, 01-DECISIONS, 99-gaps, 03, GLOSSARY and the four objection files.
- **Read by section:**
  - PRD §0 to §3, §5 to §9, J-13 and J-14;
  - POL §0, §1, §2.1 to §2.4, §5.0 (POL-240 to POL-246 rows), §6 to §8;
  - DEVIATIONS §0 to §6, §9 to §11;
  - 04 §0 to §3, T-PLT-01 to T-PLT-12, T-REF-07, T-SL-04, T-RPT-01, T-IMP-01, T-IMP-05, §14, §15, §18 to §20;
  - DG §0 to §4, §6.4 to §6.8, §9, §10 to §12, KRN-ERR, KRN-JOB and KRN-REG signatures;
  - 05 §0 to §3.5, §5, §6.18, §7.8, §8.2, §11 to §13;
  - DS §0, §1, §7.1, §10 to §15;
  - `tokens.css` header and theme selectors.
- **Machine checks** (scripts in `.scratch/design-b1-consistency/`, run 2026-09-12):
  - `deviations.json` field and status inventory;
  - PRD permission codes vs T-PLT-11;
  - PRD problem slugs vs 04 §15.2;
  - report codes vs T-RPT-01;
  - greps for make targets, queue names, AK-FAM slugs and 99-gaps industry terms.
- **Limits:**
  - PRD journeys other than J-13 and J-14 were checked only by grep for slugs, statuses and routes.
  - 04 tables not listed above, 05 §4, §6.1 to §6.17, §7.1 to §7.7, §9, §10, DS §2 to §6 and §7.2 to §9 were not read line by line. Findings there are limited to what cross-references exposed.
  - ENGINE_SPEC.md, SCREENS.md, BUILD_SPEC.md and `docs/accounting/answer-keys/` do not exist yet; §6 lists the obligations this phase places on them.

## 2. Findings

### 2.1 Blockers

#### B1-001 Parity journal expectations use a posting-rule composition that ALG-01 rejects

| Field | Value |
|---|---|
| Severity | Blocker |
| Documents and sections | POL §2.1.3 ALG-01, CHK-007, CHK-020, CHK-022, JET-04a, OQ-12; DEVIATIONS §0 item 3, §3 PJR-1, §4.2, §7.1, §9.2, OQ-D1, OQ-D2; `docs/legacy/golden/deviations.json` `tests` (the 19 `journal_entry_totals` B cases, for example `je-step-04`, `je-month-2023-01`); PRD §2.8 WLD-X-26; `objections-ra-deviations.md` O-3; DG-PAR-09, DG-AK-04, DG-AK-33 |
| Issue | **[F] What POL publishes:** ALG-01 §2.1.3 posts C_t = round(X × f_t), with X the exact allocation, bounded by the posted allocation A and aligned to A at completion. CHK-007: "round(118.533201) = 118.53 (not round(237.07 × 0.5) = 118.54)". CHK-022 (GT-04 and GT-05, January 2023): Dr 21001 295.69 / Cr 5002 118.53.<br>**[F] What the parity assets say:** DEVIATIONS PJR-1 posts round(A_p × f_p). `deviations.json` `je-step-04` expects 21001 debit 295.70 and 5002 credit 118.54, and PRD WLD-X-26 repeats 295.70 and 118.54.<br>**[F] Why no build can pass:** DG-PAR-09 forbids editing expected values, and DG-AK-33 requires every CHK id in an answer key. One engine rule cannot pass both `make parity` (G3) and `make answer-keys` (G4).<br>**[J] Which side is stale:** DEVIATIONS. ALG-01 as published is the literal D-11 rule and removes the one-cent catch-ups on untouched POBs that O-3 objects to (POL OQ-12).<br>**Notation:** JET-04a writes A′_p for the exact allocation, a symbol ALG-01 reserves for the posted allocation. |
| Proposed resolution | 1. The supervisor confirms ALG-01 §2.1.3 as published (D-11a, §9).<br>2. The supervisor adds posting rule `EXACT-CUM` to `research-harness/deviations/build_deviations.py`: PCR_p(t) = min(max(round(X_p × f_p), 0), A_p), with PCR_p(t) = A_p when f_p = 1, mirrored for negative allocations. The supervisor reruns the script and replaces `deviations.json`.<br>3. The supervisor regenerates DEVIATIONS §0, §3 PJR-1, §4.2, §7.1, §9 and `signoff_required`. Expect fewer B cases, because rounding exact cumulative revenue reproduces most legacy cents.<br>4. PRD WLD-X-26 is recomputed from the new `je-month-2023-01`.<br>5. POL JET-04a writes X′_p.<br>6. BUILD_SPEC holds every item citing `GT:journal_entry_totals` until steps 1 to 4 are done. |
| Owning document | `docs/legacy/DEVIATIONS.md` and `deviations.json` (supervisor rerun); `docs/02-PRD.md` §2.8; `docs/accounting/POLICIES.md` JET-04a |

#### B1-002 Parity probes assert import statuses that no document defines

| Field | Value |
|---|---|
| Severity | Blocker |
| Documents and sections | `deviations.json` probes P1 (`COMMITTED_WITH_FINDINGS`), P2 (`COMMITTED`), P3 and P4 (`REJECTED`); 04 E-40 `import_status`; PRD §5.2 SM-05; 05 §5.5 IPL-01, IPL-03, IPL-05; DEVIATIONS §5 #5; DG-PAR-06, DG-PAR-09, DG-KRN-ERR-05 |
| Issue | [F] DG-PAR-06 asserts `import_status` and `error_code` exactly. The mismatches:<br>- E-40 has no `COMMITTED_WITH_FINDINGS`.<br>- SM-05 moves a file with an `ERROR` finding to `INVALID`. `REJECTED` in SM-05 is an approver rejection.<br>- 05 IPL-01 refuses a duplicate file at upload with 409 `duplicate-import`. No validation runs, so there is no finding row, although DEVIATIONS §5 #5 defines `IMPORT_FILE_DUPLICATE` as a file-stage finding.<br>The runner cannot pass probes P1, P3 and P4 without inventing a mapping. |
| Proposed resolution | **DG-PAR-06 adds a normative mapping.** It does not add stored statuses to E-40:<br>- `COMMITTED` = E-40 `COMMITTED` with no findings.<br>- `COMMITTED_WITH_FINDINGS` = `COMMITTED` with at least one `WARNING` finding.<br>- `REJECTED` = E-40 `INVALID`, or an upload refused with problem `duplicate-import`.<br>- `error_code` = the code of the first `ERROR` finding, or `errors[0].rule_id` of the problem (DG-KRN-ERR-05).<br>**05 IPL-01** returns `errors[]` with `rule_id = "IMPORT_FILE_DUPLICATE"` on the 409. |
| Owning document | `docs/dev-guide.md` §9.6; `docs/05-ARCHITECTURE.md` §5.5 |

### 2.2 Majors

#### B1-003 Policy keys and enum literals differ between the decisions and register and the policy registry

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | D-13, D-21; 03 REQ-BIL-002, REQ-POB-007, REQ-BK-004, REQ-TP-009, REQ-SSP-002, REQ-SSP-005, REQ-CST-003, REQ-POL-004; GLOSSARY "Billing posting"; PRD §1.1, §2.5; POL POL-004, POL-005, POL-028, POL-052, POL-072, POL-074, POL-143; 04 NC-11, §2.1, E-32, E-47, E-84, OQ-06, OQ-07; DG-MK-registry-seed, DG-AK-32 |
| Issue | [F] The same concept has two machine spellings:<br>- **Billing posting:** `billing_posting ∈ {erp, engine}` (D-13, REQ-BIL-002, GLOSSARY, PRD §1.1) vs `billing.posting` ∈ {`ERP`, `ENGINE`} (POL-004, PRD §2.5).<br>- **Material-right exercise:** `material_right_exercise ∈ {continuation, modification}` (D-21, REQ-POB-007) vs `material_right.exercise` ∈ {`CONTINUATION`, `MODIFICATION`} (POL-028).<br>- **Journal mode:** `je_mode = adjustment` (REQ-BK-004) vs `je.posting_mode` ∈ {`GROSS`, `DELTA`} (POL-005, E-32), while 04 §2.1 writes `journal_run.mode = ADJUSTMENT`.<br>- **Returns reversal rate:** `returns_reversal_rate` (REQ-TP-009) vs `returns.reversal_rate` (POL-052).<br>- **SSP method:** `cost_plus_margin` (REQ-SSP-002, E-47) vs `EXPECTED_COST_PLUS_MARGIN` (POL-074).<br>- **Range point:** `nearest_boundary`, `midpoint` (REQ-SSP-005) vs `NEAREST_BOUND`, `MIDPOINT` and three other options (POL-072).<br>- **Amortisation pattern:** `straight_line`, `revenue_proportional` (REQ-CST-003) vs `STRAIGHT_LINE`, `PROPORTIONAL_TO_RELATED_REVENUE` (POL-143, E-84).<br>`make registry-seed` generates the registry from POL §1, and DG-AK-32 validates keys against it. A builder reading D-13 or 03 writes `erp`; seeds and answer keys write `ERP`. |
| Proposed resolution | - POL §1 keys and option literals are the only machine vocabulary for registry values (04 OQ-07 default; D-13a, D-21a).<br>- 03 cites the POL keys in the listed REQ rows; GLOSSARY "Billing posting" shows `billing.posting` `ERP` or `ENGINE`; PRD §1.1 writes `ERP`.<br>- 04 §2.1 replaces `ADJUSTMENT` with `DELTA`.<br>- POL-074 names its hierarchy with the E-47 literals (`observable` → `adjusted_market` → `cost_plus_margin` → `residual`). |
| Owning document | `docs/03-REQUIREMENTS.md`; `docs/GLOSSARY.md`; `docs/02-PRD.md` §1.1; `docs/04-DATA_MODEL.md` §2.1; `docs/accounting/POLICIES.md` POL-074; supervisor (D-13a, D-21a) |

#### B1-004 Ratable conventions required by a P0 REQ have no algorithm

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | 03 REQ-REC-003 (P0); GLOSSARY §4 ("`daily`, `monthly_even`, `mid_month`"); POL POL-090; 04 E-21, OQ-04; PRD §2.6 product templates; DG-AK-23 world `pob_templates.ratable_convention` |
| Issue | [F] REQ-REC-003 requires `daily`, `monthly_even` with partial first and last periods, and `mid_month`. POL-090 offers only `DAILY` and `MONTHLY_WHOLE_MONTHS`, and the latter rejects terms that are not whole months with `TERM_NOT_WHOLE_MONTHS`. E-21 follows POL-090. `mid_month` and partial-period monthly recognition have neither a formula nor a CHK. PRD §2.6 writes `RATABLE` `DAILY`, where E-11 has no `RATABLE` (`TIME_ELAPSED`), and `LABOR_HOURS` where E-11 has `LABOUR_HOURS`. |
| Proposed resolution | **POL-090 options become three:**<br>- `DAILY`, unchanged.<br>- `MONTHLY_EVEN`, which replaces `MONTHLY_WHOLE_MONTHS` and is identical on whole-month terms: f = (whole periods elapsed + days elapsed in a partial first or last period ÷ days in that period) ÷ (whole periods + partial-period fractions of the term).<br>- `MID_MONTH`: a start on or before the 15th counts the start month, a later start begins the next month; an end on or after the 15th counts the end month, an earlier end stops at the previous month; then equal amounts per counted month.<br>**Also:** each option gets a CHK; 04 E-21 follows; PRD §2.6 writes `TIME_ELAPSED` with `DAILY`, and `LABOUR_HOURS`.<br>[J] This keeps the P0 capability (R01 #18) instead of cutting scope; cumulative rounding still applies (ALG-01). |
| Owning document | `docs/accounting/POLICIES.md` §1.6; `docs/04-DATA_MODEL.md` E-21; `docs/02-PRD.md` §2.6 |

#### B1-005 Posting templates are keyed to event names that the event enum does not contain

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | POL §2.3 JET-01 to JET-17, POL-078; 04 E-03 `contract_event_type`; 05 RCP-01, RCP-08, RCP-10; 03 REQ-CON-004; DG-ARC-08 (`PAYLOADS` covers E-03), DG-AK timeline `event_type` |
| Issue | [F] POL names events in PascalCase: `ContractActivated`, `DeliveryRecorded`, `ProgressUpdated`, `ControlTransferred`, `UsageReported`, `RoyaltyEstimateAccrued`, `InvoiceIssued`, `CreditMemoIssued`, `EstimateVersionApproved`, `VcResolved`, `RoyaltyReportReceived`, `ModificationApproved`, `CashReceived`, `ContractCriteriaMet`, `OptionExercised`, `OptionExpired`, `ReturnReceived`. REQ-CON-004 adds `SignificantChangeFlagged`.<br>E-03 is the only event vocabulary for payloads, handlers and answer-key timelines. `ControlTransferred`, `RoyaltyEstimateAccrued`, `VcResolved` and `RoyaltyReportReceived` have no counterpart in it, so a builder must guess which handler posts each template. |
| Proposed resolution | POL §2.3 adds a mapping table and uses the E-03 literals:<br>- activation → `CONTRACT_ACTIVATED`;<br>- delivery and control transfer → `DELIVERY_RECORDED`;<br>- progress → `PROGRESS_RECORDED`, `MILESTONE_ACHIEVED`, `COST_INCURRED`;<br>- usage and royalty statements → `USAGE_REPORTED`;<br>- royalty accrual, VC resolution and estimate approval → `ESTIMATE_CHANGED` (E-09 `ROYALTY_ACCRUAL`, `VARIABLE_CONSIDERATION`);<br>- invoices → `BILLING_RECORDED`; credit memos → `CREDIT_MEMO_RECORDED`;<br>- cash → `PAYMENT_RECEIVED`;<br>- criteria met → `CONTRACT_CRITERIA_MET`;<br>- modifications → `CONTRACT_AMENDED`;<br>- option exercise and expiry → `MATERIAL_RIGHT_EXERCISED`, `MATERIAL_RIGHT_EXPIRED`;<br>- returns → `RETURN_RECORDED`;<br>- time-elapsed revenue and return-window expiry → close-run `CLOSE_RELEASE` passes (05 RCP-08).<br>REQ-CON-004 cites `SIGNIFICANT_CHANGE_FLAGGED`. E-03 is unchanged. |
| Owning document | `docs/accounting/POLICIES.md` §2.3; `docs/03-REQUIREMENTS.md` REQ-CON-004 |

#### B1-006 PRD state machines use values absent from the 04 enumerations

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | PRD §0.1 (values are the 04 enumerations), §2.2 WLD-P-02, §2.11, §3 BR-UX-01, §5.2 SM-02, SM-07, SM-08, SM-11, J-13, J-14; 04 E-04, E-17, E-34, E-35 (withdrawn), E-74, T-REF-07; 03 REQ-CON-002, REQ-CLS-001, REQ-JE-004, REQ-AI-003; DG-ARC-09; 04 DB-03 |
| Issue | [F] PRD uses states that 04 does not define:<br>- **Contract:** `COMBINED` (SM-02); E-17 and REQ-CON-002 have no such status.<br>- **Period:** upper-case `FUTURE`, `OPEN`, `CLOSING`, `CLOSED`, `REOPENED` and a new `PERMANENTLY_CLOSED` (SM-07, WLD-P-02, J-13, J-14). E-04 is lower case, with `permanently_locked`.<br>- **Journal run:** `DRAFT`, `CALCULATING`, `CALCULATED`, `SUBMITTED`, `APPROVED`, `EXPORTING`, `EXPORTED`, `ACKNOWLEDGED`, `PARTIALLY_ACKNOWLEDGED` (SM-08, titled "E-35", a withdrawn enum). E-34 is `draft`, `approved`, `exported`, `acknowledged`, `failed`, `cancelled`.<br>- **AI proposal:** `SUBMITTED` and upper-case statuses (SM-11). E-74 is lower case with no `submitted`.<br>DG-ARC-09 fails the build when enums differ from 04, and DB-03 rejects undeclared transitions, so journeys asserting these values cannot pass. |
| Proposed resolution | PRD §5.2 and the journeys use E literals; UI labels stay in sentence case as copy. Behaviour mapping:<br>- Calculation and export progress is the E-13 `job` state of `JOURNAL_RUN_CALCULATE` and `JOURNAL_EXPORT`.<br>- A submitted run is `draft` with an open `approval_request` on subject `JOURNAL_RUN`.<br>- Partial acknowledgement is per batch (`journal_batch.state`), with counts shown on the run.<br>- A contract absorbed by combination keeps its E-17 status and appears in `combination_group_member`.<br>- A proposal awaiting approval stays `proposed` with an `AI_PROPOSAL_ACCEPTANCE` request. |
| Owning document | `docs/02-PRD.md` §2.2, §2.11, §3, §5.2, J-13, J-14 |

#### B1-007 PRD problem slugs and problem type URI contradict the locked problem catalogue

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | PRD §5.5 ERR-01 to ERR-37, CPY-07, J-13-AC-1, J-13-ALT-1, J-14-AC-2, J-14-ALT-1, J-14-ALT-3 and other journeys; 04 API-C-04, API-C-05, §15.2; DG-KRN-ERR `PROBLEMS` ("exactly the 04 §15.2 rows"), DG-KRN-ERR-01, DG-KRN-ERR-03, DG-ARC-09, DG-OQ-06; 05 §2.5, JOB-06, REL-05 |
| Issue | [F] Slugs:<br>- 30 of the 37 PRD slugs are not among the 27 slugs of 04 §15.2, for example `permission-denied`, `self-approval-blocked`, `approval-stale`, `close-gates-failed`, `later-period-closed`, `sandbox-cannot-post`.<br>- DG-ARC-09 locks `PROBLEMS` to 04, so journey acceptance items that assert PRD slugs and a green `make ci` exclude each other.<br>- 05 raises `job-stalled` (JOB-06) and `release-mismatch` (REL-05), which are in neither list.<br>[F] Body and status:<br>- PRD CPY-07 sets `type = urn:erev:problem:<slug>`; 04 API-C-05 and DG-KRN-ERR-01 set `https://erev.dev/problems/<slug>`.<br>- PRD ERR-34 `unexpected-error` differs from DG-KRN-ERR-03 (`about:blank`).<br>- PRD ERR-05 (400 `idempotency-key-required`) differs from DG-OQ-06 (422 `validation-failed`). |
| Proposed resolution | **04 §15.2 absorbs the slugs with distinct semantics:**<br>- 409: `close-gates-failed`, `later-period-closed`, `activation-checklist-failed`, `field-locked-after-activation`, `option-already-exercised`, `ai-disabled`, `production-reset-forbidden`, `tenant-kind-immutable`, `approver-already-decided` (EREV-APR-002, split from `self-approval`).<br>- 422: `ssp-study-required`, `eac-below-costs-incurred`, `legacy-database-unrecognized`, `scope-not-allowed`, `password-policy`, `upload-type-not-allowed`.<br>- 423 `account-locked`; 401 `session-expired`; 403 `mfa-step-up-required`.<br>- `job-stalled` and `release-mismatch`, statuses per 05.<br>**PRD renames its synonyms:**<br>- `permission-denied` → `forbidden`; `self-approval-blocked` → `self-approval`; `approval-stale` → `stale-approval`; `mfa-enrolment-required` → `mfa-required`.<br>- `sandbox-cannot-post` → `sandbox-restricted` (403); `approved-version-immutable` → `configuration-frozen`; `ssp-effective-range-overlap` → `configuration-overlap`; `fx-rate-missing` → `missing-fx-rate` (422); `migration-source-duplicate` → `duplicate-import`.<br>- `money-must-be-string` and `idempotency-key-required` → `validation-failed` with `rule_id`.<br>- ERR-34 → 500 `about:blank`, with the ERR-34 copy as UI text.<br>**CPY-07** adopts `https://erev.dev/problems/<slug>`. D-73 fixes the authority. |
| Owning document | `docs/04-DATA_MODEL.md` §15.2; `docs/02-PRD.md` §5.5 and journeys |

#### B1-008 The architecture contradicts the dev guide on process model, packaging, configuration and adapters

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | 05 §2.2 CMP-02, CMP-06, CMP-07, CMP-08; §2.3; §2.4 PKG-01, PKG-04 to PKG-07; §2.8 CFG-01, CFG-08, CFG-09, CFG-11, CFG-12, CFG-15, CFG-17, CFG-19; §3.2 ENG-02; §3.4 RCP-01, RCP-07; §5.2 ADP-15; §5.3 ADP-20 to ADP-24; §5.10 AIA-01 to AIA-03, AIA-08; §4 PERF-11; §8.2 DPL-13, DPL-15; OQ-ARC-07, OQ-ARC-08; DG §0.5, §1.1, DG-LAY-03, DG-LAY-05, §2.3, DG-ENV-10, DG-ENV-17, §3.1, DG-RUN-10, DG-RUN-11, DG-API-09, DG-AI-01, DG-AI-02, DG-AI-05, DG-ARC-01, DG-ARC-02, DG-OQ-09, DG-PERF-01; 00-GOAL §5 (ports) |
| Issue | [F] Contradictions:<br>- **Processes:** 05 has `make dev`, PID files `vite.pid` and `mocks.pid`, a mocks process on 8191 (e2e 8198) and e2e PID names `e2e-api.pid`. DG has `make dev-up`, `web.pid` and `api-e2e.pid`, and no mocks process: mocks are mounted in-process under `/api/v1/__mocks__/<adapter>` (DG-API-09). 00-GOAL §5 lists no mock ports.<br>- **Packages:** 05 `erev_mocks`, `web/`, `tools/`, `tests/`, `erev_api/ai/…`, `erev_engine.handlers`, `erev_engine.catalogue` vs DG `erev_api/adapters/mocks/`, `frontend/`, `scripts/`, `backend/tests/`, `erev_api/domain/ai/…`, `erev_engine/stages/`.<br>- **Engine purity:** 05 PKG-01 and ENG-02 allow `pydantic` at the bundle boundary. DG-LAY-03 and DG-ARC-02 fail on any import outside the standard library.<br>- **Persistence and linting:** 05 CMP-02 "SQLAlchemy 2 Core/ORM" vs DG-LAY-05 Core only; 05 PKG-06 `import-linter` vs DG-ARC AST tests; 05 ADP-15 `tests/contract/adapters/` vs DG §9.1 directories.<br>- **Process control:** stop wait 10 s (05 §2.3 rule 2) vs 15 s (DG-RUN-11); PID file written after bind (05) vs immediately (DG-RUN-10).<br>- **Configuration:** 05 CFG-15 `EREV_AI_DISABLED` vs DG `EREV_AI_KILL_SWITCH`. `EREV_PUBLIC_ORIGIN` (the CSRF origin check), `EREV_RUN_DIR`, `EREV_EMAIL_BACKEND`, `EREV_KEY_PROVIDER`, `EREV_LOCAL_KEYRING_PATH` and `EREV_MOCKS_BASE_URL` are absent from DG §2.3, which says "exactly these names". CFG-01 adds `perf`, `compose`, `staging` beyond DG-ENV-10.<br>- **Key material:** DG-ENV-17 derives keys from environment master keys with HKDF; 05 CMP-07 and DPL-13 use a keyring file.<br>- **AI:** 05 `AIRequest` fields (`model_id`, `tools`, `timeout_s`, `request_sha256`) differ from DG §6.7. AIA-02 forces the fake provider for `test`, `e2e` and `perf`; DG-AI-01 only for `test`.<br>- **Performance database:** 05 PERF-11 uses `erev` with tenant `perf-volume`; DG-PERF-01 regenerates the volume on `erev_test` on every run. |
| Proposed resolution | - D-§0 gives the dev guide authority over code structure, commands and tests, and 05's precedence row concedes module paths. 05 is amended to DG in §2.2 to §2.4, §2.8, §3.2 ENG-02, §3.4 module names, §5.2 ADP-15, §5.3, §5.10, §8.2 DPL-13 and DPL-15; OQ-ARC-07 is withdrawn (D-72).<br>- DG §2.3 adds the variables 05 needs: `EREV_PUBLIC_ORIGIN`, `EREV_RUN_DIR`, `EREV_EMAIL_BACKEND`, `EREV_CORS_ORIGINS`, `EREV_TRUSTED_PROXY_HOPS`, `EREV_WORKER_CONCURRENCY`, `EREV_METRICS_ENABLED`, `EREV_METRICS_TOKEN`.<br>- The key model and the performance database follow §8 Q7 and Q8. |
| Owning document | `docs/05-ARCHITECTURE.md` (primary); `docs/dev-guide.md` §2.3 |

#### B1-009 Job queue names differ, so dev and e2e workers would not consume most jobs

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | DG KRN-JOB `task(kind, queue: Literal["default", "compute", "export", "maintenance"])`, DG-RUN-02, DG-RUN-05 (`--queues default,compute,export,maintenance`); 05 §5.6 execution profiles, CFG-23, DPL-31 |
| Issue | [F] 05 assigns job kinds to `compute`, `imports`, `close`, `outbox`, `reports`, `maintenance`, `integrations` and `ai`, and splits hosted workers on those names. DG allows four queue names and starts workers on those four only. A builder following 05's profile table enqueues imports, close runs, exports, reports, sync runs and AI tasks on queues that `make dev-up` and `make e2e` workers never read, and the Literal type rejects them. |
| Proposed resolution | DG KRN-JOB adopts the eight 05 queue names in its `Literal`. DG-RUN-02 and DG-RUN-05 omit `--queues`, so workers consume all queues (CFG-23 default). [J] 05's split serves the hosted two-service worker layout (DPL-31) and costs nothing locally. |
| Owning document | `docs/dev-guide.md` §5.12, §3.1 |

#### B1-010 Make targets named by the architecture and design system are not defined

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | 05 REL-01 (`make release-manifest`), PERF-04 and PERF-11 (`make perf-seed`), OQ-ARC-08 (`make db-reset`), OPR-15 and OPR-17 (`make backup`), SAR-17 (`make audit-deps`), DPL-05 (`make docker-build`), SAR-43 (`make zap-baseline`), §2.3 (`make dev`, `make compose-up`), REL-02 (`.run/gates/<gate>-<build sha>.log`); DS OQ-04 (`make dev`); DG §4 (target catalogue), DG-MK-00g (`.run/reports/<target>/report.json`); 03 REQ-CTL-003 (P0), CTL-032 |
| Issue | [F] None of these targets exists in DG §4. REQ-CTL-003, a P0 control platform requirement, needs the release manifest that `make release-manifest` produces. REL-02 reads gate logs from `.run/gates/`, while DG writes gate reports to `.run/reports/`. |
| Proposed resolution | - DG §4 adds `DG-MK-release-manifest`: offline; writes `release-manifest.json` per 05 REL-01 from `.run/reports/<target>/report.json`, hashing those files.<br>- DG §4 adds `DG-MK-perf-seed` if §8 Q7 is adopted.<br>- DG §4 adds a "Supervisor targets" table for `audit-deps`, `zap-baseline`, `docker-build` and `backup`, where network or Docker is allowed (D-48a).<br>- 05 replaces `make dev` with `make dev-up`, `make compose-up` with `make compose-verify`, `make db-reset` with `make seed RESET=1`, and `.run/gates/` with `.run/reports/`; DS OQ-04 writes `make frontend` and `make dev-up`. |
| Owning document | `docs/dev-guide.md` §4; `docs/05-ARCHITECTURE.md`; `docs/design/DESIGN_SYSTEM.md` §15 |

#### B1-011 Demo user identities conflict

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | 03 REQ-DEMO-005 ("`<role>@demo.erev`"); PRD §2.3 WLD-U-01 to WLD-U-12, WLD-U-R1, WLD-U-R2, §9 Q1; DG-MK-seed, DG-E2E-05 |
| Issue | [F] REQ-DEMO-005 requires one user per default role named `<role>@demo.erev`. PRD §2.3 names persona users (`maya@demo.erev`, `marcus@demo.erev` and others), each holding several roles, and the seed and Playwright fixtures follow PRD. The two identity models cannot both be built. |
| Proposed resolution | REQ-DEMO-005 is amended per PRD Q1: "one named persona user per default role (`<name>@demo.erev`, PRD §2.3)". The `EREV_DEMO_PASSWORD` rule stays. |
| Owning document | `docs/03-REQUIREMENTS.md` REQ-DEMO-005 |

#### B1-012 Tenant creation has no requirement, route or CLI, although e2e depends on it

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | PRD BR-PLT-01 (`erev tenant create --code … --admin <email>`), BR-PLT-02 (`AUTO-BOOTSTRAP`), E2E-05, §9 Q3; 04 §14.3 (`tenant.provision` command), API-R-04 (no create route); DG-KRN-DB-03 (`tenant.provision`), §1.1 `cli.py`, §4 (no target); 05 CMP-08 (CLI list without a tenant command); 03 §3.1 (no REQ) |
| Issue | [F] The fresh-tenant e2e project (J-01, J-20, J-21, J-23) creates tenants through `erev tenant create`. 04 defines the provisioning transaction, but no document defines the CLI command, its arguments, the invitation, or the bootstrap approval rule as build items. |
| Proposed resolution | - 03 adds REQ-PLT-038 "Operator tenant provisioning" (P0, 1.0): CLI `erev tenant create` per BR-PLT-01, bound to 04 §14.3 `tenant.provision`, with the BR-PLT-02 bootstrap rule. Acceptance: UNIT; E2E-05.<br>- DG §5 publishes the CLI signature.<br>- 04 §14.3 adds the invitation row and the `AUTO-BOOTSTRAP` rule seed. |
| Owning document | `docs/03-REQUIREMENTS.md` §3.1; `docs/dev-guide.md` §5; `docs/04-DATA_MODEL.md` §14.3 |

#### B1-013 Notification kinds and defaults conflict

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | PRD §5.4 NTF-01 to NTF-12, NTF-R2, J-13.14 (NTF-06), J-14.3 (NTF-07), §9 Q4; 04 E-69 `notification_kind`; 05 §5.8 NTF-01 to NTF-03; DG-ARC-09 |
| Issue | [F] PRD NTF-02 `ITEM_APPROVED`, NTF-06 `PERIOD_LOCKED` and NTF-07 `PERIOD_REOPENED` are not E-69 values, and journeys J-13 and J-14 expect NTF-06 and NTF-07. 05 §5.8 contradicts PRD §5.4 on three points:<br>- **Recipients:** export failures go to Integration Admins and the run creator (05) vs the exporter and Controllers (PRD NTF-10).<br>- **Email defaults:** off except two kinds (05 NTF-03) vs on for eight kinds (PRD).<br>- **Mandatory kinds:** in-app `APPROVAL_ASSIGNED` cannot be turned off (05) vs NTF-09 cannot be turned off (PRD NTF-R2). |
| Proposed resolution | 04 E-69 adds `ITEM_APPROVED`, `PERIOD_LOCKED` and `PERIOD_REOPENED`. 05 §5.8 NTF-01 to NTF-03 defer recipients, email defaults and mandatory kinds to PRD §5.4, the product-behaviour authority (D-§0). Collision of `NTF-` ids: B1-027. |
| Owning document | `docs/04-DATA_MODEL.md` E-69; `docs/05-ARCHITECTURE.md` §5.8 |

#### B1-014 Finding severities and exception codes have no single vocabulary

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | DEVIATIONS §5 (40 codes, `ERROR`/`WARNING`); PRD §5.5 IMP-01 to IMP-41, BR-DAT-02, WLD-B-04 (`BLOCKING`), §2.5 `AUTO-IMP-01`; `deviations.json` probes (`severity: WARNING`); 04 E-41, E-43, T-IMP-05 `code` examples (`DAT-HDR-001`, `REF-UNMAPPED-PRODUCT`, `JE-UNMAPPED-ROLE`), 5182 (`messages.severity`); DG-KRN-ERR-05, DG-AK checkpoints `exceptions: [{code, severity}]`; 05 IPL-12 (`DAT-CONTROL-TOTALS`), ADP-02 (`INT-STALE-VERSION`), AIA-05 (`AI_REFUSAL`), AIA-13 (`AI_TEXT_DISABLED`); POL JET-01b (`INVOICE_ON_NOT_A_CONTRACT`), POL-090 (`TERM_NOT_WHOLE_MONTHS`), ALG-01 (`NEGATIVE_WEIGHT`, `TOTAL_WEIGHT_ZERO`) |
| Issue | **[F] Severity:** findings are `ERROR`/`WARNING` in DEVIATIONS, PRD and `deviations.json`; `exception_item.severity` is `BLOCKING`/`WARNING`/`INFO` (E-43); row status is `ERROR`/`WARNING` (E-41).<br>**[F] Codes:** four formats coexist:<br>- 04 examples `DAT-HDR-001`;<br>- 05 `DAT-CONTROL-TOTALS` and `INT-STALE-VERSION`;<br>- UPPER_SNAKE in DEVIATIONS, POL and DG-KRN-ERR-05;<br>- PRD IMP-41 `PRODUCT_UNMAPPED`, not in DEVIATIONS §5.<br>Answer-key checkpoints assert `{code, severity}` as an exact set, so a builder must guess both vocabularies. |
| Proposed resolution | - 04 adds §15.4 "Finding and exception code catalogue": one UPPER_SNAKE registry that absorbs DEVIATIONS §5, the POL codes, 05 codes renamed (`CONTROL_TOTALS_MISMATCH`, `STALE_SOURCE_VERSION`, `AI_REFUSAL`, `AI_TEXT_DISABLED`), and PRD `PRODUCT_UNMAPPED`.<br>- T-IMP-05 `code` holds only catalogue codes.<br>- One mapping rule: finding severity `ERROR` → `exception_item.severity` `BLOCKING`; `WARNING` → `WARNING`.<br>- Parity and answer-key assertions use finding severities.<br>- PRD WLD-B-04 writes "two `ERROR` findings raising `BLOCKING` exception items". |
| Owning document | `docs/04-DATA_MODEL.md` (new §15.4, T-IMP-05); `docs/05-ARCHITECTURE.md` codes; `docs/02-PRD.md` IMP-41, WLD-B-04 |

#### B1-015 Counter-entry roles and clearing purposes are undecided and not stored

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | D-14; `objections-arch-data.md` OBJ-01; `objections-pm-register.md` OBJ-PM-01 and 03 §11 Q1; `objections-ra-policies.md` O-1 and POL OQ-01; 04 E-01, OQ-03, T-REF-15, T-SL-04; POL §0.8, JET-01b, JET-02 (agent), JET-07c, JET-09a and a′, JET-14, JET-16, JET-17, CHK-029, CHK-130, CHK-131; PRD §2.6 (2090 subledger clearing) |
| Issue | [F] POL templates post `BILLING_CLEARING` with a "purpose": unapplied cash, payable to supplier, inventory and cost of sales, payroll and commissions, cost of sales, equity, investments. No 04 column stores a purpose: T-SL-04 has none, and the T-REF-15 mapping key is role × entity × optional product or category. The purposes can therefore neither be routed to different accounts nor asserted.<br>Three different D-14a proposals exist:<br>- arch-data: `COST_OF_REVENUE`, `CONTRACT_COST_CLEARING`;<br>- pm-register: `COST_OF_REVENUE`, `CONTRACT_COST_OFFSET`, `RECEIVABLE_CONTRA`;<br>- ra-policies: `COST_OF_REVENUE` plus renaming `BILLING_CLEARING` to `SUBLEDGER_CLEARING` with `clearing_purpose`.<br>Answer keys CHK-029 (S3-EX22) and CHK-130 and CHK-131 (S8-CONTRACT-COSTS) assert these counter-entries. |
| Proposed resolution | **One D-14a (§9):**<br>- Add `COST_OF_REVENUE` (JET-07c, JET-16 claims) and `CONTRACT_COST_CLEARING` (JET-09a and a′).<br>- Keep the literal `BILLING_CLEARING`, and add enum `clearing_purpose` ∈ {`BILLING`, `UNAPPLIED_CASH`, `AP_SUPPLIER`, `INVENTORY`, `EQUITY`, `INVESTMENTS`} as a nullable column on `subledger_line` and `account_mapping_rule`, required when the role is `BILLING_CLEARING`.<br>- Reserve `RETAINED_EARNINGS` and `FINANCING_OBLIGATION` (later).<br>- Do not add `RECEIVABLE_CONTRA`.<br>[J] Engine-mode concessions post to `REFUND_LIABILITY` (JET-04b), and credit losses stay outside the engine (POL-125).<br>**Then:** 04 E-01, T-REF-15 and T-SL-04 change; POL JET literals change; PRD §2.6 maps the new roles. |
| Owning document | Supervisor (D-14a); then `docs/04-DATA_MODEL.md`, `docs/accounting/POLICIES.md` §0.8 and §2.3, `docs/02-PRD.md` §2.6 |

#### B1-016 Upload size limits conflict

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | 03 REQ-SEC-012 ("25 MB files, 50,000 rows per sheet"), REQ-PLT-035; PRD NFR-50 (gate), ERR-37; 04 T-PLT-29 `size_bytes` (ATTACHMENT and SSP_STUDY 25 MiB; IMPORT_SOURCE 50 MiB; LEGACY_DATABASE 500 MiB); 05 DPL-12 (nginx 26m attachments, 51m imports, 501m migrations) |
| Issue | [F] A 30 MB CSV, or any legacy `ASC606.db` above 25 MB, is accepted by 04 and 05 but refused by REQ-SEC-012 and by the PRD NFR-50 gate. REQ-MIG-001 (P0) would block large legacy databases. |
| Proposed resolution | REQ-SEC-012, PRD NFR-50 and ERR-37 adopt the per-purpose limits of 04 T-PLT-29: attachments and SSP studies 25 MiB; imports 50 MiB and 50,000 rows per sheet; legacy databases 500 MiB. ERR-37 copy names the limit of the upload's purpose. |
| Owning document | `docs/03-REQUIREMENTS.md` REQ-SEC-012; `docs/02-PRD.md` NFR-50, ERR-37 |

#### B1-017 The G4 corpus scope cannot be checked mechanically

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | 00-GOAL §3 G4 ("every ASC 606 topic in research 04, every industry playbook in research 05, FX, multi-entity and modification scenarios"); DG-AK-18, DG-AK-33; 03 §1.4 `AK-FAM` hints (research 05 scenario ids such as FS-02, GE-03); PRD §2.10 ("numbers … come from the revenue accountant's answer-key families") |
| Issue | [F] DG-AK-33 reports gaps only for `AK:` hints, `AK-FAM:` slugs, CHK ids and family codes. Nothing checks that every research 05 playbook, or every research 04 section, has a key. G4 "100% of the corpus passes" can be satisfied by a corpus that omits whole playbooks. |
| Proposed resolution | DG-AK-33 adds two coverage lists:<br>- every research 05 §26 scenario id of the six 1.0 clusters (D01, D02, D04, D05, D08, D12, per REQ-DEMO-001) appears in some active key's `derived_from.research05`;<br>- every research 04 section §1 to §13 is the prefix of some `derived_from.research04` id.<br>The answer-key README publishes both lists. A gap fails `make answer-keys` under "Corpus gaps (supervisor)". |
| Owning document | `docs/dev-guide.md` §9.5.8 |

#### B1-018 Binding obligations delegated to documents that do not exist yet

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | `docs/accounting/ENGINE_SPEC.md` (cited by D-§0; POL §0.1, POL-153; 05 §3; DG §1.1 `stages/`, DG-PAR-05, DG-OQ-05); `docs/design/SCREENS.md` (00-GOAL G8; 03 A3; PRD §0.1 SF ids; DG-E2E-07; DS §14); `docs/BUILD_SPEC.md` (G1; 03 §1.4 `UNIT` hints); `docs/accounting/answer-keys/` (G4; POL CHK ids; DG §9.5) |
| Issue | [F] This phase fixed obligations that later authors must honour:<br>- trace measure names for parity (DG-OQ-05);<br>- engine stage module names (DG §1.1) vs 05 EMOD names;<br>- the loss-stage algorithm (POL-153);<br>- estimate parameters (05 OQ-ARC-03);<br>- the DEVIATIONS OQ-D8 and OQ-D9 confirmations;<br>- screen routes that may rename SF defaults (PRD §0.1);<br>- report column definitions (M-DES-06);<br>- named assertions for `UNIT` hints.<br>A later author who misses them re-opens settled questions. |
| Proposed resolution | The supervisor's briefs for these deliverables include the obligation table of §6.2 verbatim. |
| Owning document | Supervisor (briefs for ENGINE_SPEC.md, SCREENS.md, BUILD_SPEC.md, answer-key corpus) |

#### B1-019 D-30 wording would block blank-memo rows that the register and parity suite require to process

| Field | Value |
|---|---|
| Severity | Major |
| Documents and sections | D-30 ("dropped rows on blank memo … become explicit validation errors"); `objections-ra-deviations.md` O-1; 03 REQ-REC-025, REQ-DAT-005; DEVIATIONS DEV-010, §5 #4, OQ-D3; `deviations.json` `probe-P1-blank-memo-drops-progress-rows` (`COMMITTED_WITH_FINDINGS`, `WARNING`); PRD IMP-04 |
| Issue | [F] 03, DEVIATIONS, PRD and `deviations.json` process blank-memo rows with a `WARNING` finding. D-30, which ranks above all of them, says "validation errors". A builder applying the higher-precedence text (DG-DONE-12) blocks the file and fails probe P1 under G3. |
| Proposed resolution | D-30a per O-1 (§9). No document text changes. |
| Owning document | Supervisor (D-30a) |

### 2.3 Minors

| ID | Documents and sections | Issue | Proposed resolution | Owning document |
|---|---|---|---|---|
| B1-020 | 03 REQ-JE-010; POL-006; 04 E-33, OQ-05 | REQ-JE-010 requires a contract-level journal grain. POL-006 options lack it, while E-33 adds `CONTRACT_ACCOUNT_DIMENSIONS`. The registry is generated from POL §1, so the value cannot be selected. | POL-006 adds option `CONTRACT_ACCOUNT_DIMENSIONS` (04 OQ-05 default). | POLICIES §1.1 |
| B1-021 | 03 REQ-SSP-005; GLOSSARY "SSP range and range policy"; POL-071, POL-072; 04 OQ-06 | REQ-SSP-005 fixes "inside the range, SSP = stated price" and describes a two-option book policy outside it. POL-071 allows `MIDPOINT` inside the range; POL-072 has five options at levels T, E, P. | REQ-SSP-005 and GLOSSARY cite POL-071 and POL-072 as registry values (04 OQ-06 default). | 03; GLOSSARY |
| B1-022 | 03 REQ-MOD-012; 04 API-R-31, E-25 | `early_renew` is a subscription command (REQ-MOD-012, API-R-31) with no E-25 `modification_kind`. | 04 E-25 adds `EARLY_RENEWAL`. | 04 |
| B1-023 | 03 REQ-POB-003, REQ-POB-005, REQ-POL-001; 04 E-105; DG-AK world `distinctness`, `series_increment_unit` | Series is both a distinctness value (`series`) and a separate flag ("`series = true`", "series flag"). | REQ-POB-005 and REQ-POL-001 read "distinctness `series` with an increment unit"; no separate flag. | 03 |
| B1-024 | 03 REQ-PLT-005; 04 T-PLT-11 `requires_mfa`; PRD §5.6 checks; D-44 | REQ-PLT-005 names four roles, but `integration.manage` requires MFA, so Integration Admin is forced to enrol too (PRD §5.6 says so). | REQ-PLT-005 cites T-PLT-11 `requires_mfa` as the rule. | 03 |
| B1-025 | 03 REQ-PLT-007; 04 T-PLT-02, OQ-01 | `user.external_id` names a reserved word; 04 uses `app_user.external_id`. | 03 writes `app_user.external_id`. | 03 |
| B1-026 | PRD §9 Q5, Q7, ACT-52; 04 E-74, E-08 | Q5 says E-74 lacks `failed`; it has it. Q7 asks for `MIGRATION_PROMOTION`, which E-08 already has, while ACT-52 still names `IMPORT_COMMIT`. | Close Q5 and Q7; ACT-52 names `MIGRATION_PROMOTION`. | PRD |
| B1-027 | 05 §0.2, §2.8, §5.8; PRD §5.4; POL §0.3, §0.6; 04 §0.2; DS §15 | Id collisions: `NTF-nn` (PRD notification catalogue vs 05 rules); `PT-` (04 partitioning classes vs POL policy topics); unprefixed `OQ-nn` in POL, 04 and DS; 05 `CFG-nn` vs POL approval code `CFG`. 05 §0.2 claims no collision. | 05 renames its notification rules `NTR-nn`. Cross-document citations write "POL PT-NN" and `<document>:OQ-nn`. | 05; POLICIES §0.3 |
| B1-028 | DS DS-COL-00, DS-LINT-00, DS-LINT-14, DS-DEN-01, §15 OQ-03, OQ-04; `tokens.css` header comment; DG §0.5, DG-OQ-04, DG-FE-13 | DS defaults (`web/src/…`, `tools/design_check.py`, `make dev`, an inline density script) were superseded by DG §0.5 and DG-OQ-04 but not updated. The `tokens.css` comment still names `web/src/styles/tokens.css`. | DS and the `tokens.css` comment cite the DG paths and DG-FE-13 (external `/theme-init.js`). No behaviour change. | DESIGN_SYSTEM; tokens.css |
| B1-029 | 03 REQ-UX-010; DG-MK-vocab-check; DS DS-CPY-02, DS-LINT-19; PRD LTM-O5, SF-26 | Two vocabulary lints differ. REQ-UX-010 is case-sensitive and lists "Carve-in", "Carve-out", "Unbilled A/R". DS-LINT-19 is case-insensitive and lists "Revenue planned", "POB's", "net position". PRD LTM-O5 allows "Unbilled A/R" in SF-26 help, which the REQ-UX-010 scan of `frontend/src` flags. | One list = the union, case-insensitive, whole words. The allow-list adds the SF-26 help catalogue next to the legacy column files. `make vocab-check` implements it and DS-LINT-19 references it. | dev-guide §4.3; DESIGN_SYSTEM §12 |
| B1-030 | 03 REQ-UX-006; DS DS-FMT-06, DS-I18N-03, DS-VER-03; PRD §9 Q8 | REQ-UX-006 (P0) lets each tenant choose a minus sign or parentheses; DS fixes parentheses and says the style "never varies". | DS-FMT-06: parentheses by default, tenant setting `minus` allowed; DS-VER-03 tests both (03 ranks above DS). | DESIGN_SYSTEM |
| B1-031 | DS §15 OQ-05, DS-CH-03; 03 REQ-RPT-009; POL-201; PRD WLD-X-07 | DS recommends five RPO time bands; REQ-RPT-009 and POL-201 default to three (within 12, 13 to 24, after 24 months). | Close DS OQ-05: DS-CH-03 renders the bands the API returns (POL-201). | DESIGN_SYSTEM |
| B1-032 | DS DS-CMP-02 (Home `/`, Close `/close`), DS-CMP-03 (`?period=2026-09`); PRD §3 SF-01 (`/home`), SF-05 (`/close/:entityCode/:book/:period`); 04 API-C-11 (`FY2023-P01`); DG-AK world (`FY<year>-P<nn>`) | Rail routes and the period identifier differ between DS and PRD. The UI period format differs from the API `period_key`. | SCREENS.md fixes routes by SF id. The UI `period` parameter uses the API-C-11 `period_key`. | DESIGN_SYSTEM; SCREENS.md brief |
| B1-033 | 04 §18; DG-MIG-03, DG-MIG-04, DG-OQ-01, DG-OQ-02 | 04 says revisions are forward-only (downgrade raises), in twelve layered revisions. DG requires one self-contained revision per BUILD_SPEC item, with a downgrade used only by the round-trip test. | 04 §18 adopts the DG-OQ-01 and DG-OQ-02 wording: dependency order, per-item revisions, downgrades only on test databases. | 04 |
| B1-034 | D-40; D-31; 03 REQ-MIG-001, REQ-MIG-004; PRD WLD-F-15, WLD-F-16; DG-PAR-02 | The legacy import reads `ASC606.db` and the fixture builder writes a SQLite fixture. A literal reading of D-40 ("no SQLite anywhere") forbids both. | D-40a (§9). | Supervisor |
| B1-035 | 03 REQ-OPS-013; PRD NFR-11; 05 §7, §12 | Restore-test cadence: annual (03, PRD) vs quarterly restore verification plus an annual DR exercise (05). | REQ-OPS-013 and NFR-11 adopt the stricter 05 cadence. | 03; PRD |
| B1-036 | 03 REQ-AI-007, REQ-CLS-019; 04 T-PLT-31 | Anomaly thresholds ("threshold", "N days", "X%") and data-quality "N days" have no defaults, so the P1 behaviours are untestable as written. | 04 T-PLT-31 adds `ai.anomaly.revenue_change_ratio` `"0.50"`, `ai.anomaly.revenue_ahead_of_billing_days` 60, `ai.anomaly.allocation_adjustment_ratio` `"0.20"`, `close.dq_revenue_without_billing_days` 60 and `close.dq_inactive_contract_days` 90. [J] Conservative review triggers; tenants tune them. | 04 |
| B1-037 | 03 REQ-CLS-011; PRD §5.6, §2.5 routing | REQ-CLS-011 needs two approvers besides the requester, at least one a Controller. PRD grants `period.reopen_approve` only to Controllers, so every reopen needs two Controllers and a one-controller S1 tenant cannot reopen. | PRD §5.6 also grants `period.reopen_approve` to Revenue Reviewer; routing keeps "at least one Controller". | PRD |
| B1-038 | DS DS-CMP-05; 04 E-69; PRD §5.4 | The notification panel specifies item types ("job completed", "mention") that have no E-69 kind or PRD notification. | DS-CMP-05 lists E-69 kinds only. | DESIGN_SYSTEM |
| B1-039 | D-17, D-21, D-25; `objections-ra-deviations.md` O-2; `objections-ra-policies.md` O-2, O-3; POL-026, POL-163 | Documents already implement the proposed behaviour, but the decision text is narrower: DEV-002 approval unit (D-17), option SSP formula (D-21), refundable-advance override (D-25). No builder conflict; auditors read the decisions. | D-17a, D-21a, D-25a (§9). | Supervisor |

## 3. Conformance to `docs/01-DECISIONS.md`

| Decision | Status | Evidence | Finding |
|---|---|---|---|
| D-§0 precedence | Conforms; identifier authority unstated | Each document's precedence row matches D-§0; DG §0 ranks itself above 04 and 05 for paths and commands | B1-006, B1-007, B1-014 (D-73) |
| D-01 | Conforms | REQ-PLT-023 to 025, REQ-CON-015; PRD LTM-10 to LTM-14 | — |
| D-02 | Conforms | REQ-UX-001; GLOSSARY §4; DS-CMP-02 ten destinations | B1-029 (lint lists) |
| D-03, D-04 | Conform | 03 §5 CONF-08 to CONF-11; 03 §7 | — |
| D-10 | Conforms; 05 lets the engine import `pydantic` | 05 ENG-01 to ENG-12; DG §7 | B1-008 |
| D-11 | POL conforms; DEVIATIONS PJR-1 applies another composition | POL §2.1; DEVIATIONS §3 | B1-001 |
| D-12 | Conforms | GLOSSARY §2; POL ALG-02; DG P6; 04 T-CON-09 | — |
| D-13 | Behaviour conforms; literals differ | POL-004, JET-03, JET-06; REQ-BIL-002 | B1-003 |
| D-14 | 04 E-01 exact; counter-entries unresolved | 04 §3.1; POL §0.8; three objections | B1-015 |
| D-15, D-16 | Conform | POL-122, ALG-03; JET R1; 04 DB-06, DB-16 | — |
| D-17 | Conforms; objection O-2 | DEVIATIONS §2.2; DG-PAR-07 | B1-039 |
| D-18, D-19, D-20 | Conform | POL ALG-04, ALG-09, ALG-10; PRD WLD-X-06; 04 NC-08; 05 §9 | — |
| D-21 | Behaviour conforms; literals and formula wording differ | POL-026, POL-028, ALG-05 | B1-003, B1-039 |
| D-22, D-23, D-24 | Conform | POL ALG-06, ALG-07, JET-13, POL-007; 04 E-02 | — |
| D-25 | Conforms; objection O-3 | POL ALG-08, POL-160 to POL-164 | B1-039 |
| D-26 | Conforms with open items | POL §4 register through ASU 2026-03; 14 ASUs not retrieved (POL OQ-07, OQ-08) | §4 (U-03) |
| D-30 | Flow conforms; blank-memo wording and duplicate-file handling diverge | REQ-DAT-001; 05 IPL-01 to IPL-12; DEVIATIONS §5 | B1-002, B1-019 |
| D-31 to D-34 | Conform | REQ-MIG-001 to 003; POL §6.3; REQ-RPT-012, 013; 04 §17; REQ-BK-004, JET-15 | — |
| D-40 | Conforms; SQLite wording; 05 "Core/ORM" | DG-LAY-05; 04 NC-18 | B1-008, B1-034 |
| D-41 | Conforms | DG §2.2; DS-ICO (Phosphor), DS-LINT-07, DS-LINT-08 | — |
| D-42, D-43, D-44 | Conform | 04 §1.4, §1.5, §14; DG-ENV-12; 05 TXN-01 to TXN-09 | — |
| D-45 | API conforms; PRD slugs and type URI diverge | 04 API-C-01 to API-C-16 | B1-007 |
| D-46 | Conforms; configuration names and paths diverge | REQ-AI-001 to 010; DG §6.7; 05 §5.10 | B1-008 |
| D-47 | Conforms | 05 §8; DG-MK-compose-verify, DG-MK-tf-validate | — |
| D-48 | Gate targets conform; 05 names targets outside DG §4 | DG §4.4; REQ-OPS-007 | B1-010 |
| D-60, D-61, D-62 | Conform | DS §1, §7, §11, §12 | — |
| D-70, D-71 | Conform | DG-ENV-13 (`erev_rv_*`); DG-GATE-01 | — |
| 00-GOAL §5 ports | 05 adds mock ports 8191 and 8198 | 05 §2.3, OQ-ARC-07; DG-API-09 | B1-008 (D-72) |

## 4. Status of 99-gaps P1 and P2 items

### 4.1 Not fully closed

| Gap | Pri | Status | Evidence | What remains | Owner |
|---|---|---|---|---|---|
| C-04 | P1 | Partial | 04 E-01 equals D-14 | Counter-entry roles and clearing purposes (B1-015) | Supervisor (D-14a) |
| C-11, M-RA-02 | P1 | Partial | POL ALG-08, CHK-080 to CHK-083 | No machine-readable keys; `docs/accounting/answer-keys/` does not exist | Answer-key corpus |
| M-RA-03 | P1 | Partial | POL ALG-07, CHK-070, CHK-071; PRD WLD-K-04, WLD-X-14 | Key files | Answer-key corpus |
| M-DES-01 | P1 | Partial | PRD §3 surfaces and §4 journeys; DS §7 components | Screen specifications | SCREENS.md |
| U-03 | P1 | Partial | POL §4.2 register through ASU 2026-03 | 14 ASUs not retrieved (POL OQ-07); the ASU extending 606-10-50-11 is unidentified (OQ-08) | Supervisor confirmation before G12 |
| M-ARCH-02 | P1 | Partial | 05 §3.5, §3.6 (EMOD-12, EMOD-15 to EMOD-24) | Algorithms deferred to ENGINE_SPEC.md; 05 OQ-ARC-03, OQ-ARC-04 | ENGINE_SPEC.md; 04; POLICIES |
| C-13, M-PM-02 | P1 | Mostly closed | REQ-MIG-001 to 009; PRD J-20, J-21; POL-210 to POL-214; 04 T-MIG-01 to 03 | `ONBOARDING_DIFFERENCE` mechanics | ENGINE_SPEC.md |
| M-RA-04 | P2 | Open | 0 hits for casino, timeshare, broker-dealer, depository, oil and gas or insurer in 02, 03, 05 and POL | Coverage decision for the five AICPA industries | 03 §6.8 (§8 Q13) |
| M-RA-07 | P2 | Open | PRD §2.10 asserts structure only for industry tenants | Industry keys with JEs, CA vs receivable split and YAML | Answer-key corpus |
| M-DES-06 | P2 | Partial | DS §5 chart specifications | Report columns and drill-through | SCREENS.md |
| M-ARCH-07 | P2 | Partial | DG §9.5 schema; `deviations.json` | Corpus; coverage lists (B1-017) | Answer-key corpus; DG |
| M-ARCH-06 | P2 | Closed with pending additions | 04 §15.3 | `POST /users/{membership_id}/anonymise`, `POST /files/{id}/shred`, `GET /metrics` (05 OQ-ARC-06, OQ-ARC-09) | 04 |

### 4.2 Closed

- **P1:** C-01 and M-PM-01 (03 §3, §5); C-03 (POL-004, JET-03); C-05 and M-ARCH-03 (04 §2.1); C-07 (POL §2.1.5, CHK-004, CHK-006; parity side B1-001); C-08 (DEVIATIONS §2.2, DG-PAR-07); C-09 (POL ALG-04); M-RA-01 (POL §1, §6.1); M-ARCH-01 (05 §6).
- **P2:**
  - C-02 (GLOSSARY §2, POL ALG-02); C-06 (04 TY-01, CHK-003a, CHK-003b); C-10 (DEV-021); C-12 (POL §6.2); C-14 (REQ-BK-004, JET-15).
  - U-01, U-02, U-04 (POL §4.3); U-05 (03 §9, 05 PERF-56).
  - M-RA-05, M-RA-06 (POL PT-01 to PT-11); M-RA-08 (03 §10, POL-230 to POL-234).
  - M-PM-03 to M-PM-10 (03 §2, §6; GLOSSARY).
  - M-DES-02 to M-DES-05 (DS §2 to §9; PRD BR-PLT-04 to 06, SM-01, SM-07).
  - M-ARCH-04 (05 §7); M-ARCH-05 (05 §9); M-ARCH-08 (DG §9.6, DEVIATIONS §10).
  - M-ARCH-09: DG-LAY-09, DG-ARC-05. [F] `git -C ~/dev/erev-legacy status --short` printed nothing on 2026-09-12, so the untracked `__pycache__/` reported by 99-gaps §1 is gone.

## 5. Name agreement matrix

| Name family | Documents compared | Result | Finding |
|---|---|---|---|
| Account roles | D-14; 04 E-01; POL §0.8, JET-01 to JET-17; PRD §2.6; 03 | Agree (28 literals) | B1-015 (additions) |
| Books | D-24; 04 E-02; POL-007; REQ-BK-001; GLOSSARY; DS-CMP-03 labels | Agree | — |
| Contract statuses | REQ-CON-002; 04 E-17; GLOSSARY | Agree; PRD SM-02 adds `COMBINED` | B1-006 |
| Period states | REQ-CLS-001; 04 E-04, T-REF-07; GLOSSARY | Agree; PRD uses upper case and `PERMANENTLY_CLOSED` | B1-006 |
| Journal states | REQ-JE-004; 04 E-34 | Agree; PRD SM-08 differs | B1-006 |
| Policy keys and literals | D-13, D-21; 03; GLOSSARY; POL §1; 04 | Differ | B1-003, B1-004, B1-020, B1-021 |
| Event types | 04 E-03; POL §2.3; REQ-CON-004; DG timeline; 05 RCP-01 | POL and 03 differ | B1-005 |
| Permissions | REQ-PLT-008; 04 T-PLT-11; PRD §5.6 | Agree (52 = 52) | B1-024 (MFA wording) |
| Default roles | REQ-PLT-008; 04 T-PLT-09; PRD §1.2 | Agree | — |
| Controls | 03 §4.1 CTL-001 to CTL-049; DG `controls.yaml`, DG-ARC-10 | Agree | — |
| Golden kinds and counts | 03 §1.4; DEVIATIONS §9.1; `deviations.json` `counts`; DG §9.6 | Agree (122) | B1-001, B1-002 (values) |
| DEV ids | DEVIATIONS §6 (76 entries); `deviations.json` `dev_id`, `related_dev_ids` | Agree | — |
| Finding codes and severities | DEVIATIONS §5; PRD IMP; 04 E-41, E-43, T-IMP-05; 05; POL | Differ | B1-014 |
| Problem slugs | 04 §15.2; DG `PROBLEMS`; PRD ERR; 05 | Differ | B1-007 |
| Notification kinds | 04 E-69; PRD §5.4; 05 §5.8; DS-CMP-05 | Differ | B1-013, B1-038 |
| Answer-key families and slugs | POL §0.7; DG-AK-01, DG-AK-04; 03 `AK-FAM` (9 slugs); DG-AK-33 | Agree | B1-017 (scope) |
| Invariants | 03 `PROP:Pn`; DG §9.7; 05 §11 | Agree (P1 to P14) | — |
| Report codes | 04 T-RPT-01 (55 codes); DG-PAR; 04 §17 | Agree | — |
| Make targets | D-48; REQ-OPS-007; DG §4; 05; DS | Gate targets agree; 05 and DS name undefined targets | B1-010 |
| Environment variables | DG §2.3; 05 §2.8 | Database URL names agree; others differ | B1-008 |
| API routes | 04 §15.3; 05 §2.5, §5; DG §6.4 | Agree except mock mounting | B1-008 |
| UI routes | PRD §3; DS-CMP-02, DS-CMP-03 | Differ | B1-032 |
| Code paths and packages | DG §1; 05 §2.4; DS §15 | Differ | B1-008, B1-028 |
| Job queues | DG KRN-JOB; 05 §5.6 | Differ | B1-009 |
| Demo users | REQ-DEMO-005; PRD §2.3; DG-E2E-05 | Differ | B1-011 |
| Ports | 00-GOAL §5; DG §3.1; 05 §2.3 | Agree except 05 mock ports | B1-008 |
| Upload limits | REQ-SEC-012; PRD NFR-50; 04 T-PLT-29; 05 DPL-12 | Differ | B1-016 |
| Identifier families | all | Collisions | B1-027 |

## 6. Testability and delegations

### 6.1 Testability of acceptance criteria

- **Register level.** Acceptance hints are test families (03 §1.4). DG-DONE-01 maps each family to a gate. `UNIT` hints depend on BUILD_SPEC named assertions (B1-018, §6.2 row 8).
- **Gate level:**
  - G3 is blocked by B1-001 and B1-002.
  - G4 scope is not mechanically checkable (B1-017).
  - G5 has an explicit mapping (DG §9.7). G6 (DG-TST-20 to DG-TST-25) and G7 (DG-MK-controls-report) are explicit.
  - G8 depends on SCREENS.md (B1-018) and on the PRD states, slugs and notifications (B1-006, B1-007, B1-013).
  - G9 thresholds are explicit, but the performance database is undecided (B1-008, §8 Q7).
  - G11 evidence for REQ-CTL-003 lacks its make target (B1-010).
- **Requirement level:** anomaly and monitor defaults are missing (B1-036); the NFR-50 upload-limit gate contradicts 04 (B1-016); the three ratable conventions lack CHKs (B1-004).
- **What already works.** J-13 and J-14 acceptance items are exact: figures (WLD-X-13), problem codes, states and control ids. Once B1-006 and B1-007 are fixed they are directly executable. The answer-key schema (DG §9.5) is strict enough to be red on any ambiguity: no implicit floats, cross-validated handles, exact money places.

### 6.2 Obligations for documents not yet written

| # | Obligation | Created by | Target |
|---|---|---|---|
| 1 | Stage module names under `erev_engine/stages/`, with a recorded mapping from 05 EMOD-01 to EMOD-28 | DG §1.1; 05 §3.5 | ENGINE_SPEC.md |
| 2 | Trace measure names equal the 04 columns `revenue_cum`, `remaining_allocation`, `position_obligation`, `catch_up_amount`, `catch_up_cum`, `netting_reclass_amount`, `remaining_billing`, each with `rounding_residue` | DG-PAR-05, DG-OQ-05 | ENGINE_SPEC.md |
| 3 | Loss-stage algorithm, including "loss already recognised through margin to date" | POL-153 | ENGINE_SPEC.md |
| 4 | Posting composition = ALG-01 §2.1.3 as confirmed by D-11a | B1-001 | ENGINE_SPEC.md; answer keys |
| 5 | Typed `parameters` on `estimate_version` for return-asset carrying cost, recovery cost and window end | 05 OQ-ARC-03 | 04 amendment; ENGINE_SPEC.md |
| 6 | Confirm the DEV-058 reclass fallback and the DEV-060 zero-remaining return rate | DEVIATIONS OQ-D8, OQ-D9 | POLICIES ALG-02, POL-052 |
| 7 | Routes for SF-01 to SF-28 (defaults may change; SF ids never); report columns and drill-through (M-DES-06); the screen list for `screens.spec.ts` | PRD §0.1, §3; DS §14; DG-E2E-07 | SCREENS.md |
| 8 | A named assertion for every `UNIT` hint of a 1.0 REQ; hold items citing `GT:journal_entry_totals` until B1-001 closes | 03 §1.4; DG-DONE-01 | BUILD_SPEC.md |
| 9 | Keys for every CHK id, `AK:` hint, `AK-FAM:` slug, research 05 §26 scenario of the six 1.0 clusters, and research 04 §1 to §13 | DG-AK-33; B1-017 | Answer-key corpus |
| 10 | FX, multi-entity and industry keys | 99-gaps C-11, M-RA-02, M-RA-03, M-RA-07 | Answer-key corpus |

## 7. Gaps closed

This review owns no 99-gaps item. It records the status of every P1 and P2 item in §4 (check 3). It adds one verified fact: the legacy-repository contamination of M-ARCH-09 is no longer present (§4.2).

## 8. Open questions for supervisor

| # | Question | Recommended default | Findings |
|---|---|---|---|
| Q1 | Posting composition for native and parity books | Confirm ALG-01 §2.1.3 as published (D-11a); rerun `build_deviations.py` with rule `EXACT-CUM`; approve the remaining cent differences as one class (D-17a) | B1-001, B1-039 |
| Q2 | Scope of D-14a | `COST_OF_REVENUE`, `CONTRACT_COST_CLEARING`, `clearing_purpose` on `BILLING_CLEARING`; reserve `RETAINED_EARNINGS` and `FINANCING_OBLIGATION`; no `RECEIVABLE_CONTRA` | B1-015 |
| Q3 | Ratable conventions | Add `MONTHLY_EVEN` (replacing `MONTHLY_WHOLE_MONTHS`) and `MID_MONTH` to POL-090, with CHKs | B1-004 |
| Q4 | Problem catalogue authority | Union per B1-007; 04 is the authority (D-73) | B1-007 |
| Q5 | Job queue names | The eight 05 queues; workers consume all queues by default | B1-009 |
| Q6 | Mock adapters | In-process under `/api/v1/__mocks__/<adapter>` (DG-API-09); no mock ports (D-72) | B1-008 |
| Q7 | Performance database | Persistent tenant `perf-volume` in `erev`, built by an idempotent `make perf-seed` to month 23 closed (05 PERF-11). `make perf` runs the month-24 close in a sandbox copy (REQ-PLT-023), so repeated runs start from the same state. DG-PERF-01 and DG-PERF-02 are amended. [J] Regenerating 10,000 contracts through commands on every run exceeds the loop's time budget, and `erev_test` is dropped by every test session. | B1-008, B1-010 |
| Q8 | Local key material | DG model: master keys in `.env` through `EnvSecretStore`, per-tenant HKDF (DG-ENV-17). 05 CMP-07 `LocalKeyProvider` becomes an adapter over the same protocol. Hosted Cloud KMS and Secret Manager are unchanged. | B1-008 |
| Q9 | Tenant provisioning requirement | Add REQ-PLT-038 (P0, 1.0) | B1-012 |
| Q10 | Upload limits | Per-purpose limits of 04 T-PLT-29 | B1-016 |
| Q11 | G4 coverage lists | Research 05 §26 scenarios of D01, D02, D04, D05, D08, D12, and research 04 §1 to §13 | B1-017 |
| Q12 | Reopen approvers | Grant `period.reopen_approve` to Revenue Reviewer; routing keeps at least one Controller | B1-037 |
| Q13 | M-RA-04 industries (casino gaming, oil and gas, broker-dealers and depository institutions, timeshare, insurers' non-insurance fees) | Record them in 03 §6.8 as later (datasets and answer keys after 1.0). Non-606 streams use the scope flag (REQ-CON-016). No 1.0 REQ. | §4.1 |

## 9. D-number amendments recommended to the supervisor

| Id | Amends | Proposed text | Rationale | Findings |
|---|---|---|---|---|
| D-11a | D-11 | "Cumulative rounding rounds the exact cumulative amount: C_t = round(X × f_t), where X is the exact allocation, bounded by the posted allocation A and equal to A at completion. The legacy parity suite applies the same rule." | The literal D-11 rule; no one-cent catch-ups on untouched POBs; one rule for native and parity books | B1-001 |
| D-13a | D-13 | "The registry key is `billing.posting` with literals `ERP` (default) and `ENGINE` (POLICIES POL-004). `erp` and `engine` in this decision are descriptive." | One machine vocabulary | B1-003 |
| D-14a | D-14 | "Add `COST_OF_REVENUE` and `CONTRACT_COST_CLEARING`. Lines and mapping rules with role `BILLING_CLEARING` carry `clearing_purpose` ∈ {`BILLING`, `UNAPPLIED_CASH`, `AP_SUPPLIER`, `INVENTORY`, `EQUITY`, `INVESTMENTS`}. `RETAINED_EARNINGS` and `FINANCING_OBLIGATION` are reserved (later)." | Resolves OBJ-01, OBJ-PM-01 and ra-policies O-1 without renaming a role used across four documents | B1-015 |
| D-17a | D-17 | "Cent differences between legacy report rounding and posted amounts under D-11a form one deviation class (DEV-002), approved once by the revenue accountant; the case list is regenerated mechanically by `research-harness/deviations/build_deviations.py`." | Approval effort scales with methods, not lines | B1-039 |
| D-21a | D-21 | "SSP of an option = expected purchase amount × incremental discount (discount on exercise less the discount available without exercise) × likelihood of exercise (606-10-55-44), or the renewal practical alternative (55-45). The registry key is `material_right.exercise` ∈ {`CONTINUATION` (default), `MODIFICATION`}." | Codification text; one machine vocabulary | B1-003, B1-039 |
| D-25a | D-25 | "An approved contract-level override may treat refundable advance consideration as monetary (remeasured at the closing rate) in the ASC606 book; the IFRS15 book always applies IFRIC 22." | Matches POL-163 | B1-039 |
| D-30a | D-30 | "Legacy silent defects become explicit findings in the dry-run diff and the exception queue: blocking errors where the input cannot be processed correctly (for example duplicate files, swallowed exceptions), warnings where it can (for example blank memos)." | Matches 03, DEVIATIONS and probe P1 | B1-019 |
| D-40a | D-40 | "SQLite is never an application datastore or test database. Reading legacy `ASC606.db` files (D-31) and building SQLite test fixtures from the golden CSVs are permitted." | The legacy import requires it | B1-034 |
| D-48a | D-48 | "Loop targets run offline and are defined in `docs/dev-guide.md` §4, including `make release-manifest`. Supervisor targets that need network or Docker (`make audit-deps`, `make zap-baseline`, `make docker-build`, `make backup`) are listed separately and are never run by the loop." | 05 names targets that no Makefile contract defines | B1-010 |
| D-72 (new) | — | "Mock adapter servers are mounted in-process under `/api/v1/__mocks__/<adapter>` only when `EREV_ENV` is `dev`, `test` or `e2e`. No process binds a port outside `docs/00-GOAL.md` §5." | Shared-machine port discipline | B1-008 |
| D-73 (new) | D-§0 | "Add a precedence row: enumeration literals, permission codes, problem slugs, and finding and exception codes → `docs/04-DATA_MODEL.md` (§3, T-PLT-11, §15.2, §15.4). Other documents cite them verbatim; UI labels are copy." | Removes guesswork between PRD, 05 and 04 | B1-006, B1-007, B1-013, B1-014 |
