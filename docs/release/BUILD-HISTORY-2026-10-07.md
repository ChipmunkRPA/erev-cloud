# Historical eRev build record

Archived from PROGRESS.md on October 7, 2026 to keep the active handoff concise. All dates,
claims and evidence below retain their original meaning; this archive is not a fresh verification.

## Status (historical release record)
- RELEASE CANDIDATE OF 1.0 DECLARED 2026-10-03 (ruling R-127; D-100): the production-readiness programme resumed on 2026-09-29 on Ray's instruction (D-99) ends with it. Record: `docs/reviews/loop/prod/RESUME-2026-09-29.md` (state, lanes, gate measurements; §6 items 40 to 43 are what is Ray's now). Stated limits of the release: `docs/release/LIMITS-1.0.md`. The plan of 2026-09-19 (`docs/reviews/loop/prod/`) is the historical record; brief `~/Plaid FinOps/eRev ASC 606 Review/PRODUCTION-CONTINUATION-20260919.md`.
- Main: the release candidate `f8e46e54` (2026-10-03 21:40 PDT, written 21:41) and, behind it, document commits only (the QA record, a row of the limits document, this record, ruling R-127, D-100; on 10-04 the screenshots (`docs/screenshots/`), `docs/guides/illustrated-guide.md` and, from its check against the screens, five sentences of the user guide and limits rows B3-12, B4-12, B6-8 and one of B.9). Release 1.0 = the product as built at the freeze `4832c645` with register indexes 308 (policy overrides withdrawn) and 309 (a product or a template cannot state three policy values that the books read for a contract alone; four that no rule reads stay a stated limit), decided under Ray's delegation of 10-03 (R-126). On `f8e46e54`: whole backend suite with exactly the standing 15 not passed twice, by name; vitest 2,034 and `make e2e` 189 of 189; lane WEB-QA's QA pass of record; images, compose bring-up, ZAP baseline, dependency audit, `terraform validate`, the restore drill, parity and thorough properties pass; `make answer-keys` (six standing keys), `make test-pg` (three capture witnesses) and `make controls-report` (46 of 49 controls) FAIL by standing causes; `make ci` and `make perf` not run — the release manifest is NON-STRICT ("not release acceptance"). Alembic head 0128 (chain … 0129, 0124, 0128); install on a new database. Rulings R-1 to R-127 (`docs/reviews/loop/prod/RULINGS-2026-09-29.md`). Record §5a holds every gate measurement.
- Nothing is deployed or published. On Ray's order of 10-04 main is pushed to one private repository of his, and nowhere else. The release gate is not an accounting sign-off. BEFORE PRODUCTION USE, not the programme's to close (limits document, class A): the independent revenue-accountant review (G12; package `docs/accounting/reviews/G12-REVIEW-PACKAGE-2026-09-30.md` with its addendum of 2026-10-01; the later candidates are in the rulings log), the hosted inputs UI-1 to UI-14, performance at volume.

## In flight
- Lanes (`.run/sup2/`: `lanes/`, `assignments.md`, `reports/`): nothing assigned; every lane stands by or has ended (ENG-FX l19, QA-BE w2 and ACCT l14 ended on 10-03; SECFIX-IMP w12 stopped). The next release's order is the limits document's class C.
- Known engine open items: three strict expected failures stand (limits document, behind the fifteen names): the sandbox-side close replay (SNP-2b; R-10), the historical basis's line cutoff (PLAN-SUMMARY candidate 113) and the Q-11 observation for the reviewer (AD-33). The earlier items of this line are closed: the ledger line's subject key by index 248, ENG-S14R10-FX-SIGN-1 by R-44 (a), CLO-LOCK-ORDER-1 by R-6.

## Done
- earlier ticks moved verbatim to docs/reviews/loop/sprint/ticks.md at COMMIT 74 (5 lines, 1366 bytes)
- [x] WEB-6 Workflow components (vitest 374) and WEB-7 Chart panel and chart module (vitest 400; recharts 3.10.1); SPEC-Q-239 to 245; evidence and test lines in `docs/reviews/loop/sprint/ticks.md`

- Sprint L1: 28 items ticked (lanes L1-1 to L1-5); level gates at 22c4437; tick lines and gate figures in `docs/reviews/loop/sprint/ticks.md`
- Sprint L2: 34 items ticked (lanes L2-1 to L2-5); level gates at 63b596a; tick lines and gate figures in `docs/reviews/loop/sprint/ticks.md`
- Sprint L3: 12 items ticked (lanes L3-1 to L3-3); level gates at a7a1bbd; END-9 and WEB-12 ticked in Sprint L4, END-10, WEB-15 and WEB-17 open; tick lines and gate figures in `docs/reviews/loop/sprint/ticks.md`
- Sprint L4: 15 items ticked (lanes L4-1 to L4-5); level gates at e0ff797; CTR-5, CTR-7, CTR-8, AKS-1 to AKS-3, WEB-15 and WEB-17 carried into L5; tick lines and gate figures in `docs/reviews/loop/sprint/ticks.md`
- Sprint L5: 9 items ticked (lanes L5-1 to L5-5); level gates at 4cf3013; CTR-5 and CTR-8 ticked in Sprint L6, the other unticked items carried; tick lines and gate figures in `docs/reviews/loop/sprint/ticks.md`
- Sprint L6: 18 items ticked plus CTR-5 and CTR-8 (lanes L6-1 to L6-5); level gates at 6fa3b50 and 2d8d40d; GPA-4, DIN-16, CLO-26, DIN-5 and DIN-6 ticked in Sprint L7; tick lines and gate figures in `docs/reviews/loop/sprint/ticks.md`
- Sprint L7: 16 items ticked (lanes L7-1 to L7-6, with GPA-4, CLO-26, DIN-16, DIN-5 and DIN-6 carried from L6); level gates at f5dd350; END-10 and RPS-7a ticked in Sprint L8; tick lines and gate figures in `docs/reviews/loop/sprint/ticks.md`
- Sprint L8 (remediation: D-88, D-89, D-89a, D-89b): END-10 and RPS-7a ticked (lanes L8-C, L8-R, L8-J, L8-D, L8-E; rulings applied and merged per the lane records); level gates at 30db7f4 (answer keys 170 of 174; the four failing ids resolved in Sprint L9 round A); CTR-20, CTR-7, CTR-12 and AKS-1 to AKS-7 carried into L9; tick lines and gate figures in `docs/reviews/loop/sprint/ticks.md`

- Sprint L9 round A (D-90 to D-90e; lanes L9-PLT, L9-RUN, L9-ENG): MOD-JS-06, RET-BR-03 and RND-CHK-003C in the release selection, ONB-CHK-121 out (173); G12 rc fixes QA-L9-7 and QA-L9-5a verified in pass 2; merge 22d6c6e and gates in docs/reviews/loop/sprint/L9-merge.md; tick lines and gate figures in docs/reviews/loop/sprint/ticks.md

- Sprint L9 round B (D-91 with errata; lanes ENG-B1, ENG-B2, ENG-B3; Codex independent review): C606-01..05 and the gaps guard implemented; nine D-91 keys in the release selection (182 of 182); all active 183 of 241 (58 standing failures, 2 withdrawn; all 243 key reviews pending); gates on main at 0104e86; CTR-20, CTR-7, CTR-12, AKS-1 to AKS-7 carried; tick lines and gate figures in docs/reviews/loop/sprint/ticks.md; record docs/reviews/loop/sprint/L9-round-B-merge.md

## Next
- Sequence (D-99 (7), D-100): the release candidate is declared. Next, by Ray: the accountant's review (G12), the hosted inputs and the hosted evidence, performance at volume, any reversal of a decision of R-126; then the next release in the order of `docs/release/LIMITS-1.0.md` class C. No live provisioning, remote push or publication without Ray's explicit authorisation at that step.
- Backlog measured 2026-09-29 by named acceptance tests present on main (`.run/sup2/spec_scan.py`; 431 items): unbuilt or partly built — WEB-16, WEB-24, CTR-6, 11, 13, 14, 16, 18, 24, 25, 27, 28, DIN-13, 14, 18, CLO-12, 14 to 22, 24, 25, 27, RPS-8 to 16, 18 to 22, SNP-3 to 5, LMG-1 to 11, PRP-1 to 3, FCS-1 to 8, AIX-1 to 12, SOP-3, 5, 6, DMO-1 to 34, PRF-2, 6, DEP-6 to 8, and the phase checkpoints.
- Accounting: VC-CHK-113 and AD-1 to AD-40, with the later candidates, go to the independent accountant with the G12 package; supervisor rulings stay labelled as such.
- Gate timings on a quiet machine (0104e86): ci 38 min; test-pg 1; properties 2 (ci profile; thorough about 70); parity 1; keys 1 each; screens e2e 6; avenmoor-serial 5. Under load batch #9's ci took 105 min. DB gates one at a time per database.

## Spec questions
- SPEC-Q-114 to 195 (PLF-1 to PLF-30): archived verbatim in `docs/reviews/loop/spec-questions-PLF.md` (193 during PLF-30; 194 and 195 at GATE-PLF).
- SPEC-Q-196 to 243 (WEB-1 to WEB-6): archived verbatim in `docs/reviews/loop/spec-questions-WEB.md` (196 to 226 during WEB-4, 227 to 243 during WEB-7) to keep this file under 20 KB; SPEC-Q-244 onward stay here until GATE-WEB.
- SPEC-Q-244 (WEB-7; DG-FE-08 "money strings are never converted to JavaScript numbers" vs DS-CMP-14 Recharts plots, which need numbers): `chartKit.plotNumber` converts a copy of an API string only for pixel geometry (bar heights, the bridge's running level, sparkline coordinates); every displayed figure, tooltip, table cell, summary and label is the API string through the format module, and low and high are chosen with the digit comparison `compareDecimal`. Totals come from the API (`totals`, row `total`), never summed in the browser.
- SPEC-Q-245 (WEB-7 small choices and copy no document fixes): DS-CH-02 uses Recharts range bars (`[low, high]`) instead of a transparent base series (same geometry); the Awaiting trigger column is separated by the band gap and a dashed rule, not an exact 16 px gap; a waterfall with an open period uses a 24 px top margin for the "Open" caption; 36 columns (DS-CH-01) and 12 rows (DS-CH-03) throw in development and tests, because paging and folding into "Other" need API figures; granularity and range paging are screen `controls`; the RPO chart of horizontal bars draws vertical value gridlines; Enter on an RPO row drills with `band: null` (every band); `ratioAboveOne` moved to `charts/ProportionBar.tsx`, which KpiStrip now renders (re-exported for its tests); `recharts ^3.1.0` locked at 3.10.1 (licence-check 0 findings). Copy: "View", "Chart", "Table", "The chart could not be loaded.", "No figures for this range.", "Amount", "Pending triggers", "Balance", "Increase", "Decrease", "Category", "Period", "Total", "{title} from {from} {opening} to {to} {closing}.", "Remaining performance obligations for {row}: {bands}; total {total}.", "No revenue for {scope} in this range."; RPO band column headers join label and code in code (DS-I18N-06). WEB-24 captures the charts in both themes (BS1-D-33).

## Supervisor verification needed
- Browser QA notes from the L6 captures (post-rc unless a lane touches the screen): SF-11 master rows truncate both over-delivery items to an identical "BG-AVM-000..."; SF-12:request shows the "Is active" row of a newly added role as a removal (No → —).
- D-81 (400257d, iteration 70): sprint lanes in worktrees `~/dev/erev-wt/<lane>` with records `docs/reviews/loop/sprint/<lane>.md`; `docs/build-spec/sprint/plan.json` was absent, so this serial loop kept BUILD_SPEC order and ticked WEB-7 here (the merge reconciles `frontend/src/components/charts/`).
- SUPERVISOR VERIFICATION NEEDED: make audit-deps (measured on the release candidate `f8e46e54` 2026-10-03: OK, python 0 in 77 of 77 pinned, npm 0; re-run at every release candidate).
- SUPERVISOR VERIFICATION NEEDED: make compose-verify (measured on the release candidate `f8e46e54` 2026-10-03: OK — readyz at once, CSP present, worker healthy; needs a Docker daemon; compose project `erev-verify` — never two runs at once).
- SUPERVISOR VERIFICATION NEEDED: make zap-baseline (measured on the release candidate `f8e46e54` 2026-10-03: OK, 0 fail / high / medium, 1 low, 3 informational; 05 SAR-43).
- SUPERVISOR VERIFICATION NEEDED: make backup, make restore-verify (measured on the release candidate `f8e46e54` 2026-10-03 through `make restore-drill`: verified — 12 stages, eight workspaces, 693 tables, 306 files, 11 anchors; the clone holds two rows more, the restore's own security events; the native backup and restore rehearsed on a throwaway compose PostgreSQL, project `erev-verify-drill` — never the dev or shared server, which must not receive the BYPASSRLS roles `EREV_BACKUP_URL` / `EREV_RESTORE_ADMIN_URL` need).
- SUPERVISOR VERIFICATION NEEDED: make tf-validate (measured on the release candidate `f8e46e54` 2026-10-03: OK; it fails where the checkout's path makes the gate's temporary directory longer than 86 characters — limits document, row B8-15; init -backend=false, fmt -check, validate only — never plan or apply).
- SUPERVISOR VERIFICATION NEEDED: make docker-build (measured on the release candidate `f8e46e54` 2026-10-03: OK, three images `:f8e46e542cf6` with the embedded manifest read back).
- Supervisor-verified 2026-09-13 (`docs/reviews/loop/supervisor-verification.md`): licence allow-list entries (SPEC-Q-63, 163).
- `GcpSecretManagerStore`, `GcpKeyProvider` (FND-4) are only mypy-checked; verify against GCP before hosted use (SPEC-Q-15, 16).
- Webhook client (PLF-24, SPEC-Q-189): TLS through the httpx `sni_hostname` extension is exercised only with `httpx.MockTransport`; verify one delivery to a real https receiver before hosted use.
- OIDC sign-in (PLF-27, SPEC-Q-192) is exercised only against the mock IdP; before hosted use verify one https sign-in with a real provider, including a confidential client secret through `client_secret_ref`.
- Stranded-task recovery (WEB-3c, SPEC-Q-220) is exercised with simulated Procrastinate rows; verify once with a real `make worker` killed mid-job.
- L9 merge (§7.4): docker compose -f deploy/compose.yaml config --quiet rc 0 at 22d6c6e (unset compose secrets warn only); docker build --no-cache of the three Dockerfiles rc 0 at 22d6c6e (.run/l9/docker/fresh/); multi-role browser QA pass 2 run for maya, priya and marcus, robert measured at the API level (docs/qa/G12-multi-role-qa-2026-09-17.md).
- L9 round B (§7.4): docker build --no-cache of the three Dockerfiles at 0104e86 rc 0 (.run/l9b/docker/fresh/; api 051de8c1…, worker ca344e69…, web 35f6028b…); compose config --quiet rc 0; no new browser pass (engine-only changes); robert's rendering owed.
- Launcher ports (WEB-3d, SPEC-Q-226) are exercised with `make -n dev-up` and `proc.sh status` only; verify one `make dev-up` in a review worktree with ports 8192 and 5272.

## Learnings / gotchas
- Merges: `git merge -F -` reads no stdin (message file under `.run/`); join id files with Python, since `cat` of files without a final newline fuses ids. `set -o pipefail` before `| tail`. `make fmt` rewrites files; ruff E501 flags docstrings. zsh: `status` is read-only (`rc=$?`). Never `cd` into the venv.
- Quick tests: `EREV_ENV=test backend/.venv/bin/pytest <paths> -q -p no:cacheprovider --basetemp=.run/pytest`. Never `from conftest import` or `import httpx`/`socket`/`smtplib` in a test (`support.http`, `support.network`). Fixture `PASSWORD` constants need a `scripts/secrets_allowlist.toml` entry.
- Mutation probes: `.run/mutations.py` selected by `EREV_MUTATION` (`PYTHONPATH=.run -p mutations`), patching in `pytest_sessionstart`.
- Gates: `make ci` (about 4 min) then `make test-pg` (about 1 min; never together), foreground with timeout 600000; logs `.run/<gate>-<item>.log`. Regenerate through `make registry-seed|openapi|tokens|fixtures`. New dependency: pyproject + `make setup LOCK=1`.
- DB: FORCE RLS binds `erev_owner` too; column grants refuse unlisted columns (42501); `WITH CHECK` runs after BEFORE triggers; no `%` in `text()` SQL. Config versions: tenant sessions insert DRAFT only; non-DRAFT probes use `platform_session("provisioning")` plus `set_tenant_context`.
- New revision: head id and function count in `test_migrations.py`, `schema_revision` in `tests/api/test_me.py`; `ROW_BUILDERS`; IM-S tables need `TRANSITIONS` and its tests. A changed function body keeps the older revision's body as its own constant.
- Routes: `route_class=GuardedRoute`; `Depends(command("<perm>"))`, `run_command(cmd, deps, fn)`. Domain never imports `api.*`/`adapters/*`; `create_app` stays database-free. `identity_session` only in `auth/**`, `api/v1/health.py`, `db/lint.py`.
- Tenants: provisioned tenants hold `tenant_admin` for the admin; settings through `registry.resolve.setting`, published with `support.rows.publish_registry_version`. ROLE_CHANGE `on_approved` reads the stored preview (`preview.store_preview`).
- Jobs: tests act as the worker (Procrastinate row `doing`, then `run_job`); sweeps cover every tenant, so assert own rows; `run_job` swallows handler assertions.
- Identity: secrets-check flags `TOKEN`/`SECRET` constants of 8+ characters. The next TOTP code is `time_step(now) + 1`. `security_event.occurred_at` and touch-trigger `updated_at` use the database clock.
- Frontend: DOM suites start with `// @vitest-environment jsdom` and call `cleanup()`. openapi-fetch gets `fetch: (r) => globalThis.fetch(r)`; fake timers need `notifyManager.setScheduler(queueMicrotask)`. Icons only through `components/icons/registry`. ESLint `--max-warnings 0`: key handlers on non-interactive elements go in an effect listener; `tabIndex={-1}` on `menu`/`option`/`listbox`/`tablist` containers. Never write the date 2025-12-31 or the word "premium" under frontend/src or backend, tests included (REQ-SEC-009 scan). U+00A0/U+202F need `\u` escapes. Date math lives in `lib/format`.
- Frontend checks from the repo root: `frontend/node_modules/.bin/tsc -b frontend`; `eslint --config frontend/eslint.config.js --max-warnings 0 <paths>`; vitest from `frontend/`. Catalogue messages need letters outside placeholders (DS-I18N-06 pseudo test). jsdom: no PointerEvent (`vi.stubGlobal("PointerEvent", MouseEvent)`), Node's `localStorage` shadows jsdom's (define an in-memory Storage on `window`), zero layout sizes; accessible names join adjacent spans without spaces (add `{" "}`).
- Virtual lists in jsdom: `installGridViewport()` (`src/test/layout.ts`) gives `role=grid` and `[data-virtual-viewport]` 720 px; `scrollToIndex` also needs `Element.scrollTo`, `clientHeight` and `scrollHeight` stubs. `f.*`, `sort` and `view` writes go through `withParams` raw pairs (URLSearchParams encodes `:` and `,`). `test_design_check.py` fails on any design-check warning (off-scale spacing such as `ps-7`) although `make lint` passes. zsh does not word-split `$VAR` path lists.
- Supervisor gates (L8): never run `make parity` beside a database-backed pytest (pg_advisory_lock timeouts error every case); macOS has no GNU `timeout`; a standalone `ruff check` from the repo root misreads first-party imports (use `make lint`); the next e2e run overwrites `.run/reports/e2e/report.json` and `frontend/e2e/.results`, so copy them first. (L9) chrome-devtools get_network_request on a 202 response can hang and wedge the MCP session for the rest of the session; read creation headers from the resulting URL run id (or curl) instead, and keep QA evidence in .run/l9/qa/ as you go. Commands need an Idempotency-Key header (API-C-04) and the Origin header when driven by curl. The request detail route is /approvals/requests/<uuid>, not the request number.
- Shared Postgres and the selection file (L9 round B): two lanes migrating the shared Postgres concurrently exhaust `max_locks_per_transaction` (`out of shared memory`); DB gates serialize through the gate slots (one PID per slot file). `docs/reviews/loop/sprint/rg-selection.txt` is ONE comma-separated line; append ids with a comma, never a new line (fc9b1ed → e6a0f28).
- Lane merges (L9 round B): the corpus-pin tests conflict at every lane merge and pins both lanes moved identically auto-merge one short — recompute the merged pins (234 + Σ new keys); a lane wait loop that pipes `pgrep -f` output through a pathname exclusion never excludes (resolve the PID cwd with lsof).
- Resumed programme (2026-09-30): a stale git-ignored `release-manifest.json` in a checkout (left by `make docker-build` / `compose-verify` before the schema head moved) fails every test that boots the app lifespan with "the release manifest names another schema revision" — delete it. The shared PostgreSQL lock table (6,400 entries, mostly held by other projects' suites) surfaces as SQLSTATE 53200, as HTTP 500s, as failed jobs and as missing columns after a migration-walk test died mid-walk: re-run before diagnosing (`.run/sup2/verify.py`). Conflict markers quoted inside prose broke the revision-union resolver until it matched markers at line start only.
- Supervising named lanes (2026-09-30): a lane's messages are NOT reliably delivered to an idle supervisor (85 lost for three hours) and a supervisor's message reaches a lane only when its turn ends — run `.run/sup2/inbox_watch.py` under a monitor and tell lanes to read their inbox file; a lane session's permission system may refuse `git merge main` or edits of shared test support — never take the refused step over, integrate the branch as it stands. Two lanes took the same build-spec fragment revision: every number comes from the register.


# Earlier October 7 continuation entries

## Validated policy override API — October 7, 2026

- PR #3 merged into public main (`6bca309`). Work continues on
  `codex/policy-override-authoring` from that merge.
- Enabled public draft creation for POL-122 (`balance.right_to_consideration`) at obligation scope
  and POL-047 (`sfc.discount_rate_basis`) at contract scope. Validate the registry schema, obligation
  ownership, nonblank rationale, mathematically valid periodic rate, and any linked reviewed
  same-contract judgement before storing a draft. Other policy keys retain the named refusal.
- Submission and approval recheck linked judgement validity. Approval locks group, contract and
  override before superseding the prior approval; creator/editor exclusions from PR #3 apply.
- Regressions use public creation through approval and calculation: POL-122 reclassifies balances
  and an approved successor reverses it; POL-047 reaches a real deferred-payment calculation
  following a reviewed financing assessment, activation and delivery. A successor corrects the
  inception rate and changes transaction price. Validation failures store no draft or approval;
  unsupported keys and entity-permission boundaries remain covered.
- Actual local verification: 304 policy, product-pinning, unit and architecture tests passed.
  All 15 final policy-domain tests passed again after adding entity-permission and valid judgement-link
  assertions. Mypy passed for both source files; Ruff lint/format, OpenAPI staleness and whitespace
  checks passed. Refreshed OpenAPI and generated frontend types. These are targeted checks, not a
  full-backend or production-readiness claim.
- C-2 remains partial: frontend authoring, POL-163 period-scoped exceptions, broader product
  readers and the database answer-key runner remain open. The wider C-3–C-17 backlog remains in
  `docs/release/LIMITS-1.0.md`. Repository completion only: no deployment, provisioning or live
  release certification is part of this work.

## Draft authors excluded from approval — October 7, 2026

- PR #2 was merged into public main (`4eecb0f`). The next work is on
  `codex/approval-author-exclusions`, addressing B1-14 / the authorship part of C-6.
- Approval subjects now exclude their draft's creator and successful content editors in addition
  to the submitter. The shared kernel applies the same exclusions to direct decisions, delegated
  authority, eligibility reads and notifications. SYSTEM writes preserve the human recorded in
  audit `on_behalf_of_id`; denied/failed audit events do not establish authorship.
- Attribution reviewed against each named subject:

  | Subject | Author evidence |
  | --- | --- |
  | Estimate version | Creator plus successful create/update audit actors and represented users |
  | Policy override | Creator plus successful creation audit attribution |
  | Modification | Creator plus successful create/update/classify audit attribution |
  | Manual event / attribute-change submission | Stored submission creator; inline author is also submitter |
  | Direct FX rate version | Creator plus successful version edits; imported versions retain uploader exclusion |
  | Principal/agent proposal | Authored and submitted in one command; request preparer is the proposal author |
  | SSP override proposal | Authored and submitted in one command; request preparer is the proposal author |

- Initial domain verification: 130 tests passed, one existing parity-entry-point skip, across policy
  overrides, FX, FX imports, estimates, modifications, manual events and the approval engine.
  Architecture plus approval-unit suites: 505 passed. After SYSTEM-attribution hardening,
  23 focused domain/product/SSP tests passed, including separate draft authors and submitters,
  delegated decisions and direct-entry FX editors. All 238 approval-unit tests passed again on the
  final source. Mypy passed for both source files; Ruff
  lint/format and whitespace checks passed. This closes B1-14; the other C-6 controls remain open.
- Next: validated policy-override authoring and its real calculation workflows (C-2). No
  independent accounting sign-off or full-backend/CI claim is made by these targeted checks.
- Archived the earlier build-loop record unchanged into
  `docs/release/BUILD-HISTORY-2026-10-07.md`; the active progress file is again below 20 KB.
  Historical evidence remains dated. No deployment or provisioning.

## Repository-only scope and policy calculation continuation — October 7, 2026

- Owner clarified the scope: finish the repository; do not deploy or provision anything. Cloud
  project/domain inputs are not needed for this work. Independent accounting review and operational
  release gates remain documented requirements for an eventual operator, not tasks to perform here.
- Import recovery PR #1 was merged into public main (`a83b1dd`). Work continues on
  `codex/policy-override-calculation` from that merge.
- C-2 calculation foundation: approved contract-pinned overrides now reach bundle assembly as of
  its cutoff, with obligation > contract > product precedence and member isolation. Draft and
  future approvals are excluded; superseded rows support historical cutoffs. Current approval
  wins deterministic timestamp ties in both the resolver API and bundle reader.
- Fixed two pinning hazards: a scoped value is never promoted to a group default on recomputation;
  a shadowed product default is retained as PRODUCT-scope bundle metadata for subsequent product
  pinning. PRODUCT metadata is not a contract lookup candidate and is not a group policy pin.
- A PostgreSQL regression uses the real submit/approve/compute/persist path: POL-122 changes earned
  unbilled balances from contract assets to receivables without changing their sum; repeated
  computation preserves scope, and an approved successor restores the conditional classification.
  The draft row is seeded by the fixture because public creation remains disabled.
- Actual verification: 50 tests passed across policy domain, product-pin domain/unit, scoped-input
  unit and engine kernel suites; all 267 architecture tests passed. Mypy passed for six changed
  source files; Ruff lint/format and git whitespace checks passed. An additional 346 transaction-price,
  balance-engine and scoped-input tests passed. All checks were local; no cloud services used.
- C-2 remains open: public authoring validation and approval controls, POL-163 period-scoped
  exception handling, a full significant-financing workflow and the platform answer-key runner
  still need completion. This is calculation infrastructure, not a claim that policy overrides
  are available in the UI or that the repository is production-ready. No deployment performed.

## Continuation — October 7, 2026 (America/Los_Angeles)

- Branch `codex/import-job-recovery`, based on public main `43631fc`. Closed the implementation
  of B5-3 / C-1 on this branch: a failed import commit waits for a competing upload-row lock;
  if cleanup times out or fails, its required failure hook rolls settlement back for the job
  sweeper to retry. Cancelling a queued import commit now ends its upload atomically, releasing
  its source for a fresh upload. A late dispatch cannot commit the cancelled job.
- Added four PostgreSQL regression tests covering held rows, queued cancellation/re-upload,
  cancellation rollback and cleanup-timeout recovery. Both original bug cases reproduced on
  unmodified application source before the fix. Actual verification: 52 tests passed across
  import transient-failure, job domain/API and registry unit suites; the expanded re-upload test
  passed separately. All 267 architecture tests passed. Mypy passed for all four changed source
  files; Ruff lint/format and git whitespace checks passed.
- Tests used a newly initialized, disposable PostgreSQL 17 cluster on localhost port 55437 and
  database `erev_rv_cont`, with separate unprivileged owner/app roles and ignored fresh local keys.
  No existing database, deployment or external provider was used. Dependencies installed from
  the frozen backend lockfile. No schema migration or accounting calculation changes.
- This prevents new stranded commits; it does not bulk-repair historical terminal jobs. All other
  limitations and October 3 test failures remain historical and unresolved unless stated here.
  Full backend/CI, live deployment, accounting review and volume performance were not rerun.
- Next implementation item: C-2, policy overrides that actually reach calculation, including
  POL-122 and the significant-financing rate path. Independent accounting decisions remain reviewer work; hosted inputs are outside the
  owner's clarified repository-only scope. Research folders and removed website references stay excluded.

## Contract-period policy isolation — October 7, 2026

- PR #5 merged into main (`be91991`), completing the two-policy workbench slice. The owner
  instructed automatic merging after verification and retention of **main only**. GitHub automatic
  merged-branch deletion is enabled; the four older merged branches were deleted locally/remotely.
  Future implementation branches are temporary and must be removed after merge.
- Work continues on `codex/contract-period-policy-scope`. POL-163 needs more than admitting another
  key: the FX engine currently treats the whole group/entity as one liability unit. A contract's
  exception must not change neighboring contracts in that unit.
- Added a CONTRACT_PERIOD bundle identity and resolver precedence over the entity PERIOD default.
  Identity encodes contract, entity and period unambiguously. Pin P and level C are required; both
  entity and period are required to read it. Existing readers without a contract still receive the
  entity default.
- Bundle assembly resolves approved POL-163 rows separately for each member and entity period,
  using the earlier of the known-at cutoff and the entity-local period end. Prior approvals remain
  eligible for their historical periods after supersession; later approvals cannot rewrite an
  earlier period. Forced IFRS15 treatment excludes these rows. Scoped exceptions never become the
  widest-scope persisted policy pin.
- Actual verification: 48 scoped-policy, period-row, resolver and PostgreSQL policy-domain tests
  passed. A further 590 kernel, FX engine, architecture and database period-policy tests passed,
  including the final persisted-pin assertion. Mypy passed for five source files; Ruff lint/format
  and whitespace checks passed. No full-backend or live-release claim is made.
- Initial publication attempts on October 7 returned GitHub internal server errors for both Git
  pushes and PR creation. The local commit is preserved; check the remote PR and main before
  treating this slice as published. Repository metadata confirms push/admin access and no archive.
- This is the isolation foundation, not completion of POL-163. Public authoring stays refused until
  FX liability layers carry their originating contract and use its period-scoped treatment for
  consumption and remeasurement, with monetary/historical transitions and mixed-member tie-outs
  verified. Those readers, actual FX journals, close behavior and UI remain next. No deployment.

## Policy override workbench — October 7, 2026

- PR #4 merged into public main (`51aa535`). Work continues on `codex/policy-override-ui`.
- The contract workbench now offers Policy overrides to users with entity-scoped `config.read`.
  Authoring additionally requires `contract.create` for the contract's entity. Historical views
  expose no command. Drafts can be authored before activation, including financing rates.
- Added POL-122 obligation/right and POL-047 contract/rate forms. Rates remain decimal strings;
  the screen explains inception rates and corrections. Saving creates a durable draft; submission
  is a separate action on that saved record. Reopening or retrying submission reuses the draft.
  The list displays scope, value, rationale, status and an approval-request link where present.
- Commands invalidate the contract override list along with the existing contract reads. Required
  fields, server refusals, network failures, list retry and read-only access have explicit behavior.
  Existing API validation and independent-approval controls remain authoritative.
- Actual verification: all **2,040 frontend tests across 191 files passed**, including six new drawer
  tests and the 66 workbench tests. TypeScript project build, changed-file ESLint, production frontend
  build, formatting and whitespace checks passed. Design check scanned 499 files with no findings.
  Local Chromium screenshots of both forms were inspected with mocked records and no runtime errors;
  this is UI verification, not live-service or accounting sign-off evidence.
- Remaining C-2: POL-163 period-scoped contract exceptions, broader product readers, database
  answer-key coverage, and an optional reviewed-judgement attachment selector in this drawer (the
  API already accepts and validates that link). Wider outstanding items remain in LIMITS-1.0.md.
  Current scope remains repository completion; no deployment or provisioning.

## Balance-aging liability reader and reconciliation — October 7, 2026

- Continued from merged PR #14 (`5d48cb0`). Replaced the aging draft's liability subledger
  reader with T-CON-18 movements for exactly the versions selected by its balance report binding.
  The original creation date survives partial consumption; transaction amounts exclude FX
  remeasurement, future movements and other books. A remaining layer without a creation date
  refuses rather than assigning a guessed age.
- Strengthened `TO_AGING_EQ_BALANCES`: agreement is required per contract, entity, role and currency,
  as well as currency grand totals. Misclassified or misattributed amounts can no longer offset
  each other and produce a passing tie-out. The existing public money-result shape is preserved.
- Verification: **495 report unit tests passed**, plus **13 targeted tests** including a PostgreSQL
  layer projection regression. Source Mypy, Ruff lint/format, design and whitespace checks passed.
- The report remains unregistered. Asset/unbilled attributions still require replacing the interim
  subledger source, and pre-0131 versions lack movement coverage. This change does not close RPS-12,
  POS117, full-backend verification or accounting sign-off. No deployment.

## Per-layer liability close monitor — October 7, 2026

- Continued from merged PR #13 (`5b45532`). The negative-liability monitor now projects
  current-version T-CON-18 movements through the period end, separately for each originating
  contract/layer. Consumption reduces both currencies; remeasurement changes functional carrying
  only. Either currency below zero raises a blocking finding without netting against positive layers.
- Regression coverage exercises transaction and functional deficits, future movements, other books
  and entities, repeat-run deduplication, and resolution after a corrected version replaces obsolete
  movements. The data-quality gate fails for a deficit and passes after the correction.
- Verification: **68 PostgreSQL monitor and pure-rule tests passed**; source Mypy, Ruff lint/format,
  design and whitespace checks passed. This is targeted evidence, not a full-backend pass.
- Versions predating revision 0131 still lack movement coverage. Balance aging remains unregistered
  pending its projection, presentation and historical reads. Full-backend verification and independent
  accounting review remain open. Repository work only; no deployment.

## Immutable FX layer persistence — October 7, 2026

- Continued from merged PR #12 (`afefe85`). Revision 0131 follows the actual prior head 0128
  and adds T-CON-18 `fx_layer_movement`: immutable rows, tenant/entity RLS, role/kind checks,
  tenant-bound version/contract/entity/event/rate foreign keys and currency references.
- New computations persist their complete engine movement set atomically with the version and
  audit facts. Each movement retains its layer owner's contract, including cross-member consumption,
  independent of the consuming event. Asset, receivable and monetary-liability creation now carry
  ownership through the engine output. No ownership is guessed from encoded layer-key strings.
- The writer preserves transaction/functional currency minor units, signed remeasurement amounts,
  applied rates, pinned rate IDs and trace nodes; a real source event is linked when present.
  Synthetic time/estimate sources remain trace-linked. Unknown owners/rates, mismatched rate versions,
  floats and boolean amounts refuse before movement insertion. Existing versions are never rewritten.
- Registered the table in audit ownership, privacy classification and regenerated snapshot data;
  moved it out of the unbuilt table/enum inventories. Demo/volume generator versions are now 11/16
  because persisted seed state changes. Historical seed and performance evidence stays dated.
- Verification: **433 engine/architecture tests passed**, with the existing Q-11 accounting-review
  xfail unchanged; **107 persistence/privacy/snapshot/demo-policy tests passed**; **47 combined
  migration-head/performance/persistence tests passed**. Source Mypy and Ruff lint/format pass.
  **66 PostgreSQL calculation, isolation, immutability and migration tests passed**, including
  upgrade/downgrade/upgrade and schema lint. These are targeted checks, not a whole-backend pass.
- Balance aging remains unavailable: its builder still uses the interim subledger source and needs
  a layer projection, asset/unbilled presentation and historical-version handling. Prior versions have
  no backfilled movement set. The negative-liability monitor still uses aggregate balances and needs
  a layer-level collector. Full-backend verification and independent accounting sign-off remain open.
  Repository work only; no deployment.

## Period loss-test persistence — October 7, 2026

- Continued from merged PR #16 (`4a845d0`). Revision 0133 persists T-CON-17 loss tests per
  calculation, owning contract/unit and accounting period. Rows retain scope, measurement basis,
  transaction-currency amounts and trace-node mappings, under immutable tenant/entity isolation.
  The earlier draft key omitted period identity even though the engine emits multiple periods.
- T-CON-25 `loss_provision_eac` retains every contributing EAC version with tenant-bound foreign
  keys. The parent convenience reference is set only for a single contributor. The writer refuses
  unresolved/foreign-owner EAC references, invalid unit/period identities and inexact numeric types
  before inserting results; all rows and audit facts commit with the calculation.
- Updated privacy, schema/type, enum and snapshot inventories, row fixtures and audit ownership.
  Loss rows are regenerated on snapshot replay. Demo/volume generator versions are now 13/18.
  Historical versions are not backfilled; the loss register remains unregistered.
- Newly reproduced calculation discrepancy: after K03's September change order, the persisted
  engine loss test states consideration 1,200,000 and margin 350,000, while the existing RPT-31
  acceptance requires 1,350,000 and 500,000. EAC 850,000, costs 502,000, revenue 797,294.12 and
  zero provision are preserved correctly. The original register acceptance is unchanged; storage
  tests compare against emitted engine results and do not certify those discrepant amounts.
  Next: trace the stale unconstrained-price view (`s04_transaction_price/unconstrained.py`, consumed
  by `s11_costs_loss/loss.py::_consideration`) through modifications before enabling the report.
- Verification: **7 PostgreSQL persistence/migration/grant tests**, **4 tenant/entity isolation tests**
  and **9 computation regressions passed**. **86 persistence/privacy/snapshot unit tests**,
  **26 final schema/type/persistence checks** and **32 report/demo/generator checks passed**.
  The broad architecture run passed 351 checks; its sole column-order failure was corrected and
  verified by the final schema checks. Source Mypy, Ruff and design checks passed.
- Full-backend verification and independent accounting sign-off remain open. No deployment.

## Dated loss consideration — October 7, 2026

- Continued from PR #17 (`019d64e`). The book fold now rebuilds each contract's unconstrained
  consideration at boundary dates and period ends. Approved amendment/exercise amounts are
  scoped to their owner and included before the collection cap. VC versions, realised amounts
  and other Stage-04 components are measured at the historical date. Loss and impairment share
  this corrected view. The fold's cache key now includes the horizon.
- K03's unchanged September expectations now pass in PostgreSQL: consideration 1,350,000,
  margin 500,000, costs 502,000, EAC 850,000 and revenue 797,294.12. The same version preserves
  August consideration 1,200,000. Persistence and EAC-v3 lineage checks remain intact.
- Verification: 550 engine regressions passed, with one existing expected failure (Q-11 deposit
  observation). The new price-only concession/collection-cap and VC-date regressions pass.
  The final book/demo/volume run passed 84 checks and exposed one stale seed-version fixture;
  that fixture was corrected and all 14 policy tests then passed. All 46 import/purity checks
  passed. Source Mypy, Ruff and design checks pass.
  Demo/volume generator versions 14/19 distinguish the changed stored calculations.
- Historical calculations are not backfilled. The loss-register projection/registration and its
  public report acceptance remain next; full-backend verification, the broader limitations and
  independent accounting sign-off remain open. Repository work only; no deployment.
- Earlier period-loss persistence evidence is archived in
  [BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).

## Loss provision register enabled — October 7, 2026

- Continued from merged PR #18 (`4d79cfd`). RPT-31 now reads period loss-test rows and every EAC
  contributor from the report-bound contract versions. It filters by book, entity, owning member,
  accounting period, loss scope and optional nonzero provision. Row keys distinguish contract
  and obligation units; totals retain separate currencies. Multiple EAC contributors are listed
  explicitly, with no arbitrary single version selected.
- The adapter retains calendars, selected versions and contract/obligation/EAC labels for reruns.
  Trace coverage refuses missing persisted period tests, including zero provisions from older
  versions. No historical backfill. Revision 0134 updates the previously unavailable report's IPE
  metadata and restores its immutability guard in the migration transaction.
- The original K03 public report acceptance passes. A second PostgreSQL regression verifies a
  changed fresh report, identical same-source rerun rows/hash after later changes, August's
  unchanged 1,200,000 consideration, zero-provision filtering, empty entity scope and JSON/CSV/
  XLSX/PDF generation. The report unit suite passes all 507 tests; six migration/report-schema
  tests pass, including upgrade/downgrade/upgrade and the report-definition immutability check.
  Source Mypy, Ruff and design checks pass.
- Remaining RPT-31 work: provision-cell Explain drill and functional/reporting currency when
  currencies differ. Explicit locked-source reads remain refused; ordinary bound reruns work.
  There are now 39 registered builders and 17 unavailable definitions. Standing acceptance 12
  is closed; broader C-11 work, full-backend verification and independent accounting sign-off
  remain open. No deployment.
- Previous loss storage and calculation evidence is archived in
  [BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).

## Loss provision Explain drill — October 7, 2026

- Continued from PR #19 (`f6d3ffe`). The RPT-31 provision cell now names its immutable T-CON-17
  contributor using the original report's bound versions, calendars and labels. The viewer opens
  the existing contributor/Explain flow only for the supported provision-balance column.
- Explain and Verify resolve the stored loss-test trace node, amount, period and entity. A different
  explicit period or unsupported measure is refused. Added the contributor's entity-reach rule,
  the typed API object and frontend parser support; regenerated OpenAPI and TypeScript types.
- PostgreSQL verification: the cell and contributor resolve, verification matches the saved amount,
  later calculations preserve the original contributor while a fresh report names a new one, and
  an outside-entity reader receives 404 from both Explain and Verify. The report/Explain unit
  suite passes all 515 checks; all 11 existing Explain API/entity-scope tests pass.
  The 42 existing viewer tests and the new loss-column drill test pass.
  Source Mypy, frontend TypeScript, Ruff, ESLint and design checks pass.
- Foreign-currency functional/reporting loss views and explicit locked-source reads remain open,
  as do the broader release backlog, full-backend verification and independent accounting sign-off.
  No deployment. Previous loss-register evidence is archived in
  [BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).

## Password-change lockout — October 7, 2026

- Continued from PR #20 (`762666b`). Closed release limitation B1-34: incorrect current passwords
  during password changes now consume the identity's shared sign-in failure budget. The fifth
  consecutive failure locks for 15 minutes; an active lock refuses even a correct password.
- Password verification, counter updates and a successful change hold the same identity-row
  write lock. Refused attempts commit their counter and security evidence before returning the
  error. LOGIN_FAILED evidence carries purpose `password_change`; ACCOUNT_LOCKED records the
  threshold. A correct verification clears consecutive failures, including when the proposed
  new password is rejected by policy. Existing session rotation and reset-token invalidation stay.
- Four PostgreSQL password-change tests pass, including concurrent attempts sharing earlier
  sign-in failures, audit persistence, expiry, successful retry and session-rotation behavior.
  All 33 surrounding sign-in/invitation/reset/CSRF and password-race regressions pass. Three
  password-change viewer tests pass, including the lockout banner. Mypy, TypeScript, Ruff,
  ESLint and design checks pass; OpenAPI and generated types include the 423 response.
- Full-backend verification, remaining release limitations and independent accounting sign-off
  remain open. Repository work only; no deployment. Previous dated evidence is archived in
  [BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).

## Frontend verification commands — October 7, 2026

Source: `30a42456841bc7bbda48edb9a1c8160e46fd7975` (PR #22), Node 24.5.

- From `frontend/`, `./node_modules/.bin/vitest run --bail=1`: 192 files and 2,042 tests
  passed in 64.57 seconds. jsdom logged its unsupported full-page navigation warning;
  this was not a failed test and does not prove real-browser navigation.
- From `frontend/`, `./node_modules/.bin/tsc --noEmit`: exit 0.
- From the repository root, `frontend/node_modules/.bin/eslint --config
  frontend/eslint.config.js --max-warnings 0 frontend/src frontend/config frontend/e2e`:
  exit 0. This is the Makefile's frontend lint scope. An earlier exploratory `eslint .`
  also scanned the ignored `.run/policy-preview.tsx` and failed its non-null assertion;
  that local scratch file is not published and was left unchanged.
- From `frontend/`, `./node_modules/.bin/vite build`: exit 0 in 3.83 seconds. The initial
  chunk was 1,149.57 kB (300.49 kB gzip), above Vite's warning threshold. No bundle-budget,
  browser-performance, end-to-end or deployment claim follows from the build.
- Full backend verification continues separately; production readiness remains unproven.

## Frontend verification — October 7, 2026

- Verified source at merged PR #22 (`30a4245`): all **2,042 frontend tests across 192 files**
  pass; TypeScript, the Makefile-defined ESLint gate and the production Vite build pass.
- Vite warns that the initial chunk is 1,149.57 kB (300.49 kB gzip). Build success does not
  establish browser performance or end-to-end behavior. Browser gates remain to be verified.
- The remaining backend run (excluding the already verified engine/architecture suites and
  separate parity/answer-key/performance gates) is still running. No whole-backend pass is
  claimed. Implementation limits and independent accounting review remain open; no deployment.

## Consideration history across fiscal calendars — October 7, 2026

- Continued from merged PR #21 (`ee00858`). A broader backend run selected 9,975 tests,
  excluding parity, answer-key and performance gates. It stopped after 1,096 passes at the
  mixed Stage-06/08 share-based consideration case: a performing 4-4-5 year ended January 1,
  2028, beyond the contracting calendar, and the new consideration history requested a VC
  policy for that uncovered date. This run is not a whole-backend pass.
- Incidental period-end measurements now require coverage in the contracting calendars.
  Covered performing cutoffs remain in the history for impairment; actual boundary-event dates
  retain their existing validation. The original mixed-producer accounting figures and trace
  assertions remain unchanged. The regression also checks that August 29 is retained and
  the uncovered January 1 is excluded.
- All 96 targeted share-based consideration, book-fold and cost/loss checks pass. Ruff and
  source Mypy and design checks pass. The complete engine/architecture run passed **1,996**
  tests with one existing Q-11 expected failure; there were no unexpected failures.
- Remaining backend and specialist gates, documented release gaps and independent accounting
  sign-off remain open. Repository work only; no deployment. Earlier dated evidence is preserved
  in [BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).


## Baseline browser and dependency verification — October 7, 2026

Source: main `b570edbc0448015c769106cc99c7f42e4fc4f592`, before modification-confirmation changes.
The local `scripts/e2e.sh` open-world harness passed **189 tests**, with zero failures, flaky
or skipped tests, against a separate disposable UTF-8 PostgreSQL database and local API/worker/web.
Fresh-tenant, industry and design projects contain no tests. Closed-world and QA-RC were not run.
The initial database attempt used SQL_ASCII inherited from the local template and failed driver
initialization; the empty test database was recreated as UTF-8 before the successful run. All
harness processes were stopped. Nothing was deployed.

`scripts/audit_deps.sh` directly audited 77/77 pinned Python runtime dependencies (five markers
removed) and production npm dependencies: zero reported vulnerabilities. Combined output digest:
`29f7238ca4cffab044dd38b70b158f31dd0e3a092e39557ae58d47a6c235c2c6`.
This was a direct script run, not an immutable gate-context wrapper. License scan: 133 packages
(77 Python, 56 npm), seven allowlisted, zero findings/allowlist errors. Secret scan: 3,388 files,
eight allowlisted, zero findings/unused allowlist entries.

The separate backend run excluding engine/architecture and parity/answer-key/performance markers
was intentionally interrupted to permit main to advance. JUnit contains **824 completed cases,
zero failures/errors/skips**, over 2,630.614 seconds. Interrupt teardown raised a pytest temporary-path
stash KeyError. The run is incomplete; it is not a passing full-backend gate. These results apply
to the baseline SHA above, not the subsequent confirmation change. Earlier engine/architecture
and frontend evidence retains its own source/date.


## Balance aging enabled — October 7, 2026

- Continued from merged PR #15 (`cde41c8`). Stage 10 now retains each obligation's separate
  contract-asset/unbilled share, revenue date and owner in the immutable calculation trace.
  The report reads those period-end attributions and T-CON-18 liability layers from the exact
  selected versions, including historical cutoffs and retained rerun bindings. It no longer
  depends on close journals or ERP invoice postings. Earlier periods never read later attributions.
- Registered RPT-36 and its source contract. Entities, calendars, labels and version selections
  follow the report's retained inputs. Revision 0132 corrects the previously unavailable report's
  source description; its migration restores the schema's immutability guard within the transaction.
  Demo/volume generator versions 12/17 identify the changed persisted trace content.
- The CHK-010 test setup now obtains P1's unconditional-right policy through the public POL-122
  override and independent approval path instead of relying on an ignored product-level pin.
  POS117 passes on the database platform with its original expected figures. The historical
  direct-builder witness also passes after later April calculations. A new rerun regression proves
  later billing changes a fresh report but leaves the original report's rows and output hash intact.
- Verification: **554 report/answer-key unit tests passed**, **8 PostgreSQL report tests passed**,
  and **10 migration/report-schema tests passed** (including upgrade/downgrade/upgrade and the
  immutability guard). The final historical/acceptance/rerun check passed all **4 tests**, including
  JSON, CSV, XLSX and PDF generation. Stage-10, reclass-FX, demo-policy and volume checks passed
  in the broader targeted run; this is not a full-backend pass. Source Mypy and Ruff checks pass.
- Versions without the new aging payload refuse rather than guessing dates or presentation.
  No historical data is backfilled; an unchanged-input recomputation may reuse an older version.
  Foreign-currency functional aging is still unsupported; transaction view is available. Independent
  accounting sign-off, other report builders and full-backend verification remain open. No deployment.

Earlier October 7 liability-reader, close-monitor and layer-persistence evidence is archived verbatim
in [BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).

## Modification questionnaire confirmation — October 7, 2026

- Continued from main at PR #23 (`b570edb`). Submit now requires explicit boolean answers to
  every retained classification proposal on every paired row. Approval rechecks older pending
  requests before application. Classification/preview never confirm proposals themselves.
  Invalid non-boolean answers are refused; drafts remain editable and edits invalidate old previews.
- Synthetic preparers and fixtures explicitly save answers, reclassify and preview through the
  commands. Volume generator 20 identifies that flow. No expected accounting figures changed.
  Closed B1-6 in LIMITS; the other C-6 controls remain open.
- Verification across split runs: **61 modification database tests passed, 1 existing skip**;
  **20 related integration/report/scope/audit tests passed**. Earlier fixture failures were resolved
  by explicit confirmation and including its audit entry; the final remainder passed 25/25.
  Both the linked J-06 calculation and older pending-request refusal/revision passed. **123 combined
  unit/volume checks passed**, including the 1/1000 database seed; this does not establish full-volume
  modification coverage. Ruff, source Mypy, whitespace and design checks (500 files) pass.
- A refused concurrent database run is not counted. Baseline `b570edb` open-world browser harness:
  **189 passed**, zero failures/flaky/skipped; fresh-tenant, industry and design projects have no
  tests. Baseline dependency/license/secret scans have zero findings; dated details are archived.
- Baseline backend verification was intentionally interrupted to advance main: JUnit records
  **824 completed cases, zero failures/errors/skips**; interrupt teardown raised a pytest stash
  KeyError. This is incomplete evidence, not a green backend gate. Full-backend/specialist gates,
  remaining release limitations and independent accounting review remain open. No deployment.
- Owner requested automatic PR merging and only main retained. GitHub auto-merge and automatic
  branch deletion are enabled; verified changes are merged before completed branches are removed.
  Dated evidence: [BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).

## Volume delivery quantities — October 7, 2026

- Continued from merged PR #11 (`cf727a1`). Reproduced LIMITS standing failure 8: the 1/1000
  database seed refused a delivery of 7 with only 3 remaining. The generator split total quantity
  exactly to two decimals, then rounded every batch independently to a whole number.
- Retained the exact fractional quantities accepted by the command schema. Every batch is
  positive, every prefix stays within its contracted quantity, and completed schedules sum to
  exactly that quantity. Generator version 15 gives the changed event facts a new dataset identity;
  the full manifest still has 1,262,407 events. No delivery validation or expected accounting
  amount was loosened.
- Verification so far: **46 pure volume/performance tests passed**, including the new full-scale
  delivery invariant; Ruff lint/format, source Mypy and design/whitespace checks passed.
  The corrected PostgreSQL seed **passed**, with original assertions for all groups, event
  totals, estimate approvals and evidence attachments. No full-volume database performance claim.
- Balance-aging investigation: stage 12 already emits `BookOutput.fx_layer_movements`, but
  computation persistence writes no T-CON-18 rows. The current report draft reads subledger lines
  and is incorrect under ERP billing. Persisting immutable layer movements with source-event and
  FX-rate lineage is a prerequisite to exposing that report. It remains unregistered.
- Broader repository gaps and independent accounting sign-off remain open. No deployment.

## Migration capture calendar and POS117 recheck — October 7, 2026

- Continued from merged PR #10 (`8876bd8`). Reproduced all three migration-capture failures
  listed as names 13–15 in LIMITS: each refused Contract 3 because its February inception had
  no accounting period. The fixture only supplied January despite importing the complete source.
- The two full-source fixture setups now supply January and February 2023. Source databases,
  expected amounts, product validation and worker behavior are unchanged. All existing exact
  balance, entity mapping, SSP reuse, approval/audit, capture count and immutability checks remain.
- **7 PostgreSQL capture tests passed**, closing all three named failures; **3 related PostgreSQL
  reconciliation/report tests passed**. Ruff lint/format and whitespace checks passed. These are
  targeted results, not evidence of a green whole backend or completed migration functionality.
- Also ran the real database POS117 answer key: **103 steps applied, 0 refused**, contract and
  subledger blocks compared clean. Its former four numeric mismatches are resolved by the policy
  work. The key still does not pass because balance aging lacks its persisted layer source and
  registered builder. The canonical `make answer-keys AK_SCOPE=full` already selects the database;
  ordinary pytest defaults to memory. Do not treat that default as the canonical gate's behavior.
- Remaining work includes balance-aging layers/reporting, GT07 nondistinct review mapping, the
  broader release backlog and independent accounting sign-off. No deployment.

## Close task sign-offs — October 7, 2026

- Continued from merged PR #24 (`383ef03`). Manual task signing now enforces the template's
  owner role for the period's entity, in addition to permission and MFA. Closed/permanently
  locked periods refuse new signatures. Signing locks the template as well as the item.
- An approved reopen resets passed manual tasks to NOT_STARTED and clears the current signature
  pointer, with an audit event linked to the reopen request. Immutable historical signatures stay.
  A fresh signature binds the close cycle and owner role; revision 0135 permits that history while
  preserving uniqueness for other sign-off subjects. A lossy downgrade explicitly refuses.
- **60 database checks passed across scoped runs**: 53 close/cockpit/waiver/lock/transition-drift
  tests, five migration checks (including complete downgrade/upgrade), and two signoff invariant
  checks. The six new workflow cases cover missing/other-entity/exact/all-entity owner roles,
  reopen/re-sign with immutable history, and closed-period refusal. Lossy downgrade refusal is
  verified with the real owner lacking BYPASSRLS; rollback preserves all signatures and forced RLS.
- **33 transition/locking unit tests passed**; source Mypy, Ruff and the 500-file design check pass.
  A stale migration-head test pin was corrected to 0135. No accounting amounts changed. Closed B1-9;
  the other C-6 controls remain open. Existing rows are not rewritten by the migration: task resets
  occur on an approved reopen through the new command path.
- The separate index audit found an existing 0131 index defect: `ix_fx_layer_movement__layer`
  puts `layer_key` behind the non-leakproof `book_code` enum comparison under RLS. This was not
  waived; the next schema fix must reorder its keys and rerun the index audit. No whole-backend
  pass is claimed. Other release gaps and independent accounting review remain open. No deployment.

## FX layer index under RLS — October 7, 2026

- Continued from merged PR #25 (`7b4eb69`). The index audit reproduced an existing 0131 schema
  defect: `layer_key` followed `book_code`, whose enum equality is not leakproof under RLS.
  Revision 0136 moves the enum to the final key, preserving the tenant/contract/layer prefix.
  Accounting data, grants and policies are unchanged; downgrade restores the prior key order.
- **17 PostgreSQL checks passed**: complete migration downgrade/upgrade, schema lint, all index
  condition checks and database-doctor checks, including a clean migrated catalogue. Ruff and
  whitespace checks pass. The earlier recorded FX-index finding is resolved; this establishes
  index-key eligibility under policy, not a full-volume performance result.
- Close-task and modification controls are merged; older dated evidence is archived below.
  Full-backend/specialist verification, other release gaps and independent accounting review
  remain open. No deployment.

## Originating-contract FX layers — October 7, 2026

- GitHub writes recovered. PR #6 merged into main (`5e74ea3`); its temporary branch was removed.
  The next slice connects the scoped policy input to the layer readers. No deployment.
- Liability layers retain the originating contract through ordinary credits and monetary releases.
  Consumption and period-end remeasurement resolve that contract's policy, even when another
  member's revenue consumes the layer through group FIFO. Encoded external identifiers are decoded
  after structural separators, preserving literal escape-like text.
- Mixed-member regressions cover either member's exception, ordinary/encoded identifiers, ASC606
  and IFRS15, and transaction/functional tie-outs. A later-period approval leaves the earlier
  historical period intact. The database regression uses real approval, computation and the real
  close FX pass: GBP 5,400 liability remeasurement is sealed once at the September closing rate;
  repeated passes and a recomputation add no duplicate. COMMAND correctly leaves TIME journals to
  the close pass. The test does not claim the whole close job or all gates were exercised.
- Actual verification: **571 FX, posting and architecture tests passed**, plus **4 PostgreSQL
  FX journal regressions**. Mypy passed for all three changed source files; Ruff lint/format and
  whitespace checks passed. These are targeted checks, not full-backend readiness evidence.
- Both excluded research directories remain absent from tracked files; root ignore rules now
  cover the whole directories, preventing accidental republication of more than just screenshots.
- Known transition defect reproduced locally: EUR 12,000 credited at 1.10 is carried at USD 13,440
  after a monetary January closing rate of 1.12. Returning to historical treatment and fully
  releasing in February recognizes USD 13,200, removes the open layer and leaves USD 240 of
  cumulative FX unreconciled. No accounting treatment has been invented for this transition.
  Public POL-163 creation remains disabled pending its correction, close invalidation checks,
  authoring validation and independent accounting review. C-2 remains partial.

Earlier October 7 policy-isolation and workbench evidence is archived verbatim in
[BUILD-HISTORY-2026-10-07.md](docs/release/BUILD-HISTORY-2026-10-07.md).

## Supported overrides in database answer keys — October 7, 2026

- Continued from merged PR #9 (`88bd20b`). The answer-key plan still omitted all policy
  overrides under the October 3 withdrawal, although POL-122 and POL-047 are now supported.
- Plans use the product's supported-key set, native request validation, committed override IDs,
  route permissions and separate preparer/approver personas. Each supported declaration is
  created, submitted and approved after booking and before activation. Unsupported declarations
  retain a named failure alongside numeric mismatches; in-memory runs cannot pass as database
  evidence. No answer-key files, expected figures or oracle hashes changed.
- Real PostgreSQL POS012 now creates both declared POL-122 rows and approval requests, verifies
  independent approval, compares every checkpoint clean and passes the complete key verdict.
  Existing close-job, posting, reversal and journal assertions remain intact.
- Verification: **379 tests passed** (the complete answer-key unit suite plus the PostgreSQL
  POS012 regression; two warnings), Ruff lint/format, whitespace and design checks passed.
  A standalone strict Mypy invocation of test-support files failed with 119 import/typing errors;
  it is not passing type-check evidence. This is targeted verification, not a full-backend run.
- C-12 remains open: default suite selection still uses memory, GT07's nondistinct review mapping
  is missing, and POS117 needs its balance-aging builder and fresh database verification.
  FX transition accounting review and the other documented repository backlog remain open.
  Repository work only; no deployment.

## Mandatory product disaggregation — October 7, 2026

- Continued from merged PR #26 (`ed6ea75`). The product usability warning is now enforced at
  booking/draft replacement, activation submission and approval, native modification additions,
  and legacy amendment application. Missing attributes name the product and required codes.
  Catalogue drafts remain editable. Bundle components follow the minimum inception of current
  group members, matching the calculation reference date rather than the group's retained old date.
- **108 database workflow tests passed, one existing parity-entry-point skip** across activation,
  native modification, products, bundles, legacy amendments and mixed amendment integration.
  **Five final database checks passed** after the reference-date refinement: booking/activation,
  native additions, legacy quarantine with rollback, dated bundle components and entity-scoped
  modification approval. No expected accounting amounts changed. CTL-028 tags cover the new
  activation and modification witnesses; B1-16 is closed in LIMITS.
- **267 architecture checks passed** during the change. The final focused run passed **194 tests**
  (147 unit checks plus 47 layer/import-cycle checks). Final source Mypy, Ruff, whitespace and
  design checks (500 files) pass. Initial test failures were fixture expectations/setup: error
  rule/status, a second contract's legitimate combination suggestion, legacy replay prerequisite,
  and the unmapped-product unit's newly required empty-setting/group-date context. They were
  corrected without weakening the existing controls.
- The broader backend run remains pinned to `ed6ea75` in a detached checkout and a dedicated
  loopback database, with passing tests and the existing expected Q11 failure. It is still live,
  not a completed gate, and does not cover this later change. Full-backend/specialist verification,
  other release limitations and independent accounting review remain open. No deployment.

## Backend baseline and supported override fixture — October 7, 2026

- Continued from main `3281f29`. The detached `ed6ea75` backend run finished with
  **2,959 passed, one failed, one expected Q11 failure and 640 deselected**, stopping at
  the first failure after 3,649.31 seconds. It excluded parity, answer-key and performance
  markers and did not cover PRs #27–29. This supersedes the earlier “still live” notes below;
  it is not a completed passing backend gate.
- The failed computation-cutoff case directly inserted an expected-returns override without
  a return estimate. Approved overrides now reach the engine, which correctly quarantined
  the fresh retry with `RETURN_ESTIMATE_MISSING`. The fixture now creates a supported
  POL-122 conditional-right override through the public API and obtains independent approval.
  It retains the stale-computation refusal and clean successful retry checks, and adds an
  unchanged-ledger assertion. No application behavior or accounting oracle was changed.
- **15 PostgreSQL computation-cutoff tests passed** in 76.47 seconds on the current source.
  Ruff lint/format with the repository configuration and whitespace checks pass. Secret scan:
  3,391 files, zero findings. This is scoped verification, not a green whole-backend gate.
- Repository settings enable automatic merge and deletion of merged branches. At the start
  of this slice, GitHub had only main and no open PRs. This slice used a temporary PR branch,
  merged into main and removed after review. The owner now requests direct main commits.
- Remaining work includes the broader backend/specialist verification, B1-10 identity-bound
  close-gate waivers, the other documented limitations and independent accounting sign-off.
  Archived the earlier originating-contract FX section verbatim to keep this file under 20 KB.

## Close-gate waiver identities — October 7, 2026

- Continued from main `e9cae63`. Reproduced B1-10 in pending and approved waivers: resolving
  one exception and introducing another at the same count let the replacement inherit review.
- Automatic gate results now retain sorted, typed member identities. Count and membership
  queries share their predicates; reconciliation identity, status and freshness are read together.
  Missing reconciliation kinds and a missing journal run have explicit identities. All ten
  waivable automatic gates carry a population; the four never-waivable gates remain protected.
- Approval refreshes the gates under the period/checklist locks and checks its own request's
  content hash. It refuses a changed population even without a cockpit visit. An approved
  waiver may cover a shrinking subset; additions or replacements lapse it at any count, and
  a spent waiver never revives. Legacy count-only waivers with blockers require a fresh review.
  This binds membership, not every mutable field of an existing member. B1-11 remains open.
- Submission audits retain the submitted population; lapse audits retain before/after identities.
  Same-count replacements and missing legacy scope have explicit lapse messages. A renewed
  approval removes the old lapse annotation. Existing historical lock records are unchanged.
  The existing JSONB result column is sufficient; no migration or financial-oracle change.
- **49 PostgreSQL close/lock checks passed** in 170.54 seconds, including all 11 waiver cases:
  lock-decision replacement, missing-to-unreviewed reconciliations, legacy scope, subset
  retention, renewal and reopen/audit behavior. Earlier runs also verified the fail-first cases.
- **678 close-unit and architecture checks passed**; a final focused rerun passed 37 checks.
  Updated the shared-predicate structural test and PR #29's FX unit principal fixture, which
  lacked the tenant ID required by the publication lock. Source Mypy, Ruff, whitespace and
  design checks (500 files) pass; 446 control tags validate; secret scan: 3,391 files, no findings.
- B1-10 is closed for automatic gate membership. Other limitations and accounting sign-off
  remain open. A backend run started on detached `7c9b22d` with a local database,
  excluding parity/answer-key/performance markers; no completed result yet. Exclusions and
  noncommercial licensing are preserved. Archived the earlier answer-key section verbatim.
  Repository only; no deployment.

## Error-correction reopen integration in progress — October 7, 2026

- Continued from main `b6bbedf`; the previous turn made progress by publishing the tested
  validation foundation. Current integration is **uncommitted on main** pending broader
  verification. No PR, deployment or production-readiness claim.
- Revision 0137 adds tenant-FK citations to period state and immutable reopen history;
  downgrade physically validates that no citation would be discarded, including outside
  the owner's tenant scope. Submission validates and binds reviewed evidence before opening
  the request. Final approval rechecks it under period/judgement locks; superseded evidence
  and legacy error requests without a citation become stale. Duplicate requests roll back
  their attempted citation replacement. Non-error requests refuse an irrelevant citation.
- The request hash includes the complete judgement and review identity. Its immutable audit
  retains the submitted evidence for authorized approval/history readers. The form selects a
  reviewed record using entity/book/topic/status filters and pagination; errors need that
  record before submission. Generated API types and snapshot-copy references are updated.
- **27 reopen workflow tests passed** in 77.05 seconds; **3 citation migration tests passed**
  in 17.05 seconds; **all 5 migration-walk checks passed** in 17.79 seconds. **60 frontend
  checks passed** in 3.31 seconds; TypeScript and ESLint pass. The broader unit/architecture
  run had 675 passes and 3 failures for missing column documentation/copy mapping; those
  fixes passed all 37 affected checks. Source Mypy and Ruff pass; design check: 501 files,
  no findings; secret scan: 3,396 files, no findings. Earlier API failures were missing fixture
  permissions/evidence and a refreshed MFA token discarded by the new test helper.
- A wider close/journal/API/judgement compatibility run is **live** on the primary test DB:
  session `10949`, PID `48598`, log `/private/tmp/reopen-citation-compatibility.log`.
  It has reported two setup errors; inspect terminal diagnostics before claiming a pass.
  Do not start another DB test there until it ends. The picker-filter case appended to
  `test_reopen.py` was added after collection and needs a separate run. Also finish scoped
  evidence/remaining fixture checks, update LIMITS only after verification, then push main.
- The independent baseline on `7c9b22d` remains live (PID 36126, separate DB, about 25%);
  it does not cover these edits. Follow `REOPEN-JUDGEMENT-CONTINUATION.md` for the remaining
  integration requirements. Archived the waiver-identity section verbatim to keep this file
  bounded. Other implementation gaps and independent accounting sign-off remain.

## Error-correction reopen evidence foundation — October 7, 2026

- Continued from main `4cdf8b7`. The preceding turn made progress: the B1-11 fix was tested
  and pushed directly to main. Revalidated the separate backend process as live; its pinned
  run is about 22% through, not a completed gate and not proof for later source changes.
- Investigated B1-12: the public reopen request has only reason/comment; its form submits
  the reopen before optionally authoring an unlinked judgement. A checked citation requires
  storage, approval-basis and form changes. The integration contract and remaining verification
  are recorded in `docs/release/REOPEN-JUDGEMENT-CONTINUATION.md`.
- Added `close.reopen_judgements.reviewed_basis`: validates tenant/entity/book, topic,
  REVIEWED status and independent review metadata, retaining the full accounting content and
  review identity for approval binding. A NOWAIT share lock avoids waiting in the reverse
  judgement/period order; its savepoint preserves the caller's transaction after conflict.
- **14 PostgreSQL evidence checks passed** in 25.44 seconds: valid book/all-book records,
  missing and out-of-scope records, wrong book/topic, unreviewed/superseded records and both
  lock orders. **47 layer/import checks passed** in 11.26 seconds. Source Mypy and Ruff
  lint/format pass. This foundation is not yet connected to the public command or form;
  B1-12 remains open. Do not describe it as enforcement or a completed control.
- Next: persist and hash the selected reviewed citation, revalidate at the final decision,
  retain it in immutable reopen history, update the form and run public workflow/migration
  tests. Other documented gaps and independent accounting sign-off remain. No deployment.
  Archived the earlier backend-baseline section verbatim; direct-main workflow retained.

## Error-correction reopen concurrency repair — October 7, 2026

- The prior workflow-only turn reconfirmed no open PRs and main as the sole branch; it did not
  advance implementation. Continued the uncommitted B1-12 integration on main `b6bbedf`.
- The compatibility run ended with **130 passes, one failure and two setup errors**. Storing
  the citation on the period row required an exclusive submission lock and broke the existing
  later-period close/reopen interleaving. Replaced that design with a tenant/entity-scoped
  `period_reopen_basis` table; submission keeps FOR SHARE and the original period row version.
  The per-period advisory lock serializes basis changes. Immutable submitted evidence remains
  in the request audit; the completed reopen lock retains its citation.
- Removed the redundant mid-domain-suite schema reset that invalidated cached PostgreSQL enum
  OIDs. The full migration suite already covers empty upgrade/downgrade/upgrade. Downgrade loss
  guards now inspect current basis and immutable lock citations, without bypassing RLS.
- Updated ORM exports, snapshot inventory, data-model API contract and the user guide. The
  first revised DB run finished with **57 passes and one test assertion failure**: after all
  scope for the request's entity was removed, the API correctly returned 404 rather than a
  redacted header. Corrected the expectation without changing access rules. Both close/reopen
  concurrency orders passed, including the formerly failing later-close-first interleaving.
- **742 unit/architecture/snapshot checks passed** in 166.98 seconds on the revised storage;
  schema/snapshot checks separately passed 71. Mypy: 5 source files clean. Ruff and diff checks
  pass; design scan: 501 files, no findings; secret scan: 3,396 files, no findings. Frontend:
  **62 tests passed**, TypeScript and ESLint passed (unchanged UI during storage repair).
- Broader primary-DB compatibility is live in session `1996`, PID `56657`, log
  `/private/tmp/reopen-citation-sidecar-compatibility.log`. It includes the corrected scope
  case, new public submitted/superseded refusals, approval API and close/journal compatibility.
  Wait for completion before another DB suite. Then run `backend/tests/pg/test_migrations.py`
  for the revised migration's full up/down/up; do not use the removed mid-domain schema reset.
- The independent baseline remains live, PID 36126, at about 28%; it has reported failures and
  must finish for diagnostics. It runs on `erev_rv_waivers` at `7c9b22d`, not this revised source.
  Do not restart it. Prior integration evidence was archived verbatim in BUILD-HISTORY.
- B1-12 remains open pending current migration/compatibility/static verification and publication.
  Other documented gaps and independent accounting sign-off remain. No deployment authorized.

## Reviewed evidence for error-correction reopens — October 7, 2026

- Continued from main `b6bbedf`; the preceding turn made progress by repairing the submission
  locking regression and verifying both decision orders. B1-12 is now implemented and verified
  for direct publication to main. No PR or deployment.
- ERROR_CORRECTION requires a reviewed ESTIMATE_VS_ERROR judgement from the same tenant/entity
  and applicable book. The request binds full content and independent review identity; final
  approval revalidates under period/judgement locks. Superseded evidence and legacy requests
  without citations become stale. Busy review locks are retryable. Other reasons refuse a citation.
- Revision 0137 stores the current basis separately, preserving the period's FOR SHARE request
  lock and row version. Duplicate submissions cannot replace pending evidence. Immutable request
  audit and reopen history retain the citation; downgrade refuses citation loss across tenants.
- The form selects reviewed evidence with entity/book/topic/status filters and pagination.
  Approvers and history readers see the submitted conclusion and reviewer within content scope.
  New requests cannot replace old evidence; loss of all entity access returns 404.
- **138 compatibility tests passed** in 419.60 seconds (`reopen-citation-sidecar-compatibility.log`).
  The earlier revised run passed 57 tests including both decision interleavings and the 14
  basis tests; its sole incorrect 200-vs-404 expectation was fixed and passed in the final run.
  **5 migration checks passed** in 16.31 seconds (`reopen-citation-sidecar-migration-walk.log`),
  including full up/down/up and database lint. **742 unit/architecture/snapshot checks passed**
  in 166.98 seconds. **62 frontend tests passed**; TypeScript, ESLint, Ruff and source Mypy pass.
  Design: 501 files, no findings. Secrets: 3,396 files, no findings. Logs are in `/private/tmp/`.
- Updated the data model/API contract, user guide, snapshot inventory, generated types and
  LIMITS. The noncommercial license and research-folder exclusions remain intact. See
  `docs/release/REOPEN-JUDGEMENT-CONTINUATION.md` for requirements and evidence.
- The independent full-backend baseline remains live on `7c9b22d`, PID 36126 / session 28842,
  separate DB `erev_rv_waivers`, roughly 29%, with reported failures. Preserve it and read terminal
  diagnostics when it finishes; it does not cover this change. No full-backend pass is asserted.
- Other documented implementation gaps and independent accounting sign-off remain. The next
  approval-control candidate is B1-15 (requests with no independent eligible decider); eligibility
  already exists in `approvals.engine._assigned_memberships`, but no queue/admin warning was found.

## Step 1 posting-date approval regression — October 7, 2026

- The preceding workflow-only turn verified no open PRs, only main, and automatic merged-branch
  deletion; it made no implementation progress. Revalidated the clean checkout at `5ca602f`
  and resumed B1-13 instead of repeating the status check.
- A new public-API regression reproduces the soft-close bypass: after a reviewed judgement,
  start-close succeeds, then the preparer's assessment batch advances the stream from 4 to 7
  and releases the hold. The open-period control passes. Initial run: **1 passed, 1 failed**
  in 17.70 seconds, `/private/tmp/step1-date-review-regression.log`.
  Final test rerun: **1 passed, 1 failed** in 19.76 seconds; Ruff and whitespace checks pass.
- The test and `docs/release/STEP1-DATE-APPROVAL-CONTINUATION.md` are local unfinished work.
  The test expects a pending submission and eventual independent approval; no product fix,
  skipped regression, commit or push has been made. B1-13 and broader B1-2 remain open.
  Existing stored-Step-1 bypass refusals must remain intact while the new lifecycle is built.
- Full-backend PID 36126 remains live on its independent older checkout/database, around
  33%, with earlier failures. Preserve it. No full-suite pass, deployment or readiness claim.

## Approval availability and access-admin alerts — October 7, 2026

- Previous goal turn made progress: B1-12 was tested and pushed directly to main as `ab4fa7d`.
  Continued from that clean commit. B1-15 is now implemented and verified for direct publication.
- Fail-first tests reproduced no alert when only the preparer held the approval permission and
  the absence of queue availability. Submission/next-step activation now emits APPROVAL_UNASSIGNED
  to active direct role.manage holders covering every entity. Its title/body contain no accounting
  summary or amounts. Revision 0138 adds the kind; preferences default to app/email with existing
  deduplication and sandbox restrictions. Preference input length follows the enum's actual size.
- API assignment_blocked is computed from current eligibility using the same logic as assigned
  recipients: preparer/prior-decision exclusions, delegation, subject rules and later-step
  reservations. It is separate from routing flags and clears after a valid grant is restored.
  Closed requests answer false; content-withheld headers and unsupported subjects answer null.
  Queue/detail display the warning; unsupported subject requests retain their named refusal.
- **43 backend compatibility tests passed** in 36.43 seconds (approval engine, notifications,
  approval API and preferences). **8 notification tests passed** in the final 5.55-second run, including
  entity-specific and all-entity admin scope and redacted alert content. Initial compatibility
  caught the unsupported-subject read and old 12-kind input cap; both were fixed and reverified.
- **79 frontend tests passed** in 3.04 seconds, including queue/detail visibility, preferences
  and notification panel. TypeScript and ESLint pass. **5 migration checks passed** in 16.22
  seconds (full up/down/up and lint). Unit/architecture run: 504 passes and one obsolete enum
  count assertion; corrected count and all 245 affected unit/schema checks passed in 4.08 seconds.
  Mypy: five source files clean. Logs: `/private/tmp/approval-availability-*.log`.
- Final approval API recheck: **20 passed** in 34.03 seconds. A caller who can decide already
  proves availability, so the queue avoids another recipient search for those rows. Alert titles
  include the request reference so the email (which omits the in-app body) can identify it.
- The extra scope test first tried changing a grant in place; PostgreSQL correctly refused it.
  The fixture now revokes the old grant and inserts the scoped replacement; product rules unchanged.
- Independent full-backend baseline remains live on `7c9b22d`, PID 36126 / session 28842, separate
  DB `erev_rv_waivers`, around 30%, with earlier failures. Preserve it until terminal diagnostics.
  It does not cover B1-11, B1-12 or this work. No full-backend pass or production-readiness claim.
- Remaining LIMITS and independent accounting sign-off are still open. Main-only workflow,
  research-folder exclusions, noncommercial license and no-deployment scope remain in force.

The sections above were archived verbatim during the ongoing Step 1 approval work on October 7, 2026.

## Approvals-gate waiver sequencing — October 7, 2026

- Continued on main `88de370`. Reproduced B1-11 with two failing decision-order cases;
  five controls already passed. A pending approvals-gate waiver now retains its submitted
  request identities while other requests complete. Final approval refreshes the gate under
  the existing locks and requires the live pending population to be a subset of that scope.
- New or replacement pending requests still void the waiver, including at the same count
  and without a cockpit refresh. Renewal reviews the new scope. If all requests complete,
  the gate passes and the unneeded waiver is voided. Other gates keep strict pending-basis
  checks. Rejection/voiding clears the temporary basis; approval retains reviewed coverage.
  Existing JSONB storage suffices; no migration or historical lock rewrite.
- **56 PostgreSQL close/lock checks passed** in 235.98 seconds, including all 18 waiver
  cases and seven new sequencing controls. **678 close-unit/architecture checks passed**
  in 171.83 seconds. Source Mypy, Ruff lint/format, whitespace and design checks pass;
  secret scan: 3,391 files, zero findings. B1-11 is closed for completed-request sequencing.
- GitHub has no open PRs and only main. Automatic merge and merged-branch deletion are
  enabled. Following the owner's instruction, this tested change goes directly to main.
- The separate backend run remains live on `7c9b22d` (about 20% through), excluding parity,
  answer-key and performance markers. It does not cover this change and is not a completed
  passing gate. Other limitations, specialist verification and accounting sign-off remain.
  Archived the mandatory-product section verbatim. Repository only; no deployment.

Archived verbatim on October 7, 2026 during the all-book Step 1 preview work.

## Estimate FX approval drift — October 7, 2026

- Continued from main `252c5d9`. Reproduced B1-7: EUR 46,000 was routed with one reviewer
  at USD 49,910 (1.085), then the same request approved after a rate of 1.09 made its impact
  USD 50,140. The unpublished-rate and unchanged-rate controls already passed.
- Final estimate approval now repeats its dry run and compares current functional amount,
  currency and threshold flags with the stored request before any version/event changes.
  Drift uses the existing stale-request rollback/void path: the version is WITHDRAWN and a
  fresh submission routes the Controller step. No accounting expectations were changed.
- A tenant-specific transaction gate prevents an FX publication between that check and posting.
  Estimate submission/final approval take its shared side before group/contract locks; FX
  publication takes its exclusive side before mutation and group/period hooks. It covers new
  rate sets as well. Current routing reads also include a committed publication whose application
  timestamp is later than the decision transaction's start. Historical bundle reads keep their
  time cutoffs. Automatic approval inside submission holds the gate too; a stale refusal there
  rolls back the submission. The final dry run adds work; no full-volume latency claim is made.
- **53 PostgreSQL workflow checks passed**: 51 across the complete estimate, FX-reference and
  rate-change-after-lock files, plus the linked J-06 modification journey and its K-03 report.
  Six new CTL-013 cases cover the threshold crossing, unpublished and unchanged controls, both
  ordering races observed waiting in PostgreSQL, and a publication overtaking an earlier-started
  decision. A refused request appends no estimate event; resubmission needs the Controller and
  applies once. The original J-06 monetary assertions remain intact.
- **273 architecture/routing-unit checks passed**. Four-source Mypy, Ruff lint/format, whitespace
  and design checks (500 files) pass. Control markers validate (440 tagged tests); secret scan:
  3,391 files, zero findings. B1-7 is closed in LIMITS, with the lock and API behavior documented.
- The broader backend run is still live on detached `ed6ea75` with its separate loopback database;
  it excludes specialist markers and does not cover these later changes. Full-backend/specialist
  verification, remaining limitations and independent accounting sign-off stay open. Publication
  exclusions and noncommercial licensing are preserved. No deployment.


Archived verbatim on October 7, 2026 during atomic Step 1 approval work.

## Step 1 review across books — October 7, 2026

- Previous goal turn made progress: 73 backend compatibility, six migration and 56 frontend
  checks passed. Continued the local unpublished implementation on main `5ca602f`.
- Retained previews now show revenue before/after by book, the computation time and primary
  book, and unaggregated posting lines across all output books/entities. Each line includes
  account, debit/credit, posting/origin period, subject and transaction/functional amounts.
  The primary-book summary alone no longer causes the Step 1 screen to claim no impact.
- Public-API one-book and two-book cases: **2 passed in 26.27 seconds**. Added assertions
  comparing the reviewed posting amounts with the ledger entries written by approval;
  that expanded matrix finished: **13 passed in 98.92 seconds**. Frontend: **58 passed
  in 4.37 seconds**, including
  distinct currency/entity display and avoiding a false no-impact claim. Source Mypy for two
  files, frontend TypeScript, ESLint, Ruff and whitespace checks pass. Design scan: 501 files,
  zero errors/warnings. Secret scan: 3,400 files, zero findings. Logs:
  `/private/tmp/step1-date-review-all-books-ledger.log` and
  `/private/tmp/step1-date-review-all-books-ui-final.log`.
- Actual performing-entity integration, API-client coverage, publication/computation races
  and deferred computation remain unverified. B1-13 and B1-2 remain open. The separate older
  full-backend PID 36126 is still live, with earlier failures; it has not been restarted.
  No publication, deployment or readiness claim. Older waiver evidence archived verbatim.

Archived verbatim on October 7, 2026 during draft-gate verification.

## Step 1 date approval implementation — October 7, 2026

- Previous goal turn made progress by reproducing B1-13 with a public-API regression.
  Continued on main `5ca602f`; all work in this section is local and unpublished.
- Added STEP1_EVENT and migration 0139, a dedicated event-submission lifecycle with
  independent event.approve authority and automatic approval disabled. Legacy generic
  submissions retain their Step 1/activation/void refusals. Pending submissions append
  nothing; approval revalidates the original events and derives the gate and hold releases.
  Applied event ids and approval references include the system hold-release effects.
- The live basis binds group heads/status, enabled books, judgement content/reviewer/status
  and period states. Book, judgement and period locks protect application. The later routing
  refinement checks batch/hold-release dates and all computed posting destinations rather
  than making an unrelated closing period require review. A review delayed into another
  local day is stale so its system release cannot silently use a different posting date.
- A stored preview now includes computed revenue/journal figures and readable assessment
  dates and cited conclusions. The drawer reports pending approval with its request number.
  Readers, evidence retention, enum catalogues and generated API/TypeScript types updated.
- Initial successful regression: **2 passed** in 18.88 seconds; **6 frontend tests passed**
  in 1.43 seconds. Broader run before the final routing/preview/day refinements: **64 passed,
  1 failed** in 304.33 seconds. Its period-change fixture omitted the cancel-close reason;
  corrected to CLOSE_RESTARTED. Final targeted rerun: **5 passed in 38.13 seconds**, including
  unrelated-close, changed-period and superseded-judgement cases, plus approval references
  and all applied event ids. Log: `/private/tmp/step1-date-review-final-targeted.log`.
- Latest source type checks passed for four files; frontend TypeScript, Ruff and whitespace
  checks passed. These are scoped checks, not completion evidence for B1-13.
- Migration run: **4 passed** in 16.98 seconds, including full up/down/up and database lint;
  its only failure was the old 0138 head assertion. Updated to 0139; head recheck **1 passed
  in 0.15 seconds**. No migration error remains from that run.
- Further local verification: **8 passed in 51.23 seconds**, including reopened and
  reopened-then-closing periods. A published SSP catalogue change reproduced approval
  drift; the retained preview now stores provenance and a calculation-input fingerprint,
  which is checked before application. Synthetic pending-event timestamps are normalized
  only for that comparison; the original engine input hash is retained.
- **4 timing/lock cases passed in 34.72 seconds**: same-day delay, next-day staleness,
  busy submission and busy approval. Performing-entity periods now join the locked basis.
  Migration 0139 also updates the approvals-register subject filter; this latest migration
  change passed its fresh round trip. Expanded compatibility: **73 passed in 349.91
  seconds**. Migration suite: **6 passed in 21.78 seconds**, including stored report-filter
  equality with the runtime enum before/after downgrade and upgrade, and restored trigger.
  Approval-detail plus assessment-drawer frontend suites: **56 passed in 3.15 seconds**.
  Logs: `/private/tmp/step1-date-review-expanded-compatibility.log`,
  `/private/tmp/step1-date-review-report-migrations.log` and
  `/private/tmp/step1-date-review-approval-ui.log`.
- Rechecked GitHub: no open PRs, only main; automatic merging and merged-branch deletion
  are enabled. Continue tested direct pushes to main. No deployment.
- Next: finish all-book/entity preview and API-client coverage, configuration publication
  races and deferred-computation guarantees, report-filter/snapshot/migration compatibility,
  final lint/design/secrets checks, then publish verified changes directly to main.
  B1-13 and B1-2 remain open; independent accounting sign-off is still outstanding.
- Full-backend PID 36126 remains live on its separate older checkout/database, around 33%,
  with earlier failures. Preserve it. No deployment or production-readiness claim.



Archived verbatim on October 7, 2026 during performing-entity verification.

## Performing-entity FX verification — October 7, 2026

- Previous goal turn made progress: three real cross-entity cases passed. Extended the case
  to USD transaction amounts and a GBP-functional performer, with published spot, average
  and closing rates. Both currencies' actual ledger amounts are compared with the review.
- **2 passed in 25.67 seconds**: unchanged rates apply exactly the reviewed transaction and
  functional amounts; publishing a changed average rate makes the pending assessment stale.
  Log: `/private/tmp/step1-date-review-performing-fx.log`.
- Simultaneous FX publication: **1 passed in 17.48 seconds**. PostgreSQL confirmed that the
  publication waits on the decision's backend; after the decision posts its reviewed amounts,
  publication completes. Log: `/private/tmp/step1-date-review-performing-fx-interleave.log`.
  Two earlier probes failed only query matching: the table name lay beyond truncated SQL,
  then the helper required a lowercase prefix. Matching the visible reach CTE retains exact
  publisher/holder identity. All scoped runs are terminal; erev_rv_cont is available. Source
  changes were unnecessary; Ruff and whitespace checks pass. Older baseline PID 36126 is
  still live on its separate DB, with prior failures; preserve it.
- Physical large-group verification and final publication checks remain. This does not close
  B1-2's other producers or establish independent accounting sign-off. All Step 1 work remains
  local/unpublished; no deployment or production-readiness claim.

## Step 1 publication checks — October 7, 2026

- Previous goal turn verified zero open PRs and only main remotely. Direct-main workflow
  remains in effect; the verified Step 1 implementation is included in this direct-main commit.
- Physical 201-obligation case passed (1 in 18.73 seconds), without lowering the obligation
  budget: `/private/tmp/step1-date-review-201-obligations.log`. This proves the functional
  approval path, not a production latency or load guarantee.
- Repository-wide `make lint` passed, including design, licence, secrets, OpenAPI drift and
  migration-head checks: `/private/tmp/step1-date-review-release-lint-complete.log`.
  Two existing formatting failures were corrected in the import-job and AboutDialog tests.
- Event/evidence compatibility: 36 passed, one old subject-list assertion failed. Updated it
  to retain STEP1_EVENT evidence. Evidence-registry plus snapshot-export recheck: 25 passed,
  one genuine pre-existing monetary-comparison gap remains (1.69 seconds). New Step 1
  subject-reference checks passed. Log: `/private/tmp/step1-date-review-evidence-snapshot-final.log`.
- Do not remove that failing drift guard: stored loss_provision_version and fx_layer_movement
  remain absent from snapshot_export.MONETARY_TABLES and sandboxes._monetary_rows. They are
  regenerated on load but omitted from monetary verification. Implement a state comparison
  that handles cumulative state versus incremental movements, with real sandbox coverage.
- Full Step 1/registry/data-model/preparer/evidence compatibility passed: **93 in 486.28
  seconds**, `/private/tmp/step1-date-review-final-compatibility.log`. Source Mypy passes
  all six changed backend modules. Terminal-decision/mixed-batch regression: **1 passed in
  16.56 seconds**, `/private/tmp/step1-date-review-terminal-decisions.log`: reject/withdraw
  change no accounting state; resubmission applies once and repeat approval is refused. All
  current scoped runs are terminal; erev_rv_cont is free. Older baseline PID 36126 was verified live at 3h00m54s
  on its separate DB with failures; preserve it.
- B1-13 remaining scope/evidence/snapshot coverage, broader B1-2 producers, full-suite failures and
  independent accounting sign-off remain open. No deployment or production-readiness claim.

## Performing-entity Step 1 review — October 7, 2026

- Previous goal turn made progress with draft-gate review and 5 backend/59 frontend checks.
  Continued local unpublished work on main `5ca602f`; added real cross-entity API verification.
- AVM-US contracts the subscription; AVM-OPS performs it in USD. With both periods open,
  the assessment applies immediately. With only AVM-OPS in soft close, it waits for approval
  while the owner's period remains open. Locking AVM-OPS's period produces a retryable
  conflict without changing the stream, ledger or hold; retry applies reviewed postings.
  The ledger comparison retains entity, book, account role and debit/credit, and equals the
  retained preview amounts. **2 passed in 22.88 seconds**:
  `/private/tmp/step1-date-review-performing-entity.log`.
- Performing-period-change case: **1 passed in 17.33 seconds**. Canceling the performer's
  close after submission makes approval stale and leaves the stream, ledger and hold unchanged.
  Log: `/private/tmp/step1-date-review-performing-period-change.log`; primary DB erev_rv_cont
  is available. Approval authority continues to use contracting/group entities as accepted
  subject-scope rules require; this work checks posting windows for performers.
- Source changes were unnecessary for the first two cases. Ruff and whitespace checks pass.
  FX/other configuration races, physical large-group performance and final publication checks
  remain open. B1-13/B1-2 and independent accounting sign-off remain open. No deployment,
  publication or readiness claim. Earlier Step 1 implementation evidence archived verbatim.


## Draft Step 1 gate review — October 7, 2026

- Previous goal turn made progress with 77 compatibility checks, API-client verification and
  both SSP publication interleavings. Continued unpublished changes on main `5ca602f`.
- Added before/after contract status to the retained Step 1 preview and readable contract
  status labels to the approval screen. A draft's proposed gate is now visible, including
  Draft remaining unchanged when the existing obligation-budget gate guard withholds it.
- Two new public-API cases cover a derived draft gate and its size-budget boundary. Initial
  tests reproduced missing preview status. Subsequent assertions exposed fixture assumptions:
  draft judgements create no active-contract hold, and counting every job includes unrelated
  jobs. Corrected the expected event list and scoped the no-deferral assertion to CONTRACT_COMPUTE.
- Frontend: **59 passed in 2.92 seconds**; source Mypy, TypeScript, ESLint, Ruff and whitespace
  checks pass. Backend compatibility: **5 passed in 39.64 seconds**, covering draft outcomes,
  two-book/API-client decisions and existing immediate-append budget behavior. Log:
  `/private/tmp/step1-date-review-draft-gate-compatibility.log`. Primary test DB erev_rv_cont
  is free. Lowering the budget exercises the boundary, not real-volume performance.
- Actual performing-entity behavior, FX/configuration interleavings and physical large-group
  performance remain open, along with B1-2's other producers and accounting sign-off. No
  publication/deployment/readiness claim. Earlier preview notes archived verbatim.

## Atomic Step 1 computation — October 7, 2026

- Previous goal turn made progress: all-book previews and 13 backend/58 frontend checks.
  This turn reproduced deferred approval: with the fact-capture obligation budget forced
  below the group size, the request approved while its book still had the old ACTIVE state.
  Regression: **1 failed in 14.28 seconds** (`step1-date-review-deferred-regression.log`).
- STEP1_EVENT now computes successfully inside the approval transaction, without the ordinary
  fact-capture deferral budget. It compares the actual persisted-event input bundle with the
  previously validated proposal before running the engine. Only SYSTEM append attribution,
  recorded time and assigned record sequence are normalized for this comparison; actual event
  order and accounting inputs remain checked. The unmodified actual bundle is computed and
  persisted with its normal hash. Other event approvals retain their existing computation path.
- Failed calculation rolls back approval, events and hold releases; changed inputs use stale
  approval handling. The single-book, two-book and forced-deferral cases passed: **3 in 30.37
  seconds**. Failure/late-input boundary checks passed: **2 in 23.63 seconds**, including a
  successful retry after engine failure and unchanged computation count on refusals. Their
  first run only failed the fixture expectation of null instead of an empty applied-id array.
  The late-input test injects an engine-version change; it is not real publication-race proof.
- Source Mypy (two files), Ruff and whitespace checks pass. Expanded compatibility finished:
  **77 passed in 374.20 seconds**, `/private/tmp/step1-date-review-atomic-compatibility.log`.
  API-client case passed: automated submissions still wait for date approval and retain
  non-manual attribution. Both real SSP-publication interleavings passed in **23.96 seconds**:
  before the final input read the decision is stale; after it, actual postings match the reviewed
  amounts. Initial publication probes stopped at the fixture's old session after MFA enrolment;
  using the preparer's current enrolled session fixed the fixture. Logs:
  `/private/tmp/step1-date-review-publication-client.log` (one pass, two fixture failures) and
  `/private/tmp/step1-date-review-publication-interleavings.log` (two passes). All scoped runs
  are terminal; primary test DB erev_rv_cont is available. The older baseline PID 36126 remains
  live on its separate DB with earlier failures. Updated the data-model contract for decisions.
- Remaining: FX and other configuration interleavings, actual performing-entity coverage,
  draft-gate and large-group decision verification, final compatibility and publication checks.
  Synchronous decisions can take longer; no performance claim. B1-13/B1-2 remain open, all
  changes unpublished. No deployment or production-readiness claim. FX evidence archived.

## Sandbox monetary verification — October 7, 2026

- Previous goal turn published Step 1 approval as a40d848 directly to main. This continuation
  resolves the category-M drift guard's missing loss-provision and FX-movement comparisons.
- Both tables contain full reconstructed results per computation version: period loss tests
  and FX movement history. Compare their monetary fields and pinned inputs, excluding only
  surrogate/version ownership, stamps and trace. FX natural-key duplicates are compared as a
  sorted multiset with occurrence numbers; missing rows and offsetting errors remain visible.
  The database reader now follows MONETARY_TABLES, retaining special version/schedule reads.
- Unit tests: 30 passed in 1.46 seconds. Whole Avenmoor reference-tenant snapshot export/load:
  1 passed in 48.59 seconds, twelve groups and multiple currencies. Existing repeated-computation
  control passed. Logs: `/private/tmp/sandbox-monetary-loss-fx-{unit,avenmoor,replay}.log`.
- Added real snapshot negative controls: one-cent changes to persisted loss movements or FX
  movements are named monetary mismatches; unchanged K03 period loss rows compare equally.
  Nine integration/audit-support checks passed in 40.11 seconds. Updated the audit helper's
  explicit creation-action set for existing FX/loss facts. Earlier failures were the stale
  audit set and parameter cases sharing globally unique sandbox names; distinct names fix
  the combined run. An initial diagnostic assumption about an amount constraint was not
  established by evidence; the captured validation error identifies the duplicate name.
- Final dynamic-reader recheck: **39 passed in 41.58 seconds**, with unit/export, audit
  support, positive loss and negative loss/FX controls; log
  `/private/tmp/sandbox-monetary-loss-fx-final.log`. All scoped processes are terminal and
  erev_rv_cont is free. Two source modules pass Mypy; Ruff/format/whitespace checks pass.
  This verified correction is included in this direct-main commit.
- Independent older baseline PID 36126 remained live at 3h10m33s on its separate DB, with
  failures; preserve it. Broader backend failures, Step 1 scope/evidence verification, other
  release limitations and independent accounting sign-off remain open. No deployment.

## Integration owner notifications — October 7, 2026

- Migration 0140 adds a nullable tenant-bound connection owner. API creation defaults to an
  eligible creator; explicit null remains unassigned. Owner or entity changes validate active
  membership and integration.manage plus contract.read over every served entity. Empty entity
  scope requires both permissions for all entities. Historical connections remain unassigned.
- A control-total mismatch assigns its new blocking OPEN exception and notifies the eligible
  owner transactionally. Recipient authority is rechecked at delivery; repeated handling of
  the same exception does not invoke notification again. Existing notification preferences
  govern email. No external messages were sent by this work.
- Connection editor supports assigning/clearing an owner, retains unchanged ownership on edits,
  and warns about missing owners. Browsing other members retains user.manage protection;
  self-assignment remains available and server-validated. OpenAPI/types and T-INT-01 updated.
- Six migration checks previously passed. Backend API/reconciliation suite: **20 passed in
  39.92 seconds** (/private/tmp/integration-owner-suite-final.log). Additional scope/downgrade
  and owner security checks: **7 passed in 21.05 seconds**
  (/private/tmp/integration-owner-scope-migration.log). Expansion beyond a scoped owner's
  authority is refused atomically, while replacing the owner permits expansion. A nonempty
  downgrade without tenant context refuses to discard the assignment, and rollback preserves it.
- Negative notification cases cover unassigned, suspended and revoked owners; retry coverage
  counts actual delivery calls independently of the generic ten-minute notification merge.
  Initial revoked fixture used nonexistent status rather than revoked_at; corrected. An existing
  outage test falsely matched "503" in a generated UUID; exact safe-message and whole-response
  secret assertions remain, while the invalid substring test was removed.
- Connection UI: **27 passed** (/private/tmp/integration-owner-ui-tests-final.log), including
  self-assignment and existing editing flows. Initial test used click on the component's
  mousedown-driven options; corrected to exercise its actual selection event. Final TypeScript
  and full make lint pass; whitespace checks pass. All scoped processes are terminal. This
  verified increment is published directly to main, without a PR.
- B1-19 remains open for missing/ineligible-owner fallback and import amount reconciliation.
  Existing owners who later lose authority receive nothing; the exception queue remains the
  documented recovery path. No production readiness claim or deployment. Independent accounting
  sign-off remains outstanding. The older backend baseline PID 36126 was live at 3h41m12s on its
  separate database, with failures; preserve it until terminal. Dated sections moved verbatim to
  docs/release/BUILD-HISTORY-2026-10-07.md to keep this notebook below 20 KB.

## Step 1 lifecycle verification complete — October 7, 2026

- Previous goal turn published sandbox loss/FX comparison as dbb3e57. This continuation closes
  B1-13's remaining listed lifecycle/snapshot coverage; implementation is already on main
  in a40d848. The wider B1-2 remains open.
- New public-API cases: enabling another book or independently applying a later assessment
  makes the earlier request stale/VOIDED with no applied event ids or additional accounting
  changes. Revoking a reviewer's role refuses a decision sent from the previously loaded page;
  the request stays pending and another eligible independent reviewer can apply it.
- Real export/load round trip retains the approved STEP1_EVENT request, identical readable
  impact preview, evidence attached to the request and all three resulting events, and exact
  decrypted attachment bytes. The loaded accounting computation verifies with zero mismatches.
- Initial basis run: two passed; the revoked-reviewer case then found the replacement reviewer
  lacked its required role. Corrected that fixture; authority recheck passed in 17.16 seconds.
  Evidence round trip passed in 18.86 seconds. Final combined checks: **7 passed in 64.90
  seconds**, including API-client, two-book and terminal-decision compatibility. Log:
  `/private/tmp/step1-date-review-scope-evidence-final.log`. Ruff, formatting and whitespace
  checks pass. All scoped runs are terminal and erev_rv_cont is free. This direct-main commit
  publishes verification and documentation; no product code changed in this continuation.
- Existing reopened-period coverage uses valid database state fixtures, not a fresh complete
  certification/reopen workflow. Neither scoped tests nor B1-13 closure establish full-system
  production readiness. Independent accounting sign-off and other release gaps remain open.
  Older baseline PID 36126 was live at 3h20m33s, beyond 50% with failures, on its separate DB.
  Preserve it. No deployment.

## Combined-group reporting verification — October 7, 2026

- Continued from 2ca9791. Reproduced a combined-group monitor failure on current main
  (one failed in 17.02 seconds). The expectations predated individual persisted FX layers.
  T-CON-18 identifies each billing event, while the former test expected a synthetic contract
  net balance. Group FIFO consumes both September recognitions from the first invoice's layer.
- Corrected monitor expectations using fixture events and the independently stated arithmetic:
  36,000 - 3,202.55 - 3,205.48 = 29,591.97; the other invoice's 48,000 stays untouched.
  Existing contract-level report balances, revenue assertions and duplicate-version checks
  remain. Partially recomputed membership cases check each member's actual current layer.
- Complete module: **17 passed in 89.20 seconds**; Ruff/format/whitespace checks pass.
  Evidence and rationale: docs/release/BACKEND-BASELINE-2026-10-07.md. Seven old baseline
  failures resolved as stale expectations; the other 44 await evidence-based disposition.
  No product/calculation code changed. Published directly to main; no deployment. Broader
  verification, import monetary reconciliation and independent accounting sign-off remain open.

## Reconciliation timing and publication checks — October 7, 2026

- Continued from c8fea89. Reproduced the reconciliation interleaving failure on current main
  (one failed in 10.98 seconds). An explicit precondition then proved the fixture's application
  clock was 0.163 seconds ahead of the database clock. The shared helper starts one second
  ahead; this scenario required setup to take longer than that, making its ordering accidental.
- The timing test now sets its clock from the database immediately before generation, asserts
  it is not ahead, and checks the injected billing event's persisted recorded_at against the
  generated reconciliation's as_of_known_at. Production snapshot logic is unchanged.
- All eight reconciliation timing cases passed in 47.59 seconds before the additional persisted
  timestamp assertion. Final combined verification with the assertion and publication tests:
  **18 passed in 44.02 seconds**, /private/tmp/reconciliation-and-publication-final.log.
- Two publication tests still required MIT despite the owner's noncommercial publication.
  Updated them to assert PolyForm Noncommercial 1.0.0, its noncommercial-purpose section and
  the required copyright notice; existing third-party notice checks remain. No license terms
  changed. Ruff/format/whitespace checks pass; all scoped runs are terminal. Published directly
  to main. Three more baseline failures resolved; 41 remain to be classified. No deployment
  or accounting sign-off. Broader current-main verification remains outstanding.

## File-shred durability test isolation — October 7, 2026

- Continued from 1abb52b. The older baseline's three shred failures counted unrelated tenants'
  pending files: observed completed counts 9 versus 1 and 3 versus 0, and failed counts 3 versus 1.
  Current unmodified durability module in isolation: **6 passed in 70.22 seconds**,
  /private/tmp/shred-order-current.log.
- committed_db retains other tests' tenants. Import source-shred tests deliberately mark rows
  incomplete, and the production sweep correctly scans all tenants. Durability assertions
  intended for one world were incorrectly applied to that global workload.
- Scoped this module's sweep workset to its own fresh tenant, retaining the real original
  eligibility predicate and all storage, completion, transaction, retry and alert paths.
  Production code is unchanged. Initial mixed run: 11 passed, one sandbox sweep-count failure
  (3 completions versus 1) from the same unrelated pending imports. The sandbox case now scopes
  the workset to BOTH its production and sandbox tenants through a shared test helper; its
  source-key, archived-workspace and completion assertions remain intact.
- Final combined import-source, durability and sandbox-shred verification: **12 passed in
  82.01 seconds**, /private/tmp/shred-cross-suite-verified.log. Ruff/format/whitespace checks
  pass; all scoped runs are terminal. Published directly to main. Three baseline failures
  resolved plus the newly exposed sandbox count issue; 38 original failures still await
  disposition. No deployment or readiness claim; accounting sign-off remains outstanding.

## Audit summary types and snapshot revalidation — October 7, 2026

- Continued from d90781b. The audit log's closed object-type catalogue omitted
  fx_layer_movement, loss_provision_version and loss_provision_eac. Computation writes these
  through record_facts as aggregate summaries: null object_id, with row IDs or bounded
  count/hash evidence in detail. Added the types to the explicit NO_LABEL set and documented
  this convention. No financial amounts or audit events are changed.
- Audit read unit/API tests and the two older failing sandbox replay cases: **21 passed in
  26.44 seconds**, /private/tmp/audit-labels-and-replay.log. The replay cases already benefit
  from dbb3e57's audit support additions and now have current-main evidence. Ruff/format and
  whitespace checks pass; the run is terminal. Published directly to main, no deployment.
- Three more original baseline failures resolved; 35 remain to be classified. Inspection also
  confirms the audit route catalogue still describes policy override creation as wholly
  refused, although two keys are supported. Its refusal fixture uses a still-unsupported key;
  the successful creation path needs its own audit-walk coverage, not removal of refusal proof.
  This remains open. Broader verification and independent accounting sign-off remain open.

## Supported policy-override audit coverage — October 7, 2026

- Continued from 778ce38. The route catalogue still classified all policy override creation
  as refused, even though balance.right_to_consideration and sfc.discount_rate_basis are supported.
  Changed the route to require policy_override.create audit evidence, and added that action
  to the configuration/policy category. Unsupported-key refusal is now a separate case and
  cannot count as evidence of the successful route.
- The database walk creates a real supported obligation override. Retained unsupported-key
  checks require the exact refusal, no request audit event and unchanged row counts in the
  request tenant. Their negative controls still catch a write beside the refusal or success
  returned instead. The catalogue unit test now checks both paths.
- Scoped catalogue/walk verification: **17 passed, 3 deselected in 23.49 seconds**,
  /private/tmp/policy-audit-catalogue.log. Full CTL-038 command-route walk: **1 passed in
  32.75 seconds**, /private/tmp/policy-audit-full-route-walk.log. Ruff/format/whitespace checks
  pass; all runs are terminal. No production code changed. Published directly to main.
  One more original baseline failure resolved; 34 remain without current-main disposition.
- REQ-PLT-019's pending AI lifecycle category remains open and is not waived. Wider baseline
  triage and accounting sign-off remain outstanding. No deployment or production claim.

## Estimate lock and SMTP guard verification — October 7, 2026

- Continued from ef323e6. Reproduced three older baseline failures on current main:
  two estimate-approval stand-ins crashed on the newer shared FX publication lock;
  one SMTP test expected the original spelling of a normalized IPv4-mapped IPv6 literal.
  Initial run: **3 failed, 117 passed in 2.53 seconds**, /private/tmp/lock-ssrf-before.log.
- The lock stand-in now recognizes only the expected shared advisory call, verifies its
  tenant namespace/hash seed, and records it before group/contract locks. Both approval
  assertions require this complete order, including at basis revalidation. Literal SMTP
  addresses use canonical spelling; resolver outputs retain their original checked spelling.
  All private-opt-in and blocked-destination checks remain. Production code is unchanged.
- Final verification: **120 passed in 2.25 seconds**, /private/tmp/lock-ssrf-verified.log.
  A separate process bypassed only hold_fx_publication: both approval cases failed their
  order assertions as required (/private/tmp/estimate-gate-negative.log). An intermediate
  run exposed the resolver/literal spelling distinction; the final assertions cover both.
  Ruff, format and whitespace checks pass; all runs terminal. Three baseline failures
  resolved, leaving 31 without current-main disposition. These are scoped unit checks,
  not a new full-backend baseline. Accounting sign-off remains open; no deployment.

## Import row coverage — October 7, 2026

- Continued from published a194ef2. Review of B1-19 found a separate equal-count hole: an
  emitter could return one source row twice and omit another while the commit counted every
  response. New regression reproduced COMMITTED on that invalid lineage before the fix
  (/private/tmp/import-duplicate-lineage-before.log).
- Import commit now rejects unknown or repeated source row identities before recording lineage.
  The failure uses CONTROL_TOTALS_MISMATCH and rolls back target/source records and lineage.
  Existing final row-count accounting continues to include quarantined rows.
- Complete import commit module: **11 passed in 34.04 seconds**,
  /private/tmp/import-row-coverage.log. Mypy for commit.py, Ruff formatting/checks and whitespace
  checks pass. Final duplicate/unknown-row negative cases: **2 passed in 9.32 seconds**,
  /private/tmp/import-row-coverage-negative.log. Both runs are terminal. Published directly
  to main after verification.
- This fixes row coverage, not loaded monetary amounts. B1-19 remains open: actual target
  amounts need template-aware reconciliation, including repeated header amounts and quarantine.
  No production claim, deployment or new PR. The independent older baseline was live at
  3h45m12s (94 percent) with failures on its separate database; preserve it until terminal.

## Portable backup archives — October 7, 2026

- Continued from f9f5683. Reproduced the restore baseline failure: macOS BSD tar adds
  an AppleDouble ._files entry outside the declared files/ root, so restore correctly
  refuses the backup before reaching subsequent checks. The new archive regression
  adds explicit macOS extended attributes and failed against the old script with that
  exact refusal (/private/tmp/backup-archive-regression.log, 1 failed in 1.15 seconds).
- Backup tar creation now sets COPYFILE_DISABLE=1 for that command, suppressing host
  AppleDouble metadata. Restore validation is unchanged. The regression checks exact
  archive members, preserved ciphertext bytes and acceptance by the real archive validator;
  partial uploads remain excluded. The runbook documents the archive contents.
- Complete backup/restore script module: **29 passed in 77.31 seconds**,
  /private/tmp/backup-restore-verified.log. Recovery preflight module: **25 passed in
  0.11 seconds**, /private/tmp/recovery-preflight-verified.log. Bash syntax, Ruff/format
  and whitespace checks pass; all processes are terminal. These scratch-repository runs
  stub database/verification commands; they do not prove a live backup or restore drill.
- All 14 original backup/restore baseline failures are resolved, leaving 17 original
  failures without current-main disposition. Broader verification, implementation gaps
  and independent accounting sign-off remain open. No deployment or cloud changes.

## Migration verification alignment — October 7, 2026

- Continued from 9622f13. Scoped current-main run reproduced two migration-check failures
  (2 failed, 42 passed in 1.56 seconds, /private/tmp/migration-pins-before.log). The task
  signature downgrade test omitted fresh_head; revision 0130's historical transition body
  was incorrectly compared with the current renderer, which includes 0135's reopen pair.
- The downgrade case now starts with a data-free head before creating its own signature
  history. Updated the static walk inventory for this case and the existing Step 1 report
  filter round-trip (the latter already resets correctly). No guard exemption was added.
  Revision 0130 is checked against 0135's literal previous body; the new 0135 check requires
  today's renderer and exactly one added PASSED>NOT_STARTED pair. No migration was rewritten.
- Final verification: **47 passed in 12.62 seconds**, /private/tmp/migration-pins-final.log.
  Includes the real PostgreSQL lossy-downgrade refusal with signature retention and RLS
  restoration, installed transition-function drift check, complete migration-entry/transition
  unit modules and snapshot-export module. The snapshot baseline failure was already fixed
  by dbb3e57 and now has fresh verification. An intermediate run found the missing Step 1
  inventory entry; the final run includes that correction. Ruff/format/whitespace pass.
- Three more original baseline failures resolved, leaving 14 without current-main disposition.
  All runs terminal. This is scoped evidence, not a full migration walk or backend baseline.
  Implementation gaps and independent accounting sign-off remain open. No deployment.

## Container probe fixture and release-check visibility — October 7, 2026

- Continued from d44d5c5. Reproduced the container probe and progress-list failures:
  **2 failed in 0.16 seconds**, /private/tmp/release-probes-before.log. On this host,
  files under the scratch root inherit group 0 while the process uses group 20; macOS
  silently removes setgid on chmod. A local probe confirmed mode 0755 before changing
  to the caller's group and 02755 afterward.
- The fixture now assigns its setgid file/directory the caller's group and explicitly
  asserts all privileged mode bits before running the unchanged container probe. The
  probe must still report both privileged files and exclude directories and symlinks.
  Restored the outstanding supervisor-target list below, with historical results kept
  dated and current release-candidate evidence still required.
- Full container-script module plus progress-list check: **20 passed in 15.36 seconds**,
  /private/tmp/release-probes-verified.log. Ruff/format and whitespace checks pass.
  These use Docker stand-ins; no images were built, deployed or certified by this run.
- Two original baseline failures resolved; 12 remain without current-main disposition.
  The seven-case tooling rerun started here completed in the continuation below;
  session 71400 is terminal. Its results supersede this entry's pending status.
  Accounting sign-off and implementation gaps remain open. No deployment.

## Constraint review basis — October 7, 2026

- Continued from main `72aaa2b`. Reproduced both B1-5 paths: a changed version accepted an
  earlier version's reviewed constraint, and a draft accepted figures edited after review.
  The two new API regressions failed against the prior implementation with HTTP 200 submissions.
- Constraint judgement content now includes the specific estimate version and financial inputs.
  Its existing submitted hash seals that basis; the submission audit retains the figures.
  Estimate submission and approval verify the binding. Editing figures during a pending review
  makes that review stale. No-change attestations retain their existing path; no posted history
  is rewritten. Older unbound pending requests need a fresh review and resubmission.
- The drawer offers a replacement conclusion after the API refuses an outdated review, even
  while the old record remains REVIEWED. API copy and the data-model contract describe the new
  requirement. B1-5 is closed for estimate-version submission/approval; other limitations remain.
- **55 distinct database workflow checks verified across scoped runs**: 26 estimate tests,
  19 judgement tests, two amendment integration tests and eight judgement/estimate/loss report
  tests. Five new CTL-049 cases cover both reuse paths, pending edits with version/contract
  subjects, recorded basis figures, and refusal of an old-release pending request without
  changing its history. Fresh independent reviews restore the ordinary approval path.
- The K-03 report fixture previously reviewed the constraint before creating its target version.
  It now creates the draft first, then reviews and links the record. All original accounting
  expectations are retained. An intermediate rerun also caught a missing fixture import; the
  final eight-report rerun passed. This is scoped evidence, not a green whole-backend gate.
- Architecture verification found PR #27's missing declaration for the authorized, same-tenant
  `product_reference_date` scope entry. Added its explicit reason and developer-guide contract;
  all six scope checks passed. The broader rerun passed **274 architecture/unit checks** and
  caught the changed error copy's stale PRD row; after synchronizing it, that check passed too
  (**267 architecture plus eight focused unit checks verified across these runs**).
- **61 frontend drawer/form tests passed**, including recovery from a refused reviewed record.
  TypeScript, ESLint, Vite build (existing chunk-size warning), source Mypy, Ruff, whitespace and
  design checks (500 files) pass. Control markers validate (434 tagged tests). Secret scan:
  3,391 files, zero findings. Publication exclusions and noncommercial licensing are preserved.
- The broader backend verification remains live in the detached `ed6ea75` checkout and its own
  loopback database. It excludes specialist markers and does not cover these later changes.
  Full-backend/specialist verification, other release gaps and independent accounting sign-off
  remain open. No deployment or external accounting contact.

## Waiver and modification-audit verification — October 7, 2026

- Continued from cc31480. Both remaining close-waiver/audit-report cases reproduced
  (/private/tmp/waiver-audit-before.log). The synthetic waiver request had a placeholder
  content hash; the report expected the trail from before preparer answer confirmation.
- The waiver fixture now binds the real subject content before using the approved hook.
  It checks the stored WAIVED state directly, then verifies gate evaluation invalidates
  the unbound waiver and refuses the lock while re-marking is pending. Newly dirty members
  remain blocking after the job succeeds; recomputing those groups clears the gate.
  An intermediate run confirmed read-time invalidation; no freshness check is bypassed.
- The audit report's exact expected action list now includes the proposal read, preparer's
  saved questionnaire and classification of those saved answers. Full list/export equality,
  outcome filters, field-level diffs and accounting fixture expectations remain intact.
- Full period-opening module plus the audit export case: **10 passed in 67.57 seconds**,
  /private/tmp/waiver-audit-final.log. Ruff/format/whitespace checks pass. No production
  code changed; all runs terminal. Two original baseline failures remain unresolved:
  the pending AI lifecycle audit category and late-billing out-of-period K07 report.
  Broader current-main verification, implementation gaps and independent accounting
  sign-off remain open. No deployment.

## Architecture follow-up — October 7, 2026

- Continued from 906a83e. Full command-route audit plus architecture run: **5 failed,
  263 passed in 169.16 seconds**, /private/tmp/post-import-audit-architecture.log.
  The audit walk passed in 28.52 seconds. Five architecture checks exposed missing
  declarations, a data-model column-order mismatch and an upward kernel/domain import.
- Step 1 approval content now uses a registered SubjectLifecycle.content callback;
  approvals no longer imports contracts to compute the hash. A missing callback refuses
  explicitly. The existing domain function still supplies the exact approved content.
  Sync-total exception assignment explicitly declares no contract IDs: its subject is
  the sync run, not an individual contract. Data-model documentation matches the table's
  owner-membership/entity column order.
- Enumerated the five Step 1 tenant-scope entries with their purposes and the new import
  computation deferral as a stored calculation, not a preview. Documented these boundaries
  in the developer guide. The checks still reject unlisted calls. The preview check's
  own negative-control expectation now includes the new declared call site.
- Final affected architecture modules: **38 passed in 18.74 seconds**,
  /private/tmp/architecture-followup-final.log. Preview negative controls plus actual Step 1
  soft-close approval, book-change staleness, evidence snapshot, performing-entity review,
  draft approval and sync totals: **13 passed in 54.51 seconds**,
  /private/tmp/architecture-workflow-regressions.log. Source Mypy, Ruff/format and whitespace
  pass. All runs terminal. This closes the five new architecture findings; no complete
  backend pass is claimed. The two original baseline failures, remaining implementation
  gaps and independent accounting sign-off remain open. No deployment.

## Tooling revalidation and import cleanup retry — October 7, 2026

- Continued from 09c31ef. Preserved session 71400 and its primary test database until
  terminal. The seven tooling cases passed unchanged: **7 passed in 350.56 seconds**,
  /private/tmp/local-tooling-revalidation.log. Demo fixture setup took 326.84 seconds.
  This verifies missing-demo-password refusal, fixture tamper detection/no writes,
  dependency licensing, Makefile success output, running-stack reset refusal, OpenAPI
  stale/current checks and process start/reuse/stop. Earlier missing-tooling errors do
  not reproduce in this configured checkout. No blanket environment exemption added.
- The import failure test expected settlement to finish despite a held upload. Current
  required-hook behavior deliberately rolls back settlement on cleanup failure. The
  test now checks COMMITTING/RUNNING while held and retries after release, requiring
  FAILED/FAILED plus one IMPORT_PROCESSING_FAILED item. Already committed uploads
  remain committed, and each job emits one job.failed log; the held case logs its
  initial hook failure. Production code is unchanged.
- Full import failure-hook module: **4 passed in 15.88 seconds**,
  /private/tmp/import-failure-cleanup-verified.log. Ruff/format and whitespace checks pass.
  All processes terminal. Eight original baseline failures resolved; four remain:
  close waiver freshness, pending AI audit category, modification audit report expectations,
  and the late-billing out-of-period report. Current full-backend verification and
  implementation gaps remain open, as does independent accounting sign-off. No deployment.

## Post-import computation scheduling — October 7, 2026

- Continued from 3e106e6. AI routes are genuinely absent, so its pending audit category
  remains open. Investigation of B3-7 confirmed CSV commits collect affected groups but
  schedule no computation. A new real import regression failed because no child job existed
  (/private/tmp/import-compute-before.log, 1 failed in 10.27 seconds).
- Successful CSV commits now insert one CONTRACT_COMPUTE child for each distinct affected
  group, linked to the import job and upload. Jobs share the import transaction and dispatch
  after commit. The existing worker computes each group separately; calculation failures
  cannot roll back committed imported events. The period-lock retry carries the parent ID.
- The regression verifies two rows for one contract produce one child and the actual worker
  succeeds. An injected failure after scheduling rolls back both contract and child job;
  an injected worker failure preserves the COMMITTED upload and event. Existing period-pin
  instrumentation forwards the new parent argument, retaining its original race assertions.
- Import commit module plus stream-appender architecture checks: **19 passed in 35.35 seconds**,
  /private/tmp/import-compute-final.log. Transient-error and import period-pin checks:
  **13 passed, 4 deselected in 51.20 seconds**, /private/tmp/import-compute-period-pins.log.
  Final actual lock-race check with exactly-one-child assertion: **1 passed in 43.61 seconds**,
  /private/tmp/import-compute-retry-child.log. Source Mypy, Ruff/format and whitespace pass.
- All runs terminal. LIMITS B3-7 records the scheduling improvement; B1-20 distinguishes
  CSV imports from adapter booking. The zero-posting late-event report (B4-7/K07), general
  dirty-group sweep, monetary import totals, AI feature, broader verification and independent
  accounting sign-off remain open. Both original baseline failures remain unresolved.
  No deployment; publication exclusions and noncommercial licensing are unchanged.

## Invoice monetary reconciliation — October 7, 2026

- Continued from 644bcfb; the prior turn implemented and published the late-event report
  (progress). Revalidated clean main and B1-19: commit reconciled rows but no stored amounts.
- Added a commit-only template reconciliation callback. CSV invoices/credit memos now
  independently read persisted document totals, signed source lines, positive event amounts,
  tax components and currencies against validated source rows. This runs inside the narrowed
  transaction; any mismatch rolls back the whole batch and raises CONTROL_TOTALS_MISMATCH.
  Loaded monetary_checks retain the expected/stored evidence, with an explicit mismatch
  sentence. Verified file-column amount sums are also compared to validation's source totals.
- Repeated tax rows count once per component and once per logical invoice line. File-column
  totals retain IPL-06 repeated-cell semantics. A two-tax-row fixture verifies a 54,000 invoice
  while the repeated amount column totals 108,000; neither ledger nor document is doubled.
- Three injected emitter defects change source amount, event amount or remove source tax.
  Each leaves FAILED with the blocking mismatch and no events, source documents/records,
  lineage or calculation child. Ordinary signed credit memos retain their existing behavior.
- Invoice plus shared commit modules: **24 passed in 66.78 seconds**,
  /private/tmp/invoice-reconcile-final.log. Final mismatch-copy, repeated-cell and architecture
  checks: **93 passed in 27.81 seconds**, /private/tmp/invoice-reconcile-contracts.log.
  The first invoice-only run passed 9 in 38.61 seconds. Source Mypy and Ruff pass; all runs
  terminal. No full-backend pass or deployment claimed.
- This implements invoice monetary reconciliation, not all templates. B1-19 and the developer
  guide explicitly retain other monetary templates and ineligible integration-owner fallback
  notifications as outstanding. AI, broader verification, other documented implementation
  gaps and independent accounting sign-off remain open. Licensing/publication exclusions
  are preserved; direct-main workflow continues.

## Event-import monetary reconciliation — October 7, 2026

- Continued from clean main 257533d. The preceding turn implemented and published invoice
  read-back checks (progress). Extended the existing transaction gate to CSV costs,
  pre-standard revenue and rated usage using an independent reader of persisted events.
- The reader checks contract, event type, effective date and source-record identity as well
  as amount/currency. It reads validated source rows, not the emitter's possibly altered
  plan body. Signed revenue remains signed; absent rated usage amounts stay distinct from
  explicit zero. All declared amount columns of each covered template have a reader.
- Real import tests inject altered amounts or missing target references after approval.
  Every failed batch retains a blocking monetary mismatch but no events, source records,
  lineage or calculation children. Successful imports retain matching source/stored evidence
  and file-column totals. Cases cover cost, negative pre-standard revenue, positive rated
  usage, absent rated amount and explicit zero.
- Final new workflows plus existing cost/usage/estimate/modification and quarantine tests:
  **21 passed in 67.91 seconds**, /private/tmp/event-amounts-final.log. The first run's three
  successful-path assertions expected scientific notation; corrected to decimal strings.
  Its six rollback cases already passed. Source Mypy and Ruff pass. A direct registry check
  confirms all three readers cover their complete declared monetary columns.
- Architecture import/layer checks: **47 passed in 8.95 seconds**,
  /private/tmp/event-amounts-architecture.log. All runs terminal. B1-19 and the developer guide retain
  contracts, SSP, estimate and legacy monetary reconciliation as outstanding, along with
  ineligible integration-owner notification fallback. AI, full current verification,
  other documented gaps and independent accounting sign-off remain open. No deployment;
  publication exclusions and noncommercial licensing are preserved.

## SSP monetary reconciliation — October 7, 2026

- Continued from clean main 3e5f9dc. The prior turn published cost/revenue/usage event
  read-back checks (progress). Added CSV SSP values to the transactional reconciliation gate.
- Reconstructs expected entry prices/ratios, currency, business dimensions, value basis,
  quantity unit and complete band sets from validated source rows, independently of the
  emitter's plan body. Reads actual entries/bands for the emitted book version. Missing,
  additional or changed values trigger CONTROL_TOTALS_MISMATCH and roll back the batch.
- Independently derives legacy-range low/mid/high values with wide decimal arithmetic,
  then compares at TY-02 NUMERIC(38,18) precision, including PostgreSQL rounding. SSP numeric
  fields are flattened text, so explicit monetary_checks carry coverage even though
  amount_sums is empty. Bands are grouped by entry without a quadratic scan.
- Existing declarations/scope tests first passed **10 in 33.98 seconds**. Final module plus
  layer/import-cycle checks: **61 passed in 52.11 seconds**,
  /private/tmp/ssp-reconcile-final.log. Tests include valid multi-band entries, deliberately
  changed points and missing bands after approval, batch rollback/no version or source
  lineage, and a derived legacy range with an 18-decimal discount ratio. Source Mypy,
  Ruff/format and whitespace pass. All runs terminal; no complete backend pass claimed.
- B1-19 and the developer guide now reflect SSP coverage. Contract, estimate and legacy
  monetary reconciliation, integration-owner fallback notification, AI, broader current
  verification, other documented gaps and independent accounting sign-off remain open.
  No deployment. Noncommercial licensing and publication exclusions are unchanged.

## Contract monetary reconciliation — October 7, 2026

- Continued from clean main 3577d81; prior turn published SSP read-back checks (progress).
  Added the contract template to the transactional monetary gate for new and replacement
  draft bookings. Reads actual CONTRACT_BOOKED targets bound to the current import.
- Each obligation/product line's price, out-of-scope amount, quantity, unit price and scope
  flag is compared against validated source rows. Contract and payload transaction currencies
  and the source-record identity are checked. Offsetting line errors cannot hide behind a
  matching aggregate total. Verified file-column totals retain the existing IPL-06 check.
- Inspection found that replacement imports omitted upload/source-record provenance even
  though replace_draft already accepts it. They now pass those identifiers, IMPORT origin and
  the import idempotency key; new and replacement bookings share the provenance contract.
- Existing shared commit tests: **14 passed in 40.99 seconds**,
  /private/tmp/contract-reconcile-first.log. New/replacement success and offsetting-error
  workflows plus layers/import cycles/stream-appender architecture: **56 passed in 32.58 seconds**,
  /private/tmp/contract-reconcile-final.log. A 1,000 decrease on one line and increase on the
  other rolls back despite unchanged 120,000 total. No source records, events, lineage or
  calculation children survive; failed replacements preserve the complete previous contract.
  Successful replacements carry their import source. Source Mypy, Ruff/format and whitespace
  pass. All runs terminal; no complete backend pass or deployment claimed.
- B1-19 and developer guidance reflect contract coverage. Estimate and legacy monetary
  readers, integration-owner fallback notification, AI, broader current verification,
  other documented gaps and independent accounting sign-off remain outstanding.
  Publication exclusions and noncommercial licensing remain unchanged.

## Estimate monetary reconciliation — October 7, 2026

- Continued from clean main 2b1c477. The prior turn published contract price/provenance
  checks (progress). Added estimate imports to the transactional read-back gate.
- Reconstructs scalar money values, rates, quantities, amortization months, typed parameters
  and full scenario rows from validated source rows. Compares the stored version plus
  contract/element identity, kind, method, currency, direction, allocation target and obligation.
  Scalar columns use their database precision; JSON scenarios retain their decimal precision.
  Source rows, not the emitter's altered plan body, supply the expected financial inputs.
- New-element defaults follow the existing command. Existing elements inherit omitted
  settings; explicit file settings still must agree. A regression preserves an existing
  INCREASE direction when the new version's file omits it, avoiding an unintended change
  to the established existing-element import behavior.
- Tests inject changed constrained amount, changed refund parameter, offsetting scenario
  amounts with unchanged aggregate, and a rebate direction flipped to INCREASE after approval.
  Each leaves a blocking mismatch with no estimate element/version or source lineage committed.
  Valid imports retain matching evidence, scenario zero and default contract currency.
- Initial existing end-to-end witness: **1 passed in 15.78 seconds**. Expanded workflows plus
  layer/import-cycle checks: **53 passed in 39.53 seconds**, /private/tmp/estimate-reconcile-complete.log.
  Final inherited-setting and full financial workflow rerun: **7 passed in 31.16 seconds**,
  /private/tmp/estimate-reconcile-inherited.log. Source Mypy and Ruff/format/whitespace pass.
  All runs terminal; no whole-backend pass claimed.
- B1-19 and developer guidance retain legacy monetary readers as incomplete. Integration-owner
  fallback notification, AI, broader verification, other documented gaps and independent
  accounting sign-off remain open. No deployment. Publication exclusions/noncommercial
  licensing are unchanged; tested changes continue directly to main.

## Legacy SSP monetary reconciliation — October 7, 2026

- Continued from clean main 6fb12c3. The preceding workflow check confirmed all 31 PRs
  merged and main as the sole remote branch; no implementation change in that turn.
- Legacy SKU SSP imports now reconstruct expected prices, ratios and reporting currency
  from validated legacy rows, independently of the emitter request builder. Reuses the
  stored-entry/range reader, including independently derived bands at database precision.
  A mismatch rolls back the whole import, including its approved SSP version and lineage.
- Legacy emitters have no flattened columns. Their verified file-column amount sums now
  use the upload's pinned template header definitions, matching validation metadata.
  Existing whole-version quarantine and later-version append behavior remain covered.
- New cases change two prices while preserving their aggregate, change a discount or
  remove a derived band after approval. All fail with blocking CONTROL_TOTALS_MISMATCH;
  valid input retains matching evidence and a 603 list-price sum. The initial run exposed
  a missing required distinctness field in the independent translation; corrected it.
  The complete SKU SSP module then passed **7 tests in 29.94 seconds**,
  /private/tmp/legacy-ssp-reconcile-matrix.log.
- Final legacy/shared-commit/CSV-SSP/layer/import-cycle run: **166 passed in 637.17 seconds**,
  /private/tmp/legacy-ssp-reconcile-final.log. All runs terminal. Source Mypy, Ruff lint/format
  and whitespace checks pass. No whole-backend or production claim.
- Updated B1-19 and developer guidance; preserved dated event-import evidence in build
  history. Next: legacy contract setup, progress and modification monetary readers.
  Integration-owner fallback, AI, remaining implementation/verification and independent
  accounting sign-off remain open. No deployment. Publication exclusions and noncommercial
  licensing are unchanged; verified changes publish directly to main.

## Legacy contract setup monetary reconciliation — October 7, 2026

- Continued from clean main 1ebf45a; the prior turn published legacy SSP checks (progress).
  Added a separate reader for legacy setup source orders, additive booking events and VC.
- Reconstructs file prices/quantities and currencies independently of emitter requests.
  Split uploads retain earlier draft lines read from immutable earlier bookings. Source-order
  lines are checked independently, at database precision, against the current file's rows.
- VC rows require a linked approved version with the source magnitude, reporting currency,
  effective date and import approval. Newly created elements also check source-derived sign
  and defaults; existing elements retain their settings. Added new-element target identities.
  The old test spy now observes real VC writes, so a no-op writer cannot pass reconciliation.
- Existing setup/activation/split-upload tests: **14 passed in 85.52 seconds**,
  /private/tmp/legacy-setup-first.log. The first corruption/architecture run had **54 passed,
  2 failed**: source-order UPDATE injection hit immutable-table protection before read-back.
  Replaced that injection with altered inputs to the source-order insert. Booking corruption,
  prior-line corruption, VC amount/direction corruption and missing VC already rolled back.
- Expanded setup/approval-floor/approver/architecture run: **91 passed, 1 failed in 228.64
  seconds**, /private/tmp/legacy-setup-final.log. Its sole failure was the new existing-element
  fixture's invalid API identifier (422 before import). Corrected its identifier and VC type;
  final matrix/layer/import-cycle rerun: **57 passed in 55.10 seconds**,
  /private/tmp/legacy-setup-corrected.log. Existing-element INCREASE direction is retained.
  All runs terminal. Source Mypy, Ruff lint/format and whitespace pass. No full backend
  or readiness claim.
- Updated B1-19 and developer guidance; archived dated SSP evidence without removing release
  gates. Next: legacy progress and modification monetary readers. Owner-notification fallback,
  AI, other implementation/verification gaps and independent accounting sign-off remain open.
  No deployment. Publication exclusions/noncommercial licensing are unchanged.

## Zero-posting late-event register — October 7, 2026

- Continued from 3705c7c. The previous turn confirmed no open PRs and main as the sole
  remote branch; it made no implementation change. Implemented REG-LATE-NOLINE-1 using
  stored ENGINE LATE_EVENT findings, joined to actual event UUIDs through their dedupe keys.
  New fallback findings pin the primary book. Legacy findings retain the stated primary-book
  fallback; secondary books require their own stored evidence.
- Findings are filtered by entity, book, calendar/period and both finding/event timestamps.
  Closed/resolved status does not erase inclusion evidence. Existing single/cumulative ledger
  attributions suppress additional event rows for the same origin/posting pair. Zero rows do
  not invent ledger lines or effects. Event amount is the explicit payload Money value for a
  single event; it is null for multi-event sets, triggers or events with no explicit amount.
  Column labels explicitly identify revenue/balance amounts posted out of period. Catalogue
  and source-binding declarations name the additional inputs.
- K07 now drives the actual queued import computation. Before that worker, no row is shown;
  after it, the EUR 100,000 invoice is shown with zero effects/line count, uploader and import
  approval. Checks include timestamps immediately before/at finding creation, other periods,
  origin filters and another book. Existing cumulative-attribution and frozen-register tests
  retain their original counts and monetary expectations. CSV keeps event amounts separate.
- Final register/export/provenance/snapshot/source-binding run: **110 passed in 71.39 seconds**,
  /private/tmp/late-register-final.log. Intermediate runs identified missing ReportParams in
  the new test and updated CSV header expectations; both are corrected. Source Mypy and Ruff
  pass. Import-cycle/layer/report-reader architecture checks: **49 passed in 8.86 seconds**,
  /private/tmp/late-register-architecture.log. All runs terminal; no complete backend pass claimed.
- LIMITS B4-7/B3-7 and standing K07 failure are updated. Prior-date balance classification and
  broader secondary-book finding coverage remain limited. One original baseline failure
  remains: the absent AI lifecycle feature. Monetary import reconciliation, other documented
  gaps, full current verification and independent accounting sign-off remain outstanding.
  No deployment. Publication exclusions and PolyForm Noncommercial licensing are unchanged.

## Legacy progress monetary reconciliation — October 7, 2026

- Continued from clean main f15e790. The prior turn published legacy setup checks (progress).
  Added independent read-back for legacy progress imports, including the original aggregated
  rows. Source billing, signed pre-standard revenue and delivery are summed by obligation/SKU
  without reusing the emitter's aggregation or payload builder.
- Compares stored billing/credit/revenue and delivery/return events, their currency/date,
  lead source-record identity and declared targets. Independently checks signed synthetic
  invoice/credit headers and lines, including currency, source identity, product and obligation.
  Positive billing must link to the expected invoice. Zero aggregates create neither a
  financial event nor a document. Verified file-column totals retain their original semantics.
- Tests inject changed event amount, changed signed invoice amount, changed revenue/quantity,
  a missing event and an unexpected posting for a zero aggregate after approval. Every mismatch
  rolls back the complete import, preserving existing contracts, events and invoices and leaving
  no source records or lineage. Positive, negative and zero duplicate-row aggregates succeed.
- Existing progress/credit/return workflows: **11 passed in 86.83 seconds**,
  /private/tmp/legacy-progress-first.log. New matrix, amended-terms and layer/import-cycle
  checks: **59 passed in 100.96 seconds**, /private/tmp/legacy-progress-final.log.
  Final reader uses copy_abs to preserve full decimal precision; matrix rerun: **11 passed
  in 72.55 seconds**, /private/tmp/legacy-progress-verified.log. All runs terminal.
  Source Mypy, Ruff lint/format and whitespace pass. No whole-backend or readiness claim.
- Updated B1-19 and developer guidance; preserved dated estimate evidence in build history.
  Next: legacy modification monetary read-back. Integration-owner fallback, AI, other
  implementation/verification gaps and independent accounting sign-off remain open.
  No deployment. Publication exclusions/noncommercial licensing are unchanged.

## Legacy modification reconciliation and coverage audit — October 7, 2026

- Continued from clean main 35c9fe2. Prior turn published legacy progress checks (progress).
  Added independent amendment read-back for signed consideration and quantity deltas,
  line identities/dates, all-obligation treatment, approved SSP reference and override defaults.
  Also checks source/approval/synthetic modification identity, emitted targets and added
  obligation product identities. Expected facts do not reuse emitter line/catalogue builders.
- Prospective, retrospective, price-only, negative and add-obligation workflows are covered
  by new tests. Faults injected after approval alter amount, quantity, treatment, SSP basis
  or the added obligation's stored product. Mismatches must roll back the whole import.
- Initial replay: **3 passed, 6 failed in 124.28 seconds**,
  /private/tmp/legacy-modification-first.log. The new expectation omitted default SSP
  is_override/justification fields; corrected the comparison. Expanded replay, matrix and
  layer/import-cycle run: **63 passed, 3 failed in 216.60 seconds**,
  /private/tmp/legacy-modification-final.log. The three new add-obligation fixtures omitted
  required account fields, so validation refused them before the gate. Completed those rows;
  corrected matrix rerun: **10 passed in 66.40 seconds**,
  /private/tmp/legacy-modification-corrected.log. All runs terminal. Source Mypy,
  Ruff lint/format and whitespace pass.
- Audited the actual emitter registry and callback bodies. Added dated coverage inventory
  docs/release/IMPORT-RECONCILIATION-2026-10-07.md; a callback's presence is not full coverage.
  Remaining: CSV progress refund/numeric inputs, FX rates, bundle quantities, invoice/usage
  quantities and explicit event obligation binding. CSV modifications have no emitter and
  remain explicitly refused; legacy support does not imply CSV support.
- Updated B1-19/developer guidance and preserved old SSP evidence in build history. Next:
  close the named CSV gaps. Other implementation/verification gaps, integration-owner fallback,
  AI and independent accounting sign-off remain open. No whole-backend/readiness claim or
  deployment. Publication exclusions/noncommercial licensing are unchanged.

## Invoice quantity and identity reconciliation — October 7, 2026

- Continued from main 2fcf380. Invoice read-back now compares source-line quantities at
  database precision (absent versus zero preserved), contract/obligation/product identities,
  service dates, header dates/cancellation/credit reference, and event contract/date/source,
  obligation, invoice/line references and source-invoice link. Tax roles/types/jurisdictions
  are checked alongside amounts. Expectations come from original validated rows.
- First run: **5 passed, 5 failed in 44.83 seconds**, /private/tmp/invoice-fields-first.log.
  Fixed the new reader's expectation of CSV boolean text versus stored booleans. Expanded
  invoice replay: **18 passed in 64.51 seconds**, /private/tmp/invoice-fields-second.log.
  Final invoice matrix: **28 passed in 98.51 seconds**, /private/tmp/invoice-fields-final.log.
  Includes changed quantities, wrong contracts/obligations/products/references, changed tax
  classifications/dates, credit memos, absent/zero quantities and 18-place database rounding.
  Each injected mismatch rolls back documents/events/source records/lineage/calculation jobs.
  Shared import/template and layer/import-cycle regressions: **75 passed in 84.09 seconds**,
  /private/tmp/invoice-fields-regression.log. All runs terminal. Source Mypy, Ruff lint/format
  and whitespace pass. Archived older late-event evidence verbatim in the build history.
- Updated coverage inventory, B1-19 and developer guidance. FX-rate and bundle readers,
  integration-owner fallback, AI, other implementation/release checks and independent
  accounting sign-off remain open. No full-suite or production-readiness claim. No deployment.
- Confirmed GitHub has no open PRs, only main locally/remotely, and automatic deletion of
  merged branches enabled. Continue testing and pushing directly to main; no new PRs.

## CSV progress and event field reconciliation — October 7, 2026

- Continued from clean main 31e2d1b. Prior turn published legacy modification checks and
  identified additional CSV gaps (progress). Extended the shared event reader to compare
  explicit numeric and identity fields from original validated rows, using wide decimals.
- CSV progress now checks all four event kinds: delivery, return, progress and milestone.
  Reconciles refund amount/currency (absent versus zero), quantity, progress ratio, hours,
  milestone weight/code, obligation, trigger/measure, references, contract/date/source identity.
  The expected event kind is taken from the source row, not the emitter's modified body.
- Usage now also checks quantity, period dates, metric and obligation. Cost/pre-standard
  events bind their obligation; costs also compare purpose, flags, payee and plan. Source
  amounts continue to reconcile to stored events before verified file-column totals are kept.
- Original monetary regression module: **15 passed in 55.28 seconds**,
  /private/tmp/csv-event-fields-first.log. Expanded progress/refund and event-field tests,
  CSV template workflows and layer/import-cycle checks: **95 passed in 180.38 seconds**,
  /private/tmp/csv-event-fields-final.log. Changed refunds, quantities, ratios, hours, weights,
  wrong obligations and missing event targets all roll back without source/event/lineage or
  calculation children. Null/zero refund and rated-usage cases retain their distinction.
  All runs terminal. Source Mypy, Ruff lint/format and whitespace pass; no full backend claim.
- Updated the coverage inventory, B1-19 and developer guidance; preserved older setup
  evidence in build history. Next: FX rates, bundle quantities and CSV invoice quantity/
  contract/obligation checks. Integration-owner fallback, AI, other implementation and
  verification gaps and independent accounting sign-off remain open. No deployment.
  Publication exclusions/noncommercial licensing are unchanged.

## Bundle replacement reconciliation — October 7, 2026

- Continued from clean main 74e3437 (prior turn made verified invoice progress). Bundle
  imports now independently read the full stored replacement and bind each source row to
  its declared component target. Compare bundle/component identity, quantity, split basis/
  ratio, sequence and effective windows; derive the next-set end boundary from source rows.
  Reject missing/extra targets or stored components. A mismatch restores the previous list.
- Added a PostgreSQL replacement matrix: high-precision and omitted/default fields succeed;
  changed quantity, ratio, component, bundle, date, sequence, missing target and extra row
  must fail with CONTROL_TOTALS_MISMATCH and leave no new source records/lineage.
- First run: **1 passed, 9 failed in 21.61 seconds**, /private/tmp/bundle-readback-first.log.
  The new fixture used 19 decimal places, beyond the command's 18-place input limit;
  corrected it. Second run: **10 passed, 1 failed in 23.40 seconds**,
  /private/tmp/bundle-readback-second.log. Blank CSV cells normalize to null; corrected
  the reader to apply quantity/split-basis defaults to omitted source values. Both runs
  are terminal. Final matrix, CSV workflows and layer/import-cycle regressions:
  **67 passed in 53.00 seconds**, /private/tmp/bundle-readback-final.log, terminal.
  Source Mypy, Ruff lint/format and whitespace checks pass.
- Updated coverage inventory, B1-19 and developer guidance. FX-rate read-back remains next;
  integration-owner fallback, AI, broader implementation/release checks and independent
  accounting sign-off remain open. No full-suite/readiness claim or deployment. Preserve
  publication exclusions/noncommercial licensing; publish tested changes directly to main.

## FX import rate reconciliation — October 7, 2026

- Continued from clean main 8667084; prior turn published bundle reconciliation (progress).
  Added an independent FX version reader: compare set/coverage/upload/status, the complete
  entered/derived rate list, pair/type/day/period identity and per-source lineage targets.
  Reconstruct inverse rates with independent decimal arithmetic and 12-place half-up rounding;
  explicit reverse pairs suppress derivation. Period keys resolve closing/average end dates.
- Initial matrix plus existing approval workflow: **15 passed in 31.02 seconds**,
  /private/tmp/fx-readback-first.log, terminal. Covers spot/closing/average, precision,
  explicit inverse and rounding tie; changed rate/currency/day/period/coverage/set, changed
  inverse, missing inverse and missing targets all roll back versions, FX approval requests,
  source records and lineage. Added swapped targets and a multi-version batch (including
  failure of the second version). Expanded matrix, CSV workflows and layer/import-cycle
  regressions: **74 passed in 69.18 seconds**, /private/tmp/fx-readback-final.log, terminal.
  Source Mypy, Ruff lint/format and whitespace checks pass.
- Updated inventory, B1-19 and developer guidance; archived older legacy progress evidence
  verbatim. Listed financial CSV and legacy readers now have defined scope, not a claim of
  full accounting coverage. Integration-owner fallback, AI and other implementation gaps,
  remaining release checks and independent accounting sign-off remain open. No deployment
  or full-suite/readiness claim. Preserve exclusions/licensing; push verified changes to main.

## Integration mismatch recipient fallback — October 7, 2026

- Continued from clean main e12dcfd; prior turn published verified FX checks (progress).
  Sync mismatches now prefer the configured eligible owner, then the connection's human
  creator if still an active tenant member with manage/read scope over every affected entity.
  Assign the exception and notify once; do not rewrite connection ownership. No broad role
  broadcast or API-client/system-to-human identifier fallback. With no qualified recipient,
  preserve the unassigned blocking exception for authorized queue review.
- Existing sync/reconciliation tests plus new fallback/priority/deduplication matrix:
  **11 passed in 23.65 seconds**, /private/tmp/integration-owner-fallback-first.log, terminal.
  Added narrowed-creator-scope refusal and updated owner help/missing-owner UI copy.
  Expanded backend/architecture run: **58 passed, 1 failed in 35.08 seconds**,
  /private/tmp/integration-owner-fallback-final.log. The new scoped-role fixture attempted
  a duplicate active assignment. First correction: **11 passed, 1 failed in 25.49 seconds**,
  /private/tmp/integration-owner-fallback-corrected.log: assignment scope is immutable.
  Changed the fixture to revoke then regrant within the failure transaction. Final scoped
  matrix: **12 passed in 25.25 seconds**, /private/tmp/integration-owner-fallback-verified.log.
  All backend runs are terminal; the expanded run passed all 47 architecture checks. Integration settings UI: **27 passed in 3.19 seconds**,
  /private/tmp/integration-owner-fallback-ui.log, terminal. Source Mypy, Ruff lint/format,
  JSON Prettier and whitespace checks pass.
- Source inspection confirmed file uploads deliberately retain uploader visibility; that
  existing rule is preserved. Updated B1-19/developer guidance and archived older amendment
  evidence verbatim. AI, other implementation gaps, remaining release checks and independent
  accounting sign-off remain open. No full-suite/readiness claim or deployment. Preserve
  exclusions and noncommercial licensing; push verified changes directly to main.

## Repository gate verification and Terraform socket repair — October 7, 2026

- Continued from clean main 87f53d1; prior turn published dirty-group recovery (progress).
  `make audit-deps` passed in an immutable snapshot of that revision: 77/77 pinned Python
  runtime distributions, zero Python vulnerabilities and zero npm runtime advisories.
  Source/dependency binding matched. Dated hashes and evidence paths are in
  docs/release/REPOSITORY-GATES-2026-10-07.md; raw report is under .run/reports/audit-deps/.
- Terraform init/fmt passed, but provider handshakes failed in the long immutable-context
  temporary path. A retained-context validation with a relative temporary path succeeded.
  Script now gives providers a short module-relative path within the same .run/tmp directory.
  Added a real Unix-socket regression. Initial supervisor-script run: **40 passed, 1 failed
  in 93.04 seconds**, /private/tmp/tf-provider-temp-tests.log, terminal. The old guard wrongly
  rejected permitted .run/tmp paths; narrowed it to host-global temporary paths. Corrected
  Terraform/forbidden-pattern verification: **20 passed, 26 deselected in 20.33 seconds**,
  /private/tmp/tf-provider-temp-verified.log, terminal. Ruff/format, bash syntax and whitespace
  checks pass. `make tf-validate` then passed on clean 40ae405 in an immutable
  context: init/fmt/validate all pass, matching source/dependency bindings, Terraform
  1.16.4 and four locked providers. Report: .run/reports/tf-validate/report.json;
  /private/tmp/erev-tf-validate-verified.log. Both formal gate processes are terminal.
- Docker CLI exists but its daemon is stopped; container-based gates remain unverified.
  No deployment or cloud mutation. AI/other implementation gaps, remaining verification and
  independent accounting sign-off remain open. Preserve exclusions/noncommercial licensing.
  Archived older CSV progress evidence verbatim; continue tested direct-main publication.

## Dirty contract recovery sweep — October 7, 2026

- Continued from clean main e23068e (prior turn made verified owner-fallback progress).
  Added worker SCH-17 each minute: dirty APPLIED groups with booked current members receive
  durable CONTRACT_COMPUTE jobs. Preserve FX_REPUBLISH, otherwise COMMAND; skip locked groups,
  existing live normal jobs and generations already swept. Generation includes timestamp and
  row version so a new change sharing a timestamp still runs. Preview jobs do not suppress work.
  Transactions and failures isolate each group/tenant. Engine completion owns clearing marks;
  unchanged quarantined/failed generations stay with existing retries/exception remediation.
- First matrix/worker run: **6 passed, 2 failed in 34.38 seconds**,
  /private/tmp/dirty-sweep-first.log. New fixtures used an unsupported dirty trigger; corrected
  to the schema's FX_REPUBLISH. Expanded worker/architecture run: **56 passed, 1 failed in
  48.25 seconds**, /private/tmp/dirty-sweep-final.log. The new normal-job fixture still queued
  PREVIEW; corrected it. Matrix with enqueue isolation/recovery: **6 passed in 21.33 seconds**,
  /private/tmp/dirty-sweep-corrected.log. These runs are terminal. Added generation row version
  and same-timestamp re-mark verification: **6 passed in 21.45 seconds**,
  /private/tmp/dirty-sweep-verified.log, terminal. All 47 architecture and 5 worker checks
  passed in the expanded run. Source Mypy, Ruff lint/format and whitespace checks pass.
- Updated schedule registry, B3-7 and developer guidance; preserved older invoice evidence
  in build history. AI and other implementation gaps, broad release verification and independent
  accounting sign-off remain. No full-suite/readiness claim or deployment. Preserve publication
  exclusions/noncommercial licensing and push tested changes directly to main.

## Journal validation currencies and evidence — October 8, 2026

- Continued from clean published main a63dfc0; prior turn completed SSP range lineage (progress).
  Generation now checks transaction/stamped functional currency codes against the active
  catalogue and the functional stamp against the entity. A mismatch refuses the whole run with
  JOURNAL_CURRENCY_INVALID and named exceptions. Tenant enablement is not used to discard older
  lines, and currency validation assumes no fixed decimal precision.
- Every newly written run records CTL-020 in its own transaction: validated detail population,
  currency set, checks, entity/book/period and coverage, with held lines counted as unvalidated.
  Empty populations are NOT_APPLICABLE; nonempty valid ones PASS. The calculation audit links
  the evidence UUID. Failure/retry boundaries preserve the existing atomic/idempotent behavior.
- Initial rules and PostgreSQL validation matrix: **24 passed in 12.51 seconds**,
  /private/tmp/journal-currency-first.log. Includes a sealed EUR-functional line in a USD entity:
  rejected with named exceptions, no journal run and no passing validation evidence. Added empty
  population and audit-link checks. Expanded validation/gross/delta/held/empty-run plus import
  cycle, forbidden-pattern and money-literal architecture checks: **80 passed in 126.75 seconds**,
  /private/tmp/journal-currency-final.log. Both processes terminal. Mypy passes both source files;
  Ruff lint/format and whitespace checks pass.
- Updated the finding catalogue, B1-25 and developer guidance; archived prior FX import evidence
  verbatim. Remaining implementation, full-suite/release verification, the pending engine version
  cut/replays and independent accounting sign-off are still open. No deployment or readiness
  claim. Preserve exclusions/noncommercial licensing; publish tested changes directly to main.

## Selected SSP range provenance — October 7, 2026

- Continued from clean main 4e043a1 after verifying all 31 PRs merged and only remote main.
  Engine selections now retain the actual band's natural key, including equal-price bands;
  persistence resolves it to the approved range UUID. Point/range and modification weight traces
  cite the band directly. Readback recognizes historical entry and new range sources, preserving
  pinned versions. Formula-only/bypass prices claim no band; merged selections keep all sources
  in trace and a scalar range only if every contributor shares it. No historical rewrite.
- First allocation/persistence run: **58 passed, 1 failed in 32.66 seconds**,
  /private/tmp/ssp-range-first.log (old currency trace expectation). Expanded trace/readback and
  architecture run: **361 passed, 12 failed in 175.23 seconds**,
  /private/tmp/ssp-range-expanded.log. One old repin source expectation and eleven scope-registry
  failures for the previously added dirty sweep. Registered SCH-17's reviewed SYSTEM builder,
  tenant-directory reader and non-preview computation with reasons; updated trace expectations.
- Allocation/modification/readback/persistence and affected architecture run: **290 passed,
  1 failed in 71.46 seconds**, /private/tmp/ssp-range-final.log. Remaining failure was the
  architecture reader's synthetic missing-registration expectation; corrected for the new entry.
  Added explicit range/entry readback matrix and equal-price point/range boundary cases.
  Corrected affected checks: **33 passed in 7.98 seconds**, /private/tmp/ssp-range-corrected.log.
  All runs terminal. Mypy passes 18 source files; Ruff lint/format and whitespace checks pass.
- Updated B1-23/developer guidance and archived older bundle import evidence verbatim.
  Output metadata/trace changes belong in the already pending 0.4.0 release cut and replay
  validation; no full-suite or production-readiness claim. AI/other implementation gaps,
  container/release verification and independent accounting sign-off remain. No deployment;
  preserve publication exclusions/noncommercial licensing and publish directly to main.

## SSP approval effective-value routing — October 8, 2026

- Continued from clean published main 4ebc96c (previous turn closed ledger-history freshness).
  The exact role-balance check still needs broader reader integration. Inspection also found
  material SSP changes that bypassed second review: list prices behind percentage bands,
  zero-to-nonzero points and changed observable points. Routing now compares effective SSP
  amounts, with legacy bands already scaled and retained unbanded cost-plus fallback aligned
  with the engine. Method/value-basis/quantity-unit changes also require second review.
- Cross multiplication in the explicit wide Decimal context preserves exact thresholds and
  increments above them. Unchanged zero and compensating inputs yielding the same SSP do not
  trigger numeric review; new/removed observable points do. Existing entry pairing and the
  preparer's qualitative methodology declaration remain. Historical approvals are unchanged.
- API counterexamples on unchanged code: **4 failed, 1 passed, 19 deselected in 13.68 seconds**,
  /private/tmp/ssp-routing-baseline.log: three missed second steps plus an unnecessary one when
  list-price and percentage changes compensated. Full publication checks after repair:
  **24 passed in 44.85 seconds**, /private/tmp/ssp-routing-publication.log. Added low-precision,
  exact/above-threshold, legacy and cost fallback cases; final publication/entity-scope/unit
  matrix and import-cycle/forbidden-pattern/money architecture checks: **84 passed in
  78.93 seconds**, /private/tmp/ssp-routing-final.log. All processes terminal. API cases prove
  material changes remain SUBMITTED/PENDING after the first decision and require a distinct
  second approver. Source Mypy, Ruff lint/format and whitespace checks pass.
- Updated routing requirements, PRD, B1-22 and developer guidance. B1-22 remains open for
  qualitative methodology changes not represented in stored inputs; exact reconciliation
  recomparison, remaining product/release gates and independent accounting sign-off remain.
  No deployment or readiness claim. Preserve publication exclusions/noncommercial licensing;
  publish tested changes directly to main.


## Broader repository checks and reopen UI tests — October 8, 2026

- Continued from clean published main 37c4f0c; previous turn made verified SSP-routing progress.
  `make typecheck` passed all 850 Python source files and frontend TypeScript. `make build`
  passed frontend production bundling and backend imports, with a non-failing large-chunk warning.
- Full frontend suite: **2 failed, 2,055 passed in 55.71 seconds** (192 files). Two old cockpit
  tests expected error corrections without an independently reviewed judgement. Corrected the
  scoped reviewed-evidence mock, citation-required/submitted assertions and reviewer display.
  Preserved optional new judgement/attachment coverage under late-source reopening with its
  exact request payload. No application code changed. Focused checks: **34 passed in 4.96
  seconds**. Full rerun: **2,057 passed in 55.65 seconds**, 192 files. All these processes are
  terminal; Prettier, frontend tsc and whitespace checks pass. Dated log paths/hashes and scope
  are in docs/release/REPOSITORY-CHECKS-2026-10-08.md. This is not a full CI or browser pass.
- Follow-up on clean main 1d59f65: `make lint` passed. Ruff formatting: 2,006 files;
  Ruff, Prettier, ESLint, OpenAPI, registry, migration-head and fixture checks passed. Design:
  501 files / no findings; vocabulary: 1,198 / no findings. Dependency licences: 133 packages,
  no unexpected findings; secrets: 3,423 files, no unexpected findings or unused allowances.
  All 495 control markers are valid (collection only, not a controls-report pass). Log:
  /private/tmp/erev-lint-2026-10-08.log, hash in the dated repository-checks note. Lint process
  is terminal. Confirmed PolyForm Noncommercial licence and no tracked files in either excluded
  research directory. Archived prior SSP-lineage evidence verbatim to preserve notebook size.
- LIVE PROPERTY GATE: executor session **52175**, pytest PID **6358**, immutable context
  .run/gates/ctx-properties-37c4f0c48918-6323. Command `make properties`, thorough profile,
  48 tests collected; two metamorphic tests passed, suite active with increasing CPU time. Log:
  /private/tmp/erev-properties-2026-10-08.log. Preserve and poll this exact process; never restart
  on elapsed time alone. Inspect the final report and bindings before claiming a result. Other
  test/typecheck/build handles are terminal. Inspection confirmed property tests use in-memory worlds and no database fixtures; keep database test processes serial with each other.
- Archived prior journal-validation evidence verbatim. Remaining implementation, current
  release checks, engine cut/replays and independent accounting sign-off remain open. No
  deployment/readiness claim; preserve exclusions and noncommercial licensing; push to main.

## Invitation-erasure identity recheck — October 8, 2026

- Continued from clean published main 4e90c37; previous turn recorded passing full lint.
  Closed B6-5: invitations lock and reread existing identities after locking any reused
  membership, before ending prior membership state, assigning roles or queuing mail. Disabled
  identities, changed normalized email and operator identities are refused. The acting-tenant
  membership-to-identity lock order matches erasure. New memberships also pin/recheck existing
  identities. A later explicit invitation to an erased person's former address may still create
  a separate new identity; the retained erased identity is never revived.
- PostgreSQL counterexample: **1 failed, 11 deselected in 7.71 seconds**,
  /private/tmp/invitation-erasure-baseline.log. A real erasure committed between discovery and
  membership lock; the invitation wrongly returned 201 and revived the erased row as INVITED.
  After repair, privacy/operator-reinvite/acceptance checks: **19 passed, 1 failed in 49.46
  seconds**, /private/tmp/invitation-erasure-fixed.log. Only an old 12-preference expectation
  failed: APPROVAL_UNASSIGNED had made 13. Replaced the count with the explicit expected kinds
  and corrected the stale activation docstring.
- Added erased-identity refusal in another workspace. Expanded privacy/invitation/access-scope
  and membership/person architecture checks: **29 passed in 66.36 seconds**,
  /private/tmp/invitation-erasure-final.log. After normalizing the compared address, focused
  erased/racing/new-identity verification: **3 passed, 10 deselected in 9.67 seconds**,
  /private/tmp/invitation-erasure-verified.log. These database processes are terminal. Source
  Mypy (two files), Ruff lint/format and whitespace checks pass. Tests assert no invitation
  outbox row or invitation audit survives the refusal. No live email was sent.
- Property gate session 52175 / PID 6358 remains live in its original immutable context;
  two metamorphic tests passed so far. Its fixtures were inspected: no database use, so the
  separate PostgreSQL regressions above could run safely; no two database pytest processes
  overlapped. Keep polling that same property process. Updated limitations/developer guide,
  archived prior SSP-routing evidence verbatim. No deployment or readiness claim. Remaining
  implementation/release checks, engine cut/replays and independent sign-off remain open.

## Full accounting corpus verification — October 8, 2026

- Canonical `make answer-keys AK_SCOPE=full` on clean main 177cb68 completed:
  **505 passed, two failed in 352.75 seconds**. All 255 keys selected: 251 passed,
  one failed, one not run, two withdrawn. All 255 review statuses remain unapproved.
  Coverage is complete across all six sections; source/dependency and corpus bindings verify.
- DLT-CHK-020 now reaches the nondistinct-review fixture limitation after 141 applied steps;
  its integration target is absent. VC-CHK-113 retains seven concession/billing differences,
  reserved for independent accounting decisions AD-14/AD-15. No oracle values or treatment
  were changed to force a pass. Updated limitations, accounting-review packet and dated gate
  evidence with exact counts/hashes. G4 remains failed; these are actionable remaining gaps.
- Archived the older broad-check section verbatim. Property session 52175 remains active in
  its original immutable context, with five metamorphic tests passed. The answer-key process
  is terminal, so no database pytest process remains active. No deployment or readiness claim.

## Policy approvals serialized with period locks — October 7, 2026

- Continued from PR #8 on main (`9c5556f`). Policy overrides do not append a contract event,
  so the existing event-appender period pin did not protect their approvals.
- Approval of an override on a non-draft contract now shares the close-window rows of all
  contracting/performing entities under tenant scope, after taking the group/contract locks and
  before publishing approval or supersession. Draft contracts have no frozen calculation and skip
  this control. The new scope entry is explicit in the architecture allowlist and developer guide.
- The pending-approvals gate ordinarily prevents a lock while a policy decision is outstanding.
  The regression uses the real **approved waiver** of that gate to exercise the permitted close
  path. When policy approval comes first, the lock waits, then refuses the committed dirty group.
  When the lock comes first, a later approval waits and can commit after it. When a lock overtakes
  an already-started policy decision, the stale approval is refused with `PERIOD_STATE_MOVED`;
  no approval audit or dirty mark is kept, the override remains submitted, and a retry succeeds.
- Counterfactual verification in an isolated test process bypassed only the new check: the stale
  policy decision returned **200 APPROVED** after the newer lock, where the regression requires
  409. With the check enabled, all three real PostgreSQL race cases passed. An earlier observation
  without a waiver proved lack of waiting but the ordinary pending gate still prevented locking;
  it is not evidence of a completed inconsistent lock.
- Actual verification: **26 policy and PostgreSQL window/race tests passed**, including the three
  new cases; **267 architecture tests passed**. Mypy passed both changed source files; Ruff
  lint/format and whitespace checks passed. These are targeted checks, not full-backend evidence.
- The economic treatment of FX classification transitions remains pending independent accounting
  review; public POL-163 authoring stays disabled. Repository completion only; no deployment.

## First-calculation RPO timing investigation — October 8, 2026

- Reproduced B4-2 on f3c48c4 through real event submission, independent approval and
  the report API: January NEW_CONTRACTS is 80,150 instead of 80,000 when initial
  activation and a March 150 usage fee are first computed together. **One failed
  in 11.20 seconds**; local log `/private/tmp/rpo-first-calculation-baseline.log`.
- A working-tree repair adds period/state realized-allocation trace evidence, a dated
  reader and independent realized-fee movement attribution. **262 recognition,
  disclosure and trace tests passed in 96.04 seconds**; **79 reader/version-chain
  tests passed in 0.97 seconds**. These are local, uncommitted-source results.
- The API rerun has **five passed, one failed in 35.29 seconds**. Correcting earlier
  allocation exposes the future revenue schedule's inclusion of the later fee:
  `ScheduleUnreadable` refuses the inconsistent schedule. The repair is NOT published
  or complete. Do not remove this guard or plug unexplained differences. Next: carry
  the engine's fixed/realized revenue decomposition into dated schedule placement,
  then verify both report totals/tie-outs and the revenue waterfall.
- Detailed evidence and remaining implementation cautions are in the RPO release note.
  Preserved the pending source/test edits in the local checkout; publish only verified
  repairs directly to main. Archived older policy-lock evidence verbatim. No deployment.
  Property session 52175 is still live on its original immutable 37c4f0c context;
  it has reached P11, and cannot verify these later source changes.

## API RPO usage attribution repair — October 8, 2026

- Continued from clean ada7213. Unit counterexamples: **three failed, one passed in
  0.43 seconds**. Valid PostgreSQL baseline: **one failed in 11.49 seconds**, after fixing
  the test's initial Money payload validation error. The report omitted a 150 usage addition.
- Added USAGE_REPORTED to variable-consideration activity (also the royalty-statement event).
  Existing obligations with zero allocation no longer become new contracts on their first fee.
  Unknown or competing cause classes stay unexplained; no arbitrary alphabetic attribution.
- **18 unit tests passed in 0.40 seconds**; expanded PostgreSQL RPO/disaggregation and unit
  version-chain checks: **32 passed in 61.81 seconds**. Real event submission/independent
  approval and report API verify the 150 addition, matching revenue, unchanged RPO and both
  tie-outs. Mypy, Ruff and whitespace pass. Detailed logs are in the RPO evidence note.
- B4-2 remains partial: first-version batching, multi-cause decomposition, API royalties,
  combined edge cases and release cut/replays remain. Archived corpus evidence verbatim.
  Property session 52175 continues against its original pre-repair revision. No deployment
  or production-readiness claim; direct publication to main.

## Engine RPO realized allocation repair — October 8, 2026

- Regressions reproduced both B4-2 cases: **two failed in 0.23 seconds**. Shared the
  recognition stage's realized-allocation reader with disclosures at the revenue period cuts.
  RPO closing includes realized usage/royalty allocation; its movement enters variable
  consideration, without plugging unexplained differences or double-counting Step-1 entry.
- Mixed fixed/usage closing is now 9,000 rather than 8,850; pure usage gets the 150 addition.
  Holds retain unrealized revenue in RPO. Added royalty-guarantee, delayed satisfaction and
  downward-correction checks. Initial disclosure/deterministic suite: **77 passed**; royalty
  module: **13 passed**; expanded recognition/disclosure and architecture: **268 passed in
  79.77 seconds**; final usage/hold/Step-1 matrix: **six passed in 0.24 seconds**.
  Mypy, Ruff and whitespace pass. Detailed scope and logs are in the RPO evidence note.
- B4-2 remains partially open: API attribution, combined lifecycle/exemption/calendar matrix,
  engine 0.4.0 cut and replays still required. Historical outputs unchanged; no deployment or
  readiness claim. Property session 52175 remains active on its original pre-repair revision.

## Older backend baseline completed — October 7, 2026

- PID 36126 is terminal and absent. The uninterrupted isolated run on revision 7c9b22d
  ended with **51 failed, 9,970 passed, 1 skipped, 640 deselected, 3 xfailed in 3h46m**.
  See docs/release/BACKEND-BASELINE-2026-10-07.md for the complete failure inventory and
  local evidence paths. No reset/restart occurred. This older run does not verify current main.
- Next: compare failures with current code, rerun scoped cases, and classify from evidence.
  Monetary import reconciliation and independent accounting sign-off remain outstanding.

## FX transition refusal and close-policy inputs — October 7, 2026

- PR #7 merged into main (`dc1c116`). Current work continues from that revision; no deployment.
- Added the missing functional-layer validation before a calculation can emit output. A fully
  consumed layer must carry zero; an open historical contract-liability layer must carry its
  remaining original historical basis. Positive and negative residues, partial releases and no
  release all refuse with the layer, period and expected/actual amounts identified.
- The reproduced monetary-to-historical defect is now blocked, **not implemented as a supported
  transition**. A PostgreSQL regression verifies the refused recomputation leaves the previous
  calculation head and journal lines intact and keeps the group dirty. Public POL-163 authoring
  remains disabled pending reviewed transition treatment and remaining approval/close validation.
- Close-run policy digests now include effective contract exceptions through the same period-scoped
  resolver used by bundles, under tenant scope. Drafts, same-value approvals, approvals after the
  entity-local period end and IFRS-forced treatment do not alter the digest. Existing digests are
  unchanged when no exception differs from the entity default.
- A real database close job records the old inputs, an effective approval makes its gate fail,
  and the next close job recomputes and records the new inputs. The prior period remains valid;
  the asset-position fixture needs no monetary adjustment or duplicate journal. Approval/lock
  concurrency still needs focused review; these tests do not certify the whole close workflow.
- Actual verification: **578 FX engine, posting, property and architecture tests passed**;
  **22 database and close-input unit tests passed**. Mypy passed both source files. Ruff lint,
  formatting and whitespace checks passed. No full-backend or production-readiness claim.
- Added `docs/release/ACCOUNTING-REVIEW.md` with the measured case, required decisions about
  correction versus a change in refund rights, economic timing, basis/rates and closed periods,
  and a pending independent-sign-off record. Reviewer identity was requested; no external contact
  or accounting sign-off occurred. This packet is not an approval.
- Earlier continuation entries were moved unchanged to the dated build history to keep this
  notebook below 20 KB. Publication exclusions and PolyForm Noncommercial licensing are retained.

## Golden parity verification — October 8, 2026

- `make parity` passed on clean main 6d33ae1: 18 fixture files verified; **130 tests
  passed in 106.29 seconds**, comprising 122 golden cases and eight additional checks.
  Immutable source/context hashes and Python/Node dependency bindings remained consistent.
  Report/log hashes and scope are in docs/release/REPOSITORY-CHECKS-2026-10-08.md.
- Independent accounting approval remains pending for DEV-002, DEV-052, DEV-010,
  DEV-050 and DEV-011. No production-readiness or full-current-CI claim.
  Property session 52175 remains active; preserve the same immutable run.
- Reconfirmed the owner's direct-to-main workflow: no open GitHub PRs and only remote
  main. Future verified changes go directly to main unless protection requires a PR;
  merge required PRs after checks and remove merged branches. No deployment.

## Batched amendment and usage attribution — October 8, 2026

- Continued from clean 9b199bb. A version-chain counterexample exposed a remaining B4-2
  attribution defect: the report separately identified 150 of realized usage but left the
  accompanying +200 or -200 fixed amendment unexplained because USAGE_REPORTED still
  counted as a competing fixed cause. Baseline: **four failed, 21 passed in 0.51 seconds**.
- Where the trace independently identifies realization, usage/royalty statements are now
  removed from the fixed-allocation cause set. The known amendment reaches MODIFICATIONS;
  usage stays in VC_ESTIMATE_CHANGES. Multiple remaining fixed cause classes and unsupported
  fixed changes stay unexplained. Legacy traces keep their prior behavior; no fee is inferred.
- **97 reader/version-chain units passed in 1.04 seconds**, including ten signed/ambiguous
  combinations; **15 PostgreSQL RPO/disaggregation/API checks passed in 62.60 seconds**.
  Mypy, Ruff and whitespace pass. The batched amendment itself is a version-chain witness,
  not a new end-to-end modification-approval claim. Detailed logs are in the RPO release note.
- The initial zero-net ordinary-usage hypothesis was not established through a valid API
  event: rated usage amounts are nonnegative. No invalid negative-fee fixture was introduced.
  That separate edge case remains unverified. Full fixed multi-cause decomposition and the
  other B4-2, release-gate and independent accounting-review blockers remain open.
  Publish verified changes directly to main; no PR, deployment or readiness claim.

## Dated RPO allocation and schedule repair — October 8, 2026

- Continued from fa1db7f and the retained failing first-computation regression. January
  now keeps its 80,000 fixed allocation when first calculated with a March 150 usage fee.
  Dated realization evidence adjusts the earlier remainder; engine component projections
  keep future fees out of the fixed schedule in both RPO and the revenue waterfall.
- Report cells link to the fixed-component amount actually displayed. Explain retains the
  original line and component inputs, with dedicated formula/narrative identifiers. Explicit
  no-fee states are distinct from absent legacy history; incomplete evidence, missing
  projections and mixed legacy/detailed chains are refused rather than assumed or scaled.
- **614 engine/kernel/reader/report-unit/explanation tests passed in 104.76 seconds**;
  **19 PostgreSQL report/usage/explanation/access-scope tests passed in 89.48 seconds**.
  The API witness includes a real January journal, waterfall tie-out and all RPO explanation
  links. An earlier failure was a missing journal in the new test fixture; supplied the
  journal through the normal API and retained the comparison. Ten-source mypy, Ruff and
  whitespace pass. See the RPO release note for exact scope and local logs.
- B4-2 remains partial: fixed multi-cause decomposition, adjustment/hold/Step-1 projections,
  zero-net omitted schedule lines, legacy replay handling and the combined lifecycle,
  exemption/calendar/royalty matrix still need work. Corrected stale C-4 cause-map status.
  Trace changes require the pending 0.4.0 cut/replays; historical traces are immutable.
  No full current backend/CI or production-readiness claim. No deployment; publish to main.

## Journal fixture validation evidence — October 8, 2026

- Continued from clean d09aefa. Reproduced the journal-audit fixture failure: **one failed,
  two passed in 0.64 seconds**. The real producer includes `validation_execution_id`;
  the fixture's audit omitted it. No production expectation was removed or skipped.
- The fixture now validates its stored, unaggregated journal lines with the production
  account/entity/dimension/currency/FX validator, writes CTL-020 evidence and links its
  audit to that actual ID. Evidence explicitly identifies the seeded journal-line population.
  The acknowledged-run helper creates, validates and audits in one transaction; migrated
  its twelve callers out of the old split transaction arrangement.
- Two initial database witnesses pass: a valid fixture has correctly scoped linked evidence;
  an inactive account emits neither success evidence nor a calculation audit. Added an
  atomic rollback witness for invalid newly created fixture rows. All **421 close-unit tests
  passed in 1.42 seconds**. Broader lock/reopen/waiver/file/audit validation: **154 passed,
  one failed in 542.45 seconds**; the CTL-038 command-route walk passed.
- The remaining failure also reproduces on unchanged d09aefa (**one failed, 22.70 seconds**):
  a reopened-period test tried to relock with an OPEN LATE_EVENT. Added the actual exception
  waiver request/reviewer approval and retained both refusal and successful relock assertions.
  Final close-run suite: **18 passed in 148.97 seconds**, including that corrected case.
  Logs: `/private/tmp/recon-audit-fixture-{baseline,evidence,units,domain}.log` and
  `/private/tmp/recon-audit-relock-{baseline,fixed}.log`. All processes are terminal.
- Ruff lint/format and whitespace checks pass. No tests were skipped or expectations relaxed.
  These are scoped results, not a full-current backend/CI or canonical control-gate rerun.
- This repairs verification infrastructure, not a production calculation behavior. Preserve
  historical gate dates, publication exclusions and noncommercial licensing. No deployment.

## Exact reconciliation freshness — October 8, 2026

- Continued from 364ba52. The new PostgreSQL/API witness publishes a different contract
  liability account mapping after both January reconciliations are reviewed. Ledger chain
  position and document counts do not move. The old gate incorrectly passes: baseline
  **one failed in 11.38 seconds** (`/private/tmp/recon-role-freshness-baseline.log`).
- Shared the existing attachment balance readers with the gate, without a runtime circular
  import or a second accounting derivation. The gate, blocker count and reviewed KPI compare
  all three role amounts, account membership and not-stated reasons/contracts against signed
  totals. Decimal precision is retained; omitted zero rows preserve the comparison's semantics.
- **72 PostgreSQL reconciliation/gate/lock checks passed in 227.16 seconds**. The extended
  API witness also verifies the lock request is refused, then regeneration/preparation/review
  restores the gate: **one passed in 12.65 seconds**. Ten new precision/basis units pass.
- The final close-unit run has **420 passed, one failed in 1.74 seconds**: the unchanged
  producer/fixture audit-key test finds `validation_execution_id` absent from the close-world
  fixture. Repair that fixture/evidence gap next; no full unit-suite pass is claimed.
  Three-source mypy, Ruff and whitespace pass. See
  [dated evidence](docs/release/RECONCILIATION-ROLE-FRESHNESS-2026-10-08.md).
- Preserve publication exclusions, PolyForm Noncommercial licensing and direct-main workflow.
  No deployment or readiness claim; independent accounting review and other release gaps remain.

## Evidence-pack request contract — October 8, 2026 (RPS-16 continued)

- Continued from clean 4860217. Verified zero open PRs and only remote `main`.
  Added API-S-EvidencePackCreate as a discriminated request union for CLOSE,
  CONTRACT_SAMPLE, CHANGE and ACCESS. Each kind requires exactly its documented
  selectors; unrelated fields (including explicit nulls) are rejected. Sample selection
  preserves exact business keys and order, rejects blank/duplicate IDs and enforces 1–50.
  Change ranges permit one day and reject reversed dates. No default lock/book/date.
- **151 request/archive unit tests passed in 0.17 seconds** (102 request, 49 archive),
  including the required/unused-field matrix, JSON round trips and schema requirements.
  Log: `/private/tmp/evidence-request-units.log`. Mypy on the new schema, Ruff and whitespace
  checks pass. Initial request run: 13 failed, 89 passed because the test fixture used
  nonexistent book `PRIMARY`; corrected it to the actual E-02 code `ASC606`.
- Request shape is now available for the forthcoming routes; this does not verify source
  selection, permissions, HTTP behavior or generation. Next: resolve each selector within
  tenant and permission scope, bind the generation cutoff/source identities, and implement
  complete source collection, jobs, audited downloads, automatic lock/re-lock packs and
  the specified acceptance tests. Keep EVIDENCE_PACK pending and CTL-041 open until then.
  Full-current release gates and independent accounting sign-off remain outstanding.

## Evidence pack integrity foundation — October 8, 2026 (RPS-16 in progress)

- Continued from clean 8a8cdda. RPS-16 / CTL-041 remains unimplemented at the workflow level.
  Started its required archive boundary: deterministic ZIP bytes, canonical payload manifest,
  exact byte counts/report-run IDs, SHA-256 and verification against the separately stored
  trusted manifest hash. The manifest cannot hash itself; clarified the existing detached
  `manifest_sha256` contract in T-RPT-04 and the build acceptance wording.
- `reports/evidence_archive.py` rejects changed/missing/unlisted payloads, altered manifests,
  self-references, duplicates, file/directory and case collisions, unsafe paths, symlinks,
  invalid metadata and over-limit payloads. No filesystem extraction or accounting derivation.
  Export sanitization and authorization remain the caller's responsibilities.
- **49 pure integrity tests passed in 0.11 seconds**; independent ZIP reads recompute payload
  hashes, and tampering/reforging is refused against the trusted hash. Mypy, Ruff and whitespace
  pass. Log: `/private/tmp/evidence-archive-units-final.log`. An earlier command named a
  nonexistent output-test file and collected no tests; the recorded final command is the real run.
- Continue the full RPS-16 workflow next: scoped request schemas/routes, job lifecycle, source
  collection, immutable/as-of reads, encrypted file storage, audited download, automatic lock
  enqueue and re-lock diff, and contract-sample/change/access packs. Use the archive boundary
  in that implementation. Keep EVIDENCE_PACK pending and CTL-041 unclaimed until full tests pass.
  Existing `locked.locked_dataset` verifies frozen bytes; CSV export must use the declared-kind
  formula guard (`locked.export_csv` / snapshot column kinds), not serve raw frozen CSV.
- This is a tested prerequisite, not an available evidence-pack product or readiness claim.
  No deployment; publish reviewed work directly to main. Remaining accounting sign-off and
  full-current verification requirements are unchanged.

## Evidence-pack source selection — October 8, 2026 (RPS-16 continued)

- Continued from clean db1e96f. Added `reports/evidence_selection.py`: resolves complete
  contract samples in submitted order, captures tenant/entity/contract identities and the
  request cutoff, and binds CLOSE to the exact lock/entity/book/period and stored freeze cutoff.
  REOPEN and PERMANENT_LOCK records are refused because they freeze no datasets.
- Selection intersects `report.run` and `audit.read` scopes with transaction RLS. Missing
  permission/scope grants do not become wildcards; SYSTEM has no implicit generation access.
  A missing or hidden sample member refuses the whole sample without naming hidden records.
  A hidden lock is refused before describing its kind or mismatched selectors. CHANGE/ACCESS
  bind the visible entity population for their future collectors.
- **160 tests passed in 17.52 seconds**: nine PostgreSQL/RLS selection cases, 102 request-schema
  tests and 49 archive tests. Same contract key in two tenants resolves only the caller's row;
  role-scope union does not widen report/audit access. Test rows are seeded; no real close or
  full pack is claimed. Log: `/private/tmp/evidence-selection-final.log`. Two-source mypy,
  Ruff and whitespace pass. Initial DB run had nine fixture errors from a missing REOPEN
  reason; corrected the fixture, then nine DB tests passed in 17.38 seconds before the
  stronger cross-tenant case and final combined run. All processes are terminal.
- Next integrate selection with audited command guards, persisted scope/cutoff, complete
  source collection, jobs and files, download reauthorization/audit, automatic lock/re-lock
  packs and the specified end-to-end acceptance. Selection alone does not authorize every
  payload or establish as-of content completeness. EVIDENCE_PACK remains pending, CTL-041
  open, report availability unchanged. Full-current gates and independent accounting sign-off
  remain outstanding. Archived the fixture/freshness notes verbatim to the build history.

## Frozen close-pack sources — October 8, 2026 (RPS-16 continued)

- Continued from clean 9c18557. Added `reports/evidence_close.py::collect_locked` for the
  frozen-source portion of CLOSE packs: certification, lock/snapshot identities and all twelve
  frozen CSV datasets. Rechecks the selected lock and current permissions before opening files.
  Requires all E-64 kinds and verifies their combined manifest against the selected lock;
  existing as-locked readers verify each file hash, row count and row-key presence.
- CSV output uses the existing declared-column formula guard. Snapshot metadata retains both
  original `file_sha256` and delivered `export_sha256`, actual source IDs and nullable source
  report-run IDs; it invents no run. Missing/inconsistent sources never fall back to live data.
- Real twelve-kind producer/encrypted-store witness: **one passed in 8.14 seconds**. Final
  selection/collector/schema/archive run: **168 passed in 28.88 seconds**. Includes missing
  kind, aggregate/file hash, row-count and row-key refusals; altered selection and revoked
  access; adversarial text escaped while negative numeric money remains numeric. The latter
  uses explicitly injected fixture CSV cells, not an accounting expectation. Locks are seeded,
  not approved close decisions. Logs: `/private/tmp/evidence-close-{producer,final}.log`.
  Source mypy, Ruff and whitespace pass. All processes are terminal.
- This collector is not a full CLOSE pack. Next add batch register/reconciliation signoffs,
  SSP/config/late-entry registers, period-end access evidence, audit-chain digest and re-lock
  comparison, then connect persisted selection, jobs/routes/files and audited downloads.
  CONTRACT_SAMPLE/CHANGE/ACCESS collection and all complete-pack acceptance remain required.
  EVIDENCE_PACK stays pending, CTL-041 open. Full-current gates and accounting sign-off remain
  outstanding. No deployment; preserve exclusions and publish validated work to main.

## Automatic reconciliation evidence — October 8, 2026 (RPS-16 continued)

- Continued from 292b80e. Added a database collector witness using API-published
  AUTO-REC-01, generated AUTO_CERTIFIED reconciliation and its actual CTL-026 record.
  Produces/stores all twelve frozen datasets, binds certification through domain writers,
  and verifies exported control/rule/version IDs, the 15,000.00 billing amount, population
  and repeated-byte stability. Lock approval is seeded and read permissions explicit;
  this is not the full approval or pack HTTP/download workflow and does not claim CTL-041.
- Initial run failed because the test helper did not select the control execution ID.
  Added that projection; final affected GL/billing reconciliation, source-selection and
  certification-proof regression run: **78 passed in 134.88 seconds**. Log:
  `/private/tmp/evidence-auto-final.log`; initial: `/private/tmp/evidence-auto-db.log`.
  Ruff lint/format and whitespace pass; process is terminal. No application source changed.
- Archived source-selection notes verbatim to keep this notebook below 20 KB. Full pack
  population/waiver assembly, supporting registers, other kinds, jobs/routes, audited
  downloads and automatic generation remain open, along with release gates and independent
  accounting sign-off. No deployment; publish directly to main without a PR.

## Stored re-lock evidence — October 8, 2026 (RPS-16 continued)

- Continued from clean 60e2de1. Shared verified frozen-source reads with a new re-lock
  collector. Follows LOCK → REOPEN history back to the prior LOCK within the same tenant,
  entity, book and period; refuses cycles, broken/out-of-scope history and missing comparisons.
  Verifies both twelve-kind frozen sources, file purpose/type/length/hash and the entire saved
  comparison against the existing CLO-7 comparator over those bytes. Delivers the original
  file and bound lock/manifest/file identities under `relock/`; never silently repairs evidence.
- **182 tests passed in 52.05 seconds**: selection/collector/schema/archive cases plus the
  existing approval-driven close/reopen/re-lock scenario, now also consuming the real stored
  comparison with this collector. Pack HTTP authorization/download are not exercised; the
  collector uses an explicit read principal. Other new lock-history cases use seeded rows.
  Initial DB run: 29 passed, one fixture failure (JSON incorrectly supplied as IMPORT_SOURCE).
  Corrected the wrong-purpose witness to a valid generated AUDIT_DIGEST file, still refused by
  the collector as intended. Logs: `/private/tmp/evidence-relock-{db,final}.log`.
- Two-source mypy, Ruff and whitespace pass. Processes are terminal. Archived request-schema
  and archive-foundation notes verbatim in the build history to retain the notebook size limit.
- Remaining: the separate `variance_between_closes` report, all other CLOSE supporting
  contents, full CONTRACT_SAMPLE/CHANGE/ACCESS collection, persisted bindings, jobs/routes,
  audited downloads and automatic pack generation. Stored comparison evidence does not replace
  that broader report. EVIDENCE_PACK stays pending and CTL-041 remains open. Full-current gates
  and independent accounting sign-off remain outstanding. No deployment; direct-main workflow.

## Reconciliation evidence — October 8, 2026 (RPS-16 continued)

- Continued from clean f147e9e. Added the CLOSE reconciliation collector, selecting the
  write-once `period_lock_id` population rather than current generations. Reuses the production
  signing snapshot; verifies distinct preparer/reviewer IDs, subject hashes and chronology.
  Auto-certified rows require matching CTL-026 success evidence and rule/version IDs instead
  of human signatures. Exports the certified statement, evidence and actual population index.
- Adds `contract.read` checks for both the parent entity and every referenced contract in
  items/not-stated totals. Hidden references refuse the entire export; redacting would break
  its signature. A reopen and a newer generation leave historical exported bytes unchanged.
- **210 scoped regression tests passed in 54.98 seconds**, including the real-signature
  database witness and 27 pure certification-proof checks. Extended the database witness to
  both reference locations: **two passed in 11.55 seconds**. Prepare/review use real API/MFA;
  lock/certification transitions and cross-entity source references are explicitly seeded.
  Auto-certification proof has unit coverage; its complete database/pack witness remains open.
  Logs: `/private/tmp/evidence-recon-scoped-final.log`, `evidence-recon-reference-cases.log`.
  An initial database attempt failed from a missing fixture `set_values` argument; corrected.
  Two-source mypy, Ruff and whitespace pass. All processes are terminal.
- Remaining: full population/waiver assembly, batch and supporting registers, access/audit
  evidence, variance report, other pack kinds, persisted bindings, jobs/routes, audited
  downloads and automatic generation. An empty index states the actual bound population,
  not completeness. EVIDENCE_PACK stays pending and CTL-041 open. Full-current release gates
  and independent accounting sign-off remain outstanding. No deployment; direct-main workflow.

## Saved certification evidence — October 8, 2026 (RPS-16 continued)

- Continued from clean 3c09d36. Added `reports/evidence_certification.py`: checks the
  historical lock's complete canonical gate population through existing close-domain rules,
  rejects uncleared/nonwaivable gates, invalid chronology and unbound/outgrown count waivers.
  Collects actual lock and checklist-waiver approval requests plus their recorded decisions
  into `lock/approvals.json`; verifies subject/entity/time/hash correspondence. Does not rerun
  today's gates or use current checklist status/result as historical evidence.
- **85 scoped tests passed in 62.00 seconds** (new parser refusals, existing certification
  rules, real lock/waiver and reopen/re-lock approvals, source-selection/collector regressions).
  Extended actual approval witnesses: **two passed in 16.50 seconds**, including prior-lock
  approval selection after re-lock and missing/wrong-subject/wrong-entity/late approval refusal.
  Waiver witness retains approved count 2 versus lock-time count 1 and actual decision ID/hash.
  Existing setup seeds journal/reconciliation signals; approvals use the real workflow and
  collection an explicit read principal. This is not complete-pack HTTP/download evidence.
- Initial re-lock collector witness: one passed in 11.06 seconds. Logs:
  `/private/tmp/evidence-certification-{db,final,history}.log`. Source mypy, Ruff lint/format
  and whitespace pass; all processes terminal. Archived frozen-source notes verbatim.
- Remaining: journal batch register and balancing details, reconciliation population/waiver
  completeness, other supporting registers/access/audit evidence, other pack kinds, persisted
  generation/jobs/routes/downloads. Assembly must invoke this verification; no pack endpoint
  is enabled and RPS-16/CTL-041 remain open. Final release gates and independent accounting
  sign-off remain outstanding. Direct-main publication; no deployment.

## Historical journal batch register — October 8, 2026 (RPS-16 continued)

- Continued from clean c27d724. Added `reports/evidence_journals.py`, collecting the
  selected lock's journal runs/batches at its cutoff and verifying them against the frozen
  JE population. Reuses the report's historical run-state reader; ignores later runs and
  excludes cancelled-at-cutoff runs. Checks each batch's line count, transaction/functional
  currencies, amounts and balancing, then ties batches to run totals/counts. Empty batches
  remain explicit. Records snapshot identity/hash and saved JE_BALANCED/JE_COMPLETE results;
  does not recompute completeness over today's ledger or export mutable delivery attempts.
- Requires parent `contract.read` as the journal routes do, plus report/audit selection checks.
  Missing/duplicate/unknown batches or frozen lines, invalid amounts, scope/state/currency
  mismatches and failed balancing refuse collection. The complete saved gate set is checked;
  assembly must also collect/verify lock approvals through the previous collector.
- **105 scoped tests passed in 53.96 seconds**: source/frozen collectors, existing export
  producers and historical-state tests, nineteen new batch comparison cases, saved-gate
  validation. Database witness uses seeded journal/certification rows and the real twelve-kind
  snapshot producer/store; checks nonempty figures, later-run exclusion and permission refusals.
  Full operational journal calculation/close and pack HTTP/download acceptance remain open.
- Initial DB attempt failed because the fixture queried after its tenant session commit;
  corrected the ordering. Next run: 19 passed, one assertion failure because scoped denial is
  deliberately not-found rather than forbidden; corrected to each guard's exact contract.
  Logs: `/private/tmp/evidence-journals-{db,corrected,final}.log`. Source mypy, Ruff lint/format,
  whitespace pass; all processes terminal. Archived automatic-reconciliation and re-lock notes verbatim.
- Remaining: reconciliation population/waiver completeness, supporting SSP/configuration/late
  entry/access/audit evidence, other pack kinds, persisted generation/jobs/routes/downloads
  and automatic generation. RPS-16/CTL-041 and final release gates/accounting sign-off remain
  open. Direct-main publication with no deployment; exclusions/noncommercial license retained.

## Saved supporting-report evidence — October 8, 2026 (RPS-16 continued)

- Continued from clean 628ee14. The SSP/configuration/late-entry/access/SoD report builders
  already exist. Added `reports/evidence_reports.py` to collect their successful saved CSVs,
  IPE manifests and source identities. Explicit source bindings require exact report code,
  normalized parameter hash, entity population, book, as-of date and known-at cutoff; no
  rerendering, implicit latest-run selection or fallback to current data.
- Reuses the report framework's export visibility and underlying report permissions. Checks
  original output/manifest purpose, type, size and hashes; checks canonical manifest against
  run identity/version, parameters, count, totals, tie-outs and output bytes. Uses only fixed
  admitted payload paths. Source metadata preserves actual run/file IDs and both hashes.
- All five actual report API/worker witnesses initially passed in **29.91 seconds**, including
  a nonempty access listing. Broader regression: **75 passed, three failed in 99.18 seconds**;
  all failures were the new missing-audit-permission assertions expecting not-found where
  the existing guard returns forbidden (permission removed, scope entry retained). Corrected
  those expectations; final affected report witnesses and pure checks: **38 passed in 29.88
  seconds**. Each collected CSV/manifest matches the ordinary HTTP download byte for byte.
  Covers changed cutoff, export removal/scope denial, underlying permission removal, invalid
  binding/manifest and changed-output refusals. Logs: `/private/tmp/evidence-reports-{db,final,
  corrected}.log`. Source mypy, Ruff lint/format and whitespace pass; all processes terminal.
- These witnesses bind to the actual generated report parameters, not a claimed full-close
  selection. Pack orchestration still must choose the correct close-period dates/cutoff,
  create and persist these run bindings, and invoke all collectors. Reconciliation population
  completeness, other pack kinds, assembly/jobs/routes/audited downloads/automatic generation
  and final release/accounting approval remain open. RPS-16/CTL-041 unclaimed. Archived saved
  certification notes verbatim. Direct-main publication; no deployment or external messaging.

## Audit digest evidence — October 8, 2026 (RPS-16 continued)

- Continued from clean 90871f4. Added `reports/evidence_audit.py`, requiring an explicit
  verification ID rather than selecting latest on every read. Checks the original stored
  AUDIT_DIGEST file's purpose/type/length/hash and exact canonical metadata against its
  successful complete-prefix verification row. The prefix must cover the lock's audit head.
  Rechecks HMACs through the recorded endpoint and matches the lock's saved head; a shorter
  intact prefix is insufficient. Returns original digest bytes and source IDs/hashes.
- Collection is read-only and exposes aggregate verification metadata, not audit-event
  contents. It creates no verification or external retained copy. Future pack orchestration
  must persist the chosen verification ID, alongside its other source bindings.
- **71 scoped tests passed in 61.84 seconds**: digest refusals, source/frozen collectors and
  existing audit-verification regression tests. Database cases use actual audit events/HMACs,
  verification writer and encrypted digest files with seeded close/snapshot references.
  Rejects a mismatched lock head, an overstated prefix endpoint, wrong digest metadata and
  wrong file purpose; refuses missing verification IDs and revoked audit permission.
  Another real verification extends the chain without changing the originally selected bytes.
- Initial two database witnesses passed in 9.93 seconds. Logs:
  `/private/tmp/evidence-audit-{db,final}.log`. Source mypy, Ruff lint/format and whitespace
  pass; all processes terminal. Archived earlier reconciliation notes verbatim.
- Remaining: reconciliation population/waiver completeness, supporting SSP/configuration/late
  entry/access reports, other pack kinds, persisted source bindings, full assembly, jobs/routes,
  audited downloads and automatic generation. Operational close/full-pack acceptance, current
  release gates and independent accounting sign-off remain open. RPS-16/CTL-041 unclaimed.
  Direct-main publication; no deployment, cloud mutation or external notifications.

## Close supporting-source plan — October 8, 2026 (RPS-16 continued)

- Continued from clean 277408a. Added `reports/evidence_report_plan.py`: derives five CSV
  source requests from the selected lock and its fiscal period. SSP/configuration use the
  full inclusive period date range; late-entry uses the selected entity/book/period. Access
  and SoD use UTC period-end (23:59:59.999999), consistent with the register framework's
  UTC-day date-range convention. All known-at values are the lock's freeze cutoff, not now.
- Refuses early closes that cannot supply period-end access evidence, invalid intervals,
  naive cutoffs and period records changed after the lock (no versioned period-date history).
  Queues through ordinary report creation/permissions and captures normalized selectors,
  scope and cutoff in source bindings, refusing normalization that changes scope/cutoff.
  Does not commit; the future pack command must persist bindings atomically and reuse on retry.
- Initial database witness: **one passed in 8.58 seconds**. Selected seeded January lock →
  five actual report jobs → worker execution → collection of all fifteen original files.
  Final source/collector/selector regression: **82 passed in 65.76 seconds**. Covers leap-year
  and non-calendar fiscal intervals, UTC offset normalization, re-lock cutoff changes, early
  close/changed-period refusal and export denial with no report rows left. Logs:
  `/private/tmp/evidence-plan-{db,final}.log`. Source mypy, Ruff lint/format and whitespace pass;
  all processes terminal. Historical journal-register notes archived verbatim.
- Remaining: durable pack state/idempotency and source bindings, reconciliation population
  completeness, other pack kinds, complete assembly/jobs/routes/audited downloads and automatic
  close generation. Existing builders still refuse historical mutable facts they cannot prove;
  this planner never substitutes current data. End-to-end operational close acceptance,
  current release gates and independent accounting sign-off remain open. RPS-16/CTL-041
  unclaimed. Direct-main publication; no deployment, cloud mutation or external notifications.

## Canonical property gate completed — October 8, 2026

- Preserved session 52175 completed successfully: **48 passed, zero failed/skipped in
  5899.78 seconds (1:38:19)**; `make properties` exit 0. This was the thorough run on
  clean captured 37c4f0c48918a8a72228bbc596061ecfd12f9e99, not the later RPO source.
- Verified immutable source/context start/end bindings and Python/Node dependency bindings;
  no mismatches. Captured tree matches that Git commit. Report/log hashes are recorded in
  REPOSITORY-CHECKS-2026-10-08.md. The process is terminal; no unfinished property run remains.
- Archived the preceding RPO investigation/repair notes verbatim. Full accounting corpus
  failures, control-gate gaps, other product gaps and independent accounting sign-off remain.

## Control verification and relock witness — October 8, 2026

- Started canonical `make controls-report` on clean main 68d9607. It remains active in
  .run/gates/ctx-controls-report-68d960754ea2-9993, executor **36008**, PID **10033**;
  log /private/tmp/erev-controls-2026-10-08.log. Collection confirms 495 tagged tests.
  One relock test has failed so far. Keep polling this immutable run; no final G7 claim.
- Reproduced the relock failure on a separate disposable local database, preserving the
  control gate's primary database. Initial setup failed because the new database inherited
  SQL_ASCII; recreated that empty database with UTF8. Actual baseline: **one failed in
  18.32 seconds**. Backdated progress follows a later reviewed judgement, raises LATE_EVENT
  / OUT_OF_ORDER, and the open exception correctly prevents relock.
- Updated the two reopened-period witnesses to assert the exception gate refusal, inspect
  the exact findings, request and independently approve their waivers through the API, and
  verify retained waiver evidence. All **three journal-chain tests passed in 42.13 seconds**.
  Ruff lint/format and whitespace pass. No application control was weakened; per-posting
  approval and the zero-net journal gap remain open. Log hashes are in the dated checks note.
- Diagnostic process is terminal and its database removed. Property session **52175** / PID
  **6358** remains active in the original context, past all six metamorphic tests and through
  RPO checks, now in determinism. Both ongoing gates predate this test correction; preserve
  their handles and inspect final source bindings. No deployment or readiness claim.

## Control gate result and RPO closing defect — October 8, 2026

- Completed the preserved control gate on immutable 68d9607: **494 passed, one failed,
  10,483 deselected in 820.68 seconds**. Report: 45 controls pass, CTL-018 fails, CTL-041,
  CTL-045 and CTL-048 lack evidence. The sole test failure is the relock witness already
  corrected in 7c83cb4 and verified separately. No canonical rerun/pass is claimed.
  Source/dependency bindings verify; hashes are in the dated repository-checks note.
- Measured an additional B4-2 defect on clean 7c83cb4 using real recognition and disclosure
  stages with allocated-state fixtures. A 12,000 fixed fee plus 150 March usage has 9,000
  remaining in recognition, but rollforward closing is 8,850 with zero unexplained difference.
  Pure usage produces the known 150 unexplained amount. This is engine-scoped evidence,
  not an API measurement. Recorded inputs, outputs, reproduction and full repair scope in
  docs/release/RPO-REALISED-FEES-2026-10-08.md; updated B4-2. A cause-map-only patch would
  miss the incorrect closing; dated realized allocation must also be carried into measurement.
- Control session 36008 is terminal. Property session 52175 / PID 6358 is confirmed live,
  still in determinism, in its original immutable context. Keep that run; no database test
  process is active. Archived invitation-erasure evidence verbatim. No deployment/readiness claim.

## GL reconciliation ledger-history freshness — October 8, 2026

- Continued from clean published main 8579c6b (previous turn made verified progress).
  Closed B2-8: GL reconciliation freshness now watches later seals across ledger history
  through the reconciled period end, matching the comparison's account/role population.
  An earlier-period posting invalidates review even without a reversal into the current period.
  Older rows retain timestamp fallback over the same range. Billing stays period-scoped;
  other entities/books and future periods do not invalidate either comparison.
- First regression run: **8 failed, 25 deselected in 14.32 seconds**, all fixture transition
  calls missing set_values. Corrected baseline: **6 failed, 2 passed, 25 deselected in
  15.23 seconds**: two cases reproduced the missed earlier-period posting; four were fixture
  period-state errors. Corrected fixtures and implementation: **8 passed, 25 deselected in
  13.51 seconds**. Logs: /private/tmp/reconciliation-history-{before,baseline,fixed}.log.
- Added entity isolation and unsigned-cockpit checks. Broader lock/reconciliation and query
  coverage: **48 passed in 142.38 seconds**, /private/tmp/reconciliation-history-expanded.log.
  Strengthened the matrix with amounts moved between distinct accounts: **10 passed,
  25 deselected in 15.82 seconds**, /private/tmp/reconciliation-history-final.log. All processes
  terminal. Ruff lint/format, source Mypy and whitespace checks pass. Existing concurrent
  posting/generation cases remain covered by the broad run. No current full-suite claim.
- Updated the model, B2-8 and developer guidance; archived prior repository-gate evidence
  verbatim. Exact role-balance recomparison (B1-29), volume/release checks, remaining product
  gaps and independent accounting sign-off remain open. No deployment; preserve exclusions
  and noncommercial licensing. Publish tested changes directly to main.

## Reconciliation population and retained waiver basis — October 8, 2026 (RPS-16 continued)

- Continued from clean published 4a9de2a. New checklist-waiver submission audit events retain
  the exact subject hashed by the approval request, before submission changes pending counts.
  The certification collector checks that retained document against the approved hash, gate,
  entity/book/period, reviewed count/members and the selected lock's audit prefix. Exported
  proof includes the original subject and audit event identity; later checklist state is unused.
- Added `reports/evidence_reconciliation_population.py`: resolves the reconciliation requirement
  at the lock freeze cutoff, retaining its setting source identity; enumerates only that lock's
  certified/reopened statements. Rejects duplicate kinds/IDs, wrong scope/time and unexplained
  required omissions. Approved missing/unreviewed member identities can cover absent kinds;
  an equal-count waiver of another kind or an outdated statement cannot. Omissions remain
  explicit `waived_absent_kinds`, never mislabeled as certified statements. Full assembly must
  invoke both this population reader and the existing statement/signature collector.
- Initial waiver witness: **one passed in 12.20 seconds**. Initial population/subject checks:
  **53 passed in 18.09 seconds**. Broader lock/re-lock, waiver and evidence regression:
  **149 passed in 171.95 seconds**. Extended policy-history run: **67 passed, two failed in
  18.57 seconds** because the test advanced September's frozen clock, still before the actual
  October database freeze cutoff. Corrected the fixture to publish after the recorded cutoff;
  final affected run: **69 passed in 18.51 seconds**. Covers real waiver/lock approvals,
  unchanged output after a later disabled policy, revoked scope, hash/member/scope mismatch,
  duplicate sources and explicit approved omissions. Journal/reconciliation gate setup is seeded;
  these are not complete operational close or accounting acceptance witnesses.
- Logs: `/private/tmp/waiver-basis-db.log` and `/private/tmp/waiver-population-{db,final,history,
  corrected}.log`. All processes terminal. Source Mypy, Ruff lint/format and whitespace pass.
  Saved supporting-report notes archived verbatim. No API contract or availability change.
- Legacy waiver audit events without the exact subject document cannot supply this proof;
  collection refuses rather than inventing historical details. Full pack assembly, persisted
  state/bindings/retry reuse, jobs/routes/audited downloads/automatic generation, other pack kinds
  and the separate variance-between-closes report remain open. Current release gates and
  independent accounting approval remain required; RPS-16/CTL-041 and production readiness
  are unclaimed. Validated direct-main publication; no deployment or external notifications.

## Durable completeness refusal evidence — October 8, 2026

- Continued from published main c0e4fc6. Failed JE_COMPLETE evaluations now retain CTL-019
  FAIL observations after the refused lock request or approval transaction rolls back. Evidence
  cites the existing period state, so missing journal runs are covered. The original refusal and
  pending approval remain; no period lock or business write survives. Same caller/tenant scope,
  nested refusals retained once, and evidence-write failure rolls back partial observations.
- Migration 0141 adds PERIOD_STATE and refuses downgrade while such evidence exists. Updated
  generated API types, control registry, audit classification and B1-24 guidance. Completed the
  prior currency finding's missing IMP-149 PRD catalogue row and matching architecture counts.
- Initial PostgreSQL cases: **2 passed, 21 deselected in 10.10 seconds**. Expanded lock/UOW/
  validation/all-architecture run: **329 passed, 2 failed in 203.69 seconds**; fixed missing audit
  object classification and currency catalogue drift. Final affected run: **98 passed, 1 failed
  in 85.53 seconds**; only catalogue row count remained and was corrected. Corrected catalogue/
  validation: **65 passed in 1.00 seconds**; control registry/report: **6 passed in 35.88 seconds**.
  Logs: /private/tmp/completeness-refusal-{first,expanded,final,corrected,registry}.log. All terminal.
  Coverage includes real PostgreSQL rollback, approval refusal, nested handling, migration head,
  downgrade protection and failure after evidence insert. Source Mypy, Ruff lint/format, generated
  OpenAPI, frontend tsc --noEmit and whitespace checks pass. npm run typecheck was unavailable;
  the direct TypeScript compiler check succeeded instead.
- Archived integration fallback evidence verbatim. Verified no open PRs and only remote main;
  continue tested direct-main publication. No deployment or full-suite/readiness claim. Remaining
  implementation, final release checks, engine cut/replays and independent accounting sign-off
  remain open; preserve publication exclusions and noncommercial licensing.

## First-close ZIP assembly — October 8, 2026 (RPS-16 continued)

- Continued from clean published 9fe1bd0. Added `reports/evidence_assembly.py`: reloads a
  pack's immutable source binding, reauthorizes scope/export, then invokes all frozen-close,
  certification/approval, journal, reconciliation statement/population, audit and supporting
  report readers. Includes the binding in `lock/source_binding.json`. Missing required paths,
  mismatched report populations, duplicate/unsafe files or any source refusal yield no ZIP.
- First-close output uses the deterministic archive builder and separately hashed manifest.
  Re-lock assembly explicitly refuses until the separate driver-variance report is available;
  a valid stored raw comparison alone is not substituted. This boundary creates no jobs,
  verification records or stored files and does not commit or expose an endpoint.
- Initial two database cases: **one passed, one failed in 14.26 seconds**; the assembled ZIP
  reached verification, but the new test used the wrong verifier keyword. Corrected it to
  `expected_manifest_sha256`. Final assembly/archive/close/re-lock regression:
  **79 passed in 24.33 seconds**. Actual independent waiver/lock approvals, twelve freeze
  datasets, audit digest and five report jobs feed a reproducible 36-payload ZIP. Each byte
  count/hash and source binding is checked; journal evidence is nonempty and omissions retain
  their approved identities. Journal and close-run gate setup is seeded, not full operational
  accounting acceptance. Unsigned reconciliation fixtures, pending reports, removed permissions
  and a genuine approved re-lock without its variance report all refuse assembly.
- Logs: `/private/tmp/evidence-assembly-{db,final}.log`. All processes terminal. Source Mypy,
  Ruff lint/format and whitespace pass. RPS-16/CTL-041 are unclaimed: complete job lifecycle,
  encrypted storage, creation/idempotency, audited download/API, automatic generation, other
  pack kinds and re-lock variance reporting remain open. Current release gates and independent
  accounting approval remain required. Direct-main publication; no deployment or notifications.

## Durable CLOSE source bindings — October 8, 2026 (RPS-16 continued)

- Continued from clean published a622467. Migration 0142 adds immutable
  `evidence_pack.source_binding`: an object or legacy NULL, with no UPDATE grant. DB-03
  protects it even before success; downgrade validates across all tenants and refuses to
  discard any retained binding. Existing rows are not backfilled from current sources.
- Added `reports/evidence_sources.py`. Preparation verifies an explicit audit digest, queues
  the five supporting reports through the existing planner, and returns a versioned binding
  for atomic pack insertion. It retains the request, tenant/entity/period, request/freeze
  instants, snapshot manifest, frozen run IDs, supporting run/job IDs and normalized selector
  hashes, plus the digest verification ID. Loading reauthorizes the selected close and checks
  the pack row, frozen source and report/job associations without selecting or enqueueing anew.
- Initial database witnesses: **two passed in 8.81 seconds**. Real report jobs/outputs and
  audit verification are used around a seeded close. Newer report/digest candidates do not
  replace the saved selection; repeated loads preserve output bytes. A failed enclosing pack
  transaction rolls back the pack, reports and jobs together. Legacy NULL, revoked scope,
  wrong identities/cutoffs, duplicate/missing sources and unversioned documents refuse.
- Broader source/PG/migration run: **88 passed, one failed in 82.19 seconds**. The failure found
  pre-existing out-of-period report metadata drift. Migration 0143 corrects its description
  and IPE sources for the already implemented computed late events; stored runs/outputs stay
  intact. Next run: **88 passed, one failed in 82.55 seconds** because the owner-role trigger
  test saw no tenant row under RLS. A role-switch attempt then gave **48 passed, one failed
  in 23.72 seconds** (owner cannot SET ROLE erev_app). The final fixture temporarily removes
  FORCE RLS for the table owner in a rolled-back transaction, verifies the row is visible,
  and proves the trigger refuses the mutation. **Final affected run: 49 passed in 24.25 seconds**,
  including full upgrade/downgrade/upgrade, catalogue equality, application grants, downgrade
  refusal and the extended binding/rollback witness. All processes terminal.
- Logs: `/private/tmp/evidence-binding-{db,final,corrected,verified,guards}.log`. Source/migration
  Mypy, Ruff lint/format and whitespace pass. Audit-digest and supporting-source-plan notes
  archived verbatim. Snapshot sandbox rules regenerate evidence packs/report runs instead of copying them.
- The creation command and job lifecycle/idempotency still need integration with these bindings.
  Full assembly, audited downloads/routes, automatic generation, other kinds and variance report
  remain open. Collectors must still validate output/audit bytes and export permissions. No
  pack endpoint, CTL-041, RPS-16 or production-readiness claim. Current release verification and
  independent accounting sign-off remain required. Direct main; no deployment or notifications.

## Atomic first-close retention — October 8, 2026 (RPS-16 continued)

- Continued from clean published 7f04236; previous turn closed the generic-file access bypass.
  Added `evidence_storage.finish_close`: explicitly checks evidence export/entity scope, locks
  the pack, reauthorizes and assembles all retained sources, stores encrypted ZIP output, then
  writes SUCCEEDED/file/manifest/separate hash and `evidence.finish` in the caller's transaction.
  QUEUED/FAILED and partial preexisting output refuse. SUCCEEDED repeats verify/reuse the exact
  file; hashes, metadata, canonical ZIP and freshly verified source bytes must all agree.
- Actual local database/encrypted-store witness: **2 passed in 15.04 seconds**. Rollback retains
  RUNNING with no file-object row/manifest; commit produces one file and one finish audit event;
  repeat creates neither, and each revoked source/export permission refuses. This uses the
  earlier approved-omission/seeded-journal close witness, not full operational close acceptance.
  Transaction atomicity concerns database references; object-store orphan recovery remains the
  existing file-store responsibility. No completion helper commits or exposes bytes via API.
- Broader regression: **90 passed, one failed in 16.42 seconds**; architecture correctly found
  the new evidence_pack audit object unclassified. Classified it WHERE_NAMED and explicitly
  supplied its contract_ids (empty for CLOSE, supporting future samples). Final regression:
  **99 passed in 16.45 seconds**; source Mypy, Ruff lint/format and whitespace pass. Logs:
  `/private/tmp/evidence-storage-{db,final,corrected}.log`; all processes terminal.
- Archived older control/RPO notes verbatim. Dependency scheduling, creation/idempotency,
  failure/cancellation lifecycle, download/API and export audit, automatic generation, other
  kinds and variance remain open. RPS-16/CTL-041 and production readiness remain unclaimed;
  release gates and accounting sign-off remain required. Direct main; no deployment.

## Dependency-aware queue readiness — October 8, 2026 (RPS-16 continued)

- Continued from clean published d7c27f8; previous turn retained verified first-close output.
  Added optional read-only `ready` hooks to job registration. After release/delivery fencing,
  before a slot/attempt, False keeps QUEUED and redispatches after 30 seconds with the same
  attempt/release budget. Stale/cancelled deliveries do nothing. A domain Problem settles via
  the normal terminal failure hook; unexpected reader errors preserve the queued task for
  existing stranded-task recovery. No handler attempt is spent on dependency wait.
- Added `evidence_readiness.close_ready`: checks pack/job subject identity and immutable CLOSE
  binding, then only the five bound report/run/job pairs. Pending pairs wait; missing, failed,
  cancelled or inconsistent sources refuse. This is a worker preflight, not authorization or
  evidence integrity proof; completion must still invoke the source readers and storage step.
- Queue suite **14 passed in 5.86 seconds**; source/queue/release/unit integration **30 passed in
  20.64 seconds**. Added source terminal-state fault cases, then full scoped queue, release,
  stall, cancellation API, registry and close witness: **50 passed in 23.48 seconds**. Seven
  waits preserve attempt 1 without taking a slot; stale delivery does not recheck/redispatch;
  completion runs once and produces one job.finish. Source checks use actual five report jobs;
  kernel readiness tests register probe handlers. No complete EVIDENCE_PACK handler claim.
- Logs `/private/tmp/job-readiness-{db,integrated,final}.log`; all processes terminal. Ruff,
  source Mypy and whitespace pass. Archived GL freshness notes verbatim. Pack handler wiring,
  creation/idempotency, failure/cancellation lifecycle, download/API, automatic generation,
  other kinds and variance remain open. Current release gates/accounting sign-off still needed;
  RPS-16/CTL-041 unclaimed. Direct main; no deployment or external notifications.


## Evidence-pack download boundary — October 8, 2026 (RPS-16 continued)

- Continued from clean published d558514; previous turn published verified assembly work.
  Found that generic file metadata/content routes could serve evidence-pack files under
  `evidence.export` without the pack-specific source checks and `evidence.export` audit fact.
  Reserved this purpose for API-R-42's dedicated download route, following the report/journal
  file pattern. Preserved the owner entity for destruction-scope checks. Updated the data-model
  registry and its API sweep; the dedicated pack route itself remains unimplemented.
- Two new entity/tenant-wide Auditor cases failed on the old generic route in **7.42 seconds**.
  After the repair, all file API and registry architecture tests passed: **29 in 22.33 seconds**.
  Both all-entity and scoped Auditors receive the same 404 as an unknown file for metadata and
  bytes; retained entity/whole-tenant destruction scopes are checked. Ruff lint/format, source
  Mypy and whitespace pass. Logs: `/private/tmp/evidence-file-route-{red,green}.log`.
- All processes terminal. Archived older control/relock notes verbatim. Pack lifecycle/storage,
  audited download/API, automatic generation, other kinds and variance remain open, along with
  release gates and independent accounting approval. Direct main; no deployment/readiness claim.

## First-close pack worker lifecycle — October 8, 2026 (RPS-16 continued)

- Continued from clean published 5ba0f2d; previous turn added verified dependency readiness.
  Registered `reports/evidence.py::build_pack` for EVIDENCE_PACK with the CLOSE readiness hook,
  three attempts, encrypted completion, required failure cleanup and queued cancellation.
  Uses internal SYSTEM source-reader capabilities restricted to the immutable entity; these
  grant no public caller access. Other pack kinds and re-lock variance still refuse.
- Added an optional cancellation guard under the job row lock. Completion locks job then pack:
  a pre-handler cancellation stops without output, while late cancellation after SUCCEEDED
  refuses 409. Failure cleanup requires the pack's own FAILED job/subject/params association;
  malformed foreign jobs cannot stop another pack. E-67 has no CANCELLED, so unfinished packs
  end FAILED with an evidence.stop reason; job state distinguishes failure from cancellation.
- Initial worker/registry/audit tests: **10 passed in 17.02 seconds**. Queue/release/stall/API/
  registry/close regression: **57 passed in 31.85 seconds**. Added a post-commit crash/retry
  witness: **9 passed in 23.73 seconds**; fresh QUEUED, interrupted RUNNING and retained
  SUCCEEDED completions reuse verified output, with one finish event per pack. An injected
  running cancellation produces no file; API tests cover queued and late cancellation, plus
  unsupported-kind cleanup and foreign-job isolation. Existing import cancellation/cleanup
  rollback tests: **2 passed in 24.14 seconds**. Source Mypy, Ruff lint/format, whitespace pass.
- Logs `/private/tmp/evidence-worker-{db,final,retry,cancel-regression}.log`; all terminal.
  Close witness retains seeded journal/close-run setup and approved reconciliation omissions;
  it is not full operational accounting acceptance. Archived waiver-population notes verbatim.
  Public creation/download and request idempotency, automatic enqueue/NTF-06, other kinds,
  variance, current release gates and independent accounting approval remain open. No
  RPS-16/CTL-041 or production-readiness claim. Validated direct main; no deployment.

## Atomic close-pack creation command — October 8, 2026 (RPS-16 continued)

- Continued from clean published b06824b; previous turn integrated the first-close worker.
  Added `evidence_commands.create_close`: checks caller source/export permissions and entity
  scope, refuses unsupported re-locks, validates approval/journal/reconciliation evidence as
  the caller, prepares immutable sources with an explicit completed audit verification, then
  numbers/inserts the pack and queues its worker. One transaction owns five source report
  runs, six jobs, the binding, numbering and evidence.create audit; caller owns commit.
- Creation deliberately does not choose a latest digest or create one in a separate transaction.
  The pending HTTP/idempotency boundary must orchestrate a completed verification; this internal
  argument is not a new API request field. Other pack kinds and automatic lock enqueue remain
  open. A returned JobOut describes the queued worker; no new public route was exposed.
- Initial creation/worker/audit witnesses: **6 passed in 23.46 seconds**. Final close/re-lock,
  source-binding, storage and audit-classification regression: **55 passed in 27.84 seconds**.
  Commit produces exactly one pack/five reports/six jobs, all dispatched, with source IDs in
  the create audit. Rollback restores rows and numbering. Missing or out-of-scope permissions,
  invalid verification, unsigned reconciliation fixtures and unsupported re-locks refuse.
  Existing encrypted worker/retry/cancellation checks run through command-created close packs.
- Logs `/private/tmp/evidence-create-{db,final}.log`; all processes terminal. Source Mypy,
  Ruff lint/format and whitespace pass. Archived completeness-refusal notes verbatim. The close
  witness still uses seeded journal/close-run setup and approved omissions, not full accounting
  acceptance. Public creation/download with request idempotency, verification orchestration,
  NTF-06/automatic enqueue, other kinds, variance and current release/accounting approvals
  remain open. RPS-16/CTL-041 unclaimed. Direct main; no deployment or external notifications.

## Verified close-pack read/download API — October 8, 2026 (RPS-16 continued)

- Continued from clean published caf33b7; previous turn added atomic internal pack creation.
  Added GET /evidence-packs/{id} and /download for retained CLOSE packs. Header reads expose
  status, source identities and manifest/hash, with a download href only for SUCCEEDED.
  Download rechecks current source/export permissions and entity scope, verifies original
  encrypted file metadata, ZIP/manifest and exact retained-source bytes, then commits one
  evidence.export audit before returning application/zip with attachment/sandbox/no-store.
- Split read-only retained verification from completion: a GET never finishes pending work or
  regenerates damaged output. Pending/failed downloads refuse 409; tampered bytes refuse 422.
  Source permission denials are audited; generic file routes remain closed. Creation/listing
  and other pack kinds are not exposed by this change. Updated user guide, data model and limits.
- Initial real HTTP close/download and route/audit architecture run: **17 passed in 35.57
  seconds**. Added damaged-byte injection and each source-permission scope refusal; final
  archive/storage/OpenAPI/route/audit/close regression: **83 passed in 54.79 seconds**. Two
  downloads return exact saved bytes and two export events; damage creates no export event;
  role revocation blocks header/download. The seeded-journal/approved-omission caveat remains.
- Logs `/private/tmp/evidence-download-{db,final}.log`; all processes terminal. Source Mypy,
  Ruff lint/format, whitespace, regenerated OpenAPI/client types, staleness check and frontend
  tsc --noEmit pass. Archived initial assembly notes verbatim. Public creation/listing with
  request idempotency and verification orchestration, automatic enqueue/NTF-06, other kinds,
  variance and current release/accounting approval remain open. RPS-16/CTL-041 and production
  readiness unclaimed. Direct main; no deployment or external notifications.

## Idempotent first-close creation API — October 8, 2026 (RPS-16 continued)

- Continued from clean published fbe1eaa; rechecked zero open PRs and main as the only remote
  branch. Added POST /evidence-packs with the documented discriminated selectors, 202 JobOut,
  Location and X-Erev-Evidence-Pack-Id. The command kernel stores the response atomically with
  the pack, sources, five reports, six jobs and numbering. Other kinds explicitly refuse 422.
- Creation preflights caller scope and retained evidence, then selects one completed PASS digest
  covering the frozen audit head, ordered by completion time/ID. It verifies that digest before
  queueing and persists its exact ID. Existing internal callers may still supply an explicit ID.
  A damaged selected digest refuses without older fallback; replay never reselects or queues.
  Missing verification returns actionable 422. The existing audit verify job must finish before
  a new creation key is submitted; the earlier validation response remains tied to its key.
- Initial HTTP/route regression: **14 passed in 35.07 seconds**. Expanded audit/OpenAPI/route/
  classification/close regression: **50 passed in 56.75 seconds**. Witnesses include newer digest
  after creation with unchanged replay IDs/counts, changed-body rejection, damaged digest with
  no queued effects, unsupported kind, missing verification and revoked-role replay refusal.
  Final failed-response replay extension: **3 passed in 25.32 seconds**; all processes terminal.
  The inherited close witness still has seeded journal/close-run setup and approved omissions;
  it does not establish operational CTL-041 acceptance.
- Regenerated OpenAPI/client types and updated the guide/data model/build status/limits.
  Source Mypy, Ruff lint/format, OpenAPI staleness, frontend tsc --noEmit and whitespace pass.
  Archived the older durable-source-binding section verbatim. Logs are local under
  /private/tmp/evidence-post-{db,final,retry}.log. Automatic verification orchestration, listing,
  enqueue on lock/NTF-06, other kinds, re-lock variance and current release/accounting approval
  remain open. RPS-16/CTL-041 and production readiness remain unclaimed. Direct main; no deployment.

## Scoped first-close pack register — October 8, 2026 (RPS-16 continued)

- Continued from clean published 3ceeffa. Added GET /evidence-packs with a metadata summary,
  standard keyset paging/counts, entity/book/period/kind/status filters and id/created_at/pack_no
  sorts. OpenAPI declares the filters; regenerated the API document and frontend client types.
- SQL intersects report.run, audit.read and contract.read scopes before paging/counting and
  explicitly joins tenant/entity/period identities. Only retained CLOSE bindings are admitted;
  legacy unbound/unsupported kinds are omitted. Each row must match its binding. Listing opens
  no files and makes no archive-integrity claim; individual read/download verification remains.
- Initial real HTTP/route run: **14 passed in 35.89 seconds**. Final list-kernel/OpenAPI/route/
  audit/close regression: **33 passed in 57.57 seconds**. Witnesses cover two-page traversal on
  all three sort keys (including tied timestamps), changed-filter cursor refusal, filtering,
  zero rows/counts outside each source scope, missing permissions, revoked-role HTTP refusal,
  and exclusion of seeded legacy/unsupported rows from counts. Logs:
  /private/tmp/evidence-list-{db,final}.log; all processes terminal. Source Mypy, Ruff lint/format,
  OpenAPI staleness, frontend tsc --noEmit and whitespace checks pass. Updated guide/model/limits.
- Automatic audit verification/enqueue on lock/NTF-06, other pack kinds, re-lock variance and
  current release/accounting approval remain outstanding. The inherited close fixture retains
  seeded journal/gate setup; no operational CTL-041, RPS-16 completion or production-readiness
  claim. Direct main; no deployment or external notifications.

## Stable audit verification job results — October 8, 2026 (RPS-16 prerequisite)

- Continued from clean published abc0514. Reviewed NTF-06: the existing lock notification
  truthfully promises stored snapshots; pack availability must follow successful automatic
  generation. That depends on a stable queued audit result. Found and fixed an audit worker
  retry gap: a crash after verification commit could repeat verification before job settlement.
- AUDIT_CHAIN_VERIFY now returns result.verification_id and reuses the single committed
  tenant/job/trigger result, including FAIL. It does not reverify a newer prefix, create another
  digest/control result, or notify again. Multiple retained rows or trigger mismatch refuse;
  the normal three-attempt policy remains. This proves a historical verification, not current
  chain integrity. No schema migration or public request change; JobResultOut permits this member.
- Initial audit domain/API run: **16 passed in 13.78 seconds**. Expanded ambiguous-result cases
  first had **47 passed, 4 failed in 16.10 seconds** because the test expected final failure on
  attempt two of three. Corrected the witness to fetch/run attempt three without changing the
  retry policy; final audit/API/digest/audit-classification regression: **51 passed in 16.05
  seconds**. PASS/FAIL crash cases retain exact IDs and row/file/control/notification/outbox
  counts; inconsistent cases settle FAILED without new verification. API exposes the exact ID.
- Logs /private/tmp/audit-result-{retry,final,corrected}.log; all processes terminal. Source Mypy,
  Ruff lint/format and whitespace checks pass. Updated architecture/limits and archived earlier
  retention notes verbatim. Next: bind a queued audit job in versioned pack sources, wait for
  that exact successful verification, then integrate automatic lock enqueue and availability.
  Current creation still requires a completed verification; no NTF-06/RPS-16/CTL-041 completion
  or production-readiness claim. Other kinds, variance and release/accounting gates remain open.
  Direct main; no deployment or external notifications.

## Queued audit verification for CLOSE packs — October 8, 2026 (RPS-16 continued)

- Continued from clean published 7fc16e5. New POST /evidence-packs requests no longer need a
  completed verification beforehand. Creation atomically inserts the pack, five supporting
  report runs, a dedicated AUDIT_CHAIN_VERIFY job and its parent: seven jobs, one transaction.
  Idempotent replay returns the original response without adding jobs or changing the binding.
- Added versioned sources v2: pack_id and audit_verification_job_id replace the completed
  verification_id. The audit job's evidence_pack subject and retained period_lock_id are checked;
  a pending tenant-wide job is never reused. Parent readiness waits for the exact job, then
  resolves its result.verification_id and verifies the PASS row/job/digest association. Assembly
  still verifies digest bytes, recorded prefix and lock anchor. Failed/cancelled/missing or
  mismatched results fail the parent; an unrelated PASS cannot substitute. V1 binding parsing
  and canonical bytes remain unchanged, and explicit completed-verification callers still work.
- Initial scoped run: **37 passed, 2 failed in 19.31 seconds** exposed the unsupported period_lock
  job subject; changed to the pack's existing supported subject. Next **37 passed, 4 failed in
  26.56 seconds** exposed the reserved release parameter and a timestamp-serialization fixture
  mismatch; used registry.handler_params and preserved canonical UTC strings. Next **38 passed,
  3 failed in 25.03 seconds** caught a missed test-helper pack_id argument. Corrected it and added
  actual parent wait/failure cleanup; final expanded regression: **68 passed in 58.53 seconds**.
- Tests cover no prior completed verification, atomic seven-job creation/rollback, exact replay,
  waiting/failed/cancelled/foreign-result refusals, failed-parent cleanup without ZIP, successful
  audit and report workers, v1/v2 output, interrupted completion, cancellation, register/download
  and role revocation. The inherited seeded-journal/close-gate caveat remains; not CTL-041 proof.
  Logs /private/tmp/evidence-queued-audit-{db,corrected,final,regression}.log; all terminal.
- Source Mypy, Ruff lint/format, whitespace, regenerated OpenAPI/client types, staleness check
  and frontend tsc --noEmit pass. Updated model/architecture/guide/build status/limits; archived
  earlier readiness/download-boundary notes verbatim. Automatic pack enqueue on lock and truthful
  availability notification, other kinds, re-lock variance and current release/accounting gates
  remain open. RPS-16/CTL-041 and production readiness unclaimed. Direct main; no deployment.

## Checkout recovery and dependency remediation — October 14, 2026

- Re-established current state from GitHub main 37e21a7: the old temporary checkout had lost
  tracked source/Git metadata and the prior Platonick workspace path no longer existed. Restored
  a clean clone at /Users/raysang/Documents/eRev-Cloud. Keep future work here, outside /tmp.
  Rechecked public visibility, main as the only remote branch and zero open PRs. No source was
  recovered from the obsolete Desktop original, and no hosted environment was changed.
- Reinstalled locked Python 3.12 and Node 24.5 dependencies. Created an isolated PostgreSQL 17
  cluster at .run/postgres on loopback port 55438, with fresh local owner/app roles, disposable
  test database erev_rv_oct14 and generated ignored .env keys. Prior credentials/processes/data
  were not assumed or reused. This is a new test environment, not a backup-restoration drill.
- On the recovered 37e21a7 backend, the close-pack/audit/source-binding baseline passed:
  **52 tests in 39.59 seconds**, using the fresh database and migrations. This is scoped current
  evidence, not a full backend or operational accounting acceptance run.
- npm audit reported two high-severity dependency groups. Updated only four locked entries:
  brace-expansion 1.1.18 → 1.1.21, 2.1.4 → 2.1.7, 5.0.9 → 5.0.12; source-map-js 1.2.1 → 1.2.2.
  Preserved unrelated optional-platform metadata. Reinstalled from the patched lock; npm audit
  reports zero known vulnerabilities across the dependency tree on October 14. Dependency
  manifests, application code, noncommercial licensing and research exclusions are unchanged.
- Full frontend suite: **192 files / 2,057 tests passed in 70.33 seconds**. TypeScript project
  build (`tsc -b`), ESLint with zero warnings, Vite production build, official OpenAPI staleness
  check and git whitespace check pass. A plain noEmit check initially lacked fresh referenced
  project declarations; the documented build-mode check creates them and passes. Build retains
  its >500 kB chunk warning; jsdom retains its unsupported-navigation warning. No browser,
  accessibility, volume, full backend or hosted release gate is claimed by these results.
- Published scope is the four dependency entries plus dated evidence. All test/tool processes
  are terminal; the isolated local PostgreSQL server remains available for subsequent work.
  .env, database files, dependencies and test logs are ignored. Public research paths remain
  absent and PolyForm Noncommercial 1.0.0 remains unchanged. Direct main; no PR or deployment.
- Local logs/evidence live under the new checkout's ignored .run/. Earlier October 8 evidence
  remains historical. Automatic pack enqueue/availability notification, other pack kinds,
  variance and current release/accounting gates remain outstanding. No deployment/readiness claim.


## Public repository publication — October 5, 2026 (America/Los_Angeles)

- Owner requested public publication with commercial use prohibited. Prepared the supplied directory
  snapshot for `https://github.com/ChipmunkRPA/erev-cloud`, using PolyForm Noncommercial 1.0.0.
- Updated LICENSE, NOTICE, bundled web copies, Python/npm package metadata, README and About dialog.
  Third-party notices remain intact. Previously granted MIT rights are not revoked.
- Excluded the entire `research-harness/` and `docs/research/` directories at the owner's explicit request; retained application
  source, fixtures, screenshots and documentation. See `docs/release/PUBLICATION-2026-10-05.md`.
- Actual validation: locked `npm ci --ignore-scripts --no-audit --no-fund`; AboutDialog vitest 4/4 passed;
  frontend Vite production build passed (existing large-chunk warning). `python3 scripts/secrets_check.py`:
  4,053 files scanned, 8 allow-listed, zero findings and zero unused entries before this note.
- Additional redacted Gitleaks scan reviewed: test constants, placeholder JWT, accounting identifiers
  and historical test references; research-harness findings removed with the entire directory.
  Targeted credential-pattern scan found only intentional self-test fixtures. These are targeted
  publication checks, not a full security audit. No generated dependencies or real environment/state
  files are staged.
- Backend/integration/accounting suites were not rerun for this licensing/publication change. Earlier
  results below remain historical. No deployment or cloud mutation; production/accounting blockers
  in LIMITS-1.0.md remain. Publication supersedes the earlier private-only instruction in this notebook.

### Publication correction — October 5, 2026

- Removed the entire research-harness and docs/research directories from the publication and replaced the initial root
  commit, so main has no ancestor containing those files. Used an exact force-with-lease against the
  previously verified remote commit. No application code changed; application tests were not rerun
  for this directory removal. External clones and GitHub cached/unreachable objects cannot be recalled
  by a branch rewrite alone.

### Public report website cleanup — October 5, 2026

- Scanned the repository for website references and reviewed documentation matches. Removed 155
  external website URLs plus bare domains across 12 documents and removed the design source
  bibliography. Kept explicit citation-removal markers, mandatory third-party notices, dependency
  metadata and operational endpoints. This does not revalidate the remaining historical prose.
- Follow-up documentation URL scan found only owner links, internal/example addresses and a local
  URL-validation regex. `git diff --check` passed. No application source changed; no application
  tests rerun. Replaced the public root with an exact force-with-lease against the verified head.

## Lock rollback and independent verification — October 14, 2026

- Broader lock-workflow baseline on 052e907: **39 passed, 2 failed in 145.30 seconds**.
  Both failures were the queued audit worker in the first-close evidence test: the test module
  did not import its real handler and previously passed only when another collected test did.
  Production worker already imports it. Added explicit test registration; no worker replacement.
- Extended rollback coverage to fail at the final lock audit after real notifications exist,
  as well as at the earlier control recorder. Both cases compare retained lock/state/snapshot/
  reconciliation/approval data plus jobs, packs, report runs, notifications, outbox messages and
  lock audits with their pre-decision values. This guards transaction atomicity; it does not
  establish automatic pack generation, which remains unimplemented.
- Corrected worker registration run: **41 passed, 1 failed in 175.04 seconds**. The new fault
  injector initially matched the earlier period-state audit, which shares the period.lock action.
  Restricted it to object_type=period_lock so it reaches the final audit after notifications;
  both rollback cases then **passed in 51.42 seconds**. Other cases were not rerun after this
  test-only correction. Ruff lint/format and whitespace checks pass. Logs under .run:
  lock-workflow-baseline.log, lock-workflow-final.log, lock-rollback-corrected.log; all terminal.
  No deployment, full release-suite or production-readiness claim.
- Automatic lock generation still needs a durable post-commit preparation job: source validation
  depends on committed approval/audit/freeze records. A process-only after-commit callback is
  insufficient; queued preparation must retain stable identity across retries. Availability
  notification must follow successful pack retention. Re-lock variance and other pack kinds,
  operational CTL-041 acceptance, current release gates and independent accounting approval remain.

## Automatic first-close preparation — October 14, 2026 (RPS-16 continued)

- From clean ae545bc, lock approval now defers EVIDENCE_PACK/PREPARE_CLOSE in its transaction.
  Preparation reads committed approval/freeze/audit sources, validates the job/lock/period-state
  association and grants only the selected entity's internal source capabilities. It creates
  one bound pack and seven source/build jobs. The build's immutable parent_job_id retains its
  preparation association; the preparation row lock serializes creation and crash retry reuses
  the exact saved pack. No source rebinding, migration or public request change.
- Initial actual-worker/crash/lock-rollback tests: **3 passed in 56.25 seconds**. A simulated
  post-commit crash retained one pack, one evidence.create event and the same seven jobs; real
  audit/report/build workers completed its 36-file archive. Lock rollback leaves no preparation
  job. Expanded tests add invalid selectors/job associations and cancellation before creation.
- Preparation success only means queued; cancellation after creation is refused there while the
  build job keeps its own cancellation lifecycle. Existing lock notices still promise snapshots.
  Re-lock jobs are queued but fail the explicit variance prerequisite. Completion notification,
  variance, other kinds, operational CTL-041, release gates and accounting approval remain open.
- Full lock-module plus retained-binding regression: **81 passed in 183.79 seconds**. This
  includes automatic preparation crash/reuse, exact source job completion, pre-creation
  cancellation without children, invalid selector/job rejection and prior manual pack paths.
  Logs .run/automatic-close-preparation.log and .run/automatic-close-regression.log; all terminal.
  Five source files pass Mypy; six changed Python files pass Ruff lint/format; whitespace clean.
  Public schemas unchanged. Direct main, no deployment or production-readiness claim.

## Automatic close-pack availability notification — October 14, 2026

- From clean 43c55a4, approval-driven locks now defer NTF-06 until successful automatic pack
  retention. The worker checks its preparation/lock association, stores the archive and notifies
  active Controller, Revenue Reviewer and Auditor role holders in the entity's scope in one
  transaction. Copy identifies the locking actor and confirms availability; link is the period
  cockpit. A period_lock subject prevents separate closes merging within the notification window.
- Already-SUCCEEDED retries verify the archive without notifying again; manual packs never
  send this notice. Cancellation/failure before retention makes no availability claim. Sandbox
  replay's existing separate snapshots-only notice remains; replay pack availability is unclaimed.
- Focused actual-worker and rollback regression: **4 passed in 59.95 seconds**. The witness
  injects failure after notification insertion (archive metadata and notifications both roll back),
  then a crash after commit (retry retains one notice per recipient). Each of the three roles is
  present in-scope and in another entity; only the in-scope members receive completion notices.
  The lock rollback test now checks that preparation was queued before its late failure.
- Broader lock/notification regression: **54 passed in 196.55 seconds**, including manual pack
  suppression, the existing role-scope scenario, reopen/approval notification flows, and generic
  notification preferences/delivery checks. Logs .run/close-notification.log and
  .run/close-notification-regression.log; all processes terminal. Three source files pass Mypy;
  five changed Python files pass Ruff lint/format. Whitespace clean. Direct main; no deployment.
  Re-lock variance, other kinds, operational CTL-041, current release checks and independent
  accounting sign-off remain outstanding. No production-readiness claim.

## Operational first-close manifest control — October 14, 2026 (CTL-041)

- From clean 0dfb9ec, added the exact RPS-16 CTL-041 test path/marker. AVM-US September uses
  real close execution, journal calculation/approval/export/acknowledgement, billing and GL
  reconciliation generation and distinct preparer/reviewer sign-offs, lock approval, automatic
  preparation/audit/report/build workers, and an Auditor's API download. No current-period
  journal/close result or reconciliation review is seeded, and no close gate is waived.
- The archive names the real close journal and both reviewed statements. The required path
  prefixes are present; every payload hash and the separately stored manifest hash match.
  Changed payload and manifest bytes each fail verification. Targeted marked control run:
  **1 passed in 18.51 seconds** (.run/operational-close-pack-control.log).
- Setup corrections followed the actual interfaces: enroll the preparer in MFA; retain her
  session on ReportWorld.place.author; attach an initial GL reference before reading comparison
  totals; generate a new reconciliation to attach the final source (replacement is forbidden).
  The corruption helper copies ZipInfo metadata because writestr mutates offsets. Earlier
  failure logs .run/operational-close-pack{,-mfa,-persona,-reference,-regenerated}.log are terminal;
  no production code, accounting oracle, permission rule or transition was changed to pass.
- Prior periods are fixture-closed. ERP acknowledgement uses the test adapter; the GL upload is
  a synthetic matching reference derived from the comparison, not an independent amount oracle.
  This supplies the missing first-close control witness, not accounting sign-off or a full
  controls/release pass. Re-lock variance, other pack kinds, browser/release gates and independent
  accounting approval remain. Control-tag validation passes (497 tagged tests collected, not
  executed by that check); log .run/evidence-control-tags.log. Ruff lint/format and whitespace
  checks pass. All processes terminal. Direct main; no deployment or readiness claim.

## Current control gate evidence — October 14, 2026

- Immutable c214c47 control run: **497 passed in 1,076.97 seconds**. No tagged test failed;
  47/49 controls are covered. CTL-045 (AI proposals) and CTL-048 (legacy migration promotion)
  lack tagged tests, so the gate correctly fails. CTL-018 and CTL-041 now pass in this gate.
- Source/dependency bindings match before/after execution. This result attests c214c47,
  not the subsequent screen increment. See docs/release/CONTROLS-2026-10-14.md and local
  .run/reports/controls-report/report.json. Independent accounting approval is still missing.

## Close evidence register and retained downloads — October 14, 2026 (RPS-20 partial)

- SF-09 and SF-09:pack now expose the scoped paginated first-close register, status filters,
  retained entity/period labels, file counts and manifest hashes, pending-state refresh,
  manifest file list, and authorized ZIP/manifest downloads. Manifest download verifies
  the archive and returns its exact retained bytes, with a committed export audit before
  serving. Both artifact types require all five source/export permissions in entity scope.
- Register counts/hashes use hash-consistent, schema-valid retained metadata and are null
  before success; listing does not open or verify archive payloads. Download still verifies
  archive/source integrity. Updated API docs, OpenAPI/client types, router inventory and
  crawl seed. Evidence tab requires all three read permissions.
- Actual API/worker/MFA/schema/metadata regression: **118 passed in 58.66 seconds**
  (.run/evidence-screen-api-regression.log). Checks include returned labels/count/hash,
  exact manifest bytes, pending/corrupt archive refusal, export audit artifacts/byte counts,
  each source permission's entity scope, revoked roles, and the operational CTL-041 witness.
- Full frontend suite before the final count/hash columns: **2,069 passed across 193 files
  in 73.48 seconds** (.run/evidence-ui-final-regression.log). Final focused screen suite:
  **12 passed in 1.53 seconds**, including those columns and filters/export refusals
  (.run/evidence-register-columns-tests.log). TypeScript, full ESLint, Vite build, Python
  Ruff/Mypy and OpenAPI checks pass. Existing Vite large-chunk warning remains.
- Earlier full frontend runs found route/crawl/tab integration issues (2,062 pass / 4 fail)
  and a test's incorrect filtered-empty expectation (2,067 pass / 1 fail); both are resolved.
  Ten database-free metadata tests also passed independently. All runs are terminal.
- RPS-20 stays unchecked: auditor-request table, generation forms, other pack kinds,
  remaining register details and real browser/accessibility/volume acceptance are outstanding.
  This is a tested repository increment, not a production-readiness claim. Direct main;
  no deployment, new PR, accounting oracle change or permission relaxation.

## Auditor request navigation — October 14, 2026 (RPS-20 continued)

- Added the 20 specified auditor requests, their available report sources, accessible
  action menus and context-preserving destinations. Reconciliation opens the selected
  entity/book/period; walkthrough opens audit events filtered to the signed-in user.
  Only reports returned by the API get actions. Pack generation is hidden without
  evidence.export and explicitly unavailable where the backend kind is unfinished.
  No placeholder generation commands or claim of complete read auditing is introduced.
- Fixed catalogue pack links from the obsolete /evidence path to /reports/evidence,
  preserving entity/period/book and requiring all evidence read permissions. Added
  catalogue permission/context checks and aligned table/row hooks with SCREENS_B.
- Full frontend: **2,078 passed across 194 files in 60.51 seconds**
  (.run/auditor-requests-full.log); TypeScript, full ESLint and Vite build pass. Existing
  jsdom navigation and Vite large-chunk warnings remain. Final focused checks cover
  table rows, both unavailable pack menus, context encoding, own-actor filtering,
  missing export access and failed definition reads (.run/auditor-requests-final.log).
- RPS-20 remains incomplete: generation forms and missing backend kinds, read-only
  presentation, remaining register details and real browser/accessibility acceptance.
  Repository only; direct main, no new PR or deployment.

## First-close generation form — October 14, 2026 (RPS-20 continued)

- Added a modal for entity, book, period and explicit retained first-close lock selection,
  using the existing CLOSE API and command pipeline. It follows all entity/period cursors,
  includes authorized inactive historical entities/books, clears dependent selections,
  and requires all export/source permissions for the chosen entity plus selector-read access.
  Re-lock/reopen records and locks without retained snapshot metadata are not offered.
- A successful response opens the new pack. An accepted response without navigation
  headers disables resubmission. Lost-response retries retain the original idempotency key,
  including after closing/reopening the modal or reselecting the same lock. Backend
  refusals remain visible; no optimistic pack or placeholder job is created on the client.
- Final frontend suite: **2,089 passed across 195 files in 65.15 seconds**
  (.run/close-pack-form-final-full.log). The 11 form tests also passed independently in
  1.46 seconds (.run/close-pack-form-final-focused.log). TypeScript, full ESLint and Vite
  build pass; existing jsdom navigation and large-chunk build warnings remain. No backend
  code or accounting result changed, so no database test was restarted for this UI increment.
- Earlier failures were test interactions: the combobox picks on mousedown, and the
  accepted-state button is replaced by its tooltip wrapper. Assertions now target the
  current accessible control. Initial pagination inference errors were fixed with explicit
  ListPage types. All processes terminal. No deployment or new PR; direct main.
- RPS-20 stays incomplete: re-lock variance, other pack kinds/forms, remaining presentation
  and real browser/accessibility acceptance. Independent accounting sign-off remains absent.

## First-close contents checklist — October 14, 2026 (RPS-20 continued)

- Detail now lists required sections and exact missing payload filenames, identifies the
  retained lock, sorts file paths and provides named keyboard-accessible file/manifest hash
  copy. Manifest presence does not claim byte verification; download verification is unchanged.
  The separately hashed manifest is correctly outside its own payload list.
- Direct comparison with the backend assembler confirmed all 36 required payload paths match.
  Tests cover complete/missing sections, a missing supporting source, manifest treatment,
  retained lock and exact clipboard bytes. Focused: 16 passed (1.68s). Full frontend:
  195 files / 2,093 tests passed (70.48s); TypeScript, full ESLint and production build passed.
  Existing build chunk-size and jsdom navigation warnings remain. All checks are terminal.
- No backend accounting behavior changed, no database tests rerun, no deployment. RPS-20
  remains open for other kinds, re-lock variance, remaining presentation and real browser
  acceptance. Independent accounting approval and broader release gates remain outstanding.

## Evidence metadata read audit — October 14, 2026 (RPS-16 continued)

- Successful register/detail HTTP reads now commit evidence.read before returning no-store
  responses. Register facts contain only authorized returned-page IDs (the existing AUD-FACT
  digest rule bounds large pages), including empty pages. Detail facts bind status, retained
  lock and manifest hash. Internal header reads during download add no duplicate read event.
- Regression verifies durable actor/object metadata, exact cursor-page populations, empty
  pages, invalid filters/missing records, revoked access, unchanged export counts, and failure
  after audit append rolling back both the event and successful metadata delivery.
- Final evidence/close, audit-writer and complete MFA regression: 37 passed in 170.41s.
  Ruff formatting/lint, source mypy and OpenAPI compatibility passed. Earlier test iterations
  corrected actor identity/count expectations and fault injection before the final passing run.
  All processes are terminal. Frontend unchanged; its earlier results remain historical.
- Archived the oldest publication notebook section verbatim to the build history to preserve
  the 20 KB limit. No deployment or accounting-calculation change. Other pack kinds, re-lock
  variance, browser/release gates and independent accounting approval remain outstanding.

## Current CI preflight and direction-aware evidence tables — October 14, 2026

- Immutable make ci on fcbfaa3 reached lint after local-only environment repair: a missing
  demo TOTP seed was generated in ignored .env, and a separate allow-listed local CI dev
  database was created. The existing development database remains unchanged; process-only
  URL overrides select the new database, with no credentials printed or committed.
- CI found three DS-LINT-10 violations: evidence contents, file and auditor-request tables
  used text-left. Changed them to logical text-start for direction-aware alignment.
- Full make lint passes: 2,049 Python files formatted; 510 design-scanned files, zero findings;
  vocabulary, 133-package license scan, 3,478-file secret scan, OpenAPI, registry, 18 fixtures
  and all 497 control markers pass. Marker validity does not prove the controls pass.
  Full make typecheck passes (876 backend source files plus frontend).
- The initial CI run is terminal, failed at design lint before tests. Its source hash is
  fcbfaa365bdfb5ecf7a4b1184cafecb7ffd1eaec, tree b20a7f01135cda47153d1c8dc1b23b0dcbedcddc;
  immutable source and dependency bindings matched. A clean post-fix full CI run is next.
  No complete CI, deployment or production-readiness claim is made.


## First-close browser acceptance — October 14, 2026 (RPS-20 continued)

- Added a real-browser workflow that selects a retained first-close lock, creates a pack,
  waits for successful retention, checks all 12 contents sections, downloads manifest/ZIP,
  compares the downloaded manifest SHA-256 with the displayed value, and checks every file
  path/hash/copy control. Light/dark accessibility checks cover register, form and detail.
- The initial closed-world run passed 9 tests and failed this new test on the register pack
  link target size. Enlarged the link to 24px minimum height. A focused retry then exposed a
  test interaction error: the shared combobox opens with Arrow Down, not input click alone.
  Corrected that interaction and waited for loaded register data before screen capture.
- Final focused browser run: 1 passed in 46.9s against the retained local demo world; this
  is not a fresh full-browser gate. Evidence components: 70 tests passed in four files.
  TypeScript and targeted ESLint passed. Reviewed register, form and detail screenshots.
  All browser test servers stopped. Logs: .run/evidence-browser-retry-2.log and
  .run/evidence-browser-regression.log. Initial full-run failure remains preserved.
- Full immutable CI on 165d63c is still running and has known failures; this entry does not
  claim a passing full release gate. Other pack kinds, re-lock variance, broader acceptance
  and independent accounting approval remain open. No deployment.

## Evidence navigation retains pack context — October 14, 2026

- Browser screenshot review found that successful generation dropped entity/book/period
  from the detail URL: the header then showed the default entity and January while the pack
  named AVM-US/August. Register links, grid row navigation and generation now carry the
  pack's own selectors; the detail breadcrumb returns to that scoped register.
- Component checks: 34 tests passed in three files (2.30s), TypeScript and targeted ESLint
  passed. Production build passed. Focused real-browser workflow passed in 46.0s, including
  the exact scoped URL, successful generation, downloads and light/dark accessibility.
  Reviewed the resulting screenshot: header shows AVM-US/August locked, matching the pack.
  Logs: .run/evidence-context-tests.log and .run/evidence-context-browser.log.
- Full frontend on df95848: 195 files / 2,093 tests passed (108.82s);
  log .run/frontend-df95848-full.log. Existing jsdom navigation warning remains.
- Browser test servers stopped. Full CI on 165d63c remains live with known failures;
  pending backend identity/IDOR repairs are not part of this frontend change. No deployment
  or complete release-gate claim. Broader release and accounting review gaps remain open.

## Runtime dependency and infrastructure validation — October 14, 2026

- make audit-deps passes on HEAD 4542527 with pending backend edits: all 77 pinned Python
  runtime distributions audited, zero vulnerabilities; npm production audit reports zero
  advisories at every severity. Five environment markers removed so the audit includes the
  whole pinned runtime set. Installed dependency bindings are consistent with both lockfiles.
- make tf-validate passes using Terraform 1.16.4: backend-disabled init, format check and
  validation of ten files/four providers. Input hashes agree before/after; provider versions
  google/google-beta 6.50.0, archive 2.8.1 and random 3.9.1. No cloud state or credentials used.
- Both runs are explicitly worktree-dirty development evidence, not immutable release gates.
  Reports remain in .run/reports/{audit-deps,tf-validate}/report.json; logs are
  .run/{audit-deps,tf-validate}-oct14-current.log. Docker client exists but its local daemon
  is unavailable (.run/docker-availability.log), so no container validation is claimed.
- Full backend CI on 165d63c remains live. Pending source/test repairs await database access;
  independent accounting approval and broader release checks remain open. No deployment.

## Integration command unit fixture — October 14, 2026

- Three CPU-only integration command tests failed because their fake human principal lacked
  membership_id after connection ownership was introduced. Added the distinct membership ID
  and explicit unassigned owner to the fake connection row; no permission assertion changed.
- Actor and integration command unit regression: 25 passed in 1.03s after repair (previously
  3 failed, 22 passed). Ruff lint/format pass. Logs .run/pending-repairs-units{,-fixed}.log.
  Run used the working tree, including pending scope/identity repairs; only this fixture fix
  is published here. Full architecture, backend CI and fresh closed-browser runs are ongoing.

## Evidence identity and authorization repairs — October 14, 2026

- Automatic pack availability resolves the validated locking actor through the shared
  record-actor reader; the identity architecture rule needs no exception.
- IDOR coverage includes all 49 GET-by-ID routes. A shared operational fixture builds actual
  retained packs. Tests cover foreign-tenant denial, authorized controls, manifest/ZIP reads,
  matching/excluded entity scopes and register visibility. Generic rows use a separate fresh
  tenant pair; no source validator or permission guard is bypassed.
- Integration create/update checks owner eligibility after proposed entity scope is valid.
  Invalid scope previously also produced a dependent owner error. Valid scope expansion still
  requires an eligible owner; scope refusal and denial auditing remain enforced.
- Focused tests used a separate local PostgreSQL instance and file/runtime paths, leaving
  CI/browser databases untouched. Initial run: 38 passed, 1 failed (279.75s); only the new IDOR
  setup failed. Fixed clock rollback/MFA reuse, generic version collisions with operational
  data, and uppercase persona email. Final IDOR: 4 passed (55.73s). Operational pack acceptance
  also passed after the shared-clock correction. Assertions were not weakened.
- Architecture: 267 passed (215.81s). Full lint/typecheck pass; final fixture/test edits pass
  Ruff/Mypy. Actor/integration unit checks: 25 passed. Logs under .run: isolated-repairs-first,
  isolated-idor-{clock-fixed,worlds-fixed,final}, pending-repairs-{architecture,full-lint,full-types}
  and idor-repair-types-final (all .log). Temporary repair server stopped. CI on 165d63c and
  browser gate on 3e60e6a remain live; no full-gate, deployment or accounting-approval claim.

## Fresh closed-world browser gate — October 14, 2026

- Immutable make e2e CLOSE=1 PROJECT=closed on 3e60e6a passed all 10 tests in
  58.7 seconds after a fresh local schema reset, migration, closed-world seed and build.
  Zero failed, flaky or skipped tests. Coverage includes locked schedules/reports,
  permanent-lock workflows and first-close generation with verified retained downloads.
- Source tree and context hashes match before/after; dependency bindings are consistent.
  The test servers stopped normally. Logs: .run/e2e-3e60e6a-full.log and
  .run/reports/e2e/{report,playwright-1-closed}.json. Exact binding and limits:
  docs/release/BROWSER-2026-10-14.md. This is the closed project, not every browser project.
- The gate retains JSON results but its temporary context cleanup removed newly generated
  screenshots. Existing worktree screenshots predate this run and cannot prove its visuals.
  Artifact retention needs repair. Backend CI on 165d63c remains live with known failures;
  later backend repairs and independent accounting acceptance are not covered by this gate.

## Retained browser artifacts — October 14, 2026

- Browser gate reports now name a unique artifact directory for each run. Each Playwright
  invocation writes screenshots and failure traces below it, so immutable-context cleanup
  copies them with the report. Earlier runs cannot supply screenshots to a later result.
- Authentication/network runtime state has a separate invocation directory and is removed
  on completion. Direct Playwright usage retains its existing default paths.
- Regression checks: 43 script/context tests passed (34.69s), including successful/failed
  gates retaining nested files after context deletion. A real Chromium probe produced both
  PNG captures and a valid trace ZIP from an intentional failure after capture; this is
  artifact verification, not an application acceptance pass. Final script checks also cover
  runtime-session cleanup: 10 passed (5.74s). Ruff, ESLint, shell syntax and full typecheck pass.
- Logs: .run/e2e-artifact-{all-tests,script-final,typecheck-final,real-browser}.log.
  The earlier closed-world gate remains bound to 3e60e6a and its lost screenshots cannot be
  recovered. Full backend CI on 165d63c is still live; broader readiness remains open.

## Workspace-type refusal audit — October 14, 2026

- Refused PATCH /tenant requests naming kind now append tenant.update / DENIED in the
  caller's tenant and preserve the 409 tenant-kind-immutable response. The event identifies
  the actor, tenant, refused field and problem; it survives rollback of the command.
- Refusals read without an update lock, avoiding a conflict with the independent audit
  transaction's tenant foreign key. Normal changes still lock and check row versions.
  Permission and If-Match checks remain in place; refused mixed changes do not rename a tenant.
- Isolated PostgreSQL API and sandbox tests: 2 passed (10.36s). Final actor assertion:
  1 passed (9.76s). The first attempt could not connect because the local repair server
  restarted on its default port; rerun used the intended separate port 55439. Server stopped.
  Logs: .run/tenant-kind-audit-{tests-fixed-server,actor-final}.log. Full lint/typecheck
  pass; audit/guard architecture checks: 8 passed (8.61s), logs with suffixes lint, types
  and architecture.
- A focused browser attempt against the old demo database found its temporary encrypted
  snapshot files were gone, so its 500 response is not an application acceptance result.
  Screenshots and failure trace were retained. A fresh closed gate on bce381c is now running
  with a matching local database/file store; full backend CI on 165d63c also remains live.

## Sandbox reset source isolation — October 14, 2026

- B7-5's source-provenance observation is permitted by SBX-02, which requires creation
  events in both tenants. The refused-type audit defect was repaired in 1ab522c.
- Strengthened SNAPSHOT and EMPTY reset acceptance to compare every tenant-scoped source
  row's full contents outside audit head/events, notifications, outbox and snapshot metadata.
  Existing assertions still check the expected provenance events, snapshot successor target,
  source row-count restrictions, old-sandbox archival and successor results. The populated
  K-03 case explicitly requires nonempty contract and subledger rows before comparison.
- First accounting-table comparison: 2 passed (29.63s). Broadened source comparison:
  2 passed (29.44s). Ruff and strict test Mypy pass. Logs .run/sandbox-reset-source-
  {contents,all-rows,types-final}.log. Separate local repair server stopped.
- Updated browser gate documentation to locate screenshots/traces via the report's artifacts
  field. Fresh closed browser gate bce381c and backend CI 165d63c remain live. These checks
  do not establish full CTL-043, release acceptance or accounting sign-off.

## Point-in-time royalty licences — October 14, 2026

- Repaired the API/DB mismatch that rejected the engine's supported point-in-time
  royalty licence template. Migration 0144 permits only the LICENCE/ROYALTY exception;
  non-licence obligations remain restricted. Updated T-REF-23's documented constraint.
- API-driven RPO tests verify a 15,000 statement against a 12,000 guarantee adds 3,000,
  recognition waits for delivery, April delivery releases 15,000, and a May downward
  correction reverses 1,000. Both initial delivery states reconcile with zero unexplained.
- Initial tests exposed template rejection; the next attempt exposed a missing trigger
  in the new delivery fixture. Corrected fixture and expanded checks: 4 passed (21.56s).
  Final full template/RPO files and DB invariant: 22 passed (70.78s), recorded in
  .run/rpo-royalty-regression.log. Full production typecheck, focused report-test Mypy,
  Ruff and formatting pass. Standalone Mypy of all selected test files encountered
  existing fixture-import/row-typing issues; it is not claimed as passing.
- Fresh closed browser gate bce381c passed 10/10 and retained 22 PNGs after cleanup;
  see BROWSER-2026-10-14.md. Full backend CI 165d63c remains in progress.
- B4-2's combined cases and other release limitations remain open. No deployment or
  accounting sign-off; publish directly to main without a PR.

## Renewal benefit-period engine verification — October 14, 2026

- Added eight B3-24 regressions through canonicalization, obligation construction,
  allocation and full-engine posted revenue, for ASC606 and IFRS15. A 12,000 renewal
  right spans 24 months at 500/month when the inception estimate says 24 months;
  without an estimate it keeps the booked 12-month term at 1,000/month.
- A later 36-month estimate does not change inception pricing. A discount voucher
  keeps its own term rather than inheriting the renewal estimate. Tests check exact
  period keys, posted amounts, total, option SSP and obligation dates.
- Initial fixture omitted the explicit MONTHLY_EVEN policy and therefore produced
  daily amounts; corrected the fixture's convention, preserving expected figures.
  A subsequent negative-case fixture used a nonexistent GroupInput field; corrected
  it to replace only the contract input. No engine implementation changed.
- Entire stage-03 suite: 41 passed (3.02s), .run/benefit-period-s03-final.log.
  Strict Mypy, Ruff and formatting pass. B3-24 now distinguishes this evidence from
  still-missing API-entry, answer-key and independent accounting acceptance.
- Full backend CI 165d63c remains running around 29%; existing known failures have
  later repairs. Repo only, direct main publication, no deployment.

## Native material-right gap confirmed — October 14, 2026

- Source tracing shows B3-24 needs implementation, not only another API test: bundles
  always send empty material_rights, T-CON-14 is absent, the dedicated read always
  returns 404 and the embedded read always returns null. Migration capture refuses
  converted option records. Existing engine regressions bypass these missing paths.
- Corrected the limitation and added MATERIAL-RIGHTS-IMPLEMENTATION.md with required
  persistence, governed entry, historical reads, migration, UI and acceptance coverage.
  Preserve the migration refusal until the complete terms path exists. No runtime
  change or claim of product support; full backend CI remains running.

## Material-right persistence foundation — October 14, 2026

- Migration 0145 creates immutable T-CON-14 option terms and E-92 option_type, tenant
  RLS, foreign keys, unique obligation and contract lookup index. Database checks
  enforce required discount terms, amount/ratio bounds, same-contract obligation and
  exercise-likelihood estimate, and currency agreement. A composite FK prevents a
  later parent-currency change. Application and owner mutation attempts are refused.
- Added ORM export, shared row builder, snapshot classification, cutoff, dependency
  order and likelihood-reference remapping. Removed obsolete pending-table entries
  and updated inventory assertions and the data-model specification.
- 77 focused schema/RLS/snapshot/architecture checks passed (9.99s); final parent guard
  and migration downgrade/upgrade: 2 passed (7.59s). Full typecheck (878 source files
  plus frontend), focused Mypy, Ruff and formatting pass. Evidence and remaining
  lifecycle work are in MATERIAL-RIGHTS-IMPLEMENTATION.md.
- A broader check found the existing missing period_reopen_basis test-row builder;
  retain that failure for repair. Native term entry, engine bundle reads, API status,
  migration conversion and populated snapshot acceptance are not yet implemented.
  Full CI 165d63c remains live around 30%. No deployment; direct main publication.

## Material-right bundle and reads — October 14, 2026

- Connected immutable option terms to real engine bundles at known_at, with stable
  obligation/estimate keys. Dedicated and embedded obligation reads now return terms
  and status from non-voided exercise/expiry events at the effective and record cuts.
  Contract visibility still governs access; expiry dates alone do not change status.
- Added dedicated-read as_of/known_at parameters, offset validation and regenerated
  OpenAPI/TypeScript schemas. Four database/API tests pass (22.83s): real computation
  receives stored terms; both reads agree; historical absence, event voids and tenant
  isolation hold. Route/import checks: 38 passed (18.71s). Full typecheck (879 source
  files plus frontend) and Ruff pass. Evidence: MATERIAL-RIGHTS-IMPLEMENTATION.md.
- Corrected fixture transaction/head/query-parameter mistakes found by initial runs;
  production guards and expected results were retained. Tests insert terms explicitly:
  native entry, governed corrections, migration conversion and populated snapshot
  acceptance remain unfinished. Full CI 165d63c remains live. No deployment.

## Activation approval binds material rights — October 14, 2026

- Found and repaired a review gap before exposing native term entry: adding T-CON-14
  terms after activation submission previously left the approval hash unchanged.
  The baseline review returned 200. Activation content now binds identities and all
  option accounting fields in deterministic order. Contracts without terms retain
  their existing content shape and pending hashes.
- A real API review now returns 409 stale-approval after injected terms, leaves the
  contract inactive with no postings, and succeeds only after fresh submission and
  review. The regression also checks the full bound content, including null fields.
- Full activation suite: 19 passed (121.46s); .run/material-right-approval-regression.log.
  Focused repair: 1 passed (14.05s). Full typecheck and Ruff pass. Baseline evidence,
  implementation boundaries and next entry requirements are recorded in
  MATERIAL-RIGHTS-IMPLEMENTATION.md. Native entry and corrections remain unfinished.
- Full CI 165d63c is still running independently. No deployment; publish directly to main.

## Native material-right draft entry — October 14, 2026

- Added the immutable option-term POST with contracting-entity permission, group/contract
  locks, parent-stream If-Match, DRAFT/no-pending-review checks and atomic computation.
  Invalid method, currency, likelihood or non-option classification leaves no terms
  or computation. Dedicated reads use the contracting entity's date.
- Reproduced and fixed an approval gap: a different term preparer could approve Maya's
  activation submission. Option authors are now excluded by the approval kernel;
  independent review succeeds. AUD-FACT represented-preparer identities are included.
- Activation and route/import/scope checks: 62 passed (151.74s). Final API regressions:
  2 passed (20.43s), including idempotent replay and one contract-bound creation audit.
  Full typecheck (880 source files plus frontend), Ruff and diff checks pass.
  Logs: .run/material-right-native-regression.log, .run/material-right-native-final.log,
  .run/material-right-native-types.log. OpenAPI/TypeScript and command docs updated.
- Corrections, draft replacement/race acceptance, full method matrix, UI, migration,
  populated snapshot and independent accounting acceptance remain open. Original full
  CI 165d63c remains live and is not current-candidate evidence. No deployment.

## Material-right replacement and activation routing — October 14, 2026

- Verified native term creation followed by an integration's price-only draft replacement:
  the same obligation retains identical immutable terms and exactly one record.
- Baseline activation omitted MANUAL_ENTRY for the human term preparer. MATERIAL_RIGHT
  still kept that request pending; no auto-approval bypass was demonstrated. Routing now
  reads option authors (including represented preparers) and persisted option records.
- Activation-routing regressions: 12 passed (91.18s), including untouched-integration
  auto-approval. A SYSTEM/AUD-FACT represented-preparer fixture plus import checks:
  31 passed (18.19s). Full typecheck, Ruff and diff checks pass. Logs:
  .run/material-right-replacement-baseline.log, .run/material-right-routing-regression.log,
  .run/material-right-routing-facts.log, .run/material-right-routing-types.log.
- Key/product removal, corrections, races, complete historical replacement, UI and
  migration acceptance remain open. Original CI 165d63c is live in demo/performance
  seeding. Noncommercial licensing and publication exclusions retained. No deployment.

## Reopen-basis isolation coverage — October 14, 2026

- Reproduced the catalogue-completeness failure: period_reopen_basis had no shared
  row builder. Added its period/entity/state dependencies and registered the builder.
  The existing sweep now proves own-row visibility, foreign-tenant read/write denial
  and no-context denial. Entity-scope checks include the reopen basis and now verify
  forbidden updates/deletes as well as reads/inserts for all five reference cases.
- Fixed two typing issues in touched helpers: explicit obligation-version UUID inputs
  and a real user identity for the loss-provision fixture instead of None.
- Final focused PostgreSQL run: 10 passed (6.93s); strict Mypy on both touched files,
  Ruff and diff checks pass. Evidence: .run/reopen-rls-baseline.log (failure),
  .run/reopen-rls-verified.log and .run/reopen-rls-types-final.log. Earlier Mypy invocations
  used incomplete module-path configuration; final check uses MYPYPATH and explicit
  package bases. No production runtime or schema change.
- Full CI 165d63c remains live around 32%; this focused repair does not establish a
  passing release gate. Original exclusions/noncommercial license retained; no deployment.

## Native discount-option calculation — October 14, 2026

- Added ASC606 API cases for discount-times-likelihood: USD 100 expected purchases,
  0.5 incremental discount and likelihoods 0.8/0.5 produce persisted selected SSP 40/25.
  Missing approved likelihood refuses entry with no retained terms; evidence-backed
  estimate approval permits entry, and independent activation retains the USD 12,000
  allocation with zero revenue before exercise/expiry.
- Final cases: 2 passed (31.40s), strict test-file Mypy and Ruff pass. Logs:
  .run/material-right-discount-final.log and .run/material-right-discount-types.log.
  Added an explicit heterogeneous-input annotation found by the strict check.
- Attempting native expiry failed with 422 API-R-30: the generic route requires an
  absent dedicated command. Retained .run/material-right-discount-expiry.log and
  documented the required governed expiry/exercise commands and ledger acceptance.
  These missing commands remain implementation work; no expiry support is claimed.
- Full CI 165d63c is live around 32%. No deployment; direct-main publication.

## Dedicated material-right expiry — October 14, 2026

- Added expire-material-right with event.record permission, stream preconditions,
  idempotency, group/contract locks, ACTIVE/open/current-kind guards and actual-date
  bounds. Reused posting-period/evidence validation, audit, append/compute and deferred
  jobs. Synchronous computation refusal rolls back; generic event append stays restricted.
- Reproduced and repaired duplicate expiry caused by filtering committed events at the
  request timestamp. Locked guards and current option reads now use latest records;
  explicit known_at reads preserve their cutoff. The two native pricing/activation cases
  now expire, recognize USD 12,000, leave zero allocation and verify balanced subledger
  lines with a 12,000 revenue credit. Replay creates no second event; repeat closure,
  missing/stale preconditions and future dates are refused.
- Broad event/obligation/route/import/read regressions: 56 passed (112.14s). Final lifecycle
  and historical-period assertions: 2 passed (32.49s). Revenue reads are period-end totals,
  while status is daily; a first test incorrectly expected daily revenue and was corrected
  against API-C-10, with a separate prior-period-zero assertion. Full typecheck (880 files
  plus frontend), strict test Mypy and Ruff pass. Logs: .run/material-right-expire-regression.log,
  .run/material-right-expire-period-cuts.log, .run/material-right-expire-types.log.
- OpenAPI, TypeScript, specification and limitations updated. Exercise/reversal, specific
  race/security/closed-period/failure cases and complete release/accounting acceptance remain
  open. Full CI 165d63c is live around 32%, with another demo-reference failure awaiting
  diagnostics. No deployment; publish directly to main.

## Expiry isolation, rollback and concurrent requests — October 14, 2026

- Added native refusal checks for DRAFT, premature declared expiry, read-only access,
  another entity and another tenant. Injected an engine crash and verified no change
  to head, expiry events, computations, subledger lines, exception rows or OPEN status.
- Reproduced a retry defect: a crashed expiry computation became cached 422. FAILED
  now returns sanitized 500 and abandons that idempotency attempt; the same request/key
  succeeds after recovery. Business quarantine remains validation failure.
- Two competing requests were observed as distinct PostgreSQL waiters on the group
  lock. The holder then took the contract lock without inversion. After release:
  one 201, one 412, one expiry event/head increment and USD 12,000 revenue.
- Both boundary tests passed (44.53s), full typecheck (880 source files plus frontend),
  strict test Mypy and Ruff pass. Logs: .run/material-right-expire-boundaries.log
  (retry baseline), .run/material-right-expire-boundaries-fixed.log and
  .run/material-right-expire-boundary-production-types.log.
- Other-command races, closed-period/deferred failures, exercise/reversal and release
  acceptance remain open. Full CI 165d63c remains live at 32%. No deployment.

## Seeded Step 1 event routing — October 14, 2026

- Reproduced the demo-reference failure from the ongoing backend CI: STEP1_EVENT
  lacked a seeded human-review routing rule. Added ROUTE-STEP1-01 with one
  event.approve approver, matching the subject specification and existing kernel floor.
  This closes a seed-coverage gap; the kernel already supplied fallback routing.
- Reference coverage verifies the exact permission/count; evaluation/submission parity
  now covers 39 subject/rule combinations. Seed determinism, routing parity and approval
  floors: 73 passed (24.58s). Strict Mypy for all three changed files and Ruff pass.
  Logs: .run/demo-routing-baseline.log, .run/demo-routing-regression-fixed.log,
  .run/demo-routing-types.log. Initial regression assertions were corrected for the
  output field name and the additional routing case.
- GitHub has no open PRs and only remote main. Continue verified direct-main publication,
  without deployment. Full CI on the older 165d63c snapshot remains in progress;
  its results will not establish acceptance of current main. Release gaps remain open.

## Populated option snapshot recovery — October 14, 2026

- Added stored-export/load acceptance for native entered-amount and approved
  discount-times-likelihood options, each OPEN and EXPIRED. Actual commands prepare
  and independently approve activation; stored backup is restored into a new sandbox.
- Four cases passed (42.27s): one exported terms row, unchanged manifest, export reused,
  one group recomputed, no reported derived mismatch, identical terms except tenant id,
  preserved status and revenue credits of zero/open or USD 12,000/expired in both tenants.
- Shared expiry security/rollback/concurrency cases also passed in the preceding run.
  Strict test Mypy, Ruff and diff checks pass. Logs: .run/material-right-snapshot-final.log,
  .run/material-right-snapshot-fixed.log and .run/material-right-snapshot-types.log.
  Initial fixture failures used the wrong ledger column and reused a sandbox name;
  corrected the fixture, without changing restore or accounting behavior.
- Renewal methods, IFRS15 native lifecycle, correction/exercise, migration conversion,
  UI, full release gates and independent accounting acceptance remain open. Full CI on
  165d63c is still live and has a new CSV contract-header conflict failure to investigate.
  Publish verified work directly to main; no deployment.

## CSV quarantine reconciliation assertions — October 14, 2026

- Reproduced two failures observed in the ongoing backend CI. Contract-header conflict
  and bundle quarantine imports correctly committed only valid objects, but their tests
  rejected the newer amount_sums and monetary_checks fields in control totals.
- Updated assertions retain exact loaded/quarantined counts and now require matching
  source/stored reconciliation evidence. Only SF-ORD-31004 contributes its USD 96,000
  and 24,000 lines (USD 120,000 total); only the accepted bundle component is reported.
  Existing checks still require no refused contract and no partial bundle replacement.
- Both complete files pass: 14 tests in 64.80s. Strict test Mypy, Ruff and diff checks pass.
  Logs: .run/csv-quarantine-baseline.log (2 failed, 12 passed),
  .run/csv-quarantine-fixed.log and .run/csv-quarantine-types.log.
- Rechecked publication: repository PUBLIC, default branch main, PolyForm Noncommercial
  retained, and neither research-harness nor docs/research tracked. Full CI on older
  165d63c remains live; release acceptance and accounting sign-off remain outstanding.
  No deployment. Publish reviewed changes directly to main.

## Native option creation failure recovery — October 14, 2026

- Reproduced an injected engine crash being returned as cached 422 during native option
  entry. Creation now aborts FAILED computation with sanitized 500, rolls back its facts
  and abandons that idempotency attempt. The identical request/key succeeds after recovery.
- Known incomplete option inputs/missing dated likelihood pins use a specific ValueError
  subtype, caught as validation by native entry. Unrelated ValueError crashes are not
  classified as bad terms. Missing approved likelihood and business refusals retain 422.
- The regression checks unchanged DRAFT/head, terms, computations, events, ledger and
  exceptions after failure, then successful retry/replay and independent activation review.
  API entry/invalid/discount cases plus the stage-03 suite: 45 passed (62.35s).
- Full typecheck (880 source files plus frontend), strict test Mypy, Ruff and diff checks
  pass. Logs: .run/material-right-create-retry-baseline.log,
  .run/material-right-create-retry-fixed.log and .run/material-right-create-retry-types.log.
- Full CI on older 165d63c remains live at 34%. Exercise, correction, migration/UI,
  broader release acceptance and independent accounting review remain open. No deployment;
  publish reviewed changes directly to main.

## Native option workbench controls — October 14, 2026

- Obligation Overview now displays persisted option terms/status and links its likelihood
  estimate. Entity-scoped, current-view controls permit draft entry and active/open expiry.
  Forms support the three SSP methods, approved applicable likelihood selection, decimal
  strings, dates, expiry reasons/evidence, ETag/idempotency and cache refresh/refusal handling.
- Queued expiry retains job progress, prevents duplicate submission, and distinguishes
  recorded expiry from failed computation. A failure never claims the event rolled back.
  Embedded terms now use MaterialRightOut in OpenAPI instead of an untyped dictionary.
- UI/workbench regressions: 79 passed; final option/evidence-link suite: 14 passed.
  API/read/import-cycle checks: 34 passed (27.93s). Full typecheck (880 sources/frontend),
  final frontend types, ESLint and Ruff pass. Desktop/mobile form captures were inspected;
  five screenshots in .run/option-*.png, browser reported no page errors.
- Logs: .run/material-right-ui-tests-final.log, .run/material-right-ui-tests-last-fixed.log,
  .run/material-right-ui-api-fixed.log, .run/material-right-ui-full-types.log and
  .run/material-right-ui-visual.log. Initial checks caught a closed drawer and loose schema;
  fixture corrections covered select events, currency reference and the API test filename.
- This is component/API evidence, not live full-browser accounting acceptance. Governed
  exercise/correction, migration and release/accountant sign-off remain open. Build passed; no deployment.

## Entity-scope reconciliation verification — October 14, 2026

- Reproduced two CI failures in entity-scoped CSV contract quarantine. Both correctly
  committed the admitted contract; exact legacy total assertions rejected the newer
  amount_sums and monetary_checks fields. Assertions now require only EVE-UK-0002/0003
  in the respective stored evidence, matching source/stored lines of USD 96,000 and
  24,000, USD 120,000 total, and exact loaded/quarantined counts. Refused contracts and
  partial contract writes remain prohibited by the existing persisted-row checks.
- Initial full file: 40 passed, 2 stale assertions failed (246.11s). Both corrected cases
  plus out-of-scope submit/cancel denial: 3 passed (24.61s). Strict test Mypy and Ruff pass;
  an empty command-body tuple received an explicit type. Logs: .run/import-scope-baseline.log,
  .run/import-scope-fixed.log and .run/import-scope-types.log.
- Audited migration conversion: staged option SSP equals original quantity times price,
  but T-CON-14/bundle inputs do not preserve that per-option entered amount. Quantity-one
  conversion cannot safely reuse a shared catalogue point. Recorded the dependency and
  two-options/same-catalogue acceptance case in MATERIAL-RIGHTS-IMPLEMENTATION.md.
  Conversion refusal remains until the complete amount/promotion/replay path is implemented.
- Older full CI 165d63c remains live at 35%. No readiness claim or deployment; publish to main.

## Explicit entered option SSP engine path — October 14, 2026

- Added optional per-option total SSP in contract currency. Stages 03 and 05 preserve
  the entered amount instead of repricing against a shared catalogue; quantity does not
  multiply it. Wrong method/currency and negative/nonfinite values refuse computation.
- Input hashes bind explicit values while absent values keep the previous hash shape.
  Old evidence decodes with None. Source-record trace evidence and formula reevaluation
  preserve the actual option amount without claiming it came from the catalogue.
- 397 engine stage-03/stage-05/kernel/upgrade tests passed (29.12s), including 13 new
  tests covering allocation, ASC606/IFRS15 shared catalogue options, total semantics,
  hash compatibility, codec replay and invalid inputs. Strict Mypy: 880 production
  sources plus the new test file; Ruff passes. Logs: .run/entered-option-engine-final.log,
  .run/entered-option-production-types.log and .run/entered-option-types.log.
- Persistence, command/read/UI, adapter, snapshot/export and migration promotion remain
  unfinished. Capture's option refusal remains. No readiness claim or deployment.
  Older CI 165d63c is still running at 36%; it is not current-main release evidence.

## Persisted entered option SSP and native workflow — October 14, 2026

- Revision 0146 adds immutable optional total SSP with method/nonnegative constraints.
  Native entry enforces contract currency; reads, bundle assembly, activation approval
  content and workbench entry/display preserve the amount. Absence retains catalogue
  selection and old approval content. Updated OpenAPI/types and user/data-model docs.
- Native entry proves USD 123.45 persists as selected SSP for quantity 50, with idempotent
  retry, separate activation reviewer and bound approval content. Final native/migration
  checks: 5 passed (46.85s). Four snapshot cases (explicit/discount, open/expired) and
  approval binding passed in preceding runs. Invalid method/currency/negative entry and
  API/bundle reads also passed. Initial downgrade fixtures had shared data and owner RLS
  issues; corrected with transaction-scoped fixture data and verified refusal/round-trip.
- Schema/ORM/migration/snapshot checks: 80 passed; removed a stale pending option_type
  enum entry now implemented by 0145. UI: 16 passed; full typecheck: 881 sources/frontend;
  strict test types, Ruff, ESLint and production build pass (existing chunk advisory).
  Logs: .run/entered-option-persisted-final.log, .run/entered-option-native-final.log,
  .run/entered-option-native.log, .run/entered-option-schema-final.log,
  .run/entered-option-ui-final.log and .run/entered-option-native-types.log.
- Migration capture/promotion remains unfinished and refuses option records. No deployment
  or readiness claim. Older immutable CI 165d63c remains live at 37%.

## Converted option opening units — October 14, 2026

- Found that POL-212 books quantity one but opening payloads retained dollar-unit quantities.
  Converted payload quantities now divide by source quantity and per-unit rates multiply
  by it. Monetary balances and immutable source/staging rows remain unchanged. Legacy
  KEEP behavior is unchanged; inexact conversions refuse rather than round.
- Regression reproduced 10 remaining units instead of 0.4 for source quantity 25.
  Real API-to-engine adapter and stage-07 witnesses pass under ASC606/IFRS15, preserving
  remaining SSP 10, allocation 62.5 and posted baseline revenue 37.50.
- 45 migration/capture/onboarding tests passed (1.33s); strict production Mypy (881 sources),
  test Mypy and Ruff pass. Logs: .run/option-opening-baseline.log,
  .run/option-opening-final.log, .run/option-opening-types.log and
  .run/option-opening-test-types.log.
- Capture still refuses option records: its writer and MIGRATION_PROMOTION approval
  subject remain missing. No deployment or readiness claim. Older immutable CI remains
  live at 39%, with a new audit-coverage failure to investigate when its evidence is ready.

## Native command audit coverage — October 14, 2026

- Current catalogue checks exposed missing option-entry, option-expiry and evidence-pack
  create commands. Added successful request scenarios to the full audit walk and catalogue:
  238 command operations, 232 required after the existing six exemptions. Scenarios bind
  audit evidence to the response request id, expected action, actor kind and contract key.
- Material-right facts now require their contract key in the audit writer. Verified the
  stored AUD-FACT summary names the created fact id and contract; it intentionally has no
  single object id/label. Added display labels for evidence packs and control executions.
  CLOSE packs explicitly exercise the existing period-level, no-contract audit shape.
- 26 focused database/catalogue/architecture/read-model checks passed (51.54s); strict
  production Mypy (881 sources), three test files and Ruff pass. Logs:
  .run/audit-catalogue-current.log, .run/audit-new-routes-release.log,
  .run/audit-new-routes-types.log and .run/audit-contract-production-types.log.
  Initial scenarios exposed fixture permissions/combination setup and a mistaken single-
  object label expectation for AUD-FACT; corrected without weakening product checks.
- The category sweep still requires the unimplemented AI proposal lifecycle. No exemption
  or success claim was added. Full current-main route walk/release gates remain open.
  Older immutable CI 165d63c remains live at 42%; no deployment or readiness claim.

## Shared option term persistence — October 14, 2026

- Native entry and the migration applier share validated immutable term insertion. Converted
  records carry their explicit total SSP, quantity-one convention and unclassified OTHER
  subtype; no renewal, expiry or likelihood is invented. Native guards and compute/audit
  ordering remain intact. The migration applier audits only after successful computation.
- 25 focused migration/database checks passed (8.09s), including stored adapter values,
  savepoint parent/term rollback, cross-contract refusal and exact money precision. Six
  native entry/approval/likelihood/rollback cases passed (65.49s). Logs:
  .run/shared-option-writer.log and .run/shared-option-writer-final.log.
- 19 architecture/lock-order checks passed; strict production Mypy (883 files), test
  Mypy and Ruff passed. See .run/shared-option-writer-architecture.log and *-types.log.
- Converted-option capture still refuses until full platform capture, reconciliation and
  approved promotion are verified. MIGRATION_PROMOTION remains unimplemented. This change
  verifies term persistence, not complete import acceptance. No deployment/readiness claim.
- Older immutable CI 165d63c remains live at 44%; it is not current-main release evidence.

## Converted option platform capture witness — October 14, 2026

- Added a PostgreSQL witness through the real platform booking, activation-event, engine,
  persistence and capture-reader path. Published parity templates and an approved legacy
  SSP catalogue support a paid product plus converted option, without mocking computation.
- The option retains total SSP/allocation 25, remaining quantity 0.4, revenue 15 and remaining
  allocation 10. Contract billed total 100, revenue 15 and remaining allocation 85 agree.
  Verified retained input hash/batch/cutover, contract-keyed audit facts, and rollback leaving
  no contracts or option terms. One integration test passed (9.21s); strict test Mypy/Ruff pass.
  Logs: .run/converted-option-capture.log and .run/converted-option-capture-types.log.
- Earlier setup attempts exposed an incomplete stage-only fixture (free option with no paid
  line funding allocation) and missing period-state setup. The final fixture represents the
  complete two-line contract. No engine checks or approval guards were weakened.
- The public capture refusal stays: reconciliation still compares raw legacy dollar-unit
  quantity 10 against option quantity 0.4, and MIGRATION_PROMOTION is unimplemented. Full
  import/reconcile/promotion acceptance remains open. Older CI 165d63c is live at 45%.

## Evidence-bound option quantity reconciliation — October 14, 2026

- Reconciliation consumes verified producing bundles and explains only the exact POL-212
  quantity conversion. Contract/obligation/product, quantity-one booking, currency and total
  option SSP must match source facts. Reports retain source 10, actual 0.4 and difference
  -9.6 with a named policy explanation; no source, trace, money value or golden file changes.
- Exact expected-quantity checks reject drift and the deceptive case of 10 native options
  numerically matching 10 source dollar-units. Conflicting quantity explanations refuse.
  No monetary discrepancy receives the conversion explanation; replay behavior is unchanged.
- The actual platform-capture/database witness now runs default reconciliation readers over
  retained evidence and reaches RECONCILED. Two altered-quantity/digest cases refuse without
  lines or status transition. Three database checks passed (13.30s); 93 focused domain,
  repository/job/report/architecture checks passed (10.57s). Logs:
  .run/option-reconciliation-pg.log and .run/option-reconciliation-unit.log.
- Strict production Mypy (884 files), two test files and Ruff pass. Logs:
  .run/option-reconciliation-types.log and .run/option-reconciliation-test-types.log.
- Full import/approved promotion remains incomplete, and the public option refusal stays.
  Older immutable CI 165d63c remains live at 46%; no deployment or readiness claim.

## Durable migration promotion review basis — October 14, 2026

- Extracted the shared read-only reconciliation assessment and added promotion review of
  retained evidence. It requires RECONCILED/SUBMITTED opening-balance status, reassesses all
  figures, verifies source-row hashes and requires the complete stored line set to match.
- The review fingerprint binds source/capture/reconciliation artifacts and the recorded
  profile, including replayed SSP references. It stays stable across SUBMITTED and changes
  with the SSP profile. Review alone writes no audit events or live contracts.
- Three PostgreSQL cases passed (9.56s), including missing/duplicate/changed stored-line
  refusals and status/profile binding. 68 related checks passed (9.20s); strict production
  Mypy (885 files), test Mypy and Ruff passed. Logs: .run/migration-promotion-review-*.log.
- This is a foundation for promotion, not the approval subject: current configuration/report
  checks, policy publication, activation admission, reproduction and atomic live creation,
  independent reviewer/MFA and submit route remain unfinished. Public option import stays
  unavailable. Older immutable CI remains live at 46%; no deployment/readiness claim.

## Retained opening choices and input reconstruction — October 14, 2026

- Successful imports retain complete confirmed parameters/entity mapping and staging/plan
  hashes. Promotion review restores from retained source/cutover and compares bookings,
  opening balances, customer identity and immutable option terms with captured input.
  Missing plans require re-import; no current defaults are substituted.
- A newly hashed plan with changed conversion or entity mapping refuses against the original
  capture. Decimal option terms compare exactly (25 equals stored 25.0000); no rounding.
- The registered import worker with non-identity mapping retains a reconstructable four-
  contract plan: 1 check passed (12.72s). Domain/import/reconciliation/architecture checks:
  70 passed (9.96s). Three converted-option database checks passed (12.10s), covering
  missing/changed plans and review invariants. Strict production Mypy (886 files), two test
  files, the final plan helper and Ruff pass. Evidence: .run/migration-opening-plan-*.log.
- Output reproduction under current configuration, policy publication, activation admission
  and independent approval/live creation remain unfinished. Public option import/promotion
  stay unavailable. Older immutable CI is live at 52%; no deployment/readiness claim.

## Complete opening output reproduction — October 14, 2026

- Promotion preflight replays verified retained inputs and requires the captured full output
  hash. It rebooks the confirmed plan against current configuration inside a child savepoint
  and compares every output field except the input hash (fresh identities/time). No book,
  trace, posting, schedule or diagnostic is excluded. Review basis v2 binds result hashes.
- PostgreSQL witness: 3 cases passed (12.78s), including later observation time, bad output
  hash, missing template, IFRS15 enabled after capture, changed diagnostics and rollback.
  126 domain/job/repository/architecture checks passed (17.23s); strict production Mypy
  (887 sources), changed-file Mypy and Ruff pass. Logs: .run/migration-reproduction-*.log.
- Policy/report/activation checks, configuration locking, atomic live creation and independent
  approval/MFA remain unfinished. Public option import/promotion remain guarded. Negative
  testing also found stage 03's raw ValueError for AGENT without reviewed PRINCIPAL_AGENT;
  typed admission handling remains outstanding. Older immutable CI remains live at 53%.
- Published directly to main; no deployment, readiness or accounting sign-off claim.

## Named principal-agent migration refusal — October 14, 2026

- Stage 03 now distinguishes incomplete reviewed agent terms with PrincipalAgentInputError,
  preserving the ValueError contract. Migration capture maps these failures to named 422
  validation; output replay refuses by name. Arithmetic and range invariants are unchanged.
- Real PostgreSQL reproduction verifies an unreviewed AGENT product refuses and rolls back
  temporary contracts/options/audits. An injected unexpected ValueError remains unexpected,
  rolls back, and leaves the original review basis reproducible.
- Engine/agent-billing/capture suite: 46 passed (16.49s); final PG/architecture suite: 66 passed
  (31.00s), with three overlapping database cases. Strict production plus PG-test typing
  passes (888 sources); Ruff passes. The specialist test's 28 existing helper typing errors
  reproduce unchanged from prior main. Logs: .run/agent-input-refusal-*.log.
- Promotion approval, policy/report/activation checks and independent accounting sign-off
  remain outstanding. No deployment; verified changes published directly to main.

## Migration activation prerequisites — October 14, 2026

- Review basis v3 binds each reproduced contract's complete pre-activation checklist. Missing,
  duplicate, foreign, incomplete and malformed evidence refuses. Failed mandatory/source,
  product/template/SSP, combination or existing-judgement prerequisites refuse by rule code.
- An inactive product can reproduce accounting output but now fails activation preflight.
  Distinctness/collectibility judgements required by BS3-D-23/26 stay explicitly pending and
  failed, with ready_for_activation false. No approval or waiver is fabricated.
- Three PostgreSQL cases passed (17.78s); 101 domain/capture/architecture checks passed
  (17.04s); strict production plus changed tests (890 sources) and Ruff pass. Evidence:
  .run/migration-activation-review-{pg,unit,types}.log.
- Creating/reviewing judgements under approval, final activation admission, policy/report
  checks and atomic live creation remain unfinished. Current full CI is still running on
  an older snapshot at 64%. No deployment/readiness claim; publish directly to main.

## Approved status for composed activation — October 14, 2026

- consume_fresh_basis now shares the direct approval-hook guard: the request must name the
  subject, be APPROVED and still hash to its reviewed content before it can confer authority
  on a child action. Non-approved requests refuse before content evaluation. Existing import
  activation benefits; the migration promotion subject remains unregistered.
- PostgreSQL tests cover all five request states. Final unit/PG suite: 106 passed (9.01s).
  All 18 import commit cases also passed; 124 unique cases verified across the two runs.
  Four new test-only recorder assertions were corrected before the final successful run.
  Strict production plus PG-test typing (889 sources) and Ruff pass. Evidence:
  .run/approval-consumption-status-{tests,final,types}.log.
- Judgement creation under independent approval, policy/report checks, final activation and
  atomic promotion remain outstanding. Publish directly to main; no deployment/readiness claim.

## Proposed migration judgement content — October 14, 2026

- Basis v4 includes exact proposed conclusions/rationales/questionnaires and stable targets.
  Distinctness follows published templates, binding version ids/hashes; collectibility has
  one proposed probable assessment per enabled book at inception (BS3-D-23/26). These remain
  proposals, with no fabricated reviewer or reviewed records. Fresh target resolution refuses
  a missing obligation instead of falling back to the contract.
- Real PostgreSQL witness: two obligation proposals and ASC606 collectibility, IFRS15 adds
  its own proposal, no judgement rows persist, and rollback restores the original plan.
  Final domain/PG/architecture suite: 84 passed (26.30s); strict production plus changed
  tests (891 sources) and Ruff pass. Logs: .run/migration-judgement-plan-*.log.
- Approved record creation, assessment events and their resulting output proof, final
  activation, policy/report checks and atomic promotion remain unfinished. Older immutable
  full CI is live at 94%. Publish directly to main; no deployment/readiness claim.

## Full CI results and catalogue/isolation repairs — October 14, 2026

- Immutable 165d63c backend run finished in 5h 11m 13s: 10,843 passed, 33 failed,
  1 skipped, 3 xfailed, 640 deselected; CI failed at backend tests. This is an older snapshot.
  Full failure/revalidation inventory: docs/release/CI-2026-10-14.md.
- Reconciled privacy classifications with the current schema/native option terms; updated
  reviewed scope/lock/preview inventories and integration response fixtures, clarified guide
  API paths, and regenerated the frontend as-locked fixture from its API source.
- Downgrade tests start from fresh head. Reset disposes idle app/owner pools to prevent stale
  enum type OIDs after schema recreation; the checked-out database lock remains held.
- Final affected CI-unit recheck: 20 passed (13.61s); privacy/migration isolation suite:
  22 passed (35.33s); frontend as-locked checks: 90 passed (8.13s). Strict production/DB
  support typing (890 sources, explicit package bases) and Ruff pass.
- Remaining: historical report-seed equality, current-main revalidation of 12 other snapshot
  failures, AI audit coverage, lock/relock figure expectations, three expected-failure gaps,
  migration promotion and other release work. No deployment or readiness claim.

## Migrated report catalogue verification — October 14, 2026

- Revalidated the remaining 12 integration failures on c8bc3fc: 10 passed, 2 failed
  (142.69s). AI audit lifecycle coverage and lock/relock version expectations remain open.
- Corrected the historical seed test to preserve migration 0048. The full migration-chain
  PostgreSQL comparison verifies all current catalogue fields; four catalogue checks pass
  (6.77s), Ruff/formatting pass. No historical migration changes.
- Evidence and remaining gaps: docs/release/CI-2026-10-14.md. No deployment or readiness claim.

## Reopening report verification — October 14, 2026

- Updated the lock/relock regression for required independently reviewed reopening evidence:
  preserve the hold/release versions, verify the billing version at the latest event date,
  and independently approve the specific late-event waiver through the normal API.
- The real re-close leaves September revenue and RPO unchanged, while contract balances
  reflect the invoice. All five report-figure cases pass (44.05s); strict test typing,
  Ruff and formatting pass. Evidence: .run/report-lock-recheck.log and .run/report-lock-types.log.
- AI audit coverage, other documented implementation gaps and full candidate verification
  remain open. No production-readiness claim or deployment.

## AI provider foundation — October 14, 2026

- Implemented the DG §6.7 request/response protocol and deterministic FakeProvider.
  Exact input-hash fixtures precede version-local defaults; malformed exact fixtures fail
  without fallback. Digests cover exact UTF-8 response text; token/latency fields and path
  selectors are validated. No sockets, sleeps, accounting writes or external calls.
- Provider/configuration/architecture checks: 92 passed (20.88s); strict typing: three
  sources; Ruff/formatting pass. Evidence: .run/ai-provider-final.log and
  .run/ai-provider-types.log.
- AIX remains incomplete: provider selection/live adapter, retained fixtures, schema,
  gateway/jobs, human acceptance and audit lifecycle still required. No AI enablement,
  audit-category exemption, deployment or readiness claim.

## Immutable AI call evidence storage — October 14, 2026

- Migration 0147 adds T-AI-02 ai_model_log with tenant RLS, append-only grants and
  owner mutation guards. Provider/outcome values, SHA-256 digests and nonnegative
  token/latency counters are checked; raw prompt/response text has no column.
- Registered ORM, privacy classification, isolation row builder and sandbox treatment:
  call evidence stays with the source tenant and is regenerated in a sandbox.
- Corrected the migration test's old function count for the existing 0145 ownership
  trigger. API production plus new PG-test strict typing passes (744 sources); Ruff passes.
- Combined migration round trip, DB lint, immutability, RLS, schema/privacy/snapshot
  and import-cycle verification: 127 passed (31.44s), .run/ai-model-log-final.log.
  Typing evidence: .run/ai-model-log-types.log.
- Proposal table/transitions, gateway writes/audit facts and human acceptance remain
  unfinished. The AI lifecycle audit gap remains open; no AI enablement or deployment.

## AI proposal evidence and state guards — October 14, 2026

- Migration 0148 adds T-AI-01, E-73/E-74 and the generated SM-11 transition guard.
  Content/citations and evidence links cannot change. Acceptance/rejection fields are
  set once, complete only in their matching state, and terminal records are frozen.
  Decisions must be a nonempty array; acceptance permissions and decision semantics
  still belong to the forthcoming human command. Expiry is explicitly supplied by its writer.
- Tenant-bound foreign keys reject another tenant's call log or document. Registered
  ORM, privacy, sandbox-regeneration, enum and isolation inventories; updated pinned head.
- Full migration round trip, DB lint, state/immutability/RLS, schema/privacy/snapshot
  and import-cycle checks: 140 passed; single-head check: 1 passed. Strict API/test typing
  passes (745 sources). Evidence: .run/ai-proposal-final.log, .run/ai-proposal-head.log,
  .run/ai-proposal-types.log. Provider/gateway, human acceptance and audit lifecycle
  remain incomplete; AI stays unavailable. No deployment or readiness claim.

## AI SDK adapter and provider selection — October 14, 2026

- Added the official Anthropic SDK (locked 1.14.0), explicit vendor endpoint, 60-second
  timeout, no SDK retries and no SDK telemetry. Secrets resolve lazily through the scoped
  store. Text blocks, usage, model, stop reason, digest and monotonic latency are mapped;
  typed failures produce safe codes and retryability without provider response bodies.
- Tenant disablement/kill switch returns no provider; fake remains the test default.
  Selection constructs no client. All adapter tests use mocked clients; no live AI calls.
- Adapter/configuration/architecture checks: 110 passed; final adapter/configuration,
  licence and notices checks: 55 passed. Strict API/test typing: 747 sources; Ruff passes.
  Logs: .run/ai-sdk-checks.log, .run/ai-sdk-final.log, .run/ai-sdk-types.log.
  Final SDK network-boundary checks: 16 passed, .run/ai-sdk-network-final.log.
- Licence check: 141 packages, zero findings. Development dependency audit: zero Python
  vulnerabilities across all 85 pinned runtime distributions and zero npm advisories;
  .run/ai-sdk-licences.log and .run/ai-sdk-audit.log. Final clean-candidate audit still owed.
- Gateway/jobs, retained prompt fixtures, human acceptance and lifecycle auditing remain
  unfinished. SUPERVISOR VERIFICATION NEEDED: live Anthropic provider smoke test (not run;
  no live calls authorized here). No deployment or production-readiness claim.

## AI request preparation boundary — October 14, 2026

- Moved provider contracts to domain ports, preserving adapter exports, so the forthcoming
  gateway can depend on the protocol without importing a network adapter.
- Added exact UTF-8 template digest checks and canonical request preparation. The explicit
  document-text argument requires opt-in; existing PRV-08 patterns redact values and system
  text. Contact-bearing field names are refused, not silently leaked or collapsed.
- Outgoing messages and configuration are immutable; the input digest binds template/version,
  actual message bytes, model, system text and generation/redaction settings. Floats are
  refused by canonical encoding. Callers still owe authorised, minimised input selection.
- Provider/preparation/configuration/privacy/architecture checks: 165 passed (23.21s).
  Strict API/test typing: 749 sources; Ruff/formatting pass. Evidence:
  .run/ai-preparation-checks.log and .run/ai-preparation-types.log.
- This is not an enabled gateway: job-only authorization, budget reservation, output
  validation, durable attempt/audit writes and human acceptance remain open. No live calls,
  deployment or readiness claim.

## AI extraction output validation — October 14, 2026

- Added an atomic extraction validator: response digest/completion, strict JSON and unique
  allowed paths, confidence range, authorised document identity and Unicode page-span bounds.
  Low confidence below 0.75 is marked for review; no field is automatically accepted.
- Invalid fields refuse the entire proposal. Duplicate JSON keys, nonfinite numbers,
  oversized/deep responses and excessive decimal expansion refuse with safe error codes.
  Immutable canonical values preserve exact decimals without binary floating-point rounding.
- AI/provider/architecture checks: 128 passed; strict API/test typing: 750 sources.
  Evidence: .run/ai-extraction-validation.log and .run/ai-extraction-types.log.
- This helper is not connected to a gateway. Command-specific value schemas, redaction-offset
  mapping, semantic citation review, narrative-number checks, authorised jobs, budgets,
  persistence/auditing and human acceptance remain open. No live calls or deployment.

## Source citation offsets after redaction — October 14, 2026

- PRV-08 now exposes immutable substitution coordinates alongside its existing redacted
  text/counts. Email and international/local phone precedence stays shared with ordinary
  redaction. The mapping stores no removed contact values and stays outside provider input.
- Extraction validation can validate outgoing redacted pages and restore citations to source
  Unicode coordinates. Boundaries inside replacement placeholders refuse the entire proposal;
  complete placeholders map to complete source spans, subject to human viewing authorization.
- Privacy/extraction/architecture checks: 167 passed; strict API/test typing: 751 sources.
  Logs: .run/ai-offsets-checks.log and .run/ai-offsets-types.log. Ruff/formatting pass.
- The future gateway must retain the exact page mappings used for its prompt. Durable
  document extraction, authorized gateway jobs, value schemas, narrative-number checks,
  budgets, lifecycle auditing and human acceptance remain unfinished. No live calls/deployment.

## Retained contract-review prompt — October 15, 2026

- Added the versioned contract-review v1 file with id/version/purpose/output-schema front
  matter, citation rules and instructions to treat document text as untrusted evidence.
- A checked-in digest manifest and bounded loader require registered identifiers, exact file
  bytes and matching metadata. Changes require a new version; no latest-version fallback.
  The complete file is the system message, so preparation binds its full file digest.
- AI/architecture checks: 129 passed (12.01s); strict API/test typing: 752 sources; Ruff passes.
  Offline wheel build passed and packaged prompt bytes match the reviewed source exactly.
  Logs: .run/ai-templates-{checks,types,wheel,package}.log.
- This does not implement the gateway or complete AIX-3. Other prompt kinds, retained response
  fixtures, job authorization/budgets, audited attempt persistence and human acceptance remain
  open. No provider call or deployment; no production-readiness claim.

## Document preparation and citation binding — October 15, 2026

- Added extraction preparation over ordered worker-provided page text. Text sharing disabled
  refuses before page inspection; documents must have 1–600 pages and at most 2 MiB UTF-8
  text before and after redaction. Blank pages retain their original page numbers.
- The retained contract-review template, document UUID and allowed paths feed immutable
  request preparation. Exact outgoing page text is checked against retained redaction maps;
  any serialization/redaction mismatch refuses. Provider payloads exclude source mappings.
- A fake-provider integration check follows preparation through response validation and
  confirms that the cited amount addresses original source characters with low-confidence
  review still required. Tests also cover mutation, Unicode limits and redaction expansion.
- AI/privacy/architecture checks: 195 passed (16.54s); strict API/test typing: 753 sources;
  Ruff passes. Logs: .run/ai-document-preparation-{checks,types}.log.
- PDF extraction/worker limits, authorized file reads, durable text storage, operational
  gateway jobs/budgets/auditing and human acceptance remain open. This helper enables no
  route and makes no live call; no deployment or readiness claim.

## PDF extraction and retained WLD-F-29 evidence — October 15, 2026

- Added pypdf 6.20.1 (BSD-3-Clause), worker-side PDF parsing and context-local stream/tree
  limits. Disabled text sharing refuses before parsing; files over 25 MiB, encrypted/invalid
  PDFs, more than 600 pages, over 2 MiB extracted UTF-8 text and textless documents refuse.
  Empty pages retain their numbering. Parser diagnostics are not returned as error details.
- Generated the four-page synthetic Kinsley Marrow order form and visually checked every
  page. A retained exact-input fake response now exercises all nine documented fields,
  confidences and three review flags through PDF parsing, preparation and citation validation.
  These checks create no proposal and apply no accounting fields or commands.
- AI/architecture/licence-unit checks: 154 passed (17.71s); strict API/test typing: 755 sources;
  Ruff and lock checks pass. Licence inventory: 142 packages, zero findings. Development
  dependency audit: all 86 pinned Python distributions and npm report zero vulnerabilities.
  Logs: .run/ai-pdf-{checks,types,licences,audit}.log; rendered pages: .run/ai-pdf-preview/.
- Worker process memory/time enforcement remains unverified: parser caps are not a process
  sandbox. Authorized reads, durable AI_DOCUMENT_TEXT files, job integration, budgets, audit
  writes and human acceptance remain open. No live provider call, deployment or readiness claim.

## PDF subprocess resource boundary — October 15, 2026

- Added the operational parser entry point as an isolated-interpreter subprocess with a
  minimal environment, closed inherited descriptors, discarded parser stderr and strict
  response validation. Text disablement and file caps refuse before child launch.
- The Linux child applies 512 MiB address-space and 15-second CPU limits before importing
  pypdf, and disallows core dumps/file writes through resource limits. The parent enforces
  30-second wall time; real-child testing confirms timeout kill/reap and secret removal.
  Unsupported hosts or unavailable resource limits fail closed, never parse in-process.
- AI/architecture checks: 180 passed, two Linux-only enforcement tests skipped on this Mac;
  strict API/test typing: 757 sources; Ruff passes. Logs: .run/ai-pdf-isolation-{checks,types}.log.
- Docker executable exists but its daemon cannot be reached. SUPERVISOR VERIFICATION NEEDED:
  Linux successful PDF parsing plus actual address-space/CPU exhaustion tests in the worker
  environment. These are not established by the local transport tests. No deployment.
- AI_TASK integration remains absent; the new subprocess entry point is not yet called by
  an enabled job. File authorization/storage, gateway budgets/auditing and acceptance remain open.

## AI job initiator authorization — October 15, 2026

- Added current-grant authorization for a persisted AI_TASK attempt. It verifies the live
  job/task identity, requires the stored human creator to match the SYSTEM on-behalf-of id,
  and requires active user, workspace and membership before resolving permissions.
- The returned USER principal uses ai.use entity scope rather than SYSTEM's all-entity scope
  or the union from unrelated roles. It carries no recreated login or MFA evidence. Callers
  still owe per-file/report permissions and must use this narrowed context for retrieval.
- Eight PostgreSQL cases cover scoped access, revoked grants, suspended membership/workspace,
  disabled user, completed jobs, substituted initiators and inline/wrong-attempt refusal.
  Combined AI/architecture checks: 172 passed, two Linux parser-limit tests skipped;
  strict API/test typing: 758 sources; Ruff passes. Logs: .run/ai-access-{checks,types}.log.
- This is not an enabled AI_TASK handler. Gateway settings/kill-switch checks, budget
  serialization, authorized retrieval, durable attempt/proposal/audit writes and acceptance
  remain unfinished. The isolated local test database was stopped after verification.
  No deployment or production-readiness claim.

## Superseded AI status notes consolidated October 15, 2026

October 14 AI foundation: the request/response protocol and deterministic fixture provider
are implemented, with 32 provider/configuration checks passing. This does not enable AI:
gateway jobs, human acceptance and
lifecycle audit evidence remain unfinished. The AI audit-category failure remains visible.

Migration 0147 now provides append-only, tenant-isolated AI call-log storage and its ORM,
privacy and sandbox classifications. No gateway writes these records yet, so schema
verification does not establish AI audit-lifecycle coverage or operational AI readiness.

An atomic attempt writer now records validated hashes, usage and fixed failure codes
alongside an AUD-FACT event under the requesting user. Commit/rollback and metadata
refusals are verified. It is not yet connected to an operational gateway; proposal
creation, decisions and their lifecycle audit coverage remain unfinished.

The numeric narrative validator now checks figures against supplied evidence at the
currency minor unit, with explicit locale normalization and bounded parsing. This only
establishes numeric membership: authorized retrieval, semantic/citation checks, narrative
proposal generation and deterministic fallback integration remain outstanding. Unsupported
numeric formats refuse rather than being guessed; percentages require displayed units.

Narrative preparation and response selection now use a retained explain-narrative prompt,
strict response hashes/schema, snapshot-bound node citations and cited-only numeric evidence.
Invalid responses select the original deterministic explanation without model text. This is
verified through the fake provider, but remains unconnected to authorized retrieval, AI_TASK,
proposal persistence and the public Explain/API workflow. It is not completed AIX-7 coverage.

AI explanation retrieval now reauthorizes the job's human and intersects ai.use with
contract.read scopes in a PostgreSQL read-only session. It reuses Explain's stored-trace
resolver and historical-period logic; real contract tests verify identity and scope denial.
It is not yet called by a registered AI_TASK handler or public API. Gateway admission,
provider execution, proposal persistence and approval/acceptance remain outstanding;
contract-document and Q&A retrieval are separate unfinished paths.

NUMBER_EXPLANATION now has a transaction-bound proposal writer: it revalidates the
retained trace/request and commits attempt evidence, proposed/failed output and audit
records together. Real-contract tests verify rollback, rejected-text exclusion and no
accounting changes. This does not finish the gateway, retries/crash recovery, public API,
other proposal kinds or human acceptance; the full AI lifecycle gate remains open.

A narrative gateway attempt now composes authorization, effective settings, budget admission,
read-only retrieval, lazy provider execution and committed proposal evidence. Typed provider
errors are logged; a mid-call switch or grant change retains usage without model narrative.
The fake-provider/real-contract path is verified, but no AI_TASK handler or public submission
is registered. Retry scheduling, terminal failure proposals for admission/provider errors,
notifications, idempotent completion and crash/unlogged-call recovery remain unfinished.

The narrative gateway now allows at most three provider attempts with injected 5/10-second
waits. Only classified transient errors retry; each attempt re-enters admission and commits
its log before waiting. Permanent/exhausted provider errors create a failed proposal linked
to the final existing log after reauthorization and evidence checks, without duplicate usage.
The worker still needs to supply real waiting/dispatch, enforce job delivery idempotency and
handle admission failures, notifications and crash recovery. This is not registered job/API
coverage or a completed AI lifecycle gate.

Migration 0149 binds completed narrative proposals to a unique tenant/job and immutable
source fingerprint. Redelivery returns the existing result after current read authorization,
without another model call, including after budget exhaustion or disablement. Migration and
real-contract tests verify these cases. This does not recover unfinished provider calls or
retry counts after a crash, and does not complete job registration or public API delivery.

Migration 0150 adds immutable, tenant-bound provider-call intents, numbered 1–3 per job,
with one optional linked model-log outcome. Populated intent evidence prevents downgrade;
an unlinked intent survives as an uncertain outcome. Gateway write-ahead admission, durable
retry counting and uncertain-call recovery are not connected yet: schema storage alone does
not prevent duplicate calls or account for unknown usage.

The October 15 full architecture run additionally exposed unresolved checks for contract-event
scope/appender registries, AI proposal file ownership/evidence rules, material-right expiry file
bindings, provider clock/test temporary-path rules and AI membership identity reads. The run
recorded 337 passes and 10 failures (.run/ai-intent-checks.log); privacy/snapshot counts and
AI proposal column order were subsequently corrected. A subsequent repair passed 54 targeted checks: the provider now uses the central monotonic
clock; the active AI initiator and shared event-appending helper are correctly registered;
the option-expiry evidence binding is documented; the template test retains an absolute-path
refusal without using a reserved temporary directory. Two of those architecture checks remain
open: AI proposal file ownership and file-evidence retention. The complete architecture suite
and full release gates still require a fresh pass.

AI proposal source and extracted-text references now hold their files against direct erasure,
including after proposal expiry. The existing Controller-reviewed EVIDENCE_SHRED flow can
lift those holds; without durable entity bindings it requires coverage of every tenant entity.
AI_DOCUMENT_TEXT is now encrypted with a per-file key and can be cryptographically erased.
The file-evidence registry check is now resolved; file-read ownership remains open. This does
not complete proposal file-read authorization or the extraction job/storage workflow.
Any experimental plaintext AI_DOCUMENT_TEXT object from an older build needs explicit migration
or regeneration before use; there is no plaintext fallback or automatic conversion.

AI proposal file-read ownership is now registered. Derived document text requires ai.use and
current access to a live source attachment from a same-tenant CONTRACT_EXTRACTION proposal.
Source references add no new read grant; attachment entity scope and voiding remain effective.
Malformed text-to-text links refuse without recursion. Reads do not depend on the AI enable
switch. The dedicated proposal/document-text response API and extraction workflow remain open;
this file-store authorization does not complete those public workflows.

Migration 0148 adds immutable proposal content/citations, tenant-bound evidence references
and SM-11 state guards. The schema and full migration round trip are verified; proposal
creation/acceptance APIs, approval integration and lifecycle audit events remain absent.
Database state guards do not substitute for human command permissions or field validation.

The provider selector and Anthropic SDK adapter are now implemented and mock-tested,
including disablement, safe error classification, timeout and no-SDK-retry settings.
No live provider call has been made. The gateway and audited human workflows remain absent;
these adapter checks do not establish end-to-end AI readiness.

Request preparation now applies the shared contact-redaction patterns, requires opt-in
for its explicit document-text argument, and hashes immutable outgoing content and configuration.
The gateway must still select authorised/minimised facts, enforce job execution and budgets,
validate outputs, and persist audited results. No provider-facing route is enabled by this helper.

Extraction output validation now checks response integrity/completion, unique allowed paths,
confidence and authorised document citation spans, with bounded parsing and decimal expansion.
It refuses an entire invalid proposal and marks confidence below 0.75 for review. This is an
unconnected domain helper: command-specific value schemas, semantic citation review and
narrative-number verification remain open. PRV-08 now retains immutable redaction coordinates,
and extraction validation can restore citations to original Unicode spans, refusing boundaries
inside placeholders. The future gateway must retain the exact mapping for each outgoing page;
durable document extraction and gateway integration remain absent.
Neither span validation nor a high confidence score establishes accounting correctness.

Contract-review v1 now has a retained prompt file, reviewed digest manifest and bounded
loader. Exact file bytes, including metadata, become the system message and template digest;
unknown versions and changed files refuse. The built wheel retains identical prompt bytes.
Other prompt kinds, retained fake-response fixtures and the operational gateway remain open.

October 15 document preparation now binds ordered pages, document identity, allowed paths,
retained template and local redaction mappings into the prepared extraction request. It refuses
text-disabled input, more than 600 pages, and source/redacted UTF-8 text exceeding 2 MiB.
The fake-provider path verifies source citation restoration. This accepts already-extracted
page text; PDF worker extraction, authorized file access, durable document-text storage and
operational gateway execution remain unimplemented.

October 15 PDF continuation: a pypdf adapter now extracts page text with file/page/text
and parser stream/tree limits. A visually checked four-page WLD-F-29 fixture and retained
exact-input fake response cover the nine documented fields and confidence flags through
preparation and citation validation. This supersedes the earlier absence of a PDF parser;
it does not establish a worker service or proposal workflow. Process memory/time enforcement,
authorized source reads, durable AI_DOCUMENT_TEXT storage, jobs and audited acceptance remain
unfinished. Dependency licence and development vulnerability checks passed; final candidate
audit and full release verification are still owed.

October 15 PDF isolation continuation: the operational entry point now launches a private
Python subprocess without inherited secrets, with wall timeout and strict output validation.
The Linux child sets address-space/CPU limits before parser import; unsupported hosts fail
closed. Local tests verify child transport, timeout cleanup, classified exits and unsupported
host refusal. Actual Linux success and memory/CPU exhaustion remain unverified: two tests are
skipped on this Mac, and the local Docker daemon is unavailable. No enabled AI job uses this
entry point yet. This is process resource containment, not a filesystem/network sandbox.

October 15 AI authorization continuation: a job authorization helper now validates a live
AI_TASK attempt and its stored human initiator, checks current user/workspace/membership
status and reloads ai.use grants. Retrieval must use the returned USER principal with its
ai.use entity scope, not the surrounding SYSTEM principal or unrelated role scopes. Real
PostgreSQL checks cover revocation and disabled/stale identities. Per-source permission
checks, settings/kill switches, budgets and operational gateway integration remain open.

October 15 AI settings continuation: a typed settings snapshot now resolves the five AI
registry settings from tenant-bound published versions and retains their source IDs. Effective
enablement also checks workspace status, immediate tenant turn-off and the platform kill switch.
PostgreSQL tests verify these boundaries. The configured monthly budget is read only; token
accounting/serialization, settings command lifecycle and gateway execution remain unfinished.

October 15 AI budget continuation: a tenant-specific advisory lease now serializes admission
against committed UTC-month usage. The caller must hold it through provider execution and
committed attempt logging; busy jobs must requeue. PostgreSQL witnesses cover stale-total
prevention, tenant/month isolation, zero/exhausted budgets and lock loss. This does not reserve
unknown response tokens or recover usage from a call lost before logging. The gateway is still
absent, so these primitives do not establish operational budget enforcement. Lost-connection
cleanup in the shared database session kernel was also repaired and regression-tested.

## Effective AI gateway settings — October 15, 2026

- Added an immutable settings snapshot from explicitly tenant-bound registry rows. All five
  values resolve from one version read at the aware job clock; only published/effective
  versions count. The snapshot retains source version IDs for later call evidence.
- Effective enablement requires an active workspace, published enablement, no immediate
  tenant turn-off and no platform kill switch. Model, sharing/redaction flags and monthly
  token budget are strict typed values; invalid values refuse without leaking their contents.
- Thirteen PostgreSQL cases cover defaults, draft/future versions, provenance, kill switch,
  immediate turn-off, suspended workspace, tenant isolation and malformed values. Combined
  AI/access/architecture checks: 185 passed, two Linux parser-limit tests skipped; strict
  API/test typing: 759 sources; Ruff passes. Final focused settings checks: 13 passed.
  Logs: .run/ai-settings-{checks,types,final-pg}.log.
- This reads the configured budget; it does not reserve tokens or enforce concurrency.
  Operational gateway execution, budget serialization, per-source permissions, attempt and
  proposal/audit persistence, settings command lifecycle and human acceptance remain open.
  No provider call or deployment; isolated test database stopped after verification.

## Serialized AI budget admission and lost-connection cleanup — October 15, 2026

- Added one autocommit session lock per tenant, `erev-ai-budget:<tenant>`, held across
  admission, provider work and committed usage logging by the future gateway. Busy callers
  get no lease. Usage sums all outcomes' input/output tokens in the UTC calendar month;
  equality with the budget and a zero budget refuse before provider work can be admitted.
- PostgreSQL cases prove competing admissions cannot use a stale total, tenant isolation,
  month boundaries/error usage, zero budget, exception release and lost-lease refusal.
  The final focused check also observes the lock connection idle with no open transaction.
- Lost-connection testing found and repaired shared cleanup that accessed connection.info
  while invalidated, masking the original error with a reconnect/rollback failure. Cleanup
  now preserves the original error and discards context without reconnecting; context-free
  SQL remains refused. Two existing session-test annotations were corrected for strict typing.
- Combined checks: 215 passed, two Linux parser-limit tests skipped; strict API/test typing:
  761 sources; Ruff passes. Final budget cases: 6 passed. Logs: .run/ai-budget-{final,types,final-pg}.log.
- This is committed-usage admission, not a reservation for unknown future tokens. Crash
  recovery for a provider call whose usage was never logged remains open, as do the gateway,
  durable per-attempt/proposal auditing and human acceptance. No live calls or deployment.
  Isolated local test database stopped after verification.

## Atomic AI attempt evidence — October 15, 2026

- Added a transaction-bound writer for model-log metadata and its AUD-FACT event.
  It requires a user with ai.use, verifies request/response hashes, validates counters
  and fixed outcome/failure codes, and retains no prompt or response text. Requested
  and resolved model identifiers remain distinguishable. The caller owns commit.
- PostgreSQL tests cover commit/rollback, rejected metadata, human attribution and
  usage retained for invalid output. Audit inventories now recognize the log facts.
- Focused verification: 202 passed, two Linux-only resource-limit tests skipped;
  strict typing passed for 761 sources. Ruff and diff checks pass.
- The operational gateway, proposal creation/acceptance and full AI audit lifecycle
  remain unfinished. No live provider calls or deployment; no readiness claim.

## Numeric evidence validation for AI narratives — October 15, 2026

- Implemented DG-AI-07 numeric membership validation using authorized caller-supplied
  evidence and the engine's exact half-up comparison at the supplied currency minor unit.
  English, German and French numeric formats are explicit; accounting negatives and
  Unicode decimal digits normalize without binary floats or ambient Decimal rounding.
- Valid ISO calendar dates are excluded. Malformed grouping, scientific notation,
  fractions, ambiguous signs, nonfinite evidence and oversized inputs refuse safely.
  Percentages require evidence in displayed units; no implicit scaling is inferred.
- Verification: 197 AI/architecture checks passed, two Linux parser-limit tests skipped;
  final numeric suite 32 passed after the Decimal-context regression fix. Strict typing
  passed for 762 sources; Ruff passes. Logs: .run/ai-numbers-{checks,final,types}.log.
- Numeric membership does not prove semantic support or citation authorization. Narrative
  generation, proposal persistence and deterministic fallback integration remain open,
  along with the broader AI gateway and human workflow. No deployment or readiness claim.

## Numeric-token boundary repairs — October 15, 2026

- Reproduced false acceptances where Unicode separators/invisible characters or malformed
  French grouping split a larger number into smaller allowed values. Those forms now refuse.
- Currency suffixes inside accounting parentheses now preserve the negative sign; trailing
  signs are refused rather than silently discarded. Added 17 regression cases.
- Focused numeric suite: 49 passed; strict typing: 762 sources; Ruff/diff checks pass.
  Broader AI/architecture checks: 185 passed, two Linux-only parser tests skipped;
  log: .run/ai-number-boundaries-checks.log.
- Rechecked publication boundaries: neither research-harness nor docs/research is tracked;
  PolyForm Noncommercial 1.0.0 remains in place. No deployment. Numeric checking remains
  a prerequisite, not evidence that the unfinished AI narrative workflow is complete.

## Cited narrative selection and deterministic fallback — October 15, 2026

- Added the retained explain-narrative v1 prompt and a preparation/selection boundary.
  It snapshots already-authorized explanation nodes, sends minimized trace fields,
  excludes other currencies and refuses privacy transformations that change evidence.
- Responses need exact hashes, complete output, strict JSON and nonempty unique node
  citations from the snapshot. Only cited nodes contribute allowed figures. Unsupported
  output returns the original deterministic narrative with no model text or citations.
- Fake-provider tests cover supported/untraced output; additional cases cover malformed
  responses, refusal/truncation, forged citations, immutable evidence and currency precision.
- Verification: 244 AI/architecture tests passed, two Linux-only parser tests skipped;
  typing passed for 763 sources; Ruff/diff checks pass. Offline wheel build passed and
  packaged prompt bytes match source. Logs: .run/ai-narrative-{checks,types,wheel}.log.
- This does not register an AI_TASK handler or endpoint, persist proposals or establish
  authorized retrieval. Those gateway responsibilities and the human acceptance workflow
  remain open. No live provider calls, deployment or production-readiness claim.

## Authorized read-only AI explanation retrieval — October 15, 2026

- Added a worker retrieval boundary that reauthorizes the persisted AI job's human,
  intersects ai.use and contract.read entity scopes, and reads under that user's
  PostgreSQL read-only context. The job attempt is rechecked in the read transaction.
- Explain now exposes its existing resolver/trace-integrity path as one trace-id and
  explanation snapshot. AI retrieval matches the public route's to-date period selection
  and derives numeric precision from the resolved currency table before preparation.
- PostgreSQL tests verify actor/scope settings, write refusal, revoked read permission
  and disjoint grants. A real computed K-01 contract verifies stored trace/amount identity,
  August historical-period selection and not-found for an out-of-scope entity reader.
- Verification: 232 targeted checks passed, two Linux-only parser tests skipped;
  strict typing passed for 765 sources; Ruff/diff checks pass. Logs:
  .run/ai-retrieval-{final,types}.log. Isolated local test cluster stopped afterward.
- Gateway/settings/budget integration, provider execution, persistence, public endpoints
  and human decisions remain open. This does not authorize deployment or establish
  end-to-end AI readiness. No live provider calls or external accounting sign-off.

## Atomic narrative proposal persistence — October 15, 2026

- Added NUMBER_EXPLANATION persistence under a scoped human unit of work. Before writing,
  it reloads the retained trace, rebuilds the request and validates the complete request
  against the prepared evidence; caller-substituted value mappings cannot support figures.
- Successful output writes a proposed trace-subject narrative and node citations; unsupported
  output writes a failed proposal with a fixed problem code and empty content/citations.
  Both retain usage and human attribution, default to 30-day expiry and leave acceptance empty.
- Attempt log, proposal and AUD-CMD/AUD-FACT events share the caller's transaction. Proposal
  audit events name the trace version's visible obligation contracts and retain content/citation
  hashes rather than narrative text. Registered the proposal audit type and unlabelled identity.
- Real K-01 integration verifies commit, failure, rollback, request tampering, scope refusal,
  forged value mappings, audit attribution and unchanged accounting versions. Fixed explicit
  SQL NULL handling for the successful proposal's JSONB problem column.
- Verification: 241 targeted tests passed, two Linux-only parser tests skipped; strict typing
  passed for 765 sources; Ruff/diff checks pass. Logs: .run/ai-proposal-write-{final,types}.log.
- The caller still owes fresh authorization, settings/budget admission and commit before lease
  release. Gateway/job dispatch, public APIs, other proposal kinds and human decisions remain
  unfinished; the full AI audit-lifecycle gate stays open. No deployment or readiness claim.

## Composed narrative gateway attempt — October 15, 2026

- Connected current persisted-job authorization, effective switches/settings, serialized
  budget admission, read-only source retrieval, lazy provider construction and committed
  narrative proposal evidence. The budget lease spans provider work through the usage commit;
  no SQL transaction spans provider execution. Busy admission performs no model call.
- Settings and human/source authorization are rechecked after a response. If a switch or
  permission changes mid-call, usage is retained without retaining the returned narrative.
  Typed provider errors/timeouts are logged and propagated for the future retry policy.
- Real K-01/fake-provider test verifies default disablement, competing admission, success,
  timeout, mid-call platform disablement and grant revocation, then exact budget exhaustion.
  It observes no idle-in-transaction SQL session during provider work and no competing lease.
- Verification: 272 combined tests passed, two Linux-only parser tests skipped; the expanded
  final gateway scenario passed; strict typing passed for 766 sources; Ruff/diff checks pass.
  Logs: .run/ai-gateway-{checks,final,types}.log. Local test cluster stopped afterward.
- Still no registered AI_TASK handler/public submission: retry scheduling, durable failure
  proposals for rejected admission/provider errors, notification and crash/unlogged-call
  recovery remain open. Existing request/proposal idempotency is not yet a gateway guarantee.
  Other AI tasks and human acceptance remain unfinished. No deployment or live provider calls.

## Bounded narrative retries and terminal provider failure — October 15, 2026

- Added a three-attempt gateway wrapper with injected 5/10-second waits. Only classified
  transient codes retry, even when a provider mislabels a permanent error as retryable.
  Each attempt repeats admission; no SQL transaction or tenant budget lease spans a wait.
- Permanent/exhausted provider errors create a failed proposal linked to the final committed
  attempt. The writer rechecks source evidence, human/scope, log ownership, request/model/
  template parameters, outcome and absence of a response; usage is not logged twice.
- Real-contract tests cover three failures, one permanent failure, eventual success,
  disablement during a wait, committed logs before waits and success-log substitution refusal.
  Refactored shared trace verification and proposal insertion without changing normal output.
- Verification: 262 targeted tests passed, two Linux-only parser tests skipped; strict typing
  passed for 766 sources; Ruff/diff checks pass. Logs: .run/ai-retries-{final,types}.log.
  The isolated local test cluster was stopped after checks.
- The worker must still supply waiting/dispatch and delivery idempotency. Durable admission
  failures, notifications, crash/unlogged-call recovery and other proposal workflows remain
  open; no AI_TASK handler/public API is registered. No deployment or readiness claim.

## Completed AI job redelivery protection — October 15, 2026

- Migration 0149 adds optional immutable proposal job/source-hash bindings with a tenant
  foreign key, paired digest check and one-proposal-per-job unique index. Existing rows stay
  unbound. Downgrade refuses populated completion evidence; metadata/privacy declarations match.
- The narrative gateway checks completed jobs under its budget lease before new-call admission.
  A redelivery rechecks human/source access and the stored trace's visibility, then returns the
  original proposal even after budget exhaustion or disablement, without a provider call.
  Changed source inputs or token limits refuse instead of reusing an unrelated result.
- Both successful and terminal-failure writers bind the job. Tests verify normal/failed
  redelivery, unchanged call counts, budget/kill-switch behavior, tenant FK, uniqueness,
  application and owner immutability, downgrade refusal and a full migration round trip.
- Verification: 20 gateway/privacy/head checks passed; 265 migration/AI/architecture checks
  passed with two Linux parser-limit skips; typing passed for 769 sources; Ruff/diff pass.
  Logs: .run/ai-job-completion-{checks,types}.log and .run/ai-job-binding-final.log.
- This protects completed results. Recovery between a provider call and its committed result,
  retry-count recovery for unfinished jobs, admission failures, job/API registration and the
  remaining AI workflows are still open. No deployment or production-readiness claim.

## Durable AI call-intent storage — October 15, 2026

- Migration 0150 adds immutable human-attributed call intents with tenant/job FKs,
  request/source digests, attempt numbers 1–3 and unique job/attempt keys. A nullable,
  unique tenant/intent model-log link permits at most one outcome. Populated intent
  evidence blocks downgrade, including starts with no outcome. Metadata/privacy and
  sandbox classifications match; intents are never copied into another tenant.
- PostgreSQL tests verify committed unresolved starts, tenant isolation, duplicate
  rejection, application/owner immutability and downgrade refusal. Fixed proposal ORM
  column order to match the data model and restored head after the older downgrade test.
- Final migration/metadata/privacy/snapshot checks: 100 passed; strict typing: 769 sources;
  Ruff/diff passed. Logs: .run/ai-intent-{final,types}.log. Broader architecture run found
  seven still-open checks, recorded in LIMITS-1.0.md; this is not a full-suite pass.
- Runtime write-ahead admission, durable retry counting and uncertain-call recovery are
  still required. This storage foundation does not yet prevent duplicate provider calls.
  No deployment or production-readiness claim; independent accounting sign-off remains open.

## Architecture repair after broad verification — October 15, 2026

- Provider timing now uses erev_api.clock.monotonic, retaining the injected duration source.
  The absolute-path template rejection fixture no longer names a reserved temporary directory.
- Registered the AI initiator's existing ACTIVE user/membership identity query with its reason.
  Updated computation-scope and stream-ending registries to name the shared _record_events
  function introduced for option expiry; both public event paths retain the same guards.
- Registered MaterialRightExpireIn evidence through the existing evidence_errors/file_access
  binder, matching the route and the authoritative data-model table.
- Verification: 49 provider/template/architecture checks and five file-binding checks passed;
  strict typing passed for 767 sources; Ruff/diff passed. Logs: .run/architecture-repair-
  checks.log and .run/expiry-binding-checks.log. Five of the seven
  outstanding architecture failures are resolved; AI proposal file ownership and evidence
  retention remain open. This is not a complete architecture or release-suite pass.
- Work remains on call-intent gateway integration and the other implementation/release gaps.
  No deployment or readiness claim; direct main publication continues.

## AI proposal evidence retention and encrypted text — October 15, 2026

- Source and extracted-text references now hold their files against direct shredding even
  after proposal expiry. Existing Controller-reviewed EVIDENCE_SHRED approvals lift the holds;
  no durable entity binding exists, so review must cover every tenant entity.
- AI_DOCUMENT_TEXT now uses per-file encryption. The integration test proves ciphertext at
  rest, decryption before erasure, direct-refusal audit, separate approval, sidecar destruction,
  FILE_SHREDDED on later reads, and retention of the expired proposal/source references.
- Verification: 33 retention/erasure/registry checks passed; the strengthened byte-level test
  passed separately; strict typing passed for 768 sources; Ruff/diff passed. Logs:
  .run/ai-file-retention-final.log, .run/ai-file-erasure-bytes.log and
  .run/ai-file-retention-types.log. Fixed two pre-existing test typing issues found by that run.
- The evidence-registry failure is resolved. Proposal file-read ownership remains open, as do
  extraction workflow integration, call recovery and other release gaps. Experimental plaintext
  AI_DOCUMENT_TEXT objects from older builds require explicit migration or regeneration;
  there is no plaintext fallback. No deployment or production-readiness claim.

## AI document file-read authorization — October 15, 2026

- Registered proposal source references without granting source access. Derived text now
  requires ai.use and current access to an unshredded source attachment of a same-tenant
  CONTRACT_EXTRACTION proposal. Non-extraction, missing-source and recursive text links refuse.
- PostgreSQL tests cover uploader access, another contract reader's entity permissions,
  attachment voiding, lost AI permission, source shredding, operator/foreign-tenant denial,
  reads while AI is disabled and conservative all-entity erasure scope.
- Focused checks: 14 passed; strict typing: 768 sources; Ruff/diff passed. Logs:
  .run/ai-file-read-{final,types}.log. Full architecture plus existing file API checks:
  292 passed in 226.83s (.run/ai-file-access-regression.log); this is not full release CI.
- Consolidated contradictory historical AI paragraphs in LIMITS-1.0.md into current status;
  preserved the superseded notes in BUILD-HISTORY-2026-10-07.md.
- Dedicated proposal/document-text response APIs, extraction job integration and write-ahead
  call recovery remain unfinished, along with other implementation and release gates.
  No deployment or production-readiness claim; independent accounting sign-off is still open.

## Audited AI call-intent writer — October 15, 2026

- Added a transaction-bound writer that locks the human-owned RUNNING AI_TASK job,
  validates exact request/source hashes, assigns consecutive starts up to three and writes
  immutable intent plus AUD-FACT evidence atomically. Unresolved prior starts refuse without
  creating a usage log. The caller must commit before executing a provider call.
- Attempt outcomes can now link to an intent only when provider, request hash and human
  match; duplicate outcomes and budget/disabled admission records cannot close an intent.
  Shared request validation keeps arbitrary parameters and model text out of retained evidence.
- Tests cover rollback/audit atomicity, unknown outcomes, changed input, wrong human/provider,
  duplicate outcomes, attempt exhaustion and invalid/nonrunning job ownership. Broad AI and
  audit-key regression: 224 passed, two Linux parser-limit tests skipped; strict typing:
  768 sources; Ruff/diff passed. Logs: .run/ai-intent-writer-{final,types}.log.
- This is a required writer foundation, not operational crash protection: gateway integration,
  durable retry classification/recovery and unknown-usage handling remain open, as do the
  other implementation/release gates and independent accounting sign-off. No deployment.

## Gateway call intents and restart recovery — October 15, 2026

- The narrative gateway now commits an intent before calling the provider, then links each
  outcome to that intent. Completed proposals keep their existing idempotent delivery path.
  Unobserved outcomes refuse AI_OUTCOME_UNKNOWN; returned but invalidated results require
  reconciliation. Neither path silently calls again or invents a zero-usage outcome.
- Logs retain allow-listed provider failure codes and retry decisions. Restarted gateways
  honor remaining backoff and the durable three-attempt limit; permanent/exhausted failures
  finalize their failed proposal without another call. Proposal writers verify intent/job/
  source bindings, preventing evidence reuse under another job.
- Tests verify committed starts visible inside provider execution, crash during the call,
  lost result before commit, restarted transient/permanent/exhausted failures, bounded calls,
  waits without budget leases, complete intent/outcome linkage and metadata refusals.
- Full AI/architecture regression: 493 passed, two Linux-only parser-limit skips (262.18s);
  strict typing passed for 770 sources; Ruff/diff passed. Logs: .run/ai-recovery-{final,types}.log.
- Unknown usage/reconciliation, durable admission failures, registered jobs, public AI/human
  workflows and the other release gates remain open. This is not full release CI or accounting
  sign-off. No deployment; verified work is published directly to main.

## Tenant budget quarantine for unobserved calls — October 15, 2026

- Budget admission now refuses while any tenant call intent lacks an outcome, across month
  boundaries. Another job cannot consume an understated total after a worker crash.
- After successful admission, the live lease binds one newly committed intent of its human
  caller. Only that intent is excluded from the post-response check; another unresolved start,
  replacement lease, different human or anonymous context cannot use the exemption.
- Tests cover old unresolved calls, tenant isolation, current-call completion, fresh-lease
  refusal, known-outcome release/usage accounting, other-human binding refusal and a separate
  gateway job after simulated crash/lost result. AI/session regression: 233 passed, two Linux
  parser-limit skips; two additional ownership tests passed; typing: 769 sources; Ruff/diff pass.
  Logs: .run/ai-uncertain-budget-{final,types}.log and .run/ai-budget-intent-owner.log.
- This blocks unobserved calls; it does not invent usage or add a reconciliation override.
  Returned provider errors without token counts, unknown-usage reconciliation, public workflows
  and other release gates remain open. No deployment or production-readiness claim.

## Distinguish missing AI usage from reported zero — October 15, 2026

- Attempt logs now derive immutable usage_evidence metadata: REPORTED for validated response
  counters, NOT_SENT for disabled/budget admission refusals, UNKNOWN for response-less errors.
  Caller request parameters cannot supply the marker; historical logs are not rewritten.
- Failed-proposal recovery recognizes the marker while requiring UNKNOWN for a response-less
  provider failure. Exact request hashes and strict metadata comparisons remain enforced.
- Regression: 230 passed, two Linux-only parser skips (66.77s); typing passed for 768 sources;
  Ruff and diff checks passed. Logs: .run/ai-usage-evidence-{final,types}.log. Six zero-counter
  cases distinguish evidence categories; a forged request marker refuses without log/audit writes.
- This is durable evidence groundwork. Budget admission still needs enforcement/reconciliation
  for returned errors with unknown usage, including historical evidence and bounded retries.
  Public AI workflows and all other release gates remain open. No deployment or readiness claim.

## Budget admission for unknown provider usage — October 15, 2026

- Tenant admission now refuses returned errors with unknown usage, including historical
  response-less errors without a marker. The refusal spans jobs and month boundaries; the
  current intent's lease exemption cannot hide a committed unknown-usage outcome.
- ProviderError can carry typed AIUsage. The writer validates counters, rejects conflicting
  response/admission evidence, and retains reported error usage without a response body.
  Fresh admission counts this usage; bounded retries and terminal/restarted failure recovery
  preserve reported counters. Legacy unsent admission records remain distinguishable.
- The current Anthropic adapter reports no usage on exceptions, so those errors block new
  calls. No reconciliation command, automatic expiry, zero estimate or override was added.
  Reconciliation and the remaining public workflows/release gates are still outstanding.
- Broad AI/budget regression: 260 passed, two Linux-only parser-limit skips (84.25s);
  final gateway recovery verification: 12 passed (57.50s), .run/ai-unknown-usage-recovery.log.
  Strict typing passed for 771 sources; Ruff/diff checks passed. Logs:
  .run/ai-unknown-usage-{final,types}.log. No deployment or production-readiness claim.

## Provider response usage preservation — October 15, 2026

- Anthropic message usage now validates strict nonnegative counters and includes cache-read
  plus cache-creation input tokens in the total. Optional absent/null cache fields count as zero;
  output/cache breakdowns are not counted twice, and stored totals must fit int32.
- Rejected response metadata/content preserves valid usage via ProviderError. Missing/malformed
  usage remains UNKNOWN; SDK exceptions never invent counts. No raw response body or fabricated
  response hash is retained on these errors.
- Mocked adapter-to-gateway checks verify a failed proposal links to reported usage and counts
  40 tokens, while invalid counters produce unknown usage and keep tenant admission blocked.
  Unit coverage includes cache totals, invalid/absent counters, overflow, invalid metadata and
  malformed content. Regression: 312 passed, two Linux parser-limit skips (67.12s); typing passed
  for 769 sources; final adapter/import-boundary checks: 69 passed (10.23s); Ruff/diff passed.
  Logs: .run/ai-adapter-usage-{final,types,boundary}.log.
- No live provider calls or deployment. Unknown-usage reconciliation and the remaining product,
  accounting and release-verification gates are still open; this is not production readiness.

## Broader readiness verification — October 15, 2026

- Full repository typing passed (917 Python sources plus frontend TypeScript); production build
  and backend imports passed. All 2,109 frontend tests in 196 files passed (174.31s).
- Full lint found a mocked SDK synthetic-key literal requiring an exact-line scanner exception,
  and a test module-name collision between AI prompt and policy-template tests. Added only the
  scoped fixture exception and renamed the AI test module without changing its assertions;
  both modules now collect together (28 tests). Full lint passed, including collection of
  12,015 tests and validation of 502 control-tagged tests.
- Complete backend unit/architecture verification subsequently finished; see the latest note
  and .run/readiness-unit-architecture-oct15.log. Other logs use .run/readiness-*-oct15.log.
- Details: docs/release/VERIFICATION-2026-10-15.md. Public visibility, main default, research
  exclusions and noncommercial licence verified. These development checks are not full CI,
  independent accounting sign-off or production readiness. No deployment.

## Immutable dependency audit — October 15, 2026

- make audit-deps passed on clean 621d412 in an immutable context: 86 of 86 pinned Python
  packages audited, zero Python vulnerabilities; zero npm advisories at all severities.
  Eight platform markers were removed for complete pinned-package coverage. Source and
  installed dependency hashes remained unchanged. Report and digest are recorded in
  docs/release/VERIFICATION-2026-10-15.md; log .run/readiness-audit-deps-oct15.log.
- Backend unit/architecture verification has since completed; its failures and focused repairs
  are recorded in the latest note and docs/release/VERIFICATION-2026-10-15.md.
  Historical-report cutoff repair also requires ledger-seal compatibility: LINE_MEMBERS
  dynamically includes every stored line column, so adding a timestamp alone changes hashes.
- Full implementation/release verification and independent accounting sign-off remain open.
  No deployment. Verified dependency audit is not a production-readiness claim.

## Backend broad-run isolation repairs — October 15, 2026

- The complete unit/architecture selection finished: 5,609 passed, two failed, two Linux-only
  skips in 1,364.71s. Preserve this as a failed original run, not a full green gate.
- AI intent/job-binding downgrade tests now reset to a data-free head first and are included
  in the migration-walk inventory. The process-script lifecycle test explicitly selects the
  runtime directory matching its probe paths instead of inheriting the repair runner's override.
- Focused revalidation: 15 passed (44.72s), including both failures, process-script checks,
  both actual AI database downgrade guards and the full migration round trip. Strict typing
  for four changed tests, Ruff and diff checks passed. Logs:
  .run/readiness-isolation-{repairs,types}-oct15.log. Full selection not repeated after repairs.
- No broad backend process remains running. Complete CI and other implementation/release gates,
  unknown AI usage reconciliation and independent accounting sign-off remain outstanding.
  Details: docs/release/VERIFICATION-2026-10-15.md. No deployment or readiness claim.

## Historical line insertion cutoff — October 15, 2026

- Migration 0151 adds a database-owned insertion stamp included in new line seals.
  Historical report/API predicates use it; record/current/close predicates retain recorded_at.
- Nine focused tests passed (72.72s): upgrade/downgrade refuse populated ledgers without
  changing rows or seals; 0124 historical fixture remains valid; a transaction begun before
  the cutoff cannot expose its later insert. Log: .run/server-time-migration-guards.log.
- Mypy passed 771 sources; 1,141 report/journal unit tests passed (7.04s), recorded in
  .run/server-time-unit-reports.log. Changed Python formatting and Ruff checks passed.
- Broad report/ledger/API/privacy/snapshot/migration run finished: 379 passed, one failed
  (1,701.70s). The API test still expected historical visibility at the frozen application clock;
  it now checks database instants before/after posting and excludes the earlier business stamp.
  Follow-up: 26 passed, one strict expected failure for overlapping commit visibility (123.56s).
  Log: .run/server-time-followup.log; full evidence in VERIFICATION-2026-10-15.md.
- Architecture: 269 passed, one column-order mismatch (231.36s); documentation corrected and
  the exact failed check passed (1.22s). Logs: .run/server-time-architecture.log and
  .run/server-time-drift-recheck.log. Full architecture selection not repeated.
- make lint passed (.run/server-time-lint.log): 142 dependency licenses, zero secret findings,
  registry/fixture checks and 502 control-tagged tests collected successfully.
- Insertion time is not commit time. The 0152 follow-up above closes posting splits; overlapping
  commits remain unresolved. See LIMITS-1.0.md. No readiness claim or deployment.

## Historical posting completion — October 15, 2026

- Migration 0152 adds database-owned sealed_server_at after balance/chain validation. Historical
  predicates now require the complete posting's seal by the cutoff, as well as line insertion;
  record/current/close behavior remains on its application-clock basis. Entity scope stays on
  the outer line query; the tenant-scoped seal prevents hidden sibling lines from splitting it.
- Core database checks: 19 passed, one strict expected failure for overlapping commit visibility
  (140.88s). Follow-up: nine passed (52.00s), including forged timestamp override, application/owner
  immutability, APIs, tenant isolation, older migration guards and retained AI intents.
- Unit/architecture selection: 1,192 passed (17.77s). Strict typing passed 771 sources. Logs:
  .run/seal-time-{core,followup,unit,types-final}.log. Full make lint passed;
  .run/seal-time-lint.log (502 control-tagged tests collected).
- Populated seals cannot cross 0152: the earlier server completion instant cannot be reconstructed
  and downgrade cannot discard it. The stamp is immutable seal metadata outside the line hash.
  PostgreSQL commit visibility remains open; no deployment or production-readiness claim.

## Full PostgreSQL revalidation — October 15, 2026

- Complete PostgreSQL selection on unchanged 80fba4c: 669 passed, six failed (439.45s), recorded
  in .run/seal-time-full-pg.log. Full typecheck passed 919 Python sources and frontend checks
  (.run/seal-time-full-typecheck.log). This was a failed database run, not a release pass.
- Four failures came from the AI proposal index placing enum filters before created_at under
  RLS. New migration 0153 moves the date ahead of those filters; ALLOWED is unchanged. A real
  application-role plan now proves the date bounds the scan and enums remain filters.
- The trigger inventory now names both server timestamp triggers. The AI-log retention test
  separately verifies ordinary truncate's FK refusal and CASCADE reaching the append-only guard,
  then checks all retained rows are unchanged. No permission or retention rule was relaxed.
- Focused revalidation: 21 passed (31.41s), including all failed cases and a full migration
  round trip. Strict typing passed 772 sources. An initial missing unique=False migration helper
  argument was caught and corrected before this recheck. Logs: .run/full-pg-repairs-recheck.log
  and .run/full-pg-repair-types-recheck.log.
- Full lint passed (.run/full-pg-repairs-lint.log). Complete PostgreSQL rerun: 676 passed
  (496.12s), .run/full-pg-repairs-all.log. This is development verification; full immutable CI,
  remaining implementation and independent accounting sign-off are still required. No deployment.

## Narrative worker dispatch — October 15, 2026

- Registered the narrative AI_TASK handler and connected the worker to the existing gateway.
  Queue payloads admit source selectors only; invalid/extra input is refused without persisting
  its values in validation diagnostics. Provider construction remains lazy after admission.
- The gateway owns provider retries and waiting; registry retry policy remains one attempt.
  Completion returns the durable proposal identity, including a retained provider-failure
  proposal, and does not signify human acceptance or accounting approval.
- Verification: 33 unit/worker/layer checks passed; 13 real-database retry/recovery scenarios
  passed, with completed paths dispatched through the new handler and repeated without a new
  provider call. Strict typing passed 773 sources; full make lint passed. Logs:
  .run/ai-job-dispatch-{tests,pg,types-final,lint}.log. No live provider calls or deployment.
- Public submission, other AI operations, admission-failure evidence, notifications, human
  review and unknown-outcome/usage reconciliation remain open; this does not close AI lifecycle
  verification or establish production readiness.

## AI cancellation boundaries — October 15, 2026

- Narrative tasks now stop cooperatively before another provider call and during retry waits.
  Waits use one-second chunks with attempt-fenced heartbeats and cancellation checks, outside
  transactions and the tenant budget lease. A lost attempt stops without another wait/call.
- An already-started call retains its usage and outcome; cancellation does not erase logs or
  completed proposals. The handler returns control for the registry to settle CANCELLED.
- Real registry checks passed for cancellation before dispatch and during a retry wait, proving
  zero/one calls respectively and retained evidence without a synthetic proposal. The fixture
  now inserts final immutable queue parameters rather than attempting to rewrite them.
- Unit/worker/layer selection: 36 passed; final focused unit selection: 15 passed. Strict typing
  passed 773 sources. Initial test-only issues (single-call token expectation, immutable fixture
  params and an explicit duplicate mypy source) were corrected. Logs are .run/ai-cancellation-*.log.
- Full AI domain database selection passed all 19 cases (.run/ai-cancellation-all-pg.log);
  full make lint passed (.run/ai-cancellation-lint-final.log).
- Public AI workflows and independent accounting acceptance remain unfinished. No live provider
  calls or deployment; this change is not a full readiness or immutable-CI result.

## Immediate tenant AI disable — October 15, 2026

- Added POST /tenant/ai/disable with workspace-wide settings.manage, fresh MFA, a required
  comment and normal command idempotency. It records the human/time, cancels only this tenant's
  queued AI tasks and appends ai.disabled plus per-job cancellation evidence in one transaction.
  Repeats return the original timestamp without duplicating switch/cancellation events.
- Running calls retain evidence under the gateway's existing setting rechecks. The switch
  overrides a published ai.enabled=true policy; other tenants and queued non-AI jobs are intact.
- Verification: five tenant/API/scope regressions passed, then two API cases passed with a
  published-enabled policy; 25 route/layer checks passed. Full typecheck passed 922 Python
  sources and frontend checks. Full lint and OpenAPI generation passed. Logs:
  .run/ai-disable-{api,regressions,enabled-policy,architecture,typecheck,lint,openapi}.log.
- One initial typing issue on a database timestamp was corrected with an explicit type check.
  No deployment or live provider calls. Policy-publication clearing of the emergency switch,
  public AI submission, proposal review and other outstanding readiness work remain open.

## Approved AI re-enable publication — October 15, 2026

- A new AI policy publication with ai.enabled=true clears the emergency switch in the same
  transaction, with ai.enabled audit evidence linked to its approval and registry version.
  Replaying an already-published version cannot undo a later disable; false publications leave
  the switch intact. No direct enable command was added.
- First enablement and clearing a switch require independent human configuration approval plus
  workspace-wide settings.manage. This also covers inherited ai.enabled=true values. A refused
  reviewer rolls back the decision/publication. Budget-only edits while enabled retain normal
  routing; tenant locking serializes switch changes with the publication decision.
- Final verification: 21 database lifecycle/approval/scope/disable cases passed; 53 unit/layer
  checks passed. Full make lint and make typecheck passed (922 Python sources plus frontend).
  Logs: .run/ai-reenable-{regressions-final,unit-final,lint-final,typecheck-final}.log.
  The initial test used an older non-MFA author session; it was corrected to the enrolled session.
- Public submission/review, broader AI sensitive-setting approval coverage, unknown usage/outcome
  reconciliation and the other release gaps remain open. No live provider calls or deployment.

## Sensitive AI configuration approval — October 15, 2026

- Model changes, including returning a custom model to the catalogue default, and enabling
  contract-text sending now require independent workspace-administrator review in addition to
  configuration approval. The submitted whole values are compared with their predecessor and
  defaults, so inherited values and unrelated edits do not create extra approval requirements.
- The rule applies while AI is disabled too. Approved model/text changes alone never clear the
  emergency switch. Turning text sending off retains normal routing. Existing first-enable,
  re-enable, publication replay and budget-edit behavior remains covered.
- Verification: 25 database regression cases passed, followed by five API cases checking actual
  resolved settings after publication. 53 unit/layer checks, strict typing (773 sources) and
  full make lint passed. A test's nullable timestamp assertion was made explicit for typing.
  Logs: .run/ai-sensitive-{regressions,effective-settings,unit,types-final,lint}.log.
- Provider selection remains process configuration; tenant approval gating of provider changes
  is still open, along with public submission/review and other release requirements. No live
  provider calls or deployment; this is development evidence, not a full release pass.

## Number-explanation submission — October 15, 2026

- Added POST /ai/explanations for the number-explanation form: 202 API-S-Job with Location,
  normal idempotency and the initiating human. HTTP validates source access through overlapping
  ai.use/contract.read scope and the shared narrative read path, but makes no provider call.
- Queue insertion and AI switch admission share the tenant lock. A concurrent disable completes
  before a waiting submission can proceed, causing ai-disabled with no new job. New jobs retain
  selectors, a validated trace ID and a 2048 output-token limit; prompts/model settings are not
  queued. The worker rejects a changed trace before calling; old unbound fingerprints are intact.
- Verification: 21 AI/API database cases passed, followed by both final API cases (including
  real lock contention, idempotency, scope refusal, HTTP-to-worker persistence and changed-trace
  refusal). 40 unit/route/layer checks passed. Full lint, OpenAPI generation and full typecheck
  passed (924 Python sources plus frontend); focused strict typing passed 775 sources. Logs:
  .run/ai-submission-{regressions,api-final,unit,lint,openapi,typecheck,types-final}.log.
- The initial permission fixture was corrected to use an auditor without ai.use; test import
  typing was corrected before the final checks. Anomaly/extraction/Q&A submission, proposal
  read/review and durable AI admission-failure evidence remain open. No deployment/live calls.

## Retained number-explanation reads — October 15, 2026

- Added GET /ai/proposals/{id} for NUMBER_EXPLANATION evidence with content/citations,
  status, actors and ETag. Current ai.use/contract.read grants are intersected; reads require
  a visible current or past member contract of the retained trace's group. Unsupported kinds
  fail closed. AI switches do not prevent authorized evidence reads or trigger provider calls.
- Calculation traces have tenant-only RLS, so a trace join alone does not authorize entity
  access. Added explicit member visibility to proposal reads and completed-job recovery.
- Verification: 21 AI/API database regressions and 54 unit/route/layer checks passed. API cases
  cover content, cross-tenant and entity refusal, revoked grants, peer reads and both AI switches.
  Full lint, OpenAPI generation and typecheck passed (925 Python sources plus frontend).
  Focused strict typing passed 776 sources. Logs: .run/ai-proposal-read-{regressions,unit,lint,
  openapi,typecheck,types}.log. An initial test used a nonexistent disable-reason field; corrected
  to the actual actor-kind column before the passing database run.
- Listing, other proposal kinds, review commands and broader release gates remain open.
  No deployment or live provider calls; this is development evidence, not production sign-off.

## Number-explanation rejection — October 15, 2026

- Added POST /ai/proposals/{id}/reject for supported number explanations. A human with current
  source access supplies a nonblank reason and current If-Match ETag. The locked transition
  records reviewer/time/reason, increments row version and audits once in the same transaction.
  Expired or terminal items cannot be rejected. No provider or accounting command is called.
- Source permission intersection is explicit in SQL inside the existing command transaction.
  A source-access dependency runs before idempotency replay, preventing cached content from
  bypassing later scope restrictions. Rejection remains available while AI is disabled.
- Verification: all 19 AI domain regressions passed; both final API cases passed, including
  overlapping permissions, expiry boundary, simultaneous reviewers (200/412), replay, narrowing
  access after success, reason/precondition validation and one human audit event. 54 unit/layer
  checks and 25 final route/layer checks passed. OpenAPI generation, full typecheck (925 Python
  sources plus frontend), focused typing (776 sources), and lint passed. Logs:
  .run/ai-reject-{regressions,api-verified,unit,architecture-final,openapi-final,typecheck,
  types-verified,lint-final}.log. Early tests caught a missing row-version increment; corrected.
  Expiry and revocation fixtures were corrected to use the UOW clock and revocation metadata.
- Acceptance, extraction review, other proposal kinds, listing, expiry processing and broader
  release gates remain open. No deployment or live provider calls; no production sign-off.

## Scheduled AI proposal expiry — October 15, 2026

- Wired SCH-11 into the worker at 03:20 UTC daily. Each tenant is processed in batches of
  at most 100 locked rows; concurrent review locks are skipped for a later sweep. Only due
  proposed rows become expired, with a row-version increment and SYSTEM audit in one transaction.
  Content, citations, call logs, files and terminal proposal states remain intact; AI switches
  do not govern maintenance. Existing rejection checks enforce expiry between daily sweeps.
- Migration 0154 adds the tenant/expiry/id index. The application-role EXPLAIN test proves
  expires_at bounds the expiry query under RLS; migration upgrade/downgrade/upgrade checks pass.
- Verification: eight PostgreSQL migration/index cases, the real proposal lifecycle case on
  the new head, and 22 worker/layer checks passed. The lifecycle checks the boundary, newer and
  terminal rows, two tenants, review locks, interrupted-batch rollback, multi-batch expiry,
  repeat runs, audit cardinality and retained reads. Full lint and typecheck passed (926 Python
  sources plus frontend); focused typing passed 780 sources. Logs:
  .run/ai-expiry-{head-pg,migrations,unit,typecheck,types-verified,lint-final}.log.
  Initial fixtures were corrected to provision a real second tenant and import the transition
  helper directly for strict typing. No production code was loosened for those fixes.
- Listing, acceptance, extraction and other AI operations remain open, along with the broader
  accounting/verification backlog and independent sign-off. No deployment or live AI calls.

## Authorized AI proposal list — October 15, 2026

- Added GET /ai/proposals for supported number explanations using API-C-09 cursor pagination,
  kind/status filters, optional totals and id/created_at sorts (default newest created_at,
  then descending id). The SQL source-authorization predicate is shared with detail/rejection;
  hidden and unsupported proposals cannot occupy page rows or inflate counts.
- Every page checks current overlapping ai.use/contract.read grants. Tests cover foreign and
  out-of-scope cursor reuse, and the same user's scope narrowing between pages. Unsupported
  kinds return empty results until their source authorization is implemented.
- Verification: three API database cases passed after the final change, covering submission,
  reads, rejection and listing; 25 route/layer checks passed. Full lint, OpenAPI generation and
  typecheck passed (927 Python sources plus frontend); focused typing passed 778 sources.
  Logs: .run/ai-list-{api-final,architecture,openapi,typecheck,types-final,lint}.log. A row mapping
  is copied to a dictionary at the shared serializer boundary to satisfy strict typing.
- Acceptance, extraction, anomaly summaries, Q&A and broader release/accounting requirements
  remain open. No deployment or live provider calls; no production-readiness claim.

## Authorized extraction input preparation — October 15, 2026

- Added a worker-only document retrieval component: reauthorize the current human and attempt,
  require enabled AI and text consent, bind a readable ATTACHMENT/PDF source, enforce its size
  and hash, and audit decrypted reads as the human. An injected isolated parser runs outside
  SQL sessions; heartbeats and fresh admission afterward check cancellation, grants, settings
  and source access before redacted request preparation. Original pages/citation mappings stay
  local. The PDF byte limit is shared with the adapter; cancellation guard exports stay compatible.
- This component does not call a provider, reserve tokens or create a proposal. Extraction
  dispatch, durable encrypted text, provider recovery, proposal persistence and submission still
  need integration. No accounting command or automatic field application was introduced.
- Verification: 20 AI database regressions passed, plus the final focused expiry case. The new
  test reads an encrypted fixture through the file service, checks disabled/text-off/hash/access
  refusals, user download audits, redaction, disable/revocation during parsing and cancellation.
  52 parser/preparation/layer cases passed; two Linux resource-limit cases skipped on this Mac.
  Full lint and typecheck passed (928 Python sources plus frontend); focused typing passed 780
  sources. Logs: .run/ai-document-read-{regressions-final,expiry-final,unit,lint,typecheck,
  types-verified}.log. A nullable tenant-kind read was tightened to scalar_one for typing.
- The broader run exposed a prior expiry test counting other committed tenants. Local exact
  assertions now name its tenant; global fan-out and repeat-run checks remain, with exact audit
  checks for its proposals. Production expiry code was unchanged. No deployment/live AI calls.

## Encrypted extraction proposal evidence — October 15, 2026

- Added a persistence component for original document pages and received extraction responses.
  Text is encrypted per file and bound to the source digest, human and running AI job; repeated
  retention for that job reuses the same file. Saving a proposal rebuilds the request and citation
  mappings from retained bytes, checks the call intent and records usage, content and audit
  evidence atomically. Refused, invalid or uncited responses become failed proposals without
  retaining rejected provider text. Shared job/intent binding checks also serve narratives.
- Verification: 20 existing AI database cases passed in the broader run; its new case exposed
  a missing test-helper argument, now fixed. The final focused PostgreSQL case passed, covering
  ciphertext, original citation offsets, low confidence, refusals, cross-job text/intent swaps,
  changed request fields, missing permission, deduplication, rollback and human audit attribution.
  71 preparation/validation/layer tests passed. Strict focused typing passed 780 sources; full
  typecheck passed 929 Python sources plus frontend. Full lint passed. Logs:
  .run/ai-extraction-persistence-{regressions,pg-final,unit,types-final,typecheck,lint}.log.
- Extraction dispatch, budget/provider recovery, submission, field schemas and human acceptance
  remain open. These components do not invoke a provider or apply accounting changes. Broader
  release verification and independent accounting sign-off remain outstanding. No deployment.

## Extraction provider-failure evidence — October 15, 2026

- Added terminal extraction failure persistence using the existing committed attempt log.
  It rebuilds retained document evidence, validates request/provider/error metadata and the
  initiating human/job intent, then writes a failed proposal with empty content/citations.
  It neither duplicates the attempt nor changes its reported/unknown usage. Narrative failures
  share the evidence validator; extraction additionally requires a call intent.
- Verification: 21 AI PostgreSQL cases passed, including narrative retries and extraction
  failure/rollback. The final focused extraction case also passed after adding missing-intent
  refusal and explicitly binding test-loop captures. Tests cover timeout with unknown usage,
  permission failure with reported usage, unchanged log bytes/metadata, wrong error codes,
  unrelated response logs, no intent, rollback and audit attribution. Seventeen architecture
  checks passed. Full lint/typecheck passed (929 Python sources plus frontend); final focused
  typing passed 780 sources. Logs: .run/ai-extraction-failure-{pg,pg-final,layers,lint,
  types-final,typecheck}.log.
- The gateway still owns admission and retry exhaustion. Extraction dispatch, provider recovery,
  submission, review/acceptance and the broader release/accounting gates remain unfinished.
  No deployment or live provider call; no production-readiness claim.

## Durable extraction call document links — October 15, 2026

- Migration 0155 adds paired source/text file references to immutable AI call intents, with
  tenant-bound foreign keys and a downgrade guard against losing populated links. A worker can
  locate exact retained text through the committed call before any proposal exists. Intent
  writers validate paired purposes and unshredded files; retries preserve both links. Extraction
  success/failure persistence verifies its file IDs against the call intent.
- Both references now hold evidence independently of proposal creation or outcome. They grant
  no extra read access. Direct shred is refused; existing independently reviewed EVIDENCE_SHRED
  can lift the holds and destroy the text key, preserving immutable references and digests.
- Verification: 29 PostgreSQL migration/AI regressions passed, including full migration round
  trip, tenant FK/null-pair checks, immutable intent and lossy downgrade guards. Three final
  cases passed for extraction retry-link rejection and proposal/call-only reviewed erasure.
  The latter prove direct refusal, independent approval, key destruction and failed decrypted
  reads after erasure. Thirty-two architecture/unit checks passed. Full lint/typecheck passed
  (930 Python sources plus frontend); focused typing passed 782 and erasure typing 781 sources.
  Logs: .run/ai-intent-documents-{pg,erasure-pg,unit,access,lint,typecheck,types-final,
  erasure-types}.log. No deployment or live provider calls.
- This closes a prerequisite discovered at gateway integration: call evidence previously could
  not locate or protect retained text before proposal persistence. Extraction execution/recovery,
  submission and human review remain unfinished, alongside the broader release/accounting gates.

## Extraction recovery from retained input — October 15, 2026

- Added a worker-only recovery reader that freshly authorizes the initiating human, selects
  call/proposal binding metadata, and rebuilds exact request bytes/citation maps from encrypted
  intent-linked text. It validates source access, digests, field paths and original model/prompt
  settings. It does not reparse a PDF or invoke a provider. Existing proposals return their ID;
  recorded failures return validated classification, usage, attempt number and outcome time for
  gateway backoff. Missing outcomes and unclassified results refuse automatic recovery.
- Evidence reads work while new AI calls are disabled, but current permission revocation refuses
  recovery. Tests cover completed proposals, reported/unknown provider usage, changed selectors,
  mismatched source fingerprints, no outcome, invalidated responses and unchanged call/log counts.
  Shared retained-page validation also continues to serve proposal writes.
- Verification: 21 AI PostgreSQL regressions passed; the final focused case passed after narrowing
  proposal queries to binding metadata. Thirty preparation/layer tests passed. Full lint and
  typecheck passed (931 Python sources plus frontend); final focused typing passed 782 sources.
  Logs: .run/ai-extraction-recovery-{pg,regressions,pg-final,unit,lint,typecheck,
  types-verified}.log. No deployment or live provider calls.
- Gateway admission, retry execution, worker dispatch, submission and human acceptance remain
  unfinished. This reader supplies recovery evidence; it does not authorize another provider call.
  Broader release verification and independent accounting sign-off remain outstanding.

## Extraction gateway and worker dispatch — October 15, 2026

- Connected extraction execution to fresh human/source/settings admission, the tenant budget
  lease, committed text/call intent, audited outcomes and proposal persistence. Retries reuse
  retained input without reparsing, observe durable 5/10-second backoff and stop at three calls.
  Permanent/exhausted errors finalize against the last log. Completed replay makes no new call;
  uncertain outcomes/usage block execution. Mid-call disable/revocation retains usage without
  creating a proposal. Cancelling an uncertain job preserves its evidence and budget hold.
- AI_TASK now validates narrative or extraction selectors, rejecting prompts/model/text input.
  The worker composition root supplies the isolated PDF parser and lazy provider. Worker retry
  count remains one; the gateway owns provider attempts. Human review/acceptance remains separate.
- Verification: 38 AI PostgreSQL cases passed, including a real queued extraction job, interrupted
  wait/failure recovery, lease release across waits, exact retained requests, cancellation,
  disabled/text-off/budget admission, invalid output and known/unknown usage. Three final cases
  passed after the uncertain-call cancellation correction. Thirty-nine dispatch/layer checks
  and nine worker/probe checks passed. Full lint/typecheck passed (932 Python sources plus
  frontend); final focused typing passed 784 sources and final formatting/lint checks passed.
  Logs: .run/ai-extraction-gateway-{pg-fixed,regressions,final-pg,unit,worker-unit,lint,
  typecheck-last,types-last}.log. An initial test-only mappingproxy serialization mistake and
  two strict-typing issues were corrected. Fake providers/parsers only; no deployment/live AI.
- Public extraction submission, approved field catalogue, document-text/proposal review APIs,
  human acceptance and broader release/accounting gates remain unfinished. Linux parser resource
  enforcement and live-provider operation are not proved by these local worker tests.

## Typed extraction field catalogue — October 15, 2026

- Defined the documented contract-review fields: seven header/review paths plus lines.0 through
  lines.499, matching contract line capacity. Queue and gateway selectors refuse other paths.
  Values require bounded nonblank text, exact ISO dates, positive whole JSON month counts and
  line objects containing only product_code and an exact signed decimal-string amount. Review
  terms remain text; no customer/product resolution, currency inference or accounting decision
  is made. The worker selector capacity now covers the full 507-path catalogue.
- Typed checks run on original parsed JSON before canonicalization: Decimal values would
  otherwise become strings and let a numeric money value masquerade as valid API-C-06 text.
  One invalid value refuses the whole proposal; rejected content is not retained. The documented
  four-page PDF fixture passes these field checks without changing its retained prompt bytes.
- Verification: 143 unit/architecture cases passed, including path/value boundaries, numeric
  money/coercion attacks, invalid dates, extra accounting fields and all catalogue selectors.
  Forty AI PostgreSQL cases passed, including the real worker, recovery and narrative regressions;
  unsupported selectors make no provider call and numeric amounts persist only an empty failed
  proposal. Full lint/typecheck passed (933 Python sources plus frontend), focused typing passed
  787 sources, and final formatting/diff checks passed. Logs:
  .run/ai-extraction-fields-{unit,pg,lint,typecheck,types}.log.
- Public submission, extraction review APIs, human conversion/acceptance and broader release and
  independent accounting verification remain unfinished. No deployment or live provider calls.

## Authorized extraction submission API — October 15, 2026

- Added POST /ai/contract-extractions with file_id as its only input. It requires a human
  with ai.use, current access to an unshredded PDF attachment, enabled AI and text consent.
  The server pins the digest, fixed 507-field catalogue and 16000 output-token limit, returning
  an idempotent queued job with Location. HTTP performs no parsing or provider calls.
- Current file access is checked before replaying saved command responses. Admission shares
  the tenant lock with emergency disable; the worker independently rechecks access/settings.
  Added the request file binding and regenerated OpenAPI and frontend types.
- Verification: both extraction PostgreSQL API tests passed, including the actual queued worker
  with injected parser/provider, proposal persistence, replay after source unavailability,
  forbidden/hidden/missing/non-PDF inputs, text consent, rejected extra selectors and a proven
  database lock wait against disable. The three existing explanation API regressions passed.
  Twenty-two architecture checks, full lint, full typecheck (933 Python sources and frontend)
  and final focused typing (784 sources) passed. Test setup was corrected for registry timing,
  valid attachment types and the job registry's reserved engine release metadata.
  Logs: .run/ai-extraction-submit-{api-final-pass,api-verified,architecture,lint,typecheck,
  types-verified}.log. The combined api-verified log retains an earlier extraction assertion
  failure; api-final-pass verifies its correction. No live provider calls or deployment.
- Extraction proposal/document-text reads, human review/acceptance and broader release and
  independent accounting verification remain outstanding.

## Authorized extraction proposal detail — October 15, 2026

- GET /ai/proposals/{id} now returns CONTRACT_EXTRACTION evidence as a distinct response shape
  alongside number explanations. Common actor/status/citation/ETag metadata is shared; extraction
  responses include source/text file IDs and the retained suggested-field array.
- The query selects binding metadata first, requires a current human ai.use grant and current
  original ATTACHMENT/PDF ownership access, and only then loads content/citations. Unreadable or
  shredded sources return 404. Reads work with AI disabled and neither decrypt text nor call a
  provider. Existing narrative source checks and narrative-only rejection/list paths are retained.
- Verification: five PostgreSQL API tests passed, including worker-produced evidence, AI-off
  reads, forbidden readers, another AI-enabled user without source access, missing/shredded
  sources and existing narrative list/rejection regressions. Twenty-four layer/file-access
  checks passed. Full lint and typecheck passed (933 Python sources plus frontend), focused
  typing passed 784 sources, OpenAPI/frontend regeneration and formatting/diff checks passed.
  Logs: .run/ai-extraction-read-{api,architecture,lint,typecheck,types-final,openapi}.log.
- Extraction list integration, original document-text responses, human review/acceptance and
  broader release/accounting verification remain open. No deployment or live provider calls.

## Audited extraction document-text reads — October 15, 2026

- Implemented GET /ai/proposals/{id}/document-text for retained extraction evidence. Current
  source access is checked before the normal encrypted file reader rechecks ownership and
  commits a file.download audit as the human reader. The response preserves original pages and
  order with one-based page numbers. AI-off reads work; other kinds and shredded text return 404.
- Shared the canonical envelope decoder with worker persistence. Both paths validate exact
  source/job bindings; the public read additionally checks stored size/digest, while the decoder
  rejects malformed/noncanonical envelopes, wrong bindings, invalid page types and exceeded
  page/text limits. Reads neither parse the PDF nor call a provider.
- Verification: six PostgreSQL API/persistence tests passed, including AI-off text, actor audit,
  denied/unreadable sources, non-extraction proposals, shredded text/source and retained evidence
  rollback/regressions. Forty-one unit/architecture checks passed, including 17 text-envelope
  cases. Full lint/typecheck passed (934 Python sources plus frontend), focused typing passed
  787 sources, OpenAPI/frontend generation and final diff checks passed. Logs:
  .run/ai-document-text-{pg-final,unit,lint,typecheck,types-final,openapi}.log.
- Extraction list integration, human review/acceptance, broader release checks and independent
  accounting sign-off remain outstanding. No deployment or live provider calls.

## Extraction proposal rejection — October 15, 2026

- Extended POST /ai/proposals/{id}/reject to extraction evidence, sharing the existing reason,
  If-Match, idempotency and audit controls. Source authorization now runs in the review command's
  transaction; the proposal row is locked before checking version/status/expiry and transitioning.
  Current source access also gates cached command responses. Rejection preserves suggestions
  and citations, works with AI disabled, and does not call a provider or write accounting data.
- Verification: five PostgreSQL API tests passed, including extraction and narrative review.
  Two simultaneous extraction reviewers using the same ETag yield one 200 and one 412, with
  one audit event; exact expiry and terminal rows refuse rejection. Successful replay matches
  the first response, while replay after source shredding returns 404. Unauthorized reviewers
  cannot act; retained fields/citations and one provider usage record remain unchanged.
  Twenty-four architecture checks passed. Full typecheck passed (934 Python sources plus
  frontend), focused typing passed 786 sources, and OpenAPI/frontend artifacts were regenerated.
  Full lint and final diff checks passed.
  Logs: .run/ai-extraction-reject-{api,architecture,typecheck,types,openapi,lint}.log.
- Extraction list integration, per-field decisions and structured acceptance remain unfinished,
  alongside broader release/accounting gates. No deployment or live provider calls.

## Authorized extraction review list — October 15, 2026

- GET /ai/proposals now includes extraction evidence alongside number explanations, with the
  shared kind/status filters, authorized totals and stable cursor pagination. Extraction source
  metadata is checked through the existing file ownership rules before SQL paging/counting or
  selecting proposal content. Shredded/non-PDF sources and unsupported kinds cannot enter results.
- Only distinct referenced source-file metadata is scanned, in batches; readable UUIDs use one
  array parameter. This preserves uploader/shared-upload and attachment access semantics but
  still performs per-source authorization work. Large-tenant latency/load verification and
  optimization remain outstanding. Missing contract.read grants exclude narrative evidence
  without preventing otherwise authorized extraction reads.
- Verification: five PostgreSQL API cases passed, covering extraction inclusion, exact counts,
  kind/status filters, denied source owners, disappearance after shredding, and narrative cursor,
  grant-narrowing and review regressions. Twenty-eight architecture/list-contract checks passed.
  Full typecheck passed (934 Python sources plus frontend), focused typing passed 786 sources,
  and OpenAPI/frontend generation passed. Logs:
  .run/ai-extraction-list-{api,architecture,typecheck,types-final,openapi,lint}.log.
  Full lint and final diff checks also passed.
- Per-field decisions, structured acceptance and broader release/accounting verification remain
  open. No deployment or live provider calls.

## Explicit extraction field-review decisions — October 15, 2026

- Added the ACCEPT/EDIT/REJECT request item schema and pure review resolver. Every retained path
  must appear exactly once; invalid originals, missing/duplicate/unknown paths and oversized
  reviews refuse. EDIT explicitly supplies a typed value; ACCEPT/REJECT cannot hide replacement
  values. EDIT/REJECT require bounded nonblank reasons. Accepted values retain exact types and
  decimal-string representation, edits use the field catalogue, and rejections leave fields unset.
- Resolved values and decision records are detached copies in proposal order. Rejecting every
  field produces no defaults. This component does not write contracts or enable acceptance;
  conversion still requires explicit contract identity, currency, quantities, obligation keys
  and structured terms, with command-level source/permission/status/expiry/SoD and atomicity.
- Verification: 35 final unit cases passed, covering full 507-field capacity, overflow, exact
  coverage, malformed reasons, forbidden replacements, invalid dates/months/numeric money,
  invalid retained values, all-rejected reviews and detached mutable inputs. Seventeen layer
  checks also passed in the initial 50-case run. Full lint/typecheck passed (935 Python sources
  plus frontend), final focused typing passed 786 sources and final formatting/lint/diff checks
  passed. Logs: .run/ai-field-review-{unit,boundaries,lint,typecheck,types-final}.log.
- Structured acceptance remains unimplemented; broader release/accounting and large-tenant list
  performance gates remain open. No deployment or live provider calls.

## Explicit extraction draft inputs and line bindings — October 15, 2026

- Added draft-intake preparation using the existing ContractCreateIn schema, explicit entity,
  field decisions and line_bindings from retained paths to obligation keys. Entity codes must
  agree, activation is forbidden, mapping targets must exist and be unique, and every retained
  line must map exactly once. Rejected lines cannot be mapped. Mapped product and exact amount
  must agree with reviewed values, and line currency must match the explicit draft currency.
- Required contract identity, currency, quantities and obligation keys come from human input;
  no source value fills missing fields. Additional human-authored lines remain possible. This
  is not an acceptance endpoint. Header/customer/structured-term binding, the pending approval
  subject AI_PROPOSAL_ACCEPTANCE, command authorization/expiry/SoD and atomic persistence remain.
- Verification: 76 unit/layer tests passed, including 24 new draft cases, 35 field-review cases
  and 17 architecture checks. Tests cover required inputs, entity/activation/command refusals,
  mapping coverage/uniqueness, product/sign/amount/currency mismatches, edit consistency and
  rejected lines. Initial fixture/scalar comparisons were corrected to use API-S-Money objects
  and decimal-string quantities; guards were retained. Full typecheck passed (936 Python sources
  plus frontend), focused typing passed 788 sources and final formatting/lint/diff checks passed.
  Full lint also passed. Logs: .run/ai-draft-review-{verified,typecheck,types-final,lint}.log.
- Broader release/accounting verification and large-tenant list performance remain open. No
  deployment or live provider calls; the acceptance route remains disabled.

## Explicit extraction header bindings — October 15, 2026

- Added combined draft review for retained customer name, effective date and payment terms,
  alongside the existing line checks. The reviewer explicitly maps an effective date to draft
  inception or signature; payment terms and the selected date must match exactly. Customer
  names match either the explicit inline reference or a resolved ID/name whose ID equals the
  draft's selected customer. No name search, date inference or accounting classification occurs.
- Every retained header must have an implemented mapping; rejected headers cannot be mapped.
  Term months, termination, variable-consideration terms and material-right text currently refuse
  combined review rather than disappearing silently. Existing customer resolution must still be
  wired to fresh tenant-authorized reads in the eventual acceptance command. Approval, structured
  term mappings and atomic persistence remain unfinished; acceptance is not enabled.
- Verification: 91 unit/layer cases passed, including 15 new header tests. A final 39-case draft
  suite passed after a typing-only iteration correction. Cases include explicit date meaning,
  missing/mismatched dates and payment terms, exact inline/resolved customer identity, rejected
  or unbound headers, unsupported structured terms and JSON round-trip with omitted replacement
  values preserved. Focused typing passed 788 sources. Logs:
  .run/ai-draft-headers-{unit,final,types-final,typecheck,lint}.log. Full lint and typecheck
  passed (936 Python sources plus frontend), as did final formatting/lint/diff checks.
- Broader release/accounting and list-performance gates remain open. No deployment or live
  provider calls.


## AI-assisted draft activation control — October 15, 2026

- Corrected the earlier acceptance prerequisite: PRD SM-11/BR-AI-05 permits a normal human command
  to create a new draft; AI_PROPOSAL_ACCEPTANCE applies to changes to existing records. New
  drafts instead require AI_ASSISTED activation review. The separate existing-record subject
  remains open, but is not a prerequisite for the new-draft acceptance route.
- Activation now derives AI_ASSISTED from immutable accepted extraction-to-contract links, so
  published auto-approval cannot bypass human review at any amount. Approval content includes
  provenance IDs, accepting human/time and a hash of field decisions, without quoted review text.
  Contracts without provenance retain their historical hash shape. Accepting humans are excluded
  from deciding activation, including via delegation, using the existing authorship mechanism.
- Verification: the PostgreSQL witness proves the AI-assisted contract waits under a published
  auto-approval rule, the ordinary control auto-approves, self-approval is refused and an
  independent reviewer can activate. The existing multi-flag activation regression also passed.
  A test assertion was updated for the expected MANUAL_ENTRY flag induced by human authorship.
  113 unit/layer/routing checks passed. Full typecheck passed (937 Python sources plus frontend),
  focused typing passed 788 sources, and final lint/diff checks passed. Logs:
  .run/ai-activation-provenance-{unit,verified,pg-final,typecheck,types-final,lint}.log. Full lint
  also passed. The pg-final
  log retains the earlier flag assertion failure; verified records its successful correction.
- New-draft acceptance still requires atomic command integration, source/expiry validation and
  structured-term handling. Broader release/accounting and list-performance gates remain open.
  No deployment or live provider calls.


## Atomic reviewed extraction draft acceptance — October 15, 2026

- Enabled POST /ai/proposals/{id}/accept for new drafts, requiring explicit complete draft
  inputs, field decisions and supported header/line mappings. Fresh tenant customer resolution,
  human ai.use plus contract.create for the selected entity, source access, If-Match and exact
  expiry checks precede writes. At least one retained field is required. Cached replay also
  rechecks current permissions/source access.
- Normal contract creation, source-PDF attachment, combination suggestions, rule holds, accepted
  proposal provenance and audit commit in one transaction. Acceptance creates only a DRAFT;
  it does not submit activation or post revenue. Existing AI_ASSISTED activation controls apply.
  Retained review works with AI off. OpenAPI and frontend API types regenerated.
- PostgreSQL regression: 8 tests passed across acceptance, extraction/explanation submission,
  authorized lists and emergency disable. Acceptance covers competing reviewers (201/412),
  idempotent replay, no create permission, missing If-Match, exact expiry, mismatched amount,
  empty acceptance, injected rollback including attachment, one successful audit/provenance
  record, zero revenue postings and unavailable-source replay. The acceptance test seeds retained
  proposal evidence; it does not prove a full worker-to-activation or browser workflow.
- 98 unit/architecture checks and full lint passed; focused typing passed 789 sources. Logs: .run/ai-acceptance-{regression,final-types,
  final-unit,final-lint}.log. Structured-term mappings, existing-record acceptance approval,
  complete browser review, broad release verification and independent accounting sign-off remain
  open. No deployment or live provider calls.


## Worker-to-draft acceptance evidence — October 15, 2026

- Added an integrated PostgreSQL witness using the real four-page synthetic PDF, real PDF
  text extraction, queued AI_TASK dispatch and a deterministic provider response. It reads the
  worker's retained proposal/pages, edits the suggested customer to an explicit existing customer
  with a reason, and accepts through the public draft endpoint. Original content/citations and
  model-log linkage survive unchanged; the reviewed value is retained separately.
- A different authorized reader cannot see the unattached source/proposal, then can read the
  accepted proposal and identical retained pages through the new contract attachment. The draft
  carries AI_ASSISTED and provenance into its activation review basis, with no revenue posting
  and exactly one provider call. This does not prove browser review, independent activation,
  live-provider behavior or Linux parser isolation: the test uses the real in-process parser.
- Both acceptance tests passed, focused typing passed 789 sources and full lint passed. Logs:
  .run/ai-worker-acceptance-{verified,final-types,lint}.log. Earlier pg/pg-fixed logs retain test
  setup failures (missing retry callback and reused command idempotency key); verified is the
  corrected run. Broader release/accounting and structured-term gaps remain open. No deployment.

## Retained acceptance reads and frontend API boundary — October 15, 2026

- Extraction detail/list now return accepted command/target, accepting human/time and recorded
  field decisions alongside unchanged original evidence. The fields remain protected by current
  source access. The worker-to-acceptance PostgreSQL witness compares detail and list results,
  reviewed values, actor and target; all seven acceptance/extraction/explanation API tests pass.
- Added a typed frontend API module for proposal pages/detail, document text, extraction
  submission, rejection and draft acceptance. It preserves server ETags, unmodified decimal
  strings/review bodies, shared command keys across lost responses, opaque cursors and API
  refusals. Retained reads require no AI-settings fetch; no automatic retries or draft inference.
  This is the API layer for SF-20, not a live screen. The route, field-decision controls and
  draft-form integration remain unbuilt.
- Six frontend API tests pass. Full backend typing passed 938 sources and focused typing passed
  789. Frontend typing initially caught omitted explicit default fields in the test draft; the
  fixture now supplies them. Full lint passed. Logs: .run/ai-review-client-tests.log and
  .run/ai-review-read-{pg,typecheck,focused-types,frontend-types,lint,openapi}.log.
  Broader release/accounting, structured-term conversion and browser gates remain open.
  No deployment or live provider calls.

## Contract review evidence screen — October 15, 2026

- Added SF-20 /contracts/review/:proposalId with permission-gated retained proposal/document
  reads, original text and field values, confidence/check indicators, accepted reviewer/time,
  recorded edited values/reasons and an accepted-draft link. Whole-proposal rejection requires
  a reason and the read ETag, preserves failure information, and refreshes retained evidence.
  Expired or missing-ETag proposals withhold rejection. Document failures offer reload.
- Citation spans must refer to the original file and fit the page. Highlighting uses Unicode code
  points to match Python offsets, never HTML, then focuses the highlight; Escape returns to the
  citation. Corrected focus handling so unrelated renders cannot steal focus back from a form.
- 19 route/API/permission checks, frontend typing and full lint passed. Local Chromium preview had no
  page errors and confirmed highlight/focus; light/dark 1440 and dark 1280 captures retained in
  .run/ai-review-screen-*.png. This preview mounts the component with cached synthetic responses,
  not the full shell or live backend. Logs: .run/ai-review-screen-{tests,types,browser,lint}.log.
- Upload/job navigation, field decisions, responsive panel tabs and draft-form integration remain
  unfinished. Broader release and independent accounting gates stay open. No deployment or live
  provider calls. The preview server was stopped after inspection.

## Review-source upload and resumable job navigation — October 15, 2026

- Added SF-20:new at /contracts/review/new, activating the existing Contracts entry. It validates
  nonempty PDFs up to 25 MiB, uploads ATTACHMENT, submits file_id, polls the returned AI_TASK and
  opens its retained proposal. A job URL resumes after reload, including after AI disable.
  Only the initiating human can cancel a running task. Failed/lost requests retain errors and
  retry keys; the successful upload is reused if extraction submission fails. Unrelated jobs
  and malformed result IDs cannot navigate. No entity or accounting values are inferred.
- Corrected a permission mismatch: ai.use now admits ATTACHMENT upload before a contract exists,
  without granting record-attachment or other-purpose writes. New API evidence checks upload,
  extraction admission and refusal of contract attachment/SSP upload. Existing no-upload tests
  now use a role without ai.use; request-attachment tests still refuse non-requesters and closed
  requests even when an AI source upload is permitted. Earlier logs preserve old-role assertion
  failures; the verified run passes all 25 extraction/file API tests.
- 30 frontend route/API/navigation checks, frontend typing and full lint passed. Local Chromium
  upload-to-job navigation with mocked HTTP returned no page errors; light/dark captures were
  inspected. This is not live API/provider or complete browser acceptance evidence. Logs:
  .run/ai-review-upload-{pg-verified,tests,types,python-types,lint,browser}.log.
- DOCX, field decisions, responsive panel tabs, draft-form integration, broad release verification
  and independent accounting sign-off remain open. No deployment or live provider calls.

## Per-field review and confirmed draft handoff — October 15, 2026

- Added Accept/Edit/Reject controls, explicit low-confidence choices, edit/rejection reasons,
  citation checks and an explicit effective-date target. Decimal amounts remain strings;
  customer identity/code, entity, currency and quantities require normal draft inputs.
  Unsupported retained accounting terms stop continuation rather than being interpreted.
- Reused ordinary draft validation and inputs, then a separate confirmation sends atomic
  proposal acceptance with captured ETag, decisions and bindings. No activation action is
  offered. A failed request keeps the form; successful acceptance opens the draft workbench.
- 58 focused frontend review/upload/API/form tests, frontend typing and full lint passed. Logs:
  .run/ai-review-decisions-{tests,types,lint}.log. These are component/API-boundary checks,
  not a live browser/provider workflow or current full-release verification.
- Back-navigation to field choices, unsupported terms, DOCX, responsive tabs, full browser
  acceptance, broader release gates and independent accounting sign-off remain open.
  No deployment or provider calls.

## Review round-trip preserves draft work — October 15, 2026

- Added Back to field review with an in-memory draft snapshot. Continuing preserves unrelated
  human inputs and applies changed decisions to corresponding headers and source rows. Rejected
  source rows are removed; human-added rows remain. Renamed obligation keys are rebound explicitly
  when returning to the draft. No field decision is inferred from a changed draft value.
- Fixed row identity collisions when restoring deleted retained rows and when adding rows after
  reopening a draft with gaps in its local row identities. Tests exercise both failures plus
  field-review/form round trips and changed customer/amount decisions.
- 50 focused tests, frontend typing and full lint passed. Evidence:
  .run/ai-review-recovery-{tests,types,lint}.log. Recovery is local component state,
  not persistence across reloads or live browser/API acceptance evidence. Existing server version
  preconditions remain authoritative; returning to review captures the current displayed ETag
  only on explicit continuation. Broader release verification and accounting sign-off remain open.
  No deployment or live provider calls.

## Broad frontend verification and frozen CI — October 15, 2026

- Full frontend testing found two inventory failures: omitted SF-20 route IDs and no crawl
  proposal lookup. Added both without a skip/exclusion; a live crawl still requires accessible
  retained extraction evidence. The repaired full suite passes 2,143 tests in 200 files.
  Frontend typing, focused ESLint and formatting pass. Evidence and limits:
  docs/release/CI-2026-10-15.md; .run/frontend-full-oct15-repaired.{log,xml}.
- Frozen make ci on 3cf8f5b has passed environment, full lint and typecheck (938 Python files)
  and is running the broad test stage against isolated local PostgreSQL 55439. Live log:
  .run/production-readiness-ci-oct15.log. Do not restart the live run. This snapshot predates
  the inventory repair; its eventual results must remain attributed to that snapshot.
- No full CI pass is claimed. Real retained-proposal browser fixtures, complete acceptance,
  broader release gates and accounting sign-off remain open. No deployment/provider calls.

## Bind the known extraction fixture to real upload requests — October 15, 2026

- Found that the bundled fake extraction response matched only its original fixed document ID,
  model and nine-path request. Real upload IDs/full worker catalogues had no fixture. Added a
  bundled-only fallback that reconstructs the complete known redacted-document request before
  reusing retained values, filtering allowed fields and rebinding citations to the upload ID.
  Arbitrary source text, prompts and inconsistent hashes still fail. Custom fixture roots retain
  exact/default semantics. No network calls or accounting writes are introduced.
- AI unit suite: 250 passed, two Linux resource checks skipped on macOS. Focused strict typing
  passes 790 sources; full lint passes. Evidence: .run/ai-upload-fixture-first-failure.log (completed unit run),
  .run/ai-upload-fixture-types.log. Combined AI/architecture run: 508 passed, 12 failed,
  two skipped in .run/ai-upload-fixture-tests.log. Failures identify existing AI audit writers
  without contract keys, unlisted expiry SYSTEM/platform-directory callers and AI_TASK still
  marked pending after registration. No broad pass is claimed; these require follow-up repair.
- Full frozen CI remains live on 3cf8f5b against isolated PostgreSQL 55439, in engine tests.
  Do not restart it or run other database tests there. Known-document fixture adaptation does
  not complete demo/browser seeding, Linux parser proof, browser acceptance or accounting sign-off.
  No deployment or live provider calls.

## Repair AI lifecycle audit references and worker inventories — October 15, 2026

- Narrative rejection and expiry now pass distinct source contract IDs to the audit writer
  inside their tenant transaction; missing source contracts refuse rather than writing an
  unlinked event. Extraction creation/rejection explicitly names no pre-existing draft contract.
  Database tests verify hashed detail, the contract audit index, rollback and retained evidence.
- Reviewed expiry's limited tenant-directory read and bounded tenant SYSTEM transitions; added
  the reasons to TXN-07 and caller inventories. Removed the implemented AI_TASK from the pending
  registry while preserving detector checks for omissions, duplication and wrong build phases.
- 24 targeted architecture checks, eight PostgreSQL lifecycle/API checks, strict typing (793
  sources) and full lint pass. Separate cross-tenant source check: .run/ai-audit-keys-tenant-check.log.
  PostgreSQL verification ran on a new isolated instance at 55441; initial encoding setup errors
  are retained separately from the verified UTF-8 run. Logs: .run/ai-audit-architecture.log and
  .run/ai-audit-keys-{pg-verified,types,lint}.log. See docs/release/CI-2026-10-15.md.
- The full frozen CI on 3cf8f5b remains live on 55439 and predates these repairs. No restart,
  deployment or live model call. Browser fixtures/acceptance, remaining implementation and release
  gates, and independent accounting sign-off remain open.

## Bundled extraction fixture through upload and draft acceptance — October 15, 2026

- Strengthened the worker/acceptance witness: source now enters through POST /files and the
  configured fake provider serves the complete nine-field bundled document fixture, replacing
  the test-only one-field provider. The uploaded ID is checked in every citation. Explicit human
  customer/product edits, accepted date/payment terms and rejected terms/second line are recorded
  separately from unchanged original evidence. Persisted booking values, attachment-based access,
  AI_ASSISTED review provenance, one provider call and zero revenue postings are asserted.
- Both acceptance regressions pass on isolated PostgreSQL 55441, with focused strict typing
  (791 sources), Ruff and full lint. Logs: .run/ai-bundled-acceptance-{final,types,lint}.log.
  Earlier attempts retain two corrected fixture assumptions: the test tenant uses a different
  product code, and stored ACCEPT decisions also snapshot their accepted values.
- This is API/worker/database evidence using an in-process PDF parser, not browser interaction,
  Linux isolation, live-model accuracy or independent activation/accounting sign-off. Demo/browser
  fixture setup remains unfinished. Frozen CI on 3cf8f5b remains live on separate PostgreSQL 55439.
  No deployment or live provider calls.

## Responsive contract review panes — October 15, 2026

- SF-20 now uses Document / Proposed fields panel tabs below 1440 px and two columns above,
  with pane=document|fields in the URL. Field decisions, edited values and reasons survive pane
  and viewport changes. Citations open Document and focus the source highlight; Escape waits
  for the fields pane to become visible before returning focus to the originating citation.
- 24 focused review/decision/tab tests, frontend type checking and full lint pass. A cached-data
  Chromium preview verifies citation/Escape focus and retained edits at 768/1280/1440 px;
  screenshots inspected. Logs: .run/ai-review-panes-{tests,types,lint,browser}.log.
- This browser witness uses retained synthetic data, not a live upload-to-acceptance workflow.
  Full frozen CI on 3cf8f5b remains active; repository readiness and accounting sign-off remain open.

## Source-page navigation for retained contract review — October 15, 2026

- The document pane now renders one selected source page instead of every page. The labelled
  selector is available for multipage documents; citations select their page and focus its
  highlight. Manual navigation clears the old highlight without changing field decisions.
- Twelve route tests and a cached-data Chromium probe cover page navigation, citation jumps,
  Escape focus and retained edits. Screenshots inspected at 1280/1440 px. Logs:
  .run/ai-review-pages-{tests,types-final,lint,browser}.log. Frontend typing and full lint pass;
  the initial type-check caught two Field API mistakes corrected before the final run.
- Updated release limitations for the responsive panes and page navigation. Full release evidence,
  live browser acceptance and independent accounting sign-off remain outstanding. Frozen CI on
  3cf8f5b is still live; Docker daemon remains unavailable. No deployment or live provider calls.

## Package synthetic AI evidence in runtime images — October 15, 2026

- API and worker builds now copy only the synthetic AI fixture bundle needed by FakeProvider.
  Previously local extraction tests passed but image inputs omitted the PDF and response files.
  A behavioral packaging regression reconstructs each Dockerfile's directory COPY inputs and
  invokes the provider from that isolated copy, checking a new upload ID and cited customer value.
- Seventeen packaging/PDF checks, focused typing, Ruff and full lint pass. Logs:
  .run/ai-image-fixtures-{tests,types,lint}.log. This is host-side copied-tree verification.
- Docker Desktop is now running. The first image build was deliberately interrupted to fix this
  packaging defect; Linux base-image pull session remains active, without a completed image.
  Container hardening, Linux PDF limits and full browser upload/acceptance remain unverified.
  Frozen CI on 3cf8f5b continues independently. No deployment or live provider calls.

## Container build and Linux extraction verification — October 15, 2026

- Clean b4b8210 passed make docker-build: API/worker/web image hardening and embedded-manifest
  checks passed. The manifest is non-strict. Image identities are in CI-2026-10-15.md.
- The actual worker image, Linux Python 3.12.15 / UID 10001, passed a no-network, read-only
  probe for isolated four-page PDF extraction, nine bundled fields with upload-bound citations,
  memory and CPU limits, credential stripping and timeout child reaping. Logs:
  .run/docker-build-oct15-fixtures.log; .run/ai-image-linux-probe-stdin.log.
- Docker now runs locally. A credential-helper stall was avoided with a task-local anonymous
  config; a stalled host mount was replaced with stdin. No saved credentials changed or images
  pushed. Local Compose verification on b4b8210 and frozen CI on 3cf8f5b remain active.
  Full browser acceptance and independent accounting sign-off remain open; no deployment.

## Bound stalled Compose startup and retain failure evidence — October 15, 2026

- Compose verification now bounds up -d (600s default, configurable separately from health
  polling). It stops the client/plugin group, records startup exit 124 and attempts cleanup.
  Eleven Compose checks, focused typing, shell syntax and full lint pass. The first test run
  had one manifest failure during source editing; the stable full selection passes.
- An actual development run at 30s reproduced the host-mount startup stall and failed cleanly;
  cleanup removed all test containers, volumes and network. Logs:
  .run/compose-start-timeout-{verified,types,lint,local}.log; Compose report remains failed.
- Earlier unbounded runs, including a temporary checkout outside Documents, were interrupted
  and cleaned up. That checkout was removed; diagnostics retained. Container hardening/Linux
  PDF checks remain passed on b4b8210, but Compose readiness is unverified. Frozen CI on
  3cf8f5b remains active. No deployment or independent accounting sign-off.

## Future-starting draft reader and browser acceptance — October 15, 2026

- Real browser acceptance exposed GET contract returning 422 after a successful creation:
  October inception followed the fixture's September open-period horizon. The engine correctly
  emitted no member balance (C-05), but the reader treated this as missing trace evidence.
- The reader now recognizes the explicit no-measured-period formula plus V4 draft zero-revenue
  guard, with stored revenue/billing/progress all zero. It shows no measured period and does
  not waive missing-trace refusals. No engine, posting or accounting-policy change.
- 74 reader/acceptance checks pass; the existing damaged-trace API refusal also passes.
  Full lint and backend/API typing pass (791 files). Explicit typing of the older unit module found
  pre-existing Decimal/int comparison and optional-string errors; that module is not claimed clean.
- Chromium with real API/PostgreSQL and the b4b8210 worker image's isolated Linux PDF parser
  passed upload, extraction, nine decisions, confirmation and opening the accepted obligation.
  Source attachment and zero new ledger postings verified. Synthetic provider; seeded session;
  queued handler pumped in-process; Vite frontend. This does not prove standalone worker,
  production web image, login, live-model quality or standard seeded E2E acceptance.
- Evidence: .run/future-draft-reader-{tests,types-final,lint}.log;
  .run/future-draft-browser-{tests,final}.log and .run/ai-live-browser-created.png.
  Full frozen CI remains active on 3cf8f5b; Compose and independent accounting sign-off remain open.
  No deployment. Temporary browser harness retained privately under .run.


## Expose administrator-only AI configuration gap — October 15, 2026

- Preparing the standard J-19/demo fixture revealed that its Tomas/Grace Tenant Admin personas
  cannot author or approve general registry policies. They hold settings.manage, not config.author
  or config.approve. Existing AI re-enable tests add admin rights to accounting-role actors.
- Added a strict expected-failure API regression for admin-only AI draft creation, accepting only
  the confirmed forbidden response as the known failure. Other failures remain errors; success
  becomes a strict XPASS requiring removal of the marker. A companion protects accounting-policy
  denial. This records an unfinished workflow, not a production-readiness pass.
- The corrective scope is an AI-specific admin lifecycle with independent approval and retained
  policy evidence, without broadening accounting privileges or bypassing the emergency switch.
  The standard demo fixture/E2E journey is not added through a permission bypass. Release
  limitations now distinguish this gap from the successful local browser probe.
- Six existing governance/boundary checks pass; the new workflow check is a confirmed strict
  expected failure. Focused typing and full lint pass. Evidence: .run/ai-admin-workflow-{tests,types,lint}.log.
  Frozen CI on 3cf8f5b remains active.
  No deployment, provider call or independent accounting sign-off.


## Administrator AI version authoring — October 15, 2026

- Added AI-scoped create/read/edit/test/submit/withdraw endpoints under /ai/settings/versions.
  Workspace-wide settings.manage and MFA are required; category and scope cannot be changed.
  Existing registry validation, hashes, simulation jobs, audit and If-Match behavior are reused.
  No publish endpoint or enable shortcut. General accounting authoring remains restricted.
- Admin-only authoring now passes instead of xfail. Lifecycle coverage confirms submission keeps
  AI disabled; isolation checks cover other categories/tenants and invalid accounting values.
  The independent administrator approval-read regression remains strict xfail because generic
  REGISTRY_VERSION routing still needs config.approve. AI-specific routing/visibility and UI are
  next; the standard demo/J-19 workflow is not claimed complete.
- Generated OpenAPI/TypeScript contracts add five paths (six operations); existing paths are
  unchanged. Eight API checks pass and one approval-read check is strict xfail; 34 other
  authority/governance/route checks passed in the expanded run. Typing (794 files) and full
  lint pass. Evidence: .run/ai-settings-author-{api-final,verified-final,types-final,openapi,lint}.log.
  Earlier expanded runs caught test-fixture enum/key-reuse mistakes, corrected in the API rerun.
- No deployment or provider calls. Frozen CI on 3cf8f5b remains active; independent accounting
  sign-off and broader release verification remain outstanding.

## Independent administrator AI approvals — October 15, 2026

- New AI submissions use AI_SETTINGS_VERSION with workspace-wide settings.manage review.
  A different Tenant Admin can approve without accounting privileges; self-approval remains
  refused. Retained REGISTRY_VERSION requests keep their original routing and publication hooks.
  Emergency disable, model/text review and immutable content checks remain in the lifecycle.
- settings.manage is an approval permission, so API clients cannot request or retain it in
  effective grants. Migration 0156 updates permission metadata and report filters; upgrade,
  downgrade, enum order and immutable catalogue triggers pass 12 focused checks.
- The broader regression selection passes 95 checks, including API clients, legacy routing,
  emergency disable and earlier report-filter migration compatibility. Evidence:
  .run/ai-admin-approval-{release,migration,release-types,frontend,lint}.log.
- Approval UI subject labels, OpenAPI/TypeScript and the data model are aligned. Frontend typing
  and 55 focused tests pass; backend typing passes 797 files. Full lint passes (503 control
  markers). The settings editor and standard J-19/demo journey remain unfinished.
- No deployment or provider calls. Frozen CI on 3cf8f5b remains running and predates this work;
  broader release verification and independent accounting sign-off remain outstanding.

## Administrator AI version discovery — October 15, 2026

- Added GET /ai/settings/versions with workspace-wide settings.manage, fixed tenant AI scope,
  status filtering, sorting, counts and cursor pagination. It shares the individual-read scope
  predicate, so refresh can rediscover drafts, pending requests and publication history.
- Tenant Admin already includes config.read; those broader read grants are unchanged. This
  endpoint gives the AI workflow its own scoped read boundary. Accounting authoring is unchanged.
  The settings editor, effective-status presentation and standard J-19/demo journey remain open.
- OpenAPI and TypeScript contracts regenerated. Route/scope architecture checks pass (11),
  backend typing passes 795 files, frontend typing and full lint pass (503 control markers).
  API verification and evidence are recorded in docs/release/CI-2026-10-15.md.
- No deployment or provider calls; frozen CI on 3cf8f5b remains active on its own database.

## Effective AI status for administrator settings — October 15, 2026

- Added read-only GET /ai/settings under workspace-wide settings.manage. It uses the AI job
  settings reader, distinguishing published enablement from effective availability, workspace
  emergency disable and platform disable. Provider identity and model/budget/text/redaction
  values are returned without credentials, provider construction or provider calls.
- API/PostgreSQL checks pass (31), covering draft exclusion, publication, both switches,
  defaults, tenant isolation and administrator denial. Backend typing passes 795 files.
  OpenAPI/TypeScript regenerated; frontend readers cover status and retained version pagination.
  Detailed verification is in docs/release/CI-2026-10-15.md.
- The settings editor and full J-19/demo journey remain unfinished. No deployment. Frozen CI
  on 3cf8f5b remains running; independent accounting sign-off and release gates remain open.

## Administrator AI settings screen — October 15, 2026

- Added /settings/ai and its workspace-wide settings.manage navigation guard. The page shows
  effective availability and platform disable, edits the eight documented values, resumes saved
  versions and submits through validation plus independent approval. Emergency disable uses a
  confirmation dialog and remains available during validation. Pending requests show their
  number, preparer and review link.
- Retries retain the original statement, row-version precondition and command keys. A newer read
  cannot silently replace the edit precondition; even a SUBMITTED read replays the caller's own
  submission key. Failed validation stops submission; reset-to-default drafts use catalogue values.
- Full frontend suite: 2,160 tests pass in 202 files; 43 focused checks and typing also pass.
  Real Chromium + API + PostgreSQL verifies creation, validation job and submission while AI
  remains off; desktop and pending screenshots
  inspected. A narrow viewport retains the existing minimum-width gate. Evidence is in
  docs/release/CI-2026-10-15.md. The private browser harness remains excluded in .run.
- No deployment or provider calls. Standard demo/J-19 and accounting sign-off remain open.
  Frozen CI on 3cf8f5b remains running; its snapshot predates these changes.

## AI settings without general configuration read access — October 15, 2026

- Added GET /ai/settings/values under workspace-wide settings.manage, returning only effective
  AI values and their reset defaults. The form no longer calls general configuration routes.
  Parameter choices are fixed by the server's AI catalogue; accounting keys cannot be selected.
- A custom role holding only settings.manage now passes form reads, validation-job reads,
  submission and a different custom-role administrator's approval. General policy/catalogue
  reads remain 403; draft values and another tenant's values are excluded. A real Chromium
  submission with this limited role passes and leaves AI off pending approval.
- Fifteen focused frontend tests, frontend typing, backend typing (795 files), route/scope checks
  and full lint pass. API evidence includes the corrected custom-role lifecycle after advancing
  its frozen clock past its predecessor publication. Details: docs/release/CI-2026-10-15.md.
- No deployment, provider call or new role grant. Standard demo/J-19, release gates and independent
  accounting sign-off remain open. Frozen CI on 3cf8f5b continues on its separate database.
