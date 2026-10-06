## Appendix C. Coverage waivers

| Field | Value |
|---|---|
| Owner | BUILD_SPEC finisher (design phase B3, slug `bs-finish`) |
| Date | 2026-09-12 |
| Status | Binding appendix of `docs/BUILD_SPEC.md` (header SZ-08; BSF-D-06). Read-only for the loop. Amended only by the supervisor |
| Evidence | `python3 research-harness/buildspec/check_merged.py` runs `research-harness/buildspec/check_buildspec.py` over the merged file. Checks 1 to 10 report no gap, so no coverage or ordering gap is waived. Every remaining flag of check 11 (sizing heuristics, BSC-D-09) has one row below, and every row matches one flag |

Rules:

1. A waiver accepts the size of one item for one sub-check. It never waives a formal SZ-02 limit: every item beyond a route or screen-id limit was split (BSF-D-06).
2. The measured value is the one check 11 reports. When an item changes and the value differs, `check_merged.py` fails until the row is updated or the item is split.
3. SZ-05 still applies: when the loop cannot finish a waived item in two iterations, it records a spec question proposing a split.

| Id | Sub-check | Item | Measured | Reason |
|---|---|---|---|---|
| CW-01 | 11a | FND-2 | 13 criteria | One kernel area (settings, frozen clock, structured logging) whose 13 criteria are single-assertion unit tests of dev-guide §2 and §6.6 contracts; no schema, no route and no completed requirement |
| CW-02 | 11a | FND-9 | 14 criteria | One kernel contract, problem details with the API money types, tested row by row against 04 §15.2 and REQ-PLT-028 and REQ-PLT-031; the criteria are table-driven unit tests with no schema or engine work |
| CW-03 | 11a | EKC-1 | 14 criteria | The money kernel of dev-guide §5.9: each criterion is one POLICIES ALG-01 CHK row or one CV rule as a pure engine unit test without a database; splitting would separate the apportionment rows from the helpers they exercise |
| CW-04 | 11a | RFD-2 | 14 criteria | One migration revision for five related tables that complete four requirements together; the criteria are pg invariant tests and API tests of one resource group, within the SZ-02 table and route limits |
| CW-05 | 11a | RFD-11 | 13 criteria | Registry configuration only: the tenant policy set, practical expedients and the legacy-parity preset over existing tables T-PLT-31 and T-PLT-32, with no schema change; the criteria are resolution and validation unit tests |
| CW-06 | 11a | RFD-13 | 13 criteria | One SSP publication lifecycle (study, maker-checker, range validation, immutability) in one domain area; the criteria include the DG-AK-45 range-validation rows of CHK-031, which must land with the publication command that calls them |
| CW-07 | 11a | ENB-13 | 13 criteria | One engine registry, the boundary handlers of ENGINE_SPEC Table 0.3-A with the modification integrity validator; the criteria are one pure test per handler or finding code, and the item completes a single requirement |
| CW-08 | 11a | END-9 | 13 criteria | The `compute` orchestration of ENGINE_SPEC §0.3 is one function; its 10 test bullets and three non-none sub-fields cover the fail-closed identities that must all hold before AKS starts, so a split would leave `compute` partly built |
| CW-09 | 11a | CTR-5 | 13 criteria | Fact-capture events, late events and the compute job share one command path and one migration (T-IMP-05, BS3-D-02); 11 test bullets plus Answer keys and Controls lines, within every SZ-02 limit |
| CW-10 | 11a | CTR-17 | 13 criteria | One modification object with its guided classification and impact preview over one migration (T-CON-06); 11 test bullets plus Answer keys and Controls lines; the engine proposals are consumed through `compute` without engine change |
| CW-11 | 11a | DIN-6 | 13 criteria | The four legacy v1 modification template modes run through one importer and one stage 01 rule (S01-R-09); each criterion is one mode or one golden figure, and the modes share their validation code |
| CW-12 | 11a | CLO-6 | 13 criteria | Lock with certification, lock snapshots and permanent lock form one SM-07 transition group; the criteria are transition and snapshot assertions of one close domain module, with no migration and no route beyond API-R-18 |
| CW-13 | 11a | CLO-9 | 13 criteria | The legacy gross and adjustment date-range journal views are one query module; each criterion is one journal-view figure from the golden or answer-key data, and the item adds no schema or screen |
| CW-14 | 11a | LMG-10 | 14 criteria | Journey J-20 part delivered as one Playwright journey item (BS-D-15) with at most ten steps; 11 test bullets plus Screens, Journeys and Golden lines are journey steps and captures, not separate modules |
| CW-15 | 11a | REL-1 | 16 criteria | Release sweep: its criteria are the gate rows of header §7 run on a clean tree, and it builds no capability; review finding BSC-03 states that the release sweeps need no split |
| CW-16 | 11a | REL-3 | 20 criteria | Final release gate: its criteria are the G1 to G12 evidence rows of header §7 and `docs/00-GOAL.md` §3, recorded without new code; review finding BSC-03 states that the release sweeps need no split |
| CW-17 | 11b | PLF-14 | 4 modules | Integration item: the transactional outbox, notifications and the fake email adapter are one delivery path; the approvals and memberships entries are hooks of NTF-01 to NTF-04 and preference seeding, and the item holds 11 test bullets (BSC-04) |
| CW-18 | 11b | CLO-7 | 4 modules | Integration item: reopen with dual approval touches routing and the BR-CLS-06 no-auto-approval guards in the import and contract commands; those guards must land with the reopen command they protect, and the item holds 7 test bullets (BSC-04) |
| CW-19 | 11b | EKC-7c | 4 modules | Supervisor remediation from the phase FND review (D-78): the key provider, keyring blob layout, log hygiene and money-string fixes are small security corrections to existing kernel modules found by one review; each module keeps its existing test file, the item holds 8 test bullets, and splitting would delay latent P2 fixes behind unrelated engine items |
| CW-20 | 11j | PLF | 33 items | Supervisor remediation items PLF-3a to PLF-3c from the phase EKC review (D-79) were inserted after PLF-3 so that the engine-kernel and harness fixes land before any consumer; the phase's own 30 build items are unchanged |
| CW-21 | 11b | WEB-3b | 6 modules | Supervisor remediation from the phase PLF review (D-80): the one-time secret replay, password-change rotation, outbound destination guard and invitation identity fixes each touch the module whose defect they correct (email, http and idp adapters, platform users service, auth, idempotency); they share the D-80 destination guard and must land before WEB-12, WEB-14, WEB-19 and WEB-23 bind those APIs |
| CW-22 | 11a | RPS-7a | 13 criteria | Supervisor smoke journey SUP-RC-SMOKE (D-82, D-86): one serial ten-step journey over one tenant state, where each step consumes the records the previous step created (import, approval, journal run, export); splitting it would repeat sign-in, import and run setup, and the planner sized it as one 70-minute part (sup-rc-smoke.md N-7) |
