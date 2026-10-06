# Lane F-DIN — inbound integrations: mock adapters, connections, sync, integrations screens (phase 12 DIN remainder)

Required 1.0 backlog (00-GOAL §2.10 `docs/00-GOAL.md:65` — "mock inbound adapters (Salesforce orders, Stripe subscriptions and invoices)"; G1 `:83`, G8 `:90`): the four unticked DIN items the spec-completeness investigation marked "no — product decision" are inside the authorised objective (Codex coverage review 2026-09-19 §2). Sequencing: after wave 1 as capacity frees; worker registrations only after P2 merges `worker.py`. Record: `docs/reviews/loop/sprint/F-DIN.md`. Items: DIN-12 (integration connections, the Salesforce mock adapter and canonical ingestion; `docs/BUILD_SPEC.md:7397`; after DIN-11, ticked), DIN-13 (Stripe mock adapter, adapter contract-test suite and reconciliation sweep; `:7426`; after DIN-12), DIN-14 (NetSuite chart-of-accounts mock and account sync; `:7452`; after DIN-13), DIN-18 (integrations screens; `:7548`; after DIN-17, ticked); plus PEND-OUTBOX (`PENDING_OUTBOX_HANDLERS` `(SYNC_REQUEST, DIN)` at `events/outbox.py:437` becomes a registered handler) and SCH-09 `integration_sweeps` (05 SCH table `05:935-956`; `worker.py:112-189` registers 8 of 15 today). Spec anchors: phase 12 DIN `docs/BUILD_SPEC.md:7071-7583`; GATE-DIN `:7572`.

## Scope
Serial DIN-12 → 13 → 14 → 18; adapters and their contract-test suite run against in-repo mocks only; DIN-9 (built, L7-4) is a record item for P9, not this lane. GATE-DIN is a prerequisite of F-CLO CLO-15/CLO-27 and F-RPS RPS-23, so this lane precedes them.

## Boundary (00-GOAL §4 `docs/00-GOAL.md:98`; §2 item 14 `:75`)
No live call to Salesforce, Stripe, NetSuite, QuickBooks or any third-party API; adapters are built and tested against mocks only; no credentials or connection secrets anywhere in the tree; Terraform artifacts (P3) are never applied. A production tenant operates without these mocks (CSV/API ingestion, DIN-1..11, are ticked).

## Fail-first tests and evidence
Each item's BUILD_SPEC acceptance block (tests, journeys, screens named there pass on a clean tree); adapter contract suite green for every mock; `PENDING_OUTBOX_HANDLERS` empty (GATE-SOP exit criterion 11:3003-3011); SCH-09 `@app.periodic` registration with tests; ticks in PROGRESS/ticks.md with commit ids; lane record.

## Notes and shared files
Shares `domain/imports/*` with ENG-C2a (direction) and F-CTR (CSV v2) and F-LMG; `backend/erev_api/worker.py` with P2/P5 (merge after P2); `events/outbox.py`; frontend integrations routes and `messages/en.json` with F-WEB-R/F-ADM; migrations serialised (single Alembic head, `Makefile:225`).

## Dependencies
P2 before the SCH-09 registration; none for DIN-12..14 code (DIN-11 and DIN-17 are ticked); F-CLO CLO-15/27, F-RPS RPS-23/24 and F-DMO depend on this lane.

## Do not change
Engine behaviour (return engine questions to the owning ENG lane); answer-key expected values; the CSV/API ingestion paths already ticked (DIN-1..11) except through their own acceptance tests.

## Questions to return
Whether the mock adapters ship inside the production images or stay test/demo-only (a packaging question for P1/P2, not a scope question); the SCH-09 cadence and its per-tenant scope.

Common terms: `.run/supervisor/d91/lane-dispatch-common.md` applies (own worktree and `.env`; never the dev DB `erev` or ports 8190/5270; no git write beyond commits on the lane branch; fail-first tests; scratch under `.run/<lane>/`, never `/tmp`; never print `.env` or secret values; `make lint` not bare ruff; one gate slot for DB gates; commits end `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`; do not merge to main). Production additions: supervisor-only targets (Docker, network, Terraform provider download, live databases) are RUN by the supervisor on request and recorded in `docs/reviews/loop/supervisor-verification.md`; `skipped-no-daemon` / `skipped-not-installed` are never passes; live cloud provisioning, image publishing, remote pushes and paid actions need Ray's explicit authorisation at that step (00-GOAL.md:75,102; PRODUCTION-CONTINUATION §Work boundaries). Every lane adding a Makefile target extends `BUILT_TARGETS`/`BUILT_PHASES` in `backend/tests/unit/test_makefile_targets.py` in the same commit (BS1-D-11). Gates before reporting: `make ci`, `make test-pg` where DB code changed, plus the lane-specific evidence below; measured, none projected.
