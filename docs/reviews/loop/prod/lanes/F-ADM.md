# Lane F-ADM — administration and master-data screens; fresh-tenant onboarding

Required 1.0 backlog (00-GOAL G1 `docs/00-GOAL.md:83`, G8 `:90`, G10 `:92`): every item below is inside the authorised objective, so no product decision precedes the worktree; the "yes" set of `spec-completeness.md` §1 is extended by the items that investigation marked "no — product decision" (Codex coverage review 2026-09-19 §2, applied by the docs agent). Sequencing: after wave 1 as capacity frees — authorised 1.0 scope sequenced by capacity; no confirmation hold precedes this lane. Record: `docs/reviews/loop/sprint/F-ADM.md`. Items: WEB-13 (invitation acceptance + MFA enrolment; J-22.1/22.2 fresh-tenant), WEB-14 (password change/reset), WEB-19 (users), WEB-20 (roles/SoD; CTL-034 surface), WEB-21 (access reviews; REQ-CTL-006), WEB-22 (security/support access), RFD-18 (entities/calendars/currencies), RFD-20 (customers/related parties), RFD-21 (products), RFD-23 (obligation templates + accounting policy screens; CTL-031), RFD-25 (account mapping; CTL-020). Spec anchors: `docs/BUILD_SPEC.md:3332-3575` (WEB), `:4522-4723` (RFD); SCREENS SF-12/13/15/22 rows; PHASES §10.3 audit rows.

**Added 2026-09-19 (former 'product decision' items, now required 1.0 backlog):** RFD-17 (industry tenant reference data and Draft industry policy templates; `docs/BUILD_SPEC.md:4522`; after RFD-16; feeds the G10 industry tenants of F-DMO), WEB-23 (API clients and webhooks screen; `:3554`; after WEB-22).

## Scope
Frontend-only over existing APIs (PLF users/roles/SoD/access reviews/support grants; RFD APIs); the `fresh-tenant` e2e project gains its first real tests (invitation → MFA enrol → first sign-in); admin/auditor persona QA (Q1) re-run on the new screens.

## Fail-first tests and evidence
Vitest per route (DS conformance, i18n catalogue, a11y); `frontend/e2e/projects/fresh-tenant.spec.ts` with hard assertions; screens e2e rows added for each new SF row; axe no serious/critical.
Each item's BUILD_SPEC acceptance block (tests, answer keys, journeys, screens) is the closing evidence; ticks in PROGRESS/ticks.md with commit ids.

## Notes and shared files
Shares `frontend/src/routes/**`, `messages/en.json`, `schema.d.ts` with F-WEB-R and F-CTR; no backend changes expected (return any API gap).

## Dependencies
None hard; Q1 evidence after.

## Do not change
Engine behaviour (return engine questions to the owning ENG lane); answer-key expected values; approval semantics without the owning control's test.

## Questions to return
Any control (CTL) whose tagged test cannot be written without a policy statement; any screen whose SCREENS row is ambiguous.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies (own worktree and `.env`; never the dev DB `erev` or ports 8190/5270; no git write beyond commits on the lane branch; fail-first tests; scratch under `.run/<lane>/`, never `/tmp`; never print `.env` or secret values; `make lint` not bare ruff; one gate slot for DB gates; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: supervisor-only targets (Docker, network, Terraform provider download, live databases) are RUN by the supervisor on request and recorded in `docs/reviews/loop/supervisor-verification.md`; `skipped-no-daemon` / `skipped-not-installed` are never passes; live cloud provisioning, image publishing, remote pushes and paid actions need Ray's explicit authorisation at that step (00-GOAL.md:75,102; PRODUCTION-CONTINUATION §Work boundaries). Every lane adding a Makefile target extends `BUILT_TARGETS`/`BUILT_PHASES` in `backend/tests/unit/test_makefile_targets.py` in the same commit (BS1-D-11). Gates before reporting: `make ci`, `make test-pg` where DB code changed, plus the lane-specific evidence below; measured, none projected.
