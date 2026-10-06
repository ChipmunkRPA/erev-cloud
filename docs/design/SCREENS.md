# eRev Cloud: screen specifications (index, information architecture and core workbench)

| Field | Value |
|---|---|
| Owner | Principal product designer (design phase B2, slug `screens-a`); revision 1.2 by owner-editor `fix-screens` (design phase B3); revision 1.3 by residue sweeper `doc-residue` (post-B3 residue sweep); revision 1.4 by the supervisor (D-90a); revision 1.5 by lane F-WEB-R (D-97 (3)/(3a); readiness row SSP-EDITOR-ADMISSION); revision 1.6 by lane F-WEB-R (SSP-ADMISSION-R1); revision 1.7 by lane FIX-A (the supervisor's ruling R-17; PRD rev 1.21 WLD-X-06); revision 1.8 by lane WEB-QA (the supervisor's ruling R-59); revision 1.9 by lane SECFIX-PLT (security review of 2026-09-29, findings P3-4 and S3; ruling R-48); revision 1.10 by lane QA-BE (the supervisor's ruling R-76; 04 rev 1.132); revision 1.11 by lane WEB-QA (supervisor rulings R-61 (f) and R-89: the Step 1 path of §4.1.3, §4.1.5, §4.1.6 and §4.9.1 and the criteria-met region of §15.4; SCR-URL-09: `sort` on a screen with several grids); revision 1.12 by lane F-CTR-WEB (BUILD_SPEC CTR-24; the supervisor's answers of 2026-09-30 to the lane's read-in and rulings R-89, R-93); revision 1.13 by lane F-ADM-WEB (BUILD_SPEC RPS-21: the screen parameter `event` of SF-09:audit-log; BUILD_SPEC DIN-18: §14 as bound to API-R-45 of 1.0); revision 1.18 by lane WEB-QA (supervisor ruling R-104 (a) and (b), item W-22 part 1: §15.3 flag labels; §15.4 the subject link, the notice of a request without a stored preview, the caption of "Revenue by period", enumeration labels and the cue of the sticky decision form); revision 1.19 by lane WEB-QA (item W-13, crawl finding F4: SCR-URL-13, a panel tab removes the list parameters of the pane it leaves); revision 1.20 by lane F-ADM-WEB (BUILD_SPEC WEB-16: §15.3, §15.5 and §15.7 as bound to API-R-09 of 1.0, SCR-URL-18, §1.3 the pill on the SF-12 family; §14.2 and §14.8 the totals of a sync run in records; supervisor ruling R-112 (h); §0.5 SCR-URL-32 `event` carries the audit event's chain sequence, the supervisor's ruling of 2026-09-30 19:31); revision 1.21 by lane WEB-QA (supervisor ruling R-112 (h), item W-17: §4.1.2 the marker of "Figures as of"; §4.1.4 the heading of the strip names the measured period, and Billed, Recognized and Scheduled open the list level of the Explain panel; §4.1.8 the state of figures the API refuses at the period; §6.3 and §6.4 the list level; SCR-URL-11); revision 1.22 by lane F-ADM-WEB (BUILD_SPEC RPS-18: §0.4 RT-33 and RT-106 open for `report.run` or `audit.read`); revision 1.24 by lane WEB-QA (supervisor ruling R-115 (g), item EXPLAIN-BALANCE-LINKS-1: §4.1.4 and §4.4, a balance figure is an Explain trigger where its entry's `links` name its explanation); revision 1.23 by lane F-CTR-WEB (BUILD_SPEC CTR-27: §7 as bound to API-R-31 of 1.0, §4.1.6 the modification commands on active contracts, §0.12 the SF-07 capture; the supervisor's answers of 2026-09-30 to the lane and ruling R-114 (h)); revision 1.26 by lane SECFIX-ACT (the supervisor's ruling R-118 (e), item MOD-DISCARD-1: §7.3 "Discard draft"); revision 1.30 by lane WEB-QA (item W-12, the supervisor's ruling of 2026-10-01; 04 rev 1.148: §0.6 SCR-PERM-01 and -02, a permission is held for entities, and a control asks one of four questions); revision 1.31 by lane F-ADM-WEB (item TPL-EFFECTIVE-FROM-UI-1; the supervisor's message of 2026-10-01 03:30 on lane ENG-FX's CFG-BACKDATE-1, PRD ERR-75: §11.2 the Meta with Effective from, §11.0 the two forms of the effective date and a refused command, §11.1 and §11.3 as bound to them, §15.4 the approver's sentence, §10.4 the product code, §0.12 the draft capture); revision 1.15 by lane SECFIX-IMP (the supervisor's rulings R-49 (a) and R-86: §15 names the screen item of the approval subject `EVIDENCE_SHRED`); revision 1.32 by lane SECFIX-APR (item APR-CONTENT-SCOPE-1, the supervisor's ruling of 2026-10-01; 04 rev 1.208: §15.4, what a reader who covers part of a request's entities is shown); revision 1.34 by lane WEB-QA (item W-12, slice b; supervisor ruling R-28 and the supervisor's ruling of 2026-10-01 on the slice's pre-build line: §0.6 SCR-PERM-01 and -02, §0.7 SCR-ST-06, §2.1, §2.3, §2.7 and §4.7 — the audit events are read with `audit.read` for all entities, and a read the API refuses renders what a member without the permission sees, not an error with "Retry"); revision 1.35 by lane F-ADM-WEB (two items of the supervisor's message of 2026-10-01 08:07, register index 129: §10.4 a refused "Save product" at the drawer's controls and in its banner; §14.4 "Test connection" in a sandbox, with its copy key in §14.7); revision 1.27 by lane SECFIX-PLT (independent review of the platform security merge a7d63e81; supervisor rulings R-111 (2) and (4); PRD rev 1.118 BR-PLT-07: §15.7 the limits of a delegation — the end within 90 days of today, the delegate's second factor, the separation-of-duties finding, the administrator's "End delegation"); revision 1.37 by lane F-CLO-B (item CLO-QUARANTINE-READ-1, supervisor ruling R-121 (i): §2.5 and §2.6 — the home page's close row reads "Exceptions holding the lock" and links to the exception queue with `blocking`; the key figure stays "Open exceptions"; §13.3 and §13.4 — the queue's `entity` and `blocking`); revision 1.29 by lane F-CTR-WEB (BUILD_SPEC CTR-25: §8 as bound to API-R-32 of 1.0, with the keys of the constraint checklist; §4.6 without the toolbar pair; §4.1.3 the allocation line of the tracker; §5.8 "Change price"; §0.12 the estimates captures; the supervisor's answers of 2026-10-01 to the lane); revision 1.33 by lane SECFIX-ACT (supervisor rulings R-118 (e) and R-119 (e), items EST-DISCARD-1 and MOD-LINKED-ESTIMATES-1: §0.8 E-12 `VOIDED`, §7.4 the linked panel's source, §8.4 "Discard draft"); revision 1.39 by lane F-CTR-WEB (item HIST-CALC-CHIP-1: §4.7 the chip "Calculations" reads the system's items, and an audit event names the principal it was written for); revision 1.43 by lane F-ADM-WEB (item SBX-ADD-CONNECTION-1, the supervisor's message of 2026-10-01 09:41; register index 153: §14.4 "Add connection" in a sandbox, with its copy key in §14.7); revision 1.44 by lane F-ADM-WEB (the product drawer's Code; the supervisor's message of 2026-10-01 on lane API-GAPS' `code_frozen`, 04 rev 1.223; register index 154: §10.4 Code is read-only while the product's code is frozen); revision 1.40 by lane WEB-QA (item KIT-FILTER-LEAVING-1, register index 144: §0.5 SCR-URL-33 — a control of a page that is leaving writes nothing, with the limit that a page is known by its route and not by its record; the FilterBar works out a write from the address as it stands at that moment); revision 1.41 by lane FIX-D2 (supervisor rulings R-78 (d) and R-121 (g), and the supervisor's ruling of 2026-10-01 on the lane's finding on the Home: §2.5 — the Home's revenue is that of the entity that performs; revenue, contract liability and RPO are read as the reports' jobs read them; the refusal for an entity that performs in another currency); revision 1.42 by lane F-CTR-WEB (items MOD-DISCARD-1, MOD-PATCH-CLEAR-1 and MOD-ANSWER-PREVIEW-1 on the screens: §7.3 "Discard draft" as bound, §7.4 the kind of a price change, §7.6 the override record, §7.8 one request for one submission, §7.10 the voided-request banner a warning, §0.12 the SF-07 capture; with the supervisor's word of 2026-10-01 on a red row of main: §7.5 a stored answer stays confirmed and is sent, whatever a classification names as a proposal, and §7.12 the requests and steps of the J-06 row); revision 1.36 by lane F-SNP (item REG-VERSION-WHOLE-SET-1, the supervisor's ruling of 2026-10-01, point D; 04 rev 1.183: §11.3, the basis of "New policy version" and the Proposed value of a key the version returns to the default); revision 1.47 by lane WEB-QA (item KIT-UNPLACED-ERRORS-1, head 1, register index 169: §0.7 SCR-ST-13 "Refused command" — a refused command is said in one banner and at the fields it names, each sentence once, and never nowhere); revision 1.49 by lane WEB-QA (item KIT-FILTER-LEAVING-2, register index 171: §0.5 SCR-URL-33 — a page is leaving from the moment the member starts for another page; the limit restated); revision 1.48 by lane WEB-QA (item W-12d: §15.4 "Content withheld" — region 2 without the no-rights notice, a decision's comment wherever the API sends one, the banner's message); revision 1.52 by lane F-CTR-WEB (item MOD-PRICE-TEST-FACT-1 on the screens, register index 178, taken out of patch item (b) and delivered ahead of it: §7.5 the sentence of the price test stays under a stored answer, with the attested sentence for an answer of Yes; §7.6 the range or point beside the SSP version is read from the row's `price_tests`; §7.11 the three copy keys; second part, the rest of patch item (b), items MOD-PREVIEW-JOURNAL-RULE-1 and MOD-PREFILL-READ-1 on the screens: §7.7 the journal preview states when and for which period it was computed and warns once that period is no longer the latest postable one, §7.5 a classified draft opens on the proposals its row carries, §7.2 and §7.12 the journal preview of J-05 from the rule as built, and for item MOD-PRICE-TEST-FACT-1 §7.9 the price test on SF-07:detail and §7.5, §7.6 the SSP version its figures belong to); revision 1.50 by lane F-CLO-WEB (register index 157: §13 — the exception queue under `blocking` says that its list is cut down, with the way back to every exception); revision 1.38 by lane WEB-QA (item W-12, slice c, head c3, register index 131: §0.6 SCR-PERM-02 — `import.upload` asks any entity; an exception its own entity, any entity when it has none); revision 1.55 by lane F-ADM-WEB (PRD J-06 rev 1.158 and 1.164 and BR-MOD-02 rev 1.139 on the approvals screens: §15.4, §15.5 and §15.9 — the estimate versions and the judgement record of a change order are requests of their own, decided before the modification's; "Open linked requests" is named and not built); revision 1.51 by lane F-CTR-WEB (items MOD-LINKED-ESTIMATES-1 and EST-DISCARD-1 on the screens, register index 177: §7.4 the linked estimate versions and "Add estimate version" as bound, §7.8 the summary, the submission that waits for the versions' approval and "Linked requests", §8.3 "Discard draft" as bound and the latest version that is not Void; §7.12 the J-06 row from PRD rev 1.158 and 1.164; §0.12 the captures `sf-07-change` and `sf-03-estimate-discard`); revision 1.52 by lane F-CTR-WEB (item MOD-PRICE-TEST-FACT-1 on the screens, register index 178, taken out of patch item (b) and delivered ahead of it: §7.5 the sentence of the price test stays under a stored answer, with the attested sentence for an answer of Yes; §7.6 the range or point beside the SSP version is read from the row's `price_tests`; §7.11 the three copy keys); revision 1.57 by lane SECFIX-PLT (item DELEG-LIST-SCOPE-1, ruling R-28: §15.7 — an access administrator of named entities is shown the delegations they may end and those they are a party to); revision 1.53 by lane F-CTR-WEB (patch item (c), CTR-28's screens, register index 179: §1.4 the record search of the command palette and SF-24:results as bound; §0.4 RT-95 asks `contract.read`; §0.12 the captures `sf-24-results` and `sf-24-palette`); revision 1.59 by lane WEB-QA (the dismissal line of SF-11: §13.5 — "Request a waiver instead." stands only while "Request waiver" is offered); revision 1.60 by lane WEB-QA (the binding of APR-REQUEST-REASON-1: §15.4 — region 3 shows the comment a request was submitted with whenever the API sends it; the banner of a withheld request stands in place of regions 4 to 6); revision 1.62 by lane F-CTR-WEB (the Origin cell of an event, register index 240: §5.6 the Events panel of SF-03:obligation and §4.4 column 9 of the invoices as bound — the event's own members name its origin, an integration as "Integration" and an API client by its name); revision 1.64 by lane F-CTR-WEB (item EST-DRAWER-JUDGEMENT-1, register index 245: §8.4 the constraint's judgement record — asked at the submission, a new version's own, a record that does not stand replaced, the findings of a submission on their fields; §8.3 the open version of an element whichever its number, and what the draft and the pending banner say of the record); revision 1.56 by lane F-SNP (item POLICY-WITHDRAW-ROUTES-1, the supervisor's order of 2026-10-01; register index 207: §11.0 and §11.3 — "Withdraw" on an accounting policy version returns its author to a draft; a rejected or withdrawn version is edited again, or leads to "New policy version" once a later version was published; the help of a date that cannot be edited, the Key column and the grid's literals, what the two create forms say of a refusal, the room of the parameter grid, and another open version of the scope); revision 1.63 by lane F-SNP (item POLICY-WITHDRAW-ROUTES-1, the supervisor's ruling of 2026-10-02 on the independent review of the head; register index 207: §11.3 — PRD ERR-09's banner on a policy version names the control that changes its values); revision 1.61 by lane F-CLO-WEB (item RPT-VIEW-CONTEXT-DEFAULT-1, register index 229: §0.5 SCR-URL-01 — the report screens SF-04, SF-08:report and SF-08:dashboard take the context pill's entity when their address names none, and say "All entities" with the screen parameter `entities=all`); revision 1.65 by lane F-CTR-WEB (item MOD-REJECTED-REVISE-1 on the screens, register index 246: §7.9 a rejected modification — the banner under the header, "Revise" with its confirmation and the empty `PATCH`; §7.10 the states "Rejected" and "Revised draft", and the banners of a draft's earlier request on the read-only detail of a draft; §7.11 the five copy keys); revision 1.66 by lane F-CTR-WEB (the discard of a draft judgement record, PRD ERR-95 and the word of a record's status on the screens, register index 247: §0.8 the status of a judgement record in text; §4.1.3 draft Step 1 records and "Discard"; §4.9.1; §7.4, §7.6 and §7.8 the wizard's linked records, override banner and submission; §8.3 the pending banner's evidence sentence and "Evidence"; §8.4 the hint of "Attest no change"); revision 1.72 by lane F-CTR-WEB (the draft editor and the Step 1 path under supervisor ruling R-102 (c), register index 267 (iii): §4.1.3 the path counts standing assessments, and a reviewed record that the API refuses; §4.1.6 the overflow of a draft; §4.1.7 the voids in the path's read; §4.9.1 the assessment drawer's offer of a new review; §4.10 the editor opens on a draft that carries a Step 1 assessment); revision 1.74 by lane F-CTR-WEB (the exit of a rejected judgement record on the screens, register index 274's web half: §0.8 what `VOIDED` is; §4.1.3 rejected Step 1 records and "Discard"; §4.9.8 the checklist's line of a rejected record; §7.4 and §8.3 "Discard" on a rejected record); revision 1.76 by lane F-CTR-WEB (the judgement record of a policy override and the records the activation checklist waits for, register index 287: §4.9.7 the override's record is sent for review; §4.9.8 the draft and pending records under "Judgement record required", with "Discard", "Send for review" and "View request"; §4.1.3 "View request" on a rejected record's line and the word of step 2's "Distinct review"); revision 1.70 by lane FIX-D2 (item ACT-FLAGS-1, register index 260: §15.3 — the labels of the six routing flags a contract activation gained); revision 1.75 by lane F-CTR-WEB ("Release hold", register index 281, the screen half: §4.1.6 the command in the header of a contract on hold, in every status, and its permission; §4.9.4 the drawer bound to the open holds of 04 rev 1.299; §5.1 the permission; §5.6 the table "Holds" of the obligation pane with the command or the API's sentence; §5.10 two test hooks); revision 1.77 by lane F-CTR-WEB (a stored preview of a modification that the reader is not shown, register index 276, the screen half: §7.7 the rule of a stored preview and the notice on step 4; §7.9 the notice on SF-07:detail; §7.10 the state; §7.11 three copy keys; §7.13 one test hook); revision 1.71 by lane WEB-QA (item W-12e and the blank submission comment: §0.6 SCR-PERM-01 and SCR-PERM-02 (c) — the acts on the whole workspace ask their permission for all entities, and a page such a member may not read says so; §15.4 — region 3 is rendered whenever the comment is not blank); revision 1.78 by lane F-CTR-WEB (the drawer "Combine with another contract" gives up the proposal it made, register index 266, the screen half: §4.9.7); revision 1.79 by lane F-CTR-WEB (what the preview panels say of a dry run that ended without a summary, register index 300 on the screens: §4.9.3, §8.4); revision 1.80 by lane F-CTR-WEB (policy overrides are not in release 1.0, register index 308, the web half: §4.9.7 the drawer withdrawn; §4.1.6, §5.1 and §5.3 its two menu items; §6.3 the source record's link); revision 1.81 by lane SECFIX-CLO (the template editor's policy values panel shows the refusal of a level P value that no computation reads in the form's banner, register index 309: §11.2, one clause, as built) |
| Date | 2026-10-03 (revision 1.81) |
| Status | Binding build contract. Read-only for the build loop (`docs/01-DECISIONS.md` §0). |
| Precedence | One rank with `docs/design/SCREENS_B.md` (D-74), below `docs/design/DESIGN_SYSTEM.md` for every visual, token, formatting and component rule. Enumeration literals, permission codes, problem slugs and finding codes are `docs/04-DATA_MODEL.md` verbatim (D-73). Product behaviour and copy that `docs/02-PRD.md` fixes are cited, not changed. This file owns the route path of every PRD SF id (D-73). |
| Companion | `docs/design/SCREENS_B.md`: close, journals, reports, admin, AI and onboarding screens. The index below lists every section of both files. |
| Applies decisions | D-02 (vocabulary, rail), D-12 (labelled balances), D-19 (dual dates), D-20 (estimate versions), D-30 and D-30a (import flow, findings), D-46 (AI proposals), D-60 (layout, Explain), D-62 (anti-slop), D-73 (identifier and route authority), D-74 (split screen contract), D-75 (negative style, demo users, upload limits), D-76 (rulings on OQ-S-01 to OQ-S-21 and API gaps R-01 to R-40), D-77 (design freeze) |
| Inputs | `docs/00-GOAL.md`; `docs/01-DECISIONS.md` incl. §7; `docs/02-PRD.md` §0 to §5 and §7; `docs/03-REQUIREMENTS.md` (REQ-UX, REQ-CON, REQ-SSP, REQ-POL, REQ-DAT); `docs/04-DATA_MODEL.md` §3, T-PLT-11, §15, §16; `docs/dev-guide.md` §8, §9.8; `docs/design/DESIGN_SYSTEM.md` rev 1.1; `docs/reviews/B1-consistency.md` §6.2 row 7; `docs/research/rightrev-ui/` images 02, 06, 14, 17 (layout calibration only; nothing copied); revision 1.2: `docs/01-DECISIONS.md` §8 (D-76, D-77), `docs/04-DATA_MODEL.md` rev 1.2 (§3 E-110 to E-124 and table 3.4-R, table 15.4-I, §15.3, §16.0 to §16.14, table 1.2-D), `docs/reviews/B3-fix-fix-data-model.md`, `docs/design/DESIGN_SYSTEM.md` rev 1.2 |

Legend for claims: **[F]** fact with a cited source; **[J]** judgement by this author with a one-line rationale; **[A]** assumption, listed again in §16 when material.

## Revision log

| Rev | Date | Editor | Change |
|---|---|---|---|
| 1.0 | 2026-09-12 | `screens-a` | First binding issue |
| 1.2 | 2026-09-12 | `fix-screens` (design phase B3) | D-76 and D-77 applied: tables 1.2-A and 1.2-S below. No revision 1.1 was issued; the number matches the B3 revision of the other design documents |
| 1.3 | 2026-09-12 | `doc-residue` (post-B3 residue sweep; detail in `docs/reviews/B4-doc-residue.md`) | **Applied.** §4.4 renders the 04 API-S-UsageCommitment `status` literals `IN_PROGRESS`, `MET` and `SHORTFALL` as DS-CMP-19 chips "In progress", "Met" and "Shortfall", with "billable at <status_date>" as text after the chip; the usage-commitment rows of tables 16-A and 16-B bind `status`, not a label field (04 B3-D13). §11.4 sample world: the J-02.5 coverage finding reads 41.0% (16 of 39 observations inside 95,200.00 to 128,800.00). §11.5 sample world states the band bounds and the pre-exclusion count 16 of 40 (40.0%), following the PRD rev 1.3 recomputation of WLD-X-24; the wireframe figures (39, 1, 113,000.00, 43.6%, 17 of 39) are unchanged. **Verified without change.** No screen figure uses a value that the post-B3 numeric residue sweep changed |
| 1.4 | 2026-09-17 | supervisor (D-90a) | **Applied.** §0.4 RT-56 and RT-57 state the 04 API-R-09 visibility (preparer, decider or holder of a step permission) and the SF-12:request not-found state (QA-L9-6). §2.3 and §2.5 Waiting for you lists the pending requests assigned to the user, across entities, without `entity`; the Pending approvals key figure counts decidable requests of the context entity (QA-L9-4; L7-2-Q-22). §2.9 rc note: WLD-B-02 is not seeded (L5-4-Q-7) |
| 1.5 | 2026-09-19 | lane F-WEB-R (D-97 (3)/(3a); readiness row SSP-EDITOR-ADMISSION) | **Applied.** §11.4 entries table: Basis offers the four E-49 bases ("Per increment (series)", "Per booked term (series)" added, 04 rev 1.17 / ENG-C1b); a series product (`distinctness_default` = `series`) has no default basis — "Choose a basis" until chosen, refused at the field on save; new row 5a Quantity unit (E-125 `quantity_unit`: "Service units", "Increments"), shown and required only while Basis is "Per increment (series)", round-tripped through every edit of the entry; API refusals at `entries[i].value_basis` / `entries[i].quantity_unit` (422 `validation-failed`, D-97 (3a)) show at the field. The import channel (SCR-LTH-01 legacy SKU SSP template) admits the same two fields under lane F-DIN, outside this row |
| 1.6 | 2026-09-19 | lane F-WEB-R (SSP-ADMISSION-R1; Codex `PRODUCTION-SSP-EDITOR-ADMISSION-ad8a117.md`; joint ruling with ENG-C1b) | **Applied.** §11.4 row 5: the no-default-basis rule keys to the API's derived, read-only `requires_explicit_ssp_basis` on API-S-Product (true when the product's default POB template version declares `series` distinctness — the predicate C1b's API applies), not to the product's own `distinctness_default`, which stays display-only; the two attributes can disagree (a `distinct` product with a published series default template must still be asked for its basis). Until the API carries the field the editor falls back to `distinctness_default` = `series` (bridge, recorded in the lane record) |
| 1.7 | 2026-09-30 | lane FIX-A (the supervisor's ruling R-17 of 2026-09-29; `docs/02-PRD.md` rev 1.21; number taken as the next free one and reported to the supervisor) | **Applied.** The sample-world quotations of PRD WLD-X-06 follow its corrected allocation split; no layout, state, copy key or test hook changes. §4.7 History tab: the K-02 compare reads O1 remaining allocation 155,178.08 → 148,451.55 (Delta (6,726.53)) and the added obligation 66,726.53. §7.2 wireframe "Impact preview": the two "Allocation by obligation" rows (Remaining after 148,451.55 and 66,726.53; Change (6,726.53) and +66,726.53). §7.12 sample world, J-05 K-02: modification-date SSPs remaining O1 155,178.08 and added seats 69,750.00 — the low bound of their range 69,750.00 – 85,250.00, because the stated price is below it (POL-072); remaining O1 155,178.08 → 148,451.55; added obligation 66,726.53. Unchanged: every total (transaction price, catch-up, revenue by period, RPO) and the word "Upgrade" (TA-K02-MOD-KIND-1, open) |
| 1.8 | 2026-09-30 | lane WEB-QA (the supervisor's ruling R-59 of 2026-09-30; browser-QA finding Q-9; number assigned by the supervisor in the lane package) | **Applied.** §11.0 gains the row "Effective date": 04 SC-V `effective_from` and `effective_to` are instants; every Policies screen shows their UTC date (DS-FMT-17 date part; DESIGN_SYSTEM DS-I18N-08 rev 1.6) — the "Effective <date>" caption and chip, the Effective from field and the Effective from and Effective to columns of the list grids — and a version editor sends the picked date as 12:00:00Z of that date. §11.1 Meta row and the §11.3 version editor: "Effective from" is a date, not a date-time, sent as §11.0 says; the §11.1 definition list shows Effective from and Effective to as dates. The known limitation (an entity beyond UTC+11 reads the next day, item CFG-EFFECTIVE-DATE-1) is named in §11.0. §11.3 list grid and §11.6 versions grid: Effective from and Effective to are "DS-FMT-17 date part", and Effective to is the stored boundary, the date on which the next version takes effect, exclusive (supervisor ruling R-65). No route, test hook or copy key changes |
| 1.9 | 2026-09-30 | lane SECFIX-PLT (security review of 2026-09-29, findings P3-4 and S3; supervisor ruling R-48 (a), (c); number assigned by the supervisor; 1.8 is lane WEB-QA's) | **Applied.** §15.4 "Impact preview unavailable": when the stored preview of a request cannot be loaded, a warning banner replaces the silent empty diff and "Approve" is unavailable until the preview loads, "Reject" stays (the panel had rendered no diff, said nothing and offered Approve); §15.6 names the state; §15.8 gains the three copy keys. §15.7: creating and revoking a delegation ask for the step-up confirmation (text only until the delegations screen is built, WEB-16). The API enforces both (04 rev 1.108 API-R-09) |
| 1.10 | 2026-09-30 | lane QA-BE (the supervisor's ruling R-76 of 2026-09-30 on browser-QA findings Q-1 and Q-2; `docs/04-DATA_MODEL.md` rev 1.132; number assigned by the supervisor, register index 41; the screens are built by lane WEB-QA as item W-17) | **Applied.** §4.1.2 Meta row: "Last computed" binds `context.computed_at`, the time of the computation that produced the version in context; `context.known_at` is the read's record cut-off and feeds the "Known at" banner only. The row gains "Figures as of <period label>" with the stale marker when `context.measured_period` ends before the context period. §4.1.4: the figures of the strip are to-date figures at `context.measured_period` (04 API-C-10), the returns reduction inside Transaction price among them (supervisor ruling R-85 (a)); the Explain of Recognized and Billed lists the obligations' period nodes, each by the period its API-S-Obligation link carries, because the trace holds no contract-level node per period; the balance cell's reference carries the measured period. No route, permission or copy of another section changes |
| 1.11 | 2026-09-30 | lane WEB-QA (item W-10, ACT-STEP1-UI-1; supervisor rulings R-61 (f) and R-89 of 2026-09-30; number assigned by the supervisor, register index 42; row appended at the table's tail) | **Applied.** The Step 1 judgement is recorded in two steps. §4.1.3: row 1 gains the status lines of a record that waits for review, is reviewed or is rejected, and the new paragraph "Step 1 path" with its table says, per state of the latest Step 1 record and the latest assessments, the line shown and who acts next. §4.1.5 banner 6 and §4.1.6 rows `DRAFT` and `NOT_A_CONTRACT` take their command from that path; "Submit for activation" is the command of a `NOT_A_CONTRACT` contract once its criteria-met assessment is recorded, and "Record criteria met" records that assessment (it appended `CONTRACT_CRITERIA_MET`, which 04 §16.3 now refuses on the events route). §4.9.1: "Record Step 1 review" creates and submits the judgement record (topic `NOT_A_CONTRACT` for a not-probable outcome, with the two members that topic's questionnaire takes, 04 T-CON-19: "Consideration received is non-refundable", required, and the optional date of ASC 606-10-25-7(c)) and appends no event; the new drawer "Record assessment" / "Record criteria met" appends the assessment that cites the `REVIEWED` record, dated the inception date for a `DRAFT` contract and today (editable) behind the gate. §4.1.7 binds the assessments read. §15.4 region 4: the region "Criteria met" of the activation of a contract behind the gate (per book its date, its reviewed record and its catch-up). The `step1_gate` reason region of supervisor ruling R-82 (e) is not in this revision; it follows the API member. §0.5 SCR-URL-09 (item W-13, crawl finding F2; the supervisor's ruling of 2026-09-30 on it): on a screen with more than one grid a `sort` key is applied by the grids that list it and is unrecognised only when none does — on SF-16:developer the "Deliveries" grid dropped the key of "Webhook endpoints" beside it, so that grid could not be sorted |
| 1.13 | 2026-09-30 | lane F-ADM-WEB (BUILD_SPEC RPS-21; the supervisor's ruling of 2026-09-30 on the lane's read-in, point 7; docs first; number assigned by the supervisor in the lane package, register index 46; row appended at the table's tail) | **Applied.** §0.5 SCR-URL-32 gains the screen parameter `event`, the audit event uuid that accompanies `drawer=event` on SF-09:audit-log (SCREENS_B §6.3 rev 1.36), removed when the drawer closes; the SCR-URL-20 order places it after `node`. No route row, permission or state changes. **Amended in place for BUILD_SPEC DIN-18** (same number, register index 46): §14 is stated as bound to API-R-45 of 1.0 — §14.3 the sync runs keep the API's order and show the recorded totals as "<n> records · <amounts>", "Reconciled" and "Difference" are the run's status and never a comparison made on the screen (no value for a run that recorded no totals), the Exceptions count links to SF-11 by source, entities out of scope are counted, the columns of the external ids grid; §14.4 what "Edit connection" changes, the run kinds the API queues, the reason on a Disabled connection's "Run sync", "Enable" / "Disable" as a header button until DS-CMP-28 carries a disabled item (ruling R-83 (c)), the `pane` values and the step-up of "Save connection"; §14.5 the one Result cell, the no-totals and no-exceptions lines, SCR-ST-07 and the refresh of a running run; §14.6 and §14.9 the states and test hooks that follow; §14.4 and §14.7 the credential reference as 04 T-INT-01 rev 1.108 has it (ruling R-48 (f); the supervisor's instruction to the lane of 2026-09-30 after lane SECFIX-PLT merged): the workspace's namespace `tenant-<tenant id>-` as fixed text before the field, the field holding the rest of the reference, the API's refusal on the field, the copy key `.secretHelp` reworded and `.secretOutside` added; §14.3 and §14.4 the base URL of a mock connection as the adapter client takes it (an address whose path begins with `/api/v1/__mocks__/`; the chip "Mock" reads the path, the help says the form). No route row or permission changes |
| 1.19 | 2026-09-30 | lane WEB-QA (item W-13, crawl finding F4; the supervisor's ruling of 2026-09-30 on it; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §0.5 SCR-URL-13: a panel tab that changes `pane` removes `sort`, `q`, `f.*` and `view` in the same `history.replace`. Seven screens wrote `pane` and kept the list parameters of the pane they left; on SF-13:rule-set-version (Rules, then Test cases) and SF-14:sod (Rules, then Exceptions) the next pane's grid then dropped the other pane's `sort` key with the banner "Some filters in the link were not recognised and were removed." — a warning about a link nobody had followed. The rule of revision 1.11 (a key is unrecognised only when no grid on the screen lists it) cannot cover it, because the grid of the pane left is no longer mounted. No route, permission or copy changes |
| 1.18 | 2026-09-30 | lane WEB-QA (item W-22 part 1, APR-VIEW-1; supervisor ruling R-104 (a) and (b) of 2026-09-30; number assigned by the supervisor; row appended at the table's tail) | **Applied.** An approver reads what they approve — the part the API of main already carries. §15.3: the flag chips read a label for every routing flag the API sets; they showed `ABOVE_THRESHOLD` and `MANUAL_ENTRY` as sent. §15.4 region 1: the link "Open <subject label>" is defined (label by route, no link for a route the client does not hold); it was specified and never rendered. Region 4: "No impact on revenue or balances." is kept for a computed preview that moves nothing; a request without a stored preview says "No preview is stored for this request" and what the approver can do, instead of claiming no impact. Region 5: the caption of "Revenue by period" (the first six periods) and labels for the enumeration values of a preview. Region 7: the button "More below" on the sticky footer while content lies beneath it, and the pane's scroll padding. Regions 3 and 5 from the subject's content rows, "RPO at <date>" and "posted on approval, <period> to <period>" are part 2 and follow item APR-SUBJECT-CONTENT-1 |
| 1.12 | 2026-09-30 | lane F-CTR-WEB (BUILD_SPEC CTR-24; the supervisor's answers of 2026-09-30 to the lane's read-in and rulings R-89, R-93; number assigned by the supervisor in the lane package) | **Applied.** §4.6 column 7 "Prepared by" binds `preparer.display_name`, the member 04 API-S-Modification answers (it read `created_by.display_name`). §4.7 History tab (R-93 (b), (c)): the chip "Imports" is not rendered until the history route answers items of kind IMPORT (item CTR-HISTORY-IMPORT-1); the version comparison has no Delta column until the compare route answers the difference (item CTR-COMPARE-DELTA-1; DG-FE-08) and no switch "Show unchanged fields" (the route answers changed fields only); it lists the fields the screen has labels for, never a signed position (D-12), and says how many changes it did not list; test hooks `SF-03-pane-activity` and `SF-03-pane-audit`. §4.10 Draft contract form: (1) RT-19 SF-03:edit opens behind a fail-closed guard (R-93 (a)) until the API answers a draft as it stands (item CTR-DRAFT-READ-1): the form opens only while every event after the latest booking is a hold applied or released and the stream holds no Step 1 assessment; otherwise the screen shows the state "Changed after it was booked" or "Step 1 assessment recorded"; `replace-draft` takes the stream version the guard read as `If-Match`. (2) "Create customer <name>" shows the required field "Customer code" (`customer.code`). (3) "Save and submit for activation" is two commands — the save, then `POST /contracts/{id}/submit-activation` with the saved head — because 04 §16.1 refuses `submit_for_activation` in the booking; a refused activation opens SF-03 with a warning toast that says what comes first and, when the Step 1 review is among the failed items, with step 1 of the tracker open (R-89). (4) The lines grid is the line editor (`frontend/src/components/line-editor`; DESIGN_SYSTEM rev 1.7 DS-CMP-10 form-held variant). (5) The Contracting entity and Currency choices need `config.read`. (6) Test hooks `SF-03-new-page` and `SF-03-edit-page`. No route path, copy key of §4.1.9 or sample-world figure changes |
| 1.20 | 2026-09-30 | lane F-ADM-WEB (BUILD_SPEC WEB-16; supervisor rulings R-104 and R-112 (h) of 2026-09-30; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §0.5 SCR-URL-18 gains `bulk` on SF-12; §15.3 the FilterBar as API-R-09 binds it (one type, one status, entity codes; no search; the context pill's entity not applied; chips kept on a request; SCR-ST-04); §15.5 the bulk layout (loaded rows, at most 200 items, the impact line, the toast when every item is approved and the result dialog for refusals, the step-up before any item is decided); §15.7 the delegations screen (the Delegator column, the status read from the instants, whole days, who may open "New delegation" and who revokes, the copy of the drawer and the confirmation); §15.8 and §15.10 the copy keys and test hooks that follow. Ruling R-112 (h): §1.3 the SF-12 family uses no segment of the context pill — the entity segment is "Disabled" there, because the three lists filter by the chip `f.entity` (§15.3); §15.7 the Delegate choices are stated for the final read `GET /approval-delegations/delegates?q=` (lane API-GAPS G-2 (h)) and the reading of `GET /users` by a holder of `user.manage` is marked interim; §14.2 and §14.8 the totals of a sync run read "<n> records · <amount>" (T-INT-02 holds one count per side; was "1 order · 2 lines"). The supervisor's ruling of 2026-09-30 19:31 (item AUD-ACTOR-BIND-1): §0.5 SCR-URL-32 — the companion parameter `event` of `drawer=event` carries the audit event's chain sequence, not its uuid: no index of the audit table leads with `id`, while the sequence is unique in the workspace, immutable, the first column of the grid and what a verification cites (SCREENS_B §6.3 rev 1.45). No route row or permission changes |
| 1.21 | 2026-09-30 | lane WEB-QA (item W-17; supervisor ruling R-112 (h) of 2026-09-30 on the three screen decisions of revision 1.10; number assigned by the supervisor; row appended at the table's tail) | **Applied.** The screens of the to-date figures of revision 1.10, where that revision left the form open. §4.1.4: the heading of the KPI strip names the period the figures are measured at, always — "Key figures at <measured period label> (<currency>, <book label>)"; nothing on the workbench named it, and under the context of another entity the context bar shows that entity's period state. Billed, Recognized and Scheduled open the Explain panel at a list level, defined in §6.3: the measure and the measured period, the value of the cell, the table "By obligation" with a button per obligation that pushes its explanation onto the Back stack, and the sentences that say why the value is not the sum of the rows; no total row, no "Verify", no trace link and no link to copy at that level (SCR-URL-11). §4.1.2: the marker of "Figures as of" reads "Measured at <period label>, the last period this contract was computed for."; "Recalculation queued" stays with a job that exists. §4.1.8: a header read the API refuses by name under 04 API-C-10 is a state of its own with the API's messages, not the load error. §6.3 measure labels gain `revenue_cum` and `billed_cum`; §6.4 the three states of the list level; test hooks in §4.1.11 and §6.7. Banners 1 and 4 of §4.1.5 are unchanged: they bind when API-S-Contract carries `computation`. No route or permission changes |
| 1.22 | 2026-09-30 | lane F-ADM-WEB (BUILD_SPEC RPS-18; the supervisor's ruling of 2026-09-30 on the lane's read-in, point 1; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §0.4 — RT-33 SF-08:run and RT-106 SF-08:runs open for a holder of `report.run` or `audit.read`, the two permissions the report routes admit (04 API-R-41 rev 1.128, ruling R-63 (a)); the API lists and opens the runs that member may see and the screens filter nothing (SCREENS_B §5.3 rev 1.53). No other route row or permission changes |
| 1.24 | 2026-10-01 | lane WEB-QA (item EXPLAIN-BALANCE-LINKS-1, the screens' half; supervisor ruling R-115 (g) of 2026-09-30; `docs/04-DATA_MODEL.md` rev 1.174; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** A balance figure is explained through the address its entry names. §4.1.4: the three figures of cell 6 take their Explain reference from `balances[e].links` (`explain_contract_liability`, `explain_contract_asset`, `explain_unbilled_receivable`), which name the balance row and the period it was read at; a figure whose link is null — a cut before the first period the version measures — prints without a trigger. §4.4: a cell of "Balances by entity" is an Explain trigger where the row's `links` name its explanation and prints its amount without one elsewhere; "Every cell is an Explain trigger" described a reference no response carried, the id of the balance row. No route or permission changes |
| 1.23 | 2026-09-30 | lane F-CTR-WEB (BUILD_SPEC CTR-27; the supervisor's answers of 2026-09-30 15:00 and 21:45 to the lane and ruling R-114 (h); docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §7 is stated as bound to 04 API-R-31 of 1.0. §7.3: no modification command takes `If-Match` (D-98 140-A4; two preparers on one draft are last-write-wins, item MOD-DRAFT-LWW-1), so no 412 arises on this screen; a subscription action is an ordinary modification of the matching kind whose one line has the ENGINE_SPEC S06-R-19 shape (the route `subscription-changes` is CTR-18's and not on main); a save is `PATCH`, then `/classify`; a draft opened without `step` opens at step 1 and sends no command; "Discard draft" is not rendered until a route voids a draft (item MOD-DISCARD-1). §7.4: every subscription action names an obligation, co-term and the renewals take a "New obligation key", the end date is typed for a renewal and read-only otherwise; a draft that holds a price change amount keeps its kind; the linked panel shows judgement records only, on step 1 of an existing draft (no member links an estimate version to a modification, item MOD-LINKED-ESTIMATES-1); the repeated-reference message is the API's. §7.5: an answer counts once it is stored (confirming a group or changing an answer); a group asks the questions that apply to its obligation; the save of step 1 or 2 sends `chosen_treatments` reduced to the departures the preparer made, because `/classify` keeps a stored choice and the default of an earlier classification would otherwise stand as a departure. §7.6: "Next" is open once the override record is linked and `/submit` once it is reviewed; the range beside the SSP version is the price test's of this visit, written "<low> to <high>". §7.7: no "Change" column, no totals rule and no Explain trigger (the API answers neither figure and a dry run keeps no trace; ruling R-93 (c)); entering step 4 runs the preview of a row that holds none. §7.8: `/submit` refusals are shown as they come; "Withdraw request" takes a required comment and renders for the preparer of the request. §7.9: the header, the stored preview as the snapshot, the read-only detail of a draft for a reader without `modification.create`; the quarantined-computation banner is not bound yet. §7.10: the unreachable-server line and where the voided-request banner shows. §7.13: further test hooks. The sticky footers of §7.3 and §4.10 carry the cue "More below" of DESIGN_SYSTEM rev 1.9. §4.1.6: "New modification" and "Change subscription" render on an `ACTIVE` contract only. §0.12: the SF-07 capture is a co-term draft that stays under a reference of its own. No route path changes; copy key `.discard` of §7.11 is not in the catalogue until MOD-DISCARD-1 |
| 1.26 | 2026-10-01 | lane SECFIX-ACT (supervisor ruling R-118 (e) of 2026-10-01 on the lane's pre-build line, item MOD-DISCARD-1; number assigned by the supervisor, register index 97; row appended at the table's tail) | **Applied.** §7.3 page header: "Discard draft" is offered on a DRAFT without a pending request to every holder of `modification.create`, and the confirmation reads "Discard this draft modification?" — **replaced:** "(DRAFT, preparer; confirmation \"Discard this draft modification? Nothing was submitted.\")": a draft that was submitted and withdrawn is discarded too. The command is `POST /modifications/{id}/discard` (04 rev 1.188); its 409 names the judgement record whose review is pending (PRD ERR-82, rev 1.117). |
| 1.30 | 2026-10-01 | lane WEB-QA (item W-12, slice a; the supervisor's ruling of 2026-10-01 on the item's pre-build line; `docs/04-DATA_MODEL.md` rev 1.148 API-S-Me `permission_scopes`, T-PLT-10; docs first; number assigned by the supervisor, register index 101; row appended at the table's tail) | **Applied.** A permission is held for entities. §0.6 SCR-PERM-01 and SCR-PERM-02 said "for the context entity" and "in the record's entity scope", and every gate of the client asked only whether the code was among `permissions`: a member whose role is for named entities was offered commands the API refuses. SCR-PERM-01 states when a permission is held for an entity and what a route of tenant-wide objects asks. SCR-PERM-02 states the four questions a control asks — for the record's entity, for any entity, for all entities, for every entity of a grant — that a command held for another entity is not rendered, what a member of named entities is offered before the entities are read, and that the approval decision form follows the server's `can_decide` and asks none of the four. No route, parameter or copy changes |
| 1.31 | 2026-10-01 | lane F-ADM-WEB (item TPL-EFFECTIVE-FROM-UI-1; the supervisor's message of 2026-10-01 03:30; lane ENG-FX's CFG-BACKDATE-1 on main as b800a501, PRD rev 1.89 ERR-75, 04 §16.5 rev 1.160; docs first; number assigned by the supervisor, register index 105; row appended at the table's tail) | **Applied.** Finding: since CFG-BACKDATE-1 a version that replaces a published one needs an effective date the server accepts, and the obligation template editor had no such field, so on screen such a version could not be submitted at all; the editors printed a refused command as its detail or its title and bound no message to the date field. §11.2 gains the Meta of §11.1 with "Effective from", required for a version that replaces a published version of its template and optional for the first. §11.0: the row "Effective date" states the two forms of 04 §16.5 — a kind chosen by a contract date keeps its date, and a rule set read at an instant goes without a date, or with today's, as no instant (it takes effect at its publication), which the stepper and the Meta read as "Effective on approval" and, once published, as the date of the publication; an accounting policy version keeps sending 12:00:00Z because its submission refuses a version without a date — and the new row "Refused command": a message on `effective_from` shows at the field with focus and leaves when the date is edited, and the banner lists what no field shows. §11.1 Meta and §11.3 follow. §15.4: an approval refused with ERR-75 tells the approver what she can do, since she has no date to change; §15.5 the same in the bulk result. §10.4: the product code stays editable with the server's refusal at the field until API-S-Product says that the code is fixed. §0.12: the draft capture of SF-13:template-version. Copy: the help line of "Effective from" is stated per form (the line "Required before submission. The version takes effect at 12:00 UTC on this date." is withdrawn); the help line of the product code names the three holders of 04 DB-05. No route, permission or test hook changes |
| 1.15 | 2026-09-30 | lane SECFIX-IMP (the supervisor's rulings R-49 (a) and R-86 of 2026-09-30; 04 rev 1.142; number assigned by the supervisor; row appended at the table's tail) | **The labels are built; the view is named, not built.** 04 E-08 gains the approval subject `EVIDENCE_SHRED` — the request to shred a file that a record holds as its evidence, decided by a Controller. The API serves its requests through API-R-09 now. §15.3 names its subject type label and §15.4 its diff body. Built with this revision (the supervisor's orders of 2026-10-01), because the API hands every list of requests a subject type and a type without a label is shown as its copy key: the label with its key `approvals.subjectType.EVIDENCE_SHRED` and the Type filter entry; and the label of `MIGRATION_SSP_REPLAY`, "Migration SSP replay", with its key and filter entry — an E-08 member since 04 rev 1.72 that §15.3 had not named. One test holds both tables to E-08 as the API document states it. The screen item *EVIDENCE_SHRED request view* — the proposal view — is built by a frontend lane; until then the request view shows the proposal through its generic field diff. Its companion item, the request-shred affordance, is named in SCREENS_B rev 1.41 (§9.6). No layout, route or test hook changes |
| 1.34 | 2026-10-01 | lane WEB-QA (item W-12, slice b; supervisor ruling R-28; the supervisor's ruling of 2026-10-01 on the slice's pre-build line, choices A, B and C; `docs/04-DATA_MODEL.md` API-R-10, API-R-11; docs first; number assigned by the supervisor, register index 120; row appended at the table's tail) | **Applied.** The lists of the whole workspace. Rev 1.30 gave a control four questions and left every reader of the audit events asking whether `audit.read` was among `permissions`; a journal run's "History" asked nothing and showed a member without the permission an error whose "Retry" could not work (a PRODUCT DEFECT against SCREENS_B §3.2). §0.6 SCR-PERM-02 names the audit events as a list of question (c) — `audit.read` for all entities, ruling R-28 — says that a region following a job asks nothing, and that a read of either list the API refuses with 403 renders what the region renders without the permission, not SCR-ST-05, and is not sent again. SCR-PERM-01: the audit log's route asks for all entities, which restates the rev 1.30 sentence that counted it among the routes of any entity. §0.7 SCR-ST-06 gains the page whose own list is refused. §2.1, §2.3 and §2.7: Home's figures and exceptions queue ask for the context entity, its approvals queue for any entity, "Recent activity" for all entities, with the "Recently viewed" variant otherwise and on a 403. §4.7: the "Audit trail" option needs `audit.read` for all entities, and a refused read removes it. No route, parameter or copy changes in this file; the one new sentence of copy is SCREENS_B §6.3 rev 1.68 |
| 1.35 | 2026-10-01 | lane F-ADM-WEB (two items of the supervisor's message of 2026-10-01 08:07; docs first; number assigned by the supervisor, register index 129; row appended at the table's tail) | **Applied.** (1) §10.4, the product drawer. Finding (the lane's own, reported with revision 1.31): the drawer showed nothing for a refused "Save product" whose errors named Bundle, an attribute row or any member without a text field — its banner was dropped as soon as the problem carried a field error, and only the text fields and the template select held a message. A refusal now shows at the control whose member it names, Bundle and the attribute row included, and leaves when that value is edited; what names no control is listed in the banner under the problem's title, each sentence once; the warning of a missing required attribute stays below it. The rule is that of §11.0 "Refused command" and SCREENS_B §9.15, applied to this drawer. (2) §14.4, "Test connection" in a sandbox. Since 05 SBX-08 rev 1.116 (item SBX-PROBE-1, lane F-SNP, on main as 58b6a171) the API refuses the test of every adapter but `CSV_GL` in a sandbox, 403 `sandbox-restricted`; the screen still offered the command and answered its press with the toast "Not available in a sandbox". The control now renders `aria-disabled` with its reason, as "Enable" does (SB-R-08, which SCREENS_B rev 1.74 extends to the test); §14.7 gains the copy key. No route, permission or test hook changes; one copy key is added |
| 1.32 | 2026-10-01 | lane SECFIX-APR (item APR-CONTENT-SCOPE-1; the supervisor's ruling of 2026-10-01 on finding 10 of the lane's report — a release blocker — and its rulings of the same day on the lane's pre-build line; `docs/04-DATA_MODEL.md` rev 1.208 API-S-Approval `content_withheld`; docs first; number assigned by the supervisor, register index 117; row appended at the table's tail) | **Applied.** §15.4 gains "Content withheld": what the request pane shows a reader who covers some of a request's entities and not every one — region 1 with the summary the API sends, one info banner in place of regions 3 to 6 with its title, message and `data-testid`, no decision form — and how the lists show such a row. The screen's code follows the API (a web lane's item). No route, region or key of another screen changes. |
| 1.27 | 2026-10-01 | lane SECFIX-PLT (independent review of the platform security merge a7d63e81, findings 2 and 6; supervisor rulings R-111 (2) and (4); docs first; number assigned by the supervisor, register index 98; row appended at the table's tail) | **Applied (text of §15.7; the screen binds it with the next change of SF-12:delegations).** §15.7 gains "The limits of a delegation": "Valid to" is bounded by today, not by "Valid from" (the API ends a delegation within 90 days of its command); the Delegate field shows the API's refusal of a member without a confirmed second factor, and the Permissions field the ERR-22 line of a separation-of-duties conflict; an access administrator sees every delegation of the workspace and ends any with "End delegation", its confirmation, reason, step-up and toast; a delegation that ended with its delegator's access reads "Revoked". PRD rev 1.118 (BR-PLT-07) and 04 rev 1.189 (T-PLT-21, API-R-09) carry the rule. No route row or permission changes |
| 1.37 | 2026-10-01 | lane F-CLO-B (item CLO-QUARANTINE-READ-1; supervisor ruling R-121 (i), the supervisor's message of 2026-10-01 08:42; 04 rev 1.206; number assigned by the supervisor, register index 115; row appended at the table's tail) | **Applied.** The data bindings and the one label as the API serves them; the screens are bound by lane F-CLO-WEB. §2.6 — the close row of `exceptions_open` reads "Exceptions holding the lock" and links to SF-11 with `blocking=<close.id>`; a paragraph says what the key figure and the row each count and that both take an item as the entity's by one rule. §2.5 — the key figure "Open exceptions" keeps its label and its link and equals the list behind it. §13.3 and §13.4 — the queue's Entity filter lists the items that are the entity's, and the master read passes `blocking` through. One copy key changes its text (`home.close.blocker.exceptions_open`); no route, permission or test hook changes |
| 1.29 | 2026-10-01 | lane F-CTR-WEB (BUILD_SPEC CTR-25; the supervisor's answers of 2026-10-01 to the lane's report on CTR-27 and to its pre-build line, register index 99; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §8 is stated as bound to 04 API-R-32 of 1.0. §8.3: the element list answers no figure, so a master row and the figures strip show the element's latest version, which they name, read from the versions of each element; "Current version" is the approved version, with the catch-up of the preview it was submitted with (kept with its approval request) and its evidence; the figures carry no Explain trigger (04 §16.11 has no estimate object); "New estimate version" and "Attest no change" wait while a version is a draft or pending; a rejected or withdrawn version has its own banner with "View request", a request the API voided as stale is named in the words of §15.4, and a banner that depends on a read is rendered whole once the read has answered; "Discard draft" is not rendered until item EST-DISCARD-1; "Reassessment due" is bound and no item is raised yet (ENG-S10-GATE-FACTS-1). §8.4: the method and the element type are shown, never edited; the fields follow the 04 T-CON-13 rows, the kind SHARE_BASED_CONSIDERATION included; a new version starts from the figures of the approved one; the constraint checklist has five keys named after ASC 606-10-32-12 (a) to (e); the constraint judgement is one inline field and its record names the contract; the classification of an estimate of total costs is asked and not stored (EST-CLASSIFICATION-RECORD-1); the preview shows before and after and neither one "change" figure nor a loss test (EST-PREVIEW-LOSS-TEST-1; ruling R-93 (c)); the element drawer also takes the element's obligation. §8.5: the static table at every size, the comparison of the two rows without a difference in money, one figure column for a variable consideration. §8.8: `N` works and is listed nowhere, the shortcuts dialog not being built. §8.10: the further test hooks. §4.6: the tab's toolbar carries neither "New modification" nor "Change subscription" — the header of an ACTIVE contract is the one place of both (ruling of 2026-10-01 on CTR-27's J29); the empty state keeps its action. §4.1.3: the allocation line of the tracker is not shown without the SSP book version and then with it; the step is busy until the label is read. §5.8: "Change price" is rendered. §0.12: what the four estimates captures show, the demo seed holding no estimate. §0.8: E-12 `VOIDED` reads "Void" ahead of item EST-DISCARD-1 (ruling R-119 (e)) |
| 1.33 | 2026-10-01 | lane SECFIX-ACT (supervisor rulings R-118 (e) and R-119 (e) of 2026-10-01, items EST-DISCARD-1 and MOD-LINKED-ESTIMATES-1; number assigned by the supervisor, register index 119; row appended at the table's tail) | **Applied.** §0.8: E-12 `VOIDED` shows the chip Void — the status of a discarded estimate version and of nothing else (04 rev 1.210). §8.4 banner: "Discard draft" has a command, `POST /estimate-versions/{id}/discard`, with the confirmation "Discard this draft version?" — the screen offered it and no route served it. §7.4: the linked estimate versions table reads `linked_estimate_versions` of the modification; a version is linked by `modification_id` at its creation; the versions are approved before the modification is submitted (PRD ERR-87), and the discard names a version that is waiting for approval (PRD ERR-83). |
| 1.39 | 2026-10-01 | lane F-CTR-WEB (item HIST-CALC-CHIP-1; the supervisor's message of 2026-10-01 10:33 on `docs/04-DATA_MODEL.md` rev 1.143 API-S-ContractHistoryItem; docs first; number assigned by the supervisor, register index 136; row appended at the table's tail) | **Applied.** §4.7 Activity: every computation is SYSTEM's since 04 rev 1.143, so the chip "Calculations", which read `kind=CALCULATION` alone, listed nothing until "Show system events" was on. The chip reads with `include_system=true` whatever the switch says; the switch keeps the member's choice for the other chips. An event of the audit trail whose `on_behalf_of` names the principal it was written for reads "<actor> on behalf of <name>"; API-S-ContractHistoryItem names no such principal, so an Activity item reads "System" |
| 1.43 | 2026-10-01 | lane F-ADM-WEB (item SBX-ADD-CONNECTION-1; the supervisor's message of 2026-10-01 09:41; docs first; number assigned by the supervisor, register index 153; row appended at the table's tail) | **Applied.** §14.4, "Add connection" in a sandbox. Finding (the lane's own, reported with revision 1.35): in a sandbox workspace the drawer offered all five adapters and all three directions, while `POST /integrations` refuses an inbound connection there with 403 `sandbox-restricted` — a Salesforce or Stripe connection, or the direction "Inbound" or "Both" (05 SBX-08). The drawer now offers what the API accepts in a sandbox: the adapters NetSuite, QuickBooks Online and CSV GL export and the direction "Outbound", which is NetSuite's default there; the Adapter's help says why the others are not offered, and §14.7 gains its copy key. A production workspace is unchanged; so is "Edit connection", which changes neither member. No route, permission or test hook changes; one copy key is added |
| 1.44 | 2026-10-01 | lane F-ADM-WEB (the product drawer's Code; the supervisor's message of 2026-10-01 on lane API-GAPS' item, on main as 4464a69c: 04 rev 1.223, API-R-23 `code_frozen`; docs first; number assigned by the supervisor, register index 154; row appended at the table's tail) | **Applied.** §10.4, the Code of "Edit product". Revision 1.31 left the field editable for every product, because API-S-Product named no holder of the code, and showed the server's refusal at the field. The read model now carries `code_frozen`, the predicate of 04 DB-05 — a contract line, an SSP entry or an account mapping rule references the product — so the field is read-only while it is true and editable while it is false; the help line is the same in both states, and a refusal of the server, for a code that froze after the product was read, still shows at the field. No route, permission, copy key or test hook changes |
| 1.40 | 2026-10-01 | lane WEB-QA (item KIT-FILTER-LEAVING-1; the supervisor's ruling of 2026-10-01; `docs/dev-guide.md` rev 1.215 DG-FE-03; docs first; number assigned by the supervisor, register index 144; row appended at the table's tail) | **Applied.** §0.5 gains SCR-URL-33, the rule on the writes of a page that is leaving, beside SCR-URL-20 to SCR-URL-23 (the id assigned by the supervisor; SCR-URL-24 to SCR-URL-32 are parameter rows). Finding (a PRODUCT DEFECT of the kit, met on SF-12): a control writes its parameters without naming a path, and the address it lands on is the one the router holds at that moment; a chip of All requests removed while the request page was being rendered rewrote the request's address, which lost `view=all` and the chip. The rule: a control of a page that is leaving writes nothing. Its limit is stated with it: a page is known by its route, so the page of one record giving way to another record's under the same route is not covered. A second finding of the FilterBar is closed with it: two chips removed faster than the screen redrew put the first chip back; the bar now works out each write from the address as it stands. No route, parameter or copy changes |
| 1.41 | 2026-10-01 | lane FIX-D2 (the waterfall's entity — PRODUCT DEFECT; supervisor rulings R-78 (d) and R-121 (g), and the supervisor's ruling of 2026-10-01 on the lane's finding on the Home; docs first; number assigned by the supervisor with that ruling; row appended at the table's tail; SCREENS_B rev 1.69) | **Applied.** §2.5: `revenue` and `revenue_chart` read the RPT-01 population of the context entities — the obligations they perform, with the revenue their books hold; revenue, contract liability and RPO are read as the reports' jobs read them, so the figures of a context do not depend on who asks (a reader of the contracting entity alone was refused the Home by rule S15-R-01 for a contract another entity performs); the consequence is stated: an entity that performs an obligation in another currency than its functional currency is refused by the rule of every context that holds another currency, where its Home stated 0.00 for that revenue. No region, binding, copy or state changes. |
| 1.42 | 2026-10-01 | lane F-CTR-WEB (the modification item over MOD-DISCARD-1, MOD-PATCH-CLEAR-1, MOD-ANSWER-PREVIEW-1 and DEMO-SSP-BASIS-1; the supervisor's ruling of 2026-10-01 on the lane's pre-build line and its correction, register index 152; `docs/04-DATA_MODEL.md` rev 1.188, `docs/02-PRD.md` rev 1.117 and rev 1.158 J-06; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §7.3 "As bound": "Discard draft" (rev 1.26) is bound — for a holder of `modification.create` for the contract's entity, with the consequence in its confirmation, the toast and the Modifications tab after it, and the API's messages of a 409 (PRD ERR-82) in the confirmation — **replaced:** "is not rendered until a route voids a `DRAFT`". §7.4 "As bound": the kind of a draft that holds a price change amount is a choice, and an emptied scope description is cleared, because `PATCH` clears a nullable member sent as null — **replaced:** "stays "Price change", because `PATCH` leaves a member that is sent as null". §7.6 "As bound": a save whose choices are all the proposal again takes the override record off the row. §7.8: one submission routes one request (PRD rev 1.158 J-06.5), and the toast names it, "Submitted for approval. Request <request no> is waiting for approval." — **replaced:** "<n> requests are waiting for approval." and "J-06.4 routes four requests"; "As bound": the answers of `/submit` and `/withdraw` are the row with its stored preview — **replaced:** "the screen reads the row again after either command". §7.10: the banner of a voided request is a warning (the supervisor's ruling on CTR-25's J10); a request its preparer withdrew reads `WITHDRAWN` and shows no banner. §7.11: the three copy keys of the discard. §0.12: the row SF-07:detail discards the draft the SF-07 capture creates — **replaced:** "and leaves it, because no route voids a draft yet". Joined under the same revision by the supervisor's word of 2026-10-01 15:24 (a red row of main, "SF-07:detail maya": the wizard dropped a stored answer that the classification named in `prefill_reasons`, and the next save left it out): §7.5 "As bound" — the stored answers are those of the row the classification was asked for; an answer the row holds stays confirmed and is sent by every save, whatever a classification or a read names as a proposal. §7.12, row J-06 — "Submit routes one request `MODIFICATION` with two steps; the two estimate versions are submitted and approved before it, each on a request `ESTIMATE_VERSION` with two steps" (PRD rev 1.158 J-06.5; rev 1.164 J-06.3, J-06.4) — **replaced:** "Submit routes four requests; the modification request has two steps" |
| 1.36 | 2026-10-01 | lane F-SNP (item REG-VERSION-WHOLE-SET-1; the supervisor's ruling of 2026-10-01 on the item's pre-build line, point D; `docs/04-DATA_MODEL.md` rev 1.183; docs first; number assigned by the supervisor, register index 92; row appended at the table's tail) | **Applied.** §11.3. A registry version holds the whole value set of its category (04 T-PLT-32 rev 1.183): the server keeps every published value a version does not state. (1) "New policy version": unticked, "Start from the current published values" sent an empty draft, which under the new rule would have kept every published value — the reverse of what the box says. The drawer now sends `basis: "DEFAULTS"` when it is unticked; ticked, it sends the published values as before and no basis. (2) The Proposed value column printed the published value for every key the version does not hold, also for a key the version returns to the default, beside the "Changed" chip. It prints the framework default for such a key, named by the caption the Current value column uses, and the published value for a key the version keeps; beside a level a long value truncates under its tooltip, so the level is never clipped. (3) After the independent review of the change: an emptied value returns the key to the default — the editor names it in `unset` where the published version holds it, since leaving it out alone would keep the published value; and a version of a settings category that the list opens here (Close, Integrations) is submitted without a date, with one help line of its own ("Without a date the version takes effect when it is approved. Choose a date to start later."). (4) After the supervisor's rulings of 2026-10-01 on the item's report (04 §16.5: `diff_against_current` of a `PUBLISHED` or `SUPERSEDED` version is the difference it made to the version it superseded): the grid read every version as a statement, so the page of a superseded version printed the value the published version holds NOW for a key the old version never held. A version past `TESTED` holds the whole set: a key it does not hold reads the framework default, and its "Changed" rows are the codes of its difference. No route or parameter changes; one message is reused and one is new |
| 1.47 | 2026-10-01 | lane WEB-QA (item KIT-UNPLACED-ERRORS-1, head 1; the supervisor's rulings of 2026-10-01 on the item's pre-build line and on its cut into two heads; docs first; number assigned by the supervisor, register index 169; row appended at the table's tail) | **Applied.** §0.7 gains the state SCR-ST-13 "Refused command". The rule that §10.4, §11.0 and SCREENS_B §9.15 state for their screens — a message at the field whose member it names, the rest in one banner, each sentence once — is stated once for every form, with the case those sections did not name: a message on a member the form has no field for is the banner's. Fifteen forms showed such a refusal nowhere (of SF-15 the drawers "New account", "New customer", "New group", "New dimension" and "Dimension values" and the entity drawer; of SF-13 "New rule set", "New SSP book" and "New draft version", "Save version details" of SF-13:ssp-book-version, "Create draft version" and "Exclude" of SF-13:ssp-calculator-run and "Add test case" of SF-13:rule-set-version; "New mapping profile" of SF-10:templates; the form of SF-22:accept-invitation, which keeps SCREENS_B §12.3 for a refusal its password field shows whole), and SF-15:workspace said one sentence of a refused step. Those follow the state from this head; the forms that show the banner of the contract drawers follow in the item's second head (register index 176). No route, permission, parameter or test hook changes; one copy key is added (`common.refusal.reference`, the wording of CPY-05) |
| 1.49 | 2026-10-01 | lane WEB-QA (item KIT-FILTER-LEAVING-2; the supervisor's ruling of 2026-10-01 on the item's two measured lines; docs first; number assigned by the supervisor, register index 171; row appended at the table's tail) | **Applied.** §0.5 SCR-URL-33: a page is leaving from the moment the member starts for another page. Rev 1.40 let a control of the page being left write until the address had moved; while the next page was still on its way such a write landed on the old page and cancelled the member's navigation (measured: a chip of the contracts list pressed while the reports page was being fetched left the member on the contracts list, and the report view's own answer did the same), and three writes that name their own page — the Explain panel's, Home's context and the modification detail's after "Edit" — called the member back to the page they had left or kept them on it. The limit sentence is restated: what remains is a press on a control of the earlier record between the move of the address and the drawing of the later record's page; the answer of a command is written only for the page that sent it (`docs/dev-guide.md` DG-FE-03 rule (3), revs 1.229 and 1.230). No route, parameter, permission, copy or test hook changes |
| 1.48 | 2026-10-01 | lane WEB-QA (item W-12d, the screen of APR-CONTENT-SCOPE-1; the supervisor's rulings of 2026-10-01 16:18 on the item's pre-build line, question 1, and of 18:05 on the comment of a rejection; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §15.4 "Content withheld" is restated in three places. (1) Region 2: the preparer's and the earlier approver's notices stay for a withheld request, and "You do not have approval rights for this request type." is not rendered for one — the reader may hold the right and lack an entity, and the banner says why nothing is decided here. (2) Rev 1.32 said the routing steps are shown without comments. The pane renders a decision's comment whenever the API sends one and holds no rule of its own about who reads which: with a withheld request the API sends at most the comment of a rejection, to the request's preparer. (3) The banner's message says so in a third sentence. The entities line of region 1 is rendered as the API sends it. No route, permission, parameter or test hook changes beyond the `data-testid` rev 1.32 named; two copy keys are added (`approvals.withheld.title`, `approvals.withheld.message`) |
| 1.52 | 2026-10-01 | lane F-CTR-WEB (item MOD-PRICE-TEST-FACT-1 on the screens — a red row of main, "SF-07:detail maya", since `prefill_reasons` names a stored answer no more (04 rev 1.235); the supervisor's order of 2026-10-01 20:26: taken out of patch item (b) and delivered ahead of it, register index 178; `docs/04-DATA_MODEL.md` rev 1.250 API-S-Modification `price_tests`; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §7.6 "As bound": the range beside the SSP version is the one of the engine's price test of the added line as the row states it (`price_tests`), or its point, whatever the preparer answered and in every visit — **replaced:** "The range beside the SSP version is the one of the price test this visit read" and "the API answers it only while the price question has no stored answer, so a draft reopened after its answers were confirmed shows the version alone". §7.5 "As bound": the sentence of the price test stays under the price question beside a stored answer, as a fact and without "Prefilled" — the sentence of the comparison beside an answer of No, and beside an answer of Yes "Attested by the preparer as priced at the standalone selling price. Price <price>; SSP <low> to <high> (<version>).", with its point form and its form without an SSP entry; the screen compares nothing and concludes nothing from the two figures — **replaced:** "a stored answer shows neither". §7.11: the three copy keys of the attested sentence |
| 1.50 | 2026-10-01 | lane F-CLO-WEB (the screens of lane F-CLO-B's item CLO-QUARANTINE-READ-1, register index 157; the supervisor's rulings of 2026-10-01 14:53 and 16:23 on the lane's pre-build line; SCREENS_B rev 1.81; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §13, the exception queue under `blocking` (bound in rev 1.37): while the address holds the parameter the queue says that its list is cut down. §13.3 and §13.9 — the info banner "Showing the exceptions that hold the lock of one period." with "Show all exceptions", which drops the parameter and nothing else, and its test hook. §13.4 — the parameter stays through filtering, sorting and opening an item, and the header's "<n> open" is read without it. §13.6 — an empty list under it reads "No exceptions match these filters" and offers "Show all exceptions" where no chip cuts it down as well. §2.6 is built as rev 1.37 bound it: the close row "Exceptions holding the lock" is a link to the queue under `blocking` with `close.id`. Two copy keys and one test hook added; no route or permission changes |
| 1.38 | 2026-10-01 | lane WEB-QA (item W-12, slice c, head c3; the supervisor's ruling of 2026-10-01 on the slice's four special cases, case 4, and its word of 2026-10-01 16:18 that the documents do not wait for the contracts head; docs first; number assigned by the supervisor, register index 131; row appended at the table's tail) | **Applied.** §0.6 SCR-PERM-02 gains case 4. Rev 1.30 named an import among the records of one legal entity; an upload is not one — its rows name their entities — so `import.upload` asks any entity, at the entry, on the routes and for the uploader's commands. An exception is asked for its own entity where it has one and for any entity when it has none. The other three cases of the ruling (the contracts list's bulk commands, the new-contract form, the Step 1 request link) belong to the contracts head and take a number of their own. No route, parameter or copy changes |
| 1.55 | 2026-10-01 | lane F-ADM-WEB (small item 4 of the supervisor's message of 2026-10-01 15:23, ruled at 19:11 on the lane's pre-build line; PRD rev 1.158 and 1.164 by lane SECFIX-ACT and BR-MOD-02 rev 1.139; documents only; number assigned by the supervisor, register index 200; row appended at the table's tail) | **Applied.** §15, a change order's requests. PRD J-06 follows the built order since rev 1.158: the estimate versions linked to a modification are approved before the modification is submitted, each as a request of its own — of two steps where its P&L impact is USD 50,000.00 or more (rev 1.164) — and the grouping of linked requests in the inbox is not built (BR-MOD-02 rev 1.139). Three sentences of §15 still told the earlier design, one bulk approval of four linked requests. §15.4, the diff table's `MODIFICATION` row: the pane lists no linked requests waiting, and the list with its button "Open linked requests" is named and not built. §15.5: the example of J-06.5 is withdrawn. §15.9: the row of J-06 tells its requests in the journey's order — EAC version 2, the judgement record's review, bonus version 2, the modification — with the refusal of J-06-ALT-1 on the modification's second step. §15.3 said nothing of a change order. No route, permission, copy key, test hook or test changes; no screen changes |
| 1.51 | 2026-10-01 | lane F-CTR-WEB (patch item (a): items MOD-LINKED-ESTIMATES-1 and EST-DISCARD-1 on the screens; the supervisor's ruling of 2026-10-01 on the lane's pre-build line, register index 177; `docs/04-DATA_MODEL.md` rev 1.210, `docs/02-PRD.md` rev 1.139, rev 1.158 and rev 1.164; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §7.4 "As bound": "Linked estimate versions" is bound — the table of the row's `linked_estimate_versions` with the key figure of each version, the Element cell linking to SF-03:estimate and no command on a row; "Add estimate version" for a holder of `estimate.create` for the contract's entity opens the version drawer of one element (a menu of the elements where the contract has several; unavailable with its reason for an element with an open version and on a contract without an element) and sends `modification_id` — **replaced:** ""Linked estimate versions" is not rendered, because no member of the API links an estimate version to a modification". §7.8 "As bound": the summary lists the linked estimate versions; "Submit for approval" is unavailable with the sentence of PRD ERR-87 while a linked version that is not discarded is not approved, the API's refusal staying the backstop; "Linked requests" lists the linked estimate versions with the request of each, above the judgement records — **replaced:** "The summary lists Kind, Reference, Effective date, Treatments, Linked judgement records and Flags" and ""Linked requests" lists the linked judgement records". §8.3 "As bound": "Discard draft" (rev 1.33) is bound — for every holder of `estimate.create` for the contract's legal entity, with the consequence in its confirmation and the toast after it; the discarded version reads Void and is no longer the latest one, so the master row, the figures strip and "New estimate version" follow the highest version number that is not Void (04 rev 1.210), where the screen had taken the highest number — **replaced:** ""Discard draft" is not rendered — no route discards a draft version". §7.12, row J-06, restated from PRD rev 1.158 and rev 1.164: one question answered No; the two estimate versions approved before the modification, each on a request of two steps, with their catch-ups (87,804.88) and 102,439.03; the modification's preview 1,200,000.00 → 1,350,000.00, Sep 2026 14,634.15 → 91,463.41, journal 76,829.26 — **replaced:** "Answers No / No", "transaction price 1,000,000.00 → 1,350,000.00", "revenue Sep 2026 0.00 → 91,463.41" and the journal of 91,463.41; **removed:** "progress 60.0% → 51.2%", for which PRD J-06.5 states no figure. Beyond the supervisor's list, for the same change: §7.1 and §8.1, the Journeys cells name the steps PRD rev 1.158 gives each screen (SF-07: J-06.1, J-06.2, J-06.5; SF-03:estimates: J-06.3, J-06.4); §7.11 and §8.8, the copy keys of the linked versions and of the discard; §0.12, two captures — `sf-07-change`, step `change` of the K-02 draft with the panel "Linked estimate versions", and `sf-03-estimate-discard`, the confirmation of "Discard draft"; §7.4, the reason of the unavailable command as a visible line (§0.6 SCR-PERM-03), what the panel shows when the elements or an element's versions cannot be read, and the row read again after a command on a linked version wherever it is sent |
| 1.52 | 2026-10-01 | lane F-CTR-WEB (second row of rev 1.52 — the rest of patch item (b): items MOD-PREVIEW-JOURNAL-RULE-1 and MOD-PREFILL-READ-1 on the screens, and what item MOD-PRICE-TEST-FACT-1 left for it; the supervisor's ruling of 2026-10-01 on the lane's pre-build line and its order of 20:26, register index 178; `docs/04-DATA_MODEL.md` rev 1.210 API-S-ImpactSummary `journal_lines`, `computed_at`, `computed_period_key` and T-CON-06 `classification`, rev 1.250 `price_tests`; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §7.7 "As bound": the journal preview is what the API's rule makes it — the entries the approval's computation would post at the preview's instant, the change's effect together with the amounts of the period that are not posted yet — and the step states under it the instant and the period it was computed for; a warning says that the entries at approval will differ once that period is no longer the latest postable one of the contract's entity in the primary book, with "Run preview" in the wizard and without a command on SF-07:detail, where it shows while the approval is still to come; the warning holds nothing back; a preview stored before the two members shows neither line. §7.2, the wireframe of step 4, and §7.12, row J-05: the journal preview is the measured example of that rule for the K-02 draft while September is the latest postable period — 2100 Contract liability Dr 2,120.55 / Cr 213.76 and 4010 Revenue - services and subscriptions Dr 213.76 / Cr 2,120.55, two journal lines — **replaced:** "Journal lines 0" and "No journal lines at the modification date." as the journal preview of J-05: the sentence of [J] L4-1-Q-5 is replaced by the rule as built (item MOD-PREVIEW-JOURNAL-RULE-1, way (A)). §7.5 "As bound": every answer of one row carries the proposals of its classification, so a classified draft is not classified again on opening; the rule stays for a row that carries none — **replaced:** "Opening a step past step 1 on a draft whose proposals this visit does not hold classifies it again, unless the row holds a stored preview". §7.5 and §7.6 "As bound", for item MOD-PRICE-TEST-FACT-1: the figures of a price test belong to the SSP version the test read — the sentence names that version by its label while the line's stored basis is that version, and by the engine's key otherwise; the range or point is printed beside the label of the stored basis only while it is that version, and beside a version the preparer named instead the label stands alone. §7.9 "As bound": SF-07:detail states the price test — its sentence under the answer of the price question and its range or point beside the SSP basis — by the same rules. §7.11: the two copy keys of the journal preview |
| 1.57 | 2026-10-01 | lane SECFIX-PLT (item DELEG-LIST-SCOPE-1; the supervisor's ruling of 2026-10-01 on the list clause of the R-111 slice, ruling R-28; docs first; number assigned by the supervisor, register index 208; row appended at the table's tail) | **Applied (text of §15.7).** "The limits of a delegation": the list an access administrator is shown. `GET /approval-delegations` answered every delegation of the workspace to any holder of `role.manage`; it answers the delegations the administrator may end — every one for an administrator of all entities, those whose delegator's access lies within their own for an administrator of named entities — beside the ones they gave or received. The 403 with rule `T-PLT-10` remains for one row, a delegation the administrator received from a delegator beyond their entities. 04 rev 1.261 (API-R-09, T-PLT-21) carries the rule. No route row, capture or copy string changes. |
| 1.53 | 2026-10-02 | lane F-CTR-WEB (patch item (c): CTR-28's screens — the record search of the command palette and the results page; the supervisor's ruling of 2026-10-01 on the lane's pre-build line, P1 to P6, register index 179; `docs/04-DATA_MODEL.md` rev 1.195 API-R-55 and §16.13; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §1.4 "As bound to API-R-55": the palette's record search — for a holder of `contract.read`, from two characters with a letter or digit, 120 ms after the last key; the groups a scope ahead of "Show all results", pages and commands; the scope chips as a radio group; the rows that stay while an answer is on its way, the option that is active, and the Enter that waits for the answer and for the read of an obligation's contract (P3); what is shown without the permission (P4); what is not bound — the recent records of DS-CMP-04 (P1) and the commands beyond navigation, Theme and Density (P5). SF-24:results as bound: `contract.read` and the access-limited screen (P4), the quick search and the chip "Scope", the texts that are not sent, the tables, "Show more", the failed reads, the read of an obligation's contract for its link, the test hooks. §0.4 RT-95: read permission `contract.read` — **replaced:** "authenticated" (P4). §0.12: the row SF-24:results names its two captures, `sf-24-results` and `sf-24-palette` |
| 1.59 | 2026-10-02 | lane WEB-QA (two small defects of SF-11 from lane API-GAPS's browser pass of the exception queue; the supervisor's notes of 2026-10-01 22:25 and its number; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §13.5, the line under the actions of an item whose input was committed. It told the reader to request a waiver also where no waiver was offered to them — an item that offers `ASSIGN` alone, or a reader who does not hold `exception.resolve` for the item's entity. Its second sentence, "Request a waiver instead.", now stands only while "Request waiver" is among the commands offered; otherwise the line is its first sentence alone, under the copy key `.dismissBlockedNoWaiver`. With it, in the same head and without a change of this document: after a refused `assign` the Owner field shows the item's owner again, where it kept showing the member the API had refused. No route, permission, parameter or test hook changes; one copy key is added |
| 1.60 | 2026-10-02 | lane WEB-QA (the screen of item APR-REQUEST-REASON-1, `docs/04-DATA_MODEL.md` rev 1.252 API-S-Approval `comment`; the supervisor's rulings of 2026-10-01 22:25 and 2026-10-02 02:43; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §15.4 region 3. The pane named "Justification: the submission comment" since rev 1.0 and the API answered no such member, so nothing was rendered and an approver decided without it. The API answers `comment` now: region 3 is a region headed "Justification" with the comment as a quoted block, rendered whenever the comment is not null and not rendered for a request submitted without one. The pane holds no rule about who reads it: for a withheld request the API sends the comment to the preparer alone, and "Content withheld" now says that the banner stands in place of regions 4 to 6 (rev 1.32 said 3 to 6). `reason_code` is not read in region 3 (the supervisor's ruling). No route, permission or parameter changes; one copy key (`approvals.request.justification`) and one test hook (`SF-12-justification`) are added |
| 1.62 | 2026-10-02 | lane F-CTR-WEB (the Origin cell of an event; the supervisor's ruling of 2026-10-02 on the lane's second pre-build line, P1 to P4; `docs/04-DATA_MODEL.md` T-CON-05 `origin` and §16.3 API-S-Event; docs first; number assigned by the supervisor, register index 240; row appended at the table's tail) | **Applied.** §5.6 "As bound to API-R-29": Origin of the Events panel is named from the event's own members — "Manual" for an event a person recorded, "Import row <n>" for an event with a source row, else the name of the `origin` literal of 04 T-CON-05: `UI` "Manual", `IMPORT` "Import", `API` "API client <name>" where the event's principal is an API client, `ADAPTER` "Integration", `SYSTEM` "System", `MIGRATION` "Migration"; a literal outside the six is printed as it is. Not bound: the integration's name, which the event does not carry, and the file's name and the link of "Import <file name> row <n>". §4.4 "As bound to API-R-30": column 9 of the invoices reads by the same rule. Before: an event of origin `ADAPTER`, an integration's, read "ADAPTER", and one of origin `UI` without the manual flag, the booking of a contract drafted in the product, read "UI" — the screens translated `INTEGRATION` and `MANUAL`, which the API never answers |
| 1.64 | 2026-10-02 | lane F-CTR-WEB (item EST-DRAWER-JUDGEMENT-1; the supervisor's ruling of 2026-10-02 on the lane's pre-build line, P1 to P9, register index 245; `docs/04-DATA_MODEL.md` §16.14 rev 1.241; `docs/02-PRD.md` rev 1.168 SM-04, ERR-93, ERR-94, IMP-138 to IMP-141, J-07.3; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §8.4 "The constraint's judgement record": a variable-consideration version is submitted with a `CONSTRAINT` record that is sent for review or reviewed — "Submit for approval" asks for the conclusion, "Save draft" stores without it (P1); a new version names no record and records its own, and the screen does not offer the element's earlier reviewed record (P2); a linked record that does not stand is shown with its status and replaced by a new one (P3); without `judgement.create` the submission of a version that names no such record is unavailable with its reason (P4); `ESTIMATE_EVIDENCE_REQUIRED` stands under "Evidence" and `ESTIMATE_CONSTRAINT_RECORD` on "Constraint conclusion" (P7). §8.4 "As bound" of rev 1.29: "Constraint conclusion" is no longer marked optional — **replaced:** "(optional; for a holder of `judgement.create`)"; the evidence rule is the API's too — **replaced:** "which the API does not enforce"; a linked record is shown without a second one being offered only while it is sent for review or reviewed. §8.3 "As bound" (rev 1.64): the open version of an element is the one that is a draft or pending whichever its number, takes the banner and holds a new version back, and a returned latest version has its banner only while none is open (P8) — **replaced** in the paragraph of rev 1.29: "while the latest version is a draft or is pending"; the draft banner asks for the constraint conclusion after the evidence and asks neither of a draft that carries the attestation flag (P5); the pending banner says "Judgement record <number> waits for review.", the words of PRD J-07.3, or names the status of a record that is not sent for review (P6); the status of a judgement record falls back to its literal |
| 1.56 | 2026-10-02 | lane F-SNP (item POLICY-WITHDRAW-ROUTES-1 with the version page's small things; the supervisor's order of 2026-10-01 on the lane's two lines and its three observations; docs first; number assigned by the supervisor, register index 207; row appended at the table's tail) | **Applied.** §11.0 and §11.3, the accounting policy version page. (1) "Withdraw" called `POST /approvals/{id}/withdraw`, which leaves the version `WITHDRAWN`: the page turned read-only, said "Create a new draft version to change values." and offered no control that does (measured in a browser). It calls the policy's own route now, as PRD SM-01 and SM-04 state the transition: the author is back on a `DRAFT`. (2) A `REJECTED` version, and one withdrawn on the Approvals screens, had no way out either. "Edit" is the `PATCH` that reopens it, offered while its basis is still the published version of its scope; once a later version was published the page says PRD ERR-92's sentence in place of the control, with a link to "New policy version", and a refusal that arrives all the same is shown whole. An edit refused for the effective date opens the date field, so that a version whose period start has come can still be reopened. No "New draft version" for a registry version (04 T-PLT-32). (3) Three small things seen on the page: the help of "Effective from" on a settings version that cannot be edited is its first sentence alone; a key longer than the Key column shortens under its full text and the "Changed" chip beside it stays whole; and the summary of a policy request ends without a full stop of its own, so that the Approvals toast "Approved: <summary>." ends with one. (4) Two more, met in a browser on the way of (2) and (3): the drawer the link opens, and the preset modal, answered a create refused while another version of the scope is open (PRD SM-04) with the problem's title alone — the sentence sits on `status` — and now list it; and the cells of the default, legacy-parity and source columns and of a read-only or forced proposed value cut a long literal at the cell's edge without an ellipsis or a tooltip ("RECOGNISE_IN_PERIOD_ON_INCEPTION_BASIS" in 144 px), so that it read as a shorter literal — every literal of the grid shortens as the key does. (5) The grid's room, measured in the same pass and ordered into this head by the supervisor on 2026-10-02: one filter row with the help of Effective from under it, and a floor of eight rows for the grid with the page scrolling below it (§11.3 "Version editor regions"); before, a draft showed three of its 112 parameters at 1440 × 900 and none at 1280 × 800. (6) After the independent review of the head (2026-10-02): the ERR-92 sentence stood twice in the refusal banner, as detail and as message, and stands once (`lib/api/refusals.ts`, every form that lists what no field shows); a refusal of "Edit" no longer outlives the status it was about; "Edit" and "Withdraw" are sent once; the date goes with "Edit" from the field a refusal opened and from nowhere else; focus follows "Withdraw", an accepted "Edit" and the notice that replaces a refusal; each version has its own view; an editable proposed value ends in an ellipsis; the floor leaves room for a scrollbar; a failed read of the versions is said. (7) By the supervisor's ruling on that review: where another version of the scope is open the page says PRD SM-04's sentence in place of "Edit" and of "New policy version", with the link "Open version <m>" — it listed that version and offered a control the API refuses. No route or parameter changes; eight messages are new |
| 1.63 | 2026-10-02 | lane F-SNP (item POLICY-WITHDRAW-ROUTES-1; the supervisor's ruling of 2026-10-02 on the independent review of the head, point 3; docs first; number assigned by the supervisor, register index 207; PRD rev 1.190; row appended at the table's tail) | **Applied.** §11.3 "States". The frozen banner of a policy version said PRD ERR-09's sentence as the other version editors do, "Create a new draft version to change values." — a control no page of a policy version has (rev 1.56; 04 T-PLT-32). It names the control that does change the values: "Withdraw" while the version waits for approval, to the author who is offered it, and a new policy version once the version is approved, published or superseded. §11.1 and §11.2 are unchanged: their versions are copied by "New draft version". Three messages are new |
| 1.61 | 2026-10-02 | lane F-CLO-WEB (item RPT-VIEW-CONTEXT-DEFAULT-1; the supervisor's rulings of 2026-10-02 02:50, 03:43 and 04:10; `docs/design/SCREENS_B.md` rev 1.92; docs first; number assigned by the supervisor, register index 229; row appended at the table's tail) | **Applied.** §0.5 SCR-URL-01. The row let an absent `entity` mean "All entities" on every screen that aggregates. On the three report screens — SF-04, SF-08:report and SF-08:dashboard — that is a report run over every entity in the member's scope, read by a period key that names a different month on each fiscal calendar; a member who holds every entity of a workspace of several calendars met it by opening "Schedules" from the rail. These screens now take the context pill's entity when the address names none and fill `entity`, `period` and `book` under SCR-URL-20, each only where the address leaves it out, before a run is asked. "All entities" stays for an address that says it, with the screen parameter `entities=all`. It is a parameter of its own and not a value of `entity` (the supervisor's ruling of 04:10): `entity` is copied by the rail and by the screens' own links and read as a code in thirteen files, so a value that is no code would have reached every screen, where `entities` is carried by no link that copies the context and read by no other screen. An address that carries both is the entity's. The other screens that aggregate (SF-02 among them) keep "absent means All entities". No route, permission or copy changes |
| 1.65 | 2026-10-02 | lane F-CTR-WEB (item MOD-REJECTED-REVISE-1 on the screens; the supervisor's ruling of 2026-10-02 on the lane's pre-build line, P1 to P9, register index 246; `docs/04-DATA_MODEL.md` §16.14 rev 1.236; `docs/02-PRD.md` SM-03 `REJECTED` → `DRAFT`, "Revise"; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §7.9 "A rejected modification" (a new paragraph): an info banner under the header, "Modification <reference> was rejected. Revise it to submit it again.", with "View request" and — for a holder of `modification.create` for the contract's contracting entity, asked of the access module (P1) — "Revise", the banner being the one place of the command (P3); the confirmation "Revise this modification?" and `PATCH /modifications/{id}` with an empty body, the wizard at step 1 on its answer, nothing opened for a member who has left the page, a refusal shown in the confirmation (P2); the routing of the rejected request stays in "Approval". §7.10: the states "Rejected" and "Revised draft" are added to the table; "As bound" gains the banner of a revised draft on the wizard while the row's request reads `REJECTED` (P4) and the two banners of a draft's earlier request on the read-only detail of a `DRAFT`, which showed neither (P6; ruling R-121 (m), reader C-6). §7.11: the five copy keys. No sentence of an earlier revision is replaced |
| 1.66 | 2026-10-02 | lane F-CTR-WEB (the screens' part of lane SECFIX-ACT's register index 174, with N2 and N3 of index 245 and lane ACCT's hint; the supervisor's rulings of 2026-10-02 on the lane's pre-build lines, P1 to P4 and the riders' P1 to P6, register index 247; `docs/04-DATA_MODEL.md` rev 1.242 API-R-33 `POST /judgements/{id}/discard`, E-57 `VOIDED`, §16.14; `docs/02-PRD.md` rev 1.169 SM-10, ERR-95, and ERR-94, IMP-104; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §0.8 "The status of a judgement record in text" (new): one word per E-57 literal wherever a screen names the status outside a chip, `VOIDED` "Void", a literal the catalogue does not name as itself (P1); a record sent for review reads "Waiting for review" — **replaced:** the word "Submitted" of these places (N3 of index 245). §4.1.3: "Draft Step 1 records" (new) — each draft Step 1 record named in the evidence region with "Discard" for a holder of `judgement.create` for the contract's contracting entity, the confirmation, the sentence of a contract on hold, the refusal, and the proposal of a combination group, which is offered no command (P3 (b)); the path leaves `VOIDED` out — **replaced:** "`SUPERSEDED` and `DRAFT` left out". §4.9.1: the review's two requests and the draft a refused submission leaves; the assessment drawer's line for a record without its reviewer. §7.4: "Discard" in a fourth column of "Linked judgement records" while a row is a draft (P3 (a)). §7.6: a record explains a departure while it is sent for review or reviewed; a rejected and a discarded one do not, and a draft is discarded from the banner (P2). §7.8: "Submit for approval" waits for the modification's own records that are a draft or wait for review, with the sentence of PRD ERR-95, and names a discarded override record with its status. §8.3: the status of a record is read in the words of §0.8 — **replaced:** "in the words of the Step 1 evidence"; "Rev 1.66" (new) — the pending banner says when the version's evidence is no longer attached (rider P1, P2), and "Evidence" carries "Discard" on a draft record (P3 (c)). §8.4: the help of the attestation's Rationale says what belongs in it, with ASC 606-10-32-11 and 32-12 (rider P4 to P6) |
| 1.72 | 2026-10-02 | lane F-CTR-WEB (register index 267 (iii): the screens under supervisor ruling R-102 (c); the supervisor's rulings of 2026-10-02 on the lane's pre-build line, P1 to P8, and on P4, way 1; `docs/04-DATA_MODEL.md` rev 1.150 §16.1 `replace-draft`, §16.3 (b); `docs/03-REQUIREMENTS.md` REQ-POL-008; measured on the API before the build; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §4.10 Routes: a Step 1 assessment does not close the form — **replaced:** the state "Step 1 assessment recorded" — "A Step 1 assessment is recorded on this draft, made on the terms an edit would replace. The draft cannot be edited here.", which kept the form shut on every draft whose stream held an assessment; the form opens under the warning "A Step 1 assessment is recorded on this draft." — "Saving voids it: a new Step 1 review is recorded and reviewed before the contract is activated." where an assessment stands, and says nothing of a voided one (P1); after the booking may follow a hold applied or released, an assessment and the void of an assessment — **replaced:** "`HOLD_APPLIED` or `HOLD_RELEASED` and the stream holds no `COLLECTIBILITY_ASSESSED`" (P2). §4.1.3: the path reads the latest standing assessment of each book, with the voids in its read — **replaced:** "the latest `COLLECTIBILITY_ASSESSED` event of each enabled book" and "latest assessment" in two rows of the table (P3); "A reviewed record that the API refuses" (new) — the screen compares no time, because the time the API compares is answered by no read; the path keeps the row of the reviewed record, and a new review stays in reach in the overflow and in the assessment drawer (P4, way 1). §4.1.6 `DRAFT`: "Record Step 1 review" stays in the overflow beside "Record assessment" — **replaced:** "or "Record assessment" once the record is reviewed". §4.1.7: the path's read asks for `EVENT_VOIDED` too and reads `id`, `event_type` and `supersedes_event_id`. §4.9.1: a refusal on `events.<i>.payload.judgement_record_id` is said in the API's words with the offer "Record a new Step 1 review", which closes the assessment drawer and opens the review drawer in its place (DESIGN_SYSTEM DS-CMP-09: one drawer at a time) |
| 1.74 | 2026-10-02 | lane F-CTR-WEB (register index 274, the web half — lane SECFIX-ACT's item JDG-REJECTED-EXIT-1, a release blocker; the supervisor's order of 2026-10-02 14:13, built without a pre-build line; `docs/02-PRD.md` rev 1.199 SM-10, IMP-145; `docs/04-DATA_MODEL.md` rev 1.296 API-R-33, table 15.4-I; measured on the API before the build; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §4.1.3 "Rejected Step 1 records" (new): each rejected record of a Step 1 topic is named in the evidence region among the drafts, newest first, with "Discard" for the holder and on the views of a draft's line — "Record <judgement no> was rejected. Discard it before the contract is submitted for activation." while the contract is `DRAFT` or `NOT_A_CONTRACT`, "Record <judgement no> was rejected." otherwise — and the confirmation is titled "Discard this rejected record?". §4.9.8: a row of the table and "The line of a rejected record" (new) — the line that names a rejected record of the contract, whatever the record's subject, carries "Discard"; the banner reads the workspace's rejected records once a refusal names one, and the line says "Record <judgement no> was discarded." after the discard. §7.4 and §8.3: a rejected record carries "Discard" as a draft does. §0.8: `VOIDED` is a draft or a rejected record that was discarded — **replaced:** "`VOIDED` is a draft that was discarded" |
| 1.76 | 2026-10-02 | lane F-CTR-WEB (register index 287, item POLICY-OVERRIDE-RECORD-EXIT-1, a release blocker — the lane's finding beside register index 274; the supervisor's orders of 2026-10-02 16:20 and 16:35 on the lane's measured finding, the second with lane ACCT's reading; built without a pre-build line; `docs/02-PRD.md` IMP-104, IMP-102, SM-10; `docs/04-DATA_MODEL.md` T-CON-19, T-CON-20, T-CON-23, API-R-13, API-R-33; measured on the API before the build; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §4.9.7 "The judgement record of a policy override is sent for review" (new): for a parameter whose approval code is `JDG` one press sends four requests — the record as a draft, the override, the record's submission for review, the override's submission; **replaced:** three requests, the record never sent, so that it stayed a draft no screen named and a `DRAFT` contract with such an override was not activated from a screen (measured). The field's help says that the record is sent for review and, on an `ACTIVE` contract, that the contract is on hold until it is reviewed; two toasts confirm the two requests. §4.9.8: the row of `JUDGEMENT_RECORDS` — **replaced:** the link "Record judgement", which was never rendered — and "The records under 'Judgement record required'" (new): the banner reads the workspace's records in the three statuses the item counts (**replaced:** the read of the rejected records, rev 1.74) and the contract's policy overrides, and lists the contract's draft and pending records under the item's last line that names no record — "View request" on a record that names a request; on a draft "Discard", or "Send for review" in its place where an override that is `SUBMITTED` or `APPROVED` names the record, and no command while the overrides are not read. The rule is the whole guard on the screens: the API refuses neither the discard of such a record nor the approval of an override over a record that is not reviewed. §4.9.8 and §4.1.3: the lines of a rejected record carry "View request" before "Discard". §4.1.3, step 2: "Distinct review" reads "Recorded" for a reviewed record alone and else the status word of the obligation's newest record — **replaced:** "Recorded" for a record of any status |
| 1.70 | 2026-10-02 | lane FIX-D2 (item ACT-FLAGS-1, a release blocker; `docs/04-DATA_MODEL.md` rev 1.287 T-PLT-17 `flags`; the supervisor's ruling of 2026-10-02 on the lane's pre-build line, answer Q5; number assigned by the supervisor, register index 260; row appended at the table's tail) | **Applied.** §15.3, the row's flag chips. A contract activation now carries six routing flags the catalogue did not hold — `MATERIAL_RIGHT`, `VARIABLE_CONSIDERATION`, `NEW_SKU`, `SIDE_LETTER`, `TERMS_NOT_STATED` and `RATE_NOT_PUBLISHED` — and a flag without a catalogue entry is shown verbatim, so an approver would have read the literals. Each gains its label `approvals.flag.<flag>`: "Material right", "Variable consideration", "New product", "Side letter", "Terms not stated", "Rate not published". The verbatim fallback stays for a flag the catalogue does not hold. The sentence also says what a reader meets until the booking form states the two terms of a booking (register index 261): every contract a person books reads "Terms not stated". No route, permission, parameter or test hook changes; six copy keys are added |
| 1.75 | 2026-10-02 | lane F-CTR-WEB (register index 281, the screen half of lane SECFIX-ACT's item HOLD-RELEASE-READ-1, a release blocker; the supervisor's orders of 2026-10-02 15:19 and 18:37, on the open holds lane SECFIX-ACT's item HOLD-RELEASE-READ-1 lists since 04 rev 1.299; built without a pre-build line; `docs/04-DATA_MODEL.md` rev 1.299 §16.1, §16.2 `holds`, T-CON-20, API-R-28; measured on the API before the build; docs first; number assigned by the supervisor; row appended at the table's tail, behind rev 1.76, which was delivered first) | **Applied.** §4.9.4 "Release hold as bound to 04 §16.1 and §16.2 rev 1.299" (new): the drawer lists every open hold of the contract — the contract's own, then each obligation's — offers the ones whose `release_refusal` is null in the select, lists the others under it with the API's sentence, and has nothing to send where none is released by hand; an option reads "<type label> · <reason> · applied <timestamp>", an obligation's hold with its key in front — **replaced:** "applied <date>"; the command sends `{hold_id, comment}` with `If-Match`. §4.1.6: "Release hold" renders when the contract is on hold, in the overflow of every status, for a holder of `contract.create` for the contract's contracting entity and not on a view of an earlier `known_at` — **replaced:** not rendered (L5-4-Q-30). §4.1.6 and §5.1: the permission of "Apply hold" and "Release hold" is `contract.create`, as 04 API-R-28 asks — **replaced:** `adjustment.create`. §5.6: the Overview's "Holds" is the table of the obligation's own open holds with a column "Release" — the command, or the API's sentence where the hold is not released by hand — **replaced:** the count of the holds. §5.10: the table's and the drawer's test hooks |
| 1.77 | 2026-10-02 | lane F-CTR-WEB (register index 276, the screen half of lane QA-BE's item MOD-PREVIEW-READ-SCOPE-1, a release blocker; the supervisor's rulings of 2026-10-02 20:23 on the lane's pre-build line, on the member `impact_preview_withheld` that lane QA-BE's item MOD-PREVIEW-READ-SCOPE-1 answers since 04 rev 1.300; `docs/04-DATA_MODEL.md` rev 1.300 §16.10 "Who reads a stored preview", rev 1.295 "Who may ask for a preview"; measured on the API and on the screens before the build; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §7.7 "A stored preview the reader is not shown" (new): a row holds a stored preview when `impact_preview` is not null or `impact_preview_withheld` is true, and the wizard asks that one rule for the open step, the caption of step 4, the banner of a stale preview, the run of step 4 and the classification; where the preview is withheld step 4 shows the info banner "You are not shown this preview" with its text and the line "Catch-up of this contract's obligations: <amount>." in the place of the tables, runs no preview, offers no "Run preview", and "Next" is available. §7.9: "Impact preview as submitted" shows that banner with the snapshot line where the preview is withheld — **replaced:** the row's stored preview is seen by every reader of the row. §7.10: the state "Preview not shown". §7.11: the three copy keys `modifications.impact.withheld.*`. §7.13: the test hook `SF-07-banner-preview-withheld`. Before rev 1.77 the screens read a withheld preview as none (measured): SF-07:detail said "No preview was stored.", and step 4 asked for a new preview — refused to a member whose roles do not reach every entity of the group, and never ending for a member the route takes and the read does not answer |
| 1.71 | 2026-10-02 | lane WEB-QA (item W-12e, the supervisor's rulings of 2026-10-01 16:32 and of 2026-10-02 02:43, 08:35 and 08:52; the blank submission comment, the supervisor's rulings of 2026-10-02 06:30 and 07:36; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** Two matters under one number. (1) §0.6: SCR-PERM-02 (c) names the acts on the whole workspace beside its lists, and SCR-PERM-01 names their routes. Finding (a PRODUCT DEFECT, measured for six pages in a browser as three members who hold their permission for AVM-DE alone): the API asks all entities on the routes of the workspace and the screens asked whether the permission is held for any entity, so such a member was shown pages whose reads were refused — a load-error banner with a "Retry" that repairs nothing, a grid in its error state, "No sandbox copies" over a refused list — and commands the API answered with 403. A control of such an act renders for a holder for all entities; a page whose own content is such a list or act sends no read and shows SCR-ST-06 with a description that names the area and all entities. A description names the permission by its phrase and, in parentheses, its code — the word the Roles screen prints for it — so SCR-PERM-01's "<permission label>" reads "<permission phrase> (<permission code>)": on the ten pages of this revision now, on the other access-limited pages with item PERM-SENTENCE-NAMES-CODE-1; a link asks what its page asks. The pages and their sentences are in SCREENS_B (§6.3, §9.1, §9.3, §9.4, §9.6, §9.7, §9.13, §9.14, §9.15, §10.3, §11.1). (2) §15.4 region 3: "Justification" is rendered whenever the comment is not blank. Finding: a request submitted with white space alone showed the heading over an empty quotation. No route, permission code or parameter changes |
| 1.78 | 2026-10-02 | lane F-CTR-WEB (register index 266, the screen half of lane F-RPS-REG's item COMBINATION-PROPOSAL-DISCARD-1; the supervisor's ruling of 2026-10-02 on the lane's pre-build line — the drawer alone gives up the proposal it made — on the command `POST /combination-groups/{id}/discard` that lane F-RPS-REG's item COMBINATION-PROPOSAL-DISCARD-1 answers since 04 rev 1.289; `docs/04-DATA_MODEL.md` rev 1.289 T-CON-19 "The `COMBINATION` topic", E-95, API-R-28; measured on the API and on the screens before the build; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §4.9.7 "The drawer "Combine with another contract" gives up the proposal it made" (new): after a refused submission of the group the drawer made, a press with the form unchanged continues at the submission; a press with a changed form first sends `POST /combination-groups/{id}/discard` of that group, under a key of its own, and proposes the changed form as a new group; closing the drawer sends the same discard without a question of its own, and the toast reads "The combination was not submitted. Its proposal was discarded."; a refused discard is shown as it comes and the drawer stays; a discard without an answer is sent again by the next close under the same key. **Replaced:** nothing was given up — a changed press made a second `PROPOSED` group beside the first, and closing the drawer left the proposal, which no screen lists. Not built: a list of the proposals that earlier sessions left |
| 1.79 | 2026-10-03 | lane F-CTR-WEB (register index 300 on the screens, with the defect measured beside it; the supervisor's order of 2026-10-03 on the lane's measurement; `docs/04-DATA_MODEL.md` rev 1.314 API-S-Job `result` and §16.10 "Who reads a stored preview", lane QA-BE's item PREVIEW-JOB-RESULT-SCOPE-1; measured on the screens before the build; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §4.9.3 "What the preview panel says of its dry run" (new): for a dry run that ended without a summary the Preview panel of the five event drawers shows the negative banner of SCR-ST-12 — "The preview failed. Nothing was committed." with the messages of the job's problem, the reference and "Retry" — where the job ends `FAILED`, the same banner titled "The preview was cancelled. Nothing was committed." where it was cancelled, and the info banner "You are not shown this preview" where the API withholds the summary from the reader (`result.summary_withheld`). §8.4 "A preview the reader is not shown" (new): the estimate version drawer shows that info banner in the place of the table and offers no "Run preview" while the answer stands. **Withdrawn:** the sentence "No figures change." (`contracts.drawer.preview.none`), which the event drawers showed for every finished job without a summary — a failed dry run, as measured — and which no answer of the API states. **Replaced:** in the estimate version drawer a withheld summary read "The preview of this draft has not run here yet." with "Run preview". Copy keys: `contracts.drawer.preview.failed`, `.cancelled`, `.withheld.title`, `.withheld.text` |
| 1.80 | 2026-10-03 | lane F-CTR-WEB (register index 308, item POLICY-OVERRIDE-WITHDRAW-1, the web half; supervisor ruling R-126 (b) (4) and (c) — policy overrides are withdrawn for release 1.0 — and the supervisor's word of 2026-10-03 on the lane's line; read on the tip before the build; docs first; number assigned by the supervisor; row appended at the table's tail) | **Applied.** §4.9.7 "Policy overrides are not in release 1.0" (new): the API refuses every creation and the screens do not offer the command. **Withdrawn:** the drawer "Request policy override" (§4.9.7), its item in the header's overflow (§4.1.6) and its item in the obligation pane's overflow (§5.1, §5.3), and with the drawer the rule of rev 1.76 for the judgement record it created; nothing stands where the items stood. **Stays:** the records under "Judgement record required" (§4.9.8), read with the contract's policy overrides, and the subject type "Policy override" of §15.3. §6.3: the link of a source record `policy_override` is marked not built. Copy keys withdrawn: `contracts.workbench.action.policyOverride`; `contracts.drawer.override.title`, `.policy`, `.value`, `.judgement`, `.judgementHelp`, `.judgementHelp.held`, `.judgementRequired`, `.submitted` |
| 1.81 | 2026-10-03 | lane SECFIX-CLO (register index 309, item PRODUCT-POLICY-VALUE-NOT-READ-1; supervisor ruling R-126 (c) and the supervisor's rulings of 2026-10-03 on the lane's points of form; read in the code, not in a browser; number assigned by the supervisor; row appended at the table's tail) | **Applied (one clause; no web file changes).** §11.2, the policy values panel of the obligation template version editor, named two server errors and their rendering on the row. A third refusal can answer the panel since `docs/04-DATA_MODEL.md` rev 1.323 (T-REF-23 `policy_values`; PRD ERR-103): a value of `usage.tier_minimum_method` or `upfront_fee.recognition_period` other than the framework's default, and any value of `pob.shipping_as_fulfilment`, which no computation reads from a template. As built the panel gives a refused save to the form's banner (§11.0 "Refused command") without a placing, so the banner prints the sentence of the refusal under the problem's title and no row is marked; the sentence names the parameter by its code for that reason. The key combobox offers every parameter that lists the product level, the three among them: the catalogue keeps the level (POLICIES §0.5 rule 1 rev 1.125). The product's policy values pane (§10.4) is a static table and sends nothing. |

**Table 1.2-A Applied.**

| Ruling or question | Change | Sections and ids |
|---|---|---|
| D-76 `SCREENS:OQ-S-01` to `OQ-S-21` | Each question marked resolved with its ruling | §16 Status column |
| D-76 `SCREENS:R-01` to `R-40` | Every "OQ-S-03 row R-nn" and "R-nn" binding marker replaced by the 04 rev 1.2 id (API-R, API-S, E, table or §16 subsection); names aligned where 04 renamed or reshaped: search `href` as an API link (04 B3-D11), `account` for `gl_account` (B3-D12), usage commitment `status` (B3-D13), combination suggestion fields (B3-D14), activation checklist table 15.4-I (B3-D22) | §1.4, §2.5, §2.6, §4.1.3, §4.1.3.1, §4.1.4, §4.1.7, §4.3 to §4.10, §5.4, §5.6, §5.8, §6.3, §6.5, §6.6, §7.5, §7.7, §8.4 to §8.6, §9.4, §10.3, §11.1 to §11.6, §12.2, §13.3 to §13.5, §14.3, §15.3, §15.4; new table 16-B |
| Fields 04 does not return | Marked "deferred to later" and outside 1.0 captures: search result columns beyond `primary`, `secondary` and `status`; billing plan due date; reversed-line link of subledger lines | §1.4, §4.4, §4.5 |
| D-76 `SCREENS_B:OQ-B-29` | SF-01 demo tour banner: region, condition, copy, binding, sample world and test hook | §2.3, §2.4, §2.5, §2.9, §2.10; §0.4 SF-25 placement row |
| D-76 `SCREENS_B:OQ-B-30` | Screen parameters adopted: SCR-URL-15 amended; SCR-URL-24 to SCR-URL-32 added; SCR-URL-20 order extended | §0.5 |
| Route table reconciliation | RT-99 to RT-112 unchanged and matching; SCREENS_B §14 now cites the rows and restates no path | §0.4 note; index row of SCREENS_B §14 |
| D-76 `SCREENS:OQ-S-12`, `SCREENS_B:OQ-B-01` | "proposed" chip markers removed; the words are DS-CMP-19 rev 1.2 vocabulary | §0.2, §0.8, §2.6, §11.6, §15.7 |
| D-76 `DESIGN_SYSTEM:OQ-07` | "Mark all as read" bound to `POST /me/notifications/read-all` | §1.2 |
| D-76 `SCREENS:OQ-S-11`; 04 API-S-Me | "Ask about revenue" renders on `tenant_settings.ai_enabled` | §1.1 |
| D-76 `SCREENS:OQ-S-17`, `SCREENS_B:OQ-B-06` | Void reason codes cite E-110 and table 3.4-R | §4.9.6 |
| 04 API-R-44 | Severity sort breaks ties newest first | §2.3, §2.5, §2.6, §13.3 |

**Table 1.2-S Decisions taken in B3.**

| Id | Question | Decision | Rationale |
|---|---|---|---|
| B3-S01 | Search items carry only `id`, `primary`, `secondary`, `status` and an API `href` (04 B3-D11) | The client builds routes from scope and id; obligation results read `GET /obligations/{id}` for `contract_id`; other result columns are deferred to later | 04 owns the API and SCREENS owns routes (D-73) |
| B3-S02 | `GET /dashboard/home` accepts only `entity`, `period` and `book` | Home sends no `as_of` or `currency_view` and shows `context.currency` | 04 API-S-DashboardHome picks the currency |
| B3-S03 | The billing plan "Due date" and the subledger "Reverses" link have no API field | Both deferred to later; "Reverses" reads `posting_kind` and `entry_kind` | No invented fields |
| B3-S04 | Placement and persistence of the SF-01 demo tour banner | Above the legacy panel; dismissal per browser session and tenant; a completed demo tour hides it through `preferences.tour_completed` | PRD J-24.1 copy; the preference is the tour's only write (J-24-AC-2) |
| B3-S05 | Parameters used by screens but absent from SCR-URL, which SCR-URL-20 would strip | SCR-URL-24 to SCR-URL-32 cover SCREENS_B §14.3 plus `rows`, `format`, `template`, `mode`, `action`, `kind`, `obligation`, `row`, `sheet`, `source_record` and `node`; the number 19 stays unassigned | Canonicalisation would otherwise remove them |
| B3-S06 | Distinct review form fields against the 04 command body | Conclusion → `distinctness`; "Combine with" → `integrates_into_obligation_key`; Basis → `codification_refs` | 04 §16.1 body |
| B3-S07 | The source record drawer linked an integration connection, while API-S-SourceRecord returns `sync_run_id` only | Link the sync run and read its connection id from `GET /sync-runs/{id}` | Uses defined endpoints only |
| B3-S08 | The rule set list "Lint" chip read `lint_result` | `latest_version.lint_status` of API-S-VersionSummary | 04 naming |

## Index of the screen contract (both files)

| File | Section | Content | SF ids and screen ids |
|---|---|---|---|
| SCREENS.md | §0 | Conventions: identifiers, information architecture, route table, URL parameters, permission gating, `data-testid`, common states, status chips, legacy transition hooks, wireframe notation, saved-view screen codes, screen audit list | all |
| SCREENS.md | §1 | Shell composition: top bar, rail, banners, notifications placement, context pill and tenant switcher, command palette and search results | SF-21, SF-23, SF-24, SF-24:results |
| SCREENS.md | §2 | Home | SF-01 |
| SCREENS.md | §3 | Contracts list | SF-02 |
| SCREENS.md | §4 | Contract workbench: record header, KPI strip, five-step tracker, tabs, Schedules, Billing, Journals, Modifications and History tabs, documents drawer, event drawers, draft contract form | SF-03, SF-03:schedules, SF-03:billing, SF-03:journals, SF-03:modifications, SF-03:history, SF-03:new, SF-03:edit |
| SCREENS.md | §5 | Obligation detail pane | SF-03:obligation |
| SCREENS.md | §6 | Explain panel and calculation trace page | all computed figures; X:trace |
| SCREENS.md | §7 | Modification wizard and modification detail | SF-07, SF-07:detail |
| SCREENS.md | §8 | Estimates workbench | SF-03:estimates, SF-03:estimate |
| SCREENS.md | §9 | Customers and related-party groups | SF-15:customers, SF-15:customer, SF-15:related-party-groups |
| SCREENS.md | §10 | Products and bundles | SF-15:products, SF-15:product |
| SCREENS.md | §11 | Policies: revenue policies and control rules (decision tables), accounting policies, SSP studio, historical SSP calculator, account-role mapping | SF-13 and its secondary screens |
| SCREENS.md | §12 | Imports: list, import wizard, templates and mapping profiles | SF-10, SF-10:new, SF-10:detail, SF-10:templates |
| SCREENS.md | §13 | Exception queue | SF-11, SF-11:item |
| SCREENS.md | §14 | Integrations status | SF-16, SF-16:connection, SF-16:sync-run |
| SCREENS.md | §15 | Approvals inbox, request detail, bulk approval and delegations | SF-12 and its secondary screens |
| SCREENS.md | §16 | Open questions for supervisor | none |
| SCREENS_B.md | §0 | How to use part B: relationship to this file, identifiers, part-B conventions, status chips for part-B literals, report viewer contract, coverage | none |
| SCREENS_B.md | §1 | Close cockpit, close run, journal preview, close history, soft close, lock, reopen, permanent lock, multi-entity close | SF-05, SF-05:close-run, SF-05:journal-preview, SF-05:history, SF-05:multi-entity |
| SCREENS_B.md | §2 | Reconciliations: billing to subledger, subledger to GL, sign-off | SF-05:reconciliations, SF-05:reconciliation |
| SCREENS_B.md | §3 | Journal runs, run detail, lines, batches and acknowledgements, entries by date range | SF-06, SF-06:run, SF-06:run-lines, SF-06:run-batches, SF-06:entries |
| SCREENS_B.md | §4 | Schedules (revenue waterfall) | SF-04 |
| SCREENS_B.md | §5 | Report catalogue, report view, run register and run record, disclosure pack, dashboards, report specifications | SF-08, SF-08:report, SF-08:runs, SF-08:run, SF-08:disclosure-pack, SF-08:dashboard |
| SCREENS_B.md | §6 | Evidence packs and auditor requests, audit log, chain verification | SF-09, SF-09:pack, SF-09:audit-log, SF-09:verification |
| SCREENS_B.md | §7 | Scenarios, forecasts and the deal preview | SF-17, SF-17:event-set, SF-17:run, SF-18 |
| SCREENS_B.md | §8 | AI: contract review, revenue Q&A, proposed narratives, anomaly flags, AI settings, call log | SF-20:new, SF-20, SF-28, SF-15:ai, SF-15:ai-call-log |
| SCREENS_B.md | §9 | Settings index, entities, calendars, currencies and rates, chart of accounts, workspace settings, sandbox copies, notification preferences, profile; users, roles, SoD, access reviews, security, support access; developer settings | SF-15, SF-15:entities, SF-15:calendars, SF-15:currencies, SF-15:chart-of-accounts, SF-15:workspace, SF-15:sandbox, SF-15:notifications, SF-15:profile, SF-14, SF-14:user, SF-14:roles, SF-14:sod, SF-14:access-reviews, SF-14:access-review, SF-14:security, SF-14:support-access, SF-16:developer |
| SCREENS_B.md | §10 | Legacy migration: database import, replay, reconciliation, promotion | SF-19, SF-19:new, SF-19:detail |
| SCREENS_B.md | §11 | Onboarding: workspace setup, guided tour, workspace selection and demo tenants, legacy transition map, About | SF-15:setup, SF-25, SF-23:select, SF-26, SF-27 |
| SCREENS_B.md | §12 | Authentication and error pages | SF-22, SF-22:mfa-challenge, SF-22:mfa-enrol, SF-22:password-change, SF-22:accept-invitation, SF-22:password-reset, SF-22:password-reset-confirm, X:session-expiring, X:route-error, X:narrow-viewport |
| SCREENS_B.md | §13 | Design gallery composition | X:design |
| SCREENS_B.md | §14 | Route and parameter citations (the paths are owned by §0.4 and §0.5 of this file) | none |
| SCREENS_B.md | §15 | Screen audit list for `screens.spec.ts` (part-B screens) | all part-B screens |
| SCREENS_B.md | §16 | Journey coverage | none |
| SCREENS_B.md | §17 | Gaps closed | none |
| SCREENS_B.md | §18 | Open questions for supervisor (`OQ-B-nn`) | none |

The route table (§0.4) names the owning file for every screen id, and a screen id appears in exactly one file.

## 0. Conventions

### 0.1 Identifier families

| Family | Format | Meaning | Rule |
|---|---|---|---|
| Screen id | `SF-nn` (primary route of a surface) or `SF-nn:<slug>` (secondary route) | One navigable route, or one placement for shell surfaces | Stable. It is the React Router route object `id` and the `saved_view.screen_code` (04 T-PLT-37). `<slug>` is kebab-case ASCII. Extra screens that belong to no SF id use `X:<slug>` |
| Route row | `RT-nn` | One row of the route table (§0.4) | Stable; never renumbered |
| Convention | `SCR-<AREA>-nn` | A cross-screen rule: `IA` information architecture, `URL` URL parameters, `PERM` permission gating, `TID` test hooks, `ST` states, `CHIP` status chips, `LTH` legacy transition hooks, `WF` wireframe notation | Mandatory unless marked (guidance) |
| Copy key | `<area>.<screen>.<element>` | Message catalogue key (DG-FE-11) | Copy in this document is binding English text for that key |
| Open question | `OQ-S-nn` | §16 | Resolved by D-76 (rev 1.2). The ids stay listed with their rulings and are never reused |

Every screen section uses the same sub-structure, in this order: summary table (screen id, route, roles and permissions, purpose, REQ, journeys); wireframes at 1440 px and 1280 px; regions and components; data bindings; grid columns; states; interactions, keyboard and copy; sample-world content; test hooks; light and dark notes; accessibility notes.

### 0.2 How the build uses this contract

- **SCR-IA-00.** A screen module lives at `frontend/src/routes/<area>/<screen>.tsx` (DG-READ-02, §8.1). A BUILD_SPEC screen item names screen ids from §0.4; the item is complete when every region, binding, state, copy string and test hook of those screen ids exists and `screens.spec.ts` captures them (§0.12).
- Components are the DS-CMP entries named in each region table. This document introduces no visual pattern; where a composition needs content the design system does not name, §0.8 states it. Every chip word of §0.8 and SCREENS_B §0.4 is DS-CMP-19 vocabulary as of DESIGN_SYSTEM rev 1.2.
- Figures quoted under "Sample world" are PRD §2 values. A figure marked "asserted" is a journey acceptance value; the others are layout content that tests locate but do not assert (WLD-R-06).

### 0.3 Information architecture

**SCR-IA-01 Rail.** The icon rail carries the ten D-02 destinations exactly as DS-CMP-02 specifies (labels, icons, groups, active sets). The default route of each destination:

| Rail item | Destination SF id | Default route (§0.4) | Context filled from the pill | Badge |
|---|---|---|---|---|
| Home | SF-01 | `/home` | `entity`, `period`, `book` | none |
| Contracts | SF-02 | `/contracts` | `entity`, `period`, `book` | none |
| Schedules | SF-04 | `/schedules` | `entity`, `period`, `book` | none |
| Close | SF-05 | `/close` (redirects to `/close/<entity>/<book>/<period>`) | path parameters | none |
| Journals | SF-06 | `/journals` | `entity`, `period`, `book` | none |
| Reports | SF-08 | `/reports` | `entity`, `period`, `book` | none |
| Approvals | SF-12 | `/approvals` | `entity` | count of `PENDING` requests where `can_decide = true` (`GET /approvals?assigned_to_me=true&status=PENDING&count=true`, header `X-Erev-Total-Count`) |
| Policies | SF-13 | `/policies` (redirects to `/policies/revenue`) | none | none |
| Data | SF-10 | `/data/imports` | `entity` | none |
| Settings | SF-15 | `/settings` | none | none |

**SCR-IA-02 Sub-areas are route tabs** (DS-CMP-07 route variant). Each area below renders its page `h1` and one route tab bar. Tabs whose read permission the user lacks are not rendered.

| Area | `h1` | Route tabs, in order (screen id) |
|---|---|---|
| Policies | "Policies" | Revenue policies (SF-13:revenue) · Control rules (SF-13:control-rules) · Accounting policies (SF-13:accounting) · SSP books (SF-13:ssp-books) · SSP calculator (SF-13:ssp-calculator) · Account mapping (SF-13:account-mapping) |
| Data | "Data" | Imports (SF-10) · Exceptions (SF-11) · Integrations (SF-16) · Migrations (SF-19) · Templates (SF-10:templates) |
| Approvals | "Approvals" | Waiting for me (SF-12) · Submitted by me (SF-12:submitted) · All requests (SF-12:all) · Delegations (SF-12:delegations) |
| Reports | "Reports" | Catalogue (SF-08) · Report runs (SF-08:runs) · Evidence packs (SF-09) · Audit log (SF-09:audit-log) · Scenarios and forecasts (SF-17); dashboards (SF-08:dashboard) open from the catalogue; composition in SCREENS_B |
| Journals | "Journals" | Journal runs (SF-06) · Entries by date range (SF-06:entries); composition in SCREENS_B |
| Contract workbench | the contract `h1` | Obligations · Estimates · Schedules · Billing · Journals · Modifications · History (§4.1; REQ-UX-004 as amended by D-76, OQ-S-01) |

**SCR-IA-03 Settings.** `/settings` (SF-15) is a start-aligned section index, not a card grid (DS-AP-02). Each settings page renders the breadcrumb "Settings / <page>" and the route tab bar of its group only:

| Group | Pages (screen id, path) | Specified in |
|---|---|---|
| Your preferences | Notifications (SF-15:notifications, `/settings/notifications`); Profile (SF-15:profile, `/settings/profile`) | SCREENS_B |
| Workspace | Setup (SF-15:setup); Workspace settings (SF-15:workspace); Entities (SF-15:entities); Calendars (SF-15:calendars); Currencies and rates (SF-15:currencies); Chart of accounts (SF-15:chart-of-accounts) | SCREENS_B |
| Reference data | Customers (SF-15:customers); Related-party groups (SF-15:related-party-groups); Products (SF-15:products) | this file §9, §10 |
| Access | Users (SF-14, with child route SF-14:user); Roles (SF-14:roles); Separation of duties (SF-14:sod); Access reviews (SF-14:access-reviews, with child route SF-14:access-review); Security (SF-14:security); Support access (SF-14:support-access) | SCREENS_B |
| Developer | API clients and webhooks (SF-16:developer) | SCREENS_B |
| AI | AI settings (SF-15:ai); Call log (SF-15:ai-call-log) | SCREENS_B |
| Sandbox | Sandbox copies (SF-15:sandbox) | SCREENS_B |

[J] An index plus per-group tabs keeps one navigation paradigm (DS-CMP-02) without a nineteen-tab bar. Customers and products sit under Settings because PRD SF-15 carries REQ-REF-010 to REQ-REF-013 [F: PRD §3].

**SCR-IA-04 Record hierarchy.** Contract (SF-03) contains obligations, estimates, schedules, billing, journal lines, modifications and history. Obligations never appear as a top-level destination (D-02). A modification (SF-07) is a child route of its contract; the rail stays on Contracts.

**SCR-IA-05 Drill-down chain** (REQ-RPT-017, J-16). Any figure → Explain (§6) → contract (SF-03) → obligation (SF-03:obligation) → schedule lines (SF-03:obligation Schedule panel, or SF-04 filtered) → contributing events (SF-03:obligation Events panel) → source row (the import row drawer of SF-10:detail, §12.3) or source record drawer (§6.6). Every step has a Back path: the browser Back button restores the previous route with its panel state (§0.5), and Esc closes the topmost panel and returns focus to its trigger.

### 0.4 Route table

Paths are React Router 7 patterns. `:contractId`, `:obligationId`, `:estimateId`, `:modificationId`, `:importId`, `:exceptionId`, `:connectionId`, `:syncRunId`, `:requestId`, `:templateId`, `:ruleSetId`, `:versionId`, `:policyId`, `:bookId`, `:runId`, `:mappingVersionId`, `:customerId`, `:productId`, `:proposalId`, `:packId`, `:verificationId`, `:eventSetId`, `:migrationId`, `:calcTraceId`, `:reconciliationId`, `:membershipId` and `:reviewId` match a lowercase UUID (`^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`); a non-matching value renders NotFound (X:not-found). `:dashboardCode` matches `^[a-z][a-z0-9_]*$`. Static segments rank above parameters, so `/contracts/new` never matches `:contractId`. "Read permission" is any-of (SCR-PERM-01); "authenticated" means any signed-in member. Document titles follow DS-BR-06: `<title> · eRev Cloud`.

| RT | Screen id | Path | Title | Rail item | Read permission | Specified in |
|---|---|---|---|---|---|---|
| RT-01 | SF-22 | `/sign-in` | Sign in | none | public | SCREENS_B |
| RT-02 | SF-22:mfa-challenge | `/sign-in/mfa` | Verify your sign-in | none | password step completed | SCREENS_B |
| RT-03 | SF-22:mfa-enrol | `/mfa/enrol` | Set up multi-factor authentication | none | authenticated | SCREENS_B |
| RT-04 | SF-22:password-change | `/password/change` | Change password | none | authenticated | SCREENS_B |
| RT-05 | SF-22:accept-invitation | `/accept-invitation` (token in the URL fragment `#token=<token>`, never a query parameter) | Accept invitation | none | public | SCREENS_B |
| RT-06 | SF-23:select | `/select-workspace` | Choose a workspace | none | authenticated | SCREENS_B |
| RT-07 | SF-01 | `/home` (`/` redirects here, keeping the search string) | Home | Home | authenticated | §2 |
| RT-08 | SF-02 | `/contracts` | Contracts | Contracts | `contract.read` | §3 |
| RT-09 | SF-03:new | `/contracts/new` | New contract | Contracts | `contract.create` | §4.10 |
| RT-10 | SF-03 | `/contracts/:contractId/obligations` (`/contracts/:contractId` redirects here) | `<external id> · <customer name>` | Contracts | `contract.read` | §4 |
| RT-11 | SF-03:obligation | `/contracts/:contractId/obligations/:obligationId` | `<obligation key> · <external id>` | Contracts | `contract.read` | §5 |
| RT-12 | SF-03:estimates | `/contracts/:contractId/estimates` | `Estimates · <external id>` | Contracts | `contract.read` | §8 |
| RT-13 | SF-03:estimate | `/contracts/:contractId/estimates/:estimateId` | `<element code> · <external id>` | Contracts | `contract.read` | §8 |
| RT-14 | SF-03:schedules | `/contracts/:contractId/schedules` | `Schedules · <external id>` | Contracts | `contract.read` | §4.3 |
| RT-15 | SF-03:billing | `/contracts/:contractId/billing` | `Billing · <external id>` | Contracts | `contract.read` | §4.4 |
| RT-16 | SF-03:journals | `/contracts/:contractId/journals` | `Journal lines · <external id>` | Contracts | `contract.read` | §4.5 |
| RT-17 | SF-03:modifications | `/contracts/:contractId/modifications` | `Modifications · <external id>` | Contracts | `contract.read` | §4.6 |
| RT-18 | SF-03:history | `/contracts/:contractId/history` | `History · <external id>` | Contracts | `contract.read` | §4.7 |
| RT-19 | SF-03:edit | `/contracts/:contractId/edit` | `Edit draft · <external id>` | Contracts | `contract.create` | §4.10 |
| RT-20 | SF-07 | `/contracts/:contractId/modifications/new` | `New modification · <external id>` | Contracts | `modification.create` | §7 |
| RT-21 | SF-07:detail | `/contracts/:contractId/modifications/:modificationId` | `<modification no> · <external id>` | Contracts | `contract.read` | §7 |
| RT-22 | SF-18 | `/contracts/deal-preview` | Deal preview | Contracts | `scenario.use` | SCREENS_B |
| RT-23 | SF-20:new | `/contracts/review/new` | Review a contract document | Contracts | `ai.use` | SCREENS_B |
| RT-24 | SF-20 | `/contracts/review/:proposalId` | Contract review | Contracts | `ai.use` | SCREENS_B |
| RT-25 | SF-04 | `/schedules` | Schedules | Schedules | `contract.read` | SCREENS_B |
| RT-26 | SF-05 | `/close/:entity/:book/:period` (`/close` redirects from the context) | `Close · <entity> · <period label> · <book label>` | Close | `contract.read` | SCREENS_B |
| RT-27 | SF-05:multi-entity | `/close/multi-entity` | Multi-entity close | Close | `period.close` | SCREENS_B |
| RT-28 | SF-06 | `/journals` | Journal runs | Journals | `contract.read` | SCREENS_B |
| RT-29 | SF-06:run | `/journals/runs/:runId` | `Journal run <run no>` | Journals | `contract.read` | SCREENS_B |
| RT-30 | SF-06:entries | `/journals/entries` | Journal entries by date range | Journals | `contract.read` | SCREENS_B |
| RT-31 | SF-08 | `/reports` | Reports | Reports | `report.run` | SCREENS_B |
| RT-32 | SF-08:report | `/reports/:reportCode` (`:reportCode` is a 04 T-RPT-01 code) | `<report name>` | Reports | `report.run` | SCREENS_B |
| RT-33 | SF-08:run | `/reports/runs/:runId` | `Report run <run no>` | Reports | `report.run` or `audit.read` (rev 1.22; 04 API-R-41 rev 1.128) | SCREENS_B |
| RT-34 | SF-08:disclosure-pack | `/reports/disclosure-pack` | Disclosure pack | Reports | `report.run` | SCREENS_B |
| RT-35 | SF-09 | `/reports/evidence` | Evidence packs | Reports | `report.run` | SCREENS_B |
| RT-36 | SF-09:pack | `/reports/evidence/:packId` | `Evidence pack <pack no>` | Reports | `report.run` | SCREENS_B |
| RT-37 | SF-09:audit-log | `/reports/audit-log` | Audit log | Reports | `audit.read` | SCREENS_B |
| RT-38 | SF-09:verification | `/reports/audit-log/verifications/:verificationId` | Audit chain verification | Reports | `audit.read` | SCREENS_B |
| RT-39 | SF-17 | `/reports/forecasts` | Scenarios and forecasts | Reports | `scenario.use` | SCREENS_B |
| RT-40 | SF-17:event-set | `/reports/forecasts/event-sets/:eventSetId` | `<event set name>` | Reports | `scenario.use` | SCREENS_B |
| RT-41 | SF-17:run | `/reports/forecasts/runs/:runId` | `Forecast run <run no>` | Reports | `scenario.use` | SCREENS_B |
| RT-42 | SF-10 | `/data/imports` | Imports | Data | `contract.read` | §12.1 |
| RT-43 | SF-10:new | `/data/imports/new` | New import | Data | `import.upload` | §12.2 |
| RT-44 | SF-10:detail | `/data/imports/:importId/:step` (`:step` ∈ `map`, `validate`, `review`, `approval`, `committed`; `/data/imports/:importId` redirects to the step of the import status, §12.2) | `<import no> · <template name>` | Data | `contract.read` | §12.2 |
| RT-45 | SF-10:templates | `/data/templates` | Import templates | Data | `contract.read` | §12.4 |
| RT-46 | SF-11 | `/data/exceptions` | Exceptions | Data | `contract.read` | §13 |
| RT-47 | SF-11:item | `/data/exceptions/:exceptionId` | `<exception title>` | Data | `contract.read` | §13 |
| RT-48 | SF-16 | `/data/integrations` | Integrations | Data | `integration.manage` | §14 |
| RT-49 | SF-16:connection | `/data/integrations/:connectionId` | `<connection name>` | Data | `integration.manage` | §14 |
| RT-50 | SF-16:sync-run | `/data/integrations/:connectionId/sync-runs/:syncRunId` | `Sync run · <connection name>` | Data | `integration.manage` | §14 |
| RT-51 | SF-19 | `/data/migrations` | Migrations | Data | `migration.run` | SCREENS_B |
| RT-52 | SF-19:new | `/data/migrations/new` | New migration | Data | `migration.run` | SCREENS_B |
| RT-53 | SF-19:detail | `/data/migrations/:migrationId` | `Migration <migration no>` | Data | `migration.run` | SCREENS_B |
| RT-54 | SF-12 | `/approvals` | Approvals | Approvals | authenticated | §15 |
| RT-55 | SF-12:submitted | `/approvals/submitted` | Submitted by me | Approvals | authenticated | §15 |
| RT-56 | SF-12:all | `/approvals/all` | All requests | Approvals | authenticated; lists the requests the caller may see under 04 API-R-09 (preparer, decider or holder of a step permission; D-90a) | §15 |
| RT-57 | SF-12:request | `/approvals/requests/:requestId` | `<request summary>` | Approvals | authenticated; a request the caller may see under 04 API-R-09 (preparer, decider or holder of a step permission); otherwise the SF-12:request not-found state "Approval request not found" (§15.6; D-90a) | §15 |
| RT-58 | SF-12:delegations | `/approvals/delegations` | Delegations | Approvals | any approval permission (T-PLT-11 `is_approval`) | §15.7 |
| RT-59 | SF-13:revenue | `/policies/revenue` (`/policies` redirects here) | Revenue policies | Policies | `config.read` | §11.1 |
| RT-60 | SF-13:control-rules | `/policies/control-rules` | Control rules | Policies | `config.read` | §11.1 |
| RT-61 | SF-13:template-version | `/policies/templates/:templateId/versions/:versionId` | `<template code> v<n>` | Policies | `config.read` | §11.2 |
| RT-62 | SF-13:rule-set-version | `/policies/rule-sets/:ruleSetId/versions/:versionId` | `<rule set code> v<n>` | Policies | `config.read` | §11.1 |
| RT-63 | SF-13:accounting | `/policies/accounting` | Accounting policies | Policies | `config.read` | §11.3 |
| RT-64 | SF-13:accounting-version | `/policies/accounting/:policyId` | `Accounting policies v<n> · <scope>` | Policies | `config.read` | §11.3 |
| RT-65 | SF-13:ssp-books | `/policies/ssp-books` | SSP books | Policies | `ssp.read` | §11.4 |
| RT-66 | SF-13:ssp-book-version | `/policies/ssp-books/:bookId/versions/:versionId` (`/policies/ssp-books/:bookId` redirects to the current approved version, else the draft) | `<book code> <version label>` | Policies | `ssp.read` | §11.4 |
| RT-67 | SF-13:ssp-calculator | `/policies/ssp-calculator` | SSP calculator | Policies | `ssp.read` | §11.5 |
| RT-68 | SF-13:ssp-calculator-run | `/policies/ssp-calculator/runs/:runId` | `<run name>` | Policies | `ssp.read` | §11.5 |
| RT-69 | SF-13:account-mapping | `/policies/account-mapping` | Account mapping | Policies | `config.read` | §11.6 |
| RT-70 | SF-13:account-mapping-version | `/policies/account-mapping/:mappingVersionId` | `<mapping name> v<n>` | Policies | `config.read` | §11.6 |
| RT-71 | SF-15 | `/settings` | Settings | Settings | authenticated | SCREENS_B |
| RT-72 | SF-15:notifications | `/settings/notifications` | Notification preferences | Settings | authenticated | SCREENS_B |
| RT-73 | SF-15:profile | `/settings/profile` | Profile | Settings | authenticated | SCREENS_B |
| RT-74 | SF-15:setup | `/settings/setup` | Workspace setup | Settings | `settings.manage` | SCREENS_B |
| RT-75 | SF-15:entities | `/settings/entities` | Entities | Settings | `config.read` | SCREENS_B |
| RT-76 | SF-15:calendars | `/settings/calendars` | Calendars | Settings | `config.read` | SCREENS_B |
| RT-77 | SF-15:currencies | `/settings/currencies` | Currencies and rates | Settings | `config.read` | SCREENS_B |
| RT-78 | SF-15:chart-of-accounts | `/settings/chart-of-accounts` | Chart of accounts | Settings | `config.read` | SCREENS_B |
| RT-79 | SF-15:customers | `/settings/customers` | Customers | Settings | `contract.read` | §9 |
| RT-80 | SF-15:customer | `/settings/customers/:customerId` | `<customer name>` | Settings | `contract.read` | §9 |
| RT-81 | SF-15:related-party-groups | `/settings/related-party-groups` | Related-party groups | Settings | `contract.read` | §9 |
| RT-82 | SF-15:products | `/settings/products` | Products | Settings | `contract.read` | §10 |
| RT-83 | SF-15:product | `/settings/products/:productId` | `<product code> · <product name>` | Settings | `contract.read` | §10 |
| RT-84 | SF-15:sandbox | `/settings/sandbox` | Sandbox copies | Settings | `tenant.snapshot` | SCREENS_B |
| RT-85 | SF-15:ai | `/settings/ai` | AI assistance | Settings | `settings.manage` | SCREENS_B |
| RT-86 | SF-15:ai-call-log | `/settings/ai/call-log` | AI call log | Settings | `ai.use`, `settings.manage` | SCREENS_B |
| RT-87 | SF-14 | `/settings/users` | Users | Settings | `user.manage` | SCREENS_B |
| RT-88 | SF-14:roles | `/settings/roles` | Roles | Settings | `role.manage` | SCREENS_B |
| RT-89 | SF-14:sod | `/settings/separation-of-duties` | Separation of duties | Settings | `role.manage` | SCREENS_B |
| RT-90 | SF-14:access-reviews | `/settings/access-reviews` | Access reviews | Settings | `access.approve` | SCREENS_B |
| RT-91 | SF-14:security | `/settings/security` | Security | Settings | `settings.manage` | SCREENS_B |
| RT-92 | SF-14:support-access | `/settings/support-access` | Support access | Settings | `support_grant.approve` | SCREENS_B |
| RT-93 | SF-16:developer | `/settings/developer` | API clients and webhooks | Settings | `api_client.manage`, `webhook.manage` | SCREENS_B |
| RT-94 | SF-26 | `/help/legacy-transition` | Coming from eRev desktop | none | authenticated | SCREENS_B |
| RT-95 | SF-24:results | `/search` | Search results | none | `contract.read` | §1.4 |
| RT-96 | X:trace | `/trace/:calcTraceId` | Calculation trace | none | `contract.read`, `report.run` | §6.5 |
| RT-97 | X:design | `/design` (compiled only when `VITE_EREV_DESIGN_GALLERY=1`, DS-VER-06) | Design gallery | none | authenticated | DESIGN_SYSTEM DS-VER-06 |
| RT-98 | X:not-found | `*` | Not found | none | authenticated | §0.7 |
| RT-99 | SF-05:close-run | `/close/:entity/:book/:period/close-run` | `Close run · <entity> · <period label>` | Close | `contract.read` | SCREENS_B |
| RT-100 | SF-05:journal-preview | `/close/:entity/:book/:period/journal-preview` | `Journal preview · <entity> · <period label>` | Close | `contract.read` | SCREENS_B |
| RT-101 | SF-05:history | `/close/:entity/:book/:period/history` | `Close history · <entity> · <period label>` | Close | `contract.read` | SCREENS_B |
| RT-102 | SF-05:reconciliations | `/close/:entity/:book/:period/reconciliations` | `Reconciliations · <entity> · <period label>` | Close | `contract.read` | SCREENS_B |
| RT-103 | SF-05:reconciliation | `/close/:entity/:book/:period/reconciliations/:reconciliationId` | `<reconciliation kind label> · <entity> · <period label>` | Close | `contract.read` | SCREENS_B |
| RT-104 | SF-06:run-lines | `/journals/runs/:runId/lines` | `Journal run <run no> · lines` | Journals | `contract.read` | SCREENS_B |
| RT-105 | SF-06:run-batches | `/journals/runs/:runId/batches` | `Journal run <run no> · batches` | Journals | `contract.read` | SCREENS_B |
| RT-106 | SF-08:runs | `/reports/runs` | Report runs | Reports | `report.run` or `audit.read` (rev 1.22; 04 API-R-41 rev 1.128) | SCREENS_B |
| RT-107 | SF-08:dashboard | `/reports/dashboards/:dashboardCode` | `<dashboard name>` | Reports | `report.run` | SCREENS_B |
| RT-108 | SF-14:user | `/settings/users/:membershipId` | `<user name>` | Settings | `user.manage` | SCREENS_B |
| RT-109 | SF-14:access-review | `/settings/access-reviews/:reviewId` | `Access review <review no>` | Settings | `access.approve` | SCREENS_B |
| RT-110 | SF-15:workspace | `/settings/workspace` | Workspace settings | Settings | `settings.manage` | SCREENS_B |
| RT-111 | SF-22:password-reset | `/password/reset` | Reset password | none | public | SCREENS_B |
| RT-112 | SF-22:password-reset-confirm | `/password/reset/confirm` (token in the URL fragment `#token=<token>`) | Choose a new password | none | public | SCREENS_B |

Placements (no route):

| Screen id | Placement | Opened by | Specified in |
|---|---|---|---|
| SF-21 | Top-bar Notifications bell popover (DS-CMP-05) | Bell button | §1.2 |
| SF-23 | Top-bar context pill (DS-CMP-03); "Switch tenant" in the user menu; sandbox indicator and banner; "Read-only access" chip | Always present | §1.3 |
| SF-24 | Command palette modal (DS-CMP-04) | `Mod K`, search trigger | §1.4 |
| SF-25 | Guided tour overlay | Help menu "Guided tour", search parameter `tour=demo` or `tour=legacy`, or "Take the tour" on the SF-01 demo tour banner (§2.4) | SCREENS_B (the banner on SF-01 is specified in §2.4) |
| SF-27 | About dialog | Help menu "About eRev Cloud" (DS-CMP-01), search parameter `dialog=about` (OQ-S-10) | SCREENS_B |
| SF-28 | Revenue Q&A docked panel | Top-bar ghost icon button "Ask about revenue", search parameter `panel=ask` (OQ-S-11) | SCREENS_B |
| X:session-expiring | Session-expiry modal (DS-CMP-01 state) | Two minutes before expiry | SCREENS_B |
| X:route-error | Route error boundary inside the shell | An unhandled render or loader error | SCREENS_B |
| X:narrow-viewport | Notice below 1024 px (not a G8 target, DS-SP-04) | Viewport width below 1024 px | SCREENS_B |

Screen ids RT-99 to RT-112 and the three X placements were first named by SCREENS_B (SB-R-03, §14); their paths, titles and read permissions are fixed here (D-73). SCREENS_B §14 cites these rows and is not a second source for them.

**SCR-IA-06 Route objects.** The route object of a primary screen has `id = "SF-nn"`; a secondary screen has `id = "SF-nn:<slug>"`; every route object carries `handle = {sf: "SF-nn", screen: "<screen id>", titleKey}` (DG-FE-02 as clarified by OQ-S-09). `notification.link_path` (T-PLT-24; PRD NTF-R6) uses these paths: NTF-01 `/approvals/requests/<request id>`; NTF-02 to NTF-04 the subject route (for example `/contracts/<id>/obligations`); NTF-05 the originating screen; NTF-06 to NTF-08 `/close/<entity>/<book>/<period>`; NTF-09 `/reports/audit-log/verifications/<id>`; NTF-10 `/journals/runs/<id>`; NTF-11 `/data/exceptions/<id>`; NTF-12 `/settings/support-access`.

### 0.5 URL parameters

| Id | Parameter | Values | Rule |
|---|---|---|---|
| SCR-URL-01 | `entity` | Entity code (API-C-11), for example `AVM-US`; absent means "All entities" on screens that aggregate — except on the report screens of rev 1.61, where an absent entity is filled and "All entities" is said by `entities=all` | On every route with the context pill except SF-05 (path). Screens that cannot aggregate fill the default entity when absent. **The report screens (rev 1.61; item RPT-VIEW-CONTEXT-DEFAULT-1; SCREENS_B §0.5 "The context of a view", rev 1.92).** SF-04, SF-08:report and SF-08:dashboard aggregate, and still take the context pill's entity when their address names none: they fill `entity`, `period` and `book` under SCR-URL-20 — each only where the address leaves it out, never rewriting one it names — and write them before a report run is asked. A period key names a different month on each fiscal calendar, so "every entity in scope" is no default for a report screen whose address says nothing. On these three screens an address says "All entities" with the screen parameter `entities=all`: the runs cover every entity in the member's scope, with the `period` and the `book` the address has, and nothing is filled (on SF-08:dashboard the period and the book are then read as SCREENS_B §5.5 states). `entities` is no context parameter: no link that copies the context carries it and no other screen reads it; only a link that means all entities writes it, and it stands after the parameters SCR-URL-20 orders. An address that carries both `entity` and `entities=all` is the entity's |
| SCR-URL-02 | `period` | `period_key` (API-C-11), for example `FY2026-P09` | The pill shows the DS-FMT-19 label ("Sep 2026"), never the key (DS-CMP-03) |
| SCR-URL-03 | `book` | `ASC606`, `IFRS15`, `LEGACY` | Pill label `ASC 606`, `IFRS 15`, `Legacy` |
| SCR-URL-04 | `currency_view` | `transaction` (default, omitted), `functional`, `reporting` (API-C-11) | Only on screens with the currency view switch (DS-FMT-12) |
| SCR-URL-05 | `known_at` | RFC 3339 UTC timestamp with `Z` | Advanced read option (BR-UX-02, BR-PLT-10). When present, a static info banner reads "Showing figures known at <DS-FMT-17 timestamp>." with the action "Show current figures" (removes the parameter) |
| SCR-URL-06 | `snapshot` | `period_lock.id` (T-CLS-04) of the context entity, book and period | "As locked" read (BR-PLT-10, BR-RPT-02). Overrides `known_at`. Report screens pass it as `period_lock_id` (SCREENS_B RV-04); other screens read with `known_at` = the lock's `created_at` (OQ-S-18). Banner "Showing <period label> as locked on <DS-FMT-17 timestamp>." with the action "Show current figures" |
| SCR-URL-07 | `view` | `saved_view.id` or a quick-list literal (§3.4) | DataGrid state (DS-CMP-10). Unsaved modifications of a view are carried by the other grid parameters and the selector shows its dot |
| SCR-URL-08 | `q` | Free text | Quick search (DS-CMP-13) |
| SCR-URL-09 | `sort` | `<field>` ascending, `-<field>` descending; one key | Field names are 04 API sort keys. On a screen with more than one grid the key belongs to the grids that list it: each grid applies only a key of its own and keeps its default order otherwise, and the value is unrecognised under SCR-URL-21 only when no grid on the screen lists it (rev 1.11) |
| SCR-URL-10 | `f.<field>` | `<operator>:<value>[,<value>…]`, operators `is`, `in`, `not`, `contains`, `between`, `gte`, `lte`, `empty`, `notempty`; values are API literals or ISO dates; commas inside a value are percent-encoded | One parameter per filter chip; the grid maps each to the API query parameter named in its filter table |
| SCR-URL-11 | `explain` | `<object_type>~<id>~<measure>` with an optional `~<period_key>` | Opens the Explain panel for that figure (§6). `object_type` and `measure` are 04 §16.11 values. "Copy link" in the panel copies the URL with this parameter. The parameter names a figure the API explains: while the panel shows a list level (§6.3, rev 1.21) the parameter is absent |
| SCR-URL-12 | `drawer` | Screen-defined drawer name, for example `documents` | Informational drawers only. Form drawers are never URL state, so dirty input never appears in a URL |
| SCR-URL-13 | `pane` | Panel tab of a detail pane, for example `ssp` | DS-CMP-07 panel tabs change `pane` with `history.replace`; the default tab omits it. A panel tab that changes `pane` removes the list parameters of the pane it leaves (`sort`, `q`, `f.*`, `view`) in the same `history.replace` (rev 1.19; crawl finding F4): on a screen whose panes hold their own lists those parameters belong to the pane that wrote them, and the next pane's grid would report a `sort` key it does not list as an unrecognised link value (SCR-URL-21). A screen whose list stays mounted beside its panes (SF-03: the obligations list beside the obligation pane) keeps them |
| SCR-URL-14 | `dialog`, `tour`, `panel` | `about`, `shortcuts`; `demo`, `legacy`; `ask` | Shell overlays (§0.4 placements) |
| SCR-URL-15 | `step` path segment or search parameter | Wizard step slug | Path segment on SF-10:detail only (RT-44). Search parameter on SF-07 (`change`, `questionnaire`, `treatment`, `preview`, `submit`) and on SF-19:detail (opening balances: `profile`, `mapping`, `import`, `reconciliation`, `promotion`; replay: `profile`, `plan`, `replay`, `reconciliation`, `promotion`; SCREENS_B §10.3) |
| SCR-URL-16 | `run` | Report run uuid (T-RPT-02) | Renders a stored report run and creates none (SCREENS_B RV-01) |
| SCR-URL-17 | `p.<key>` | Report-specific parameter values (API-S-ReportRunCreate keys) | Report screens only (SCREENS_B RPT-R-01) |
| SCR-URL-18 | `layout` | Screen-defined layout literal, for example `lines` | SF-04 (SCREENS_B §4); SF-12 on Waiting for me: `bulk`, the selection grid of §15.5 (rev 1.20, WEB-16) |
| SCR-URL-24 | `rows`, `granularity`, `measure` | `rows` ∈ `contract` (default), `obligation`, `product`, `revenue_category`; `granularity` ∈ `month`, `quarter`, `year`; `measure` ∈ `total` (default), `by_state` | SF-04 only (SCREENS_B §4.1). A missing `granularity` means `month`, or `quarter` when the range exceeds 36 months. The values reach the `revenue_waterfall` run as `row_dimension`, `granularity` and `measure` in uppercase (SCREENS_B RPT-01) |
| SCR-URL-25 | `format`, `from`, `to` | `format` ∈ `gross` (default), `adjustment` (SCR-LTH-07); `from` and `to` are ISO dates `YYYY-MM-DD`, `from` on or before `to` | SF-06:entries only (SCREENS_B §3.5). Missing dates are filled from the context period's start and end dates; a reversed range is replaced by them under SCR-URL-21 |
| SCR-URL-26 | `run.<panel>` | Report run uuid per dashboard panel | SF-08:dashboard only (SCREENS_B §5.5); each value renders its stored run as SCR-URL-16 does |
| SCR-URL-27 | `calendar`; `rate_set`, `version` | Calendar code; rate set code and version number (integer) | `calendar` on SF-15:calendars; `rate_set` and `version` on SF-15:currencies (SCREENS_B §9.3, §9.4). They select a list item; an unknown value selects the first item under SCR-URL-21 |
| SCR-URL-28 | `template`, `mode` | SF-10:new: `template` = an import template code and `mode` ∈ `prospective`, `retrospective`, `pob_price_change` (SCR-LTH-O5); SF-19:new: `mode` ∈ `OPENING_BALANCES`, `REPLAY` (SCREENS_B §10.2) | Preselection only; the form fields stay editable |
| SCR-URL-29 | `event_set` | Forecast event set uuid | SF-10:new in a scenario tenant only; sent as API-S-ImportCreate `forecast_event_set_id`, so the committed upload is appended to that set (SCREENS_B §7.2) |
| SCR-URL-30 | `reason`, `next` | `reason` ∈ `session-expired`; `next` = a same-origin path that begins with `/` and not with `//` | SF-22 only (SCREENS_B §12.1). Any other `next` value is dropped |
| SCR-URL-31 | `action`, `kind`, `obligation` | `action` ∈ `upgrade`, `downgrade`, `co_term`, `renew`, `early_renew`, `cancel` (§4.1.6); `kind` = a modification kind literal of 04, for example `PRICE_CHANGE`; `obligation` = an obligation uuid (SCR-LTH-06) | SF-07 only; preselection of step `change`, whose fields stay editable |
| SCR-URL-32 | `row`, `sheet`; `source_record`; `node`; `event` | Import row number and sheet name; source record uuid; calculation trace node id; audit event chain sequence (T-PLT-19 `chain_seq`; rev 1.20, was the event's uuid) | `row` and `sheet` open the import row drawer on SF-10:detail (§6.6, §12.3); `source_record` accompanies `drawer=source-record` (§6.6); `node` selects a node on X:trace (§6.5); `event` accompanies `drawer=event` on SF-09:audit-log (SCREENS_B §6.3; rev 1.13). They are removed when their drawer closes |

No id with the number 19 exists in this family, and SCR-URL-20 to SCR-URL-23 and SCR-URL-33 are the rules below rather than parameter rows; SCR-URL-33 was added in revision 1.40. SCR-URL-24 to SCR-URL-32 were added in revision 1.2 from SCREENS_B §14.3 and the screen parameters of §0.10, §4.1.6, §6.5, §6.6 and §12.3 (SCREENS_B:OQ-B-30 resolved by D-76); `event` joined SCR-URL-32 in revision 1.13 (SCREENS_B §6.3); since revision 1.20 its value is the event's chain sequence.

- **SCR-URL-20 Canonicalisation.** On first render, missing context parameters are filled from BR-UX-01 (last choice, else first entity in scope in code order, its earliest `open` period, the primary book) and written with `history.replace`. Parameters that a screen does not use are removed. Parameter order in the canonical URL: path, then `entity`, `period`, `book`, `currency_view`, `known_at`, `snapshot`, `run`, `p.*`, `layout`, `rows`, `granularity`, `measure`, `format`, `from`, `to`, `run.*`, `calendar`, `rate_set`, `version`, `template`, `mode`, `event_set`, `action`, `kind`, `obligation`, `step`, `reason`, `next`, `view`, `q`, `sort`, `f.*` in column order, `pane`, `explain`, `drawer`, `row`, `sheet`, `source_record`, `node`, `event`, `dialog`, `tour`, `panel`.
- **SCR-URL-21 Invalid values.** An entity code outside the user's scope, an unknown `period_key` or a book the entity does not keep is replaced by the default, and a dismissible warning banner (DS-CMP-29) reads "The link named <parameter label> <value>, which is not available to you. Showing <replacement label>." An unparseable `f.*`, `sort` or `view` value is dropped with the banner "Some filters in the link were not recognised and were removed."
- **SCR-URL-22 Context changes.** Changing a pill segment replaces the context parameters, keeps grid parameters that remain valid, closes Explain (figures belong to the old context) and announces "Context changed to <entity>, <period>, <book>" (DS-CMP-03).
- **SCR-URL-23 Reads.** Every read passes `as_of` = end date of the context period and `known_at` = now unless SCR-URL-05 or SCR-URL-06 applies (BR-UX-02, DG-FE-04).
- **SCR-URL-33 Writes of a page that is leaving.** (Rev 1.40; item KIT-FILTER-LEAVING-1; `docs/dev-guide.md` DG-FE-03 rev 1.215.) A control changes the address of the page it belongs to and of no other. Once the address has moved to another page, a filter chip, a sort header, a tab or any other control of the page still on screen changes nothing: its write is dropped, and the next page keeps the address it was opened with. A control that names its destination (a link to another page, a row's link, a breadcrumb) is followed as before. A page is leaving from the moment the member starts for another page, not only once the address has moved (rev 1.49; item KIT-FILTER-LEAVING-2; DG-FE-03 rev 1.230): while the next page is on its way, a control of the page being left changes nothing either, and neither a press there, nor the late answer of a command, nor a panel or a context that the leaving page writes into its own address keeps the member on it or calls them back. A control of a page that is on its way to itself — a filter applied while an earlier one is still being loaded — writes as before. The limit (restated in rev 1.49): a page is known by its route, not by its record. Once the address has moved from one record to another under the same route (contract A to contract B) and until the later record's page is drawn, a control of the earlier record that is pressed still writes, onto the later record's address. The answer of a command is not such a write: it is made only for the page that sent it. The FilterBar (SCR-URL-08, SCR-URL-10) works out each write from the address as it stands at that moment, so two chips removed in quick succession are both removed.

### 0.6 Permission gating

- **SCR-PERM-01 Route guard.** Each route declares the any-of read permissions of §0.4, evaluated against `GET /me` permissions for the context entity. When the user holds none, the route renders inside the shell the access-limited empty state (DS-CMP-23): title "You do not have access to <area label>", description "Ask a workspace administrator for a role that includes <permission phrase> (<permission code>).", no primary action. The API remains the enforcer (BR-UX-05). (Rev 1.30; 04 §16.12 API-S-Me `permission_scopes`.) A permission is held for an entity when `permission_scopes[<code>]` is `"*"` or names the entity's id; that the code is among `permissions` says only that it is held for some entity. A route of tenant-wide objects (Policies, Settings, Access) asks whether its permission is held for any entity. (Rev 1.34; supervisor ruling R-28.) The audit log (RT-37), which rev 1.30 counted among those routes, is a list of the whole workspace, which the API answers to a holder of `audit.read` for all entities only: its route asks whether the permission is held for all entities, and a holder for named entities reads the access-limited state of SCREENS_B §6.3. (Rev 1.71; item W-12e.) So are the routes whose page is a list of, or an act on, the whole workspace: RT-51 to RT-53 (legacy migration), RT-74 (workspace setup), RT-84 (sandbox copies), RT-90 and RT-109 (access reviews), RT-91 (security), RT-92 (support access) and RT-110 (workspace settings, whose values `config.read` still reads, SCREENS_B §9.6) ask whether the permission is held for all entities, and RT-93 asks `api_client.manage` for any entity or `webhook.manage` for all; a holder for named entities reads the access-limited state SCR-PERM-02 states. A description names the permission by its phrase and, in parentheses and in mono, its code — the word the Roles screen prints for it (SCREENS_B §9.11), which the administrator who is asked will look for; "<permission label>" named the phrase alone. The pages of rev 1.71 say so now, the other access-limited pages with item PERM-SENTENCE-NAMES-CODE-1.
- **SCR-PERM-02 Actions.** A command control renders only when the user holds its permission in the record's entity scope (BR-UX-05, DG-FE-16). Controls are never shown disabled for lack of permission, with one exception: the approval decision form, which renders the text "You do not have approval rights for this request type." (DS-CMP-16). (Rev 1.30; 04 T-PLT-10, API-S-Me `permission_scopes`; supervisor ruling of 2026-10-01 on item W-12.) A control asks one of four questions, the ones the API asks: (a) for a record of one legal entity — a contract, a period, an import, a journal run — whether the permission is held for that entity; (b) for a tenant-wide object — a policy, a product, a customer, the read-only chip of SCR-PERM-06 — whether it is held for any entity; (c) for a tenant-wide act or list — the definition of a role, a list of the whole workspace — whether it is held for all entities; (d) for a membership or a role assignment, whether it is held for every entity the grants name, and for all entities when one of them is for all. A command held for another entity only is not rendered, exactly like a command without the permission; no state says so. A member of all entities is answered from `GET /me` alone. For a member of named entities a record that states its entity by code alone is resolved through the entities of the workspace, and until they are read no command of such a record is offered. (Rev 1.38; item W-12, slice c; the supervisor's ruling of 2026-10-01 on the slice's special cases, case 4.) The upload of an import is not of one entity: its rows name their entities and are judged at validation. `import.upload` therefore asks whether it is held for any entity — at "New import", on the routes of the import screens and for the uploader's commands on an import — which restates the mention of an import under (a). An exception is asked for its own entity where it has one, and for any entity when it has none (one raised on an import that names no entity). The approval decision form asks none of the four: it follows `can_decide` of API-S-Approval (§15.4 region 7), the server's own answer, which counts the entities of the request's subject and an authority delegated to the member; the client computes no coverage for it. (Rev 1.34; item W-12, slice b; supervisor ruling R-28; 04 API-R-10, API-R-11.) The audit events of the workspace are a list of question (c): a region that reads `GET /audit-events` — "Recent activity" of §2, the "Audit trail" of §4.7, the history of a journal run and the audit log (SCREENS_B §3.2, §6.3) — asks whether `audit.read` is held for all entities, and a holder for named entities gets what a member without the permission gets. `GET /jobs` answers every member the jobs they started, so a region that follows a job asks nothing. Where the API refuses either read with 403 `forbidden` all the same, the region renders what it renders for a member without the permission — the variant its screen states, or nothing — and not the error state SCR-ST-05: "Retry" does not repair a refusal, and the read is not sent again. (Rev 1.71; item W-12e; supervisor ruling R-28; 04 API-C-03.) The acts on the whole workspace are of question (c) with its lists: the tenant and its setup, the currencies the workspace enables, a snapshot, a sandbox copy and a reset, a support grant, a webhook endpoint and its deliveries, an access review, a legacy migration. A control of such an act renders for a holder of its permission for all entities, and so does the setup branch of "Open period" (SCREENS_B §9.3). A page whose own content is such a list or act — Workspace setup, Workspace settings, Security, Support access, Sandbox copies, Access reviews and a campaign, a migration, the webhooks of the developer page — sends no read for a member who does not hold the permission for all entities and shows the access-limited state SCR-ST-06: for a holder for named entities with the description "<Area> covers every entity of the workspace. Ask a workspace administrator for a role that includes <permission phrase> (<permission code>) for all entities." and for a member without the permission with the description of SCR-PERM-01; both name the permission the page asks. A link to such a page — in the settings index and in the tabs of a settings page — asks the same question as the page, so that no link leads to that state.
- **SCR-PERM-03 State guards.** A permitted command that the record state does not allow renders with `aria-disabled="true"` and a visible reason line when the user would reasonably look for it (for example "Submit for activation" on a contract that is `PENDING_REVIEW`: "Activation is waiting for approval."); otherwise it is not rendered. Each screen's interaction table states which.
- **SCR-PERM-04 Scope.** An id outside the user's entity scope renders the not-found state (§0.7, ERR-30), identical to an unknown id (BR-UX-06).
- **SCR-PERM-05 Problems at command time.** `forbidden` shows a negative toast with ERR-01 copy. `mfa-step-up-required` opens the step-up modal (DS-CMP-11 form variant) titled "Confirm with your authenticator" with one field "Authentication code" (`autocomplete="one-time-code"`), buttons "Cancel" and "Confirm"; on success the command is re-sent with the same `Idempotency-Key` (DG-FE-05). `mfa-required` for a not-enrolled user navigates to `/mfa/enrol`. `self-approval`, `approver-already-decided` and `stale-approval` render their ERR copy in a negative banner inside the decision form (§15).
- **SCR-PERM-06 Read-only chip.** A user whose roles hold no command permission sees the neutral chip "Read-only access" in the top bar after the sandbox indicator (BR-UX-04).
- **SCR-PERM-07 Permission labels** used in SCR-PERM-01 copy (message keys `perm.<code>`):

| Code | Label | Code | Label |
|---|---|---|---|
| `contract.read` | viewing contracts | `contract.create` | preparing contracts |
| `modification.create` | preparing modifications | `estimate.create` | preparing estimates |
| `config.read` | viewing configuration | `config.author` | authoring configuration |
| `ssp.read` | viewing SSP books | `ssp.create` | preparing SSP versions |
| `masterdata.maintain` | maintaining customers and products | `import.upload` | uploading imports |
| `exception.resolve` | resolving exceptions | `integration.manage` | managing integrations |
| `audit.read` | viewing the audit log | `ai.use` | using AI assistance |
| `scenario.use` | using scenarios | `report.run` | running reports |
| `migration.run` | running migrations | `user.manage` | managing users |

### 0.7 Common states

Every data region implements these states (DG-FE-14). Screen sections give only the region-specific copy.

| Id | State | Trigger | Rendering and copy |
|---|---|---|---|
| SCR-ST-01 | Loading | First fetch | Region skeleton after 150 ms (DS-CMP-30), `aria-busy="true"`, visually hidden "Loading <region name>" |
| SCR-ST-02 | Refreshing | Refetch with data present | Grid: 2 px indeterminate bar along its top edge (DS-CMP-10); other regions keep content |
| SCR-ST-03 | Empty | API returns no items and no filters are applied | DS-CMP-23 with the screen's title, description and next step |
| SCR-ST-04 | No results | No items with filters applied | Title "No <plural record label> match these filters", action "Clear filters" |
| SCR-ST-05 | Error | Problem response or network failure | Negative banner (DS-CMP-29) inside the region: title "Could not load <region name>", message = problem `title` then "Reference <request id>." (CPY-05), action "Retry". A 500 without slug uses ERR-34 copy. Existing rows stay visible |
| SCR-ST-06 | No permission | SCR-PERM-01; for a page whose own list is refused with 403, SCR-PERM-02 (rev 1.34) | Access-limited empty state |
| SCR-ST-07 | Not found | 404 `not-found`, or a non-matching path parameter | Page-level empty state: title "<Object label> not found", description "It may have been removed from your access, or the link is incorrect.", action "Go to <parent area>" (X:not-found uses "Page not found" and "Go to Home") |
| SCR-ST-08 | Stale or recomputing | A `CONTRACT_COMPUTE` job for the record is `QUEUED` or `RUNNING`, or the record's `context.known_at` precedes its latest event `recorded_at` | Info banner "Figures were computed before the latest change. Recalculation is queued." with the job indicator (DS-CMP-24); figures stay visible with the stale marker (DS-CMP-26). On job success the region refetches and the banner is removed |
| SCR-ST-09 | Record changed | 412 `precondition-failed` on a command | Warning banner "This record changed. Reload to see the latest version." with action "Reload" (DG-FE-05; ERR-07). Typed input is kept (DS-A11Y-19) |
| SCR-ST-10 | Time travel | SCR-URL-05 or SCR-URL-06 | Info banner of that rule; every command control is hidden, because commands act on current state |
| SCR-ST-11 | Sandbox | Tenant kind `sandbox` | Global banner "Sandbox: <tenant name>. Nothing here posts or exports." (BR-UX-03) |
| SCR-ST-12 | Job failed | Job `FAILED` for a command started on the screen | Negative banner "<job label> failed. Nothing was committed." with the problem title, "Reference <job id prefix>", action "Retry" where the command is repeatable (DS-CMP-24; NTF-05 is sent by the server) |
| SCR-ST-13 | Refused command (rev 1.47) | Problem response to a command, other than the 412 of SCR-ST-09 | One negative banner (DS-CMP-29) in the form, drawer or dialog that sent the command: the problem's `title`, or the sentence the screen's section states for its slug; its `detail`, unless a field shows the same sentence; every message of `errors[]` that no field of the form shows; "Reference <request id>." (CPY-05). Each sentence is said once, also where the API sends it as the `detail` and again as a message. A message whose pointer names a member that a field on screen sends shows at that field (DS-CMP-21) and leaves when the field is edited; a message on a member the form has no field for, or whose field is not on screen, is the banner's. A refusal is therefore never shown nowhere, and a banner never points at fields that show nothing. §10.4, §11.0 "Refused command" and SCREENS_B §9.15 state it for their screens; a screen section adds only the sentences of its own slugs (DG-FE-06; item KIT-UNPLACED-ERRORS-1) |

### 0.8 Status chips for 04 literals

DS-CMP-19 fixes words and tones. The table below maps each 04 enumeration literal shown on the screens of this file to a chip. SCREENS_B §0.4 extends it for part-B literals; where both files map a literal, this table governs. Every chip word below is DS-CMP-19 vocabulary as of DESIGN_SYSTEM rev 1.2, which adopted the words this table first proposed (OQ-S-12 resolved by D-76); the tone and icon columns repeat DS-CMP-19 as a reading aid, and DS-CMP-19 governs.

| Enum | Literal | Chip | Tone and icon |
|---|---|---|---|
| E-17 `contract_status` | `DRAFT` / `PENDING_REVIEW` / `ACTIVE` / `VOIDED` | Draft / Pending approval / Active / Void | DS-CMP-19 |
| E-17 | `NOT_A_CONTRACT` | Not a contract | neutral, Prohibit |
| E-17 | `COMPLETED` | Completed | positive, CheckCircle |
| E-17 | `TERMINATED` | Terminated | neutral, Prohibit |
| SMAP-01 label | non-singleton group member | Combined | outline variant |
| E-26 `modification_status` | `DRAFT` / `SUBMITTED` / `APPROVED` / `REJECTED` / `VOIDED` | Draft / Pending approval / Approved / Rejected / Void | DS-CMP-19 |
| E-26 | `APPLIED` | Applied | positive, CheckCircle |
| E-12 `config_status` | `DRAFT` / `SUBMITTED` / `APPROVED` / `REJECTED` / `WITHDRAWN` / `VOIDED` | Draft / Pending approval / Approved / Rejected / Withdrawn / Void (`VOIDED`: a discarded estimate version only; rev 1.33, 04 rev 1.210) | DS-CMP-19 |
| E-12 | `TESTED` | Tested | info, CheckCircle |
| E-12 | `PUBLISHED` | Published | positive, CheckCircle |
| E-12 | `SUPERSEDED` | Superseded | neutral, ClockCounterClockwise |
| E-12 | `VOIDED` (rev 1.29: a discarded estimate version; the literal arrives with item EST-DISCARD-1, ruling R-119 (e)) | Void | DS-CMP-19 |
| E-40 `import_status` | `UPLOADED` / `VALIDATING`, `VALIDATED`, `DIFFING`, `COMMITTING` | Queued / Running | DS-CMP-19 |
| E-40 | `INVALID` | Error, with the caption "Rejected: fix the file and upload again" (SM-05) | negative |
| E-40 | `DIFF_READY` | Valid | positive |
| E-40 | `SUBMITTED` / `APPROVED` / `REJECTED` / `FAILED` | Pending approval / Approved / Rejected / Failed | DS-CMP-19 |
| E-40 | `COMMITTED` | Committed | positive, CheckCircle |
| E-40 | `CANCELLED` | Cancelled | neutral, Prohibit |
| E-41 `import_row_status` | `VALID` / `WARNING` / `ERROR` | Valid / Warning / Error | DS-CMP-19 |
| E-41 | `BLANK` / `AGGREGATED` | Blank / Aggregated | neutral, Minus / neutral, TreeStructure |
| E-43 `exception_severity` | `BLOCKING` / `WARNING` / `INFO` | Blocking / Warning / Info | negative, XCircle / warning / info, Info |
| E-44 `exception_status` | `OPEN` / `IN_PROGRESS` / `RESOLVED` / `WAIVED` / `DISMISSED` | Open / In progress / Resolved / Waived / Dismissed | neutral, Circle / info, CircleHalf / positive, CheckCircle / neutral, CheckCircle / neutral, Prohibit |
| E-05 `approval_request_status` | `PENDING` / `APPROVED` / `REJECTED` / `WITHDRAWN` | Pending approval / Approved / Rejected / Withdrawn | DS-CMP-19 |
| E-05 | `VOIDED` with `void_reason = STALE_SUBJECT` | Stale | DS-CMP-19 |
| E-05 | `VOIDED` with `void_reason = SUBJECT_VOIDED` | Void | DS-CMP-19 |
| E-72 `sync_run_status` | `QUEUED` / `RUNNING` / `SUCCEEDED` / `FAILED` | Queued / Running / Succeeded / Failed | DS-CMP-19 |
| E-72 | `CONTROL_TOTAL_MISMATCH` | Difference | DS-CMP-19 |
| E-22 `satisfaction_status` | `SATISFIED` | Satisfied | DS-CMP-19 |
| E-22 | `UNSATISFIED` / `PARTIALLY_SATISFIED` / `CANCELLED` | none (not a chip; the Overview panel states progress) / none / Cancelled | — / — / neutral, Prohibit |
| T-INT-01 `status` | `ACTIVE` / `DISABLED` | Active / Disabled | neutral, Circle / neutral, Prohibit |
| E-57 `judgement_status` | `REVIEWED` | Reviewed | positive, CheckCircle |

**The status of a judgement record in text (rev 1.66; 04 E-57 rev 1.242).** Where a screen names the status of a judgement record in a sentence or a cell and not as a chip — the Step 1 evidence of §4.1.3 and the assessment drawer of §4.9.1, the linked records, the override banner and the summary of §7.4, §7.6 and §7.8, "Evidence", the banners and the version drawer of §8.3 and §8.4, and the criteria-met region of §15.4 — it reads one word per literal: `DRAFT` "Draft", `SUBMITTED` "Waiting for review", `REVIEWED` "Reviewed", `REJECTED` "Rejected", `SUPERSEDED` "Superseded", `VOIDED` "Void". `VOIDED` is a draft or — rev 1.74 — a rejected record that was discarded (PRD SM-10) and reads as a discarded estimate version and a discarded modification read. A record sent for review reads "Waiting for review" and not "Submitted", the word these places had: "Submitted" names the preparer's act, the state is a wait, and the sentences of §4.1.3, §7.8 and §8.3 say "waits for review" of it. A literal the catalogue does not name reads as itself, so a status a later API adds does not fail the screen; three of these places read the status through a catalogue key alone before rev 1.66. The chip of E-57 stays `REVIEWED` alone.

Classifications (outline variant, no icon): "Point in time", "Over time", "Ratable", "Series", "Material right", "Licence", "Service warranty", "Legacy v1", "CSV v2", "Remediable", "Discarded", "Manual", "Intercompany: <entity code> performs" (J-03.4), and the outline flags of approval requests (§15.3).

### 0.9 Test hooks

- **SCR-TID-01 Locator order.** Journeys locate by role and accessible name, then by label, and use `data-testid` only where no accessible name exists (DG-E2E-09). Each screen's hooks table lists the accessible locator first.
- **SCR-TID-02 Format.** `data-testid="<SF id>-<element>"`. `<SF id>` is the PRD id verbatim, uppercase with its hyphen (`SF-03`), for primary and secondary screens alike; extra screens use `X`. `<element>` matches `^[a-z0-9]+(-[a-z0-9]+)*$`.
- **SCR-TID-03 Keys.** A key inside `<element>` is a business identifier normalised by: lowercase; every run of characters outside `[a-z0-9]` becomes one hyphen; leading and trailing hyphens removed. Examples: `SF-ORD-10001` → `sf-ord-10001`; `FY2026-P09` → `fy2026-p09`; obligation key `O1` → `o1`; code `PROGRESS_OVER_DELIVERY` → `progress-over-delivery`. Generated sequence numbers (`CON-`, `IMP-`, `APR-`) and UUIDs never appear in a test id (WLD-R-07).
- **SCR-TID-04 Shared vocabulary.** `page` (the route's `main` content root); `kpi-strip`; `kpi-<measure>` (measure names of 04 API fields in kebab-case, for example `kpi-transaction-price`); `tracker`; `tracker-step-<n>`; `evidence-<n>`; `tabs`; `grid-<name>`; `row-<key>`; `chart-<name>`; `empty-<region>`; `error-<region>`; `banner-<name>`; `job-<region>`; `pane-<name>`; `drawer-<name>`; `filter-bar`; `saved-view`; `selection-bar`; `diff`; `decision-form`; `explain`; `explain-<section>`; `step-<slug>`.
- **SCR-TID-05 Volatile content.** Relative times, "Last computed" timestamps, elapsed durations, request ids, job ids and `recorded_at` values carry `data-volatile` so screenshots mask them (DG-E2E-06).

### 0.10 Legacy 14-button transition hooks

Each legacy button (PRD LTM-01 to LTM-14) has a concrete landing in the product. The command palette (§1.4) indexes the legacy label as an alias, so typing it finds the landing: the result row reads "<eRev Cloud action>" with the secondary text "Desktop: <legacy button>". The strings "Load SSPs", "Purge Contracts" and the other legacy labels appear only in the palette alias catalogue `messages/en.json` namespace `legacy.aliases` and in SF-26 (LTM-O5; none is a DS-LINT-19 term).

| Id | LTM | Legacy button | Landing (route and control) | Control copy | Locator |
|---|---|---|---|---|---|
| SCR-LTH-01 | LTM-01 | Load SSPs | `/data/imports/new?template=legacy_sku_ssp`; also SF-13:ssp-books overflow "Import SKU SSP template" | "Upload legacy SKU SSP template" | palette option; button name "Import SKU SSP template" |
| SCR-LTH-02 | LTM-02 | Load Contracts | `/data/imports/new?template=legacy_contract_setup`; SF-02 overflow "Import contracts" | "Upload legacy Contract Setup template" | button name "Import contracts" |
| SCR-LTH-03 | LTM-03 | Load Delivery and Billing | `/data/imports/new?template=legacy_progress_tracking` (the Upload step asks for the effective date) | "Upload legacy Contract Progress Tracking template" | palette option |
| SCR-LTH-04 | LTM-04 | Prospective Contract Mod | `/data/imports/new?template=legacy_contract_modification&mode=prospective`; SF-03 "New modification" | "Upload legacy Contract Modification template (prospective)" | button name "New modification" |
| SCR-LTH-05 | LTM-05 | Retrospective Contract Mod | `/data/imports/new?template=legacy_contract_modification&mode=retrospective`; SF-07 treatment "Cumulative catch-up" | "Upload legacy Contract Modification template (retrospective)" | palette option |
| SCR-LTH-06 | LTM-06 | POB Specific VC | `/data/imports/new?template=legacy_contract_modification&mode=pob_price_change`; SF-03:obligation action "Change price" (opens SF-07 with `kind=PRICE_CHANGE&obligation=<obligationId>`) | "Upload legacy Contract Modification template (price change)" | button name "Change price" |
| SCR-LTH-07 | LTM-07 | Revenue Journal Entries | `/journals`; `/journals/entries?format=gross` and `?format=adjustment` | "Journal runs", "Entries by date range" | link names |
| SCR-LTH-08 | LTM-08 | Contract History | `/reports/contract_history`; SF-03:history "Versions" view | "Contract history report" | link name |
| SCR-LTH-09 | LTM-09 | Latest Contract Status | `/reports/latest_contract_status`; SF-03 KPI strip | "Latest contract status report" | link name |
| SCR-LTH-10 | LTM-10 | Backup Database | `/settings/sandbox` "Create sandbox copy" | "Create sandbox copy" | button name |
| SCR-LTH-11 | LTM-11 | Restore from Backup | `/settings/sandbox` "Restore into a new sandbox" | "Restore into a new sandbox" | button name |
| SCR-LTH-12 | LTM-12 | !Reset Database Completely! | `/settings/sandbox` "Reset sandbox" (rendered in sandbox tenants only) | "Reset sandbox" | button name |
| SCR-LTH-13 | LTM-13 | Append from Another | `/data/migrations/new` | "Import a legacy database" | link name |
| SCR-LTH-14 | LTM-14 | Purge Contracts | SF-03 overflow menu "Void contract" (§4.1) | "Void contract" | menu item name |

| Id | Onboarding hook (PRD LTM-O1 to LTM-O4) | Where |
|---|---|---|
| SCR-LTH-O1 | Dismissible panel "Coming from eRev desktop" on Home in tenants whose published TENANT accounting policy version has `preset_code = LEGACY_PARITY` | §2.4 |
| SCR-LTH-O2 | Tour variant `tour=legacy` with five stops: SF-10:templates, SF-10:detail review step, SF-12, SF-08:report `contract_history`, SF-06 | SCREENS_B (SF-25) |
| SCR-LTH-O3 | Empty states of SF-02, SF-10 and SF-06 in preset tenants link to the legacy templates, and for members of WLD-T-00 to the Legacy parity pack | §3.6, §12.1; SCREENS_B |
| SCR-LTH-O4 | SF-26 renders PRD §7.1 to §7.3 | SCREENS_B |
| SCR-LTH-O5 | `?template=<code>` and `?mode=<literal>` on SF-10:new preselect the template and parameter, so help links and the palette land on the right upload | §12.2 |

### 0.11 Wireframe notation

- **SCR-WF-01.** One character is 12 px wide and one line is 24 px high. The 1440 px wireframe is 120 characters wide; the 1280 px wireframe is 106 characters. Wireframes show layout, not copy length.
- **SCR-WF-02.** Glyphs: `[Label]` button (a leading `*` marks the primary button); `{Label v}` select or combobox; `(Chip)` status chip; `<Chip>` outline chip; `____` input; `[x]` checkbox; `##` bar fill, `..` bar track; `//` hatch (Awaiting trigger); `|*` selection edge on a selected row; `>` caret or breadcrumb separator; `...` overflow menu; `fn` Explain affordance; `~` separator in URLs only.
- **SCR-WF-03.** Between 1024 and 1279 px, layouts follow DS-SP-04 (rail collapsed, master 300 px, Explain as overlay). Screens state only departures from that rule.

### 0.12 Saved-view screen codes and screen audit list

- **SCR-IA-07 Screen codes.** `saved_view.screen_code` = the screen id, plus `#<grid name>` when a screen has more than one grid. Codes used by this file: `SF-02`; `SF-03:schedules#revenue`; `SF-03:journals`; `SF-10`; `SF-11`; `SF-15:customers`; `SF-15:products`; `SF-13:revenue#templates`; `SF-13:revenue#rule-sets`; `SF-13:control-rules`; `SF-13:accounting`; `SF-13:ssp-books`; `SF-16#sync-runs`; `SF-12:all`.
- **SCR-IA-08 Favourites** (REQ-UX-017). A favourite is a `saved_view` row with `is_favourite = true`, `screen_code` = the target screen id and `config = {"target": "contract" | "report" | "saved_view", "path": "<route path with search string>", "label": "<display label>"}` (04 T-PLT-37 favourites; OQ-S-15 resolved by D-76).
- **SCR-ST-20 `screens.spec.ts`.** DG-E2E-07 captures each screen below in light and dark themes, comfortable density, at 1440 × 900. DG-E2E-02 runs the `screens` project after `avenmoor-serial`, so records show their post-journey state; captures check rendering and axe results, never figures. Tenant WLD-T-01 unless stated; context `entity=AVM-US&period=FY2026-P09&book=ASC606` unless stated. SCREENS_B §15 lists the part-B screens.

| Screen id | Persona | URL and state captured |
|---|---|---|
| SF-01 | `priya` | `/home` (approver variant) |
| SF-01 | `robert` | `/home` (Viewer: "Recently viewed" variant) |
| SF-02 | `maya` | `/contracts` default view |
| SF-03 | `maya` | K-01 `SF-ORD-10001`, Obligations tab, no selection |
| SF-03:obligation | `maya` | K-11 `NS-SO-DE-5004` O1 selected, context `entity=AVM-DE` |
| SF-03:estimates, SF-03:estimate | `maya` | K-03 `PRJ-CB-2026-01`, EAC element selected. Rev 1.29: `sf-03-estimates` (RT-12) is the list with the element under its kind and nothing selected, the route having no element; `sf-03-estimate` (RT-13) the element at `pane=versions` with version 1 pending approval; `sf-03-estimate-version` the version drawer with the preview of the saved draft; `sf-03-estimate-current` the panel "Current version" of that pending version, with the catch-up of its stored preview and its evidence; `sf-03-estimate-discard` (rev 1.51) the confirmation of "Discard draft" over the banner of the draft. The rows add the element and version 1 through the two drawers, because the demo seed holds no estimate (§8.9 is owed) |
| SF-03:schedules, SF-03:billing, SF-03:journals, SF-03:modifications, SF-03:history | `maya` | K-02 `SF-ORD-10002` |
| SF-03:new | `maya` | empty form |
| Explain panel | `maya` | K-01 O1 Sep 2026 schedule amount (`explain` parameter) |
| X:trace | `maya` | trace of that figure |
| SF-07 | `maya` | K-02 co-term wizard at step `questionnaire`; the capture creates the draft under a reference of its own, and the row SF-07:detail discards it after its own captures (rev 1.42; item MOD-DISCARD-1). Rev 1.51: a second capture, `sf-07-change`, is step `change` of that draft once the row SF-07:detail has withdrawn its request — the panel "Linked estimate versions" without a version, and "Add estimate version" with its reason, K-02 holding no estimated element |
| SF-15:customers, SF-15:customer, SF-15:related-party-groups | `tomas` | list; C-05 detail; groups |
| SF-15:products, SF-15:product | `maya` | list; AVM-PLAT-100 detail |
| SF-13:revenue, SF-13:control-rules, SF-13:rule-set-version | `maya` | lists; `APPROVAL_ROUTING` version 1 |
| SF-13:template-version | `maya` | `TPL-SUB-DAILY` current version; a draft that replaces the current version of `TPL-OPTION`, with the Meta form (`sf-13-template-version-draft`): the row creates the draft, is refused today's date, submits it under a later one and withdraws it, and leaves the withdrawn version 2 (rev 1.31) |
| SF-13:accounting, SF-13:accounting-version | `marcus` | list; published TENANT version |
| SF-13:ssp-books, SF-13:ssp-book-version | `maya` | list; `US-LIST 2026-H1` |
| SF-13:ssp-calculator, SF-13:ssp-calculator-run | `maya` | form; run over WLD-F-18 |
| SF-13:account-mapping, SF-13:account-mapping-version | `marcus` | list; `AVM-MAP-2026-01` |
| SF-10, SF-10:new, SF-10:detail, SF-10:templates | `maya` | list; new; WLD-B-04 invalid import at `validate`; templates |
| SF-11, SF-11:item | `maya` | queue; a WLD-B-04 item selected with `f.status=in:DISMISSED` |
| SF-16, SF-16:connection, SF-16:sync-run | `nikhil` | list; Salesforce mock connection; latest sync run |
| SF-12, SF-12:request, SF-12:submitted, SF-12:all, SF-12:delegations | `priya`, `maya` | inbox (`priya`); submitted (`maya`); all requests with the J-02 `US-LIST 2026-H2` request selected; delegations (`priya`) |
| SF-24:results | `maya` | `/search?q=SF-ORD`: the first page of every scope (`sf-24-results`); then the command palette over the page with the query "SF-ORD", its records a group a scope (`sf-24-palette`; rev 1.53) |
| X:not-found | `maya` | `/contracts/00000000-0000-4000-8000-000000000000/obligations` |

## 1. Shell composition

### 1.1 Frame

| Field | Value |
|---|---|
| Screen ids | SF-21, SF-23, SF-24 (placements); SF-24:results (RT-95) |
| Roles and permissions | Every authenticated member |
| Purpose | One frame for every route: context, search, notifications, help, identity; no second navigation paradigm (DS-CMP-01, DS-CMP-02) |
| REQ | REQ-UX-001, REQ-UX-002, REQ-PLT-003, REQ-PLT-021; BR-UX-01 to BR-UX-06 |
| Journeys | J-02.7, J-03.8, J-05-ALT-2 (notifications); J-17.1 (read-only chip); J-18.1, J-18.2 (sandbox); J-26.1 (palette to a contract) |

Wireframe, 1440 px:

<!-- WF:shell-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Global banner region: at most one banner (DS-CMP-29), for example the sandbox banner             |
| Work              |--------------------------------------------------------------------------------------------------|
| |* Home           | main (--bg-canvas): skip link target; page h1; route tabs; regions                               |
|    Contracts      |                                                                                                  |
|    Schedules      |                                                                                                  |
|    Close          |                                                                                                  |
|    Journals       |                                                                                                  |
|    Reports        |                                                      +- Explain (docked at >= 1440 px, 440 px) -+|
| ----------------  |                                                      | content reflows; Esc closes              ||
| Govern            |                                                      +------------------------------------------+|
|    Approvals    3 |                                                                                                  |
|    Policies       |                                                 Toasts: bottom inline-end corner (DS-CMP-22)     |
|    Data           |                                                                                                  |
| Settings          |                                                                                                  |
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:shell-1440 -->

Wireframe, 1280 px:

<!-- WF:shell-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Global banner region                                                                              |
| *H |---------------------------------------------------------------------------------------------------|
| Ct | main: rail collapsed by default (DS-SP-04); Explain opens as a non-modal overlay drawer           |
| Sc |                                                                                                   |
| Cl |                                                                                                   |
| Jn |                                                                                                   |
| Rp |                                                                                                   |
| -- |                                                                                                   |
| Ap |                                                                                                   |
| Po |                                                                                                   |
| Da |                                                                                                   |
| Se |                                                                                                   |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:shell-1280 -->

| Region | Component | Content |
|---|---|---|
| Top bar | DS-CMP-01 | Start to end: context pill (SF-23, DS-CMP-03); search trigger (SF-24); flexible space; sandbox indicator (sandbox tenants); "Read-only access" chip (SCR-PERM-06); "Ask about revenue" ghost icon button with the Sparkle icon, rendered when `GET /me` returns `tenant_settings.ai_enabled = true` (04 API-S-Me) and the user holds `ai.use` (SF-28; DS-CMP-01 item 6; OQ-S-11); Notifications bell (SF-21); Help menu; user menu |
| Rail | DS-CMP-02 | SCR-IA-01 |
| Global banner region | DS-CMP-29 | At most one banner: sandbox (SCR-ST-11), offline ("API unreachable. Changes are not being saved."), maintenance |
| `main` | none | The route's page; `h1` receives focus on route change (DS-CMP-01) |
| Explain dock | DS-CMP-15 | §6 |
| Toast region | DS-CMP-22 | Outcomes of commands |

States: normal; sandbox (warning chip "Sandbox: <tenant name>", 2 px `--warning-solid` top line, global banner); session expiring (modal "Your session ends in 2 minutes." with "Stay signed in" primary and "Sign out"); offline (banner). Keyboard: DS-CMP-01 shortcuts. Test hooks: `getByRole("navigation", {name: "Primary"})`, `getByRole("group", {name: "Accounting context"})`, `getByRole("button", {name: /^Notifications/})`, `getByRole("button", {name: "Ask about revenue"})`, `getByText("Read-only access")`. Light and dark: surfaces `--bg-surface` with hairlines in both themes; the sandbox top line uses `--warning-solid`, which always sits beside the chip label (C76 note). Accessibility: DS-A11Y-09 landmarks; skip link first.

### 1.2 SF-21 Notifications (placement)

- Component DS-CMP-05 exactly, E-69 kinds only.
- Bindings: badge `GET /me/notifications?unread=true&count=true&limit=1` (header `X-Erev-Total-Count`); panel tabs "Unread" `GET /me/notifications?unread=true&limit=50` and "All" `GET /me/notifications?limit=50`; selecting an item navigates to `link_path` (SCR-IA-06) and sends `POST /me/notifications/{id}/read`.
- Refresh: the badge refetches every 60 s while `document.visibilityState` is `visible`, after every successful command and on window focus. [J] No push channel exists in 1.0; a minute is short enough for approval hand-offs.
- "Mark all as read" (DS-CMP-05): `POST /me/notifications/read-all` with `before` = the `created_at` of the newest notification loaded in the panel (04 API-R-03, §16.12); on success the badge and both tabs refetch (DESIGN_SYSTEM:OQ-07 resolved by D-76). Test hook `getByRole("button", {name: "Mark all as read"})`.
- Test hooks: panel `getByRole("dialog", {name: "Notifications"})`; items are links named by the notification title, for example "Approval needed: SSP book version US-LIST 2026-H2" (NTF-01).

### 1.3 SF-23 Context pill, tenant switcher and read-only chip

Context dimensions per screen. "Used": the segment is interactive and its value reaches every read; "Disabled": `aria-disabled="true"` with the tooltip "Not used on this page" (DS-CMP-03); "All": the entity segment offers "All entities (<n>)".

| Screen ids | Entity | Period | Book |
|---|---|---|---|
| SF-01 | Used, All | Used | Used |
| SF-02 | Used, All | Used (drives `as_of`) | Used |
| SF-03 family, SF-07 | Used (selects the balances cell, §4.1) | Used | Used |
| SF-10 family | Used, All (filter default) | Disabled | Disabled |
| SF-11 family | Used, All | Used (default of the Period filter chip) | Disabled |
| SF-12 family | Disabled (rev 1.20; ruling R-112 (h): the three lists filter by the Entity chip `f.entity`, never by the pill's entity, §15.3 — as the Home table "Waiting for you", §2.5) | Disabled | Disabled |
| SF-13 family, SF-15 reference data, SF-16 family, SF-24:results | Disabled | Disabled | Disabled |

- Tenant switcher: user menu item "Switch tenant" (rendered when `GET /me` lists more than one membership) opens a listbox popover (APG Listbox) of memberships: tenant display name, kind chip "Sandbox" for `sandbox` tenants, the current tenant marked "Current". Selecting sends `POST /session/tenant`, clears the query cache, navigates to `/home` with BR-UX-01 defaults and announces "Switched to <tenant name>".
- Read-only chip: SCR-PERM-06. Tooltip: "Your roles let you view records and run reports. Ask a workspace administrator for command permissions."

### 1.4 SF-24 Command palette and SF-24:results

- Component DS-CMP-04. Record search uses `GET /search?q=<query>&limit=8` (04 API-R-55, API-S-SearchResult), with `scope=<scope>` when a scope chip other than "All" is selected; scopes are the E-120 literals `contracts`, `customers`, `invoices`, `obligations`, `journals`. Items carry `{id, primary, secondary, status, href}`. `href` is an API link (04 B3-D11), so the client builds each route from the scope and id: contracts `/contracts/<id>/obligations`; customers `/settings/customers/<id>`; invoices `/contracts/<contract id>/billing`, with the contract id taken from `href` (`/api/v1/contracts/{contract id}`); obligations `/contracts/<contract_id>/obligations/<id>`, after `GET /obligations/{id}` returns `contract_id`; journals `/journals/runs/<id>`. Pages and commands are a static catalogue filtered on the client.
- Result rows: primary text `primary`, secondary text `secondary`, and a trailing status chip from `status` when it is not null (words of §0.8 and SCREENS_B §0.4). By scope (04 API-S-SearchResult): Contracts external id · customer name, chip E-17; Customers code · name; Invoices invoice number · contract external id; Obligations "<contract external id> · <obligation key>" · product name, chip E-22; Journals run number · period key and entity code, chip E-34.
- Commands (rendered only with the permission named): "Go to <rail item>" (all ten); "Switch entity…", "Switch period…", "Switch book…"; "Theme: System", "Theme: Light", "Theme: Dark"; "Density: Comfortable", "Density: Compact"; "Keyboard shortcuts"; "New contract…" (`contract.create`); "New import…" (`import.upload`); "Review a contract document…" (`ai.use` and AI enabled); "Open close cockpit for <entity> <period label>" (`contract.read`); "Run journals for <period label>…" (`journal.run`, opens the SF-06 run form); the legacy aliases of §0.10.
- "Show all results" opens SF-24:results `/search?q=<query>`.

SF-24:results: `h1` "Search results for "<query>""; a FilterBar with one chip field "Scope" (values as above); one static table per scope (DS-CMP-10 static variant, at most 25 rows each, "Show more <scope label>" button fetching the next page with `GET /search?q=<query>&scope=<scope>&limit=25&cursor=<next_cursor>`). The first load without a scope reads `results[]` of `GET /search?q=<query>&limit=25`.

| Scope | Columns (header, field, format, alignment) |
|---|---|
| Contracts | Contract (`primary`, mono link, start); Customer (`secondary`, start); Status (`status` chip, start) |
| Customers | Code (`primary`, mono link, start); Customer (`secondary`, start) |
| Invoices | Invoice (`primary`, mono link to the contract's Billing tab, start); Contract (`secondary`, mono, start) |
| Obligations | Obligation (`primary`, mono link, start); Product (`secondary`, start); Status (`status` chip, start) |
| Journals | Run (`primary`, mono link, start); Period and entity (`secondary`, mono, start); State (`status` chip, start) |

Further result columns (inception date, country, issue date, invoice amount) are deferred to later: 04 API-S-SearchResult returns no other fields.

States: empty query "Type at least 2 characters to search."; no results `No matches for "<query>". Search by contract number, customer, invoice number or order number.` (DS-CMP-04); error "Search is unavailable. Pages and commands still work." Test hooks: `getByRole("dialog", {name: "Command palette"})`, `getByRole("combobox")`, options by name; results tables by caption "Contracts", "Customers", "Invoices", "Obligations", "Journals".

**As bound to API-R-55 of 1.0 (rev 1.53, CTR-28).** The palette searches records for a holder of `contract.read` for any entity, the permission of the route (04 API-R-55): from two characters with a letter or digit, 120 ms after the last key, `GET /search?q=<text>&limit=8`, the text trimmed and cut to the 200 characters the route takes. A found record is a row of its scope's group; the groups stand in E-120 order ahead of the row "Show all results", of "Pages" and of "Commands", and a scope that found nothing has no group. A row reads `primary` and `secondary` with the beginning of each word a term matches in weight 600 — the API's rule repeated for emphasis alone (04 §16.13 "Matching and order"); pages and commands keep their substring mark — and the chip of `status`: E-17 for a contract, E-22 for an obligation, whose literals `UNSATISFIED` and `PARTIALLY_SATISFIED` show none (§0.8), E-34 for a journal run. A screen reader reads a record as "<primary>, <secondary>, <status word>". The scope chips are a radio group "Search scope" that takes one Tab stop; Left and Right move and choose, and a press leaves the focus in the input. "All" lists every group; a scope of records lists that scope alone and sends `scope=<scope>`; "Pages" and "Commands" list those alone and search nothing. "Show all results" stands under the records while one is listed, stays in view at the lower edge of the list while the records above it scroll, and opens `/search?q=<text>`, with `&f.scope=is:<scope>` under a scope chip of records. A record is listed only when the route it opens is built, and "Show all results" only when RT-95 is (header XR-14). A record opens its route without the context parameters of the page beneath; `Mod Enter`, and a press with Command or Control, open the route of a record, of a page and of "Show all results" in a new tab and leave the palette open.

Loading, and the active option (rev 1.53). While an answer is on its way the rows of the answer before stay and the running mark of DS-CMP-20 stands at the end of the input; none of those rows is the active option, because the member did not ask for them with the text as it stands. A page or a command the text matches is the active option at once and stays it when the records arrive; with none, the first record of the answer becomes it. Enter with no active option while an answer is on its way waits for that answer and then opens its first option. The route of an obligation needs its contract: `GET /obligations/{id}` is read when the obligation's row becomes the active one, Enter and `Mod Enter` wait for that read, and a read that fails says "Could not open <primary>. Try again.". Whatever an Enter waited for opens only while the palette is still open over the page it was opened on; typing, another chip and Esc end the wait (dev-guide DG-FE-03 (3)).

States of the palette (rev 1.53). Under a scope chip of records a text that is not searched reads "Type at least 2 characters to search."; under "All" such a text lists the pages and commands it matches. Once a search has answered nothing and no page or command matches, the palette reads the no-results sentence above; where no search was made — one character, no letter or digit, "Pages", "Commands" — it reads "No pages or commands match "<query>".". A search that fails reads the error sentence above the pages and commands the text matches. Without `contract.read` no search is sent and nothing is said of records: the chips are "All", "Pages" and "Commands" and the input reads "Search pages and commands"; a 403 of the route — a session whose access changed under it — lists no record and shows no error line. A text the route refuses as holding no term (422: the database alone says what a letter is) finds nothing. Not bound: the "recent records" of DS-CMP-04 on an empty query, which no API serves — the palette lists pages and commands there — and the commands of the third bullet above beyond "Go to <rail item>", the Theme and the Density commands.

SF-24:results as bound (rev 1.53). The route asks `contract.read` for any entity through the access module and shows the access-limited screen without it (§0.6: "You do not have access to search"); nothing is read then. The quick search "Search records" of the FilterBar holds `q`, written 250 ms after the last key (DS-CMP-13), and the chip field "Scope" holds `f.scope=is:<scope>`, under which the read sends `scope` and the page shows that scope's table alone. The `h1` reads "Search results" while the URL names no text. A text the route would refuse — fewer than two characters after trimming, or no letter or digit — is not sent, and the page reads "Type at least 2 characters to search.". A table stands for each scope that found something, in E-120 order, and none found reads the no-results sentence. "Show more <scope label>" ("Show more contracts") adds the next 25 rows under those shown and leaves when the scope's cursor is null. A first read that fails reads "Could not load the search results" with "Retry"; a further page that fails reads "Could not load more results" under its table with "Retry", and the rows read before stay. An obligation's link needs its contract: one `GET /obligations/{id}` for each obligation row shown, kept for the session; the row reads as text until its read has answered. Links are drawn for built routes and carry no context parameters; the context pill is not used (§1.3). Test hooks: `SF-24-results-page`, `SF-24-filters`, `SF-24-results-<scope>`, `SF-24-too-short`, `SF-24-no-matches`; in the palette `SF-24-searching` (the running mark) and `getByRole("radiogroup", {name: "Search scope"})`.

## 2. SF-01 Home

### 2.1 Summary

| Field | Value |
|---|---|
| Screen id and route | SF-01, `/home` (RT-07) |
| Roles and permissions | Every member. Figures need `contract.read`; the approvals queue needs any approval permission; the exceptions queue needs `exception.resolve` or `contract.read`; recent activity needs `audit.read` (otherwise the "Recently viewed" variant renders). Rev 1.34 (SCR-PERM-02): the figures and the exceptions queue ask for the context entity, the approvals queue for any entity, and recent activity for all entities; a holder of `audit.read` for named entities, and a member whose read of the audit events is refused with 403, sees the "Recently viewed" variant |
| Purpose | For the context entity, period and book: revenue against the prior period, contract liability, RPO, close status, open exceptions and pending approvals, each drilling to the screen that owns it; the user's queues; recent activity; favourites (PRD SF-01) |
| REQ | REQ-RPT-016, REQ-UX-016, REQ-UX-017, REQ-UX-019 (LTM-O1) |
| Journeys | J-16.1 (Revenue figure drills to SF-04 and totals match); J-17.1 (auditor lands on Home with the read-only chip); J-18.2 (scenario tenant banner); J-24 (tour start, SCREENS_B) |

### 2.2 Wireframes

1440 px:

<!-- WF:home-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Home                                                                                             |
| Work              | +- (i) Coming from eRev desktop ------------------------------------------------------------+    |
| |* Home           | | Your workspace uses the legacy-parity preset. [Open the transition map] [Download ..]  [x] |   |
|    Contracts      | +-------------------------------------------------------------------------------------------+    |
|    Schedules      | Key figures (USD, ASC 606, Sep 2026)                                                             |
|    Close          | +------------------+------------------+------------------+------------------+------------------+ |
|    Journals       | | Revenue          | Contract liabilit| RPO              | Pending approvals| Open exceptions  | |
|    Reports        | | 1,284,310.55     | 3,902,114.20     | 11,406,882.13    | 3                | 4                | |
| ----------------  | | spark +3.1%      | Opening 3,861,.. | Within 12 mo ..  | Oldest 12 Sep    | 3 blocking       | |
| Govern            | +------------------+------------------+------------------+------------------+------------------+ |
|    Approvals    3 |                                                                                                  |
|    Policies       | +- Waiting for you (3) ---------------------------------+ +- Close status ---------------------+ |
|    Data           | | Request                        Type                Cur| | (Period open) Sep 2026 . AVM-US    | |
|                   | | Contract activation BG-AVM-0020 Contract activation US| | Pending approvals ........... 3    | |
|                   | | Manual adjustment BG-AVM-0022  Manual adjustment   USD| | Open exceptions ............. 4    | |
|                   | | Judgement record BG-AVM-0023   Judgement record    —  | | Open holds .................. 1    | |
|                   | | [View all approvals]                                  | | Unreviewed judgements ....... 1    | |
|                   | +-------------------------------------------------------+ | [Open close cockpit]               | |
|                   |                                                           +------------------------------------+ |
|                   | +- Open exceptions (4) ---------------------------------+                                        |
|                   | | (Blocking) Over-delivery        PROGRESS_OVER_DELIVERY| +- Revenue by period ----------------+ |
|                   | | (Blocking) Over-delivery        PROGRESS_OVER_DELIVERY| | [Chart|Table]           Month      | |
|                   | | (Blocking) VC reassessment      VC_REASSESSMENT_MISSIN| |  ## ## ## ## ## ## .. .. .. .. //  | |
|                   | | [View all exceptions]                                 | |  ## ## ## ## ## ## .. .. .. .. //  | |
|                   | +-------------------------------------------------------+ | Apr .. .. .. Aug Sep Oct .. Mar Awa| |
|                   |                                                           +------------------------------------+ |
|                   | +- Recent activity -------------------------------------+                                        |
|                   | | 12 Sep 2026                                           | +- Favourites -----------------------+ |
|                   | |  o Maya Chen submitted Contract activation BG-AVM-0020| | SF-ORD-10001 . Pellworth Logistics | |
|                   | |  o Maya Chen uploaded avm-us-progress-2026-09-invalid.| | Contract balance rollforward       | |
|                   | | [Load older activity]                                 | | Saved view: Largest value          | |
| Settings          | +-------------------------------------------------------+ +------------------------------------+ |
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:home-1440 -->

1280 px (the two columns keep their 7 : 5 ratio; "Recent activity" and "Favourites" move below both columns at full width):

<!-- WF:home-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Home                                                                                              |
| *H | Key figures (USD, ASC 606, Sep 2026)                                                              |
| Ct | +------------------+------------------+------------------+------------------+------------------+  |
| Sc | | Revenue          | Contract liabilit| RPO              | Pending approvals| Open exceptions  |  |
| Cl | | 1,284,310.55     | 3,902,114.20     | 11,406,882.13    | 3                | 4                |  |
| Jn | +------------------+------------------+------------------+------------------+------------------+  |
| Rp |                                                                                                   |
| -- | +- Waiting for you (3) ----------------------------------+ +- Close status ---------------------+ |
| Ap | | Request   Type   Cur  Amount  Preparer                 | | (Period open) Sep 2026             | |
| Po | | Contract activation BG-AVM-0020 ..                     | | Pending approvals ....... 3        | |
| Da | | Manual adjustment BG-AVM-0022 ..                       | | Open exceptions ......... 4        | |
|    | | Judgement record BG-AVM-0023 ..                        | | [Open close cockpit]               | |
|    | +--------------------------------------------------------+ +------------------------------------+ |
|    |                                                                                                   |
|    | +- Open exceptions (4) ----------------------------------+ +- Revenue by period ----------------+ |
|    | | (Blocking) PROGRESS_OVER_DELIVERY ..                   | | ## ## ## ## ## ## .. .. //         | |
|    | | (Blocking) VC_REASSESSMENT_MISSING ..                  | +------------------------------------+ |
|    | +--------------------------------------------------------+                                        |
|    |                                                                                                   |
| Se | Recent activity and Favourites follow at full width                                               |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:home-1280 -->

### 2.3 Regions and components

| Region | Component | Content |
|---|---|---|
| Page header | none | `h1` "Home"; no primary action. [J] Home is a reading surface; actions live on the records |
| Demo tour banner | DS-CMP-29 info banner, dismissible | SF-25 entry on demo workspaces, §2.4 (SCREENS_B:OQ-B-29) |
| Legacy panel | DS-CMP-29 info banner, dismissible | SCR-LTH-O1, §2.4 |
| Key figures | DS-CMP-06 KPI strip (standalone, no record header) | Five cells: Revenue, Contract liability, RPO, Pending approvals, Open exceptions. Heading "Key figures (<currency>, <book label>, <period label>)" |
| Waiting for you | Panel with DS-CMP-10 static table | Up to 8 pending requests assigned to the user (API-R-09 `assigned_to_me`), across entities, oldest first. The Pending approvals key figure counts requests the user can decide in the context entity, so the two may differ by entity scope and by the decision checks the assigned clause does not apply (rev 1.4; D-90a QA-L9-4; §2.5) |
| Open exceptions | Panel with DS-CMP-10 static table | Up to 8 open exception items in the context entity, blocking first, then newest (04 API-R-44 `sort=severity`) |
| Recent activity | Panel with DS-CMP-12 (audit variant, compact, read-only) | 10 latest audit events from the start of the context period; "Recently viewed" variant for users without `audit.read` for all entities (rev 1.34) |
| Close status | Panel with a definition list and DS-CMP-19 chip | Period state and non-zero blocker counts |
| Revenue by period | DS-CMP-14 with DS-CH-01 | Context period − 5 to context period + 6, Month granularity, plus "Awaiting trigger" |
| Favourites | Panel with a flat list | Pinned contracts, reports and saved views (SCR-IA-08) |

Layout: full-bleed (DS-SP-05). At ≥ 1280 px two columns, 7 : 5 of the content width, `--stack-gap` between regions. Panels are `--bg-surface` with `--border-default` outlines on `--bg-canvas`; they differ in content and height, so the page never reads as a card grid (DS-AP-02).

### 2.4 Demo tour banner (SF-25) and legacy panel (SCR-LTH-O1)

**Demo tour banner** (PRD J-24.1, J-24.2; SCREENS_B §11.2; SCREENS_B:OQ-B-29 resolved by D-76).

- Rendered below the page header and above the legacy panel when all of these hold: the active workspace is a demo workspace (the `GET /me` membership whose `membership_id` equals `active_membership_id` has `tenant.is_demo = true`); `preferences.tour_completed` is null or names a `variant` other than `demo`; and the user has not dismissed the banner in this browser session.
- Copy: info banner (DS-CMP-29) without a title, message "This is a demo workspace with sample data. The tour shows six places where eRev Cloud keeps revenue auditable."; actions "Take the tour" and "Dismiss".
- "Take the tour" sets `tour=demo` (SCR-URL-14) and opens SF-25 at stop 1 (J-24.2). "Dismiss" hides the banner and stores `sessionStorage` key `erev.dismissed.demo-tour.<tenant id>`. Finishing the tour writes `PATCH /me/preferences` `{tour_completed: {variant: "demo", completed_at}}` (04 §16.12; SCREENS_B §11.2), after which the banner no longer renders.

**Legacy panel** (SCR-LTH-O1).

- Rendered when the published TENANT accounting policy version (`GET /policies?category=ACCOUNTING_POLICY&scope=TENANT&status=PUBLISHED&limit=1`) has `preset_code = "LEGACY_PARITY"` and the user has not dismissed it.
- Copy: title "Coming from eRev desktop"; message "Your workspace uses the legacy-parity preset. See where each desktop button lives now, or download the four legacy templates."; actions "Open the transition map" (SF-26) and "Download legacy templates" (SF-10:templates `?f.family=is:LEGACY_V1`); dismiss button "Dismiss".
- Dismissal is stored in `localStorage` key `erev.dismissed.legacy-panel.<tenant id>`. [J] A per-device dismissal is enough for an orientation panel; nothing about it is evidence.

### 2.5 Data bindings

| Region | Endpoint | Parameters | Fields used |
|---|---|---|---|
| Key figures, Close status, Revenue by period | `GET /dashboard/home` (04 API-R-50, API-S-DashboardHome) | `entity` (repeatable; omitted for All entities), `period`, `book`. The API picks the currency: the entity's functional currency for one entity, the tenant reporting currency across entities (`context.currency`) | `context.currency`, `context.known_at`; `revenue.current`, `revenue.prior`, `revenue.change_ratio`, `revenue.trend[]`; `contract_liability.closing`, `contract_liability.opening`; `rpo.total`, `rpo.within_12_months`; `pending_approvals.count`, `pending_approvals.oldest_submitted_at`; `open_exceptions.total`, `.blocking`, `.warning`, `.info`; `close.state`, `close.blockers`, `close.close_run`; `revenue_chart.periods[]`, `revenue_chart.awaiting_trigger`, `revenue_chart.pending_trigger_count` |
| Demo tour banner | `GET /me` (04 API-R-03, API-S-Me) | none | `active_membership_id`, `memberships[].membership_id`, `memberships[].tenant.is_demo`, `preferences.tour_completed` |
| Waiting for you | `GET /approvals` (API-R-09) | `assigned_to_me=true`, `status=PENDING`, `sort=submitted_at` (04 API-R-09 sort keys), `limit=8`, `count=true`. No `entity` (rev 1.4; D-90a QA-L9-4; L7-2-Q-22): the table lists the pending requests assigned to the user (the API-R-09 assigned clause), across entities, because an `entity` filter excludes tenant-wide requests (`ROLE_CHANGE`, `ROLE_ASSIGNMENT`, `SOD_EXCEPTION`, `SUPPORT_GRANT`, `IMPORT_COMMIT`, configuration versions). The Pending approvals key figure counts requests the user can decide in the context entity (04 API-S-DashboardHome `pending_approvals`; `can_decide`, including required-role and delegator exclusions that the assigned clause does not apply), so the two may differ by entity scope and by those decision checks. Post-rc: entity scoping that keeps tenant-wide requests listed, together with the SF-12 filters | `id`, `summary`, `subject.type`, `amount`, `preparer.display_name`, `submitted_at`, `current_step_no`, `steps[].name` |
| Open exceptions | `GET /exceptions` (API-R-44) | `status=OPEN`, `status=IN_PROGRESS`, `entity`, `sort=severity` (04 API-R-44: `BLOCKING`, `WARNING`, `INFO`, then `created_at` descending), `limit=8`, `count=true` | `id`, `title`, `code`, `severity`, `contract_id` resolved to `business_key`, `created_at` |
| Recent activity | `GET /audit-events` (API-R-10) | `from` = context period start (entity time zone, as UTC), `limit=10` | `occurred_at`, `actor_kind`, `actor_id` display name, `action`, `object_type`, `object_id`, `outcome` |
| Recently viewed (variant) | `GET /contracts` (API-R-28) | `quick_list=RECENTLY_VIEWED` (04 E-111), `limit=10` | `id`, `external_id`, `customer.name`, `status` |
| Favourites | `GET /saved-views` (API-R-16) | none; client keeps rows with `is_favourite = true` | `id`, `screen_code`, `config.path`, `config.label`, `config.target` |

**Revenue of the entity that performs (rev 1.41; supervisor rulings R-78 (d) and R-121 (g), and the supervisor's ruling of 2026-10-01 on the lane's finding on the Home; SCREENS_B RPT-01 rev 1.69).** `revenue` and `revenue_chart` are read from the RPT-01 population of the context entities: the obligations those entities PERFORM, with the revenue their books hold. The API reads the three figures that come from report datasets — revenue, contract liability and RPO — for the context as the reports' jobs read them, so a reader whose roles name one entity and a reader of every entity get the same figures for the same context; an obligation another entity performs has its schedule lines in that entity's books, and a read under the caller's own scope refused the whole Home by rule S15-R-01 for a reader of the contracting entity alone. Consequence: the Home of an entity that performs an obligation in another currency than its functional currency is refused as every context that holds another currency is — `GET /dashboard/home` answers 422 `validation-failed` on `entity`, "Key figures show amounts in <ISO> only. Contracts in other currencies are not converted." — for the whole request, so the key figures, the close status and the chart show their error state (§2.7); WLD-K-04 is such a case, AVM-US performing an obligation of a GBP contract of AVM-UK. Until rev 1.41 the population was read by the contracting entity: that Home stated 0.00 for revenue its entity's books hold, and the contracting entity's Home stated revenue its books do not hold (measured in WLD-K-04 for April 2026: AVM-UK 9,647.75 where its books hold 4,857.14).

### 2.6 Key figures and tables

KPI cells (values are buttons that drill; they are portfolio aggregates without an `/explain` node, so the drilled screen provides Explain on its cells) [J]:

| Cell label | Value | Secondary line | Drill target |
|---|---|---|---|
| Revenue | `revenue.current` (DS-FMT-04 digits; the heading carries the code) with a DS-CH-04 sparkline of `revenue.trend` | "<prior period label>: <revenue.prior> · <change>" where change is `revenue.change_ratio` as a percent with one decimal, `+` for increases and the tenant negative style for decreases (DS-FMT-09, DS-FMT-31); "No prior period" when `prior` is null | SF-04 `/schedules?entity&period&book` (J-16.1) |
| Contract liability | `contract_liability.closing` | "Opening <contract_liability.opening>" | SF-08:report `/reports/contract_balance_rollforward?entity&period&book` |
| RPO | `rpo.total` | "Within 12 months <rpo.within_12_months>" | SF-08:report `/reports/rpo?entity&period&book` |
| Pending approvals | `pending_approvals.count` (DS-FMT-21) | "Oldest submitted <DS-FMT-16 date>"; "None waiting" when 0 | SF-12 `/approvals?entity` |
| Open exceptions | `open_exceptions.total` (DS-FMT-21; the client never adds the severity counts, 04 API-S-DashboardHome) | "<open_exceptions.blocking> blocking" | SF-11 `/data/exceptions?entity&f.status=in:OPEN,IN_PROGRESS` (rev 1.37: the figure is the count of that list — both read one attribution of an item to an entity, 04 rev 1.206) |

Waiting for you (static table, caption "Waiting for you"):

| # | Header | Field | Format | Alignment | Sort and filter | Visible |
|---|---|---|---|---|---|---|
| 1 | Request | `summary`, link to `/approvals/requests/<id>` | text link | start | fixed order: `submitted_at` ascending | yes |
| 2 | Type | `subject.type` label (§15.3 table) | text | start | none | yes |
| 3 | Currency | `amount.currency` | mono, "—" when null | start | none | yes |
| 4 | Amount | `amount.amount` | DS-FMT-04; DS-FMT-08 when null | end | none | yes |
| 5 | Preparer | `preparer.display_name` | text | start | none | yes |
| 6 | Submitted | `submitted_at` | DS-FMT-16 date part | start | none | yes |

Open exceptions (static table, caption "Open exceptions"):

| # | Header | Field | Format | Alignment | Sort and filter | Visible |
|---|---|---|---|---|---|---|
| 1 | Severity | `severity` | chip (§0.8) | start | fixed order: `BLOCKING`, `WARNING`, `INFO`, then `created_at` descending (04 API-R-44) | yes |
| 2 | Exception | `title`, link to `/data/exceptions/<id>` | text link | start | none | yes |
| 3 | Code | `code` | mono | start | none | yes |
| 4 | Record | `business_key` or the contract external id | mono | start | none | yes |
| 5 | Created | `created_at` | DS-FMT-16 date part | start | none | yes |

Close status definition list: chip for `close.state` (Period open, Soft close, Locked, Reopened, Permanently locked); then one row per non-zero `close.blockers` key, in this order and with these labels: `approvals_pending` "Pending approvals"; `exceptions_open` "Exceptions holding the lock" (rev 1.37; "Open exceptions" before), a link to SF-11 `/data/exceptions?blocking=<close.id>`; `holds_open` "Open holds"; `judgements_unreviewed` "Unreviewed judgements"; `unmapped_products` "Products without mapping"; `interface_failures` "Interface failures"; `jobs_failed` "Failed jobs"; `groups_dirty` "Contracts awaiting recalculation"; `batches_unexported` "Journal batches not exported"; `batches_unacknowledged` "Journal batches not acknowledged"; `reconciliations_unsigned` "Reconciliations not signed"; `manual_adjustments_pending` "Pending manual adjustments". When every count is 0: "No blockers." Action link "Open close cockpit" → `/close/<entity>/<book>/<period>` (hidden for All entities; the panel then reads "Select an entity to see its close status.").

Rev 1.37 (item CLO-QUARANTINE-READ-1; 04 §16.13 and T-IMP-05 "An item that names no entity", rev 1.206; supervisor ruling R-121 (i)). The page states two figures about exceptions, and they are two things by definition. The key figure "Open exceptions" is every open item of the context entity — any severity, any period — and equals the list behind its link. The close row counts the items that hold the lock of the context period (`close.blockers.exceptions_open`): open, blocking or warning, of this period or of none. It is therefore labelled "Exceptions holding the lock" and links to the list it counts, the queue under `blocking` with `close.id`, the period's id. Both take an item as the entity's by one rule, so every item of the close row is among the open exceptions; a member who may not read an item of an import is told the row's count and is not shown that item. Until this revision both read "Open exceptions", the key figure took the item's own entity and the row the gates' rule: one page stated two counts under one label.

Revenue by period: DS-CH-01 exactly; subtitle "Revenue by period · <currency> · <book label>"; drill per segment to SF-04 with `period` and `f.state`.

Recent activity item copy: "<actor> <verb> <object label>" where the verb comes from catalogue key `audit.action.<action>` (for example `contract.book` "booked", `import_upload.submit` "submitted", `approval_request.approve` "approved"); an unknown action renders the raw `action` in mono. Timestamps DS-FMT-17 with `data-volatile`.

### 2.7 States

| Region | Loading | Empty (copy and next step) | Error | No permission | Stale |
|---|---|---|---|---|---|
| Key figures | SCR-ST-01, labels visible | Tenant with no computed contracts: cells show 0.00 and 0 from the API; below the strip, "No contracts yet. Import contracts or connect a source to see figures here." with link "Go to Data" | SCR-ST-05 "Could not load key figures" | Cells whose read permission is missing are not rendered | When `GET /dashboard/home` returns `context.known_at` earlier than the latest close run start, info line "Figures are being recalculated." [A] |
| Waiting for you | 3 skeleton rows | Approver: title "No requests waiting for you", description "Requests you can approve appear here, oldest first."; user without approval permissions: title "You have no approval permissions", description "Items you can view appear in reports and registers." (J-17.7 copy) | SCR-ST-05 | none | none |
| Open exceptions | 3 skeleton rows | Title "No open exceptions", description "Rows that fail validation during imports and integrations, and close blockers, appear here." | SCR-ST-05 | none | none |
| Recent activity | 3 skeleton events | "No activity yet. Changes, approvals and calculations appear here." (DS-CMP-12) | SCR-ST-05; a 403 renders the "Recently viewed" variant instead (rev 1.34) | Variant "Recently viewed": empty "Contracts you open appear here." | none |
| Close status | skeleton list | none (a period always exists) | SCR-ST-05 | not rendered | none |
| Revenue by period | DS-CMP-14 static skeleton | "No revenue scheduled for this range." | retry | not rendered | none |
| Favourites | 3 skeleton rows | Title "Nothing pinned yet", description "Pin contracts, reports and saved views from their page menus." | retry | none | none |

### 2.8 Interactions, keyboard and copy

| Element | Interaction | Keyboard |
|---|---|---|
| KPI value | Selecting navigates to the drill target with the same context | Enter |
| Table rows | The first-column link opens the record | Tab to link, Enter |
| Legacy panel | "Dismiss" hides it and announces "Panel dismissed" | Enter |
| Favourite row | Link opens `config.path`; ghost icon button "Unpin <label>" (Minus) sends `PATCH /saved-views/{id}` with `is_favourite = false` | Tab, Enter |
| Chart | DS-CMP-14 keyboard | Left, Right, Enter |

Copy keys: `home.page.title` "Home"; `home.kpi.heading` "Key figures ({currency}, {book}, {period})"; `home.kpi.revenue` "Revenue"; `home.kpi.contractLiability` "Contract liability"; `home.kpi.rpo` "RPO"; `home.kpi.pendingApprovals` "Pending approvals"; `home.kpi.openExceptions` "Open exceptions"; `home.queue.approvals.title` "Waiting for you"; `home.queue.approvals.viewAll` "View all approvals"; `home.queue.exceptions.title` "Open exceptions"; `home.queue.exceptions.viewAll` "View all exceptions"; `home.activity.title` "Recent activity"; `home.activity.recentlyViewed` "Recently viewed"; `home.close.title` "Close status"; `home.close.open` "Open close cockpit"; `home.chart.title` "Revenue by period"; `home.favourites.title` "Favourites".

### 2.9 Sample world

WLD-T-01, context AVM-US, Sep 2026, ASC606 at seed:
- "Waiting for you" for `priya`: WLD-B-01 contract activation `BG-AVM-0020`, USD 146,000.00, preparer Maya Chen; WLD-B-02 manual adjustment `BG-AVM-0022`, USD 2,400.00, preparer Maya Chen; WLD-B-03 judgement record `PRINCIPAL_AGENT` on `BG-AVM-0023`, no amount, preparer Maya Chen. rc note (rev 1.4; D-90a): WLD-B-02 is not seeded in the rc because manual adjustments (CLO-12) and their seed (DMO-4) are post-rc (L5-4-Q-7), so Waiting for you lists WLD-B-01 and WLD-B-03.
- "Open exceptions" for `maya`: two items `PROGRESS_OVER_DELIVERY` (severity Blocking, source `IMPORT`, WLD-B-04) and `VC_REASSESSMENT_MISSING` on `BG-AVM-0024` (Blocking, source `CLOSE`, WLD-B-06).
- Close status: Period open; the blocker rows include "Pending approvals", "Open exceptions", "Open holds" (WLD-B-05) and "Unreviewed judgements" (WLD-B-03).
- Figures are not asserted (background contracts, WLD-R-06). Asserted consistency: the Revenue value equals the SF-04 waterfall total for AVM-US Sep 2026 (J-16.1).
- `robert` (Viewer): no approvals queue content (empty variant "You have no approval permissions"), "Recently viewed" variant.
- WLD-T-20 (legacy preset, J-01): legacy panel rendered.
- WLD-T-02 Fernhill Software, Inc. (Demo), `robert` before J-24.2: demo tour banner rendered (J-24.1).

### 2.10 Test hooks

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page | `getByRole("heading", {level: 1, name: "Home"})` | `SF-01-page` |
| KPI strip | `getByRole("region", {name: /^Key figures/})` | `SF-01-kpi-strip` |
| Revenue value | `getByRole("link", {name: /^Revenue, USD/})` | `SF-01-kpi-revenue` |
| Sparkline | `getByRole("img", {name: /^Recognized revenue/})` | `SF-01-chart-revenue-trend` |
| Queues | tables by caption "Waiting for you", "Open exceptions" | `SF-01-grid-approvals`, `SF-01-grid-exceptions` |
| Close status | `getByRole("region", {name: "Close status"})` | `SF-01-pane-close` |
| Chart | `getByRole("figure", {name: "Revenue by period"})` | `SF-01-chart-revenue` |
| Legacy panel | `getByRole("heading", {name: "Coming from eRev desktop"})` | `SF-01-banner-legacy` |
| Demo tour banner | `getByRole("button", {name: "Take the tour"})` | `SF-25-banner-demo-tour` (the SF-25 hook name of SCREENS_B §11.2) |

### 2.11 Light, dark and accessibility

- Light and dark: KPI values in `--fg-1`; the sparkline uses `--viz-sparkline` (8.59:1 light, 9.39:1 dark); chart colours DS-CH-01 validated in both themes; panel outlines `--border-default` on `--bg-canvas`.
- Accessibility: one `h1`; each panel is a `section` with an `h2` title; KPI strip is a `dl` (DS-CMP-06) whose value links are named "<label>, <currency> <value>"; the sparkline carries the DS-CH-04 accessible name; tables have captions; the chart has a `figure` summary and a Table view.

## 3. SF-02 Contracts list

### 3.1 Summary

| Field | Value |
|---|---|
| Screen id and route | SF-02, `/contracts` (RT-08) |
| Roles and permissions | Read `contract.read`. Actions: "New contract" `contract.create` (ACT-01); "Review a contract document" `ai.use` with `ai.enabled` (ACT-48); "Deal preview" `scenario.use` (ACT-49); "Import contracts" `import.upload` (ACT-15); bulk "Submit for activation" `contract.create` (ACT-02); bulk "Apply hold" `adjustment.create` (ACT-13); "Pin to Home" any member |
| Purpose | Find contracts by filters, saved views and quick lists; enter manual contract creation, AI contract review and deal preview (PRD SF-02) |
| REQ | REQ-CON-017, REQ-CON-018, REQ-UX-009, REQ-UX-016, REQ-UX-017 |
| Journeys | J-01-AC-1 (empty state in a preset tenant); J-03.2 (quick list "Created from integrations this period"); J-19.1 ("Review a contract document"); J-26.1 (locate `BG-AVM-0030`) |

### 3.2 Wireframes

1440 px:

<!-- WF:contracts-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Contracts  1,204 contracts          [Review a contract document] [Deal preview] [*New contract] .|
| Work              | +-----------------------------------------------------------------------------------------------+|
|    Home           | | {All contracts v}              [Transaction|Functional|Reporting] [Columns] [Export v]  ...    |
| |* Contracts      | | [Search contracts_________] (Entity is AVM-US x) (Status is Active x) [+ Filter]  Clear all    |
|    Schedules      | +--+--------------+-------------------+----------+------+-----------+---+------------+----------+|
|    Close          | |[]| Contract     | Customer          | Status   |Entity| Inception |Cur|Transaction | Recogniz.||
|    Journals       | +--+--------------+-------------------+----------+------+-----------+---+------------+----------+|
|    Reports        | |[]| SF-ORD-10001 | Pellworth Logist..| (Active) |AVM-US|01 Jan 2026|USD|  135,000.00|105,055.89||
| ----------------  | |[]| SF-ORD-10002 | Marrowby Health ..| (Active) |AVM-US|01 Jan 2026|USD|  240,000.00| 84,821.92||
| Govern            | |[]|PRJ-CB-2026-01| Castellan Build ..| (Active) |AVM-US|01 Feb 2026|USD|1,000,000.00|600,000.00||
|    Approvals    3 | |[]| SF-ORD-10417 | Orrin Vale Archi..| (Active) |AVM-US|01 Sep 2026|USD|  108,000.00|  2,956.20||
|    Policies       | |[]| SF-ORD-20417 | Kinsley Marrow F..| (Draft)  |AVM-US|01 Sep 2026|USD|  120,000.00|      0.00||
|    Data           | |[]| BG-AVM-0020  | ..                | (Pending approval) ..                                    |
|                   | |  |              |                   |          |      |           |   |  <- columns scroll ->  |
|                   | +--+--------------+-------------------+----------+------+-----------+---+------------+----------+|
| Settings          |   1,204 rows                                                                                     |
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:contracts-1440 -->

1280 px:

<!-- WF:contracts-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Contracts  1,204 contracts                  [Review a contract document] [*New contract] ..       |
| H  | +-----------------------------------------------------------------------------------------------+ |
| *Ct| | {All contracts v}                [Transaction|Functional|Reporting] [Columns] [Export v] ...    |
| Sc | | [Search contracts______] (Entity is AVM-US x) [+ Filter]                                        |
| Cl | +--+--------------+-----------------+----------+------+-----------+---+------------+------------+ |
| Jn | |[]| Contract     | Customer        | Status   |Entity| Inception |Cur|Transaction | Recognized | |
| Rp | +--+--------------+-----------------+----------+------+-----------+---+------------+------------+ |
| -- | |[]| SF-ORD-10001 | Pellworth Log.. | (Active) |AVM-US|01 Jan 2026|USD|  135,000.00| 105,055.89 | |
| Ap | |[]| SF-ORD-10002 | Marrowby Heal.. | (Active) |AVM-US|01 Jan 2026|USD|  240,000.00|  84,821.92 | |
| Po | |  |  first column pinned; other columns scroll inside the grid viewport (DS-SP-07)              ||
| Da | +--+--------------+-----------------+----------+------+-----------+---+------------+------------+ |
| Se |                                                                                                   |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:contracts-1280 -->

### 3.3 Regions and components

| Region | Component | Content |
|---|---|---|
| Page header | none | `h1` "Contracts" with the count "<n> contracts" (DS-FMT-21, from `X-Erev-Total-Count`); secondary buttons "Review a contract document", "Deal preview"; primary "New contract"; overflow menu "Import contracts", "Download Contract Setup template" (legacy preset tenants) |
| Toolbar | DS-CMP-10 toolbar | Saved-view selector; currency view switch (DS-CMP-31); column chooser; export menu (CSV, XLSX); overflow "Reset view" |
| FilterBar | DS-CMP-13 | §3.6 |
| Grid | DS-CMP-10 | §3.5; checkbox column; row-actions column |
| Selection bar | DS-CMP-10 | §3.7 |

### 3.4 Data bindings and quick lists

- Grid: `GET /contracts` (API-R-28) with `entity` (repeatable), `customer`, `status` (repeatable), `on_hold`, `modified_in_period`, `value_min`, `value_max`, `has_exceptions`, `quick_list`, `q`, `sort`, `limit=200`, `cursor`, `count=true`, `as_of`, `book`, `currency_view`.
- Export: `POST /report-runs` with `report_code = "extract_contracts"` and parameters equal to the grid's API filters, then the DS-CMP-24 indicator in the toolbar and a toast with "Download" (`GET /report-runs/{id}/output`) (BR-RPT-01).
- Saved views: `GET /saved-views?screen_code=SF-02`; save `POST /saved-views` with `config = {columns, widths, pinned, sort, filters, currency_view}`; shared views need `is_shared` (tenant sharing permission per DS-CMP-10).
- Quick lists (REQ-CON-017; 04 E-111 `contract_quick_list` literals, OQ-S-04 resolved by D-76) appear first in the saved-view selector under the group "Quick lists"; selecting one sets `view=<literal>` and sends `quick_list=<literal>`:

| Literal | Label | Default sort |
|---|---|---|
| none | All contracts (the default view) | `-updated_at` |
| `RECENTLY_VIEWED` | Recently viewed | server order (most recent first) |
| `ON_HOLD` | On hold | `-updated_at` |
| `LARGEST_VALUE` | Largest value | `-transaction_price` |
| `MODIFIED_THIS_PERIOD` | Modified this period | `-updated_at` |
| `CREATED_MANUALLY` | Created manually | `-updated_at` |
| `CREATED_FROM_INTEGRATIONS_THIS_PERIOD` | Created from integrations this period | `-updated_at` |

### 3.5 Grid columns

Mixed-currency grid (DS-FMT-12): amount headers carry no code and the Currency column precedes the first amount. There is no totals row (OQ-S-14). Sortable columns are exactly the API sort keys.

| # | Header | Field | Format | Alignment | Sort | Filter | Visible by default |
|---|---|---|---|---|---|---|---|
| 1 | Contract | `external_id`, link to SF-03 | Identifier, DS-FMT-23; pinned start | start | no | quick search | yes |
| 2 | Customer | `customer.name`, link to SF-15:customer | text | start | no | Customer | yes |
| 3 | Status | `status`; plus "On hold" chip when `on_hold`; plus outline "Combined" when `combination_group.is_singleton = false` | chips (§0.8) | start | no | Status | yes |
| 4 | Entity | `contracting_entity.code` | mono | start | no | Entity | yes |
| 5 | Inception date | `inception_date` | DS-FMT-16 | start | `inception_date` | none | yes |
| 6 | Currency | `transaction_currency` | mono | start | no | none | yes |
| 7 | Transaction price | `kpis.transaction_price.amount` | DS-FMT-04 | end | `transaction_price` | Transaction price (between) | yes |
| 8 | Recognized to date | `kpis.revenue_to_date.amount` | DS-FMT-04 | end | no | none | yes |
| 9 | Billed to date | `kpis.billed_to_date.amount` | DS-FMT-04 | end | no | none | yes |
| 10 | RPO | `kpis.rpo.amount` | DS-FMT-04 | end | no | none | yes |
| 11 | Open exceptions | `open_exception_count` | DS-FMT-21 | end | no | Has exceptions | yes |
| 12 | Scheduled | `kpis.scheduled.amount` | DS-FMT-04 | end | no | none | no |
| 13 | Awaiting trigger | `kpis.awaiting_trigger.amount` | DS-FMT-04 | end | no | none | no |
| 14 | Contract number | `contract_no` | mono | start | `contract_no` | none | no |
| 15 | Source | `source_system` label: `LEGACY_TEMPLATE_V1` "Legacy v1 template", `CSV_V2` "CSV v2", `API` "API", `MANUAL_UI` "Manual", `SALESFORCE` "Salesforce", `STRIPE` "Stripe", `NETSUITE` "NetSuite", `QUICKBOOKS_ONLINE` "QuickBooks Online", `LEGACY_DB` "Legacy database" | text | start | no | none | no |
| 16 | Region | `region` | text | start | no | none | no |
| 17 | Channel | `channel` | text | start | no | none | no |
| 18 | Contract type | `contract_type` | text | start | no | none | no |
| 19 | Signature date | `signature_date` | DS-FMT-16 | start | no | none | no |
| 20 | Updated | `updated_at` | DS-FMT-17 | start | `updated_at` | none | no |
| 21 | (row actions) | menu "Open", "Open in new tab", "Pin to Home", "Copy link" | ghost icon button | end | no | none | yes |

### 3.6 Filters

| Filter label | Editor (DS-CMP-13) | API parameter | Operators |
|---|---|---|---|
| Quick search | text, placeholder "Search contracts" | `q` (external id, contract number, customer name, order number) | contains |
| Entity | enum checklist of entities in scope | `entity` (repeatable) | is, in |
| Customer | combobox over `GET /customers?q=` | `customer` | is |
| Status | enum checklist of E-17 labels | `status` (repeatable) | is, in |
| On hold | Yes / No | `on_hold` | is |
| Modified in period | period picker | `modified_in_period` (`period_key`) | is |
| Transaction price | money between, at least, at most (string decimals) | `value_min`, `value_max` | between, at least, at most |
| Has exceptions | Yes / No | `has_exceptions` | is |

### 3.7 Bulk and row actions

- Selection bar: "<n> selected"; "Submit for activation"; "Apply hold"; "Pin to Home"; "Clear selection". Items are commanded one at a time with their own `Idempotency-Key` and `If-Match` (no bulk endpoint, OQ-S-16), at most 200 per action, with a DS-CMP-24 indicator "Submitting <done> of <total>" in the selection bar.
- "Submit for activation": `POST /contracts/{id}/submit-activation` for each selected contract. A contract whose status is not `DRAFT` is skipped with the result "Not a draft". The result modal (DS-CMP-11 form variant, no inputs) is titled "Submitted <m> of <n> contracts" and lists failures in a static table: Contract, Problem (problem `title`), Detail (checklist items for `activation-checklist-failed`, ERR-31).
- "Apply hold": drawer "Apply hold to <n> contracts" with Hold type (radio "Recognition hold" `recognition`, "Journal export hold" `journal_export`), Reason (reason field, minimum 10 characters, BR-PLT-08); primary "Apply hold"; `POST /contracts/{id}/apply-hold` per contract; result modal as above.
- "Pin to Home": `POST /saved-views` per contract with SCR-IA-08 config; toast "Pinned <n> contracts to Home."

### 3.8 States

| State | Rendering and copy |
|---|---|
| Loading | Header row plus 10 skeleton rows (DS-CMP-10) |
| Empty, native tenant | Title "No contracts yet"; description "Contracts arrive from imports, integrations or the API. Start with a template or connect a source."; primary "Import contracts" (SF-10:new `?template=contracts`); secondary link "Read the import guide" |
| Empty, legacy preset tenant (J-01-AC-1; SCR-LTH-O3) | Title "No contracts yet"; description "Import your legacy Contract Setup template or create a contract."; primary "Download legacy templates" (SF-10:templates); secondary "Create a contract" (SF-03:new, `contract.create`); for members of WLD-T-00, link "Open the Legacy parity pack" |
| No results | SCR-ST-04 "No contracts match these filters" with "Clear filters" |
| Quick list empty | "No contracts in <quick list label>." with "Show all contracts" |
| Error | SCR-ST-05 "Could not load contracts" |
| No permission | SCR-PERM-01, area label "contracts", permission label "viewing contracts" |
| Stale | none at list level; rows show values as last computed |
| Export running | Toolbar indicator "Preparing export" (DS-CMP-24); on success toast "Export ready." with "Download"; on failure negative toast "The export failed. Nothing was downloaded." |

### 3.9 Interactions, keyboard and copy

| Element | Interaction | Keyboard |
|---|---|---|
| Grid | DS-CMP-10 keyboard table; Enter on a row opens SF-03 | arrows, Enter, Space in the checkbox column |
| Quick search | Debounced 250 ms; results announced "<n> contracts" | `/` focuses it when focus is not in a field (listed in the shortcuts dialog) |
| New contract | Navigates to SF-03:new | Enter |
| Review a contract document | Navigates to SF-20:new | Enter |
| Deal preview | Navigates to SF-18 | Enter |

Copy keys: `contracts.list.title` "Contracts"; `contracts.list.count.one` "{count} contract"; `contracts.list.count.other` "{count} contracts"; `contracts.list.new` "New contract"; `contracts.list.review` "Review a contract document"; `contracts.list.dealPreview` "Deal preview"; `contracts.list.import` "Import contracts"; `contracts.list.search` "Search contracts"; `contracts.list.bulk.submit` "Submit for activation"; `contracts.list.bulk.hold` "Apply hold"; `contracts.list.bulk.pin` "Pin to Home".

### 3.10 Sample world

WLD-T-01, context AVM-US, Sep 2026, ASC606. Rows located by external id (WLD-R-07):

| Contract | Customer | Status | Currency | Transaction price | State in the journey order |
|---|---|---|---|---|---|
| `SF-ORD-10001` | Pellworth Logistics Inc. (Demo) | Active | USD | 135,000.00 | seed |
| `SF-ORD-10388` | Pellworth Logistics Inc. (Demo) | Active | USD | 30,000.00 | seed (entity AVM-US) |
| `SF-ORD-10002` | Marrowby Health Partners LLC (Demo) | Active | USD | 240,000.00; 300,000.00 after J-05 | seed |
| `PRJ-CB-2026-01` | Castellan Build Group Inc. (Demo) | Active | USD | 1,000,000.00; 1,350,000.00 after J-06 | seed |
| `SF-ORD-10003` | Ulvane Telematics Inc. (Demo) | Active | USD | not asserted (usage contract) | seed |
| `SF-ORD-10417` | Orrin Vale Architects LLP (Demo) | Active | USD | 108,000.00 | seed |
| `SF-ORD-20417` | Kinsley Marrow Foods Inc. (Demo) | Draft, then Active after J-03.9 | USD | 120,000.00 | J-03.1 (appears in "Created from integrations this period") |
| `BG-AVM-0020` | background | Pending approval | USD | 146,000.00 | WLD-B-01 |
| `BG-AVM-0030` | background | Active, Void after J-26 | USD | not asserted | WLD-B-08 |

Count: 100 background AVM-US contracts plus the key contracts; the count is asserted only as equal to `X-Erev-Total-Count` (WLD-R-06). With `entity` omitted, AVM-UK `SF-ORD-UK-2001` (GBP 68,000.00), AVM-DE `NS-SO-DE-5001` to `NS-SO-DE-5004` (EUR) and AVM-JP `JP-LIC-0001` (JPY 50,000,000, zero decimals, J-11-AC-2) also appear.

### 3.11 Test hooks

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Grid | `getByRole("grid", {name: "Contracts"})` | `SF-02-grid-contracts` |
| Row | `getByRole("row", {name: /SF-ORD-20417/})` | `SF-02-row-sf-ord-20417` |
| Saved-view selector | `getByRole("button", {name: /^View:/})` | `SF-02-saved-view` |
| Quick list option | `getByRole("menuitemradio", {name: "Created from integrations this period"})` | none |
| FilterBar | `getByRole("toolbar", {name: "Filters"})` | `SF-02-filter-bar` |
| Selection bar | `getByRole("region", {name: /selected$/})` | `SF-02-selection-bar` |
| Empty state | `getByRole("heading", {name: "No contracts yet"})` | `SF-02-empty-contracts` |

### 3.12 Light, dark and accessibility

- Light and dark: identifier links `--fg-1` with dotted `--border-control` underline (DS-CMP-10); status chips per §0.8; selected rows `--accent-subtle` plus `--selection-edge`.
- Accessibility: grid `aria-rowcount` from the API count; the first column is `role="rowheader"`; filter changes announce "Filter removed. <n> contracts." (DS-CMP-13); bulk results modal is `role="dialog"` with focus on its heading.

## 4. SF-03 Contract workbench

### 4.1 Frame: record header, five-step tracker, KPI strip and tabs

| Field | Value |
|---|---|
| Screen ids and routes | SF-03 `/contracts/:contractId/obligations` (RT-10) and the tab routes RT-11 to RT-19 |
| Roles and permissions | Read `contract.read`. Header commands by status in §4.1.6; tab commands in each tab section |
| Purpose | One place to review a contract through the five steps, see its figures, act on it and trace every number (PRD SF-03; D-60) |
| REQ | REQ-UX-003, REQ-UX-004, REQ-UX-005, REQ-UX-015; REQ-CON-001 to REQ-CON-015, REQ-CON-018; REQ-TP-004; REQ-REC-021; REQ-BIL-003 |
| Journeys | J-03.2 to J-03.10, J-04.4, J-07.1, J-08.1, J-09.1 to J-09.3, J-10.3, J-11.4, J-11.5, J-12.3, J-16.4, J-19.6, J-19.7, J-26.1, J-26.2; J-03-ALT-1, J-08-ALT-1, J-09-ALT-1, J-09-ALT-2 |

#### 4.1.1 Wireframes

1440 px (Obligations tab with O1 selected; the obligation pane is §5):

<!-- WF:workbench-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Contracts > NS-SO-DE-5004                                                                        |
| Work              | NS-SO-DE-5004 [copy] Hollenbrand Medizintechnik (Demo) (Active) (v4)  [Documents 1] [*New modific|
|    Home           | Customer Hollenbrand Medizintechnik . Entity AVM-DE . Currency EUR . Inception 01 Sep 2026       |
| |* Contracts      |+------------------+------------------+------------------+------------------+------------------+  |
|    Schedules      || (ok) 1 Contract  | (ok) 2 Obligation| (ok) 3 Transactio| (ok) 4 Allocation| (ok) 5 Recognitio|  |
|    Close          || Stand-alone      | 2 obligations    | EUR 108,000.00   | Relative SSP     | 50.3% recognized |  |
|    Journals       |+------------------+------------------+------------------+------------------+------------------+  |
|    Reports        | Key figures (EUR, ASC 606)                                                [Transaction|Functional|
| ----------------  |+---------------+---------------+---------------+---------------+---------------+---------------+ |
| Govern            || Transaction pr| Billed        | Recognized    | Scheduled     | Awaiting trig.| Contract liab.| |
|    Approvals    3 || 108,000.00    | 72,000.00     | 54,329.83     | 18,000.45     | 35,669.72     | 17,670.17     | |
|    Policies       ||               | ####.. 66.7%  | ###... 50.3%  |               | //            | Asset 0.00 .. | |
|    Data           |+---------------+---------------+---------------+---------------+---------------+---------------+ |
|                   |  Obligations 2    Estimates 0    Schedules    Billing    Journals    Modifications 0    History  |
|                   |  ============                                                                                    |
|                   |+----------------------------+  +----------------------------------------------------------------+|
|                   || [Filter____] {Sort v}      |  | Sensor gateway unit  O1 <Point in time>   [Record event v] ..  ||
|                   || 2 obligations (EUR)        |  | Allocated      Recognized      Scheduled      Awaiting trigger ||
|                   |||* Sensor gateway  89,174.31|  | 89,174.31      53,504.59 ###.. 0.00           35,669.72 //     ||
|                   |||* O1 <Point in time>       |  | Overview | Attributes | SSP and allocation | Schedule | Events ||
|                   ||  Platform support  18,825.6|  | ========                                                       ||
|                   ||  O2 <Over time><Ratable>   |  | Delivered 120 of 200 units (60.0%)                             ||
|                   ||                            |  | Billed to date 54,000.00 . Remaining allocation 35,669.72      ||
|                   ||                            |  | Satisfaction: partially satisfied . No holds                   ||
| Settings          |+----------------------------+  +----------------------------------------------------------------+|
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:workbench-1440 -->

1280 px (rail collapsed; master 300 px when the viewport is below 1280 px, 360 px otherwise):

<!-- WF:workbench-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Contracts > NS-SO-DE-5004                                                                         |
| H  | NS-SO-DE-5004 [copy] Hollenbrand Medizintechnik (Demo) (Active) (v4) [Documents 1] [*New modificat|
| *Ct| Customer Hollenbrand .. . Entity AVM-DE . Currency EUR . Inception 01 Sep 2026                    |
| Sc |+------------------+------------------+------------------+------------------+------------------+   |
| Cl || (ok) 1 Contract  | (ok) 2 Obligation| (ok) 3 Transactio| (ok) 4 Allocation| (ok) 5 Recognitio|   |
| Jn |+------------------+------------------+------------------+------------------+------------------+   |
| Rp |+---------------+---------------+---------------+---------------+---------------+---------------+  |
| -- || Transaction pr| Billed        | Recognized    | Scheduled     | Awaiting trig.| Contract liab.|  |
| Ap || 108,000.00    | 72,000.00     | 54,329.83     | 18,000.45     | 35,669.72     | 17,670.17     |  |
| Po |+---------------+---------------+---------------+---------------+---------------+---------------+  |
| Da |  Obligations 2   Estimates 0   Schedules   Billing   Journals   Modifications 0   History         |
|    |+-----------------------+ +-----------------------------------------------------------------------+|
|    || [Filter____] {Sort v} | | Sensor gateway unit  O1 <Point in time>   [Record event v] ...        ||
|    || 2 obligations         | | Allocated      Recognized      Scheduled     Awaiting trigger         ||
|    |||* Sensor gateway unit | | 89,174.31      53,504.59       0.00          35,669.72                ||
|    |||* O1  89,174.31       | | Overview | Attributes | SSP and allocation | Schedule | Events        ||
|    ||  Platform support     | | Delivered 120 of 200 units (60.0%)                                    ||
|    ||  O2  18,825.69        | +-----------------------------------------------------------------------+|
| Se |+-----------------------+                                                                          |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:workbench-1280 -->

1440 px with the Explain panel docked (content reflows; the master pane shrinks to its 280 px minimum while Explain is open below 1680 px) [J: keeps the detail pane at least 480 px wide]:

<!-- WF:workbench-explain-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Contracts > NS-SO-DE-5004  ... record header, tracker and KPI strip as above ...                 |
| Work              |  Obligations 2    Estimates 0    Schedules    Billing    Journals    Modifications 0    History  |
|    Home           |+----------------------+ +----------------------------------+ +----------------------------------+|
| |* Contracts      || [Filter___] 2        | | Sensor gateway unit  O1          | | Explain                          ||
|    Schedules      |||* Sensor gateway u.. | | Allocated  Recognized  Awaiting  | | Revenue to date . O1             ||
|    Close          |||* O1  89,174.31      | | 89,174.31  53,504.59   35,669.72 | | EUR 53,504.59                    ||
|    Journals       ||  Platform support    | | Overview | Attributes | SSP ..   | | Formula  Inputs  Steps           ||
|    Reports        ||  O2  18,825.69       | |                                  | | Source records  Versions         ||
| ----------------  ||                      | |                                  | | History                          ||
| Govern            ||                      | |                                  | | [Open calculation trace]         ||
|    Approvals    3 ||                      | |                                  | |                                  ||
|    Policies       |+----------------------+ +----------------------------------+ +----------------------------------+|
|    Data           |                                                                                                  |
| Settings          |                                                                                                  |
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:workbench-explain-1440 -->

#### 4.1.2 Regions and components

| Region | Component | Content |
|---|---|---|
| Record header | DS-CMP-06 contract variant | Breadcrumb "Contracts / <external id>" (link keeps the context parameters); title row; meta row; banner slot; tracker; KPI strip. Sticky condensed header after the strip scrolls out |
| Title row | DS-CMP-06 | Identifier `external_id` (mono, copy button "Copy contract id"); `h1` = `customer.name`; chips: status (§0.8), "On hold" when `on_hold`, outline "Combined" when `combination_group.is_singleton = false`, neutral version chip `v<context.version_no>`; buttons per §4.1.6 |
| Meta row | DS-CMP-06 | Customer (link to SF-15:customer); Entity (`contracting_entity.code` · `contracting_entity.name`); Currency; Inception date; Signature date; Payment terms; Source (label of `source_system`, a link that opens the source record drawer §6.6 when `GET /contracts/{id}/sources` returns a record); Contract number (`contract_no`, mono); Last computed (`context.computed_at`, DS-FMT-17, `data-volatile`; rev 1.10: the time of the computation that produced the version in context, 04 API-S-Context — `context.known_at` is the read's record cut-off and feeds the "Known at" banner only); Figures as of (`context.measured_period`, the period label with the stale marker DS-CMP-26, shown only when that period ends before the context period: the to-date figures were measured at the version's horizon, 04 API-C-10; rev 1.21: the marker is an Info icon button named, and with the tooltip, "Measured at <period label>, the last period this contract was computed for." — no job need exist for it, so it does not read "Recalculation queued", which stays with banner 4 and a job that exists; `data-testid` `SF-03-figures-as-of`). Empty values are omitted, not shown as em dashes |
| Banner slot | DS-CMP-29 | §4.1.5 |
| Five-step tracker | DS-CMP-17 | §4.1.3 |
| KPI strip | DS-CMP-06, DS-CH-05 bars | §4.1.4 |
| Tabs | DS-CMP-07 route tabs | Obligations · Estimates · Schedules · Billing · Journals · Modifications · History. Counts: "Obligations <n>" (`GET /contracts/{id}/obligations` item count), "Estimates <n>" (`GET /contracts/{id}/estimates` count), "Modifications <n>" (`count=true`). WarningCircle on a tab when an open exception of the contract maps to it (table below). REQ-UX-004 "Documents" and "Audit" are the header "Documents" drawer (§4.8) and the History tab "Audit trail" view (§4.7) (OQ-S-01) |
| Tab content | per tab | §4.2 to §4.7, §5, §8 |
| Explain dock | DS-CMP-15 | §6 |

Exception-to-tab mapping for the WarningCircle (`GET /exceptions?contract=<id>&status=OPEN&status=IN_PROGRESS`):

| Tab | Codes |
|---|---|
| Obligations | `PRODUCT_UNMAPPED`, `SSP_KEY_NOT_FOUND`, `RESIDUAL_REJECTED`, `OBSERVABLE_POINT_MISSING`, `NEGATIVE_WEIGHT`, `TOTAL_WEIGHT_ZERO`, `SFC_REVIEW_REQUIRED`, `SFC_RATE_MISSING`, `ENGINE_INVARIANT_VIOLATION` |
| Estimates | `VC_REASSESSMENT_MISSING`, `ROYALTY_ACCRUAL_MISSING`, `RETURN_ESTIMATE_MISSING`, `LOSS_EAC_MISSING`, `BREAKAGE_EXPECTED_ZERO`, `BREAKAGE_OVER_REDEMPTION`, `ESTIMATE_VERSION_NOT_APPROVED`, `COST_NO_EAC` |
| Billing | `INVOICE_ON_NOT_A_CONTRACT`, `DQ_DUPLICATE_INVOICE`, `DQ_REVENUE_WITHOUT_BILLING`, `DQ_NEGATIVE_LIABILITY_LAYER`, `ANOMALY_REVENUE_AHEAD_OF_BILLING`, `FX_RATE_MISSING` |
| Journals | `ACCOUNT_MAPPING_MISSING`, `JOURNAL_UNBALANCED` |
| Schedules | `COST_RELATED_POB_MISSING`, `COST_PATTERN_INVALID`, `DQ_RECOGNITION_AFTER_POB_END`, `ANOMALY_REVENUE_CHANGE`, `ANOMALY_NEGATIVE_REVENUE`, `ANOMALY_RECOGNITION_AFTER_POB_END` |

#### 4.1.3 Five-step tracker

Step labels follow REQ-UX-015 and PRD J-03.2: "Contract", "Obligations", "Transaction price", "Allocation", "Recognition" (OQ-S-13). States come from `API-S-Contract.steps[]` (04 E-112 steps and E-113 states, derived by the 04 §16.14 contract step rule; `status_code` names the code behind a Blocked or Needs attention state): `COMPLETE` → Complete; `NEEDS_ATTENTION` → Needs attention; `BLOCKED` → Blocked; `IN_REVIEW` → In review; `NOT_STARTED` → Not started (DS-CMP-17 icons and tones).

| # | Status line when not complete | Status line when complete | Evidence region (loads on expand) |
|---|---|---|---|
| 1 Contract | "Needs review" (no Step 1 record, J-03.2); "Review <judgement no> waiting for review"; "Review <judgement no> reviewed: record the assessment" (behind the not-a-contract gate "…: record criteria met"); "Review <judgement no> rejected" (the Step 1 path below; rev 1.11); "Combination suggested with <external id>"; "Criteria not met" (`NOT_A_CONTRACT`); "Criteria met on <date>: submit for activation" (`NOT_A_CONTRACT` with the criteria-met assessment recorded; rev 1.11) | "Stand-alone contract"; "Combined with <external ids>" | Criteria table: (a) "Approved and committed"; (b) "Rights identified"; (c) "Payment terms identified"; (d) "Commercial substance"; (e) "Collectibility probable"; each with Conclusion (Yes / No / Not recorded), Evidence (judgement record link, attachments) and the Codification citation "ASC 606-10-25-1(a)" to "(e)". Termination: party, substantive penalty, notice days. Enforceable term (`steps[0].detail.enforceable_term`, DS-FMT-20). Combination: group code, members, open suggestions with actions "Combine" and "Dismiss suggestion". The Step 1 path line with its action (below; rev 1.11) |
| 2 Obligations | "Needs review" (a distinct review is missing) | "<n> obligations"; "<n> obligations · <m> material rights" | Table: Obligation (key, mono), Product (code), Kind, Distinctness, Template (`template_code v<version_no>`), Distinct review ("Recorded" where a reviewed record of the obligation exists — what the checklist's `DISTINCT_REVIEW` asks; else the status, in the words of §0.8, of the obligation's newest record that is a draft, waits for review or was rejected; else "Not recorded". Rev 1.76; **replaced:** "Recorded" for a record of any status, beside a checklist that said "not recorded"). Row action "Record distinct review" (drawer §4.9.2) |
| 3 Transaction price | "Computed · <currency> <total>" for drafts (J-03.2) | "<currency> <total>" | Build-up static table from `GET /contracts/{id}/versions/{version_no}` `transaction_price_buildup`: Fixed consideration; Variable consideration (constrained); Expected returns; Consideration payable to a customer; Significant financing component; Noncash consideration; Sales tax excluded; Out of scope; Total (totals rule, DS-ELV-02). Memo row below the total: "Excluded by the constraint <vc_excluded>". Financing note from `steps[2].detail.financing_note`, for example "Not assessed: payment in advance within one year (ASC 606-10-32-18)." (J-03.5). Link "Open estimates" |
| 4 Allocation | "Computed · Relative SSP" for drafts; "Blocked: no SSP for <product>" | "Relative SSP · <SSP book version label>". Rev 1.29: while the obligations or the label of their SSP book version are being read the step shows no status line and is busy (`aria-busy` on the step), so the line is never read or captured first without the book and then with it | Allocation walk (§4.1.3.1) |
| 5 Recognition | "Preview" for drafts (J-03.2) | "<ratio> recognized" (`steps[4].detail.recognized_ratio`, DS-FMT-09) | Table per obligation: Obligation, Pattern (satisfaction pattern, method and convention labels), Recognized to date, Scheduled, Awaiting trigger, Next event (`steps[4].detail.obligations[].next_trigger` label and date, or "—"). Link "Open schedules" (SF-03:schedules) |

##### 4.1.3.1 Allocation walk

Binding `GET /contracts/{id}/allocation` (API-S-AllocationWalk). Static table, caption "Allocation walk (<currency>)", every amount an Explain trigger (`contract_version~<context.contract_version_id>~allocated_amount~` scoped to the obligation key).

| # | Header | Field | Format | Alignment |
|---|---|---|---|---|
| 1 | Obligation | `lines[].obligation_key` | mono | start |
| 2 | Product | `lines[].product.code` | mono | start |
| 3 | SSP source | `lines[].ssp_book_version.label` · `ssp_method` label | text | start |
| 4 | Low | `lines[].low` | DS-FMT-13 | end |
| 5 | Mid | `lines[].mid` | DS-FMT-13 | end |
| 6 | High | `lines[].high` | DS-FMT-13 | end |
| 7 | Stated price | `lines[].stated_price.amount` | DS-FMT-04 | end |
| 8 | Range | `lines[].range_position` (04 E-114) with `lines[].outside_range_point` (the resolved POL-072 literal, null when inside): `INSIDE` "Inside range"; `BELOW` "Below range: <point words>"; `ABOVE` "Above range: <point words>". Point words: `NEAREST_BOUND` "nearest bound applied"; `MIDPOINT` "midpoint applied"; `LOW_POINT` "low point applied"; `HIGH_POINT` "high point applied"; `OBSERVABLE_POINT` "observable point applied" | text | start |
| 9 | Selected SSP | `lines[].selected_ssp` | DS-FMT-13 | end |
| 10 | Weight | `lines[].weight` | DS-FMT-09 two decimals | end |
| 11 | Allocated | `lines[].allocated.amount` | DS-FMT-04 | end |
| 12 | Allocation adjustment | `lines[].allocation_adjustment.amount` | DS-FMT-31 | end |

Totals row (DS-ELV-02): label "Total"; Allocated = `totals.allocated` (equal to the transaction price); Allocation adjustment = `totals.allocation_adjustment` (asserted 0.00 in J-03-AC-1); other cells empty.

**Step 1 path (rev 1.11; supervisor ruling R-89; PRD SM-02).** A Step 1 judgement is recorded in two steps, the review first and the assessment after it is reviewed, because the review request of a judgement record hashes the contract's head (04 §16.10) and an assessment appended while that request is pending makes it stale. The screen reads the path from the latest Step 1 record of the contract (`GET /judgements`, topic `COLLECTIBILITY` or `NOT_A_CONTRACT`, newest first, `SUPERSEDED`, `DRAFT` and — rev 1.66; 04 E-57 rev 1.242 — `VOIDED`, a discarded draft, left out) and the latest standing `COLLECTIBILITY_ASSESSED` event of each enabled book of the contracting entity (`GET /contracts/{id}/events?event_type=COLLECTIBILITY_ASSESSED&event_type=EVENT_VOIDED`, latest by effective date, then record order). An assessment that an `EVENT_VOIDED` names counts for nothing (rev 1.72; supervisor ruling R-102 (c); 04 §16.1 rev 1.150): `replace-draft` voids the assessments of the draft it replaces, the events route lists a voided event like any other and no member of API-S-Event marks it, so the path reads the voids with the assessments; before, a replaced draft read "The assessment of <date> cites Step 1 review <judgement no>. Submit the contract for activation." over an assessment that no longer stood. While the contract is `DRAFT` or `NOT_A_CONTRACT`, the status line of step 1, the line in its evidence region and the commands of §4.1.5 and §4.1.6 follow this table; each line says who acts next. When `steps[0].state` is `COMPLETE` and the path is not at its last row, the step shows In review for a record that waits and Needs attention otherwise. When the records or the assessments cannot be read the evidence region says "Could not load the Step 1 review and its assessments" with "Retry" and no Step 1 command is offered. A contract in any other status shows no Step 1 command: the reassessment of an activated contract (606-10-25-5) has no screen yet (item CTR-STEP1-REENTRY-1).

| Latest Step 1 record | Line in the evidence region | Action (`contract.create` and `judgement.create`) |
|---|---|---|
| none | "No Step 1 review is recorded." | "Record Step 1 review" (§4.9.1) |
| `SUBMITTED` | "Step 1 review <judgement no> is waiting for review by a Revenue Reviewer." | link "View request" (SF-12:request of the record's `approval_request_id`), rendered for a holder of `judgement.review` and for the preparer |
| `REJECTED` | "Step 1 review <judgement no> was rejected. Record a new review." | "Record Step 1 review" |
| `REVIEWED`, and the latest standing assessment of an enabled book does not cite it | "Step 1 review <judgement no> was reviewed by <reviewer> on <DS-FMT-17 timestamp>. Record the assessment to continue."; where the action is "Record criteria met" the last sentence is "Record criteria met to continue." | "Record assessment" (`DRAFT`, and `NOT_A_CONTRACT` with a record of topic `NOT_A_CONTRACT`) or "Record criteria met" (`NOT_A_CONTRACT`, record of topic `COLLECTIBILITY`) (§4.9.1) |
| `REVIEWED` and cited by the latest standing assessment of every enabled book | `DRAFT`: "The assessment of <date> cites Step 1 review <judgement no>. Submit the contract for activation." `NOT_A_CONTRACT`, assessment probable: "Criteria met on <date> (Step 1 review <judgement no>). Submit the contract for activation." `NOT_A_CONTRACT`, assessment not probable: "Criteria not met since <date> (Step 1 review <judgement no>). Record a new Step 1 review when the criteria are met." | "Submit for activation" (`contract.create`); for the last case "Record Step 1 review" |

**A reviewed record that the API refuses (rev 1.72; supervisor ruling R-102 (c); REQ-POL-008; 04 §16.3 (b)).** `replace-draft` leaves the judgement records as they are, and the API takes an assessment only on a record that was reviewed at or after the time the latest standing booking was written. That time is the booking's `created_at`, the clock a review is stamped with, and no read answers it: API-S-Event answers `recorded_at`, which the database sets, so a comparison on the screen would refuse a record the API takes — one reviewed in the instant of the booking, as the Contract Setup import reviews its record — and would differ from the API by whatever the two clocks differ. The screen therefore compares nothing. The path keeps the row of the reviewed record: "Record assessment" stays its action and the fix of the checklist's `STEP1_RECORD` (§4.9.8). A new review is never out of reach beside it: the overflow of a `DRAFT` offers "Record Step 1 review" after "Record assessment" (§4.1.6), and the assessment drawer offers "Record a new Step 1 review" once the API has refused the record (§4.9.1). Once a new record is recorded the path follows it, as the latest Step 1 record. Before, a draft that was replaced after its review had no way on: the path, the overflow and the fix link each opened the assessment of the record the API refuses.

**Draft Step 1 records (rev 1.66; PRD SM-10 `DRAFT` → `VOIDED`, IMP-104; 04 API-R-33 `POST /judgements/{id}/discard`, E-57 rev 1.242).** "Record Step 1 review" creates its record and sends it for review as two requests (§4.9.1). A record whose submission was refused stays a draft: it is no step of the path, which offers the review again, and it holds the activation (the checklist's `JUDGEMENT_RECORDS`). Each draft record of topic `COLLECTIBILITY` or `NOT_A_CONTRACT` is named in the evidence region of step 1, whatever the contract's status and above the path's line where the path is shown, newest first — "Record <judgement no> is a draft that was not sent for review." — with the command "Discard" for a holder of `judgement.create` for the contract's contracting entity, asked of the access module (§0.6 SCR-PERM-02 (a)); the API asks the permission of anyone and not of the record's creator alone. A member without it reads the line and no command, as does a view of an earlier `known_at`. "Discard" opens the confirmation "Discard this draft record?" with the consequence "Record <judgement no> is voided: it takes no further edit and no review, and its number is not given out again." and, where the contract is on hold, the sentence "<external id> is on hold. The discard releases nothing: the hold stays and is released on the contract." — the discard appends nothing to the contract, so a hold that the record's earlier submission placed stays. The command sends `POST /judgements/{id}/discard` without a body; on its answer the toast reads "Record <judgement no> was discarded.", the records are read again and the confirmation closes. A refusal — 409, the record is no draft any more — is shown in the confirmation and the record stays; a command that got no answer says so and goes out again under the key it had. The criteria table, which falls back to the newest record that is not discarded where no other Step 1 record stands, names such a draft "Record <judgement no> · Draft", in the words of §0.8. The same command stands on a draft record in "Linked judgement records" and in the override banner of SF-07 (§7.4, §7.6) and in "Evidence" of SF-03:estimate (§8.3). The proposal of a combination group — a draft of topic `COMBINATION` whose subject is the group — is decided with its group: the screens know it by those two members and offer it no command, and the API's 409 stays the guarantee.

**Rejected Step 1 records (rev 1.74; PRD SM-10 rev 1.199, IMP-145; 04 rev 1.296 API-R-33, table 15.4-I `JUDGEMENT_RECORD_REJECTED`).** A record whose review was rejected stays `REJECTED`. The path offers a new review, which writes a new record, and the rejected one keeps failing the activation checklist (`JUDGEMENT_RECORDS`) until it is discarded: the API's other road, an edit by the record's author that makes it a draft again, has no screen. Before rev 1.74 no screen offered the discard, and a contract whose Step 1 review was once rejected was never activated from a screen. Each rejected record of topic `COLLECTIBILITY` or `NOT_A_CONTRACT` is named in the evidence region of step 1 among the draft records, newest first, whatever the contract's status: "Record <judgement no> was rejected. Discard it before the contract is submitted for activation." while the contract is `DRAFT` or `NOT_A_CONTRACT`, and "Record <judgement no> was rejected." in every other status, where no activation waits for it. The record that the path's own line names as rejected is named here as well: the path says what comes next, this line what the record still holds. The line carries "Discard" for the holder and on the views of a draft's line, and the command is the draft's — its consequence, its sentence of a contract on hold, its toast and its refusal — under the title "Discard this rejected record?". The command stands on a rejected record in "Linked judgement records" of SF-07 (§7.4) and in "Evidence" of SF-03:estimate (§8.3) as well, and on the line of the activation checklist that names the record (§4.9.8). The line carries "View request" before "Discard" (rev 1.76): the record's review request (SF-12:request of its `approval_request_id`), where the reviewer's reason stands, for a holder of `judgement.review` for the contract's contracting entity and for the record's preparer, where the request screen is built — also on a view of an earlier `known_at`, since it commands nothing. A draft's line carries it by the same rule where the draft names a request: one that its author revised after a rejection.

#### 4.1.4 KPI strip

Heading "Key figures at <measured period label> (<currency>, <book label>)" — the period the figures are measured at, `context.measured_period`, by its label in the contracting entity's calendar, always named (rev 1.21; supervisor ruling R-112 (h)): the context bar names the period asked for and, under another entity's context, another calendar's state — and "Key figures (<currency>, <book label>)" when `context.measured_period` is null, where nothing is measured yet (04 API-C-10); currency view switch "Transaction | Functional" (DS-CMP-31) rendered when the contracting entity's functional currency differs from `transaction_currency`. Six cells (DS-CMP-06 maximum), all Explain triggers:

| Cell | Label | Value | Bar and secondary line | Explain reference |
|---|---|---|---|---|
| 1 | Transaction price | `kpis.transaction_price` | none | `links.explain_transaction_price` |
| 2 | Billed | `kpis.billed_to_date` | Bar against the transaction price; secondary "<ratio> of transaction price" from `kpis_ratios.billed` (04 API-S-Contract `kpis_ratios`) | The list level of §6.3 (rev 1.21), entries `links.explain_billed_to_date` |
| 3 | Recognized | `kpis.revenue_to_date` | Bar; "<ratio> of transaction price" from `kpis_ratios.recognized` | The list level of §6.3 (rev 1.21), entries `links.explain_revenue_to_date` |
| 4 | Scheduled | `kpis.scheduled` | none | The list level of §6.3 (rev 1.21), the entries of Recognized |
| 5 | Awaiting trigger | `kpis.awaiting_trigger` | No bar; secondary line "<n> triggers pending" when the API returns `kpis_ratios.pending_trigger_count` | `contract_version~<id>~awaiting_trigger` |
| 6 | Contract liability | `balances[e].contract_liability` where `e` is the context entity when present in `balances`, else the contracting entity | Secondary line "Contract asset <contract_asset> · Unbilled receivable <unbilled_receivable>", each an Explain trigger; when `balances` has more than one entity, the line ends "· <n> entities" linking to the Billing tab balances table | `balances[e].links.explain_contract_liability` (and `explain_contract_asset`, `explain_unbilled_receivable`; rev 1.24): `contract_version_balance~<balance id>~<measure>` at the `period` the link carries |

Rules: values never show a signed position (D-12, DS-FMT-28). An over-100% billed or recognized bar shows the warning chip "Over transaction price" (DS-CH-05). REQ-UX-004 lists eight figures; the sixth cell carries three (OQ-S-02). To-date figures (rev 1.10; 04 API-C-10 rev 1.132): Billed, Recognized, Scheduled, their ratios and the balances of cell 6 are measured at `context.measured_period`, the period of the context or the version's horizon when the context lies beyond it; Awaiting trigger is the version's, and so is Transaction price except for the returns reduction of a returnable obligation, which is measured at the same period (04 API-C-10; supervisor ruling R-85 (a)). The calculation trace holds no contract-level node per period, so the Explain of Recognized and of Billed lists one entry per obligation — `obligation_version~<obligation_version_id>~revenue_cum` (API-S-Obligation `links.explain_revenue_to_date`) and `~billed_cum` (`links.explain_billed_to_date`), each with the `period` its link carries: the billing node's period is one of the contracting entity's and may be named otherwise than the obligation's measured period — in place of the single reference of the table; Scheduled opens the same list as Recognized (it is the allocation less the recognized and the awaiting-trigger amounts, 03 REQ-REC-021); the references of cell 6 are the links of the balance entry (04 API-S-Contract `kpis.balances[].links`, rev 1.174; rev 1.24): each names the balance row — an id no other member carries — and the period the balance was read at, and the panel follows it as sent; a figure whose link is null (a cut before the first period the version measures: the balance is 0.00 and no node holds it) prints without a trigger. The list is the list level of the Explain panel, §6.3 (rev 1.21).

#### 4.1.5 Banner slot

At most one banner, in this priority order:

| Priority | Condition | Tone | Copy | Actions |
|---|---|---|---|---|
| 1 | Latest computation `QUARANTINED` (E-88) | negative | Title "Calculation quarantined"; message "This contract failed invariant <invariant> and was quarantined. Nothing was posted for it." (IMP-75) | "Open exception" |
| 2 | Status `VOIDED` | neutral | "This contract is void. Its posted lines were reversed in <period label>." | none |
| 3 | Open approval request on the contract (activation, void, modification) | info | "Activation is waiting for approval." / "Void is waiting for approval." / "Modification <modification no> is waiting for approval." | "View request" (SF-12:request); "Withdraw request" for the preparer |
| 4 | SCR-ST-08 stale | info | "Figures were computed before the latest change. Recalculation is queued." with the job indicator | none |
| 5 | Context period `closed` or `permanently_locked` for the contracting entity | neutral | "<period label> is locked for <entity code>. Late events post to <first open period label> with origin period <period label>." (DS-CMP-29; D-19) | none |
| 6 | Status `NOT_A_CONTRACT` | warning | "The contract criteria are not met. Receipts post to deposit liability until the criteria are met." (REQ-CON-003), followed by the line of the Step 1 path (§4.1.3; rev 1.11) | The action of the Step 1 path: "Record Step 1 review", "View request", "Record criteria met" or "Submit for activation" (rev 1.11; the command "Record criteria met" no longer appends `CONTRACT_CRITERIA_MET`, which the approved activation alone appends, 04 §16.3) |

#### 4.1.6 Header commands by status

| Status | Primary | Secondary | Overflow menu (in order; destructive last) |
|---|---|---|---|
| `DRAFT` | "Submit for activation" (`contract.create`, ACT-02) | "Edit draft" (SF-03:edit, `contract.create`); "Documents <n>" | The commands of the Step 1 path (§4.1.3; rev 1.11): "Record Step 1 review" (also once the assessment is recorded, for a new review) and, once the record is reviewed, "Record assessment" before it (rev 1.72: the review stays beside the assessment, because the API may refuse the reviewed record, §4.1.3); none while the record waits for review; "Combine with another contract"; "Copy link"; "Pin to Home"; separator; "Void contract" (`contract.void`) |
| `PENDING_REVIEW` | none | "Documents <n>" | "Copy link"; "Pin to Home" |
| `NOT_A_CONTRACT` | The command of the Step 1 path (§4.1.3; rev 1.11; PRD SM-02 `NOT_A_CONTRACT` → `PENDING_REVIEW`): "Record Step 1 review" (`contract.create` and `judgement.create`) until a new review is recorded, none while it waits for review, "Record criteria met" once it is reviewed, "Submit for activation" (`contract.create`, ACT-02) once the criteria-met assessment is recorded | "Documents <n>" | "Copy link"; "Pin to Home"; separator; "Void contract" |
| `ACTIVE`, `COMPLETED` | "New modification" (`modification.create`, SF-07) | "Change subscription" menu button (`modification.create`): "Upgrade", "Downgrade", "Co-term", "Renew", "Early renew", "Cancel" (each opens SF-07 with `action=<upgrade|downgrade|co_term|renew|early_renew|cancel>`); "Documents <n>" | "Record event" submenu (`event.record`): "Record delivery", "Record progress", "Record milestone", "Record cost", "Record return"; "Apply hold", "Release hold" (`contract.create`, the permission 04 API-R-28 asks; rev 1.75 — **replaced:** `adjustment.create`); "Edit memos" (`contract.create`); "Regroup lines" (`contract.create`); "Combine with another contract" (`contract.create`); "Request policy override" (`contract.create`; rev 1.80: not rendered in release 1.0, §4.9.7); "Copy link"; "Pin to Home"; separator; "Void contract" (`contract.void`) |
| `TERMINATED`, `VOIDED` | none | "Documents <n>" | "Copy link"; "Pin to Home" |

"Release hold" renders only when `on_hold` — and then in the overflow of a contract of every status (rev 1.75), behind "Apply hold" where that stands and before "Copy link" elsewhere: a hold is applied on a draft too, from the list's selection bar (§3.7) and from the obligation pane (§5.3), a hold of the whole contract is listed by the contract's read alone, and on a voided or terminated contract the drawer says why its holds are not released. It renders for a holder of `contract.create` for the contract's contracting entity, asked of the access module (§0.6 SCR-PERM-02 (a)), and not on a view of an earlier `known_at`. Before rev 1.75 it was not rendered at all (L5-4-Q-30): no read answered the id the command takes, and a hold applied on a screen had no exit on the screens. "New modification" and "Change subscription" render, in the header and in the toolbar of the Modifications tab (§4.6), on an `ACTIVE` contract only: 04 API-R-31 refuses a modification of a contract in any other status, `COMPLETED` included (rev 1.23). "Submit for activation" on a `PENDING_REVIEW` contract is not rendered (banner priority 3 explains the state). The activation of a `NOT_A_CONTRACT` contract is never auto-approved (PRD SM-02 rev 1.55), so its toast always reads "Submitted for activation. Request <request no> is waiting for approval." (rev 1.11).

#### 4.1.7 Data bindings

| Region | Endpoint | Parameters | Fields |
|---|---|---|---|
| Header, KPI strip, tracker | `GET /contracts/{id}` (API-S-Contract; ETag `"s<head_stream_version>"` kept for commands) | `as_of`, `known_at`, `book`, `currency_view` | every field of §4.1.2 to §4.1.4; `steps[]` and `kpis_ratios` (04 API-S-Contract, rev 1.2) |
| Step 1 evidence and Step 1 path | `GET /judgements?subject_type=contract&subject_id=<id>`; `GET /contracts/{id}/events?event_type=COLLECTIBILITY_ASSESSED&event_type=EVENT_VOIDED` (rev 1.11; the voids since rev 1.72); `GET /combination-suggestions?contract=<id>` (04 API-R-28, §16.14) | none | `topic`, `conclusion`, `status`, `judgement_no`, `reviewer`, `reviewed_at`, `approval_request_id`; event `id`, `event_type`, `supersedes_event_id`, `effective_date`, `record_seq`, `payload.book`, `payload.is_probable`, `payload.judgement_record_id`; suggestion `{id, contract_ids, contract_external_ids, related_party_group, inception_dates, detection_window_days, status, created_at}`, where `id` is the exception item id (04 B3-D14) |
| Step 2 and 5 evidence | `GET /contracts/{id}/obligations` | `as_of`, `known_at`, `book` | API-S-Obligation fields |
| Step 3 evidence | `GET /contracts/{id}/versions/{version_no}` | `book` | `transaction_price_buildup` |
| Step 4 evidence | `GET /contracts/{id}/allocation` | `as_of`, `known_at`, `book` | API-S-AllocationWalk |
| Tab counts and warnings | `GET /contracts/{id}/estimates`, `GET /contracts/{id}/modifications?count=true&limit=1`, `GET /exceptions?contract=<id>&status=OPEN&status=IN_PROGRESS` | none | counts, `code` |
| Documents count | `GET /attachments?subject_type=contract&subject_id=<id>&count=true&limit=1` | none | `X-Erev-Total-Count` |
| Recalculation | `GET /jobs?kind=CONTRACT_COMPUTE&state=QUEUED&state=RUNNING&subject_type=contract&subject_id=<id>` (04 API-R-11, T-PLT-27 `subject_type`, `subject_id`) | none | `progress`, `state` |

#### 4.1.8 States

| State | Rendering and copy |
|---|---|
| Loading | Header labels visible; identifier and title skeletons; five skeleton tracker segments; KPI value skeletons (DS-CMP-06) |
| Not found or out of scope | SCR-ST-07 "Contract not found", action "Go to Contracts" |
| No permission | SCR-PERM-01 "contracts" |
| Error | SCR-ST-05 "Could not load the contract" in the page region |
| Figures refused at the period (rev 1.21) | The header read answers 422 `validation-failed` with an entry of `errors[]` whose `rule_id` is `API-C-10` (04 API-C-10: a to-date measure the version's trace cannot answer at the cut is refused by name and never replaced by the version's stored figure). Not SCR-ST-05, and no figure, tracker or tab is rendered: a warning banner (`data-testid` `SF-03-figures-unreadable`), title "The figures of this contract cannot be read for <context period label>" ("… cannot be read as of today" when the context names no period), then each `errors[].message` of that rule as the API sends it (it names the contract, the obligation or entity, the measure and the period), then "Nothing is shown in their place. Choose another period in the context bar, or give the reference below to your administrator." and "Reference <request id>". The read is not repeated automatically. A `GET /contracts` row with `kpis: null` (SF-02) shows no value in its figure columns |
| Stale | Banner priority 4; KPI values keep the stale marker (DS-CMP-26) |
| Pending approval, locked, void, quarantined | §4.1.5 |
| Time travel | SCR-ST-10; the version chip reads `v<n> as known at <timestamp>` |

#### 4.1.9 Interactions, keyboard and copy

| Element | Interaction | Keyboard |
|---|---|---|
| Copy contract id | Copies `external_id`; toast "Copied NS-SO-DE-5004." | Enter |
| Tracker segment | Toggles its evidence region; only one open (DS-CMP-17); the expanded step is `?step=<n>` with `history.replace` | Enter or Space; Esc collapses |
| KPI value | Opens Explain | Enter or `E` |
| Tabs | Route links | Tab, Enter |
| Submit for activation | `POST /contracts/{id}/submit-activation` with `If-Match`. Success: toast "Submitted for activation. Request <request no> is waiting for approval." or, with auto-approval, "Contract activated." Failure `activation-checklist-failed`: negative banner in the banner slot titled "Contract cannot be activated" with ERR-31 detail and one link per failed checklist item (§4.9.8) | Enter |
| Void contract | Confirmation §4.9.6 | Enter |

Copy keys: `contracts.workbench.breadcrumb` "Contracts"; `contracts.workbench.copyId` "Copy contract id"; `contracts.workbench.kpi.heading` "Key figures ({currency}, {book})"; `contracts.workbench.kpi.transactionPrice` "Transaction price"; `.billed` "Billed"; `.recognized` "Recognized"; `.scheduled` "Scheduled"; `.awaitingTrigger` "Awaiting trigger"; `.contractLiability` "Contract liability"; `.contractAsset` "Contract asset"; `.unbilledReceivable` "Unbilled receivable"; `.ofTransactionPrice` "{ratio} of transaction price"; `contracts.workbench.tabs.obligations` "Obligations"; `.estimates` "Estimates"; `.schedules` "Schedules"; `.billing` "Billing"; `.journals` "Journals"; `.modifications` "Modifications"; `.history` "History"; `contracts.workbench.tracker.label` "ASC 606 steps"; step labels "Contract", "Obligations", "Transaction price", "Allocation", "Recognition".

#### 4.1.10 Sample world

| Contract (context) | Figures rendered | Source |
|---|---|---|
| K-11 `NS-SO-DE-5004` (AVM-DE, EUR) after J-04 | Transaction price 108,000.00; Billed 72,000.00; Recognized 54,329.83; Scheduled 18,000.45; Awaiting trigger 35,669.72; Contract liability 17,670.17 (asserted, J-04.4, WLD-X-22) | J-04-AC-1 |
| K-11 allocation walk | O1 `AVM-GW` low 81,000.00, mid 90,000.00, high 99,000.00 (405.00 / 450.00 / 495.00 × 200), stated 90,000.00, Inside range, selected SSP 90,000.00, allocated 89,174.31, adjustment (825.69); O2 `AVM-SUP-12` low 19,000.00, mid 20,000.00, high 21,000.00, stated 18,000.00, Below range: nearest bound applied, selected SSP 19,000.00, allocated 18,825.69, adjustment +825.69; totals allocated 108,000.00, adjustment 0.00 | WLD-X-22 derivation |
| `SF-ORD-20417` (AVM-US, USD), Draft after J-03.1 | Tracker "Needs review", "Needs review", "Computed · USD 120,000.00", "Computed · Relative SSP", "Preview"; allocation O1 `AVM-PLAT-100` low 85,000.00, mid 100,000.00, high 115,000.00, stated 96,000.00, Inside range, selected 96,000.00, allocated 97,627.12, adjustment +1,627.12; O2 `AVM-IMPL-PLUS` low 18,000.00, mid 20,000.00, high 22,000.00, stated 24,000.00, Above range: nearest bound applied, selected 22,000.00, allocated 22,372.88, adjustment (1,627.12) (asserted, WLD-X-23, J-03.6); Step 3 financing note "Not assessed: payment in advance within one year (ASC 606-10-32-18)." | J-03.2 to J-03.7 |
| K-01 `SF-ORD-10001` (AVM-US, USD) | Transaction price 135,000.00; contract liability 29,944.11 at 30 Sep 2026 (WLD-X-03); allocation O1 118,800.00, O2 16,200.00 (WLD-X-01) | J-15, J-16 |
| K-07 `NS-SO-DE-5003` (AVM-DE, EUR) after J-08 | Billed 100,000.00; Recognized 130,000.00; Contract liability 0.00; secondary line contract asset and unbilled receivable summing to 30,000.00 (J-08-AC-2) | J-08 |
| `BG-AVM-0030` | Void confirmation copy of §4.9.6 | J-26 |

#### 4.1.11 Test hooks

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Page title | `getByRole("heading", {level: 1})` (customer name) | `SF-03-page` |
| Identifier | `getByRole("button", {name: "Copy contract id"})` and the adjacent text | `SF-03-identifier` |
| KPI strip | `getByRole("region", {name: /^Key figures/})` | `SF-03-kpi-strip` |
| Figures as of (rev 1.21) | `getByRole("button", {name: /^Measured at /})` inside the meta row | `SF-03-figures-as-of` |
| Figures refused at the period (rev 1.21) | `getByRole("heading", {name: /^The figures of this contract cannot be read for /})` | `SF-03-figures-unreadable` |
| KPI value | `getByRole("button", {name: /^Explain Contract liability, EUR/})` | `SF-03-kpi-contract-liability` |
| Tracker | `getByRole("list", {name: "ASC 606 steps"})` | `SF-03-tracker` |
| Step | `getByRole("button", {name: /^Step 4, Allocation/})` | `SF-03-tracker-step-4` |
| Evidence region | `getByRole("region", {name: "Allocation"})` | `SF-03-evidence-4` |
| Allocation walk | `getByRole("table", {name: /^Allocation walk/})` | `SF-03-grid-allocation-walk` |
| Tabs | `getByRole("navigation", {name: /sections$/})` | `SF-03-tabs` |
| Banner | `getByRole("status")` inside the header | `SF-03-banner-header` |

#### 4.1.12 Light, dark and accessibility

- Light and dark: tracker state icons use `--<tone>-fg` (never `-solid`); the expanded segment indicator `--accent-solid`; KPI bars `--viz-kpi-bar` on `--viz-kpi-track` (C72); header on `--bg-surface` with `--border-hairline`.
- Accessibility: `section aria-labelledby=<h1 id>` (DS-CMP-06); tracker `ol aria-label="ASC 606 steps"` with names "Step 3, Transaction price, complete, USD 120,000.00"; route tabs `nav aria-label="<external id> sections"`; banners present on load are static; the condensed sticky header does not duplicate the `h1` (it uses a `p` with `aria-hidden="true"` and the full header stays in the accessibility tree).

### 4.2 Obligations tab (master list)

| Field | Value |
|---|---|
| Screen ids | SF-03 (no selection), SF-03:obligation (selected; pane §5) |
| Component | DS-CMP-08 obligations variant |
| Binding | `GET /contracts/{id}/obligations?as_of&known_at&book` |

Master pane: toolbar "Filter obligations" input (client-side match on `obligation_key`, `product.code`, `product.name`; a contract has at most 500 lines, API-S-ContractCreate) and sort menu "Obligation key" (default, `Intl.Collator` numeric), "Start date", "Product"; caption "<n> obligations · Allocated (<currency>)".

| Row line | Content |
|---|---|
| Line 1 | `product.name` (truncated, tooltip); end: `current.allocated_amount.amount` (DS-FMT-04 digits; the caption carries the code) |
| Line 2 | `obligation_key` (mono); outline chips: "Point in time" or "Over time"; "Ratable" when `recognition_method = TIME_ELAPSED`; "Series" when `distinctness = series`; "Material right" when `obligation_kind = MATERIAL_RIGHT`; "Intercompany: <performing entity code> performs" when performing ≠ contracting entity; state chips "Satisfied" (`satisfaction_status = SATISFIED`), "On hold" (`holds` non-empty); date range `start_date – end_date` (DS-FMT-20) |

States: loading 6 skeleton rows; empty (a draft without lines) title "No obligations yet", description "Add lines to the draft to create obligations.", action "Edit draft"; nothing selected: "Select an obligation to see its allocation, schedule and history." (DS-CMP-08); error SCR-ST-05 "Could not load obligations".

Keyboard: DS-CMP-08 (Up/Down select after 150 ms, `J`/`K`, Enter to the pane heading, Esc back). Test hooks: `getByRole("listbox", {name: "Obligations"})`; options by name "<product name>, <obligation key>"; `SF-03-row-<obligation key>`.

Sample world: K-11 O1 "Sensor gateway unit" 89,174.31, chips "Point in time", 01 Sep 2026 (no end date: "—" omitted); O2 "Platform support, 12 months" 18,825.69, chips "Over time", "Ratable", 15 Sep 2026 – 14 Sep 2027. `SF-ORD-20417` O2 `AVM-IMPL-PLUS` carries "Intercompany: AVM-UK performs" (J-03.4).

### 4.3 Schedules tab (SF-03:schedules)

| Field | Value |
|---|---|
| Route | `/contracts/:contractId/schedules` (RT-14) |
| Permissions | `contract.read`; export `report.export` |
| Purpose | Revenue schedule lines by period and the contract cost assets of the contract (REQ-UX-004 "Schedules (including contract costs)"; J-12.3) |

Layout: two panels stacked. Panel 1 "Revenue schedule" (DataGrid). Panel 2 "Contract costs" (DataGrid, rendered when the contract has cost assets). Panel 3 "Loss provision" (definition list, rendered when `GET /contracts/{id}/loss-provisions` returns rows).

Revenue schedule binding: `GET /schedule-lines?contract=<id>&book&from_period&to_period&obligation&line_type&as_of&known_at` (API-R-35), default range inception period to last scheduled period; saved-view code `SF-03:schedules#revenue`.

| # | Header | Field | Format | Alignment | Sort | Filter | Visible |
|---|---|---|---|---|---|---|---|
| 1 | Period | `period.name` | DS-FMT-19 | start | yes (default ascending) | Period range → `from_period`, `to_period` | yes |
| 2 | Obligation | `obligation_key` (04 API-S-ScheduleLine; "—" for contract-level lines, whose key is null) | mono link to SF-03:obligation | start | no | Obligation → `obligation` | yes |
| 3 | Line type | `line_type` label: `NORMAL` "Normal", `CATCH_UP` "Catch-up", `TP_CHANGE` "Transaction price change", `BREAKAGE` "Breakage", `ROYALTY` "Royalty", `RETURN` "Return", `MODIFICATION` "Modification", `OPENING_BALANCE` "Opening balance" | text | start | no | Line type → `line_type` | yes |
| 4 | State | `state`: `RECOGNIZED` "Recognized", `SCHEDULED` "Scheduled" | text | start | no | none | yes |
| 5 | Quantity | `quantity` | DS-FMT-11 | end | no | none | no |
| 6 | Amount (<currency>) | `amount.amount` | DS-FMT-04; Explain trigger `schedule_line~<id>~amount` | end | no | none | yes |
| 7 | Cumulative (<currency>) | `cumulative_amount.amount` | DS-FMT-04 | end | no | none | yes |
| 8 | Entity | `entity.code` | mono | start | no | none | no |

Contract costs binding: `GET /contracts/{id}/cost-assets?as_of&known_at&book&period` (API-R-34; `period` = the context `period_key`, which fills `period_amortization`; fields = T-CON-15 columns plus the current T-CON-16 row, API-C-14).

| # | Header | Field | Format | Alignment | Visible |
|---|---|---|---|---|---|
| 1 | Asset | `plan_code` · `payee` | mono | start | yes |
| 2 | Kind | `cost_kind`: `OBTAIN` "Cost to obtain", `FULFILL` "Cost to fulfil" | text | start | yes |
| 3 | Capitalised on | `capitalization_date` | DS-FMT-16 | start | yes |
| 4 | Capitalised (<currency>) | `capitalized_cum` | DS-FMT-04 | end | yes |
| 5 | Amortised to date | `amortized_cum` | DS-FMT-04 | end | yes |
| 6 | Impaired | `impaired_cum` | DS-FMT-04 | end | yes |
| 7 | Carrying amount | `carrying_amount` | DS-FMT-04; Explain trigger | end | yes |
| 8 | Amortisation | `amortization_pattern` label ("Straight line", "Proportional to related revenue") · `amortization_start_date` · `amortization_months` months | text | start | yes |
| 9 | Remaining months | `remaining_months` | DS-FMT-21 | end | yes |
| 10 | Amortisation in <period label> | `period_amortization` (04 API-R-34) | DS-FMT-04 | end | yes |

States: empty revenue schedule "No schedule lines for this range." with "Show all periods"; cost panel not rendered when empty; error SCR-ST-05. Sample world: K-09 `SF-ORD-10417` asset `SALES-2026` capitalised 6,480.00, Sep 2026 amortisation 177.37 (asserted, J-12.3, WLD-X-20); K-01 O1 Sep 2026 normal line 9,764.38 (WLD-X-02). Test hooks: grids by name "Revenue schedule", "Contract costs"; `SF-03-grid-revenue-schedule`, `SF-03-grid-contract-costs`.

### 4.4 Billing tab (SF-03:billing)

| Field | Value |
|---|---|
| Route | `/contracts/:contractId/billing` (RT-15) |
| Purpose | Labelled balances per legal entity, invoices and credit memos, billing plan and usage commitments (REQ-UX-004; REQ-BIL-003, REQ-BIL-007; J-11.4) |

Panels in order:

1. "Balances by entity" static table (transposed), binding `GET /contracts/{id}/balances?as_of&known_at&book`. Rows are balances, columns are entities, caption "Balances by entity (<currency>)". Row order and labels: Contract liability; Contract liability, current portion; Contract asset; Contract asset, current portion; Unbilled receivable; Accounts receivable; Refund liability; Return asset; Deposit liability; Customer incentive asset; Consideration payable to a customer; Contract cost asset; Loss provision. A cell is an Explain trigger where its row names the explanation of that balance (rev 1.24; 04 API-S-ContractBalance `links`, rev 1.174): `links.explain_<field>`, the address `contract_version_balance~<balance id>~<field>` with the `period` of the read, followed as sent. At 04 rev 1.174 the row names Contract liability, Contract asset and Unbilled receivable; a cell whose balance has no link, or a null one, prints its amount without a trigger. A row whose value is 0.00 in every entity collapses under the switch "Show zero balances" (off by default). [J] Refund liability and return asset are presented on their own rows, apart from contract liability and asset (REQ-RPT-005, J-09-AC-2). `net_position` is never rendered (D-12).
2. "Invoices and credit memos" DataGrid, binding `GET /contracts/{id}/events?event_type=BILLING_RECORDED&event_type=CREDIT_MEMO_RECORDED` (API-R-30).

| # | Header | Field | Format | Alignment | Sort | Visible |
|---|---|---|---|---|---|---|
| 1 | Document | `payload.invoice_number` or `payload.credit_memo_number` | mono | start | no | yes |
| 2 | Kind | "Invoice" or "Credit memo" by `event_type` | text | start | no | yes |
| 3 | Issue date | `payload.issue_date` | DS-FMT-16 | start | yes (default descending) | yes |
| 4 | Obligation | `payload.obligation_key` | mono link | start | no | yes |
| 5 | Service period | `payload.service_period_start – payload.service_period_end` | DS-FMT-20 | start | no | no |
| 6 | Invoiced (<currency>) | `payload.amount` for invoices | DS-FMT-04 | end | no | yes |
| 7 | Credited (<currency>) | `payload.amount` for credit memos | DS-FMT-04 | end | no | yes |
| 8 | Effective date | `effective_date` | DS-FMT-16 | start | no | yes |
| 9 | Origin | `origin` label and `source_row` link ("<file> row <n>") | text link | start | no | yes |
| 10 | Recorded at | `recorded_at` | DS-FMT-17 | start | no | no |

3. "Billing plan" static table from `GET /schedule-lines?contract=<id>&schedule_kind=BILLING_PLAN` (04 API-R-35 `schedule_kind`, E-27): Period (`period.name`), Amount (<currency>) (`amount`). Rendered when rows exist. A due-date column is deferred to later, because API-S-ScheduleLine carries the period and no due date.
4. "Minimum commitment" panel from `GET /contracts/{id}/usage-commitments?period=<period_key>` (04 API-R-28, API-S-UsageCommitment), rendered for contracts with usage commitment terms, one definition list per item: "Commitment (<period_label>)" `commitment`; "Usage" `usage_amount` followed by "(<usage_quantity> <metric>)"; "Shortfall" `shortfall`; "Status" as a DS-CMP-19 chip from `status` (04 B3-D13): `IN_PROGRESS` "In progress", `MET` "Met", `SHORTFALL` "Shortfall", followed by the text "billable at <status_date>" (rev 1.3). Each figure is an Explain trigger.

States: invoices empty "No invoices or credit memos yet. Billing arrives from imports and integrations."; balances loading skeleton; error SCR-ST-05. Sample world: K-11 invoices INV-DE-4471 54,000.00 (12 Sep 2026, O1) and INV-DE-4472 18,000.00 (15 Sep 2026, O2) from `avm-de-invoices-2026-09.csv` rows 2 and 3 (J-04.2); K-05 balances after J-09: refund liability 100.00, return asset 60.00 (WLD-X-15); K-06 refund liability 5,750.00 at 30 Sep 2026 (WLD-X-16); K-08 minimum commitment panel "Commitment (Q3 2026) 20,000.00", "Usage 15,000.00 (150,000 calls)", "Shortfall 5,000.00", "Status Shortfall billable at 30 Sep 2026" (asserted, J-11.4); K-02 billing plan 120,000.00 in Jan 2027. Test hooks: tables by caption "Balances by entity", "Minimum commitment"; grid "Invoices and credit memos"; `SF-03-grid-balances`, `SF-03-pane-minimum-commitment`.

**As bound to API-R-30 of 1.0 (rev 1.62, CTR-23).** Column 9 "Origin" reads by the rule of the Events panel of SF-03:obligation (§5.6 "As bound"): "Manual" for an event a person recorded, "Import row <n>" for an event with a source row, else the name of the `origin` literal — an integration's invoice reads "Integration", an API client's "API client <name>". The cell is text: the file's name and the link of "<file> row <n>" to the import row drawer are not bound (§5.6).

### 4.5 Journals tab (SF-03:journals)

| Field | Value |
|---|---|
| Route | `/contracts/:contractId/journals` (RT-16) |
| Purpose | The contract's subledger lines, with origin periods and reversals, drilling to journal runs (REQ-UX-004; REQ-RPT-017) |
| Binding | `GET /subledger-lines?contract=<id>&book&period&account_role&origin_period&known_at` (API-R-36); saved-view code `SF-03:journals` |

| # | Header | Field | Format | Alignment | Sort | Filter | Visible |
|---|---|---|---|---|---|---|---|
| 1 | Period | label of `period_key` (04 API-S-SubledgerLine) | DS-FMT-19 | start | yes (default descending) | Period → `period` | yes |
| 2 | Origin period | label of `origin_period_key` | DS-FMT-19; "—" when null | start | no | Origin period → `origin_period` | yes |
| 3 | Effective date | `effective_date` | DS-FMT-16 | start | no | none | yes |
| 4 | Entry | `entry_kind` label (catalogue `je.entryKind.<literal>`, for example `REVENUE_RECOGNITION` "Revenue recognition", `NETTING_RECLASS` "Netting reclass") | text | start | no | none | yes |
| 5 | Account role | `account_role` label (catalogue `accountRole.<literal>`, for example `CONTRACT_LIABILITY` "Contract liability"); for `BILLING_CLEARING` followed by " · <clearing purpose label>" | text | start | no | Account role → `account_role` | yes |
| 6 | Account | `account.code` · `account.name` (API-S-Ref; 04 B3-D12) | mono code | start | no | none | yes |
| 7 | Currency | `amount_txn.currency` | mono | start | no | none | yes |
| 8 | Debit | `amount_txn` when `dr_cr = D` | DS-FMT-04 | end | no | none | yes |
| 9 | Credit | absolute `amount_txn` when `dr_cr = C` (format module, DS-FMT-06) | DS-FMT-04 | end | no | none | yes |
| 10 | Obligation | obligation key of `obligation_id`, resolved through the contract's `GET /contracts/{id}/obligations` | mono link | start | no | none | yes |
| 11 | Post-reopen | `is_post_reopen` | DS-FMT-22 | start | no | none | no |
| 12 | Reverses | "Yes" when `posting_kind = VOID_REVERSAL` or `entry_kind = NETTING_RECLASS_REVERSAL`, else "No". A link to the reversed line is deferred to later, because API-S-SubledgerLine has no `reverses_line_id` | DS-FMT-22 | start | no | none | no |
| 13 | Journal run | link "View run" to SF-06:run from `journal_run_id` (04 API-S-SubledgerLine); "—" when null | text link | start | no | none | yes |
| 14 | Recorded at | `recorded_at` | DS-FMT-17 | start | no | none | no |

Every Debit and Credit cell is an Explain trigger (`subledger_line~<id>~amount`). States: empty "No journal lines yet. Lines appear once the contract is active and events post."; error SCR-ST-05. Sample world: `BG-AVM-0030` after J-26: reversal lines in Sep 2026 with origin periods Jul 2026 and Aug 2026, Reverses = Yes (J-26-AC-2). Test hooks: grid "Journal lines"; `SF-03-grid-journal-lines`.

### 4.6 Modifications tab (SF-03:modifications)

| Field | Value |
|---|---|
| Route | `/contracts/:contractId/modifications` (RT-17) |
| Permissions | `contract.read`; "New modification" and "Change subscription" `modification.create` |
| Binding | `GET /contracts/{id}/modifications?status&effective_from&effective_to` (API-R-31) |

| # | Header | Field | Format | Alignment | Visible |
|---|---|---|---|---|---|
| 1 | Reference | `reference`, link to SF-07:detail; falls back to `modification_no` | mono link | start | yes |
| 2 | Kind | `kind` label (catalogue `modification.kind.<literal>`: `ADD_OBLIGATION` "Add obligation", `QUANTITY_CHANGE` "Quantity change", `PRICE_CHANGE` "Price change", `TERM_CHANGE` "Term change", `UPGRADE` "Upgrade", `DOWNGRADE` "Downgrade", `CO_TERM` "Co-term", `RENEWAL` "Renewal", `EARLY_RENEWAL` "Early renewal", `CANCELLATION` "Cancellation", `TERMINATION` "Termination", `REMOVE_OBLIGATION` "Remove obligation", `VC_CHANGE` "Variable consideration change", `OTHER` "Other") | text | start | yes |
| 3 | Effective date | `effective_date` | DS-FMT-16 | start | yes |
| 4 | Treatment | `treatment_summary` label (§7.5 table) | text | start | yes |
| 5 | Status | `status` | chip (§0.8) | start | yes |
| 6 | Catch-up (<currency>) | `impact_summary.catch_up_total` (04 API-S-Modification list items) | DS-FMT-31 | end | yes |
| 7 | Prepared by | `preparer.display_name` (04 API-S-Modification `preparer`, API-S-Actor; rev 1.12) | user | start | yes |
| 8 | Template mode | `template_mode` (`prospective`, `retrospective`, `pob_price_change` labels "Prospective", "Retrospective", "Price change") | text | start | no |

Toolbar (rev 1.29; the supervisor's ruling of 2026-10-01): none of its own — "New modification" and "Change subscription" are commands of the header of an ACTIVE contract (§4.1.6), the one place of both. Empty: title "No modifications", description "Changes to scope or price appear here with their classification and approval.", action "New modification" for a holder of `modification.create` on an ACTIVE contract. Sample world: K-02 `CR-MARROWBY-2026-09` Upgrade, 16 Sep 2026, Prospective, Applied, catch-up 0.00 (J-05); K-03 `CR-CASTELLAN-2026-09` Other, 10 Sep 2026, Cumulative catch-up, Applied, catch-up +91,463.41 (J-06); K-01 `CR-PELLWORTH-2026-07` Separate contract (WLD-K-01b). Test hooks: grid "Modifications"; `SF-03-grid-modifications`.

### 4.7 History tab (SF-03:history)

| Field | Value |
|---|---|
| Route | `/contracts/:contractId/history` (RT-18); view in `?view=activity|versions|audit` |
| Permissions | `contract.read`; the "Audit trail" option renders only with `audit.read`, held for all entities (rev 1.34, SCR-PERM-02) |
| Purpose | Activity timeline, immutable contract versions and field-by-field comparison, and the audit trail slice (REQ-CON-014, REQ-UX-004 "History" and "Audit"; J-05-AC-2) |

View switch DS-CMP-31 "Activity | Versions | Audit trail".

- **Activity** (DS-CMP-12 record activity variant, read-only; there is no comment composer in 1.0 because 04 has no comment resource [F]): binding `GET /contracts/{id}/history` with items `{occurred_at, kind: EVENT|CALCULATION|APPROVAL|IMPORT, actor, summary_key, params, links}` (04 API-S-ContractHistoryItem, E-116). Filters: event-type chips "All", "Changes" (`kind=EVENT`), "Approvals" (`kind=APPROVAL`), "Calculations" (`kind=CALCULATION`), "Imports" (`kind=IMPORT`); switch "Show system events" (`include_system=true`). The chip "Imports" is not rendered until the route answers items of kind IMPORT (item CTR-HISTORY-IMPORT-1; rev 1.12, ruling R-93 (b)): today an imported event reads as a system event under "Show system events". Paging "Load older activity". Item copy examples: "Maya Chen recorded Return of 2 units on O1"; "System computed version 5 (engine 1.0.0)"; "Priya Raman approved Manual event"; "Import `avm-de-invoices-2026-09.csv` appended 2 events". Migrated history rows display "Migrated, unattributed" (BR-MIG-04). Rev 1.39 (item HIST-CALC-CHIP-1; 04 API-S-ContractHistoryItem rev 1.143): every computation is SYSTEM's, so the chip "Calculations" reads with `include_system=true` whatever the switch says, the switch keeping the member's choice for the other chips, and an event of the audit trail whose `on_behalf_of` (API-S-Actor; SCREENS_B §6.3) names the principal it was written for reads "<actor> on behalf of <name>" ("System on behalf of Maya Chen"), which an Activity item cannot, because API-S-ContractHistoryItem names no such principal.
- **Versions**: DataGrid over `GET /contracts/{id}/versions?book` with columns Version (`version_no`), Known at (DS-FMT-17), Cause (first cause event label and effective date), Engine (`engine_version`, mono), Transaction price, Revenue to date, Status in book (chip). Selecting two rows enables "Compare versions" → `GET /contracts/{id}/versions/compare?from=<n>&to=<m>` rendered as a DS-CMP-16 field diff table grouped by obligation, with a Delta column for amounts (DS-FMT-31) and the switch "Show unchanged fields". Rev 1.12 (ruling R-93 (b), (c)): the Delta column is not rendered until the compare route answers the difference (item CTR-COMPARE-DELTA-1; DG-FE-08 leaves money arithmetic to the server), and the switch is not rendered because the route answers changed fields only. The table lists the fields the screen has labels for, never a signed position (D-12), and the line "<n> changes in internal fields are not listed." says how many it left out; an obligation that only the later version holds reads "Obligation — → <key>", marked added.
- **Audit trail** (DS-CMP-12 audit variant): `GET /audit-events?object_type=contract&object_id=<id>` plus the latest verification `GET /audit-events/verifications?limit=1` for the header "Audit chain verified <timestamp>".

States: Activity empty "No activity yet. Changes, approvals and calculations appear here."; Versions empty (drafts) "No computed versions yet."; compare with fewer than two selected: button `aria-disabled` with reason "Select two versions to compare."; audit no permission: option not rendered; (rev 1.34) a read of the audit events refused with 403 removes the option and renders "Activity". Sample world: K-02 compare version before and after J-05: O1 remaining allocation 155,178.08 → 148,451.55 (Delta (6,726.53), not rendered under rev 1.12); added obligation allocation — → 66,726.53 (asserted fields, J-05-AC-2; PRD rev 1.21). Test hooks: radiogroup "History view"; grid "Contract versions"; the compare table caption reads "Changes from version <n> to version <m>"; `SF-03-grid-versions`, `SF-03-diff`; `SF-03-pane-activity`, `SF-03-pane-audit` (rev 1.12).

### 4.8 Documents drawer

| Field | Value |
|---|---|
| Placement | Header button "Documents <n>" opens a standard drawer (DS-CMP-09, `--drawer-w`), URL `drawer=documents` |
| Permissions | Read `contract.read`; upload `contract.create`; void attachment `contract.create` with a reason |
| Binding | `GET /attachments?subject_type=contract&subject_id=<id>`; upload `POST /files` (purpose `ATTACHMENT`) then `POST /attachments`; `POST /attachments/{id}/void`; download `GET /files/{id}/content` |

Content: "Contract reference" definition (`document_ref`, "Not set" when null, which also fails the activation checklist); static table File (name, link), Description, Size, SHA-256 (DS-FMT-23 middle ellipsis with copy), Uploaded by, Uploaded at (DS-FMT-17), row action "Void attachment" (confirmation with reason, rendered while no approved request references the contract, T-PLT-30 DB-11). Footer primary "Upload document" opening the file chooser; accepted types and limit copy "PDF, DOCX, XLSX, CSV, PNG, JPG or EML, at most 25 MiB." (ERR-37). Evidence attached to estimates and events is listed in a second table "Evidence on events and estimates" (read-only; `GET /attachments?contract_id=<id>`, 04 API-R-12, excluding the attachments whose subject is the contract itself). Empty: "No documents yet. Attach the order form or signed contract so reviewers can see the terms." Test hooks: `getByRole("dialog", {name: "Documents"})`; `SF-03-drawer-documents`.

### 4.9 Command drawers and confirmations

All form drawers are DS-CMP-09 modal drawers with sticky footers "Cancel" and the primary action; commands send `Idempotency-Key` and `If-Match: "s<head_stream_version>"`; problem `errors[]` map to fields (DS-CMP-21). Manual events route through `MANUAL_EVENT` approval (BR-REC-01), so their primary action reads "Submit for approval", and success toasts read "Submitted for approval. Request <request no> is waiting for approval." Each event drawer shows an impact preview panel below the fields, bound to `POST /contracts/{id}/events/preview` (04 API-R-30; 202 job whose `result.summary` is API-S-ImpactSummary) after the fields validate; the panel title is "Preview" and it lists the figures named per drawer.

#### 4.9.1 Record Step 1 review, record assessment and record criteria met

**Record Step 1 review** (rev 1.11; supervisor ruling R-89). Fields: five criteria (radio Yes / No, optional note each) with labels "Approved and committed (ASC 606-10-25-1(a))", "Rights identified (ASC 606-10-25-1(b))", "Payment terms identified (ASC 606-10-25-1(c))", "Commercial substance (ASC 606-10-25-1(d))", "Collectibility probable (ASC 606-10-25-1(e))"; Credit grade (text, optional); Mitigation (select "None", "Advance payment", "Stop service"); Termination right (select "None", "Customer", "Entity", "Both"); Substantive penalty (Yes / No); Notice days (integer); Rationale (reason field); Evidence (attachments, optional). While "Collectibility probable" is No the drawer shows two more fields, the members of the `NOT_A_CONTRACT` questionnaire that ENGINE_SPEC S02-R-07 reads while the contract is behind the gate (04 T-CON-19): "Consideration received is non-refundable (ASC 606-10-25-7)" (radio Yes / No, required; `consideration_nonrefundable`) and "Transfer stopped with no further obligation, since (ASC 606-10-25-7(c))" (date, optional, help "The date from which control of what the consideration received relates to has transferred, the transfer has stopped and no obligation to transfer more remains. The ASC 606 book then recognises non-refundable consideration received as revenue from that date; the IFRS 15 book does not use the date, because IFRS 15.15 has no such event."; `event_c_met_on`; ENGINE_SPEC S02-R-07 (c) applies it only in a book where POL-012 is `ENABLED`, which is forced for ASC 606 and `DISABLED` for IFRS 15, and only with non-refundable consideration). Primary "Submit for review". Commands: `POST /judgements` (subject contract; topic `NOT_A_CONTRACT` when "Collectibility probable" is No, else `COLLECTIBILITY`; the criteria, notes, credit grade, mitigation and termination are the record's questionnaire, and a `NOT_A_CONTRACT` record carries its two members beside them), then `POST /judgements/{id}/submit`. A 422 on `questionnaire.consideration_nonrefundable` or `questionnaire.event_c_met_on` shows on its field. No event is appended. Toast "Step 1 review <judgement no> submitted for review."; the Step 1 path (§4.1.3) then reads "waiting for review by a Revenue Reviewer". Rev 1.66: the two commands are two requests. A refusal of the second leaves the record a draft, which the drawer keeps while it stays open — the next press sends that record again — and which §4.1.3 names with "Discard" once the drawer is closed.

**Record assessment** (`DRAFT`) **and Record criteria met** (`NOT_A_CONTRACT`) (rev 1.11). Offered once the latest Step 1 record is `REVIEWED` (§4.1.3). A modal drawer that states, read-only, the Step 1 review ("<judgement no> · <conclusion>"), "Reviewed by <reviewer>, <DS-FMT-17 timestamp>", the outcome ("Collectibility probable" for a record of topic `COLLECTIBILITY`, "Collectibility not probable" for topic `NOT_A_CONTRACT`) and the books (the enabled books of the contracting entity, by label). Effective date: for a `DRAFT` contract the inception date, stated and not editable (the assessment in force at inception is the book's latest, supervisor ruling R-77 (2)); for a `NOT_A_CONTRACT` contract a date field that starts at today, the current date in the contracting entity's time zone (05 TZ-02). Primary "Record assessment" or "Record criteria met". Command: `POST /contracts/{id}/events` with one `COLLECTIBILITY_ASSESSED` per enabled book (`book`, `is_probable`, `credit_grade`, `mitigation`, `judgement_record_id` of the reviewed record) and `If-Match` (ACT-01). A 422 `REQ-POL-008` on `events.<i>.effective_date` shows on the date field; any other problem shows in the drawer's banner. A 422 `REQ-POL-008` on `events.<i>.payload.judgement_record_id` refuses the record itself (rev 1.72; §4.1.3). Whatever reason the API states — the record was reviewed before the draft was last replaced ("Use a judgement record reviewed after the draft was last replaced.") or before the not-a-contract gate, it is of another topic or book, it answers No to a criterion — no other date leads out of it: the banner says the API's sentence and offers "Record a new Step 1 review". The offer closes this drawer and opens "Record Step 1 review" in its place; one drawer is open at any time (DS-CMP-09). Behind the not-a-contract gate, where the header holds the one command of the path (§4.1.6), the offer is the way from a refused record to a new review. The drawer compares no time itself and refuses nothing the API takes. Toast "Assessment recorded." or "Criteria met recorded. Submit the contract for activation." For a not-probable outcome on a `DRAFT` contract the drawer says "When every book is assessed not probable the contract goes behind the not-a-contract gate: receipts post to deposit liability until the criteria are met." (REQ-CON-003; the gate is the API's decision, 04 §16.3 (c)). A record the drawer is handed without its reviewer is named "Record <judgement no> · <status>", the status in the words of §0.8 (rev 1.66).

The screen records the assessment only for a `REVIEWED` record. That is stricter than the PRD SM-02 guard "Judgement `NOT_A_CONTRACT` submitted": the API still admits an assessment that cites a `SUBMITTED` record (04 §16.3 (b)), and the screen does not use that path because the appended assessment would make the record's pending review stale (item STEP1-JR-STALE-1). J-03.3 sample: collectibility Yes, credit grade B, termination Customer, penalty Yes, notice 60 days; after the review and the assessment the Step 1 status line becomes "Stand-alone contract".

#### 4.9.2 Record distinct review

Fields: Obligation (read-only key and product); Conclusion (radio "Distinct" `distinct`, "Not distinct: combine with another obligation" `nondistinct`; E-105 → `distinctness`); Combine with (obligation select, rendered and required for `nondistinct` → `integrates_into_obligation_key`); Basis (select "Customer can benefit on its own (ASC 606-10-25-19(a))", "Customer can benefit with readily available resources (ASC 606-10-25-19)", "Separately identifiable (ASC 606-10-25-21)" → `codification_refs` `["606-10-25-19(a)"]`, `["606-10-25-19"]` or `["606-10-25-21"]`); Rationale (`rationale`). Primary "Save review". Command `POST /contracts/{id}/obligations/{obligation_key}/distinct-review` (04 §16.1) → 201 `{judgement_record_id, approval_request_id}`: a `POB_DISTINCT_OVERRIDE` judgement record submitted for review; the Step 2 row then shows "Recorded" and the tracker step shows In review until it is reviewed. J-03.4 sample: O2 `AVM-IMPL-PLUS` "Customer can benefit with readily available resources (606-10-25-19)".

#### 4.9.3 Record delivery, progress, milestone, cost and return

| Drawer | Fields (payload of 04 §16.3) | Preview figures |
|---|---|---|
| Record delivery | Obligation; Quantity (> 0); Trigger ("Delivery", "Acceptance", "Sell-through", "Bill-and-hold", "Control transfer"); Effective date; Reference; Evidence (required for acceptance); Comment | Revenue on the effective date; delivered quantity after; remaining quantity |
| Record progress | Obligation; Measure ("Output percent", "Labour hours"); Cumulative progress (percent input, ratio stored); Hours to date (labour hours only); Effective date; Evidence (required); Comment | Progress before → after; revenue change; catch-up |
| Record milestone | Obligation; Milestone code; Cumulative weight (percent); Effective date; Evidence (required) | Revenue on the effective date |
| Record cost | Purpose ("Progress input", "Cost to obtain", "Cost to fulfil"); Obligation (optional); Amount; Wasted (Yes / No); Uninstalled material (Yes / No); Payee; Plan code; Incremental (Yes / No); Clawback (Yes / No); Effective date; Evidence (required) | Progress before → after; revenue change; capitalised amount and amortisation period for costs to obtain or fulfil |
| Record return | Obligation; Return reference (for example RMA number, stored as `reason`); Quantity returned; Effective date; Condition ("Resaleable", "Not resaleable", appended to `reason`); Credit memo number (optional); Credit amount (optional); Evidence | Cumulative revenue; refund liability; return asset; remaining expected returns |

"Record return" appends `RETURN_RECORDED` and, when a credit memo number is given, `CREDIT_MEMO_RECORDED` in one `events` array. Errors: `RETURN_EXCEEDS_DELIVERED` and `REFUND_EXCEEDS_BILLED` render their IMP-24 and IMP-25 messages on the quantity and credit fields (J-09-ALT-1, J-09-ALT-2). J-09.2 sample: `RMA-DE-0077`, 2 units, 18 Sep 2026, Resaleable, `CM-DE-0102` 200.00; preview cumulative revenue 9,700.00 (unchanged), refund liability 100.00, return asset 60.00, remaining expected returns 1 (asserted).

**What the preview panel says of its dry run (rev 1.79; the supervisor's order of 2026-10-03 on the lane's measurement; register index 300 on the screens, with the defect measured beside it; 04 API-S-Job `result` rev 1.314 and §16.10 "Who reads a stored preview"; §0.7 SCR-ST-12).** The panel of the five drawers lists the figures of `result.summary` once the job of the dry run has ended with one. Where the job ended without one, the panel says which of three things happened, each inserted after load and announced. (1) A job that ends `FAILED` shows the negative banner of SCR-ST-12, titled "The preview failed. Nothing was committed.", with the messages of the job's problem — each `errors[].message`, and without one the problem's title — then "Reference <job id prefix>." and the action "Retry", which asks for the preview of the same fields again. (2) A job that ends `CANCELLED` and left no summary shows the same banner titled "The preview was cancelled. Nothing was committed.", with the reference and "Retry". (3) A summary the reader is not shown — `result.summary_withheld` true: the API answers the summary of a dry run to a reader of the job who holds `contract.read` for every entity of the contract's combination group, and tells every other reader that one exists — shows the info banner "You are not shown this preview" with the text "The preview holds figures of legal entities outside your access. It is shown to people whose access covers every entity of the contract's combination group."; the job answers this reader no figure, so none stands beside the banner, and "Retry" is not offered. "Submit for approval" waits for the preview in none of the three: the API decides the submission. **Withdrawn:** the sentence "No figures change." (`contracts.drawer.preview.none`). The panel showed it for every finished job without a summary — on the build before this revision a dry run that had failed, as measured — and no answer of the API states it: a dry run that succeeds stores a summary, and the panel lists its catch-up and its periods — required members of API-S-ImpactSummary — also where each is 0.00. A finished job that answers neither a summary nor `summary_withheld` and is not cancelled reads as failed. Copy keys: `contracts.drawer.preview.failed`, `.cancelled`, `.withheld.title`, `.withheld.text`; the action is `common.job.retry` "Retry".

#### 4.9.4 Apply hold and release hold

Apply hold: Level ("Contract", "Obligation" with an obligation select); Hold type ("Recognition hold" `recognition`, "Journal export hold" `journal_export`); Reason (minimum 10 characters, BR-PLT-08). Primary "Apply hold"; `POST /contracts/{id}/apply-hold`. Release hold: Hold (select of open holds "<type label> · <reason> · applied <date>"); Comment (minimum 10 characters). Primary "Release hold"; `POST /contracts/{id}/release-hold` (rev 1.75: bound, below). J-13 step 4 sample (SCREENS_B journey context): hold on `BG-AVM-0021` reason "Customer dispute on invoice INV-US-3988" (WLD-B-05).

**Release hold as bound to 04 §16.1 and §16.2 rev 1.299 (rev 1.75; lane SECFIX-ACT's item HOLD-RELEASE-READ-1 on the screens, a release blocker; 04 T-CON-20, API-R-28, API-S-Contract and API-S-Obligation `holds`).** The drawer lists every open hold of the contract: the holds of the whole contract, which API-S-Contract lists, then each obligation's own, which that obligation lists, in the order of the obligations — each list oldest first, as the API answers it. The option of a hold of the whole contract reads "<type label> · <reason> · applied <timestamp>" (DS-FMT-17) — **replaced:** "applied <date>": the read answers the instant the hold was applied and no date of the entity — and the option of an obligation's hold carries the obligation's key in front. A hold whose `release_refusal` is null is an option of the select; where one hold alone is an option it is chosen at once, and a hold the obligation pane named (§5.6) is chosen when the drawer opens from it. A hold that is not released by hand is no option: it is listed under the select, read-only, with the API's sentence (`release_refusal`) — "This hold is released by the review of judgement record <judgement no>.", "This hold is released when the Step 1 assessment that cites judgement record <judgement no> is recorded.", "A voided or terminated contract takes no hold." — and where no hold is released by hand the drawer has no select, no comment and no primary action. The screen keeps no rule of its own for which hold is released by hand: the member says it, and the command's 409 stays the backstop. The command sends `{hold_id, comment}` with `If-Match`; on its answer the toast reads "Hold released on <external id>.", the contract's reads are read again and the drawer closes. A refusal is placed as DG-FE-06 asks: a message of `comment` at the field, everything else — 409 `invalid-transition` with the API's sentence, 404 for a hold that is no longer the contract's — in the banner, and a 412 as the banner's line of a record that changed. Before rev 1.75 the drawer was not built (L5-4-Q-30): no read answered the id the command takes.

#### 4.9.5 Edit memos

Fields: Level (Contract or Obligation); Memo 1, Memo 2, Memo 3; custom attributes (key and value rows); dimensions (select per dimension); Comment (required). Primary "Save memos"; `POST /contracts/{id}/update-memos` (ACT-06; BR-CON-02).

#### 4.9.6 Void contract

Confirmation modal (DS-CMP-11, `role="alertdialog"`): title "Void contract <external id>?"; description "Its posted lines reverse in <first open period label> and the change goes to approval." (J-26.1; DS-CPY-05); Reason code (select of the E-110 subset of 04 table 3.4-R for `request-void`: `DUPLICATE` "Duplicate", `CREATED_IN_ERROR` "Created in error", `CUSTOMER_CANCELLED` "Customer cancelled", `DATA_CORRECTION` "Data correction", `ESTIMATE_CORRECTION` "Estimate correction", `OTHER` "Other"; OQ-S-17 resolved by D-76) → `reason_code`; Reason (minimum 10 characters) → `comment`; info text "Approval: 1 step when nothing has posted, 2 steps when posted lines exist." Buttons "Cancel" (initial focus) and Danger "Void contract". Command `POST /contracts/{id}/request-void`; success toast "Void submitted for approval." J-26.2 sample reason "Duplicate of BG-AVM-0029 created by a repeated CRM sync."

#### 4.9.7 Regroup lines, combine and policy override

- Regroup lines (ACT-04; REQ-CON-012): obligations (checklist), Target ("Existing contract" combobox or "New contract"), Comment. Primary "Submit regroup"; `POST /contracts/{id}/regroup`.
- Combine with another contract (ACT-04; REQ-CON-009): Contracts (multi-select combobox of the same customer or related-party group), Criterion (radio "(a) Negotiated as a package", "(b) Price of one depends on the other", "(c) Goods or services form a single obligation", citing ASC 606-10-25-9), Rationale. Primary "Submit for approval"; `POST /combination-groups` then `POST /combination-groups/{id}/submit` (rev 1.78: a proposal the drawer made and did not submit is given up, below).
- Dismiss suggestion: modal with Rationale (minimum 10 characters); `POST /combination-suggestions/{id}/dismiss` `{rationale}` (04 API-R-28, §16.14; the item becomes `DISMISSED`). WLD-K-11 sample rationale "Separate purchasing entities; negotiated independently."
- Request policy override (ACT-55): Level ("Contract", "Obligation"); Obligation; Policy (combobox over `GET /registry/parameters` whose `allowed_levels` contains `CONTRACT` or `OBLIGATION`, labelled "<POL id> <key>"); Value (control per `value_schema`); Rationale; Judgement record (required when `approval_code = JDG`, created inline and — rev 1.76 — sent for review, below). Primary "Submit for approval"; `POST /policy-overrides` then `POST /policy-overrides/{id}/submit`. Rev 1.80: not in release 1.0 — the drawer is withdrawn, below.

**The drawer "Combine with another contract" gives up the proposal it made (rev 1.78; lane F-RPS-REG's item COMBINATION-PROPOSAL-DISCARD-1 on the screens, register index 266; 04 T-CON-19 "The `COMBINATION` topic" rev 1.289, E-95 `VOIDED`, API-R-28 `POST /combination-groups/{id}/discard`).** One press sends two requests, each under the key of its step (DG-FE-05): `POST /combination-groups`, which makes a `PROPOSED` group with its draft record, and that group's `/submit`. A refused submission is shown in the drawer and the group stays `PROPOSED`; a `PROPOSED` group is listed on no screen, and its record names no contract. The drawer therefore gives up a proposal it made and did not submit. (a) A press with the form unchanged continues at the submission, the first step under the key it had, and discards nothing. (b) A press with a changed form first sends `POST /combination-groups/{id}/discard` of the group the drawer made — without a body, under a key of its own — and then proposes the changed form as a new group; a form that cannot be sent sends nothing, the discard included. (c) Closing the drawer — "Cancel", the close button or Esc, after the kit's question of a form that holds input ("Discard changes?") — sends the same discard without a question of its own; on its answer the toast reads "The combination was not submitted. Its proposal was discarded." and the drawer closes. After a discard the drawer forgets the keys of the press: the stored answer of the first step would name the discarded group again (measured through the API). A refused discard is shown as it comes — 409 "This combination waits for approval. Withdraw its request, or have it rejected." for a group whose submission the API took, "Only a proposed combination that is not submitted can be discarded." for every other state — and the drawer stays; the group is then no proposal of the drawer, so a further press proposes anew and a further close closes. A discard that gets no answer leaves the drawer and its proposal as they are ("No answer came back from the server. Try again."), and the next close sends it under the same key. **Replaced:** nothing was given up — a press with a changed form made a second `PROPOSED` group beside the first, and closing the drawer left the proposal behind (measured on the screens before the build), for good while the API had no discard. Not built: a list of the proposals that earlier sessions left; no flow stops on such a group, and it is discarded through the API.

**The judgement record of a policy override is sent for review (rev 1.76; item POLICY-OVERRIDE-RECORD-EXIT-1, a release blocker; PRD IMP-104, SM-10; 04 T-CON-19, T-CON-20 "Judgement holds", API-R-33; POLICIES §0.6 `JDG`).** For a parameter whose approval code is `JDG` one press sends four requests, each under the key of its step (DG-FE-05): `POST /judgements` (topic `OTHER`, subject the contract: a draft), `POST /policy-overrides` with the record, `POST /judgements/{id}/submit`, `POST /policy-overrides/{id}/submit`. **Replaced:** three requests — the record was created and never sent. It stayed a draft that no screen named, the override was approved over it, and on a `DRAFT` contract the activation checklist then failed on "Judgement record required: Other." with no way out on a screen (measured through the API). The record is sent once the override that rests on it exists — a refused override leaves a draft, and no review that waits for nothing — and before the override is submitted, so that no override waits for approval over a record that was not sent. The record then waits for its reviewer: the checklist's line stands until it is reviewed (§4.9.8 names the record under it), the close counts it while it waits, and an `ACTIVE` contract is on hold — a recognition hold of the whole contract — from the record's submission to its review (04 T-CON-20; measured). The field says so before the press: its help reads "The conclusion of the judgement record created with the request. The record is sent for review." and, on an `ACTIVE` contract, "The conclusion of the judgement record created with the request. The record is sent for review, and <external id> is on hold until it is reviewed." A refused step is shown in the drawer and the next press continues at it, the steps before it under the keys they had; where the record was already sent, the contract is read again although the press did not complete, because a hold may have moved its head. On the answer of the last request two toasts confirm the two requests: "Judgement record <judgement no> was submitted for review." and the override's own. Rev 1.80: withdrawn with the drawer for release 1.0, below; the rule returns with it.

**Policy overrides are not in release 1.0 (rev 1.80; supervisor ruling R-126 (b) (4) and (c); register index 308, item POLICY-OVERRIDE-WITHDRAW-1, the web half; 04 T-CON-23, API-R-13).** An approved policy override reaches no computation, so release 1.0 takes none: the API refuses every creation (`POST /policy-overrides`) by name — the other half of the item — and the screens do not offer the command. **Withdrawn:** the drawer "Request policy override" of this section, its item in the header's overflow (§4.1.6) and its item in the obligation pane's overflow (§5.1, §5.3), and with the drawer the rule of rev 1.76 above, the judgement record it created and sent for review. Nothing stands where the items stood. **Stays:** what the screens read of a policy override that exists — under "Judgement record required" (§4.9.8) a draft that a `SUBMITTED` or `APPROVED` override names is sent for review and not discarded, by the read `GET /policy-overrides?contract=<id>`; and the subject type "Policy override" of an approval request and of the inbox's filter (§15.3). The link of an explanation's source record `policy_override` (§6.3) was never built. The drawer returns with the feature, as the commit before this revision holds it. Copy keys withdrawn: `contracts.workbench.action.policyOverride`; `contracts.drawer.override.title`, `.policy`, `.value`, `.judgement`, `.judgementHelp`, `.judgementHelp.held`, `.judgementRequired`, `.submitted`. `contracts.drawer.override.valueRequired` stays: the fields of an estimate version read it.

#### 4.9.8 Activation checklist failure copy

`activation-checklist-failed` returns `errors[].rule_id` = the checklist item code (04 table 15.4-I). Before submission, the banner may also read `GET /contracts/{id}/activation-checklist` (04 API-S-ActivationChecklist `items[] {code, passed, detail}`), which evaluates the items without storing them. Banner lines and their fix links:

| Code (04 table 15.4-I) | Line | Link |
|---|---|---|
| `MANDATORY_FIELDS` | "Mandatory fields not set: <field labels>." | "Edit draft" |
| `SOURCE_REFERENCE` | "No contract reference is recorded." | "Open documents" |
| `PRODUCT_TEMPLATE_SSP` | "No product, template or SSP for <obligation key> (<product code>)." | "Open allocation" (step 4) |
| `DISTINCT_REVIEW` | "Distinct review not recorded for <obligation key> (<product code>)." (J-03-ALT-1) | "Record distinct review" |
| `COMBINATION_SUGGESTIONS` | "Combination suggestion with <external id> is open." | "Open step 1" |
| `JUDGEMENT_RECORDS` | "Judgement record required: <topic label>." | none on the line (**replaced:** "Record judgement", which was never rendered); under the item's last such line the contract's draft and pending records — "View request" on a record that names a request, "Discard" or "Send for review" on a draft (rev 1.76, below) |
| `JUDGEMENT_RECORDS`, a rejected record (rev 1.74; PRD IMP-145) | "Judgement record <judgement no> (<topic>) was rejected. Discard it, or have its author revise it and send it for review again." | "View request" (rev 1.76) and "Discard" (the command of §4.1.3 on the record the line names) |
| `STEP1_RECORD` | "Step 1 review not recorded." | "Record Step 1 review" |

**The line of a rejected record (rev 1.74; PRD IMP-145; 04 rev 1.296 table 15.4-I `JUDGEMENT_RECORD_REJECTED`).** The checklist names each rejected judgement record of the contract by its number, one line a record, whatever the record's subject — the contract, one of its obligations, an estimate version. Once a refused activation names the item, the banner reads the workspace's records that the item counts, kept by `contract_id` — the list route filters no contract; rev 1.76: one read of the three statuses, below, where rev 1.74 read `GET /judgements?status=REJECTED` — and the line whose words hold a rejected record's number carries "Discard" for a holder of `judgement.create` for the contract's contracting entity — the confirmation and the command of §4.1.3. On the discard's answer the line reads "Record <judgement no> was discarded." in the command's place; the banner stays as the API answered it until the activation is submitted again. A line whose record the read does not hold carries no command.

**The records under "Judgement record required" (rev 1.76; item POLICY-OVERRIDE-RECORD-EXIT-1; PRD IMP-104; 04 T-CON-19, T-CON-23, API-R-13, API-R-33).** The line names a topic and no record, and its link "Record judgement" was never rendered: a draft or a pending record of a topic outside Step 1 — the record of a policy override before rev 1.76 (§4.9.7), a draft that a refused submission left — was named on no screen. Once a refused activation names the item, the banner makes two reads: the workspace's records in the three statuses the item counts (`GET /judgements?status=DRAFT&status=SUBMITTED&status=REJECTED`, kept by `contract_id`; **replaced:** the read of the rejected records alone, rev 1.74) and the contract's policy overrides (`GET /policy-overrides?contract=<id>`, read with `config.read`). Under the item's last line that names no record it lists the contract's draft and pending records in number order, each as its number, its conclusion and its status in the words of §0.8 — one list for the item: the API prints its own title of a topic, which the screens do not hold, so a record is told by its number and its conclusion and not by the line of its topic. A record that names a request carries "View request" (SF-12:request of its `approval_request_id`) — a record that waits for review, and a draft that its author revised after a rejection, which keeps the rejected request; a draft that was never sent names none — for a holder of `judgement.review` for the contract's contracting entity and for the record's preparer, where the request screen is built. A draft carries one command, for a holder of `judgement.create` for the contract's contracting entity: "Discard" — the command and the confirmation of §4.1.3 — where no override of the contract that is `SUBMITTED` or `APPROVED` names the record, and "Send for review" in its place where one does. "Send for review" sends `POST /judgements/{id}/submit` with `{comment: null}`, the request the override's drawer sends for a new record; on its answer the toast reads "Judgement record <judgement no> was submitted for review.", the records are read again and the record stands in the list as one that waits for review; a refusal is shown under the record's line and the record stays a draft. **Why no "Discard" there:** the approval of an override certifies the id of its record and nothing of the record's state, so a record discarded afterwards leaves an override in force that names a record which can never be reviewed and which nothing shows. The API refuses neither the discard of such a record nor the approval of an override over a record that is not reviewed; until it does, this list is the only place on the screens that names these records, and its rule is the whole guard on the screens. An override that was rejected or withdrawn, was superseded or was never submitted names a record that is free again: its draft carries "Discard". While the overrides are not read — the read is pending, it failed, or the member does not hold `config.read` — a draft carries no command: a read that answered nothing says nothing about the record. A draft discarded from the list stays in it as "Record <judgement no> was discarded." until the activation is submitted again. The line of a rejected record carries "View request" before "Discard" (rev 1.76) by the same rule, so that the reviewer's reason is one step away.

### 4.10 Draft contract form (SF-03:new, SF-03:edit)

| Field | Value |
|---|---|
| Routes | `/contracts/new` (RT-09), `/contracts/:contractId/edit` (RT-19). RT-19 opens behind a fail-closed guard (rev 1.12; ruling R-93 (a)) until the API answers a draft as it stands (item CTR-DRAFT-READ-1): `MEMO_UPDATED` (`update-memos`, or the events route), `LINE_ATTRIBUTES_CHANGED` (an approved `ATTRIBUTE_CHANGE`) and `REGROUPED` (`regroup` before posting) can follow the booking of a `DRAFT` and change memos, a line's performing entity and SSP version, and the set of lines, so the latest `CONTRACT_BOOKED` payload is then no longer the draft. The screen reads the contract's events (`GET /contracts/{id}/events`, newest first, the whole stream) and opens the form, seeded from the latest booking that no `EVENT_VOIDED` names, only when every event after that booking is `HOLD_APPLIED`, `HOLD_RELEASED`, `COLLECTIBILITY_ASSESSED` or the `EVENT_VOIDED` of a `COLLECTIBILITY_ASSESSED` (rev 1.72): none of them changes a member of the booking. Otherwise it shows a state with the action "Back to the contract": "Changed after it was booked" — "This draft was changed after it was booked; it cannot be edited here yet." A stream that cannot be read back to its first event is treated as changed. A Step 1 assessment does not close the form (rev 1.72; supervisor ruling R-102 (c); 04 §16.1 rev 1.150; before, the state "Step 1 assessment recorded" kept the form shut on every draft whose stream held an assessment, standing or voided): the API takes the edit whatever assessments the stream holds, and `replace-draft` voids every assessment that stands. Where a `COLLECTIBILITY_ASSESSED` stands — no `EVENT_VOIDED` names it — the form opens under a warning banner above its sections, present with the page: "A Step 1 assessment is recorded on this draft." — "Saving voids it: a new Step 1 review is recorded and reviewed before the contract is activated." A voided assessment says nothing |
| Permissions | `contract.create` (ACT-01, ACT-02). The Contracting entity and Currency choices read `GET /entities` and `GET /tenant-currencies`, so a user without `config.read` sees the SCR-PERM-01 state naming "viewing configuration" (rev 1.12) |
| Purpose | Manual contract entry with lines, saved as Draft and optionally submitted for activation (REQ-CON-018) |
| Binding | Create `POST /contracts` (API-S-ContractCreate); edit of a draft `POST /contracts/{id}/replace-draft` (04 API-R-28, §16.1: an API-S-ContractCreate body with the same `external_id`, allowed while `DRAFT`, otherwise 409 `invalid-transition`). "Save and submit for activation" is two commands (rev 1.12): the save, then `POST /contracts/{id}/submit-activation` with `If-Match` of the head the save answered, because 04 §16.1 refuses `submit_for_activation: true` in the booking. `replace-draft` takes as `If-Match` the stream version the guard of RT-19 read (`"s<n>"`), not a later read of the contract; after a 412 (SCR-ST-09) "Reload" reads the contract and its events again, and the guard decides again |

Layout: form sections at `--content-max-form` start-aligned (DS-SP-05), except the lines grid, which is full-bleed below them.

| Section | Fields (label, API field, control) |
|---|---|
| Contract | External id (`external_id`, text, required); Customer (`customer_id` combobox with "Create customer <name>" option → `customer {code, name}`; that option shows the required field "Customer code", `customer.code`; rev 1.12); Contracting entity (`contracting_entity_code`, select); Currency (`transaction_currency`, select of enabled tenant currencies); Inception date (date); Signature date (date, optional); Contract reference (`document_ref`, optional; required before activation); Payment terms (text, optional) |
| Termination | Termination right (`termination.party` select "None", "Customer", "Entity", "Both"); Substantive penalty (`termination.has_penalty`); Notice days (`termination.notice_days`) |
| Classification | Commercial substance (`has_commercial_substance`, checkbox, default checked); Region; Channel; Contract type; Memo 1 to 3 |
| Lines | The line editor (`frontend/src/components/line-editor`; the form-held variant of DS-CMP-10, DESIGN_SYSTEM rev 1.7; rev 1.12): the grid of the form's own lines, saved with the form in one body, with the DS-CMP-10 anatomy, keyboard (one tab stop with a roving `tabindex`, cell navigation, Enter, F2 or a printable character to edit, Enter and Tab to commit, Esc to cancel) and ARIA, and one DS-CMP-21 control in each cell (typed dates as the DataGrid's date editor, a select for Performing entity and Scope, the combobox for Product). A new line starts with the key `O<n>`; "Out-of-scope amount" takes input only while the scope differs. Columns: Obligation key (required, unique), Product (combobox, required), Stratification, Quantity (non-zero), Total price (money, contract currency), Unit price (optional), Start date, End date (≥ start), Performing entity (select, default contracting entity), SSP version (optional label), Scope (select of E-77 labels, default "In scope (ASC 606)"), Out-of-scope amount (required when scope differs), Memo 1 to 3. Buttons "Add line" and "Remove line"; at most 500 lines |

Footer (sticky): "Cancel", "Save draft" (secondary), "Save and submit for activation" (primary). Validation per DS-CMP-21: cross-field messages "Enter an end date on or after <start date>." and "Obligation key <key> is used twice."; product price outside range is not a form error (the allocation walk shows it). Success: navigate to SF-03 with toast "Draft saved." or the submission toast of §4.1.9; an activation refused after the save (409 `activation-checklist-failed`) opens SF-03 with a warning toast of two lines (DS-CMP-22), and "Submit for activation" on SF-03 then lists every failed item with its fix (§4.9.8). A new manual contract has no Step 1 review yet (ruling R-89), so when `STEP1_RECORD` is among the failed items SF-03 opens with step 1 of the tracker expanded (`?step=1`, §4.1.3) and the toast reads "Draft saved. Not submitted: record the Step 1 review first."; otherwise it reads "Draft saved. Not submitted: <the message of the one failed item>" or "Draft saved. Not submitted: <n> checklist items have not passed."; when the activation command gets no answer it reads "Draft saved. Not submitted: the server could not be reached." (rev 1.12). States: dirty navigation "Discard changes?"; submitting; server `validation-failed` mapped to fields and grid cells. Test hooks: form heading "New contract"; grid "Contract lines"; `SF-03-new-page`, `SF-03-edit-page`; `SF-03-grid-lines`.

Light and dark for §4.2 to §4.10: DataGrids and static tables use DS-CMP-10 tokens; diff tints C52 to C54 with markers; drawers `--bg-raised`. Accessibility: each tab root is a `section` with an `h2` equal to the tab label; drawers follow APG Dialog; the Versions compare table has a caption and marker prefixes (DS-CMP-16).

## 5. SF-03:obligation Obligation detail pane

### 5.1 Summary

| Field | Value |
|---|---|
| Screen id and route | SF-03:obligation, `/contracts/:contractId/obligations/:obligationId` (RT-11); panel tab in `pane=overview|attributes|ssp|schedule|events` |
| Roles and permissions | Read `contract.read`. "Record event" items `event.record` (ACT-09); "Change price" `modification.create` (ACT-07); "Change attributes" `event.record` (ACT-54); "Request SSP override" `contract.create` (ACT-21); "Request policy override" `contract.create` (ACT-55; rev 1.80: not rendered in release 1.0, §4.9.7); "Apply hold" and "Release hold" `contract.create` (ACT-13; rev 1.75: the permission 04 API-R-28 asks — **replaced:** `adjustment.create`); "Void event" `event.record` |
| Purpose | Everything about one performance obligation: its figures with proportion bars, attributes, SSP derivation and allocation, schedule and events, each figure explainable (PRD SF-03; D-60) |
| REQ | REQ-UX-003, REQ-UX-005, REQ-POB-001 to REQ-POB-009, REQ-SSP-006, REQ-SSP-011, REQ-ALC-009, REQ-REC-021, REQ-MOD-021 |
| Journeys | J-03.4, J-03.6, J-03.7, J-08.1 to J-08.3, J-08-ALT-1, J-16.4, J-19.6, J-19.7 |

### 5.2 Wireframes

1440 px, "SSP and allocation" panel:

<!-- WF:obligation-ssp-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Contracts > NS-SO-DE-5004 . Hollenbrand Medizintechnik (Demo) (Active)       [*New modification] |
| Work              |  Obligations 2    Estimates 0    Schedules    Billing    Journals    Modifications 0    History  |
|    Home           |  ============                                                                                    |
| |* Contracts      |+----------------------------+  +----------------------------------------------------------------+|
|    Schedules      || [Filter obligations___] {So|  | Sensor gateway unit  O1 <Point in time>   [Record event v] [Cha||
|    Close          || 2 obligations . Allocated (|  | Obligation figures (EUR)                                       ||
|    Journals       |||* Sensor gateway unit   89,|  | Allocated       Recognized        Scheduled      Awaiting trigg||
|    Reports        |||* O1 <Point in time> 01 Sep|  | 89,174.31 fn    53,504.59 fn ###.. 0.00 fn        35,669.72 fn ||
| ----------------  ||  Platform support, 12   18,|  | Overview   Attributes   SSP and allocation   Schedule   Events ||
| Govern            ||  O2 <Over time><Ratable> 15|  |                         ==================                     ||
|    Approvals    3 ||                            |  | SSP derivation                                                 ||
|    Policies       ||                            |  |  SSP book version DE-LIST 2026 . Method Observable . Unit list ||
|    Data           ||                            |  |  Low 81,000.00    Mid 90,000.00    High 99,000.00              ||
|                   ||                            |  |  Stated price 90,000.00 . Inside range . Selected SSP 90,000.00||
|                   ||                            |  | Allocation                                                     ||
|                   ||                            |  |  Total contract SSP 109,000.00 . Weight 82.57% fn              ||
|                   ||                            |  |  Allocated 89,174.31 fn . Allocation adjustment (825.69) fn    ||
|                   |+----------------------------+  | [Request SSP override]                                         ||
| Settings          |                                +----------------------------------------------------------------+|
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:obligation-ssp-1440 -->

1280 px:

<!-- WF:obligation-ssp-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Contracts > NS-SO-DE-5004 . Hollenbrand Medizintechnik (Demo) (Active)       [*New modification] .|
| H  |  Obligations 2    Estimates 0    Schedules    Billing    Journals    Modifications 0    History   |
| *Ct|+-----------------------+ +-----------------------------------------------------------------------+|
| Sc || [Filter____] {Sort v} | | Sensor gateway unit  O1 <Point in time>   [Record event v] ..         ||
| Cl || 2 obligations         | | Allocated      Recognized      Scheduled     Awaiting trigger         ||
| Jn |||* Sensor gateway unit | | 89,174.31      53,504.59       0.00          35,669.72                ||
| Rp |||* O1  89,174.31       | | Overview  Attributes  SSP and allocation  Schedule  Events            ||
| -- ||  Platform support     | | SSP book version DE-LIST 2026 . Observable                            ||
| Ap ||  O2  18,825.69        | | Low 81,000.00  Mid 90,000.00  High 99,000.00 . Inside range           ||
| Po ||                       | | Selected SSP 90,000.00 . Weight 82.57% . Allocated 89,174.31          ||
| Da ||                       | | Allocation adjustment (825.69)                                        ||
|    ||                       | +-----------------------------------------------------------------------+|
|    ||                       |                                                                          |
| Se |+-----------------------+                                                                          |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:obligation-ssp-1280 -->

### 5.3 Regions and components

| Region | Component | Content |
|---|---|---|
| Pane header | DS-CMP-06 obligation variant | `h2` = `product.name` (`--text-title-md`); identifier `obligation_key` (mono); outline and state chips as in §4.2; actions: "Record event" menu button, "Change price", overflow ("Change attributes", "Request SSP override", "Request policy override" (rev 1.80: not rendered in release 1.0, §4.9.7), "Apply hold", "Edit memos", "Copy link") |
| Figures | DS-CMP-06 compact strip (four cells), DS-CH-05 bars | §5.5 |
| Panel tabs | DS-CMP-07 panel variant | Overview · Attributes · SSP and allocation · Schedule · Events |
| Panel content | definition lists, DS-CMP-10 static tables | §5.6 |

### 5.4 Data bindings

| Region | Endpoint | Parameters | Fields |
|---|---|---|---|
| Header, figures, Overview, Attributes, SSP and allocation | `GET /obligations/{id}` (API-S-Obligation) | `as_of`, `known_at`, `book` | all fields of §5.5 and §5.6; `ratios.recognized`, `ssp.range_position` (E-114) and `ssp.outside_range_point`; `material_right.status` (E-115) and `material_right.status_date` (04 API-S-Obligation, rev 1.2) |
| Schedule | `GET /obligations/{id}/schedule` (API-S-ScheduleLine) | `as_of`, `known_at`, `book` | `period.name`, `line_type`, `state`, `quantity`, `amount`, `cumulative_amount`, `links.explain` |
| Events | `GET /obligations/{id}/events` (API-S-Event) | `known_at` | `effective_date`, `event_type`, `payload`, `origin`, `is_manual`, `approval_request_id`, `source_row`, `recorded_at`, `created_by` |
| Material right | `GET /obligations/{id}/material-right` | none | T-CON-14 columns |
| Commands | §5.8 | `If-Match: "s<head_stream_version>"` of the contract | none |

### 5.5 Figures

Heading "Obligation figures (<currency>)". Every value is an Explain trigger.

| Cell | Value | Bar and secondary line | Explain reference |
|---|---|---|---|
| Allocated | `current.allocated_amount` | none | `links.explain_allocated_amount` |
| Recognized | `to_date.revenue` | Bar against allocated; "<ratios.recognized> of allocation" | `links.explain_revenue_to_date` |
| Scheduled | `scheduled` | Bar against allocated; "<ratios.scheduled> of allocation" | `obligation~<id>~scheduled` |
| Awaiting trigger | `awaiting_trigger` | Bar against allocated; "<ratios.awaiting_trigger> of allocation" | `obligation~<id>~awaiting_trigger` |

The server guarantees allocated = recognized + scheduled + awaiting trigger (REQ-REC-021); the pane never computes it.

### 5.6 Panels

**Overview** (definition list):

| Label | Value |
|---|---|
| Progress | By `recognition_method`: `UNITS_DELIVERED` "Delivered <to_date.delivered_quantity> of <current.quantity> <unit of measure> (<to_date.progress_ratio>)"; `TIME_ELAPSED` "Elapsed <progress_ratio>"; `COST_TO_COST` "Progress (cost to cost) <progress_ratio>"; `LABOUR_HOURS` "Progress (labour hours) <progress_ratio>"; `OUTPUT_PERCENT` "Progress <progress_ratio>"; `MILESTONE` "Milestones achieved <progress_ratio>"; `USAGE`, `ROYALTY` "Recognized as usage is reported"; `POINT_IN_TIME` "Transferred on <satisfied_date>" or "Not yet transferred"; ratios DS-FMT-09 one decimal |
| Billed to date | `to_date.billed` |
| Catch-up to date | `to_date.catch_up`, then the line "Modification <catch_up_modification> · Transaction price change <catch_up_tp_change> · Estimate change <catch_up_estimate>" (DS-FMT-31) |
| Remaining allocation | `remaining.allocation` |
| Remaining billing | `remaining.billing` |
| Returned quantity | `to_date.returned_quantity` (rendered when not 0) |
| Balance | `position.label`: `CONTRACT_LIABILITY` "Contract liability <amount>"; `CONTRACT_ASSET` "Contract asset <amount>"; `NONE` "No balance" (D-12; the amount is always positive) |
| Satisfaction | "Satisfied on <satisfied_date>" or "Partially satisfied" or "Not satisfied" or "Cancelled" |
| Holds | "No holds", or a static table of the obligation's own open holds (API-S-Obligation `holds`; a hold of the whole contract is the contract's and is not repeated here): Hold type, Source ("System", "Rule", "Manual"), Reason, Applied at (DS-FMT-17), and a column "Release" (rev 1.75) that stands where a row has something for it — the action "Release hold", for a holder of `contract.create` for the contract's contracting entity and not on a view of an earlier `known_at`, which opens the drawer of §4.9.4 with the hold chosen; or, for every reader, the API's sentence where the hold is not released by hand (`release_refusal`). **Replaced:** the count of the holds, which was all the pane showed while the read answered none (L5-4-Q-30) |
| Option (material rights only) | Option type label; Incremental discount (DS-FMT-09 two decimals); Expected purchase amount; Expiry date; SSP method label ("Discount × likelihood", "Renewal alternative", "Entered amount"); Likelihood of exercise (link to SF-03:estimate); Status from `material_right.status` (E-115): `OPEN` "Open", `EXERCISED` "Exercised on <status_date>", `EXPIRED` "Expired on <status_date>" (04 API-S-Obligation) |

**Attributes** (definition list, read-only): Obligation key; Legacy record key; Product (code · name, link to SF-15:product); Stratification; Kind (E-18 label); Distinctness ("Distinct", "Not distinct", "Series (increment: <unit>)"); Template (`template_code v<version_no>`, link to SF-13:template-version); Scope (E-77 label); Satisfaction pattern ("Point in time", "Over time"); Over-time criterion (`OT_A` "ASC 606-10-25-27(a)", `OT_B` "ASC 606-10-25-27(b)", `OT_C` "ASC 606-10-25-27(c)", `NOT_APPLICABLE` omitted); Recognition method (E-11 label); Ratable convention (`DAILY` "Daily", `MONTHLY_EVEN` "Monthly, even", `MID_MONTH` "Mid-month"); Principal or agent; Licence nature; Warranty type; Start date; End date; Contracting entity; Performing entity; Currency; Memo 1 to 3; Account overrides (static table Account role, Account). Action "Change attributes".

**SSP and allocation**:

| Group | Label | Field | Format |
|---|---|---|---|
| SSP derivation | SSP book version | `ssp.version_label`, link to SF-13:ssp-book-version with `f.product` | text link |
| | Method | `ssp.method` label (`observable` "Observable", `adjusted_market` "Adjusted market", `cost_plus_margin` "Cost plus margin", `residual` "Residual", `legacy_range` "Legacy range") | text |
| | Unit list price | `ssp.unit_list_price` | DS-FMT-13 |
| | Midpoint discount | `ssp.midpoint_discount_ratio` | DS-FMT-09 two decimals |
| | Range | `ssp.range_ratio` | "± <percent>" |
| | Low / Mid / High | `original.ssp_low`, `original.ssp_mid`, `original.ssp_high` | DS-FMT-13 |
| | Stated price | `original.stated_price` | DS-FMT-05 |
| | Range position | `ssp.range_position` (E-114) and `ssp.outside_range_point` with the copy of §4.1.3.1 column 8 | text |
| | Selected SSP | `original.ssp_selected` | DS-FMT-13; Explain trigger |
| | Override | "Approved override <request no>" link when `ssp.override_approval_request_id` | text link |
| Allocation | Total contract SSP | `original.total_contract_ssp` | DS-FMT-13 |
| | Weight | `current.allocation_weight` | DS-FMT-09 two decimals; Explain shows 18 decimals |
| | Allocated | `current.allocated_amount` | DS-FMT-05; Explain trigger |
| | Allocation adjustment | `current.allocation_adjustment` | DS-FMT-31; Explain trigger |
| | Unit SSP | `current.unit_ssp` | DS-FMT-13 |
| | Remaining unit revenue rate | `current.remaining_unit_revenue_rate` | DS-FMT-13 |

Action "Request SSP override" (drawer §5.8). [J] Low, mid and high are shown as text, not as a slider or range graphic: the design system has no range mark, and the position is carried by the Range position text.

**Schedule**: static table (DS-CMP-10 static variant) caption "Schedule (<currency>)": Period (DS-FMT-19), Line type (label §4.3), State ("Recognized", "Scheduled"), Quantity (DS-FMT-11), Amount (DS-FMT-04, Explain trigger), Cumulative (DS-FMT-04). More than 100 lines switch to the DataGrid with server paging. Footer link "Open in Schedules" → SF-03:schedules `?f.obligation=is:<obligation key>`.

**Events**: static table caption "Events": Effective date; Event (E-03 label, catalogue `event.type.<literal>`); Details (quantity and amount summary from `payload`, for example "120 units · Delivery", "Invoice INV-DE-4471 · 54,000.00"); Origin ("Manual", "Import <file name> row <n>" linking to the import row drawer, "API client <name>", "<integration name>"); Approval (request number link or "—"); Recorded at (DS-FMT-17, `data-volatile`). Selecting a row opens the read-only event drawer: payload fields, source row, supersedes, computation status; action "Void event" (confirmation with reason code and reason, `POST /events/{id}/request-void`).

**As bound to API-R-29 of 1.0 (rev 1.62, CTR-22).** Origin is named from the event's own members, by one rule for this panel and for column 9 of the invoices of SF-03:billing (§4.4). An event a person recorded (`is_manual`; one applied from that person's submission is appended as `SYSTEM` and stays manual, 04 T-CON-05) reads "Manual". Else an event that answers a `source_row` reads "Import row <n>". Else the literal of `origin` (04 T-CON-05) is named: `UI` "Manual", `IMPORT` "Import", `API` "API client <name>" with the `display_name` of `created_by` where that principal is an API client and "API client" where it is not, `ADAPTER` "Integration", `SYSTEM` "System", `MIGRATION` "Migration". A literal outside the six is printed as it is, so a seventh is seen and not hidden. Not bound: the integration's name — the event names its origin `ADAPTER` and no integration — and, of "Import <file name> row <n>", the file's name and the link to the import row drawer: `source_row` names the upload, the sheet and the row (L5-4-Q-60), and the cell is text. `GET /obligations/{id}/events` answers `source_row` null for every event at this revision, so an imported event reads "Import" on this panel until that route answers API-S-Event whole.

### 5.7 States

| State | Rendering and copy |
|---|---|
| Loading | Header skeleton; four KPI skeletons; panel skeleton |
| Not found (the obligation is not in this contract) | Pane text "Obligation not found." with link "Back to obligations" |
| Error | SCR-ST-05 "Could not load the obligation" |
| Stale | The workbench header banner applies; values keep the stale marker |
| Schedule empty | "No schedule lines yet. Lines appear once the contract is computed." |
| Events empty | "No events yet. Deliveries, billing and other events appear here." |
| Option already exercised | "Record exercise" is not rendered when `material_right.status` is exercised or expired; a command that races returns `option-already-exercised` rendered with ERR-12 copy (J-08-ALT-1) |

### 5.8 Commands, keyboard and copy

- "Record event" items by `recognition_method`: `UNITS_DELIVERED`, `POINT_IN_TIME` "Record delivery"; `OUTPUT_PERCENT`, `LABOUR_HOURS` "Record progress"; `MILESTONE` "Record milestone"; `COST_TO_COST` "Record cost"; product obligations with the returns model "Record return"; `obligation_kind = MATERIAL_RIGHT` "Record exercise" and "Record expiry". Drawers per §4.9.3 with the obligation preselected and read-only.
- **Record exercise** drawer (`MATERIAL_RIGHT_EXERCISED`): Exercise date; Additional order reference (text, stored in the event comment); List value (money); Discount on exercise (percent); Additional consideration (money, `additional_consideration`); Goods delivered on (date); New lines (optional, API-S-ContractLine rows); Evidence (required). Preview figures: "Revenue on <date>", "Option contract liability <before> → <after>", "Option status after". Primary "Submit for approval" (MANUAL_EVENT, BR-REC-01).
- **Record expiry**: confirmation "Record expiry of <option label> on <external id>? The allocated amount <amount> is recognized on <expiry date>." with Reason; `MATERIAL_RIGHT_EXPIRED`.
- **Change price** (LTM-06): navigates to SF-07 with `kind=PRICE_CHANGE&obligation=<obligationId>`. Rev 1.29: rendered between "Record event" and the overflow for a holder of `modification.create` on an ACTIVE contract (API-R-31 takes a modification of an active contract only), with the context parameters kept.
- **Change attributes** (ACT-54, `LINE_ATTRIBUTES_CHANGED`): account overrides per role (select of GL accounts; roles limited to those the obligation posts), performing entity (select), SSP version pin (select of approved versions of the book); Comment (required). The drawer shows the field diff before submission (DS-CMP-16 inline variant). Primary "Submit for approval" (`ATTRIBUTE_CHANGE`).
- **Request SSP override** (ACT-21; BR-SSP-03): SSP book version (select of approved versions whose scope covers the product), Justification (reason field). Primary "Submit for approval"; `POST /obligations/{id}/request-ssp-override` `{ssp_book_version_id, justification}` → 200 `{approval_request_id}`, subject `SSP_OVERRIDE` (04 §16.2).
- Keyboard: panel tabs APG Tabs (Left and Right switch and activate; `pane` updated with `history.replace`); `E` on a figure opens Explain; Esc returns focus to the selected master row (DS-CMP-08).
- Copy keys: `contracts.obligation.figures.heading` "Obligation figures ({currency})"; `.tabs.overview` "Overview"; `.tabs.attributes` "Attributes"; `.tabs.ssp` "SSP and allocation"; `.tabs.schedule` "Schedule"; `.tabs.events` "Events"; `.actions.recordEvent` "Record event"; `.actions.changePrice` "Change price"; `.actions.changeAttributes` "Change attributes"; `.actions.requestSspOverride` "Request SSP override"; `.recordExercise.title` "Record exercise"; `.ofAllocation` "{ratio} of allocation".

### 5.9 Sample world

| Obligation | Rendered content | Source |
|---|---|---|
| K-11 `NS-SO-DE-5004` O1 `AVM-GW` (after J-04) | Allocated 89,174.31; Recognized 53,504.59; Scheduled 0.00; Awaiting trigger 35,669.72; Overview "Delivered 120 of 200 EA (60.0%)", billed to date 54,000.00; SSP book version `DE-LIST 2026`, Observable, low 81,000.00, mid 90,000.00, high 99,000.00, stated 90,000.00, Inside range, selected 90,000.00; total contract SSP 109,000.00; weight 82.57%; allocation adjustment (825.69) | WLD-X-22 |
| K-11 O2 `AVM-SUP-12` | Allocated 18,825.69; Recognized 825.24; Scheduled 18,000.45; Awaiting trigger 0.00; Schedule Sep 2026 825.24 (asserted); SSP `DE-LIST 2026` Cost plus margin, low 19,000.00, mid 20,000.00, high 21,000.00, stated 18,000.00, "Below range: nearest bound applied", selected 19,000.00, weight 17.43%, adjustment +825.69 | WLD-X-22 |
| K-07 `NS-SO-DE-5003` O2 `AVM-EXP-CREDIT` | Option: Discount voucher; incremental discount 30.00%; expected purchase amount 50,000.00; expiry 13 Oct 2026; SSP method "Discount × likelihood"; allocated 10,714.29. "Record exercise" preview: "Revenue on 22 Sep 2026 40,714.29"; "Option contract liability 10,714.29 → 0.00"; "Option status after Exercised" (asserted, J-08.1). Second exercise refused: "The expansion credit on NS-SO-DE-5003 was already exercised on 22 Sep 2026." (J-08-ALT-1) | WLD-X-17 |
| `SF-ORD-20417` O2 `AVM-IMPL-PLUS` | Outline chip "Intercompany: AVM-UK performs"; performing entity AVM-UK | J-03.4 |
| K-01 `SF-ORD-10001` O1 | Schedule Sep 2026 9,764.38 (Explain in J-19.6) | WLD-X-02 |

### 5.10 Test hooks

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Pane | `getByRole("region", {name: /^Obligation details: /})` | `SF-03-pane-obligation` |
| Figures | `getByRole("button", {name: /^Explain Recognized, EUR/})` | `SF-03-kpi-revenue-to-date` |
| Panel tabs | `getByRole("tablist", {name: "Obligation sections"})` | none |
| SSP panel | `getByRole("tabpanel", {name: "SSP and allocation"})` | `SF-03-pane-ssp` |
| Schedule table | `getByRole("table", {name: /^Schedule/})` | `SF-03-grid-obligation-schedule` |
| Record exercise | `getByRole("dialog", {name: "Record exercise"})` | `SF-03-drawer-record-exercise` |
| Holds table (rev 1.75) | `getByRole("table", {name: "Holds"})` | `SF-03-grid-obligation-holds` |
| Release hold (rev 1.75) | `getByRole("dialog", {name: "Release hold"})` | `SF-03-drawer-release-hold` |

### 5.11 Light, dark and accessibility

- Light and dark: bars `--viz-kpi-bar` on `--viz-kpi-track`; outline chips `--border-default`; the pane is `--bg-surface` beside the master pane with the hairline resize handle.
- Accessibility: pane `role="region"` named "Obligation details: <product name>" (DS-CMP-08); figures `dl`; panel tabs APG Tabs with `aria-controls`; the Weight value's accessible name includes "percent"; event drawer APG Dialog.

## 6. Explain panel

### 6.1 Summary

| Field | Value |
|---|---|
| Placement | DS-CMP-15 docked panel; opened from any Explain trigger on every screen, URL parameter `explain` (SCR-URL-11); also X:trace (RT-96) and the source record drawer §6.6 |
| Roles and permissions | `contract.read` for engine figures; `report.run` for report cells (SCREENS_B); "Ask about this figure" `ai.use` with AI enabled |
| Purpose | Show how a figure was computed: narrative, formula, contributions, inputs, steps, source records, versions and history, with drill-down to the source row (D-60; PP-07) |
| REQ | REQ-UX-005, REQ-RPT-017, REQ-RPT-018, REQ-AI-006 |
| Journeys | J-16.2 to J-16.6, J-19.6, J-19.7, J-11.4 (Explain available on each commitment figure) |

### 6.2 Wireframes

1440 px (docked beside SF-04, which SCREENS_B specifies):

<!-- WF:explain-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   |+---------------------------------------------------------+ +------------------------------------+|
| Work              || Schedules . AVM-US . Sep 2026                           | | Explain                            ||
|    Home           || Contract        Aug 2026   Sep 2026                     | | Revenue . Sep 2026                 ||
|    Contracts      || PRJ-CB-2026-01  xx,xxx.xx  197,294.12 |*                | | USD 197,294.12                     ||
| |* Schedules      || SF-ORD-10001    x,xxx.xx   9,764.38                     | | PRJ-CB-2026-01 . O1 . ASC 606 . AVM||
|    Close          ||                                                         | | [Copy link]                      [x||
|    Journals       ||                                                         | | Revenue for Sep 2026 has 3 causes. ||
|    Reports        ||                                                         | | Contributions                      ||
| ----------------  ||                                                         | |  Modification CR-CAS..   91,463.41 ||
| Govern            ||                                                         | |  Progress (costs 82,..) 135,000.00 ||
|    Approvals    3 ||                                                         | |  Estimate change        (29,169.29)||
|    Policies       ||                                                         | | Formula                            ||
|    Data           ||                                                         | |  revenue = cum(t) - cum(t-1)       ||
|                   ||                                                         | | Inputs . Steps . Source records    ||
|                   ||                                                         | | Versions . History                 ||
|                   ||                                                         | | [Verify] [Open calculation trace]  ||
| Settings          |+---------------------------------------------------------+ +------------------------------------+|
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:explain-1440 -->

1280 px (non-modal overlay drawer; no scrim; content underneath stays interactive):

<!-- WF:explain-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    |+----------------------------------------------------------+ +------------------------------------+|
| H  || Schedules . AVM-US . Sep 2026                            | | Explain                            ||
| Ct || Contract        Aug 2026   Sep 2026                      | | Revenue . Sep 2026                 ||
| *Sc|| PRJ-CB-2026-01  xx,xxx.xx  197,294.12                    | | USD 197,294.12                     ||
| Cl ||                                                          | | PRJ-CB-2026-01 . O1 . ASC 606 . AVM||
| Jn ||                                                          | | [Copy link]                      [x||
| Rp ||                                                          | | Revenue for Sep 2026 has 3 causes. ||
| -- ||                                                          | | Contributions                      ||
| Ap ||                                                          | |  Modification CR-CAS..   91,463.41 ||
| Po ||                                                          | |  Progress (costs 82,..) 135,000.00 ||
| Da ||                                                          | |  Estimate change        (29,169.29)||
|    ||                                                          | | Formula                            ||
|    ||                                                          | |  revenue = cum(t) - cum(t-1)       ||
|    ||                                                          | | Inputs . Steps . Source records    ||
|    ||                                                          | | Versions . History                 ||
|    ||                                                          | | [Verify] [Open calculation trace]  ||
| Se |+----------------------------------------------------------+ +------------------------------------+|
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:explain-1280 -->

### 6.3 Sections and bindings

Binding: `GET /explain/{object_type}/{id}/{measure}?period&book&as_of&known_at&depth=6` (API-S-Explain). Report cells use `GET /explain/report-runs/{id}/cell` and then the contributor's own explanation (SCREENS_B).

| # | Section (`h3`) | Content | Fields |
|---|---|---|---|
| 1 | Header | Eyebrow "Explain"; `h2` figure name "<measure label> · <period label>"; value (DS-FMT-05); context line "<contract external id> · <obligation key> · <book label> · <entity code>"; buttons "Copy link" and Close; breadcrumb "<root label> › <input label>" with "Back" when drilled | `object`, `value`, `context` |
| 2 | Narrative | Deterministic sentences, each a paragraph; never AI text | `narrative[]` |
| 3 | Formula | Sentence from catalogue `explain.formula.<formula_id>.sentence`; expression in mono with named variables from `explain.formula.<formula_id>.expression`; rounding line "ROUND_HALF_UP to <minor unit> decimals, cumulative rounding" (D-11a) | root node `formula_id`, `params` |
| 4 | Contributions | Rendered when the root formula is a sum by cause: static table Cause, Amount (DS-FMT-31); the label of each cause comes from its node `params` (for example the modification reference or the estimate version pair) | root node `inputs[]` with `node_id` |
| 5 | Inputs | Native table Name, Value (full stored precision; identifiers mono), Source (link). A computed input has a Function icon button "Explain <name>" that pushes its explanation onto the panel's Back stack | root node `inputs[]` |
| 6 | Calculation steps | Ordered list, depth-first from the root: measure label, formula id (mono), value, "Rounding residue <value>" when not 0. More than 6 steps collapse behind "Show all <n> steps" | `nodes[]` |
| 7 | Source records | Links by `ref_type`: `contract_event` → the event drawer of SF-03:obligation; `import_row` → the import row drawer (§12.3); `source_record` → §6.6; `ssp_entry`, `ssp_range` → SF-13:ssp-book-version with the entry highlighted; `rule` → SF-13:rule-set-version; `fx_rate` → SF-15:currencies; `estimate_version` → SF-03:estimate; `registry_version` → SF-13:accounting-version; `policy_override` → the contract's policy override drawer (read-only; rev 1.80: not built, and not in release 1.0, §4.9.7). Drill row: "Open contract", "Open obligation", "Schedule lines", "Subledger lines" | `nodes[].inputs[].ref_*`, `drill` |
| 8 | Versions | Engine version; calculation trace id (DS-FMT-23); contract version (`version_no`, id); `as_of`; `known_at` (DS-FMT-17); link "Pinned policies (<n>)" opening a static table Key, Value, Level, Source | `engine_version`, `calc_trace_id`, `context`, pinned policies of the contract version |
| 9 | History | DS-CMP-12 compact: one item per earlier value by contract version: value, delta (DS-FMT-31), cause (events, "EAC version 2 → 3", modification reference), approvals, origin period of a catch-up | `history[] {contract_version_id, version_no, known_at, value, delta, cause, estimate_version_pair, origin_period_key}` (04 API-S-Explain) |
| 10 | Footer | "Verify" (`POST /explain/{object_type}/{id}/{measure}/verify` → 200 `{recomputed_value, stored_value, matches}`, or 202 job with the same object in `result` after 30 seconds; 04 API-R-49); "Open calculation trace" (X:trace); "Ask about this figure" (AI, SCREENS_B proposal block below the narrative) | none |

Measure labels (catalogue `explain.measure.<measure>`): `transaction_price` "Transaction price"; `allocated_amount` "Allocated"; `revenue_to_date` "Recognized to date"; `revenue` "Revenue"; `amount` "Amount"; `billed_to_date` "Billed to date"; `scheduled` "Scheduled"; `awaiting_trigger` "Awaiting trigger"; `contract_liability` "Contract liability"; `contract_asset` "Contract asset"; `unbilled_receivable` "Unbilled receivable"; `carrying_amount` "Carrying amount"; `selected_ssp` "Selected SSP"; `allocation_adjustment` "Allocation adjustment"; and the measures the to-date links of an obligation name (04 API-S-Obligation `links`, rev 1.132; rev 1.21): `revenue_cum` "Recognized to date", `billed_cum` "Billed to date".

List level (rev 1.21; supervisor ruling R-112 (h)). A figure the calculation trace holds at no node of its own — the contract's Billed, Recognized and Scheduled at the measured period (§4.1.4) — opens the panel at a list level instead of at a figure:

| Part | Content |
|---|---|
| Header | Eyebrow "Explain"; `h2` "<measure label> · <measured period label>" with the measure labels "Billed to date", "Recognized to date" and "Scheduled"; the value of the cell that opened it (DS-FMT-05), which is the API's figure; the context line "<contract external id> · <book label> · <entity code>"; Close. No "Copy link": the `explain` parameter names a figure and is absent at a list level (SCR-URL-11) |
| Section "By obligation" (`h3`) | A static table, one row per obligation of `GET /contracts/{id}/obligations` (API-S-Obligation), in the order of that read: the columns Obligation ("<obligation key> · <product code>"), the amount, under the measure label of what it shows — `to_date.revenue` ("Recognized to date") for Recognized and for Scheduled, `to_date.billed` ("Billed to date") for Billed — and "Explain", a Function icon button "Explain <obligation key>" that pushes that obligation's explanation onto the panel's Back stack — `links.explain_revenue_to_date`, or `links.explain_billed_to_date`, with the `period` the link carries, named "<measure label> · <obligation key> · <label of that period>" (the obligation key keeps it apart from the list in the path "<list name> › <entry name>") with the context line "<contract external id> · <obligation key> · <book label> · <entity code>". A row whose link is null has no button. The table has no total row: the value in the header is the total as the API measures it, and the panel adds no money (DG-FE-08) |
| Sentences | They say why the header's value is not what a reader adds up from the rows. Above the table, for Scheduled: "Scheduled is the allocated amount less the amounts recognized and awaiting a trigger. The table shows what is recognized for each obligation." (03 REQ-REC-021). Below the table, for Recognized, when the build-up of the contract version has consideration payable (`transaction_price_buildup.consideration_payable` of API-S-ContractVersion is not zero): "The contract's figure is net of consideration payable released to date. The amounts of the obligations are before that reduction." (ENGINE_SPEC S04-R-02; 04 T-CON-08 `revenue_cum`). Billed has no sentence |
| Footer | Not rendered: no "Verify", no "Open calculation trace" and no "Ask about this figure", because the list is no node of the trace |

"Back" from an obligation's explanation returns to the list. The rows are the page's own read of the obligations: a refetch replaces them while the level is open.

### 6.4 States and behaviour

| State | Rendering and copy |
|---|---|
| Loading | Skeleton per section (DS-CMP-15) |
| Input value | "This value is an input." with its source record link |
| Partially restricted | Info line "<n> source records are outside your access." |
| Figure changed | Warning banner "This figure changed after the page loaded. Refresh to see current figures." when `context.contract_version_id` differs from the trigger's version (DS-CMP-15) |
| Stale | Info banner as SCR-ST-08 |
| Depth limit | "Showing <n> levels." with the button "Show deeper levels" (re-request with `depth=20`) |
| Error | "The explanation could not be loaded." with "Retry" |
| List level, loading (rev 1.21) | A skeleton in place of the table while the obligations are read |
| List level, error (rev 1.21) | "Could not load obligations" with "Retry", which repeats the page's read of the obligations |
| List level, no obligation (rev 1.21) | "No obligations yet" in place of the table |
| Verify, match | Positive message "Recomputed from the stored trace: <value>. Matches." (J-16.3) |
| Verify, mismatch | Negative banner "Recomputed from the stored trace: <value>. It does not match the stored value <stored value>. Reference <request id>." |
| Proposed narrative discarded | Note "A proposed narrative was discarded because it contained a figure that is not in the calculation trace." (J-19.7; REQ-AI-006) |

Behaviour: opening another figure replaces the content and pushes the previous one onto the Back stack; the panel stays open across tabs of the same record and closes when the route leaves the record (DS-CMP-15). Keyboard: Enter or `E` on a trigger opens and focuses the `h2`; Esc closes and returns focus to the trigger; `Alt+Left` goes back one level.

### 6.5 X:trace Calculation trace page

| Field | Value |
|---|---|
| Route | `/trace/:calcTraceId?node=<node id>` (RT-96) |
| Binding | `GET /calc-traces/{id}` (04 API-R-49, API-S-CalcTrace `{id, contract_version_id, combination_group_id, book, format_version, engine_version, trace_sha256, node_count, root_measures, trace}`; the T-ENG-03 DAG with every node) |
| Layout | `h1` "Calculation trace"; meta row: engine version, contract version, known at, trace id; DataGrid in treegrid mode (DS-CMP-10) with columns Node (measure label, indented by depth), Formula (`formula_id`, mono), Value (full precision), Currency (mono), Rounding residue, Inputs (count), Source (link as §6.3 row 7); toolbar "Expand all", "Collapse all", "Download JSON" (the response body, file name `trace-<id prefix>.json`) |
| States | Loading 10 skeleton rows; error SCR-ST-05 "Could not load the calculation trace"; not found SCR-ST-07 "Calculation trace not found" |
| Test hooks | `getByRole("treegrid", {name: "Calculation trace"})`; `X-grid-trace` |

### 6.6 Source record drawer and import row drawer

- Source record drawer (standard drawer, `drawer=source-record&source_record=<id>`): binding `GET /source-records/{id}` (04 API-R-56, API-S-SourceRecord). Definition list: Source system (`source_system`); Object type (`object_type`, E-39 label); External id (`external_id`, mono); External version (`external_version`); Received at (`received_at`, DS-FMT-17); Payload SHA-256 (`payload_sha256`, DS-FMT-23); API client (`api_client.name`) when not null; Sync run (link to SF-16:sync-run, whose connection id comes from `GET /sync-runs/{sync_run_id}`) when `sync_run_id` is set; Import (link to the SF-10:detail row drawer) when `import_upload_id` is set; Idempotency key (`idempotency_key`, mono); Request id (`request_id`, mono, `data-volatile`). Below: "Payload" code block (mono, collapsible, redacted by the server). J-16.5 sample: API client `svc-metering`, idempotency key `metering-2026-09-SF-ORD-10003`.
- Import row drawer (on SF-10:detail `committed` and `validate`, `row=<row number>&sheet=<sheet name>`): binding `GET /imports/{id}/rows?row_number=<n>&sheet_name=<s>` (API-S-ImportRow; 04 API-R-43 row filters). Definition list: File (original file name), File SHA-256 (DS-FMT-23), Sheet ("—" for CSV), Row number, Status chip, Business key; static table "Cell values" Column, Raw value (mono), Normalised value; "Findings" list (IMP copy with code); "Created records" (lineage links); Uploaded by; Approved by. J-16.4 sample: `avm-us-costs-2026-09.csv` row 2, uploader Maya Chen, approver Priya Raman.

### 6.7 Sample world, hooks, light and dark, accessibility

- J-16.2 (K-03 `PRJ-CB-2026-01`, Sep 2026, opened from SF-04): value USD 197,294.12; contributions "Modification CR-CASTELLAN-2026-09" 91,463.41, "Progress (costs 82,000.00)" 135,000.00, "Estimate change (EAC 820,000.00 → 850,000.00)" (29,169.29); drilled input "Recognized to date" 797,294.12 with inputs costs incurred 502,000.00, estimated total costs (version 3) 850,000.00, transaction price 1,350,000.00, exact value 797,294.117647, rounding residue 0.002353; narrative "Revenue to date = 1,350,000.00 × 502,000.00 ÷ 850,000.00 = 797,294.12 (rounded half up)." (asserted). "Verify" message "Recomputed from the stored trace: 797,294.12. Matches." (J-16.3).
- J-19.6: K-01 O1 Sep 2026 9,764.38 shows the deterministic narrative and a "Proposed narrative" block (DS-CMP-25).
- Test hooks: panel `getByRole("complementary", {name: /^Revenue/})`; sections by heading; "Verify" button by name; `X-explain` is not used: the panel carries `data-testid="<SF id of the host screen>-explain"`, sections `<SF id>-explain-<section slug>`; the list level's section is `<SF id>-explain-by-obligation` and its buttons are found by name, "Explain <obligation key>" (rev 1.21).
- Light and dark: `--bg-raised` in both themes with `--border-default`; mono formula on `--bg-subtle`; the proposed narrative uses the dashed `--proposal-border`.
- Accessibility: `aside aria-labelledby=<h2 id>`; each section `h3`; formula in `code`; the Back button is named "Back to <previous figure name>"; value changes after Verify are announced politely.

## 7. SF-07 Modification wizard and SF-07:detail

### 7.1 Summary

| Field | Value |
|---|---|
| Screen ids and routes | SF-07 `/contracts/:contractId/modifications/new` (RT-20); SF-07:detail `/contracts/:contractId/modifications/:modificationId` (RT-21). A `DRAFT` modification renders the wizard on SF-07:detail; any other status renders the read-only detail. The step is `?step=change|questionnaire|treatment|preview|submit` |
| Roles and permissions | Create and edit `modification.create` (ACT-07); submit `modification.create`; approve in SF-12 `modification.approve` (ACT-08); linked estimate versions `estimate.create`; linked judgements `judgement.create` |
| Purpose | Record a typed change, answer the classification questionnaire, choose a treatment per obligation with SSP basis, preview the effect (catch-up, revenue by period, RPO, balances, journal lines) and submit for approval (PRD SF-07; REQ-MOD-002) |
| REQ | REQ-MOD-001 to REQ-MOD-022; REQ-SSP-006; REQ-PLT-013 to REQ-PLT-015; REQ-POL-008; REQ-UX-012 |
| Journeys | J-05.1 to J-05.4, J-05-ALT-1, J-05-ALT-2, J-06.1, J-06.2, J-06.5 (rev 1.51: the steps PRD rev 1.158 gives SF-07); SCR-LTH-04 to SCR-LTH-06 |

### 7.2 Wireframes

1440 px, step 4 Impact preview (K-02, J-05.3 figures; rev 1.52: the journal preview is the measured example of the rule as built — the entries the approval would post while September is the latest postable period, 04 API-S-ImpactSummary rev 1.210 — with the line that states when and for which period they were computed):

<!-- WF:modwiz-preview-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Contracts > SF-ORD-10002 > New modification                                                      |
| Work              | New modification  CR-MARROWBY-2026-09  (Draft)                                    [Discard draft]|
|    Home           | (ok) 1 Change -- (ok) 2 Questionnaire -- (ok) 3 Treatment -- (4) 4 Impact preview -- ( ) 5 Submit|
| |* Contracts      |   Upgrade . 16 Sep    3 answers confirmed      Prospective         Catch-up 0.00                 |
|    Schedules      | Impact summary (USD)                                                                             |
|    Close          |+------------------+------------------+------------------+------------------+------------------+  |
|    Journals       || Transaction price| Catch-up         | Revenue Sep 2026 | RPO at 16 Sep 202| Journal lines    |  |
|    Reports        || 300,000.00       | 0.00             | 11,769.80        | 215,178.08       | 2                |  |
| ----------------  || Before 240,000.00|                  | Before 9,863.01  | Before 155,178.08|                  |  |
| Govern            |+------------------+------------------+------------------+------------------+------------------+  |
|    Approvals    3 | Allocation by obligation                                                                         |
|    Policies       | | Obligation | Treatment   | Remaining before | Remaining after | Change      | Catch-up |       |
|    Data           | | O1         | Prospective |       155,178.08 |      148,451.55 |  (6,726.53) |     0.00 |       |
|                   | | O2 (added) | Prospective |                — |       66,726.53 | +66,726.53  |     0.00 |       |
|                   | Revenue by period                                                                                |
|                   | | Period   | Before    | After     | Change    |                                                 |
|                   | | Sep 2026 |  9,863.01 | 11,769.80 | +1,906.79 |                                                 |
|                   | | Oct 2026 | 10,191.79 | 14,132.46 | +3,940.67 |                                                 |
|                   | Journal preview                                                                                  |
|                   | | Account                 | Account role       | Debit    | Credit   |                           |
|                   | | 2100 Contract liability | Contract liability | 2,120.55 |   213.76 |                           |
|                   | | 4010 Revenue            | Revenue            |   213.76 | 2,120.55 |                           |
|                   | Computed 16 Sep 2026 09:40 UTC for Sep 2026: the entries the approval would post then - the      |
|                   | change's effect with the period's amounts not posted yet.                                        |
| Settings          |                                                                               [Back] [*Next]     |
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:modwiz-preview-1440 -->

1280 px, step 2 Questionnaire:

<!-- WF:modwiz-questionnaire-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Contracts > SF-ORD-10002 > New modification                                                       |
| H  | New modification  CR-MARROWBY-2026-09  (Draft)                                [Discard draft]     |
| *Ct| (ok) 1 Change --- (2) 2 Questionnaire --- ( ) 3 Treatment --- ( ) 4 Preview --- ( ) 5 Submit      |
| Sc | O1 AVM-SEAT-MO . 100 seats . 01 Jan 2026 - 31 Dec 2027                                            |
| Cl |  Are the added goods or services distinct?            (x) Yes  ( ) No   Prefilled                 |
| Jn |  Is the added price at SSP?                           ( ) Yes  (x) No   Prefilled                 |
| Rp |   60,000.00 is below the range low 69,750.00 (US-LIST 2026-H1)                                    |
| -- |  Are the remaining goods or services distinct from                                                |
| Ap |  those already transferred?                           (x) Yes  ( ) No   Prefilled                 |
| Po |  [x] I confirm these answers for O1                                                               |
| Da | Proposed treatment: Prospective (ASC 606-10-25-13(a))                                             |
| Se |                                                                          [Back] [*Next]           |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:modwiz-questionnaire-1280 -->

### 7.3 Frame

| Region | Component | Content |
|---|---|---|
| Page header | none | Breadcrumb "Contracts / <external id> / New modification" (or "/ <reference>"); `h1` "New modification" or "Modification <reference>"; status chip (§0.8); secondary "Discard draft" (a DRAFT without a pending request, `modification.create`; confirmation "Discard this draft modification?" → `POST /modifications/{id}/discard` → `VOIDED` per SM-03; a 409 names the judgement record whose review is pending, PRD ERR-82; rev 1.26) |
| Stepper | DS-CMP-18 stepper anatomy (OQ-S-05) | Steps "Change", "Questionnaire", "Treatment", "Impact preview", "Submit"; captions per §7.4 to §7.8; completed steps are links |
| Step content | forms DS-CMP-21, static tables, DS-CMP-06 impact strip, DS-CMP-24 job indicator | §7.4 to §7.8 |
| Footer | sticky | "Back" and "Next" (step 5: "Submit for approval"); "Next" reports what blocks it in a line above the footer |

The draft is created on leaving step 1 (`POST /contracts/{id}/modifications`, or `POST /contracts/{id}/subscription-changes` for `action`), and the URL is replaced with SF-07:detail. Every step change saves with `PATCH /modifications/{id}` (`If-Match: "r<row_version>"`).

**As bound to API-R-31 of 1.0 (rev 1.23, CTR-27).** No modification command takes `If-Match` (D-98 140-A4): the row answers `ETag "r<row_version>"`, the wizard sends none, two preparers on one draft are last-write-wins (item MOD-DRAFT-LWW-1), and SCR-ST-09 does not arise on this screen. `POST /contracts/{id}/subscription-changes` is not on main (CTR-18): a subscription action creates an ordinary modification of the matching kind (`UPGRADE`, `DOWNGRADE`, `CO_TERM`, `RENEWAL`, `EARLY_RENEWAL`, `CANCELLATION`) whose one line has the ENGINE_SPEC S06-R-19 shape of that kind. A save is `PATCH /modifications/{id}`, then `POST /modifications/{id}/classify`, because every `PATCH` clears the proposal and the stored preview; a step left without a change saves nothing. The draft opens on the first step that is not done when `step` names a later one, and at step 1, without a command, when the URL names no step. "Discard draft" (rev 1.26; bound in rev 1.42, item MOD-DISCARD-1) renders for a holder of `modification.create` for the contract's entity (§0.6 SCR-PERM-02 (a)); its confirmation states the consequence, "The draft is voided and can no longer be edited or submitted."; after the command the page is the contract's Modifications tab with the toast "The draft modification was discarded."; a 409 shows the API's messages in the confirmation, and the draft stays. The breadcrumb of the wizard ends in "New modification"; the reference stands beside the `h1`. The sticky footer carries the cue "More below" of DESIGN_SYSTEM rev 1.9 (DS-CMP-18 footer; `SF-07-more-below`), as the footer of the draft contract form of §4.10 does (`SF-03-more-below`).

### 7.4 Step 1 Change

Subscription change (`action` present):

| Field | Control | API |
|---|---|---|
| Change | read-only label "Upgrade", "Downgrade", "Co-term", "Renew", "Early renew", "Cancel" | action |
| Obligation | select of active obligations (required for downgrade, co-term and cancel) | obligation key |
| Quantity | decimal (added for upgrade and co-term, removed for downgrade) | quantity delta |
| Price | money | consideration delta |
| Effective date | date | `effective_date` |
| End date | date; for co-term read-only "Ends on <original end date>" | line end date |
| Reference | text, required, unique per contract (REQ-MOD-019) | `reference` |

General modification (no `action`):

| Field | Control | API |
|---|---|---|
| Kind | select of E-25 labels (§4.6) | `kind` |
| Reference | text, required | `reference` |
| Effective date | date | `effective_date` |
| Scope description | textarea | `rationale` |
| Lines | DataGrid, inline-editable draft data: Action ("Add", "Remove", "Change"), Obligation (existing key or new key), Product, Quantity change, Consideration change, Start date, End date, Performing entity, SSP version, Memo 1 to 3 | `lines[]` |
| Price change (kind `PRICE_CHANGE`) | Obligation (preselected from `obligation`); Price change amount (money); quantity fixed at 0 (IMP-33) | `price_change_amount`, `lines[]` |

Linked items panel (BR-MOD-02): "Linked estimate versions" static table Element, Kind, Version, Figure, Status, with the button "Add estimate version" (drawer §8.4 bound to this modification); "Linked judgement records" static table Topic, Conclusion, Status, with "Add judgement record" (drawer: topic, conclusion, rationale, Codification references). Caption: "Stepper caption: <kind label> · <effective date>". Rev 1.33 (04 rev 1.210; item MOD-LINKED-ESTIMATES-1): the table reads `linked_estimate_versions` of `GET /modifications/{id}` — Element `element_code`, Kind the E-09 label of `estimate_kind`, Version `version_no`, Status the E-12 chip — and its Figure from `GET /estimate-versions/{id}`; "Add estimate version" sends `modification_id` and is offered while the modification is a draft. The linked versions are approved before the modification is submitted: `POST /modifications/{id}/submit` names each version that is not (PRD ERR-87), and "Discard draft" names a version that is waiting for approval (PRD ERR-83).

Validation copy: "Enter a reference for this modification."; "Reference <reference> is already used on this contract."; "Add at least one line or a price change."; backdated info (not blocking) "Effective <date> is before the latest event on this contract (<date>). Events from <date> replay in order." (BR-MOD-04).

**As bound to API-R-31 of 1.0 (rev 1.23, CTR-27).** Subscription change: "Obligation" is required for every action, because the line of each kind names one (S06-R-19): upgrade and downgrade change it for the remaining term, co-term and the renewals add an obligation of its product under "New obligation key" (required; prefilled with the next free key `O<n>`), cancel removes from it. "Quantity" and "Price" carry a help line that says what the amount does for the action; a co-term and a renewal need a quantity. "End date" is typed for "Renew" and "Early renew" (the renewal term starts the day after the obligation ends) and reads "Ends on <original end date>" for the other four. An existing draft opens step 1 as the general form; the kind of a draft that holds a price change amount is a choice like any other (rev 1.42): `PATCH` clears a nullable member that is sent as null (04 §16.14 rev 1.188, item MOD-PATCH-CLEAR-1), so the save of another kind removes the amount, and an emptied scope description is cleared. Linked items panel (rev 1.51; 04 §16.14 rev 1.210, item MOD-LINKED-ESTIMATES-1): "Linked estimate versions" lists `linked_estimate_versions` of the row on step 1 of an existing draft — Element (a link to SF-03:estimate, where a version is edited, submitted, withdrawn and discarded; a row carries no command of its own), Kind, Version, Figure (the key figure of the kind, read from `GET /estimate-versions/{id}`) and Status; a discarded version stays in the list and reads Void, and a draft without one reads "No estimate version is linked.". "Add estimate version" renders for a holder of `estimate.create` for the contract's entity (§0.6 SCR-PERM-02 (a)) and opens the version drawer of §8.4 for one estimated element of the contract: at once where the contract has one element, from a menu of them ("<element code> · <kind label>") where it has several; an element whose latest version is a draft or waits for approval is unavailable with the sentence SF-03:estimate gives, and on a contract without an element the command is unavailable with "Add an estimated element on the Estimates tab first."; the reason of the unavailable button is a visible line beside the list, which its tooltip repeats (§0.6 SCR-PERM-03; DESIGN_SYSTEM DS-CMP-27), and in the menu each element's item states its own. A failed read of the contract's elements shows "Could not load estimates" with "Retry" in place of the command, and a failed read of the versions the drawer starts from shows "Could not load the versions" with "Retry", which opens the drawer. The drawer sends `modification_id` with its `POST`, starts from the figures of the element's approved version (§8.4), and the row is read again after it saves or submits; a command on a linked version that is sent on SF-03:estimate — an edit, a submission, a withdrawal, a discard — marks the row for a new read as well, so the panel and the summary show the version's status when SF-07 is opened again. "Linked judgement records" lists the records whose subject is the modification (`GET /judgements?subject_type=modification&subject_id=<id>`) with Topic (the record number beneath), Conclusion and Status, on step 1 of an existing draft; "Add judgement record" (`judgement.create`) offers the topics that take no questionnaire of their own (`MODIFICATION_TREATMENT_OVERRIDE`, `SSP_OVERRIDE`, `ESTIMATE_VS_ERROR`, `OTHER`), creates the record and submits it for review. The message of a repeated reference is the API's: "Reference <reference> is already used by modification <modification no> of this contract.". A line `/classify` refuses (S06-R-19) is shown with the API's message: at the cell it names when the save of step 1 of an existing draft is refused, on step 2 with "Retry" for a draft that was just created. Rev 1.66 (PRD SM-10 `DRAFT` → `VOIDED`, ERR-95; 04 API-R-33 rev 1.242): the drawer of "Add judgement record", and that of "Record judgement" of §7.6, creates its record and sends it for review as two requests. A record whose submission was refused stays a draft in "Linked judgement records" once the drawer is closed, and holds the modification's own submission (§7.8). A row whose record is a draft carries "Discard" in a fourth column, "Actions", for a holder of `judgement.create` for the contract's contracting entity — the command, its confirmation and its refusal as §4.1.3 states them. The column stands only while a row has the command; the read-only detail of §7.9 shows none. Status is the word of §0.8. Rev 1.74 (PRD SM-10 rev 1.199): a row whose record is rejected carries "Discard" as well — the override banner of §7.6 keeps offering "Record judgement" for it, and the record that the new one replaces is discarded here.

### 7.5 Step 2 Questionnaire

Binding: `POST /modifications/{id}/classify` returns `questionnaire` prefilled per obligation key, `proposed_treatments` and `prefill_reasons` (obligation key → question → `{value, reason_key, params}`; 04 API-S-Modification). The caption text is catalogue key `reason_key` rendered with `params`. One group per affected obligation: heading "<obligation key> <product code> · <quantity> · <date range>", three radio groups (Yes / No), a caption "Prefilled" with the reason under each prefilled answer, and a checkbox "I confirm these answers for <obligation key>" (BR-MOD-01).

| Key (T-CON-06) | Question copy | Help |
|---|---|---|
| `added_goods_distinct` | "Are the added goods or services distinct?" | "ASC 606-10-25-12(a)" |
| `priced_at_ssp` | "Is the added price at SSP?" | "ASC 606-10-25-12(b). Prefilled from the modification-date SSP range (D-18)." |
| `remaining_goods_distinct_from_transferred` | "Are the remaining goods or services distinct from those already transferred?" | "ASC 606-10-25-13(a) and (b)" |

Changing an answer re-runs `classify`. Next is blocked with "Confirm every answer to continue." Caption: "<n> answers confirmed". The proposed treatment line under the groups reads "Proposed treatment: <treatment label>".

**As bound to API-R-31 of 1.0 (rev 1.23, CTR-27).** `/classify` proposes the answers and stores none, and `GET /modifications/{id}` answers the stored ones alone, so an answer counts as confirmed once it is stored (BR-MOD-01): confirming a group stores every answer it shows, changing an answer stores that answer, and clearing the checkbox removes the group's answers, which are then proposed again. A group asks what applies to its obligation: the two questions of added goods for the key of an `ADD` line, the third for an existing obligation the classification proposes an answer for; the added lines come first. A proposed answer shows "Prefilled" with its reason (catalogue keys `modifications.prefill.<question>.<reason>`, 04 §16.14; a price test names the SSP book version as `<book code> <version label>`); a stored answer shows neither — but for the price question, where the price test of the row stays under the answer as a fact (rev 1.52; 04 §16.14 rev 1.250 `price_tests`, item MOD-PRICE-TEST-FACT-1): the engine's test of the added line as the latest classification read it, whatever the preparer answered. Beside an answer of No it is the sentence of the comparison, as beside a proposal. Beside an answer of Yes the engine passed the test on the preparer's attestation and compared nothing, and the sentence states the two figures and concludes nothing from them: "Attested by the preparer as priced at the standalone selling price. Price <price>; SSP <low> to <high> (<book code> <version label>).", with the point in place of the range for an entry with a point, and "… Price <price>; no approved SSP applies to the added goods or services at the modification date." where no entry resolves. A row that states no price test — not classified, or edited since — shows no sentence. The figures of a price test are those of the SSP version the test read, which the engine names by `<book code>@v<version no>` (`params.ssp_version_key`): the sentence names that version by its label while the line's stored basis is that version, and by the key, written "<book code> v<n>", once the preparer named another version for the allocation (§7.6 "Override"). The stored answers are those `PATCH` and `GET` answer: a classification stores none, so the screen keeps the answers of the row it asked the classification for and takes a proposal from `prefill_reasons` only for a question that row holds no answer to. An answer the row holds stays confirmed, and every save sends it, whatever a classification or a read names as a proposal — the price test, for one, may be reported beside a stored answer (rev 1.42). `/classify` keeps a stored chosen treatment and writes the proposal only where none is stored, so the save of step 1 or 2 sends `chosen_treatments` reduced to the departures the preparer made: the defaults of the classification before it then follow the new proposal instead of standing as departures `/submit` would refuse (REQ-MOD-002); a departure stays for an obligation the modification still names. Every answer of one row carries the proposals of its classification as `prefill_reasons` (rev 1.52; 04 T-CON-06 `classification`, rev 1.210, item MOD-PREFILL-READ-1), so a classified draft opens on its proposals and is not classified again; a row that carries none — one classified before the API stored its classification — is classified again on opening a step past step 1, unless it holds a stored preview, which `/classify` would clear. A classification that is refused shows the API's messages with "Retry".

### 7.6 Step 3 Treatment

Static table, caption "Treatment by obligation":

| # | Header | Content |
|---|---|---|
| 1 | Obligation | key and product code |
| 2 | Proposed treatment | `proposed_treatments[key]` label |
| 3 | Chosen treatment | select with the E-23 labels allowed for the tenant (the `LEGACY_*` literals only under POL-100 `USER_SELECTED_TEMPLATE`) |
| 4 | SSP basis | `ssp_basis[key].ssp_book_version_id` label and the range, for example "US-LIST 2026-H1 · 69,750.00 – 85,250.00"; for 25-13(b) existing obligations "Inception SSP (ASC 606-10-32-43)" |
| 5 | Override | checkbox "Use another approved SSP version" with a version select and a Justification field (REQ-SSP-006) |

Treatment labels: `SEPARATE_CONTRACT` "Separate contract (ASC 606-10-25-12)"; `PROSPECTIVE` "Prospective (ASC 606-10-25-13(a))"; `CUMULATIVE_CATCH_UP` "Cumulative catch-up (ASC 606-10-25-13(b))"; `MIXED` "Mixed (ASC 606-10-25-13(c))"; `LEGACY_PROSPECTIVE` "Prospective (legacy preset)"; `LEGACY_RETROSPECTIVE` "Retrospective (legacy preset)"; `LEGACY_POB_VC` "Price change (legacy preset)".

When a chosen treatment differs from the proposal, a warning banner inside the step reads "Record why this treatment differs from the proposal." with the button "Record judgement" (drawer, topic `MODIFICATION_TREATMENT_OVERRIDE`, rationale required), and the outline chip "Treatment override" appears in the page header (J-05-ALT-1; REQ-MOD-002). Next is blocked until the judgement record exists. Caption: the treatment summary label.

**As bound to API-R-31 of 1.0 (rev 1.23, CTR-27).** The table holds one row per obligation of the proposal. "Next" saves the treatments and the SSP versions the preparer names instead (`chosen_treatments`, the `ssp_basis` overrides), then classifies. "Record judgement" (`judgement.create`) creates the record with conclusion and rationale, submits it for review and links it with the choice in one save (`judgement_record_id`); "Next" reads "Record the judgement to continue." until then and is open once the record is linked. `/submit` takes the modification only when that record is `REVIEWED`: step 5 keeps "Submit for approval" disabled with "Judgement record <no> waits for review. The modification can be submitted once it is reviewed." and, after a rejection, with the line that asks for a new record or the proposed treatment; the banner then offers "Record judgement" again. A session without `judgement.create` sees the banner without the button and "Ask a workspace administrator for a role that includes preparing judgement records.". The range beside the SSP version is the one of the engine's price test of the added line, read from the row's `price_tests` (rev 1.52; 04 §16.14 rev 1.250, item MOD-PRICE-TEST-FACT-1) and written "<low> to <high>" (every catalogue message carries a word), or its point for an entry with a point: the row states it whatever the preparer answered, so a draft opened after its answers were confirmed shows it as the visit that classified does. A row that states no price test for the line — not classified or edited since, a line the engine does not test, an attestation where no SSP entry resolves — shows the version alone. The range or point is printed beside the label of the stored basis only while that basis is the version the price test read (§7.5): beside a version the preparer named instead ("Use another approved SSP version") the label stands alone, because the figures of the test are not that version's. "Override" renders for an obligation with an `ssp_basis` entry when approved versions of the contract currency are readable (`ssp.read`). Rev 1.42 (04 §16.14 rev 1.188, item MOD-PATCH-CLEAR-1): a save whose choices are all the proposal again takes the override record off the row (`judgement_record_id: null`); the record itself stays as it is. Rev 1.66 (04 E-57 rev 1.242): a record explains a departure while it is sent for review or reviewed. A rejected and a discarded record explain nothing: the banner keeps naming the record with its status — "Judgement record <no>: <status>.", the status in the words of §0.8 — and offers "Record judgement" again, and "Next" reads "Record the judgement to continue."; before rev 1.66 a discarded record read as one that waits, and no new record was offered. While the linked record is a draft the banner offers "Discard" (§4.1.3's command) in place of "Record judgement": the draft holds the submission (§7.8) and is discarded first.

### 7.7 Step 4 Impact preview

Binding: `POST /modifications/{id}/preview` (202 job `CONTRACT_COMPUTE` or `POLICY_SIMULATION` per 05), then `GET /modifications/{id}` field `impact_preview` (04 API-S-ImpactSummary, also returned in the job's `result.summary`: `{transaction_price_before, transaction_price_after, catch_up_total, catch_up_by_obligation[], remaining_allocation_before[], remaining_allocation_after[], revenue_by_period[] {period_key, before, after, change}, rpo_before, rpo_after, rpo_date, balances_before[], balances_after[], journal_lines[] {gl_account, account_role, debit, credit}, progress_before, progress_after, replay_from_date, posting_period_key, origin_period_key}`).

| Region | Content |
|---|---|
| Job indicator | "Calculating preview" with elapsed time (DS-CMP-24) |
| Impact summary | DS-CMP-06 strip, heading "Impact summary (<currency>)": Transaction price (after; secondary "Before <before>"); Catch-up (`catch_up_total`, DS-FMT-31); Revenue <context period label> (after; secondary "Before <before>"); RPO at <rpo_date> (after; secondary "Before <before>"); Journal lines (count). Every figure is an Explain trigger on the preview trace |
| Allocation by obligation | Static table Obligation, Treatment, Remaining before, Remaining after, Change (DS-FMT-31), Catch-up (DS-FMT-31); added obligations show "—" before |
| Progress | For cost-to-cost obligations, the line "Progress <progress_before> → <progress_after>" |
| Revenue by period | Static table Period, Before, After, Change; six periods from the effective period |
| Balances | Static table Balance, Before, After (labelled balances only, D-12) |
| Journal preview | Static table Account (code · name), Account role, Debit, Credit, with totals rule; or the text "No journal lines at the modification date." |
| Closed period | Info banner "Effective in closed period <origin period label>. The effect posts to <posting period label> with origin period <origin period label>." (D-19) |

States: failed job (SCR-ST-12, "The preview could not be calculated. Nothing was changed."); stale preview after any change in steps 1 to 3 (warning banner "The preview is out of date. Run it again before submitting." with "Run preview"). Caption: "Catch-up <catch_up_total>".

**As bound to API-R-31 of 1.0 (rev 1.23, CTR-27).** Entering step 4 runs the preview of a row that holds none, once for a row version; a stored preview is shown without a run. API-S-ImpactSummary answers neither the difference of the remaining allocation nor totals of the journal lines, and the browser computes no money (DG-FE-08; ruling R-93 (c)): the allocation table has no "Change" column and the journal preview no totals rule. The figures are not Explain triggers, because a dry run keeps no trace. "Revenue <period>" in the strip is the row of the context period, else the first row. "Run preview" in the stale banner opens step 4; it reads "Finish the steps before the preview first." while an earlier step is not done and is absent on step 4 itself, which is already running the preview. Rev 1.52 (04 API-S-ImpactSummary rev 1.210, item MOD-PREVIEW-JOURNAL-RULE-1): the journal preview lists the entries the approval's computation would post at the preview's instant — the change's effect together with the amounts of the period that are not posted yet — so an account may show both sides and the lines move with the open period; "No journal lines at the modification date." stays the text of a preview without lines. Under the table, or under that text, the step states the two members the API answers: "Computed <`computed_at`, DS-FMT-17> for <period label of `computed_period_key`>: the entries the approval would post then — the change's effect with the period's amounts not posted yet.". Where the latest postable period (`open`, `closing` or `reopened`) of the contract's entity in the primary book (`GET /periods`, which answers that book when none is asked) is no longer that period, a warning banner reads "<period label> is no longer the latest open period. The entries at approval will differ from these." with "Run preview", which computes the preview again and stores it in place of the one shown; the warning holds nothing back — the stored preview is not stale, and `/submit` takes it. SF-07:detail shows the same line under every stored preview and the warning, without a command, while the modification is a draft or its request is pending. A preview stored before the API answered the two members shows neither.

**A stored preview the reader is not shown (rev 1.77; 04 §16.10 rev 1.300 "Who reads a stored preview", lane QA-BE's item MOD-PREVIEW-READ-SCOPE-1 on the screens, a release blocker; register index 276).** The API answers the stored preview of a modification to a member who holds `contract.read` for every contracting entity of the contract's combination group. To every other reader of the row it answers `impact_preview` null with `impact_preview_withheld` true; `impact_summary.catch_up_total`, the catch-up of the contract's own obligations, and `impact_preview_sha256` are answered to every reader of the row. A row HOLDS a stored preview when `impact_preview` is not null or `impact_preview_withheld` is true. The wizard asks that one rule wherever it asks whether the row is previewed — which step is open, the caption of step 4, the banner of a stale preview, whether step 4 runs a preview and whether the row is classified again — and the tables alone ask `impact_preview`. Where the preview is withheld, step 4 shows, in the place of the tables, the info banner "You are not shown this preview" with the text "The stored preview holds figures of legal entities outside your access. It is shown to people whose access covers every entity of the contract's combination group." and, where the row states the catch-up, the line "Catch-up of this contract's obligations: <catch_up_total, DS-FMT-05 and DS-FMT-31>.". The step runs no preview for such a row and offers no "Run preview" — a second run changes nothing for that reader — and "Next" is available: `/submit` and its refusal, shown with the API's sentence, decide the rest. The caption of the step reads "Catch-up <catch_up_total>" from `impact_summary`. A row that holds no stored preview is as before: the step runs the preview, and a member the route refuses (04 §16.10 rev 1.295) reads the 403's sentence, "This item belongs to legal entities outside your roles, so you cannot preview it.". Before rev 1.77 the wizard read a withheld preview as none (measured before the build): step 4 asked for a new one — refused with that sentence to a member whose roles do not reach every entity of the group, while nothing said that a preview is stored — and for a member the route takes and the read does not answer (roles that reach every entity of the group, `contract.read` not for every one; with the ten default roles there is none) the step asked one preview and then stayed on "Calculating preview" with "Next" unavailable, so that member did not reach the submission the API takes.

### 7.8 Step 5 Submit

Content: summary definition list (Kind, Reference, Effective date, Treatments, Linked estimate versions, Linked judgement records, Flags); Comment (optional, textarea); primary "Submit for approval" → `POST /modifications/{id}/submit` with `If-Match`. On success the status chip becomes Pending approval, toast "Submitted for approval. Request <request no> is waiting for approval." (rev 1.42; PRD rev 1.158 J-06.5: one submission routes one request — the linked estimate versions are approved and the override record is reviewed before it, and `/submit` answers one line per linked version that is not approved, PRD ERR-87), and the step shows "Approval routing": one row per step of the request (`GET /approvals/{approval_request_id}`): "<step name> · <required permission label> · <status chip>", plus "Linked requests" (the linked estimate versions, each approved before the submission, and the judgement records). Secondary "Withdraw request" (preparer; optional comment) returns the modification to Draft. Editing a submitted modification opens the confirmation "Edit this submitted modification? The pending approval request is voided and approvers are notified." before returning to step 1 (BR-PLT-05; J-05-ALT-2).

**As bound to API-R-31 of 1.0 (rev 1.23, CTR-27).** `/submit` takes no `If-Match`. The summary lists Kind, Reference, Effective date, Treatments, Linked estimate versions (rev 1.51: each as "<element code> v<n>" with its status chip, or "No estimate version is linked."), Linked judgement records and Flags. "Submit for approval" is unavailable while a linked estimate version is not approved — a draft, a pending, a rejected or a withdrawn one; a discarded version is not counted — with the sentence of PRD ERR-87 for the first of them, "Estimate version <element code> v<n> of this modification is not approved. It is approved before the modification is submitted.", as it is unavailable while the override record waits for its review (§7.6); the API's refusal stays the backstop (rev 1.51; 04 §16.14 rev 1.210). A refusal of `/submit` (REQ-MOD-001 not classified, REQ-PLT-015 no preview, REQ-MOD-002 a departure without a reviewed record, and the unconfirmed answers of item MOD-QUESTIONNAIRE-GUARD-1 once that is on main) is shown with the API's messages. After the submission the screen is the read-only detail of §7.9 with the stepper complete; "Linked requests" lists the linked estimate versions — the table of §7.4 under the heading "Linked estimate versions", with a last column "Request" that links the request of a version that has one ("View request"; rev 1.51) — and, below them, the linked judgement records. The toast names the request by its number, read from `GET /approvals/{approval_request_id}` — the read the routing is shown from — and reads "Submitted for approval." alone when that read fails (rev 1.42). The answers of `/submit` and `/withdraw` are the row as `GET /modifications/{id}` answers it, with its stored preview (04 §16.14 rev 1.188, item MOD-ANSWER-PREVIEW-1; rev 1.42): the screen takes the row from the answer and reads it no second time. "Withdraw request" renders for the preparer of the request and asks for a comment, which `/withdraw` requires; "Edit" renders for a holder of `modification.create`. Rev 1.66 (PRD ERR-95; 04 §16.14 rev 1.242, item MOD-LINKED-JUDGEMENTS-1): "Submit for approval" is unavailable as well while a judgement record whose subject is the modification is a draft or waits for review, with the sentence of PRD ERR-95 for the first of them, "Judgement record <judgement no> of this modification is not reviewed. It is reviewed, or discarded, before the modification is submitted."; a rejected, a superseded and a discarded record hold nothing. The override record keeps its own lines — "waits for review", and after a rejection the line that asks for a new record — and a discarded one reads "Judgement record <no> is not reviewed (Void). Record a new one in step Treatment, or choose the proposed treatment.". The API's 409 stays the backstop and is shown as it comes, one sentence per record. The summary names each linked record with its status in the words of §0.8.

### 7.9 SF-07:detail (not Draft)

Read-only sections in order: header (reference, kind, effective date, status chip, flags); "Change" (lines table); "Answers" (questions and answers per obligation); "Treatments" (table of §7.6 without controls); "Impact preview as submitted" (from the approval request `impact_preview.summary`, identical tables to §7.7, with the note "Snapshot <sha256 prefix> reviewed by the approver."); "Approval" (DS-CMP-16 routing steps with decisions and comments); "Applied" (applied event, new contract version link to SF-03:history `?view=versions`, modification register link `/reports/modification_register?f.reference=is:<reference>`). Status `APPROVED` with a quarantined computation shows the negative banner of §4.1.5 priority 1.

**As bound to API-R-31 of 1.0 (rev 1.23, CTR-27).** The header is the `h1` "Modification <reference>" (the breadcrumb ends in the reference) with the status chip, the line "<kind label> · effective <date>" and the flags of the request (`GET /approvals/{id}` `flags`, and "Treatment override" when a chosen treatment departs). "Impact preview as submitted" reads the row's own stored preview (`impact_preview`, `impact_preview_sha256`), the one `/submit` handed to the request, so a reader who cannot open the request sees it too — where the API answers that reader the stored preview (rev 1.77 — **replaced:** every reader of the row; 04 §16.10 rev 1.300 answers it to a member who holds `contract.read` for every entity of the contract's combination group). Where it is withheld (`impact_preview_withheld`) the section shows the banner "You are not shown this preview" of §7.7 with the catch-up line and, where the row states the hash, the snapshot line; before rev 1.77 the section read "No preview was stored." for such a reader, of a modification that was submitted with one. A request the reader cannot see reads "The approval request is not visible to you.". A `DRAFT` opened without `modification.create` renders this detail. The banner of a quarantined computation is not bound until API-S-Contract answers `computation` (item W-17). Rev 1.52 (04 §16.14 rev 1.250 `price_tests`, item MOD-PRICE-TEST-FACT-1): "Answers" shows the sentence of the price test of an added line under the answer of its price question, as a second description of that question, and "Treatments" prints the range or the point of the test beside the SSP basis, both by the rules of §7.5 and §7.6 — the reviewer of the request reads the two figures beside an attestation as the preparer did.

**A rejected modification (rev 1.65; PRD SM-03 `REJECTED` → `DRAFT`, "Revise"; 04 §16.14 rev 1.236, item MOD-REJECTED-REVISE-1).** Under the header an info banner reads "Modification <reference> was rejected. Revise it to submit it again." with the link "View request" — the request the row names, where the request screen is built and the reader can open the request — and, for a holder of `modification.create` for the contract's contracting entity (§0.6 SCR-PERM-02 (a)), the command "Revise". The banner is the one place of the command; a rejected modification shows no stepper, no "Edit" and no "Withdraw request", since it has no pending request. "Revise" opens the confirmation "Revise this modification?" with the consequence "It returns to Draft: the proposal, the classification and the preview are made again. The rejected request stays closed; the next submission makes a new one." and then sends `PATCH /modifications/{id}` with an empty body, the edit that returns the row to Draft and changes no member the preparer wrote. On its answer the wizard opens at step 1 with the row as stored and the banner of a revised draft (§7.10); an answer that comes after the member has left the page opens nothing (dev-guide DG-FE-03 rule (3)). A refusal is shown in the confirmation with the API's messages, and the detail stays. "Approval" keeps the routing of the rejected request: the step the rejection was decided at with the decision and its comment, and the steps behind it as "Skipped".

### 7.10 States

| State | Rendering and copy |
|---|---|
| Loading | Stepper skeleton, form skeleton |
| Contract not active | Page empty state "Modifications apply to active contracts" with description "<external id> is <status label>." and link "Back to the contract" |
| Not found | SCR-ST-07 "Modification not found" |
| No permission | SCR-PERM-01 "modifications", permission label "preparing modifications" |
| Error on save | Field errors per DS-CMP-21; 412 SCR-ST-09 |
| Pending approval | Step 5 routing view; the stepper shows every step complete and step 5 "Pending approval" |
| Voided request (stale) | Warning banner "The approval request was voided because this modification changed after submission. Resubmit it." (NTF-04; a warning since rev 1.42, as on an estimate version whose request the API voided, §8.3) |
| Rejected | SF-07:detail: info banner "Modification <reference> was rejected. Revise it to submit it again." with "View request" and, for a holder of `modification.create` for the contract's entity, "Revise" (§7.9; rev 1.65) |
| Revised draft | Info banner "This draft revises a rejected modification. Request <request no> stays closed; submitting makes a new one." with "View request" (rev 1.65) |
| Preview not shown | Info banner "You are not shown this preview" with "The stored preview holds figures of legal entities outside your access. It is shown to people whose access covers every entity of the contract's combination group." and the line "Catch-up of this contract's obligations: <amount>.", in the place of the preview's tables on step 4 and on SF-07:detail (§7.7, §7.9; rev 1.77) |

**As bound to API-R-31 of 1.0 (rev 1.23, CTR-27).** A save answers no 412 (§7.3). A command the server did not answer shows "The server could not be reached. Try again." and keeps the input. The voided-request banner shows on the wizard of a `DRAFT` whose request reads `VOIDED` (`GET /approvals/{approval_request_id}`); a request its preparer withdrew reads `WITHDRAWN` and shows no banner (rev 1.42). A contract whose currency reference cannot be read does not open the form (DS-FMT-03). Rev 1.65 (04 §16.14 rev 1.236, item MOD-REJECTED-REVISE-1): the row of a revised draft names the rejected request until its next submission makes a new one, and while that request reads `REJECTED` the wizard shows the banner of "Revised draft" above the step, on every step, with "View request" where the request screen is built. The two banners of a draft's earlier request, "Voided request (stale)" and "Revised draft", show on the read-only detail of a `DRAFT` as well — the rendering of §7.9 for a reader without `modification.create` — so that the record says the same to every reader; before rev 1.65 that detail showed neither. A request the reader cannot open (the read of `GET /approvals/{approval_request_id}` fails) shows no banner of a draft, since its status is not known, and the banner of a rejected modification then offers no "View request".

### 7.11 Keyboard and copy

Keyboard: stepper links in Tab order; "Next" is the default button of each step (Enter in single-field forms only, DS-CMP-21); radio groups APG Radio Group. Copy keys: `modifications.wizard.title.new` "New modification"; `.steps.change` "Change"; `.steps.questionnaire` "Questionnaire"; `.steps.treatment` "Treatment"; `.steps.preview` "Impact preview"; `.steps.submit` "Submit"; `.next` "Next"; `.back` "Back"; `.submit` "Submit for approval"; `.discard` "Discard draft"; `.discardTitle` "Discard this draft modification?"; `.discardDescription` "The draft is voided and can no longer be edited or submitted."; `.discarded` "The draft modification was discarded." (the three since rev 1.42); `.override.banner` "Record why this treatment differs from the proposal."; `.preview.noJournal` "No journal lines at the modification date."; `.preview.stale` "The preview is out of date. Run it again before submitting."; since rev 1.51 `.linked.versions` "Linked estimate versions", `.linked.addVersion` "Add estimate version", `.linked.noVersions` "No estimate version is linked.", `.linked.noElements` "Add an estimated element on the Estimates tab first." and `.submit.versionNotApproved`, the sentence of PRD ERR-87; since rev 1.52 (04 §16.14 rev 1.250) the sentences of an attested price test, `modifications.prefill.priced_at_ssp.attested` "Attested by the preparer as priced at the standalone selling price. Price {price}; SSP {low} to {high} ({version}).", `.attestedPoint` "… Price {price}; SSP {point} ({version})." and `.attestedNoSsp` "… Price {price}; no approved SSP applies to the added goods or services at the modification date."; and `modifications.impact.journal.computed` and `.journal.periodMoved`, the two sentences of §7.7; since rev 1.65 `modifications.detail.rejected` "Modification {reference} was rejected. Revise it to submit it again.", `.revise` "Revise", `.reviseTitle` "Revise this modification?", `.reviseDescription` "It returns to Draft: the proposal, the classification and the preview are made again. The rejected request stays closed; the next submission makes a new one." and `modifications.wizard.revised` "This draft revises a rejected modification. Request {number} stays closed; submitting makes a new one."; since rev 1.77 `modifications.impact.withheld.title` "You are not shown this preview", `.text` "The stored preview holds figures of legal entities outside your access. It is shown to people whose access covers every entity of the contract's combination group." and `.catchUp` "Catch-up of this contract's obligations: {amount}."

### 7.12 Sample world

| Journey | Content (asserted values) |
|---|---|
| J-05 K-02 `SF-ORD-10002` | Step 1: Upgrade, add 50 seats `AVM-SEAT-MO`, 16 Sep 2026 – 31 Dec 2027, price 60,000.00, reference `CR-MARROWBY-2026-09`. SSP basis `US-LIST 2026-H1`: remaining O1 155,178.08; added seats 69,750.00, the low bound of their range 69,750.00 – 85,250.00 (the stated price is below the range; PRD rev 1.21). Step 2 answers Yes / No (60,000.00 is below 69,750.00) / Yes. Step 3 Prospective for O1 and the added obligation. Step 4: transaction price 240,000.00 → 300,000.00; catch-up 0.00 per obligation; revenue Sep 2026 9,863.01 → 11,769.80; Oct 2026 10,191.79 → 14,132.46; RPO at 16 Sep 2026 155,178.08 → 215,178.08; remaining O1 155,178.08 → 148,451.55; added obligation 66,726.53; journal preview, computed while Sep 2026 is the latest postable period: 2100 Contract liability Dr 2,120.55 / Cr 213.76 and 4010 Revenue - services and subscriptions Dr 213.76 / Cr 2,120.55 — the entries the approval would post then, the change's effect with September's amounts not posted yet (rev 1.52; 04 API-S-ImpactSummary rev 1.210; measured on the e2e world on 2026-10-01), with the line "Computed <date and time> for Sep 2026: …". Step 5: one routing step (WLD-X-05, WLD-X-06) |
| J-06 K-03 `PRJ-CB-2026-01` | Reference `CR-CASTELLAN-2026-09`, effective 10 Sep 2026, consideration +150,000.00, scope "Floor plan change (change order CO-07)"; linked EAC version 2 820,000.00 (rationale "Change order CO-07 adds 120,000.00 of cost"); bonus version 2 200,000.00, method most likely amount; judgement `CONSTRAINT` "Completion within the extended 30-month window is highly likely; no significant reversal expected." Answer No to the one question asked, the remaining goods — the change order adds no line, so no question is asked about added goods; proposed "Cumulative catch-up (ASC 606-10-25-13(b))". The two estimate versions are submitted and approved before the modification, each on a request `ESTIMATE_VERSION` with two steps: EAC version 2 with a catch-up of (87,804.88), bonus version 2 with a catch-up of 102,439.03. Preview of the modification after them: transaction price 1,200,000.00 → 1,350,000.00; catch-up at the change order's date 91,463.41, of which 14,634.15 was posted with the two estimate versions; revenue Sep 2026 14,634.15 → 91,463.41; journal preview Dr 2100 Contract liability 76,829.26, Cr 4010 Revenue - services and subscriptions 76,829.26. Submit routes one request `MODIFICATION` with two steps (rev 1.51; PRD rev 1.158 J-06.1 to J-06.6, rev 1.164 J-06.3 and J-06.4; WLD-X-10) |

### 7.13 Test hooks, light and dark, accessibility

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Stepper | `getByRole("navigation", {name: "Modification steps"})` | `SF-07-stepper` |
| Question | `getByRole("radiogroup", {name: /^Is the added price at SSP\?/})` | none |
| Impact summary | `getByRole("region", {name: /^Impact summary/})` | `SF-07-kpi-strip` |
| Allocation table | `getByRole("table", {name: "Allocation by obligation"})` | `SF-07-grid-allocation` |
| Revenue table | `getByRole("table", {name: "Revenue by period"})` | `SF-07-grid-revenue` |
| Override banner | `getByText("Record why this treatment differs from the proposal.")` | `SF-07-banner-override` |
| Preview not shown (rev 1.77) | `getByText("You are not shown this preview")` | `SF-07-banner-preview-withheld` |
| Routing | `getByRole("list", {name: "Approval routing"})` | `SF-07-routing` |

Further hooks (rev 1.23): `SF-07-page` (the wizard), `SF-07-detail-page` (the read-only detail), `SF-07-identifier`, `SF-07-blocked` (the line above the footer), `SF-07-group-<obligation key>`, `SF-07-grid-lines`, `SF-07-grid-treatments`, `SF-07-grid-judgements`, `SF-07-grid-balances`, `SF-07-grid-journal`, `SF-07-summary`, `SF-07-drawer-judgement`, `SF-07-dialog-withdraw`, `SF-07-dialog-edit` and `SF-07-section-<change|answers|treatments|preview|approval|applied>`.

Light and dark: the current step marker `--accent-solid` with `--on-accent`; impact deltas carry `+` or parentheses and never colour (DS-FMT-30). Accessibility: stepper `nav aria-label="Modification steps"` with `aria-current="step"`; each question group is a `fieldset` whose `legend` is the question; preview completion announced politely "Preview calculated."; the override banner is inserted with `role="status"`.

## 8. SF-03:estimates Estimates workbench

### 8.1 Summary

| Field | Value |
|---|---|
| Screen ids and routes | SF-03:estimates `/contracts/:contractId/estimates` (RT-12); SF-03:estimate `/contracts/:contractId/estimates/:estimateId` (RT-13); panel tab `pane=current|versions|evidence` |
| Roles and permissions | Read `contract.read`. "Add estimated element", "New estimate version", "Attest no change", "Submit for approval", "Withdraw" `estimate.create` (ACT-11); approval in SF-12 `estimate.approve` |
| Purpose | Variable consideration, returns, estimated total costs, breakage, likelihood of exercise, royalty accruals and the other E-09 estimates as immutable versions with rationale, evidence, preview and history (D-20) |
| REQ | REQ-TP-002 to REQ-TP-006, REQ-TP-008, REQ-TP-009, REQ-REC-007, REQ-REC-011, REQ-CST-007, REQ-LOS-001; POL-040, POL-042, POL-183 |
| Journeys | J-06.1 (linked versions), J-06.3, J-06.4 (rev 1.51: the linked versions are submitted here, PRD rev 1.158), J-07.1 to J-07.4, J-10.3, J-10.4, J-10-ALT-1, J-11.5, J-11.6; J-13 step 5 attestation (SCREENS_B journey context) |

### 8.2 Wireframes

1440 px (K-03, EAC selected, version 3 pending approval):

<!-- WF:estimates-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Contracts > PRJ-CB-2026-01 . Castellan Build Group Inc. (Demo) (Active)          [*New modificati|
| Work              |  Obligations 1    Estimates 2    Schedules    Billing    Journals    Modifications 1    History  |
|    Home           |                   ===========                                                                    |
| |* Contracts      |+----------------------------+  +----------------------------------------------------------------+|
|    Schedules      || [Filter___] [Add estimated |  | EAC  Estimated total costs <Cost build-up>  [*New estimate vers||
|    Close          || 2 estimated elements       |  | Estimate figures (USD)                                         ||
|    Journals       || Estimated total costs      |  | Estimated total costs  Costs incurred     Progress             ||
|    Reports        |||* EAC                  850,|  | 850,000.00 fn          502,000.00 fn      59.1% fn             ||
| ----------------  |||* v3 . 30 Sep 2026 (Pending|  | (i) Version 3 is waiting for approval.         [View request]  ||
| Govern            || Variable consideration     |  | Current version   Versions   Evidence                          ||
|    Approvals    3 ||  BONUS-CB-01          200,0|  | =============                                                  ||
|    Policies       ||  v2 . 10 Sep 2026 (Approved|  | Effective 30 Sep 2026 . Change in estimate                     ||
|    Data           ||                            |  | Rationale: Steel price escalation (supplier notice 24 Sep 2026)||
|                   ||                            |  | Preview: progress 61.2% -> 59.1% . catch-up (29,169.29)        ||
|                   ||                            |  | No anticipated loss: estimated costs 850,000.00 are below      ||
|                   ||                            |  | the transaction price 1,350,000.00.                            ||
|                   ||                            |  | Evidence: eac-review-castellan-2026-09.xlsx                    ||
|                   |+----------------------------+  |                                                                ||
| Settings          |                                +----------------------------------------------------------------+|
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:estimates-1440 -->

1280 px:

<!-- WF:estimates-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Contracts > PRJ-CB-2026-01 . Castellan Build Group Inc. (Demo) (Active)          [*New modificatio|
| H  |  Obligations 1    Estimates 2    Schedules    Billing    Journals    Modifications 1    History   |
| *Ct|+-----------------------+ +-----------------------------------------------------------------------+|
| Sc || [Filter___] [Add]     | | EAC  Estimated total costs     [*New estimate version] ..             ||
| Cl || Estimated total costs | | Estimated total costs  Costs incurred   Progress                      ||
| Jn |||* EAC    850,000.00   | | 850,000.00             502,000.00       59.1%                         ||
| Rp |||* v3 (Pending appr.)  | | (i) Version 3 is waiting for approval.  [View request]                ||
| -- || Variable consideration| | Current version  Versions  Evidence                                   ||
| Ap ||  BONUS-CB-01          | | Effective 30 Sep 2026 . Change in estimate                            ||
| Po ||                       | | Preview: catch-up (29,169.29)                                         ||
| Da ||                       | +-----------------------------------------------------------------------+|
|    ||                       |                                                                          |
| Se |+-----------------------+                                                                          |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:estimates-1280 -->

### 8.3 Regions and components

| Region | Component | Content |
|---|---|---|
| Master | DS-CMP-08 | Toolbar "Filter estimates", button "Add estimated element"; caption "<n> estimated elements"; rows grouped under kind headings (E-09 labels, §8.4) |
| Master row | DS-CMP-08 | Line 1 `element_code` (mono) and the key figure of the current version (§8.4); line 2 "v<version_no> · effective <date>", status chip of the latest version, warning chip "Reassessment due" when an open `VC_REASSESSMENT_MISSING` exception names the element |
| Detail header | DS-CMP-06 compact | `h2` `element_code`; kind label; outline chip method label with a LockSimple icon and the tooltip "The estimation method is fixed after the first version (POL-040)." after version 1 (J-07.1; BR-TP-01); allocation target label ("Whole contract", "Specific obligations: <keys>", "Increments"); actions primary "New estimate version", secondary "Attest no change" (variable consideration only), overflow "Compare versions", "Copy link" |
| Figures | DS-CMP-06 compact strip | Kind-specific cells (§8.4) |
| Banner slot | DS-CMP-29 | Draft version: info "Version <n> is a draft." with "Edit draft", "Submit for approval", "Discard draft" (confirmation "Discard this draft version?" → `POST /estimate-versions/{id}/discard` → `VOIDED` per SM-04, for every holder of `estimate.create`; the version keeps its number and is no longer the element's latest version; rev 1.33); pending: info "Version <n> is waiting for approval." with "View request" and "Withdraw request"; reassessment due: warning "No estimate version or approved "No change" attestation is effective at <period end>." (IMP-72) with "Attest no change" and "New estimate version" |
| Panel tabs | DS-CMP-07 panel | "Current version" (definition list of the approved version and its preview snapshot); "Versions" (§8.5); "Evidence" (attachments of every version and linked judgement records) |

**As bound to API-R-32 of 1.0 (rev 1.29, CTR-25).** `GET /contracts/{id}/estimates` answers the summaries of an element's current and latest version without their figures. A master row therefore shows the key figure of the element's **latest** version, read from `GET /estimates/{id}/versions` (one read per element, shared with the detail), and line 2 names that version ("v<n> · effective <date>") with its status chip; the figures strip shows the same version under the heading "Estimate figures of version <n> (<currency>)". "Current version" is the APPROVED version; while none is approved the panel says "No version is approved yet. The latest version is shown." above the latest one. Its preview snapshot is the one the API keeps: the dry run a version was submitted with is stored with the approval request of the version, not with the version (REQ-PLT-015; 04 API-S-Approval `impact_preview`), so the panel reads the request of a pending, an approved or a superseded version and shows "Preview" with "Catch-up <amount>" (`impact_preview.summary.catch_up_total`) and "View request", where the whole stored preview is read; a reader the API shows no request to sees no preview, a version that came back (rejected, withdrawn) or is a draft shows none, and the progress before and after is not stored and is not shown. The attachments of the version follow under "Evidence". Both are shown once they are read, and the block is busy until then. The figures are printed without Explain triggers: 04 §16.11 has no estimate object and a version names no explanation. The method chip carries the lock, the tooltip and the name "Method <method>, locked" once a version of the element is approved (04 T-CON-12); the API fixes the method from the element's creation, so the method is never a control. The commands of the two screens are offered where `estimate.create` is held for the contract's legal entity, and the constraint conclusion where `judgement.create` is (§0.6 SCR-PERM-02 (a), rev 1.30). "New estimate version" and "Attest no change" are unavailable, with the reason, while a version of the element is a draft or is pending (rev 1.64: the open version, whichever its number — below; it was the latest version alone); "Attest no change" also needs an approved version; "Compare versions" of the overflow opens the Versions panel. Banner slot: a draft offers "Edit draft" and "Submit for approval" (unavailable with "Attach the evidence to the draft first." while a kind that needs evidence has none); "Discard draft" (rev 1.33; bound in rev 1.51, item EST-DISCARD-1) renders beside them for every holder of `estimate.create` for the contract's legal entity: its confirmation "Discard this draft version?" states the consequence, "The version is voided. It keeps its number and can no longer be edited or submitted."; after the command the toast reads "Version <n> was discarded.", the version reads Void in the Versions panel and is no longer the latest one — the master row, the figures strip and what "New estimate version" waits for follow the highest version number that is not Void, as the API's `latest_version` does (04 §16.14 rev 1.210); a 409 shows the API's messages in the confirmation and the version stays (a version that is no draft any more, rule `DB-03`), and the submission of a version whose modification was discarded shows the API's sentence (PRD ERR-88); a REJECTED or WITHDRAWN version shows "Version <n> was rejected. Edit it to submit it again." (or "was withdrawn") with "View request" and "Edit draft", the edit returning it to DRAFT; the API returns a version to WITHDRAWN also when it voids the request itself (04 E-12; REQ-PLT-014; ruling R-66 (3)), so the pane reads the last request of a WITHDRAWN version, and one that is `VOIDED` with `void_reason = STALE_SUBJECT` shows, as a warning and in the words §15.4 has for a stale request, "The approval request of version <n> was voided: this item changed after submission. Edit the version to submit it again." with the same two actions; a pending version shows "View request" (SF-12:request) and, for the preparer of the request, "Withdraw request" (a confirmation "Withdraw this request?" with an optional comment, as §15.4 has it for the Approvals screens). A banner that depends on a read — the request of a pending or a withdrawn version, the evidence of a draft whose kind needs some — is rendered whole once that read has answered, and its slot is busy until then. A `VOIDED` version (§0.8) is listed with its chip and holds no new version back; nothing else of item EST-DISCARD-1 is bound. "Reassessment due" binds the open `VC_REASSESSMENT_MISSING` item whose `business_key` is the element code and reads its period's end date; nothing raises that item yet (item ENG-S10-GATE-FACTS-1), so the chip and the banner are shown by a component test only. "Evidence" lists, per version, the attachments (File, Size, Uploaded by, Uploaded at) and the judgement records (number, conclusion, status).

**As bound to API-R-32 of 1.0 (rev 1.64, CTR-25; item EST-DRAWER-JUDGEMENT-1; 04 §16.14 rev 1.241).** One version of an element is open at a time (PRD ERR-93). The open version is the one that is a draft or pending, whichever its number — a rejected or withdrawn version below the latest can be returned to draft through the API: it takes the banner and holds "New estimate version" and "Attest no change" back with its reason. A rejected or withdrawn latest version shows its banner, with "Edit draft", only while no version is open: beside an open one its edit would be refused. The API's 409 stays the guarantee and is shown as any refusal. The draft banner of a variable consideration: "Submit for approval" is unavailable with "Record the constraint conclusion in the draft first." while the draft names no `CONSTRAINT` record that is sent for review or reviewed (`judgement_record_id`, read by `GET /judgements/{id}`; PRD IMP-140), after the evidence sentence where both hold; a record whose read fails is left to the API. A draft that carries `parameters.no_change_attestation` — "Attest no change" stored it and its submission failed — is asked neither for evidence nor for a record: the API asks an attestation for its reason alone and refuses the flag itself where the values differ (PRD IMP-139, IMP-141). The pending banner of a variable consideration adds a sentence while the version's record is not reviewed, for the approval is refused until it is (PRD ERR-94): "Judgement record <number> waits for review." for a record that is sent for review, in the words of PRD J-07.3, and "Judgement record <number> is not reviewed (<status>). Withdraw the request to record a new conclusion." for any other status. The record the open version names is among the reads a banner waits for. The status of a judgement record (E-57) is read in the words of §0.8 (rev 1.66), and as its literal where the catalogue holds none.

**Rev 1.66 (CTR-25; PRD ERR-94, its second refusal; PRD SM-10 `DRAFT` → `VOIDED`; 04 API-R-33 rev 1.242).** The approval of a pending version is refused as well once its evidence is no longer attached — the uploader may void the attachment of a submitted version. The pending banner therefore reads the live attachments of a pending version whose kind needs evidence and that is no attestation, the read "Evidence" makes, and where there is none it says under its title "The evidence is no longer attached. Withdraw the request to attach it again.", before the sentence of the record where both hold — the order of the draft's banner. The screen attaches in the draft's drawer alone, so the way it names is the withdrawal. The banner waits for that read as it waits for the record's, and a read that failed is left to the API. An attachment whose file was shredded is not told from the list, for API-S-Attachment states `voided_at` and nothing of a shred: the approval's 409 stays the guarantee. "Evidence" names each judgement record of a version with its number, its conclusion and its status in the words of §0.8. A draft record — one the version drawer created and whose submission was refused (§8.4) — carries "Discard" for a holder of `judgement.create` for the contract's contracting entity, on every view but one of an earlier `known_at`: the command, its confirmation and its refusal are §4.1.3's. The version that names a discarded record asks for a new conclusion, as it does for a rejected one. Rev 1.74 (PRD SM-10 rev 1.199): a rejected record carries "Discard" as well, for the same holder and on the same views.

### 8.4 Kinds, figures and version drawer fields

The version drawer is a wide modal drawer (`--drawer-w-wide`) titled "New estimate version · <element code>". Common fields: Effective date (required); Rationale (required); Evidence (attachments; required for variable consideration, estimated total costs and return rate, SM-04). A preview panel below the fields (`POST /estimate-versions/{id}/preview`, run after save; 202 job whose `result.summary` is 04 API-S-ImpactSummary, API-R-32) shows: Transaction price change; Catch-up; Revenue <context period> before → after; Balances before → after (contract liability, contract asset, refund liability, return asset where not 0); for estimated total costs the loss test sentence. Footer: "Cancel", "Save draft", primary "Submit for approval" (`POST /estimates/{id}/versions`, `PATCH /estimate-versions/{id}`, `POST /estimate-versions/{id}/submit`).

| E-09 kind | Label | Figures (cells) | Kind-specific fields |
|---|---|---|---|
| `VARIABLE_CONSIDERATION` | Variable consideration | Constrained amount; Unconstrained amount; Excluded by the constraint (`excluded_amount`, 04 §16.14 estimates); Effective date | Element type (read-only after version 1); Method (read-only after version 1, tooltip as above); for `EXPECTED_VALUE` a scenarios table Outcome, Amount, Probability (percent); for `MOST_LIKELY_AMOUNT` and `ENTERED_AMOUNT` Outcome and Amount; Unconstrained amount; Most conservative amount; Constrained amount with the hint "Between <most conservative> and <unconstrained>." (IMP-74 on submit); Constraint factors (ASC 606-10-32-12) checkboxes "Highly susceptible to factors outside the entity's influence", "Uncertainty not expected to be resolved for a long time", "Limited experience with similar contracts", "Practice of offering price concessions or changing payment terms", "Broad range of possible amounts"; Judgement record (topic `CONSTRAINT`, created inline) |
| `RETURN_RATE` | Return rate | Expected returns (units); Rate; Carrying cost per unit; Recovery cost per unit | Rate or Expected returns (units); Carrying cost per unit; Recovery cost per unit; Return window ends (`parameters`) |
| `BREAKAGE` | Breakage | Rate; Expected total redemptions | Rate; Expected total redemptions |
| `EAC` | Estimated total costs | Estimated total costs; Costs incurred to date (`costs_incurred_to_date`); Progress (`progress_ratio`) (04 §16.14 estimates) | Estimated total costs (`expected_total_amount`); Expected total hours (`expected_quantity`, labour-hours obligations); Classification radio "Change in estimate" (`CHANGE_IN_ESTIMATE`) or "Error correction" (`ERROR_CORRECTION`, POL-183), where "Error correction" shows the info line "Error corrections go through a period reopen with dual approval." and blocks submission |
| `EXERCISE_LIKELIHOOD` | Likelihood of exercise | Rate | Rate |
| `IMPLICIT_PRICE_CONCESSION` | Implicit price concession | Rate or constrained amount | Rate or Amount |
| `RENEWAL_EXPECTATION` | Expected renewals | Amortisation months | Amortisation months |
| `ROYALTY_ACCRUAL` | Royalty accrual | Estimated royalties; Usage period | Usage period start and end (`parameters`); Estimated royalties (`expected_total_amount`) |
| `EXPECTED_PURCHASES` | Expected purchases | Expected purchases | Expected total amount |

"Add estimated element" drawer (`POST /contracts/{id}/estimates`): Kind; Element code (text, unique per contract); Element type (variable consideration types of T-CON-12, labelled "Bonus", "Penalty", "Performance incentive", "Rebate", "Volume tier", "Price protection", "SLA credit", "Discount", "Return", "Refund", "Implicit price concession", "Claim", "Unpriced change order", "Usage", "Royalty", "Milestone"); Method (E-10 labels "Expected value", "Most likely amount", "Entered amount", "Rate", "Cost build-up"); Allocation target; Target obligations; Allocation criteria evidence (ASC 606-10-32-40, required when the target is not the whole contract). Primary "Add element", then the version drawer opens for version 1.

"Attest no change" modal (DS-CMP-11 form): title "Attest no change for <element code>?"; description "The approved version <n> still applies at <period end>. The attestation goes to approval."; Effective date (default: end date of the context period); Rationale (minimum 10 characters); primary "Submit attestation" (creates a version with `parameters.no_change_attestation = true`, then submits). Rev 1.66: the help of Rationale says what belongs in it, one sentence before the minimum — "Say what you reviewed: the constraint factors, and that they stand as they were." An attestation states that the constraint was assessed again (ASC 606-10-32-11) against its factors (ASC 606-10-32-12) — the drawer's own list, "Constraint factors (ASC 606-10-32-12)" — and that they stand, not only that the amount is unchanged. The sentence is part of the field's description (the `hint` of the kit's reason field); it asks for content and holds nothing back, and the API's rule stays the length (PRD IMP-139).

Errors: `eac-below-costs-incurred` renders ERR-13 on the Estimated total costs field, for example "Estimated total costs (500,000.00) cannot be lower than costs incurred to date (502,000.00)." (J-10-ALT-1); `ESTIMATE_METHOD_LOCKED` renders IMP-71 on Method.

**As bound to API-R-32 of 1.0 (rev 1.29, CTR-25).** The method and, for a variable consideration, the element type are the element's (T-CON-12): the drawer shows them and edits neither, so `ESTIMATE_METHOD_LOCKED` cannot arise from the screen. A new version starts from the figures of the approved version (else of the latest one); the effective date and the rationale are its own. The kind-specific fields are the members of the 04 T-CON-13 row of the kind: amounts in the version's currency, a rate typed as a percent and sent as the ratio, units and hours as quantities, dates as dates. The kind's first figure is required; a return rate takes a rate or the expected returns and its three parameters; an implicit price concession a rate or an amount; a royalty accrual both dates of its usage period, in order. A parameter the drawer does not show (`refund_liability_target`, `uninstalled_materials_cost`) stays as the version it started from holds it. The tenth E-09 kind, `SHARE_BASED_CONSIDERATION` (label "Share-based consideration"): figures "Expected related revenue", "Grant-date fair value", "Grant date"; fields Expected related revenue (`expected_total_amount`), Grant date, Grant-date fair value, the checkbox "Vesting is probable" and Expected forfeiture ratio (optional). Scenarios are the form-held line grid of DESIGN_SYSTEM rev 1.7 with "Add outcome".

The constraint checklist (`constraint_checklist`, variable consideration only) holds one boolean per key, true where the factor is present; every save writes all five; other kinds send null:

| Key | Label | Factor |
|---|---|---|
| `susceptible_to_outside_factors` | Highly susceptible to factors outside the entity's influence | ASC 606-10-32-12(a) |
| `long_resolution_period` | Uncertainty not expected to be resolved for a long time | ASC 606-10-32-12(b) |
| `limited_experience` | Limited experience with similar contracts | ASC 606-10-32-12(c) |
| `price_concession_practice` | Practice of offering price concessions or changing payment terms | ASC 606-10-32-12(d) |
| `broad_range_of_amounts` | Broad range of possible amounts | ASC 606-10-32-12(e) |

The constraint judgement is one field, "Constraint conclusion" (for a holder of `judgement.create`; asked at the submission since rev 1.64, below): on save the drawer records a `CONSTRAINT` judgement record whose subject is the version, with the contract of the estimate (`contract_id`: `POST /judgements` defaults none for an estimate version, and a record that names no contract is read by no computation), the conclusion, the version's rationale and the questionnaire `{estimate_key: <element code>, remote: false}` (the member `remote` attests the remoteness of a breakage, ENGINE_SPEC_B S09-R-29), submits it for review and links it (`judgement_record_id`); a linked record that is sent for review or reviewed is shown as "<number> · <conclusion>" and no second one is offered (rev 1.64: a record that does not stand is replaced, below). The classification of an estimate of total costs is asked and **not stored** with the version — 04 holds no member for it (item EST-CLASSIFICATION-RECORD-1): "Error correction" shows its line and makes "Submit for approval" unavailable with "An error correction is not submitted as an estimate version."; no read view shows a classification. Evidence files are attached after the save (`POST /files` with purpose `ATTACHMENT`, then `POST /attachments` on the version); the screen asks for at least one at submission of a variable consideration, an estimate of total costs and a return rate, as the API does (04 §16.14 rev 1.241; PRD IMP-138; rev 1.64). "Save draft" stores the version (`POST` the first time, `PATCH` afterwards) and the preview runs after every save and from "Run preview"; a step that failed is taken up again without creating anything twice, and a step whose answer was lost goes out again under the Idempotency-Key it had (dev-guide DG-FE-05). The preview shows "Catch-up" and a table "Before and after (<currency>)" with Transaction price, Revenue <context period>, Progress where the summary answers it, and the labelled balances: API-S-ImpactSummary answers neither one "Transaction price change" figure nor a loss test, and the browser compares and subtracts no money (ruling R-93 (c)), so the loss test sentence is not rendered (item EST-PREVIEW-LOSS-TEST-1) and the catalogue holds no `.lossTest` key. Footer: "Cancel", "Save draft", "Submit for approval" (DESIGN_SYSTEM rev 1.10). After the submission the drawer closes and a toast names the request, or says that the version was approved on submission. The API's refusals are shown on the fields `errors[]` names, `eac-below-costs-incurred` on "Estimated total costs".

"Add estimated element" also takes "Obligation" (optional; T-CON-12 `obligation_id`, the obligation the element measures, for example that of an estimate of total costs); every E-10 method is offered and the kind proposes one (Cost build-up for estimated total costs, Rate for a return rate, breakage and the likelihood of exercise, Entered amount otherwise, none for a variable consideration); the direction is not asked (the API derives it). "Attest no change" needs an approved version: it creates a version with that version's figures, scenarios and checklist and `parameters.no_change_attestation = true`, then submits it.

**The constraint's judgement record (rev 1.64, CTR-25; item EST-DRAWER-JUDGEMENT-1; 04 §16.14 rev 1.241; PRD IMP-138 to IMP-141).** A variable-consideration version is submitted with a `CONSTRAINT` record of its element that is sent for review or reviewed. "Submit for approval" asks for it: the version names such a record or a conclusion is typed now, else the field reads "Write the constraint conclusion. A variable consideration version names its judgement record."; "Save draft" stores the version without it. A new version names no record and records its own conclusion: the record of the version it starts from is that version's — the `POST` sends none and the API copies none. The screen does not offer the element's earlier reviewed record, which the API would take (04's stated limit): a changed amount is a new conclusion (ASC 606-10-32-14) and an unchanged one is an attestation; the drawer does not compare values to tell an attestation, the API alone does, and "Attest no change" is the command for it. A linked record that is neither sent for review nor reviewed — a draft, a rejected, a superseded or a discarded one — is shown as "<number> · <conclusion> (<status>)" with the conclusion field under it: on save a new record is created, sent for review and linked in its place, and the old one stays under "Evidence". It is not revised, which only its creator may do (04 T-CON-19). While the read of a linked record (`GET /judgements/{id}`) has not answered, or where it fails, the drawer shows "A judgement record is linked." and leaves the question to the API. Without `judgement.create` the field is not shown and "Submit for approval" of a version that names no such record is unavailable with "Recording the constraint conclusion needs the permission judgement.create."; "Save draft" works. The findings of a submission stand on the fields they are about, placed by their rule id: `ESTIMATE_EVIDENCE_REQUIRED` (IMP-138, which names no field) under "Evidence", and `ESTIMATE_CONSTRAINT_RECORD` (IMP-140, on `judgement_record_id`) on "Constraint conclusion" where that field stands, else in the banner — the record is read again after a refusal, so one that was rejected meanwhile gives way to the field. `ESTIMATE_ATTESTATION_REASON` (IMP-139) stands on "Rationale", `ESTIMATE_ATTESTATION_VALUES` (IMP-141) in the banner of "Attest no change", and the 409 of an open version (ERR-93) in the banner of the drawer.

**A preview the reader is not shown (rev 1.79; the supervisor's order of 2026-10-03; register index 300 on the screens; 04 API-S-Job `result` rev 1.314, §16.10 "Who reads a stored preview").** The dry run of an estimate version keeps no document: its job answers the summary, to a reader who holds `contract.read` for every entity of the contract's combination group. Where the job answers `result.summary_withheld` true, the preview panel shows the info banner of §4.9.3 (3) — "You are not shown this preview", with its text — in the place of the table of before and after, with no figure beside it. "Run preview" is not offered while that answer stands, as on step 4 of the modification wizard (§7.7 rev 1.77); the next "Save draft" runs the preview as before, and "Submit for approval" does not wait for it. **Replaced:** the panel read a withheld summary as a preview that had not run — "The preview of this draft has not run here yet." with "Run preview", which ran it again to the same answer (measured on bc74313be).

### 8.5 Versions panel

DataGrid (small; static variant when at most 100 versions), caption "Versions":

| # | Header | Field | Format | Alignment | Visible |
|---|---|---|---|---|---|
| 1 | Version | `version_no` | integer | end | yes |
| 2 | Status | `status` | chip (§0.8) | start | yes |
| 3 | Effective date | `effective_date` | DS-FMT-16 | start | yes |
| 4 | Figure | kind key figure (§8.4 first cell) | DS-FMT-04, DS-FMT-09 or DS-FMT-11 | end | yes |
| 5 | Constrained amount | `constrained_amount` | DS-FMT-04 | end | variable consideration only |
| 6 | Rate | `rate` | DS-FMT-09 | end | rate kinds only |
| 7 | Attestation | `parameters.no_change_attestation` | DS-FMT-22 | start | variable consideration only |
| 8 | Prepared by | `created_by` | user | start | yes |
| 9 | Approved by | `approver` (04 §16.14 estimates) | user | start | yes |
| 10 | Approved at | `approved_at` (04 §16.14 estimates) | DS-FMT-17 | start | yes |
| 11 | Rationale | `rationale` | text, truncated with tooltip | start | yes |

Selecting two versions enables "Compare versions" (DS-CMP-16 field diff, caption "Changes from version <n> to version <m>").

**As built (rev 1.29, CTR-25).** The panel is the static table at every size, with a selection column: the screen holds every version of the element for the figures and the comparison, and no DataGrid variant is built for an element of more than 100 versions. The table scrolls inside its own viewport with the selection and the version number pinned (DESIGN_SYSTEM DS-SP-07), and the rationale is one truncated line with its whole text as the tooltip. For a variable consideration column 4 and column 5 are the same figure (§8.4's first cell is the constrained amount) and it is shown once, under "Constrained amount"; "Rate" is its own column where the kind's key figure is not the rate (a return rate). The comparison is of the two rows the screen holds, field by field (effective date, the kind's members, scenarios, constraint factors, attestation, rationale), the earlier version first; it states no difference in money (ruling R-93 (c)).

### 8.6 Data bindings

| Region | Endpoint | Fields |
|---|---|---|
| Master | `GET /contracts/{id}/estimates` (T-CON-12 columns plus `current_version` and `latest_version` summaries `{id, version_no, status, effective_date, approver, approved_at}`; 04 API-R-32, §16.14) | `id`, `estimate_kind`, `element_code`, `vc_element_type`, `method`, `allocation_target`, `target_obligation_ids`, summaries |
| Detail, Versions | `GET /estimates/{id}/versions` (T-CON-13 columns plus the 04 §16.14 version additions) | as §8.4, §8.5 |
| Evidence | `GET /attachments?subject_type=estimate_version&subject_id=<id>` per version; `GET /judgements?subject_type=estimate_version&subject_id=<id>` | file fields; judgement fields |
| Exceptions | `GET /exceptions?contract=<id>&code=VC_REASSESSMENT_MISSING&status=OPEN` | `business_key` |

Rev 1.29: the master also reads `GET /estimates/{id}/versions` of every element (the list answers no figure); the Current version panel reads `GET /approvals/{id}` of the version it shows (the stored preview) and that version's attachments; the banner of a pending or a withdrawn version reads `GET /approvals/{id}` — for the preparer of a pending request, and for the reason a request was voided — and a reader who cannot see the request is offered no withdrawal and reads "was withdrawn"; the tab count "Estimates <n>" is the list's `X-Erev-Total-Count`. No estimate command takes `If-Match`.

### 8.7 States

| State | Rendering and copy |
|---|---|
| Loading | 6 skeleton rows; detail skeleton |
| Empty | Title "No estimated elements"; description "Variable consideration, returns, estimated total costs, breakage and exercise likelihood appear here once a contract has them."; action "Add estimated element" |
| Nothing selected | "Select an estimated element to see its versions and evidence." |
| Error | SCR-ST-05 "Could not load estimates" |
| Pending approval, draft, reassessment due | Banner slot §8.3 |
| Stale | Workbench banner |

### 8.8 Keyboard and copy

Keyboard: DS-CMP-08 master keys; `N` opens "New estimate version" when focus is in the detail pane and not in a field (listed in the shortcuts dialog). Copy keys: `contracts.estimates.new` "New estimate version"; `.add` "Add estimated element"; `.attest` "Attest no change"; `.methodLocked` "The estimation method is fixed after the first version (POL-040)."; `.lossTest.none` "No anticipated loss: estimated costs {eac} are below the transaction price {tp}."; `.lossTest.loss` "Anticipated loss: estimated costs {eac} exceed the transaction price {tp}. A loss provision of {amount} is recognized."; `.reassessmentDue` "Reassessment due".

Rev 1.29: `N` opens the drawer while focus is in the detail pane, not in a field, no dialog is open and a new version is available; the shortcuts dialog is not built (the Help menu holds "About eRev Cloud" alone), so the key is listed nowhere yet. The copy keys are `contracts.estimates.*` as §8.8 names them, without `.lossTest.none` and `.lossTest.loss`. Rev 1.51 (item EST-DISCARD-1): `.banner.discard` "Discard draft"; `.discard.title` "Discard this draft version?"; `.discard.description` "The version is voided. It keeps its number and can no longer be edited or submitted."; `.version.discarded` "Version {version} was discarded.".

### 8.9 Sample world

| Element | Content (asserted where cited) | Source |
|---|---|---|
| K-06 `NS-SO-DE-5002` `REBATE-DR-01` | Version 1 approved, most likely amount, outcome "threshold not expected"; new version drawer: method "Most likely amount" read-only with the POL-040 tooltip (J-07.1); version 2 outcome "Threshold expected: all units re-priced to 90.00", effective 30 Sep 2026, rationale "Customer acquired Tessen Werke; forecast 1,450 units in the framework year.", evidence `rebate-forecast-drossel-2026-09.pdf`; preview transaction price change (5,750.00), catch-up (750.00), revenue Sep 2026 50,000.00 → 44,250.00, refund liability 0.00 → 5,750.00, contract liability 0.00 → 0.00 (J-07.2) | WLD-X-16 |
| K-03 `PRJ-CB-2026-01` `EAC` | Version 1 700,000.00; version 2 820,000.00 (linked to `CR-CASTELLAN-2026-09`); version 3 850,000.00 effective 30 Sep 2026, rationale "Steel price escalation (supplier notice 24 Sep 2026)", evidence `eac-review-castellan-2026-09.xlsx`, classification Change in estimate; preview progress 61.2% → 59.1%, catch-up (29,169.29), "No anticipated loss: estimated costs 850,000.00 are below the transaction price 1,350,000.00." (J-10.3) | WLD-X-12 |
| K-03 `BONUS-CB-01` | Version 1 constrained 0.00; version 2 200,000.00, most likely amount | WLD-K-03, J-06 |
| K-05 `NS-SO-DE-5001` return rate | Version 1: expected returns 3; carrying cost per unit 60.00; recovery cost per unit 0.00 | WLD-K-05 |
| K-07 exercise likelihood | Rate 80.00% | WLD-K-07 |
| K-10 `JP-LIC-0001` `ROY-KM-01` | New version: usage period 01 Jul 2026 – 30 Sep 2026; estimated royalties 25,000,000 (JPY, no decimals); rationale citing estimated licensee revenue 125,000,000; evidence `k10-royalty-estimate-2026-09.pdf`; preview revenue Sep 2026 5,000,000 (J-11.5) | WLD-X-21 |
| `BG-AVM-0024` `VC-BG-017` | Master row chip "Reassessment due"; banner IMP-72 copy for 30 Sep 2026 | WLD-B-06 |

Rev 1.29: the demo seed holds no estimate (`domain/demo/avenmoor/contracts.py`: "estimate versions … are not seeded"), and K-03 is a draft there. The `screens` rows add the `EAC` element of K-03 and its version 1 (700,000.00, effective 01 Feb 2026) through the two drawers and assert that; the rest of this world is owed to the seed.

### 8.10 Test hooks, light and dark, accessibility

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Master | `getByRole("listbox", {name: "Estimated elements"})` | `SF-03-grid-estimates` |
| Row | `getByRole("option", {name: /^REBATE-DR-01/})` | `SF-03-row-rebate-dr-01` |
| Method chip | `getByText("Most likely amount")` with its tooltip | `SF-03-chip-method` |
| Version drawer | `getByRole("dialog", {name: /^New estimate version/})` | `SF-03-drawer-estimate-version` |
| Preview | `getByRole("region", {name: "Preview"})` | `SF-03-pane-estimate-preview` |
| Versions grid | `getByRole("table", {name: "Versions"})` | `SF-03-grid-estimate-versions` |

Light and dark: the locked method chip is an outline chip with `--fg-2` text and icon; warning chip "Reassessment due" uses the warning tone tokens. Accessibility: grouped master options carry `aria-describedby` naming their kind group; the method lock is conveyed in the chip's accessible name "Method most likely amount, locked"; the scenarios table shows no client-computed total; a probability total other than 100% is reported by the server on save and shown in the error summary (DS-CMP-21).

Rev 1.29, further hooks: the detail pane `SF-03-pane-estimate`; the strip `SF-03-kpi-strip-estimate` with cells `SF-03-kpi-estimate-<member>`; the banner slot `SF-03-banner-estimate`; the details of a version `SF-03-estimate-version`, with the catch-up of its stored preview `SF-03-estimate-version-catch-up`; a row of the versions table `SF-03-row-estimate-version-<n>`; the comparison `SF-03-diff-estimate`; the element drawer `SF-03-drawer-estimate-element`; the scenarios grid `SF-03-grid-estimate-scenarios`; the catch-up of the preview `SF-03-estimate-preview-catch-up`; the dialogs `SF-03-dialog-attest` and `SF-03-dialog-withdraw-estimate`.

## 9. Customers and related-party groups

### 9.1 Summary

| Field | Value |
|---|---|
| Screen ids and routes | SF-15:customers `/settings/customers` (RT-79); SF-15:customer `/settings/customers/:customerId` (RT-80); SF-15:related-party-groups `/settings/related-party-groups` (RT-81) |
| Roles and permissions | Read `contract.read`. "New customer", "Edit customer", "New group", "Edit group" `masterdata.maintain` (ACT-24); "Import customers" `import.upload` |
| Purpose | Customer master with external ids per source system and related-party groups used by combination detection and disclosure (PRD SF-15) |
| REQ | REQ-REF-010, REQ-REF-011, REQ-CON-010 |
| Journeys | none asserts these screens directly; WLD-K-11 combination suggestion context (J-04, J-14-ALT) and J-18.6 customer names; captured by `screens.spec.ts` |

### 9.2 Wireframes

The list pages (SF-15:customers, SF-15:related-party-groups) use the DataGrid page frame of §3.2 inside the Settings frame (breadcrumb, group tabs "Customers · Related-party groups · Products"); only the columns of §9.4 differ. Customer detail, 1440 px:

<!-- WF:customer-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Settings > Customers                                                                             |
| Work              |  Customers    Related-party groups    Products                                                   |
|    Home           |  =========                                                                                       |
|    Contracts      | Hollenbrand Klinikbedarf GmbH (Demo)   C-DE-3001 [copy]  (Active)                  [*Edit custome|
|    Schedules      | Related-party group HOLLENBRAND . Country DE . Segment .. . Credit grade .. . Source NetSuite    |
|    Close          | +- Contracts (1) -------------------------------------------------------------------------------+|
|    Journals       | | Contract       | Status   | Entity | Inception   | Cur | Transaction price | Recognized to date|
|    Reports        | | NS-SO-DE-5001  | (Active) | AVM-DE | 03 Sep 2026 | EUR |         10,000.00 |           9,700.00|
| ----------------  | +-----------------------------------------------------------------------------------------------+|
| Govern            | +- Related customers in HOLLENBRAND -------------------------------------------------------------|
|    Approvals    3 | | Hollenbrand Medizintechnik GmbH (Demo)   C-DE-3004   DE   1 contract                           |
|    Policies       | +-----------------------------------------------------------------------------------------------+|
|    Data           |                                                                                                  |
| |* Settings       |                                                                                                  |
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:customer-1440 -->

Customer detail, 1280 px:

<!-- WF:customer-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Settings > Customers                                                                              |
| H  |  Customers    Related-party groups    Products                                                    |
| Ct | Hollenbrand Klinikbedarf GmbH (Demo)  C-DE-3001  (Active)                   [*Edit customer] ..   |
| Sc | Group HOLLENBRAND . DE . Source NetSuite                                                          |
| Cl | +- Contracts (1) --------------------------------------------------------------------------------+|
| Jn | | Contract      | Status   | Entity | Inception   | Cur | Transaction price | Recognized        | |
| Rp | | NS-SO-DE-5001 | (Active) | AVM-DE | 03 Sep 2026 | EUR |         10,000.00 |          9,700.00 | |
| -- | +------------------------------------------------------------------------------------------------+|
| Ap | Related customers follow below at full width                                                      |
| Po |                                                                                                   |
| Da |                                                                                                   |
| *Se|                                                                                                   |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:customer-1280 -->

### 9.3 Regions and components

| Screen | Region | Component | Content |
|---|---|---|---|
| All | Settings header | none | Breadcrumb "Settings / <page>"; group route tabs (DS-CMP-07) "Customers · Related-party groups · Products" |
| SF-15:customers | Page header | none | `h1` "Customers" with count; primary "New customer"; overflow "Import customers" (SF-10:new `?template=customers`) |
| SF-15:customers | Grid | DS-CMP-10 with DS-CMP-13 | §9.4 |
| SF-15:customer | Record header | DS-CMP-06 customer variant (no KPI strip) | `h1` `name`; identifier `code` (mono, copy); chip "Active" or outline "Inactive"; meta row Related-party group (link), Country, Segment, Credit grade, Source, External id; primary "Edit customer" |
| SF-15:customer | Contracts panel | DS-CMP-10 | Columns 1, 3, 4, 5, 6, 7, 8 of §3.5 for `GET /contracts?customer=<id>` |
| SF-15:customer | Related customers panel | static table | Other customers of the same group: Customer (link), Code, Country |
| SF-15:related-party-groups | Grid and drawer | DS-CMP-10, DS-CMP-09 | Groups; selecting a row opens the group drawer with its members |

### 9.4 Data bindings and columns

| Screen | Endpoint | Parameters |
|---|---|---|
| SF-15:customers | `GET /customers` (API-R-22; fields T-REF-19) | `q`, `related_party_group_id`, `source_system`, `external_id`, `is_active` and `sort` (04 API-R-22: `code`, `name`, `updated_at`), `limit=200`, `count=true` |
| SF-15:customer | `GET /customers/{id}`; `PATCH /customers/{id}` with `If-Match: "r<row_version>"`; `GET /contracts?customer=<id>`; `GET /customers?related_party_group_id=<group id>` | none |
| SF-15:related-party-groups | `GET /related-party-groups` (T-REF-18 plus `member_count`, 04 API-R-22); `POST /related-party-groups`; `PATCH /related-party-groups/{id}` | none |

Customers grid (saved-view code `SF-15:customers`):

| # | Header | Field | Format | Alignment | Sort | Filter | Visible |
|---|---|---|---|---|---|---|---|
| 1 | Customer | `name`, link to SF-15:customer | text link, pinned start | start | `name` | quick search "Search customers" (`q`) | yes |
| 2 | Code | `code` | mono | start | `code` | none | yes |
| 3 | Related-party group | group `code` · `name`, link opening the group drawer | text | start | no | Related-party group | yes |
| 4 | Country | `country_code` | mono | start | no | none | yes |
| 5 | Segment | `segment` | text | start | no | none | yes |
| 6 | Credit grade | `credit_grade` | text | start | no | none | no |
| 7 | Source | `source_system` label (§3.5 column 15) | text | start | no | Source | yes |
| 8 | External id | `external_id` | mono | start | no | External id (equals) | yes |
| 9 | Active | `is_active` | DS-FMT-22 | start | no | Active | yes |
| 10 | Updated | `updated_at` | DS-FMT-17 | start | `updated_at` | none | no |

Related-party groups grid: Group (`code`, mono link), Name, Description (truncated), Members (`member_count`, DS-FMT-21, end), Updated (DS-FMT-17, hidden).

### 9.5 Forms

"New customer" and "Edit customer" drawer (standard): Code (required; read-only after the first contract references the customer [J: codes appear in exports]); Name (required); Related-party group (select, optional; a customer belongs to at most one group, REQ-REF-011); Parent customer (combobox, optional); Credit grade; Segment; Country (select of ISO 3166-1 alpha-2 codes with names); Active (checkbox). Help text under Name: "Customer records hold business identity only. Do not enter personal contact details." (04 T-REF-19). Customers created by an integration or template show Source and External id read-only. Primary "Save customer". Duplicate code: server `validation-failed` mapped to the Code field with the message "Customer code <code> is already used."

"New group" and "Edit group" drawer: Code (required), Name (required), Description; members list (read-only, links) with the note "Add a customer to this group from the customer's page." Primary "Save group".

### 9.6 States

| Screen | Empty | Other |
|---|---|---|
| SF-15:customers | Title "No customers yet"; description "Customers arrive with contracts from imports and integrations, or you can add one."; primary "New customer"; secondary "Import customers" | No results SCR-ST-04 "No customers match these filters"; error SCR-ST-05 "Could not load customers" |
| SF-15:customer | Contracts panel: "No contracts for this customer yet." | Not found SCR-ST-07 "Customer not found" |
| SF-15:related-party-groups | Title "No related-party groups"; description "Group customers under common control so combination suggestions and disclosures can find them."; primary "New group" | error SCR-ST-05 "Could not load related-party groups" |

### 9.7 Keyboard and copy

Keyboard: DS-CMP-10; `/` focuses quick search. Copy keys: `settings.customers.title` "Customers"; `.new` "New customer"; `.edit` "Edit customer"; `.search` "Search customers"; `.help.identityOnly` "Customer records hold business identity only. Do not enter personal contact details."; `settings.relatedParty.title` "Related-party groups"; `.new` "New group".

### 9.8 Sample world

| WLD | Customer | Country | External id (source) | Group | Contracts shown on the detail page |
|---|---|---|---|---|---|
| C-01 | Pellworth Logistics Inc. (Demo) | US | `001DEMO0001` (Salesforce) | none | `SF-ORD-10001`, `SF-ORD-10388` |
| C-02 | Marrowby Health Partners LLC (Demo) | US | `001DEMO0002` (Salesforce) | none | `SF-ORD-10002` |
| C-03 | Castellan Build Group Inc. (Demo) | US | `CB-2026` (project system) | none | `PRJ-CB-2026-01` |
| C-04 | Saltmarsh Freight Ltd (Demo) | GB | `001DEMO0104` (Salesforce) | none | `SF-ORD-UK-2001` |
| C-05 | Hollenbrand Klinikbedarf GmbH (Demo) | DE | `C-DE-3001` (NetSuite) | `HOLLENBRAND` | `NS-SO-DE-5001` |
| C-06 | Drossel Fahrzeugtechnik GmbH (Demo) | DE | `C-DE-3002` (NetSuite) | none | `NS-SO-DE-5002` |
| C-07 | Fenwright Logistik AG (Demo) | DE | `C-DE-3003` (NetSuite) | none | `NS-SO-DE-5003` |
| C-08 | Ulvane Telematics Inc. (Demo) | US | `001DEMO0005` (Salesforce) | none | `SF-ORD-10003` |
| C-09 | Orrin Vale Architects LLP (Demo) | US | `001DEMO0006` (Salesforce) | none | `SF-ORD-10417` |
| C-10 | Kumotori Media KK (Demo) | JP | `C-JP-0001` (NetSuite) | none | `JP-LIC-0001` |
| C-11 | Hollenbrand Medizintechnik GmbH (Demo) | DE | `C-DE-3004` (NetSuite) | `HOLLENBRAND` | `NS-SO-DE-5004` |
| C-12 | Kinsley Marrow Foods Inc. (Demo) | US | `001DEMO0417` (Salesforce) | none | `SF-ORD-20417` after J-03.1 |

Customer codes are seed-generated and not asserted. The related-party groups page lists `HOLLENBRAND` with 2 members. In WLD-T-20, legacy template imports create customers `LEGACY-Contract 1` and `LEGACY-Contract 2` (04 T-REF-19 legacy note).

### 9.9 Test hooks, light and dark, accessibility

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Customers grid | `getByRole("grid", {name: "Customers"})` | `SF-15-grid-customers` |
| Customer row | `getByRole("row", {name: /Hollenbrand Klinikbedarf/})` | `SF-15-row-c-de-3001` (external id key) |
| Customer drawer | `getByRole("dialog", {name: /customer$/})` | `SF-15-drawer-customer` |
| Groups grid | `getByRole("grid", {name: "Related-party groups"})` | `SF-15-grid-related-party-groups` |

Light and dark: standard DataGrid and drawer tokens; the outline "Inactive" chip uses `--border-default`. Accessibility: settings group tabs are `nav aria-label="Reference data sections"`; the customer page `h1` is the customer name; form help is linked with `aria-describedby`.

## 10. Products and bundles

### 10.1 Summary

| Field | Value |
|---|---|
| Screen ids and routes | SF-15:products `/settings/products` (RT-82); SF-15:product `/settings/products/:productId` (RT-83); panel tab `pane=attributes|bundle|ssp|policy-values` |
| Roles and permissions | Read `contract.read`. "New product", "Edit product", bundle components `masterdata.maintain` (ACT-24); "Propose principal or agent change" `masterdata.maintain` with approval `PRINCIPAL_AGENT_CHANGE` approved by `config.approve`; "Import products" `import.upload` |
| Purpose | Product master: default obligation template, revenue category, disaggregation attributes, principal or agent conclusion, bundles, and the SSP entries that price the product (PRD SF-15) |
| REQ | REQ-REF-012, REQ-REF-013, REQ-REF-014, REQ-POB-009 |
| Journeys | J-23 (Quayside catalogue import creates `QUAY-PLAT`, `QUAY-ADDON`, `QUAY-SVC`; SCREENS_B journey context); captured by `screens.spec.ts` |

### 10.2 Wireframes

SF-15:products uses the DataGrid page frame of §3.2. Product detail, 1440 px:

<!-- WF:product-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Settings > Products                                                                              |
| Work              |  Customers    Related-party groups    Products                                                   |
|    Home           |                                       ========                                                   |
|    Contracts      | AVM-PLAT-100 [copy]  Platform, 100 seats, 12 months  (Active)                      [*Edit product|
|    Schedules      |  Attributes    Bundle components    SSP    Policy values                                         |
|    Close          |  ==========                                                                                      |
|    Journals       | Product family ..              Revenue category SUBSCRIPTION     Unit EA                         |
|    Reports        | Default obligation template TPL-SUB-DAILY v1 (link)              Distinct by default Distinct    |
| ----------------  | Principal or agent Principal   [Propose principal or agent change]                               |
| Govern            | Disaggregation attributes  (none required by the tenant)                                         |
|    Approvals    3 | +- SSP entries --------------------------------------------------------------------------------+ |
|    Policies       | | Book     | Version  | Effective               | Method     | Low        | Mid        | High   ||
|    Data           | | US-LIST  | 2026-H1  | 01 Jan 2026 - 30 Sep 2026| Observable | 85,000.00  | 100,000.00 | 115,..||
|                   | | US-LIST  | 2026-H2  | 01 Oct 2026 -           | Observable | 95,200.00  | 112,000.00 | 128,..| |
| |* Settings       | +----------------------------------------------------------------------------------------------+ |
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:product-1440 -->

Product detail, 1280 px:

<!-- WF:product-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Settings > Products                                                                               |
| H  |  Customers    Related-party groups    Products                                                    |
| Ct | AVM-PLAT-100  Platform, 100 seats, 12 months  (Active)                         [*Edit product] .. |
| Sc |  Attributes    Bundle components    SSP    Policy values                                          |
| Cl | Revenue category SUBSCRIPTION . Template TPL-SUB-DAILY v1 . Distinct                              |
| Jn | Principal or agent Principal  [Propose principal or agent change]                                 |
| Rp | SSP entries: US-LIST 2026-H1 85,000.00 / 100,000.00 / 115,000.00 ...                              |
| -- |                                                                                                   |
| Ap |                                                                                                   |
| Po |                                                                                                   |
| Da |                                                                                                   |
| *Se|                                                                                                   |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:product-1280 -->

### 10.3 Regions, bindings and columns

| Screen | Region | Component | Binding |
|---|---|---|---|
| SF-15:products | Grid | DS-CMP-10, DS-CMP-13 | `GET /products` (API-R-23; T-REF-20 columns) with `q`, `product_family`, `is_active`, `sort` (04 API-R-23), `limit=200`, `count=true` |
| SF-15:product | Record header | DS-CMP-06 (no KPI strip) | `GET /products/{id}` (ETag `"r<row_version>"`) |
| SF-15:product | Attributes panel | definition list; "Edit product" drawer | `PATCH /products/{id}` |
| SF-15:product | Bundle components panel | DS-CMP-10 inline-editable | `GET /products/{id}/bundle-components`; `PUT /products/{id}/bundle-components` |
| SF-15:product | SSP panel | static table | `GET /ssp-books`, then `GET /ssp-book-versions/{id}/entries?product=<code>` for the current approved and draft versions of each book |
| SF-15:product | Policy values panel | static table | `product.policy_values` and the default template version's `policy_values` |
| SF-15:product | Principal or agent drawer | DS-CMP-09 | `POST /products/{id}/propose-principal-agent-change` |

Products grid (saved-view code `SF-15:products`):

| # | Header | Field | Format | Alignment | Sort | Filter | Visible |
|---|---|---|---|---|---|---|---|
| 1 | Product | `code`, link to SF-15:product | mono link, pinned start | start | `code` | quick search "Search products" | yes |
| 2 | Name | `name` | text | start | `name` | none | yes |
| 3 | SKU number | `sku_number` | mono | start | no | none | no |
| 4 | Product family | `product_family` | text | start | no | Product family | yes |
| 5 | Revenue category | `revenue_category` | mono | start | no | none | yes |
| 6 | Default template | template code of `default_pob_template_id`, link to SF-13:template-version (current) | mono link | start | no | none | yes |
| 7 | Principal or agent | `principal_agent`: `PRINCIPAL` "Principal", `AGENT` "Agent", `NOT_ASSESSED` "Not assessed" | text | start | no | none | yes |
| 8 | Distinct by default | `distinctness_default`: `distinct` "Distinct", `nondistinct` "Not distinct", `series` "Series" | text | start | no | none | yes |
| 9 | Unit | `unit_of_measure` | mono | start | no | none | no |
| 10 | Bundle | `is_bundle` | DS-FMT-22 | start | no | none | yes |
| 11 | Active | `is_active` | DS-FMT-22 | start | no | Active | yes |

### 10.4 Panels and forms

- **Attributes** definition list: Code; SKU number; Name; Product family; Revenue category; Default obligation template (link); Distinct by default; Unit of measure; Bundle; Disaggregation attributes (table Attribute, Value; attributes named by the registry parameter `disclosure.mandatory_disaggregation_attributes` are marked "Required"); Principal or agent with the button "Propose principal or agent change"; Active.
- **Edit product** drawer: Code (read-only after the first contract line references it [J]; rev 1.31: 04 T-REF-20 DB-05 fixes the code once a contract line, an SSP entry or an account mapping rule references the product, and API-S-Product names none of them, so until it carries that fact the field stays editable with the help "The code is fixed once a contract line, an SSP entry or an account mapping rule references the product." and the server's refusal shows at the field; rev 1.44: API-S-Product carries the fact as `code_frozen` (04 API-R-23 rev 1.223, the predicate of DB-05), so the field is read-only while `code_frozen` is true and editable while it is false, with that help in both states; the server's refusal still shows at the field for a code that froze after the product was read); SKU number; Name (required); Product family; Revenue category (combobox of categories used by the published account mapping, free entry allowed); Default obligation template (combobox of templates with a published version); Distinct by default (radio); Unit of measure; Bundle (checkbox, editable while no contract references the bundle); Disaggregation attributes (key and value rows); Active. When a required disaggregation attribute is missing, a warning banner in the drawer reads "This product cannot be used on contracts until <attribute labels> are set." (REQ-REF-012). Primary "Save product". A refused save (rev 1.35): each message of the refusal shows at the control whose member it names (DS-CMP-21) and leaves it when that value is edited — at the text fields and the template select, at Bundle (`is_bundle`: "Remove the bundle components before clearing Bundle.") and at the Value of the Disaggregation attributes row whose key the pointer names (`disaggregation.<key>`: "Enter a value for this disaggregation attribute."); a message on the attributes that names no row of the drawer stands under their heading. A message on a member the drawer has no control for is listed in the DS-CMP-29 negative banner at the top of the drawer, under the problem's title, each sentence once; the banner does not repeat a sentence a control shows, and a banner left with its title alone leaves once every refused control has been edited (§11.0 "Refused command"; SCREENS_B §9.15). The warning of a missing required attribute stays below that banner.
- **Propose principal or agent change** drawer: Conclusion (radio "Principal", "Agent", "Not assessed"); Control indicators (ASC 606-10-55-39A): "Primarily responsible for fulfilling the promise", "Has inventory risk", "Has discretion in establishing the price", each Yes / No with a note; Judgement record (topic `PRINCIPAL_AGENT`, created inline, required); Rationale. Primary "Submit for approval". Info line: "The change applies prospectively after approval."
- **Bundle components** panel (rendered when `is_bundle`): DataGrid "Bundle components" with Component (product combobox), Quantity per bundle (DS-FMT-11), Split basis ("Relative SSP" `relative_ssp`, "Fixed percentage" `fixed_percentage`), Split percentage (DS-FMT-09 two decimals; required for fixed percentage), Sequence, Valid from (DS-FMT-16), Valid to. Inline-editable while no contract references the bundle; afterwards read-only with the note "Components change by adding rows with a later valid-from date." and the button "Add component row". Footer "Save components". Server message for split ratios not totalling 100%: rendered in a banner above the grid.
- **SSP** panel: static table "SSP entries": Book (code, link), Version (label), Status (chip), Effective (DS-FMT-20), Method, Low, Mid, High, Point (DS-FMT-13), Currency; empty "No SSP entry prices this product. Contracts with it cannot be activated." with link "Open SSP books".
- **Policy values** panel: static table Key (mono), Value, Level ("Product", "Template <code v<n>>"); note "Template values take precedence over product values (POLICIES §0.5)."

### 10.5 States, keyboard and copy

States: products empty title "No products yet", description "Products arrive from template imports and integrations, or you can add one.", primary "New product", secondary "Import products"; no results "No products match these filters"; not found "Product not found"; pending principal or agent change: info banner "A principal or agent change is waiting for approval." with "View request". Keyboard: DS-CMP-10, panel tabs APG Tabs. Copy keys: `settings.products.title` "Products"; `.new` "New product"; `.edit` "Edit product"; `.proposePrincipalAgent` "Propose principal or agent change"; `.bundle.title` "Bundle components"; `.ssp.title` "SSP entries"; `.policyValues.title` "Policy values".

### 10.6 Sample world

| Product | Name | Revenue category | Default template | SSP (book version, method, low / mid / high or point) |
|---|---|---|---|---|
| AVM-PLAT-ENT | Platform, enterprise tier, 12 months | SUBSCRIPTION | TPL-SUB-DAILY | US-LIST 2026-H1, Observable, point 132,000.00 USD |
| AVM-SEAT-MO | Platform seat, per seat per month | SUBSCRIPTION | TPL-SUB-DAILY | US-LIST 2026-H1, Observable, 90.00 / 100.00 / 110.00 USD |
| AVM-PLAT-100 | Platform, 100 seats, 12 months | SUBSCRIPTION | TPL-SUB-DAILY | US-LIST 2026-H1, Observable, 85,000.00 / 100,000.00 / 115,000.00 USD; after J-02 US-LIST 2026-H2, 95,200.00 / 112,000.00 / 128,800.00 USD |
| AVM-IMPL-STD | Implementation, standard | SERVICES | TPL-SVC-PCT | US-LIST 2026-H1, Cost plus margin, point 18,000.00 USD |
| AVM-IMPL-PLUS | Implementation, extended scope | SERVICES | TPL-SVC-HOURS | US-LIST 2026-H1, Cost plus margin, 18,000.00 / 20,000.00 / 22,000.00 USD |
| AVM-API-CALL | API calls (usage) | SERVICES | TPL-USAGE | US-LIST 2026-H1, Observable, point 0.10 USD |
| AVM-ENG-BUILD | Engineered facility build | SERVICES | TPL-ENG-C2C | US-LIST 2026-H1, Cost plus margin, percent of list, point 100% |
| AVM-KIT | Sensor kit | PRODUCT | TPL-PROD-PIT | DE-LIST 2026, Observable, point 100.00 EUR |
| AVM-PART | Automotive sensor part | PRODUCT | TPL-PROD-PIT | DE-LIST 2026, Observable, point 100.00 EUR |
| AVM-GW | Sensor gateway unit | PRODUCT | TPL-PROD-UNITS | DE-LIST 2026, Observable, 405.00 / 450.00 / 495.00 EUR |
| AVM-FLEET | Gateway fleet package | PRODUCT | TPL-PROD-PIT | DE-LIST 2026, Observable, point 100,000.00 EUR |
| AVM-SUP-12 | Platform support, 12 months | SERVICES | TPL-SUB-DAILY | DE-LIST 2026, Cost plus margin, 19,000.00 / 20,000.00 / 21,000.00 EUR |
| AVM-EXP-CREDIT | Expansion credit (customer option) | MATERIAL_RIGHT | TPL-OPTION | none (SSP from the option record; the SSP panel empty text reads "SSP comes from the option record (discount × likelihood).") |
| AVM-PLAT-UK | Platform, enterprise tier, 12 months (UK) | SUBSCRIPTION | TPL-SUB-DAILY | UK-LIST 2026, Observable, point 60,000.00 GBP |
| AVM-IMPL-UK | Implementation, UK standard | SERVICES | TPL-SVC-PCT | UK-LIST 2026, Cost plus margin, point 10,000.00 GBP |
| AVM-LIB-LIC | Film library licence | LICENCE | TPL-LIC-FUNC | JP-LIST FY2027, Observable, point 50,000,000 JPY |
| AVM-ROYALTY | Royalty on licensee streaming revenue | ROYALTY | none | none |

### 10.7 Test hooks, light and dark, accessibility

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Products grid | `getByRole("grid", {name: "Products"})` | `SF-15-grid-products` |
| Product row | `getByRole("row", {name: /AVM-PLAT-100/})` | `SF-15-row-avm-plat-100` |
| Panel tabs | `getByRole("tablist", {name: "Product sections"})` | none |
| SSP entries | `getByRole("table", {name: "SSP entries"})` | `SF-15-grid-product-ssp` |
| Bundle grid | `getByRole("grid", {name: "Bundle components"})` | `SF-15-grid-bundle-components` |

Light and dark: standard tokens; mandatory disaggregation attributes carry the neutral chip "Required" (DS-CMP-19), never colour alone. Accessibility: panel tabs APG Tabs; the drawer's principal or agent indicators are `fieldset` groups with legends.

## 11. SF-13 Policies

### 11.0 Frame

Every Policies screen renders `h1` "Policies" on list pages (the record title on version pages, with breadcrumb "Policies / <tab label> / <code>"), the route tabs of SCR-IA-02, and the context pill with all segments disabled (§1.3). Version pages share one lifecycle pattern:

| Element | Component | Rule |
|---|---|---|
| Lifecycle stepper | DS-CMP-18 stepper anatomy, non-interactive (OQ-S-05) | Rule sets, templates, account mappings and accounting policies: "Draft · Tested · Approval · Published". SSP book versions: "Draft · Approval · Approved". Captions: "Edited <date>"; "<passed> of <total> tests passed"; "Pending approval" or "Approved by <name>"; "Effective <date>" |
| Status chip | DS-CMP-19 (§0.8) | E-12 literal of the version |
| Header commands | DS-CMP-20 | `DRAFT`: primary "Run tests" (secondary "Run lint" for rule sets); `TESTED`: primary "Submit for approval", secondary "Run tests"; `SUBMITTED`: secondary "Withdraw" (author); `PUBLISHED`, `APPROVED` (SSP), `SUPERSEDED`, `REJECTED`, `WITHDRAWN`: primary "New draft version" (copies this version). Editing a `TESTED` version returns it to `DRAFT` (API-C-13). Rev 1.56 (item POLICY-WITHDRAW-ROUTES-1): an accounting policy version (§11.3) is not copied — its pages render no "New draft version" in any status (04 T-PLT-32: a copy would restate a whole value set on whatever is published now); its "Withdraw" and the way out of a version that came back are stated in §11.3 |
| Author notice | DS-CMP-29 info | When the viewer authored a `SUBMITTED` version: "You authored this version. Another user with configuration approval must approve it." (SoD-5; SoD-2 for SSP) |
| Publication | none | The approval executes publication with the effective date set before submission, so the UI renders no "Publish" button (04 §16.5 publish note; OQ-S-07 resolved by D-76; PRD J-01.5) |
| Effective date (rev 1.8; supervisor ruling R-59) | DS-CMP-21 date field; DS-FMT-16 | 04 SC-V `effective_from` and `effective_to` are instants. Every Policies screen shows the UTC date of the instant (DS-FMT-17 date part; DESIGN_SYSTEM DS-I18N-08): the "Effective <date>" caption and header chip, the Effective from field and the Effective from and Effective to columns of the list grids. A version editor takes a date and sends `effective_from` as 12:00:00Z of that date, so the date picked is the date shown. `effective_to` is the instant the next version takes effect (the interval is half-open, 04 SC-V), so its date is the first day of the successor. Known limitation: an entity beyond UTC+11 reads the next day (item CFG-EFFECTIVE-DATE-1). SSP book versions carry plain dates (`effective_from_date`, `effective_to_date`), which are never converted. **Rev 1.31 (PRD ERR-75; 04 §16.5 "Effective date of a superseding version").** How the date is entered follows how the kind is chosen. *By a contract date* — an obligation template version and a version of an obligation-assignment or SSP-assignment rule set: the help reads "Contracts dated on or after this date use this version." and, for a version that replaces a published version of its scope, continues "It replaces a published one, so choose a date later than today; the approval must come before that date."; whether a date is late enough in every active entity is the server's answer. *At an instant* — a version of every other rule set: the field is optional; an empty field or today's date (the UTC date at the save) is sent as no instant (`effective_from: null`), because 12:00:00Z of today has passed or passes before the approval: the version takes effect at its publication, the save answers "Saved. The version takes effect when it is approved." and the field shows no date; a later date is sent as 12:00:00Z of it; the help reads "Empty or today: the version takes effect when it is approved. A later date: it takes effect at 12:00 UTC on that date, and the approval must come before then." A version read at an instant that holds none reads "Effective on approval" in the stepper and "On approval" in the Meta until it is published, and the UTC date of `published_at` afterwards. An accounting policy version (§11.3) is read at an instant as well, but `POST /policies/{id}/submit` refuses a version without a date, so its field keeps sending 12:00:00Z of the date picked, today included |
| Refused command (rev 1.31) | DS-CMP-29 negative banner; DS-CMP-21 field error | A refused "Run lint", "Run tests", "Submit for approval", "Withdraw" or "New draft version" shows in the header banner the problem's title, its detail unless a field shows the same sentence, and every message of `errors[]` that no field of the screen shows (for example "This version changed after its tests ran. Run the tests again."). A message on `effective_from` — PRD ERR-75 at "Submit for approval" — shows at the Effective from field, which receives focus, and leaves when the date is edited; a banner that then holds its title alone ("Check the highlighted fields") leaves with it. A successful "Run tests" and a saved effective date clear the refusal of an earlier submission. On §11.3 a refused "Save values" is answered the same way, in the banner above the grid. Rev 1.56: a refused "Edit" of §11.3 is answered in the header banner as the lifecycle commands are, and its message on `effective_from` at the field |

List pages (SF-13:revenue, SF-13:control-rules, SF-13:accounting, SF-13:ssp-books, SF-13:account-mapping) use the DataGrid page frame of §3.2; their columns are below.

### 11.1 Revenue policies, control rules and the decision-table editor

| Field | Value |
|---|---|
| Screen ids and routes | SF-13:revenue `/policies/revenue` (RT-59); SF-13:control-rules `/policies/control-rules` (RT-60); SF-13:rule-set-version `/policies/rule-sets/:ruleSetId/versions/:versionId` (RT-62); panel tab `pane=rules|tests|lint|simulation|changes` |
| Roles and permissions | Read `config.read`. Author `config.author` (ACT-22): create rule sets and versions, edit rules and test cases, run lint and tests, submit, withdraw. Approve in SF-12 `config.approve` (ACT-23) |
| Purpose | Versioned decision tables: obligation assignment and SSP assignment (revenue policies); approval routing, auto-approval, holds, combination detection and data-quality monitors (control rules), with publish lint, example tests, simulation and maker-checker (REQ-POL-001 to REQ-POL-003) |
| REQ | REQ-POL-001, REQ-POL-002, REQ-POL-003, REQ-POL-006, REQ-POL-010; REQ-PLT-013, REQ-PLT-016; BR-POL-01 |
| Journeys | none asserts the editor; `APPROVAL_ROUTING` version 1 and `AUTO_APPROVAL` version 1 render the PRD §2.5 routing that J-02 to J-26 exercise |

Wireframes, rule set version editor, 1440 px:

<!-- WF:ruleset-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Policies > Control rules > APPROVAL_ROUTING                                                      |
| Work              |  Revenue policies  Control rules  Accounting policies  SSP books  SSP calculator  Account mapping|
|    Home           |                    =============                                                                 |
|    Contracts      | Approval routing  APPROVAL_ROUTING (Published) (v1) <Approval routing>     [*New draft version] .|
|    Schedules      | (ok) Draft --- (ok) Tested --- (ok) Approval --- (ok) Published                                  |
|    Close          |   Edited ..      12 of 12 tests passed   Approved by Marcus Webb   Effective 01 Jan 2026         |
|    Journals       |  Rules   Test cases   Lint   Simulation   Changes                                                |
|    Reports        |  =====                                                                                           |
| ----------------  | +--------+---------------+----------------------------------------+-------------------------+---+|
| Govern            | |Priority| Rule key      | Conditions                             | Outputs                 |Spc||
|    Approvals    3 | +--------+---------------+----------------------------------------+-------------------------+---+|
| |* Policies       | |      10| CON-ACT-1M    | Subject is CONTRACT_ACTIVATION; TP ..  | 1 contract.approve . 2..|  2||
|    Data           | |      20| CON-ACT-STD   | Subject is CONTRACT_ACTIVATION         | 1 contract.approve      |  1||
|                   | |      10| MOD-CATCHUP   | Subject is MODIFICATION; catch-up ..   | 1 modification.approve  |  2||
|                   | |      10| PERIOD-REOPEN | Subject is PERIOD_REOPEN               | 1 period.reopen_appr. x2|  1||
| Settings          | +--------+---------------+----------------------------------------+-------------------------+---+|
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:ruleset-1440 -->

1280 px:

<!-- WF:ruleset-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Policies > Control rules > APPROVAL_ROUTING                                                       |
| H  |  Revenue policies  Control rules  Accounting policies  SSP books  SSP calculator  Account mapping |
| Ct | Approval routing  (Published) (v1)                                     [*New draft version] ..    |
| Sc | (ok) Draft --- (ok) Tested --- (ok) Approval --- (ok) Published                                   |
| Cl |  Rules   Test cases   Lint   Simulation   Changes                                                 |
| Jn | +--------+---------------+-----------------------------------+---------------------------+---+    |
| Rp | |Priority| Rule key      | Conditions                        | Outputs                   |Spc|    |
| -- | |      10| CON-ACT-1M    | Subject is CONTRACT_ACTIVATION .. | 1 contract.approve . 2 .. |  2|    |
| Ap | |  first column pinned; Conditions and Outputs truncate with tooltips                          |  |
| *Po| +--------+---------------+-----------------------------------+---------------------------+---+    |
| Da |                                                                                                   |
| Se |                                                                                                   |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:ruleset-1280 -->

**Revenue policies page.** Two panels. "Obligation templates" DataGrid (`GET /pob-templates`, T-REF-22 plus `current_version` and `latest_version`, 04 API-S-VersionSummary; saved-view code `SF-13:revenue#templates`): Template (`code`, mono link to the current version, pinned start); Name; Current version (`v<n>`); Latest status (chip); Satisfaction pattern; Recognition method; Convention; Distinctness; Effective from (DS-FMT-17 date part); Updated by. Primary "New template". "Assignment rules" DataGrid (`GET /rule-sets?kind=POB_ASSIGNMENT` and `?kind=SSP_ASSIGNMENT`, 04 API-S-VersionSummary; code `SF-13:revenue#rule-sets`): Rule set (`code`, mono link); Name; Kind label ("Obligation assignment", "SSP assignment"); Current version (`current_version.version_no`); Latest status (`latest_version.status`); Rules (`latest_version.rule_count`); Lint (`latest_version.lint_status`: `PASS` "Valid", `FAIL` "Error", `NOT_APPLICABLE` or null "—"); Effective from (`current_version.effective_from`); Updated by. Secondary "New rule set".

**Control rules page.** One DataGrid with the rule-set columns above for kinds `APPROVAL_ROUTING` "Approval routing", `AUTO_APPROVAL` "Auto-approval", `HOLD` "Holds", `COMBINATION_DETECTION` "Combination detection", `DATA_QUALITY` "Data-quality monitors" (code `SF-13:control-rules`); filter chip "Kind". Primary "New rule set".

"New rule set" drawer: Code, Name, Kind (immutable after creation), Description. Primary "Create rule set" (`POST /rule-sets`, then `POST /rule-sets/{id}/versions`); navigates to the draft version.

**Decision-table editor** (SF-13:rule-set-version):

| Region | Component | Content and binding |
|---|---|---|
| Header | DS-CMP-06 (no KPI strip) | `h1` rule set name; identifier `code`; chips status, `v<version_no>`, outline kind label; commands §11.0 |
| Meta | form while `DRAFT` or `TESTED`; definition list otherwise | Effective from (a date, shown and sent as §11.0 "Effective date" says; rev 1.8; rev 1.31: required before submission for an obligation-assignment or SSP-assignment rule set and optional for every other kind, whose "Submit for approval" needs no date; "Save effective date" without a required date answers "Enter the effective date." at the field); Effective to (a date, read-only, "Set when a later version is published."); Author; Approver; Content SHA-256 (DS-FMT-23). `GET, PATCH /rule-set-versions/{id}` |
| Rules panel | DS-CMP-10 DataGrid, inline-editable draft data | `GET /rule-set-versions/{id}/rules`; add and update `POST /rule-set-versions/{id}/rules` (upsert by `rule_key` while the version is `DRAFT` or `TESTED`, 04 API-R-25); remove `DELETE /rule-set-versions/{id}/rules/{rule_id}` |
| Rule drawer | DS-CMP-09 wide | Conditions builder and outputs by kind (below) |
| Test cases panel | DS-CMP-10 | `GET, POST /rule-set-versions/{id}/test-cases`; "Run tests" `POST /rule-set-versions/{id}/test` (202 job) |
| Lint panel | static list | "Run lint" `POST /rule-set-versions/{id}/lint` → `lint_result` |
| Simulation panel | static tables | `impact_simulation.summary` (04 API-S-SimulationSummary `{contracts_affected, revenue_delta_by_period[], balance_delta[], journal_delta[]}`) and "Download simulation report" (`GET /files/{impact_simulation_file_id}/content`) |
| Changes panel | DS-CMP-16 grid diff | Against the published version: rules Added, Removed, Changed |
| Try a line | DS-CMP-09 drawer | Inputs for the kind's condition fields; `POST /rule-sets/{id}/evaluate` |

Rules grid columns: Priority (integer, end); Rule key (mono, required, unique); Conditions (text summary such as "Product code is AVM-PLAT-100 · Contract currency is USD"; editing opens the rule drawer); Outputs (text summary; drawer); Specificity (server value, end, read-only, `aria-readonly`); Description. Toolbar "Add rule", "Duplicate rule", "Remove rule", "Try a line".

Rule drawer "Rule <rule key>": Conditions rows Field · Operator · Value with "Add condition" and "Remove condition"; fields by kind are `erev_engine.rules.FIELDS[kind]` with labels (for `POB_ASSIGNMENT`: `product.code` "Product code", `product.product_family` "Product family", `bundle_parent.code` "Bundle parent code", `contract.region` "Contract region", `contract.channel` "Contract channel", `customer.segment` "Customer segment", `contract.contract_type` "Contract type", `line.term_band` "Line term band", `contract.currency` "Contract currency", `effective_date` "Effective date"); operators `eq` "is", `in` "is one of", `range` "between", `prefix` "starts with", `gte` "at least" (dates "on or after"), `lte` "at most" (dates "on or before"). Outputs by kind (T-REF-26): `POB_ASSIGNMENT` "Obligation template" (select); `SSP_ASSIGNMENT` "SSP book" (select); `APPROVAL_ROUTING` steps table Name, Permission (select of T-PLT-11 approval permissions), Minimum approvers; `AUTO_APPROVAL` "Approve automatically" (checkbox, fixed checked); `COMBINATION_DETECTION` "Window days", "Match" ("Same customer", "Related party"); `HOLD` "Hold type", "Level" ("Contract", "Obligation"); `DATA_QUALITY` "Severity" ("Error", "Warning"), "Message". Primary "Save rule".

Lint findings copy: overlap error "Rules <rule key a> and <rule key b> have equal specificity (<n>) and priority (<p>). Change a priority or a condition." (REQ-POL-002); empty result "No lint findings." A version with lint errors cannot become `TESTED`, and "Submit for approval" is not rendered.

Test cases grid: Name; Input (mono summary); Expected output (mono summary); Last result (`PASS` chip "Succeeded", `FAIL` chip "Failed"); Last run at (DS-FMT-17). "Add test case" drawer: Name; Input (mono textarea validated as a JSON object); Expected output (mono textarea, JSON). "Run tests" shows a DS-CMP-24 indicator "Running <n> test cases"; completion announces "<passed> of <total> tests passed."

Simulation: `impact_simulation.summary` renders "No contracts affected" when `contracts_affected = 0` (BR-POL-01), otherwise static tables "Revenue change by period" (Period, Entity, Change), "Balance change" (Balance, Entity, Change) and "Journal change" (Account role, Debit, Credit).

"Try a line" results: "Rule <rule key> matched (specificity <n>, priority <p>). Output: <output summary>." or "No rule matched. A line like this goes to the exception queue." (REQ-POL-002).

States: rules empty "No rules yet. Add a rule to route <kind label> items."; tests empty "No test cases. Add at least one example before the version can be tested."; lint not run "Run lint to check for overlapping rules."; error SCR-ST-05; configuration frozen on `PATCH` (ERR-09) shows the banner "This version is no longer a draft, so it is read-only. Create a new draft version to change values."

Sample world (`APPROVAL_ROUTING` version 1, Avenmoor, PRD §2.5): rule rows for `CONTRACT_ACTIVATION` (manually created, AI-assisted, TP ≥ USD 100,000.00 or flagged → 1 step `contract.approve`; TP ≥ USD 1,000,000.00 → 2 steps, the second held by a Controller), `MODIFICATION` (1 step; catch-up ≥ USD 50,000.00 or TP change ≥ USD 250,000.00 → 2 steps), `ESTIMATE_VERSION`, `MANUAL_EVENT`, `JUDGEMENT_RECORD`, `COMBINATION_GROUP`, `SSP_OVERRIDE`, `MANUAL_ADJUSTMENT` (< USD 10,000.00 → 1 step; ≥ → 2 steps with attachment), `IMPORT_COMMIT`, `SSP_BOOK_VERSION` (mid change > 10% → 2 steps), the configuration subjects → `config.approve`, `POLICY_OVERRIDE`, `ATTRIBUTE_CHANGE`, `AI_PROPOSAL_ACCEPTANCE`, `EXCEPTION_WAIVER`, `JOURNAL_RUN`, `PERIOD_LOCK`, `PERIOD_REOPEN` (one step, minimum 2 approvers, at least one Controller), `MIGRATION_PROMOTION`, `CONTRACT_VOID` (1 or 2 steps), access subjects → `access.approve` or `support_grant.approve`. `AUTO_APPROVAL` version 1 rules `AUTO-CON-01` (Salesforce-originated contract, TP < USD 100,000.00, no flags) and `AUTO-IMP-01` (API-client import with matching control totals and zero `ERROR` findings). The seed's rule keys other than `AUTO-CON-01` and `AUTO-IMP-01` are not asserted.

Test hooks: grid "Rules" `SF-13-grid-rules`; drawer "Rule <key>" `SF-13-drawer-rule`; lint list `getByRole("list", {name: "Lint findings"})` `SF-13-pane-lint`; simulation `SF-13-pane-simulation`. Light and dark: specificity column in `--fg-2`; lint error rows use the negative chip only. Accessibility: the conditions builder is a `fieldset` per row with the legend "Condition <n>"; row reordering has "Move up" and "Move down" buttons (DS-CMP-10 drag alternative).

### 11.2 Obligation template version editor

| Field | Value |
|---|---|
| Screen id and route | SF-13:template-version `/policies/templates/:templateId/versions/:versionId` (RT-61); `pane=outputs|policy-values|tests|simulation|changes` |
| Roles and permissions | As §11.1 |
| Purpose | The outputs an obligation receives from its template: distinctness, satisfaction pattern, measure of progress, dates, principal or agent, warranty, licence nature, revenue category, account overrides and product-level policy values (REQ-POL-001) |
| Binding | `GET, PATCH /pob-template-versions/{id}`; `POST /pob-template-versions/{id}/test`, `/submit`, `/publish` (not rendered, §11.0); test cases `GET, POST /config-test-cases?subject_type=pob_template_version&subject_id=<id>` and `PATCH, DELETE /config-test-cases/{id}` (04 API-R-57) |

Wireframes, 1440 px:

<!-- WF:template-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Policies > Revenue policies > TPL-SUB-DAILY                                                      |
| Work              |  Revenue policies  Control rules  Accounting policies  SSP books  SSP calculator  Account mapping|
|    Home           |  ================                                                                                |
|    Contracts      | Subscription, daily ratable   TPL-SUB-DAILY  (Published) (v1)                    [*New draft vers|
|    Schedules      | (ok) Draft --- (ok) Tested --- (ok) Approval --- (ok) Published                                  |
|    Close          |  Outputs   Policy values   Test cases   Simulation   Changes                                     |
|    Journals       |  =======                                                                                         |
|    Reports        | Obligation kind Standard        Distinctness Series (increment: day)                             |
| ----------------  | Satisfaction pattern Over time  Over-time criterion ASC 606-10-25-27(a)                          |
| Govern            | Recognition method Time elapsed Ratable convention Daily                                         |
|    Approvals    3 | Start date rule Line start      End date rule Line end                                           |
| |* Policies       | Principal or agent Principal    Warranty type None     Licence nature Not applicable             |
|    Data           | Revenue category SUBSCRIPTION   Account role overrides (none)                                    |
| Settings          |                                                                                                  |
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:template-1440 -->

1280 px:

<!-- WF:template-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Policies > Revenue policies > TPL-SUB-DAILY                                                       |
| H  |  Revenue policies  Control rules  Accounting policies  SSP books  SSP calculator  Account mapping |
| Ct | Subscription, daily ratable   TPL-SUB-DAILY  (Published) (v1)                    [*New draft vers |
| Sc | (ok) Draft --- (ok) Tested --- (ok) Approval --- (ok) Published                                   |
| Cl |  Outputs   Policy values   Test cases   Simulation   Changes                                      |
| Jn | Obligation kind Standard . Distinctness Series (day) . Over time 25-27(a)                         |
| Rp | Time elapsed . Daily . Line start to line end . Principal                                         |
| -- |                                                                                                   |
| Ap |                                                                                                   |
| *Po|                                                                                                   |
| Da |                                                                                                   |
| Se |                                                                                                   |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:template-1280 -->

**Meta (rev 1.31; item TPL-EFFECTIVE-FROM-UI-1).** Between the lifecycle stepper and the panel tabs the editor shows the Meta of §11.1, region "Version details": Effective from (the form "Effective date" with "Save effective date" while `DRAFT` or `TESTED` for `config.author`, sent as `effective_from` alone with `If-Match`; a definition otherwise), Effective to, Author, Approver, Content SHA-256. The date is required for a version that replaces a published version of its template — `current_version` of the template is another version — and optional for the first version, with the help lines §11.0 "Effective date" gives a kind chosen by a contract date; PRD ERR-75 at "Submit for approval" shows at the field (§11.0 "Refused command"). Before this revision the editor had no such field, and "New draft version" sends only `source_version_id`, so a version that replaces a published one could not be submitted on screen (CFG-BACKDATE-1).

Outputs form (T-REF-23; controls enabled while `DRAFT` or `TESTED`):

| Label | Field | Control and rule |
|---|---|---|
| Obligation kind | `obligation_kind` | select of E-18 labels ("Standard", "VC line", "Material right", "Service warranty", "Custodial", "Licence", "Shipping") |
| Distinctness | `distinctness` | radio "Distinct", "Not distinct", "Series" |
| Series increment | `series_increment_unit` | select "Day", "Month", "Transaction", "Unit"; required for Series, hidden otherwise |
| Satisfaction pattern | `satisfaction_pattern` | radio "Point in time", "Over time" |
| Over-time criterion | `over_time_criterion` | select "ASC 606-10-25-27(a)", "(b)", "(c)"; shown for Over time |
| Recognition method | `recognition_method` | select of E-11 labels; for Point in time only "Point in time", "Units delivered", "Manual" |
| Ratable convention | `ratable_convention` | select "Daily", "Monthly, even", "Mid-month"; required for Time elapsed, hidden otherwise |
| Start date rule | `start_date_rule` | select "Line start", "Booking date", "Control transfer", "First usage", "Later of licence start and availability" |
| End date rule | `end_date_rule` | select "Line end", "Start plus term", "None"; Term months required for "Start plus term" |
| Principal or agent | `principal_agent` | select |
| Warranty type | `warranty_type` | select "Assurance", "Service", "None" |
| Licence nature | `licence_nature` | select "Functional", "Symbolic", "Not applicable" |
| Significant financing assessment required | `sfc_assessment_required` | checkbox |
| Revenue category | `revenue_category` | combobox |
| Legacy stratification | `stratification_label` | text |
| Account role overrides | `account_role_overrides` | table Role (or "Billing clearing · <purpose>"), GL account |
| Excluded from netting attribution | `is_excluded_from_netting_attribution` | checkbox (VC line templates) |

Policy values panel: table Key (combobox of registry parameters whose `allowed_levels` contains `PRODUCT`), Value (control per `value_schema`), Approval code label, Remove. Server errors `POLICY_LEVEL_NOT_ALLOWED` and `POLICY_VALUE_INVALID` render IMP-46 and IMP-47 on the row. Rev 1.81 (register index 309, item PRODUCT-POLICY-VALUE-NOT-READ-1; PRD ERR-103; as built, read in the code): the refusal of a value that no computation reads — `usage.tier_minimum_method` or `upfront_fee.recognition_period` other than the framework's default, any value of `pob.shipping_as_fulfilment` — is shown in the form's banner with its sentence, which names the parameter, and marks no row; the key combobox offers every parameter that lists the product level, these three among them. Test cases, simulation and changes panels as §11.1.

Sample world: `TPL-SUB-DAILY` Series (increment day), Over time, ASC 606-10-25-27(a), Time elapsed, Daily; `TPL-SVC-PCT` Distinct, Over time, Output percent; `TPL-SVC-HOURS` Distinct, Over time, Labour hours; `TPL-USAGE` Series (transaction), Usage; `TPL-ENG-C2C` Over time, ASC 606-10-25-27(b), Cost to cost; `TPL-PROD-PIT` Point in time on delivery, returns model `EXPECTED_RETURNS` as a policy value (POL-051); `TPL-PROD-UNITS` Point in time, Units delivered; `TPL-OPTION` Material right; `TPL-LIC-FUNC` Licence, Functional, Point in time, start rule "Later of licence start and availability". Test hooks: form `getByRole("form", {name: "Template outputs"})` `SF-13-pane-template-outputs`. Accessibility: dependent fields announce their appearance through `aria-describedby` help, not live regions.

### 11.3 Accounting policies

| Field | Value |
|---|---|
| Screen ids and routes | SF-13:accounting `/policies/accounting` (RT-63); SF-13:accounting-version `/policies/accounting/:policyId` (RT-64) |
| Roles and permissions | Read `config.read`; author `config.author` ("New policy version", "Apply legacy-parity preset", edit values, "Run tests and simulation", submit, withdraw, "Edit" of a version that came back); approve in SF-12 `config.approve` |
| Purpose | The tenant, entity and book policy registry versions: POLICIES §1 parameters with framework defaults, legacy-parity values, levels, pinning and approval codes; the legacy-parity preset; simulation before approval (REQ-POL-004 to REQ-POL-007, REQ-POL-011) |
| REQ | REQ-POL-003 to REQ-POL-007, REQ-POL-011; BR-POL-01, BR-POL-02 |
| Journeys | J-01.4 (Maya drafts "Legacy parity", simulation "No contracts affected", `TESTED`, submits); J-01.5 (Marcus approves; `PUBLISHED` effective 01 Jan 2023); J-01-AC-2 |

Wireframes, version editor, 1440 px:

<!-- WF:accounting-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Policies > Accounting policies > Tenant v3                                                       |
| Work              |  Revenue policies  Control rules  Accounting policies  SSP books  SSP calculator  Account mapping|
|    Home           |                                   ===================                                            |
|    Contracts      | Accounting policies . Tenant (Draft) (v3) <Legacy parity>  [Run tests and simulation] [*Submit]  |
|    Schedules      | (2) Draft --- ( ) Tested --- ( ) Approval --- ( ) Published                                      |
|    Close          | Effective from {01 Jan 2023 v}      [Search parameters___] (Changed only)                        |
|    Journals       | +-------+----------------------+----------------------------+-----------+-----------+--------+---|
|    Reports        | | POL   | Key                  | Question                   | Current   | Proposed  | Parity |Pin|
| ----------------  | +-------+----------------------+----------------------------+-----------+-----------+--------+---|
| Govern            | |POL-004| billing.posting      | Who posts invoices ...     | ERP       | {ERP v}   | ERP    | P |
|    Approvals    3 | |POL-005| je.posting_mode      | Does the GL receive full ..| GROSS     | {GROSS v} | GROSS  | P |
| |* Policies       | |POL-007| books.enabled        | Which books run ...        | ASC606    |{ASC606,L.}| ASC606,| P |
|    Data           | |POL-001| rounding.posting_mode| How are posted amounts ... | HALF_UP   | HALF_UP lk| HALF_UP| P |
| Settings          | +-------+----------------------+----------------------------+-----------+-----------+--------+---|
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:accounting-1440 -->

1280 px:

<!-- WF:accounting-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Policies > Accounting policies > Tenant v3                                                        |
| H  |  Revenue policies  Control rules  Accounting policies  SSP books  SSP calculator  Account mapping |
| Ct | Accounting policies . Tenant (Draft) (v3)                   [Run tests and simulation] [*Submit]  |
| Sc | (2) Draft --- ( ) Tested --- ( ) Approval --- ( ) Published                                       |
| Cl | Effective from {01 Jan 2023 v}      [Search parameters___] (Changed only)                         |
| Jn | +-------+----------------------+----------------------------+-----------+-----------+--------+---+|
| Rp | | POL   | Key                  | Question                   | Current   | Proposed  | Parity |Pin||
| -- | |POL-004| billing.posting      | Who posts invoices ...     | ERP       | {ERP v}   | ERP    | P ||
| Ap | |POL-005| je.posting_mode      | Does the GL receive full ..| GROSS     | {GROSS v} | GROSS  | P ||
| *Po| |  Levels, Approval and Source columns scroll inside the grid viewport                        |   |
| Da |                                                                                                   |
| Se |                                                                                                   |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:accounting-1280 -->

List grid (`GET /policies`, API-S-Policy; code `SF-13:accounting`): Category (E-53 label: `ACCOUNTING_POLICY` "Accounting policies", `PRACTICAL_EXPEDIENT` "Practical expedients", `DISCLOSURE_ELECTION` "Disclosure elections", `CLOSE` "Close", `PLATFORM` "Platform", `SECURITY` "Security", `AI` "AI", `INTEGRATION` "Integration"); Scope ("Tenant", "Entity <code>", "Book <label>"); Version; Status; Preset (`DEFAULT` "Framework defaults", `LEGACY_PARITY` "Legacy parity", `INDUSTRY_<cluster>` "Industry template <cluster>"); Effective from (DS-FMT-17 date part); Effective to (DS-FMT-17 date part of the stored boundary: the date on which the next version takes effect, exclusive; rev 1.8); Author; Approver. Primary "New policy version" (drawer: Category, Scope, Entity (for Entity scope), Book (for Book scope), "Start from the current published values" checkbox → `POST /policies`; rev 1.36: ticked, the draft states the published values of the same category and scope; unticked, it starts from the framework defaults — the request sends no values and `basis: "DEFAULTS"`, so the version returns every published value to its default until the author states one (04 §16.5 `basis`: without it a version keeps every published value it does not state)); secondary "Apply legacy-parity preset" (modal: Scope, Entity, Book (default ASC 606); primary "Create draft" → `POST /policies/presets/legacy-parity`). The security, AI and platform categories are edited on their Settings pages (SCREENS_B); this list shows them read-only with a link "Open in Settings".

Version editor regions: header (`h1` "<category label> · <scope label>", chips status, `v<n>`, outline preset label); lifecycle stepper; meta: Effective from (select of the start dates of future `open` periods when any changed parameter has `pin = P`, otherwise a date; both are sent as §11.0 "Effective date" says, rev 1.8; help "Pinned-at-inception values apply to contracts computed after publication; per-period values apply from this period." REQ-POL-007; rev 1.31: a message on `effective_from` from "Save values" or "Submit" shows at this field with focus and leaves when the date is edited, §11.0 "Refused command"; rev 1.36: a version of a settings category — the list opens Close and Integrations versions here — needs no date: its help reads "Without a date the version takes effect when it is approved. Choose a date to start later." and "Submit" is enabled without one, 04 §16.5; rev 1.56: where the field cannot be edited that help is its first sentence alone); FilterBar: quick search "Search parameters", chips "Section" (04 API-S-RegistryParameter `section`: the POLICIES §1.1 to §1.14 titles, or `Platform`) and switch "Changed only" (`diff_against_current` non-empty). Rev 1.56 (the supervisor's word of 2026-10-02 on the lane's measurement): the four controls — Effective from, "Search parameters", "Section" and "Changed only" — stand on one row from 1280 px (the wireframes above draw that row, without "Section"), and the help of Effective from stands under that row at full width, still the description its control names. Inside its 160 px field the sentence wrapped to six lines, and with "Section" and "Changed only" on a second row the block took 236 px: on a draft the grid was left 196 px at 1440 × 900 (three whole rows of 112), 96 px at 1280 × 800 and 16 px at 1280 × 720 (no whole row), on a page that did not scroll. The grid takes the height the other blocks leave of the main region and keeps a floor of eight rows — 400 px: the grid's bar, its header row, eight rows of 36 px and the room of a horizontal scrollbar where one takes room; below the floor the page scrolls, which a draft's page does by 44 px at 1440 × 900 and does not at 1440 × 1200.

Parameter grid (DataGrid over `GET /registry/parameters?category=<category>` joined with `values`, `diff_against_current` and the resolution `GET /policies/resolve?key=<code>&entity&book` for "Current value"):

| # | Header | Field | Format and control | Alignment | Visible |
|---|---|---|---|---|---|
| 1 | POL | `pol_id` | mono, pinned start | start | yes |
| 2 | Key | `code` | mono; rev 1.56: a key longer than the column shortens with its full text as the tooltip, and the "Changed" chip beside it stays whole; every literal of this grid shortens the same way — a current, proposed, default or legacy-parity value, a source, a forced value beside its lock — and no cell cuts one at its edge; the control of an editable proposed value ends a longer literal in an ellipsis and shows it whole among its options | start | yes |
| 3 | Question | `description` | text, truncated with tooltip | start | yes |
| 4 | Current value | resolved value and level ("Tenant", "Framework default") | literal in mono; lists joined by commas | start | yes |
| 5 | Proposed value | `values[code]` | select of `value_schema` literals, number or list editor; forced parameters show LockSimple and "Forced by the framework" read-only; rev 1.36: a key a `DRAFT` or `TESTED` version does not state shows the published value, which the version keeps; a later version holds the whole value set (04 T-PLT-32), so a key it does not hold shows the framework default, whatever the published version holds now — and its "Changed" rows are the codes of `diff_against_current` alone, which for a `PUBLISHED` or `SUPERSEDED` version is the difference it made (04 §16.5); a key the version returns to the default (`diff_against_current[].change = RETURNED_TO_DEFAULT`) shows the framework default, with the caption "Framework default" where the version is read-only; an emptied value returns the key to the default — "Save values" leaves it out of `values` and, where the published version holds it, names it in `unset`; beside a level a value truncates with its full text as the tooltip and the level stays whole | start | yes |
| 6 | ASC 606 default | `default_asc606` | mono | start | yes |
| 7 | IFRS 15 default | `default_ifrs15` | mono | start | no |
| 8 | Legacy parity | `legacy_parity_value` | mono; "n/a" when null | start | yes |
| 9 | Levels | `allowed_levels` ("Tenant", "Entity", "Book", "Product", "Contract", "Obligation") | text | start | no |
| 10 | Pinning | `pin`: `K` "At inception", `P` "Per posting period" | text | start | yes |
| 11 | Approval | `approval_code`: `CFG` "Configuration", `OVR` "Override", `EST` "Estimate", `JDG` "Judgement", `FIX` "Fixed" | text | start | no |
| 12 | Source | `source_ref` | mono | start | no |

"Run tests and simulation" → `POST /policies/{id}/test` with `run_simulation = true` (202 job); results panel: "Example cases: <passed> of <total> passed"; simulation summary "No contracts affected" or tables as §11.1. Row errors `POLICY_LEVEL_NOT_ALLOWED` and `POLICY_VALUE_INVALID` render IMP-46 and IMP-47 on the row and in a banner "Fix <n> parameters to continue."

**Withdraw, and a version that came back (rev 1.56; item POLICY-WITHDRAW-ROUTES-1).** "Withdraw" — rendered on a `SUBMITTED` version for the preparer of its request — calls the policy's own route, `POST /policies/{id}/withdraw` (200 API-S-Policy, `DRAFT`): the request is withdrawn and the version is a draft again in one step (PRD SM-01 "Subject returns to Draft", SM-04), so the page is the editor again; the toast reads "Withdrew <scope> v<n>.". `POST /approvals/{id}/withdraw`, which the editor called before this revision and which the Approvals screens call, ends at `WITHDRAWN`. A `REJECTED` version, and one withdrawn on the Approvals screens, shows a holder of `config.author` the info banner "Version <n> was rejected. Edit it to submit it again." (or "was withdrawn") and the primary "Edit": `PATCH /policies/{id}` with an empty body and `If-Match` — the edit that returns the version to `DRAFT` (E-12; 04 §16.5), holding the statement of its last submit — answered by the toast "<scope> v<n> is a draft again.". The API refuses that edit once another version of the category and scope was published since the submit (PRD ERR-92), and the page knows it from the versions it lists — the `PUBLISHED` version of the scope is not the one `supersedes_version_id` names: in place of "Edit" the banner then reads ERR-92's sentence, "Version <m> was published after this version was submitted. Create a new version: it starts from the published values.", with the link "New policy version", which opens that drawer on the version's category and scope ("Open in Settings" for a category that is edited there). Until the versions are read the page offers neither. If the refusal arrives all the same — a version was published after the page read them — the header banner shows the problem with its sentence whole and once (the refusal carries it as its detail and as its message), the versions are read again, and the banner with the link takes its place with focus on its sentence. A refusal of "Edit" leaves the banner when the version is a draft again, by whoever's edit; "Edit" and "Withdraw" are sent once however often they are pressed, and when either is accepted focus is on the page's heading, the pressed control having left with the status. Where another version of the scope is open — `DRAFT`, `TESTED`, `SUBMITTED` or `APPROVED`, which the page knows from the same list — it offers neither "Edit" nor "New policy version", since the API refuses both (PRD SM-04): the banner reads SM-04's sentence, "Another version is open. Finish it or withdraw it first.", with the link "Open version <m>" to that version's page, whether the basis is still the published version or not. An "Edit" refused SM-04 all the same — the version was opened after the page read the list — is answered as the ERR-92 refusal is: the versions are read again and that banner takes the refusal's place, with focus on its sentence. The drawer says a refused create the same way, and so does the "Apply legacy-parity preset" modal: a message on a member the form has no field for — SM-04's, on `status` — is listed in the form's banner (§11.0 "Refused command"), which before this revision showed the problem's title alone. An "Edit" refused for the effective date — a period-scoped version whose period start has come since its submit; a save validates the date the version holds — shows the message at "Effective from", which becomes the date field with focus, and the next "Edit" sends the date with it: the date chosen in that field, or none where the author emptied it; a text that is no date is not sent, so the refusal stands, and a date typed while the field was not this edit's is never sent. The accepted edit closes the field again. Each version has its own view: what was chosen on one version's page and not saved — proposed values, the date, the filters — is no part of another's, to which the link above and Back lead on the same route. A failed read of the versions is said in place of the grid ("Could not load the policy version"), where the page offered neither exit and a skeleton that did not end. A reader without `config.author` sees the status chip and no banner.

States: list empty (a new tenant) "No policy versions yet. The framework defaults apply until a version is published." with "New policy version"; editor error SCR-ST-05; frozen ERR-09 banner as §11.1 — rev 1.56: on a `SUBMITTED`, `APPROVED`, `PUBLISHED` or `SUPERSEDED` version; a `REJECTED` or `WITHDRAWN` one reads the banners of "a version that came back" above. Rev 1.63 (PRD rev 1.190): on a policy version the banner does not say §11.1's second sentence — no control copies a policy version (rev 1.56). A `SUBMITTED` version reads "This version is read-only while it waits for approval. Withdraw it to change values." to the preparer of its request, who alone is offered "Withdraw", and the first of the two sentences to another author; an `APPROVED`, `PUBLISHED` or `SUPERSEDED` version reads "This version is no longer a draft, so it is read-only. Create a new policy version to change values.".

Sample world: WLD-T-20 (J-01.4): version "Tenant · Accounting policies", preset Legacy parity, `books.enabled` {`ASC606`, `LEGACY`} primary `ASC606`, `billing.posting` `ERP`, `je.posting_mode` `GROSS`, simulation "No contracts affected", status Tested, then Pending approval, then Published effective 01 Jan 2023 with author Maya Chen and approver Marcus Webb (asserted, J-01-AC-2). WLD-T-01 published values: POL-004 `billing.posting` `ERP`; POL-005 `je.posting_mode` `GROSS`; POL-006 `je.summarization` `ENTITY_BOOK_CURRENCY_PERIOD_ACCOUNT_DIMENSIONS`; POL-028 `material_right.exercise` `CONTINUATION`; POL-090 `recognition.time_convention` `DAILY`; POL-052 `returns.reversal_rate` `AVERAGE_CARRYING_RATE`; POL-140 `costs.obtain_expedient` `APPLY`; POL-201 `rpo.time_bands` `[12, 24]`.

Test hooks: grid "Policy parameters" `SF-13-grid-parameters`; results `SF-13-pane-simulation`; preset modal `getByRole("dialog", {name: "Apply legacy-parity preset"})`. Light and dark: forced rows show the lock icon in `--fg-3`; changed rows carry the neutral chip "Changed" (never a colour tint). Accessibility: the Proposed value control's accessible name is "<key>, proposed value"; the lock is named "Forced by the framework".

### 11.4 SSP books and the version editor

| Field | Value |
|---|---|
| Screen ids and routes | SF-13:ssp-books `/policies/ssp-books` (RT-65); SF-13:ssp-book-version `/policies/ssp-books/:bookId/versions/:versionId` (RT-66); `pane=entries|diff|versions|study` |
| Roles and permissions | Read `ssp.read`; "New SSP book", "New draft version", entry edits, study attachment, submit, withdraw `ssp.create` (ACT-19); approve in SF-12 `ssp.approve` (ACT-20; second approver when the mid value changes by more than 10% or methodology changes, REQ-SSP-007) |
| Purpose | Versioned standalone selling prices by product, stratification and dimension with methods, ranges and bands, a study attachment and a diff against the approved version (REQ-SSP-001 to REQ-SSP-008) |
| REQ | REQ-SSP-001 to REQ-SSP-008, REQ-SSP-012, REQ-SSP-013; BR-SSP-01, BR-SSP-02, BR-SSP-05 |
| Journeys | J-02.3 to J-02.5, J-02.8, J-02-AC-2, J-02-AC-5, J-02-ALT-1; J-01.6 (legacy SKU SSP import version `2023-01-01`) |

Wireframes, version editor, 1440 px:

<!-- WF:sspversion-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Policies > SSP books > US-LIST                                                                   |
| Work              |  Revenue policies  Control rules  Accounting policies  SSP books  SSP calculator  Account mapping|
|    Home           |                                                        =========                                 |
|    Contracts      | US list prices  {Version 2026-H2 (Draft) v}  (Draft) (v2)                  [*Submit for approval]|
|    Schedules      | Version label 2026-H2 . Effective from 01 Oct 2026 . Methodology Observable standalone sales ..  |
|    Close          | Study: ssp-study-platform-2026H2.pdf [x]     [x] Methodology change                              |
|    Journals       |  Entries   Diff (1 changed)   Versions                                                           |
|    Reports        |  =======                                                                                         |
| ----------------  | +--------------+------+---+-----------+------------+------------+------------+---------+--------+|
| Govern            | | Product      |Strat.|Cur| Method    | Low        | Mid        | High       | Distinct| Finding||
|    Approvals    3 | +--------------+------+---+-----------+------------+------------+------------+---------+--------+|
| |* Policies       | | AVM-PLAT-ENT |      |USD| Observable|          — | 132,000.00 |          — | Series  |        ||
|    Data           | | AVM-SEAT-MO  |      |USD| Observable|      90.00 |     100.00 |     110.00 | Series  |        ||
|                   | | AVM-PLAT-100 |      |USD| Observable|  95,200.00 | 112,000.00 | 128,800.00 | Series  |(Warn..)||
|                   | | AVM-IMPL-STD |      |USD| Cost+marg.|          — |  18,000.00 |          — | Distinct|        ||
| Settings          | +--------------+------+---+-----------+------------+------------+------------+---------+--------+|
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:sspversion-1440 -->

1280 px:

<!-- WF:sspversion-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Policies > SSP books > US-LIST                                                                    |
| H  |  Revenue policies  Control rules  Accounting policies  SSP books  SSP calculator  Account mapping |
| Ct | US list prices {Version 2026-H2 (Draft) v} (Draft)                         [*Submit for approval] |
| Sc | Effective from 01 Oct 2026 . Methodology Observable standalone sales ..                           |
| Cl |  Entries   Diff (1 changed)   Versions                                                            |
| Jn | +--------------+------+---+-----------+------------+------------+------------+---------+--------+ |
| Rp | | Product      |Strat.|Cur| Method    | Low        | Mid        | High       | Distinct| Finding| |
| -- | | AVM-PLAT-100 |      |USD| Observable|  95,200.00 | 112,000.00 | 128,800.00 | Series  |(Warn..)| |
| Ap | |  Revenue account and Bands columns scroll inside the grid viewport                           |  |
| *Po|                                                                                                   |
| Da |                                                                                                   |
| Se |                                                                                                   |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:sspversion-1280 -->

Books grid (`GET /ssp-books`, API-S-SspBook; code `SF-13:ssp-books`): Book (`code`, mono link); Name; Scope (`entity_code`, `currency`, `channel`, `segment` joined, "All entities" when absent); Resolution (`EFFECTIVE_DATE` "By effective date", `BY_LABEL` "By version label"); Current version (`current_version.legacy_version_label` · `v<version_no>`); Effective from; Effective to; Draft (link "v<n> draft" when `draft_version_id`). Primary "New SSP book" (drawer: Code, Name, Description, Entity, Currency, Channel, Segment, Resolution mode); overflow "Import SKU SSP template" (SCR-LTH-01) and "Import SSP values (CSV v2)".

Version editor:

| Region | Content and binding |
|---|---|
| Header | `h1` book name; version select "Version <label> (<status>)" listing every version (`GET /ssp-books/{id}/versions`); chips status and `v<n>`; commands §11.0 ("Submit for approval" for `DRAFT`) |
| Meta | Version label (`legacy_version_label`); Effective from (date; required for `EFFECTIVE_DATE` books); Effective to (read-only; help "Set when a later version is approved.", BR-SSP-02); Methodology label (required); Methodology change (checkbox; help "A methodology change needs a second approver."); SSP study (attachments with purpose `SSP_STUDY`; at least one before submission). `GET, PATCH /ssp-book-versions/{id}` |
| Entries panel | DataGrid over `GET /ssp-book-versions/{id}/entries`, inline-editable while `DRAFT`; upsert `POST /ssp-book-versions/{id}/entries` (1 to 5,000 per call); remove `DELETE …/entries/{entry_id}` |
| Bands drawer | Band dimension ("None", "Quantity", "Deal size", "Term months"); rows From, To, Point, Low, Mid, High (DS-FMT-13 inputs) |
| Diff panel | `GET /ssp-book-versions/{id}/diff?against=<current approved version id>` as a DS-CMP-16 grid diff; changed cells carry the tooltip "Was <value>"; a Delta column for Mid with the percent change `mid_change_ratio` (04 API-R-26 diff, DS-FMT-31 percent); switch "Show unchanged entries" |
| Versions panel | Static table Version, Label, Status, Effective from, Effective to, Entries, Methodology, Approved at |
| Study panel | Attachments list with SHA-256 and upload |

Entries grid columns (code `SF-13:ssp-book-version#entries`):

| # | Header | Field | Format | Alignment | Editable while Draft | Visible |
|---|---|---|---|---|---|---|
| 1 | Product | `product_code` | mono, pinned start | start | combobox | yes |
| 2 | Stratification | `stratification` | text | start | yes | yes |
| 3 | Currency | `currency` | mono | start | select | yes |
| 4 | Method | `method` label (§5.6); `formula` not offered | text | start | select | yes |
| 5 | Basis | `value_basis` (E-49): "Amount", "Percent of list", "Per increment (series)", "Per booked term (series)". A product the API marks `requires_explicit_ssp_basis` (API-S-Product, derived and read-only: its default POB template version declares `series` distinctness, the predicate the API's 422 applies; the product's own `distinctness_default` is display-only and may differ) has no default: the select shows "Choose a basis" until chosen and "Save entry" refuses with "Choose the value basis of this series product's entry." at the field; other products keep "Amount" (D-97 (3a); rev 1.5; the predicate keyed to the API field in rev 1.6, SSP-ADMISSION-R1) | text | start | select | no |
| 5a | Quantity unit | `quantity_unit` (E-125): "Service units", "Increments". Shown and required only while Basis is "Per increment (series)" ("Choose a unit" until chosen; "Save entry" refuses with "Choose what the line quantity counts for a per-increment entry." at the field); the stored value round-trips through every edit of the entry, inline band edits included. An API refusal at `entries[i].value_basis` or `entries[i].quantity_unit` (422 `validation-failed`; D-97 (3a)) shows at that field, other findings in the drawer banner (D-97 (3); rev 1.5). The import channel (SCR-LTH-01) admits the same fields under lane F-DIN | text | start | select | no |
| 6 | Unit list price | `unit_list_price` | DS-FMT-13 | end | yes (required for Legacy range) | no |
| 7 | Midpoint discount | `midpoint_discount_ratio` | DS-FMT-09 two decimals | end | yes | no |
| 8 | Range (±) | `range_ratio` | DS-FMT-09 two decimals | end | yes | yes |
| 9 | Low | `ranges[0].low_value` | DS-FMT-13; "Derived" in `--fg-3` for Legacy range | end | yes | yes |
| 10 | Mid | `ranges[0].mid_value` | DS-FMT-13 | end | yes | yes |
| 11 | High | `ranges[0].high_value` | DS-FMT-13 | end | yes | yes |
| 12 | Point | `ranges[0].point_value` | DS-FMT-13 | end | yes | yes |
| 13 | Distinctness | `distinctness` label | text | start | select | yes |
| 14 | Revenue account | `revenue_account_code` | mono | start | combobox | no |
| 15 | Bands | count of `ranges` | DS-FMT-21, button opening the bands drawer | end | drawer | yes |
| 16 | Findings | range statistics findings of the entry (IMP-56 to IMP-58 messages) | chip Warning or Error with tooltip | start | no | yes |

Submission: `POST /ssp-book-versions/{id}/submit` with `If-Match`. Missing study refuses with ERR-10, shown as a banner "Attach the SSP study before submitting this version." (J-02-AC-5). `WARNING` range findings are non-blocking: the submit area shows the findings list and the checkbox "I have reviewed these warnings", which is recorded with the command (DS-CMP-21). Overlap refusal ERR-32 renders in a banner. After submission: info banner "Version <label> is waiting for approval." and the routing panel listing the request's `steps` (two steps in J-02.5). After approval every field is read-only; a direct API update returns ERR-09 (J-02.8).

States: books empty "No SSP book versions" description "An SSP book holds standalone selling prices by product and effective date." primary "Create SSP book" (DS-CMP-23 copy); entries empty "No entries yet. Add entries or import SSP values."; error SCR-ST-05.

Sample world: `US-LIST 2026-H1` approved, effective 01 Jan 2026, prepared by Maya Chen and approved by Priya Raman (entries per §10.6 USD rows). J-02.3 draft `2026-H2` effective from 01 Oct 2026 copies every H1 entry with AVM-PLAT-100 mid proposed 113,000.00; J-02.4 edited to mid 112,000.00 with range ± 15.00%, low 95,200.00, high 128,800.00; methodology label "Observable standalone sales, Jan-Aug 2026"; study `ssp-study-platform-2026H2.pdf`; finding on AVM-PLAT-100 "Fewer than 50% of observations fall inside the range (41.0%)." (IMP-57, WARNING, J-02.5; 16 of 39 observations inside 95,200.00 to 128,800.00; rev 1.3); diff "AVM-PLAT-100 low 85,000.00 → 95,200.00; mid 100,000.00 → 112,000.00 (+12.0%); high 115,000.00 → 128,800.00", every other entry "Unchanged" (asserted, J-02-AC-2). After J-02.7 the H1 version shows effective to 30 Sep 2026. WLD-T-20: book `LEGACY-SKU-SSP` version `2023-01-01`, 7 entries, method Legacy range (J-01.6).

Test hooks: grid "SSP entries" `SF-13-grid-ssp-entries`; diff `SF-13-diff`; version select `getByRole("button", {name: /^Version /})`; study upload `getByRole("button", {name: "Upload SSP study"})`. Light and dark: derived cells `--fg-3`; changed diff cells `--warning-border` inset edge (DS-CMP-16). Accessibility: grid edit mode announces "Editing Mid, 112,000.00" (DS-A11Y-11).

### 11.5 Historical SSP calculator

| Field | Value |
|---|---|
| Screen ids and routes | SF-13:ssp-calculator `/policies/ssp-calculator` (RT-67); SF-13:ssp-calculator-run `/policies/ssp-calculator/runs/:runId` (RT-68) |
| Roles and permissions | Read `ssp.read`; run, exclude, create draft `ssp.create` (ACT-19) |
| Purpose | Compute count, median, mean, percentiles, a band around the median and the compliance percentage from a pool of standalone sales, exclude outliers with a reason, and create a draft SSP version (REQ-SSP-009; BR-SSP-04) |
| Journeys | J-02.1 to J-02.3, J-02-AC-1 |

Wireframes, run page, 1440 px:

<!-- WF:calculator-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Policies > SSP calculator > AVM-PLAT-100 standalone sales 2026                                   |
| Work              |  Revenue policies  Control rules  Accounting policies  SSP books  SSP calculator  Account mapping|
|    Home           |                                                                   ==============                 |
|    Contracts      | AVM-PLAT-100 standalone sales 2026 (Succeeded)         [*Create draft version from results] ..   |
|    Schedules      | Book US-LIST . 01 Jan 2026 - 31 Aug 2026 . Band +/- 15% . Pool avm-plat-100-standalone-sales..   |
|    Close          |+-----------------------+-----------------------+-----------------------+-----------------------+ |
|    Journals       || Observations          | Excluded              | Median (USD)          | Inside +/-15%         | |
|    Reports        || 39                    | 1                     | 113,000.00            | 43.6%                 | |
| ----------------  ||                       |                       |                       | 17 of 39              | |
| Govern            |+-----------------------+-----------------------+-----------------------+-----------------------+ |
|    Approvals    3 | +- Distribution ([Chart|Table]) -------------------------------------------------------------+   |
| |* Policies       | |        ##                                                                                   |  |
|    Data           | |     ## ## ##       |median                                                                  |  |
|                   | |  ## ## ## ## ## ## ## ##                                                                    |  |
|                   | |  73K .. .. 96K .. 113K .. 130K .. 151K                                                      |  |
|                   | +--------------------------------------------------------------------------------------------+   |
| Settings          | Observations: Date | Order line | Customer | Quantity | Unit price | In band | Excluded    [Exclu|
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:calculator-1440 -->

1280 px:

<!-- WF:calculator-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Policies > SSP calculator > AVM-PLAT-100 standalone sales 2026                                    |
| H  |  Revenue policies  Control rules  Accounting policies  SSP books  SSP calculator  Account mapping |
| Ct | AVM-PLAT-100 standalone sales 2026 (Succeeded)                [*Create draft version from results]|
| Sc |+-----------------------+-----------------------+-----------------------+-----------------------+  |
| Cl || Observations          | Excluded              | Median (USD)          | Inside +/-15%         |  |
| Jn || 39                    | 1                     | 113,000.00            | 43.6%                 |  |
| Rp |+-----------------------+-----------------------+-----------------------+-----------------------+  |
| -- | Distribution chart panel and Observations grid follow at full width                               |
| Ap |                                                                                                   |
| *Po|                                                                                                   |
| Da |                                                                                                   |
| Se |                                                                                                   |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:calculator-1280 -->

Calculator page: panel "New run" form: Name (required); SSP book (select); Products (multi-select combobox); Source (radio "Uploaded pool of standalone sales" `source_order_lines`, "Committed contract lines" `committed_obligations`); Pool file (upload, CSV, 50 MiB, stored with SHA-256, shown for the uploaded source); Date from and Date to; Band around the median (percent, default 15.00%); Currency (select). Primary "Run calculator" → `POST /ssp-calculator-runs` (202 job `SSP_CALCULATOR`), navigate to the run. Panel "Runs": static table Run (link), Products, Observations, Status (E-67 chip "Queued", "Running", "Succeeded", "Failed"), Created (DS-FMT-17), Draft version (link).

Run page regions:

| Region | Component | Content and binding |
|---|---|---|
| Header | none | `h1` run name; status chip; parameters line (book, date range, band, pool file name); primary "Create draft version from results" |
| Figures per product | DS-CMP-06 strip | Observations; Excluded; Median (<currency>); Inside ± <band> (`compliance_ratio`, DS-FMT-09 one decimal) with secondary "<inside count> of <observation count>" (`inside_count`, 04 §16.14). `GET /ssp-calculator-runs/{id}/results` |
| Statistics | static table | P10, P25, Median, P75, P90, Mean, Proposed low, Proposed mid, Proposed high (DS-FMT-13) |
| Distribution | DS-CMP-14 plain bars | One bar per `histogram` bin (x: bin range with compact ticks DS-FMT-15; y: count); 1 px `--viz-baseline` rules labelled "Median", "− <band>", "+ <band>"; bars in `--viz-1`; Table view From, To, Count |
| Observations | DS-CMP-10 | `GET /ssp-calculator-runs/{id}/observations` (04 API-R-27, §16.14: `{date, source_reference, customer, quantity, unit_price, in_band, exclusion_reason}`): Date (DS-FMT-16), Source (order line external id or contract external id and obligation key, mono), Customer, Quantity (DS-FMT-11), Unit price (DS-FMT-13), In band (DS-FMT-22), Excluded (reason text or "—"). Row action "Exclude observation" |
| Exclude modal | DS-CMP-11 form | Reason (minimum 10 characters); primary "Exclude"; `POST /ssp-calculator-runs/{id}/exclusions` recomputes (job) |
| Create draft modal | DS-CMP-11 form | Version label (required); Effective from (date); book shown read-only; primary "Create draft version" → `POST /ssp-calculator-runs/{id}/create-draft-version` → navigate to SF-13:ssp-book-version |

States: running (figures skeleton and job indicator "Calculating statistics"); failed SCR-ST-12 "The calculator run failed. Nothing was created."; no observations "No standalone sales match these filters. Widen the date range or check the pool file." Sample world (WLD-X-24, asserted): 40 observations of AVM-PLAT-100 from `avm-plat-100-standalone-sales-2026.csv` (prices 73,000.00 to 151,000.00 in steps of 2,000.00); median 112,000.00, 16 inside ±15% (95,200.00 to 128,800.00; 40.0%); after excluding 73,000.00 with reason "Distressed sale to a customer in administration": 39 observations, median 113,000.00, 17 inside ±15% (96,050.00 to 129,950.00; 43.6%) (rev 1.3). "Create draft version from results": label `2026-H2`, effective from 01 Oct 2026 (J-02.3). Test hooks: figures `SF-13-kpi-strip`; chart `getByRole("figure", {name: /^Distribution/})` `SF-13-chart-distribution`; observations grid `SF-13-grid-observations`. Accessibility: the chart summary names the median and band; the Table view is the complete equivalent (DS-A11Y-13).

### 11.6 Account-role mapping

| Field | Value |
|---|---|
| Screen ids and routes | SF-13:account-mapping `/policies/account-mapping` (RT-69); SF-13:account-mapping-version `/policies/account-mapping/:mappingVersionId` (RT-70); `pane=rules|coverage|resolve|simulation|changes` |
| Roles and permissions | Read `config.read`; author `config.author`; approve `config.approve` (`ACCOUNT_MAPPING_VERSION`) |
| Purpose | Versioned, effective-dated mapping of the 33 account roles (D-14a) × entity × optional book, product or revenue category to GL accounts, with `clearing_purpose` on billing clearing rules, publish lint, coverage and resolution testing (REQ-REF-008) |
| REQ | REQ-REF-008, REQ-JE-022, REQ-POL-002, REQ-POL-006 |
| Journeys | J-17.8 (configuration change register lists `AVM-MAP-2026-01`; SCREENS_B); captured by `screens.spec.ts` |

Wireframes, version editor, 1440 px:

<!-- WF:mapping-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Policies > Account mapping > AVM-MAP-2026-01                                                     |
| Work              |  Revenue policies  Control rules  Accounting policies  SSP books  SSP calculator  Account mapping|
|    Home           |                                                                                   ===============|
|    Contracts      | AVM-MAP-2026-01   (Published) (v1)   Effective 01 Jan 2026                       [*New draft vers|
|    Schedules      |  Rules   Coverage   Test resolution   Simulation   Changes                                       |
|    Close          |  =====                                                                                           |
|    Journals       | +----------------------+----------------+--------+------+---------+---------+------------------+-|
|    Reports        | | Account role         | Clearing purp. | Entity | Book | Product | Revenue | GL account       |S|
| ----------------  | +----------------------+----------------+--------+------+---------+---------+------------------+-|
| Govern            | | Revenue              | —              | Any    | Any  | Any     | PRODUCT | 4000 Revenue - pr| |
|    Approvals    3 | | Contract liability   | —              | Any    | Any  | Any     | Any     | 2100 Contract li | |
| |* Policies       | | Billing clearing     | Unapplied cash | Any    | Any  | Any     | Any     | 2090 Subledger cl| |
|    Data           | | Cost of revenue      | —              | Any    | Any  | Any     | Any     | 5000 Cost of rev | |
| Settings          | +----------------------+----------------+--------+------+---------+---------+------------------+-|
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:mapping-1440 -->

1280 px:

<!-- WF:mapping-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Policies > Account mapping > AVM-MAP-2026-01                                                      |
| H  |  Revenue policies  Control rules  Accounting policies  SSP books  SSP calculator  Account mapping |
| Ct | AVM-MAP-2026-01   (Published) (v1)   Effective 01 Jan 2026                       [*New draft versi|
| Sc |  Rules   Coverage   Test resolution   Simulation   Changes                                        |
| Cl | +----------------------+----------------+--------+------+---------+---------+------------------+--|
| Jn | | Account role         | Clearing purp. | Entity | Book | Product | Revenue | GL account       |Sp|
| Rp | | Revenue              | —              | Any    | Any  | Any     | PRODUCT | 4000 Revenue - pr| 2|
| -- | | Billing clearing     | Unapplied cash | Any    | Any  | Any     | Any     | 2090 Subledger cl| 0|
| Ap | |  Default dimensions and Priority columns scroll inside the grid viewport                    |   |
| *Po|                                                                                                   |
| Da |                                                                                                   |
| Se |                                                                                                   |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:mapping-1280 -->

Versions grid (`GET /account-mappings`, T-REF-14 plus `rule_count`, 04 §16.14): Mapping (`name`, link); Version; Status; Effective from (DS-FMT-17 date part); Effective to (DS-FMT-17 date part of the stored boundary: the date on which the next version takes effect, exclusive; rev 1.8); Rules (count); Author; Approver. Primary "New mapping version" (copies the published version).

Rules grid (`GET /account-mappings/{id}/rules`; `POST` to add, `PATCH /account-mappings/{id}` for meta, `DELETE …/rules/{rule_id}`; inline-editable while `DRAFT` or `TESTED`):

| # | Header | Field | Control and format | Alignment | Visible |
|---|---|---|---|---|---|
| 1 | Account role | `account_role` | select of the 31 mappable roles (label, with the literal in mono as secondary text); `RETAINED_EARNINGS` and `FINANCING_OBLIGATION` are not offered (04 `ck_account_mapping_rule__reserved_role`) | start | yes |
| 2 | Clearing purpose | `clearing_purpose` | select of E-109 labels, enabled and required only when the role is `BILLING_CLEARING`; "—" otherwise | start | yes |
| 3 | Entity | `entity_id` | select; "Any entity" | start | yes |
| 4 | Book | `book_code` | select; "Any book" | start | yes |
| 5 | Product | `product_id` | combobox; "Any product" | start | yes |
| 6 | Revenue category | `revenue_category` | combobox; disabled while a product is set | start | yes |
| 7 | GL account | `gl_account_id` | combobox "<code> <name>" | start | yes |
| 8 | Default dimensions | `default_dimensions` | summary, drawer editor | start | no |
| 9 | Priority | `priority` | integer | end | yes |
| 10 | Specificity | `specificity` | server value 0 to 14, read-only | end | yes |

Role labels (catalogue `accountRole.<literal>`): `REVENUE` "Revenue"; `CONTRACT_LIABILITY` "Contract liability"; `CONTRACT_ASSET` "Contract asset"; `UNBILLED_RECEIVABLE` "Unbilled receivable"; `ACCOUNTS_RECEIVABLE` "Accounts receivable"; `BILLING_CLEARING` "Billing clearing"; `REFUND_LIABILITY` "Refund liability"; `RETURN_ASSET` "Return asset"; `DEPOSIT_LIABILITY` "Deposit liability"; `CONSIDERATION_PAYABLE` "Consideration payable to a customer"; `CUSTOMER_INCENTIVE_ASSET` "Customer incentive asset"; `COST_TO_OBTAIN_ASSET` "Capitalised cost to obtain"; `COST_TO_FULFILL_ASSET` "Capitalised cost to fulfil"; `CONTRACT_COST_AMORTIZATION` "Contract cost amortisation"; `CONTRACT_COST_IMPAIRMENT` "Contract cost impairment"; `LOSS_PROVISION` "Loss provision"; `LOSS_EXPENSE` "Loss expense"; `WARRANTY_PROVISION` "Warranty provision"; `WARRANTY_EXPENSE` "Warranty expense"; `INTEREST_INCOME` "Interest income"; `INTEREST_EXPENSE` "Interest expense"; `FX_GAIN_LOSS` "Foreign exchange gain or loss"; `INTERCOMPANY_DUE_TO` "Intercompany due to"; `INTERCOMPANY_DUE_FROM` "Intercompany due from"; `NONCASH_CONSIDERATION_ASSET` "Noncash consideration asset"; `SALES_TAX_PAYABLE` "Sales tax payable"; `PRE_STANDARD_REVENUE` "Pre-standard revenue"; `ROUNDING` "Rounding"; `COST_OF_REVENUE` "Cost of revenue"; `CONTRACT_COST_CLEARING` "Contract cost clearing"; `RECEIVABLE_CONTRA` "Receivable contra"; `RETAINED_EARNINGS` "Retained earnings (reserved)"; `FINANCING_OBLIGATION` "Financing obligation (reserved)". Clearing purposes: `BILLING` "Billing"; `UNAPPLIED_CASH` "Unapplied cash"; `AP_SUPPLIER` "Supplier payables"; `INVENTORY` "Inventory"; `EQUITY` "Equity"; `INVESTMENTS` "Investments".

Validation copy: "Choose a clearing purpose for billing clearing."; "A clearing purpose applies only to billing clearing."; "Set a product or a revenue category, not both."; lint "Rules <n> and <m> resolve the same role, clearing purpose and key with equal specificity and priority." (04 T-REF-15).

Coverage panel: static table "Role coverage", one row per role and, for `BILLING_CLEARING`, one row per clearing purpose (38 rows): Account role, Clearing purpose, Status ("Mapped · <n> rules"; "Not mapped"; "Reserved: no mapping allowed"), computed on the client by counting loaded rules per key (no money involved). "Not mapped" rows carry the note "Postings that need this role fail with ACCOUNT_MAPPING_MISSING." (REQ-JE-022).

Test resolution panel: form Account role, Clearing purpose, Entity, Book, Product, Revenue category, Known at → `GET /account-mappings/resolve`; result "<code> <name> · rule <priority>/<specificity>" or ERR-46 copy "No account is mapped for role <role label> for <entity code>. Publish an account mapping, then retry."

Simulation and changes panels as §11.1 (`POST /account-mappings/{id}/test`).

Sample world (WLD-T-01 `AVM-MAP-2026-01`, effective 01 Jan 2026, approved by Marcus Webb): rules per PRD §2.6 — 1100 Accounts receivable; 1105 Unbilled receivable; 1200 Contract asset; 1210 Customer incentive asset; 1310 Return asset; 1400 Capitalised cost to obtain; 1410 Capitalised cost to fulfil; 1500 Noncash consideration asset; 1800 Intercompany due from; 2020 Contract cost clearing; 2090 Billing clearing with six rules, one per clearing purpose; 2100 Contract liability; 2105 Deposit liability; 2110 Refund liability; 2200 Sales tax payable; 2300 Loss provision; 2400 Consideration payable; 2600 Warranty provision; 2800 Intercompany due to; 4000 Revenue (category PRODUCT); 4010 Revenue (categories SUBSCRIPTION and SERVICES, two rules); 4020 Revenue (LICENCE and ROYALTY); 4030 Revenue (MATERIAL_RIGHT); 5000 Cost of revenue; 5100 Contract cost amortisation; 5200 Warranty expense; 5300 Loss expense; 6000 Contract cost impairment; 7000 Interest income; 7100 Interest expense; 7200 Foreign exchange gain or loss; 7900 Rounding. Coverage shows "Not mapped" for Pre-standard revenue and Receivable contra, and "Reserved: no mapping allowed" for the two reserved roles (PRD §2.6). WLD-T-06 Riverbend maps Receivable contra (D-14a).

Test hooks: grid "Mapping rules" `SF-13-grid-mapping-rules`; coverage `getByRole("table", {name: "Role coverage"})` `SF-13-grid-coverage`; resolve result `SF-13-pane-resolve`. Light and dark: reserved rows in `--fg-3`; not-mapped status uses the warning chip "Not mapped" (warning, WarningCircle). Accessibility: the clearing purpose select is `aria-disabled` with the reason "Only billing clearing has a clearing purpose." when the role is not billing clearing.

## 12. SF-10 Imports

### 12.1 Imports list (SF-10)

| Field | Value |
|---|---|
| Screen id and route | SF-10 `/data/imports` (RT-42) |
| Roles and permissions | Read `contract.read`; "New import" `import.upload` (ACT-15); "Cancel import" the uploader; approval in SF-12 `import.approve` (ACT-16) |
| Purpose | Every uploaded file with its status, counts, approval and commit (PRD SF-10; D-30) |
| REQ | REQ-DAT-001 to REQ-DAT-017, REQ-UX-014, REQ-UX-016 |
| Journeys | J-01.6 to J-01.11, J-01-ALT-1 to J-01-ALT-3, J-04.1, J-04.2, J-04-ALT-1, J-10.1, J-12.1, J-12-ALT-1; WLD-B-04 |

The list uses the DataGrid page frame of §3.2 inside the Data frame (route tabs "Imports · Exceptions · Integrations · Migrations · Templates"). Header: `h1` "Imports" with count; primary "New import"; secondary "Download templates" (SF-10:templates).

Binding: `GET /imports` (API-R-43; API-S-Import list items) with `status` (repeatable), `template_code`, `created_from`, `limit=200`, `count=true`; saved-view code `SF-10`.

| # | Header | Field | Format | Alignment | Sort | Filter | Visible |
|---|---|---|---|---|---|---|---|
| 1 | Import | `file.original_filename`, link to SF-10:detail | text link, pinned start | start | no | quick search "Search imports" | yes |
| 2 | Template | `template.name` (§12.4 names) | text | start | no | Template → `template_code` | yes |
| 3 | Status | `status` | chip (§0.8) | start | no | Status | yes |
| 4 | Rows | `counts.rows` | DS-FMT-21 | end | no | none | yes |
| 5 | Errors | `counts.errors` | DS-FMT-21 | end | no | none | yes |
| 6 | Warnings | `counts.warnings` | DS-FMT-21 | end | no | none | yes |
| 7 | Uploaded by | `created_by` | user | start | no | none | yes |
| 8 | Uploaded at | `created_at` | DS-FMT-17 | start | default descending | Uploaded from → `created_from` | yes |
| 9 | Approval | request status of `approval_request_id` | chip | start | no | none | yes |
| 10 | Committed at | `committed_at` | DS-FMT-17 | start | no | none | yes |
| 11 | Import number | `import_no` | mono | start | no | none | no |
| 12 | File SHA-256 | `file.sha256` | DS-FMT-23 | start | no | none | no |
| 13 | Aggregated rows | `counts.aggregated` | DS-FMT-21 | end | no | none | no |

States: empty (native) title "No imports yet", description "Upload a legacy template or a CSV file. Every import is validated and shows its changes before anything is committed.", primary "New import"; empty (legacy preset tenant, SCR-LTH-O3) description "Start with the four legacy templates. Download them, fill them in as in eRev desktop, and upload them here.", primary "Download legacy templates"; no results SCR-ST-04 "No imports match these filters"; error SCR-ST-05 "Could not load imports". Test hooks: grid "Imports" `SF-10-grid-imports`; row by file name, `SF-10-row-<file name key>`.

### 12.2 Import wizard (SF-10:new, SF-10:detail)

| Field | Value |
|---|---|
| Screen ids and routes | SF-10:new `/data/imports/new` (RT-43; `?template=<code>&mode=<literal>`, SCR-LTH-O5); SF-10:detail `/data/imports/:importId/:step` (RT-44) |
| Roles and permissions | Upload, submit, cancel `import.upload` (the uploader); approve in SF-12 |
| Purpose | Upload → map → validate → review the dry-run diff → submit for approval → atomic commit, with row lineage and findings named by 04 §15.4 codes (D-30, D-30a; DS-CMP-18) |

Wireframes, Validate step of an invalid import (WLD-B-04), 1440 px:

<!-- WF:import-validate-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Data > Imports > avm-us-progress-2026-09-invalid.csv                                             |
| Work              |  Imports    Exceptions    Integrations    Migrations    Templates                                |
|    Home           |  =======                                                                                         |
|    Contracts      | Progress events (CSV v2)  avm-us-progress-2026-09-invalid.csv  SHA-256 3f9c..7d1e  (Error)       |
|    Schedules      | (ok) 1 Upload - (-) 2 Map - (x) 3 Validate - ( ) 4 Review - ( ) 5 Approval - ( ) 6 Committed     |
|    Close          |   12 Sep 2026      Headers matched      2 errors in 2 rows                                       |
|    Journals       | +- (x) Rejected: fix the file and upload again --------------------------------------------------|
|    Reports        | | 2 errors in 2 rows. Nothing was committed. Exception items were raised.                        |
| ----------------  | | [Upload a corrected file]  [View exception items]                                              |
| Govern            | +------------------------------------------------------------------------------------------------|
|    Approvals    3 |+------------------+------------------+------------------+------------------+------------------+  |
|    Policies       || Rows             | Valid            | Warnings         | Errors           | Aggregated       |  |
| |* Data           || 14               | 12               | 0                | 2                | 0                |  |
|                   |+------------------+------------------+------------------+------------------+------------------+  |
|                   | (PROGRESS_OVER_DELIVERY . 2 rows x)                              [Download error report]         |
|                   | +-----+---------+-------------------------------------------------+-------------+----------------|
|                   | | Row | Status  | Messages                                        | Contract    | POB            |
|                   | +-----+---------+-------------------------------------------------+-------------+----------------|
|                   | |   5 | (Error) | BG-AVM-..., obligation O1 (..): requested .. +0 | BG-AVM-00.. | O1             |
|                   | |   9 | (Error) | BG-AVM-..., obligation O2 (..): requested ..    | BG-AVM-00.. | O2             |
|                   | |   2 | (Valid) |                                                 | ...         |                |
| Settings          | +-----+---------+-------------------------------------------------+-------------+----------------|
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:import-validate-1440 -->

1280 px:

<!-- WF:import-validate-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Data > Imports > avm-us-progress-2026-09-invalid.csv                                              |
| H  |  Imports    Exceptions    Integrations    Migrations    Templates                                 |
| Ct | Progress events (CSV v2)  avm-us-progress-2026-09-invalid.csv                            (Error)  |
| Sc | (ok) 1 Upload -- (-) 2 Map -- (x) 3 Validate -- ( ) 4 Review -- ( ) 5 Approval -- ( ) 6 Committed |
| Cl | +- (x) Rejected: fix the file and upload again ---------------------------------------------------|
| Jn | | 2 errors in 2 rows. Nothing was committed.  [Upload a corrected file] [View exception items]    |
| Rp | +-------------------------------------------------------------------------------------------------|
| -- | Rows 14 . Valid 12 . Warnings 0 . Errors 2                               [Download error report]  |
| Ap | +-----+---------+----------------------------------------------------+---------------------------+|
| Po | | Row | Status  | Messages                                           | Contract                  ||
| *Da| |   5 | (Error) | BG-AVM-..., obligation O1 (..): requested ..       | BG-AVM-00..               ||
| Se | +-----+---------+----------------------------------------------------+---------------------------+|
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:import-validate-1280 -->

**Frame.** Page header: breadcrumb "Data / Imports / <file name>"; `h1` "<template name>"; meta row: file name, SHA-256 (DS-FMT-23), parameters ("Effective date 31 Jan 2023"; "Mode Prospective"), uploaded by, uploaded at; status chip. Stepper DS-CMP-18: "Upload", "Map columns", "Validate", "Review changes", "Approval", "Committed". Sticky footer "Back" / "Next" (DS-CMP-18); leaving keeps the batch resumable from the list.

**Step redirect by status** (`/data/imports/:importId`): `UPLOADED`, `VALIDATING`, `INVALID`, `VALIDATED` → `validate`; `DIFFING`, `DIFF_READY` → `review`; `SUBMITTED`, `APPROVED`, `REJECTED`, `COMMITTING` → `approval`; `COMMITTED`, `FAILED` → `committed`; `CANCELLED` → `validate` with the neutral banner "This import was cancelled. Nothing was committed."

**Step 1 Upload** (SF-10:new):

| Field | Control | Rule |
|---|---|---|
| Template | select grouped "Legacy v1 templates" and "CSV v2 templates" (`GET /import-templates`) | preselected by `?template=` |
| Effective date | date | rendered when the template's `required_parameters` has `effective_date` (legacy progress tracking and modification templates, and CSV v2 event templates); required |
| Mode | radio "Prospective" `prospective`, "Retrospective" `retrospective`, "Price change" `pob_price_change` | legacy modification template only (REQ-DAT-003); preselected by `?mode=` |
| Progress mode | read-only "Delivery and billing" | legacy progress tracking template (PRD J-01.10; LTM-03) |
| Mapping profile | select of published profiles for the template, plus "None: headers match the template" | CSV v2 only |
| File | DS-CMP-18 dropzone: "Drop a CSV or XLSX file here, or choose a file" with "Choose file"; limit line "Import files must be .xlsx or .csv and at most 50 MiB." (T-PLT-29); links "Download templates" | required |

Primary "Upload and validate": `POST /files` (purpose `IMPORT_SOURCE`) then `POST /imports` (API-S-ImportCreate) → 202 job; navigate to `validate`. Refusals render on the dropzone: `upload-type-not-allowed` with ERR-37 copy; `duplicate-import` with the IMP-05 message, for example "This file was already imported in <import number> on <date>. Nothing was imported again." (J-01-ALT-1).

**Step 2 Map columns.** Legacy v1 templates: marker "Skipped", caption "Not needed: legacy template headers matched" (DS-CMP-18). CSV v2: static table from `header_match[]` (04 API-S-Import; E-119): Source column (`source_column`), Sample values (`samples`, first 3), Template field (`template_field`), Match (`match`: `EXACT` "Exact", `ALIAS` "Alias from <alias_profile_code>", `NOT_MAPPED` "Not mapped", `MISSING` "Missing"). A header mismatch makes the step Error and shows the IMP-01 finding, for example "The file does not match the Legacy v1: Contract Setup template. Missing: Memo 3. Extra: Notes." (J-01-ALT-2), with the action "Choose a mapping profile and upload again". The API has no per-import ad-hoc mapping, so there is no column select on this step; saving a mapping is a configuration change on SF-10:templates (§12.4; OQ-S-06).

**Step 3 Validate.**

| Region | Content and binding |
|---|---|
| Job indicator | "Validating <file name>" (`IMPORT_VALIDATE`), counts "<done> of <total> rows" |
| Summary strip | DS-CMP-06 import batch variant: Rows, Valid, Warnings, Errors, Aggregated (`counts`) |
| Finding chips | One DS-CMP-13 filter chip per `finding_counts[] {code, severity, rows}` item (04 API-S-Import): "<code> · <rows> rows"; selecting sets `f.code` |
| Rows grid | DataGrid over `GET /imports/{id}/rows?status&code&sort=status` (04 API-R-43 row filters): Row (`row_number`, end); Sheet (`sheet_name`, hidden for CSV); Status (chip); Messages (first `messages[].message` with the code in parentheses per CPY-06, then "+<n> more" opening the row drawer); Business key (mono); then one column per template header with `raw` values (mono for identifiers). Errors first. Rows are read-only: a corrected file is a new import (04 T-IMP-03) |
| Actions | "Download error report" (`GET /imports/{id}/error-report`, 04 §16.6: CSV `row,column,rule_id,message` over `ERROR` and `WARNING` messages); for `INVALID`: primary "Upload a corrected file" (SF-10:new with the same template and parameters) and secondary "View exception items" (SF-11 `?f.import=is:<import id>`) |
| Banner (`INVALID`) | Negative, title "Rejected: fix the file and upload again", message "<errors> errors in <rows> rows. Nothing was committed. Exception items were raised for each finding group." (SM-05) |

When validation finishes with no `ERROR` finding, the diff job starts automatically and the screen moves to `review` when the status is `DIFF_READY`; the completion is announced "Validation finished: <warnings> warnings." (DS-CMP-18).

**Step 4 Review changes.**

| Region | Content and binding |
|---|---|
| Job indicator | "Preparing changes" (`IMPORT_DIFF`) |
| Summary strip | Contracts affected, Contracts created, Allocation changes, Journal lines (`diff_summary.contracts_affected`, `diff_summary.contracts_created`, and the item counts of `diff_summary.allocation_changes[]` and `diff_summary.journal_preview[]`; 04 API-S-Import) |
| Allocation changes | Static table Contract (external id), Before, After (`diff_summary.allocation_changes[]`) |
| Revenue change by period | Static table Period, Change (DS-FMT-31) (`diff_summary.revenue_by_period_delta[]`) |
| Journal preview | Static table Account role, Debit, Credit (`diff_summary.journal_preview[]`) |
| Warnings | List of `WARNING` findings with location and code (CPY-06), for example "Row 4, column Invoice date: Effective 31 Aug 2026 in closed period Aug 2026. The effect posts to Sep 2026 with origin period Aug 2026. (LATE_EVENT)" (J-04.2) |
| Affected records | DS-CMP-16 grid diff over `GET /imports/{id}/diff` (04 API-S-ImportDiff, E-118; available from `DIFF_READY`): Change chip ("Added", "Changed"), Contract, Obligation, Measure, Before, After; SSP imports list entries (Added, Changed) |

"Next" goes to Approval. "Cancel import" (secondary, uploader) → confirmation "Cancel this import? Nothing is committed." → `POST /imports/{id}/cancel`.

**Step 5 Approval.** Before submission: Comment (required, DS-CMP-18); primary "Submit for approval" → `POST /imports/{id}/submit`; toast "Submitted for approval. Request <request no> is waiting for approval." After submission: routing steps of the request (step name, permission label, status chip, decisions with comments); link "View request"; auto-approval line "Approved automatically under rule <rule key> version <n>." when the decision is `AUTO_APPROVE` (REQ-PLT-016); rejection banner "Rejected by <name>: <comment>" with "Upload a corrected file".

**Step 6 Committed.** Job indicator "Committing <rows> rows" (`IMPORT_COMMIT`). Summary: Committed at (DS-FMT-17); control totals static table Measure, Source, Loaded, Result chip ("Reconciled" or "Difference") from `control_totals`; "Created records" DataGrid over rows with `lineage[]`: Row, Target (label of `target_type`, for example "Contract event", "SSP book version", "Customer"), Record (link); link "View exception items" when any exist. `FAILED`: negative banner with IMP-43 "Control totals do not match for <import>: source <count> records, <amount>; loaded <count> records, <amount>. Nothing was committed." or IMP-07 copy.

**States.** Loading: stepper and summary skeletons. Not found: SCR-ST-07 "Import not found". Error: SCR-ST-05. Job failed: SCR-ST-12 with the job label.

**Keyboard and copy.** DS-CMP-18 keyboard; dropzone is a button backed by `input type="file"`. Copy keys: `data.imports.new.title` "New import"; `.upload.dropzone` "Drop a CSV or XLSX file here, or choose a file"; `.upload.choose` "Choose file"; `.upload.limit` "Import files must be .xlsx or .csv and at most 50 MiB."; `.upload.submit` "Upload and validate"; `.map.skipped` "Not needed: legacy template headers matched"; `.validate.rejected.title` "Rejected: fix the file and upload again"; `.validate.downloadErrors` "Download error report"; `.review.title` "Review changes"; `.approval.submit` "Submit for approval"; `.cancel` "Cancel import".

**Sample world.**

| Journey | File and template | Rendered content |
|---|---|---|
| J-01.6 (WLD-T-20) | `SKU SSP Template.xlsx`, Legacy v1: SKU SSP | Map "Not needed: legacy template headers matched"; 0 findings; review "SSP book version 2023-01-01 · 7 entries · method Legacy range" |
| J-01.8 | `Contract Setup Template 1.1.2023.xlsx`, Legacy v1: Contract Setup | Review: 2 contracts created; Contract 1 with 4 obligations, allocation 322.10 / 237.07 / 96.63 / 644.20 (transaction price 1,300.00); Contract 2 with 3 obligations and 1 VC element, allocation 470.77 / 313.85 / 115.38 and VC element (100.00) (transaction price 900.00) (asserted, WLD-X-26) |
| J-01.10 | `Contract Progress Tracking Template 1.31.2023.xlsx`, Legacy v1: Contract Progress Tracking, effective date 31 Jan 2023, mode Delivery and billing | Rows grid: the two Contract 1 POB #1 rows show chip Aggregated; review: Contract 1 POB #1 revenue 128.84; Contract 2 contract asset and unbilled receivable 58.85 (D-12 labelled display of the PRD debit net position) |
| J-01-ALT-3 | `Contract Setup Template 1.1.2023.xlsx` before the SSP import | Error `SSP_KEY_NOT_FOUND` "No approved SSP for Hardware 1 / Hardware 1 / 2023-01-01." |
| J-04.1 | `avm-de-progress-2026-09.csv`, Progress events (CSV v2) | 0 findings; review "NS-SO-DE-5004 O1 delivered 120 of 200; revenue 53,504.59 on 12 Sep 2026" |
| J-04.2 | `avm-de-invoices-2026-09.csv`, Invoices and credit memos (CSV v2) | Review: INV-DE-4471 → NS-SO-DE-5004 O1; INV-DE-4472 → O2; INV-DE-4390 → NS-SO-DE-5003 with warning `LATE_EVENT` "Effective 31 Aug 2026 in closed period Aug 2026. The effect posts to Sep 2026 with origin period Aug 2026." |
| J-04-ALT-1 | `avm-de-progress-2026-09-overdelivery.csv` | Invalid; error "NS-SO-DE-5004, obligation O1 (AVM-GW): requested 90, remaining 80." (asserted) |
| J-12-ALT-1 | commission file with contract `SF-ORD-99999` | Invalid; message "Row 2, column Contract: Contract SF-ORD-99999 does not exist in this workspace. (CONTRACT_NOT_FOUND)" (asserted) |
| WLD-B-04 | `avm-us-progress-2026-09-invalid.csv` | Status Error with caption "Rejected: fix the file and upload again"; two `PROGRESS_OVER_DELIVERY` errors; two exception items |

**Test hooks.**

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Stepper | `getByRole("navigation", {name: "Import steps"})` | `SF-10-stepper` |
| Dropzone | `getByRole("button", {name: /^Drop a CSV or XLSX file/})` | `SF-10-dropzone` |
| Summary strip | `getByRole("region", {name: /^Import figures/})` | `SF-10-kpi-strip` |
| Rows grid | `getByRole("grid", {name: "Import rows"})` | `SF-10-grid-rows` |
| Rejected banner | `getByRole("heading", {name: "Rejected: fix the file and upload again"})` | `SF-10-banner-rejected` |
| Review diff | `getByRole("grid", {name: "Affected records"})` | `SF-10-diff` |

**Light, dark and accessibility.** Dropzone edge 1 px dashed `--border-control` in both themes; invalid cells carry the `--negative-fg` inset edge with an icon and text (DS-CMP-10). Stepper items are named "Step 3 of 6, Validate, 2 errors in 2 rows" (DS-CMP-18); validation completion and failure are announced.

### 12.3 Import row drawer

The drawer of §6.6 opens on the `validate` and `committed` steps from a row's "+<n> more" link, from lineage links, and from Explain source records (`row=<row number>&sheet=<sheet name>`). J-16.4 sample: file `avm-us-costs-2026-09.csv`, row 2, raw cell values, import number, uploader Maya Chen, approver Priya Raman. Test hook `getByRole("dialog", {name: /^Row /})`, `SF-10-drawer-row`.

### 12.4 Templates and mapping profiles (SF-10:templates)

| Field | Value |
|---|---|
| Route | `/data/templates` (RT-45) |
| Permissions | Read `contract.read`; mapping profiles authored with `config.author` and approved with `config.approve` (`MAPPING_PROFILE_VERSION`) |
| Purpose | Download the legacy v1 and CSV v2 templates with example rows and column definitions; manage mapping profiles (REQ-DAT-013, REQ-DAT-016) |

Templates static table (`GET /import-templates`), caption "Import templates": Template (`name`); Code (mono); Family (outline chip "Legacy v1" or "CSV v2"); Format; Version; Parameters (labels of `required_parameters`); Download (button "Download <name>", `GET /import-templates/{code}/download`). Filter chip "Family" (`?f.family=is:LEGACY_V1`).

Template names (seeded `import_template.name`; copy): `legacy_sku_ssp` "Legacy v1: SKU SSP"; `legacy_contract_setup` "Legacy v1: Contract Setup"; `legacy_progress_tracking` "Legacy v1: Contract Progress Tracking"; `legacy_contract_modification` "Legacy v1: Contract Modification"; `customers` "Customers (CSV v2)"; `products` "Products (CSV v2)"; `bundles` "Bundles (CSV v2)"; `ssp_values` "SSP values (CSV v2)"; `contracts` "Contracts (CSV v2)"; `invoices` "Invoices and credit memos (CSV v2)"; `progress_events` "Progress events (CSV v2)"; `usage` "Usage (CSV v2)"; `modifications` "Modifications (CSV v2)"; `estimates` "Estimates (CSV v2)"; `fx_rates` "FX rates (CSV v2)"; `cost_events` "Cost events (CSV v2)"; `pre_standard_revenue` "Pre-standard revenue (CSV v2)"; `gl_accounts` "GL accounts (CSV v2)"; `account_mapping` "Account mapping (CSV v2)".

Mapping profiles panel: DataGrid (`GET /import-mapping-profiles`): Profile (`code`), Name, Template, Version, Status (chip), Effective from. Primary "New mapping profile" (drawer: Code, Name, Template (CSV v2), Aliases table Source column → Template column, Constants table Template column → Value, Custom attribute columns list; primary "Save draft"); version actions "Run tests", "Submit for approval" as §11.0 (`POST /import-mapping-profiles/{id}/test`, `/submit`).

States: mapping profiles empty "No mapping profiles. Create one when your CSV headers differ from a template." Sample world: J-01.6 downloads "Legacy v1: SKU SSP". Test hooks: table "Import templates" `SF-10-grid-templates`; button "Download Legacy v1: SKU SSP".

## 13. SF-11 Exception queue

### 13.1 Summary

| Field | Value |
|---|---|
| Screen ids and routes | SF-11 `/data/exceptions` (RT-46); SF-11:item `/data/exceptions/:exceptionId` (RT-47) |
| Roles and permissions | Read `contract.read`. Assign, reprocess, resolve, dismiss, request waiver `exception.resolve` (ACT-17); waiver decision in SF-12 `exception.waive` (ACT-18) |
| Purpose | One queue for import, sync, engine, close, reconciliation, journal, integration, data-quality, migration and anomaly findings: remediable items reprocess, never-committed input can be dismissed, everything else needs an approved waiver (REQ-DAT-009; BR-DAT-04; SM-06) |
| REQ | REQ-DAT-009, REQ-CLS-013, REQ-CLS-019, REQ-AI-007, REQ-REF-014 |
| Journeys | J-04-ALT-1 (item raised and dismissed); J-13 steps 3 and 5 (WLD-B-04 dismissed, WLD-B-06 cleared by attestation; SCREENS_B journey context); J-23 (`PRODUCT_UNMAPPED` reprocessed) |

### 13.2 Wireframes

1440 px (WLD-B-04 item selected):

<!-- WF:exceptions-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Data > Exceptions                                                                                |
| Work              |  Imports    Exceptions    Integrations    Migrations    Templates                                |
|    Home           |             ==========                                                                           |
|    Contracts      | Exceptions  4 open                                                                               |
|    Schedules      | [Search exceptions___] (Status is Open, In progress x) (Entity is AVM-US x) [+ Filter]  Clear all|
|    Close          |+--------------------------------------+  +------------------------------------------------------+|
|    Journals       || {Sort: Severity v}   4 exceptions    |  | Delivery exceeds the remaining quantity              ||
|    Reports        |||* Delivery exceeds remaining   (Block|  | PROGRESS_OVER_DELIVERY  (Blocking) (Open) <Remediable||
| ----------------  |||* PROGRESS_OVER_DELIVERY . Import    |  | Message                                              ||
| Govern            ||  Delivery exceeds remaining   (Blocki|  |  BG-AVM-..., obligation O1 (..): requested .., remain||
|    Approvals    3 ||  PROGRESS_OVER_DELIVERY . Import     |  | Location                                             ||
|    Policies       ||  VC reassessment missing      (Blocki|  |  Import avm-us-progress-2026-09-invalid.csv . row 5  ||
| |* Data           ||  VC_REASSESSMENT_MISSING . Close     |  |  Contract BG-AVM-... . Entity AVM-US . Period Sep 202||
|                   ||                                      |  | Owner {Unassigned v} [Assign to me]                  ||
|                   ||                                      |  | [Dismiss exception]  [Request waiver]                ||
|                   ||                                      |  |                                                      ||
|                   ||                                      |  |                                                      ||
| Settings          |+--------------------------------------+  +------------------------------------------------------+|
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:exceptions-1440 -->

1280 px:

<!-- WF:exceptions-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Data > Exceptions                                                                                 |
| H  |  Imports    Exceptions    Integrations    Migrations    Templates                                 |
| Ct | Exceptions  4 open                                                                                |
| Sc |+-----------------------+ +-----------------------------------------------------------------------+|
| Cl || {Sort v}  4 exceptions| | Delivery exceeds the remaining quantity                               ||
| Jn |||* Delivery exceeds rem| | PROGRESS_OVER_DELIVERY (Blocking) (Open)                              ||
| Rp |||* (Blocking) Import   | | BG-AVM-..., obligation O1: requested .., remaining ..                 ||
| -- ||  VC reassessment m..  | | Import .. row 5 . Contract BG-AVM-..                                  ||
| Ap ||  (Blocking) Close     | | [Assign to me] [Dismiss exception] [Request waiver]                   ||
| Po ||                       | |                                                                       ||
| *Da||                       | |                                                                       ||
| Se |+-----------------------+ +-----------------------------------------------------------------------+|
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:exceptions-1280 -->

### 13.3 Regions and components

| Region | Component | Content |
|---|---|---|
| Page header | none | `h1` "Exceptions" with "<n> open" |
| FilterBar | DS-CMP-13 | Status (default `in:OPEN,IN_PROGRESS`); Severity; Source; Code (combobox of 04 §15.4 codes); Entity (rev 1.37: the items that are the entity's, 04 rev 1.206 — those that name it, a contract or a contract group of it, an import or a connection of it, and the workspace-level items); Owner (user combobox with "Me"); Contract (combobox); Period; Import (combobox of imports) |
| Lock banner (rev 1.50) | DS-CMP-29, info | Shown while the address holds `blocking` (§13.4): "Showing the exceptions that hold the lock of one period." with the link "Show all exceptions", which drops the parameter and nothing else. A list cut down by a parameter that no control shows would read as "there are only these". The queue knows the period by its id alone and does not name it |
| Master list | DS-CMP-08 exception queue variant | Sort menu "Severity" (default: Blocking, Warning, Info, then newest; 04 API-R-44), "Newest", "Oldest" |
| Detail pane | DS-CMP-08 detail with DS-CMP-06 compact header | §13.5 |

### 13.4 Data bindings

| Region | Endpoint | Parameters and fields |
|---|---|---|
| Master | `GET /exceptions` (API-R-44; fields T-IMP-05) | `status`, `severity`, `source`, `code`, `contract`, `entity`, `owner`, `period`, `import_upload_id`, `sort` (04 API-R-44), `limit=200`, `count=true`; rev 1.37: `blocking` — the id of one period (API-S-Period `id`), passed through from the URL parameter of the same name by the links of SCREENS_B BLK-02 and of the home page's close row: the items that hold that period's lock (04 §16.14 rev 1.206); rev 1.50: the parameter stays in the address while the reader filters, sorts or opens an item, and the header's "<n> open" stays the count of every open exception, read without it; fields `id`, `title`, `code`, `severity`, `status`, `source`, `business_key`, `contract_id` with its external id, `occurrence_count`, `created_at` |
| Detail | `GET /exceptions/{id}` | every T-IMP-05 column plus `available_actions[]` (E-117) and `dismiss_blocked_reason` (`INPUT_COMMITTED` or null) (04 §16.14) |
| Commands | `POST /exceptions/{id}/assign` (`owner_membership_id`); `/reprocess` (202 job); `/resolve` (`resolution`); `/request-waiver` (`comment`); `/dismiss` (`comment`) | `Idempotency-Key`; `If-Match` `"r<row_version>"` |

Master row: line 1 `title` and, at the end, the severity chip; line 2 `code` (mono) · source label (E-42: `IMPORT` "Import", `SYNC` "Sync", `ENGINE` "Engine", `CLOSE` "Close", `RECONCILIATION` "Reconciliation", `JOURNAL` "Journal", `INTEGRATION` "Integration", `DATA_QUALITY` "Data quality", `MIGRATION` "Migration", `ANOMALY` "Anomaly") · business key or contract external id · "Seen <n> times" when `occurrence_count` > 1 · created date.

### 13.5 Detail pane

| Section | Content |
|---|---|
| Header | `h2` `title`; chips severity and status; outline `disposition` ("Remediable", "Discarded"); `exception_no` (mono, copy) |
| Message | `message` (PRD IMP copy of the code) |
| Suggestion | `suggestion` (rendered when present) |
| Location | Definition list: Source; Import (file name link to SF-10:detail with the row drawer), Row, Field; Contract (link), Obligation (link); Entity; Period; Close run, Journal run, Sync run (links, SCREENS_B and §14) |
| Occurrences | "<occurrence_count> occurrences · last seen <DS-FMT-17>" |
| Owner | Combobox "Owner" with "Unassigned" and the button "Assign to me"; changing the owner sends `assign` and moves `OPEN` to `IN_PROGRESS` |
| Resolution | For `RESOLVED`, `WAIVED`, `DISMISSED`: resolution text, resolved by, resolved at, waiver request link |
| Source payload | Collapsible mono block "Source payload" (`source_payload`) |
| Actions | Rendered from `available_actions[]` (E-117; 04 §16.14): "Reprocess" (primary for remediable items); "Mark resolved" (when the server reports the condition cleared); "Request waiver"; "Dismiss exception" (Danger inside its confirmation) |

- **Reprocess**: `POST /exceptions/{id}/reprocess` → job indicator "Reprocessing <code>"; success toast "Reprocessed. The exception is resolved."; a new finding shows its IMP message in a negative banner.
- **Mark resolved**: modal "Mark <code> resolved?" with Resolution (minimum 10 characters) → `resolve`.
- **Request waiver** drawer: Comment (minimum 10 characters), attachments; primary "Request waiver" → `request-waiver`; banner "Waiver requested. Request <request no> is waiting for approval." (SM-06; `EXCEPTION_WAIVER`).
- **Dismiss**: confirmation (DS-CMP-11) title "Dismiss exception <code>?"; description "Dismissal applies only to input that was never committed. The item counts as cleared for the close gates."; Reason (minimum 10 characters); buttons "Cancel" and Danger "Dismiss exception". When `DISMISS` is not available, the button is not rendered and the line "Dismissal applies only to input that was never committed." appears under the actions, followed by its second sentence, "Request a waiver instead.", only while "Request waiver" is among the commands offered to the reader (rev 1.59; BR-DAT-04; SCR-PERM-03).

Exception titles are copy stored with the item (T-IMP-05 `title`) from the shared catalogue `finding.<code>.title`. Titles fixed here for the sample world: `PROGRESS_OVER_DELIVERY` "Delivery exceeds the remaining quantity"; `VC_REASSESSMENT_MISSING` "Variable consideration reassessment missing"; `PRODUCT_UNMAPPED` "Product without an approved product record"; `LATE_EVENT` "Event in a closed period"; `CONTRACT_NOT_FOUND` "Contract not found"; `TEMPLATE_HEADER_MISMATCH` "File headers do not match the template"; `ACCOUNT_MAPPING_MISSING` "Account mapping missing"; `ENGINE_INVARIANT_VIOLATION` "Calculation quarantined"; `CONTROL_TOTALS_MISMATCH` "Control totals do not match" (04 T-IMP-05 `title` from `finding.<code>.title`; OQ-S-21 resolved by D-76). Codes without a title here use the first clause of their PRD IMP message as the catalogue title.

### 13.6 States

| State | Rendering and copy |
|---|---|
| Loading | 6 skeleton rows; detail skeleton |
| Empty (no filters) | Title "No exceptions"; description "Rows that fail validation during imports and integrations appear here for correction."; action "View imports" (DS-CMP-23) |
| No results | SCR-ST-04 "No exceptions match these filters" |
| No results under `blocking` (rev 1.50) | The list of the items that hold a lock is a cut-down list: empty, it reads "No exceptions match these filters", never "No exceptions". Where no chip cuts it down as well the action is "Show all exceptions" — "Clear filters" would change nothing; with a chip beside it the action is "Clear filters", which clears the chips and keeps `blocking` |
| Nothing selected | "Select an exception to see its location, message and next steps." |
| Error | SCR-ST-05 "Could not load exceptions" |
| Not found | "Exception not found" |

### 13.7 Keyboard and copy

Keyboard: DS-CMP-08 list keys; FilterBar APG Toolbar. Copy keys: `data.exceptions.title` "Exceptions"; `.openCount` "{count} open"; `.assignToMe` "Assign to me"; `.reprocess` "Reprocess"; `.resolve` "Mark resolved"; `.requestWaiver` "Request waiver"; `.dismiss` "Dismiss exception"; `.dismissBlocked` "Dismissal applies only to input that was never committed. Request a waiver instead."; rev 1.59: `.dismissBlockedNoWaiver` "Dismissal applies only to input that was never committed."; rev 1.50: `.blocking.title` "Showing the exceptions that hold the lock of one period."; `.blocking.showAll` "Show all exceptions"

### 13.8 Sample world

| Item | Rendering (asserted where cited) |
|---|---|
| WLD-B-04, two items | Title "Delivery exceeds the remaining quantity"; code `PROGRESS_OVER_DELIVERY`; severity Blocking; status Open; source Import; location `avm-us-progress-2026-09-invalid.csv`; actions include "Dismiss exception" (input never committed; J-13 step 3) |
| WLD-B-06 | Title "Variable consideration reassessment missing"; `VC_REASSESSMENT_MISSING`; Blocking; source Close; contract `BG-AVM-0024`; message "BG-AVM-0024, VC element VC-BG-017: no estimate version or approved "No change" attestation is effective at 30 Sep 2026."; "Dismiss exception" not available (line of §13.5) |
| J-04-ALT-1 | `PROGRESS_OVER_DELIVERY` "NS-SO-DE-5004, obligation O1 (AVM-GW): requested 90, remaining 80."; source Import; severity Blocking; Maya dismisses it (asserted) |
| J-23 (WLD-T-22) | `PRODUCT_UNMAPPED` "Order <order>, line <n>: product SF-PROD-X99 has no approved product record."; disposition Remediable; "Reprocess" after the product is mapped |

### 13.9 Test hooks, light and dark, accessibility

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Master list | `getByRole("listbox", {name: "Exceptions"})` | `SF-11-grid-exceptions` |
| Option | `getByRole("option", {name: /PROGRESS_OVER_DELIVERY/})` | `SF-11-row-progress-over-delivery` (first match; use role locators to distinguish duplicates) |
| Detail pane | `getByRole("region", {name: /^Exception details: /})` | `SF-11-pane-exception` |
| Dismiss dialog | `getByRole("alertdialog", {name: /^Dismiss exception/})` | `SF-11-dialog-dismiss` |
| Lock banner (rev 1.50) | `getByRole("heading", {name: "Showing the exceptions that hold the lock of one period."})` | `SF-11-banner-blocking` |

Light and dark: severity chips per §0.8; the source payload block `--bg-subtle` with mono text. Accessibility: detail pane region named "Exception details: <title>"; the blocked-dismissal line is linked to the actions group through `aria-describedby`.

## 14. SF-16 Integrations status

### 14.1 Summary

| Field | Value |
|---|---|
| Screen ids and routes | SF-16 `/data/integrations` (RT-48); SF-16:connection `/data/integrations/:connectionId` (RT-49); SF-16:sync-run `/data/integrations/:connectionId/sync-runs/:syncRunId` (RT-50). Developer settings SF-16:developer are SCREENS_B |
| Roles and permissions | `integration.manage` for every read and command (ACT-45); mapping profiles through ACT-22 |
| Purpose | Connection status, test connection with UTC time, sync runs with control totals and differences, and external ids, against in-process mock adapters in dev, test and e2e (PRD SF-16; D-72) |
| REQ | REQ-INT-001 to REQ-INT-009, REQ-DAT-010; BR-INT-01 to BR-INT-03 |
| Journeys | J-01.13 ("Connection succeeded" with UTC time); J-03.1 (sync run control totals); J-23 (Quayside Salesforce and Stripe scenario) |

### 14.2 Wireframes

Connection detail, 1440 px:

<!-- WF:integration-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Data > Integrations > Salesforce orders                                                          |
| Work              |  Imports    Exceptions    Integrations    Migrations    Templates                                |
|    Home           |                           ============                                                           |
|    Contracts      | Salesforce orders  (Active) <Salesforce> <Mock>              [*Test connection] [Run sync v] ..  |
|    Schedules      | (ok) Connection succeeded . 12 Sep 2026 09:12 UTC                                                |
|    Close          |  Settings    Sync runs    External ids                                                           |
|    Journals       |              =========                                                                           |
|    Reports        | +-------------------+--------------+-----------+---------+-----------------------+-------------+-|
| ----------------  | | Started           | Kind         | Status    | Records | Source totals         | Result      |E|
| Govern            | +-------------------+--------------+-----------+---------+-----------------------+-------------+-|
|    Approvals    3 | | 12 Sep 2026 14:01 | Webhook batch| (Succeed.)|       1 | 1 record . USD 120,000| (Reconciled)| |
|    Policies       | | 12 Sep 2026 13:00 | Inbound poll | (Succeed.)|       0 | 0 records             | (Reconciled)| |
| |* Data           | +-------------------+--------------+-----------+---------+-----------------------+-------------+-|
| Settings          |                                                                                                  |
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:integration-1440 -->

Integrations list, 1280 px:

<!-- WF:integration-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Data > Integrations                                                                               |
| H  |  Imports    Exceptions    Integrations    Migrations    Templates                                 |
| Ct | Integrations  2 connections                                                  [*Add connection]    |
| Sc | +--------------------+------------+----------+----------+-------------------+-------------------+ |
| Cl | | Connection         | Adapter    | Direction| Status   | Last test         | Last sync         | |
| Jn | +--------------------+------------+----------+----------+-------------------+-------------------+ |
| Rp | | Salesforce orders  | Salesforce | Inbound  | (Active) | (Succeeded) 12 Sep| (Succeeded) 12 Sep| |
| -- | | NetSuite GL        | NetSuite   | Both     | (Active) | (Succeeded) 12 Sep| (Succeeded) 12 Sep| |
| Ap | +--------------------+------------+----------+----------+-------------------+-------------------+ |
| Po |                                                                                                   |
| *Da|                                                                                                   |
| Se |                                                                                                   |
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:integration-1280 -->

### 14.3 Regions, bindings and columns

| Screen | Region | Component | Binding |
|---|---|---|---|
| SF-16 | Grid | DS-CMP-10 | `GET /integrations` (T-INT-01 columns plus `last_sync_run {id, status, finished_at, result {record_count, exception_count}}`, 04 §16.14) |
| SF-16 | Add connection drawer | DS-CMP-09 | `POST /integrations` |
| SF-16:connection | Header and settings | DS-CMP-06, definition list | `GET /integrations/{id}`; `PATCH /integrations/{id}` |
| SF-16:connection | Test connection | DS-CMP-20, DS-CMP-29 | `POST /integrations/{id}/test` |
| SF-16:connection | Run sync | menu button, DS-CMP-24 | `POST /integrations/{id}/sync` with `kind` |
| SF-16:connection | Sync runs | DS-CMP-10 | `GET /sync-runs?connection=<id>&status&kind` (04 API-R-45); code `SF-16#sync-runs` |
| SF-16:connection | External ids | DS-CMP-10 | `GET /external-ids?connection=<id>` (04 API-R-45; T-INT-04) |
| SF-16:sync-run | Summary, control totals, exceptions | definition list, static tables | `GET /sync-runs/{id}`; `GET /exceptions?source=SYNC&sync_run_id=<id>` (04 API-R-44) |

Connections grid:

| # | Header | Field | Format | Alignment | Visible |
|---|---|---|---|---|---|
| 1 | Connection | `name`, link | text link, pinned start | start | yes |
| 2 | Adapter | `adapter`: `SALESFORCE` "Salesforce", `STRIPE` "Stripe", `NETSUITE` "NetSuite", `QUICKBOOKS_ONLINE` "QuickBooks Online", `CSV_GL` "CSV GL export"; outline chip "Mock" when the path of `base_url` starts with `/api/v1/__mocks__/` (rev 1.13: in a running stack the value is an address, the API's own origin followed by that path, because the adapter client connects to an absolute address — 05 ADP-14, SAR-15; the bare path is what the in-process test client takes) | text | start | yes |
| 3 | Direction | `direction`: "Inbound", "Outbound", "Both" | text | start | yes |
| 4 | Entities | codes of `entity_ids`, "All entities" when empty | mono | start | yes |
| 5 | Status | `status` | chip (§0.8) | start | yes |
| 6 | Last test | `last_test_result` chip ("Succeeded", "Failed") and `last_test_at` (DS-FMT-17) | chip and text | start | yes |
| 7 | Last sync | `last_sync_run.status` chip and `finished_at` | chip and text | start | yes |
| 8 | Control totals | `last_sync_run.status`: `CONTROL_TOTAL_MISMATCH` "Difference", `SUCCEEDED` "Reconciled", otherwise "—" (the `result` object holds `record_count` and `exception_count`, 04 §16.14) | chip | start | yes |
| 9 | Code | `code` | mono | start | no |

Sync runs grid (SF-16:connection):

| # | Header | Field | Format | Alignment | Sort | Visible |
|---|---|---|---|---|---|---|
| 1 | Started | `started_at`, link to SF-16:sync-run | DS-FMT-17 | start | default descending | yes |
| 2 | Kind | `kind`: `INBOUND_POLL` "Inbound poll", `WEBHOOK_BATCH` "Webhook batch", `RECONCILIATION_SWEEP` "Reconciliation sweep", `COA_SYNC` "Chart of accounts sync", `TRIAL_BALANCE_PULL` "Trial balance pull", `JOURNAL_EXPORT` "Journal export", `TEST_CONNECTION` "Test connection" | text | start | no | yes |
| 3 | Status | `status` | chip | start | no | yes |
| 4 | Records | `record_count` | DS-FMT-21 | end | no | yes |
| 5 | Source totals | `source_totals.count` and each `amount_by_currency` as "USD 120,000.00" | text | start | no | yes |
| 6 | Loaded totals | `loaded_totals` as above | text | start | no | yes |
| 7 | Result | "Reconciled" when the totals match, "Difference" otherwise (`status = CONTROL_TOTAL_MISMATCH`) | chip | start | no | yes |
| 8 | Exceptions | `exception_count`, link to SF-11 | DS-FMT-21 | end | no | yes |
| 9 | Duration | `finished_at − started_at` from the API field `duration_seconds` (04 §16.14; null while running) | DS-FMT-24 | end | no | yes |

**As bound to API-R-45 of 1.0 (rev 1.13).** Sync runs: the grid keeps the API's order, newest first by `created_at` (`GET /sync-runs` sorts by `created_at`, `finished_at` or `id`; it has no `started_at` key, so "Started" is not sortable), and its filter chips are Status and Kind. Columns 5 and 6 read the recorded totals `{count, amount_by_currency}` as "<n> records · USD 120,000.00": T-INT-02 records one count per side, not orders and lines. Column 7 and the connections grid's column 8 show the run's `status` (`SUCCEEDED` "Reconciled", `CONTROL_TOTAL_MISMATCH` "Difference", otherwise no value); the screens never compare the two sides themselves. Column 7 shows no value for a run that recorded no totals on either side — a test, a run that failed before it loaded anything — because nothing was reconciled; SF-16:sync-run reads "This run recorded no control totals." for the same run. The connections grid's column 8 cannot make that distinction: `last_sync_run` is the connection's newest run of any kind, a test included, and its shape carries neither `kind` nor totals. Column 8 links to SF-11 filtered to source Sync while SF-11 has no sync-run chip; the run's own items are listed on SF-16:sync-run. Connections: a connection's entities outside the viewer's scope are counted ("AVM-US and 1 other"), never shown by id; the grid sorts by Connection (`name`) and Code (`code`). External ids: External id (mono), Record (the T-INT-04 object type in words, linked to the record's screen for a contract, a customer and a product), Source version, Valid from, Valid to and Linked (`created_at`), newest first.

### 14.4 Forms and commands

- **Add connection** and **Edit connection** drawer: Adapter (select, immutable after creation); Name; Code; Direction (default per adapter: Salesforce and Stripe "Inbound", NetSuite "Both", QuickBooks Online "Outbound", CSV GL export "Outbound"); Entities (multi-select, empty = all); Base URL (help "In development and test workspaces this is the address of the in-process mock adapter: the API's own origin followed by /api/v1/__mocks__/ and the adapter's name." — rev 1.13; the wording of rev 1.0 said "path", and a connection saved with the path alone fails its test with "base_url refused: The destination must use https."); Credential reference (`secret_ref`; BR-INT-01; rev 1.13 after 04 T-INT-01 rev 1.108 and ruling R-48 (f): the workspace's own namespace of the secret store, `tenant-<tenant id>-`, stands as fixed text before the field and the field holds the rest of the reference, `<name>@<version number>`; the two together are what is sent, a reference pasted whole keeps one prefix, and an empty field sends no reference; help "Enter the rest of the secret's name and its version number, for example netsuite-token@3. The secret itself is never stored. Leave the field empty for a connection that sends no credential."; the API's refusal of a reference, 422 on `secret_ref`, is shown on the field in the API's words; a stored reference outside the namespace is shown in full under the field with "The stored reference <reference> is outside this workspace's namespace, so the secret store does not serve it. Enter a reference of this workspace to replace it." and is sent only when the field is changed); Settings (key and value rows, non-secret). Primary "Save connection". New connections start `DISABLED`. In a sandbox workspace "Add connection" offers what `POST /integrations` accepts there (rev 1.43; SB-R-08; 05 SBX-08: the API answers 403 `sandbox-restricted` for a Salesforce or Stripe connection and for the direction "Inbound" or "Both"): the adapters NetSuite, QuickBooks Online and CSV GL export, and the direction "Outbound" alone, which is NetSuite's default there; the Adapter's help adds "A sandbox workspace takes no inbound connection: Salesforce, Stripe and the directions Inbound and Both are not offered."
- **Test connection**: result banner inside the header region: positive "Connection succeeded · <DD MMM YYYY HH:mm UTC>" or negative "Connection failed · <DD MMM YYYY HH:mm UTC>: <last_test_detail>" (J-01.13). In a sandbox workspace the control renders `aria-disabled` with the reason "A connection cannot be tested in a sandbox workspace: a sandbox reaches no external system." for every adapter that calls out — every adapter but CSV GL export, whose export is a download (rev 1.35; SB-R-08; 05 SBX-08 rev 1.116, item SBX-PROBE-1: the API answers the command 403 `sandbox-restricted`).
- **Run sync** menu: items by adapter and direction ("Inbound poll", "Reconciliation sweep", "Chart of accounts sync", "Trial balance pull"); job indicator "Syncing <connection name>" (SB-R-06); completion toast "Sync finished: <records> records, control totals reconciled." or warning toast "Sync finished with a control total difference. Exceptions were raised."
- **Enable** and **Disable** (overflow): `PATCH /integrations/{id}` `status`. In sandbox tenants, enabling an outbound GL adapter other than CSV GL export renders `aria-disabled` with the reason "Sandbox workspaces cannot post or export journals." (SB-R-08; DB-15).
- **As bound to API-R-45 of 1.0 (rev 1.13).** "Edit connection" opens from the Settings panel and changes what `PATCH /integrations/{id}` admits (name, entities, base URL, credential reference, settings; `If-Match` with the row version); adapter, code and direction are fixed once the connection is saved. "Test connection" answers at once (200 with `last_test_*`); a failure without a detail reads "Connection failed · <timestamp>". "Run sync" offers the kinds the API queues: "Inbound poll" and "Reconciliation sweep" for a Salesforce or Stripe connection that reads, "Chart of accounts sync" for a NetSuite connection; "Trial balance pull" joins when the API queues it (CLO-15). On a Disabled connection "Run sync" renders `aria-disabled` with the reason "Enable the connection to run a sync." (SCR-PERM-03). A run that ends `FAILED` shows the negative toast "The sync failed. Open the run to see why."; every completion toast carries "View run". "Enable" and "Disable" are a header button, not overflow items, until DS-CMP-28 carries a disabled item with a reason (ruling R-83 (c)); the sandbox rule above needs one. The panel tabs write `pane` = `settings`, `sync-runs` (the default, omitted) or `external-ids`. A `mfa-step-up-required` answer to "Save connection" opens the step-up dialog of SCR-PERM-05 and re-sends the command with the same key.

### 14.5 Sync run page

Header `h1` "Sync run · <connection name>" with the status chip. Definition list: Kind; Started; Finished; Duration; Checkpoint before and after (mono, collapsible). "Control totals" static table: Measure ("Records", then one row per currency amount), Source, Loaded, Result chip. Problem banner when `problem` is present (problem title, "Reference <request id>"). "Exceptions" static table Title, Code, Severity, link. Rev 1.13: the "Result" cell spans the table's rows and shows the run's one result (its `status`, which the API decided over every measure); the currency rows read "Amount (<ISO code>)"; a run without totals (a test, a run that failed before loading) reads "This run recorded no control totals." and a run without items "This run raised no exceptions."; the title of an exception links to SF-11:item; a run whose connection is not the one in the path is SCR-ST-07 "Sync run not found"; a run still `QUEUED` or `RUNNING` is read again every two seconds.

### 14.6 States

| Screen | State | Copy |
|---|---|---|
| SF-16 | Empty | Title "No integrations yet"; description "Connect CRM, billing and ERP systems. Tests and syncs record control totals, and differences go to the exception queue."; primary "Add connection" |
| SF-16:connection | Sync runs empty | "No sync runs yet. Run a sync or wait for the next scheduled poll." |
| SF-16:connection | Never tested | Info line "This connection has not been tested." with "Test connection" (rev 1.13: the header's primary "Test connection"; the line holds no second control of that name) |
| SF-16:connection, SF-16:sync-run | Not found (rev 1.13) | SCR-ST-07 "Connection not found" and "Sync run not found", action "Go to Integrations" |
| all | No permission | SCR-PERM-01 "integrations", "managing integrations" |
| all | Error | SCR-ST-05 "Could not load integrations" |

### 14.7 Keyboard and copy

Keyboard: DS-CMP-10; panel tabs "Settings · Sync runs · External ids" APG Tabs. Copy keys: `data.integrations.title` "Integrations"; `.add` "Add connection"; `.test` "Test connection"; `.test.succeeded` "Connection succeeded · {timestamp}"; `.test.failed` "Connection failed · {timestamp}: {detail}"; `.runSync` "Run sync"; `.secretHelp` "Enter the rest of the secret's name and its version number, for example netsuite-token@3. The secret itself is never stored. Leave the field empty for a connection that sends no credential." (rev 1.13; the wording of rev 1.0 named an environment variable or any Secret Manager path, which 04 T-INT-01 rev 1.108 refuses); `.secretOutside` "The stored reference {reference} is outside this workspace's namespace, so the secret store does not serve it. Enter a reference of this workspace to replace it." (rev 1.13); `.test.sandboxReason` "A connection cannot be tested in a sandbox workspace: a sandbox reaches no external system." (rev 1.35); `.drawer.sandboxHelp` "A sandbox workspace takes no inbound connection: Salesforce, Stripe and the directions Inbound and Both are not offered." (rev 1.43)

### 14.8 Sample world

| Tenant | Content |
|---|---|
| WLD-T-01 | "Salesforce orders" (Salesforce, Mock, Inbound, all entities, Active); "NetSuite GL" (NetSuite, Mock, Both: journals, chart-of-accounts sync, trial-balance pull). J-03.1 sync run: kind Webhook batch, source totals "<n> records · <amount>" (rev 1.20; ruling R-112 (h): T-INT-02 holds one count and the amounts by currency per side, not orders and lines; the amount of J-03.1 is USD 120,000.00), loaded identical, Result Reconciled |
| WLD-T-20 | "QuickBooks Online" (Mock, Outbound) with credential reference names; "Connection succeeded · <timestamp>" (asserted text prefix, J-01.13) |
| WLD-T-22 | Salesforce and Stripe mocks from `quayside-salesforce-scenario.json` and `quayside-stripe-scenario.json`: 3 orders including one duplicate webhook recorded once, one out-of-order version with warning `STALE_SOURCE_VERSION`, one 429 retried; product `SF-PROD-X99` raises `PRODUCT_UNMAPPED`; Stripe subscription `sub_DEMO0001` 1,200.00 per year (J-23) |

### 14.9 Test hooks, light and dark, accessibility

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Connections grid | `getByRole("grid", {name: "Integrations"})` | `SF-16-grid-connections` |
| Test result | `getByText(/^Connection succeeded · /)` | `SF-16-banner-test` |
| Sync runs grid | `getByRole("grid", {name: "Sync runs"})` | `SF-16-grid-sync-runs` |
| Control totals | `getByRole("table", {name: "Control totals"})` | `SF-16-grid-control-totals` |
| Connection row; connection drawer (rev 1.13) | row of the grid; dialog "Add connection" or "Edit connection" | `SF-16-row-<code>`; `SF-16-drawer-connection` |
| Panels (rev 1.13) | tab panels "Settings", "Sync runs", "External ids" | `SF-16-pane-settings`, `SF-16-pane-sync-runs`, `SF-16-pane-external-ids` |
| Run problem; run exceptions (rev 1.13) | banner with the problem title; table named "Exceptions" | `SF-16-banner-problem`; `SF-16-grid-exceptions` |

Light and dark: "Mock" outline chip `--border-default`; result chips per §0.8. Accessibility: the credential reference field's help is announced with the field; test results are inserted with `role="status"` (positive) or `role="alert"` (negative).

## 15. SF-12 Approvals

### 15.1 Summary

| Field | Value |
|---|---|
| Screen ids and routes | SF-12 `/approvals` (RT-54, "Waiting for me"); SF-12:submitted `/approvals/submitted` (RT-55); SF-12:all `/approvals/all` (RT-56); SF-12:request `/approvals/requests/:requestId` (RT-57; rendered inside the view that contains it: Waiting for me when `can_decide`, Submitted by me when the viewer is the preparer, otherwise All requests; `?view=` overrides); SF-12:delegations `/approvals/delegations` (RT-58) |
| Roles and permissions | Every member may open the inbox. Decisions need the active step's permission and SoD (SM-01); "Withdraw request" the preparer; delegations any approval permission |
| Purpose | One inbox for maker-checker: the changes, the impact preview, the evidence and the routing of every request, with a required comment, bulk approval and history (REQ-UX-012, REQ-UX-013; DS-CMP-16) |
| REQ | REQ-UX-012, REQ-UX-013, REQ-PLT-011 to REQ-PLT-017 |
| Journeys | J-01.5, J-01.7, J-01.9, J-01.11, J-01.15, J-01-AC-3; J-02.6, J-02.7, J-02-AC-7, J-02-ALT-1; J-03.9; J-04.3; J-05.5, J-05-ALT-2; J-06.5, J-06.6, J-06-ALT-1; J-07.4, J-07-AC-4; J-08.3; J-09.3; J-10.2, J-10.4; J-11.6; J-12.2; J-13 step 2; J-17.7; J-19.9; J-26.3 |

### 15.2 Wireframes

1440 px (J-02.6: `US-LIST 2026-H2` selected for `priya`):

<!-- WF:approvals-1440 -->
```text
+-------------------+--------------------------------------------------------------------------------------------------+
| eRev           [|]| [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search or run a command    Mod K]          Bell 3  ?  MC   |
|                   +--------------------------------------------------------------------------------------------------+
|                   | Approvals                                                                                        |
| Work              |  Waiting for me 3    Submitted by me    All requests    Delegations                              |
|    Home           |  ================                                                                                |
|    Contracts      | [Filter: Type v] (Entity is AVM-US x)                                  [Select for bulk approval]|
|    Schedules      |+----------------------------------+  +----------------------------------------------------------+|
|    Close          || 3 requests . oldest first        |  | APR-000231  SSP book version  (Pending approval)         ||
|    Journals       |||* SSP book version US-LIST 2026-H|  | Maya Chen submitted 12 Sep 2026 14:05 UTC                ||
|    Reports        |||* SSP book version . Maya Chen . |  | Steps: 1 SSP approval . waiting   2 SSP approval . waitin||
| ----------------  ||  Contract activation BG-AVM-0020 |  | "Observable standalone sales, Jan-Aug 2026"              ||
| Govern            ||  USD 146,000.00 . Maya Chen . 12 |  | Entries changed 1 . Unchanged 6 . Finding 1 warning      ||
| |* Approvals    3 ||  Manual adjustment BG-AVM-0022   |  | Change  Product       Field  Current     Proposed    Delt||
|    Policies       ||  USD 2,400.00 . Maya Chen . 12 Se|  |  ~      AVM-PLAT-100  Low    85,000.00   95,200.00   +10,||
|    Data           ||                                  |  |  ~      AVM-PLAT-100  Mid    100,000.00  112,000.00  +12.||
|                   ||                                  |  |  ~      AVM-PLAT-100  High   115,000.00  128,800.00  +13,||
|                   ||                                  |  | [ ] Show unchanged entries                               ||
|                   ||                                  |  | Comment (required) ____________________________________  ||
|                   ||                                  |  |                                        [Reject] [*Approve||
|                   ||                                  |  |                                                          ||
|                   ||                                  |  |                                                          ||
| Settings          |+----------------------------------+  +----------------------------------------------------------+|
+-------------------+--------------------------------------------------------------------------------------------------+
```
<!-- /WF:approvals-1440 -->

1280 px:

<!-- WF:approvals-1280 -->
```text
+----+---------------------------------------------------------------------------------------------------+
| e  | [AVM-US v|Sep 2026 Open v|ASC 606 v] [Search  Mod K]                         Bell 3  ?  MC        |
|    +---------------------------------------------------------------------------------------------------+
|    | Approvals                                                                                         |
| H  |  Waiting for me 3    Submitted by me    All requests    Delegations                               |
| Ct |+-----------------------+ +-----------------------------------------------------------------------+|
| Sc || 3 requests            | | APR-000231  SSP book version  (Pending approval)                      ||
| Cl |||* SSP book version    | | Maya Chen . 12 Sep 2026 14:05 UTC                                     ||
| Jn |||* US-LIST 2026-H2     | | AVM-PLAT-100 Mid 100,000.00 -> 112,000.00 (+12.0%)                    ||
| Rp ||  Contract activation  | | AVM-PLAT-100 Low 85,000.00 -> 95,200.00                               ||
| -- ||  BG-AVM-0020          | | Comment (required) ______________________________                     ||
| *Ap||  Manual adjustment    | |                              [Reject] [*Approve]                      ||
| Po ||  BG-AVM-0022          | |                                                                       ||
| Da ||                       | |                                                                       ||
|    ||                       | |                                                                       ||
| Se |+-----------------------+ +-----------------------------------------------------------------------+|
+----+---------------------------------------------------------------------------------------------------+
```
<!-- /WF:approvals-1280 -->

### 15.3 Master list

Route tabs "Waiting for me <n> · Submitted by me · All requests · Delegations". FilterBar: Type (E-08 labels below), Entity, Status (All requests only). Component DS-CMP-08 approvals variant; toolbar "Select for bulk approval" on Waiting for me (§15.5).

| View | Binding (API-R-09) | Order |
|---|---|---|
| Waiting for me | `GET /approvals?assigned_to_me=true&status=PENDING&entity&subject_type&sort=submitted_at` (04 API-R-09) | oldest first |
| Submitted by me | `GET /approvals?preparer=me&status&entity&subject_type&sort=-submitted_at` (04 API-R-09 `preparer`) | newest first |
| All requests | `GET /approvals?status&entity&subject_type&sort=-submitted_at` | newest first |

Row: line 1 `summary` and, at the end, `amount` as DS-FMT-05 ("USD 146,000.00") or nothing; line 2 subject type label · entity code · preparer · submitted date (DS-FMT-16) · status chip when not `PENDING` · outline flag chips from the catalogue `approvals.flag.<flag>` (rev 1.18; supervisor ruling R-104 (a)): `TREATMENT_OVERRIDE` "Treatment override"; `AI_ASSISTED` "AI assisted"; and the routing flags the API sets (04 T-PLT-17) — `ABOVE_THRESHOLD` "Above threshold"; `ABOVE_CONTROLLER_THRESHOLD` "Above Controller threshold"; `MANUAL_ENTRY` "Manual entry"; `NON_STANDARD_TERMS` "Non-standard terms"; `METHODOLOGY_CHANGE` "Methodology change"; `CATCH_UP_GE_50K` "Catch-up of USD 50,000.00 or more"; `TP_CHANGE_GE_250K` "Price change of USD 250,000.00 or more"; `POSTED_LINES` "Posted lines"; `PERIOD_IN_CLOSE` "Period in close"; and, since rev 1.70 (item ACT-FLAGS-1; 04 T-PLT-17 rev 1.287), the six flags a contract activation gained — `MATERIAL_RIGHT` "Material right"; `VARIABLE_CONSIDERATION` "Variable consideration"; `NEW_SKU` "New product"; `SIDE_LETTER` "Side letter"; `TERMS_NOT_STATED` "Terms not stated"; `RATE_NOT_PUBLISHED` "Rate not published". The booking form does not state the two terms of a booking yet (register index 261), so every contract a person books reads "Terms not stated" until it does. A flag without a catalogue entry is shown verbatim (a routing flag string from a rule output, for example "TP at or above USD 100,000.00").

Subject type labels (E-08): `SSP_BOOK_VERSION` "SSP book version"; `SSP_OVERRIDE` "SSP override"; `CONTRACT_ACTIVATION` "Contract activation"; `MODIFICATION` "Modification"; `MANUAL_EVENT` "Manual event"; `ESTIMATE_VERSION` "Estimate version"; `MANUAL_ADJUSTMENT` "Manual adjustment"; `REGISTRY_VERSION` "Policy version"; `RULE_SET_VERSION` "Rule set version"; `POB_TEMPLATE_VERSION` "Obligation template version"; `ACCOUNT_MAPPING_VERSION` "Account mapping version"; `FX_RATE_SET_VERSION` "FX rate set version"; `ROLE_CHANGE` "Role change"; `ROLE_ASSIGNMENT` "Role assignment"; `SOD_EXCEPTION` "Separation of duties exception"; `PERIOD_LOCK` "Period lock"; `PERIOD_REOPEN` "Period reopen"; `IMPORT_COMMIT` "Import commit"; `CONTRACT_VOID` "Contract void"; `COMBINATION_GROUP` "Contract combination"; `JUDGEMENT_RECORD` "Judgement record"; `JOURNAL_RUN` "Journal run"; `SUPPORT_GRANT` "Support access"; `AI_PROPOSAL_ACCEPTANCE` "AI proposal acceptance"; `PRINCIPAL_AGENT_CHANGE` "Principal or agent change"; `ATTRIBUTE_CHANGE` "Obligation attribute change"; `EXCEPTION_WAIVER` "Exception waiver"; `MIGRATION_PROMOTION` "Migration promotion"; `MAPPING_PROFILE_VERSION` "Mapping profile version"; `POLICY_OVERRIDE` "Policy override". Rev 1.15: `EVIDENCE_SHRED` "Evidence file shredding" (04 E-08 rev 1.142; its request view is the screen item *EVIDENCE_SHRED request view*, named and not built) and `MIGRATION_SSP_REPLAY` "Migration SSP replay" (04 E-08 rev 1.72, which this list had not named).

**As bound to API-R-09 of 1.0 (rev 1.20, WEB-16).** The FilterBar writes `f.type`, `f.entity` and `f.status` (SCR-URL-10) and sends them as `subject_type` (one value, the E-08 labels above), `entity` (the codes of entities in the member's scope, one or several, repeated; ruling R-64 (7) (d)) and `status` (one value of E-05; `VOIDED` reads "Stale or void", the two chips of that literal): the filters `GET /approvals` admits. Status is a chip of All requests only. The route has no search, so the bar holds chips only. The context pill's entity is not applied to the three lists, and its entity segment reads "Not used on this page" on the SF-12 family (§1.3; ruling R-112 (h)): API-R-09 matches a request to an entity by the entity it names or by its subject, so an applied entity would leave out every request without one (role changes, configuration versions, import commits) and "Waiting for me <n>" would disagree with the list under it — the reason §2.5 gives for the Home table "Waiting for you"; the member filters with the Entity chip. A member who cannot read the workspace structure (`config.read`) has no Entity chip. A request opened from a filtered list keeps the chips in its URL and the list beside it stays filtered; a filtered list without rows is SCR-ST-04 "No approval requests match these filters". The tab of the view on screen links to its own URL.

### 15.4 Request detail (DS-CMP-16)

| # | Region | Content and binding (`GET /approvals/{id}`, API-S-Approval) |
|---|---|---|
| 1 | Request header | `request_no` (mono); type label; status chip (§0.8); preparer avatar, name and `submitted_at` (DS-FMT-17); routing steps "<step name> · <decisions recorded> of <min_approvers> recorded" with approver, "on behalf of <delegator>" when delegated, decided at and comment; link "Open <subject label>" (`subject.href` mapped to its route). Rev 1.18 (supervisor ruling R-104 (a)): the link is rendered wherever `subject.href` is not null and names a route the client holds, and it opens that route; `<subject label>` is the record word of the route, each link a whole catalogue string (DS-I18N-01) — `/contracts/:contractId` "Open contract", `/journals/runs/:runId` "Open journal run", `/settings/products/:productId` "Open product", `/policies/accounting/:policyId` "Open accounting policy", `/data/exceptions/:exceptionId` "Open exception", `/settings/support-access` "Open support access", and "Open record" for any other route of §0.4 that the client holds. A `subject.href` that names no route of the client renders no link (at rev 1.18 the API sends `/close/periods/<id>` for a period lock or reopen and `/modifications/<id>` for a modification, which §0.4 does not define). `data-testid` `SF-12-subject-link` |
| 2 | SoD notice | Info banner: preparer "You submitted this request. Another approver must review it."; earlier approver "You approved an earlier step of this request. Another approver must decide this step."; no permission "You do not have approval rights for this request type." (DS-CMP-16) |
| 3 | Justification | A region headed "Justification" (`data-testid` `SF-12-justification`) with a quoted block: the comment the request was submitted with (rev 1.60: API-S-Approval `comment`, 04 rev 1.252). Rendered whenever the comment is not blank (rev 1.71): a request submitted without one, or with white space alone, has no such region. The request's `reason_code` is not shown here |
| 4 | Impact summary | DS-CMP-06 strip from `impact_preview.summary`: revenue in the context period (after, with "Before" secondary), balances changed, journal lines; "No impact on revenue or balances." for configuration without simulation deltas. Rev 1.18 (supervisor ruling R-104 (a)): that sentence is for a stored preview whose figures are all empty — a preview was computed and moves nothing. It is never shown for a request without a stored preview (`impact_preview` null — a judgement record, a journal run, a period lock), because nothing was computed there. Such a request shows the notice "No preview is stored for this request" (info banner, `data-testid` `SF-12-banner-no-preview`) with the message "Use the link above to open the record and read what you are approving before you decide." when region 1 holds the link, and "This screen does not show what the request changes, and it has no link to the record. Ask <preparer> what it changes, or open the record from its own screen, before you decide." when it holds none. A reader who does not decide the request (it is decided, or `can_decide` is false) reads "The link above opens the record this request is about." or "This screen does not show what the request changes, and it has no link to the record." instead. The notice is the stop-gap until the content rows of item APR-SUBJECT-CONTENT-1 fill regions 3 and 5. For the activation of a contract behind the not-a-contract gate (`impact_preview.summary.criteria_met` not null; rev 1.11; supervisor ruling R-61 (f)) the region "Criteria met" comes first: the sentence "Approving records that the contract criteria are met in the books below and activates the contract. Revenue for performance up to each date is recognised as a catch-up."; the table "Books that move", one row per `criteria_met[]` item — Book (book label), Criteria met on (`effective_date`, DS-FMT-16), Step 1 review ("<judgement no> · Reviewed by <reviewer>, <DS-FMT-17 timestamp>" of `judgement_record_id`, read from `GET /judgements?subject_type=contract&subject_id=<subject id>`), Catch-up (the item's `catch_up_total`, DS-FMT-01). The books are parallel ledgers, so their catch-ups are stated per book and not added; `impact_preview.summary.catch_up_total` is the primary book's figure (04 §16.10) and is not shown a second time. `data-testid` `SF-12-criteria-met` |
| 5 | Diff body | By subject (table below). Rev 1.18 (supervisor ruling R-104 (b)): the row "Revenue by period" of a stored preview carries the caption "The first six periods from <period label>; later periods are not listed." (04 API-S-ImpactSummary: six periods from the effective period), so that its sum is not read as the whole revenue; the captions "RPO at <date>" and "posted on approval, <period> to <period>" follow the members of item APR-SUBJECT-CONTENT-1. Enumeration values of a preview read their labels where the product has one: `status` of a `CONTRACT_ACTIVATION` or `CONTRACT_VOID` preview the §0.8 contract status word (E-17: "Draft" → "Active"), `account_role` the account role label; a value without a label is shown as the API sends it |
| 6 | Attachments | `attachments[]` links |
| 7 | Decision form | Sticky footer: "Comment (required)", minimum 10 characters; "Reject" (secondary) and "Approve" (primary); rendered only when `can_decide`. Rev 1.18 (supervisor ruling R-104; browser-QA finding on 1440 × 761): the footer covers the lower part of a pane that is taller than its viewport, so while content of the pane lies beneath it the footer's first row, at its upper edge, is the link button "More below" (CaretDown icon; `data-testid` `SF-12-more-below`; inside the footer, so that the cue covers nothing of the request), which scrolls the pane by one view and is not rendered at the end of the pane; the pane's `scroll-padding-block-end` is the footer's height (DS-A11Y-03), so a change row that takes focus with `N` or `Shift+N` is never under the footer. The same holds for the preparer's "Withdraw request" footer |

| Subject types | Diff body |
|---|---|
| `CONTRACT_ACTIVATION` | "New contract" view: contract meta; Step 1 criteria table (§4.1.3 row 1); obligations table (§4.1.3 row 2); allocation walk (§4.1.3.1); activation checklist results ("Passed" per item); revenue by period, balances and journal preview from the preview, with "No lines at activation." when empty (J-03.9) |
| `MODIFICATION` | Answers per obligation; treatments with overrides and the linked judgement; preview tables of §7.7. Rev 1.55 (PRD BR-MOD-02 rev 1.139; J-06 rev 1.158): the estimate versions and the judgement record created inside a modification are requests of their own, decided before the modification is submitted, so the pane lists no linked request that still waits; the list of linked requests with their statuses and the button "Open linked requests" are named and not built |
| `ESTIMATE_VERSION` | Field diff previous approved version → proposed (kind fields of §8.4), P&L impact by period (REQ-TP-005), evidence links |
| `SSP_BOOK_VERSION` | Field diff of version meta; grid diff of entries (DS-CMP-16) with Change chip, Product, Field, Current, Proposed, Delta (`mid_change_ratio` as percent for Mid, 04 API-R-26 diff); switch "Show unchanged entries"; range findings; study attachments |
| `IMPORT_COMMIT` | Import summary (template, file, SHA-256, counts); warnings; review tables of §12.2 step 4; affected records grid diff |
| `REGISTRY_VERSION`, `RULE_SET_VERSION`, `POB_TEMPLATE_VERSION`, `ACCOUNT_MAPPING_VERSION`, `MAPPING_PROFILE_VERSION`, `FX_RATE_SET_VERSION` | Field diff (`diff_against_current`) or grid diff of rules or rows; "<passed> of <total> tests passed"; simulation summary (§11.1) |
| `MANUAL_EVENT` | Event fields, evidence and preview figures (§4.9.3, §5.8) |
| `EVIDENCE_SHRED` (rev 1.15; screen item *EVIDENCE_SHRED request view*, named and not built) | The proposal of `impact_preview.after` (04 §16.10 rev 1.142): the file's name and SHA-256, one line per record that holds the file (`holds[].record`) and the requester's reason; no amount, no impact summary and no subject link (a file has no screen); the request's entities are those of the records that hold the file. Approving shreds the file |
| `MANUAL_ADJUSTMENT`, `JUDGEMENT_RECORD`, `COMBINATION_GROUP`, `SSP_OVERRIDE`, `ATTRIBUTE_CHANGE`, `POLICY_OVERRIDE`, `PRINCIPAL_AGENT_CHANGE`, `CONTRACT_VOID`, `EXCEPTION_WAIVER`, `AI_PROPOSAL_ACCEPTANCE` | Field diff of the subject, reason or rationale, attachments, subject link |
| `JOURNAL_RUN`, `PERIOD_LOCK`, `PERIOD_REOPEN`, `MIGRATION_PROMOTION`, `ROLE_ASSIGNMENT`, `ROLE_CHANGE`, `SOD_EXCEPTION`, `SUPPORT_GRANT` | The subject summary component that SCREENS_B defines on the subject's screen (journal totals and balance check; gate results; reopen reason and dual-approval count; reconciliation result; SoD check), rendered inside this pane |

**Decisions.**
- Approve: `POST /approvals/{id}/approve` with `subject_content_sha256 = subject.content_sha256`, `impact_preview_sha256 = impact_preview.sha256` when present, and `comment`. Step-up per SCR-PERM-05. Success: toast "Approved: <summary>.", the status chip and routing update, focus moves to the next request in the list, and the list count is announced.
- Reject: opens the confirmation (`role="alertdialog"`) titled "Reject <summary>?" with the description "The preparer is notified and the item returns to Draft." and the typed comment shown read-only; buttons "Cancel" (initial focus) and Danger "Reject request" → `POST /approvals/{id}/reject`; toast "Rejected: <summary>."
- Withdraw (preparer, Submitted by me): secondary "Withdraw request" → confirmation "Withdraw this request? The item returns to Draft and approvers are notified." with optional comment → `POST /approvals/{id}/withdraw`.
- Problems: `self-approval` ERR-02 "You prepared this item, so another user must approve it."; `approver-already-decided` ERR-03 "You approved an earlier step of this item. Another approver must decide this step." (J-06-ALT-1); `stale-approval` ERR-04: the chip becomes Stale, the decision form is removed, and a warning banner reads "Voided: this item changed after submission." with the message "The record changed after this request was submitted. The maker must resubmit it." (J-05-ALT-2; DS-CMP-16). Rev 1.31 (PRD ERR-75 at the decision; 04 §16.5): a `validation-failed` whose `errors[]` carry `rule_id = "REQ-POL-007"` keeps nothing of the decision, leaves the request pending and the form in place, and reads "This version replaces a published one and its effective date has been reached, so it can no longer be approved. Reject the request, or ask <preparer> to withdraw it: the version can then be given a later date and submitted again." The approver has no date to change, so neither the author's sentence of ERR-75 nor the title "Check the highlighted fields" is shown; the result of a bulk approval (§15.5) shows the same sentence as the item's detail under the title "Effective date reached".
- Content withheld (rev 1.32; 04 §16.10 rev 1.208 "Content of a request", API-S-Approval `content_withheld`; item APR-CONTENT-SCOPE-1): a request that names several legal entities is listed for a reader who covers one of them, and what it would put in force is shown only to a reader who covers every one. When `content_withheld` is true the pane shows region 1 — `request_no`, the type label, the status chip, the preparer, the routing steps with who decided and when, and a decision's comment wherever the API sends one — and the summary as the API sends it, which is then the type label and the request number. In place of regions 4 to 6 (rev 1.60; rev 1.32 said 3 to 6: region 3 is rendered whenever the API sends the submission comment, which for a withheld request it sends to the preparer alone) it shows one info banner (`data-testid` `SF-12-banner-content-withheld`) titled "You see part of this request" with the message "This request names legal entities outside your access. Its summary, amount, impact preview, attachments and the approvers' comments are shown to people whose access covers every entity it names. An approver's comment on a rejection is also shown to the person who submitted the request." The decision form is not rendered (`can_decide` is false), and the preparer's "Withdraw request" stays. The link of region 1 is rendered as for any request; the record behind it answers "not found" where the reader does not cover its entity. In the lists of §15.3 such a row shows the same summary and "—" for the amount, and sorts by amount as a request without one. Restated in rev 1.48 (item W-12d; the supervisor's rulings of 2026-10-01): the pane renders a decision's comment whenever the API sends one and holds no rule of its own about who reads which — with a withheld request the API sends at most the comment of a rejection, to the request's preparer, which the third sentence of the banner's message says; and of the notices of region 2 the preparer's and the earlier approver's stay, while "You do not have approval rights for this request type." is not rendered for a withheld request, because the reader may hold the right and lack an entity, and the banner says why nothing is decided here. The entities line of region 1 is rendered as the API sends it.
- Impact preview unavailable (rev 1.9; REQ-PLT-015): a request is approved on the preview its approver read. When the stored preview cannot be loaded — `GET /files/{impact_preview.file_id}/content` does not answer, or the file holds no preview document — region 5 shows, in place of the diff, a warning banner titled "The impact preview could not be loaded" with the message "Approve is unavailable until the preview loads. Reload the page, or reject the request." and the link "Retry", which reads the preview again. "Approve" is unavailable (DS-CMP-20: `aria-disabled` with the reason "Approve is unavailable until the impact preview loads.") while the preview has not loaded and for as long as it cannot be loaded; "Reject" stays. The API refuses the same approval with 409 `invalid-transition` (04 API-R-09), so the state is never the control.
- Keyboard: `N` and `Shift+N` move between changes in the diff; `Mod Enter` in the comment does not submit (DS-CMP-16).

### 15.5 Bulk approval

On Waiting for me, "Select for bulk approval" switches the master pane to a DS-CMP-10 grid with a checkbox column: Request, Type, Currency, Amount, Preparer, Submitted; "Exit bulk selection" returns to the list. Selection bar: "<n> selected" and the primary "Approve <n> items" (J-04.3 "Approve 2 items"; rev 1.55: the example of J-06.5 is withdrawn — the requests of a change order are decided one after the other, PRD J-06 rev 1.158). The modal (DS-CMP-11 form, `--modal-w-lg`) titled "Approve <n> items" lists the items (Request, Type, Impact summary line, Amount), a "Comment (required)" field (minimum 10 characters) and the checkbox "I reviewed the changes and impact of every selected item." Primary "Approve <n> items" → `POST /approvals/bulk-approve` with each item's hashes (REQ-PLT-017). Result modal "Approved <m> of <n> items" with a failures table (Request, Problem title, Detail). Step-up MFA once before the command.

**As bound to API-R-09 of 1.0 (rev 1.20, WEB-16).** The toolbar button writes `layout=bulk` on RT-54 (SCR-URL-18) and closes a request open in the detail pane; "Exit bulk selection" removes it. The grid "Requests waiting for me" takes the place of the master list and the detail pane and reads Waiting for me with the view's chips, oldest first, 200 rows a page; Request shows the request number and the summary. Only loaded rows are selected: an item sends the hashes of its own row (`subject.content_sha256`, and `impact_preview.sha256` when the request has a preview), and the command takes 1 to 200 items — above 200 the action is unavailable with "Select at most 200 items." The modal is a DS-CMP-11 dialog at `--modal-w-lg`. "Impact summary line" states what `impact_preview.summary` holds, without arithmetic: "Catch-up <amount>" when the preview names a catch-up total, "Revenue in <n> periods" and "<n> journal lines" by the entries it lists, "Figures in the impact preview" when it holds only other figures, and "No impact on revenue or balances." when it holds none or the request has no preview. "Approve <n> items" without a comment of 10 characters or without the statement shows "Enter at least 10 characters." and "Confirm that you reviewed every selected item." and sends nothing. A 403 `mfa-step-up-required` arrives before any item is decided: the step-up dialog opens once and the command is sent again with the same key (SCR-PERM-05). When every item is approved the modal closes with the toast "Approved <n> items." (DS-CMP-11: success is a toast, never a modal); when an item is refused, the result dialog "Approved <m> of <n> items" lists each refusal under the caption "Requests that were not approved" — Request, Problem (the problem's title), Detail (its detail and field messages) — with the one action "Done". Either way the grid is read again and the selection ends.

### 15.6 States

| View | Empty copy | Other |
|---|---|---|
| Waiting for me, approver | Title "No requests waiting for you"; description "Requests you can approve appear here, oldest first." | Nothing selected "Select a request to review its changes, impact and routing." |
| Waiting for me, no approval permissions | Title "You have no approval permissions"; description "Items you can view appear in reports and registers." (J-17.7) | none |
| Submitted by me | "You have not submitted any requests." | none |
| All requests | "No approval requests yet." | none |
| Request detail | Loading skeletons per region; not found "Approval request not found" | Error SCR-ST-05 "Could not load the request"; impact preview unavailable: the warning banner of §15.4 with "Approve" unavailable (rev 1.9) |

### 15.7 Delegations (SF-12:delegations)

DataGrid (`GET /approval-delegations`, T-PLT-21 columns): Delegate (user); Permissions (labels of approval permission codes); Valid from; Valid to (DS-FMT-16); Reason; Status ("Active", "Revoked", "Expired"); Created at. Primary "New delegation" drawer: Delegate (user combobox; excludes the viewer); Permissions (checklist of the viewer's approval permissions); Valid from; Valid to; Reason (minimum 10 characters). Validation "A delegation lasts at most 90 days." (BR-PLT-07). Row action "Revoke delegation" (confirmation with reason → `POST /approval-delegations/{id}/revoke`). Creating and revoking a delegation are access administration (rev 1.9; PRD BR-PLT-06, BR-PLT-07): both commands ask for the step-up confirmation of SCR-PERM-05 — 403 `mfa-step-up-required` opens the ERR-28 dialog and the command is sent again after the code — and the screen is reached only by a session whose second factor is verified (REQ-PLT-005). Empty: "No delegations. Delegate approval permissions for up to 90 days when you are away."

**As bound to API-R-09 of 1.0 (rev 1.20, WEB-16).** The page is the Approvals header with its route tabs, then the grid; the Delegations tab renders for a holder of an approval permission (RT-58), and a member without one who opens the route sees SCR-PERM-01 "delegations", "an approval permission". `GET /approval-delegations` answers the delegations a member gave and received, so the grid adds the column Delegator after Delegate; it sorts by Valid from, Valid to and Created at, newest first by default. T-PLT-21 stores no status: "Revoked" when `revoked_at` is set, "Expired" when `valid_to` has passed, "Not started" while `valid_from` is ahead, otherwise "Active", against the browser's clock at the time the page was read. "Valid from" (today by default) and "Valid to" are dates sent as whole days of platform time — 00:00:00Z of the first, 23:59:59Z of the last (DS-I18N-08) — so "Valid to" is at most 89 days after "Valid from"; "Valid to" before "Valid from" reads "Choose a date on or after Valid from." The Delegate choices are the active members the delegation command would accept as a delegate, other than the viewer — membership id, display name and email — read from `GET /approval-delegations/delegates?q=`, which is open to every holder of an approval permission, so "New delegation" opens for every member who sees the screen (ruling R-112 (g); lane API-GAPS G-2 (h)). **Interim, until that read is on main:** the choices are the active members other than the viewer read from `GET /users` (API-R-05), which needs `user.manage`; for a member without it "New delegation" is `aria-disabled` with the reason "Choosing a delegate needs the member directory, which your roles do not include." Permissions are labelled with the T-PLT-11 descriptions (catalogue `approvals.permission.<code>`); at least one is selected ("Select at least one permission."). The drawer's primary is "Create delegation" and its toast "Delegated to <delegate> until <date>."; the API's findings are shown on their fields. "Revoke delegation" renders on a delegation the member gave that is Active or Not started — the delegator alone revokes; its confirmation is titled "Revoke the delegation to <delegate>?", describes "<delegate> can no longer approve on your behalf. Decisions already recorded stay as they are.", takes a reason of at least 10 characters and ends with the toast "Revoked the delegation to <delegate>." The empty state is DS-CMP-23: title "No delegations", description "Delegate approval permissions for up to 90 days when you are away.", and "New delegation" where the member may open it.

**The limits of a delegation (rev 1.27; PRD BR-PLT-07 rev 1.118; supervisor rulings R-111 (2) and (4)).** "Valid to" is at most 89 days after TODAY, whatever "Valid from" is — the API admits no end later than 90 days after the command — so the picker's bound follows today, and the API's finding on the field reads "A delegation ends within 90 days of today." The API's other findings stay on their fields: on Delegate, "Choose a member who has set up multi-factor authentication." for a member without a confirmed second factor — the Delegate choices of `GET /approval-delegations/delegates` are the members the command accepts, so that read leaves such a member out, and under the interim read from `GET /users` the finding appears on submit; on Permissions, the ERR-22 line of a separation-of-duties conflict (409 `sod-conflict`, `errors[].field` `permissions[i]`). For an access administrator — a holder of `role.manage` — `GET /approval-delegations` answers, beside the delegations they gave or received, the ones they may end: every delegation of the workspace for an administrator of all entities, and for an administrator of named entities those whose delegator's access lies within their own, nothing else (rev 1.57; item DELEG-LIST-SCOPE-1). "End delegation" renders on each that is Active or Not started and that the administrator did not give ("Revoke delegation" stays on their own): its confirmation is titled "End the delegation from <delegator> to <delegate>?", describes "<delegate> can no longer approve on behalf of <delegator>. Decisions already recorded stay as they are.", takes a reason of at least 10 characters, asks for the step-up and ends with the toast "Ended the delegation from <delegator> to <delegate>."; 403 `forbidden` with rule `T-PLT-10` — the delegator's access reaches beyond the administrator's — shows its detail in the dialog; the list holding what the administrator may end and what they gave or received, that refusal remains for one row, a delegation they received from a delegator beyond their entities. A delegation that ended because its delegator lost the permission or the membership reads "Revoked" like any other (`revoked_at` is set; the audit log names the cause, `approval_delegation.end`). Until SF-12:delegations binds this paragraph the grid shows an administrator the further rows without the action.

### 15.8 Copy keys

`approvals.title` "Approvals"; `.tabs.waiting` "Waiting for me"; `.tabs.submitted` "Submitted by me"; `.tabs.all` "All requests"; `.tabs.delegations` "Delegations"; `.selectBulk` "Select for bulk approval"; `.approveN` "Approve {count} items"; `.comment.label` "Comment (required)"; `.approve` "Approve"; `.reject` "Reject"; `.reject.confirm.title` "Reject {summary}?"; `.withdraw` "Withdraw request"; `.sod.preparer` "You submitted this request. Another approver must review it."; `.stale.title` "Voided: this item changed after submission."; `.preview.unreadable.title` "The impact preview could not be loaded"; `.preview.unreadable.message` "Approve is unavailable until the preview loads. Reload the page, or reject the request."; `.approve.needsPreview` "Approve is unavailable until the impact preview loads." (rev 1.9); `.bulk.exit` "Exit bulk selection"; `.bulk.reviewed` "I reviewed the changes and impact of every selected item."; `.bulk.approved` "Approved {count} items."; `.bulk.result.title` "Approved {approved} of {count} items"; `.noResults` "No approval requests match these filters"; `.delegations.new` "New delegation"; `.delegations.revoke` "Revoke delegation"; `.delegations.limit` "A delegation lasts at most 90 days."; `.delegations.empty.title` "No delegations"; `.delegations.empty.description` "Delegate approval permissions for up to 90 days when you are away." (rev 1.20, WEB-16)

### 15.9 Sample world

| Journey or seed | Content (asserted where cited) |
|---|---|
| Seed, `priya` Waiting for me | WLD-B-01 "Contract activation BG-AVM-0020" USD 146,000.00; WLD-B-02 "Manual adjustment BG-AVM-0022" USD 2,400.00 (J-13 rejection comment "Attach the customer acceptance before resubmitting."); WLD-B-03 "Judgement record BG-AVM-0023" topic Principal or agent |
| J-02.6, J-02.7 | "SSP book version US-LIST 2026-H2"; two steps; grid diff AVM-PLAT-100 Low 85,000.00 → 95,200.00, Mid 100,000.00 → 112,000.00 (+12.0%), High 115,000.00 → 128,800.00, others Unchanged; Priya's comment "Supported by H1 standalone sales."; Marcus approves step 2 |
| J-02-ALT-1 | Draft `2026-H2b` rejected with "Range too wide." |
| J-03.9 | "Contract activation SF-ORD-20417" with flag "TP at or above USD 100,000.00"; new contract view; "No lines at activation." |
| J-04.3 | Bulk "Approve 2 items" for the two AVM-DE imports, each with its own preview snapshot |
| J-05-ALT-2 | Priya sees chip Stale and "Voided: this item changed after submission." |
| J-06.3 to J-06.6, J-06-ALT-1 (rev 1.55; PRD rev 1.158 and 1.164) | "Estimate version" request for EAC version 2, two steps — Priya, then Marcus; the judgement record `CONSTRAINT`, which Priya reviews; "Estimate version" request for bonus version 2, two steps again — each estimate request because its P&L impact is USD 50,000.00 or more; then the "Modification" request, two steps; Priya's attempt on its step 2 shows "You approved an earlier step of this item. Another approver must decide this step." |
| J-01-AC-3 | Maya's own import on Submitted by me is read-only with the preparer notice and no Approve action |
| J-17.7 | Hannah: "You have no approval permissions" |
| J-26.3 | "Contract void BG-AVM-0030": two steps, Priya then Marcus |

### 15.10 Test hooks, light and dark, accessibility

| Element | Accessible locator | `data-testid` |
|---|---|---|
| Inbox list | `getByRole("listbox", {name: "Approval requests"})` | `SF-12-grid-requests` |
| Request option | `getByRole("option", {name: /US-LIST 2026-H2/})` | `SF-12-row-us-list-2026-h2` |
| Diff | `getByRole("table", {name: /^Proposed changes/})` or grid "Changed entries" | `SF-12-diff` |
| Decision form | `getByRole("form", {name: "Decision"})`; `getByLabel("Comment (required)")`; buttons "Approve", "Reject" | `SF-12-decision-form` |
| Bulk modal | `getByRole("dialog", {name: /^Approve \d+ items$/})` | `SF-12-dialog-bulk-approve` |
| SoD notice | `getByText("You submitted this request. Another approver must review it.")` | `SF-12-banner-sod` |
| Filter bar (rev 1.20) | toolbar "Filters" | `SF-12-filter-bar` |
| Bulk grid (rev 1.20) | `getByRole("grid", {name: "Requests waiting for me"})` | `SF-12-grid-bulk`; rows `SF-12-row-<request no>` |
| Bulk result (rev 1.20) | `getByRole("dialog", {name: /^Approved \d+ of \d+ items?$/})` | `SF-12-dialog-bulk-result` |
| Delegations grid (rev 1.20) | `getByRole("grid", {name: "Delegations"})` | `SF-12-grid-delegations`; empty `SF-12-empty-delegations` |
| New delegation (rev 1.20) | `getByRole("dialog", {name: "New delegation"})` | `SF-12-drawer-delegation` |
| Revoke confirmation (rev 1.20) | `getByRole("alertdialog", {name: /^Revoke the delegation to /})` | `SF-12-dialog-revoke` |

Light and dark: diff tints `--diff-removed-bg` and `--diff-added-bg` with markers and screen-reader prefixes (C52 to C54); the sticky decision footer sits on `--bg-surface` with a hairline. Accessibility: the diff table caption "Proposed changes (<n>)"; decision outcomes announced through the toast and the chip change; the bulk grid is APG Grid with `aria-multiselectable="true"`.

## 16. Open questions for supervisor

D-76 resolved every question below and adopted every row of table 16-A (revision 1.2). The Status column records each ruling and where it is applied. Revision 1.2 raises no question (D-77); build gaps become Spec questions in `PROGRESS.md`.

| # | Question | Recommended default | Status |
|---|---|---|---|
| OQ-S-01 | REQ-UX-004 names eight workbench tabs (Obligations, Schedules, Billing, Journals, Modifications, Documents, History, Audit); the SCREENS brief caps the tabs at seven and adds an Estimates workbench. | Seven route tabs: Obligations, Estimates, Schedules, Billing, Journals, Modifications, History. "Documents" is the header "Documents <n>" drawer (§4.8); "Audit" is the History tab "Audit trail" view (§4.7). Amend REQ-UX-004 to name these placements. | Resolved by D-76: SCREENS placement governs and REQ-UX-004 is amended to match; SCR-IA-02 and §4.1 stand |
| OQ-S-02 | REQ-UX-004 lists eight KPI figures; DS-CMP-06 allows six cells. | Six cells; the sixth, "Contract liability", carries contract asset and unbilled receivable in its secondary line, each an Explain trigger (§4.1.4). | Resolved by D-76: REQ-UX-004 is amended to match; §4.1.4 stands |
| OQ-S-03 | The screens need read-model fields and a few commands that 04 §15.3 and §16 do not define (table below, rows R-01 to R-40). | 04 adopts every row as written; until then the build blocks the dependent regions under DG-READ-04 rather than inventing fields. | Resolved by D-76: 04 rev 1.2 adopted every row (table 16-A column "04 rev 1.2"). The bindings cite the 04 ids, and fields 04 does not return are marked "deferred to later" |
| OQ-S-04 | API-R-28 accepts `quick_list` but 04 lists no literals. | `RECENTLY_VIEWED`, `ON_HOLD`, `LARGEST_VALUE`, `MODIFIED_THIS_PERIOD`, `CREATED_MANUALLY`, `CREATED_FROM_INTEGRATIONS_THIS_PERIOD` (§3.4). | Resolved by D-76: 04 E-111 `contract_quick_list`; §2.5, §3.4 |
| OQ-S-05 | DS-CMP-18 defines the stepper for imports only; the modification wizard and configuration lifecycles need the same anatomy. | DESIGN_SYSTEM notes that DS-CMP-18's stepper anatomy (markers, captions, completed-step links, ARIA) applies to any multi-step flow; import-specific content stays with imports. | Resolved by D-76: DESIGN_SYSTEM rev 1.2 DS-CMP-18 "Scope of the anatomy" |
| OQ-S-06 | DS-CMP-18 makes staging rows inline-editable and offers "Save mapping as preset" on the Map step, but 04 T-IMP-03 rows are written once ("a corrected file is a new upload") and API-S-ImportCreate takes only a published mapping profile. | Follow 04: no inline edit of staging rows; "Download error report" and "Upload a corrected file"; the Map step reports header matching and mapping profiles are authored on SF-10:templates. DESIGN_SYSTEM revises DS-CMP-18 accordingly. | Resolved by D-76: DESIGN_SYSTEM rev 1.2 DS-CMP-18 removes inline editing and "Save mapping as preset"; §12.2 stands |
| OQ-S-07 | E-12 separates `APPROVED` from `PUBLISHED`, and API-C-13 has a `publish` command, while PRD J-01.5 shows approval producing `PUBLISHED`. | The approval executes publication with the effective date set before submission (BR-PLT-04 subject command); the UI renders no Publish button; API clients may still call `publish` on an `APPROVED` version. | Resolved by D-76: 04 §16.5 publish note; §11.0 |
| OQ-S-08 | Home figures are portfolio aggregates without an `/explain` node, while PP-07 says every computed figure opens Explain. | Home values drill to the screen that owns the figure (J-16.1), where each cell opens Explain; Home KPI buttons are drill links, not Explain triggers. | Resolved by D-76: default adopted; §2.6 stands |
| OQ-S-09 | DG-FE-02 says each route object's `id` is its SF id, but several screens share an SF id. | Primary route `id = "SF-nn"`; secondary `id = "SF-nn:<slug>"`; `handle = {sf, screen, titleKey}` (SCR-IA-06). Amend DG-FE-02. | Resolved by D-76: dev-guide DG-FE-02 amended; SCR-IA-06 stands |
| OQ-S-10 | PRD §3 places SF-27 About in the user menu; DS-CMP-01 lists "About eRev Cloud" in the Help menu. | Help menu (DS-CMP-01 ranks for placement); PRD §3 placement text updated. | Resolved by D-76: PRD §3 SF-27 amended |
| OQ-S-11 | PRD SF-28 Revenue Q&A is a top-bar placement, but DS-CMP-01 lists no top-bar trigger for it. | Ghost icon button "Ask about revenue" (Sparkle, AI component directory) between the read-only chip and the bell, rendered when AI is enabled and the user holds `ai.use`; DS-CMP-01 amended. | Resolved by D-76: DESIGN_SYSTEM DS-CMP-01 item 6; §1.1 reads `tenant_settings.ai_enabled` |
| OQ-S-12 | DS-CMP-19 has no words for several 04 literals (for example Completed, Applied, Committed, Tested, Published, Superseded, Open, Waived). | Adopt the "proposed" rows of §0.8 (and SCREENS_B §0.4) into DS-CMP-19 with the tones and icons given. | Resolved by D-76: DESIGN_SYSTEM rev 1.2 DS-CMP-19 adds the words; the markers are removed from §0.8 |
| OQ-S-13 | DS-CMP-17 labels step 3 "Price"; REQ-UX-015 and PRD J-03.2 say "Transaction price". | "Transaction price" (03 ranks above DS); DS-CMP-17 example text updated. | Resolved by D-76: DESIGN_SYSTEM DS-CMP-17 step 3 "Transaction price" |
| OQ-S-14 | DataGrid totals must come from the API (DS-FMT-02), but list endpoints return no totals. | No totals row on SF-02, SF-03:schedules, SF-03:journals or SF-10; totals appear on report screens (SCREENS_B). Add list totals later if requested. | Resolved by D-76: default adopted |
| OQ-S-15 | REQ-UX-017 favourites have no dedicated table; T-PLT-37 `saved_view` has `is_favourite` and free `config`. | Favourites are `saved_view` rows with `is_favourite = true` and `config = {target, path, label}` (SCR-IA-08). | Resolved by D-76: 04 T-PLT-37 note; SCR-IA-08 |
| OQ-S-16 | SF-02 bulk commands have no bulk endpoints. | The client commands items one at a time with their own `Idempotency-Key`, at most 200 per action, and reports per-item results (§3.7). | Resolved by D-76: default adopted; §3.7 stands |
| OQ-S-17 | `POST /contracts/{id}/request-void`, `POST /periods/{id}/request-reopen`, `/cancel-close` and `POST /events/{id}/request-void` require `reason_code`, but 04 defines no literal set. | 04 adds enum `reason_code` with `DUPLICATE`, `CREATED_IN_ERROR`, `CUSTOMER_CANCELLED`, `DATA_CORRECTION`, `ESTIMATE_CORRECTION`, `OTHER`; labels "Duplicate", "Created in error", "Customer cancelled", "Data correction", "Estimate correction", "Other". | Resolved by D-76: 04 E-110 with the per-command subsets of table 3.4-R (union with SCREENS_B OQ-B-06); §4.9.6 |
| OQ-S-18 | SCREENS_B RV-04 gives `snapshot` the value `period_lock.id` on report screens; SCR-URL-06 said lock snapshot id, and workbench reads have no lock parameter. | `snapshot` = `period_lock.id` everywhere; report screens pass it as `period_lock_id`; workbench and list screens translate it to `known_at` = the lock's `created_at` (SCR-URL-06 as amended in this revision). | Resolved by D-76: 04 API-C-10 note; SCR-URL-06 stands |
| OQ-S-19 | Customers and products carry PRD SF-15 REQ ids, so they sit under Settings, although accountants reach them from contracts. | Keep them under Settings › Reference data (SCR-IA-03); link customer and product names from every contract surface to their pages. | Resolved by D-76: default adopted |
| OQ-S-20 | DS-CMP-08 enumerates four master-detail variants; the estimates workbench and approval delegations reuse the pattern. | Treat the DS-CMP-08 variant list as examples; no new visual pattern is introduced. | Resolved by D-76: DESIGN_SYSTEM DS-CMP-08 variants are examples |
| OQ-S-21 | T-IMP-05 stores a `title` per exception item, but no document fixes title copy per §15.4 code. | A catalogue `finding.<code>.title` shared by the API and the UI; §13.5 fixes the sample-world titles; the other codes use the first clause of their IMP message until the catalogue is completed. | Resolved by D-76: 04 T-IMP-05 `title` from `finding.<code>.title`; §13.5 |

**Table 16-A API read-model and command gaps (OQ-S-03).** Every row was adopted by 04 rev 1.2 (D-76). Table 16-B gives the 04 ids that each row became; the bindings of this file cite those ids.

| Row | Needed by | Proposed 04 addition |
|---|---|---|
| R-01 | §1.4 | `GET /search?q=&scope=&limit=&cursor=` returning `{scope, items: [{id, primary, secondary, status, href}]}` per scope (`contracts`, `customers`, `invoices`, `obligations`, `journals`); permission-filtered |
| R-02 | §2 | API-S-DashboardHome for `GET /dashboard/home`: `context {entity, book, period {period_key, name, end_date}, currency, known_at}`; `revenue {current, prior, change_ratio, trend: [{period_key, recognized}]}`; `contract_liability {closing, opening}`; `rpo {total, within_12_months}`; `pending_approvals {count, oldest_submitted_at}`; `open_exceptions {total, blocking, warning, info}`; `close {state, blockers, close_run}` (API-S-Period shapes); `revenue_chart {periods: [{period_key, recognized, scheduled}], awaiting_trigger, pending_trigger_count}` |
| R-03 | §2, §13, §15 | Sort keys: approvals `submitted_at`, `-submitted_at`, `amount`; exceptions `severity` (Blocking, Warning, Info, then `created_at`), `created_at`, `-created_at` |
| R-04 | §15.3 | Approvals filter `preparer` (`me` or membership id) |
| R-05 | §4.1.3, §4.9.8 | `API-S-Contract.steps[]`: `{step: CONTRACT|OBLIGATIONS|TRANSACTION_PRICE|ALLOCATION|RECOGNITION, state: COMPLETE|NEEDS_ATTENTION|BLOCKED|IN_REVIEW|NOT_STARTED, status_code, detail}` with `detail.enforceable_term`, `detail.financing_note`, `detail.recognized_ratio`, `detail.obligations[].next_trigger`; activation checklist item codes `MANDATORY_FIELDS`, `SOURCE_REFERENCE`, `PRODUCT_TEMPLATE_SSP`, `DISTINCT_REVIEW`, `COMBINATION_SUGGESTIONS`, `JUDGEMENT_RECORDS`, `STEP1_RECORD` in `errors[].rule_id`; `GET /contracts/{id}/activation-checklist` (evaluate without storing) |
| R-06 | §4.1.3.1, §5.6 | Allocation walk lines and `API-S-Obligation.ssp` add `range_position` ∈ `INSIDE`, `BELOW`, `ABOVE` and the resolved POL-072 value |
| R-07 | §4.1.4, §5.5 | `API-S-Contract.kpis_ratios {billed, recognized, pending_trigger_count}`; `API-S-Obligation.ratios {recognized, scheduled, awaiting_trigger}` (Decimal strings, of transaction price or allocation) |
| R-08 | §4.1.3, §4.9.7 | `GET /combination-suggestions?contract=`; `POST /combination-suggestions/{id}/dismiss` with `rationale` |
| R-09 | §4.1.7 | `GET /jobs?subject_type=&subject_id=` |
| R-10 | §4.3, §4.4, §4.5 | Schedule lines add `obligation_key`; API-R-35 filter `schedule_kind`; subledger lines add `period_key`, `origin_period_key`, `journal_run_id`, `gl_account {code, name}` |
| R-11 | §4.3 | Cost asset list items add `period_amortization` for the `period` parameter |
| R-12 | §4.4 | `GET /contracts/{id}/usage-commitments?period=` returning `{period_label, commitment, usage_amount, usage_quantity, metric, shortfall, status, status_date}`, where the 04 literals `status` ∈ {`IN_PROGRESS`, `MET`, `SHORTFALL`} map to the DS-CMP-19 chip words "In progress", "Met" and "Shortfall" (rev 1.3; 04 B3-D13) |
| R-13 | §4.6, §7.7 | `API-S-Modification.impact_preview` summary of §7.7 and list item `impact_summary.catch_up_total` |
| R-14 | §4.7 | `GET /contracts/{id}/history` items `{occurred_at, kind: EVENT|CALCULATION|APPROVAL|IMPORT, actor, summary_key, params, links}` |
| R-15 | §4.8 | `GET /attachments?contract_id=` spanning the contract's events, estimates and modifications |
| R-16 | §4.9, §5.8, §8.4 | `POST /contracts/{id}/events/preview` and `POST /estimate-versions/{id}/preview` (202 job; result = the §7.7 summary shape) |
| R-17 | §4.9.2 | `POST /contracts/{id}/obligations/{obligation_key}/distinct-review` storing the 25-19 / 25-21 rationale (REQ-POB-001) |
| R-18 | §4.10 | `POST /contracts/{id}/replace-draft` (API-S-ContractCreate body) allowed while `DRAFT` |
| R-19 | §6.3 | `API-S-Explain.history[] {contract_version_id, version_no, known_at, value, delta, cause, estimate_version_pair, origin_period_key}` |
| R-20 | §6.3, §6.4 | `POST /explain/{object_type}/{id}/{measure}/verify` returning `{recomputed_value, stored_value, matches}` |
| R-21 | §6.5 | `GET /calc-traces/{id}` returning the full DAG (T-ENG-03) |
| R-22 | §6.6 | `GET /source-records/{id}` with API client, idempotency key, request id, payload SHA-256 and redacted payload |
| R-23 | §7.5 | `POST /modifications/{id}/classify` response `prefill_reasons` per obligation and question |
| R-24 | §8 | Estimates list `current_version`, `latest_version` summaries; versions add `approver`, `approved_at`; variable consideration `excluded_amount`; estimated total costs `costs_incurred_to_date`, `progress_ratio` |
| R-25 | §5.6 | `API-S-Obligation.material_right.status` ∈ `OPEN`, `EXERCISED`, `EXPIRED` with `status_date` |
| R-26 | §5.8 | `POST /obligations/{id}/request-ssp-override` (`ssp_book_version_id`, `justification`; subject `SSP_OVERRIDE`) |
| R-27 | §12.2, §6.6 | Import rows filters `row_number`, `sheet_name`, `code`, `status`; `sort=status` |
| R-28 | §9, §10 | Customers filter `is_active`; customers and products `sort` keys `code`, `name`, `updated_at`; related-party groups `member_count` |
| R-29 | §11.1, §11.2 | Template and rule set list items add `current_version` and `latest_version` summaries (version no, status, effective from, rule count, lint status) |
| R-30 | §11.1, §11.2 | Rules upsert by `rule_key` on `POST /rule-set-versions/{id}/rules`; generic test cases `GET, POST /config-test-cases?subject_type=&subject_id=` for templates, mappings and registry versions |
| R-31 | §11.1, §11.3, §11.6 | Configuration versions expose `impact_simulation.summary {contracts_affected, revenue_delta_by_period[], balance_delta[], journal_delta[]}` |
| R-32 | §11.3 | Registry parameters add `section` (POLICIES §1.1 to §1.14 title) |
| R-33 | §11.4, §15.4 | SSP version diff changed items add `mid_change_ratio` |
| R-34 | §11.5 | Calculator results add `inside_count`; `GET /ssp-calculator-runs/{id}/observations` (date, source reference, customer, quantity, unit price, in band, exclusion reason) |
| R-35 | §11.6 | Account mapping list items add `rule_count` |
| R-36 | §12.2 | `API-S-Import.finding_counts[] {code, severity, rows}` and `header_match[] {source_column, samples, template_field, match}` |
| R-37 | §12.2 | `GET /imports/{id}/error-report` (CSV: row, column, rule id, message) |
| R-38 | §12.2 | `GET /imports/{id}/diff` schema `{summary_counts, items: [{change: ADDED|CHANGED, contract_external_id, obligation_key, measure, before, after}]}` |
| R-39 | §13, §14.5 | Exception items add `available_actions[]` (`ASSIGN`, `REPROCESS`, `RESOLVE`, `REQUEST_WAIVER`, `DISMISS`) and `dismiss_blocked_reason`; filters `import_upload_id`, `sync_run_id`; `sort` per R-03 |
| R-40 | §14 | Connections add `last_sync_run {status, finished_at, result}`; `GET /sync-runs?connection=`; sync runs add `duration_seconds`; `GET /external-ids?connection=` |

**Table 16-B Adoption of table 16-A by 04 rev 1.2 (D-76).**

| Row | 04 rev 1.2 | Applied in |
|---|---|---|
| R-01 | API-R-55, API-S-SearchResult, E-120; `href` is an API link (04 B3-D11) | §1.4 builds routes by scope; further result columns deferred to later |
| R-02 | API-R-50, API-S-DashboardHome; parameters `entity`, `period`, `book` only | §2.5, §2.6 |
| R-03 | API-R-09 `sort`; API-R-44 `sort` (severity, then `created_at` descending) | §2.3, §2.5, §2.6, §13.3, §15.3 |
| R-04 | API-R-09 `preparer` | §15.3 |
| R-05 | API-S-Contract `steps[]` (E-112, E-113, §16.14 step rule); API-S-ActivationChecklist; table 15.4-I (04 B3-D22) | §4.1.3, §4.1.7, §4.9.8 |
| R-06 | API-S-AllocationWalk and API-S-Obligation `range_position` (E-114) and `outside_range_point` | §4.1.3.1, §5.4, §5.6 |
| R-07 | API-S-Contract `kpis_ratios`; API-S-Obligation `ratios` | §4.1.4, §4.1.7, §5.4 |
| R-08 | API-R-28 combination suggestions over exception items (04 B3-D14) | §4.1.7, §4.9.7 |
| R-09 | API-R-11 `subject_type`, `subject_id` | §4.1.7 |
| R-10 | API-S-ScheduleLine `obligation_key`; API-R-35 `schedule_kind`; API-S-SubledgerLine `journal_run_id`, with `account` as the `gl_account` field (04 B3-D12) | §4.3, §4.4, §4.5; billing plan due date and reversed-line link deferred to later |
| R-11 | API-R-34 `period`, `period_amortization` | §4.3 |
| R-12 | API-S-UsageCommitment `status` literals mapped to DS-CMP-19 chip words (04 B3-D13; rev 1.3) | §4.4 |
| R-13 | API-S-ImpactSummary; API-S-Modification `impact_preview` and list `impact_summary` | §4.6, §7.7 |
| R-14 | API-S-ContractHistoryItem, E-116 | §4.7 |
| R-15 | API-R-12 `contract_id` | §4.8 |
| R-16 | API-R-30 events preview; API-R-32 estimate-version preview | §4.9, §8.4 |
| R-17 | §16.1 `distinct-review` command | §4.9.2 |
| R-18 | API-R-28 `replace-draft` (§16.1) | §4.10 |
| R-19 | API-S-Explain `history[]` | §6.3 |
| R-20 | API-R-49 `verify` | §6.3 |
| R-21 | API-R-49 `GET /calc-traces/{id}`, API-S-CalcTrace | §6.5 |
| R-22 | API-R-56, API-S-SourceRecord | §6.6 |
| R-23 | API-S-Modification `prefill_reasons` | §7.5 |
| R-24 | §16.14 estimates list and version additions | §8.4 to §8.6 |
| R-25 | API-S-Obligation `material_right.status` (E-115), `status_date` | §5.4, §5.6 |
| R-26 | §16.2 `request-ssp-override` | §5.8 |
| R-27 | API-R-43 row filters and `sort=status` | §6.6, §12.2 |
| R-28 | API-R-22 and API-R-23 filters and sort keys; `member_count` | §9.4, §10.3 |
| R-29 | API-S-VersionSummary | §11.1 |
| R-30 | API-R-25 upsert by `rule_key`; API-R-57 configuration test cases | §11.1, §11.2 |
| R-31 | API-S-SimulationSummary | §11.1 |
| R-32 | T-PLT-31 and API-S-RegistryParameter `section` | §11.3 |
| R-33 | API-R-26 diff `mid_change_ratio` | §11.4, §15.4 |
| R-34 | §16.14 `inside_count`; API-R-27 observations | §11.5 |
| R-35 | §16.14 account mapping `rule_count` | §11.6 |
| R-36 | API-S-Import `finding_counts[]`, `header_match[]` (E-119) | §12.2 |
| R-37 | §16.6 error report | §12.2 |
| R-38 | API-S-ImportDiff (E-118) | §12.2 |
| R-39 | §16.14 `available_actions` (E-117) and `dismiss_blocked_reason`; API-R-44 filters | §13.4, §13.5, §14.3 |
| R-40 | §16.14 `last_sync_run` and `duration_seconds`; API-R-45 `connection` filters | §14.3 |

