# eRev Cloud: BUILD_SPEC phase plan

| Field | Value |
|---|---|
| Owner | Principal engineering manager, BUILD_SPEC plan (design phase B3, slug `bs-lead`) |
| Date | 2026-09-12 |
| Status | Binding build contract for the BUILD_SPEC authors BS-1 to BS-4 and for the loop at GATE items. Read-only for the loop (DG-LAY-01, DG-GIT-05). Amended only by the supervisor |
| Precedence | Subordinate to every document of `docs/01-DECISIONS.md` §0, D-73 and D-74. Governs phase order, phase membership, author assignment, gate scope at phase exits and hint closure. A BUILD_SPEC item governs its own acceptance criteria; where an item and this file disagree on membership or order, this file governs |
| Companion | `docs/build-spec/00-header.md`, the header of `docs/BUILD_SPEC.md` |
| Generation | The tables marked "generated" are produced by `.scratch/b3-bs-lead/phases.py` from `.scratch/b3-bs-lead/inventory.json`, which `.scratch/b3-bs-lead/extract.py` builds from the binding documents. The generator fails when an id of §17 is unassigned or assigned twice. Rev 1.1 amends two generated tables by hand, the §1 membership counts of GPA and GPB and the §9 rows `legacy_probe` (B3-BS2-04; header BSF-D-03); a regeneration must carry those amendments |

## Revision log

| Rev | Date | Change |
|---|---|---|
| 1.0 | 2026-09-12 | First issue (design phase B3, `bs-lead`): 27 phases, author assignment, gate scope at every phase exit, generated membership tables and mechanical checks |
| 1.2 | 2026-09-21 | MIGRATION_SSP_REPLAY — the mode-(a) legacy SSP replay request, auto-approved under AUTO-MIG-01 (D-98 133 AMENDMENT 4); built in F-LMG-PG-7b (§5.3 LMG row; amended by lane F-LMG inside the PG-7b gated commit under explicit supervisor instruction — the third addendum — a disclosed exception to DG-LAY-01 / DG-GIT-05) |
| 1.1 | 2026-09-12 | Finisher pass (design phase B3, `bs-finish`; header BSF-D-01 to BSF-D-03): §0 and §2 name the four author files and the merge script that assembles `docs/BUILD_SPEC.md`; the parity selection of §1 row GPA and of §4 row GATE-GPA, which the rows "as GATE-GPA" inherit, becomes `probe-P3-over-delivery-validation` with 94 cases; §1 row GPB, the membership counts (GPA 94, GPB 28) and the §9 rows `legacy_probe` (P3 in GPA; P1, P2 and P4 in GPB) follow B3-BS2-04 (review finding BSC-01) |
| 1.3 | 2026-09-30 | RECONCILIATION_GENERATE — the job of `POST /reconciliations` (04 API-R-40, E-14 rev 1.121; supervisor ruling R-54 (a)); built in CLO-16 (§5.3 CLO row; totals 26 of 26 E-14 values; amended by lane F-CLO-B under the supervisor's ruling — a disclosed exception to DG-LAY-01 / DG-GIT-05, as the 1.2 row) |
| 1.5 | 2026-09-30 | PERIOD_OPEN_REDIRTY — the job the lock decision defers for the period it opens (04 E-14 rev 1.164; 05 SCH-06 rev 1.79; supervisor rulings R-101 (a) and R-106 (a)); built in item CLO-LOCK-OPEN-REDIRTY-1 (§5.3 CLO row; totals 27 of 27 E-14 values; amended by lane FIX-D2 on the supervisor's instruction of 2026-09-30 — a disclosed exception to DG-LAY-01 / DG-GIT-05, as the 1.2 and 1.3 rows) |
| 1.4 | 2026-09-30 | EVIDENCE_SHRED — the request to shred a file that a record holds as its evidence, decided by a Controller (supervisor rulings R-49 (a) and R-86; 04 rev 1.142); built by lane SECFIX-IMP on the SOP-5 `file.shred` command (§5.3 SOP row; totals 32 of 32 E-08 values — the cell read 30 since rev 1.2 although `MIGRATION_SSP_REPLAY` had made 31; amended by lane SECFIX-IMP under the supervisor's ruling, number assigned by the supervisor) |
| 1.6 | 2026-10-02 | RT-95 (SF-24:results, `/search`) asks `contract.read` — the cell read `authenticated`; SCREENS §0.4 rev 1.53 states the permission (the supervisor's ruling of 2026-10-01 on lane F-CTR-WEB's pre-build line for CTR-28's screens, point P4), and the route as built asks it. Found by that lane; amended by the supervisor |

### Decisions taken in B3 (D-77)

None of these opens a question. Each is the most reasonable default within the BUILD_SPEC author's remit, and `00-header.md` applies them.

| Id | Decision | Rationale |
|---|---|---|
| BS-D-01 | Phase codes are three capital letters that no other id family uses (dev-guide §0.2; 05 families such as `ENG`, `PERF`, `SBX`; SCREENS_B `RPT-nn`; legacy 07 `PAR-nn`). Item ids are `<code>-<n>` with n unpadded from 1. Supervisor items appended later are `<code>-<n><letter>` (the PROMPT.md `ENG-5a` pattern). The release phase keeps the code `REL` that the design brief requires; 05 rules are always cited as `05 REL-0n` | Greppable ids that never collide across authors or with cited ids |
| BS-D-02 | Engine stage items (ENA, ENB, ENC, END, EDS) are accepted on stage-level evidence: the rules, invariants, findings and trace nodes of their ENGINE_SPEC section, its worked examples as engine tests, and CHK unit tests (DG-ENG-11). Answer keys close in AKS, EDS and PRP (§8) | 188 of the 232 active keys assert subledger lines (stage 14) and 192 assert labelled balances (stage 10), so key-level acceptance cannot precede stage 14. D-71 holds: no REQ with an `AK` hint closes before its keys pass (§15) |
| BS-D-03 | Answer-key counts are taken from the corpus at run time: 234 files, 232 active and 2 withdrawn; 227 engine runner and 5 platform runner | `docs/accounting/answer-keys/_coverage/ADJUDICATION.md` §1 supersedes the figure of 221 keys in the design brief |
| BS-D-04 | A specialist gate runs unfiltered at a phase exit once its complete scope exists; before then it runs with the selection of §4 | dev-guide §10.1 names "section boundaries", but an unfiltered `make answer-keys` or `make parity` cannot pass before the engine, the parity runner and the platform capabilities exist. DG-GATE-01 applies to the selection named |
| BS-D-05 | Serial journeys (PRD E2E-04) are built in DMO, after the Avenmoor world seed, in E2E-04 order. Fresh-tenant journeys land at the end of the phase that builds their last surface | Serial journeys run on the seeded Avenmoor world (PRD §2.5 to §2.9; WLD-P-02 periods closed through close runs) and depend on each other's outcomes |
| BS-D-06 | Report codes `migration_reconciliation` (RPT-41) and `parallel_run_comparison` (RPT-42) are built in LMG by BS-3; `forecast_outputs` (RPT-39) and `actual_vs_forecast` (RPT-40) are built in FCS. All four use the RPS report framework unchanged | Their source tables (T-MIG-01 to 03, T-FC-01 to 04) are created in those phases |
| BS-D-07 | Registry completeness (DG-ARC-08). The item that creates `SUBJECTS`, the job handler registry or the outbox handler registry also creates the DG-ARC-08 test with a module-level tuple `PENDING_<REGISTRY>` listing the 04 literals whose handlers later phases build; each entry names its phase code from §5.3. Every item that builds a handler removes its entry. `JOB_QUEUE` and `PAYLOADS` are complete when created. GATE-SOP requires every `PENDING_` tuple to be empty | DG-ARC-09 requires complete enum mirrors from the start, and DG-ARC-08 would otherwise force handler stubs, which header XR-14 forbids |
| BS-D-08 | Until SF-01 exists, sign-in and `/` redirect to the first built route in the order `/home`, `/contracts`, `/approvals` (constant `LANDING_ROUTES` in `frontend/src/app/router.tsx`). The RPS item that builds SF-01 leaves only `/home` | RT-07 redirects `/` to `/home`, which does not exist before RPS; navigation lists only built routes |
| BS-D-09 | Capture names passed to `screens.capture(page, name)` are the SCREENS SCR-TID-03 normalisation of the screen id plus an optional state slug (`sf-03-obligation`, `sf-01-approver`). A capture whose SCREENS §0.12 or SCREENS_B §15 state needs a later journey outcome captures the seeded state until the journey item that produces the state updates the row | Stable file names for designer review (DG-E2E-06) without forward dependencies |
| BS-D-10 | The 15 requirements with an `E2E` hint that no journey cites close through named `test.step` blocks in `screens.spec.ts`, `design.spec.ts` or a fresh-tenant `beforeAll`, titled `<REQ id> <assertion>`, at the phase named in §15.2 | DG-DONE-01 requires Playwright steps for `E2E` hints; the screen and design projects are the harness for cross-screen behaviour |
| BS-D-11 | Rule-set tables T-REF-24 to T-REF-27 are created in PLF | The 04 §14.3 provisioning seed creates rule set `AUTO-BOOTSTRAP` (kind `AUTO_APPROVAL`), and the approval engine evaluates routing rules. RFD builds API-R-25 and the SF-13 rule screens over the same tables |
| BS-D-12 | The phase that creates a table named in the 04 §14.3 provisioning seed extends `tenant.provision` (§5.3). Dev databases provisioned earlier are rebuilt with `make seed RESET=1`; tests and e2e always provision fresh tenants | Migrations never seed tenant data (DG-MIG-07) |
| BS-D-13 | Guide and security file names: `docs/guides/runbook.md`, `docs/guides/user-guide.md`, `docs/guides/migration-guide.md`, `docs/guides/itgc-guide.md` (REQ-CTL-004); `docs/security/threat-model.md` (REQ-SEC-005), `docs/security/ASVS-L2.md` (05 SAR-41), `docs/security/SUBPROCESSORS.md` and `docs/security/DPA-TEMPLATE.md` (05 PRV-11). FND creates the four guides with sections for what is built; items update them (DG-DONE-07); SOP completes the security documents and `itgc-guide.md`; DEP completes the other guides | dev-guide DG-LAY-01 names only the directories |
| BS-D-14 | GATE items do not pause the loop. The loop records the checkpoint block of header §6, commits and continues; the supervisor reviews asynchronously and steers through appended items and D-numbers (D-70) | The loop cannot create files under `.ralph/` (DG-FORBID-06) and prints the done marker only when the whole task is complete |
| BS-D-15 | A journey may be delivered across consecutive items; each adds consecutive steps with their acceptance items and alternates. The journey counts for G8 only when its last item is ticked | J-13 has 16 steps, 9 acceptance items and 2 alternates, more than one iteration can build |
| BS-D-16 | The stage 01 platform part (`erev_api/domain/imports/legacy_v1/`, `erev_api/domain/integrations/normalise.py`) is built in DIN; ENA builds the engine part | ENGINE_SPEC Table 0.2-A splits the stage, and the platform part needs the import tables |
| BS-D-17 | WEB builds DS-CMP-03 in the design gallery together with the SF-23 tenant switcher, sandbox indicator and read-only chip; RFD binds the context pill to entities, periods and books with the BR-UX-01 defaults | Entities and periods do not exist before RFD |
| BS-D-18 | `make controls-report` is expected green from GATE-SOP; earlier GATE items run only `erev controls-report --tags-only` inside `make lint` | Every control of §7 has its first tagged test by GATE-SOP |
| BS-D-19 | Each release-1.0 REQ has exactly one build phase (§6): the phase whose last backend or screen component makes the requirement statement true. Specialist hints close as §15 states | G1 needs one tick per requirement; hints such as `GT`, `AK`, `E2E` and `PERF` close in harness phases |
| BS-D-20 | Until a Playwright project holds a test, `scripts/e2e.sh` skips it, records `{project, skipped: "no tests yet"}` in `.run/reports/e2e/report.json` and prints the project name. From GATE-DMO every project of DG-E2E-02 holds tests and none is skipped | DG-E2E-02 runs five projects, and Playwright exits non-zero for a project without tests |
| BS-D-21 | Legacy port-note hints `TC-<doc>-<nn>` are proved by tests named `test_tc_<doc>_<nn>_<slug>` (for example `test_tc_setup_20_unmapped_product_row_message`) asserting the "Expected (eRev Cloud)" or "Fixed" column of legacy 01 to 06 §7.3 | 03 §1.4 defines the hint without a naming rule |
| BS-D-22 | Test names in an item's acceptance are binding for evidence. A named test may be split into several functions whose names start with the named function name; any other rename is a spec question | Fresh agents and the supervisor find evidence by grep |
| BS-D-23 | The dev-guide §10.5 evidence block gains one line, `- REQs completed: <ids>`, after `- Tests:` whenever the item completes requirements | G1 traceability from PROGRESS.md alone (header §7) |
| BS-D-24 | G1 is measured by comparing the item-id set of `docs/BUILD_SPEC.md` (lines starting `- [ ] **`) with the ticked-id set of `PROGRESS.md` (lines starting `- [x] `), and the REQ set named under "REQs completed" with the release-1.0 rows of 03 §3 | A mechanical, repeatable check without a new script path |

## 0. How to use this file

- **Authors (BS-1 to BS-4).** Write items only for your phases (§2), in the order of §1, into the author file of §2. Each phase section starts with `## <nn> <code> <phase name>`, where `<nn>` is the two-digit phase order, and a preamble that repeats the phase's entry criteria, exit criteria and gate scope from §1 and §4, and it ends with item `GATE-<code>` (header §6); REL has no GATE item. Every requirement of the phase (§6) appears in at least one item's acceptance, and the item whose tick makes its statement true lists it under **REQs completed**. Every control of §7, route row and placement of §10, journey of §11 and make target of §13 assigned to the phase appears in an item.
- **Assembly.** `python3 research-harness/buildspec/merge_buildspec.py` assembles `docs/BUILD_SPEC.md` from `docs/build-spec/00-header.md`, the phase sections of the author files of §2 in §3 order and `docs/build-spec/90-appendices.md`; `--check` proves that the merged file equals a fresh merge. The merged file is authoritative (header BSF-D-01). No item references a later item, except fail-closed consumers (header XR-12).
- **The loop** reads this file at GATE items and when an item cites a section. The membership tables are the membership contract; an item's acceptance criteria are its test contract.
- **Cross-author interfaces.** When an item needs an interface from an earlier phase of another author, it cites that item id and the dev-guide signature (dev-guide §5 kernel, §7 engine). An author changes another author's interface only through a supervisor item.

## 1. Phases

The order is linear: every phase depends on every earlier phase, and the column "Uses" names the phases whose outputs it consumes directly. Entry criteria of every phase after FND include `GATE-<previous code>` ticked. Item counts are indicative and exclude GATE items; authors may differ by up to a third.

| # | Code | Phase | Author | Uses | Entry criteria beyond the previous GATE | Exit criteria | Items |
|---:|---|---|---|---|---|---|---:|
| 1 | FND | Foundation: repository, toolchain, gates and kernel base | BS-1 | none | Roles `erev_owner`, `erev_app` and databases `erev`, `erev_test`, `erev_e2e` provisioned by the supervisor (D-42; DG-ENV-15); `docs/BUILD_SPEC.md` assembled | (1) Tree and layout rules of dev-guide §1.1 to §1.3: `backend/` uv project, `frontend/` toolchain (DG-FE-01, 09, 12, 13, 17, 19, 20; DG-RUN-20 to 24), `scripts/`, `Makefile`, `LICENSE`, `NOTICE`, `README.md`, `.env.example`. (2) Every FND target of §13 with DG-MK-00a to 00h semantics; `make setup` idempotent. (3) Kernel: dev-guide §5.1; §5.2 engines, session factories and role guard over global tables; §5.8 with `PROBLEMS` equal to 04 §15.2; §5.9 API money types; §5.10; §5.18 over global tables; §6.4 route helpers; §6.6 logging; API-R-53 `healthz`, `readyz`, `openapi.json`. (4) Revision for 04 §18 step 0001 and the FND tables of §5.1, with DG-MIG-05. (5) `erev registry-seed` over POLICIES §1 and T-PLT-31; `controls.yaml` equal to 03 §4.1; StrEnum mirrors of 04 §3; `CATALOGUE` of T-PLT-11. (6) Self-tested `design_check`, `vocab_check`, `licence_check`, `secrets_check` and `openapi_check`; `make fixtures` with committed legacy fixtures and manifest (DG-PAR-02). (7) DG-ARC-01 to 06, 09, 10, 12 and 13. (8) Frontend toolchain with `theme-init.js`, the tokens copy and the DS-VER-01 and DS-VER-02 Vitest suites; the router holds no screen until WEB. (9) The guides of BS-D-13 exist with sections for what is built. (10) `make ci` and `make test-pg` green | 14 |
| 2 | EKC | Engine kernel and test harnesses | BS-2 | FND | none | (1) `erev_engine` public modules of DG-ENG-07 other than stage packages: `money` (dev-guide §5.9; ALG-01), `currencies`, `dates`, `progress`, `canonical` (§5.17), `trace`, `formulas` and `reevaluate` (§5.16), `enums`, `rules` (T-REF-26 `FIELDS`, `match`), `errors`, `guards`, `bundle` (ENGINE_SPEC §0.4, §0.5), `stages/state` (ENGINE_SPEC §0.11; ENGINE_SPEC_B §0.5, §0.6), `stages/__init__` constants and `ENGINE_VERSION`. (2) DG-ARC-02 purity; CHK unit tests of COV-C-01 (DG-ENG-11). (3) Answer-key loader of dev-guide §9.5.8 loading all 234 files with zero errors, and `coverage()` reporting zero gaps, as unit tests outside `tests/answer_keys/`; `run_engine` bundle assembly (DG-AK-40) and `assert_checkpoints` (DG-AK-50 to 57) with unit tests; `test_answer_keys.py`; the `make answer-keys` report (DG-AK-43). (4) Strategies (DG-PROP-03), Hypothesis profiles (dev-guide §9.7), P2, P3 and the helper part of P4; `make properties` | 12 |
| 3 | PLF | Platform services | BS-1 | FND, EKC | none | (1) Kernel dev-guide §5.2 tenant context, §5.3, §5.4, §5.5 with chain and verification, §5.6 (routing, delegation, stale invalidation, preview snapshot storage), §5.7, §5.11 (outbox, notifications, fake email, webhooks), §5.12 (Procrastinate schema DG-MIG-09, eight queues, sweeper, worker), §5.13, §5.14, §5.15 (versions, resolve, presets), §5.16 explain service over in-memory traces, §5.19 and §5.20. (2) PLF tables of §5.1 with RLS templates, IM classes, grants and DB invariants; DG-TST-20 to 25 over every tenant table. (3) API-R rows of §5.2 for PLF: argon2id passwords, sessions and CSRF, TOTP and recovery codes, password reset, OIDC against the in-process mock IdP (D-72), OAuth2 API clients, support grants, saved views, access review campaigns. (4) `erev tenant create` and `POST /operator/tenants` with the PLF provisioning rows of §5.3 and `AUTO-BOOTSTRAP`. (5) DG-ARC-04, 07 and 08 (BS-D-07). (6) Tagged tests of §7 for PLF. (7) `make dev-up`, `dev-down`, `status`, `worker` and `doctor` | 24 |
| 4 | WEB | Frontend foundation, platform screens and e2e harness | BS-1 | PLF | none | (1) Frontend source layout of dev-guide §8.1; format module and i18n (DS-VER-03; DESIGN_SYSTEM §9); DS-CMP-01 to 32 with DS-VER-04 tests; design gallery X:design (DS-VER-06). (2) Shell of SCREENS §1 with a rail listing built destinations only, and the WEB screens and placements of §10. (3) Playwright harness DG-E2E-01 to 12: five projects, `personas` with TOTP, `screens.capture`, `a11y.check`, network guard and `tenants.ts`; `scripts/e2e.sh` (BS-D-20); `screens.spec.ts` rows for WEB screens; `design.spec.ts` (DS-VER-06 to 09). (4) `erev seed demo` scaffold: tenants WLD-T-00 to 07 with code, display name, kind, `is_demo` and reporting currency (PRD §2.4); persona users WLD-U-01 to 11 with memberships and roles (§2.3); TOTP factors (WLD-U-R2); `.run/demo-credentials.txt` (DG-RUN-32); `make seed` and `make e2e` | 22 |
| 5 | ENA | Engine stages 01 to 05 | BS-2 | EKC | none | Stage packages of §16 for ENA: every S01-R to S05-R rule, stage invariant, finding code and trace node, and the worked examples of ENGINE_SPEC §1 to §5 as engine tests; entry functions of ENGINE_SPEC Table 0.2-A, called directly by tests (`compute` is wired in END); CHK unit tests of COV-C-13 other than CHK-031; P1 at stage 05 level; CTL-012 allocation identities fail closed | 14 |
| 6 | RFD | Reference data, policies and SSP studio | BS-3 | PLF, WEB, ENA | none | (1) API-R rows of §5.2 for RFD with schemas 04 §16.4, §16.5 and the period reads of §16.8; commands routed through the RFD subjects of §5.3. (2) RFD tables of §5.1 and the provisioning extensions of §5.3. (3) SSP publication with range validation `erev_api.domain.ssp.range_validation.validate_ranges` (DG-AK-45; CHK-031); SSP resolution through `s05_allocation.resolve_ssp`; SSP calculator job; legacy-parity preset command (DG-KRN-REG-05). (4) RFD screens of §10 with captures, including SF-15:setup and the context pill binding (BS-D-17). (5) Tagged tests of §7 for RFD | 20 |
| 7 | ENB | Engine stages 06 to 08 | BS-2 | ENA | none | Stage packages of §16 for ENB per ENGINE_SPEC §6 to §8 with rules, invariants, findings, trace nodes and worked examples; the boundary handlers of ENGINE_SPEC Table 0.3-A; CHK unit tests of COV-C-05, COV-C-10 and COV-C-11 | 12 |
| 8 | ENC | Engine stages 09 to 11 | BS-2 | ENB | none | Stage packages of §16 for ENC per ENGINE_SPEC_B §9 to §11; CHK unit tests of COV-C-02, 04, 06, 07 and 12; P4 at schedule level; P10 | 16 |
| 9 | END | Engine stages 12 to 14 and `compute` | BS-2 | ENC | none | Stage packages of §16 for END per ENGINE_SPEC_B §12, §13 and §14.2; `compute` of ENGINE_SPEC §0.3 with DG-ENG-03, 05, 08 and 10; CHK unit tests of COV-C-03, 08 and 09, including CHK-084; P5 engine part, P8, P12, P13, P14 and the metamorphic suite | 16 |
| 10 | AKS | Answer-key sweep, engine runner | BS-2 | END | none | Every key of §8.2.1 passes `make answer-keys ID=<ids>`, family by family; corrections land in the stage packages and cite the ENGINE_SPEC rule they correct; engine-area requirements whose `AK` hints all fall in §8.2.1 are closed (§15) | 8 |
| 11 | CTR | Contracts, computation and workbench | BS-3 | RFD, END, AKS | none | (1) API-R rows of §5.2 for CTR with schemas 04 §16.1 to §16.3, §16.11, §16.13 and §16.14; `PAYLOADS` for every E-03 type. (2) `erev_api.domain.contracts.bundles.build` and `computation.persist` (DG-CMD-09, 10); `CONTRACT_COMPUTE` and `POLICY_SIMULATION` jobs; dirty marking. (3) Contract lifecycle SM-02: drafts, activation checklist, approval routing, field locks, holds, combination and suggestions, void with reversal lines; events and event submissions; estimates and portfolios; judgements; modifications and subscription changes with impact previews; calc trace store and the `/explain` routes. (4) CTR screens of §10, including the Explain panel, X:trace and SF-24 search. (5) Provisioning extension of §5.3. (6) Tagged tests of §7 for CTR | 26 |
| 12 | DIN | Data in: imports, exception queue and integrations | BS-3 | CTR | none | (1) DIN tables of §5.1 and API-R rows of §5.2. (2) Import pipeline of 05 §5.5 (IPL-01 to 12): upload, validate, dry-run diff, submit, approve, commit, row lineage and control totals; legacy v1 templates (04 §17.4) with the four modification template modes and the stage 01 platform part (BS-D-16); modern CSV templates; findings of 04 §15.4 (D-30a); exception queue; mapping profiles. (3) Canonical ingestion (05 §5.1), adapter interface and contract tests, in-process mock Salesforce and Stripe adapters and the NetSuite chart-of-accounts endpoint (D-72), reconciliation sweep, inbound webhooks. (4) DIN screens of §10. (5) Tagged tests of §7 for DIN | 16 |
| 13 | GPA | Golden parity: contract and probe kinds | BS-2 | DIN, AKS, RFD | none | Parity runner DG-PAR-01 to 11 over the legacy v1 pipeline under the `LEGACY_PARITY` preset; `make parity K="initial_allocation or pob_position or contract_position or cumulative_catchup or probe-P3-over-delivery-validation"` passes 94 of 94 (probes P1, P2 and P4 pass in GPB, B3-BS2-04); report of DG-PAR-08 | 7 |
| 14 | EDS | Engine stage 15: close projections and disclosures | BS-2 | END | none | Stage 15 engine part of ENGINE_SPEC_B §15.2 (RPO and time bands, rollforwards, prior-period revenue, disaggregation, cost rollforward, lock snapshot content, variance between closes) with invariants, findings and worked examples; the keys of §8.2.2 pass; P7 engine part | 8 |
| 15 | CLO | Close, schedules, journals and reconciliations | BS-4 | CTR, DIN, EDS | none | (1) CLO tables of §5.1, API-R rows of §5.2 and the provisioning extension of §5.3. (2) Period transitions SM-07 (DB-07): soft close, close gates, lock with certification, reopen with dual approval, permanent lock; close runs with the 14 steps of SCREENS_B §1.2 (05 RCP-19; PERF-01 steps); schedule release, FX remeasurement pass and netting reclass; lock snapshots (`erev_api/domain/close/snapshots.py`). (3) Journal summarisation and export (ENGINE_SPEC_B §14.3): runs, batches, grain, the CSV adapter and the NetSuite and QuickBooks Online mock adapters, outbox relay, acknowledgements; manual adjustments, manual release and defer. (4) Billing-to-subledger and subledger-to-GL reconciliations with the mock trial balance pull and auto-certification; multi-entity close. (5) CLO screens of §10; J-23. (6) Tagged tests of §7 for CLO | 24 |
| 16 | RPS | Reports, dashboards, evidence packs and audit log | BS-4 | CLO, EDS | none | (1) RPS tables of §5.1 and API-R rows of §5.2. (2) Report framework: definitions and parameter schemas, report runs with IPE records, exports and stamped outputs (SCREENS_B RV-01 to 14), tie-outs of 04 table 10-T; every RPS report code of §5.4 per SCREENS_B §5.6; the disclosure pack. (3) Dashboards and SF-01 Home (API-R-50) with favourites. (4) Period evidence pack and contract sample pack with manifests; audit log and chain verification screens. (5) RPS screens of §10; J-01. (6) Tagged tests of §7 for RPS | 22 |
| 17 | SNP | Sandbox tenants: snapshot, restore and reset | BS-4 | CLO | none | T-PLT-34; API-R-04 snapshots, sandboxes and reset; `TENANT_SNAPSHOT` and `SANDBOX_RESET` per 05 SBX-01 to 11; DB-15 restrictions and 403 `sandbox-restricted`; the sandbox banner (BR-UX-03); SF-15:sandbox; CTL-043 | 6 |
| 18 | LMG | Legacy migration and onboarding | BS-3 | DIN, SNP, RPS | none | T-MIG-01 to 03; API-R-48; legacy `ASC606.db` import mode (a) opening balances and mode (b) replay into a sandbox then promotion (D-31; 05 SBX-10); reconciliation lines; the report codes of §5.4 for LMG; the parity preset on migrated tenants; acquired contracts and onboarding from other systems; SF-19 screens; J-20 and J-21; CTL-048 | 12 |
| 19 | GPB | Golden parity: journal and migration kinds; full G3 | BS-2 | GPA, RPS, LMG | none | `journal_entry_totals` (24), `point_in_time_equivalence` (1) and probes P1, P2 and P4 of `legacy_probe` (3) pass (B3-BS2-04); `make parity` passes 122 of 122 with none skipped; DEV sign-off statuses listed (DG-PAR-08) | 4 |
| 20 | PRP | Platform properties and platform answer keys; full G4 and G5 | BS-2 | CLO, RPS, GPB | none | Platform parts of P5, P6 and P7; P9; P11; the stateful machine (dev-guide §9.7); the keys of §8.2.3 pass; `make answer-keys` unfiltered (232 active keys, zero corpus gaps) and `make properties` unfiltered green | 8 |
| 21 | FCS | Scenarios, forecasts and deal preview | BS-4 | SNP, RPS | none | T-FC-01 to 04; API-R-46; scenario tenants (05 SBX-09), forecast event sets, runs, refresh, actual vs forecast, deal preview and save; the report codes of §5.4 for FCS; SF-17 screens and SF-18 | 10 |
| 22 | AIX | AI assistance under human control | BS-4 | CTR, RPS | none | T-AI-01 and 02; API-R-47 and `POST /tenant/ai/disable`; provider interface DG-AI-01 to 09 with `FakeProvider` and the Anthropic adapter tested only against a mocked SDK client; `AI_TASK`; contract review proposals and acceptance; explain narratives with number validation; anomaly flags; revenue Q&A with citations; budget and kill switch; SF-20 screens, SF-28, SF-15:ai and SF-15:ai-call-log; DG-ARC-11; CTL-045 | 12 |
| 23 | SOP | Security, operability, controls evidence and release stamping | BS-1 | all earlier | none | T-PLT-39 and API-R-52 (control evidence registry); engine release stamping and `make release-manifest` (05 REL-01 to 06); `REPLAY_VERIFY` upgrade validation; rate limits; `GET /metrics`; privacy commands `user.anonymise` and `file.shred` (05 PRV-07); `erev doctor` complete (05 SAR-40, REL-07); an audit coverage test over every action of REQ-PLT-019; SAR-42 security tests; the security documents and `itgc-guide.md` (BS-D-13); every `PENDING_` tuple empty (BS-D-07); `make controls-report` passes 49 of 49 | 10 |
| 24 | DMO | Demo world, onboarding surfaces and serial journeys | BS-4 | all earlier | none | (1) `erev seed demo` builds WLD-T-01 Avenmoor (PRD §2.5 to §2.9, with the WLD-X figures asserted by seed tests), WLD-T-02 to 07 (§2.10) and WLD-T-00 through migration mode (b) (§2.11), deterministically (REQ-DEMO-007) within NFR-08. (2) SF-25 guided tour with the SF-01 demo banner; SF-26. (3) The 21 serial journeys in E2E-04 order and J-24. (4) Every SCREENS §0.12 and SCREENS_B §15 row captured in its stated state. (5) `make e2e` unfiltered green with no project skipped | 34 |
| 25 | PRF | Performance | BS-4 | DMO | none | `erev_api.domain.demo.volume` generator; `make perf-seed` (DG-PERF-01); harness DG-PERF-02 to 08; `make perf`: close ≤ 600 s and every DG-PERF-03 endpoint p95 ≤ 300 ms | 6 |
| 26 | DEP | Deploy artifacts and guides | BS-4 | PRF | none | Dockerfiles (05 DPL-01 to 05), `deploy/compose.yaml` (DPL-10 to 16) and Terraform (DPL-30 to 42) with offline static tests; supervisor scripts of dev-guide §4.5; completed `runbook.md` (05 §7.7 RB entries), `user-guide.md` and `migration-guide.md`; OpenAPI current; a `SUPERVISOR VERIFICATION NEEDED` entry for every §4.5 target | 8 |
| 27 | REL | Release | BS-4 | all | none | Header §7 evidence table complete on a clean tree after the last commit; the PROMPT.md done conditions hold | 3 |

Membership counts per phase (generated):

| Order | Phase | Author | REQs built | CTLs | 04 tables | Route rows | Journeys | Answer keys closed | Golden cases | Make targets |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | FND | BS-1 | 12 | 0 | 3 | 0 | 0 | 0 | 0 | 22 |
| 2 | EKC | BS-2 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| 3 | PLF | BS-1 | 14 | 9 | 42 | 0 | 0 | 0 | 0 | 5 |
| 4 | WEB | BS-1 | 26 | 0 | 0 | 27 | 0 | 0 | 0 | 2 |
| 5 | ENA | BS-2 | 31 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 | RFD | BS-3 | 32 | 3 | 29 | 23 | 0 | 0 | 0 | 0 |
| 7 | ENB | BS-2 | 19 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 8 | ENC | BS-2 | 38 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 9 | END | BS-2 | 15 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 10 | AKS | BS-2 | 0 | 0 | 0 | 0 | 0 | 221 | 0 | 0 |
| 11 | CTR | BS-3 | 50 | 13 | 30 | 16 | 0 | 0 | 0 | 0 |
| 12 | DIN | BS-3 | 32 | 2 | 19 | 9 | 0 | 0 | 0 | 0 |
| 13 | GPA | BS-2 | 0 | 0 | 0 | 0 | 0 | 0 | 94 | 1 |
| 14 | EDS | BS-2 | 2 | 0 | 0 | 0 | 0 | 6 | 0 | 0 |
| 15 | CLO | BS-4 | 37 | 11 | 14 | 13 | 1 | 0 | 0 | 0 |
| 16 | RPS | BS-4 | 39 | 5 | 4 | 11 | 1 | 0 | 0 | 0 |
| 17 | SNP | BS-4 | 5 | 1 | 1 | 1 | 0 | 0 | 0 | 0 |
| 18 | LMG | BS-3 | 9 | 1 | 3 | 3 | 2 | 0 | 0 | 0 |
| 19 | GPB | BS-2 | 0 | 0 | 0 | 0 | 0 | 0 | 28 | 0 |
| 20 | PRP | BS-2 | 0 | 0 | 0 | 0 | 0 | 5 | 0 | 0 |
| 21 | FCS | BS-4 | 7 | 0 | 4 | 4 | 0 | 0 | 0 | 0 |
| 22 | AIX | BS-4 | 10 | 1 | 2 | 4 | 0 | 0 | 0 | 0 |
| 23 | SOP | BS-1 | 10 | 2 | 1 | 0 | 0 | 0 | 0 | 1 |
| 24 | DMO | BS-4 | 10 | 0 | 0 | 1 | 22 | 0 | 0 | 0 |
| 25 | PRF | BS-4 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 2 |
| 26 | DEP | BS-4 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | 6 |
| 27 | REL | BS-4 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| | **Total** | | **409** | **49** | **152** | **112** | **26** | **232** | **122** | **41** |

## 2. Author assignment

| Author | Phases | Scope (design brief) | Files |
|---|---|---|---|
| BS-1 | FND, PLF, WEB, SOP | Foundation and platform: backend kernel, authentication, MFA, OIDC mock, permissions and SoD, audit chain, approvals, idempotency, problems, jobs, outbox, notifications, webhooks, files, numbering, registry, explain infrastructure; frontend foundation, tokens, primitives, shell, design gallery; Playwright harness; seed scaffold; security and operations routes, observability, release manifest, API clients, privacy | `docs/build-spec/11-foundation-platform.md` (sections 01 FND, 03 PLF, 04 WEB, 23 SOP) |
| BS-2 | EKC, ENA, ENB, ENC, END, AKS, GPA, EDS, GPB, PRP | Engine: money, bundle, hashing, trace, stages 01 to 15 in ENGINE_SPEC order; parity runner and golden gate; property suite; answer-key runner and families | `docs/build-spec/12-engine.md` (sections 02 EKC, 05 ENA, 07 ENB, 08 ENC, 09 END, 10 AKS, 13 GPA, 14 EDS, 19 GPB, 20 PRP) |
| BS-3 | RFD, CTR, DIN, LMG | Reference data, contracts and data in: entities, calendars, periods, currencies and FX, accounts and role mapping, customers, products, policies registry, SSP studio, revenue policies; contract ingestion and events; computed versions; workbench, obligations, explain panel, estimates, modification wizard; import pipeline with legacy v1 and CSV, exception queue, integration mock adapters; legacy migration, including RPT-41 and RPT-42 (BS-D-06) | `docs/build-spec/13-reference-contracts-data.md` (sections 06 RFD, 11 CTR, 12 DIN, 18 LMG) |
| BS-4 | CLO, RPS, SNP, FCS, AIX, DMO, PRF, DEP, REL | Close, reports, forecast and AI, demo, deploy and release: period states, schedule release, journal runs, GL export adapters, reconciliations, close cockpit, reopen; report runs with IPE, report codes, disclosure pack, dashboards, evidence packs, audit log screens; forecasts, scenarios, sandbox; AI proposals and assistant; demo seeds and guided tour; perf-seed and perf; Dockerfiles, compose, Terraform, OpenAPI, runbook, user guide, migration guide; release | `docs/build-spec/14-close-reports-ai-demo-release.md` (sections 15 CLO, 16 RPS, 17 SNP, 21 FCS, 22 AIX, 24 DMO, 25 PRF, 26 DEP, 27 REL) |

## 3. Global ordering

Sequence: FND → EKC → PLF → WEB → ENA → RFD → ENB → ENC → END → AKS → CTR → DIN → GPA → EDS → CLO → RPS → SNP → LMG → GPB → PRP → FCS → AIX → SOP → DMO → PRF → DEP → REL.

Rules applied:

1. **Engine stages before their consumers.** Each engine phase ends before the first platform phase that calls it.
2. **Within a phase, APIs before screens.** An item that builds a screen follows the items that build every route the screen binds (SCREENS data-binding tables; 04 §15.3).
3. **Schema in 04 §18 dependency order.** A table's revision follows the revisions of every table it references (DG-MIG-03).
4. **Harness phases follow the capabilities they measure.** AKS follows `compute`; GPA follows the legacy v1 pipeline; GPB follows `legacy_je_summary` and migration mode (b); PRP follows close and reports; DMO journeys follow the seeded world.

| Consumer phase | Consumes | Why |
|---|---|---|
| EKC | FND registry (`POLICY_PARAMETERS`), enum mirrors, 03 register | DG-AK-32 cross-validation |
| PLF | EKC `rules.match` and `trace` | Approval routing and `AUTO-BOOTSTRAP`; explain service tests |
| WEB | PLF session, me, approvals, users, roles, SoD, API client and notification routes | Every WEB screen binds PLF routes |
| RFD | ENA `s05_allocation.resolve_ssp` and `s03_pob_builder.build_lines`; PLF approvals, registry and files; WEB components | SSP resolution, template tests, configuration lifecycle |
| CTR | END `compute`, verified by AKS; RFD reference data | Decision and fact-capture commands persist complete output bundles |
| DIN | CTR fact-capture commands; RFD products, templates and SSP books | Imports and adapters append events through commands |
| GPA | DIN legacy v1 pipeline; RFD preset | DG-PAR-04 replays the 14 golden steps through imports |
| CLO | EDS lock-snapshot and rollforward targets; CTR subledger postings; DIN control totals | Close gates, snapshots and journal runs |
| RPS | CLO journal runs, locks and snapshots; EDS projections | Reports read locked data and tie to journals |
| SNP | CLO transitions; CTR recomputation | 05 SBX-04 replays period states and recomputes groups |
| LMG | DIN pipeline; SNP sandboxes; RPS framework | Mode (b) replays into a sandbox; RPT-41 uses the framework |
| GPB | RPS `legacy_je_summary`; LMG mode (b) | `journal_entry_totals` and `point_in_time_equivalence` |
| PRP | CLO, RPS, GPB | P6, P7, P11 and the stateful machine exercise close, lock and reopen |
| FCS | SNP; RPS | Scenario tenants are sandboxes; forecast outputs are reports |
| AIX | CTR drafts; RPS report runs | Contract review creates drafts; Q&A cites report runs |
| SOP | every feature phase | Privacy commands, audit coverage and `erev doctor` span all tables |
| DMO | every capability the seeded world uses | The seed runs imports, approvals and close runs as personas (WLD-R-02) |
| PRF | CLO close runs; SNP snapshots | DG-PERF-02 restores a sandbox and measures the close |

## 4. Gate scope at phase exits

Every `GATE-<code>` item runs `make ci`, `make test-pg` and the gates of its row on a clean tree after the phase's last commit. "Unfiltered" means the target without selection variables. A failing selected case is fixed before the GATE item is ticked (DG-GATE-01); a gate is never weakened.

| GATE | `make e2e` | `make answer-keys` | `make parity` | `make properties` | `make controls-report` | `make perf-seed`, `make perf` | Extra evidence |
|---|---|---|---|---|---|---|---|
| GATE-FND | not yet | not yet | not yet | not yet | `--tags-only` inside `make lint` | no | `make setup` run twice with no change; `make backend` readiness 200, then stopped; `make fixtures CHECK=1` |
| GATE-EKC | not yet | loader and coverage unit tests inside `make ci` | not yet | unfiltered | inside `make lint` | no | none |
| GATE-PLF | not yet | as GATE-EKC | not yet | unfiltered | inside `make lint` | no | `make dev-up`, `GET /api/v1/readyz` 200, `make dev-down`; `make doctor` |
| GATE-WEB | unfiltered (BS-D-20) | as GATE-EKC | not yet | unfiltered | inside `make lint` | no | Light and dark screenshots of every WEB capture read and compared with SCREENS |
| GATE-ENA, GATE-RFD, GATE-ENB, GATE-ENC, GATE-END | unfiltered | as GATE-EKC | not yet | unfiltered | inside `make lint` | no | none |
| GATE-AKS, GATE-CTR, GATE-DIN | unfiltered | `ID=<§8.2.1 ids>` (221 keys) | not yet | unfiltered | inside `make lint` | no | none |
| GATE-GPA | unfiltered | `ID=<§8.2.1 ids>` | `K="initial_allocation or pob_position or contract_position or cumulative_catchup or probe-P3-over-delivery-validation"` (94 cases; B3-BS2-04) | unfiltered | inside `make lint` | no | Parity report counts by kind |
| GATE-EDS, GATE-CLO, GATE-RPS, GATE-SNP, GATE-LMG | unfiltered | `ID=<§8.2.1 and §8.2.2 ids>` (227 keys) | as GATE-GPA | unfiltered | inside `make lint` | no | none |
| GATE-GPB | unfiltered | as GATE-EDS | unfiltered (122 cases) | unfiltered | inside `make lint` | no | DEV sign-off listing (DG-PAR-08) |
| GATE-PRP, GATE-FCS, GATE-AIX | unfiltered | unfiltered (232 keys, zero gaps) | unfiltered | unfiltered | inside `make lint` | no | none |
| GATE-SOP | unfiltered | unfiltered | unfiltered | unfiltered | unfiltered (49 of 49) | no | `make release-manifest` without `STRICT`; every `PENDING_` tuple empty |
| GATE-DMO | unfiltered, no project skipped | unfiltered | unfiltered | unfiltered | unfiltered | no | `make seed` report and duration |
| GATE-PRF, GATE-DEP | unfiltered | unfiltered | unfiltered | unfiltered | unfiltered | yes | `make openapi` leaves no diff; guides and security documents present |
| REL items | header §7 | header §7 | header §7 | header §7 | header §7 | header §7 | header §7 |

## 5. Schema, API and registries by phase

### 5.1 04 tables (generated)

| Phase | 04 tables created (one revision per item, 04 §18 dependency order) | Count |
|---|---|---:|
| FND | T-PLT-11 `permission`, T-PLT-31 `registry_parameter`, T-REF-08 `currency` | 3 |
| PLF | T-PLT-01 `tenant`, T-PLT-02 `app_user`, T-PLT-03 `identity_provider`, T-PLT-04 `user_mfa_factor`, T-PLT-05 `user_recovery_code`, T-PLT-06 `security_event`, T-PLT-07 `tenant_membership`, T-PLT-08 `user_session`, T-PLT-09 `role`, T-PLT-10 `role_assignment`, T-PLT-12 `role_permission`, T-PLT-13 `sod_rule`, T-PLT-14 `sod_exception`, T-PLT-15 `api_client`, T-PLT-16 `api_token`, T-PLT-17 `approval_request`, T-PLT-18 `approval_step`, T-PLT-19 `audit_event`, T-PLT-20 `approval_decision`, T-PLT-21 `approval_delegation`, T-PLT-22 `audit_chain_head`, T-PLT-23 `audit_chain_verification`, T-PLT-24 `notification`, T-PLT-25 `notification_preference`, T-PLT-26 `numbering_series`, T-PLT-27 `job`, T-PLT-28 `idempotency_record`, T-PLT-29 `file_object`, T-PLT-30 `file_attachment`, T-PLT-32 `registry_version`, T-PLT-33 `support_grant`, T-PLT-35 `webhook_endpoint`, T-PLT-36 `webhook_delivery`, T-PLT-37 `saved_view`, T-PLT-38 `engine_release`, T-PLT-40 `access_review_campaign`, T-PLT-41 `access_review_item`, T-PLT-42 `password_reset_token`, T-REF-24 `rule_set`, T-REF-25 `rule_set_version`, T-REF-26 `rule`, T-REF-27 `rule_test_case` | 42 |
| RFD | T-REF-01 `legal_entity`, T-REF-02 `book`, T-REF-03 `entity_book`, T-REF-04 `fiscal_calendar`, T-REF-05 `period`, T-REF-06 `period_state`, T-REF-07 `period_state_transition`, T-REF-09 `tenant_currency`, T-REF-10 `fx_rate_set`, T-REF-11 `fx_rate_set_version`, T-REF-12 `fx_rate`, T-REF-13 `gl_account`, T-REF-14 `account_mapping_version`, T-REF-15 `account_mapping_rule`, T-REF-16 `dimension_definition`, T-REF-17 `dimension_value`, T-REF-18 `related_party_group`, T-REF-19 `customer`, T-REF-20 `product`, T-REF-21 `product_bundle_component`, T-REF-22 `pob_template`, T-REF-23 `pob_template_version`, T-REF-28 `ssp_book`, T-REF-29 `ssp_book_version`, T-REF-30 `ssp_entry`, T-REF-31 `ssp_range`, T-REF-32 `ssp_calculator_run`, T-REF-33 `ssp_calculator_result`, T-REF-34 `ssp_calculator_exclusion` | 29 |
| CTR | T-CON-01 `contract`, T-CON-03 `combination_group`, T-CON-04 `combination_group_member`, T-CON-05 `contract_event`, T-CON-06 `modification`, T-CON-07 `contract_computation`, T-CON-08 `contract_version`, T-CON-09 `contract_version_balance`, T-CON-10 `obligation`, T-CON-11 `obligation_version`, T-CON-12 `estimate`, T-CON-13 `estimate_version`, T-CON-14 `material_right`, T-CON-15 `contract_cost_asset`, T-CON-16 `cost_asset_version`, T-CON-17 `loss_provision_version`, T-CON-18 `fx_layer_movement`, T-CON-19 `judgement_record`, T-CON-20 `contract_hold`, T-CON-21 `portfolio`, T-CON-22 `portfolio_member`, T-CON-23 `policy_override`, T-CON-24 `event_submission`, T-ENG-01 `schedule`, T-ENG-02 `schedule_line`, T-ENG-03 `calc_trace`, T-SL-01 `subledger_posting`, T-SL-02 `subledger_posting_seal`, T-SL-03 `ledger_chain_head`, T-SL-04 `subledger_line` | 30 |
| DIN | T-SRC-01 `source_record`, T-SRC-02 `source_order`, T-SRC-03 `source_order_line`, T-SRC-04 `source_invoice`, T-SRC-05 `source_invoice_line`, T-SRC-06 `source_usage`, T-SRC-07 `source_payment`, T-SRC-08 `source_match`, T-CON-02 `contract_source_link`, T-IMP-01 `import_template`, T-IMP-02 `import_upload`, T-IMP-03 `import_row`, T-IMP-04 `import_row_lineage`, T-IMP-05 `exception_item`, T-IMP-06 `import_mapping_profile`, T-INT-01 `integration_connection`, T-INT-02 `sync_run`, T-INT-03 `outbox_message`, T-INT-04 `external_id_map` | 19 |
| CLO | T-SL-05 `manual_adjustment`, T-SL-06 `journal_run`, T-SL-07 `journal_batch`, T-SL-08 `journal_entry`, T-SL-09 `journal_line`, T-SL-10 `posting_ack`, T-CLS-01 `close_run`, T-CLS-02 `close_checklist_template`, T-CLS-03 `close_checklist_item`, T-CLS-04 `period_lock`, T-CLS-05 `lock_snapshot`, T-CLS-06 `reconciliation`, T-CLS-07 `reconciliation_item`, T-CLS-08 `signoff` | 14 |
| RPS | T-RPT-01 `report_definition`, T-RPT-02 `report_run`, T-RPT-03 `disclosure_snapshot`, T-RPT-04 `evidence_pack` | 4 |
| SNP | T-PLT-34 `tenant_snapshot` | 1 |
| LMG | T-MIG-01 `migration_batch`, T-MIG-02 `migrated_legacy_row`, T-MIG-03 `migration_reconciliation_line` | 3 |
| FCS | T-FC-01 `scenario`, T-FC-02 `forecast_event_set`, T-FC-03 `forecast_run`, T-FC-04 `deal_preview` | 4 |
| AIX | T-AI-01 `ai_proposal`, T-AI-02 `ai_model_log` | 2 |
| SOP | T-PLT-39 `control_execution` | 1 |

Step 0001 of 04 §18 (schema `erev`, domains TY-01 to TY-10, sequences, RLS helper functions, `tg_forbid_mutation`, `tg_touch`) is FND. The Procrastinate objects in `public` (DG-MIG-09) are PLF.

### 5.2 API resource catalogue (04 §15.3)

| Phase | API-R rows; a row whose routes span phases is listed in each, with its routes named |
|---|---|
| FND | API-R-53 (`GET /healthz`, `GET /readyz`, `GET /openapi.json`) |
| PLF | API-R-01, 02, 03, 04 (`GET, PATCH /tenant`), 05, 06, 07, 08, 09, 10, 11, 12, 14, 15, 16, 51, 54 |
| RFD | API-R-13, 17, 18 (calendars, `generate-year`, period reads, `open`), 19, 20, 21, 22, 23, 24, 25, 26, 27, 57 |
| CTR | API-R-28, 29, 30, 31, 32, 33, 34, 35, 36, 49, 55 |
| DIN | API-R-43, 44, 45, 56 |
| CLO | API-R-18 (`cockpit`, `checklist`, close, lock, reopen and permanent-lock commands, `locks`, `transitions`), 37, 38, 39, 40 |
| RPS | API-R-41, 42, 50 |
| SNP | API-R-04 (`snapshots`, `sandboxes`, `reset`) |
| LMG | API-R-48 |
| FCS | API-R-46 |
| AIX | API-R-47; API-R-04 (`POST /tenant/ai/disable`) |
| SOP | API-R-52; API-R-53 (`GET /metrics`) |

In-process mock routes under `/api/v1/__mocks__/<adapter>` (D-72; DG-API-09): the OIDC IdP in PLF; Salesforce, Stripe and the NetSuite chart-of-accounts endpoints in DIN; the NetSuite and QuickBooks Online journal export and trial balance endpoints in CLO.

### 5.3 Registries and provisioning seed

| Phase | E-08 approval subjects (`SUBJECTS`) | E-14 job kinds (handlers) | E-70 outbox topics | 04 §14.3 provisioning rows added |
|---|---|---|---|---|
| PLF | `ROLE_CHANGE`, `ROLE_ASSIGNMENT`, `SOD_EXCEPTION`, `SUPPORT_GRANT` | `AUDIT_CHAIN_VERIFY`, `OUTBOX_RELAY`, `WEBHOOK_DELIVERY`, `EMAIL_DELIVERY`, `RETENTION_SWEEP` | `WEBHOOK`, `EMAIL` | `tenant`; `audit_chain_head`; `numbering_series` for every T-PLT-26 code; the ten default roles and their permissions; `sod_rule` SoD-1 to SoD-7; `registry_version` DEFAULT per category; admin user, membership and role assignment approved by `AUTO-BOOTSTRAP`; invitation `outbox_message`; rule set `AUTO-BOOTSTRAP` |
| RFD | `SSP_BOOK_VERSION`, `REGISTRY_VERSION`, `RULE_SET_VERSION`, `POB_TEMPLATE_VERSION`, `ACCOUNT_MAPPING_VERSION`, `FX_RATE_SET_VERSION`, `PRINCIPAL_AGENT_CHANGE` | `SSP_CALCULATOR` | none | `book` rows `ASC606`, `IFRS15`, `LEGACY`; built-in `dimension_definition` rows; `tenant_currency` for the reporting currency; JE numbering series when an entity is created |
| CTR | `SSP_OVERRIDE`, `CONTRACT_ACTIVATION`, `MODIFICATION`, `MANUAL_EVENT`, `ESTIMATE_VERSION`, `CONTRACT_VOID`, `COMBINATION_GROUP`, `JUDGEMENT_RECORD`, `ATTRIBUTE_CHANGE`, `POLICY_OVERRIDE` | `CONTRACT_COMPUTE`, `POLICY_SIMULATION` | none | `ledger_chain_head` per book |
| DIN | `IMPORT_COMMIT`, `EXCEPTION_WAIVER`, `MAPPING_PROFILE_VERSION` | `IMPORT_VALIDATE`, `IMPORT_DIFF`, `IMPORT_COMMIT`, `SYNC_RUN` | `SYNC_REQUEST` | none |
| CLO | `PERIOD_LOCK`, `PERIOD_REOPEN`, `JOURNAL_RUN`, `MANUAL_ADJUSTMENT` | `CLOSE_RUN`, `JOURNAL_RUN_CALCULATE`, `JOURNAL_EXPORT`, `RECONCILIATION_GENERATE`, `PERIOD_OPEN_REDIRTY` | `JOURNAL_EXPORT` | system `close_checklist_template` rows for every gate check code |
| RPS | none | `REPORT_RUN`, `EVIDENCE_PACK` | none | none |
| SNP | none | `TENANT_SNAPSHOT`, `SANDBOX_RESET` | none | none |
| LMG | `MIGRATION_PROMOTION`, `MIGRATION_SSP_REPLAY` | `MIGRATION_IMPORT`, `MIGRATION_RECONCILE` | none | none |
| FCS | none | `FORECAST_RUN`, `DEAL_PREVIEW` | none | none |
| AIX | `AI_PROPOSAL_ACCEPTANCE` | `AI_TASK` | none | none |
| SOP | `EVIDENCE_SHRED` | `REPLAY_VERIFY` | none | none |
| Totals | 32 of 32 E-08 values | 27 of 27 E-14 values | 4 of 4 E-70 values | 04 §14.3 complete after CLO |

`PAYLOADS` covers every E-03 event type from the first CTR item that appends events. `JOB_QUEUE` equals the 05 §5.6 execution profile table from its creation in PLF.

### 5.4 Report codes (generated)

| Phase | Report codes (04 T-RPT-01; SCREENS_B §5.6 specification id) | Count |
|---|---|---:|
| RPS | `revenue_waterfall` (RPT-01), `contract_balances` (RPT-02), `contract_balance_rollforward` (RPT-03), `revenue_from_opening_liability` (RPT-04), `revenue_from_prior_period_obligations` (RPT-05), `rpo` (RPT-06), `rpo_rollforward` (RPT-07), `disaggregation` (RPT-08), `contract_history` (RPT-09), `legacy_contract_history_export` (RPT-10), `latest_contract_status` (RPT-11), `legacy_latest_contract_export` (RPT-12), `legacy_je_summary` (RPT-13), `modification_register` (RPT-14), `je_population` (RPT-15), `out_of_period_register` (RPT-16), `late_entry_report` (RPT-17), `manual_adjustment_register` (RPT-18), `ssp_change_log` (RPT-19), `ssp_version_diff` (RPT-20), `allocations_by_ssp_version` (RPT-21), `ssp_override_listing` (RPT-22), `config_change_register` (RPT-23), `user_access_listing` (RPT-24), `sod_conflict_report` (RPT-25), `approvals_register` (RPT-26), `api_client_inventory` (RPT-27), `judgement_register` (RPT-28), `estimate_change_listing` (RPT-29), `scope_exclusion_register` (RPT-30), `loss_provision_register` (RPT-31), `contract_cost_rollforward` (RPT-32), `book_bridge` (RPT-33), `adoption_bridge` (RPT-34), `intercompany_pairs` (RPT-35), `balance_aging` (RPT-36), `bookings_billings_revenue` (RPT-37), `variance_between_closes` (RPT-38), `audit_log_export` (RPT-43), `chain_verification_report` (RPT-44), `extract_contracts` (RPT-45), `extract_obligations` (RPT-46), `extract_contract_versions` (RPT-47), `extract_schedule_lines` (RPT-48), `extract_subledger_lines` (RPT-49), `extract_journal_lines` (RPT-50), `extract_balances` (RPT-51), `extract_events` (RPT-52), `extract_legacy_contract_live` (RPT-53), `period_evidence_pack` (RPT-54), `contract_sample_pack` (RPT-55), `disclosure_pack` (SCREENS_B §5.4) | 52 |
| LMG | `migration_reconciliation` (RPT-41), `parallel_run_comparison` (RPT-42) | 2 |
| FCS | `forecast_outputs` (RPT-39), `actual_vs_forecast` (RPT-40) | 2 |

## 6. Requirements by build phase (generated)

Each release-1.0 row of 03 §3 appears once, under its build phase (BS-D-19). The 25 release-`later` rows are not built; where a later row says "Reserve:", the reserved hook is built by the phase that creates its table or enumeration (03 §1.2 rule 3).

### 6.1 FND (BS-1): 12 requirements (PLT 3, CTL 1, SEC 3, OPS 3, UX 2)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-PLT-028 | P0 | Problem details | UNIT |
| REQ-PLT-031 | P0 | Money representation | UNIT; PROP:P1-P4 |
| REQ-PLT-032 | P0 | OpenAPI 3.1 | ART |
| REQ-CTL-001 | P0 | Controls report | ART |
| REQ-SEC-003 | P0 | Secrets | UNIT; ART |
| REQ-SEC-009 | P0 | No licence keys or kill switch | UNIT |
| REQ-SEC-010 | P0 | Dependency licence gate | ART |
| REQ-OPS-005 | P0 | Health and logs | UNIT |
| REQ-OPS-007 | P0 | Gate targets | ART |
| REQ-OPS-010 | P0 | Shared-machine constraints | ART |
| REQ-UX-010 | P0 | Vocabulary lint | ART |
| REQ-UX-011 | P0 | Design lint | ART |

### 6.2 EKC (BS-2): 1 requirements (REC 1)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-REC-019 | P0 | Cumulative rounding | PROP:P4; AK (re-baselined keys) |

### 6.3 PLF (BS-1): 14 requirements (PLT 12, SEC 1, OPS 1)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-PLT-001 | P0 | Pooled tenancy with forced RLS | PG; CTL-036 |
| REQ-PLT-002 | P0 | RLS catalog lint | PG; CTL-036 |
| REQ-PLT-011 | P0 | Universal self-approval block | UNIT; CTL-014; CTL-034 |
| REQ-PLT-014 | P0 | Stale-approval invalidation | UNIT; CTL-007 |
| REQ-PLT-018 | P0 | Hash-chained audit log | PG; CTL-038 |
| REQ-PLT-020 | P0 | Audit chain verification | PG; CTL-039 |
| REQ-PLT-026 | P0 | Idempotency-Key | UNIT; PROP:P9; CTL-001 |
| REQ-PLT-027 | P0 | Optimistic concurrency | UNIT |
| REQ-PLT-029 | P0 | Async jobs | UNIT |
| REQ-PLT-034 | P2 | Outbound webhooks | UNIT |
| REQ-PLT-035 | P1 | Attachments | UNIT |
| REQ-PLT-038 | P0 | Operator tenant provisioning | UNIT; E2E |
| REQ-SEC-012 | P1 | Upload safety | UNIT |
| REQ-OPS-006 | P0 | Job monitoring | UNIT; CTL-040 |

### 6.4 WEB (BS-1): 26 requirements (PLT 11, CTL 1, SEC 2, OPS 1, UX 11)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-PLT-004 | P0 | Password authentication | UNIT; CTL-033 |
| REQ-PLT-005 | P0 | TOTP MFA | UNIT; E2E; CTL-033 |
| REQ-PLT-006 | P1 | OIDC login | UNIT |
| REQ-PLT-008 | P0 | Permissions and default roles | UNIT; E2E |
| REQ-PLT-009 | P1 | Custom roles | UNIT |
| REQ-PLT-010 | P0 | Preventive SoD engine | UNIT; CTL-034 |
| REQ-PLT-013 | P0 | Approval engine | UNIT; CTL-005; CTL-007; CTL-014 |
| REQ-PLT-017 | P1 | Bulk approval | UNIT; E2E |
| REQ-PLT-021 | P1 | Notifications | UNIT; E2E |
| REQ-PLT-033 | P1 | API clients | UNIT; CTL-037 |
| REQ-PLT-036 | P1 | Operator support access | UNIT; PG; CTL-035 |
| REQ-CTL-006 | P1 | Access review campaign | UNIT |
| REQ-SEC-004 | P0 | Web session security | UNIT; E2E |
| REQ-SEC-008 | P0 | No outbound network by default | UNIT; E2E |
| REQ-OPS-016 | P1 | Developer settings | E2E |
| REQ-UX-001 | P0 | Navigation | E2E |
| REQ-UX-002 | P0 | Shell | E2E |
| REQ-UX-006 | P0 | Accounting number format | E2E; UNIT |
| REQ-UX-007 | P0 | Themes and accessibility | E2E |
| REQ-UX-008 | P1 | Density modes | E2E |
| REQ-UX-009 | P1 | Grid interaction | E2E |
| REQ-UX-012 | P0 | Maker-checker views | E2E |
| REQ-UX-013 | P0 | Approvals inbox | E2E |
| REQ-UX-016 | P1 | Teaching empty states | E2E |
| REQ-UX-021 | P1 | Async progress | E2E |
| REQ-UX-022 | P1 | Locale formatting | UNIT; E2E |

### 6.5 ENA (BS-2): 31 requirements (SSP 2, POB 11, TP 10, ALC 8)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-SSP-004 | P0 | Legacy range formula | GT:initial_allocation; GT-01; GT-02; TC-setup-03 to 06; TC-06 |
| REQ-SSP-005 | P0 | Range policy | AK:S4-SSPRANGE-OWN; GT-01; GT-02 |
| REQ-POB-001 | P0 | POB builder | AK:S2-EX11-CASEA-OWNPRICES |
| REQ-POB-002 | P0 | $0 POBs | GT-02; GT:initial_allocation |
| REQ-POB-003 | P0 | Distinct value domain | TC-13; UNIT |
| REQ-POB-004 | P0 | Continuous POB identity | GT:pob_position; UNIT |
| REQ-POB-005 | P0 | Series | AK:S2-EX12A-OWNVOLUMES |
| REQ-POB-008 | P0 | Warranties | AK:S2-WARRANTY-OWN |
| REQ-POB-009 | P0 | Principal vs agent | AK:S2-EX45-AGENT |
| REQ-POB-010 | P0 | Licences of IP | AK:S2-EX61; AK:S2-EX59 |
| REQ-POB-011 | P0 | Shipping and handling election | AK:S2-SHIPPING-OWN |
| REQ-POB-012 | P1 | Immaterial promises | UNIT |
| REQ-POB-013 | P0 | Franchisor expedient | AK:S12-FRANCHISOR-OWN |
| REQ-TP-001 | P0 | Transaction price build-up | UNIT; AK:S3-EX21-EXTENDED |
| REQ-TP-002 | P0 | Variable consideration elements | AK:S3-EX21-EXTENDED |
| REQ-TP-003 | P0 | Constraint | AK:S3-EX23; AK:S10-DISCLOSURES |
| REQ-TP-008 | P0 | Expected returns | AK:S3-EX22; AK:S3-EX26 |
| REQ-TP-010 | P0 | Volume rebates and tiers | AK:S3-EX24 |
| REQ-TP-011 | P0 | Significant financing component | AK:S3-EX29; AK:S3-EX28-CASEB; AK:S3-EX26 |
| REQ-TP-012 | P0 | Noncash consideration | AK:S3-EX31 |
| REQ-TP-013 | P0 | Consideration payable to a customer | AK:S3-EX32 |
| REQ-TP-014 | P0 | Sales taxes | AK:S3-SALESTAX-OWN |
| REQ-TP-015 | P0 | Implicit price concessions | AK:S1-EX2 |
| REQ-ALC-001 | P0 | Relative-SSP allocation | GT:initial_allocation; AK:S4-EX33; PROP:P1; CTL-012 |
| REQ-ALC-002 | P0 | Largest remainder | TC-setup-08; TC-setup-09; PROP:P2; PROP:P3; CTL-012 |
| REQ-ALC-003 | P0 | Exact ratios | PROP:P2; UNIT |
| REQ-ALC-004 | P0 | Discount exception | AK:S4-EX34 |
| REQ-ALC-005 | P0 | VC allocation exception | AK:S4-EX35 |
| REQ-ALC-006 | P0 | Residual approach | AK:S4-EX33 |
| REQ-ALC-007 | P0 | Allocation pipeline order | AK:S4-EX33 to EX35 |
| REQ-ALC-008 | P1 | Allocation adjustment measure | UNIT |

### 6.6 RFD (BS-3): 32 requirements (PLT 2, REF 14, SSP 7, POL 7, BK 1, CLS 1)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-PLT-012 | P1 | Entity-scoped access | UNIT; PG |
| REQ-PLT-016 | P1 | Rule-based auto-approval | UNIT; CTL-005 |
| REQ-REF-001 | P0 | Legal entities | UNIT |
| REQ-REF-002 | P0 | Monthly calendars | UNIT |
| REQ-REF-003 | P1 | Retail and 13-period calendars | UNIT |
| REQ-REF-004 | P0 | Currencies | UNIT; PROP:P1 |
| REQ-REF-005 | P0 | FX rate sets | UNIT; PROP:P12 |
| REQ-REF-006 | P1 | FX rate maintenance | UNIT |
| REQ-REF-007 | P0 | Chart of accounts | UNIT; CTL-020 |
| REQ-REF-008 | P0 | Account-role mapping | UNIT; TC-JE-12; CTL-020; CTL-031 |
| REQ-REF-009 | P1 | Dimensions | UNIT |
| REQ-REF-010 | P0 | Customers | UNIT |
| REQ-REF-011 | P1 | Related-party groups | UNIT |
| REQ-REF-012 | P0 | Products and SKUs | UNIT; CTL-028; CTL-031 |
| REQ-REF-013 | P1 | Bundles | UNIT |
| REQ-REF-016 | P1 | Tenant entity type and elections | UNIT |
| REQ-SSP-001 | P0 | Versioned SSP books | PG; CTL-011 |
| REQ-SSP-002 | P0 | SSP methods | UNIT |
| REQ-SSP-003 | P0 | SSP values | UNIT |
| REQ-SSP-006 | P0 | Effective-date resolution and override | UNIT; AK:S6-EX5-CASEB; CTL-010 |
| REQ-SSP-007 | P0 | SSP maker-checker | UNIT; CTL-010 |
| REQ-SSP-008 | P1 | SSP evidence | UNIT |
| REQ-SSP-009 | P1 | Historical SSP calculator | UNIT; E2E |
| REQ-POL-001 | P0 | POB templates | UNIT |
| REQ-POL-002 | P0 | Rule evaluation | UNIT |
| REQ-POL-003 | P0 | Configuration lifecycle | UNIT; CTL-031 |
| REQ-POL-004 | P0 | Tenant accounting policy set | UNIT; CTL-031 |
| REQ-POL-005 | P0 | Legacy-parity preset | GT:all kinds; `make parity` |
| REQ-POL-009 | P1 | Industry policy templates | UNIT; DEMO |
| REQ-POL-011 | P0 | Practical-expedient flags | UNIT; AK:S10-DISCLOSURES; CTL-027 |
| REQ-BK-001 | P0 | Three books | UNIT; PG |
| REQ-CLS-005 | P0 | Time zones | UNIT |

### 6.7 ENB (BS-2): 19 requirements (POB 1, TP 2, MOD 16)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-POB-007 | P0 | Material-right exercise policy | GT-15; TC-04 (continuation values) |
| REQ-TP-006 | P0 | Transaction price changes | AK:S4-EX6 |
| REQ-TP-007 | P0 | POB-specific price change | GT-11; GT:cumulative_catchup (step 09); TC-pob-vc-01 to 07, 08, 12 |
| REQ-MOD-003 | P0 | Separate contract | AK:S6-EX5-CASEA; TC-07 (fixed) |
| REQ-MOD-004 | P0 | Prospective | AK:S6-EX5-CASEB; AK:S6-EX7 |
| REQ-MOD-005 | P0 | Cumulative catch-up | AK:S6-EX8 |
| REQ-MOD-006 | P0 | Mixed | AK:S6-COMBINED-MOD-OWN |
| REQ-MOD-007 | P0 | Legacy prospective parity | GT-12; GT-13; GT-15; GT:cumulative_catchup (steps 10, 11, 13); TC-01 to TC-05 |
| REQ-MOD-008 | P0 | Legacy retrospective parity | GT-10; GT-14; GT:cumulative_catchup (steps 08, 12); TC-RM-01 to 03 |
| REQ-MOD-009 | P0 | Reductions | TC-09; TC-RM-15 |
| REQ-MOD-010 | P0 | Price-only change on satisfied POBs | TC-08 |
| REQ-MOD-011 | P0 | Terminations | AK-FAM:termination (FS-09, GE-08) |
| REQ-MOD-015 | P0 | Catch-up disclosure measures | GT:cumulative_catchup |
| REQ-MOD-016 | P1 | Unpriced change orders and claims | AK-FAM:construction (GE-02) |
| REQ-MOD-017 | P1 | Prepaid credit rollover | AK-FAM:usage-rollover |
| REQ-MOD-018 | P0 | Backdated modifications | TC-15; TC-RM-13; PROP:P11 |
| REQ-MOD-019 | P0 | Modification integrity | TC-10 to TC-12; TC-17; TC-20; TC-RM-09, 10, 14 |
| REQ-MOD-020 | P0 | Pre/post-modification boundary | AK:S4-EX6 |
| REQ-MOD-021 | P1 | Changing accounts, entity or SSP version | TC-RM-04 |

### 6.8 ENC (BS-2): 38 requirements (POB 1, TP 1, REC 20, BIL 9, CST 5, LOS 2)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-POB-006 | P0 | Material rights | AK:S2-EX49; AK:S2-EX52; AK:S2-EX51 |
| REQ-TP-018 | P1 | Concessions on billed amounts | TC-pob-vc-16; AK:S3-EX23 |
| REQ-REC-001 | P0 | Point in time | AK:S5-ACCEPTANCE-OWN; GT-16 |
| REQ-REC-002 | P0 | Over-time criteria | AK:S5-OVERTIME-OWN |
| REQ-REC-003 | P0 | Ratable time elapsed | AK:S2-EX11-CASEA-OWNPRICES (re-baselined) |
| REQ-REC-004 | P0 | Units delivered | GT:contract_position; GT:pob_position; GT-04; GT-16; TC-delivery-01 to 08, 20 |
| REQ-REC-005 | P0 | Milestones | AK:S5-PROGRESS-VARIANTS |
| REQ-REC-006 | P0 | Percent-complete events | AK:S5-PROGRESS-VARIANTS |
| REQ-REC-007 | P0 | Cost-to-cost with EAC | AK:S5-EX19; AK:S5-PROGRESS-VARIANTS |
| REQ-REC-008 | P1 | Labour-hours input | UNIT |
| REQ-REC-009 | P0 | Right to invoice | AK:S5-PROGRESS-VARIANTS |
| REQ-REC-010 | P0 | Usage and consumption | AK-FAM:usage (FS-02, TP-02); AK:S2-EX12A-OWNVOLUMES |
| REQ-REC-011 | P0 | Royalty exception | AK:S5-EX60 |
| REQ-REC-012 | P0 | Bill-and-hold | AK:S5-EX63-OWNSSP |
| REQ-REC-013 | P0 | Consignment | AK:S5-CONSIGNMENT-OWN |
| REQ-REC-014 | P0 | Customer acceptance | AK:S5-ACCEPTANCE-OWN |
| REQ-REC-015 | P1 | Repurchase agreements | AK:S5-EX62 (classification) |
| REQ-REC-016 | P0 | Breakage | AK:S5-BREAKAGE-OWN |
| REQ-REC-017 | P0 | Nonrefundable upfront fees | AK:S5-UPFRONTFEE-OWN |
| REQ-REC-018 | P0 | One measure per POB | UNIT |
| REQ-REC-021 | P0 | Scheduled vs awaiting trigger | PROP:P7 (extended with the scheduled and awaiting-trigger split); UNIT |
| REQ-REC-026 | P0 | Progress edge cases | GT-05; GT-06; GT-09 |
| REQ-BIL-002 | P0 | Billing posting setting | AK:S9-PRESENTATION; GT:journal_entry_totals (`ERP`) |
| REQ-BIL-003 | P0 | Net position | GT:contract_position; GT-19; AK:S9-PRESENTATION; PROP:P6 |
| REQ-BIL-004 | P0 | Contract asset vs unbilled receivable | AK:S9-PRESENTATION (ex39); AK:S5-PROGRESS-VARIANTS |
| REQ-BIL-005 | P0 | Period-end netting reclass | GT-05; GT-06; GT-09; TC-JE-01; AK:S9-PRESENTATION (netting) |
| REQ-BIL-006 | P0 | Legacy reclass allocation key | GT-06; GT-09; TC-delivery-09; TC-19 |
| REQ-BIL-007 | P0 | Excluded from position | AK:S9-PRESENTATION; AK:S3-EX22; AK:S3-EX28-CASEB |
| REQ-BIL-008 | P1 | Cancellable-contract invoices | AK:S9-PRESENTATION (ex38) |
| REQ-BIL-010 | P1 | Current vs noncurrent | UNIT |
| REQ-BIL-012 | P1 | Cash receipts | UNIT; AK-FAM:fx |
| REQ-CST-002 | P0 | Capitalization | AK:S8-CONTRACT-COSTS |
| REQ-CST-003 | P0 | Amortization | AK:S8-CONTRACT-COSTS (re-baselined) |
| REQ-CST-004 | P0 | Impairment | AK:S8-CONTRACT-COSTS (impairment) |
| REQ-CST-005 | P1 | Clawbacks and termination | AK-FAM:termination (FS-09) |
| REQ-CST-007 | P1 | Amortization period changes | UNIT |
| REQ-LOS-001 | P0 | 605-35 loss provision | AK:S7-LOSS-OWN |
| REQ-LOS-002 | P0 | IAS 37 onerous-contract variant | AK:S7-LOSS-OWN (IFRS variant) |

### 6.9 END (BS-2): 15 requirements (BK 4, FX 6, ENT 4, JE 1)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-BK-002 | P0 | IFRS switch list | AK (IFRS variants of S1, S2, S3, S8 keys) |
| REQ-BK-003 | P1 | Shared stages | PROP:P13; PERF |
| REQ-BK-004 | P0 | Delta posting | GT-07; GT-18 (delta); GT:journal_entry_totals (delta); TC-JE-02; TC-JE-08 |
| REQ-BK-005 | P0 | Pre-standard revenue as events | GT-23 (deviate); GT:legacy_probe (P2); TC-14; TC-RM-12; TC-pob-vc-13; TC-JE-10 |
| REQ-FX-001 | P0 | Currency roles | UNIT; AK-FAM:fx |
| REQ-FX-002 | P0 | Historical-rate liability layers | PROP:P12; AK-FAM:fx |
| REQ-FX-003 | P0 | Remeasuring monetary balances | PROP:P12; AK-FAM:fx |
| REQ-FX-004 | P0 | IFRIC 22 and US layer flag | AK-FAM:fx |
| REQ-FX-005 | P1 | Reporting translation | UNIT |
| REQ-FX-006 | P0 | Rate id stamping | UNIT; CTL-020 |
| REQ-ENT-001 | P0 | Contracting and performing entity | AK-FAM:multi-entity |
| REQ-ENT-002 | P0 | Per-entity netting | AK-FAM:multi-entity; PROP:P5 |
| REQ-ENT-003 | P0 | Intercompany pairs | AK-FAM:multi-entity; PROP:P5 |
| REQ-ENT-004 | P0 | Legacy cross-entity parity | UNIT; AK-FAM:multi-entity |
| REQ-JE-002 | P0 | Line pairs from one amount | PROP:P5; UNIT; CTL-022 |

### 6.10 AKS (BS-2): 0 requirements (none)

No requirement has this phase as its build phase; the phase closes hints of §15.

### 6.11 CTR (BS-3): 50 requirements (PLT 2, REF 2, SSP 2, POL 4, CON 18, TP 3, ALC 1, REC 2, MOD 5, BIL 1, CST 1, CLS 1, JE 1, RPT 1, DAT 2, UX 4)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-PLT-015 | P0 | Impact preview snapshot | UNIT; E2E |
| REQ-PLT-030 | P0 | Time-travel reads | UNIT; PROP:P11 |
| REQ-REF-014 | P0 | Unmapped products block | UNIT; TC-setup-20; CTL-003 |
| REQ-REF-015 | P0 | Pinned reference versions | UNIT; PROP:P8 |
| REQ-SSP-011 | P0 | Allocation lineage | UNIT; CTL-011 |
| REQ-SSP-014 | P0 | SSP snapshot on the POB | UNIT; CTL-011 |
| REQ-POL-006 | P1 | Policy impact simulation | UNIT; CTL-031 |
| REQ-POL-007 | P0 | Prospective by default | UNIT; PROP:P11; CTL-031 |
| REQ-POL-008 | P0 | Judgement records | UNIT; CTL-049 |
| REQ-POL-010 | P1 | Holds policies | UNIT |
| REQ-CON-001 | P0 | Contract header | UNIT |
| REQ-CON-002 | P0 | Status model | UNIT; AK:S1-EX1-CASEA |
| REQ-CON-003 | P0 | Step 1 and deposit accounting | AK:S1-EX1-CASEA; AK:S1-EX1-CASEB-C |
| REQ-CON-004 | P0 | Collectibility | AK:S1-EX1-CASEB-C |
| REQ-CON-005 | P0 | Activation gate | UNIT; CTL-004 |
| REQ-CON-006 | P0 | Contract approval routing | UNIT; CTL-005 |
| REQ-CON-007 | P0 | Field locks | UNIT; CTL-006 |
| REQ-CON-008 | P1 | Non-accounting attribute edits | UNIT |
| REQ-CON-009 | P0 | Contract combination | AK:S1-COMBINATION-OWN |
| REQ-CON-010 | P1 | Combination suggestions | UNIT |
| REQ-CON-012 | P1 | Regroup lines | UNIT |
| REQ-CON-013 | P0 | Enforceable term | AK-FAM:termination (GE-06, GE-08) |
| REQ-CON-014 | P0 | Immutable contract versions | PG; PROP:P8; CTL-047 |
| REQ-CON-015 | P0 | Contract void | UNIT; PG; CTL-046 |
| REQ-CON-016 | P1 | Scope flag | UNIT |
| REQ-CON-017 | P1 | Contract lists | E2E |
| REQ-CON-018 | P1 | Manual contract entry | E2E |
| REQ-CON-019 | P0 | Single transaction currency | UNIT |
| REQ-TP-004 | P0 | Estimate versions | UNIT; CTL-013 |
| REQ-TP-005 | P0 | Estimate maker-checker | UNIT; CTL-013 |
| REQ-TP-017 | P1 | Portfolio-scoped estimates | UNIT; AK-FAM:portfolio (JS-01, RB-01) |
| REQ-ALC-009 | P0 | Allocation walk | UNIT; E2E |
| REQ-REC-020 | P0 | Versioned schedules | UNIT; PERF |
| REQ-REC-022 | P1 | Recognition and export holds | UNIT; E2E |
| REQ-MOD-001 | P0 | Modification object | UNIT; CTL-007 |
| REQ-MOD-002 | P0 | Guided classification | AK:S6-EX5-CASEA; AK:S6-EX5-CASEB; AK:S6-EX7; AK:S6-EX8; AK:S6-COMBINED-MOD-OWN; CTL-007 |
| REQ-MOD-012 | P0 | Subscription changes | AK-FAM:subscription (FS-03, FS-04) |
| REQ-MOD-013 | P0 | Impact preview | UNIT; E2E; CTL-007 |
| REQ-MOD-022 | P0 | Whole-contract versioning | TC-10 (fixed); TC-REP-01 |
| REQ-BIL-009 | P1 | Billing plans | UNIT |
| REQ-CST-001 | P0 | Cost events | UNIT |
| REQ-CLS-004 | P0 | Late events | PROP:P11; UNIT; CTL-017 |
| REQ-JE-006 | P0 | Reversal-only corrections | PG; CTL-023; CTL-047 |
| REQ-RPT-018 | P0 | Explain | PROP:P14; E2E |
| REQ-DAT-012 | P0 | API commands | UNIT |
| REQ-DAT-014 | P0 | Manual event maker-checker | UNIT; CTL-009 |
| REQ-UX-003 | P0 | Record layout | E2E |
| REQ-UX-004 | P0 | Contract workbench content | E2E; DEMO |
| REQ-UX-005 | P0 | Explain panel | E2E |
| REQ-UX-015 | P1 | Contract spine | E2E |

### 6.12 DIN (BS-3): 32 requirements (SSP 1, CON 1, TP 2, ALC 1, REC 2, BIL 1, DAT 15, INT 8, UX 1)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-SSP-013 | P0 | Legacy SKU SSP import | GT (step 01); UNIT |
| REQ-CON-011 | P0 | Grouping policy for ingestion | UNIT |
| REQ-TP-009 | P0 | Legacy return rows | GT-08; TC-delivery-06, 15, 19, 20, 22 |
| REQ-TP-016 | P0 | Legacy VC rows | GT-02; GT-03; GT:pob_position (VC1 cases) |
| REQ-ALC-010 | P0 | Legacy split-upload deviation | TC-setup-11 |
| REQ-REC-024 | P0 | Over-delivery and over-billing block | GT-21; GT:legacy_probe (P3); TC-delivery-10; CTL-008 |
| REQ-REC-025 | P0 | Aggregating duplicate progress rows | GT-04; GT-22 (deviate); TC-delivery-13, 16 |
| REQ-BIL-001 | P0 | Invoice and credit-memo ingestion | UNIT |
| REQ-DAT-001 | P0 | Import pipeline | UNIT; CTL-001; CTL-044 |
| REQ-DAT-002 | P0 | Legacy v1 templates | TC-setup-21; TC-delivery-11; TC-18; TC-pob-vc-18; G3 |
| REQ-DAT-003 | P0 | Modification template modes | GT (steps 08-13) |
| REQ-DAT-004 | P0 | Modern CSV templates | UNIT |
| REQ-DAT-005 | P0 | Legacy silent defects made explicit | TC-setup-13 to 20, 22; TC-delivery-12 to 17; TC-RM-09, 10, 16; TC-pob-vc-10, 15; GT-22; GT-24; GT:legacy_probe (P1, P4) |
| REQ-DAT-006 | P0 | Row-level messages | TC-setup-20; TC-delivery-12 |
| REQ-DAT-007 | P0 | Cell coercion | UNIT |
| REQ-DAT-008 | P1 | Commit semantics | UNIT |
| REQ-DAT-009 | P0 | Exception queue | UNIT; E2E |
| REQ-DAT-010 | P0 | Interface control totals | UNIT; CTL-002 |
| REQ-DAT-011 | P0 | Source uniqueness | GT-24 (deviate); UNIT; CTL-001 |
| REQ-DAT-013 | P1 | Field mapping profiles | UNIT |
| REQ-DAT-015 | P0 | Dry-run diff | UNIT; E2E |
| REQ-DAT-016 | P1 | Template registry and download | E2E |
| REQ-DAT-017 | P0 | Existing contract on setup | TC-setup-22 |
| REQ-INT-001 | P0 | Canonical ingestion | UNIT; PROP:P9 |
| REQ-INT-002 | P0 | Adapter interface and contract tests | UNIT |
| REQ-INT-003 | P0 | Mock servers | UNIT |
| REQ-INT-004 | P1 | Salesforce orders adapter (mock) | UNIT |
| REQ-INT-005 | P1 | Stripe adapter (mock) | UNIT |
| REQ-INT-006 | P1 | Connection settings | UNIT |
| REQ-INT-007 | P1 | Reconciliation sweep | UNIT |
| REQ-INT-008 | P1 | Chart-of-accounts sync (mock) | UNIT |
| REQ-UX-014 | P0 | Import wizard | E2E |

### 6.13 GPA (BS-2): 0 requirements (none)

No requirement has this phase as its build phase; the phase closes hints of §15.

### 6.14 EDS (BS-2): 2 requirements (CST 1, FX 1)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-CST-006 | P0 | Contract cost rollforward | AK:S8-CONTRACT-COSTS; PROP:P6 |
| REQ-FX-007 | P0 | FX movement in rollforwards | PROP:P6; AK-FAM:fx |

### 6.15 CLO (BS-4): 37 requirements (REC 1, BIL 1, ENT 1, CLS 16, JE 17, INT 1)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-REC-023 | P1 | Manual release and defer | UNIT; CTL-014 |
| REQ-BIL-011 | P1 | Per-contract AR tie-out | UNIT |
| REQ-ENT-006 | P1 | Multi-entity close command | UNIT |
| REQ-CLS-001 | P0 | Period states | UNIT; CTL-015 |
| REQ-CLS-002 | P0 | Closed-period guard | PG; PROP:P11; CTL-015 |
| REQ-CLS-003 | P1 | Soft close | UNIT; CTL-015 |
| REQ-CLS-008 | P0 | Close cockpit | E2E; CTL-016 |
| REQ-CLS-009 | P0 | Close gates | UNIT; CTL-002; CTL-016; CTL-049 |
| REQ-CLS-010 | P0 | Lock snapshot | UNIT; PG |
| REQ-CLS-011 | P0 | Reopen with dual approval | UNIT; E2E; CTL-018 |
| REQ-CLS-012 | P0 | Close run orchestration | UNIT; PERF |
| REQ-CLS-013 | P0 | Incremental recompute and quarantine | UNIT; PERF |
| REQ-CLS-015 | P0 | Billing-to-subledger reconciliation | UNIT; CTL-024 |
| REQ-CLS-016 | P0 | Subledger-to-GL reconciliation | UNIT; CTL-025 |
| REQ-CLS-017 | P1 | Auto-certification | UNIT; CTL-026 |
| REQ-CLS-018 | P0 | Change in estimate vs error | UNIT |
| REQ-CLS-019 | P1 | Data-quality monitors | UNIT |
| REQ-CLS-020 | P2 | Close KPIs | UNIT |
| REQ-CLS-021 | P2 | Custom close tasks | UNIT |
| REQ-JE-001 | P0 | Balanced journal runs | PG; PROP:P5; CTL-022 |
| REQ-JE-003 | P0 | Journal data model | UNIT |
| REQ-JE-004 | P0 | Journal states | UNIT |
| REQ-JE-005 | P0 | Completeness assertions | UNIT; CTL-019 |
| REQ-JE-007 | P0 | Legacy gross format | GT:journal_entry_totals; GT-17; GT-18; TC-JE-01, 04, 06, 07, 08 |
| REQ-JE-008 | P0 | Date-range journal view | TC-JE-03; TC-JE-09; TC-JE-11 |
| REQ-JE-009 | P0 | Legacy imbalance deviations | GT-17 (deviate); GT-25; TC-JE-05; TC-JE-07; TC-JE-14; TC-JE-15 |
| REQ-JE-010 | P1 | Configurable journal grain | UNIT |
| REQ-JE-011 | P0 | GL export CSV | UNIT; ART |
| REQ-JE-012 | P0 | GL adapter interface | UNIT; CTL-021 |
| REQ-JE-013 | P0 | Transactional outbox | UNIT; PROP:P9; CTL-021 |
| REQ-JE-014 | P1 | NetSuite adapter (mock) | UNIT; CTL-021 |
| REQ-JE-015 | P1 | QuickBooks Online adapter (mock) | UNIT; CTL-021 |
| REQ-JE-016 | P0 | Posting receipts and lock block | UNIT; CTL-021 |
| REQ-JE-017 | P1 | Journal export hold | UNIT |
| REQ-JE-019 | P1 | Manual adjustments | UNIT; CTL-014 |
| REQ-JE-022 | P0 | Journal line validation | TC-JE-12; UNIT; CTL-020 |
| REQ-INT-009 | P1 | Trial balance pull (mock) | UNIT |

### 6.16 RPS (BS-4): 39 requirements (SSP 1, MOD 1, BIL 1, LOS 1, BK 2, ENT 1, CLS 2, JE 1, RPT 26, SEC 2, UX 1)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-SSP-012 | P1 | SSP reports | UNIT |
| REQ-MOD-014 | P0 | Modification register | UNIT |
| REQ-BIL-013 | P1 | Balance aging | UNIT |
| REQ-LOS-003 | P1 | Loss provision register | UNIT |
| REQ-BK-006 | P1 | Book-to-book bridge | UNIT |
| REQ-BK-007 | P1 | Adoption bridge report | AK:S11-MODRETRO-OWN |
| REQ-ENT-005 | P1 | Intercompany pair report | UNIT |
| REQ-CLS-006 | P0 | Out-of-period register | UNIT; CTL-017 |
| REQ-CLS-007 | P1 | Late-entry report | UNIT |
| REQ-JE-018 | P0 | JE population export | UNIT |
| REQ-RPT-001 | P0 | Standard report catalogue | UNIT |
| REQ-RPT-002 | P0 | Report run records | UNIT; CTL-029 |
| REQ-RPT-003 | P0 | Built-in tie-outs | UNIT; CTL-030 |
| REQ-RPT-004 | P0 | Revenue waterfall | UNIT; E2E; PROP:P7 |
| REQ-RPT-005 | P0 | Contract balances report | AK:S9-PRESENTATION; UNIT |
| REQ-RPT-006 | P0 | Contract balance rollforward | AK:S10-DISCLOSURES; PROP:P6 |
| REQ-RPT-007 | P0 | Revenue from opening contract liability | AK:S10-DISCLOSURES (rollforward_ex21) |
| REQ-RPT-008 | P0 | Revenue from prior-period POBs | AK:S10-DISCLOSURES (prior_period_pob_revenue_ex23B) |
| REQ-RPT-009 | P0 | RPO report | AK:S10-DISCLOSURES (rpo_ex42); PROP:P7; CTL-027 |
| REQ-RPT-010 | P0 | RPO rollforward | UNIT; CTL-030 |
| REQ-RPT-011 | P0 | Disaggregation report | AK:S10-DISCLOSURES (timing); CTL-028 |
| REQ-RPT-012 | P0 | Contract history report | TC-REP-01; TC-REP-02; TC-REP-04 to 06 |
| REQ-RPT-013 | P0 | Latest contract status report | TC-REP-03; TC-REP-07 |
| REQ-RPT-014 | P0 | Period evidence pack | UNIT; CTL-041 |
| REQ-RPT-015 | P1 | Contract sample pack | UNIT |
| REQ-RPT-016 | P0 | Home dashboard | E2E; DEMO |
| REQ-RPT-017 | P0 | Drill-down | E2E; UNIT |
| REQ-RPT-019 | P1 | Variance between closes | UNIT |
| REQ-RPT-020 | P1 | Bookings, billings and revenue metrics | UNIT |
| REQ-RPT-022 | P0 | Standard registers | UNIT |
| REQ-RPT-023 | P1 | Judgement and estimate registers | UNIT |
| REQ-RPT-024 | P0 | Export formats | UNIT |
| REQ-RPT-025 | P1 | Disclosure elections | UNIT |
| REQ-RPT-026 | P2 | Interim disclosure flag | UNIT |
| REQ-RPT-027 | P2 | IPE documentation export | UNIT |
| REQ-RPT-028 | P1 | Data extracts for BI | UNIT; ART |
| REQ-SEC-006 | P0 | Injection safety | TC-REP-04; TC-REP-05; UNIT |
| REQ-SEC-011 | P1 | Spreadsheet formula injection | UNIT |
| REQ-UX-017 | P2 | Favourites | E2E |

### 6.17 SNP (BS-4): 5 requirements (PLT 5)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-PLT-003 | P0 | Tenant types | UNIT; E2E |
| REQ-PLT-022 | P0 | Sandbox tenants cannot post | UNIT; CTL-043 |
| REQ-PLT-023 | P1 | Tenant snapshot to sandbox | UNIT; PG |
| REQ-PLT-024 | P0 | Restore only into sandbox | UNIT; CTL-043 |
| REQ-PLT-025 | P1 | Sandbox reset | UNIT |

### 6.18 LMG (BS-3): 9 requirements (MIG 9)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-MIG-001 | P0 | Legacy DB import: opening balances | UNIT; CTL-048 |
| REQ-MIG-002 | P0 | Legacy replay | GT (full UAT replay); CTL-048 |
| REQ-MIG-003 | P0 | Migration reconciliation report | UNIT; GT-20; GT:point_in_time_equivalence; CTL-048 |
| REQ-MIG-004 | P0 | Source file handling | TC-setup-25; UNIT |
| REQ-MIG-005 | P0 | Parity preset on migrated tenants | UNIT |
| REQ-MIG-006 | P0 | Legacy field mapping | UNIT |
| REQ-MIG-007 | P1 | Parallel-run comparison | UNIT |
| REQ-MIG-008 | P1 | Acquired contracts | UNIT; AK-FAM:business-combination |
| REQ-MIG-009 | P1 | Onboarding from other systems | UNIT |

### 6.19 GPB (BS-2): 0 requirements (none)

No requirement has this phase as its build phase; the phase closes hints of §15.

### 6.20 PRP (BS-2): 0 requirements (none)

No requirement has this phase as its build phase; the phase closes hints of §15.

### 6.21 FCS (BS-4): 7 requirements (FC 7)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-FC-001 | P1 | Scenario tenant | UNIT; CTL-043 |
| REQ-FC-002 | P1 | Forecast event sets | UNIT |
| REQ-FC-003 | P1 | Forecast outputs | UNIT |
| REQ-FC-004 | P1 | Forecast refresh | UNIT |
| REQ-FC-005 | P1 | Actual vs forecast | UNIT |
| REQ-FC-006 | P1 | Deal-desk allocation preview | UNIT; E2E |
| REQ-FC-007 | P1 | What-if modifications | UNIT |

### 6.22 AIX (BS-4): 10 requirements (AI 10)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-AI-001 | P0 | Provider interface | UNIT |
| REQ-AI-002 | P0 | Tenant enablement | UNIT; CTL-031 |
| REQ-AI-003 | P0 | Proposals, never writes | UNIT; CTL-045 |
| REQ-AI-004 | P0 | Configuration evidence | UNIT; CTL-045 |
| REQ-AI-005 | P1 | Contract review extraction | UNIT; E2E |
| REQ-AI-006 | P1 | Explain narrative | UNIT |
| REQ-AI-007 | P1 | Anomaly flags | UNIT |
| REQ-AI-008 | P1 | Revenue Q&A with citations | UNIT |
| REQ-AI-009 | P1 | Data minimization and budget | UNIT |
| REQ-AI-010 | P1 | Kill switch and failures | UNIT |

### 6.23 SOP (BS-1): 10 requirements (PLT 2, CTL 4, SEC 2, OPS 2)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-PLT-019 | P0 | Audit coverage | UNIT; CTL-038 |
| REQ-PLT-037 | P2 | API rate limits | UNIT |
| REQ-CTL-002 | P1 | Control evidence registry | UNIT; CTL-042 |
| REQ-CTL-003 | P0 | Release manifest and stamping | ART; UNIT; CTL-032 |
| REQ-CTL-004 | P1 | CUEC list and customer-operated ITGC guide | ART |
| REQ-CTL-005 | P1 | Deployment self-check | UNIT; PG |
| REQ-SEC-005 | P1 | Threat model and ASVS checklist | ART |
| REQ-SEC-007 | P1 | Personal data handling | UNIT; PG |
| REQ-OPS-011 | P1 | Upgrade validation replay | UNIT |
| REQ-OPS-012 | P2 | Metrics endpoint | UNIT |

### 6.24 DMO (BS-4): 10 requirements (UX 3, DEMO 7)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-UX-018 | P0 | Guided tour | E2E; DEMO |
| REQ-UX-019 | P1 | Legacy transition map | ART; E2E |
| REQ-UX-020 | P0 | Screens and role journeys | E2E |
| REQ-DEMO-001 | P0 | Six industry cluster tenants | DEMO |
| REQ-DEMO-002 | P0 | Legacy parity demo tenant | DEMO; GT:all kinds |
| REQ-DEMO-003 | P0 | Mandatory scenarios | DEMO |
| REQ-DEMO-004 | P0 | Fictitious names | DEMO |
| REQ-DEMO-005 | P0 | Demo users | DEMO; UNIT |
| REQ-DEMO-006 | P0 | Real data everywhere | DEMO; E2E |
| REQ-DEMO-007 | P1 | Deterministic generator | UNIT |

### 6.25 PRF (BS-4): 3 requirements (CLS 1, OPS 2)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-CLS-014 | P0 | Close performance | PERF |
| REQ-OPS-008 | P0 | Workbench latency | PERF |
| REQ-OPS-009 | P0 | Volume tenant generator | PERF |

### 6.26 DEP (BS-4): 7 requirements (SEC 2, OPS 5)

| REQ | Pri | Title | Acceptance hints (03 §1.4) |
|---|---|---|---|
| REQ-SEC-001 | P0 | TLS | ART |
| REQ-SEC-002 | P1 | Encryption at rest | ART |
| REQ-OPS-001 | P0 | Containers and compose | ART |
| REQ-OPS-002 | P0 | Terraform artifacts | ART |
| REQ-OPS-003 | P0 | Runbook | ART |
| REQ-OPS-004 | P0 | User and migration guides | ART |
| REQ-OPS-013 | P2 | DR objectives | ART |

### 6.27 REL (BS-4): 0 requirements (none)

No requirement has this phase as its build phase; the phase closes hints of §15.


## 7. Controls by phase (generated)

The phase writes the first test tagged `@pytest.mark.control("CTL-nnn")` that exercises the control's failure path (DG-TST-06). Later phases may add tagged tests for the same control.

| CTL | Control (03 §4.1) | Type | System feature (REQ) | Phase | Author |
|---|---|---|---|---|---|
| CTL-001 | Import uniqueness and idempotency: duplicates rejected before commit; command retries are safe | Prev · Auto | REQ-DAT-001, REQ-DAT-011, REQ-PLT-026 | DIN | BS-3 |
| CTL-002 | Interface control totals; a failed batch blocks lock | Det/Prev · Auto | REQ-DAT-010, REQ-CLS-009 | CLO | BS-4 |
| CTL-003 | Unmapped products blocked from activation and posting | Prev · Auto | REQ-REF-014 | CTR | BS-3 |
| CTL-004 | Contract activation gate | Prev · Auto | REQ-CON-005 | CTR | BS-3 |
| CTL-005 | Contract approval routing and rule-based auto-approval | Prev · Auto | REQ-CON-006, REQ-PLT-013, REQ-PLT-016 | CTR | BS-3 |
| CTL-006 | Active contract field locks | Prev · Auto | REQ-CON-007 | CTR | BS-3 |
| CTL-007 | Modification classification, approval and stale-approval voiding | Prev · Auto | REQ-MOD-001, REQ-MOD-002, REQ-MOD-013, REQ-PLT-013, REQ-PLT-014 | CTR | BS-3 |
| CTL-008 | Over-delivery and over-billing blocked | Prev · Auto | REQ-REC-024 | CTR | BS-3 |
| CTL-009 | Manual progress events require another user's approval; source tagged | Prev · Auto | REQ-DAT-014 | CTR | BS-3 |
| CTL-010 | SSP version maker-checker and override approval | Prev · Auto | REQ-SSP-006, REQ-SSP-007 | RFD | BS-3 |
| CTL-011 | Approved SSP immutability, no overlap, effective-date resolution, allocation lineage | Prev · Auto | REQ-SSP-001, REQ-SSP-011, REQ-SSP-014 | RFD | BS-3 |
| CTL-012 | Allocation invariant fails closed | Prev · Auto | REQ-ALC-001, REQ-ALC-002 | ENA | BS-2 |
| CTL-013 | Estimate change maker-checker with immutable versions | Prev · Auto | REQ-TP-004, REQ-TP-005 | CTR | BS-3 |
| CTL-014 | Manual adjustment maker-checker and universal self-approval block | Prev · Auto | REQ-JE-019, REQ-PLT-011, REQ-PLT-013, REQ-REC-023 | PLF | BS-1 |
| CTL-015 | Posting to locked periods blocked; soft-close restriction | Prev · Auto | REQ-CLS-001, REQ-CLS-002, REQ-CLS-003 | CLO | BS-4 |
| CTL-016 | Close gates before lock | Prev · Auto | REQ-CLS-008, REQ-CLS-009 | CLO | BS-4 |
| CTL-017 | Out-of-period items post to first open period with origin tag | Prev · Auto | REQ-CLS-004, REQ-CLS-006 | CTR | BS-3 |
| CTL-018 | Reopen requires dual approval; diff at re-lock | Prev/Det · Auto | REQ-CLS-011 | CLO | BS-4 |
| CTL-019 | Journal completeness assertions | Det/Prev · Auto | REQ-JE-005 | CLO | BS-4 |
| CTL-020 | Journal line validation: account, dimensions, entity, currency, FX rate id; mapping completeness | Prev · Auto | REQ-JE-022, REQ-REF-007, REQ-REF-008, REQ-FX-006 | CLO | BS-4 |
| CTL-021 | Idempotent GL export with acknowledgement matching; unacknowledged batches block lock | Det · Auto | REQ-JE-012, REQ-JE-013, REQ-JE-014, REQ-JE-015, REQ-JE-016 | CLO | BS-4 |
| CTL-022 | Journals balance per entity, book, currency and period (database constraint) | Prev · Auto | REQ-JE-001, REQ-JE-002 | CTR | BS-3 |
| CTL-023 | Posted lines corrected only by reversal or delta lines | Prev · Auto | REQ-JE-006 | CTR | BS-3 |
| CTL-024 | Billing-to-subledger reconciliation | Det · Auto + ITDM | REQ-CLS-015 | CLO | BS-4 |
| CTL-025 | Subledger-to-GL reconciliation computation and direct-GL-entry flagging | Det · Auto | REQ-CLS-016 | CLO | BS-4 |
| CTL-026 | Zero-variance auto-certification under an approved rule | Det · Auto | REQ-CLS-017 | CLO | BS-4 |
| CTL-027 | Expedient flag approval and RPO derived from allocations and schedules | Prev · Auto | REQ-POL-011, REQ-RPT-009 | RPS | BS-4 |
| CTL-028 | Disaggregation attributes mandatory; disaggregation ties to revenue journals | Prev/Det · Auto | REQ-REF-012, REQ-RPT-011 | RPS | BS-4 |
| CTL-029 | Report run records and reproducibility | Det · Auto | REQ-RPT-002 | RPS | BS-4 |
| CTL-030 | Built-in report tie-outs | Det · Auto | REQ-RPT-003, REQ-RPT-010 | RPS | BS-4 |
| CTL-031 | Configuration change approval, simulation and prospective effect | Prev · Auto | REQ-POL-003, REQ-POL-004, REQ-POL-006, REQ-POL-007, REQ-REF-008, REQ-REF-012, REQ-AI-002 | RFD | BS-3 |
| CTL-032 | Engine and report-definition release stamping; release manifest with gate evidence | Prev · Auto | REQ-CTL-003 | SOP | BS-1 |
| CTL-033 | MFA enforcement, lockout and session timeout | Prev · Auto | REQ-PLT-004, REQ-PLT-005 | PLF | BS-1 |
| CTL-034 | Preventive SoD and self-approval block | Prev · Auto | REQ-PLT-010, REQ-PLT-011 | PLF | BS-1 |
| CTL-035 | Operator support access only by tenant-approved, time-boxed grant | Prev/Det · Auto | REQ-PLT-036 | PLF | BS-1 |
| CTL-036 | Forced RLS tenant isolation and catalog lint | Prev · Auto | REQ-PLT-001, REQ-PLT-002 | PLF | BS-1 |
| CTL-037 | API credentials scoped, expiring and without approval rights | Prev · Auto | REQ-PLT-033 | PLF | BS-1 |
| CTL-038 | Append-only, hash-chained audit log with required coverage | Prev/Det · Auto | REQ-PLT-018, REQ-PLT-019 | PLF | BS-1 |
| CTL-039 | Audit chain verification and alerting | Det · Auto | REQ-PLT-020 | PLF | BS-1 |
| CTL-040 | Failed or stuck jobs detected, retried and alerted | Det · Auto | REQ-OPS-006 | PLF | BS-1 |
| CTL-041 | Period evidence pack with manifest and hashes | Det · Auto | REQ-RPT-014 | RPS | BS-4 |
| CTL-042 | Control evidence registry | Det · Auto | REQ-CTL-002 | SOP | BS-1 |
| CTL-043 | Sandbox tenants cannot post, export, convert or restore over production | Prev · Auto | REQ-PLT-022, REQ-PLT-024, REQ-FC-001 | SNP | BS-4 |
| CTL-044 | Import commit requires approval by a user other than the uploader | Prev · Auto | REQ-DAT-001 | DIN | BS-3 |
| CTL-045 | AI outputs are proposals; accepting is an audited human command; configuration evidence logged | Prev · Auto | REQ-AI-003, REQ-AI-004 | AIX | BS-4 |
| CTL-046 | Contract void by approval with reversal lines; no hard delete | Prev · Auto | REQ-CON-015 | CTR | BS-3 |
| CTL-047 | Immutable contract versions, subledger and import lineage (database-enforced) | Prev · Auto | REQ-CON-014, REQ-JE-006 | CTR | BS-3 |
| CTL-048 | Legacy migration reconciliation before promotion | Det · Auto | REQ-MIG-001, REQ-MIG-002, REQ-MIG-003 | LMG | BS-3 |
| CTL-049 | Judgement records reviewed before close | Prev · Auto | REQ-POL-008, REQ-CLS-009 | CLO | BS-4 |

Controls per phase: PLF 9; ENA 1; RFD 3; CTR 13; DIN 2; CLO 11; RPS 5; SNP 1; LMG 1; AIX 1; SOP 2.

## 8. Answer keys by phase

### 8.1 Families (generated)

| Family (`families[0]`, POLICIES §0.7) | Active | Engine runner | Platform runner | Withdrawn | Closes in |
|---|---:|---:|---:|---:|---|
| ALC | 10 | 10 | 0 | 0 | AKS |
| BRK | 6 | 6 | 0 | 0 | AKS |
| COST | 5 | 5 | 0 | 0 | AKS |
| CPC | 6 | 6 | 0 | 0 | AKS |
| DISC | 8 | 6 | 2 | 0 | EDS, PRP |
| DLT | 2 | 1 | 1 | 0 | AKS, PRP |
| ENT | 5 | 5 | 0 | 0 | AKS |
| FX | 11 | 11 | 0 | 0 | AKS |
| IFRS | 4 | 4 | 0 | 0 | AKS |
| JE | 12 | 12 | 0 | 0 | AKS |
| LATE | 3 | 3 | 0 | 0 | AKS |
| LOSS | 2 | 2 | 0 | 0 | AKS |
| MOD | 19 | 19 | 0 | 0 | AKS |
| MR | 12 | 12 | 0 | 0 | AKS |
| NCC | 1 | 1 | 0 | 0 | AKS |
| ONB | 3 | 3 | 0 | 0 | AKS |
| POB | 16 | 16 | 0 | 0 | AKS |
| POS | 11 | 9 | 2 | 2 | AKS, PRP |
| REC | 24 | 24 | 0 | 0 | AKS |
| RET | 7 | 7 | 0 | 0 | AKS |
| RND | 25 | 25 | 0 | 0 | AKS |
| ROY | 3 | 3 | 0 | 0 | AKS |
| SFC | 8 | 8 | 0 | 0 | AKS |
| SSP | 8 | 8 | 0 | 0 | AKS |
| STP1 | 5 | 5 | 0 | 0 | AKS |
| TAX | 2 | 2 | 0 | 0 | AKS |
| VC | 14 | 14 | 0 | 0 | AKS |
| **Total** | **232** | **227** | **5** | **2** | |

Family codes in any position (DG-AK-33 requires a key per code): ALC 45, BRK 9, COST 10, CPC 7, DISC 14, DLT 2, ENT 5, FX 15, IFRS 9, JE 53, LATE 4, LOSS 4, MOD 29, MR 16, NCC 1, ONB 7, PAR 15, POB 29, POS 63, REC 108, RET 15, RND 31, ROY 7, SFC 10, SSP 17, STP1 12, TAX 3, VC 39. `PAR` occurs only as a secondary family.

### 8.2 Key ids by closing phase (generated)

#### 8.2.1 AKS: 221 keys

| Family | Count | Key ids (`make answer-keys ID=<comma-separated ids>`) |
|---|---:|---|
| ALC | 10 | ALC-BR-06-DAAS-EMBEDDED-LEASE-ROUTED-OUT, ALC-CHK-002-GT01-GT03, ALC-CHK-032-S4-EX34-CASEC-ESTIMATED, ALC-CHK-032-S4-EX34-CASEC-REJECTED, ALC-CHK-033-S4-EX34-CASEB, ALC-CHK-034-S4-EX34-CASEA, ALC-CHK-118, ALC-S4-EX33, ALC-S4-EX35-CASEB, ALC-S4-EX6 |
| BRK | 6 | BRK-CAP-CREDITS-ROLLOVER-RENEWAL, BRK-CHK-111-LAPSED, BRK-CHK-111-RENEWED, BRK-JS-02-GIFT-CARDS-BREAKAGE-ESCHEAT, BRK-S5-BREAKAGE-OWN, BRK-WM-06-PLATFORM-CREDITS-BREAKAGE-RE-ESTIMATE |
| COST | 5 | COST-CAP-COMMISSION-EXPECTED-RENEWALS-IMPAIRMENT, COST-S8-CONTRACT-COSTS-EX1, COST-S8-CONTRACT-COSTS-EX2, COST-S8-CONTRACT-COSTS-EXPEDIENT, COST-S8-CONTRACT-COSTS-IMPAIRMENT |
| CPC | 6 | CPC-BR-07-CASEA-MDF-DISTINCT-SERVICE-FAIR-VALUE, CPC-BR-07-CASEB-MDF-EXCESS-OVER-FAIR-VALUE, CPC-CHK-120-SHARE-BASED-WARRANTS-NOT-PROBABLE, CPC-CHK-120-SHARE-BASED-WARRANTS-PROBABLE, CPC-CHK-133-S3-EX32, CPC-WM-03-BUYER-PROMOTIONS-NEGATIVE-REVENUE-TEST |
| DLT | 1 | DLT-NATIVE-SUBSCRIPTION-PRE-STANDARD-UPFRONT |
| ENT | 5 | ENT-CHK-070-CONTRACTING-ENTITY-RECOGNISES-REVENUE, ENT-CHK-070-INTERCOMPANY-PAIR-PERFORMING-ENTITY, ENT-CHK-071-CONTRACT-ASSET-HELD-BY-CONTRACTING-ENTITY, ENT-CROSS-CURRENCY-PAIR-GBP-CONTRACT-USD-PERFORMER, ENT-PER-ENTITY-NETTING-IN-A-COMBINED-GROUP |
| FX | 11 | FX-BHD-FUNCTIONAL-USD-CONTRACT-MINOR-UNITS, FX-CHK-080-LIABILITY-LAYERS-AT-HISTORICAL-RATES, FX-CHK-081-CONTRACT-ASSET-REMEASURED-TO-CLOSING-RATE, FX-CHK-082-REFUNDABLE-ADVANCE-MONETARY-OVERRIDE-VS-IFRIC22, FX-CHK-083-ENGINE-RECEIVABLE-REMEASUREMENT, FX-CHK-084-A-REFUND-LIABILITY-REMEASURED, FX-CHK-084-B-DEPOSIT-LIABILITY-REMEASURED, FX-CHK-084-C-CONSIDERATION-PAYABLE-REMEASURED, FX-JPY-CONTRACT-USD-FUNCTIONAL-MINOR-UNITS, FX-POL-160-IFRIC22-LAYER-DATE-ASC606-VS-IFRS15, FX-POL-161-FIFO-TWO-LAYERS-IN-ONE-PERIOD |
| IFRS | 4 | IFRS-S13-SWITCH-SHIPPING, IFRS-SW01-COLLECTIBILITY-THRESHOLD-PER-BOOK, IFRS-SW04-SHIPPING-FULFILMENT-ELECTION-VS-SEPARATE-OBLIGATION, IFRS-SW11-ONEROUS-CONTRACT-SCOPE-IFRS15-ONLY |
| JE | 12 | JE-CHK-021-S1-EX1-CASEC-DEPOSIT-TO-CONTRACT-LIABILITY, JE-CHK-023-S3-SALESTAX-OWN-ENGINE-BILLING, JE-CHK-024-S9-PRESENTATION-EX38-CASEA-CANCELLABLE, JE-CHK-024-S9-PRESENTATION-EX38-CASEB-NONCANCELLABLE, JE-CHK-025-S3-EX24-VOLUME-REBATE-REFUND-LIABILITY, JE-CHK-026-CHK-100-S3-EX21-EXTENDED-BONUS-CATCH-UP, JE-CHK-130-S8-CONTRACT-COSTS-EX2-AMORTISATION, JE-CHK-131-S8-EXPEDIENT-ONE-YEAR-COMMISSION-EXPENSED, JE-CHK-131-S8-IMPAIRMENT-AND-IFRS15-REVERSAL, JE-CHK-132-S7-LOSS-OWN-PROVISION-AND-RELEASE, JE-CHK-136-S3-EX29-ADVANCE-PAYMENT-ACCRETION, JE-CHK-138-S1-EX2-IMPLICIT-PRICE-CONCESSION-RECEIVABLE-CONTRA |
| LATE | 3 | LATE-CHK-090-GOLDEN-CONTRACT1-DELIVERY-AFTER-JANUARY-LOCK, LATE-CHK-091-TC-JE-11-EVENTS-RECORDED-OUT-OF-ORDER, LATE-POL-181-FX-LATE-DELIVERY-AT-EFFECTIVE-DATE-RATES |
| LOSS | 2 | LOSS-GE-03-LOSS-CONTRACT-PROVISION, LOSS-S7-LOSS-OWN |
| MOD | 19 | MOD-CHK-027-S6-EX8, MOD-CHK-028-S6-EX5-CASEB, MOD-CHK-042-D18, MOD-CHK-042-INCEPTION, MOD-CHK-043-S6-EX7, MOD-CHK-112, MOD-CHK-115, MOD-FS-03-CASEA-UPSELL-AT-SSP-SEPARATE, MOD-FS-03-CASEB-UPSELL-DISCOUNT-PROSPECTIVE, MOD-FS-09-CANCELLATION-REFUND-COMMISSION, MOD-FS-10-CLOUD-CONVERSION-CREDIT, MOD-GE-02-CHANGE-ORDERS-UNPRICED-AND-CLAIM, MOD-GE-08-PARTIAL-TERMINATION-FOR-CONVENIENCE, MOD-JS-06-AREA-DEVELOPMENT-SCHEDULE-REVISION, MOD-LEGACY-POBVC-GT11, MOD-LEGACY-PROS-GT12, MOD-LEGACY-RETRO-GT10, MOD-S6-COMBINED-MOD-OWN, MOD-S6-EX5-CASEA |
| MR | 12 | MR-CHK-050-CONTINUATION, MR-CHK-050-MODIFICATION, MR-CHK-051-S2-EX49-EXPIRY, MR-CHK-051-S2-EX49-REDEEM, MR-CHK-052-GT15-CONTINUATION, MR-CHK-052-GT15-MODIFICATION, MR-CHK-053-S2-EX52, MR-CHK-054-S2-EX49, MR-FS-04-EARLY-RENEWAL-PRICE-CAP, MR-JS-01-POS-PORTFOLIO-POINTS-REDEMPTION, MR-S2-EX51, MR-WM-07-PARTNER-AIRLINE-TICKETS-WITH-MILES |
| NCC | 1 | NCC-CHK-135-S3-EX31 |
| ONB | 3 | ONB-CHK-121-BUSINESS-COMBINATION-SUBSCRIPTION, ONB-RB-06-RELIEF-GRANT-ROUTED-OUT, ONB-S11-MODRETRO-OWN |
| POB | 16 | POB-BR-01-ROBOTS-PLATFORM-EXTENDED-WARRANTY, POB-CHK-134-S2-WARRANTY-OWN, POB-JS-05-CASEA-FRANCHISE-PUBLIC, POB-JS-05-CASEB-FRANCHISE-PRIVATE-EXPEDIENT, POB-S12-FRANCHISOR-OWN, POB-S2-EX11-CASEA-OWNPRICES, POB-S2-EX12A-OWNVOLUMES, POB-S2-EX45-AGENT-AGENT, POB-S2-EX45-AGENT-PRINCIPAL, POB-S2-EX59, POB-S2-EX61, POB-S2-SHIPPING-OWN-OFF, POB-S2-SHIPPING-OWN-ON, POB-WM-01-THIRD-PARTY-COMMISSIONS-NET, POB-WM-02-FIRST-PARTY-INVENTORY-GROSS, POB-WM-05-HOTEL-MERCHANT-VERSUS-AGENCY |
| POS | 9 | POS-CHK-010, POS-CHK-010-UNBILLED-RECEIVABLE-AND-CONTRACT-ASSET-SPLIT, POS-CHK-011-GT06, POS-CHK-011-GT06-CONTRACT2-SSP-DELIVERED-RECLASS, POS-CHK-012-S9-PRESENTATION-NETTING, POS-CHK-013-EXAMPLE-39-CONDITIONAL-RIGHT-ENGINE-BILLING, POS-CHK-013-S9-PRESENTATION-EX39, POS-CHK-014-S5-PROGRESS-VARIANTS-RIGHT-TO-INVOICE, POS-GE-07-RETAINAGE-PRESENTATION |
| REC | 24 | REC-BR-04-BILL-AND-HOLD-CUSTODIAL, REC-BR-05-CONSIGNMENT-SELL-THROUGH, REC-BR-08-CUSTOMISED-TOOLING-COST-TO-COST, REC-CHK-014-S5-PROGRESS-VARIANTS-RTI, REC-FS-01-SAAS-RAMP-ANNUAL-BILLING, REC-FS-06-TERM-LICENCE-RENEWAL-START-GATE, REC-FS-07-FIXED-FEE-EAC-HOURS-REVISION, REC-FS-08-TM-RIGHT-TO-INVOICE, REC-GE-01-EPC-UNINSTALLED-MATERIALS-ZERO-MARGIN, REC-JS-04-PAID-MEMBERSHIP-DAILY, REC-RB-03-DRG-IN-HOUSE-PATIENT-MONTH-END, REC-RB-05-CAPITATION-PMPM-RATE-AMENDMENT, REC-S5-ACCEPTANCE-OWN-OBJ, REC-S5-ACCEPTANCE-OWN-SUBJ, REC-S5-CONSIGNMENT-OWN, REC-S5-EX19, REC-S5-EX62-CASEB, REC-S5-EX63-OWNSSP, REC-S5-OVERTIME-OWN-OT, REC-S5-OVERTIME-OWN-PIT, REC-S5-PROGRESS-VARIANTS-COSTRECOVERY, REC-S5-PROGRESS-VARIANTS-WASTE, REC-S5-UPFRONTFEE-OWN-A, REC-S5-UPFRONTFEE-OWN-B |
| RET | 7 | RET-BR-03-PRICE-PROTECTION-STOCK-ROTATION, RET-CHK-029-S3-EX22, RET-CHK-060-S3-EX22-REVISED, RET-CHK-061-GT08, RET-CHK-116, RET-JS-03-ECOMMERCE-REFUND-RETURN-ASSET, RET-WM-04-REFUNDS-AND-CHARGEBACKS |
| RND | 25 | RND-CHK-001, RND-CHK-001-USD-EQUAL-SSP-THIRDS, RND-CHK-002-CHK-007-GT01-CONTRACT1, RND-CHK-003A, RND-CHK-003A-JPY-EQUAL-SSP-THIRDS, RND-CHK-003B, RND-CHK-003B-BHD-WEIGHTS-ONE-TWO, RND-CHK-003C, RND-CHK-003C-USD-NEGATIVE-CREDIT-MEMO-APPORTIONMENT, RND-CHK-003D, RND-CHK-003D-TIE-BROKEN-BY-LARGER-WEIGHT, RND-CHK-004-CHK-006-S2-EX11-CASEA-OWNPRICES, RND-CHK-005-USD-100-OVER-THREE-MONTHS, RND-CHK-006-S12-FRANCHISOR-OWN-LICENCE-TEN-YEARS, RND-CHK-006-S2-WARRANTY-OWN-EXTENDED-WARRANTY, RND-CHK-006-S5-EX63-OWNSSP-CUSTODY, RND-CHK-006-S5-UPFRONTFEE-OWN-OPTION-B-PATTERN, RND-CHK-006-S6-COMBINED-MOD-OWN-SUPPORT-PATTERN, RND-CHK-006-S6-EX5-CASEB-UNITS-PATTERN, RND-CHK-140-DAILY-365-DAY-TERM, RND-CHK-141-MONTHLY-EVEN-PARTIAL-MONTHS, RND-CHK-142-MID-MONTH-DAY-15-RULE, RND-CHK-143-MONTHLY-EVEN-WHOLE-AND-PARTIAL-TERMS, RND-CHK-144-MID-MONTH-LATE-START-EARLY-END, RND-CHK-145-MID-MONTH-EDGE-CASES |
| ROY | 3 | ROY-JS-07-ADVERTISING-FUND-GROSS, ROY-JS-08-ROYALTIES-LAGGING-REPORTS, ROY-S5-EX60 |
| SFC | 8 | SFC-CAP-DEFERRED-PAYMENT-ROBOT-SALE, SFC-CHK-136-S3-EX29-ANNUAL, SFC-CHK-137-S3-EX28-CASEB, SFC-FS-11-CASEA-UPFRONT-NO-FINANCING, SFC-FS-11-CASEB-UPFRONT-ADVANCE-ACCRETION, SFC-S3-EX26, SFC-S3-EX26-RETURN-RIGHT, SFC-S3-EX29 |
| SSP | 8 | SSP-CHK-030-S4-SSPRANGE-OWN-HIGHPOINT, SSP-CHK-030-S4-SSPRANGE-OWN-LOWPOINT, SSP-CHK-030-S4-SSPRANGE-OWN-MIDPOINT, SSP-CHK-030-S4-SSPRANGE-OWN-NEAREST, SSP-CHK-030-S4-SSPRANGE-OWN-OBSERVABLE-POINT, SSP-CHK-031-RANGE-VALIDATION-AT-PUBLICATION, SSP-CHK-035-TC-SETUP, SSP-FS-05-PERPETUAL-LICENCE-PCS-RESIDUAL |
| STP1 | 5 | STP1-S1-COMBINATION-OWN, STP1-S1-EX1-CASEA, STP1-S1-EX1-CASEB-C-VARB, STP1-S1-EX1-CASEB-C-VARC, STP1-S1-EX2 |
| TAX | 2 | TAX-S3-SALESTAX-OWN, TAX-WM-08-TAXES-AND-FEES-GROSS-OR-NET |
| VC | 14 | VC-BR-02-DISTRIBUTOR-RETRO-REBATE, VC-CAP-USAGE-QUARTERLY-MINIMUM-TRUEUP, VC-CHK-100-S3-EX21-EXTENDED, VC-CHK-101-S3-EX23-CASEB, VC-CHK-110, VC-CHK-113-TC-POBVC-16, VC-FS-02-COMMITTED-SPEND-TIERED-OVERAGE, VC-GE-04-CPIF-EAC-REVISIONS, VC-GE-05-AWARD-FEE-POOL-CONSTRAINT, VC-RB-01-SELF-PAY-IMPLICIT-CONCESSION-CREDIT-LOSS, VC-RB-02-COMMERCIAL-PAYOR-CONTRACTUAL-QUALITY-BONUS, VC-RB-04-COST-REPORT-SETTLEMENT, VC-S3-EX23-CASEA, VC-S3-EX24 |

#### 8.2.2 EDS: 6 keys

| Family | Count | Key ids (`make answer-keys ID=<comma-separated ids>`) |
|---|---:|---|
| DISC | 6 | DISC-CATCH-UP-BY-CAUSE-ESTIMATE-CHANGE-AND-MODIFICATION, DISC-CHK-006-S10-DISCLOSURES-ROLLFORWARD-EX21, DISC-CHK-101-S3-EX23-CASEB-PRIOR-PERIOD-POB-REVENUE, DISC-GE-06-IDIQ-TASK-ORDERS-OPTIONS-RPO, DISC-S10-DISCLOSURES-ROLLFORWARD-EX21, DISC-S10-DISCLOSURES-RPO-EX42 |

#### 8.2.3 PRP: 5 keys

| Family | Count | Key ids (`make answer-keys ID=<comma-separated ids>`) |
|---|---:|---|
| DISC | 2 | DISC-S10-DISCLOSURES-REPORTS-EX21-ROLLFORWARD-AND-TIMING, DISC-S10-DISCLOSURES-RPO-EX42-TIME-BANDS-AND-EXPEDIENT |
| DLT | 1 | DLT-CHK-020-CHK-022-GT07-JANUARY-2023-GROSS-AND-DELTA-JOURNALS |
| POS | 2 | POS-CHK-012-S9-PRESENTATION-NETTING-PER-CONTRACT, POS-CHK-117-BALANCE-AGING-EXPORT-TIES-TO-RECLASS |

#### 8.2.4 Withdrawn keys (validated and reported, never run; DG-AK-13)

POS-S9-PRESENTATION-EX38-CASEA, POS-S9-PRESENTATION-EX38-CASEB.

#### 8.2.5 Platform-runner keys and what they need

| Key | Checkpoint blocks | Requirements | Needs phases |
|---|---|---|---|
| DISC-S10-DISCLOSURES-REPORTS-EX21-ROLLFORWARD-AND-TIMING | reports; reports contract_balance_rollforward, disaggregation, revenue_from_opening_liability | REQ-RPT-006, REQ-RPT-007, REQ-RPT-011, REQ-RPT-003 | CTR, CLO, RPS |
| DISC-S10-DISCLOSURES-RPO-EX42-TIME-BANDS-AND-EXPEDIENT | contracts, reports; reports rpo | REQ-RPT-009, REQ-RPT-010, REQ-TP-003 | CTR, CLO, RPS |
| DLT-CHK-020-CHK-022-GT07-JANUARY-2023-GROSS-AND-DELTA-JOURNALS | contracts, journals, subledger | REQ-BK-001, REQ-BK-004, REQ-BK-005, REQ-JE-001, REQ-JE-007 | CTR, CLO |
| POS-CHK-012-S9-PRESENTATION-NETTING-PER-CONTRACT | contracts, subledger | REQ-BIL-003, REQ-BIL-005, REQ-BIL-007 | CTR, CLO |
| POS-CHK-117-BALANCE-AGING-EXPORT-TIES-TO-RECLASS | contracts, reports, subledger; reports balance_aging | REQ-BIL-013, REQ-RPT-003, REQ-BIL-003 | CTR, CLO, RPS |

### 8.3 CHK families: where the unit tests and the keys land

| COV-C (03 §12.3) | CHK family (POLICIES section) | `test_chk_<nnn>_<slug>` unit tests in (DG-ENG-11) | Keys whose id contains the CHK id close in |
|---|---|---|---|
| COV-C-01 | ALG-01 rounding (§2.1) | EKC | AKS |
| COV-C-02 | ALG-02 contract position and netting (§2.2) | ENC | AKS; `POS-CHK-012-…` in PRP |
| COV-C-03 | JET templates (§2.3) | END | AKS; `DLT-CHK-020-CHK-022-…` in PRP |
| COV-C-04 | ALG-03 contract asset vs unbilled receivable (§2.4) | ENC | AKS |
| COV-C-05 | ALG-04 SSP basis for modifications (§2.5) | ENB | AKS |
| COV-C-06 | ALG-05 material rights (§2.6) | ENC; option SSP rows in ENA | AKS |
| COV-C-07 | ALG-06 returns (§2.7) | ENC | AKS |
| COV-C-08 | ALG-07 cross-entity contracts (§2.8) | END | AKS |
| COV-C-09 | ALG-08 foreign currency (§2.9), including CHK-084, added after the 03 snapshot | END | AKS |
| COV-C-10 | ALG-09 late and backdated events (§2.10) | ENB | AKS |
| COV-C-11 | ALG-10 estimate versions and prior-period decomposition (§2.11) | ENB | AKS |
| COV-C-12 | ALG-11 time-elapsed conventions (§2.12) | ENC | AKS |
| COV-C-13 | SSP policy (§3.2 to §3.4) | ENA; CHK-031 in RFD (DG-AK-45 helper) | AKS |
| COV-C-14 | Policy topics PT-01 to PT-11 (§5) | the phase of the stage that implements the topic's rule (§16) | AKS; `POS-CHK-117-…` in PRP |

## 9. Golden parity kinds (generated)

| Kind (`golden-tests.json`) | Cases | Phase | Object read (DG-PAR kind table) |
|---|---:|---|---|
| `initial_allocation` | 16 | GPA | obligation version of the first contract version produced by `steps_through` |
| `pob_position` | 17 | GPA | latest obligation version after step 14 |
| `contract_position` | 50 | GPA | latest obligation versions of every obligation of the contract |
| `cumulative_catchup` | 10 | GPA | obligation version created by the modification of `steps_through` |
| `legacy_probe` | 1 | GPA | DG-PAR-06 probe replay in a fresh tenant: probe P3 (B3-BS2-04) |
| `legacy_probe` | 3 | GPB | DG-PAR-06 probe replay in a fresh tenant: probes P1, P2 and P4, whose expected objects carry `je_gross_*` and `je_delta_*` members read through `legacy_je_summary` (B3-BS2-04) |
| `journal_entry_totals` | 24 | GPB | report `legacy_je_summary`, gross and adjustment views |
| `point_in_time_equivalence` | 1 | GPB | report `migration_reconciliation`, mode (b) after step 04 |
| **Total** | **122** | GPB runs all | |

Curated cases `GT-nn` of legacy 07 §7 are cases of these kinds; a requirement citing `GT-nn` closes with the kind that holds the case.

## 10. Screens and routes by phase

### 10.1 Route table rows (SCREENS §0.4) (generated)

| RT | Screen id | Path | Read permission | Specified in | Phase | Author |
|---|---|---|---|---|---|---|
| RT-01 | SF-22 | `/sign-in` | public | SCREENS_B | WEB | BS-1 |
| RT-02 | SF-22:mfa-challenge | `/sign-in/mfa` | password step completed | SCREENS_B | WEB | BS-1 |
| RT-03 | SF-22:mfa-enrol | `/mfa/enrol` | authenticated | SCREENS_B | WEB | BS-1 |
| RT-04 | SF-22:password-change | `/password/change` | authenticated | SCREENS_B | WEB | BS-1 |
| RT-05 | SF-22:accept-invitation | `/accept-invitation` (token in the URL fragment `#token=<token>`, never a query parameter) | public | SCREENS_B | WEB | BS-1 |
| RT-06 | SF-23:select | `/select-workspace` | authenticated | SCREENS_B | WEB | BS-1 |
| RT-07 | SF-01 | `/home` (`/` redirects here, keeping the search string) | authenticated | §2 | RPS | BS-4 |
| RT-08 | SF-02 | `/contracts` | `contract.read` | §3 | CTR | BS-3 |
| RT-09 | SF-03:new | `/contracts/new` | `contract.create` | §4.10 | CTR | BS-3 |
| RT-10 | SF-03 | `/contracts/:contractId/obligations` (`/contracts/:contractId` redirects here) | `contract.read` | §4 | CTR | BS-3 |
| RT-11 | SF-03:obligation | `/contracts/:contractId/obligations/:obligationId` | `contract.read` | §5 | CTR | BS-3 |
| RT-12 | SF-03:estimates | `/contracts/:contractId/estimates` | `contract.read` | §8 | CTR | BS-3 |
| RT-13 | SF-03:estimate | `/contracts/:contractId/estimates/:estimateId` | `contract.read` | §8 | CTR | BS-3 |
| RT-14 | SF-03:schedules | `/contracts/:contractId/schedules` | `contract.read` | §4.3 | CTR | BS-3 |
| RT-15 | SF-03:billing | `/contracts/:contractId/billing` | `contract.read` | §4.4 | CTR | BS-3 |
| RT-16 | SF-03:journals | `/contracts/:contractId/journals` | `contract.read` | §4.5 | CTR | BS-3 |
| RT-17 | SF-03:modifications | `/contracts/:contractId/modifications` | `contract.read` | §4.6 | CTR | BS-3 |
| RT-18 | SF-03:history | `/contracts/:contractId/history` | `contract.read` | §4.7 | CTR | BS-3 |
| RT-19 | SF-03:edit | `/contracts/:contractId/edit` | `contract.create` | §4.10 | CTR | BS-3 |
| RT-20 | SF-07 | `/contracts/:contractId/modifications/new` | `modification.create` | §7 | CTR | BS-3 |
| RT-21 | SF-07:detail | `/contracts/:contractId/modifications/:modificationId` | `contract.read` | §7 | CTR | BS-3 |
| RT-22 | SF-18 | `/contracts/deal-preview` | `scenario.use` | SCREENS_B | FCS | BS-4 |
| RT-23 | SF-20:new | `/contracts/review/new` | `ai.use` | SCREENS_B | AIX | BS-4 |
| RT-24 | SF-20 | `/contracts/review/:proposalId` | `ai.use` | SCREENS_B | AIX | BS-4 |
| RT-25 | SF-04 | `/schedules` | `contract.read` | SCREENS_B | CLO | BS-4 |
| RT-26 | SF-05 | `/close/:entity/:book/:period` (`/close` redirects from the context) | `contract.read` | SCREENS_B | CLO | BS-4 |
| RT-27 | SF-05:multi-entity | `/close/multi-entity` | `period.close` | SCREENS_B | CLO | BS-4 |
| RT-28 | SF-06 | `/journals` | `contract.read` | SCREENS_B | CLO | BS-4 |
| RT-29 | SF-06:run | `/journals/runs/:runId` | `contract.read` | SCREENS_B | CLO | BS-4 |
| RT-30 | SF-06:entries | `/journals/entries` | `contract.read` | SCREENS_B | CLO | BS-4 |
| RT-31 | SF-08 | `/reports` | `report.run` | SCREENS_B | RPS | BS-4 |
| RT-32 | SF-08:report | `/reports/:reportCode` (`:reportCode` is a 04 T-RPT-01 code) | `report.run` | SCREENS_B | RPS | BS-4 |
| RT-33 | SF-08:run | `/reports/runs/:runId` | `report.run` | SCREENS_B | RPS | BS-4 |
| RT-34 | SF-08:disclosure-pack | `/reports/disclosure-pack` | `report.run` | SCREENS_B | RPS | BS-4 |
| RT-35 | SF-09 | `/reports/evidence` | `report.run` | SCREENS_B | RPS | BS-4 |
| RT-36 | SF-09:pack | `/reports/evidence/:packId` | `report.run` | SCREENS_B | RPS | BS-4 |
| RT-37 | SF-09:audit-log | `/reports/audit-log` | `audit.read` | SCREENS_B | RPS | BS-4 |
| RT-38 | SF-09:verification | `/reports/audit-log/verifications/:verificationId` | `audit.read` | SCREENS_B | RPS | BS-4 |
| RT-39 | SF-17 | `/reports/forecasts` | `scenario.use` | SCREENS_B | FCS | BS-4 |
| RT-40 | SF-17:event-set | `/reports/forecasts/event-sets/:eventSetId` | `scenario.use` | SCREENS_B | FCS | BS-4 |
| RT-41 | SF-17:run | `/reports/forecasts/runs/:runId` | `scenario.use` | SCREENS_B | FCS | BS-4 |
| RT-42 | SF-10 | `/data/imports` | `contract.read` | §12.1 | DIN | BS-3 |
| RT-43 | SF-10:new | `/data/imports/new` | `import.upload` | §12.2 | DIN | BS-3 |
| RT-44 | SF-10:detail | `/data/imports/:importId/:step` (`:step` ∈ `map`, `validate`, `review`, `approval`, `committed`; `/data/imports/:importId` redirects to the step of the import status, §12.2) | `contract.read` | §12.2 | DIN | BS-3 |
| RT-45 | SF-10:templates | `/data/templates` | `contract.read` | §12.4 | DIN | BS-3 |
| RT-46 | SF-11 | `/data/exceptions` | `contract.read` | §13 | DIN | BS-3 |
| RT-47 | SF-11:item | `/data/exceptions/:exceptionId` | `contract.read` | §13 | DIN | BS-3 |
| RT-48 | SF-16 | `/data/integrations` | `integration.manage` | §14 | DIN | BS-3 |
| RT-49 | SF-16:connection | `/data/integrations/:connectionId` | `integration.manage` | §14 | DIN | BS-3 |
| RT-50 | SF-16:sync-run | `/data/integrations/:connectionId/sync-runs/:syncRunId` | `integration.manage` | §14 | DIN | BS-3 |
| RT-51 | SF-19 | `/data/migrations` | `migration.run` | SCREENS_B | LMG | BS-3 |
| RT-52 | SF-19:new | `/data/migrations/new` | `migration.run` | SCREENS_B | LMG | BS-3 |
| RT-53 | SF-19:detail | `/data/migrations/:migrationId` | `migration.run` | SCREENS_B | LMG | BS-3 |
| RT-54 | SF-12 | `/approvals` | authenticated | §15 | WEB | BS-1 |
| RT-55 | SF-12:submitted | `/approvals/submitted` | authenticated | §15 | WEB | BS-1 |
| RT-56 | SF-12:all | `/approvals/all` | authenticated; lists the requests the caller may see under 04 API-R-09 (preparer, decider or holder of a step permission; D-90a) | §15 | WEB | BS-1 |
| RT-57 | SF-12:request | `/approvals/requests/:requestId` | authenticated; a request the caller may see under 04 API-R-09 (preparer, decider or holder of a step permission); otherwise the SF-12:request not-found state "Approval request not found" (§15.6; D-90a) | §15 | WEB | BS-1 |
| RT-58 | SF-12:delegations | `/approvals/delegations` | any approval permission (T-PLT-11 `is_approval`) | §15.7 | WEB | BS-1 |
| RT-59 | SF-13:revenue | `/policies/revenue` (`/policies` redirects here) | `config.read` | §11.1 | RFD | BS-3 |
| RT-60 | SF-13:control-rules | `/policies/control-rules` | `config.read` | §11.1 | RFD | BS-3 |
| RT-61 | SF-13:template-version | `/policies/templates/:templateId/versions/:versionId` | `config.read` | §11.2 | RFD | BS-3 |
| RT-62 | SF-13:rule-set-version | `/policies/rule-sets/:ruleSetId/versions/:versionId` | `config.read` | §11.1 | RFD | BS-3 |
| RT-63 | SF-13:accounting | `/policies/accounting` | `config.read` | §11.3 | RFD | BS-3 |
| RT-64 | SF-13:accounting-version | `/policies/accounting/:policyId` | `config.read` | §11.3 | RFD | BS-3 |
| RT-65 | SF-13:ssp-books | `/policies/ssp-books` | `ssp.read` | §11.4 | RFD | BS-3 |
| RT-66 | SF-13:ssp-book-version | `/policies/ssp-books/:bookId/versions/:versionId` (`/policies/ssp-books/:bookId` redirects to the current approved version, else the draft) | `ssp.read` | §11.4 | RFD | BS-3 |
| RT-67 | SF-13:ssp-calculator | `/policies/ssp-calculator` | `ssp.read` | §11.5 | RFD | BS-3 |
| RT-68 | SF-13:ssp-calculator-run | `/policies/ssp-calculator/runs/:runId` | `ssp.read` | §11.5 | RFD | BS-3 |
| RT-69 | SF-13:account-mapping | `/policies/account-mapping` | `config.read` | §11.6 | RFD | BS-3 |
| RT-70 | SF-13:account-mapping-version | `/policies/account-mapping/:mappingVersionId` | `config.read` | §11.6 | RFD | BS-3 |
| RT-71 | SF-15 | `/settings` | authenticated | SCREENS_B | WEB | BS-1 |
| RT-72 | SF-15:notifications | `/settings/notifications` | authenticated | SCREENS_B | WEB | BS-1 |
| RT-73 | SF-15:profile | `/settings/profile` | authenticated | SCREENS_B | WEB | BS-1 |
| RT-74 | SF-15:setup | `/settings/setup` | `settings.manage` | SCREENS_B | RFD | BS-3 |
| RT-75 | SF-15:entities | `/settings/entities` | `config.read` | SCREENS_B | RFD | BS-3 |
| RT-76 | SF-15:calendars | `/settings/calendars` | `config.read` | SCREENS_B | RFD | BS-3 |
| RT-77 | SF-15:currencies | `/settings/currencies` | `config.read` | SCREENS_B | RFD | BS-3 |
| RT-78 | SF-15:chart-of-accounts | `/settings/chart-of-accounts` | `config.read` | SCREENS_B | RFD | BS-3 |
| RT-79 | SF-15:customers | `/settings/customers` | `contract.read` | §9 | RFD | BS-3 |
| RT-80 | SF-15:customer | `/settings/customers/:customerId` | `contract.read` | §9 | RFD | BS-3 |
| RT-81 | SF-15:related-party-groups | `/settings/related-party-groups` | `contract.read` | §9 | RFD | BS-3 |
| RT-82 | SF-15:products | `/settings/products` | `contract.read` | §10 | RFD | BS-3 |
| RT-83 | SF-15:product | `/settings/products/:productId` | `contract.read` | §10 | RFD | BS-3 |
| RT-84 | SF-15:sandbox | `/settings/sandbox` | `tenant.snapshot` | SCREENS_B | SNP | BS-4 |
| RT-85 | SF-15:ai | `/settings/ai` | `settings.manage` | SCREENS_B | AIX | BS-4 |
| RT-86 | SF-15:ai-call-log | `/settings/ai/call-log` | `ai.use`, `settings.manage` | SCREENS_B | AIX | BS-4 |
| RT-87 | SF-14 | `/settings/users` | `user.manage` | SCREENS_B | WEB | BS-1 |
| RT-88 | SF-14:roles | `/settings/roles` | `role.manage` | SCREENS_B | WEB | BS-1 |
| RT-89 | SF-14:sod | `/settings/separation-of-duties` | `role.manage` | SCREENS_B | WEB | BS-1 |
| RT-90 | SF-14:access-reviews | `/settings/access-reviews` | `access.approve` | SCREENS_B | WEB | BS-1 |
| RT-91 | SF-14:security | `/settings/security` | `settings.manage` | SCREENS_B | WEB | BS-1 |
| RT-92 | SF-14:support-access | `/settings/support-access` | `support_grant.approve` | SCREENS_B | WEB | BS-1 |
| RT-93 | SF-16:developer | `/settings/developer` | `api_client.manage`, `webhook.manage` | SCREENS_B | WEB | BS-1 |
| RT-94 | SF-26 | `/help/legacy-transition` | authenticated | SCREENS_B | DMO | BS-4 |
| RT-95 | SF-24:results | `/search` | `contract.read` | §1.4 | CTR | BS-3 |
| RT-96 | X:trace | `/trace/:calcTraceId` | `contract.read`, `report.run` | §6.5 | CTR | BS-3 |
| RT-97 | X:design | `/design` (compiled only when `VITE_EREV_DESIGN_GALLERY=1`, DS-VER-06) | authenticated | DESIGN_SYSTEM DS-VER-06 | WEB | BS-1 |
| RT-98 | X:not-found | `*` | authenticated | §0.7 | WEB | BS-1 |
| RT-99 | SF-05:close-run | `/close/:entity/:book/:period/close-run` | `contract.read` | SCREENS_B | CLO | BS-4 |
| RT-100 | SF-05:journal-preview | `/close/:entity/:book/:period/journal-preview` | `contract.read` | SCREENS_B | CLO | BS-4 |
| RT-101 | SF-05:history | `/close/:entity/:book/:period/history` | `contract.read` | SCREENS_B | CLO | BS-4 |
| RT-102 | SF-05:reconciliations | `/close/:entity/:book/:period/reconciliations` | `contract.read` | SCREENS_B | CLO | BS-4 |
| RT-103 | SF-05:reconciliation | `/close/:entity/:book/:period/reconciliations/:reconciliationId` | `contract.read` | SCREENS_B | CLO | BS-4 |
| RT-104 | SF-06:run-lines | `/journals/runs/:runId/lines` | `contract.read` | SCREENS_B | CLO | BS-4 |
| RT-105 | SF-06:run-batches | `/journals/runs/:runId/batches` | `contract.read` | SCREENS_B | CLO | BS-4 |
| RT-106 | SF-08:runs | `/reports/runs` | `report.run` | SCREENS_B | RPS | BS-4 |
| RT-107 | SF-08:dashboard | `/reports/dashboards/:dashboardCode` | `report.run` | SCREENS_B | RPS | BS-4 |
| RT-108 | SF-14:user | `/settings/users/:membershipId` | `user.manage` | SCREENS_B | WEB | BS-1 |
| RT-109 | SF-14:access-review | `/settings/access-reviews/:reviewId` | `access.approve` | SCREENS_B | WEB | BS-1 |
| RT-110 | SF-15:workspace | `/settings/workspace` | `settings.manage` | SCREENS_B | RFD | BS-3 |
| RT-111 | SF-22:password-reset | `/password/reset` | public | SCREENS_B | WEB | BS-1 |
| RT-112 | SF-22:password-reset-confirm | `/password/reset/confirm` (token in the URL fragment `#token=<token>`) | public | SCREENS_B | WEB | BS-1 |

Route rows per phase: WEB 27; RFD 23; CTR 16; DIN 9; CLO 13; RPS 11; SNP 1; LMG 3; FCS 4; AIX 4; DMO 1.

### 10.2 Placements (generated)

| Screen id | Placement | Specified in | Phase |
|---|---|---|---|
| SF-21 | Top-bar Notifications bell popover (DS-CMP-05) | §1.2 | WEB |
| SF-23 | Top-bar context pill (DS-CMP-03); "Switch tenant" in the user menu; sandbox indicator and banner; "Read-only access" chip | §1.3 | WEB |
| SF-24 | Command palette modal (DS-CMP-04) | §1.4 | CTR |
| SF-25 | Guided tour overlay | SCREENS_B (the banner on SF-01 is specified in §2.4) | DMO |
| SF-27 | About dialog | SCREENS_B | WEB |
| SF-28 | Revenue Q&A docked panel | SCREENS_B | AIX |
| X:session-expiring | Session-expiry modal (DS-CMP-01 state) | SCREENS_B | WEB |
| X:route-error | Route error boundary inside the shell | SCREENS_B | WEB |
| X:narrow-viewport | Notice below 1024 px (not a G8 target, DS-SP-04) | SCREENS_B | WEB |
| Explain panel | Docked panel on every computed figure (SCREENS §6; DS-CMP-15) | SCREENS §6 | CTR |

### 10.3 Screen audit rows and the phase that first captures them (generated)

DG-E2E-07 and SCREENS SCR-ST-20 govern the captures; BS-D-09 governs rows whose state needs a later journey.

| Source row | Screen ids | Persona | Phase that adds the capture |
|---|---|---|---|
| SCREENS §0.12 | SF-01 | `priya` | RPS |
| SCREENS §0.12 | SF-01 | `robert` | RPS |
| SCREENS §0.12 | SF-02 | `maya` | CTR |
| SCREENS §0.12 | SF-03 | `maya` | CTR |
| SCREENS §0.12 | SF-03:obligation | `maya` | CTR |
| SCREENS §0.12 | SF-03:estimates, SF-03:estimate | `maya` | CTR |
| SCREENS §0.12 | SF-03:schedules, SF-03:billing, SF-03:journals, SF-03:modifications, SF-03:history | `maya` | CTR |
| SCREENS §0.12 | SF-03:new | `maya` | CTR |
| SCREENS §0.12 | Explain panel | `maya` | CTR |
| SCREENS §0.12 | X:trace | `maya` | CTR |
| SCREENS §0.12 | SF-07 | `maya` | CTR |
| SCREENS §0.12 | SF-15:customers, SF-15:customer, SF-15:related-party-groups | `tomas` | RFD |
| SCREENS §0.12 | SF-15:products, SF-15:product | `maya` | RFD |
| SCREENS §0.12 | SF-13:revenue, SF-13:control-rules, SF-13:rule-set-version | `maya` | RFD |
| SCREENS §0.12 | SF-13:template-version | `maya` | RFD |
| SCREENS §0.12 | SF-13:accounting, SF-13:accounting-version | `marcus` | RFD |
| SCREENS §0.12 | SF-13:ssp-books, SF-13:ssp-book-version | `maya` | RFD |
| SCREENS §0.12 | SF-13:ssp-calculator, SF-13:ssp-calculator-run | `maya` | RFD |
| SCREENS §0.12 | SF-13:account-mapping, SF-13:account-mapping-version | `marcus` | RFD |
| SCREENS §0.12 | SF-10, SF-10:new, SF-10:detail, SF-10:templates | `maya` | DIN |
| SCREENS §0.12 | SF-11, SF-11:item | `maya` | DIN |
| SCREENS §0.12 | SF-16, SF-16:connection, SF-16:sync-run | `nikhil` | DIN |
| SCREENS §0.12 | SF-12, SF-12:request, SF-12:submitted, SF-12:all, SF-12:delegations | `priya`, `maya` | WEB |
| SCREENS §0.12 | SF-24:results | `maya` | CTR |
| SCREENS §0.12 | X:not-found | `maya` | WEB |
| SCREENS_B §15 | SF-05 | `marcus` | CLO |
| SCREENS_B §15 | SF-05 | `maya` | CLO |
| SCREENS_B §15 | SF-05:close-run | `maya` | CLO |
| SCREENS_B §15 | SF-05:journal-preview | `maya` | CLO |
| SCREENS_B §15 | SF-05:history | `marcus` | CLO |
| SCREENS_B §15 | SF-05:multi-entity | `marcus` | CLO |
| SCREENS_B §15 | SF-05:reconciliations | `priya` | CLO |
| SCREENS_B §15 | SF-05:reconciliation | `priya` | CLO |
| SCREENS_B §15 | SF-06 | `maya` | CLO |
| SCREENS_B §15 | SF-06:run | `maya` | CLO |
| SCREENS_B §15 | SF-06:run-lines | `maya` | CLO |
| SCREENS_B §15 | SF-06:run-batches | `maya` | CLO |
| SCREENS_B §15 | SF-06:entries | `maya` | CLO |
| SCREENS_B §15 | SF-04 | `marcus` | CLO |
| SCREENS_B §15 | SF-04 | `marcus` | CLO |
| SCREENS_B §15 | SF-08 | `robert` | RPS |
| SCREENS_B §15 | SF-08:report | `marcus` | RPS |
| SCREENS_B §15 | SF-08:runs, SF-08:run | `marcus` | RPS |
| SCREENS_B §15 | SF-08:disclosure-pack | `marcus` | RPS |
| SCREENS_B §15 | SF-08:dashboard | `robert` | RPS |
| SCREENS_B §15 | SF-09, SF-09:pack | `hannah` | RPS |
| SCREENS_B §15 | SF-09:audit-log, SF-09:verification | `hannah` | RPS |
| SCREENS_B §15 | SF-17 | `jordan` | FCS |
| SCREENS_B §15 | SF-17:event-set, SF-17:run | `jordan` | FCS |
| SCREENS_B §15 | SF-18 | `jordan` | FCS |
| SCREENS_B §15 | SF-20:new, SF-20 | `maya` | AIX |
| SCREENS_B §15 | SF-28 | `maya` | AIX |
| SCREENS_B §15 | SF-15:ai | `tomas` | AIX |
| SCREENS_B §15 | SF-15:ai-call-log | `maya` | AIX |
| SCREENS_B §15 | SF-15 | `tomas` | WEB |
| SCREENS_B §15 | SF-15:entities, SF-15:calendars, SF-15:currencies, SF-15:chart-of-accounts, SF-15:workspace | `tomas` | RFD |
| SCREENS_B §15 | SF-15:sandbox | `marcus` | SNP |
| SCREENS_B §15 | SF-15:notifications, SF-15:profile | `maya` | WEB |
| SCREENS_B §15 | SF-14, SF-14:user | `tomas` | WEB |
| SCREENS_B §15 | SF-14:roles, SF-14:sod | `tomas` | WEB |
| SCREENS_B §15 | SF-14:access-reviews, SF-14:access-review | `grace` | WEB |
| SCREENS_B §15 | SF-14:security, SF-14:support-access | `tomas` | WEB |
| SCREENS_B §15 | SF-16:developer | `tomas` | WEB |
| SCREENS_B §15 | SF-19, SF-19:new, SF-19:detail | `maya` | LMG |
| SCREENS_B §15 | SF-19:detail | `maya` | LMG |
| SCREENS_B §15 | SF-15:setup | `tomas` | RFD |
| SCREENS_B §15 | SF-25 | `robert` | DMO |
| SCREENS_B §15 | SF-23:select | `robert` | WEB |
| SCREENS_B §15 | SF-26 | `maya` | DMO |
| SCREENS_B §15 | SF-27 | `maya` | WEB |
| SCREENS_B §15 | SF-22 | unauthenticated | WEB |
| SCREENS_B §15 | SF-22:mfa-challenge | `marcus` | WEB |
| SCREENS_B §15 | SF-22:mfa-enrol | Invitee created by the spec as in J-22.1 and J-22.2 (Revenue Reviewer) | WEB |
| SCREENS_B §15 | SF-22:accept-invitation | unauthenticated | WEB |
| SCREENS_B §15 | SF-22:password-change | `maya` | WEB |
| SCREENS_B §15 | SF-22:password-reset, SF-22:password-reset-confirm | unauthenticated | WEB |
| SCREENS_B §15 | X:session-expiring | `maya` | WEB |
| SCREENS_B §15 | X:route-error | `maya` | WEB |
| SCREENS_B §15 | X:narrow-viewport | `maya` | WEB |
| SCREENS_B §15 | X:design | `maya` | WEB |

## 11. Journeys by phase (generated)

| Journey | Title (PRD §4) | Project and order (E2E-04 to E2E-06) | Tenant | Surfaces in steps | Steps / AC / ALT | Phase |
|---|---|---|---|---|---|---|
| J-01 | Legacy user onboarding with the legacy templates | fresh-tenant | WLD-T-20 | SF-22, SF-15, SF-14, SF-13, SF-12, SF-10, SF-06, SF-16 | 16 / 7 / 3 | RPS |
| J-02 | SSP book version publish with approval | avenmoor-serial, 1 of 21 | WLD-T-01 | SF-13, SF-12 | 8 / 7 / 1 | DMO |
| J-03 | Contract ingest, five-step review and activation | avenmoor-serial, 2 of 21 | WLD-T-01 | SF-02, SF-03, SF-12 | 10 / 5 / 1 | DMO |
| J-04 | Delivery and billing events, late invoice and over-delivery | avenmoor-serial, 3 of 21 | WLD-T-01 | SF-10, SF-12, SF-03, SF-08 | 6 / 4 / 1 | DMO |
| J-05 | Prospective modification with classification, impact preview and approval | avenmoor-serial, 4 of 21 | WLD-T-01 | SF-07, SF-12, SF-08 | 6 / 3 / 2 | DMO |
| J-06 | Cumulative catch-up modification with linked estimates | avenmoor-serial, 5 of 21 | WLD-T-01 | SF-07, SF-12 | 6 / 4 / 1 | DMO |
| J-07 | Variable consideration estimate reassessment | avenmoor-serial, 6 of 21 | WLD-T-01 | SF-03, SF-12 | 4 / 4 / 0 | DMO |
| J-08 | Material-right exercise | avenmoor-serial, 7 of 21 | WLD-T-01 | SF-03, SF-12 | 3 / 3 / 1 | DMO |
| J-09 | Returns | avenmoor-serial, 8 of 21 | WLD-T-01 | SF-03, SF-12 | 3 / 3 / 2 | DMO |
| J-10 | Cost-to-cost progress and EAC update | avenmoor-serial, 9 of 21 | WLD-T-01 | SF-10, SF-12, SF-03 | 4 / 3 / 1 | DMO |
| J-11 | Usage minimum true-up and royalty accrual | avenmoor-serial, 10 of 21 | WLD-T-01 | SF-03, SF-12 | 6 / 4 / 0 | DMO |
| J-12 | Contract cost capitalization | avenmoor-serial, 11 of 21 | WLD-T-01 | SF-10, SF-12, SF-03, SF-08 | 4 / 2 / 1 | DMO |
| J-13 | Month-end close | avenmoor-serial, 15 of 21 | WLD-T-01 | SF-05, SF-12, SF-11, SF-03, SF-06, SF-10 | 16 / 9 / 2 | DMO |
| J-14 | Reopen with dual approval and re-lock | avenmoor-serial, 16 of 21 | WLD-T-01 | SF-05, SF-12, SF-10, SF-06 | 7 / 4 / 3 | DMO |
| J-15 | Reports and the disclosure pack | avenmoor-serial, 17 of 21 | WLD-T-01 | SF-08, SF-04 | 9 / 4 / 0 | DMO |
| J-16 | Explain a number and drill to the source row | avenmoor-serial, 12 of 21 | WLD-T-01 | SF-01, SF-04, SF-03, SF-06 | 6 / 3 / 0 | DMO |
| J-17 | Auditor self-service evidence | avenmoor-serial, 18 of 21 | WLD-T-01 | SF-22, SF-01, SF-09, SF-08, SF-12 | 8 / 4 / 0 | DMO |
| J-18 | Forecast scenario and deal preview | avenmoor-serial, 19 of 21 | WLD-T-01 | SF-23, SF-01, SF-17, SF-06:run, SF-18 | 6 / 4 / 1 | DMO |
| J-19 | AI contract-review proposal: accept, edit and reject | avenmoor-serial, 13 of 21 | WLD-T-01 | SF-02, SF-20, SF-15, SF-03, SF-12 | 9 / 4 / 0 | DMO |
| J-20 | Legacy `ASC606.db` import: opening balances | fresh-tenant | WLD-T-21 | SF-19, SF-12, SF-03 | 5 / 3 / 2 | LMG |
| J-21 | Legacy template replay into a sandbox, then promotion | fresh-tenant | WLD-T-23 | SF-19, SF-12, SF-06, SF-08 | 6 / 2 / 0 | LMG |
| J-22 | Administration: users, roles, separation of duties and MFA | avenmoor-serial, 21 of 21 | WLD-T-01 | SF-14, SF-12, SF-22, SF-03, SF-08 | 12 / 2 / 0 | DMO |
| J-23 | Integration setup against the mock Salesforce, Stripe and NetSuite | fresh-tenant | WLD-T-22 | SF-16, SF-12, SF-15, SF-11, SF-05 | 9 / 3 / 0 | CLO |
| J-24 | Guided tour on an industry demo tenant | industry | WLD-T-02 | SF-23, SF-01, SF-25 | 4 / 2 / 0 | DMO |
| J-25 | Sandbox copy and reset (replaces legacy backup, restore and reset) | avenmoor-serial, 20 of 21 | WLD-T-01 | SF-15:sandbox, SF-03 | 4 / 2 / 0 | DMO |
| J-26 | Contract void (replaces legacy Purge Contracts) | avenmoor-serial, 14 of 21 | WLD-T-01 | SF-03, SF-12 | 3 / 3 / 0 | DMO |

Serial journeys are built in E2E-04 order. J-01, J-20, J-21 and J-23 create their own tenants (E2E-05; DG-E2E-12). `SPEC` semantics follow DG-E2E-04. A journey item names every step, acceptance item and alternate it adds (BS-D-15).

## 12. Properties by phase

| Property (dev-guide §9.7) | Module under `backend/tests/properties/` | Engine part in | Platform part in |
|---|---|---|---|
| P1 allocation sum | `test_prop_p01_allocation_sum.py` | ENA (stage 05); END (`compute`) | none |
| P2 allocation quota | `test_prop_p02_allocation_quota.py` | EKC | none |
| P3 allocation symmetry | `test_prop_p03_allocation_symmetry.py` | EKC | none |
| P4 schedule bounds | `test_prop_p04_schedule_bounds.py` | EKC (helper); ENC (schedules) | none |
| P5 journal balance | `test_prop_p05_journal_balance.py` | END | PRP |
| P6 rollforward | `test_prop_p06_rollforward.py` | none | PRP |
| P7 RPO | `test_prop_p07_rpo.py` | EDS | PRP |
| P8 replay determinism | `test_prop_p08_determinism.py` | END | none |
| P9 idempotency | `test_prop_p09_idempotency.py` | none | PRP |
| P10 split invariance | `test_prop_p10_split_invariance.py` | ENC | none |
| P11 closed-period immutability | `test_prop_p11_closed_period.py` | none | PRP |
| P12 FX layers | `test_prop_p12_fx_layers.py` | END | none |
| P13 book equivalence | `test_prop_p13_book_equivalence.py` | END | none |
| P14 trace re-evaluation | `test_prop_p14_trace_reevaluation.py` | END | none |
| Stateful machine | `test_prop_state_machine.py` | none | PRP |
| Metamorphic | `test_prop_metamorphic.py` | END | none |

## 13. Make targets by phase (generated)

| Dev-guide id | Target | Class (dev-guide §4) | Phase that implements it |
|---|---|---|---|
| DG-MK-setup | `make setup` | loop | FND |
| DG-MK-dev-up | `make dev-up` | loop | PLF |
| DG-MK-dev-down | `make dev-down` | loop | PLF |
| DG-MK-status | `make status` | loop | PLF |
| DG-MK-backend | `make backend` | loop | FND |
| DG-MK-frontend | `make frontend` | loop | FND |
| DG-MK-worker | `make worker` | loop | PLF |
| DG-MK-migrate | `make migrate` | loop | FND |
| DG-MK-db-reset | `make db-reset` | loop | FND |
| DG-MK-revision | `make revision` | loop | FND |
| DG-MK-seed | `make seed` | loop | WEB |
| DG-MK-fixtures | `make fixtures` | loop | FND |
| DG-MK-tokens | `make tokens` | loop | FND |
| DG-MK-registry-seed | `make registry-seed` | loop | FND |
| DG-MK-openapi | `make openapi` | loop | FND |
| DG-MK-doctor | `make doctor` | loop | PLF |
| DG-MK-fmt | `make fmt` | loop | FND |
| DG-MK-lint | `make lint` | loop | FND |
| DG-MK-design-check | `make design-check` | loop | FND |
| DG-MK-vocab-check | `make vocab-check` | loop | FND |
| DG-MK-licence-check | `make licence-check` | loop | FND |
| DG-MK-secrets-check | `make secrets-check` | loop | FND |
| DG-MK-typecheck | `make typecheck` | loop | FND |
| DG-MK-test | `make test` | loop | FND |
| DG-MK-build | `make build` | loop | FND |
| DG-MK-ci | `make ci` | loop | FND |
| DG-MK-test-pg | `make test-pg` | loop | FND |
| DG-MK-parity | `make parity` | loop | GPA |
| DG-MK-answer-keys | `make answer-keys` | loop | EKC |
| DG-MK-properties | `make properties` | loop | EKC |
| DG-MK-e2e | `make e2e` | loop | WEB |
| DG-MK-perf | `make perf` | loop | PRF |
| DG-MK-perf-seed | `make perf-seed` | loop | PRF |
| DG-MK-release-manifest | `make release-manifest` | loop | SOP |
| DG-MK-controls-report | `make controls-report` | loop | FND |
| DG-MK-audit-deps | `make audit-deps` | supervisor (§4.5; script only, never run by the loop) | DEP |
| DG-MK-zap-baseline | `make zap-baseline` | supervisor (§4.5; script only, never run by the loop) | DEP |
| DG-MK-docker-build | `make docker-build` | supervisor (§4.5; script only, never run by the loop) | DEP |
| DG-MK-compose-verify | `make compose-verify` | supervisor (§4.5; script only, never run by the loop) | DEP |
| DG-MK-tf-validate | `make tf-validate` | supervisor (§4.5; script only, never run by the loop) | DEP |
| DG-MK-backup | `make backup` | supervisor (§4.5; script only, never run by the loop) | DEP |

A target is complete from the item that implements it, with the exact semantics of dev-guide §4. No item calls a target implemented by a later phase. Supervisor scripts are written in DEP and never run by the loop (DG-FORBID-12).

## 14. Decisions with build effect by phase

| Phase | Decisions | Build effect |
|---|---|---|
| FND | D-01, D-02, D-40, D-40a, D-41, D-42, D-45, D-48, D-48a, D-62, D-73, D-75, D-76 | MIT `LICENSE` and no licence keys; vocabulary lint; Python, PostgreSQL-only and frontend toolchains; SQLite only for legacy files and fixtures; role guard; problems, money strings and OpenAPI 3.1; loop and supervisor targets; design-check; verbatim enum, permission and problem catalogues; copyright line and `EREV_DEMO_PASSWORD` placeholder; network only in `make setup` (DG-OQ-13) |
| EKC | D-10, D-11, D-11a, D-17, D-71, D-74, D-76, D-77 | Pure engine package; Decimal context, largest remainder and `cumulative_posted`; runner tolerances; answer keys first; split specifications; answer-key schema of dev-guide §9.5; frozen corpus |
| PLF | D-19, D-42, D-43, D-44, D-45, D-72, D-75 | Server `recorded_at`; forced RLS and `SET LOCAL`; append-only grants, triggers and HMAC chain; identity model; Idempotency-Key, ETag, time-travel reads, 202 jobs; in-process mocks; eight queues, key model, tenant provisioning, upload limits, reopen-approve grant |
| WEB | D-02, D-41, D-60, D-61, D-62, D-75, D-76 | Navigation vocabulary; React stack; layout and craft; brand and accent; anti-slop rules; negative style default and named persona users; DESIGN_SYSTEM OQ-06 and OQ-07 rulings |
| ENA | D-10, D-11, D-11a, D-14, D-14a, D-21a, D-22, D-23, D-32, D-76 | Stages as pure functions; allocation rounding; 33 account roles in the bundle; option SSP; expected returns reduce the price; contracting and performing entity per obligation; range clamp under the preset; ENGINE_SPEC OQ-A rulings |
| RFD | D-13a, D-14, D-14a, D-15, D-18, D-24, D-32, D-73, D-75, D-76 | Registry literals; role mapping with `clearing_purpose`; one account for both balance roles allowed; approved SSP version effective on a date; three books; legacy-parity preset; verbatim literals; tenant settings; `compounding` member |
| ENB | D-18, D-19, D-20, D-21, D-21a, D-31, D-76 | Modification SSP basis; late events; immutable estimate versions; exercise treatment; opening balances; ENGINE_SPEC OQ-A rulings |
| ENC | D-11a, D-12, D-13, D-15, D-22, D-76 | Cumulative rounding of schedules; net position sign; billing posting; contract asset vs unbilled receivable; returns; financing interest in the position, uninstalled materials, impairment with renewals, MONTHLY compounding |
| END | D-16, D-23, D-24, D-25, D-25a, D-25b, D-34, D-76 | Balanced line pairs and rounding residue; intercompany pairs; book loop and memoisation; FX layers and remeasurement; refundable advances; monetary liabilities; delta posting; E-86 and JET literals |
| AKS | D-11a, D-71, D-76, D-77 | Re-baselined keys; keys gate capabilities; CHK re-baselines; corpus frozen |
| CTR | D-01, D-10, D-19, D-20, D-43, D-45, D-76 | Void through approval replaces purge; pinned reference versions; dual dates; estimate versions; immutable versions; `/explain`; workbench tabs, KPI strip and SCREENS R-01 to R-40 |
| DIN | D-13, D-30, D-30a, D-72 | ERP billing ingested without posting; four legacy templates, CSV and the import flow; explicit findings; mock adapters |
| GPA | D-11a, D-17, D-17a, D-32 | `EXACT-CUM`; tolerances; DEV-002 cent class; preset |
| EDS | D-12, D-76 | Labelled balances; POL-201 RPO bands |
| CLO | D-13, D-16, D-19, D-72, D-75 | Auto-reversing netting reclass; batch balance constraint; first open period; GL mocks; reopen approvers |
| RPS | D-33, D-76 | Legacy exports with legacy columns and sign; RPO bands and report cell keys |
| SNP | D-01, D-42 | Backup, restore and reset become snapshot, restore into sandbox and sandbox reset; pooled tenants |
| LMG | D-31, D-32, D-40a | Database import modes and reconciliation; preset on migrated tenants; read-only SQLite access |
| GPB | D-17a, D-34 | Class sign-offs; delta journal parity (GT-07) |
| PRP | D-12, D-25b, D-71 | P6 sign; P12 monetary liabilities; full corpus |
| FCS | D-01, D-04 | Scenario tenants and the deal preview in 1.0 |
| AIX | D-46, D-76 | Provider interface, fake default, proposals only; AI turn-off route |
| SOP | D-43, D-48a, D-75 | Chain verification alerting; release manifest; key rotation by id |
| DMO | D-02, D-04, D-75 | Vocabulary on seeded content; six industry clusters; named persona users and password from the environment |
| PRF | D-75, D-76 | `perf-volume` tenant and sandbox close; perf-worker protocol |
| DEP | D-47, D-48a | Dockerfiles, compose and Terraform artifacts only; supervisor targets |
| REL | D-70, D-77 | Evidence for G1 to G11; spec questions listed for the supervisor |

## 15. Hint closure

### 15.1 Families (03 §1.4)

| Hint | Closes at | Evidence |
|---|---|---|
| `UNIT` | The item that completes the requirement (§6) | Named tests with their assertions |
| `PG` | The item that completes the requirement | `make test-pg` counts |
| `CTL-nnn` | The phase of §7; all 49 at GATE-SOP and at REL | `make controls-report` |
| `AK:<id>`, `AK-FAM:<slug>`, CHK containment | §8.2: AKS for engine-runner keys other than DISC, EDS for DISC engine-runner keys, PRP for platform-runner keys; unfiltered from GATE-PRP | `make answer-keys ID=…`, then unfiltered |
| `GT:<kind>`, `GT-nn` | §9: GPA or GPB | `make parity K=…`, then unfiltered |
| `TC-…` | The item that completes the requirement, through `test_tc_…` (BS-D-21) | pytest |
| `PROP:Pn` | §12 | `make properties` |
| `E2E` | The journey whose REQ list cites the requirement (§11); otherwise §15.2 | `make e2e SPEC=…` |
| `PERF` | PRF | `make perf` |
| `DEMO` | DMO seed tests; supervisor browser QA at REL (G10) | seed report; **Supervisor verification needed** |
| `ART` | The item that creates the artifact; DEP and REL for deploy artifacts | Files and command output |

A requirement is ticked for G1 when its completing item is ticked and every hint it carries has closed per this table (BS-D-19, BS-D-24).

### 15.2 `E2E` hints without a citing journey (generated)

| REQ | Closes in | Spec | `test.step` title starts with the REQ id and asserts |
|---|---|---|---|
| REQ-PLT-021 | WEB | `screens.spec.ts` | SF-21 popover: unread count, mark read, open link; SF-15:notifications saves a preference |
| REQ-PLT-038 | CLO | `fresh-tenant.spec.ts` `beforeAll` of J-23 | tenant created through `erev tenant create` (DG-E2E-12); duplicate code fails |
| REQ-CON-017 | CTR | `screens.spec.ts` | SF-02 quick lists, filters and a saved view round trip |
| REQ-SEC-008 | WEB | every project (network guard DG-E2E-08) | no request to a non-loopback host is recorded |
| REQ-UX-001 | RPS | `screens.spec.ts` | the rail shows the ten D-02 destinations once Home exists |
| REQ-UX-002 | RFD | `screens.spec.ts` | top bar, context pill defaults (BR-UX-01), command palette trigger |
| REQ-UX-003 | CTR | `screens.spec.ts` | record header, KPI strip, tabs and obligation pane on SF-03 |
| REQ-UX-007 | WEB | `design.spec.ts` | DS-VER-06 to DS-VER-08 themes, reduced motion, forced colours, target size |
| REQ-UX-008 | CTR | `screens.spec.ts` | compact density captures of SF-02 and SF-03 (DS-VER-05) |
| REQ-UX-013 | WEB | `screens.spec.ts` | SF-12 inbox: approve with comment, reject, bulk selection |
| REQ-UX-017 | RPS | `screens.spec.ts` | SF-01 favourite added and opened (SCR-IA-08) |
| REQ-UX-019 | DMO | `screens.spec.ts` | SF-26 lists 14 buttons and 4 templates with working links |
| REQ-UX-020 | REL | `make e2e` full | every journey and every screen audit row passes |
| REQ-UX-021 | DIN | `screens.spec.ts` | SF-10:detail job progress (DS-CMP-24) through validate and diff |
| REQ-UX-022 | WEB | `design.spec.ts` | DS-VER-09 pseudo-localisation and `dir=rtl` smoke |

## 16. Engine stage map (generated)

| Stage | Title | Section | Package under `backend/erev_engine/stages/` | Rule ids S<nn>-R | Worked examples | Phase |
|---|---|---|---|---:|---|---|
| 01 | Ingest and canonicalisation (engine part; platform part in DIN, BS-D-16) | ENGINE_SPEC §1 | `s01_canonicalize` | 20 | EX-01-A | ENA |
| 02 | Contract identification | ENGINE_SPEC §2 | `s02_contract_identification` | 14 | EX-02-A, EX-02-B | ENA |
| 03 | POB builder | ENGINE_SPEC §3 | `s03_pob_builder` | 18 | EX-03-A, EX-03-B, EX-03-C, EX-03-D, EX-03-E | ENA |
| 04 | Transaction price | ENGINE_SPEC §4 | `s04_transaction_price` | 21 | EX-04-A, EX-04-B, EX-04-C, EX-04-D, EX-04-E, EX-04-F, EX-04-G | ENA |
| 05 | SSP resolution and allocation | ENGINE_SPEC §5 | `s05_allocation` | 17 | EX-05-A, EX-05-B, EX-05-C, EX-05-D | ENA |
| 06 | Modifications | ENGINE_SPEC §6 | `s06_modifications` | 32 | EX-06-A, EX-06-B, EX-06-C, EX-06-D, EX-06-E, EX-06-F, EX-06-G, EX-06-H, EX-06-I, EX-06-J | ENB |
| 07 | Onboarding and migration | ENGINE_SPEC §7 | `s07_onboarding` | 13 | EX-07-A, EX-07-B, EX-07-C | ENB |
| 08 | Estimate reassessment and late events | ENGINE_SPEC §8 | `s08_estimates_late_events` | 16 | EX-08-A, EX-08-B, EX-08-C, EX-08-D, EX-08-E | ENB |
| 09 | Recognition and schedules | ENGINE_SPEC_B §9 | `s09_recognition` | 50 | EX-09-A, EX-09-B, EX-09-C, EX-09-D, EX-09-E, EX-09-F, EX-09-G | ENC |
| 10 | Billing and balances | ENGINE_SPEC_B §10 | `s10_billing_balances` | 25 | EX-10-A, EX-10-B, EX-10-C | ENC |
| 11 | Contract costs and loss contracts | ENGINE_SPEC_B §11 | `s11_costs_loss` | 16 | EX-11-A, EX-11-B | ENC |
| 12 | Foreign currency and multi-entity | ENGINE_SPEC_B §12 | `s12_fx_entities` | 21 | EX-12-A, EX-12-B | END |
| 13 | Books | ENGINE_SPEC_B §13 | `s13_books` | 11 | EX-13-A, EX-13-B | END |
| 14 | Journal derivation (engine part §14.2) | ENGINE_SPEC_B §14 | `s14_posting` | 24 | EX-14-A | END |
| 15 | Close projections and disclosures (engine part) | ENGINE_SPEC_B §15 | `s15_disclosures` | 23 | EX-15-A, EX-15-B, EX-15-C, EX-15-D | EDS |

## 17. Mechanical checks (generated)

| Check | Result | Detail |
|---|---|---|
| REQ 1.0 assigned once | PASS | 409 assigned of 409 release-1.0 rows (03 §8 total 409); 25 later rows unassigned |
| CTL assigned once | PASS | 49 of 49 designated controls |
| RT rows assigned | PASS | 112 RT rows; unassigned [] |
| Placements assigned | PASS | 9 placements plus the Explain panel; unassigned [] |
| Journeys assigned | PASS | 26 journeys; serial 21, fresh-tenant 4, industry 1 |
| Golden kinds assigned | PASS | 7 kinds, 122 cases |
| Active answer keys assigned | PASS | 234 files: 232 active (221 AKS, 6 EDS, 5 PRP), 2 withdrawn |
| Make targets assigned | PASS | 41 DG-MK targets; 6 supervisor targets |
| 04 tables assigned | PASS | 152 tables; missing []; unknown [] |
| Report codes assigned | PASS | 56 seeded codes of T-RPT-01 |
| Every phase has an author | PASS | 27 phases; authors ['BS-1', 'BS-2', 'BS-3', 'BS-4'] |
