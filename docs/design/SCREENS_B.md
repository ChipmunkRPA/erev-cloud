# eRev Cloud: screen specifications, part B (close, journals, schedules, reports, evidence, forecasts, AI, administration, migration, onboarding, authentication)

| Field | Value |
|---|---|
| Owner | Principal product designer (design phase B2, slug `screens-b`); revision 1.2 by owner-editor `fix-screens` (design phase B3); revision 1.3 by the supervisor (D-90a); revision 1.4 by the supervisor (D-90); revision 1.5 by the supervisor (D-91); revision 1.6 by lane F-WEB-R (D-90e L9-PLT-Q-6; PR-8.2); revision 1.7 by lane F-WEB-R (D-90e L9-PLT-Q-5; PR-8.1); revision 1.8 by lane F-LMG (D-98 candidate 48; 04 rev 1.35); revision 1.9 by lane F-ADM (D-98 candidate 24; BUILD_SPEC WEB-13, WEB-14); revision 1.12 by lane ENG-C4 (D-98 candidate 85; ENGINE_SPEC_B S15-R-20a); revision 1.13 by lane F-LMG (slice F-LMG-RPT41); revision 1.10 by lane F-CLO (CLO-7c; D-98 85); revision 1.14 by lane ENG-C8 (COST_ROLLFORWARD producer; D-98 85 / 97); revision 1.17 by lane F-CLO (CLO-8; D-98 candidate 96); revision 1.18 by lane F-RPS (F-RPS-CUTOFF-R1; D-98 candidate 112); revision 1.19 by lane F-RPS (frps3b; Codex 2131); revision 1.20 by lane F-LMG (workstream 2 LM-CL-09 writers; supervisor engineering ruling D-98 candidate 133; docs first; number assigned by the supervisor 03:01); revision 1.23 by lane F-CTR (CTR-17 `modification_register` frozen dataset; D-98 140-A1); revision 1.25 by lane F-RPS-REG (BUILD_SPEC RPS-9, RPS-10 and RPS-11 report builders; REQ-SSP-011 value row id on RPT-21; rows of RPT-24 and RPT-26, exception columns of RPT-25, subject reference and content hash on RPT-26, row key of RPT-44; row key, first versions, preparer and effect of RPT-29; amount and rationale of RPT-30; datasets and rules of RPT-33 to RPT-35 for BUILD_SPEC RPS-12; dataset and rules of RPT-17 and the preparer of RPT-15 for BUILD_SPEC RPS-8; RPT-33 driver attribution under supervisor ruling R-47 (b), AD-44); revision 1.26 by lane FIX-D2 (supervisor ruling R-40 (a): the RPT-01 row key encodes each identifier); revision 1.27 by lane F-CLO-B (BUILD_SPEC CLO-16; supervisor ruling R-54; §0.3 SB-R-06 label of `RECONCILIATION_GENERATE`; §2.1 the grid lists the current reconciliation of each kind; §2.2 reopening a reconciliation takes `recon.signoff`); revision 1.30 by lane WEB-QA (the supervisor's ruling R-59: the SoD exception window of §9.10); revision 1.31 by lane F-RPS-REG (supervisor rulings R-63 (a) and R-63 (c); §5.6.5 the permission of RPT-23 to RPT-27; §5.6.3 recorder and approval of an imported event on RPT-16 and RPT-17); revision 1.34 by lane WEB-QA (supervisor ruling R-67 and decision D-87 L6-5-Q-9: the source-line drill of §3.3 takes no filter); revision 1.35 by lane F-CLO-B (BUILD_SPEC CLO-19; supervisor ruling R-79: §1.2 reads of API-S-CloseRun, the 200 answer of an active run, the execution order of rows 5 and 6); revision 1.36 by lane F-ADM-WEB (BUILD_SPEC RPS-21: §6.3 and §6.4 as bound to API-R-10 of 1.0; the supervisor's rulings on the lane's read-in of 2026-09-30; item AUD-API-GAPS-1); revision 1.37 by lane API-GAPS (item API-ACTOR-MEMBERS-1; 04 rev 1.139: the "On behalf of" column of §6.3 binds the API-S-Actor `on_behalf_of`); revision 1.47 by lane F-CLO-B (BUILD_SPEC CLO-20: §1.2 the counts behind each step summary, "No trial balance attached", what a failed invariant shows); revision 1.39 by lane WEB-QA (item W-19, crawl finding F1: the Contract and Batch filters of §3.3 are a combobox and a list of the run's batches, and send ids); revision 1.40 by lane F-RPS-REG (RPT-ROLLFWD-KINDS-1, supervisor ruling R-72: §5.6.1 RPT-03 the line of each kind and the billing that posts no line; RPT-04 the revenue family); revision 1.46 by lane F-RPS-REG (item RPT-OOP-ROWKEY-1, supervisor ruling R-112 (j): §5.6.3 RPT-16 the row key carries the origin and the posting period beside the event key); revision 1.45 by lane F-ADM-WEB (item AUD-ACTOR-BIND-1, supervisor ruling R-112 (h): §6.3 the Actor and On behalf of columns as bound to API-S-Actor; §6.3 and §6.4 the `event` link by chain sequence, the supervisor's ruling of 2026-09-30 19:31); revision 1.38 by lane FIX-D2 (supervisor rulings R-101 (a) and R-106 (a): §0.3 SB-R-06 the label of `PERIOD_OPEN_REDIRTY`; §1.1 the second failing detail of `NO_DIRTY_GROUPS` and what BLK-08 counts); revision 1.53 by lane F-ADM-WEB (BUILD_SPEC RPS-18: §5.3 SF-08:runs and SF-08:run as bound to API-R-41 of 1.0; §6.3 the Object cell of a report run); revision 1.32 by lane F-CLO-WEB (BUILD_SPEC CLO-25; §2.1 and §2.2 as built: the menu lists the kinds the API generates, the earlier generations under the grid, the superseded, reopened and period states of the detail, the key-figure rule, the default columns, the refusals and their copy, test hooks, and the attach section on the members of BUILD_SPEC CLO-17; and item 1b under supervisor ruling R-83: §1.1 the pending permanent-lock banner, the disabled "Permanently lock" item, the pending reopen banner without its reason clause, the withdrawal, the step-up of "Lock period", the permissions of the reopen drawer's two optional parts); revision 1.51 by lane F-RPS-REG (item RPT-FORMER-GROUP-VERSIONS-1: §5.6.1 RPT-02, RPT-05, RPT-06 and RPT-07 and §5.6.2 RPT-11 read a contract from the versions of the group it is a member of — a combined contract is stated once); revision 1.57 by lane F-ADM-WEB (item AUD-SCREEN-BIND-1: §6.3 and §6.4 as bound to the audit reads of 04 rev 1.154 — the outcome filter, the trail of a contract, an event read by its sequence, the object's label, the actor's drill and the names of the actor filter, a verification read by its id); revision 1.42 by lane F-CLO-WEB (BUILD_SPEC CLO-24: §1.2, §1.4 and §1.5 as built on the routes of 1.0 — the quarantine read, the lasting journal run link, the locks grid's shown columns and drawer, the activity copy, the interim per-entity start until CLO-21 — with §1.1 "Run close", "Close several entities", the drawer "Record estimate-versus-error judgement" of item CLO-JDG-ESTERR-UI-1 and the line of a period of the LEGACY book (API-S-Period `follows`; supervisor rulings R-112 (e), R-113 (h) and R-114 (d)), and §2.2 the permission of "Upload CSV"); revision 1.59 by lane F-ADM-WEB (the API-client screen states, part 1; supervisor ruling R-113 (e): §0.4 E-103 and §9.15 — an API client that awaits approval or was refused it; §5.3 who sees the progress of a computing run); revision 1.62 by lane F-ADM-WEB (the supervisor's ruling of 2026-10-01: §9.15 — the entity choice of "New API client" until the API admits one, and a server error at the field it names); revision 1.61 by lane F-CLO-WEB (item REOPEN-CLOSING-FLAG-1, the screens' half: §1.1 — the banner of a soft close under the period's `REOPEN` record and the information line of "Request reopen"); revision 1.65 by lane F-CLO-WEB (item JRN-DRILL-CONTRACT-NAME-1, the screen's half: §3.3 — the Contract of a source line is the drill's own `contract_external_id`); revision 1.50 by lane F-CLO-B (item CLO-GATE-RUN-1, supervisor rulings R-114 (b) and R-116 (e): §1.1 the gate `CLOSE_RUN_COMPLETED` with its three failure details, never waivable; the wireframes count fourteen gates); revision 1.60 by lane WEB-QA (item W-12, slice a; 04 rev 1.148 T-PLT-10: §9.10 the scope a grantor may give and the commands on what is granted; §9.11 a role's definition needs `role.manage` for all entities); revision 1.54 by lane F-SNP (BUILD_SPEC SNP-5 and SNP-4: §9.7 the bindings of SF-15:sandbox as built — the session and `GET /me` in place of `GET /tenant`, "Created by" from the snapshot's Actor, the failed copy with PRD ERR-77, the origin line of an empty sandbox; §9.7 the open workspace is named by the session, so the switcher moves between a workspace and its copies and lists no archived sandbox; §9.8 the email switches and the footnote of SF-15:notifications in a sandbox; §9.15 the create control of a webhook endpoint in a sandbox); revision 1.55 by lane QA-BE (item RPT-ASOF-FIGURES-1; supervisor ruling R-116 (c), pending the accountant — candidate AD-63: §5.6.1 RPT-01, RPT-06 and RPT-07 and §5.6.2 RPT-11 state an obligation at the report's date — recognised up to the as-of period, scheduled after it, the awaiting-trigger amount and the remainder of that date, one date in every figure of RPT-11); revision 1.41 by lane SECFIX-IMP (the supervisor's rulings R-49 (a) and R-86: §9.6 names the screen item of `POST /files/{id}/request-shred`); revision 1.58 by lane F-RPS-REG (item RPT-FORMER-GROUP-READERS-1: §5.6.2 RPT-09, RPT-10 and RPT-11 number a contract's versions along its chain of combination groups; §5.6.1 RPT-02 reads a contract whose group awaits its computation from the version it was last computed in); revision 1.68 by lane WEB-QA (item W-12, slice b; supervisor ruling R-28; SCREENS.md rev 1.34: §3.2 a journal run's "History" and the name and reason of its Cancelled banner need `audit.read` for all entities; §6.3 the audit log is read with `audit.read` for all entities and its access-limited state says so; §6.4 a refused read of a verification); revision 1.74 by lane F-ADM-WEB (the supervisor's message of 2026-10-01 08:07, register index 129: §0.3 SB-R-08 names the connection test among the commands a sandbox holds back, with a reason line of its own; SCREENS §14.4 rev 1.35); revision 1.64 by lane API-GAPS (item PERF-PERIODS-LIST-1; supervisor ruling of 2026-10-01 on the lane's pre-build line; 04 rev 1.199: §5.5 — the close dashboard takes the blocker counts from the cockpit read it makes for every row; a row of `GET /periods` carries none); revision 1.73 by lane SECFIX-PLT (supervisor ruling R-111 (4): §5.6.5 RPT-25 — the column "Through delegations" names the delegations a conflict is held through); revision 1.75 by lane F-RPS-REG (item RPT-43-PARAMS-1; supervisor ruling R-119 (h): §5.6.5 RPT-43 takes `contract_id` and `outcome`, so that an export under the filters of the audit log states the rows of the list); revision 1.66 by lane F-CLO-B (item CLO-QUARANTINE-READ-1: §1.1 BLK-02's link and §1.2 the quarantined contracts are read as the list of what the close gates count, `GET /exceptions?blocking=<period id>`; the grid's "Contract" shows the group's code for the item of a group of several contracts); revision 1.67 by lane F-CLO-B (item CLO-LOCKS-READ-1: §1.4 — a record of the locks list states its certification, its datasets, its ledger head hash and its request's number, and a transition its request's number; the reads ask `config.read`); revision 1.71 by lane F-CLO-WEB (item JRN-FAILED-EXITS-UI-1, the screens of lane F-CLO-A's failed-run exits: §3.2 — the cancel of a Failed run through its job and the refused download; §3.4 — "Hand over" and "Record ERP reference" on a batch handed over); revision 1.80 by lane F-ADM-WEB (item SBX-ADD-CONNECTION-1, the supervisor's message of 2026-10-01 09:41; register index 153: §0.3 SB-R-08 names the drawer "Add connection" among what a sandbox holds back; SCREENS §14.4 rev 1.43); revision 1.70 by lane FIX-D2 (item RPT-RPO-ROLLFWD-1; supervisor ruling R-121 (g): §5.6.1 RPT-06 and RPT-07 and §5.6.2 RPT-11 — a contract is in the reports from the day it was activated; RPT-07 gains the row and the column "Late events"); revision 1.76 by lane F-RPS-REG (item SCOPE-WORKSPACE-LISTS-1; supervisor rulings R-28 and R-121 (c): §5.6.5 RPT-23 and RPT-26 state a request when the run's entities cover every entity it names, and a run names only entities inside both of its permissions; RPT-44 is run with `audit.read` at any scope); revision 1.69 by lane FIX-D2 (supervisor rulings R-78 (d) and R-121 (g): §5.6.1 RPT-01 — an obligation is stated under its performing entity); revision 1.77 by lane F-CLO-WEB (item JRN-RETRY-FOLLOW-1: §3.2 and §3.4 — the retry of a failed batch is followed to its ending, a job without a mode the frame did not send is followed too, "exported" is said only of a run that is, the endings a toast cut, and the export dialog's one target); revision 1.72 by lane F-SNP (items REG-VERSION-WHOLE-SET-1 and CFG-PLATFORM-PIN-1, the supervisor's ruling of 2026-10-01; 04 rev 1.183: §9.6, a value submitted on the workspace settings screen takes effect when its version is approved); revision 1.81 by lane F-CLO-WEB (register indexes 157 and 158: §1.2 — a refused "Resume close run" says why and the runs are read again; §1.4 — the close history as built on the reads of rev 1.67, with the request numbers for every reader, the ledger head's hash and the tables "Certification" and "Frozen datasets"; §3.3 — the source-lines drawer opens on the contract, the side and the amount); revision 1.85 by lane F-CLO-WEB (item JRN-RUN-ENDINGS-2: §3.2 — the failed banner leads to the batches, a failed export job says what it did not do, History words the run's actions; §2.2 — a forbidden signature is said on the record); revision 1.79 by lane WEB-QA (item W-12, slice c, register index 131: §3.1 — the "Run journals" form offers the entities `journal.run` is held for, preselects the context entity only when it is one of them and reads the periods with `config.read` for the first chosen entity; what the form shows and does when no entity is chosen or no period is listed; SB-R-01 — the ranges of the URL parameters and the common states reach SCR-URL-33 and SCR-ST-13); revision 1.82 by lane F-CLO-WEB (BUILD_SPEC RPS-19, first head, register index 159: §5.5 — the revenue dashboard as built: the page's rule for a context without an entity, the view "Functional", the panels' parameters, states, drills and permissions; §5.1 — the "Dashboards" list as built; §13 — the gallery's Data section lists DS-CH-06; §15 — the row of SF-08:dashboard); revision 1.90 by lane F-RPS-REG (item S-1 of the lane's sweep under RPT-FORMER-GROUP-READERS-1; register index 218: §5.6.4 RPT-21 — the row key names the version a row is read from by its number along the contract's chain, as RPT-09 does); revision 1.94 by lane F-SNP (item POLICY-WITHDRAW-ROUTES-1, the supervisor's ruling of 2026-10-02 on the independent review of the head; register index 207: §9.6 — the form names an open version of a category it authors, with the link to its page, and does not submit that category); revision 1.86 by lane F-CLO-B (BUILD_SPEC CLO-17, the role basis; supervisor rulings R-69 and R-74 and the supervisor's ruling of 2026-10-01 21:23; 04 rev 1.253: §2.2 — a row of a contract balance role, a row the subledger does not state with its reason and contracts, the kind `NOT_STATED`); revision 1.97 by lane F-CLO-B (item REC-GEN-LOCK-1's head, register index 211; the supervisor's words of 2026-10-02 02:51 and 06:32 on lane F-CLO-WEB's observation O1; 04 §16.8 rev 1.259: §1.2 — the sentence of a refused "Resume close run" for a superseded run ends "Run close again."); revision 1.92 by lane F-CLO-WEB (item RPT-VIEW-CONTEXT-DEFAULT-1 with REPORT-RERUN-AFTER-REFUSAL-1, register index 229: §0.5 — "The context of a view": the report screens take the context pill's entity, book and period where their address leaves them out, and say all entities with `entities=all`; RV-01 — "Run report" asks again after a refused creation; §4.1, §5.2, §5.3, §5.5 — the routes, bindings, states and links that follow; §14.3 — the screen parameter `entities`; §15 — the rows of SF-04, SF-08:report and SF-08:dashboard); revision 1.93 by lane F-CLO-WEB (item O2 with the reopen request's reason, register index 236: §1.1 — the pending reopen request names its reason; a refused "Run close" keeps the API's sentence and the period is read again; §1.2 — the same for the tab's "Run close", and a refused "Cancel close run" closes its dialog); revision 1.100 by lane F-CLO-B (item CLO-RATE-AFTER-RUN-1, register index 272; the supervisor's ruling of 2026-10-02 08:56 on the lane's pre-build line; 04 §16.8 rev 1.291: §1.1 gate label table — the sentence of a close run whose rates or policies changed since it ran); revision 1.95 by lane F-RPS-REG (head R28-READS; register index 232: §5.6.2 RPT-28 — the proposal of a combination is stated by a run whose entities hold every contract it names, and a run that holds some of them counts it: `record_count` and the head line); revision 1.103 by lane F-SNP (item ACCESS-LISTING-SECOND-LIFE-1, register index 289; 04 T-PLT-07 rev 1.307: §5.6.5 RPT-24 — a membership is removed at `as_of` by its row or, for a removal that a later invitation ended, by the audit trail; the Membership chip and the person's cells stay the values at the run's cutoff); revision 1.98 by lane F-CLO-WEB (item RV-AS-LOCKED-DEFAULT-1, register index 264: §0.5 RV-04 — the as-locked default is a frozen report's, an as-locked run asks the lock's own selectors alone, the toolbar is unavailable, frozen rows draw no chart and the banner speaks of the context period's own lock; RV-08, §4.1 and §15 with it); revision 1.99 by lane WEB-QA (item W-12e: §9.1, §9.3, §9.4, §9.6, §9.7, §9.13, §9.14, §9.15, §10.3 and §11.1 — the pages and commands of the whole workspace ask their permission for all entities; what a holder for named entities reads on each, the permission named by its phrase and its code; the links of the index and the reviewers of a new campaign; §6.3 — the audit log's sentence names `audit.read`); revision 1.101 by lane F-CLO-WEB (the web half of register index 280: §0.5 RV-04 — the lock of the view is the lock whose datasets stand, API-S-Period `dataset_lock`, so a frozen report of a permanently locked period opens as locked on the lock of its close with that lock's time; RV-03 and §5.3 — a refused rerun says every sentence of its problem; §15 — the closed world's row of it); revision 1.104 by lane FIX-D2 (item RPT-ROLLFWD-LOCKED-CLOSING-1; the supervisor's rulings of 2026-10-02 on lane WEB-QA's measurement and on this lane's two lines; register index 297: §5.6.1 RPT-02, RPT-03 and RPT-04 — a period end locked at the run's cutoff is the lock's, in a current run too; a billing document recorded after a lock is billing of the period it entered in); revision 1.102 by lane SECFIX-APR (item POLICY-TENANT-SCOPE-ALL-ENTITIES-1, register index 291; the supervisor's ruling of 2026-10-02 on lane F-SNP's measurement; 04 §16.5 rev 1.309: §9.6 SF-15 — the form's controls are for a holder of `config.author` for all entities); revision 1.105 by lane F-SNP (item IDENTITY-WITHHELD-BY-STATUS-1, register index 302; 04 T-PLT-02 rev 1.316: §9.10 SF-14 — "Not shown" in the grid's "MFA" and "Last login" and on the user page for an invited or a removed member; §5.6.5 RPT-24 — the two cells of such a row, and the exception of the cutoff refusal for a person whose name is withheld; §9.13 — what the null of an access review item's last login means); revision 1.106 by lane SECFIX-PLT (item FX-REPUBLISH-DIRTY-1, register index 277; ENGINE_SPEC_B S15-R-18b rev 1.166, 04 rev 1.297: §5.6.3 RPT-16 — the proof of a Trigger row has a third condition under `FX_REPUBLISH`, a nil transaction amount) |
| Date | 2026-10-03 (revision 1.106; revision 1.25 amended in place for RPS-10, RPS-11, RPS-12 and RPS-8 RPT-15 and RPT-17) |
| Status | Binding build contract. Read-only for the build loop (`docs/01-DECISIONS.md` §0). |
| Precedence | One rank with `docs/design/SCREENS.md` (D-74), below `docs/design/DESIGN_SYSTEM.md` for every visual, token, formatting and component rule. Enumeration literals, permission codes, problem slugs and finding codes are `docs/04-DATA_MODEL.md` verbatim (D-73). Registry keys and option literals are `docs/accounting/POLICIES.md` §1 (D-13a). Product behaviour and copy that `docs/02-PRD.md` fixes are cited, not changed. SCREENS.md owns the route path of every SF id (D-73); routes this file needs that SCREENS.md §0.4 does not list are in §14 "Routes to add". |
| Companion | `docs/design/SCREENS.md`: index of both files, §0 conventions (identifiers, information architecture, route table, URL parameters, permission gating, test hooks, common states, status chips, legacy hooks, wireframe notation, screen codes) and the core workbench. |
| Applies decisions | D-02, D-11a, D-12, D-13a, D-14a, D-19, D-20, D-30a, D-31, D-33, D-44, D-46, D-60, D-61, D-62, D-72, D-73, D-74, D-75, D-76, D-77 |
| Closes gaps | M-DES-06 (report specifications, §5.6). Contributes to M-DES-01 (part B screens), M-DES-05 (close, reopen and sign-off UX) and M-DES-07 (onboarding, legacy transition, empty states) |
| Inputs | `docs/00-GOAL.md`; `docs/01-DECISIONS.md` incl. §7; `docs/02-PRD.md` rev 1.1 §0 to §7; `docs/03-REQUIREMENTS.md` (PLT, REF, SSP, MOD, BIL, CST, LOS, BK, FX, ENT, CLS, JE, RPT, INT, FC, AI, MIG, UX, DEMO); `docs/04-DATA_MODEL.md` rev 1.1 §0.5, §3, T-PLT, T-REF, T-CON, T-ENG, T-SL, T-CLS, T-RPT, T-INT, T-FC, T-AI, T-MIG, §15, §16, §17; `docs/05-ARCHITECTURE.md` §5.2 to §5.10, §6.7 to §6.12, §7.8, §10; `docs/dev-guide.md` §0.6, §8, §9.6, §9.8; `docs/accounting/POLICIES.md` §1.1, §1.8 to §1.13; `docs/design/DESIGN_SYSTEM.md` rev 1.1; `docs/design/SCREENS.md` §0 as published 2026-09-12; `docs/reviews/B1-consistency.md`; research 07 §5 (A-01 to A-20); RightRev reference images 01, 03, 13, 22, 23, 25 (calibration only; nothing copied, `docs/00-GOAL.md` §5); revision 1.2: `docs/01-DECISIONS.md` §8 (D-76, D-77), `docs/04-DATA_MODEL.md` rev 1.2 (§15.3, §16.7, §16.8, §16.12, §16.14, tables 3.4-R, 10-T and 1.2-D), `docs/reviews/B3-fix-fix-data-model.md`, `docs/design/DESIGN_SYSTEM.md` rev 1.2, `docs/design/SCREENS.md` rev 1.2 (§0.4, §0.5, §2.4) |

Legend for claims: **[F]** fact with a cited source; **[J]** judgement by this author with a one-line rationale.

## Revision log

| Rev | Date | Editor | Change |
|---|---|---|---|
| 1.0 | 2026-09-12 | `screens-b` | First binding issue |
| 1.2 | 2026-09-12 | `fix-screens` (design phase B3) | D-76 and D-77 applied: tables 1.2-A and 1.2-S below. No revision 1.1 was issued; the number matches the B3 revision of the other design documents |
| 1.3 | 2026-09-17 | supervisor (D-90a) | **Applied.** §1.1 SF-05 BLK-06 and BLK-15 subtract API-S-PeriodCockpit `pending_requests[]` (04 rev 1.8) instead of request counts read through `GET /approvals`, so BLK-06 and BLK-15 no longer depend on the reader's request visibility; BLK-03 still reads the permission-filtered exception count (QA-L9-7; L8-C-Q-2) |
| 1.4 | 2026-09-18 | supervisor (D-90) | **Applied.** §0.5 RV-04: while `snapshot` is present the parameters toolbar stays editable, "Run report" posts `period_lock_id` = the snapshot and "Run details" keeps "Rerun from the same source"; running, exporting and rerunning are not SCR-ST-10 command controls (D-88 L7-3-Q-2; the BUILD_SPEC RPS-6 clause D-90 amended) |
| 1.5 | 2026-09-18 | supervisor (D-91) | **Applied.** §0.5 RV-14: the SCR-ST-12 "Reference <job id prefix>" is bound to the (run, job) pair the mounted view created and shown only while that run is displayed; a stored run rendered from `run=` and an SF-04 created run show no reference in the rc (accepted deviation; API-S-ReportRun `job_id` post-rc). Copy and state rule only; no route, parameter or binding change (plt-job-reference; amends D-90 L8-R-Q-4 as built; merged ad06f60). The header rows are updated to revision 1.5, superseding the missed 1.4 header change |
| 1.6 | 2026-09-19 | lane F-WEB-R (D-90e L9-PLT-Q-6; PR-8.2) | **Applied.** §0.5 RV-01: the problem of a refused creation (`POST /report-runs` answered with a problem, so no run exists) is bound to the parameter set and source it was attempted for and shows only while the view stays on that pair and displays no `run`; a stored run rendered from `run=`, including one opened by a later `run` navigation in the same mounted view, never shows it; a context change or "Run report" clears it. State rule only; no route, parameter or API change (`useReportRun`; SF-08:report, SF-04, SF-06:entries) |
| 1.7 | 2026-09-19 | lane F-WEB-R (D-90e L9-PLT-Q-5; PR-8.1) | **Applied.** §0.5 RV-14: the "Reference <job id prefix>" line names the displayed run's own job (API-S-ReportRun `job_id`, 04 rev 1.17; T-RPT-02) on every report surface — SF-08:report, SF-06:entries and SF-04 — for created runs, runs rendered from `run=` and runs opened by a later `run` navigation; a run record without `job_id` keeps the rev 1.5 created-pair rule; every creation answer is bound to the attempt that produced it and a late answer after a later attempt, a context change or "Run report" is discarded. Closes the rev 1.5 rc deviation (no reference for stored runs and for a failed run created on SF-04; D-91 SF-04 addition) |
| 1.8 | 2026-09-20 | lane F-LMG (D-98 candidate 48; 04 rev 1.35) | **Applied.** §5.6.7 RPT-41 "Measure" gains "Original allocation" (`ORIGINAL_ALLOCATION`), the obligation's creation-time allocation, listed between "Transaction price" and "Allocation"; the DEV-052 line of Contract 3 POB #5 (PRD J-21.3) renders under it. Label only; no binding, state or copy change elsewhere. |
| 1.9 | 2026-09-19 | lane F-ADM (D-98 candidate 24; BUILD_SPEC WEB-13, WEB-14; numbered 1.9 at the merge preparation of 2026-09-20, 1.8 being F-LMG's) | **Applied.** §12.3: the invitation lookup answers `has_password` (04 §16.12 rev 1.38) and the state "Existing user with a password" renders from it; the profile's "Change password" action of the §9.9 wireframe opens SF-22:password-change (RT-04), closing L3-3-Q-12 and L3-3-Q-13, without the "Last changed <date>" text until API-S-Me carries `password_changed_at`; a successful password change shows its toast and then opens the landing route `/`; "Forgot password?" of the §12.1 wireframe opens SF-22:password-reset. Copy unchanged Sections: §12.3; §9.9 (note) |
| 1.12 | 2026-09-20 | lane ENG-C4 (D-98 candidate 85; ENGINE_SPEC_B S15-R-20a on sprint/l18 aa90492b, not yet on main) | **Applied (renumbered 1.12 at the merge of main a7347356).** §5.6.1 RPT-05 `revenue_from_prior_period_obligations`: the dataset identity is the §15.2.7 row key (entity, contract, obligation) as the code columns `entity_code`, `contract_external_id`, `obligation_key` with exactly one row per obligation; `cause` becomes an attribute (the causes present, joined) and the finer cause grain is kept as attribute money columns (`from_price_changes`, `from_estimate_changes`, `from_modifications`, `from_late_events`, `from_other`); `row_key` `obligation:<entity code>:<external id>:<key>`; rows sorted by the key; control totals `row_count` and `revenue_total` per currency. Source: the stage 08 nodes `revenue_prior_period:<obligation>:<period>` of the traces the range's `REVENUE` subledger lines reference (ENGINE_SPEC_B S15-R-14), causes from the events those nodes cite. Code columns export-visible; the screen keeps the labels. |
| 1.13 | 2026-09-20 | lane F-LMG (slice F-LMG-RPT41, docs first; number assigned at merge prep 2026-09-20, drafted as 1.9) | **Applied.** §5.6.7 RPT-41 gains the "Reader and registration" statement: the builder registered under `migration_reconciliation`, the T-MIG-01 / T-MIG-03 / `exception_item` reads, the refusal copy for an absent migration, the KPI strip bound to control totals — which gain `contracts` and `legacy_obligation_rows` from the T-MIG-01 `profile` — and the no-entity-filter statement; and the "Value representation" statement (D-98 89): comparison rows carry exact, trace-sourced eRev values (DG-PAR-05 `exact(m)`, per measure) and the legacy stored text at full precision, never posted cents; the Measure cell says which representation each label carries. Codex RPT41-ID-1 / IPE-1: `row_key` components percent-encoded (`%25`, `%3A`) with an empty contract-level component, and the IPE statement (tenant-wide batch population, no entity filter). No binding, state or copy change elsewhere. |
| 1.10 | 2026-09-20 | lane F-CLO (CLO-7c; supervisor ruling D-98 85) | **Applied.** §5.6 dataset identity columns: every report whose run is frozen as a lock snapshot (E-64) carries its row key as stable code fields beside its display labels — RPT `contract_balance_rollforward` and `rpo_rollforward` `line_code`; RPT `contract_cost_rollforward`'s `cost_kind` / `line_code` arrive with ENG-C8's long dataset shape (D-98 candidate 97; its RPT-32 grid is unchanged here); RPT `disaggregation` `dimension_code`, `dimension_value`, `timing_code`; RPT `out_of_period_register` `event_key` = `event:<external id>:<stream version>`. Export-only by default (CSV / JSON / XLSX); the screens keep showing the labels. No screen, control or copy change otherwise. |
| 1.11 | 2026-09-20 | lane ENG-C6 (D-98 candidate 85 — canonical export producers; docs first; 1.11 assigned by the supervisor's merge prep, authored as provisional 1.8) | **Applied.** §5.6.3 RPT-15 `je_population` and RPT-16 `out_of_period_register`: the frozen-dataset paragraphs state the CSV column shape — key code columns first (`entity_code`, `book`, `je_no`, `line_no`; `origin_period_key`, `posting_period_key`, `event_key` = `event:<external id>:<stream version>` carried from the source event), then code and measure fields, display labels as attributes last — and the control totals; ENGINE_SPEC_B S15-R-18a (rev 1.24) is the rule |
| 1.14 | 2026-09-20 | lane ENG-C8 (COST_ROLLFORWARD producer; supervisor rulings D-98 85 / 97; docs first; number assigned at merge prep) | **Applied.** §5.6.1 RPT-32 `contract_cost_rollforward`: section 1 is the governed dataset — one row per (`cost_kind`, `line_code`) and entity with the S15-R-17 line codes `OPENING`, `ADDITIONS`, `CLAWBACKS`, `AMORTIZATION`, `ACCELERATION`, `IMPAIRMENT`, `IMPAIRMENT_REVERSAL`, `CLOSING`, one signed money field `amount`, labels as attributes (`category_label`, `line_label`), the codes and `entity_code` as export / API fields, functional currency by default; control totals `opening` / `closing` per currency; tie-out `TO_COST_ROLLFORWARD_BALANCES` restated on the identity. Section 2 "By cost asset" deferred (not part of the frozen dataset). ENGINE_SPEC_B S15-R-20b (rev 1.27) |
| 1.15 | 2026-09-20 | lane ENG-C6 (D-98 candidates 95, 96 and 102 — Codex C6-RPT-R3 and C6-RPT-R4, then the supervisor's rulings on Q-C6-RPT-1 to 5; docs first; 1.15 assigned by the supervisor's merge prep, authored as provisional 1.12; D-98 candidates 104 (Codex C6-RPT-R5), 102a (Codex packet 1130), 102b (Q-C6-RPT-6: group lineage) and 102c (Codex packet 1210: scope in the row identity; audit-chain ordering) folded in) | **Applied.** §5.6.3 RPT-16: rows are one per attribution (ENGINE_SPEC_B S15-R-18a rev 1.29, S15-R-18b) — a cumulative delta of several first-included events is one row whose `event_key` joins the keys with `\|` in ENG-06 order; a trigger-only delta is a "Trigger" row keyed `trigger:<trigger code>:<computation id>` (new column "Attribution", `attribution_kind`; D-98 102 Q1); a line with neither refuses the run by name (`OUT_OF_PERIOD_ATTRIBUTION_MISSING`) and never disappears; control total `line_count`. RPT-15 and RPT-16 "Source": run state, approval, acknowledgement and cancellation are reconstructed as of the run's `known_at` — a `failed` transition takes the time of its audit event, neither is refused by name (`JOURNAL_RUN_STATE_UNKNOWN_AS_OF`; Q3); a lock source is served from the lock dataset by the framework (CLO-8, rev 1.17) and refused by name at the builder as a guard; under the close freeze RPT-15 is read as of the freeze instant (Q5; the `close_run_id` parameter of the provisional text is withdrawn). RPT-16 `row_key` / `event_key`: components CV-21 percent-encoded before joining (`\|` → `%7C`), the joined key injective (D-98 candidate 104; Codex C6-RPT-R5). D-98 102a (Codex 1130): a Trigger row needs persisted proof (empty stored lineage and a non-event trigger), else the line refuses; RPT-15 Source reconstructs the state from the run's full audit transition history across retry cycles. D-98 102b (Q-C6-RPT-6): RPT-16 gains the "Lineage" column `lineage_scope` — a line whose subject had no first-included event carries the group's set as "Group", never a refusal. D-98 102c (Codex 1210): the scope is part of the RPT-16 row identity (`row_key` ends `:SUBJECT` / `:GROUP`), and the RPT-15 Source history is ordered by the audit chain. The event-only UI `row_key` of a multi-origin void (two origin rows, one `row_key`) is recorded as a consumer-alignment item, not changed. |
| 1.16 | 2026-09-20 | lane ENG-C4 (PRIOR_PERIOD_POB_REVENUE builder slice; D-98 candidates 85, 96, 104; number assigned by the supervisor) | **Applied.** §5.6.1 RPT-05 reading rule: traces named by the range's `REVENUE` subledger lines recorded by `known_at`, one (the latest recorded) version per combination group and period, every `revenue_prior_period` node of that trace read; the identity `PRIOR_PERIOD_ROWS_EQ_SUM_NODES` (per contract and period key, Σ of the contract's complete obligation population = the `revenue_prior_period_sum` node under the CONTRACTING entity, input set checked; S15-R-13; C4-PP-R1 amended in place before landing) as the control total `prior_period_sum_total` with refusal by name, rows restricted to the entity scope only after the identity holds; all-zero rows omitted; `cause` lists the non-zero causes; `row_key` components CV-21 encoded (D-98 104) with a same-contract collision witness; `period_lock_id` refused by name until F-CLO's locked-dataset branch (D-98 96). Reading and identity rules only; no column, parameter or control-total name change |
| 1.17 | 2026-09-20 | lane F-CLO (CLO-8; supervisor ruling D-98 candidate 96) | **Applied.** §0.5 RV-04 run semantics: an as-locked run reads the lock's frozen dataset of the report's E-64 kind (CSV = the frozen file; JSON grid / XLSX / PDF from the frozen rows as text columns) and never current figures under an "as locked" label; a report without a lock dataset kind or a lock without that kind's snapshot returns the named refusal; no cell explainer on an as-locked run; CLO8-SCOPE-R1 (same revision): an as-locked run is of the lock's entity / book / period — mismatched selectors are the named refusal, other filter / dimension / view / band controls unavailable, readers see it only within the lock's entity, an inconsistent run (entity, book, period or extra selector) is shown to no one in the list or on any addressed read, completed runs included. Formatting: the header's `Date` and `Status` cells, which had run into one line, are separate rows again. Number reserved by the supervisor (1.14–1.16 other lanes). |
| 1.18 | 2026-09-20 | lane F-RPS (F-RPS-CUTOFF-R1; supervisor engineering ruling D-98 candidate 112; docs first; number assigned by the supervisor) | **Applied.** RPT-R-01 parameter keys gain `known_at_basis` (`record` \| `historical`; 04 §16.9 rev 1.54); RV-03 run details show `known_at` with its basis (a pre-parameter run: "basis: record (pre-parameter run)"). An explicit as-of read (`historical`) keeps the supplied cutoff exactly; a run whose `known_at` defaulted uses the record basis. No screen layout change. |
| 1.19 | 2026-09-20 | lane F-RPS (frps3b — CUTOFF-R1 consumed-source binding; supervisor dispatch on Codex 2131; docs first; number assigned by the lane per descending union) | **Applied.** RV-03 run details show "Sources" (API-S-ReportRun `sources`, 04 §16.9 rev 1.55): "Bound: <versions> contract versions, <labels> grouping labels, <rows> rows, cutoff <datetime>" for a bound live run, "Frozen dataset (as locked)" for an as-locked run, "Unbound (created before source binding) — rerun and cell explanation unavailable" for a `legacy_unbound` run of an `adapter` / `retained_inputs` builder (an `open` builder's legacy run: "— a rerun is a new live evaluation"; Codex 2331) (Codex 2154 / 2216 / 2225: pending, failed-without-capture, retained and open kinds have their own copy; an open run's rerun button reads "Rerun (new evaluation)"); the "Rerun from the same source" button is disabled with that copy on a legacy run (409 `invalid-transition` if invoked); SB-R-07: the explanation of a bound live run resolves against its bound sources, an unbound live run's returns 404 `not-found` by name, shown as the problem copy in the Explain panel. No layout change. |
| 1.20 | 2026-09-21 | lane F-LMG (workstream 2 LM-CL-09 writers; supervisor engineering ruling D-98 candidate 133; docs first; number assigned by the supervisor 03:01) | **Applied.** §10.3 SF-19:detail, step "Mapping (opening balances)" (04 §17.2 rev 1.64 LM-CL-09 / LM-CL-03; BUILD_SPEC LMG-2 rev 1.11): table "Entity mapping" gains "Calendar" (fiscal calendar select; default the workspace's only calendar when exactly one exists, else blank and required for a "Will be created" row; a "Matched" row shows the entity's calendar read-only) and "Time zone" (IANA time zone select; required for a "Will be created" row; a "Matched" row shows the entity's time zone read-only) after "Entity"; a DS-CMP-21 field group "Entity defaults" ("Calendar", "Time zone") above the table, applied to every "Will be created" row without its own value (the row's own value wins); under "Batch parameters" a toggle "Create missing products" (default on) with the helper text "Products absent from this workspace are created from the legacy SKU name with the parity template of their rows; a SKU mapped to two templates is refused."; validation copy (422 by name, one finding per entity, field named): "Choose a calendar for <legacy entity>.", "Choose a time zone for <legacy entity>.", "SKU <name> maps to two templates (<a>, <b>); resolve it in the legacy database before importing."; data binding: `POST /migrations/{id}/import` gains `entity_mapping[].calendar_id`, `entity_mapping[].time_zone`, `entity_defaults {calendar_id?, time_zone?}`, `create_missing_products` (default true); the functional currency is always the workspace reporting currency (not a field); the legacy-parity notice unchanged. The frontend implementation is a separate later WEB item tracked by the supervisor; this revision is the screen contract. No layout change elsewhere. |
| 1.24 | 2026-09-22 | lane F-LMG (F-LMG-CL55; D-98 89 RULING 2 + AMENDMENT 1; D-98 candidate 149; numbers assigned by the supervisor) | **Applied.** RPT-10 / RPT-12 legacy exports: the decimal column `Current Rev Rec` (LM-CL-55) carries the literal text `unavailable` on a row whose exact activity the engine names unavailable (an adjusted target — `params.exact_basis`); every other row writes the exact decimal text of 04 §17.1 rule 4a; a legacy trace or a missing / redirected / invalid companion refuses the whole run by name (RPT-10 refusal copy, DG-PAR-05). No layout, filter or parameter change. |
| 1.23 | 2026-09-21 | lane F-CTR (CTR-17 `modification_register` frozen dataset; D-98 140-A1 on Codex production-20260921-1505 §3; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §5.6.2 RPT-14 gains "Frozen dataset": the lock dataset's S15-R-20a shape (key code columns first, code and measure columns, attributes), the two declared money measures, empty optional cells and no total row (the totals per currency are control totals), the served currency view; the grid's fields remain the builder's columns. No screen layout change. |
| 1.22 | 2026-09-21 | lane F-LMG (F-LMG-API-2; the SF-19:detail host wording lane F-ADM needed beyond §10.3 — ruled the migration lane's row; D-98 133 AMENDMENT 1 (b) for the Field mapping read; number assigned by the supervisor 08:41) | **Applied.** §10.3 SF-19:detail: States gain "Not found" (SCR-ST-07 "Migration not found" + description), "Load failure" (SCR-ST-05 "Could not load the migration") and the two FAILED origins (without a `profile` → Profile with "Profiling <file name> failed. Nothing was committed."; with a `profile` → Import with "Importing legacy database <migration no> failed. Nothing was committed."); the "Host wording" statement: the DS-CMP-24 label as the job region's accessible name, API-S-Job progress rendered verbatim (no unit noun), in-table control names "<Column> for <legacy entity>", the wireframe's stepper captions, the document title "Migration", the status → step redirect with the API-derived FAILED-origin rule and its caveat (holds only while PROFILING / IMPORTING remain the only FAILED origins; no `failed_phase` member by ruling), "Back" on Mapping, and the read-only "Field mapping" table rendering `GET /migrations/field-mapping` verbatim; test hooks `SF-19-job` and `SF-19-grid-field-mapping`; accessibility names. Body follow-up (same revision, before landing; lane F-ADM's ask 18:0x Z): the "Field mapping" table's headings / row key and its own load failure SCR-ST-05 "Could not load the field mapping". No binding change beyond the field-mapping read (04 1.66); no layout change elsewhere. |
| 1.21 | 2026-09-21 | lane F-LMG (slice D-98 candidate 89; supervisor dispatch after integrated batch #5; Codex production-20260921-1155 §1; docs first; number assigned by the supervisor) | **Applied.** §5.6.2 RPT-10 `legacy_contract_history_export` formats (04 §17.1 rule 4 rev 1.66): `Previous Remaining Allocation`, `Current Remaining Allocation`, `Current Rev Rec - Cumulative`, `Current Contract Position - POB`, `Current Contract Position - Contract Level` and `Current Reclass to UAR` render the exact trace-sourced value (DG-PAR-05 `exact(m)`, exact decimal text) instead of the posted cents; a missing trace, an absent node or a hash mismatch refuses the whole run by name with every offending version / column listed; an adjusted target's cumulative is posted-only by rule; `Current Rev Rec` stays posted until the engine's exact activity operand exists (ENG-T1F, T1F-89-1); RPT-12 inherits by reference; RPT-53 (no builder) out of scope. No binding, state or copy change elsewhere; the 71 names, order and row keys unchanged. |
| 1.25 | 2026-09-29 | lane F-RPS-REG (BUILD_SPEC RPS-9 SSP report builders; docs first; number taken as the next free decimal per the lane brief, reported to the supervisor) | **Applied.** §5.6.4 RPT-21 `allocations_by_ssp_version`: the grid gains the column "SSP entry" (`ssp_entry_id`, export and API only) after "SSP book version" — the T-REF-30 value row the allocation was priced from, which REQ-SSP-011 lists as stored lineage ("value row id") and the BUILD_SPEC RPS-9 acceptance `test_allocations_by_ssp_version_sf_ord_20417` names (PRD J-03-AC-2 "entry id"); the on-screen grid keeps its columns. No parameter, row key, total or copy change. **Amended in place 2026-09-30 (BUILD_SPEC RPS-10 builders; docs first).** §5.6.5 RPT-24 `user_access_listing`: a membership that holds no role at `as_of` has one row without a role, so every membership appears (PRD J-17.6 "every membership"); removal and existence are read at `as_of`. RPT-25 `sod_conflict_report`: the five exception columns describe the exception covering the conflict at `as_of` (its E-96 status at that instant) and are empty without one. RPT-26 `approvals_register`: every request without a decision has its row (a pending request, and a request voided before any decision), keyed with its first step and sequence 0; the grid gains "Subject" (`subject_id`) and "Content hash" (`subject_content_sha256`), export and API only, which the BUILD_SPEC RPS-10 acceptance `test_approvals_register` names ("subject reference", "`subject_content_sha256`"). RPT-44 `chain_verification_report`: two verifications that finished at the same instant keep distinct row keys. The builders of RPT-23 to RPT-26 and RPT-44 echo the resolved range or instant in the control totals (`from_date`, `to_date`; `as_of`; `from`, `to`), as `contract_history` and `rpo` do (L6-3-Q-26). No parameter, format or copy change. **Amended in place 2026-09-30 (BUILD_SPEC RPS-11 builders; docs first).** §5.6.2 RPT-29 `estimate_change_listing`: the row key names the contract, `estimate:<contract external id>:<element code>:<version no>`, because an element code is unique within its contract only (04 T-CON-12 `ux_estimate__code`); an element's first approved version is listed with the pair "v1" and empty "before" cells; the grid gains "Preparer" (`preparer`), which PRD J-07-AC-2 and the BUILD_SPEC RPS-11 acceptance `test_estimate_change_listing_k06` name; "P&L effect" is defined as the catch-up of the contract versions the version's `ESTIMATE_CHANGED` events caused, empty when that catch-up is joint with another estimate version or a modification. RPT-30 `scope_exclusion_register`: "Out-of-scope amount" is the allocation of a `LEASE_842` obligation (POLICIES PT-09), else the contract version's amount when it holds one routed-out line; the grid gains "Rationale" (`rationale`, export and API only), the rationale of the judgement record on the obligation, which the acceptance `test_scope_exclusion_register` names. The builders echo the resolved range or date in the control totals. No parameter, format or copy change. **Amended in place 2026-09-30 (BUILD_SPEC RPS-12 builders; docs first).** §5.6.6 RPT-33 `book_bridge`, RPT-34 `adoption_bridge` and RPT-35 `intercompany_pairs` named their sections' columns by header only: each gains its dataset grid (fields, row keys per section) and its rules. RPT-33: `REVENUE` from the entity's subledger lines of each book over the range, the five balances as RPT-02 at the range end, difference = ASC 606 less IFRS 15; the driver of a contract's difference is identified from stored facts (`COLLECTIBILITY` when the Step 1 conclusion differed between the books: exactly one of them held the contract as `NOT_A_CONTRACT` at a computation, or both hold it so at their latest version; `ONEROUS_CONTRACTS` for the loss provision; `COST_IMPAIRMENT_REVERSAL` for the cost assets when the IFRS 15 book posted a JET-09d reversal; else `OTHER`); `ADVANCE_CONSIDERATION_FX` is 0.00 in the served transaction amounts; `FRAMEWORK_ELECTIONS` and `LICENCE_RENEWALS` are not identified in 1.0, are part of `OTHER`, and show an empty cell rather than 0.00 when a difference is left to `OTHER` (no governing document fixed the attribution; adopted as the documented rule by supervisor ruling R-47 (b) of 2026-09-30 — supervisor ruling pending the accountant, AD-44; REQ-BK-006 stays partial for the two drivers). RPT-34: the date of initial application is the first day of a period (new validation copy "Choose the first day of a period of the entity's calendar."); legacy revenue from the `LEGACY` book's `PRE_STANDARD_REVENUE` lines by origin period, ASC 606 revenue and billed amount from the T-ENG-03 nodes of the latest `ASC606` version, the legacy contract liability = billed less legacy revenue, no legacy contract asset, no legacy contract cost asset (empty); contracts without an `ASC606` version in the disclosures are stated in the control totals. RPT-35: a side whose entity is outside the run is empty, the tie-out tests the pairs with both entities in the run, section 2 keys and `pair_amount` (POL-171), the transaction view. RPT-32 and RPT-36 are unchanged. No parameter or format change. **Amended in place 2026-09-30 (BUILD_SPEC RPS-8 RPT-17 builder, assigned to the lane by the supervisor; docs first).** §5.6.3 RPT-17 `late_entry_report` named its two sections and nine fields only: the grid gains "Section" (`section`), "Entity" (`entity_code`), "Event key" (`event_key`) and "Event label" (`event_type_label`), the last three export and API only, and the specification gains its dataset and rules — the population (the events of the run's entities' contracts recorded by the cutoff), the first lock (`lock_recorded_at` = the earliest `LOCK` record of the entity, book and period), the window (both sides of the period end, inclusive), `days_from_period_end`, the row identity of an event listed in both sections (`section` with `row_key`), the row order, the stored default of `window_days` (the registry value at the run's `known_at`) and its validation copy at the API. No parameter, format, total or copy change. **Amended in place 2026-09-30 (BUILD_SPEC RPS-8 acceptance `test_je_population_ties_and_flags_post_close`; docs first).** §5.6.3 RPT-15 `je_population`: "Created by" (`created_by`) names the run's preparer — the principal that requested the run's calculation (04 T-PLT-27 `job.created_by`; the runner of BR-JE-01) — as the report's definition and empty copy state ("with preparer, approver and UTC timestamps"; REQ-JE-018 "creator"); the builder had shown the system principal under which the calculation job writes every entry. No column, key, total or copy change. |
| 1.27 | 2026-09-30 | lane F-CLO-B (BUILD_SPEC CLO-16; supervisor ruling R-54 of 2026-09-30; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §0.3 SB-R-06: job label `RECONCILIATION_GENERATE` "Generating <kind label>" (04 E-14 rev 1.121). §2.1: `POST /reconciliations` names its job kind and the reconciliation id header; every generation is a new reconciliation and the grid lists the current one of each kind (`is_current`). §2.2: the roles row and the reopen interaction — reopening a reconciliation takes `recon.signoff` (it discards the reviewer's sign-off; BUILD_SPEC CLO-16 acceptance), from `PREPARED` or `REVIEWED` only; the row stays `REOPENED` and the next generation replaces it; a `CERTIFIED` reconciliation is reopened only with its period (04 T-CLS-06). The preparer's sign-off needs an MFA-verified session (T-CLS-08). **BUILD_SPEC CLO-17 and supervisor ruling R-58 (e) (same revision).** §1.1 gate label table: `RECONCILIATIONS_GENERATED` gains the detail "Reconciliation out of date, generate it again: <kind label>". §2.2 data bindings: `attach-trial-balance` answers 202 with the `RECONCILIATION_GENERATE` job (the "Generating or pulling" state), and a file that cannot be compared is refused by the request with its rows. **Read members for BUILD_SPEC CLO-25 (same revision; supervisor ruling R-68 (c)).** §2.1 reads the list with `is_current=true`; §2.2 data bindings name what the key figures (`summary`), the header's Source and the pulling and pull-failed states (`trial_balance`) and the "Pull from <connection name>" choice (`gl_connections`) read. No wireframe, locator or test hook changes |
| 1.30 | 2026-09-30 | lane WEB-QA (the supervisor's ruling R-59 of 2026-09-30; browser-QA finding Q-9, write side; number assigned by the supervisor in the lane package) | **Applied.** §9.10 "Request SoD exception": "Valid from" and "Valid to" are dates; the window is sent in platform time as 00:00:00Z of "Valid from" to 23:59:59Z of "Valid to" (DESIGN_SYSTEM DS-I18N-08 rev 1.6) and lasts at most 366 days (04 T-PLT-14), so "Valid to" is at most 365 days after "Valid from"; the copy "Choose a validity of at most 366 days." is unchanged. The row said "at most 366 days after 'Valid from'", which with an inclusive last day is one day more than the API admits. No route, test hook or copy key changes |
| 1.26 | 2026-09-30 | lane FIX-D2 (supervisor ruling R-40 (a) of 2026-09-30 on the key audit of R-16; PRODUCT DEFECT; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §5.6.1 RPT-01 `revenue_waterfall`: each identifier of a `row_key` — the contract's external id, the obligation key, the product code, the revenue category — is CV-21-encoded before the join, as RPT-05's row key and the frozen long-form keys already are (D-98 104). The builder groups its rows by that key, and the unescaped join made the obligation `C` of contract `A:B` and the obligation `B:C` of contract `A` ONE row `obligation:A:B:C` holding the sum of both (measured: 19,726.02 where two rows of 9,863.01 belong, the contract `A:B` not shown); a key split by currency could also replace another row. An identifier without `%` `/` `@` `#` `:` keeps its key; one that holds a delimiter changes its key text only (`POB #1` → `POB %231`), the identifier columns are unchanged. The other presentation row keys joined from raw identifiers (RPT-02, RPT-03, RPT-04, RPT-09, RPT-10, RPT-11, the RPO exempt rows) group nothing by the key and show no wrong figure; they take the same encoder as item RPT-ROWKEY-ENC-1 of the reports lane, not here. |
| 1.31 | 2026-09-30 | lane F-RPS-REG (supervisor rulings R-63 (a) and R-63 (c) of 2026-09-30; docs first; number assigned by the supervisor, register index 37; row appended at the table's tail; PRD rev 1.57; 04 rev 1.128) | **Applied.** §5.6.5 RPT-23 to RPT-27 gain a "Permission" row: the user access listing, the SoD conflict report and the API client inventory are run under `audit.read` and not under `report.run` (Tenant Admin, PRD J-22.8; Auditor, J-17.6), with the known limit that a file output needs `report.export`, which the Tenant Admin role does not hold; the configuration change register and the approvals register need `report.run` and `audit.read`. A Viewer, an SSP Analyst and an SSP Approver run none of the five. §5.6.3 RPT-16 and RPT-17: "Recorded by" and "Approval" of an event an import commit wrote are those of its upload — the user who uploaded the import and the upload's approval request (PRD J-04.5); every other event keeps its own. No grid column, parameter or copy string changes. |
| 1.32 | 2026-09-30 | lane F-CLO-WEB (BUILD_SPEC CLO-25; the supervisor's rulings on the lane's read-in of 2026-09-30; docs first; number assigned in the package; row appended at the table's tail) | **Applied.** §2.1 as built: "Generate reconciliation" lists the kinds the API generates (billing to subledger; subledger to GL with CLO-17) and the two rollforward items are owed (422 on `kind`); the control is rendered for `recon.prepare` in an open, soft-close or reopened period; the generations a later one replaced are listed under the grid as "Earlier generations (<n>)"; the default columns, the "Sign-offs" column below 1440 px, the job row, the refused generation and two test hooks. §2.2 as built: the breadcrumb; "Source" of a billing reconciliation; the key-figure rule (API rows only, no client sum); the default columns per kind; "Difference" as plain money until API-R-49 names the object type (item REC-EXPLAIN-1); the read-only drawer outside a draft; the states Prepared, Superseded, Reopened, Period not open and Command refused with their copy; command controls only on the current reconciliation of a workable period; the reviewer's sign-off hidden from every holder of `integration.manage`; the `mfa-required` paths; success toasts; the 1280 px departure for "Explanation"; test hooks for the key figures and the state banners. On the members of BUILD_SPEC CLO-17 (main 7faf6389): the menu lists "Subledger to GL", whose generation opens the detail; the key figures read `summary`; the list reads `is_current`; the attach section — one segment per GL connection, "Upload CSV" for a holder of `import.upload`, the upload's own button "Upload and compare", the "Generating or pulling", "Pull failed" and "Upload failed" states read from `trial_balance` by re-reading the record, the two source lines, its test hooks. Item 1b of the lane's package (supervisor ruling R-83 of 2026-09-30): §1.1 — "Request reopen" is not offered while a reopen request is pending; the pending reopen banner without its reason clause until API-S-Approval states the request's reason (item APR-REQUEST-REASON-1), with "Withdraw request" and its confirmation; the banner of a pending permanent-lock request and its "View request"; "Permanently lock" rendered for `period.lock`, not rendered while pending, disabled with its reason through the DS-CMP-28 disabled menu item; "Lock period" with the step-up resend and its problems in the dialog, the order of periods on "Submit for lock", "Lock period" and "Open period" (supervisor ruling R-112 (a), item LOCK-ORDER-UI-1), a `lock-conflict` shown as a warning to try again (ERR-52; the supervisor's message of 2026-09-30 after lane FIX-D2's follow-up); the reopen drawer's attachments for a holder of an attachment permission and its judgement fields for `judgement.create`, with the line that tells another requester where the judgement is recorded (supervisor ruling R-100); two banner test hooks |
| 1.34 | 2026-09-30 | lane WEB-QA (browser-QA finding Q-30; supervisor ruling R-67 of 2026-09-30; decision D-87 L6-5-Q-9; number assigned by the supervisor, register index 42; row appended at the table's tail) | **Applied.** §3.3 Data bindings: the drill `GET /journal-lines/{id}/drill` takes no filter. The sentence said "filter `contract`", which decision D-87 L6-5-Q-9 had replaced by a filter the drawer applies in the browser by contract external id; the request function kept a `contract` key that its one caller left empty and is now without it (item W-9). No route, test hook or copy key changes |
| 1.35 | 2026-09-30 | lane F-CLO-B (BUILD_SPEC CLO-19; supervisor ruling R-79 of 2026-09-30; docs first; number assigned by the supervisor, register index 43; row appended at the table's tail) | **Applied.** §1.2 data bindings: `POST /close-runs` answers 202 with the job or 200 with the active run (R-79 (h)), `resume` 202 and `cancel` 200; the screen follows a run by reading API-S-CloseRun (`status`, `current_step_code`, `job.progress`, `steps[].counts`, `steps[].problem`, `journal_run_id`), not the job; the rows keep the order of the T-CLS-01 array while the run executes "FX remeasurement" before "Release schedules" (R-79 (b)), so the running wireframe (row 5 running, row 6 queued) shows the layout, not a reachable state. No wireframe, locator or test hook changes |
| 1.36 | 2026-09-30 | lane F-ADM-WEB (BUILD_SPEC RPS-21; the supervisor's rulings of 2026-09-30 on the lane's read-in and on its correction of the default range; docs first; number assigned by the supervisor in the lane package, register index 46; row appended at the table's tail) | **Applied.** §6.3 SF-09:audit-log is stated as bound to API-R-10 of 1.0: the route row drops `f.outcome` (no outcome filter exists) and names the companion parameter `event` of `drawer=event`; every read carries a range — without `f.occurred` the last 30 days through today (UTC), stated in a caption and never written to the URL or a saved view, because a saved view stores raw `f.*` values — and SCR-ST-03 names that range; the object filter resolves a contract's external id or number through the contract search; the Actor filter offers the viewer and the actors of the loaded rows; the grid-column table gains the column "API-R-10 of 1.0", which marks each cell bound or waiting (Object label, On behalf of, API client and operator names, the actor drill) — the five waiting points are item AUD-API-GAPS-1 and are not approximated in the client; the verification header, the contents of the event drawer ("Recorded values" in the DS-FMT-23 form), the event-not-listed banner and three test hooks are stated. §6.4: when "Download digest", "Open register" and the "Reports" crumb render; the current row of "Recent verifications". §14.3 cites `event` (SCREENS.md SCR-URL-32, rev 1.13). No route, permission or chip word changes |
| 1.28 | 2026-09-30 | lane SECFIX-CLO (security finding SC-N4; supervisor ruling R-55 (c); docs first; number assigned by the supervisor) | **Applied.** §1.1 SF-05: "Request waiver" is offered only when the checklist row's `is_waivable` is true (04 API-S-PeriodCockpit rev 1.106) — the journal balance, journal completeness and controller certification gates are never waivable — and the dialog's consequence ("The gate counts as cleared once another user approves it") is what the server now applies at the lock request and at the lock decision. No layout, token or copy change |
| 1.37 | 2026-09-30 | lane API-GAPS (item API-ACTOR-MEMBERS-1; 04 rev 1.139; number assigned by the supervisor, register index 48; row appended at the table's tail) | **Applied.** §6.3 Grid columns, "On behalf of": the field is the member `on_behalf_of`, the API-S-Actor of the column `on_behalf_of_id`, shown as the user or the API client name. The row named the column; the audit event answered the bare id, for which a screen has no name without `user.manage`, and the API now answers the Actor in its place (04 §16.14). The "Actor" row is unchanged: the member `actor` already is the API-S-Actor of `actor_id` and `actor_kind`, and an API client is now named there as the row says. No layout, copy or state changes. |
| 1.29 | 2026-10-01 | lane SECFIX-APR (supervisor ruling R-56 (b) and R-38 (iv) with its addendum; 04 §14.3 rev 1.104; number assigned by the supervisor on 2026-09-30; row appended at the table's tail, entered late — the behaviour changed with the lane's Parts 1 and 2) | **Applied.** §9.10 SF-14 "Invite user": the second toast, "Invitation sent. Setup grants are approved by rule AUTO-BOOTSTRAP.", is shown when that rule approved every role of the invitation at once — the bootstrap Tenant Admin during setup, while no other person has been active with `access.approve` — and no longer whenever `setup_completed_at` is null; every other invitation shows "Invitation for <email> is waiting for approval." The screen already decides by the answer (`invitationOutcome`: no role `REQUESTED`). No layout or copy changes. |
| 1.47 | 2026-09-30 | lane F-CLO-B (BUILD_SPEC CLO-20; docs first; number assigned by the supervisor, register index 72; row appended at the table's tail) | **Applied.** §1.2 data bindings name the `steps[].counts` members behind each summary (04 T-CLS-01 "Step counts" rev 1.163); the `GL_TIE_OUT` row gains "No trial balance attached" (BUILD_SPEC CLO-20 acceptance, PRD J-13.7); the `BLOCKED` row states what a failed invariant shows. No wireframe, locator or test hook changes |
| 1.39 | 2026-09-30 | lane WEB-QA (item W-19; crawl finding F1 of item W-13; the supervisor's ruling of 2026-09-30 on it; number assigned by the supervisor, register index 50; row appended at the table's tail) | **Applied.** §3.3 Regions and components names the four FilterBar fields. "Contract" and "Batch" were text fields whose typed text went to the uuid filters `contract` and `batch_id` of `GET /journal-runs/{id}/lines`, which answered 422 `validation-failed`: a filter that could only fail. "Contract" is the combobox of contracts the exceptions screen uses and sends the contract id; "Batch" lists the batches of the run and sends the batch id, the value the Batches tab already writes into its link. No route, test hook or copy key changes |
| 1.40 | 2026-09-30 | lane F-RPS-REG (item RPT-ROLLFWD-KINDS-1; supervisor ruling R-72 of 2026-09-30 on the lane's pre-build report; docs first; number assigned by the supervisor; row appended at the table's tail; ENGINE_SPEC_B rev 1.76) | **Applied.** §5.6.1 RPT-03 gains the table "kind → line": the nine line codes of 03 REQ-RPT-006 stand and every flow of the control role is shown under one of them by its kind — `BILLINGS` = billing less credit memos; the two revenue lines = revenue relief, the contracting side of an intercompany pair included, net of negative revenue; `RECLASSIFICATIONS` = a deposit transfer, noncash consideration, financing, the refund liability and its release, the contra and the transfers between the asset captions; `OTHER` = the unexplained difference only. Under `billing.posting = ERP` the billing of a period enters from the billing documents against the engine's stored billed amount (ENGINE_SPEC_B S15-R-03a). RPT-04: "Revenue recognized" and "From opening contract liability" count the same revenue family. The three mappings and the deposit-transfer presentation are stated as supervisor ruling R-72, pending the accountant (candidate AD-48). Cause: the report walked the posted lines of the role alone and labelled every credit `BILLINGS`, so an invoice that posts no line was shown as `OTHER` and the rollforward failed its tie-out in every period that holds an invoice. |
| 1.46 | 2026-09-30 | lane F-RPS-REG (item RPT-OOP-ROWKEY-1 — PRODUCT DEFECT, release blocker; supervisor ruling R-112 (j) of 2026-09-30; docs first; number assigned by the supervisor, register index 71; row appended at the table's tail; ENGINE_SPEC_B rev 1.110) | **Applied.** §5.6.3 RPT-16: the `row_key` is `<origin period key>:<posting period key>:<event key>` — the whole key of the aggregation — in place of the event key alone, which one event set shares across the origin periods of its late lines (the rows are one per origin period, posting period and event set; with one `row_key` for several rows the grid had no row identity and the lock of the posting period was refused on the frozen dataset). The `event_key` column, the other columns, the totals and the copy do not change. |
| 1.45 | 2026-09-30 | lane F-ADM-WEB (item AUD-ACTOR-BIND-1; supervisor ruling R-112 (h) of 2026-09-30; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §6.3 Grid columns: "Actor" is bound for every kind of principal — a person by display name, "System", an API client by its name and an operator as "Operator <name> under support grant", read from `actor.display_name` (API-S-Actor, 04 §16.14 rev 1.139); "On behalf of" is rendered from the Actor `on_behalf_of` with the same naming and shows no value where the event names nobody. The event drawer names that principal under "On behalf of" and keeps its recorded id among "Recorded values". Point (4) of the bindings paragraph is bound; the drill of the Actor cell still waits for a membership id (lane API-GAPS G-2). The supervisor's ruling of 2026-09-30 19:31: §6.3 the companion parameter of `drawer=event` carries the event's chain sequence (`event=<chain sequence>`; SCREENS.md SCR-URL-32 rev 1.20), stated for the final read — a sequence the loaded rows do not hold is read alone through the `chain_seq` filter of `GET /audit-events` (lane API-GAPS G-2) — with "Event not listed" marked as the interim; §6.4 a failed run links to its first failing event with the same parameter. No route, permission or chip word changes |
| 1.38 | 2026-09-30 | lane FIX-D2 (item CLO-LOCK-OPEN-REDIRTY-1; supervisor rulings R-101 (a) and R-106 (a) of 2026-09-30; docs first; number assigned by the supervisor, register index 49; row appended at the table's tail) | **Applied.** §0.3 SB-R-06: job label `PERIOD_OPEN_REDIRTY` "Re-marking contracts for <entity code> <period label>" (04 E-14 rev 1.164). §1.1: the gate label table gives `NO_DIRTY_GROUPS` a second failing detail, "Contracts not re-marked since the period was opened", shown without a count while the re-marking job of a period a lock opened has not succeeded; the row is not waivable meanwhile (`is_waivable` false: no "Request waiver"); BLK-08 counts that job once its newest one failed (a waiting job is named by the gate, not by "Failed jobs"). No wireframe, locator or test hook changes |
| 1.53 | 2026-09-30 | lane F-ADM-WEB (BUILD_SPEC RPS-18; the supervisor's rulings of 2026-09-30 on the lane's read-in; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §5.3 SF-08:runs and SF-08:run are stated as bound to API-R-41 of 1.0 — who opens them (`report.run` or `audit.read`), the Reports frame, the four filters as the route row names them with the two dates as whole days, the API's order without a sortable column, the contents of the run record, "Open report view", the rerun by `sources` (RV-03 rev 1.19), the rerun result stated for the final read (`rerun_of` and the two flags on API-S-ReportRun, lane API-GAPS G-6) with the carry in the navigation state marked interim, the states and the added test hooks; §6.3 the Object cell links a `report_run` to SF-08:run. No route or chip word changes |
| 1.51 | 2026-09-30 | lane F-RPS-REG (item RPT-FORMER-GROUP-VERSIONS-1 — PRODUCT DEFECT, release blocker; supervisor ruling R-115 (a) of 2026-09-30; docs first; number assigned by the supervisor, register index 84; row appended at the table's tail; 04 rev 1.175; ENGINE_SPEC_B rev 1.123) | **Applied.** A contract computed in its own group and combined later by the approved command was read from both groups: RPT-02 listed it twice under one row key, RPT-06 and RPT-07 stated its obligations twice, RPT-11 listed them twice, and the lock of the period was refused on the frozen datasets. §5.6.1 RPT-02 (the latest version of the group the contract is a member of), RPT-05 (one version per contract and period), RPT-06 (the version at the as-of date along the contract's chain of groups), RPT-07 (the combination under "Modifications" of each member), §5.6.2 RPT-11 (per contract). No column, label, total or copy changes. |
| 1.49 | 2026-09-30 | lane SECFIX-CLO part 2 (item CLO-CANCEL-CLOSE-REOPENED-1; 04 rev 1.170, PRD rev 1.99; docs first; number assigned by the supervisor, register index 79; row appended at the table's tail) | **Applied.** §1.1 End soft close: the consequence sentence promised "The period returns to open" for every period. A period that has been locked before returns to `reopened` (PRD SM-07 rev 1.99), where BR-CLS-06 keeps applying, so the dialog says that for a period whose current lock record is a `REOPEN`. Title, reason select, comment and button are unchanged. |
| 1.57 | 2026-10-01 | lane F-ADM-WEB (item AUD-SCREEN-BIND-1; the supervisor's message of 2026-10-01 00:04 on the lane's pre-build line: eight bindings and additions (a), (b), (c); docs first; number assigned by the supervisor; row appended at the table's tail; 04 rev 1.154) | **Applied.** §6.3 SF-09:audit-log is bound to the reads lane API-GAPS put on main (0f8c0c5e): (1) the filter `f.outcome` (`is:` or `in:` over `SUCCESS`, `DENIED`, `FAILED`) → `outcome`, one parameter per literal; (2) `f.object` → `contract_id`: the trail of the contract, every event that names it whatever its object type, narrowed by `f.object_type` when both are set; (3) the trail is read whole — without `f.occurred` neither `from` nor `to` is sent and the caption reads "Showing every event that names <value>. Add the Occurred filter to narrow the range."; (4) an `event` link whose sequence the loaded rows do not hold is read alone by `chain_seq`: the drawer opens at once, shows the loading state or the failure of the read with "Retry", and fills when the event arrives; the state "Event not listed" becomes "Event unknown" ("The link names no audit event of this workspace.") for a value that is no sequence or that no event has; (5) the Object cell and the drawer show `object_label` — an identifier in the identifier face, a name in the text face — linked where the record's screen opens from the id; an event without a label keeps the type in words and nothing says whether a label exists (addition (c)); (6) the Actor's name links to SF-14:user for a holder of `user.manage` when the event carries `actor_membership_id`; (7) the options of `f.actor` are the principals who acted in the range on screen (`GET /audit-events/actors`), at most 100: when the range holds more a line under the chips says so and a name outside them is reached by narrowing the range — no server search (addition (b)); (8) §6.4 SF-09:verification reads `GET /audit-events/verifications/{id}`, 404 is SCR-ST-07, and the list is read for "Recent verifications" only. The event drawer lists a member as a change only when it differs: a member that is null before and null after is not listed (addition (a); finding Q-58). Enter on the Actor or the Object cell opens the cell's link and, where the cell shows none, the event drawer. The "Export" button (RPT-43) is unavailable with its reason while the list carries an Object or an Outcome chip: the report takes neither `contract_id` nor `outcome`, so its rows would not be the list's (owed by the report's owner). No route, permission, chip word or test hook changes |
| 1.42 | 2026-09-30 | lane F-CLO-WEB (BUILD_SPEC CLO-24 and item CLO-JDG-ESTERR-UI-1; the supervisor's rulings of 2026-09-30 on the lane's report, questions A, B and C, and R-94 (d); docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §1.2 as built: the run is followed while queued or running by every reader; quarantined contracts are the engine's open blocking items of the entity (no `code`, no `period`; no "Customer" column) and the banner counts the run's own `groups_quarantined`; the failed banner shows the step's problem title and detail; who sees "Run close", "Resume close run" and "Cancel close run"; the lasting "Open journal run" link; the duration after the summary below 1440 px; two banner test hooks. §1.4 as built: the shown columns of the locks grid and the line of the newest lock, "Frozen as known at" (`cutoff_known_at`), the person from API-S-Actor, the approval by number where the reader may read the request, the previous lock by kind and instant, the drawer's title, content and URL, the activity copy, pages of 50; the certification results, the snapshot kinds, the ledger head hash and a `request_no` on the rows are owed to the API. §1.5: `POST /close-runs/multi-entity` stays the binding (BUILD_SPEC CLO-21); the interim start of one `POST /close-runs` per chosen entity, the period of each entity's own calendar by its dates, the entities chosen when the page opens, the rows, the access-limited state. §1.1: "Run close" opens SF-05:close-run; "Close several entities" in the overflow; "Record estimate-versus-error judgement" on a locked period for `judgement.create` (item CLO-JDG-ESTERR-UI-1), its subject the contract — a period as subject and a judgement on the reopen request are owed to the API; a period of the LEGACY book (API-S-Period `follows`; supervisor rulings R-112 (e), R-113 (h) and R-114 (d); PRD ERR-76) offers no command of a close beside "Open period" and "End soft close", and shows one line naming the book it follows, that book's state and the way there in place of the close status, the blockers and the checklist, with the tabs "Checklist" and "History" (§1.4: its empty locks grid; §1.5: the page in a LEGACY context). §2.2: "Upload CSV" needs `import.upload` beside `recon.prepare`. No route, wireframe or existing copy key changes |
| 1.59 | 2026-10-01 | lane F-ADM-WEB (the API-client screen states, part 1; supervisor ruling R-113 (e) of 2026-09-30 and the supervisor's message of 2026-10-01 01:58; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §0.4: E-103 `api_client_status` maps `PENDING_APPROVAL` to "Pending approval" and `REJECTED` to "Rejected", both DS-CMP-19 words, beside `ACTIVE` and `REVOKED`. §9.15 States: a client that awaits approval and a client whose request was refused show that chip and offer no action — "Rotate secret" and "Revoke" stay the actions of an `ACTIVE` client. The two literals are those ruling R-113 (e) gives E-103 (an API client's scopes are an access grant: the client is created `PENDING_APPROVAL`, is `ACTIVE` when its request is approved and `REJECTED` when the request is rejected, withdrawn or voided); 04 gains them with lane SECFIX-APR's slice, and this revision precedes it so that the pane reads such a row when the API first answers one. The creation flow, the link to the request and the issue of the first secret are part 2, bound when that slice is on main under a revision of its own. **Grown before its merge** (the supervisor's message of 2026-10-01 02:35; question (d) of the lane's RPS-18 report): §5.3 SF-08:run — the progress of a computing run comes from the run's job for the run's starter and for a holder of `audit.read`, who may read that job (04 API-R-11: its owner or `audit.read`); another reader of the run sees the line "Running <report name>" without progress and the job is not asked for; the record is read again until the run ends in either case. No route, permission, copy or test hook changes |
| 1.62 | 2026-10-01 | lane F-ADM-WEB (the supervisor's ruling of 2026-10-01 on the lane's report of the API-client screen states, part 1; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §9.15 Interactions gains two entries. *Entity scope, interim:* `POST /api-clients` refuses every entity code until item API-CLIENT-ENTITY-SCOPE-1 is on main, so "Selected entities" is unavailable with the reason "An API client covers all entities." and "All entities" stays chosen. *Server errors:* a refusal's field errors show at the field whose member they name (DS-CMP-21) and leave it when its value is edited — in "New API client", "New webhook endpoint" and "Revoke"; a message that names no field of the form is listed in the banner. Before, the banner "Check the highlighted fields" stood over a form that highlighted nothing. No route, permission or test hook changes; one copy key is added (the reason line) |
| 1.61 | 2026-10-01 | lane F-CLO-WEB (item REOPEN-CLOSING-FLAG-1, the screens' half; the supervisor's messages of 2026-10-01 02:16 and 02:56 and ruling R-119 (h); PRD BR-CLS-06 rev 1.113, REQ-CLS-011 rev 1.99; docs first; number assigned by the supervisor, register index 102; row appended at the table's tail) | **Applied.** §1.1 banners: a period in soft close whose current lock record is its `REOPEN` shows, under the soft-close banner, "<period label> was reopened and is not locked again yet. Lines posted now are flagged post-reopen, and re-lock produces a diff report." — the cockpit showed the plain soft-close banner there, as if the reopen were over; the second approver joins the copy with item CLO-REOPEN-APPROVAL-1. §1.1 "Request reopen": the information line says "until it is locked again" instead of "while it is reopened". One test hook. No route, wireframe box, column or other copy changes |
| 1.65 | 2026-10-01 | lane F-CLO-WEB (item JRN-DRILL-CONTRACT-NAME-1, the screen's half; the member is lane F-CLO-A's, on main as de3a93ed; the supervisor's messages of 2026-10-01 02:56, 03:30 and 04:27; docs first; number assigned by the supervisor, register index 110; row appended at the table's tail) | **Applied.** §3.3 Data bindings and the source-lines grid: "Contract" is the drill's own `contract_external_id` and the drawer reads no contract. It read `GET /contracts/{id}` once for every distinct contract among a line's source lines before it showed a row — 91 reads, 18.8 s together, for the August 4010 line of the seeded tenant, behind the 10 s wait of the e2e row "SF-06:run-lines". The row of the grid said "mono link"; the cell is mono text, and reads an em dash for a line without a contract and for a contract outside the reader's entity scope. No route, test hook or copy key changes |
| 1.50 | 2026-09-30 | lane F-CLO-B (item CLO-GATE-RUN-1; supervisor rulings R-114 (b) and R-116 (e) of 2026-09-30; docs first; number assigned by the supervisor, register index 81; row appended at the table's tail) | **Applied.** §1.1 gate label table: `CLOSE_RUN_COMPLETED` "Close run completed", the thirteenth system gate before "Controller certification", with its three failure details — no close run, the latest run not succeeded (named with its E-62 label), the run out of date with the count of contracts — and no waiver offered (04 §16.8 rev 1.172). The two wireframes count fourteen gates. No locator or test hook changes: the row's hook is `SF-05-row-close-run-completed` by the existing rule |
| 1.60 | 2026-10-01 | lane WEB-QA (item W-12, slice a; the supervisor's ruling of 2026-10-01 on the item's pre-build line; `docs/04-DATA_MODEL.md` rev 1.148 T-PLT-10; `docs/design/SCREENS.md` rev 1.30; docs first; number assigned by the supervisor, register index 101; row appended at the table's tail) | **Applied.** Entity-scoped grants as the screens of SF-14 offer them. §9.10: the scope field of "Invite user" and "Add role" offers the entities the grantor's own `user.manage` or `role.manage` covers; a grantor of named entities is offered "Selected entities" alone with the API's sentence; the API's findings on a scope are shown under the scope field of their row; a command on a member or on a role renders when the viewer's permission covers every entity the grants name. §9.11: "New role" and "Propose change" need `role.manage` for all entities. Before, the scope field offered every entity to every grantor and no command asked for which entities its permission was held. No route or parameter changes |
| 1.54 | 2026-09-30 | lane F-SNP (BUILD_SPEC SNP-5 and SNP-4; supervisor rulings of 2026-09-30 on the SNP-3 and SNP-4 reports and on item CFG-PLATFORM-PIN-1; docs first; number assigned by the supervisor, register index 86; row appended at the table's tail) | **Applied.** §9.7 SF-15:sandbox, as the screen is built: (1) data bindings — the workspace's kind and origin from `GET /session` and the `GET /me` memberships, because `GET /tenant` needs `settings.manage` and the screen's reader holds `tenant.snapshot`; `POST /tenant/reset` without a snapshot id (the server resolves the seed); the list leaves out a sandbox that is still loading; a reset is followed until the session has moved; (2) "Created by" is the snapshot's `created_by` API-S-Actor (04 rev 1.177) — for a sandbox, of the snapshot that targets it; (3) a failed copy's banner carries the failed job's own sentence in place of the problem title — PRD ERR-77 where the retention policy is missing — and no "Retry"; the determinism warning counts contracts; (4) "A specific time" is the field "Time"; the reset's radio group is "Reset to" and an empty sandbox offers "Empty workspace" alone; (5) the origin line of an empty sandbox and of a reader who is no member of the source. §9.15: a sandbox disables "New webhook endpoint" as it disables the activation, and its empty state offers no action (05 SBX-08 rev 1.64). §9.8 SF-15:notifications (item SBX-EMAIL-1; 05 SBX-08 rev 1.116): in a sandbox the "Email" switches are off and unavailable with their reason, the mandatory kind's "In app" tooltip names the app alone and the footnote says that a sandbox sends no email. §9.7 the open workspace (PRODUCT DEFECT of the shell, found in a browser with a workspace and its copies; supervisor ruling of 2026-10-01): a copy's memberships carry the ids of the source's, and the shell matched a membership by id — four workspaces read "Current", the archived sandbox was listed and a choice between a workspace and its copies opened nothing. The open workspace is the session's; an archived sandbox is not listed unless the session is in it. No route, locator or test hook changes |
| 1.55 | 2026-10-01 | lane QA-BE (item RPT-ASOF-FIGURES-1; supervisor ruling R-116 (c) of 2026-09-30, pending the accountant, candidate AD-63; ENGINE_SPEC_B rev 1.127, 04 rev 1.179; docs first; number assigned by the supervisor, register index 88; row appended at the table's tail) | **Applied.** §5.6.1 RPT-01: recognized is revenue posted up to the as-of period, scheduled the later schedule amounts of obligations whose remainder has a scheduled part, awaiting trigger the obligation's amount at the as-of; a row's three states add up to its allocation at every as-of. RPT-06: the amount of an obligation is its remainder at the as-of date, read at that date. RPT-07: opening, closing and revenue are read at their dates. §5.6.2 RPT-11: a row states one date, the as-of, in every figure and both balance columns. No column, parameter, row key or copy string changes. |
| 1.41 | 2026-09-30 | lane SECFIX-IMP (the supervisor's rulings R-49 (a) and R-86 of 2026-09-30; 04 rev 1.142; number assigned by the supervisor; row appended at the table's tail) | **Named, not built.** §9.6 names the screen item *request-shred affordance*: `POST /files/{id}/request-shred` (04 API-R-12 rev 1.142) opens the `EVIDENCE_SHRED` approval for an uploaded document that a record rests on; like `POST /files/{id}/shred` it has no screen in 1.0 and is sent to the API (runbook RB-14). The affordance and the request view of SCREENS rev 1.15 are built by a frontend lane. No layout, route, test hook or copy key changes. |
| 1.58 | 2026-10-01 | lane F-RPS-REG (item RPT-FORMER-GROUP-READERS-1 — PRODUCT DEFECTS of the cause of rev 1.51; supervisor ruling R-117 (a) of 2026-09-30 and the supervisor's ruling of 2026-10-01 on the lane's finding; docs first; number assigned by the supervisor, register index 96; row appended at the table's tail; 04 rev 1.187; ENGINE_SPEC_B rev 1.135) | **Applied.** §5.6.2 RPT-09, RPT-10 and RPT-11: the version number — in the row key of RPT-09 and RPT-10, the order of their rows and the "Version" column of RPT-09 and RPT-11 — counts a contract's versions along its chain of combination groups; a contract combined after it was computed in its own group showed two rows under `version:<id>:1:<key>` and "Version" v1, v1. §5.6.1 RPT-02: a contract whose combined group awaits its first computation is read from the version it was last computed in (the report stated no row for it). No column, label, total or copy changes. |
| 1.68 | 2026-10-01 | lane WEB-QA (item W-12, slice b; supervisor ruling R-28; the supervisor's ruling of 2026-10-01 on the slice's pre-build line, choices A, B and C; `docs/design/SCREENS.md` rev 1.34; docs first; number assigned by the supervisor, register index 120; row appended at the table's tail) | **Applied.** §3.2 SF-06:run — PRODUCT DEFECT repaired: the overflow item "History" was offered to every reader of a run and read the audit events without asking, so a Viewer, an SSP Analyst and an SSP Approver got "Could not load the history" with a "Retry" that could not work. The item and the drawer render for a holder of `audit.read` for all entities; without it `drawer=history` opens nothing and leaves the address, a refused read closes the drawer and removes the item, and an overflow menu left without an item is not rendered. The Cancelled banner says when the run was cancelled, from `cancelled_at`, without a read for everyone else; which event it names for a reader of the audit events is unchanged. §6.3 SF-09:audit-log: the log is read with `audit.read` for all entities; a holder for named entities reads the access-limited state with the new description "The audit log covers every entity of the workspace. Ask a workspace administrator for a role that includes viewing the audit log for all entities.", and a read of the audit events refused with 403 renders that state in place of the page. §6.4 SF-09:verification stays open for a holder for any entity, and a refused read of the verification renders the same state instead of the error with "Retry" |
| 1.74 | 2026-10-01 | lane F-ADM-WEB (the supervisor's message of 2026-10-01 08:07, item 2; docs first; number assigned by the supervisor, register index 129; row appended at the table's tail) | **Applied.** §0.3 SB-R-08 names the test of a connection among the commands a sandbox holds back, with a reason line of its own: the sentence of ERR-17 speaks of journals, and a test neither posts nor exports. 05 SBX-08 rev 1.116 (item SBX-PROBE-1) made the test a restricted command for every adapter but `CSV_GL`; the screen is SCREENS §14.4 rev 1.35. No route, permission or test hook changes |
| 1.64 | 2026-10-01 | lane API-GAPS (item PERF-PERIODS-LIST-1; supervisor ruling of 2026-10-01 on the lane's pre-build line; 04 rev 1.199; docs first; number assigned by the supervisor, register index 108; row appended at the table's tail) | **Applied.** §5.5 Data bindings and the close dashboard's grid columns: a row of `GET /periods` answers `blockers` null (04 §16.8 rev 1.199 — the counts cost a statement over 23 tables for every row of a list that every screen reads), so the Blockers and the Batches acknowledged columns read `period.blockers` of the `GET /periods/{id}/cockpit` read the dashboard already makes for every row; the list supplies the rows, their `state` and their `close_run`. No built screen changes its read: the cockpit (§1.1) reads API-S-PeriodCockpit `period`, the home dashboard its own `close`. |
| 1.73 | 2026-10-01 | lane SECFIX-PLT (independent review of the platform security merge a7d63e81, finding 6; supervisor ruling R-111 (4) and the supervisor's message of 2026-10-01 14:57Z; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §5.6.5 RPT-25 gains the column "Through delegations" (`delegations`) after "Through roles": a permission held through an approval delegation is held, so a member who holds one function of a rule by role and the other by delegation — or both by delegation — is a row, and the cell names each delegation as "<delegator> until <DD MMM YYYY>". As built the report read roles only and showed no row for such a member, a conflict under an approved exception included. A delegation counts for the permissions its delegator held at `as_of` through the assignments the run's entity scope counts. 04 rev 1.189 (T-PLT-21, T-RPT-01 rule 5) carries the contract; no parameter, permission or route changes |
| 1.75 | 2026-10-01 | lane F-RPS-REG (item RPT-43-PARAMS-1; supervisor ruling R-119 (h) of 2026-10-01; docs first; number assigned by the supervisor, register index 135; row appended at the table's tail) | **Applied.** §5.6.5 RPT-43 takes `contract_id` and `outcome`, the two filters SF-09:audit-log gained with rev 1.57, so that an export under the range and the filters of the list states the rows of the list: with `contract_id` the rows are the trail of that contract — every event that names it, whatever its object type — and `outcome` keeps the events of the outcomes given. The sample world of J-17.5 is the contract's trail. Two parameter rows; no column, label, total or copy changes. The screen's part — "Export" under an Object or an Outcome filter — is bound by the lane of SF-09:audit-log once the report is on main; until then §6.3's state "Export unavailable" (rev 1.57) stands. |
| 1.66 | 2026-10-01 | lane F-CLO-B (item CLO-QUARANTINE-READ-1; the supervisor's ruling of 2026-10-01 on the lane's pre-build line; docs first; number assigned by the supervisor, register index 115; row appended at the table's tail) | **Applied.** The data bindings as the API serves them from 04 rev 1.206; the two screens are bound by lane F-CLO-WEB. §1.1 — BLK-02's link opens SF-11 with `blocking=<period id>`, the list `blockers.exceptions_open` is counted from, in place of `entity` and `period`, which left out every item that names no entity or no period. §1.2 — quarantined contracts are read as `GET /exceptions?blocking=<period id>&source=ENGINE&severity=BLOCKING`: the item of a group of several contracts is in the list; "Contract" shows the group's code for it. By supervisor ruling R-121 (i) `entity` on `GET /exceptions` lists the items that are the entity's by the gates' attribution, so BLK-03's read by `entity` and the grid's read as built hold the items that name no entity too; the home page's close row is renamed in SCREENS rev 1.37. No wireframe, locator, test hook or copy key changes |
| 1.67 | 2026-10-01 | lane F-CLO-B (item CLO-LOCKS-READ-1; the supervisor's ruling of 2026-10-01 on the lane's pre-build line; docs first; number assigned by the supervisor, register index 116; row appended at the table's tail) | **Applied.** §1.4 as the API serves it from 04 rev 1.207; the screen is bound by lane F-CLO-WEB. The read permission is `config.read`, the permission of both routes (`contract.read` was a slip of the earlier revisions). A record of the locks list and a transition state the number of their request, so "Approval" names it for every reader of the history; the record states its ledger head hash for the tooltip, its gate results for "Certification" and its datasets with row counts. No wireframe, locator, test hook or copy key changes |
| 1.71 | 2026-10-01 | lane F-CLO-WEB (item JRN-FAILED-EXITS-UI-1; the API is lane F-CLO-A's, on main as 15ccedb6 — 04 §16.7 rev 1.159, PRD ERR-73, ERR-74, ERR-79; the supervisor's assignment of 2026-10-01 and the lane's pre-build line; docs first; number assigned by the supervisor, register index 124; row appended at the table's tail) | **Applied.** The screens of the two exits of a failed journal run. **§3.2 SF-06:run.** The Failed row of the action bar gains "Cancel journal run"; the dialog says that the ledger is asked first when a failed batch is of an ERP adapter; the command answers 202 and the page follows the job — "Cancelling journal run <run no>", then the toast of a cancelled run or the banner "Journal run <run no> was not cancelled" with the job's sentence (PRD ERR-73; an unreachable ledger). On a run that is partly in a ledger the item is disabled with ERR-74's sentence (SCREENS SCR-PERM-03); the command's other refusals stay in the dialog as sent. The failed banner names the exits offered to the reader. A frame follows the run's active cancel or hand-over job also when it did not send the command, and the active-job read covers a run with a failed batch. "Download batch files" fetches before it saves: a refused download (ERR-79) saved a JSON problem under the batch's name. **§3.4 SF-06:run-batches.** "Hand over" on a failed batch of an ERP adapter, with its confirmation, disabled in a sandbox; "Record ERP reference" on every `exported` batch, which a batch handed over is; the row's "Download" as §3.2. Both screens ask their permissions for the run's entity (SCREENS SCR-PERM-02 (a)). The Cancelled banner reads the `SUCCESS` cancel event and names the person a job acted for; the History drawer tells a job's entries as "System on behalf of <name>", marks a refused event and quotes its refusal. Stated limit of 1.0: an ending that falls between two frames is read in History only. Joined with rev 1.68 at the merge of main 8ec7a521: "History" and the banner's name need `audit.read` for all entities. No route changes; one test hook added (`SF-06-banner-exit-refused`) |
| 1.80 | 2026-10-01 | lane F-ADM-WEB (item SBX-ADD-CONNECTION-1; the supervisor's message of 2026-10-01 09:41; docs first; number assigned by the supervisor, register index 153; row appended at the table's tail) | **Applied.** §0.3 SB-R-08 names the drawer "Add connection" of SF-16: in a sandbox it offers the adapters and the direction the API accepts there, and says why the others are not offered. 05 SBX-08 refuses an inbound connection in a sandbox at its creation; the screen is SCREENS §14.4 rev 1.43. No route, permission or test hook changes |
| 1.70 | 2026-10-01 | lane FIX-D2 (item RPT-RPO-ROLLFWD-1 — PRODUCT DEFECT; supervisor rulings R-78 (c) and R-121 (g); docs first; number assigned by the supervisor, register index 122; row appended at the table's tail; ENGINE_SPEC_B rev 1.161, 04 rev 1.213) | **Applied.** §5.6.1 RPT-06: a contract is in the report from the day it was activated, and an obligation satisfied after the as-of date is stated with what remained of it. §5.6.1 RPT-07: the row `LATE_EVENTS` "Late events" in section 1 and the column in section 2, what it holds, that a contract enters under "New contracts" in the period of its activation, and the limitation that remains (the line follows the versions' dates, not the ledger's posting period). §5.6.2 RPT-11: a contract is listed from the day it was activated; Effective date still names the version. §5.6.2 RPT-12: the legacy export keeps the row rule as it was — a version counts from its own effective date. No parameter, format, tie-out or chart changes. |
| 1.76 | 2026-10-01 | lane F-RPS-REG (item SCOPE-WORKSPACE-LISTS-1; supervisor rulings R-28 and R-121 (c) and the supervisor's ruling of 2026-10-01 on the item's pre-build line; docs first; number assigned by the supervisor, register index 128; row appended at the table's tail; 04 rev 1.219) | **Applied — PRODUCT DEFECT of the population.** §5.6.5 RPT-26 and RPT-23 took every request without a single entity for a tenant-wide one, and since 04 T-PLT-17 rev 1.104 a request of several entities or of all entities has none: measured, a run over one entity stated five of six requests, those of the other entity, of both and of all entities among them, each with its summary. A request is now stated when the run's entities cover every entity it names, a request of all entities only by a run that names every entity of the workspace, a tenant-level request always. Both reports name only entities inside the caller's scope of `report.run` AND `audit.read`. RPT-44 gains its Permission row: `audit.read` at any scope, with the reason it differs from RPT-43. §5.3 SF-08:run follows 04 API-R-11: the progress of another member's run is shown to a holder of `audit.read` for all entities. §5.6.1 RPT-08 says when a row exists: only where a `REVENUE` line exists in the range (the supervisor's word of 2026-10-01 on lane QA-BE's answer-key work; the builder as built, no code). No column, label, total or copy changes. |
| 1.69 | 2026-10-01 | lane FIX-D2 (the waterfall's entity — PRODUCT DEFECT for a contract performed across entities; supervisor rulings R-78 (d) and R-121 (g), and the supervisor's ruling of 2026-10-01 on the lane's finding on the Home; candidate AD-49; docs first; number assigned by the supervisor, register index 121; row appended at the table's tail; SCREENS rev 1.41) | **Applied.** §5.6.1 RPT-01 `revenue_waterfall`: the population is read by the PERFORMING entity — the entity whose books hold the obligation's revenue — where it was read by the contracting entity; "Entity" is the performing entity; the four consequences are stated (a run for the contracting entity alone; the `functional` and `reporting` views of an obligation in another currency than its performing entity's; the Home of such an entity; [J] what a reader of the performing entity alone sees of the contract). The tie-out's sentence stands and is now true of every run: the same entity on both sides. No parameter, column, format or chart changes; single-entity contracts are unchanged. |
| 1.77 | 2026-10-01 | lane F-CLO-WEB (item JRN-RETRY-FOLLOW-1 — a PRODUCT DEFECT older than rev 1.71, found by the lane with that item; the supervisor's assignment of 2026-10-01 12:31 and the lane's pre-build line; the API's part is lane F-CLO-A's item JRN-RETRY-CLAIMED-1, 04 §16.7 rev 1.221; docs first; number assigned by the supervisor, register index 145; row appended at the table's tail) | **Applied.** **§3.4 and §3.2 States.** The row's "Retry export" changed nothing on the page: its dialog owned the command and closed on the accepted answer, so the batch stayed "Failed" with "Retry export" beside it until the page was opened again. The frame now follows the job as it follows an exit — "Sending batch <batch> · <chunk> again", the actions hidden — and says the ending after the run is read again, of the batch as it then is: the toast "Batch <batch> · <chunk> was sent again." for a batch that left `failed`; the warning banner "Batch <batch> · <chunk> was not sent again" with the instant from the job's `result.waiting` for a batch whose message keeps its schedule; nothing beside the failed banner for a batch the ledger refused again; the negative banner with the job's sentence for a job that failed. The job ends `SUCCEEDED` in the first three, so no ending is read from its state. **§3.2.** The frame follows the run's active job without a mode also when it did not send the command, and reads the run again at its end: a reader who had not sent an export kept an Approved page over a run that was exported. "Journal run <run no> exported." is said only of a run the job exported, read again after it; it followed every job that had not failed. The export dialog's "Target" is the one adapter the run's batches were calculated for and the command sends it (04 rev 1.145): it sent `CSV` for every run, which the API refuses for a run of an ERP adapter. A request that gets no answer is said in the four older dialogs as in the two exit dialogs. Two endings of rev 1.71 were cut by the two lines DESIGN_SYSTEM DS-CMP-22 gives a toast: the hand-over's toast says the outcome alone, and a refused download is a banner of the frame with the API's sentence whole. On a Failed run the header's "Retry export" and the failed banner's link are not offered (the supervisor's ruling of 2026-10-01): they sent `export`, which sends nothing for a batch that has a message, and the page answered "exported"; the rows' "Retry export" are the way until lane F-CLO-A's item JRN-RUN-RETRY-1 makes `export` retry the failed batches of a run. No route changes; two test hooks added (`SF-06-banner-retry-not-sent`, `SF-06-banner-download-refused`) |
| 1.72 | 2026-10-01 | lane F-SNP (items REG-VERSION-WHOLE-SET-1 and CFG-PLATFORM-PIN-1; supervisor rulings R-115 (e) and R-117 (b) of 2026-09-30 and the supervisor's ruling of 2026-10-01 on the items' pre-build line; `docs/04-DATA_MODEL.md` rev 1.183; docs first; number assigned by the supervisor, register index 92; row appended at the table's tail) | **Applied.** §9.6 SF-15:workspace, Data bindings: the screen sends no `effective_from`, and the API refused every such submit ("Choose the date this version takes effect.") and left a tested version that closed its category to the next attempt. A version of the platform, close and integration categories now takes effect when it is approved and keeps the published values the request does not state; the sentence says so. The screen is unchanged. Its two list fields, which are shown and never sent, and a tested version left behind by an earlier refused attempt are lane F-ADM-WEB's |
| 1.81 | 2026-10-01 | lane F-CLO-WEB (two items in one head, register indexes 157 and 158: the screens of lane F-CLO-B's two reads — items CLO-QUARANTINE-READ-1 and CLO-LOCKS-READ-1, bound in rev 1.66 and 1.67 — and the order of the source-lines drawer, the lane's observation in its report of JRN-DRILL-CONTRACT-NAME-1; the supervisor's rulings of 2026-10-01 14:53 and 16:23 on the lane's pre-build lines; SCREENS rev 1.50; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** **§1.4, as built on the reads of rev 1.67.** "Approval" and the activity show the record's and the transition's `approval_request_no` to every reader — a link where the reader may read the request, text where not, a dash where the record states none. "Ledger head" has its tooltip, the prefix of the hash as text, and the drawer states the head with prefix, copy and full value. The record's drawer, now the wide variant, gains two static tables: "Certification" — "Gate", "Status", "Count", "Evaluated"; a waived gate with the second line "Waiver <request no>, <n> at approval"; a replayed gate result is not marked — and "Frozen datasets" — "Dataset", "Rows", "File hash", the twelve report titles in E-64 order. A permanent lock shows "Certification" alone, a reopen neither. **§1.1 and §1.2** are built as rev 1.66 bound them — BLK-02's link and the quarantined grid's read by `blocking` — and the `BLOCKED` banner of a run that states no count takes the count of that list. §1.2 gains the refusal of "Resume close run" for a run a newer one has superseded (lane F-CLO-B's item CLO-GATE-RUN-2; the supervisor's message of 2026-10-01 17:24): the API's sentence in the page's banner, and the runs read again. **§3.3, the source-lines drawer:** the columns stand in the order of the question the drawer answers — "Contract", "Debit or credit", "Amount (txn)", "Effective" in view without scrolling (608 of the grid's 686 px), then "Entry kind", "Posting kind", "Account role", "Amount (functional)", "FX rate", "Origin period", "Post-reopen", "Reason", "Recorded", "Actions". The drawer opened on four columns that read alike on every row, with the contract its one filter is about and the amount it explains beyond its width. "Contract" is the leading identifier column, pinned, its cell the row header; a line without a contract names its row "No contract" for assistive technology and keeps the dash. The three wireframe lines that drew the drawer's first columns are redrawn. "Obligation" stays unbuilt, owed to the API. No route, width, header or test hook changes; catalogue keys added for the two tables, the request number as text and the row name |
| 1.85 | 2026-10-01 | lane F-CLO-WEB (item JRN-RUN-ENDINGS-2: the lane's observations O4, O-a and O-b and its finding F4 in its report of JRN-RETRY-FOLLOW-1; the supervisor's rulings of 2026-10-01 17:24 and 18:22 on them and on the lane's pre-build line; docs first; number assigned by the supervisor, register index 194; row appended at the table's tail) | **Applied.** **§3.2.** The failed banner of a run opened on Summary or Lines has the link "Open batches": since rev 1.77 a Failed run has no command in its header, and the banner named no place for the retry. A job of the run's own export that failed or was cancelled said nothing and left the page as it was: it is told by a negative banner with the job's sentence and reference, in every frame that followed it — "Journal run <run no> was not exported", and over an Exported run "The export of journal run <run no> was not repeated"; a run the job exported all the same is told by the export's toast. History printed the audit action literal as its verb: the seven actions the journals domain records for a run have words, an event that did not succeed keeps the contract trail's form before the same phrase, and History is stated to list the run's own events — the decisions on its request are read on the request. **§2.2.** A 403 `forbidden` of a signature or of the reopen is shown in the record's refusal banner, whole, and no longer as a toast, which cut PRD ERR-01's two sentences after two lines. One test hook added (`SF-06-banner-export-not-done`); ten catalogue keys added; no route or permission changes |
| 1.79 | 2026-10-01 | lane WEB-QA (item W-12, slice c; the supervisor's ruling of 2026-10-01 14:09 on the slice's one open case; `docs/design/SCREENS.md` §0.6 SCR-PERM-02 (a), rev 1.30; docs first; number assigned by the supervisor, register index 131; row appended at the table's tail) | **Applied.** §3.1 SF-06, the "Run journals" form. Finding (a PRODUCT DEFECT against SCR-PERM-02): "Entities" offered every active entity and preselected the context entity whatever it was, so a member who holds `journal.run` for one entity only, on the journals page of another, pressed "Calculate journals" for an entity the API then refused. The row "Entities" states its options — the entities `journal.run` is held for — and its default — the context entity when it is one of them, otherwise none. A new paragraph states the entry (any entity), the read of the period list (`config.read` for the first chosen entity) and what the form shows and does with no entity chosen or no period listed, as measured: "Period" lists nothing, "Calculate journals" stays enabled, shows the two validation sentences as they apply and sends nothing. No route, parameter or copy changes. Also under this revision, by the supervisor's word of 2026-10-01 18:32 (no number of its own): SB-R-01 names the ranges SCR-URL-01 to SCR-URL-33 and SCR-ST-01 to SCR-ST-13 — `docs/design/SCREENS.md` rev 1.40 added SCR-URL-33 and its rev 1.47 adds SCR-ST-13, and the two ranges had stayed at -32 and -12 |
| 1.82 | 2026-10-02 | lane F-CLO-WEB (BUILD_SPEC RPS-19, first head — the revenue dashboard; the supervisor's rulings of 2026-10-01 14:53, 22:52 and 23:35 on the lane's pre-build line and its notes; `docs/design/DESIGN_SYSTEM.md` rev 1.12; docs first; number assigned by the supervisor, register index 159; row appended at the table's tail) | **Applied.** **§5.5, the revenue dashboard as built.** No report converts an amount in 1.0 and a run that names its period by key reads each entity on its own calendar, so the wireframe's "All entities … Currency (Reporting)" could not be drawn rightly in a world of several calendars or functional currencies. The page asks its four runs under the functional view in every context and shows the chip "Functional"; without an entity the panels are drawn only where the entities of the member's `report.run` scope that keep the book share one calendar and one functional currency, and otherwise no run is made and one banner says what differs, the flags panel staying. Stated as built: each panel's parameters; the category bars as DESIGN_SYSTEM DS-CH-06; the bridge's lines and its unbalanced banner; a refused run, said as SCREENS.md SCR-ST-13 says a refused command under the panel's own title; a failed run, a read that fails, an empty run and figures in several currencies; "Retry" and "Refresh"; the runs of another context leaving the address; the drills of the marks and of the flags; the permissions each panel is asked of; current figures, with "As locked" one "Open report" away. **§5.1.** The "Dashboards" list as built: the dashboards that are built, as links in the page's context. **§13.** The gallery's Data section lists `#DS-CH-06` with RPT-08 sample data. **§15.** The row of SF-08:dashboard opens the revenue dashboard without an entity and with `entity=AVM-US`, and no longer with `currency_view=reporting`. `close` stays X:not-found until the item's second head. Two test hooks added (`SF-08-dashboard-banner-scope`, `SF-08-page`); 29 catalogue keys added; one route built (RT-107); no permission changes |
| 1.90 | 2026-10-02 | lane F-RPS-REG (item S-1 of the lane's sweep under RPT-FORMER-GROUP-READERS-1; the supervisor's word of 2026-10-01 on the lane's sweep, after supervisor ruling R-117 (a); docs first; number assigned by the supervisor, register index 218; row appended at the table's tail) | **Applied.** §5.6.4 RPT-21: the row key names the version the row is read from by its number along the contract's chain, the number RPT-09 gives the same version since rev 1.58. Measured before, in the world of a combination (two orders, each computed in its own group, then combined): `allocation:SF-ORD-10417:O1:1` for the allocation of 117,000.00, the version RPT-09 states as `version:SF-ORD-10417:2:O1` — the key's 1 was the number of the order's version in its own group (108,000.00), which this report does not show. Now `allocation:SF-ORD-10417:O1:2`. A contract that never changed its group keeps its numbers. No column, amount, date, cause, order of rows, total or copy changes; nothing reads the number out of the key. |
| 1.94 | 2026-10-02 | lane F-SNP (item POLICY-WITHDRAW-ROUTES-1; the supervisor's ruling of 2026-10-02 on the independent review of the head, point 1; docs first; number assigned by the supervisor, register index 207; SCREENS rev 1.56; row appended at the table's tail) | **Applied.** §9.6 SF-15:workspace, "Regions and components" and "States". Measured in a browser on the dev stack: with a `TESTED` Platform version open, "Job concurrency" 4 to 5 was refused "Another version is open. Finish it or withdraw it first." and the form showed no such version — on main before this head; and a Close value submitted from the form, then withdrawn on its version's page as SCREENS rev 1.56 makes "Withdraw" work (the version is a `DRAFT` again), held every later Close change of the form the same way. The form now names the open version of a category with the link to its page and does not submit that category; the others go through. It does not reuse the open version, and no route deletes a draft. One message is new |
| 1.86 | 2026-10-01 | lane F-CLO-B (BUILD_SPEC CLO-17, the role basis; supervisor rulings R-69 and R-74 of 2026-09-30 and the supervisor's order of 2026-10-01 18:35 and ruling of 21:23; docs first; number assigned by the supervisor, register index 196; row appended at the table's tail) | **Applied.** §2.2 "Grid columns: totals by account": a row of a contract balance role shows the role's label with its accounts (`account_role`, `account_codes`), and a row the subledger does not state shows "Not stated", no difference, the reason, the contracts the reader reads and "and <n> contracts outside your entities" for the rest (`not_stated` with `contract_count`); the key figures strip adds "Not stated <n>". "Grid columns: differences": the kind `NOT_STATED` "Not stated by the subledger", and the role's label in "Account" for an item that names a role and no account. No wireframe, locator or test hook changes, and no screen file: 04 rev 1.253 states the members and the generated schema carries them |
| 1.97 | 2026-10-02 | lane F-CLO-B (item REC-GEN-LOCK-1's head, with which the API's sentence changed; the supervisor's words of 2026-10-02 02:51 and 06:32 on lane F-CLO-WEB's observation O1; number assigned by the supervisor, register index 211; row appended at the table's tail) | **Applied.** §1.2: the sentence a refused "Resume close run" shows for a run that a newer one has superseded ends "Run close again." — the words of the button that starts a run (04 §16.8 rev 1.259). The banner shows the API's sentence as it is sent, so no screen file changes; the fake of `frontend/src/routes/close/__tests__/close-run.test.tsx::a resume the API refuses says why, and the runs are read again` answers the sentence as it ends now. The clause of rev 1.81 is qualified by a clause of this revision and not rewritten |
| 1.92 | 2026-10-02 | lane F-CLO-WEB (item RPT-VIEW-CONTEXT-DEFAULT-1 with REPORT-RERUN-AFTER-REFUSAL-1; the supervisor's rulings of 2026-10-02 02:50, 03:43 and 04:10; `docs/design/SCREENS.md` rev 1.61; docs first; number assigned by the supervisor, register index 229; row appended at the table's tail) | **Applied.** **§0.5, "The context of a view".** SF-04 and SF-08:report read `entity`, `period` and `book` from the address alone, so an address without them was a report run over every entity in the member's scope without a period; SF-08:dashboard read a missing entity as all entities. The three screens now run for what the address says: an entity it names; every entity in scope where it says `entities=all`, with nothing filled; otherwise the context pill's entity, book and period, each filled only where the address leaves it out and written before a run is asked. The view is mounted once the address holds its context. Stated with it: a stored run in an address without a context keeps its run; the pill's change of entity or book, which takes the period out of the address — the period is filled and the earlier context's runs leave the address in the same write, where SF-08:report asked a run without a period before; a member without `config.read`; a read that fails while the address is filled; who writes `entities=all`; and the pill's entity outside the member's `report.run` scope. **§0.5 RV-01.** "Run report" cleared a refused creation and sent nothing, so the view stood empty; it now sends that creation again, and a set that changes with the press is sent once. **§4.1, §5.2.** The routes name `entities`; the run bindings say where `entity_codes` comes from; two states each: the context being filled, and the read that fails. **§5.3.** "Open report view" of a run of several entities says `entities=all`. **§5.5.** The dashboard follows (the supervisor's ruling of 03:43, Q1): its rule for a context without an entity is the rule for `entities=all`, and its links to the report views and to SF-04 say so. **§14.3.** The row of `entities`. **§15.** SF-04 opened from the rail without a context; `/reports/rpo` without a context; the dashboard under `entities=all`, without a context and with an entity. No test hook, copy key, route or permission changes |
| 1.93 | 2026-10-02 | lane F-CLO-WEB (the refused close commands, item O2 of the lane's report on the close screens, with the reason of a pending reopen request; the supervisor's rulings of 2026-10-01 23:35 and of 2026-10-02 02:50 and 03:43; docs first; number assigned by the supervisor, register index 236; row appended at the table's tail) | **Applied.** **§1.1, the pending reopen request.** API-S-Approval states the reason code a request was submitted with (04 §16.10 rev 1.252), so the banner names it, as rev 1.32 left it to: "Reopen requested by <name> on <DD MMM YYYY>: <reason label>. Dual approval · <n> of 2 recorded."; without a code, or with one this build has no label for, the sentence of rev 1.32 stands. **§1.1 and §1.2, a refused close command.** "Run close" and "Cancel close run" are offered by what the page has read, and the kit reads a command's keys again after a 412 and not after a 409: a refused "Run close" left the period under the chip and the commands of a state it was no longer in, and a refused "Cancel close run" left its dialog open with the command, on a blocked run that is never read again. Both now keep the API's sentence in the banner — the cancel's above the run, its dialog closed — and read the period and the runs again, as the refused resume does since rev 1.81; the states the period and the run can then be in, and what each offers, are stated. One copy key added (`close.cockpit.banner.reopenRequestReason`); no test hook, route or permission changes |
| 1.100 | 2026-10-02 | lane F-CLO-B (item CLO-RATE-AFTER-RUN-1; the supervisor's ruling of 2026-10-02 08:56 on the lane's pre-build line; docs first; number assigned by the supervisor, register index 272; row appended at the table's tail) | **Applied.** §1.1 gate label table, `CLOSE_RUN_COMPLETED`: one more failure detail — "Close run out of date, run it again: <what> changed since it ran. A run posts nothing where the change moves nothing for this entity." — <what> is "exchange rates", "policies" or "exchange rates and policies"; the remedy is "Run close", as for the gate's other details, and the second sentence states the price of a read that is the workspace's and not the entity's. The checklist row shows the detail the API sends, so no screen file, wireframe, locator or test hook changes (04 §16.8 rev 1.291) |
| 1.95 | 2026-10-02 | lane F-RPS-REG (head R28-READS; supervisor ruling R-28 and the supervisor's rulings of 2026-10-02 on the lane's measurement of its remainder; docs first; number assigned by the supervisor, register index 232; row appended at the table's tail; 04 rev 1.275) | **Applied.** §5.6.2 RPT-28 `judgement_register`: which records a run states, the control total `record_count` and the head line. Measured before: a run for AVM-DE, by a member of AVM-DE alone as by a member of all entities, stated the record of a combination of two orders of another entity with its conclusion, "Combine SF-ORD-10417, SF-ORD-10418." — every record without a contract of its own was in every run. A record of a product, a registry version or a migration batch still is. A record of a combination group is stated when the run's entities hold a contract of the group, and the proposal of a combination when they hold every contract it names; a run that holds some and not all does not state it and says so: `record_count` counts it beside `row_count`, and the head line names the difference. The run's entities stand for its readers, as for the requests of RPT-23 and RPT-26. No column, filter, order or empty copy changes. |
| 1.48 | 2026-10-02 | lane SECFIX-APR (supervisor ruling R-38 (iii); 04 rev 1.168; number assigned by the supervisor, register index 77; row appended at the table's tail) | **Applied.** §9.15 Data bindings: what `POST /api-clients` answers now — the secret only for a request approved at once; otherwise `PENDING_APPROVAL`, no secret and the request's id, the first secret by rotate-secret after the approval. §5.6.5 RPT-27: "Secret rotated" is "Secret issued" (empty text "Not issued"), and the columns "Approval", "Approved by" and "Approved" show each client's grant (CTL-037 evidence). The interim note of §9.15 on the entity scope states that the API admits entity codes now (item API-CLIENT-ENTITY-SCOPE-1). The permission note of §9: what `POST /periods/{id}/open` accepts once the completion conditions hold (04 T-PLT-01 rev 1.168). The status chips "Pending approval" and "Rejected", the create dialog's pending outcome, the "Issue secret" action and the entity choice are items of lane F-ADM-WEB and are not specified by this row. |
| 1.103 | 2026-10-02 | lane F-SNP (item ACCESS-LISTING-SECOND-LIFE-1; the supervisor's ruling of 2026-10-02 18:40 PDT on the independent review of the head of register index 273, finding M4, with the three points of lane F-RPS-REG on the as-of rule; docs first; number assigned by the supervisor, register index 289; row appended at the table's tail; 04 rev 1.307) | **Applied.** §5.6.5 RPT-24 Rows: a membership is removed at `as_of` by its row or, for a removal that a later invitation ended, by the audit trail. Measured before: after a second invitation an `as_of` inside the removal listed the person as a member without a role (`membership_count` 8 where 7; with removed members `assignment_count` 9 where 10). Stated with it, unchanged: `as_of` selects the memberships and their role assignments; the Membership chip and the person's cells are the values at the run's record cutoff, and a run on the `historical` basis whose cutoff precedes a later change of a membership in scope is refused by name. No column, parameter, copy or control total changes. |
| 1.98 | 2026-10-02 | lane F-CLO-WEB (item RV-AS-LOCKED-DEFAULT-1, a release blocker; the supervisor's rulings of 2026-10-02 07:48 and 09:15 on the lane's finding and its pre-build line; docs first; number assigned by the supervisor, register index 264; row appended at the table's tail) | **Applied.** **§0.5 RV-04, the default on a locked period.** Measured with the API's own function over the 56 report definitions: on a `closed` context period the default sent three views — `revenue_waterfall`, `modification_register` and SF-04 — a parameter set the API refuses, opened the seventeen views of reports that take a lock and have no dataset on the named refusal, and said "as locked" over current figures on the twenty-four views of reports that take no lock; the other ten frozen reports were admitted until a toolbar field was changed. Now: the default is a report's that has a lock dataset — the twelve of ENGINE_SPEC_B §15.2.7, read from a generated file — and every other report runs current figures there and says so, with "A period lock does not freeze this report."; an as-locked run asks the lock, its entity and book, the schema's period keys as the context period and a named `known_at`, nothing else; the toolbar's fields are shown and unavailable under "Figures as locked take no parameters. Show current figures to change them." — rev 1.4's "stays editable" goes, rev 1.17's "unavailable" stands; frozen rows draw no chart and `rpo` keeps its two sections; the banner's sentences are said of the context period's own lock only, and an address that names another lock is kept as written; on a `permanently_locked` period, whose current lock record holds no dataset, no report defaults to the lock or offers it (register index 280 measures that record with the API). RV-08 points to it; §4.1 states SF-04 as locked — the frozen table, with what the page should be beyond it left undesigned by ruling; §15 gains the rows of the closed world (`closed.spec.ts` under `make e2e CLOSE=1`, dev-guide rev 1.277), among them the cockpit of a locked month and the permanent-lock request of register index 268. Two copy keys added (`reports.asLocked.noParameters`, `reports.asLocked.notFrozen`); no route, permission or test hook changes |
| 1.99 | 2026-10-02 | lane WEB-QA (item W-12e, the supervisor's rulings of 2026-10-01 16:32 and of 2026-10-02 02:43, 08:35 and 08:52; `docs/design/SCREENS.md` §0.6 SCR-PERM-01 and SCR-PERM-02 (c), rev 1.71; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** The pages of the whole workspace. Finding (a PRODUCT DEFECT; SCREENS.md rev 1.71 states it and how it was measured): the rows "Roles and permissions" of ten sections named a permission and not for which entities it is asked, the screens asked for any, and the API asks for all. Each row now says so and gives the description of the access-limited state a holder for named entities reads, in which the permission is named by its phrase and, in parentheses, its code — the word the Roles screen prints for it, which the phrase alone ("managing workspace settings") is not; the description of a member without the permission names it the same way on these pages, and the audit log's sentences of rev 1.68 follow in §6.3: §9.6 Workspace settings (whose values `config.read` still reads), §9.7 Sandbox copies and "Reset sandbox", §9.13 Access reviews and a campaign, §9.14 Security and Support access, §9.15 the webhooks of the developer page and the reasons of its unavailable tabs, §10.3 a migration, §11.1 Workspace setup. §9.1: a link of the index, and a tab of a settings page, asks what its page asks, and the setup banner is the tenant's. §9.3: the setup branch of "Open period" asks `settings.manage` for all entities (the supervisor's ruling). §9.4: "Save currencies". §9.13: the reviewers "New campaign" offers are the holders of `access.approve` for all entities by a role of their own — the list offered every member whose role holds the permission, and the API answers 422 on one of named entities. §10.3: the description for a member without `migration.run` says "running migrations (migration.run)"; it named the words of `contract.read`. §10.1 and §10.2, whose routes are not built, follow §10.3 when they are. No route, parameter or test hook changes |
| 1.101 | 2026-10-02 | lane F-CLO-WEB (the web half of register index 280, a release blocker; the supervisor's order of 2026-10-02 16:20, rulings of 16:26 and 16:44 and message of 20:32; docs first; number assigned by the supervisor, register index 280; row appended at the table's tail) | **Applied.** **§0.5 RV-04, the lock whose datasets stand.** Measured by lane F-CLO-B: a permanently locked period's current lock is the permanent lock's record, which holds no dataset; a run given that record is created and fails, and the same run given the lock of the period's close succeeds, before and after the permanent lock. API-S-Period now names that lock as `dataset_lock` (04 §16.8), and a run that names a record that is not a LOCK is refused at its creation, and at its rerun, with the LOCK to pass. RV-04 takes `snapshot`, both sentences' time and the run stamp's "As locked on <timestamp>" from `dataset_lock`: on a permanently locked period a report that has a lock dataset opens as locked again, on the lock of the close and at the instant its figures were frozen; a locked period without such a lock has no default and no offer, as rev 1.98 said of every permanently locked period. An address that names the permanent lock's record is kept as written and meets the API's refusal; no address is rewritten. **RV-03 and §5.3, a refused rerun.** The drawer said a refused rerun's title alone and the run record its title and detail, so the sentence that names the lock to pass was shown nowhere; both now say the problem's title, its detail and every sentence of its findings, each once (DS-CMP-29, the `RefusalBanner` of DG-FE-06). §15: the closed world's cockpit rows run in one worker and end with the decision of a second Controller and the report of the permanently locked January (dev-guide DG-E2E-02 rev 1.285). No copy key, route, permission or test hook changes |
| 1.104 | 2026-10-02 | lane FIX-D2 (item RPT-ROLLFWD-LOCKED-CLOSING-1; the supervisor's rulings of 2026-10-02 on lane WEB-QA's measurement and on this lane's two lines — PRODUCT DEFECT: a report's own tie-out fails on the journey of the PRD; docs first; number assigned by the supervisor, register index 297; row appended at the table's tail; ENGINE_SPEC_B rev 1.168, 04 rev 1.313) | **Applied.** §5.6.1 RPT-02: at a period end locked at the run's cutoff the rows and figures of a current run are the lock's dataset; a contract activated after the lock is a row of the first period end that is not locked; the Explain drill is not offered at such an end; the refusal by name. §5.6.1 RPT-03: the opening and the closing are the locks' where the period before the range and its last period are locked, so a range of locked months and the period after it foot after a late activation; a billing document recorded after the lock of the period it is dated in is "Billings" of the first period whose end holds it (PRD J-04). §5.6.1 RPT-04: the opening is the lock's where the period before the range is locked. No route, permission, parameter, copy key or test hook changes |
| 1.102 | 2026-10-02 | lane SECFIX-APR (item POLICY-TENANT-SCOPE-ALL-ENTITIES-1; the supervisor's ruling of 2026-10-02 on lane F-SNP's measurement; docs first; number assigned by the supervisor, register index 291; row appended at the table's tail) | **Applied.** §9.6 SF-15:workspace, "Roles and permissions" and "States": the form states `TENANT` registry versions, which the API lets a member author only with `config.author` for all entities (04 §16.5 rev 1.309). The form's controls and "Submit for approval" are therefore for a holder of that permission for all entities; a holder for named entities sees the values read-only without a submit control, as a reader does. Before the item she was given the controls and her submission was accepted — the finding of 04 rev 1.309; with the API's refusal alone the form would have offered her a submit that is refused. No wireframe, label, locator or test hook changes |
| 1.105 | 2026-10-03 | lane F-SNP (item IDENTITY-WITHHELD-BY-STATUS-1; the supervisor's rulings of 2026-10-02 and 2026-10-03 on the lane's line; docs first; number assigned by the supervisor, register index 302; row appended at the table's tail; 04 rev 1.316) | **Applied.** §9.10 SF-14 and SF-14:user: for an invited or a removed member the grid's "MFA" and "Last login" read "Not shown" and the user page's Security section says that MFA and last sign-in are not shown — API-S-User `sign_in_withheld`; before, null printed "No" and "Never". §5.6.5 RPT-24 Rows: the two cells of an `INVITED` or `REMOVED` row are not shown — null in the data, empty in CSV, "Not shown" in XLSX and PDF — and go by the row's own Membership value; a historical run is not refused for a change of a person whose name is withheld, which "or of its person" did not say, and an erasure counts. §9.13 access reviews, Items: what the null of "Last login" means, and the limit that the item's screen prints "Never" for an invited member. An erased person reads by the erasure's label, whoever added them. No column and no parameter changes. |
| 1.106 | 2026-10-03 | lane SECFIX-PLT (item FX-REPUBLISH-DIRTY-1 — PRODUCT DEFECT, release blocker for a multi-currency workspace; the supervisor's word of 2026-10-03 on the lane's line; number assigned by the supervisor, register index 277; row appended at the table's tail; ENGINE_SPEC_B rev 1.166, 04 rev 1.297) | **Applied.** §5.6.3 RPT-16, Rows: the sentence that states the proof of a Trigger row gains the third condition of ENGINE_SPEC_B S15-R-18b — under `FX_REPUBLISH` the line's transaction amount is nil. The approval of an FX rate set version now marks the groups its changed rates reach and their recompute is stored under `FX_REPUBLISH`, so the register lists what a republication posts behind a lock as "Fx republish"; a line that moves a transaction amount under that trigger was not made by the republication: it is missing lineage and refuses the run by name (`OUT_OF_PERIOD_ATTRIBUTION_MISSING`). No column, label or parameter changes. |

**Table 1.2-A Applied.**

| Ruling or question | Change | Sections and ids |
|---|---|---|
| D-76 `SCREENS_B:OQ-B-01` to `OQ-B-32` | Each question marked resolved with its ruling | §18 Status column |
| API additions adopted by 04 rev 1.2 | Bindings cite the 04 ids and schemas: derived blockers (E-122); reason-code subsets (table 3.4-R); close run step statuses (E-62); multi-entity results; `gl_document_reference`; journal run summary and balance checks; tie-out codes (table 10-T); report parameters; disclosure pack; evidence pack creation; deal preview save; document text and accept (E-121); anomaly flags; AI kill switch; any-of setup permissions; preferences (E-123, E-124); identity providers; engine release; password and invitation commands | §1.1, §1.2, §1.4, §1.5, §2.2, §3.2, §4.1, §5.4, §5.6 (RV-05, RPT-R-01, RPT-R-08, RPT-33), §6.1, §6.2, §7.4, §8.2 to §8.5, §9 permission note, §9.2 to §9.4, §9.9, §9.14, §11.2, §11.3, §11.5, §12.3 |
| Parameters and fields 04 does not define | Deferred to later: journal run summary columns for role, clearing purpose, functional amounts and line count; evidence pack `kind` and `status` filters; AI call log filters; SF-23:select industry, roles and source columns; report grid header sorting. Adapted without deferral: recent report runs and earlier answers filtered on the client by creator; the verification page read by paging the list; run data sections through the new row field `section` (RPT-R-09) | §3.2, §5.1, §5.2, §5.6 RPT-R-09, §6.1, §6.4, §8.3, §8.6, §11.3 |
| Route reconciliation (SCREENS.md owns paths, D-73) | §14 rewritten as citations; SB-R-03 amended; the "(proposed, §14)" markers of screen id rows replaced by SCREENS.md §0.4 citations; "screen parameters, §14" citations replaced by SCR-URL ids | §0.1 SB-R-01, SB-R-03; §14; summary tables of §1 to §12 |
| D-76 `SCREENS_B:OQ-B-01` | "proposed" chip markers removed; the words are DS-CMP-19 rev 1.2 vocabulary | §0.4; §5.6 RPT-28; §6.3; §8.5; §8.6; §13 |
| D-76 `SCREENS_B:OQ-B-27`; DESIGN_SYSTEM DS-VER-06 | The tour popover cites DS-CMP-32; the gallery composition row names the route-error button | §11.2, §13 |

**Table 1.2-S Decisions taken in B3.**

| Id | Question | Decision | Rationale |
|---|---|---|---|
| B3-SB01 | 04 API-R-41 has no creator filter and no sort key for report runs | Recent runs read `created_from` 30 days back with `limit=50`, keep `run_by.id = user.id` and show the first 10 | Lists default to newest first (04 API-C-09, NC-04) |
| B3-SB02 | 04 API-R-47 has no creator filter for revenue Q&A answers | The same client-side filter over `limit=50` | As B3-SB01 |
| B3-SB03 | 04 defines no verification detail route and no `id` filter | SF-09:verification pages `GET /audit-events/verifications` until the id appears, else SCR-ST-07 | Uses the defined list only |
| B3-SB04 | API-S-JournalRunSummary returns account code, name, currency, debit and credit only | The summary grid shows those; a balance checks grid is added; the other columns are deferred to later; no client-computed totals row | DS-FMT-02; 04 B3-D20 |
| B3-SB05 | `GET /report-runs/{id}/data` has no `section` or `sort` parameter | Rows carry the field `section` (RPT-R-09); grids keep the response order; header sorting is deferred to later | This file owns report column contracts (M-DES-06) |
| B3-SB06 | `POST /deal-previews/{id}/save` requires `contract_external_id` | The save confirmation adds a required "Contract external id" field; the toast names that id | 04 §16.14 request |
| B3-SB07 | SF-23:select used membership fields that 04 API-S-Me does not return | Industry, Roles and Source columns deferred to later | 04 membership shape |
| B3-SB08 | Multi-entity close refusals now arrive as `results[].problem` | A refused entity keeps its existing run; 409 `invalid-transition` shows the existing-run toast; other problems show ERR copy in the row | 04 §16.8 response |

## Contents

| Section | Content | Screen ids |
|---|---|---|
| §0 | How to use this file: relationship to SCREENS.md, identifiers, part-B conventions, status chips for part-B literals, report viewer contract, coverage | none |
| §1 | Close cockpit, close run, journal preview, history, soft close, lock, reopen, permanent lock, multi-entity close | SF-05, SF-05:close-run, SF-05:journal-preview, SF-05:history, SF-05:multi-entity |
| §2 | Reconciliations: billing to subledger, subledger to GL, sign-off | SF-05:reconciliations, SF-05:reconciliation |
| §3 | Journal runs, run detail, lines, batches, acknowledgements, entries by date range | SF-06, SF-06:run, SF-06:run-lines, SF-06:run-batches, SF-06:entries |
| §4 | Schedules (revenue waterfall) | SF-04 |
| §5 | Reports catalogue, report view, run record, disclosure pack, dashboards; every 1.0 report specification | SF-08, SF-08:report, SF-08:run, SF-08:disclosure-pack, SF-08:dashboard |
| §6 | Evidence packs and auditor requests, audit log, chain verification | SF-09, SF-09:pack, SF-09:audit-log, SF-09:verification |
| §7 | Scenarios, forecasts and the deal-desk allocation preview | SF-17, SF-17:event-set, SF-17:run, SF-18 |
| §8 | AI: contract review, revenue Q&A, proposed narratives, anomaly flags, AI settings, call log | SF-20:new, SF-20, SF-28, SF-15:ai, SF-15:ai-call-log |
| §9 | Settings: index, entities, calendars and periods, currencies and rates, chart of accounts, workspace settings, sandbox copies, notification preferences, profile; users, roles, separation of duties, access reviews, security, support access; developer settings | SF-15, SF-15:entities, SF-15:calendars, SF-15:currencies, SF-15:chart-of-accounts, SF-15:workspace, SF-15:sandbox, SF-15:notifications, SF-15:profile, SF-14, SF-14:user, SF-14:roles, SF-14:sod, SF-14:access-reviews, SF-14:access-review, SF-14:security, SF-14:support-access, SF-16:developer |
| §10 | Legacy migration: database import, replay, reconciliation, promotion | SF-19, SF-19:new, SF-19:detail |
| §11 | Onboarding: workspace setup, guided tour, workspace selection and demo tenants, legacy transition map, About | SF-15:setup, SF-25, SF-23:select, SF-26, SF-27 |
| §12 | Authentication and error pages | SF-22, SF-22:mfa-challenge, SF-22:mfa-enrol, SF-22:password-change, SF-22:accept-invitation, SF-22:password-reset, SF-22:password-reset-confirm, X:session-expiring, X:route-error, X:narrow-viewport |
| §13 | Design gallery composition | X:design |
| §14 | Route and parameter citations | none |
| §15 | Screen audit list for `screens.spec.ts` | all part-B screens |
| §16 | Journey coverage | none |
| §17 | Gaps closed | none |
| §18 | Open questions for supervisor | none |

## 0. How to use this file

### 0.1 Relationship to SCREENS.md

- **SB-R-01.** SCREENS.md §0 applies to every screen of this file without restatement: identifier families (§0.1), information architecture and area tabs (§0.3), route table (§0.4), URL parameters SCR-URL-01 to SCR-URL-33, permission gating SCR-PERM-01 to SCR-PERM-07 (including the step-up modal of SCR-PERM-05), common states SCR-ST-01 to SCR-ST-13, status chips (§0.8), test hooks SCR-TID-01 to SCR-TID-05, legacy hooks SCR-LTH-01 to SCR-LTH-O5, wireframe notation SCR-WF-01 to SCR-WF-03, screen codes SCR-IA-07. This file adds only the rules in §0.3 to §0.5.
- **SB-R-02.** Every screen section uses the SCREENS.md sub-structure, in this order: summary table; wireframes at 1440 px and 1280 px; regions and components; data bindings; grid columns; states; interactions, keyboard and copy; sample-world content; test hooks; light and dark notes; accessibility notes. Dialogs and drawers opened from a screen are specified inside that screen's section and give one wireframe, because SCR-WF-03 fixes their 1280 px behaviour.
- **SB-R-03.** Screen ids of this file are those the SCREENS.md index assigns to SCREENS_B. Every one has a route row or placement row in SCREENS.md §0.4, which owns its path, title and read permission (D-73). This file cites those rows (§14) and restates paths only as reading aids; where a restated path differs, SCREENS.md §0.4 governs. Route objects follow SCR-IA-06 (`id`, `handle`).
- **SB-R-04.** Figures under "Sample world" are PRD §2 values. A figure marked "asserted" is a journey acceptance value; figures shown in wireframes that the PRD does not fix are layout content, not asserted (SCREENS.md §0.2).

### 0.2 Identifier families added by this file

| Family | Format | Meaning |
|---|---|---|
| Part-B rule | `SB-R-nn` | A convention of this file |
| Report viewer rule | `RV-nn` | Common report behaviour (§0.5) |
| Report specification | `RPT-nn` | One 04 T-RPT-01 report code (§5.6) |
| Close blocker | `BLK-nn` | One cockpit blocker row (§1.1) |
| Open question | `OQ-B-nn` | §18; resolved by D-76 (rev 1.2); the ids stay listed with their rulings and are never reused |

### 0.3 Part-B conventions

| Id | Convention | Authority |
|---|---|---|
| SB-R-05 | **High-risk confirmations.** Lock, reopen, void, reject, cancel journal run, waive or dismiss an exception, apply or release a hold, request an SoD exception, end soft close, revoke an API client and suspend or remove a member use DS-CMP-11 confirmation with a reason field of at least 10 characters (help text "Minimum 10 characters"; error "Enter at least 10 characters."). Initial focus is "Cancel"; the command button is Danger. | BR-PLT-08; DS-CMP-11; DS-CMP-21 |
| SB-R-06 | **Job progress labels.** DS-CMP-24 indicators and toasts use the labels below; SCR-ST-12 applies on failure. | DS-CMP-24; NTF-05 |
| SB-R-07 | **Report cells explain.** A report figure opens Explain through `GET /explain/report-runs/{id}/cell` (API-R-49), which lists contributors; a single contributor opens its own `/explain` tree in the Explain panel of SCREENS.md §6. A bound live run's explanation resolves against the run's bound sources (04 §16.11 rev 1.55; S15-R-24); an unbound live run's returns 404 `not-found` by name, shown as the problem copy in the Explain panel (rev 1.19). | REQ-RPT-017; DG-FE-15 |
| SB-R-08 | **Sandbox restrictions.** In a sandbox tenant, commands that post or export (journal export, adapter activation, webhook activation) render with `aria-disabled="true"` and the reason line "Sandbox workspaces cannot post or export journals." (ERR-17; SCR-PERM-03); CSV downloads stay available. The test of a connection (SF-16:connection "Test connection") renders the same way for every adapter that calls out — every adapter but CSV GL export — with the reason line "A connection cannot be tested in a sandbox workspace: a sandbox reaches no external system." (rev 1.74; 05 SBX-08 rev 1.116; SCREENS §14.4). The drawer "Add connection" of SF-16 offers in a sandbox what the API accepts there — the adapters NetSuite, QuickBooks Online and CSV GL export with the direction "Outbound"; no Salesforce or Stripe connection and no inbound or two-way direction — and its Adapter help says so (rev 1.80; SCREENS §14.4). | SBX-08; REQ-PLT-022 |
| SB-R-09 | **Money.** Grids show numbers with the ISO code in the header; outside grids `USD 1,234.56`; negatives follow `ui.negative_number_style` (default parentheses); totals come from the API. Wireframes use the parentheses style. | DS §6; D-75 PRD Q8 |
| SB-R-10 | **Labelled balances.** No screen of this file shows a signed contract position. Where a PRD acceptance speaks of a "debit net position", the screen shows "Contract asset and unbilled receivable"; legacy exports keep their legacy column names and sign (D-33). | D-12; DS-FMT-28; DS-CPY-02 |
| SB-R-11 | **Package paths.** Screen modules live at `frontend/src/routes/<area>/<screen>.tsx` with areas `close`, `journals`, `schedules`, `reports`, `evidence`, `forecasts`, `deal-preview`, `ai`, `settings`, `access`, `developer`, `migrations`, `onboarding`, `auth`, `errors`; message keys use the same area names. | DG-READ-02; DG-FE-11 |

| `job_kind` | Label |
|---|---|
| `CLOSE_RUN` | "Close run for <entity code> <period label>" |
| `JOURNAL_RUN_CALCULATE` | "Calculating journals for <entity code> <period label>" |
| `RECONCILIATION_GENERATE` | "Generating <kind label>" (rev 1.27; 04 E-14 rev 1.121) |
| `PERIOD_OPEN_REDIRTY` | "Re-marking contracts for <entity code> <period label>" (rev 1.38; 04 E-14 rev 1.164) |
| `JOURNAL_EXPORT` | "Exporting journal run <run no> to <adapter label>" |
| `REPORT_RUN` | "Running <report name>" |
| `EVIDENCE_PACK` | "Building evidence pack <pack no>" |
| `AUDIT_CHAIN_VERIFY` | "Verifying the audit chain" |
| `TENANT_SNAPSHOT` | "Copying <tenant name> to a sandbox" |
| `SANDBOX_RESET` | "Resetting sandbox <tenant name>" |
| `MIGRATION_IMPORT` | "Importing legacy database <migration no>" |
| `MIGRATION_RECONCILE` | "Reconciling migration <migration no>" |
| `POLICY_SIMULATION` | "Simulating <version name>" |
| `FORECAST_RUN` | "Running forecast <event set name>" |
| `DEAL_PREVIEW` | "Computing deal preview" |
| `AI_TASK` | "Generating proposal" |
| `SYNC_RUN` | "Syncing <connection name>" |

### 0.4 Status chips for part-B literals

This table extends SCREENS.md §0.8 with the literals shown on part-B screens. Every chip word below is DS-CMP-19 vocabulary as of DESIGN_SYSTEM rev 1.2, which adopted the words this table first proposed (OQ-S-12, OQ-B-01, resolved by D-76); the tone and icon columns repeat DS-CMP-19 as a reading aid, and DS-CMP-19 governs. Where SCREENS.md §0.8 already maps a literal (E-05, E-12, E-40, E-44, E-72, T-INT-01), that row governs.

| Enum or state | Literal | Chip | Tone and icon |
|---|---|---|---|
| E-04 `period_state` | `open` / `closing` / `closed` / `reopened` | Period open / Soft close / Locked / Reopened | DS-CMP-19 |
| E-04 | `future` | Future | neutral, CalendarBlank |
| E-04 | `permanently_locked` | Permanently locked | neutral, LockSimple |
| E-62 `close_run_status` | `PENDING` / `RUNNING` / `SUCCEEDED` / `FAILED` | Queued / Running / Succeeded / Failed | DS-CMP-19 |
| E-62 | `BLOCKED` | Blocked | warning, PauseCircle |
| E-62 | `CANCELLED` | Cancelled | neutral, Prohibit |
| E-60 `checklist_status` | `NOT_STARTED` | Not started | neutral, Circle |
| E-60 | `IN_PROGRESS` | In progress | info, CircleHalf |
| E-60 | `PASSED` | Passed | positive, CheckCircle |
| E-60 | `FAILED` | Not passed | negative, XCircle |
| E-60 | `WAIVED` | Waived | neutral, CheckCircle |
| E-60 | `NOT_APPLICABLE` | Not applicable | neutral, Minus |
| E-59 `reconciliation_status` | `DRAFT` / `CERTIFIED` / `REOPENED` | Draft / Reconciled / Reopened | DS-CMP-19 |
| E-59 | `PREPARED` | Prepared | info, HourglassMedium |
| E-59 | `AUTO_CERTIFIED` | Auto-certified | positive, CheckCircle |
| E-59 | `REVIEWED` | Reviewed | positive, CheckCircle |
| Reconciliation with `variance_count > 0` and not certified | second chip | Difference | DS-CMP-19 |
| E-34 `journal_state`, SMAP-05 calculating | `draft` with `JOURNAL_RUN_CALCULATE` job `QUEUED` or `RUNNING` | Running, caption "Calculating" | DS-CMP-19 |
| E-34, SMAP-05 calculated | `draft` without a pending request | Calculated | neutral, PencilSimpleLine |
| E-34, SMAP-06 | `draft` with `JOURNAL_RUN` request `PENDING` | Pending approval, caption "Submitted" | DS-CMP-19 |
| E-34 | `approved` / `exported` / `failed` | Approved / Exported / Failed | DS-CMP-19 |
| E-34, SMAP-07 | `approved` with `JOURNAL_EXPORT` job `QUEUED` or `RUNNING` | Running, caption "Exporting" | DS-CMP-19 |
| E-34, SMAP-08 | run `exported` with at least one batch `acknowledged` | Exported, caption "Partially acknowledged: <n> of <m> batches" | DS-CMP-19 |
| E-34 | `acknowledged` | Posted | DS-CMP-19 |
| E-34 | `cancelled` | Cancelled | neutral, Prohibit |
| E-67 `run_status` | `QUEUED` / `RUNNING` / `SUCCEEDED` / `FAILED` | Queued / Running / Succeeded / Failed | DS-CMP-19 |
| Tie-out result (T-RPT-02) | `PASS` | Pass | positive, CheckCircle |
| Tie-out result | `FAIL` | Difference | DS-CMP-19 |
| Tie-out result | `NOT_APPLICABLE` | Not applicable | neutral, Minus |
| E-98 `control_result` (chain verification) | `PASS` | Verified | positive, ShieldCheck |
| E-98 | `FAIL` | Verification failed | negative, XCircle |
| E-76 `migration_status` | `UPLOADED` / `PROFILING`, `IMPORTING` / `RECONCILED` / `SUBMITTED` / `FAILED` | Queued / Running / Reconciled / Pending approval / Failed | DS-CMP-19 |
| E-76 | `PROFILED` | Profiled | info, CheckCircle |
| E-76 | `IMPORTED` | Imported | info, CheckCircle |
| E-76 | `PROMOTED` | Promoted | positive, CheckCircle |
| E-76 | `CANCELLED` | Cancelled | neutral, Prohibit |
| E-74 `ai_proposal_status` | `proposed` / `failed` | Proposed / Failed | DS-CMP-19 |
| E-74, SMAP-11 | `proposed` with `AI_PROPOSAL_ACCEPTANCE` request `PENDING` | Pending approval | DS-CMP-19 |
| E-74 | `accepted` | Accepted | positive, CheckCircle |
| E-74 | `rejected` | Dismissed | neutral, Prohibit |
| E-74 | `expired` | Expired | neutral, ClockCounterClockwise |
| E-78 `membership_status` | `ACTIVE` | Active | DS-CMP-19 |
| E-78 | `INVITED` | Invited | info, HourglassMedium |
| E-78 | `SUSPENDED` | Suspended | warning, PauseCircle |
| E-78 | `REMOVED` | Removed | neutral, Prohibit |
| E-102 `user_status` | `LOCKED` | Account locked | warning, LockSimple |
| SMAP-14 role assignment | requested / active | Pending approval / Active | DS-CMP-19 |
| SMAP-14 | revoked | Revoked | neutral, Prohibit |
| E-96 `grant_status` | `REQUESTED` / `APPROVED` / `REJECTED` | Pending approval / Approved / Rejected | DS-CMP-19 |
| E-96 | `REVOKED` / `EXPIRED` | Revoked / Expired | neutral, Prohibit / neutral, ClockCounterClockwise |
| E-107 `access_review_status` | `DRAFT` | Draft | DS-CMP-19 |
| E-107 | `IN_REVIEW` / `COMPLETED` / `CANCELLED` | In review / Completed / Cancelled | info, CircleHalf / positive, CheckCircle / neutral, Prohibit |
| E-108 `access_review_decision` | `PENDING` / `CERTIFIED` / `REVOKE_REQUESTED` / `REVOKED` | Pending review / Certified / Revocation requested / Revoked | info, HourglassMedium / positive, CheckCircle / warning, WarningCircle / neutral, Prohibit |
| E-103 `api_client_status` | `PENDING_APPROVAL` / `ACTIVE` / `REJECTED` | Pending approval / Active / Rejected | DS-CMP-19 (rev 1.59: `PENDING_APPROVAL` and `REJECTED`, the literals of ruling R-113 (e)) |
| E-103 | `REVOKED` | Revoked | neutral, Prohibit |
| E-97 `webhook_delivery_status` | `PENDING` / `SUCCEEDED` / `FAILED` | Queued / Succeeded / Failed | DS-CMP-19 |
| E-97 | `ABANDONED` | Abandoned | neutral, Prohibit |
| E-100 `scenario_status` | `ACTIVE` | Active | DS-CMP-19 |
| E-100 | `ARCHIVED` | Archived | neutral, Prohibit |
| E-16 `tenant_kind` | `sandbox` | Sandbox | DS-CMP-19 |
| E-101 `tenant_status` | `ARCHIVED` | Archived | neutral, Prohibit |
| E-43 `exception_severity` on anomaly flags | `WARNING` | Warning | DS-CMP-19 |

Classifications (outline variant, no icon) used here: "Automatic", "Manual" (checklist gate kind); "Gross", "Delta" (journal mode); "Legacy v1" (templates); "Opening balances", "Replay" (migration mode); "Close", "Contract sample", "Change", "Access" (evidence pack kind); "High risk" (reconciliation item); "Setup grant" (BR-PLT-02); "Check" (low-confidence AI field, BR-AI-01); "Uncited figure" is a warning chip (DS-CMP-25).

### 0.5 Report viewer contract

Every report surface follows these rules: SF-08:report, SF-04, SF-06:entries, SF-08:disclosure-pack sections, SF-08:dashboard panels, registers opened from SF-09, SF-17:run outputs and the SF-19:detail reconciliation.

| Id | Rule |
|---|---|
| RV-01 | **One run per view.** Opening a report with a parameter set creates a report run (`POST /report-runs` with `output_format = JSON`; 202; job `REPORT_RUN`) and renders `GET /report-runs/{id}/data`. Changing parameters and pressing "Run report" creates a new run. A URL that carries `run=<report run uuid>` renders that stored run and creates none (BR-RPT-01; REQ-RPT-002). `run` is SCREENS.md SCR-URL-16. A refused creation (`POST /report-runs` answered with a problem, so no run exists) shows its problem only while the view stays on the parameter set and source it was attempted for and displays no `run`; a stored run rendered from `run=`, including one opened by a later `run` navigation in the same mounted view, never shows it; a context change or "Run report" clears it (rev 1.6; D-90e L9-PLT-Q-6). "Run report" also asks again: on the parameter set of a refused creation it sends that creation once more, and a set that changes with the press is sent once, as the address then holds it (rev 1.92; item REPORT-RERUN-AFTER-REFUSAL-1). |
| RV-02 | **Run stamp.** Directly under the report `h1`, a DS-CMP-06 meta row shows, in order: "Report" `<name> v<version>`; "Run" `<report run no>` (mono, copy button); "Entity" `<codes>`; "Book" `<book label>`; "As of" `<DD MMM YYYY>`; "Source" `As locked on <DD MMM YYYY HH:mm UTC>` or `Current, known at <DD MMM YYYY HH:mm UTC>`; "Engine" `<engine_version>` (tooltip: first 8 characters of `build_sha`); "Run by" `<name>`; "Run at" `<DD MMM YYYY HH:mm UTC>`; "Rows" `<count>`; "Output SHA-256" (first 8 and last 4 characters, copy button, DS-FMT-23). Test hook `<SF id>-run-stamp`; the run number, run time and hash carry `data-volatile`. |
| RV-03 | **Run details drawer.** "Run details" (secondary button beside the export menu) opens a DS-CMP-09 docked panel (480 px, `drawer=run-details`, SCR-URL-12) listing every API-S-ReportRun field: parameters (every key and value, including defaults); entity scope; `known_at` and its basis (`known_at_basis`: "As of the supplied cutoff" for `historical`, "Recorded by the run" for `record`, "basis: record (pre-parameter run)" for a run stored before the parameter; rev 1.18); `period_lock_id`; engine release; control totals (key, value); tie-out results (chip, expected, actual); ledger heads (book, `chain_seq`, `seal_sha256` prefix); output format; output SHA-256; manifest link; sources (rev 1.19; API-S-ReportRun `sources`, 04 §16.9 rev 1.55; by `kind`: "Bound: <versions> contract versions, <labels> grouping labels, <members> memberships, <rows> rows, cutoff <datetime>" for `bound`, "Retained inputs — a same-source rerun rebuilds from the run's retained evidence" for `retained`, "Open (no same-source support yet) — a rerun is a new live evaluation" for `open`, "Frozen dataset (as locked)" for `as_locked`, "Pending (not yet captured)" for `pending`, "Failed before capture — a rerun is a new evaluation" for `failed_without_capture`, "Unbound (created before source binding) — rerun and cell explanation unavailable" for a `legacy_unbound` run of an `adapter` / `retained_inputs` builder and "Unbound (created before source binding) — a rerun is a new live evaluation" for a `legacy_unbound` run of an `open` builder (`sources.strategy`); an `open` list renders as "Not bound: <items>" beneath); started and finished times; problem. Button "Rerun from the same source" (`POST /report-runs/{id}/rerun`; 202) shows the job result as two lines "Output identical: Yes" and "Control totals identical: Yes" (CTL-029; J-15.6). On a `legacy_unbound` run of an `adapter` / `retained_inputs` builder the button is disabled and carries the "Unbound…" copy (409 `invalid-transition` if invoked); on a `failed_without_capture` run, an `open` run or an `open` builder's `legacy_unbound` run (`sources.strategy` `open`) it reads "Rerun (new evaluation)" (rev 1.19; S15-R-24; Codex 2154 / 2216 / 2225). **Rev 1.101 (register index 280).** A refused rerun is shown as a refused command is: the problem's title, its detail and every sentence of its findings, each once (DS-CMP-29, the `RefusalBanner` of DG-FE-06). Before, the drawer said the title alone. Since S15-R-19 rev 1.167 the API refuses the rerun of a stored run that names a record which froze no dataset — a permanent lock's or a reopen's — as it refuses such a run's creation, and the lock to pass stands in the finding alone (RV-04). |
| RV-04 | **As locked.** For a `closed` or `permanently_locked` context period the source defaults to "As locked" — since rev 1.98 for a report that has a lock dataset, where the period's current lock record holds datasets, and for no other (below): the screen sets SCR-URL-06 `snapshot`, whose value on report screens is the `period_lock.id` of the context entity, book and period (OQ-B-04), and passes it as `period_lock_id`. The SCR-URL-06 banner "Showing <period label> as locked on <timestamp>." offers "Show current figures", which removes `snapshot` and shows the info banner "Showing current figures. <period label> was locked on <timestamp>." with the action "Show as locked" (BR-RPT-02). While the lock is the source "Run report" posts `period_lock_id` = the snapshot and "Run details" keeps "Rerun from the same source"; running, exporting and rerunning a report are not command controls under SCR-ST-10 (rev 1.4; D-90; D-88 L7-3-Q-2). Rev 1.4 also kept the parameters toolbar editable; rev 1.98 ends that (below). Run semantics (rev 1.17; D-98 candidate 96; ENGINE_SPEC_B S15-R-19): an as-locked run reads the lock's frozen dataset of the report's E-64 kind and no live table — the CSV export is the frozen file itself; the on-screen (JSON) grid and the XLSX / PDF exports render the frozen rows as text columns under the same headers; a report without a lock dataset kind (for example `revenue_from_opening_liability`, the extracts, the packs) or a lock without that kind's snapshot returns the named refusal (RV-14 shows it) instead of current figures under an "as locked" label; the cell explainer is not offered on an as-locked run. An as-locked run is of the lock's entity, book and period: the screen's entity / book / period selectors must match the chosen lock (a mismatch is the named refusal on RV-14, never the whole frozen dataset under the requested scope), every other filter, dimension, view or band control is unavailable for an as-locked run, and the run's scope shown on RV-02 / RV-03 is the lock's. Readers see an as-locked run only within the lock's entity; a run whose stored scope — entity, book, period or any extra selector — differs from its lock's is shown to no one, in the list and on RV-02 / RV-03 / the data grid / every export and the cell explainer alike, whatever its status and whenever it ran (rev 1.17, CLO8-SCOPE-R1; Codex 1622 residual). **Rev 1.98 (item RV-AS-LOCKED-DEFAULT-1; register index 264).** *The default is a frozen report's.* A lock freezes the twelve reports of the kinds table (ENGINE_SPEC_B §15.2.7). The screen reads which they are from a file written from the API's own table and held to it by a test (dev-guide DG-FE-18), until API-S-ReportDefinition states it. On a `closed` context period such a report defaults to "As locked", as before. On a `permanently_locked` one no report does: the period's current lock record is the permanent lock's, which holds no dataset of its own (04 T-CLS-04) — a run that names it ends in the API's "Lock <id> holds no <kind> dataset for <code>." — and API-S-Period names that record alone. Until the API names the datasets that stand (register index 280) every report runs current figures there, and the banner is the current sentence without "Show as locked" — for a report the lock froze without a second line, since a lock did freeze it. Every other report opens on current figures on any locked period and writes no `snapshot`: the banner reads "Showing current figures. <period label> was locked on <timestamp>." with the line "A period lock does not freeze this report." and no action. Before, every report defaulted: one that takes `period_lock_id` and has no lock dataset opened on the named refusal, and one that takes no lock ran current figures under "Showing <period label> as locked on <timestamp>." *What an as-locked run asks.* The lock, the context entity and book, each period key of the report's schema (`period_key`, `from_period_key`, `to_period_key`) as the context period, and a `known_at` the address names — nothing else: no `as_of`, no date, no `currency_view` and no `p.<key>`. The export menu's runs ask the same. Before, the view sent its §5.6 defaults beside the lock, which the API refuses by name: `revenue_waterfall`, `modification_register` and SF-04 opened on that refusal. *The toolbar.* While the lock is the source every field of RV-08 is shown and unavailable (DS-CMP-21 disabled; each option of a segmented control with the reason as its tooltip), and the toolbar is described by the sentence under it: "Figures as locked take no parameters. Show current figures to change them." "Run report", the export menu and "Rerun from the same source" stay. On SF-04 "From" and "To" both show the lock's period, "Layout" stays, and "Run report" writes no range into the address. *The frozen rows.* The grid shows the lock's dataset as it is — the columns of the frozen header, every cell text; `rpo` keeps its two sections, by the `section` each frozen row states — and no chart is drawn from frozen rows, on SF-08:report or on SF-04: the waterfall's dataset is one row per obligation of the lock's one period and holds no revenue by period. *Which lock.* The banner's two sentences name the context period and its lock's time, so they are said only while the address names the context period's own lock and that lock holds datasets — the default's case and "Show as locked". An address that names another lock — one written by hand, the record of a permanent lock, or the link of a stored as-locked run whose parameters name no `period_key`, once the context is filled around it ("The context of a view") — is kept as written: a run it asks carries that lock beside the view's own parameters, and the API answers (RV-14); neither sentence is shown, the toolbar stays available, and RV-02's "Source" states what the run on the page is — "As locked" without a time where its lock is not the context period's. A `snapshot` beside a report that takes no lock is sent nowhere, and the banner is the current one. **Rev 1.101 (register index 280; the supervisor's order of 2026-10-02 16:20, rulings of 16:26 and 16:44 and message of 20:32; 04 §16.8 API-S-Period `dataset_lock`).** *The lock of this row is the lock whose datasets stand.* API-S-Period names it as `dataset_lock`: the period's current lock while the period is `closed`; on a `permanently_locked` period the LOCK the permanent lock sealed; null where no LOCK record exists, and under a reopen. Wherever this row named the context period's lock it names that lock: `snapshot` takes its id, both sentences of the banner and RV-02's "As locked on <timestamp>" say its time — the instant the period's figures were frozen at, on a permanently locked period too, and not the instant of the permanent lock — and "Show as locked" is offered where it is not null. So on a `permanently_locked` period a report that has a lock dataset defaults to "As locked" again, on the lock of the period's close, and rev 1.98's "no report does" there ends. A locked period whose `dataset_lock` is null has no default and no offer: every report runs current figures and the banner is the current sentence, with the time of the record that locked the period. *An address that names the permanent lock's record* is another lock and is kept as written (rev 1.98 "Which lock"): the API refuses the run at its creation — "Lock <id> is the permanent lock of <period key>: it froze no dataset (E-63 PERMANENT_LOCK). The datasets of <period key> are those of lock <id>; pass that lock." — and RV-14 shows that sentence. Before rev 1.98 these screens wrote that record into the address themselves on a permanently locked period, so a stored link of that kind meets the refusal now; the screen rewrites no address. The rerun of a run stored with such a record is refused in the same words, in RV-03's drawer and on the run record (§5.3). |
| RV-05 | **Tie-out strip.** Reports with tie-outs show, below the run stamp, the heading "Tie-outs (<n> pass, <m> fail)" and one row per `tie_out_results` item: chip (§0.4), tie-out name, "Expected <currency> <amount>", "Actual <currency> <amount>", and "Difference <currency> <amount>" when failing. Tie-out codes are 04 table 10-T literals; §5.6 names the codes of each report (OQ-B-02 resolved by D-76). |
| RV-06 | **Exports.** The export menu (DownloadSimple, label "Export") lists only the definition's `output_formats`: "Excel workbook (XLSX)", "CSV with manifest", "PDF", "JSON", "ZIP archive". Choosing one creates a run with the same parameters and that `output_format` (permission `report.export`; `evidence.export` for packs), shows DS-CMP-24 in the menu row, and on success downloads `GET /report-runs/{id}/output`. Toast "Exported <report name> as <format>. Run <report run no>." with the action "Run details". |
| RV-07 | **Stamped outputs.** XLSX and PDF outputs carry a header block of the RV-02 fields plus every parameter, the control totals and the output SHA-256; XLSX amounts are numeric cells with the DS-FMT-26 number format; CSV outputs ship a JSON manifest (`row_count`, `control_totals`, `sha256`) and use DS-FMT-25 raw values; text cells starting with `=`, `+`, `-`, `@`, tab or carriage return are prefixed with an apostrophe (REQ-SEC-011). |
| RV-08 | **Parameters toolbar.** Parameters sit above the grid in one wrapping row: the report's parameters in §5.6 order, then "Run report" as the primary button of the region. Validation reports on submit (DS-CMP-21), for example "Start period must be on or before end period." (REQ-RPT-012). Rev 1.98: while a lock is the source the fields are shown and unavailable, and the toolbar says why (RV-04). |
| RV-09 | **Drill-through.** A drillable cell renders as a grid link (DS-CMP-10). Enter or click calls SB-R-07; when all contributors are one object type, the §5.6 drill target opens with filters; otherwise the Explain panel lists contributors. Esc returns focus to the originating cell (REQ-UX-009; J-16.6). |
| RV-10 | **Chart and table.** Reports with a DS chart (DS-CH-01, DS-CH-02, DS-CH-03) show a DS-CMP-14 chart panel above the grid with the view switch "Chart" / "Table" (DS-CMP-31); the grid is always present (DS-VIZ-00). |
| RV-11 | **Large runs.** The grid pages through `GET /report-runs/{id}/data` in 200-row pages (DG-FE-07). The status footer reads "<row count> rows". |
| RV-12 | **Elections.** Sections suppressed by nonpublic elections render "Omitted under the <election> election." with the registry key in the tooltip (BR-RPT-03). |
| RV-13 | **Empty run.** A successful run with zero rows keeps the run stamp and shows DS-CMP-23 with the report's empty copy (§5.6), because an empty population is evidence. |
| RV-14 | **Failed run.** SCR-ST-12 with the label "Running <report name>"; the run record remains with status Failed and is listed on SF-08:run. The "Reference <job id prefix>" line names the displayed run's own job: API-S-ReportRun `job_id` (04 rev 1.17; the T-RPT-02 `job_id` stamped at creation from the `POST /report-runs` 202 `Location` job, or the rerun's job) on every report surface — SF-08:report, SF-06:entries and SF-04 — whether the run was created by this mounted view, rendered from `run=` (RV-01; SCR-URL-16) or opened by a later `run` navigation in the same mounted view. A run record without `job_id` names the job of the creation this mounted view started, only while that run is the displayed `run` (the rev 1.5 pair); a context change or "Run report" clears the pair; a retry creates a new run and binds the new job to it. Every creation answer is bound to the attempt that produced it: an answer arriving after a later attempt, a context change or "Run report" is discarded, so a late 202 never moves `run` to a superseded creation and a late refusal never shows. The rev 1.5 rc deviation (no reference for stored runs and for a failed run created on SF-04) is closed (rev 1.7; D-90e L9-PLT-Q-5; D-91 SF-04 addition; DS-CMP-24 read literally). |

**The context of a view (rev 1.92; item RPT-VIEW-CONTEXT-DEFAULT-1; SCREENS.md SCR-URL-01 rev 1.61, SCR-URL-20; PRD BR-UX-01; the supervisor's rulings of 2026-10-02 02:50, 03:43 and 04:10).** SF-04, SF-08:report and SF-08:dashboard run for what their address says. (1) An address that names an entity is that entity's. (2) An address that says `entities=all` and names no entity is every entity's in the member's scope: the runs name no entity, with the book and the period the address has, and nothing is filled — what an absent `entity` read before this revision; on SF-08:dashboard it is the context without an entity of §5.5. An entity named beside `entities=all` decides. (3) Any other address takes the context pill's: `entity`, `book` and `period` are filled, each only where the address leaves it out — by the member's last choice, else by BR-UX-01's default, the first entity in code order, the primary book it keeps and its earliest open period — and written with `history.replace` before a run is asked. What the address names is never rewritten: a book the entity does not keep, or an entity outside the member's list, stays, a period is not filled beside it, since it has no calendar to be chosen on, and the API answers such a run by name. Nor is a period filled on a calendar the member may not read: the periods of one entity are read with `config.read` for that entity (SCREENS.md SCR-PERM-02). The screen mounts its view once the address holds what can be filled; until then it shows its loading state (SCR-ST-01) and asks no run. *Why.* A period key names a different month on each fiscal calendar, so a run by key over entities that keep different calendars is not one statement (what the API answers to it is item RPT-PERIOD-KEY-CALENDARS-1's); in a workspace of several calendars a member who holds every entity met that run by opening "Schedules" from a page that keeps no context. *A stored run.* An address that carries `run=<id>` — or `run.<panel>` on the dashboard — and no context keeps its runs: the context is filled around them and no run is asked. *The pill's change.* The context pill takes `period` out of the address when its entity or its book changes, so that the new calendar's default applies. The address is then incomplete: the view gives way to the loading state, the period is filled on the new calendar, and the runs still in the address leave it in the same write, since they are the earlier context's (RV-01). Before this revision SF-08:report asked that run without a period. *Without `config.read`* a member has no pill and no list of entities, and the address stays as it is. *A read that fails.* Where the entities, the books or the calendar that fill the address cannot be read, no run is asked: the screen shows its load error — "Could not load the report", "Could not load the revenue waterfall", "Could not load the dashboard" — with the API's sentence and "Retry", which reads again. *Who writes `entities=all`.* Only a link that means all entities: "Open report view" of a run that covers several entities (§5.3), and the dashboard's "Open report" links and its bar's link to SF-04 while it shows all entities (§5.5). The context pill offers no "All entities" in 1.0, so where §5.6 says "context pill (All entities allowed)" the parameter is how an address says it. *The pill's entity outside `report.run`.* A member whose `report.run` scope does not hold the pill's entity is refused that entity's run by the API (04 API-R-41: 422 on `parameters.entity_codes`, "Choose entities that exist in this workspace.") on SF-04 and SF-08:report, and reads no chart panel on the dashboard (§5.5, Roles and permissions); the member chooses another entity in the pill.

### 0.6 Coverage

| Screen ids | Section | Primary personas | REQ |
|---|---|---|---|
| SF-05, SF-05:close-run, SF-05:journal-preview, SF-05:history, SF-05:multi-entity | §1 | PRS-03, PRS-03a, PRS-01, PRS-02 | REQ-CLS-001 to 021; REQ-ENT-006 |
| SF-05:reconciliations, SF-05:reconciliation | §2 | PRS-01, PRS-02 | REQ-CLS-015 to 017 |
| SF-06, SF-06:run, SF-06:run-lines, SF-06:run-batches, SF-06:entries | §3 | PRS-01, PRS-02 | REQ-JE-001 to 019, 022 |
| SF-04 | §4 | PRS-01, PRS-04 | REQ-RPT-004, 017; REQ-AI-007 |
| SF-08, SF-08:report, SF-08:run, SF-08:disclosure-pack, SF-08:dashboard | §5 | PRS-03, PRS-04, PRS-05 | REQ-RPT-001 to 028 |
| SF-09, SF-09:pack, SF-09:audit-log, SF-09:verification | §6 | PRS-05, PRS-05a, PRS-03 | REQ-RPT-014, 015; REQ-PLT-018 to 020 |
| SF-17, SF-17:event-set, SF-17:run, SF-18 | §7 | PRS-07 | REQ-FC-001 to 007 |
| SF-20:new, SF-20, SF-28, SF-15:ai, SF-15:ai-call-log | §8 | PRS-01, PRS-04, PRS-06 | REQ-AI-001 to 010 |
| SF-15 and its §9 pages, SF-14 and its pages, SF-16:developer | §9 | PRS-06, PRS-06a, PRS-03 | REQ-REF-001 to 009, 016; REQ-PLT-004 to 012, 021 to 025, 033 to 036; REQ-CTL-006; REQ-OPS-016 |
| SF-19, SF-19:new, SF-19:detail | §10 | PRS-01, PRS-03 | REQ-MIG-001 to 007 |
| SF-15:setup, SF-25, SF-23:select, SF-26, SF-27 | §11 | PRS-06, PRS-04, PRS-01 | REQ-PLT-038; REQ-UX-018, 019; REQ-DEMO-001, 006 |
| SF-22 family, X:session-expiring, X:route-error, X:narrow-viewport | §12 | all | REQ-PLT-004 to 006; NFR-32, NFR-42 |
| X:design | §13 | designers, e2e | DS-VER-06 |

Integrations status and setup (SF-16, SF-16:connection, SF-16:sync-run; J-23) are specified in SCREENS.md §14 per its index; the not-found and access-limited pages are SCREENS.md SCR-ST-06, SCR-ST-07 and X:not-found.

## 1. Close cockpit (SF-05)

The close cockpit is one page per entity × book × period. Its route tabs (DS-CMP-07) are **Checklist** (SF-05, default), **Close run** (SF-05:close-run), **Journal preview** (SF-05:journal-preview), **Reconciliations** (SF-05:reconciliations, §2) and **History** (SF-05:history). The header, KPI strip, banners and action bar of §1.1 are shared by every tab.

### 1.1 SF-05 Close cockpit: checklist and blockers

| Field | Value |
|---|---|
| Screen id | SF-05 |
| Route | `/close/:entity/:book/:period` (RT-26); `/close` redirects to the context entity, primary book and earliest open period (BR-UX-01) |
| Roles and permissions | Read: `contract.read` (RT-26; every default role except Service Account). Open period, start or end soft close, run close, submit for lock, sign a manual task, request a waiver: `period.close` (Revenue Accountant, Controller). Lock and permanent lock: `period.lock` (Controller), decided on a request submitted by another user. Request reopen: `period.reopen_request` (Revenue Reviewer, Controller). Download evidence pack: `evidence.export` (Controller, Auditor) |
| Purpose | Show every close blocker with count, owner and link and every close gate with its result, and move the period through soft close, lock and reopen, so the controller locks only when the evidence is complete |
| REQ | REQ-CLS-001, 003, 008, 009, 010, 011, 020, 021; REQ-JE-016; REQ-TP-004 |
| Journeys | J-13.1, J-13.6, J-13.13, J-13.14, J-13-AC-1, J-13-AC-2, J-13-AC-8, J-13-ALT-1, J-13-ALT-2; J-14.1 to J-14.3, J-14.7, J-14-ALT-3; J-24.2 (tour stop 5 on FS-US); J-26 |

**Wireframe, 1440 px (J-13.1 state, viewer `marcus`).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Close · AVM-US · Sep 2026 · ASC 606   (Period open)                    [Run close] [Lock period] [*Start soft close] ...|
| Entity AVM-US · Avenmoor Inc. (Demo)  Book ASC 606  Period 01 Sep 2026 – 30 Sep 2026  Close run None  Current lock None|
| Close status                                                                                                          |
| Blockers          | Checklist           | Reconciliations reviewed  | Journal difference (USD)  | Days to close             |
| 10                | 7 of 14 passed      | 0 of 2                    | —                         | Jul 2026: 6 days          |
|                   |                     |                           |                           | Aug 2026: 5 days          |
| Lock is not available: 7 close gates have not passed. No pending approvals · Exceptions resolved, waived or dismissed…|
+----------------------------------------------------------------------------------------------------------------------+
| Checklist   Close run   Journal preview   Reconciliations   History                                                  |
+----------------------------------------------+-----------------------------------------------------------------------+
| Blockers (10)                                | Checklist (14 gates, 0 custom tasks)                                  |
| Pending approvals                 3  Priya > | (Not passed) No pending approvals            <Automatic>   3       ...  |
| Exceptions                        2  Maya  > | (Not passed) Exceptions resolved, waived…    <Automatic>   3       ...  |
| VC elements without a period-end            | (Not passed) Holds released or waived        <Automatic>   1       ...  |
|   estimate                        1  Maya  > | (Not passed) Reconciliations generated…      <Automatic>   2       ...  |
| Holds                             1  Maya  > | (Not passed) Journals complete               <Automatic>   1       ...  |
| Reconciliations not generated     2  Maya  > | (Not passed) Controller certification        <Automatic>   —       ...  |
| Journal run not calculated        1  Maya  > | (Passed)     Interface batches complete       <Automatic>   0            |
|                                              | ...                                                                   |
+----------------------------------------------+-----------------------------------------------------------------------+
```

**Wireframe, 1280 px.** Rail collapsed (SCR-WF-03); the KPI strip wraps "Days to close" onto a second row; blockers stack above the checklist.

```text
+--------------------------------------------------------------------------------------------------------+
| Close · AVM-US · Sep 2026 · ASC 606  (Period open)           [Run close] [Lock period] [*Start soft close]|
| Entity AVM-US  Book ASC 606  Period 01 Sep 2026 – 30 Sep 2026  Close run None  Current lock None         |
| Blockers 10 | Checklist 7 of 14 passed | Reconciliations reviewed 0 of 2 | Journal difference (USD) —    |
| Days to close  Jul 2026: 6 days · Aug 2026: 5 days                                                       |
| Lock is not available: 7 close gates have not passed. No pending approvals · Exceptions resolved…        |
| Checklist   Close run   Journal preview   Reconciliations   History                                     |
| Blockers (10)                                                                                            |
| Pending approvals 3 Priya >   Exceptions 2 Maya >   VC elements without a period-end estimate 1 Maya >   |
| Holds 1 Maya >   Reconciliations not generated 2 Maya >   Journal run not calculated 1 Maya >            |
| Checklist (14 gates, 0 custom tasks)                                                                     |
| (Not passed) No pending approvals                    <Automatic>   3                               ...   |
| ...                                                                                                      |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.**

| Region | Components | Content |
|---|---|---|
| Header | DS-CMP-06 record header, period variant; DS-CMP-19 period chip; DS-CMP-20 action bar; DS-CMP-28 overflow menu | `h1` "Close · <entity code> · <period label> · <book label>"; meta row "Entity" `<code> · <name>`, "Book", "Period" `<DD MMM YYYY – DD MMM YYYY>`, "Close run" `<close run no>` with chip or "None", "Current lock" `<lock id prefix>` or "None" |
| KPI strip | DS-CMP-06 KPI strip | Heading "Close status"; cells "Blockers" (sum of visible blocker rows); "Checklist" `<passed> of <total> passed`; "Reconciliations reviewed" `<n> of <m>` (kinds `BILLING_TO_SUBLEDGER`, `SUBLEDGER_TO_GL` in `REVIEWED`, `AUTO_CERTIFIED` or `CERTIFIED` over required kinds); "Journal difference (<functional currency>)" from `journal_preview` (em dash without a run); "Days to close" with one secondary line per item of `kpis.days_to_close_last_three`: "<period label>: <n> days", or "<period label>: In progress" when unlocked (REQ-CLS-020) |
| Lock reason line | DS-CMP-21 visible reason line | Present only while "Lock period" is `aria-disabled` (SCR-PERM-03) |
| Banners | DS-CMP-29 | Table "Banners" below |
| Route tabs | DS-CMP-07 route variant | Checklist · Close run · Journal preview · Reconciliations · History |
| Blockers | DS-CMP-10 static table (native `table`, at most 16 rows) | Rows with count 0 are hidden; `caption` "Blockers (<n>)" |
| Checklist | DS-CMP-10 DataGrid | System gates in `sequence` order, then custom tasks |
| Task details | DS-CMP-09 informational drawer (`drawer=task`) | Gate or task description, result detail, owner, due date, sign-off, waiver request link |

**Data bindings.**

| Region | Read or command | Notes |
|---|---|---|
| Period resolution | `GET /periods?entity=<code>&book=<book>&period=<period_key>` | One API-S-Period row; `id` is the `period_state.id` used below |
| Header, KPI strip, checklist | `GET /periods/{id}/cockpit` (API-S-PeriodCockpit) | `period`, `checklist[]`, `journal_preview`, `kpis`, `derived_blockers[]` (BLK-10, BLK-13), `pending_requests[]` (BLK-06, BLK-15; rev 1.3) |
| Blockers | API-S-Period `blockers`; API-S-PeriodCockpit `pending_requests[]`; `GET /exceptions?code=VC_REASSESSMENT_MISSING&entity=<code>&period=<key>&status=OPEN,IN_PROGRESS&count=true` | Counts only; the exception count is read from `X-Erev-Total-Count`. The request counts come from the cockpit read, not from `GET /approvals`, so API-R-09 request visibility does not apply to BLK-06 and BLK-15; BLK-03 still reads `GET /exceptions`, which applies the reader's permissions (a 403 reads as 0) (rev 1.3; D-90a QA-L9-7; L8-C-Q-2); count arithmetic is permitted because counts are not money |
| Close run chip | `GET /close-runs?entity&book&period&limit=1` | Newest first |
| Lock and reopen requests | `GET /approvals?subject_type=PERIOD_LOCK&status=PENDING&entity=<code>`; `subject_type=PERIOD_REOPEN` | The request whose subject is this `period_state.id` |
| Commands | `POST /periods/{id}/open`, `/start-close`, `/cancel-close`, `/request-lock`, `/request-reopen`, `/request-permanent-lock`, `/checklist/{item_id}/sign`, `/checklist/{item_id}/waive`; `POST /approvals/{id}/approve` for "Lock period" | `If-Match` on period commands (API-S-Period `row_version`) |

**Blocker rows.** A row counts only items that no earlier row counts, so each item appears once (J-13.1). Owner is the checklist item owner of the related gate; when none, the role label below.

| Id | Label | Count | Default owner | Link |
|---|---|---|---|---|
| BLK-01 | "Pending approvals" | `blockers.approvals_pending` | "Revenue Reviewer" | SF-12:all with `f.status=is:PENDING&entity=<code>` |
| BLK-02 | "Exceptions" | `blockers.exceptions_open` − BLK-03 | exception owners | SF-11 with `blocking=<period id>` (rev 1.66; before: `entity`, `period`, `f.status=in:OPEN,IN_PROGRESS`) |
| BLK-03 | "VC elements without a period-end estimate" | exception items with code `VC_REASSESSMENT_MISSING` open for the period | "Revenue Accountant" | SF-11 with `f.code=is:VC_REASSESSMENT_MISSING` |
| BLK-04 | "Holds" | `blockers.holds_open` | "Revenue Accountant" | SF-02 with `f.on_hold=is:true` |
| BLK-05 | "Unmapped products" | `blockers.unmapped_products` | "Integration Admin" | SF-11 with `f.code=is:PRODUCT_UNMAPPED` |
| BLK-06 | "Judgements not reviewed" | `blockers.judgements_unreviewed` − `pending_requests[]` count of `JUDGEMENT_RECORD` (rev 1.3) | "Revenue Reviewer" | SF-08:report `judgement_register` with `p.status=SUBMITTED` |
| BLK-07 | "Interface batches failed" | `blockers.interface_failures` | "Integration Admin" | SF-16 sync runs with `f.status=in:FAILED,CONTROL_TOTAL_MISMATCH` |
| BLK-08 | "Failed jobs" | `blockers.jobs_failed` (rev 1.38: includes the re-marking job of a period a lock opened, once its newest job failed — 04 §16.8) | job initiator | SF-05:close-run |
| BLK-09 | "Contracts changed since the last close run" | `blockers.groups_dirty` | "Revenue Accountant" | SF-05:close-run |
| BLK-10 | "Journal run not calculated" | `derived_blockers[]` count of code `JOURNAL_RUN_NOT_CALCULATED` (04 API-S-PeriodCockpit, E-122): 1 when no non-cancelled journal run exists for the entity, book and period, else 0 | "Revenue Accountant" | SF-06 with `entity`, `book`, `period` |
| BLK-11 | "Batches not exported" | `blockers.batches_unexported` | "Revenue Accountant" | SF-06 with `f.state=is:approved` |
| BLK-12 | "Batches not acknowledged" | `blockers.batches_unacknowledged` | "Revenue Accountant" | SF-06 with `f.state=in:exported,failed` |
| BLK-13 | "Reconciliations not generated" | `derived_blockers[]` count of code `RECONCILIATIONS_NOT_GENERATED` (04 API-S-PeriodCockpit, E-122): required reconciliation kinds without a reconciliation for the period | "Revenue Accountant" | SF-05:reconciliations |
| BLK-14 | "Reconciliations not signed" | `blockers.reconciliations_unsigned` | "Revenue Reviewer" | SF-05:reconciliations |
| BLK-15 | "Manual adjustments pending" | `blockers.manual_adjustments_pending` − `pending_requests[]` count of `MANUAL_ADJUSTMENT` (rev 1.3) | "Revenue Accountant" | SF-08:report `manual_adjustment_register` with `p.status=DRAFT` |
| BLK-16 | "Close tasks not signed" | manual checklist items not `PASSED`, `WAIVED` or `NOT_APPLICABLE` | task owner | the task row in the checklist grid |

Required reconciliation kinds: `BILLING_TO_SUBLEDGER` and `SUBLEDGER_TO_GL` when registry `close.require_reconciliations_for_lock = true` (T-PLT-31), otherwise none.

Rev 1.66 (item CLO-QUARANTINE-READ-1; 04 §15.3 API-R-44 and §16.14, rev 1.206). BLK-02's link opens the exception queue on the list its count is made of: the queue reads `GET /exceptions?blocking=<id>` with the API-S-Period `id` of the cockpit, which lists the items `blockers.exceptions_open` counts, by the gates' own predicate. The link of the earlier revisions passed `entity` and `period`, which then compared the item's own columns (`entity` reads the gates' attribution since 04 rev 1.206, supervisor ruling R-121 (i); `period` still compares the item's own column): an item that names no entity — the quarantine of a contract group of several contracts, an import- or workspace-level item — or no period — every engine item — was counted and not listed. The list holds BLK-03's items too (the count shown stays `blockers.exceptions_open` − BLK-03; BLK-03's own link narrows by code), and it holds open items only, so the link names no status.

**Grid columns: checklist.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Status | `checklist[].status` | chip (§0.4 E-60) | none |
| Gate or task | gate label (table below) or `name` | text link | Task details drawer |
| Kind | `gate_kind` | outline chip "Automatic" or "Manual" | none |
| Count | `result.count` | integer (DS-FMT-21); em dash for manual tasks | the related blocker link |
| Owner | `owner` | user cell | none |
| Due | `due_date` | DS-FMT-16 | none |
| Signed | `signoff.signer`, `signoff.signed_at` | user and DS-FMT-17 | none |
| Evaluated | `result.evaluated_at` | DS-FMT-17 | none |
| Actions | none | ghost buttons "Sign task" (manual, `period.close`), "Request waiver" (not passed, `is_waivable`, `period.close`; rev 1.28) | none |

| `gate_check_code` | Label | Failure detail (row caption and ERR-14 gate list item) |
|---|---|---|
| `INTERFACES_COMPLETE` | "Interface batches complete" | "Interface batch not complete: <connection name> (<n> runs)" |
| `JE_BALANCED` | "Journals balance per currency" | "Journal batch does not balance: <currency>" |
| `JE_COMPLETE` | "Journals complete" | "Journal run not calculated" or "Schedule lines without journal lines: <n>" |
| `APPROVALS_CLEARED` | "No pending approvals" | "Pending approvals: <n>" |
| `EXCEPTIONS_CLEARED` | "Exceptions resolved, waived or dismissed" | "Open exceptions: <n>" |
| `HOLDS_REVIEWED` | "Holds released or waived" | "Open holds: <n>" |
| `BATCHES_ACKNOWLEDGED` | "Batches acknowledged by the GL" | "Unacknowledged batches: <n>" |
| `RECONCILIATIONS_GENERATED` | "Reconciliations generated and reviewed" | "Reconciliation not generated: <kind label>", "Reconciliation not reviewed: <kind label>" (J-13-ALT-2 "Reconciliation not reviewed: Subledger to GL") or, for a reviewed reconciliation that a later posting or billing document of the period has overtaken, "Reconciliation out of date, generate it again: <kind label>" (rev 1.27; supervisor ruling R-58 (e)) |
| `JUDGEMENTS_REVIEWED` | "Judgements reviewed" | "Judgements not reviewed: <n>" |
| `DATA_QUALITY_CLEAR` | "Data-quality errors cleared" | "Data-quality errors: <n>" |
| `NO_DIRTY_GROUPS` | "All contracts computed" | "Contracts changed since the last close run: <n>"; for a period a lock opened, while its re-marking job has not succeeded: "Contracts not re-marked since the period was opened" with no count; the row's `is_waivable` is false while that lasts, so "Request waiver" is not offered (rev 1.38; 04 §16.8) |
| `MANUAL_ADJUSTMENTS_CLEARED` | "Manual adjustments cleared" | "Manual adjustments pending: <n>" |
| `CLOSE_RUN_COMPLETED` | "Close run completed" | "Close run not completed" while the period has no close run; "Close run <close run no> is <status>" while its latest close run has not succeeded, the status as §0.4 labels E-62 ("Close run CLS-000012 is Failed"); "Close run out of date, run it again: <n> contracts" when contracts hold a period end of the period that is still to post since the run; rev 1.100 (04 §16.8 rev 1.291; item CLO-RATE-AFTER-RUN-1): "Close run out of date, run it again: <what> changed since it ran. A run posts nothing where the change moves nothing for this entity." when no contract holds one and the exchange rates or the period-pinned policy values the run read are no longer what is in force — <what> is "exchange rates", "policies" or "exchange rates and policies". The row's `is_waivable` is false, so "Request waiver" is never offered; the remedy is "Run close" (rev 1.50; 04 §16.8 "The close-run gate") |
| `CONTROLLER_CERTIFIED` | "Controller certification" | "Awaiting Controller certification at lock" |

Reconciliation kind labels (E-58), used throughout §1 and §2: `BILLING_TO_SUBLEDGER` "Billing to subledger"; `SUBLEDGER_TO_GL` "Subledger to GL"; `CONTRACT_BALANCE_ROLLFORWARD` "Contract balance rollforward"; `RPO_ROLLFORWARD` "RPO rollforward"; `MIGRATION_OPENING_BALANCE` "Migration opening balances".

**States** (SCREENS.md SCR-ST applies; region copy only).

| State | Copy and rendering |
|---|---|
| SCR-ST-03 blockers empty | Region title "No blockers"; description "Every blocker is clear. Submit the period for lock when the checklist has passed." |
| SCR-ST-03 checklist empty | Title "No close checklist"; description "System gates are seeded when a workspace is provisioned. Ask a workspace administrator to check the setup." |
| SCR-ST-05 | "Could not load the close status" |
| SCR-ST-07 | "Period not found" (unknown entity, book or `period_key` in the path), action "Go to Close" |
| Running close run | A two-line strip under the KPI strip: "Close run <no> · Step <n> of 14: <step label> · <elapsed>" with link "View close run" (DS-CMP-24 compact) |

**Interactions, keyboard and copy.**

*Action bar* (one primary per state; SCR-PERM-02 hides actions the viewer may not perform).

| Period state | Primary | Secondary | Overflow menu |
|---|---|---|---|
| `future` | "Open period" | none | none |
| `open` | "Start soft close" | "Run close"; "Lock period" (`period.lock` holders; state-guarded, SCR-PERM-03) | "Close several entities" |
| `closing`, no pending lock request | "Run close" | "Submit for lock"; "Lock period" (guarded) | "End soft close"; "Close several entities" |
| `closing`, pending lock request, viewer holds `period.lock` and is not the requester | "Lock period" | "View lock request" | "End soft close" |
| `closing`, pending lock request, other viewers | none | "View lock request" | "End soft close" |
| `closed` | none | "Request reopen" (not offered while a `PERIOD_REOPEN` request is pending; rev 1.32); "Download evidence pack" | "Permanently lock" (`period.lock`; not rendered while its request is pending; rev 1.32, supervisor ruling R-83) |
| `reopened` | "Run close" | "Start soft close" | none |
| `permanently_locked` | none | "Download evidence pack" | none |

"Lock period" is `aria-disabled="true"` when no lock request is pending or a gate fails; the reason line reads "Lock is not available: <n> close gates have not passed." followed by the failing gate labels as links that focus their checklist rows (J-13.1). "View lock request" opens SF-12:request. "Download evidence pack" opens SF-09:pack of the current lock's `CLOSE` pack. "Close several entities" opens SF-05:multi-entity with the current `period` and `book`. Rev 1.42 (BUILD_SPEC CLO-24, as built): "Run close" starts the run, opens SF-05:close-run and, where the period's run has not ended, says "Close run <no> is already running." "Close several entities" is rendered for `period.close` in an `open` period and in a `closing` period without a pending lock request; DS-CMP-28 lists the destructive "End soft close" after it.

Rev 1.93, a refused "Run close" (item O2 of the lane's report on the close screens; the supervisor's rulings of 2026-10-01 23:35 and 2026-10-02 03:43). The bar offers "Run close" by the state the page has read, and the API starts a run in an open period, in soft close or in a reopened one (04 §16.8). A refusal, 409 — "<period key> of <entity code> in book <book code> is <state>. A close run needs an open period, a period in soft close or a reopened one." — therefore means that read is out of date: the API's sentence stays in the page's banner, and the period, the cockpit and its close runs are read again, so that the bar offers what the period now allows — `closed`: no "Run close", and "Request reopen" for its holder; `permanently_locked`: neither; `future`: "Open period". A refusal that is no conflict (403, 422) stays in the banner and nothing is read again.

Rev 1.32, the order of periods (supervisor ruling R-112 (a), item LOCK-ORDER-UI-1; PRD BR-CLS-08, ERR-65; SM-07). A period is submitted for lock, and locked, only when no earlier period of its entity and book is `open`, `closing` or `reopened`. The cockpit knows this before the command from its read of the entity's and book's periods (API-S-Period; API-S-PeriodCockpit carries no member for it and needs none). While such a period exists, "Submit for lock" and "Lock period" are `aria-disabled="true"` and the reason line reads "Lock <earliest such period label> first. An earlier period of <entity code> in book <book label> is not closed." with the link "Go to <period label>" to that period's cockpit; this reason comes before the two of "Lock period" above. A 409 `earlier-period-open` that arrives all the same — the earlier period was reopened after the read — shows its title and detail in the dialog. Periods also open in order: "Open period" is `aria-disabled="true"` while the previous period is `future`, with the reason line "Open <previous period label> first." and the link "Go to <previous period label>" (test hook `SF-05-banner-open-unavailable`).

Rev 1.42, a period of the LEGACY book (supervisor rulings R-112 (e), R-113 (h) and R-114 (d); 04 §16.8 rev 1.155, API-S-Period `follows`; PRD ERR-76). The LEGACY book has no close of its own: its period follows the close of the tenant's primary book, and the row says which in `follows` — the book's code and that book's state for the same entity and period — beside its own `state`, which is what the row holds. Where `follows` is not null the cockpit offers no command of a close — none of "Start soft close", "Run close", "Submit for lock", "Lock period", "Request reopen", "Record estimate-versus-error judgement", "Permanently lock" and "Close several entities" — and keeps the two commands 04 §16.8 keeps for such a row: "Open period" on a `future` period, with its order rule, and "End soft close" on a `closing` one, which returns a row an earlier release left in soft close to open. The header keeps the row's own E-04 chip and its banners, and shows neither the "Close run" and "Current lock" items nor the "Close status" strip. In place of the blockers and the checklist the Checklist tab shows one line (test hook `SF-05-follows`): "The legacy book follows the close of <followed book label>.", then "<period label> in <followed book label>:" with the E-04 chip of `follows.state`, and the link "Go to <period label> in <followed book label>" to that period's cockpit in the followed book, in its own context; where `follows.state` is null — the entity keeps no period of that book there — the line ends "<followed book label> has no period <period label> for <entity code>." and carries no link. The state comes with the row: no second request, and the client names no book of its own. The route tabs of such a period are "Checklist" and "History": a close run, a journal preview — the LEGACY book takes no journal run (04 T-SL-06) — and reconciliations are not offered, and their addresses show the same line instead of their content. The cockpit reads neither the period's pending requests nor its blocker counts. SF-05:history and SF-05:multi-entity say the same in their own words (§1.4, §1.5).

*Banners.*

| Condition | Tone | Copy |
|---|---|---|
| `closing` | warning | "Soft close: only users with the lock permission may submit manual adjustments. Imports wait for review." (J-13.6; REQ-CLS-003) |
| `closing` under the period's `REOPEN` record (API-S-Period `current_lock.kind` = `REOPEN`; rev 1.61; PRD BR-CLS-06 rev 1.113, BR-CLS-07, REQ-CLS-011 rev 1.99) | warning | A second banner under the soft-close banner: "<period label> was reopened and is not locked again yet. Lines posted now are flagged post-reopen, and re-lock produces a diff report." — a soft close does not end what the reopen began. The sentence "Every posting needs a second approver" of the `reopened` banner joins it with item CLO-REOPEN-APPROVAL-1: a banner promises no control the product does not hold for every posting (the supervisor's message of 2026-10-01 02:56 on ruling R-119 (h)) |
| `closed` | info | "<period label> is locked for <entity code>. Late events post to <next period label> with origin period <period label>." (DS-CMP-29) |
| `reopened` | warning | "<period label> is reopened. Every posting needs a second approver, and lines are flagged post-reopen. Re-lock produces a diff report." (BR-CLS-06, BR-CLS-07) |
| Pending `PERIOD_REOPEN` request | info | "Reopen requested by <name> on <DD MMM YYYY>: <reason label>. Dual approval · <n> of 2 recorded." action "Review in Approvals" (SF-12:request). Rev 1.32 (supervisor ruling R-83 (d)): API-S-Approval does not state the request's own reason code yet (item APR-REQUEST-REASON-1), so until it does the banner reads "Reopen requested by <name> on <DD MMM YYYY>. Dual approval · <n> of 2 recorded.". Rev 1.93 (04 §16.10 rev 1.252, item APR-REQUEST-REASON-1; the supervisor's messages of 2026-10-02 02:50 and 03:43): API-S-Approval states `reason_code`, so the banner reads as first specified, with the label the reopen drawer offers for the code ("Error correction", "Late source data", "Audit adjustment", "Other"). Where `reason_code` is null — the API withholds a request's content from a reader of its header alone — or names a code this build has no label for, the sentence of rev 1.32 stands and no code is shown |
| Pending `PERIOD_LOCK` request | info | "Submitted for lock by <name> on <DD MMM YYYY HH:mm UTC>." action "View lock request" |
| Pending `PERIOD_LOCK` request on a `closed` period: the permanent-lock request (rev 1.32; supervisor ruling R-83 (b)) | info | "Permanent lock requested by <name> on <DD MMM YYYY HH:mm UTC>." action "View request" (SF-12:request, where another Controller decides with the step-up) |
| `permanently_locked` | info | "<period label> is permanently locked for <entity code>. It cannot be reopened." |

*Open period.* DS-CMP-11 form modal: title "Open <period label> for <entity code>?"; description "Postings and events effective in <period label> can be recorded once it is open."; field "Comment (optional)"; buttons "Cancel", "Open period" (`POST /periods/{id}/open`). Toast "<period label> opened for <entity code>."

*Start soft close.* DS-CMP-11 form modal: title "Start soft close for <period label>?"; description "Only users with the lock permission may submit manual adjustments for the period, and imports wait for review."; field "Comment (optional)"; buttons "Cancel", "Start soft close" (`POST /periods/{id}/start-close`). Toast "Soft close started for <entity code> <period label>." J-13.6 comment "September close in progress".

*End soft close* (SB-R-05). Title "End soft close for <period label>?"; consequence "The period returns to open. Manual adjustments and imports follow the normal rules again." — for a period that has been locked before (API-S-Period `current_lock.kind` = `REOPEN`; rev 1.49; 04 §16.8 rev 1.170) "The period returns to reopened. Postings into it keep needing a second person's approval."; select "Reason" (`reason_code`, the E-110 subset of 04 table 3.4-R for `cancel-close`: `CLOSE_RESTARTED` "Close restarted", `DATA_CORRECTION_PENDING` "Data correction pending", `OTHER` "Other"; OQ-B-06 resolved by D-76); "Comment (required)"; Danger "End soft close" (`POST /periods/{id}/cancel-close`).

*Submit for lock* (J-13.13). DS-CMP-11 form modal `--modal-w-md`: title "Submit <period label> for lock"; a static table "Close gates" (label, chip); field "Certification comment (required)", minimum 10 characters; buttons "Cancel", "Submit for lock" (`POST /periods/{id}/request-lock`). A 409 keeps the typed comment and shows the negative banner "<n> close gates have not passed: <gate list>." (ERR-14), each gate a link that closes the modal and focuses its row. Success toast "Submitted <period label> for lock. A Controller other than you must lock it."

*Lock period* (J-13.14; SB-R-05). Title "Lock <period label> for <entity code>?"; consequence "Locking <period label> for <entity code> prevents new postings to that period. Late events post to <next period label> with origin period <period label>. The lock snapshot and evidence pack are generated automatically."; static table "Close gates" (all Pass); field "Reason (required)"; Danger "Lock period". The command is `POST /approvals/{lock request id}/approve` with `subject_content_sha256` and `comment` = the reason; SCR-PERM-05 step-up applies. Success: period chip Locked; toast "<entity code> <period label> locked." with the action "Download evidence pack", which shows "Building evidence pack <pack no>" until the `EVIDENCE_PACK` job succeeds; NTF-06 is sent. Problems: `self-approval` ERR-02; `stale-approval` ERR-04 with "Reload"; `close-gates-failed` ERR-14. Rev 1.32 (supervisor ruling R-83 (e)): the step-up modal keeps the typed reason and the approval is sent again with the same Idempotency-Key; the problems show inside the dialog, "Reload" reads the period and its requests again and closes the dialog; the toast's "Download evidence pack" action is owed to SF-09:pack. A 409 `lock-conflict` (ERR-52; the decision does not wait for the next period's row, 04 DB-07 rev 1.113) is not a failed lock: a warning banner shows the problem's title and detail, the dialog keeps the reason, and "Lock period" sends the approval again — under a new Idempotency-Key, because the API keeps that refusal as the answer of the first key (dev-guide DG-KRN-IDEM-03; supervisor ruling R-97 (6)).

*Request reopen* (J-14.1). DS-CMP-09 modal drawer `--drawer-w` (form drawer; not URL state, SCR-URL-12). Rev 1.61 (REQ-CLS-011 rev 1.99; supervisor ruling R-117 (c)): the information line says "until it is locked again", not "while it is reopened" — a line posted in the soft close that follows the reopen is a post-reopen line too.

```text
+------------------------------------------------------------------------------------------------+
| Request reopen of Sep 2026                                                                  [X] |
| AVM-US · ASC 606 · Locked by Marcus Webb on 01 Oct 2026 09:14 UTC                              |
| [i] Reopening lets approved postings into Sep 2026. Lines posted until it is locked again are  |
|     flagged post-reopen, and re-lock produces a diff report. Two approvers other than you      |
|     must approve, at least one a Controller.                                                   |
| Reason                {Error correction v}                                                     |
| Comment (required)                                                                             |
| ____________________________________________________________________________________________ |
| Costs of 20,500.00 on PRJ-CB-2026-01 incurred on 29 Sep 2026 were omitted from the September   |
| cost file.                                                                                     |
| 131 characters · Minimum 10 characters                                                         |
| Attachments (optional)   [ Drop a file here, or choose a file ]    job-cost-report.pdf  (Valid)|
| [x] Record an estimate-versus-error judgement                                                  |
|     Contract     {PRJ-CB-2026-01 · Castellan Build Group Inc. (Demo) v}                        |
|     Conclusion   Error: the cost existed and was known at period end.                          |
|     Rationale    ____________________________________________________________                  |
+------------------------------------------------------------------------------------------------+
|                                                              [Cancel]  [*Submit reopen request] |
+------------------------------------------------------------------------------------------------+
```

| Label | Control | Binding | Validation copy |
|---|---|---|---|
| "Reason" | select | `reason_code`, the E-110 subset of 04 table 3.4-R for `request-reopen`: `ERROR_CORRECTION` "Error correction" (PRD J-14.1); `LATE_SOURCE_DATA` "Late source data"; `AUDIT_ADJUSTMENT` "Audit adjustment"; `OTHER` "Other" (OQ-B-06 resolved by D-76) | "Choose a reason." |
| "Comment (required)" | reason textarea | `comment` | "Enter at least 10 characters." |
| "Attachments (optional)" | DS-CMP-18 dropzone anatomy, multiple | `POST /files` purpose `ATTACHMENT`; after the request exists, `POST /attachments` `{subject_type: "approval_request", subject_id}` (T-PLT-30) | ERR-37 attachment copy |
| "Record an estimate-versus-error judgement" | checkbox revealing a `fieldset`; rendered for a holder of `judgement.create` (PRD ACT-12; SCR-PERM-02; rev 1.32; supervisor ruling R-100 (a)) | none | none |
| "Contract" | combobox over contracts of the entity | `POST /judgements` `{topic: "ESTIMATE_VS_ERROR", subject_type: "contract", subject_id, conclusion, rationale}`, then `POST /judgements/{id}/submit` | "Choose a contract." |
| "Conclusion" | textarea | `conclusion` | "Enter a conclusion." |
| "Rationale" | textarea | `rationale` | "Enter a rationale." |

Rev 1.32, the drawer's two optional parts (SCR-PERM-02; supervisor ruling R-100). *The judgement* is the Revenue Accountant's (`judgement.create`) and its review another person's, so the judgement fields render for a holder of `judgement.create` only. A requester without it reads, in their place, the line "A Revenue Accountant records the estimate-versus-error judgement. Name it in the comment." with the link "Judgement register" (SF-08:report `judgement_register` in the period's context, where the record and its number are listed; PRD J-14.1 rev 1.59). *The attachments*: "Attachments (optional)" renders for a requester who may upload an attachment — a holder of one of the subject write permissions that `POST /files` purpose `ATTACHMENT` and `POST /attachments` answer (04 API-R-12) — and the files are attached to the reopen request (`subject_type` `approval_request`). Once a requester may attach evidence to their own pending request whatever other permission they hold (R-100 (b); item ATT-REQUESTER-1), the field renders for every requester.

Rev 1.42 (item CLO-JDG-ESTERR-UI-1; the supervisor's ruling on the lane's question A). *Record estimate-versus-error judgement.* On a `closed` period a holder of `judgement.create` sees the secondary action "Record estimate-versus-error judgement", whoever requests the reopen: a DS-CMP-09 modal drawer "Estimate-versus-error judgement for <period label>" with the info line "The record goes to a Revenue Reviewer for review. A reopen request names it in its comment.", the fields "Contract", "Conclusion" and "Rationale" of the reopen form, all required here, and the primary "Record judgement". It sends `POST /judgements` `{topic: "ESTIMATE_VS_ERROR", subject_type: "contract", subject_id, conclusion, rationale}`, then `POST /judgements/{id}/submit`; toast "Judgement <judgement no> was submitted for review." with the action "Judgement register"; a refused submission keeps the drawer open, and the next press submits the record that exists. The subject is the contract: 04 T-CON-19 admits no period as the subject of a judgement, and `POST /periods/{id}/request-reopen` has no member for a judgement record, so a record is not tied to the period and a reopen request cannot carry it; the form of a requester without `judgement.create` keeps its line, which names the record in the comment. Both members are owed to the API. Test hook `SF-05-drawer-judgement`.

"Submit reopen request" sends `POST /periods/{id}/request-reopen` `{reason_code, comment}` → `{approval_request_id}`, then the attachments, then the judgement. When a later step fails, the drawer stays open with the warning banner "Reopen request <request no> was created, but <n> attachments were not saved. Add them from the request in Approvals." Toast "Reopen requested for <entity code> <period label>. Two approvers must approve." with the action "View request". "Request reopen" is `aria-disabled="true"` with the tooltip "Reopen <later period label> first. A later period of <entity code> in book <book literal> is closed." when a later period is `closed` or `permanently_locked` (ERR-16; BR-CLS-05); the API refusal `later-period-closed` shows the same text as a banner (J-14-ALT-3).

*Dual-approval status.* While the reopen request is `PENDING`, the banner of the table above and SF-05:history show the DS-CMP-16 routing step "Dual approval · <n> of 2 recorded" with each decision's approver, "on behalf of <delegator>" when delegated, and UTC time. The requester sees "You submitted this request. Two other approvers must review it." and "Withdraw request" (`POST /approvals/{id}/withdraw`). Approvers decide in SF-12:request (J-14.2, J-14.3). Rev 1.32 (supervisor ruling R-83 (d)): "Withdraw request" opens a DS-CMP-11 confirmation "Withdraw the reopen request?" with the consequence "The period stays locked and the approvers are notified." and the button "Withdraw request"; toast "Reopen request withdrawn."; a non-requester sees neither the line nor the action.

*Permanently lock* (SB-R-05). Title "Permanently lock <period label> for <entity code>?"; consequence "A permanently locked period can never be reopened. Every earlier period of <entity code> in book <book label> must already be permanently locked. Another Controller must approve."; "Comment (required)"; Danger "Request permanent lock" (`POST /periods/{id}/request-permanent-lock`). The menu item is `aria-disabled="true"` with the tooltip "Permanently lock <earliest earlier period label> first." when an earlier period is not permanently locked (SM-07). Rev 1.32 (supervisor ruling R-83): the item is rendered for `period.lock`; the disabled item is a DS-CMP-28 menu item with `aria-disabled`, in the arrow-key order, described by its tooltip and never activated; after the request the item is not rendered and the permanent-lock banner of the table "Banners" shows.

*Sign task* (manual task). DS-CMP-11 confirmation: title "Sign <task name>?"; statement "I completed this close task for <entity code> <period label>." with checkbox "I confirm this statement" (OQ-B-05); buttons "Cancel", "Sign task" (`POST /periods/{id}/checklist/{item_id}/sign` `{statement_accepted: true}`; MFA-verified session). Toast "Signed <task name>."

*Request waiver* (SB-R-05). Consequence "The waiver goes to approval. The gate counts as cleared once another user approves it."; "Reason (required)"; Danger "Request waiver" (`POST /periods/{id}/checklist/{item_id}/waive` `{reason}`). The row then shows chip Pending approval and the link "View request". Rev 1.28 (supervisor ruling R-55): the action is offered only for a row whose `is_waivable` is true — "Journals balance per currency", "Journals complete" and "Controller certification" are never waivable, and the server refuses a waiver of them with 409 `invalid-transition` naming the gate; an approved waiver clears its row for the lock request and the lock decision (04 §16.8 rev 1.106).

*Keyboard.* Blocker rows are links in the Tab order; their accessible name is "<label>, <count>, open <destination label>". The checklist grid follows DS-CMP-10; Enter on "Gate or task" opens the task drawer; Esc closes it and returns focus to the cell.

**Sample world.** WLD-T-01, context `entity=AVM-US`, `book=ASC606`, `period=FY2026-P09`. J-13.1 blocker counts (asserted): Pending approvals 3 (WLD-B-01 to 03); Exceptions 2 (WLD-B-04); Holds 1 (WLD-B-05); VC elements without a period-end estimate 1 (WLD-B-06); Reconciliations not generated 2; Journal run not calculated 1. After J-13.5 only BLK-10 and BLK-13 remain; after J-13.7 BLK-10 clears. Lock reason "September 2026 close complete" (J-13.14); after lock Oct 2026 is `open` (BR-CLS-03). Reopen comment of J-14.1 as in the wireframe; `marcus` and `elena` approve (J-14.2, J-14.3). WLD-P-03: Jun 2026 of AVM-US has lock, reopen and re-lock history.

**Test hooks** (SCR-TID-01 locator first).

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page root | `main` | `SF-05-page` |
| KPI strip | region named "Close status" | `SF-05-kpi-strip` |
| Days to close KPI | term "Days to close" | `SF-05-kpi-days-to-close` |
| Blockers table | table named "Blockers (<n>)" | `SF-05-grid-blockers` |
| Blocker row | link named "<label>, <count>, …" | `SF-05-row-<blocker key>` (`approvals-pending`, `exceptions`, `vc-reassessment-missing`, `holds`, `unmapped-products`, `judgements-unreviewed`, `interface-failures`, `jobs-failed`, `groups-dirty`, `journal-run-missing`, `batches-unexported`, `batches-unacknowledged`, `reconciliations-missing`, `reconciliations-unsigned`, `manual-adjustments-pending`, `close-tasks-unsigned`) |
| Checklist grid | grid named "Checklist" | `SF-05-grid-checklist` |
| Checklist row | row header "<gate label>" | `SF-05-row-<gate_check_code normalised>` (for example `SF-05-row-controller-certified`) |
| Lock reason line | text "Lock is not available: …" | `SF-05-banner-lock-unavailable` |
| Soft close banner | status "Soft close: …" | `SF-05-banner-soft-close` |
| Banner of a soft close under the `REOPEN` record (rev 1.61) | status "<period label> was reopened and is not locked again yet. …" | `SF-05-banner-reopened-closing` |
| Reopen request banner | status "Reopen requested by …" | `SF-05-banner-reopen-request` |
| Lock request banner (rev 1.32) | text "Submitted for lock by …" | `SF-05-banner-lock-request` |
| Permanent-lock request banner (rev 1.32) | text "Permanent lock requested by …" | `SF-05-banner-permanent-lock-request` |
| Line of a period that follows another book's close (rev 1.42) | text "The legacy book follows the close of …" | `SF-05-follows` |
| Reopen drawer | dialog named "Request reopen of <period label>" | `SF-05-drawer-reopen` |
| Running close run strip | progressbar named "Close run …" | `SF-05-job-close-run` |

**Light and dark.** Chips and banners only; verify the warning soft-close banner and the Not passed chips on `--bg-surface` in both themes.

**Accessibility.** The disabled "Lock period" button carries `aria-describedby` = the reason line; the KPI strip is a `dl` with one `dd` per "Days to close" period; the reopen drawer's judgement fields are a `fieldset` with legend "Estimate-versus-error judgement"; the comment character counter is announced politely at most every 500 ms (DS-A11Y-08).

### 1.2 SF-05:close-run Close run

| Field | Value |
|---|---|
| Screen id | SF-05:close-run (SCREENS.md §0.4; §14) |
| Route | `/close/:entity/:book/:period/close-run` |
| Roles and permissions | Read `contract.read` (API-R-39). "Run close", "Resume close run", "Cancel close run": `period.close` |
| Purpose | Run and observe the persisted, resumable close state machine with step timings, counts and quarantined contracts |
| REQ | REQ-CLS-012, 013; NFR-14; REQ-OPS-006 |
| Journeys | J-13.7, J-13-AC-9, J-14.6 |

**Wireframe, 1440 px (running).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Close · AVM-US · Sep 2026 · ASC 606   (Soft close)                                              [*Run close]  ...     |
| Checklist   Close run   Journal preview   Reconciliations   History                                                  |
+----------------------------------------------------------------------------------------------------------------------+
| Close run CLS-000031   (Running) Step 5 of 14: Release schedules            2 min 14 s          [Cancel close run]  |
| ##############################......................................  412 of 1,204 contracts                         |
+----------------------------------------------------------------------------------------------------------------------+
| (Succeeded) 1   Cut-off known at                12 Sep 2026 14:05 UTC                                    0 s          |
| (Succeeded) 2   Interface completeness          3 interface runs complete                                1 s          |
| (Succeeded) 3   Exception check                 0 blocking exceptions                                    1 s          |
| (Succeeded) 4   Recompute changed contracts     14 groups recomputed, 0 quarantined                     38 s          |
| (Running)   5   Release schedules               412 of 1,204 contracts                               running          |
| (Queued)    6   FX remeasurement                                                                                     |
| ...                                                                                                                  |
| (Queued)    14  Lock                                                                                                 |
+----------------------------------------------------------------------------------------------------------------------+
| Earlier close runs                                                                                                   |
| CLS-000030  (Succeeded)  11 Sep 2026 09:12 UTC   Maya Chen   4 min 02 s                                              |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** Same regions; the step summary column truncates with a tooltip; durations move under the summary. Rev 1.42 (BUILD_SPEC CLO-24, as built): below 1440 px a row has no duration column and the duration follows the summary after a middle dot, as drawn; from 1440 px it has its own column.

```text
+--------------------------------------------------------------------------------------------------------+
| Close run CLS-000031  (Running) Step 5 of 14: Release schedules   2 min 14 s        [Cancel close run]  |
| ##########################.......................................  412 of 1,204 contracts               |
| (Succeeded) 1  Cut-off known at            12 Sep 2026 14:05 UTC · 0 s                                  |
| (Running)   5  Release schedules           412 of 1,204 contracts · running                             |
| ...                                                                                                     |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.**

| Region | Components | Content |
|---|---|---|
| Run header | DS-CMP-24 inline job indicator; DS-CMP-19 chip | Close run number, chip with caption, elapsed (DS-FMT-24), determinate bar with counts, "Cancel close run" |
| Steps | ordered list composed of DS-ICO-07 state icons and DS-CMP-19 chips | One row per `steps[]` item in T-CLS-01 order |
| Quarantined contracts | DS-CMP-10 DataGrid | Only while status is `BLOCKED` or quarantined count > 0 |
| Earlier close runs | DS-CMP-10 static table | Previous runs, newest first, at most 10 |

**Data bindings.** `GET /close-runs?entity&book&period` (list); `GET /close-runs/{id}` (steps, counts, status; polled every 2 s while `RUNNING`); `POST /close-runs` `{entity_code, book, period_key}` → 202 job `CLOSE_RUN`; `POST /close-runs/{id}/resume`; `POST /close-runs/{id}/cancel` `{reason}`; quarantined contracts `GET /exceptions?source=ENGINE&code=ENGINE_INVARIANT_VIOLATION&entity=<code>&period=<key>&status=OPEN,IN_PROGRESS`. Rev 1.35 (04 §16.8 API-S-CloseRunCreate and API-S-CloseRun, rev 1.134): `POST /close-runs` answers 202 with the job and the header `X-Erev-Close-Run-Id`, or 200 with the run that is already active; `resume` answers 202 with its job and `cancel` 200 with the run. The run header, the bar and the step rows read the run itself — `status`, `current_step_code`, `job.progress` (`done` of `total` contracts while "Recompute changed contracts" runs) and `steps[]` — because `GET /jobs/{id}` answers only the job's initiator and an auditor. A step's summary reads `steps[].counts` (04 T-CLS-01 "Step counts"; rev 1.47): `interface_runs_complete`; `blocking_exceptions`; `groups_recomputed` and `groups_quarantined`; `postings` and `lines` of the three period-end steps; `invariant_failures` ("All invariants pass" at 0); `batches` of "Journal summarization"; `batches_exported`; `batches_acknowledged` of `batches`; `trial_balance_attached` with `currency` and `difference`; `datasets_frozen`; and `locked_by.display_name` once the period is locked. The `FAILED` state reads `steps[].problem.title` of the step `current_step_code` names, and "Open journal run" reads `journal_run_id`. The rows are listed in the order of the array (04 T-CLS-01); the run executes "FX remeasurement" before "Release schedules" (04 T-CLS-01 rev 1.134, supervisor ruling R-79 (b)), so row 6 can be Running or Succeeded while row 5 is Queued, and the caption "Step <n> of 14" counts the position of `current_step_code` in the array. Rev 1.42 (BUILD_SPEC CLO-24, as built): the period's newest run is read by `GET /close-runs/{id}` every 2 s while it is `PENDING` or `RUNNING`, by every reader. Quarantined contracts are read as `GET /exceptions?source=ENGINE&severity=BLOCKING&entity=<code>&status=OPEN,IN_PROGRESS`: the item a recalculation raises for a quarantined group carries the code of its refusal — `ENGINE_INVARIANT_VIOLATION` or another engine code of 04 §15.4 — and no period, so the read names neither `code` nor `period`; the item of a group of several contracts carries no entity and no contract (05 RCP-20 as built) and is not in the list, which is owed to an API member that ties a quarantine to its run. Rev 1.66 (item CLO-QUARANTINE-READ-1; 04 §16.14 rev 1.206): quarantined contracts are read as `GET /exceptions?blocking=<period id>&source=ENGINE&severity=BLOCKING`, with the API-S-Period `id` of the run's entity, book and period — the blocking engine items the close gates count for the period, the item of a group of several contracts among them; the read names no `entity`, `period`, `code` or `status` (the list holds open items only), and the sentence of rev 1.42 on the item that is not in the list ends (since 04 rev 1.206 the read as built, by `entity`, lists that item too; `blocking` adds the period). The list is of the period, not of the run: an engine item raised before the run and still open is in it, and a quarantine that was resolved or waived is not. The count of the `BLOCKED` banner is the run's own `groups_quarantined`. Rev 1.81 (as built): a run that states none takes the count of this list. The difference of "Subledger to GL tie-out" is shown in the `currency` the step states (DS-FMT-05).

**Grid columns.**

Steps (step status chips apply the E-62 words of §0.4 to `steps[].status`, whose literal set is E-62 per 04 T-CLS-01; OQ-B-03 resolved by D-76):

| `step_code` | Label | Summary when finished |
|---|---|---|
| `CUTOFF` | "Cut-off known at" | `cutoff_known_at` (DS-FMT-17) |
| `INTERFACE_COMPLETENESS` | "Interface completeness" | "<n> interface runs complete" |
| `EXCEPTION_CHECK` | "Exception check" | "<n> blocking exceptions" |
| `RECOMPUTE_DIRTY` | "Recompute changed contracts" | "<groups_recomputed> groups recomputed, <groups_quarantined> quarantined" (plural keys `close.run.groups.one`, `.other`) |
| `RELEASE_SCHEDULES` | "Release schedules" | "<postings> postings, <lines> lines" |
| `FX_REMEASUREMENT` | "FX remeasurement" | "<lines> lines" |
| `NETTING_RECLASS` | "Contract balance reclassification" | "<lines> lines" |
| `INVARIANTS` | "Invariant checks" | "All invariants pass" or "<n> invariant failures" |
| `JOURNAL_SUMMARIZATION` | "Journal summarization" | "<batches> batches" |
| `EXPORT` | "Export" | "<batches> batches exported" |
| `ACKNOWLEDGEMENT_WAIT` | "Acknowledgement wait" | "<n> of <m> batches acknowledged" |
| `GL_TIE_OUT` | "Subledger to GL tie-out" | "Difference <currency> <amount>", or "No trial balance attached" while the period's current subledger-to-GL reconciliation has none (rev 1.47; BUILD_SPEC CLO-20, PRD J-13.7) |
| `DATASET_FREEZE` | "Dataset freeze" | "<n> datasets frozen" |
| `LOCK` | "Lock" | "Locked by <name>" |

Quarantined contracts:

| Header | Field | Format | Drill |
|---|---|---|---|
| Contract | `contract_id` → external id | mono link | SF-03 |
| Customer | customer name | text | none |
| Code | `code` | mono `ENGINE_INVARIANT_VIOLATION` | none |
| Message | `message` | IMP-75 copy, truncated with tooltip | none |
| Exception | `exception_no` | mono link | SF-11:item |

Rev 1.42 (BUILD_SPEC CLO-24, as built). The quarantined grid has no "Customer" column — API-S-ExceptionItem carries no customer name — and "Code" shows the item's own code; it is shown while the run is blocked by quarantined contracts or its recalculation quarantined some, and its empty state reads "No quarantined contracts" with "Every contract the run quarantined is resolved or waived. Resume the close run." Rev 1.66 (04 §16.14 rev 1.206): "Contract" shows `contract_external_id` with its drill for an item that names a contract, and `combination_group_code` (mono, no drill) for the item of a group of several contracts, which names none; the item's message names the member contracts. Earlier close runs: "Close run" (number, mono), "Status" (E-62 chip), "Started" (`created_at`, DS-FMT-17), "By" (`created_by.display_name`), "Duration" (`started_at` to `finished_at`, DS-FMT-24).

**States.**

| State | Copy |
|---|---|
| SCR-ST-03 | Title "No close run for <period label>"; description "A close run recomputes changed contracts, releases schedules and prepares journals for <entity code>."; primary "Run close" |
| `BLOCKED` | Warning banner "Close run <no> is blocked: <n> contracts were quarantined. Resolve or waive them, then resume." with "Resume close run". Rev 1.47 (04 T-CLS-01 "Ends of a run"; PRD SM-14): a run blocked by a failed invariant has its "Invariant checks" row Failed with `steps[].problem`; the banner for it is the `FAILED` copy below with the run's "Resume close run" |
| `FAILED` | SCR-ST-12 "Close run for <entity code> <period label> failed at <step label>. Nothing was committed for that step." with "Resume close run" (NFR-14) |
| SCR-ST-05 | "Could not load the close run" |

Rev 1.42 (BUILD_SPEC CLO-24, as built). SCR-ST-03 offers "Run close" to a holder of `period.close` in a period that is open, in soft close or reopened; the API refuses a run elsewhere. The `FAILED` banner — and the same banner of a run blocked by a failed invariant — shows the step's `problem.title` and `problem.detail` under the copy, so a run refused over an earlier period names it ("<period> has period-end amounts no close run has posted; run its close first."). A failed step's row reads its `problem.title`, and "Invariant checks" its count of failures. "Resume close run" is offered on a `FAILED` and on a `BLOCKED` run and "Cancel close run" while the run is `PENDING`, `RUNNING` or `BLOCKED`, each to a holder of `period.close` (SCR-PERM-02); a run that ended shows neither. "Cancel close run" answers with the toast "Close run <no> is being cancelled." while the run's current step ends, and with "Close run <no> was cancelled." where the run ends at once — a queued or a blocked run (04 §16.8). A command that does not reach the server shows "The request did not reach the server. Nothing was started or changed. Try again." Rev 1.81 (04 §16.8 rev 1.228, lane F-CLO-B's item CLO-GATE-RUN-2; the supervisor's message of 2026-10-01): "Resume close run" is refused, 409, for a run a newer one has superseded — "<no> is not the latest close run of this period. Start a new close run." (rev 1.97; 04 §16.8 rev 1.259: the API's sentence ends "Run close again." — the words of the button that starts a run — and the banner shows it as it is sent) — as it is for a run that is no longer failed or blocked and beside another run that has not ended. The page offers the command on the newest run it has read, so such a refusal means that read is out of date: the API's sentence stands in the banner above the run, and the runs, the cockpit and the quarantined contracts are read again, so that the page shows the run the period has. "Run close" in the cockpit's action bar starts the new run the sentence asks for. Rev 1.93 (the same item as §1.1's): "Run close" on a period without a run — SCR-ST-03's command — is refused and read again as the action bar's is. "Cancel close run" is refused, 409, for a run that has ended since the page read it — "<no> is <status>. Only a close run that has not ended is cancelled." A blocked run is not read again on an interval, so the page would go on offering the command: the dialog closes, the API's sentence stands in the banner above the run, and the runs, the cockpit and the quarantined contracts are read again, so that the page shows how the run ended — Succeeded: nothing is left to cancel; Failed: "Resume close run"; Cancelled, by another member's cancel: "Run close" starts another. A refusal that is no conflict stays in the dialog, which stays open with its command.

**Interactions, keyboard and copy.** "Run close": toast on success "Close run <no> succeeded." with the action "Open journal run" when a journal run was calculated. "Cancel close run" (SB-R-05): consequence "Cancelling stops the run after the current step. Steps already completed stay recorded."; Danger "Cancel close run". Completion is announced politely and failure assertively (DS-A11Y-08). Starting a run while one is active returns the active run; toast "Close run <no> is already running." Rev 1.42 (BUILD_SPEC CLO-24, as built): the toast shows to a reader who watches the run end, whoever started it, and the run header keeps the link "Open journal run" while `journal_run_id` is set, for a reader who arrives later.

**Sample world.** J-13.7: `maya` runs close for AVM-US Sep 2026; status Succeeded; "All invariants pass"; the journal run is `draft` with chip Calculated. J-14.6: incremental run; step 4 summary "1 group recomputed, 0 quarantined" (only K-03).

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Steps list | list named "Close run steps" | `SF-05-close-run-steps` |
| Step row | listitem named "Step <n> of 14, <label>, <status>" | `SF-05-row-<step_code normalised>` |
| Run indicator | progressbar named "Close run for …" | `SF-05-job-close-run` |
| Quarantined grid | grid named "Quarantined contracts" | `SF-05-grid-quarantined` |
| Earlier runs | table named "Earlier close runs" | `SF-05-grid-close-runs` |

Rev 1.42: `SF-05-banner-close-run-blocked` wraps the banner of a run blocked by quarantined contracts and `SF-05-banner-close-run-failed` the banner of a failed step.

**Light and dark.** Determinate bar fill `--accent-solid` on `--bg-active` in both themes.

**Accessibility.** Steps are `ol aria-label="Close run steps"`; durations carry `data-volatile`; the bar is `role="progressbar"` with `aria-valuetext="412 of 1,204 contracts"`.

### 1.3 SF-05:journal-preview Journal preview

| Field | Value |
|---|---|
| Screen id | SF-05:journal-preview (SCREENS.md §0.4; §14) |
| Route | `/close/:entity/:book/:period/journal-preview` |
| Roles and permissions | Read `contract.read`; "Run journals" link needs `journal.run` |
| Purpose | Show the period's journal totals by account role with the debits = credits check |
| REQ | REQ-CLS-008; REQ-JE-001 |
| Journeys | J-13.7, J-13-AC-3 |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Checklist   Close run   Journal preview   Reconciliations   History                                                  |
+----------------------------------------------------------------------------------------------------------------------+
| Journal preview (USD)                                                             [Open journal run JR-000214]       |
| Debits …        | Credits …        | Difference 0.00   (Pass) Balanced                                               |
+------------------------------------------------------------+-----------------------------+---------------------------+
| Account role                                               |                 Debit (USD) |              Credit (USD) |
| Contract liability                                         |                          …  |                        …  |
| Revenue                                                    |                          …  |                        …  |
| ...                                                        |                             |                           |
| Total                                                      |                          …  |                        …  |
+============================================================+=============================+===========================+
```

**Wireframe, 1280 px.** As 1440 px; the account role column narrows to 360 px.

```text
+--------------------------------------------------------------------------------------------------------+
| Journal preview (USD)                                                   [Open journal run JR-000214]   |
| Debits … | Credits … | Difference 0.00  (Pass) Balanced                                                 |
| Account role                                     |                Debit (USD) |          Credit (USD)  |
| ...                                              |                            |                        |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** KPI strip (DS-CMP-06 journal batch variant: debits, credits, difference); check chip (§0.4 tie-out words); static table (DS-CMP-10 native table) with DS-ELV-02 grand total rule; link button to SF-06:run.

**Data bindings.** `GET /periods/{id}/cockpit` → `journal_preview {debit_functional, credit_functional, balanced, by_account_role[]}`; `GET /journal-runs?entity&book&period&limit=1` for the link.

**Grid columns.** "Account role" (E-01 literal label in sentence case, for example `CONTRACT_LIABILITY` "Contract liability", `BILLING_CLEARING` "Billing clearing", `COST_OF_REVENUE` "Cost of revenue"); "Debit (<functional currency>)" money; "Credit (<functional currency>)" money; totals row from the API values.

**States.** SCR-ST-03: title "No journal lines for <period label>"; description "Journal lines appear once contracts in this entity and book have postings for the period." Unbalanced: chip Difference and negative banner "The journal preview does not balance. Difference <currency> <amount>. Journals cannot be submitted." (ERR-43). No journal run: text "Journal run not calculated" with link "Run journals" (SF-06).

**Interactions, keyboard and copy.** "Open journal run <run no>" navigates to SF-06:run. No commands on this tab.

**Sample world.** J-13.7: preview balanced per currency for AVM-US Sep 2026 (J-13-AC-3 asserts balancing, not totals).

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Check strip | region named "Journal preview (USD)" | `SF-05-kpi-journal-difference` |
| Table | table named "Journal preview by account role, <currency>" | `SF-05-grid-journal-preview` |

**Light and dark.** Totals rules `--rule-total` in both themes.

**Accessibility.** The check chip's word is part of the region's accessible name ("Journal preview, balanced").

### 1.4 SF-05:history Close history

| Field | Value |
|---|---|
| Screen id | SF-05:history (SCREENS.md §0.4; §14) |
| Route | `/close/:entity/:book/:period/history` |
| Roles and permissions | Read `config.read` (04 API-R-18: both reads of the screen; rev 1.67 — `contract.read` in the earlier revisions); opening the re-lock diff report needs `report.run`; downloading the stored diff file needs `report.export` or `evidence.export` |
| Purpose | Show audited period state transitions and locks with head hashes, snapshot manifests, approvals and the re-lock diff |
| REQ | REQ-CLS-001, 010, 011; BR-CLS-07 |
| Journeys | J-14.7, J-14-AC-3, J-17.2 |

**Wireframe, 1440 px (after J-14.7).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Checklist   Close run   Journal preview   Reconciliations   History                                                  |
+---------------------------------------------------+------------------------------------------------------------------+
| State transitions                                 | Locks (3)                                                        |
| 02 Oct 2026                                       | Kind        Recorded               By           Approval  Diff   |
|  (Locked)  Reopened → Closed · Marcus Webb        | Lock        02 Oct 2026 10:02 UTC  Marcus Webb  APR-…     Open > |
|  10:02:11 UTC · Approval APR-000540               | Reopen      01 Oct 2026 16:40 UTC  Priya Raman  APR-…     —      |
| 01 Oct 2026                                       | Lock        01 Oct 2026 09:14 UTC  Marcus Webb  APR-…     —      |
|  (Reopened) Closed → Reopened · Priya Raman       | Snapshot manifest 8b10…aa42  Ledger head 1,388  Audit head 9,112 |
|  "Costs of 20,500.00 on PRJ-CB-2026-01 incurred…" |                                                                  |
| ...                                               |                                                                  |
+---------------------------------------------------+------------------------------------------------------------------+
```

**Wireframe, 1280 px.** The locks grid stacks above the transitions timeline.

```text
+--------------------------------------------------------------------------------------------------------+
| Locks (3)                                                                                              |
| Lock    02 Oct 2026 10:02 UTC  Marcus Webb  APR-…  Open diff report >                                  |
| Reopen  01 Oct 2026 16:40 UTC  Priya Raman  APR-…  —                                                   |
| State transitions                                                                                      |
|  (Locked) Reopened → Closed · Marcus Webb · 02 Oct 2026 10:02:11 UTC                                   |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Transitions: DS-CMP-12 timeline, audit variant (read-only). Locks: DS-CMP-10 DataGrid. Selected lock detail: DS-CMP-09 informational drawer (`drawer=lock`). Rev 1.42 (BUILD_SPEC CLO-24, as built): the drawer is the modal variant with its title focused; from 1440 px the transitions take a column of 20 rem beside the locks, and below 1440 px the locks stack above them. The five shown columns of the grid take 808 px — the room the second column has at 1440 px beside the open rail less a scrollbar's width — with "Recorded" at 192 px: an instant of DS-FMT-17 with the cell padding is 186 px, more than the 176 px of DS-CMP-10's default. Rev 1.81 (register index 157, as built): the record's drawer is the wide variant, `--drawer-w-wide` (720 px), for the two tables it holds.

**Data bindings.** `GET /periods/{id}/transitions`; `GET /periods/{id}/locks`; diff report: SF-08:report `variance_between_closes` (RPT-38) with `p.from_period_lock_id=<previous_lock_id>` and `p.to_period_lock_id=<lock id>` (04 API-S-ReportRunCreate `parameters`; OQ-B-17 resolved by D-76); stored file `GET /files/{diff_report_file_id}/content`. Rev 1.42 (BUILD_SPEC CLO-24, as built): the transitions are read 50 at a time, newest first, and "Load older activity" reads the next page. "By" and the actor of a transition are `created_by.display_name` (API-S-Actor; 04 rev 1.139). An approval request is named by its number, read with `GET /approvals/{id}` for a reader who holds `period.close`, `period.lock`, `period.reopen_request` or `period.reopen_approve` — the permissions under which API-R-09 can make a period's request visible; any other reader, and a holder outside a request's visibility, sees a dash under "Approval" and no request in the activity — a `request_no` on the two rows is owed. Rev 1.67 (item CLO-LOCKS-READ-1; 04 §16.8 API-S-PeriodLock and "Period transitions", rev 1.207): the two rows state it — `approval_request_no` on a record of `GET /periods/{id}/locks` and on a transition of `GET /periods/{id}/transitions`, read with the row under the reader's own row scope — so every reader of the history sees the number under "Approval" and in the activity, and no request is read for it. `GET /approvals/{id}` stays the read of a request's decisions, for a reader inside its visibility (API-R-09); a reader outside it reads the number and cannot open the request.

**Grid columns: locks.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Kind | `kind` | "Lock", "Reopen", "Permanent lock" (E-63) | none |
| Recorded | `created_at` | DS-FMT-17 | none |
| By | `created_by` | user cell | none |
| Approval | `approval_request_no` (rev 1.81; `approval_request_id` → request no before rev 1.67) | mono; a link where the reader may read the request (API-R-09), text for another reader, a dash where the record states no number | SF-12:request |
| Reason | `reason_code` | E-110 label (04 table 3.4-R) | none |
| Ledger head | `ledger_head_chain_seq` | integer; `ledger_head_sha256` prefix in tooltip (rev 1.81: as text — a tooltip holds no control and is never the only place of a value, DS-CMP-27) | none |
| Audit head | `audit_head_chain_seq` | integer | none |
| Snapshot manifest | `snapshot_manifest_sha256` | hash prefix with copy | none |
| Previous lock | `previous_lock_id` | mono UUID prefix | row of that lock |
| Diff report | `diff_report_file_id` | links "Open diff report" (SF-08:report) and "Download file" | SF-08:report |

Rev 1.42 (BUILD_SPEC CLO-24, as built). The grid shows "Kind", "Recorded", "By", "Approval" and "Diff report" — the columns of the wireframe, which the second column holds at 1440 px; "Reason", "Ledger head", "Audit head", "Snapshot manifest", "Frozen as known at" and "Previous lock" are in the column chooser (DS-CMP-10) and in the record's drawer, and the line under the grid states the manifest and the two heads of the newest lock, as drawn. "Kind" is the row header and opens the drawer; its accessible name is "<kind label>, recorded <DS-FMT-17>". "Ledger head" has no tooltip: the route returns no `ledger_head_sha256` (rev 1.67: it returns it, 04 rev 1.207 — the tooltip of the table above shows its prefix where the record states a hash; a record of a book without a seal states none). "Frozen as known at" is `cutoff_known_at` with seconds (supervisor ruling R-94 (d)); a reopen record has none. "Previous lock" names that record by kind and instant and opens it, in place of a UUID prefix. "Diff report": a record that follows another lock shows "Open diff report" to a holder of `report.run` and "Download file" to a holder of `report.export` or `evidence.export` where `diff_report_file_id` is set; a reopen record shows a dash. Rev 1.81 (as built on the reads of rev 1.67). "Approval" shows the record's `approval_request_no` at once and to every reader; it becomes a link when the request itself was read, which only a reader inside its visibility can (API-R-09), and a record whose request lies outside the reader's row scope states no number and shows a dash. "Ledger head" is the sequence, described by the prefix of the record's hash as a tooltip of text — in the grid and in the line under it. The drawer states the head as its sequence with the hash, as it states "Snapshot manifest": prefix, copy button and the full value (DS-FMT-23). A record of a book without a seal states no hash, and its sequence stands alone.

Timeline event copy: "<from chip word> → <to chip word> · <actor>"; time with seconds; reason label and comment as a quoted block; approval link. Rev 1.42 (BUILD_SPEC CLO-24, as built): DS-CMP-12 leads an event with its actor and a verb phrase, and a catalogue message holds words beside its placeholders, so the event reads "<actor> changed the period from <from chip word> to <to chip word>", followed by "with approval <request no>" as a link where the reader may read the request, and "<actor> set the period to <to chip word>" for a first state; the quoted block reads "Reason: <label>. <comment>"; the event's icon is the icon of the new state's E-04 chip. Rev 1.81 (as built from the transition's `approval_request_no`, rev 1.67): the event names the request by its number for every reader — "<actor> changed the period from <from chip word> to <to chip word> with approval <request no>" — the number a link where the reader may read the request and text where not; a transition that states no number names no request.

**States.** SCR-ST-03: title "No locks yet"; description "Locks, reopens and permanent locks of <period label> appear here with their head hashes and snapshots." First lock: Diff report cell "No previous lock". Rev 1.42: for a period of the LEGACY book (API-S-Period `follows` not null; §1.1) the empty grid promises no lock — title "No locks"; description "The legacy book has no locks of its own. It follows the close of <followed book label>." — and the state changes of the row stay its history.

**Interactions, keyboard and copy.** Selecting a lock row opens the drawer "Lock <kind label> · <DD MMM YYYY HH:mm UTC>" listing every T-CLS-04 field, the certification gate results (static table "Certification") and the snapshot kinds with row counts (T-CLS-05). Rev 1.42 (BUILD_SPEC CLO-24, as built): the drawer is titled "<kind label>, recorded <DD MMM YYYY HH:mm UTC>" and lists what `GET /periods/{id}/locks` returns — kind, instant with seconds, person, approval with its decisions (approver, "on behalf of", time), reason, comment, "Frozen as known at", manifest, the two heads, the previous lock and the diff report. The certification gate results and the snapshot kinds with row counts are owed: the route returns neither. Rev 1.67 (04 §16.8 API-S-PeriodLock, rev 1.207): the route returns both — `certification[]` for the static table "Certification" (gate check code, status, count and evaluation instant; a waived gate with its waiver request's number and the count when the waiver was approved) and `snapshots[]` for the snapshot kinds with row counts (kind, row count and file hash, in E-64 order). A lock and a permanent lock hold fourteen gate results, a lock twelve datasets; a reopen holds neither. Rev 1.81 (as built; the copy approved by the supervisor on 2026-10-01). "Certification" is a static table with that caption and the headers "Gate", "Status", "Count" and "Evaluated", one row per gate in the API's order: the gate by the label the checklist gives it, its status as the checklist's chip, its count — a dash for the certification gate, which counts nothing — and the instant it was evaluated (DS-FMT-17). A waived gate has a second line under its chip, "Waiver <request no>, <n> at approval": the number of its waiver request and the count its item held when the waiver was approved. A waiver whose request lies outside the reader's row scope has no number, as a record's own request has none, and its chip stands alone. A replayed gate result is not marked: the result that the replay of a source lock laid over a sandbox's own evaluation (`replayed`) reads as any other. The datasets are a static table with the caption "Frozen datasets" and the headers "Dataset", "Rows" and "File hash", in the API's order (E-64): the dataset by the title of the report whose run the lock froze — "Revenue waterfall", "Contract balances", "Contract balance rollforward", "Remaining performance obligations", "RPO rollforward", "Disaggregation of revenue", "Revenue from obligations satisfied in prior periods", "Contract cost rollforward", "Journal entry population", "Out-of-period register", "Modification register", "Manual adjustment register" — its row count, and the hash of its file as prefix with copy and the full value (DS-FMT-23). A lock shows both tables; a permanent lock holds no dataset and shows "Certification" alone; a reopen shows neither. Both tables are named by their captions. The count and the instant of a gate stay on one line; its label and a waiver's line break where the drawer's width asks for it. Enter on a cell opens the record, except under "Approval" and "Diff report", which follow their link. The URL names the drawer and not the record (SCR-URL-12 gives the record no parameter): a link with `drawer=lock` opens the newest record.

**Sample world.** J-14-AC-3 re-lock diff (asserted), shown on SF-08:report `variance_between_closes`: K-03 `PRJ-CB-2026-01` Sep 2026 revenue 197,294.12 → 229,852.94 (+32,558.82); contract asset and unbilled receivable 97,294.12 → 129,852.94 (+32,558.82; the PRD's "debit net position", SB-R-10); remaining performance obligations 552,705.88 → 520,147.06 ((32,558.82)); both lock ids listed.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Locks grid | grid named "Locks" | `SF-05-grid-locks` |
| Transitions | list named "Activity" | `SF-05-timeline-transitions` |
| Diff link | link named "Open diff report" | `SF-05-row-diff-report` |

**Light and dark.** Timeline connectors `--border-default`; quoted comments on `--bg-subtle`.

**Accessibility.** Timeline per DS-CMP-12 with `time datetime`; hash prefixes have accessible names with the full value (DS-A11Y-12). Rev 1.81: the copy button of a dataset's hash is named "Copy file hash of <dataset>" and that of the ledger head "Copy Ledger head"; the ledger head's tooltip is described text on its sequence, whose trigger is focusable outside the grid (DS-CMP-27) while inside the grid the cell holds the focus; a row of either table is headed by its gate or its dataset.

### 1.5 SF-05:multi-entity Multi-entity close

| Field | Value |
|---|---|
| Screen id | SF-05:multi-entity |
| Route | `/close/multi-entity` (RT-27) with `period`, `book` |
| Roles and permissions | Read `period.close` (RT-27); start close runs `period.close` |
| Purpose | Start close runs for several entities of one period with independent status and exceptions; no lock is attempted |
| REQ | REQ-ENT-006; REQ-CLS-012 |
| Journeys | J-13.16, J-13-AC-9 |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Multi-entity close · Sep 2026 · ASC 606                                                                              |
| Entities  [AVM-DE x] [AVM-UK x] [AVM-JP x] {Add entity v}                                     [*Start close runs]    |
| Close runs start for each entity independently. No period is locked.                                                 |
+----------+------------------------+--------------+--------------------------------+-------------+--------------------+
| Entity   | Period                 | Close run    | Status                         | Exceptions  | Cockpit            |
| AVM-DE   | Sep 2026 (Soft close)  | CLS-000032   | (Running) Step 5 of 14         | 0           | Open cockpit >     |
| AVM-UK   | Sep 2026 (Period open) | CLS-000033   | (Succeeded)                    | 0           | Open cockpit >     |
| AVM-JP   | Sep 2026 (Period open) | CLS-000034   | (Queued)                       | 0           | Open cockpit >     |
+----------+------------------------+--------------+--------------------------------+-------------+--------------------+
```

**Wireframe, 1280 px.** The Cockpit column becomes a row action (CaretRight). Rev 1.42 (BUILD_SPEC CLO-24, as built): the six columns take 1,128 px and the rail is collapsed below 1440 px (SCREENS §1.1), so the Cockpit column stays a column at 1280 px.

```text
+--------------------------------------------------------------------------------------------------------+
| Multi-entity close · Sep 2026 · ASC 606                                                                |
| Entities [AVM-DE x] [AVM-UK x] [AVM-JP x] {Add entity v}                        [*Start close runs]    |
| AVM-DE  Sep 2026 (Soft close)  CLS-000032  (Running) Step 5 of 14  0  >                                |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Entity selector: DS-CMP-21 multi-select combobox. Runs: DS-CMP-10 DataGrid with DS-CMP-24 compact progress in the Status cell.

**Data bindings.** Entity options `GET /entities?is_active=true` filtered to those keeping `book`; `POST /close-runs/multi-entity` `{entity_codes, book, period_key}` → 200 `{results: [{entity_code, close_run_id, job_id, problem}]}`, one independent start per entity in `entity_codes` order (04 API-R-39, §16.8; OQ-B-23 resolved by D-76); `GET /close-runs?book&period&entity=<code>` per entity, polled every 2 s while any is running; exceptions `GET /exceptions?entity=<code>&period=<key>&status=OPEN,IN_PROGRESS&count=true`. Rev 1.42 (BUILD_SPEC CLO-24; the supervisor's ruling on the lane's question C): `POST /close-runs/multi-entity` is BUILD_SPEC CLO-21 and stays the binding of "Start close runs". INTERIM, until CLO-21 is on main: the screen sends one `POST /close-runs` `{entity_code, book, period_key}` per chosen entity, in the order shown (code order), and each row reads its own answer — 202 the new run, 200 the run that had not ended, a problem its `detail`. The period and book are the context's (BR-UX-01), the period key read on the calendar of the context entity; each entity closes the period of its own calendar with the same start and end dates (WLD-P-05), read from `GET /periods?entity=<code>&book=<book>`. When the page opens, the entities whose run of the period has not ended are chosen (`GET /close-runs?book=<book>&status=PENDING,RUNNING,BLOCKED`), so the runs that still move are in view; the choice is page state, not a URL parameter.

**Grid columns.** "Entity" (code, mono); "Period" (per-entity calendar label and period chip; AVM-JP shows "Sep 2026" for `FY2027-P06`, WLD-P-05); "Close run" (number, mono link to SF-05:close-run of that entity); "Status" (E-62 chip with step caption); "Exceptions" (count link to SF-11); "Cockpit" (link to SF-05). Rev 1.42 (BUILD_SPEC CLO-24, as built): "Status" shows the E-62 chip with the caption "Step <n> of 14" and no bar; an entity chip of the selector reads "<code> · <name>".

**States.** SCR-ST-03 before starting: title "No close runs started"; description "Choose the entities to close for <period label>. Each entity's run and exceptions are recorded independently." Validation on press without entities: "Choose at least one entity." A result that carries `problem` leaves that entity's existing run in place; for 409 `invalid-transition` (an active close run) the row shows that run and the toast reads "<entity code> already has a running close run. It was not started again."; any other problem shows its ERR copy in the row's Status cell. Rev 1.42 (BUILD_SPEC CLO-24, as built with the interim start): a row is a chosen entity with a close run of the period or an answer of this page. An entity whose calendar has no period with the context period's dates is not started and its row reads "<entity code> has no period from <date> to <date>." A request that does not reach the server reads "The request did not reach the server. No close run was started. Try again." in the row. A reader without `period.close` sees the access-limited state of SCR-PERM-01 with the permission named "running the period close". In a LEGACY context (the context period's `follows` is not null; §1.1) the page offers no entity and starts nothing: under its title it shows the cockpit's line (`SF-05-follows`) with the link "Close several entities in <followed book label>" to this page in the followed book, and reads no close run.

**Interactions, keyboard and copy.** "Start close runs" posts once; the grid fills from the response. Row Enter opens the entity's close run.

**Sample world.** J-13.16 (asserted): AVM-DE, AVM-UK, AVM-JP for Sep 2026; three close run records with independent statuses (J-13-AC-9).

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Entity selector | combobox named "Entities" | `SF-05-multi-entity-entities` |
| Runs grid | grid named "Close runs" | `SF-05-grid-multi-entity` |
| Row | row header "<entity code>" | `SF-05-row-<entity code normalised>` (for example `SF-05-row-avm-de`) |

**Light and dark.** Chips only.

**Accessibility.** Removing an entity chip announces "Removed <entity code>" politely.

## 2. Reconciliations (SF-05)

### 2.1 SF-05:reconciliations Reconciliations

| Field | Value |
|---|---|
| Screen id | SF-05:reconciliations (SCREENS.md §0.4; §14) |
| Route | `/close/:entity/:book/:period/reconciliations` |
| Roles and permissions | Read `contract.read` (API-R-40). "Generate reconciliation": `recon.prepare` (Revenue Accountant), rendered while the period is `open`, `closing` or `reopened` (PRD SM-09; rev 1.32). Integration Admin holds neither sign-off permission (SoD-7) |
| Purpose | List the period's reconciliations by kind with status, variances and sign-offs, and generate new ones |
| REQ | REQ-CLS-015, 016, 017; REQ-RPT-006, 010 |
| Journeys | J-13.10 to J-13.12, J-13-ALT-2, J-23.9 |

**Wireframe, 1440 px (after J-13.11).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Checklist   Close run   Journal preview   Reconciliations   History                                                  |
+----------------------------------------------------------------------------------------------------------------------+
| Reconciliations · Sep 2026                                                              [*Generate reconciliation v] |
+------------+-------------------------+-----------------------------------------+-----------+-------------+------------+
| Number     | Kind                    | Status                                  | Variances | Preparer    | Reviewer   |
| REC-000041 | Billing to subledger    | (Auto-certified) under AUTO-REC-01 v1   | 0         | System      | —          |
| REC-000042 | Subledger to GL         | (Prepared) (Difference)                 | 1         | Maya Chen   | —          |
+------------+-------------------------+-----------------------------------------+-----------+-------------+------------+
```

**Wireframe, 1280 px.** Preparer and Reviewer merge into one "Sign-offs" column.

```text
+--------------------------------------------------------------------------------------------------------+
| Reconciliations · Sep 2026                                              [*Generate reconciliation v]   |
| REC-000041  Billing to subledger  (Auto-certified) under AUTO-REC-01 v1   0   System · —               |
| REC-000042  Subledger to GL       (Prepared) (Difference)                 1   Maya Chen · —            |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-10 DataGrid; DS-CMP-28 menu button "Generate reconciliation"; DS-CMP-19 chips; DS-CMP-24 progress row while generating. Under the grid, the disclosure "Earlier generations (<n>)" with a DS-CMP-10 static table of the generations that a later one replaced (rev 1.32).

**Data bindings.** `GET /reconciliations?entity&book&period&is_current=true`; sign-offs from `GET /reconciliations/{id}` (T-CLS-08 rows; the list rows carry them as well); `POST /reconciliations` `{kind, entity_code, book, period_key}` → 202 job `RECONCILIATION_GENERATE` (generate), whose response header `X-Erev-Reconciliation-Id` and job `result.href` name the reconciliation. Every generation is a new reconciliation (04 T-CLS-06, rev 1.121): the grid lists the rows with `is_current = true`, one per kind, through the list filter `is_current` (rev 1.27). The "Earlier generations" are the rows of a second read with `is_current=false` (`sort=-created_at`, pages of 200; rev 1.32).

**Grid columns.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Number | `reconciliation_no` | mono link | SF-05:reconciliation |
| Kind | `kind` | E-58 label (§1.1) | none |
| Status | `status`; `variance_count` | chip; second chip Difference when variances exist and not certified; caption "under <rule key> v<n>" for `AUTO_CERTIFIED` | none |
| Variances | `variance_count` | integer | SF-05:reconciliation |
| Unexplained other (<currency>) | `unexplained_other_amount` | money; em dash when null | SF-05:reconciliation |
| Preparer | preparer sign-off `signer_id` | user cell; "System" for auto-certification | none |
| Reviewer | reviewer sign-off `signer_id` | user cell | none |
| Certified | `certified_at` | DS-FMT-17 | none |
| Report run | `report_run_id` → run no | mono link | SF-08:run |

Default view (rev 1.32): Number, Kind, Status, Variances, Preparer and Reviewer, the columns of the 1440 px wireframe; below 1440 px Preparer and Reviewer are the one column "Sign-offs" (`<preparer> · <reviewer>`). "Unexplained other (<currency>)", "Certified" and "Report run" start hidden and stay in the column chooser. "Report run" is the run number as text until SF-08:run is built (XR-14). The grid is named "Reconciliations"; its toolbar shows the period label beside the name and carries "Generate reconciliation".

**States.** SCR-ST-03: title "No reconciliations for <period label>"; description "Generate the billing-to-subledger and subledger-to-GL reconciliations before submitting the period for lock."; primary "Generate reconciliation". Generating: a pinned first row "Generating <kind label>" with the job indicator; the row sits directly above the grid (rev 1.32). A failed generation leaves SCR-ST-12 there with "Retry", which generates again, and a refused `POST /reconciliations` (for example 409 `invalid-transition` outside an open period) shows the problem's title and detail above the grid (rev 1.32).

**Interactions, keyboard and copy.** Menu items: the kinds `POST /reconciliations` generates (04 §16.8 API-S-ReconciliationCreate; XR-14), that is "Billing to subledger" and "Subledger to GL" (BUILD_SPEC CLO-17; rev 1.32). "Contract balance rollforward" and "RPO rollforward" are owed: the rollforward kinds are report runs and the route answers 422 `validation-failed` on `kind` for them, so the menu does not list them (rev 1.32; supervisor ruling on lane F-CLO-WEB's read-in, Q1). "Subledger to GL" creates the reconciliation and opens SF-05:reconciliation in its "Attach trial balance" state, when its job has ended, in place of the toast (rev 1.32). Toast "Generated <reconciliation no> (<kind label>)." "Earlier generations (<n>)" (rev 1.32): closed by default; opened, it shows the note "Each was replaced by a later generation of its kind and is kept as history." and the columns Number (mono link to SF-05:reconciliation), Kind, Status (the E-59 chip and the chip Difference), Variances and Generated (`created_at`, DS-FMT-17), newest first. Enter on a row of the grid opens SF-05:reconciliation.

**Sample world.** J-13.10 (asserted): billing to subledger, zero variance, `AUTO_CERTIFIED` under rule `AUTO-REC-01` version 1. J-13.11 subledger to GL with one variance.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Grid | grid named "Reconciliations" | `SF-05-grid-reconciliations` |
| Row | row header "<reconciliation no>"; tests locate by kind label | `SF-05-row-<kind normalised>` (for example `SF-05-row-subledger-to-gl`) |
| Generate menu | button named "Generate reconciliation" | none |
| Generating job (rev 1.32) | progressbar named "Generating <kind label>" | `SF-05-job-reconciliations` |
| Earlier generations (rev 1.32) | button named "Earlier generations (<n>)"; table named "Earlier generations (<n>)" | `SF-05-grid-reconciliation-history` |

**Light and dark.** Chips only.

**Accessibility.** The menu follows APG Menu Button (DS-CMP-28).

### 2.2 SF-05:reconciliation Reconciliation detail

| Field | Value |
|---|---|
| Screen id | SF-05:reconciliation (SCREENS.md §0.4; §14) |
| Route | `/close/:entity/:book/:period/reconciliations/:reconciliationId` (UUID) |
| Roles and permissions | Read `contract.read`. Attach trial balance, explain differences, sign as preparer (MFA-verified session): `recon.prepare`. Sign as reviewer: `recon.signoff` with step-up MFA; reviewer ≠ preparer (DB-10); not Integration Admin (SoD-7). Reopen the reconciliation: `recon.signoff` — a reopen discards the reviewer's sign-off (rev 1.27; supervisor ruling R-54 (c)). A command control renders only on the current reconciliation (`is_current`) while the period is `open`, `closing` or `reopened`; "Sign as reviewer" is rendered for no holder of `integration.manage`, whatever else the role holds, because the command answers 403 (SoD-7; 04 §16.8; rev 1.32). Rev 1.42 (the supervisor's ruling on the lane's question B): "Upload CSV" stores the file under the purpose `IMPORT_SOURCE`, which needs `import.upload`; the default Revenue Accountant holds `recon.prepare` and `import.upload`, and a custom preparer role needs both to upload. A file purpose of its own for a trial balance is noted for the file store (item FILE-TB-PURPOSE-1) and not promised |
| Purpose | Show totals by account and currency, itemised differences with classification and explanation, and the preparer and reviewer sign-offs that freeze the snapshot |
| REQ | REQ-CLS-015, 016, 017; REQ-INT-009; CTL-024, CTL-025, CTL-026 |
| Journeys | J-13.11, J-13.12, J-13-AC-2, J-13-ALT-2, J-23.9 |

**Wireframe, 1440 px (J-13.11 before signing).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Close > AVM-US > ASC 606 > Reconciliations                                                                            |
| REC-000042 · Subledger to GL · Sep 2026   (Draft) (Difference)                                  [*Sign as preparer] ...|
| Source NetSuite (mock) trial balance · pulled 12 Sep 2026 15:20 UTC   Report run RPT-000401                           |
| Key figures (USD)   Accounts 12 │ Subledger total … │ GL total … │ Difference 250.00 │ Variances 1                   |
+----------------------------------------------------------------------------------------------------------------------+
| Totals by account                                                                                                    |
| Account   Currency         Subledger (USD)             GL (USD)          Difference (USD)                            |
| 2100      USD                            …                    …                    250.00  (Difference)              |
| ...                                                                                                                  |
+----------------------------------------------------------------------------------------------------------------------+
| Differences (1)                                                                                                      |
| Kind                               Account  Reference    Subledger (USD)  GL (USD)  Difference (USD)  Risk  Explanation|
| Direct GL entry to a subledger-    2100     JE-NS-88121             0.00    250.00   fn     250.00  <High risk>      |
| controlled account                          Manual accrual posted in NetSuite by AP; reversed on 01 Oct 2026 by…     |
+----------------------------------------------------------------------------------------------------------------------+
| Sign-offs   Preparer —   Reviewer —                                                                                  |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** The Explanation column moves under each difference row as a second line; the key figures strip wraps. Built departure (rev 1.32): DS-CMP-10 rows are one line, so "Explanation" stays a column with its tooltip and the grid scrolls horizontally; the full text is read in the drawer.

```text
+--------------------------------------------------------------------------------------------------------+
| REC-000042 · Subledger to GL · Sep 2026  (Draft) (Difference)                      [*Sign as preparer]  |
| Accounts 12 │ Difference 250.00 │ Variances 1                                                           |
| Direct GL entry to a subledger-controlled account  2100  JE-NS-88121  0.00  250.00  250.00 <High risk>  |
|   Manual accrual posted in NetSuite by AP; reversed on 01 Oct 2026 by JE-NS-88410.                      |
| Sign-offs  Preparer —  Reviewer —                                                                       |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.**

| Region | Components | Content |
|---|---|---|
| Header | DS-CMP-06 record header (reconciliation variant) | Breadcrumb "Close" (the close area), "<entity code> · <book label>" (the period's cockpit), "Reconciliations" (SF-05:reconciliations) (rev 1.32); `h1` "<reconciliation no> · <kind label> · <period label>"; chips; meta "Source" (trial balance source and time, or "No source attached"; for `BILLING_TO_SUBLEDGER` "Billing documents known at <`as_of_known_at`, DS-FMT-17>", rev 1.32), "Report run" (the run number as text until SF-08:run is built); KPI strip "Key figures (<currency>)": "Accounts", "Subledger total", "<source label> total", "Difference", "Variances" (rule below). Rev 1.32, the "Source" of a subledger-to-GL reconciliation: "<connection name> trial balance · pulled <DS-FMT-17>" for a pull, "<file name> · uploaded <DS-FMT-17>" for an upload, "Trial balance attached" where the record names no request |
| Attach trial balance | DS-CMP-31 segmented control "Pull from <connection name>" / "Upload CSV"; DS-CMP-18 dropzone anatomy | Only for `SUBLEDGER_TO_GL` without a source. The controls render for a holder of `recon.prepare` on the current draft while the period is `open`, `closing` or `reopened` (rev 1.32): one segment per connection of `gl_connections` (beyond four connections, one segment "Pull from a GL connection" with the select "GL connection"), and "Upload CSV" for a holder of `import.upload`, the permission of `POST /files` purpose `IMPORT_SOURCE` (04 API-R-12). Without a connection the preparer reads, in place of the state's description, "No GL connection is set up for <entity code>.", followed by "Upload a CSV of account balances." and the upload alone for that holder. Every other reader sees the state without controls |
| Totals by account | DS-CMP-10 DataGrid | One row per account and currency |
| Differences | DS-CMP-10 DataGrid | T-CLS-07 items |
| Explain difference | DS-CMP-09 modal drawer (form) | Explanation editor |
| Sign-offs | DS-CMP-12 approval-history variant | Preparer and reviewer statements with signer and UTC time |

**Key figures (rev 1.32).** Every figure is an API value; the client adds no money (DG-FE-08): the strip reads API-S-Reconciliation `summary`, one row per currency, and `variance_count`. With several currencies the strip is headed "Key figures" and each figure shows one line per currency with its ISO code (DS-FMT-12). "Accounts" is `account_count` and is left out where every row counts none (billing).

**Data bindings.** `GET /reconciliations/{id}`; `GET /reconciliations/{id}/items`; `POST /reconciliations/{id}/attach-trial-balance` (`{source: "ADAPTER", integration_connection_id}` or `{file_id}` after `POST /files` purpose `IMPORT_SOURCE`) → 202 job `RECONCILIATION_GENERATE` (04 API-S-ReconciliationAttach, rev 1.27; a file that cannot be compared is refused by the request, 422 with its rows); `PATCH /reconciliations/{id}/items/{item_id}` `{explanation}` with `If-Match`; `POST /reconciliations/{id}/prepare`; `POST /reconciliations/{id}/sign` `{role: "REVIEWER", statement_accepted: true}`; `POST /reconciliations/{id}/reopen` `{reason}`. Read members of API-S-Reconciliation (04 §16.8, rev 1.121; rev 1.27): the key figures strip reads `summary` (one row per currency: `account_count`, `subledger_amount`, `source_amount`, `difference`) and `variance_count` — the client sums no money (DS-FMT-12; dev-guide DG-FE-08); the header's "Source" reads `trial_balance` (`integration_connection.name` with "pulled <attached_at>", or `file.name` with "uploaded <attached_at>"; "No source attached" while `attached_at` is null); the "Generating or pulling" state is `trial_balance.job.state` `QUEUED` or `RUNNING` and the "Pull failed" banner is `FAILED` with `trial_balance.integration_connection.name` and `trial_balance.job.problem.title` — read by re-reading the reconciliation, because `GET /jobs/{id}` answers only the job's initiator and an auditor; "Pull from <connection name>" offers `gl_connections` (present for a holder of `recon.prepare`), and with none only "Upload CSV" is offered.

**Grid columns: totals by account.** "Account" (`totals[].account_code`, mono); "Currency" (mono); "Subledger (<currency>)" (`subledger_amount`); "<source label> (<currency>)" where the source label is "GL" for `SUBLEDGER_TO_GL`, "Billing" for `BILLING_TO_SUBLEDGER` and "Rollforward" for the rollforward kinds (`source_amount`); "Difference (<currency>)" (`difference`, chip Difference when non-zero, DS-FMT-30). Mixed currencies: one totals row per currency (DS-FMT-12). "Account" starts hidden where no totals row carries an account (rev 1.32). Rev 1.86 (04 T-CLS-06 "Role basis", rev 1.253; supervisor rulings R-69 and R-74): a `SUBLEDGER_TO_GL` row of a contract balance role (`totals[].account_role` set) shows in "Account" the role's E-01 label followed by its accounts — "Contract liability · 2100"; several accounts comma-separated from `account_codes`; the label alone when the role has no account. A row marked `not_stated` shows the neutral chip "Not stated" in "Subledger (<currency>)" and an em dash in "Difference (<currency>)" (both members are null), keeps its "GL (<currency>)" amount, and carries `not_stated.reason` on a second line with the external ids of `not_stated.contracts` as links to SF-03, followed by "and <n> contracts outside your entities" when `not_stated.contract_count` exceeds the contracts named (n is the difference; "1 contract" in the singular). The key figures strip adds "Not stated <n>" (`summary[].not_stated_count`) when n is above zero; its sums leave those rows out of "Subledger total" and "Difference".

**Grid columns: differences.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Kind | `item_kind` | `UNMATCHED_SOURCE` "Unmatched in source"; `UNMATCHED_SUBLEDGER` "Unmatched in subledger"; `AMOUNT_VARIANCE` "Amount variance"; `UNPOSTED_BATCH` "Unposted batch"; `TIMING` "Timing"; `DIRECT_GL_ENTRY` "Direct GL entry to a subledger-controlled account"; `OTHER` "Other"; `NOT_STATED` "Not stated by the subledger" (rev 1.86: the one item of a role row marked `not_stated`; it carries the ledger's balance as source and as difference and is explained like any other) | none |
| Account | `account_code` | mono; for an item of a role row that names no account (`account_role` set, `account_code` null) the role's E-01 label (rev 1.86) | none |
| Contract | `contract_id` → external id | mono link; em dash when null | SF-03 |
| Reference | `invoice_number` (billing) or `gl_document_reference` (subledger to GL; 04 T-CLS-07; OQ-B-25 resolved by D-76) | mono | none |
| Subledger (<currency>) | `subledger_amount` | money | none |
| Source (<currency>) | `source_amount` | money | none |
| Difference (<currency>) | `difference` | money, Explain trigger (owed: API-R-49 names no object type for a reconciliation item, item REC-EXPLAIN-1, so the figure is plain money; rev 1.32) | Explain |
| Risk | `is_high_risk` | outline chip "High risk" | none |
| Explanation | `explanation` | text with tooltip; ghost button "Add explanation" when empty and editable | Explain difference drawer; read-only outside a draft (rev 1.32) |
| Resolved | `resolved_at`, `resolved_by` | DS-FMT-17 and user | none |

Default view (rev 1.32): a billing reconciliation hides "Account", "Risk" and "Resolved", every other kind "Contract" and "Resolved"; the column widths keep the amounts and "Explanation" in view at 1440 px, so the long kind label of a direct GL entry truncates with its tooltip (built departure from the wireframe's two-line cell: DS-CMP-10 rows are one line); a "Currency" column (DS-FMT-12) precedes the amounts when the differences carry several currencies. Every column stays in the column chooser. The grid reads every difference in the order it was itemised.

**States.**

| State | Copy |
|---|---|
| Differences empty | Title "No differences"; description "Subledger and source totals agree for every account." |
| No source (subledger to GL) | Title "Attach a trial balance"; description "Pull the trial balance for <entity code> <period label> from the GL connection, or upload a CSV of account balances." |
| Generating or pulling | DS-CMP-24 "Generating Subledger to GL"; shown to every reader from `trial_balance.job`, the record being read again every 2 s while the job is `QUEUED` or `RUNNING`; the attach controls are not rendered meanwhile (rev 1.32) |
| Pull failed | Negative banner "The trial balance could not be pulled from <connection name>: <problem title>. Upload a CSV instead." |
| Upload failed (rev 1.32) | Negative banner "The trial balance file could not be compared: <problem title>." with the problem's detail (`trial_balance.job.problem`); the attach controls stay |
| Certified | Info banner "Certified at lock on <DD MMM YYYY HH:mm UTC>. Reopen the period to change it."; every edit control hidden |
| Prepared | Info banner "Snapshot frozen for review."; the preparer also reads "You prepared this reconciliation. Another user must review it." (DB-10) |
| Superseded (rev 1.32; supervisor ruling R-54 (b)) | Chip Superseded after the status chips; info banner "<reconciliation no> was replaced by <later reconciliation no>. Work on the current reconciliation." with the link "Open <later reconciliation no>"; every edit control hidden |
| Reopened (rev 1.32) | Warning banner "<reconciliation no> is reopened. Generate it again and repeat the sign-offs." with the link "Reconciliations"; every edit control hidden |
| Period not open (rev 1.32) | For a current `DRAFT`, `PREPARED` or `REVIEWED` reconciliation whose period is not `open`, `closing` or `reopened`: info banner "<period label> is not open for <entity code>. A reconciliation is generated and signed while the period is open, in soft close or reopened."; every edit control hidden |
| Command refused (rev 1.32) | A 409 `invalid-transition` (the reconciliation was replaced, signed or reopened meanwhile; the snapshot changed; the period state) or a 403 `self-approval` closes the dialog or drawer, shows a negative banner with the problem's title and detail, and reads the record again, so a replaced reconciliation then shows the Superseded state. Rev 1.85 (the lane's finding F4; the supervisor's ruling of 2026-10-01): a 403 `forbidden` of a signature or of the reopen is shown in that banner as well. It was a negative toast (SCREENS SCR-PERM-05), and PRD ERR-01's two sentences take three lines of the two a toast shows (DESIGN_SYSTEM DS-CMP-22). A 403 that carries no sentence of its own takes ERR-01's, whole: "You do not have permission to sign this reconciliation. Ask a workspace administrator if you need it." |
| SCR-ST-07 | "Reconciliation not found" |

**Interactions, keyboard and copy.**

- "Pull trial balance from <connection name>" (J-13.11 "Pull trial balance from NetSuite") starts the pull; the CSV option accepts ".xlsx or .csv at most 50 MiB" (ERR-37 import copy). Rev 1.32: the chosen file shows as "<name> · <size> bytes" and is sent by its own button, "Upload and compare" (`POST /files` purpose `IMPORT_SOURCE`, then the attach) — the source is written once (04 T-CLS-06), so choosing a file sends nothing; without a file the button reports "Choose a CSV or XLSX file." (DS-CMP-21), and a refused upload shows the problem's detail on the dropzone (ERR-37). A file that cannot be compared (422) shows the problem in the section with each finding as "Row <n>, <column>: <message>" (a finding about the file as a whole as its message alone); a 409 is the "Command refused" state. After a failed pull the section opens on "Upload CSV". The differences are read once the reconciliation has its source.
- "Add explanation" opens the drawer "Explain difference": a static table of the item; field "Explanation (required)", minimum 10 characters; buttons "Cancel", "Save explanation". Explanations are editable while the status is `DRAFT`. "Save explanation" sends the item's `If-Match`; success closes the drawer with the toast "Explanation saved." The explanation text of a row opens the same drawer; outside a draft the drawer is titled "Explanation of the difference" and shows the static table, the explanation in full and who explained it and when, without a field (rev 1.32).
- "Sign as preparer": DS-CMP-11 confirmation "Sign <reconciliation no> as preparer?"; statement "I prepared this reconciliation and explained every difference above the threshold." with checkbox "I confirm this statement" (OQ-B-05); buttons "Cancel", "Sign as preparer". When differences above the threshold lack explanations the button stays enabled and pressing it reports "Explain <n> differences above the threshold before signing." (SM-09; DS-CMP-21) in a negative banner of the header, and no dialog opens; pressing the dialog's button without the checkbox reports "Confirm the statement before signing." (rev 1.32). `mfa-required` opens the SCR-PERM-05 verification modal for a user with a factor and navigates to `/mfa/enrol` for a user without one (rev 1.32). Success: chip Prepared; info banner "Snapshot frozen for review."; toast "Signed <reconciliation no> as preparer." (rev 1.32).
- "Sign as reviewer": same pattern, statement "I reviewed this reconciliation, its differences and their explanations.", SCR-PERM-05 step-up. The preparer sees "You prepared this reconciliation. Another user must review it." and no button (DB-10). An Integration Admin sees no sign-off control (SCR-PERM-02; J-23.9). Success: chip Reviewed and the toast "Signed <reconciliation no> as reviewer." (rev 1.32).
- "Reopen reconciliation" (overflow; status `PREPARED` or `REVIEWED`; holders of `recon.signoff`; SB-R-05): consequence "The reconciliation is reopened. Its sign-offs stay in the history; generate it again and repeat them."; Danger "Reopen reconciliation". The reopened reconciliation stays `REOPENED` and is never reused: "Generate reconciliation" creates the next one (04 T-CLS-06; rev 1.27). A `CERTIFIED` reconciliation has no reopen action (the Certified state below; the API answers 409 `invalid-transition`). Success: chip Reopened and the toast "Reopened <reconciliation no>." (rev 1.32).

**Sample world.** J-13.11 (asserted): difference 250.00 on account 2100, kind "Direct GL entry to a subledger-controlled account", reference `JE-NS-88121`, high risk; explanation "Manual accrual posted in NetSuite by AP; reversed on 01 Oct 2026 by JE-NS-88410."; `maya` signs as preparer (Prepared). J-13.12: `priya` signs as reviewer (Reviewed). J-13.14: Reconciled "Certified at lock". Fixture WLD-F-32.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Totals grid | grid named "Totals by account" | `SF-05-grid-recon-totals` |
| Differences grid | grid named "Differences" | `SF-05-grid-recon-items` |
| Difference row | row header "<kind label>"; tests filter by reference text | `SF-05-row-<reference normalised>` (for example `SF-05-row-je-ns-88121`) |
| Explanation drawer | dialog named "Explain difference" | `SF-05-drawer-explain-difference` |
| Sign-offs | region named "Sign-offs" | `SF-05-signoffs` |
| Key figures (rev 1.32) | region named "Key figures (<currency>)" | `SF-05-kpi-strip`; a figure `SF-05-kpi-<figure>` with `accounts`, `subledger-total`, `source-total`, `difference` or `variances` |
| State banners (rev 1.32) | the banner text | `SF-05-banner-<state>` with `superseded`, `certified`, `reopened`, `frozen`, `period`, `refused`, `unexplained`, `own-preparation` or `attach-failed` |
| Attach trial balance (rev 1.32) | radiogroup named "Trial balance source"; buttons "Pull trial balance from <connection name>" and "Upload and compare"; progressbar named "Generating Subledger to GL" | `SF-05-attach-trial-balance`; the job `SF-05-job-trial-balance`; the dropzone `SF-05-trial-balance-dropzone`, its file input `SF-05-trial-balance-file` and the chosen file `SF-05-trial-balance-selected` |

**Light and dark.** Difference chips and the high-risk outline chip in both themes; verify the frozen-snapshot info banner on `--bg-surface`.

**Accessibility.** The Risk cell's accessible name is "High risk"; the sign-off statements are the labels of their checkboxes (each checkbox is labelled by "I confirm this statement" together with its statement; rev 1.32); the Explain trigger on "Difference" is named "Explain Difference, USD 250.00".

## 3. Journal runs and GL export (SF-06)

The Journals area renders `h1` "Journals" and the route tabs **Journal runs** (SF-06) and **Entries by date range** (SF-06:entries) (SCR-IA-02). A journal run record (SF-06:run) renders its own `h1` and route tabs **Summary** (SF-06:run), **Lines** (SF-06:run-lines) and **Batches** (SF-06:run-batches).

### 3.1 SF-06 Journal runs

| Field | Value |
|---|---|
| Screen id | SF-06 |
| Route | `/journals` (RT-28) with `entity`, `period`, `book`, `f.state`, `f.mode`, `sort`, `view` |
| Roles and permissions | Read `contract.read`. "Run journals": `journal.run` (Revenue Accountant). Approval is decided in SF-12 with `journal.approve` |
| Purpose | List journal runs per entity, book and period with state, totals and acknowledgement progress, and start new runs |
| REQ | REQ-JE-001, 004, 010; REQ-ENT-006 |
| Journeys | J-01.14, J-13.8, J-13.9, J-14.6, J-16.5, J-18.5, J-21.5 |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Journals                                                                                           [*Run journals]   |
| Journal runs   Entries by date range                                                                                 |
+----------------------------------------------------------------------------------------------------------------------+
| 12 journal runs   {All runs v}                                                     Columns  Export v  ...            |
| [Search runs____]  [Entity is AVM-US x] [Period is Sep 2026 x]  [Filter]  Clear all                                  |
| [!] Journal calculation for AVM-UK Sep 2026 failed: Account mapping missing. Open exception >                        |
+-----------+--------+---------+----------+-------+----------------------------+-------+-------------+-------------+-----+
| Run       | Entity | Book    | Period   | Mode  | State                      | Lines | Debit (USD) | Credit (USD)| Ack |
| JR-000214 | AVM-US | ASC 606 | Sep 2026 | Gross | (Posted)                   |   164 |           … |           … | 2/2 |
| JR-000209 | AVM-US | ASC 606 | Aug 2026 | Gross | (Posted)                   |   158 |           … |           … | 2/2 |
+-----------+--------+---------+----------+-------+----------------------------+-------+-------------+-------------+-----+
```

**Wireframe, 1280 px.** Columns Grain, Approved, Exported and Created by are hidden by the default view (available in Columns); money columns keep their width (DS-AP-10).

```text
+--------------------------------------------------------------------------------------------------------+
| Journals                                                                          [*Run journals]      |
| Journal runs   Entries by date range                                                                   |
| 12 journal runs  {All runs v}   [Entity is AVM-US x] [Period is Sep 2026 x] [Filter]                   |
| Run        Entity  Period    Mode   State      Lines   Debit (USD)   Credit (USD)   Ack               |
| JR-000214  AVM-US  Sep 2026  Gross  (Posted)     164             …              …   2/2               |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.**

| Region | Components | Content |
|---|---|---|
| Area header | DS-CMP-06 plain header; DS-CMP-07 route tabs | `h1` "Journals"; primary "Run journals" |
| Calculation failures | DS-CMP-29 negative banner, one per failed `JOURNAL_RUN_CALCULATE` job of the context in the last 7 days | "Journal calculation for <entity code> <period label> failed: <problem title>." action "Open exception" |
| Runs grid | DS-CMP-10 DataGrid with DS-CMP-13 FilterBar | Rows per run; a pinned progress row per calculating job |
| Run journals form | DS-CMP-11 form modal (§3.1 interactions) | Entities, book, period, mode, summarization, cut-off |

**Data bindings.** `GET /journal-runs?entity&book&period&state&mode&sort=-period&count=true` (API-R-38); calculations without a run row `GET /jobs?kind=JOURNAL_RUN_CALCULATE&state=QUEUED,RUNNING,FAILED` (SMAP-05); failed-calculation exception link from `job.problem` `errors[]` to `GET /exceptions?source=JOURNAL&code=ACCOUNT_MAPPING_MISSING` or `JOURNAL_UNBALANCED`; `POST /journal-runs` per entity (API-S-JournalRunCreate; 202). Saved-view code `SF-06`.

**Grid columns.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Run | `run_no` | mono link | SF-06:run |
| Entity | `entity.code` | mono | none |
| Book | `book` | "ASC 606", "IFRS 15" | none |
| Period | `period.name` | DS-FMT-19 | SF-05 of that entity, book and period |
| Mode | `mode` | outline chip "Gross" (`GROSS`) or "Delta" (`DELTA`) | none |
| Grain | `grain` | "Account and dimensions" (`ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS`); "Contract, account and dimensions" (`CONTRACT_ACCOUNT_DIMENSIONS`); "Legacy contract and obligation" (`LEGACY_CONTRACT_POB`) | none |
| State | `state`, job and approval status | chip (§0.4 E-34) with caption | none |
| Lines | `totals.line_count` | integer | SF-06:run-lines |
| Debit (<functional>) | `totals.debit_functional` | money | none |
| Credit (<functional>) | `totals.credit_functional` | money | none |
| Balanced | `totals.balanced` | "Yes"; "No" with chip Difference | none |
| Acknowledged | batches `acknowledged` / all batches | "<n>/<m>" | SF-06:run-batches |
| Approved | `approved_at` | DS-FMT-17 | none |
| Exported | `exported_at` | DS-FMT-17 | none |
| Created by | `created_by` | user cell | none |

All entities: a `Currency` column precedes the money columns and totals rows are per currency (DS-FMT-12). FilterBar fields: Entity, Book, Period, State, Mode.

**States.**

| State | Copy |
|---|---|
| SCR-ST-03 | Title "No journal runs for <period label>"; description "Run journals after schedules are computed to produce balanced entries for the GL."; primary "Run journals" (DS-CMP-23). Legacy-preset tenant: secondary link "Download legacy templates" (SF-10:templates `?f.family=is:LEGACY_V1`; SCR-LTH-O3) |
| SCR-ST-04 | "No journal runs match these filters" |
| Calculating | Pinned row with chip Running, caption "Calculating", and DS-CMP-24 "Calculating journals for <entity code> <period label>" |

**Interactions, keyboard and copy.**

*Run journals* (DS-CMP-11 form modal `--modal-w-md`; the palette command "Run journals for <period label>…" opens the same form).

```text
+----------------------------------------------------------------------------+
| Run journals                                                           [X] |
| Entities        [Mock Entity 1 x] [Mock Entity 2 x] {Add entity v}         |
| Book            {ASC 606 v}                                                |
| Period          {Jan 2023 (Period open) v}                                 |
| Mode            (Gross | Delta)                                            |
| Summarization   {Legacy contract and obligation v}                         |
| > Advanced: Cut-off known at  ____________                                 |
+----------------------------------------------------------------------------+
|                                           [Cancel]  [*Calculate journals]  |
+----------------------------------------------------------------------------+
```

| Label | Control | Binding (API-S-JournalRunCreate) | Default | Validation copy |
|---|---|---|---|---|
| "Entities" | multi-select combobox of the entities `journal.run` is held for (rev 1.79) | one `POST /journal-runs` per `entity_code` | context entity, when `journal.run` is held for it; otherwise none (rev 1.79) | "Choose at least one entity." |
| "Book" | select (ASC 606, IFRS 15; Legacy is not offered) | `book` | primary book | none |
| "Period" | period select listing `open`, `closing` and `reopened` periods | `period_key` | context period | "Choose an open, soft-closed or reopened period." |
| "Mode" | segmented control "Gross" / "Delta" | `mode` | registry POL-005 `je.posting_mode` | "Enable the Legacy book for <entity code> before running delta journals." (POL-007) |
| "Summarization" | select | `grain` | registry POL-006 `je.summarization` | none |
| "Cut-off known at (optional)" | timestamp input behind the "Advanced" disclosure | `cutoff_known_at` | now | "Enter a time that is not in the future." |

**Whose entities (rev 1.79; item W-12, slice c; SCREENS §0.6 SCR-PERM-02 (a)).** A journal run is a record of one legal entity, and one press sends one start per chosen entity. "Run journals" is offered when `journal.run` is held for any entity; "Entities" offers only the entities it is held for, and the context entity is preselected only when it is one of them. The period list is read with `config.read` for the first chosen entity. With no entity chosen, or when `config.read` is not held for the first chosen entity, "Period" lists no period. "Calculate journals" stays enabled in both cases; pressed, it shows "Choose at least one entity." when none is chosen and "Choose an open, soft-closed or reopened period." while no listed period is chosen, and it sends nothing.

"Calculate journals" closes the modal; one progress row appears per entity; toast per entity on success "Journals calculated for <entity code> <period label>." with the action "Open run". Problems: `period-closed` ERR-15; `unmapped-account-role` ERR-46; a failed job becomes the calculation banner with the IMP-36 or IMP-37 message.

**Sample world.** WLD-T-01: Aug and Sep 2026 runs for AVM-US. WLD-T-20 (J-01.14, asserted): two runs for Jan 2023, chip Calculated then Pending approval "Submitted"; `Mock Entity 1` batch Dr 295.69 = Cr 295.69; `Mock Entity 2` batch Dr 58.85 = Cr 58.85 (WLD-X-26).

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Journals" | `SF-06-page` |
| Runs grid | grid named "Journal runs" | `SF-06-grid-runs` |
| Run row | row header "<run no>"; tests filter by entity code and period label | `SF-06-row-<entity code normalised>-<period_key normalised>` (for example `SF-06-row-avm-us-fy2026-p09`) |
| Calculation banner | alert "Journal calculation for …" | `SF-06-banner-calculation-failed` |
| Run form | dialog named "Run journals" | none |

**Light and dark.** Negative banner on `--bg-canvas`; mode outline chips.

**Accessibility.** Grid named by the tab label; the modal's segmented control is named "Mode".

### 3.2 SF-06:run Journal run: summary

| Field | Value |
|---|---|
| Screen id | SF-06:run |
| Route | `/journals/runs/:runId` (RT-29) |
| Roles and permissions | Read `contract.read`. Submit and cancel: `journal.run`. Export, retry, "Export again", record ERP reference: `journal.export`. Download batch files: `journal.export` or `report.export`. Rev 1.68 (SCREENS.md SCR-PERM-02; supervisor ruling R-28): "History" and the name and reason of the Cancelled banner are read from the audit events and need `audit.read` for all entities. Rev 1.71: each is asked for the run's entity (SCREENS SCR-PERM-02 (a)); a command held for another entity only is not rendered |
| Purpose | Review a calculated run in summary, submit it, export it to the GL and follow acknowledgements |
| REQ | REQ-JE-001, 003, 004, 010 to 017; REQ-PLT-022 |
| Journeys | J-01.14 to J-01.16, J-13.8, J-13.9, J-13-AC-3, J-13-AC-4, J-14.6, J-18.5 |

**Wireframe, 1440 px (J-13.8, approved).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Journals > JR-000214                                                                                                 |
| Journal run JR-000214   (Approved)                                   [Download batch files]  [*Export to NetSuite] ...|
| Entity AVM-US  Book ASC 606  Period Sep 2026  Mode Gross  Summarization Account and dimensions                        |
| Journal entries JE-AVM-US-000101 – JE-AVM-US-000164 (64)   Approval APR-000512   Close run CLS-000031                |
| Totals (USD)  Debits …  │  Credits …  │  Difference 0.00 (Pass) Balanced  │  Lines 164  │  Batches acknowledged 0 of 2 |
+----------------------------------------------------------------------------------------------------------------------+
| Summary   Lines   Batches                                                                                            |
+----------+---------------------------------------+------------------------+----------+----------------+----------------+
| Account  | Name                                  | Account role           | Currency |    Debit (USD) |   Credit (USD) |
| 2100     | Contract liability                    | Contract liability     | USD      |              … |              … |
| 4010     | Revenue - services and subscriptions  | Revenue                | USD      |              … |              … |
| ...                                                                                                                  |
| Total                                                                                |              … |              … |
+============================================================================================+================+================+
```

**Wireframe, 1280 px.** Meta row wraps to three lines; the Name column truncates with a tooltip.

```text
+--------------------------------------------------------------------------------------------------------+
| Journal run JR-000214  (Approved)                      [Download batch files] [*Export to NetSuite] ... |
| Entity AVM-US · Book ASC 606 · Period Sep 2026 · Mode Gross                                             |
| Debits … │ Credits … │ Difference 0.00 (Pass) Balanced │ Lines 164 │ Batches acknowledged 0 of 2        |
| Summary  Lines  Batches                                                                                 |
| 2100  Contract liability  Contract liability  USD            …            …                             |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.**

| Region | Components | Content |
|---|---|---|
| Header | DS-CMP-06 record header, journal batch variant; DS-CMP-19; DS-CMP-20; DS-CMP-28 | `h1` "Journal run <run no>"; meta "Entity", "Book", "Period", "Mode", "Summarization", "Cut-off known at", "Journal entries" `<first je no> – <last je no> (<count>)`, "Approval" (link to SF-12:request), "Close run" (link to SF-05:close-run) |
| KPI strip | DS-CMP-06 KPI strip | Heading "Totals (<functional currency>)"; "Debits" `totals.debit_functional`; "Credits" `totals.credit_functional`; "Difference" = `difference` of the summary `balance_checks[]` row with `basis = FUNCTIONAL`, with the chip "Balanced" when `totals.balanced` is true, else "Difference"; "Lines" `totals.line_count`; "Batches acknowledged" `<n> of <m>` from `batches[]` (04 API-S-JournalRun) |
| Banners | DS-CMP-29 | Partially acknowledged: info "Partially acknowledged: <n> of <m> batches." (SMAP-08); failed: negative "<adapter label> rejected <n> chunks: <last error>. Retry after correcting the cause; retries do not duplicate postings." (NTF-10) — with the link "Retry export" until rev 1.77, which takes it away (*Export* below); rev 1.85: on the Summary and Lines tabs the banner has the link "Open batches", to the Batches tab in the page's context, where a failed batch is retried, and on Batches, where the rows are in view, none — and, since rev 1.71 (item JRN-FAILED-EXITS-UI-1), a second line that names the exits offered to this reader on this run and none that is not ("Cancel journal run" below; "Hand over", §3.4): both — "If the ledger can never accept a batch, cancel the journal run, or hand the batch over for manual posting on the Batches tab."; the cancel alone — "If a batch can never be exported as it was calculated, cancel the journal run."; the hand-over alone — "If the ledger can never accept a batch, hand it over for manual posting on the Batches tab."; neither — no line. An exit its job refused: negative "Journal run <run no> was not cancelled" or "Batch <batch> · <chunk> was not handed over" with the job's sentence (States; rev 1.71); a retry that did not send its batch: warning or negative "Batch <batch> · <chunk> was not sent again" (States "Sending again"; rev 1.77); a refused download: negative "Batch <batch> · <chunk> was not downloaded" with the API's sentence ("Download batch files" below; rev 1.77); a job of the run's export that failed or was cancelled: negative "Journal run <run no> was not exported", or over an Exported run "The export of journal run <run no> was not repeated", with the job's sentence (States "Exporting"; rev 1.85); sandbox: SB-R-08 reason line |
| Route tabs | DS-CMP-07 | Summary · Lines · Batches |
| Summary grid | DS-CMP-10 DataGrid | Totals by GL account and transaction currency from `GET /journal-runs/{id}/summary` `lines[]` (04 API-S-JournalRunSummary; OQ-B-07 resolved by D-76) |
| Balance checks | DS-CMP-10 static table, caption "Balance checks" | One row per `balance_checks[]` item: one per entity and transaction currency (`basis = TRANSACTION`) and one per entity and functional currency (`basis = FUNCTIONAL`) (04 B3-D20) |
| History drawer | DS-CMP-09 informational drawer (`drawer=history`) opened from the overflow item "History" | DS-CMP-12 audit timeline of the run. Rev 1.68: the item and the drawer render for a holder of `audit.read` for all entities. Without it the item is not rendered and `drawer=history` opens nothing; a read of the audit events refused with 403 closes the drawer and removes the item. An overflow menu without an item is not rendered. Rev 1.71 (the supervisor's answer of 2026-10-01): an entry a job wrote for a person reads "System on behalf of <name>" (`actor`, `on_behalf_of`); an event whose outcome is `DENIED` reads "was refused: <action>", one whose outcome is `FAILED` "failed: <action>"; the message an event recorded (`detail.message` — for the `DENIED` event of a job, the sentence of its refusal) is quoted above the comment, which is the reason the person gave. Rev 1.85 (the lane's observation O4; the supervisor's ruling of 2026-10-01): the drawer printed the audit action literal where DS-CMP-12 leads an event with its actor and a verb phrase — "Maya Chen journal_run.submit". The seven actions the journals domain records for a run read: `journal_run.request_calculation` "started the journal run"; `journal_run.calculate` "calculated the journals"; `journal_run.submit` "submitted the run for approval"; `journal_run.approve` "approved the run"; `journal_run.request_export` "started the export"; `journal_run.request_cancel` "asked for the run to be cancelled"; `journal_run.cancel` "cancelled the run". An event that did not succeed keeps its form, which is the contract trail's, before the same phrase: "was refused: cancelled the run", "failed: calculated the journals". A literal the catalogue does not know reads as itself. History lists the run's own events: the decisions on its approval request are the request's events and are read on the request (SF-12:request), so the run's History names the submission and not the decision that answered it |

**Data bindings.** `GET /journal-runs/{id}` (API-S-JournalRun); summary `GET /journal-runs/{id}/summary` (04 API-R-38, API-S-JournalRunSummary, computed server-side); `GET /audit-events?object_type=journal_run&object_id=<id>`; commands `POST /journal-runs/{id}/submit` `{comment}`, `/cancel` `{reason}` (200; rev 1.71: 202 job `JOURNAL_EXPORT` in mode `CANCEL` for a run with a failed batch, 04 §16.7 rev 1.159), `/export` `{adapter}` (202 job `JOURNAL_EXPORT`); batch downloads `GET /journal-batches/{id}/download`. Rev 1.71: the job a cancel or a hand-over was accepted as, `GET /jobs/{id}` (`mode`, `state`, `result.outcome`, `result.refusal`, `problem`); the run's active job, `GET /jobs` with `kind` `JOURNAL_EXPORT`, `state` `QUEUED` and `RUNNING`, `subject_type` `journal_run` and `subject_id` the run, read for an approved run (SMAP-07) and, since this revision, for a run with a failed batch — the API lists a job to the member who started it and to a holder of `audit.read` (04 API-C-12). Rev 1.77 (item JRN-RETRY-FOLLOW-1; 04 §16.7, rows `retry` and `export`): the job of a retry and of an export carries no `mode` and is followed by its id as an exit's is — `state`, `problem` and `result.waiting`, the batches whose export message is due again when the job ends, each `{journal_batch_id, external_id, next_attempt_at}` (04 rev 1.221, lane F-CLO-A's item JRN-RETRY-CLAIMED-1; a job of an API before that revision states none). Such a job ends `SUCCEEDED` whether or not it sent a batch, so what it did is read from the run after it: `GET /journal-runs/{id}` again, and the batch's `state` in it.

**Grid columns: summary.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Account | `lines[].account_code` | mono | SF-06:run-lines with `f.account_code=is:<code>` |
| Name | `lines[].account_name` | text | none |
| Currency | `lines[].currency` | mono | none |
| Debit (<txn>) | `lines[].debit` | money | none |
| Credit (<txn>) | `lines[].credit` | money | none |

Rows keep the API order (`account_code`, then `currency`). The account role, clearing purpose, functional-currency and line-count columns are deferred to later, because API-S-JournalRunSummary returns none of them; SF-06:run-lines shows role and clearing purpose per line. The grid has no client-computed totals row (DS-FMT-02): the functional totals are the KPI strip values, and each currency's balance is its balance check row.

**Grid columns: balance checks.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Entity | `balance_checks[].entity_code` | mono | none |
| Basis | `basis`: `TRANSACTION` "Transaction currency"; `FUNCTIONAL` "Functional currency" | text | none |
| Currency | `currency` | mono | none |
| Debit | `debit` | money | none |
| Credit | `credit` | money | none |
| Difference | `difference`, with the chip "Balanced" when it is 0, else "Difference" | money and chip | none |

**States.**

| State | Copy |
|---|---|
| SCR-ST-07 | "Journal run not found" |
| Exporting | DS-CMP-24 in the header "Exporting journal run <run no> to <adapter label>" with chunk counts; actions hidden. Rev 1.77: the frame follows the job by its id — the one its own "Export" was accepted as, or the run's active job without a mode that `GET /jobs` lists — and reads the run, its batches and the active jobs again when it ends; until this revision a reader who had not sent the command kept an Approved page with "Export journals" over a run that was exported. The line shows for every such job the frame can name no batch for: on an approved run, and on a run with a failed batch, where the job is the run's export sent again or a retry another frame sent and where nothing showed before. The toast of "Export" below shows to every frame that followed the job. Rev 1.85 (the lane's observation O-b; the supervisor's rulings of 2026-10-01): a job of the run's export that ends `FAILED` or `CANCELLED` left the page as it was and said nothing. It is told in every frame that followed it, by a negative banner with the job's sentence (`problem.detail`) and its reference: over a run that is not exported "Journal run <run no> was not exported"; over a run that was exported when the frame began to follow the job — "Export again", or a job found under way beside a failed batch — "The export of journal run <run no> was not repeated", the run's status and its batches staying as they are. The run decides before the job, as for a retry: a job that failed over a run it exported all the same is told by the export's toast. The banner leaves when the frame follows another job, or with the page |
| Cancelling (rev 1.71) | DS-CMP-24 in the header "Cancelling journal run <run no>" from the accepted command until its job ends; actions hidden. `result.outcome` `CANCELLED`: the run is read again and the toast "Journal run <run no> was cancelled." shows. `NOT_CANCELLED`, or a job that ended `FAILED`: the run is read again — a batch the ledger holds is acknowledged by then — and the negative banner "Journal run <run no> was not cancelled" stays with the job's sentence: `result.refusal.detail` (PRD ERR-73 and the sentences of 04 §16.7), or `problem.detail` of the failed job (an unreachable ledger) with the line "Reference <job id prefix>." |
| Handing over (rev 1.71) | DS-CMP-24 in the header "Handing over batch <batch> · <chunk>" from the accepted command until its job ends; actions hidden. `HANDED_OVER`: the run and its batches are read again and the toast "Batch <batch> · <chunk> was handed over." shows (rev 1.77: the outcome alone. The toast of rev 1.71 added "Download its file, post it in the ledger and record the ERP reference." — three lines in a toast that DESIGN_SYSTEM DS-CMP-22 gives two, so that it was cut after "record the". The confirmation of §3.4 states the instruction before the command). `NOT_HANDED_OVER`, or a job that ended `FAILED`: the negative banner "Batch <batch> · <chunk> was not handed over" with the job's sentence, as for the cancel |
| Sending again (rev 1.77) | The row action "Retry export" of §3.4: DS-CMP-24 in the header "Sending batch <batch> · <chunk> again" from the accepted command until its job ends; actions hidden. The job of a retry ends `SUCCEEDED` whether or not it sent the batch, so the ending is said after the run is read again, of the batch as it then is. No longer `failed`: the toast "Batch <batch> · <chunk> was sent again." Named in the job's `result.waiting` — its message keeps its schedule, and the job sent nothing for it or tried and the ledger did not answer: the warning banner "Batch <batch> · <chunk> was not sent again" with the line "It is waiting to be sent again at <DD MMM YYYY HH:mm UTC>." (`next_attempt_at`). Still `failed` and not named — the ledger refused it again: nothing is added, and the failed banner states the batch's new error. A job that ended `FAILED` or `CANCELLED` over a batch still `failed` and not named: the negative banner "Batch <batch> · <chunk> was not sent again" with `problem.detail`, else the problem's title, and the line "Reference <job id prefix>." Stated limits of 1.0: the page does not read the run again at the instant the banner states, and the banner stays until the frame follows another job or is replaced; a frame that did not send the retry names no batch (the row "Exporting") and states no waiting batch; a job of an API that states no `waiting` leaves a waiting batch told as one the ledger refused again; an ending that falls between two frames is read in History only, as an exit's |
| A job this frame did not start (rev 1.71) | Each tab mounts the frame, and another member may have sent the command: the frame follows the run's active job of mode `CANCEL` or `HAND_OVER` to its end in the same way. API-S-Job names no batch, so such a hand-over reads "Handing over a batch of journal run <run no>", "A batch of journal run <run no> was handed over." (rev 1.77, as the row above) and "A batch of journal run <run no> was not handed over". Rev 1.77: the frame follows the run's active job without a mode in the same way (the row "Exporting"). The API lists a job to the member who started it and to a holder of `audit.read`; another reader sees the run as it is when it is read again. Stated limit of 1.0 (the supervisor's answer of 2026-10-01): an ending that falls between two frames — the job ended while the tab was being changed — is read in History only, by a reader who holds `audit.read` for all entities (rev 1.68); another reader sees the run as it is. While an exit is under way a reader without that permission is left no overflow item, and the menu is not rendered |
| Cancelled | Info banner "Journal run <run no> was cancelled by <name> on <DD MMM YYYY HH:mm UTC>: <reason>." Rev 1.68: without `audit.read` for all entities the audit events are not read and the banner says "Journal run <run no> was cancelled on <DD MMM YYYY HH:mm UTC>." from `cancelled_at`, as it does when that read fails or is refused. Rev 1.71 (04 §16.7 rev 1.159): a failed run is cancelled by its job, as System on behalf of the person who asked, and can hold `DENIED` events of the same action from attempts the job refused. The banner reads the `journal_run.cancel` event whose outcome is `SUCCESS`, and its name is `on_behalf_of` where the event has one, else the actor |
| SCR-ST-05 | "Could not load the journal run" |

**Interactions, keyboard and copy.**

*Action bar.*

| State (§0.4) | Primary | Secondary | Overflow |
|---|---|---|---|
| Calculated | "Submit for approval" | none | "Cancel journal run"; "History" |
| Pending approval "Submitted" | none | "View approval request" | "Cancel journal run"; "History" |
| Approved | "Export to <adapter label>"; "Export journals" when the entity has no active GL connection (OQ-B-31); in a sandbox the control renders with `aria-disabled="true"` and the SB-R-08 reason | "Download batch files" | "Cancel journal run"; "History" |
| Running "Exporting" | none | none | "History" |
| Exported | none | "Download batch files" | "Export again"; "History" |
| Failed | none (rev 1.77: "Retry export" until then; *Export* below) | "Download batch files" | "Cancel journal run" (rev 1.71; `aria-disabled` with its reason on a run that is partly in a ledger, below); "History" |
| Posted | none | "Download batch files" | "History" |
| Cancelled | none | none | "History" |
| Any state, while a cancel or a hand-over of the run is under way (rev 1.71; States), or while the frame follows a retry or an export of it (rev 1.77) | none | none | "History" |

*Submit for approval.* DS-CMP-11 form modal: title "Submit journal run <run no> for approval?"; description "A user other than you must approve it before export."; "Comment (optional)"; buttons "Cancel", "Submit for approval". Toast "Submitted journal run <run no> for approval."

*Export.* DS-CMP-11 confirmation: title "Export journal run <run no> to <adapter label>?"; consequence "Each batch is sent once with its external id. Repeating the export does not post again."; select "Target" listing active outbound connections that map the entity (adapter labels "NetSuite", "QuickBooks Online") and "CSV download"; buttons "Cancel", "Export". Toast "Journal run <run no> exported. <n> of <m> batches acknowledged." "Export again" repeats the command; toast "The export was already recorded. No batch was posted again." (BR-JE-02; J-01.16). In a sandbox the Export button is `aria-disabled="true"` with the SB-R-08 reason (J-18.5; the API returns 403 `sandbox-restricted`). Rev 1.77 (item JRN-RETRY-FOLLOW-1). *The target*: a run's batches are calculated for one adapter — the entity's GL connection, or `CSV` — and `export` answers 422 `validation-failed` for any other (04 §16.7 rev 1.145; BUILD_SPEC CLO-15), so "Target" lists that one target and the command sends it; the action reads "Export to <adapter label>" for a run of an ERP adapter and "Export journals" for a `CSV` run. Until this revision the select listed "CSV download" alone and the command sent `CSV` for every run, which the API refuses for a run of an ERP adapter. *The toast* shows after the run is read again, and only of a run the job exported — one that is then `exported` or `acknowledged` and was neither when the frame began to follow the job; "Export again" keeps its own toast. It followed every job that had not failed, a job that sent nothing included. *On a Failed run* (the supervisor's ruling of 2026-10-01 on the lane's finding) the header's "Retry export" and the failed banner's link are not offered. Both sent this command, which writes no message for a batch that has one — a failed batch is sent again by `POST /journal-batches/{id}/retry` (04 T-SL-07 "Failed export and retry") — so its job sent nothing for a failed batch, ended `SUCCEEDED`, and the page answered "Journal run <run no> exported." over a run that was still Failed. A page offers no command that sends nothing: the rows' "Retry export" of §3.4 are the way, and the failed banner keeps its sentence and the line of the exits. Rev 1.85: from the Summary and Lines tabs the failed banner leads to them ("Open batches"). Stated limit of 1.0, until item JRN-RUN-RETRY-1 (lane F-CLO-A) is on main: that item makes `export` on a run with failed batches write each one's retry message under the rule of `retry`, and the header's action then returns as one command, followed like the row's. On an Exported run with a failed batch (SMAP-08) the banner offers no retry either, and "Export again" stays: it is the export that posts nothing again, and says so. *No answer*: a command of this page or of §3.4 whose request gets no answer — "Submit for approval", "Export", "Record ERP reference" and "Retry export", as the two exits since rev 1.71 — shows the toast "No answer came back from the server. Try again." and its dialog stays open.

*Cancel journal run* (SB-R-05). Consequence "The run and its batches are cancelled. Their subledger lines can be summarized again in a new run."; Danger "Cancel journal run". A pending approval request is voided (SM-08). Rev 1.71 (item JRN-FAILED-EXITS-UI-1; 04 §16.7 rev 1.159; PRD SM-08, ERR-73, ERR-74): a Failed run offers the command too. When one of its failed batches is of an ERP adapter the consequence reads "The ledger is asked first whether it holds a failed batch. If it holds none, the run and its batches are cancelled, and their subledger lines can be summarized again in a new run. A batch the ledger holds is acknowledged instead, and the run is not cancelled."; a run whose failed batches are all `CSV` keeps the first consequence, there being no ledger to ask. The command answers 202: the dialog closes on the accepted command and the page follows the job (States "Cancelling"). A refusal of the command itself (409) stays in the dialog with its title and its sentence as sent: a later run of the same entity, book and period, a batch being sent or still waiting to be sent, a cancellation already under way. State guard (SCREENS SCR-PERM-03): on a Failed run one of whose batches is `exported` or `acknowledged` the item renders `aria-disabled="true"` with the reason of PRD ERR-74, "Journal run <run no> has a batch that a ledger holds or that was handed out (<external id>). Retry its failed batch, or hand it over for manual posting.", naming the first such batch in batch and chunk order as the API does. An Exported run with a failed batch does not offer the command: one of its batches is `exported` (SMAP-08), so it could only be refused. The command has no sandbox state: a sandbox holds no failed run — it writes no export message and has no active ERP connection (the supervisor's answer of 2026-10-01).

*Download batch files.* A menu listing each batch "Batch <n> · chunk <c> · <currency> (CSV and manifest)"; each item downloads `GET /journal-batches/{id}/download` (ZIP). Rev 1.71 (PRD ERR-79): the item fetches the file and then saves it under the name the API gives it (`Content-Disposition`). A refused download saves nothing and shows the problem's sentence in a negative toast — its `detail`, for ERR-79 "Batch <external id> differs from what was calculated and approved: <differences>. It cannot be downloaded.", else its title and "Reference <request id>."; a request that got no answer shows "No answer came back from the server. Try again.". Rev 1.77: the refusal is a negative banner of the frame, "Batch <batch> · <chunk> was not downloaded", with that sentence whole — a toast holds two lines (DESIGN_SYSTEM DS-CMP-22) and cut ERR-79's sentence before its differences. The banner stays until another download is asked or the frame is replaced; a request without an answer stays the toast.

**Sample world.** J-13.8: `maya` submits, `priya` approves (Approved). J-13.9 (asserted): export to the NetSuite mock; every batch acknowledged with NetSuite document ids; chip Posted; J-13-AC-4 repeat creates no posting. J-01.16: QuickBooks Online export repeated; same records. J-14.6: post-reopen run for K-03 lines.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Journal run <run no>" | `SF-06-page` |
| KPI strip | region named "Totals (<currency>)" | `SF-06-kpi-strip` |
| Difference KPI | term "Difference" | `SF-06-kpi-difference` |
| Summary grid | grid named "Summary by account" | `SF-06-grid-summary` |
| Balance checks | table named "Balance checks" | `SF-06-grid-balance-checks` |
| Export target | combobox named "Target" | `SF-06-export-target` |
| Failed banner | alert "<adapter label> rejected …" | `SF-06-banner-export-failed` |
| Exit progress (rev 1.71) | progressbar named "Cancelling journal run <run no>" or "Handing over …" | none |
| Refused exit banner (rev 1.71) | alert "Journal run <run no> was not cancelled" or "… was not handed over" | `SF-06-banner-exit-refused` |
| Retry progress (rev 1.77) | progressbar named "Sending batch <batch> · <chunk> again" | none |
| Banner of a retry that did not send its batch (rev 1.77) | status (the batch waits) or alert (the job failed) "Batch <batch> · <chunk> was not sent again" | `SF-06-banner-retry-not-sent` |
| Refused download banner (rev 1.77) | alert "Batch <batch> · <chunk> was not downloaded" | `SF-06-banner-download-refused` |
| Banner of an export job that failed or was cancelled (rev 1.85) | alert "Journal run <run no> was not exported" or "The export of journal run <run no> was not repeated" | `SF-06-banner-export-not-done` |

**Light and dark.** KPI chips; the double totals rule `--rule-total`.

**Accessibility.** The Difference value's accessible name ends with "balanced" or "not balanced"; the export confirmation is an `alertdialog` with initial focus on "Cancel". Rev 1.71: the disabled "Cancel journal run" item keeps its place in the menu and is described by its reason (DS-CMP-28); the refused exit banner is inserted after load and announced as an alert (DS-CMP-29). Rev 1.77: the banner of a retry that did not send its batch is inserted after load and announced — as a status when the batch waits, as an alert when the job failed; the refused download banner is an alert.

### 3.3 SF-06:run-lines Journal run: lines and source drill

| Field | Value |
|---|---|
| Screen id | SF-06:run-lines (SCREENS.md §0.4; §14) |
| Route | `/journals/runs/:runId/lines` with `f.account_code`, `f.account_role`, `f.contract`, `f.batch`, `f.post_close` |
| Roles and permissions | Read `contract.read` |
| Purpose | Show journal lines with JE numbers, dimensions and flags, and drill each line to its contributing subledger lines, events, schedule lines and source rows |
| REQ | REQ-JE-003, 010, 018; REQ-RPT-017 |
| Journeys | J-14-AC-4, J-16.5, J-16-AC-3 |

**Wireframe, 1440 px (J-16.5 with the source-lines drawer open).**

```text
+-----------------------------------------------------------------------------+----------------------------------------+
| Journal run JR-000209  (Posted)                                             | Source lines for JE-AVM-US-000088 · 3  |
| Summary   Lines   Batches                                                   | Account 4010 · Credit USD …            |
| [Account is 4010 x] [Filter]                                                | [Contract is SF-ORD-10003 x]           |
| JE             Line Account Role     Debit (USD) Credit (USD) Contract      | Contract     Debit or credit  Amount … |
| JE-AVM-US-0088   3  4010    Revenue         0.00          … SF-ORD-…  12 > | SF-ORD-10003 Credit                  … |
| ...                                                                         |   [Explain] [Open event] [Source row]  |
+-----------------------------------------------------------------------------+----------------------------------------+
```

**Wireframe, 1280 px.** The drawer overlays the grid (DS-SP-04) instead of reflowing it.

```text
+--------------------------------------------------------------------------------------------------------+
| Summary  Lines  Batches   [Account is 4010 x]                        +- Source lines for JE-… · 3 ---+  |
| JE-AVM-US-0088  3  4010  Revenue  0.00  …  SF-ORD-10003  12 >        | SF-ORD-10003  Credit        …  |  |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-13 FilterBar; DS-CMP-10 DataGrid; source-lines drawer DS-CMP-09 docked panel `--drawer-w-wide` (informational; `drawer=source-lines`); DS-CMP-15 Explain triggers. FilterBar fields (rev 1.39; item W-19, crawl finding F1): "Account" (text; `f.account_code`), "Account role" (the account roles by label; `f.account_role`), "Contract" (DS-CMP-21 combobox of contracts, read as the exceptions screen reads them, `GET /contracts?sort=contract_no`; an option shows the contract's external id, and the URL and the request carry its id; `f.contract`) and "Batch" (the batches of the run, from `batches[]` of API-S-JournalRun, each labelled "<batch> · <chunk>" as §3.4 labels it; the URL and the request carry the batch id, which is what the §3.4 link of a batch to its lines writes; `f.batch`). A `f.batch` value that is not a batch of the run is dropped under SCR-URL-21.

**Data bindings.** `GET /journal-runs/{id}/lines` (API-S-JournalLine; filters `account_code`, `account_role`, `contract`, `batch_id`); drill `GET /journal-lines/{id}/drill` (API-S-SubledgerLine list; the route takes no filter: the drawer's "Contract" field filters the loaded source lines in the browser by contract external id, decision D-87 L6-5-Q-9; rev 1.34; rev 1.65, item JRN-DRILL-CONTRACT-NAME-1: a source line names its contract itself, `contract_external_id` (04 §16.7), so the drawer reads no contract — it read one for every distinct contract of the line before its first row, 91 for one line of the seeded tenant); Explain `GET /explain/journal_line/{id}/amount`; each subledger line's `links.explain`, `links.event`, `links.schedule_line`, `links.source_row`. Saved-view code `SF-06:run-lines`.

**Grid columns: lines.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Journal entry | `je_no` | mono | none |
| Type | `je_type` | "Automated", "Manual", "Reversal" (E-30) | none |
| Line | `line_no` | integer | none |
| Account | `account.code` | mono | none |
| Account role | `account_role` | E-01 label | none |
| Dimensions | `dimensions` | "department: SALES · location: NYC" (codes in mono) | none |
| Currency | `txn_currency` | mono | none |
| Debit (txn) | `debit_txn` | money | Explain |
| Credit (txn) | `credit_txn` | money | Explain |
| Debit (functional) | `debit_functional` | money | none |
| Credit (functional) | `credit_functional` | money | none |
| Contract | `contract.external_id` | mono link | SF-03 |
| Obligation | `obligation_key` | mono link | SF-03:obligation |
| Counterparty entity | `counterparty_entity.code` | mono | none |
| Origin period | `origin_period_key` → label | DS-FMT-19 | SF-08:report `out_of_period_register` |
| Post-close | `is_post_close` | "Yes" / "No" | none |
| Memo | `memo` | text | none |
| Source lines | `source_line_count` | integer link | source-lines drawer |

**Grid columns: source-lines drawer.**

| Header | Field | Format |
|---|---|---|
| Contract | `contract_external_id` (rev 1.65) | mono; em dash when null: a line without a contract, or a contract outside the reader's entity scope. Rev 1.81: the grid's leading identifier column — pinned to the start, its cell the row header (DS-CMP-10); a line without one names its row "No contract" for assistive technology, the visible cell staying the dash |
| Debit or credit | `dr_cr` | "Debit" / "Credit" |
| Amount (txn) | `amount_txn` | money |
| Effective | `effective_date` | DS-FMT-16 |
| Entry kind | `entry_kind` | E-29 label in sentence case |
| Posting kind | `posting_kind` | E-31 label ("Engine computation", "Close release", "FX remeasurement", "Netting reclass", "Manual adjustment", "Void reversal") |
| Account role | `account_role` | E-01 label |
| Obligation | `obligation_id` → key | mono link. Not built: API-S-SubledgerLine states `obligation_id` and no key — the gap the contract had before rev 1.65; placed with lane F-CLO-A (the supervisor's message of 2026-10-01) |
| Amount (functional) | `amount_functional` | money |
| FX rate | `fx_rate.rate` | DS-FMT-14 |
| Origin period | `origin_period_key` | DS-FMT-19 |
| Post-reopen | `is_post_reopen` | "Yes" / "No" |
| Reason | `reason_code` | mono |
| Recorded | `recorded_at` | DS-FMT-17 with seconds, `data-volatile` |
| Actions | none | ghost buttons "Explain", "Open event" (SF-03:history), "Open schedule line" (SF-04 `layout=lines` filtered), "Open source row" (the SCREENS.md §6.6 source record drawer or the SF-10:detail import row drawer) |

Rev 1.81 (the drawer's order; register index 158; the supervisor's ruling of 2026-10-01). The order follows the question the drawer answers — which lines make up this amount. The drawer is `--drawer-w-wide`, 720 px at every viewport, and its grid has 686 px: "Contract" (176), "Debit or credit" (144), "Amount (txn)" (160) and "Effective" (128) stand in view without scrolling, 608 px. Until this revision the table began "Effective", "Recorded", "Posting kind", "Entry kind" — 688 px that read alike on every row of one journal line ("31 Aug 2026 · … UTC · Engine computation · Revenue recognition", 91 times for the August 4010 line of the seeded tenant) — with the contract, which is what the drawer's one filter filters by, and the amount, which is what the drawer explains, beyond its width. The side stands before the amount: the amount is signed as the subledger keeps it (04 T-SL-04 — a debit positive, a credit negative, shown in the tenant's negative style, DS-FMT-06), and the word is read before the mark, so that a reversal among the lines of one journal line does not read as a recognition. "Recorded", the bitemporal instant, moves to the end before "Actions". No width, header or copy changes; the drawer's grid keeps no saved view, so no stored order is overridden.

**States.** SCR-ST-03 lines: title "No journal lines"; description "This run summarized no subledger lines." Drawer empty: "No source lines match this filter."

**Interactions, keyboard and copy.** Enter on "Source lines" opens the drawer and moves focus to its heading; Esc closes it and returns focus to the cell (J-16.6). The drawer's FilterBar has one field "Contract". "Open source row" shows, for API-originated events, API client, idempotency key, request id and payload SHA-256 (J-16.5).

**Sample world.** J-16.5 (asserted drill path): Aug 2026 AVM-US run, 4010 revenue line, drill, filter `SF-ORD-10003`, `USAGE_REPORTED` event from `svc-metering`. J-14-AC-4: lines of the post-reopen run show "Post-close Yes".

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Lines grid | grid named "Journal lines" | `SF-06-grid-lines` |
| Line row | row header "<je no> line <n>" | none (generated numbers; tests filter by account and contract) |
| Source-lines drawer | complementary region named "Source lines for …" | `SF-06-drawer-source-lines` |
| Drawer grid | grid named "Source lines" | `SF-06-grid-source-lines` |

**Light and dark.** Drawer `--bg-raised` beside the grid in both themes.

**Accessibility.** The drawer is an `aside` (docked variant); focus returns to the originating cell; the Explain buttons are named "Explain <amount label>". Rev 1.81: the row header of a source line is its contract, and "No contract" where the line has none.

### 3.4 SF-06:run-batches Journal run: batches and acknowledgements

| Field | Value |
|---|---|
| Screen id | SF-06:run-batches (SCREENS.md §0.4; §14) |
| Route | `/journals/runs/:runId/batches` |
| Roles and permissions | Read `contract.read`. "Record ERP reference", "Retry export", "Hand over" (rev 1.71): `journal.export`. "Download": `journal.export` or `report.export`. Rev 1.71: each is asked for the run's entity (SCREENS SCR-PERM-02 (a)) |
| Purpose | Show each batch and chunk with state, external id, adapter, acknowledgements and failures, and record CSV acknowledgements or retry failed chunks; rev 1.71: hand a failed batch of an ERP adapter over for manual posting and record its ERP reference |
| REQ | REQ-JE-011 to 016; CTL-021 |
| Journeys | J-01.16, J-13.9, J-13-AC-4 |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Journal run JR-000214  (Exported) Partially acknowledged: 1 of 2 batches                                             |
| Summary   Lines   Batches                                                                                            |
+-------+----------+------------+-------+-------------+-------------+---------------------------------------+----------+-----+
| Batch | Currency | State      | Lines | Debit (USD) | Credit (USD)| External id                           | GL doc   | ... |
| 1 · 1 | USD      | (Posted)   |    88 |           … |           … | erev:avenmoor:JR-000214:1:1           | 44021    | ... |
| 1 · 2 | USD      | (Exported) |    76 |           … |           … | erev:avenmoor:JR-000214:1:2           | —        | ... |
+-------+----------+------------+-------+-------------+-------------+---------------------------------------+----------+-----+
```

**Wireframe, 1280 px.** Adapter, Exported and Attempts move into the batch drawer.

```text
+--------------------------------------------------------------------------------------------------------+
| Batch  Currency  State      Lines  Debit (USD)  Credit (USD)  External id                    GL doc    |
| 1 · 1  USD       (Posted)      88            …             …  erev:avenmoor:JR-000214:1:1    44021     |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-10 DataGrid; batch drawer DS-CMP-09 informational (`drawer=batch`); DS-CMP-11 form modal "Record ERP reference"; DS-CMP-11 confirmation "Hand over" (rev 1.71); DS-CMP-29 failure banner.

**Data bindings.** `GET /journal-runs/{id}/batches`; `GET /journal-batches/{id}` (attempts, last error, acknowledgements); `GET /journal-batches/{id}/download`; `POST /journal-batches/{id}/acknowledge` `{gl_document_id, gl_posted_date, message}`; `POST /journal-batches/{id}/retry` (202); `POST /journal-batches/{id}/hand-over` (202 job `JOURNAL_EXPORT` in mode `HAND_OVER`; rev 1.71, 04 §16.7 rev 1.159).

**Grid columns.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Batch | `batch_no`, `chunk_no` | "<batch> · <chunk>" | batch drawer |
| Currency | `txn_currency` | mono | none |
| State | `state` | chip (§0.4 E-34) | none |
| Lines | `line_count` | integer | SF-06:run-lines with `f.batch` |
| Debit (<txn>) | `total_debit_txn` | money | none |
| Credit (<txn>) | `total_credit_txn` | money | none |
| External id | `external_id` | mono, never truncated (DS-FMT-23) | none |
| Adapter | `adapter` | "CSV", "NetSuite", "QuickBooks Online" (E-37) | none |
| Exported | `exported_at` | DS-FMT-17 | none |
| Acknowledged | `acknowledged_at` | DS-FMT-17 | none |
| GL document | latest `acknowledgements[].gl_document_id` | mono | none |
| Attempts | `attempt_count` | integer | none |
| Last error | `last_error` | text with tooltip | none |
| Actions | none | "Download"; "Record ERP reference" (`exported`; rev 1.71: of any adapter — a batch handed over waits for its reference as a CSV batch does, and a batch an ERP adapter posts is acknowledged in the same step and is never left `exported`; the State chip does not caption a batch that was handed over in this revision — API-S-JournalBatch says so only once lane F-CLO-A's next item adds the instant of the hand-over, and the caption belongs on that chip); "Retry export" (`failed`); "Hand over" (`failed`, adapter other than `CSV`; rev 1.71) | none |

Batch drawer acknowledgements table: "Kind" (`ack_kind`: `POSTED` "Posted", `REJECTED` "Rejected", `DUPLICATE` "Duplicate", `MANUAL_CONFIRMATION` "Manual confirmation"); "GL document" (mono); "Posted date" (DS-FMT-16); "Message"; "Response SHA-256" (prefix with copy); "Received" (DS-FMT-17); "Recorded by" (user or "System").

**States.** No batches (calculated run with no lines): title "No batches"; description "This run has no journal lines to export." A failed batch: negative banner as SF-06:run, with "Retry export" on the row. Rev 1.71: while a cancel or a hand-over of the run is under way the header shows its progress (§3.2 States) and neither "Retry export" nor "Hand over" is rendered. Rev 1.77: likewise while the frame follows a retry or an export of the run (§3.2 States "Sending again" and "Exporting").

**Interactions, keyboard and copy.** *Record ERP reference* (BR-JE-03): title "Record ERP reference for batch <batch> · <chunk>"; fields "ERP document reference (required)", "Posted date (optional)", "Message (optional)"; buttons "Cancel", "Record reference"; toast "Batch <batch> · <chunk> acknowledged with reference <reference>." *Retry export*: confirmation "Retry batch <batch> · <chunk>?" with consequence "The chunk is sent again with the same external id. The GL will not post it twice."; buttons "Cancel", "Retry export". Rev 1.77 (item JRN-RETRY-FOLLOW-1): on 202 the dialog closes and the frame follows the job to its ending (§3.2 States "Sending again"). Until this revision nothing followed it: the row kept "Failed" and "Retry export" until the page was opened again, whatever the job had done. Rev 1.71: a refusal of "Record ERP reference" or of "Retry export" (409) stays in its dialog with its title and its sentence as sent, as one of "Hand over" does. *Hand over* (rev 1.71; item JRN-FAILED-EXITS-UI-1; 04 §16.7 `hand-over`; PRD SM-08, BR-JE-03, ERR-73): DS-CMP-11 confirmation, title "Hand over batch <batch> · <chunk> for manual posting?"; consequence "The ledger is asked first whether it holds the batch. If it does not, the batch leaves eRev as its file and is not sent again: download the file, post it in the ledger by hand, then record the ERP reference."; buttons "Cancel", "Hand over". In a sandbox the row action renders `aria-disabled="true"` with the SB-R-08 reason (the API answers 403 `sandbox-restricted`). A refusal of the command (409) stays in the dialog with its title and its sentence as sent; on 202 the dialog closes and the frame follows the job (§3.2 States "Handing over"). *Download* (rev 1.71): the row's link is fetched and saved as "Download batch files" of §3.2 is; a refusal is said in a negative toast and nothing is saved. Rev 1.77: in the frame's banner "Batch <batch> · <chunk> was not downloaded", as §3.2.

**Sample world.** J-13.9: NetSuite mock document ids per chunk; `external_id` pattern `erev:avenmoor:<run no>:<batch>:<chunk>` (T-SL-07). J-01.16: QuickBooks Online ids; repeat export leaves the mock's posting count unchanged.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Batches grid | grid named "Batches" | `SF-06-grid-batches` |
| Batch drawer | complementary region named "Batch <batch> · <chunk>" | `SF-06-drawer-batch` |
| Record reference form | dialog named "Record ERP reference …" | none |
| Hand-over confirmation (rev 1.71) | alertdialog named "Hand over batch <batch> · <chunk> for manual posting?" | none |

**Light and dark.** Mono external ids on `--bg-surface`.

**Accessibility.** External ids are isolated LTR (DS-I18N-07); action buttons named "Record ERP reference for batch 1 · 2" and, since rev 1.71, "Hand over batch 1 · 2 for manual posting".

### 3.5 SF-06:entries Journal entries by date range

| Field | Value |
|---|---|
| Screen id | SF-06:entries |
| Route | `/journals/entries` (RT-30) with `entity`, `format` (`gross`, `adjustment`; SCR-LTH-07), `from`, `to` (ISO dates; SCREENS.md SCR-URL-25), `snapshot`, `run` |
| Roles and permissions | Read `contract.read` (RT-30); running the view needs `report.run`; export `report.export` |
| Purpose | Show the gross and adjustment journal views for an inclusive effective-date range: the replacement of the legacy "Revenue Journal Entries" report |
| REQ | REQ-JE-007, 008, 009; REQ-BK-004; LTM-07 |
| Journeys | J-01.12, J-01-AC-6, J-21.5, J-21-AC-1 |

**Wireframe, 1440 px (J-01.12).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Journals                                                                                                             |
| Journal runs   Entries by date range                                                                                 |
+----------------------------------------------------------------------------------------------------------------------+
| {Mock Entity 1, Mock Entity 2 v}  From 01 Jan 2023  To 31 Jan 2023  (Gross | Adjustment)          [*Run report]      |
| Report Legacy journal summary v1 · Run RPT-000019 · Book ASC 606 · Source Current · Run by Maya Chen · Rows 5        |
|                                                                                       [Run details]  Export v        |
+------------------------+------------------+-------------------+-------------------+----------------------------------+
| Account                |      Debit (USD) |      Credit (USD) |         Net (USD) |                                  |
| 15002                  |            58.85 |              0.00 |             58.85 |                                  |
| 21001                  |           295.69 |              0.00 |            295.69 |                                  |
| 5001                   |             0.00 |            187.69 |           (187.69)|                                  |
| 5002                   |             0.00 |            118.53 |           (118.53)|                                  |
| 5003                   |             0.00 |             48.32 |            (48.32)|                                  |
| Total                  |           354.54 |            354.54 |              0.00 |                                  |
+========================+==================+===================+===================+==================================+
| Line items (legacy keys)                                                                                             |
| Key                                           Account                               Amount (USD)                     |
| Contract 1 POB #1 Hardware 1                  5001                                     (128.84)                      |
| ...                                                                                                                  |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** The account table and line items stack; the empty fifth column is removed.

```text
+--------------------------------------------------------------------------------------------------------+
| {Mock Entity 1, Mock Entity 2 v} From 01 Jan 2023 To 31 Jan 2023 (Gross|Adjustment)  [*Run report]      |
| Account   Debit (USD)   Credit (USD)   Net (USD)                                                        |
| 21001          295.69           0.00      295.69                                                        |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Report viewer (§0.5) of `legacy_je_summary` (RPT-13): parameters toolbar with DS-CMP-21 date inputs and DS-CMP-31 segmented control named "Journal view"; run stamp; DS-CMP-10 grids "By account" and "Line items".

**Data bindings.** `POST /report-runs` `{report_code: "legacy_je_summary", parameters: {entity_codes, book: "ASC606", from_date, to_date, mode: "GROSS" | "DELTA"}, output_format: "JSON"}`; `GET /report-runs/{id}/data` (sections `by_account`, `line_items`; RPT-13).

**Grid columns.** RPT-13 (§5.6).

**States.** Start after end: "Start date must be on or before end date." (REQ-RPT-012). SCR-ST-03 via RV-13: title "No journal activity from <from> to <to>"; description "Journal lines appear for contracts with postings in this date range." Delta view without a Legacy book: info banner "The adjustment view needs the Legacy book. Enable it for <entity code> to see pre-standard revenue reversals." (POL-007).

**Interactions, keyboard and copy.** Changing `format` re-runs with the new mode; "Run report" per RV-08; exports per RV-06 (XLSX, CSV).

**Sample world.** WLD-X-26 (asserted) Jan 2023 gross: Dr 21001 295.69, Dr 15002 58.85 / Cr 5001 187.69, Cr 5002 118.53, Cr 5003 48.32; total 354.54 / 354.54; Mock Entity 1 batch 295.69 / 295.69; Mock Entity 2 batch 58.85 / 58.85. J-21.5 (asserted) May 2023: Dr 5001 5.31, Dr 15002 5.18 / Cr 5003 10.49; Oct 2023: Dr 21001 2,990.37, Dr 21002 2,053.48 / Cr 5001 2,060.35, Cr 5002 1,108.63, Cr 5003 1,784.69, Cr 15002 90.18; total 5,043.85.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Format switch | radiogroup named "Journal view" | `SF-06-entries-format` |
| By-account grid | grid named "Journal lines by account" | `SF-06-grid-entries-by-account` |
| Account row | row header "<account code>" | `SF-06-row-<account code normalised>` (for example `SF-06-row-21001`) |
| Line items grid | grid named "Line items" | `SF-06-grid-entries-line-items` |
| Run stamp | region named "Run details" meta row | `SF-06-run-stamp` |

**Light and dark.** Totals rules in both themes.

**Accessibility.** The grid `caption` states range and view, for example "Journal lines by account, 01 Jan 2023 to 31 Jan 2023, gross view".

## 4. Schedules: revenue waterfall (SF-04)

### 4.1 SF-04 Schedules

| Field | Value |
|---|---|
| Screen id | SF-04 |
| Route | `/schedules` (RT-25) with `entity`, `period`, `book`, `currency_view`, `snapshot`, `run`, `f.period` (`between:<period_key>,<period_key>`), `f.state` (`is:recognized`, `is:scheduled`, `is:awaiting_trigger`), `f.contract`, `f.customer`, `f.product`, `f.revenue_category`, and the screen parameters `rows` (`contract`, `obligation`, `product`, `revenue_category`), `granularity` (`month`, `quarter`, `year`), `measure` (`total`, `by_state`), `layout` (`waterfall`, `lines`) (SCREENS.md SCR-URL-18, SCR-URL-24); rev 1.92: and the screen parameter `entities` (`all`; SCREENS.md SCR-URL-01 rev 1.61) — an address that names no entity takes the context pill's, and one that says `entities=all` is every entity's in scope (§0.5 "The context of a view") |
| Roles and permissions | Read `contract.read` (RT-25); the waterfall layout runs a report and needs `report.run` (every role holding `contract.read` except Service Account holds it); export `report.export` |
| Purpose | Show recognized, scheduled and awaiting-trigger revenue by period for the context, with every cell drilling to its schedule lines and Explain, and anomaly flags on the rows they concern |
| REQ | REQ-RPT-004, 017, 018; REQ-REC-021; REQ-UX-009; REQ-AI-007; NFR-22 |
| Journeys | J-15.2, J-15.7, J-15-AC-1, J-16.1, J-16.2, J-16.4, J-16.6, J-24.4 |

**Wireframe, 1440 px (AVM-US, as locked Sep 2026, rows by obligation).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Schedules                                                                         [Run details]  Export v  ...       |
| {Rows: Obligation v} (Month | Quarter | Year) From {Jan 2026 v} To {Dec 2026 v} (Total | By state) (Waterfall | Lines)|
| Report Revenue waterfall v1 · Run RPT-000388 · Entity AVM-US · Book ASC 606 · Source As locked on 01 Oct 2026 …      |
| [i] Showing Sep 2026 as locked on 01 Oct 2026 09:14 UTC.  Show current figures                                        |
| Tie-outs (1 pass, 0 fail)  (Pass) Waterfall revenue equals revenue journal total                                     |
+----------------------------------------------------------------------------------------------------------------------+
| Revenue by period · USD · ASC 606                                                          (Chart | Table)           |
| ■ Recognized  ■ Scheduled  // Awaiting trigger                                     Open                              |
|  ##  ##  ##  ##  ##  ##  ##  ##  ##  ..  ..  ..        //                                                            |
| Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec   Awaiting trigger                                                   |
+----------------------+---------+----------------+------------+--------------+--------------+--------------+----------+
| Contract             | Oblig.  | Customer       | Sep 2026   | Oct 2026     | Awaiting     | Total (USD)  | Flags    |
|                      |         |                | (USD)      | (USD)        | trigger (USD)|              |          |
| SF-ORD-10001         | O1      | Pellworth…     | fn 9,764.38|    10,090.41 |         0.00 |            … |          |
| SF-ORD-10388         | O1      | Pellworth…     | fn 4,891.30|     5,054.35 |         0.00 |            … |          |
| PRJ-CB-2026-01       | O1      | Castellan…     |fn 229,852.94|          … |            … |            … |          |
| ...                                                                                                                  |
| Total                                                                    |            … |            … |            … |          |
+==========================================================================+==============+==============+==============+==========+
```

**Wireframe, 1280 px.** The chart panel keeps full width; the grid pins "Contract" and "Obligation" (DS-CMP-10 pinned columns) and scrolls periods horizontally inside its viewport (DS-SP-07).

```text
+--------------------------------------------------------------------------------------------------------+
| Schedules                                                               [Run details] Export v         |
| {Rows: Obligation v} (Month|Quarter|Year) From {Jan 2026 v} To {Dec 2026 v} (Total|By state)            |
| Revenue by period · USD · ASC 606  (Chart | Table)                                                     |
|  ## ## ## ## ## ## ## ## ## .. .. ..   //                                                              |
| Contract        Oblig. | Sep 2026 (USD)  Oct 2026 (USD)  ...  Awaiting trigger (USD)  Total (USD)       |
| SF-ORD-10001    O1     |    9,764.38        10,090.41                   0.00                …        |
+--------------------------------------------------------------------------------------------------------+
```

The October figures of the wireframe are illustrative (SB-R-04).

**Regions and components.**

| Region | Components | Content |
|---|---|---|
| Header and parameters | DS-CMP-06 plain header; DS-CMP-21 selects; DS-CMP-31 segmented controls ("Granularity", "Measure", "Layout") | `h1` "Schedules"; RV-08 toolbar |
| Run stamp, banners, tie-outs | RV-02, RV-04, RV-05 | Tie-out `TO_WATERFALL_EQ_JE_REVENUE` (04 table 10-T) |
| Chart panel | DS-CMP-14 with DS-CH-01 | Subtitle "Revenue by period · <currency> · <book label>"; at most 36 columns; above 36 months the default granularity is Quarter |
| Waterfall grid | DS-CMP-10 DataGrid (treegrid when `rows=obligation` groups obligations under contracts) | RPT-01 columns |
| Schedule lines grid | DS-CMP-10 DataGrid | `layout=lines` |
| Anomaly flag drawer | DS-CMP-09 informational drawer (`drawer=flag`) embedding the §8.4 flag block | Opened from the Flags cell |

**Data bindings.**

| Region | Read | Notes |
|---|---|---|
| Waterfall (chart and grid) | `POST /report-runs` `{report_code: "revenue_waterfall", parameters: {entity_codes, book, from_period_key, to_period_key, as_of, known_at, period_lock_id, row_dimension, granularity, measure, currency_view, filters}, output_format: "JSON"}`; `GET /report-runs/{id}/data` | RV-01; one run per parameter set (BR-RPT-01); parameters per RPT-01. Rev 1.92: `entity_codes` is the context entity — the pill's where the address named none, written into the address before the run is asked — and is not sent under `entities=all` (§0.5 "The context of a view") |
| Cell drill | `GET /explain/report-runs/{id}/cell?row_key&column_key` | SB-R-07 |
| Schedule lines | `GET /schedule-lines?entity&book&from_period&to_period&contract&obligation&line_type&as_of&known_at&count=true` (API-R-35) | `layout=lines` |
| Period states and the Open marker | `GET /periods?entity&book` | First `open` period for DS-CH-01's marker |
| Anomaly flags | `GET /exceptions?source=ANOMALY&status=OPEN,IN_PROGRESS&entity&period` grouped by `contract_id` (count per row) | §8.4 |

**Grid columns: waterfall.** RPT-01 (§5.6) plus one column "Flags": open anomaly flags of the row's contract, rendered as chip Warning with the caption "<n> flags" (link opens the flag drawer). Saved-view code `SF-04#waterfall`.

**Grid columns: schedule lines.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Contract | contract external id (`contract_id`) | mono link | SF-03 |
| Obligation | obligation key (`subject_id` when `subject_type = obligation`) | mono link | SF-03:obligation |
| Subject | `subject_type` | "Obligation", "Contract cost asset", "Contract" | none |
| Entity | entity code (`entity_id`) | mono | none |
| Period | `period_id` → label, with period chip | DS-FMT-19 | SF-05 of that period |
| Line type | `line_type` | E-28 label: "Normal", "Catch-up", "Price change", "Breakage", "Royalty", "Return", "Modification", "Opening balance" | none |
| Currency | `currency` | mono | none |
| Amount | `amount` | money, Explain (`schedule_line` `amount`) | Explain |
| Cumulative | `cumulative_amount` | money | none |
| Quantity | `quantity` | DS-FMT-11; em dash when null | none |
| Released at close | `is_released_at_close` | "Yes" / "No" | none |
| Computed | `created_at` | DS-FMT-17, `data-volatile` | none |

Saved-view code `SF-04#lines`.

**States.**

| State | Copy |
|---|---|
| SCR-ST-03 | Title "No schedules for <period label>"; description "Schedules appear once contracts in this entity and book are computed."; primary "Go to Contracts" (DS-CMP-23) |
| SCR-ST-04 | "No schedules match these filters" |
| Chart empty | "No revenue scheduled for this range." (DS-CMP-14) |
| Running report | DS-CMP-24 "Running Revenue waterfall" in the grid region; the previous run stays visible until the new run succeeds |
| All entities, mixed currencies | Info banner "Figures are shown per transaction currency. Switch the currency view to Reporting to see one total." (DS-FMT-12). Rev 1.92: all entities is an address that says `entities=all` |
| The context is being filled (rev 1.92; §0.5 "The context of a view") | SCR-ST-01 in the page's place; no run is asked |
| The entities, the books or the calendar that fill the address cannot be read (rev 1.92) | The `h1` and a negative banner "Could not load the revenue waterfall" with the API's sentence and "Retry", which reads again; no run is asked |
| As locked (rev 1.98; §0.5 RV-04) | The grid is the lock's frozen `WATERFALL` dataset as it is: one row per obligation of the lock's period under the frozen header, every cell text — not RPT-01's columns by period — and no chart. The bar's fields are shown and unavailable under RV-04's sentence, "From" and "To" both the lock's period; "Layout" stays. What an as-locked Schedules page shows beyond the frozen table is not designed (the supervisor's ruling of 2026-10-02 09:15, point D5) |

**Interactions, keyboard and copy.**

| Element | Interaction | Keyboard |
|---|---|---|
| Chart segment | Opens the grid filtered by `f.period` and `f.state` (DS-CH-01); from Home the same parameters arrive in the URL | Left, Right, Enter |
| Waterfall cell | RV-09: single-contributor cells open Explain (J-16.2); multi-contributor cells open the Explain contributor list; the context menu (Shift+F10) offers "Open schedule lines", which switches to `layout=lines` with the row's contract or obligation and period | Enter drills; Esc returns focus to the cell (J-16.6) |
| "Layout" switch | Waterfall and Lines keep filters; Lines has no run stamp because it reads current schedule lines | Arrow keys |
| Flags cell | Opens the anomaly flag drawer | Enter |
| Row dimension select | Re-runs with `row_dimension`; option labels "Contract", "Obligation", "Product", "Revenue category" | Enter |

**Sample world.** WLD-T-01, AVM-US, `ASC606`. J-15.2 (asserted, as locked Sep 2026): K-01 `SF-ORD-10001` O1 Sep 2026 9,764.38; K-01b `SF-ORD-10388` O1 4,891.30; K-03 `PRJ-CB-2026-01` 229,852.94. J-15.7 (asserted): context AVM-JP, `granularity=quarter`, K-10 `JP-LIC-0001`: `FY2027 Q1` 50,000,000 and `FY2027 Q2` 5,000,000 (JPY, no decimals). J-16.1 (asserted consistency): opened from Home with AVM-US Sep 2026, the waterfall total equals the Home Revenue figure. J-16.2 (before J-13): K-03 Sep 2026 cell 197,294.12 opens Explain with the decomposition Modification `CR-CASTELLAN-2026-09` 91,463.41; Progress (costs 82,000.00) 135,000.00; Estimate change (EAC 820,000.00 → 850,000.00) (29,169.29).

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Schedules" | `SF-04-page` |
| Chart | figure named "Revenue by period · <currency> · <book label>" | `SF-04-chart-waterfall` |
| Waterfall grid | grid named "Revenue waterfall" | `SF-04-grid-waterfall` |
| Waterfall row | row header "<contract external id>" (and obligation key) | `SF-04-row-<external id normalised>` or `SF-04-row-<external id normalised>-<obligation key normalised>` (for example `SF-04-row-sf-ord-10001-o1`) |
| Schedule lines grid | grid named "Schedule lines" | `SF-04-grid-lines` |
| Run stamp | meta row "Report Revenue waterfall …" | `SF-04-run-stamp` |
| Tie-out strip | region named "Tie-outs …" | `SF-04-banner-tie-outs` |
| Flag drawer | complementary region named "Anomaly flags · <external id>" | `SF-04-drawer-flag` |

**Light and dark.** DS-CH-01 series `--viz-recognized`, `--viz-scheduled` and the hatch `--viz-awaiting` must be reviewed in both themes; the Open marker rule `--fg-2`.

**Accessibility.** The waterfall grid exposes row headers (contract, obligation) and column headers (period) in the accessibility tree (NFR-22); the chart is a `figure` with the DS-CH-01 summary text and the Table view; the Flags chip's accessible name is "Warning, <n> anomaly flags".

## 5. Reports (SF-08)

The Reports area renders `h1` "Reports" and the route tabs **Catalogue** (SF-08), **Evidence packs** (SF-09), **Audit log** (SF-09:audit-log) and **Scenarios and forecasts** (SF-17) (SCR-IA-02). Report views (SF-08:report), run records (SF-08:run, SF-08:runs), the disclosure pack (SF-08:disclosure-pack) and dashboards (SF-08:dashboard) render their own `h1` with the breadcrumb "Reports > <title>".

### 5.1 SF-08 Report catalogue

| Field | Value |
|---|---|
| Screen id | SF-08 |
| Route | `/reports` (RT-31) with `q`, `f.group`, `f.kind` |
| Roles and permissions | Read `report.run` (RT-31): Revenue Accountant, Revenue Reviewer, Controller, SSP Analyst, SSP Approver, Integration Admin, Auditor, Viewer. Pin a report: authenticated |
| Purpose | Find every standard report, register, disclosure, extract, legacy export and pack, open dashboards and the disclosure pack, and see recent runs |
| REQ | REQ-RPT-001, 002, 016, 024, 027; REQ-UX-017 |
| Journeys | J-15.1 to J-15.9, J-17.3, J-17.6, J-22.8, J-24.2 (tour stop 6) |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Reports                                                                                                              |
| Catalogue   Evidence packs   Audit log   Scenarios and forecasts                                                     |
+----------------------------------------------------------------------------------------------------------------------+
| [Search reports________________]   [Group is Balances and disclosures x]  [Filter]                                   |
+-------------------------------------------------------------------------+--------------------------------------------+
| Dashboards                                                              | Recent runs                    View all >  |
|   Revenue dashboard · Revenue, balances, RPO and anomaly flags          | RPT-000412  RPO           Succeeded  12 Sep |
|   Close dashboard · Close status of every entity for the period         | RPT-000411  Contract bal… Succeeded  12 Sep |
|   Disclosure pack · Revenue disclosures with tie-outs for one entity    | RPT-000409  JE population Succeeded  11 Sep |
+-------------------------------------------------------------------------+--------------------------------------------+
| Balances and disclosures (10)                                                                                        |
| Contract balances                   Contract assets, liabilities and receivables at period end   <Standard>  XLSX CSV PDF |
| Contract balance rollforward        Opening, billings, revenue, reclassifications, FX, closing   <Disclosure>  XLSX CSV PDF|
| Remaining performance obligations   RPO by contract and time band, with exempt listing           <Disclosure>  XLSX CSV PDF|
| ...                                                                                                                  |
| Registers (…)                                                                                                        |
| ...                                                                                                                  |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** "Recent runs" moves below "Dashboards"; report descriptions truncate to one line with a tooltip.

```text
+--------------------------------------------------------------------------------------------------------+
| Reports                                                                                                |
| Catalogue  Evidence packs  Audit log  Scenarios and forecasts                                          |
| [Search reports____]  [Filter]                                                                         |
| Dashboards: Revenue dashboard · Close dashboard · Disclosure pack                                      |
| Recent runs  RPT-000412 RPO Succeeded 12 Sep 2026 · …                                     View all >  |
| Balances and disclosures (10)                                                                          |
| Contract balances            Contract assets, liabilities and receivables…     <Standard>  XLSX CSV   |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.**

| Region | Components | Content |
|---|---|---|
| Area header | DS-CMP-06 plain header; DS-CMP-07 route tabs | `h1` "Reports" |
| Search and filters | DS-CMP-13 FilterBar | Quick search over name and description; filter fields "Group", "Kind" |
| Dashboards | flat list of links (DS-CMP-10 static table without headers) | "Revenue dashboard", "Close dashboard" (SF-08:dashboard), "Disclosure pack" (SF-08:disclosure-pack), each with a one-line description. Rev 1.82 (as built; BUILD_SPEC RPS-19, first head): the list holds the dashboards that are built — "Revenue dashboard" with "Revenue, balances, RPO and anomaly flags"; "Close dashboard" joins with the item's second head and "Disclosure pack" with SF-08:disclosure-pack. Each row is a link in the page's context (entity, period, book), without the catalogue's own parameters, and its description; the rows are a list, not a table — they have no columns to head. The region is absent while no dashboard is built |
| Recent runs | DS-CMP-10 static table, at most 10 rows | The viewer's runs, newest first; "View all" → SF-08:runs |
| Report groups | one static table per group (caption "<group label> (<n>)") | Rows per report definition in §5.6 index order |

**Data bindings.** `GET /report-definitions` (API-S-ReportDefinition: `code`, `version`, `name`, `kind`, `description`, `output_formats`, `tie_outs`); recent runs `GET /report-runs?created_from=<today minus 30 days>&limit=50` (04 API-R-41; default order newest first, API-C-09 and NC-04), keeping the items whose `run_by.id` equals `GET /me` `user.id` and showing the first 10, because 04 defines no creator filter; favourites `GET /saved-views`, pin `POST /saved-views` `{screen_code: "SF-08:report", name, config: {target: "report", path: "/reports/<code>", label}, is_favourite: true}` (SCR-IA-08).

**Grid columns: report group table.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Report | `name` | link | SF-08:report `/reports/<code>` with the current context; packs link to SF-09 |
| Description | `description` | text, one line, tooltip | none |
| Kind | `kind` | outline chip "Standard", "Register", "Disclosure", "Extract", "Pack", "Legacy export" | none |
| Outputs | `output_formats` | mono codes separated by spaces, JSON omitted | none |
| Version | `version` | "v<n>" | none |
| Pin | none | ghost icon button "Pin <report name>" / "Unpin <report name>" | none |

Recent runs columns: "Run" (`report_run_no`, mono link to SF-08:run); "Report" (`report.name`); "Status" (chip E-67); "Run at" (`started_at`, DS-FMT-16 date part, `data-volatile`).

Groups (labels and membership; the §5.6 index assigns each code):

| Group label | Codes |
|---|---|
| "Revenue and analysis" | `revenue_waterfall`, `bookings_billings_revenue`, `variance_between_closes`, `book_bridge`, `adoption_bridge`, `intercompany_pairs` |
| "Balances and disclosures" | `contract_balances`, `contract_balance_rollforward`, `revenue_from_opening_liability`, `revenue_from_prior_period_obligations`, `rpo`, `rpo_rollforward`, `disaggregation`, `contract_cost_rollforward`, `loss_provision_register`, `balance_aging` |
| "Contracts, modifications and judgements" | `contract_history`, `latest_contract_status`, `modification_register`, `estimate_change_listing`, `judgement_register`, `scope_exclusion_register` |
| "Journals and close" | `je_population`, `out_of_period_register`, `late_entry_report`, `manual_adjustment_register`, `legacy_je_summary` |
| "SSP" | `ssp_change_log`, `ssp_version_diff`, `allocations_by_ssp_version`, `ssp_override_listing` |
| "Access, configuration and audit" | `config_change_register`, `user_access_listing`, `sod_conflict_report`, `approvals_register`, `api_client_inventory`, `audit_log_export`, `chain_verification_report` |
| "Forecasts and migration" | `forecast_outputs`, `actual_vs_forecast`, `migration_reconciliation`, `parallel_run_comparison` |
| "Legacy exports" | `legacy_contract_history_export`, `legacy_latest_contract_export` |
| "Data extracts" | `extract_contracts`, `extract_obligations`, `extract_contract_versions`, `extract_schedule_lines`, `extract_subledger_lines`, `extract_journal_lines`, `extract_balances`, `extract_events`, `extract_legacy_contract_live` |
| "Evidence packs" | `period_evidence_pack`, `contract_sample_pack` (links open SF-09) |

Visibility rules: `forecast_outputs` and `actual_vs_forecast` render only in sandbox tenants that hold a `scenario` (REQ-FC-003, 005); `migration_reconciliation` and `parallel_run_comparison` render when `GET /migrations?limit=1` returns an item; `legacy_je_summary` links to SF-06:entries.

**States.**

| State | Copy |
|---|---|
| SCR-ST-04 | "No reports match these filters" |
| Recent runs empty | Title "No report runs yet"; description "Every report you view or export creates a run record with its parameters, totals and output hash." |
| SCR-ST-05 | "Could not load the report catalogue" |

**Interactions, keyboard and copy.** Enter on a report name opens it; the pin button toggles and announces "Pinned <report name>" or "Unpinned <report name>". The Help menu's guided tour stop 6 anchors on the Balances and disclosures table (J-24.2).

**Sample world.** WLD-T-01: all 1.0 codes except the forecast reports (production tenant) and the migration reports (no migration). WLD-T-30 (scenario sandbox): forecast reports visible. WLD-T-21 and WLD-T-23: migration reports visible.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Reports" | `SF-08-page` |
| Group table | table named "<group label> (<n>)" | `SF-08-grid-<group label normalised>` (for example `SF-08-grid-balances-and-disclosures`) |
| Report row | link named "<report name>" | `SF-08-row-<code normalised>` (for example `SF-08-row-rpo`) |
| Recent runs | table named "Recent runs" | `SF-08-grid-recent-runs` |
| Dashboards list | region named "Dashboards" | `SF-08-dashboards` |

**Light and dark.** Group tables on `--bg-surface` with `--border-default` outlines on `--bg-canvas`; outline chips.

**Accessibility.** Each group table has a `caption`; kind chips are text; pin buttons are toggle buttons with `aria-pressed`.

### 5.2 SF-08:report Report view

| Field | Value |
|---|---|
| Screen id | SF-08:report |
| Route | `/reports/:reportCode` (RT-32) with context `entity`, `period`, `book`, `currency_view`, `known_at`, `snapshot` (OQ-B-04), the screen parameters `run` and `p.<parameter key>` (SCREENS.md SCR-URL-16, SCR-URL-17), and grid parameters `sort`, `f.*`; rev 1.92: and the screen parameter `entities` (`all`; SCREENS.md SCR-URL-01 rev 1.61) — an address that names no entity takes the context pill's, and one that says `entities=all` is every entity's in scope (§0.5 "The context of a view") |
| Roles and permissions | Read `report.run` (RT-32). Export `report.export` (Revenue Accountant, Revenue Reviewer, Controller, Auditor, Viewer). "IPE documentation" needs `report.export`, because `ipe_logic` is returned only with that permission (API-S-ReportDefinition) |
| Purpose | Run a standard report with parameters, read it on screen with tie-outs and drill-through, export stamped outputs and reproduce any run from the same source |
| REQ | REQ-RPT-002, 003, 004 to 013, 017, 019 to 028; REQ-JE-018; REQ-CLS-006, 007; CTL-027 to CTL-030 |
| Journeys | J-15.3 to J-15.6, J-15.8, J-15-AC-1 to AC-4, J-17.3, J-17.6, J-17.8, J-21.6, J-22.8 |

**Wireframe, 1440 px (`rpo`, AVM-US, as locked Sep 2026).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Reports > Remaining performance obligations                                                                          |
| Remaining performance obligations                                        [IPE documentation]  [Run details]  Export v|
| RPO by contract and expected timing of recognition (ASC 606-10-50-13).                                               |
| {AVM-US v} {ASC 606 v} As of {30 Sep 2026 v}  Time bands 12, 24 months  {Rows: Contract v}   [*Run report]            |
| Report RPO v1 · Run RPT-000412 · Entity AVM-US · Book ASC 606 · As of 30 Sep 2026 · Source As locked on 01 Oct 2026…  |
| Engine 1.0.0 · Run by Marcus Webb · Run at 12 Sep 2026 16:02 UTC · Rows 211 · Output SHA-256 5c1e7a90…04b2            |
| [i] Showing Sep 2026 as locked on 01 Oct 2026 09:14 UTC.  Show current figures                                        |
| Tie-outs (1 pass, 0 fail)  (Pass) RPO rollforward closing equals RPO report total                                    |
+----------------------------------------------------------------------------------------------------------------------+
| Remaining performance obligations by time band · USD · ASC 606                                   (Chart | Table)     |
| ■ Within 12 months  ■ 13 to 24 months  ■ After 24 months                                                             |
| Total          ##########################################//////////                                                |
+--------------------+----------------+---------+--------------+--------------+--------------+--------------+----------+
| Contract           | Customer       | Entity  | Total (USD)  | Within 12    | 13 to 24     | After 24     | Current  |
|                    |                |         |              | months (USD) | months (USD) | months (USD) | (USD)    |
| SF-ORD-10002       | Marrowby Hea…  | AVM-US  |   208,339.79 |   166,398.30 |    41,941.49 |         0.00 |   …      |
| PRJ-CB-2026-01     | Castellan Bu…  | AVM-US  |   520,147.06 |            … |            … |            … |   …      |
| SF-ORD-10417       | Orrin Vale A…  | AVM-US  |   105,043.80 |            … |            … |            … |   …      |
| Total              |                |         |            … |            … |            … |            … |   …      |
+====================+================+=========+==============+==============+==============+==============+==========+
| Exempt contracts (0)   No contracts are excluded. AVM-US applies no RPO practical expedient.                          |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** The run stamp wraps to three lines; the chart panel collapses to "Table" by default below 1280 px only when more than 12 rows are charted; money columns keep width and the grid scrolls horizontally with "Contract" pinned.

```text
+--------------------------------------------------------------------------------------------------------+
| Remaining performance obligations                         [IPE documentation] [Run details] Export v   |
| {AVM-US v} {ASC 606 v} As of {30 Sep 2026 v} Time bands 12, 24   [*Run report]                          |
| Report RPO v1 · Run RPT-000412 · As of 30 Sep 2026 · As locked · Rows 211                               |
| Tie-outs (1 pass, 0 fail)                                                                               |
| Contract       | Total (USD)   Within 12 months (USD)   13 to 24 months (USD)   After 24 months (USD)      |
| SF-ORD-10002   |  208,339.79              166,398.30                41,941.49                    0.00      |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.**

| Region | Components | Content |
|---|---|---|
| Header | DS-CMP-06 plain header; DS-CMP-20 buttons; DS-CMP-28 export menu | `h1` = definition `name`; description (`body-sm`, 72ch cap); "IPE documentation"; "Run details"; "Export" |
| Parameters toolbar | DS-CMP-21 fields; DS-CMP-31 segmented controls | RV-08; the report's parameters in §5.6 order |
| Run stamp | DS-CMP-06 meta row | RV-02 |
| Banners | DS-CMP-29 | RV-04 source banners; RV-12 election notes; SCR-ST-10 time travel |
| Tie-out strip | static list with chips | RV-05 |
| Chart panel | DS-CMP-14 with DS-CH-01, DS-CH-02 or DS-CH-03, or plain bars | Only for reports whose §5.6 spec names a chart |
| Sections | one DS-CMP-10 DataGrid per data section of the §5.6 spec (for example "Remaining performance obligations" and "Exempt contracts") | Section heading `h2` with row count |
| Footnotes | text block (`body-sm`, `--fg-2`) | Practical expedients and definitions per §5.6 |
| Run details | DS-CMP-09 docked panel (`drawer=run-details`) | RV-03 |
| IPE documentation | DS-CMP-09 docked panel (`drawer=ipe`) | Definition `code`, `version`, `kind`, `description`, `parameters_schema` (every key, type, default), `ipe_logic.source_tables`, `joins`, `filters`, `parameters`, `tie_outs`; button "Download definition (JSON)" (REQ-RPT-027) |

**Data bindings.**

| Region | Read or command | Notes |
|---|---|---|
| Definition | `GET /report-definitions/{code}` | Unknown code: SCR-ST-07 "Report not found" |
| Run | `POST /report-runs` `{report_code, parameters, output_format: "JSON"}` (202; job `REPORT_RUN`); `GET /report-runs/{id}` | RV-01; parameters from the URL: `entity` → `entity_codes` (rev 1.92: an address that names no entity is filled with the context pill's before the run is asked; under `entities=all` no `entity_codes` is sent and the run covers every entity in scope, as an absent `entity` did before — §0.5 "The context of a view"), `book` → `book`, `period` → `period_key` and `as_of` = period end date, `snapshot` → `period_lock_id`, `known_at` → `known_at`, `p.<key>` → `<key>` |
| Data | `GET /report-runs/{id}/data?cursor&limit=200` (04 API-R-41) | RV-11; each row has `row_key`; a report with several data sections groups its rows by the row field `section` (RPT-R-09); rows keep the response order, because 04 defines no sort or section parameter for run data |
| Cell drill | `GET /explain/report-runs/{id}/cell?row_key&column_key` | RV-09 |
| Export | `POST /report-runs` with `output_format`; `GET /report-runs/{id}/output` | RV-06; permission `report.export` |
| Rerun | `POST /report-runs/{id}/rerun` | RV-03 |

**Grid columns.** Per report, §5.6.

**States.**

| State | Copy |
|---|---|
| Before the first run of a parameter-heavy report (a report whose required parameters have no default) | Title "Choose parameters to run <report name>"; description "<report name> needs <parameter labels>. Each run records its parameters, totals and output hash." |
| Running | DS-CMP-24 "Running <report name>" in the sections region; parameters stay editable; a second "Run report" while running is ignored with the toast "<report name> is already running." |
| RV-13 empty run | §5.6 empty copy |
| RV-14 failed run | SCR-ST-12 |
| Required parameter missing on submit | "<parameter label> is required." |
| SCR-ST-07 | "Report not found" |
| The context is being filled (rev 1.92; §0.5 "The context of a view") | SCR-ST-01 in the page's place; no run is asked |
| The entities, the books or the calendar that fill the address cannot be read (rev 1.92) | Negative banner "Could not load the report" with the API's sentence and "Retry", which reads again; no run is asked |

**Interactions, keyboard and copy.** RV-01 to RV-14. Keyboard: the parameters toolbar is a DS-CMP-13 toolbar (one tab stop, arrow keys between fields); grids per DS-CMP-10; Enter on a drillable cell drills; `E` on a figure opens Explain; Esc returns focus. Copy: button labels "Run report", "Run details", "IPE documentation", "Export", "Rerun from the same source"; toast "Report <name> ran. <row count> rows." only when a run takes longer than 2 seconds.

**Sample world.** J-15.3 (asserted): `contract_balances` at 30 Sep 2026: K-01 contract liability 29,944.11; K-02 contract liability 28,339.79; K-03 contract asset and unbilled receivable total 129,852.94. J-15.4 (asserted): `rpo` at 30 Sep 2026: K-02 total 208,339.79, within 12 months 166,398.30, 13 to 24 months 41,941.49, after 24 months 0.00; K-03 total 520,147.06; K-09 total 105,043.80. J-15.5: XLSX export with the RV-07 header (report name and version, run id, parameters with `as_of` 2026-09-30 and the lock id, engine release, user, UTC time, row count, control totals, output SHA-256). J-15.6: rerun from the same snapshot: "Output identical: Yes", "Control totals identical: Yes". J-15-AC-4: exempt listing empty. J-15.8: `legacy_contract_history_export` CSV for `SF-ORD-10001`, 01 Jan 2026 – 30 Sep 2026.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "<report name>" | `SF-08-page` |
| Parameters toolbar | toolbar named "Report parameters" | `SF-08-filter-bar` |
| Run report | button named "Run report" | none |
| Run stamp | meta row beginning "Report <name>" | `SF-08-run-stamp` |
| Tie-out strip | region named "Tie-outs …" | `SF-08-banner-tie-outs` |
| Chart | figure named per §5.6 | `SF-08-chart-<code normalised>` |
| Section grid | grid named "<section heading>" | `SF-08-grid-<section normalised>` (for example `SF-08-grid-exempt-contracts`) |
| Row | row header per §5.6 row key | `SF-08-row-<row key normalised>` (for example `SF-08-row-sf-ord-10002`) |
| Export menu | button named "Export" | none |
| Run details drawer | complementary region named "Run details" | `SF-08-drawer-run-details` |
| IPE drawer | complementary region named "IPE documentation" | `SF-08-drawer-ipe` |

**Light and dark.** Chart ramps (DS-VIZ-06 ordinal time bands; DS-CH-02 increase, decrease and total colours) must be reviewed in both themes; totals rules.

**Accessibility.** Each section grid is labelled by its `h2`; the run stamp is a `dl`; figures announce currency in their accessible names; charts have Table views.

### 5.3 SF-08:runs Report run register and SF-08:run Run record

| Field | Value |
|---|---|
| Screen ids | SF-08:runs (SCREENS.md §0.4; §14); SF-08:run |
| Routes | `/reports/runs` (RT-106) with `f.report_code`, `f.status`, `f.created_from`, `f.created_to`; `/reports/runs/:runId` (RT-33) |
| Roles and permissions | Read `report.run`; downloading an output needs `report.export` (or `evidence.export` for pack outputs); "Rerun" needs `report.run`. Rev 1.53: both screens open for a holder of `report.run` or `audit.read`, the two permissions the report routes admit (04 API-R-41 rev 1.128; ruling R-63 (a)); a run is listed, opened and rerun under its report's run permission, which the API decides — the screens filter nothing and offer the rerun on every run shown |
| Purpose | List every report and export run with its IPE fields, and show one run record with its parameters, totals, tie-outs, output hash and manifest (the report run register of research 07 RPT-01, A-18) |
| REQ | REQ-RPT-002, 027; CTL-029 |
| Journeys | J-15-AC-3, J-15.6, J-17-AC-4 |

**Wireframe, 1440 px (SF-08:run).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Reports > Runs > RPT-000412                                                                                           |
| Report run RPT-000412   (Succeeded)                                   [Open report view]  [Download XLSX]  [*Rerun] |
| Report RPO v1 · Entity AVM-US · Book ASC 606 · As of 30 Sep 2026 · Source As locked (lock 8b10…aa42)                  |
| Engine 1.0.0 (build 3f9a1c22) · Run by Marcus Webb · Started 12 Sep 2026 16:02:11 UTC · Finished 16:02:19 UTC         |
+----------------------------------------------+-----------------------------------------------------------------------+
| Parameters                                   | Control totals                                                        |
| entity_codes      AVM-US                     | row_count             211                                             |
| book              ASC606                     | total_rpo (USD)       …                                               |
| as_of             2026-09-30                 | Tie-outs                                                              |
| period_lock_id    8b10…aa42                  | (Pass) RPO rollforward closing equals RPO report total                |
| time_bands        12, 24                     | Output                                                                |
| known_at          2026-10-01T09:14:02Z       | Format XLSX · SHA-256 5c1e7a90…04b2 · Manifest —                      |
|                                              | Ledger heads  ASC606 chain 1,388 · seal 9d21…7c0e                     |
+----------------------------------------------+-----------------------------------------------------------------------+
```

**Wireframe, 1280 px.** The two columns stack: Parameters, then Control totals, Tie-outs, Output.

```text
+--------------------------------------------------------------------------------------------------------+
| Report run RPT-000412  (Succeeded)                      [Open report view] [Download XLSX] [*Rerun]     |
| Parameters   entity_codes AVM-US · book ASC606 · as_of 2026-09-30 · period_lock_id 8b10…aa42            |
| Control totals   row_count 211 · total_rpo (USD) …                                                      |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** SF-08:runs: DS-CMP-06 plain header "Report runs"; DS-CMP-13 FilterBar; DS-CMP-10 DataGrid. SF-08:run: DS-CMP-06 record header (report run variant); static tables (DS-CMP-10 native) "Parameters", "Control totals", "Tie-outs", "Output", "Ledger heads"; DS-CMP-29 problem banner for failed runs; DS-CMP-24 for a running rerun.

**Data bindings.** `GET /report-runs?report_code&status&created_from&created_to&count=true`; `GET /report-runs/{id}`; `GET /report-runs/{id}/output`; `POST /report-runs/{id}/rerun`; manifest `GET /files/{manifest_file_id}/content`.

**Grid columns: SF-08:runs.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Run | `report_run_no` | mono link | SF-08:run |
| Report | `report.name`, `report.version` | "<name> v<n>" | SF-08:report |
| Status | `status` | chip E-67 | none |
| Entity | `entity_scope[].code` | mono, comma-separated | none |
| Book | `book` | label | none |
| As of | `as_of` | DS-FMT-16 | none |
| Source | `period_lock_id` | "As locked" or "Current" | none |
| Format | `output.format` | mono | none |
| Rows | `row_count` | integer | none |
| Output SHA-256 | `output.sha256` | DS-FMT-23 prefix, copy | none |
| Run by | `run_by` | user cell | none |
| Started | `started_at` | DS-FMT-17 | none |
| Finished | `finished_at` | DS-FMT-17 | none |

Saved-view code `SF-08:runs`.

**As bound to API-R-41 of 1.0 (rev 1.53; BUILD_SPEC RPS-18).** *SF-08:runs.* The page is the Reports frame (SCREENS.md §0.3 SCR-IA-02): the `h1` "Reports" and the route tabs with "Report runs" current, a tab that renders for a holder of `report.run` or `audit.read`; the DataGrid is named "Report runs" (the plain header of the regions row is the frame's). The FilterBar writes the route's four filters: `f.report_code` ("Report", the report definitions by name; is or in), `f.status` ("Status", E-67; is or in), `f.created_from` ("Created from", `gte:<date>`) and `f.created_to` ("Created to", `lte:<date>`). The two dates are whole days of platform time: `created_from` is sent as 00:00:00Z of its day and `created_to`, which API-R-41 reads as exclusive, as 00:00:00Z of the day after. The register has no default range (T-RPT-02 is not partitioned) and no quick search (the route has none). It keeps the API's order, newest first, and no column sorts: API-R-41 sorts by `id` or `created_at`, the run carries neither as a column, and "Started" has no key (a `started_at` key is item G-6 of lane API-GAPS). "Report" links to SF-08:report as "Open report view" below; "Source" reads "As locked" or "Current" by `period_lock_id`; "Output SHA-256" shows the DS-FMT-23 prefix with a copy button and the whole hash for assistive technology. States: SCR-ST-04 "No report runs match these filters"; SCR-PERM-01 for a member with neither permission, "You do not have access to report runs" and "Ask a workspace administrator for a role that includes running reports or viewing the audit log." *SF-08:run.* The record header shows the crumbs "Reports" (for a holder of `report.run`) and "Report runs", the `h1` "Report run <run no>" with the E-67 chip, and one meta row: Report, Entity, Book, As of, Source ("As locked (lock <id prefix>)" or "Current, known at <timestamp>"), Engine ("<version> (build <8 characters>)"), Run by, Started and Finished with seconds. The static tables carry their titles as captions: "Parameters" (every key the run stored, defaults included, as recorded); "Control totals" (a total the run recorded per currency as amounts, any other value as stored); the RV-05 tie-out strip; "Output" (Format, Output SHA-256 with copy, Manifest as the link "Download manifest" for a holder of the export permission, Rows); "Ledger heads" (per book "chain <sequence>" and the seal as a DS-FMT-23 prefix); "Source" (Period lock; Known at with its basis in the RV-03 words; Sources with the RV-03 sentence of `sources.kind` and "Not bound: <items>"). A table the run recorded nothing for says so in one row. "Open report view" opens SF-08:report with the run's parameters as the view's URL carries them — `entity_codes` of one entity as `entity` and of several as `entities=all` (rev 1.92; §0.5 "The context of a view": an address that names no entity is the pill's entity, and the view would stand in one entity around a run of several), `book`, `period_key` as `period`, `period_lock_id` as `snapshot`, a supplied `known_at` (`known_at_basis` `historical`), `currency_view`, every other key as `p.<key>` — and, for a JSON run, `run=<id>`, so the view renders the stored run and creates none; it is not offered for the two pack reports, which have no report view. "Download <format>" renders when the run has an output and the member holds `report.export` (`evidence.export` for a pack output). The rerun follows RV-03 rev 1.19 by `sources`: "Rerun from the same source"; "Rerun (new evaluation)" for an `open` run, a `failed_without_capture` run and an `open` builder's `legacy_unbound` run; unavailable, with the "Unbound…" sentence as its reason, for a `legacy_unbound` run of a builder that binds its source; not offered while the run computes. *The rerun result.* Final state: the record of a run that repeats another shows "Rerun of <run no>" with "Output identical: <Yes|No>" and "Control totals identical: <Yes|No>" whenever it is opened, read from API-S-ReportRun (`rerun_of` and the two flags, which the CTL-029 fact holds; item G-6 of lane API-GAPS). **Interim, until those members are on main:** the page that started the rerun follows its job (DS-CMP-24 on the record) and, on success, opens the new run's record — `report_run_id` of the job result — carrying the two answers in the navigation state; that record shows the status block `SF-08-banner-rerun-result` with the title "Rerun of <run no>", the two lines and the link "Open <run no>", positive when both answers are Yes and a warning otherwise; a record opened later does not show it. A failed rerun job shows "<job label> failed. Nothing was committed."; a refused rerun shows its problem. *States.* Failed: the negative banner "The run failed: <problem title>. Nothing was exported." with the problem's detail and the RV-14 reference of the run's own job. Running: DS-CMP-24 "Running <report name>" from the run's job, the record read again until the run ends. Rev 1.59: the progress is shown to who may read the job — the run's starter and a holder of `audit.read` (04 API-R-11: a job is read by its owner or by a holder of `audit.read`; rev 1.76: of `audit.read` for all entities, 04 rev 1.219, so a holder of named entities is another reader); another reader of the run sees the line "Running <report name>" without progress, the job is not asked for, and the record is read again until the run ends all the same. SCR-ST-07 "Report run not found" with "Go to report runs": API-R-41 answers a run the member may not see as an unknown id. Rev 1.101 (register index 280): "a refused rerun shows its problem" is the problem's title, its detail and every sentence of its findings, each once (DS-CMP-29, the `RefusalBanner` of DG-FE-06); before, the record said the title and the detail, and the sentence of a finding — the lock to pass, for a run that names a record which froze no dataset — was shown nowhere.

**States.** SF-08:runs SCR-ST-03: title "No report runs yet"; description "Every report view, export and pack creates a run record here." SF-08:run failed: negative banner "The run failed: <problem title>. Nothing was exported." SF-08:run running: DS-CMP-24 "Running <report name>". SCR-ST-07: "Report run not found".

**Interactions, keyboard and copy.** "Open report view" opens SF-08:report with `run=<id>` (JSON runs) or with the same parameters (file runs). "Download <format>" downloads the output. "Rerun" per RV-03 and opens the new run record on success with the result lines "Output identical: <Yes|No>" and "Control totals identical: <Yes|No>".

**Sample world.** J-15.6 (asserted): rerun of the RPO run from the same snapshot has identical control totals and output hash. J-15-AC-3: every run of J-15 appears in SF-08:runs with the REQ-RPT-002 fields.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Runs grid | grid named "Report runs" | `SF-08-grid-runs` |
| Run record parameters | table named "Parameters" | `SF-08-grid-run-parameters` |
| Control totals | table named "Control totals" | `SF-08-grid-run-control-totals` |
| Rerun result | status "Output identical: …" | `SF-08-banner-rerun-result` |
| Run row; filter bar; saved-view selector (rev 1.53) | row of the grid; toolbar "Filters"; button "View: <name>" | `SF-08-row-<run no>`; `SF-08-filter-bar`; `SF-08-saved-view` |
| Empty register (rev 1.53) | heading "No report runs yet" | `SF-08-empty-runs` |
| Output; ledger heads; source (rev 1.53) | tables named "Output", "Ledger heads", "Source" | `SF-08-grid-run-output`; `SF-08-grid-run-ledger-heads`; `SF-08-grid-run-source` |
| Failed run (rev 1.53) | heading "The run failed: …" | `SF-08-banner-run-failed` |

**Light and dark.** Mono hash prefixes; chips.

**Accessibility.** Hash prefixes have accessible names with the full value (DS-A11Y-12); parameters table `caption` "Parameters".

### 5.4 SF-08:disclosure-pack Disclosure pack

| Field | Value |
|---|---|
| Screen id | SF-08:disclosure-pack |
| Route | `/reports/disclosure-pack` (RT-34) with `entity` (one entity), `book`, `period`, `snapshot`, and the screen parameter `p.quarter` (`true` adds the fiscal quarter-to-date column; default `true`) |
| Roles and permissions | Read `report.run` (RT-34); export `report.export`. Viewers run and export (J-15.9); no command controls exist on this screen |
| Purpose | Assemble the revenue disclosures for one entity, book and period with every tie-out printed, from the lock snapshot when the period is locked |
| REQ | REQ-RPT-003, 005 to 011, 024 to 026; REQ-CST-006; REQ-POL-011; REQ-BIL-010; POL-190 to 204 |
| Journeys | J-15.1, J-15.9, J-15-AC-2, J-15-AC-4 |

**Wireframe, 1440 px (AVM-US, Sep 2026 and Q3 2026, as locked).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Reports > Disclosure pack                                                                                            |
| Disclosure pack · AVM-US · Sep 2026 · ASC 606                                           [Run details]  Export v      |
| {AVM-US v} {ASC 606 v} Period {Sep 2026 v} [x] Include quarter to date (Q3 2026)                [*Run disclosure pack] |
| Report Disclosure pack v1 · Run RPT-000420 · Source As locked on 01 Oct 2026 09:14 UTC · Reporting entity type PBE   |
| Tie-outs (4 pass, 0 fail)                                                                                            |
|  (Pass) Disaggregation total equals revenue journal total  (Pass) Rollforward closing equals contract balances       |
|  (Pass) RPO rollforward closing equals RPO report total    (Pass) Waterfall revenue equals revenue journal total     |
+-----------------------+----------------------------------------------------------------------------------------------+
| Sections              | 1 Disaggregation of revenue                                                                  |
| 1 Disaggregation      |   Revenue category        Timing of transfer      Sep 2026 (USD)     Q3 2026 (USD)          |
| 2 Contract balances   |   Subscription            Over time                           …                  …          |
| 3 Opening liability   |   Services                Over time                           …                  …          |
| 4 Prior-period        |   Total                                                       …                  …          |
|   obligations         | 2 Contract balances and rollforward                                                          |
| 5 RPO                 |   …                                                                                          |
| 6 Contract costs      | 5 Remaining performance obligations                                                          |
| 7 Expedients used     |   Exempt contracts (0)  No contracts are excluded. AVM-US applies no RPO practical expedient.  |
+-----------------------+----------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** The section index becomes a "Jump to section" select above the content.

```text
+--------------------------------------------------------------------------------------------------------+
| Disclosure pack · AVM-US · Sep 2026 · ASC 606                              [Run details] Export v       |
| {AVM-US v} {ASC 606 v} {Sep 2026 v} [x] Include quarter to date   [*Run disclosure pack]                |
| Tie-outs (4 pass, 0 fail)          {Jump to section v}                                                  |
| 1 Disaggregation of revenue  …                                                                          |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.**

| Region | Components | Content |
|---|---|---|
| Header, parameters, run stamp, tie-outs | RV-02, RV-05, RV-08 | `h1` "Disclosure pack · <entity code> · <period label> · <book label>"; "Reporting entity type" meta (`entity.reporting_type`, POL-190) |
| Section index | ordered list of links (in-page anchors) | Seven sections; election-suppressed sections keep their entry with "Omitted" |
| Sections | `h2` per section; DS-CMP-10 static tables or DataGrids; DS-CH-02 in section 2 | Section table below |
| Election notes | DS-CMP-29 info banner per suppressed section | RV-12 |

| # | Section `h2` | Source (report run or disclosure snapshot) | Content | Suppressed when |
|---|---|---|---|---|
| 1 | "Disaggregation of revenue" | RPT-08 `disaggregation` with `p.dimension_code=revenue_category`, `p.include_timing=true` | Revenue by category and timing of transfer for the period and the quarter to date | POL-191 `ELECT` (the timing table remains, POL-191 engine effect) |
| 2 | "Contract balances and rollforward" | RPT-02 and RPT-03 | Opening and closing contract liability, contract asset, unbilled receivable and receivables; rollforward table with DS-CH-02 bridge; current and noncurrent split (POL-124) | POL-192 `ELECT` (opening and closing balances remain) |
| 3 | "Revenue from the opening contract liability" | RPT-04 | One figure per column and per currency with the FIFO basis footnote (POL-126) | POL-192 `ELECT` |
| 4 | "Revenue from obligations satisfied in prior periods" | RPT-05 | Figure and decomposition by cause (POL-204) | POL-192 `ELECT` |
| 5 | "Remaining performance obligations" | RPT-06 | Totals by time band, current and noncurrent; "Exempt contracts" table with 50-15 descriptors | POL-193 `ELECT` |
| 6 | "Contract cost rollforward" | RPT-32 | By category obtain and fulfil | POL-196 `ELECT` |
| 7 | "Practical expedients used" | registry values of category `PRACTICAL_EXPEDIENT` resolved for the entity (`GET /policies/resolve` per key); `disclosure_kind` `EXPEDIENTS_USED` snapshot when locked | Table "Expedient", "Registry key", "Value", "Disclosure" (POL-015, POL-021, POL-045, POL-046, POL-140, POL-197 to POL-200, POL-202) | POL-195 `ELECT` |

Interim flag: when POL-203 lists a section as required for the quarterly pack, the quarter column's header shows the outline chip "Interim required" (REQ-RPT-026).

**Data bindings.** One report run `disclosure_pack` (04 T-RPT-01 rule 2, `child_report_run_ids`, `disclosure_snapshot_ids`; OQ-B-09 resolved by D-76) whose data sections are 1 to 7; when the period is locked, the run reads `GET /disclosure-snapshots?entity&book&period&disclosure_kind=<kind>` values frozen at lock (T-RPT-03); section runs per the table otherwise. Export: `POST /report-runs` `{report_code: "disclosure_pack", output_format: "PDF" | "XLSX"}`.

**Grid columns.** Section 1: "Revenue category" (dimension value label), "Timing of transfer" ("Point in time", "Over time"), "<period label> (<currency>)", "<quarter label> (<currency>)"; totals row. Sections 2 to 6: the RPT-02, RPT-03, RPT-04, RPT-05, RPT-06 and RPT-32 columns of §5.6, restricted to the entity and the two columns. Section 7: "Expedient" (POL question label), "Registry key" (mono), "Value" (option label "Applied" for `APPLY`, "Not applied" for `DO_NOT_APPLY`, "Elected" for `ELECT_*`, "Not elected" for `NOT_ELECTED` or `DO_NOT_ELECT`), "Disclosure" (copy "Disclosed under ASC <paragraph>").

**States.** Before the first run: title "Choose an entity and period"; description "The disclosure pack covers one legal entity at a time." All entities in the context: the entity select is required; validation "Choose one entity." Election-suppressed section: "Omitted under the <election label> election." RV-13/RV-14 as usual.

**Interactions, keyboard and copy.** "Run disclosure pack" per RV-01; "Export" offers "PDF" and "Excel workbook (XLSX)"; the PDF contains the RV-07 stamp on every page footer ("Run <no> · page <n> of <m>"). The section index links move focus to the section heading.

**Sample world.** J-15.1 (asserted): AVM-US, `ASC606`, Sep 2026 and Q3 2026, source as locked; seven sections; every tie-out Pass. J-15-AC-2: disaggregation total equals the AVM-US Sep 2026 revenue journal total; rollforward closing equals contract balances closing; RPO rollforward closing equals the RPO report total. J-15-AC-4: exempt listing empty because POL-197 to POL-200 are `DO_NOT_APPLY`. J-15.9: `robert` exports the pack as PDF.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Disclosure pack · …" | `SF-08-page` |
| Section index | navigation named "Sections" | `SF-08-disclosure-sections` |
| Section | heading level 2 "<section heading>" | `SF-08-grid-disclosure-<n>` |
| Tie-outs | region named "Tie-outs …" | `SF-08-banner-tie-outs` |

**Light and dark.** DS-CH-02 bridge colours; chips.

**Accessibility.** Sections are `section` elements labelled by their `h2`; the index is `nav aria-label="Sections"`.

### 5.5 SF-08:dashboard Dashboards

| Field | Value |
|---|---|
| Screen id | SF-08:dashboard (SCREENS.md §0.4; §14) |
| Route | `/reports/dashboards/:dashboardCode` (RT-107) with `dashboardCode` ∈ {`revenue`, `close`} (OQ-B-12) and the context parameters; rev 1.82 (BUILD_SPEC RPS-19, first head): `revenue` is built; `close`, like every code this build has no dashboard for, answers X:not-found (SCR-ST-07) until the second head; rev 1.92: and the screen parameter `entities` (`all`; SCREENS.md SCR-URL-01 rev 1.61) |
| Roles and permissions | Read `report.run`; the close dashboard additionally needs `contract.read`; panels whose read permission is missing are not rendered. Rev 1.82: the route opens with `report.run` held for any entity (RT-107). The chart panels are report runs: they render where `report.run` is held for the context entity — a run that names an entity outside the member's scope is refused (04 API-R-41) — or, without an entity, for the entities of the member's `report.run` scope, and where `config.read` gives the calendar. The flags panel renders where `contract.read`, the exception queue's read (04 API-R-44), is held for the context entity, or for any entity without one. A panel whose report the member's catalogue does not hold is not rendered. Where no panel may be read the page shows the access state (the copy of SCREENS.md SCR-PERM-01) naming what the charts lack: viewing configuration, or running reports |
| Purpose | Portfolio views that compose report runs into charts and a close status overview, each figure drilling to its report or cockpit |
| REQ | REQ-RPT-016, 017; REQ-CLS-008, 020; REQ-AI-007; `docs/00-GOAL.md` §2 item 9 (dashboards) |
| Journeys | none (covered by `screens.spec.ts`, §15) |

**Wireframe, 1440 px (revenue dashboard, All entities that keep one calendar and one functional currency; rev 1.82).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Reports > Revenue dashboard                                                                                          |
| Revenue dashboard · All entities · Sep 2026 · ASC 606                                   Currency (Functional) Refresh |
+--------------------------------------------------------------------------+-------------------------------------------+
| Revenue by period · USD · ASC 606                        (Chart | Table) | Contract liability rollforward · USD       |
|  ## ## ## ## ## ## ## ## ## .. .. ..  //                                 |  Opening  +Billings  −Revenue  FX  Closing |
|  Run RPT-000431 · 12 Sep 2026 16:20 UTC                     Open report >|  Run RPT-000432              Open report > |
+--------------------------------------------------------------------------+-------------------------------------------+
| Remaining performance obligations by time band · USD                     | Open anomaly flags (4)                    |
|  Total   ########################////////                                | (Warning) ANOMALY_REVENUE_CHANGE BG-AVM-… |
|  AVM-US  ##################////                                          | ...                        View all >     |
|  Run RPT-000433                                             Open report >|                                           |
+--------------------------------------------------------------------------+-------------------------------------------+
| Revenue by category · USD · Sep 2026                                                                                 |
|  Subscription ###############   Services ########   Products ####   Licences ##                                     |
|  Run RPT-000434                                                                                     Open report >    |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** Panels stack in one column in the same order.

```text
+--------------------------------------------------------------------------------------------------------+
| Revenue dashboard · All entities · Sep 2026 · ASC 606                      Currency (Functional) Refresh |
| Revenue by period · USD · ASC 606 (Chart | Table)                                                      |
| Contract liability rollforward · USD                                                                   |
| Remaining performance obligations by time band · USD                                                   |
| Open anomaly flags (4)                                                                                 |
| Revenue by category · USD · Sep 2026                                                                   |
+--------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1440 px (revenue dashboard, All entities that keep different calendars or functional currencies; rev 1.82).** No report run is made; the flags panel stays.

```text
+----------------------------------------------------------------------------------------------------------------------+
| Reports > Revenue dashboard                                                                                          |
| Revenue dashboard · All entities · Sep 2026 · ASC 606                                                                |
+----------------------------------------------------------------------------------------------------------------------+
| (i) The entities in scope keep different calendars and functional currencies. Select an entity to see its charts.    |
+--------------------------------------------------------------------------+-------------------------------------------+
| Open anomaly flags (0)                                                   |                                           |
|  No open anomaly flags                                                   |                                           |
+--------------------------------------------------------------------------+-------------------------------------------+
```

**Wireframe, 1440 px (close dashboard).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Reports > Close dashboard                                                                                            |
| Close dashboard · Sep 2026 · ASC 606                                                                                 |
+---------+----------------------+-------------------+----------+-------------------+-------------------+--------------+
| Entity  | Period               | Close run         | Blockers | Reconciliations   | Batches           | Days to close|
|         |                      |                   |          | reviewed          | acknowledged      | (last three) |
| AVM-US  | Sep 2026 (Locked)    | CLS-000031 (Succ.)| 0        | 2 of 2            | 2 of 2            | 6 · 5 · 4    |
| AVM-UK  | Sep 2026 (Soft close)| CLS-000033 (Succ.)| 1        | 0 of 2            | 0 of 1            | 7 · 6 · —    |
| AVM-DE  | Sep 2026 (Soft close)| CLS-000032 (Run.) | 2        | 0 of 2            | —                 | 5 · 5 · —    |
| AVM-JP  | Sep 2026 (Period open)| CLS-000034 (Q.)  | 0        | 0 of 2            | —                 | 4 · 4 · —    |
+---------+----------------------+-------------------+----------+-------------------+-------------------+--------------+
```

The close dashboard's figures other than period states are illustrative.

**The context, the view and the entities in scope (rev 1.82; the supervisor's rulings of 2026-10-01 14:53 and 23:35).** No report converts an amount in 1.0: the `functional` and `reporting` views serve the contracts held in their entity's functional currency and refuse any other (D-87 L6-3-Q-20; D-88 L7-2-Q-17). And a run that names its period by key reads each entity at that key on its own calendar. So the page asks its four runs under `currency_view=functional` in every context and states that view as the chip "Functional" beside "Currency"; it has no switch and no "Reporting" chip, which would name a conversion that is not made, and it reads no `currency_view` from the address (SCREENS.md SCR-URL-04). The period and the book are the context pill's — the address, else the member's last choice, else the defaults; the entity is the address's alone. With an entity the four panels are that entity's. Without one the title reads "All entities", the runs name no entity and read the entities of the member's `report.run` scope, and the panels are drawn only where those of them that keep the book share one calendar and one functional currency (`calendar_id`, `functional_currency` of API-S-Entity). That calendar is also the one the context period was chosen on, the calendar of the pill's entity: where the pill's entity keeps another, the period's key is another month on the scope's calendar, and the page reads it as a difference of calendars. Otherwise no report run is made and one information banner stands in the panels' place, by what differs: "The entities in scope keep different calendars. Select an entity to see its charts.", "The entities in scope keep different functional currencies. Select an entity to see its charts." or "The entities in scope keep different calendars and functional currencies. Select an entity to see its charts." The header then shows neither the chip nor "Refresh"; the flags panel, which names no period, stays. The context pill offers no "All entities" on this page — SCREENS.md §1.3 has no row for SF-08, and the option is not built — so "Select an entity" means choosing one in the pill, also the one it already shows.

**The address (rev 1.92; item RPT-VIEW-CONTEXT-DEFAULT-1; §0.5 "The context of a view"; the supervisor's ruling of 2026-10-02 03:43, Q1).** The page follows the report screens' rule. An address that names no entity takes the context pill's: entity, book and period are written into it before a run is asked, and the four panels are that entity's. "Without an entity" in the paragraph above and in the rows of this section is, from this revision, an address that says `entities=all` — and the address of a member without `config.read`, which nothing fills and which draws no chart. Under `entities=all` no entity is written; the period and the book are still the pill's where the address names none, as above. The page's "Open report" links and the link of a bar of "Revenue by period" to SF-04 say `entities=all` while the page shows all entities, so that the report opens on the run the panel shows and not on the pill's entity around it; its other links — the breadcrumb, the flags — name no entity and carry no `entities`, which no other screen reads. In the demo world an address without a context is therefore the dashboard of the first entity in code order, and the banner of the different calendars and currencies stands under `entities=all`.

**Regions and components.** Revenue dashboard: DS-CMP-14 chart panels for DS-CH-01 (RPT-01), DS-CH-02 (RPT-03, contract liability), DS-CH-03 (RPT-06) and plain horizontal bars for RPT-08 by revenue category (DS-VIZ-01 slots); a static list panel of open anomaly flags (§8.4 block rows). Each panel footer shows "Run <no> · <DD MMM YYYY HH:mm UTC>" and "Open report". Close dashboard: DS-CMP-10 DataGrid, one row per entity in scope. Layout follows SCREENS.md §2.3 (panels differ in content and height; never a card grid, DS-AP-02). Rev 1.82 (as built): the bars of RPT-08 are DESIGN_SYSTEM DS-CH-06 "Category bars" (rev 1.12) — the largest category first, more than seven left to the Table view, which ends with the run's own total. The bridge draws the contract liability column of RPT-03's section 1 in the API's order — "Opening balance" and "Closing balance" as totals, a line without movement left out (the report lists all nine) — and, where the run's tie-out `TO_ROLLFORWARD_BALANCES` fails, DS-CH-02's banner with the API's difference in place of the plot. The time bands are asked by entity (`row_dimension=ENTITY`), as the wireframe draws them. A panel whose figures hold several currencies is not drawn: its frame keeps its name and says "These figures cannot be drawn as one chart. Open the report to read them." above the run line. The footer's instant is the run's `finished_at`. "Open report" is named "Open report: <report name>" and leads to SF-08:report in the page's context with `currency_view=functional`, `run=<the panel's run>` and the panel's parameters as `p.<key>`, so that the report shows the run the panel shows. The flags panel is one panel throughout: it does not wait for the charts.

**Data bindings.** Revenue dashboard: one `POST /report-runs` per chart panel with `output_format = JSON` (RV-01), parameters from the context; the page URL records the run ids as `run.<panel>=<uuid>` so that a shared link shows the same runs (SCREENS.md SCR-URL-26); anomaly flags `GET /exceptions?source=ANOMALY&status=OPEN,IN_PROGRESS&entity&limit=8&count=true`. Rev 1.82 (as built): each run sends `currency_view=functional`, `book` and, with an entity in the context, `entity_codes`; `revenue_waterfall` the first and last period of the context period's fiscal year (§5.6 RPT-01's default) and `as_of` its end date; `contract_balance_rollforward` and `disaggregation` the context period as both ends of their range, the latter with `dimension_code=revenue_category` and `include_timing=false`; `rpo` `period_key` and `row_dimension=ENTITY`. The panels read current figures, also of a locked period: RV-04's default to the lock snapshot is the report view's, one "Open report" away. No panel says the toast of §5.2 for a run longer than two seconds: four would say it four times. The runs in the address are those of the context they were made in — a period, an entity or a book that changes, "Refresh" and a panel's "Retry" take the runs they replace out of the address and make new ones, and a context whose panels are not drawn keeps none. The flags read sends `entity` only with an entity in the context. Close dashboard: `GET /periods?period=<key>&book=<book>` for every entity in scope (API-S-Period rows with `state` and `close_run`; a row of the list answers `blockers` null — 04 §16.8 rev 1.199, rev 1.64); `GET /periods/{id}/cockpit` per row for the blocker counts (`period.blockers`, `derived_blockers[]`), days to close and the checklist counts.

**Grid columns: close dashboard.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Entity | `entity.code` | mono | SF-05 |
| Period | `period.name`, `state` | DS-FMT-19 with period chip | SF-05 |
| Close run | `close_run.id` → number, `close_run.status` | mono and chip | SF-05:close-run |
| Blockers | sum of the §1.1 blocker counts, from the row's cockpit read (rev 1.64) | integer | SF-05 |
| Reconciliations reviewed | cockpit counts | "<n> of <m>" | SF-05:reconciliations |
| Batches acknowledged | `period.blockers.batches_unacknowledged` of the row's cockpit read (rev 1.64) with journal run batch counts | "<n> of <m>"; em dash without a run | SF-06 |
| Days to close (last three) | `kpis.days_to_close_last_three` | three integers separated by " · ", "—" when in progress | SF-05 |

**States.** Revenue panels: DS-CMP-14 empty "No revenue scheduled for this range."; flags empty "No open anomaly flags"; close dashboard SCR-ST-03 "No entities in scope". A panel's run failure shows the panel-level SCR-ST-12 banner; other panels still render. Rev 1.82 (as built). A panel before its run and while it computes: DS-CMP-14 loading under the panel's name; a run that is `QUEUED` or `RUNNING` is read again until it ends. A run the API refuses — a problem answer to `POST /report-runs`, so no run exists: a negative banner in the panel, said as SCREENS.md SCR-ST-13 says a refused command — the problem's detail, each finding once, "Reference <request id>." — under the panel's own sentence, "Running <report name> failed. Nothing was committed.", in place of the API's title: the panel has no field, and "Check the highlighted fields" would point at nothing. A refusal that states neither a detail nor a finding says its title under the panel's. "Retry" stands in the banner and asks for that panel's run alone. A run whose job failed: the same title with the problem's title, SCR-ST-12's "Reference <job id prefix>." and "Retry", which makes a new run for that panel alone. A run or its rows that cannot be read: "Could not load the report" or "Could not load the report rows" with the API's sentence, the request and "Retry", which reads again and creates nothing. An empty run keeps its run line under the empty text. The reports' catalogue unread: one banner "Could not load the dashboard" in the panels' place, the flags beside it; the entities, books or periods unread: the same banner for the page. No period to report on: title "No period to report on", description "No entity of this workspace keeps a book with periods." Flags unread: "Could not load the anomaly flags" in the panel, under the heading "Open anomaly flags" without a count.

**Interactions, keyboard and copy.** Chart marks drill to SF-04 (revenue), SF-08:report `contract_balance_rollforward` filtered to the category (bridge), SF-08:report `rpo` filtered to the band and row, SF-08:report `disaggregation` filtered to the category. "Refresh" (ghost button in the header, `ArrowsClockwise`) creates new runs for every panel. Rev 1.82 (as built; the supervisor's ruling of 2026-10-01 14:53 on the item's ninth question): a mark of "Revenue by period" opens SF-04 on the mark's period in the page's context; a bar of the bridge, a band and a category bar open their report with the panel's run, the view and the panel's parameters — no report parameter filters a view to one category, band or row, so none is sent. An anomaly flag opens its item in the exception queue (SF-11:item) in the page's context and is named by its code and the record it is about: the contract, else the record's business key. "View all", shown while the count is above zero, opens the queue on `f.source=is:ANOMALY` and, with an entity in the context, `f.entity=is:<code>`. Each of these links is rendered only where its target is built.

**Sample world.** WLD-T-01 at seed: AVM-US, AVM-UK, AVM-DE, AVM-JP with Sep 2026 open; K-02 RPO 208,339.79 contributes to the AVM-US time bands after J-15. Rev 1.82: without an entity a member whose `report.run` covers the four entities sees the header, the banner "The entities in scope keep different calendars and functional currencies. Select an entity to see its charts." (AVM-JP keeps an April fiscal year, PRD WLD-P-05; the four entities keep USD, GBP, EUR and JPY) and "No open anomaly flags" — nothing raises an anomaly flag in 1.0; with `entity=AVM-US` the page shows the four charts.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Revenue panel | figure named "Revenue by period · …" | `SF-08-chart-dashboard-revenue` |
| Rollforward panel | figure named "Contract liability rollforward · …" | `SF-08-chart-dashboard-rollforward` |
| RPO panel | figure named "Remaining performance obligations by time band · …" | `SF-08-chart-dashboard-rpo` |
| Category panel | figure named "Revenue by category · …" | `SF-08-chart-dashboard-disaggregation` |
| Flags panel | region named "Open anomaly flags (<n>)" | `SF-08-dashboard-flags` |
| Scope banner (rev 1.82) | the banner of the entities' calendars and functional currencies | `SF-08-dashboard-banner-scope` |
| Page (rev 1.82) | heading level 1 "Revenue dashboard · <entity or All entities> · <period> · <book>" | `SF-08-page` |
| Close grid | grid named "Close status by entity" | `SF-08-grid-dashboard-close` |

**Light and dark.** Every chart ramp in both themes (DS-VER-05).

**Accessibility.** Each chart is a `figure` with a summary and Table view; panel footers' run numbers carry `data-volatile`. Rev 1.82: a panel that is loading or empty is a `figure` named by the panel's plain name — "Revenue by period", "Contract liability rollforward", "Remaining performance obligations by time band", "Revenue by category" — and one that is refused, failed, unread or not drawn is a region of that name; each keeps its test id. A drawn chart adds its currency, and its book or period, as the wireframe names it. The flags panel's heading states no count until one is known.

### 5.6 Report specifications

This subsection specifies every 1.0 report code of 04 T-RPT-01 (55 codes) and closes M-DES-06.

**Rules for every specification.**

- **RPT-R-01 Parameters.** Keys are the API-S-ReportRunCreate `parameters` keys (04 §16.9: `entity_codes`, `book`, `period_key`, `from_period_key`, `to_period_key`, `as_of`, `known_at`, `known_at_basis` (`record` | `historical`; stored with every run; rev 1.18, D-98 candidate 112), `period_lock_id`, `contract_external_id`, `mode`, `time_bands`, `row_dimension`, `from_period_lock_id`, `to_period_lock_id`) plus the report-specific keys listed per report, which the definition's `parameters_schema` accepts; any other key returns 422 `validation-failed` (T-RPT-01 rule 1; OQ-B-08 and OQ-B-17 resolved by D-76). The URL carries context keys through SCREENS.md SCR-URL parameters and report-specific keys as `p.<key>`. `known_at` and entity scope are always present (T-RPT-01).
- **RPT-R-02 Columns.** "Field" names the `GET /report-runs/{id}/data` row key; money fields are API-S-Money objects rendered by `<Money>`; XLSX and CSV column headers are the "Header" text with the currency code where shown, except legacy exports, which use legacy names (D-33).
- **RPT-R-03 Currency.** Single-currency results put the ISO code in money headers (`<header> (<ISO>)`); mixed results add a "Currency" column and totals per currency (DS-FMT-12). `currency_view` ∈ `transaction`, `functional`, `reporting` where the spec says "Currency view: yes".
- **RPT-R-04 Totals.** Totals rows and control totals come from the run (`control_totals`), never from client arithmetic (DS-FMT-02).
- **RPT-R-05 Output formats.** "Formats" lists the definition's `output_formats` (subset of XLSX, CSV, PDF, JSON, ZIP); JSON is always included for the on-screen view.
- **RPT-R-06 IPE stamp.** Every run carries the RV-02 stamp and the RV-07 output header; the definition's `ipe_logic` is exportable (REQ-RPT-027). Specs name only departures.
- **RPT-R-07 Kinds.** `kind` literals per T-RPT-01 CHECK: `STANDARD`, `REGISTER`, `DISCLOSURE`, `EXTRACT`, `PACK`, `LEGACY_EXPORT`.
- **RPT-R-08 Tie-out codes.** 04 table 10-T literals, with names as copy (OQ-B-02 resolved by D-76): `TO_WATERFALL_EQ_JE_REVENUE` "Waterfall revenue equals revenue journal total"; `TO_ROLLFORWARD_EQ_GL` "Rollforward closing equals GL balance" (`NOT_APPLICABLE` without a trial balance); `TO_RPO_ROLLFORWARD_EQ_RPO` "RPO rollforward closing equals RPO report total"; `TO_DISAGGREGATION_EQ_JE_REVENUE` "Disaggregation total equals revenue journal total"; `TO_ROLLFORWARD_BALANCES` "Opening plus activity equals closing"; `TO_BALANCES_EQ_ROLLFORWARD` "Contract balances equal rollforward closing"; `TO_JE_POPULATION_EQ_RUNS` "Population totals equal journal run totals"; `TO_AGING_EQ_BALANCES` "Aging totals equal contract balances"; `TO_COST_ROLLFORWARD_BALANCES` "Cost opening plus activity equals closing"; `TO_BBR_EQ_JE_REVENUE` "Revenue equals revenue journal total"; `TO_IC_UNMATCHED_ZERO` "Unmatched intercompany balance is zero"; `TO_MIGRATION_UNEXPLAINED_ZERO` "Unexplained differences are zero"; `TO_BRIDGE_DRIVERS_EQ_DIFFERENCE` "Driver effects equal the book difference" (RPT-33).
- **RPT-R-09 Sections.** A report whose specification names more than one data section returns every row of every section from `GET /report-runs/{id}/data`, and each row carries the field `section`, the integer section number of the specification (1, 2, 3). The viewer renders one grid per section in that order. `section` is a row field, not a query parameter, because 04 API-R-41 defines no data filter. `rpo` reads section 2 from the `exemptions` member of 04 API-S-RpoReportData instead. Rows keep the response order; header sorting of report grids is deferred to later (rev 1.2; B3-SB05).

**Index.**

| RPT | Code | Name | Kind | REQ | Formats | Chart | Section |
|---|---|---|---|---|---|---|---|
| RPT-01 | `revenue_waterfall` | Revenue waterfall | STANDARD | REQ-RPT-004 | XLSX, CSV, PDF, JSON | DS-CH-01 | §5.6.1 |
| RPT-02 | `contract_balances` | Contract balances | STANDARD | REQ-RPT-005; REQ-BIL-010 | XLSX, CSV, PDF, JSON | none | §5.6.1 |
| RPT-03 | `contract_balance_rollforward` | Contract balance rollforward | DISCLOSURE | REQ-RPT-006; REQ-FX-007 | XLSX, CSV, PDF, JSON | DS-CH-02 | §5.6.1 |
| RPT-04 | `revenue_from_opening_liability` | Revenue from the opening contract liability | DISCLOSURE | REQ-RPT-007 | XLSX, CSV, PDF, JSON | none | §5.6.1 |
| RPT-05 | `revenue_from_prior_period_obligations` | Revenue from obligations satisfied in prior periods | DISCLOSURE | REQ-RPT-008 | XLSX, CSV, PDF, JSON | none | §5.6.1 |
| RPT-06 | `rpo` | Remaining performance obligations | DISCLOSURE | REQ-RPT-009 | XLSX, CSV, PDF, JSON | DS-CH-03 | §5.6.1 |
| RPT-07 | `rpo_rollforward` | RPO rollforward | DISCLOSURE | REQ-RPT-010 | XLSX, CSV, PDF, JSON | DS-CH-02 | §5.6.1 |
| RPT-08 | `disaggregation` | Disaggregation of revenue | DISCLOSURE | REQ-RPT-011 | XLSX, CSV, PDF, JSON | bars | §5.6.1 |
| RPT-09 | `contract_history` | Contract history | STANDARD | REQ-RPT-012 | XLSX, CSV, JSON | none | §5.6.2 |
| RPT-10 | `legacy_contract_history_export` | Legacy contract history export | LEGACY_EXPORT | REQ-RPT-012; D-33 | XLSX, CSV, JSON | none | §5.6.2 |
| RPT-11 | `latest_contract_status` | Latest contract status | STANDARD | REQ-RPT-013 | XLSX, CSV, JSON | none | §5.6.2 |
| RPT-12 | `legacy_latest_contract_export` | Legacy latest contract export | LEGACY_EXPORT | REQ-RPT-013; D-33 | XLSX, CSV, JSON | none | §5.6.2 |
| RPT-13 | `legacy_je_summary` | Legacy journal summary | LEGACY_EXPORT | REQ-JE-007, 008 | XLSX, CSV, JSON | none | §5.6.3 |
| RPT-14 | `modification_register` | Modification register | REGISTER | REQ-MOD-014 | XLSX, CSV, PDF, JSON | none | §5.6.2 |
| RPT-15 | `je_population` | Journal entry population | REGISTER | REQ-JE-018 | XLSX, CSV, JSON | none | §5.6.3 |
| RPT-16 | `out_of_period_register` | Out-of-period register | REGISTER | REQ-CLS-006 | XLSX, CSV, PDF, JSON | none | §5.6.3 |
| RPT-17 | `late_entry_report` | Late-entry report | REGISTER | REQ-CLS-007 | XLSX, CSV, PDF, JSON | none | §5.6.3 |
| RPT-18 | `manual_adjustment_register` | Manual adjustment register | REGISTER | REQ-JE-019; REQ-RPT-022 | XLSX, CSV, PDF, JSON | none | §5.6.3 |
| RPT-19 | `ssp_change_log` | SSP change log | REGISTER | REQ-SSP-012 | XLSX, CSV, PDF, JSON | none | §5.6.4 |
| RPT-20 | `ssp_version_diff` | SSP version diff | STANDARD | REQ-SSP-012 | XLSX, CSV, PDF, JSON | none | §5.6.4 |
| RPT-21 | `allocations_by_ssp_version` | Allocations by SSP version | STANDARD | REQ-SSP-012; REQ-SSP-011 | XLSX, CSV, JSON | none | §5.6.4 |
| RPT-22 | `ssp_override_listing` | SSP override listing | REGISTER | REQ-SSP-012; REQ-SSP-006 | XLSX, CSV, PDF, JSON | none | §5.6.4 |
| RPT-23 | `config_change_register` | Configuration change register | REGISTER | REQ-RPT-022 | XLSX, CSV, PDF, JSON | none | §5.6.5 |
| RPT-24 | `user_access_listing` | User access listing | REGISTER | REQ-RPT-022; REQ-CTL-006 | XLSX, CSV, PDF, JSON | none | §5.6.5 |
| RPT-25 | `sod_conflict_report` | SoD conflict report | REGISTER | REQ-PLT-010; REQ-RPT-022 | XLSX, CSV, PDF, JSON | none | §5.6.5 |
| RPT-26 | `approvals_register` | Approvals register | REGISTER | REQ-RPT-022 | XLSX, CSV, PDF, JSON | none | §5.6.5 |
| RPT-27 | `api_client_inventory` | API client inventory | REGISTER | REQ-PLT-033 | XLSX, CSV, PDF, JSON | none | §5.6.5 |
| RPT-28 | `judgement_register` | Judgement register | REGISTER | REQ-RPT-023 | XLSX, CSV, PDF, JSON | none | §5.6.2 |
| RPT-29 | `estimate_change_listing` | Estimate change listing | REGISTER | REQ-RPT-023 | XLSX, CSV, PDF, JSON | none | §5.6.2 |
| RPT-30 | `scope_exclusion_register` | Scope exclusion register | REGISTER | REQ-RPT-023; REQ-CON-016 | XLSX, CSV, PDF, JSON | none | §5.6.2 |
| RPT-31 | `loss_provision_register` | Loss provision register | REGISTER | REQ-LOS-003 | XLSX, CSV, PDF, JSON | none | §5.6.1 |
| RPT-32 | `contract_cost_rollforward` | Contract cost rollforward | DISCLOSURE | REQ-CST-006 | XLSX, CSV, PDF, JSON | DS-CH-02 | §5.6.1 |
| RPT-33 | `book_bridge` | Book-to-book bridge | STANDARD | REQ-BK-006 | XLSX, CSV, PDF, JSON | none | §5.6.6 |
| RPT-34 | `adoption_bridge` | Adoption bridge | STANDARD | REQ-BK-007 | XLSX, CSV, PDF, JSON | none | §5.6.6 |
| RPT-35 | `intercompany_pairs` | Intercompany pairs | STANDARD | REQ-ENT-005 | XLSX, CSV, PDF, JSON | none | §5.6.6 |
| RPT-36 | `balance_aging` | Balance aging | STANDARD | REQ-BIL-013 | XLSX, CSV, PDF, JSON | none | §5.6.1 |
| RPT-37 | `bookings_billings_revenue` | Bookings, billings and revenue | STANDARD | REQ-RPT-020 | XLSX, CSV, PDF, JSON | none | §5.6.6 |
| RPT-38 | `variance_between_closes` | Variance between closes | STANDARD | REQ-RPT-019; REQ-CLS-011 | XLSX, CSV, PDF, JSON | none | §5.6.6 |
| RPT-39 | `forecast_outputs` | Forecast outputs | STANDARD | REQ-FC-003 | XLSX, CSV, JSON | DS-CH-01 | §5.6.7 |
| RPT-40 | `actual_vs_forecast` | Actual vs forecast | STANDARD | REQ-FC-005 | XLSX, CSV, PDF, JSON | none | §5.6.7 |
| RPT-41 | `migration_reconciliation` | Migration reconciliation | STANDARD | REQ-MIG-003 | XLSX, CSV, PDF, JSON | none | §5.6.7 |
| RPT-42 | `parallel_run_comparison` | Parallel-run comparison | STANDARD | REQ-MIG-007 | XLSX, CSV, PDF, JSON | none | §5.6.7 |
| RPT-43 | `audit_log_export` | Audit log export | EXTRACT | REQ-PLT-018; A-19 | CSV, JSON | none | §5.6.5 |
| RPT-44 | `chain_verification_report` | Audit chain verification report | REGISTER | REQ-PLT-020 | CSV, PDF, JSON | none | §5.6.5 |
| RPT-45 | `extract_contracts` | Extract: contracts | EXTRACT | REQ-RPT-028 | CSV, JSON | none | §5.6.8 |
| RPT-46 | `extract_obligations` | Extract: obligations | EXTRACT | REQ-RPT-028 | CSV, JSON | none | §5.6.8 |
| RPT-47 | `extract_contract_versions` | Extract: contract versions | EXTRACT | REQ-RPT-028 | CSV, JSON | none | §5.6.8 |
| RPT-48 | `extract_schedule_lines` | Extract: schedule lines | EXTRACT | REQ-RPT-028 | CSV, JSON | none | §5.6.8 |
| RPT-49 | `extract_subledger_lines` | Extract: subledger lines | EXTRACT | REQ-RPT-028 | CSV, JSON | none | §5.6.8 |
| RPT-50 | `extract_journal_lines` | Extract: journal lines | EXTRACT | REQ-RPT-028 | CSV, JSON | none | §5.6.8 |
| RPT-51 | `extract_balances` | Extract: balances | EXTRACT | REQ-RPT-028 | CSV, JSON | none | §5.6.8 |
| RPT-52 | `extract_events` | Extract: events | EXTRACT | REQ-RPT-028 | CSV, JSON | none | §5.6.8 |
| RPT-53 | `extract_legacy_contract_live` | Extract: legacy Contract_Live dataset | EXTRACT | REQ-RPT-028; D-33 | CSV, JSON | none | §5.6.8 |
| RPT-54 | `period_evidence_pack` | Period evidence pack | PACK | REQ-RPT-014 | ZIP | none | §6 |
| RPT-55 | `contract_sample_pack` | Contract sample pack | PACK | REQ-RPT-015 | ZIP, PDF, XLSX | none | §6 |

#### 5.6.1 Revenue, balances and disclosures

##### RPT-01 `revenue_waterfall` Revenue waterfall

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-004, 017; research 07 A-02 |
| Screens | SF-04 (primary view); SF-08:report; SF-08:dashboard revenue panel |
| Currency view | yes; default `transaction` for one entity, `reporting` for All entities |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes` | "Entity" | context pill (All entities allowed) | context entity | none |
| `book` | "Book" | context pill | primary book | none |
| `from_period_key` | "From" | period select | first period of the context fiscal year | "Start period must be on or before end period." |
| `to_period_key` | "To" | period select | last period of the context fiscal year | as above; more than 36 columns at `MONTH`: "Choose Quarter or Year, or a range of at most 36 months." |
| `as_of`, `known_at`, `period_lock_id` | "Source" | RV-04 | end of the context period; now; the context lock when locked | none |
| `row_dimension` | "Rows" | select "Contract", "Obligation", "Product", "Revenue category" (`CONTRACT`, `OBLIGATION`, `PRODUCT`, `REVENUE_CATEGORY`; SF-04 URL `rows` lowercase) | `CONTRACT` | none |
| `granularity` | "Granularity" | segmented "Month", "Quarter", "Year" (`MONTH`, `QUARTER`, `YEAR`) | `MONTH`; `QUARTER` when the range exceeds 36 months | none |
| `measure` | "Measure" | segmented "Total", "By state" (`TOTAL`, `BY_STATE`) | `TOTAL` | none |
| `contract_external_id` | "Contract (optional)" | combobox | none | "No contract <value> in this workspace." |

Rows: one per `row_dimension` value in scope with any schedule amount, recognized revenue or awaiting-trigger amount in the range; sort by contract external id, then obligation key; `row_key` `contract:<external id>`, `obligation:<external id>:<obligation key>`, `product:<code>`, `category:<revenue category>`, each identifier CV-21-encoded before the join (rev 1.26; supervisor ruling R-40 (a); the D-98 104 rule of RPT-05 and of the frozen long-form keys; `ENGINE_SPEC.md` CV-21: `%` → `%25` first, then `/` `@` `#` `:`): the row key is the key the rows are grouped by, so an identifier holding a delimiter never makes two contracts or obligations one row, and a key split by currency (`:<ISO>`) never equals another row's key. An identifier without a delimiter is written unchanged (`contract:SF-ORD-10002`); one that holds a delimiter changes its key text and nothing else — the legacy obligation `POB #1` of `Contract 1` is `obligation:Contract 1:POB %231`, and the columns `Contract`, `Obligation`, `Product` and `Revenue category` keep showing the identifiers as entered. Grouping: rows by obligation render as a treegrid under their contract (subtotals per contract). **Population (rev 1.69; supervisor rulings R-78 (d) and R-121 (g), and the supervisor's ruling of 2026-10-01 on the lane's finding on the Home).** An obligation is stated under its PERFORMING entity: the rows of a run are the obligations the run's entities perform, "Entity" is the performing entity, recognized is the revenue in that entity's books, and the periods and the as-of period are that entity's. PRODUCT DEFECT repaired: until rev 1.69 the population was read by the contracting entity, so that a run for the contracting entity of a contract another entity performs stated revenue its books do not hold, a run for the performing entity stated none, and the tie-out — which compares with the journal of the run's entities — could pass for neither (measured on WLD-K-04 for April and May 2026: a run for AVM-UK stated 9,647.75 and 9,807.44 where its books hold 4,857.14 and 4,857.15; a run for AVM-US stated nothing where its books hold 4,790.61 and 4,950.29). Four consequences: (1) a run for the contracting entity alone does not show the obligations another entity performs — the whole waterfall of such a contract is a run over both entities; (2) an obligation whose transaction currency is not its performing entity's functional currency is shown in the `transaction` view only — the `functional` and `reporting` views refuse by name, as for every obligation in another currency; (3) the Home, which reads this population (SCREENS §2.5 rev 1.41), refuses for an entity that performs an obligation in another currency than its functional currency, by the rule of every context that holds another currency — before, it stated 0.00 for that revenue; (4) [J] a reader whose roles name the performing entity alone sees, in the rows of a run for that entity, the external id and the customer name of a contract whose own row their scope does not reach — the performing entity's books carry that revenue, and its accountant must be able to name what was performed and for whom; the contract's pages stay closed to them (`GET /contracts/{id}` answers 404) (the supervisor's ruling of 2026-10-01 13:54).

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Contract | `contract_external_id` | mono link | start | SF-03 |
| Customer | `customer_name` | text | start | none |
| Obligation | `obligation_key` (rows `OBLIGATION`) | mono link | start | SF-03:obligation |
| Product | `product_code` (rows `OBLIGATION`, `PRODUCT`) | mono | start | none |
| Revenue category | `revenue_category` (rows `REVENUE_CATEGORY`) | text | start | none |
| Entity | `entity_code` | mono | start | none |
| Currency | `currency` (mixed results only) | mono | start | none |
| "<period label> (<ISO>)" per period (`MONTH` DS-FMT-19 label; `QUARTER` "Q3 2026" or "FY2027 Q2"; `YEAR` "FY2026") | `periods.<period or bucket key>.total`; column key `period:<key>` | money | end | SB-R-07 cell → contributors (schedule lines, SF-04 `layout=lines`) or Explain |
| With `BY_STATE`, per period: "<label> recognized (<ISO>)", "<label> scheduled (<ISO>)" | `periods.<key>.recognized`, `periods.<key>.scheduled` | money | end | as above |
| Awaiting trigger (<ISO>) | `awaiting_trigger` | money | end | SF-04 with `f.state=is:awaiting_trigger` and the row filter |
| Total (<ISO>) | `total` | money | end | Explain contributors |

Totals: one totals row per currency with the same fields; control totals `recognized_total`, `scheduled_total`, `awaiting_trigger_total` per currency. Recognized means revenue posted in the periods up to the as-of period; scheduled means the schedule amounts of the later periods, for an obligation whose remainder at the as-of has a scheduled part; awaiting trigger is the obligation's awaiting-trigger amount at the end of the as-of period and has no period (DS-CH-01) — so each row's recognized + scheduled + awaiting trigger is its allocation at every as-of (rev 1.55; item RPT-ASOF-FIGURES-1; ENGINE_SPEC_B S15-R-01 rev 1.127; supervisor ruling R-116 (c)). Revenue a computation has posted into a period after the as-of is not recognized at the as-of: it shows as scheduled, or inside the awaiting-trigger amount of an obligation that recognises by events. Tie-out: `TO_WATERFALL_EQ_JE_REVENUE` (recognized total of the range equals journal activity of role `REVENUE` for the same entity, book and periods). Chart: DS-CH-01. Empty copy: title "No revenue from <from label> to <to label>"; description "Revenue appears once contracts in this entity and book have schedules in the range." Sample world (asserted): J-15.2 AVM-US as locked Sep 2026, rows `OBLIGATION`: `SF-ORD-10001` O1 Sep 2026 9,764.38; `SF-ORD-10388` O1 4,891.30; `PRJ-CB-2026-01` O1 229,852.94. J-15.7 AVM-JP `QUARTER`: `JP-LIC-0001` `FY2027 Q1` 50,000,000, `FY2027 Q2` 5,000,000. J-16.1 total equals the Home revenue figure.

##### RPT-02 `contract_balances` Contract balances

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-005; REQ-BIL-003, 004, 007, 010; POL-122, POL-124, POL-127; D-12; research 07 A-08 |
| Screens | SF-08:report; SF-08:disclosure-pack section 2 |
| Currency view | yes |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes` | "Entity" | context pill | context entity | none |
| `book` | "Book" | context pill | primary book | none |
| `period_key` | "Period end" | context period | context period (`as_of` = its end date) | none |
| `period_lock_id` | "Source" | RV-04 | lock of a locked period | none |
| `include_zero` | "Include contracts without balances" | checkbox | false | none |
| `contract_external_id` | "Contract (optional)" | combobox | none | as RPT-01 |

Rows: one per member contract × contracting entity from `contract_version_balance` of the latest version known at `known_at` (T-CON-09) of the group the contract is a member of then (rev 1.51; 04 T-CON-04 reading rule: a contract computed in its own group and combined later has one row, from the combined group's version — and, while the combined group awaits its first computation, from the version the contract was last computed in, rev 1.58; 04 T-CON-04 reading rule form (1)); `row_key` `contract:<external id>:<entity code>`. At a period end that is locked at the run's cutoff (rev 1.104; ENGINE_SPEC_B S15-R-20 rev 1.168; 04 §16.9 rev 1.313; item RPT-ROLLFWD-LOCKED-CLOSING-1) the rows and their figures are those of the lock's dataset — what "Source: As locked" shows —, in a current run too: a contract activated after the lock is not a row of that period end, and it is a row of the first period end that is not locked. A change a person sees: before, a current run of a locked period stated such a contract by its schedule. At such an end the Explain drill of the columns below is not offered — the figure is the lock's, and the contract's own page explains its current balances. A lock that holds no dataset, or whose datasets do not agree, refuses the run by name (RV-01); nothing is shown in its place.

| Header | Field | Format | Align | Drill | Visible by default |
|---|---|---|---|---|---|
| Contract | `contract_external_id` | mono link | start | SF-03 | yes |
| Customer | `customer_name` | text | start | none | yes |
| Entity | `entity_code` | mono | start | none | yes |
| Currency | `currency` | mono | start | none | mixed results |
| Contract liability (<ISO>) | `contract_liability` | money | end | Explain `contract_version_balance` `contract_liability` | yes |
| Contract liability, current (<ISO>) | `contract_liability_current` | money | end | none | when POL-124 = `EXPECTED_TIMING_12_MONTHS` |
| Contract liability, noncurrent (<ISO>) | `contract_liability_noncurrent` | money | end | none | as above |
| Contract asset (<ISO>) | `contract_asset` | money | end | Explain `contract_asset` | yes |
| Contract asset, current (<ISO>) | `contract_asset_current` | money | end | none | as above |
| Unbilled receivable (<ISO>) | `unbilled_receivable` | money | end | Explain `unbilled_receivable` | yes |
| Accounts receivable (<ISO>) | `accounts_receivable` | money | end | none | only when POL-004 `billing.posting = ENGINE` |
| Refund liability (<ISO>) | `refund_liability` | money | end | none | yes |
| Return asset (<ISO>) | `return_asset` | money | end | none | column chooser |
| Deposit liability (<ISO>) | `deposit_liability` | money | end | none | column chooser |
| Customer incentive asset (<ISO>) | `customer_incentive_asset` | money | end | none | column chooser |
| Consideration payable (<ISO>) | `consideration_payable` | money | end | none | column chooser |
| Contract cost assets (<ISO>) | `cost_asset_carrying` | money | end | RPT-32 | column chooser |
| Loss provision (<ISO>) | `loss_provision` | money | end | RPT-31 | column chooser |

Totals per currency; control totals per column. Footnote when POL-124 = `NONE`: "Current and noncurrent classification is not applied for <entity code> (balance.current_noncurrent = NONE)." Refund liabilities are never netted (POL-127). Tie-outs: `TO_BALANCES_EQ_ROLLFORWARD`; `TO_ROLLFORWARD_EQ_GL` (Pass or Difference when a reviewed subledger-to-GL reconciliation exists for the period, otherwise Not applicable). Empty copy: title "No contract balances at <DD MMM YYYY>"; description "Contract balances appear once contracts are billed or recognize revenue." Sample world (asserted, J-15.3, 30 Sep 2026): `SF-ORD-10001` contract liability 29,944.11; `SF-ORD-10002` contract liability 28,339.79; `PRJ-CB-2026-01` contract asset and unbilled receivable total 129,852.94 (WLD-X-13).

##### RPT-03 `contract_balance_rollforward` Contract balance rollforward

| Aspect | Specification |
|---|---|
| Kind, formats | `DISCLOSURE`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-006, 007; REQ-FX-007; REQ-MIG-008; 606-10-50-8 to 50-10; research 07 RP-01, A-08 |
| Screens | SF-08:report; SF-08:disclosure-pack section 2; SF-08:dashboard (bridge); SF-05:reconciliation (rollforward kind) |
| Currency view | yes; default `functional` |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book` | context | context pill | context | none |
| `from_period_key` | "From" | period select | context period | "Start period must be on or before end period." |
| `to_period_key` | "To" | period select | context period | as above |
| `balance_role` | "Detail balance" | select "Contract liability", "Contract asset", "Unbilled receivable" (`CONTRACT_LIABILITY`, `CONTRACT_ASSET`, `UNBILLED_RECEIVABLE`) | `CONTRACT_LIABILITY` | none |
| `period_lock_id` | "Source" | RV-04 | lock of `to_period_key` when locked | none |

Section 1 "Rollforward": rows in this order, `row_key` = the line code: `OPENING` "Opening balance"; `BILLINGS` "Billings"; `REVENUE_FROM_OPENING` "Revenue recognized from the opening balance"; `REVENUE_FROM_PERIOD_BILLINGS` "Revenue recognized from billings of the period"; `RECLASSIFICATIONS` "Reclassifications"; `FX_REMEASUREMENT` "FX remeasurement"; `BUSINESS_COMBINATIONS` "Business combinations"; `OTHER` "Other"; `CLOSING` "Closing balance". The two ends (rev 1.104; ENGINE_SPEC_B S15-R-20 rev 1.168; 04 §16.9 rev 1.313; item RPT-ROLLFWD-LOCKED-CLOSING-1): the opening is the closing of the lock of the period before `from_period_key` where that period is locked at the run's cutoff, and the closing is the lock's where `to_period_key` is; an end that is not locked is read from the contract versions. A range of locked months therefore states what those locks state whatever was recorded since, and a contract activated after them is activity of the period its lines are posted in: neither that range nor the period after it shows the contract under "Other". A billing document that posts no line (`billing.posting = ERP`) and was recorded after the lock of the period it is dated in is "Billings" of the first period whose end holds it — the first that is not locked, or was locked after the document was recorded —, as a line posted with an earlier origin is activity of the period it is posted in (PRD J-04: August, locked, shows no billing of the invoice dated 31 August and recorded afterwards; September shows it).

Kind → line (rev 1.40; supervisor ruling R-72 (c); ENGINE_SPEC_B S15-R-03, S15-R-03a). The nine line codes are the line set of 03 REQ-RPT-006. Every flow of the control role is shown under one of them by its kind:

| Kind of the flow (ENGINE_SPEC_B S15-R-03) | Line | Carried by |
|---|---|---|
| `BILLING` less `CREDIT_MEMO` | `BILLINGS` | JET-03 invoice and credit memo lines in `ENGINE` billing mode; under `billing.posting = ERP`, where an invoice or a credit memo posts no line, the period's billing documents at their effective dates (S15-R-03a) |
| Revenue relief, the contracting side of an intercompany pair included, net of `NEGATIVE_REVENUE` — relief of the opening layer | `REVENUE_FROM_OPENING` | `REVENUE_RECOGNITION` and `INTERCOMPANY` lines of the role |
| — relief of a later layer; relief beyond the layers (revenue in excess of billing, on the contract asset column); negative revenue | `REVENUE_FROM_PERIOD_BILLINGS` | as above |
| `DEPOSIT_TRANSFER`, `NONCASH`, `FINANCING`, `REFUND_LIABILITY` and `REFUND_RELEASE`, `CONTRA`, any other movement of the role; the transfers between the two asset captions | `RECLASSIFICATIONS` | `DEPOSIT`, `NONCASH_CONSIDERATION`, `FINANCING_INTEREST`, `REFUND_LIABILITY`, `RECEIVABLE_CONTRA` and every other line of the role |
| Balances a business combination establishes (S15-R-06) | `BUSINESS_COMBINATIONS` | no journal line |
| The unexplained difference only (S15-R-07) | `OTHER` | none: a flow is never shown here |

A credit of any kind settles the unbilled receivable, then the contract asset, and the rest opens a liability layer; a debit consumes the layers first in first out and the rest is an asset — each under the line of its kind. The billing of a period that posted no line is the engine's stored billed amount of the contract (`billed_unconditional_cum`) less the billing lines of the role; the documents enter as recorded, so a difference between them and that amount stays in `OTHER` and fails `TO_ROLLFORWARD_BALANCES`. Supervisor ruling R-72, pending the accountant (candidate AD-48): a credit memo is netted in `BILLINGS`; negative revenue is netted in the revenue lines; the relief of an obligation another entity performs is shown as revenue in the contracting entity's rollforward; a deposit transfer is shown under `RECLASSIFICATIONS`. A line per kind is not shown in 1.0.

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Line code | `line_code` | mono; the line code of the row (`OPENING`, `BILLINGS`, …); export only (rev 1.10; D-98 85) | start | none |
| Line | `line_label` | text | start | none |
| Contract liability (<ISO>) | `contract_liability` | money; activity signed (DS-FMT-28, DS-FMT-31) | end | SB-R-07 contributors (subledger lines by entry kind) |
| Contract asset (<ISO>) | `contract_asset` | as above | end | as above |
| Unbilled receivable (<ISO>) | `unbilled_receivable` | as above | end | as above |

Section 2 "By contract" (balance of `balance_role`): columns "Contract" (mono link SF-03), "Customer", "Currency", "Opening", "Billings", "Revenue from opening", "Revenue from period billings", "Reclassifications", "FX remeasurement", "Business combinations", "Other", "Closing"; `row_key` `contract:<external id>`. Totals: the Opening and Closing rows of section 1 carry DS-ELV-02 rules; section 2 has a totals row per currency. The `OTHER` row shows the chip Warning with caption "Explanation required" when its absolute value exceeds `close.rollforward_other_threshold_ratio` × closing balance (REQ-RPT-006), linking to SF-05:reconciliation of kind `CONTRACT_BALANCE_ROLLFORWARD`. Tie-outs: `TO_ROLLFORWARD_BALANCES`, `TO_BALANCES_EQ_ROLLFORWARD`, `TO_ROLLFORWARD_EQ_GL`. Chart: DS-CH-02 for the `balance_role` column; when `TO_ROLLFORWARD_BALANCES` fails the chart is replaced by the DS-CH-02 banner "This rollforward does not balance. Difference <currency> <amount>." Empty copy: title "No contract balance activity from <from label> to <to label>"; description "Rollforward lines appear once contracts are billed or recognize revenue." Sample world: `SF-ORD-10001` contract liability opening at 31 Aug 2026 39,708.49 and closing at 30 Sep 2026 29,944.11 (asserted, WLD-X-03); the difference is Sep revenue 9,764.38 (WLD-X-02), which POL-126 `FIFO_WITHIN_CONTRACT` presents as revenue from the opening balance (not asserted).

##### RPT-04 `revenue_from_opening_liability` Revenue from the opening contract liability

| Aspect | Specification |
|---|---|
| Kind, formats | `DISCLOSURE`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-007; POL-126; 606-10-50-8(b) |
| Screens | SF-08:report; SF-08:disclosure-pack section 3 |
| Currency view | yes; default `functional` |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book`, `period_lock_id` | context | context pill; RV-04 | context | none |
| `from_period_key`, `to_period_key` | "From", "To" | period selects | context period for both | "Start period must be on or before end period." |

The opening (rev 1.104; ENGINE_SPEC_B S15-R-20 rev 1.168; 04 §16.9 rev 1.313; item RPT-ROLLFWD-LOCKED-CLOSING-1): where the period before `from_period_key` is locked at the run's cutoff, "Opening contract liability" is the lock's, as RPT-03 opens — the two reports are one disclosure and state one opening. A contract that is not in the lock's opening liability, one activated after the lock, has no row: its revenue is not revenue from the opening.

Section 1 "Summary": one row per currency: "Revenue recognized in <range label> that was included in the contract liability at the beginning of the period" with columns "Currency", "Opening contract liability", "Revenue recognized", "From opening contract liability". Section 2 "By contract":

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Contract | `contract_external_id` | mono link | start | SF-03 |
| Customer | `customer_name` | text | start | none |
| Entity | `entity_code` | mono | start | none |
| Currency | `currency` | mono | start | none |
| Opening contract liability | `opening_contract_liability` | money | end | none |
| Revenue recognized | `revenue_recognized` | money | end | RPT-01 for the contract and range |
| From opening contract liability | `revenue_from_opening` | money | end | Explain contributors |

Totals per currency. Footnote: "Measured first-in first-out within each contract (accounting.rollforward.opening_liability_consumption = <option>)." with the resolved POL-126 option. Tie-out: none. Empty copy: title "No revenue from opening contract liabilities in <range label>"; description "Contracts with a contract liability at the start of the range appear here when they recognize revenue." Sample world (not asserted): `SF-ORD-10001` Sep 2026: opening contract liability 39,708.49; revenue recognized 9,764.38; from opening contract liability 9,764.38.

Revenue family (rev 1.40; supervisor ruling R-72 (d), pending the accountant — candidate AD-48). "Revenue recognized" and "From opening contract liability" count the revenue relief of the contract liability by the kinds RPT-03 shows under its two revenue lines: the revenue the entity recognizes in the range, net of negative revenue, and the relief of an obligation another entity of the tenant performs (the contracting side of an intercompany pair, whose revenue is in the performing entity's books). A contract whose liability is relieved only by another entity's performance therefore appears, with that relief in both columns.

##### RPT-05 `revenue_from_prior_period_obligations` Revenue from obligations satisfied in prior periods

| Aspect | Specification |
|---|---|
| Kind, formats | `DISCLOSURE`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-008; REQ-MOD-015; POL-204 (ALG-10 §2.11.3); 606-10-50-12A |
| Screens | SF-08:report; SF-08:disclosure-pack section 4 |
| Currency view | yes |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book`, `period_lock_id` | context | context pill; RV-04 | context | none |
| `from_period_key`, `to_period_key` | "From", "To" | period selects | context period | as RPT-04 |

Rows (rev 1.12; D-98 candidate 85; ENGINE_SPEC_B S15-R-20a): exactly one per contract × obligation with non-zero revenue in the range attributable to performance satisfied before the range — the §15.2.7 row key (entity, contract, obligation) carried as the code columns `entity_code`, `contract_external_id`, `obligation_key`; `row_key` `obligation:<entity code>:<external id>:<key>`; rows sorted by that key. Reading rule (rev 1.16; D-98 candidates 96, 104; the RPT-05 builder): the range's `REVENUE` subledger lines recorded by `known_at` name the traces; where the lines of one combination group and period reference several versions' traces, the node values are read once from the latest version (highest `version_no`) recorded by the run's version cutoff — and where a period's lines reference versions of two groups for one contract (a contract combined, or uncombined, within the period) that contract is read from the one recorded last (rev 1.51; 04 T-CON-04 reading rule) — and every `revenue_prior_period` node of that trace for the period is read — the contract's complete obligation population, every performing entity, before any entity filter. Identity `PRIOR_PERIOD_ROWS_EQ_SUM_NODES` (C4-PP-R1): per (contract, period key) Σ of those obligation nodes = the `revenue_prior_period_sum` node the engine emits under the CONTRACTING entity, `revenue_prior_period_sum:<contract>@<contracting entity>:<period>`, whose inputs are exactly those nodes (ENGINE_SPEC_B S15-R-13; `disc.prior_period_sum.v1`; stage 15 `prior_period._sums`); the sum node is never sought under a performing entity, a missing sum node, a value difference or an input set that differs from the nodes read is refused by name (`RPT05_SUM_NODE_MISMATCH`), and only after the identity holds are the rows restricted to the run's entity scope (a row's `entity_code` is the obligation's performing entity). The control total `prior_period_sum_total` per currency is Σ of the sum nodes read over that complete population, so it equals `revenue_total` when the scope covers every performing entity of the contracts read and differs from it by the signed sum of the out-of-scope rows otherwise; a row whose `revenue` and every per-cause amount are 0 across the range is omitted; `cause` lists the causes whose amount in the range is non-zero. `row_key` carries each of its three components CV-21 percent-encoded (`%`, `/`, `@`, `#`, `:`; ENGINE_SPEC CV-21; D-98 104), so a same-contract witness whose obligation key contains `:` never collides with another row; the code columns carry the raw codes. A run naming `period_lock_id` is refused by name (`RPT05_LOCK_SOURCE_NOT_SUPPORTED`) until the framework's locked-dataset branch lands (D-98 96; F-CLO CLO-8). `cause` is an attribute (the causes present, joined with "; "), never part of the identity; the finer cause grain is kept in the attribute money columns below. The amounts are the stage 08 `revenue_prior_period:<obligation>:<period>` node values of the periods in the range (ENGINE_SPEC_B S15-R-13, S15-R-14), read from the traces the range's `REVENUE` subledger lines reference; a cause is attributed from the boundary events the node cites (`CONTRACT_AMENDED`, `LINE_ATTRIBUTES_CHANGED`, `REGROUPED` → "Modification"; `ESTIMATE_CHANGED` on a reallocating version → "Transaction price change", on a measure-only `EAC` version → "Estimate change"; `CONTRACT_TERMINATED` → "Termination"; `MATERIAL_RIGHT_EXERCISED` → "Material right exercised") and from its late carries ("Late event", S08-R-15).

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Entity | `entity_code` | mono; key column (rev 1.12) | start | none |
| Contract | `contract_external_id` | mono link; key column | start | SF-03 |
| Obligation | `obligation_key` | mono link; key column | start | SF-03:obligation |
| Product | `product_code` | mono; attribute | start | none |
| Satisfied in | `satisfied_period_key` → label | DS-FMT-19; attribute, empty while the obligation is partially satisfied | start | none |
| Cause | `cause` | attribute; the causes present joined with "; " from "Transaction price change", "Estimate change", "Modification", "Termination", "Material right exercised", "Late event" | start | none |
| Currency | `currency` | mono | start | none |
| From price changes | `from_price_changes` | money; signed; attribute (reallocating estimate versions) | end | none |
| From estimate changes | `from_estimate_changes` | money; signed; attribute (measure-only `EAC` versions) | end | none |
| From modifications | `from_modifications` | money; signed; attribute | end | none |
| From late events | `from_late_events` | money; signed; attribute (S08-R-15 carries) | end | none |
| From other boundaries | `from_other` | money; signed; attribute (terminations, material-right exercises, CV-63 zero parts) | end | none |
| Revenue in range | `revenue` | money; signed; Σ of the attribute columns = Σ of the node values in the range | end | Explain contributors (the `revenue_prior_period` nodes) |

Totals per currency; control totals `row_count` and `revenue_total` per currency (the E-64 `PRIOR_PERIOD_POB_REVENUE` snapshot; ENGINE_SPEC_B §15.2.7, S15-R-18). Tie-out: none. Empty copy: title "No revenue from prior-period obligations in <range label>"; description "Price changes, estimate changes and modifications that affect obligations satisfied before the range appear here." Sample world (not asserted): AVM-DE Sep 2026, `NS-SO-DE-5002` O1 (units shipped in Jul 2026), one row, cause "Estimate change", `from_estimate_changes` = `revenue` = EUR (750.00): the re-pricing of 75 July units by estimate version 2 (WLD-X-16). Dataset identity (D-98 candidate 85): a `DATASET_FREEZE` of this report refuses by name when any of `entity_code`, `contract_external_id`, `obligation_key` is missing from the header; the relock diff keys on those three columns and reports the money columns as measures and `cause` / `satisfied_period_key` / `product_code` as attributes.

##### RPT-06 `rpo` Remaining performance obligations

| Aspect | Specification |
|---|---|
| Kind, formats | `DISCLOSURE`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-009; POL-197 to POL-201; 606-10-50-13 to 50-15; research 07 RP-03, A-09; CTL-027 |
| Screens | SF-08:report; SF-08:disclosure-pack section 5; SF-08:dashboard (time bands) |
| Currency view | yes |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book` | context | context pill | context | none |
| `period_key` | "As of" | context period | context period (`as_of` = its end date) | none |
| `period_lock_id` | "Source" | RV-04 | lock when locked | none |
| `time_bands` | "Time bands" | read-only text "<b1>, <b2> months" from `GET /policies/resolve?key=rpo.time_bands&entity=<code>` with the tooltip "Set by the rpo.time_bands policy." | POL-201 resolved value (default `[12, 24]`) | none |
| `row_dimension` | "Rows" | select "Contract", "Entity", "Product family", "Customer segment" (`CONTRACT`, `ENTITY`, `PRODUCT_FAMILY`, `CUSTOMER_SEGMENT`) | `CONTRACT` | none |

Section 1 "Remaining performance obligations": `row_key` `contract:<external id>` (or the dimension value). Each contract is read from one version, the version at the as-of date along the contract's own chain of groups (rev 1.51; 04 T-CON-04 reading rule; ENGINE_SPEC_B S15-R-24a): a contract combined after it was computed in its own group is stated once, by the combined group's version from the date the combination takes effect and by its former group's before. The amount of an obligation is its remainder at the as-of date — the allocation less the revenue recognised to that date —, read at that date (rev 1.55; item RPT-ASOF-FIGURES-1; ENGINE_SPEC_B S15-R-08 rev 1.127): its scheduled part is placed in the bands by the period ends of the later schedule lines, its awaiting-trigger part by the obligation's end date. A contract is in the report from the day it was activated (rev 1.70; item RPT-RPO-ROLLFWD-1; ENGINE_SPEC_B S15-R-24a rev 1.161): its first version counts from that day, not from the last event computed with it, and an obligation that was satisfied only after the as-of date is stated with what remained of it at that date.

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Contract | `contract_external_id` | mono link | start | SF-03 |
| Customer | `customer_name` | text | start | none |
| Entity | `entity_code` | mono | start | none |
| Currency | `currency` | mono | start | none |
| Total (<ISO>) | `total` | money | end | Explain contributors |
| One column per returned band (labels per DS-CH-03: "Within 12 months (<ISO>)", "13 to 24 months (<ISO>)", "After 24 months (<ISO>)") | `bands.<n>` in API order | money | end | SF-04 `layout=lines` for the contract and the band's periods |
| Current (<ISO>) | `current` | money | end | none |
| Noncurrent (<ISO>) | `noncurrent` | money | end | none |

Section 2 "Exempt contracts" (POL-197 to POL-200 `APPLY` only): columns "Contract", "Obligation", "Expedient" ("Original expected duration of one year or less", "Right to invoice", "Sales- or usage-based royalty", "Variable consideration allocated to a wholly unsatisfied obligation"), "Nature of goods or services" (text), "Remaining duration (months)" (integer), "Excluded amount" ("Not disclosed" or the descriptor text). Footnote when section 2 is empty: "No contracts are excluded. <entity code> applies no RPO practical expedient." Totals per currency for section 1. Tie-out: `TO_RPO_ROLLFORWARD_EQ_RPO`. Chart: DS-CH-03 (rows: total plus up to 12 dimension rows). Empty copy: title "No remaining performance obligations at <DD MMM YYYY>"; description "Unsatisfied and partially satisfied obligations appear here with their expected timing." Sample world (asserted, J-15.4, 30 Sep 2026): `SF-ORD-10002` total 208,339.79; within 12 months 166,398.30; 13 to 24 months 41,941.49; after 24 months 0.00 (WLD-X-07); `PRJ-CB-2026-01` total 520,147.06; `SF-ORD-10417` total 105,043.80. J-15-AC-4: section 2 empty.

##### RPT-07 `rpo_rollforward` RPO rollforward

| Aspect | Specification |
|---|---|
| Kind, formats | `DISCLOSURE`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-010; research 07 RP-02; research 04 V9; CTL-030 |
| Screens | SF-08:report; SF-05:reconciliation (kind `RPO_ROLLFORWARD`) |
| Currency view | yes |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book`, `period_lock_id` | context | context pill; RV-04 | context | none |
| `from_period_key`, `to_period_key` | "From", "To" | period selects | context period | as RPT-04 |

Section 1 "Rollforward": rows `OPENING` "Opening RPO"; `NEW_CONTRACTS` "New contracts"; `MODIFICATIONS` "Modifications"; `VC_ESTIMATE_CHANGES` "Variable consideration estimate changes"; `LATE_EVENTS` "Late events" (rev 1.70); `REVENUE` "Revenue recognized"; `CANCELLATIONS` "Cancellations and terminations"; `FX` "FX"; `UNEXPLAINED` "Unexplained difference"; `CLOSING` "Closing RPO". Columns "Line" and one money column per currency ("RPO (<ISO>)"). Section 2 "By contract": "Contract" (link SF-03), "Currency", "Opening", "New contracts", "Modifications", "Variable consideration estimate changes", "Late events", "Revenue recognized", "Cancellations and terminations", "FX", "Unexplained difference", "Closing". The Unexplained difference row shows the chip Difference when non-zero (V9). Opening and closing are the remainders at the day before the range and at its end, and revenue recognized is the revenue between those two dates, each read at its date (rev 1.55; ENGINE_SPEC_B S15-R-08, S15-R-12 rev 1.127). Late events (rev 1.70; item RPT-RPO-ROLLFWD-1; ENGINE_SPEC_B S15-R-12 rev 1.161) is the revenue a version that became effective in the range recognises for the time before the range, which the opening did not state — a progress report of a locked period, posted in the range with that period as its origin; it is 0.00 when nothing of the kind arrived. A contract enters under "New contracts" in the period it was activated in. Known limitation: the line follows the dates of the contract's versions, not the ledger — an event that arrives while the earlier period is still open is posted in that period, and this report shows its revenue as a late event of the period in which it was recorded as effective. Totals: section 1 opening and closing rules; section 2 totals per currency. Tie-outs: `TO_ROLLFORWARD_BALANCES`, `TO_RPO_ROLLFORWARD_EQ_RPO`. Chart: DS-CH-02 per currency. Empty copy: title "No RPO activity from <from label> to <to label>"; description "Contracts with remaining performance obligations appear here as they are booked, modified and recognized." Sample world (not asserted as rows): `SF-ORD-10002` modification effective 16 Sep 2026 raises RPO from 155,178.08 to 215,178.08 (+60,000.00, WLD-X-06); closing at 30 Sep 2026 208,339.79 (asserted as the RPO report total, WLD-X-07; J-15-AC-2). Every row also carries `line_code` (the stable line code; export only, rev 1.10; D-98 85) beside `line_label`.

Combined contracts (rev 1.51; 04 T-CON-04 reading rule; ENGINE_SPEC_B S15-R-24a). A contract's opening is read from the group it was a member of at the day before the range and its closing from its group at the range end. An approved combination effective in the range is shown under "Modifications" of each member — the re-allocation of the transaction price between the members, which sums to zero over them; a contract booked and combined in the same range shows its booked price under "New contracts" and the re-allocation under "Modifications". Nothing of a combination is "Unexplained".

##### RPT-08 `disaggregation` Disaggregation of revenue

| Aspect | Specification |
|---|---|
| Kind, formats | `DISCLOSURE`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-011; REQ-REF-012; POL-191; 606-10-50-5 to 50-7, 55-89 to 55-91; research 07 RP-04, A-10; CTL-028 |
| Screens | SF-08:report; SF-08:disclosure-pack section 1; SF-08:dashboard category panel |
| Currency view | yes; default `functional` |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book`, `period_lock_id` | context | context pill; RV-04 | context | none |
| `from_period_key`, `to_period_key` | "From", "To" | period selects | context period | as RPT-04 |
| `dimension_code` | "Disaggregate by" | select: "Revenue category" (`revenue_category`), "Product family" (`product_family`), each product disaggregation attribute of registry `disclosure.mandatory_disaggregation_attributes`, and each active dimension definition (`department`, `class`, `location`, `customer`, tenant codes) | `revenue_category` | none |
| `include_timing` | "Include timing of transfer" | checkbox | true | none |

Rows: dimension value × timing (when `include_timing`); `row_key` `<dimension value>:<POINT_IN_TIME | OVER_TIME>`. A row is stated only where a `REVENUE` subledger line exists in the range: a dimension value, or a value and a timing, without revenue in the range has no row (rev 1.76; the supervisor's word of 2026-10-01 on lane QA-BE's answer-key work — the builder as built).

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Dimension | `dimension_code` | mono; the run's dimension (`revenue_category`, `product_family`, a custom dimension code, or `timing` for the nonpublic timing rows); export only (rev 1.10; D-98 85) | start | none |
| Dimension value | `dimension_value` | mono; the value code (empty for the timing rows); export only (rev 1.10; D-98 85) | start | none |
| Timing code | `timing_code` | mono (`POINT_IN_TIME`, `OVER_TIME`; empty without timing); export only (rev 1.10; D-98 85) | start | none |
| "<dimension label>" (for example "Revenue category") | `dimension_value_label` | text | start | none |
| Timing of transfer | `timing` | "Point in time", "Over time" | start | none |
| Currency | `currency` | mono (mixed only) | start | none |
| "<period label> (<ISO>)" per period in the range | `periods.<period_key>` | money | end | SB-R-07 contributors (journal lines of role `REVENUE`) |
| Total (<ISO>) | `total` | money | end | none |

Totals per currency. Nonpublic election (POL-191 `ELECT`): only the timing rows render, with RV-12 note "Quantitative disaggregation omitted under the nonpublic disaggregation relief election." Tie-out: `TO_DISAGGREGATION_EQ_JE_REVENUE`. Chart: horizontal bars by dimension value for the total column (DS-VIZ-01 slots in descending total order; at most 7 plus Other). Empty copy: title "No revenue to disaggregate in <range label>"; description "Revenue appears once journal lines of role Revenue exist for the range." Sample world (asserted, J-15-AC-2): the AVM-US Sep 2026 total equals the Sep 2026 revenue journal total.

##### RPT-31 `loss_provision_register` Loss provision register

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-LOS-001 to 003; POL-150 to POL-153; research 07 A-07 |
| Screens | SF-08:report |
| Currency view | yes |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book`, `period_lock_id` | context | context pill; RV-04 | context | none |
| `period_key` | "As of" | context period | context period | none |
| `only_with_provision` | "Only contracts with a provision" | checkbox | false | none |

Rows: one per contract (per obligation when POL-150 = `POB`) tested for losses (POL-151); `row_key` `contract:<external id>` or `obligation:<external id>:<key>`.

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Contract | `contract_external_id` | mono link | start | SF-03 |
| Obligation | `obligation_key` | mono; em dash for contract unit | start | SF-03:obligation |
| Unit | `unit` | "Contract", "Obligation" (E-85) | start | none |
| Basis | `measurement_basis` | "ASC 605-35", "IAS 37" | start | none |
| EAC version | `eac_version_no` | "v<n>" link when one contributor; em dash otherwise | start | SF-03:estimate |
| EAC contributors | `eac_versions` | element code and version for every contributor | start | none |
| Currency | `currency` | mono | start | none |
| Expected consideration | `expected_consideration` | money | end | none |
| Expected total costs | `expected_total_costs` | money | end | none |
| Costs to date | `costs_to_date` | money | end | none |
| Revenue to date | `revenue_to_date` | money | end | none |
| Expected margin | `expected_margin` | money; signed | end | none |
| Provision balance | `provision_balance` | money | end | Explain |
| Movement in period | `provision_movement` | money; signed | end | none |

Totals per currency for the provision columns. Tie-out: none. Empty copy: title "No contracts tested for anticipated losses"; description "Contracts in the loss-test scope of <book label> appear here with their estimate of total costs." Sample world (not asserted): `PRJ-CB-2026-01` (AVM-US, `SCOPED_605_35_ONLY`), EAC v3; expected consideration 1,350,000.00; expected total costs 850,000.00; costs to date 522,500.00; revenue to date 829,852.94; expected margin 500,000.00; provision balance 0.00.

##### RPT-32 `contract_cost_rollforward` Contract cost rollforward

| Aspect | Specification |
|---|---|
| Kind, formats | `DISCLOSURE`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-CST-006; POL-140 to POL-146; 340-40-50-3; ENGINE_SPEC_B S15-R-17, S15-R-20a, S15-R-20b (rev 1.14; D-98 85 / 97) |
| Screens | SF-08:report; SF-08:disclosure-pack section 6 |
| Currency view | yes; default `functional`. `transaction` only when every cost asset of the entity carries one transaction currency, else the run refuses by name (as RPT-07) |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book`, `period_lock_id` | context | context pill; RV-04 | context | none |
| `from_period_key`, `to_period_key` | "From", "To" | period selects | context period | as RPT-04 |

Section 1 "Rollforward by category" (rev 1.14; D-98 85 / 97, ENGINE_SPEC_B S15-R-20b). One row per governed key (`cost_kind`, `line_code`) and entity: `cost_kind` `OBTAIN` "Costs to obtain a contract" and `FULFILL` "Costs to fulfil a contract"; `line_code` in ENGINE_SPEC_B S15-R-17 order — `OPENING` "Opening carrying amount", `ADDITIONS` "Additions", `CLAWBACKS` "Clawbacks", `AMORTIZATION` "Amortization", `ACCELERATION` "Acceleration on termination", `IMPAIRMENT` "Impairment", `IMPAIRMENT_REVERSAL` "Impairment reversal" (book `IFRS15`; a zero row for `ASC606`), `CLOSING` "Closing carrying amount". Every line of a cost kind with a cost asset in scope is a row (zero rows kept, so the frozen dataset has one row per key and the re-lock diff compares like with like); a cost kind without any cost asset in scope has no rows. `row_key` `<cost_kind>:<line_code>` (prefixed `<entity code>:` when the run names several entities). Movements are signed as changes of the carrying amount (additions and impairment reversals positive; clawbacks, amortization, acceleration and impairment negative); `OPENING` + Σ movements = `CLOSING` per cost kind. Display labels are attributes, never key. The dataset and the API rows are the long form; the on-screen grid may render the familiar wide layout (one row per category, one column per line) as a view-level pivot of the dataset rows — grid = pivot of the dataset rows, the dataset is the long form (supervisor ruling D-98 97).

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Category | `category_label` | text | start | none |
| Line | `line_label` | text | start | none |
| Amount (<ISO>) | `amount` | money; signed | end | contributors (cost assets) for the movement lines; none for `OPENING` and `CLOSING` |
| Cost kind | `cost_kind` | mono (`OBTAIN`, `FULFILL`); export and API only (D-98 85) | start | none |
| Line code | `line_code` | mono; export and API only (D-98 85) | start | none |
| Entity | `entity_code` | mono; export and API only; constant within a lock dataset | start | none |

Totals: the category totals row and the report total come from `control_totals` (`opening`, `closing` per currency; RPT-R-04), never from client arithmetic. Tie-out: `TO_COST_ROLLFORWARD_BALANCES` — `PASS` when `OPENING` + Σ movements = `CLOSING` for every cost kind and the `CLOSING` rows equal Σ `cost_asset_version.carrying_amount` at the range end (S15-R-17). Chart: DS-CH-02 per category over the movement lines. Empty copy: title "No capitalized contract costs in <range label>"; description "Incremental costs of obtaining a contract and qualifying fulfilment costs appear here once capitalized." Sample world (asserted amounts): `SF-ORD-10002` commission `COM-2026-0002` 12,000.00 with Sep 2026 amortization 493.15 and cumulative amortization at 31 Aug 2026 3,994.52 (WLD-X-08); `SF-ORD-10417` addition 6,480.00 and Sep 2026 amortization 177.37 (WLD-X-20).

Section 2 "By cost asset" (rev 1.7 wording, DEFERRED at rev 1.14 to a follow-up of RPS-12): "Contract" (link), "Category", "Plan" (`plan_code`), "Capitalized on" (DS-FMT-16), "Amortization months", "Pattern" ("Straight line", "Proportional to related revenue") and the movement lines per cost asset. It is not part of the `COST_ROLLFORWARD` frozen dataset, whose row key is (`cost_kind`, `line_code`) with exactly one row per key (S15-R-20a); a per-asset section needs its own key (`contract_external_id`, cost asset event key) and returns as a separate data section or report once that key is ruled.

##### RPT-36 `balance_aging` Balance aging

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-BIL-013; POL-125; research 07 A-14 |
| Screens | SF-08:report |
| Currency view | yes |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book`, `period_lock_id` | context | context pill; RV-04 | context | none |
| `period_key` | "As of" | context period | context period | none |
| `balance_role` | "Balance" | select "All balances", "Contract asset", "Unbilled receivable", "Contract liability" | "All balances" | none |

Rows: one per contract × balance role with a non-zero balance; `row_key` `contract:<external id>:<role>`. Age of a balance amount = days from the effective date of its layer (T-CON-18 layer movements) to `as_of`.

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Contract | `contract_external_id` | mono link | start | SF-03 |
| Customer | `customer_name` | text | start | none |
| Entity | `entity_code` | mono | start | none |
| Balance | `balance_role` | "Contract asset", "Unbilled receivable", "Contract liability" | start | none |
| Currency | `currency` | mono | start | none |
| 0 to 30 days | `bucket_0_30` | money | end | none |
| 31 to 90 days | `bucket_31_90` | money | end | none |
| 91 to 180 days | `bucket_91_180` | money | end | none |
| 181 to 365 days | `bucket_181_365` | money | end | none |
| Over 365 days | `bucket_over_365` | money | end | none |
| Total | `total` | money | end | RPT-02 for the contract |

Totals per currency and balance. Tie-out: `TO_AGING_EQ_BALANCES`. Empty copy: title "No balances to age at <DD MMM YYYY>"; description "Contract assets, unbilled receivables and contract liabilities appear here by age." Sample world (asserted total): `PRJ-CB-2026-01` contract asset and unbilled receivable total 129,852.94 at 30 Sep 2026; bucket split not asserted.

#### 5.6.2 Contracts, modifications and judgements

##### RPT-09 `contract_history` Contract history

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, JSON |
| REQ and evidence | REQ-RPT-012; REQ-MOD-022; LTM-08 (SCR-LTH-08) |
| Screens | SF-08:report (`/reports/contract_history`) |
| Currency view | no (transaction currency) |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book` | context | context pill | context | none |
| `from_date` | "Effective from" | date | first day of the context fiscal year | "Start date must be on or before end date." |
| `to_date` | "Effective to" | date | end of the context period | as above |
| `contract_external_id` | "Contract (optional)" | combobox | all contracts | "No contract <value> in this workspace." |
| `known_at` | advanced | timestamp | now | none |

Rows: one per obligation version whose `effective_date` is in the inclusive range (04 §17.1 rule 1), ordered by contract external id, version number, `line_sequence`; `row_key` `version:<external id>:<version no>:<obligation key>`. The version number (rev 1.58; 04 T-CON-04 reading rule form (4); supervisor ruling R-117 (a) of 2026-09-30 and the supervisor's ruling of 2026-10-01 on the lane's finding) counts a contract's versions along its chain of combination groups in record order — the versions computed with it, membership after membership — and is the group's own number for a contract that never changed its group: a contract computed in its own group and combined later shows v1 for its own group's version and v2 for the combined group's, where both read v1 under one row key.

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Contract | `contract_external_id` | mono link | start | SF-03:history |
| Version | `version_no` (the number along the contract's chain, rev 1.58) | "v<n>" | start | SF-03:history |
| Effective date | `effective_date` | DS-FMT-16 | start | none |
| Known at | `known_at` | DS-FMT-17 | start | none |
| Cause | `cause_event_types` | E-03 labels joined with ", " (for example "Delivery recorded, Billing recorded") | start | SF-03:history |
| Obligation | `obligation_key` | mono | start | SF-03:obligation |
| Product | `product_code` | mono | start | none |
| Currency | `currency` | mono | start | none |
| Quantity | `quantity` | DS-FMT-11 | end | none |
| Allocated | `allocated_amount` | money | end | Explain `obligation_version` `allocated_amount` |
| Revenue to date | `revenue_cum` | money | end | Explain |
| Billed to date | `billed_cum` | money | end | none |
| Remaining allocation | `remaining_allocation` | money | end | none |
| Scheduled | `scheduled_amount` | money | end | none |
| Awaiting trigger | `awaiting_trigger_amount` | money | end | none |
| Catch-up in version | `catch_up_amount` | money; signed | end | none |
| Status | `satisfaction_status` | "Unsatisfied", "Partially satisfied", "Satisfied", "Cancelled" (E-22 text) | start | none |

Totals: none (history rows are not additive). Control totals: `row_count`, `contract_count`. Tie-out: none. Empty copy: title "No contract versions from <from> to <to>"; description "Every event on a contract creates a version of all its obligations. Versions effective in the range appear here." Sample world: `SF-ORD-10001` from 01 Jan 2026 to 30 Sep 2026 (J-15.8 uses the legacy export of the same range).

##### RPT-10 `legacy_contract_history_export` Legacy contract history export

| Aspect | Specification |
|---|---|
| Kind, formats | `LEGACY_EXPORT`; CSV (primary), XLSX, JSON |
| REQ and evidence | REQ-RPT-012; D-33; 04 §17.1, §17.2; LTM-08 |
| Screens | SF-08:report |
| Currency view | no |

Parameters: as RPT-09 (`from_date`, `to_date`, `contract_external_id`, `entity_codes`, `book` fixed to `ASC606` per 04 §17.1). Rows: 04 §17.1 rules 1 to 6 (one row per obligation version in range, in the order and under the `row_key` of RPT-09 — the version's number along the contract's chain, rev 1.58; "Previous …" columns from the previous version; migrated rows before a cutover come from `migrated_legacy_row.legacy_row` unchanged). Columns: exactly the 71 legacy names LM-CL-01 to LM-CL-71 of 04 §17.2, in that order, as headers and row keys (the legacy names are allow-listed copy, D-33, DS-LINT-19). No index column is written. Formats per 04 §17.1: dates `YYYY-MM-DD 00:00:00`; `Processing Time Log` `YYYY-MM-DD HH:MM:SS.ffffff` UTC; amounts at full stored precision without trailing zeros — for `Previous Remaining Allocation`, `Current Remaining Allocation`, `Current Rev Rec - Cumulative`, `Current Contract Position - POB`, `Current Contract Position - Contract Level` and `Current Reclass to UAR` the EXACT trace-sourced value (04 §17.1 rule 4 rev 1.66; dev-guide DG-PAR-05 `exact(m)` = the row's own contract version's trace node `value + rounding_residue`, exact decimal text; D-98 candidate 89) — a missing trace, an absent node or a hash mismatch refuses the whole run by name, every offending version / column listed — while `Current Rev Rec` stays the posted `revenue_amount` until the engine records an exact activity operand (ENG-T1F, T1F-89-1); account codes as text; legacy sign (`Current Contract Position - Contract Level` = billing − revenue). The on-screen grid renders the same 71 columns; money-like cells are right-aligned text at full precision (no `<Money>` rounding, because the export preserves precision); RPT-12 inherits these formats by reference. Totals: none. Tie-out: none. Empty copy: title "No contract versions from <from> to <to>"; description "The legacy export writes one row per obligation version with the 71 legacy column names." Sample world (asserted, J-15.8): `SF-ORD-10001`, 01 Jan 2026 – 30 Sep 2026, CSV header equals the 71 `Contract_Live` names in legacy order; `Current Contract Position - Contract Level` uses billing − revenue.

##### RPT-11 `latest_contract_status` Latest contract status

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, JSON |
| REQ and evidence | REQ-RPT-013; LTM-09 (SCR-LTH-09) |
| Screens | SF-08:report (`/reports/latest_contract_status`) |
| Currency view | no |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book` | context | context pill | context | none |
| `as_of` | "As of" | date | end of the context period | none |
| `contract_external_id` | "Contract (optional)" | combobox | all | as RPT-09 |

Rows: per contract, the obligation versions of the latest contract version with `effective_date ≤ as_of` among the versions the contract is read from (rev 1.51; 04 T-CON-04 reading rule: a contract combined after it was computed in its own group is listed once), tie-broken by `record_seq` (04 §17.1 rule 1); `row_key` `obligation:<external id>:<key>`. **One date (rev 1.55; item RPT-ASOF-FIGURES-1; supervisor ruling R-116 (c)).** A row states the obligation at `as_of`: allocated, revenue to date, billed to date, remaining allocation, scheduled, awaiting trigger, the status and both balance columns are the figures of the as-of, read at the end of its period as the contract reads serve them (04 API-C-10). Version and Effective date name the version the row is read from; Remaining quantity is that version's. A contract is listed from the day it was activated (rev 1.70; item RPT-RPO-ROLLFWD-1; ENGINE_SPEC_B S15-R-24a rev 1.161): its first version counts from that day, so at an as-of between the activation and the last event computed with it the row shows a version whose Effective date is later than the as-of — the figures are still those of the as-of. Before this revision the money columns were the version's own, the state at its effective date, beside balances of its latest period. The legacy export RPT-12 keeps the version's columns, as the legacy system printed them.

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Contract | `contract_external_id` | mono link | start | SF-03 |
| Obligation | `obligation_key` | mono | start | SF-03:obligation |
| Product | `product_code` | mono | start | none |
| Entity | `entity_code` | mono | start | none |
| Version | `version_no` (the number along the contract's chain, as RPT-09; rev 1.58) | "v<n>" | start | SF-03:history |
| Effective date | `effective_date` | DS-FMT-16 | start | none |
| Currency | `currency` | mono | start | none |
| Allocated | `allocated_amount` | money | end | Explain |
| Revenue to date | `revenue_cum` | money | end | Explain |
| Billed to date | `billed_cum` | money | end | none |
| Remaining quantity | `remaining_quantity` | DS-FMT-11 | end | none |
| Remaining allocation | `remaining_allocation` | money | end | none |
| Scheduled | `scheduled_amount` | money | end | none |
| Awaiting trigger | `awaiting_trigger_amount` | money | end | none |
| Contract liability | `contract_liability` (contract × entity, T-CON-09) | money | end | none |
| Contract asset and unbilled receivable | `contract_asset_and_unbilled` (contract × entity) | money | end | none |
| Status | `satisfaction_status` | E-22 text | start | none |

Totals per currency for the money columns except the balance columns, which total per contract × entity only once (the run supplies them). Tie-out: none. Empty copy: title "No contracts at <DD MMM YYYY>"; description "The latest version of each obligation effective on or before the date appears here." Sample world: WLD-T-23 as of 31 Oct 2023: 17 rows, one per legacy POB row (J-21.6).

##### RPT-12 `legacy_latest_contract_export` Legacy latest contract export

| Aspect | Specification |
|---|---|
| Kind, formats | `LEGACY_EXPORT`; CSV (primary), XLSX, JSON |
| REQ and evidence | REQ-RPT-013; D-33; 04 §17.1, §17.2 |
| Screens | SF-08:report |
| Currency view | no |

Parameters: as RPT-11 (book fixed to `ASC606`). Rows: RPT-11 row rule, without the entry at activation of rev 1.70: a version counts from its own effective date, as the export has always written it (item RPT-RPO-ROLLFWD-1). Columns and formats: the 71 legacy names of 04 §17.2 in order, with the RPT-10 format rules; no index column (REQ-RPT-013). Rev 1.24 (04 §17.1 rule 4a): `Current Rev Rec` (LM-CL-55) writes the exact decimal text of the row's own trace companion, or the literal text `unavailable` on a row whose exact activity the engine names unavailable (an adjusted target) — a text cell in a decimal column, never posted cents; a legacy trace or a missing / redirected / invalid companion refuses the whole run by name. Totals and tie-outs: none. Empty copy: title "No contracts at <DD MMM YYYY>"; description "The legacy export writes the latest version of each obligation with the 71 legacy column names." Sample world (asserted, J-21.6): WLD-T-23 as of 31 Oct 2023: 17 rows; `Current Contract Position - Contract Level` 0 for every row.

##### RPT-14 `modification_register` Modification register

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-MOD-014; research 07 A-06, CM-03 |
| Screens | SF-08:report; guided tour stop 4 opens the register filtered to `FS-03` (J-24.2) |
| Currency view | yes |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book` | context | context pill | context | none |
| `from_date`, `to_date` | "Effective from", "Effective to" | dates | context fiscal year to the end of the context period | "Start date must be on or before end date." |
| `status` | "Status" | multi-select E-26 ("Draft", "Pending approval", "Approved", "Applied", "Rejected", "Void") | "Applied", "Approved" | none |
| `contract_external_id` | "Contract (optional)" | combobox | all | as RPT-09 |

Rows: one per modification × obligation line (`modification.lines[]`); `row_key` `modification:<modification no>:<obligation key>`.

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Modification | `modification_no` | mono link | start | SF-07:detail |
| Reference | `reference` | mono | start | none |
| Contract | `contract_external_id` | mono link | start | SF-03:modifications |
| Kind | `kind` | E-25 label ("Add obligation", "Remove obligation", "Quantity change", "Price change", "Term change", "Upgrade", "Downgrade", "Co-term", "Renewal", "Early renewal", "Cancellation", "Termination", "VC change", "Other") | start | none |
| Effective date | `effective_date` | DS-FMT-16 | start | none |
| Entered | `created_at` | DS-FMT-17 | start | none |
| Added goods distinct | `questionnaire.added_goods_distinct` | "Yes", "No", em dash | start | none |
| Priced at SSP | `questionnaire.priced_at_ssp` | as above | start | none |
| Remaining goods distinct | `questionnaire.remaining_goods_distinct_from_transferred` | as above | start | none |
| Obligation | `obligation_key` | mono | start | SF-03:obligation |
| Proposed treatment | `proposed_treatment` | E-23 label ("Separate contract", "Prospective", "Cumulative catch-up", "Mixed", "Legacy prospective", "Legacy retrospective", "Legacy obligation price change") | start | none |
| Chosen treatment | `chosen_treatment` | E-23 label; chip Warning caption "Override" when different | start | judgement record |
| Status | `status` | chip (SCREENS.md §0.8 E-26) | start | none |
| Preparer | `preparer` | user | start | none |
| Approver | `approvers` | users joined with ", " | start | SF-12:request |
| Approved | `approved_at` | DS-FMT-17 | start | none |
| Currency | `currency` | mono | start | none |
| Transaction price change | `tp_change` | money; signed | end | none |
| Catch-up | `catch_up_amount` | money; signed | end | Explain contributors |

Totals per currency for "Transaction price change" and "Catch-up". Tie-out: none. Empty copy: title "No modifications from <from> to <to>"; description "Approved and applied modifications appear here with their questionnaire, treatment and catch-up." Sample world (not asserted as register rows; figures from WLD): `SF-ORD-10002` effective 16 Sep 2026, treatment "Prospective", catch-up 0.00, transaction price change +60,000.00 (WLD-X-06); `CR-CASTELLAN-2026-09` on `PRJ-CB-2026-01` effective 10 Sep 2026, "Cumulative catch-up", catch-up 91,463.41 (WLD-X-10); `CR-PELLWORTH-2026-07` on `SF-ORD-10001`, "Separate contract" (WLD-K-01b).

**Frozen dataset (rev 1.23; ENGINE_SPEC_B S15-R-20c; D-98 140-A1).** The lock's `MODIFICATION_REGISTER` dataset is this grid's rows in the S15-R-20a shape: key code columns `contract_external_id`, `modification_no`, `obligation_key` first, then `kind`, `effective_date`, `created_at`, `status`, `proposed_treatment`, `chosen_treatment`, `treatment_override`, `judgement_no`, `added_goods_distinct`, `priced_at_ssp`, `remaining_goods_distinct_from_transferred`, `currency`, `tp_change`, `catch_up_amount`, `approval_request_no`, `approved_at`, `impact_preview_sha256`, `applied_event_key`, then the attributes `reference`, `kind_label`, `proposed_treatment_label`, `chosen_treatment_label`, `preparer`, `approvers`; `row_key` as above; the two money columns are the declared measures (typed API-S-Money cells in the row's `currency`; signed); optional cells are empty; the dataset carries no total row — the totals per currency above are its control totals `tp_change_total` and `catch_up_total` beside `row_count` and `modification_count`. Currency view: `transaction` served; `functional` only when every row's currency is its entity's functional currency, else refused by name. The grid's fields are the builder's columns (`erev_api.domain.reports.builders.modification_register.COLUMNS`: a dotted questionnaire field maps to its last segment); the entered timestamp is UTC (DS-FMT-17).

##### RPT-28 `judgement_register` Judgement register

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-023; REQ-POL-008; research 07 A-07 |
| Screens | SF-08:report; SF-05 blocker BLK-06 link |
| Currency view | no |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book` | context | context pill | context | none |
| `from_date`, `to_date` | "Recorded from", "Recorded to" | dates | context fiscal year to today | as RPT-14 |
| `topic` | "Topic" | multi-select E-56 labels | all | none |
| `status` | "Status" | multi-select E-57 ("Draft", "Submitted", "Reviewed", "Rejected", "Superseded") | all | none |

Rows: one per judgement record; `row_key` `judgement:<judgement no>`. Rev 1.95 (head R28-READS; 04 API-C-03 rev 1.275): a run states the records of the contracts of its entities; a record that names no contract of its own — of a product, a registry version or a migration batch — in every run; a record of a combination group when the run's entities hold a contract of the group; and the proposal of a combination (topic "Combination"), whose conclusion names its contracts, when the run's entities hold EVERY contract it names. The run's entities stand for its readers — a run is read by every member whose scope covers them — as for the requests of RPT-23 and RPT-26 (rev 1.76).

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Judgement | `judgement_no` | mono | start | none |
| Topic | `topic` | E-56 label ("Not a contract", "Collectibility", "Contract term", "Combination", "Distinct obligation override", "Series classification", "Principal or agent", "Licence nature", "Warranty type", "Constraint", "Significant financing component", "Modification treatment override", "SSP override", "Repurchase classification", "Estimate or error", "Other") | start | none |
| Subject | `subject_type`, `subject_label` | "<type label> <label>" | start | subject screen |
| Contract | `contract_external_id` | mono link | start | SF-03 |
| Book | `book` | label or "All books" | start | none |
| Conclusion | `conclusion` | text with tooltip | start | none |
| Codification references | `codification_refs` | mono joined with ", " (DS-CPY-06 form) | start | none |
| Preparer | `created_by` | user | start | none |
| Reviewer | `reviewer` | user | start | none |
| Status | `status` | chip E-57 (SCREENS.md §0.8 "Reviewed"; others per DS words "Draft", "Pending approval", "Rejected", "Superseded") | start | none |
| Reviewed | `reviewed_at` | DS-FMT-17 | start | none |
| Supersedes | `supersedes_no` | mono | start | none |

Totals: none; control totals `row_count` and, rev 1.95, `record_count` — the records of the run in all: greater than `row_count` by the proposals of a combination of which the run's entities hold some contracts and not all, which the run does not state. Head line (rev 1.95), shown when `record_count` is greater than `row_count`: "<row count> of <record count> records. <the difference> name contracts of entities outside this run." A run for all the entities of such a record states it. Tie-out: none. Empty copy: title "No judgement records from <from> to <to>"; description "Documented accounting judgements with preparer and reviewer appear here." Sample world: WLD-B-03 `PRINCIPAL_AGENT` on `BG-AVM-0023`, Submitted at seed, Reviewed after J-13.2; J-14.1 `ESTIMATE_VS_ERROR` on `PRJ-CB-2026-01` "Error: the cost existed and was known at period end."

##### RPT-29 `estimate_change_listing` Estimate change listing

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-023; D-20; POL-182; research 07 A-07 |
| Screens | SF-08:report |
| Currency view | yes |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book` | context | context pill | context | none |
| `from_date`, `to_date` | "Effective from", "Effective to" | dates | context fiscal year to the end of the context period | as RPT-14 |
| `estimate_kind` | "Estimate kind" | multi-select E-09 labels | all | none |

Rows: one per approved estimate version effective in the range with its predecessor (rev 1.25: an element's first version is listed with the pair "v1" and empty "before" cells); `row_key` `estimate:<contract external id>:<element code>:<version no>` (rev 1.25: an element code is unique within its contract only, 04 T-CON-12). "P&L effect" is the catch-up of the contract versions that the version's `ESTIMATE_CHANGED` events caused; it is empty when that catch-up is joint with another estimate version or a modification (rev 1.25).

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Element | `element_code` | mono | start | SF-03:estimate |
| Kind | `estimate_kind` | E-09 label ("Variable consideration", "Return rate", "Breakage", "Estimate at completion", "Exercise likelihood", "Implicit price concession", "Renewal expectation", "Royalty accrual", "Expected purchases") | start | none |
| Contract | `contract_external_id` | mono link | start | SF-03:estimates |
| Obligation | `obligation_key` | mono | start | none |
| Versions | `version_pair` | "v<n−1> → v<n>" | start | SF-03:estimate |
| Effective date | `effective_date` | DS-FMT-16 | start | none |
| Method | `method` | E-10 label ("Expected value", "Most likely amount", "Entered amount", "Rate", "Cost build-up") | start | none |
| No-change attestation | `no_change_attestation` | "Yes", "No" | start | none |
| Measure | `measure_label` | "Constrained amount", "Rate", "Expected total" | start | none |
| Currency | `currency` | mono; em dash for rates | start | none |
| Before | `before_value` | money, or DS-FMT-09 percent for rates | end | none |
| After | `after_value` | as above | end | none |
| P&L effect | `pnl_effect` | money; signed | end | Explain contributors (catch-up lines) |
| Preparer | `preparer` | user (rev 1.25) | start | none |
| Approver | `approver` | user | start | SF-12:request |
| Approved | `approved_at` | DS-FMT-17 | start | none |
| Evidence | `attachment_count` | integer | end | none |

Totals per currency for "P&L effect". Tie-out: none. Empty copy: title "No estimate changes from <from> to <to>"; description "Each approved estimate version appears here with its predecessor and effect." Sample world (figures from WLD, not asserted as rows): `REBATE-DR-01` on `NS-SO-DE-5002` v1 → v2, Sep 2026, P&L effect (5,750.00) EUR (WLD-X-16); `PRJ-CB-2026-01` estimate at completion v2 → v3, 820,000.00 → 850,000.00, effect (29,169.29) (WLD-X-12).

##### RPT-30 `scope_exclusion_register` Scope exclusion register

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-023; REQ-CON-016; E-77 |
| Screens | SF-08:report |
| Currency view | yes |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book`, `period_lock_id` | context | context pill; RV-04 | context | none |
| `period_key` | "As of" | context period | context period | none |

Rows: one per obligation version at `as_of` with `scope_flag ≠ IN_SCOPE_606`; `row_key` `obligation:<external id>:<key>`. "Out-of-scope amount" is the allocation of a `LEASE_842` obligation, which the transaction price excludes (POLICIES PT-09); for another flag it is the contract version's out-of-scope amount when the version holds one routed-out line, else empty (rev 1.25).

| Header | Field | Format | Align | Drill |
|---|---|---|---|---|
| Contract | `contract_external_id` | mono link | start | SF-03 |
| Obligation | `obligation_key` | mono | start | SF-03:obligation |
| Product | `product_code` | mono | start | none |
| Scope | `scope_flag` | "Lease (ASC 842)", "Insurance (ASC 944)", "Financial instrument", "Guarantee (ASC 460)", "Contribution (ASC 958-605)", "Nonfinancial asset (ASC 610-20)", "Alternative revenue (ASC 980-605)", "Collaboration (ASC 808)" | start | none |
| Currency | `currency` | mono | start | none |
| Out-of-scope amount | `out_of_scope_amount` | money | end | none |
| Judgement | `judgement_no` | mono link | start | RPT-28 |
| Rationale | `rationale` | text; the rationale of the judgement record on the obligation; export and API only (rev 1.25) | start | none |
| Effective date | `effective_date` | DS-FMT-16 | start | none |

Totals per currency. Tie-out: none. Empty copy: title "No out-of-scope lines at <DD MMM YYYY>"; description "Lines routed out of Topic 606 appear here with their measured amounts. They produce no revenue or journal lines." Sample world: WLD-T-03 `BR-06` and WLD-T-06 `RB-06`, routed out (PRD §2.10).

**RPT-R-09 Grid filters on report views.** Columns marked "Filter" in a specification accept SCREENS.md SCR-URL-10 `f.<field>` parameters. They filter the stored run's rows server-side (`GET /report-runs/{id}/data?<field>=<value>`) without creating a new run; for example SF-07:detail links to `/reports/modification_register?f.reference=is:<reference>`. Filters never change control totals, which describe the full run; the status footer reads "<visible rows> of <row count> rows".

#### 5.6.3 Journals and close registers

##### RPT-13 `legacy_je_summary` Legacy journal summary

| Aspect | Specification |
|---|---|
| Kind, formats | `LEGACY_EXPORT`; XLSX, CSV, JSON |
| REQ and evidence | REQ-JE-007, 008, 009; REQ-BK-004; D-32, D-34; `docs/dev-guide.md` §9.6 kind `journal_entry_totals` |
| Screens | SF-06:entries (primary); `/reports/legacy_je_summary` redirects to SF-06:entries with the same parameters |
| Currency view | no (transaction currency) |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes` | "Entities" | multi-select | context entity | "Choose at least one entity." |
| `book` | none | fixed `ASC606` | `ASC606` | none |
| `from_date` | "From" | date | first day of the context period | "Start date must be on or before end date." |
| `to_date` | "To" | date | last day of the context period | as above |
| `mode` | "Journal view" | segmented "Gross" / "Adjustment" (`GROSS`, `DELTA`; URL `format=gross|adjustment`) | `GROSS` | Adjustment without an enabled Legacy book: "Enable the Legacy book for <entity code> before viewing adjustment journals." |

Section 1 "By account": `row_key` `account:<code>`. Section 2 "By entity": `row_key` `entity:<code>`. Section 3 "Line items": `row_key` `item:<legacy key>:<account>`.

| Section | Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|---|
| By account | Account | `account` | mono | start | none | yes |
| By account | Debit (<ISO>) | `debit` | money | end | SB-R-07 contributors (subledger lines in range) | no |
| By account | Credit (<ISO>) | `credit` | money | end | as above | no |
| By account | Net (<ISO>) | `net` | money; signed (debit − credit) | end | none | no |
| By entity | Entity | `entity_code` | mono | start | none | yes |
| By entity | Debit (<ISO>) | `debit` | money | end | none | no |
| By entity | Credit (<ISO>) | `credit` | money | end | none | no |
| By entity | Balanced | `balanced` | "Yes"; "No" with chip Difference | start | none | no |
| Line items | Key | `key` (legacy key: `legacy_record_key` for revenue lines, contract unique name for balance-sheet lines, T-SL-04 `legacy_key`) | mono | start | none | yes |
| Line items | Account | `account` | mono | start | none | yes |
| Line items | Amount (<ISO>) | `amount` | money; signed (debit positive) | end | Explain contributors | no |

Totals: "By account" totals row `total_debit`, `total_credit`, `net`; control totals `lines`, `total_debit`, `total_credit`, `net`. Rules: the reclassification posted over a range equals the change in the reclassification balance between start and end; the sum of monthly views equals the full-year view per line (REQ-JE-008). Tie-out: none; the "By entity" check carries balancing per entity (CTL-022). Empty copy: title "No journal activity from <from> to <to>"; description "Journal lines appear for contracts with postings in this date range." Sample world (asserted): WLD-X-26 (WLD-T-20) Jan 2023 gross by account: 15002 Dr 58.85; 21001 Dr 295.69; 5001 Cr 187.69; 5002 Cr 118.53; 5003 Cr 48.32; totals 354.54 / 354.54; by entity `Mock Entity 1` 295.69 / 295.69, `Mock Entity 2` 58.85 / 58.85. J-21.5 (WLD-T-23) May 2023: 5001 Dr 5.31, 15002 Dr 5.18, 5003 Cr 10.49; Oct 2023: 21001 Dr 2,990.37, 21002 Dr 2,053.48, 5001 Cr 2,060.35, 5002 Cr 1,108.63, 5003 Cr 1,784.69, 15002 Cr 90.18; total 5,043.85.

##### RPT-15 `je_population` Journal entry population

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; CSV with manifest (primary), XLSX, JSON |
| REQ and evidence | REQ-JE-018; research 07 A-01, JE-04; AS 2401 population testing |
| Screens | SF-08:report; SF-09 auditor requests (A-01) |
| Currency view | no (both transaction and functional columns) |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book` | context | context pill | context | none |
| `from_period_key`, `to_period_key` | "From", "To" | period selects | context period | "Start period must be on or before end period." |
| `period_lock_id` | "Source" | RV-04 | lock when locked | none |
| `include_cancelled` | "Include cancelled runs" | checkbox | false | none |

Rows: one per journal line of the selected runs (non-cancelled unless included); `row_key` `line:<je no>:<line no>`; order `entity`, `period`, `je_no`, `line_no`.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Journal entry | `je_no` | mono | start | SF-06:run-lines filtered | yes |
| Line | `line_no` | integer | end | none | no |
| Entity | `entity_code` | mono | start | none | yes |
| Book | `book` | label | start | none | no |
| Period | `period_key` → label | DS-FMT-19 | start | none | yes |
| Type | `je_type` | "Automated", "Manual", "Reversal" | start | none | yes |
| Description | `description` | text | start | none | no |
| Account | `account_code` | mono | start | none | yes |
| Account role | `account_role` | E-01 label | start | none | yes |
| Dimensions | `dimensions` | codes (mono) | start | none | no |
| Currency | `txn_currency` | mono | start | none | yes |
| Debit (txn) | `debit_txn` | money | end | none | no |
| Credit (txn) | `credit_txn` | money | end | none | no |
| Functional currency | `functional_currency` | mono | start | none | no |
| Debit (functional) | `debit_functional` | money | end | none | no |
| Credit (functional) | `credit_functional` | money | end | none | no |
| Contract | `contract_external_id` | mono link | start | SF-03 | yes |
| Obligation | `obligation_key` | mono | start | SF-03:obligation `pane=schedule` | no |
| Origin period | `origin_period_key` | DS-FMT-19 | start | RPT-16 | no |
| Post-close | `is_post_close` | "Yes" / "No" | start | none | yes |
| Manual | `is_manual` (`je_type = manual`) | "Yes" / "No" | start | RPT-18 | yes |
| Run | `run_no` | mono link | start | SF-06:run | yes |
| Run state | `run_state` | E-34 chip word | start | none | no |
| Batch external id | `batch_external_id` | mono | start | none | no |
| Created by | `created_by` | user: the run's preparer (rev 1.25) | start | none | no |
| Created at | `created_at` | DS-FMT-17 (CSV ISO 8601 UTC) | start | none | no |
| Approved by | `approved_by` | user | start | none | no |
| Approved at | `approved_at` | DS-FMT-17 | start | none | no |
| Posted at | `acknowledged_at` | DS-FMT-17 | start | none | no |
| GL document | `gl_document_id` | mono | start | none | no |
| Source lines | `source_line_count` | integer | end | SF-06:run-lines drawer | no |

Totals: none on screen (population); control totals `row_count`, `entry_count`, `debit_functional_total` and `credit_functional_total` per functional currency. **Frozen dataset (D-98 candidate 85; ENGINE_SPEC_B S15-R-18a, rev 1.24):** the CSV header carries the key code columns first — `entity_code`, `book`, `je_no`, `line_no` — then the code and measure fields above in this order (`period_key`, `je_type`, `account_code`, `account_role`, `dimensions`, `txn_currency`, `debit_txn`, `credit_txn`, `functional_currency`, `debit_functional`, `credit_functional`, `contract_external_id`, `obligation_key`, `origin_period_key`, `is_post_close`, `is_manual`, `run_no`, `run_state`, `batch_external_id`, `gl_document_id`, `source_line_count`, `created_at`, `approved_at`, `acknowledged_at`) and the label attributes last (`description`, `created_by`, `approved_by`); exactly one row per journal line; the control totals also carry `debit_txn_total` and `credit_txn_total` per transaction currency. Tie-out: `TO_JE_POPULATION_EQ_RUNS`. **Source (D-98 candidates 96 and 102; ENGINE_SPEC_B S15-R-18b; rev 1.15):** `run_state`, `approved_at`, `approved_by`, `acknowledged_at` and `gl_document_id` are the values as of the run's `known_at` (a later approval, acknowledgement or cancellation never appears in an earlier report; a run cancelled after the cutoff stays in the population); the state is the latest transition at or before the cutoff across every retry cycle, from the run's full audit transition history read regardless of its current state (D-98 102a) — both audit shapes (run and batch roll-up), ordered by occurrence time then the audit chain sequence, never the state's spelling (D-98 102c) — a `failed` transition, which has no stored timestamp, exists only through its audit event, and a failed run with neither is refused by name (`JOURNAL_RUN_STATE_UNKNOWN_AS_OF`); an as-locked run reads the lock dataset in the framework (RV-04 rev 1.17, CLO-8) and the builder refuses a `period_lock_id` by name as a guard against a direct call; under the close freeze the population and its state are read as of the freeze instant, so the close's own journal runs are in the frozen dataset (no close-run parameter). **Preparer (rev 1.25; BUILD_SPEC RPS-8):** `created_by` names the run's preparer — the principal that requested the run's calculation (`POST /journal-runs`; 04 T-PLT-27 `job.created_by` of the run's job, the runner BR-JE-01 bars from approving the run) — because the calculation job writes every entry as the system principal; an entry of a run that no principal requested shows the system. Empty copy: title "No journal entries from <from label> to <to label>"; description "Journal lines of approved, exported and acknowledged runs appear here with preparer, approver and UTC timestamps." Sample world (asserted): J-17.3 AVM-US Sep 2026: manifest row count and totals equal the journal runs of Sep 2026; lines of the J-14 post-reopen run carry "Post-close Yes" (J-14-AC-4).

##### RPT-16 `out_of_period_register` Out-of-period register

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-CLS-004, 006; D-19; POL-180; research 07 PC-04, A-11; CTL-017 |
| Screens | SF-08:report |
| Currency view | yes |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book` | context | context pill | context | none |
| `from_period_key`, `to_period_key` | "Posting period from", "Posting period to" | period selects | context period | as RPT-15 |
| `origin_period_key` | "Origin period (optional)" | period select | none | none |
| `period_lock_id` | "Source" | RV-04 | lock when locked | none |

Rows: one per attributed event set whose effect posted in a period different from the period of its effective date (subledger lines with `origin_period_id`, each attributed to its `contract_event_id` or to its T-SL-12 event set and aggregated per (origin period, posting period, attribution key); ENGINE_SPEC_B S15-R-18b, rev 1.15); `row_key` `<origin period key>:<posting period key>:<event key>` (rev 1.46; item RPT-OOP-ROWKEY-1; ENGINE_SPEC_B S15-R-18a rev 1.110) — the row key is the whole key of the aggregation, the period keys CV-21-encoded as every other component: one event set whose late lines belong to several origin periods is several rows, one per origin period, each with its own `row_key` — where the event key, the `event_key` column, is `event:<external id>:<stream version>` with the external id CV-21 percent-encoded (`%` first, then `/` `@` `#` `:`, and `|` → `%7C`; ENGINE_SPEC_B §15.2.7, D-98 candidate 104) — for a set of several events the encoded keys joined with `|` in ENG-06 order, so an id containing a delimiter never merges two sets, and ending with the encoded lineage scope (`…:SUBJECT` / `…:GROUP`; D-98 102c) so one event set's Subject and Group populations are two rows with distinct `row_key`s; a line of a trigger-only recomputation (no first-included event of its subject) carries the group's first-included events instead (`lineage_scope` "Group"; D-98 102b) and, only when the group's set is also empty, is attributed to its computation's trigger on persisted proof — the computation's stored lineage is empty, its trigger is non-event (`POLICY_RERUN`, `FX_REPUBLISH`, `RESTATE`; D-98 102a) and, under `FX_REPUBLISH`, the line's transaction amount is nil (rev 1.106; ENGINE_SPEC_B S15-R-18b rev 1.166: a republished rate moves the functional amount alone, so a line that moves a transaction amount under that trigger is missing lineage like any other) — event key `trigger:<trigger code>:<computation id>`; an empty set without that proof refuses ("Attribution" column `attribution_kind` "Trigger"; D-98 102 Q1). A line with neither refuses the run by name (`OUT_OF_PERIOD_ATTRIBUTION_MISSING`) rather than vanish.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Event key | `event_key` | mono; `event:<external id>:<stream version>` — the row key, distinct for events sharing contract, type and date; export only (rev 1.10; D-98 85) | start | none | no |
| Contract | `contract_external_id` | mono link | start | SF-03:history | yes |
| Event | `event_type` | E-03 label ("Billing recorded", "Contract voided", …); a Trigger row shows the E-87 trigger label ("Policy rerun", …) | start | SF-03:history | yes |
| Attribution | `attribution_kind` | "Event set" / "Trigger" (rev 1.15; D-98 102) | start | none | yes |
| Lineage | `lineage_scope` | "Subject" / "Group" (D-98 102b: the group's first-included events when the subject's own were empty); blank on a Trigger row | start | none | yes |
| Effective date | `effective_date` | DS-FMT-16 | start | none | no |
| Recorded | `recorded_at` | DS-FMT-17 | start | none | no |
| Origin period | `origin_period_key` | DS-FMT-19 | start | none | yes |
| Posting period | `posting_period_key` | DS-FMT-19 | start | SF-05 | yes |
| Reason | `reason_code` | mono (for example `LATE_EVENT`) | start | none | yes |
| Origin | `origin` | "API", "UI", "Import", "Adapter", "System", "Migration" | start | none | no |
| Currency | `currency` | mono | start | none | no |
| Revenue effect | `revenue_effect` | money; signed | end | Explain contributors | no |
| Balance effect | `balance_effect` | money; signed (contract liability decreases in parentheses) | end | none | no |
| Recorded by | `recorded_by` | user or API client name; for an event an import commit wrote, the user who uploaded the import (rev 1.31) | start | none | no |
| Approval | `approval_request_no` | mono link; for an event an import commit wrote, the approval request of its upload (rev 1.31) | start | SF-12:request | no |

Imported events (rev 1.31; supervisor ruling R-63 (c); PRD J-04.5; 04 T-RPT-01 rule 4). An import commit appends its events as the system principal, and the control over them is the approval of the upload. An event written that way is therefore shown with the user who uploaded the import under "Recorded by" and the upload's approval request under "Approval"; an event with no upload, and an event a person or an API client recorded, keeps its own recorder and approval. A row of several events states a recorder only when every member agrees, as before.

Totals per currency for "Revenue effect" and "Balance effect". **Frozen dataset (D-98 candidate 85; ENGINE_SPEC_B S15-R-18a, rev 1.24):** the CSV header carries the key code columns first — `origin_period_key`, `posting_period_key`, `event_key` (`event:<external id>:<stream version>`, carried from the source `contract_event`, its components CV-21 percent-encoded before joining (D-98 104); never a proxy tuple of contract, type and date, which distinct events can share; a Trigger row `trigger:<trigger code>:<computation id>`) — then `attribution_kind` (`EVENT_SET` or `TRIGGER`; rev 1.15), `lineage_scope` (`SUBJECT` or `GROUP`, null on a Trigger row; D-98 102b), `contract_external_id`, `event_type`, `effective_date`, `recorded_at`, `reason_code`, `origin`, `currency`, `revenue_effect`, `balance_effect`, `approval_request_no`, and the label attributes last (`event_type_label`, `recorded_by`); exactly one row per attribution (S15-R-18b, rev 1.15: a singleton set is the event row; several events are one row whose `event_key` joins the keys with `|`; a trigger-only delta is a Trigger row; the file's `row_key` is the three key columns in their single-string form, rev 1.46); control totals `row_count`, `line_count` and per currency `revenue_effect_total`, `balance_effect_total`. Tie-out: none. **Source (D-98 candidate 96; rev 1.15):** the register reads lines recorded by the run's `known_at`; an as-locked run reads the lock dataset in the framework (RV-04 rev 1.17, CLO-8); the builder refuses a `period_lock_id` by name (`parameters.period_lock_id`) as a guard against a direct call. Empty copy: title "No out-of-period postings in <range label>"; description "Events effective in a closed period post to the first open period with their origin period, and appear here." Sample world (asserted): WLD-X-18 `NS-SO-DE-5003`, "Billing recorded" (INV-DE-4390) effective 31 Aug 2026, origin Aug 2026, posting Sep 2026, revenue effect 0.00; J-26-AC-2 `BG-AVM-0030` "Contract voided" reversals with origin periods Jul 2026 and Aug 2026 and posting period Sep 2026.

##### RPT-17 `late_entry_report` Late-entry report

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-CLS-007; registry `close.late_entry_window_days`; research 07 PC-03, A-11 |
| Screens | SF-08:report |
| Currency view | no |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book` | context | context pill | context | none |
| `period_key` | "Period" | context period | context period | none |
| `window_days` | "Days around period end" | integer input 0 to 31 | registry `close.late_entry_window_days` (default 5) | "Enter a number of days from 0 to 31." |

Section 1 "Entered after lock": events recorded after the period's first lock with an effective date in the period. Section 2 "Near period end": events with an effective date within `window_days` of the period end. `row_key` `event:<external id>:<stream version>`.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Section | `section` | integer: 1 "Entered after lock", 2 "Near period end"; the section heading on screen (rev 1.25) | end | none | no |
| Entity | `entity_code` | mono; export and API only (rev 1.25) | start | none | no |
| Event key | `event_key` | mono; the row key, encoded as RPT-16's; export and API only (rev 1.25) | start | none | no |
| Contract | `contract_external_id` | mono link | start | SF-03:history | yes |
| Event | `event_type` | E-03 label | start | SF-03:history | yes |
| Effective date | `effective_date` | DS-FMT-16 | start | none | no |
| Recorded | `recorded_at` | DS-FMT-17 with seconds | start | none | no |
| Days from period end | `days_from_period_end` | integer; signed with "+" after the period end | end | none | no |
| Lock recorded (section 1) | `lock_recorded_at` | DS-FMT-17 | start | SF-05:history | no |
| Origin | `origin` | as RPT-16 | start | none | yes |
| Recorded by | `recorded_by` | user or API client; for an event an import commit wrote, the user who uploaded the import (rev 1.31) | start | none | no |
| Approval | `approval_request_no` | mono link; for an event an import commit wrote, the approval request of its upload (rev 1.31) | start | SF-12:request | no |
| Event label | `event_type_label` | the E-03 label of `event_type`, the text the "Event" column shows; export and API only (rev 1.25) | start | none | no |

Totals: none; control totals `section_1_count`, `section_2_count`. Tie-out: none. Empty copy per section: "No events entered after the lock of <period label>." / "No events within <n> days of <period end date>." Sample world (not asserted): AVM-US Sep 2026 section 2 lists `PRJ-CB-2026-01` "Cost incurred" effective 25 Sep 2026 (days from period end −5); after J-14 section 1 lists `PRJ-CB-2026-01` "Cost incurred" effective 29 Sep 2026, recorded after the first lock.

Imported events (rev 1.31; supervisor ruling R-63 (c); PRD J-04.5; 04 T-RPT-01 rule 4). An import commit appends its events as the system principal, and the control over them is the approval of the upload. An event written that way is therefore shown with the user who uploaded the import under "Recorded by" and the upload's approval request under "Approval"; an event with no upload, and an event a person or an API client recorded, keeps its own recorder and approval.

Dataset and rules (rev 1.25; BUILD_SPEC RPS-8). The report lists the contract events (04 T-CON-05) of the contracts whose contracting entity is an entity of the run, recorded by the run's cutoff, against the period `period_key` of each entity's calendar (the period that holds the run's as-of date when omitted) and the run's book. Section 1 lists an event whose effective date lies in the period and whose `recorded_at` is after `lock_recorded_at`, the `created_at` of the earliest `LOCK` record (04 T-CLS-04) of the entity, book and period by the cutoff; an entity whose period has no lock by then has no section 1 row. Section 2 lists an event whose effective date lies from `window_days` days before the period end to `window_days` days after it, both inclusive, so `window_days` 0 lists the events effective on the period end date. `days_from_period_end` is the effective date less the period end date in days: negative before the period end, 0 on it. One dataset holds both sections; a row fills `lock_recorded_at` in section 1 only. An event that meets both rules has a row in each section under the same `row_key`, so `section` and `row_key` together identify a row; the external id in `row_key` and `event_key` is CV-21 percent-encoded as in RPT-16, and the same event carries the same key in both reports without RPT-16's lineage scope. Rows are ordered by section, entity code, effective date, `recorded_at`, contract and stream version. `event_type` is the E-03 code in exports and the API, with its label in `event_type_label`; `origin`, `recorded_by` and `approval_request_no` are read as RPT-16 reads them. `window_days` omitted at the run's creation is stored with the run as the registry value `close.late_entry_window_days` in force at the run's `known_at` (D-87 L6-3-Q-29), and the control totals state the `window_days` applied; the API answers a value that is not an integer from 0 to 31 with the validation copy above. T-CON-05 and T-CLS-04 are append-only, so a run with an explicit `known_at` states the register as it stood at that instant and never refuses.

##### RPT-18 `manual_adjustment_register` Manual adjustment register

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-JE-019; REQ-RPT-022; research 07 MA-01, MA-02, A-12 |
| Screens | SF-08:report; SF-05 blocker BLK-15 link |
| Currency view | yes; default `functional` |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book` | context | context pill | context | none |
| `from_period_key`, `to_period_key` | "From", "To" | period selects | context period | as RPT-15 |
| `status` | "Status" | multi-select E-94 | all | none |
| `kind` | "Kind" | multi-select E-93 | all | none |

Rows: one per manual adjustment; `row_key` `adjustment:<adjustment no>`.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Adjustment | `adjustment_no` | mono | start | none | yes |
| Kind | `kind` | "Schedule override", "Manual release", "Manual defer", "Manual journal", "Account reclassification" (E-93) | start | none | yes |
| Contract | `contract_external_id` | mono link | start | SF-03 | yes |
| Obligation | `obligation_key` | mono | start | SF-03:obligation | no |
| Entity | `entity_code` | mono | start | none | no |
| Period | `period_key` → label | DS-FMT-19 | start | SF-05 | yes |
| Effective date | `effective_date` | DS-FMT-16 | start | none | no |
| Status | `status` | E-94 chip ("Draft", "Pending approval", "Approved", "Posted", "Rejected", "Void") | start | none | yes |
| Reason | `reason_code` | mono | start | none | no |
| Memo | `memo` | text | start | none | no |
| Currency | `currency` | mono | start | none | no |
| Amount | `amount_functional_abs` | money | end | Explain contributors | no |
| Preparer | `preparer` | user | start | none | no |
| Approvers | `approvers` | users joined with ", " | start | SF-12:request | no |
| Preparer differs from approver | `preparer_differs` | "Yes" / "No" | start | none | no |
| Approved | `approved_at` | DS-FMT-17 | start | none | no |
| Attachments | `attachment_count` | integer | end | none | no |
| Deferred past lock | `is_deferred_past_lock` | "Yes" / "No" | start | none | no |
| Decision comment | `decision_comment` | text | start | none | no |

Totals per currency for "Amount" of posted adjustments. Tie-out: none. Empty copy: title "No manual adjustments in <range label>"; description "Schedule overrides, manual releases and deferrals, and manual journals appear here with their approvals." Sample world: WLD-B-02 `BG-AVM-0022` "Schedule override", USD 2,400.00, preparer Maya Chen, no attachment; after J-13.2 status Rejected, approver Priya Raman, decision comment "Attach the customer acceptance before resubmitting."

#### 5.6.4 SSP reports

##### RPT-19 `ssp_change_log` SSP change log

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-SSP-001, 007, 008, 012; research 07 SSP-03, A-05; CTL-011 |
| Screens | SF-08:report |
| Currency view | no |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `from_date`, `to_date` | "Changed from", "Changed to" | dates | first day of the context fiscal year; today | "Start date must be on or before end date." |
| `ssp_book_code` | "SSP book (optional)" | select | all books | none |

Rows: one per SSP book version with a lifecycle transition in the range; `row_key` `ssp:<book code>:<version no>`.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| SSP book | `ssp_book_code` | mono | start | SF-13:ssp-books | yes |
| Version | `version_label` (`legacy_version_label` or "v<n>") | mono | start | SF-13:ssp-book-version | yes |
| Status | `status` | SCREENS.md §0.8 E-12 chip | start | none | yes |
| Effective from | `effective_from_date` | DS-FMT-16 | start | none | no |
| Effective to | `effective_to_date` | DS-FMT-16; em dash when open | start | none | no |
| Methodology | `methodology_label` | text | start | none | no |
| Methodology change | `is_methodology_change` | "Yes" / "No" | start | none | no |
| Entries | `entry_count` | integer | end | none | no |
| Added | `diff_summary.added` | integer | end | RPT-20 | no |
| Removed | `diff_summary.removed` | integer | end | RPT-20 | no |
| Changed | `diff_summary.changed` | integer | end | RPT-20 | no |
| Preparer | `preparer` | user | start | none | no |
| Approvers | `approvers` | users joined with ", " | start | SF-12:request | no |
| Approved | `approved_at` | DS-FMT-17 | start | none | no |
| Superseded by | `superseded_by_label` | mono | start | none | no |
| Study | `study_file_name` | link (download) | start | none | no |

Totals: none; control total `row_count`. Tie-out: none. Empty copy: title "No SSP changes from <from> to <to>"; description "SSP book versions appear here when they are created, submitted, approved or superseded." Sample world: `US-LIST 2026-H1` effective 01 Jan 2026, prepared by Maya Chen, approved by Priya Raman; `US-LIST 2026-H2` from J-02; `UK-LIST 2026`, `DE-LIST 2026` effective 01 Jan 2026; `JP-LIST FY2027` effective 01 Apr 2026 (PRD §2.6).

##### RPT-20 `ssp_version_diff` SSP version diff

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-SSP-007, 012; research 07 A-05 |
| Screens | SF-08:report; SF-13:ssp-book-version links here |
| Currency view | no |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `ssp_book_version_id` | "Version" | select (versions of all books) | none (required) | "Choose a version." |
| `against_version_id` | "Compared with" | select (versions of the same book) | the prior approved version | "Choose a version of the same SSP book." |
| `only_changes` | "Only changed entries" | checkbox | true | none |

Rows: one per entry key (product, stratification, region, channel, segment, deal-size band, term band, currency) present in either version; `row_key` `entry:<product code>:<stratification>:<dimension keys>:<currency>`.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Change | `change` | DS-CMP-16 grid-diff chips "Added", "Removed", "Changed", "Unchanged" with markers `+`, `−`, `~` | start | none | yes |
| Product | `product_code` | mono | start | SF-15:product | yes |
| Stratification | `stratification` | text | start | none | no |
| Region, Channel, Segment | `region`, `channel`, `segment` | text | start | none | no |
| Currency | `currency` | mono | start | none | no |
| Method | `method_before`, `method_after` | E-47 labels ("Observable", "Adjusted market", "Cost plus margin", "Residual", "Legacy range"); changed cells use the DS-CMP-16 inline variant "Observable → Cost plus margin" | start | none | no |
| Low (<ISO>) | `low_before`, `low_after` | DS-FMT-13 unit rate; changed cells show the after value with the tooltip "Was <before>" | end | none | no |
| Mid (<ISO>) | `mid_before`, `mid_after` | as above | end | none | no |
| High (<ISO>) | `high_before`, `high_after` | as above | end | none | no |
| Point (<ISO>) | `point_before`, `point_after` | as above | end | none | no |
| Mid change | `mid_change_ratio` | DS-FMT-09 percent with sign (DS-FMT-31); em dash for added and removed rows | end | none | no |

Totals: none; control totals `added`, `removed`, `changed`. Tie-out: none. Empty copy with `only_changes`: title "No differences between <version> and <compared version>"; description "Every entry has the same method and values in both versions." Sample world (asserted values from PRD §2.6): `AVM-PLAT-100`, `US-LIST 2026-H1` → `US-LIST 2026-H2`: low 85,000.00 → 95,200.00; mid 100,000.00 → 112,000.00; high 115,000.00 → 128,800.00; mid change +12.0%.

##### RPT-21 `allocations_by_ssp_version` Allocations by SSP version

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, JSON |
| REQ and evidence | REQ-SSP-011, 012, 014; D-18; research 07 A-05 |
| Screens | SF-08:report |
| Currency view | no (transaction currency) |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book` | context | context pill | context | none |
| `ssp_book_version_id` | "SSP book version (optional)" | select | all versions | none |
| `from_date`, `to_date` | "Allocated from", "Allocated to" (inception or modification date) | dates | first day of the context fiscal year; end of the context period | as RPT-19 |

Rows: one per obligation allocation event (inception, 25-13(a) reallocation) in range; `row_key` `allocation:<external id>:<obligation key>:<version no>`. Rev 1.90 (item S-1 of the lane's sweep under RPT-FORMER-GROUP-READERS-1): `<version no>` is the number, along its contract's chain, of the version the row is read from — the number RPT-09 gives that version (rev 1.58). `version_no` counts the versions of one combination group, so for a contract combined after it had been computed in its own group the combined group's first version is the contract's 2, not 1; a contract that never changed its group keeps its numbers. Asserted in the world of a combination: `allocation:SF-ORD-10417:O1:2` (117,000.00) and `allocation:SF-ORD-10418:O1:2` (39,000.00), the versions RPT-09 states as `version:SF-ORD-10417:2:O1` and `version:SF-ORD-10418:2:O1`.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Contract | `contract_external_id` | mono link | start | SF-03 | yes |
| Obligation | `obligation_key` | mono | start | SF-03:obligation `pane=ssp` | no |
| Product | `product_code` | mono | start | none | yes |
| Allocated on | `allocation_date` | DS-FMT-16 | start | none | no |
| Cause | `cause` | "Inception", "Modification" | start | none | yes |
| SSP book version | `ssp_version_label` | mono | start | SF-13:ssp-book-version | yes |
| SSP entry | `ssp_entry_id` | mono; the T-REF-30 value row of the SSP book version the allocation was priced from (REQ-SSP-011 "value row id"); export and API only (rev 1.25) | start | none | no |
| SSP method | `ssp_method` | E-47 label | start | none | no |
| Currency | `currency` | mono | start | none | no |
| SSP low | `ssp_low` | money (extended, DS-FMT-13 precision) | end | none | no |
| SSP mid | `ssp_mid` | as above | end | none | no |
| SSP high | `ssp_high` | as above | end | none | no |
| Stated price | `stated_price` | money | end | none | no |
| Range check | `range_status` | "Inside range", "Below range", "Above range" (outline chips) | start | none | yes |
| Selected SSP | `selected_ssp` | money | end | Explain `obligation_version` `original_ssp_selected` | no |
| Weight | `allocation_weight` | DS-FMT-09 two decimals | end | none | no |
| Allocated | `allocated_amount` | money | end | Explain `allocated_amount` | no |
| Allocation adjustment | `allocation_adjustment` | money; signed (DS-FMT-31) | end | none | no |
| Override | `is_override` | "Yes" / "No" | start | RPT-22 | yes |

Totals per currency for "Stated price", "Allocated" and "Allocation adjustment" (the adjustment totals 0.00 per contract). Tie-out: none. Empty copy: title "No allocations from <from> to <to>"; description "Allocations appear here with the SSP book version, range check and selected SSP used." Sample world (asserted): J-03 `SF-ORD-20417` (WLD-X-23): AVM-PLAT-100 selected SSP 96,000.00 "Inside range" (85,000.00 – 115,000.00); AVM-IMPL-PLUS selected SSP 22,000.00 "Above range" (stated 24,000.00); allocated 97,627.12 / 22,372.88; allocation adjustment 1,627.12 / (1,627.12). J-01-AC-4 (WLD-T-20): Contract 1 POB #1 low 382.50, mid 450.00, high 517.50, stated 500.00, "Inside range", selected 500.00; Contract 2 POB #1 stated 600.00, "Below range", selected 612.00.

##### RPT-22 `ssp_override_listing` SSP override listing

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-SSP-006, 012; BR-SSP-03; research 07 SSP-03, A-05 |
| Screens | SF-08:report |
| Currency view | no |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes` | context | context pill | context | none |
| `from_date`, `to_date` | "Approved from", "Approved to" | dates | first day of the context fiscal year; today | as RPT-19 |

Rows: one per obligation version carrying `ssp_override_approval_request_id`; `row_key` `override:<external id>:<obligation key>:<request no>`.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Contract | `contract_external_id` | mono link | start | SF-03 | yes |
| Obligation | `obligation_key` | mono | start | SF-03:obligation `pane=ssp` | no |
| Product | `product_code` | mono | start | none | yes |
| Default version | `default_version_label` | mono | start | none | no |
| Override version | `override_version_label` | mono | start | none | no |
| Justification | `justification` | text | start | none | no |
| Requested by | `requested_by` | user | start | none | no |
| Approved by | `approved_by` | user | start | SF-12:request | no |
| Approved | `approved_at` | DS-FMT-17 | start | none | no |

Totals: none. Tie-out: none. Empty copy: title "No SSP overrides from <from> to <to>"; description "Obligations allocated with an SSP version other than the effective one appear here with their justification and approval." Sample world: none seeded in WLD-T-01; the empty state renders.

#### 5.6.5 Access, configuration and audit

##### RPT-23 `config_change_register` Configuration change register

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-022; REQ-POL-003, 006; research 07 CH-01, CH-02, A-16; CTL-031 |
| Screens | SF-08:report; SF-09 auditor requests (A-16) |
| Currency view | no |
| Permission | `report.run` and `audit.read` (rev 1.31; supervisor ruling R-63 (a); 04 API-R-41 rev 1.128): a Viewer, an SSP Analyst and an SSP Approver do not run it; a file output needs `report.export`. Rev 1.76: a run names only entities inside the caller's scope of BOTH permissions, and is read within them (04 API-R-41 rev 1.219) |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `from_date`, `to_date` | "Approved from", "Approved to" | dates | first day of the context fiscal year; today | as RPT-19 |
| `subject_types` | "Change types" | multi-select of E-08 subjects `REGISTRY_VERSION`, `RULE_SET_VERSION`, `POB_TEMPLATE_VERSION`, `ACCOUNT_MAPPING_VERSION`, `FX_RATE_SET_VERSION`, `SSP_BOOK_VERSION`, `MAPPING_PROFILE_VERSION`, `ROLE_CHANGE`, `PRINCIPAL_AGENT_CHANGE` with labels "Policy registry", "Rule set", "Obligation template", "Account mapping", "FX rate set", "SSP book", "Mapping profile", "Role", "Principal or agent" | all | none |

Rows: one per decided configuration approval request; `row_key` `change:<request no>`. Population (rev 1.76; item SCOPE-WORKSPACE-LISTS-1; supervisor rulings R-28 and R-121 (c); 04 T-PLT-17): a request is stated when the run's entities cover EVERY entity it names — the one of a request of one entity, each of a request of several — a request of all entities only by a run that names every entity of the workspace, and a tenant-level request always. A run of one entity states nothing of a request that also names another.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Change | `request_no` | mono link | start | SF-12:request | yes |
| Type | `subject_type` | label (parameter table) | start | none | yes |
| Object | `object_label` | "<name> v<n>" | start | subject screen | yes |
| Status | `status` | SCREENS.md §0.8 E-05 chip | start | none | yes |
| Effective from | `effective_from` | DS-FMT-16 | start | none | no |
| Author | `author` | user | start | none | yes |
| Submitted | `submitted_at` | DS-FMT-17 | start | none | no |
| Approvers | `approvers` | users joined with ", " | start | none | no |
| Approved | `decided_at` | DS-FMT-17 | start | none | no |
| Author differs from approver | `author_differs` | "Yes" / "No" (No shows chip Difference) | start | none | yes |
| Fields changed | `changed_field_count` | integer | end | SF-12:request diff | no |
| Simulation attached | `simulation_attached` | "Yes" / "No" | start | none | no |
| Test evidence | `test_evidence_count` | integer | end | none | no |

Totals: none; control totals `row_count`, `author_equals_approver_count` (expected 0). Tie-out: none. Empty copy: title "No configuration changes from <from> to <to>"; description "Approved and rejected configuration versions appear here with author, approver and diff." Sample world (asserted, J-17.8): rows for `AVM-MAP-2026-01` (approved by Marcus Webb) and `US-LIST 2026-H2`, each "Author differs from approver Yes".

##### RPT-24 `user_access_listing` User access listing

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-022; REQ-CTL-006; REQ-PLT-008, 012; BR-PLT-02; research 07 AC-04, A-15 |
| Screens | SF-08:report; SF-14 "Download access listing"; SF-09 auditor requests (A-15) |
| Currency view | no |
| Permission | `audit.read`, and not `report.run` (rev 1.31; supervisor ruling R-63 (a); 04 API-R-41 rev 1.128): the register holds no accounting data. A Tenant Admin runs it (PRD J-22.8) and so does an Auditor (J-17.6); a holder of `report.run` alone — Viewer, SSP Analyst, SSP Approver — does not. Known limit of 1.0: a file output needs `report.export`, which the Tenant Admin role does not hold, so a Tenant Admin reads the register on screen; the Auditor and the Controller export |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `as_of` | "As of" | timestamp (date and time UTC) | now | "Enter a time that is not in the future." |
| `include_removed` | "Include removed members" | checkbox | false | none |

Rows: one per membership × role assignment active at `as_of` (and removed memberships when included); a membership that holds no role at `as_of` has one row without a role, so every membership appears (rev 1.25); `row_key` `access:<email>:<role code>`. Removed at `as_of` (rev 1.103; item ACCESS-LISTING-SECOND-LIFE-1; 04 T-PLT-07 rev 1.307): a membership is removed at `as_of` when its row says so — `REMOVED` with `removed_at` by then — or when `as_of` lies inside a removal that a later invitation ended. The row keeps its last removal only, so an ended one is read from the audit trail, where the invitation's event states the removal's instant and its own time ends it; a listing as of a past instant so states the same memberships and control totals after the person is invited again. The trail gives that interval and nothing else: `as_of` selects the memberships and their role assignments, while the Membership chip, the name, "MFA enrolled" and "Last login" stay the values at the run's record cutoff — 04 T-PLT-07 and T-PLT-02 keep no history of them — so a membership listed as removed at `as_of` can read `INVITED`, and a run on the `historical` basis (a supplied `known_at`) whose cutoff precedes the last change of a membership in scope, or of its person, is refused by name on `known_at` — an invitation is such a change of the membership — while a run on the `record` basis never refuses. A change of the person does not count while the row shows nothing of that person but the address (rev 1.105: an invited or a removed member whose name is withheld, 04 T-PLT-02 rev 1.316 — such a member's later sign-in elsewhere refuses nothing); an erasure counts, for an erased identity is not withheld. The two cells of the person's own facts (rev 1.105; item IDENTITY-WITHHELD-BY-STATUS-1; 04 T-PLT-02 rev 1.316): for a row whose Membership is `INVITED` or `REMOVED`, "MFA enrolled" and "Last login" are not shown — null in the run's data and empty in CSV, as an empty cell is, and "Not shown" in XLSX and PDF, where "Never" would say of the person that there was no sign-in. "Never" keeps its meaning: an active or suspended member who has not signed in. The cells go by the row's own Membership value, so the run's data decide the printed cell. Whether the last login of a removed member becomes the time the member last opened this workspace is not decided in this revision.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| User | `display_name` | text | start | SF-14:user | yes |
| Email | `email` | mono | start | none | yes |
| Membership | `membership_status` | §0.4 E-78 chip | start | none | yes |
| Role | `role_name` | text | start | SF-14:roles | yes |
| Entity scope | `entity_scope` | "All entities" or entity codes (mono) | start | none | no |
| Granted | `granted_at` | DS-FMT-17 | start | none | no |
| Granted by | `granted_by` | user, or outline chip "Setup grant" with the rule `AUTO-BOOTSTRAP` | start | SF-12:request | yes |
| SoD exception | `sod_exception_id` | mono prefix link | start | SF-14:sod | no |
| MFA enrolled | `mfa_enrolled` | "Yes" / "No" | start | none | yes |
| Last login | `last_login_at` | DS-FMT-17; "Never" when null | start | none | no |
| Revoked | `revoked_at` | DS-FMT-17 | start | none | no |

Totals: none; control totals `membership_count`, `assignment_count`. Tie-out: none. Empty copy: not reachable (every tenant has a Tenant Admin). Sample world (asserted): J-17.6 lists every WLD-T-01 membership with roles, scopes, last login, grant date and grantor; J-01.3 (WLD-T-20) rows for `maya`, `priya`, `marcus`, `nikhil` show "Setup grant".

##### RPT-25 `sod_conflict_report` SoD conflict report

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-PLT-010; REQ-RPT-022; research 07 AC-03, A-15; CTL-034 |
| Screens | SF-08:report; SF-14:sod "SoD conflict report" |
| Currency view | no |
| Permission | `audit.read`, and not `report.run` (rev 1.31; supervisor ruling R-63 (a); 04 API-R-41 rev 1.128): the register holds no accounting data. A Tenant Admin runs it (PRD J-22.8) and so does an Auditor (J-17.6); a holder of `report.run` alone — Viewer, SSP Analyst, SSP Approver — does not. Known limit of 1.0: a file output needs `report.export`, which the Tenant Admin role does not hold, so a Tenant Admin reads the register on screen; the Auditor and the Controller export |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `as_of` | "As of" | timestamp | now | as RPT-24 |

Rows: one per membership × SoD rule in conflict at `as_of`; `row_key` `sod:<email>:<rule code>`. The five exception columns describe the exception that covers the conflict at `as_of` and are empty without one (rev 1.25). A permission held through an approval delegation that stood at `as_of` is held (rev 1.73; 04 T-PLT-21; supervisor ruling R-111 (4)): the conflict is a row, "Function A held" and "Function B held" include the delegated permissions, and "Through delegations" names each delegation that gives a permission of either function — "<delegator> until <DD MMM YYYY>", the UTC day of the delegation's end ("Priya Raman until 12 Oct 2026"), in the order of the delegator's name and the end. The cell is empty for a conflict held through roles alone; "Through roles" is empty for a member who holds both functions through delegations. A delegation counts for the permissions its delegator held at `as_of` through the assignments the run's entity scope counts, and from its creation at the earliest.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| User | `display_name` | text | start | SF-14:user | yes |
| Rule | `rule_code` | mono (for example `SoD-3`) | start | SF-14:sod | yes |
| Rule name | `rule_name` | text | start | none | no |
| Function A held | `function_a_permissions` | permission codes (mono) | start | none | no |
| Function B held | `function_b_permissions` | permission codes (mono) | start | none | no |
| Through roles | `roles` | role names joined with ", " | start | none | no |
| Through delegations | `delegations` | "<delegator> until <DD MMM YYYY>" per delegation, joined with ", " (rev 1.73) | start | none | no |
| Exception | `sod_exception_id` | mono prefix link; "None" with chip Difference when no approved exception covers the conflict | start | SF-14:sod | yes |
| Compensating control | `compensating_control` | text | start | none | no |
| Valid from | `valid_from` | DS-FMT-16 | start | none | no |
| Valid to | `valid_to` | DS-FMT-16 | start | none | no |
| Status | `exception_status` | §0.4 E-96 chip | start | none | yes |

Totals: none; control totals `conflict_count`, `uncovered_conflict_count`. Tie-out: none. Empty copy: title "No conflicts"; description "No member holds conflicting permissions at <DD MMM YYYY HH:mm UTC>." (J-17.6). Sample world (asserted): J-17.6 "No conflicts"; after J-22.7, J-22.8 lists Lena Fischer, `SoD-3`, the exception id, compensating control "Controller reviews every approval by Lena Fischer monthly using the approvals register.", valid for 90 days.

##### RPT-26 `approvals_register` Approvals register

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-022; REQ-PLT-011, 013 to 017; research 07 A-12 |
| Screens | SF-08:report |
| Currency view | yes (functional amounts of requests) |
| Permission | `report.run` and `audit.read` (rev 1.31; supervisor ruling R-63 (a); 04 API-R-41 rev 1.128): a Viewer, an SSP Analyst and an SSP Approver do not run it; a file output needs `report.export`. Rev 1.76: a run names only entities inside the caller's scope of BOTH permissions, and is read within them (04 API-R-41 rev 1.219) |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes` | context | context pill (All entities allowed) | context entity | none |
| `from_date`, `to_date` | "Submitted from", "Submitted to" | dates | first day of the context period; today | as RPT-19 |
| `subject_types` | "Types" | multi-select E-08 with SCREENS.md §15.3 labels | all | none |
| `status` | "Status" | multi-select E-05 | all | none |

Rows: one per decision, plus one row per pending request without decisions (rev 1.25: every request without a decision, so a request voided before any decision appears too; its key carries its first step and sequence 0); `row_key` `decision:<request no>:<step no>:<sequence>`. Population (rev 1.76; item SCOPE-WORKSPACE-LISTS-1; supervisor rulings R-28 and R-121 (c); 04 T-PLT-17): a request is stated when the run's entities cover EVERY entity it names — the one of a request of one entity, each of a request of several — a request of all entities only by a run that names every entity of the workspace, and a tenant-level request always. A run of one entity states nothing of a request that also names another.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Request | `request_no` | mono link | start | SF-12:request | yes |
| Type | `subject_type` | label | start | none | yes |
| Subject | `subject_id` | mono; the id of the subject the request names (04 T-PLT-17); export and API only (rev 1.25) | start | none | no |
| Summary | `summary` | text | start | none | no |
| Entity | `entity_code` | mono | start | none | yes |
| Currency | `amount_currency` | mono | start | none | no |
| Amount | `amount_functional` | money | end | none | no |
| Flags | `flags` | outline chips | start | none | no |
| Preparer | `preparer` | user or "System" | start | none | yes |
| Submitted | `submitted_at` | DS-FMT-17 | start | none | no |
| Step | `step_name`, `step_no` | "<n> · <name>" | start | none | no |
| Approver | `approver` | user; "System" for auto-approval | start | none | yes |
| On behalf of | `on_behalf_of` | user | start | none | no |
| Decision | `decision` | "Approve", "Reject", "Auto-approve" (E-07) | start | none | yes |
| Rule | `auto_rule_key`, `auto_rule_version` | "<rule key> v<n>" | start | none | no |
| Decided | `decided_at` | DS-FMT-17 | start | none | no |
| Comment | `comment` | text | start | none | no |
| Status | `status` | SCREENS.md §0.8 E-05 chip | start | none | yes |
| Content hash | `subject_content_sha256` | mono; the SHA-256 of the subject content the decision covered (04 T-PLT-20), the request's for a row without a decision; export and API only (rev 1.25) | start | none | no |

Totals: none; control totals `request_count`, `decision_count`, `auto_approval_count`. Tie-out: none. Empty copy: title "No approval requests from <from> to <to>"; description "Every approval request, decision and auto-approval appears here with preparer and approver." Sample world: WLD-B-01 to WLD-B-03 submitted by Maya Chen; J-14 `PERIOD_REOPEN` request with two decision rows (Marcus Webb, Elena Sokolova).

##### RPT-27 `api_client_inventory` API client inventory

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-PLT-033, 037; research 07 AC-07, CU-12; CTL-037 |
| Screens | SF-08:report; SF-16:developer "Download inventory" |
| Currency view | no |
| Permission | `audit.read`, and not `report.run` (rev 1.31; supervisor ruling R-63 (a); 04 API-R-41 rev 1.128): the register holds no accounting data. A Tenant Admin runs it (PRD J-22.8) and so does an Auditor (J-17.6); a holder of `report.run` alone — Viewer, SSP Analyst, SSP Approver — does not. Known limit of 1.0: a file output needs `report.export`, which the Tenant Admin role does not hold, so a Tenant Admin reads the register on screen; the Auditor and the Controller export |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `include_revoked` | "Include revoked clients" | checkbox | false | none |

Rows: one per API client; `row_key` `client:<name normalised>`.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Name | `name` | text | start | SF-16:developer | yes |
| Client id | `client_id` | mono, never truncated | start | none | no |
| Status | `status` | §0.4 E-103 chip | start | none | yes |
| Scopes | `scopes` | permission codes (mono) joined with ", " | start | none | no |
| Entity scope | `entity_scope` | "All entities" or codes | start | none | no |
| Rate limit per minute | `rate_limit_per_minute` | integer | end | none | no |
| Expires | `expires_at` | DS-FMT-16 | start | none | no |
| Last used | `last_used_at` | DS-FMT-17; "Never" | start | none | no |
| Secret issued | `secret_rotated_at` | DS-FMT-17; "Not issued" | start | none | no |
| Approval | `approval` | request number, or empty for a client created before approvals applied | start | none | no |
| Approved by | `approved_by` | approver names joined with ", "; "Rule AUTO-BOOTSTRAP" for a request approved by that rule; empty while pending or rejected | start | none | no |
| Approved | `approved_at` | DS-FMT-17 | start | none | no |
| Created by | `created_by` | user | start | none | no |
| Created | `created_at` | DS-FMT-17 | start | none | no |

Totals: none; control total `client_count`. Tie-out: none. Empty copy: title "No API clients"; description "OAuth2 client-credentials clients appear here with their scopes and last use. Secrets are never shown." Sample world: WLD-T-01 `svc-salesforce`, `svc-netsuite`, `svc-metering` (WLD-U-12).

##### RPT-43 `audit_log_export` Audit log export

| Aspect | Specification |
|---|---|
| Kind, formats | `EXTRACT`; CSV with manifest, JSON |
| REQ and evidence | REQ-PLT-018, 019; research 07 AU-01, A-19 |
| Screens | SF-09:audit-log "Export" (the grid of SF-09:audit-log is the on-screen view) |
| Currency view | no |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `from` | "From" | timestamp | the SF-09:audit-log filter value | "Start must be on or before end." |
| `to` | "To" | timestamp | now | as above |
| `object_type`, `object_id` | "Object" | from SF-09:audit-log filters | none | none |
| `contract_id` (rev 1.75) | "Object" | the contract the Object chip of SF-09:audit-log names; the screen sends it once §6.3 binds it — until then its state "Export unavailable" stands | none | none |
| `actor_id` | "Actor" | from filters | none | none |
| `action` | "Action" | from filters | none | none |
| `outcome` (rev 1.75) | "Outcome" | one or more of `SUCCESS`, `DENIED`, `FAILED`: the Outcome chip of SF-09:audit-log; sent by the screen as `contract_id` is | none | none |

Rows: one per audit event in `chain_seq` order; `row_key` `event:<chain_seq>`. With `contract_id` (rev 1.75; item RPT-43-PARAMS-1; supervisor ruling R-119 (h)) the rows are the trail of that contract — every event that names it, whatever its object type (04 §16.14) — read as SF-09:audit-log lists it and narrowed by the other parameters; `outcome` keeps the events of any of the outcomes given. Under the range and the filters of the list the export states the rows of the list, up to its record cutoff. Columns: every T-PLT-19 column in table order, headers equal to the column names: `chain_seq`, `occurred_at` (ISO 8601 UTC with microseconds), `id`, `actor_id`, `actor_kind`, `actor_roles`, `auth_method`, `mfa_verified`, `on_behalf_of_id`, `api_client_id`, `support_grant_id`, `source_ip`, `request_id`, `action`, `object_type`, `object_id`, `object_version`, `before`, `after`, `diff`, `reason_code`, `comment`, `approval_request_id`, `outcome`, `detail`, `prev_hmac`, `hmac`, `hmac_key_id`; JSON-valued columns are canonical JSON strings (redacted per `erev_api.audit.REDACT`). Totals: none; manifest `row_count`, `first_chain_seq`, `last_chain_seq`, `last_hmac`. Tie-out: none. Empty copy: "No audit events match these filters." Sample world (asserted, J-17.5): filtered to the trail of `PRJ-CB-2026-01` (`contract_id`, rev 1.75), the export contains the field-level diffs of the modification and estimate events beside the contract's own; J-17-AC-4 every download writes an audit event `report.export` with the run id.

##### RPT-44 `chain_verification_report` Audit chain verification report

| Aspect | Specification |
|---|---|
| Kind, formats | `REGISTER`; CSV, PDF, JSON |
| REQ and evidence | REQ-PLT-020; D-43; research 07 AU-03, A-19; CTL-039 |
| Screens | SF-08:report; SF-09:audit-log "Verification history" link |
| Currency view | no |
| Permission | `report.run` and `audit.read`, the latter at any scope (rev 1.76; the supervisor's ruling of 2026-10-01 on item SCOPE-WORKSPACE-LISTS-1): the report states counts and chain values and no entity's data, as the verifications are read (04 API-C-03 rev 1.219). RPT-43 states the events themselves and asks `audit.read` for all entities |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `from`, `to` | "Finished from", "Finished to" | timestamps | 30 days before now; now | as RPT-43 |

Rows: one per `audit_chain_verification` row; `row_key` `verification:<finished_at ISO>` (rev 1.25: a further verification that finished at the same instant carries `:2`, `:3`, so a key occurs once).

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Finished | `finished_at` | DS-FMT-17 with seconds | start | SF-09:verification | no |
| Trigger | `trigger` | "Scheduled", "On demand" | start | none | yes |
| From sequence | `from_chain_seq` | integer | end | none | no |
| To sequence | `to_chain_seq` | integer | end | none | no |
| Events checked | `events_checked` | integer | end | none | no |
| Result | `result` | §0.4 E-98 chip | start | none | yes |
| First failure | `first_failure_seq` | integer; em dash | end | SF-09:verification | no |
| Last chain value | `digest_last_hmac` | hash prefix with copy | start | none | no |
| Digest | `digest_file_id` | link "Download digest" | start | none | no |

Totals: none; control totals `verification_count`, `failure_count`. Tie-out: none. Empty copy: title "No verifications from <from> to <to>"; description "The audit chain is verified daily and on demand. Each verification records the events checked and a digest." Sample world: daily scheduled verifications through the seed; J-17.5 on-demand verification, result Verified.

#### 5.6.6 Analysis: books, entities, metrics and closes

##### RPT-33 `book_bridge` Book-to-book bridge

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-BK-001, 002, 006; D-24, D-25; research 04 §13 |
| Screens | SF-08:report |
| Currency view | yes; default `functional` |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes` | "Entity" | select, one entity keeping both books | context entity | "Choose an entity that keeps both the ASC 606 and IFRS 15 books." |
| `from_period_key`, `to_period_key` | "From", "To" | period selects | context period | as RPT-15 |
| `period_lock_id` | "Source" | RV-04 | lock when locked | none |

Section 1 "Summary by measure": rows `REVENUE` "Revenue", `CONTRACT_LIABILITY` "Contract liability", `CONTRACT_ASSET` "Contract asset", `UNBILLED_RECEIVABLE` "Unbilled receivable", `COST_ASSETS` "Contract cost assets", `LOSS_PROVISION` "Loss provision"; columns "Measure", "ASC 606 (<ISO>)", "IFRS 15 (<ISO>)", "Difference (<ISO>)" (signed). Section 2 "Difference by driver": rows `COLLECTIBILITY` "Collectibility", `COST_IMPAIRMENT_REVERSAL` "Contract cost impairment reversal", `FRAMEWORK_ELECTIONS` "Framework elections", `LICENCE_RENEWALS` "Licence renewals", `ONEROUS_CONTRACTS` "Onerous contracts", `ADVANCE_CONSIDERATION_FX` "Advance consideration FX (IFRIC 22)", `OTHER` "Other"; columns "Driver", "Measure", "Effect (<ISO>)" (signed, Explain contributors), "Contracts affected" (integer). Section 3 "By contract": "Contract" (link SF-03), "Driver", "Measure", "ASC 606", "IFRS 15", "Difference". Totals per currency; section 2 total equals section 1 difference per measure. Tie-out: `TO_BRIDGE_DRIVERS_EQ_DIFFERENCE` "Driver effects equal the book difference" (04 table 10-T). Empty copy: title "No differences between ASC 606 and IFRS 15 in <range label>"; description "Differences appear when a framework switch changes revenue or balances for <entity code>." Sample world: AVM-UK (`ASC606` and `IFRS15`, PRD §2.5), Sep 2026; the PRD fixes no difference figures.

Dataset and rules (rev 1.25; BUILD_SPEC RPS-12). One dataset holds the three sections; a row fills the fields of its section and leaves the others empty. `row_key`: section 1 `measure:<MEASURE>`; section 2 `driver:<DRIVER>:<MEASURE>`; section 3 `contract:<external id>:<MEASURE>`. The keys of sections 1 and 2 gain `:<ISO>` when the run holds several currencies. Section 1 lists the six measures when a contract of the entity has an amount in either book; section 2 lists every driver for each measure in which a contract differs; section 3 has one row per contract and measure that differ.

| Header | Field | Format | Align | Sections |
|---|---|---|---|---|
| Section | `section` | integer; export and API only | end | 1, 2, 3 |
| Measure code | `measure_code` | mono; export and API only | start | 1, 2, 3 |
| Measure | `measure_label` | text | start | 1, 2, 3 |
| Driver code | `driver_code` | mono; export and API only | start | 2, 3 |
| Driver | `driver_label` | text | start | 2, 3 |
| Contract | `contract_external_id` | mono link (SF-03) | start | 3 |
| Currency | `currency` | mono | start | 1, 2, 3 |
| ASC 606 (<ISO>) | `asc606_amount` | money | end | 1, 3 |
| IFRS 15 (<ISO>) | `ifrs15_amount` | money | end | 1, 3 |
| Difference (<ISO>) | `difference` | money; signed | end | 1, 3 |
| Effect (<ISO>) | `effect` | money; signed | end | 2 |
| Contracts affected | `contracts_affected` | integer | end | 2 |

Measures. `REVENUE` is the revenue the entity's subledger carries in each book over the range: credit less debit of its T-SL-04 `REVENUE` lines recorded by the run's `known_at`. The five balances are the presented balances of each book at the end of the range, read as RPT-02 reads them (the latest contract version of the book in the disclosures): `CONTRACT_LIABILITY`, `CONTRACT_ASSET`, `UNBILLED_RECEIVABLE`, `COST_ASSETS` (T-CON-09 contract cost assets) and `LOSS_PROVISION`. A difference is ASC 606 less IFRS 15.

Drivers. Each contract's difference in a measure has one driver, identified from stored facts in this order. (1) `COLLECTIBILITY`: the Step 1 conclusion differed between the books — at a computation recorded by the cutoff exactly one of them held the contract as not a contract (E-06 `NOT_A_CONTRACT`), or both books hold it as not a contract at their latest version, when revenue can arise only under ASC 606-10-25-7, whose event (c) is the POL-012 switch; Step 1 is assessed per book (POL-011, POL-012), and a contract that fails it in one book has no revenue and no contract balance there, so the driver carries every measure of that contract. (2) `ONEROUS_CONTRACTS`: the loss provision (POL-150 to POL-152). (3) `COST_IMPAIRMENT_REVERSAL`: the contract cost assets, when the IFRS 15 book posted an impairment reversal (JET-09d) for the contract on or before the range end (POL-144). (4) `OTHER`: every other difference. `ADVANCE_CONSIDERATION_FX` is 0.00: the IFRIC 22 layer date (POL-160, POL-163) moves functional amounts only, and the report serves transaction-currency amounts. `FRAMEWORK_ELECTIONS` and `LICENCE_RENEWALS` are not identified from stored facts in 1.0 — the switches of POLICIES §6.2 differ between the books of every contract, and which of them moved an amount is not stored — so their effect is part of `OTHER`: their two cells show 0.00 when no contract's difference in the measure is left to `OTHER`, and are empty otherwise, never an unsupported 0.00. `TO_BRIDGE_DRIVERS_EQ_DIFFERENCE` passes when, per measure and currency, the driver effects sum to the section 1 difference. This attribution is the documented rule by supervisor ruling R-47 (b) of 2026-09-30 — supervisor ruling pending the accountant (accounting decision AD-44); REQ-BK-006 stays partial for `FRAMEWORK_ELECTIONS` and `LICENCE_RENEWALS` until the accountant decides.

Currency view. `functional` (the default) and `reporting` are served when every contract is in the entity's functional currency; otherwise the run is refused by name and `transaction` is the view (as RPT-03). A run whose `entity_codes` do not name exactly one entity that keeps both books is refused with the validation copy of `entity_codes`. Control totals: `contract_count`, `revenue_asc606`, `revenue_ifrs15`, `revenue_difference` and `other_effect` per currency.

##### RPT-34 `adoption_bridge` Adoption bridge

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-BK-007; POL-218; 606-10-65-1(h), (i); D-14a |
| Screens | SF-08:report |
| Currency view | no |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes` | "Entity" | select (entities keeping the `LEGACY` book) | context entity | "Choose an entity that keeps the Legacy book." |
| `date_of_initial_application` | "Date of initial application" | date | first day of the entity's first ASC 606 period | "Choose a date on or after the first ASC 606 period." |
| `contract_external_id` | "Contract (optional)" | combobox | all | as RPT-09 |

Section 1 "Cumulative effect by contract": `row_key` `contract:<external id>`; columns "Contract" (link), "Customer", "Currency", "Revenue to date, legacy GAAP", "Revenue to date, ASC 606", "Cumulative effect" (signed), "Contract liability, legacy GAAP", "Contract liability, ASC 606", "Contract asset and unbilled receivable, ASC 606". Section 2 "Line-item comparison (ASC 606-10-65-1(i))": rows "Revenue", "Contract liability", "Contract asset", "Unbilled receivable", "Contract cost assets"; columns "Line item", "Under legacy GAAP", "Under Topic 606", "Effect". Totals per currency. Footnote: "The cumulative-effect adjustment to retained earnings is exported for a manually approved journal. No 1.0 posting uses the Retained earnings role." Tie-out: none. Empty copy: title "No contracts at the date of initial application"; description "Contracts with both Legacy and ASC 606 figures at <date> appear here." Sample world: WLD-T-00 `Mock Entity 1` and `Mock Entity 2` keep `ASC606` and `LEGACY` (PRD §2.11); no figures are asserted.

Dataset and rules (rev 1.25; BUILD_SPEC RPS-12). The date of initial application is the first day of a period of the entity's calendar; a date inside a period is refused with "Choose the first day of a period of the entity's calendar." Every figure is at the end of the day before that date; a date that opens the calendar has no day before it and the report is empty. One dataset holds both sections; a row fills the fields of its section. `row_key`: section 1 `contract:<external id>`; section 2 `line:<LINE>` (`:<ISO>` when the run holds several currencies), with `<LINE>` one of `REVENUE`, `CONTRACT_LIABILITY`, `CONTRACT_ASSET`, `UNBILLED_RECEIVABLE`, `COST_ASSETS`.

| Header | Field | Format | Align | Sections |
|---|---|---|---|---|
| Section | `section` | integer; export and API only | end | 1, 2 |
| Contract | `contract_external_id` | mono link (SF-03) | start | 1 |
| Customer | `customer_name` | text | start | 1 |
| Currency | `currency` | mono | start | 1, 2 |
| Revenue to date, legacy GAAP | `revenue_legacy` | money | end | 1 |
| Revenue to date, ASC 606 | `revenue_asc606` | money | end | 1 |
| Cumulative effect | `cumulative_effect` | money; signed | end | 1 |
| Contract liability, legacy GAAP | `contract_liability_legacy` | money | end | 1 |
| Contract liability, ASC 606 | `contract_liability_asc606` | money | end | 1 |
| Contract asset and unbilled receivable, ASC 606 | `asset_asc606` | money | end | 1 |
| Line code | `line_code` | mono; export and API only | start | 2 |
| Line item | `line_label` | text | start | 2 |
| Under legacy GAAP | `legacy_amount` | money | end | 2 |
| Under Topic 606 | `asc606_amount` | money | end | 2 |
| Effect | `effect` | money; signed | end | 2 |

Figures, in each contract's transaction currency. `revenue_legacy` is the pre-standard revenue the `LEGACY` book holds for the contract through that day: debit less credit of its T-SL-04 `PRE_STANDARD_REVENUE` lines whose origin period (else posting period) ends on or before it (ENGINE_SPEC_B S13-R-08). `revenue_asc606` is the cumulative revenue of the contract's obligations at that period end in the latest `ASC606` contract version (T-ENG-03 `revenue_cum`), the version RPT-02 reads the balances from. `cumulative_effect` is `revenue_asc606` less `revenue_legacy`. `contract_liability_legacy` is the amount billed to that day (T-ENG-03 `billed_cum`) less `revenue_legacy` when positive; when it is negative the legacy position is the unbilled receivable of section 2, and legacy GAAP carries no contract asset (0.00). `contract_liability_asc606` and `asset_asc606` are the presented `ASC606` balances. In section 2 `effect` is Topic 606 less legacy GAAP; the `LEGACY` book records no contract cost asset, so the legacy amount and the effect of `COST_ASSETS` are empty, never 0.00. Section 1 lists the contracts the entity contracted that have an `ASC606` version in the disclosures and a figure on either side; a contract whose pre-standard revenue stands against no such version (a draft, or not a contract under Topic 606) is not listed and is stated in the control totals `legacy_only_contract_count` and `legacy_only_revenue`. Control totals: `contract_count`, `revenue_legacy_total`, `revenue_asc606_total` and `cumulative_effect_total` per currency, `date_of_initial_application` and `as_of`. A run whose `entity_codes` do not name exactly one entity that keeps the `LEGACY` and `ASC606` books is refused with the validation copy of `entity_codes`.

##### RPT-35 `intercompany_pairs` Intercompany pairs

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-ENT-003, 005; D-23; POL-170, POL-171 |
| Screens | SF-08:report |
| Currency view | yes; default `transaction` |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes` | "Entities" | context pill; All entities allowed | All entities | none |
| `book`, `period_lock_id` | context | context pill; RV-04 | context | none |
| `from_period_key`, `to_period_key` | "From", "To" | period selects | context period | as RPT-15 |

Section 1 "Pairs by entity": `row_key` `pair:<due from entity>:<due to entity>:<currency>`. Section 2 "By contract" (rev 1.25; BUILD_SPEC RPS-12): `row_key` `contract:<external id>:<obligation key>:<period key>`. One dataset holds both sections; a row fills the fields of its section.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Section | `section` | integer; export and API only | end | none | no |
| Due from entity | `due_from_entity_code` | mono | start | none | yes |
| Due to entity | `due_to_entity_code` | mono | start | none | yes |
| Currency | `currency` | mono | start | none | no |
| Due from (<ISO>) | `due_from_amount` | money | end | contributors | no |
| Due to (<ISO>) | `due_to_amount` | money | end | contributors | no |
| Unmatched (<ISO>) | `unmatched_amount` | money; chip Difference when non-zero; sections 1 and 2 | end | none | no |
| Contract | `contract_external_id` | mono link; section 2 | start | SF-03 | no |
| Obligation | `obligation_key` | mono; section 2 | start | none | no |
| Contracting entity | `contracting_entity_code` | mono; section 2 (the due-to entity) | start | none | no |
| Performing entity | `performing_entity_code` | mono; section 2 (the due-from entity) | start | none | no |
| Period | `period_key` | mono; section 2 | start | none | no |
| Pair amount (<ISO>) | `pair_amount` | money; section 2 | end | none | no |

Section 2 "By contract": "Contract" (link SF-03), "Obligation", "Contracting entity", "Performing entity", "Period", "Currency", "Pair amount". Totals per currency. Tie-out: `TO_IC_UNMATCHED_ZERO`. Empty copy: title "No intercompany pairs in <range label>"; description "Pairs appear when an obligation is performed by an entity other than the contracting entity." Sample world (asserted, J-13-AC-7, WLD-X-14): Sep 2026 `SF-ORD-UK-2001` O1 performed by AVM-US for AVM-UK: pairs 4,790.61 GBP; unmatched 0.00.

Rules (rev 1.25; BUILD_SPEC RPS-12). A pair sums the T-SL-04 lines of the two intercompany roles (JET-13) recorded by the run's `known_at`, each entity over its own period range: `due_from_amount` is debit less credit of the `INTERCOMPANY_DUE_FROM` lines the due-from entity carries against the due-to entity; `due_to_amount` is credit less debit of the `INTERCOMPANY_DUE_TO` lines the due-to entity carries against the due-from entity; `unmatched_amount` is their difference. A side whose entity is outside the run is not read: its cell and the unmatched cell are empty, never 0.00. In section 2 `pair_amount` is the contracting entity's relief (POL-171), and the performing entity's amount when the contracting entity is outside the run; two entities on different calendars list each side under its own period. `TO_IC_UNMATCHED_ZERO` passes when every pair whose two entities are in the run has an unmatched amount of 0.00 (two pairs that offset each other are two breaks); it is `NOT_APPLICABLE` without such a pair. Control totals: `pair_count`, `incomplete_pair_count` (pairs with an entity outside the run), and `due_from_total`, `due_to_total` and `unmatched_total` per currency. Currency view: `transaction` is always served; another view only when every line's currency is the functional currency of the entity that carries it, else the run is refused by name.

##### RPT-37 `bookings_billings_revenue` Bookings, billings and revenue

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-020 |
| Screens | SF-08:report |
| Currency view | yes; default `functional` |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `entity_codes`, `book`, `period_lock_id` | context | context pill; RV-04 | context | none |
| `from_period_key`, `to_period_key` | "From", "To" | period selects | context fiscal year to the context period | as RPT-15 |
| `granularity` | "Granularity" | segmented "Month", "Quarter", "Year" | `MONTH` | none |

Rows: one per period bucket × entity; `row_key` `period:<key>:<entity code>`.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Period | `period_label` | DS-FMT-19 | start | none | no |
| Entity | `entity_code` | mono | start | none | yes |
| Currency | `currency` | mono | start | none | no |
| Booked, new contracts | `booked_new` | money | end | contributors (activated contracts) | no |
| Booked, modifications | `booked_modifications` | money; signed | end | RPT-14 | no |
| Billings | `billings` | money; signed | end | contributors (billing events) | no |
| Revenue | `revenue` | money | end | RPT-01 | no |

Totals per currency. Tie-out: `TO_BBR_EQ_JE_REVENUE`. Empty copy: title "No bookings, billings or revenue in <range label>"; description "Activated contracts, modifications, invoices and recognized revenue appear here by period." Sample world (not asserted): AVM-US Sep 2026 booked modifications include `SF-ORD-10002` +60,000.00 (WLD-X-06).

##### RPT-38 `variance_between_closes` Variance between closes

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-RPT-019; REQ-CLS-011 (re-lock diff); BR-CLS-07 |
| Screens | SF-08:report; SF-05:history "Open diff report" |
| Currency view | no |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `from_period_lock_id` | "Earlier lock" | select of locks of the context entity and book | previous lock of the context period | "Choose an earlier lock." |
| `to_period_lock_id` | "Later lock" | select | current lock of the context period | "The later lock must be recorded after the earlier lock." |

Header meta adds "Earlier lock <id prefix> (<DD MMM YYYY HH:mm UTC>)" and "Later lock <id prefix> (<DD MMM YYYY HH:mm UTC>)". Section 1 "Change by driver": rows `NEW_CONTRACTS` "New contracts", `MODIFICATIONS` "Modifications", `ESTIMATE_CHANGES` "VC and estimate changes", `PROGRESS` "Progress", `FX` "FX", `LATE_EVENTS` "Late events", `OTHER` "Other"; columns "Driver", "Measure" ("Revenue", "Contract liability", "Contract asset and unbilled receivable", "Remaining performance obligations"), "Change (<ISO>)" (signed). Section 2 "Changes by contract": `row_key` `change:<external id>:<measure>:<period key>`.

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Measure | `measure_label` (with period for revenue, for example "Revenue, Sep 2026") | text | start | none | yes |
| Scope | `contract_external_id` or entity code | mono link | start | SF-03 | yes |
| Currency | `currency` | mono | start | none | no |
| Earlier lock | `earlier_value` | money | end | none | no |
| Later lock | `later_value` | money | end | none | no |
| Change | `change` | money; signed (DS-FMT-31) | end | Explain contributors | no |
| Driver | `driver_label` | text | start | none | yes |

Totals per currency and measure. Tie-out: none. Empty copy: title "No changes between the two locks"; description "The figures frozen at both locks are identical." Sample world (asserted, J-14-AC-3): `PRJ-CB-2026-01` "Revenue, Sep 2026" 197,294.12 → 229,852.94, change +32,558.82; "Contract asset and unbilled receivable" 97,294.12 → 129,852.94, change +32,558.82; "Remaining performance obligations" 552,705.88 → 520,147.06, change (32,558.82); both lock ids listed.

#### 5.6.7 Forecasts and migration

##### RPT-39 `forecast_outputs` Forecast outputs

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, JSON |
| REQ and evidence | REQ-FC-003; T-FC-03 |
| Screens | SF-17:run (primary); SF-08:report in sandbox tenants |
| Currency view | yes |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `forecast_run_id` | "Forecast run" | select of succeeded forecast runs | latest succeeded run | "Choose a forecast run." |
| `entity_codes`, `book` | context | context pill | the run's `parameters.entity_ids` and `book_code` | none |

Sections: 1 "Forecast revenue by period" (columns of RPT-01 over the horizon periods; chart DS-CH-01 with no Recognized series beyond the last closed period); 2 "Forecast billing by period" ("Contract", "Currency", one column per period, "Total"); 3 "Projected contract balances" ("Period end", "Entity", "Currency", "Contract liability", "Contract asset", "Unbilled receivable"); 4 "Projected remaining performance obligations" (RPT-06 section 1 columns at the horizon end); 5 "Journal preview" ("Period", "Account role", "Currency", "Debit", "Credit"). Totals per currency per section. Header meta adds "Scenario <name>", "Event set <name> v<n>", "Horizon <first period> – <last period>". Tie-out: none. Empty copy: title "No forecast figures"; description "Run a forecast over an event set to see projected revenue, billing, balances and RPO." Sample world (asserted, J-18.4): scenario "Q4 2026 outlook", event set "Q4 base" v1, horizon Oct 2026 – Dec 2026; `NS-SO-DE-5004` O1 Oct 2026 forecast revenue 35,669.72.

##### RPT-40 `actual_vs_forecast` Actual vs forecast

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-FC-004, 005 |
| Screens | SF-17:run "Actual vs forecast" link; SF-08:report in sandbox tenants |
| Currency view | yes |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `forecast_run_id` | "Forecast run" | select | latest succeeded run | "Choose a forecast run." |
| `row_dimension` | "Rows" | select "Contract", "Revenue category" | `CONTRACT` | none |
| `from_period_key`, `to_period_key` | "From", "To" | period selects within the horizon | the run's horizon | "Choose periods inside the forecast horizon." |

Rows: row value × period; `row_key` `<dimension>:<value>:<period key>`. Columns: "Contract" or "Revenue category"; "Period" (DS-FMT-19); "Currency"; "Forecast revenue"; "Actual revenue"; "Variance" (signed, actual − forecast); "Variance %" (DS-FMT-09 with sign; em dash when forecast is 0). Actual revenue is the revenue posted in the scenario tenant as of its latest refresh (REQ-FC-004); header meta adds "Actuals known at <scenario.last_refreshed_at>". Totals per currency. Tie-out: none. Empty copy: title "No actuals yet for the forecast horizon"; description "Refresh the scenario after production periods close to compare actual revenue with the forecast." Sample world: J-18-AC-4 (availability asserted): WLD-T-30, Oct 2026 – Dec 2026.

##### RPT-41 `migration_reconciliation` Migration reconciliation

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-MIG-003, 004; D-17, D-31; BR-MIG-02; `docs/legacy/DEVIATIONS.md`; CTL-048 |
| Screens | SF-19:detail "Reconciliation" tab (primary); SF-08:report |
| Currency view | no (legacy values at full precision) |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `migration_id` | "Migration" | select of migrations | the migration of SF-19:detail | "Choose a migration." |
| `only_differences` | "Only differences above tolerance" | checkbox | false | none |

Summary strip (DS-CMP-06 KPI strip "Reconciliation"): "Contracts", "Legacy obligation rows", "Lines compared", "Differences above tolerance", "Explained by deviations", "Unexplained" (chip Difference when above 0). Rows: T-MIG-03 lines; `row_key` `line:<contract>:<obligation>:<measure>` with each component percent-encoded so the key is injective (`%` → `%25`, then `:` → `%3A`; the CV-21 key convention) and the contract level marked by an EMPTY obligation component (`line:Contract 1::TRANSACTION_PRICE`) — never a word that could be a legitimate obligation key; an obligation key that is itself the empty string (not a legitimate key — T-MIG-02 `obligation_key` is non-empty text) encodes as `%`, which no encoded component can otherwise produce, so the contract level and the empty string never collide (rev 1.13; Codex RPT41-ID-1, packet 1006). Consumers match the row by its T-MIG-03 identity (contract, obligation, measure), not by parsing the key.

Reader and registration (rev 1.13): the builder is registered in the report framework under the report code `migration_reconciliation` (RPT-41) and reads only migration tables — no engine call; the eRev values are those the reconciliation stored. For the run's `migration_id` it reads the tenant's T-MIG-01 `migration_batch` row (absent or not visible → 422 `validation-failed` on `parameters.migration_id` with "Choose a migration."), the batch's T-MIG-03 `migration_reconciliation_line` rows as the report rows (ordered by contract, "Contract level" before obligations, then the measure in the T-MIG-03 CHECK order), and the exception numbers of the linked `exception_item` rows. The KPI strip binds to the control totals: "Contracts" `contracts` and "Legacy obligation rows" `legacy_obligation_rows` from the batch's T-MIG-01 `profile` (`contracts`, `legacy_pob_rows`; 0 while the batch is not profiled), "Lines compared" `line_count`, then `differences_above_tolerance`, `explained`, `unexplained`. Migration lines carry no entity (T-MIG tables have no entity column), so the run's entity scope filters nothing; a batch that holds no lines yet renders the empty copy below. IPE (T-RPT-01 `ipe_logic`, REQ-RPT-027): sources `migration_reconciliation_line`, `migration_batch`, `exception_item`; joins on `migration_batch_id` and `exception_item_id`; filters `migration_batch.id = migration_id` and, with `only_differences`, lines outside tolerance; population: every line of the batch in the tenant — the entity scope names no filter (rev 1.13; Codex RPT41-IPE-1).

Value representation (D-98 89): the comparison rows carry exact values, never the posted-cents journal representation. "Legacy value" is the legacy database's stored text at full precision (the unrounded floats the shipped `ASC606.db` holds). "eRev value" is the exact, trace-sourced measure of the compared obligation or contract (dev-guide DG-PAR-05 `exact(m)`): `ORIGINAL_ALLOCATION` → `obligation_version.original_allocated_exact`; `ALLOCATION` → `exact(revenue_cum) + exact(remaining_allocation)`; `TRANSACTION_PRICE` → Σ of that sum over the contract's obligations; `REVENUE_CUM` → `exact(revenue_cum)`; `NET_POSITION` → `exact(position_obligation)` (contract level: Σ); `RECLASS` → `exact(netting_reclass_amount)` (contract level: Σ); `REMAINING_QTY` → `remaining_quantity`; `POB_COUNT` → the count of non-`VC` obligations; `BILLED_CUM` → `billed_cum`, a billing fact carried in cents on both sides. The reconciliation writes these exact values to T-MIG-03 (`erev.exact`), the report renders them as exact decimal text, and the tolerance and the expected values are unchanged; posted cents remain the journal representation (RPT-13, RPT-10).

| Header | Field | Format | Align | Drill | Filter |
|---|---|---|---|---|---|
| Contract | `contract_external_id` | mono | start | SF-03 after promotion | yes |
| Obligation | `obligation_key` | mono; "Contract level" when null | start | none | yes |
| Measure | `measure` | "Obligation count" (`POB_COUNT`), "Transaction price" (`TRANSACTION_PRICE`), "Original allocation" (`ORIGINAL_ALLOCATION`; the creation-time allocation, 04 rev 1.35), "Allocation" (`ALLOCATION`), "Revenue to date" (`REVENUE_CUM`), "Billed to date" (`BILLED_CUM`), "Billed less recognized" (`NET_POSITION`, SB-R-10), "Reclassification to contract asset" (`RECLASS`), "Remaining quantity" (`REMAINING_QTY`); every label names an exact, trace-sourced eRev measure except "Billed to date", a posted-cents billing fact (D-98 89; "Value representation" above) | start | none | yes |
| Legacy value | `source_value` | exact decimal text, trailing zeros trimmed | end | none | no |
| eRev value | `erev_value` | as above | end | none | no |
| Difference | `difference` | as above; signed | end | none | no |
| Tolerance | `tolerance` | "0.0001" | end | none | no |
| Within tolerance | `is_within_tolerance` | "Yes"; "No" with chip Difference | start | none | yes |
| Deviation | `deviation_ref` | mono (for example `DEV-052`) | start | none | yes |
| Exception | `exception_item_id` → exception no | mono link | start | SF-11:item | no |

Totals: none; control totals `contracts`, `legacy_obligation_rows` (rev 1.13), `line_count`, `differences_above_tolerance`, `explained`, `unexplained`. Tie-out: `TO_MIGRATION_UNEXPLAINED_ZERO` (promotion requires Pass, BR-MIG-02). Empty copy: title "No reconciliation lines"; description "Run the import to reconcile each contract and obligation with the legacy database." Sample world (asserted): J-20 (WLD-X-27, cutover 31 Jan 2023): contracts 4; legacy obligation rows 16 (14 obligations, 2 VC elements); transaction price C1 1,300.00, C2 900.00, C3 1,300.00, C4 950.00; revenue to date C1 295.69, C2 58.85; billed to date C1 300.00, C2 0.00; C1 contract liability 4.31; C2 contract asset and unbilled receivable 58.85; migrated history rows 24; differences above 1e-4: 0. J-21 (WLD-X-28, 31 Oct 2023): transaction price 800.00 / 1,100.00 / 2,600.00 / 1,200.00; revenue = billing = transaction price; every difference above 1e-4 carries a deviation reference (for example `DEV-052` on Contract 3 POB #5); unexplained 0.

##### RPT-42 `parallel_run_comparison` Parallel-run comparison

| Aspect | Specification |
|---|---|
| Kind, formats | `STANDARD`; XLSX, CSV, PDF, JSON |
| REQ and evidence | REQ-MIG-007; C-13 |
| Screens | SF-19:detail "Parallel run" link; SF-08:report |
| Currency view | no |

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `migration_id` | "Migration" | select | the current migration | "Choose a migration." |
| `from_period_key`, `to_period_key` | "From", "To" | period selects | the migration's first period after cutover; the latest open period | as RPT-15 |

Section 1 "Journal lines by account": `row_key` `je:<period key>:<account>`; columns "Period", "Account" (mono), "Legacy debit", "Legacy credit", "eRev debit", "eRev credit", "Difference" (signed; chip Difference when non-zero). Section 2 "Contract balances": `row_key` `balance:<external id>:<period key>`; columns "Contract", "Period end", "Legacy billed less recognized", "eRev contract liability", "eRev contract asset and unbilled receivable", "Difference". Totals per section. Tie-out: none. Empty copy: title "No periods to compare"; description "Legacy outputs and eRev outputs are compared per period once both exist for the range." Sample world: WLD-T-21 Feb 2023 onward; no figures asserted.

#### 5.6.8 Data extracts

Extracts are CSV datasets with a JSON manifest for BI tools (REQ-RPT-028). One specification table covers the nine codes; the SF-08:report view renders the first 200 rows of a JSON run as a preview grid whose columns are the dataset columns.

| Parameter key | Label | Control | Default | Validation copy |
|---|---|---|---|---|
| `mode` | "Extract" | segmented "Full as of a snapshot", "Changes known since" (`FULL`, `INCREMENTAL`) | `FULL` | none |
| `entity_codes`, `book` | context | context pill | context; `book` absent for `extract_contracts`, `extract_events` | none |
| `period_lock_id` or `known_at` | "Source" | RV-04 (full) | lock of the context period when locked, else now | none |
| `known_since` | "Changes known since" (incremental) | timestamp | the `known_at` of the user's previous run of the same extract | "Enter a time before the source time." |

| RPT | Code | Rows | Columns (dataset schema version 1) | Control totals |
|---|---|---|---|---|
| RPT-45 | `extract_contracts` | T-CON-01 rows in scope | Every T-CON-01 column except `tenant_id`, in table order, plus `customer_code`, `contracting_entity_code`; `custom_attributes` as canonical JSON | `row_count` |
| RPT-46 | `extract_obligations` | Obligation versions of the latest contract version per book known at the source time | Every T-CON-11 column except `tenant_id` and `trace_nodes`, plus `contract_external_id` | `row_count`; `allocated_amount`, `revenue_cum` sums per currency |
| RPT-47 | `extract_contract_versions` | T-CON-08 rows known at the source time | Every T-CON-08 column except `tenant_id`, plus `contract_external_ids` (member contracts) | `row_count` |
| RPT-48 | `extract_schedule_lines` | T-ENG-02 rows of the latest versions | Every T-ENG-02 column except `tenant_id`, plus `contract_external_id`, `period_key` | `row_count`; `amount` sum per currency |
| RPT-49 | `extract_subledger_lines` | T-SL-04 rows with `recorded_at ≤` source time | Every T-SL-04 column except `tenant_id`, plus `contract_external_id`, `period_key`, `origin_period_key`, `gl_account_code` | `row_count`; `amount_functional` sum per functional currency (0.00 per entity, book, currency, period by D-16) |
| RPT-50 | `extract_journal_lines` | T-SL-09 rows of non-cancelled runs | Every T-SL-09 column except `tenant_id`, plus `je_no`, `run_no`, `batch_external_id`, `period_key` | `row_count`; `debit_functional`, `credit_functional` sums per functional currency |
| RPT-51 | `extract_balances` | T-CON-09 rows of the latest versions | Every T-CON-09 column except `tenant_id`, plus `contract_external_id`, `entity_code` | `row_count`; `contract_liability_functional`, `contract_asset_functional`, `unbilled_receivable_functional` sums per currency |
| RPT-52 | `extract_events` | T-CON-05 rows with `recorded_at ≤` source time | Every T-CON-05 column except `tenant_id`; `payload` as canonical JSON | `row_count` |
| RPT-53 | `extract_legacy_contract_live` | 04 §17.1 rule 1 over all dates (history rows) | The 71 legacy columns of 04 §17.2 in order with the RPT-10 format rules | `row_count` |

Rules: incremental mode selects rows whose `created_at` (or `recorded_at` for events and subledger lines) is after `known_since` and at or before the source time; manifest `{dataset, schema_version, mode, known_since, known_at, period_lock_id, row_count, control_totals, sha256}`; CSV values follow DS-FMT-25 (signed decimal strings, ISO dates, ISO 8601 UTC timestamps); columns holding personal data are never added (REQ-SEC-007). Tie-outs: none. Empty copy (all extracts): "No rows in <extract name> for these parameters." Formats CSV and JSON only. Sample world: WLD-T-01 full extracts as locked Aug 2026 contain the 180 background contracts plus the key contracts in scope; counts are not asserted (WLD-R-06).

## 6. Evidence packs, auditor requests and the audit log (SF-09)

### 6.1 SF-09 Evidence packs and auditor requests

| Field | Value |
|---|---|
| Screen id | SF-09 |
| Route | `/reports/evidence` (RT-35) with `entity`, `period`, `book`, `f.kind`, `f.status` |
| Roles and permissions | Read `report.run` (RT-35). Generate and download packs: `evidence.export` (Controller, Auditor). Every read and download writes an audit event (PP-03; J-17-AC-4) |
| Purpose | Let auditors self-serve research 07 requests A-01 to A-20 from locked data, and list, generate and download evidence packs with per-file hashes |
| REQ | REQ-RPT-014, 015; REQ-PLT-019; research 07 §7 (A-01 to A-20), F-20 |
| Journeys | J-17.2, J-17.4, J-17-AC-1, J-17-AC-4 |

**Wireframe, 1440 px (viewer `hannah`).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Reports                                                                                                              |
| Catalogue   Evidence packs   Audit log   Scenarios and forecasts                                                     |
+----------------------------------------------------------------------------------------------------------------------+
| Auditor requests (20)                                                                         Read-only access       |
| A-01  Complete revenue JE population, tied to GL           Journal entry population        [Run report]              |
| A-02  Revenue waterfall by contract and obligation         Revenue waterfall (as locked)   [Open]                    |
| A-04  Contract-to-schedule tie-out for samples             Contract sample pack            [Generate pack]           |
| ...                                                                                                                  |
| A-17  SOC 1 Type II report and bridge letter               Provided outside eRev Cloud     —                         |
+----------------------------------------------------------------------------------------------------------------------+
| Evidence packs (6)                                                                        [*Generate evidence pack v]|
| Pack        Kind             Entity  Book     Period    Status       Files  Manifest SHA-256   Created                |
| EVP-000014  Close            AVM-US  ASC 606  Sep 2026  (Succeeded)    21   7d0a91c3…ee10    02 Oct 2026 10:04 UTC  |
| EVP-000015  Contract sample  AVM-US  ASC 606  —         (Succeeded)     9   41bb02d7…1a9c    12 Sep 2026 16:40 UTC  |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** "Auditor requests" shows the Source column under the request text; the packs grid hides "Book" and "Created" (column chooser).

```text
+--------------------------------------------------------------------------------------------------------+
| Auditor requests (20)                                                                                  |
| A-01 Complete revenue JE population, tied to GL · Journal entry population            [Run report]     |
| Evidence packs (6)                                                         [*Generate evidence pack v] |
| EVP-000014  Close  AVM-US  Sep 2026  (Succeeded)  21  7d0a91c3…ee10                                     |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.**

| Region | Components | Content |
|---|---|---|
| Area header | DS-CMP-06; DS-CMP-07 route tabs | `h1` "Reports"; "Evidence packs" tab active |
| Auditor requests | DS-CMP-10 static table (20 rows) | Table below |
| Evidence packs | DS-CMP-10 DataGrid; DS-CMP-28 menu "Generate evidence pack" | T-RPT-04 rows |
| Generate forms | DS-CMP-11 form modals (one per kind) | Fields below |

**Auditor requests** (research 07 §7; the request text is copy):

| A id | Request | Source in eRev Cloud | Action |
|---|---|---|---|
| A-01 | "Complete revenue JE population, tied to GL" | RPT-15 `je_population` | "Run report" |
| A-02 | "Revenue waterfall by contract and obligation, tied to GL revenue" | RPT-01 on SF-04, as locked | "Open" |
| A-03 | "Contract population: new contracts and modifications with key terms" | RPT-45 `extract_contracts`; RPT-14 `modification_register` | "Run report" (menu of both) |
| A-04 | "Contract-to-schedule tie-out for samples" | RPT-55 `contract_sample_pack` | "Generate pack" |
| A-05 | "SSP study, version history, approvals and application" | RPT-19, RPT-20, RPT-21, RPT-22 | "Run report" (menu) |
| A-06 | "Modification listing with classification and catch-up" | RPT-14 | "Run report" |
| A-07 | "Variable consideration estimates and revenue from prior-period obligations" | RPT-29; RPT-05 | "Run report" (menu) |
| A-08 | "Contract balance rollforward and revenue from the opening contract liability" | RPT-03; RPT-04 | "Run report" (menu) |
| A-09 | "RPO by contract and time band, expedients and rollforward" | RPT-06; RPT-07 | "Run report" (menu) |
| A-10 | "Disaggregation tied to total revenue" | RPT-08 | "Run report" |
| A-11 | "Cutoff: events near period end and late entries" | RPT-17; RPT-16 | "Run report" (menu) |
| A-12 | "Manual adjustments and overrides with approvals" | RPT-18 | "Run report" |
| A-13 | "Billing-to-subledger and subledger-to-GL reconciliations with sign-offs" | SF-05:reconciliations of the context period; included in the period evidence pack | "Open" |
| A-14 | "Contract asset, unbilled receivable and contract liability aging" | RPT-36 | "Run report" |
| A-15 | "User listing, role matrix, SoD conflicts and access review evidence" | RPT-24; RPT-25; evidence pack kind `ACCESS` | "Run report" (menu with "Generate access pack") |
| A-16 | "Configuration change log and release manifest" | RPT-23; evidence pack kind `CHANGE` | "Run report" (menu with "Generate change pack") |
| A-17 | "SOC 1 Type II report and bridge letter" | "Provided outside eRev Cloud" (REQ-CTL-009, later) | none; the row states "Service organization reports are not part of eRev Cloud 1.0." |
| A-18 | "IPE documentation and report run register" | SF-08:runs; the IPE documentation drawer of each report | "Open" |
| A-19 | "Audit trail for selected contracts and chain integrity" | SF-09:audit-log; RPT-44 | "Open" |
| A-20 | "Walkthrough access to trace one transaction end to end" | The Auditor role (read-only) with Explain and drill-down; SF-09:audit-log filtered to the viewer's own actions | "Open" with the note "Your reads and exports are logged." |

Each action opens its target with the context entity, book and period; for a closed context period the target defaults to "As locked" (RV-04).

**Data bindings.** `GET /evidence-packs?entity&book&period&count=true` (04 API-R-42 filters); `POST /evidence-packs` `{kind, entity_code, book, period_key, period_lock_id, contract_external_ids, from_date, to_date, as_of}` (202; job `EVIDENCE_PACK`; header `X-Erev-Evidence-Pack-Id`; 04 API-S-EvidencePackCreate, whose required fields per kind the generate forms enforce; OQ-B-10 resolved by D-76); `GET /evidence-packs/{id}/download`. Filtering the pack list by kind or status is deferred to later, because 04 API-R-42 defines no `kind` or `status` filter.

**Grid columns: evidence packs.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Pack | `pack_no` | mono link | SF-09:pack |
| Kind | `kind` | outline chip "Close", "Contract sample", "Change", "Access" (E-66) | none |
| Entity | `entity.code` | mono; em dash | none |
| Book | `book` | label | none |
| Period | `period` → label | DS-FMT-19; em dash | SF-05 |
| Lock | `period_lock_id` | mono prefix | SF-05:history |
| Contracts | `contract_ids` → external ids | mono joined with ", " (contract sample packs) | SF-03 |
| Status | `status` | E-67 chip | none |
| Files | `manifest.files` count | integer | SF-09:pack |
| Manifest SHA-256 | `manifest_sha256` | prefix with copy | none |
| Created by | `created_by` | user or "System" (packs generated at lock) | none |
| Created | `created_at` | DS-FMT-17 | none |
| Actions | none | "Download" (`evidence.export`) | none |

**States.**

| State | Copy |
|---|---|
| Packs SCR-ST-03 | Title "No evidence packs yet"; description "A close evidence pack is generated when a period is locked. Generate contract sample, change or access packs on demand." |
| Running pack | Pinned row with chip Running and DS-CMP-24 "Building evidence pack <pack no>" |
| SCR-ST-05 | "Could not load evidence packs" |

**Interactions, keyboard and copy.** *Generate evidence pack* menu items: "Period evidence pack", "Contract sample pack", "Change evidence pack", "Access evidence pack". Forms (DS-CMP-11 form modal):

| Kind | Fields | Buttons and toast |
|---|---|---|
| Period (`CLOSE`) | "Entity" (select), "Book", "Period" (period select; closed periods show "As locked"), "Source" (segmented "As locked" / "Current"; As locked only for closed periods) | "Cancel", "Generate pack"; toast "Building evidence pack <pack no>." |
| Contract sample (`CONTRACT_SAMPLE`) | "Contracts" (multi-select combobox by external id, at most 25), "As of period" | as above |
| Change (`CHANGE`) | "From", "To" (dates) | as above |
| Access (`ACCESS`) | "As of" (timestamp) | as above |

Download starts `GET /evidence-packs/{id}/download` (ZIP) and toasts "Downloaded <pack no>. Verify files against manifest.json."

**Sample world.** J-17.2 (asserted): `hannah` downloads the AVM-US Sep 2026 close pack generated at re-lock; ZIP with `manifest.json`; every file SHA-256 matches; the pack includes both lock ids and the re-lock diff report. J-17.4 (asserted): `hannah` generates the contract sample pack for `PRJ-CB-2026-01`.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Auditor requests | table named "Auditor requests (20)" | `SF-09-grid-auditor-requests` |
| Request row | row header "A-01" … "A-20" | `SF-09-row-a-01` … `SF-09-row-a-20` |
| Packs grid | grid named "Evidence packs" | `SF-09-grid-packs` |
| Pack row | row header "<pack no>"; tests filter by kind, entity and period | `SF-09-row-<kind normalised>-<entity code normalised>-<period_key normalised>` (for example `SF-09-row-close-avm-us-fy2026-p09`) |
| Generate menu | button named "Generate evidence pack" | none |

**Light and dark.** Outline chips and hash prefixes.

**Accessibility.** The A-17 row's missing action is announced through its text; action menus follow DS-CMP-28.

### 6.2 SF-09:pack Evidence pack

| Field | Value |
|---|---|
| Screen id | SF-09:pack |
| Route | `/reports/evidence/:packId` (RT-36) |
| Roles and permissions | Read `report.run`; download `evidence.export` |
| Purpose | Show one pack's scope, lock hashes and manifest with per-file SHA-256, and download the pack and manifest |
| REQ | REQ-RPT-014, 015; CTL-041 |
| Journeys | J-17.2, J-17.4, J-13-AC-6 |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Reports > Evidence packs > EVP-000014                                                                                 |
| Evidence pack EVP-000014   (Succeeded)  <Close>                               [Download manifest]  [*Download pack]  |
| Entity AVM-US · Book ASC 606 · Period Sep 2026 · Lock 8b10…aa42 (re-lock) · Previous lock 4f2a…91c0                   |
| Snapshot manifest 8b10c3e2…aa42 · Manifest SHA-256 7d0a91c3…ee10 · Created by System · 02 Oct 2026 10:04 UTC         |
| [i] Recompute each file's SHA-256 and compare it with manifest.json to verify the pack.                               |
+----------------------------------------------+-------------------+---------------+-------------------------------------+
| File                                          | Report run        | Bytes         | SHA-256                             |
| certification.json                            | —                 | 3,412         | 51c0e8aa…90d1                       |
| journals/batch_register.csv                   | RPT-000418        | 18,204        | 0b7fe211…4c2e                       |
| relock/variance_between_closes.xlsx           | RPT-000419        | 22,871        | e3a1d6f4…77b0                       |
| ...                                                                                                                  |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** Bytes column moves into the tooltip of the file name.

```text
+--------------------------------------------------------------------------------------------------------+
| Evidence pack EVP-000014 (Succeeded) <Close>                   [Download manifest] [*Download pack]     |
| File                                   Report run    SHA-256                                           |
| certification.json                     —             51c0e8aa…90d1                                     |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-06 record header (pack variant); DS-CMP-29 info banner; DS-CMP-10 DataGrid "Files"; static table "Contents" (expected sections and whether present).

**Data bindings.** `GET /evidence-packs/{id}` (`manifest.files[] {path, sha256, bytes, report_run_id}`); `GET /evidence-packs/{id}/download`; manifest `GET /files/{manifest file}/content` through the "Download manifest" action.

**Grid columns: files.** "File" (`path`, mono); "Report run" (`report_run_id` → run no, mono link SF-08:run); "Bytes" (integer); "SHA-256" (prefix with copy and full value in tooltip). Sort by `path`.

**Contents** (the period pack must list every REQ-RPT-014 item; missing items render chip Difference "Missing"):

| Content (copy) | Expected path prefix (04 T-RPT-04 manifest layout; OQ-B-11 resolved by D-76) | Source |
|---|---|---|
| "Close certification" | `certification.json` | `period_lock.certification` |
| "Lock snapshot ids and hashes" | `lock/snapshots.json` | T-CLS-05 rows |
| "Journal batch register with balancing and completeness" | `journals/` | RPT-15 and batch register |
| "Reconciliations with sign-offs" | `reconciliations/` | T-CLS-06, T-CLS-08 |
| "Rollforwards" | `reports/contract_balance_rollforward.*`, `reports/rpo_rollforward.*` | RPT-03, RPT-07 |
| "RPO and disaggregation" | `reports/rpo.*`, `reports/disaggregation.*` | RPT-06, RPT-08 |
| "Registers: manual adjustments, modifications, SSP, configuration" | `registers/` | RPT-18, RPT-14, RPT-19, RPT-23 |
| "Late-entry and out-of-period reports" | `registers/late_entries.*`, `registers/out_of_period.*` | RPT-17, RPT-16 |
| "User listing and SoD report as of period end" | `access/` | RPT-24, RPT-25 |
| "Audit chain digest" | `audit/chain_digest.json` | T-PLT-23 digest |
| "Re-lock diff report" (re-lock packs only) | `relock/` | RPT-38 |
| "Manifest" | `manifest.json` | T-RPT-04 manifest |

Contract sample pack contents (REQ-RPT-015): "Contract versions and source documents", "Allocation walk", "Schedule", "Events", "Journal lines", "Approvals", "Audit-log slice", as a stamped PDF and XLSX per contract.

**States.** Running: DS-CMP-24 "Building evidence pack <pack no>" with files counted as they are written. Failed: SCR-ST-12 "Building evidence pack <pack no> failed. Nothing was published." SCR-ST-07: "Evidence pack not found".

**Interactions, keyboard and copy.** "Download pack" and "Download manifest" per §6.1; copy buttons named "Copy SHA-256 of <path>".

**Sample world.** J-17.2 (asserted): re-lock pack for AVM-US Sep 2026 lists both lock ids and the re-lock diff; J-13-AC-6: the lock pack contains every REQ-RPT-014 item with per-file SHA-256 in `manifest.json`. J-17.4: contract sample pack for `PRJ-CB-2026-01` with PDF and XLSX including the J-06, J-10 and J-14 decisions.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Evidence pack <pack no>" | `SF-09-page` |
| Files grid | grid named "Files" | `SF-09-grid-pack-files` |
| File row | row header "<path>" | `SF-09-row-<path normalised>` (for example `SF-09-row-manifest-json`) |
| Contents table | table named "Contents" | `SF-09-grid-pack-contents` |

**Light and dark.** Mono paths and hash prefixes on `--bg-surface`.

**Accessibility.** Hash prefixes have full accessible names (DS-A11Y-12).

### 6.3 SF-09:audit-log Audit log

| Field | Value |
|---|---|
| Screen id | SF-09:audit-log |
| Route | `/reports/audit-log` (RT-37) with `f.object`, `f.object_type`, `f.actor`, `f.action`, `f.outcome` (`is:` or `in:` over `SUCCESS`, `DENIED`, `FAILED`; rev 1.57, item AUD-SCREEN-BIND-1 — it waited for the outcome filter of API-R-10, on main with 04 rev 1.154), `f.occurred` (`between:<date>,<date>`, UTC days) and `drawer=event` with `event=<chain sequence>` (SCREENS.md SCR-URL-32, rev 1.20; rev 1.45: the event's chain sequence, was its id) |
| Roles and permissions | Read `audit.read` (Revenue Accountant, Revenue Reviewer, Controller, Integration Admin, Tenant Admin, Auditor). "Verify chain now": `audit.read`. Export: `report.export` (RPT-43). Rev 1.68 (SCREENS.md SCR-PERM-01, SCR-PERM-02; supervisor ruling R-28): the log is a list of the whole workspace, read with `audit.read` held for all entities |
| Purpose | Search the hash-chained audit log with field-level diffs, verify the chain on demand and export the log |
| REQ | REQ-PLT-018, 019, 020; REQ-MIG-001 (migrated rows are not audit events); research 07 AU-01, AU-03, A-19; CTL-038, CTL-039 |
| Journeys | J-17.5, J-17.7 (denied outcome), J-20-AC-3, J-22-AC-1 |

**Wireframe, 1440 px (J-17.5).**

```text
+-----------------------------------------------------------------------------------+----------------------------------+
| Reports                                                                           | Event 9,104                  [X] |
| Catalogue   Evidence packs   Audit log   Scenarios and forecasts                  | modification.approve · Succeeded |
+-----------------------------------------------------------------------------------+ 10 Sep 2026 15:22:41 UTC         |
| [shield] Audit chain verified 12 Sep 2026 02:00 UTC · 9,112 events   [Verify chain now] | Actor Priya Raman (Revenue  |
| [Object is PRJ-CB-2026-01 x] [Filter]                          Export v                |   Reviewer) · MFA Yes        |
| Seq    Occurred                Actor         Action                  Object    Outcome| Object modification MOD-000… |
| 9,104  10 Sep 2026 15:22:41 UTC Priya Raman  modification.approve     MOD-0…   (Succ.)| Field      Current  Proposed |
| 9,097  10 Sep 2026 14:05:02 UTC Maya Chen    modification.submit      MOD-0…   (Succ.)| − status   Submitted         |
| ...                                                                                   | + status            Approved |
+---------------------------------------------------------------------------------------+ Comment "…"                  |
                                                                                        | HMAC 1a09…7c21 · prev 88e0…  |
                                                                                        +------------------------------+
```

**Wireframe, 1280 px.** The event drawer overlays the grid; the Roles and Request id columns are hidden by default.

```text
+--------------------------------------------------------------------------------------------------------+
| [shield] Audit chain verified 12 Sep 2026 02:00 UTC · 9,112 events              [Verify chain now]      |
| [Object is PRJ-CB-2026-01 x] [Filter]                                                    Export v       |
| 9,104  10 Sep 2026 15:22:41 UTC  Priya Raman  modification.approve  MOD-…  (Succeeded)                  |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Verification header: DS-CMP-12 audit-variant header (ShieldCheck; negative banner "Audit chain verification failed at event <n>" with link "Open verification details" when the latest result failed). FilterBar DS-CMP-13. Events: DS-CMP-10 DataGrid. Event drawer: DS-CMP-09 docked panel with a DS-CMP-16 field diff (inline and table variants), comment block, detail JSON (mono) and chain values. Rev 1.36: the header shows the E-98 chip and "Audit chain verified <DS-FMT-17 timestamp> · <n> events" as a link to SF-09:verification, the link "Verification history" (RPT-44; holders of `report.run`) and "Verify chain now"; before the first verification it reads "The audit chain has not been verified yet." The drawer holds, in this order: the action (mono) with the outcome chip and the instant with seconds; actor, role codes, sign-in method and MFA; the object; the table "Changes (<n>)" with the changed fields only, read from the event's `diff` (for a creation or a removal, every leaf of the one document), or "This event recorded no field changes."; the comment; the detail as JSON; and "Recorded values": HMAC, previous HMAC, key id, request id, event id and, where the event carries them, the object id, the on-behalf-of id, the API client id, the support grant id and the source address — system ids and hashes in the DS-FMT-23 form with a copy button. Rev 1.45: after MFA the drawer shows "On behalf of" with the name of the principal a system step acted for, where the event names one. Values are shown as recorded; the API redacts credential keys to "[REDACTED]". Rev 1.57 (item AUD-SCREEN-BIND-1): the drawer opens at once on the sequence of its link — an event the loaded rows hold fills it directly, another is read alone and the drawer shows SCR-ST-01 under its title until the event arrives. The object reads "<type in words> <label>" with the label linked as in the grid, or the type in words alone where the event carries no label; the actor's name links to SF-14:user as in the grid. A member is listed as a change only when it differs: a member that is null (or absent) before and null (or absent) after is not listed — such a row read "Added" — and a creation or a removal lists the leaves that hold a value.

**Data bindings.** `GET /audit-events?object_type&contract_id&actor_id&action&outcome&from&to&count=true` (API-R-10; rev 1.57: `contract_id` and `outcome` join and `object_id` is no longer sent; the object filter resolves a business id through the contract search); `GET /audit-events?chain_seq=<n>&limit=1` for an `event` link whose sequence the loaded rows do not hold (rev 1.57); `GET /audit-events/actors?from&to` for the options of the actor filter (rev 1.57); `GET /audit-events/verifications?limit=1` for the header; `POST /audit-events/verify` (202; job `AUDIT_CHAIN_VERIFY`); export RPT-43. Saved-view code `SF-09:audit-log`.

**Range (rev 1.36).** Every read of the log carries `from` and `to`: `audit_event` is partitioned by month (04 PT-MOC) and a read without a time bound probes every partition. Without `f.occurred` the screen reads the last 30 days through today in UTC (`from` = 00:00:00Z of the day 30 days before today, inclusive; `to` = 00:00:00Z of the day after today, exclusive) and states that range in a caption under the filter chips: "Showing the last 30 days, <from> – <to> (UTC). Add the Occurred filter to read another range." A chosen `f.occurred=between:<date>,<date>` replaces it (presets "Last 7 days", "Last 30 days", "Last 90 days", "Last 365 days", or a custom range): `from` = the start of the first day, `to` = the start of the day after the last day. The default range never reaches the URL or a saved view: a saved view stores raw `f.*` values, so a written default would freeze two absolute dates in every view saved from the default state. 30 days is the span RPT-44 and the SF-08 recent runs use. Rev 1.57 (item AUD-SCREEN-BIND-1): two reads carry no time bound, because an index answers them at any age (04 §16.14). The trail of a contract is read whole: with `f.object` and without `f.occurred` the screen sends neither `from` nor `to`, and the caption reads "Showing every event that names <value>. Add the Occurred filter to narrow the range."; with `f.occurred` the trail is read over that range and no caption shows. One event by its sequence (`chain_seq`) is read without a range and without the filters of the list. Every other read keeps the rule above, and the 30 days are sent explicitly although the API would apply them itself, so that the caption and the read agree.

**Bindings to API-R-10 of 1.0 (rev 1.36; item AUD-API-GAPS-1).** Bound: `f.object_type` → `object_type` (typed words are read as the table name: "Contract hold" is `contract_hold`); `f.actor` → `actor_id`, with the viewer and the actors of the rows the list has loaded as options (`GET /users` needs `user.manage`, which the Auditor does not hold); `f.action` → `action`; `f.object` → `object_type=contract` with the `object_id` of the contract whose external id or contract number equals the value, found through `GET /contracts?q=` (the filter is offered to holders of `contract.read`; a value no contract has lists nothing, with the line "No contract has the external id or number <value>."). The list has no quick search (the route answers `q` with 422). Waiting for the API, and not approximated in the client: (1) an outcome filter (`f.outcome`); (2) the events of a contract across its object types — the modification and estimate events of J-17.5 carry their own object ids, so the object filter lists the events recorded on the contract itself; (3) a business label of the event's object; (4) the name behind `on_behalf_of_id`, and the name of an API client or an operator in API-S-Actor; (5) an event by id or chain sequence, so that an `event` link opens whatever the list has loaded. Rev 1.45: point (4) is bound — the API answers API-S-Actor for `actor` of every kind and for `on_behalf_of` (04 rev 1.139; item AUD-ACTOR-BIND-1); point (5) is settled as the `chain_seq` filter of `GET /audit-events` (lane API-GAPS G-2), which the `event` link reads when it is on main; points (1) to (3) wait. The "Export" menu (RPT-43) renders for holders of `report.run` and `report.export` and passes the range and the bound filters as run parameters. Rev 1.57 (item AUD-SCREEN-BIND-1; 04 rev 1.154, lane API-GAPS G-2 on main): points (1), (2), (3) and (5) are bound, and the actor's drill and the names of the actor filter with them. (1) `f.outcome` → `outcome`, one parameter per chosen literal; the editor offers "Succeeded", "Denied" and "Failed". (2) `f.object` → `contract_id` of the contract the value names, found as before through `GET /contracts?q=`: the list is the trail of that contract — every event that names it, whatever its object type, so the modification and estimate events of J-17.5 are listed — and `f.object_type` narrows it when both are set; `object_type=contract` with `object_id` is no longer sent. (3) The Object cell and the drawer show `object_label` (Grid columns). (5) An `event` link whose sequence the loaded rows do not hold is read alone by `GET /audit-events?chain_seq=<n>`, at any age and whatever the filters of the list; the banner of an unknown event remains for a value no event answers (States). `f.actor`: the options are the principals who acted in the range on screen — `GET /audit-events/actors` with the `from` and `to` of the list, and for a trail read whole without either, which the API reads as its own last 30 days — named as the Actor column names a principal; the viewer is an option when he or she acted in that range (was: the viewer and the actors of the loaded rows). The API answers at most 100 names in name order: when it says the range holds more (`is_truncated`), a line under the chips reads "Actor filter: showing the first <n> who acted in this range.", and a name outside them is reached by narrowing the range with the Occurred filter; the screen does not search the server (`q` is not sent). An actor the link names and the range does not hold keeps its chip under the label "another member". Export (RPT-43): the report takes `from`, `to`, `object_type`, `object_id`, `actor_id` and `action`, and neither `contract_id` nor `outcome`; with an Object or an Outcome chip its rows would not be the rows of the list, so the "Export" button is then unavailable with the reason "The export cannot apply the Object or Outcome filter. Remove that filter to export." — until RPT-43 takes the two parameters (owed by the report's owner). With the other chips the menu passes the range, `object_type`, `actor_id` and `action` as before.

**Grid columns.**

| Header | Field | Format | Drill | API-R-10 of 1.0 (rev 1.36) |
|---|---|---|---|---|
| Sequence | `chain_seq` | integer | event drawer | Bound |
| Occurred | `occurred_at` | DS-FMT-17 with seconds | none | Bound |
| Actor | `actor_id` display name; `actor_kind` "System", API client name, or "Operator <name> under support grant" | user cell | SF-14:user | Bound (rev 1.45; item AUD-ACTOR-BIND-1): a person by display name, "System", an API client by its name and an operator as "Operator <name> under support grant", from `actor.display_name` (04 §16.14). The drill waits (the event carries a user id, SF-14:user takes a membership id). Rev 1.57: the drill is bound — the name links to SF-14:user (`/settings/users/<actor_membership_id>`) for a holder of `user.manage` when the event carries the membership; the system, an API client, an operator and a removed member carry none and stay text, as does every name for a reader without `user.manage`. Enter on the cell opens the link and, where the cell shows none, the event drawer |
| Roles | `actor_roles` | role codes (mono) | none | Bound; hidden by default |
| Action | `action` | mono, with the catalogue verb in the tooltip (`audit.action.<action>`) | none | Bound; the tooltip where the catalogue holds the verb |
| Object type | `object_type` | text | none | Bound: the table name in words ("Import upload") |
| Object | object label from `object_type` and `object_id` | mono link | the object's screen | Waits for the label. The cell shows the type in words as a link to the record's screen for `contract`, `approval_request`, `import_upload` and `journal_run` (screens that open from the id) and no value for other types; no record is read for a label. Rev 1.53: `report_run` joins them, linked to SF-08:run. Rev 1.57: bound — the cell shows `object_label`, the business identifier the API reads with the event (04 §16.14 "Object label"): an identifier in the identifier face (DS-FMT-23), a name — of a member, a user, an API client, a review campaign, a calculator run or a mapping version — in the text face; as a link to the record's screen for the five types above, as text for every other type. An event without a label — a type the API labels none, an event without an object id, a row that is gone, a row the reader's access does not show — keeps the cell of rev 1.53 (the type in words as a link for the five types, no value otherwise), and nothing on the screen says whether a label exists. Default width 232 px: a composed label ("AVM-US · FY2026-P09 · ASC606") stays whole. Enter on the cell opens the link and, where the cell shows none, the event drawer |
| Outcome | `outcome` | chips "Succeeded" (`SUCCESS`, positive), "Denied" (`DENIED`, negative XCircle), "Failed" (`FAILED`) | none | Bound |
| Reason | `reason_code` | mono | none | Bound |
| MFA | `mfa_verified` | "Yes" / "No" | none | Bound |
| On behalf of | `on_behalf_of` (API-S-Actor of `on_behalf_of_id`; rev 1.37) | user or API client name | none | Bound (rev 1.45; item AUD-ACTOR-BIND-1): the name of the Actor, as the Actor column names a principal; no value where the event names nobody. The event drawer shows the name under "On behalf of" and the Actor's recorded id among "Recorded values" |
| Request id | `request_id` | mono prefix, `data-volatile` | none | Bound; hidden by default |

Sort keys (rev 1.36): Sequence (`chain_seq`; the default is newest first) and Occurred (`occurred_at`), the keys API-R-10 admits.

**States.**

| State | Copy |
|---|---|
| SCR-ST-03 | Title "No audit events from <from> to <to>" (rev 1.36: the default range, because the log is never read unbounded; was "No audit events"); description "Changes, approvals, runs, exports and sign-ins appear here with field-level before and after values." |
| SCR-ST-04 | "No audit events match these filters"; with an object id no contract has, the description "No contract has the external id or number <value>." (rev 1.36) |
| Event unknown (rev 1.57; was "Event not listed", rev 1.36) | Dismissible info banner "The link names no audit event of this workspace."; the drawer closes and `drawer` and `event` leave the URL. Shown when `event` is not a chain sequence (a positive integer without sign or leading zero, at most 15 digits; nothing is read for it) or when the workspace holds no event of that sequence. A sequence the loaded rows do not hold is no longer this state: it is read alone and opens (rev 1.45 kept the banner as an interim) |
| Event loading; event not read (rev 1.57) | The drawer "Event <sequence>" with SCR-ST-01 under its title while the event is read alone; when that read fails, the negative banner "Could not load the event" with the problem's title and "Retry" inside the drawer |
| Actor names (rev 1.57) | While they load, the editor of the Actor filter says "Loading options" (DS-CMP-13). More than the API answers: the line "Actor filter: showing the first <n> who acted in this range." under the chips. Not read: the line "Could not load the names of the Actor filter." with "Retry" under the chips |
| Export unavailable (rev 1.57) | With an Object or an Outcome chip the "Export" button is unavailable; its reason: "The export cannot apply the Object or Outcome filter. Remove that filter to export." |
| Verifying | DS-CMP-24 "Verifying the audit chain" in the header |
| Verification failed (latest) | Negative banner "Audit chain verification failed at event <n>. Open the verification details and follow the runbook." (NTF-09 body) |
| SCR-ST-06 | Access-limited state for users without `audit.read`. Rev 1.68: a holder of `audit.read` for named entities reads the same title with the description "The audit log covers every entity of the workspace. Ask a workspace administrator for a role that includes viewing the audit log for all entities.", and nothing is read; a read of the audit events refused with 403 renders that state in place of the page. Rev 1.99 (SCREENS.md §0.6 SCR-PERM-02 (c), rev 1.71): a description names the permission by its phrase and, in parentheses, its code, the word the Roles screen prints for it (§9.11): for a member without it "Ask a workspace administrator for a role that includes viewing the audit log (audit.read).", and for a holder for named entities "The audit log covers every entity of the workspace. Ask a workspace administrator for a role that includes viewing the audit log (audit.read) for all entities." |

**Interactions, keyboard and copy.** "Verify chain now": toast on success "Audit chain verified: <events checked> events, last chain value <prefix>." with action "View details" (SF-09:verification). Selecting a row opens the event drawer; `N` / `Shift+N` move between changes in the diff (DS-CMP-16). Migrated legacy rows never appear (BR-MIG-04). Rev 1.36: the sequence link, or Enter on a row, opens the drawer and writes `drawer=event&event=<chain sequence>` (rev 1.45; was the event's id); the event is one of the rows the list has loaded, and a sequence they do not hold is read alone by `GET /audit-events?chain_seq=<n>` (lane API-GAPS G-2; bound in rev 1.57, which ends the interim state "Event not listed"); the drawer closes with its Close button or with Esc while focus is inside it, and focus returns to the row. A verification that fails shows a negative toast with the banner's title and "View details"; a verification job that fails shows SCR-ST-12 in the header with "Retry".

**Sample world.** J-17.5 (asserted): filter object `PRJ-CB-2026-01` shows field-level diffs of the modification and estimate events; "Verify chain now" returns Verified with event count and last chain value; digest download. J-17.7: `hannah`'s refused approval decision appears with outcome Denied and actor Hannah Lindqvist. J-20-AC-3: the audit log contains only the migration commands of J-20.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Verification header | status "Audit chain verified …" | `SF-09-banner-chain` |
| Verify button | button named "Verify chain now" | none |
| Events grid | grid named "Audit events" | `SF-09-grid-audit-events` |
| Event drawer | complementary region named "Event <sequence>" | `SF-09-drawer-event` |
| Diff | table named "Changes (<n>)" | `SF-09-diff` |
| Event row (rev 1.36) | row of the grid | `SF-09-row-<sequence>` |
| Filter bar; saved-view selector (rev 1.36) | toolbar "Filters"; button "View: <name>" | `SF-09-filter-bar`; `SF-09-saved-view` |

**Light and dark.** Diff tints `--diff-removed-bg` and `--diff-added-bg` with markers in both themes (DS-COL-24).

**Accessibility.** Diff rows carry "Removed:", "Added:", "Changed:" prefixes (DS-CMP-16); timestamps have `time datetime`.

### 6.4 SF-09:verification Audit chain verification

| Field | Value |
|---|---|
| Screen id | SF-09:verification |
| Route | `/reports/audit-log/verifications/:verificationId` (RT-38; NTF-09 link) |
| Roles and permissions | Read `audit.read` |
| Purpose | Show one verification run's range, result, first failure and digest, and the recent verification history |
| REQ | REQ-PLT-020; CTL-039 |
| Journeys | J-17.5 |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Reports > Audit log > Verification                                                                                   |
| Audit chain verification   (Verified)                                                    [*Download digest]          |
| Trigger On demand · Started 12 Sep 2026 16:45:02 UTC · Finished 16:45:09 UTC · Sequences 1 – 9,112                   |
| Key figures   Events checked 9,112 │ First failure — │ Last chain value 1a09e4b2…7c21                                  |
+----------------------------------------------------------------------------------------------------------------------+
| Recent verifications                                                                         Open register >          |
| 12 Sep 2026 16:45 UTC  On demand  (Verified)  9,112 events                                                           |
| 12 Sep 2026 02:00 UTC  Scheduled  (Verified)  9,050 events                                                           |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** As 1440 px with the key figures wrapping.

```text
+--------------------------------------------------------------------------------------------------------+
| Audit chain verification (Verified)                                        [*Download digest]          |
| Events checked 9,112 │ First failure — │ Last chain value 1a09e4b2…7c21                                 |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-06 record header with KPI strip; DS-CMP-29 negative banner on failure; static table "Failure detail" (`failure_detail` keys and values); DS-CMP-10 static table "Recent verifications" (10 rows).

**Data bindings.** The verification is read by `GET /audit-events/verifications/{id}` (04 API-R-10, rev 1.154; rev 1.57, item AUD-SCREEN-BIND-1); 404 is SCR-ST-07. Until rev 1.57 the list was paged with `limit=50` until the id appeared, because 04 defined no detail route. Recent verifications: `GET /audit-events/verifications?limit=10`. Digest: `GET /files/{digest_file_id}/content`.

**Grid columns: recent verifications.** "Finished" (DS-FMT-17, link to that verification); "Trigger" ("Scheduled", "On demand"); "Result" (§0.4 E-98 chip); "Events checked" (integer); "First failure" (integer or em dash).

**States.** Failure: negative banner "Audit chain verification failed at event <first failure sequence>. Open the verification details and follow the runbook." with the failure detail table. SCR-ST-07: "Verification not found". Rev 1.68 (SCREENS.md SCR-PERM-02): the page opens for a holder of `audit.read` for any entity — ruling R-28 names the audit events and not this read; a read of the verification refused with 403 renders the access-limited state of §6.3 with its all-entities description in place of the page, not the error with "Retry", and is not sent again.

**Interactions, keyboard and copy.** "Download digest" downloads the digest file (last chain value, count, UTC time; REQ-PLT-020). "Open register" opens RPT-44. Rev 1.36: "Download digest" renders when the run has a digest (a run that failed stores none); "Open register" and the breadcrumb link "Reports" render for holders of `report.run`; in "Recent verifications" the run on screen is marked current and is not a link; the meta row reads "Sequences <from> to <to>". Rev 1.45: the banner of a failed run that names its first failure offers the link "Open event <first failure sequence>", which opens SF-09:audit-log with `drawer=event&event=<first failure sequence>` (§6.3).

**Sample world.** J-17.5: on-demand verification Verified with event count and last chain value; digest download.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Result chip | heading level 1 "Audit chain verification" region | `SF-09-kpi-strip` |
| Failure banner | alert "Audit chain verification failed …" | `SF-09-banner-verification-failed` |
| Recent verifications | table named "Recent verifications" | `SF-09-grid-verifications` |

**Light and dark.** Negative banner on `--bg-canvas`.

**Accessibility.** The failure banner is `role="alert"` only when inserted after load (DS-CMP-29).

## 7. Scenarios, forecasts and the deal-desk allocation preview (SF-17, SF-18)

### 7.1 SF-17 Scenarios and forecasts

| Field | Value |
|---|---|
| Screen id | SF-17 |
| Route | `/reports/forecasts` (RT-39) |
| Roles and permissions | Read `scenario.use` (Revenue Accountant, Controller, custom role "Deal desk analyst"). "New scenario", "Refresh scenario", "New forecast event set", "Run forecast": `scenario.use`. "Archive scenario": the scenario's creator or a Controller (SM-14) |
| Purpose | In a production workspace, create, open, refresh and archive scenario workspaces; in a scenario workspace, manage forecast event sets and forecast runs |
| REQ | REQ-FC-001 to 005, 007; REQ-PLT-003, 022, 023; BR-FC-01 to 03 |
| Journeys | J-18.1 to J-18.4, J-18-AC-3, J-18-AC-4 |

The page renders one of two variants by tenant kind (`X-Erev-Tenant-Kind`): **production** (scenarios) or **sandbox with a scenario** (event sets and runs). A sandbox without a scenario (a sandbox copy of SF-15:sandbox) renders the production variant's empty state with the note "Scenarios are created from a production workspace."

**Wireframe, 1440 px (production variant, viewer `jordan`).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Reports                                                                                                              |
| Catalogue   Evidence packs   Audit log   Scenarios and forecasts                                                     |
+----------------------------------------------------------------------------------------------------------------------+
| Scenarios (1)                                                                                         [*New scenario] |
| Name               Purpose               Status     Known at               Last refreshed        Created by    ...    |
| Q4 2026 outlook    Q4 revenue outlook    (Active)   12 Sep 2026 17:02 UTC  —                     Jordan Blake  ...    |
|                                                                                                   [Open scenario]    |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1440 px (scenario variant, WLD-T-30).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Sandbox: Q4 2026 outlook (Scenario). Nothing here posts or exports.                                                  |
| Reports                                                                                                              |
| Catalogue   Evidence packs   Audit log   Scenarios and forecasts                                                     |
+----------------------------------------------------------------------------------------------------------------------+
| Forecast event sets (1)                                                                  [New forecast event set]    |
| Name        Code     Version  Status       Inputs   Updated                                                          |
| Q4 base     Q4-BASE  v1       (Published)  1        12 Sep 2026 17:20 UTC                                            |
+----------------------------------------------------------------------------------------------------------------------+
| Forecast runs (1)                                                                                  [*Run forecast]   |
| Event set     Horizon                 Status       Started                Finished               Outputs             |
| Q4 base v1    Oct 2026 – Dec 2026     (Succeeded)  12 Sep 2026 17:24 UTC  12 Sep 2026 17:25 UTC  Open >              |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** Both variants hide "Purpose" and "Created by" (column chooser); regions keep their order.

```text
+--------------------------------------------------------------------------------------------------------+
| Forecast event sets (1)                                                   [New forecast event set]     |
| Q4 base  Q4-BASE  v1  (Published)  1 input                                                             |
| Forecast runs (1)                                                                  [*Run forecast]     |
| Q4 base v1  Oct 2026 – Dec 2026  (Succeeded)  Open >                                                   |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Area header with DS-CMP-07 route tabs; DS-CMP-10 DataGrids "Scenarios", "Forecast event sets", "Forecast runs"; DS-CMP-11 form modals "New scenario", "New forecast event set", "Run forecast"; DS-CMP-24 job progress for scenario creation and refresh; DS-CMP-29 sandbox banner (SCR-ST-11).

**Data bindings.** Production: `GET /scenarios`; `POST /scenarios` `{name, purpose, known_at}` (202; job `TENANT_SNAPSHOT`); `POST /scenarios/{id}/refresh` (202); `POST /scenarios/{id}/archive`; open scenario `POST /session/tenant` `{tenant_id: scenario_tenant_id}` (SCREENS.md §1.3 switcher behaviour). Scenario: `GET /forecast-event-sets`; `POST /forecast-event-sets` `{code, name}`; `GET /forecast-runs`; `POST /forecast-runs` `{forecast_event_set_id, parameters: {horizon_periods, entity_ids, book_code}}` (202; job `FORECAST_RUN`).

**Grid columns.**

| Grid | Header | Field | Format | Drill |
|---|---|---|---|---|
| Scenarios | Name | `name` | text | "Open scenario" |
| Scenarios | Purpose | `purpose` | text | none |
| Scenarios | Status | `status` | §0.4 E-100 chip | none |
| Scenarios | Known at | `base_known_at` | DS-FMT-17 | none |
| Scenarios | Last refreshed | `last_refreshed_at` | DS-FMT-17; em dash | none |
| Scenarios | Created by | `created_by` | user | none |
| Scenarios | Actions | none | "Open scenario", "Refresh scenario", "Archive scenario" | none |
| Event sets | Name | `name` | link | SF-17:event-set |
| Event sets | Code | `code` | mono | none |
| Event sets | Version | `version_no` | "v<n>" | none |
| Event sets | Status | `status` (SC-V lifecycle) | SCREENS.md §0.8 E-12 chip | none |
| Event sets | Inputs | count of `import_upload_ids` and `api_commands` | integer | SF-17:event-set |
| Event sets | Updated | `updated_at` | DS-FMT-17 | none |
| Runs | Event set | event set name and version | text link | SF-17:event-set |
| Runs | Horizon | `parameters.horizon_periods` | "<first label> – <last label>" (DS-FMT-20) | none |
| Runs | Status | `status` | E-67 chip | none |
| Runs | Started, Finished | `started_at`, `finished_at` | DS-FMT-17 | none |
| Runs | Outputs | none | link "Open" | SF-17:run |

**States.**

| State | Copy |
|---|---|
| Production SCR-ST-03 | Title "No scenarios yet"; description "A scenario is a sandbox copy of this workspace for forecasts and what-if changes. Nothing in a scenario posts or exports."; primary "New scenario" |
| Event sets SCR-ST-03 | Title "No forecast event sets"; description "An event set holds forecast deliveries, billings, modifications and new contracts, uploaded with the same templates as production imports."; primary "New forecast event set" |
| Runs SCR-ST-03 | Title "No forecast runs"; description "Run a forecast over a published event set to see projected revenue, billing, balances and RPO." |
| Creating scenario | Pinned row with DS-CMP-24 "Copying <tenant name> to a sandbox" |

**Interactions, keyboard and copy.**

*New scenario* (also opened from SF-23:select "New scenario").

```text
+----------------------------------------------------------------------------+
| New scenario                                                           [X] |
| Name                 Q4 2026 outlook____________________________           |
| Purpose (optional)   Q4 revenue outlook_________________________           |
| Source workspace     Avenmoor Holdings (Demo)                              |
| Known at             (Now | A specific time)                               |
| [i] A sandbox copy is created from Avenmoor Holdings (Demo) as known at    |
|     the chosen time. Nothing in the scenario posts or exports.             |
+----------------------------------------------------------------------------+
|                                               [Cancel]  [*Create scenario] |
+----------------------------------------------------------------------------+
```

Validation: "Enter a name." Toast on success "Scenario <name> is ready." with the action "Open scenario". The scenario appears in the tenant switcher with the chip Sandbox (BR-FC-01).

*Refresh scenario*: DS-CMP-11 confirmation "Refresh <name>?"; consequence "The scenario is copied again from the latest production snapshot, and its published event sets are re-applied in their original order. The current scenario workspace is archived."; buttons "Cancel", "Refresh scenario" (REQ-FC-004; SBX-07).

*Archive scenario* (SB-R-05): consequence "Archived scenarios are read-only and are removed from the workspace switcher."; Danger "Archive scenario".

*New forecast event set*: fields "Name", "Code" (uppercase letters, digits and hyphens; "Use letters, digits and hyphens."); buttons "Cancel", "Create event set"; on success navigates to SF-17:event-set.

*Run forecast*: fields "Event set" (published versions), "From" and "To" (periods after the last closed period), "Entities" (multi-select), "Book"; buttons "Cancel", "Run forecast"; toast "Forecast run started." then on success "Forecast run finished." with action "Open outputs".

**Sample world.** J-18.1 (asserted): `jordan` creates "Q4 2026 outlook" from Avenmoor Holdings (Demo), known at now; WLD-T-30 appears in the switcher labelled Sandbox. J-18.2: in the scenario AVM-US Sep 2026 is `closed` and Oct 2026 `open`. J-18.3: event set "Q4 base", WLD-F-30 uploaded, applied without approval, version 1. J-18.4: forecast run Oct 2026 – Dec 2026. J-18-AC-3: API update of the tenant kind returns 409 `tenant-kind-immutable`.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Scenarios grid | grid named "Scenarios" | `SF-17-grid-scenarios` |
| Scenario row | row header "<name>" | `SF-17-row-<name normalised>` (for example `SF-17-row-q4-2026-outlook`) |
| Event sets grid | grid named "Forecast event sets" | `SF-17-grid-event-sets` |
| Runs grid | grid named "Forecast runs" | `SF-17-grid-runs` |
| Creation job | progressbar named "Copying …" | `SF-17-job-scenario` |

**Light and dark.** Sandbox banner and the 2 px `--warning-solid` top line in both themes.

**Accessibility.** The "Known at" segmented control reveals a timestamp field; the reveal is announced politely.

### 7.2 SF-17:event-set Forecast event set

| Field | Value |
|---|---|
| Screen id | SF-17:event-set |
| Route | `/reports/forecasts/event-sets/:eventSetId` (RT-40) |
| Roles and permissions | Read and write `scenario.use` |
| Purpose | Assemble a named, versioned set of forecast inputs in order and publish it for forecast runs and refreshes |
| REQ | REQ-FC-002, 004, 007; BR-FC-02 |
| Journeys | J-18.3 |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Reports > Scenarios and forecasts > Q4 base                                                                          |
| Q4 base   (Published)  v1                                         [Add forecast file]  [Publish version]  [*Run forecast]|
| Code Q4-BASE · Scenario Q4 2026 outlook · Updated 12 Sep 2026 17:20 UTC by Jordan Blake                              |
+------+---------------+---------------------------------------+--------------------------------+-------+--------------+
| Order| Kind          | Input                                 | Template                       | Rows  | Status       |
| 1    | Import        | forecast-q4-2026.csv                  | Modern CSV: progress and billing| 4    | (Committed)  |
+------+---------------+---------------------------------------+--------------------------------+-------+--------------+
```

**Wireframe, 1280 px.** "Template" moves under "Input".

```text
+--------------------------------------------------------------------------------------------------------+
| Q4 base (Published) v1                          [Add forecast file] [Publish version] [*Run forecast]   |
| 1  Import  forecast-q4-2026.csv · Modern CSV: progress and billing   4 rows  (Committed)                 |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-06 record header; DS-CMP-10 DataGrid "Inputs in order"; DS-CMP-11 confirmation "Publish version".

**Data bindings.** `GET /forecast-event-sets/{id}`; `PATCH /forecast-event-sets/{id}` (name while draft); `POST /forecast-event-sets/{id}/publish`; import rows `GET /imports/{id}` per `import_upload_ids`.

**Grid columns.** "Order" (integer); "Kind" ("Import", "API command"); "Input" (file name link to SF-10:detail, or `method path` in mono); "Template" (template name); "Rows" (integer; em dash for commands); "Status" (SCREENS.md §0.8 E-40 chip); "Committed" (DS-FMT-17); "Committed by" (user).

**States.** SCR-ST-03: title "No inputs yet"; description "Add forecast files with the production templates. Each file is validated like a production import and applied without approval." primary "Add forecast file".

**Interactions, keyboard and copy.** "Add forecast file" opens SF-10:new with `event_set=<eventSetId>` (SCREENS.md SCR-URL-29), which appends the committed upload to the set. "Publish version": consequence "Version <n> becomes the input of forecast runs and refreshes. Later changes create version <n+1>."; buttons "Cancel", "Publish version".

**Sample world.** J-18.3 (asserted): "Q4 base" with WLD-F-30 `forecast-q4-2026.csv` (K-11 remaining 80 units on 2026-10-15; K-08 usage 70,000 calls per month Oct to Dec 2026), version 1.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "<event set name>" | `SF-17-page` |
| Inputs grid | grid named "Inputs in order" | `SF-17-grid-event-set-inputs` |

**Light and dark.** Chips only.

**Accessibility.** Order column is the row header.

### 7.3 SF-17:run Forecast run

| Field | Value |
|---|---|
| Screen id | SF-17:run |
| Route | `/reports/forecasts/runs/:runId` (RT-41) |
| Roles and permissions | Read `scenario.use`; export `report.export` (holders of `scenario.use` without it see no export menu) |
| Purpose | Show one forecast run's parameters and outputs: forecast revenue, billing, projected balances, projected RPO and journal preview |
| REQ | REQ-FC-003, 005 |
| Journeys | J-18.4, J-18-AC-4 |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Reports > Scenarios and forecasts > Forecast run                                                                     |
| Forecast run · Q4 base v1 · 12 Sep 2026 17:24 UTC   (Succeeded)                   [Actual vs forecast]  Export v     |
| Horizon Oct 2026 – Dec 2026 · Entities AVM-US, AVM-DE · Book ASC 606 · Report runs 5                                 |
+----------------------------------------------------------------------------------------------------------------------+
| Revenue   Billing   Balances   RPO   Journal preview                                                                 |
| Forecast revenue by period · EUR · ASC 606                                                        (Chart | Table)    |
|  .. .. ..                                                                                                            |
| Contract          Obligation   Oct 2026 (EUR)   Nov 2026 (EUR)   Dec 2026 (EUR)   Total (EUR)                        |
| NS-SO-DE-5004     O1               35,669.72              …                …              …                          |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** As 1440 px; period columns scroll with "Contract" pinned.

```text
+--------------------------------------------------------------------------------------------------------+
| Forecast run · Q4 base v1 · 12 Sep 2026 17:24 UTC (Succeeded)             [Actual vs forecast] Export v |
| Revenue  Billing  Balances  RPO  Journal preview                                                        |
| NS-SO-DE-5004  O1  | Oct 2026 (EUR) 35,669.72   Nov 2026 (EUR) …                                        |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-06 record header; DS-CMP-07 panel tabs (`pane=revenue|billing|balances|rpo|journals`); the RPT-39 sections rendered per §0.5; DS-CMP-14 chart for the revenue tab.

**Data bindings.** `GET /forecast-runs/{id}` (`report_run_ids`); `GET /report-runs/{id}/data` per section; export per RV-06 of `forecast_outputs`; "Actual vs forecast" opens SF-08:report `actual_vs_forecast` with `p.forecast_run_id=<runId>`.

**Grid columns.** RPT-39 (§5.6.7).

**States.** Running: DS-CMP-24 "Running forecast <event set name>". Failed: SCR-ST-12 "Running forecast <event set name> failed. Nothing was committed." SCR-ST-07: "Forecast run not found".

**Interactions, keyboard and copy.** Tabs per DS-CMP-07 panel variant; figures open Explain on the scenario tenant's calculation traces.

**Sample world.** J-18.4 (asserted): `NS-SO-DE-5004` O1 Oct 2026 forecast revenue 35,669.72 (remaining allocation when remaining quantity reaches zero); XLSX export with run record. J-18-AC-4: "Actual vs forecast" available for Oct – Dec 2026.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Forecast run · …" | `SF-17-page` |
| Revenue grid | grid named "Forecast revenue by period" | `SF-17-grid-forecast-revenue` |
| Revenue row | row header "<external id>" | `SF-17-row-<external id normalised>-<obligation key normalised>` (for example `SF-17-row-ns-so-de-5004-o1`) |
| Chart | figure named "Forecast revenue by period · …" | `SF-17-chart-forecast-revenue` |

**Light and dark.** DS-CH-01 scheduled series in both themes.

**Accessibility.** Panel tabs APG Tabs; the chart's Table view is equivalent.

### 7.4 SF-18 Deal preview

| Field | Value |
|---|---|
| Screen id | SF-18 |
| Route | `/contracts/deal-preview` (RT-22) |
| Roles and permissions | Read and write `scenario.use` (J-18.6 in production). "Save as scenario contract": `scenario.use` in a scenario workspace only |
| Purpose | Preview allocation, SSP range compliance, material-right and VC indicators and revenue by period for a proposed deal from approved SSPs, without saving anything |
| REQ | REQ-FC-006; REQ-SSP-005, 006, 011; D-18 |
| Journeys | J-18.6, J-18-AC-1, J-18-AC-2 |

**Wireframe, 1440 px (J-18.6 result).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Contracts > Deal preview                                                                                             |
| Deal preview                                                                                         [Start over]    |
| [i] Preview only. Nothing is saved.                                                                                  |
+-------------------------------------------+--------------------------------------------------------------------------+
| Customer   {Tamsin Row Hotels Inc. (Demo) v}| Allocation · USD · SSP book US-LIST 2026-H2                            |
| Entity     {AVM-US v}                      | Product        Stated    SSP low    SSP high   Range         Selected   |
| Start date 01 Nov 2026                     |                  price                                     SSP        |
| Lines                                      | AVM-PLAT-100   90,000.00 95,200.00 128,800.00 <Below range>  95,200.00  |
|  Product          Qty  Months   Price      | AVM-IMPL-PLUS  26,000.00         …  22,000.00 <Above range>  22,000.00  |
|  AVM-PLAT-100       1    12   90,000.00    | Total          116,000.00                                              |
|  AVM-IMPL-PLUS      1     —   26,000.00    |  ...   Weight     Allocated      Allocation adjustment                  |
|  [Add line]                                |                    94,225.26                                            |
| [*Preview allocation]                      |                    21,774.74                                            |
|                                            | Indicators   Material rights None · Variable consideration None         |
|                                            | Revenue by period from Nov 2026 · USD      (Chart | Table)              |
+-------------------------------------------+--------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** The form stacks above the results.

```text
+--------------------------------------------------------------------------------------------------------+
| Deal preview                                                                          [Start over]     |
| [i] Preview only. Nothing is saved.                                                                    |
| Customer {Tamsin Row Hotels Inc. (Demo) v}  Entity {AVM-US v}  Start date 01 Nov 2026                  |
| Lines: AVM-PLAT-100 1 · 12 months · 90,000.00 | AVM-IMPL-PLUS 1 · 26,000.00  [Add line]  [*Preview allocation] |
| Allocation · USD · US-LIST 2026-H2                                                                     |
| AVM-PLAT-100  90,000.00  <Below range>  95,200.00  94,225.26                                           |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Form: DS-CMP-21 fields; DS-CMP-10 inline-editable draft grid for lines (draft data, DS-CMP-10). Results: DS-CMP-29 info banner; DS-CMP-10 static table "Allocation"; outline chips for range checks; definition list "Indicators"; DS-CMP-14 chart DS-CH-01 (Scheduled series only) with Table view; DS-CMP-24 progress while computing.

**Data bindings.** Customers `GET /customers?q=`; products `GET /products?q=&is_active=true`; `POST /deal-previews` `{input: {customer_name | customer_id, entity_code, start_date, lines: [{product_code, quantity, term_months, price, performing_entity_code}]}}` (job `DEAL_PREVIEW`; response `result` with allocation, range compliance, indicators and revenue by period; T-FC-04); scenario save `POST /deal-previews/{id}/save` `{contract_external_id}` → 201 `{saved_contract_id}`, allowed in a scenario workspace only (04 §16.14, T-FC-04; OQ-B-13 resolved by D-76).

**Grid columns.**

Lines (draft grid):

| Header | Field | Control | Validation copy |
|---|---|---|---|
| Product | `product_code` | combobox | "Choose a product." |
| Quantity | `quantity` | decimal input | "Enter a quantity above 0." |
| Months | `term_months` | integer input; em dash for point-in-time products | "Enter the term in months." |
| Price (<currency>) | `price` | money input (entity functional currency) | "Enter a price with at most <n> decimals." |
| Performing entity | `performing_entity_code` | select (optional) | none |
| Actions | none | "Remove line" | none |

Allocation (results):

| Header | Field | Format | Align |
|---|---|---|---|
| Product | `product_code` | mono | start |
| Stated price (<ISO>) | `stated_price` | money | end |
| SSP low (<ISO>) | `ssp_low` | money | end |
| SSP mid (<ISO>) | `ssp_mid` | money | end |
| SSP high (<ISO>) | `ssp_high` | money | end |
| Range | `range_status` | outline chip "Inside range", "Below range", "Above range" | start |
| Selected SSP (<ISO>) | `selected_ssp` | money | end |
| Weight | `weight` | DS-FMT-09 two decimals | end |
| Allocated (<ISO>) | `allocated` | money | end |
| Allocation adjustment (<ISO>) | `allocation_adjustment` | money; signed | end |

Totals row "Transaction price" with `total_stated_price` and `total_allocated`. Revenue by period Table view: "Period", "Scheduled (<ISO>)" per product and "Total".

**States.**

| State | Copy |
|---|---|
| Before preview | Results region title "No preview yet"; description "Enter the customer, entity, start date and lines, then preview the allocation from approved SSPs." |
| No approved SSP | Negative banner "No approved SSP exists for <product code> on <start date>. The preview cannot allocate the transaction price." (IMP-09 wording adapted to a preview) |
| Computing | DS-CMP-24 "Computing deal preview" |
| Job failed | SCR-ST-12 "Computing deal preview failed. Nothing was saved." |

**Interactions, keyboard and copy.** "Preview allocation" validates and posts; every preview writes the audit event `deal_preview.run` with the parameters (J-18-AC-2). "Start over" clears the form after the confirmation "Discard this preview?" only when results exist. "Save as scenario contract" (scenario workspace only): DS-CMP-11 form confirmation "Save this deal as a draft contract in <scenario name>?" with the required field "Contract external id" (`contract_external_id`) and buttons "Cancel", "Save as scenario contract"; toast "Saved as draft contract <contract external id> in <scenario name>." with the action "Open contract" (SF-03 for `saved_contract_id`). In production the button is not rendered; the banner states "Preview only. Nothing is saved." Draft grid keyboard per DS-CMP-10 inline editing (Enter commits, Tab moves, Esc cancels).

**Sample world (asserted, J-18.6, WLD-X-25).** Customer "Tamsin Row Hotels Inc. (Demo)"; entity AVM-US; start 01 Nov 2026; SSP book `US-LIST 2026-H2`; AVM-PLAT-100 stated 90,000.00 for 12 months, "Below range", selected SSP 95,200.00; AVM-IMPL-PLUS stated 26,000.00, "Above range", selected SSP 22,000.00; transaction price 116,000.00; allocation 94,225.26 / 21,774.74; no material-right or VC indicators; revenue by period from Nov 2026. J-18-AC-1: production contract count unchanged. Allocation adjustments 4,225.26 / (4,225.26) and the SSP low and mid of AVM-IMPL-PLUS are not asserted.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Deal preview" | `SF-18-page` |
| Lines grid | grid named "Lines" | `SF-18-grid-lines` |
| Allocation table | table named "Allocation" | `SF-18-grid-allocation` |
| Allocation row | row header "<product code>" | `SF-18-row-<product code normalised>` (for example `SF-18-row-avm-plat-100`) |
| Preview banner | status "Preview only. Nothing is saved." | `SF-18-banner-preview-only` |
| Indicators | region named "Indicators" | `SF-18-indicators` |
| Chart | figure named "Revenue by period from <period label> · <currency>" | `SF-18-chart-revenue` |

**Light and dark.** Outline range chips and the DS-CH-01 scheduled series in both themes.

**Accessibility.** The draft grid announces "Editing <column>, <value>" (DS-A11Y-11); range chips are text; results region is `aria-live="polite"` only for the completion message through `announce()`.

## 8. AI assistance (SF-20, SF-28, SF-15:ai, SF-15:ai-call-log)

Every AI output on these screens is a DS-CMP-25 proposal block: dashed `--proposal-border` edge, Sparkle icon, label "Proposed", source line and details popover (model id, prompt template id and version, prompt hash). No block uses the accent colour or any violet treatment (D-61), and no copy uses the first person (DS-CPY-08). AI entry points are not rendered when `ai.enabled` is false or the user lacks `ai.use`.

### 8.1 SF-20:new Review a contract document

| Field | Value |
|---|---|
| Screen id | SF-20:new |
| Route | `/contracts/review/new` (RT-23) |
| Roles and permissions | `ai.use` (RT-23); creating the draft later needs `contract.create` |
| Purpose | Upload a contract document and start an extraction proposal |
| REQ | REQ-AI-001 to 005, 009, 010; BR-AI-03 |
| Journeys | J-19.1, J-19.8 |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Contracts > Review a contract document                                                                               |
| Review a contract document                                                                                           |
| The assistant proposes header fields, lines, variable consideration terms and material-right indicators with         |
| citations. Nothing is applied until you accept fields and create a draft contract.                                   |
| Contracting entity  {AVM-US v}                                                                                       |
| +----------------------------------------------------------------------------------------------------------------+   |
| | Drop a PDF or DOCX file here, or choose a file                                          [Choose file]           |   |
| | PDF, DOCX · at most 25 MiB                                                                                       |   |
| +----------------------------------------------------------------------------------------------------------------+   |
| Kinsley-Marrow-Order-Form-2026-10.pdf · 214 KB · SHA-256 9f3a02c1…b7d4                         [*Start review]      |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** As 1440 px at `--content-max-form`.

```text
+--------------------------------------------------------------------------------------------------------+
| Review a contract document                                                                             |
| Contracting entity {AVM-US v}   [ Drop a PDF or DOCX file here, or choose a file ]   [*Start review]   |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-06 plain header; DS-CMP-21 select; DS-CMP-18 dropzone anatomy (purpose `ATTACHMENT`); DS-CMP-25 generating state; DS-CMP-29 banners.

**Data bindings.** `POST /files` (`purpose = ATTACHMENT`); `POST /ai/contract-extractions` `{file_id, entity_code}` (202; job `AI_TASK`); on job success navigate to SF-20 with the proposal id from `job.result`.

**Grid columns.** None.

**States.**

| State | Copy |
|---|---|
| AI turned off | Page body renders DS-CMP-23 title "AI assistance is turned off for this workspace"; description "A workspace administrator can turn it on in Settings > AI." (ERR-18); holders of `settings.manage` see the link "Open AI settings" |
| Contract text sending off | Negative banner "Sending contract text to the AI provider is turned off for this workspace, so the document cannot be reviewed." (IMP-88) |
| Generating | DS-CMP-25 generating block "Generating proposal" with "Cancel" (`POST /jobs/{id}/cancel`) |
| Failed | DS-CMP-25 failed block "The assistant could not produce a proposal. No data was changed."; refusal adds "The AI provider declined this request. Nothing was proposed." (IMP-87) |
| Upload refused | ERR-37 attachment copy |
| 409 `ai-disabled` at start | ERR-18 banner "AI assistance is turned off for this workspace." (J-19.8) |

**Interactions, keyboard and copy.** The dropzone is a button (Enter or Space opens the file dialog); "Start review" validates "Choose a contract document." and "Choose a contracting entity."; toast on completion "Proposal ready for <file name>."

**Sample world.** J-19.1 (asserted): `maya` uploads WLD-F-29 `Kinsley-Marrow-Order-Form-2026-10.pdf`; job `AI_TASK`; proposal `proposed`; SF-20 opens. J-19.8: after "Turn off AI now", a new attempt returns 409 `ai-disabled` and no proposal is created.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Review a contract document" | `SF-20-page` |
| Dropzone | button named "Choose file" | `SF-20-dropzone` |
| Generating block | region named "Proposed" with `aria-busy="true"` | `SF-20-proposal-generating` |
| AI off banner | text "AI assistance is turned off …" | `SF-20-banner-ai-off` |

**Light and dark.** Dashed proposal edge `--proposal-border` in both themes.

**Accessibility.** The proposal block carries the hidden note "AI-generated proposal. Not applied until accepted." (DS-CMP-25).

### 8.2 SF-20 Contract review

| Field | Value |
|---|---|
| Screen id | SF-20 |
| Route | `/contracts/review/:proposalId` (RT-24) |
| Roles and permissions | Read `ai.use`. Record field decisions and "Create draft contract": `ai.use` and `contract.create`. "Reject proposal": `ai.use` |
| Purpose | Review proposed fields side by side with the document, with citations and confidence, accept, edit or reject each field, and create a draft contract from accepted values |
| REQ | REQ-AI-003, 004, 005; BR-AI-01, 04, 05; REQ-CON-018 |
| Journeys | J-19.2 to J-19.4, J-19-AC-1 to AC-3 |

**Wireframe, 1440 px (J-19.2).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Contracts > Contract review                                                                                          |
| Contract review · Kinsley-Marrow-Order-Form-2026-10.pdf   (Proposed)                     [Reject proposal]  [*Create draft contract]|
| Source Contract review · 12 Sep 2026 14:05 UTC · Details                  Fields 9 · Accepted 6 · Edited 1 · Check 3   |
+------------------------------------------------------+---------------------------------------------------------------+
| Document                                   Page 1 v | [sparkle] Proposed                                             |
|  ORDER FORM                                          | Header                                                        |
|  Customer: [Kinsley Marrow Foods Inc.]               |  Customer        Kinsley Marrow Foods Inc.   [1] p.1  0.97   |
|  Effective date: [01 October 2026]                   |                  (Accept | Edit | Reject)                     |
|  Term: [12 months]                                   |  Payment terms   Net 30 → Net 45 (edited)    [4] p.2  0.91   |
|  ...                                                 |  Termination     Customer may terminate for… [5] p.3  0.72 <Check>|
|                                                      | Lines                                                         |
|                                                      |  Line 1  AVM-PLAT-100   96,000.00            [6] p.2  0.94   |
|                                                      | Variable consideration terms                                  |
|                                                      |  Service credits up to 5% of monthly fees    [8] p.4  0.62 <Check>|
|                                                      |  Reason for rejection: Assess in the transaction price review.|
|                                                      | Sources [1] p.1 chars 120–146 · [4] p.2 chars 88–95 · …       |
+------------------------------------------------------+---------------------------------------------------------------+
```

**Wireframe, 1280 px.** The document viewer and fields become panel tabs "Document" and "Proposed fields" (`pane=document|fields`); selecting a citation switches to "Document" and focuses the highlight.

```text
+--------------------------------------------------------------------------------------------------------+
| Contract review · Kinsley-Marrow-Order-Form-2026-10.pdf (Proposed)      [Reject proposal] [*Create draft contract]|
| Document   Proposed fields                                                                             |
| Customer  Kinsley Marrow Foods Inc.  [1] p.1  0.97  (Accept | Edit | Reject)                           |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.**

| Region | Components | Content |
|---|---|---|
| Header | DS-CMP-06 plain header; DS-CMP-19 chip; DS-CMP-20 buttons | `h1` "Contract review · <file name>"; meta "Source" (DS-CMP-25 source line with "Details" popover), decision counts |
| Document | docked region rendering the extracted text page by page with `mark` highlights for cited character spans; page select | Text from `GET /ai/proposals/{id}/document-text` → `{proposal_id, file_object_id, pages [{page_no, text}]}` (04 API-R-47, §16.14; it calls no model and works while AI is disabled) |
| Proposed fields | DS-CMP-25 proposal block containing a DS-CMP-10 static table per group | Groups "Header", "Lines", "Variable consideration terms", "Material-right indicators" |
| Field decision | DS-CMP-31 segmented control "Accept" / "Edit" / "Reject"; DS-CMP-21 edit input; reason textarea | Per field |
| Sources | ordered list of citations | "[n] Page <p>, characters <start>–<end>" |

**Data bindings.** `GET /ai/proposals/{id}` (`content[] {path, value, confidence}`, `citations[]`, `status`, `expires_at`, `ai_model_log_id`); `GET /ai/proposals/{id}/document-text` (04 §16.14); `POST /ai/proposals/{id}/accept` `{field_decisions: [{path, decision: ACCEPT | EDIT | REJECT, value, reason}], command: "contract.create_draft", entity_code}` → 201 `{contract_id}` (04 API-R-47, §16.14, E-121: every `content[].path` appears exactly once, `value` is required for `EDIT`, `reason` for `EDIT` and `REJECT`; OQ-B-14 resolved by D-76); `POST /ai/proposals/{id}/reject` `{reason}`.

**Grid columns: field table.**

| Header | Field | Format | Align |
|---|---|---|---|
| Field | label of `content[].path` (for example "Customer", "Effective date", "Term", "Payment terms", "Termination", "Line 1", "Service credits", "Renewal price cap") | text | start |
| Proposed value | `content[].value` | text; dates DS-FMT-16; amounts DS-FMT-05 | start |
| Citation | citation number and page | link "[n] p.<page>" | start |
| Confidence | `content[].confidence` | two decimals as text "0.72"; chip outline "Check" when below 0.75 (BR-AI-01; DS-CMP-25; OQ-B-15 resolved by D-76) | end |
| Decision | segmented control | "Accept", "Edit", "Reject"; fields at or above 0.75 start at "Accept", fields below 0.75 start with no selection | start |
| Edited value | text input shown for "Edit" | text | start |
| Reason | textarea shown for "Reject" ("Reason (required)", minimum 10 characters) | text | start |

**States.**

| State | Copy |
|---|---|
| Accepted | Chip Accepted with "Accepted by <name> on <DD MMM YYYY HH:mm UTC>"; block edge turns solid (DS-CMP-25); link "Open draft contract <external id or contract no>" |
| Awaiting approval (SMAP-11) | Chip Pending approval; info banner "Accepted fields wait for approval of request <request no>." |
| Rejected | Collapsed single line "Dismissed by <name>: <reason>" |
| Expired | Warning banner "This proposal expired on <DD MMM YYYY>. Review the document again to create a new proposal." (BR-AI-04); decision controls hidden |
| Uncited figure | Warning chip "Uncited figure" on the field and "Accept" not rendered for it (DS-CMP-25) |
| Failed | DS-CMP-25 failed state |
| SCR-ST-07 | "Proposal not found" |

**Interactions, keyboard and copy.**

- Selecting a citation scrolls the document to the highlighted span and moves focus to it; Esc returns focus to the citation link.
- "Create draft contract": validates that at least one field is accepted or edited ("Accept at least one field to create a draft contract.") and that every "Reject" has a reason; confirmation "Create a draft contract from <n> accepted fields?" with the description "Rejected fields are not added to the draft. The draft carries the flag AI-assisted and routes activation to a Revenue Reviewer."; buttons "Cancel", "Create draft contract". Toast "Draft contract created from AI proposal <proposal id prefix>." with the action "Open draft contract" (SF-03:edit).
- "Reject proposal" (SB-R-05): consequence "No field is applied. The proposal is kept as evidence."; Danger "Reject proposal".
- Keyboard: segmented controls per APG Radio Group; `N` / `Shift+N` move to the next or previous field needing a decision.

**Sample world (asserted, J-19.2 to J-19.4).** Fields with value, citation page and confidence: Customer "Kinsley Marrow Foods Inc." 0.97 (p.1); Effective date 01 Oct 2026 0.95 (p.1); Term 12 months 0.93 (p.1); Payment terms "Net 30" 0.91 (p.2); Termination "Customer may terminate for convenience on 60 days' notice; early-termination fee 25% of remaining fees" 0.72 (p.3, Check); Line 1 AVM-PLAT-100 96,000.00 0.94 (p.2); Line 2 AVM-IMPL-PLUS 24,000.00 0.88 (p.2); VC term "Service credits up to 5% of monthly fees" 0.62 (p.4, Check); material-right indicator "Renewal price increase capped at 3%" 0.58 (p.4, Check). `maya` accepts customer, effective date, term, termination and both lines; edits payment terms to "Net 45"; rejects the VC term and the indicator with reason "Assess in the transaction price review."; "Create draft contract" creates the draft with source reference "AI proposal <id>" and flag `AI_ASSISTED`; proposal `accepted`. J-19-AC-1: the creation audit event has actor `maya`; J-19-AC-2: rejected terms appear nowhere on the draft.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Contract review · …" | `SF-20-page` |
| Document | region named "Document" | `SF-20-pane-document` |
| Fields block | region named "Proposed" | `SF-20-proposal` |
| Field row | row header "<field label>" | `SF-20-row-<path normalised>` (for example `SF-20-row-payment-terms`) |
| Decision control | radiogroup named "Decision for <field label>" | none |
| Check chip | text "Check" | none |

**Light and dark.** Highlight `mark` uses `--accent-subtle` (text selection token, DS-COL-08) with `--fg-1`; dashed edges; verify in both themes.

**Accessibility.** Highlights have accessible names "Cited text for <field label>"; the confidence cell reads "Confidence 0.72, check"; decisions announce "<field label> accepted" politely.

### 8.3 SF-28 Revenue Q&A panel

| Field | Value |
|---|---|
| Screen id | SF-28 (placement) |
| Placement | Docked panel opened by the top-bar ghost icon button "Ask about revenue" or `panel=ask` (SCREENS.md §0.4 placements) |
| Roles and permissions | `ai.use`, AI enabled; answers read only what the user may read (REQ-AI-008) |
| Purpose | Answer revenue questions through read-only queries, with every figure cited to a record or report run |
| REQ | REQ-AI-003, 004, 008, 009, 010 |
| Journeys | none (covered by `screens.spec.ts` with the fake provider) |

**Wireframe, 1440 px (panel docked, 440 px).**

```text
                                                                          +------------------------------------------+
                                                                          | Ask about revenue                    [X] |
                                                                          | Answers are proposals with citations.    |
                                                                          | They never change data.                  |
                                                                          | Context AVM-US · Sep 2026 · ASC 606      |
                                                                          | ________________________________________ |
                                                                          | What was revenue for Sep 2026?           |
                                                                          |                               [*Ask]     |
                                                                          | [sparkle] Proposed · 12 Sep 2026 17:40   |
                                                                          | Recognized revenue for AVM-US in Sep     |
                                                                          | 2026 was USD … [1].                      |
                                                                          | Sources [1] Report run RPT-000431        |
                                                                          | [Copy answer]  [Dismiss]                 |
                                                                          +------------------------------------------+
```

**Wireframe, 1280 px.** The panel overlays the page as a non-modal drawer (DS-SP-04).

```text
                                                              +------------------------------------------+
                                                              | Ask about revenue                    [X] |
                                                              | ... as 1440 px ...                       |
                                                              +------------------------------------------+
```

**Regions and components.** DS-CMP-09 docked panel variant (width `--explain-w`; opening it closes an open Explain panel, because one docked panel shows at a time); DS-CMP-21 textarea "Question"; DS-CMP-25 proposal blocks (Q&A variant: actions "Copy answer" and "Dismiss"; "Accept" is not rendered because an answer has no command, DS-CMP-25 as amended in DESIGN_SYSTEM rev 1.2; OQ-B-16 resolved by D-76); DS-CMP-12 compact list "Earlier answers".

**Data bindings.** `POST /ai/questions` `{question, context: {entity, period, book}}` (202; job `AI_TASK`); `GET /ai/proposals/{id}`; earlier answers `GET /ai/proposals?kind=QA_ANSWER&limit=50` (04 API-R-47 filters `kind`, `status`), keeping the items created by the caller (`created_by.id` equals `GET /me` `user.id`) and showing the first 10, because 04 defines no creator filter; dismiss `POST /ai/proposals/{id}/reject` `{reason}`.

**Grid columns.** None.

**States.**

| State | Copy |
|---|---|
| Empty | Title "Ask a question about revenue"; description "Answers use the figures you can see in <entity code>, <period label>, <book label>, and cite each figure." |
| Generating | "Generating proposal" block with "Cancel" |
| Unsupported answer | Warning chip "Uncited figure" and text "This answer contains a figure without a citation. Treat it as unsupported." (REQ-AI-008) |
| Failed | "The assistant could not produce an answer. No data was changed." |
| Budget stop | "This workspace reached its monthly AI budget. Answers resume next month or when an administrator raises the budget." |
| AI off | Button not rendered; an open `panel=ask` link renders "AI assistance is turned off for this workspace." (ERR-18) |

**Interactions, keyboard and copy.** "Ask" sends; `Mod Enter` in the textarea sends; Esc closes the panel and returns focus to "Ask about revenue". Citations link to the cited record or SF-08:run. "Dismiss" opens a reason field ("Reason (required)", minimum 10 characters) inside the block, button "Dismiss answer".

**Sample world.** Fake-provider fixtures only (REQ-AI-001); no figures are asserted.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Panel | complementary region named "Ask about revenue" | `SF-28-page` |
| Question | textbox named "Question" | none |
| Answer block | region named "Proposed" | `SF-28-proposal` |
| Sources | list named "Sources" | `SF-28-sources` |

**Light and dark.** Panel `--bg-raised` beside `main` in both themes; dashed edges.

**Accessibility.** New answers are announced politely once ("Answer ready"); the panel is an `aside`.

### 8.4 Anomaly flags and AI narratives (embedded blocks)

These blocks are embedded in screens specified elsewhere: the SF-04 flag drawer (§4.1), the SF-08:dashboard flags panel (§5.5), the SF-11:item detail (SCREENS.md §13) and the Explain panel (SCREENS.md §6).

**Anomaly flag block** (REQ-AI-007; 04 table 15.4-F; E-42 source `ANOMALY`):

| Part | Content |
|---|---|
| Heading | Chip Warning; code in mono (`ANOMALY_REVENUE_CHANGE`, `ANOMALY_NEGATIVE_REVENUE`, `ANOMALY_RECOGNITION_AFTER_POB_END`, `ANOMALY_REVENUE_AHEAD_OF_BILLING`, `ANOMALY_ALLOCATION_ADJUSTMENT`) |
| Message | IMP-82 to IMP-86 copy with placeholders filled |
| Meta | "Owner <name>", "Priority <n>" (1 to 5), status chip (SCREENS.md §0.8 E-44), "Raised <DD MMM YYYY>" |
| Threshold | Tooltip on the code: the registry value used, for example "Threshold: revenue change above 50.0% of the trailing three-period average (ai.anomaly.revenue_change_ratio)" |
| Actions | "Open contract" (SF-03); "Open in exception queue" (SF-11:item); "Summarize with AI" (`ai.use`, AI enabled) |
| AI summary | DS-CMP-25 block kind `ANOMALY_FLAG` from `POST /ai/explanations` `{subject_type: "exception_item", subject_id}` (202 job `AI_TASK`, proposal kind `ANOMALY_FLAG`; 04 §16.14; OQ-B-26 resolved by D-76), actions "Copy summary" and "Dismiss"; the note "Flags never change data." |

**Proposed narrative in Explain** (REQ-AI-006; J-19.6, J-19.7):

| State | Rendering and copy |
|---|---|
| Trigger | Explain footer button "Ask about this figure" (DS-CMP-15) → `POST /ai/explanations` `{object_type, id, measure, period}` |
| Ready | DS-CMP-25 block labelled "Proposed" with the source line "Explain narrative · <timestamp>"; every figure is rendered through the format module and cites a trace node ("[n] <measure name>") |
| Discarded | Info text below the deterministic narrative: "A proposed narrative was discarded because it contained a figure that is not in the calculation trace." |
| Failed | "The assistant could not produce a narrative. The explanation above is complete." |

Sample world (asserted): J-19.6 Explain on `SF-ORD-10001` O1 Sep 2026 (9,764.38) shows the deterministic narrative plus a proposed narrative whose figures all appear in the trace; J-19.7 Explain on `SF-ORD-10002` O1 Sep 2026 shows the deterministic narrative only with the discarded note.

Test hooks: `SF-04-drawer-flag` (SF-04), `SF-08-dashboard-flags` (SF-08:dashboard); the narrative block inside Explain uses SCREENS.md hook `explain-<section>` with section `ai-narrative`.

### 8.5 SF-15:ai AI settings

| Field | Value |
|---|---|
| Screen id | SF-15:ai |
| Route | `/settings/ai` (RT-85) |
| Roles and permissions | Read and submit `settings.manage` (Tenant Admin). Enabling AI, changing the model or enabling contract-text sending is a configuration change approved by another Tenant Admin (BR-AI-02; OQ-B-18 resolved by D-76). "Turn off AI now": `settings.manage` with MFA step-up, immediate, audited (BR-AI-03; 04 API-R-04) |
| Purpose | Show and change the AI registry values with approval, and turn AI off immediately |
| REQ | REQ-AI-001, 002, 009, 010; D-46; BR-AI-02, 03 |
| Journeys | J-19.8, J-19.9 |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > AI assistance                                                                                             |
| AI settings   Call log                                                                                               |
+----------------------------------------------------------------------------------------------------------------------+
| AI assistance                                                                              (Active) On                |
| Provider fake · Model claude-opus-5 · Contract text sending On · Redaction On · Monthly budget 2,000,000 tokens      |
|                                                                                              [Turn off AI now]       |
+----------------------------------------------------------------------------------------------------------------------+
| Change settings                                                                                                      |
| AI assistance              (o) On   ( ) Off                                                                          |
| Send contract text         [x] Send contract text to the provider when reviewing documents                          |
| Model                      claude-opus-5____________                                                                 |
| Monthly token budget       2000000__________                                                                         |
| Redact contact details     [x] Redact email addresses and phone numbers                                             |
| Anomaly thresholds         Revenue change 50.0 %   Revenue ahead of billing 60 days   Allocation adjustment 20.0 %    |
| Comment (required)         ________________________________________________                                         |
|                                                                                          [*Submit for approval]      |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** As 1440 px at `--content-max-form`; the anomaly thresholds stack.

```text
+--------------------------------------------------------------------------------------------------------+
| AI settings   Call log                                                                                  |
| AI assistance (Active) On · Model claude-opus-5 · Budget 2,000,000 tokens          [Turn off AI now]    |
| Change settings … [*Submit for approval]                                                                |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-07 group route tabs "AI settings" · "Call log" (SCREENS.md SCR-IA-03); DS-CMP-06 status section with a definition list; DS-CMP-21 form (radio group, checkboxes, text and number inputs; no switches, because changes need approval, DS-CMP-21); DS-CMP-29 banner for a pending request; DS-CMP-11 confirmation "Turn off AI now".

**Data bindings.** Effective values `GET /policies/resolve?key=ai.enabled` and the other `ai.*` keys; pending request `GET /policies?category=AI&scope=TENANT&status=SUBMITTED`; submit: `POST /policies` `{category: "AI", scope: "TENANT", values}` → `POST /policies/{id}/test` → `POST /policies/{id}/submit` `{comment}` (SM-04; the simulation states "No contracts affected", BR-POL-01); immediate kill switch `POST /tenant/ai/disable` `{comment}` → 200 `{ai_disabled_at}`, with MFA step-up (SCR-PERM-05) and audit event `ai.disabled` (04 API-R-04, §16.14, T-PLT-01 `ai_disabled_at`; OQ-B-18 resolved by D-76). While `ai_disabled_at` is set, `GET /me` returns `tenant_settings.ai_enabled = false`; publishing an approved AI registry version with `ai.enabled = true` clears it (04 B3-D09).

**Grid columns.** None.

| Field | Registry key | Control | Validation copy |
|---|---|---|---|
| "AI assistance" | `ai.enabled` | radio "On" / "Off" | none |
| "Send contract text" | `ai.send_contract_text` | checkbox | none |
| "Model" | `ai.model` | text input | "Enter a model id." |
| "Monthly token budget" | `ai.monthly_token_budget` | integer input | "Enter a whole number of tokens, 0 or more." |
| "Redact contact details" | `ai.redact_contact_details` | checkbox | none |
| "Revenue change threshold" | `ai.anomaly.revenue_change_ratio` | percent input (ratio as a string) | "Enter a percentage from 0 to 1,000." |
| "Revenue ahead of billing" | `ai.anomaly.revenue_ahead_of_billing_days` | integer input, days | "Enter 1 to 365 days." |
| "Allocation adjustment threshold" | `ai.anomaly.allocation_adjustment_ratio` | percent input | "Enter a percentage from 0 to 100." |
| "Comment (required)" | request comment | textarea | "Enter at least 10 characters." |

**States.**

| State | Copy |
|---|---|
| Pending request | Info banner "A change to AI settings is waiting for approval: request <request no>, submitted by <name>." with "View request" |
| AI off | Status chip "Disabled" and text "AI assistance is off. Turning it on needs approval by another workspace administrator." |
| Kill switch set platform-wide | Warning banner "AI assistance is turned off for the platform. Workspace settings take effect when the platform switch is cleared." |

**Interactions, keyboard and copy.** "Submit for approval" toast "Submitted AI settings for approval." "Turn off AI now": DS-CMP-11 confirmation "Turn off AI assistance now?"; consequence "AI features stop immediately for every user. Turning AI on again needs approval."; "Comment (optional)"; Danger "Turn off AI now"; toast "AI assistance turned off."

**Sample world (asserted).** WLD-T-01 at seed: AI enabled with the fake provider, contract text sending on, redaction on, budget 2,000,000 tokens (PRD §2.5). J-19.8: `tomas` turns AI off; effective immediately; `maya`'s review attempt returns 409 `ai-disabled`. J-19.9: `tomas` submits "On"; `grace` approves in SF-12; AI enabled.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Status section | region named "AI assistance" | `SF-15-ai-status` |
| Kill switch | button named "Turn off AI now" | none |
| Settings form | form named "Change settings" | `SF-15-ai-form` |
| Pending banner | status "A change to AI settings is waiting …" | `SF-15-banner-ai-pending` |

**Light and dark.** Danger button fill in both themes (C68, C81 notes).

**Accessibility.** Radio group labelled "AI assistance"; percent inputs have the `%` adornment in their accessible description.

### 8.6 SF-15:ai-call-log AI call log

| Field | Value |
|---|---|
| Screen id | SF-15:ai-call-log |
| Route | `/settings/ai/call-log` (RT-86) with `drawer=call`; the filter parameters `f.user`, `f.template`, `f.outcome` and `f.created` are deferred to later (data bindings below) |
| Roles and permissions | Read `ai.use` or `settings.manage` (RT-86); users holding only `ai.use` see their own calls |
| Purpose | Configuration evidence for every AI call: template, model, parameters, hashes, tokens, latency and user, without prompt or response text |
| REQ | REQ-AI-004; CTL-045 |
| Journeys | J-19.5, J-19-AC-4 |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > AI assistance                                                                                             |
| AI settings   Call log                                                                                               |
+----------------------------------------------------------------------------------------------------------------------+
| 14 calls                                                                                             Export v        |
| Called                   User       Template           Model                     Outcome     In    Out   Latency     |
| 12 Sep 2026 14:05 UTC    Maya Chen  contract-review v1 fake-contract-review-v1   (Succeeded) 1,204  388  0.4 s       |
| ...                                                                                                                  |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** Hash columns move into the row drawer.

```text
+--------------------------------------------------------------------------------------------------------+
| 12 Sep 2026 14:05 UTC  Maya Chen  contract-review v1  fake-contract-review-v1  (Succeeded)  0.4 s       |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Group route tabs; DS-CMP-10 DataGrid (the DS-CMP-13 FilterBar is deferred to later; data bindings); DS-CMP-09 informational drawer (`drawer=call`) showing parameters as a static key-value table and the linked proposal.

**Data bindings.** `GET /ai/model-logs?count=true&limit=50&cursor` (04 API-R-47; default order newest first, API-C-09). Saved-view code `SF-15:ai-call-log`. The FilterBar fields User, Template, Outcome and Called are deferred to later, because 04 API-R-47 defines no `created_by`, `prompt_template_id`, `outcome`, `from` or `to` filter for model logs; 1.0 renders the list without them.

**Grid columns.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Called | `created_at` | DS-FMT-17 | drawer |
| User | `created_by` | user | none |
| Template | `prompt_template_id`, `prompt_template_version` | mono "<id> v<version>" | none |
| Provider | `provider` | "Fake", "Anthropic" | none |
| Model | `model_id` | mono | none |
| Outcome | `outcome` | "Succeeded" (`SUCCESS`), "Failed" (`ERROR`), "Timed out" (`TIMEOUT`, warning ClockCounterClockwise), "Budget exceeded" (`BUDGET_EXCEEDED`, warning WarningCircle), "Disabled" (`DISABLED`, neutral Prohibit) | none |
| Input tokens | `input_tokens` | integer | none |
| Output tokens | `output_tokens` | integer | none |
| Latency | `latency_ms` | DS-FMT-24 ("850 ms", "1.2 s") | none |
| Input SHA-256 | `input_sha256` | prefix with copy | none |
| Response SHA-256 | `response_sha256` | prefix with copy; em dash | none |
| Error | `error_detail` | text with tooltip | none |

**States.** SCR-ST-03: title "No AI calls yet"; description "Every call to the AI provider is logged here with hashes and token counts. Prompt and response text are never stored."

**Interactions, keyboard and copy.** Row Enter opens the drawer "AI call · <DD MMM YYYY HH:mm UTC>". Export per the grid export menu (CSV, XLSX).

**Sample world (asserted, J-19.5).** Entry for `maya`: prompt template `contract-review` version 1; model `fake-contract-review-v1`; parameters; input SHA-256; response SHA-256; token counts; latency. J-19-AC-4: no contract text and no secret in the entry.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Grid | grid named "AI calls" | `SF-15-grid-ai-calls` |
| Row | row header "<called timestamp>"; tests locate the row by its template text, because list filters are deferred to later | `SF-15-row-<template normalised>` (for example `SF-15-row-contract-review`) |
| Drawer | complementary region named "AI call · …" | `SF-15-drawer-ai-call` |

**Light and dark.** Chips only.

**Accessibility.** Hash prefixes with full accessible names; timestamps `data-volatile`.

## 9. Settings (SF-15, SF-14, SF-16:developer)

Settings pages follow SCREENS.md SCR-IA-03: `/settings` is a start-aligned section index; each page renders the breadcrumb "Settings > <page>" and the route tab bar of its group only. Groups and tabs used in this section: **Your preferences** (Notifications, Profile); **Workspace** (Setup, Entities, Calendars, Currencies and rates, Chart of accounts, Workspace settings); **Access** (Users, Roles, Separation of duties, Access reviews, Security, Support access); **Developer** (API clients and webhooks); **AI** (AI settings, Call log, §8); **Sandbox** (Sandbox copies). "Workspace settings" (SF-15:workspace) is proposed in §14.

**Permission note (OQ-B-19 resolved by D-76).** 04 rev 1.2 amends API-R-17 to API-R-19 with any-of write permissions: entities, calendars and `generate-year` accept `masterdata.maintain` or `settings.manage`; rate set versions and rates accept `config.author` or `masterdata.maintain`; `POST /periods/{id}/open` accepts `period.close`, or `settings.manage` while `tenant.setup_completed_at` is null. A control renders for holders of any listed permission. Rev 1.48 (04 T-PLT-01 rev 1.168): the API accepts `settings.manage` there only until the completion conditions hold; in the instant between the conditions and the timestamp the control still renders and the command answers 403, shown as any refusal. API-R-20 (chart of accounts and mapping) keeps `config.author` only.

### 9.1 SF-15 Settings index

| Field | Value |
|---|---|
| Screen id | SF-15 |
| Route | `/settings` (RT-71) |
| Roles and permissions | Authenticated; each link renders only when the user holds a read permission of its page (SCREENS.md §0.4). Rev 1.99: a link asks what its page asks (SCREENS.md §0.6 SCR-PERM-01, SCR-PERM-02 (c)) — the links to Setup, Workspace settings, Access reviews, Security, Support access and Sandbox copies render for a holder of the page's permission for all entities, the link to the developer page for `api_client.manage` held for any entity or `webhook.manage` held for all; the tabs of a settings page follow the same rule. The setup banner renders, and `GET /tenant` is read, for a holder of `settings.manage` for all entities alone |
| Purpose | One index of settings pages grouped by purpose, never a card grid |
| REQ | REQ-UX-001; REQ-REF-001 to 009; REQ-PLT-003, 021 to 025, 033 to 036 |
| Journeys | J-01.1 (redirect to setup), J-22, J-25.4 |

**Wireframe, 1440 px (viewer `tomas`).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings                                                                                                             |
| [i] Workspace setup is not complete. Finish setup >                                                                  |
+----------------------------------------------------------------------------------------------------------------------+
| Your preferences                                                                                                     |
|   Notifications            Choose which notifications you receive in the app and by email                           |
|   Profile                  Password, multi-factor authentication, formats, theme and density                        |
| Workspace                                                                                                            |
|   Setup                    First-run checklist for entities, periods, people and policies                           |
|   Entities                 Legal entities with functional currency, time zone, calendar and books                   |
|   Calendars                Fiscal calendars and period states per entity and book                                   |
|   Currencies and rates     Enabled currencies and FX rate sets with approval                                        |
|   Chart of accounts        GL accounts and dimensions                                                                |
|   Workspace settings       Workspace name, negative amount style and close, platform and integration settings       |
| Reference data                                                                                                       |
|   Customers · Related-party groups · Products                                                                        |
| Access                                                                                                               |
|   Users · Roles · Separation of duties · Access reviews · Security · Support access                                  |
| Developer                  API clients, webhooks and the OpenAPI document                                            |
| AI                         AI settings and call log                                                                  |
| Sandbox                    Sandbox copies, restore into a sandbox and sandbox reset                                  |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** As 1440 px at `--content-max-form`; descriptions wrap under the page names.

```text
+--------------------------------------------------------------------------------------------------------+
| Settings                                                                                               |
| Your preferences                                                                                       |
|   Notifications · Choose which notifications you receive …                                             |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-06 plain header; DS-CMP-29 info banner (setup incomplete, `settings.manage` holders only); one `section` per group with an `h2` and a list of links with descriptions (DS-CMP-10 static table without column headers).

**Data bindings.** `GET /me` (permissions, memberships); `GET /tenant` (`setup_completed_at`).

**Grid columns.** None.

**States.** No readable pages beyond preferences: only "Your preferences" renders.

**Interactions, keyboard and copy.** Links are in the Tab order; group headings are `h2`. Banner copy "Workspace setup is not complete." with the link "Finish setup" (SF-15:setup; BR-PLT-02).

**Sample world.** WLD-T-20 before setup completes: banner shown (J-01.1). WLD-T-01: no banner.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Settings" | `SF-15-page` |
| Group | heading level 2 "<group>" | none |
| Link | link named "<page label>" | `SF-15-row-<page label normalised>` |
| Setup banner | status "Workspace setup is not complete." | `SF-15-banner-setup` |

**Light and dark.** Plain lists on `--bg-surface`.

**Accessibility.** One `h1`; groups are `section` with `h2`.

### 9.2 SF-15:entities Entities

| Field | Value |
|---|---|
| Screen id | SF-15:entities |
| Route | `/settings/entities` (RT-75) |
| Roles and permissions | Read `config.read`. Create and edit: `masterdata.maintain` (04 API-R-17) or `settings.manage` (PRD ACT-44; J-01.2), any-of per 04 API-R-17 rev 1.2 |
| Purpose | Maintain legal entities with functional currency, time zone, calendar, parent and books |
| REQ | REQ-REF-001; REQ-BK-001; REQ-ENT-001; BR-REF-01 |
| Journeys | J-01.2, J-20 preconditions, J-23 preconditions |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Entities                                                                                                  |
| Setup   Entities   Calendars   Currencies and rates   Chart of accounts   Workspace settings                         |
+----------------------------------------------------------------------------------------------------------------------+
| 4 entities                                                                                            [*New entity]  |
| Code     Name                     Country  Functional currency  Time zone          Calendar   Books            Active|
| AVM-US   Avenmoor Inc. (Demo)     US       USD [lock]           America/New_York   MONTHLY    ASC 606          Yes   |
| AVM-UK   Avenmoor UK Ltd (Demo)   GB       GBP [lock]           Europe/London      MONTHLY    ASC 606, IFRS 15 Yes   |
| AVM-DE   Avenmoor Devices GmbH …  DE       EUR [lock]           Europe/Berlin      MONTHLY    ASC 606          Yes   |
| AVM-JP   Avenmoor Media KK (Demo) JP       JPY [lock]           Asia/Tokyo         MONTHLY-AP ASC 606          Yes   |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** "Country" and "Active" move into the edit drawer.

```text
+--------------------------------------------------------------------------------------------------------+
| AVM-US  Avenmoor Inc. (Demo)  USD [lock]  America/New_York  MONTHLY  ASC 606                           |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Group route tabs; DS-CMP-10 DataGrid; DS-CMP-09 modal drawer "New entity" / "Edit <code>"; DS-CMP-27 tooltips on lock icons.

**Data bindings.** `GET /entities`; `GET /books`; `GET /calendars`; `GET /tenant-currencies`; `POST /entities`; `PATCH /entities/{id}` (`If-Match`); `PUT /entities/{id}/books/{code}` `{is_enabled, first_period_key}`.

**Grid columns.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Code | `code` | mono | edit drawer |
| Name | `name` | text | none |
| Country | `country_code` | mono | none |
| Functional currency | `functional_currency` | mono; LockSimple icon with tooltip "Fixed after the first posting." once postings exist (BR-REF-01) | none |
| Time zone | `time_zone` | text; lock icon as above | none |
| Calendar | calendar code | mono link | SF-15:calendars `?calendar=<code>` |
| Parent entity | `parent_entity` code | mono | none |
| Books | enabled `entity_book` rows | "ASC 606", "IFRS 15", "Legacy" joined with ", " | none |
| Active | `is_active` | "Yes" / "No" | none |

**States.** SCR-ST-03: title "No entities yet"; description "An entity sets the functional currency, time zone, calendar and books for its contracts and postings."; primary "New entity".

**Interactions, keyboard and copy.** Drawer fields: "Code" (validation "Use letters, digits and hyphens."); "Name"; "Country" (ISO 3166-1 combobox); "Functional currency" (enabled currencies; read-only once postings exist); "Time zone" (IANA combobox; read-only once postings exist); "Calendar" (select); "Parent entity (optional)"; "Tax id (optional)"; "Books" (checkboxes "ASC 606", "IFRS 15", "Legacy", each with "First period" select); "Active" (checkbox). Buttons "Cancel", "Save entity". Toast "Saved entity <code>." Problems: `precondition-failed` SCR-ST-09; `immutable-record` ERR-41 for the locked fields.

**Sample world.** WLD-T-01 (PRD §2.5): AVM-US USD America/New_York January, ASC606; AVM-UK GBP Europe/London January, ASC606 and IFRS15; AVM-DE EUR Europe/Berlin January, ASC606; AVM-JP JPY Asia/Tokyo April, ASC606. J-01.2 (WLD-T-20): `Mock Entity 1` and `Mock Entity 2`, USD, America/New_York, monthly calendar starting January.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Grid | grid named "Entities" | `SF-15-grid-entities` |
| Row | row header "<code>" | `SF-15-row-<code normalised>` |
| Drawer | dialog named "New entity" or "Edit <code>" | `SF-15-drawer-entity` |

**Light and dark.** Lock icons `--fg-2`.

**Accessibility.** Lock icons are named "Fixed after the first posting".

### 9.3 SF-15:calendars Calendars and periods

| Field | Value |
|---|---|
| Screen id | SF-15:calendars |
| Route | `/settings/calendars` (RT-76) with the screen parameter `calendar=<code>` (SCREENS.md SCR-URL-27) and `f.fiscal_year` |
| Roles and permissions | Read `config.read`. Create calendars and generate fiscal years: `masterdata.maintain` or `settings.manage` (04 API-R-18). "Open period": `period.close`, or `settings.manage` while `tenant.setup_completed_at` is null (J-01.2; 04 API-R-18 rev 1.2). Rev 1.99 (the supervisor's ruling of 2026-10-02 02:43; PRD ACT-44, BR-UX-06): the setup branch of "Open period" asks `settings.manage` for all entities — the setup of the workspace is the tenant's, and `GET /tenant`, which says that the workspace is being set up, answers such a holder alone and is read for no other; `period.close` stays asked for the period's entity |
| Purpose | Maintain fiscal calendars, generate periods and see the state of every period per entity and book |
| REQ | REQ-REF-002, 003; REQ-CLS-001; BR-REF-02 |
| Journeys | J-01.2, J-20 preconditions |

**Wireframe, 1440 px (calendar MONTHLY selected).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Calendars                                                                                                 |
| Setup   Entities   Calendars   Currencies and rates   Chart of accounts   Workspace settings                         |
+-----------------------------------------+----------------------------------------------------------------------------+
| Calendars (2)            [New calendar] | MONTHLY · Monthly, fiscal year starts January      [Generate fiscal year] |
| |* MONTHLY   Monthly · January          | Fiscal year {FY2026 v}                                                     |
|    MONTHLY-AP Monthly · April           | Period      Name      Start        End          Q   AVM-US ASC 606  AVM-UK ASC 606  AVM-UK IFRS 15 |
|                                         | FY2026-P08  Aug 2026  01 Aug 2026  31 Aug 2026  3   (Locked)        (Locked)        (Locked)       |
|                                         | FY2026-P09  Sep 2026  01 Sep 2026  30 Sep 2026  3   (Period open)   (Period open)   (Period open)  |
|                                         | FY2026-P10  Oct 2026  01 Oct 2026  31 Oct 2026  4   (Future) [Open] (Future)        (Future)       |
+-----------------------------------------+----------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** The calendars master list collapses to a select above the periods grid; state columns scroll horizontally with "Period" pinned.

```text
+--------------------------------------------------------------------------------------------------------+
| {MONTHLY v}  Fiscal year {FY2026 v}                                          [Generate fiscal year]    |
| FY2026-P09  Sep 2026  | AVM-US ASC 606 (Period open)  AVM-UK ASC 606 (Period open) …                    |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-08 master-detail (calendars list; selection in `calendar`); DS-CMP-10 DataGrid of periods with one state column per entity × book using the calendar; DS-CMP-11 form modals "New calendar", "Generate fiscal year", "Open period"; DS-CMP-19 period chips.

**Data bindings.** `GET /calendars`; `POST /calendars` `{code, name, pattern, fiscal_year_start_month, week_end_day, year_end_anchor}`; `POST /calendars/{id}/generate-year` `{fiscal_year}`; `GET /periods?fiscal_year=<n>&entity&book` (API-S-Period rows per entity × book); `POST /periods/{id}/open`.

**Grid columns.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Period | `period.period_key` | mono | none |
| Name | `period.name` | DS-FMT-19 | none |
| Start | `period.start_date` | DS-FMT-16 | none |
| End | `period.end_date` | DS-FMT-16 | none |
| Quarter | `period.quarter_no` | integer | none |
| "<entity code> <book label>" per entity × book | `state` | period chip (§0.4 E-04); ghost button "Open" in `future` cells whose previous period is not `future` | SF-05 for that entity, book and period |

**States.** SCR-ST-03 calendars: title "No calendars yet"; description "A calendar defines fiscal years and periods. Entities use one calendar each."; primary "New calendar". No periods for the fiscal year: title "No periods for <fiscal year label>"; description "Generate the fiscal year to create its periods."; primary "Generate fiscal year".

**Interactions, keyboard and copy.** *New calendar*: fields "Code", "Name", "Pattern" (select "Monthly", "4-4-5", "4-5-4", "5-4-4", "13 four-week periods", "52/53-week year"; E-50), "Fiscal year starts in" (month select), "Week ends on" and "Year-end anchor" (week-based patterns: "Last weekday of the month", "Nearest weekday to month end"). Editing a calendar lists the affected future periods before saving: "Changes apply to <n> future periods without postings: <period labels>." (BR-REF-02). *Generate fiscal year*: field "Fiscal year" (the year in which the fiscal year ends; help "AVM-JP's April 2026 to March 2027 year is FY2027."); toast "Generated <n> periods for <fiscal year label>." *Open period*: confirmation "Open <period label> for <entity code> in book <book label>?"; buttons "Cancel", "Open period".

**Sample world.** WLD-T-01 (WLD-P-02): Jan to Aug 2026 Locked, Sep 2026 Period open, Oct 2026 to Dec 2027 Future; AVM-JP calendar April start, Sep 2026 = `FY2027-P06` (WLD-P-05). J-01.2 (asserted): WLD-T-20 periods Jan to Dec 2023 open, Jan 2024 onward future.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Calendars list | listbox named "Calendars" | `SF-15-calendars-list` |
| Periods grid | grid named "Periods" | `SF-15-grid-periods` |
| Period row | row header "<period_key>" | `SF-15-row-<period_key normalised>` |
| Open button | button named "Open <period label> for <entity code> <book label>" | none |

**Light and dark.** Period chips in the matrix; hairline dividers.

**Accessibility.** State cells are named "<entity code> <book label> <period label>: <state>".

### 9.4 SF-15:currencies Currencies and rates

| Field | Value |
|---|---|
| Screen id | SF-15:currencies |
| Route | `/settings/currencies` (RT-77) with the screen parameters `rate_set=<code>` and `version=<n>` (SCREENS.md SCR-URL-27) |
| Roles and permissions | Read `config.read`. Enable currencies: `settings.manage`. Create and edit rate set versions, upload rates: `config.author` (04 API-R-19) or `masterdata.maintain` (PRD ACT-24), any-of per 04 API-R-19 rev 1.2. Approval of `FX_RATE_SET_VERSION`: `config.approve` in SF-12. Rev 1.99 (SCREENS.md §0.6 SCR-PERM-02 (c)): "Save currencies" renders for `settings.manage` held for all entities — `PUT /tenant-currencies` is an act on the whole workspace; a holder for named entities reads the currencies |
| Purpose | Enable currencies and maintain FX rate sets as immutable approved versions |
| REQ | REQ-REF-004, 005, 006; D-25; BR-FC none |
| Journeys | J-23 preconditions; FX figures of J-13 and J-15 |

**Wireframe, 1440 px (AVM-RATES closing version selected).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Currencies and rates                                                                                      |
| Setup   Entities   Calendars   Currencies and rates   Chart of accounts   Workspace settings                         |
+----------------------------------------------------------------------------------------------------------------------+
| Enabled currencies                                                                                                   |
| Code  Name             Minor unit  Enabled   Used by                                                                 |
| USD   US dollar        2           [x]       AVM-US                                                                  |
| JPY   Japanese yen     0           [x]       AVM-JP                                                                  |
+----------------------------------------------------------------------------------------------------------------------+
| FX rate sets (3)                                                                         [New rate set]              |
| AVM-RATES-CLOSING · closing · Manual   Latest approved v9 · coverage 01 Jan 2026 – 30 Sep 2026                        |
| Versions  v9 (Approved)  v10 (Draft)                                          [Upload rates CSV] [*Submit for approval]|
| Base  Quote  Effective date  Period    Rate (base to quote)  Derived                                                 |
| EUR   USD    30 Sep 2026     Sep 2026  1.120000              No                                                      |
| GBP   USD    30 Sep 2026     Sep 2026  1.290000              No                                                      |
| JPY   USD    30 Sep 2026     Sep 2026  0.006950              No                                                      |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** The currencies table collapses to a comma-separated list with an "Edit currencies" button opening a drawer.

```text
+--------------------------------------------------------------------------------------------------------+
| Enabled currencies: USD, GBP, EUR, JPY                                         [Edit currencies]       |
| {AVM-RATES-CLOSING v}  v10 (Draft)                    [Upload rates CSV] [*Submit for approval]         |
| EUR USD 30 Sep 2026 Sep 2026 1.120000                                                                  |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-10 static table "Enabled currencies" with checkboxes (changes apply on "Save currencies"); DS-CMP-10 DataGrid "Rates" (inline editable only while the version is Draft, DS-CMP-10); DS-CMP-11 form modals "New rate set", "New version"; DS-CMP-29 banner for a pending approval.

**Data bindings.** `GET /currencies`; `GET, PUT /tenant-currencies`; `GET /fx-rate-sets`; `POST /fx-rate-sets` `{code, name, rate_type, source}`; `GET, POST /fx-rate-sets/{id}/versions`; `GET, PATCH /fx-rate-set-versions/{id}` (draft rates); `POST /fx-rate-set-versions/{id}/submit`, `/withdraw`; `GET /fx-rates?rate_type&base&quote&date&period`. "Upload rates CSV" opens SF-10:new with the FX rates template (REQ-REF-006).

**Grid columns: rates.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Base | `base_currency` | mono | none |
| Quote | `quote_currency` | mono | none |
| Effective date | `effective_date` | DS-FMT-16 | none |
| Period | `period_id` → label (closing and average rates) | DS-FMT-19 | none |
| "Rate (<base> to <quote>)" when one pair is filtered, else "Rate (base to quote)" | `rate` | DS-FMT-14, 6 decimals | none |
| Derived | `is_derived` | "Yes" / "No" | none |

**States.** SCR-ST-03 rate sets: title "No FX rate sets"; description "Rate sets hold spot, closing and average rates. Each version is approved before it is used." Draft version without rates: title "No rates in this draft"; description "Add rates in the grid or upload a CSV, then submit the version for approval." Missing required rate (from an exception): negative banner with ERR-36 copy.

**Interactions, keyboard and copy.** "Submit for approval": confirmation "Submit <code> v<n> with <rate count> rates for approval?"; buttons "Cancel", "Submit for approval". A zero or empty rate cell reports "Enter a rate above 0." (REQ-REF-005). Approved versions are read-only with the tooltip "This version is no longer a draft, so it is read-only." (ERR-09).

**Sample world (PRD §2.5, asserted values).** AVM-RATES: Aug 2026 average / closing EUR to USD 1.100000 / 1.105000; GBP to USD 1.270000 / 1.275000; JPY to USD 0.006800 / 0.006850. Sep 2026 average / closing EUR to USD 1.110000 / 1.120000; GBP to USD 1.280000 / 1.290000; JPY to USD 0.006900 / 0.006950. Daily spot equals the month average; Jan to Jul 2026 rates equal the Aug 2026 average. The split of AVM-RATES into one set per rate type (T-REF-10 `rate_type`) is a seed detail and not asserted.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Currencies table | table named "Enabled currencies" | `SF-15-grid-currencies` |
| Rate sets | region named "FX rate sets" | `SF-15-rate-sets` |
| Rates grid | grid named "Rates" | `SF-15-grid-rates` |
| Rate row | row header "<base> to <quote> <effective date>" | `SF-15-row-<base normalised>-<quote normalised>-<period_key normalised>` |

**Light and dark.** Editable cells `--bg-hover` on hover in both themes.

**Accessibility.** Rate headers name the direction (DS-FMT-14).

### 9.5 SF-15:chart-of-accounts Chart of accounts

| Field | Value |
|---|---|
| Screen id | SF-15:chart-of-accounts |
| Route | `/settings/chart-of-accounts` (RT-78) with `f.account_type`, `q` |
| Roles and permissions | Read `config.read`. Create and edit accounts: `config.author` (04 API-R-20). Dimensions: `masterdata.maintain` (04 API-R-21). Sync from a GL connection: `integration.manage` on SF-16:connection |
| Purpose | Maintain GL accounts and dimensions used by account mapping and journal validation |
| REQ | REQ-REF-007, 009; REQ-INT-008; REQ-JE-022 |
| Journeys | J-23.7 (sync on SF-16:connection) |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Chart of accounts                                                                                         |
| Setup   Entities   Calendars   Currencies and rates   Chart of accounts   Workspace settings                         |
+----------------------------------------------------------------------------------------------------------------------+
| Accounts (31)                                                              [Import accounts]  [*New account]         |
| Code   Name                                    Type       Normal   Entities       Required dimensions  Source  Active|
| 1100   Accounts receivable                     Asset      Debit    All entities   —                    Manual  Yes   |
| 2100   Contract liability                      Liability  Credit   All entities   —                    Manual  Yes   |
| 4010   Revenue - services and subscriptions    Revenue    Credit   All entities   department           Manual  Yes   |
| ...                                                                                                                  |
+----------------------------------------------------------------------------------------------------------------------+
| Dimensions (5 built in, 0 of 5 custom)                                                   [New dimension]             |
| Code        Name         Built in  Values  Active                                                                    |
| department  Department   Yes       …       Yes                                                                       |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** "Required dimensions" and "Source" move into the account drawer.

```text
+--------------------------------------------------------------------------------------------------------+
| 2100  Contract liability  Liability  Credit  All entities  Yes                                         |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-10 DataGrids "Accounts" and "Dimensions"; DS-CMP-09 modal drawers "New account" / "Edit <code>" and "Dimension values"; link button "Import accounts" (SF-10:new with the chart-of-accounts template; SCREENS.md §12).

**Data bindings.** `GET /gl-accounts`; `POST /gl-accounts`; `PATCH /gl-accounts/{id}`; `GET /dimensions`; `POST /dimensions`; `GET, POST /dimensions/{code}/values`; `PATCH /dimensions/{code}/values/{id}`.

**Grid columns: accounts.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Code | `code` | mono | drawer |
| Name | `name` | text | none |
| Type | `account_type` | "Asset", "Liability", "Equity", "Revenue", "Expense" (E-52) | none |
| Normal balance | `normal_balance` | "Debit" / "Credit" | none |
| Entities | `entity_ids` | "All entities" or codes | none |
| Required dimensions | `required_dimensions` | codes (mono) | none |
| Source | `source_system` | "Manual", "NetSuite", "QuickBooks Online", "Legacy v1" | none |
| Active | `is_active` | "Yes" / "No" | none |
| Mapped roles | resolved mapping rules of the published mapping | E-01 labels joined with ", " | SF-13:account-mapping |

**States.** SCR-ST-03 accounts: title "No accounts yet"; description "Accounts are loaded by CSV, synced from the GL connection or entered here. Journal lines are validated against them."; primary "New account". Custom dimension limit on submit: "A workspace can define at most five custom dimensions."

**Interactions, keyboard and copy.** Account drawer fields "Code", "Name", "Type", "Normal balance", "Entities" (All entities or selection), "Required dimensions" (multi-select), "Active"; buttons "Cancel", "Save account"; toast "Saved account <code>." Deactivating an account used by the published mapping shows the warning "Account <code> is mapped for <role labels>. Journal generation fails for those roles until the mapping changes." with "I have reviewed this warning" (DS-CMP-21).

**Sample world.** WLD-T-01 chart of accounts (PRD §2.6): 1100 Accounts receivable through 7900 Rounding, with 2090 Subledger clearing carrying one mapping rule per clearing purpose.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Accounts grid | grid named "Accounts" | `SF-15-grid-accounts` |
| Account row | row header "<code>" | `SF-15-row-<code normalised>` |
| Dimensions grid | grid named "Dimensions" | `SF-15-grid-dimensions` |

**Light and dark.** Plain grids.

**Accessibility.** Account codes are row headers.

### 9.6 SF-15:workspace Workspace settings

| Field | Value |
|---|---|
| Screen id | SF-15:workspace (SCREENS.md §0.4; §14) |
| Route | `/settings/workspace` |
| Roles and permissions | Read `settings.manage` (Tenant Admin); `config.read` holders see values read-only. Submitting changes creates registry versions approved in SF-12 (`REGISTRY_VERSION`, `config.approve`). Rev 1.99 (SCREENS.md §0.6 SCR-PERM-02 (c)): `settings.manage` is asked for all entities, for the page's own commands and for `GET /tenant`, which is read for no other member. A holder for named entities who holds `config.read` sees the values read-only like every such reader; one who does not reads SCR-ST-06 with "Workspace settings cover every entity of the workspace. Ask a workspace administrator for a role that includes managing workspace settings (settings.manage) for all entities." Rev 1.102 (04 §16.5 rev 1.309; item POLICY-TENANT-SCOPE-ALL-ENTITIES-1): the form authors versions of the tenant, so its controls and "Submit for approval" are for a holder of `config.author` for ALL entities; a holder for named entities reads the values, as every other reader does, and the requests are approved by a holder of `config.approve` for all entities |
| Purpose | Workspace identity and the platform, close and integration registry values that are not accounting policies |
| REQ | REQ-PLT-003; REQ-UX-006; REQ-CLS-007, 019; REQ-RPT-006; REQ-DAT-008; REQ-CON-011; T-PLT-31 platform parameters; D-75 (negative style) |
| Journeys | none (covered by `screens.spec.ts`) |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Workspace settings                                                                                        |
| Setup   Entities   Calendars   Currencies and rates   Chart of accounts   Workspace settings                         |
+----------------------------------------------------------------------------------------------------------------------+
| Workspace                                                                                                            |
| Name  Avenmoor Holdings (Demo)   Code avenmoor   Kind production   Reporting currency USD   Demo workspace Yes         |
+----------------------------------------------------------------------------------------------------------------------+
| Formats                                                                                                              |
| Negative amounts          (o) (4,000.00)   ( ) −4,000.00                                                             |
| Close                                                                                                                |
| Require reconciliations for lock      [x]                                                                            |
| Block lock after unacknowledged export  5 days                                                                       |
| Late-entry window                        5 days                                                                      |
| Rollforward "Other" threshold          1.0 %                                                                         |
| Revenue without billing monitor         60 days      Inactive contract monitor   90 days                            |
| Platform and integrations                                                                                            |
| Job concurrency 4 · Audit retention 7 years · Quarantine failed import rows [ ] · Grouping fields order_number        |
| SSP second-approver threshold 10.0 % · Mandatory disaggregation attributes —                                          |
| Accounting policies and practical expedients are set in Policies > Accounting policies >                             |
| Comment (required) ____________________________________                                   [*Submit for approval]      |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** As 1440 px at `--content-max-form`, one field per line.

```text
+--------------------------------------------------------------------------------------------------------+
| Workspace: Avenmoor Holdings (Demo) · avenmoor · production · USD                                      |
| Negative amounts (o) (4,000.00) ( ) −4,000.00                                                          |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-06 definition list "Workspace"; DS-CMP-21 form grouped in `fieldset`s "Formats", "Close", "Platform and integrations"; DS-CMP-29 pending-request banner and, rev 1.94, one open-version banner per category; link to SF-13:accounting.

**Data bindings.** `GET /tenant`; `PATCH /tenant` `{display_name, default_locale}` (`settings.manage`; `kind` is never sent, ERR-26); effective registry values `GET /policies/resolve?key=<code>` for each platform key; submit per changed category: `POST /policies` `{category, scope: "TENANT", values}` → `/test` → `/submit` `{comment}`. Rev 1.72: the request names no `effective_from` — a version of the platform, close and integration categories takes effect when it is approved, and it keeps every published value of its category that the request does not state (04 T-PLT-32 and §16.5 rev 1.183).

| Field | Registry key (category) | Control | Validation copy |
|---|---|---|---|
| "Negative amounts" | `ui.negative_number_style` (PLATFORM) | radio "(4,000.00)" (`PARENTHESES`) / "−4,000.00" (`MINUS`) | none |
| "Require reconciliations for lock" | `close.require_reconciliations_for_lock` (CLOSE) | checkbox | none |
| "Block lock after unacknowledged export" | `close.unacknowledged_export_block_days` (CLOSE) | integer, days 0 to 30 | "Enter 0 to 30 days." |
| "Late-entry window" | `close.late_entry_window_days` (CLOSE) | integer 0 to 31 | "Enter 0 to 31 days." |
| "Rollforward Other threshold" | `close.rollforward_other_threshold_ratio` (CLOSE) | percent | "Enter a percentage from 0 to 100." |
| "Revenue without billing monitor" | `close.dq_revenue_without_billing_days` (CLOSE) | integer 1 to 365 | "Enter 1 to 365 days." |
| "Inactive contract monitor" | `close.dq_inactive_contract_days` (CLOSE) | integer 1 to 730 | "Enter 1 to 730 days." |
| "Job concurrency" | `platform.job_concurrency` (PLATFORM) | integer 1 to 16 | "Enter 1 to 16." |
| "Audit retention" | `platform.audit_retention_years` (PLATFORM) | integer 7 to 30, years | "Enter 7 to 30 years." |
| "SSP second-approver threshold" | `approval.ssp_second_approver_threshold_ratio` (PLATFORM) | percent | "Enter a percentage from 0 to 100." |
| "Quarantine failed import rows" | `data.quarantine_failed_rows` (INTEGRATION) | checkbox with help "Off: imports commit all rows or none." | none |
| "Grouping fields" | `integration.grouping_fields` (INTEGRATION) | multi-select of canonical order fields, at most five | "Choose at most five fields." |
| "Mandatory disaggregation attributes" | `disclosure.mandatory_disaggregation_attributes` (DISCLOSURE_ELECTION) | multi-select of product attribute codes | none |
| "Comment (required)" | request comment | textarea | "Enter at least 10 characters." |

**States.** Pending request: info banner "Changes to <category labels> are waiting for approval: request <request no>." Read-only viewer: every control read-only; no submit — rev 1.102: also for a member whose `config.author` names entities (the form states versions of the tenant, which the API refuses her by name; before the item she was given the controls and her submission was accepted — 04 rev 1.309). Open version (rev 1.94): where a `DRAFT` or `TESTED` tenant version of a category of this form is open — a request withdrawn on the version's page, which returns it to `DRAFT` (SCREENS §11.3 rev 1.56), or a submission that stopped before its last command — an info banner per category reads "Version <n> of <category label> is open. Finish it on its page." with the link "Open version <n>" to SF-13:accounting-version, for every reader of the form. One version of a category is open at a time (PRD SM-04) and the form creates a new one, so "Submit for approval" reads the versions again before it sends anything and does not submit such a category: the sentence stands beside the button, and the changed categories that are free go through. The form does not continue the open version, which may hold values stated on its page. No command withdraws or deletes a `DRAFT` or `TESTED` version: it is finished on its page — the page opens by its address for the categories whose list row leads here, and a holder of `config.author` edits, tests and submits it there — and a draft nobody wants is finished by stating the values in force. Before this revision the form sent `POST /policies`, showed the refusal and gave no way to the version.

**Interactions, keyboard and copy.** "Submit for approval" toast "Submitted workspace settings for approval." Saving the workspace name is immediate: button "Save name", toast "Workspace name saved."

**Sample world.** WLD-T-01: negative amounts `PARENTHESES`; quarantine off; grouping fields order number, account id, contracting entity, currency (Salesforce integration, PRD §2.5); other values are the T-PLT-31 defaults.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Negative style | radiogroup named "Negative amounts" | `SF-15-workspace-negative-style` |
| Form | form named "Workspace settings" | `SF-15-workspace-form` |

**Light and dark.** Radio labels render the two styles in `num-money` figures.

**Accessibility.** The radio options' accessible names are "Parentheses, (4,000.00)" and "Minus sign, −4,000.00".

**Screen item *request-shred affordance* (rev 1.41; named and not built).** The erasure commands of runbook RB-14 have no screen in 1.0: `POST /files/{id}/shred` and, since 04 rev 1.142, `POST /files/{id}/request-shred` are sent to the API by a Tenant Admin (`settings.manage`). The item a frontend lane builds: where a file is shown to a holder of `settings.manage`, an action "Request shredding" for a file whose shred answers `FILE_SHRED_APPROVAL_REQUIRED` (04 table 15.4-B; PRD IMP-129) — a step-up per SCR-PERM-05, a required reason of at least 10 characters, the refusal copy of PRD IMP-128 and IMP-129 shown as the problem detail — that links to the pending request in SF-12 (SCREENS §15, screen item *EVIDENCE_SHRED request view*). Its place, route and test hooks are fixed by the revision that builds it.

### 9.7 SF-15:sandbox Sandbox copies

| Field | Value |
|---|---|
| Screen id | SF-15:sandbox |
| Route | `/settings/sandbox` (RT-84) |
| Roles and permissions | Read and create copies `tenant.snapshot` (Controller). "Reset sandbox": `sandbox.reset` (Controller), sandbox workspaces only. Step-up MFA for both (PRD ACT-50, ACT-51). Rev 1.99 (SCREENS.md §0.6 SCR-PERM-02 (c)): both are asked for all entities — a copy is a copy of the whole workspace and a reset replaces all of a sandbox. A holder of `tenant.snapshot` for named entities reads SCR-ST-06 with "Sandbox copies cover every entity of the workspace. Ask a workspace administrator for a role that includes creating sandbox copies (tenant.snapshot) for all entities." and no snapshot is read; "Reset sandbox" is not rendered for a holder of `sandbox.reset` for named entities |
| Purpose | Copy production into a sandbox, restore stored snapshots into new sandboxes, and reset a sandbox; production is never overwritten |
| REQ | REQ-PLT-022 to 025; D-01; SBX-02 to SBX-07; LTM-10 to LTM-12 |
| Journeys | J-25.1 to J-25.4, J-25-AC-1, J-25-AC-2 |

**Wireframe, 1440 px (production).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Sandbox copies                                                                                            |
| Sandbox copies                                                                                 [*Create sandbox copy]|
| A sandbox copy is a separate workspace. Nothing in a sandbox posts or exports, and production is never overwritten.  |
+----------------------------------------------------------------------------------------------------------------------+
| Sandboxes (2)                                                                                                         |
| Name                                   Known at               Status    Created by    [Open]                         |
| Avenmoor pre-close snapshot (Sandbox)  12 Sep 2026 18:10 UTC  (Active)  Marcus Webb   [Open]                         |
| Q4 2026 outlook (Scenario)             12 Sep 2026 17:02 UTC  (Active)  Jordan Blake  [Open]                         |
+----------------------------------------------------------------------------------------------------------------------+
| Stored snapshots (1)                                                                                                 |
| Snapshot    Purpose        Known at               Status       Manifest SHA-256     [Restore into a new sandbox]     |
| 5b1e…09ac   Sandbox copy   12 Sep 2026 18:10 UTC  (Succeeded)  a0c4e9d1…7e22        [Restore into a new sandbox]     |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1440 px (sandbox WLD-T-31).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Sandbox: Avenmoor pre-close snapshot (Sandbox). Nothing here posts or exports.                                       |
| Settings > Sandbox copies                                                                                            |
| This workspace is a sandbox copied from Avenmoor Holdings (Demo) as known at 12 Sep 2026 18:10 UTC.  [Reset sandbox] |
+----------------------------------------------------------------------------------------------------------------------+
```

The origin line of a sandbox (rev 1.54): "This workspace is a sandbox copied from <source name> as known at <DD MMM YYYY HH:mm UTC>."; a sandbox created empty by a reset has no `source_known_at` and reads "This workspace is an empty sandbox of <source name>."; the reader who is no member of the source workspace reads the line without the name ("This workspace is a sandbox copied as known at <…>.", "This workspace is an empty sandbox.").

**Wireframe, 1280 px.** Tables hide "Created by" and "Manifest SHA-256".

```text
+--------------------------------------------------------------------------------------------------------+
| Sandbox copies                                                               [*Create sandbox copy]    |
| Avenmoor pre-close snapshot (Sandbox)  12 Sep 2026 18:10 UTC  (Active)  [Open]                         |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-06 plain header; DS-CMP-10 static tables "Sandboxes", "Stored snapshots"; DS-CMP-11 form modals "Create sandbox copy", "Restore into a new sandbox", confirmation "Reset sandbox"; DS-CMP-24 progress rows.

**Data bindings.** The workspace's kind and origin come from the session and from `GET /me` (rev 1.54): `GET /session` `active_tenant` (id, kind) and the caller's `GET /me` memberships, whose `tenant` carries `kind`, `status`, `source_tenant_id` and `source_known_at` — `GET /tenant` needs `settings.manage` (04 API-R-17), which the reader of this screen, a Controller with `tenant.snapshot`, does not hold. `GET /tenant/snapshots` (newest first); `POST /tenant/snapshots` `{known_at, purpose: "SANDBOX_COPY", name}` → job `TENANT_SNAPSHOT`; `POST /tenant/sandboxes` `{tenant_snapshot_id, name}`; `POST /tenant/reset` `{mode: "SNAPSHOT" | "EMPTY", reason}` → job `SANDBOX_RESET` (the server resolves the sandbox's seed snapshot, 05 SBX-07); open `POST /session/tenant`. Sandboxes list from `GET /me` memberships whose tenant is a sandbox with `source_tenant_id` this workspace and is not `SUSPENDED` (a copy that is still loading is its progress row, not a list row). A reset is followed on its job until the session's active tenant is the successor (`GET /session`): the job row stays in the superseded sandbox.

**The open workspace (rev 1.54; supervisor ruling of 2026-10-01 on a PRODUCT DEFECT of the shell found with this screen).** A sandbox copy keeps the ids of the rows it copies, so the member of a workspace and of its copies holds memberships with one `membership_id`: `GET /me` `active_membership_id` does not name the workspace a session is in. The shell and every screen name it by the session — `GET /session` `active_tenant.id` — and match a `GET /me` membership by its workspace. In the switcher (SCREENS §1.3) exactly one workspace reads "Current", and choosing a copy from its source, the source from a copy, or one copy from another opens it; SF-23:select lists each workspace once. An `ARCHIVED` sandbox — the one a reset superseded — is listed neither in the switcher nor on SF-23:select; the one exception is the workspace the session is in, which the switcher always lists and marks "Current", whatever its status.

**Grid columns.** Sandboxes: "Name" (display name); "Known at" (`source_known_at`, DS-FMT-17); "Status" (§0.4 E-101 or Active); "Created by" (rev 1.54: the display name of the `created_by` API-S-Actor of the snapshot whose `target_tenant_id` is the sandbox; "—" where no listed snapshot targets it); action "Open". Stored snapshots: "Snapshot" (id prefix); "Purpose" ("Sandbox copy", "Stored backup", "Sandbox seed"); "Known at"; "Status" (E-67 chip); "Target sandbox" (name); "Manifest SHA-256" (prefix); "Created by" (the snapshot's `created_by` API-S-Actor, display name); action "Restore into a new sandbox" on a `SUCCEEDED` snapshot with a manifest.

**States.** Production SCR-ST-03 sandboxes: title "No sandbox copies"; description "Copy this workspace to rehearse a close, test a policy change or train users without touching production."; primary "Create sandbox copy". Copying: row with DS-CMP-24 "Copying <tenant name> to a sandbox". A copy that failed (rev 1.54): the SCR-ST-12 banner in place of its progress row, carrying the failed job's own sentence — its `detail`, else its first finding — where a job banner carries the problem title: a load refusal rides a general 412 whose title, "Record changed", says nothing of it. For a workspace without a snapshot retention policy in force the sentence is the copy of PRD ERR-77, which says from when copies are possible. The banner offers no "Retry": a copy is asked for again through "Create sandbox copy", which runs the step-up. Determinism mismatch after copy: warning banner with the IMP-45 sentence for the number of contracts the job counts, "Recomputing <n> contracts in the sandbox produced results that differ from the source workspace. Review them before relying on the sandbox copy." (one contract: "… <n> contract … a result that differs … Review it …").

**Interactions, keyboard and copy.**

- *Create sandbox copy* (SCR-LTH-10): fields "Name" (required), "Known at" (segmented "Now" / "A specific time"; with "A specific time" the field "Time", typed as the cut-off of a journal run is typed — `YYYY-MM-DD HH:mm`, UTC unless an offset is named, help "A time in UTC, for example 2026-09-12 18:10." — and refused in place when it has not passed; rev 1.54); consequence "The copy includes reference data, events, versions and memberships as known at the chosen time. Derived figures are recomputed in the sandbox."; buttons "Cancel", "Create sandbox copy"; step-up MFA; toast "Sandbox <name> is ready." with "Open sandbox".
- *Restore into a new sandbox* (SCR-LTH-11): fields "Name"; consequence "A new sandbox is created from this snapshot. Production is not changed."; buttons "Cancel", "Restore into a new sandbox".
- *Reset sandbox* (SCR-LTH-12; sandbox only; SB-R-05): radio group "Reset to" with "Back to the copy taken on <DD MMM YYYY HH:mm UTC>" / "Empty workspace" (a sandbox that was created empty has no copy to go back to and offers "Empty workspace" alone; rev 1.54); "Reason (required)"; consequence "The current sandbox is archived and a new sandbox replaces it. No data is deleted."; Danger "Reset sandbox". In production the button is not rendered (J-25.4); the API answers 409 `production-reset-forbidden` with ERR-25 copy.

**Sample world (asserted).** J-25.1: `marcus` creates "Avenmoor pre-close snapshot", known at now; WLD-T-31 created; audit events in both workspaces. J-25.2: in the sandbox `PRJ-CB-2026-01` cumulative revenue 829,852.94. J-25.3: reset "Back to the copy taken on <timestamp>" with reason "Rehearsal complete". J-25.4: production shows no Reset; "Restore" creates a new sandbox.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Create button | button named "Create sandbox copy" | none |
| Sandboxes table | table named "Sandboxes" | `SF-15-grid-sandboxes` |
| Snapshots table | table named "Stored snapshots" | `SF-15-grid-snapshots` |
| Reset button | button named "Reset sandbox" | none |

**Light and dark.** Sandbox banner and top line in both themes.

**Accessibility.** The reset confirmation is an `alertdialog`; initial focus "Cancel".

### 9.8 SF-15:notifications Notification preferences

| Field | Value |
|---|---|
| Screen id | SF-15:notifications |
| Route | `/settings/notifications` (RT-72) |
| Roles and permissions | Authenticated; each user edits only their own preferences |
| Purpose | Choose in-app and email delivery per notification kind |
| REQ | REQ-PLT-021; PRD §5.4 NTF-R2, NTF-R3 |
| Journeys | none (covered by `screens.spec.ts`) |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Notification preferences                                                                                  |
| Notifications   Profile                                                                                              |
+----------------------------------------------------------------------------------------------------------------------+
| Notification                                   When it is sent                                   In app   Email      |
| Approval assigned to you                       A step becomes active for an item you can approve  [on]    [on]       |
| Your item was approved                         An item you prepared is approved                   [on]    [off]      |
| ...                                                                                                                  |
| Audit chain verification failed                The audit chain verification fails                 [on]    [on]  (i)  |
| Emails contain the object reference and a link, never amounts or customer data.                                      |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** "When it is sent" wraps under the notification name.

```text
+--------------------------------------------------------------------------------------------------------+
| Approval assigned to you                                                            [on]    [on]       |
|   A step becomes active for an item you can approve                                                    |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Group route tabs; DS-CMP-10 static table with DS-CMP-21 switches (immediately applied preferences, DS-CMP-21).

**Data bindings.** `GET /me/notification-preferences`; `PUT /me/notification-preferences` with the full list after each change.

**Grid columns.**

| `notification_kind` | Notification | When it is sent |
|---|---|---|
| `APPROVAL_ASSIGNED` | "Approval assigned to you" | "A step becomes active for an item you can approve" |
| `ITEM_APPROVED` | "Your item was approved" | "An item you prepared is approved" |
| `ITEM_REJECTED` | "Your item was rejected" | "An item you prepared is rejected" |
| `APPROVAL_VOIDED` | "An approval request was voided" | "An item changed after submission or was withdrawn" |
| `JOB_FAILED` | "A job failed" | "A job you started fails; for close runs, Controllers of the entity" |
| `PERIOD_LOCKED` | "A period was locked" | "A period of an entity in your scope is locked" |
| `PERIOD_REOPENED` | "A period was reopened" | "A period of an entity in your scope is reopened" |
| `CLOSE_BLOCKER_RAISED` | "A close blocker was raised" | "A new blocker appears for a period in soft close" |
| `CHAIN_VERIFICATION_FAILED` | "Audit chain verification failed" | "The audit chain verification fails" |
| `EXPORT_FAILED` | "A journal export failed" | "A journal batch or run fails to export" |
| `EXCEPTION_ASSIGNED` | "An exception was assigned to you" | "An exception is created for you or assigned to you" |
| `SUPPORT_GRANT_REQUESTED` | "Support access was requested" | "A platform operator requests support access" |

Columns "In app" (`in_app`) and "Email" (`email`) are switches. The `CHAIN_VERIFICATION_FAILED` switches have `aria-disabled="true"` with the tooltip "Audit chain failures are always sent in the app and by email." (NTF-R2). Defaults are the T-PLT-25 email defaults.

**States.** Saving: the switch shows its busy state; failure reverts the switch and shows the toast "Could not save the preference. Try again."

**Sandbox (rev 1.54; 05 SBX-08, item SBX-EMAIL-1).** A notification raised in a sandbox is delivered in the app only. In a sandbox workspace — the session's `active_tenant.kind` — every "Email" switch is off and `aria-disabled="true"` with the tooltip "No email is sent from a sandbox workspace."; the stored email preferences are not shown there, and a change of an "In app" switch sends them as stored. The `CHAIN_VERIFICATION_FAILED` "In app" switch stays on and `aria-disabled` with the tooltip "Audit chain failures are always sent in the app." The footnote reads "A sandbox sends no email. Notifications raised in this workspace are delivered in the app only."

**Interactions, keyboard and copy.** Space toggles; toast "Preferences saved." at most once per 5 seconds; footnote "Emails contain the object reference and a link, never amounts or customer data." (NTF-R3).

**Sample world.** Seed defaults for every demo user.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Table | table named "Notification preferences" | `SF-15-grid-notification-preferences` |
| Row | row header "<notification>" | `SF-15-row-<kind normalised>` (for example `SF-15-row-approval-assigned`) |

**Light and dark.** Switch tracks in both themes.

**Accessibility.** Switches named "<notification>, in app" and "<notification>, email".

### 9.9 SF-15:profile Profile

| Field | Value |
|---|---|
| Screen id | SF-15:profile |
| Route | `/settings/profile` (RT-73) |
| Roles and permissions | Authenticated |
| Purpose | The user's security (password, MFA, recovery codes), formats and display preferences, and memberships |
| REQ | REQ-PLT-004, 005; REQ-UX-008, 022; DS-DEN-01; DS-I18N-02; DS-CMP-01 |
| Journeys | J-24-AC-2 (tour preference) |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Profile                                                                                                   |
| Notifications   Profile                                                                                              |
+----------------------------------------------------------------------------------------------------------------------+
| Maya Chen · maya@demo.erev                                                                                           |
| Sign-in and security                                                                                                 |
|   Password                    Last changed 01 Sep 2026                                   [Change password]           |
|   Multi-factor authentication Enrolled 01 Sep 2026 · 10 recovery codes issued              [Regenerate recovery codes]|
| Formats and display                                                                                                  |
|   Number format               {English (United States) v}   Example 1,234,567.89                                     |
|   Theme                       (System | Light | Dark)                                                                |
|   Density                     (Comfortable | Compact)                                                                |
|   Single-key shortcuts        [on]                                                                                   |
| Workspaces                                                                                                           |
|   Avenmoor Holdings (Demo)    Revenue Accountant, SSP Analyst · All entities                                         |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** As 1440 px at `--content-max-form`.

```text
+--------------------------------------------------------------------------------------------------------+
| Password  Last changed 01 Sep 2026                                              [Change password]      |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Definition lists; DS-CMP-20 buttons; DS-CMP-21 select; DS-CMP-31 segmented controls and a switch (immediately applied); DS-CMP-11 dialog "Recovery codes"; SCR-PERM-05 step-up.

**Data bindings.** `GET /me`; preferences `PATCH /me/preferences` with any of `format_locale`, `theme` (E-123 `SYSTEM`, `LIGHT`, `DARK`), `density` (E-124 `COMFORTABLE`, `COMPACT`) and `shortcuts_enabled` → 200 `{preferences}` (04 API-R-03, §16.12; OQ-B-20 resolved by D-76); `POST /me/recovery-codes` (step-up) → ten codes shown once.

**Grid columns.** None.

**States.** Not enrolled in MFA (optional for the user's roles): text "Not enrolled" with button "Set up multi-factor authentication" (SF-22:mfa-enrol).

**Interactions, keyboard and copy.** "Change password" opens SF-22:password-change. "Regenerate recovery codes": confirmation "Regenerate recovery codes?" with consequence "Your current recovery codes stop working."; then the dialog "Recovery codes" listing ten codes (mono) with "Copy codes", "Download codes (TXT)" and the required checkbox "I have stored these recovery codes" before "Done". Theme, density and shortcut changes apply at once and persist to `erev.theme` and `erev.density` (DS-DEN-01).

**Sample world.** Demo users enrolled per WLD-U-R2.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Security section | region named "Sign-in and security" | `SF-15-profile-security` |
| Recovery codes dialog | dialog named "Recovery codes" | `SF-15-drawer-recovery-codes` |
| Theme control | radiogroup named "Theme" | none |

**Light and dark.** The theme control previews the effect immediately; verify both.

**Accessibility.** Recovery codes are a list; the acknowledgement checkbox is required before "Done" is enabled for pressing, with the visible reason "Confirm that you stored the codes."

### 9.10 SF-14 Users and SF-14:user User

| Field | Value |
|---|---|
| Screen ids | SF-14; SF-14:user (SCREENS.md §0.4; §14) |
| Routes | `/settings/users` (RT-87) with `f.status`, `q`; `/settings/users/:membershipId` |
| Roles and permissions | Read `user.manage` (Tenant Admin). Invite, suspend, reactivate, remove, resend invitation, reset MFA: `user.manage` (step-up for reset MFA). Add or revoke roles, request SoD exceptions: `role.manage`. Approvals of assignments and exceptions: `access.approve` by another Tenant Admin in SF-12. For which entities each is held decides what is offered (rev 1.60; "The scope a grantor may give" and "Commands on what is granted" below) |
| Purpose | Invite members, assign scoped roles with preventive SoD checks, and suspend or remove memberships |
| REQ | REQ-PLT-004, 005, 008, 010, 011, 012; REQ-CTL-006; BR-PLT-02 |
| Journeys | J-01.3, J-22.1, J-22.6, J-22.7, J-22.9, J-22.12, J-22-AC-1 |

**Wireframe, 1440 px (SF-14).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Users                                                                                                     |
| Users   Roles   Separation of duties   Access reviews   Security   Support access                                    |
+----------------------------------------------------------------------------------------------------------------------+
| 12 members                                                               [Download access listing]  [*Invite user]   |
| Name              Email                 Status      Roles                                  Scope        MFA  Last login |
| Maya Chen         maya@demo.erev        (Active)    <Revenue Accountant> <SSP Analyst>     All entities Yes  12 Sep 2026|
| Lena Fischer      lena@demo.erev        (Invited)   <Revenue Reviewer> (Pending approval)   AVM-DE       No   Never     |
| ...                                                                                                                  |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1440 px (SF-14:user, J-22.6).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Users > Lena Fischer                                                                                      |
| Lena Fischer · lena@demo.erev   (Active)                                  [Reset MFA]  [Suspend]  [*Add role]  ...  |
+----------------------------------------------------------------------------------------------------------------------+
| Roles                                                                                                                |
| Role               Scope    Status     Granted               Granted by     SoD exception                            |
| Revenue Reviewer   AVM-DE   (Active)   12 Sep 2026 19:02 UTC Grace Okafor   —                                        |
| [!] Separation of duties conflict SoD-3: Revenue Accountant with Revenue Reviewer lets one person create and         |
|     approve the same contract or modification.                                          [Request an exception]       |
| Security  MFA enrolled 12 Sep 2026 · Failed sign-ins 0 · Account not locked                                          |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** Users grid hides "Last login" and "MFA"; the user page stacks sections.

```text
+--------------------------------------------------------------------------------------------------------+
| Lena Fischer (Invited) <Revenue Reviewer> (Pending approval)  AVM-DE                                   |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-10 DataGrid "Members"; DS-CMP-09 modal drawers "Invite user", "Add role", "Request SoD exception"; DS-CMP-06 record header on SF-14:user; DS-CMP-10 static table "Roles"; DS-CMP-29 negative banner for SoD conflicts (ERR-22); DS-CMP-11 confirmations.

**Data bindings.** `GET /users?status&q&count=true`; `POST /users` `{email, display_name, roles: [{role_id, is_all_entities, entity_codes}]}` (creates the membership and role-assignment requests); `GET /users/{membership_id}`; `POST /users/{id}/suspend`, `/reactivate`, `/remove`, `/reset-mfa`, `/resend-invitation`; `GET, POST /role-assignments` `{membership_id, role_id, is_all_entities, entity_codes, sod_exception_id}`; `POST /role-assignments/{id}/revoke` `{reason}`; `POST /sod-exceptions` `{sod_rule_code, membership_id, compensating_control, valid_from, valid_to, comment}`.

**Grid columns: members.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Name | `display_name` | text link | SF-14:user |
| Email | `email` | mono | none |
| Status | `status` | §0.4 E-78 chip | none |
| Roles | active and requested assignments | outline chips per role; requested ones followed by chip Pending approval | none |
| Scope | entity scope | "All entities" or codes | none |
| MFA | enrolled | "Yes" / "No"; "Not shown" for an invited or a removed member (rev 1.105) | none |
| Last login | `last_login_at` | DS-FMT-17; "Never"; "Not shown" for an invited or a removed member (rev 1.105) | none |
| Invited | `invited_at` | DS-FMT-16 | none |

**Grid columns: roles (SF-14:user).** "Role" (name); "Scope"; "Status" (§0.4 SMAP-14); "Granted" (DS-FMT-17); "Granted by" (user, or outline chip "Setup grant" for `AUTO-BOOTSTRAP`); "Approval" (request link); "SoD exception" (id prefix link); "Revoked" (DS-FMT-17); action "Revoke role" (SB-R-05).

**States.** SCR-ST-04 "No members match these filters". Suspended user page: warning banner "This membership is suspended. The user's sessions ended on <timestamp>." An invited or a removed member (rev 1.105; item IDENTITY-WITHHELD-BY-STATUS-1; 04 T-PLT-02 rev 1.316): API-S-User answers `sign_in_withheld` true, and its `last_login_at` and `mfa_enrolled` are null because they are not shown. The grid then reads "Not shown" in "MFA" and in "Last login" — never "No" or "Never", which say of a member that there is no factor and no sign-in — and the user page's Security section reads "MFA and last sign-in are not shown while a membership is invited or removed." The name is the email unless this workspace's invitation added the person to eRev; an erased person reads `Erased user <8 hex>` in every workspace (05 PRV-07 a).

**Interactions, keyboard and copy.**

- *Invite user*: fields "Email", "Display name", "Roles" (repeatable rows "Role" select and "Scope" radio "All entities" / "Selected entities" with a multi-select); live SoD check on each change shows the ERR-22 banner inside the drawer; buttons "Cancel", "Send invitation". The inviter sees no Approve action on the request (J-22.1). Toast "Invitation for <email> is waiting for approval." When rule `AUTO-BOOTSTRAP` approved every role of the invitation at once — the bootstrap Tenant Admin during setup, while no other person has been active with `access.approve` (rev 1.29; 04 §14.3 rev 1.104; supervisor rulings R-38 (iv) and R-66 (2)) — the toast reads "Invitation sent. Setup grants are approved by rule AUTO-BOOTSTRAP." (BR-PLT-02); an invitation by another Tenant Admin, or after a second access approver has existed, shows the first toast although `setup_completed_at` is still null.
- *Add role*: same role and scope fields; a conflict blocks with "Separation of duties conflict <rule>: <description>." and the action "Request an exception" (ERR-22).
- *The scope a grantor may give (rev 1.60; 04 T-PLT-10 rev 1.148; SCREENS §0.6 SCR-PERM-02 rev 1.30).* Nobody grants beyond their own access. The scope field offers the entities the grantor's own permission covers — `user.manage` in "Invite user", `role.manage` in "Add role" (API-S-Me `permission_scopes`). A grantor of all entities sees the field as before. A grantor of named entities is offered "Selected entities" alone, chosen, with those entities in the multi-select and under the field the line "Your own access covers named entities only. Choose from those entities, not all entities.", the sentence the API answers to an all-entities grant from such a grantor (422, rule `T-PLT-10`, on `is_all_entities`). The API's findings on a scope are shown under the scope field of their row and nowhere else: `roles[<n>].entity_codes` and `roles[<n>].is_all_entities` of `POST /users`, `entity_codes` and `is_all_entities` of `POST /role-assignments` ("Choose at least one entity, or all entities.", "Choose all entities or named entities, not both.", "Choose entities that exist in this workspace." — the last also for an entity outside the grantor's scope, which the API does not tell apart).
- *Commands on what is granted (rev 1.60; 04 T-PLT-10).* "Suspend", "Reactivate", "Remove", "Reset MFA", "Resend invitation" and the edit of a member render when the viewer's `user.manage` covers every entity the member's roles that are not revoked name, and all entities when one of them is for all; a member without a role is covered by every holder. "Revoke role" renders on a role the viewer's `role.manage` covers in the same sense; "Add role" renders for `role.manage` held for any entity. The API shows a viewer the entities of a role that the viewer's session sees, so a role that also names an entity outside it looks covered: the command is offered and the API refuses it by name (403, rule `T-PLT-10`; SCR-PERM-05).
- *Request SoD exception* (SB-R-05 reason rule applies to "Compensating control"): fields "Rule" (read-only), "Compensating control (required)", "Valid from", "Valid to" (dates; the window is sent as 00:00:00Z of "Valid from" to 23:59:59Z of "Valid to", DESIGN_SYSTEM DS-I18N-08, and lasts at most 366 days, so "Valid to" is at most 365 days after "Valid from": "Choose a validity of at most 366 days."; rev 1.30, supervisor ruling R-59), "Comment (required)"; buttons "Cancel", "Request exception". The assignment request then carries the exception.
- *Suspend* (SB-R-05): consequence "Suspending <name> ends every session immediately. The membership and its history remain."; Danger "Suspend member". *Remove*: consequence "Removing <name> ends access to this workspace. History is kept."; Danger "Remove member". *Reset MFA*: consequence "<name> must enrol again at the next sign-in. Every session of the user ends."; Danger "Reset MFA"; step-up.
- SoD-1 on self-assignment copy (J-22.9): "Separation of duties conflict SoD-1: user administration with transaction or approval permissions."

**Sample world (asserted).** J-22.1: `tomas` invites Lena Fischer, `lena@demo.erev`, Revenue Reviewer, scope AVM-DE; request pending. J-22.6: adding Revenue Accountant is blocked with the SoD-3 copy of the wireframe. J-22.7: exception with compensating control "Controller reviews every approval by Lena Fischer monthly using the approvals register." for 90 days; `grace` approves both; assignment active with `sod_exception_id`. J-22.9: `tomas` assigning himself Controller is blocked with SoD-1. J-22.12: `tomas` suspends Lena; her next request returns to sign-in. J-01.3 (WLD-T-20): four invitations approved by `AUTO-BOOTSTRAP`.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Members grid | grid named "Members" | `SF-14-grid-members` |
| Member row | row header "<name>" | `SF-14-row-<email normalised>` (for example `SF-14-row-lena-demo-erev`) |
| Invite drawer | dialog named "Invite user" | `SF-14-drawer-invite` |
| SoD banner | alert "Separation of duties conflict …" | `SF-14-banner-sod-conflict` |
| Roles table | table named "Roles" | `SF-14-grid-user-roles` |
| Exception drawer | dialog named "Request SoD exception" | `SF-14-drawer-sod-exception` |

**Light and dark.** Negative SoD banner inside the drawer on `--bg-raised`.

**Accessibility.** The SoD banner is inserted after load, so it is `role="alert"`; focus moves to "Request an exception".

### 9.11 SF-14:roles Roles

| Field | Value |
|---|---|
| Screen id | SF-14:roles |
| Route | `/settings/roles` (RT-88) with `drawer=role` |
| Roles and permissions | Read `role.manage`. Propose a custom role or a change: `role.manage` (approval `ROLE_CHANGE` by `access.approve`). A role's definition is a tenant-wide act (rev 1.60; 04 T-PLT-10 rev 1.148): "New role" and "Propose change" render for `role.manage` held for all entities; a holder for named entities reads the roles and is offered neither |
| Purpose | View default roles and their permissions, and propose custom roles under approval with SoD checks |
| REQ | REQ-PLT-008, 009, 010; T-PLT-09, T-PLT-11, T-PLT-12 |
| Journeys | J-22 (role labels) |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Roles                                                                                                     |
| Users   Roles   Separation of duties   Access reviews   Security   Support access                                    |
+-----------------------------------------------------------------------------+----------------------------------------+
| 11 roles                                              [Download role matrix] [*New role] | Revenue Reviewer    [X] |
| Role                 Code                System  Permissions  Members  Active | Code revenue_reviewer · System |
| Revenue Accountant   revenue_accountant  Yes     21           1        Yes    | Contracts                       |
| Revenue Reviewer     revenue_reviewer    Yes     16           2        Yes    |  contract.read      View contr… |
| Deal desk analyst    deal_desk_analyst   No      3            1        Yes    |  contract.approve   Approve … MFA Approval |
+-----------------------------------------------------------------------------+----------------------------------------+
```

**Wireframe, 1280 px.** The role drawer overlays the grid.

```text
+--------------------------------------------------------------------------------------------------------+
| Revenue Reviewer  revenue_reviewer  Yes  16  2  Yes                                                    |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-10 DataGrid "Roles"; DS-CMP-09 docked informational drawer (permission list grouped by area); DS-CMP-09 modal drawer "New role" with checkbox groups.

**Data bindings.** `GET /roles`; `GET /roles/{id}`; `GET /permissions`; `POST /roles` `{code, name, description, permissions}`; `POST /roles/{id}/propose-change` `{permissions, comment}`; role matrix download: RPT-24 section "Role matrix" (OQ-B-21).

**Grid columns.** "Role" (name link opens drawer); "Code" (mono); "System" (Yes/No); "Permissions" (count); "Members" (count); "Active" (Yes/No). Drawer permission rows: "Permission" (code, mono), "Description", flags as outline chips "Approval", "Access admin", "MFA" (T-PLT-11 `is_approval`, `is_access_admin`, `requires_mfa`).

**States.** SCR-ST-03 is not reachable (system roles always exist).

**Interactions, keyboard and copy.** *New role*: fields "Name", "Code" ("Use lowercase letters and underscores."), "Description", permissions as checkbox groups by area; approval permissions show the note "Holding an approval permission forces multi-factor authentication."; a checked pair that matches an SoD rule shows the warning "This role combines <function A> with <function B> (SoD <n>). Members will need an exception." with "I have reviewed this warning"; buttons "Cancel", "Submit for approval". System roles show no edit control and the tooltip "System roles cannot change."

**Sample world.** Ten default roles (T-PLT-09) plus the Avenmoor custom role "Deal desk analyst" with `scenario.use` (PRD §1.2).

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Roles grid | grid named "Roles" | `SF-14-grid-roles` |
| Role row | row header "<role name>" | `SF-14-row-<code normalised>` |
| Role drawer | complementary region named "<role name>" | `SF-14-drawer-role` |

**Light and dark.** Outline chips.

**Accessibility.** Checkbox groups are `fieldset`s with the area label as legend.

### 9.12 SF-14:sod Separation of duties

| Field | Value |
|---|---|
| Screen id | SF-14:sod |
| Route | `/settings/separation-of-duties` (RT-89) with `pane=rules|exceptions` |
| Roles and permissions | Read `role.manage`. Propose a rule version: `role.manage` (configuration lifecycle). Revoke an exception: `role.manage` |
| Purpose | Show the SoD rules and the approved exceptions with compensating controls and validity |
| REQ | REQ-PLT-010, 011; T-PLT-13, T-PLT-14; research 07 §5.8 |
| Journeys | J-22.6 to J-22.8 |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Separation of duties                                                          [SoD conflict report]       |
| Users   Roles   Separation of duties   Access reviews   Security   Support access                                    |
+----------------------------------------------------------------------------------------------------------------------+
| Rules   Exceptions                                                                                                   |
| User           Rule    Compensating control                                    Valid from   Valid to     Status      |
| Lena Fischer   SoD-3   Controller reviews every approval by Lena Fischer …      12 Sep 2026  11 Dec 2026  (Approved)  |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** "Compensating control" wraps to two lines.

```text
+--------------------------------------------------------------------------------------------------------+
| Lena Fischer  SoD-3  (Approved)  12 Sep 2026 – 11 Dec 2026                                             |
|   Controller reviews every approval by Lena Fischer monthly using the approvals register.              |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-07 panel tabs "Rules" · "Exceptions"; DS-CMP-10 DataGrids; DS-CMP-09 informational drawer for an exception; DS-CMP-11 confirmation "Revoke exception".

**Data bindings.** `GET /sod-rules`; `POST /sod-rules/{code}/versions`; `GET /sod-exceptions?status`; `POST /sod-exceptions/{id}/revoke` `{reason}`; link to RPT-25.

**Grid columns.** Rules: "Rule" (`code`, mono); "Name"; "Function A permissions" (codes); "Function B permissions" (codes); "Rationale"; "Version" ("v<n>"); "Status" (SCREENS.md §0.8 E-12 chip). Exceptions: "User"; "Rule" (mono); "Compensating control"; "Valid from" (DS-FMT-16); "Valid to" (DS-FMT-16); "Status" (§0.4 E-96 chip); "Approval" (request link); action "Revoke exception".

**States.** Exceptions SCR-ST-03: title "No SoD exceptions"; description "Approved exceptions allow a conflicting role combination for a limited time with a compensating control."

**Interactions, keyboard and copy.** *Revoke exception* (SB-R-05): consequence "Revoking the exception blocks the conflicting role assignment. Revoke the role first or it becomes a conflict without an exception."; Danger "Revoke exception".

**Sample world.** Rules SoD-1 to SoD-7 seeded per tenant (T-PLT-13). J-22.7 (asserted): Lena Fischer SoD-3 exception with the compensating control of §9.10, 90 days.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Rules grid | grid named "SoD rules" | `SF-14-grid-sod-rules` |
| Exceptions grid | grid named "SoD exceptions" | `SF-14-grid-sod-exceptions` |

**Light and dark.** Chips only.

**Accessibility.** Panel tabs APG Tabs.

### 9.13 SF-14:access-reviews Access reviews and SF-14:access-review Campaign

| Field | Value |
|---|---|
| Screen ids | SF-14:access-reviews; SF-14:access-review (SCREENS.md §0.4; §14) |
| Routes | `/settings/access-reviews` (RT-90); `/settings/access-reviews/:reviewId` |
| Roles and permissions | Read, start, decide, complete `access.approve` (Tenant Admin); a reviewer never reviews their own membership (DB-10). Rev 1.99 (SCREENS.md §0.6 SCR-PERM-02 (c); 04 T-PLT-40): `access.approve` is asked for all entities on both pages — a campaign reviews the members of the whole workspace. A holder for named entities reads SCR-ST-06 with "Access reviews cover every entity of the workspace. Ask a workspace administrator for a role that includes approving access (access.approve) for all entities." and neither the campaigns nor a campaign is read. "Reviewers" of "New campaign" offers the active members who hold `access.approve` for all entities by a role assignment of their own, the ones the API takes |
| Purpose | Run access review campaigns that snapshot users, roles, scopes, last login, grant date and grantor, certify or revoke per user and track revocations to completion |
| REQ | REQ-CTL-006; T-PLT-40, T-PLT-41; research 07 AC-04, A-15 |
| Journeys | J-22.11 |

**Wireframe, 1440 px (SF-14:access-review).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Access reviews > Q3 2026 access review                                                                    |
| Q3 2026 access review   (In review)   As of 12 Sep 2026 20:00 UTC · Reviewers Grace Okafor   [Download snapshot] [*Complete campaign]|
| Key figures  Members 13 │ Certified 9 │ Revocations requested 1 │ Revocations completed 1 │ Pending 3                 |
+----------------------------------------------------------------------------------------------------------------------+
| Member        Roles at snapshot                               Last login   Granted by    Decision                     |
| Lena Fischer  Revenue Reviewer (AVM-DE); Revenue Accountant   12 Sep 2026  Grace Okafor  (Revocation requested)       |
|               (AVM-DE, SoD exception)                                                    [Confirm revocation]         |
| Maya Chen     Revenue Accountant; SSP Analyst (All entities)  12 Sep 2026  seed          [Certify] [Request revocation]|
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** "Granted by" moves under "Roles at snapshot".

```text
+--------------------------------------------------------------------------------------------------------+
| Lena Fischer (Revocation requested)  [Confirm revocation]                                              |
|   Revenue Reviewer (AVM-DE); Revenue Accountant (AVM-DE, SoD exception) · last login 12 Sep 2026        |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** SF-14:access-reviews: DS-CMP-10 DataGrid "Campaigns"; DS-CMP-11 form modal "New campaign". SF-14:access-review: DS-CMP-06 record header with KPI strip; DS-CMP-10 DataGrid "Items"; DS-CMP-11 confirmations.

**Data bindings.** `GET, POST /access-reviews` `{name, as_of, reviewer_membership_ids}`; `POST /access-reviews/{id}/start`, `/complete`, `/cancel`; `GET /access-reviews/{id}/items`; `POST /access-reviews/{id}/items/{item_id}/decide` `{decision: "CERTIFIED" | "REVOKE_REQUESTED", comment}`; `POST /access-reviews/{id}/items/{item_id}/confirm-revocation`; snapshot `GET /files/{snapshot_file_id}/content`.

**Grid columns.** Campaigns: "Name" (link); "Status" (§0.4 E-107); "As of" (DS-FMT-17); "Reviewers"; "Members" (count); "Decided" ("<n> of <m>"); "Revocations completed" (count); "Started"; "Completed". Items: "Member" (`user_email_snapshot` with display name); "Roles at snapshot" (`roles_snapshot[]` "<role> (<scope>)" joined with "; "); "Last login" (`last_login_at`; "Never" when null — since rev 1.105 the null of an item of an invited member also means that the last sign-in is not shown, the item stores no status to tell the two apart, and the screen prints "Never" for either: a stated limit, 04 T-PLT-02 rev 1.316); "Granted" (earliest `granted_at`); "Granted by" (`granted_by`); "Decision" (§0.4 E-108 chip); "Reviewer"; "Decided" (DS-FMT-17); "Comment"; "Revocation completed" (DS-FMT-17); actions "Certify", "Request revocation", "Confirm revocation".

**States.** Campaigns SCR-ST-03: title "No access reviews yet"; description "A campaign snapshots every membership and its roles so reviewers can certify or revoke access."; primary "New campaign". Own membership row: text "You cannot review your own access." instead of actions. Completing with pending items: "Decide <n> pending items before completing the campaign."

**Interactions, keyboard and copy.** *New campaign*: fields "Name", "As of" (timestamp), "Reviewers" (members holding `access.approve`); buttons "Cancel", "Create campaign", then "Start review". *Request revocation*: "Comment (required)", minimum 10 characters; the role is then revoked in SF-14:user; "Confirm revocation" records completion. *Complete campaign*: confirmation "Complete <name>? The certification is kept as evidence."

**Sample world (asserted, J-22.11).** `grace` starts "Q3 2026 access review"; snapshot rows with roles, entity scopes, last login, grant date and grantor; Lena Fischer's Revenue Accountant revocation tracked to completed.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Campaigns grid | grid named "Campaigns" | `SF-14-grid-access-reviews` |
| Items grid | grid named "Items" | `SF-14-grid-access-review-items` |
| Item row | row header "<member>" | `SF-14-row-<email normalised>` |

**Light and dark.** KPI strip neutral figures.

**Accessibility.** Decision buttons named "Certify <member>" and "Request revocation for <member>".

### 9.14 SF-14:security Security and SF-14:support-access Support access

| Field | Value |
|---|---|
| Screen ids | SF-14:security; SF-14:support-access |
| Routes | `/settings/security` (RT-91); `/settings/support-access` (RT-92; NTF-12 link) |
| Roles and permissions | Security: read and submit `settings.manage` (registry category SECURITY, approval `REGISTRY_VERSION`). Support access: read `support_grant.approve`; decisions in SF-12 (`SUPPORT_GRANT`); revoke `support_grant.approve`. Rev 1.99 (SCREENS.md §0.6 SCR-PERM-02 (c); for Security the supervisor's ruling of 2026-10-02 02:43): each permission is asked for all entities. A holder for named entities reads SCR-ST-06 — "Security covers every entity of the workspace. Ask a workspace administrator for a role that includes managing workspace settings (settings.manage) for all entities.", "Support access covers every entity of the workspace. Ask a workspace administrator for a role that includes approving support access (support_grant.approve) for all entities." — and no grant is read |
| Purpose | Security settings (session timeout, role-assignment approval), sign-in methods and password rules; tenant-approved, time-boxed operator support grants |
| REQ | REQ-PLT-004 to 007, 036; SAR-06, SAR-10, SAR-29 |
| Journeys | J-22.10 (lockout rule shown); NTF-12 landing |

**Wireframe, 1440 px (SF-14:security).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Security                                                                                                  |
| Users   Roles   Separation of duties   Access reviews   Security   Support access                                    |
+----------------------------------------------------------------------------------------------------------------------+
| Sessions                                                                                                             |
|   Idle timeout                      30 minutes                                                                       |
|   Role assignments need approval    [x]                                                                              |
|   Comment (required) ______________________________                                    [*Submit for approval]        |
| Sign-in methods                                                                                                      |
|   Email and password  (Active)    OIDC  none configured                                                              |
| Password rules                                                                                                       |
|   At least 12 characters · not your email address · not a common password · five failed attempts lock for 15 minutes |
| Multi-factor authentication                                                                                          |
|   Required for members holding approval, lock, access administration, integration or sandbox permissions.            |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1440 px (SF-14:support-access).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Support access                                                                                            |
| [i] Support access requested by operator Ari Lang: read-only from 13 Sep 2026 09:00 UTC to 13 Sep 2026 17:00 UTC.     |
|     Review in Approvals >                                                                                            |
| Operator    Scope      Reason                     Ticket     Valid from             Valid to               Status    |
| Ari Lang    Read-only  Investigate export failure SUP-2291   13 Sep 2026 09:00 UTC  13 Sep 2026 17:00 UTC  (Pending approval)|
+----------------------------------------------------------------------------------------------------------------------+
```

The operator name and ticket in the support-access wireframe are illustrative; no support grant is seeded.

**Wireframe, 1280 px.** Both pages at `--content-max-form`; the grants table hides "Ticket".

```text
+--------------------------------------------------------------------------------------------------------+
| Ari Lang  Read-only  13 Sep 2026 09:00 – 17:00 UTC  (Pending approval)                                 |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Security: DS-CMP-21 form; definition lists; DS-CMP-19 chips. Support access: DS-CMP-29 info banner per pending request; DS-CMP-10 DataGrid "Support grants"; DS-CMP-11 confirmation "Revoke support access".

**Data bindings.** Security: `GET /policies/resolve?key=platform.session_idle_minutes`, `platform.role_assignment_requires_approval`; submit `POST /policies` `{category: "SECURITY", scope: "TENANT", values}` → `/test` → `/submit`. Sign-in methods: identity providers are global and listed read-only from `GET /session` `capabilities.identity_providers [{code, name}]` (04 API-S-Session, B3-D15). Support access: `GET /support-grants?status`; `POST /support-grants/{id}/revoke` `{reason}`; audit link `/reports/audit-log?f.support_grant=is:<id>`.

**Grid columns: support grants.** "Operator" (name); "Scope" ("Read-only"); "Reason"; "Ticket" (mono); "Valid from", "Valid to" (DS-FMT-17; at most 72 hours apart); "Status" (§0.4 E-96); "Approval" (request link); "Approved" (DS-FMT-17); "Revoked" (DS-FMT-17); actions "Revoke" (approved and unexpired grants), "View operator activity" (audit log filtered).

| Security field | Registry key | Control | Validation copy |
|---|---|---|---|
| "Idle timeout" | `platform.session_idle_minutes` | integer 5 to 240, minutes | "Enter 5 to 240 minutes." |
| "Role assignments need approval" | `platform.role_assignment_requires_approval` | checkbox | none |
| "Comment (required)" | request comment | textarea | "Enter at least 10 characters." |

**States.** Support grants SCR-ST-03: title "No support access"; description "A platform operator can read this workspace only under a grant that a workspace administrator approves, for at most 72 hours. Every operator action is logged here and in the audit log."

**Interactions, keyboard and copy.** *Revoke support access* (SB-R-05): consequence "The operator's sessions end immediately."; Danger "Revoke support access". Security submit toast "Submitted security settings for approval."

**Sample world.** WLD-T-01: idle timeout 30 minutes, absolute 12 hours, role assignments require approval (PRD §2.5). No support grants seeded.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Security form | form named "Sessions" | `SF-14-security-form` |
| Password rules | region named "Password rules" | `SF-14-security-password-rules` |
| Grants grid | grid named "Support grants" | `SF-14-grid-support-grants` |
| Pending banner | status "Support access requested …" | `SF-14-banner-support-request` |

**Light and dark.** Info banners.

**Accessibility.** Password rules are a list.

### 9.15 SF-16:developer API clients and webhooks

| Field | Value |
|---|---|
| Screen id | SF-16:developer |
| Route | `/settings/developer` (RT-93) with `pane=api-clients|webhooks|openapi` |
| Roles and permissions | Read any of `api_client.manage` (Tenant Admin) or `webhook.manage` (Integration Admin); the API clients tab needs `api_client.manage` (step-up to create or rotate); the webhooks tab needs `webhook.manage`; the OpenAPI tab is readable by either. Rev 1.99 (SCREENS.md §0.6 SCR-PERM-02 (c)): `webhook.manage` is asked for all entities — an endpoint receives the events of the whole workspace — and `api_client.manage` for any entity. A holder of `webhook.manage` for named entities alone reads SCR-ST-06 with "Webhooks cover every entity of the workspace. Ask a workspace administrator for a role that includes managing webhooks (webhook.manage) for all entities."; beside `api_client.manage` the Webhooks tab is unavailable with the reason "The Webhooks tab needs a role that includes managing webhooks (webhook.manage) for all entities." and no webhook is read. A member without the permission reads "Ask a workspace administrator for a role that includes managing API clients (api_client.manage) or managing webhooks (webhook.manage).", and the reason of a tab names its permission the same way: "The API clients tab needs a role that includes managing API clients (api_client.manage)." |
| Purpose | Create, rotate and revoke OAuth2 client-credentials API clients with non-approval scopes; manage signed webhook endpoints and their delivery log; find the OpenAPI document and rate limits |
| REQ | REQ-PLT-033, 034, 037; REQ-OPS-016; CTL-037 |
| Journeys | J-23.3, J-23-AC-1 |

**Wireframe, 1440 px (API clients).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > API clients and webhooks                                                                                  |
| API clients   Webhooks   OpenAPI                                                                                     |
+----------------------------------------------------------------------------------------------------------------------+
| 3 API clients                                                                [Download inventory]  [*New API client] |
| Name            Client id                                    Status    Scopes                      Last used    ...   |
| svc-salesforce  erevc_3f09…_Xq2…                             (Active)  contract.read, contract.…   12 Sep 2026  ...   |
| svc-netsuite    erevc_3f09…_7Lm…                             (Active)  journal.export, …           12 Sep 2026  ...   |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1440 px (one-time secret dialog, J-23.3).**

```text
+----------------------------------------------------------------------------+
| Client secret for svc-salesforce                                            |
| This secret is shown once. It cannot be shown again.                        |
| Client id      erevc_3f09a1…_Xq2P9sKf0LmN3aBc7dE1fG      [Copy]              |
| Client secret  ••••••••••••••••••••••••••••••  [Show] [Copy]                |
| [x] I have stored this secret                                               |
+----------------------------------------------------------------------------+
|                                                                   [*Done]   |
+----------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** "Scopes" truncates with a tooltip; "Last used" moves into the drawer.

```text
+--------------------------------------------------------------------------------------------------------+
| svc-salesforce  erevc_3f09…_Xq2…  (Active)  contract.read, contract.create …                          |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-07 panel tabs; DS-CMP-10 DataGrids "API clients", "Webhook endpoints", "Deliveries"; DS-CMP-09 modal drawers "New API client", "New webhook endpoint"; DS-CMP-11 dialog "Client secret" (and "Signing secret"); DS-CMP-11 confirmations; static definition list on the OpenAPI tab.

**Data bindings.** `GET /api-clients`; `POST /api-clients` `{name, scopes, is_all_entities, entity_codes, expires_at, rate_limit_per_minute}` (response includes the secret once when the request was approved at once — the bootstrap Tenant Admin during setup; otherwise `status` is `PENDING_APPROVAL`, `client_secret` is null and `approval_request_id` names the request another access approver decides, and `POST /api-clients/{id}/rotate-secret` issues the first secret after the approval — rev 1.48; 04 T-PLT-15 rev 1.168; the screen states for it are an item of lane F-ADM-WEB); `POST /api-clients/{id}/rotate-secret`; `POST /api-clients/{id}/revoke` `{reason}`; `GET /permissions` (scope options where `is_approval = false`); `GET, POST /webhook-endpoints`; `PATCH /webhook-endpoints/{id}` `{is_active, description, event_kinds}`; `GET /webhook-deliveries?status`; OpenAPI `GET /api/v1/openapi.json`; inventory RPT-27.

**Grid columns.** API clients: RPT-27 columns "Name", "Client id", "Status", "Scopes", "Entity scope", "Rate limit per minute", "Expires", "Last used", "Secret rotated"; actions "Rotate secret", "Revoke". Webhook endpoints: "URL" (mono); "Description"; "Events" (codes `run.completed`, `import.committed`, `period.locked`, `journal_batch.exported`, `journal_batch.acknowledged`, `exception.raised`); "Active" (Yes/No); "Created" (DS-FMT-17); actions "Deactivate" or "Activate". Deliveries: "Endpoint" (URL prefix); "Event" (mono); "Status" (§0.4 E-97); "Attempts"; "Next attempt" (DS-FMT-17); "Last response" (HTTP status); "Last error"; "Succeeded" (DS-FMT-17).

**States.**

| State | Copy |
|---|---|
| API clients SCR-ST-03 | Title "No API clients"; description "API clients use OAuth2 client credentials. Their scopes never include approval permissions."; primary "New API client" |
| Webhooks SCR-ST-03 | Title "No webhook endpoints"; description "Endpoints receive signed notifications with resource ids only, never amounts or personal data." |
| Sandbox | "New webhook endpoint" and the webhook activation `aria-disabled="true"` with the SB-R-08 reason line; the Webhooks empty state offers no action (rev 1.54; 05 SBX-08: an endpoint is created active, so a sandbox neither creates nor activates one) |
| API client awaiting approval; refused (rev 1.59) | The Status chip reads "Pending approval" (`PENDING_APPROVAL`) or "Rejected" (`REJECTED`), §0.4 E-103. Neither row offers "Rotate secret" or "Revoke": the two actions are those of an `ACTIVE` client. Ruling R-113 (e): the scopes of an API client are an access grant, so a client is created `PENDING_APPROVAL` with a ROLE_ASSIGNMENT request, is `ACTIVE` once the request is approved and `REJECTED` when it is rejected, withdrawn or voided. What the screen does on creation, the link to the request and the issue of the first secret follow when that slice of the API is on main (part 2, its own revision) |

**Interactions, keyboard and copy.**

- *New API client*: fields "Name", "Scopes" (checkbox list of non-approval permissions grouped by area; no approval permission is offered, J-23.3), "Entity scope" ("All entities" / selected), "Expires" (date; default 365 days), "Rate limit per minute" (default 600); buttons "Cancel", "Create API client"; step-up MFA; then the one-time dialog: title "Client secret for <name>", warning "This secret is shown once. It cannot be shown again.", "Show" and "Copy" controls, required checkbox "I have stored this secret", button "Done" (reports "Confirm that you stored the secret." until checked). The secret never appears again in any view or response (REQ-PLT-033). An API request adding an approval scope returns 422 `scope-not-allowed` with ERR-24 "API clients cannot hold approval permissions." (CTL-037).
- *Rotate secret*: confirmation "Rotate the secret of <name>? The current secret stops working immediately."; then the one-time dialog.
- *Revoke* (SB-R-05): consequence "Tokens of <name> stop working immediately."; Danger "Revoke API client".
- *New webhook endpoint*: fields "URL" ("Use an https URL." except `http://127.0.0.1` and `http://localhost` in dev and e2e), "Description", "Events" (checkboxes); signing secret one-time dialog "Signing secret for <URL>" with the same acknowledgement.
- *Entity scope, interim* (rev 1.62): until the API admits an entity scope on an API client (item API-CLIENT-ENTITY-SCOPE-1: `POST /api-clients` refuses every entity code), "Selected entities" is unavailable — `aria-disabled="true"`, with the reason line "An API client covers all entities." under the two options — and "All entities" stays chosen. The "Entities" multi-select returns with the choice. Rev 1.48 (04 T-PLT-15 rev 1.168; item API-CLIENT-ENTITY-SCOPE-1): the API admits it now — `POST /api-clients` takes `entity_codes` within its creator's own `api_client.manage` scope, and a code outside it answers as an unknown one — so the interim ends when the dialog offers the choice again (an item of lane F-ADM-WEB).
- *Server errors* (rev 1.62; DS-CMP-21): a refusal's field errors show at the field whose member they name and leave it when its value is edited. "New API client": `name` at "Name", `scopes` at "Scopes", `entity_codes` and `is_all_entities` at "Entities" (at "Entity scope" while no entity can be chosen), `expires_at` at "Expires", `rate_limit_per_minute` at "Rate limit per minute". "New webhook endpoint": `url` at "URL", `description` at "Description", `event_kinds` at "Events". "Revoke": `reason` at the reason field. A message that names a member the form has no field for is listed in the banner, so that the banner "Check the highlighted fields" never stands over a form that highlights nothing.
- OpenAPI tab copy: "API base URL <origin>/api/v1"; "Token endpoint POST /api/v1/oauth/token (client credentials, HTTP Basic client authentication); tokens last 60 minutes."; "Rate limit: <n> requests per minute per API client (default 600)."; link "Download the OpenAPI document (JSON)".

**Sample world (asserted).** J-23.3 (WLD-T-22): `tomas` creates `svc-salesforce` with scopes `contract.read`, `contract.create`, `import.upload`, `masterdata.maintain`; the secret is shown once with "I have stored this secret"; approval permissions are not offered. WLD-T-01: `svc-salesforce`, `svc-netsuite`, `svc-metering` active.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| API clients grid | grid named "API clients" | `SF-16-grid-api-clients` |
| Client row | row header "<name>" | `SF-16-row-<name normalised>` (for example `SF-16-row-svc-salesforce`) |
| New client drawer | dialog named "New API client" | `SF-16-drawer-api-client` |
| Secret dialog | dialog named "Client secret for <name>" | `SF-16-dialog-client-secret` |
| Webhook endpoints | grid named "Webhook endpoints" | `SF-16-grid-webhooks` |
| Deliveries | grid named "Deliveries" | `SF-16-grid-webhook-deliveries` |

**Light and dark.** Masked secret field mono on `--bg-surface`; warning text `--warning-fg`.

**Accessibility.** The secret value is not announced by default ("Client secret, hidden"); "Show" toggles `aria-pressed`; the acknowledgement checkbox is required (`aria-required="true"`).

## 10. Legacy migration (SF-19)

Migrations render in the Data area with its route tabs (SCR-IA-02: Imports · Exceptions · Integrations · Migrations · Templates), breadcrumb "Data > Migrations" and the page `h1`. The migration steps reuse the DS-CMP-18 stepper anatomy (named composition "migration stepper"): markers, labels, status captions and completed-step links, without the column-mapping and row-grid steps of imports.

### 10.1 SF-19 Migrations

| Field | Value |
|---|---|
| Screen id | SF-19 |
| Route | `/data/migrations` (RT-51) with `f.mode`, `f.status` |
| Roles and permissions | Read `migration.run` (Revenue Accountant; RT-51). Promotion approval `migration.approve` (Controller) in SF-12 |
| Purpose | List legacy `ASC606.db` imports and template replays with their status, reconciliation result and promotion |
| REQ | REQ-MIG-001 to 007; D-31; LTM-13 (SCR-LTH-13) |
| Journeys | J-20, J-21 |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Data > Migrations                                                                                                    |
| Imports   Exceptions   Integrations   Migrations   Templates                                                         |
| Migrations                                                           [Replay legacy templates]  [*Import a legacy database]|
+-------------+-------------------+----------------------------------+-------------------+------------+-----------+------+
| Migration   | Mode              | Source                           | Status            | Cutover    | Unexplained| By   |
| MIG-000001  | <Opening balances>| ASC606-shipped-step04.db 1f09…9ce2| (Promoted)        | 31 Jan 2023| 0          | Maya |
+-------------+-------------------+----------------------------------+-------------------+------------+-----------+------+
```

**Wireframe, 1280 px.** "Source" shows the file name only; the hash is in the tooltip.

```text
+--------------------------------------------------------------------------------------------------------+
| Migrations                                          [Replay legacy templates] [*Import a legacy database]|
| MIG-000001  <Opening balances>  ASC606-shipped-step04.db  (Promoted)  31 Jan 2023  0                   |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-06 plain header with the Data route tabs; DS-CMP-10 DataGrid "Migrations".

**Data bindings.** `GET /migrations?status&mode&count=true` (API-R-48; T-MIG-01 fields plus `unexplained_count` from the reconciliation run's control totals).

**Grid columns.**

| Header | Field | Format | Drill |
|---|---|---|---|
| Migration | `migration_no` | mono link | SF-19:detail |
| Mode | `mode` | outline chip "Opening balances" (`OPENING_BALANCES`), "Replay" (`REPLAY`) | none |
| Source | source file name, `source_sha256` | file name and hash prefix | none |
| Status | `status` | §0.4 E-76 chip | none |
| Cutover | `cutover_date` | DS-FMT-16; em dash for replay | none |
| Sandbox | sandbox display name (replay) | text | none |
| Unexplained differences | `unexplained_count` | integer; chip Difference when above 0 | SF-19:detail `step=reconciliation` |
| Created by | `created_by` | user | none |
| Created | `created_at` | DS-FMT-17 | none |

**States.** SCR-ST-03: title "No migrations yet"; description "Import a legacy eRev ASC606.db as opening balances, or replay the legacy templates into a sandbox and promote them after reconciliation."; primary "Import a legacy database"; secondary "Replay legacy templates".

**Interactions, keyboard and copy.** "Import a legacy database" opens SF-19:new `?mode=OPENING_BALANCES`; "Replay legacy templates" opens SF-19:new `?mode=REPLAY`.

**Sample world.** WLD-T-21 after J-20: one opening-balances migration, promoted, cutover 31 Jan 2023. WLD-T-23 after J-21: one replay migration, promoted.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Migrations" | `SF-19-page` |
| Grid | grid named "Migrations" | `SF-19-grid-migrations` |
| Row | row header "<migration no>"; tests filter by mode | `SF-19-row-<mode normalised>` (for example `SF-19-row-opening-balances`) |

**Light and dark.** Outline chips.

**Accessibility.** Grid named "Migrations".

### 10.2 SF-19:new New migration

| Field | Value |
|---|---|
| Screen id | SF-19:new |
| Route | `/data/migrations/new` (RT-52) with the screen parameter `mode=OPENING_BALANCES|REPLAY` (SCREENS.md SCR-URL-28) |
| Roles and permissions | `migration.run` |
| Purpose | Upload a legacy database (opening balances) or a reference database (replay) and start profiling |
| REQ | REQ-MIG-001, 002, 004; BR-MIG-01; T-PLT-29 `LEGACY_DATABASE` |
| Journeys | J-20.1, J-20-ALT-1, J-20-ALT-2, J-21.1 |

**Wireframe, 1440 px (opening balances).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Data > Migrations > New migration                                                                                    |
| New migration                                                                                                        |
| (o) Opening balances: import the latest version of each obligation as balances at a cutover date                    |
| ( ) Replay: replay the legacy templates in order into a sandbox, reconcile, then promote                             |
| +----------------------------------------------------------------------------------------------------------------+   |
| | Drop a legacy ASC606.db file here, or choose a file                                     [Choose file]          |   |
| | SQLite database · at most 500 MiB · the file is read from a copy and never changed                             |   |
| +----------------------------------------------------------------------------------------------------------------+   |
|                                                                                              [*Upload and profile]    |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** As 1440 px at `--content-max-form`.

```text
+--------------------------------------------------------------------------------------------------------+
| New migration   (o) Opening balances  ( ) Replay   [ Drop a legacy ASC606.db file … ]  [*Upload and profile]|
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-21 radio group "Mode"; DS-CMP-18 dropzone anatomy (purpose `LEGACY_DATABASE`); DS-CMP-29 banners.

**Data bindings.** `POST /files` (`purpose = LEGACY_DATABASE`); `POST /migrations` `{mode, source_file_id}` → migration `UPLOADED`; `POST /migrations/{id}/profile` (202; job `MIGRATION_IMPORT` profiling phase); navigate to SF-19:detail `step=profile`.

**Grid columns.** None.

**States.**

| State | Copy |
|---|---|
| Upload refused | "Legacy databases must be SQLite files of at most 500 MiB." (ERR-37) |
| Duplicate | "This legacy database was already imported in migration <number> on <date>." (ERR-19; J-20-ALT-1) with link "Open migration <number>" |
| Not a legacy database | "The file is not a legacy eRev database: table Contract_Live was not found." (ERR-20; J-20-ALT-2) |
| Uploading | DS-CMP-24 determinate bar "Uploading <file name>" |

**Interactions, keyboard and copy.** "Upload and profile" validates "Choose a legacy database file." For replay the dropzone copy reads "Drop the reference ASC606.db for reconciliation, or choose a file" and the button "Upload and plan replay".

**Sample world.** J-20.1: WLD-F-15 `ASC606-shipped-step04.db`. J-21.1: WLD-F-16 `ASC606-after-step14.db` as the reference database.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Mode | radiogroup named "Mode" | `SF-19-new-mode` |
| Dropzone | button named "Choose file" | `SF-19-dropzone` |
| Error banner | alert with ERR-19 or ERR-20 text | `SF-19-banner-upload-error` |

**Light and dark.** Dashed dropzone edge `--border-control`.

**Accessibility.** The dropzone is a button backed by `input type="file"`; drag and drop is optional (DS-CMP-18).

### 10.3 SF-19:detail Migration

| Field | Value |
|---|---|
| Screen id | SF-19:detail |
| Route | `/data/migrations/:migrationId` (RT-53) with the screen parameter `step` (opening balances: `profile`, `mapping`, `import`, `reconciliation`, `promotion`; replay: `profile`, `plan`, `replay`, `reconciliation`, `promotion`) (SCREENS.md SCR-URL-15) |
| Roles and permissions | Read and run `migration.run`; promotion approval `migration.approve` by a user other than the runner (BR-MIG-02) in SF-12. Rev 1.99 (SCREENS.md §0.6 SCR-PERM-02 (c); 04 API-R-48): `migration.run` is asked for all entities — a legacy migration is the workspace's. A holder for named entities reads SCR-ST-06 with "Migrations cover every entity of the workspace. Ask a workspace administrator for a role that includes running migrations (migration.run) for all entities." and the migration is not read; a member without the permission reads "Ask a workspace administrator for a role that includes running migrations (migration.run)." |
| Purpose | Profile the source, confirm mappings and the cutover or the replay plan, run the import or replay, reconcile against the source, and submit for promotion |
| REQ | REQ-MIG-001 to 007; REQ-POL-005; REQ-DAT-002, 003; BR-MIG-01 to 04; SBX-10; CTL-048 |
| Journeys | J-20.1 to J-20.5, J-20-AC-1 to AC-3, J-21.1 to J-21.4, J-21-AC-2 |

**Wireframe, 1440 px (opening balances, step reconciliation, J-20.3).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Data > Migrations > MIG-000001                                                                                        |
| Migration MIG-000001   <Opening balances>  (Reconciled)                                     [*Submit for promotion]  |
| Source ASC606-shipped-step04.db · SHA-256 1f09c2aa…9ce2 · Cutover 31 Jan 2023 · Run by Maya Chen                       |
| (1 Profile)──(2 Mapping)──(3 Import)──(4 Reconciliation)──(5 Promotion)                                               |
|  + 24 rows    + confirmed  + imported   * 0 unexplained     - not submitted                                           |
+----------------------------------------------------------------------------------------------------------------------+
| Key figures  Contracts 4 │ Legacy obligation rows 16 │ Lines compared … │ Differences above tolerance 0 │ Unexplained 0|
| Contract   Obligation      Measure             Legacy value   eRev value   Difference   Within tolerance  Deviation  |
| Contract 1 Contract level  Transaction price   1300           1300.00      0            Yes               —          |
| Contract 1 Contract level  Revenue to date     295.69         295.69       0            Yes               —          |
| Contract 2 Contract level  Billed less recognized −58.85      −58.85       0            Yes               —          |
| ...                                                                                                                  |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1440 px (replay, step plan, J-21.1).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Migration MIG-000001  <Replay>  (Profiled)                                                          [*Start replay]  |
| (1 Profile)──(2 Plan)──(3 Replay)──(4 Reconciliation)──(5 Promotion)                                                  |
| Replay plan (14 files)                                                                          [Add file]           |
| Order  File                                               Template                       Mode            Date        |
| 1      SKU SSP Template.xlsx                               Legacy v1: SKU SSP             —               —           |
| 2      Contract Setup Template 1.1.2023.xlsx               Legacy v1: Contract Setup      —               01 Jan 2023 |
| 8      Contract Modification Template 05.15.2023 ….xlsx     Legacy v1: Contract Modification  retrospective  15 May 2023 |
| ...                                                                    [Move up] [Move down] [Remove]                |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** The stepper captions move into tooltips; the plan table hides "Template" (shown under the file name).

```text
+--------------------------------------------------------------------------------------------------------+
| Migration MIG-000001 <Opening balances> (Reconciled)                          [*Submit for promotion]  |
| (1)──(2)──(3)──(4 Reconciliation)──(5)                                                                 |
| Contract 1  Contract level  Transaction price  1300  1300.00  0  Yes                                   |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.**

| Region | Components | Content |
|---|---|---|
| Header | DS-CMP-06 record header (migration variant); chips | `h1` "Migration <migration no>"; mode outline chip; status chip; meta source file, SHA-256 prefix, cutover or sandbox, run by |
| Migration stepper | DS-CMP-18 stepper anatomy | Five steps with markers and captions; completed steps link to their `step` |
| Profile | DS-CMP-06 KPI strip; static tables "Tables", "Selling entities" | T-MIG-01 `profile` |
| Mapping (opening balances) | DS-CMP-21 form (incl. the field group "Entity defaults": "Calendar", "Time zone" — rev 1.20); static tables "Entity mapping", "Field mapping", "Batch parameters" (incl. the toggle "Create missing products" — rev 1.20); DS-CMP-29 info notice | J-20.2 |
| Plan (replay) | DS-CMP-10 inline-editable draft grid "Replay plan" with "Move up", "Move down", "Remove" buttons (drag has button alternatives, DS-A11Y-10) | J-21.1 |
| Import or replay | DS-CMP-24 job progress; DS-CMP-10 static table "Batches" (replay) | Per-batch progress |
| Reconciliation | RPT-41 embedded per §0.5 | Summary strip and lines |
| Promotion | DS-CMP-16 routing status; DS-CMP-29 banners | Submit and approval state |

**Data bindings.** `GET /migrations/{id}` (status, profile, `import_upload_ids`, `registry_version_id`, `reconciliation_report_run_id`, `approval_request_id`); `POST /migrations/{id}/profile`; `POST /migrations/{id}/import` `{cutover_date, entity_mapping: [{legacy_name, entity_code, calendar_id?, time_zone?}], entity_defaults: {calendar_id?, time_zone?}, batch_parameters: {"migration.nondistinct_mapping", "migration.material_right_convention"}, create_missing_entities, create_missing_products}` (opening balances; rev 1.20 — the functional currency is the workspace reporting currency, not a field) or `{plan: [{file_id, template_code, mode, effective_date}]}` (replay) (202; job `MIGRATION_IMPORT`); `POST /migrations/{id}/reconcile` (202; job `MIGRATION_RECONCILE`); `GET /migrations/{id}/reconciliation-lines`; `GET /migrations/{id}/legacy-rows`; `POST /migrations/{id}/submit-promotion` `{comment}`; `POST /migrations/{id}/cancel` `{reason}`.

**Grid columns.**

Profile "Tables": "Table" (`Contract_Live`, `SKU_SSP`; mono); "Rows" (integer). Profile key figures: "File SHA-256"; "Contract_Live rows"; "Contracts"; "Legacy obligation rows"; "SKU_SSP rows"; "SSP versions" (labels); "Selling entities" (names); "Latest Current Period" (DS-FMT-16).

Mapping "Entity mapping": "Legacy Selling Entity" (text, exact); "Entity" (entity code; created automatically when absent, LM-CL-09); "Calendar" (rev 1.20; fiscal calendar select; default the workspace's only calendar when exactly one exists, else blank and required for a "Will be created" row; a "Matched" row shows the entity's calendar read-only); "Time zone" (rev 1.20; IANA time zone select; required for a "Will be created" row; a "Matched" row shows the entity's time zone read-only); "Status" ("Matched", "Will be created"). Above the table, the DS-CMP-21 field group "Entity defaults" ("Calendar", "Time zone") applies to every "Will be created" row without its own value; the row's own value wins. The table lists EVERY selling entity of the profile; a row the user does not edit is confirmed as the identity mapping (legacy text = code) with the defaults — "Confirm mapping" is refused by name while a "Will be created" row has no calendar or time zone (Codex 1106 R2). A row may target another entity code (existing, or created by the import); the confirmed target is what the migrated contracts carry — the legacy text stays visible in the row; rows that share a target consolidate to ONE entity named by its code, and a row whose calendar / time zone disagree with the others of that target is refused by name (Codex 1227 F1 / F2). The functional currency of a created entity is always the workspace reporting currency (not a field; 04 §17.2 LM-CL-09 rev 1.64). "Field mapping" (read-only, REQ-MIG-006): "Legacy column" (legacy names allowed, D-33); "eRev field"; "Rule" — rows `ASC 606 Stratification` → revenue category, `VC` → transaction price component; `Distinct or Nondistinct` → distinctness (`distinct`, `nondistinct`); `Selling Entity` → contracting and performing entity; `Deferred Revenue Account`, `Unbilled A/R Account`, `Revenue Account` → account overrides; material-right rows → material rights under the preset convention; `SSP Version` → SSP book versions. "Batch parameters": POL-211 `migration.nondistinct_mapping` (select; preset value `SINGLE_POB`), POL-212 `migration.material_right_convention` (preset `KEEP_QUANTITY_CONVENTION`), POL-213 `migration.legacy_vc_rows` (forced `VC_ELEMENT_PLUS_CREDIT_EVENTS`, read-only), POL-214 `migration.split_upload_allocation` (forced `ALLOCATE_ACROSS_ALL_POBS`, read-only); toggle "Create missing products" (rev 1.20; default on; helper text "Products absent from this workspace are created from the legacy SKU name with the parity template of their rows; a SKU mapped to two templates is refused."; 04 §17.2 LM-CL-03 rev 1.64).

Replay plan: "Order" (integer); "File" (name, SHA prefix in tooltip); "Template" (select "Legacy v1: SKU SSP", "Legacy v1: Contract Setup", "Legacy v1: Contract Progress Tracking", "Legacy v1: Contract Modification"); "Mode" (select `prospective`, `retrospective`, `pob_price_change` for modification files only; E-24); "Effective date" (date; required for progress and modification files); "Status" (SCREENS.md §0.8 E-40 chip once uploaded); actions "Move up", "Move down", "Remove".

Replay "Batches": "Order"; "File"; "Import" (link SF-10:detail in the sandbox); "Status"; "Rows"; "Duration" (DS-FMT-24).

Reconciliation: RPT-41 columns.

**States.**

| Step | State | Copy |
|---|---|---|
| Profile | Running | DS-CMP-24 "Profiling <file name>" |
| Mapping | Notice | Info banner "The legacy-parity preset will apply to this workspace when the migration is promoted." (J-20.2; REQ-MIG-005) |
| Mapping | Validation | 422 by name, one finding per entity, field named (rev 1.20): "Choose a calendar for <legacy entity>." / "Choose a time zone for <legacy entity>." / "SKU <name> maps to two templates (<a>, <b>); resolve it in the legacy database before importing." |
| Plan | Validation | "Add <n> files in order." / "Choose a mode for <file name>." / "Enter the effective date for <file name>." |
| Import | Running | DS-CMP-24 "Importing legacy database <migration no>"; replay rows per batch |
| Replay | Sandbox created | Info banner "Replay sandbox <name> was created. Batches commit in order without per-batch approval." (BR-MIG-03) |
| Reconciliation | Unexplained differences | Negative banner "<n> differences have no deviation reference. Promotion needs zero unexplained differences." (BR-MIG-02) and "Submit for promotion" `aria-disabled` with that reason |
| Promotion | Pending | Info banner "Promotion request <request no> is waiting for approval by a Controller other than you." |
| Promotion | Promoted (opening balances) | Positive banner "Promoted on <DD MMM YYYY HH:mm UTC>. <n> contracts are active with opening balances at <cutover date>." with link "Open contracts" (SF-02) |
| Promotion | Promoted (replay) | Positive banner "Promoted on <DD MMM YYYY HH:mm UTC>. The <n> batches were re-executed into this workspace under request <request no>. The replay sandbox was not converted." (SBX-10) |
| any | Failed | SCR-ST-12 "<job label> failed. Nothing was committed." |
| any | Not found (rev 1.22) | SCR-ST-07 title "Migration not found", description "It may have been removed from your access, or the link is incorrect." (the SF-10:detail pattern) |
| any | Load failure (rev 1.22) | SCR-ST-05 "Could not load the migration" |
| Mapping | Field mapping load failure (rev 1.22) | SCR-ST-05 "Could not load the field mapping" with Retry, inline in the "Field mapping" table region (the read is informational: the "Entity mapping" form and "Confirm mapping" are unaffected) |
| Profile | Failed while profiling (rev 1.22) | a FAILED batch WITHOUT a `profile` (MigrationOut.profile is written only at PROFILED): the route lands on Profile with SCR-ST-12 "Profiling <file name> failed. Nothing was committed." (the file name from `GET /files/{source_file_id}` `original_filename`) |
| Import | Failed while importing (rev 1.22) | a FAILED batch WITH a `profile`: the route lands on Import with SCR-ST-12 "Importing legacy database <migration no> failed. Nothing was committed." |

**Interactions, keyboard and copy.** "Confirm mapping" (mapping step): fields "Cutover date" (default latest Current Period; "Choose a cutover date on or before the latest legacy period."); buttons "Back", "Confirm mapping" (J-20.2). The import step then shows the summary "Cutover <date> · <n> entities · <n> contracts" and the primary "Run import" (J-20.3), which starts `MIGRATION_IMPORT` and, on success, `MIGRATION_RECONCILE`; the stepper moves to Reconciliation when the reconciliation job succeeds. "Add file" (plan step) opens a dropzone for legacy templates (`IMPORT_SOURCE`, ".xlsx or .csv at most 50 MiB"). "Start replay" confirms "Replay <n> files into a new sandbox?" with consequence "A sandbox with the legacy-parity preset is created and the files are committed in order. Production is not changed until promotion." "Submit for promotion": DS-CMP-11 form modal with "Comment (required)"; toast "Submitted migration <migration no> for promotion." "Open parallel run" opens SF-08:report `parallel_run_comparison` with `p.migration_id`. Migrated history rows appear elsewhere labelled "Migrated, unattributed" (BR-MIG-04).

**Host wording (rev 1.22; the SF-19:detail host built by lane F-ADM for J-20.2 / J-20.3 — the wording §10.3 lacked, ruled the migration lane's row).** The DS-CMP-24 progress label is the job region's accessible name ("Importing legacy database <migration no>" on the Import step; "Profiling <file name>" on Profile); no separate job noun and no hardcoded unit noun — the region renders API-S-Job progress exactly as the job reports it (`done` / `total` / `unit` verbatim when present; the `MIGRATION_IMPORT` job is single-phase and reports its state, not per-contract counts). In-table controls of "Entity mapping" are named "<Column> for <legacy entity>" ("Calendar for Mock Entity 2", "Time zone for …", "Entity for …"), after "Move <file name> up". Stepper captions are the wireframe's: "<n> rows" (Profile), "confirmed" (Mapping), "imported" (Import), "<n> unexplained" (Reconciliation), "not submitted" (Promotion); at 1280 px they move into tooltips. The document title is "Migration" (the h1 stays "Migration <migration no>"). The route without `step` redirects by status: UPLOADED / PROFILING → `profile`; PROFILED → `mapping` (replay: `plan`); IMPORTING / IMPORTED / FAILED / CANCELLED → `import` (replay: `replay`) — except a FAILED batch WITHOUT a `profile`, which failed while profiling and lands on `profile`; RECONCILED → `reconciliation`; SUBMITTED / PROMOTED → `promotion`. The FAILED-origin rule is API-derived (`MigrationOut.profile` is written only at PROFILED; the reconcile job registers no failure hook and there is no RECONCILING state, so PROFILING and IMPORTING are the only FAILED origins) and holds ONLY while those two remain the only origins — a later slice adding a failure hook (reconcile / promotion) re-opens the question and adds an explicit phase member then; no `failed_phase` member exists today by ruling. "Back" on Mapping returns to Profile when that step is built (omitted while Profile is not). The read-only "Field mapping" table renders `GET /migrations/field-mapping` (04 §16.1 API-R-48 rev 1.66; 71 rows `{id, legacy_column, target, rule}` in legacy order) verbatim — the frontend holds no legacy column name literal (REQ-UX-010). Its headings are the §10.3 columns "Legacy column" / "eRev field" / "Rule", bound to `legacy_column` / `target` / `rule`; `id` (LM-CL-nn) is the row key, not a displayed column; its own load failure is SCR-ST-05 "Could not load the field mapping" with Retry, inline in the table region — the "Entity mapping" form and "Confirm mapping" are unaffected.

**Sample world (asserted).** J-20.1 profile: SHA-256 of WLD-F-15; `Contract_Live` rows 24; contracts 4; legacy obligation rows 16; `SKU_SSP` rows 7; SSP versions `2023-01-01`; selling entities `Mock Entity 1`, `Mock Entity 2`; latest Current Period 31 Jan 2023. J-20.2: mode opening balances, cutover 31 Jan 2023, automatic entity mapping, preset notice. J-20.3: reconciliation per WLD-X-27 (RPT-41). J-20.4: `maya` submits; `marcus` approves with a fresh TOTP; contracts active with `OPENING_BALANCE_ESTABLISHED` events dated 31 Jan 2023. J-21.1: plan of 14 files in legacy 07 §3 order (SKU SSP; setup 1.1.2023; setup 2.1.2023; progress 31 Jan, 28 Feb, 31 Mar, 30 Apr 2023; modification `retrospective` 15 May 2023; `pob_price_change` 31 May 2023; `prospective` 15 Jun and 15 Jul 2023; `retrospective` 15 Aug 2023; `prospective` 15 Sep 2023; progress 31 Oct 2023). J-21.2: sandbox "Pembrey Gauges replay (Sandbox)"; J-21.3 reconciliation per WLD-X-28 with `DEV-052`; J-21.4 promotion re-executes the 14 batches; J-21-AC-2 each production batch records the promotion approval id.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Migration <migration no>" | `SF-19-page` |
| Stepper | navigation named "Migration steps" | `SF-19-stepper` |
| Step content | region named "<step label>" | `SF-19-step-<step slug>` (for example `SF-19-step-reconciliation`) |
| Profile figures | region named "Key figures" | `SF-19-kpi-strip` |
| Preset notice | status "The legacy-parity preset will apply …" | `SF-19-banner-preset` |
| Job region (rev 1.22) | region named "<DS-CMP-24 label>" (for example "Importing legacy database MIG-000001") | `SF-19-job` |
| Field mapping (rev 1.22) | table named "Field mapping" | `SF-19-grid-field-mapping` |
| Plan grid | grid named "Replay plan" | `SF-19-grid-plan` |
| Reconciliation grid | grid named "Reconciliation" | `SF-19-grid-reconciliation` |

**Light and dark.** Stepper markers (accent current step, positive complete) in both themes.

**Accessibility.** Stepper per DS-CMP-18 ARIA ("Step 4 of 5, Reconciliation, 0 unexplained"); plan reorder buttons named "Move <file name> up". Entity-mapping controls named "<Column> for <legacy entity>" (rev 1.22).

## 11. Onboarding (SF-15:setup, SF-25, SF-23:select, SF-26, SF-27)

### 11.1 SF-15:setup Workspace setup

| Field | Value |
|---|---|
| Screen id | SF-15:setup |
| Route | `/settings/setup` (RT-74) |
| Roles and permissions | Read `settings.manage` (Tenant Admin). Rev 1.99 (SCREENS.md §0.6 SCR-PERM-02 (c)): asked for all entities — the checklist reads `GET /tenant`. A holder for named entities reads SCR-ST-06 with "Workspace setup covers every entity of the workspace. Ask a workspace administrator for a role that includes managing workspace settings (settings.manage) for all entities.", the tenant is not read, and the landing does not lead there |
| Purpose | First-run checklist that takes a new workspace to the BR-PLT-02 completion conditions and points to the optional setup |
| REQ | REQ-PLT-038; BR-PLT-01, BR-PLT-02; REQ-REF-001, 002; REQ-UX-016 |
| Journeys | J-01.1 to J-01.3 |

After sign-in, a member holding `settings.manage` in a workspace whose `setup_completed_at` is null lands here instead of `/home` (J-01.1).

**Wireframe, 1440 px (WLD-T-20 after J-01.2).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Settings > Workspace setup                                                                                           |
| Setup   Entities   Calendars   Currencies and rates   Chart of accounts   Workspace settings                         |
+----------------------------------------------------------------------------------------------------------------------+
| Workspace setup · Harbourline Instruments (Demo)                                                                     |
| Setup completes when an entity has an open period and two different people can prepare and approve contracts.       |
|  (Passed)      1  Create a legal entity                          2 entities                         Open entities >  |
|  (Passed)      2  Generate a calendar and open a period          Jan 2023 open                      Open calendars > |
|  (Not started) 3  Invite a preparer and an approver              0 of 2 roles held by different people  Invite people >|
|  <Optional>    4  Choose accounting policies or the legacy-parity preset                             Open policies >  |
|  <Optional>    5  Connect a GL, CRM or billing system                                                Open integrations >|
|  <Optional>    6  Download the import templates                                                      Open templates > |
| Setup grants                                                                                                         |
|  Role assignments made during setup are approved by rule AUTO-BOOTSTRAP and appear in the next access review.        |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** As 1440 px at `--content-max-form`; the action links move under each item.

```text
+--------------------------------------------------------------------------------------------------------+
| (Passed) 1 Create a legal entity · 2 entities                                                          |
|   Open entities >                                                                                      |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Group route tabs; DS-CMP-10 static table "Setup checklist" with chips (§0.4 E-60 words and outline "Optional"); DS-CMP-29 positive banner when complete; static table "Setup grants".

**Data bindings.** `GET /tenant` (`setup_completed_at`, `display_name`); `GET /entities?count=true`; `GET /periods?state=open&limit=1`; `GET /users` with role permissions (`GET /roles/{id}`) to evaluate item 3; setup grants `GET /role-assignments` whose approval decision names rule `AUTO-BOOTSTRAP`.

**Grid columns: setup grants.** "Member"; "Role"; "Scope"; "Granted" (DS-FMT-17); "Rule" (mono `AUTO-BOOTSTRAP`).

**States.** Complete: positive banner "Setup is complete. Setup grants are listed in the access listing and the next access review." and the checklist stays visible read-only.

**Interactions, keyboard and copy.** Item links open SF-15:entities, SF-15:calendars, SF-14 (invite), SF-13:accounting, SF-16, SF-10:templates. Items 1 to 3 pass from live data; items 4 to 6 are optional and carry no status.

**Sample world.** J-01.1 (asserted): `tomas` lands on setup. J-01.2: entities `Mock Entity 1`, `Mock Entity 2`; periods Jan to Dec 2023 open. J-01.3: invitations for `maya`, `priya`, `marcus`, `nikhil` approved by `AUTO-BOOTSTRAP` and listed under "Setup grants".

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Checklist | table named "Setup checklist" | `SF-15-grid-setup` |
| Item row | row header "<item label>" | `SF-15-row-setup-<n>` |
| Setup grants | table named "Setup grants" | `SF-15-grid-setup-grants` |

**Light and dark.** Chips only.

**Accessibility.** Items are ordered; statuses in accessible names.

### 11.2 SF-25 Guided tour

| Field | Value |
|---|---|
| Screen id | SF-25 (placement) |
| Placement | Overlay opened from Help menu "Guided tour" or `tour=demo` / `tour=legacy` (SCREENS.md §0.4). On a demo workspace (`is_demo`) whose user has no `tour.completed` preference for `demo`, SF-01 shows below the page header the info banner (DS-CMP-29) "This is a demo workspace with sample data. The tour shows six places where eRev Cloud keeps revenue auditable." with the actions "Take the tour" (sets `tour=demo`; J-24.2) and "Dismiss" (hides the banner for the session); test hook `SF-25-banner-demo-tour`. SCREENS.md §2.4 specifies the banner on SF-01 and governs it (OQ-B-29 resolved by D-76) |
| Roles and permissions | Authenticated; the demo variant renders on demo workspaces (`is_demo`); stops that need a permission the user lacks are skipped with the note "Skipped: your roles do not include <permission label>." |
| Purpose | A six-stop tour of the product on demo workspaces, and a five-stop variant for legacy desktop users |
| REQ | REQ-UX-018, 019; LTM-O2 (SCR-LTH-O2) |
| Journeys | J-24.2, J-24.3, J-24-AC-1, J-24-AC-2 |

**Composition.** DS-CMP-32 Tour step popover (DESIGN_SYSTEM rev 1.2; OQ-B-27 resolved by D-76). The tour step is a non-modal popover dialog composed from the DS-CMP-05 panel surface (E2, `--bg-raised`, `--radius-lg`, 360 px wide) anchored beside the stop's target element, with DS-CMP-20 buttons. The target receives a 2 px `--border-control` outline with 2 px offset (a 3:1 UI boundary; not an accent use, DS-BR-09). No scrim; the page stays operable.

**Wireframe, 1440 px (stop 5 on SF-05, WLD-T-02).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Close · FS-US · Sep 2026 · ASC 606  (Period open)                                                                    |
| +- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -+   |
| | Blockers (…)                          Checklist                                                                |   |
| +- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -+   |
|                   +-------------------------------------------+                                                      |
|                   | Stop 5 of 6 · Close with evidence         |                                                      |
|                   | The close cockpit lists blockers and      |                                                      |
|                   | gates. A period locks only when the       |                                                      |
|                   | evidence is complete, and reopening       |                                                      |
|                   | needs two approvers.                      |                                                      |
|                   |                     [End tour] [Back] [*Next]|                                                   |
|                   +-------------------------------------------+                                                      |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** The popover positions below the target when there is no room beside it.

```text
+--------------------------------------------------------------------------------------------------------+
| [ target outlined ]                                                                                    |
| +---------------------------------------------+                                                        |
| | Stop 5 of 6 · Close with evidence  [End tour] [Back] [*Next] |                                       |
| +---------------------------------------------+                                                        |
+--------------------------------------------------------------------------------------------------------+
```

**Stops.**

| Variant | Stop | Target (route and anchor) | Title | Body |
|---|---|---|---|---|
| demo | 1 | SF-10:new, the upload region with the sample file preview (no upload) | "Bring contracts in" | "Imports validate every row and show a dry-run diff before anything is committed. An approver commits the batch." |
| demo | 2 | SF-03 for contract `FS-01`, the five-step tracker | "The contract workbench" | "Each contract shows its obligations, price, allocation and recognition, with the five steps of ASC 606 across the top." |
| demo | 3 | SF-03:schedules for `FS-01` with `explain` set to an `FS-01` schedule figure, the Explain panel | "Explain any figure" | "Every computed figure opens its formula, inputs, source records and history." |
| demo | 4 | SF-08:report `modification_register` with `f.contract=is:FS-03`, the first row | "Modifications on record" | "Each modification records its classification answers, treatment, approver and catch-up." |
| demo | 5 | SF-05 for FS-US, Sep 2026, `ASC606`, the blockers region | "Close with evidence" | "The close cockpit lists blockers and gates. A period locks only when the evidence is complete, and reopening needs two approvers." |
| demo | 6 | SF-08, the report catalogue | "Reports with run records" | "Every report run records its parameters, totals and output hash, so figures can be reproduced." |
| legacy | 1 | SF-10:templates | "Your four templates still work" | "The SKU SSP, Contract Setup, Contract Progress Tracking and Contract Modification templates import with their exact headers." |
| legacy | 2 | SF-10:detail review step of the latest import | "See changes before they commit" | "The dry-run diff shows allocations, schedules and journals before an approver commits the file." |
| legacy | 3 | SF-12 | "A second person approves" | "Uploads, SSP versions and journals wait for approval by another user." |
| legacy | 4 | SF-08:report `contract_history` | "Contract history, now a report" | "The history report keeps the 71 legacy columns in its legacy export." |
| legacy | 5 | SF-06 | "Journals that balance" | "Journal runs balance per entity and currency and export once to the GL." |

**Regions and components.** Popover dialog (composition above); step counter; buttons "End tour", "Back", "Next" (last stop "Finish").

**Data bindings.** Tour progress is the user preference `tour.completed` (J-24-AC-2) written with `PATCH /me/preferences` `{tour_completed: {variant, completed_at}}` (04 §16.12; OQ-B-20 resolved by D-76); navigation between stops uses the routes above.

**Grid columns.** None.

**States.** Missing anchor (for example a demo record absent): the stop shows "This stop is not available in this workspace." with "Next" (J-24-AC-1 requires every anchor to exist in WLD-T-02). Finish: toast "Tour complete" (J-24.3).

**Interactions, keyboard and copy.** Opening a stop navigates to its route, waits for the target region, moves focus to the popover heading and announces "Stop <n> of <total>: <title>". "Next" and "Back" move between stops; Esc or "End tour" closes the tour and returns focus to the Help menu button; the tour never traps focus (non-modal). The only write is the preference.

**Sample world (asserted).** J-24.2 on WLD-T-02 Fernhill Software, Inc. (Demo): six stops in order with `FS-01`, `FS-03` and FS-US Sep 2026; J-24.3 toast "Tour complete".

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Popover | dialog named "Stop <n> of <total>: <title>" | `SF-25-popover` |
| Stop | text "Stop <n> of <total>" | `SF-25-step-<title normalised>` (for example `SF-25-step-close-with-evidence`) |
| Next | button named "Next" or "Finish" | none |

**Light and dark.** Popover `--bg-raised` with `--shadow-popover`; target outline `--border-control` in both themes.

**Accessibility.** `role="dialog"` without `aria-modal`; the popover `aria-describedby` its body; the target carries `aria-describedby` the popover while active.

### 11.3 SF-23:select Choose a workspace

| Field | Value |
|---|---|
| Screen id | SF-23:select |
| Route | `/select-workspace` (RT-06) |
| Roles and permissions | Authenticated. "New scenario": `scenario.use` in the current production workspace |
| Purpose | Choose among production, demo, sandbox and scenario workspaces after sign-in or from the tenant switcher's "All workspaces" link; start a scenario |
| REQ | REQ-PLT-003, 023; REQ-FC-001; REQ-DEMO-001, 004 |
| Journeys | J-18.1, J-24.1 |

After password and MFA steps, a member of more than one workspace without a remembered last workspace lands here; the SCREENS.md §1.3 switcher popover ends with the link "All workspaces", which opens this page.

**Wireframe, 1440 px (viewer `robert`).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| eRev                                                                                                                 |
| Choose a workspace                                                                                                   |
+----------------------------------------------------------------------------------------------------------------------+
| Production                                                                                                           |
|   Avenmoor Holdings (Demo)          avenmoor      Viewer                         Last opened 12 Sep 2026   [Open]    |
| Demo workspaces                                                                                                      |
|   Fernhill Software, Inc. (Demo)    fernhill      Software and cloud (D01)        Viewer                   [Open]    |
|   Bracken Robotics Corp. (Demo)     bracken       Devices and industrial products (D02)                    [Open]    |
|   ...                                                                                                                |
| Sandboxes and scenarios                                                                                              |
|   Q4 2026 outlook (Scenario)  (Sandbox)  from Avenmoor Holdings (Demo) · known at 12 Sep 2026 17:02 UTC     [Open]    |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** Roles and last-opened wrap under the workspace name.

```text
+--------------------------------------------------------------------------------------------------------+
| Choose a workspace                                                                                     |
| Fernhill Software, Inc. (Demo) · fernhill · Software and cloud (D01)                         [Open]    |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Minimal frame (wordmark 16 px at the start of a header bar; no rail, because no workspace is active); three `section`s with DS-CMP-10 static tables; DS-CMP-19 Sandbox chip; DS-CMP-20 buttons; New scenario form (§7.1).

**Data bindings.** `GET /me` `memberships[] {membership_id, tenant {id, code, display_name, kind, is_demo}, status, last_opened_at}`, already ordered by `last_opened_at` descending (04 API-S-Me; OQ-B-20 resolved by D-76); `POST /session/tenant` `{tenant_id}`.

**Grid columns.** "Workspace" (`tenant.display_name`, with the outline chip "Sandbox" when `tenant.kind = sandbox`); "Code" (`tenant.code`, mono); "Last opened" (`last_opened_at`, DS-FMT-16; "—" when null); action "Open". The "Industry" column (cluster labels D01 "Software and cloud", D02 "Devices and industrial products", D04 "Engineering, construction and government", D05 "Consumer brands and franchising", D08 "Healthcare providers", D12 "Platforms and travel"), the "Roles" column and the "Source" column of sandboxes are deferred to later, because 04 API-S-Me memberships carry no industry cluster, role names or source tenant; the Roles text in the wireframe is layout only.

**States.** One membership: the page redirects to `/home` after selecting it automatically. No memberships: title "You are not a member of any workspace"; description "Ask a workspace administrator to invite you, or use the link in your invitation email."; action "Sign out".

**Interactions, keyboard and copy.** "Open" sends `POST /session/tenant`, navigates to `/home` (or SF-15:setup when setup is incomplete and the member holds `settings.manage`) and announces "Switched to <workspace name>". "New scenario" (`scenario.use`) opens the §7.1 form for the selected production workspace.

**Sample world (asserted).** J-24.1: `robert` switches to Fernhill Software, Inc. (Demo); Home renders FS-US Sep 2026 figures. Demo workspace names per PRD §2.4. J-18.1: WLD-T-30 appears under "Sandboxes and scenarios" with chip Sandbox.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Choose a workspace" | `SF-23-page` |
| Section | heading level 2 "Production", "Demo workspaces", "Sandboxes and scenarios" | none |
| Workspace row | row header "<workspace name>" | `SF-23-row-<code normalised>` (for example `SF-23-row-fernhill`) |

**Light and dark.** Sandbox chip; minimal header on `--bg-surface`.

**Accessibility.** Workspace names are row headers; "Open" buttons are named "Open <workspace name>".

### 11.4 SF-26 Legacy transition map

| Field | Value |
|---|---|
| Screen id | SF-26 |
| Route | `/help/legacy-transition` (RT-94) |
| Roles and permissions | Authenticated |
| Purpose | Where each desktop button and template lives now, and what changed |
| REQ | REQ-UX-019; LTM-O4, LTM-O5; SCR-LTH-01 to SCR-LTH-14 |
| Journeys | none (covered by `screens.spec.ts`) |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Coming from eRev desktop                                                                  [Take the legacy tour]     |
| Every desktop button has a place in eRev Cloud. Uploads now show a dry-run diff and need approval.                   |
+----------------------------------------------------------------------------------------------------------------------+
| The 14 desktop buttons                                                                                               |
| Desktop group          Desktop button             Where it lives now                    What changes for you         |
| Contract Operations    Load SSPs                  Upload legacy SKU SSP template >       SSPs need an approver …     |
| ...                                                                                                                  |
| The four templates                                                                                                   |
| Retired behaviours                                                                                                   |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** "What it did" is hidden; all other columns wrap.

```text
+--------------------------------------------------------------------------------------------------------+
| Coming from eRev desktop                                                     [Take the legacy tour]    |
| Load SSPs → Upload legacy SKU SSP template >                                                           |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-06 plain header; three static tables (DS-CMP-10 native): "The 14 desktop buttons", "The four templates", "Retired behaviours"; DS-CMP-20 button "Take the legacy tour" (`tour=legacy`).

**Data bindings.** Static catalogue from PRD §7.1 to §7.3 in `messages/en.json` namespace `help.legacyTransition` (allow-listed legacy strings, LTM-O5, DS-LINT-19).

**Grid columns.** Buttons table: "Desktop group"; "Desktop button"; "What it did"; "Where it lives now" (link from SCREENS.md SCR-LTH-01 to SCR-LTH-14 landing with its control copy); "What changes for you" (PRD §7.1 text). Templates table: "Desktop template"; "eRev Cloud template"; "Header rule"; link "Download template" (SF-10:templates). Retired behaviours table: "Desktop behaviour"; "eRev Cloud replacement" (PRD §7.3).

**States.** Static content; no loading state beyond fonts.

**Interactions, keyboard and copy.** Links open their landings; "Take the legacy tour" starts SF-25 `tour=legacy`.

**Sample world.** Static; the landing links resolve in WLD-T-20 and WLD-T-00.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Coming from eRev desktop" | `SF-26-page` |
| Buttons table | table named "The 14 desktop buttons" | `SF-26-grid-buttons` |
| Row | row header "<desktop button>" | `SF-26-row-ltm-<nn>` (for example `SF-26-row-ltm-01`) |

**Light and dark.** Static tables.

**Accessibility.** Tables have captions; links are named by their control copy.

### 11.5 SF-27 About dialog

| Field | Value |
|---|---|
| Screen id | SF-27 (placement) |
| Placement | Help menu "About eRev Cloud" or `dialog=about` (SCREENS.md §0.4) |
| Roles and permissions | Authenticated |
| Purpose | Product identity, engine release, licence and copyright |
| REQ | D-61; D-75 (03 Q2); DS-BR-02, DS-BR-05, DS-BR-06; REQ-CTL-003 |
| Journeys | none (covered by `screens.spec.ts`) |

**Wireframe, 1440 px (dialog `--modal-w-sm`).**

```text
+--------------------------------------------+
| About eRev Cloud                       [X] |
| eRev                                       |
| by Chipmunk Robotics                       |
| eRev Cloud                                 |
| Engine 1.0.0 · build 3f9a1c22 · schema e41 |
| MIT licence · Third-party notices          |
| Copyright (c) 2025-2026 ChipmunkRPA        |
|                                   [Close]  |
+--------------------------------------------+
```

**Wireframe, 1280 px.** Identical.

```text
+--------------------------------------------+
| About eRev Cloud                       [X] |
| ... as 1440 px ...                         |
+--------------------------------------------+
```

**Regions and components.** DS-CMP-11 dialog (informational; `role="dialog"`); wordmark as live text 28 px (DS-BR-02, DS-BR-03); "by Chipmunk Robotics" in `--fg-3` `body-sm` below the wordmark so the pair reads "eRev by Chipmunk Robotics" (DS-BR-05); product name "eRev Cloud" (DS-BR-06).

**Data bindings.** Engine release `{engine_version, build_sha, schema_revision}` from `GET /me` `engine_release` (04 API-S-Me; OQ-B-24 resolved by D-76); licence text and notices are static files bundled with the web app (`/licenses/LICENSE.txt`, `/licenses/NOTICE.txt`).

**Grid columns.** None.

**States.** Release unavailable: the engine line reads "Engine release unavailable".

**Interactions, keyboard and copy.** Focus moves to the title; Esc closes and returns focus to the Help menu button; links open in the same tab and restore the dialog on Back (`dialog=about`).

**Sample world.** Build values are volatile and masked in screenshots.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Dialog | dialog named "About eRev Cloud" | `SF-27-page` |
| Wordmark | element named "eRev" | none |
| Engine line | text beginning "Engine" | `SF-27-engine-release` (`data-volatile`) |

**Light and dark.** Wordmark `--fg-1` in both themes; no accent.

**Accessibility.** The wordmark element has `aria-label="eRev"`; copyright is plain text.

## 12. Authentication and error pages (SF-22, X placements)

Authentication pages render outside the shell: a header bar with the wordmark (16 px) and the form in a start-aligned 440 px column at `--gutter` from the inline-start edge, 15vh from the top (never centred hero copy, DS-AP-03). The sign-in wordmark is 28 px (DS-BR-03). Every field allows paste and password managers (DS-A11Y-17).

### 12.1 SF-22 Sign in and SF-22:mfa-challenge Verify your sign-in

| Field | Value |
|---|---|
| Screen ids | SF-22; SF-22:mfa-challenge |
| Routes | `/sign-in` (RT-01) with `reason=session-expired` and `next=<path>`; `/sign-in/mfa` (RT-02) |
| Roles and permissions | Public; the MFA step requires a completed password step |
| Purpose | Password sign-in with lockout, OIDC sign-in when configured, and TOTP or recovery-code verification |
| REQ | REQ-PLT-004, 005, 006; NFR-42, NFR-43; SAR-06, SAR-26 |
| Journeys | J-01.1, J-17.1, J-22.4, J-22.10, and every persona sign-in of DG-E2E-05 |

**Wireframe, 1440 px (SF-22).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| eRev                                                                                                                 |
|                                                                                                                      |
|    eRev                                                                                                              |
|    Sign in                                                                                                           |
|    [i] Your session ended after 30 minutes without activity. Sign in again.                                          |
|    Email                                                                                                             |
|    maya@demo.erev_______________________________                                                                     |
|    Password                                                   [Show]                                                 |
|    •••••••••••••••______________________________                                                                     |
|    [*Sign in]                                                                                                        |
|    Forgot password?                                                                                                  |
|    [Sign in with <provider name>]                                                                                    |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1440 px (SF-22:mfa-challenge).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| eRev                                                                                                                 |
|    Verify your sign-in                                                                                               |
|    Enter the 6-digit code from your authenticator app.                                                               |
|    Authentication code                                                                                               |
|    ______                                                                                                            |
|    [*Verify]                                                                                                         |
|    Use a recovery code instead · Sign in as someone else                                                             |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** Identical column; the layout also works at 320 px width (NFR-23).

```text
+--------------------------------------------------------------------------------------------------------+
| eRev                                                                                                   |
|    Sign in  Email ____  Password ____  [*Sign in]                                                      |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-21 fields; DS-CMP-20 buttons (primary "Sign in", secondary OIDC buttons); DS-CMP-29 banners; link buttons.

**Data bindings.** `POST /session/login` `{email, password}` → session with `csrf_token` and next step (`mfa_required`, `mfa_enrolment_required`); `POST /session/mfa` `{code}` or `{recovery_code}`; OIDC `GET /session/oidc/{provider}/start`; after success `GET /me` decides the landing: `next` when safe (same origin), SF-22:mfa-enrol when enrolment is required, SF-15:setup when setup is incomplete for `settings.manage` holders, SF-23:select for several workspaces, else `/home`.

**Grid columns.** None.

**States and copy.**

| Condition | Copy |
|---|---|
| Wrong email or password | "The email or password is incorrect." (no disclosure of which) |
| Account locked | "Too many failed sign-in attempts. Try again in 15 minutes or ask a workspace administrator." (ERR-23; J-22.10) |
| Session expired (`reason=session-expired`) | "Your session ended after <n> minutes without activity. Sign in again." (ERR-29) |
| Rate limited (429) | "Too many sign-in attempts. Try again in <seconds> seconds." |
| Wrong code | "That code did not match. Check your authenticator app and try again." |
| Recovery code used | Info toast after sign-in "You used a recovery code. <n> codes remain." |
| Suspended membership after sign-in | "Your access to <workspace name> is suspended. Ask a workspace administrator." |

**Interactions, keyboard and copy.** Enter submits each form; "Show" toggles password visibility (`aria-pressed`); "Use a recovery code instead" swaps the field to "Recovery code" (`autocomplete="one-time-code"` off); "Sign in as someone else" ends the pending session and returns to SF-22. Field autocomplete: email `username`, password `current-password`, code `one-time-code`.

**Sample world (asserted).** J-17.1: `hannah` signs in with password only (no MFA challenge; Auditor holds no MFA-required permission) and sees "Read-only access". J-22.10: five wrong passwords then the correct one: the lockout copy; security events `LOGIN_FAILED` ×5 and `ACCOUNT_LOCKED`.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Email | textbox named "Email" | none |
| Password | textbox named "Password" | none |
| Sign in | button named "Sign in" | none |
| Error banner | alert with the error copy | `SF-22-banner-error` |
| Code field | textbox named "Authentication code" | none |

**Light and dark.** Both themes follow `erev.theme` from `/theme-init.js` before sign-in.

**Accessibility.** Errors are announced assertively and linked to the fields (DS-CMP-21); no CAPTCHA or cognitive tests (DS-A11Y-17).

### 12.2 SF-22:mfa-enrol Set up multi-factor authentication

| Field | Value |
|---|---|
| Screen id | SF-22:mfa-enrol |
| Route | `/mfa/enrol` (RT-03) |
| Roles and permissions | Authenticated; the only reachable route for a member who holds a `requires_mfa` permission and is not enrolled (REQ-PLT-005; DG-FE-02 `MfaGate`) |
| Purpose | Enrol a TOTP factor and store ten recovery codes |
| REQ | REQ-PLT-005; SAR-26; ERR-27 |
| Journeys | J-22.4, J-22-AC-2 |

**Wireframe, 1440 px (step 3).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| eRev                                                                                                      Sign out   |
|    Set up multi-factor authentication                                                                                |
|    [!] Set up multi-factor authentication to continue. Your roles include approval or administration permissions.    |
|    (1 Scan)──(2 Verify)──(3 Recovery codes)                                                                          |
|    Store these recovery codes. Each code works once.                                                                 |
|      4k7p-2m9x   8d3q-7c1v   …   (10 codes)                                           [Copy codes] [Download codes]  |
|    [x] I have stored these recovery codes                                                                            |
|    [*Continue]                                                                                                       |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** Identical column.

```text
+--------------------------------------------------------------------------------------------------------+
|    Set up multi-factor authentication  (1)──(2)──(3 Recovery codes)                                    |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-29 warning banner (ERR-27); DS-CMP-18 stepper anatomy (three steps); QR image (`img` with a data URI; CSP `img-src data:` permits it, SAR-20); manual secret in mono with copy; DS-CMP-21 code field; recovery codes list; checkbox acknowledgement.

**Data bindings.** `POST /me/mfa/enroll` → `{otpauth_uri, secret_base32}`; `POST /me/mfa/confirm` `{code}` → `{recovery_codes[10]}` (shown once, never returned again, J-22-AC-2).

**Grid columns.** None.

**States and copy.** Step 1 "Scan the QR code with your authenticator app, or enter the key manually." with "Key" (mono, grouped in fours) and "Copy key". Step 2 "Enter the 6-digit code from your authenticator app." with "Verify code"; wrong code "That code did not match. Check the time on your device and try again." Step 3 as the wireframe; "Continue" reports "Confirm that you stored the recovery codes." until the checkbox is checked. Navigation elsewhere redirects back here.

**Interactions, keyboard and copy.** "Download codes" saves `erev-recovery-codes.txt`; "Sign out" ends the session. After "Continue" the landing rules of §12.1 apply (J-22.4: Home).

**Sample world (asserted).** J-22.4: Lena Fischer after setting her password: only the enrolment route is reachable; after verifying a code ten recovery codes are shown once and acknowledged; Home opens.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| QR image | img named "QR code for eRev multi-factor authentication" | `SF-22-mfa-qr` |
| Key | text in mono with copy button "Copy key" | `SF-22-mfa-key` (`data-volatile`) |
| Recovery codes | list named "Recovery codes" | `SF-22-mfa-recovery-codes` (`data-volatile`) |

**Light and dark.** The QR image renders black modules on a white quiet zone in both themes (a fixed image, exempt from token colours as content, not UI).

**Accessibility.** The QR image has a text alternative and the manual key is always visible; codes are a list.

### 12.3 SF-22:password-change, SF-22:accept-invitation, SF-22:password-reset and SF-22:password-reset-confirm

| Field | Value |
|---|---|
| Screen ids | SF-22:password-change; SF-22:accept-invitation; SF-22:password-reset (SCREENS.md §0.4; §14); SF-22:password-reset-confirm (SCREENS.md §0.4; §14) |
| Routes | `/password/change` (RT-04); `/accept-invitation#token=<token>` (RT-05); `/password/reset`; `/password/reset/confirm#token=<token>` (token in the fragment, never a query parameter) |
| Roles and permissions | Password change: authenticated. Invitation, reset request and reset confirm: public with a token |
| Purpose | Change a password, accept an invitation with a new password, and reset a forgotten password without revealing whether an account exists |
| REQ | REQ-PLT-004, 038; T-PLT-07 invitation acceptance; SAR-06, SAR-10; ERR-21 |
| Journeys | J-01.1 (accept), J-22.3, J-22.4 |

**Wireframe, 1440 px (SF-22:accept-invitation, J-22.3).**

```text
+----------------------------------------------------------------------------------------------------------------------+
| eRev                                                                                                                 |
|    Accept invitation                                                                                                 |
|    Tomás Rivera invited lena@demo.erev to Avenmoor Holdings (Demo).                                                  |
|    Choose a password                                                                                                 |
|    ________________________                                                                                          |
|    [!] Choose a less common password.                                                                                |
|    Use at least 12 characters. Do not use your email address or a common password.                                   |
|    Confirm password                                                                                                  |
|    ________________________                                                                                          |
|    [*Accept invitation]                                                                                              |
+----------------------------------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** Identical column.

```text
+--------------------------------------------------------------------------------------------------------+
|    Accept invitation · Choose a password ____ · Confirm password ____ · [*Accept invitation]           |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** DS-CMP-21 fields with help text; DS-CMP-29 banners; DS-CMP-20 buttons.

**Data bindings.** Password change: `POST /me/password` `{current_password, new_password}` → 204; a wrong current password returns 422 `validation-failed` on `current_password`, a weak password 422 `password-policy` (04 §16.12). Invitation: `POST /session/invitations/lookup` `{token}` → `{workspace_display_name, inviter_display_name, email, expires_at, has_password}` fills the heading and selects the form (`has_password` true: the "Your eRev password" state below; rev 1.9, 04 rev 1.38), and 404 `not-found` shows the expired-link state; then `POST /session/accept-invitation` `{token, password}` (API-R-01). Reset request: `POST /session/password-reset` `{email}` (always 202, empty body). Reset confirm: `POST /session/password-reset/confirm` `{token, new_password}` → 204. The token travels only in request bodies (04 §16.12, T-PLT-42; OQ-B-28 resolved by D-76).

**Grid columns.** None.

**States and copy.**

| Screen | Condition | Copy |
|---|---|---|
| all with a new password | Policy failures | "Choose a less common password." / "Use at least 12 characters." / "The password cannot be your email address." (ERR-21) |
| all with a new password | Mismatch | "The passwords do not match." |
| SF-22:password-change | Wrong current password before the shared lockout threshold | "The current password is incorrect." |
| SF-22:password-change | Fifth consecutive failed password check or active lock (423) | "Too many failed sign-in attempts. Try again in 15 minutes or ask a workspace administrator." |
| SF-22:password-change | Success | Toast "Password changed. Your other sessions were signed out." (SAR-10) |
| SF-22:accept-invitation | Expired or used token (404) | "This invitation link has expired or was already used. Ask a workspace administrator to resend it." |
| SF-22:accept-invitation | Existing user with a password (`has_password` true; rev 1.9) | Field "Your eRev password" (`autocomplete="current-password"`, no policy help) instead of the two new-password fields; button "Accept invitation"; a wrong password is the API's 422 `validation-failed` on `password` as the field error |
| SF-22:password-reset | After submit | "If an account exists for <email>, we sent a link to reset the password. The link expires in 60 minutes." |
| SF-22:password-reset-confirm | Expired token | "This reset link has expired. Request a new link." with link to SF-22:password-reset |
| SF-22:password-reset-confirm | Success | "Password reset. Sign in with your new password." with link "Sign in"; every session of the user ends |

**Interactions, keyboard and copy.** New-password fields use `autocomplete="new-password"`; the current password field `current-password`. Buttons: "Change password", "Accept invitation", "Send reset link", "Reset password". After accepting an invitation the §12.1 landing rules apply (MFA enrolment first when required). SF-15:profile's "Change password" (§9.9 wireframe) opens SF-22:password-change; this closes L3-3-Q-12 and L3-3-Q-13 (rev 1.8, D-98 candidate 24 Q4), and the row shows no "Last changed <date>" until API-S-Me carries `password_changed_at`. After the toast of a successful change the page opens the landing route `/` (Q5). "Forgot password?" on SF-22 (§12.1 wireframe) opens SF-22:password-reset (Q7).

**Sample world (asserted).** J-22.3: Lena Fischer sets `password1234` and sees "Choose a less common password."; J-22.4: `Lena!Revenue2026` succeeds and enrolment follows. J-01.1: `tomas` accepts the WLD-T-20 invitation from the fake outbox.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| New password | textbox named "Choose a password" or "New password" | none |
| Policy error | text beginning "Choose a less common password" | `SF-22-banner-password-policy` |
| Accept button | button named "Accept invitation" | none |
| Reset confirmation | status "If an account exists …" | `SF-22-banner-reset-sent` |

**Light and dark.** Standard form tokens.

**Accessibility.** Help text is referenced by `aria-describedby` after the error; the reset confirmation never reveals account existence.

### 12.4 Error and viewport placements

| Screen id | Placement | Rendering and copy | Authority |
|---|---|---|---|
| X:not-found | Route `*` (RT-98) and in-route not-found states | SCREENS.md SCR-ST-07: "Page not found" / "<Object label> not found" | SCREENS.md §0.7; ERR-30; BR-UX-06 |
| Access limited | In-route state | SCREENS.md SCR-PERM-01 access-limited empty state | SCREENS.md §0.6 |
| X:route-error (SCREENS.md §0.4; §14) | React Router error boundary of every route, inside the shell | `h1` "Something went wrong"; body "Something went wrong on our side. The request was not completed and nothing was saved. Reference <request id>." (ERR-34, CPY-05); buttons "Reload page" (primary) and "Go to Home"; "Copy reference"; no stack trace, SQL or internal id beyond the request id; test hooks `X-page`, `X-banner-route-error` | ERR-34; CPY-05; DG-FE-02 `RouteError` |
| X:narrow-viewport (SCREENS.md §0.4; §14) | Below 1024 px CSS width on every route except SF-01, SF-12 and the SF-22 family | Inside `main`: title "This screen needs a wider window"; description "Use a window at least 1,024 pixels wide, or open Home or Approvals, which work on smaller screens."; links "Go to Home", "Go to Approvals"; test hook `X-empty-narrow-viewport` | NFR-32 |
| Session expiring, offline | Shell | SCREENS.md §1.1 (modal "Your session ends in 2 minutes." with "Stay signed in"; banner "API unreachable. Changes are not being saved.") | SCREENS.md §1.1; DS-CMP-01 |
| Command-time problems | In place | SCREENS.md SCR-PERM-05 (step-up, forbidden, self-approval) | SCREENS.md §0.6 |

Light and dark: the error pages use the shell surfaces; the narrow-viewport message is start-aligned. Accessibility: X:route-error moves focus to its `h1` and announces "Something went wrong" assertively once.

## 13. Design gallery (X:design)

| Field | Value |
|---|---|
| Screen id | X:design |
| Route | `/design` (RT-97), compiled only when `VITE_EREV_DESIGN_GALLERY=1` (`make frontend`, `make dev-up`, `make e2e`; unset in `make build` and images) |
| Roles and permissions | Authenticated (RT-97) |
| Purpose | Render every DS-CMP component in every state in both themes and both densities, with sample-world data, for designer QA and `design.spec.ts` |
| REQ | DS-VER-05 to DS-VER-09; G8; G12 |
| Journeys | none; `design.spec.ts` (DG-E2E-07) |

**Composition (in order; anchors are the DS ids).**

| # | Section `h2` | Anchor | Content |
|---|---|---|---|
| 0 | "Tokens" | `#DS-COL` | Every token of DS §2.5 as a swatch with name and sRGB value; contrast pairs C01 to C81 as a static table with ratios |
| 1 | "Typography" | `#DS-TYP` | DS-TYP-11 to DS-TYP-19 samples; tabular figures sample `1,234,567.89` |
| 2 | "Numbers and formats" | `#DS-FMT` | Every row of DS §6.4 under both negative styles side by side |
| 3 | "Icons" | `#DS-ICO` | The DS-ICO-07 registry with names |
| 4 | "Base controls" | `#DS-CMP-20`, `#DS-CMP-27`, `#DS-CMP-28` | Buttons in every variant and state; tooltip; menu |
| 5 | "Shell" | `#DS-CMP-01` to `#DS-CMP-05` | Top bar variants (normal, sandbox, read-only), rail collapsed and expanded, context pill states, palette states, notifications states |
| 6 | "Record and layout" | `#DS-CMP-06` to `#DS-CMP-09`, `#DS-CMP-11`, `#DS-CMP-12` | KPI strip variants with `SF-ORD-10001` figures; tabs; master-detail; drawers; modals incl. confirmation with reason; timeline audit variant |
| 7 | "Data" | `#DS-CMP-10`, `#DS-CMP-13`, `#DS-CMP-14`, `#DS-CMP-26`, `#DS-CH-01` to `#DS-CH-06` (rev 1.82: DESIGN_SYSTEM rev 1.12) | DataGrid states (loading, empty, no results, error, refreshing, editing, grouped, totals); FilterBar; charts with RPT-01, RPT-03, RPT-06 and RPT-08 sample data (`SF-ORD-10002` time bands 166,398.30 / 41,941.49 / 0.00); money and number components |
| 8 | "Workflow" | `#DS-CMP-15` to `#DS-CMP-18`, `#DS-CMP-25` | Explain panel states; approval diff (pending, stale, insufficient permission); five-step tracker; import stepper; proposal block (generating, ready, accepted, dismissed, failed, uncited figure) |
| 9 | "Feedback and forms" | `#DS-CMP-19`, `#DS-CMP-21` to `#DS-CMP-24`, `#DS-CMP-29` to `#DS-CMP-31` | Every chip word of DS-CMP-19, which includes every word of SCREENS.md §0.8 and §0.4 of this file; fields and validation; toasts; empty states; job progress incl. reduced-motion bar; banners; skeletons; segmented controls |
| 10 | "Compositions" | `#SB-compositions` | Run stamp (RV-02), tie-out strip (RV-05), close blocker table (§1.1), migration stepper (§10.3), tour popover (DS-CMP-32; §11.2), one-time secret dialog (§9.15); the button "Throw a render error" (X:route-error, DS-VER-06) |

**Wireframe, 1440 px.**

```text
+----------------------------------------------------------------------------------------------------------------------+
| Design gallery                          Theme (Light | Dark | Side by side)   Density (Comfortable | Compact)          |
+------------------------+---------------------------------------------------------------------------------------------+
| Sections               | 7 Data · DS-CMP-10 DataGrid                                                                 |
|  0 Tokens              |  State: {Loading v}                                                                         |
|  1 Typography          |  [ grid rendered in the chosen state with WLD sample rows ]                                 |
|  ...                   |                                                                                             |
|  10 Compositions       |                                                                                             |
+------------------------+---------------------------------------------------------------------------------------------+
```

**Wireframe, 1280 px.** The section index becomes a select.

```text
+--------------------------------------------------------------------------------------------------------+
| Design gallery  {Section: 7 Data v}  Theme (Light|Dark|Side by side)  Density (Comfortable|Compact)     |
+--------------------------------------------------------------------------------------------------------+
```

**Regions and components.** Every DS component; the gallery itself uses DS-CMP-06 plain header, DS-CMP-31 segmented controls and an in-page `nav`.

**Data bindings.** None beyond static fixtures derived from PRD §2 figures; no API calls, so the gallery renders without a seeded database.

**Grid columns.** Component-specific fixtures.

**States.** Every component shows its states explicitly; "Side by side" renders two `data-theme` containers, which is the only place components render in both themes at once.

**Interactions, keyboard and copy.** Section links move focus to the section `h2`; the theme and density controls apply at once; `?pseudo=1` and `dir=rtl` work on this route for DS-VER-09.

**Sample world.** K-01, K-02 and K-03 figures of PRD §2.8 as fixture values.

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | heading level 1 "Design gallery" | `X-page` |
| Section | heading level 2 "<section>" | `X-design-section-<anchor normalised>` (for example `X-design-section-ds-cmp-10`) |
| Theme control | radiogroup named "Theme" | none |

**Light and dark.** The gallery is the designer review surface for both themes (DS-VER-06).

**Accessibility.** The gallery passes the same axe scan as product screens; demonstration of disabled and error states keeps accessible names.

**Route error demonstration.** Section 10 ends with the button "Throw a render error", which mounts a child that throws during render inside a nested route error boundary, so X:route-error renders without a failing API call (captured by `screens.spec.ts`, §15).

## 14. Route and parameter citations

SCREENS.md owns the path, title and read permission of every screen id (D-73). This section cites the SCREENS.md rows that the screens of this file use and restates no path, title or permission. Where any text of this file restates a path, SCREENS.md §0.4 governs.

### 14.1 Route rows first named by this file

| SF id | SCREENS.md row | Section |
|---|---|---|
| SF-05:close-run | RT-99 | §1.2 |
| SF-05:journal-preview | RT-100 | §1.3 |
| SF-05:history | RT-101 | §1.4 |
| SF-05:reconciliations | RT-102 | §2.1 |
| SF-05:reconciliation | RT-103 | §2.2 |
| SF-06:run-lines | RT-104 | §3.3 |
| SF-06:run-batches | RT-105 | §3.4 |
| SF-08:runs | RT-106 | §5.3 |
| SF-08:dashboard | RT-107 | §5.5 |
| SF-14:user | RT-108 | §9.10 |
| SF-14:access-review | RT-109 | §9.13 |
| SF-15:workspace | RT-110 | §9.6 |
| SF-22:password-reset | RT-111 | §12.3 |
| SF-22:password-reset-confirm | RT-112 | §12.3 |

Every other screen id of this file has its route row in SCREENS.md §0.4 (RT-01 to RT-06, RT-22 to RT-41, RT-51 to RT-53, RT-71 to RT-78, RT-84 to RT-94, RT-97).

### 14.2 Placements

| Screen id | SCREENS.md §0.4 placement or section | Section |
|---|---|---|
| X:session-expiring | Placement row | §12.4 |
| X:route-error | Placement row | §12.4 |
| X:narrow-viewport | Placement row | §12.4 |
| SF-25 | Placement row; the SF-01 demo tour banner is specified in SCREENS.md §2.4 (OQ-B-29 resolved by D-76) | §11.2 |

### 14.3 Screen parameters

SCREENS.md adopted every screen parameter this file uses (OQ-B-30 resolved by D-76), and SCR-URL-20 to SCR-URL-23 apply to them.

| Parameter | SCREENS.md row | Screens | Section |
|---|---|---|---|
| `run` | SCR-URL-16 | report screens | §0.5 |
| `p.<key>` | SCR-URL-17 | report screens | §5.2, §5.6 |
| `layout` | SCR-URL-18 | SF-04 | §4.1 |
| `rows`, `granularity`, `measure` | SCR-URL-24 | SF-04 | §4.1 |
| `format`, `from`, `to` | SCR-URL-25 | SF-06:entries | §3.5 |
| `run.<panel>` | SCR-URL-26 | SF-08:dashboard | §5.5 |
| `calendar`; `rate_set`, `version` | SCR-URL-27 | SF-15:calendars; SF-15:currencies | §9.3; §9.4 |
| `mode` | SCR-URL-28 | SF-19:new | §10.2 |
| `step` (search parameter) | SCR-URL-15 | SF-19:detail | §10.3 |
| `event_set` | SCR-URL-29 | SF-10:new (SCREENS.md §12.2) | §7.2 |
| `reason`, `next` | SCR-URL-30 | SF-22 | §12.1 |
| `event` (rev 1.36) | SCR-URL-32 | SF-09:audit-log | §6.3 |
| `entities` (rev 1.92) | SCR-URL-01 (rev 1.61) | SF-04, SF-08:report, SF-08:dashboard | §0.5 |

## 15. Screen audit list for `screens.spec.ts`

DG-E2E-07 captures each screen below under SCREENS.md SCR-ST-20: light and dark themes, comfortable density, 1440 × 900, rendering and axe checks only, never figures. Captures run after the journey project that produces the stated state. Tenant WLD-T-01 and context `entity=AVM-US&period=FY2026-P09&book=ASC606` apply unless a row states otherwise. Where a URL needs a record uuid, the spec resolves it by business key through the API before navigating. Elements carrying `data-volatile` are masked. Rev 1.98: the rows marked "Closed world" are those of `closed.spec.ts` (dev-guide DG-E2E-02 rev 1.277), captured on the world `make e2e CLOSE=1` seeds — AVM-US in book `ASC606` closed from January to August 2026 — with the context `entity=AVM-US&period=FY2026-P08&book=ASC606` unless the row names another. The world of the other rows holds no lock.

| Screen id | Persona | URL and state captured |
|---|---|---|
| SF-05 | `marcus` | `/close/AVM-US/ASC606/FY2026-P09`: Locked after J-14.7, every gate Passed |
| SF-05 | `maya` | `/close/AVM-US/ASC606/FY2026-P10`: Period open, blockers listed |
| SF-05 | `marcus` | Closed world (rev 1.98): `/close/AVM-US/ASC606/FY2026-P08`: Locked, no command of a close, "Permanently lock" unavailable behind January |
| SF-05 | `maya`, `marcus` | Closed world (rev 1.98): `/close/AVM-US/ASC606/FY2026-P01`: `maya` is not offered "Permanently lock"; `marcus` requests it and the banner "Permanent lock requested by <name> on <at>." stands with "View request" (captured); the request is then withdrawn. Rev 1.101: the row after it makes the request again and `elena`, the world's second Controller, approves it with her step-up; January is `permanently_locked`. The three cockpit rows run in this order in one worker, and what the last does cannot be undone |
| SF-05:close-run | `maya` | `/close/AVM-US/ASC606/FY2026-P09/close-run`: latest succeeded close run with its 14 steps |
| SF-05:journal-preview | `maya` | `/close/AVM-US/ASC606/FY2026-P09/journal-preview`: balanced preview with the Dr = Cr check |
| SF-05:history | `marcus` | `/close/AVM-US/ASC606/FY2026-P09/history`: lock, reopen with two decisions, re-lock with the diff link |
| SF-05:multi-entity | `marcus` | `/close/multi-entity?book=ASC606&period=FY2026-P09`: the three J-13.16 close runs |
| SF-05:reconciliations | `priya` | `/close/AVM-US/ASC606/FY2026-P09/reconciliations`: billing to subledger and subledger to GL |
| SF-05:reconciliation | `priya` | Subledger-to-GL reconciliation of J-13.11, Reviewed, with the 250.00 explained difference |
| SF-06 | `maya` | `/journals`: default list |
| SF-06:run | `maya` | `/journals/runs/<uuid>`: the J-13.8 run for AVM-US Sep 2026 (earliest run of `GET /journal-runs?entity=AVM-US&period=FY2026-P09&book=ASC606`) |
| SF-06:run-lines | `maya` | Same run, `/lines?f.account=is:4010`, first line selected with its source drawer open |
| SF-06:run-batches | `maya` | Same run, `/batches`: every batch acknowledged |
| SF-06:entries | `maya` | `/journals/entries?format=gross&from=2026-09-01&to=2026-09-30` |
| SF-04 | `marcus` | `/schedules` with `snapshot` = current AVM-US Sep 2026 lock id: As locked |
| SF-04 | `marcus` | `/schedules?entity=AVM-JP&granularity=quarter`: K-10 by fiscal quarter |
| SF-04 | `marcus` | `/schedules` opened from the rail on a page that keeps no context (rev 1.92): the address gains the context pill's entity, period and book, and the run names that entity |
| SF-04 | `marcus` | Closed world (rev 1.98): `/schedules`: As locked by default — the frozen rows without the chart, the bar's fields unavailable |
| SF-08 | `robert` | `/reports`: catalogue |
| SF-08:report | `marcus` | `/reports/revenue_waterfall` (chart and tie-out strip); `/reports/rpo` As locked; `/reports/je_population`; `/reports/legacy_contract_history_export` with the J-15.8 parameters; `/reports/extract_contracts`; `/reports/rpo` without a context (rev 1.92): the address gains the context pill's entity, period and book, and the run names that entity |
| SF-08:report | `marcus` | Closed world (rev 1.98): `/reports/revenue_waterfall`, `/reports/modification_register` and `/reports/rpo` As locked by default; `/reports/revenue_from_opening_liability` and, without a capture, `/reports/judgement_register` on current figures with "A period lock does not freeze this report.". Rev 1.101 (register index 280), last of the cockpit's group: `/reports/rpo` of the permanently locked January is As locked by default on the lock of its close — the API's `dataset_lock`, not the permanent lock's record — with that lock's time in the banner (captured); "Show current figures" says the same time and offers "Show as locked" |
| SF-08:runs, SF-08:run | `marcus` | `/reports/runs`; the J-15.5 RPO XLSX run record |
| SF-08:disclosure-pack | `marcus` | `/reports/disclosure-pack`: AVM-US Sep 2026 As locked, seven sections |
| SF-08:dashboard | `robert` | `/reports/dashboards/revenue` without `entity` and with `entity=AVM-US` (rev 1.82: without an entity the demo world shows the header, the banner and the flags panel, with one the four chart panels; the page reads no `currency_view`; rev 1.92: "without `entity`" is `entities=all`, and a third state opens the page without a context — the address gains the context pill's entity, period and book and the panels are that entity's); `/reports/dashboards/close` |
| SF-09, SF-09:pack | `hannah` | `/reports/evidence`; `EVP-000014` close pack for AVM-US Sep 2026 |
| SF-09:audit-log, SF-09:verification | `hannah` | `/reports/audit-log` filtered to object `PRJ-CB-2026-01`; the J-17.5 verification record |
| SF-17 | `jordan` | `/reports/forecasts` in WLD-T-01 (production variant) and in WLD-T-30 (scenario variant) |
| SF-17:event-set, SF-17:run | `jordan` | Tenant WLD-T-30: event set "Q4 base"; the J-18.4 forecast run |
| SF-18 | `jordan` | `/contracts/deal-preview` after "Preview allocation" with the J-18.6 inputs |
| SF-20:new, SF-20 | `maya` | `/contracts/review/new` empty; the J-19 proposal after J-19.4 (Accepted) |
| SF-28 | `maya` | `/home?panel=ask`: empty panel |
| SF-15:ai | `tomas` | `/settings/ai` after J-19.9 |
| SF-15:ai-call-log | `maya` | `/settings/ai/call-log` with the J-19.5 entry expanded |
| SF-15 | `tomas` | `/settings`: section index |
| SF-15:entities, SF-15:calendars, SF-15:currencies, SF-15:chart-of-accounts, SF-15:workspace | `tomas` | Lists; calendars with the AVM-US calendar selected; currencies with the first rate set selected |
| SF-15:sandbox | `marcus` | `/settings/sandbox` in production after J-25.4 (no Reset action) |
| SF-15:notifications, SF-15:profile | `maya` | Own preferences; profile |
| SF-14, SF-14:user | `tomas` | `/settings/users`; Lena Fischer after J-22.12 (Suspended) |
| SF-14:roles, SF-14:sod | `tomas` | Roles; separation-of-duties rules with the SoD-3 exception |
| SF-14:access-reviews, SF-14:access-review | `grace` | Campaigns; "Q3 2026 access review" |
| SF-14:security, SF-14:support-access | `tomas` | Security settings; support access grants |
| SF-16:developer | `tomas` | `/settings/developer`: API clients including `svc-salesforce` |
| SF-19, SF-19:new, SF-19:detail | `maya` | Tenant WLD-T-21 after J-20: `/data/migrations`; `/data/migrations/new?mode=OPENING_BALANCES`; `MIG-000001` with `step=reconciliation` |
| SF-19:detail | `maya` | Tenant WLD-T-23 after J-21: the replay migration with `step=plan` |
| SF-15:setup | `tomas` | Tenant WLD-T-20 after J-01: setup complete |
| SF-25 | `robert` | Tenant WLD-T-02: `/home?tour=demo`, stop 1 |
| SF-23:select | `robert` | `/select-workspace` |
| SF-26 | `maya` | `/help/legacy-transition` |
| SF-27 | `maya` | `/home?dialog=about` (engine line masked) |
| SF-22 | unauthenticated | `/sign-in`; `/sign-in?reason=session-expired` |
| SF-22:mfa-challenge | `marcus` | `/sign-in/mfa` after the password step |
| SF-22:mfa-enrol | Invitee created by the spec as in J-22.1 and J-22.2 (Revenue Reviewer) | `/mfa/enrol` step 1 after accepting the invitation (QR image and key masked) |
| SF-22:accept-invitation | unauthenticated | The invitation link of that invitee from the fake outbox, before acceptance |
| SF-22:password-change | `maya` | `/password/change` |
| SF-22:password-reset, SF-22:password-reset-confirm | unauthenticated | `/password/reset` after submitting `maya@demo.erev`; `/password/reset/confirm#token=invalid` (expired-link state) |
| X:session-expiring | `maya` | `/home` with the Playwright clock advanced to two minutes before the idle timeout |
| X:route-error | `maya` | `/design`, section 10, after "Throw a render error" |
| X:narrow-viewport | `maya` | `/contracts` at 900 × 900 |
| X:design | `maya` | `/design`, section 7 "Data", theme "Side by side" |

## 16. Journey coverage

Each row maps a PRD journey step or acceptance criterion to the screens and controls that carry it. "SCREENS.md" rows are specified there; this file only links them.

| Journey step | Screen ids | Control, region or state | Owner |
|---|---|---|---|
| J-01.1 | SF-22:accept-invitation, SF-22, SF-22:mfa-enrol, SF-15:setup | "Accept invitation"; "Sign in"; enrolment; landing on setup | §12.3, §12.1, §12.2, §11.1 |
| J-01.2 | SF-15:entities, SF-15:calendars | "New entity"; "Generate fiscal year"; "Open" per period | §9.2, §9.3 |
| J-01.3 | SF-14, SF-15:setup | "Invite user"; "Setup grants" table | §9.10, §11.1 |
| J-01.4, J-01.5 | SF-13:accounting, SF-12 | Policy version and approval | SCREENS.md §11.3, §15 |
| J-01.6 to J-01.11, J-01-ALT-1 to ALT-3 | SF-10:templates, SF-10:new, SF-10:detail, SF-12 | Templates, uploads, dry-run diff, approvals | SCREENS.md §12, §15 |
| J-01.12, J-01-AC-6 | SF-06:entries | `format=gross`, `from=2023-01-01`, `to=2023-01-31`; lines per WLD-X-26 | §3.5 |
| J-01.13 | SF-16 | Add connection; test connection | SCREENS.md §14 |
| J-01.14 | SF-06, SF-06:run | "Run journals" form, "Calculate journals"; submit on the run | §3.1, §3.2 |
| J-01.15 | SF-12 | Approve both runs | SCREENS.md §15 |
| J-01.16 | SF-06:run, SF-06:run-batches | "Export to <adapter label>"; repeated export posts nothing | §3.2, §3.4 |
| J-01-AC-1 to AC-5 | SF-02, SF-12, SF-03 | Empty state, approver identity, allocation walk, balances | SCREENS.md §3, §15, §4 |
| J-01-AC-7 | SF-09:audit-log | Audit events with actor ids | §6.3 |
| J-13.1 | SF-05 | Blocker table BLK-01 to BLK-16 with counts, owners and links | §1.1 |
| J-13.2 | SF-12 | Approve, reject with comment, review | SCREENS.md §15 |
| J-13.3 | SF-11 | Dismiss with reason | SCREENS.md §13 |
| J-13.4 | SF-03 | Release hold | SCREENS.md §4 |
| J-13.5 | SF-03:estimates, SF-12 | "No change" attestation and approval | SCREENS.md §8, §15 |
| J-13.6 | SF-05 | "Start soft close"; soft close banner | §1.1 |
| J-13.7 | SF-05, SF-05:close-run | "Run close"; 14 step labels with progress | §1.1, §1.2 |
| J-13.8 | SF-06:run, SF-12 | Submit on the Calculated action bar; approval | §3.2; SCREENS.md §15 |
| J-13.9 | SF-06:run, SF-06:run-batches | "Export to NetSuite"; batch acknowledgements | §3.2, §3.4 |
| J-13.10 | SF-05:reconciliations, SF-05:reconciliation | "Generate reconciliation", billing to subledger; chip Auto-certified under `AUTO-REC-01` | §2.1, §2.2 |
| J-13.11 | SF-05:reconciliation | "Pull trial balance from NetSuite"; difference 250.00 on account 2100 with `JE-NS-88121`; "Sign as preparer" | §2.2 |
| J-13.12 | SF-05:reconciliation | "Sign as reviewer" | §2.2 |
| J-13.13, J-13-AC-1, J-13-ALT-2 | SF-05 | "Submit for lock"; ERR-14 banner listing failing gates | §1.1 |
| J-13.14 | SF-05 | "Lock period" with reason and step-up (SCR-PERM-05) | §1.1 |
| J-13.15 | SF-10:detail | `LATE_EVENT` finding in the dry-run diff | SCREENS.md §12 |
| J-13.16, J-13-AC-9 | SF-05:multi-entity | "Close several entities"; "Start close runs"; three independent rows | §1.5 |
| J-13-AC-2 | SF-05:history | Lock entry with the gate results | §1.4 |
| J-13-AC-3 | SF-06:run | Balancing per entity and currency; totals by account | §3.2 |
| J-13-AC-4 | SF-06:run-batches | One external id per batch; repeated export idempotent | §3.4 |
| J-13-AC-5 | SF-05 | Locked chip; commands hidden | §1.1 |
| J-13-AC-6 | SF-09:pack | Manifest with a SHA-256 per file | §6.2 |
| J-13-AC-7 | SF-08:report | `intercompany_pairs` (RPT-35) | §5.6.6 |
| J-13-AC-8 | SF-05 | "Days to close" for Jul, Aug and Sep 2026 | §1.1 |
| J-13-ALT-1 | SF-05 | No "Lock period" control for `maya` (SCR-PERM-02) | §1.1 |
| J-14.1, J-14-ALT-3 | SF-05 | "Request reopen" drawer, reason `ERROR_CORRECTION`, judgement; `later-period-closed` refusal copy | §1.1 |
| J-14.2, J-14.3, J-14-AC-2, J-14-ALT-1 | SF-12, SF-05 | Two decisions with step-up; dual-approval status on the cockpit | SCREENS.md §15; §1.1 |
| J-14.4, J-14.5, J-14-ALT-2 | SF-10:detail, SF-12 | Post-reopen dry-run copy; approval | SCREENS.md §12, §15 |
| J-14.6 | SF-05:close-run, SF-06:run | Incremental close run; post-reopen journal run | §1.2, §3.2 |
| J-14.7, J-14-AC-3 | SF-05, SF-05:history, SF-08:report | "Submit for lock", "Lock period"; re-lock diff `variance_between_closes` (RPT-38) | §1.1, §1.4, §5.6.6 |
| J-14-AC-1 | SF-04, SF-08:report | WLD-X-13 figures | §4.1, §5.6.1 |
| J-14-AC-4 | SF-08:report | `je_population` (RPT-15) post-close flag | §5.6.3 |
| J-15.1 | SF-08:disclosure-pack | "Run disclosure pack", source As locked | §5.4 |
| J-15.2 | SF-04 | As locked Sep 2026: K-01 9,764.38; K-01b 4,891.30; K-03 229,852.94 | §4.1 |
| J-15.3 | SF-08:report | `contract_balances` (RPT-02) | §5.6.1 |
| J-15.4, J-15-AC-4 | SF-08:report | `rpo` (RPT-06); empty exempt listing | §5.6.1 |
| J-15.5 | SF-08:report | Export "Excel workbook (XLSX)" with the stamped header (RV-06, RV-07) | §0.5 |
| J-15.6 | SF-08:report | "Run details", "Rerun from the same source" (RV-03) | §0.5 |
| J-15.7 | SF-04 | `granularity=quarter`, AVM-JP, K-10 | §4.1 |
| J-15.8 | SF-08:report | `legacy_contract_history_export` (RPT-10) | §5.6.2 |
| J-15.9 | SF-08:disclosure-pack | Export "PDF"; no command actions for `robert` | §5.4 |
| J-15-AC-1 to AC-3 | SF-04, SF-08:report, SF-08:run | Figures; tie-out strip (RV-05); run records | §4.1, §0.5, §5.3 |
| J-16.1 | SF-01, SF-04 | Revenue figure drills to the waterfall | SCREENS.md §2; §4.1 |
| J-16.2, J-16.3, J-16-AC-1, J-16-AC-2 | SF-04 | Cell Explain; decomposition; "Verify" | §4.1; SCREENS.md §6 |
| J-16.4, J-16-AC-3 | SF-04, SF-03:schedules | Drill to schedule lines, events and the source row | §4.1; SCREENS.md §4.3, §6.6 |
| J-16.5 | SF-06:run, SF-06:run-lines | Revenue line 4010; source drawer; contract filter | §3.3 |
| J-16.6 | SF-04 | Enter drills, Esc returns focus to the cell (RV-09) | §4.1, §0.5 |
| J-17.1 | SF-22, SF-01 | "Sign in" without MFA challenge; read-only chip | §12.1; SCREENS.md §1.1 |
| J-17.2, J-17-AC-1 | SF-09, SF-09:pack | "Download pack"; manifest hashes | §6.1, §6.2 |
| J-17.3, J-17-AC-2 | SF-08:report | `je_population` (RPT-15) export "CSV with manifest" | §5.6.3 |
| J-17.4 | SF-09 | "Generate evidence pack", contract sample (RPT-55) for `PRJ-CB-2026-01` | §6.1 |
| J-17.5 | SF-09:audit-log, SF-09:verification | Object filter; "Verify chain now" | §6.3, §6.4 |
| J-17.6 | SF-08:report | `user_access_listing` (RPT-24); `sod_conflict_report` (RPT-25) | §5.6.5 |
| J-17.7 | SF-12 | Approvals empty state for an auditor | SCREENS.md §15 |
| J-17.8 | API; SF-08:report | `config_change_register` (RPT-23) | §5.6.5 |
| J-17-AC-3, J-17-AC-4 | all part-B screens | No command controls (SCR-PERM-02); export audit events | §0.5 |
| J-18.1 | SF-23:select, SF-17 | "New scenario" form | §11.3, §7.1 |
| J-18.2 | SF-01 | Sandbox banner and figures | SCREENS.md §1.1, §2 |
| J-18.3 | SF-17, SF-17:event-set, SF-10:new | "New forecast event set"; "Add forecast file" with `event_set` | §7.1, §7.2; SCREENS.md §12.2 |
| J-18.4, J-18-AC-4 | SF-17:event-set, SF-17:run | "Run forecast"; outputs (RPT-39); "Actual vs forecast" (RPT-40) | §7.2, §7.3 |
| J-18.5, J-25-AC-2 | SF-06:run | Export control with `aria-disabled` and the ERR-17 reason (SB-R-08; OQ-B-31) | §3.2 |
| J-18.6, J-18-AC-1, J-18-AC-2 | SF-18 | "Preview allocation"; WLD-X-25 figures | §7.4 |
| J-18-AC-3, J-18-ALT-1 | API | none | none |
| J-19.1 | SF-02, SF-20:new, SF-20 | "Review a contract document"; "Start review" | SCREENS.md §3; §8.1 |
| J-19.2, J-19.3 | SF-20 | Fields with citation and confidence, "Check" chip; accept, edit, reject per field | §8.2 |
| J-19.4, J-19-AC-1 to AC-3 | SF-20 | "Create draft contract" | §8.2 |
| J-19.5, J-19-AC-4 | SF-15:ai-call-log | Call log entry without contract text | §8.6 |
| J-19.6, J-19.7 | Explain panel on SF-03 | Proposed narrative block and dismissed note | §8.4; SCREENS.md §6 |
| J-19.8 | SF-15:ai | "Turn off AI now" | §8.5 |
| J-19.9 | SF-15:ai, SF-12 | "Submit for approval"; approval by another Tenant Admin | §8.5; SCREENS.md §15 |
| J-20.1 | SF-19, SF-19:new, SF-19:detail | "Import a legacy database" (OQ-B-32); "Upload and profile"; profile step | §10.1, §10.2, §10.3 |
| J-20.2 | SF-19:detail | Mapping step; preset notice; "Confirm mapping" | §10.3 |
| J-20.3, J-20-AC-1 | SF-19:detail | "Run import"; reconciliation step with `migration_reconciliation` (RPT-41) | §10.3, §5.6.7 |
| J-20.4 | SF-19:detail, SF-12 | "Submit for promotion"; promotion banner | §10.3; SCREENS.md §15 |
| J-20.5 | SF-03 | Contract 1 figures and History tab | SCREENS.md §4 |
| J-20-AC-2, J-20-AC-3 | SF-19:detail, SF-09:audit-log | Source hash unchanged; migration commands only | §10.3, §6.3 |
| J-20-ALT-1, J-20-ALT-2 | SF-19:new | ERR-19 and ERR-20 banners | §10.2 |
| J-21.1 | SF-19, SF-19:new, SF-19:detail | "Replay legacy templates"; plan of 14 files | §10.1 to §10.3 |
| J-21.2 | SF-19:detail | "Start replay"; sandbox banner | §10.3 |
| J-21.3 | SF-19:detail | Reconciliation step with `DEV-052` | §10.3, §5.6.7 |
| J-21.4, J-21-AC-2 | SF-19:detail, SF-12 | "Submit for promotion"; approval id on each batch | §10.3; SCREENS.md §15 |
| J-21.5, J-21-AC-1 | SF-06:entries | Gross views for May and Oct 2023 | §3.5 |
| J-21.6 | SF-08:report | `legacy_latest_contract_export` (RPT-12) as of 31 Oct 2023 | §5.6.2 |
| J-22.1 | SF-14 | "Invite user", scope AVM-DE | §9.10 |
| J-22.2 | SF-12 | Approval with step-up | SCREENS.md §15 |
| J-22.3, J-22.4, J-22-AC-2 | SF-22:accept-invitation, SF-22:mfa-enrol | ERR-21 copy; enrolment; recovery codes shown once | §12.3, §12.2 |
| J-22.5 | SF-03, X:not-found | "Contract not found" | SCREENS.md §0.7 |
| J-22.6, J-22.9 | SF-14:user | "Add role"; SoD-3 and SoD-1 blocking copy | §9.10 |
| J-22.7 | SF-14:user, SF-12 | "Request an exception" with compensating control | §9.10; SCREENS.md §15 |
| J-22.8 | SF-08:report, SF-14:sod | `sod_conflict_report` (RPT-25); link "SoD conflict report" | §5.6.5, §9.12 |
| J-22.10 | SF-22 | Lockout copy (ERR-23) | §12.1 |
| J-22.11 | SF-14:access-reviews, SF-14:access-review | "New campaign"; "Request revocation"; "Confirm revocation" | §9.13 |
| J-22.12 | SF-14:user | "Suspend" | §9.10 |
| J-22-AC-1 | SF-09:audit-log | Role changes, SoD exception, failed logins, MFA enrolment | §6.3 |
| J-23.1, J-23.2, J-23.4, J-23.6, J-23.7, J-23-AC-1 to AC-3 | SF-16, SF-16:connection, SF-16:sync-run, SF-12 | Connections, grouping policy, sync runs | SCREENS.md §14, §15 |
| J-23.3 | SF-16:developer | "New API client"; one-time secret dialog | §9.15 |
| J-23.5 | SF-15:product, SF-11:item | External id; "Reprocess" | SCREENS.md §10, §13 |
| J-23.8 | API | none | none |
| J-23.9 | SF-05:reconciliation | No sign-off controls for `nikhil` (SCR-PERM-02; SoD-7) | §2.2 |
| J-24.1 | SF-23:select, SF-01 | "Open Fernhill Software, Inc. (Demo)"; Home figures | §11.3; SCREENS.md §2 |
| J-24.2, J-24-AC-1 | SF-01, SF-25 | "Take the tour" on the SF-01 demo tour banner; six stops | SCREENS.md §2.4; §11.2 |
| J-24.3, J-24-AC-2 | SF-25 | "Next", "Finish"; toast "Tour complete"; preference write only | §11.2 |
| J-24.4 | every area | Real data in each area | §15; SCREENS.md SCR-ST-20 |
| J-25.1 | SF-15:sandbox | "Create sandbox copy" | §9.7 |
| J-25.2 | SF-03 in the sandbox | K-03 cumulative revenue | SCREENS.md §4 |
| J-25.3 | SF-15:sandbox | "Reset sandbox", "Back to the copy taken on <timestamp>" | §9.7 |
| J-25.4, J-25-AC-1 | SF-15:sandbox | Production: no Reset; "Restore into a new sandbox" (PRD "SF-15 workspace" names the Settings area; SCR-LTH places the actions on `/settings/sandbox`) | §9.7 |
| J-26.1 to J-26.3, J-26-AC-1, J-26-AC-3 | SF-03, SF-12 | "Void contract" and two approval steps | SCREENS.md §4, §15 |
| J-26-AC-2 | SF-08:report | `out_of_period_register` (RPT-16) | §5.6.3 |

## 17. Gaps closed

| Gap | Status | Evidence in this file |
|---|---|---|
| M-DES-06 Report specifications: waterfall, rollforwards, RPO time bands and disaggregation grids with drill-through and column definitions | **Closed** | §5.6 specifies all 55 codes of 04 T-RPT-01 (RPT-01 to RPT-55) with parameters, columns (header, field, format, alignment, drill, filter), grouping, totals, tie-outs, empty copy, export formats and sample figures; RV-01 to RV-14 fix the run stamp, run details, "As locked" source, tie-out strip, exports and stamped outputs. The literal and schema amendments OQ-B-02, OQ-B-08, OQ-B-09 and OQ-B-17 were adopted by 04 rev 1.2 (D-76) without reopening the specification |
| M-DES-01 Information architecture, core flows and screen specifications | Contributes (closed jointly with SCREENS.md) | Close cockpit (§1), reconciliations (§2), journal runs (§3), schedules (§4), reports (§5), evidence and audit log (§6); SCREENS.md covers the contract workbench, import wizard, approvals inbox and exception queue |
| M-DES-05 Controls UX | Contributes | Lock with reason and step-up (§1.1); reopen with dual approval and the re-lock diff (§1.1, §1.4); preparer and reviewer sign-off (§2.2); journal approval and idempotent export (§3.2, §3.4); promotion approval (§10.3); SoD blocking and exceptions (§9.10 to §9.12); AI configuration approval (§8.5) |
| M-DES-07 Legacy-user transition, onboarding and empty states tied to demo datasets | Contributes (closed jointly with PRD §7 and SCREENS.md SCR-LTH) | Legacy transition map (§11.4); legacy tour variant (§11.2); legacy database import and replay (§10); workspace setup checklist (§11.1); demo workspace selection and tour (§11.2, §11.3); empty states with exact copy on every screen |
| M-DES-03 Accessibility, M-DES-04 Internationalisation | Owned and closed by DESIGN_SYSTEM.md | Every screen carries accessibility notes; money and date formats follow DS §6 (SB-R-09) |

## 18. Open questions for supervisor

D-76 resolved every question below (revision 1.2). The Status column records each ruling and where it is applied. Revision 1.2 raises no question (D-77); build gaps become Spec questions in `PROGRESS.md`.

| Id | Question | Recommended default | Sections | Status |
|---|---|---|---|---|
| OQ-B-01 | DS-CMP-19 has no words for several part-B literals (for example Future, Permanently locked, Passed, Auto-certified, Promoted, Invited, Suspended, Revoked). | Adopt the "(proposed)" rows of §0.4 into DS-CMP-19 with the tones and icons given, together with SCREENS.md OQ-S-12. | §0.4 | Resolved by D-76: DESIGN_SYSTEM rev 1.2 DS-CMP-19 adds the words; the markers are removed from §0.4 and the other part-B tables |
| OQ-B-02 | 04 T-RPT-02 stores `tie_out_results` but defines no tie-out codes. | 04 adopts the twelve RPT-R-08 codes and names, plus `TO_BRIDGE_DRIVERS_EQ_DIFFERENCE` of RPT-33, with results `PASS`, `FAIL`, `NOT_APPLICABLE`. | §0.5, §5.6 | Resolved by D-76: 04 table 10-T with E-98 results; RV-05, RPT-R-08, RPT-33 |
| OQ-B-03 | E-62 `close_run_status` covers the run, but the per-step `steps[].status` of a close run has no literal set. | 04 applies E-62 to `steps[].status`; the step chips use the §0.4 E-62 words. | §1.2 | Resolved by D-76: 04 E-62 note and T-CLS-01 `steps[].status`; §1.2 |
| OQ-B-04 | Report screens need a lock reference for "As locked"; SCR-URL-06 first described `snapshot` differently. | `snapshot` = `period_lock.id`, passed to report runs as `period_lock_id`. Adopted by SCREENS.md OQ-S-18 and SCR-URL-06; no further action. | §0.5 | Resolved by D-76: default adopted; no change |
| OQ-B-05 | Sign-off dialogs (close tasks, reconciliation preparer and reviewer) show a statement with the checkbox "I confirm this statement", which 03 does not require. | Keep the checkbox as a client-side gate only; the command bodies stay as 04 defines them, and the audit event records the command as today. | §1.1, §2.2 | Resolved by D-76: default adopted; no change |
| OQ-B-06 | The reopen reasons (`ERROR_CORRECTION`, `LATE_SOURCE_DATA`, `AUDIT_ADJUSTMENT`, `OTHER`; PRD J-14.1) and the end-soft-close reasons (`CLOSE_RESTARTED`, `DATA_CORRECTION_PENDING`, `OTHER`) differ from the single `reason_code` set that SCREENS.md OQ-S-17 proposes for voids, reopen and cancel-close. | 04 adds one enum `reason_code` whose literals are the union of both sets, with per-command subsets: contract and event void use the OQ-S-17 set; `request-reopen` accepts `ERROR_CORRECTION`, `LATE_SOURCE_DATA`, `AUDIT_ADJUSTMENT`, `OTHER`; `cancel-close` accepts `CLOSE_RESTARTED`, `DATA_CORRECTION_PENDING`, `OTHER`. A literal outside the command's subset returns 422 `validation-failed`. Labels as §1.1 and SCREENS.md OQ-S-17 give. | §1.1, §1.4 | Resolved by D-76: 04 E-110 and table 3.4-R; §1.1, §1.4 |
| OQ-B-07 | SF-06:run needs totals by account and currency and the balancing check per entity and currency, which API-S-JournalRun does not return. | 04 adds `GET /journal-runs/{id}/summary` returning `lines [{account_code, account_name, currency, debit, credit}]` and `balance_checks [{entity_code, currency, debit, credit, difference}]`, all computed server-side (DS-FMT-02). | §3.2 | Resolved by D-76: 04 API-S-JournalRunSummary, whose balance checks add `basis` (04 B3-D20); §3.2 summary and balance checks grids; the columns 04 does not return are deferred to later |
| OQ-B-08 | API-S-ReportRunCreate has fixed keys, while several reports need report-specific parameters (for example lock ids, time band sets, grouping). | 04 adds `parameters: object`, validated against `report_definition.parameters_schema` (JSON Schema), with the keys §5.6 lists per report; the URL carries them as `p.<key>` (SCR-URL-17). | §5.2, §5.6 | Resolved by D-76: 04 API-S-ReportRunCreate `parameters` and T-RPT-01 rule 1; RPT-R-01 |
| OQ-B-09 | The disclosure pack has no T-RPT-01 code. | 04 adds `disclosure_pack` (kind `DISCLOSURE`, formats XLSX, PDF, JSON); its run references one child run per data section (RPT-01 to RPT-08) and the locked disclosure snapshots. | §5.4 | Resolved by D-76: 04 T-RPT-01 rule 2, T-RPT-02 `child_report_run_ids` and `disclosure_snapshot_ids`; §5.4 |
| OQ-B-10 | 04 defines no create schema for evidence packs. | 04 adds API-S-EvidencePackCreate `{kind, entity_code, book, period_key, period_lock_id, contract_external_ids, from_date, to_date, as_of}` with required fields per kind: Close needs entity, book, period and lock; Contract sample needs contract external ids and `as_of`; Change needs `from_date` and `to_date`; Access needs `as_of`. | §6.1 | Resolved by D-76: 04 API-S-EvidencePackCreate; §6.1 |
| OQ-B-11 | The folder layout inside evidence pack ZIP files is not fixed by 04. | Adopt the §6.2 path prefixes as the manifest layout; tests assert prefixes and per-file SHA-256, never file order. | §6.2 | Resolved by D-76: 04 T-RPT-04 manifest layout; §6.2 |
| OQ-B-12 | Dashboards `revenue` and `close` have no definition record. | Fixed client compositions in 1.0: the dashboard codes are route literals, each panel is an ordinary report run (RV-01), and no server dashboard entity exists. | §5.5 | Resolved by D-76: default adopted; no change |
| OQ-B-13 | Saving a deal preview (`POST /deal-previews/{id}/save`) is not in 04. | 04 adds the command for sandbox tenants that hold a scenario only; production previews are never saved and write only the `deal_preview.run` audit event (REQ-FC-006). | §7.4 | Resolved by D-76: 04 §16.14 `{contract_external_id}` → `{saved_contract_id}`, T-FC-04 (B3-D23); §7.4 |
| OQ-B-14 | Contract review needs the extracted document text and an accept body with per-field decisions, neither of which 04 defines. | 04 adds `GET /ai/proposals/{id}/document-text` (served from the stored extraction; never re-sent to the model) and the accept body `{field_decisions [{path, decision: ACCEPT, EDIT or REJECT, value, reason}], command: "contract.create_draft", entity_code}` returning `{contract_id}`. | §8.2 | Resolved by D-76: 04 API-R-47, §16.14, E-121; §8.2 |
| OQ-B-15 | Confidence could be shown as a decimal or a percentage. | Two decimals as text ("0.72"), with the outline chip "Check" below 0.75 (BR-AI-01). | §8.2 | Resolved by D-76: default adopted; DESIGN_SYSTEM DS-CMP-25 amended |
| OQ-B-16 | DS-CMP-25 shows "Accept" on proposal blocks, but a Q&A answer has no command to accept. | DS-CMP-25 notes that "Accept" renders only for proposals bound to a command; answers offer "Copy answer" and "Dismiss". | §8.3 | Resolved by D-76: DESIGN_SYSTEM DS-CMP-25 amended; §8.3 |
| OQ-B-17 | `variance_between_closes` (RPT-38) compares two locks, but API-S-ReportRunCreate carries one `period_lock_id`. | Report-specific keys `from_period_lock_id` and `to_period_lock_id` under OQ-B-08. | §1.4, §5.6.6 | Resolved by D-76: 04 API-S-ReportRunCreate keys; §1.4, RPT-R-01 |
| OQ-B-18 | Enabling AI, changing the model or enabling contract-text sending needs approval by another Tenant Admin (BR-AI-02), while "Turn off AI now" is immediate; 04 names neither the approval subject nor the kill-switch endpoint. | Configuration changes go through `POST /policies` with category `AI` and the normal policy approval; 04 adds `POST /tenant/ai/disable` `{comment}` with step-up, effective at once, audit event `ai.disabled`. | §8.5 | Resolved by D-76: 04 API-R-04, §16.14, T-PLT-01 `ai_disabled_at` (B3-D09); §8.5 |
| OQ-B-19 | 04 API-R-17 to API-R-20 name write permissions (`masterdata.maintain`, `config.author`, `period.close`) that the PRD setup actor (Tenant Admin, J-01.2) does not hold. | 04 amends those endpoints to accept the any-of permissions §9.2 to §9.4 list; opening a period accepts `period.close`, or `settings.manage` while `setup_completed_at` is null. | §9.2 to §9.4 | Resolved by D-76: 04 API-R-17 to API-R-19 any-of sets and `POST /periods/{id}/open`; API-R-20 is unchanged; §9 permission note, §9.2 to §9.4 |
| OQ-B-20 | Profile, tour and workspace selection need `/me` and session read-model additions: preferences, last opened per workspace, identity providers. | 04 adds `PATCH /me/preferences` `{format_locale, theme, density, shortcuts_enabled, tour_completed}`, `last_opened_at` on each membership of API-S-Me, and `identity_providers [{code, name}]` in the `GET /session` capabilities. | §9.9, §9.14, §11.2, §11.3 | Resolved by D-76: 04 §16.12, E-123, E-124, API-S-Session (B3-D15); §9.9, §9.14, §11.2, §11.3; the SF-23:select industry, roles and source columns are deferred to later |
| OQ-B-21 | The role matrix download has no report code. | Keep it as section "Role matrix" of `user_access_listing` (RPT-24); no separate code. | §9.11 | Resolved by D-76: default adopted; no change |
| OQ-B-22 | Blockers BLK-10 "Journal run not calculated" and BLK-13 "Reconciliations not generated" are derived conditions that API-S-PeriodCockpit does not expose. | 04 adds blocker codes `JOURNAL_RUN_NOT_CALCULATED` and `RECONCILIATIONS_NOT_GENERATED` with counts to the cockpit response. | §1.1 | Resolved by D-76: 04 API-S-PeriodCockpit `derived_blockers[]`, E-122; BLK-10, BLK-13 |
| OQ-B-23 | Multi-entity close (`POST /close-runs/multi-entity`) is not in 04. | 04 adds the command returning one close run and job per entity; until then the client sends one close-run command per entity with its own `Idempotency-Key` and reports per-entity results (as SCREENS.md OQ-S-16). | §1.5 | Resolved by D-76: 04 API-R-39 and §16.8 `results[]`; §1.5 |
| OQ-B-24 | The About dialog needs the engine release, which `GET /me` does not return. | 04 adds `engine_release {engine_version, build_sha, schema_revision}` to API-S-Me. | §11.5 | Resolved by D-76: 04 API-S-Me `engine_release`; §11.5 |
| OQ-B-25 | Subledger-to-GL reconciliation items need the GL document reference, which the 04 reconciliation item table (T-CLS-07) has no column for. | 04 adds `gl_document_reference text NULL` to T-CLS-07, filled from the pulled trial balance detail when the adapter provides it. | §2.2 | Resolved by D-76: 04 T-CLS-07 `gl_document_reference`; §2.2 |
| OQ-B-26 | `POST /ai/explanations` has no subject type for exception items, which anomaly flags need. | 04 adds `exception_item` to the explanation subject types; flags stay read-only and never change data. | §8.4 | Resolved by D-76: 04 §16.14; §8.4 |
| OQ-B-27 | DESIGN_SYSTEM has no tour component. | DESIGN_SYSTEM records the §11.2 popover as a named composition (panel surface, non-modal dialog, step counter, "End tour", "Back", "Next" or "Finish") and the gallery shows it (§13, section 10). | §11.2, §13 | Resolved by D-76: DESIGN_SYSTEM DS-CMP-32 and DS-VER-06; §11.2, §13 |
| OQ-B-28 | Password change, password reset and the invitation lookup have no 04 endpoints. | 04 adds `POST /me/password`; `POST /session/password-reset` (always 202, rate limited, single-use token valid 60 minutes); `POST /session/password-reset/confirm`; `POST /session/invitations/lookup` `{token}` returning inviter and workspace display names (the token never appears in a URL path or query). Every success ends the user's other sessions (SAR-10). | §12.3 | Resolved by D-76: 04 API-R-01, API-R-03, §16.12, T-PLT-42 (B3-D10); §12.3 |
| OQ-B-29 | PRD J-24.2 starts the tour with "Take the tour", but no screen rendered that control; SF-01 is owned by SCREENS.md. | SCREENS.md §2 renders the SF-25 demo banner exactly as §11.2 specifies. | §11.2 | Resolved by D-76: SCREENS.md §2.4 renders the banner; PRD J-24.1 aligned |
| OQ-B-30 | Several screen parameters of this file are not SCR-URL rows (§14.3). | SCREENS.md adds them to SCR-URL with the values of §14.3. | §14.3 | Resolved by D-76: SCREENS.md SCR-URL-15 amended and SCR-URL-24 to SCR-URL-32 added; §14.3 cites them |
| OQ-B-31 | PRD J-18.5 says "Export journals", while the SF-06:run export command is labelled "Export to <adapter label>". | The label is "Export to <adapter label>" when the entity has an active GL connection and "Export journals" otherwise; in a sandbox the control renders `aria-disabled` with the SB-R-08 reason and the API returns 403 `sandbox-restricted`. | §3.2 | Resolved by D-76: PRD J-18.5 aligned; §3.2 stands |
| OQ-B-32 | PRD J-20.1 says "Import legacy database", while SCREENS.md SCR-LTH-13 fixes "Import a legacy database". | Use "Import a legacy database" (SCR-LTH-13); PRD J-20.1 wording is amended; tests locate the button by that name. | §10.1 | Resolved by D-76: PRD J-20.1 aligned; §10.1 stands |
