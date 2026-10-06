# Lane F-DMO — demo world, industry tenants, guided tour and the serial journeys (phase 24 DMO; G8/G10 evidence)

Required 1.0 backlog (00-GOAL §2 item 14 `docs/00-GOAL.md:75` — "Demo tenants seeded per industry cluster, a guided tour"; G8 `:90` — every screen built, all Playwright journeys pass; G10 `:92` — demo tenants for at least six industry clusters, the guided tour completes; G12 `:94` browser QA): the 34 DMO items the spec-completeness investigation marked "no — product decision" are the product's G8/G10 evidence and inside the authorised objective (Codex coverage review 2026-09-19 §2). Evidence work is not dropped because it is not a deployment control. Sequencing: the last F-lane — after wave 1 and after every feature lane a journey evidences; before P9. Record: `docs/reviews/loop/sprint/F-DMO.md`. Also owns QA-6 (the `fresh-tenant`, `industry` and `design` e2e projects hold 3-5-line stubs today, `frontend/e2e/projects/*.spec.ts`; the fresh-tenant invitation/MFA path itself is F-ADM WEB-13). Spec anchors: phase 24 `docs/BUILD_SPEC.md:11026-11873`; GATE-DMO `:11848` (unfiltered e2e, no project skipped; `make seed` report and duration).

## Items (serial in this order; prerequisite column from the readiness matrix)
| Item | Intent | Anchor | Prerequisites |
|---|---|---|---|
| DMO-1 | Demo generator, deterministic datasets and persona credentials | `docs/BUILD_SPEC.md:11041` | GATE-SOP, GATE-WEB, GATE-RFD, GATE-CTR, GATE-DIN, CLO-22, FCS-7 |
| DMO-2 | Avenmoor structure, settings, chart of accounts and SSP books | `docs/BUILD_SPEC.md:11068` | DMO-1 |
| DMO-3 | Avenmoor customers, key contracts and seed-state figures | `docs/BUILD_SPEC.md:11094` | DMO-2 |
| DMO-4 | Avenmoor close history and seeded open-period items | `docs/BUILD_SPEC.md:11124` | DMO-3 |
| DMO-5 | Fernhill Software and Bracken Robotics demo tenants | `docs/BUILD_SPEC.md:11150` | DMO-4 |
| DMO-6 | Granitefield Engineering and Juniper Street Coffee demo tenants | `docs/BUILD_SPEC.md:11174` | DMO-5 |
| DMO-7 | Riverbend Health and Wayfarer Marketplace demo tenants | `docs/BUILD_SPEC.md:11197` | DMO-6 |
| DMO-8 | Legacy parity pack through migration mode (b) | `docs/BUILD_SPEC.md:11220` | DMO-7, GATE-LMG |
| DMO-9 | Seed orchestration, duration and the seed report | `docs/BUILD_SPEC.md:11244` | DMO-8 |
| DMO-10 | Guided tour and the demo tour banner | `docs/BUILD_SPEC.md:11269` | DMO-9 |
| DMO-11 | Legacy transition map screen and user guide map | `docs/BUILD_SPEC.md:11293` | DMO-10 |
| DMO-12 | Journey J-02 SSP book version publish with approval | `docs/BUILD_SPEC.md:11317` | DMO-11 |
| DMO-13 | Journey J-03 contract ingest, five-step review and activation | `docs/BUILD_SPEC.md:11341` | DMO-12 |
| DMO-14 | Journey J-04 delivery and billing events, late invoice and over-delivery | `docs/BUILD_SPEC.md:11365` | DMO-13 |
| DMO-15 | Journey J-05 prospective modification with classification, impact preview and approval | `docs/BUILD_SPEC.md:11389` | DMO-14 |
| DMO-16 | Journey J-06 cumulative catch-up modification with linked estimates | `docs/BUILD_SPEC.md:11413` | DMO-15 |
| DMO-17 | Journeys J-07 variable consideration reassessment and J-08 material-right exercise | `docs/BUILD_SPEC.md:11437` | DMO-16 |
| DMO-18 | Journeys J-09 returns and J-10 cost-to-cost progress and EAC update | `docs/BUILD_SPEC.md:11463` | DMO-17 |
| DMO-19 | Journey J-11 usage minimum true-up and royalty accrual | `docs/BUILD_SPEC.md:11490` | DMO-18 |
| DMO-20 | Journey J-12 contract cost capitalization | `docs/BUILD_SPEC.md:11513` | DMO-19 |
| DMO-21 | Journey J-16 explain a number and drill to the source row | `docs/BUILD_SPEC.md:11537` | DMO-20 |
| DMO-22 | Journey J-19 AI contract-review proposal: accept, edit and reject | `docs/BUILD_SPEC.md:11560` | DMO-21 |
| DMO-23 | Journey J-26 contract void | `docs/BUILD_SPEC.md:11583` | DMO-22 |
| DMO-24 | Journey J-13 month-end close, part 1 (blockers to journal run approval) | `docs/BUILD_SPEC.md:11606` | DMO-23 |
| DMO-25 | Journey J-13 month-end close, part 2 (export, reconciliations, lock and multi-entity close) | `docs/BUILD_SPEC.md:11629` | DMO-24 |
| DMO-26 | Journey J-14 reopen with dual approval and re-lock | `docs/BUILD_SPEC.md:11653` | DMO-25 |
| DMO-27 | Journey J-15 reports and the disclosure pack | `docs/BUILD_SPEC.md:11677` | DMO-26 |
| DMO-28 | Journey J-17 auditor self-service evidence | `docs/BUILD_SPEC.md:11700` | DMO-27 |
| DMO-29 | Journey J-18 forecast scenario and deal preview | `docs/BUILD_SPEC.md:11723` | DMO-28 |
| DMO-30 | Journey J-25 sandbox copy and reset | `docs/BUILD_SPEC.md:11747` | DMO-29 |
| DMO-31 | Journey J-22 administration, part 1 (invitation, MFA and SoD block) | `docs/BUILD_SPEC.md:11770` | DMO-30 |
| DMO-32 | Journey J-22 administration, part 2 (SoD exception, lockout, access review and suspension) | `docs/BUILD_SPEC.md:11792` | DMO-31 |
| DMO-33 | Journey J-24 guided tour on an industry demo tenant | `docs/BUILD_SPEC.md:11815` | DMO-32 |
| DMO-34 | Every screen audit row in its stated state and the unfiltered e2e run | `docs/BUILD_SPEC.md:11838` | DMO-33 |

## Scope
DMO-1..11: generator, Avenmoor and six industry tenants (Fernhill, Bracken, Granitefield, Juniper Street, Riverbend, Wayfarer), legacy parity pack, seed orchestration and report, guided tour, transition map. DMO-12..34: journeys J-02..J-26 as Playwright evidence of features built by their owning lanes (the matrix rows name them: RFD-13, CTR-9/24, CTR-17/27, CTR-12/25, ENC-5..8, CTR-14, CTR-26, AIX, CTR-11, CLO-6/10/12/14/16/17/21, CLO-7, RPS-15/16/21, FCS, SNP, WEB-13/19/20/21/22) and DMO-34's unfiltered run. A journey lands only after its feature lane merges; the lane may start DMO-1..4 (Avenmoor seed; RPS-7a SUP-RC-SMOKE already runs on it) as soon as CLO-22 (F-CLO) and FCS-7 (F-FCS) exist or are stubbed by their owners with a recorded interim.

## Boundary (00-GOAL §4 `docs/00-GOAL.md:98`; §2 item 14 `:75`)
Seeded demo data only; no live third-party call from any demo tenant (the J-23 integration journey, CLO-27, runs against the F-DIN mocks); demo tenants never post or export over a production tenant; persona credentials are demo-only and never reused; Terraform artifacts are never applied. Screen captures and journeys are G12 browser-QA inputs (Q1), not a substitute for the personas' manual QA.

## Fail-first tests and evidence
Each item's BUILD_SPEC acceptance block on a clean tree; `make seed` twice → identical dataset hashes (determinism); `make e2e` unfiltered with no project skipped and the seed report with duration (GATE-DMO); light and dark screenshots of every WEB capture (G8); ticks in PROGRESS/ticks.md with commit ids; lane record.

## Notes and shared files
Shares `domain/demo/*` (`personas.py`) with Q1; `frontend/e2e/projects/*` and `screens.spec.ts` / `avenmoor-serial.spec.ts` with F-WEB-R (CTR-20 K-04 gate clause) and every frontend lane; seed scripts with F-CLO (CLO-22) and F-ADM (RFD-17 industry reference data); the e2e ports lock 8199 and the shared DB slot with P7.

## Dependencies
Every feature lane a journey evidences (table above); GATE-LMG for DMO-8; RFD-17 (F-ADM) for the industry tenants; CLO-22 (F-CLO) and FCS-7 (F-FCS) for DMO-1; P9 runs GATE-DMO after this lane.

## Do not change
Engine behaviour; answer-key expected values; any feature under test (defects return to the owning lane with the failing journey step); the K-04 gate clause (D-88 L7-6-Q-1).

## Questions to return
Interim rule when a journey's feature lane has not merged (skip with a recorded reason vs block); the industry cluster list if the six named tenants differ from the demo research; whether SUP-RC-SMOKE (RPS-7a) stays beside the PRD journeys or is retired at DMO-34.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies (own worktree and `.env`; never the dev DB `erev` or ports 8190/5270; no git write beyond commits on the lane branch; fail-first tests; scratch under `.run/<lane>/`, never `/tmp`; never print `.env` or secret values; `make lint` not bare ruff; one gate slot for DB gates; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: supervisor-only targets (Docker, network, Terraform provider download, live databases) are RUN by the supervisor on request and recorded in `docs/reviews/loop/supervisor-verification.md`; `skipped-no-daemon` / `skipped-not-installed` are never passes; live cloud provisioning, image publishing, remote pushes and paid actions need Ray's explicit authorisation at that step (00-GOAL.md:75,102; PRODUCTION-CONTINUATION §Work boundaries). Every lane adding a Makefile target extends `BUILT_TARGETS`/`BUILT_PHASES` in `backend/tests/unit/test_makefile_targets.py` in the same commit (BS1-D-11). Gates before reporting: `make ci`, `make test-pg` where DB code changed, plus the lane-specific evidence below; measured, none projected.
