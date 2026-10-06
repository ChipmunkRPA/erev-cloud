# eRev Cloud - adversarial security review, 2026-09-29 (lane SEC)

Scope: the product as built at `main e139ade8` on branch `sprint/l10`. This is an adversarial
review of exploitability, not a checklist audit. Method: read the route table and the kernel
(auth, db/session, approvals, idempotency, audit, files, events, adapters), follow data from
request to SQL, and prove the strongest candidates with throwaway proof-of-concept tests run
against this lane's own test database. PoC tests live under `.run/sec/**` and are not committed;
each is named below and its decisive output quoted. Findings are CONFIRMED (reproduced with a PoC)
or PLAUSIBLE (code path shown, not reproduced - the reason is stated).

The programme's own severity scale is used: **P1** cross-tenant data access, authentication bypass,
privilege escalation, silent financial-record tampering, remote code execution, secret disclosure;
**P2** same-tenant authorization bypass, integrity or audit gaps, SSRF with limited reach,
brute-force weaknesses; **P3** hardening and defence in depth.

The review was run by one lead reviewer and six scoped helper reviewers (contract-side authz,
close/journals/imports/reports, input handling, tenancy/jobs/sandbox, deploy/HTTP surface,
frontend). Every finding below was re-checked against the code by the lead before inclusion; where
a claim was not independently reproduced it is marked "not verified by the lead".

## Counts

| Severity | CONFIRMED | PLAUSIBLE | Total |
|---|---|---|---|
| P1 | 1 | 0 | 1 |
| P2 | 20 | 1 | 21 |
| P3 | 12 | 12 | 24 |

The one P1 and every P2 is summarised in the table, then detailed. P3 findings are listed compactly
in section P3. "The product as built is not a release candidate until the P1 and the financial-
integrity / maker-checker P2s (S2-S19) are resolved": a single low-privilege user can post revenue
on an unapproved contract (S1), product master-data edits silently re-time posted revenue (S5), and
entity scope is not enforced on approvals, imports, several reads or period-open (S11, S13-S18).

| Id | Sev | Status | Title | Key file:line |
|---|---|---|---|---|
| S1 | P1 | CONFIRMED | Preparer alone posts revenue on a contract with zero approvals (Step-1 other-book gate) | `domain/contracts/events.py:805-819` |
| S2 | P2 | CONFIRMED | Any `audit.read` holder (incl. an operator support grant) downloads every file in the tenant | `domain/platform/attachments.py:349` |
| S3 | P2 | CONFIRMED | Approval authority delegated from a password-only session; no MFA, step-up or SoD | `domain/platform/approval_delegations.py:84-175` |
| S4 | P2 | CONFIRMED | Revenue recognised without the CONTRACT_ACTIVATION approval / Controller step | `domain/contracts/events.py:838-864` |
| S5 | P2 | CONFIRMED | Product policy_values re-time recognition of ACTIVE posted contracts, no approval | `domain/reference/commands.py:3095-3097` |
| S6 | P2 | CONFIRMED | Regroup before posting injects unapproved lines into an ACTIVE contract | `domain/contracts/regroup.py:304-486` |
| S7 | P2 | CONFIRMED | Manual delivery/progress events recognise revenue with no MANUAL_EVENT approval | `domain/contracts/events.py:1068-1132` |
| S8 | P2 | CONFIRMED | Auto-approval / routing rules unconstrained; author then self-publishes routing | `domain/policies/rule_sets.py:153-186` |
| S9 | P2 | CONFIRMED | Preparer releases a SYSTEM recognition hold on an unreviewed judgement | `domain/contracts/holds.py:307-347` |
| S10 | P2 | CONFIRMED | SSP book scope is outside the approved content and editable while SUBMITTED | `approvals/subjects.py:2104-2126` |
| S11 | P2 | CONFIRMED | Approvals of contract-bound / run subjects are not entity-scoped (22 subjects) | `approvals/subjects.py` (entity_id None) |
| S12 | P2 | CONFIRMED | SSP calculator run exports contract lines of every entity | `domain/ssp/calculator.py:681-743` |
| S13 | P2 | CONFIRMED | Judgement records readable across entity scope | `domain/policies/judgements.py:572-590` |
| S14 | P2 | CONFIRMED | Combination groups readable across entity scope (contract-id oracle) | `domain/contracts/combination.py:1037-1054` |
| S15 | P2 | CONFIRMED | A posting in flight at lock approval lands in the CLOSED period | `db/migrations/versions/0040_ctr_3_subledger.py:169-205` |
| S16 | P2 | CONFIRMED | Import pipeline ignores the uploader's and approver's entity scope | `domain/imports/diff.py:127-129,169-188` |
| S17 | P2 | CONFIRMED | Entity-restricted users read other entities' data on tenant-level read routes | `api/v1/imports.py`, `subledger.py`, `audit.py` |
| S18 | P2 | CONFIRMED | `POST /periods/{id}/open` accepts `period.close` held for any entity | `domain/reference/commands.py:1742-1765` |
| S19 | P2 | CONFIRMED | Close/import evidence is shreddable; a shredded lock dataset blocks later locks | `domain/platform/privacy.py:544-587` |
| S20 | P2 | CONFIRMED | Sandbox webhook endpoints activate over the API and fan out (client-only gate) | `domain/platform/webhook_endpoints.py:158,205` |
| S21 | P2 | CONFIRMED | MFA-mandatory enrolment gate is client-only, lifted by a page reload | `api/v1/session.py:122-135` |
| S22 | P2 | CONFIRMED (config) / PLAUSIBLE (exploit) | Compose api and worker run with `erev_owner` creds and the master keys | `deploy/compose.yaml:22-27,92,114` |

---

## P1

### S1. A preparer alone posts revenue on a contract with zero approval decisions (Step-1 other-book activation gate)

- **Status.** CONFIRMED (reproduced by the lead). PoC `.run/sec/sec-con/test_step1_path.py::test_f13_preparer_alone_activates_through_other_book_assessment`; the lead re-ran it (`.run/sec/main/verify_f13.log`, "1 passed").
- **Where.** `backend/erev_api/domain/contracts/events.py:765-802` (`_step1_errors`: a SUBMITTED, never-reviewed judgement suffices; the payload book is compared only to the judgement's own book, never to the entity's enabled books); `:805-819` (`_gate` fabricates `CONTRACT_ACTIVATED` with a passed `STEP1_RECORD` checklist); `:838-864` (`step1_events` appends the gate on the caller's authority); `:1068-1090` (`record_events` appends, no `approvals.submit`). Engine: `backend/erev_engine/stages/s02_contract_identification/status.py:114-124` (DRAFT + `CONTRACT_ACTIVATED` -> `_activation` -> ACTIVE) and `:157-160` (`_observe` records a not-probable assessment only for the book it names, so an assessment in another book is ignored while the fabricated `CONTRACT_ACTIVATED` still lands). `backend/erev_api/events/stream.py:182-206` header projection leaves the header at `NOT_A_CONTRACT`.
- **Attacker.** A default `revenue_accountant` (holds `contract.create`, `judgement.create`, `event.record`; no approval permission).
- **Exploit.**
  1. `POST /api/v1/contracts` - a DRAFT of USD 1,080,000 (the amount is above the USD 1,000,000 Controller second-step threshold).
  2. `POST /api/v1/judgements` topic `NOT_A_CONTRACT`, `book "IFRS15"` (the entity keeps only ASC606), then `POST /judgements/{id}/submit`. Nobody reviews it.
  3. `POST /api/v1/contracts/{id}/events` with `If-Match "s1"`, one `COLLECTIBILITY_ASSESSED` payload `{book: "IFRS15", is_probable: false, judgement_record_id}`. The route appends the assessment plus `CONTRACT_ACTIVATED`. The engine, evaluating ASC606, ignores the IFRS15 assessment, sees `CONTRACT_ACTIVATED` on a DRAFT and returns ACTIVE; revenue posts.
- **Evidence (quoted).** `F13 approval decisions by anyone: 0`; `F13 engine status per book: [["ASC606", "ACTIVE", null, "985.4000"]]`; `F13 posted subledger totals by account role: {"REVENUE": "-29562.0400", "CONTRACT_LIABILITY": "29562.0400"}`; `F13 stored header: [{"status": "NOT_A_CONTRACT", "activated_at": null}]`. So: revenue and a contract liability are posted, no approval decision was recorded, and the header contradicts the engine.
- **Why P1.** Maker-checker on contract activation (REQ-CON-005/006, CTL-004/005) is defeated by one person; revenue posts on a contract the activation control never approved and whose header says it is not a contract - silent financial-record tampering.
- **Fix.** (1) Reject a Step-1 payload or judgement whose book is not an enabled book of the contracting entity. (2) The route must not append `CONTRACT_ACTIVATED` on the recorder's authority; a not-a-contract conclusion needs a REVIEWED `NOT_A_CONTRACT` record (REQ-POL-008) and must not make the engine activate any book. (3) `CONTRACT_CRITERIA_MET` must route the CONTRACT_ACTIVATION approval before the engine treats any book as ACTIVE. (4) Add an invariant that the engine's per-book status and the header status cannot diverge into a recognising status. Docs: REQ-CON-002, REQ-CON-005/006, REQ-POL-008, CTL-004/005.

---

## P2

### S2. Any `audit.read` holder downloads every file in the tenant; an operator support grant inherits this

- **Status.** CONFIRMED (lead PoC `.run/sec/main/test_poc_file_read_auditread.py`, "1 passed"). Operator amplification: PLAUSIBLE (code path; not reproduced).
- **Where.** `backend/erev_api/domain/platform/attachments.py:345-362` `_readable`: `if AUDIT_READ in principal.permissions: return True` - readable for every `file_object` of the tenant whatever its purpose, uploader or attachment. Route `backend/erev_api/api/v1/files.py:145-168` (`GET /files/{id}/content`, `require_authenticated()`). Operator inheritance: `backend/erev_api/auth/operators.py:40` (`READ_ONLY_PERMISSIONS` includes `audit.read`), `:56,124`.
- **Exploit.** An auditor (default `auditor` role, `audit.read`, no upload right, not the uploader, no attachment) calls `GET /api/v1/files/{id}/content` for any id and receives the raw bytes - IMPORT_SOURCE (customer CSV with PII), ATTACHMENT (contract PDFs), SSP_STUDY, LEGACY_DATABASE, snapshot datasets. A platform operator under an APPROVED support grant holds `audit.read` too, so a "read-only" support session exfiltrates every document in the customer tenant, across the cross-organization boundary REQ-PLT-036 / SAR-29 / TB-7 promise is read-only.
- **Evidence (quoted).** `auditor GET content: 200 bytes match: True`; control `viewer GET content: 404`. The auditor read the exact upload bytes; a `viewer` without `audit.read` is correctly 404.
- **Fix.** Authorise file-content reads by the attachment's subject-read permission and purpose, not blanket `audit.read`; narrow the operator READ_ONLY scope so it never confers file-content download. Docs: REQ-PLT-012, REQ-PLT-035, REQ-PLT-036, 04 T-PLT-29.

### S3. Approval authority is delegated from a password-only session, with no MFA, no step-up and no SoD check

- **Status.** CONFIRMED (lead PoC `.run/sec/main/test_poc_delegation_no_mfa.py`, "1 passed").
- **Where.** `backend/erev_api/api/v1/approvals.py:353-380` (`POST /approval-delegations` guarded by `command(per_subject=True)` = `require_authenticated()` only); `backend/erev_api/domain/platform/approval_delegations.py:84-175` (`create_delegation`: checks the codes are approval permissions the delegator holds, but never MFA, never a step-up, never `sod.assert_*`). Contrast: creating an API client needs a fresh step-up (`auth/api_clients.py`), approving needs MFA (`approvals.py:123-128`).
- **Exploit.** An attacker with only Ben's password opens a session (MFA challenge pending, `mfa_verified_at` null). That session is refused on any `requires_mfa` route (control: `GET /users` -> 403 `mfa-required`), yet `POST /approval-delegations` succeeds and hands Ben's `access.approve` and `support_grant.approve` to any active member (here Mia, who holds no role) for 90 days. Mia then approves on Ben's behalf.
- **Evidence (quoted).** `GET /users with Ben's password-only session -> 403 mfa-required`; `POST /approval-delegations with the password-only session -> 201`; `POST /approvals/{id}/approve by the delegate -> 200 APPROVED`; decision `{'decision': 'APPROVE', 'approver': Mia, 'on_behalf_of': Ben}`.
- **Fix.** Require an MFA-verified session (and a fresh step-up, matching the approve path) to create a delegation, and run the SoD check on the delegated permissions. Docs: REQ-PLT-005 (`requires_mfa` covers `access.approve` and `support_grant.approve`), REQ-PLT-013, BR-PLT-07, THR-10.

### S4. Revenue recognised without the CONTRACT_ACTIVATION approval or the Controller second step

- **Status.** CONFIRMED. PoC `.run/sec/sec-con/test_step1_path.py::test_f12_revenue_without_contract_activation_approval`.
- **Where.** same `events.py` Step-1 path as S1; the difference is `book "ASC606"` plus a COLLECTIBILITY judgement reviewed by one `revenue_reviewer` (`judgement.review`), then `CONTRACT_CRITERIA_MET`. The engine goes ACTIVE (`s02.../status.py:118-124`) with the header at `PENDING_REVIEW`.
- **Exploit.** A preparer plus any one `judgement.review` holder (not a Controller) bring a >= USD 1,000,000 contract into recognition, skipping the activation checklist, the `contract.approve` routing and the Controller second step.
- **Evidence (quoted).** `F12 CONTRACT_ACTIVATION approval requests ever opened: 0`; `F12 engine status of the stored version: [... "status_in_book": "ACTIVE" ... "revenue_cum": "1970.8000"]`; `F12 posted subledger totals: {"REVENUE": "-29562.0400", "CONTRACT_LIABILITY": "29562.0400"}`.
- **Fix.** As S1 (3): `CONTRACT_CRITERIA_MET` must route CONTRACT_ACTIVATION before recognition. Docs: REQ-CON-005/006, CTL-004/005.

### S5. Product `policy_values` re-time recognition of ACTIVE, posted contracts with no approval

- **Status.** CONFIRMED. PoC `.run/sec/sec-con/test_maker_checker.py::test_f7_product_policy_values_change_active_contract`.
- **Where.** `backend/erev_api/domain/reference/commands.py:3095-3097` (`update_product` stores `policy_values` after a shape check only; only `principal_agent` routes an approval); `backend/erev_api/domain/contracts/bundles.py:1210-1245,1591-1609` (the LIVE product row's values are merged at OBLIGATION scope and win over the template). Route `api/v1/products.py:165-189` (`masterdata.maintain`, held by default `revenue_accountant`, `integration_admin` and `service_account` API clients).
- **Exploit.** `PATCH /api/v1/products/{id}` `{"policy_values": {"recognition.time_convention": "MONTHLY_EVEN"}}`. The next recompute of any contract using the product re-times its schedule and posts the difference; 23 of 155 registry parameters accept PRODUCT level, including approval-coded ones.
- **Evidence (quoted).** before `{"FY2026-P01": "10191.78", "FY2026-P02": "9205.48", ...}`; `pending approval requests after the product edit: 0`; after `{"FY2026-P01": "10000.00", "FY2026-P02": "10000.00", ...}`; `posted subledger lines before: 18` -> `after: 36`.
- **Fix.** Pin product-level accounting values into the contract at activation, or version product accounting attributes under CFG approval with impact simulation; refuse approval-coded parameters at PRODUCT level without approval. Docs: POLICIES section 0.5 rule 3 / 0.6, REQ-CON-007.

### S6. Regroup before posting injects unapproved DRAFT lines into an ACTIVE contract

- **Status.** CONFIRMED. PoC `.run/sec/sec-con/test_maker_checker.py::test_f6_regroup_injects_draft_lines_into_active_contract`.
- **Where.** `backend/erev_api/domain/contracts/regroup.py:304-486`: the source status is never tested (`:314-316`), the target may be ACTIVE (`:353`), `REGROUPED` is appended directly (`:437,444`), no `approvals.submit`. Route `api/v1/contracts.py:406-429` (`modification.create`, no `If-Match`).
- **Exploit.** A preparer creates a DRAFT with a 960,000 line and `POST /contracts/{draft}/regroup` with `target_contract_id` an approved ACTIVE contract that has not yet posted a line; the line lands in the ACTIVE contract at once, as APPLIED modifications with `approval_request_id: null`.
- **Evidence (quoted).** target before `transaction_price 120000.00, posted_subledger_lines 0` -> after `1080000.00`; `MODIFICATION approval requests: 0`; `REGROUPED on the ACTIVE target: [{"by": "USER", "approval_request_id": null}]`.
- **Limit.** Only while neither contract has posted a line; after posting the rows are DRAFT modifications needing approval.
- **Fix.** Route any regroup touching a non-DRAFT contract through the MODIFICATION approval; validate the source status. Docs: REQ-CON-012, 04 E-03 `REGROUPED`.

### S7. Manual measure events recognise revenue with no MANUAL_EVENT approval (documented deferral CTR-6)

- **Status.** CONFIRMED. PoC `.run/sec/sec-con/test_manual_event.py`. This is a documented-incomplete build item (CTR-6 unticked in `docs/BUILD_SPEC.md`), reported because the requirement is P0 and the effect is direct posting.
- **Where.** `backend/erev_api/domain/contracts/events.py:23-29,196-213,1068-1132`; `evidence_file_ids` only lands in the audit detail. The MANUAL_EVENT submission machinery already exists for event voids (`:1684`).
- **Exploit.** A preparer posts `DELIVERY_RECORDED`/progress/milestone/cost to `POST /contracts/{id}/events` with no evidence and no approval.
- **Evidence (quoted).** before `revenue_to_date 0.00, posted_lines 2` -> after `revenue_to_date 89174.31, posted_lines 4`; `MANUAL_EVENT approval requests / event submissions: [0, 0]`.
- **Fix.** Build CTR-6; until then refuse revenue-affecting `is_manual` events from USER principals or route them through `event_submission` as the void path does. Docs: REQ-DAT-014 (P0), CTL-009, BR-REC-01.

### S8. Auto-approval and approval-routing rules have no guardrails; an author self-publishes routing

- **Status.** CONFIRMED (the match-all auto-approval rule and the author's own routing publication reproduced). Not verified: a period reopen actually decided under the weakened route; ROLE_ASSIGNMENT/ROLE_CHANGE auto-approval (by code only). PoC `.run/sec/sec-con/test_config_integrity.py` (F9).
- **Where.** `backend/erev_api/domain/policies/rule_sets.py:153-186` (empty `conditions` valid), `:206-248`; `backend/erev_engine/rules.py:154-162` (`all([])` matches everything); `backend/erev_api/approvals/routing.py:154-175` (a matched routing rule REPLACES the subject's permission, approver count and second step; auto-approval needs only `auto_approve: true`); `backend/erev_api/domain/policies/lifecycle.py:271-276,320`.
- **Exploit.** A `config.author` holder publishes (with one Controller approval, once) an AUTO_APPROVAL rule `{conditions: [], outputs: {auto_approve: true}}`. Thereafter every submission that leaves `auto_approval=True` self-approves for every preparer, including the author's own APPROVAL_ROUTING version that sends PERIOD_REOPEN to a single `judgement.review` holder.
- **Evidence (quoted).** `F9 SEC-AUTO-ALL: POST rule: {"http": 201, ... "conditions": [], "outputs": {"auto_approve": true}}`; `F9 SEC-ROUTE-REOPEN right after the AUTHOR's own submit: {"status": "PUBLISHED", "pending_approval_request_id": null ...}`; `F9 published routing for PERIOD_REOPEN: {"matched": true, "outputs": {"steps": [{"permission": "judgement.review", "min_approvers": 1}]}}`.
- **Fix.** Require a `subject.type` condition; allow-list auto-approvable subject types and require a system source channel (REQ-PLT-016); never auto-approve RULE_SET_VERSION of kinds AUTO_APPROVAL / APPROVAL_ROUTING or role/access subjects; forbid a routed step below the subject spec's permission and approver count. Docs: REQ-PLT-016, REQ-CLS-011, CTL-005.

### S9. A preparer releases a SYSTEM recognition hold on an unreviewed judgement

- **Status.** CONFIRMED. PoC `.run/sec/sec-con/test_maker_checker.py::test_f5_preparer_releases_system_judgement_hold`.
- **Where.** `backend/erev_api/domain/contracts/holds.py:307-347` (`release_hold` selects the hold by id and contract and checks only `released_at`; no `hold_source` test), permission `contract.create` (`:84`).
- **Exploit.** A preparer submits a judgement on an ACTIVE contract; the system applies a recognition hold until review; the preparer calls `POST /contracts/{id}/release-hold` with that hold id and recognition resumes though nobody reviewed the judgement.
- **Evidence (quoted).** `F5 HOLD_APPLIED event: {"by": "SYSTEM", ... "hold_source": "SYSTEM"}`; `F5 POST release-hold as the preparer: {"http": 200, "on_hold": false}`; `F5 judgement afterwards (never reviewed): {"status": "SUBMITTED", "reviewer": null}`.
- **Fix.** Refuse a manual release when `hold_source` is not MANUAL (DENIED audit); system holds clear only when their condition clears. Docs: REQ-POL-010.

### S10. SSP book scope is not in the approved content and stays editable while a version is SUBMITTED

- **Status.** CONFIRMED. PoC `.run/sec/sec-con/test_config_integrity.py` (F8).
- **Where.** `backend/erev_api/approvals/subjects.py:2104-2126` (`ssp_book_version_content` hashes the book code, version and entries; entity, currency, segment, channel and resolution mode are absent); `backend/erev_api/domain/ssp/commands.py:345-357,412-423` (scope frozen only once a version is APPROVED/SUPERSEDED).
- **Exploit.** A preparer submits prices scoped to entity AVM-US / segment PILOT-ONLY, then `PATCH /ssp-books/{id}` `{entity_code: null, segment: null}` while the version is SUBMITTED. The content hash is unchanged, the request is not voided, the approver approves, and the prices apply tenant-wide.
- **Evidence (quoted).** scope at submission `entity_code AVM-US ... segment PILOT-ONLY`; after the PATCH `entity_code null ... segment null`; request `content_sha256 04c35eb4...2702` unchanged; `approve -> APPROVED`; `scope in force entity_code null`.
- **Fix.** Hash the scope into the version content (a change then voids the stale approval), or freeze scope while any version is SUBMITTED; recompute the request entity. Docs: REQ-PLT-014, REQ-SSP-007.

### S11. Approvals of contract-bound and run subjects are not entity-scoped (22 subjects)

- **Status.** CONFIRMED for POLICY_OVERRIDE (sec-con) and for JOURNAL_RUN and IMPORT_COMMIT (sec-close); the other 19 share the pattern and were not each reproduced. PoCs `.run/sec/sec-con/test_entity_scope.py`, `.run/sec/sec-close/test_poc_ledger_scope.py`.
- **Where.** `backend/erev_api/approvals/subjects.py` sets `entity_id=lambda ...: None` for 22 subjects (verified count), including MANUAL_EVENT, IMPORT_COMMIT, JUDGEMENT_RECORD, COMBINATION_GROUP, CONTRACT_ACTIVATION, POLICY_OVERRIDE, SSP_OVERRIDE, ESTIMATE_VERSION, JOURNAL_RUN; `backend/erev_api/approvals/engine.py:636-637` (`_covers` passes when `entity_id is None`); `backend/erev_api/domain/platform/approval_queries.py:124-130` (NULL-entity requests visible to every scope).
- **Exploit.** An approver whose `contract.approve`/`journal.approve` is limited to E1, plus any role on E2, approves an E2 request; an approver with no role on E2 still sees it with `can_decide: true` (the write is stopped only by RLS on the underlying row).
- **Evidence (quoted).** sec-con: `F4 approval_request.entity_id ... None`; `POST approve as rita (contract.approve for E_in only + viewer on E_out): HTTP 200 APPROVED`. sec-close: `Rex (journal.approve for E2 only) approves E1's run -> 200; journal run of E1 is now: approved`.
- **Fix.** Resolve `entity_id` from the contract / run / version for every bound subject; the `subjects.py:82-90` docstring that justifies None is stale. Docs: REQ-PLT-012, 04 T-PLT-17.

### S12. SSP calculator run exports contract lines of every entity (confused deputy through the SYSTEM job)

- **Status.** CONFIRMED. PoC `.run/sec/sec-con/test_config_integrity.py` (F10).
- **Where.** `backend/erev_api/domain/ssp/calculator.py:681-743` (`_committed_statement` reads every ACTIVE single-obligation contract of the tenant), `:1006-1051` (`create_run`: no entity or `contract.read` check), `:872-891,1548-1588` (observations served to any `ssp.read` holder); the job runs as `system_principal` scope `*` (`jobs/registry.py:775`).
- **Exploit.** An `ssp_analyst` limited to AVM-DE posts `POST /ssp-calculator-runs` source `committed_obligations` and reads `GET /ssp-calculator-runs/{id}/observations` - contract prices, customers and quantities of every entity; any `ssp.read` holder reads the stored run afterwards.
- **Evidence (quoted).** control `GET /contracts/{AVM-US contract} as erin (scope AVM-DE): {"http": 404}`; run observation of the AVM-US order returned to erin with `customer ... "Marrowby Health Partners LLC (Demo)"`, `unit_price 2400`.
- **Fix.** Restrict the provider to the requester's `contract.read` entity scope (the job carries `on_behalf_of_id`), store that scope on the run and apply it to reads. Docs: REQ-PLT-012.

### S13. Judgement records readable across entity scope

- **Status.** CONFIRMED. PoC `.run/sec/sec-con/test_entity_scope.py::test_entity_restricted_reader_reads_out_of_scope_rows`.
- **Where.** `backend/erev_api/domain/policies/judgements.py:572-590,639-641,189-196` (statement and get-by-id have no contract join; the table is tenant-only under RLS). The IDOR suite does not cover judgements.
- **Exploit.** An E1-restricted reader `GET /judgements/{E2 judgement}` and `GET /judgements?subject_id={E2 contract}` reads the conclusion and rationale of another entity's judgement.
- **Evidence (quoted).** control `GET /contracts/{E_out} as erin: HTTP 404`; `F1 GET /judgements/{E_out judgement} as erin: HTTP 200 {... "conclusion": "SECRET-OUT: collectibility of this customer is doubtful."}`; list `X-Erev-Total-Count: 1`.
- **Fix.** Join to `contract` (entity-scoped under RLS) whenever `contract_id` is set, for list, count and get. Docs: REQ-PLT-012.

### S14. Combination groups readable across entity scope (contract-id oracle)

- **Status.** CONFIRMED (low end - ids, code, currency, inception date). Same PoC as S13.
- **Where.** `backend/erev_api/domain/contracts/combination.py:1037-1054,1057-1097`.
- **Evidence (quoted).** `F2 GET /combination-groups/{E_out group} as erin: HTTP 200 {"code": "CG-9FD00B98", "member_contract_ids": [...]}`.
- **Fix.** Return a group only when the caller can see at least one member contract; list only visible members.

### S15. A posting in flight when the lock approval commits lands in the CLOSED period

- **Status.** CONFIRMED. PoC `.run/sec/sec-close/test_poc_lock_race.py`.
- **Where.** `backend/erev_api/db/migrations/versions/0040_ctr_3_subledger.py:169-205` (DB-07 guard reads `period_state.state` with a plain SELECT in a BEFORE INSERT trigger - no row lock, no commit-time recheck; verified: the guard does `SELECT s.state ... INTO period_state_now` with no `FOR SHARE`); same in `0046_journal_tables.py:398-418`. `backend/erev_api/domain/close/commands.py:1068-1084,1513-1581` compute gates and the ledger head with plain SELECTs.
- **Exploit.** T1 (any posting transaction) inserts lines while the period is `closing`; the guard passes. T2 (the Controller's approval) commits `closing`->`closed`, computing gates, the 12 lock snapshots and the ledger head without T1's lines. T1 commits: the lines sit in the closed period with `is_post_reopen=false`, no reopen, no relock diff. All postings go through `subledger.post`, so the carriers are contract computations, close-run jobs and an approved IMPORT_COMMIT job.
- **Evidence (quoted).** `period state after both commits: closed`; `lines now in the CLOSED period (amount, is_post_reopen, origin_period_id): [('777.0000', False, None), ('-777.0000', False, None)]`; `lock snapshots frozen before the posting became visible: 12`.
- **Fix.** Read `period_state` `FOR SHARE` in both DB-07 guard functions (the lock path already holds the row lock, so posters wait and then see `closed`); optionally gate on in-progress import/posting jobs. Docs: 04 DB-07, REQ-CLS-002/009, CTL-015/017, DG-KRN-DB-08.

### S16. The import pipeline never applies the uploader's or approver's entity scope

- **Status.** CONFIRMED. PoC `.run/sec/sec-close/test_poc_imports_scope.py`.
- **Where.** `backend/erev_api/domain/imports/diff.py:127-129,169-188` (`import_principal` = SYSTEM with `IMPORT_PERMISSIONS` scope `"*"`, used for the dry run and the commit; verified); `backend/erev_api/domain/contracts/commands.py:235-236` (SYSTEM is exempt from `require_for_entity`); `commit.py:170-176` and `upload.py:181` check only the uploader's identity, never the entities the rows name; `subjects.py:2907` + `engine.py:636-637` (IMPORT_COMMIT approval entity None).
- **Exploit.** An E1-only `revenue_accountant` uploads a `contracts` CSV naming an existing E2 contract and `GET /imports/{id}/diff` returns that contract's transaction price and allocations; uploads a new E2 contract, an E1-only reviewer approves, and the commit job creates an E2 contract neither can read. The uploader's direct `POST /contracts` for E2 is refused 422.
- **Evidence (quoted).** `Eve POST /contracts for AVM-US -> 422`; diff returns the AVM-US contract's `transaction_price before 120000.00 after 126000.00`; `Rhea (AVM-UK only) approves IMPORT_COMMIT -> 200`; `committed contract: AVM-US DRAFT`.
- **Fix.** Resolve every entity the rows name and check it against the uploader's scope at diff and submit; give `import_principal` the uploader's scope (drop the SYSTEM exemption for on-behalf-of principals); require `import.approve` to cover every named entity; filter `_before` by the uploader's scope. Docs: REQ-PLT-012, DG-KRN-AUTH-04, 05 IPL-07/10.

### S17. Entity-restricted users read other entities' data on tenant-level read routes

- **Status.** CONFIRMED for imports, postings and audit events; source-records and control-executions by code only. PoC `.run/sec/sec-close/test_poc_ledger_scope.py`, `.run/sec/sec-close/run_imports.log`.
- **Where.** imports `api/v1/imports.py:217-377` (`contract.read`, no scope filter; RLS-T tables); postings `api/v1/subledger.py:101-112` + `domain/journals/subledger.py:757-809`; audit `api/v1/audit.py:100-127` + `domain/platform/audit_log.py:39-42` (tenant-wide for any `audit.read`).
- **Exploit.** An E2-restricted auditor gets an empty `/subledger-lines` for an E1 contract and 404 on E1's run, but reads E1's run totals and every posting id from `/audit-events`, then `GET /subledger-postings/{id}` returns the E1 posting with its seal control totals.
- **Evidence (quoted).** `Ann reads journal_run.calculate of E1: {"run_no": "JR-000001", "total_debit_functional": "295.6900"}`; `Ann GET /subledger-postings/<E1 posting> -> 200 ... [{"entity_id": "<E1>", "debit_txn": "295.6900", ...}]`.
- **Fix.** Store the named entity set on the upload and filter reads; require a visible line for postings and filter totals to visible entities; add entity attribution to audit events or restrict the route to principals whose `audit.read` scope is `*`. Docs: REQ-PLT-012, T-IMP-02/03, T-SL-01/02, T-PLT-19.

### S18. `POST /periods/{id}/open` accepts `period.close` held for any entity

- **Status.** CONFIRMED. PoC `.run/sec/sec-close/test_poc_ledger_scope.py` (part B).
- **Where.** `backend/erev_api/domain/reference/commands.py:1742-1765` (`open_period` calls `authorize` - a holds-any check - not `require_for_entity`; verified: no `require_for_entity` in the function). The other period commands do scope (`domain/close/commands.py:257,365`).
- **Exploit.** A `revenue_accountant` for E2 and viewer for E1 gets 404 on `start-close` of E1 but `POST /periods/<E1 period>/open` -> 200 and the period becomes postable.
- **Evidence (quoted).** `Pat start-close on E1 -> 404 not-found`; `Pat open E1 FY2024-P01 -> 200 open`.
- **Fix.** Call `require_for_entity` for the held permission after loading the row (keep the SYSTEM SCH-05 path). The `_authorize_reference` any-entity shape (`reference/commands.py:1146-1156`) has the same pattern - see S-P3. Docs: API-R-18, DG-KRN-AUTH-04.

### S19. Close and import evidence is not protected from `file.shred`; a shredded lock dataset blocks later locks

- **Status.** CONFIRMED. PoCs `.run/sec/sec-close/test_poc_import_source_shred.py`, `.run/sec/sec-close/test_poc_snapshot_shred.py`.
- **Where.** nothing writes `legal_hold`/`retention_until` (grep); `domain/close/snapshots.py:130-136` stores lock datasets with no retention; `domain/platform/privacy.py:544-587` (`shred_refusal` refuses only on hold/retention/plaintext purpose); `files/policy.py:38-46` (IMPORT_SOURCE and SNAPSHOT_DATASET are encrypted, hence shreddable); route `api/v1/files.py:171-193` (`settings.manage`); `files/store.py:453-460` (`_admit` then refuses identical bytes after a shred).
- **Exploit.** A Tenant Admin with no finance permission reads a COMMITTED import's `file.id` from `GET /imports` and `POST /files/{id}/shred` (200): the source is unreadable and `GET /imports/{id}` becomes 404 for everyone. Shredding a frozen lock dataset then makes every later lock whose dataset of that kind has identical (header-only, empty) bytes fail in `freeze_datasets` with 409, leaving the period `closing`.
- **Evidence (quoted).** `Tess POST /files/<import source>/shred -> 200`; `GET /imports/<id> afterwards -> 404`; `Tess POST /files/<WATERFALL dataset>/shred -> 200`; `lock approval of FY2026-P10 after the shred -> 409 invalid-transition ['FILE_SHREDDED']`; `FY2026-P10 state: closing`. Precondition: no reviewed route returns `lock_snapshot.file_id`; the PoC read it from the database.
- **Fix.** Set retention or a hold when a file becomes lock/import/export evidence, or refuse the shred while a `lock_snapshot`, `period_lock`, COMMITTED `import_upload` or `journal_batch` references it; make `imports_get` tolerate a shredded source. Docs: PRV-07 b, T-PLT-29, T-CLS-05, REQ-CLS-010.

### S20. Sandbox webhook endpoints are created and reactivated over the API and fan out (client-only gate)

- **Status.** CONFIRMED. PoC `.run/sec/sec-fe/test_secfe_poc.py::test_b1_sandbox_webhook_endpoint_is_created_active_and_reactivated`.
- **Where.** the only enforcement is `frontend/src/routes/developer/developer.tsx:1176` (a disabled toggle; the create drawer `:1451` has no gate). Server: `backend/erev_api/api/v1/webhooks.py:136-160,181-207` declare no `sandbox-restricted` and read no `tenant_kind`; `backend/erev_api/domain/platform/webhook_endpoints.py:158` inserts `is_active=True` unconditionally, `:205` applies `is_active` from the PATCH body (verified: no `tenant_kind`/`SANDBOX` reference in either module). No DB-15 trigger on `webhook_endpoint`. Contrast journals `export.py:347,413` and integrations `commands.py:152`, which refuse in a sandbox.
- **Exploit.** An `integration_admin` (`webhook.manage`, no MFA) in a SANDBOX tenant - which per SBX-03 holds a copy of production data - `POST /api/v1/webhook-endpoints {url:"https://attacker/..."}` (or `PATCH is_active:true`) with curl; the endpoint is stored ACTIVE and receives signed deliveries. No DENIED audit.
- **Evidence (quoted).** `B1 sandbox create_endpoint: is_active = True`; `B1 sandbox update_endpoint is_active False->True: False -> True`; `B1 sandbox: active endpoints 1 | deliveries emitted 1 | queued 1 | DENIED audit events 0`.
- **Fix.** Refuse 403 `sandbox-restricted` (audited DENIED) in `create_endpoint`/`update_endpoint` when `tenant_kind` is SANDBOX and the result is `is_active=True`; add a DB-15 trigger. Docs: SBX-08, REQ-PLT-022, CTL-043, ADP-34.

### S21. The MFA-mandatory enrolment gate is client-only and is lifted by a page reload

- **Status.** CONFIRMED. PoC `.run/sec/sec-fe/test_secfe_poc.py::test_b3_get_session_carries_no_enrolment_step_and_the_unenrolled_session_reads`.
- **Where.** `frontend/src/app/auth/MfaGate.tsx:14-20` + `RequireSession.tsx:80` read `mfa_enrolment_required`, which exists only on `SessionLoginOut` (the sign-in answer). `GET /session` returns `SessionOut`, which has no such member (`backend/erev_api/api/v1/session.py:122-135`), so after a reload the flag is undefined and the gate is off. The server gates each call only by the permission's `requires_mfa`.
- **Exploit.** A never-enrolled `revenue_reviewer`/`controller`/`tenant_admin` signs in, reloads, and performs every non-MFA action: contract/ssp/config/audit reads, `report.run`/`export`, `journal.export`, `period.close`, `masterdata.maintain`, `webhook.manage`, files, saved views - contradicting REQ-PLT-005 ("cannot reach any screen other than MFA enrolment until enrolled").
- **Evidence (quoted).** `B3 POST /session/login: mfa_enrolment_required = True`; `B3 GET /session keys: [...]` (no `mfa_enrolment_required`, `mfa_verified_at` null); `B3 un-enrolled reviewer: GET /contracts 200 GET /audit-events 200`; a `requires_mfa` approve correctly 403.
- **Fix.** Enforce mandatory enrolment server-side: carry the requirement on `GET /session` and re-assert it in the guard, or block every non-enrolment route for a user who holds a `requires_mfa` permission with no confirmed factor. Docs: REQ-PLT-005, SAR-26.

### S22. Compose runs the api and worker with `erev_owner` credentials and the master keys

- **Status.** CONFIRMED (config, read by the lead); exploitation PLAUSIBLE (needs a prior in-process compromise; not reproduced).
- **Where.** `deploy/compose.yaml:22-27` (anchor `x-erev-environment` sets `EREV_DB_OWNER_URL` and the three master keys) applied at `:73` (migrate), `:92` (api) and `:114` (worker) - verified. The production api never needs the owner URL (`backend/erev_api/config.py:332-333` requires it only in local envs). Owner-role tamper exemption `backend/erev_api/db/migration_ops.py:193-208`. Hosted is clean: `deploy/terraform/gcp/cloud_run.tf` gives api/worker only runtime secrets and IAM grants the owner URL to the migrate SA alone (`main.tf:403-421`).
- **Exploit.** An attacker with code execution in the api or worker reads `EREV_DB_OWNER_URL` from the environment and connects as `erev_owner`, which owns every table/trigger/policy: disable RLS, drop triggers, and use the DB-01 `erev_owner`+`app.data_fix_ticket` exemption to UPDATE/DELETE append-only `audit_event`/`security_event`/`subledger`. The same env holds the local master keys, so valid HMACs are recomputed and verification still passes - silent tamper.
- **Evidence.** `deploy/compose.yaml` lines 22-27/73/92/114 and `migration_ops.py:193-208` read directly; the role guard (`db/session.py:137-153`) rejects only SUPERUSER/BYPASSRLS, so it admits this owner connection. No runtime exploit run.
- **Fix.** Give the compose api and worker their own environment block with `EREV_DB_APP_URL` only; keep `EREV_DB_OWNER_URL` on the `migrate` service. Docs: DPL-33, TB-7, 04 DB-01. Related P3: `deploy/compose.env.example:21-23` ships placeholder all-zero-ish master keys that pass the 64-hex format check with no strength check.

---

## P3 (hardening and defence in depth)

Each is a real code path; none is a same-tenant authz bypass or worse on its own. CONFIRMED = reproduced by a PoC; PLAUSIBLE = code path only.

- **P3-1 (CONFIRMED).** Entity-scoped SSP books are readable and preparable by an out-of-scope `ssp.create` holder, and an out-of-scope book shows as `entity_code: null`. `domain/ssp/commands.py` has no `require_for_entity`; `domain/ssp/queries.py:104-113` outer-joins. PoC `.run/sec/sec-con/test_entity_scope.py` (F3). Fix: `require_for_entity(ctx, "ssp.create", book.entity_id)`.
- **P3-2 (CONFIRMED).** A GROSS and a DELTA journal run cover the same seals (DB-16 key and coverage include `mode`). `domain/journals/summarise.py:591-607`, `0046_journal_tables.py:262-287`. Each still needs its own approval. PoC `.run/sec/sec-close` (F7).
- **P3-3 (CONFIRMED).** Read-only roles cause audited SYSTEM writes and unbounded verify jobs: the cockpit/checklist GETs run `refresh_checklist` and commit (`api/v1/periods.py:306-351`); `POST /audit-events/verify` needs only `audit.read`, no MFA, no dedupe (`api/v1/audit.py:160-178`, `jobs/registry.py:428-462`). PoC `.run/sec/sec-close/test_poc_readonly_writes.py`. Fix: dedupe/rate-limit verify; write the cockpit refresh only on change.
- **P3-4 (CONFIRMED).** Approver without `audit.read` sees no impact preview, no warning, Approve stays enabled (maker-checker degrades to a rubber stamp). `lib/api/queries/approvals.ts:291-306`, `routes/approvals/request.tsx:497,521-549`; server `domain/platform/attachments.py:345-362`. PoC `.run/sec/sec-fe/test_secfe_poc.py::test_b2`. Fix: grant the approve permission read of that preview, or block the decision when the preview is unreadable. Docs REQ-PLT-015.
- **P3-5 (CONFIRMED).** Client-side spreadsheet formula injection via the DataGrid Mod+C copy: `components/data-grid/DataGrid.tsx:645-671` writes raw tenant text to the clipboard as TSV; the server export neutraliser is not applied. PoC `.run/sec/sec-fe/src/sec_fe.test.tsx` (PoC-FE-3). Fix: apply `safe_text` in `copy()`. Docs REQ-SEC-011/THR-13.
- **P3-6 (CONFIRMED).** Session-cookie `Secure` is chosen from the request Host, not `EREV_PUBLIC_ORIGIN`: `api/deps.py:111-113` (`request.url.hostname != "127.0.0.1"`), deviating from SAR-09 and the doctor check. A `Host: 127.0.0.1` request gets a non-Secure cookie. PoC `.run/sec/sec-deploy/test_cpu_probes.py`. Fix: derive from `settings.public_origin`.
- **P3-7 (CONFIRMED).** No `Strict-Transport-Security` on any active tier (`api/middleware.py:50-62`, `nginx/security-headers.conf`, `load_balancer.tf:185-207`). Fix: emit HSTS at the LB / self-host front end.
- **P3-8 (CONFIRMED).** `GET /metrics` returns 500 (not 401) on a non-ASCII bearer token: `api/metrics.py:156-163` (`secrets.compare_digest` on two `str`). Fix: compare bytes or reject non-ASCII with 401.
- **P3-9 (CONFIRMED).** UPL-07 per-sheet column limit (200) and per-cell length limit (32,767) are not enforced by the import parser (`domain/imports/parse.py`, `validate.py:455-481` applies only the 50,000-row limit, after the whole sheet is in memory). Weak DoS. PoC `.run/sec/sec-input/test_import_limits.py`.
- **P3-10 (CONFIRMED).** Inbound/GL adapters honour an unbounded `Retry-After` and a caller-set attempt budget (`config.max_attempts`, unvalidated), so a hostile tenant-configured source pins a shared worker slot: `adapters/crm/salesforce.py:169-170,382,409-413`, `adapters/billing/stripe.py:589-614`, `adapters/gl/netsuite.py:182-205`; a non-numeric `Retry-After` crashes `float()`. Cross-tenant availability impact on the shared worker pool. PoC `.run/sec/sec-input/test_adapter_retry_bounds.py`. Fix: cap the honoured `Retry-After` at the schedule cap, clamp `config.max_attempts`, reject non-numeric, add a per-job deadline. Docs ADP-12.
- **P3-11 (CONFIRMED).** Combination/SSP/other reads aside, `api/v1/source_records.py` and `/control-executions` are tenant-wide for a `contract.read`/`audit.read` holder (entity not applied); code path from sec-close, not separately reproduced beyond S17.
- **P3-12 (CONFIRMED).** Context-pill selection in `localStorage` is keyed by tenant, not user (`frontend/src/app/shell/ContextPill.tsx:415-443`): a shared browser leaks the previous user's last-viewed entity/period/book codes. Fix: key by user+tenant or clear on sign-out.
- **P3-13 (PLAUSIBLE).** Identity providers are global (`identity_provider` is RLS-NONE-U, no `tenant_id` - confirmed by the schema dump) and `find_provider`/`sign_in_external` (`auth/oidc.py`, `auth/sessions.py:753-862`) apply no tenant or email-domain binding; the first OIDC sign-in auto-links any existing user by verified email. A malicious or compromised provider that any operator adds can sign in a user of any tenant. Only an operator can add providers (`erev idp create`, no API route), and 1.0 ships only a mock; not reproduced (the mock asserts only three fixed emails). Fix: bind a provider to a tenant/domain; make linking explicit. Docs THR-05.
- **P3-14 (PLAUSIBLE).** Uploaded legacy SQLite is fully materialised with `fetchall()` and no row/time/memory bound and no `PRAGMA integrity_check` (UPL-09): `domain/migration/legacy_db.py:193-201,291-333`. Open is sound (`mode=ro&immutable=1`, `trusted_schema=OFF`, `query_only=ON`, no identifier injection). Fix: bound/stream rows, busy timeout, integrity check.
- **P3-15 (PLAUSIBLE).** Production web image may ship JS source maps at a public immutable path (`frontend/vite.config.ts:82` `sourcemap:"hidden"` still emits `.map`; `web.Dockerfile` copies `dist`; nginx serves `/assets/`). Not built. Fix: `sourcemap:false` or strip `*.map`.
- **P3-16 (PLAUSIBLE).** `erev doctor` SAR-40 production checks are advisory, not enforced at startup (`main.py:85-93` vs `cli.py:420-497`); e.g. `EREV_EMAIL_BACKEND=fake` is allowed under production and caught only by doctor. Fix: run doctor as a rollout gate or fail startup on the fail-closed subset.
- **P3-17 (PLAUSIBLE).** Password-reset email persists the cleartext single-use token in the outbox of the user's last-opened tenant (`auth/credentials.py:150-194,280-293`, RLS-T `outbox_message.payload`). No app route returns `outbox_message.payload`, so exploitation needs DB/backup access within 60 minutes. Fix: store a reference and resolve the link at send time.
- **P3-18 (PLAUSIBLE).** Per-tenant fan-out loops have no per-tenant error isolation (`jobs/sweeper.py:201`, `jobs/registry.py:482,505`): one tenant's raising query aborts the sweep for the rest. Fix: wrap each tenant, continue-on-error.
- **P3-19 (PLAUSIBLE).** Jobs are visible to any `audit.read` holder regardless of entity (`domain/platform/jobs.py:53-58`).
- **P3-20 (PLAUSIBLE).** Commands guarded by the RLS union scope, not the permission's own scope: `update_entity`/`put_entity_book` (`domain/reference/commands.py:1451,1626`), ENTITY-scope registry versions, `create_judgement` for non-contract subjects, contract-create performing entity (`domain/contracts/commands.py:228-236`). A caller with viewer on E2 and an authoring role on E1 can act on E2. Same family as S18.
- **P3-21 (PLAUSIBLE).** `CustomerIn.source_system` is client-settable (`schemas/customers.py:73-76`, `reference/commands.py:1028`): provenance spoofing and `(source_system, external_id)` squatting that adapter sync matches on.
- **P3-22 (PLAUSIBLE).** `create_override` stores `judgement_record_id` unvalidated (`domain/policies/overrides.py:202-224`); `MEMO_UPDATED` through `/events` skips the mandatory comment/field audit of `update-memos` (`events.py:209`); activation routing thresholds compared in transaction currency without FX (`domain/contracts/activation.py:633-654`). The override still needs approval.
- **P3-23 (PLAUSIBLE).** `integration_connection.secret_ref` is an unscoped reference into the shared secret store (deny-list only in `adapters/keys/provider.py::GcpKeyProvider.secret`); `base_url` is stored as given and only checked by the SAR-15 guard at fetch time. Known before this pass.
- **P3-24 (PLAUSIBLE).** Group-level reads (`domain/contracts/queries.py:1453,1539,861`) can expose other members' obligations in a cross-entity combined group; `explain/service.py:1030-1034` checks one visible member only.

---

## Reviewed and found sound

- **Outbound SSRF guard** (`adapters/http/guard.py`): https-only, resolves once and connects to the checked global-unicast address with SNI/Host set to the name, no redirects, no env proxies; loopback/http only in dev/test/e2e. The OIDC, webhook and adapter clients all route through it. Residual: no total request deadline / response-size cap (feeds P3-10).
- **SQL construction** (sec-input, lead spot-check): every runtime `text()`/`exec_driver_sql` is a constant with bound parameters; `api/lists.py` sort/filter are allow-listed, values cast from validated literals, LIKE escaped, the cursor is bound to `sha256(sort+filters)`; dynamic identifiers exist only in migration/CLI DDL over constants. No SQL injection found.
- **Export formula injection**: one neutraliser (`domain/reports/outputs/sanitise.py::guard` = `imports/templates.py::safe_text`, triggers `= + - @ \t \r`) is routed through by every server CSV/XLSX writer; XlsxWriter disables formula/url/number coercion; no text value reaches a decimal-kind column. (Client clipboard copy is the exception, P3-5.)
- **Upload policy** (`files/policy.py`, `files/store.py`): magic-byte type sniffing, zip-bomb and local-header/ZIP64 size cross-checks, `..`/absolute-path/nested-archive/`vbaProject.bin`/OLE2/DTD refusal, `check_storage_key` segment allow-list, content-addressed keys, kept-object plaintext verification. Downloads served `attachment` + CSP `sandbox` + nosniff.
- **Idempotency store** (`idempotency/store.py`): keyed on (tenant, principal, key); a differing body is 422; a completed record replays; `abandon`/`complete` bind to the attempt.
- **Password / session / TOTP kernel** (`auth/sessions.py`, `mfa.py`, `totp.py`, `passwords.py`): argon2id, dummy-hash timing equalisation, lockout after five failures, the earlier P1s (MFA brute force, cross-tenant MFA reset, unserialised SoD race, audit head anchoring) are fixed; TOTP `last_used_step` replay block and 6-digit format guard; session tokens 256-bit, stored as SHA-256, rotated on login/MFA/password-change/tenant-select; CSRF synchronizer + Origin check on cookie state-changing requests, bearer exempt.
- **Tenancy kernel** (sec-tenancy inventory): `app.tenant_id` is never taken from request input across ~60 `DbContext`/`Principal` constructions; `platform_session` scopes are the two documented ones; the RLS-bypass `owner_engine` is CLI-only and unreachable from any route; advisory-lock keys are all tenant-scoped; RLS is FORCE on tenant tables with per-schema-verified policies.
- **Sandbox / snapshot copy** (sec-tenancy area 3): source bound by `plan.source_tenant_id == jc.tenant_id` plus the manifest digest chain; `coerce_row` forces the target tenant id (a swapped dataset cannot write cross-tenant); sessions, API clients, tokens, MFA, webhook and integration secrets are classed `_secret` and excluded; invitation tokens nulled; the requester gets only their copied source grants; code collisions -> `SANDBOX_NAME_TAKEN`.
- **Operator support grants** (sec-tenancy area 4): reachable only under an APPROVED in-force grant re-checked each request; a grant for tenant X cannot be used in tenant Y; command writes refused by `refuse_operator_command`. The exception is the file-read over-read, S2.
- **Deploy** (sec-deploy): XFF hop arithmetic is correct for the shipped compose (1) and hosted (2) values; body/upload limits cannot be flipped by path variants; `/metrics` and mock routes are not exposed in a production app; error bodies leak no SQL/stack/params; containers run non-root, read-only, cap-drop-all; Cloud SQL is private-IP + ENCRYPTED_ONLY; buckets enforce uniform + public-access-prevention; IAM is per-secret with the owner URL to the migrate SA only.
- **Frontend** (sec-fe): no `dangerouslySetInnerHTML`/`innerHTML`/`eval`/`srcdoc` sinks; the CSRF token is memory-only; the query cache is cleared on tenant switch and sign-out; `safeNext` blocks open redirects; the approve flow sends the hashes the user saw (REQ-PLT-014 not defeated client-side); CSP is strict in both the app and nginx.
- **Journals export authorization** (sec-close, sec-fe): `GET /journal-batches/{id}/download` (route perm understated as `contract.read`) verifies `journal.export` or `report.export` for the entity before any bytes.

## Not reviewed (or not verified by the lead)

- The engine stages beyond the s02 status machine and the rule matcher; report builders' SQL beyond spot checks; tie-outs, snapshot dataset replay content, dashboard internals, monitor rules.
- Database triggers (DB-03/04/10/18) were not exercised directly except DB-07 (S15).
- The approvals engine internals beyond routing, self-approval and the subjects listed; `compute_job.py`, migration reconciliation, upgrade report.
- Cross-tenant behaviour was reasoned from RLS by reading plus the two-tenant PoCs of S11-S18; no dedicated cross-tenant read was reproduced beyond those.
- Live nginx / Cloud Run / Cloud Armor / IAP runtime; Terraform `plan`/`validate`; `test_terraform_policy.py` claims vs the HCL line by line.
- P3-13, P3-14, P3-15, P3-16, P3-17, P3-18, P3-23 were not reproduced (reasons given inline).
- No performance suite, no e2e run.

## Proof-of-concept index (throwaway; under `.run/sec/`, not committed)

- `main/test_poc_delegation_no_mfa.py` (S3), `main/test_poc_file_read_auditread.py` (S2), `main/verify_f13.log` (lead re-run of S1).
- `sec-con/test_step1_path.py` (S1, S4), `test_maker_checker.py` (S5, S6, S9), `test_manual_event.py` (S7), `test_config_integrity.py` (S8, S10, S12, P3-1), `test_entity_scope.py` (S11, S13, S14).
- `sec-close/test_poc_lock_race.py` (S15), `test_poc_imports_scope.py` (S16), `test_poc_ledger_scope.py` (S17, S18, P3-2), `test_poc_import_source_shred.py` / `test_poc_snapshot_shred.py` (S19), `test_poc_readonly_writes.py` (P3-3).
- `sec-fe/test_secfe_poc.py` + `src/sec_fe.test.tsx` (S20, S21, P3-4, P3-5).
- `sec-deploy/test_cpu_probes.py` (S22 config, P3-6, P3-7, P3-8), `sec-input/test_adapter_retry_bounds.py` (P3-10), `test_import_limits.py` (P3-9).
