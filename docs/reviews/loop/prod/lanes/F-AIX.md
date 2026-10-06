# Lane F-AIX — AI assistance under human control (phase 22 AIX)

Required 1.0 backlog (00-GOAL §2.12 `docs/00-GOAL.md:67-73` — contract-review extraction proposals, explaining a number, anomaly flags, a revenue Q&A that cites records; "Tests use a fake provider. The AI never posts or changes accounting data without an audited human action"; G1 `:83`, G8 `:90`): the twelve AIX items the spec-completeness investigation marked "no — product decision" are inside the authorised objective (Codex coverage review 2026-09-19 §2). Sequencing: after wave 1 as capacity frees and after F-FCS (AIX-1 prerequisite GATE-FCS); worker registrations after P2. Record: `docs/reviews/loop/sprint/F-AIX.md`. Items: AIX-1 (AI tables and the provider interface with the fake provider; `docs/BUILD_SPEC.md:10441`; GATE-FCS), AIX-2 (Anthropic SDK adapter against a mocked client; `:10467`), AIX-3 (AI gateway, `AI_TASK` job, configuration evidence, redaction and token budget; `:10494`), AIX-4 (tenant enablement, turn-off and the kill switch; `:10520`; GATE-RFD), AIX-5 (contract review extraction proposals; `:10545`), AIX-6 (proposal acceptance into draft contracts and rejection; `:10571`; GATE-CTR; carries the CTL-045 tagged control test and removes AI_PROPOSAL_ACCEPTANCE from `PENDING_SUBJECTS`, `approvals/subjects.py:2622-2630`), AIX-7 (explain narratives with number validation; `:10597`; GATE-CTR), AIX-8 (anomaly detectors and flag summaries; `:10620`), AIX-9 (revenue Q&A with citations; `:10646`), AIX-10 (AI settings and AI call log screens; `:10670`), AIX-11 (contract review screens; `:10694`; journey J-19 lands in F-DMO DMO-22), AIX-12 (revenue Q&A panel and embedded AI blocks; `:10718`); plus SCH-11 `ai_proposal_expiry` (05 SCH table). Spec anchors: phase 22 `docs/BUILD_SPEC.md:10426-10754`; GATE-AIX `:10743`; CTL-045 (03-REQUIREMENTS §4.1).

## Scope
Serial AIX-1 → 12; every AI output is a proposal or narrative bound to a human, audited action (maker-checker through the approvals subject); AI off by default per tenant, the kill switch global; the doctor asserts the default (SAR-40, P4).

## Boundary (00-GOAL §2.12, §4 `docs/00-GOAL.md:98`; §2 item 14 `:75`)
Fake provider in every test; the Anthropic SDK adapter is exercised against a mocked client only; no live model call in any gate; the Anthropic key provisioning decision and kill-switch default (UI-8) are needed only for the optional REL-2 live smoke (AIX-2, "if AI enabled") and never for the build; no key or secret in the tree; Terraform artifacts are never applied. Redaction and token budget (AIX-3) are tested with the fake provider.

## Fail-first tests and evidence
Each item's BUILD_SPEC acceptance block on a clean tree; CTL-045 `@pytest.mark.control("CTL-045")` failure-path test (`make controls-report` lists it PASS); `PENDING_SUBJECTS` loses AI_PROPOSAL_ACCEPTANCE; SCH-11 registration with tests; licence-check for any new dependency (REQ-SEC-010; Anthropic SDK licence recorded); ticks in PROGRESS/ticks.md with commit ids; lane record.

## Notes and shared files
Shares `backend/erev_api/worker.py` with P2/P5 (merge after P2); `approvals/subjects.py` with F-CTR/F-CLO/F-LMG (subject removals); `domain/contracts/*` draft creation with F-CTR (AIX-6); frontend routes and `messages/en.json` with F-WEB-R; migrations serialised.

## Dependencies
F-FCS (GATE-FCS) before AIX-1; GATE-RFD (ticked phase, checkpoint run by P9) for AIX-4; F-CTR CTR-24 draft form for AIX-6 acceptance into drafts; P2 before SCH-11; F-DMO DMO-22 (J-19) depends on AIX-11.

## Do not change
Engine behaviour; answer-key expected values; the fail-closed "AI never posts" rule (any AI write path routes through an approval subject with a tagged control test).

## Questions to return
The AI-provider dependency shape (runtime dependency vs `ai` extra, mirroring the P2 `gcp` question); token-budget and redaction defaults (CFG rows for P5); whether AIX-2's live smoke is in REL-2 at all before UI-8 is answered.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies (own worktree and `.env`; never the dev DB `erev` or ports 8190/5270; no git write beyond commits on the lane branch; fail-first tests; scratch under `.run/<lane>/`, never `/tmp`; never print `.env` or secret values; `make lint` not bare ruff; one gate slot for DB gates; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: supervisor-only targets (Docker, network, Terraform provider download, live databases) are RUN by the supervisor on request and recorded in `docs/reviews/loop/supervisor-verification.md`; `skipped-no-daemon` / `skipped-not-installed` are never passes; live cloud provisioning, image publishing, remote pushes and paid actions need Ray's explicit authorisation at that step (00-GOAL.md:75,102; PRODUCTION-CONTINUATION §Work boundaries). Every lane adding a Makefile target extends `BUILT_TARGETS`/`BUILT_PHASES` in `backend/tests/unit/test_makefile_targets.py` in the same commit (BS1-D-11). Gates before reporting: `make ci`, `make test-pg` where DB code changed, plus the lane-specific evidence below; measured, none projected.
